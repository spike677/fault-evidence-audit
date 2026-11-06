"""Synthetic initialization, evidence scopes and preserved baseline history."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook

from faultaudit import trigger_workflow as workflow
from faultaudit.bridge import policy_fingerprint
from faultaudit.store import AuditError, Store, digest
from faultaudit.trigger_taxonomy import EXPECTED_IDS, builtin_user_branches
from tests.test_trigger_assessment import fixture


def synthetic_taxonomy():
    branches = builtin_user_branches()["branches"]
    return {"taxonomy_id": "synthetic-trigger-taxonomy", "taxonomy_hash": "a" * 64,
        "source_file": "synthetic-taxonomy-only", "source_sha256": "a" * 64,
        "item_count": 42, "families": [], "context": {},
        "items": [{"id": item_id, "family_id": item_id.rsplit(".", 1)[0], "name": "Synthetic trigger",
                   "definition": "维长65", "requires": [], "skip_if": []} for item_id in EXPECTED_IDS],
        "branches": [{**branch, "status": "DEFINED", "included_in_42": False} for branch in branches]}


class TriggerWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="trigger-workflow-", dir=Path(__file__).parent)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "state")
        self.work = self.root / "work"
        self.work.mkdir()
        self.modes = self.root / "synthetic_original_modes.xlsx"
        self.taxonomy = self.root / "synthetic_taxonomy.md"
        self.taxonomy.write_text("Synthetic loader is patched; the real loader has dedicated tests.", encoding="utf-8")
        self.run = None

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def write_modes(self, count=1):
        book = Workbook()
        sheet = book.active
        sheet.title = "合成原始模式库"
        sheet.append(["故障模式编号", "模式名称", "故障原因", "算子", "案例链接"])
        for index in range(count):
            sheet.append([f"SYN-ORIGINAL-{7 + index * 5}", "尾块寻址异常",
                "尾块地址步长在65维时错误", "SyntheticFoo", f"https://example.invalid/wiki/mode-{index}"])
        book.save(self.modes)

    def start(self, count=1):
        self.write_modes(count)
        with patch("faultaudit.trigger_workflow.load_taxonomy", return_value=synthetic_taxonomy()):
            cfg = workflow.start_init(self.store, self.modes, self.taxonomy, self.work, executor="codex")
        self.run = cfg["run_id"]
        return cfg

    def cases(self):
        return sorted(self.store.records(self.run, "cases"), key=lambda c: c["row"])

    def capture(self, case=None, *, url=None, text=None):
        case = case or self.cases()[0]
        url = url or case["raw"]["案例链接"]
        text = text or "SyntheticFoo在维长65时尾块地址步长错误。\n另一个独立子问题：布局读取错误。"
        return self.store.ingest_evidence(self.run, {"url": url, "title": "Synthetic mode evidence", "text": text,
            "status": "COMPLETE", "components": {"body": "COMPLETE"}, "is_synthetic": True,
            "case_ids": [case["case_id"]], "record_discovery": url != case["raw"]["案例链接"],
            "origin": "SEARCH_DISCOVERED", "capture_observation": {
                "page_kind": "BODY", "requested_url": url, "final_url": url,
                "title": "Synthetic mode evidence", "body_locator": "synthetic article body",
                "body_quotes": [text], "observed_by": "synthetic-agent", "observed_at": "2026-11-06T10:00:00+08:00",
                "tool_observation": "Synthetic test, no website visited"}})

    def summary(self, snapshot, count=1, revision=1, *, processed=None, mode="codex"):
        segment = snapshot["segments"][0]
        ref = {"segment_id": segment["segment_id"], "quote": segment["text"]}
        task = self.store.task(self.run, "summarize", snapshot["snapshot_id"], {"revision": revision})
        value = {"task_id": task["task_id"], "snapshot_id": snapshot["snapshot_id"],
            "issues": [{"label": f"synthetic-issue-{index}", "facts": [
                {"field": "root_cause", "value": f"Synthetic observed mechanism {index}", "evidence": [ref]}]}
                for index in range(count)], "unknown_fields": [], "model_mode": mode, "model_id": "synthetic-only",
            "segments_processed": len(snapshot["segments"]) if processed is None else processed,
            "policy_hash": policy_fingerprint()}
        self.store.put(self.run, "summaries", task["task_id"], value)
        self.store.task_status(self.run, task["task_id"], "SUCCEEDED")
        return value

    def request(self, payload):
        identity = {"subject_id": payload["subject"]["subject_id"], "basis": payload["basis_hash"],
                    "snapshot_id": (payload.get("source_issue") or {}).get("snapshot_id"),
                    "issue_index": (payload.get("source_issue") or {}).get("issue_index")}
        return {"task_id": "synthetic-classification-" + digest(identity)[:24],
                "request_hash": digest(payload), "payload": payload}

    def response(self, request, *, relation="UNKNOWN", definition_only=False):
        payload = request["payload"]
        _, response = fixture()
        response["request_hash"] = request["request_hash"]
        response["case_id"] = payload["subject"]["case_id"]
        response["rows"] = [{**copy.deepcopy(response["rows"][0]), "trigger_id": item["id"]}
                            for item in payload["taxonomy"]["items"]]
        source = payload["subject"]["source_case"]
        cell = {"field": "故障原因", "cell": source["cell_locations"]["故障原因"], "quote": source["raw"]["故障原因"]}
        if relation != "UNKNOWN":
            issue = payload["source_issue"]
            ref = issue["facts"][0]["evidence"][0]
            response.update(source_relation=relation, source_alignment=[{
                "dimension": "mechanism", "relation": "DIFFERENT" if relation == "NOT_RELATED" else "MATCH",
                "reason": "Synthetic comparison of this mode cell and this issue only.",
                "evidence": [ref], "source_cells": [cell]}])
            if relation == "MATCH":
                response["rows"][0].update(applicability="APPLICABLE", relation="MATCH",
                    evidence_basis="SOURCE_REPORTED", evidence=[ref], predicate_checks=[
                        {"clause": "维长65", "result": "MET", "evidence": [ref]}], detail_ids=["SYN-DETAIL"])
                response["details"] = [{"detail_id": "SYN-DETAIL", "mode_id": payload["subject"]["mode_id"],
                    "name": "Synthetic tail addressing detail", "mechanism": "尾块地址步长错误", "operator": "SyntheticFoo",
                    "conditions": ["维长65"], "trigger_ids": [EXPECTED_IDS[0]], "evidence_basis": "SOURCE_REPORTED",
                    "evidence": [ref], "unknowns": ["No runtime reproduction"]}]
        if definition_only:
            response["rows"][0].update(relation="PARTIAL", evidence_basis="SOURCE_DEFINITION", source_cells=[cell],
                                       detail_ids=["SYN-DEFINITION"])
            response["details"] = [{"detail_id": "SYN-DEFINITION", "mode_id": payload["subject"]["mode_id"],
                "name": "Synthetic source definition", "mechanism": source["raw"]["故障原因"],
                "trigger_ids": [EXPECTED_IDS[0]], "evidence_basis": "SOURCE_DEFINITION", "source_cells": [cell]}]
        return response

    def accept(self, payload, **options):
        request = self.request(payload)
        return workflow.accept_assessment(self.store, self.run, request, self.response(request, **options))

    def complete_matched(self):
        for case in self.cases():
            self.summary(self.capture(case))
        for payload in list(workflow.classification_payloads(self.store, self.run)):
            self.accept(payload, relation="MATCH")

    def test_init_preserves_actual_original_ids_cells_and_separate_branches(self):
        cfg = self.start(2)
        self.assertEqual((cfg["mode_count"], cfg["trigger_count"]), (2, 42))
        self.assertEqual(cfg["branch_categories"], ["2.1", "2.2", "2.3", "3.1", "3.2", "3.3"])
        self.assertEqual([c["external_id"] for c in self.cases()], ["SYN-ORIGINAL-7", "SYN-ORIGINAL-12"])
        for row, case in enumerate(self.cases(), start=2):
            self.assertEqual(case["source_file"], str(self.modes.resolve()))
            self.assertEqual(case["cell_locations"]["故障原因"], f"C{row}")
        subjects = self.store.records(self.run, "trigger_subjects")
        self.assertEqual({s["mode_id"] for s in subjects}, {"SYN-ORIGINAL-7", "SYN-ORIGINAL-12"})
        self.assertTrue(all(s["subject_kind"] == "MODE_ENTRY" for s in subjects))
        self.assertEqual({s["case_id"] for s in subjects}, set(cfg["selected_case_ids"]))
        self.assertEqual(self.store.records(self.run, "judgments"), [])

    def test_even_provisional_baseline_requires_every_original_mode_assessed(self):
        self.start(2)
        payloads = list(workflow.classification_payloads(self.store, self.run))
        self.accept(payloads[0])
        for allow_pending in (False, True):
            with self.subTest(allow_pending=allow_pending), self.assertRaisesRegex(AuditError, "Every original mode"):
                workflow.finalize(self.store, self.run, allow_pending=allow_pending)
        self.assertEqual(self.store.records(self.run, "trigger_baselines"), [])

    def test_definition_only_baseline_is_provisional_and_cannot_confirm_coverage(self):
        self.start()
        self.accept(next(workflow.classification_payloads(self.store, self.run)), definition_only=True)
        with self.assertRaises(AuditError):
            workflow.finalize(self.store, self.run)
        baseline = workflow.finalize(self.store, self.run, allow_pending=True)
        self.assertEqual(baseline["status"], "READY_WITH_GAPS")
        self.assertEqual(baseline["coverage_details"], [])
        self.assertFalse(baseline["execution_verified"])
        with self.assertRaisesRegex(AuditError, "provisional|gaps"):
            workflow._baseline(self.store, self.run)
        self.assertEqual(workflow._baseline(self.store, self.run, allow_pending=True)["baseline_id"], baseline["baseline_id"])

    def test_provisional_incremental_start_requires_explicit_flag_and_keeps_original_library(self):
        self.start()
        self.accept(next(workflow.classification_payloads(self.store, self.run)))
        baseline = workflow.finalize(self.store, self.run, allow_pending=True)
        source = self.root / "synthetic_new_cases.xlsx"
        book = Workbook()
        book.active.append(["统一ID", "问题描述"])
        book.active.append(["SYN-NEW-1", "Synthetic new fault, mechanism unknown"])
        book.save(source)
        baseline_run = self.run
        with self.assertRaisesRegex(AuditError, "provisional|gaps"):
            workflow.start_incremental(self.store, source, baseline_run, self.work, executor="codex")
        cfg = workflow.start_incremental(self.store, source, baseline_run, self.work, executor="codex",
                                         allow_pending_baseline=True)
        self.assertEqual(cfg["purpose"], "TRIGGER_INCREMENTAL")
        self.assertEqual(cfg["baseline_id"], baseline["baseline_id"])
        self.assertEqual([c["item_id"] for c in self.store.records(cfg["run_id"], "catalog")], ["SYN-ORIGINAL-7"])
        self.assertEqual(self.store.records(cfg["run_id"], "catalog")[0]["source_file"], str(self.modes.resolve()))

    def test_each_snapshot_and_subissue_has_independent_deduplicated_work(self):
        self.start()
        snapshots = [self.capture(), self.capture(url="https://example.invalid/wiki/second")]
        for snapshot in snapshots:
            self.summary(snapshot, count=2)
        payloads = list(workflow.classification_payloads(self.store, self.run))
        keys = {(p["source_issue"]["snapshot_id"], p["source_issue"]["issue_index"]) for p in payloads}
        self.assertEqual(keys, {(s["snapshot_id"], index) for s in snapshots for index in range(2)})
        self.assertEqual(len({self.request(p)["task_id"] for p in payloads}), 4)
        self.accept(payloads[0])
        remaining = list(workflow.classification_payloads(self.store, self.run))
        self.assertEqual(len(remaining), 3)
        self.assertEqual([self.request(p)["task_id"] for p in remaining],
                         [self.request(p)["task_id"] for p in workflow.classification_payloads(self.store, self.run)])
        with self.assertRaisesRegex(AuditError, "issue|Issue"):
            workflow.finalize(self.store, self.run, allow_pending=True)

    def test_incomplete_or_mock_summary_is_not_exposed_as_completed_issue(self):
        self.start()
        snapshot = self.capture()
        self.summary(snapshot, count=2, processed=0)
        self.assertIsNone(next(workflow.classification_payloads(self.store, self.run))["source_issue"])
        self.summary(snapshot, count=2, revision=2, mode="mock")
        self.assertIsNone(next(workflow.classification_payloads(self.store, self.run))["source_issue"])
        self.summary(snapshot, count=2, revision=3)
        self.assertEqual(len(list(workflow.classification_payloads(self.store, self.run))), 2)

    def test_current_source_relations_exclude_only_after_all_snapshot_issues_assessed(self):
        self.start()
        snapshot = self.capture()
        self.summary(snapshot, count=2)
        payloads = list(workflow.classification_payloads(self.store, self.run))
        pair = (payloads[0]["subject"]["case_id"], snapshot["snapshot_id"])
        self.accept(payloads[0], relation="NOT_RELATED")
        self.assertNotIn(pair, workflow.source_relations(self.store, self.run))
        self.accept(payloads[1], relation="NOT_RELATED")
        self.assertEqual(workflow.source_relations(self.store, self.run)[pair], "NOT_RELATED")

    def test_current_assessments_and_source_relations_do_not_reenter_routing(self):
        self.start()
        self.complete_matched()
        with patch("faultaudit.evidence_plan.build_evidence_plan", side_effect=AssertionError("Unexpected plan recursion")), \
             patch("faultaudit.wiki_checks.wiki_plan", side_effect=AssertionError("Unexpected Wiki recursion")):
            before = self.store.conn.total_changes
            values = workflow.current_assessments(self.store, self.run)
            relations = workflow.source_relations(self.store, self.run)
            self.assertEqual(len(values), 1)
            self.assertEqual(list(relations.values()), ["MATCH"])
            self.assertEqual(self.store.conn.total_changes, before)

    def test_current_evidence_baseline_does_not_require_all_42_predicates_proved(self):
        self.start()
        self.complete_matched()
        baseline = workflow.finalize(self.store, self.run)
        self.assertEqual(len(baseline["coverage_details"]), 1)
        self.assertEqual(baseline["coverage_kind"], "HISTORICAL_EVIDENCE")
        self.assertFalse(baseline["execution_verified"])
        self.assertEqual(workflow._baseline(self.store, self.run)["baseline_id"], baseline["baseline_id"])

    def test_new_candidate_keeps_old_independent_assessment_but_requires_baseline_maintenance(self):
        self.start()
        self.complete_matched()
        original = workflow.current_assessments(self.store, self.run)
        baseline = workflow.finalize(self.store, self.run)
        new_snapshot = self.capture(url="https://example.invalid/wiki/new-candidate")
        self.summary(new_snapshot)
        self.assertEqual(workflow.current_assessments(self.store, self.run), original)
        payloads = list(workflow.classification_payloads(self.store, self.run))
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["source_issue"]["snapshot_id"], new_snapshot["snapshot_id"])
        with self.assertRaisesRegex(AuditError, "stale"):
            workflow._baseline(self.store, self.run)
        self.assertEqual(self.store.get(self.run, "trigger_baselines", baseline["baseline_id"]), baseline)

    def test_completed_wiki_check_does_not_invalidate_cited_snapshot_assessment(self):
        from faultaudit.wiki_checks import record_wiki_check

        self.start()
        self.complete_matched()
        original = workflow.current_assessments(self.store, self.run)
        snapshot = self.store.active_snapshots(self.run)[0]
        record_wiki_check(self.store, self.run, self.cases()[0]["case_id"], outcome="FOUND", snapshot_id=snapshot["snapshot_id"])
        self.assertEqual(workflow.current_assessments(self.store, self.run), original)
        self.assertEqual(list(workflow.classification_payloads(self.store, self.run)), [])

    def test_definition_only_assessment_expires_when_source_content_becomes_available(self):
        self.start()
        self.accept(next(workflow.classification_payloads(self.store, self.run)), definition_only=True)
        self.assertEqual(len(workflow.current_assessments(self.store, self.run)), 1)
        self.summary(self.capture())
        self.assertEqual(workflow.current_assessments(self.store, self.run), [])
        self.assertEqual(len(self.store.records(self.run, "trigger_assessments")), 1)
        self.assertIsNotNone(next(workflow.classification_payloads(self.store, self.run))["source_issue"])

    def test_stale_source_request_cannot_be_submitted_and_old_response_is_retained(self):
        self.start()
        snapshot = self.capture()
        self.summary(snapshot)
        payload = next(workflow.classification_payloads(self.store, self.run))
        request = self.request(payload)
        self.capture(text="Revised source; previous issue content has been replaced.")
        with self.assertRaisesRegex(AuditError, "changed|fresh"):
            workflow.accept_assessment(self.store, self.run, request, self.response(request, relation="MATCH"))
        self.assertEqual(self.store.records(self.run, "trigger_assessments"), [])
        self.assertEqual(len(self.store.records(self.run, "snapshots")), 2)
        self.assertEqual(len(self.store.records(self.run, "summaries")), 1)

    def test_source_summary_or_policy_changes_stale_baseline_without_deleting_history(self):
        for change in ("source", "summary", "policy"):
            with self.subTest(change=change):
                self.start()
                self.complete_matched()
                baseline = workflow.finalize(self.store, self.run, allow_pending=True)
                old = copy.deepcopy(self.store.records(self.run, "trigger_assessments"))
                if change == "source":
                    self.capture(text="Revised source: SyntheticFoo uses another tail addressing strategy at dimension 65.")
                elif change == "summary":
                    snapshot = self.store.active_snapshots(self.run)[0]
                    self.summary(snapshot, revision=2)
                if change == "policy":
                    with patch("faultaudit.xlsx_workflow._policy", return_value="changed-trigger-policy"):
                        self.assertEqual(workflow.current_assessments(self.store, self.run), [])
                        with self.assertRaisesRegex(AuditError, "stale"):
                            workflow._baseline(self.store, self.run, allow_pending=True)
                else:
                    self.assertEqual(workflow.current_assessments(self.store, self.run), [])
                    with self.assertRaisesRegex(AuditError, "stale"):
                        workflow._baseline(self.store, self.run, allow_pending=True)
                self.assertEqual(self.store.records(self.run, "trigger_assessments"), old)
                self.assertEqual(self.store.get(self.run, "trigger_baselines", baseline["baseline_id"]), baseline)


if __name__ == "__main__":
    unittest.main()
