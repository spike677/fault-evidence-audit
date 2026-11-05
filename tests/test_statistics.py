"""Synthetic report reconciliation; these tests never open production SQLite."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from faultaudit.statistics import report_statistics


def _judgment(identity, case_id, snapshot_id, *, attribution="PARTIAL", event="UNDETERMINED", support="PARTIAL", review="NEEDS_REVIEW", stale=False):
    return {"judgment_id": identity, "task_id": identity, "case_id": case_id, "snapshot_id": snapshot_id,
            "case_attribution": attribution, "event_relation": event, "pattern_relation": "POSSIBLY_RELATED",
            "support_level": support, "review_status": review, "is_stale": stale,
            "conflicting_dimensions": [], "claim_support": {"root_cause": "PARTIAL"},
            "model_mode": "opencode", "model_id": "synthetic-model"}


def fixture():
    run_id = "synthetic-run"
    old = _judgment("J-OLD", "case-old", "S-OLD", stale=True)
    judgments = [old,
        _judgment("J-1", "case-1", "S-1", attribution="CONFIRMED", event="SAME_EVENT", support="DIRECT", review="ACCEPT"),
        _judgment("J-2", "case-1", "S-2", attribution="MISMATCH", event="DIFFERENT_EVENT", support="NONE", review="REJECT"),
        _judgment("J-3", "case-2", "S-3")]
    mapping = {"task_id": "M-1", "case_id": "case-1", "overall": "UNDETERMINED", "catalog_results": [],
               "model_mode": "opencode", "model_id": "synthetic-model", "review_status": "NEEDS_REVIEW", "is_stale": False}
    data = {"run": {"run_id": run_id}, "cases": [{"case_id": identity} for identity in ("case-old", "case-1", "case-2", "case-no-judgment")],
        "snapshots": [{"snapshot_id": identity, "is_stale": identity == "S-OLD", "status": "COMPLETE"}
                      for identity in ("S-OLD", "S-1", "S-2", "S-3")],
        "judgments": judgments, "mappings": [mapping], "tasks": [], "model_tasks": [], "model_results": []}
    for record, kind in [(judgment, "compare") for judgment in judgments] + [(mapping, "catalog")]:
        task_id = record["task_id"]
        data["tasks"].append({"task_id": task_id, "run_id": run_id, "kind": kind,
                              "status": "STALE" if record["is_stale"] else "SUCCEEDED"})
        payload = {"case": {"case_id": record["case_id"]}}
        if kind == "compare":
            payload["snapshot"] = {"snapshot_id": record["snapshot_id"]}
        result = {key: value for key, value in record.items()
                  if key not in {"judgment_id", "task_id", "review_status", "is_stale"}}
        model_task_id = "MODEL-" + task_id
        data["model_tasks"].append({"task_id": model_task_id, "pipeline_task_id": task_id, "kind": kind,
                                    "run_id": run_id, "request_hash": "hash-" + task_id, "payload": payload})
        data["model_results"].append({"task_id": model_task_id, "run_id": run_id, "request_hash": "hash-" + task_id, "result": result})
    baseline = copy.deepcopy(data)
    baseline["judgments"] = baseline["judgments"][:1]
    baseline["judgments"][0]["is_stale"] = False
    baseline["snapshots"] = baseline["snapshots"][:1]
    baseline["snapshots"][0]["is_stale"] = False
    baseline["mappings"] = []
    baseline["tasks"] = baseline["tasks"][:1]
    baseline["tasks"][0]["status"] = "SUCCEEDED"
    baseline["model_tasks"] = baseline["model_tasks"][:1]
    baseline["model_results"] = baseline["model_results"][:1]
    manifest = {"run_id": run_id, "judgment_ids": ["J-1", "J-2", "J-3"], "mapping_ids": ["M-1"],
                "snapshot_ids": ["S-1", "S-2", "S-3"]}
    return data, baseline, manifest


class StatisticsTests(unittest.TestCase):
    def test_current_uses_judgment_ids_and_separate_case_ids_and_reject_policy(self):
        data, _, _ = fixture()
        result = report_statistics(data)
        self.assertEqual(result["current"]["including_rejected"], {"judgment_count": 3, "case_count": 2})
        self.assertEqual(result["current"]["excluding_rejected"], {"judgment_count": 2, "case_count": 2})
        self.assertEqual(result["current"]["rejected"], {"judgment_count": 1, "case_count": 1})
        self.assertEqual(result["current"]["confirmed_accepted"], {"judgment_count": 1, "case_count": 1})
        self.assertEqual(result["current"]["snapshot_count"], 3)
        self.assertEqual(result["round"]["status"], "UNKNOWN")
        self.assertIsNone(result["round"]["new_snapshot_count"])
        self.assertTrue(result["definitions"]["classifications_overlap"])
        self.assertIn("not a fresh database", result["definitions"]["current_scope"])

    def test_axes_overlap_and_do_not_use_case_count_as_judgment_count(self):
        data, _, _ = fixture()
        data["judgments"][3]["case_attribution"] = "CONFIRMED"
        result = report_statistics(data)
        bucket = result["current"]["classifications"]["case_attribution"]["CONFIRMED"]
        self.assertEqual(bucket, {"judgment_count": 2, "case_count": 2})
        data["judgments"][3]["case_id"] = "case-1"
        result = report_statistics(data)
        self.assertEqual(result["current"]["classifications"]["case_attribution"]["CONFIRMED"], {"judgment_count": 2, "case_count": 1})

    def test_identical_records_deduplicate_but_conflicting_duplicates_fail(self):
        data, _, _ = fixture()
        for name in ("judgments", "snapshots", "mappings"):
            data[name].append(copy.deepcopy(data[name][-1]))
        result = report_statistics(data)
        self.assertEqual(result["current"]["including_rejected"]["judgment_count"], 3)
        self.assertEqual(result["current"]["snapshot_count"], 3)
        data["judgments"][-1]["case_id"] = "case-1"
        failed = report_statistics(data)
        self.assertEqual(failed["status"], "RECONCILIATION_FAILED")
        self.assertIsNone(failed["current"]["including_rejected"]["judgment_count"])
        self.assertTrue(any(error["code"] == "CONFLICTING_DUPLICATE_ID" for error in failed["errors"]))

    def test_round_counts_require_both_inputs_and_match_full_history_delta(self):
        data, baseline, manifest = fixture()
        for before, selected in ((None, None), (baseline, None), (None, manifest)):
            unknown = report_statistics(data, before, selected)
            self.assertEqual(unknown["round"]["status"], "UNKNOWN")
            self.assertIsNone(unknown["round"]["new_judgment_count"])
        result = report_statistics(data, baseline, manifest)
        self.assertEqual(result["round"]["status"], "KNOWN", result)
        self.assertEqual(result["round"]["new_judgment_count"], 3)
        self.assertEqual(result["round"]["new_case_count"], 2)
        self.assertEqual(result["round"]["new_snapshot_count"], 3)
        self.assertEqual(result["round"]["new_mapping_count"], 1)
        self.assertEqual(result["round"]["new_judgment_count_excluding_rejected"], 2)

    def test_round_stale_history_is_kept_but_current_new_excludes_it(self):
        data, baseline, manifest = fixture()
        data["judgments"][3]["is_stale"] = True
        data["snapshots"][3]["is_stale"] = True
        next(task for task in data["tasks"] if task["task_id"] == "J-3")["status"] = "STALE"
        result = report_statistics(data, baseline, manifest)
        self.assertEqual(result["round"]["status"], "KNOWN", result)
        self.assertEqual(result["round"]["new_judgment_count"], 3)
        self.assertEqual(result["round"]["current_new_judgment_count"], 2)
        self.assertEqual(result["round"]["current_new_case_count"], 1)
        self.assertEqual(result["round"]["new_snapshot_count"], 3)
        self.assertEqual(result["round"]["current_new_snapshot_count"], 2)

    def test_empty_reconciled_round_is_zero_but_missing_manifest_is_not_zero(self):
        data, _, _ = fixture()
        empty = {"run_id": "synthetic-run", "judgment_ids": [], "mapping_ids": [], "snapshot_ids": []}
        result = report_statistics(data, copy.deepcopy(data), empty)
        self.assertEqual(result["round"]["status"], "KNOWN")
        self.assertEqual(result["round"]["new_judgment_count"], 0)
        self.assertEqual(result["round"]["new_snapshot_count"], 0)

    def test_incomplete_or_old_ids_in_manifest_fail_with_null_counts(self):
        data, baseline, manifest = fixture()
        for field, value in (("judgment_ids", ["J-1"]), ("snapshot_ids", ["S-1", "S-2"]),
                             ("mapping_ids", []), ("judgment_ids", ["J-1", "J-2", "J-3", "J-OLD"])):
            bad = {**manifest, field: value}
            result = report_statistics(data, baseline, bad)
            self.assertEqual(result["round"]["status"], "RECONCILIATION_FAILED")
            self.assertIsNone(result["round"]["new_snapshot_count"])
        bad = copy.deepcopy(manifest)
        del bad["snapshot_ids"]
        self.assertEqual(report_statistics(data, baseline, bad)["status"], "RECONCILIATION_FAILED")

    def test_pipeline_manifest_can_infer_result_ids_without_guessing(self):
        data, baseline, manifest = fixture()
        selected = {"run_id": "synthetic-run", "snapshot_ids": manifest["snapshot_ids"],
                    "pipeline_task_ids": ["J-1", "J-2", "J-3", "M-1"]}
        result = report_statistics(data, baseline, selected)
        self.assertEqual(result["round"]["status"], "KNOWN", result)
        self.assertEqual(result["round"]["new_judgment_count"], 3)
        selected["judgment_ids"] = ["J-1"]
        self.assertEqual(report_statistics(data, baseline, selected)["status"], "RECONCILIATION_FAILED")

    def test_new_results_need_matching_model_response_and_succeeded_task(self):
        data, baseline, manifest = fixture()
        for change in ("missing_response", "wrong_hash", "wrong_case", "wrong_result", "failed_task"):
            modified = copy.deepcopy(data)
            response = next(result for result in modified["model_results"] if result["task_id"] == "MODEL-J-1")
            if change == "missing_response":
                modified["model_results"].remove(response)
            elif change == "wrong_hash":
                response["request_hash"] = "wrong"
            elif change == "wrong_case":
                response["result"]["case_id"] = "case-2"
            elif change == "wrong_result":
                response["result"]["support_level"] = "NONE"
            else:
                next(task for task in modified["tasks"] if task["task_id"] == "J-1")["status"] = "FAILED"
            with self.subTest(change=change):
                result = report_statistics(modified, baseline, manifest)
                self.assertEqual(result["status"], "RECONCILIATION_FAILED")
                self.assertIsNone(result["round"]["new_judgment_count"])

    def test_new_unprocessed_snapshot_does_not_require_model_execution(self):
        data, _, _ = fixture()
        baseline = copy.deepcopy(data)
        data["snapshots"].append({"snapshot_id": "JUST-INGESTED", "is_stale": False, "status": "CONTENT_CAPTURED"})
        manifest = {"run_id": "synthetic-run", "judgment_ids": [], "mapping_ids": [], "snapshot_ids": ["JUST-INGESTED"]}
        result = report_statistics(data, baseline, manifest)
        self.assertEqual(result["round"]["status"], "KNOWN", result)
        self.assertEqual(result["round"]["new_snapshot_count"], 1)
        self.assertEqual(result["round"]["new_judgment_count"], 0)

    def test_current_missing_stale_metadata_is_unknown_not_zero(self):
        data, _, _ = fixture()
        del data["judgments"][1]["is_stale"]
        result = report_statistics(data)
        self.assertEqual(result["current"]["status"], "UNKNOWN")
        self.assertIsNone(result["current"]["including_rejected"]["judgment_count"])
        self.assertIsNone(result["current"]["snapshot_count"])
        old_fixture = report_statistics({"cases": []})
        self.assertEqual(old_fixture["status"], "UNKNOWN")
        self.assertIsNone(old_fixture["current"]["including_rejected"]["judgment_count"])

    def test_confirmation_requires_complete_snapshot_and_no_explicit_contradictions(self):
        data, _, _ = fixture()
        for change in ("partial", "dimension_conflict", "claim_conflict", "not_accepted"):
            modified = copy.deepcopy(data)
            if change == "partial":
                modified["snapshots"][1]["status"] = "PARTIAL"
            elif change == "dimension_conflict":
                modified["judgments"][1]["conflicting_dimensions"] = ["root_cause"]
            elif change == "claim_conflict":
                modified["judgments"][1]["claim_support"]["root_cause"] = "CONTRADICTED"
            else:
                modified["judgments"][1]["review_status"] = "NEEDS_REVIEW"
            with self.subTest(change=change):
                self.assertEqual(report_statistics(modified)["current"]["confirmed_accepted"]["judgment_count"], 0)

    def test_wrong_run_and_changed_immutable_baseline_record_fail(self):
        data, baseline, manifest = fixture()
        self.assertEqual(report_statistics(data, baseline, {**manifest, "run_id": "another-run"})["status"], "RECONCILIATION_FAILED")
        modified = copy.deepcopy(data)
        modified["judgments"][0]["case_id"] = "case-1"
        self.assertEqual(report_statistics(modified, baseline, manifest)["status"], "RECONCILIATION_FAILED")

    def test_function_is_read_only_and_does_not_open_sqlite(self):
        data, baseline, manifest = fixture()
        before = copy.deepcopy((data, baseline, manifest))
        with patch("sqlite3.connect", side_effect=AssertionError("report statistics must not open SQLite")):
            report_statistics(data, baseline, manifest)
        self.assertEqual((data, baseline, manifest), before)

    def test_processing_and_selected_scope_are_separate_from_ingested_snapshots(self):
        data, _, _ = fixture()
        for judgment, status, required, review in zip(data["judgments"][1:],
                ("AUTO_PROCESSED", "EXCEPTION", "PENDING"), (False, True, False),
                ("NOT_REQUIRED", "NEEDS_REVIEW", "PENDING_AGENT")):
            judgment.update(processing_status=status, review_required=required, review_status=review)
        data["mappings"][0].update(processing_status="AUTO_PROCESSED", review_required=False, review_status="NOT_REQUIRED")
        data["references"] = [{"ref_id": "R-1"}, {"ref_id": "R-2"}, {"ref_id": "R-unused"}]
        data["evidence_plans"] = {"cases": [{"case_id": "case-1", "selected_ref_ids": ["R-1", "R-2"],
                                              "selected_snapshot_ids": ["S-1", "S-2"]}]}
        data["event_groups"] = [{"group_id": "G-1", "case_ids": ["case-1", "case-2"]}]
        result = report_statistics(data)
        current = result["current"]
        self.assertEqual(current["status"], "OK", result)
        self.assertEqual((current["snapshot_count"], current["selected_snapshot_count"]), (3, 2))
        self.assertEqual((current["unused_reference_count"], current["required_reference_count"]), (1, 2))
        self.assertEqual(current["event_group_count"], 1)
        self.assertEqual((current["auto_processed_count"], current["human_exception_count"], current["agent_pending_count"]), (1, 1, 1))
        self.assertEqual(current["pending_human_exception_count"], 1)
        self.assertEqual(current["mapping_auto_processed_count"], 1)
        self.assertEqual(current["confirmed_accepted"]["judgment_count"], 0)
        self.assertEqual(data["judgments"][1]["review_status"], "NOT_REQUIRED")

    def test_unused_results_are_history_even_when_task_is_failed(self):
        data, _, _ = fixture()
        unused = data["judgments"][2]
        unused["required"] = False
        unused.pop("is_stale")
        next(task for task in data["tasks"] if task["task_id"] == unused["task_id"]).update(required=False, status="FAILED")
        data["mappings"][0]["required"] = False
        result = report_statistics(data)
        self.assertEqual(result["current"]["status"], "OK", result)
        self.assertEqual(result["current"]["including_rejected"], {"judgment_count": 2, "case_count": 2})
        self.assertEqual(result["current"]["mapping_count"], 0)
        self.assertEqual(result["current"]["snapshot_count"], 3)
        self.assertIsNone(result["current"]["selected_snapshot_count"])
        self.assertEqual(len(data["judgments"]), 4)

    def test_group_one_judgment_involves_distinct_member_cases(self):
        data, baseline, manifest = fixture()
        shared = data["judgments"][1]
        shared["member_case_ids"] = ["case-1", "case-2", "case-2"]
        # Keep proof exact: explicit membership is part of the accepted result.
        next(value for value in data["model_results"] if value["task_id"] == "MODEL-J-1")["result"]["member_case_ids"] = shared["member_case_ids"]
        for judgment in data["judgments"][2:]:
            judgment["required"] = False
        result = report_statistics(data, baseline, manifest)
        self.assertEqual(result["status"], "OK", result)
        self.assertEqual(result["current"]["including_rejected"], {"judgment_count": 1, "case_count": 2})
        self.assertEqual(result["current"]["classifications"]["case_attribution"]["CONFIRMED"]["case_count"], 2)
        self.assertEqual(result["round"]["new_judgment_count"], 3)
        self.assertEqual(result["round"]["new_case_count"], 2)
        self.assertEqual(result["round"]["current_new_judgment_count"], 1)
        self.assertEqual(result["round"]["current_new_case_count"], 2)

    def test_selection_metadata_can_change_but_round_history_proof_is_still_required(self):
        data, baseline, manifest = fixture()
        data["judgments"][0]["required"] = False
        data["snapshots"][0]["required"] = False
        data["judgments"][2]["required"] = False
        result = report_statistics(data, baseline, manifest)
        self.assertEqual(result["round"]["status"], "KNOWN", result)
        self.assertEqual(result["round"]["new_judgment_count"], 3)
        self.assertEqual(result["round"]["current_new_judgment_count"], 2)
        # Unselected new judgments are still part of the full historical delta.
        bad = {**manifest, "judgment_ids": ["J-1", "J-3"]}
        self.assertEqual(report_statistics(data, baseline, bad)["round"]["status"], "RECONCILIATION_FAILED")
        data["judgments"][0]["short_reason"] = "history tampering"
        self.assertEqual(report_statistics(data, baseline, manifest)["round"]["status"], "RECONCILIATION_FAILED")

    def test_malformed_optional_selection_is_unknown_not_fabricated_zero(self):
        data, _, _ = fixture()
        data["evidence_plans"] = {"cases": [{"selected_ref_ids": None, "selected_snapshot_ids": {"S-1": True}}]}
        result = report_statistics(data)
        self.assertEqual(result["current"]["status"], "OK")
        self.assertIsNone(result["current"]["selected_snapshot_count"])
        self.assertIsNone(result["current"]["unused_reference_count"])

    def test_distinct_issue_work_counts_do_not_collapse_to_one_case_snapshot_pair(self):
        data, _, _ = fixture()
        data["judgments"][2]["snapshot_id"] = "S-1"
        for judgment, work_id in zip(data["judgments"][1:3], ("W-issue-a", "W-issue-b")):
            judgment["work_id"] = work_id
        data["judgments"][3]["required"] = False
        data["evidence_plans"] = {"cases": [{"case_id": "case-1", "selected_ref_ids": [], "selected_snapshot_ids": ["S-1"]}],
                                  "work_items": [{"work_id": "W-issue-a"}, {"work_id": "W-issue-b"}, {"work_id": "W-issue-a"}]}
        result = report_statistics(data)
        self.assertEqual(result["status"], "OK", result)
        self.assertEqual(result["current"]["including_rejected"], {"judgment_count": 2, "case_count": 1})
        self.assertEqual((result["current"]["current_work_count"], result["current"]["planned_work_count"]), (2, 2))
        self.assertEqual(result["current"]["current_case_snapshot_pair_count"], 1)
        self.assertEqual(result["current"]["selected_snapshot_count"], 1)
        self.assertEqual(result["current"]["snapshot_count"], 3)

    def test_two_current_judgments_of_same_work_fail_instead_of_choosing_one(self):
        data, _, _ = fixture()
        data["judgments"][1]["work_id"] = data["judgments"][2]["work_id"] = "W-same"
        result = report_statistics(data)
        self.assertEqual(result["status"], "RECONCILIATION_FAILED")
        self.assertIsNone(result["current"]["including_rejected"]["judgment_count"])
        self.assertTrue(any(error["code"] == "CURRENT_WORK_ID_CONFLICT" for error in result["errors"]))

    def test_round_result_requires_the_exact_issue_work_request_binding(self):
        data, baseline, manifest = fixture()
        for judgment in data["judgments"][1:]:
            work_id = "W-" + judgment["judgment_id"]
            judgment["work_id"] = work_id
            request = next(value for value in data["model_tasks"] if value["pipeline_task_id"] == judgment["task_id"])
            response = next(value for value in data["model_results"] if value["task_id"] == request["task_id"])
            request["work_id"] = response["work_id"] = work_id
            request["payload"]["processing_context"] = {"work_id": work_id, "applicable_issue": {"scope": "ISSUES", "applicable_issue_ids": [work_id]}}
        self.assertEqual(report_statistics(data, baseline, manifest)["round"]["status"], "KNOWN")
        request = next(value for value in data["model_tasks"] if value["pipeline_task_id"] == "J-1")
        request["payload"]["processing_context"]["work_id"] = "another-issue-work"
        failed = report_statistics(data, baseline, manifest)
        self.assertEqual(failed["round"]["status"], "RECONCILIATION_FAILED")
        self.assertTrue(any(error["code"] == "ROUND_WORK_SCOPE_CONFLICT" for error in failed["errors"]))
        request["payload"]["processing_context"]["work_id"] = "W-J-1"
        next(value for value in data["model_results"] if value["task_id"] == request["task_id"])["work_id"] = "another-issue-work"
        self.assertEqual(report_statistics(data, baseline, manifest)["round"]["status"], "RECONCILIATION_FAILED")


if __name__ == "__main__":
    unittest.main()
