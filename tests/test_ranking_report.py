"""Synthetic ranking/report projection tests; no workbook authoring or site access."""
from __future__ import annotations

import copy
import unittest

from faultaudit.ranking_report import RANKING_BASIS, build_ranked_workbook


def records(workbook, name):
    sheet = next(s for s in workbook["sheets"] if s["name"] == name)
    return [dict(zip(sheet["columns"], row)) for row in sheet["rows"]]


class RankingReportTests(unittest.TestCase):
    def sample(self):
        return {"run": {"run_id": "synthetic-run"}, "cases": [
            {"case_id": "C2", "external_id": "WB-SYN-2", "source_file": "B.xlsx", "sheet": "Cases", "row": 3,
             "cell_locations": {"问题描述": "D3", "根因": "E3"}, "raw": {"统一ID": "WB-SYN-2", "问题描述": "original two", "根因": "raw two"}},
            {"case_id": "C1", "external_id": "WB-SYN-1", "source_file": "A.xlsx", "sheet": "Cases", "row": 2,
             "cell_locations": {"问题描述": "D2", "根因": "E2"}, "root_cause": "invented model cause",
             "raw": {"统一ID": "WB-SYN-1", "问题描述": "original one", "根因": "raw one", "wiki": "https://example.invalid/wiki/a"}}],
            "references": [{"ref_id": "R1", "case_id": "C1", "url": "https://example.invalid/wiki/a", "origin": "ORIGINAL_WEEKLY",
                "location": "Cases!F2 (row 2)", "source_grade": "SOURCE_CELL_LINKED", "required": True}],
            "snapshots": [{"snapshot_id": "S1", "url": "https://example.invalid/wiki/a", "status": "PARTIAL", "required": True}],
            "summaries": [], "judgments": [], "mappings": [], "tasks": [], "catalog": [{"item_id": "BASE-1"}],
            "evidence_plans": {"cases": [{"case_id": "C1", "selected_ref_ids": ["R1"], "path": "SOURCE_CELL_LINKED"}]}}

    def test_single_ranked_case_row_and_source_ids_preserve_original_values(self):
        data = self.sample()
        before = copy.deepcopy(data)
        workbook = build_ranked_workbook(data)
        self.assertEqual(len(workbook["sheets"]), 5)
        self.assertEqual(workbook["sheets"][0]["columns"][:3], ["排名", "原编号", "case_id"])
        self.assertIn("不代表已验证故障严重程度", RANKING_BASIS)
        rows = records(workbook, "整体故障排名")
        self.assertEqual([row["case_id"] for row in rows], ["C1", "C2"])
        self.assertEqual([row["排名"] for row in rows], [1, 2])
        self.assertEqual(rows[0]["原编号"], "WB-SYN-1")
        self.assertEqual(rows[0]["根因/进展原文"], "raw one")
        self.assertEqual(rows[0]["来源文件"], "A.xlsx")
        self.assertEqual((rows[0]["Sheet"], rows[0]["Excel行"]), ("Cases", 2))
        self.assertIn("问题描述=D2", rows[0]["单元格定位"])
        self.assertEqual(data, before)

    def test_explicit_original_priority_precedes_processing_group(self):
        data = self.sample()
        data["cases"][0]["raw"]["优先级"] = "P0"
        data["cases"][1]["raw"]["优先级"] = "P2"
        rows = records(build_ranked_workbook(data), "整体故障排名")
        self.assertEqual([row["case_id"] for row in rows], ["C2", "C1"])
        self.assertEqual(rows[0]["原优先级"], "P0")
        self.assertIn("原表优先级 P0", rows[0]["排序依据"])

    def test_source_priority_group_is_not_invented_as_severity(self):
        data = self.sample()
        data["cases"][0]["raw"]["优先级组"] = "有证据+未覆盖"
        rows = records(build_ranked_workbook(data), "整体故障排名")
        self.assertEqual(rows[0]["case_id"], "C1")
        self.assertTrue(all(row["原优先级"] == "" for row in rows))
        self.assertEqual(next(row["原优先级组"] for row in rows if row["case_id"] == "C2"), "有证据+未覆盖")

    def test_no_original_id_retains_internal_id_and_all_rows(self):
        data = self.sample()
        data["cases"][0]["external_id"] = ""
        data["cases"][0]["raw"]["统一ID"] = ""
        rows = records(build_ranked_workbook(data), "整体故障排名")
        self.assertEqual(len(rows), 2)
        self.assertEqual(next(row for row in rows if row["case_id"] == "C2")["原编号"], "")

    def test_multiple_judgments_do_not_duplicate_case_or_count_stale_as_current(self):
        data = self.sample()
        first = {"judgment_id": "J1", "case_id": "C1", "snapshot_id": "S1", "short_reason": "current one",
            "processing_status": "AUTO_PROCESSED", "review_required": False, "review_status": "NOT_REQUIRED", "support_level": "PARTIAL"}
        second = {**first, "judgment_id": "J2", "short_reason": "current two"}
        data["judgments"] = [first, copy.deepcopy(first), second,
            {**first, "judgment_id": "J-old", "is_stale": True, "support_level": "DIRECT", "short_reason": "stale claim"}]
        data["mappings"] = [{"task_id": "M-old", "case_id": "C1", "overall": "COVERED", "is_stale": True}]
        workbook = build_ranked_workbook(data, {"C1": {"status": "FOUND"}})
        rows = records(workbook, "整体故障排名")
        self.assertEqual(len(rows), 2)
        row = next(row for row in rows if row["case_id"] == "C1")
        self.assertNotIn("stale claim", row["当前证据判断"])
        self.assertEqual(row["模式库覆盖"], "待核验")
        stats = {row["指标"]: row["值"] for row in records(workbook, "运行统计")}
        self.assertEqual((stats["故障记录数量"], stats["当前判断数量"], stats["过期判断留档数量"]), (2, 2, 1))

    def test_normal_auto_processed_source_does_not_enter_human_review(self):
        data = self.sample()
        data["judgments"] = [{"judgment_id": "J1", "case_id": "C1", "snapshot_id": "S1", "short_reason": "normal",
            "processing_status": "AUTO_PROCESSED", "review_required": False, "review_status": "NOT_REQUIRED", "support_level": "PARTIAL"}]
        workbook = build_ranked_workbook(data, {"C1": {"status": "FOUND", "reason": "captured Wiki"}})
        rows = records(workbook, "异常与待处理")
        self.assertFalse(any(row["case_id"] == "C1" for row in rows))
        self.assertEqual(next(row for row in records(workbook, "整体故障排名") if row["case_id"] == "C1")["需人工裁决"], "否")

    def test_wiki_blocking_and_no_match_are_visible_without_human_accept(self):
        workbook = build_ranked_workbook(self.sample(), {
            "C1": {"status": "BLOCKED", "reason": "login required", "query": "synthetic fault", "scope": "synthetic wiki space"},
            "C2": {"status": "NO_MATCH", "reason": "no matching Wiki in checked scope"}})
        rows = records(workbook, "异常与待处理")
        self.assertTrue(any(row["Wiki检查"] == "BLOCKED" and "login required" in row["说明"] for row in rows))
        evidence = records(workbook, "来源与证据")[0]
        self.assertEqual((evidence["Wiki查询词"], evidence["Wiki查询范围"]), ("synthetic fault", "synthetic wiki space"))
        self.assertTrue(all(row["需人工裁决"] == "否" for row in rows))

    def test_original_and_discovered_reference_origins_remain_distinct(self):
        data = self.sample()
        data["references"].append({**data["references"][0], "ref_id": "R2", "origin": "SEARCH_DISCOVERED", "required": False})
        rows = records(build_ranked_workbook(data), "来源与证据")
        self.assertEqual({row["最初来源"] for row in rows}, {"ORIGINAL_WEEKLY", "SEARCH_DISCOVERED"})
        self.assertEqual({row["来源单元格"] for row in rows}, {"Cases!F2 (row 2)"})

    def test_new_pattern_suggestions_include_source_ids_and_unexecuted_labels(self):
        proposal = {"proposal_id": "P1", "action": "ADD", "case_ids": ["C1", "C2"],
            "implementation_owner": "synthetic custom operator", "evidence_scope": "INDEPENDENT_TECHNICAL_PATTERN",
            "row": {"pattern_name": "缓冲区生命周期错误", "root_cause": "synthetic premature reuse", "detection": "compare outputs"},
            "field_bases": {"detection": {"kind": "PROPOSED"}}, "unknowns": ["not reproduced"], "conflicts": []}
        workbook = build_ranked_workbook(self.sample(), proposals=[proposal, copy.deepcopy(proposal), {**proposal, "proposal_id": "P-old", "is_stale": True}])
        rows = records(workbook, "模式库建议")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["关联原编号"], "WB-SYN-1；WB-SYN-2")
        self.assertIn("未验证、未执行", rows[0]["检查机制"])
        self.assertIn("客户关联未确认", rows[0]["故障原因"])
        self.assertEqual(rows[0]["状态"], "草案，未正式入库")
        self.assertEqual({row["整理分组"] for row in records(workbook, "整体故障排名")}, {"未覆盖或新增候选"})

    def test_current_rejected_judgment_is_counted_but_not_support(self):
        data = self.sample()
        data["judgments"] = [{"judgment_id": "J-rejected", "case_id": "C1", "snapshot_id": "S1", "review_status": "REJECT",
            "short_reason": "wrong relation", "support_level": "DIRECT"}]
        workbook = build_ranked_workbook(data)
        stats = {row["指标"]: row["值"] for row in records(workbook, "运行统计")}
        self.assertEqual((stats["当前判断数量"], stats["可支持结论的判断数量"]), (1, 0))
        row = next(row for row in records(workbook, "整体故障排名") if row["case_id"] == "C1")
        self.assertIn("已拒绝", row["证据强度"])

    def test_empty_input_has_named_tables_and_zero_cases(self):
        workbook = build_ranked_workbook({})
        self.assertEqual(len(workbook["sheets"]), 5)
        self.assertEqual(records(workbook, "整体故障排名"), [])
        stats = {row["指标"]: row["值"] for row in records(workbook, "运行统计")}
        self.assertEqual(stats["故障记录数量"], 0)


if __name__ == "__main__":
    unittest.main()
