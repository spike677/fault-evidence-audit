"""Read-only, evidence-grounded handoff for an external investigating agent.

This module performs no search, model call or state mutation. Independent
technical facts and a proposed cause of the current case are separate outputs.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from .contracts import EvidenceSummary, Judgment
from .model import ModelError, validate_task_result
from .pipeline import (check_citations, current_summaries, evidence_plan,
                       gate_judgment, necessary_judgments, work_context)
from .store import Store, canonical_url, digest

ROOT_FIELDS = {"root_cause", "mechanism", "cause", "根因", "故障原因", "故障机理", "根因机制"}
SUMMARY_CARD_FIELDS = {
    "operator": {"operator", "operators", "operator_name", "算子", "算子名", "算子名称"},
    "symptom": {"symptom", "symptoms", "observed_problem", "症状", "故障现象", "问题现象", "现象"},
    "root_cause": ROOT_FIELDS,
    "trigger": {"trigger", "trigger_condition", "trigger_conditions", "触发", "触发条件", "复现条件"},
    "fix": {"fix", "repair", "fix_operation", "修复", "修复操作", "修复方案", "解决方案"},
    "verification": {"verification", "validation", "test_result", "验证", "验证结果", "测试结果"},
}
READABLE = {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"}
URL_PATTERN = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)


def _within(refs: list[dict], scope: list[dict]) -> bool:
    return bool(refs) and all(any(ref.get("segment_id") == outer.get("segment_id")
        and ref.get("quote", "") in outer.get("quote", "") for outer in scope) for ref in refs)


def _public_repository_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        parsed = urlsplit(canonical_url(url))
        return parsed.hostname in {"gitcode.com", "github.com"}
    except (ValueError, TypeError):
        return False


def _linked_resources(snapshot: dict) -> list[dict]:
    """Extract navigation leads only. A hyperlink is never a verified relation."""
    found = {}
    for segment in snapshot.get("segments", []):
        for match in URL_PATTERN.finditer(segment["text"]):
            raw = match.group().rstrip(".,;:!?)，。；：！）]}")
            try:
                url = canonical_url(raw)
            except (ValueError, TypeError):
                continue
            parsed = urlsplit(url)
            if parsed.hostname not in {"github.com", "gitcode.com"} or not re.search(
                    r"/(?:issues?|pulls?|commits?)/[A-Za-z0-9_-]+(?:/|$)", parsed.path):
                continue
            if url == snapshot["url"]:
                continue
            ref = {"segment_id": segment["segment_id"], "quote": raw}
            item = found.setdefault(url, {"url": url, "origin": "LINK_DISCOVERED",
                "parent_url": snapshot["url"], "parent_snapshot_id": snapshot["snapshot_id"],
                "evidence": [], "association_status": "UNVERIFIED",
                "action": "ASSESS_RELEVANCE_THEN_TARGETED_READ", "required": False,
                "root_cause_evidence": False})
            if ref not in item["evidence"]:
                item["evidence"].append(ref)
    return sorted(found.values(), key=lambda item: item["url"])


def _resource_summary_cards(summaries: dict, facts: dict, snapshots: dict) -> list[dict]:
    """Present cited facts; do not perform another semantic judgment or inference."""
    cards = []
    for task_id, summary in sorted(summaries.items()):
        snapshot = snapshots[summary["snapshot_id"]]
        for index, issue in enumerate(summary["issues"]):
            issue_facts = sorted((fact for fact in facts.values()
                if fact["summary_task_id"] == task_id and fact["issue_index"] == index),
                key=lambda fact: fact["fact_id"])
            fields, used = {}, set()
            for name, aliases in SUMMARY_CARD_FIELDS.items():
                selected = [fact for fact in issue_facts if fact["field"].strip().casefold() in aliases]
                used.update(fact["fact_id"] for fact in selected)
                fields[name] = {"status": "CITED_FACTS" if selected else "UNKNOWN_IN_CAPTURED_CONTENT",
                    "fact_ids": [fact["fact_id"] for fact in selected],
                    "facts": [{key: fact[key] for key in ("fact_id", "field", "value", "evidence")}
                              for fact in selected],
                    "basis": "CITED_MODEL_SUMMARY" if selected else "NO_CITED_FACT_IN_CAPTURED_CONTENT"}
                if name == "verification":
                    fields[name]["local_execution_verified"] = False
                    fields[name]["attribution"] = ("SOURCE_REPORTED_VIA_CURRENT_MODEL_SUMMARY" if selected
                                                    else "UNKNOWN_IN_CAPTURED_CONTENT")
            identity = {"snapshot_id": snapshot["snapshot_id"], "summary_task_id": task_id,
                        "issue_label": issue["label"], "issue_index": index}
            cards.append({"card_id": "summary-card-" + digest(identity)[:24], **identity,
                "url": snapshot["url"], "status": "CURRENT_CITED_SUMMARY",
                "fields": fields, "other_fact_ids": [fact["fact_id"] for fact in issue_facts
                    if fact["fact_id"] not in used],
                "summary_unknown_fields": summary.get("unknown_fields", []),
                "model_mode": summary["model_mode"], "model_id": summary["model_id"],
                "basis": "CITED_MODEL_SUMMARY", "capture_status": snapshot["status"],
                "observation_scope": "CAPTURED_CONTENT", "case_root_cause_confirmed": False})
    return sorted(cards, key=lambda card: card["card_id"])


def investigation_plan(store: Store, run_id: str) -> dict:
    """Describe necessary investigations and quote only current, valid results.

    A candidate is still a model proposal. No source title, link, imported root
    cause or technical fact from an excluded event supplies a case root cause.
    """
    store.run_info(run_id)
    plan = evidence_plan(store, run_id)
    cases = {case["case_id"]: case for case in store.records(run_id, "cases")}
    snapshots = {snap["snapshot_id"]: snap for snap in store.active_snapshots(run_id)}
    summary_records = sorted(current_summaries(store, run_id), key=lambda item: item["task_id"])
    summaries, facts, gaps = {}, {}, {}
    for summary in summary_records:
        sid = summary["snapshot_id"]
        snapshot = snapshots[sid]
        errors = store.verify_snapshot(snapshot)
        if summary.get("model_mode") == "mock":
            errors.append("MOCK_SUMMARY_IS_NOT_TECHNICAL_VERIFICATION")
        try:
            value = {key: summary[key] for key in EvidenceSummary.model_fields}
            validate_task_result("summarize", value, snapshot=snapshot)
        except (ValueError, KeyError, ModelError) as exc:
            errors.append("INVALID_SUMMARY: " + str(exc))
        if summary.get("segments_processed") != len(snapshot.get("segments", [])):
            errors.append("SUMMARY_SEGMENT_COVERAGE_UNCONFIRMED")
        if errors:
            gaps.setdefault(sid, []).extend(errors)
            continue
        summaries[summary["task_id"]] = summary
        for issue_index, issue in enumerate(summary.get("issues", [])):
            for fact in issue.get("facts", []):
                refs = fact.get("evidence", [])
                if fact.get("value") in (None, "", []) or not refs or check_citations(refs, snapshot):
                    continue
                identity = {"summary_task_id": summary["task_id"], "issue_label": issue["label"], "issue_index": issue_index,
                            "field": fact["field"], "value": fact["value"], "evidence": refs}
                fid = "fact-" + digest(identity)[:24]
                facts[fid] = {"fact_id": fid, "snapshot_id": sid, "url": snapshot["url"],
                    **identity, "capture_status": snapshot["status"], "observation_scope": "CAPTURED_CONTENT",
                    "case_root_cause_confirmed": False, "producer": "CURRENT_INDEPENDENT_MODEL_SUMMARY"}

    summary_cards = _resource_summary_cards(summaries, facts, snapshots)
    judgments = necessary_judgments(store, run_id, plan)
    works = []
    for work in plan["work_items"]:
        sid = work["snapshot_id"]
        snapshot = snapshots[sid]
        work_gaps = list(gaps.get(sid, []))
        matching = [j for j in judgments if j.get("work_id") == work["work_id"]]
        selected_facts, candidates, excluded = set(), [], []
        for judgment in matching:
            jid = judgment["judgment_id"]
            if judgment.get("review_status") == "REJECT":
                excluded.append({"judgment_id": jid, "reason": "HUMAN_REJECTED"})
                continue
            if judgment.get("summary_task_id") not in summaries:
                excluded.append({"judgment_id": jid, "reason": "NO_CURRENT_VERIFIED_SUMMARY"})
                continue
            try:
                value = {key: judgment[key] for key in Judgment.model_fields if key in judgment}
                context = work_context(store, run_id, work["work_id"], plan)
                checked = gate_judgment(cases[work["representative_case_id"]], snapshot, value, context=context)
            except (ValueError, KeyError) as exc:
                excluded.append({"judgment_id": jid, "reason": "INVALID_JUDGMENT: " + str(exc)})
                continue
            if checked.get("case_attribution") == "MISMATCH" or checked.get("event_relation") == "DIFFERENT_EVENT":
                excluded.append({"judgment_id": jid, "reason": "OTHER_EVENT_OR_ATTRIBUTION_MISMATCH"})
                continue
            if checked.get("processing_status") != "AUTO_PROCESSED":
                excluded.append({"judgment_id": jid, "reason": "FACT_COMPARISON_NOT_RESOLVED"})
                continue
            issue = checked.get("applicable_issue") or {}
            for fid, fact in facts.items():
                if (fact["summary_task_id"] != judgment["summary_task_id"] or fact["issue_label"] != issue.get("label")
                        or not _within(fact["evidence"], issue.get("evidence", []))):
                    continue
                selected_facts.add(fid)
                if (fact["field"].strip().casefold() in ROOT_FIELDS
                        and checked.get("claim_support", {}).get("root_cause") in {"SUPPORTED", "PARTIAL"}):
                    candidates.append({"fact_id": fid, "judgment_id": jid, "issue_label": fact["issue_label"],
                        "value": fact["value"], "evidence": fact["evidence"], "url": snapshot["url"],
                        "snapshot_id": sid, "status": "ROOT_CAUSE_CANDIDATE", "human_accepted": False,
                        "claim_support": checked["claim_support"]["root_cause"],
                        "event_relation": checked["event_relation"], "observation_scope": "CAPTURED_CONTENT"})
        if not candidates:
            work_gaps.append("ROOT_CAUSE_UNCONFIRMED")
        labels = work["issue_scope"].get("applicable_issue_ids", [])
        works.append({**work, "independent_fact_ids": sorted(selected_facts),
            "resource_summary_card_ids": [card["card_id"] for card in summary_cards
                if card["snapshot_id"] == sid and (not labels or card["issue_label"] in labels)],
            "root_cause_status": "ROOT_CAUSE_CANDIDATE" if candidates else "ROOT_CAUSE_UNCONFIRMED",
            "root_cause_candidates": candidates, "excluded_results": excluded, "gaps": sorted(set(work_gaps))})

    resources = []
    discovered = []
    resource_plan = {resource["url"]: {**resource} for resource in plan["fetch_work_items"]}
    # A user-confirmed snapshot may have no imported reference occurrence.
    # It still requires a resource entry and must keep its independent facts.
    for work in plan["work_items"]:
        snapshot = snapshots[work["snapshot_id"]]
        resource = resource_plan.setdefault(snapshot["url"], {"url": snapshot["url"],
            "snapshot_id": snapshot["snapshot_id"], "fetch_id": "resource-" + digest(snapshot["url"])[:24],
            "ref_ids": [], "case_ids": [], "required": False, "retrieval_status": snapshot["status"]})
        resource["case_ids"] = sorted(set(resource["case_ids"]) | set(work["case_ids"]))
    for resource in sorted(resource_plan.values(), key=lambda item: item["url"]):
        snapshot = snapshots.get(resource.get("snapshot_id"))
        parsed = urlsplit(resource["url"])
        code_change = bool(re.search(r"/(?:pulls?|commits?)/", parsed.path))
        requested = ["body", "discussion", "linked_issues"] + (["file_list", "diff"] if code_change else [])
        capture_gaps = []
        integrity_errors = store.verify_snapshot(snapshot) if snapshot else ["SNAPSHOT_NOT_AVAILABLE"]
        valid = bool(snapshot and not integrity_errors)
        if not valid:
            capture_gaps.append("SNAPSHOT_NOT_AVAILABLE_OR_INVALID")
        elif snapshot.get("status") not in READABLE:
            capture_gaps.append("CAPTURE_BLOCKED: " + snapshot["status"])
        else:
            capture_gaps.extend("CAPTURE_COMPONENT_NOT_CONFIRMED: " + component for component in requested
                if snapshot.get("components", {}).get(component) not in {"COMPLETE", "NOT_APPLICABLE"})
            if snapshot["status"] != "COMPLETE":
                capture_gaps.append("PARTIAL_CAPTURE_RETAINED_NO_ABSENCE_INFERENCE")
            discovered.extend(_linked_resources(snapshot))
        current_summary_ids = sorted(task_id for task_id, summary in summaries.items()
                                     if snapshot and summary["snapshot_id"] == snapshot["snapshot_id"])
        resource_cards = [card["card_id"] for card in summary_cards
                          if snapshot and card["snapshot_id"] == snapshot["snapshot_id"]]
        resources.append({**resource, "requested_capture_scope": requested,
            "read_priority": 1 if _public_repository_url(resource["url"]) else 2,
            "summary_requirements": {"fields": list(SUMMARY_CARD_FIELDS), "separate_issues": True,
                "source_priority": ["AUTHOR_BODY", "EXPLICITLY_LINKED_ISSUE", "NECESSARY_FIX_DIFF"],
                "label_author_statement_vs_code_inference": True,
                "preserve_units_and_execution_phase": True,
                "verification_actor_must_be_reported_without_invention": True,
                "robot_summary_is_not_independent_root_cause_evidence": True},
            "summary_reading_scope": {"scope": "CAPTURED_CONTENT",
                "segment_ids": [segment["segment_id"] for segment in snapshot.get("segments", [])] if valid else [],
                "captured_chars": len(snapshot.get("text", "")) if valid else 0,
                "capture_status": snapshot["status"] if snapshot else "NOT_FETCHED"},
            "summary_status": ("CURRENT_CITED_SUMMARY" if resource_cards else "CURRENT_SUMMARY_NO_ISSUES")
                              if current_summary_ids else "SUMMARY_REQUIRED",
            "summary_task_ids": current_summary_ids, "resource_summary_card_ids": resource_cards,
            "capture_status": snapshot["status"] if snapshot else "NOT_FETCHED",
            "snapshot_integrity_verified": valid,
            "snapshot_integrity_errors": integrity_errors,
            "captured_components": snapshot.get("components", {}) if snapshot else {},
            "independent_fact_ids": sorted(fid for fid, fact in facts.items() if snapshot and fact["snapshot_id"] == snapshot["snapshot_id"]),
            "gaps": sorted(set(capture_gaps)), "actor": "EXTERNAL_AGENT",
            "action": "VERIFY_CAPTURE_SCOPE_AND_SUMMARIZE" if valid and snapshot.get("status") in READABLE else "FETCH_OR_REPAIR_CAPTURE"})

    work_by_id = {item["work_id"]: item for item in works}
    refs_by_id = {ref["ref_id"]: ref for ref in store.records(run_id, "references")}
    output_cases = []
    for row in plan["cases"]:
        case_works = [work_by_id[wid] for wid in row["work_ids"]]
        candidates = [{"work_id": work["work_id"], **candidate} for work in case_works for candidate in work["root_cause_candidates"]]
        public_urls = {refs_by_id[ref_id]["url"] for ref_id in row["selected_ref_ids"]
            if ref_id in refs_by_id and refs_by_id[ref_id].get("status") == "PARSED"
            and _public_repository_url(refs_by_id[ref_id].get("url"))}
        public_urls.update(snapshots[sid]["url"] for sid in row["selected_snapshot_ids"]
            if sid in snapshots and _public_repository_url(snapshots[sid]["url"]))
        output_cases.append({**row, "source_case": cases[row["case_id"]],
            "priority_repository_urls": sorted(public_urls),
            "source_root_cause_is_verified": False,
            "source_root_cause_notice": "IMPORTED_ATTRIBUTION_ONLY_NOT_VERIFIED_BY_THIS_PLAN",
            "root_cause_status": "ROOT_CAUSE_CANDIDATE" if candidates else "ROOT_CAUSE_UNCONFIRMED",
            "root_cause_candidates": candidates,
            "gaps": sorted(set([item["code"] if isinstance(item, dict) else item for item in row.get("issues", [])]
                               + ([] if candidates else ["ROOT_CAUSE_UNCONFIRMED"]))),
            "agent_next_steps": ["READ_ALL_SELECTED_RESOURCES_WITH_DISCUSSION_AND_APPLICABLE_FIX",
                "INDEPENDENTLY_SUMMARIZE_EACH_RESOURCE_WITH_EXACT_QUOTES", "COMPARE_APPLICABLE_ISSUE_FACTS_AND_RUN_BOUNDED_SELF_CHECK"]
                + (["SEARCH_UNTIL_CURRENT_POLICY_SATISFIED"] if row["search_control"]["search_allowed"] else ["DO_NOT_EXPAND_SEARCH"])})
    selected_sids = {resource["snapshot_id"] for resource in resources if resource.get("snapshot_id")}
    suggested_order = sorted(output_cases, key=lambda case: (not bool(case["priority_repository_urls"]),
        case["source_case"].get("external_id") or case["case_id"], case["case_id"]))
    return {"schema_version": "1.0", "kind": "INVESTIGATION_PLAN", "run_id": run_id,
        "policy_version": plan["policy_version"], "evidence_plan_hash": plan["plan_hash"],
        "read_only": True, "network_owner": "EXTERNAL_OPENCODE_OR_CODEX_AGENT",
        "ignored_empty_reference_ids": plan.get("ignored_empty_reference_ids", []),
        "cases": output_cases, "resources": resources, "work_items": works,
        "priority_case_ids": [case["case_id"] for case in suggested_order if case["priority_repository_urls"]],
        "suggested_execution_order": [case["case_id"] for case in suggested_order],
        "resource_summary_cards": [card for card in summary_cards if card["snapshot_id"] in selected_sids],
        "independent_technical_facts": sorted((fact for fact in facts.values() if fact["snapshot_id"] in selected_sids), key=lambda fact: fact["fact_id"]),
        "linked_resource_candidates": sorted(discovered, key=lambda item: (item["url"], item["parent_snapshot_id"])),
        "limitations": ["MODEL_FACTS_AND_CAUSES_ARE_PROPOSALS_NOT_HUMAN_ACCEPT",
            "EXACT_QUOTES_ESTABLISH_TRACEABILITY_NOT_SEMANTIC_TRUTH", "PARTIAL_CAPTURE_DOES_NOT_PROVE_ABSENCE",
            "LINK_TITLE_IMPORTED_CAUSE_AND_OTHER_EVENT_FACTS_NEVER_CONFIRM_CASE_ROOT_CAUSE"]}
