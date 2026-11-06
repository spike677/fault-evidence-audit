"""Whole-request budget regressions, using only synthetic local evidence."""
from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from faultaudit import model, pipeline, prompts
from faultaudit.bridge import OpenCodeJudge, export_model_tasks, policy_fingerprint, submit_model_results
from faultaudit.contracts import CatalogItem, EvidenceSummary, SourceCase
from faultaudit.input_budget import (BUDGET_ENV, InputTooLarge, budget_policy, check_input_budget,
                                     get_budget_chars, serialized_chars)
from faultaudit.model import ModelError, PendingModelResult
from faultaudit.pipeline import execute
from faultaudit.store import AuditError, Store, canonical_json, digest


class BudgetMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()

    def test_default_and_explicit_budget(self):
        self.assertEqual(get_budget_chars(), model.MAX_INPUT_CHARS)
        with patch.object(model, "MAX_INPUT_CHARS", 49001):
            self.assertEqual(get_budget_chars(), 49001)
        with patch.dict(os.environ, {BUDGET_ENV: " 52000 "}):
            self.assertEqual(get_budget_chars(), 52000)
            self.assertEqual(budget_policy()["budget"], 52000)

    def test_invalid_budget_is_configuration_error(self):
        for value in ("0", "-1", "", "abc", "1.5"):
            with self.subTest(value=value), patch.dict(os.environ, {BUDGET_ENV: value}):
                with self.assertRaises(ModelError) as raised:
                    get_budget_chars()
                self.assertEqual(raised.exception.code, "INVALID_INPUT_BUDGET")

    def test_count_is_serialized_characters_and_exact_limit_is_allowed(self):
        request = {"instructions": "不要截取", "payload": {"text": "带引号\"和换行\n"}}
        count = len(canonical_json(request))
        self.assertEqual(serialized_chars(request), count)
        self.assertNotEqual(count, len(canonical_json(request).encode("utf-8")))
        self.assertEqual(check_input_budget(request, budget=count)["chars"], count)
        with self.assertRaises(InputTooLarge) as raised:
            check_input_budget(request, budget=count - 1)
        self.assertEqual(raised.exception.code, "INPUT_TOO_LARGE")
        self.assertEqual(raised.exception.details["scope"], "WHOLE_MODEL_TASK")

    def test_budget_and_runtime_rules_are_in_policy_identity(self):
        original = policy_fingerprint()
        with patch.dict(os.environ, {BUDGET_ENV: "49000"}):
            self.assertNotEqual(original, policy_fingerprint())
        with patch.object(model, "MAX_INPUT_CHARS", model.MAX_INPUT_CHARS + 1):
            self.assertNotEqual(original, policy_fingerprint())
        with patch.object(prompts, "PROMPT_VERSION", prompts.PROMPT_VERSION + "-changed"):
            self.assertNotEqual(original, policy_fingerprint())
        with patch.object(pipeline, "RULE_VERSION", pipeline.RULE_VERSION + "-changed"):
            self.assertNotEqual(original, policy_fingerprint())
        self.assertEqual(original, policy_fingerprint())


class BridgeBudgetTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.test_root = Path(__file__).resolve().parent
        self.temp = tempfile.TemporaryDirectory(prefix="budget-", dir=self.test_root)
        self.directory = Path(self.temp.name).resolve()
        self.store = Store(self.directory / "state")
        self.run_id = self.store.create_run({"is_synthetic": True})
        self.case = SourceCase(case_id="synthetic-case", source_file="synthetic.json", source_sha256="synthetic-hash",
            sheet="JSON", row=1, source_kind="ORIGINAL_WEEKLY", raw={"问题描述": "合成异常"},
            description="合成异常", cell_locations={"问题描述": "A1"}, root_cause_origin="SOURCE_RAW").model_dump()
        self.store.put(self.run_id, "cases", self.case["case_id"], self.case)
        self.snapshot = self.add_snapshot("Synthetic observed failure.")

    def tearDown(self):
        self.store.close()
        self.assertTrue(self.directory.is_relative_to(self.test_root))
        self.temp.cleanup()
        self.environment.stop()

    def add_snapshot(self, text):
        return self.store.ingest_evidence(self.run_id, {"url": "https://example.invalid/evidence",
            "title": "Synthetic evidence", "text": text, "status": "COMPLETE", "components": {"body": "COMPLETE"},
            "is_synthetic": True, "case_ids": [self.case["case_id"]]})

    def judge_context(self, kind="summarize"):
        task = self.store.task(self.run_id, kind, f"synthetic-{kind}", {"kind": kind})
        self.store.task_status(self.run_id, task["task_id"], "RUNNING")
        judge = OpenCodeJudge(self.store, self.run_id)
        judge.pipeline_task_id = task["task_id"]
        return judge, task

    def drive(self):
        status = execute(self.store, self.run_id, OpenCodeJudge(self.store, self.run_id),
                         mode="opencode", model_id="opencode-managed")
        return status, export_model_tasks(self.store, self.run_id)["tasks"]

    def envelope(self, task):
        snapshot = task["payload"]["snapshot"]
        facts = [{"field": "raw_observation", "value": segment["text"], "evidence": [
            {"segment_id": segment["segment_id"], "quote": segment["text"]}]} for segment in snapshot["segments"]]
        return {"schema_version": "1.0", "run_id": self.run_id, "task_id": task["task_id"],
            "request_hash": task["request_hash"], "result": {"snapshot_id": snapshot["snapshot_id"],
                "issues": [{"label": "Synthetic observations", "facts": facts}], "unknown_fields": ["event"]},
            "producer": {"executor": "opencode", "opencode_version": "test", "provider": "synthetic",
                         "model": "synthetic-model", "session_id": "offline-budget-test"}}

    def comparison_envelope(self, task, *, observation_scope="FULL_DOCUMENT"):
        from tests.fact_fixtures import with_fact_audit
        envelope = self.envelope(task)
        envelope["result"] = {"case_id": self.case["case_id"],
            "snapshot_id": task["payload"]["snapshot"]["snapshot_id"],
            "case_attribution": "UNKNOWN", "event_relation": "UNDETERMINED", "pattern_relation": "UNDETERMINED",
            "support_level": "PENDING", "claim_support": {field: "UNKNOWN" for field in
                ("symptom", "root_cause", "fix", "verification")}, "matched_dimensions": [],
            "conflicting_dimensions": [], "unknown_dimensions": ["event"], "evidence": [],
            "short_reason": "Synthetic scope validation", "observation_scope": observation_scope}
        envelope["result"] = with_fact_audit(envelope["result"], task)
        return envelope

    def add_catalog(self, width=20):
        items = [CatalogItem(item_id=f"F-{i:03d}", description="Synthetic " + "x" * width,
            mechanism="example-mechanism", trigger="example-trigger", source_file="synthetic-catalog.json",
            source_sha256="catalog-hash", source_location=f"JSON:{i + 1}").model_dump() for i in range(98)]
        for item in items:
            self.store.put(self.run_id, "catalog", item["item_id"], item)
        return items

    def test_all_three_operations_count_instructions_plus_data_and_preserve_inputs(self):
        for kind in ("summarize", "compare", "catalog"):
            with self.subTest(kind=kind), patch.dict(os.environ, {BUDGET_ENV: "3000"}):
                judge, _ = self.judge_context(kind)
                payload = {"data": "x" * 1600, "input_scope": {"scope": "FULL_CATALOG" if kind == "catalog" else "SELECTED_SEGMENTS"}}
                original = copy.deepcopy(payload)
                with self.assertRaises(InputTooLarge) as raised:
                    judge._request(kind, payload, "instruction" * 160, "SyntheticContract")
                self.assertGreater(raised.exception.chars, raised.exception.budget)
                self.assertEqual(raised.exception.details["kind"], kind)
                self.assertEqual(raised.exception.details["input_scope"], payload["input_scope"])
                self.assertEqual(payload, original)
        self.assertEqual(self.store.records(self.run_id, "model_tasks"), [])

    def test_export_records_exact_whole_request_size_and_scope(self):
        judge, _ = self.judge_context()
        with self.assertRaises(PendingModelResult):
            judge.summarize(self.snapshot)
        exported = export_model_tasks(self.store, self.run_id)["tasks"]
        self.assertEqual(len(exported), 1)
        task = exported[0]
        self.assertEqual(task["input_budget"]["chars"], len(canonical_json(task)))
        self.assertEqual(task["input_budget"]["budget"], 48000)
        self.assertEqual(task["input_budget"]["scope"], "WHOLE_MODEL_TASK")
        self.assertNotIn("text", task["payload"]["snapshot"])
        self.assertEqual("".join(s["text"] for s in task["payload"]["snapshot"]["segments"]), self.snapshot["text"])
        self.assertIn("input_scope", task["payload"]["snapshot"])

    def test_98_item_catalog_is_preserved_and_missing_or_duplicate_sets_cannot_export(self):
        items = self.add_catalog()
        judge, _ = self.judge_context("catalog")
        with self.assertRaises(PendingModelResult):
            judge.map_catalog(self.case, [], items)
        ready = export_model_tasks(self.store, self.run_id)["tasks"]
        self.assertEqual(len(ready), 1)
        self.assertEqual(len(ready[0]["payload"]["items"]), 98)
        self.assertEqual(len(set(ready[0]["payload"]["input_scope"]["provided_item_ids"])), 98)
        for altered in (items[:-1], items[:-1] + [items[0]]):
            with self.subTest(count=len(altered)), self.assertRaises(PendingModelResult):
                judge.map_catalog(self.case, [], altered)
        # Altered requests may remain for auditing but cannot be exported as valid work.
        exported = export_model_tasks(self.store, self.run_id)
        self.assertEqual(len(exported["tasks"]), 1)
        self.assertEqual(len(exported["stale_tasks_excluded"]), 2)

    def test_oversized_catalog_fails_without_removing_any_of_98_items(self):
        items = self.add_catalog(width=900)
        judge, _ = self.judge_context("catalog")
        with self.assertRaises(InputTooLarge) as raised:
            judge.map_catalog(self.case, [], items)
        self.assertEqual(raised.exception.details["input_scope"]["catalog_item_count"], 98)
        self.assertEqual(len(self.store.records(self.run_id, "catalog")), 98)
        self.assertEqual(self.store.records(self.run_id, "model_tasks"), [])

    def test_budget_change_invalidates_old_request_without_execute(self):
        judge, _ = self.judge_context()
        with self.assertRaises(PendingModelResult):
            judge.summarize(self.snapshot)
        task = export_model_tasks(self.store, self.run_id)["tasks"][0]
        with patch.dict(os.environ, {BUDGET_ENV: "49000"}):
            self.assertEqual(export_model_tasks(self.store, self.run_id)["tasks"], [])
            with self.assertRaises(AuditError):
                submit_model_results(self.store, self.run_id, [self.envelope(task)])

    def test_blocked_pipeline_task_cannot_accept_a_returned_result(self):
        judge, parent = self.judge_context()
        with self.assertRaises(PendingModelResult):
            judge.summarize(self.snapshot)
        task = export_model_tasks(self.store, self.run_id)["tasks"][0]
        self.store.task_status(self.run_id, parent["task_id"], "BLOCKED", "INPUT_TOO_LARGE")
        self.assertEqual(export_model_tasks(self.store, self.run_id)["tasks"], [])
        with self.assertRaises(AuditError):
            submit_model_results(self.store, self.run_id, [self.envelope(task)])

    def test_rehashed_inaccurate_budget_metadata_is_rejected(self):
        judge, _ = self.judge_context()
        with self.assertRaises(PendingModelResult):
            judge.summarize(self.snapshot)
        task = copy.deepcopy(export_model_tasks(self.store, self.run_id)["tasks"][0])
        unsigned = {key: value for key, value in task.items() if key not in {"task_id", "request_hash"}}
        unsigned["input_budget"]["chars"] += 1
        unsigned["task_id"] = "llm-" + digest(unsigned)[:24]
        unsigned["request_hash"] = digest(unsigned)
        self.store.put(self.run_id, "model_tasks", unsigned["task_id"], unsigned)
        with self.assertRaisesRegex(AuditError, "budget metadata"):
            submit_model_results(self.store, self.run_id, [self.envelope(unsigned)])

    def test_full_document_result_accepts_complete_whole_view_scope(self):
        _, tasks = self.drive()
        submit_model_results(self.store, self.run_id, [self.envelope(tasks[0])])
        _, tasks = self.drive()
        self.assertEqual([task["kind"] for task in tasks], ["compare"])
        self.assertEqual(tasks[0]["payload"]["input_scope"]["scope"], "FULL_CAPTURED_SNAPSHOT")
        accepted = submit_model_results(self.store, self.run_id, [self.comparison_envelope(tasks[0])])
        self.assertEqual(accepted["accepted"], 1)

    def test_full_document_result_rejects_selected_segment_scope(self):
        snapshot = self.add_snapshot("x" * 7000)
        _, tasks = self.drive()
        submit_model_results(self.store, self.run_id, [self.envelope(tasks[0])])
        self.drive()
        summary = pipeline.current_summaries(self.store, self.run_id)[0]
        selected = snapshot["segments"][:1]
        view = {**snapshot, "text": "".join(segment["text"] for segment in selected), "segments": selected,
                "input_scope": pipeline.input_scope(snapshot, selected)}
        judge, _ = self.judge_context("compare")
        with self.assertRaises(PendingModelResult):
            judge.compare(self.case, view, {key: summary[key] for key in EvidenceSummary.model_fields})
        task = next(task for task in export_model_tasks(self.store, self.run_id)["tasks"]
                    if task["kind"] == "compare" and task["payload"]["input_scope"]["scope"] == "SELECTED_SEGMENTS")
        with self.assertRaises((AuditError, ModelError)):
            submit_model_results(self.store, self.run_id, [self.comparison_envelope(task)])

    def test_pipeline_budget_failure_is_blocked_with_structured_measurement(self):
        with patch.dict(os.environ, {BUDGET_ENV: "1000"}):
            status, tasks = self.drive()
            self.assertEqual(tasks, [])
            self.assertEqual(status["counts"]["task_states"].get("FAILED", 0), 0)
            self.assertGreater(status["counts"]["task_states"].get("BLOCKED", 0), 0)
            events = self.store.events(self.run_id, "model_input_blocked")
            self.assertTrue(events)
            self.assertGreater(events[0]["chars"], events[0]["budget"])
            self.assertEqual(events[0]["scope"], "WHOLE_MODEL_TASK")

    def test_long_snapshot_covers_tail_and_waits_for_every_summary_group(self):
        marker = "SYNTHETIC_TAIL_CONCLUSION"
        text = "x" * 62000 + marker
        snapshot = self.add_snapshot(text)
        groups = 0
        for _ in range(20):
            status, tasks = self.drive()
            summaries = self.store.records(self.run_id, "summaries")
            summary_tasks = [task for task in tasks if task["kind"] == "summarize"]
            if not summary_tasks:
                break
            self.assertEqual(summaries, [], "A final summary must not exist while a source group is missing")
            if not groups:
                self.assertGreater(len(summary_tasks), 1, "Independent groups must all be available for isolated workers")
            task = summary_tasks[0]
            self.assertLessEqual(task["input_budget"]["chars"], task["input_budget"]["budget"])
            submit_model_results(self.store, self.run_id, [self.envelope(task)])
            groups += 1
        self.assertGreater(groups, 1)
        summaries = self.store.records(self.run_id, "summaries")
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["segments_processed"], len(snapshot["segments"]))
        values = "".join(str(fact["value"]) for issue in summaries[0]["issues"] for fact in issue["facts"])
        self.assertIn(marker, values)
        compare = [task for task in self.store.tasks(self.run_id) if task["kind"] == "compare" and task["status"] != "STALE"]
        self.assertEqual(len(compare), 1)
        self.assertEqual(compare[0]["status"], "BLOCKED")
        self.assertIn("INPUT_TOO_LARGE", compare[0]["error"])


if __name__ == "__main__":
    unittest.main()
