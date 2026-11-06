"""Synthetic source-availability overrides; no network or production evidence."""
from __future__ import annotations

import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

from faultaudit import trigger_workflow, xlsx_workflow
from faultaudit.evidence_plan import collection_source_policy, get_search_policy
from faultaudit.store import AuditError
from tests import test_trigger_workflow as trigger_fixtures
from tests import test_xlsx_workflow as xlsx_fixtures


class WorkflowSourceOverrideTests(unittest.TestCase):
    def setUp(self):
        # Composition keeps imported TestCase classes out of unittest discovery.
        self.fixture = xlsx_fixtures.XlsxWorkflowTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.store = self.fixture.store

    def start(self, rows=None):
        config = self.fixture.start(rows)
        self.run = config["run_id"]
        return config

    def override(self, sources=None, **options):
        return xlsx_workflow.configure_collection(
            self.store, self.run, ["GITCODE", "GITHUB"] if sources is None else sources,
            wiki_policy=options.pop("wiki_policy", "NOT_SUPPORTED"),
            reason=options.pop("reason", "explicit user test"), **options)

    def assert_wiki_unavailable(self, step):
        for check in step["wiki_checks"].values():
            self.assertEqual(check["status"], "NOT_SUPPORTED")
            self.assertFalse(check["checked"])
            self.assertFalse(check["search_allowed"])
            self.assertEqual(check["required_actions"], [])
            self.assertEqual(check["query"], "")
            self.assertEqual(check["checked_at"], "")
            self.assertEqual(check["executed_by"], "")
        self.assertEqual(self.store.records(self.run, "wiki_checks"), [])

    def test_override_routes_search_instead_of_unavailable_original_links(self):
        self.start([
            ["SYN-WIKI-DTS", "Synthetic output Inf", "unverified hypothesis",
             "https://example.invalid/wiki/original", "https://dts.example.invalid/dts/123", "P1"],
            ["SYN-OTHER", "Synthetic addressing error", "unverified hypothesis",
             "https://example.invalid/wiki/other", "https://codehub.example.invalid/project/pull/1", "P2"],
        ])
        references = copy.deepcopy(self.store.records(self.run, "references"))
        policy = self.override()
        config = xlsx_workflow.config(self.store, self.run)
        self.assertEqual(config["collection_sources"], ["GITCODE", "GITHUB"])
        self.assertEqual(config["collection_policy_reason"], "explicit user test")
        self.assertEqual(config["wiki_policy"], "NOT_SUPPORTED")
        self.assertEqual(policy["reason"], config["collection_policy_reason"])
        self.assertTrue(policy["explicit_override"])
        self.assertEqual(policy["policy_hash"], collection_source_policy(self.store, self.run)["policy_hash"])

        first = xlsx_workflow.next_tasks(self.store, self.run)
        self.assert_wiki_unavailable(first)
        self.assertFalse(any(task["kind"] in {"wiki_check", "fetch"} for task in first["tasks"]))
        searches = [task for task in first["tasks"] if task["kind"] == "search"]
        self.assertEqual(len(searches), 2)
        for task in searches:
            request = self.fixture.load_request(task)
            self.assertEqual(request["collection_policy_hash"], policy["policy_hash"])
            self.assertEqual(request["payload"]["collection_source_policy"],
                             collection_source_policy(self.store, self.run))
            self.assertNotIn("source_lookup", request["payload"])
            self.assertEqual(request["payload"]["search_policy"]["required_sources"], [])
            self.assertEqual(request["payload"]["search_policy"]["required_any_sources"], ["GITCODE", "GITHUB"])
        self.assertEqual(self.store.records(self.run, "references"), references)
        policy_events = {kind: self.store.events(self.run, kind) for kind in
                         ("collection_source_policy_changed", "search_policy_registered")}
        requests = self.store.records(self.run, "workflow_requests")
        second = xlsx_workflow.next_tasks(self.store, self.run)
        self.assertEqual(second, first)
        for kind, events in policy_events.items():
            self.assertEqual(self.store.events(self.run, kind), events)
        self.assertEqual(self.store.records(self.run, "workflow_requests"), requests)

    def test_enabled_github_link_remains_fetchable_with_gitcode_search_scope(self):
        github = "https://github.com/example/synthetic/pull/1"
        self.start([["SYN-PUBLIC", "Synthetic fault", "unknown",
                     "https://example.invalid/wiki/original", github, "P1"]])
        self.override()
        step = xlsx_workflow.next_tasks(self.store, self.run)
        self.assert_wiki_unavailable(step)
        fetches = [self.fixture.load_request(task)["payload"]["url"]
                   for task in step["tasks"] if task["kind"] == "fetch"]
        self.assertEqual(fetches, [github])
        self.assertFalse(any(task["kind"] == "wiki_check" for task in step["tasks"]))
        self.assertEqual(xlsx_workflow.next_tasks(self.store, self.run), step)

    def test_pending_request_becomes_stale_without_deleting_original_request(self):
        self.start()
        old_task = xlsx_workflow.next_tasks(self.store, self.run)["tasks"][0]
        old_request = copy.deepcopy(self.store.get(self.run, "workflow_requests", old_task["task_id"]))
        old_bytes = Path(old_task["request"]).read_bytes()
        response = self.fixture.response(old_task)
        self.override()
        with self.assertRaisesRegex(AuditError, "source availability changed"):
            xlsx_workflow.submit(self.store, self.run, old_task["task_id"], response)
        self.assertEqual(self.store.get(self.run, "workflow_requests", old_task["task_id"]), old_request)
        self.assertEqual(Path(old_task["request"]).read_bytes(), old_bytes)
        self.assertEqual(self.store.records(self.run, "workflow_attempts"), [])
        self.assertEqual(self.store.records(self.run, "snapshots"), [])
        new_tasks = xlsx_workflow.next_tasks(self.store, self.run)["tasks"]
        self.assertNotIn(old_task["task_id"], {task["task_id"] for task in new_tasks})

    def test_policy_change_preserves_previously_accepted_result_and_capture(self):
        self.start()
        old_task = xlsx_workflow.next_tasks(self.store, self.run)["tasks"][0]
        response = self.fixture.response(old_task)
        xlsx_workflow.submit(self.store, self.run, old_task["task_id"], response)
        history = {kind: copy.deepcopy(self.store.records(self.run, kind)) for kind in
                   ("workflow_requests", "workflow_results", "workflow_attempts", "snapshots")}
        self.override()
        with self.assertRaisesRegex(AuditError, "source availability changed"):
            xlsx_workflow.submit(self.store, self.run, old_task["task_id"], response)
        for kind, records in history.items():
            self.assertEqual(self.store.records(self.run, kind), records)
        step = xlsx_workflow.next_tasks(self.store, self.run)
        self.assert_wiki_unavailable(step)
        self.assertFalse(any(task["kind"] == "fetch" for task in step["tasks"]))

    def test_default_configuration_still_reads_original_wiki_first(self):
        self.start([["SYN-DEFAULT", "Synthetic fault", "unknown",
                     "https://example.invalid/wiki/original", "https://github.com/example/synthetic/pull/1", "P1"]])
        policy = collection_source_policy(self.store, self.run)
        self.assertFalse(policy["explicit_override"])
        self.assertEqual(policy["wiki_policy"], "REQUIRED")
        first = xlsx_workflow.next_tasks(self.store, self.run)
        self.assertEqual(first["tasks"][0]["kind"], "fetch")
        self.assertEqual(self.fixture.load_request(first["tasks"][0])["payload"]["url"],
                         "https://example.invalid/wiki/original")
        self.assertEqual({check["status"] for check in first["wiki_checks"].values()}, {"FETCH_REQUIRED"})
        self.assertEqual(xlsx_workflow.next_tasks(self.store, self.run), first)

    def test_invalid_combinations_and_missing_reason_leave_configuration_unchanged(self):
        self.start()
        before = copy.deepcopy(xlsx_workflow.config(self.store, self.run))
        events = self.store.events(self.run)
        policies = self.store.records(self.run, "search_policies")
        invalid = [
            ([], "NOT_SUPPORTED", "explicit user test"),
            (["GITCODE", "GITCODE"], "NOT_SUPPORTED", "explicit user test"),
            (["UNKNOWN"], "NOT_SUPPORTED", "explicit user test"),
            (["gitcode"], "NOT_SUPPORTED", "explicit user test"),
            (["WIKI", "GITCODE"], "NOT_SUPPORTED", "explicit user test"),
            (["GITCODE"], "REQUIRED", "explicit user test"),
            (["GITCODE"], "UNKNOWN", "explicit user test"),
            (["GITCODE"], "NOT_SUPPORTED", ""),
            (["GITCODE"], "NOT_SUPPORTED", "   "),
        ]
        for sources, wiki_policy, reason in invalid:
            with self.subTest(sources=sources, wiki_policy=wiki_policy, reason=reason):
                with self.assertRaises(AuditError):
                    xlsx_workflow.configure_collection(self.store, self.run, sources,
                                                       wiki_policy=wiki_policy, reason=reason)
        with self.assertRaises(TypeError):
            xlsx_workflow.configure_collection(self.store, self.run, ["GITCODE"], wiki_policy="NOT_SUPPORTED")
        self.assertEqual(xlsx_workflow.config(self.store, self.run), before)
        self.assertEqual(self.store.events(self.run), events)
        self.assertEqual(self.store.records(self.run, "search_policies"), policies)

    def test_setting_same_sources_is_idempotent_even_when_order_changes(self):
        self.start()
        first = self.override()
        events = self.store.events(self.run)
        policies = self.store.records(self.run, "search_policies")
        self.assertEqual(len(self.store.events(self.run, "collection_source_policy_changed")), 1)
        second = self.override(["GITHUB", "GITCODE"])
        self.assertEqual(second, first)
        self.assertEqual(self.store.events(self.run), events)
        self.assertEqual(self.store.records(self.run, "search_policies"), policies)
        for case in self.store.records(self.run, "cases"):
            self.assertEqual(get_search_policy(self.store, self.run, case["case_id"])["policy"]["required_any_sources"],
                             ["GITCODE", "GITHUB"])

    def test_external_search_no_match_does_not_fabricate_a_wiki_search(self):
        self.start()
        self.override()
        first = xlsx_workflow.next_tasks(self.store, self.run)
        search = next(task for task in first["tasks"] if task["kind"] == "search")
        xlsx_workflow.submit(self.store, self.run, search["task_id"], self.fixture.response(search))
        second = xlsx_workflow.next_tasks(self.store, self.run)
        self.assert_wiki_unavailable(second)
        self.assertFalse(any(task["kind"] in {"wiki_check", "search", "fetch"} for task in second["tasks"]))
        self.assertEqual(xlsx_workflow.next_tasks(self.store, self.run), second)

    def test_trigger_init_keeps_not_supported_gap_and_skips_wiki_dts_identifiers(self):
        trigger = trigger_fixtures.TriggerWorkflowTests(methodName="runTest")
        trigger.setUp()
        self.addCleanup(trigger.tearDown)
        book = Workbook()
        book.active.append(["故障模式编号", "模式名称", "故障原因", "算子", "案例链接", "DTS", "wiki"])
        book.active.append(["SYN-ORIGINAL-7", "尾块寻址异常", "尾块地址步长在65维时错误", "SyntheticFoo",
                            "https://example.invalid/wiki/mode-0", "DTS202611060001", "WIKI202611060001"])
        book.save(trigger.modes)
        with patch("faultaudit.trigger_workflow.load_taxonomy", return_value=trigger_fixtures.synthetic_taxonomy()):
            config = trigger_workflow.start_init(trigger.store, trigger.modes, trigger.taxonomy,
                                                 trigger.work, executor="codex")
        trigger.run = config["run_id"]
        xlsx_workflow.configure_collection(trigger.store, trigger.run, ["GITCODE", "GITHUB"],
                                           wiki_policy="NOT_SUPPORTED", reason="explicit user test")
        original_refs = trigger.store.records(trigger.run, "references")
        self.assertTrue(any("DTS202611060001" in ref["raw_text"] for ref in original_refs))
        first = xlsx_workflow.next_tasks(trigger.store, trigger.run)
        self.assertFalse(any(task["kind"] in {"fetch", "wiki_check"} for task in first["tasks"]))
        searches = [trigger.store.get(trigger.run, "workflow_requests", task["task_id"])
                    for task in first["tasks"] if task["kind"] == "search"]
        self.assertTrue(searches)
        self.assertTrue(all("source_lookup" not in request["payload"] for request in searches))
        self.assertTrue(all(request["payload"]["collection_source_policy"]["collection_sources"] == ["GITCODE", "GITHUB"]
                            for request in searches))
        self.assertEqual(list(trigger_workflow.source_lookups(trigger.store, trigger.run)), [])
        for check in first["wiki_checks"].values():
            self.assertEqual(check["status"], "NOT_SUPPORTED")
            self.assertFalse(check["checked"])
            self.assertEqual(check["query"], "")
        status = trigger_workflow.status(trigger.store, trigger.run)
        kinds = {gap["kind"] for gap in status["gaps"]}
        self.assertIn("WIKI_NOT_SUPPORTED", kinds)
        self.assertIn("SOURCE_NOT_AVAILABLE_USER_POLICY", kinds)
        self.assertNotIn("WIKI_NO_MATCH", kinds)
        self.assertEqual(trigger.store.records(trigger.run, "wiki_checks"), [])
        self.assertEqual(trigger.store.records(trigger.run, "trigger_source_lookups"), [])
        policy_events = {kind: trigger.store.events(trigger.run, kind) for kind in
                         ("collection_source_policy_changed", "search_policy_registered")}
        self.assertEqual(xlsx_workflow.next_tasks(trigger.store, trigger.run), first)
        for kind, events in policy_events.items():
            self.assertEqual(trigger.store.events(trigger.run, kind), events)
        self.assertEqual(trigger_workflow.status(trigger.store, trigger.run), status)
        self.assertEqual(trigger.store.records(trigger.run, "references"), original_refs)


if __name__ == "__main__":
    unittest.main()
