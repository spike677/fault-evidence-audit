"""Wiki-first checks for the structured XLSX workflow.

This module plans work and records declared search attempts. It does not fetch
pages, invoke a model, create human reviews or change the global search policy.
"""
from __future__ import annotations

from datetime import datetime

from .capture_quality import capture_quality
from .evidence_plan import (TABLE_GRADES, _search_usable, _trigger_source_relations,
                            collection_source_policy, resource_kind, source_relation)
from .resource_identity import resource_key, snapshot_index
from .store import AuditError, Store, canonical_url, digest, now

RULE_VERSION = "wiki-check-2"
READABLE = {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"}


def requires_body_observation(store: Store, run_id: str) -> bool:
    config = store.get(run_id, "xlsx_workflow", "config")
    return bool(config and config.get("capture_quality_required", True))


def _inputs(store: Store, run_id: str, case: dict | str) -> tuple[dict, dict, list[dict], list[dict]]:
    cid = case if isinstance(case, str) else case["case_id"]
    source = store.get(run_id, "cases", cid)
    if not source:
        raise AuditError("Wiki check case is outside this run")
    groups = [g for g in store.records(run_id, "event_groups") if cid in g["case_ids"] and g.get("user_confirmed")]
    members = {cid} | {member for group in groups for member in group["case_ids"]}
    cases = {c["case_id"]: c for c in store.records(run_id, "cases") if c["case_id"] in members}
    refs = [r for r in store.records(run_id, "references") if r["case_id"] in members]
    supplied = [r for r in refs if r.get("discovered_by") == "importer"
                or source_relation(cases[r["case_id"]], r)["relation"] in TABLE_GRADES]
    associations = [a for a in store.records(run_id, "evidence_associations") if a["case_id"] in members]
    identity = {"rule_version": RULE_VERSION, "cases": cases, "supplied_references": supplied,
                "groups": groups, "associations": associations,
                "capture_quality_required": requires_body_observation(store, run_id)}
    collection_policy = collection_source_policy(store, run_id)
    if collection_policy["explicit_override"]:
        identity["collection_policy_hash"] = collection_policy["policy_hash"]
    return source, {"input_hash": digest(identity), "cases": cases, "associations": associations,
                    "domain_source_relations": _trigger_source_relations(store, run_id),
                    "collection_source_policy": collection_policy}, refs, supplied


def _materials(store: Store, run_id: str, source: dict, context: dict, refs: list[dict], supplied: list[dict]) -> list[dict]:
    from .pipeline import current_judgments

    active = {snap["snapshot_id"]: snap for snap in store.active_snapshots(run_id)}
    by_url = snapshot_index(list(active.values()))
    original_ids = {ref["ref_id"] for ref in supplied}
    associations = context["associations"]
    domain_relations = context["domain_source_relations"]
    judgments = current_judgments(store, run_id)
    all_cases = {case["case_id"]: case for case in store.records(run_id, "cases")}
    materials = {}
    for ref in refs:
        if resource_kind(ref, case=all_cases[ref["case_id"]]) != "WIKI":
            continue
        url = canonical_url(ref["url"]) if ref.get("url") else None
        key = resource_key(url) if url else ref["ref_id"]
        snapshot = by_url.get(key)
        item = materials.setdefault(key, {"url": url, "ref_ids": [], "snapshot": snapshot, "supplied": False,
            "confirmed": False, "usable": False, "excluded": False})
        item["ref_ids"].append(ref["ref_id"])
        item["supplied"] |= ref["ref_id"] in original_ids
        item["confirmed"] |= any(a.get("ref_id") == ref["ref_id"] or snapshot
            and a.get("snapshot_id") == snapshot["snapshot_id"] for a in associations)
    # Explicitly confirmed snapshots need not have an imported reference.
    for association in associations:
        snapshot = active.get(association.get("snapshot_id"))
        if snapshot and resource_kind(snapshot=snapshot) == "WIKI":
            item = materials.setdefault(resource_key(snapshot["url"]), {"url": snapshot["url"], "ref_ids": [],
                "snapshot": snapshot, "supplied": False, "confirmed": False, "usable": False, "excluded": False})
            item["confirmed"] = True
    for item in materials.values():
        snapshot = item["snapshot"]
        item["capture_readable"] = bool(snapshot and snapshot["status"] in READABLE and snapshot["text"].strip()
                                        and not store.verify_snapshot(snapshot))
        quality = capture_quality(snapshot, require_observation=requires_body_observation(store, run_id)) if snapshot else None
        item["capture_quality"] = quality
        item["readable"] = bool(item["capture_readable"] and quality["usable_body"])
        item["domain_source_relation"] = None
        item["assessment_complete"] = False
        if snapshot:
            relevant = [j for j in judgments if j["snapshot_id"] == snapshot["snapshot_id"]
                        and source["case_id"] in j.get("member_case_ids", [j["case_id"]])
                        and j.get("review_status") != "REJECT"]
            item["excluded"] = any(j.get("case_attribution") == "MISMATCH" or j.get("event_relation") == "DIFFERENT_EVENT"
                                   for j in relevant)
            domain_relation = domain_relations.get((source["case_id"], snapshot["snapshot_id"]))
            item["domain_source_relation"] = domain_relation
            item["excluded"] |= domain_relation == "NOT_RELATED"
            item["assessment_complete"] = bool(item["readable"] and not item["supplied"] and not item["confirmed"]
                and domain_relation in {"MATCH", "PARTIAL", "UNKNOWN", "NOT_RELATED", "SUPPLIED_IDENTIFIER"})
            item["usable"] = item["readable"] and not item["excluded"] and (
                item["supplied"] or item["confirmed"] or domain_relation in {"MATCH", "SUPPLIED_IDENTIFIER"}
                or _search_usable(source, snapshot, judgments, all_cases))
    return sorted(materials.values(), key=lambda item: (not item["supplied"], item["url"] or ""))


def wiki_plan(store: Store, run_id: str, case: dict | str) -> dict:
    """Read-only preflight. A missing Wiki requires a check, not endless search."""
    source, context, refs, supplied = _inputs(store, run_id, case)
    materials = _materials(store, run_id, source, context, refs, supplied)
    records = [record for record in store.records(run_id, "wiki_checks")
               if record["case_id"] == source["case_id"] and record["input_hash"] == context["input_hash"]]
    latest = max(records, key=lambda record: record["revision"], default={})
    usable = [item for item in materials if item["usable"]]
    pending = [item for item in materials if not item["excluded"] and not item["usable"] and not item["assessment_complete"]]
    domain_assessments = [{"snapshot_id": item["snapshot"]["snapshot_id"], "source_relation": item["domain_source_relation"]}
        for item in materials if item["snapshot"] and item["domain_source_relation"]]
    actions = []
    collection_policy = context["collection_source_policy"]
    unsupported = collection_policy["explicit_override"] and "WIKI" not in collection_policy["collection_sources"]
    if unsupported:
        status = "NOT_SUPPORTED"
        reason = ("Explicit run collection policy: Wiki is unavailable; "
                  f"wiki_policy={collection_policy['wiki_policy']}; "
                  f"collection_sources={','.join(collection_policy['collection_sources'])}; "
                  f"{collection_policy['reason']}")
        latest = {}
        pending = []
    elif usable:
        status, reason = "FOUND", "Existing readable supplied/confirmed Wiki or currently verified discovery; no additional Wiki search"
    elif pending:
        repair = [item for item in pending if item["capture_readable"] and not item["readable"]
                  and item["capture_quality"]["needs_repair"]]
        broken = [item for item in pending if item["snapshot"] and (
            item["snapshot"]["status"] not in READABLE or not item["readable"])]
        unread = [item for item in pending if not item["snapshot"]]
        if repair:
            status, reason = "FETCH_REQUIRED", "Wiki body quality is unconfirmed; repair the original capture/navigation before searching"
            actions = [{"action": "REPAIR_WIKI_CAPTURE", "url": item["url"], "ref_ids": item["ref_ids"],
                        "snapshot_id": item["snapshot"]["snapshot_id"], "page_kind": item["capture_quality"]["status"]}
                       for item in repair]
        elif broken:
            status, reason = "BLOCKED", "Wiki capture is blocked or invalid; retain the gap and continue other materials"
        elif unread:
            status, reason = "FETCH_REQUIRED", "Read the supplied/existing Wiki before searching for more"
            actions = [{"action": "FETCH_WIKI", "url": item["url"], "ref_ids": item["ref_ids"]} for item in unread]
        else:
            status, reason = "CANDIDATE_PENDING", "Wiki candidate captured; summarize and compare before accepting its association"
            actions = [{"action": "VERIFY_WIKI", "snapshot_id": item["snapshot"]["snapshot_id"]} for item in pending]
    elif latest.get("outcome") in {"NO_MATCH", "BLOCKED"}:
        status, reason = latest["outcome"], latest["reason"]
    else:
        status, reason = "SEARCH_REQUIRED", "No applicable Wiki; execute a bounded Wiki search even when other sources exist"
        actions = [{"action": "SEARCH_WIKI", "case_id": source["case_id"],
                    "scope": "WIKI", "query_planning": "AGENT_SOURCE_GROUNDED_FACETS"}]
    snapshots = sorted({item["snapshot"]["snapshot_id"] for item in materials if item["snapshot"] and not item["excluded"]})
    task_identity = {"input": context["input_hash"], "status": status,
                     "snapshots": snapshots, "check_id": latest.get("check_id")}
    if domain_assessments:
        task_identity["domain_source_assessments"] = domain_assessments
    result = {"case_id": source["case_id"], "status": status, "checked": status in {"FOUND", "NO_MATCH"},
            "search_allowed": status == "SEARCH_REQUIRED", "input_hash": context["input_hash"],
            "task_id": "wiki-" + digest(task_identity)[:24],
            "required_actions": actions, "wiki_ref_ids": sorted({rid for item in materials for rid in item["ref_ids"]}),
            "wiki_snapshot_ids": snapshots, "check_id": latest.get("check_id"), "reason": reason,
            "query": latest.get("query", ""), "scope": latest.get("scope", ""),
            "checked_at": latest.get("checked_at", ""), "executed_by": latest.get("executed_by", ""),
            "domain_source_assessments": domain_assessments,
            "excluded_source_snapshot_ids": sorted(item["snapshot_id"] for item in domain_assessments if item["source_relation"] == "NOT_RELATED"),
            "insufficient_source_snapshot_ids": sorted(item["snapshot_id"] for item in domain_assessments if item["source_relation"] in {"PARTIAL", "UNKNOWN"}),
            "capture_quality_gaps": [{"url": item["url"], "snapshot_id": item["snapshot"]["snapshot_id"],
                "page_kind": item["capture_quality"]["status"], "needs_repair": item["capture_quality"]["needs_repair"],
                "errors": item["capture_quality"]["errors"]} for item in pending if item["snapshot"] and not item["readable"]],
            "case_root_cause_confirmed": False}
    if collection_policy["explicit_override"]:
        result["collection_source_policy"] = collection_policy
        result["unavailable_references"] = [{"ref_ids": item["ref_ids"], "url": item["url"],
            "snapshot_id": item["snapshot"]["snapshot_id"] if item["snapshot"] else None,
            "resource_kind": "WIKI", "status": "NOT_SUPPORTED", "reason": collection_policy["reason"]}
            for item in materials] if unsupported else []
    return result


def record_wiki_check(store: Store, run_id: str, case_id: str, *, outcome: str,
                      query: str = "", scope: str = "", checked_at: str = "", executed_by: str = "",
                      executed: bool = False, snapshot_id: str | None = None, reason: str = "") -> dict:
    """Append an idempotent search/read declaration; FOUND may remain pending."""
    source, context, refs, supplied = _inputs(store, run_id, case_id)
    policy = context["collection_source_policy"]
    if policy["explicit_override"] and "WIKI" not in policy["collection_sources"]:
        raise AuditError("Wiki is NOT_SUPPORTED by the explicit run collection policy; no check was performed")
    if outcome not in {"FOUND", "NO_MATCH", "BLOCKED"}:
        raise AuditError("Wiki outcome must be FOUND, NO_MATCH or BLOCKED")
    materials = _materials(store, run_id, source, context, refs, supplied)
    if outcome == "FOUND":
        matched = [item for item in materials if item["snapshot"] and item["snapshot"]["snapshot_id"] == snapshot_id
                   and item["readable"] and not item["excluded"]]
        if not matched:
            raise AuditError("FOUND requires a current readable Wiki snapshot linked to this case")
        snapshot = matched[0]["snapshot"]
        checked_at = checked_at or snapshot["retrieved_at"]
        executed_by = executed_by or snapshot["retrieved_by"]
        reason = reason or "Wiki captured; association remains subject to the existing comparison gate"
    else:
        if executed is not True or not all(isinstance(value, str) and value.strip()
            for value in (query, scope, checked_at, executed_by, reason)):
            raise AuditError("NO_MATCH/BLOCKED requires actual execution, query, scope, time, actor and reason")
        try:
            timestamp = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("timezone missing")
        except ValueError as exc:
            raise AuditError("Wiki check time must be an ISO timestamp with timezone") from exc
        if outcome == "NO_MATCH" and any(not item["excluded"] and not (item["assessment_complete"] and not item["usable"])
                                         for item in materials):
            raise AuditError("Cannot report NO_MATCH while an existing Wiki is pending or available")
    identity = {"case_id": case_id, "input_hash": context["input_hash"], "outcome": outcome,
                "query": query, "scope": scope, "checked_at": checked_at, "executed_by": executed_by,
                "executed": executed if outcome != "FOUND" else True, "snapshot_id": snapshot_id, "reason": reason}
    check_id = "wiki-check-" + digest(identity)[:24]
    existing = store.get(run_id, "wiki_checks", check_id)
    if existing:
        return existing
    previous = [record for record in store.records(run_id, "wiki_checks") if record["case_id"] == case_id]
    record = {"check_id": check_id, **identity,
              "revision": max((record["revision"] for record in previous), default=0) + 1, "recorded_at": now()}
    store.put(run_id, "wiki_checks", check_id, record)
    store.event(run_id, "wiki_check_recorded", record)
    return record
