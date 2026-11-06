"""Synthetic resource aliases are reused without merging incident records."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from faultaudit.evidence_plan import build_evidence_plan, register_evidence_association
from faultaudit.importers import import_cases
from faultaudit.pipeline import execute, import_into
from faultaudit.model import MockJudge
from faultaudit.resource_identity import resource_key, resource_url, same_resource, snapshot_index
from faultaudit.store import Store


PR = "https://github.com/synthetic-owner/fault-fixture/pull/41"


class ResourceIdentityTests(unittest.TestCase):
    def test_github_comment_and_tracking_aliases_share_one_resource(self):
        self.assertEqual(resource_key(PR), resource_key(PR + "?utm_source=mail#discussion_r123"))
        self.assertEqual(resource_url(PR + "/files#diff-abc"), PR)
        self.assertEqual(resource_key(PR.upper().replace("/PULL/", "/pull/")), PR)

    def test_known_repository_names_on_github_are_case_insensitive(self):
        self.assertEqual(resource_key("https://github.com/Synthetic-Owner/Fault-Fixture/pull/41"), PR)

    def test_gitcode_and_gitee_comment_navigation_is_shared(self):
        for url in ("https://gitcode.com/synthetic-owner/fault-fixture/pull/41",
                    "https://gitee.com/synthetic-owner/fault-fixture/pulls/41"):
            self.assertTrue(same_resource(url, url + "?utm_medium=mail#note_71"))

    def test_meaningful_version_and_ref_queries_are_not_removed(self):
        self.assertFalse(same_resource(PR, PR + "?ref=revision-a"))
        self.assertFalse(same_resource(PR + "?ref=revision-a", PR + "?ref=revision-b"))
        self.assertFalse(same_resource(PR + "?version=1", PR + "?version=2"))
        self.assertTrue(same_resource(PR + "?version=1&utm_source=x", PR + "?version=1"))

    def test_unknown_queries_and_ordered_repeated_values_are_preserved(self):
        self.assertFalse(same_resource(PR + "?view=one", PR + "?view=two"))
        self.assertFalse(same_resource(PR + "?ref=a&ref=b", PR + "?ref=b&ref=a"))

    def test_different_issue_number_or_repository_is_not_a_duplicate(self):
        self.assertFalse(same_resource(PR, PR.replace("41", "42")))
        self.assertFalse(same_resource(PR, PR.replace("fault-fixture", "other-fixture")))
        self.assertFalse(same_resource(PR, PR.replace("/pull/", "/issues/")))

    def test_unknown_url_and_blob_revision_remain_conservative(self):
        unknown = "https://example.invalid/page?a=1#part-a"
        self.assertEqual(resource_url(unknown), unknown)
        self.assertFalse(same_resource(unknown, unknown.replace("part-a", "part-b")))
        a = "https://github.com/synthetic-owner/fault-fixture/blob/revision-a/op.cpp"
        self.assertFalse(same_resource(a, a.replace("revision-a", "revision-b")))
        self.assertFalse(same_resource(PR, PR + ".diff"))

    def test_wiki_and_dts_locators_reuse_resource_but_not_other_spaces(self):
        wiki = "https://wiki.huawei.com/domains/1/wiki/2/WIKI2099010100000000"
        self.assertTrue(same_resource(wiki, wiki + "?utm_source=mail#section-x"))
        self.assertFalse(same_resource(wiki, wiki.replace("domains/1", "domains/2")))
        dts = "https://dts-synthetic.example.invalid/DTSPortal/ticket/DTS209901010001"
        self.assertTrue(same_resource(dts, dts + "#comment-2"))
        self.assertFalse(same_resource(dts, dts.replace("0001", "0002")))

    def test_invalid_or_credential_url_is_not_an_alias(self):
        for value in ("relative", "file:///tmp/source", "https://user:password@github.com/org/repo/pull/1"):
            with self.assertRaises(ValueError):
                resource_url(value)
            self.assertFalse(same_resource(PR, value))

    def test_latest_failure_is_not_hidden_by_older_readable_alias(self):
        old = {"snapshot_id": "OLD", "url": PR, "retrieved_at": "2026-01-01T10:00:00+08:00", "status": "COMPLETE"}
        new = {"snapshot_id": "NEW", "url": PR + "#note-1", "retrieved_at": "2026-01-01T03:00:00Z", "status": "AUTH_REQUIRED"}
        self.assertEqual(snapshot_index([new, old])[resource_key(PR)]["snapshot_id"], "NEW")


class ResourcePlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="resource-reuse-", dir=Path(__file__).resolve().parent)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "state")
        self.run = self.store.create_run({"is_synthetic": True})

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def source(self, rows):
        path = self.root / "cases.json"
        path.write_text(json.dumps(rows), encoding="utf-8")
        value = import_cases(path, "LEGACY_TABLE")
        import_into(self.store, self.run, value)
        return value["cases"]

    def snapshot(self):
        return self.store.ingest_evidence(self.run, {"url": PR, "title": "Synthetic resource",
            "text": "Synthetic precision failure in cache operation during restore; independent fixture only.",
            "status": "COMPLETE", "artifact_type": "PR", "components": {
                "body": "COMPLETE", "diff": "COMPLETE", "file_list": "COMPLETE"},
            "expected_file_count": 0, "captured_file_count": 0, "is_synthetic": True})

    def test_same_case_main_and_comment_urls_keep_two_sources_one_work(self):
        cases = self.source([{"统一ID": "SYNTHETIC-1", "问题描述": "Synthetic precision failure", "PR": PR,
                              "github": PR + "?utm_source=mail#discussion_r123"}])
        before = build_evidence_plan(self.store, self.run)
        self.assertEqual(len(before["fetch_work_items"]), 1)
        self.assertEqual(len(before["fetch_work_items"][0]["ref_ids"]), 2)
        self.assertEqual(len(before["fetch_work_items"][0]["original_urls"]), 2)
        self.snapshot()
        after = build_evidence_plan(self.store, self.run)
        self.assertEqual(len(after["work_items"]), 1)
        self.assertEqual(len(after["work_items"][0]["ref_ids"]), 2)
        self.assertFalse(after["fetch_work_items"][0]["required"])
        self.assertEqual(len(self.store.records(self.run, "references")), 2)
        self.assertEqual(len(cases), 1)

    def test_two_cases_share_capture_and_summary_without_event_merge(self):
        cases = self.source([{"统一ID": "SYNTHETIC-1", "问题描述": "Synthetic precision failure", "PR": PR},
                             {"统一ID": "SYNTHETIC-2", "问题描述": "Synthetic precision failure", "PR": PR + "#issuecomment-7"}])
        self.snapshot()
        plan = build_evidence_plan(self.store, self.run)
        self.assertEqual(len(plan["fetch_work_items"]), 1)
        self.assertEqual(len(plan["work_items"]), 2)
        self.assertEqual(len(self.store.records(self.run, "cases")), 2)
        self.assertEqual(self.store.records(self.run, "event_groups"), [])
        execute(self.store, self.run, MockJudge(), mode="mock", model_id="synthetic")
        self.assertEqual(len(self.store.records(self.run, "summaries")), 1)
        before = [(t["task_id"], t["status"]) for t in self.store.tasks(self.run)]
        execute(self.store, self.run, MockJudge(), mode="mock", model_id="synthetic")
        self.assertEqual([(t["task_id"], t["status"]) for t in self.store.tasks(self.run)], before)
        self.assertEqual(len(self.store.records(self.run, "summaries")), 1)

    def test_aliases_do_not_collapse_two_explicit_subproblem_scopes(self):
        case = self.source([{"统一ID": "SYNTHETIC-1", "问题描述": "Synthetic precision failure", "PR": PR,
                             "github": PR + "#discussion_r123"}])[0]
        snapshot = self.snapshot()
        refs = self.store.records(self.run, "references")
        for index, ref in enumerate(refs):
            register_evidence_association(self.store, self.run, case_id=case["case_id"], ref_id=ref["ref_id"],
                snapshot_id=snapshot["snapshot_id"], applicable_issue_ids=["SYNTHETIC-ISSUE-" + str(index)],
                user_confirmed=True, confirmed_by="synthetic-user", reason="Distinct explicitly selected subproblem")
        plan = build_evidence_plan(self.store, self.run)
        self.assertEqual(len(plan["fetch_work_items"]), 1)
        self.assertEqual(len(plan["work_items"]), 2)
        self.assertEqual(len({tuple(w["issue_scope"]["applicable_issue_ids"]) for w in plan["work_items"]}), 2)


if __name__ == "__main__":
    unittest.main()
