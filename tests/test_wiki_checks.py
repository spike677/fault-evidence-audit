"""Synthetic Wiki-first workflow checks; no live site or model calls."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from faultaudit.evidence_plan import register_event_group, register_evidence_association
from faultaudit.importers import import_cases
from faultaudit.pipeline import import_into
from faultaudit.store import AuditError, Store
from faultaudit.wiki_checks import record_wiki_check, wiki_plan


class WikiCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wiki-checks-", dir=Path(__file__).parent)
        self.directory = Path(self.temp.name)
        self.store = Store(self.directory / "state")
        self.run = self.store.create_run({"is_synthetic": True})

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def source(self, wiki=True, rows=None):
        path = self.directory / "cases.json"
        row = {"统一ID": "SYN-1", "问题描述": "Synthetic cache precision problem", "根因": "Synthetic buffer reuse",
               "PR": "https://github.com/example.invalid/example/pull/1"}
        if wiki:
            row["wiki"] = "https://example.invalid/wiki/one"
        path.write_text(json.dumps(rows or [row]), encoding="utf-8")
        result = import_cases(path, source_kind="ORIGINAL_WEEKLY")
        import_into(self.store, self.run, result)
        self.case = result["cases"][0]
        return result["cases"]

    def capture(self, url="https://example.invalid/wiki/one", status="CONTENT_CAPTURED", *, discovery=False, case_id=None):
        return self.store.ingest_evidence(self.run, {"url": url, "title": "Synthetic source",
            "text": "Synthetic buffer reuse precision problem" if status in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"} else "",
            "status": status, "components": {"body": "COMPLETE" if status == "COMPLETE" else "PARTIAL"},
            "is_synthetic": True, "case_ids": [case_id or self.case["case_id"]],
            "origin": "SEARCH_DISCOVERED" if discovery else "HUMAN_ADDED", "record_discovery": discovery})

    def attempt(self, outcome="NO_MATCH", **changes):
        values = {"outcome": outcome, "query": "Synthetic cache buffer reuse", "scope": "example.invalid Wiki space:synthetic",
            "checked_at": "2026-11-06T10:00:00+08:00", "executed_by": "synthetic-agent", "executed": True,
            "reason": "No matching result in this synthetic scope" if outcome == "NO_MATCH" else "Synthetic authentication required"}
        values.update(changes)
        return record_wiki_check(self.store, self.run, self.case["case_id"], **values)

    def plan(self):
        return wiki_plan(self.store, self.run, self.case)

    def test_original_wiki_requires_read_then_stops_additional_search_without_confirming_root(self):
        self.source()
        before = self.plan()
        self.assertEqual(before["status"], "FETCH_REQUIRED")
        self.assertFalse(before["search_allowed"])
        self.assertEqual(before["required_actions"][0]["action"], "FETCH_WIKI")
        snapshot = self.capture()
        after = self.plan()
        self.assertEqual(after["status"], "FOUND")
        self.assertTrue(after["checked"])
        self.assertFalse(after["case_root_cause_confirmed"])
        self.assertFalse(after["search_allowed"])
        self.assertEqual(after["wiki_snapshot_ids"], [snapshot["snapshot_id"]])

    def test_existing_non_wiki_evidence_does_not_skip_wiki_search(self):
        self.source(wiki=False)
        self.capture("https://github.com/example.invalid/example/pull/1")
        plan = self.plan()
        self.assertEqual(plan["status"], "SEARCH_REQUIRED")
        self.assertTrue(plan["search_allowed"])
        self.assertEqual(plan["required_actions"][0]["action"], "SEARCH_WIKI")

    def test_no_match_records_actual_scope_and_is_idempotent_without_endless_search(self):
        self.source(wiki=False)
        record = self.attempt()
        self.assertEqual(record, self.attempt())
        self.assertEqual(len(self.store.records(self.run, "wiki_checks")), 1)
        self.assertEqual(len(self.store.events(self.run, "wiki_check_recorded")), 1)
        plan = self.plan()
        self.assertEqual(plan["status"], "NO_MATCH")
        self.assertTrue(plan["checked"])
        self.assertFalse(plan["search_allowed"])
        self.assertEqual(plan["query"], record["query"])
        self.assertEqual(plan["scope"], record["scope"])
        self.assertEqual(plan, self.plan())

    def test_missing_execution_and_unknown_time_cannot_claim_no_match(self):
        self.source(wiki=False)
        for change in ({"executed": False}, {"query": ""}, {"scope": ""}, {"checked_at": "2026-11-06"}, {"executed_by": ""}):
            with self.assertRaises(AuditError):
                self.attempt(**change)
        self.assertEqual(self.store.records(self.run, "wiki_checks"), [])

    def test_login_failure_is_blocked_not_no_match_and_other_sources_remain(self):
        self.source()
        self.capture(status="AUTH_REQUIRED")
        self.assertEqual(self.plan()["status"], "BLOCKED")
        self.assertFalse(self.plan()["checked"])
        with self.assertRaises(AuditError):
            self.attempt()
        self.assertEqual(len(self.store.records(self.run, "references")), 2)

    def test_search_authentication_attempt_is_retained_as_blocked(self):
        self.source(wiki=False)
        self.attempt(outcome="BLOCKED")
        plan = self.plan()
        self.assertEqual(plan["status"], "BLOCKED")
        self.assertFalse(plan["checked"])
        self.assertFalse(plan["search_allowed"])

    def test_captured_discovery_waits_for_comparison_without_repeating_search(self):
        self.source(wiki=False)
        snapshot = self.capture(discovery=True)
        record_wiki_check(self.store, self.run, self.case["case_id"], outcome="FOUND", snapshot_id=snapshot["snapshot_id"])
        plan = self.plan()
        self.assertEqual(plan["status"], "CANDIDATE_PENDING")
        self.assertFalse(plan["search_allowed"])
        self.assertFalse(plan["checked"])
        self.assertEqual(plan["required_actions"], [{"action": "VERIFY_WIKI", "snapshot_id": snapshot["snapshot_id"]}])
        self.assertEqual(plan["task_id"], self.plan()["task_id"])
        # Routing relies on the existing current comparison gate, rather than
        # upgrading an executor's FOUND declaration into an accepted association.
        with patch("faultaudit.wiki_checks._search_usable", return_value=True):
            self.assertEqual(self.plan()["status"], "FOUND")

    def test_found_requires_a_current_readable_wiki_linked_to_the_case(self):
        self.source(wiki=False)
        git = self.capture("https://github.com/example.invalid/example/pull/1")
        with self.assertRaises(AuditError):
            record_wiki_check(self.store, self.run, self.case["case_id"], outcome="FOUND", snapshot_id=git["snapshot_id"])
        wiki = self.capture(discovery=True)
        self.capture(status="AUTH_REQUIRED", discovery=True)
        with self.assertRaises(AuditError):
            record_wiki_check(self.store, self.run, self.case["case_id"], outcome="FOUND", snapshot_id=wiki["snapshot_id"])

    def test_input_and_original_reference_changes_invalidate_checks_without_deletion(self):
        self.source(wiki=False)
        first = self.attempt()
        changed = copy.deepcopy(self.case)
        changed["description"] += " new configuration"
        self.store.put(self.run, "cases", changed["case_id"], changed, mutable=True)
        self.assertEqual(self.plan()["status"], "SEARCH_REQUIRED")
        self.store.put(self.run, "cases", self.case["case_id"], self.case, mutable=True)
        self.assertEqual(self.plan()["status"], "NO_MATCH")
        ref = self.store.records(self.run, "references")[0]
        ref["raw_text"] += " extra source hint"
        self.store.put(self.run, "references", ref["ref_id"], ref, mutable=True)
        self.assertEqual(self.plan()["status"], "SEARCH_REQUIRED")
        self.assertEqual(self.store.get(self.run, "wiki_checks", first["check_id"]), first)

    def test_confirmed_same_event_reuses_supplied_wiki_and_preserves_source_cases(self):
        rows = [{"统一ID": "SYN-A", "问题描述": "Synthetic shared failure", "wiki": "https://example.invalid/wiki/one"},
                {"统一ID": "SYN-B", "问题描述": "Synthetic shared failure"}]
        cases = self.source(rows=rows)
        register_event_group(self.store, self.run, case_ids=[case["case_id"] for case in cases],
            user_confirmed=True, confirmed_by="synthetic-user", reason="Known same event")
        self.capture(case_id=cases[0]["case_id"])
        self.assertEqual(wiki_plan(self.store, self.run, cases[1])["status"], "FOUND")
        self.assertEqual(len(self.store.records(self.run, "cases")), 2)

    def test_confirmed_snapshot_without_reference_and_read_only_plan(self):
        self.source(wiki=False)
        wiki = self.store.ingest_evidence(self.run, {"url": "https://example.invalid/wiki/one", "text": "Synthetic confirmed Wiki",
            "status": "CONTENT_CAPTURED", "components": {"body": "COMPLETE"}, "is_synthetic": True})
        register_evidence_association(self.store, self.run, case_id=self.case["case_id"], snapshot_id=wiki["snapshot_id"],
            user_confirmed=True, confirmed_by="synthetic-user", reason="Known corresponding material")
        before = (self.store.root / "audit.sqlite3").read_bytes()
        store = Store(self.store.root, read_only=True)
        try:
            self.assertEqual(wiki_plan(store, self.run, self.case)["status"], "FOUND")
        finally:
            store.close()
        self.assertEqual((self.store.root / "audit.sqlite3").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
