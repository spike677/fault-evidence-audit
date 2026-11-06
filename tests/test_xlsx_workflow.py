"""Structured XLSX continuation through synthetic collection/model responses."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import Workbook

from faultaudit import xlsx_workflow as workflow
from faultaudit.catalog_drafts import COLUMNS
from faultaudit.model import ModelError
from faultaudit.store import AuditError, Store
from tests import test_codex_bridge as bridge_fixtures


class XlsxWorkflowTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).parent / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="xlsx-workflow-", dir=scratch)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "state")
        self.source = self.root / "source.xlsx"
        self.catalog = self.root / "catalog.json"
        self.catalog.write_text(json.dumps([{"item_id": "SYN-BASE", "description": "Synthetic frozen pattern",
            "mechanism": "not confirmed in this workflow"}]), encoding="utf-8")
        self.work = self.root / "runs"
        self.run = None

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def write_source(self, rows=None):
        book = Workbook()
        sheet = book.active
        sheet.title = "合成故障表"
        sheet.append(["统一ID", "问题描述", "根因", "wiki", "PR", "优先级"])
        for row in rows or [["SYN-ORIGINAL-1", "Synthetic output differs", "原始归因待核验",
                            "https://example.invalid/wiki/shared", "", "P1"]]:
            sheet.append(row)
        book.save(self.source)

    def start(self, rows=None):
        self.write_source(rows)
        config = workflow.start(self.store, self.source, self.catalog, self.work, executor="codex")
        self.run = config["run_id"]
        return config

    def load_request(self, task):
        return json.loads(Path(task["request"]).read_text(encoding="utf-8"))

    def package(self, url):
        return {"url": url, "title": "Synthetic captured source", "text": "Synthetic observation; mechanism is unknown.",
            "status": "CONTENT_CAPTURED", "components": {"body": "COMPLETE"}, "is_synthetic": True}

    def draft_response(self, request):
        context = request["payload"]
        case_ids = context["selected_case_ids"]
        row = {key: "未知（合成资料未说明）" for key in COLUMNS}
        row.update(level1="芯片使能", level2="CANN", level3="计算算子", level4="算子计算",
                   pattern_name="合成故障，机理待定位")
        bases = {key: {"kind": "UNKNOWN", "note": "Synthetic input does not establish this fact"} for key in COLUMNS}
        for key in ("level1", "level2", "level3", "level4", "pattern_name"):
            bases[key] = {"kind": "ABSTRACTION", "note": "Synthetic taxonomy, not a confirmed root cause"}
        return {"schema_version": "1.0", "kind": "CATALOG_DRAFT", "request_hash": request["request_hash"],
            "executor": "codex", "created_by": "synthetic-workflow-producer", "producer": {
                "executor_version": "synthetic", "provider": "synthetic-only", "model": "synthetic-fixture",
                "session_id": "offline-workflow-test"},
            "proposals": [{"proposal_id": "SYN-PROP-" + case_ids[0], "revision": 1, "action": "NO_CHANGE",
                "case_ids": case_ids, "work_ids": [], "evidence_scope": "INDEPENDENT_TECHNICAL_PATTERN",
                "implementation_owner": "UNKNOWN", "row": row, "field_bases": bases,
                "coverage_comparisons": [{"item_id": item["item_id"], "relation": "UNKNOWN",
                    "reason": "Synthetic input has no verified mechanism"} for item in context["catalog"]],
                "unknowns": ["故障机理待核验"], "conflicts": [], "self_check": {
                    "attempt": 1, "numeric_meaning_checked": True, "citations_checked": True,
                    "counterevidence_checked": True, "issue_scope_checked": True,
                    "event_vs_technical_checked": True, "passed": True, "issues": []}}]}

    def response(self, task):
        request = self.load_request(task)
        if task["kind"] == "fetch":
            return {"request_hash": request["request_hash"], "outcome": "CAPTURED",
                    "packages": [self.package(request["payload"]["url"])]}
        if task["kind"] in {"wiki_check", "search"}:
            return {"request_hash": request["request_hash"], "outcome": "NO_MATCH", "executed": True,
                "query": "synthetic bounded query", "scope": "synthetic project only", "checked_at": "2026-11-06T10:00:00+08:00",
                "executed_by": "synthetic-producer", "reason": "No match in the synthetic bounded corpus", "packages": []}
        if task["kind"] == "model":
            return bridge_fixtures.CodexBridgeTests.envelope(SimpleNamespace(run_id=self.run), request["payload"]["task"])
        if task["kind"] == "catalog_draft":
            return self.draft_response(request["payload"]["request"])
        self.fail("Unexpected workflow task kind: " + task["kind"])

    def complete_tasks(self):
        observed = []
        for _ in range(15):
            step = workflow.next_tasks(self.store, self.run)
            if not step["tasks"]:
                return step, observed
            for task in step["tasks"]:
                observed.append(task["kind"])
                workflow.submit(self.store, self.run, task["task_id"], self.response(task))
        self.fail("Synthetic workflow did not reach a stable no-task state")

    def test_start_supports_only_structured_xlsx_and_preserves_source_number(self):
        with self.assertRaisesRegex(AuditError, "structured XLSX"):
            workflow.start(self.store, self.root / "input.docx", self.catalog, self.work)
        book = Workbook()
        book.active.append(["Some arbitrary prose, no table header"])
        book.save(self.source)
        with self.assertRaisesRegex(AuditError, "recognized problem-description"):
            workflow.start(self.store, self.source, self.catalog, self.work)
        config = self.start()
        self.assertEqual(config["case_count"], 1)
        case = self.store.records(self.run, "cases")[0]
        self.assertEqual(case["external_id"], "SYN-ORIGINAL-1")
        self.assertEqual(case["source_kind"], "LEGACY_TABLE")
        self.assertEqual((case["sheet"], case["row"]), ("合成故障表", 2))
        self.assertTrue(case["cell_locations"]["问题描述"])
        self.assertEqual(case["root_cause_raw"], "原始归因待核验")

    def test_original_wiki_is_first_shared_url_is_fetched_once_and_next_is_stable(self):
        self.start([["SYN-1", "Synthetic issue one", "待定位", "https://example.invalid/wiki/shared", "https://github.com/example/synthetic/pull/1", "P1"],
                    ["SYN-2", "Synthetic issue two", "待定位", "https://example.invalid/wiki/shared", "", "P2"]])
        first = workflow.next_tasks(self.store, self.run)
        second = workflow.next_tasks(self.store, self.run)
        self.assertEqual(first["tasks"], second["tasks"])
        self.assertEqual(first["tasks"][0]["kind"], "fetch")
        self.assertNotIn("wiki_check", [task["kind"] for task in first["tasks"]])
        fetched_urls = [self.load_request(task)["payload"]["url"] for task in first["tasks"] if task["kind"] == "fetch"]
        self.assertEqual(fetched_urls.count("https://example.invalid/wiki/shared"), 1)
        self.assertEqual(self.load_request(first["tasks"][0])["payload"]["url"], "https://example.invalid/wiki/shared")

    def test_wiki_check_cannot_be_skipped_by_an_existing_readable_pr(self):
        self.start([["SYN-PR", "Synthetic output differs", "待定位", "", "https://github.com/example/synthetic/pull/1", "P1"]])
        self.store.ingest_evidence(self.run, self.package("https://github.com/example/synthetic/pull/1"))
        first = workflow.next_tasks(self.store, self.run)
        self.assertEqual(first["tasks"][0]["kind"], "wiki_check")
        check = first["tasks"][0]
        response = self.response(check)
        workflow.submit(self.store, self.run, check["task_id"], response)
        next_step = workflow.next_tasks(self.store, self.run)
        cid = self.store.records(self.run, "cases")[0]["case_id"]
        self.assertEqual(next_step["wiki_checks"][cid]["status"], "NO_MATCH")
        self.assertEqual(next_step["wiki_checks"][cid]["query"], response["query"])
        self.assertTrue(self.store.records(self.run, "wiki_checks"))
        self.assertFalse(any(task["kind"] == "wiki_check" for task in next_step["tasks"]))
        from faultaudit.evidence_plan import get_search_policy
        self.assertEqual(get_search_policy(self.store, self.run, cid)["policy"]["required_sources"], [])

    def test_full_file_loop_reuses_results_and_exports_one_workbook(self):
        cfg = self.start()
        step, observed = self.complete_tasks()
        self.assertIn("fetch", observed)
        self.assertIn("model", observed)
        self.assertIn("catalog_draft", observed)
        self.assertEqual(step["tasks"], [])
        self.assertEqual(workflow.next_tasks(self.store, self.run)["tasks"], [])
        attempts = self.store.records(self.run, "workflow_attempts")
        self.assertEqual(len(attempts), len(observed))
        self.assertEqual(self.store.events(self.run, "review"), [])
        captured = []
        def fake_export(source, target):
            captured.append(json.loads(source.read_text(encoding="utf-8")))
            target.write_bytes(b"synthetic-xlsx-output")
            (target.parent / "xlsx_previews").mkdir()
            (target.parent / "xlsx_previews" / "01.png").write_bytes(b"synthetic-preview")
            return {"xlsx": str(target)}
        with patch("faultaudit.exporters.export_workbook_xlsx", side_effect=fake_export):
            exported = workflow.export(self.store, self.run)
        final = Path(exported["xlsx"])
        self.assertEqual(final.name, "故障整理及模式库建议.xlsx")
        self.assertEqual(list(final.parent.iterdir()), [final])
        table = next(table for table in captured[0]["sheets"] if table["name"] == "整体故障排名")
        row = dict(zip(table["columns"], table["rows"][0]))
        self.assertEqual(row["原编号"], "SYN-ORIGINAL-1")
        self.assertEqual(row["来源文件"], str(self.source.resolve()))
        self.assertEqual(row["根因/进展原文"], "原始归因待核验")
        stats = next(table for table in captured[0]["sheets"] if table["name"] == "运行统计")
        self.assertTrue(any(row[0] == "运行验收状态" and row[1] == exported["status"] for row in stats["rows"]))
        files = [path for path in Path(cfg["directory"]).rglob("*") if path.is_file()]
        self.assertEqual({path.name for path in files}, {"request.json", "response.json", workflow.WORKBOOK_NAME})

    def test_invalid_response_is_retained_and_does_not_create_accept(self):
        self.start()
        task = workflow.next_tasks(self.store, self.run)["tasks"][0]
        response = self.response(task)
        response["request_hash"] = "wrong-request"
        with self.assertRaisesRegex(AuditError, "request_hash"):
            workflow.submit(self.store, self.run, task["task_id"], response)
        self.assertEqual(self.store.events(self.run, "review"), [])
        self.assertEqual(self.store.records(self.run, "workflow_attempts")[0]["status"], "REJECTED")
        accepted = workflow.submit(self.store, self.run, task["task_id"], self.response(task))
        self.assertTrue(accepted["accepted"])
        replay = workflow.submit(self.store, self.run, task["task_id"], self.response(task))
        self.assertTrue(replay["idempotent"])

    def test_model_cannot_submit_accept_through_workflow_entry(self):
        self.start()
        fetch = workflow.next_tasks(self.store, self.run)["tasks"][0]
        workflow.submit(self.store, self.run, fetch["task_id"], self.response(fetch))
        model = next(task for task in workflow.next_tasks(self.store, self.run)["tasks"] if task["kind"] == "model")
        response = self.response(model)
        response["result"]["review_status"] = "ACCEPT"
        with self.assertRaises(ModelError):
            workflow.submit(self.store, self.run, model["task_id"], response)
        self.assertEqual(self.store.events(self.run, "review"), [])
        self.assertEqual(self.store.records(self.run, "model_results"), [])

    def test_no_link_case_keeps_bounded_wiki_and_other_search_no_match(self):
        self.start([["SYN-NO-LINK", "Synthetic fault with no links", "待定位", "", "", "P2"]])
        step, observed = self.complete_tasks()
        self.assertEqual(observed.count("wiki_check"), 1)
        self.assertEqual(observed.count("search"), 1)
        self.assertIn("catalog_draft", observed)
        self.assertEqual(step["tasks"], [])
        self.assertTrue(all(check["status"] == "NO_MATCH" for check in step["wiki_checks"].values()))
        self.assertEqual(workflow.next_tasks(self.store, self.run)["tasks"], [])

    def test_driver_calls_configured_agent_adapter_and_finishes_without_extra_reports(self):
        self.start()
        calls = []
        def fake_agent(command, request_path, destination):
            request = json.loads(request_path.read_text(encoding="utf-8"))
            task = {"task_id": request["task_id"], "kind": request["kind"], "request": str(request_path)}
            response = self.response(task)
            destination.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
            calls.append((command, request["kind"]))
            return response
        def fake_export(source, target):
            target.write_bytes(b"synthetic-xlsx-output")
            return {"xlsx": str(target)}
        command = ["synthetic-agent", "{request}", "{response}"]
        with patch("faultaudit.agent_adapter.run_agent", side_effect=fake_agent), \
             patch("faultaudit.exporters.export_workbook_xlsx", side_effect=fake_export):
            result = workflow.drive(self.store, self.run, command)
        self.assertTrue(Path(result["xlsx"]).is_file())
        self.assertTrue(calls)
        self.assertTrue(all(call[0] == command for call in calls))
        self.assertEqual(workflow.next_tasks(self.store, self.run)["tasks"], [])

    def test_cli_start_next_submit_use_actual_python_and_paths_with_spaces(self):
        self.write_source()
        runner = Path(__file__).resolve().parents[1] / "run_faultaudit.py"
        environment = dict(os.environ, PYTHONIOENCODING="utf-8")
        def cli(*args):
            process = subprocess.run([sys.executable, str(runner), "--state", str(self.store.root),
                "xlsx-workflow", *map(str, args)], cwd=self.root, env=environment, capture_output=True,
                text=True, encoding="utf-8", timeout=30)
            self.assertEqual(process.returncode, 0, (process.stdout, process.stderr))
            self.assertFalse(process.stderr)
            return json.loads(process.stdout)
        config = cli("start", "--input", self.source, "--catalog", self.catalog,
                     "--work-root", self.root / "CLI work files", "--executor", "codex", "--expected-catalog-count", 1)
        self.run = config["run_id"]
        observed = []
        for _ in range(15):
            step = cli("next", "--run", self.run)
            if not step["tasks"]:
                break
            for task in step["tasks"]:
                observed.append(task["kind"])
                response_path = Path(task["response"])
                response_path.write_text(json.dumps(self.response(task), ensure_ascii=False), encoding="utf-8-sig")
                result = cli("submit", "--run", self.run, "--task-id", task["task_id"], "--response", response_path)
                self.assertTrue(result["accepted"])
        else:
            self.fail("CLI did not finish its synthetic task loop")
        self.assertIn("fetch", observed)
        self.assertIn("model", observed)
        self.assertIn("catalog_draft", observed)
        self.assertEqual(cli("next", "--run", self.run)["tasks"], [])
        self.assertEqual(Path(config["directory"]).parent, self.root / "CLI work files")
        self.assertEqual(self.store.records(self.run, "cases")[0]["external_id"], "SYN-ORIGINAL-1")
        self.assertEqual(self.store.events(self.run, "review"), [])

    def test_same_local_proposal_id_in_two_case_responses_keeps_both_suggestions(self):
        self.start([["SYN-1", "Synthetic first issue", "待定位", "https://example.invalid/wiki/shared", "", "P1"],
                    ["SYN-2", "Synthetic second issue", "待定位", "https://example.invalid/wiki/shared", "", "P2"]])
        original_response = self.draft_response
        def local_p1(request):
            response = original_response(request)
            response["proposals"][0]["proposal_id"] = "P1"
            return response
        with patch.object(self, "draft_response", side_effect=local_p1):
            self.complete_tasks()
        originals = self.store.records(self.run, "workflow_drafts")
        self.assertEqual(len(originals), 2)
        self.assertTrue(all(value["response"]["proposals"][0]["proposal_id"] == "P1" for value in originals))
        captured = []
        def fake_export(source, target):
            captured.append(json.loads(source.read_text(encoding="utf-8")))
            target.write_bytes(b"synthetic-xlsx-output")
            return {"xlsx": str(target)}
        with patch("faultaudit.exporters.export_workbook_xlsx", side_effect=fake_export):
            workflow.export(self.store, self.run)
        table = next(table for table in captured[0]["sheets"] if table["name"] == "模式库建议")
        rows = [dict(zip(table["columns"], row)) for row in table["rows"]]
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({row["提案编号"] for row in rows}), 2)
        self.assertTrue(all(row["提案编号"].endswith(":P1") for row in rows))
        self.assertEqual({row["关联原编号"] for row in rows}, {"SYN-1", "SYN-2"})
        self.assertTrue(all(value["response"]["proposals"][0]["proposal_id"] == "P1"
                            for value in self.store.records(self.run, "workflow_drafts")))

    def test_drive_resumes_an_agent_response_written_before_submit(self):
        self.start()
        pending = workflow.next_tasks(self.store, self.run)["tasks"][0]
        saved_path = Path(pending["response"])
        saved_path.write_text(json.dumps(self.response(pending), ensure_ascii=False), encoding="utf-8-sig")
        saved_bytes = saved_path.read_bytes()
        calls = []
        def fake_agent(command, request_path, destination):
            request = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertNotEqual(request["task_id"], pending["task_id"], "Existing complete response must be resumed, not overwritten")
            task = {"task_id": request["task_id"], "kind": request["kind"], "request": str(request_path)}
            response = self.response(task)
            destination.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
            calls.append(request["task_id"])
            return response
        def fake_export(source, target):
            target.write_bytes(b"synthetic-xlsx-output")
            return {"xlsx": str(target)}
        with patch("faultaudit.agent_adapter.run_agent", side_effect=fake_agent), \
             patch("faultaudit.exporters.export_workbook_xlsx", side_effect=fake_export):
            result = workflow.drive(self.store, self.run, ["synthetic-agent", "{request}", "{response}"])
        self.assertTrue(Path(result["xlsx"]).is_file())
        self.assertTrue(calls)
        self.assertEqual(saved_path.read_bytes(), saved_bytes)
        self.assertEqual(workflow.next_tasks(self.store, self.run)["tasks"], [])
        completed = [attempt for attempt in self.store.records(self.run, "workflow_attempts") if attempt["task_id"] == pending["task_id"]]
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["status"], "ACCEPTED")


if __name__ == "__main__":
    unittest.main()
