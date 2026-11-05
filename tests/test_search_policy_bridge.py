"""Synthetic file-executor parity and immutable search-policy binding.

The explicitly written responses below are fixtures, not live model output.
No MockJudge or generic semantic-response completion helper is used.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from faultaudit.bridge import CodexJudge, OpenCodeJudge, export_model_tasks, submit_model_results
from faultaudit.importers import import_cases, import_catalog
from faultaudit.pipeline import evidence_plan, execute, import_into, report_data
from faultaudit.store import AuditError, Store

ROOT = Path(__file__).resolve().parents[1]
DTS_URL = "https://example.invalid/dts/SYNTHETIC-101"
TEXT = "sample_op在TP8推理阶段首次输出异常，定位为舍入误差；logprob=0.404。修复版本未知。"


class SearchPolicyBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="policy-bridge-", dir=ROOT / "tests")
        self.directory = Path(self.temp.name)
        self.store = Store(self.directory / "state")
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        no_network = patch("urllib.request.urlopen", side_effect=AssertionError("Offline protocol tests cannot call services"))
        self.network = no_network.start()
        self.addCleanup(no_network.stop)
        source = self.directory / "source.json"
        source.write_text(json.dumps([{"统一ID": "SYN-POLICY-1", "问题描述": "首次输出异常",
            "触发条件": "TP8推理阶段", "算子": "sample_op", "根因": "舍入误差", "关键数值": "logprob=0.404",
            "DTS": DTS_URL}], ensure_ascii=False), encoding="utf-8")
        self.imported = import_cases(source, "ORIGINAL_WEEKLY")
        catalog = self.directory / "catalog.json"
        catalog.write_text(json.dumps([{"item_id": "SYN-P1", "mechanism": "rounding"},
                                       {"item_id": "SYN-P2", "mechanism": "quantization"}]), encoding="utf-8")
        self.catalog = import_catalog(catalog)

    def run_fixture(self):
        run_id = self.store.create_run({"is_synthetic": True})
        import_into(self.store, run_id, self.imported)
        import_into(self.store, run_id, self.catalog, catalog=True)
        snapshot = self.store.ingest_evidence(run_id, {"url": DTS_URL, "title": "Synthetic DTS source",
            "text": TEXT, "status": "PARTIAL", "components": {"body": "COMPLETE"}, "artifact_type": "DTS",
            "is_synthetic": True, "retrieved_by": "offline-fixture-collector"})
        return run_id, snapshot

    def drive(self, run_id, executor="opencode"):
        judge = (OpenCodeJudge if executor == "opencode" else CodexJudge)(self.store, run_id)
        status = execute(self.store, run_id, judge, mode=executor, model_id=executor + "-managed")
        return status, export_model_tasks(self.store, run_id, executor=executor)["tasks"]

    def fixture_envelope(self, task):
        """An explicitly declared synthetic semantic answer for this fixed case."""
        payload, executor = task["payload"], task["executor"]
        if task["kind"] == "catalog":
            result = {"case_id": payload["case"]["case_id"], "scope": "FULL_CATALOG", "overall": "UNDETERMINED",
                "catalog_results": [{"item_id": item["item_id"], "result": "UNDETERMINED",
                    "reason": "Synthetic factual processing does not confirm the incident or final coverage", "evidence": []}
                    for item in payload["items"]]}
        else:
            snap = payload["snapshot"]
            self.assertEqual(snap["text"], TEXT)
            ref = {"segment_id": snap["segments"][0]["segment_id"], "quote": TEXT}
            if task["kind"] == "summarize":
                result = {"snapshot_id": snap["snapshot_id"], "issues": [{"label": "synthetic-precision", "facts": [
                    {"field": "observation", "value": TEXT, "evidence": [ref]}]}], "unknown_fields": ["fix_version"]}
            else:
                case = payload["case"]
                facts = []
                for category, field, meaning, value in (
                    ("NUMBER", "关键数值", "log_probability", "0.404"),
                    ("TERM", "算子", "operator", "sample_op"),
                    ("SCENARIO", "问题描述", "symptom", "首次输出异常"),
                    ("SCENARIO", "触发条件", "occurrence_context", "TP8推理阶段"),
                    ("TECHNICAL_CONCLUSION", "根因", "mechanism", "舍入误差"),
                ):
                    facts.append({"category": category, "source_field": field, "source_quote": case["raw"][field],
                        "source_cell": case["cell_locations"][field], "source_value": value, "evidence_value": value,
                        "source_meaning": meaning, "evidence_meaning": meaning, "relation": "MATCH", "evidence": [ref],
                        "reason": "Explicit fixed synthetic observation with identical meaning in the cited scope"})
                result = {"case_id": case["case_id"], "snapshot_id": snap["snapshot_id"], "case_attribution": "PARTIAL",
                    "event_relation": "UNDETERMINED", "pattern_relation": "POSSIBLY_RELATED", "support_level": "PARTIAL",
                    "matched_dimensions": [], "conflicting_dimensions": [], "unknown_dimensions": ["event_identity", "fix_version"],
                    "event_anchor": "", "evidence": [ref], "short_reason": "Cited synthetic facts match; incident identity and fix remain unknown",
                    "missing_information": ["Fix version not captured"],
                    "claim_support": {"symptom": "SUPPORTED", "root_cause": "PARTIAL", "fix": "UNKNOWN", "verification": "UNKNOWN"},
                    "fact_comparisons": facts,
                    "applicable_issue": {"label": "synthetic-precision", "evidence": [ref], "selection_reason": "The single scoped synthetic problem"},
                    "self_check": {"attempt": 1, "numeric_meaning_checked": True, "citations_checked": True,
                        "counterevidence_checked": True, "issue_scope_checked": True, "event_vs_technical_checked": True,
                        "passed": True, "issues": []}}
        return {"schema_version": "1.0", "run_id": task["run_id"], "task_id": task["task_id"],
            "request_hash": task["request_hash"], "result": result,
            "producer": {"executor": executor, executor + "_version": "synthetic-protocol-version",
                         "provider": "offline-synthetic-fixture", "model": "synthetic-" + executor + "-model",
                         "session_id": "synthetic-" + executor + "-file-session"}}

    def cli(self, *arguments):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "run_faultaudit.py"), "--state", str(self.store.root),
                                 *arguments], cwd=ROOT, capture_output=True, encoding="utf-8", timeout=30,
                                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_opencode_and_codex_use_equivalent_three_stage_file_protocol(self):
        comparable = {}
        for executor in ("opencode", "codex"):
            with self.subTest(executor=executor):
                run_id, _ = self.run_fixture()
                comparable[executor] = {}
                for kind in ("summarize", "compare", "catalog"):
                    request_file = self.directory / (executor + "-" + kind + "-requests.json")
                    self.cli("model-tasks", "--run", run_id, "--executor", executor, "--out", str(request_file))
                    exported = json.loads(request_file.read_text(encoding="utf-8"))
                    self.assertEqual(exported["executor"], executor)
                    self.assertEqual([task["kind"] for task in exported["tasks"]], [kind])
                    task = exported["tasks"][0]
                    self.assertEqual(task["executor"], executor)
                    comparable[executor][kind] = copy.deepcopy(task["payload"])
                    response_file = self.directory / (executor + "-" + kind + "-responses.json")
                    response_file.write_text(json.dumps([self.fixture_envelope(task)], ensure_ascii=False), encoding="utf-8")
                    accepted = self.cli("submit-model-results", "--run", run_id, "--executor", executor, "--file", str(response_file))
                    self.assertEqual(accepted["accepted"], 1)
                data = report_data(self.store, run_id)
                self.assertTrue(data["validation"]["fact_organization_complete"], "Default one usable DTS does not force more search")
                self.assertFalse(data["validation"]["complete"], "Catalog uncertainty must remain visible")
                self.assertEqual(len(data["judgments"]), 1)
                self.assertFalse(data["judgments"][0]["review_required"])
                self.assertNotEqual(data["judgments"][0]["review_status"], "ACCEPT")
                control = data["evidence_plans"]["cases"][0]["search_control"]
                self.assertTrue(control["satisfied"])
                self.assertFalse(control["search_allowed"])
                self.assertEqual(control["usable_evidence_count"], 1)
                self.assertTrue(all(item["producer"]["executor"] == executor for item in data["model_results"]))
                self.assertTrue(all(item["producer"]["provider"] == "offline-synthetic-fixture" for item in data["model_results"]))
                before = self.store.records(run_id, "model_tasks")
                self.assertEqual(self.drive(run_id, executor)[1], [])
                self.assertEqual(self.store.records(run_id, "model_tasks"), before)
        self.assertEqual(comparable["opencode"]["summarize"], comparable["codex"]["summarize"])
        for executor in ("opencode", "codex"):
            comparable[executor]["compare"]["summary"].pop("model_mode")
            comparable[executor]["compare"]["summary"].pop("model_id")
        self.assertEqual(comparable["opencode"]["compare"], comparable["codex"]["compare"])
        self.assertFalse(self.network.called)

    def test_mixed_executor_envelopes_are_rejected_without_saving(self):
        run_id, _ = self.run_fixture()
        _, tasks = self.drive(run_id)
        correct = self.fixture_envelope(tasks[0])
        wrong = copy.deepcopy(correct)
        wrong["producer"] = {"executor": "codex", "codex_version": "synthetic-test", "provider": "offline-fixture",
                             "model": "synthetic-codex-model", "session_id": "synthetic-codex-session"}
        for envelope, executor in ((wrong, "opencode"), (correct, "codex")):
            with self.subTest(executor=executor), self.assertRaises(AuditError):
                submit_model_results(self.store, run_id, [envelope], executor=executor)
            self.assertEqual(self.store.records(run_id, "model_results"), [])
        self.assertEqual(submit_model_results(self.store, run_id, [correct], executor="opencode")["accepted"], 1)

    def test_changed_search_policy_invalidates_pending_comparison_but_reuses_summary(self):
        from faultaudit.evidence_plan import register_search_policy

        run_id, _ = self.run_fixture()
        _, tasks = self.drive(run_id)
        submit_model_results(self.store, run_id, [self.fixture_envelope(tasks[0])])
        _, tasks = self.drive(run_id)
        previous = next(task for task in tasks if task["kind"] == "compare")
        case_id = self.imported["cases"][0]["case_id"]
        old_policy = previous["payload"]["processing_context"]["search_policies"][case_id]
        register_search_policy(self.store, run_id, {"min_usable_evidence": 2, "required_sources": ["WIKI"],
                                                   "required_any_sources": ["GITCODE", "GITHUB"]}, case_id=case_id)
        before = self.store.records(run_id, "model_results")
        with self.assertRaises(AuditError):
            submit_model_results(self.store, run_id, [self.fixture_envelope(previous)])
        self.assertEqual(self.store.records(run_id, "model_results"), before)
        self.assertNotIn(previous["task_id"], {task["task_id"] for task in export_model_tasks(self.store, run_id)["tasks"]})
        _, tasks = self.drive(run_id)
        current = next(task for task in tasks if task["kind"] == "compare")
        self.assertEqual(current["work_id"], previous["work_id"])
        self.assertNotEqual(current["request_hash"], previous["request_hash"])
        self.assertNotEqual(current["payload"]["processing_context"]["search_policies"][case_id]["policy_hash"], old_policy["policy_hash"])
        self.assertEqual(current["payload"]["processing_context"]["processing_version"], "evidence-first-0.1.8")
        self.assertEqual(len([task for task in self.store.records(run_id, "model_tasks") if task["kind"] == "summarize"]), 1)
        incomplete = self.fixture_envelope(current)
        incomplete["result"].pop("fact_comparisons")
        with self.assertRaises(AuditError):
            submit_model_results(self.store, run_id, [incomplete])
        self.assertEqual(self.store.records(run_id, "model_results"), before)
        submit_model_results(self.store, run_id, [self.fixture_envelope(current)])
        self.drive(run_id)
        control = evidence_plan(self.store, run_id)["cases"][0]["search_control"]
        self.assertFalse(control["satisfied"])
        self.assertTrue(control["search_allowed"])
        self.assertFalse(report_data(self.store, run_id)["validation"]["fact_organization_complete"])


if __name__ == "__main__":
    unittest.main()
