"""Codex file-executor integration; every source and returned result is synthetic."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from faultaudit.bridge import CodexJudge, OpenCodeJudge, export_model_tasks, submit_model_results
from faultaudit.importers import import_cases, import_catalog
from faultaudit.input_budget import finalize_model_task
from faultaudit.model import ModelError
from faultaudit.pipeline import execute, import_into, report_data
from faultaudit.store import AuditError, Store, digest


class CodexBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-bridge-", dir=Path(__file__).resolve().parent)
        self.directory = Path(self.temp.name)
        self.store = Store(self.directory / "state")
        self.run_id = self.store.create_run({"is_synthetic": True})
        source = self.directory / "source.json"
        source.write_text(json.dumps([{
            "统一ID": "SYNTHETIC-CODEX-1", "事件编号": "SYNTHETIC-CODEX-EVENT-1",
            "问题描述": "Synthetic precision issue", "根因": "synthetic rounding",
            "wiki": "https://example.invalid/wiki/codex"}]), encoding="utf-8")
        imported = import_cases(source, "ORIGINAL_WEEKLY")
        import_into(self.store, self.run_id, imported)
        self.case = imported["cases"][0]
        catalog = self.directory / "catalog.json"
        catalog.write_text(json.dumps([{"item_id": "SYNTHETIC-PATTERN-1", "description": "Synthetic pattern",
                                        "mechanism": "synthetic rounding"}]), encoding="utf-8")
        import_into(self.store, self.run_id, import_catalog(catalog), catalog=True)
        self.package = {"url": "https://example.invalid/wiki/codex", "title": "Synthetic Codex fixture",
                        "text": "SYNTHETIC-CODEX-EVENT-1: synthetic precision observation; cause remains unverified.",
                        "status": "COMPLETE", "components": {"body": "COMPLETE"}, "is_synthetic": True}
        self.snapshot = self.store.ingest_evidence(self.run_id, self.package)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def drive(self):
        status = execute(self.store, self.run_id, CodexJudge(self.store, self.run_id),
                         mode="codex", model_id="codex-managed")
        return status, export_model_tasks(self.store, self.run_id, executor="codex")["tasks"]

    def envelope(self, task):
        payload = task["payload"]
        if task["kind"] == "summarize":
            segment = payload["snapshot"]["segments"][0]
            result = {"snapshot_id": payload["snapshot"]["snapshot_id"], "issues": [{"label": "Synthetic source", "facts": [
                {"field": "observation", "value": segment["text"],
                 "evidence": [{"segment_id": segment["segment_id"], "quote": segment["text"]}]}]}],
                "unknown_fields": ["verified root cause"]}
        elif task["kind"] == "compare":
            result = {"case_id": payload["case"]["case_id"], "snapshot_id": payload["snapshot"]["snapshot_id"],
                      "case_attribution": "UNKNOWN", "event_relation": "UNDETERMINED",
                      "pattern_relation": "UNDETERMINED", "support_level": "PENDING",
                      "claim_support": {"symptom": "UNKNOWN", "root_cause": "UNKNOWN", "fix": "UNKNOWN", "verification": "UNKNOWN"},
                      "matched_dimensions": [], "conflicting_dimensions": [], "unknown_dimensions": ["root cause"],
                      "evidence": [], "event_anchor": "", "short_reason": "Synthetic response, no semantic confirmation.",
                      "missing_information": ["root-cause validation"]}
        else:
            result = {"case_id": payload["case"]["case_id"], "scope": "FULL_CATALOG", "overall": "UNDETERMINED",
                      "catalog_results": [{"item_id": item["item_id"], "result": "UNDETERMINED",
                                           "reason": "Synthetic event remains unconfirmed.", "evidence": []}
                                          for item in payload["items"]]}
        return {"schema_version": "1.0", "run_id": self.run_id, "task_id": task["task_id"],
                "request_hash": task["request_hash"], "result": result,
                "producer": {"executor": "codex", "codex_version": "unreported",
                             "provider": "synthetic-protocol-test", "model": "synthetic-codex-result",
                             "session_id": "offline-codex-protocol-fixture"}}

    def submit(self, envelope):
        return submit_model_results(self.store, self.run_id, [envelope], executor="codex")

    def test_codex_three_stage_protocol_preserves_real_executor_identity(self):
        status, tasks = self.drive()
        for kind in ("summarize", "compare", "catalog"):
            self.assertEqual([task["kind"] for task in tasks], [kind])
            task = tasks[0]
            self.assertEqual(task["executor"], "codex")
            self.assertEqual(task["model_service"], "codex")
            self.assertNotIn("DeepSeek", task["model_role"])
            envelope = self.envelope(task)
            self.assertEqual(self.submit(envelope)["accepted"], 1)
            self.assertEqual(self.submit(envelope)["idempotent"], 1)
            status, tasks = self.drive()
        self.assertEqual(tasks, [])
        self.assertFalse(status["complete"])
        self.assertEqual(status["counts"]["task_states"].get("FAILED", 0), 0)
        data = report_data(self.store, self.run_id)
        self.assertEqual(len(data["model_results"]), 3)
        self.assertTrue(all(result["producer"]["executor"] == "codex" for result in data["model_results"]))
        self.assertTrue(all(result["producer"]["codex_version"] == "unreported" for result in data["model_results"]))
        self.assertTrue(all(result["result"]["model_mode"] == "codex" for result in data["model_results"]))
        self.assertEqual(data["judgments"][0]["model_id"], "synthetic-codex-result")
        self.assertEqual(len(self.store.events(self.run_id, "codex_result_received")), 3)

    def test_opencode_default_neither_exports_nor_accepts_codex_tasks(self):
        _, tasks = self.drive()
        self.assertEqual(export_model_tasks(self.store, self.run_id)["tasks"], [])
        with self.assertRaisesRegex(AuditError, "another executor"):
            submit_model_results(self.store, self.run_id, [self.envelope(tasks[0])])
        envelope = self.envelope(tasks[0])
        envelope["producer"].update(executor="opencode", opencode_version="unreported")
        with self.assertRaisesRegex(AuditError, "Producer"):
            self.submit(envelope)
        self.assertEqual(self.store.records(self.run_id, "model_results"), [])

    def test_codex_producer_metadata_is_required_and_result_metadata_must_agree(self):
        _, tasks = self.drive()
        for field in ("codex_version", "provider", "model", "session_id"):
            with self.subTest(field=field):
                envelope = self.envelope(tasks[0])
                envelope["producer"][field] = ""
                with self.assertRaises(AuditError):
                    self.submit(envelope)
        for field, value in (("model_mode", "opencode"), ("model_id", "different-model")):
            envelope = self.envelope(tasks[0])
            envelope["result"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(AuditError, "metadata disagrees"):
                self.submit(envelope)

    def test_codex_fabricated_or_cross_segment_quotes_are_rejected(self):
        _, tasks = self.drive()
        original = self.envelope(tasks[0])
        for field, value in (("quote", "This claim never appeared."), ("segment_id", "other-snapshot:s1")):
            envelope = copy.deepcopy(original)
            envelope["result"]["issues"][0]["facts"][0]["evidence"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ModelError):
                self.submit(envelope)
        self.assertEqual(self.store.records(self.run_id, "model_results"), [])

    def test_codex_stale_snapshot_response_is_rejected(self):
        _, tasks = self.drive()
        old = self.envelope(tasks[0])
        self.store.ingest_evidence(self.run_id, {**self.package, "text": "Synthetic revised source, event still unverified."})
        with self.assertRaises(AuditError):
            self.submit(old)

    def test_executor_switch_excludes_old_requests_and_rejects_old_responses(self):
        _, tasks = self.drive()
        old = self.envelope(tasks[0])
        execute(self.store, self.run_id, OpenCodeJudge(self.store, self.run_id),
                mode="opencode", model_id="opencode-managed")
        self.assertEqual(len(export_model_tasks(self.store, self.run_id)["tasks"]), 1)
        self.assertEqual(export_model_tasks(self.store, self.run_id, executor="codex")["tasks"], [])
        with self.assertRaises(AuditError):
            self.submit(old)

    def test_codex_catalog_review_dependency_uses_codex_judgments(self):
        _, tasks = self.drive()
        self.submit(self.envelope(tasks[0]))
        _, tasks = self.drive()
        self.submit(self.envelope(tasks[0]))
        _, tasks = self.drive()
        self.assertEqual([task["kind"] for task in tasks], ["catalog"])
        old = self.envelope(tasks[0])
        judgment = report_data(self.store, self.run_id)["judgments"][0]
        self.store.event(self.run_id, "review", {"judgment_id": judgment["judgment_id"], "verdict": "REJECT",
                                               "reason": "Synthetic review dependency", "reviewer": "offline-fixture"})
        with self.assertRaisesRegex(AuditError, "dependencies are stale"):
            self.submit(old)

    def test_legacy_opencode_request_without_executor_keeps_default_semantics(self):
        execute(self.store, self.run_id, OpenCodeJudge(self.store, self.run_id),
                mode="opencode", model_id="opencode-managed")
        task = export_model_tasks(self.store, self.run_id)["tasks"][0]
        legacy = finalize_model_task({key: value for key, value in task.items()
                                      if key not in {"executor", "task_id", "request_hash", "input_budget"}})
        self.store.put(self.run_id, "model_tasks", legacy["task_id"], legacy)
        envelope = self.envelope(legacy)
        envelope["producer"] = {"executor": "opencode", "opencode_version": "unreported",
                                "provider": "synthetic-protocol-test", "model": "synthetic-opencode-result",
                                "session_id": "offline-legacy-protocol"}
        self.assertEqual(submit_model_results(self.store, self.run_id, [envelope])["accepted"], 1)
        saved = self.store.get(self.run_id, "model_results", legacy["task_id"])
        self.assertEqual(saved["result"]["model_mode"], "opencode")
        self.assertNotIn(legacy["task_id"], {task["task_id"] for task in export_model_tasks(self.store, self.run_id)["tasks"]})


if __name__ == "__main__":
    unittest.main()
