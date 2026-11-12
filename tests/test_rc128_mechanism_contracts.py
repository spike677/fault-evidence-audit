"""Synthetic, offline mechanism-contract regressions; no generated bundle needed."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from faultaudit.trigger_design import DesignCard, DesignVariable
from faultaudit.trigger_sparse import LabelLink, Scenario
from rc128_mechanism_contracts import MechanismAnalysis, validate_analysis


def synthetic():
    definitions = [{
        "scheme": "V4", "definition_version": "SYNTHETIC-V4-v1", "id": "S5",
        "definition": "A source shape may enter a tail path.",
        "requires": ["The real target has a tail predicate."],
        "skip_if": ["The target has no tail semantics."],
        "allowed_fact_roles": ["INPUT_SHAPE", "DERIVED_CONTROL"],
        "construction_ids": ["SYNTHETIC-TAIL-CODE"],
        "constructions": [{"id": "SYNTHETIC-TAIL-CODE", "definition": "Propose a shape around the real tile."}],
        "guides": [{"guide_id": "SYNTHETIC-GUIDE", "category_id": "S5"}],
    }]
    record = {
        "analysis_id": "RC-SYNTHETIC:issue-A:mechanism-1", "task_id": "RC-SYNTHETIC", "subproblem_id": "issue-A",
        "source_claims": [{"claim_id": "C1", "task_id": "RC-SYNTHETIC", "subproblem_id": "issue-A",
                           "statement": "The handoff reports a size-sensitive tail failure.",
                           "basis": "SOURCE_DECLARED", "evidence_ids": ["E1"]}],
        "mechanism": {"statement": "The reported mechanism is unconfirmed tail handling.", "source_claim_ids": ["C1"]},
        "condition_facts": [{"fact_id": "F1", "statement": "The source reports a shape-dependent tail.",
                             "role": "INPUT_SHAPE", "basis": "SOURCE_DECLARED", "source_claim_ids": ["C1"]}],
        "selected_labels": [{"scheme": "V4", "definition_version": "SYNTHETIC-V4-v1", "trigger_id": "S5",
                             "semantic_applicability": "PARTIAL",
                             "construction_feasibility": {"status": "UNKNOWN", "reason": "No executor observation."},
                             "condition_fact_ids": ["F1"],
                             "predicate_checks": [
                                 {"clause_role": "INCLUSION", "clause": definitions[0]["definition"],
                                  "result": "UNKNOWN", "condition_fact_ids": []},
                                 {"clause_role": "INCLUSION", "clause": definitions[0]["requires"][0],
                                  "result": "UNKNOWN", "condition_fact_ids": []},
                                 {"clause_role": "EXCLUSION", "clause": definitions[0]["skip_if"][0],
                                  "result": "UNKNOWN", "condition_fact_ids": []}],
                             "construction_checks": []}],
        "scenarios": [{"scenario_id": "local-A", "title": "One source issue", "condition_fact_ids": ["F1"],
                       "reason": "Reported together in this one source claim, with no reproduction."}],
        "label_links": [{"scheme": "V4", "definition_version": "SYNTHETIC-V4-v1", "trigger_id": "S5",
                         "detail_ids": ["RC-SYNTHETIC:issue-A:mechanism-1"], "scenario_ids": ["local-A"],
                         "condition_fact_ids": ["F1"], "construction_ids": []}],
        "design_cards": [{"card_id": "CARD1", "assessment_id": "RC-SYNTHETIC:issue-A:mechanism-1",
                          "scenario_id": "local-A", "status": "NEEDS_FACTS", "category_ids": ["S5"],
                          "construction_ids": [], "guide_ids": [], "condition_fact_ids": ["F1"],
                          "variables": [{"name": "legal shape", "kind": "INPUT", "proposed_values": ["symbolic T-1, T, T+1"],
                                         "condition_fact_ids": ["F1"], "guide_ids": [],
                                         "reason": "Proposed boundary values; no historical input is asserted."}],
                          "reference": "Design a serial mathematical reference after the contract is known.",
                          "target_path": "The target tail path and full predicate are still unknown.",
                          "checks": ["Check legality and path predicate before comparing against the serial reference."],
                          "required_capabilities": ["Preserve legal shape values at the real target call."],
                          "capability_gaps": ["Executor and real tile have not been checked."],
                          "unknowns": ["Real tile size and target legality."],
                          "execution_status": "NOT_RUN", "execution_implemented": False, "path_coverage": "DESIGN_ONLY"}],
        "mode_comparisons": [], "mode_decision": {"action": "PENDING", "reason": "No independent baseline relation decided."},
        "adoption_status": "SUGGESTION_ONLY", "formal_adoption": False,
    }
    return record, definitions, {"E1", "E2"}


def unlabelled():
    record, definitions, evidence = synthetic()
    record["selected_labels"] = []
    record["scenarios"] = []
    record["label_links"] = []
    card = record["design_cards"][0]
    card["scenario_id"] = ""
    card["category_ids"] = []
    return record, definitions, evidence


def make_applicable(record):
    label = record["selected_labels"][0]
    label["semantic_applicability"] = "APPLICABLE"
    for check in label["predicate_checks"]:
        check["result"] = "MET" if check["clause_role"] == "INCLUSION" else "NOT_MET"
        check["condition_fact_ids"] = ["F1"]


class MechanismContractTests(unittest.TestCase):
    def errors(self, record, definitions, evidence):
        return validate_analysis(record, definitions, evidence)

    def codes(self, record, definitions, evidence):
        return {item["code"] for item in self.errors(record, definitions, evidence)}

    def test_native_models_are_reused(self):
        record, definitions, evidence = synthetic()
        parsed = MechanismAnalysis.model_validate(record)
        self.assertIsInstance(parsed.scenarios[0], Scenario)
        self.assertIsInstance(parsed.label_links[0], LabelLink)
        self.assertIsInstance(parsed.design_cards[0], DesignCard)
        self.assertIsInstance(parsed.design_cards[0].variables[0], DesignVariable)
        self.assertEqual(self.errors(record, definitions, evidence), [])

    def test_validation_does_not_mutate_its_inputs(self):
        record, definitions, evidence = synthetic()
        before = deepcopy((record, definitions, evidence))
        self.assertEqual(self.errors(record, definitions, evidence), [])
        self.assertEqual((record, definitions, evidence), before)

    def test_partial_with_every_predicate_unknown_is_legal(self):
        record, definitions, evidence = synthetic()
        self.assertTrue(all(c["result"] == "UNKNOWN" for c in record["selected_labels"][0]["predicate_checks"]))
        self.assertEqual(self.errors(record, definitions, evidence), [])

    def test_each_claim_binds_task_and_subproblem(self):
        for key in ("task_id", "subproblem_id"):
            record, definitions, evidence = synthetic()
            record["source_claims"][0][key] = "another-issue"
            self.assertIn("CLAIM_SCOPE", self.codes(record, definitions, evidence))

    def test_mechanism_must_bind_local_source_claim(self):
        record, definitions, evidence = synthetic()
        record["mechanism"]["source_claim_ids"] = ["other-issue-claim"]
        self.assertIn("UNKNOWN_REFERENCE", self.codes(record, definitions, evidence))

    def test_claim_evidence_must_resolve(self):
        record, definitions, evidence = synthetic()
        record["source_claims"][0]["evidence_ids"] = ["uncaptured"]
        errors = self.errors(record, definitions, evidence)
        self.assertIn("UNKNOWN_REFERENCE", {x["code"] for x in errors})
        self.assertTrue(all(set(x) == {"code", "path", "message"} for x in errors))

    def test_duplicate_fact_and_claim_ids_rejected(self):
        for key in ("condition_facts", "source_claims"):
            record, definitions, evidence = synthetic()
            record[key].append(deepcopy(record[key][0]))
            self.assertIn("DUPLICATE_ID", self.codes(record, definitions, evidence))

    def test_unknown_is_explicit_without_positive_link_or_facts(self):
        record, definitions, evidence = unlabelled()
        unknown = deepcopy(synthetic()[0]["selected_labels"][0])
        unknown["semantic_applicability"] = "UNKNOWN"
        unknown["condition_fact_ids"] = []
        record["selected_labels"] = [unknown]
        self.assertEqual(self.errors(record, definitions, evidence), [])

    def test_no_positive_label_still_has_needs_facts_card(self):
        record, definitions, evidence = unlabelled()
        self.assertEqual(self.errors(record, definitions, evidence), [])
        record["design_cards"][0]["status"] = "DESIGN_READY"
        self.assertIn("NO_LABEL_NEEDS_FACTS", self.codes(record, definitions, evidence))

    def test_unknown_does_not_establish_inapplicability(self):
        record, definitions, evidence = unlabelled()
        negative = deepcopy(synthetic()[0]["selected_labels"][0])
        negative["semantic_applicability"] = "NOT_APPLICABLE"
        record["selected_labels"] = [negative]
        self.assertIn("EXCLUSION_WITHOUT_FACT", self.codes(record, definitions, evidence))
        negative["predicate_checks"][1].update(result="NOT_MET", condition_fact_ids=["F1"])
        self.assertEqual(self.errors(record, definitions, evidence), [])

    def test_complete_requires_skip_are_checked_once(self):
        for mutate in (lambda x: x.pop(), lambda x: x.append(deepcopy(x[0]))):
            record, definitions, evidence = synthetic()
            mutate(record["selected_labels"][0]["predicate_checks"])
            self.assertIn("PREDICATE_COMPLETENESS", self.codes(record, definitions, evidence))

    def test_both_label_and_link_preserve_frozen_versions(self):
        for key, code in (("selected_labels", "DEFINITION_VERSION"), ("label_links", "LINK_VERSION")):
            record, definitions, evidence = synthetic()
            record[key][0]["definition_version"] = "unversioned-guess"
            self.assertIn(code, self.codes(record, definitions, evidence))

    def test_no_complete_library_matrix_required(self):
        record, definitions, evidence = synthetic()
        self.assertEqual(len(definitions), 1)
        self.assertEqual(self.errors(record, {(d["scheme"], d["id"]): d for d in definitions}, evidence), [])
        record, _, evidence = unlabelled()
        self.assertEqual(self.errors(record, [], evidence), [])

    def test_semantic_applicability_independent_of_construction(self):
        record, definitions, evidence = synthetic()
        make_applicable(record)
        record["selected_labels"][0]["construction_feasibility"].update(status="BLOCKED", reason="Executor cannot preserve the input.")
        self.assertEqual(self.errors(record, definitions, evidence), [])

    def test_applicable_cannot_retain_unknown_checks(self):
        record, definitions, evidence = synthetic()
        record["selected_labels"][0]["semantic_applicability"] = "APPLICABLE"
        self.assertIn("APPLICABLE_WITH_UNKNOWN", self.codes(record, definitions, evidence))

    def test_positive_cannot_override_skip(self):
        record, definitions, evidence = synthetic()
        record["selected_labels"][0]["predicate_checks"][-1].update(result="MET", condition_fact_ids=["F1"])
        self.assertIn("POSITIVE_WITH_EXCLUSION", self.codes(record, definitions, evidence))

    def test_positive_facts_cannot_be_silently_dropped(self):
        record, definitions, evidence = synthetic()
        record["condition_facts"].append(dict(record["condition_facts"][0], fact_id="F2"))
        record["selected_labels"][0]["condition_fact_ids"].append("F2")
        self.assertIn("POSITIVE_LABEL_UNLINKED", self.codes(record, definitions, evidence))

    def test_scenario_facts_cannot_be_stitched(self):
        record, definitions, evidence = synthetic()
        record["condition_facts"].append(dict(record["condition_facts"][0], fact_id="F2"))
        record["scenarios"][0]["condition_fact_ids"] = ["F2"]
        self.assertIn("LINK_SCENARIO_FACTS", self.codes(record, definitions, evidence))

    def test_card_cannot_borrow_another_analysis(self):
        record, definitions, evidence = synthetic()
        record["design_cards"][0]["assessment_id"] = "other-subproblem"
        self.assertIn("CARD_ANALYSIS_SCOPE", self.codes(record, definitions, evidence))

    def test_native_design_contract_rejects_execution_and_extra_custom_card_fields(self):
        for key, value in (("execution_status", "PASS"), ("execution_implemented", True), ("pretend_original_input", True)):
            record, definitions, evidence = synthetic()
            record["design_cards"][0][key] = value
            self.assertIn("SCHEMA", self.codes(record, definitions, evidence))

    def test_execution_fields_and_capability_gaps_must_be_explicit(self):
        for key, code in (("execution_status", "OFFLINE_ONLY"), ("execution_implemented", "OFFLINE_ONLY"),
                          ("capability_gaps", "CARD_CAPABILITY_EXPLICIT"), ("required_capabilities", "CARD_CAPABILITY_EXPLICIT")):
            record, definitions, evidence = synthetic()
            del record["design_cards"][0][key]
            self.assertIn(code, self.codes(record, definitions, evidence))

    def test_design_requires_reference_path_and_checks(self):
        for key in ("reference", "target_path", "checks"):
            record, definitions, evidence = synthetic()
            del record["design_cards"][0][key]
            self.assertIn("SCHEMA", self.codes(record, definitions, evidence))

    def test_hypothesis_cannot_be_laundered_to_a_declared_fact(self):
        record, definitions, evidence = synthetic()
        record["source_claims"][0]["basis"] = "HYPOTHESIS"
        self.assertIn("HYPOTHESIS_AS_FACT", self.codes(record, definitions, evidence))

    def test_hypothetical_shape_cannot_support_historical_positive_label(self):
        record, definitions, evidence = synthetic()
        record["source_claims"][0]["basis"] = "HYPOTHESIS"
        record["condition_facts"][0]["basis"] = "HYPOTHESIS"
        self.assertIn("HYPOTHESIS_AS_OBSERVATION", self.codes(record, definitions, evidence))

    def test_hypothesis_cannot_become_original_input_variable(self):
        record, definitions, evidence = unlabelled()
        record["source_claims"][0]["basis"] = "HYPOTHESIS"
        record["condition_facts"][0]["basis"] = "HYPOTHESIS"
        record["design_cards"][0]["condition_fact_ids"] = []
        self.assertIn("ASSUMPTION_AS_INPUT", self.codes(record, definitions, evidence))
        record["design_cards"][0]["variables"][0]["kind"] = "DERIVED"
        self.assertEqual(self.errors(record, definitions, evidence), [])

    def test_internal_quantity_not_api_input(self):
        record, definitions, evidence = synthetic()
        record["condition_facts"][0]["role"] = "DERIVED_CONTROL"
        self.assertIn("ASSUMPTION_AS_INPUT", self.codes(record, definitions, evidence))

    def test_unknown_comparison_cannot_create_new_mode(self):
        record, definitions, evidence = synthetic()
        record["mode_comparisons"] = [{"mode_id": "M-SYNTHETIC", "relation": "UNKNOWN", "reason": "Cannot compare the consumer.", "evidence_ids": []}]
        self.assertEqual(self.errors(record, definitions, evidence), [])
        record["mode_decision"]["action"] = "NEW"
        self.assertIn("UNKNOWN_IS_NOT_NOVELTY", self.codes(record, definitions, evidence))

    def test_selected_grounded_difference_can_be_suggestion_without_full_matrix(self):
        record, definitions, evidence = synthetic()
        record["mode_comparisons"] = [{"mode_id": "M-SYNTHETIC", "relation": "DIFFERENT", "reason": "Source comparison states a different consumer.", "evidence_ids": ["E1"]}]
        record["mode_decision"]["action"] = "NEW"
        self.assertEqual(self.errors(record, definitions, evidence), [])
        record["formal_adoption"] = True
        self.assertIn("SCHEMA", self.codes(record, definitions, evidence))

    def test_construction_code_and_definition_need_independent_checks_and_link(self):
        record, definitions, evidence = synthetic()
        construction = {"construction_id": "SYNTHETIC-TAIL-CODE", "applicability": "PARTIAL",
                        "definition_check": {"clause": definitions[0]["constructions"][0]["definition"],
                                             "clause_role": "INCLUSION", "result": "MET", "condition_fact_ids": ["F1"]},
                        "condition_fact_ids": ["F1"], "reason": "A bounded source construction clue."}
        record["selected_labels"][0]["construction_checks"] = [construction]
        self.assertIn("POSITIVE_CONSTRUCTION_UNLINKED", self.codes(record, definitions, evidence))
        record["label_links"][0]["construction_ids"] = [construction["construction_id"]]
        record["design_cards"][0]["construction_ids"] = [construction["construction_id"]]
        self.assertEqual(self.errors(record, definitions, evidence), [])
        construction["construction_id"] = "S5-07-guide-not-a-code"
        self.assertIn("CONSTRUCTION_SCOPE", self.codes(record, definitions, evidence))

    def test_original42_rule_is_independent_from_v4(self):
        record, definitions, evidence = synthetic()
        definitions[0].update(scheme="ORIGINAL42", id="1.2.2", construction_ids=[])
        record["selected_labels"][0].update(scheme="ORIGINAL42", trigger_id="1.2.2")
        record["label_links"][0].update(scheme="ORIGINAL42", trigger_id="1.2.2")
        record["design_cards"][0]["category_ids"] = []
        self.assertEqual(self.errors(record, definitions, evidence), [])
        record["label_links"][0].update(scheme="V4", trigger_id="S5")
        self.assertIn("LINK_REQUIRES_POSITIVE", self.codes(record, definitions, evidence))


if __name__ == "__main__":
    unittest.main()
