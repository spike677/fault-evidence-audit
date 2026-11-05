"""Synthetic report/CLI integration; no field database or real model is used."""
import copy
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import test_bridge as bridge_tests
from faultaudit.bridge import submit_model_results
from faultaudit.exporters import export_report
from faultaudit.pipeline import report_data, validate
from faultaudit.statistics import report_statistics

ROOT = Path(__file__).resolve().parents[1]


class ReportReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = bridge_tests.BridgeTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.store, self.run_id = self.fixture.store, self.fixture.run_id

    def finish(self):
        for _ in range(20):
            _, tasks = self.fixture.drive()
            if not tasks:
                return
            submit_model_results(self.store, self.run_id, [self.fixture.envelope(task) for task in tasks])
        self.fail("Synthetic bridge did not reach an idle state")

    def test_report_keeps_multi_judgments_and_history_separate_from_round_counts(self):
        self.finish()
        baseline = report_data(self.store, self.run_id)
        self.store.ingest_evidence(self.run_id, {**self.fixture.package, "url": "https://example.invalid/wiki/two"})
        self.finish()
        self.store.ingest_evidence(self.run_id, {**self.fixture.package, "text": "Synthetic revised first source."})
        self.finish()
        data = report_data(self.store, self.run_id)
        manifest = {"run_id": self.run_id,
            "judgment_ids": sorted({j["judgment_id"] for j in data["judgments"]} - {j["judgment_id"] for j in baseline["judgments"]}),
            "mapping_ids": sorted({m["task_id"] for m in data["mappings"]} - {m["task_id"] for m in baseline["mappings"]}),
            "snapshot_ids": sorted({s["snapshot_id"] for s in data["snapshots"]} - {s["snapshot_id"] for s in baseline["snapshots"]})}
        reconciled = report_data(self.store, self.run_id, baseline=baseline, round_manifest=manifest)
        stats = reconciled["statistics"]
        self.assertEqual(stats["status"], "OK", stats)
        self.assertEqual(stats["current"]["including_rejected"], {"judgment_count": 1, "case_count": 1})
        self.assertEqual(stats["round"]["new_judgment_count"], 1)
        self.assertEqual(stats["round"]["new_case_count"], 1)
        self.assertEqual(stats["round"]["new_snapshot_count"], 2)
        duplicated = copy.deepcopy(reconciled)
        duplicated["judgments"].append(copy.deepcopy(duplicated["judgments"][0]))
        self.assertEqual(report_statistics(duplicated)["current"]["including_rejected"], stats["current"]["including_rejected"])
        outputs = export_report(reconciled, self.fixture.directory / "reconciled")
        self.assertEqual(json.loads(Path(outputs["statistics_json"]).read_text(encoding="utf-8")), stats)
        self.assertIn("统计口径", Path(outputs["report_html"]).read_text(encoding="utf-8"))
        state = validate(self.store, self.run_id)
        self.assertEqual(state["counts"]["current_judgment_ids_including_rejected"], 1)
        self.assertEqual(state["counts"]["current_case_ids_with_judgments_including_rejected"], 1)
        self.assertEqual(state["counts"]["pending_reason_entries"], len(state["pending"]))

    def test_json_reconciliation_never_opens_sqlite_and_reports_missing_baseline_unknown(self):
        source = self.fixture.directory / "report.json"
        source.write_text(json.dumps(report_data(self.store, self.run_id)), encoding="utf-8")
        missing_state = self.fixture.directory / "must-not-create-state"
        output = self.fixture.directory / "statistics.json"
        process = subprocess.run([sys.executable, str(ROOT / "run_faultaudit.py"), "--state", str(missing_state),
            "reconcile-report", "--input", str(source), "--out", str(output)], cwd=ROOT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertFalse(json.loads(process.stdout)["sqlite_opened"])
        self.assertFalse(missing_state.exists())
        stats = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(stats["round"]["status"], "UNKNOWN")
        self.assertIsNone(stats["round"]["new_judgment_count"])

    def test_json_reconciliation_reports_bad_manifest_without_changing_inputs(self):
        self.finish()
        source = self.fixture.directory / "report.json"
        source.write_text(json.dumps(report_data(self.store, self.run_id)), encoding="utf-8")
        manifest = self.fixture.directory / "round.json"
        manifest.write_text(json.dumps({"run_id": self.run_id, "judgment_ids": ["missing-judgment"],
                                       "mapping_ids": [], "snapshot_ids": []}), encoding="utf-8")
        before = source.read_bytes(), manifest.read_bytes()
        output = self.fixture.directory / "invalid-statistics.json"
        process = subprocess.run([sys.executable, str(ROOT / "run_faultaudit.py"), "reconcile-report", "--input", str(source),
            "--baseline", str(source), "--round-manifest", str(manifest), "--out", str(output)], cwd=ROOT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(process.returncode, 2, process.stdout + process.stderr)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "RECONCILIATION_FAILED")
        self.assertEqual((source.read_bytes(), manifest.read_bytes()), before)
