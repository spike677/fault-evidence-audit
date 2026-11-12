"""Evidence binding and scope checks for the R4 pilot data; no device/client."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rc128_mechanism_cases as cases


class MechanismCasesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = cases.mechanism_cases()
        cls.definitions = json.loads((cases.R3 / "condition_definitions.json").read_text(encoding="utf-8"))
        cls.by_definition = {(d["system"], d["condition_id"]): d for d in cls.definitions["definitions"]}
        cls.resources = {json.loads(line)["resource_id"]: json.loads(line)
                         for line in (cases.R3 / "resource_audit.jsonl").read_text(encoding="utf-8").splitlines()}

    def test_all_representatives_are_independent_public_cases(self):
        self.assertEqual({x["task_id"] for x in self.cards}, set(cases.REPRESENTATIVE_TASK_IDS))
        self.assertEqual(len(self.cards), len({x["issue_key"] for x in self.cards}))
        for card in self.cards:
            self.assertEqual(card["entity_type"], "INDEPENDENT_PUBLIC_TECHNICAL_CASE")
            self.assertEqual(card["evidence_level"], "CODE_OBSERVED_WITH_LIMITS")
            self.assertEqual(card["event_relation"], "UNDETERMINED")
            self.assertFalse(card["weekly_event_confirmed"])
            self.assertFalse(card["hardware_validated"])
            self.assertFalse(card["formal_adoption"])

    def test_exact_markers_exist_in_declared_archived_files(self):
        for card in self.cards:
            for marker in card["locator_markers"]:
                with self.subTest(issue=card["issue_key"], file=marker["file"]):
                    self.assertIn(marker["resource_id"], card["resource_ids"])
                    self.assertIn(marker["resource_id"], self.resources)
                    text = (cases.R3 / marker["file"]).read_text(encoding="utf-8")
                    self.assertIn(marker["marker"], text)
                    self.assertTrue(marker["claim_scope"])

    def test_each_reviewed_mount_keeps_every_frozen_predicate(self):
        for card in self.cards:
            for candidate in card["candidate_conditions"]:
                with self.subTest(issue=card["issue_key"], condition=candidate["condition_id"], mount=candidate["class_id"]):
                    original = self.by_definition[(candidate["system"], candidate["condition_id"])]
                    self.assertEqual(candidate["original_definition"], original)
                    self.assertIn(candidate["semantic_applicability"], {"APPLICABLE", "PARTIAL", "UNKNOWN", "NOT_APPLICABLE"})
                    for axis, key in [("requires", "requires_check"), ("skip_if", "skip_if_check")]:
                        expected = [text for mount, text in cases._flatten_predicates(original[axis])
                                    if mount in (None, candidate["class_id"])]
                        self.assertEqual([x["predicate"] for x in candidate[key]], expected)
                        self.assertTrue(all(x["status"] and x["reason"] for x in candidate[key]))
                    if candidate["system"] == "V4":
                        self.assertEqual(len(candidate["class_assessments"]), 1)

    def test_source_definitions_and_returned_cases_are_not_mutated(self):
        before = deepcopy(self.definitions)
        first = cases.mechanism_cases(self.definitions)
        first[0]["mechanism_claim"] = "changed by consumer"
        first[0]["candidate_conditions"][0]["original_definition"]["definition"] = "changed by consumer"
        self.assertEqual(self.definitions, before)
        self.assertEqual(cases.mechanism_cases()[0], self.cards[0])

    def test_dropped_frozen_requirement_fails_closed(self):
        definitions = deepcopy(self.definitions)
        next(x for x in definitions["definitions"] if x["system"] == "API42" and x["condition_id"] == "1.C.3")["requires"].append("new predicate")
        with self.assertRaisesRegex(ValueError, "exact checks"):
            cases.mechanism_cases(definitions)

    def test_design_roles_and_status_do_not_claim_execution(self):
        for card in self.cards:
            d = card["proposed_design"]
            self.assertIn(d["design_status"], {"DESIGN_READY", "NEEDS_FACTS", "CAPABILITY_BLOCKED"})
            self.assertEqual(d["execution_status"], "NOT_EXECUTED")
            self.assertTrue(d["target_path"] and d["baseline"] and d["oracle"])
            for variable in d["variables"]:
                self.assertIn(variable["role"], {"INPUT", "DERIVED", "CONTEXT", "EXECUTION_PROTOCOL"})
                self.assertTrue(variable["proposed_values"])

    def test_common_record_ids_do_not_merge_distinct_mechanisms(self):
        rc30 = [x for x in self.cards if x["task_id"] == "RC-030"]
        self.assertEqual(len(rc30), 3)
        self.assertEqual({r for x in rc30 for r in x["resource_ids"]}, {"GH12123", "GC-cann-ops-transformer-8752"})
        rc122 = [x for x in self.cards if x["task_id"] == "RC-122"]
        self.assertEqual(len(rc122), 2)
        self.assertNotEqual(rc122[0]["resource_ids"], rc122[1]["resource_ids"])

    def test_scale_word_does_not_establish_s7_and_ordinary_shape_does_not_establish_api13(self):
        scale = next(x for x in self.cards if x["task_id"] == "RC-029")
        s7 = next(c for c in scale["candidate_conditions"] if c["condition_id"] == "scale_structure")
        self.assertEqual(s7["class_id"], "S7")
        self.assertEqual(s7["semantic_applicability"], "UNKNOWN")
        for card in self.cards:
            for c in card["candidate_conditions"]:
                if c["system"] == "API42" and c["condition_id"].startswith("1.3"):
                    self.assertEqual(c["semantic_applicability"], "NOT_APPLICABLE")

    def test_topk_prs_unmerged_and_dtype_assert_is_not_value_assert(self):
        topk = [x for x in self.cards if x["task_id"] == "RC-099"]
        self.assertEqual(len(topk), 2)
        for card in topk:
            for resource in card["resource_ids"]:
                self.assertFalse(self.resources[resource]["merged"])
        whitelist = next(x for x in topk if x["issue_key"].endswith("floating-whitelist"))
        self.assertIn("没有assert权重数值", whitelist["observed_change"])
        patch = (cases.R3 / "evidence/decoded/PATCH-RC-099-15613-1.diff").read_text(encoding="utf-8")
        assertions = [line.strip() for line in patch.splitlines() if line.startswith("+    assert")]
        self.assertEqual(assertions, ["+    assert topk_weights.dtype == expected_dtype", "+    assert topk_ids.dtype == torch.int32"])

    def test_every_association_has_an_explicit_source_or_design_basis(self):
        actual = set()
        for card in self.cards:
            for c in card["candidate_conditions"]:
                actual.add((card["issue_key"], c["system"], c["condition_id"], c["class_id"]))
                self.assertIn(c["association_basis"], {
                    "OBSERVED_CONDITION", "STRUCTURAL_APPLICABILITY", "PROPOSED_TEST_ONLY", "UNKNOWN"})
                if c["association_basis"] in {"PROPOSED_TEST_ONLY", "UNKNOWN"}:
                    self.assertEqual(c["semantic_applicability"], "UNKNOWN")
                self.assertIn("NO_EXECUTION", c["association_scope"])
        self.assertEqual(actual, set(cases._ASSOCIATION_REVIEWS))

    def test_stress_design_and_internal_controls_are_not_observed_input_conditions(self):
        expected_unknown = {
            ("RC-002:gemm-precision-flag", "API42", "1.7.6"),
            ("RC-002:gemm-precision-flag", "V4", "intermediate_overflow"),
            ("RC-029:vscale-call-binding", "API42", "1.C.1"),
            ("RC-099:topk-prequant-dtype", "API42", "1.C.2"),
            ("RC-099:topk-floating-whitelist", "API42", "1.C.1"),
        }
        found = set()
        for card in self.cards:
            for c in card["candidate_conditions"]:
                key = (card["issue_key"], c["system"], c["condition_id"])
                if key in expected_unknown:
                    found.add(key)
                    self.assertEqual(c["semantic_applicability"], "UNKNOWN")
        self.assertEqual(found, expected_unknown)

    def test_stream_configuration_is_branch3_context_not_c4_input_classification(self):
        for card in self.cards:
            if card["task_id"] != "RC-122":
                continue
            for c in card["candidate_conditions"]:
                if c["system"] == "V4" and c["class_id"] == "C4":
                    self.assertEqual(c["semantic_applicability"], "UNKNOWN")
                    self.assertEqual(c["association_basis"], "UNKNOWN")
                    self.assertIn("Branch3", c["execution_branch_hint"])
                    self.assertTrue(all(x["status"] == "UNKNOWN" for x in c["requires_check"]))


if __name__ == "__main__":
    unittest.main()
