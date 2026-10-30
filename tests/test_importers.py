import csv
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from faultaudit.importers import extract_urls, import_cases, import_catalog


def write_minimal_xlsx(path):
    """Make a tiny OOXML fixture with stdlib; openpyxl is used only for reading."""
    content_types = '''<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'''
    root_rels = '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    workbook = '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="周报" sheetId="1" r:id="rId1"/></sheets></workbook>'''
    workbook_rels = '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'''
    sheet_rels = '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdLink" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.invalid/wiki/one" TargetMode="External"/></Relationships>'''
    def string_cell(coordinate, value):
        return f'<c r="{coordinate}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
    first = ''.join(string_cell(f'{chr(65+i)}1', value) for i, value in enumerate(["统一ID", "问题描述", "wiki", "PR", "根因"]))
    second = ''.join([string_cell("A2", "WB-1"), string_cell("B2", "输出乱码"), string_cell("C2", "Wiki展示文字"),
                      '<c r="D2"><f>HYPERLINK("https://example.invalid/pr/2","PR")</f></c>', string_cell("E2", "原文根因")])
    third = string_cell("A3", "WB-2") + string_cell("B3", "没有链接也必须导入")
    sheet = f'''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><dimension ref="A1:E3"/><sheetData><row r="1">{first}</row><row r="2" hidden="1">{second}</row><row r="3">{third}</row></sheetData><hyperlinks><hyperlink ref="C2" r:id="rIdLink"/></hyperlinks></worksheet>'''
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in {"[Content_Types].xml": content_types, "_rels/.rels": root_rels,
                           "xl/workbook.xml": workbook, "xl/_rels/workbook.xml.rels": workbook_rels,
                           "xl/worksheets/sheet1.xml": sheet, "xl/worksheets/_rels/sheet1.xml.rels": sheet_rels}.items():
            archive.writestr(name, data)


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.test_root = Path(__file__).resolve().parent
        self.temp = tempfile.TemporaryDirectory(dir=self.test_root)
        self.directory = Path(self.temp.name)

    def tearDown(self):
        self.assertTrue(self.directory.resolve().is_relative_to(self.test_root))
        self.temp.cleanup()

    def test_all_sixteen_columns_raw_and_linkless_case_retained(self):
        path = self.directory / "legacy.tsv"
        headers = ["序号", "优先级组", "统一ID", "来源", "客户/模型", "问题描述", "算子", "根因", "wiki", "DTS", "PR", "库覆盖（98条）", "证据强度", "训练/推理/无法确定", "证据来源", "证据判断"]
        rows = [["ROW-A", "有证据+未覆盖", "CASE-DELTA", "研发周报 batch-alpha", "Example Client/Model-X", "输出乱码", "all_reduce", "ExampleRuntime 1.2.3精度问题", "https://example.invalid/wiki/1", "", "", "未覆盖", "直接", "推理", "周报", "旧判断"],
                ["ROW-B", "无证据", "CASE-EPSILON", "研发周报 batch-beta", "Example Client/Model-X", "无链接问题", "", "未知", "", "", "", "待判断", "", "", "", ""]]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(headers)
            writer.writerows(rows)
        before = path.read_bytes()
        imported = import_cases(path)
        self.assertEqual(len(imported["cases"]), 2)
        case = imported["cases"][0]
        self.assertEqual(set(case["raw"]), set(headers))
        self.assertEqual(case["external_id"], "CASE-DELTA")
        self.assertEqual(case["root_cause_origin"], "LEGACY_DERIVED_UNKNOWN")
        self.assertEqual(case["root_cause_raw"], rows[0][7])
        self.assertEqual(case["source_sha256"], hashlib.sha256(before).hexdigest())
        self.assertEqual(imported["references"][0]["origin"], "LEGACY_TABLE")
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(import_cases(path)["cases"][0]["case_id"], case["case_id"])

    def test_malformed_markdown_preserves_raw_and_separates_each_cell(self):
        raw = r"[[https://example.invalid/pr/1034\](https://example.invalid/pr/1034)\](https://example.invalid/pr/1034)"
        path = self.directory / "references.json"
        path.write_text(json.dumps([{"统一ID": "WB-1", "问题描述": "x", "wiki": raw, "PR": raw},
                                    {"统一ID": "WB-2", "问题描述": "y", "wiki": raw}], ensure_ascii=False), encoding="utf-8")
        data = import_cases(path, "ORIGINAL_WEEKLY")
        self.assertEqual(len(data["references"]), 3)
        self.assertEqual(len({ref["ref_id"] for ref in data["references"]}), 3)
        self.assertTrue(all(ref["raw_text"] == raw for ref in data["references"]))
        self.assertTrue(all(ref["url"] == "https://example.invalid/pr/1034" for ref in data["references"]))
        self.assertEqual(data["cases"][0]["root_cause_origin"], "SOURCE_RAW")

    def test_unresolved_and_invalid_urls_not_silently_lost(self):
        path = self.directory / "bad.csv"
        path.write_text("问题描述,wiki,DTS,PR\nx,待提供正文,https://,无\n", encoding="utf-8")
        imported = import_cases(path)
        self.assertEqual(len(imported["references"]), 2)
        self.assertEqual({ref["status"] for ref in imported["references"]}, {"UNRESOLVED", "MALFORMED"})
        self.assertTrue(imported["warnings"])

    def test_xlsx_hyperlink_formula_hidden_row_and_no_source_write(self):
        path = self.directory / "weekly.xlsx"
        write_minimal_xlsx(path)
        original = path.read_bytes()
        imported = import_cases(path, "ORIGINAL_WEEKLY")
        self.assertEqual(len(imported["cases"]), 2)
        self.assertEqual({ref["url"] for ref in imported["references"]},
                         {"https://example.invalid/wiki/one", "https://example.invalid/pr/2"})
        self.assertTrue(any("C2" in ref["location"] for ref in imported["references"]))
        self.assertEqual(imported["cases"][0]["cell_locations"]["根因"], "E2")
        self.assertTrue(imported["cases"][0]["raw"]["PR"].startswith("=HYPERLINK("))
        self.assertTrue(any("hidden rows included" in warning for warning in imported["warnings"]))
        self.assertEqual(path.read_bytes(), original)

    def test_catalog_retains_duplicate_ids_for_review(self):
        path = self.directory / "catalog.json"
        path.write_text(json.dumps({"items": [
            {"item_id": "F-1", "description": "all reduce", "operator": "all_reduce", "mechanism": "precision", "trigger": "PCIe"},
            {"item_id": "F-1", "description": "duplicate"}]}), encoding="utf-8")
        data = import_catalog(path)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["items"][0]["mechanism"], "precision")
        self.assertTrue(any("duplicate catalog" in warning for warning in data["warnings"]))

    def test_url_extraction_does_not_rewrite_domains_or_query(self):
        text = "https://wiki.example.invalid/domains/52290/wiki/212178/WIKI1?x=2&amp;y=3"
        self.assertEqual(extract_urls(text), ["https://wiki.example.invalid/domains/52290/wiki/212178/WIKI1?x=2&y=3"])

    def test_duplicate_headers_and_empty_row_reported(self):
        path = self.directory / "duplicates.csv"
        path.write_text("问题描述,wiki,wiki\nx,https://example.invalid/a,https://example.invalid/b\n,,\n", encoding="utf-8")
        data = import_cases(path)
        self.assertEqual(len(data["cases"]), 1)
        self.assertEqual(len(data["references"]), 2)
        self.assertIn("wiki#2", data["cases"][0]["raw"])
        self.assertEqual(data["exclusions"][0]["reason"], "EMPTY_ROW")

    def test_priority_is_not_misidentified_as_pr(self):
        path = self.directory / "priority.json"
        path.write_text(json.dumps([{"description": "x", "priority": "high"}]), encoding="utf-8")
        self.assertEqual(import_cases(path)["references"], [])

    def test_site_root_cause_progress_header_preserves_origin_and_raw(self):
        for header in ("根因/进展", "根因／进展"):
            with self.subTest(header=header):
                path = self.directory / "site.csv"
                original = f"统一ID,问题描述,{header}\nWB-1,合成问题,仍在定位，待验证\n".encode("utf-8")
                path.write_bytes(original)
                imported = import_cases(path, "LEGACY_TABLE")
                case = imported["cases"][0]
                self.assertEqual(case["root_cause_raw"], "仍在定位，待验证")
                self.assertEqual(case["raw"][header], "仍在定位，待验证")
                self.assertEqual(case["root_cause_origin"], "LEGACY_DERIVED_UNKNOWN")
                self.assertEqual(path.read_bytes(), original)

    def catalog_workbook(self):
        from openpyxl import Workbook

        path = self.directory / "catalog.xlsx"
        workbook = Workbook()
        inference = workbook.active
        inference.title = "推理汇总"
        inference.append(["合成故障模式库，仅用于测试"])
        inference.append([])
        inference.append(["编号", "模式名称", "故障原因"])
        inference.append([])
        inference.append([1, "推理模式", "推理机理"])
        training = workbook.create_sheet("训练汇总")
        training.append(["编号", "模式名称", "故障原因"])
        training.append([1, "训练模式", "训练机理"])
        workbook.create_sheet("空表")
        workbook.save(path)
        workbook.close()
        return path

    def test_catalog_sheet_selection_keeps_scope_location_and_source(self):
        path = self.catalog_workbook()
        original = path.read_bytes()
        data = import_catalog(path, sheets=["推理汇总"], scope="INFERENCE", expected_count=1)
        self.assertEqual(len(data["items"]), 1)
        item = data["items"][0]
        self.assertEqual(item["item_id"], "1")
        self.assertEqual(item["description"], "推理模式")
        self.assertEqual(item["mechanism"], "推理机理")
        self.assertEqual(item["sheet"], "推理汇总")
        self.assertEqual(item["row"], 5)
        self.assertIn("A5,B5,C5", item["source_location"])
        self.assertEqual(item["catalog_scope"], "INFERENCE")
        sha256 = hashlib.sha256(original).hexdigest()
        self.assertEqual(item["catalog_version"], sha256)
        identity = {"source_sha256": sha256, "sheets": ["推理汇总"], "scope": "INFERENCE"}
        self.assertEqual(data["catalog_identity"], identity)
        self.assertEqual(data["documents"][0]["catalog_identity"], identity)
        self.assertFalse(any("duplicate catalog" in warning for warning in data["warnings"]))
        self.assertEqual(path.read_bytes(), original)

    def test_catalog_default_retains_all_sheets_and_duplicate_ids(self):
        path = self.catalog_workbook()
        data = import_catalog(path)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual({item["sheet"] for item in data["items"]}, {"推理汇总", "训练汇总"})
        self.assertEqual(data["catalog_identity"]["sheets"], sorted(["推理汇总", "训练汇总", "空表"]))
        self.assertEqual(data["catalog_identity"]["scope"], "UNSPECIFIED")
        self.assertTrue(any("duplicate catalog" in warning for warning in data["warnings"]))

    def test_catalog_invalid_or_empty_sheet_selection_is_explicit(self):
        path = self.catalog_workbook()
        original = path.read_bytes()
        for sheets, message in ((["不存在"], "Unknown sheet"), (["空表"], "contain no items"),
                                ([], "at least one"), (["推理汇总 "], "Unknown sheet")):
            with self.subTest(sheets=sheets):
                with self.assertRaisesRegex(ValueError, message):
                    import_catalog(path, sheets=sheets)
        self.assertEqual(path.read_bytes(), original)

    def test_catalog_expected_count_cannot_hide_a_scope_mismatch(self):
        path = self.catalog_workbook()
        with self.assertRaisesRegex(ValueError, "expected 1, got 2"):
            import_catalog(path, expected_count=1)
        with self.assertRaisesRegex(ValueError, "expected 2, got 1"):
            import_catalog(path, sheets=["推理汇总"], expected_count=2)

    def test_catalog_json_sheet_selection_and_canonical_identity(self):
        path = self.directory / "catalog.json"
        path.write_text(json.dumps({"sheets": {
            "training": [{"item_id": "1", "description": "training"}],
            "inference": [{"item_id": "1", "description": "inference"}],
            "empty": []}}, ensure_ascii=False), encoding="utf-8")
        data = import_catalog(path, sheets=["inference", "empty", "inference"], scope="INFERENCE", expected_count=1)
        self.assertEqual(data["items"][0]["description"], "inference")
        self.assertEqual(data["catalog_identity"]["sheets"], ["empty", "inference"])
        with self.assertRaisesRegex(ValueError, "Unknown sheet"):
            import_catalog(path, sheets=["Inference"])

    def test_catalog_csv_sheet_selection_uses_file_name(self):
        path = self.directory / "catalog.csv"
        path.write_text("编号,模式名称\n1,合成模式\n", encoding="utf-8")
        data = import_catalog(path, sheets=[path.name], expected_count=1)
        self.assertEqual(data["catalog_identity"]["sheets"], [path.name])
        with self.assertRaisesRegex(ValueError, "Unknown sheet"):
            import_catalog(path, sheets=["JSON"])


if __name__ == "__main__":
    unittest.main()
