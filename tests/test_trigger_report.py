"""Synthetic trigger-report projection tests, no state or site access."""
import copy
import unittest

from faultaudit.trigger_report import COVERAGE_SCOPE, build_workbook


def records(workbook, sheet):
    value = next(s for s in workbook["sheets"] if s["name"] == sheet)
    return [dict(zip(value["columns"], row)) for row in value["rows"]]


def fixture():
    subjects = [{"subject_id": "SUB" + str(i), "case_id": "C" + str(i), "mode_id": "M" + str(i),
        "subject_kind": "MODE_ENTRY", "source_case": {"external_id": "MODE-" + str(i), "source_file": "synthetic.xlsx",
            "sheet": "Modes", "row": i + 1, "description": "synthetic mode", "root_cause_raw": "original cause",
            "cell_locations": {"模式名称": "A" + str(i + 1)}}} for i in range(1, 4)]
    result = {"rows": [{"trigger_id": "T" + str(i), "applicability": "APPLICABLE" if i < 2 else "UNKNOWN",
        "relation": "MATCH" if i < 2 else "UNKNOWN", "evidence_basis": "SOURCE_REPORTED" if i < 2 else "UNKNOWN",
        "predicate_checks": [{"clause": "complete predicate", "result": "MET", "evidence": [{"segment_id": "S:s1", "quote": "exact text"}]}] if i < 2 else [],
        "reason": "synthetic", "detail_ids": ["D1"] if i < 2 else []} for i in range(42)],
        "details": [{"detail_id": "D1", "mode_id": "M1", "name": "specific detail", "mechanism": "concrete failure",
            "evidence_basis": "SOURCE_REPORTED", "conditions": ["specific shape"], "trigger_ids": ["T0", "T1"],
            "evidence": [{"segment_id": "S:s1", "quote": "exact text"}], "unknowns": ["no local execution"]}],
        "external_branches": [{"branch_id": "2", "relation": "UNKNOWN", "category_ids": [], "reason": "unknown"},
                              {"branch_id": "3", "relation": "UNKNOWN", "category_ids": [], "reason": "unknown"}],
        "source_relation": "MATCH", "processing_status": "AUTO_PROCESSED", "review_required": False,
        "decision": {"action": "INIT_ONLY"}}
    assessments = [{"assessment_id": "A1", "subject_id": "SUB1", "case_id": "C1", "snapshot_id": "S", "issue_index": 0, "result": result},
        {"assessment_id": "A2", "subject_id": "SUB2", "case_id": "C2", "snapshot_id": "S", "issue_index": 0, "result": copy.deepcopy(result)}]
    return {"run_id": "synthetic", "phase": "INIT", "subjects": subjects, "assessments": assessments,
        "taxonomy": {"items": [{"id": "T" + str(i), "family_id": "F" + str(i % 9), "name": "trigger", "definition": "complete predicate"} for i in range(42)],
            "branches": [{"branch_id": "2", "status": "DEFINED", "name": "implementation", "definition": "fixed instance may be zero",
                          "provenance": "synthetic", "categories": [{"id": "2.1", "name": "platform"}]},
                         {"branch_id": "3", "status": "UNDEFINED"}]},
        "wiki_checks": {"C1": {"status": "FOUND"}, "C2": {"status": "FOUND"}, "C3": {"status": "BLOCKED", "reason": "login required"}}}


class TriggerReportTests(unittest.TestCase):
    def test_multilabel_counts_have_explicit_separate_units(self):
        workbook = build_workbook(fixture())
        stats = {r["指标"]: r for r in records(workbook, "运行统计")}
        self.assertEqual(stats["原模式数量"]["值"], 3)
        self.assertEqual(stats["当前分类判断数量"]["值"], 2)
        self.assertEqual(stats["涉及资料子问题数量"]["值"], 1)
        self.assertEqual(stats["有匹配证据的触发类数"]["值"], 2)
        self.assertEqual(stats["逐项匹配标签数"]["值"], 4)
        self.assertIn("不能当作故障数量", stats["逐项匹配标签数"]["口径"])
        self.assertEqual(len(records(workbook, "42类覆盖详情")), 84)

    def test_unassessed_mode_and_original_anchors_are_retained(self):
        workbook = build_workbook(fixture())
        rows = records(workbook, "模式初始化总览")
        self.assertEqual(len(rows), 3)
        row = next(r for r in rows if r["case_id"] == "C3")
        self.assertEqual((row["处理状态"], row["Wiki检查"], row["需人工裁决"]), ("UNASSESSED", "BLOCKED", "否"))
        self.assertEqual((row["原编号"], row["来源文件"], row["Sheet"], row["原始行"]), ("MODE-3", "synthetic.xlsx", "Modes", 4))
        self.assertEqual(row["原故障原因"], "original cause")
        self.assertTrue(any(r["类型"] == "UNASSESSED" for r in records(workbook, "证据与缺口")))

    def test_stale_and_duplicate_assessments_do_not_repeat_counts(self):
        data = fixture()
        data["assessments"].extend([copy.deepcopy(data["assessments"][0]), {**copy.deepcopy(data["assessments"][0]), "assessment_id": "OLD", "is_stale": True}])
        workbook = build_workbook(data)
        self.assertEqual(len(records(workbook, "42类覆盖详情")), 84)
        stats = {r["指标"]: r["值"] for r in records(workbook, "运行统计")}
        self.assertEqual(stats["当前分类判断数量"], 2)

    def test_detail_identity_namespaces_per_response(self):
        workbook = build_workbook(fixture())
        self.assertEqual({r["明细编号"] for r in records(workbook, "机理明细")}, {"A1:D1", "A2:D1"})
        row = records(workbook, "42类覆盖详情")[0]
        self.assertEqual(row["关联明细编号"], "A1:D1")
        self.assertIn("S:s1: exact text", row["完整谓词检查"])

    def test_branches_separate_and_execution_never_claimed(self):
        workbook = build_workbook(fixture())
        stats = {r["指标"]: r["值"] for r in records(workbook, "运行统计")}
        self.assertEqual((stats["42类唯一项数"], stats["输入触发族数"]), (42, 9))
        self.assertEqual(stats["本地执行验证"], "未执行")
        self.assertTrue(all(r["计入42类"] == "否" for r in records(workbook, "Branch2和3")))
        self.assertTrue(any(r["对应判断"] == "UNDEFINED" for r in records(workbook, "Branch2和3")))
        self.assertTrue(all(r["覆盖范围"] == COVERAGE_SCOPE for r in records(workbook, "42类覆盖详情")))

    def test_incremental_conflicts_only_are_human_and_input_unchanged(self):
        data = fixture()
        data["phase"] = "INCREMENTAL"
        data["assessments"][0]["result"].update(review_required=True, processing_status="EXCEPTION", review_reasons=["grounded technical conflict"])
        data["resources"] = [{"case_id": "C1", "ref_id": "R1", "url": "https://example.invalid/wiki/a", "origin": "SEARCH_DISCOVERED", "location": "A2", "status": "PARTIAL"}]
        before = copy.deepcopy(data)
        workbook = build_workbook(data)
        self.assertEqual(data, before)
        self.assertEqual(records(workbook, "故障分类总览")[0]["需人工裁决"], "是")
        gaps = records(workbook, "证据与缺口")
        self.assertTrue(any(r["需人工裁决"] == "是" and r["说明"] == "grounded technical conflict" for r in gaps))
        self.assertTrue(any(r["最初来源"] == "SEARCH_DISCOVERED" for r in gaps))

    def test_empty_data_still_has_six_named_sheets(self):
        workbook = build_workbook({})
        self.assertEqual(len(workbook["sheets"]), 6)
        self.assertEqual(records(workbook, "模式初始化总览"), [])
        self.assertEqual(records(workbook, "42类覆盖详情"), [])

    def test_projection_gaps_do_not_duplicate_generated_gaps(self):
        data = fixture()
        data["assessments"][0]["result"].update(review_required=True, processing_status="EXCEPTION", review_reasons=["specific conflict"])
        data["gaps"] = [{"case_id": "C3", "kind": "UNASSESSED", "reason": "No current classification result"},
            {"case_id": "C3", "kind": "WIKI_BLOCKED", "reason": "login required"},
            {"case_id": "C1", "kind": "FACT_CONFLICT", "reason": "specific conflict", "review_required": True}]
        data["gaps"].append(copy.deepcopy(data["gaps"][0]))
        rows = records(build_workbook(data), "证据与缺口")
        self.assertEqual(sum(r["类型"] == "UNASSESSED" for r in rows), 1)
        self.assertEqual(sum(r["类型"] == "WIKI_BLOCKED" for r in rows), 1)
        self.assertEqual(sum(r["类型"] == "FACT_CONFLICT" for r in rows), 1)

    def test_partial_capture_and_unknowns_do_not_require_human_review(self):
        data = fixture()
        data["assessments"][0]["result"]["processing_status"] = "PENDING"
        data["assessments"][0]["result"]["rows"][0].update(relation="PARTIAL")
        data["gaps"] = [{"case_id": "C1", "kind": "CAPTURE_PARTIAL", "reason": "comments not captured"},
                        {"case_id": "C1", "kind": "TRIGGER_UNKNOWNS", "reason": "missing exact dimensions"}]
        workbook = build_workbook(data)
        self.assertEqual(records(workbook, "模式初始化总览")[0]["需人工裁决"], "否")
        self.assertTrue(all(r["需人工裁决"] == "否" for r in records(workbook, "证据与缺口")))
        self.assertIn("PARTIAL", {r["对应判断"] for r in records(workbook, "42类覆盖详情")})


if __name__ == "__main__":
    unittest.main()
