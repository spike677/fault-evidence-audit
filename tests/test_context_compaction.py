"""Compact wire projections retain semantic facts, raw inputs and dependencies."""
from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

from faultaudit.catalog_drafts import _check_request, compact_draft_context, prepare_draft
from faultaudit.investigation import investigation_plan
from faultaudit.store import AuditError, digest
from tests import test_catalog_drafts as fixtures


class DraftContextProjectionTests(unittest.TestCase):
    def context(self):
        source = {"case_id": "C1", "source_file": "synthetic.xlsx", "source_sha256": "source-hash",
            "sheet": "Cases", "row": 2, "external_id": "SYN-1", "source_kind": "LEGACY_TABLE",
            "raw": {"问题描述": "Q-model TP64 has stale data", "根因": "Possible reuse before completion"},
            "cell_locations": {"问题描述": "D2", "根因": "F2"}}
        provenance = {"relation": "LEGACY_TABLE_LINKED", "trace": {"case_id": "C1", "discovered_by": "original-importer",
            "source_file": "synthetic.xlsx", "reference_location": "Cases!G2"}}
        refs = [{"segment_id": "S1:s1", "quote": "buffer reused before completion"}]
        fact = {"fact_id": "F1", "snapshot_id": "S1", "summary_task_id": "SUM1", "issue_label": "Issue A",
            "issue_index": 0, "field": "mechanism", "value": "buffer reused before completion", "evidence": refs,
            "url": "https://example.invalid/wiki/1", "capture_status": "CONTENT_CAPTURED",
            "producer": "actual-synthetic-author", "case_root_cause_confirmed": False}
        counterfact = {**fact, "fact_id": "F2", "field": "verification", "value": "author did not reproduce on TP64",
            "evidence": [{"segment_id": "S1:s2", "quote": "not reproduced on TP64"}]}
        candidate = {"fact_id": "F1", "judgment_id": "J1", "status": "ROOT_CAUSE_CANDIDATE",
            "claim_support": "PARTIAL", "event_relation": "UNDETERMINED", "observation_scope": "CAPTURED_CONTENT",
            **{key: fact[key] for key in ("value", "evidence", "url", "snapshot_id", "issue_label")}}
        source_record = {key: source[key] for key in ("case_id", "source_file", "sheet", "row", "cell_locations")}
        case = {"case_id": "C1", **{key: source[key] for key in ("source_file", "sheet", "row", "external_id")},
            "source_case": source, "provenance": [provenance], "search_control": {"satisfied": True, "search_allowed": False},
            "source_root_cause_notice": "IMPORTED_ATTRIBUTION_ONLY_NOT_VERIFIED_BY_THIS_PLAN",
            "root_cause_candidates": [{"work_id": "W1", **candidate}], "gaps": ["CUSTOMER_EVENT_UNDETERMINED"],
            "issues": [{"code": "KNOWN_CONFLICT", "judgment_ids": ["J1"]}], "group_confirmation": None,
            "required_actions": [{"action": "EXTRACT_FACTS", "description": "synthetic queue description " * 80}],
            "agent_next_steps": ["READ_ALL_SELECTED_RESOURCES_WITH_DISCUSSION_AND_APPLICABLE_FIX"]}
        work = {"work_id": "W1", "case_ids": ["C1"], "snapshot_id": "S1", "input_hash": "work-input",
            "issue_scope": {"scope": "ISSUE", "applicable_issue_ids": ["Issue A"]}, "independent_fact_ids": ["F1", "F2"],
            "root_cause_candidates": [candidate], "source_records": [source_record], "provenance": [provenance],
            "excluded_results": [{"judgment_id": "J2", "reason": "Explicit counterevidence retained"}],
            "member_relations": {"C1": "LEGACY_TABLE_LINKED"}, "actions": ["EXTRACT_FACTS", "MATCH_CATALOG"]}
        return {"selected_case_ids": ["C1"], "catalog": [{"item_id": f"BASE-{i}", "description": f"Pattern {i}",
            "mechanism": "original mechanism with units32b", "raw": {"故障原因": "原始机制", "案例链接": "https://example.invalid/base"}}
            for i in range(30)], "baseline_identity": {"source_sha256": "frozen-hash"},
            "cases": [case], "work_items": [work], "resources": [{"url": fact["url"], "case_ids": ["C1"],
                "snapshot_id": "S1", "capture_status": "CONTENT_CAPTURED", "actor": "actual-synthetic-collector",
                "captured_components": {"body": "PARTIAL"}, "gaps": ["DISCUSSION_NOT_CAPTURED"],
                "summary_reading_scope": {"scope": "CAPTURED_CONTENT", "segment_ids": ["S1:s1", "S1:s2"]},
                "summary_requirements": {"instructions": "synthetic duplicated summary instruction " * 80},
                "resource_summary_card_ids": ["CARD1"], "independent_fact_ids": ["F1", "F2"]}],
            "independent_technical_facts": [fact, counterfact],
            "current_mappings": [{"case_id": "C1", "overall": "UNDETERMINED", "short_reason": "Preserve mapping uncertainty"}]}

    def test_full_library_source_records_and_counterfacts_remain_unchanged(self):
        context = self.context()
        before = copy.deepcopy(context)
        compact = compact_draft_context(context)
        self.assertEqual(context, before)
        self.assertEqual(compact["catalog"], context["catalog"])
        self.assertEqual(len({item["item_id"] for item in compact["catalog"]}), 30)
        self.assertEqual(compact["cases"][0]["source_case"], context["cases"][0]["source_case"])
        self.assertEqual(compact["independent_technical_facts"], context["independent_technical_facts"])
        self.assertEqual(compact["current_mappings"], context["current_mappings"])
        for key in ("search_control", "source_root_cause_notice", "issues", "gaps", "provenance"):
            self.assertEqual(compact["cases"][0][key], context["cases"][0][key])
        self.assertEqual(compact["resources"][0]["actor"], "actual-synthetic-collector")
        self.assertEqual(compact["resources"][0]["captured_components"], {"body": "PARTIAL"})
        self.assertEqual(compact["resources"][0]["gaps"], ["DISCUSSION_NOT_CAPTURED"])
        self.assertLess(len(json.dumps(compact)), len(json.dumps(context)) * 0.8)

    def test_candidate_references_resolve_exact_text_in_registry_with_scope_preserved(self):
        context = self.context()
        compact = compact_draft_context(context)
        work = compact["work_items"][0]
        self.assertNotIn("source_records", work)
        self.assertNotIn("provenance", work)
        candidate = work["root_cause_candidates"][0]
        fact = next(fact for fact in compact["independent_technical_facts"] if fact["fact_id"] == candidate["fact_id"])
        self.assertEqual(fact["value"], "buffer reused before completion")
        self.assertEqual(fact["evidence"], context["work_items"][0]["root_cause_candidates"][0]["evidence"])
        self.assertNotIn("value", candidate)
        self.assertNotIn("evidence", candidate)
        for key in ("judgment_id", "status", "claim_support", "event_relation", "observation_scope"):
            self.assertEqual(candidate[key], context["work_items"][0]["root_cause_candidates"][0][key])
        self.assertEqual(work["issue_scope"], context["work_items"][0]["issue_scope"])
        self.assertEqual(work["excluded_results"], context["work_items"][0]["excluded_results"])

    def test_unique_provenance_foreign_source_or_different_candidate_text_is_not_discarded(self):
        context = self.context()
        work = context["work_items"][0]
        unique = {"relation": "LINK_DISCOVERED", "trace": {"discovered_by": "synthetic-second-actor"}}
        foreign = {"case_id": "C2", "source_file": "foreign-source.xlsx", "row": 5}
        work["provenance"].append(unique)
        work["source_records"].append(foreign)
        work["root_cause_candidates"][0]["value"] = "Different statement is not an exact registry duplicate"
        result = compact_draft_context(context)["work_items"][0]
        self.assertEqual(result["provenance"], [unique])
        self.assertEqual(result["source_records"], [foreign])
        self.assertEqual(result["root_cause_candidates"][0]["value"], work["root_cause_candidates"][0]["value"])

    def test_repeated_mapping_quotes_are_losslessly_interned_with_all_rows_and_actors(self):
        context = self.context()
        refs = copy.deepcopy(context["independent_technical_facts"][0]["evidence"])
        context["current_mappings"] = [{"task_id": "MAP1", "case_id": "C1", "model_id": "synthetic-agent",
            "review_status": "NOT_REQUIRED", "overall": "UNDETERMINED",
            "catalog_results": [{"item_id": f"BASE-{i}", "result": "UNDETERMINED", "reason": f"Retained item reason {i}",
                "evidence": refs} for i in range(30)]}]
        before = copy.deepcopy(context)
        compact = compact_draft_context(context)
        mapping = compact["current_mappings"][0]
        self.assertEqual((mapping["model_id"], mapping["review_status"]), ("synthetic-agent", "NOT_REQUIRED"))
        self.assertEqual(len(mapping["catalog_results"]), 30)
        self.assertEqual(len(compact["mapping_evidence"]), 1)
        restored = []
        for row in mapping["catalog_results"]:
            value = dict(row)
            value["evidence"] = [compact["mapping_evidence"][ref_id] for ref_id in value.pop("evidence_ref_ids")]
            restored.append(value)
        self.assertEqual(restored, context["current_mappings"][0]["catalog_results"])
        self.assertEqual(context, before)
        self.assertEqual(compact_draft_context(compact), compact)


class CompactDraftDependencyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CatalogDraftTests()
        self.fixture.setUp()
        self.store, self.run = self.fixture.store, self.fixture.run

    def tearDown(self):
        self.fixture.tearDown()

    def test_current_request_uses_compact_context_and_still_validates(self):
        request = prepare_draft(self.store, self.run, [self.fixture.cases[0]["case_id"]])["request"]
        self.assertEqual(request["payload"]["context_projection"], "catalog-fact-registry-1")
        self.assertEqual(_check_request(self.store, self.run, request), request["payload"])
        response = self.fixture.response(request)
        self.assertEqual(self.fixture.validate(request, response)["status"], "VALID_DRAFT")

    def test_fact_content_change_including_counterfact_invalidates_the_old_request(self):
        case_id = self.fixture.cases[0]["case_id"]
        request = prepare_draft(self.store, self.run, [case_id])["request"]
        plan = investigation_plan(self.store, self.run)
        changed = copy.deepcopy(plan)
        changed["independent_technical_facts"][0]["value"] = "New contradictory fact must invalidate the old request"
        with patch("faultaudit.catalog_drafts.investigation_plan", return_value=changed):
            with self.assertRaisesRegex(AuditError, "inputs are stale"):
                _check_request(self.store, self.run, request)
        self.assertEqual(digest(_check_request(self.store, self.run, request)), digest(request["payload"]))


if __name__ == "__main__":
    unittest.main()
