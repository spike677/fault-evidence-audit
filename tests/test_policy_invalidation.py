"""Upgrade/read-time invalidation uses synthetic records, retaining all history."""
import copy
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import test_bridge as bridge_tests
from faultaudit import prompts
from faultaudit.bridge import export_model_tasks, submit_model_results
from faultaudit.exporters import export_report
from faultaudit.pipeline import current_judgments, current_mappings, evidence_index, report_data, validate
from faultaudit.store import AuditError


class PolicyInvalidationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = bridge_tests.BridgeTests(methodName="runTest")
        self.fixture.setUp()
        self.store, self.run_id = self.fixture.store, self.fixture.run_id

    def tearDown(self):
        self.fixture.tearDown()

    def finish(self):
        for kind in ("summarize", "compare", "catalog"):
            _, tasks = self.fixture.drive()
            self.assertEqual([t["kind"] for t in tasks], [kind])
            submit_model_results(self.store, self.run_id, [self.fixture.envelope(tasks[0])])
        self.fixture.drive()

    def test_upgrade_read_paths_exclude_old_results_and_preserve_history(self):
        self.finish()
        old = current_judgments(self.store, self.run_id)[0]
        self.store.event(self.run_id, "review", {"judgment_id": old["judgment_id"], "verdict": "ACCEPT",
                                               "reviewer": "synthetic", "reason": "fixture only"})
        saved_responses = copy.deepcopy(self.store.records(self.run_id, "model_results"))
        for change in (patch.object(prompts, "PROMPT_VERSION", "synthetic-new-policy"),
                       patch.dict(os.environ, {"FAULTAUDIT_MAX_INPUT_CHARS": "47000"})):
            with self.subTest(change=change), change:
                self.assertEqual(current_judgments(self.store, self.run_id), [])
                self.assertEqual(current_mappings(self.store, self.run_id), [])
                self.assertEqual(validate(self.store, self.run_id)["counts"]["judged_associations"], 0)
                self.assertEqual(evidence_index(self.store, self.run_id)["evidence_index"][0]["associations"][0]["judgments"], [])
                data = report_data(self.store, self.run_id)
                self.assertTrue(all(item["is_stale"] for key in ("summaries", "judgments", "mappings") for item in data[key]))
                self.assertEqual(data["judgments"][0]["review_status"], "ACCEPT", "Historical review remains visible")
                output = export_report(data, self.fixture.directory / "policy-export")
                workbook = json.loads(Path(output["workbook_data"]).read_text(encoding="utf-8"))
                sheet = workbook["sheets"][0]
                row = dict(zip(sheet["columns"], sheet["rows"][0]))
                self.assertEqual(row["库覆盖（98条）"], "待核验")
                self.assertEqual(row["证据强度"], "待核验")
        self.assertEqual(saved_responses, self.store.records(self.run_id, "model_results"))
        self.assertEqual(len(self.store.events(self.run_id, "review")), 1)

    def test_old_request_rejected_after_rule_prompt_or_budget_change(self):
        _, tasks = self.fixture.drive()
        response = self.fixture.envelope(tasks[0])
        import faultaudit.pipeline as pipeline
        changes = (patch.object(prompts, "PROMPT_VERSION", "synthetic-next"),
                   patch.object(pipeline, "RULE_VERSION", "synthetic-next"),
                   patch.dict(os.environ, {"FAULTAUDIT_MAX_INPUT_CHARS": "47000"}))
        for change in changes:
            with self.subTest(change=change), change:
                with self.assertRaises(AuditError):
                    submit_model_results(self.store, self.run_id, [response])
                self.assertEqual(export_model_tasks(self.store, self.run_id)["tasks"], [])
        self.assertEqual(self.store.records(self.run_id, "model_results"), [])

    def test_legacy_missing_policy_is_history_and_accept_does_not_move(self):
        self.finish()
        old = current_judgments(self.store, self.run_id)[0]
        self.store.event(self.run_id, "review", {"judgment_id": old["judgment_id"], "verdict": "ACCEPT"})
        legacy = self.store.get(self.run_id, "judgments", old["judgment_id"])
        legacy.pop("policy_hash")
        self.store.put(self.run_id, "judgments", old["judgment_id"], legacy, mutable=True)
        self.assertEqual(current_judgments(self.store, self.run_id), [])
        self.assertTrue(report_data(self.store, self.run_id)["judgments"][0]["is_stale"])
        # A new strategy must issue new tasks in the same run, with no inherited review.
        with patch.object(prompts, "PROMPT_VERSION", "synthetic-upgrade"):
            self.finish()
            new = current_judgments(self.store, self.run_id)[0]
            self.assertNotEqual(new["judgment_id"], old["judgment_id"])
            self.assertEqual(new["review_status"], "NEEDS_REVIEW")
            self.assertEqual(len(self.store.records(self.run_id, "judgments")), 2)

    def test_input_change_immediately_invalidates_judgments_and_mappings(self):
        self.finish()
        self.assertTrue(current_mappings(self.store, self.run_id))
        self.store.ingest_evidence(self.run_id, {**self.fixture.package, "text": "A changed synthetic occurrence."})
        self.assertEqual(current_judgments(self.store, self.run_id), [])
        self.assertEqual(current_mappings(self.store, self.run_id), [])
        data = report_data(self.store, self.run_id)
        self.assertTrue(all(item["is_stale"] for key in ("summaries", "judgments", "mappings") for item in data[key]))
        self.assertEqual(len(data["snapshots"]), 2)
        self.assertEqual(len(data["model_results"]), 3)

    def test_altered_snapshot_file_is_not_current_even_without_execute(self):
        self.finish()
        Path(self.fixture.snapshot["text_path"]).write_text("synthetic tampering", encoding="utf-8")
        self.assertEqual(current_judgments(self.store, self.run_id), [])
        self.assertEqual(current_mappings(self.store, self.run_id), [])
        self.assertFalse(validate(self.store, self.run_id)["valid"])
        self.assertTrue(report_data(self.store, self.run_id)["judgments"][0]["is_stale"])

    def test_full_document_observation_survives_validate_with_its_saved_input_scope(self):
        tasks = self.fixture.summary_done()
        returned = self.fixture.envelope(tasks[0])
        returned["result"]["observation_scope"] = "FULL_DOCUMENT"
        submit_model_results(self.store, self.run_id, [returned])
        self.fixture.drive()
        status = validate(self.store, self.run_id)
        self.assertTrue(status["valid"], status["errors"])
        self.assertEqual(current_judgments(self.store, self.run_id)[0]["observation_scope"], "FULL_DOCUMENT")
