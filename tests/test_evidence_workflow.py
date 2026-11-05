"""Evidence-first acceptance through the real file bridge, using synthetic data."""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from faultaudit.bridge import OpenCodeJudge, export_model_tasks, submit_model_results
from faultaudit.evidence_plan import register_event_group
from faultaudit.importers import import_cases, import_catalog
from faultaudit.pipeline import evidence_plan, execute, fetch_tasks, import_into, report_data
from faultaudit.store import AuditError, Store

ROOT = Path(__file__).resolve().parents[1]
TEXT = "main：sample_op在推理阶段TP8首次输出异常，定位为舍入误差；logprob=0.404。修复版本未说明。"


class EvidenceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.directory = Path(self.temp.name)
        self.store = Store(self.directory / "state")
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        self.run_id = self.store.create_run({"is_synthetic": True})

    def load(self, count=1, source_kind="ORIGINAL_WEEKLY", with_links=True):
        rows = [{"统一ID": f"SYN-{i}", "问题描述": "首次输出异常", "触发条件": "推理阶段TP8", "算子": "sample_op",
                 "根因": "舍入误差", "关键数值": "logprob=0.404", "wiki": "https://example.invalid/main",
                 "PR": "https://example.invalid/unused"} for i in range(count)]
        if not with_links:
            for row in rows:
                row.pop("wiki")
                row.pop("PR")
        source = self.directory / "cases.json"
        source.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        imported = import_cases(source, source_kind)
        import_into(self.store, self.run_id, imported)
        catalog = self.directory / "catalog.json"
        catalog.write_text(json.dumps([{"item_id": "SYN-PATTERN", "mechanism": "rounding"}]), encoding="utf-8")
        import_into(self.store, self.run_id, import_catalog(catalog), catalog=True)
        return imported["cases"]

    def capture(self, status="PARTIAL"):
        return self.store.ingest_evidence(self.run_id, {"url": "https://example.invalid/main", "text": TEXT,
            "status": status, "components": {"body": "COMPLETE"}, "is_synthetic": True})

    def drive(self):
        status = execute(self.store, self.run_id, OpenCodeJudge(self.store, self.run_id), mode="opencode", model_id="opencode-managed")
        return status, export_model_tasks(self.store, self.run_id)["tasks"]

    def envelope(self, task):
        payload = task["payload"]
        if task["kind"] == "summarize":
            snap = payload["snapshot"]
            ref = {"segment_id": snap["segments"][0]["segment_id"], "quote": snap["text"]}
            result = {"snapshot_id": snap["snapshot_id"], "issues": [{"label": "main", "facts": [
                {"field": "observation", "value": snap["text"], "evidence": [ref]}]}], "unknown_fields": ["fix_version"]}
        elif task["kind"] == "catalog":
            result = {"case_id": payload["case"]["case_id"], "scope": "FULL_CATALOG", "overall": "UNDETERMINED",
                "catalog_results": [{"item_id": item["item_id"], "result": "UNDETERMINED", "reason": "Event remains unconfirmed", "evidence": []}
                                    for item in payload["items"]]}
        else:
            case, snap = payload["case"], payload["snapshot"]
            ref = {"segment_id": snap["segments"][0]["segment_id"], "quote": snap["text"]}
            def fact(category, field, meaning, value):
                return {"category": category, "source_field": field, "source_quote": case["raw"][field],
                    "source_cell": case["cell_locations"][field], "source_meaning": meaning, "evidence_meaning": meaning,
                    "source_value": value, "evidence_value": value, "evidence": [ref], "relation": "MATCH", "reason": "Exact scoped facts"}
            result = {"case_id": case["case_id"], "snapshot_id": snap["snapshot_id"], "case_attribution": "PARTIAL",
                "event_relation": "UNDETERMINED", "pattern_relation": "POSSIBLY_RELATED", "support_level": "PARTIAL",
                "claim_support": {"symptom": "SUPPORTED", "root_cause": "SUPPORTED", "fix": "UNKNOWN", "verification": "UNKNOWN"},
                "short_reason": "Original evidence supports the observed facts; fix version remains unknown", "evidence": [ref],
                "fact_comparisons": [fact("NUMBER", "关键数值", "logprob", "0.404"), fact("TERM", "算子", "operator", "sample_op"),
                    fact("SCENARIO", "问题描述", "symptom", "首次输出异常"), fact("SCENARIO", "触发条件", "occurrence_context", "推理阶段TP8"),
                    fact("TECHNICAL_CONCLUSION", "根因", "mechanism", "舍入误差")],
                "applicable_issue": {"label": "main", "evidence": [ref], "selection_reason": "One applicable problem"},
                "self_check": {"attempt": 1, "numeric_meaning_checked": True, "citations_checked": True,
                    "counterevidence_checked": True, "issue_scope_checked": True, "event_vs_technical_checked": True,
                    "passed": True, "issues": []}}
        return {"schema_version": "1.0", "run_id": self.run_id, "task_id": task["task_id"], "request_hash": task["request_hash"],
                "result": result, "producer": {"executor": "opencode", "opencode_version": "synthetic-test",
                    "provider": "offline-fixture", "model": "synthetic-model", "session_id": "synthetic-session"}}

    def finish(self):
        for _ in range(8):
            _, tasks = self.drive()
            if not tasks:
                return
            submit_model_results(self.store, self.run_id, [self.envelope(task) for task in tasks])
        self.fail("Evidence-first workflow kept generating new work")

    def test_partial_original_evidence_completes_without_search_or_human_queue(self):
        self.load()
        self.capture()
        self.finish()
        data = report_data(self.store, self.run_id)
        judgment = next(j for j in data["judgments"] if j["required"])
        self.assertEqual(judgment["processing_status"], "AUTO_PROCESSED")
        self.assertFalse(judgment["review_required"])
        self.assertEqual(judgment["review_status"], "NOT_REQUIRED")
        self.assertEqual(judgment["claim_support"]["fix"], "UNKNOWN")
        self.assertNotEqual(data["evidence_plans"]["cases"][0]["path"], "SEARCH_REQUIRED")
        self.assertEqual(fetch_tasks(self.store, self.run_id)["fetch_tasks"], [])
        before = self.store.records(self.run_id, "model_tasks")
        self.finish()
        self.assertEqual(self.store.records(self.run_id, "model_tasks"), before)
        self.assertEqual(len(before), 3)
        self.assertFalse(any("human review" in reason for reason in data["validation"]["pending"]))
        self.assertTrue(data["validation"]["fact_organization_complete"])
        self.assertFalse(data["validation"]["complete"], "Undetermined catalog coverage is retained independently")

    def test_confirmed_group_shares_work_and_retains_both_original_sources(self):
        cases = self.load(count=2)
        register_event_group(self.store, self.run_id, case_ids=[c["case_id"] for c in cases], user_confirmed=True,
                             confirmed_by="synthetic-user", reason="Explicit synthetic event relationship")
        self.capture()
        self.assertEqual(len(evidence_plan(self.store, self.run_id)["work_items"]), 1)
        self.finish()
        data = report_data(self.store, self.run_id)
        self.assertEqual(len(data["cases"]), 2)
        self.assertEqual(len(data["event_conclusions"]), 1)
        self.assertEqual(len([j for j in data["judgments"] if j["required"]]), 1)
        self.assertEqual(len(data["model_tasks"]), 3)

    def test_first_usable_search_evidence_stops_and_old_unused_work_never_becomes_success(self):
        case = self.load(with_links=False)[0]
        self.assertEqual(evidence_plan(self.store, self.run_id)["cases"][0]["path"], "SEARCH_REQUIRED")
        for url in ("https://example.invalid/candidate-a", "https://example.invalid/candidate-b"):
            self.store.ingest_evidence(self.run_id, {"url": url, "text": TEXT, "status": "PARTIAL",
                "is_synthetic": True, "origin": "SEARCH_DISCOVERED", "case_ids": [case["case_id"]]})
        initial = evidence_plan(self.store, self.run_id)
        selected = set(initial["cases"][0]["selected_ref_ids"])
        unused = next(ref for ref in self.store.records(self.run_id, "references") if ref["ref_id"] not in selected)
        old_task = self.store.task(self.run_id, "fetch", unused["ref_id"], ["synthetic-old-fetch"])
        self.store.task_status(self.run_id, old_task["task_id"], "BLOCKED", "Previous unexecuted task")
        self.finish()
        data = report_data(self.store, self.run_id)
        self.assertEqual(data["evidence_plans"]["cases"][0]["path"], "VERIFIED_SEARCH")
        self.assertEqual(len(data["model_tasks"]), 3)
        old = next(task for task in data["tasks"] if task["task_id"] == old_task["task_id"])
        self.assertFalse(old["required"])
        self.assertEqual(old["status"], "BLOCKED")
        self.assertFalse(any(old["task_id"] in reason for reason in data["validation"]["pending"]))
        self.assertEqual(len([ref for ref in data["references"] if not ref["required"]]), 1)

    def test_original_root_cause_conflict_keeps_reference_and_enters_exception_queue(self):
        self.load()
        self.store.ingest_evidence(self.run_id, {"url": "https://example.invalid/main", "text": TEXT.replace("舍入误差", "量化错配"),
            "status": "PARTIAL", "is_synthetic": True})
        _, tasks = self.drive()
        submit_model_results(self.store, self.run_id, [self.envelope(tasks[0])])
        _, tasks = self.drive()
        result = self.envelope(tasks[0])
        result["result"]["claim_support"]["root_cause"] = "CONTRADICTED"
        result["result"]["conflicting_dimensions"] = ["root_cause"]
        fact = result["result"]["fact_comparisons"][-1]
        fact.update(evidence_value="量化错配", relation="CONFLICT")
        submit_model_results(self.store, self.run_id, [result])
        self.drive()
        data = report_data(self.store, self.run_id)
        selected = [j for j in data["judgments"] if j["required"]]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["processing_status"], "EXCEPTION")
        self.assertTrue(selected[0]["review_required"])
        self.assertEqual(len(data["references"]), 2)
        self.assertEqual(len([ref for ref in data["references"] if ref["required"]]), 1)

    def test_plan_preview_opens_database_read_only_and_does_not_advance_tasks(self):
        self.load()
        before = self.store.conn.total_changes
        database = self.store.root / "audit.sqlite3"
        digest = hashlib.sha256(database.read_bytes()).hexdigest()
        process = subprocess.run([sys.executable, str(ROOT / "run_faultaudit.py"), "--state", str(self.store.root),
            "evidence-plan", "--run", self.run_id], cwd=ROOT, capture_output=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), digest)
        self.assertEqual(self.store.conn.total_changes, before)
        self.assertEqual(self.store.tasks(self.run_id), [])
        self.assertEqual(json.loads(process.stdout)["cases"][0]["path"], "FETCH_ORIGINAL")
