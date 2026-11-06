"""Synthetic, read-only root-cause investigation handoff tests."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from faultaudit.bridge import policy_fingerprint
from faultaudit.evidence_plan import register_evidence_association
from faultaudit.importers import import_cases, is_empty_link_value
from faultaudit.investigation import investigation_plan
from faultaudit.pipeline import evidence_plan, gate_judgment, import_into, work_context
from faultaudit.store import Store, digest


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="investigation-", dir=Path(__file__).parent)
        self.directory = Path(self.temp.name)
        self.store = Store(self.directory / "state")
        self.run = self.store.create_run({"is_synthetic": True})

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def source(self, rows=None):
        path = self.directory / "cases.json"
        path.write_text(json.dumps(rows or [{"统一ID": "SYN-1", "问题描述": "garbled after restore",
            "根因": "buffer reused before completion", "wiki": "https://example.invalid/wiki/one"}]), encoding="utf-8")
        result = import_cases(path, "ORIGINAL_WEEKLY")
        import_into(self.store, self.run, result)
        return result["cases"]

    def snapshot(self, text=None, status="PARTIAL", url="https://example.invalid/wiki/one"):
        text = text or "Issue A: garbled after restore; buffer reused before completion.\nIssue B: other event; offset calculation error."
        return self.store.ingest_evidence(self.run, {"url": url, "text": text, "title": "Synthetic fixture",
            "status": status, "components": {"body": "PARTIAL" if status == "PARTIAL" else "COMPLETE"}, "is_synthetic": True})

    def finish(self, case, snapshot, *, selected="Issue A", root_claim="PARTIAL"):
        segment = snapshot["segments"][0]
        a, b = snapshot["text"].split("\n", 1)
        ref = lambda quote: {"segment_id": segment["segment_id"], "quote": quote}
        summary_task = self.store.task(self.run, "summarize", snapshot["snapshot_id"], {"synthetic": True})
        summary = {"snapshot_id": snapshot["snapshot_id"], "issues": [
            {"label": "Issue A", "facts": [{"field": "mechanism", "value": "buffer reused before completion", "evidence": [ref(a)]}]},
            {"label": "Issue B", "facts": [{"field": "mechanism", "value": "offset calculation error", "evidence": [ref(b)]}]}],
            "unknown_fields": [], "model_mode": "opencode", "model_id": "synthetic-reported-model",
            "task_id": summary_task["task_id"], "segments_processed": len(snapshot["segments"]),
            "blocks_processed": 1, "policy_hash": policy_fingerprint()}
        self.store.put(self.run, "summaries", summary_task["task_id"], summary)
        self.store.task_status(self.run, summary_task["task_id"], "SUCCEEDED")
        plan = evidence_plan(self.store, self.run)
        work = next(work for work in plan["work_items"] if (work["issue_scope"].get("applicable_issue_ids") or [selected]) == [selected])
        context = work_context(self.store, self.run, work["work_id"], plan)
        scope_text = a if selected == "Issue A" else b
        facts = [{"category": category, "relation": "UNKNOWN", "reason": "Not reported"} for category in ("NUMBER", "TERM")]
        facts += [{"category": "SCENARIO", "source_field": "问题描述", "source_quote": case["raw"]["问题描述"],
            "source_cell": case["cell_locations"]["问题描述"], "evidence": [ref(scope_text)], "relation": "UNKNOWN", "reason": "Captured scoped context"},
            {"category": "TECHNICAL_CONCLUSION", "source_field": "根因", "source_quote": case["raw"]["根因"],
             "source_cell": case["cell_locations"]["根因"], "evidence": [ref(scope_text)], "relation": "UNKNOWN", "reason": "Mechanism in selected issue"}]
        value = {"case_id": case["case_id"], "snapshot_id": snapshot["snapshot_id"], "case_attribution": "PARTIAL",
            "event_relation": "UNDETERMINED", "pattern_relation": "POSSIBLY_RELATED", "support_level": "PARTIAL",
            "claim_support": {"root_cause": root_claim}, "evidence": [ref(scope_text)], "short_reason": "Synthetic scoped comparison",
            "fact_comparisons": facts, "applicable_issue": {"label": selected, "evidence": [ref(scope_text)], "selection_reason": "Applicable synthetic issue"},
            "self_check": {"attempt": 1, "numeric_meaning_checked": True, "citations_checked": True,
                "counterevidence_checked": True, "issue_scope_checked": True, "event_vs_technical_checked": True, "passed": True, "issues": []},
            "model_mode": "opencode", "model_id": "synthetic-reported-model"}
        judgment = gate_judgment(case, snapshot, value, context=context)
        task = self.store.task(self.run, "compare", work["work_id"], {"synthetic": True})
        judgment.update(judgment_id=task["task_id"], task_id=task["task_id"], work_id=work["work_id"],
            policy_hash=policy_fingerprint(), case_hash=digest(case), summary_task_id=summary_task["task_id"],
            summary_hash=digest(summary), processing_context=context, member_case_ids=[case["case_id"]])
        self.store.put(self.run, "judgments", judgment["judgment_id"], judgment)
        self.store.task_status(self.run, task["task_id"], "SUCCEEDED")
        return summary, judgment

    def save_card_summary(self, snapshot, issues, *, mode="opencode", target_suffix=""):
        task = self.store.task(self.run, "summarize", snapshot["snapshot_id"] + target_suffix,
                               {"synthetic_card_summary": True, "mode": mode, "issues": issues})
        value = {"snapshot_id": snapshot["snapshot_id"], "issues": issues,
            "unknown_fields": [], "model_mode": mode, "model_id": "synthetic-reported-" + mode,
            "task_id": task["task_id"], "segments_processed": len(snapshot["segments"]),
            "blocks_processed": 1, "policy_hash": policy_fingerprint()}
        self.store.put(self.run, "summaries", task["task_id"], value)
        self.store.task_status(self.run, task["task_id"], "SUCCEEDED")
        return value

    def test_summary_cards_require_a_current_summary_not_imported_cause_or_title(self):
        self.source()
        self.snapshot("Only a captured symptom; no stated mechanism.")
        result = investigation_plan(self.store, self.run)
        self.assertEqual(result["resource_summary_cards"], [])
        resource = result["resources"][0]
        self.assertEqual(resource["summary_status"], "SUMMARY_REQUIRED")
        self.assertEqual(resource["resource_summary_card_ids"], [])
        self.assertEqual(resource["summary_requirements"]["fields"],
                         ["operator", "symptom", "root_cause", "trigger", "fix", "verification"])
        self.assertEqual(resource["summary_reading_scope"]["scope"], "CAPTURED_CONTENT")

    def test_summary_card_keeps_missing_fields_unknown_and_other_facts(self):
        self.source()
        snapshot = self.snapshot("example_norm emits NaN. Runtime build B123.")
        ref = {"segment_id": snapshot["segments"][0]["segment_id"], "quote": snapshot["text"]}
        self.save_card_summary(snapshot, [{"label": "Captured symptom", "facts": [
            {"field": "operator", "value": "example_norm", "evidence": [ref]},
            {"field": "symptom", "value": "emits NaN", "evidence": [ref]},
            {"field": "version", "value": "B123", "evidence": [ref]}]}])
        result = investigation_plan(self.store, self.run)
        card = result["resource_summary_cards"][0]
        for name in ("root_cause", "trigger", "fix", "verification"):
            self.assertEqual(card["fields"][name]["status"], "UNKNOWN_IN_CAPTURED_CONTENT")
            self.assertEqual(card["fields"][name]["facts"], [])
            self.assertEqual(card["fields"][name]["basis"], "NO_CITED_FACT_IN_CAPTURED_CONTENT")
        self.assertEqual(card["fields"]["operator"]["facts"][0]["value"], "example_norm")
        facts = {fact["fact_id"]: fact for fact in result["independent_technical_facts"]}
        self.assertEqual([facts[fid]["field"] for fid in card["other_fact_ids"]], ["version"])
        self.assertFalse(card["case_root_cause_confirmed"])
        self.assertEqual(card["basis"], "CITED_MODEL_SUMMARY")
        self.assertEqual(card["fields"]["verification"]["attribution"], "UNKNOWN_IN_CAPTURED_CONTENT")

    def test_summary_cards_separate_issues_and_keep_units_and_verification_attribution(self):
        self.source()
        text = "Issue A: buffer is 64 bytes; author reports a test passed.\nIssue B: reduction width is 96 elements; offset error."
        snapshot = self.snapshot(text)
        segment_id = snapshot["segments"][0]["segment_id"]
        a, b = text.split("\n")
        ref_a = {"segment_id": segment_id, "quote": a}
        ref_b = {"segment_id": segment_id, "quote": b}
        summary = self.save_card_summary(snapshot, [
            {"label": "Issue A", "facts": [
                {"field": "trigger", "value": "64 bytes", "evidence": [ref_a]},
                {"field": "verification", "value": "Author reports a test passed", "evidence": [ref_a]}]},
            {"label": "Issue B", "facts": [
                {"field": "trigger", "value": "96 elements", "evidence": [ref_b]},
                {"field": "mechanism", "value": "offset error", "evidence": [ref_b]}]}])
        result = investigation_plan(self.store, self.run)
        cards = {card["issue_label"]: card for card in result["resource_summary_cards"]}
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards["Issue A"]["fields"]["trigger"]["facts"][0]["value"], "64 bytes")
        self.assertEqual(cards["Issue B"]["fields"]["trigger"]["facts"][0]["value"], "96 elements")
        self.assertEqual(cards["Issue A"]["fields"]["root_cause"]["facts"], [])
        self.assertEqual(cards["Issue B"]["fields"]["verification"]["facts"], [])
        verification = cards["Issue A"]["fields"]["verification"]
        self.assertFalse(verification["local_execution_verified"])
        self.assertEqual(verification["basis"], "CITED_MODEL_SUMMARY")
        self.assertEqual(verification["facts"][0]["evidence"], [ref_a])
        self.assertTrue(all(card["summary_task_id"] == summary["task_id"] for card in cards.values()))
        self.assertTrue(all(not card["case_root_cause_confirmed"] for card in cards.values()))

    def test_summary_cards_do_not_merge_executors_or_duplicate_issue_labels(self):
        self.source()
        snapshot = self.snapshot("A: first source cause. B: second source cause.")
        sid = snapshot["segments"][0]["segment_id"]
        issue = lambda quote: {"label": "Repeated label", "facts": [
            {"field": "mechanism", "value": quote, "evidence": [{"segment_id": sid, "quote": quote}]}]}
        first = self.save_card_summary(snapshot, [issue("first source cause"), issue("second source cause")],
                                       target_suffix=":first-executor")
        second = self.save_card_summary(snapshot, [issue("first source cause")], mode="codex",
                                        target_suffix=":second-executor")
        cards = investigation_plan(self.store, self.run)["resource_summary_cards"]
        self.assertEqual(len(cards), 3)
        self.assertEqual(len({card["card_id"] for card in cards}), 3)
        self.assertEqual({card["summary_task_id"] for card in cards}, {first["task_id"], second["task_id"]})
        self.assertTrue(all(len(card["fields"]["root_cause"]["facts"]) == 1 for card in cards))
        self.assertEqual({card["model_mode"] for card in cards}, {"codex", "opencode"})

    def test_stale_or_incomplete_summary_cannot_create_resource_cards(self):
        case = self.source()[0]
        snapshot = self.snapshot()
        summary, _ = self.finish(case, snapshot)
        self.assertTrue(investigation_plan(self.store, self.run)["resource_summary_cards"])
        summary["segments_processed"] = 0
        self.store.put(self.run, "summaries", summary["task_id"], summary, mutable=True)
        result = investigation_plan(self.store, self.run)
        self.assertEqual(result["resource_summary_cards"], [])
        self.assertEqual(result["resources"][0]["summary_status"], "SUMMARY_REQUIRED")
        summary["segments_processed"] = len(snapshot["segments"])
        self.store.put(self.run, "summaries", summary["task_id"], summary, mutable=True)
        import faultaudit.prompts as prompts
        with patch.object(prompts, "PROMPT_VERSION", "synthetic-new-policy"):
            self.assertEqual(investigation_plan(self.store, self.run)["resource_summary_cards"], [])
        self.snapshot("New captured source replaces the old snapshot.")
        self.assertEqual(investigation_plan(self.store, self.run)["resource_summary_cards"], [])

    def test_repository_link_priority_keeps_other_cases_and_ignores_title_or_similar_hosts(self):
        cases = self.source([
            {"统一ID": "A-NO-LINK", "问题描述": "github.com is mentioned without a URL"},
            {"统一ID": "B-OTHER", "问题描述": "Another fault", "wiki": "https://notgithub.com/pull/1"},
            {"统一ID": "C-PUBLIC", "问题描述": "Public issue", "PR": "https://github.com/synthetic/repo/pull/1"},
            {"统一ID": "D-PUBLIC", "问题描述": "Public issue", "PR": "https://gitcode.com/synthetic/repo/pull/2"}])
        result = investigation_plan(self.store, self.run)
        ids = {case["external_id"]: case["case_id"] for case in cases}
        self.assertEqual(result["priority_case_ids"], [ids["C-PUBLIC"], ids["D-PUBLIC"]])
        self.assertEqual(result["suggested_execution_order"],
                         [ids[name] for name in ("C-PUBLIC", "D-PUBLIC", "A-NO-LINK", "B-OTHER")])
        self.assertEqual({case["case_id"] for case in result["cases"]}, set(ids.values()))
        self.assertEqual(result["suggested_execution_order"], investigation_plan(self.store, self.run)["suggested_execution_order"])
        priorities = {resource["url"]: resource["read_priority"] for resource in result["resources"]}
        self.assertEqual(priorities["https://notgithub.com/pull/1"], 2)
        self.assertEqual(priorities["https://github.com/synthetic/repo/pull/1"], 1)

    def test_every_case_including_description_only_and_all_urls_deduplicate(self):
        cases = self.source([{"统一ID": "S1", "问题描述": "one", "wiki": "https://example.invalid/wiki/one",
                             "PR": "https://gitcode.com/org/repo/pull/1"},
                            {"统一ID": "S2", "问题描述": "two", "wiki": "https://example.invalid/wiki/one"},
                            {"统一ID": "S3", "问题描述": "only description", "根因": "old alleged cause"}])
        result = investigation_plan(self.store, self.run)
        self.assertEqual({case["case_id"] for case in result["cases"]}, {case["case_id"] for case in cases})
        self.assertEqual(len(result["resources"]), 2)
        self.assertEqual(len({resource["url"] for resource in result["resources"]}), 2)
        self.assertTrue(all(case["root_cause_status"] == "ROOT_CAUSE_UNCONFIRMED" for case in result["cases"]))
        self.assertEqual(result["independent_technical_facts"], [])
        self.assertIn("diff", next(r for r in result["resources"] if "/pull/" in r["url"])["requested_capture_scope"])

    def test_policy_satisfied_blocks_search_without_claiming_full_capture(self):
        self.source()
        self.snapshot()
        case = investigation_plan(self.store, self.run)["cases"][0]
        self.assertTrue(case["search_control"]["satisfied"])
        self.assertFalse(case["search_control"]["search_allowed"])
        self.assertIn("DO_NOT_EXPAND_SEARCH", case["agent_next_steps"])
        self.assertEqual(case["root_cause_status"], "ROOT_CAUSE_UNCONFIRMED")

    def test_description_only_case_retains_search_context_and_cell_trace(self):
        original = self.source([{"统一ID": "DESCRIPTION-ONLY", "客户/模型": "Synthetic Model-X",
            "问题描述": "TP16 after restore emits a repeated first token", "算子": "cache_op",
            "根因": "Historical unverified attribution"}])[0]
        planned = investigation_plan(self.store, self.run)["cases"][0]
        self.assertEqual(planned["source_case"], original)
        self.assertEqual(planned["source_case"]["description"], original["raw"]["问题描述"])
        self.assertEqual(planned["source_case"]["customer_model"], "Synthetic Model-X")
        self.assertEqual(planned["source_case"]["operator_raw"], "cache_op")
        self.assertEqual(planned["source_case"]["cell_locations"]["问题描述"], original["cell_locations"]["问题描述"])
        self.assertTrue(planned["source_case"]["source_sha256"])
        self.assertFalse(planned["source_root_cause_is_verified"])
        self.assertEqual(planned["root_cause_status"], "ROOT_CAUSE_UNCONFIRMED")
        self.assertEqual(planned["root_cause_candidates"], [])
        self.assertTrue(planned["search_control"]["search_allowed"])

    def test_link_discovery_is_navigation_not_root_cause(self):
        self.source()
        self.snapshot("A title mentions buffer failure. See https://gitcode.com/org/repo/issues/12 and https://github.com/org/repo/pull/34.")
        result = investigation_plan(self.store, self.run)
        self.assertEqual(len(result["linked_resource_candidates"]), 2)
        for lead in result["linked_resource_candidates"]:
            self.assertEqual(lead["origin"], "LINK_DISCOVERED")
            self.assertFalse(lead["root_cause_evidence"])
            self.assertEqual(lead["association_status"], "UNVERIFIED")
        self.assertEqual(result["cases"][0]["root_cause_candidates"], [])

    def test_only_current_selected_issue_can_supply_cited_candidate(self):
        case = self.source()[0]
        snap = self.snapshot()
        self.finish(case, snap)
        result = investigation_plan(self.store, self.run)
        self.assertEqual(len(result["independent_technical_facts"]), 2)
        causes = result["cases"][0]["root_cause_candidates"]
        self.assertEqual([cause["value"] for cause in causes], ["buffer reused before completion"])
        self.assertTrue(all(cause["issue_label"] == "Issue A" for cause in causes))
        self.assertFalse(causes[0]["human_accepted"])
        self.assertEqual(causes[0]["observation_scope"], "CAPTURED_CONTENT")

    def test_reject_old_policy_and_changed_snapshot_cannot_supply_case_cause(self):
        case = self.source()[0]
        snap = self.snapshot()
        _, judgment = self.finish(case, snap)
        self.store.event(self.run, "review", {"judgment_id": judgment["judgment_id"], "verdict": "REJECT"})
        self.assertEqual(investigation_plan(self.store, self.run)["cases"][0]["root_cause_candidates"], [])
        import faultaudit.prompts as prompts
        with patch.object(prompts, "PROMPT_VERSION", "changed-test-policy"):
            result = investigation_plan(self.store, self.run)
            self.assertEqual(result["independent_technical_facts"], [])
            self.assertEqual(result["cases"][0]["root_cause_candidates"], [])
        self.snapshot("Updated captured text")
        self.assertEqual(investigation_plan(self.store, self.run)["independent_technical_facts"], [])

    def test_other_event_never_inherits_its_root_cause(self):
        case = self.source()[0]
        snap = self.snapshot()
        _, judgment = self.finish(case, snap)
        # Simulate a persisted negative result: even a supported claim cannot be inherited.
        judgment.update(event_relation="DIFFERENT_EVENT", claim_support={"root_cause": "SUPPORTED"}, negative_basis=None)
        self.store.put(self.run, "judgments", judgment["judgment_id"], judgment, mutable=True)
        result = investigation_plan(self.store, self.run)
        self.assertEqual(len(result["independent_technical_facts"]), 2)
        self.assertEqual(result["cases"][0]["root_cause_candidates"], [])

    def test_precise_quotes_are_rechecked_instead_of_trusting_saved_fact(self):
        case = self.source()[0]
        snap = self.snapshot()
        summary, _ = self.finish(case, snap)
        summary["issues"][0]["facts"][0]["evidence"][0]["quote"] = "fabricated absent words"
        self.store.put(self.run, "summaries", summary["task_id"], summary, mutable=True)
        result = investigation_plan(self.store, self.run)
        self.assertEqual(result["independent_technical_facts"], [])
        self.assertEqual(result["cases"][0]["root_cause_candidates"], [])

    def test_multiple_scopes_keep_distinct_work_ids(self):
        case = self.source()[0]
        snapshot = self.snapshot()
        reference = self.store.records(self.run, "references")[0]
        for label in ("Issue A", "Issue B"):
            register_evidence_association(self.store, self.run, case_id=case["case_id"], ref_id=reference["ref_id"],
                snapshot_id=snapshot["snapshot_id"], applicable_issue_ids=[label], user_confirmed=True,
                confirmed_by="synthetic-user", reason="Explicit synthetic subproblem")
        self.finish(case, snapshot)
        result = investigation_plan(self.store, self.run)
        self.assertEqual(len(result["resources"]), 1)
        self.assertEqual(len(result["work_items"]), 2)
        self.assertEqual({tuple(work["issue_scope"]["applicable_issue_ids"]) for work in result["work_items"]}, {("Issue A",), ("Issue B",)})
        labels = {card["card_id"]: card["issue_label"] for card in result["resource_summary_cards"]}
        for work in result["work_items"]:
            self.assertEqual({labels[card_id] for card_id in work["resource_summary_card_ids"]},
                             set(work["issue_scope"]["applicable_issue_ids"]))

    def test_invalid_snapshot_and_incomplete_summary_cannot_supply_facts(self):
        case = self.source()[0]
        snap = self.snapshot()
        summary, _ = self.finish(case, snap)
        summary["segments_processed"] = 0
        self.store.put(self.run, "summaries", summary["task_id"], summary, mutable=True)
        self.assertEqual(investigation_plan(self.store, self.run)["independent_technical_facts"], [])
        Path(snap["text_path"]).write_text("tampered synthetic text", encoding="utf-8")
        result = investigation_plan(self.store, self.run)
        self.assertFalse(result["resources"][0]["snapshot_integrity_verified"])
        self.assertEqual(result["resources"][0]["action"], "FETCH_OR_REPAIR_CAPTURE")
        self.assertEqual(result["cases"][0]["root_cause_candidates"], [])

    def test_cli_rejects_output_inside_state(self):
        self.source()
        destination = self.store.root / "forbidden-output.json"
        process = subprocess.run([sys.executable, "-m", "faultaudit", "--state", str(self.store.root),
            "investigation-plan", "--run", self.run, "--out", str(destination)],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertNotEqual(process.returncode, 0)
        self.assertFalse(destination.exists())

    def test_empty_link_placeholders_import_without_references_and_allow_search(self):
        values = ("无（待补）", "无(待补)", " 无（待补） ", "无", "N/A", "—")
        original = self.source([{"统一ID": f"EMPTY-{index}", "问题描述": "Description retained", "wiki": value}
                                for index, value in enumerate(values)])
        self.assertEqual(self.store.records(self.run, "references"), [])
        result = investigation_plan(self.store, self.run)
        self.assertTrue(all(case["search_control"]["search_allowed"] for case in result["cases"]))
        self.assertEqual({case["source_case"]["raw"]["wiki"] for case in result["cases"]}, set(values))
        self.assertEqual(len(original), len(values))

    def test_historical_empty_reference_is_ignored_by_plan_but_not_deleted(self):
        case = self.source([{"统一ID": "OLD-EMPTY", "问题描述": "Description retained", "wiki": "无（待补）"}])[0]
        ref = {"ref_id": "old-empty-placeholder", "case_id": case["case_id"], "raw_text": "无（待补）",
               "url": None, "origin": "LEGACY_TABLE", "status": "UNRESOLVED", "discovered_by": "importer",
               "location": f"{case['sheet']}!{case['cell_locations']['wiki']} (row {case['row']})"}
        self.store.put(self.run, "references", ref["ref_id"], ref)
        before = copy.deepcopy(self.store.records(self.run, "references"))
        plan = investigation_plan(self.store, self.run)
        self.assertTrue(plan["cases"][0]["search_control"]["search_allowed"])
        self.assertEqual(plan["cases"][0]["selected_ref_ids"], [])
        self.assertEqual(plan["ignored_empty_reference_ids"], [ref["ref_id"]])
        self.assertEqual(self.store.records(self.run, "references"), before)
        # A hyperlink target remains real evidence even if its display text is empty-link wording.
        self.store.put(self.run, "references", ref["ref_id"], {**ref,
            "url": "https://example.invalid/wiki/hidden-target", "status": "PARSED"}, mutable=True)
        plan = investigation_plan(self.store, self.run)
        self.assertFalse(plan["cases"][0]["search_control"]["search_allowed"])
        self.assertEqual(plan["ignored_empty_reference_ids"], [])
        self.assertEqual(len(plan["resources"]), 1)

    def test_real_bad_and_mixed_reference_fields_are_not_empty(self):
        values = ("#NAME?", "DTS2025122319172", "https://", "待补", "无（待补）但需要定位正文",
                  "无（待补）；https://gitcode.com/synthetic/repo/pull/1")
        self.assertTrue(all(not is_empty_link_value(value) for value in values))
        self.source([{"统一ID": f"NONEMPTY-{index}", "问题描述": "Fault", "wiki": value}
                     for index, value in enumerate(values)])
        refs = self.store.records(self.run, "references")
        self.assertEqual(len(refs), len(values))
        plan = investigation_plan(self.store, self.run)
        self.assertTrue(all(not case["search_control"]["search_allowed"] for case in plan["cases"]))
        self.assertEqual(plan["ignored_empty_reference_ids"], [])
        self.assertEqual(len(plan["resources"]), 1)

    def test_importer_rule_source_changes_invalidate_pending_model_requests(self):
        from tests.test_bridge import BridgeTests
        from faultaudit.bridge import submit_model_results
        from faultaudit.store import AuditError
        workflow = BridgeTests(methodName="runTest")
        workflow.setUp()
        self.addCleanup(workflow.tearDown)
        _, requests = workflow.drive()
        response = workflow.envelope(requests[0])
        original_read_bytes = Path.read_bytes
        def changed_source(path):
            content = original_read_bytes(path)
            return content + b"\n# changed shared empty-link policy\n" if path.name == "importers.py" else content
        with patch.object(Path, "read_bytes", changed_source):
            with self.assertRaisesRegex(AuditError, "obsolete core policy"):
                submit_model_results(workflow.store, workflow.run_id, [response])
        self.assertEqual(workflow.store.records(workflow.run_id, "model_results"), [])

    def test_repeated_read_only_plan_and_cli_do_not_change_state(self):
        case = self.source()[0]
        snap = self.snapshot()
        self.finish(case, snap)
        root = self.store.root
        hashes = lambda: {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in root.rglob("*") if path.is_file()}
        before = hashes()
        count = self.store.conn.total_changes
        first = investigation_plan(self.store, self.run)
        self.assertEqual(first, investigation_plan(self.store, self.run))
        self.assertEqual(self.store.conn.total_changes, count)
        out = self.directory / "investigation.json"
        process = subprocess.run([sys.executable, "-m", "faultaudit", "--state", str(root), "investigation-plan",
            "--run", self.run, "--out", str(out)], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), first)
        self.assertEqual(before, hashes())


if __name__ == "__main__":
    unittest.main()
