import copy
import unittest

from faultaudit.store import AuditError
from faultaudit.trigger_assessment import instructions, response_schema, validate_assessment


HASH = "a" * 64
REF = {"segment_id": "S:s1", "quote": "Foo在维长65时尾块地址步长错误"}
CELL = {"field": "故障原因", "cell": "B2", "quote": "尾块地址步长在65维时错误"}


def fixture(phase="INIT"):
    payload = {"phase": phase, "subject": {"subject_id": "subject-M1", "case_id": "C1",
        "subject_kind": "MODE_ENTRY" if phase == "INIT" else "FAULT_CASE", "mode_id": "M1",
        "source_case": {"case_id": "C1", "raw": {"模式名称": "尾块寻址异常", "故障原因": CELL["quote"]},
                        "cell_locations": {"模式名称": "A2", "故障原因": "B2"}}},
        "taxonomy": {"items": [{"id": f"T{i:02}", "definition": "维长65"} for i in range(42)],
                     "branches": [{"branch_id": b, "status": "UNDEFINED"} for b in ("2", "3")]},
        "source_issue": {"snapshot_id": "S", "issue_index": 0, "label": "tail",
            "facts": [{"fact_id": "F1", "field": "root_cause", "value": "observed source claim",
                       "evidence": [REF]}],
            "snapshot": {"snapshot_id": "S", "status": "COMPLETE", "segments": [
                {"segment_id": "S:s1", "text": REF["quote"] + "。修复源步长计算。"},
                {"segment_id": "S:s2", "text": "另一个问题：无关故障。"}]},
            "input_scope": {"provided_segment_ids": ["S:s1"]}},
        "wiki_check": {"status": "FOUND"}, "mechanism_catalog": [{"item_id": "M1", "mechanism": "tail addressing"}],
        "judgments": [], "mappings": [], "baseline": None}
    response = {"schema_version": "1.0", "request_hash": HASH, "executor": "codex",
        "producer": {"executor_version": "unreported", "provider": "OpenAI", "model": "unreported", "session_id": "synthetic-test"},
        "case_id": "C1", "rows": [{"trigger_id": f"T{i:02}", "applicability": "UNKNOWN",
            "relation": "UNKNOWN", "evidence_basis": "UNKNOWN", "reason": "当前证据不足，保持未知。"} for i in range(42)],
        "details": [], "external_branches": [{"branch_id": b, "relation": "UNKNOWN", "reason": "未提供权威定义。"} for b in ("2", "3")],
        "decision": {"action": "INIT_ONLY" if phase == "INIT" else "UNDETERMINED", "reason": "本轮分类建议，未正式采用。"},
        "self_check": {"attempt": 1, "numeric_meaning_checked": True, "citations_checked": True,
            "counterevidence_checked": True, "issue_scope_checked": True, "event_vs_technical_checked": True,
            "passed": True, "issues": []}}
    return payload, response


def source_match(response):
    response["source_relation"] = "MATCH"
    response["source_alignment"] = [{"dimension": "mechanism", "relation": "MATCH",
        "reason": "对照原字段与同一资料的具体机制。", "evidence": [copy.deepcopy(REF)], "source_cells": [copy.deepcopy(CELL)]}]


def strong_row(response):
    source_match(response)
    response["rows"][0].update(applicability="APPLICABLE", relation="MATCH", evidence_basis="SOURCE_REPORTED",
        evidence=[copy.deepcopy(REF)], predicate_checks=[{"clause": "维长65", "result": "MET", "evidence": [copy.deepcopy(REF)]}])


def detail(detail_id="Dnew", mode_id="M1"):
    return {"detail_id": detail_id, "mode_id": mode_id, "name": "具体寻址机理候选", "mechanism": "尾块步长计算错误",
        "operator": "Foo", "conditions": ["维长65"], "trigger_ids": ["T00"],
        "evidence_basis": "SOURCE_REPORTED", "evidence": [copy.deepcopy(REF)], "unknowns": ["未本机复现"]}


def incremental_payload():
    payload, response = fixture("INCREMENTAL")
    source_match(response)
    payload["baseline"] = {"baseline_id": "BASE1", "mode_ids": ["M1"],
        "coverage_details": [detail("Dold")]}
    payload["mappings"] = [{"case_id": "C1", "catalog_results": [{"item_id": "M1", "result": "COVERED"}]}]
    return payload, response


class TriggerAssessmentTests(unittest.TestCase):
    def test_complete_unknown_init_is_pending_not_human_review(self):
        payload, response = fixture()
        result = validate_assessment(payload, response, HASH)
        self.assertEqual(len(result["rows"]), 42)
        self.assertEqual(result["processing_status"], "PENDING")
        self.assertFalse(result["review_required"])
        self.assertEqual(result["coverage_kind"], "HISTORICAL_EVIDENCE")
        self.assertFalse(result["execution_verified"])

    def test_schema_and_instructions_explain_two_axes_and_no_execution(self):
        self.assertIn("TriggerAssessment", response_schema()["title"])
        self.assertIn("MODE_ENTRY is not an incident", instructions())
        self.assertIn("every original mode", instructions())

    def test_frozen_identity_and_all_42_unique_are_required(self):
        for mutate in (lambda r: r.update(request_hash="b" * 64), lambda r: r.update(case_id="other"),
                       lambda r: r["rows"].pop(), lambda r: r["rows"].__setitem__(1, copy.deepcopy(r["rows"][0]))):
            with self.subTest(mutate=mutate):
                payload, response = fixture(); mutate(response)
                with self.assertRaises(AuditError): validate_assessment(payload, response, HASH)

    def test_source_definition_can_be_partial_but_not_strong_match(self):
        payload, response = fixture()
        response["rows"][0].update(relation="PARTIAL", evidence_basis="SOURCE_DEFINITION", source_cells=[CELL])
        self.assertEqual(validate_assessment(payload, response, HASH)["rows"][0]["relation"], "PARTIAL")
        response["rows"][0]["relation"] = "MATCH"
        with self.assertRaisesRegex(AuditError, "MATCH requires"): validate_assessment(payload, response, HASH)

    def test_mode_source_alignment_uses_mechanism_not_fake_incident(self):
        payload, response = fixture(); strong_row(response)
        result = validate_assessment(payload, response, HASH)
        self.assertEqual(result["source_relation"], "MATCH")
        self.assertEqual(result["processing_status"], "AUTO_PROCESSED")
        self.assertNotIn("event_relation", result)
        response["source_alignment"][0]["dimension"] = "operator"
        with self.assertRaisesRegex(AuditError, "mechanism alignment"): validate_assessment(payload, response, HASH)

    def test_source_alignment_needs_both_original_cell_and_web_evidence(self):
        for key in ("evidence", "source_cells"):
            payload, response = fixture(); source_match(response)
            response["source_alignment"][0][key] = []
            with self.assertRaisesRegex(AuditError, "both source"): validate_assessment(payload, response, HASH)

    def test_source_match_cannot_hide_positive_differences_in_any_dimension(self):
        for dimension in ("mechanism", "trigger", "operator", "symptom", "context"):
            payload, response = fixture(); source_match(response)
            other = copy.deepcopy(response["source_alignment"][0])
            other.update(dimension=dimension, relation="DIFFERENT", reason="当前原文与源记录的具体事实明确不同。")
            response["source_alignment"].append(other)
            with self.subTest(dimension=dimension), self.assertRaisesRegex(AuditError, "without unresolved fact conflicts"):
                validate_assessment(payload, response, HASH)

    def test_partial_or_unknown_cannot_omit_observed_fact_conflicts(self):
        for relation in ("PARTIAL", "UNKNOWN"):
            payload, response = fixture(); source_match(response)
            response["source_relation"] = relation
            response["source_alignment"][0]["relation"] = "DIFFERENT"
            with self.subTest(relation=relation), self.assertRaisesRegex(AuditError, "require grounded fact_conflicts"):
                validate_assessment(payload, response, HASH)
            response["fact_conflicts"] = [{"reason": "需核对明确的事实差异。", "evidence": [REF], "source_cells": [CELL]}]
            result = validate_assessment(payload, response, HASH)
            self.assertTrue(result["review_required"])
            self.assertEqual(result["processing_status"], "EXCEPTION")

    def test_match_requires_complete_grounded_met_predicates(self):
        for change in ("unknown", "not_met", "no_checks", "cell_only", "no_source_match"):
            payload, response = fixture(); strong_row(response)
            row = response["rows"][0]
            if change == "unknown": row["predicate_checks"][0]["result"] = "UNKNOWN"
            if change == "not_met": row["predicate_checks"][0]["result"] = "NOT_MET"
            if change == "no_checks": row["predicate_checks"] = []
            if change == "cell_only": row["predicate_checks"][0].update(evidence=[], source_cells=[CELL])
            if change == "no_source_match": response["source_relation"] = "UNKNOWN"
            with self.subTest(change=change), self.assertRaises(AuditError): validate_assessment(payload, response, HASH)

    def test_missing_information_cannot_be_negative_or_not_applicable(self):
        for key, value in (("applicability", "NOT_APPLICABLE"), ("relation", "NOT_MATCHED")):
            payload, response = fixture(); response["rows"][0][key] = value
            with self.assertRaisesRegex(AuditError, "NOT_MET"): validate_assessment(payload, response, HASH)
        payload, response = fixture()
        response["rows"][0].update(applicability="NOT_APPLICABLE", relation="NOT_MATCHED", evidence_basis="SOURCE_DEFINITION",
            source_cells=[CELL], predicate_checks=[{"clause": "维长65", "result": "NOT_MET", "source_cells": [CELL]}])
        self.assertFalse(validate_assessment(payload, response, HASH)["review_required"])

    def test_invented_predicate_cannot_supply_a_negative(self):
        payload, response = fixture()
        response["rows"][0].update(relation="NOT_MATCHED", predicate_checks=[
            {"clause": "与该类无关的自造条件", "result": "NOT_MET", "source_cells": [CELL]}])
        with self.assertRaisesRegex(AuditError, "Predicate clause"): validate_assessment(payload, response, HASH)

    def test_predicate_can_quote_its_family_requires(self):
        payload, response = fixture(); strong_row(response)
        payload["taxonomy"]["items"][0]["family_id"] = "family-1"
        payload["taxonomy"]["families"] = [{"family_id": "family-1", "requires": ["CON-SHAPE on tensor-like"]}]
        response["rows"][0]["predicate_checks"].append({"clause": "CON-SHAPE on tensor-like", "result": "MET", "evidence": [REF]})
        validate_assessment(payload, response, HASH)

    def test_match_must_check_whole_definition_and_all_local_family_requires(self):
        payload, response = fixture(); strong_row(response)
        item = payload["taxonomy"]["items"][0]
        item.update(definition="维长65且按布局读取", family_id="family-1", requires=["仅浮点输入"])
        payload["taxonomy"]["families"] = [{"family_id": "family-1", "requires": ["tensor-like OR explicitly scalar-compatible"]}]
        with self.assertRaisesRegex(AuditError, "whole canonical"): validate_assessment(payload, response, HASH)
        checks = response["rows"][0]["predicate_checks"]
        checks[0]["clause"] = item["definition"]
        with self.assertRaisesRegex(AuditError, "MATCH requires"): validate_assessment(payload, response, HASH)
        for clause in ["仅浮点输入", "tensor-like OR explicitly scalar-compatible"]:
            checks.append({"clause": clause, "result": "MET", "evidence": [REF]})
        validate_assessment(payload, response, HASH)
        checks[-1]["result"] = "UNKNOWN"
        with self.assertRaisesRegex(AuditError, "MATCH requires"): validate_assessment(payload, response, HASH)

    def test_skip_is_exclusion_and_cannot_supply_positive_inclusion(self):
        payload, response = fixture(); strong_row(response)
        payload["taxonomy"]["items"][0]["skip_if"] = ["该输入角色不适用"]
        with self.assertRaisesRegex(AuditError, "MATCH requires"): validate_assessment(payload, response, HASH)
        checks = response["rows"][0]["predicate_checks"]
        checks.append({"clause": "该输入角色不适用", "clause_role": "EXCLUSION", "result": "NOT_MET", "evidence": [REF]})
        validate_assessment(payload, response, HASH)
        checks[-1]["result"] = "MET"
        with self.assertRaisesRegex(AuditError, "MATCH requires"): validate_assessment(payload, response, HASH)
        response["rows"][0].update(applicability="NOT_APPLICABLE", relation="NOT_MATCHED")
        validate_assessment(payload, response, HASH)
        checks[-1]["clause_role"] = "INCLUSION"
        with self.assertRaisesRegex(AuditError, "proper role"): validate_assessment(payload, response, HASH)

    def test_existing_baseline_detail_is_not_rewritten(self):
        payload, response = incremental_payload(); response["details"] = [detail("Dold")]
        with self.assertRaisesRegex(AuditError, "not rewritten"): validate_assessment(payload, response, HASH)

    def test_partial_capture_can_support_observed_facts_without_full_document_claim(self):
        payload, response = fixture(); strong_row(response)
        payload["source_issue"]["snapshot"]["status"] = "CONTENT_CAPTURED"
        self.assertEqual(validate_assessment(payload, response, HASH)["rows"][0]["relation"], "MATCH")

    def test_quote_must_be_current_fact_and_inside_provided_issue_scope(self):
        for ref in ({"segment_id": "S:s2", "quote": "另一个问题"}, {"segment_id": "S:s1", "quote": "修复源步长计算"},
                    {"segment_id": "S:s1", "quote": "不存在的文本"}):
            payload, response = fixture(); response["rows"][0]["evidence"] = [ref]
            with self.subTest(ref=ref), self.assertRaisesRegex(AuditError, "outside"): validate_assessment(payload, response, HASH)

    def test_source_cell_quote_and_locator_are_checked(self):
        for key, value in (("cell", "B99"), ("field", "不存在"), ("quote", "编造")):
            payload, response = fixture(); bad = {**CELL, key: value}; response["rows"][0]["source_cells"] = [bad]
            with self.assertRaisesRegex(AuditError, "immutable source"): validate_assessment(payload, response, HASH)

    def test_no_body_or_no_current_issue_cannot_confirm_source(self):
        for status in ("NETWORK_BLOCKED", None):
            payload, response = fixture(); source_match(response)
            if status: payload["source_issue"]["snapshot"]["status"] = status
            else: payload["source_issue"] = None
            with self.assertRaises(AuditError): validate_assessment(payload, response, HASH)

    def test_not_related_requires_positive_mechanism_difference(self):
        payload, response = fixture(); response["source_relation"] = "NOT_RELATED"
        with self.assertRaisesRegex(AuditError, "positive grounded"): validate_assessment(payload, response, HASH)
        source_match(response); response["source_relation"] = "NOT_RELATED"
        response["source_alignment"][0]["relation"] = "DIFFERENT"
        self.assertEqual(validate_assessment(payload, response, HASH)["source_relation"], "NOT_RELATED")
        response["rows"][0].update(relation="PARTIAL", evidence_basis="SOURCE_REPORTED", evidence=[REF])
        with self.assertRaisesRegex(AuditError, "Unrelated"): validate_assessment(payload, response, HASH)

    def test_unrelated_material_cannot_supply_any_web_mechanism_detail(self):
        for phase in ("INIT", "INCREMENTAL"):
            payload, response = fixture(phase); source_match(response)
            response["source_relation"] = "NOT_RELATED"
            response["source_alignment"][0]["relation"] = "DIFFERENT"
            response["details"] = [detail(mode_id="M1" if phase == "INIT" else None)]
            with self.subTest(phase=phase), self.assertRaisesRegex(AuditError, "Unrelated material"):
                validate_assessment(payload, response, HASH)

    def test_positive_incremental_decisions_require_matched_unconflicted_source(self):
        for action in ("CLASSIFY_EXISTING", "EXTEND_DETAIL", "PROPOSE_NEW_MODE"):
            for relation in ("PARTIAL", "UNKNOWN", "NOT_RELATED"):
                payload, response = incremental_payload()
                response["decision"].update(action=action, target_mode_ids=["M1"], target_detail_ids=["Dold"])
                response["source_relation"] = relation
                if relation == "NOT_RELATED": response["source_alignment"][0]["relation"] = "DIFFERENT"
                with self.subTest(action=action, relation=relation), self.assertRaisesRegex(AuditError, "positive incremental decision requires source MATCH"):
                    validate_assessment(payload, response, HASH)

    def test_direct_prior_judgment_cannot_override_current_unrelated_source(self):
        payload, response = incremental_payload()
        payload["mappings"][0]["catalog_results"][0]["result"] = "NOT_COVERED"
        payload["judgments"] = [{"case_id": "C1", "case_attribution": "CONFIRMED", "event_relation": "SAME_EVENT",
            "support_level": "DIRECT", "claim_support": {"root_cause": "SUPPORTED"}, "evidence": [REF]}]
        response["source_relation"] = "NOT_RELATED"
        response["source_alignment"][0]["relation"] = "DIFFERENT"
        response["details"] = [detail(mode_id=None)]
        response["decision"].update(action="PROPOSE_NEW_MODE", target_detail_ids=["Dnew"])
        with self.assertRaisesRegex(AuditError, "Unrelated material"):
            validate_assessment(payload, response, HASH)

    def test_undefined_branches_never_get_invented_labels(self):
        for change in ({"relation": "APPLICABLE"}, {"category_ids": ["2.1"]}):
            payload, response = fixture(); response["external_branches"][0].update(change)
            with self.assertRaisesRegex(AuditError, "Undefined"): validate_assessment(payload, response, HASH)

    def test_defined_outside_branch_uses_only_explicit_ids(self):
        payload, response = fixture()
        payload["taxonomy"]["branches"][0].update(status="DEFINED", categories=[{"id": "2.explicit"}])
        response["external_branches"][0].update(relation="APPLICABLE", category_ids=["2.explicit"], source_cells=[CELL])
        validate_assessment(payload, response, HASH)
        response["external_branches"][0]["category_ids"] = ["2.invented"]
        with self.assertRaisesRegex(AuditError, "explicit definitions"): validate_assessment(payload, response, HASH)

    def test_detail_identity_and_trigger_links_are_preserved(self):
        payload, response = fixture(); response["details"] = [detail()]
        response["rows"][0]["detail_ids"] = ["Dnew"]
        validate_assessment(payload, response, HASH)
        response["details"][0]["trigger_ids"] = ["T01"]
        with self.assertRaisesRegex(AuditError, "links must agree"): validate_assessment(payload, response, HASH)

    def test_init_keeps_mode_identity_and_never_creates_new_mode(self):
        payload, response = fixture(); response["details"] = [detail(mode_id=None)]
        with self.assertRaisesRegex(AuditError, "retain"): validate_assessment(payload, response, HASH)
        response["details"] = []; response["decision"]["action"] = "PROPOSE_NEW_MODE"
        with self.assertRaisesRegex(AuditError, "Init classifies"): validate_assessment(payload, response, HASH)

    def test_classify_existing_requires_current_covered_known_detail(self):
        payload, response = incremental_payload()
        response["decision"].update(action="CLASSIFY_EXISTING", target_mode_ids=["M1"], target_detail_ids=["Dold"])
        validate_assessment(payload, response, HASH)
        for key, value in (("is_stale", True), ("review_status", "REJECT"), ("model_mode", "mock")):
            bad = copy.deepcopy(payload); bad["mappings"][0][key] = value
            with self.assertRaisesRegex(AuditError, "current COVERED"): validate_assessment(bad, response, HASH)
        payload["mappings"][0]["catalog_results"][0]["result"] = "PARTIALLY_COVERED"
        with self.assertRaisesRegex(AuditError, "current COVERED"): validate_assessment(payload, response, HASH)

    def test_extend_needs_parent_coverage_and_new_grounded_detail(self):
        payload, response = incremental_payload(); response["details"] = [detail()]
        response["decision"].update(action="EXTEND_DETAIL", target_mode_ids=["M1"], target_detail_ids=["Dnew"])
        validate_assessment(payload, response, HASH)
        payload["mappings"][0]["catalog_results"][0]["result"] = "UNDETERMINED"
        with self.assertRaisesRegex(AuditError, "parents"): validate_assessment(payload, response, HASH)

    def test_unknown_trigger_mapping_does_not_prove_new_mode(self):
        payload, response = incremental_payload()
        response["decision"].update(action="PROPOSE_NEW_MODE", target_detail_ids=["Dnew"])
        response["details"] = [detail(mode_id=None)]
        with self.assertRaisesRegex(AuditError, "every original"): validate_assessment(payload, response, HASH)
        payload["mappings"][0]["catalog_results"][0]["result"] = "NOT_COVERED"
        with self.assertRaisesRegex(AuditError, "confirmed DIRECT"): validate_assessment(payload, response, HASH)
        payload["judgments"] = [{"case_id": "C1", "case_attribution": "CONFIRMED", "event_relation": "SAME_EVENT",
            "support_level": "DIRECT", "claim_support": {"root_cause": "SUPPORTED"}, "evidence": [REF]}]
        self.assertEqual(validate_assessment(payload, response, HASH)["decision"]["action"], "PROPOSE_NEW_MODE")

    def test_missing_init_baseline_prevents_incremental_claim(self):
        payload, response = incremental_payload(); payload["baseline"] = None
        response["decision"].update(action="CLASSIFY_EXISTING", target_mode_ids=["M1"])
        with self.assertRaisesRegex(AuditError, "initialized baseline"): validate_assessment(payload, response, HASH)

    def test_only_grounded_explicit_fact_conflicts_enter_review(self):
        payload, response = fixture()
        response["fact_conflicts"] = [{"reason": "具体来源事实存在矛盾。", "evidence": [REF], "source_cells": [CELL]}]
        result = validate_assessment(payload, response, HASH)
        self.assertTrue(result["review_required"])
        self.assertEqual(result["processing_status"], "EXCEPTION")
        response["fact_conflicts"][0]["evidence"] = []
        with self.assertRaisesRegex(AuditError, "webpage"): validate_assessment(payload, response, HASH)

    def test_unknown_verification_does_not_manufacture_review_exception(self):
        payload, response = fixture()
        response["self_check"].update(passed=False, issues=["没有CI日志"])
        with self.assertRaisesRegex(AuditError, "Ordinary unknowns"): validate_assessment(payload, response, HASH)

    def test_accept_adoption_and_local_execution_are_rejected(self):
        for key, value in (("review_status", "ACCEPT"), ("execution_verified", True), ("coverage_kind", "EXECUTED"), ("adopt", True)):
            payload, response = fixture(); response[key] = value
            with self.assertRaises(AuditError): validate_assessment(payload, response, HASH)

    def test_validation_does_not_mutate_inputs(self):
        payload, response = fixture(); strong_row(response)
        old = copy.deepcopy((payload, response))
        validate_assessment(payload, response, HASH)
        self.assertEqual((payload, response), old)


if __name__ == "__main__":
    unittest.main()
