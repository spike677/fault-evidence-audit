"""Synthetic mode-entry routing; no incident judgments, live data or websites."""
from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from faultaudit.evidence_plan import build_evidence_plan, register_search_policy
from faultaudit.importers import import_cases
from faultaudit.pipeline import import_into
from faultaudit.store import AuditError, Store
from faultaudit.wiki_checks import record_wiki_check, wiki_plan


class TriggerSourceRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="trigger-routing-", dir=Path(__file__).parent)
        self.directory = Path(self.temp.name)
        self.store = Store(self.directory / "state")
        self.run = self.store.create_run({"is_synthetic": True})
        self.relations = {}
        helper = types.ModuleType("faultaudit.trigger_workflow")
        helper.source_relations = Mock(side_effect=lambda store, run_id: self.relations)
        self.helper = helper.source_relations
        self.module_patch = patch.dict(sys.modules, {"faultaudit.trigger_workflow": helper})
        self.module_patch.start()
        self.configure()

    def tearDown(self):
        self.module_patch.stop()
        self.store.close()
        self.temp.cleanup()

    def configure(self, purpose="TRIGGER_INIT"):
        self.store.put(self.run, "xlsx_workflow", "config", {
            "purpose": purpose, "capture_quality_required": False}, mutable=True)

    def source(self, **links):
        path = self.directory / "synthetic.json"
        path.write_text(json.dumps([{"统一ID": "SYN-MODE-1", "问题描述": "Synthetic dimension boundary pattern",
            "根因": "Synthetic fixed-width dimension assumption", **links}]), encoding="utf-8")
        imported = import_cases(path, source_kind="ORIGINAL_WEEKLY")
        import_into(self.store, self.run, imported)
        self.case = imported["cases"][0]
        return self.case

    def capture(self, url="https://example.invalid/wiki/one", *, discovery=True, status="COMPLETE"):
        return self.store.ingest_evidence(self.run, {"url": url, "title": "Synthetic mode source",
            "text": "Synthetic dimension boundary pattern; fixed-width dimension assumption" if status in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"} else "",
            "status": status, "components": {"body": "COMPLETE" if status == "COMPLETE" else "PARTIAL"},
            "is_synthetic": True, "case_ids": [self.case["case_id"]],
            "origin": "SEARCH_DISCOVERED" if discovery else "HUMAN_ADDED", "record_discovery": discovery})

    def assess(self, snapshot, relation):
        self.relations[(self.case["case_id"], snapshot["snapshot_id"])] = relation

    def plan(self):
        return build_evidence_plan(self.store, self.run)["cases"][0]

    def wiki(self):
        return wiki_plan(self.store, self.run, self.case)

    def found(self, snapshot):
        return record_wiki_check(self.store, self.run, self.case["case_id"], outcome="FOUND",
                                 snapshot_id=snapshot["snapshot_id"])

    def test_mode_match_routes_without_fabricating_incident_or_human_confirmation(self):
        self.source()
        snapshot = self.capture()
        self.assess(snapshot, "MATCH")
        before = self.store.conn.total_changes
        row, wiki = self.plan(), self.wiki()
        self.assertEqual(self.store.conn.total_changes, before)
        self.assertTrue(row["search_control"]["satisfied"])
        self.assertFalse(row["search_control"]["search_allowed"])
        self.assertFalse(row["user_confirmed"])
        self.assertIn("SEARCH_DISCOVERED", row["source_grades"])
        self.assertEqual(wiki["status"], "FOUND")
        self.assertFalse(wiki["case_root_cause_confirmed"])
        self.assertEqual(row["domain_source_assessments"], [{"snapshot_id": snapshot["snapshot_id"], "source_relation": "MATCH"}])
        for kind in ("judgments", "reviews", "evidence_associations", "event_groups"):
            self.assertEqual(self.store.records(self.run, kind), [])

    def test_resolved_original_identifier_preserves_discovery_origin(self):
        self.source(DTS="DTS2099010100001")
        snapshot = self.capture("https://example.invalid/ticket/DTS2099010100001")
        self.assess(snapshot, "SUPPLIED_IDENTIFIER")
        row = self.plan()
        self.assertTrue(row["search_control"]["satisfied"])
        self.assertFalse(row["user_confirmed"])
        self.assertIn("SEARCH_DISCOVERED", row["source_grades"])
        discovered = [ref for ref in self.store.records(self.run, "references") if ref.get("url") == snapshot["url"]]
        self.assertTrue(discovered)
        self.assertTrue(all(ref["origin"] == "SEARCH_DISCOVERED" for ref in discovered))
        self.assertEqual(self.store.records(self.run, "evidence_associations"), [])

    def test_weak_candidates_finish_verification_and_advance_stable_search(self):
        for relation in ("PARTIAL", "UNKNOWN"):
            with self.subTest(relation=relation):
                if not hasattr(self, "case"):
                    self.source()
                    self.snapshot = self.capture()
                    self.found(self.snapshot)
                self.relations.clear()
                before = self.wiki()
                self.assertEqual(before["status"], "CANDIDATE_PENDING")
                self.assess(self.snapshot, relation)
                after = self.wiki()
                self.assertEqual(after["status"], "SEARCH_REQUIRED")
                self.assertNotEqual(after["task_id"], before["task_id"])
                self.assertEqual(after, self.wiki())
                self.assertTrue(self.plan()["search_control"]["search_allowed"])
                self.assertEqual(self.plan()["selected_snapshot_ids"], [])
                self.assertEqual(after["insufficient_source_snapshot_ids"], [self.snapshot["snapshot_id"]])
                self.assertEqual([a["action"] for a in after["required_actions"]], ["SEARCH_WIKI"])

    def test_excluded_discovery_advances_without_negative_incident_judgment(self):
        self.source()
        snapshot = self.capture()
        self.found(snapshot)
        self.assess(snapshot, "NOT_RELATED")
        self.assertEqual(self.wiki()["status"], "SEARCH_REQUIRED")
        self.assertEqual(self.plan()["excluded_source_snapshot_ids"], [snapshot["snapshot_id"]])
        self.assertEqual(self.plan()["selected_snapshot_ids"], [])
        self.assertEqual(self.store.records(self.run, "judgments"), [])
        with self.assertRaises(AuditError):
            self.found(snapshot)

    def test_new_candidate_waits_for_assessment_after_weak_candidate(self):
        self.source()
        first = self.capture()
        self.found(first)
        self.assess(first, "PARTIAL")
        next_search = self.wiki()["task_id"]
        second = self.capture("https://example.invalid/wiki/two")
        self.found(second)
        pending = self.wiki()
        self.assertEqual(pending["status"], "CANDIDATE_PENDING")
        self.assertEqual(pending["required_actions"], [{"action": "VERIFY_WIKI", "snapshot_id": second["snapshot_id"]}])
        self.assess(second, "UNKNOWN")
        after = self.wiki()
        self.assertEqual(after["status"], "SEARCH_REQUIRED")
        self.assertNotEqual(after["task_id"], next_search)
        self.assertEqual(after, self.wiki())

    def test_no_match_after_weak_assessment_remains_terminal(self):
        self.source()
        snapshot = self.capture()
        self.found(snapshot)
        self.assess(snapshot, "UNKNOWN")
        record_wiki_check(self.store, self.run, self.case["case_id"], outcome="NO_MATCH", executed=True,
            query="Synthetic dimension boundary", scope="Synthetic Wiki space", checked_at="2026-11-06T10:00:00+08:00",
            executed_by="synthetic-agent", reason="No stronger source in this bounded search")
        plan = self.wiki()
        self.assertEqual(plan["status"], "NO_MATCH")
        self.assertTrue(plan["checked"])
        self.assertFalse(plan["search_allowed"])
        self.assertEqual(plan, self.wiki())

    def test_all_supplied_links_remain_organized_but_excluded_wiki_does_not_satisfy_goal(self):
        self.source(wiki="https://example.invalid/wiki/one", DTS="https://example.invalid/ticket/one",
                    PR="https://github.com/example.invalid/example/pull/1")
        snapshots = [self.capture(url, discovery=False, status="CONTENT_CAPTURED") for url in (
            "https://example.invalid/wiki/one", "https://example.invalid/ticket/one",
            "https://github.com/example.invalid/example/pull/1")]
        self.assess(snapshots[0], "NOT_RELATED")
        register_search_policy(self.store, self.run, {"required_sources": ["WIKI"]})
        result = build_evidence_plan(self.store, self.run)
        row = result["cases"][0]
        self.assertEqual(set(row["selected_snapshot_ids"]), {snapshot["snapshot_id"] for snapshot in snapshots})
        self.assertEqual(len(result["work_items"]), 3)
        self.assertTrue(row["search_control"]["search_allowed"])
        self.assertEqual(self.wiki()["status"], "SEARCH_REQUIRED")

    def test_domain_routing_is_never_used_for_normal_or_incremental_runs(self):
        self.source()
        snapshot = self.capture()
        self.assess(snapshot, "MATCH")
        for purpose in ("INCIDENT_AUDIT", "TRIGGER_INCREMENTAL"):
            with self.subTest(purpose=purpose):
                self.configure(purpose)
                self.helper.reset_mock()
                self.assertEqual(self.wiki()["status"], "CANDIDATE_PENDING")
                self.assertFalse(self.plan()["search_control"]["satisfied"])
                self.assertEqual(self.plan()["domain_source_assessments"], [])
                self.helper.assert_not_called()

    def test_unassessed_or_unreadable_source_cannot_inherit_match_usability(self):
        self.source()
        snapshot = self.capture()
        self.assess(snapshot, "MATCH")
        self.assertEqual(self.wiki()["status"], "FOUND")
        self.relations.clear()
        self.assertEqual(self.wiki()["status"], "CANDIDATE_PENDING")
        blocked = self.capture("https://example.invalid/wiki/blocked", status="AUTH_REQUIRED")
        self.assess(blocked, "MATCH")
        self.assertFalse(self.plan()["search_control"]["satisfied"])


if __name__ == "__main__":
    unittest.main()
