"""Automatic pattern counts with explicit batch limits kept as an opt-in."""
from __future__ import annotations

import copy
import unittest

from faultaudit.catalog_drafts import prepare_draft, validate_draft
from faultaudit.store import AuditError
from tests import test_catalog_drafts as fixtures


class CatalogDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CatalogDraftTests()
        self.fixture.setUp()
        self.store, self.run = self.fixture.store, self.fixture.run
        self.case_ids = [case["case_id"] for case in self.fixture.cases]

    def tearDown(self):
        self.fixture.tearDown()

    def request(self, expected=None):
        prepared = prepare_draft(self.store, self.run, self.case_ids, expected)
        self.assertEqual(prepared["status"], "READY_FOR_AGENT")
        return prepared["request"]

    def test_default_auto_mode_accepts_agent_selected_addition_count(self):
        request = prepare_draft(self.store, self.run, self.case_ids)["request"]
        self.assertIsNone(request["payload"]["expected_additions"])
        response = self.fixture.response(request)
        first = validate_draft(self.store, self.run, request, response)
        self.assertEqual((first["status"], first["addition_count"]), ("VALID_DRAFT", 1))
        self.assertIsNone(first["expected_additions"])
        # Count validation does not force a previously assumed quota. Semantic
        # pattern abstraction is still the Agent's responsibility.
        second = copy.deepcopy(response["proposals"][0])
        second.update(proposal_id="SYN-P2")
        second["row"]["pattern_name"] = "另一合成模式（测试自主数量）"
        response["proposals"].append(second)
        result = validate_draft(self.store, self.run, request, response)
        self.assertEqual((result["status"], result["addition_count"], result["case_count"]), ("VALID_DRAFT", 2, 1))

    def test_auto_mode_can_return_no_change_without_an_addition(self):
        request = self.request()
        response = self.fixture.response(request)
        response["proposals"][0].update(action="NO_CHANGE")
        result = validate_draft(self.store, self.run, request, response)
        self.assertEqual(result["status"], "VALID_DRAFT")
        self.assertEqual((result["addition_count"], result["merged_preview_count"]), (0, 2))

    def test_auto_mode_can_classify_into_an_existing_pattern(self):
        request = self.request()
        response = self.fixture.response(request)
        proposal = response["proposals"][0]
        proposal.update(action="APPEND_CASE", target_item_id="BASE-000")
        proposal["coverage_comparisons"][0]["relation"] = "SAME_PATTERN"
        result = validate_draft(self.store, self.run, request, response)
        self.assertEqual((result["status"], result["addition_count"]), ("VALID_DRAFT", 0))
        self.assertFalse(result["formal_catalog_updated"])
        self.assertFalse(result["human_accept_created"])

    def test_explicit_count_including_zero_is_still_enforced(self):
        for expected in (0, 3):
            with self.subTest(expected=expected):
                request = self.request(expected)
                response = self.fixture.response(request)
                result = validate_draft(self.store, self.run, request, response)
                self.assertEqual(result["status"], "BLOCKED")
                self.assertIn(f"Expected {expected} ADD proposals, received 1", result["errors"])
        request = self.request(0)
        response = self.fixture.response(request)
        response["proposals"][0]["action"] = "NO_CHANGE"
        self.assertEqual(validate_draft(self.store, self.run, request, response)["status"], "VALID_DRAFT")

    def test_auto_mode_keeps_complete_library_and_case_coverage_gates(self):
        request = self.request()
        response = self.fixture.response(request)
        response["proposals"][0]["coverage_comparisons"].pop()
        result = validate_draft(self.store, self.run, request, response)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("every frozen item" in error for error in result["errors"]))

    def test_invalid_explicit_counts_are_not_auto_mode(self):
        for value in (True, -1, "auto"):
            with self.subTest(value=value):
                with self.assertRaises(AuditError):
                    self.request(value)


if __name__ == "__main__":
    unittest.main()
