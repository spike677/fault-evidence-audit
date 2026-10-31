"""Negative proposals require positive, scoped identity evidence; no inference."""
from __future__ import annotations

import copy
import unittest

from pydantic import ValidationError

from faultaudit.contracts import Judgment
from faultaudit.gates import judgment_semantic_errors
from faultaudit.model import MockJudge, ModelError, validate_task_result
from faultaudit.pipeline import gate_judgment
from faultaudit.store import AuditError


OTHER_CONTEXT = "另一事件EVT-B002为乙客户于周二在TP16推理时发生首token乱码，属于独立客户复现。"
OWNERSHIP_CONTEXT = "本记录仅归属乙客户的EVT-B002故障，明确排除甲客户EVT-A001的这次复现。"


def source_case():
    return {"case_id": "case-a", "description": "甲客户在周一推理首token乱码",
            "raw": {"事件编号": "EVT-A001", "问题描述": "甲客户在周一推理首token乱码", "算子": "all_reduce",
                    "根因": "周报归因all_reduce", "DTS": "DTS-111"},
            "customer_model": "甲客户Model-X", "operator_raw": "all_reduce",
            "root_cause_raw": "周报归因all_reduce", "root_cause_origin": "SOURCE_RAW"}


def snapshot(text=OTHER_CONTEXT, status="COMPLETE", scope=None):
    result = {"snapshot_id": "snapshot-a", "status": status, "text": text,
              "segments": [{"segment_id": "segment-a", "text": text}], "is_synthetic": False}
    if scope is not None:
        result["input_scope"] = {"scope": scope}
    return result


def judgment(snap, **updates):
    value = {"case_id": "case-a", "snapshot_id": "snapshot-a", "case_attribution": "UNKNOWN",
             "event_relation": "UNDETERMINED", "pattern_relation": "POSSIBLY_RELATED",
             "support_level": "PARTIAL", "evidence": [{"segment_id": "segment-a", "quote": snap["text"]}],
             "matched_dimensions": [], "conflicting_dimensions": [], "unknown_dimensions": ["event_identity"],
             "event_anchor": "", "short_reason": "仅依据当前采集内容的待复核建议", "missing_information": [],
             "claim_support": {"symptom": "UNKNOWN", "root_cause": "UNKNOWN", "fix": "UNKNOWN", "verification": "UNKNOWN"},
             "model_mode": "opencode", "model_id": "external-model"}
    value.update(updates)
    return value


def basis(snap, *, kind="other_event", context=None, identity="EVT-B002", dimensions=None):
    if dimensions is None:
        dimensions = ["event_identity", "symptom", "occurrence_context"] if kind == "other_event" else ["ownership", "explicit_exclusion"]
    return {kind: {"positive_identity": identity, "context": context or snap["text"], "dimensions": dimensions,
                   "evidence": [{"segment_id": "segment-a", "quote": snap["text"]}]}}


def check(value, snap):
    return validate_task_result("compare", value, case=source_case(), snapshot=snap)


class NegativeJudgmentGatesTests(unittest.TestCase):
    def test_schema_requires_positive_basis_without_source_context(self):
        snap = snapshot()
        for updates in ({"event_relation": "DIFFERENT_EVENT"}, {"case_attribution": "MISMATCH"}):
            with self.subTest(updates=updates), self.assertRaises(ValidationError):
                Judgment.model_validate(judgment(snap, **updates))

    def test_technical_differences_and_missing_fields_do_not_identify_other_event(self):
        text = "算子rope与原表all_reduce不同，机制也不同；页面未提供预期客户字段，工单编号为DTS-222。"
        snap = snapshot(text)
        for difference in ("operator", "mechanism", "root_cause", "missing_customer", "artifact_id", "link"):
            for conclusion in ({"event_relation": "DIFFERENT_EVENT"}, {"case_attribution": "MISMATCH"}):
                with self.subTest(difference=difference, conclusion=conclusion):
                    value = judgment(snap, conflicting_dimensions=[difference], **conclusion)
                    with self.assertRaises(ModelError):
                        check(value, snap)

    def test_operator_difference_cannot_be_laundered_as_negative_identity(self):
        snap = snapshot("operator rope 与原表 all_reduce 不同，因此技术路径存在差异。")
        forged = basis(snap, identity="rope", dimensions=["operator"])
        for target in ("other_event", "attribution_mismatch"):
            value = judgment(snap, event_relation="DIFFERENT_EVENT" if target == "other_event" else "UNDETERMINED",
                             case_attribution="MISMATCH" if target == "attribution_mismatch" else "UNKNOWN",
                             negative_basis={target: forged["other_event"]})
            with self.subTest(target=target), self.assertRaises(ModelError):
                check(value, snap)

    def test_operator_basis_is_rejected_by_shared_gate_even_before_schema(self):
        snap = snapshot("operator rope 与原表 all_reduce 不同，因此技术路径存在差异。")
        value = judgment(snap, event_relation="DIFFERENT_EVENT", negative_basis=basis(snap, identity="rope", dimensions=["operator"]))
        self.assertTrue(judgment_semantic_errors(source_case(), snap, value))

    def test_mechanism_and_identifier_only_dimensions_are_rejected(self):
        snap = snapshot("工单DTS-222的量化算子机制不同于原表DTS-111，编号也不同。")
        for dimension in ("mechanism", "root_cause", "artifact_id", "link"):
            with self.subTest(dimension=dimension), self.assertRaises(ModelError):
                check(judgment(snap, event_relation="DIFFERENT_EVENT",
                               negative_basis=basis(snap, identity="DTS-222", dimensions=[dimension])), snap)

    def test_another_identifier_by_itself_does_not_establish_another_incident(self):
        snap = snapshot("资料中的工单标识为DTS-222，原始记录引用了DTS-111。")
        value = judgment(snap, event_relation="DIFFERENT_EVENT",
                         negative_basis=basis(snap, identity="DTS-222", dimensions=["event_identity"]))
        with self.assertRaises(ModelError):
            check(value, snap)

    def test_isolated_long_token_does_not_become_context_by_dimension_labels(self):
        identity = "npu_dequant_swiglu_quant"
        snap = snapshot(identity)
        value = judgment(snap, event_relation="DIFFERENT_EVENT", negative_basis=basis(snap, identity=identity))
        with self.assertRaises(ModelError):
            check(value, snap)

    def test_positive_other_event_context_can_be_a_review_proposal(self):
        snap = snapshot()
        value = judgment(snap, event_relation="DIFFERENT_EVENT", negative_basis=basis(snap))
        result = check(value, snap)
        self.assertEqual(result["event_relation"], "DIFFERENT_EVENT")
        self.assertEqual(result["case_attribution"], "UNKNOWN")
        self.assertNotEqual(result.get("review_status"), "ACCEPT")
        self.assertEqual(judgment_semantic_errors(source_case(), snap, result), [])

    def test_source_event_identity_cannot_be_used_as_another_event_basis(self):
        snap = snapshot("资料明确描述事件EVT-A001，属于原记录的同一次故障，发生于甲客户周一推理首token乱码。")
        value = judgment(snap, event_relation="DIFFERENT_EVENT", negative_basis=basis(snap, identity=" EVT-A001 "))
        for field in ("事件编号", "事件ID", "故障编号", "incident_id", "event_id"):
            with self.subTest(source_field=field):
                case = source_case()
                case["raw"].pop("事件编号")
                case["raw"][field] = " EVT-A001 "
                before = copy.deepcopy(value)
                self.assertTrue(judgment_semantic_errors(case, snap, value))
                with self.assertRaises(ModelError):
                    validate_task_result("compare", value, case=case, snapshot=snap)
                with self.assertRaises(AuditError):
                    gate_judgment(case, snap, value)
                self.assertEqual(value, before)

    def test_record_and_artifact_ids_are_not_compared_as_source_event_ids(self):
        snap = snapshot()
        case = source_case()
        case.update(external_id="EVT-B002")
        case["raw"].update({"统一ID": "EVT-B002", "DTS": "EVT-B002", "PR": "EVT-B002", "wiki": "EVT-B002"})
        value = judgment(snap, event_relation="DIFFERENT_EVENT", negative_basis=basis(snap))
        result = validate_task_result("compare", value, case=case, snapshot=snap)
        self.assertEqual(result["event_relation"], "DIFFERENT_EVENT")
        self.assertEqual(gate_judgment(case, snap, value)["review_status"], "NEEDS_REVIEW")

    def test_source_event_identity_is_not_inferred_from_description_mentions(self):
        snap = snapshot()
        case = source_case()
        case["raw"].pop("事件编号")
        case["raw"]["问题描述"] += "，另外参考了事件EVT-B002的资料。"
        value = judgment(snap, event_relation="DIFFERENT_EVENT", negative_basis=basis(snap))
        self.assertEqual(judgment_semantic_errors(case, snap, value), [])

    def test_explicit_ownership_exclusion_can_propose_mismatch(self):
        snap = snapshot(OWNERSHIP_CONTEXT)
        value = judgment(snap, case_attribution="MISMATCH", negative_basis=basis(snap, kind="attribution_mismatch"))
        result = check(value, snap)
        self.assertEqual(result["case_attribution"], "MISMATCH")
        self.assertEqual(result["event_relation"], "UNDETERMINED")

    def test_event_identity_does_not_substitute_for_ownership_exclusion(self):
        snap = snapshot()
        value = judgment(snap, case_attribution="MISMATCH",
                         negative_basis=basis(snap, kind="attribution_mismatch", dimensions=["event_identity", "symptom", "occurrence_context"]))
        with self.assertRaises(ModelError):
            check(value, snap)

    def test_negative_basis_must_have_exact_snapshot_citations(self):
        snap = snapshot()
        invalid = basis(snap)
        invalid["other_event"]["evidence"][0]["quote"] += "伪造引文"
        value = judgment(snap, event_relation="DIFFERENT_EVENT", negative_basis=invalid)
        with self.assertRaises(ModelError):
            check(value, snap)

    def test_negative_basis_cannot_cite_another_snapshot_segment(self):
        snap = snapshot()
        invalid = basis(snap)
        invalid["other_event"]["evidence"][0]["segment_id"] = "other-snapshot:segment-a"
        value = judgment(snap, event_relation="DIFFERENT_EVENT", negative_basis=invalid)
        with self.assertRaises(ModelError):
            check(value, snap)

    def test_negative_basis_context_must_occur_in_its_quote(self):
        snap = snapshot()
        invalid = basis(snap, context="另一事件EVT-B002在不存在于当前正文的日期发生不同故障。")
        value = judgment(snap, event_relation="DIFFERENT_EVENT", negative_basis=invalid)
        with self.assertRaises(ModelError):
            check(value, snap)

    def test_negative_basis_cannot_hide_citations_outside_top_level_evidence(self):
        snap = snapshot()
        value = judgment(snap, event_relation="DIFFERENT_EVENT", negative_basis=basis(snap),
                         evidence=[{"segment_id": "segment-a", "quote": "EVT-B002"}])
        with self.assertRaises(ModelError):
            check(value, snap)

    def test_root_cause_conflict_remains_unknown_instead_of_mismatch(self):
        snap = snapshot("本页定位量化算子输入未对齐，周报原文将根因归于all_reduce；当前需要确认两者冲突。")
        value = judgment(snap, support_level="CONFLICT", conflicting_dimensions=["root_cause"])
        value["claim_support"]["root_cause"] = "CONTRADICTED"
        result = check(value, snap)
        self.assertEqual(result["case_attribution"], "UNKNOWN")
        self.assertEqual(result["event_relation"], "UNDETERMINED")
        self.assertEqual(result["claim_support"]["root_cause"], "CONTRADICTED")

    def test_partial_capture_can_report_observed_conflicts_without_whole_document_claim(self):
        for status in ("PARTIAL", "CONTENT_CAPTURED"):
            with self.subTest(status=status):
                snap = snapshot("当前已采集片段定位为量化输入对齐问题，与周报根因冲突。", status=status)
                value = judgment(snap, support_level="CONFLICT", conflicting_dimensions=["root_cause"])
                value["claim_support"]["root_cause"] = "CONTRADICTED"
                result = check(value, snap)
                self.assertEqual(result["observation_scope"], "CAPTURED_CONTENT")
                self.assertEqual(result["event_relation"], "UNDETERMINED")

    def test_partial_capture_can_cite_positive_another_event_without_claiming_full_coverage(self):
        for status in ("PARTIAL", "CONTENT_CAPTURED"):
            snap = snapshot(status=status)
            result = check(judgment(snap, event_relation="DIFFERENT_EVENT", negative_basis=basis(snap)), snap)
            self.assertEqual(result["observation_scope"], "CAPTURED_CONTENT")

    def test_partial_or_selected_input_cannot_claim_full_document(self):
        combinations = [("PARTIAL", "FULL_CAPTURED_SNAPSHOT"), ("CONTENT_CAPTURED", "FULL_CAPTURED_SNAPSHOT"),
                        ("COMPLETE", "SELECTED_SEGMENTS"), ("COMPLETE", "SUMMARY_GROUP"), ("COMPLETE", None)]
        for status, scope in combinations:
            with self.subTest(status=status, scope=scope):
                snap = snapshot(status=status, scope=scope)
                with self.assertRaises(ModelError):
                    check(judgment(snap, observation_scope="FULL_DOCUMENT"), snap)

    def test_full_document_scope_requires_full_captured_complete_input(self):
        snap = snapshot(scope="FULL_CAPTURED_SNAPSHOT")
        result = check(judgment(snap, observation_scope="FULL_DOCUMENT"), snap)
        self.assertEqual(result["observation_scope"], "FULL_DOCUMENT")

    def test_direct_rejects_unresolved_claim_contradiction_without_dimension_flags(self):
        snap = snapshot("事件EVT-A001为甲客户周一的首token乱码，定位与原始归因存在待确认冲突。")
        for claim in ("symptom", "root_cause", "fix", "verification"):
            with self.subTest(claim=claim):
                value = judgment(snap, case_attribution="CONFIRMED", event_relation="SAME_EVENT", event_anchor="EVT-A001", support_level="DIRECT")
                value["claim_support"][claim] = "CONTRADICTED"
                with self.assertRaises(ModelError):
                    check(value, snap)

    def test_model_review_status_is_forbidden(self):
        snap = snapshot()
        with self.assertRaises(ModelError):
            check(judgment(snap, event_relation="DIFFERENT_EVENT", negative_basis=basis(snap), review_status="ACCEPT"), snap)

    def test_pipeline_forbids_model_accept_and_shares_negative_gates(self):
        snap = snapshot()
        for value in (judgment(snap, event_relation="DIFFERENT_EVENT"),
                      judgment(snap, event_relation="DIFFERENT_EVENT", negative_basis=basis(snap), review_status="ACCEPT")):
            with self.subTest(value=value), self.assertRaises((AuditError, ValidationError)):
                gate_judgment(source_case(), snap, value)

    def test_pipeline_positive_other_event_stays_needs_review(self):
        snap = snapshot()
        result = gate_judgment(source_case(), snap, judgment(snap, event_relation="DIFFERENT_EVENT", negative_basis=basis(snap)))
        self.assertEqual(result["review_status"], "NEEDS_REVIEW")

    def test_pipeline_rejects_direct_with_root_claim_contradiction(self):
        snap = snapshot("事件EVT-A001为甲客户周一的首token乱码，定位与原始归因存在待确认冲突。")
        value = judgment(snap, case_attribution="CONFIRMED", event_relation="SAME_EVENT", event_anchor="EVT-A001", support_level="DIRECT")
        value["claim_support"]["root_cause"] = "CONTRADICTED"
        with self.assertRaises(AuditError):
            gate_judgment(source_case(), snap, value)

    def test_invalid_negative_proposal_is_not_silently_rewritten(self):
        snap = snapshot()
        value = judgment(snap, case_attribution="MISMATCH")
        before = copy.deepcopy(value)
        with self.assertRaises(ModelError):
            check(value, snap)
        self.assertEqual(value, before)

    def test_mock_does_not_infer_negative_identity_from_technical_difference(self):
        snap = snapshot("本资料只出现rope算子，未显示原表客户字段，周报算子是all_reduce。")
        judge = MockJudge()
        result = judge.compare(source_case(), snap, judge.summarize(snap))
        self.assertEqual(result["case_attribution"], "UNKNOWN")
        self.assertEqual(result["event_relation"], "UNDETERMINED")


class NegativeBridgeGatesTests(unittest.TestCase):
    def setUp(self):
        from tests import test_bridge as fixtures
        self.fixture = fixtures.BridgeTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_bridge_rejects_model_accept_without_saving_result(self):
        from faultaudit.bridge import submit_model_results
        tasks = self.fixture.summary_done()
        returned = self.fixture.envelope(tasks[0])
        returned["result"]["review_status"] = "ACCEPT"
        count_before = len(self.fixture.store.records(self.fixture.run_id, "model_results"))
        with self.assertRaises((ModelError, AuditError, ValidationError)):
            submit_model_results(self.fixture.store, self.fixture.run_id, [returned])
        self.assertEqual(len(self.fixture.store.records(self.fixture.run_id, "model_results")), count_before)

    def test_bridge_rejects_original_event_as_other_event_without_saving_result(self):
        from faultaudit.bridge import submit_model_results
        identity = self.fixture.case["raw"]["事件编号"]
        context = f"资料明确描述事件{identity}，属于原记录同一次故障，甲客户周一推理首token乱码。"
        self.fixture.store.ingest_evidence(self.fixture.run_id, {**self.fixture.package, "text": context})
        tasks = self.fixture.summary_done()
        returned = self.fixture.envelope(tasks[0])
        segment = tasks[0]["payload"]["snapshot"]["segments"][0]
        ref = {"segment_id": segment["segment_id"], "quote": segment["text"]}
        returned["result"].update(event_relation="DIFFERENT_EVENT", support_level="PARTIAL", evidence=[ref],
            negative_basis={"other_event": {"positive_identity": identity, "context": context,
                            "dimensions": ["event_identity", "symptom", "occurrence_context"], "evidence": [ref]}})
        count_before = len(self.fixture.store.records(self.fixture.run_id, "model_results"))
        with self.assertRaises(ModelError):
            submit_model_results(self.fixture.store, self.fixture.run_id, [returned])
        self.assertEqual(len(self.fixture.store.records(self.fixture.run_id, "model_results")), count_before)
        self.assertEqual(self.fixture.store.records(self.fixture.run_id, "judgments"), [])
        self.assertEqual(self.fixture.store.events(self.fixture.run_id, "review"), [])

    def test_bridge_positive_other_event_remains_review_proposal(self):
        from faultaudit.bridge import submit_model_results
        from faultaudit.pipeline import report_data
        self.fixture.store.ingest_evidence(self.fixture.run_id, {**self.fixture.package, "text": OTHER_CONTEXT})
        tasks = self.fixture.summary_done()
        returned = self.fixture.envelope(tasks[0])
        snap = tasks[0]["payload"]["snapshot"]
        segment = snap["segments"][0]
        ref = {"segment_id": segment["segment_id"], "quote": segment["text"]}
        returned["result"].update(event_relation="DIFFERENT_EVENT", support_level="PARTIAL", evidence=[ref],
            negative_basis={"other_event": {"positive_identity": "EVT-B002", "context": OTHER_CONTEXT,
                            "dimensions": ["event_identity", "symptom", "occurrence_context"], "evidence": [ref]}})
        self.assertEqual(submit_model_results(self.fixture.store, self.fixture.run_id, [returned])["accepted"], 1)
        self.fixture.drive()
        values = report_data(self.fixture.store, self.fixture.run_id)["judgments"]
        self.assertEqual(values[0]["event_relation"], "DIFFERENT_EVENT")
        self.assertEqual(values[0]["review_status"], "NEEDS_REVIEW")


if __name__ == "__main__":
    unittest.main()
