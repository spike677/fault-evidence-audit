"""Local synthetic producers exercise argv/file transport without network calls."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

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

    def test_existing_response_is_preserved_without_running_command(self):
        self.response.parent.mkdir()
        self.response.write_text('{"old": true}', encoding="utf-8")
        command = self.command("raise RuntimeError('must not execute')\n")
        with self.assertRaisesRegex(AuditError, "already exists"):
            run_agent(command, self.request, self.response)
        self.assertEqual(self.response.read_text(encoding="utf-8"), '{"old": true}')

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
