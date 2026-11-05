"""Autonomous factual processing remains distinct from event confirmation."""
from __future__ import annotations

import copy
import unittest

from faultaudit.contracts import Judgment
from faultaudit.gates import processing_decision
from faultaudit.model import ModelError, validate_task_result
from faultaudit.pipeline import gate_judgment
from faultaudit.prompts import PROMPT_VERSION, comparison_messages
from faultaudit.store import AuditError


def fixture(*, number_source="prob=0.5", number_evidence="prob=0.5", number_source_value="0.5",
            number_evidence_value="0.5", number_source_meaning="probability", number_evidence_meaning="probability",
            term_source="rope", term_evidence="rope", status="COMPLETE"):
    raw = {"数值": number_source, "算子": term_source, "问题描述": "TP16首token乱码",
           "发生情境": "sleep/wakeup后", "根因": "异步H2D缓冲区提前复用", "事件编号": "EVT-A001"}
    case = {"case_id": "c1", "raw": raw, "cell_locations": {field: f"原表!{chr(65 + i)}2" for i, field in enumerate(raw)},
            "description": raw["问题描述"], "customer_model": "客户甲/Model-X", "operator_raw": term_source,
            "root_cause_raw": raw["根因"], "root_cause_origin": "SOURCE_RAW"}
    paragraph = f"问题一：{number_evidence}；算子{term_evidence}；TP16首token乱码；sleep/wakeup后；异步H2D缓冲区提前复用。"
    other = "问题二：npu_mrope在不同输入轴下出现问题，根因是另一条量化路径。"
    snap = {"snapshot_id": "s1", "status": status, "text": paragraph + "\n" + other,
            "segments": [{"segment_id": "seg-1", "text": paragraph}, {"segment_id": "seg-2", "text": other}],
            "input_scope": {"scope": "FULL_CAPTURED_SNAPSHOT"}}
    def fact(category, field, meaning, evidence_quote, source_value="", evidence_value=""):
        return {"category": category, "source_field": field, "source_quote": raw[field], "source_cell": case["cell_locations"][field],
                "source_value": source_value, "evidence_value": evidence_value, "source_meaning": meaning, "evidence_meaning": meaning,
                "evidence": [{"segment_id": "seg-1", "quote": evidence_quote}], "relation": "MATCH", "reason": "对照原字段和当前子问题"}
    facts = [fact("NUMBER", "数值", number_source_meaning, number_evidence, number_source_value, number_evidence_value),
             fact("TERM", "算子", "operator", term_evidence, term_source, term_evidence),
             fact("SCENARIO", "问题描述", "symptom", raw["问题描述"], raw["问题描述"], raw["问题描述"]),
             fact("SCENARIO", "发生情境", "occurrence_context", raw["发生情境"], raw["发生情境"], raw["发生情境"]),
             fact("TECHNICAL_CONCLUSION", "根因", "mechanism", raw["根因"], raw["根因"], raw["根因"])]
    facts[0]["evidence_meaning"] = number_evidence_meaning
    value = {"case_id": "c1", "snapshot_id": "s1", "case_attribution": "UNKNOWN", "event_relation": "UNDETERMINED",
             "pattern_relation": "POSSIBLY_RELATED", "support_level": "PARTIAL", "matched_dimensions": [], "conflicting_dimensions": [],
             "unknown_dimensions": ["event_identity", "fix_version"], "evidence": [{"segment_id": "seg-1", "quote": paragraph}],
             "event_anchor": "", "short_reason": "已完成当前适用子问题的逐事实对照，事件身份与修复版本仍未知",
             "missing_information": ["修复版本未报告"],
             "claim_support": {"symptom": "SUPPORTED", "root_cause": "UNKNOWN", "fix": "UNKNOWN", "verification": "UNKNOWN"},
             "fact_comparisons": facts,
             "applicable_issue": {"label": "问题一", "evidence": [{"segment_id": "seg-1", "quote": paragraph}], "selection_reason": "发生情境对应原记录"},
             "self_check": {"attempt": 1, "numeric_meaning_checked": True, "citations_checked": True, "counterevidence_checked": True,
                            "issue_scope_checked": True, "event_vs_technical_checked": True, "passed": True, "issues": []},
             "model_mode": "opencode", "model_id": "site-reported-model"}
    return case, snap, value


def validated(case, snap, value):
    return validate_task_result("compare", value, case=case, snapshot=snap)


class FactComparisonTests(unittest.TestCase):
    def test_legacy_judgment_is_compatible_but_not_autoprocessed(self):
        case, snap, value = fixture()
        for key in ("fact_comparisons", "applicable_issue", "self_check"):
            value.pop(key)
        checked = validated(case, snap, value)
        self.assertEqual(checked["fact_comparisons"], [])
        result = gate_judgment(case, snap, checked, context={"source_relation": "SOURCE_LINKED"})
        self.assertEqual(result["processing_status"], "PENDING")
        self.assertFalse(result["review_required"])
        self.assertEqual(result["review_status"], "PENDING_AGENT")

    def test_known_legacy_conflicts_remain_exceptions_without_fact_padding(self):
        for change in ("dimensions", "root_claim", "support", "trusted_mismatch", "trusted_different_event"):
            with self.subTest(change=change):
                case, snap, value = fixture()
                for field in ("fact_comparisons", "applicable_issue", "self_check"):
                    value.pop(field)
                if change == "dimensions":
                    value["conflicting_dimensions"] = ["root_cause"]
                elif change == "root_claim":
                    value["claim_support"]["root_cause"] = "CONTRADICTED"
                elif change == "support":
                    value["support_level"] = "CONFLICT"
                elif change == "trusted_mismatch":
                    value["case_attribution"] = "MISMATCH"
                else:
                    value["event_relation"] = "DIFFERENT_EVENT"
                result = processing_decision(case, snap, value, "SOURCE_LINKED")
                self.assertEqual(result["processing_status"], "EXCEPTION")
                self.assertTrue(result["review_required"])
                self.assertTrue(result["review_reasons"])
                value["model_mode"] = "mock"
                mock = processing_decision(case, snap, value, "SOURCE_LINKED")
                self.assertEqual(mock["processing_status"], "PENDING")
                self.assertFalse(mock["review_required"])

    def test_trusted_source_completes_facts_without_event_confirmation(self):
        case, snap, value = fixture()
        result = gate_judgment(case, snap, validated(case, snap, value), context={"source_relation": "SOURCE_LINKED"})
        self.assertEqual(result["processing_status"], "AUTO_PROCESSED")
        self.assertFalse(result["review_required"])
        self.assertEqual(result["review_status"], "NOT_REQUIRED")
        self.assertEqual(result["case_attribution"], "UNKNOWN")
        self.assertEqual(result["event_relation"], "UNDETERMINED")
        self.assertNotEqual(result["support_level"], "DIRECT")

    def test_partial_capture_can_finish_scoped_source_facts_with_unknown_fix(self):
        for status in ("PARTIAL", "CONTENT_CAPTURED"):
            with self.subTest(status=status):
                case, snap, value = fixture(status=status)
                result = gate_judgment(case, snap, value, context={"source_relation": "SOURCE_LINKED"})
                self.assertEqual(result["processing_status"], "AUTO_PROCESSED")
                self.assertFalse(result["review_required"])
                self.assertEqual(result["observation_scope"], "CAPTURED_CONTENT")
                self.assertIn("修复版本未报告", result["missing_information"])

    def test_source_trace_requires_original_field_quote_and_exact_cell(self):
        for changes in ({"source_field": "不存在的字段"}, {"source_quote": "prob=0.7"}, {"source_cell": "其他页!A2"},
                        {"source_cell": ""}):
            with self.subTest(changes=changes):
                case, snap, value = fixture()
                value["fact_comparisons"][0].update(changes)
                with self.assertRaises(ModelError):
                    validated(case, snap, value)
                with self.assertRaises(AuditError):
                    gate_judgment(case, snap, value)

    def test_same_number_probability_and_log_probability_cannot_match(self):
        case, snap, value = fixture(number_evidence="logprob=0.5", number_evidence_meaning="log_probability")
        with self.assertRaises(ModelError):
            validated(case, snap, value)

    def test_alignment_64_and_tp_64_cannot_match(self):
        case, snap, value = fixture(number_source="alignment=64", number_evidence="TP64", number_source_value="64",
                                   number_evidence_value="64", number_source_meaning="alignment", number_evidence_meaning="tensor_parallel")
        with self.assertRaises(ModelError):
            validated(case, snap, value)

    def test_numeric_values_and_meanings_both_required_for_match(self):
        case, snap, value = fixture(number_evidence="prob=0.7", number_evidence_value="0.7")
        with self.assertRaises(ModelError):
            validated(case, snap, value)
        case, snap, value = fixture()
        value["fact_comparisons"][0]["source_meaning"] = ""
        with self.assertRaises(ModelError):
            validated(case, snap, value)

    def test_decimal_equivalent_values_have_same_meaning(self):
        case, snap, value = fixture(number_evidence="prob=0.50", number_evidence_value="0.50")
        self.assertEqual(validated(case, snap, value)["fact_comparisons"][0]["relation"], "MATCH")

    def test_rope_and_npu_mrope_cannot_match(self):
        case, snap, value = fixture(term_evidence="npu_mrope")
        with self.assertRaises(ModelError):
            validated(case, snap, value)

    def test_rope_substring_cannot_be_laundered_as_whole_operator(self):
        case, snap, value = fixture(term_evidence="npu_mrope")
        value["fact_comparisons"][1]["evidence_value"] = "rope"
        with self.assertRaises(ModelError):
            validated(case, snap, value)

    def test_name_only_and_different_roles_are_preserved_without_false_match(self):
        case, snap, value = fixture(term_evidence="npu_mrope", number_evidence="logprob=0.5", number_evidence_meaning="log_probability")
        value["fact_comparisons"][0].update(relation="DIFFERENT", reason="数字同值，prob与logprob意义不同")
        value["fact_comparisons"][1].update(relation="NAME_ONLY", reason="名称相近，不能确认同一算子")
        result = validated(case, snap, value)
        self.assertEqual([f["relation"] for f in result["fact_comparisons"][:2]], ["DIFFERENT", "NAME_ONLY"])
        self.assertEqual(processing_decision(case, snap, result, "SOURCE_LINKED")["processing_status"], "AUTO_PROCESSED")

    def test_fact_evidence_cannot_cross_snapshot_or_selected_subissue(self):
        for ref in ({"segment_id": "other:s1", "quote": "prob=0.5"},
                    {"segment_id": "seg-2", "quote": "npu_mrope"}):
            with self.subTest(ref=ref):
                case, snap, value = fixture()
                fact = value["fact_comparisons"][1]
                fact.update(evidence=[ref], evidence_value="npu_mrope" if ref["segment_id"] == "seg-2" else "rope", relation="NAME_ONLY")
                value["evidence"].append(ref)
                with self.assertRaises(ModelError):
                    validated(case, snap, value)

    def test_fabricated_fact_quote_is_rejected(self):
        case, snap, value = fixture()
        value["fact_comparisons"][0]["evidence"][0]["quote"] = "invented prob=0.5"
        with self.assertRaises(ModelError):
            validated(case, snap, value)

    def test_fact_quotes_must_survive_in_top_level_evidence(self):
        case, snap, value = fixture()
        value["evidence"] = [{"segment_id": "seg-1", "quote": "问题一"}]
        with self.assertRaises(ModelError):
            validated(case, snap, value)

    def test_one_bounded_check_is_required_and_retries_are_not_claimed(self):
        for attempt in (0, 2, True):
            with self.subTest(attempt=attempt):
                case, snap, value = fixture()
                value["self_check"]["attempt"] = attempt
                with self.assertRaises(ModelError):
                    validated(case, snap, value)
        case, snap, value = fixture()
        value["self_check"]["citations_checked"] = "true"
        with self.assertRaises(ModelError):
            validated(case, snap, value)

    def test_unfinished_check_or_missing_category_is_pending_for_agent(self):
        for change in ("category", "numeric", "counterevidence", "issue", "event", "passed", "no_check", "no_issue"):
            with self.subTest(change=change):
                case, snap, value = fixture()
                if change == "category":
                    value["fact_comparisons"] = value["fact_comparisons"][1:]
                elif change in {"no_check", "no_issue"}:
                    value["self_check" if change == "no_check" else "applicable_issue"] = None
                else:
                    key = {"numeric": "numeric_meaning_checked", "counterevidence": "counterevidence_checked", "issue": "issue_scope_checked",
                           "event": "event_vs_technical_checked", "passed": "passed"}[change]
                    value["self_check"][key] = False
                result = processing_decision(case, snap, validated(case, snap, value), "SOURCE_LINKED")
                self.assertEqual(result["processing_status"], "PENDING")
                self.assertFalse(result["review_required"])

    def test_real_fact_conflict_and_self_check_issues_require_resolution(self):
        for change in ("fact", "dimension", "root_claim", "self_check"):
            with self.subTest(change=change):
                case, snap, value = fixture()
                if change == "fact":
                    value["fact_comparisons"][4]["relation"] = "CONFLICT"
                elif change == "dimension":
                    value["conflicting_dimensions"] = ["root_cause"]
                elif change == "root_claim":
                    value["claim_support"]["root_cause"] = "CONTRADICTED"
                else:
                    value["self_check"].update(passed=False, issues=["两个子问题的归属尚无法区分"])
                result = processing_decision(case, snap, validated(case, snap, value), "SOURCE_LINKED")
                self.assertEqual(result["processing_status"], "EXCEPTION")
                self.assertTrue(result["review_required"])

    def test_search_positive_needs_specific_scenario_and_technical_matches(self):
        case, snap, value = fixture()
        self.assertEqual(processing_decision(case, snap, validated(case, snap, value), "SEARCH_CANDIDATE")["processing_status"], "AUTO_PROCESSED")
        for drop in (2, 3, 4):
            with self.subTest(drop=drop):
                modified = copy.deepcopy(value)
                modified["fact_comparisons"][drop].update(relation="UNKNOWN", reason="当前输入不能确认此维度")
                result = processing_decision(case, snap, validated(case, snap, modified), "SEARCH_CANDIDATE")
                self.assertEqual(result["processing_status"], "PENDING")
                self.assertFalse(result["review_required"])

    def test_search_match_does_not_require_numbers(self):
        case, snap, value = fixture()
        case["raw"].pop("数值")
        case["cell_locations"].pop("数值")
        value["fact_comparisons"][0] = {"category": "NUMBER", "relation": "UNKNOWN", "reason": "原记录未给可对比数值"}
        result = processing_decision(case, snap, validated(case, snap, value), "SEARCH_CANDIDATE")
        self.assertEqual(result["processing_status"], "AUTO_PROCESSED")

    def test_generic_name_or_number_matches_do_not_establish_search_link(self):
        case, snap, value = fixture()
        for fact in value["fact_comparisons"][2:]:
            fact.update(source_meaning="generic_name", evidence_meaning="generic_name")
        result = processing_decision(case, snap, validated(case, snap, value), "SEARCH_CANDIDATE")
        self.assertEqual(result["processing_status"], "PENDING")
        self.assertFalse(result["review_required"])

    def test_pending_provenance_and_mock_do_not_autoprocess(self):
        case, snap, value = fixture()
        result = processing_decision(case, snap, value, "PROVENANCE_PENDING")
        self.assertEqual(result["processing_status"], "PENDING")
        value["model_mode"] = "mock"
        result = processing_decision(case, snap, value, "SOURCE_LINKED")
        self.assertEqual(result["processing_status"], "PENDING")
        self.assertFalse(result["review_required"])

    def test_unknown_category_requires_explanation_not_invented_quotes(self):
        case, snap, value = fixture()
        value["fact_comparisons"][0] = {"category": "NUMBER", "relation": "UNKNOWN", "reason": ""}
        result = processing_decision(case, snap, validated(case, snap, value), "SOURCE_LINKED")
        self.assertEqual(result["processing_status"], "PENDING")

    def test_search_negative_can_complete_normally_without_positive_match_requirements(self):
        case, snap, value = fixture()
        exclusion = "事件EVT-B002是乙客户周二单独的故障，已核对关联资料并排除原事件EVT-A001的多工单关系。"
        snap["segments"][0]["text"] += exclusion
        snap["text"] = snap["segments"][0]["text"] + "\n" + snap["segments"][1]["text"]
        ref = {"segment_id": "seg-1", "quote": exclusion}
        value["evidence"].append(ref)
        value["applicable_issue"]["evidence"][0]["quote"] += exclusion
        value["event_relation"] = "DIFFERENT_EVENT"
        value["negative_basis"] = {"other_event": {"positive_identity": "EVT-B002", "context": exclusion,
            "dimensions": ["event_identity", "symptom", "occurrence_context"], "evidence": [ref]}}
        for fact in value["fact_comparisons"][2:]:
            fact.update(relation="DIFFERENT", reason="另一事件的技术事实不能确认原记录")
        checked = validated(case, snap, value)
        self.assertEqual(processing_decision(case, snap, checked, "SEARCH_CANDIDATE")["processing_status"], "AUTO_PROCESSED")
        trusted = processing_decision(case, snap, checked, "SOURCE_LINKED")
        self.assertEqual(trusted["processing_status"], "EXCEPTION")
        self.assertTrue(trusted["review_required"])
        checked["claim_support"]["root_cause"] = "SUPPORTED"
        with self.assertRaises(ModelError):
            validated(case, snap, checked)

    def test_processing_helper_does_not_trust_negative_labels_without_valid_basis(self):
        case, snap, value = fixture()
        value["event_relation"] = "DIFFERENT_EVENT"
        result = processing_decision(case, snap, value, "SEARCH_CANDIDATE")
        self.assertNotEqual(result["processing_status"], "AUTO_PROCESSED")
        exclusion = "事件EVT-A001仍为甲客户本次故障，不能将原事件编号伪装成另一次事故。"
        snap["segments"][0]["text"] += exclusion
        snap["text"] = snap["segments"][0]["text"] + "\n" + snap["segments"][1]["text"]
        ref = {"segment_id": "seg-1", "quote": exclusion}
        value["evidence"].append(ref)
        value["applicable_issue"]["evidence"][0]["quote"] += exclusion
        value["negative_basis"] = {"other_event": {"positive_identity": "EVT-A001", "context": exclusion,
            "dimensions": ["event_identity", "symptom", "occurrence_context"], "evidence": [ref]}}
        self.assertNotEqual(processing_decision(case, snap, value, "SEARCH_CANDIDATE")["processing_status"], "AUTO_PROCESSED")

    def test_no_processing_or_human_acceptance_fields_from_model(self):
        case, snap, value = fixture()
        for field, content in (("review_status", "ACCEPT"), ("processing_status", "AUTO_PROCESSED")):
            with self.subTest(field=field), self.assertRaises(ModelError):
                validated(case, snap, {**value, field: content})

    def test_prompt_contains_bounded_facts_and_source_context(self):
        case, snap, value = fixture()
        messages = comparison_messages(case, snap, {}, context={"source_relation": "SOURCE_LINKED"})
        self.assertEqual(PROMPT_VERSION, "faultaudit-1.7")
        self.assertIn("source_cell", messages[0]["content"])
        self.assertIn("self_check", messages[0]["content"])
        self.assertIn("SOURCE_LINKED", messages[1]["content"])

    def test_live_bridge_rejects_empty_facts_then_accepts_completed_result_for_same_task(self):
        from tests.test_evidence_workflow import EvidenceWorkflowTests
        from faultaudit.bridge import export_model_tasks, submit_model_results
        from faultaudit.pipeline import report_data

        workflow = EvidenceWorkflowTests(methodName="runTest")
        workflow.setUp()
        self.addCleanup(workflow.doCleanups)
        workflow.load()
        workflow.capture()
        _, requests = workflow.drive()
        self.assertEqual([task["kind"] for task in requests], ["summarize"])
        submit_model_results(workflow.store, workflow.run_id, [workflow.envelope(requests[0])])
        _, requests = workflow.drive()
        self.assertEqual([task["kind"] for task in requests], ["compare"])
        task = requests[0]
        self.assertEqual(task["payload"]["processing_context"]["processing_version"], "evidence-first-0.1.8")
        completed = workflow.envelope(task)
        before = workflow.store.records(workflow.run_id, "model_results")
        for variant in ("no_facts", "unfinished_check", "no_issue", "unknown_without_reason", "no_source_trace"):
            with self.subTest(variant=variant):
                incomplete = copy.deepcopy(completed)
                if variant == "no_facts":
                    incomplete["result"].pop("fact_comparisons")
                    incomplete["result"].pop("self_check")
                elif variant == "unfinished_check":
                    incomplete["result"]["self_check"].update(passed=False, issues=[])
                elif variant == "no_issue":
                    incomplete["result"]["applicable_issue"] = None
                elif variant == "unknown_without_reason":
                    incomplete["result"]["fact_comparisons"][0] = {"category": "NUMBER", "relation": "UNKNOWN", "reason": ""}
                else:
                    incomplete["result"]["fact_comparisons"] = [{"category": category, "relation": "UNKNOWN",
                        "reason": "尚未绑定原表单元格，Agent须补足来源对照"} for category in ("NUMBER", "TERM", "SCENARIO", "TECHNICAL_CONCLUSION")]
                with self.assertRaises(AuditError):
                    submit_model_results(workflow.store, workflow.run_id, [incomplete])
                self.assertEqual(workflow.store.records(workflow.run_id, "model_results"), before)
                self.assertIsNone(workflow.store.get(workflow.run_id, "model_results", task["task_id"]))
                pending = export_model_tasks(workflow.store, workflow.run_id)["tasks"]
                self.assertEqual([request["task_id"] for request in pending], [task["task_id"]])
                self.assertEqual(pending[0]["request_hash"], completed["request_hash"])
        submitted = submit_model_results(workflow.store, workflow.run_id, [completed])
        self.assertEqual(submitted["accepted"], 1)
        workflow.drive()
        judgments = report_data(workflow.store, workflow.run_id)["judgments"]
        self.assertEqual(len(judgments), 1)
        self.assertEqual(judgments[0]["processing_status"], "AUTO_PROCESSED")
        self.assertFalse(judgments[0]["review_required"])

    def test_live_bridge_keeps_complete_but_weak_search_result_pending(self):
        from tests.test_evidence_workflow import EvidenceWorkflowTests
        from faultaudit.bridge import submit_model_results
        from faultaudit.pipeline import report_data

        workflow = EvidenceWorkflowTests(methodName="runTest")
        workflow.setUp()
        self.addCleanup(workflow.doCleanups)
        case = workflow.load(with_links=False)[0]
        text = "main：sample_op仅列于通用算子目录；logprob=0.404为通用数值示例，未给客户故障症状、发生场景或定位结论。"
        workflow.store.ingest_evidence(workflow.run_id, {"url": "https://example.invalid/weak-candidate", "text": text,
            "status": "PARTIAL", "is_synthetic": True, "origin": "SEARCH_DISCOVERED", "case_ids": [case["case_id"]]})
        _, requests = workflow.drive()
        submit_model_results(workflow.store, workflow.run_id, [workflow.envelope(requests[0])])
        _, requests = workflow.drive()
        self.assertEqual([task["kind"] for task in requests], ["compare"])
        returned = workflow.envelope(requests[0])
        returned["result"]["case_attribution"] = "UNKNOWN"
        returned["result"]["support_level"] = "INDIRECT"
        returned["result"]["claim_support"] = {field: "UNKNOWN" for field in ("symptom", "root_cause", "fix", "verification")}
        for fact in returned["result"]["fact_comparisons"][2:]:
            fact.update(relation="UNKNOWN", source_value="", evidence_value="", evidence_meaning="unreported",
                        reason="已核对当前片段，只有通用词/数值，无法确认该具体维度与原故障对应")
        submitted = submit_model_results(workflow.store, workflow.run_id, [returned])
        self.assertEqual(submitted["accepted"], 1)
        workflow.drive()
        data = report_data(workflow.store, workflow.run_id)
        result = data["judgments"][0]
        self.assertEqual(result["processing_status"], "PENDING")
        self.assertFalse(result["review_required"])
        self.assertEqual(result["case_attribution"], "UNKNOWN")
        self.assertEqual(result["event_relation"], "UNDETERMINED")
        self.assertNotEqual(data["evidence_plans"]["cases"][0]["path"], "VERIFIED_SEARCH")
        self.assertIsNotNone(workflow.store.get(workflow.run_id, "model_results", returned["task_id"]))


if __name__ == "__main__":
    unittest.main()
