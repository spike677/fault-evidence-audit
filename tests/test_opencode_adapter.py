"""CLI transport tests only; no provider, browser or semantic model execution."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_opencode_agent", ROOT / "scripts/run_opencode_agent.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

HELP = "--file FILE --format FORMAT --agent AGENT --model MODEL --attach URL --dir DIR"


class OpenCodeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="opencode-adapter-", dir=ROOT / "tests")
        self.project = Path(self.temp.name) / "项目 with spaces"
        agent = self.project / ".opencode/agents/fault-audit-worker.md"
        agent.parent.mkdir(parents=True)
        agent.write_text("---\nmode: all\n---\nSynthetic transport profile", encoding="utf-8")
        self.request = self.project / "request.json"
        self.request.write_text(json.dumps({"task_id":"synthetic-task","request_hash":"a"*64,"kind":"model",
                                             "payload":{"private":"PRIVATE_BODY"}}),encoding="utf-8")
        self.response = self.project / "attempt-1/response.json"

    def tearDown(self):
        self.temp.cleanup()

    def fake_process(self, argv, **kwargs):
        if argv[-1] == "--version":
            return subprocess.CompletedProcess(argv,0,"2.1.4\n","")
        if argv[-2:] == ["run","--help"]:
            return subprocess.CompletedProcess(argv,0,HELP,"")
        if argv[-1] == "--help":
            return subprocess.CompletedProcess(argv,0,"--server URL","")
        self.response.parent.mkdir(parents=True,exist_ok=True)
        self.response.write_text('{"synthetic_transport_only":true}',encoding="utf-8")
        return subprocess.CompletedProcess(argv,0,"","")

    def preflight(self, **kwargs):
        with patch.object(adapter.shutil,"which",return_value="synthetic-opencode.exe"), \
             patch.object(adapter.subprocess,"run",side_effect=self.fake_process):
            return adapter.preflight("opencode",self.project,**kwargs)

    def test_preflight_reports_unprobed_tool_and_model_capabilities(self):
        result = self.preflight()
        self.assertEqual(result["cli_version"],"2.1.4")
        self.assertEqual(result["context_mode"],"fresh-task")
        for key in ("subagent_tool_access","edge_login_and_body_access","agent_search_access","provider_model_execution"):
            self.assertEqual(result[key],"NOT_PROBED")

    def test_command_has_one_request_fresh_session_and_no_inline_private_body(self):
        caps = self.preflight()
        command = adapter.build_command(caps,self.request,self.response,kind="model")
        self.assertEqual(command[:3],["synthetic-opencode.exe","run","--format"])
        self.assertEqual(command[command.index("--file")+1],str(self.request.resolve()))
        self.assertEqual(command[command.index("--agent")+1],"fault-audit-worker")
        self.assertEqual(command[command.index("--dir")+1],str(self.project.resolve()))
        for flag in ("--session","--continue","--fork","-c","-s","--auto"):
            self.assertNotIn(flag,command)
        self.assertNotIn("PRIVATE_BODY"," ".join(command))
        self.assertIn(str(self.response.resolve()),command[-3])
        self.assertEqual(command[-2:],["--file",str(self.request.resolve())])

    def test_retry_diagnostic_is_non_source_feedback_and_does_not_inline_old_answers(self):
        caps = self.preflight()
        diagnostic = "citation is not in selected snapshot segment; " + "R" * 3000
        with patch.dict(adapter.os.environ, {"FAULTAUDIT_ATTEMPT_FEEDBACK": diagnostic}):
            command = adapter.build_command(caps,self.request,self.response,kind="model")
        prompt = command[-3]
        self.assertIn("THIS SAME TASK", prompt)
        self.assertIn("not source evidence", prompt)
        self.assertIn("citation is not in selected snapshot segment;", prompt)
        self.assertNotIn("R" * 3000, prompt)
        self.assertNotIn("PRIVATE_BODY", " ".join(command))
        self.assertEqual(command[-2:], ["--file", str(self.request.resolve())])
        fresh = adapter.build_command(caps,self.request,self.response,kind="model",feedback="")
        self.assertNotIn("previous attempt", fresh[-3])

    def test_legacy_attach_uses_only_advertised_flag(self):
        caps = self.preflight(server_url="http://localhost:4096")
        command = adapter.build_command(caps,self.request,self.response,kind="fetch",server_url="http://localhost:4096")
        self.assertIn("--attach",command)
        self.assertNotIn("--server",command)
        self.assertEqual(caps["backend_version"],"NOT_PROBED")

    def test_global_server_profile_is_detected_without_version_guess(self):
        def process(argv,**kwargs):
            if argv[-2:]==["run","--help"]:
                return subprocess.CompletedProcess(argv,0,"--file --format --agent","")
            return self.fake_process(argv,**kwargs)
        with patch.object(adapter.shutil,"which",return_value="synthetic-opencode.exe"), \
             patch.object(adapter.subprocess,"run",side_effect=process):
            caps=adapter.preflight("opencode",self.project,server_url="http://localhost:4096")
        command=adapter.build_command(caps,self.request,self.response,kind="search",server_url="http://localhost:4096")
        self.assertEqual(command[:4],["synthetic-opencode.exe","--server","http://localhost:4096","run"])
        self.assertNotIn("--dir",command)

    def test_missing_required_flag_is_blocked_before_task_launch(self):
        with patch.object(adapter.shutil,"which",return_value="synthetic-opencode.exe"), \
             patch.object(adapter.subprocess,"run",return_value=subprocess.CompletedProcess([],0,"--file --format", "")):
            with self.assertRaisesRegex(RuntimeError,"does not advertise"):
                adapter.preflight("opencode",self.project)

    def test_user_credentials_are_not_allowed_in_server_argv(self):
        for server in ("https://user:secret@example.invalid", "https://example.invalid?token=secret"):
            with self.assertRaisesRegex(RuntimeError,"credential-free"):
                self.preflight(server_url=server)

    def test_execute_does_not_rewrite_transport_body_or_guess_producer(self):
        with patch.object(adapter.shutil,"which",return_value="synthetic-opencode.exe"), \
             patch.object(adapter.subprocess,"run",side_effect=self.fake_process) as calls:
            observed=adapter.execute_task("opencode",self.project,self.request,self.response,timeout=12)
        self.assertEqual(observed["status"],"RESPONSE_WRITTEN")
        self.assertEqual(json.loads(self.response.read_text("utf-8")),{"synthetic_transport_only":True})
        self.assertEqual(len(calls.call_args_list),4)
        self.assertEqual(calls.call_args.kwargs["timeout"],12)
        self.assertEqual(calls.call_args.kwargs["cwd"],self.project.resolve())
        self.assertFalse(calls.call_args.kwargs["shell"])

    def test_existing_response_is_never_overwritten(self):
        self.response.parent.mkdir()
        self.response.write_text('{"old":true}',encoding="utf-8")
        with patch.object(adapter.subprocess,"run") as calls:
            with self.assertRaisesRegex(RuntimeError,"fresh attempt"):
                adapter.execute_task("opencode",self.project,self.request,self.response)
        calls.assert_not_called()
        self.assertEqual(self.response.read_text("utf-8"),'{"old":true}')

    def test_no_response_and_nonzero_exit_are_not_success(self):
        for code in (0,7):
            with self.subTest(code=code),patch.object(adapter,"preflight",return_value=self.preflight()), \
                 patch.object(adapter,"_invoke",return_value=subprocess.CompletedProcess([],code,"done", "")):
                with self.assertRaisesRegex(RuntimeError,"without writing|process failed"):
                    adapter.execute_task("opencode",self.project,self.request,self.response)

    def test_template_can_run_as_child_or_fresh_cli_worker(self):
        text=(ROOT/"integration/.opencode/agents/fault-audit-worker.md").read_text("utf-8")
        self.assertIn("mode: all",text)
        self.assertIn("Do not launch further workers",text)
        self.assertIn("capture_observation",text)
        self.assertIn("search_attempts",text)
        self.assertIn("Only the user enters credentials",text)


if __name__=="__main__":
    unittest.main()
