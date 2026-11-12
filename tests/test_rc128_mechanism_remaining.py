"""Registration and evidence-boundary checks, without running fault designs."""

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rc128_mechanism_remaining as remaining


class RemainingReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = remaining.all_reviews()
        cls.by_id = {r["task_id"]: r for r in cls.rows}
        cls.issues = [i for r in cls.rows for i in r["issues"]]
        cls.relations = {
            json.loads(line)["relation_id"]
            for line in (remaining.R3 / "failure_relations.jsonl").read_text(encoding="utf-8").splitlines()
        }

    def test_exact_registration_and_exclusion(self):
        expected = {f"RC-{n:03}" for n in range(1, 129)} - remaining.EXCLUDED_TASK_IDS
        self.assertEqual(set(self.by_id), expected)
        self.assertEqual(len(self.rows), 121)
        for task_id in remaining.EXCLUDED_TASK_IDS:
            self.assertIsNone(remaining.review(task_id))

    def test_every_split_retains_valid_frozen_source(self):
        keys = [i["issue_key"] for i in self.issues]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(keys), 140)
        for issue in self.issues:
            self.assertIn(issue["source_relation_id"], self.relations)
            self.assertTrue(issue["source_evidence_ids"])
            self.assertTrue(issue["mechanism_summary"])
            self.assertTrue(issue["expected_relation"])
            self.assertTrue(issue["consumer"])
            self.assertTrue(issue["design"]["reference"])
            self.assertTrue(issue["design"]["checks"])

    def test_designs_are_unexecuted_and_incomplete_parameters_remain_unknown(self):
        for row in self.rows:
            self.assertEqual(row["execution_status"], "NOT_RUN")
            self.assertFalse(row["manual_accept_created"])
            self.assertFalse(row["formal_adoption"])
            self.assertFalse(row["hardware_validated"])
            self.assertEqual(row["admission"], "NOT_EVALUATED")
            for public in row["independent_public_observations"]:
                self.assertFalse(public["used_as_weekly_root_cause"])
                self.assertEqual(public["weekly_event_relation"], "UNDETERMINED")
        for issue in self.issues:
            self.assertIn(issue["evidence_level"], {"source_declared", "logic_hypothesis", "unknown"})
            self.assertEqual(issue["design"]["status"], "NEEDS_FACTS")
            self.assertEqual(issue["design"]["execution_status"], "NOT_RUN")
            self.assertIsNone(issue["design"]["generated_parameters"])
            self.assertIsNone(issue["design"]["pass_fail"])

    def test_condition_proposals_never_turn_into_coverage(self):
        defs = remaining._sources()[-1]
        for issue in self.issues:
            for cond in issue["suggested_conditions"]:
                definition = defs[(cond["system"], cond["condition_id"])]
                self.assertEqual(cond["status"], "UNKNOWN")
                self.assertFalse(cond["counts_as_verified_coverage"])
                self.assertTrue(cond["requires_check"])
                if cond["system"] == "V4":
                    self.assertIn(cond["class_id"], definition["class_ids"])
                    self.assertEqual({r["class_id"] for r in cond["requires_check"]}, {cond["class_id"]})
                if cond["system"] == "API42" and cond["condition_id"].startswith("1.3."):
                    self.assertEqual(issue["source_relation_id"], "RC-023:REL-01")

    def test_no_parameter_labels_inferred_from_nan_or_determinism_symptoms(self):
        all_conditions = {(c["system"], c["condition_id"]) for i in self.issues for c in i["suggested_conditions"]}
        self.assertNotIn(("API42", "1.7.2"), all_conditions)
        self.assertNotIn(("V4", "special_values"), all_conditions)
        self.assertNotIn(("API42", "1.C.5"), all_conditions)
        self.assertNotIn(("V4", "minus_one"), all_conditions)

    def test_independent_subissues_do_not_inherit_numeric_modes(self):
        row104 = self.by_id["RC-104"]["issues"]
        self.assertEqual(len(row104), 4)
        self.assertEqual(row104[0]["original30_comparison"]["mode_ids"], ["M001"])
        for issue in row104[1:]:
            self.assertEqual(issue["original30_comparison"]["mode_ids"], [])
        row65 = self.by_id["RC-065"]["issues"]
        self.assertEqual(len(row65), 3)
        self.assertEqual(row65[0]["original30_comparison"]["mode_ids"], [])
        self.assertFalse(row65[0]["suggested_conditions"])
        self.assertTrue(row65[1]["suggested_conditions"])
        self.assertTrue(row65[2]["suggested_conditions"])

    def test_corrected_original_claims_and_transcription_conflict_remain_visible(self):
        for n in (37, 55, 56, 57, 83, 121):
            row = self.by_id[f"RC-{n:03}"]
            self.assertTrue(row["source_corrections"])
        self.assertIn("人脸", self.by_id["RC-037"]["issues"][0]["mechanism_summary"])
        self.assertIn("0.42", self.by_id["RC-055"]["issues"][0]["mechanism_summary"])
        self.assertIn("单batch", self.by_id["RC-056"]["issues"][0]["mechanism_summary"])
        self.assertIn("index_add", self.by_id["RC-083"]["issues"][0]["mechanism_summary"])
        row128 = self.by_id["RC-128"]
        self.assertIn("初始化的空间", row128["original_claim"]["reported_root_cause"])
        self.assertIn("转录冲突", row128["issues"][0]["design"]["unknowns"][0])

    def test_missing_fault_operator_never_gets_a_tensor_case(self):
        for n in (3, 4, 5, 15, 36, 37, 40, 41, 50, 52, 55, 56, 57, 59, 63, 68, 79, 89, 95, 96, 98, 101, 126):
            issue = self.by_id[f"RC-{n:03}"]["issues"][0]
            self.assertEqual(issue["design"]["analysis_scope"], "FACT_COLLECTION_ONLY")
            self.assertEqual(issue["design"]["status"], "NEEDS_FACTS")
            self.assertFalse(issue["suggested_conditions"])

    def test_returned_review_cannot_mutate_frozen_cache(self):
        row = remaining.review(65)
        row["issues"][0]["source_evidence_ids"].clear()
        row["issues"][1]["original30_comparison"]["mode_ids"].clear()
        row["original_claim"]["description"] = "mutated"
        again = remaining.review("RC065")
        self.assertTrue(again["issues"][0]["source_evidence_ids"])
        self.assertTrue(again["issues"][1]["original30_comparison"]["mode_ids"])
        self.assertNotEqual(again["original_claim"]["description"], "mutated")


if __name__ == "__main__":
    unittest.main()
