"""Synthetic, scoped reassessment with immutable evidence and model history."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from faultaudit import trigger_workflow as workflow, xlsx_workflow
from faultaudit.store import AuditError, digest
from faultaudit.trigger_maintenance import request_reassessment
from tests import test_trigger_workflow as helpers


class TriggerMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.helper = helpers.TriggerWorkflowTests("runTest")
        self.helper.setUp()
        self.helper.start(2)
        self.store, self.run = self.helper.store, self.helper.run
        self.old_payloads = list(workflow.classification_payloads(self.store, self.run))
        self.old_results = [self.helper.accept(p, definition_only=True) for p in self.old_payloads]
        self.subject = self.old_payloads[0]["subject"]["subject_id"]

    def tearDown(self):
        self.helper.tearDown()

    def request(self, **overrides):
        return request_reassessment(self.store, self.run, self.subject,
            **{"reason": "Source does not establish an entry contract", "requested_by": "synthetic-agent", **overrides})

    def test_only_target_expires_without_changing_sources_history_or_policy(self):
        sources = copy.deepcopy(self.store.records(self.run, "cases"))
        old_subject = self.store.get(self.run, "trigger_subjects", self.subject)
        policy = xlsx_workflow._policy()
        result = self.request()
        self.assertEqual(result["revision"], 1)
        current = workflow.current_assessments(self.store, self.run)
        self.assertEqual([a["assessment_id"] for a in current], [self.old_results[1]["assessment_id"]])
        self.assertEqual(self.store.records(self.run, "cases"), sources)
        self.assertEqual(len(self.store.records(self.run, "trigger_assessments")), 2)
        self.assertEqual(xlsx_workflow._policy(), policy)
        event = self.store.events(self.run, "trigger_reassessment_requested")[0]
        self.assertEqual(event["previous_subject"], old_subject)
        self.assertFalse(event["reassessment"]["source_evidence"])
        self.assertEqual(self.store.events(self.run, "review"), [])
        self.assertEqual(self.store.get(self.run, "trigger_assessments", self.old_results[0]["assessment_id"]), self.old_results[0])

    def test_pending_request_is_idempotent_and_later_review_gets_fresh_input(self):
        first = self.request()
        payload = next(workflow.classification_payloads(self.store, self.run))
        second = self.request()
        self.assertTrue(second["idempotent"])
        self.assertEqual(len(self.store.events(self.run, "trigger_reassessment_requested")), 1)
        self.assertEqual(payload, next(workflow.classification_payloads(self.store, self.run)))
        self.helper.accept(payload, definition_only=True)
        third = self.request()
        self.assertFalse(third["idempotent"])
        self.assertEqual(third["revision"], first["revision"] + 1)
        self.assertNotEqual(payload["basis_hash"], next(workflow.classification_payloads(self.store, self.run))["basis_hash"])
        self.assertEqual(len(self.store.records(self.run, "trigger_assessments")), 3)

    def test_old_request_and_frozen_baseline_become_stale(self):
        baseline = workflow.finalize(self.store, self.run, allow_pending=True)
        old_request = self.helper.request(self.old_payloads[0])
        old_response = self.helper.response(old_request, definition_only=True)
        self.request()
        with self.assertRaisesRegex(AuditError, "input/baseline changed"):
            workflow.accept_assessment(self.store, self.run, old_request, old_response)
        with self.assertRaisesRegex(AuditError, "baseline is stale"):
            workflow._baseline(self.store, self.run, baseline["baseline_id"], allow_pending=True)
        self.assertEqual(self.store.get(self.run, "trigger_baselines", baseline["baseline_id"]), baseline)
        self.assertNotEqual(old_request["task_id"], self.helper.request(next(workflow.classification_payloads(self.store, self.run)))["task_id"])

    def test_invalid_requests_do_not_mutate_any_subject(self):
        before = copy.deepcopy(self.store.records(self.run, "trigger_subjects"))
        for override in ({"reason": " "}, {"requested_by": " "}):
            with self.assertRaises(AuditError): self.request(**override)
        with self.assertRaisesRegex(AuditError, "missing or outside"):
            request_reassessment(self.store, self.run, "synthetic-missing-subject", reason="review", requested_by="synthetic-agent")
        self.assertEqual(self.store.records(self.run, "trigger_subjects"), before)
        self.assertEqual(self.store.events(self.run, "trigger_reassessment_requested"), [])

    def test_cli_requests_reassessment_without_accept_or_source_rewrite(self):
        command = [sys.executable, "run_faultaudit.py", "--state", str(self.store.root),
                   "trigger-workflow", "reassess", "--run", self.run, "--subject-id", self.subject,
                   "--reason", "Synthetic bounded review", "--requested-by", "synthetic-agent"]
        result = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["subject_id"], self.subject)
        self.assertFalse(output["human_review_created"])
        self.assertEqual(len(self.store.records(self.run, "trigger_assessments")), 2)
        self.assertEqual(self.store.events(self.run, "review"), [])


if __name__ == "__main__":
    unittest.main()
