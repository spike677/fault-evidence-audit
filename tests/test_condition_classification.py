"""Synthetic conditions-first boundaries; no real records or website access."""
import copy
import unittest

from faultaudit.store import AuditError
from faultaudit.trigger_assessment import CLASSIFICATION_FRAMEWORK, validate_assessment
from faultaudit.trigger_taxonomy import EXPECTED_IDS, builtin_user_branches
from faultaudit.trigger_report import build_workbook
from tests.condition_fixtures import condition_attempt
from tests.test_trigger_assessment import fixture, HASH
from tests.test_trigger_report import records


def attempt(text="INT32地址偏移溢出", role="INDEX_OR_OFFSET"):
    payload, response = fixture("INCREMENTAL")
    payload["classification_framework"] = CLASSIFICATION_FRAMEWORK
    payload["source_issue"] = None
    payload["subject"]["source_case"].update(raw={"故障原因": text}, cell_locations={"故障原因": "B2"})
    payload["taxonomy"] = {"items": [{"id": tid, "family_id": tid.rsplit(".", 1)[0],
        "definition": "合成条件 " + tid, "name": "合成条件", "requires": [], "skip_if": []} for tid in EXPECTED_IDS],
        "families": [], "branches": [{**b, "status": "DEFINED"} for b in builtin_user_branches()["branches"]]}
    offset = next(i for i in payload["taxonomy"]["items"] if i["id"] == "1.3.2")
    offset.update(definition="地址偏移超INT32范围", requires=["明确索引参数或地址公式"], skip_if=["仅数据且无索引或地址映射"])
    response["rows"] = [{"trigger_id": tid, "applicability": "UNKNOWN", "relation": "UNKNOWN",
        "evidence_basis": "UNKNOWN", "reason": "合成记录没有给出该条件"} for tid in EXPECTED_IDS]
    condition_attempt(payload, response)
    cell = {"field": "故障原因", "cell": "B2", "quote": text}
    response["condition_facts"] = [{"fact_id": "F", "statement": text, "role": role,
        "subject": "SOURCE_RECORD", "evidence_basis": "SOURCE_DEFINITION", "source_cells": [cell]}]
    return payload, response, cell


def label(response, tid, cell, applicability="PARTIAL", role_result="UNKNOWN"):
    row = next(r for r in response["rows"] if r["trigger_id"] == tid)
    row.update(applicability=applicability, relation="UNKNOWN", evidence_basis="SOURCE_DEFINITION",
        condition_fact_ids=["F"], source_cells=[cell], reason="按原单元格分类；资料及未给出的前提另记未知")
    for check in row["predicate_checks"]:
        if check["clause"].startswith("地址偏移"):
            check.update(result=role_result, source_cells=[cell] if role_result != "UNKNOWN" else [],
                         condition_fact_ids=["F"] if role_result != "UNKNOWN" else [])
    return row


def leaf(response, category, cell, applicability="APPLICABLE", facts=None):
    branch = next(b for b in response["external_branches"] if b["branch_id"] == category[0])
    item = next(c for c in branch["category_checks"] if c["category_id"] == category)
    item.update(applicability=applicability, condition_fact_ids=facts or ["F"], source_cells=[cell],
                reason="合成明确条件", unknowns=["同实参和同二进制尚未知"] if applicability == "PARTIAL" else [])
    branch.update(relation=applicability, category_ids=[category] if applicability == "APPLICABLE" else [])
    return item


class ConditionClassificationTests(unittest.TestCase):
    def test_offset_description_label_is_separate_from_evidence_and_adoption(self):
        payload, response, cell = attempt()
        label(response, "1.3.2", cell, role_result="MET")
        result = validate_assessment(payload, response, HASH)
        row = next(r for r in result["rows"] if r["trigger_id"] == "1.3.2")
        self.assertEqual((row["applicability"], row["relation"]), ("PARTIAL", "UNKNOWN"))
        self.assertEqual(result["condition_processing_status"], "ASSESSED_WITH_UNKNOWNS")
        self.assertEqual(result["decision"]["action"], "UNDETERMINED")
        self.assertFalse(result["review_required"])
        row["relation"] = "MATCH"
        response["rows"] = result["rows"]
        with self.assertRaises(AuditError): validate_assessment(payload, response, HASH)

    def test_all_requires_skip_checked_and_partial_cannot_claim_full_applicability(self):
        payload, response, cell = attempt()
        row = label(response, "1.3.2", cell, "APPLICABLE", "MET")
        with self.assertRaisesRegex(AuditError, "all conditions"): validate_assessment(payload, response, HASH)
        row["applicability"] = "PARTIAL"
        row["predicate_checks"].pop()
        with self.assertRaisesRegex(AuditError, "every complete"): validate_assessment(payload, response, HASH)

    def test_explicit_exclusion_is_not_a_positive_label(self):
        payload, response, cell = attempt()
        row = label(response, "1.3.2", cell)
        check = next(c for c in row["predicate_checks"] if c["clause_role"] == "EXCLUSION")
        check.update(result="MET", condition_fact_ids=["F"], source_cells=[cell])
        with self.assertRaisesRegex(AuditError, "exclusion"): validate_assessment(payload, response, HASH)

    def test_intermediate_inf_cannot_label_input_inf(self):
        payload, response, cell = attempt("输入有限，中间计算溢出为Inf", "INTERMEDIATE_VALUE")
        label(response, "1.7.2", cell)
        with self.assertRaisesRegex(AuditError, "proper input"): validate_assessment(payload, response, HASH)
        next(r for r in response["rows"] if r["trigger_id"] == "1.7.2").update(applicability="UNKNOWN", condition_fact_ids=[])
        self.assertFalse(validate_assessment(payload, response, HASH)["review_required"])

    def test_internal_nondeterminism_cannot_label_api_deterministic_control(self):
        payload, response, cell = attempt("内部ReduceMean累加不确定", "INTERNAL_COMPUTATION")
        label(response, "1.C.5", cell)
        with self.assertRaisesRegex(AuditError, "proper input"): validate_assessment(payload, response, HASH)

    def test_internal_sparse_path_cannot_label_input_mask(self):
        payload, response, cell = attempt("内部FA使用下三角Sparse计算", "INTERNAL_COMPUTATION")
        label(response, "1.8.2", cell)
        with self.assertRaisesRegex(AuditError, "proper input"): validate_assessment(payload, response, HASH)

    def test_platform_transition_can_classify_without_confirming_root(self):
        payload, response, cell = attempt("从910B迁移到310P", "PLATFORM")
        leaf(response, "2.1", cell)
        result = validate_assessment(payload, response, HASH)
        self.assertEqual(result["external_branches"][0]["category_ids"], ["2.1"])
        self.assertEqual(result["source_relation"], "UNKNOWN")
        self.assertEqual(result["decision"]["action"], "UNDETERMINED")

    def test_version_only_cannot_be_a_build_variant(self):
        payload, response, cell = attempt("版本9.0变成9.1", "VERSION")
        leaf(response, "2.3", cell)
        with self.assertRaisesRegex(AuditError, "version-only"): validate_assessment(payload, response, HASH)
        payload, response, cell = attempt("同一源码分别以Debug和Release构建，产物路径不同", "BUILD_VARIANT")
        leaf(response, "2.3", cell)
        self.assertFalse(validate_assessment(payload, response, HASH)["review_required"])

    def test_race_keeps_unknown_same_args_binary_until_stated(self):
        payload, response, cell = attempt("多核搬运缺少同步", "SYNC_RACE")
        leaf(response, "3.3", cell)
        with self.assertRaisesRegex(AuditError, "same arguments"): validate_assessment(payload, response, HASH)
        leaf(response, "3.3", cell, "PARTIAL")
        validate_assessment(payload, response, HASH)
        for key in ("SAME_ARGUMENTS", "SAME_BINARY"):
            response["condition_facts"].append({**copy.deepcopy(response["condition_facts"][0]), "fact_id": key, "role": key})
        leaf(response, "3.3", cell, facts=["F", "SAME_ARGUMENTS", "SAME_BINARY"])
        validate_assessment(payload, response, HASH)

    def test_training_record_still_has_all_condition_attempts(self):
        payload, response, cell = attempt("训练阶段发生INT32地址偏移溢出")
        label(response, "1.3.2", cell)
        result = validate_assessment(payload, response, HASH)
        self.assertEqual(len(result["rows"]), 42)
        self.assertEqual(sum(len(b["category_checks"]) for b in result["external_branches"]), 6)

    def test_unknown_does_not_force_branch_fallback(self):
        payload, response, _ = attempt("未定位故障", "UNKNOWN")
        result = validate_assessment(payload, response, HASH)
        self.assertTrue(all(r["applicability"] == "UNKNOWN" for r in result["rows"]))
        self.assertTrue(all(b["relation"] == "UNKNOWN" for b in result["external_branches"]))

    def test_scope_and_source_cell_cannot_be_borrowed(self):
        payload, response, cell = attempt()
        label(response, "1.3.2", cell)
        response["condition_facts"][0]["source_cells"][0]["cell"] = "B3"
        with self.assertRaisesRegex(AuditError, "immutable source"): validate_assessment(payload, response, HASH)
        response["condition_facts"][0]["source_cells"][0]["cell"] = "B2"
        response["condition_facts"][0].update(subject="CURRENT_ISSUE", evidence_basis="SOURCE_REPORTED", source_cells=[],
            evidence=[{"segment_id": "wrong-subissue", "quote": "INT32地址偏移溢出"}])
        with self.assertRaisesRegex(AuditError, "issue facts"): validate_assessment(payload, response, HASH)

    def test_unbound_candidate_cannot_label_original_but_linked_original_can(self):
        payload, response, cell = attempt()
        web = {"segment_id": "S:s1", "quote": "INT32地址偏移溢出"}
        payload["source_issue"] = {"snapshot": {"status": "CONTENT_CAPTURED", "segments": [dict(web, text=web["quote"])]},
            "facts": [{"evidence": [web]}], "reference_relation": "SEARCH_DISCOVERED"}
        response["condition_facts"][0].update(subject="CURRENT_ISSUE", evidence_basis="SOURCE_REPORTED", source_cells=[], evidence=[web])
        row = label(response, "1.3.2", cell)
        row.update(evidence_basis="SOURCE_REPORTED", source_cells=[], evidence=[web])
        with self.assertRaisesRegex(AuditError, "Unbound candidate"): validate_assessment(payload, response, HASH)
        payload["source_issue"]["reference_relation"] = "SOURCE_CELL_LINKED"
        result = validate_assessment(payload, response, HASH)
        self.assertEqual(result["source_relation"], "UNKNOWN")

    def test_same_condition_different_mechanisms_not_merged(self):
        payload, response, cell = attempt()
        label(response, "1.3.2", cell)
        response["details"] = [{"detail_id": did, "name": did, "mechanism": mechanism,
            "evidence_basis": "SOURCE_DEFINITION", "source_cells": [cell]} for did, mechanism in (
                ("A", "合成步长整数乘法溢出"), ("B", "合成缓存偏移截断"))]
        result = validate_assessment(payload, response, HASH)
        self.assertEqual(len(result["details"]), 2)

    def test_report_conditions_first_unknowns_and_multi_labels_count_separately(self):
        from tests.test_trigger_report import fixture as report_fixture
        data = report_fixture()
        data["classification_framework"] = CLASSIFICATION_FRAMEWORK
        first = data["assessments"][0]
        data["assessments"].append({**copy.deepcopy(first), "assessment_id": "A3", "issue_index": 1})
        workbook = build_workbook(data)
        names = [s["name"] for s in workbook["sheets"]]
        self.assertEqual(names[:4], ["条件分类索引", "条件事实", "42项条件分类", "Branch2和3"])
        self.assertLess(names.index("42项条件分类"), names.index("机理明细"))
        first_columns = workbook["sheets"][0]["columns"]
        self.assertLess(first_columns.index("42项适用"), first_columns.index("来源文件"))
        stats = {r["指标"]: r["值"] for r in records(workbook, "运行统计")}
        self.assertEqual((stats["来源记录数量"], stats["条件分类尝试来源数"], stats["条件分类子问题评估数"]), (3, 2, 3))
        self.assertEqual((stats["42项描述适用标签数"], stats["描述正向条件对数"]), (6, 4))
        self.assertEqual((stats["描述适用触发类数"], stats["有描述正向标签的来源数"]), (2, 2))
        self.assertGreater(stats["42项描述未知数"], 0)

    def test_frozen_init_index_and_before_after_are_separate_dimensions(self):
        from tests.test_trigger_report import fixture as report_fixture
        data = report_fixture()
        old = copy.deepcopy(data)
        data.update(phase="INCREMENTAL", classification_framework=CLASSIFICATION_FRAMEWORK,
            baseline={"mode_ids": ["M1"], "classification_framework": CLASSIFICATION_FRAMEWORK, "condition_index": [{**data["assessments"][0],
                **copy.deepcopy(data["assessments"][0]["result"]), "source_case": data["subjects"][0]["source_case"], "mode_id": "M1"}]},
            previous_classification=old)
        book = build_workbook(data)
        self.assertEqual(len(records(book, "Init42项核对")), 42)
        init_columns = next(s["columns"] for s in book["sheets"] if s["name"] == "Init42项核对")
        self.assertEqual(init_columns[:4], ["模式编号", "触发类编号", "触发类名称", "描述条件归类"])
        self.assertEqual(records(book, "分类前后对照")[0]["旧证据MATCH数"], 2)
        self.assertIn("不同维度", records(book, "分类前后对照")[0]["对比口径"])
        data["baseline"]["status"] = "STALE"
        self.assertNotIn("Init42项核对", [s["name"] for s in build_workbook(data)["sheets"]])


if __name__ == "__main__":
    unittest.main()
