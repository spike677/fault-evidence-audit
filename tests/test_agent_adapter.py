"""Local synthetic producers exercise argv/file transport without network calls."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from faultaudit.agent_adapter import run_agent
from faultaudit.store import AuditError


class AgentAdapterTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).parent / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="agent-adapter-", dir=scratch)
        self.root = Path(self.temp.name)
        self.request = self.root / "input files" / "request.json"
        self.request.parent.mkdir()
        self.request.write_text(json.dumps({"synthetic": True, "value": "原文"}, ensure_ascii=False), encoding="utf-8")
        self.response = self.root / "attempt-1" / "response.json"

    def tearDown(self):
        self.temp.cleanup()

    def command(self, body):
        script = self.root / "synthetic producer.py"
        script.write_text("import json, pathlib, sys\n" + body, encoding="utf-8")
        return [sys.executable, str(script), "{request}", "{response}"]

    def test_success_reads_bom_response_with_absolute_paths_and_request_cwd(self):
        command = self.command(
            "request, response = map(pathlib.Path, sys.argv[1:])\n"
            "value = json.loads(request.read_text(encoding='utf-8'))\n"
            "value.update(request_absolute=request.is_absolute(), response_absolute=response.is_absolute(), "
            "cwd_is_request_parent=pathlib.Path.cwd() == request.parent)\n"
            "response.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8-sig')\n"
            "print('Progress text is not response JSON')\n")
        response = run_agent(command, self.request, self.response)
        self.assertEqual(response["value"], "原文")
        self.assertTrue(response["request_absolute"])
        self.assertTrue(response["response_absolute"])
        self.assertTrue(response["cwd_is_request_parent"])

    def test_embedded_placeholders_are_replaced_without_shell_interpretation(self):
        command = self.command(
            "request = pathlib.Path(sys.argv[1].removeprefix('--input='))\n"
            "response = pathlib.Path(sys.argv[2].removeprefix('--output='))\n"
            "response.write_text(json.dumps({'literal': sys.argv[3], 'read': request.is_file()}), encoding='utf-8')\n")
        command[-2:] = ["--input={request}", "--output={response}", "literal && not-a-shell-command"]
        response = run_agent(command, self.request, self.response)
        self.assertEqual(response["literal"], "literal && not-a-shell-command")
        self.assertTrue(response["read"])

    def test_process_receives_only_the_explicit_fresh_task_context_contract(self):
        command = self.command(
            "import os\n"
            "response = pathlib.Path(sys.argv[2])\n"
            "response.write_text(json.dumps({'context':os.environ['FAULTAUDIT_CONTEXT_MODE'],"
            "'request':os.environ['FAULTAUDIT_REQUEST_PATH'],'response':os.environ['FAULTAUDIT_RESPONSE_PATH']}),encoding='utf-8')\n")
        result = run_agent(command, self.request, self.response)
        self.assertEqual(result, {"context": "fresh-task", "request": str(self.request.resolve()),
                                  "response": str(self.response.resolve())})

    def test_feedback_uses_a_per_process_environment_without_mutating_parent(self):
        command = self.command(
            "import os\n"
            "pathlib.Path(sys.argv[2]).write_text(json.dumps({'feedback':os.environ['FAULTAUDIT_ATTEMPT_FEEDBACK']}),encoding='utf-8')\n")
        with patch.dict(os.environ, {"FAULTAUDIT_ATTEMPT_FEEDBACK": "unrelated-parent-task"}):
            result = run_agent(command, self.request, self.response, feedback="same-task-diagnostic " + "R" * 3000)
            self.assertEqual(len(result["feedback"]), 2000)
            self.assertTrue(result["feedback"].startswith("same-task-diagnostic "))
            self.assertEqual(os.environ["FAULTAUDIT_ATTEMPT_FEEDBACK"], "unrelated-parent-task")
        self.response = self.root / "attempt-2" / "response.json"
        with patch.dict(os.environ, {"FAULTAUDIT_ATTEMPT_FEEDBACK": "unrelated-parent-task"}):
            self.assertEqual(run_agent(command, self.request, self.response)["feedback"], "")
            self.assertEqual(os.environ["FAULTAUDIT_ATTEMPT_FEEDBACK"], "unrelated-parent-task")

    def test_existing_response_is_preserved_without_running_command(self):
        self.response.parent.mkdir()
        self.response.write_text('{"old": true}', encoding="utf-8")
        command = self.command("raise RuntimeError('must not execute')\n")
        with self.assertRaisesRegex(AuditError, "already exists"):
            run_agent(command, self.request, self.response)
        self.assertEqual(self.response.read_text(encoding="utf-8"), '{"old": true}')

    def test_retry_handoff_has_complete_same_task_answer_and_structured_diagnostic(self):
        request = {'request_hash':'a'*64, 'input_budget':{'budget':5000}, 'payload':{'source':'原始事实'}}
        self.request.write_text(json.dumps(request), encoding='utf-8')
        prior = self.request.parent / 'attempt-0001/response.json'; prior.parent.mkdir()
        old = {'request_hash':'a'*64, 'valid_part':'保留有效部分', 'bad_link':'F-missing'}
        prior.write_text(json.dumps(old, ensure_ascii=False), encoding='utf-8')
        self.response = self.request.parent / 'attempt-0002/response.json'
        command = self.command("import os\n"
            "context=json.loads(pathlib.Path(os.environ['FAULTAUDIT_RETRY_CONTEXT']).read_text(encoding='utf-8'))\n"
            "pathlib.Path(sys.argv[2]).write_text(json.dumps(context),encoding='utf-8')\n")
        diagnostic = {'row_id':'S5', 'link_id':'label_links[1]', 'missing_fact_ids':['F-missing']}
        result = run_agent(command, self.request, self.response, previous_response=str(prior),
                           diagnostic=diagnostic, feedback='定位错误，需修正引用')
        self.assertEqual(result['previous_response'], old)
        self.assertEqual(result['diagnostic'], diagnostic)
        self.assertEqual(json.loads(prior.read_text(encoding='utf-8')), old)
        size = json.loads((self.response.parent/'retry_input_budget.json').read_text(encoding='utf-8'))
        self.assertLessEqual(size['chars'], size['budget'])

    def test_retry_context_over_budget_is_blocked_without_truncation_or_launch(self):
        from faultaudit.input_budget import InputTooLarge
        self.request.write_text(json.dumps({'request_hash':'a'*64, 'input_budget':{'budget':1000}}), encoding='utf-8')
        prior = self.request.parent / 'old/response.json'; prior.parent.mkdir()
        prior.write_text(json.dumps({'request_hash':'a'*64,'body':'末尾结论'+ 'R'*2000}), encoding='utf-8')
        command = self.command("raise AssertionError('producer must not launch')\n")
        with self.assertRaises(InputTooLarge) as error:
            run_agent(command, self.request, self.response, previous_response=str(prior))
        self.assertGreater(error.exception.chars, error.exception.budget)
        self.assertFalse(self.response.exists())
        self.assertFalse((self.response.parent/'retry_context.json').exists())
        self.assertIn('末尾结论', json.loads(prior.read_text(encoding='utf-8'))['body'])

    def test_retry_rejects_other_task_identity_or_location(self):
        self.request.write_text(json.dumps({'request_hash':'a'*64}), encoding='utf-8')
        prior = self.request.parent/'old.json'; prior.write_text(json.dumps({'request_hash':'b'*64}), encoding='utf-8')
        command = self.command("raise AssertionError('must not launch')\n")
        with self.assertRaisesRegex(AuditError, 'unchanged task'):
            run_agent(command, self.request, self.response, previous_response=str(prior))
        outside = self.root/'other-task.json'; outside.write_text(json.dumps({'request_hash':'a'*64}), encoding='utf-8')
        with self.assertRaisesRegex(AuditError, 'belong to this task'):
            run_agent(command, self.request, self.response, previous_response=str(outside))

    def test_failed_process_logs_survive_and_attempt_directory_is_not_reused(self):
        command = self.command("print('RAW_STDOUT')\nprint('R'*3500,file=sys.stderr)\nraise SystemExit(2)\n")
        with self.assertRaisesRegex(AuditError, 'returncode=2'): run_agent(command, self.request, self.response)
        self.assertIn('RAW_STDOUT', (self.response.parent/'agent.stdout.log').read_text(encoding='utf-8'))
        self.assertGreater(len((self.response.parent/'agent.stderr.log').read_text(encoding='utf-8')), 3000)
        with self.assertRaisesRegex(AuditError, 'new attempt'): run_agent(command, self.request, self.response)

    def test_request_budget_is_handed_to_worker_without_changing_parent_environment(self):
        self.request.write_text(json.dumps({'input_budget': {'budget': 160000}}), encoding='utf-8')
        command = self.command(
            "import os\n"
            "pathlib.Path(sys.argv[2]).write_text(json.dumps({'budget':os.environ['FAULTAUDIT_MAX_INPUT_CHARS']}),encoding='utf-8')\n")
        with patch.dict(os.environ, {'FAULTAUDIT_MAX_INPUT_CHARS': '48000'}):
            self.assertEqual(run_agent(command, self.request, self.response)['budget'], '160000')
            self.assertEqual(os.environ['FAULTAUDIT_MAX_INPUT_CHARS'], '48000')

    def test_nonzero_exit_reports_stderr_and_keeps_attempt_output(self):
        command = self.command(
            "pathlib.Path(sys.argv[2]).write_text('{\"partial\": true}', encoding='utf-8')\n"
            "sys.stderr.write('synthetic command failed')\n"
            "sys.exit(7)\n")
        with self.assertRaisesRegex(AuditError, "returncode=7.*synthetic command failed"):
            run_agent(command, self.request, self.response)
        self.assertEqual(json.loads(self.response.read_text(encoding="utf-8")), {"partial": True})

    def test_zero_exit_without_response_is_not_success(self):
        with self.assertRaisesRegex(AuditError, "did not write"):
            run_agent(self.command("print('done')\n"), self.request, self.response)

    def test_invalid_response_json_is_not_success(self):
        command = self.command("pathlib.Path(sys.argv[2]).write_text('not json', encoding='utf-8')\n")
        with self.assertRaisesRegex(AuditError, "response JSON could not be read"):
            run_agent(command, self.request, self.response)

    def test_non_object_response_is_not_a_response_contract(self):
        command = self.command("pathlib.Path(sys.argv[2]).write_text('[]', encoding='utf-8')\n")
        with self.assertRaisesRegex(AuditError, "must be an object"):
            run_agent(command, self.request, self.response)

    def test_both_placeholders_are_required(self):
        for command in ([sys.executable, "{request}"], [sys.executable, "{response}"], []):
            with self.subTest(command=command):
                with self.assertRaisesRegex(AuditError, "both"):
                    run_agent(command, self.request, self.response)
        self.assertFalse(self.response.parent.exists())

    def test_timeout_stops_local_producer(self):
        command = self.command("import time\ntime.sleep(2)\n")
        with self.assertRaisesRegex(AuditError, "timed out"):
            run_agent(command, self.request, self.response, timeout=0.05)

    def test_missing_executable_reports_start_failure(self):
        command = [str(self.root / "missing-agent.exe"), "{request}", "{response}"]
        with self.assertRaisesRegex(AuditError, "could not start"):
            run_agent(command, self.request, self.response)


if __name__ == "__main__":
    unittest.main()
