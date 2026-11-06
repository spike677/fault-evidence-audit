"""Synthetic acceptance cases for read-only pattern proposals and lossless export."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from faultaudit.catalog_drafts import COLUMNS, export_draft, prepare_draft, validate_draft
from faultaudit.evidence_plan import register_evidence_association
from faultaudit.importers import import_catalog
from faultaudit.pipeline import import_into
from faultaudit.store import AuditError, digest
from tests import test_investigation as investigation_tests


class CatalogDraftTests(unittest.TestCase):
    def setUp(self):
        self.fx = investigation_tests.InvestigationTests()
        self.fx.setUp()
        self.store, self.run, self.root = self.fx.store, self.fx.run, self.fx.directory
        self.cases = self.fx.source()
        self.catalog(2)
        self.snap = self.fx.snapshot()
        self.summary, self.judgment = self.fx.finish(self.cases[0], self.snap)

    def tearDown(self):
        self.fx.tearDown()

    def catalog(self, count):
        path = self.root / "catalog.json"
        path.write_text(json.dumps([{"item_id": f"BASE-{i:03d}", "模式名称": f"原始模式{i}",
            "故障原因": f"原始原因{i}", "故障影响": f"原始影响{i}", "案例链接": f"https://example.invalid/base/{i}"}
            for i in range(count)], ensure_ascii=False), encoding="utf-8")
        self.catalog_input = import_catalog(path, expected_count=count)
        import_into(self.store, self.run, self.catalog_input, catalog=True)

    def request(self, additions=1):
        prepared = prepare_draft(self.store, self.run, [case["case_id"] for case in self.cases], additions)
        self.assertEqual(prepared["status"], "READY_FOR_AGENT", prepared.get("input_budget"))
        return prepared["request"]

    def response(self, request, *, issue="Issue A", proposal_id="SYN-P1", case_index=0):
        context = request["payload"]
        fact = next(f for f in context["independent_technical_facts"] if f["issue_label"] == issue)
        case = self.cases[case_index]
        basis = lambda kind, **kwargs: {"kind": kind, "note": "Synthetic field basis; no semantic proof", **kwargs}
        cell = lambda field: {"case_id": case["case_id"], "field": field,
            "cell": case["cell_locations"][field], "quote": case["raw"][field]}
        row = {"level1": "芯片使能", "level2": "CANN", "level3": "计算算子", "level4": "数据切分",
            "pattern_name": "合成模式：缓冲区生命周期错误", "root_cause": str(fact["value"]),
            "effect": case["raw"]["问题描述"], "scenario": "未知（采集资料未说明）", "precision_type": "精度错误",
            "detection": "比较缓冲区复用前后的值", "mitigation": "验证完成后再复用缓冲区",
            "constructibility": "有条件，方案未验证", "injection_tool": "暂无", "injection_method": "修改缓冲区复用时机",
            "case_links": self.snap["url"]}
        bases = {key: basis("ABSTRACTION") for key in COLUMNS}
        bases.update(root_cause=basis("CITED_FACT", fact_ids=[fact["fact_id"]]),
            effect=basis("SOURCE_CELL", source_cells=[cell("问题描述")]), scenario=basis("UNKNOWN"),
            precision_type=basis("ABSTRACTION", fact_ids=[fact["fact_id"]]))
        for key in ("detection", "mitigation", "constructibility", "injection_method"):
            bases[key] = basis("PROPOSED")
        bases["injection_tool"] = basis("UNKNOWN")
        proposal = {"proposal_id": proposal_id, "revision": 1, "action": "ADD", "case_ids": [case["case_id"]],
            "work_ids": [next(work["work_id"] for work in context["work_items"] if case["case_id"] in work["case_ids"])],
            "evidence_scope": "INDEPENDENT_TECHNICAL_PATTERN",
            "implementation_owner": "合成生态自定义算子，非已确认CANN内置故障", "row": row, "field_bases": bases,
            "coverage_comparisons": [{"item_id": item["item_id"], "relation": "DIFFERENT",
                                      "reason": "Synthetic comparison: different mechanism"} for item in context["catalog"]],
            "unknowns": ["客户事件关联未确认", "未执行注入"], "conflicts": [],
            "self_check": {"attempt": 1, "numeric_meaning_checked": True, "citations_checked": True,
                "counterevidence_checked": True, "issue_scope_checked": True, "event_vs_technical_checked": True,
                "passed": True, "issues": []}}
        return {"schema_version": "1.0", "kind": "CATALOG_DRAFT", "request_hash": request["request_hash"],
                "executor": "codex", "created_by": "synthetic-agent", "producer": {
                    "executor_version": "synthetic", "provider": "synthetic-only", "model": "synthetic-fixture",
                    "session_id": "offline-not-real-execution"}, "proposals": [proposal]}

    def validate(self, request, response):
        return validate_draft(self.store, self.run, request, response)

    def blocked(self, mutate, expected):
        request = self.request()
        response = self.response(request)
        mutate(response["proposals"][0])
        result = self.validate(request, response)
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertTrue(any(expected in error for error in result["errors"]), result)
        output = self.root / "must-not-exist"
        exported = export_draft(self.store, self.run, request, response, output)
        self.assertFalse(exported["outputs"])
        self.assertFalse(output.exists())

    def test_prepare_is_deterministic_and_full_request_measured_without_state_changes(self):
        before = (self.store.root / "audit.sqlite3").read_bytes()
        request = self.request()
        self.assertEqual(request, self.request())
        self.assertEqual(request["input_budget"]["chars"], len(json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))))
        self.assertGreater(request["input_budget"]["chars"], len(json.dumps(request["payload"], ensure_ascii=False)))
        self.assertEqual((self.store.root / "audit.sqlite3").read_bytes(), before)
        self.assertEqual(len(request["payload"]["catalog"]), 2)
        self.assertFalse(request["payload"]["cases"][0]["search_control"]["search_allowed"])

    def test_valid_independent_pattern_exports_fifteen_columns_and_preserves_original(self):
        request = self.request()
        response = self.response(request)
        before = digest(self.store.records(self.run, "catalog"))
        result = export_draft(self.store, self.run, request, response, self.root / "output")
        validation = result["validation"]
        self.assertEqual(validation["status"], "VALID_DRAFT")
        self.assertEqual((validation["proposal_count"], validation["case_count"], validation["merged_preview_count"]), (1, 1, 3))
        self.assertFalse(validation["formal_catalog_updated"])
        self.assertFalse(validation["human_accept_created"])
        workbook = json.loads(Path(result["outputs"]["workbook_data"]).read_text(encoding="utf-8"))
        self.assertEqual(len(workbook["sheets"][0]["columns"]), 15)
        self.assertEqual(len(workbook["sheets"][0]["rows"]), 1)
        self.assertIn("客户关联未确认", workbook["sheets"][0]["rows"][0][5])
        self.assertIn("未执行", workbook["sheets"][0]["rows"][0][9])
        self.assertEqual(workbook["sheets"][1]["rows"][0][2:5], ["原始模式0", "原始原因0", "原始影响0"])
        evidence = next(table for table in workbook["sheets"] if table["name"] == "字段与来源依据")
        self.assertTrue(any(row[8] == self.snap["text"].split("\n")[0] for row in evidence["rows"]))
        self.assertTrue(any(row[8] == self.cases[0]["raw"]["问题描述"] for row in evidence["rows"]))
        raw = json.loads(Path(result["outputs"]["baseline"]).read_text(encoding="utf-8"))
        self.assertEqual(raw["items"], request["payload"]["catalog"])
        self.assertEqual(digest(self.store.records(self.run, "catalog")), before)
        self.assertEqual(self.store.events(self.run, "review"), [])
        repeated = export_draft(self.store, self.run, request, response, self.root / "second")
        self.assertEqual(Path(result["outputs"]["workbook_data"]).read_bytes(), Path(repeated["outputs"]["workbook_data"]).read_bytes())
        with self.assertRaises(FileExistsError):
            export_draft(self.store, self.run, request, response, self.root / "output")
        with self.assertRaisesRegex(AuditError, "outside the state"):
            export_draft(self.store, self.run, request, response, self.store.root / "forbidden")

    def test_missing_and_duplicate_library_comparisons_block(self):
        self.blocked(lambda p: p["coverage_comparisons"].pop(), "every frozen item")
        self.blocked(lambda p: p["coverage_comparisons"].append(copy.deepcopy(p["coverage_comparisons"][0])), "every frozen item")

    def test_existing_pattern_cannot_be_added_again(self):
        self.blocked(lambda p: p["coverage_comparisons"][0].update(relation="SAME_PATTERN"), "requires append")
        self.blocked(lambda p: p["row"].update(pattern_name="原始模式0"), "already exists")

    def test_append_case_requires_matching_pattern_and_never_updates_baseline(self):
        request = self.request(additions=0)
        response = self.response(request)
        proposal = response["proposals"][0]
        proposal.update(action="APPEND_CASE", target_item_id="BASE-000")
        self.assertEqual(self.validate(request, response)["status"], "BLOCKED")
        proposal["coverage_comparisons"][0]["relation"] = "SAME_PATTERN"
        result = self.validate(request, response)
        self.assertEqual(result["status"], "VALID_DRAFT")
        self.assertEqual(result["merged_preview_count"], 2)

    def test_wrong_source_cell_and_missing_fact_block(self):
        self.blocked(lambda p: p["field_bases"]["effect"]["source_cells"][0].update(quote="invented"), "quotation")
        self.blocked(lambda p: p["field_bases"]["root_cause"].update(fact_ids=["not-current"]), "out-of-scope")

    def test_foreign_issue_is_not_used_for_an_explicit_scope(self):
        register_evidence_association(self.store, self.run, case_id=self.cases[0]["case_id"],
            snapshot_id=self.snap["snapshot_id"], applicable_issue_ids=["Issue A"], user_confirmed=True,
            confirmed_by="synthetic-user", reason="Select only the first issue")
        request = self.request()
        result = self.validate(request, self.response(request, issue="Issue B"))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("out-of-scope" in error for error in result["errors"]))

    def test_two_issues_in_one_snapshot_are_separate_proposals_not_mixed(self):
        request = self.request(additions=2)
        response = self.response(request)
        second = self.response(request, issue="Issue B", proposal_id="SYN-P2")["proposals"][0]
        second["row"]["pattern_name"] = "合成模式：偏移计算错误"
        response["proposals"].append(second)
        valid = self.validate(request, response)
        self.assertEqual(valid["status"], "VALID_DRAFT")
        self.assertEqual((valid["proposal_count"], valid["case_count"]), (2, 1))
        response["proposals"][0]["field_bases"]["root_cause"]["fact_ids"].extend(second["field_bases"]["root_cause"]["fact_ids"])
        self.assertTrue(any("cannot mix" in error for error in self.validate(request, response)["errors"]))

    def test_case_root_cause_requires_resolved_work_not_another_event(self):
        request = self.request()
        response = self.response(request)
        response["proposals"][0]["evidence_scope"] = "CASE_ROOT_CAUSE"
        self.assertEqual(self.validate(request, response)["status"], "VALID_DRAFT")
        other = self.response(request, issue="Issue B")
        other["proposals"][0]["evidence_scope"] = "CASE_ROOT_CAUSE"
        self.assertEqual(self.validate(request, other)["status"], "BLOCKED")
        self.store.event(self.run, "review", {"judgment_id": self.judgment["judgment_id"], "verdict": "REJECT"})
        current = self.request()
        rejected = self.response(current)
        rejected["proposals"][0]["evidence_scope"] = "CASE_ROOT_CAUSE"
        self.assertEqual(self.validate(current, rejected)["status"], "BLOCKED")

    def test_source_attribution_remains_unverified_not_case_confirmation(self):
        request = self.request()
        response = self.response(request)
        p, case = response["proposals"][0], self.cases[0]
        p["row"]["root_cause"] = case["root_cause_raw"]
        p["field_bases"]["root_cause"] = {"kind": "SOURCE_CELL", "note": "Only an imported attribution",
            "source_cells": [{"case_id": case["case_id"], "field": "根因", "cell": case["cell_locations"]["根因"], "quote": case["root_cause_raw"]}]}
        result = export_draft(self.store, self.run, request, response, self.root / "attribution")
        self.assertEqual(result["validation"]["proposals"][0]["root_cause_status"], "IMPORTED_ATTRIBUTION_NOT_VERIFIED")
        workbook = json.loads(Path(result["outputs"]["workbook_data"]).read_text(encoding="utf-8"))
        self.assertIn("未核验", workbook["sheets"][0]["rows"][0][5])

    def test_unknown_information_is_explicit_not_fabricated(self):
        self.blocked(lambda p: p["row"].update(scenario="推理"), "explicit unknown")
        self.blocked(lambda p: p["field_bases"]["root_cause"].update(kind="ABSTRACTION"), "cannot be invented")
        request = self.request()
        response = self.response(request)
        response["proposals"][0]["row"]["scenario"] = "无法确定"
        self.assertEqual(self.validate(request, response)["status"], "VALID_DRAFT")

    def test_self_check_and_executed_injection_cannot_be_claimed(self):
        self.blocked(lambda p: p["self_check"].update(numeric_meaning_checked=False), "self-check")
        request = self.request()
        for key, value in (("injection_execution", "EXECUTED"), ("review_status", "ACCEPT")):
            response = self.response(request)
            response["proposals"][0][key] = value
            with self.assertRaises(ValueError):
                self.validate(request, response)
        self.blocked(lambda p: p["field_bases"]["injection_method"].update(kind="CITED_FACT"), "must remain a suggestion")

    def test_invalid_taxonomy_and_blank_cells_are_rejected(self):
        request = self.request()
        for key, value in (("level3", "自定义模块"), ("level4", "未知分类"), ("pattern_name", " ")):
            response = self.response(request)
            response["proposals"][0]["row"][key] = value
            with self.assertRaises(ValueError):
                self.validate(request, response)

    def test_refinement_is_a_separate_suggestion_and_does_not_overwrite_old_rows(self):
        request = self.request(additions=0)
        response = self.response(request)
        response["proposals"][0].update(action="REFINE", target_item_id="BASE-000")
        result = export_draft(self.store, self.run, request, response, self.root / "refine")
        workbook = json.loads(Path(result["outputs"]["workbook_data"]).read_text(encoding="utf-8"))
        self.assertEqual(workbook["sheets"][0]["rows"], [])
        self.assertEqual(len(workbook["sheets"][1]["rows"]), 2)
        self.assertEqual(workbook["sheets"][1]["rows"][0][2], "原始模式0")
        self.assertEqual(len(workbook["sheets"][3]["rows"]), 1)

    def test_exact_addition_count_no_silent_extra_or_duplicate_proposals(self):
        self.blocked(lambda p: p.update(action="NO_CHANGE"), "Expected 1 ADD")
        request = self.request()
        response = self.response(request)
        response["proposals"].append(copy.deepcopy(response["proposals"][0]))
        result = self.validate(request, response)
        self.assertTrue(any("duplicate proposal_id" in error for error in result["errors"]))
        self.assertEqual(result["proposal_count"], 1)

    def test_request_hash_policy_budget_and_snapshot_changes_invalidate_without_deleting_history(self):
        request = self.request()
        response = self.response(request)
        tampered = copy.deepcopy(request)
        tampered["payload"]["catalog"].pop()
        with self.assertRaisesRegex(AuditError, "integrity"):
            self.validate(tampered, response)
        with patch("faultaudit.catalog_drafts.draft_policy_fingerprint", return_value="changed"):
            with self.assertRaisesRegex(AuditError, "policy is stale"):
                self.validate(request, response)
        with patch.dict(os.environ, {"FAULTAUDIT_MAX_INPUT_CHARS": "47000"}):
            with self.assertRaises(ValueError):
                self.validate(request, response)
        self.fx.snapshot("New capture with a changed mechanism.")
        with self.assertRaisesRegex(AuditError, "inputs are stale"):
            self.validate(request, response)
        self.assertTrue(self.store.records(self.run, "summaries"))
        self.assertTrue(self.store.records(self.run, "judgments"))

    def test_full_serialized_input_over_budget_is_blocked_without_truncation(self):
        with patch.dict(os.environ, {"FAULTAUDIT_MAX_INPUT_CHARS": "100"}):
            result = prepare_draft(self.store, self.run, [self.cases[0]["case_id"]], 1)
        self.assertEqual((result["status"], result["reason"]), ("BLOCKED", "INPUT_TOO_LARGE"))
        self.assertIsNone(result["request"])
        self.assertEqual(result["context"]["catalog"], self.store.records(self.run, "catalog"))
        self.assertGreater(result["input_budget"]["chars"], result["input_budget"]["budget"])

    @patch.dict(os.environ, {"FAULTAUDIT_MAX_INPUT_CHARS": "60000"})
    def test_thirty_original_plus_three_selected_proposals_keep_old_values_and_all_sources(self):
        # Explicit test configuration for the complete 30-row request. The
        # production default stays 48000 and oversized requests remain blocked.
        # A new synthetic run, never replace a frozen catalog in place.
        self.run = self.fx.run = self.store.create_run({"is_synthetic": True})
        self.cases = self.fx.source([{"统一ID": f"SYN-{i}", "问题描述": f"Synthetic symptom {i}",
            "根因": f"Synthetic imported mechanism {i}", "wiki": "https://example.invalid/wiki/one"} for i in range(3)])
        self.catalog(30)
        self.snap = self.fx.snapshot()
        self.fx.save_card_summary(self.snap, [{"label": "Issue A", "facts": [{"field": "mechanism",
            "value": "buffer reused before completion", "evidence": [{"segment_id": self.snap["segments"][0]["segment_id"],
                "quote": "buffer reused before completion"}]}]}])
        request = self.request(additions=3)
        response = self.response(request)
        for i in range(1, 3):
            proposal = self.response(request, proposal_id=f"SYN-P{i+1}", case_index=i)["proposals"][0]
            proposal["row"]["pattern_name"] = f"合成模式{i}（仅测试数量和追溯）"
            response["proposals"].append(proposal)
        result = export_draft(self.store, self.run, request, response, self.root / "thirty-three")
        validation = result["validation"]
        self.assertEqual(validation["status"], "VALID_DRAFT", validation)
        self.assertEqual([validation[key] for key in ("baseline_count", "addition_count", "merged_preview_count", "case_count")], [30, 3, 33, 3])
        workbook = json.loads(Path(result["outputs"]["workbook_data"]).read_text(encoding="utf-8"))
        self.assertEqual(len(workbook["sheets"][0]["rows"]), 3)
        for i, row in enumerate(workbook["sheets"][1]["rows"][:30]):
            self.assertEqual(row[2:5], [f"原始模式{i}", f"原始原因{i}", f"原始影响{i}"])
        self.assertEqual(len(next(s for s in workbook["sheets"] if s["name"] == "字段与来源依据")["rows"]), 45)
        # Dropping a selected case does not turn a partial response into success.
        response["proposals"].pop()
        self.assertEqual(self.validate(request, response)["status"], "BLOCKED")

    def test_source_input_and_frozen_baseline_changes_invalidate_a_previous_request(self):
        request = self.request()
        response = self.response(request)
        case = copy.deepcopy(self.cases[0])
        case["description"] += " changed"
        self.store.put(self.run, "cases", case["case_id"], case, mutable=True)
        with self.assertRaisesRegex(AuditError, "inputs are stale"):
            self.validate(request, response)
        self.store.put(self.run, "cases", case["case_id"], self.cases[0], mutable=True)
        item = self.store.records(self.run, "catalog")[0]
        item["raw"]["故障原因"] = "changed baseline"
        self.store.put(self.run, "catalog", item["item_id"], item, mutable=True)
        with self.assertRaisesRegex(AuditError, "inputs are stale"):
            self.validate(request, response)

    def test_complete_ninety_eight_item_set_is_retained_when_budget_blocks(self):
        self.run = self.fx.run = self.store.create_run({"is_synthetic": True})
        self.cases = self.fx.source()
        self.catalog(98)
        with patch.dict(os.environ, {"FAULTAUDIT_MAX_INPUT_CHARS": "48000"}):
            result = prepare_draft(self.store, self.run, [self.cases[0]["case_id"]], 1)
        self.assertEqual((result["status"], result["reason"]), ("BLOCKED", "INPUT_TOO_LARGE"))
        self.assertEqual(len({item["item_id"] for item in result["context"]["catalog"]}), 98)
        self.assertEqual(result["context"]["catalog"], self.catalog_input["items"])

    def run_cli(self, *args, expected=0, environment=None):
        process = subprocess.run([sys.executable, str(Path(__file__).parents[1] / "run_faultaudit.py"),
            "--state", str(self.store.root), "catalog-draft", *map(str, args)], cwd=self.root,
            capture_output=True, text=True, encoding="utf-8", timeout=30, env=environment)
        self.assertEqual(process.returncode, expected, (process.stdout, process.stderr))
        return json.loads(process.stdout)

    def test_cli_prepare_validate_export_are_read_only_and_keep_revisions(self):
        database = self.store.root / "audit.sqlite3"
        before = hashlib.sha256(database.read_bytes()).hexdigest()
        folder = self.root / "prepared"
        self.run_cli("prepare", "--case-id", self.cases[0]["case_id"], "--expected-additions", 1, "--out", folder)
        request_file = folder / "request.json"
        request = json.loads(request_file.read_text(encoding="utf-8"))
        response_file = self.root / "response.json"
        response_file.write_text(json.dumps(self.response(request), ensure_ascii=False), encoding="utf-8")
        common = ["--request", request_file, "--draft", response_file]
        self.assertEqual(self.run_cli("validate", *common)["status"], "VALID_DRAFT")
        exported = self.run_cli("export", *common, "--out", self.root / "cli-export")
        self.assertEqual(exported["validation"]["merged_preview_count"], 3)
        self.run_cli("export", *common, "--out", self.root / "cli-export", expected=1)
        self.run_cli("export", *common, "--out", self.store.root / "forbidden", expected=1)
        self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), before)

    def test_cli_blocked_request_is_not_presented_as_executable(self):
        environment = dict(os.environ, FAULTAUDIT_MAX_INPUT_CHARS="100")
        folder = self.root / "blocked"
        result = self.run_cli("prepare", "--case-id", self.cases[0]["case_id"], "--expected-additions", 1,
                              "--out", folder, expected=2, environment=environment)
        self.assertEqual(result["reason"], "INPUT_TOO_LARGE")
        self.assertTrue((folder / "blocked.json").is_file())
        self.assertFalse((folder / "request.json").exists())


if __name__ == "__main__":
    unittest.main()
