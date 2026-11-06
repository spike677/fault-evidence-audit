"""Synthetic collection observations and Agent-owned search provenance."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from faultaudit.capture_quality import capture_quality, capture_quality_errors, collection_observation_instructions
from faultaudit.contracts import EvidencePackage
from faultaudit.importers import import_cases
from faultaudit.pipeline import import_into
from faultaudit.search_guidance import search_guidance, validate_search_trace
from faultaudit.store import Store
from faultaudit.wiki_checks import wiki_plan


def observation(kind="BODY", **changes):
    return {"page_kind": kind, "requested_url": "https://wiki.example.invalid/domains/1/WIKI123",
        "final_url": "https://wiki.example.invalid/domains/1/WIKI123", "title": "Synthetic issue",
        "body_locator": "main article / root-cause section", "body_quotes": ["Buffer reuse caused stale values."],
        "observed_by": "synthetic browser observation", "observed_at": "2026-11-06T18:00:00+08:00",
        "tool_observation": "Synthetic visible body section was extracted, not only the heading.", **changes}


def package(**changes):
    return {"url": "https://wiki.example.invalid/domains/1/WIKI123", "title": "Synthetic issue",
        "artifact_type": "WIKI", "text": "Buffer reuse caused stale values.", "status": "COMPLETE",
        "components": {"body": "COMPLETE"}, "capture_observation": observation(), "is_synthetic": True, **changes}


class CaptureQualityTests(unittest.TestCase):
    def test_explicit_body_is_grounded_and_preserves_short_but_meaningful_text(self):
        value = EvidencePackage.model_validate(package()).model_dump()
        self.assertEqual(capture_quality(value, require_observation=True),
            {"status": "BODY", "usable_body": True, "needs_repair": False, "errors": []})

    def test_missing_observation_is_legacy_compatible_but_not_new_workflow_success(self):
        value = package(capture_observation=None)
        self.assertTrue(capture_quality(value)["usable_body"])
        strict = capture_quality(value, require_observation=True)
        self.assertFalse(strict["usable_body"])
        self.assertTrue(strict["needs_repair"])

    def test_index_title_shell_cannot_declare_complete_body(self):
        for kind in ("INDEX", "TITLE_ONLY", "RENDER_PENDING", "EXTRACTION_FAILED", "LOGIN", "FORBIDDEN", "UNRELATED"):
            with self.subTest(kind=kind):
                value = package(capture_observation=observation(kind, body_quotes=[]))
                result = capture_quality(value)
                self.assertFalse(result["usable_body"])
                self.assertIn("Non-body page cannot declare COMPLETE document/body capture", result["errors"])

    def test_partial_index_text_is_retained_but_cannot_satisfy_wiki(self):
        value = package(status="CONTENT_CAPTURED", components={"body": "PARTIAL"},
                        capture_observation=observation("INDEX", body_quotes=[]))
        result = capture_quality(value, require_observation=True)
        self.assertEqual(result["errors"], [])
        self.assertFalse(result["usable_body"])
        self.assertTrue(result["needs_repair"])
        self.assertEqual(value["text"], "Buffer reuse caused stale values.")

    def test_partial_body_can_support_observed_facts_without_claiming_full_capture(self):
        value = package(status="CONTENT_CAPTURED", components={"body": "PARTIAL"})
        self.assertTrue(capture_quality(value, require_observation=True)["usable_body"])
        self.assertEqual(value["status"], "CONTENT_CAPTURED")

    def test_title_only_quote_cannot_be_relabelled_body(self):
        value = package(text="Synthetic issue", capture_observation=observation(body_quotes=["Synthetic issue"]))
        self.assertFalse(capture_quality(value)["usable_body"])
        self.assertTrue(any("title" in error for error in capture_quality_errors(value)))
        value["capture_observation"]["title"] = ""
        self.assertFalse(capture_quality(value)["usable_body"])

    def test_title_only_text_cannot_use_a_title_substring_as_body(self):
        value = package(text="Synthetic issue", capture_observation=observation(body_quotes=["Synthetic"]))
        self.assertFalse(capture_quality(value, require_observation=True)["usable_body"])
        self.assertIn("BODY capture cannot use only the page title as body evidence", capture_quality_errors(value))

    def test_locator_quotes_time_and_actual_urls_are_checked(self):
        for changes in ({"body_locator": ""}, {"body_quotes": []}, {"body_quotes": ["invented"]},
                        {"observed_at": "2026-11-06"}, {"final_url": "https://example.invalid/other"},
                        {"observed_by": " "}, {"tool_observation": " "}):
            with self.subTest(changes=changes):
                self.assertTrue(capture_quality_errors(package(capture_observation=observation(**changes))))

    def test_failed_capture_needs_no_fake_body_observation(self):
        value = package(status="AUTH_REQUIRED", text="", capture_observation=None, components={"body": "NOT_FETCHED"})
        result = capture_quality(value, require_observation=True)
        self.assertFalse(result["usable_body"])
        self.assertEqual(result["errors"], [])

    def test_guidance_mentions_navigation_and_real_edge_login(self):
        text = collection_observation_instructions()
        self.assertIn("INDEX/TITLE_ONLY", text)
        self.assertIn("Edge", text)
        self.assertIn("user enters credentials", text)


class WikiQualityPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="quality-wiki-", dir=Path(__file__).parent)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "state")
        self.run = self.store.create_run({"is_synthetic": True})
        path = self.root / "source.json"
        path.write_text(json.dumps([{"统一ID": "SYN-QUALITY", "问题描述": "Synthetic buffer reuse fault",
            "wiki": package()["url"]}]), encoding="utf-8")
        imported = import_cases(path, source_kind="ORIGINAL_WEEKLY")
        import_into(self.store, self.run, imported)
        self.case = imported["cases"][0]

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_repeat_body_keeps_snapshot_identity_and_full_observation_history(self):
        first = self.store.ingest_evidence(self.run, package(case_ids=[self.case["case_id"]]))
        changed = package(case_ids=[self.case["case_id"]], capture_observation=observation(
            observed_at="2026-11-06T18:01:00+08:00", observed_by="synthetic second collector",
            tool_observation="Synthetic independent re-read of the same body."))
        second = self.store.ingest_evidence(self.run, changed)
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertEqual(len(self.store.records(self.run, "snapshots")), 1)
        self.assertEqual(self.store.events(self.run, "snapshot_superseded"), [])
        events = self.store.events(self.run, "evidence_ingested")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[-1]["capture_observation"], changed["capture_observation"])
        self.assertEqual(events[0]["capture_observation"]["observed_at"], "2026-11-06T18:00:00+08:00")
        self.assertEqual(second["capture_observation"], first["capture_observation"])
        self.assertEqual(self.store.verify_snapshot(second), [])

    def test_meaningful_body_observation_change_creates_new_snapshot(self):
        first = self.store.ingest_evidence(self.run, package(case_ids=[self.case["case_id"]]))
        second = self.store.ingest_evidence(self.run, package(case_ids=[self.case["case_id"]],
            capture_observation=observation(body_locator="main article / specific repair subsection")))
        self.assertNotEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertEqual(len(self.store.records(self.run, "snapshots")), 2)
        self.assertEqual(len(self.store.events(self.run, "snapshot_superseded")), 1)

    def test_alias_failure_then_identical_body_recovery_selects_latest_observation(self):
        first = self.store.ingest_evidence(self.run, package(retrieved_at="2026-11-06T18:00:00+08:00",
            case_ids=[self.case["case_id"]]))
        alias = package()["url"] + "#comment-1"
        failure = self.store.ingest_evidence(self.run, package(url=alias,
            retrieved_at="2026-11-06T18:01:00+08:00", text="", status="AUTH_REQUIRED",
            components={"body": "NOT_FETCHED"}, capture_observation=None,
            case_ids=[self.case["case_id"]]))
        self.assertEqual([s["snapshot_id"] for s in self.store.active_snapshots(self.run)], [failure["snapshot_id"]])
        recovered = self.store.ingest_evidence(self.run, package(retrieved_at="2026-11-06T18:02:00+08:00",
            capture_observation=observation(observed_at="2026-11-06T18:02:00+08:00"),
            case_ids=[self.case["case_id"]]))
        self.assertEqual(first["snapshot_id"], recovered["snapshot_id"])
        self.assertEqual([s["snapshot_id"] for s in self.store.active_snapshots(self.run)], [first["snapshot_id"]])
        self.assertEqual(len(self.store.records(self.run, "snapshots")), 2)
        self.assertEqual(len(self.store.events(self.run, "evidence_ingested")), 3)
        self.assertEqual({head["snapshot_id"] for head in self.store.records(self.run, "heads")}, {first["snapshot_id"]})

    def test_existing_legacy_title_is_not_promoted_in_structured_workflow(self):
        self.store.ingest_evidence(self.run, package(text="Synthetic issue", capture_observation=None,
            case_ids=[self.case["case_id"]]))
        self.assertEqual(wiki_plan(self.store, self.run, self.case)["status"], "FOUND")
        self.store.put(self.run, "xlsx_workflow", "config", {"run_id": self.run})
        plan = wiki_plan(self.store, self.run, self.case)
        self.assertEqual(plan["status"], "FETCH_REQUIRED")
        self.assertFalse(plan["checked"])
        self.assertFalse(plan["search_allowed"])
        self.assertEqual(plan["required_actions"][0]["action"], "REPAIR_WIKI_CAPTURE")
        self.assertEqual(plan["capture_quality_gaps"][0]["page_kind"], "UNASSESSED")

    def test_original_index_gets_repair_not_blind_search(self):
        self.store.put(self.run, "xlsx_workflow", "config", {"capture_quality_required": True})
        self.store.ingest_evidence(self.run, package(status="CONTENT_CAPTURED", components={"body": "PARTIAL"},
            capture_observation=observation("INDEX", body_quotes=[]), case_ids=[self.case["case_id"]]))
        plan = wiki_plan(self.store, self.run, self.case)
        self.assertEqual(plan["status"], "FETCH_REQUIRED")
        self.assertEqual(plan["required_actions"][0]["page_kind"], "INDEX")
        self.assertFalse(plan["search_allowed"])

    def test_actual_body_satisfies_wiki_without_confirming_customer_root(self):
        self.store.put(self.run, "xlsx_workflow", "config", {"capture_quality_required": True})
        self.store.ingest_evidence(self.run, package(case_ids=[self.case["case_id"]]))
        plan = wiki_plan(self.store, self.run, self.case)
        self.assertEqual(plan["status"], "FOUND")
        self.assertTrue(plan["checked"])
        self.assertFalse(plan["case_root_cause_confirmed"])


class SearchTraceTests(unittest.TestCase):
    def setUp(self):
        self.case = {"raw": {"问题描述": "Synthetic Q-model npu_mrope stale cache", "根因": "Possible buffer reuse"},
            "cell_locations": {"问题描述": "D2", "根因": "F2"}}
        self.response = {"outcome": "NO_MATCH", "search_facets": [
            {"kind": "operator", "value": "npu_mrope", "source_field": "问题描述", "source_cell": "D2",
             "source_quote": "Synthetic Q-model npu_mrope stale cache", "hypothesis": False}],
            "search_attempts": [{"round": 1, "query": "npu_mrope stale cache", "scope": "synthetic Wiki space",
                "reason": "Use exact operator and symptom before relaxing model", "executed": True,
                "checked_at": "2026-11-06T18:00:00+08:00"}]}

    def test_agent_queries_and_source_facets_are_validated_without_generating_keywords(self):
        self.assertEqual(validate_search_trace(self.case, self.response, required=True), [])
        guide = search_guidance(self.case)
        self.assertEqual(guide["max_rounds"], 3)
        self.assertNotIn("query", guide)
        self.assertIn("not a required filter", guide["instructions"])

    def test_fabricated_or_wrong_cell_facets_are_rejected(self):
        for change in ({"value": "rope"}, {"source_cell": "D3"}, {"source_quote": "invented"}):
            response = copy.deepcopy(self.response)
            response["search_facets"][0].update(change)
            self.assertTrue(validate_search_trace(self.case, response, required=True))

    def test_old_attribution_stays_a_hypothesis(self):
        response = copy.deepcopy(self.response)
        response["search_facets"] = [{"kind": "root_claim", "value": "buffer reuse", "source_field": "根因",
            "source_cell": "F2", "source_quote": "Possible buffer reuse", "hypothesis": False}]
        self.assertTrue(validate_search_trace(self.case, response, required=True))
        response["search_facets"][0]["hypothesis"] = True
        self.assertEqual(validate_search_trace(self.case, response, required=True), [])

    def test_queries_have_bounded_unique_increasing_actual_rounds(self):
        for change in ({"round": 4}, {"round": True}, {"executed": False}, {"query": ""}, {"checked_at": "2026-11-06"}):
            response = copy.deepcopy(self.response)
            response["search_attempts"][0].update(change)
            self.assertTrue(validate_search_trace(self.case, response, required=True))
        response = copy.deepcopy(self.response)
        response["search_attempts"] *= 2
        self.assertTrue(validate_search_trace(self.case, response, required=True))

    def test_login_blocking_can_record_no_site_queries_without_faking_no_match(self):
        response = {"outcome": "BLOCKED", "search_facets": [], "search_attempts": [],
            "input_gap": "Wiki entry requires user login; no station search executed"}
        self.assertEqual(validate_search_trace(self.case, response, required=True), [])
        response["outcome"] = "NO_MATCH"
        self.assertTrue(validate_search_trace(self.case, response, required=True))

    def test_legacy_responses_remain_compatible_until_new_dispatch_requires_trace(self):
        self.assertEqual(validate_search_trace(self.case, {"outcome": "NO_MATCH"}), [])
        self.assertTrue(validate_search_trace(self.case, {"outcome": "NO_MATCH"}, required=True))


if __name__ == "__main__":
    unittest.main()
