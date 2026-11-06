"""Deterministic orchestration; model proposals never bypass evidence gates."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from .contracts import EvidenceSummary, Judgment
from .gates import event_anchor_errors, judgment_semantic_errors, processing_decision
from .store import AuditError, Store, canonical_url, digest
from .resource_identity import resource_key, resource_url, snapshot_index, same_resource

RULE_VERSION = "nightly-0.1.12"


def cited_refs(summary: dict):
    for issue in summary.get("issues", []):
        for ref in issue.get("evidence", issue.get("evidence_refs", [])):
            yield ref
        for fact in issue.get("facts", []):
            yield from fact.get("evidence", fact.get("evidence_refs", []))


def check_citations(refs: list[dict], snapshot: dict) -> list[str]:
    segments = {s["segment_id"]: s for s in snapshot["segments"]}
    errors = []
    for ref in refs:
        segment = segments.get(ref.get("segment_id"))
        quote = ref.get("quote", "")
        if not segment or not quote.strip() or quote not in segment["text"]:
            errors.append("Citation is absent from its declared snapshot segment")
    return errors


def gate_judgment(case: dict, snapshot: dict, value: dict, *, context: dict | None = None) -> dict:
    result = Judgment.model_validate(value).model_dump()
    errors = []
    if result["case_id"] != case["case_id"] or result["snapshot_id"] != snapshot["snapshot_id"]:
        errors.append("Model returned a different case_id or snapshot_id")
    errors.extend(check_citations(result["evidence"], snapshot))
    errors.extend(judgment_semantic_errors(case, snapshot, result))
    chosen_issue = result.get("applicable_issue") or {}
    known_labels = snapshot.get("summary_issue_labels") or []
    if chosen_issue and known_labels and chosen_issue.get("label") not in known_labels:
        errors.append("Applicable issue must identify a subproblem from the independent summary")
    scope = (context or {}).get("applicable_issue") or {}
    if isinstance(scope, dict) and scope.get("applicable_issue_ids") and chosen_issue.get("label") not in scope["applicable_issue_ids"]:
        errors.append("Fact comparison must stay within the explicitly selected applicable issue")
    positive = result["case_attribution"] == "CONFIRMED" or result["support_level"] == "DIRECT"
    if any(v in {"SUPPORTED", "PARTIAL", "CONTRADICTED"} for v in result.get("claim_support", {}).values()) and not result["evidence"]:
        errors.append("Claim support requires cited text")
    if result["event_relation"] == "SAME_EVENT" or positive:
        errors.extend(event_anchor_errors(case, snapshot, result))
    if positive and result["event_relation"] != "SAME_EVENT":
        errors.append("Direct/confirmed attribution requires a same-event result")
    if positive and snapshot["status"] != "COMPLETE":
        errors.append("Partial or failed retrieval cannot establish overall direct attribution")
    if positive and snapshot.get("derived_from"):
        errors.append("Derived evidence cannot independently confirm this event")
    if positive and result["model_mode"] == "mock":
        errors.append("Mock results cannot establish direct attribution")
    if errors:
        raise AuditError("; ".join(dict.fromkeys(errors)))
    decision = processing_decision(case, snapshot, result, context or {})
    result.update(decision)
    result["review_status"] = "NEEDS_REVIEW" if decision["review_required"] else "NOT_REQUIRED" if decision["processing_status"] == "AUTO_PROCESSED" else "PENDING_AGENT"
    result["rule_version"] = RULE_VERSION
    return result


def check_catalog_import(store: Store, run_id: str | None, result: dict) -> dict:
    """Validate the whole selection before writing cases or catalog records."""
    items = result.get("items", [])
    hashes = {item["source_sha256"] for item in items}
    if len(hashes) != 1:
        raise AuditError("Catalog must contain items from exactly one source file")
    item_ids = [item["item_id"] for item in items]
    if len(set(item_ids)) != len(item_ids):
        raise AuditError("Duplicate catalog item IDs; select one scope or fix the catalog")
    identity = result.get("catalog_identity") or {
        "source_sha256": next(iter(hashes)),
        "sheets": sorted({item.get("sheet", "") for item in items}),
        "scope": "UNSPECIFIED",
    }
    if identity.get("source_sha256") != next(iter(hashes)):
        raise AuditError("Catalog selection does not match its source hash")
    if run_id is None:
        return identity
    old = store.records(run_id, "catalog")
    frozen = store.get(run_id, "catalog_selections", "frozen")
    if old and not frozen:
        raise AuditError("Existing catalog predates selection metadata; use a new run for catalog import")
    if frozen and frozen != identity:
        raise AuditError("Catalog file, sheets and scope are frozen within a run; use a new run for another selection")
    if old and {item["item_id"] for item in old} != set(item_ids):
        raise AuditError("Catalog item set is frozen within a run; use a new run")
    for item in items:
        existing = store.get(run_id, "catalog", item["item_id"])
        if existing is not None and existing != item:
            raise AuditError("Immutable catalog item differs; use a new run")
    return identity


def import_into(store: Store, run_id: str, result: dict, catalog: bool = False) -> dict:
    counts = {}
    identity = check_catalog_import(store, run_id, result) if catalog else None
    keys = {"cases": "cases", "references": "references", "exclusions": "exclusions",
            "documents": "documents", "items": "catalog"}
    for source, kind in keys.items():
        values = result.get(source, [])
        if isinstance(values, dict):
            values = [values]
        counts[kind] = len(values)
        if kind == "catalog" and len({v["item_id"] for v in values}) != len(values):
            raise AuditError("Duplicate catalog item IDs; fix the catalog instead of overwriting entries")
        for i, value in enumerate(values):
            primary = {"cases": "case_id", "references": "ref_id", "catalog": "item_id",
                       "documents": "document_id", "exclusions": "exclusion_id"}[kind]
            key = str(value[primary]) if value.get(primary) else digest(value)[:24]
            store.put(run_id, kind, key, value)
    for warning in result.get("warnings", []):
        store.event(run_id, "import_warning", {"warning": warning})
    if identity is not None:
        store.put(run_id, "catalog_selections", "frozen", identity)
    store.event(run_id, "catalog_imported" if catalog else "cases_imported", {"counts": counts})
    return counts


def associations(store: Store, run_id: str) -> tuple[list[tuple[dict, dict]], list[dict]]:
    cases = {c["case_id"]: c for c in store.records(run_id, "cases")}
    by_url = snapshot_index(store.active_snapshots(run_id))
    pairs, missing, seen = [], [], set()
    for ref in store.records(run_id, "references"):
        try:
            snapshot = by_url.get(resource_key(ref["url"])) if ref.get("url") and ref.get("status") == "PARSED" else None
        except AuditError:
            snapshot = None
        if not snapshot:
            missing.append(ref)
            continue
        key = (ref["case_id"], snapshot["snapshot_id"])
        if key not in seen and ref["case_id"] in cases:
            pairs.append((cases[ref["case_id"]], snapshot))
            seen.add(key)
    return pairs, missing


def evidence_plan(store: Store, run_id: str) -> dict:
    from .evidence_plan import build_evidence_plan
    judgments = current_judgments(store, run_id)
    plan = build_evidence_plan(store, run_id, judgments=judgments)
    summaries = {summary["snapshot_id"]: summary["task_id"] for summary in current_summaries(store, run_id)}
    for row in plan["cases"]:
        row["reusable_summary_ids"] = [summaries[sid] for sid in row["selected_snapshot_ids"] if sid in summaries]
        applicable = [j for j in judgments if row["case_id"] in j.get("member_case_ids", [j["case_id"]])
                      and j.get("work_id") in row["work_ids"]
                      and (not j.get("processing_context") or digest(j["processing_context"]) == digest(
                          work_context(store, run_id, j["work_id"], plan)))]
        processed = {j.get("work_id") for j in applicable if j.get("processing_status") == "AUTO_PROCESSED" and j.get("review_status") != "REJECT"}
        row["processing_status"] = "AUTO_PROCESSED" if row["work_ids"] and set(row["work_ids"]).issubset(processed) else "EXCEPTION" if row["path"] == "EXCEPTION" else "PENDING"
        if row["processing_status"] == "AUTO_PROCESSED" and not any(
                action["action"] not in {"EXTRACT_FACTS", "REUSE_PROCESSED_FACTS"} for action in row["required_actions"]):
            row["required_actions"] = [{"action": "REUSE_PROCESSED_FACTS", "judgment_ids": [j["judgment_id"] for j in applicable]}]
    return plan


def planned_work(store: Store, run_id: str, plan: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Keep the precise work identity, including applicable subproblem scope."""
    plan = plan or evidence_plan(store, run_id)
    snapshots = {s["snapshot_id"]: s for s in store.active_snapshots(run_id)}
    work = [item for item in plan["work_items"] if item.get("snapshot_id") in snapshots]
    selected = {ref_id for item in plan["cases"] for ref_id in item["selected_ref_ids"]}
    available = {resource_key(s["url"]) for s in snapshots.values() if s["status"] in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"} and s["text"].strip()}
    missing = [r for r in store.records(run_id, "references") if r["ref_id"] in selected
               and (r.get("status") != "PARSED" or not r.get("url") or resource_key(r["url"]) not in available)]
    return work, missing


def planned_associations(store: Store, run_id: str, plan: dict | None = None) -> tuple[list[tuple[dict, dict]], list[dict]]:
    """Compatibility view for callers; execution always uses planned_work."""
    work, missing = planned_work(store, run_id, plan)
    cases = {case["case_id"]: case for case in store.records(run_id, "cases")}
    snapshots = {snapshot["snapshot_id"]: snapshot for snapshot in store.active_snapshots(run_id)}
    return [(cases[item["representative_case_id"]], snapshots[item["snapshot_id"]]) for item in work], missing


def work_context(store: Store, run_id: str, work_id: str, plan: dict) -> dict:
    from .evidence_plan import get_search_policy
    matches = [item for item in plan["work_items"] if item["work_id"] == work_id]
    if len(matches) != 1:
        raise AuditError("Evidence work is absent or ambiguous in the current plan: " + work_id)
    work = matches[0]
    refs = [ref for ref in store.records(run_id, "references") if ref["ref_id"] in work["ref_ids"]]
    cases = [case for case in store.records(run_id, "cases") if case["case_id"] in work["case_ids"]]
    search_policies = {}
    for case in cases:
        policy = get_search_policy(store, run_id, case["case_id"])
        search_policies[case["case_id"]] = {"policy": policy["policy"], "policy_hash": policy["policy_hash"]}
    # Routing identity excludes completion/stop wording so consuming a result does not create another task.
    return {"source_relation": work["relation"], "source_grades": work.get("source_grades", [work["relation"]]),
            "user_confirmed": work.get("user_confirmed", False), "selected_ref_ids": work["ref_ids"],
            "association_ids": work.get("association_ids", []), "group_confirmation": work.get("group_confirmation"),
            "member_source_grades": work.get("member_source_grades", {}),
            "member_user_confirmed": work.get("member_user_confirmed", {}),
            "source_trace": work.get("provenance", []),
            "provenance": refs, "source_records": cases, "member_case_ids": work["case_ids"],
            "group_id": work.get("group_id"),
            "search_policies": search_policies,
            "applicable_issue": work.get("issue_scope", {}), "work_id": work["work_id"],
            "plan_hash": work["work_id"], "processing_version": "evidence-first-0.1.8"}


def task_views(store: Store, run_id: str, plan: dict | None = None) -> list[dict]:
    from .bridge import policy_fingerprint
    plan = plan or evidence_plan(store, run_id)
    selected_sids = {sid for item in plan["cases"] for sid in item["selected_snapshot_ids"]}
    selected_refs = {rid for item in plan["cases"] for rid in item["selected_ref_ids"]}
    fetch_targets = {fetch_resource_id(ref["url"]) for ref in store.records(run_id, "references")
                     if ref["ref_id"] in selected_refs and ref.get("status") == "PARSED" and ref.get("url")}
    compare_targets = {item["work_id"] for item in plan["work_items"] if item.get("snapshot_id")}
    representatives = {item["representative_case_id"] for item in plan["work_items"]}
    values = [{**task, "required": task["status"] != "STALE" and (
        task["target_id"] in selected_sids if task["kind"] == "summarize" else
        task["target_id"] in compare_targets if task["kind"] == "compare" else
        task["target_id"] in fetch_targets if task["kind"] == "fetch" else
        task["target_id"] in representatives if task["kind"] == "catalog" else False)} for task in store.tasks(run_id)]
    policy = policy_fingerprint()
    requests = store.records(run_id, "model_tasks")
    work_ids = {item["work_id"] for item in plan["work_items"]}
    for task in values:
        bound = [request for request in requests if request["pipeline_task_id"] == task["task_id"]]
        if bound and not any(request["policy_hash"] == policy for request in bound):
            task["required"] = False
        if task["kind"] == "compare" and bound and not any(
                request["policy_hash"] == policy and request["payload"].get("processing_context", {}).get("work_id") in work_ids
                and digest(request["payload"]["processing_context"]) == digest(work_context(
                    store, run_id, request["payload"]["processing_context"]["work_id"], plan)) for request in bound):
            task["required"] = False
    return values


def fetch_resource_id(url: str) -> str:
    return "resource-" + digest(resource_key(url))[:24]


def necessary_judgments(store: Store, run_id: str, plan: dict | None = None, **filters) -> list[dict]:
    plan = plan or evidence_plan(store, run_id)
    work_ids = {item["work_id"] for item in plan["work_items"]}
    return [j for j in current_judgments(store, run_id, **filters)
            if j.get("work_id") in work_ids and (not j.get("processing_context") or
                digest(j["processing_context"]) == digest(work_context(store, run_id, j["work_id"], plan)))]


def fetch_tasks(store: Store, run_id: str, *, include_unselected: bool = False) -> dict:
    plan = evidence_plan(store, run_id)
    selected = {rid for case in plan["cases"] for rid in case["selected_ref_ids"]}
    by_url = snapshot_index(store.active_snapshots(run_id))
    grouped = {}
    malformed = []
    for ref in store.records(run_id, "references"):
        if not ref.get("url") or ref.get("status") != "PARSED":
            malformed.append(ref)
            continue
        if not include_unselected and ref["ref_id"] not in selected:
            continue
        try:
            url = resource_url(ref["url"])
        except AuditError:
            malformed.append(ref)
            continue
        group = grouped.setdefault(url, {"url": url, "case_ids": [], "references": [], "original_urls": [], "retrieval_status": "NOT_FETCHED", "required": False})
        if ref["url"] not in group["original_urls"]:
            group["original_urls"].append(ref["url"])
        group["required"] = group["required"] or ref["ref_id"] in selected
        if ref["case_id"] not in group["case_ids"]:
            group["case_ids"].append(ref["case_id"])
        group["references"].append(ref)
        if url in by_url:
            group["retrieval_status"] = by_url[url]["status"]
            group["snapshot_id"] = by_url[url]["snapshot_id"]
    for group in grouped.values():
        if group["retrieval_status"] in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"} and by_url[group["url"]]["text"].strip():
            from .capture_quality import capture_quality
            cfg = store.get(run_id, "xlsx_workflow", "config")
            quality = capture_quality(by_url[group["url"]], require_observation=bool(cfg))
            group["required"] = group["required"] and not quality["usable_body"]
            group["capture_quality"] = quality
    return {"run_id": run_id, "fetch_tasks": list(grouped.values()) if include_unselected else [g for g in grouped.values() if g["required"]],
            "malformed_references": malformed, "evidence_plan": plan,
            "note": "Only required selected original links need collection. Do not search to fill fields or evidence types; use the evidence plan."}


def evidence_index(store: Store, run_id: str, url: str | None = None) -> dict:
    """Expose every citing case and its individual verdict without merging cases."""
    target = resource_key(url) if url else None
    cases = {case["case_id"]: case for case in store.records(run_id, "cases")}
    judgments = necessary_judgments(store, run_id)
    snapshots = store.records(run_id, "snapshots")
    plan = fetch_tasks(store, run_id, include_unselected=True)
    entries = []
    for group in plan["fetch_tasks"]:
        if target and group["url"] != target:
            continue
        associations = []
        for case_id in sorted(group["case_ids"]):
            case = cases.get(case_id, {})
            associations.append({
                "case_id": case_id, "external_id": case.get("external_id", ""),
                "source_file": case.get("source_file"), "sheet": case.get("sheet"), "row": case.get("row"),
                "references": [ref for ref in group["references"] if ref["case_id"] == case_id],
                "judgments": [j for j in judgments if j["case_id"] == case_id
                              and j["snapshot_id"] == group.get("snapshot_id")],
            })
        entries.append({**group, "shared_by_multiple_cases": len(associations) > 1,
                        "associations": associations,
                        "snapshot_versions": [s["snapshot_id"] for s in snapshots if same_resource(s["url"], group["url"])]})
    return {"run_id": run_id, "evidence_index": entries,
            "shared_evidence_count": sum(entry["shared_by_multiple_cases"] for entry in entries),
            "malformed_references": plan["malformed_references"],
            "note": "Shared evidence identifies records to cross-check; it does not establish a shared event or root cause."}


def _task_allowed(task: dict, retry_failed: bool):
    return task["status"] in {"PENDING", "BLOCKED", "RUNNING"} or (retry_failed and task["status"] == "FAILED")


def input_scope(snapshot: dict, segments: list[dict], *, group: bool = False) -> dict:
    """Describe exactly which captured text is supplied, including partial captures."""
    full_ids = [segment["segment_id"] for segment in snapshot["segments"]]
    selected_ids = [segment["segment_id"] for segment in segments]
    return {"scope": "SUMMARY_GROUP" if group else "FULL_CAPTURED_SNAPSHOT" if selected_ids == full_ids else "SELECTED_SEGMENTS",
            "retrieval_status": snapshot["status"], "snapshot_segment_count": len(full_ids),
            "provided_segment_ids": selected_ids, "total_chars": len(snapshot["text"]),
            "provided_chars": sum(len(segment["text"]) for segment in segments)}


def _model_failure(store: Store, run_id: str, task: dict, exc: Exception) -> None:
    if getattr(exc, "code", None) == "INPUT_TOO_LARGE":
        store.task_status(run_id, task["task_id"], "BLOCKED", "INPUT_TOO_LARGE: " + str(exc))
        store.event(run_id, "model_input_blocked", {"task_id": task["task_id"],
                                                   **getattr(exc, "details", {})})
    else:
        store.task_status(run_id, task["task_id"], "FAILED", str(exc))


def execute(store: Store, run_id: str, judge, *, mode: str, model_id: str, retry_failed: bool = False,
            summarize_only: bool = False) -> dict:
    from .bridge import policy_fingerprint
    from . import prompts, gates, contracts, model
    from . import store as store_module
    signature = {"mode": mode, "model_id": model_id, "rules": RULE_VERSION,
                 "policy_hash": policy_fingerprint(),
                 "prompt_version": prompts.PROMPT_VERSION,
                 "prompt_hash": digest(Path(prompts.__file__).read_bytes()),
                 "engine_hash": digest(b"".join(Path(module.__file__).read_bytes() for module in
                                                 (gates, contracts, model, store_module)) + Path(__file__).read_bytes()),
                 "executor_signature": getattr(judge, "execution_signature", "local-validation")}
    plan = evidence_plan(store, run_id)
    work, missing = planned_work(store, run_id, plan)
    cases_by_id = {case["case_id"]: case for case in store.records(run_id, "cases")}
    snapshots_by_id = {snapshot["snapshot_id"]: snapshot for snapshot in store.active_snapshots(run_id)}
    active = {item["snapshot_id"]: snapshots_by_id[item["snapshot_id"]] for item in work}
    missing_resources = {}
    for ref in missing:
        if ref.get("url") and ref.get("status") == "PARSED":
            target = fetch_resource_id(ref["url"])
        else:
            target = ref["ref_id"]
        missing_resources.setdefault(target, []).append(ref)
    for target, refs in missing_resources.items():
        t = store.task(run_id, "fetch", target, sorted(refs, key=lambda ref: ref["ref_id"]))
        store.task_status(run_id, t["task_id"], "BLOCKED", "Missing snapshot or malformed URL")
    # Mark previously missing references resolved as soon as evidence is supplied.
    missing_ids = set(missing_resources)
    selected_ref_ids = {rid for row in plan["cases"] for rid in row["selected_ref_ids"]}
    readable_urls = {resource_key(s["url"]) for s in store.active_snapshots(run_id) if s["status"] in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"} and s["text"].strip()}
    captured_refs = {fetch_resource_id(r["url"]) for r in store.records(run_id, "references") if r["ref_id"] in selected_ref_ids and r.get("status") == "PARSED" and r.get("url") and resource_key(r["url"]) in readable_urls}
    for task in store.tasks(run_id):
        if task["kind"] == "fetch" and task["target_id"] not in missing_ids and task["target_id"] in captured_refs:
            store.task_status(run_id, task["task_id"], "SUCCEEDED")
    for sid, snapshot in active.items():
        task = store.task(run_id, "summarize", sid, [sid, signature])
        if not _task_allowed(task, retry_failed):
            continue
        if snapshot["status"] not in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"} or not snapshot["text"].strip():
            store.task_status(run_id, task["task_id"], "BLOCKED", "Evidence body unavailable: " + snapshot["status"])
            continue
        from .capture_quality import capture_quality
        quality = capture_quality(snapshot, require_observation=bool(store.get(run_id, "xlsx_workflow", "config")))
        if not quality["usable_body"]:
            store.task_status(run_id, task["task_id"], "BLOCKED", "PAGE_BODY_UNAVAILABLE: " + quality["status"])
            continue
        store.task_status(run_id, task["task_id"], "RUNNING")
        try:
            problems = store.verify_snapshot(snapshot)
            if problems:
                raise AuditError("; ".join(problems))
            # Every segment is summarized; no silent prefix truncation.
            issues, unknown, responses = [], [], []
            groups, current = [], []
            for segment in snapshot["segments"]:
                if current and sum(len(s["text"]) for s in current) + len(segment["text"]) > 16000:
                    groups.append(current)
                    current = []
                current.append(segment)
            if current:
                groups.append(current)
            awaiting = []
            for group in groups:
                view = {**snapshot, "segments": group, "text": "".join(s["text"] for s in group),
                        "input_scope": input_scope(snapshot, group, group=len(groups) > 1)}
                judge.pipeline_task_id = task["task_id"]
                try:
                    response = EvidenceSummary.model_validate(judge.summarize(view)).model_dump()
                except model.PendingModelResult as exc:
                    awaiting.append(exc)
                    continue
                if response["snapshot_id"] != sid:
                    raise AuditError("Summary refers to a different snapshot")
                problems = check_citations(list(cited_refs(response)), snapshot)
                if problems:
                    raise AuditError("; ".join(problems))
                responses.append(response)
                issues.extend(response["issues"])
                unknown.extend(response["unknown_fields"])
            if awaiting:
                raise awaiting[0]
            actual_models = sorted({r["model_id"] for r in responses})
            if len(actual_models) != 1:
                raise AuditError("Model identity changed between summary chunks")
            value = {"snapshot_id": sid, "issues": issues, "unknown_fields": sorted(set(unknown)),
                     "model_mode": mode, "model_id": actual_models[0], "requested_model_id": model_id,
                     "blocks_processed": len(groups),
                     "segments_processed": len(snapshot["segments"]), "task_id": task["task_id"],
                     "policy_hash": signature["policy_hash"]}
            store.put(run_id, "summaries", task["task_id"], value)
            store.task_status(run_id, task["task_id"], "SUCCEEDED")
        except model.PendingModelResult as exc:
            store.task_status(run_id, task["task_id"], "PENDING", "Awaiting model executor result: " + exc.task_id)
        except Exception as exc:
            _model_failure(store, run_id, task, exc)
    summaries = {s["snapshot_id"]: s for s in current_summaries(store, run_id)
                 if s["model_mode"] == mode and s.get("requested_model_id", s["model_id"]) == model_id}
    if summarize_only:
        for call in getattr(judge, "calls", []):
            store.event(run_id, "model_bridge_event", call)
        store.event(run_id, "execution", {"mode": mode, "model_id": model_id, "rules": RULE_VERSION,
                                           "summarize_only": True})
        relevant = {"summarize": set(active), "fetch": set(missing_resources)}
        return {"run_id": run_id, "phase": "SUMMARIZE_ONLY",
                "complete": not missing_resources and set(active) <= set(summaries),
                "counts": {"snapshots": len(active), "summaries": len(set(active) & set(summaries)),
                           "missing_resources": len(missing_resources)},
                "tasks": [task for task in store.tasks(run_id)
                          if task["target_id"] in relevant.get(task["kind"], set()) and task["status"] != "STALE"]}
    for item in work:
        case = cases_by_id[item["representative_case_id"]]
        snapshot = active[item["snapshot_id"]]
        sid = snapshot["snapshot_id"]
        summary = summaries.get(sid)
        context = work_context(store, run_id, item["work_id"], plan)
        task = store.task(run_id, "compare", item["work_id"],
                          [case, sid, digest(summary) if summary else None, signature, context])
        if not _task_allowed(task, retry_failed):
            continue
        if not summary:
            store.task_status(run_id, task["task_id"], "BLOCKED", "A valid independent summary is required")
            continue
        store.task_status(run_id, task["task_id"], "RUNNING")
        try:
            # Pass all extracted facts and the original cited segments. If a model call is
            # too large it must fail visibly; the model adapter never truncates silently.
            quoted_ids = {r["segment_id"] for r in cited_refs(summary)}
            view = {**snapshot, "segments": [s for s in snapshot["segments"] if s["segment_id"] in quoted_ids
                                            or len(snapshot["text"]) <= 16000]}
            view["text"] = "".join(s["text"] for s in view["segments"])
            view["input_scope"] = input_scope(snapshot, view["segments"])
            view["summary_issue_labels"] = [issue["label"] for issue in summary["issues"]]
            summary_input = {key: summary[key] for key in EvidenceSummary.model_fields}
            judge.pipeline_task_id = task["task_id"]
            judge.processing_context = context
            value = gate_judgment(case, view, judge.compare(case, view, summary_input), context=context)
            value["judgment_id"] = task["task_id"]
            value["task_id"] = task["task_id"]
            value["requested_model_id"] = model_id
            value.update(policy_hash=signature["policy_hash"], case_hash=digest(case),
                         summary_task_id=summary["task_id"], summary_hash=digest(summary),
                         input_scope=view["input_scope"])
            value.update(processing_context=context, member_case_ids=context["member_case_ids"], work_id=context["work_id"])
            store.put(run_id, "judgments", task["task_id"], value)
            store.task_status(run_id, task["task_id"], "SUCCEEDED")
        except model.PendingModelResult as exc:
            store.task_status(run_id, task["task_id"], "PENDING", "Awaiting model executor result: " + exc.task_id)
        except Exception as exc:
            _model_failure(store, run_id, task, exc)
    items = store.records(run_id, "catalog")
    if items:
        representatives = {item["representative_case_id"] for item in plan["work_items"]}
        for case in [c for c in store.records(run_id, "cases") if c["case_id"] in representatives]:
            js = necessary_judgments(store, run_id, plan, mode=mode, model_id=model_id)
            case_judgments = [j for j in js if j["case_id"] == case["case_id"]]
            js = [j for j in case_judgments if j.get("review_status") != "REJECT"]
            task = store.task(run_id, "catalog", case["case_id"], [case, js, items, signature])
            if not _task_allowed(task, retry_failed):
                continue
            if mode in {"opencode", "codex"}:
                needed = {item["work_id"] for item in work if item["representative_case_id"] == case["case_id"]}
                ready = {j.get("work_id") for j in case_judgments}
                if not needed or not needed.issubset(ready) or any(r["case_id"] == case["case_id"] for r in missing):
                    store.task_status(run_id, task["task_id"], "BLOCKED", "Catalog waits for complete per-artifact judgments")
                    continue
            store.task_status(run_id, task["task_id"], "RUNNING")
            try:
                judge.pipeline_task_id = task["task_id"]
                result = judge.map_catalog(case, js, items)
                from .model import _validate_catalog
                result = _validate_catalog(result, case, js, items)
                expected = {i["item_id"] for i in items}
                results = result.get("catalog_results", [])
                actual = [r.get("item_id") for r in results]
                if set(actual) != expected or len(actual) != len(expected):
                    raise AuditError("Catalog result must cover each frozen item exactly once")
                if result.get("case_id") != case["case_id"] or result.get("scope") != "FULL_CATALOG":
                    raise AuditError("Catalog identity or comparison scope mismatch")
                confirmed = any(j["case_attribution"] == "CONFIRMED" and j["event_relation"] == "SAME_EVENT" for j in js)
                allowed = {"COVERED", "PARTIALLY_COVERED", "NOT_COVERED", "UNDETERMINED"}
                for item in results:
                    if item.get("result") not in allowed or not str(item.get("reason", "")).strip():
                        raise AuditError("Catalog result needs a valid result and reason")
                    if not confirmed and item["result"] != "UNDETERMINED":
                        raise AuditError("Unconfirmed incident cannot establish final catalog coverage")
                if result.get("overall") not in allowed:
                    raise AuditError("Invalid overall catalog result")
                if not confirmed and result["overall"] != "UNDETERMINED":
                    raise AuditError("Unconfirmed incident cannot establish overall catalog coverage")
                result.update({"task_id": task["task_id"], "catalog_hash": digest(items), "model_mode": mode,
                               "requested_model_id": model_id, "catalog_count": len(items), "review_status": "NEEDS_REVIEW",
                               "policy_hash": signature["policy_hash"], "case_hash": digest(case),
                               "judgments_hash": digest(js)})
                members = sorted({cid for item in plan["work_items"] if item["representative_case_id"] == case["case_id"] for cid in item["case_ids"]})
                result.update(member_case_ids=members, review_required=False, processing_status="AUTO_PROCESSED",
                              review_status="NOT_REQUIRED")
                store.put(run_id, "mappings", task["task_id"], result)
                store.task_status(run_id, task["task_id"], "SUCCEEDED")
            except model.PendingModelResult as exc:
                store.task_status(run_id, task["task_id"], "PENDING", "Awaiting model executor result: " + exc.task_id)
            except Exception as exc:
                _model_failure(store, run_id, task, exc)
    for call in getattr(judge, "calls", []):
        store.event(run_id, "model_bridge_event", call)
    store.event(run_id, "execution", {"mode": mode, "model_id": model_id, "rules": RULE_VERSION})
    return validate(store, run_id)


def current_summaries(store: Store, run_id: str) -> list[dict]:
    from .bridge import policy_fingerprint
    policy = policy_fingerprint()
    active = {s["snapshot_id"] for s in store.active_snapshots(run_id) if not store.verify_snapshot(s)}
    statuses = {t["task_id"]: t["status"] for t in store.tasks(run_id)}
    return [s for s in store.records(run_id, "summaries") if s["snapshot_id"] in active
            and statuses.get(s["task_id"]) == "SUCCEEDED" and s.get("policy_hash") == policy]


def current_judgments(store: Store, run_id: str, *, mode: str | None = None, model_id: str | None = None) -> list[dict]:
    from .bridge import policy_fingerprint
    policy = policy_fingerprint()
    active = {s["snapshot_id"] for s in store.active_snapshots(run_id)}
    statuses = {t["task_id"]: t["status"] for t in store.tasks(run_id)}
    cases = {case["case_id"]: digest(case) for case in store.records(run_id, "cases")}
    summaries = {s["task_id"]: digest(s) for s in current_summaries(store, run_id)}
    values = [j for j in store.records(run_id, "judgments") if j["snapshot_id"] in active
              and statuses.get(j["task_id"]) == "SUCCEEDED"
              and j.get("policy_hash") == policy and j.get("case_hash") == cases.get(j["case_id"])
              and j.get("summary_hash") == summaries.get(j.get("summary_task_id"))
              and j.get("summary_task_id") in summaries
              and (not mode or j["model_mode"] == mode)
              and (not model_id or j.get("requested_model_id", j["model_id"]) == model_id)]
    reviews = {}
    for event in store.events(run_id, "review"):
        if event.get("judgment_id"):
            reviews[event["judgment_id"]] = event
    for value in values:
        if value["judgment_id"] in reviews:
            value["review_status"] = reviews[value["judgment_id"]]["verdict"]
    return values


def current_mappings(store: Store, run_id: str) -> list[dict]:
    from .bridge import policy_fingerprint
    policy = policy_fingerprint()
    statuses = {task["task_id"]: task["status"] for task in store.tasks(run_id)}
    cases = {case["case_id"]: digest(case) for case in store.records(run_id, "cases")}
    catalog_hash = digest(store.records(run_id, "catalog"))
    plan = evidence_plan(store, run_id)
    judgments = necessary_judgments(store, run_id, plan)
    reviews = {event["mapping_id"]: event["verdict"] for event in store.events(run_id, "review")
               if event.get("mapping_id")}
    work, missing = planned_work(store, run_id, plan)
    values = []
    for mapping in store.records(run_id, "mappings"):
        case_id = mapping["case_id"]
        js = [j for j in judgments if j["case_id"] == case_id
              and j["model_mode"] == mapping["model_mode"]
              and j.get("requested_model_id", j["model_id"]) == mapping.get("requested_model_id", mapping.get("model_id"))]
        needed = {item["work_id"] for item in work if item["representative_case_id"] == case_id}
        ready = {j.get("work_id") for j in js}
        if (statuses.get(mapping["task_id"]) != "SUCCEEDED" or mapping.get("policy_hash") != policy
                or mapping.get("case_hash") != cases.get(case_id) or mapping.get("catalog_hash") != catalog_hash
                or mapping.get("judgments_hash") != digest([j for j in js if j.get("review_status") != "REJECT"])):
            continue
        if mapping["model_mode"] in {"opencode", "codex"} and (not needed or not needed.issubset(ready)
                or any(ref["case_id"] == case_id for ref in missing)):
            continue
        values.append(mapping)
    for value in values:
        value["review_status"] = reviews.get(value["task_id"], value.get("review_status", "NEEDS_REVIEW"))
    return values


def validate(store: Store, run_id: str) -> dict:
    cases, refs = store.records(run_id, "cases"), store.records(run_id, "references")
    plan = evidence_plan(store, run_id)
    snapshots = store.active_snapshots(run_id)
    tasks = task_views(store, run_id, plan)
    required_sids = {sid for row in plan["cases"] for sid in row["selected_snapshot_ids"]}
    case_by_id = {c["case_id"]: c for c in cases}
    snap_by_id = {s["snapshot_id"]: s for s in snapshots}
    errors, pending = [], []
    if not cases:
        errors.append("No imported cases")
    # Reconcile the actual imported source before applying the selected view;
    # a 232-row scope must not rewrite a larger document's original row counts.
    integrity_store = getattr(store, "unscoped", store)
    integrity_cases = integrity_store.records(run_id, "cases")
    integrity_refs = integrity_store.records(run_id, "references")
    exclusions = integrity_store.records(run_id, "exclusions")
    for document in store.records(run_id, "documents"):
        if "input_record_count" not in document:
            continue
        sha = document["source_sha256"]
        document_cases = [c for c in integrity_cases if c["source_sha256"] == sha]
        document_excluded = [e for e in exclusions if e.get("source_sha256") == sha]
        document_ids = {c["case_id"] for c in document_cases}
        document_refs = [r for r in integrity_refs if r["case_id"] in document_ids and r["discovered_by"] == "importer"]
        if len(document_cases) != document["case_count"] or len(document_excluded) != document["excluded_count"] or (
            len(document_cases) + len(document_excluded) != document["input_record_count"]
        ):
            errors.append("Input row reconciliation failed: " + document["source_file"])
        if len(document_refs) != document["reference_count"]:
            errors.append("Original reference reconciliation failed: " + document["source_file"])
    for snapshot in snapshots:
        if snapshot["snapshot_id"] not in required_sids:
            continue
        errors.extend(store.verify_snapshot(snapshot))
        # Partial capture is a recorded collection gap, not a reason to search or block usable facts.
    for ref in refs:
        if ref["case_id"] not in case_by_id:
            errors.append("Reference belongs to a missing case")
    work, missing = planned_work(store, run_id, plan)
    pending.extend(f"No snapshot for reference {r['ref_id']}" for r in missing)
    js = necessary_judgments(store, run_id, plan)
    for j in js:
        stripped = {key: j[key] for key in Judgment.model_fields}
        try:
            saved_snapshot = snap_by_id[j["snapshot_id"]]
            scope = j.get("input_scope", {})
            selected = set(scope.get("provided_segment_ids", []))
            view_segments = [segment for segment in saved_snapshot["segments"] if segment["segment_id"] in selected]
            view = {**saved_snapshot, "input_scope": scope,
                    "segments": view_segments, "text": "".join(segment["text"] for segment in view_segments)} if scope else saved_snapshot
            gate_judgment(case_by_id[j["case_id"]], view, stripped, context=j.get("processing_context"))
        except Exception as exc:
            errors.append(str(exc))
        if j["model_mode"] == "mock":
            pending.append(f"{j['judgment_id']}: mock workflow only, semantic verification pending")
        if j.get("processing_status") != "AUTO_PROCESSED" and j.get("review_status") != "ACCEPT":
            pending.append(f"{j['judgment_id']}: Agent fact comparison {j.get('processing_status', 'PENDING')}")
        if j.get("review_required", True) and j.get("review_status") != "ACCEPT":
            pending.append(f"{j['judgment_id']}: human review {j.get('review_status')}")
    pair_keys = {item["work_id"] for item in work}
    judged_keys = {j["work_id"] for j in js}
    pending.extend(f"Unjudged work {work_id}" for work_id in sorted(pair_keys - judged_keys))
    for case in cases:
        row = next(p for p in plan["cases"] if p["case_id"] == case["case_id"])
        control = row.get("search_control", {})
        if control and not control.get("satisfied", False):
            pending.append(f"{case['case_id']}: evidence search requirement pending ({control.get('status', 'UNKNOWN')}); "
                           + "; ".join(control.get("reasons", [])))
        if row["path"] == "SEARCH_REQUIRED":
            pending.append(f"{case['case_id']}: no references or usable evidence; search required")
        if row["path"] == "EXCEPTION":
            pending.append(f"{case['case_id']}: evidence exception {row['issues']}")
        for action in row["required_actions"]:
            if action["action"] in {"RECOVER_PROVENANCE", "RESTORE_PROVENANCE", "RESTORE_REFERENCE",
                                    "RECONFIRM_SNAPSHOT", "RESOLVE_CAPTURE_FAILURE"}:
                pending.append(f"{case['case_id']}: Agent {action['action']} pending; collection/provenance gap")
    for task in tasks:
        if task["required"] and task["status"] in {"PENDING", "BLOCKED", "FAILED", "RUNNING"}:
            pending.append(f"{task['task_id']}: {task['status']} {task['error']}")
    catalog = store.records(run_id, "catalog")
    if not catalog:
        pending.append("No frozen catalog imported; 98-item coverage not evaluated")
    statuses = {t["task_id"]: t["status"] for t in tasks}
    current_maps = current_mappings(store, run_id)
    for mapping in current_maps:
        if mapping["overall"] == "UNDETERMINED":
            pending.append(f"{mapping['case_id']}: catalog coverage undetermined")
        unknown_count = sum(item.get("result") == "UNDETERMINED" for item in mapping.get("catalog_results", []))
        if unknown_count:
            pending.append(f"{mapping['case_id']}: {unknown_count} catalog items undetermined")
        if mapping.get("review_required", True) and mapping.get("review_status") != "ACCEPT":
            pending.append(f"{mapping['task_id']}: catalog human review {mapping.get('review_status')}")
    if catalog:
        mapped = {m["case_id"] for m in current_maps}
        mapped.update(cid for m in current_maps for cid in m.get("member_case_ids", []))
        selected_case_ids = {cid for item in plan["work_items"] for cid in item["case_ids"]}
        pending.extend(f"{cid}: catalog comparison missing" for cid in sorted(selected_case_ids - mapped))
    pending = list(dict.fromkeys(pending))
    search_goals_satisfied = bool(cases) and all(row.get("search_control", {}).get("satisfied", True) for row in plan["cases"])
    facts_complete = bool(cases) and search_goals_satisfied and not errors and not missing and all(
        row.get("processing_status") == "AUTO_PROCESSED" and not any(action["action"] in {
            "RECOVER_PROVENANCE", "RESTORE_PROVENANCE", "RESTORE_REFERENCE", "RECONFIRM_SNAPSHOT", "RESOLVE_CAPTURE_FAILURE"}
            for action in row["required_actions"]) for row in plan["cases"])
    return {"run_id": run_id, "valid": not errors, "complete": not errors and not pending,
            "fact_organization_complete": facts_complete,
            "search_goals_satisfied": search_goals_satisfied,
            "batch_status": "FAILED" if errors else "COMPLETE_WITH_PENDING" if pending else "COMPLETE",
            "counts": {"cases": len(cases), "reference_occurrences": len(refs), "active_snapshots": len(snapshots),
                       "excluded_records": len(exclusions),
                       "all_snapshots": len(store.records(run_id, "snapshots")), "planned_associations": len(pair_keys),
                       "judged_associations": len(judged_keys), "catalog_items": len(catalog),
                       "association_identity": "work_id", "planned_work_ids": len(pair_keys),
                       "judged_work_ids": len(judged_keys),
                       "current_judgment_ids_including_rejected": len({j["judgment_id"] for j in js}),
                       "current_case_ids_with_judgments_including_rejected": len({j["case_id"] for j in js}),
                       "pending_reason_entries": len(pending),
                       "catalog_versions": len({i['source_sha256'] for i in catalog}),
                       "tasks": len(tasks), "required_tasks": sum(t["required"] for t in tasks),
                       "human_exceptions": sum(j.get("review_required", True) for j in js),
                       "satisfied_search_goals": sum(row.get("search_control", {}).get("satisfied", False) for row in plan["cases"]),
                       "search_allowed_cases": sum(row.get("search_control", {}).get("search_allowed", False) for row in plan["cases"]),
                       "task_states": dict(Counter(t["status"] for t in tasks if t["required"]))},
            "errors": list(dict.fromkeys(errors)), "pending": pending, "rule_version": RULE_VERSION}


def report_data(store: Store, run_id: str, *, baseline: dict | None = None,
                round_manifest: dict | None = None) -> dict:
    data = {kind: store.records(run_id, kind) for kind in
            ("cases", "references", "snapshots", "summaries", "judgments", "catalog", "mappings", "exclusions", "documents",
             "model_tasks", "model_results", "evidence_associations", "search_policies")}
    active = {s["snapshot_id"] for s in store.active_snapshots(run_id)}
    statuses = {t["task_id"]: t["status"] for t in store.tasks(run_id)}
    for key in ("snapshots", "summaries", "judgments"):
        for value in data[key]:
            value["is_stale"] = value.get("snapshot_id") not in active or (
                "task_id" in value and statuses.get(value["task_id"]) != "SUCCEEDED")
    for value in data["mappings"]:
        value["is_stale"] = statuses.get(value["task_id"]) != "SUCCEEDED"
    plan = evidence_plan(store, run_id)
    current_ids = {j["judgment_id"] for j in necessary_judgments(store, run_id, plan)}
    selected_sids = {sid for row in plan["cases"] for sid in row["selected_snapshot_ids"]}
    selected_refs = {rid for row in plan["cases"] for rid in row["selected_ref_ids"]}
    summary_ids = {s["task_id"] for s in current_summaries(store, run_id)}
    mapping_ids = {m["task_id"] for m in current_mappings(store, run_id)}
    for value in data["summaries"]:
        value["is_stale"] = value["task_id"] not in summary_ids
    reviews = {e["judgment_id"]: e["verdict"] for e in store.events(run_id, "review") if e.get("judgment_id")}
    mapping_reviews = {e["mapping_id"]: e["verdict"] for e in store.events(run_id, "review") if e.get("mapping_id")}
    for value in data["mappings"]:
        value["is_stale"] = value["task_id"] not in mapping_ids
        value["required"] = value["task_id"] in mapping_ids
        value["review_status"] = mapping_reviews.get(value["task_id"], value.get("review_status", "NEEDS_REVIEW"))
    for value in data["judgments"]:
        value["is_stale"] = value["judgment_id"] not in current_ids
        value["required"] = value["judgment_id"] in current_ids
        value["review_status"] = reviews.get(value["judgment_id"], value.get("review_status", "NEEDS_REVIEW"))
    case_ids = {c["case_id"] for c in data["cases"]}
    from .evidence_plan import source_relation
    for ref in data["references"]:
        case = next(c for c in data["cases"] if c["case_id"] == ref["case_id"])
        ref["source_relation"] = source_relation(case, ref)
        snapshot_ids = {snapshot["snapshot_id"] for snapshot in data["snapshots"]
                        if ref.get("status") == "PARSED" and ref.get("url") and canonical_url(ref["url"]) == snapshot["url"]}
        confirmed = [association for association in data["evidence_associations"]
                     if association["case_id"] == ref["case_id"] and association.get("user_confirmed") is True
                     and (association.get("ref_id") == ref["ref_id"] or association.get("snapshot_id") in snapshot_ids)]
        ref["user_confirmed"] = bool(confirmed)
        ref["association_ids"] = sorted(association["association_id"] for association in confirmed)
        ref["required"] = ref["ref_id"] in selected_refs
    for snapshot in data["snapshots"]:
        snapshot["required"] = snapshot["snapshot_id"] in selected_sids
    task_values = task_views(store, run_id, plan)
    work_by_id = {work["work_id"]: work for work in plan["work_items"]}
    for task in task_values:
        if task["kind"] == "compare" and task["target_id"] in work_by_id:
            task["work_id"] = task["target_id"]
            task["case_id"] = work_by_id[task["target_id"]]["representative_case_id"]
        cid = task["target_id"].split("|", 1)[0]
        if cid in case_ids:
            task["case_id"] = cid
    for case in data["cases"]:
        gaps = []
        if case["root_cause_origin"] == "LEGACY_DERIVED_UNKNOWN":
            gaps.append("旧根因来源未恢复，不能当作周报原文")
        case_plan = next(row for row in plan["cases"] if row["case_id"] == case["case_id"])
        if not case_plan["selected_ref_ids"] and not case_plan["selected_snapshot_ids"] and not any(r["case_id"] == case["case_id"] for r in data["references"]):
            gaps.append("没有资料引用，需要补搜或补充证据")
        case["missing_information"] = gaps
    data.update({"run": store.run_info(run_id), "tasks": task_values,
                 "evidence_plans": plan, "event_groups": store.records(run_id, "event_groups"),
                 "evidence_index": evidence_index(store, run_id)["evidence_index"],
                 "catalog_selections": store.records(run_id, "catalog_selections"),
                 "review_events": store.events(run_id, "review"), "validation": validate(store, run_id)})
    data["event_conclusions"] = [{"group_id": group["group_id"], "case_ids": group["case_ids"],
        "selected_snapshot_ids": sorted({sid for row in plan["cases"] if row["case_id"] in group["case_ids"] for sid in row["selected_snapshot_ids"]}),
        "judgment_ids": sorted({j["judgment_id"] for j in data["judgments"] if j["required"] and
                                 set(j.get("member_case_ids", [j["case_id"]])).intersection(group["case_ids"])}),
        "source_attributions": [{"case_id": c["case_id"], "root_cause_raw": c["root_cause_raw"],
                                 "source_file": c["source_file"], "sheet": c["sheet"], "row": c["row"]}
                                for c in data["cases"] if c["case_id"] in group["case_ids"]],
        "conflicts": [{"judgment_id": j["judgment_id"], "dimensions": j.get("conflicting_dimensions", [])}
                      for j in data["judgments"] if j["required"] and j.get("conflicting_dimensions") and
                      set(j.get("member_case_ids", [j["case_id"]])).intersection(group["case_ids"])]}
        for group in data["event_groups"]]
    from .statistics import report_statistics
    data["statistics"] = report_statistics(data, baseline=baseline, round_manifest=round_manifest)
    return data
