"""Explicit run source availability preserves the original reference ledger."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook

from faultaudit import trigger_workflow as workflow
from faultaudit.bridge import policy_fingerprint
from faultaudit.evidence_plan import build_evidence_plan, collection_source_policy, register_search_policy
from faultaudit.store import AuditError, Store, digest
from faultaudit.wiki_checks import record_wiki_check, wiki_plan
from tests.test_trigger_assessment import fixture
from tests.test_trigger_workflow import synthetic_taxonomy


class CollectionSourcePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="collection-policy-", dir=Path(__file__).parent)
        self.directory = Path(self.temp.name)
        self.store = Store(self.directory / "state")
        modes = self.directory / "synthetic_original_modes.xlsx"
        book = Workbook()
        sheet = book.active
        sheet.title = "Synthetic original modes"
        sheet.append(["故障模式编号", "模式名称", "故障原因", "算子", "wiki", "DTS"])
        sheet.append(["SYN-ORIGINAL-7", "尾块寻址异常", "尾块地址步长在65维时错误", "SyntheticFoo",
                      "https://example.invalid/wiki/original", "DTS2099010100001"])
        book.save(modes)
        taxonomy = self.directory / "synthetic_taxonomy.md"
        taxonomy.write_text("Synthetic taxonomy fixture", encoding="utf-8")
        with patch("faultaudit.trigger_workflow.load_taxonomy", return_value=synthetic_taxonomy()):
            cfg = workflow.start_init(self.store, modes, taxonomy, self.directory / "work", executor="codex")
        self.run = cfg["run_id"]
        self.case = self.store.records(self.run, "cases")[0]
        self.original_refs = copy.deepcopy(self.store.records(self.run, "references"))

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def override(self, reason="用户要求：当前不支持wiki，直接查gitcode相关"):
        cfg = self.store.get(self.run, "xlsx_workflow", "config")
        cfg.update(collection_sources=["GITCODE"], wiki_policy="NOT_SUPPORTED", collection_policy_reason=reason)
        self.store.put(self.run, "xlsx_workflow", "config", cfg, mutable=True)
        register_search_policy(self.store, self.run, {"required_any_sources": ["GITCODE"]})

    def plan(self):
        return build_evidence_plan(self.store, self.run)

    def wiki(self):
        return wiki_plan(self.store, self.run, self.case)

    def capture(self, url="https://gitcode.com/example.invalid/kernel/issues/1", *, status="COMPLETE"):
        text = "SyntheticFoo在维长65时尾块地址步长错误。" if status == "COMPLETE" else ""
        return self.store.ingest_evidence(self.run, {"url": url, "title": "Synthetic mode evidence", "text": text,
            "status": status, "components": {"body": "COMPLETE" if text else "MISSING"}, "is_synthetic": True,
            "case_ids": [self.case["case_id"]], "record_discovery": True, "origin": "SEARCH_DISCOVERED",
            "capture_observation": {"page_kind": "BODY" if text else "LOGIN", "requested_url": url, "final_url": url,
                "title": "Synthetic mode evidence", "body_locator": "synthetic article body", "body_quotes": [text] if text else [],
                "observed_by": "synthetic-agent", "observed_at": "2026-11-06T10:00:00+08:00",
                "tool_observation": "Synthetic fixture; no website visited"}})

    def summarize(self, snapshot):
        segment = snapshot["segments"][0]
        ref = {"segment_id": segment["segment_id"], "quote": segment["text"]}
        task = self.store.task(self.run, "summarize", snapshot["snapshot_id"], {"revision": 1})
        value = {"task_id": task["task_id"], "snapshot_id": snapshot["snapshot_id"],
            "issues": [{"label": "Synthetic tail stride", "facts": [
                {"field": "root_cause", "value": "尾块地址步长在65维时错误", "evidence": [ref]}]}],
            "unknown_fields": [], "model_mode": "codex", "model_id": "synthetic-only",
            "segments_processed": len(snapshot["segments"]), "policy_hash": policy_fingerprint()}
        self.store.put(self.run, "summaries", task["task_id"], value)
        self.store.task_status(self.run, task["task_id"], "SUCCEEDED")
        return value

    def match(self, payload):
        request = {"task_id": "synthetic-classification-" + digest(payload)[:24],
                   "request_hash": digest(payload), "payload": payload}
        _, response = fixture()
        response.update(request_hash=request["request_hash"], case_id=self.case["case_id"], source_relation="MATCH")
        response["rows"] = [{**copy.deepcopy(response["rows"][0]), "trigger_id": item["id"]}
                            for item in payload["taxonomy"]["items"]]
        response["source_alignment"] = [{"dimension": "mechanism", "relation": "MATCH",
            "reason": "Synthetic comparison of the original mode mechanism with the captured GitCode issue.",
            "evidence": payload["source_issue"]["facts"][0]["evidence"],
            "source_cells": [{"field": "故障原因", "cell": self.case["cell_locations"]["故障原因"],
                              "quote": self.case["raw"]["故障原因"]}]}]
        from tests.condition_fixtures import condition_attempt
        return workflow.accept_assessment(self.store, self.run, request, condition_attempt(payload, response))

    def test_default_supplied_reference_and_wiki_priority_are_unchanged(self):
        plan = self.plan()
        row = plan["cases"][0]
        self.assertEqual(set(row["selected_ref_ids"]), {ref["ref_id"] for ref in self.original_refs})
        self.assertFalse(row["search_control"]["search_allowed"])
        self.assertEqual(self.wiki()["status"], "FETCH_REQUIRED")
        self.assertEqual([action["action"] for action in self.wiki()["required_actions"]], ["FETCH_WIKI"])
        self.assertFalse(collection_source_policy(self.store, self.run)["explicit_override"])
        self.assertNotIn("collection_policy_hash", row)

    def test_gitcode_only_keeps_original_wiki_and_bare_dts_unselected_and_searchable(self):
        self.override()
        changes = self.store.conn.total_changes
        plan = self.plan()
        row = plan["cases"][0]
        self.assertEqual(self.store.conn.total_changes, changes)
        self.assertEqual(self.store.records(self.run, "references"), self.original_refs)
        self.assertEqual(row["selected_ref_ids"], [])
        self.assertEqual(plan["work_items"], [])
        self.assertEqual(plan["fetch_work_items"], [])
        self.assertTrue(row["search_control"]["search_allowed"])
        self.assertEqual([a["action"] for a in row["required_actions"]], ["SEARCH_SUPPORT"])
        self.assertEqual(row["required_actions"][0]["target_sources"], ["GITCODE"])
        unavailable = row["unavailable_references"]
        self.assertEqual({item["resource_kind"] for item in unavailable}, {"WIKI", "DTS"})
        self.assertEqual({item["ref_id"] for item in unavailable}, {ref["ref_id"] for ref in self.original_refs})
        self.assertTrue(all(item["status"] == "NOT_SUPPORTED" and item["reason"] for item in unavailable))
        self.assertTrue(all(item["source_grade"] == "LEGACY_TABLE_LINKED" for item in unavailable))

    def test_wiki_not_supported_is_unchecked_even_with_a_readable_original(self):
        self.capture("https://example.invalid/wiki/original")
        self.assertEqual(self.wiki()["status"], "FOUND")
        self.override()
        wiki = self.wiki()
        self.assertEqual(wiki["status"], "NOT_SUPPORTED")
        self.assertFalse(wiki["checked"])
        self.assertFalse(wiki["search_allowed"])
        self.assertEqual(wiki["required_actions"], [])
        self.assertIn("wiki_policy=NOT_SUPPORTED", wiki["reason"])
        self.assertIn("collection_sources=GITCODE", wiki["reason"])
        self.assertIn("当前不支持wiki", wiki["reason"])
        self.assertTrue(wiki["wiki_ref_ids"])
        self.assertTrue(wiki["unavailable_references"])
        self.assertEqual(self.store.records(self.run, "wiki_checks"), [])

    def test_current_gitcode_summary_is_pending_until_actual_mode_match_then_search_stops(self):
        self.override()
        snapshot = self.capture()
        before = self.plan()["cases"][0]
        self.assertFalse(before["search_control"]["satisfied"])
        self.assertEqual(before["search_control"]["status"], "CANDIDATE_PENDING")
        self.summarize(snapshot)
        self.assertFalse(self.plan()["cases"][0]["search_control"]["satisfied"])
        payloads = list(workflow.classification_payloads(self.store, self.run))
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["source_issue"]["snapshot_id"], snapshot["snapshot_id"])
        self.match(payloads[0])
        after = self.plan()["cases"][0]
        self.assertTrue(after["search_control"]["satisfied"])
        self.assertFalse(after["search_control"]["search_allowed"])
        self.assertEqual(after["search_control"]["usable_sources"], ["GITCODE"])
        self.assertEqual(after["selected_snapshot_ids"], [snapshot["snapshot_id"]])
        self.assertFalse(after["user_confirmed"])
        self.assertEqual(self.wiki()["status"], "NOT_SUPPORTED")
        for kind in ("judgments", "reviews", "evidence_associations", "event_groups"):
            self.assertEqual(self.store.records(self.run, kind), [])

    def test_policy_changes_invalidate_routing_and_wiki_checks_without_rewriting_history(self):
        self.capture("https://example.invalid/wiki/original", status="AUTH_REQUIRED")
        record = record_wiki_check(self.store, self.run, self.case["case_id"], outcome="BLOCKED", executed=True,
            query="synthetic tail stride", scope="example.invalid Wiki", checked_at="2026-11-06T10:00:00+08:00",
            executed_by="synthetic-agent", reason="Synthetic authentication required")
        old_input = self.wiki()["input_hash"]
        self.override()
        first_plan, first_wiki = self.plan()["cases"][0], self.wiki()
        self.assertNotEqual(first_wiki["input_hash"], old_input)
        self.assertIsNone(first_wiki["check_id"])
        self.override("用户明确要求仅查GitCode；本轮Wiki不可用")
        second_plan, second_wiki = self.plan()["cases"][0], self.wiki()
        self.assertNotEqual(first_plan["routing_hash"], second_plan["routing_hash"])
        self.assertNotEqual(first_wiki["input_hash"], second_wiki["input_hash"])
        self.assertNotEqual(first_wiki["task_id"], second_wiki["task_id"])
        self.assertEqual(self.store.get(self.run, "wiki_checks", record["check_id"]), record)
        with self.assertRaisesRegex(AuditError, "NOT_SUPPORTED"):
            record_wiki_check(self.store, self.run, self.case["case_id"], outcome="NO_MATCH")

    def test_source_override_requires_a_reason(self):
        cfg = self.store.get(self.run, "xlsx_workflow", "config")
        cfg.update(collection_sources=["GITCODE"], wiki_policy="NOT_SUPPORTED")
        self.store.put(self.run, "xlsx_workflow", "config", cfg, mutable=True)
        with self.assertRaisesRegex(AuditError, "collection_policy_reason"):
            collection_source_policy(self.store, self.run)


if __name__ == "__main__":
    unittest.main()
