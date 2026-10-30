"""Offline OpenCode handoff protocol tests; returned model data is synthetic."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from faultaudit.bridge import OpenCodeJudge, export_model_tasks, submit_model_results
from faultaudit.importers import import_cases, import_catalog
from faultaudit.model import ModelError
from faultaudit.pipeline import execute, import_into, report_data
from faultaudit.store import AuditError, Store


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.test_root = Path(__file__).resolve().parent
        self.temp = tempfile.TemporaryDirectory(prefix="bridge-", dir=self.test_root)
        self.directory = Path(self.temp.name).resolve()
        self.store = Store(self.directory / "state")
        self.run_id = self.store.create_run({"is_synthetic": True})
        source = self.directory / "source.json"
        source.write_text(json.dumps([{"统一ID": "SYNTHETIC-WB-1", "事件编号": "TEST-INCIDENT-001",
            "问题描述": "合成客户TP6场景all_reduce出现乱码", "根因": "rounding", "算子": "all_reduce",
            "wiki": "https://example.invalid/wiki/one"}], ensure_ascii=False), encoding="utf-8")
        self.source_result = import_cases(source, "ORIGINAL_WEEKLY")
        import_into(self.store, self.run_id, self.source_result)
        self.case = self.source_result["cases"][0]
        catalog = self.directory / "catalog.json"
        catalog.write_text(json.dumps([{"item_id": "F-001", "description": "synthetic precision",
            "mechanism": "rounding", "operator": "all_reduce", "trigger": "PCIe"}]), encoding="utf-8")
        import_into(self.store, self.run_id, import_catalog(catalog), catalog=True)
        self.package = {"url": "https://example.invalid/wiki/one", "title": "Synthetic case",
            "text": "TEST-INCIDENT-001 synthetic: TP6 all_reduce乱码; rounding on PCIe; fixed by precision update.",
            "status": "COMPLETE", "components": {"body": "COMPLETE"}, "is_synthetic": True,
            "retrieved_by": "unittest-fixture", "case_ids": [self.case["case_id"]]}
        self.snapshot = self.store.ingest_evidence(self.run_id, self.package)

    def tearDown(self):
        self.store.close()
        self.assertTrue(self.directory.is_relative_to(self.test_root))
        self.temp.cleanup()

    def drive(self, run_id=None):
        run_id = run_id or self.run_id
        status = execute(self.store, run_id, OpenCodeJudge(self.store, run_id), mode="opencode", model_id="opencode-managed")
        return status, export_model_tasks(self.store, run_id)["tasks"]

    def envelope(self, task, result=None):
        payload = task["payload"]
        if result is None and task["kind"] == "summarize":
            snapshot = payload["snapshot"]
            segment = snapshot["segments"][0]
            result = {"snapshot_id": snapshot["snapshot_id"], "issues": [{"label": "Synthetic issue", "facts": [
                {"field": "operator", "value": "all_reduce", "evidence": [{"segment_id": segment["segment_id"], "quote": segment["text"]}]}]}],
                "unknown_fields": ["event attribution"]}
        elif result is None and task["kind"] == "compare":
            result = {"case_id": payload["case"]["case_id"], "snapshot_id": payload["snapshot"]["snapshot_id"],
                "case_attribution": "UNKNOWN", "event_relation": "UNDETERMINED", "pattern_relation": "UNDETERMINED",
                "support_level": "PENDING", "claim_support": {"symptom": "UNKNOWN", "root_cause": "UNKNOWN", "fix": "UNKNOWN", "verification": "UNKNOWN"},
                "matched_dimensions": [], "conflicting_dimensions": [], "unknown_dimensions": ["event"], "evidence": [],
                "event_anchor": "", "short_reason": "Synthetic protocol response only; attribution remains unknown.",
                "missing_information": ["human review"]}
        elif result is None:
            result = {"case_id": payload["case"]["case_id"], "scope": "FULL_CATALOG", "overall": "UNDETERMINED",
                "catalog_results": [{"item_id": item["item_id"], "result": "UNDETERMINED", "reason": "Unconfirmed synthetic case", "evidence": []}
                                    for item in payload["items"]]}
        return {"schema_version": "1.0", "run_id": task["run_id"], "task_id": task["task_id"],
            "request_hash": task["request_hash"], "result": result,
            "producer": {"executor": "opencode", "opencode_version": "2.2.0", "provider": "synthetic-protocol-test",
                         "model": "synthetic-reported-model", "session_id": "offline-unittest-session"}}

    def summary_done(self):
        _, tasks = self.drive()
        self.assertEqual([task["kind"] for task in tasks], ["summarize"])
        submit_model_results(self.store, self.run_id, [self.envelope(tasks[0])])
        _, tasks = self.drive()
        return tasks

    def test_three_stage_protocol_needs_no_network_or_model_config(self):
        environment = {key: value for key, value in os.environ.items() if key not in
                       {"FAULTAUDIT_BASE_URL", "FAULTAUDIT_MODEL", "FAULTAUDIT_API_KEY"}}
        with patch.dict(os.environ, environment, clear=True), patch("urllib.request.urlopen", side_effect=AssertionError("core must never call a model")) as network:
            _, tasks = self.drive()
            self.assertEqual([task["kind"] for task in tasks], ["summarize"])
            self.assertIn("text", tasks[0]["payload"]["snapshot"])
            self.assertIn("segments", tasks[0]["payload"]["snapshot"])
            for expected_kind in ("summarize", "compare", "catalog"):
                self.assertEqual([task["kind"] for task in tasks], [expected_kind])
                submitted = submit_model_results(self.store, self.run_id, [self.envelope(tasks[0])])
                self.assertEqual(submitted["accepted"], 1)
                status, tasks = self.drive()
            self.assertEqual(tasks, [])
            self.assertEqual(status["counts"]["judged_associations"], 1)
            self.assertEqual(status["counts"]["task_states"].get("FAILED", 0), 0)
            self.assertFalse(status["complete"])
            self.assertFalse(network.called)
        data = report_data(self.store, self.run_id)
        self.assertEqual(len(data["model_results"]), 3)
        self.assertTrue(all(result["producer"]["executor"] == "opencode" for result in data["model_results"]))

    def test_reexport_is_stable_and_does_not_unlock_compare(self):
        _, first = self.drive()
        _, second = self.drive()
        self.assertEqual(first, second)
        self.assertEqual([task["kind"] for task in second], ["summarize"])

    def test_wrong_request_hash_or_run_is_rejected(self):
        _, tasks = self.drive()
        envelope = self.envelope(tasks[0])
        for key, value in (("request_hash", "wrong"), ("run_id", "different-run"), ("schema_version", "0.0"), ("task_id", "nonexistent")):
            with self.subTest(key=key), self.assertRaises((AuditError, ValueError, ModelError)):
                submit_model_results(self.store, self.run_id, [{**envelope, key: value}])
        self.assertEqual(self.store.records(self.run_id, "model_results"), [])

    def test_wrong_snapshot_id_or_fabricated_quote_is_rejected(self):
        _, tasks = self.drive()
        envelope = self.envelope(tasks[0])
        wrong_id = copy.deepcopy(envelope)
        wrong_id["result"]["snapshot_id"] = "different-snapshot"
        with self.assertRaises((AuditError, ValueError, ModelError)):
            submit_model_results(self.store, self.run_id, [wrong_id])
        fabricated = copy.deepcopy(envelope)
        fabricated["result"]["issues"][0]["facts"][0]["evidence"][0]["quote"] = "this sentence never appeared"
        with self.assertRaises((AuditError, ValueError, ModelError)):
            submit_model_results(self.store, self.run_id, [fabricated])
        self.assertEqual(self.store.records(self.run_id, "model_results"), [])

    def test_snapshot_replacement_rejects_old_pending_result(self):
        _, tasks = self.drive()
        old = self.envelope(tasks[0])
        self.store.ingest_evidence(self.run_id, {**self.package, "text": "Updated synthetic source: new finding."})
        with self.assertRaises((AuditError, ValueError, ModelError)):
            submit_model_results(self.store, self.run_id, [old])
        self.assertEqual(export_model_tasks(self.store, self.run_id)["tasks"], [])

    def test_identical_submit_is_idempotent_but_changed_result_is_rejected(self):
        _, tasks = self.drive()
        envelope = self.envelope(tasks[0])
        self.assertEqual(submit_model_results(self.store, self.run_id, [envelope])["accepted"], 1)
        self.assertEqual(submit_model_results(self.store, self.run_id, [envelope])["idempotent"], 1)
        changed = copy.deepcopy(envelope)
        changed["result"]["unknown_fields"] = ["changed after first accepted response"]
        with self.assertRaises((AuditError, ValueError, ModelError)):
            submit_model_results(self.store, self.run_id, [changed])
        self.assertEqual(len(self.store.records(self.run_id, "model_results")), 1)

    def test_producer_and_result_metadata_must_agree(self):
        _, tasks = self.drive()
        original = self.envelope(tasks[0])
        for key, value in (("executor", "codex"), ("provider", ""), ("model", ""), ("session_id", ""), ("opencode_version", "")):
            bad = copy.deepcopy(original)
            bad["producer"][key] = value
            with self.subTest(key=key), self.assertRaises((AuditError, ValueError, ModelError)):
                submit_model_results(self.store, self.run_id, [bad])
        mismatch = copy.deepcopy(original)
        mismatch["result"]["model_id"] = "another-model"
        with self.assertRaises((AuditError, ValueError, ModelError)):
            submit_model_results(self.store, self.run_id, [mismatch])

    def test_compare_rejects_cross_snapshot_citation_and_wrong_case(self):
        tasks = self.summary_done()
        self.assertEqual([task["kind"] for task in tasks], ["compare"])
        envelope = self.envelope(tasks[0])
        bad_id = copy.deepcopy(envelope)
        bad_id["result"]["case_id"] = "other-case"
        with self.assertRaises((AuditError, ValueError, ModelError)):
            submit_model_results(self.store, self.run_id, [bad_id])
        false_citation = copy.deepcopy(envelope)
        false_citation["result"]["evidence"] = [{"segment_id": "another-snapshot:s1", "quote": self.snapshot["text"]}]
        with self.assertRaises((AuditError, ValueError, ModelError)):
            submit_model_results(self.store, self.run_id, [false_citation])

    def test_batch_is_checked_before_any_result_is_saved(self):
        self.store.ingest_evidence(self.run_id, {**self.package, "url": "https://example.invalid/wiki/two", "record_discovery": True})
        _, tasks = self.drive()
        self.assertEqual(len(tasks), 2)
        valid, invalid = (self.envelope(task) for task in tasks)
        invalid["request_hash"] = "wrong"
        with self.assertRaises((AuditError, ValueError, ModelError)):
            submit_model_results(self.store, self.run_id, [valid, invalid])
        self.assertEqual(self.store.records(self.run_id, "model_results"), [])

    def test_catalog_rejects_missing_entry(self):
        tasks = self.summary_done()
        submit_model_results(self.store, self.run_id, [self.envelope(tasks[0])])
        _, tasks = self.drive()
        self.assertEqual([task["kind"] for task in tasks], ["catalog"])
        invalid = self.envelope(tasks[0])
        invalid["result"]["catalog_results"] = []
        with self.assertRaises((AuditError, ValueError, ModelError)):
            submit_model_results(self.store, self.run_id, [invalid])

    def test_backed_external_proposal_preserves_producer_and_stays_for_review(self):
        tasks = self.summary_done()
        envelope = self.envelope(tasks[0])
        segment = tasks[0]["payload"]["snapshot"]["segments"][0]
        envelope["result"].update({"case_attribution": "CONFIRMED", "event_relation": "SAME_EVENT",
            "pattern_relation": "SAME_PATTERN", "support_level": "DIRECT", "event_anchor": "TEST-INCIDENT-001",
            "matched_dimensions": ["symptom", "root_cause", "trigger"], "unknown_dimensions": [],
            "claim_support": {"symptom": "SUPPORTED", "root_cause": "SUPPORTED", "fix": "SUPPORTED", "verification": "UNKNOWN"},
            "evidence": [{"segment_id": segment["segment_id"], "quote": segment["text"]}]})
        submit_model_results(self.store, self.run_id, [envelope])
        status, tasks = self.drive()
        self.assertEqual([task["kind"] for task in tasks], ["catalog"])
        data = report_data(self.store, self.run_id)
        judgment = data["judgments"][0]
        self.assertEqual(judgment["case_attribution"], "CONFIRMED")
        self.assertEqual(judgment["model_mode"], "opencode")
        self.assertEqual(judgment["model_id"], envelope["producer"]["model"])
        self.assertEqual(judgment["review_status"], "NEEDS_REVIEW")
        self.assertFalse(status["complete"])
        self.assertTrue(data["snapshots"][0]["is_synthetic"])

    def test_review_change_invalidates_pending_catalog_response(self):
        tasks = self.summary_done()
        submit_model_results(self.store, self.run_id, [self.envelope(tasks[0])])
        _, tasks = self.drive()
        self.assertEqual([task["kind"] for task in tasks], ["catalog"])
        stale_response = self.envelope(tasks[0])
        judgment = report_data(self.store, self.run_id)["judgments"][0]
        self.store.event(self.run_id, "review", {"judgment_id": judgment["judgment_id"], "verdict": "REJECT",
            "reason": "Synthetic rejection tests dependency invalidation", "reviewer": "offline-test"})
        with self.assertRaises((AuditError, ValueError, ModelError)):
            submit_model_results(self.store, self.run_id, [stale_response])

    def test_conflicting_duplicate_results_in_one_batch_are_rejected(self):
        _, tasks = self.drive()
        first = self.envelope(tasks[0])
        different = copy.deepcopy(first)
        different["result"]["unknown_fields"] = ["different assessment"]
        with self.assertRaises((AuditError, ValueError, ModelError)):
            submit_model_results(self.store, self.run_id, [first, different])
        self.assertEqual(self.store.records(self.run_id, "model_results"), [])


if __name__ == "__main__":
    unittest.main()
