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


if __name__ == "__main__":
    unittest.main()
