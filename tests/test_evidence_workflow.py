"""Evidence-first acceptance through the real file bridge, using synthetic data."""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from faultaudit.bridge import OpenCodeJudge, export_model_tasks, submit_model_results
from faultaudit.evidence_plan import register_event_group, register_evidence_association, register_search_policy
from faultaudit.importers import import_cases, import_catalog
from faultaudit.pipeline import evidence_plan, execute, fetch_tasks, import_into, report_data
from faultaudit.store import AuditError, Store

ROOT = Path(__file__).resolve().parents[1]
TEXT = "main：sample_op在推理阶段TP8首次输出异常，定位为舍入误差；logprob=0.404。修复版本未说明。"


class EvidenceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.directory = Path(self.temp.name)
        self.store = Store(self.directory / "state")
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.store.close)
        self.run_id = self.store.create_run({"is_synthetic": True})

    def load(self, count=1, source_kind="ORIGINAL_WEEKLY", with_links=True, extra_links=False):
        rows = [{"统一ID": f"SYN-{i}", "问题描述": "首次输出异常", "触发条件": "推理阶段TP8", "算子": "sample_op",
                 "根因": "舍入误差", "关键数值": "logprob=0.404", "wiki": "https://example.invalid/main"} for i in range(count)]
        if extra_links:
            for row in rows:
                row.update(DTS="https://example.invalid/ticket", PR="https://example.invalid/fix")
        if not with_links:
            for row in rows:
                row.pop("wiki")
                row.pop("PR", None)
        source = self.directory / "cases.json"
        source.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        imported = import_cases(source, source_kind)
        import_into(self.store, self.run_id, imported)
        catalog = self.directory / "catalog.json"
        catalog.write_text(json.dumps([{"item_id": "SYN-PATTERN", "mechanism": "rounding"}]), encoding="utf-8")
        import_into(self.store, self.run_id, import_catalog(catalog), catalog=True)
        return imported["cases"]

    def capture(self, status="PARTIAL"):
        return self.store.ingest_evidence(self.run_id, {"url": "https://example.invalid/main", "text": TEXT,
            "status": status, "components": {"body": "COMPLETE"}, "is_synthetic": True})

    def drive(self):
        status = execute(self.store, self.run_id, OpenCodeJudge(self.store, self.run_id), mode="opencode", model_id="opencode-managed")
        return status, export_model_tasks(self.store, self.run_id)["tasks"]

    def envelope(self, task):
        payload = task["payload"]
        if task["kind"] == "summarize":
            snap = payload["snapshot"]
            ref = {"segment_id": snap["segments"][0]["segment_id"], "quote": snap["text"]}
            result = {"snapshot_id": snap["snapshot_id"], "issues": [{"label": "main", "facts": [
                {"field": "observation", "value": snap["text"], "evidence": [ref]}]}], "unknown_fields": ["fix_version"]}
        elif task["kind"] == "catalog":
            result = {"case_id": payload["case"]["case_id"], "scope": "FULL_CATALOG", "overall": "UNDETERMINED",
                "catalog_results": [{"item_id": item["item_id"], "result": "UNDETERMINED", "reason": "Event remains unconfirmed", "evidence": []}
                                    for item in payload["items"]]}
        else:
            case, snap = payload["case"], payload["snapshot"]
            ref = {"segment_id": snap["segments"][0]["segment_id"], "quote": snap["text"]}
            def fact(category, field, meaning, value):
                return {"category": category, "source_field": field, "source_quote": case["raw"][field],
                    "source_cell": case["cell_locations"][field], "source_meaning": meaning, "evidence_meaning": meaning,
                    "source_value": value, "evidence_value": value, "evidence": [ref], "relation": "MATCH", "reason": "Exact scoped facts"}
            result = {"case_id": case["case_id"], "snapshot_id": snap["snapshot_id"], "case_attribution": "PARTIAL",
                "event_relation": "UNDETERMINED", "pattern_relation": "POSSIBLY_RELATED", "support_level": "PARTIAL",
                "claim_support": {"symptom": "SUPPORTED", "root_cause": "SUPPORTED", "fix": "UNKNOWN", "verification": "UNKNOWN"},
                "short_reason": "Original evidence supports the observed facts; fix version remains unknown", "evidence": [ref],
                "fact_comparisons": [fact("NUMBER", "关键数值", "logprob", "0.404"), fact("TERM", "算子", "operator", "sample_op"),
                    fact("SCENARIO", "问题描述", "symptom", "首次输出异常"), fact("SCENARIO", "触发条件", "occurrence_context", "推理阶段TP8"),
                    fact("TECHNICAL_CONCLUSION", "根因", "mechanism", "舍入误差")],
                "applicable_issue": {"label": "main", "evidence": [ref], "selection_reason": "One applicable problem"},
                "self_check": {"attempt": 1, "numeric_meaning_checked": True, "citations_checked": True,
                    "counterevidence_checked": True, "issue_scope_checked": True, "event_vs_technical_checked": True,
                    "passed": True, "issues": []}}
        return {"schema_version": "1.0", "run_id": self.run_id, "task_id": task["task_id"], "request_hash": task["request_hash"],
                "result": result, "producer": {"executor": "opencode", "opencode_version": "synthetic-test",
                    "provider": "offline-fixture", "model": "synthetic-model", "session_id": "synthetic-session"}}

    def finish(self):
        for _ in range(8):
            _, tasks = self.drive()
            if not tasks:
                return
            submit_model_results(self.store, self.run_id, [self.envelope(task) for task in tasks])
        self.fail("Evidence-first workflow kept generating new work")

    def test_partial_original_evidence_completes_without_search_or_human_queue(self):
        self.load()
        self.capture()
        self.finish()
        data = report_data(self.store, self.run_id)
        judgment = next(j for j in data["judgments"] if j["required"])
        self.assertEqual(judgment["processing_status"], "AUTO_PROCESSED")
        self.assertFalse(judgment["review_required"])
        self.assertEqual(judgment["review_status"], "NOT_REQUIRED")
        self.assertEqual(judgment["claim_support"]["fix"], "UNKNOWN")
        self.assertNotEqual(data["evidence_plans"]["cases"][0]["path"], "SEARCH_REQUIRED")
        self.assertEqual(fetch_tasks(self.store, self.run_id)["fetch_tasks"], [])
        before = self.store.records(self.run_id, "model_tasks")
        self.finish()
        self.assertEqual(self.store.records(self.run_id, "model_tasks"), before)
        self.assertEqual(len(before), 3)
        self.assertFalse(any("human review" in reason for reason in data["validation"]["pending"]))
        self.assertTrue(data["validation"]["fact_organization_complete"])
        self.assertFalse(data["validation"]["complete"], "Undetermined catalog coverage is retained independently")

    def test_confirmed_group_shares_work_and_retains_both_original_sources(self):
        cases = self.load(count=2)
        register_event_group(self.store, self.run_id, case_ids=[c["case_id"] for c in cases], user_confirmed=True,
                             confirmed_by="synthetic-user", reason="Explicit synthetic event relationship")
        self.capture()
        self.assertEqual(len(evidence_plan(self.store, self.run_id)["work_items"]), 1)
        self.finish()
        data = report_data(self.store, self.run_id)
        self.assertEqual(len(data["cases"]), 2)
        self.assertEqual(len(data["event_conclusions"]), 1)
        self.assertEqual(len([j for j in data["judgments"] if j["required"]]), 1)
        self.assertEqual(len(data["model_tasks"]), 3)

    def test_first_usable_search_evidence_stops_and_old_unused_work_never_becomes_success(self):
        case = self.load(with_links=False)[0]
        self.assertEqual(evidence_plan(self.store, self.run_id)["cases"][0]["path"], "SEARCH_REQUIRED")
        for url in ("https://example.invalid/candidate-a", "https://example.invalid/candidate-b"):
            self.store.ingest_evidence(self.run_id, {"url": url, "text": TEXT, "status": "PARTIAL",
                "is_synthetic": True, "origin": "SEARCH_DISCOVERED", "case_ids": [case["case_id"]]})
        initial = evidence_plan(self.store, self.run_id)
        selected = set(initial["cases"][0]["selected_ref_ids"])
        unused = next(ref for ref in self.store.records(self.run_id, "references") if ref["ref_id"] not in selected)
        old_task = self.store.task(self.run_id, "fetch", unused["ref_id"], ["synthetic-old-fetch"])
        self.store.task_status(self.run_id, old_task["task_id"], "BLOCKED", "Previous unexecuted task")
        self.finish()
        data = report_data(self.store, self.run_id)
        self.assertEqual(data["evidence_plans"]["cases"][0]["path"], "VERIFIED_SEARCH")
        self.assertEqual(len(data["model_tasks"]), 3)
        old = next(task for task in data["tasks"] if task["task_id"] == old_task["task_id"])
        self.assertFalse(old["required"])
        self.assertEqual(old["status"], "BLOCKED")
        self.assertFalse(any(old["task_id"] in reason for reason in data["validation"]["pending"]))
        self.assertEqual(len([ref for ref in data["references"] if not ref["required"]]), 1)

    def test_original_root_cause_conflict_keeps_reference_and_enters_exception_queue(self):
        self.load()
        self.store.ingest_evidence(self.run_id, {"url": "https://example.invalid/main", "text": TEXT.replace("舍入误差", "量化错配"),
            "status": "PARTIAL", "is_synthetic": True})
        _, tasks = self.drive()
        submit_model_results(self.store, self.run_id, [self.envelope(tasks[0])])
        _, tasks = self.drive()
        result = self.envelope(tasks[0])
        result["result"]["claim_support"]["root_cause"] = "CONTRADICTED"
        result["result"]["conflicting_dimensions"] = ["root_cause"]
        fact = result["result"]["fact_comparisons"][-1]
        fact.update(evidence_value="量化错配", relation="CONFLICT")
        submit_model_results(self.store, self.run_id, [result])
        self.drive()
        data = report_data(self.store, self.run_id)
        selected = [j for j in data["judgments"] if j["required"]]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["processing_status"], "EXCEPTION")
        self.assertTrue(selected[0]["review_required"])
        self.assertEqual(len(data["references"]), 1)
        self.assertEqual(len([ref for ref in data["references"] if ref["required"]]), 1)

    def test_all_existing_wiki_ticket_and_pr_are_processed_without_repeated_dispatch(self):
        self.load(count=2, source_kind="LEGACY_TABLE", extra_links=True)
        # Two independent source rows retain six links, but each resource is fetched once.
        self.assertEqual(len(fetch_tasks(self.store, self.run_id)["fetch_tasks"]), 3)
        self.drive()
        self.assertEqual(len([task for task in self.store.tasks(self.run_id) if task["kind"] == "fetch"]), 3)
        for url in ("https://example.invalid/main", "https://example.invalid/ticket", "https://example.invalid/fix"):
            self.store.ingest_evidence(self.run_id, {"url": url, "text": TEXT, "status": "PARTIAL", "is_synthetic": True})
        self.finish()
        data = report_data(self.store, self.run_id)
        self.assertEqual(len([task for task in data["model_tasks"] if task["kind"] == "summarize"]), 3)
        self.assertEqual(len([j for j in data["judgments"] if j["required"]]), 6)
        self.assertEqual(len([ref for ref in data["references"] if ref["required"]]), 6)
        self.assertTrue(all(case["root_cause_origin"] == "LEGACY_DERIVED_UNKNOWN" for case in data["cases"]))
        self.assertTrue(all(not j["review_required"] for j in data["judgments"] if j["required"]))
        before = self.store.records(self.run_id, "model_tasks")
        self.finish()
        self.assertEqual(self.store.records(self.run_id, "model_tasks"), before)

    def test_one_failed_existing_link_keeps_other_material_processing_without_human_referral(self):
        self.load(extra_links=True)
        self.capture()
        self.store.ingest_evidence(self.run_id, {"url": "https://example.invalid/fix", "text": TEXT,
            "status": "PARTIAL", "is_synthetic": True})
        self.store.ingest_evidence(self.run_id, {"url": "https://example.invalid/ticket", "text": "",
            "status": "AUTH_REQUIRED", "is_synthetic": True})
        self.finish()
        data = report_data(self.store, self.run_id)
        selected = [j for j in data["judgments"] if j["required"]]
        self.assertEqual(len(selected), 2)
        self.assertTrue(all(j["processing_status"] == "AUTO_PROCESSED" and not j["review_required"] for j in selected))
        self.assertNotEqual(data["evidence_plans"]["cases"][0]["path"], "SEARCH_REQUIRED")
        self.assertFalse(any("human review" in reason for reason in data["validation"]["pending"]))
        self.assertFalse(data["validation"]["fact_organization_complete"])
        self.assertEqual(len(fetch_tasks(self.store, self.run_id)["fetch_tasks"]), 1)

    def test_changed_work_context_invalidates_current_result_without_losing_history_or_inheriting_accept(self):
        case = self.load()[0]
        snapshot = self.capture()
        self.finish()
        old = next(j for j in report_data(self.store, self.run_id)["judgments"] if j["required"])
        self.store.event(self.run_id, "review", {"judgment_id": old["judgment_id"], "verdict": "ACCEPT",
            "reviewer": "synthetic-reviewer", "reason": "Synthetic history only"})
        register_evidence_association(self.store, self.run_id, case_id=case["case_id"], snapshot_id=snapshot["snapshot_id"],
            user_confirmed=True, confirmed_by="synthetic-user", reason="Additional explicit source confirmation")
        data = report_data(self.store, self.run_id)
        self.assertTrue(next(j for j in data["judgments"] if j["judgment_id"] == old["judgment_id"])["is_stale"])
        self.assertFalse(any(j["required"] for j in data["judgments"]))
        self.finish()
        data = report_data(self.store, self.run_id)
        current = next(j for j in data["judgments"] if j["required"])
        self.assertEqual(current["work_id"], old["work_id"], "Provenance changes do not invent another technical work")
        self.assertNotEqual(current["judgment_id"], old["judgment_id"], "Changed input requires a new bound request/result")
        self.assertEqual(current["review_status"], "NOT_REQUIRED")
        self.assertEqual(next(j for j in data["judgments"] if j["judgment_id"] == old["judgment_id"])["review_status"], "ACCEPT")
        self.assertTrue(any(result["result"].get("case_id") == case["case_id"] for result in data["model_results"]))

    def test_explicit_gitcode_goal_uses_candidate_then_stops_without_new_tasks(self):
        case = self.load()[0]
        self.capture()
        self.finish()
        self.store.ingest_evidence(self.run_id, {"url": "https://gitcode.com/synthetic/evidence/pull/1", "text": TEXT,
            "status": "PARTIAL", "is_synthetic": True, "origin": "LINK_DISCOVERED", "case_ids": [case["case_id"]],
            "record_discovery": True, "discovered_from_url": "https://example.invalid/main"})
        # An unsolicited candidate does not restart default search or processing.
        before = self.store.records(self.run_id, "model_tasks")
        self.finish()
        self.assertEqual(self.store.records(self.run_id, "model_tasks"), before)
        register_search_policy(self.store, self.run_id, {"required_sources": ["GITCODE"]})
        pending = evidence_plan(self.store, self.run_id)["cases"][0]
        self.assertFalse(pending["search_control"]["satisfied"])
        self.assertEqual(pending["search_control"]["status"], "CANDIDATE_PENDING")
        self.finish()
        data = report_data(self.store, self.run_id)
        control = data["evidence_plans"]["cases"][0]["search_control"]
        self.assertTrue(control["satisfied"])
        self.assertFalse(control["search_allowed"])
        self.assertEqual(control["usable_sources"], ["GITCODE", "WIKI"])
        selected = [judgment for judgment in data["judgments"] if judgment["required"]]
        self.assertEqual(len(selected), 2)
        self.assertTrue(all(not judgment["review_required"] and judgment["review_status"] == "NOT_REQUIRED" for judgment in selected))
        self.assertEqual(self.store.events(self.run_id, "review"), [])
        self.assertTrue(data["validation"]["search_goals_satisfied"])
        self.assertTrue(data["validation"]["fact_organization_complete"])
        self.assertFalse(data["validation"]["complete"], "Unknown catalog coverage is independent of search completion")
        before = self.store.records(self.run_id, "model_tasks")
        self.finish()
        self.assertEqual(self.store.records(self.run_id, "model_tasks"), before)

    def test_same_case_snapshot_two_issue_scopes_keep_separate_work_through_submission(self):
        case = self.load()[0]
        passages = {"issue-a": "issue-a: " + TEXT,
                    "issue-b": "issue-b: " + TEXT.replace("logprob=0.404", "概率=0.404")}
        snapshot = self.store.ingest_evidence(self.run_id, {"url": "https://example.invalid/main",
            "text": "\n\n".join(passages.values()), "status": "PARTIAL", "is_synthetic": True})
        for label in ("issue-a", "issue-b"):
            register_evidence_association(self.store, self.run_id, case_id=case["case_id"],
                snapshot_id=snapshot["snapshot_id"], scope="ISSUES", applicable_issue_ids=[label],
                user_confirmed=True, confirmed_by="synthetic-user", reason="Explicitly scoped source relationship")
        _, tasks = self.drive()
        summary = self.envelope(tasks[0])
        summary["result"]["issues"] = [{"label": label, "facts": [{"field": "observation", "value": text,
            "evidence": [{"segment_id": segment["segment_id"], "quote": text} for segment in snapshot["segments"] if text in segment["text"]]}]}
            for label, text in passages.items()]
        submit_model_results(self.store, self.run_id, [summary])
        _, tasks = self.drive()
        comparisons = [task for task in tasks if task["kind"] == "compare"]
        self.assertEqual(len(comparisons), 2)
        self.assertEqual(len({task["work_id"] for task in comparisons}), 2)
        self.assertEqual(len({task["payload"]["snapshot"]["snapshot_id"] for task in comparisons}), 1)
        responses = []
        for task in comparisons:
            response = self.envelope(task)
            scope = task["payload"]["processing_context"]["applicable_issue"]["applicable_issue_ids"]
            response["result"]["applicable_issue"]["label"] = scope[0]
            text = passages[scope[0]]
            refs = [{"segment_id": segment["segment_id"], "quote": text} for segment in snapshot["segments"] if text in segment["text"]]
            response["result"]["evidence"] = refs
            response["result"]["applicable_issue"]["evidence"] = refs
            for fact in response["result"]["fact_comparisons"]:
                fact["evidence"] = refs
                if scope[0] == "issue-b" and fact["category"] == "NUMBER":
                    fact.update(evidence_meaning="probability", relation="UNKNOWN", reason="Same number denotes probability, not logprob")
            responses.append(response)
        wrong_scope = copy.deepcopy(responses[0])
        wrong_scope["result"]["applicable_issue"]["label"] = responses[1]["result"]["applicable_issue"]["label"]
        with self.assertRaises(AuditError):
            submit_model_results(self.store, self.run_id, [wrong_scope])
        # The second work alone must not count the first as judged or release its catalog dependency.
        submit_model_results(self.store, self.run_id, [responses[1]])
        data = self.drive()[0]
        self.assertEqual(data["counts"]["judged_work_ids"], 1)
        self.assertEqual(data["counts"]["planned_work_ids"], 2)
        self.assertTrue(any("Unjudged work" in reason for reason in data["pending"]))
        self.assertFalse(any(task["kind"] == "catalog" for task in export_model_tasks(self.store, self.run_id)["tasks"]))
        submit_model_results(self.store, self.run_id, [responses[0]])
        self.finish()
        judgments = [j for j in report_data(self.store, self.run_id)["judgments"] if j["required"]]
        self.assertEqual({j["applicable_issue"]["label"] for j in judgments}, {"issue-a", "issue-b"})
        self.assertTrue(all(j["evidence"][0]["quote"] == passages[j["applicable_issue"]["label"]] for j in judgments))
        self.assertEqual({j["work_id"] for j in judgments}, {task["work_id"] for task in comparisons})
        before = self.store.records(self.run_id, "model_tasks")
        self.drive()
        self.assertEqual(self.store.records(self.run_id, "model_tasks"), before)

    def test_plan_preview_opens_database_read_only_and_does_not_advance_tasks(self):
        self.load()
        before = self.store.conn.total_changes
        database = self.store.root / "audit.sqlite3"
        digest = hashlib.sha256(database.read_bytes()).hexdigest()
        process = subprocess.run([sys.executable, str(ROOT / "run_faultaudit.py"), "--state", str(self.store.root),
            "evidence-plan", "--run", self.run_id], cwd=ROOT, capture_output=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), digest)
        self.assertEqual(self.store.conn.total_changes, before)
        self.assertEqual(self.store.tasks(self.run_id), [])
        self.assertEqual(json.loads(process.stdout)["cases"][0]["path"], "FETCH_ORIGINAL")
