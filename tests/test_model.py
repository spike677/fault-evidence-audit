"""Pure offline result validation; no HTTP servers, endpoints or credentials."""
from __future__ import annotations

import ast
import copy
import json
import unittest
from pathlib import Path

import faultaudit.model as model_module
from faultaudit.model import MockJudge, ModelError, PendingModelResult, _json_loads, validate_task_result


def snapshot(**changes):
    text = "事件 DEMO-001 的 all_reduce 在 PCIe 场景存在精度问题。"
    value = {"snapshot_id": "SNAP-1", "url": "https://example.invalid/wiki/1", "title": "定位记录",
             "text": text, "status": "COMPLETE", "components": {"body": "COMPLETE"},
             "segments": [{"segment_id": "S1", "text": text, "start": 0, "end": len(text)}], "is_synthetic": False}
    value.update(changes)
    return value


def case(**changes):
    value = {"case_id": "CASE-1", "external_id": "CASE-DELTA", "raw": {}, "description": "输出乱码",
             "customer_model": "Model-X", "operator_raw": "all_reduce", "root_cause_raw": "原始归因",
             "root_cause_origin": "LEGACY_DERIVED_UNKNOWN"}
    value.update(changes)
    return value


def summary():
    return {"snapshot_id": "SNAP-1", "issues": [{"label": "精度问题", "facts": [
        {"field": "operator", "value": "all_reduce", "evidence": [{"segment_id": "S1", "quote": "all_reduce"}]}]}],
        "unknown_fields": ["version"]}


def judgment(**changes):
    value = {"case_id": "CASE-1", "snapshot_id": "SNAP-1", "case_attribution": "UNKNOWN",
             "event_relation": "UNDETERMINED", "pattern_relation": "POSSIBLY_RELATED", "support_level": "PARTIAL",
             "matched_dimensions": ["operator"], "conflicting_dimensions": [], "unknown_dimensions": ["event"],
             "evidence": [{"segment_id": "S1", "quote": "all_reduce"}], "event_anchor": "",
             "short_reason": "只有同算子证据，事件未知", "missing_information": ["事件身份"],
             "claim_support": {"symptom": "UNKNOWN", "root_cause": "PARTIAL", "fix": "NOT_MENTIONED", "verification": "NOT_MENTIONED"}}
    value.update(changes)
    return value

class MockJudgeTests(unittest.TestCase):
    def test_real_evidence_never_confirms_mock(self):
        judge = MockJudge()
        snap = snapshot()
        result = judge.compare(case(raw={"事件编号": "DEMO-001"}), snap, judge.summarize(snap))
        self.assertEqual(result["event_relation"], "UNDETERMINED")
        self.assertEqual(result["support_level"], "PENDING")
        self.assertEqual(result["model_mode"], "mock")

    def test_synthetic_positive_requires_explicit_demo_anchor(self):
        judge = MockJudge()
        snap = snapshot(is_synthetic=True)
        result = judge.compare(case(raw={"事件编号": "DEMO-001"}), snap, judge.summarize(snap))
        self.assertEqual(result["event_relation"], "SAME_EVENT")
        self.assertEqual(result["support_level"], "DIRECT")
        self.assertIn("合成", result["short_reason"])
        self.assertEqual(result["claim_support"]["root_cause"], "UNKNOWN")

    def test_same_url_or_operator_does_not_form_anchor(self):
        judge = MockJudge()
        snap = snapshot(is_synthetic=True)
        result = judge.compare(case(raw={"DTS": "DEMO-001"}), snap, judge.summarize(snap))
        self.assertEqual(result["event_relation"], "UNDETERMINED")

    def test_partial_cannot_be_direct_even_in_demo(self):
        judge = MockJudge()
        snap = snapshot(is_synthetic=True, status="PARTIAL")
        result = judge.compare(case(raw={"事件编号": "DEMO-001"}), snap, judge.summarize(snap))
        self.assertEqual(result["support_level"], "PENDING")

    def test_missing_body_is_pending(self):
        judge = MockJudge()
        snap = snapshot(status="AUTH_REQUIRED", text="", segments=[])
        summ = judge.summarize(snap)
        self.assertEqual(summ["issues"], [])
        self.assertEqual(judge.compare(case(), snap, summ)["support_level"], "PENDING")

    def test_full_98_catalog_is_unknown(self):
        items = [{"item_id": str(i)} for i in range(98)]
        result = MockJudge().map_catalog(case(), [], items)
        self.assertEqual(len(result["catalog_results"]), 98)
        self.assertTrue(all(row["result"] == "UNDETERMINED" for row in result["catalog_results"]))
        self.assertEqual(result["scope"], "FULL_CATALOG")

    def test_summary_preserves_each_segment_without_guessing(self):
        result = MockJudge().summarize(snapshot())
        self.assertEqual(result["issues"][0]["facts"][0]["field"], "raw_observation")
        self.assertIn("mechanism", result["unknown_fields"])

    def test_persisted_summary_metadata_is_not_semantic_input(self):
        judge = MockJudge()
        snap = snapshot()
        summ = judge.summarize(snap)
        summ.update(task_id="TASK-1", blocks_processed=1, segments_processed=1)
        result = judge.compare(case(), snap, summ)
        self.assertEqual(result["support_level"], "PENDING")

    def test_segment_from_another_body_is_rejected(self):
        snap = snapshot()
        snap["segments"][0]["text"] = "正文之外的伪造段落"
        with self.assertRaises(ModelError) as raised:
            MockJudge().summarize(snap)
        self.assertEqual(raised.exception.code, "invalid_segments")



def stamped(value):
    return {**value, "model_mode": "opencode", "model_id": "site-reported-model"}


class OfflineValidationTests(unittest.TestCase):
    def validate_summary(self, value, snap=None):
        return validate_task_result("summarize", stamped(value), snapshot=snap or snapshot())

    def validate_judgment(self, value, source=None, snap=None):
        return validate_task_result("compare", stamped(value), case=source or case(), snapshot=snap or snapshot())

    def catalog(self, rows, *, judgments=None, items=None, overall="UNDETERMINED"):
        value = stamped({"case_id": "CASE-1", "catalog_results": rows, "overall": overall, "scope": "FULL_CATALOG"})
        return validate_task_result("map_catalog", value, case=case(), judgments=judgments or [], items=items or [{"item_id": "1", "mechanism": "rounding"}])

    def test_core_has_no_network_or_credential_client(self):
        tree = ast.parse(Path(model_module.__file__).read_text(encoding="utf-8"))
        forbidden = {"os", "socket", "http", "urllib", "requests", "httpx", "openai", "aiohttp"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported.intersection(forbidden))
        self.assertFalse(hasattr(model_module, "DeepSeekJudge"))

    def test_pending_result_is_explicit_and_has_task_identity(self):
        pending = PendingModelResult("TASK-001", "summarize")
        self.assertEqual(pending.code, "MODEL_RESULT_PENDING")
        self.assertEqual(pending.task_id, "TASK-001")
        self.assertEqual(pending.operation, "summarize")

    def test_summary_is_validated_without_mutation(self):
        value = stamped(summary())
        before = copy.deepcopy(value)
        result = validate_task_result("summary", value, snapshot=snapshot())
        self.assertEqual(result["model_id"], "site-reported-model")
        self.assertEqual(value, before)

    def test_wrong_snapshot_id_rejected(self):
        value = summary()
        value["snapshot_id"] = "OTHER"
        with self.assertRaises(ModelError) as raised:
            self.validate_summary(value)
        self.assertEqual(raised.exception.code, "identity_mismatch")

    def test_fabricated_quote_rejected(self):
        value = summary()
        value["issues"][0]["facts"][0]["evidence"][0]["quote"] = "invented mechanism"
        with self.assertRaises(ModelError) as raised:
            self.validate_summary(value)
        self.assertEqual(raised.exception.code, "invalid_citation")

    def test_quote_from_other_segment_rejected(self):
        value = summary()
        value["issues"][0]["facts"][0]["evidence"][0]["segment_id"] = "OTHER-SEGMENT"
        with self.assertRaises(ModelError):
            self.validate_summary(value)

    def test_facts_without_citations_rejected(self):
        value = summary()
        value["issues"][0]["facts"][0]["evidence"] = []
        with self.assertRaises(ModelError):
            self.validate_summary(value)

    def test_label_without_facts_is_not_summary(self):
        value = summary()
        value["issues"][0]["facts"] = []
        with self.assertRaises(ModelError) as raised:
            self.validate_summary(value)
        self.assertEqual(raised.exception.code, "invalid_summary")

    def test_unavailable_body_cannot_supply_facts(self):
        with self.assertRaises(ModelError):
            self.validate_summary(summary(), snapshot(status="AUTH_REQUIRED"))

    def test_empty_summary_for_unavailable_body_is_allowed(self):
        result = self.validate_summary({"snapshot_id": "SNAP-1", "issues": [], "unknown_fields": ["body"]}, snapshot(status="AUTH_REQUIRED", text="", segments=[]))
        self.assertEqual(result["issues"], [])

    def test_same_event_without_explicit_or_specific_anchor_rejected(self):
        value = judgment(case_attribution="CONFIRMED", event_relation="SAME_EVENT", event_anchor="DEMO-001")
        value["evidence"] = [{"segment_id": "S1", "quote": "事件 DEMO-001"}]
        with self.assertRaises(ModelError) as raised:
            self.validate_judgment(value, case(raw={"DTS": "DEMO-001"}))
        self.assertEqual(raised.exception.code, "unverified_event_anchor")

    def test_explicit_event_anchor_passes_as_proposal(self):
        value = judgment(case_attribution="CONFIRMED", event_relation="SAME_EVENT", event_anchor="DEMO-001", support_level="DIRECT")
        value["evidence"] = [{"segment_id": "S1", "quote": "事件 DEMO-001 的 all_reduce"}]
        result = self.validate_judgment(value, case(raw={"事件编号": "DEMO-001"}))
        self.assertEqual(result["event_relation"], "SAME_EVENT")
        self.assertNotEqual(result.get("review_status"), "ACCEPT")

    def test_partial_snapshot_cannot_be_direct(self):
        value = judgment(case_attribution="CONFIRMED", event_relation="SAME_EVENT", event_anchor="DEMO-001", support_level="DIRECT")
        value["evidence"] = [{"segment_id": "S1", "quote": "事件 DEMO-001"}]
        with self.assertRaises(ModelError) as raised:
            self.validate_judgment(value, case(raw={"事件编号": "DEMO-001"}), snapshot(status="PARTIAL"))
        self.assertEqual(raised.exception.code, "ungrounded_direct_support")

    def test_specific_corroborated_signature_without_event_number(self):
        anchor = "Model-X在TP6输出乱码而TP3回答正常"
        text = anchor + "；机制是示例量化参数不匹配，触发条件为TP6。"
        snap = snapshot(text=text, segments=[{"segment_id": "S1", "text": text, "start": 0, "end": len(text)}])
        source = case(raw={"问题描述": anchor, "根因": "示例量化参数不匹配"}, description=anchor)
        value = judgment(case_attribution="CONFIRMED", event_relation="SAME_EVENT", event_anchor=anchor,
                         support_level="DIRECT", matched_dimensions=["symptom", "mechanism", "trigger"],
                         evidence=[{"segment_id": "S1", "quote": text}])
        self.assertEqual(self.validate_judgment(value, source, snap)["event_relation"], "SAME_EVENT")

    def test_operator_or_shared_link_cannot_be_incident_signature(self):
        for anchor in ("all_reduce", "https://example.invalid/wiki/shared"):
            with self.subTest(anchor=anchor):
                text = "此处仅共享引用 " + anchor
                snap = snapshot(text=text, segments=[{"segment_id": "S1", "text": text, "start": 0, "end": len(text)}])
                source = case(raw={"问题描述": anchor}, description=anchor)
                value = judgment(case_attribution="CONFIRMED", event_relation="SAME_EVENT", event_anchor=anchor,
                                 support_level="DIRECT", matched_dimensions=["symptom", "mechanism", "trigger"],
                                 evidence=[{"segment_id": "S1", "quote": text}])
                with self.assertRaises(ModelError) as raised:
                    self.validate_judgment(value, source, snap)
                self.assertEqual(raised.exception.code, "unverified_event_anchor")

    def test_pattern_assertion_without_citation_rejected(self):
        value = judgment(evidence=[], support_level="PENDING", matched_dimensions=[], pattern_relation="SAME_PATTERN")
        value["claim_support"] = dict.fromkeys(("symptom", "root_cause", "fix", "verification"), "UNKNOWN")
        with self.assertRaises(ModelError) as raised:
            self.validate_judgment(value)
        self.assertEqual(raised.exception.code, "invalid_citation")

    def test_missing_claim_dimension_rejected(self):
        value = judgment()
        del value["claim_support"]["root_cause"]
        with self.assertRaises(ModelError):
            self.validate_judgment(value)

    def test_wrong_case_identity_rejected(self):
        with self.assertRaises(ModelError) as raised:
            self.validate_judgment(judgment(case_id="OTHER"))
        self.assertEqual(raised.exception.code, "identity_mismatch")

    def test_catalog_missing_or_duplicate_item_rejected(self):
        row = {"item_id": "1", "result": "UNDETERMINED", "reason": "待核验", "evidence": []}
        for rows in ([], [row, row]):
            with self.subTest(rows=len(rows)):
                with self.assertRaises(ModelError) as raised:
                    self.catalog(rows)
                self.assertEqual(raised.exception.code, "incomplete_catalog")

    def test_unconfirmed_case_cannot_be_not_covered(self):
        with self.assertRaises(ModelError) as raised:
            self.catalog([{"item_id": "1", "result": "NOT_COVERED", "reason": "未知", "evidence": []}], overall="NOT_COVERED")
        self.assertEqual(raised.exception.code, "unconfirmed_catalog")

    def test_all_98_catalog_items_can_return_unknown(self):
        items = [{"item_id": str(i)} for i in range(98)]
        rows = [{"item_id": item["item_id"], "result": "UNDETERMINED", "reason": "事件未确认", "evidence": []} for item in items]
        self.assertEqual(len(self.catalog(rows, items=items)["catalog_results"]), 98)

    def confirming(self):
        confirmed = judgment(case_attribution="CONFIRMED", event_relation="SAME_EVENT", support_level="DIRECT", event_anchor="DEMO-001")
        confirmed["claim_support"]["root_cause"] = "SUPPORTED"
        return confirmed

    def test_missing_catalog_mechanism_cannot_be_excluded(self):
        rows = [{"item_id": "1", "result": "NOT_COVERED", "reason": "无法对应", "evidence": []}]
        with self.assertRaises(ModelError) as raised:
            self.catalog(rows, judgments=[self.confirming()], items=[{"item_id": "1", "mechanism": ""}], overall="NOT_COVERED")
        self.assertEqual(raised.exception.code, "ungrounded_catalog")

    def test_mismatch_citations_cannot_be_recycled_into_coverage(self):
        conflict = judgment(case_attribution="MISMATCH", support_level="CONFLICT", evidence=[{"segment_id": "S2", "quote": "different fault"}])
        rows = [{"item_id": "1", "result": "COVERED", "reason": "错误复用", "evidence": conflict["evidence"]}]
        with self.assertRaises(ModelError) as raised:
            self.catalog(rows, judgments=[self.confirming(), conflict], overall="COVERED")
        self.assertEqual(raised.exception.code, "ungrounded_catalog")

    def test_human_rejected_direct_cannot_establish_coverage(self):
        rejected = self.confirming()
        rejected["review_status"] = "REJECT"
        rows = [{"item_id": "1", "result": "COVERED", "reason": "错误使用人工拒绝判断", "evidence": rejected["evidence"]}]
        with self.assertRaises(ModelError) as raised:
            self.catalog(rows, judgments=[rejected], overall="COVERED")
        self.assertEqual(raised.exception.code, "unconfirmed_catalog")

    def test_actual_model_metadata_required(self):
        value = stamped(summary())
        value["model_id"] = " "
        with self.assertRaises(ModelError) as raised:
            validate_task_result("summarize", value, snapshot=snapshot())
        self.assertEqual(raised.exception.code, "invalid_response")

    def test_missing_context_and_unknown_operation_explicit(self):
        for operation, expected in (("summarize", "missing_context"), ("compare", "missing_context"), ("map_catalog", "missing_context"), ("other", "unknown_operation")):
            with self.subTest(operation=operation):
                with self.assertRaises(ModelError) as raised:
                    validate_task_result(operation, stamped(summary()))
                self.assertEqual(raised.exception.code, expected)

    def test_result_must_be_object_and_valid_schema(self):
        with self.assertRaises(ModelError):
            validate_task_result("summarize", [], snapshot=snapshot())
        with self.assertRaises(ModelError):
            validate_task_result("summarize", stamped({"snapshot_id": "SNAP-1", "issues": "invalid"}), snapshot=snapshot())

    def test_json_parser_rejects_duplicate_keys_and_nonfinite_numbers(self):
        for value in ('{"id":1,"id":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    _json_loads(value)
        self.assertEqual(_json_loads('{"ok":true}'), {"ok": True})


if __name__ == "__main__":
    unittest.main()
