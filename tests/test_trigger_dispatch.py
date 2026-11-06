"""Real task dispatch with synthetic Agent responses and no network access."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from openpyxl import Workbook

from faultaudit import trigger_workflow, xlsx_workflow
from faultaudit.store import AuditError
from tests import test_trigger_workflow as fixtures


class TriggerDispatchTests(unittest.TestCase):
    setUp = fixtures.TriggerWorkflowTests.setUp
    tearDown = fixtures.TriggerWorkflowTests.tearDown
    write_modes = fixtures.TriggerWorkflowTests.write_modes
    start = fixtures.TriggerWorkflowTests.start
    cases = fixtures.TriggerWorkflowTests.cases
    response = fixtures.TriggerWorkflowTests.response

    def request(self, task):
        return json.loads(Path(task["request"]).read_text(encoding="utf-8"))

    def next(self):
        step = xlsx_workflow.next_tasks(self.store, self.run)
        for task in step["tasks"]:
            if task["kind"] == "model":
                self.assertEqual(self.request(task)["payload"]["task"]["kind"], "summarize")
            self.assertNotIn(task["kind"], {"compare", "catalog", "catalog_draft"})
        return step

    def package(self, url, *, title="Synthetic captured source", text=None):
        text = text or "SyntheticFoo在维长65时尾块地址步长错误。\n另一个独立子问题：布局读取错误。"
        return {"url": url, "title": title, "text": text, "status": "CONTENT_CAPTURED",
            "components": {"body": "COMPLETE"}, "is_synthetic": True,
            "capture_observation": {"page_kind": "BODY", "requested_url": url, "final_url": url,
                "title": title, "body_locator": "synthetic article body", "body_quotes": [text],
                "observed_by": "synthetic-agent", "observed_at": "2026-11-06T10:00:00+08:00",
                "tool_observation": "Synthetic fixture; no real website accessed"}}

    def summary_envelope(self, task, issue_count=2):
        wrapper = self.request(task)
        inner = wrapper["payload"]["task"]
        self.assertEqual(inner["kind"], "summarize")
        snapshot = inner["payload"]["snapshot"]
        segment = snapshot["segments"][0]
        quotes = segment["text"].splitlines()
        return {"schema_version": "1.0", "run_id": self.run, "task_id": inner["task_id"],
            "request_hash": inner["request_hash"], "result": {"snapshot_id": snapshot["snapshot_id"],
                "issues": [{"label": f"synthetic-issue-{index}", "facts": [{"field": "root_cause",
                    "value": quotes[index % len(quotes)], "evidence": [{"segment_id": segment["segment_id"],
                    "quote": quotes[index % len(quotes)]}]}]} for index in range(issue_count)], "unknown_fields": []},
            "producer": {"executor": "codex", "codex_version": "synthetic",
                "provider": "synthetic-only", "model": "synthetic-summary-model", "session_id": "offline-dispatch-test"}}

    def submit(self, task, response):
        result = xlsx_workflow.submit(self.store, self.run, task["task_id"], response)
        self.assertTrue(result["accepted"])
        duplicate = xlsx_workflow.submit(self.store, self.run, task["task_id"], response)
        self.assertTrue(duplicate["idempotent"])
        return result

    def search_response(self, task, *, outcome="NO_MATCH", packages=None):
        request = self.request(task)
        case = request["payload"]["case"]
        lookup = request["payload"].get("source_lookup")
        field = "案例链接" if lookup else "模式名称"
        quote = case["raw"][field]
        return {"request_hash": request["request_hash"], "outcome": outcome, "executed": True,
            "query": "Synthetic source-grounded query", "scope": "Synthetic Wiki/DTS corpus",
            "checked_at": "2026-11-06T10:00:00+08:00", "executed_by": "synthetic-agent",
            "reason": "Synthetic bounded search result", "packages": packages or [],
            "search_facets": [{"kind": "identifier" if lookup else "symptom", "value": quote,
                "source_field": field, "source_cell": case["cell_locations"][field], "source_quote": quote, "hypothesis": False}],
            "search_attempts": [{"round": 1, "query": "Synthetic source-grounded query", "scope": "Synthetic Wiki/DTS corpus",
                "reason": "Synthetic actual-query declaration", "executed": True, "checked_at": "2026-11-06T10:00:00+08:00"}]}

    def start_bare_dts(self):
        book = Workbook()
        sheet = book.active
        sheet.title = "合成原始模式库"
        sheet.append(["故障模式编号", "模式名称", "故障原因", "算子", "案例链接"])
        sheet.append(["SYN-ORIGINAL-7", "尾块寻址异常", "尾块地址步长在65维时错误", "SyntheticFoo", "DTS2099010100001"])
        book.save(self.modes)
        with patch("faultaudit.trigger_workflow.load_taxonomy", return_value=fixtures.synthetic_taxonomy()):
            cfg = trigger_workflow.start_init(self.store, self.modes, self.taxonomy, self.work, executor="codex")
        self.run = cfg["run_id"]
        return cfg

    def lookup_task(self):
        self.start_bare_dts()
        first = self.next()
        self.assertEqual([task["kind"] for task in first["tasks"]], ["wiki_check"])
        self.submit(first["tasks"][0], self.search_response(first["tasks"][0]))
        second = self.next()
        self.assertEqual([task["kind"] for task in second["tasks"]], ["search"])
        task = second["tasks"][0]
        self.assertEqual(self.request(task)["payload"]["source_lookup"]["identifier"], "DTS2099010100001")
        return task

    def test_fetch_summary_two_issue_classification_dispatches_once_and_never_incident_tasks(self):
        self.start()
        initial = self.next()
        self.assertEqual([task["kind"] for task in initial["tasks"]], ["fetch"])
        fetch = initial["tasks"][0]
        request = self.request(fetch)
        self.assertTrue(request["execution_context"]["new_session_required"])
        self.assertEqual(request["execution_context"]["history"], "THIS_TASK_ONLY")
        self.submit(fetch, {"request_hash": request["request_hash"], "outcome": "CAPTURED",
                            "packages": [self.package(request["payload"]["url"])]})
        summarize = self.next()
        self.assertEqual([task["kind"] for task in summarize["tasks"]], ["model"])
        self.submit(summarize["tasks"][0], self.summary_envelope(summarize["tasks"][0]))
        classify = self.next()
        self.assertEqual([task["kind"] for task in classify["tasks"]], ["trigger_classify", "trigger_classify"])
        requests = [self.request(task) for task in classify["tasks"]]
        self.assertEqual({r["payload"]["source_issue"]["issue_index"] for r in requests}, {0, 1})
        self.assertEqual(len({r["task_id"] for r in requests}), 2)
        self.assertTrue(all(r["execution_context"]["new_session_required"] for r in requests))
        self.assertTrue(all(r["execution_context"]["history"] == "THIS_TASK_ONLY" for r in requests))
        first = classify["tasks"][0]
        self.submit(first, self.response(self.request(first), relation="MATCH"))
        remaining = self.next()["tasks"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["kind"], "trigger_classify")
        self.assertNotEqual(remaining[0]["task_id"], first["task_id"])
        self.submit(remaining[0], self.response(self.request(remaining[0]), relation="NOT_RELATED"))
        self.assertEqual(self.next()["tasks"], [])
        self.assertEqual(self.next()["tasks"], [])
        self.assertEqual(len(trigger_workflow.current_assessments(self.store, self.run)), 2)
        self.assertTrue({task["kind"] for task in self.store.tasks(self.run)} <= {"fetch", "summarize"})
        self.assertEqual(self.store.records(self.run, "judgments"), [])
        self.assertEqual(self.store.records(self.run, "mappings"), [])

    def test_bare_dts_lookup_follows_wiki_check_and_preserves_original_reference(self):
        task = self.lookup_task()
        original_refs = copy.deepcopy(self.store.records(self.run, "references"))
        url = "https://dts.example.invalid/DTSPortal/ticket/DTS2099010100001"
        self.submit(task, self.search_response(task, outcome="FOUND", packages=[
            self.package(url, title="DTS2099010100001: Synthetic actual ticket")]))
        snapshots = self.store.active_snapshots(self.run)
        self.assertEqual(len(snapshots), 1)
        pair = (self.cases()[0]["case_id"], snapshots[0]["snapshot_id"])
        self.assertEqual(trigger_workflow.source_relations(self.store, self.run)[pair], "SUPPLIED_IDENTIFIER")
        for original in original_refs:
            self.assertEqual(self.store.get(self.run, "references", original["ref_id"]), original)
        discovered = [ref for ref in self.store.records(self.run, "references") if ref.get("url") == url]
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0]["origin"], "SEARCH_DISCOVERED")
        self.assertEqual(self.store.records(self.run, "evidence_associations"), [])
        self.assertEqual(self.store.records(self.run, "judgments"), [])
        followup = self.next()
        self.assertEqual([task["kind"] for task in followup["tasks"]], ["model"])

    def test_pr_mention_cannot_resolve_original_dts_identifier(self):
        task = self.lookup_task()
        wrong = self.package("https://github.com/example.invalid/example/pull/1", title="DTS2099010100001 mentioned",
                             text="This synthetic PR mentions DTS2099010100001; it is not the ticket page.")
        with self.assertRaisesRegex(AuditError, "actual Wiki/DTS page"):
            xlsx_workflow.submit(self.store, self.run, task["task_id"], self.search_response(task, outcome="FOUND", packages=[wrong]))
        self.assertEqual(self.store.records(self.run, "snapshots"), [])
        self.assertEqual(self.store.records(self.run, "trigger_source_lookups"), [])
        right = self.package("https://dts.example.invalid/DTSPortal/ticket/DTS2099010100001")
        self.submit(task, self.search_response(task, outcome="FOUND", packages=[right]))

    def test_explicit_different_dts_url_cannot_be_overridden_by_matching_title(self):
        task = self.lookup_task()
        wrong = self.package("https://dts.example.invalid/DTSPortal/ticket/DTS2099010109999",
                             title="DTS2099010100001 mentioned in this other ticket")
        with self.assertRaisesRegex(AuditError, "identifier|ticket|Wiki/DTS"):
            xlsx_workflow.submit(self.store, self.run, task["task_id"], self.search_response(task, outcome="FOUND", packages=[wrong]))
        self.assertEqual(self.store.records(self.run, "snapshots"), [])


if __name__ == "__main__":
    unittest.main()
