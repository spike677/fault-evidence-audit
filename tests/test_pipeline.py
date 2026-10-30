import json
import tempfile
import unittest
from pathlib import Path

from faultaudit.importers import import_cases, import_catalog
from faultaudit.model import MockJudge
from faultaudit.pipeline import (current_judgments, execute, fetch_tasks, gate_judgment,
                                 import_into, report_data, validate)
from faultaudit.store import AuditError, Store


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.test_root = Path(__file__).resolve().parent
        self.temp = tempfile.TemporaryDirectory(dir=self.test_root)
        self.directory = Path(self.temp.name).resolve()
        self.store = Store(self.directory / "state")
        self.run_id = self.store.create_run({"is_synthetic": True})

    def tearDown(self):
        self.store.close()
        self.assertTrue(self.directory.is_relative_to(self.test_root))
        self.temp.cleanup()

    def load_case(self, *, url="https://example.invalid/wiki/one", include_link=True, extra=None):
        row = {"统一ID": "CASE-DELTA", "问题描述": "Model-X输出乱码", "算子": "all_reduce", "根因": "all_reduce精度异常"}
        if include_link:
            row["wiki"] = url
        row.update(extra or {})
        path = self.directory / "weekly.json"
        path.write_text(json.dumps([row], ensure_ascii=False), encoding="utf-8")
        imported = import_cases(path, "ORIGINAL_WEEKLY")
        import_into(self.store, self.run_id, imported)
        return imported["cases"][0]

    def add_evidence(self, case, **overrides):
        package = {"url": "https://example.invalid/wiki/one", "title": "合成核验资料",
                   "text": "合成样例：all_reduce精度异常，具体事件尚待确认。",
                   "status": "COMPLETE", "components": {"body": "COMPLETE"},
                   "case_ids": [case["case_id"]], "is_synthetic": True,
                   "retrieved_by": "unittest-fixture", **overrides}
        return self.store.ingest_evidence(self.run_id, package)

    def run_mock(self, judge=None, model_id=None):
        judge = judge or MockJudge()
        return execute(self.store, self.run_id, judge, mode="mock", model_id=model_id or judge.model_id)

    def test_summary_metadata_does_not_break_comparison(self):
        case = self.load_case()
        self.add_evidence(case)
        result = self.run_mock()
        compare = [task for task in self.store.tasks(self.run_id) if task["kind"] == "compare"]
        self.assertEqual(len(compare), 1)
        self.assertEqual(compare[0]["status"], "SUCCEEDED", compare[0]["error"])
        self.assertEqual(result["counts"]["judged_associations"], 1)
        self.assertFalse(result["complete"], "Mock execution must remain visibly unverified")

    def test_malformed_url_is_visible_without_crashing_entire_run(self):
        self.load_case(url="https://")
        plan = fetch_tasks(self.store, self.run_id)
        self.assertTrue(plan["malformed_references"])
        result = self.run_mock()
        self.assertFalse(result["complete"])
        self.assertTrue(result["pending"])

    def test_snapshot_update_invalidates_old_judgment_and_summary(self):
        case = self.load_case()
        old = self.add_evidence(case)
        self.run_mock()
        self.assertEqual(len(current_judgments(self.store, self.run_id)), 1)
        new = self.add_evidence(case, text="合成更新：定位尚未完成，保留all_reduce排查方向。")
        self.assertNotEqual(old["snapshot_id"], new["snapshot_id"])
        self.assertEqual(current_judgments(self.store, self.run_id), [])
        data = report_data(self.store, self.run_id)
        self.assertTrue(all(s["is_stale"] for s in data["summaries"]))
        self.run_mock()
        current = current_judgments(self.store, self.run_id)
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["snapshot_id"], new["snapshot_id"])

    def test_operator_word_is_not_an_event_anchor(self):
        case = self.load_case()
        snapshot = self.add_evidence(case)
        segment = snapshot["segments"][0]
        proposed = {"case_id": case["case_id"], "snapshot_id": snapshot["snapshot_id"],
                    "case_attribution": "CONFIRMED", "event_relation": "SAME_EVENT",
                    "pattern_relation": "SAME_PATTERN", "support_level": "DIRECT",
                    "claim_support": {"symptom": "SUPPORTED", "root_cause": "SUPPORTED", "fix": "UNKNOWN", "verification": "UNKNOWN"},
                    "matched_dimensions": ["operator"], "conflicting_dimensions": [], "unknown_dimensions": [],
                    "event_anchor": "all_reduce", "evidence": [{"segment_id": segment["segment_id"], "quote": segment["text"]}],
                    "short_reason": "不充分的算子匹配不能当事件证据", "missing_information": [],
                    "model_mode": "deepseek", "model_id": "test-model"}
        with self.assertRaises((AuditError, ValueError)):
            gate_judgment(case, snapshot, proposed)

    def test_snapshot_hash_tampering_fails_validation(self):
        case = self.load_case()
        snapshot = self.add_evidence(case)
        Path(snapshot["text_path"]).write_text("tampered", encoding="utf-8")
        result = validate(self.store, self.run_id)
        self.assertFalse(result["valid"])
        self.assertTrue(any("hash" in error.lower() for error in result["errors"]))

    def test_linkless_case_is_never_silently_discarded(self):
        case = self.load_case(include_link=False)
        result = self.run_mock()
        self.assertEqual(result["counts"]["cases"], 1)
        self.assertFalse(result["complete"])
        self.assertTrue(any(case["case_id"] in message and "no references" in message for message in result["pending"]))

    def test_search_discovery_is_not_lost_when_original_url_exists(self):
        case = self.load_case()
        self.add_evidence(case)
        self.assertEqual(len(self.store.records(self.run_id, "references")), 1)
        self.add_evidence(case, origin="SEARCH_DISCOVERED", record_discovery=True,
                          discovery_query="Model-X all_reduce root cause")
        references = self.store.records(self.run_id, "references")
        self.assertEqual(len(references), 2)
        self.assertEqual({ref["origin"] for ref in references}, {"ORIGINAL_WEEKLY", "SEARCH_DISCOVERED"})

    def test_changed_model_does_not_leave_two_current_judgments(self):
        case = self.load_case()
        self.add_evidence(case)
        self.run_mock()
        second = MockJudge()
        second.model_id = "offline-mock-v2"
        self.run_mock(second)
        current = current_judgments(self.store, self.run_id)
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["model_id"], "offline-mock-v2")
        old_summaries = [summary for summary in report_data(self.store, self.run_id)["summaries"]
                         if summary["model_id"] == "offline-mock-v1"]
        self.assertTrue(old_summaries and all(summary["is_stale"] for summary in old_summaries))

    def test_actual_model_revision_can_differ_from_requested_alias(self):
        case = self.load_case()
        self.add_evidence(case)
        judge = MockJudge()
        judge.model_id = "mock-actual-revision"
        self.run_mock(judge, model_id="mock-requested-alias")
        current = current_judgments(self.store, self.run_id, mode="mock", model_id="mock-requested-alias")
        self.assertEqual(len(current), 1, "Selection should use requested model signature, preserving actual model revision in audit")

    def test_citation_from_another_snapshot_is_rejected(self):
        case = self.load_case()
        first = self.add_evidence(case)
        second = self.add_evidence(case, url="https://example.invalid/wiki/another", case_ids=[])
        proposed = {"case_id": case["case_id"], "snapshot_id": first["snapshot_id"],
                    "case_attribution": "PARTIAL", "event_relation": "UNDETERMINED",
                    "pattern_relation": "POSSIBLY_RELATED", "support_level": "PARTIAL",
                    "claim_support": {"root_cause": "PARTIAL"},
                    "evidence": [{"segment_id": second["segments"][0]["segment_id"], "quote": second["text"]}],
                    "short_reason": "错误地引用另一个快照", "model_mode": "deepseek", "model_id": "test-model"}
        with self.assertRaises((AuditError, ValueError)):
            gate_judgment(case, first, proposed)

    def test_duplicate_identical_catalog_ids_are_not_silently_coalesced(self):
        path = self.directory / "catalog.json"
        duplicate = {"item_id": "F-001", "description": "合成库条目", "mechanism": "precision"}
        path.write_text(json.dumps({"items": [duplicate, duplicate]}, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(AuditError):
            import_into(self.store, self.run_id, import_catalog(path), catalog=True)

    def test_catalog_version_is_frozen_within_one_run(self):
        path = self.directory / "catalog.json"
        path.write_text(json.dumps({"items": [{"item_id": "F-001", "description": "first"}]}), encoding="utf-8")
        import_into(self.store, self.run_id, import_catalog(path), catalog=True)
        path.write_text(json.dumps({"items": [{"item_id": "F-002", "description": "second version"}]}), encoding="utf-8")
        with self.assertRaises(AuditError):
            import_into(self.store, self.run_id, import_catalog(path), catalog=True)

    def test_model_switch_back_reactivates_valid_input(self):
        case = self.load_case()
        self.add_evidence(case)
        first = MockJudge()
        self.run_mock(first)
        second = MockJudge()
        second.model_id = "offline-mock-v2"
        self.run_mock(second)
        self.run_mock(first)
        current = current_judgments(self.store, self.run_id)
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]["model_id"], first.model_id)

    def test_executor_revision_change_invalidates_cached_tasks(self):
        case = self.load_case()
        self.add_evidence(case)
        first = MockJudge()
        first.execution_signature = "opencode-executor-revision-a"
        self.run_mock(first)
        initial_tasks = {task["task_id"] for task in self.store.tasks(self.run_id) if task["kind"] == "summarize"}
        second = MockJudge()
        second.execution_signature = "opencode-executor-revision-b"
        self.run_mock(second)
        subsequent = {task["task_id"] for task in self.store.tasks(self.run_id) if task["kind"] == "summarize"}
        self.assertGreater(len(subsequent), len(initial_tasks))

    def test_repeated_search_discovery_package_is_idempotent(self):
        case = self.load_case()
        discovery = {"origin": "SEARCH_DISCOVERED", "record_discovery": True,
                     "discovery_query": "Model-X all_reduce root cause"}
        self.add_evidence(case, **discovery)
        self.add_evidence(case, **discovery)
        self.assertEqual(len(self.store.records(self.run_id, "references")), 2)

    def test_one_case_keeps_wiki_dts_and_pr_as_distinct_references(self):
        self.load_case(extra={"DTS": "https://example.invalid/dts/123", "PR": "https://example.invalid/pr/456"})
        references = self.store.records(self.run_id, "references")
        self.assertEqual(len(references), 3)
        self.assertEqual(len({reference["ref_id"] for reference in references}), 3)
        self.assertEqual({reference["url"] for reference in references}, {
            "https://example.invalid/wiki/one", "https://example.invalid/dts/123", "https://example.invalid/pr/456"})


if __name__ == "__main__":
    unittest.main()
