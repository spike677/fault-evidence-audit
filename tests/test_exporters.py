import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

from faultaudit.exporters import COMPAT_COLUMNS, EXTRA_COLUMNS, export_report


class ExportReportTests(unittest.TestCase):
    def sample(self):
        return {
            "run": {"run_id": "run-test", "model_mode": "mock", "status": "COMPLETE_WITH_PENDING"},
            "cases": [{"case_id": "case-1", "root_cause_origin": "LEGACY_DERIVED_UNKNOWN",
                       "root_cause": "模型改写不应覆盖", "raw": {"统一ID": "CASE-DELTA", "根因": "原始AllReduce",
                       "问题描述": "<script>alert(1)</script>", "wiki": "javascript:alert(1)", "来源": "=HYPERLINK(\"evil\")"}},
                      {"case_id": "case-2", "raw": {"统一ID": "CASE-ZETA", "根因": "", "问题描述": " \t@SUM(1)"}}],
            "references": [{"case_id": "case-1", "url": "https://example.com/wiki", "origin": "ORIGINAL_WEEKLY"},
                           {"case_id": "case-1", "url": "https://example.com/wiki", "origin": "SEARCH_DISCOVERED"}],
            "snapshots": [{"snapshot_id": "s-1", "retrieval_status": "PARTIAL", "text": "原文"}],
            "summaries": [{"snapshot_id": "s-1", "operator": ["dequant"], "root_cause": "量化对齐问题"}],
            "judgments": [{"case_id": "case-1", "snapshot_id": "s-1", "decision": "REJECTED",
                           "short_reason": "根因冲突，拒绝关联", "missing_information": ["版本"], "model_mode": "mock"}],
            "tasks": [{"task_id": "t-fail", "case_id": "case-1", "status": "AUTH_REQUIRED", "error": "登录失效"},
                      {"task_id": "t-ok", "case_id": "case-1", "status": "COMPLETE"}],
            "catalog": [], "mappings": [], "review_events": [],
            "validation": {"status": "COMPLETE_WITH_PENDING", "errors": ["缺正文"]},
        }

    def test_original_root_source_and_all_associations_survive(self):
        data = self.sample()
        original = copy.deepcopy(data)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            paths = export_report(data, Path(directory))
            report = json.loads(Path(paths["report_json"]).read_text(encoding="utf-8"))
            workbook = json.loads(Path(paths["workbook_data"]).read_text(encoding="utf-8"))
            summary = workbook["sheets"][0]
            self.assertEqual(summary["columns"], COMPAT_COLUMNS + EXTRA_COLUMNS)
            self.assertEqual(summary["rows"][0][7], "原始AllReduce")
            self.assertEqual(summary["rows"][1][7], "")
            self.assertEqual(summary["rows"][1][11], "待核验")
            self.assertEqual(summary["rows"][1][12], "待核验")
            self.assertEqual(report, original)
            by_name = {sheet["name"]: sheet for sheet in workbook["sheets"]}
            self.assertEqual(len(by_name["引用来历"]["rows"]), 2)
            self.assertEqual(len(by_name["关联判断"]["rows"]), 1)
            self.assertEqual(len(by_name["失败与待办"]["rows"]), 1)
            self.assertIn("根因冲突，拒绝关联", Path(paths["report_html"]).read_text(encoding="utf-8"))
            self.assertEqual(data, original)

    def test_html_escapes_text_and_only_links_http_urls(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            paths = export_report(self.sample(), Path(directory))
            report = Path(paths["report_html"]).read_text(encoding="utf-8")
            self.assertNotIn("<script>alert(1)</script>", report)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", report)
            self.assertNotIn('href="javascript:', report)
            self.assertIn('href="https://example.com/wiki"', report)
            self.assertIn("登录失效", report)
            self.assertIn("PARTIAL", report)

    def test_tsv_formula_injection_protection_and_raw_json(self):
        data = self.sample()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            paths = export_report(data, Path(directory))
            with Path(paths["summary_tsv"]).open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
            self.assertTrue(rows[0]["来源"].startswith("'="))
            self.assertTrue(rows[1]["问题描述"].startswith("'"))
            report = json.loads(Path(paths["report_json"]).read_text(encoding="utf-8"))
            self.assertEqual(report["cases"][0]["raw"]["来源"], '=HYPERLINK("evil")')

    def test_payload_records_missing_columns_and_empty_report(self):
        data = {"run": {"id": "r2"}, "cases": [{"payload": {"case_id": "c2", "description": "d", "root_cause_raw": "raw"}}]}
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            paths = export_report(data, Path(directory))
            workbook = json.loads(Path(paths["workbook_data"]).read_text(encoding="utf-8"))
            row = dict(zip(workbook["sheets"][0]["columns"], workbook["sheets"][0]["rows"][0]))
            self.assertEqual(row["根因"], "raw")
            self.assertEqual(row["case_id"], "c2")
            self.assertEqual(row["run_id"], "r2")
            self.assertEqual(row["模型模式"], "NOT_RUN")
            self.assertEqual(row["根因来源"], "LEGACY_DERIVED_UNKNOWN")
            self.assertTrue(all(Path(value).is_file() for value in paths.values()))
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            export_report({}, Path(directory))
            self.assertIn("无记录", (Path(directory) / "report.html").read_text(encoding="utf-8"))

    def test_stale_results_and_legacy_direct_are_never_current_results(self):
        data = self.sample()
        data["cases"][0]["raw"].update({"证据强度": "DIRECT", "库覆盖（98条）": "已覆盖"})
        data["judgments"][0].update({"is_stale": True, "support_level": "DIRECT"})
        data["mappings"] = [{"case_id": "case-1", "coverage": "COVERED", "is_stale": True}]
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            paths = export_report(data, Path(directory))
            workbook = json.loads(Path(paths["workbook_data"]).read_text(encoding="utf-8"))
            summary = workbook["sheets"][0]
            row = dict(zip(summary["columns"], summary["rows"][0]))
            self.assertEqual(row["证据强度"], "待核验")
            self.assertEqual(row["库覆盖（98条）"], "待核验")
            self.assertIn("过期", row["证据判断"])
            self.assertIn("过期", row["缺口"])
            self.assertEqual(len(next(s for s in workbook["sheets"] if s["name"] == "关联判断")["rows"]), 1)

    def test_model_positive_requires_accept_and_rejected_link_has_no_support(self):
        data = self.sample()
        data["judgments"][0].update({"support_level": "DIRECT", "case_attribution": "CONFIRMED", "review_status": "NEEDS_REVIEW"})
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            paths = export_report(data, Path(directory))
            workbook = json.loads(Path(paths["workbook_data"]).read_text(encoding="utf-8"))
            columns = workbook["sheets"][0]["columns"]
            row = dict(zip(columns, workbook["sheets"][0]["rows"][0]))
            self.assertEqual(row["证据强度"], "DIRECT（模型建议，待复核）")
            self.assertIn("模型建议，待复核", row["证据判断"])
            data["judgments"][0]["review_status"] = "ACCEPT"
            paths = export_report(data, Path(directory))
            workbook = json.loads(Path(paths["workbook_data"]).read_text(encoding="utf-8"))
            row = dict(zip(columns, workbook["sheets"][0]["rows"][0]))
            self.assertEqual(row["证据强度"], "DIRECT")
            data["judgments"][0]["review_status"] = "REJECT"
            paths = export_report(data, Path(directory))
            workbook = json.loads(Path(paths["workbook_data"]).read_text(encoding="utf-8"))
            row = dict(zip(columns, workbook["sheets"][0]["rows"][0]))
            self.assertNotIn("DIRECT", row["证据强度"])
            self.assertIn("已拒绝关联", row["证据判断"])
            self.assertIn("根因冲突", row["证据判断"])
            self.assertEqual(len(next(s for s in workbook["sheets"] if s["name"] == "关联判断")["rows"]), 1)

    def test_positive_coverage_is_a_proposal_until_accepted(self):
        data = self.sample()
        data["mappings"] = [{"case_id": "case-1", "overall": "COVERED", "review_status": "NEEDS_REVIEW"}]
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            paths = export_report(data, Path(directory))
            workbook = json.loads(Path(paths["workbook_data"]).read_text(encoding="utf-8"))
            columns = workbook["sheets"][0]["columns"]
            row = dict(zip(columns, workbook["sheets"][0]["rows"][0]))
            self.assertEqual(row["库覆盖（98条）"], "COVERED（模型建议，待复核）")
            data["mappings"][0]["review_status"] = "ACCEPT"
            paths = export_report(data, Path(directory))
            workbook = json.loads(Path(paths["workbook_data"]).read_text(encoding="utf-8"))
            row = dict(zip(columns, workbook["sheets"][0]["rows"][0]))
            self.assertEqual(row["库覆盖（98条）"], "COVERED")


if __name__ == "__main__":
    unittest.main()
