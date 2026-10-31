"""Synthetic records test review gates; no human approval is fabricated."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from faultaudit.importers import import_cases, import_catalog
from faultaudit.exporters import export_report
from faultaudit.pipeline import current_judgments, gate_judgment, import_into, report_data, validate
from faultaudit.bridge import policy_fingerprint
from faultaudit.store import Store, digest

ROOT = Path(__file__).resolve().parents[1]


class MappingReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.directory = Path(self.temp.name)
        self.store = Store(self.directory / "state")
        self.run_id = self.store.create_run({"is_synthetic": True})
        source = self.directory / "cases.json"
        source.write_text(json.dumps([{"description": "Synthetic precision incident", "event_id": "SYN-101",
                                       "wiki": "https://example.invalid/one"}]), encoding="utf-8")
        imported = import_cases(source, "ORIGINAL_WEEKLY")
        import_into(self.store, self.run_id, imported)
        self.case = imported["cases"][0]
        catalog = self.directory / "catalog.json"
        catalog.write_text(json.dumps([{"item_id": "F-001", "mechanism": "synthetic rounding"},
                                       {"item_id": "F-002", "mechanism": "synthetic cache invalidation"}]), encoding="utf-8")
        import_into(self.store, self.run_id, import_catalog(catalog), catalog=True)
        snapshot = self.store.ingest_evidence(self.run_id, {"url": "https://example.invalid/one",
            "text": "SYN-101 synthetic rounding verified by synthetic fixture.", "status": "COMPLETE",
            "components": {"body": "COMPLETE"}, "is_synthetic": True})
        refs = [{"segment_id": snapshot["segments"][0]["segment_id"], "quote": snapshot["text"]}]
        summary_task = self.store.task(self.run_id, "summarize", snapshot["snapshot_id"], [])
        summary = {"task_id": summary_task["task_id"], "snapshot_id": snapshot["snapshot_id"],
                   "issues": [], "unknown_fields": [], "model_mode": "codex", "model_id": "synthetic-fixture",
                   "policy_hash": policy_fingerprint()}
        self.store.put(self.run_id, "summaries", summary_task["task_id"], summary)
        self.store.task_status(self.run_id, summary_task["task_id"], "SUCCEEDED")
        task = self.store.task(self.run_id, "compare", self.case["case_id"] + "|" + snapshot["snapshot_id"], [])
        result = gate_judgment(self.case, snapshot, {"case_id": self.case["case_id"], "snapshot_id": snapshot["snapshot_id"],
            "case_attribution": "CONFIRMED", "event_relation": "SAME_EVENT", "pattern_relation": "SAME_PATTERN",
            "support_level": "DIRECT", "claim_support": {"symptom": "SUPPORTED", "root_cause": "SUPPORTED",
                "fix": "UNKNOWN", "verification": "UNKNOWN"}, "event_anchor": "SYN-101", "evidence": refs,
            "short_reason": "Synthetic review fixture only", "model_mode": "codex", "model_id": "synthetic-fixture"})
        self.judgment_id = task["task_id"]
        result.update(task_id=self.judgment_id, judgment_id=self.judgment_id,
                      policy_hash=policy_fingerprint(), case_hash=digest(self.case),
                      summary_task_id=summary_task["task_id"], summary_hash=digest(summary))
        self.store.put(self.run_id, "judgments", self.judgment_id, result)
        self.store.task_status(self.run_id, self.judgment_id, "SUCCEEDED")
        self.store.event(self.run_id, "review", {"judgment_id": self.judgment_id, "verdict": "ACCEPT",
            "reviewer": "synthetic-test-reviewer", "reason": "Synthetic test review, not a real business approval"})
        task = self.store.task(self.run_id, "catalog", self.case["case_id"], [])
        self.mapping_id = task["task_id"]
        self.store.put(self.run_id, "mappings", self.mapping_id, {"task_id": self.mapping_id, "case_id": self.case["case_id"],
            "overall": "COVERED", "scope": "FULL_CATALOG", "catalog_results": [{"item_id": "F-001", "result": "COVERED",
            "reason": "Synthetic mapping", "evidence": refs}, {"item_id": "F-002", "result": "NOT_COVERED",
            "reason": "Different synthetic mechanism", "evidence": []}], "review_status": "NEEDS_REVIEW", "model_mode": "codex",
            "model_id": "synthetic-fixture", "policy_hash": policy_fingerprint(), "case_hash": digest(self.case),
            "catalog_hash": digest(self.store.records(self.run_id, "catalog")),
            "judgments_hash": digest(current_judgments(self.store, self.run_id))})
        self.store.task_status(self.run_id, self.mapping_id, "SUCCEEDED")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def review_mapping(self, verdict):
        process = subprocess.run([sys.executable, str(ROOT / "run_faultaudit.py"), "--state", str(self.store.root),
            "review", "--run", self.run_id, "--mapping", self.mapping_id, "--verdict", verdict,
            "--reviewer", "synthetic-test-reviewer", "--reason", "Synthetic workflow test only"],
            capture_output=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        return json.loads(process.stdout)

    def test_unreviewed_mapping_keeps_strict_completion_pending(self):
        status = validate(self.store, self.run_id)
        self.assertTrue(status["valid"])
        self.assertFalse(status["complete"])
        self.assertTrue(any("catalog human review" in reason for reason in status["pending"]))
        self.review_mapping("ACCEPT")
        self.assertTrue(validate(self.store, self.run_id)["complete"])
        data = report_data(self.store, self.run_id)
        self.assertEqual(data["mappings"][0]["review_status"], "ACCEPT")
        self.assertEqual(data["judgments"][0]["review_status"], "ACCEPT")

    def test_rejected_mapping_remains_visible_and_pending(self):
        self.review_mapping("REJECT")
        self.assertFalse(validate(self.store, self.run_id)["complete"])
        self.assertEqual(report_data(self.store, self.run_id)["mappings"][0]["review_status"], "REJECT")
        paths = export_report(report_data(self.store, self.run_id), self.directory / "report")
        workbook = json.loads(Path(paths["workbook_data"]).read_text(encoding="utf-8"))
        summary = workbook["sheets"][0]
        row = dict(zip(summary["columns"], summary["rows"][0]))
        self.assertEqual(row["库覆盖（98条）"], "待核验", "Rejected mapping must not contribute coverage")

    def test_unknown_catalog_rows_cannot_be_hidden_by_covered_overall(self):
        mapping = self.store.get(self.run_id, "mappings", self.mapping_id)
        mapping["catalog_results"][1].update(result="UNDETERMINED", reason="Fixture gap")
        self.store.put(self.run_id, "mappings", self.mapping_id, mapping, mutable=True)
        self.review_mapping("ACCEPT")
        status = validate(self.store, self.run_id)
        self.assertFalse(status["complete"])
        self.assertTrue(any("catalog items undetermined" in reason for reason in status["pending"]))

    def test_judgment_review_invalidates_previously_accepted_mapping_immediately(self):
        self.review_mapping("ACCEPT")
        process = subprocess.run([sys.executable, str(ROOT / "run_faultaudit.py"), "--state", str(self.store.root),
            "review", "--run", self.run_id, "--judgment", self.judgment_id, "--verdict", "REJECT",
            "--reviewer", "synthetic-test-reviewer", "--reason", "Synthetic changed assessment"],
            capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        data = report_data(self.store, self.run_id)
        self.assertTrue(data["mappings"][0]["is_stale"])
        self.assertFalse(data["validation"]["complete"])


if __name__ == "__main__":
    unittest.main()
