"""Evidence-first planning on synthetic local records only."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from faultaudit.evidence_plan import (build_evidence_plan, register_event_group, register_evidence_association,
                                     semantic_input_hash, source_relation)
from faultaudit.importers import import_cases
from faultaudit.pipeline import import_into
from faultaudit.store import AuditError, Store


class EvidencePlanTests(unittest.TestCase):
    def setUp(self):
        self.test_root = Path(__file__).resolve().parent
        self.temp = tempfile.TemporaryDirectory(prefix="evidence-plan-", dir=self.test_root)
        self.directory = Path(self.temp.name).resolve()
        self.store = Store(self.directory / "state")
        self.run_id = self.store.create_run({"is_synthetic": True})

    def tearDown(self):
        self.store.close()
        self.assertTrue(self.directory.is_relative_to(self.test_root))
        self.temp.cleanup()

    def rows(self, count=1, *, link=True, kind="ORIGINAL_WEEKLY", different_root=False):
        rows = []
        for index in range(count):
            row = {"统一ID": f"SYNTHETIC-{index}", "来源": f"synthetic batch {index}", "问题描述": "garbled during restore",
                   "客户/模型": "Model-X", "算子": "cache_op", "根因": "different cause" if different_root and index else "cache failure"}
            if link:
                row["wiki"] = "https://example.invalid/wiki/one"
            rows.append(row)
        path = self.directory / "cases.json"
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        imported = import_cases(path, kind)
        import_into(self.store, self.run_id, imported)
        return imported["cases"]

    def snapshot(self, case_ids=None, *, url="https://example.invalid/wiki/one", status="COMPLETE", text=None):
        return self.store.ingest_evidence(self.run_id, {"url": url, "title": "Synthetic fixture",
            "text": ("garbled during restore; cache failure" if text is None else text) if status not in {"AUTH_REQUIRED", "FORBIDDEN"} else "",
            "status": status, "components": {"body": "COMPLETE" if status == "COMPLETE" else "PARTIAL"},
            "case_ids": case_ids or [], "is_synthetic": True, "origin": "SEARCH_DISCOVERED", "record_discovery": True})

    def plan(self, judgments=None):
        return build_evidence_plan(self.store, self.run_id, judgments=judgments)

    def first(self, plan):
        return plan["cases"][0]

    def useful_search(self, case, snapshot):
        ref = {"segment_id": snapshot["segments"][0]["segment_id"], "quote": snapshot["text"]}
        facts = []
        for meaning, value, field, category in (("symptom", "garbled", "问题描述", "SCENARIO"),
            ("occurrence_context", "restore", "问题描述", "SCENARIO"), ("mechanism", "cache failure", "根因", "TECHNICAL_CONCLUSION")):
            facts.append({"category": category, "source_field": field, "source_quote": case["raw"][field],
                "source_cell": case["cell_locations"][field], "source_value": value, "evidence_value": value,
                "source_meaning": meaning, "evidence_meaning": meaning, "evidence": [ref], "relation": "MATCH", "reason": "Synthetic exact match"})
        for category in ("NUMBER", "TERM"):
            facts.append({"category": category, "source_field": "", "source_quote": "", "source_cell": "", "source_value": "",
                "evidence_value": "", "source_meaning": "unreported", "evidence_meaning": "unreported", "evidence": [],
                "relation": "UNKNOWN", "reason": "Not reported in this synthetic issue"})
        return {"judgment_id": "synthetic-search-judgment", "case_id": case["case_id"], "snapshot_id": snapshot["snapshot_id"],
            "case_attribution": "PARTIAL", "event_relation": "UNDETERMINED", "review_status": "NEEDS_REVIEW",
            "support_level": "PARTIAL", "claim_support": {"root_cause": "PARTIAL"}, "conflicting_dimensions": [],
            "processing_status": "AUTO_PROCESSED", "model_mode": "opencode", "fact_comparisons": facts,
            "applicable_issue": {"label": "Synthetic issue", "evidence": [ref], "selection_reason": "Applicable captured issue"},
            "evidence": [ref], "self_check": {"attempt": 1, "numeric_meaning_checked": True, "citations_checked": True,
                "counterevidence_checked": True, "issue_scope_checked": True, "event_vs_technical_checked": True,
                "passed": True, "issues": []}}

    def excluded_search(self, case, snapshot):
        judgment = self.useful_search(case, snapshot)
        ref = {"segment_id": snapshot["segments"][0]["segment_id"], "quote": snapshot["text"]}
        context = snapshot["text"]
        judgment.update(case_attribution="MISMATCH", event_relation="DIFFERENT_EVENT", support_level="NONE",
            claim_support={"root_cause": "UNKNOWN"}, negative_basis={
                "other_event": {"positive_identity": "OTHER-EVENT", "context": context,
                    "dimensions": ["event_identity", "symptom", "occurrence_context"], "evidence": [ref]},
                "attribution_mismatch": {"positive_identity": "OtherTenant", "context": context,
                    "dimensions": ["ownership", "symptom", "occurrence_context"], "evidence": [ref]}})
        return judgment

    def test_original_link_is_source_linked_with_cell_trace_and_fetch_only(self):
        case = self.rows()[0]
        ref = self.store.records(self.run_id, "references")[0]
        relation = source_relation(case, ref)
        self.assertEqual(relation["relation"], "SOURCE_LINKED")
        self.assertTrue(relation["trace"]["reference_location"])
        before = self.store.conn.total_changes
        plan = self.plan()
        self.assertEqual(self.store.conn.total_changes, before)
        self.assertEqual(self.first(plan)["path"], "FETCH_ORIGINAL")
        self.assertEqual([action["action"] for action in self.first(plan)["required_actions"]], ["FETCH"])

    def test_no_link_searches_but_unknown_source_reference_does_not(self):
        case = self.rows(link=False)[0]
        self.assertEqual(self.first(self.plan())["path"], "SEARCH_REQUIRED")
        self.snapshot([case["case_id"]])
        ref = self.store.records(self.run_id, "references")[0]
        self.store.put(self.run_id, "references", ref["ref_id"], {**ref, "origin": "LEGACY_TABLE"}, mutable=True)
        planned = self.first(self.plan())
        self.assertEqual(planned["path"], "EXCEPTION")
        self.assertEqual(planned["stop_reason"], "REFERENCE_PROVENANCE_PENDING")
        self.assertNotIn("SEARCH", [action["action"] for action in planned["required_actions"]])

    def test_old_root_and_source_metadata_are_not_promoted_to_original(self):
        case = self.rows(kind="LEGACY_TABLE")[0]
        ref = self.store.records(self.run_id, "references")[0]
        self.assertEqual(source_relation(case, ref)["relation"], "PROVENANCE_PENDING")
        self.snapshot()
        self.assertEqual(self.first(self.plan())["path"], "EXCEPTION")
        self.assertEqual(self.store.get(self.run_id, "cases", case["case_id"])["root_cause_origin"], "LEGACY_DERIVED_UNKNOWN")

    def test_partial_is_usable_and_capture_completion_is_optional(self):
        self.rows()
        snapshot = self.snapshot(status="PARTIAL")
        plan = self.plan()
        case = self.first(plan)
        self.assertEqual(case["relation"], "SOURCE_LINKED")
        self.assertEqual(case["selected_snapshot_ids"], [snapshot["snapshot_id"]])
        self.assertEqual([action["action"] for action in case["required_actions"]], ["EXTRACT_FACTS"])
        self.assertFalse(case["optional_actions"][0]["blocking"])
        self.assertEqual(len(plan["work_items"]), 1)

    def test_auth_failure_is_not_no_evidence_or_search(self):
        self.rows()
        self.snapshot(status="AUTH_REQUIRED")
        case = self.first(self.plan())
        self.assertEqual(case["path"], "EXCEPTION")
        self.assertEqual(case["required_actions"][0]["action"], "RESOLVE_CAPTURE_FAILURE")
        self.assertEqual(self.plan()["work_items"], [])

    def test_explicit_confirmed_association_does_not_require_old_event_confirmation(self):
        case = self.rows(kind="LEGACY_TABLE")[0]
        ref = self.store.records(self.run_id, "references")[0]
        snapshot = self.snapshot()
        association = register_evidence_association(self.store, self.run_id, case_id=case["case_id"], ref_id=ref["ref_id"],
            snapshot_id=snapshot["snapshot_id"], user_confirmed=True, confirmed_by="synthetic-user", reason="Explicit synthetic association")
        plan = self.first(self.plan())
        self.assertEqual(plan["relation"], "USER_CONFIRMED")
        self.assertEqual(plan["association_ids"], [association["association_id"]])
        self.assertEqual(plan["selected_snapshot_ids"], [snapshot["snapshot_id"]])

    def test_search_candidate_is_processed_before_more_search_and_valid_result_stops(self):
        case = self.rows(link=False)[0]
        snapshot = self.snapshot([case["case_id"]])
        before = self.plan()
        self.assertEqual(self.first(before)["path"], "SEARCH_CANDIDATE")
        useful = self.useful_search(case, snapshot)
        after = self.plan([useful])
        self.assertEqual(self.first(after)["path"], "VERIFIED_SEARCH")
        self.assertEqual(self.first(after)["relation"], "SEARCH_CANDIDATE")
        self.assertEqual(self.first(before)["routing_hash"], self.first(after)["routing_hash"])
        self.assertEqual(before["plan_hash"], after["plan_hash"])
        self.assertNotIn("SEARCH", [action["action"] for action in self.first(after)["required_actions"]])
        del useful["fact_comparisons"]
        self.assertEqual(self.first(self.plan([useful]))["path"], "SEARCH_CANDIDATE")

    def test_known_conflict_keeps_both_captured_sources_without_fetching_unread_links(self):
        case = self.rows()[0]
        first = self.snapshot()
        second = self.snapshot([case["case_id"]], url="https://example.invalid/wiki/two", text="Different synthetic conclusion")
        ref = self.store.records(self.run_id, "references")[0]
        self.store.put(self.run_id, "references", "unread-ref", {**ref, "ref_id": "unread-ref", "url": "https://example.invalid/unread"})
        conflict = {"judgment_id": "CONFLICT", "case_id": case["case_id"], "snapshot_id": second["snapshot_id"],
                    "review_status": "NEEDS_REVIEW", "support_level": "CONFLICT", "conflicting_dimensions": ["root_cause"]}
        planned = self.first(self.plan([conflict]))
        self.assertEqual(planned["path"], "EXCEPTION")
        self.assertEqual(set(planned["selected_snapshot_ids"]), {first["snapshot_id"], second["snapshot_id"]})
        self.assertNotIn("unread-ref", planned["selected_ref_ids"])
        self.assertNotIn("FETCH", [action["action"] for action in planned["required_actions"]])

    def test_shared_url_does_not_register_or_merge_event_groups(self):
        cases = self.rows(count=2)
        self.snapshot()
        planned = self.plan()
        self.assertEqual(planned["groups"], [])
        self.assertEqual(len(planned["work_items"]), 2)
        self.assertEqual(self.store.records(self.run_id, "event_groups"), [])

    def test_explicit_group_deduplicates_same_input_despite_different_source_ids(self):
        cases = self.rows(count=2)
        original = copy.deepcopy(self.store.records(self.run_id, "cases"))
        self.snapshot()
        self.assertEqual(semantic_input_hash(cases[0]), semantic_input_hash(cases[1]))
        register_event_group(self.store, self.run_id, case_ids=[case["case_id"] for case in cases], user_confirmed=True,
            confirmed_by="synthetic-user", reason="Explicitly the same synthetic event")
        planned = self.plan()
        self.assertEqual(len(planned["work_items"]), 1)
        self.assertEqual(set(planned["work_items"][0]["case_ids"]), {case["case_id"] for case in cases})
        self.assertEqual(self.store.records(self.run_id, "cases"), original)

    def test_group_member_without_link_inherits_actual_source_and_shares_only_same_input(self):
        cases = self.rows(count=2)
        second_refs = [ref for ref in self.store.records(self.run_id, "references") if ref["case_id"] == cases[1]["case_id"]]
        for ref in second_refs:
            self.store.conn.execute("DELETE FROM records WHERE run_id=? AND kind='references' AND id=?", (self.run_id, ref["ref_id"]))
        self.store.conn.commit()
        self.snapshot()
        register_event_group(self.store, self.run_id, case_ids=[case["case_id"] for case in cases], user_confirmed=True,
            confirmed_by="synthetic-user", reason="Explicit same event")
        planned = self.plan()
        inherited = next(case for case in planned["cases"] if case["case_id"] == cases[1]["case_id"])
        self.assertEqual(inherited["relation"], "USER_CONFIRMED")
        self.assertEqual(inherited["provenance"][0]["inherited_from_case_id"], cases[0]["case_id"])
        self.assertEqual(len(planned["work_items"]), 1)

    def test_group_different_original_root_causes_stay_separate_work(self):
        cases = self.rows(count=2, different_root=True)
        self.snapshot()
        register_event_group(self.store, self.run_id, case_ids=[case["case_id"] for case in cases], user_confirmed=True,
            confirmed_by="synthetic-user", reason="Same event with distinct source hypotheses")
        planned = self.plan()
        self.assertEqual(len(planned["work_items"]), 2)
        self.assertTrue(planned["groups"][0]["technical_input_divergence"])

    def test_same_group_snapshot_but_different_applicable_issues_does_not_share_work(self):
        cases = self.rows(count=2)
        snapshot = self.snapshot()
        register_event_group(self.store, self.run_id, case_ids=[case["case_id"] for case in cases], user_confirmed=True,
            confirmed_by="synthetic-user", reason="Same event, scoped different questions")
        for index, case in enumerate(cases):
            ref = next(ref for ref in self.store.records(self.run_id, "references") if ref["case_id"] == case["case_id"])
            register_evidence_association(self.store, self.run_id, case_id=case["case_id"], ref_id=ref["ref_id"], snapshot_id=snapshot["snapshot_id"],
                applicable_issue_ids=[f"ISSUE-{index}"], user_confirmed=True, confirmed_by="synthetic-user", reason="Explicit issue scope")
        self.assertEqual(len(self.plan()["work_items"]), 2)

    def test_registrations_require_explicit_user_confirmation_and_known_members(self):
        cases = self.rows(count=2)
        for kwargs in ({"user_confirmed": False, "confirmed_by": "synthetic-user", "reason": "x"},
                       {"user_confirmed": True, "confirmed_by": "", "reason": "x"}):
            with self.assertRaises(AuditError):
                register_event_group(self.store, self.run_id, case_ids=[case["case_id"] for case in cases], **kwargs)
        with self.assertRaises(AuditError):
            register_event_group(self.store, self.run_id, case_ids=[cases[0]["case_id"], "not-in-run"], user_confirmed=True,
                confirmed_by="synthetic-user", reason="x")

    def test_completed_negative_search_candidate_selects_next_without_permanent_exception(self):
        case = self.rows(link=False)[0]
        first = self.snapshot([case["case_id"]], text="OtherTenant owns OTHER-EVENT, a separate garbled during restore incident due to cache failure.")
        second = self.snapshot([case["case_id"]], url="https://example.invalid/wiki/two")
        negative = self.excluded_search(case, first)
        planned = self.first(self.plan([negative]))
        self.assertEqual(planned["path"], "SEARCH_CANDIDATE")
        self.assertEqual(planned["selected_snapshot_ids"], [second["snapshot_id"]])
        self.assertIn(negative["judgment_id"], planned["excluded_candidate_judgment_ids"])

    def test_all_search_candidates_positively_excluded_allows_more_search(self):
        case = self.rows(link=False)[0]
        snapshot = self.snapshot([case["case_id"]], text="OtherTenant owns OTHER-EVENT, a separate garbled during restore incident due to cache failure.")
        planned = self.first(self.plan([self.excluded_search(case, snapshot)]))
        self.assertEqual(planned["path"], "SEARCH_REQUIRED")
        self.assertEqual(planned["required_actions"][0]["action"], "SEARCH")
        self.assertEqual(planned["selected_snapshot_ids"], [])


if __name__ == "__main__":
    unittest.main()
