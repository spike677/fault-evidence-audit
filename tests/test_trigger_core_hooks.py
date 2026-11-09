"""Synthetic acceptance of the shared CLI, import and summary-only hooks."""
from contextlib import closing
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import faultaudit
from faultaudit import cli, xlsx_workflow
from faultaudit.importers import extract_urls, import_cases, import_catalog
from faultaudit.model import MockJudge
from faultaudit.pipeline import execute, import_into
from faultaudit.store import AuditError, Store
from faultaudit.workflow_driver import executor_blocked


class TriggerCoreHookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="trigger-hooks-", dir=Path(__file__).parent)
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def source(self, rows, name="source.json"):
        path = self.root / name
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return path

    def test_mode_identity_aliases_and_cause_keep_raw_origin(self):
        for alias in ("baseline_id", "mode_id"):
            rows = [{alias: "M-original-1", "模式名称": "尾块寻址异常", "故障原因": "步长错误"}]
            path = self.source(rows)
            original = path.read_bytes()
            self.assertEqual(import_catalog(path)["items"][0]["item_id"], "M-original-1")
            case = import_cases(path)["cases"][0]
            self.assertEqual(case["root_cause_raw"], "步长错误")
            self.assertEqual(case["root_cause_origin"], "LEGACY_DERIVED_UNKNOWN")
            self.assertEqual(case["raw"], rows[0])
            self.assertEqual(path.read_bytes(), original)

    def test_escaped_scheme_is_parsed_without_mutating_raw(self):
        raw = r"https\://wiki.example.invalid/domains/1/wiki/WIKI1"
        self.assertEqual(extract_urls(raw), ["https://wiki.example.invalid/domains/1/wiki/WIKI1"])
        path = self.source([{"问题描述": "合成故障", "案例链接": raw}])
        result = import_cases(path)
        self.assertEqual(result["cases"][0]["raw"]["案例链接"], raw)
        self.assertEqual(result["references"][0]["raw_text"], raw)
        self.assertEqual(result["references"][0]["status"], "PARSED")

    def test_bare_dts_is_retained_even_beside_another_url(self):
        for text, expected_count in (("DTS2099010100001", 1),
                ("https://example.invalid/wiki/one\nDTS2099010100001", 2)):
            path = self.source([{"问题描述": "合成故障", "案例链接": text}])
            result = import_cases(path)
            self.assertEqual(len(result["references"]), expected_count)
            unresolved = [ref for ref in result["references"] if ref["status"] == "UNRESOLVED"]
            self.assertEqual(len(unresolved), 1)
            self.assertIn("DTS2099010100001", unresolved[0]["raw_text"])
            self.assertIsNone(unresolved[0]["url"])

    def test_original_mode_json_fields_keep_mode_id_and_bare_link(self):
        row = {"baseline_id": "CANN-original-04", "模式名称": "[合成] 接口参数适配异常",
               "故障原因": "[合成] 参数适配条件遗漏", "link": "DTS2022122705052"}
        path = self.source([row])
        original = path.read_bytes()
        mode = import_catalog(path)["items"][0]
        imported = import_cases(path)
        self.assertEqual(mode["item_id"], row["baseline_id"])
        self.assertEqual(mode["mechanism"], row["故障原因"])
        self.assertEqual(imported["cases"][0]["raw"], row)
        self.assertEqual(imported["cases"][0]["root_cause_raw"], row["故障原因"])
        self.assertEqual(len(imported["references"]), 1)
        ref = imported["references"][0]
        self.assertEqual((ref["raw_text"], ref["status"], ref["url"]), (row["link"], "UNRESOLVED", None))
        self.assertIn("/link", ref["location"])
        self.assertEqual(path.read_bytes(), original)

    def test_original_mode_raw_link_and_link_keep_both_cell_occurrences(self):
        identifier = "DTS2022122705052"
        row = {"baseline_id": "CANN-original-04", "模式名称": "[合成] 接口参数适配异常",
               "故障原因": "[合成] 参数适配条件遗漏", "raw_link": identifier, "link": identifier}
        path = self.source([row])
        imported = import_cases(path)
        refs = imported["references"]
        self.assertEqual(len(refs), 2)
        self.assertEqual(len({ref["ref_id"] for ref in refs}), 2)
        self.assertEqual({ref["raw_text"] for ref in refs}, {identifier})
        self.assertEqual({ref["status"] for ref in refs}, {"UNRESOLVED"})
        self.assertTrue(all(ref["url"] is None for ref in refs))
        self.assertTrue(any("/raw_link" in ref["location"] for ref in refs))
        self.assertTrue(any("/link " in ref["location"] for ref in refs))
        self.assertEqual(imported["cases"][0]["raw"], row)

    def test_summary_only_never_creates_incident_comparison_or_normal_validation(self):
        path = self.source([{"问题描述": "合成故障", "wiki": "https://example.invalid/wiki/one"}])
        with closing(Store(self.root / "state")) as store:
            run_id = store.create_run({"is_synthetic": True})
            import_into(store, run_id, import_cases(path))
            store.ingest_evidence(run_id, {"url": "https://example.invalid/wiki/one", "title": "合成资料",
                "text": "合成资料：尾块寻址步长错误。", "status": "COMPLETE", "components": {"body": "COMPLETE"},
                "is_synthetic": True, "retrieved_by": "unittest-fixture"})
            judge = MockJudge()
            with patch("faultaudit.pipeline.validate", side_effect=AssertionError("normal validate called")):
                result = execute(store, run_id, judge, mode="mock", model_id=judge.model_id, summarize_only=True)
            self.assertEqual(result["phase"], "SUMMARIZE_ONLY")
            self.assertTrue(result["complete"])
            self.assertEqual(result["counts"]["summaries"], 1)
            self.assertEqual({task["kind"] for task in store.tasks(run_id)}, {"summarize"})
            self.assertEqual(store.records(run_id, "judgments"), [])
            self.assertEqual(store.records(run_id, "mappings"), [])
            with patch.object(judge, "summarize", side_effect=AssertionError("duplicate summary")):
                again = execute(store, run_id, judge, mode="mock", model_id=judge.model_id, summarize_only=True)
            self.assertEqual(again["counts"], result["counts"])

    def test_summary_only_reports_missing_source_without_normal_pending_noise(self):
        path = self.source([{"问题描述": "合成故障", "wiki": "https://example.invalid/wiki/missing"}])
        with closing(Store(self.root / "state")) as store:
            run_id = store.create_run({"is_synthetic": True})
            import_into(store, run_id, import_cases(path))
            judge = MockJudge()
            result = execute(store, run_id, judge, mode="mock", model_id=judge.model_id, summarize_only=True)
            self.assertFalse(result["complete"])
            self.assertEqual(result["counts"]["missing_resources"], 1)
            self.assertEqual(result["tasks"][0]["kind"], "fetch")
            self.assertNotIn("pending", result)

    def test_trigger_context_block_requires_exact_outer_identity(self):
        request = {"kind": "trigger_classify", "request_hash": "a" * 64}
        response = {"outcome": "BLOCKED", "request_hash": "a" * 64,
                    "reason_code": "EXECUTOR_CONTEXT_LIMIT", "reason": "完整输入超过执行上下文。"}
        self.assertTrue(executor_blocked(request, response))
        response["request_hash"] = "b" * 64
        with self.assertRaisesRegex(AuditError, "outer request_hash"):
            executor_blocked(request, response)

    def test_cli_parser_default_user_branches_and_pending_flags(self):
        args = cli.parser().parse_args(["trigger-workflow", "init", "--modes", "m.xlsx", "--taxonomy", "t.md"])
        self.assertTrue(args.user_branches)
        args = cli.parser().parse_args(["trigger-workflow", "init", "--modes", "m.xlsx", "--taxonomy", "t.md", "--no-user-branches"])
        self.assertFalse(args.user_branches)
        args = cli.parser().parse_args(["trigger-workflow", "classify", "--baseline-run", "init-run", "--input", "new.xlsx", "--allow-pending-baseline"])
        self.assertTrue(args.allow_pending_baseline)
        args = cli.parser().parse_args(["trigger-workflow", "finalize", "--allow-pending"])
        self.assertTrue(args.allow_pending)

    def test_cli_routes_init_incremental_and_reuses_existing_workflow_commands(self):
        state = self.root / "state"
        with closing(Store(state)) as store:
            run_id = store.create_run({"is_synthetic": True})
        module = types.ModuleType("faultaudit.trigger_workflow")
        for name in ("start_init", "start_incremental", "status", "finalize", "export"):
            setattr(module, name, MagicMock(return_value={"status": "COMPLETE"}))
        prefix = ["--state", str(state), "trigger-workflow"]
        with patch.dict(sys.modules, {"faultaudit.trigger_workflow": module}), \
             patch.object(faultaudit, "trigger_workflow", module, create=True), patch.object(cli, "write_json"):
            self.assertEqual(cli.main([*prefix, "init", "--modes", "m.xlsx", "--taxonomy", "t.md"]), 0)
            self.assertTrue(module.start_init.call_args.kwargs["user_branches"])
            self.assertEqual(cli.main([*prefix, "classify", "--input", "new.xlsx", "--baseline-run", run_id,
                                       "--baseline-id", "B1", "--allow-pending-baseline"]), 0)
            self.assertEqual(module.start_incremental.call_args.kwargs["baseline_id"], "B1")
            self.assertTrue(module.start_incremental.call_args.kwargs["allow_pending_baseline"])
            for operation, method, extra in (("status", "status", []), ("finalize", "finalize", ["--allow-pending"])):
                self.assertEqual(cli.main([*prefix, operation, "--run", run_id, *extra]), 0)
                self.assertEqual(getattr(module, method).call_args.args[1], run_id)
            self.assertTrue(module.finalize.call_args.kwargs["allow_pending"])
            response = self.source({}, "response.json")
            command = self.source(["agent", "{request}", "{response}"], "command.json")
            operations = (("next", "next_tasks", []), ("submit", "submit", ["--task-id", "T1", "--response", str(response)]),
                ("retry", "retry", ["--task-id", "T1"]), ("export", "export", []),
                ("drive", "drive", ["--agent-command-file", str(command)]))
            for operation, method, extra in operations:
                target = module if operation == "export" else xlsx_workflow
                with patch.object(target, method, return_value={"status": "COMPLETE"}) as shared:
                    self.assertEqual(cli.main([*prefix, operation, "--run", run_id, *extra]), 0)
                    self.assertEqual(shared.call_args.args[1], run_id)


if __name__ == "__main__":
    unittest.main()
