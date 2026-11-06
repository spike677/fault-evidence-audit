"""Synthetic Wiki workflow regressions for retries and replacement candidates."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from faultaudit import xlsx_workflow as workflow
from faultaudit.contracts import Judgment
from faultaudit.evidence_plan import get_search_policy
from faultaudit.pipeline import evidence_plan, gate_judgment, task_views
from tests import test_investigation as investigation_tests
from tests import test_xlsx_workflow as workflow_tests


class WorkflowWikiRetryTests(unittest.TestCase):
    def setUp(self):
        self.fx = workflow_tests.XlsxWorkflowTests()
        self.fx.setUp()
        self.store = self.fx.store

    def tearDown(self):
        self.fx.tearDown()

    def start_without_wiki(self):
        self.fx.start([["SYN-NO-WIKI", "Synthetic output differs", "待定位", "",
                       "https://github.com/example/synthetic/pull/1", "P1"]])
        self.run = self.fx.run
        return next(task for task in workflow.next_tasks(self.store, self.run)["tasks"] if task["kind"] == "wiki_check")

    def wiki_package(self, url):
        return {"url": url, "title": "Synthetic Wiki", "text":
                "Issue A: Event EVT-OTHER belongs to OtherTenant scanning before deployment; buffer reused before completion.\n"
                "Issue B: offset calculation error.",
                "status": "CONTENT_CAPTURED", "components": {"body": "COMPLETE"}, "is_synthetic": True}

    def current_comparison(self, snapshot):
        helper = investigation_tests.InvestigationTests()
        helper.store, helper.run = self.store, self.run
        case = self.store.records(self.run, "cases")[0]
        def exact_snapshot_plan(store, run_id):
            plan = evidence_plan(store, run_id)
            return {**plan, "work_items": [work for work in plan["work_items"] if work["snapshot_id"] == snapshot["snapshot_id"]]}
        with patch.object(investigation_tests, "evidence_plan", side_effect=exact_snapshot_plan):
            _, old = helper.finish(case, snapshot)
        return case, old

    def make_other_event(self, snapshot):
        case, old = self.current_comparison(snapshot)
        value = {key: old[key] for key in Judgment.model_fields if key in old}
        quote = snapshot["text"].split("\n", 1)[0]
        ref = {"segment_id": snapshot["segments"][0]["segment_id"], "quote": quote}
        value.update(case_attribution="MISMATCH", event_relation="DIFFERENT_EVENT", support_level="NONE",
            claim_support={"root_cause": "UNKNOWN"}, short_reason="Synthetic unrelated scan, independently identified",
            negative_basis={"other_event": {"positive_identity": "EVT-OTHER", "context": quote,
                "dimensions": ["event_identity", "symptom", "occurrence_context"], "evidence": [ref]},
                "attribution_mismatch": {"positive_identity": "OtherTenant", "context": quote,
                    "dimensions": ["ownership", "symptom", "occurrence_context"], "evidence": [ref]}})
        checked = gate_judgment(case, snapshot, value, context=old["processing_context"])
        self.store.put(self.run, "judgments", old["judgment_id"], {**old, **checked}, mutable=True)
        return case

    def test_explicit_retry_redispatches_no_match_and_blocked_and_keeps_attempts(self):
        for outcome in ("NO_MATCH", "BLOCKED"):
            with self.subTest(outcome=outcome):
                first = self.start_without_wiki()
                body = self.fx.response(first)
                body["outcome"] = outcome
                if outcome == "BLOCKED":
                    body["reason"] = "Synthetic authentication required"
                workflow.submit(self.store, self.run, first["task_id"], body)
                self.assertFalse(any(t["kind"] == "wiki_check" for t in workflow.next_tasks(self.store, self.run)["tasks"]))
                workflow.retry(self.store, self.run, first["task_id"])
                dispatched = workflow.next_tasks(self.store, self.run)["tasks"]
                self.assertTrue(any(t["task_id"] == first["task_id"] for t in dispatched))
                retried = self.fx.response(first)
                retried["checked_at"] = "2026-11-06T11:00:00+08:00"
                workflow.submit(self.store, self.run, first["task_id"], retried)
                attempts = [item for item in self.store.records(self.run, "workflow_attempts") if item["task_id"] == first["task_id"]]
                self.assertEqual(len(attempts), 2)
                self.assertEqual(len({item["response"] for item in attempts}), 2)
                self.assertTrue(all(item["status"] == "ACCEPTED" for item in attempts))

    def test_case_or_original_reference_change_restores_temporary_wiki_condition(self):
        for changed in ("case", "reference"):
            with self.subTest(changed=changed):
                first = self.start_without_wiki()
                workflow.submit(self.store, self.run, first["task_id"], self.fx.response(first))
                workflow.next_tasks(self.store, self.run)
                case = self.store.records(self.run, "cases")[0]
                self.assertEqual(get_search_policy(self.store, self.run, case["case_id"])["policy"]["required_sources"], [])
                if changed == "case":
                    value = copy.deepcopy(case)
                    value["description"] += " new configuration"
                    self.store.put(self.run, "cases", case["case_id"], value, mutable=True)
                else:
                    ref = self.store.records(self.run, "references")[0]
                    ref["raw_text"] += " new source hint"
                    self.store.put(self.run, "references", ref["ref_id"], ref, mutable=True)
                step = workflow.next_tasks(self.store, self.run)
                self.assertEqual(get_search_policy(self.store, self.run, case["case_id"])["policy"]["required_sources"], ["WIKI"])
                new = next(task for task in step["tasks"] if task["kind"] == "wiki_check")
                self.assertNotEqual(new["task_id"], first["task_id"])
                self.assertTrue(self.store.records(self.run, "wiki_checks"))

    def test_excluded_found_candidate_gets_a_new_search_identity(self):
        first = self.start_without_wiki()
        body = self.fx.response(first)
        body.update(outcome="FOUND", packages=[self.wiki_package("https://example.invalid/wiki/candidate")])
        workflow.submit(self.store, self.run, first["task_id"], body)
        step = workflow.next_tasks(self.store, self.run)
        self.assertFalse(any(task["kind"] == "wiki_check" for task in step["tasks"]))
        self.store.ingest_evidence(self.run, self.fx.package("https://github.com/example/synthetic/pull/1"))
        snapshot = next(s for s in self.store.active_snapshots(self.run) if s["url"] == "https://example.invalid/wiki/candidate")
        self.make_other_event(snapshot)
        next_step = workflow.next_tasks(self.store, self.run)
        replacement = next(task for task in next_step["tasks"] if task["kind"] == "wiki_check")
        self.assertNotEqual(replacement["task_id"], first["task_id"])
        self.assertEqual(next_step["wiki_checks"][self.store.records(self.run, "cases")[0]["case_id"]]["status"], "SEARCH_REQUIRED")

    def test_bad_original_wiki_keeps_conflict_but_replacement_enters_necessary_work(self):
        self.fx.start()
        self.run = self.fx.run
        case = self.store.records(self.run, "cases")[0]
        original = self.store.ingest_evidence(self.run, self.wiki_package("https://example.invalid/wiki/shared"))
        self.make_other_event(original)
        replacement = self.store.ingest_evidence(self.run, {**self.wiki_package("https://example.invalid/wiki/replacement"),
            "case_ids": [case["case_id"]], "origin": "SEARCH_DISCOVERED", "record_discovery": True,
            "discovery_query": "Synthetic directed replacement search"})
        plan = evidence_plan(self.store, self.run)
        row = next(item for item in plan["cases"] if item["case_id"] == case["case_id"])
        self.assertEqual(row["path"], "EXCEPTION")
        self.assertTrue(any(issue["code"] == "KNOWN_CONFLICT" for issue in row["issues"]))
        self.assertIn(original["snapshot_id"], row["selected_snapshot_ids"])
        self.assertIn(replacement["snapshot_id"], row["selected_snapshot_ids"])
        self.assertTrue(any(work["snapshot_id"] == replacement["snapshot_id"] for work in plan["work_items"]))
        self.store.task(self.run, "summarize", replacement["snapshot_id"], {"synthetic_replacement_summary": True})
        self.assertTrue(any(task["kind"] == "summarize" and task["target_id"] == replacement["snapshot_id"] and task["required"]
                            for task in task_views(self.store, self.run, plan)))
        # Ordinary runs retain their original conflict routing.
        original_get = self.store.get
        def no_workflow(run_id, kind, record_id):
            return None if kind == "xlsx_workflow" and record_id == "config" else original_get(run_id, kind, record_id)
        with patch.object(self.store, "get", side_effect=no_workflow):
            ordinary = evidence_plan(self.store, self.run)
        self.assertNotIn(replacement["snapshot_id"], ordinary["cases"][0]["selected_snapshot_ids"])
        self.assertEqual(self.store.events(self.run, "review"), [])

    def test_provided_pr_access_failure_does_not_prevent_wiki_candidate_verification(self):
        first = self.start_without_wiki()
        self.store.ingest_evidence(self.run, {"url": "https://github.com/example/synthetic/pull/1", "text": "",
            "status": "AUTH_REQUIRED", "components": {"body": "AUTH_REQUIRED"}, "is_synthetic": True})
        body = self.fx.response(first)
        body.update(outcome="FOUND", packages=[self.wiki_package("https://example.invalid/wiki/candidate")])
        workflow.submit(self.store, self.run, first["task_id"], body)
        plan = evidence_plan(self.store, self.run)
        wiki = next(s for s in self.store.active_snapshots(self.run) if s["url"] == "https://example.invalid/wiki/candidate")
        self.assertTrue(any(work["snapshot_id"] == wiki["snapshot_id"] for work in plan["work_items"]))
        self.assertTrue(any(item["url"] == "https://github.com/example/synthetic/pull/1" and item["retrieval_status"] == "AUTH_REQUIRED"
                            for item in plan["fetch_work_items"]))

    def test_generic_search_continues_after_found_candidate_is_excluded_or_insufficient(self):
        for classification in ("excluded", "insufficient"):
            with self.subTest(classification=classification):
                self.fx.start([["SYN-NO-LINK", "Synthetic output differs", "待定位", "", "", "P1"]])
                self.run = self.fx.run
                wiki = next(task for task in workflow.next_tasks(self.store, self.run)["tasks"] if task["kind"] == "wiki_check")
                workflow.submit(self.store, self.run, wiki["task_id"], self.fx.response(wiki))
                first = next(task for task in workflow.next_tasks(self.store, self.run)["tasks"] if task["kind"] == "search")
                body = self.fx.response(first)
                url = "https://github.com/example/synthetic/issues/2"
                body.update(outcome="FOUND", packages=[self.wiki_package(url)])
                workflow.submit(self.store, self.run, first["task_id"], body)
                snapshot = next(s for s in self.store.active_snapshots(self.run) if s["url"] == url)
                if classification == "excluded":
                    self.make_other_event(snapshot)
                else:
                    self.current_comparison(snapshot)
                step = workflow.next_tasks(self.store, self.run)
                second = next(task for task in step["tasks"] if task["kind"] == "search")
                self.assertNotEqual(second["task_id"], first["task_id"])
                # A bounded search with NO_MATCH remains cached; this new work
                # exists because a concrete candidate comparison changed.
                workflow.submit(self.store, self.run, second["task_id"], self.fx.response(second))
                self.assertFalse(any(task["kind"] == "search" for task in workflow.next_tasks(self.store, self.run)["tasks"]))


if __name__ == "__main__":
    unittest.main()
