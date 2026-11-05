"""Synthetic work binding and independently recorded source-grade checks."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from faultaudit.bridge import _check_current, submit_model_results
from faultaudit.gates import processing_decision
from faultaudit.input_budget import finalize_model_task
from faultaudit.pipeline import gate_judgment, report_data
from faultaudit.store import AuditError
from tests.test_fact_comparison import fixture, validated


class SourceGradeProcessingTests(unittest.TestCase):
    def test_source_and_legacy_cell_links_finish_facts_without_promoting_root_origin(self):
        for grade in ("SOURCE_CELL_LINKED", "LEGACY_TABLE_LINKED"):
            with self.subTest(grade=grade):
                case, snap, value = fixture(status="PARTIAL")
                case["root_cause_origin"] = "LEGACY_DERIVED_UNKNOWN"
                case["source_kind"] = "LEGACY_TABLE"
                before = copy.deepcopy(case)
                result = gate_judgment(case, snap, validated(case, snap, value), context={"source_relation": grade})
                self.assertEqual(result["processing_status"], "AUTO_PROCESSED")
                self.assertFalse(result["review_required"])
                self.assertEqual(result["event_relation"], "UNDETERMINED")
                self.assertEqual(result["claim_support"]["root_cause"], "UNKNOWN")
                self.assertEqual(case, before)
                self.assertEqual(case["root_cause_origin"], "LEGACY_DERIVED_UNKNOWN")

    def test_current_cited_partial_root_support_does_not_require_same_event(self):
        case, snap, value = fixture(status="PARTIAL")
        case["root_cause_origin"] = "LEGACY_DERIVED_UNKNOWN"
        value["claim_support"]["root_cause"] = "PARTIAL"
        result = gate_judgment(case, snap, validated(case, snap, value), context={"source_relation": "LEGACY_TABLE_LINKED"})
        self.assertEqual(result["processing_status"], "AUTO_PROCESSED")
        self.assertEqual(result["claim_support"]["root_cause"], "PARTIAL")
        self.assertEqual(result["event_relation"], "UNDETERMINED")
        self.assertEqual(case["root_cause_origin"], "LEGACY_DERIVED_UNKNOWN")

    def test_user_confirmation_is_independent_and_does_not_supply_technical_claims(self):
        case, snap, value = fixture()
        for fact in value["fact_comparisons"][2:]:
            fact.update(relation="UNKNOWN", source_value="", evidence_value="", evidence_meaning="unreported",
                        reason="当前范围没有足够具体的关联事实")
        checked = validated(case, snap, value)
        context = {"source_relation": "SEARCH_DISCOVERED", "user_confirmed": False}
        self.assertEqual(processing_decision(case, snap, checked, context)["processing_status"], "PENDING")
        context["user_confirmed"] = True
        before = copy.deepcopy(context)
        result = gate_judgment(case, snap, checked, context=context)
        self.assertEqual(result["processing_status"], "AUTO_PROCESSED")
        self.assertEqual(context, before)
        self.assertEqual(context["source_relation"], "SEARCH_DISCOVERED")
        self.assertEqual(result["claim_support"]["root_cause"], "UNKNOWN")
        self.assertNotEqual(result["review_status"], "ACCEPT")

    def test_user_confirmed_relation_label_alone_cannot_replace_provenance(self):
        case, snap, value = fixture()
        result = processing_decision(case, snap, validated(case, snap, value), "USER_CONFIRMED")
        self.assertEqual(result["processing_status"], "PENDING")
        self.assertFalse(result["review_required"])

    def test_new_grades_preserve_missing_facts_and_known_conflict_queues(self):
        for grade in ("SOURCE_CELL_LINKED", "LEGACY_TABLE_LINKED", "SEARCH_DISCOVERED"):
            with self.subTest(grade=grade):
                case, snap, value = fixture()
                value["fact_comparisons"] = []
                context = {"source_relation": grade, "user_confirmed": True}
                self.assertEqual(processing_decision(case, snap, value, context)["processing_status"], "PENDING")
                value["claim_support"]["root_cause"] = "CONTRADICTED"
                result = processing_decision(case, snap, value, context)
                self.assertEqual(result["processing_status"], "EXCEPTION")
                self.assertTrue(result["review_required"])

    def test_confirmation_does_not_remove_negative_or_direct_gates(self):
        from tests.test_negative_gates import basis, judgment, snapshot, source_case

        case, snap = source_case(), snapshot()
        value = judgment(snap, event_relation="DIFFERENT_EVENT", negative_basis=basis(snap))
        for grade in ("SOURCE_CELL_LINKED", "LEGACY_TABLE_LINKED", "SEARCH_DISCOVERED"):
            context = {"source_relation": grade, "user_confirmed": True}
            decision = processing_decision(case, snap, value, context)
            self.assertEqual(decision["processing_status"], "EXCEPTION")
            self.assertTrue(decision["review_required"])
        # A known contradiction remains an exception independently of source.
        value["conflicting_dimensions"] = ["root_cause"]
        for grade in ("SOURCE_CELL_LINKED", "LEGACY_TABLE_LINKED", "SEARCH_DISCOVERED"):
            context = {"source_relation": grade, "user_confirmed": True}
            self.assertEqual(processing_decision(case, snap, value, context)["processing_status"], "EXCEPTION")
        case, snap, value = fixture(status="PARTIAL")
        value.update(case_attribution="CONFIRMED", event_relation="SAME_EVENT", support_level="DIRECT", event_anchor="EVT-A001")
        with self.assertRaises(AuditError):
            gate_judgment(case, snap, value, context={"source_relation": "LEGACY_TABLE_LINKED", "user_confirmed": True})


class WorkBridgeTests(unittest.TestCase):
    def ready(self):
        from tests.test_bridge import BridgeTests

        workflow = BridgeTests(methodName="runTest")
        workflow.setUp()
        self.addCleanup(workflow.tearDown)
        tasks = workflow.summary_done()
        self.assertEqual([task["kind"] for task in tasks], ["compare"])
        return workflow, tasks[0]

    def test_core_binds_work_to_task_result_and_judgment_without_model_field(self):
        workflow, task = self.ready()
        context = task["payload"]["processing_context"]
        self.assertEqual(task["work_id"], context["work_id"])
        self.assertEqual(context["processing_version"], "evidence-first-0.1.8")
        parent = next(item for item in workflow.store.tasks(workflow.run_id) if item["task_id"] == task["pipeline_task_id"])
        self.assertEqual(parent["target_id"], task["work_id"])
        returned = workflow.envelope(task)
        self.assertNotIn("work_id", returned["result"])
        submit_model_results(workflow.store, workflow.run_id, [returned])
        saved = workflow.store.get(workflow.run_id, "model_results", task["task_id"])
        self.assertEqual(saved["work_id"], task["work_id"])
        workflow.drive()
        judgment = report_data(workflow.store, workflow.run_id)["judgments"][0]
        self.assertEqual(judgment["work_id"], task["work_id"])
        self.assertEqual(judgment["processing_context"]["work_id"], task["work_id"])

    def test_wrong_envelope_work_is_rejected_without_saving_then_correctable(self):
        workflow, task = self.ready()
        returned = workflow.envelope(task)
        returned["work_id"] = "work-" + "0" * 24
        before = workflow.store.records(workflow.run_id, "model_results")
        with self.assertRaisesRegex(AuditError, "work_id"):
            submit_model_results(workflow.store, workflow.run_id, [returned])
        self.assertEqual(workflow.store.records(workflow.run_id, "model_results"), before)
        returned["work_id"] = task["work_id"]
        self.assertEqual(submit_model_results(workflow.store, workflow.run_id, [returned])["accepted"], 1)

    def test_signed_wrong_task_or_parent_work_cannot_reuse_same_case_snapshot(self):
        workflow, task = self.ready()
        unsigned = {key: value for key, value in task.items() if key not in {"task_id", "request_hash", "input_budget"}}
        unsigned["work_id"] = "work-" + "0" * 24
        forged = finalize_model_task(unsigned)
        with self.assertRaisesRegex(AuditError, "work_id"):
            _check_current(workflow.store, workflow.run_id, forged)
        parents = [{**item, "target_id": "work-" + "1" * 24} if item["task_id"] == task["pipeline_task_id"] else item
                   for item in workflow.store.tasks(workflow.run_id)]
        with patch.object(workflow.store, "tasks", return_value=parents):
            with self.assertRaisesRegex(AuditError, "work_id|no longer selected"):
                _check_current(workflow.store, workflow.run_id, task)

    def test_work_context_is_revalidated_by_id_and_scope_changes_stale_task(self):
        workflow, task = self.ready()
        from faultaudit.pipeline import work_context

        with patch("faultaudit.pipeline.work_context", wraps=work_context) as resolver:
            _check_current(workflow.store, workflow.run_id, task)
        self.assertEqual(resolver.call_args.args[2], task["work_id"])
        current = copy.deepcopy(task["payload"]["processing_context"])
        current["applicable_issue"] = {"applicable_issue_ids": ["another-issue"]}
        with patch("faultaudit.pipeline.work_context", return_value=current):
            with self.assertRaisesRegex(AuditError, "scope changed|no longer selected"):
                _check_current(workflow.store, workflow.run_id, task)

    def test_work_cannot_bind_another_payload_case_or_snapshot(self):
        workflow, task = self.ready()
        for key, field in (("case", "case_id"), ("snapshot", "snapshot_id")):
            with self.subTest(key=key):
                unsigned = copy.deepcopy({key: value for key, value in task.items()
                                          if key not in {"task_id", "request_hash", "input_budget"}})
                unsigned["payload"][key][field] = "another-" + key
                from faultaudit.store import digest
                unsigned["input_hash"] = digest(unsigned["payload"])
                forged = finalize_model_task(unsigned)
                with self.assertRaisesRegex(AuditError, "case and snapshot.*work_id"):
                    _check_current(workflow.store, workflow.run_id, forged)

    def test_old_issue_scope_conflict_is_history_and_cannot_block_new_scope(self):
        from faultaudit.evidence_plan import register_evidence_association
        from faultaudit.pipeline import evidence_plan, necessary_judgments
        from tests.test_evidence_workflow import EvidenceWorkflowTests, TEXT

        workflow = EvidenceWorkflowTests(methodName="runTest")
        workflow.setUp()
        self.addCleanup(workflow.doCleanups)
        case = workflow.load()[0]
        passages = {"good": "good: " + TEXT, "bad": "bad: " + TEXT.replace("舍入误差", "量化错配")}
        snapshot = workflow.store.ingest_evidence(workflow.run_id, {"url": "https://example.invalid/main",
            "text": "\n\n".join(passages.values()), "status": "PARTIAL", "is_synthetic": True})

        def refs(label):
            return [{"segment_id": segment["segment_id"], "quote": passages[label]}
                    for segment in snapshot["segments"] if passages[label] in segment["text"]]

        def scoped_response(task, label):
            response = workflow.envelope(task)
            result = response["result"]
            result["evidence"] = refs(label)
            result["applicable_issue"].update(label=label, evidence=refs(label))
            for fact in result["fact_comparisons"]:
                fact["evidence"] = refs(label)
            if label == "bad":
                result["claim_support"]["root_cause"] = "CONTRADICTED"
                result["conflicting_dimensions"] = ["root_cause"]
                result["fact_comparisons"][-1].update(evidence_value="量化错配", relation="CONFLICT")
            return response

        _, tasks = workflow.drive()
        summary = workflow.envelope(tasks[0])
        summary["result"]["issues"] = [{"label": label, "facts": [{"field": "observation", "value": text,
            "evidence": refs(label)}]} for label, text in passages.items()]
        submit_model_results(workflow.store, workflow.run_id, [summary])
        _, tasks = workflow.drive()
        original = next(task for task in tasks if task["kind"] == "compare")
        submit_model_results(workflow.store, workflow.run_id, [scoped_response(original, "bad")])
        workflow.drive()
        self.assertEqual(evidence_plan(workflow.store, workflow.run_id)["cases"][0]["path"], "EXCEPTION")
        old_judgment = necessary_judgments(workflow.store, workflow.run_id)[0]["judgment_id"]
        register_evidence_association(workflow.store, workflow.run_id, case_id=case["case_id"],
            snapshot_id=snapshot["snapshot_id"], scope="ISSUES", applicable_issue_ids=["good"],
            user_confirmed=True, confirmed_by="synthetic-user", reason="Select the separately documented matching issue")
        plan = evidence_plan(workflow.store, workflow.run_id)
        self.assertNotEqual(plan["cases"][0]["path"], "EXCEPTION")
        self.assertFalse(any(action["action"] == "RECONCILE_CONFLICT" for action in plan["cases"][0]["required_actions"]))
        self.assertEqual(necessary_judgments(workflow.store, workflow.run_id, plan), [])
        scoped_report = report_data(workflow.store, workflow.run_id)
        history = next(value for value in scoped_report["judgments"]
                       if value["judgment_id"] == old_judgment)
        self.assertTrue(history["is_stale"])
        self.assertFalse(history["required"])
        self.assertEqual(history["claim_support"]["root_cause"], "CONTRADICTED")
        indexed_judgments = [value for entry in scoped_report["evidence_index"] for association in entry["associations"]
                             for value in association["judgments"]]
        self.assertFalse(any(value["judgment_id"] == old_judgment for value in indexed_judgments))
        _, tasks = workflow.drive()
        current = next(task for task in tasks if task["kind"] == "compare")
        self.assertNotEqual(current["work_id"], original["work_id"])
        self.assertEqual(current["payload"]["processing_context"]["applicable_issue"]["applicable_issue_ids"], ["good"])
        submit_model_results(workflow.store, workflow.run_id, [scoped_response(current, "good")])
        workflow.drive()
        current_judgments = necessary_judgments(workflow.store, workflow.run_id)
        self.assertEqual(len(current_judgments), 1)
        self.assertEqual(current_judgments[0]["processing_status"], "AUTO_PROCESSED")
        self.assertFalse(current_judgments[0]["review_required"])
        self.assertNotEqual(current_judgments[0]["review_status"], "ACCEPT")
        self.assertNotEqual(evidence_plan(workflow.store, workflow.run_id)["cases"][0]["path"], "EXCEPTION")

    def test_completed_negative_search_candidate_is_not_rechecked_when_next_is_usable(self):
        import json
        from faultaudit.importers import import_cases
        from faultaudit.pipeline import evidence_plan, import_into, necessary_judgments
        from tests.test_evidence_workflow import EvidenceWorkflowTests, TEXT

        workflow = EvidenceWorkflowTests(methodName="runTest")
        workflow.setUp()
        self.addCleanup(workflow.doCleanups)
        source = workflow.directory / "independent-events.json"
        source.write_text(json.dumps([{"事件编号": "EVT-A001", "客户/模型": "甲客户/Model-X",
            "问题描述": "首次输出异常", "触发条件": "推理阶段TP8", "算子": "sample_op",
            "根因": "舍入误差", "关键数值": "logprob=0.404"}], ensure_ascii=False), encoding="utf-8")
        imported = import_cases(source, "ORIGINAL_WEEKLY")
        import_into(workflow.store, workflow.run_id, imported)
        case = imported["cases"][0]
        other_context = "main：另一事件EVT-B002为乙客户周二在推理阶段TP8首次输出异常，已明确是独立复现；sample_op定位为舍入误差；logprob=0.404。"
        workflow.store.ingest_evidence(workflow.run_id, {"url": "https://example.invalid/negative-candidate",
            "text": other_context, "status": "PARTIAL", "is_synthetic": True,
            "origin": "SEARCH_DISCOVERED", "case_ids": [case["case_id"]]})
        _, tasks = workflow.drive()
        submit_model_results(workflow.store, workflow.run_id, [workflow.envelope(tasks[0])])
        _, tasks = workflow.drive()
        negative_task = next(task for task in tasks if task["kind"] == "compare")
        negative = workflow.envelope(negative_task)
        result = negative["result"]
        result.update(case_attribution="UNKNOWN", event_relation="DIFFERENT_EVENT", support_level="NONE",
                      claim_support={key: "UNKNOWN" for key in ("symptom", "root_cause", "fix", "verification")},
                      negative_basis={"other_event": {"positive_identity": "EVT-B002", "context": other_context,
                          "dimensions": ["event_identity", "symptom", "occurrence_context"], "evidence": result["evidence"]}})
        submit_model_results(workflow.store, workflow.run_id, [negative])
        workflow.drive()
        self.assertEqual(evidence_plan(workflow.store, workflow.run_id)["cases"][0]["path"], "SEARCH_REQUIRED")
        rejected_work = negative_task["work_id"]
        self.assertEqual(necessary_judgments(workflow.store, workflow.run_id), [])
        # A later discovery is assessed; the completed exclusion remains usable routing history.
        workflow.store.ingest_evidence(workflow.run_id, {"url": "https://example.invalid/usable-candidate",
            "text": TEXT + " 原事件EVT-A001为甲客户。", "status": "PARTIAL", "is_synthetic": True,
            "origin": "SEARCH_DISCOVERED", "case_ids": [case["case_id"]]})
        _, tasks = workflow.drive()
        self.assertEqual([task["kind"] for task in tasks], ["summarize"])
        submit_model_results(workflow.store, workflow.run_id, [workflow.envelope(tasks[0])])
        _, tasks = workflow.drive()
        self.assertEqual([task["kind"] for task in tasks], ["compare"])
        self.assertNotEqual(tasks[0]["work_id"], rejected_work)
        submit_model_results(workflow.store, workflow.run_id, [workflow.envelope(tasks[0])])
        workflow.drive()
        data = report_data(workflow.store, workflow.run_id)
        self.assertEqual(data["evidence_plans"]["cases"][0]["path"], "VERIFIED_SEARCH")
        self.assertTrue(all(value["work_id"] != rejected_work for value in necessary_judgments(workflow.store, workflow.run_id)))
        before = workflow.store.records(workflow.run_id, "model_tasks")
        for _ in range(2):
            self.assertEqual(workflow.drive()[1], [])
        self.assertEqual(workflow.store.records(workflow.run_id, "model_tasks"), before)
        self.assertEqual(len([task for task in before if task["kind"] == "compare"]), 2)
        historical_negative = next(value for value in data["judgments"] if value["work_id"] == rejected_work)
        self.assertEqual(historical_negative["event_relation"], "DIFFERENT_EVENT")
        self.assertFalse(historical_negative["required"])
        self.assertNotEqual(historical_negative["review_status"], "ACCEPT")


if __name__ == "__main__":
    unittest.main()
