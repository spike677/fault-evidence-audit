"""Captured navigation descendants must reach summary without confirming a fault."""
import unittest
from unittest.mock import patch

from faultaudit.evidence_plan import build_evidence_plan
from faultaudit.store import AuditError
from faultaudit import xlsx_workflow
from tests import test_collection_source_policy as fixtures


class NavigationCandidateTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.CollectionSourcePolicyTests()
        self.fx.setUp()
        self.fx.override()
        self.store, self.run, self.case = self.fx.store, self.fx.run, self.fx.case
        self.index_url = "https://gitcode.com/example.invalid/kernel/issues"
        self.child_url = self.index_url + "/17"

    def tearDown(self):
        self.fx.tearDown()

    def capture(self, url, *, parent=None, kind="BODY", status="PARTIAL"):
        text = ("SyntheticFoo在维长65时尾块地址步长错误。" if kind == "BODY"
                else "Synthetic navigation: " + self.child_url)
        return self.store.ingest_evidence(self.run, {"url": url, "text": text, "title": "Synthetic resource",
            "status": status, "components": {"body": "PARTIAL"}, "is_synthetic": True,
            "case_ids": [self.case["case_id"]], "record_discovery": True,
            "origin": "LINK_DISCOVERED" if parent else "SEARCH_DISCOVERED",
            "discovered_from_url": parent, "discovery_query": "synthetic navigation test",
            "capture_observation": {"page_kind": kind, "requested_url": url, "final_url": url,
                "title": "Synthetic resource", "body_locator": "synthetic article" if kind == "BODY" else "",
                "body_quotes": [text] if kind == "BODY" else [], "observed_by": "synthetic-test",
                "observed_at": "2026-11-06T12:00:00+00:00", "tool_observation": "Synthetic fixture, no website"}})

    def row(self):
        return build_evidence_plan(self.store, self.run)["cases"][0]

    def test_readable_child_is_selected_instead_of_search_index(self):
        index = self.capture(self.index_url, kind="INDEX")
        body = self.capture(self.child_url, parent=self.index_url)
        row = self.row()
        self.assertEqual(row["selected_snapshot_ids"], [body["snapshot_id"]])
        self.assertFalse(row["search_control"]["satisfied"])
        self.assertEqual(row["search_control"]["usable_evidence_count"], 0)
        self.assertTrue(any(a["action"] == "NAVIGATION_CAPTURED" and a["snapshot_id"] == index["snapshot_id"]
                            for a in row["optional_actions"]))
        self.assertEqual(len(self.store.records(self.run, "references")), 4)

    def test_body_descendant_is_prioritized_at_its_index_queue_position(self):
        self.capture(self.index_url, kind="INDEX")
        self.capture("https://gitcode.com/example.invalid/other/issues/9")
        body = self.capture(self.child_url, parent=self.index_url)
        self.assertEqual(self.row()["selected_snapshot_ids"], [body["snapshot_id"]])

    def test_transitive_navigation_retains_both_parents(self):
        self.capture(self.index_url, kind="INDEX")
        middle = self.index_url + "/page/2"
        self.capture(middle, parent=self.index_url, kind="INDEX")
        body = self.capture(self.child_url, parent=middle)
        row = self.row()
        self.assertEqual(row["selected_snapshot_ids"], [body["snapshot_id"]])
        self.assertEqual(sum(a["action"] == "NAVIGATION_CAPTURED" for a in row["optional_actions"]), 2)

    def test_authentication_failure_is_not_replaced_by_a_later_body(self):
        parent = self.capture(self.index_url, kind="LOGIN", status="AUTH_REQUIRED")
        self.capture(self.child_url, parent=self.index_url)
        self.assertEqual(self.row()["selected_snapshot_ids"], [parent["snapshot_id"]])

    def test_completed_weak_body_does_not_resurrect_parent_index(self):
        self.capture(self.index_url, kind="INDEX")
        body = self.capture(self.child_url, parent=self.index_url)
        with patch("faultaudit.trigger_workflow.source_relations", return_value={
                (self.case["case_id"], body["snapshot_id"]): "PARTIAL"}):
            row = self.row()
        self.assertEqual(row["selected_snapshot_ids"], [])
        self.assertTrue(row["search_control"]["search_allowed"])

    def test_actual_workflow_emits_summary_for_captured_child(self):
        self.capture(self.index_url, kind="INDEX")
        body = self.capture(self.child_url, parent=self.index_url)
        step = xlsx_workflow.next_tasks(self.store, self.run)
        inner = [self.store.get(self.run, "workflow_requests", t["task_id"])["payload"].get("task", {})
                 for t in step["tasks"] if t["kind"] == "model"]
        self.assertTrue(any(t["kind"] == "summarize" and t["payload"]["snapshot"]["snapshot_id"] == body["snapshot_id"]
                            for t in inner))
        self.assertFalse(any(t["kind"] == "fetch" for t in step["tasks"]))


if __name__ == "__main__":
    unittest.main()
