"""Evidence-first planning on synthetic local records only."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from faultaudit.evidence_plan import (build_evidence_plan, register_event_group, register_evidence_association,
                                     semantic_input_hash, source_relation, register_search_policy, get_search_policy,
                                     normalize_search_policy, resource_kind)
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

    def rows(self, count=1, *, link=True, kind="ORIGINAL_WEEKLY", different_root=False, additional_links=None):
        rows = []
        for index in range(count):
            row = {"统一ID": f"SYNTHETIC-{index}", "来源": f"synthetic batch {index}", "问题描述": "garbled during restore",
                   "客户/模型": "Model-X", "算子": "cache_op", "根因": "different cause" if different_root and index else "cache failure"}
            if link:
                row["wiki"] = "https://example.invalid/wiki/one"
            row.update(additional_links or {})
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
        self.assertEqual(relation["relation"], "SOURCE_CELL_LINKED")
        self.assertEqual(relation["legacy_relation"], "SOURCE_LINKED")
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
        self.assertEqual(planned["path"], "PROVENANCE_RECOVERY")
        self.assertEqual(planned["stop_reason"], "AGENT_RECOVERS_SOURCE_BEFORE_REPORTING_GAP")
        recovery = next(action for action in planned["required_actions"] if action["action"] == "RECOVER_PROVENANCE")
        self.assertEqual(recovery["actor"], "AGENT")
        self.assertEqual(recovery["on_failure"], "REPORT_PROVENANCE_GAP")
        self.assertNotIn("SEARCH", [action["action"] for action in planned["required_actions"]])

    def test_old_root_and_source_metadata_are_not_promoted_to_original(self):
        case = self.rows(kind="LEGACY_TABLE")[0]
        ref = self.store.records(self.run_id, "references")[0]
        self.assertEqual(source_relation(case, ref)["relation"], "LEGACY_TABLE_LINKED")
        self.snapshot()
        self.assertEqual(self.first(self.plan())["path"], "LEGACY_TABLE_LINKED")
        self.assertNotEqual(self.first(self.plan())["relation"], "SOURCE_CELL_LINKED")
        self.assertEqual(self.store.get(self.run_id, "cases", case["case_id"])["root_cause_origin"], "LEGACY_DERIVED_UNKNOWN")

    def test_partial_is_usable_and_capture_completion_is_optional(self):
        self.rows()
        snapshot = self.snapshot(status="PARTIAL")
        plan = self.plan()
        case = self.first(plan)
        self.assertEqual(case["relation"], "SOURCE_CELL_LINKED")
        self.assertEqual(case["selected_snapshot_ids"], [snapshot["snapshot_id"]])
        self.assertEqual([action["action"] for action in case["required_actions"]], ["EXTRACT_FACTS"])
        self.assertFalse(case["optional_actions"][0]["blocking"])
        self.assertEqual(len(plan["work_items"]), 1)

    def test_auth_failure_is_not_no_evidence_or_search(self):
        self.rows()
        self.snapshot(status="AUTH_REQUIRED")
        case = self.first(self.plan())
        self.assertEqual(case["path"], "CAPTURE_GAPS")
        self.assertEqual(case["required_actions"][0]["action"], "RESOLVE_CAPTURE_FAILURE")
        self.assertEqual(case["required_actions"][0]["actor"], "AGENT")
        self.assertEqual(self.plan()["work_items"], [])

    def test_explicit_confirmed_association_does_not_require_old_event_confirmation(self):
        case = self.rows(kind="LEGACY_TABLE")[0]
        ref = self.store.records(self.run_id, "references")[0]
        snapshot = self.snapshot()
        association = register_evidence_association(self.store, self.run_id, case_id=case["case_id"], ref_id=ref["ref_id"],
            snapshot_id=snapshot["snapshot_id"], user_confirmed=True, confirmed_by="synthetic-user", reason="Explicit synthetic association")
        plan = self.first(self.plan())
        self.assertEqual(plan["relation"], "LEGACY_TABLE_LINKED")
        self.assertTrue(plan["user_confirmed"])
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
        self.assertEqual(self.first(after)["relation"], "SEARCH_DISCOVERED")
        self.assertEqual(self.first(before)["routing_hash"], self.first(after)["routing_hash"])
        self.assertEqual(before["plan_hash"], after["plan_hash"])
        self.assertNotIn("SEARCH", [action["action"] for action in self.first(after)["required_actions"]])
        del useful["fact_comparisons"]
        self.assertEqual(self.first(self.plan([useful]))["path"], "SEARCH_CANDIDATE")

    def test_known_conflict_keeps_captured_sources_and_all_supplied_table_references(self):
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
        self.assertIn("unread-ref", planned["selected_ref_ids"])
        self.assertIn("FETCH", [action["action"] for action in planned["required_actions"]])

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
        self.assertEqual(inherited["relation"], "SOURCE_CELL_LINKED")
        self.assertTrue(inherited["user_confirmed"])
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

    def test_all_original_table_references_are_selected_and_fetch_is_shared_by_url(self):
        cases = self.rows(count=2, additional_links={"DTS": "https://example.invalid/dts/one", "PR": "https://example.invalid/code/one"})
        planned = self.plan()
        self.assertEqual(len(self.store.records(self.run_id, "references")), 6)
        self.assertEqual([len(row["selected_ref_ids"]) for row in planned["cases"]], [3, 3])
        self.assertEqual(len(planned["fetch_work_items"]), 3)
        self.assertTrue(all(fetch["required"] for fetch in planned["fetch_work_items"]))
        self.assertTrue(all(len(fetch["ref_ids"]) == 2 and set(fetch["case_ids"]) == {case["case_id"] for case in cases}
                            for fetch in planned["fetch_work_items"]))
        for url in ("https://example.invalid/wiki/one", "https://example.invalid/dts/one", "https://example.invalid/code/one"):
            self.snapshot(url=url)
        captured = self.plan()
        self.assertEqual(len(captured["work_items"]), 6, "Collection sharing must not merge unconfirmed cases")
        self.assertTrue(all(not fetch["required"] for fetch in captured["fetch_work_items"]))

    def test_same_case_two_cells_same_url_and_scope_share_one_fact_work(self):
        self.rows(additional_links={"DTS": "https://example.invalid/wiki/one"})
        self.snapshot()
        planned = self.plan()
        self.assertEqual(len(self.first(planned)["selected_ref_ids"]), 2)
        self.assertEqual(len(planned["work_items"]), 1)
        self.assertEqual(len(planned["work_items"][0]["ref_ids"]), 2)
        self.assertEqual(len(planned["fetch_work_items"]), 1)
        self.assertEqual(planned["work_items"][0]["source_grades"], ["SOURCE_CELL_LINKED"])

    def test_same_case_same_snapshot_distinct_explicit_issues_replace_default_full_scope(self):
        case = self.rows()[0]
        snapshot = self.snapshot()
        for label in ("ISSUE-A", "ISSUE-B"):
            register_evidence_association(self.store, self.run_id, case_id=case["case_id"], snapshot_id=snapshot["snapshot_id"],
                applicable_issue_ids=[label], user_confirmed=True, confirmed_by="synthetic-user", reason="Explicit scope")
        planned = self.plan()
        self.assertEqual(len(planned["work_items"]), 2)
        self.assertEqual({tuple(work["issue_scope"]["applicable_issue_ids"]) for work in planned["work_items"]},
                         {("ISSUE-A",), ("ISSUE-B",)})
        self.assertTrue(all(work["issue_scope"]["scope"] == "ISSUES" for work in planned["work_items"]))
        self.assertEqual(len(planned["fetch_work_items"]), 1)

    def test_confirmation_is_independent_of_legacy_and_search_source_grades(self):
        case = self.rows(kind="LEGACY_TABLE")[0]
        snapshot = self.snapshot()
        register_evidence_association(self.store, self.run_id, case_id=case["case_id"], snapshot_id=snapshot["snapshot_id"],
            user_confirmed=True, confirmed_by="synthetic-user", reason="Confirm applicability only")
        planned = self.plan()
        self.assertEqual(len(planned["work_items"]), 1, "Confirmation must not create another FULL_SNAPSHOT work")
        work = planned["work_items"][0]
        self.assertTrue(work["user_confirmed"])
        self.assertEqual(work["relation"], "LEGACY_TABLE_LINKED")
        self.assertEqual(work["source_grades"], ["LEGACY_TABLE_LINKED"])
        self.assertEqual(self.store.get(self.run_id, "cases", case["case_id"])["root_cause_origin"], "LEGACY_DERIVED_UNKNOWN")

    def test_unselected_unknown_origin_is_visible_as_agent_recovery_alongside_known_source(self):
        case = self.rows()[0]
        ref = self.store.records(self.run_id, "references")[0]
        unknown = {**ref, "ref_id": "unknown-origin", "origin": "UNKNOWN", "discovered_by": "unrestored-import",
                   "location": "unknown-origin", "url": "https://example.invalid/unrestored"}
        self.store.put(self.run_id, "references", unknown["ref_id"], unknown)
        self.snapshot()
        planned = self.first(self.plan())
        self.assertEqual(planned["relation"], "SOURCE_CELL_LINKED")
        recovery = [action for action in planned["optional_actions"] if action["action"] == "RECOVER_PROVENANCE"]
        self.assertEqual(len(recovery), 1)
        self.assertEqual(recovery[0]["ref_id"], "unknown-origin")
        self.assertEqual(recovery[0]["actor"], "AGENT")
        self.assertFalse(recovery[0]["blocking"])
        self.assertTrue(any(issue["code"] == "UNRESOLVED_REFERENCE_PROVENANCE" for issue in planned["issues"]))
        self.assertNotEqual(planned["path"], "EXCEPTION")
        self.assertNotIn("SEARCH", [action["action"] for action in planned["required_actions"]])

    def test_replaced_full_snapshot_conflict_does_not_pollute_new_explicit_issue_scope(self):
        case = self.rows()[0]
        snapshot = self.snapshot()
        old_work = self.plan()["work_items"][0]["work_id"]
        old_conflict = {"judgment_id": "OLD-FULL-CONFLICT", "case_id": case["case_id"], "snapshot_id": snapshot["snapshot_id"],
            "work_id": old_work, "review_status": "NEEDS_REVIEW", "support_level": "CONFLICT",
            "claim_support": {"root_cause": "CONTRADICTED"}, "conflicting_dimensions": ["root_cause"]}
        self.assertEqual(self.first(self.plan([old_conflict]))["path"], "EXCEPTION")
        register_evidence_association(self.store, self.run_id, case_id=case["case_id"], snapshot_id=snapshot["snapshot_id"],
            applicable_issue_ids=["GOOD-ISSUE"], user_confirmed=True, confirmed_by="synthetic-user", reason="Replace the old broad scope")
        planned = self.plan([old_conflict])
        self.assertNotEqual(self.first(planned)["path"], "EXCEPTION")
        self.assertNotIn(old_work, self.first(planned)["work_ids"])
        self.assertNotIn("RECONCILE_CONFLICT", [action["action"] for action in self.first(planned)["required_actions"]])
        self.assertEqual(planned["work_items"][0]["issue_scope"]["applicable_issue_ids"], ["GOOD-ISSUE"])

    def test_unselected_negative_search_work_stays_candidate_bound_and_is_not_retried(self):
        case = self.rows(link=False)[0]
        first = self.snapshot([case["case_id"]], text="OtherTenant owns OTHER-EVENT, a separate garbled during restore incident due to cache failure.")
        old_work = self.plan()["work_items"][0]["work_id"]
        negative = {**self.excluded_search(case, first), "work_id": old_work}
        second = self.snapshot([case["case_id"]], url="https://example.invalid/wiki/two")
        for _ in range(2):
            planned = self.first(self.plan([negative]))
            self.assertEqual(planned["selected_snapshot_ids"], [second["snapshot_id"]])
            self.assertNotIn(old_work, planned["work_ids"])
            self.assertIn(negative["judgment_id"], planned["excluded_candidate_judgment_ids"])

    def test_group_scope_change_filters_prior_shared_conflict_for_only_changed_member(self):
        cases = self.rows(count=2)
        snapshot = self.snapshot()
        register_event_group(self.store, self.run_id, case_ids=[case["case_id"] for case in cases],
            user_confirmed=True, confirmed_by="synthetic-user", reason="Same synthetic event")
        old = self.plan()["work_items"][0]
        prior = {"judgment_id": "OLD-SHARED-CONFLICT", "case_id": old["representative_case_id"],
            "member_case_ids": old["case_ids"], "snapshot_id": snapshot["snapshot_id"], "work_id": old["work_id"],
            "review_status": "NEEDS_REVIEW", "support_level": "CONFLICT", "conflicting_dimensions": ["root_cause"]}
        changed = next(case for case in cases if case["case_id"] != old["representative_case_id"])
        register_evidence_association(self.store, self.run_id, case_id=changed["case_id"], snapshot_id=snapshot["snapshot_id"],
            applicable_issue_ids=["GOOD-ISSUE"], user_confirmed=True, confirmed_by="synthetic-user", reason="Scope one member independently")
        planned = self.plan([prior])
        original = next(row for row in planned["cases"] if row["case_id"] == old["representative_case_id"])
        changed_row = next(row for row in planned["cases"] if row["case_id"] == changed["case_id"])
        self.assertEqual(original["path"], "EXCEPTION")
        self.assertIn(old["work_id"], original["work_ids"])
        self.assertNotEqual(changed_row["path"], "EXCEPTION")
        self.assertNotIn(old["work_id"], changed_row["work_ids"])
        self.assertNotIn("RECONCILE_CONFLICT", [action["action"] for action in changed_row["required_actions"]])

    def test_default_any_existing_source_stops_search_including_dts(self):
        sources = {"WIKI": "https://wiki.example.invalid/main", "DTS": "https://dts.example.invalid/ticket/DTS2026110500001",
                   "GITCODE": "https://gitcode.com/synthetic/example/pull/1", "GITHUB": "https://github.com/synthetic/example/pull/1",
                   "CODEHUB": "https://codehub-dg.example.invalid/project/merge_requests/1"}
        for expected, url in sources.items():
            with self.subTest(source=expected):
                self.run_id = self.store.create_run({"is_synthetic": True})
                self.rows(link=False, additional_links={"链接": url})
                before = self.first(self.plan())
                self.assertFalse(before["search_control"]["search_allowed"])
                self.assertNotIn("SEARCH", [action["action"] for action in before["required_actions"]])
                self.snapshot(url=url, status="PARTIAL")
                after = self.first(self.plan())
                self.assertTrue(after["search_control"]["satisfied"])
                self.assertEqual(after["search_control"]["usable_sources"], [expected])
                self.assertEqual(after["search_control"]["usable_evidence_count"], 1)

    def test_policy_append_history_case_override_and_read_only_lookup(self):
        cases = self.rows(count=2)
        initial = get_search_policy(self.store, self.run_id, cases[0]["case_id"])
        self.assertEqual(initial["scope"], "DEFAULT")
        first = register_search_policy(self.store, self.run_id, {"required_sources": ["GITCODE"]})
        again = register_search_policy(self.store, self.run_id, {"required_sources": ["GITCODE", "GITCODE"]})
        self.assertEqual(first, again)
        second = register_search_policy(self.store, self.run_id, {"min_usable_evidence": 2})
        override = register_search_policy(self.store, self.run_id, {"required_any_sources": ["GITHUB", "GITCODE"]}, cases[0]["case_id"])
        self.assertEqual(len(self.store.records(self.run_id, "search_policies")), 3)
        self.assertEqual(first["revision"], 1)
        self.assertEqual(second["revision"], 2)
        self.assertEqual(get_search_policy(self.store, self.run_id, cases[0]["case_id"])["policy_record_id"], override["policy_record_id"])
        self.assertEqual(get_search_policy(self.store, self.run_id, cases[1]["case_id"])["policy_record_id"], second["policy_record_id"])
        changes = self.store.conn.total_changes
        self.plan()
        self.assertEqual(self.store.conn.total_changes, changes)
        reverted = register_search_policy(self.store, self.run_id, {"required_sources": ["GITCODE"]})
        self.assertEqual(reverted["revision"], 3)
        self.assertNotEqual(reverted["policy_record_id"], first["policy_record_id"])
        self.assertEqual(reverted["policy_hash"], first["policy_hash"])

    def test_policy_rejects_invalid_counts_sources_and_unknown_case(self):
        self.rows()
        for policy in ({"min_usable_evidence": True}, {"min_usable_evidence": 0}, {"min_usable_evidence": "2"},
                       {"required_sources": "WIKI"}, {"required_sources": ["CODE"]}, {"required_any_sources": [None]}, {"unknown": 1}):
            with self.subTest(policy=policy), self.assertRaises(AuditError):
                normalize_search_policy(policy)
        with self.assertRaises(AuditError):
            register_search_policy(self.store, self.run_id, {}, "outside-run")

    def test_explicit_source_policy_selects_discovered_support_and_keeps_it_after_goal(self):
        case = self.rows()[0]
        original = self.snapshot()
        support = self.snapshot([case["case_id"]], url="https://gitcode.com/synthetic/example/pull/1", status="PARTIAL")
        default = self.first(self.plan())
        self.assertEqual(default["selected_snapshot_ids"], [original["snapshot_id"]])
        register_search_policy(self.store, self.run_id, {"required_sources": ["GITCODE"]})
        pending = self.first(self.plan())
        self.assertEqual(set(pending["selected_snapshot_ids"]), {original["snapshot_id"], support["snapshot_id"]})
        self.assertEqual(pending["search_control"]["status"], "CANDIDATE_PENDING")
        self.assertFalse(pending["search_control"]["search_allowed"])
        self.assertFalse(pending["search_control"]["satisfied"])
        complete = self.first(self.plan([self.useful_search(case, support)]))
        self.assertTrue(complete["search_control"]["satisfied"])
        self.assertEqual(complete["selected_snapshot_ids"], pending["selected_snapshot_ids"])
        self.assertEqual(complete["routing_hash"], pending["routing_hash"])
        self.assertFalse(complete["search_control"]["search_allowed"])
        self.assertFalse(complete["user_confirmed"])

    def test_source_requirements_are_and_with_separate_any_source_or(self):
        case = self.rows()[0]
        self.snapshot()
        register_search_policy(self.store, self.run_id, {"required_sources": ["WIKI", "DTS"],
            "required_any_sources": ["GITCODE", "GITHUB"]})
        missing = self.first(self.plan())
        self.assertEqual(missing["search_control"]["missing_sources"], ["DTS"])
        self.assertEqual(missing["search_control"]["missing_any_sources"], ["GITCODE", "GITHUB"])
        action = next(action for action in missing["required_actions"] if action["action"] == "SEARCH_SUPPORT")
        self.assertEqual(action["target_sources"], ["DTS", "GITCODE", "GITHUB"])
        dts = self.snapshot([case["case_id"]], url="https://dts.example.invalid/ticket/DTS2026110500001")
        github = self.snapshot([case["case_id"]], url="https://github.com/synthetic/example/pull/1", status="PARTIAL")
        useful = [self.useful_search(case, dts), {**self.useful_search(case, github), "judgment_id": "second-search"}]
        done = self.first(self.plan(useful))
        self.assertTrue(done["search_control"]["satisfied"])
        self.assertEqual(done["search_control"]["usable_sources"], ["DTS", "GITHUB", "WIKI"])
        self.assertEqual(len(done["selected_snapshot_ids"]), 3)

    def test_minimum_counts_unique_snapshots_not_occurrences_and_policy_changes_routing(self):
        case = self.rows(additional_links={"DTS": "https://example.invalid/wiki/one"})[0]
        self.snapshot()
        before = self.first(self.plan())
        register_search_policy(self.store, self.run_id, {"min_usable_evidence": 2})
        required = self.first(self.plan())
        self.assertEqual(required["search_control"]["usable_evidence_count"], 1)
        self.assertTrue(required["search_control"]["search_allowed"])
        self.assertNotEqual(before["routing_hash"], required["routing_hash"])
        support = self.snapshot([case["case_id"]], url="https://github.com/synthetic/example/pull/1", status="PARTIAL")
        self.assertFalse(self.first(self.plan())["search_control"]["satisfied"])
        done = self.first(self.plan([self.useful_search(case, support)]))
        self.assertTrue(done["search_control"]["satisfied"])
        self.assertEqual(done["search_control"]["usable_evidence_count"], 2)

    def test_blocked_first_policy_candidate_does_not_jump_to_later_readable_one(self):
        case = self.rows()[0]
        self.snapshot()
        register_search_policy(self.store, self.run_id, {"required_sources": ["GITCODE"]})
        failed = self.snapshot([case["case_id"]], url="https://gitcode.com/synthetic/first/pull/1", status="AUTH_REQUIRED")
        later = self.snapshot([case["case_id"]], url="https://gitcode.com/synthetic/later/pull/2", status="PARTIAL")
        planned = self.first(self.plan())
        self.assertIn(failed["snapshot_id"], planned["selected_snapshot_ids"])
        self.assertNotIn(later["snapshot_id"], planned["selected_snapshot_ids"])
        self.assertEqual(planned["search_control"]["status"], "CAPTURE_GAP")
        self.assertFalse(planned["search_control"]["search_allowed"])
        self.assertIn("RESOLVE_CAPTURE_FAILURE", [action["action"] for action in planned["required_actions"]])

    def test_negative_policy_candidate_is_not_counted_then_searches_next(self):
        case = self.rows()[0]
        self.snapshot()
        register_search_policy(self.store, self.run_id, {"required_sources": ["GITCODE"]})
        other = self.snapshot([case["case_id"]], url="https://gitcode.com/synthetic/other/pull/1", status="PARTIAL",
            text="OtherTenant owns OTHER-EVENT, a separate garbled during restore incident due to cache failure.")
        pending_work = next(work for work in self.plan()["work_items"] if work["snapshot_id"] == other["snapshot_id"])
        negative = {**self.excluded_search(case, other), "work_id": pending_work["work_id"]}
        planned = self.first(self.plan([negative]))
        self.assertTrue(planned["search_control"]["search_allowed"])
        self.assertFalse(planned["search_control"]["satisfied"])
        self.assertEqual(planned["search_control"]["usable_sources"], ["WIKI"])
        self.assertNotIn(other["snapshot_id"], planned["selected_snapshot_ids"])
        self.assertEqual(planned["path"], "SEARCH_REQUIRED")

    def test_existing_source_capture_failure_is_processed_before_explicit_search(self):
        self.rows()
        self.snapshot(status="AUTH_REQUIRED")
        register_search_policy(self.store, self.run_id, {"required_sources": ["GITCODE"]})
        planned = self.first(self.plan())
        self.assertFalse(planned["search_control"]["search_allowed"])
        self.assertEqual(planned["search_control"]["status"], "CAPTURE_GAP")
        self.assertNotIn("SEARCH_SUPPORT", [action["action"] for action in planned["required_actions"]])

    def test_generic_source_type_under_explicit_source_goal_is_recovered_before_search(self):
        self.rows(link=False, additional_links={"链接": "https://example.invalid/unknown"})
        self.snapshot(url="https://example.invalid/unknown")
        register_search_policy(self.store, self.run_id, {"required_sources": ["GITHUB"]})
        planned = self.first(self.plan())
        self.assertEqual(planned["search_control"]["status"], "SOURCE_UNKNOWN")
        self.assertFalse(planned["search_control"]["search_allowed"])
        self.assertIn("RECOVER_RESOURCE_KIND", [action["action"] for action in planned["required_actions"]])

    def test_resource_classifier_honors_actual_url_and_exact_header_over_generic_artifact(self):
        case = self.rows(additional_links={"DTS": "https://github.com/synthetic/example/pull/1"})[0]
        refs = self.store.records(self.run_id, "references")
        wiki = next(ref for ref in refs if "/wiki/" in ref["url"])
        github = next(ref for ref in refs if "github.com" in ref["url"])
        self.assertEqual(resource_kind(github, {"artifact_type": "GENERIC"}, case), "GITHUB")
        self.assertEqual(resource_kind({**wiki, "url": "https://example.invalid/main"}, {"artifact_type": "GENERIC"}, case), "WIKI")
        self.assertEqual(resource_kind({"url": "https://example.invalid/main", "location": "wiki-discovery"}), "UNKNOWN")
        self.assertEqual(resource_kind({"url": "https://github.evil.invalid/project/pull/1"}), "UNKNOWN")
        self.assertEqual(resource_kind({"url": "https://gitcode.evil.invalid/project/pull/1"}), "UNKNOWN")

    def test_seven_description_only_rows_generate_independent_search_plans(self):
        path = self.directory / "blind.json"
        path.write_text(json.dumps([{"问题描述": f"Synthetic independent fault description {index}"} for index in range(7)]), encoding="utf-8")
        import_into(self.store, self.run_id, import_cases(path, "ORIGINAL_WEEKLY"))
        planned = self.plan()
        self.assertEqual(len(planned["cases"]), 7)
        self.assertEqual(planned["work_items"], [])
        self.assertTrue(all(case["search_control"]["search_allowed"] for case in planned["cases"]))
        self.assertTrue(all([action["action"] for action in case["required_actions"]] == ["SEARCH"] for case in planned["cases"]))

    def test_complete_but_weak_candidate_allows_next_or_search_without_false_negative(self):
        case = self.rows()[0]
        self.snapshot()
        register_search_policy(self.store, self.run_id, {"required_sources": ["GITCODE"]})
        weak_snapshot = self.snapshot([case["case_id"]], url="https://gitcode.com/synthetic/weak/pull/1", status="PARTIAL")
        work = next(work for work in self.plan()["work_items"] if work["snapshot_id"] == weak_snapshot["snapshot_id"])
        weak = {**self.useful_search(case, weak_snapshot), "work_id": work["work_id"]}
        next(fact for fact in weak["fact_comparisons"] if fact["category"] == "TECHNICAL_CONCLUSION").update(
            relation="NAME_ONLY", reason="Only a generic mechanism name; no specific technical support")
        planned = self.first(self.plan([weak]))
        self.assertEqual(planned["insufficient_candidate_judgment_ids"], [weak["judgment_id"]])
        self.assertTrue(planned["search_control"]["search_allowed"])
        self.assertFalse(planned["search_control"]["satisfied"])
        self.assertNotIn(weak_snapshot["snapshot_id"], planned["selected_snapshot_ids"])
        self.assertEqual(weak["event_relation"], "UNDETERMINED")
        self.assertEqual(len(self.store.records(self.run_id, "references")), 2)
        next_snapshot = self.snapshot([case["case_id"]], url="https://gitcode.com/synthetic/next/pull/2", status="PARTIAL")
        planned = self.first(self.plan([weak]))
        self.assertIn(next_snapshot["snapshot_id"], planned["selected_snapshot_ids"])
        self.assertNotIn(weak_snapshot["snapshot_id"], planned["selected_snapshot_ids"])
        self.assertFalse(planned["search_control"]["search_allowed"])

    def test_incomplete_or_mock_weak_candidate_stays_pending_instead_of_being_skipped(self):
        case = self.rows(link=False)[0]
        snapshot = self.snapshot([case["case_id"]])
        incomplete = self.useful_search(case, snapshot)
        incomplete["self_check"]["passed"] = False
        for judgment in (incomplete, {**self.useful_search(case, snapshot), "model_mode": "mock"}):
            with self.subTest(mock=judgment.get("model_mode") == "mock"):
                planned = self.first(self.plan([judgment]))
                self.assertEqual(planned["insufficient_candidate_judgment_ids"], [])
                self.assertEqual(planned["selected_snapshot_ids"], [snapshot["snapshot_id"]])
                self.assertFalse(planned["search_control"]["search_allowed"])

    def test_explicit_source_target_does_not_select_unneeded_positive_discovery(self):
        case = self.rows(link=False)[0]
        wiki = self.snapshot([case["case_id"]])
        gitcode = self.snapshot([case["case_id"]], url="https://gitcode.com/synthetic/target/pull/1", status="PARTIAL")
        register_search_policy(self.store, self.run_id, {"required_sources": ["GITCODE"]})
        judgments = [self.useful_search(case, wiki), {**self.useful_search(case, gitcode), "judgment_id": "target"}]
        planned = self.first(self.plan(judgments))
        self.assertTrue(planned["search_control"]["satisfied"])
        self.assertEqual(planned["selected_snapshot_ids"], [gitcode["snapshot_id"]])
        self.assertEqual(planned["search_control"]["usable_evidence_count"], 1)


if __name__ == "__main__":
    unittest.main()
