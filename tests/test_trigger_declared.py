"""Declared Init and incremental suggestions use isolated synthetic inputs only."""
from __future__ import annotations

import copy
import json
import os
import unittest
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from faultaudit import pipeline, trigger_workflow as workflow, xlsx_workflow
from faultaudit.exporters import export_report
from faultaudit.input_budget import BUDGET_ENV, serialized_chars
from faultaudit.store import AuditError
from faultaudit.trigger_assessment import validate_assessment
from faultaudit.trigger_report import SOURCE_DEFINITION_SCOPE, build_workbook
from tests import test_trigger_workflow as fixtures
from tests.fact_fixtures import with_fact_audit
from tests.test_trigger_assessment import CELL, HASH, fixture
from tests.test_trigger_report import records


class DeclaredWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.source = fixtures.TriggerWorkflowTests(methodName="runTest")
        self.source.setUp()
        self.store = self.source.store

    def tearDown(self):
        self.source.tearDown()

    def start(self, count=1, source=None):
        if source is None:
            self.source.write_modes(count)
            source = self.source.modes
        with patch("faultaudit.trigger_workflow.load_taxonomy", return_value=fixtures.synthetic_taxonomy()):
            cfg = workflow.start_init(self.store, source, self.source.taxonomy, self.source.work,
                executor="codex", basis="SOURCE_DEFINITIONS", catalog_scope="SYNTHETIC_INFERENCE_SUBSET")
        self.source.run = cfg["run_id"]
        return cfg

    def complete(self):
        dispatch = xlsx_workflow.next_tasks(self.store, self.source.run)
        for task in dispatch["tasks"]:
            request = self.store.get(self.source.run, "workflow_requests", task["task_id"])
            response = self.source.response(request, definition_only=True)
            xlsx_workflow.submit(self.store, self.source.run, task["task_id"], response)
        return workflow.finalize(self.store, self.source.run)

    def test_source_init_dispatches_only_semantic_tasks_and_keeps_declared_details(self):
        self.start(2)
        with patch("faultaudit.xlsx_workflow.wiki_plan", side_effect=AssertionError("No Wiki requested")), \
             patch("faultaudit.xlsx_workflow.fetch_tasks", side_effect=AssertionError("No fetch requested")), \
             patch("faultaudit.xlsx_workflow.evidence_plan", side_effect=AssertionError("No evidence plan requested")):
            dispatch = xlsx_workflow.next_tasks(self.store, self.source.run)
        self.assertEqual([t["kind"] for t in dispatch["tasks"]], ["trigger_classify"] * 2)
        for task in dispatch["tasks"]:
            request = self.store.get(self.source.run, "workflow_requests", task["task_id"])
            self.assertIsNone(request["payload"]["source_issue"])
            self.assertEqual(request["payload"]["assessment_basis"], "SOURCE_DEFINITIONS")
            self.assertEqual(request["input_budget"]["chars"], serialized_chars(request))
            self.assertEqual(request["execution_context"]["history"], "THIS_TASK_ONLY")
        baseline = self.complete()
        self.assertEqual(baseline["status"], "READY")
        self.assertEqual(baseline["coverage_kind"], "SOURCE_DEFINITIONS")
        self.assertEqual(baseline["coverage_details"], [])
        self.assertEqual(len(baseline["declared_details"]), 2)
        self.assertTrue(all(d["source_cells"] and not d["execution_verified"] for d in baseline["declared_details"]))
        self.assertEqual(self.store.records(self.source.run, "judgments"), [])
        data = workflow._projection(self.store, self.source.run)
        self.assertEqual({g["kind"] for g in data["gaps"]}, {"TRIGGER_UNKNOWNS"})
        report = build_workbook(data)
        self.assertTrue(all(r["覆盖范围"] == SOURCE_DEFINITION_SCOPE for r in records(report, "42项条件分类")))
        self.assertFalse(any(r["类型"].startswith("WIKI_") for r in records(report, "证据与缺口")))

    def test_source_init_requires_concrete_detail_and_frozen_basis(self):
        self.start()
        payload = next(workflow.classification_payloads(self.store, self.source.run))
        request = self.source.request(payload)
        response = self.source.response(request)
        with self.assertRaisesRegex(AuditError, "at least one"):
            workflow.accept_assessment(self.store, self.source.run, request, response)
        response = self.source.response(request, definition_only=True)
        request["payload"]["assessment_basis"] = "HISTORICAL_EVIDENCE"
        with self.assertRaisesRegex(AuditError, "phase/basis"):
            workflow.accept_assessment(self.store, self.source.run, request, response)
        self.assertEqual(self.store.records(self.source.run, "trigger_assessments"), [])

    def test_json_chat_definition_keeps_exact_pointer_anchor(self):
        source = self.source.root / "synthetic_chat.json"
        source.write_text(json.dumps([{"故障模式编号": "CHAT-M1", "模式名称": "尾块寻址",
            "故障原因": "尾块地址步长错误", "聊天记录": "用户原话：65维时误用完整块步长。"}], ensure_ascii=False), encoding="utf-8")
        self.start(source=source)
        payload = next(workflow.classification_payloads(self.store, self.source.run))
        request = self.source.request(payload)
        response = self.source.response(request, definition_only=True)
        case = payload["subject"]["source_case"]
        chat = {"field": "聊天记录", "cell": case["cell_locations"]["聊天记录"], "quote": case["raw"]["聊天记录"]}
        response["details"][0]["source_cells"].append(chat)
        workflow.accept_assessment(self.store, self.source.run, request, response)
        baseline = workflow.finalize(self.store, self.source.run)
        self.assertIn(chat, baseline["declared_details"][0]["source_cells"])
        self.assertTrue(chat["cell"].endswith("/0/聊天记录"))

    def test_budget_refusal_never_drops_definition_or_emits_browser_work(self):
        self.start()
        with patch.dict(os.environ, {BUDGET_ENV: "1000"}):
            dispatch = xlsx_workflow.next_tasks(self.store, self.source.run)
            self.assertEqual(dispatch["tasks"], [])
            state = self.store.get(self.source.run, "workflow_state", "current")
            block = self.store.get(self.source.run, "workflow_blocks", state["block_ids"][0])
            self.assertEqual((block["kind"], block["reason"]), ("trigger_classify", "INPUT_TOO_LARGE"))
            self.assertGreater(block["input_budget"]["chars"], 1000)
        self.assertEqual(len(list(workflow.classification_payloads(self.store, self.source.run))), 1)

    def test_incremental_inherits_complete_definitions_without_claiming_evidence(self):
        self.start(2)
        baseline = self.complete()
        baseline_run = self.source.run
        source = self.source.root / "synthetic_new.xlsx"
        book = Workbook()
        book.active.append(["统一ID", "问题描述"])
        book.active.append(["NEW-1", "Synthetic tail addressing failure"])
        book.save(source)
        cfg = workflow.start_incremental(self.store, source, baseline_run, self.source.work, executor="codex")
        payload = next(workflow.classification_payloads(self.store, cfg["run_id"]))
        self.assertEqual(payload["assessment_basis"], "HISTORICAL_EVIDENCE")
        self.assertEqual(payload["baseline"]["coverage_kind"], "SOURCE_DEFINITIONS")
        self.assertEqual(payload["input_scope"]["catalog_mode_ids"], baseline["mode_ids"])
        self.assertEqual(len(payload["mechanism_catalog"]), 2)
        self.assertEqual(len(payload["baseline"]["declared_details"]), 2)
        self.assertTrue(all(item["description"] and item["mechanism"] for item in payload["mechanism_catalog"]))
        self.assertEqual(payload["input_scope"]["catalog_view"], "COMPLETE_DEFINITION_COMPARISON_PROJECTION")
        self.assertFalse(payload["input_scope"]["full_source_document_audit"])
        # Web facts arriving later do not turn the frozen declared Init into a
        # historical-evidence baseline or erase its source-defined details.
        self.source.summary(self.source.capture())
        self.assertEqual(workflow._baseline(self.store, baseline_run)["baseline_id"], baseline["baseline_id"])
        self.assertEqual(self.store.records(cfg["run_id"], "judgments"), [])

    def test_catalog_projection_retains_every_definition_and_boundary_without_duplicate_chapters(self):
        original = [{"item_id": f"MODE-{i}", "description": "完整描述", "operator": "SyntheticFoo",
            "mechanism": "完整机理", "trigger": "完整条件", "source_file": "synthetic.json",
            "source_sha256": "a" * 64, "source_location": f"JSON!row:{i + 1}", "sheet": "JSON", "row": i + 1,
            "raw": {"三级": "计算算子", "四级": "精度", "边界": "明确边界", "未知": "待核验字段",
                "代表子案例": "完整代表说明", "source_anchors": "重复原始章节" * 1000,
                "精确引文": "重复引文" * 1000}} for i in range(15)]
        before = copy.deepcopy(original)
        view = workflow._model_catalog(original)
        self.assertEqual(original, before)
        self.assertEqual([item["item_id"] for item in view], [item["item_id"] for item in original])
        for item in view:
            self.assertEqual(item["mechanism"], "完整机理")
            self.assertEqual(item["trigger"], "完整条件")
            self.assertEqual(set(item["raw"]), {"三级", "四级", "边界", "未知", "代表子案例"})
            self.assertEqual(item["raw"]["代表子案例"], "完整代表说明")
        self.assertLess(serialized_chars(view), serialized_chars(original) / 10)


def declared_fixture():
    payload, response = fixture("INCREMENTAL")
    payload["source_issue"] = None
    payload["baseline"] = {"baseline_id": "DECLARED-BASE", "mode_ids": ["M1", "M2"],
        "catalog_scope": {"scope": "SYNTHETIC_INFERENCE_SUBSET"}, "coverage_kind": "SOURCE_DEFINITIONS",
        "declared_details": [{"detail_id": "M1:D1", "mode_id": "M1", "mechanism": "尾块步长错误", "trigger_ids": []},
                             {"detail_id": "M2:D1", "mode_id": "M2", "mechanism": "布局读取错误", "trigger_ids": []}]}
    payload["mechanism_catalog"].append({"item_id": "M2", "mechanism": "layout read"})
    response["declared_comparison"] = {"basis": "SOURCE_DEFINITIONS", "scope_relation": "IN_SCOPE",
        "scope_reason": "Synthetic input explicitly describes an inference operator.", "rows": [
            {"mode_id": "M1", "result": "COVERED", "mechanism_relation": "SAME", "baseline_detail_ids": ["M1:D1"],
             "reason": "Synthetic explicit same mechanism", "source_cells": [CELL]},
            {"mode_id": "M2", "result": "NOT_COVERED", "mechanism_relation": "DIFFERENT", "baseline_detail_ids": ["M2:D1"],
             "reason": "Synthetic explicit mechanism difference", "source_cells": [CELL]}],
        "decision": {"action": "CLASSIFY_DECLARED", "target_mode_ids": ["M1"], "target_detail_ids": ["M1:D1"],
                     "reason": "Only a declared-definition suggestion."}}
    return payload, response


class DeclaredAssessmentTests(unittest.TestCase):
    def test_complete_semantic_comparison_is_separate_from_formal_decision(self):
        payload, response = declared_fixture()
        result = validate_assessment(payload, response, HASH)
        self.assertEqual(result["decision"]["action"], "UNDETERMINED")
        self.assertEqual(result["declared_processing_status"], "AUTO_PROCESSED")
        self.assertEqual(result["declared_comparison"]["adoption_status"], "SUGGESTION_ONLY")
        self.assertEqual(result["declared_comparison"]["case_confirmation"], "NOT_ESTABLISHED")
        self.assertEqual(result["source_relation"], "UNKNOWN")

    def test_every_original_mode_and_its_correct_detail_are_required(self):
        payload, response = declared_fixture()
        for mutate in (lambda r: r["declared_comparison"]["rows"].pop(),
                       lambda r: r["declared_comparison"]["rows"][0].update(baseline_detail_ids=["M2:D1"]),
                       lambda r: r.update(declared_comparison=None)):
            with self.subTest(mutate=mutate):
                bad = copy.deepcopy(response)
                mutate(bad)
                with self.assertRaises(AuditError):
                    validate_assessment(payload, bad, HASH)

    def test_negative_comparison_requires_positive_current_source_and_mechanism_difference(self):
        payload, response = declared_fixture()
        response["declared_comparison"]["rows"][1]["source_cells"] = []
        with self.assertRaisesRegex(AuditError, "requires positive"):
            validate_assessment(payload, response, HASH)
        response["declared_comparison"]["rows"][1].update(source_cells=[CELL], mechanism_relation="UNKNOWN")
        with self.assertRaisesRegex(AuditError, "mechanism relation"):
            validate_assessment(payload, response, HASH)

    def test_new_declared_mode_is_scope_limited_and_never_bypasses_web_add_gate(self):
        payload, response = declared_fixture()
        for row in response["declared_comparison"]["rows"]:
            row.update(result="NOT_COVERED", mechanism_relation="DIFFERENT")
        response["details"] = [{"detail_id": "NEW-DETAIL", "name": "Synthetic new mechanism", "mechanism": CELL["quote"],
            "evidence_basis": "SOURCE_DEFINITION", "source_cells": [CELL]}]
        response["declared_comparison"]["decision"].update(action="PROPOSE_DECLARED_MODE",
            target_mode_ids=[], target_detail_ids=["NEW-DETAIL"])
        result = validate_assessment(payload, response, HASH)
        self.assertEqual(result["decision"]["action"], "UNDETERMINED")
        response["declared_comparison"]["scope_relation"] = "OUT_OF_SCOPE"
        with self.assertRaisesRegex(AuditError, "in-scope"):
            validate_assessment(payload, response, HASH)
        response["declared_comparison"]["scope_relation"] = "IN_SCOPE"
        response["decision"].update(action="PROPOSE_NEW_MODE", target_detail_ids=["NEW-DETAIL"])
        with self.assertRaisesRegex(AuditError, "source MATCH"):
            validate_assessment(payload, response, HASH)

    def test_declared_report_preserves_every_mode_and_marks_suggestions(self):
        payload, response = declared_fixture()
        result = validate_assessment(payload, response, HASH)
        subject = payload["subject"]
        data = {"phase": "INCREMENTAL", "subjects": [subject], "baseline": payload["baseline"],
            "assessments": [{"assessment_id": "A", "subject_id": subject["subject_id"], "result": result}],
            "taxonomy": payload["taxonomy"], "wiki_checks": {"C1": {"status": "NO_MATCH"}}}
        rows = records(build_workbook(data), "声明定义对照")
        self.assertEqual({r["对照模式编号"] for r in rows}, {"M1", "M2"})
        self.assertTrue(all(r["采用状态"] == "SUGGESTION_ONLY" and r["事件确认"] == "NOT_ESTABLISHED" for r in rows))


class DeclaredDispatchScopeTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {BUDGET_ENV: "96000"})
        self.environment.start()
        self.source = fixtures.TriggerWorkflowTests(methodName="runTest")
        self.source.setUp()
        self.store = self.source.store

    def tearDown(self):
        self.source.tearDown()
        self.environment.stop()

    def declared_baseline(self):
        self.source.write_modes(15)
        book = load_workbook(self.source.modes)
        sheet = book.active
        sheet.cell(1, 6, "source_anchors")
        for row in range(2, 17):
            sheet.cell(row, 6, "SYNTHETIC ORIGINAL CHAPTER. " * 312)
        book.save(self.source.modes)
        with patch("faultaudit.trigger_workflow.load_taxonomy", return_value=fixtures.synthetic_taxonomy()):
            cfg = workflow.start_init(self.store, self.source.modes, self.source.taxonomy, self.source.work,
                executor="codex", basis="SOURCE_DEFINITIONS")
        self.source.run = cfg["run_id"]
        for task in xlsx_workflow.next_tasks(self.store, self.source.run)["tasks"]:
            request = self.store.get(self.source.run, "workflow_requests", task["task_id"])
            xlsx_workflow.submit(self.store, self.source.run, task["task_id"],
                self.source.response(request, definition_only=True))
        workflow.finalize(self.store, self.source.run)
        self.assertGreater(serialized_chars(self.store.records(self.source.run, "catalog")), 123000)
        return self.source.run

    def incremental(self, baseline_run=None, *, structured=False):
        source = self.source.root / "synthetic_incremental.xlsx"
        book = Workbook()
        book.active.append(["统一ID", "问题描述", "故障原因", "算子", "案例链接"])
        book.active.append(["NEW-1", "Synthetic tail addressing failure", "尾块地址步长在65维时错误",
                            "SyntheticFoo", "https://github.com/example/synthetic/issues/1"])
        book.save(source)
        if structured:
            cfg = xlsx_workflow.start(self.store, source, self.source.modes, self.source.work, executor="codex")
        else:
            cfg = workflow.start_incremental(self.store, source, baseline_run, self.source.work, executor="codex")
        self.source.run = cfg["run_id"]
        xlsx_workflow.configure_collection(self.store, self.source.run, ["GITHUB"], wiki_policy="NOT_SUPPORTED",
            reason="Synthetic source availability; no website accessed")
        self.source.capture()
        return cfg

    def inner_response(self, outer):
        inner = outer["payload"]["task"]
        snapshot = inner["payload"]["snapshot"]
        segment = snapshot["segments"][0]
        ref = {"segment_id": segment["segment_id"], "quote": segment["text"]}
        if inner["kind"] == "summarize":
            result = {"snapshot_id": snapshot["snapshot_id"], "issues": [{"label": "synthetic-tail", "facts": [
                {"field": "root_cause", "value": "Synthetic source statement only", "evidence": [ref]}]}],
                "unknown_fields": ["event identity"]}
        else:
            result = with_fact_audit({"case_id": inner["payload"]["case"]["case_id"],
                "snapshot_id": snapshot["snapshot_id"], "case_attribution": "UNKNOWN", "event_relation": "UNDETERMINED",
                "pattern_relation": "UNDETERMINED", "support_level": "PENDING",
                "claim_support": {key: "UNKNOWN" for key in ("symptom", "root_cause", "fix", "verification")},
                "matched_dimensions": [], "conflicting_dimensions": [], "unknown_dimensions": ["event"],
                "evidence": [], "short_reason": "Synthetic fixture leaves incident unconfirmed",
                "observation_scope": "FULL_DOCUMENT"}, inner)
        return {"schema_version": "1.0", "run_id": self.source.run, "task_id": inner["task_id"],
            "request_hash": inner["request_hash"], "result": result,
            "producer": {"executor": "codex", "codex_version": "synthetic", "provider": "synthetic",
                "model": "synthetic", "session_id": "isolated-declared-dispatch-test"}}

    def model_step(self, expected_kind):
        tasks = xlsx_workflow.next_tasks(self.store, self.source.run)["tasks"]
        self.assertEqual([task["kind"] for task in tasks], ["model"])
        outer = self.store.get(self.source.run, "workflow_requests", tasks[0]["task_id"])
        self.assertEqual(outer["payload"]["task"]["kind"], expected_kind)
        return tasks[0], outer

    def test_large_declared_catalog_keeps_fact_comparison_then_dispatches_complete_declared_task(self):
        baseline_run = self.declared_baseline()
        self.incremental(baseline_run)
        summary, outer = self.model_step("summarize")
        xlsx_workflow.submit(self.store, self.source.run, summary["task_id"], self.inner_response(outer))
        comparison, outer = self.model_step("compare")
        response = self.inner_response(outer)
        bad = copy.deepcopy(response)
        bad["result"]["fact_comparisons"] = []
        with self.assertRaises(AuditError):
            xlsx_workflow.submit(self.store, self.source.run, comparison["task_id"], bad)
        repeated, _ = self.model_step("compare")
        self.assertEqual(repeated["task_id"], comparison["task_id"])
        xlsx_workflow.submit(self.store, self.source.run, comparison["task_id"], response)
        tasks = xlsx_workflow.next_tasks(self.store, self.source.run)["tasks"]
        self.assertEqual([task["kind"] for task in tasks], ["trigger_classify"])
        request = self.store.get(self.source.run, "workflow_requests", tasks[0]["task_id"])
        self.assertEqual(len(request["payload"]["mechanism_catalog"]), 15)
        self.assertEqual(len(request["payload"]["baseline"]["declared_details"]), 15)
        self.assertEqual({t["kind"] for t in self.store.tasks(self.source.run)}, {"summarize", "compare"})
        self.assertEqual(self.store.records(self.source.run, "mappings"), [])
        self.assertEqual(self.store.events(self.source.run, "model_input_blocked"), [])
        event = self.store.events(self.source.run, "execution")[-1]
        self.assertFalse(event["catalog_mapping_required"])
        self.assertEqual(event["catalog_mapping_status"], "NOT_REQUIRED")
        response = self.source.response(request)
        response["decision"]["action"] = "UNDETERMINED"
        response["declared_comparison"] = {"scope_reason": "Synthetic scope is not established", "rows": [
            {"mode_id": item["item_id"], "result": "UNKNOWN", "mechanism_relation": "UNKNOWN",
                "reason": "Synthetic test exercises dispatch without inferring coverage"}
            for item in request["payload"]["mechanism_catalog"]], "decision": {
                "action": "UNDETERMINED", "reason": "Synthetic protocol fixture does not infer a semantic outcome"}}
        xlsx_workflow.submit(self.store, self.source.run, tasks[0]["task_id"], response)
        final = xlsx_workflow.next_tasks(self.store, self.source.run)
        self.assertEqual((final["status"], final["tasks"]), ("READY_TO_EXPORT", []))
        self.assertEqual(self.store.events(self.source.run, "model_input_blocked"), [])
        validation = pipeline.validate(self.store, self.source.run)
        self.assertFalse(validation["catalog_mapping_required"])
        self.assertFalse(any("catalog comparison missing" in value for value in validation["pending"]))
        self.assertTrue(all(value["case_attribution"] == "UNKNOWN" for value in pipeline.current_judgments(
            self.store, self.source.run)))

    def test_historical_baseline_and_structured_workflow_still_require_formal_catalog_tasks(self):
        self.source.start()
        self.source.complete_matched()
        workflow.finalize(self.store, self.source.run)
        historical_run = self.source.run
        self.incremental(historical_run)
        self.model_step("summarize")
        self.assertIn("catalog", {t["kind"] for t in self.store.tasks(self.source.run)})
        self.assertTrue(self.store.events(self.source.run, "execution")[-1]["catalog_mapping_required"])
        self.assertTrue(pipeline.require_catalog_mapping(self.store, self.source.run))
        self.assertTrue(any("catalog comparison missing" in value for value in pipeline.validate(
            self.store, self.source.run)["pending"]))
        self.assertTrue(all(task["required"] for task in pipeline.task_views(self.store, self.source.run)
                            if task["kind"] == "catalog"))
        self.incremental(structured=True)
        self.model_step("summarize")
        self.assertIn("catalog", {t["kind"] for t in self.store.tasks(self.source.run)})
        self.assertTrue(self.store.events(self.source.run, "execution")[-1]["catalog_mapping_required"])
        self.assertTrue(pipeline.require_catalog_mapping(self.store, self.source.run))
        self.assertTrue(any("catalog comparison missing" in value for value in pipeline.validate(
            self.store, self.source.run)["pending"]))
        self.assertTrue(all(task["required"] for task in pipeline.task_views(self.store, self.source.run)
                            if task["kind"] == "catalog"))

    def test_unused_formal_mapping_tasks_remain_history_without_false_validation_report_or_statistics_gaps(self):
        baseline_run = self.declared_baseline()
        self.incremental(baseline_run)
        case = self.source.cases()[0]
        legacy = self.store.task(self.source.run, "catalog", case["case_id"], {"synthetic_old_strategy": True})
        self.store.task_status(self.source.run, legacy["task_id"], "BLOCKED", "Synthetic retained oversized catalog task")
        with patch("faultaudit.pipeline.require_catalog_mapping", return_value=True):
            before = pipeline.validate(self.store, self.source.run)
        self.assertTrue(any("catalog comparison missing" in value for value in before["pending"]))
        after = pipeline.validate(self.store, self.source.run)
        self.assertFalse(after["catalog_mapping_required"])
        expected_remaining = [value for value in before["pending"] if "catalog comparison missing" not in value
                              and legacy["task_id"] not in value]
        self.assertEqual(after["pending"], expected_remaining)
        self.assertTrue(any("Unjudged work" in value for value in after["pending"]))
        self.assertEqual((before["counts"]["required_tasks"], after["counts"]["required_tasks"]), (1, 0))
        view = next(task for task in pipeline.task_views(self.store, self.source.run) if task["task_id"] == legacy["task_id"])
        self.assertEqual((view["status"], view["required"]), ("BLOCKED", False))
        report = pipeline.report_data(self.store, self.source.run)
        self.assertEqual(report["validation"]["pending"], after["pending"])
        self.assertEqual(report["statistics"]["current"]["mapping_count"], 0)
        self.assertFalse(next(task for task in report["tasks"] if task["task_id"] == legacy["task_id"])["required"])
        self.assertEqual(self.store.records(self.source.run, "mappings"), [])
        files = export_report(report, self.source.root / "synthetic_report")
        with open(files["workbook_data"], encoding="utf-8") as source:
            workbook = json.load(source)
        self.assertFalse(any(row.get("task_id") == legacy["task_id"] for row in records(workbook, "失败与待办")))
        history = next(row for row in records(workbook, "任务台账") if row.get("task_id") == legacy["task_id"])
        self.assertEqual((history["status"], history["required"]), ("BLOCKED", False))

    def test_policy_change_preserves_old_result_without_automatically_rebinding(self):
        self.source.write_modes()
        with patch("faultaudit.trigger_workflow.load_taxonomy", return_value=fixtures.synthetic_taxonomy()):
            cfg = workflow.start_init(self.store, self.source.modes, self.source.taxonomy, self.source.work,
                executor="codex", basis="SOURCE_DEFINITIONS")
        self.source.run = cfg["run_id"]
        with patch("faultaudit.xlsx_workflow._policy", return_value="0" * 64):
            task = xlsx_workflow.next_tasks(self.store, self.source.run)["tasks"][0]
            old_request = self.store.get(self.source.run, "workflow_requests", task["task_id"])
            old_response = self.source.response(old_request, definition_only=True)
            xlsx_workflow.submit(self.store, self.source.run, task["task_id"], old_response)
            self.assertEqual(len(workflow.current_assessments(self.store, self.source.run)), 1)
        self.assertEqual(workflow.current_assessments(self.store, self.source.run), [])
        with self.assertRaisesRegex(AuditError, "policy changed"):
            xlsx_workflow.submit(self.store, self.source.run, task["task_id"], old_response)
        fresh = xlsx_workflow.next_tasks(self.store, self.source.run)["tasks"][0]
        new_request = self.store.get(self.source.run, "workflow_requests", fresh["task_id"])
        self.assertEqual(old_request["payload"], new_request["payload"])
        self.assertNotEqual(old_request["request_hash"], new_request["request_hash"])
        self.assertIsNotNone(self.store.get(self.source.run, "workflow_results", task["task_id"]))
        self.assertEqual(len(self.store.records(self.source.run, "trigger_assessments")), 1)
        self.assertEqual(self.store.records(self.source.run, "reviews"), [])


if __name__ == "__main__":
    unittest.main()
