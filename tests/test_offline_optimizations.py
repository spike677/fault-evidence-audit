"""External-environment regressions using local, synthetic inputs only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from faultaudit.contracts import Judgment
from faultaudit.importers import import_cases
from faultaudit.model import MockJudge, ModelError, validate_task_result
from faultaudit.pipeline import evidence_index, execute, gate_judgment, import_into, report_data
from faultaudit.store import AuditError, Store


ROOT = Path(__file__).resolve().parents[1]


class OfflineOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.directory = Path(self.temp.name)
        self.state = self.directory / "state"

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args, expected=0, without_site=False, io_encoding="utf-8"):
        environment = {**os.environ, "PYTHONIOENCODING": io_encoding}
        command = [sys.executable, *(["-S"] if without_site else []), str(ROOT / "run_faultaudit.py"),
                   "--state", str(self.state), *map(str, args)]
        process = subprocess.run(command, cwd=self.directory, env=environment, capture_output=True,
                                 encoding="utf-8", timeout=30)
        self.assertEqual(process.returncode, expected, process.stdout + process.stderr)
        self.assertFalse(process.stderr)
        return json.loads(process.stdout)

    def write_cases(self, name="weekly.json", rows=None):
        path = self.directory / name
        path.write_text(json.dumps(rows or [{"统一ID": "SYNTHETIC-1", "问题描述": "Synthetic only",
                                            "根因/进展": "Original observation", "wiki": "https://example.invalid/wiki/shared"}],
                                   ensure_ascii=False), encoding="utf-8")
        return path

    def catalog(self):
        from openpyxl import Workbook
        path = self.directory / "synthetic-catalog.xlsx"
        workbook = Workbook()
        inference = workbook.active
        inference.title = "推理汇总"
        training = workbook.create_sheet("训练汇总")
        for sheet, count in ((inference, 98), (training, 43)):
            sheet.append(["编号", "模式名称", "故障原因"])
            for index in range(1, count + 1):
                sheet.append([str(index), f"Synthetic pattern {index}", "Synthetic mechanism"])
        workbook.save(path)
        workbook.close()
        return path

    def test_doctor_runs_without_third_party_dependencies_or_state(self):
        result = self.cli("doctor", without_site=True)
        self.assertFalse(result["core_ready"])
        self.assertIsNone(result["dependencies"]["pydantic"])
        self.assertTrue(result["dependency_help"])
        self.assertFalse(self.state.exists())
        result = self.cli("import", "--input", self.write_cases(), without_site=True, expected=1)
        self.assertEqual(result["error"], "ModuleNotFoundError")
        self.assertFalse(self.state.exists())

    def test_json_output_supports_chinese_paths_with_an_ascii_inherited_console(self):
        target = self.directory / "中文 schema目录"
        result = self.cli("schemas", "--out", target, io_encoding="ascii")
        self.assertEqual(result["schemas"], str(target.resolve()))
        self.assertTrue((target / "EvidencePackage.schema.json").is_file())

    def test_installer_cli_outputs_chinese_paths_under_an_ascii_console(self):
        workspace = self.directory / "中文 工作区"
        workspace.mkdir()
        process = subprocess.run([sys.executable, str(ROOT / "scripts" / "install_opencode.py"),
                                  "--project", str(workspace)],
                                 env={**os.environ, "PYTHONIOENCODING": "ascii"},
                                 capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertIn(str(workspace), process.stdout)
        self.assertTrue((workspace / ".opencode" / "skills" / "fault-evidence-audit" / "core-location.json").is_file())

    def test_cli_freezes_inference_98_separately_from_training_43(self):
        source, catalog = self.write_cases(), self.catalog()
        options = ["--catalog", catalog, "--catalog-sheet", "推理汇总", "--catalog-scope", "INFERENCE",
                   "--expected-catalog-count", "98"]
        first = self.cli("import", "--input", source, "--source-kind", "ORIGINAL_WEEKLY", *options)
        run_id = first["run_id"]
        self.assertEqual(first["validation"]["counts"]["catalog_items"], 98)
        self.assertEqual(first["catalog_identity"]["scope"], "INFERENCE")
        repeated = self.cli("import", "--run", run_id, "--input", source, "--source-kind", "ORIGINAL_WEEKLY", *options)
        self.assertEqual(repeated["validation"]["counts"], first["validation"]["counts"])
        # Reject a different selection before adding unrelated new case rows.
        second_source = self.write_cases("other.json", [{"问题描述": "Should not be added"}])
        for sheet, scope, count in (("训练汇总", "TRAINING", 43), ("推理汇总", "TRAINING", 98)):
            result = self.cli("import", "--run", run_id, "--input", second_source,
                              "--catalog", catalog, "--catalog-sheet", sheet, "--catalog-scope", scope,
                              "--expected-catalog-count", count, expected=1)
            self.assertIn("frozen", result["message"])
        status = self.cli("status", "--run", run_id)
        self.assertEqual(status["counts"]["cases"], 1)
        self.assertEqual(status["counts"]["catalog_items"], 98)
        training = self.cli("import", "--input", source, "--catalog", catalog,
                            "--catalog-sheet", "训练汇总", "--catalog-scope", "TRAINING",
                            "--expected-catalog-count", 43)
        self.assertNotEqual(run_id, training["run_id"])
        self.assertEqual(training["validation"]["counts"]["catalog_items"], 43)

    def test_bad_catalog_selection_does_not_create_a_run(self):
        source, catalog = self.write_cases(), self.catalog()
        for options in (["--catalog-sheet", "不存在"],
                        ["--catalog-sheet", "推理汇总", "--expected-catalog-count", 141]):
            self.cli("import", "--input", source, "--catalog", catalog, *options, expected=1)
        store = Store(self.state)
        try:
            with self.assertRaises(AuditError):
                store.run_info("latest")
        finally:
            store.close()

    def test_duplicate_catalog_ids_reject_before_case_records_are_written(self):
        good = self.cli("import", "--input", self.write_cases())
        self.cli("import", "--input", self.write_cases(), "--catalog", self.catalog(), expected=1)
        store = Store(self.state)
        try:
            run_id = store.run_info("latest")["run_id"]
            self.assertEqual(run_id, good["run_id"], "Failed catalog import must not replace latest with an empty run")
            self.assertEqual(len(store.records(run_id, "cases")), 1)
            self.assertEqual(store.records(run_id, "catalog"), [])
        finally:
            store.close()

    def test_reverse_index_keeps_each_case_verdict_and_discovery_origin(self):
        source = self.write_cases(rows=[
            {"统一ID": "SYNTHETIC-A", "问题描述": "Different mechanism A", "wiki": "https://example.invalid/wiki/shared"},
            {"统一ID": "SYNTHETIC-B", "问题描述": "Different mechanism B", "wiki": "https://example.invalid/wiki/shared"},
        ])
        store = Store(self.state)
        try:
            run_id = store.create_run()
            imported = import_cases(source, "ORIGINAL_WEEKLY")
            import_into(store, run_id, imported)
            package = {"url": "https://example.invalid/wiki/shared", "text": "Synthetic: two distinct mechanisms.",
                       "status": "COMPLETE", "components": {"body": "COMPLETE"}, "is_synthetic": True,
                       "case_ids": [imported["cases"][0]["case_id"]], "origin": "SEARCH_DISCOVERED",
                       "record_discovery": True, "discovery_query": "synthetic search"}
            store.ingest_evidence(run_id, package)
            execute(store, run_id, MockJudge(), mode="mock", model_id="synthetic")
            index = evidence_index(store, run_id)
            self.assertEqual(index["shared_evidence_count"], 1)
            group = index["evidence_index"][0]
            self.assertEqual(len(group["associations"]), 2)
            self.assertEqual(len(group["references"]), 3)
            self.assertEqual({ref["origin"] for ref in group["references"]}, {"ORIGINAL_WEEKLY", "SEARCH_DISCOVERED"})
            self.assertTrue(all(len(a["judgments"]) == 1 for a in group["associations"]))
            judgment = group["associations"][0]["judgments"][0]
            store.event(run_id, "review", {"judgment_id": judgment["judgment_id"], "verdict": "REJECT",
                                           "reason": "Synthetic rejection", "reviewer": "test"})
            current = evidence_index(store, run_id)["evidence_index"][0]
            self.assertEqual(current["associations"][0]["judgments"][0]["review_status"], "REJECT")
            self.assertEqual(report_data(store, run_id)["evidence_index"], [current])
        finally:
            store.close()
        index = self.cli("evidence-index", "--run", run_id, "--url", package["url"])
        self.assertEqual(len(index["evidence_index"]), 1)
        self.assertEqual(self.cli("evidence-index", "--run", run_id, "--url", "https://example.invalid/absent")["evidence_index"], [])

    def test_content_captured_is_summarized_but_cannot_confirm_event(self):
        store = Store(self.state)
        try:
            run_id = store.create_run()
            imported = import_cases(self.write_cases(rows=[{
                "问题描述": "Synthetic incident", "event_id": "SYNTHETIC-EVENT-1",
                "wiki": "https://example.invalid/wiki/shared"}]), "ORIGINAL_WEEKLY")
            import_into(store, run_id, imported)
            snapshot = store.ingest_evidence(run_id, {
                "url": "https://example.invalid/wiki/shared", "text": "SYNTHETIC-EVENT-1: synthetic source content, event still unverified.",
                "status": "CONTENT_CAPTURED", "components": {"body": "COMPLETE"}, "is_synthetic": True})
            result = execute(store, run_id, MockJudge(), mode="mock", model_id="synthetic")
            self.assertEqual(len(store.records(run_id, "summaries")), 1)
            self.assertFalse(result["complete"])
            self.assertTrue(any("CONTENT_CAPTURED" in item for item in result["pending"]))
            judgment = store.records(run_id, "judgments")[0]
            proposed = {key: judgment[key] for key in Judgment.model_fields}
            proposed.update(case_attribution="CONFIRMED", support_level="DIRECT", event_relation="SAME_EVENT",
                            event_anchor="SYNTHETIC-EVENT-1", model_mode="opencode",
                            evidence=[{"segment_id": snapshot["segments"][0]["segment_id"], "quote": snapshot["text"]}])
            with self.assertRaisesRegex(AuditError, "Partial or failed retrieval"):
                gate_judgment(imported["cases"][0], snapshot, proposed)
            proposed["support_level"] = "PARTIAL"
            with self.assertRaises(ModelError) as rejected:
                validate_task_result("compare", proposed, case=imported["cases"][0], snapshot=snapshot)
            self.assertEqual(rejected.exception.code, "ungrounded_direct_support")
        finally:
            store.close()

    def test_legacy_complete_snapshot_is_rechecked_against_new_component_rules(self):
        store = Store(self.state)
        try:
            run_id = store.create_run()
            snapshot = store.ingest_evidence(run_id, {
                "url": "https://example.invalid/wiki/legacy", "text": "Synthetic old source.",
                "status": "COMPLETE", "components": {"body": "COMPLETE"}})
            # A 0.1.1 snapshot could declare COMPLETE while comments remained PARTIAL.
            snapshot["components"]["comments"] = "PARTIAL"
            self.assertTrue(any("incomplete components" in error for error in store.verify_snapshot(snapshot)))
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
