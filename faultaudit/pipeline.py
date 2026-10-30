"""Deterministic orchestration; model proposals never bypass evidence gates."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from .contracts import EvidenceSummary, Judgment
from .gates import event_anchor_errors
from .store import AuditError, Store, canonical_url, digest

RULE_VERSION = "nightly-0.1.1"


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


def gate_judgment(case: dict, snapshot: dict, value: dict) -> dict:
    result = Judgment.model_validate(value).model_dump()
    errors = []
    if result["case_id"] != case["case_id"] or result["snapshot_id"] != snapshot["snapshot_id"]:
        errors.append("Model returned a different case_id or snapshot_id")
    errors.extend(check_citations(result["evidence"], snapshot))
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
    result["review_status"] = "NEEDS_REVIEW"
    result["rule_version"] = RULE_VERSION
    return result


def import_into(store: Store, run_id: str, result: dict, catalog: bool = False) -> dict:
    counts = {}
    if catalog:
        old_hashes = {i["source_sha256"] for i in store.records(run_id, "catalog")}
        new_hashes = {i["source_sha256"] for i in result.get("items", [])}
        if len(new_hashes) != 1 or (old_hashes and old_hashes != new_hashes):
            raise AuditError("Catalog version is frozen within a run; use a new run for another catalog file")
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
    store.event(run_id, "catalog_imported" if catalog else "cases_imported", {"counts": counts})
    return counts


def associations(store: Store, run_id: str) -> tuple[list[tuple[dict, dict]], list[dict]]:
    cases = {c["case_id"]: c for c in store.records(run_id, "cases")}
    by_url = {s["url"]: s for s in store.active_snapshots(run_id)}
    pairs, missing, seen = [], [], set()
    for ref in store.records(run_id, "references"):
        try:
            snapshot = by_url.get(canonical_url(ref["url"])) if ref.get("url") and ref.get("status") == "PARSED" else None
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


def fetch_tasks(store: Store, run_id: str) -> dict:
    by_url = {s["url"]: s for s in store.active_snapshots(run_id)}
    grouped = {}
    malformed = []
    for ref in store.records(run_id, "references"):
        if not ref.get("url") or ref.get("status") != "PARSED":
            malformed.append(ref)
            continue
        try:
            url = canonical_url(ref["url"])
        except AuditError:
            malformed.append(ref)
            continue
        group = grouped.setdefault(url, {"url": url, "case_ids": [], "references": [], "retrieval_status": "NOT_FETCHED"})
        if ref["case_id"] not in group["case_ids"]:
            group["case_ids"].append(ref["case_id"])
        group["references"].append(ref)
        if url in by_url:
            group["retrieval_status"] = by_url[url]["status"]
            group["snapshot_id"] = by_url[url]["snapshot_id"]
    return {"run_id": run_id, "fetch_tasks": list(grouped.values()), "malformed_references": malformed,
            "note": "Call existing site tools, preserve text and return EvidencePackage JSON. Search discoveries require explicit case_ids."}


def _task_allowed(task: dict, retry_failed: bool):
    return task["status"] in {"PENDING", "BLOCKED", "RUNNING"} or (retry_failed and task["status"] == "FAILED")


def execute(store: Store, run_id: str, judge, *, mode: str, model_id: str, retry_failed: bool = False) -> dict:
    from . import prompts, gates, contracts, model
    signature = {"mode": mode, "model_id": model_id, "rules": RULE_VERSION,
                 "prompt_version": prompts.PROMPT_VERSION,
                 "prompt_hash": digest(Path(prompts.__file__).read_bytes()),
                 "engine_hash": digest(b"".join(Path(module.__file__).read_bytes() for module in
                                                 (gates, contracts, model)) + Path(__file__).read_bytes()),
                 "executor_signature": getattr(judge, "execution_signature", "local-validation")}
    pairs, missing = associations(store, run_id)
    active = {s["snapshot_id"]: s for _, s in pairs}
    for ref in missing:
        t = store.task(run_id, "fetch", ref["ref_id"], ref)
        store.task_status(run_id, t["task_id"], "BLOCKED", "Missing snapshot or malformed URL")
    # Mark previously missing references resolved as soon as evidence is supplied.
    missing_ids = {r["ref_id"] for r in missing}
    for task in store.tasks(run_id):
        if task["kind"] == "fetch" and task["target_id"] not in missing_ids:
            store.task_status(run_id, task["task_id"], "SUCCEEDED")
    for sid, snapshot in active.items():
        task = store.task(run_id, "summarize", sid, [sid, signature])
        if not _task_allowed(task, retry_failed):
            continue
        if snapshot["status"] not in {"COMPLETE", "PARTIAL"} or not snapshot["text"].strip():
            store.task_status(run_id, task["task_id"], "BLOCKED", "Evidence body unavailable: " + snapshot["status"])
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
            for group in groups:
                view = {**snapshot, "segments": group, "text": "".join(s["text"] for s in group)}
                judge.pipeline_task_id = task["task_id"]
                response = EvidenceSummary.model_validate(judge.summarize(view)).model_dump()
                if response["snapshot_id"] != sid:
                    raise AuditError("Summary refers to a different snapshot")
                problems = check_citations(list(cited_refs(response)), snapshot)
                if problems:
                    raise AuditError("; ".join(problems))
                responses.append(response)
                issues.extend(response["issues"])
                unknown.extend(response["unknown_fields"])
            actual_models = sorted({r["model_id"] for r in responses})
            if len(actual_models) != 1:
                raise AuditError("Model identity changed between summary chunks")
            value = {"snapshot_id": sid, "issues": issues, "unknown_fields": sorted(set(unknown)),
                     "model_mode": mode, "model_id": actual_models[0], "requested_model_id": model_id,
                     "blocks_processed": len(groups),
                     "segments_processed": len(snapshot["segments"]), "task_id": task["task_id"]}
            store.put(run_id, "summaries", task["task_id"], value)
            store.task_status(run_id, task["task_id"], "SUCCEEDED")
        except model.PendingModelResult as exc:
            store.task_status(run_id, task["task_id"], "PENDING", "Awaiting OpenCode result: " + exc.task_id)
        except Exception as exc:
            store.task_status(run_id, task["task_id"], "FAILED", str(exc))
    summaries = {s["snapshot_id"]: s for s in store.records(run_id, "summaries")
                 if any(t["task_id"] == s["task_id"] and t["status"] == "SUCCEEDED" for t in store.tasks(run_id))
                 and s["model_mode"] == mode and s.get("requested_model_id", s["model_id"]) == model_id}
    for case, snapshot in pairs:
        sid = snapshot["snapshot_id"]
        summary = summaries.get(sid)
        task = store.task(run_id, "compare", case["case_id"] + "|" + sid,
                          [case, sid, digest(summary) if summary else None, signature])
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
            summary_input = {key: summary[key] for key in EvidenceSummary.model_fields}
            judge.pipeline_task_id = task["task_id"]
            value = gate_judgment(case, snapshot, judge.compare(case, view, summary_input))
            value["judgment_id"] = task["task_id"]
            value["task_id"] = task["task_id"]
            value["requested_model_id"] = model_id
            store.put(run_id, "judgments", task["task_id"], value)
            store.task_status(run_id, task["task_id"], "SUCCEEDED")
        except model.PendingModelResult as exc:
            store.task_status(run_id, task["task_id"], "PENDING", "Awaiting OpenCode result: " + exc.task_id)
        except Exception as exc:
            store.task_status(run_id, task["task_id"], "FAILED", str(exc))
    items = store.records(run_id, "catalog")
    if items:
        for case in store.records(run_id, "cases"):
            js = current_judgments(store, run_id, mode=mode, model_id=model_id)
            case_judgments = [j for j in js if j["case_id"] == case["case_id"]]
            js = [j for j in case_judgments if j.get("review_status") != "REJECT"]
            task = store.task(run_id, "catalog", case["case_id"], [case, js, items, signature])
            if not _task_allowed(task, retry_failed):
                continue
            if mode == "opencode":
                needed = {(c["case_id"], s["snapshot_id"]) for c, s in pairs if c["case_id"] == case["case_id"]}
                ready = {(j["case_id"], j["snapshot_id"]) for j in case_judgments}
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
                               "requested_model_id": model_id, "catalog_count": len(items), "review_status": "NEEDS_REVIEW"})
                store.put(run_id, "mappings", task["task_id"], result)
                store.task_status(run_id, task["task_id"], "SUCCEEDED")
            except model.PendingModelResult as exc:
                store.task_status(run_id, task["task_id"], "PENDING", "Awaiting OpenCode result: " + exc.task_id)
            except Exception as exc:
                store.task_status(run_id, task["task_id"], "FAILED", str(exc))
    for call in getattr(judge, "calls", []):
        store.event(run_id, "model_bridge_event", call)
    store.event(run_id, "execution", {"mode": mode, "model_id": model_id, "rules": RULE_VERSION})
    return validate(store, run_id)


def current_judgments(store: Store, run_id: str, *, mode: str | None = None, model_id: str | None = None) -> list[dict]:
    active = {s["snapshot_id"] for s in store.active_snapshots(run_id)}
    statuses = {t["task_id"]: t["status"] for t in store.tasks(run_id)}
    values = [j for j in store.records(run_id, "judgments") if j["snapshot_id"] in active
              and statuses.get(j["task_id"]) == "SUCCEEDED"
              and (not mode or j["model_mode"] == mode)
              and (not model_id or j.get("requested_model_id", j["model_id"]) == model_id)]
    reviews = {}
    for event in store.events(run_id, "review"):
        reviews[event["judgment_id"]] = event
    for value in values:
        if value["judgment_id"] in reviews:
            value["review_status"] = reviews[value["judgment_id"]]["verdict"]
    return values


def validate(store: Store, run_id: str) -> dict:
    cases, refs = store.records(run_id, "cases"), store.records(run_id, "references")
    snapshots, tasks = store.active_snapshots(run_id), store.tasks(run_id)
    case_by_id = {c["case_id"]: c for c in cases}
    snap_by_id = {s["snapshot_id"]: s for s in snapshots}
    errors, pending = [], []
    if not cases:
        errors.append("No imported cases")
    exclusions = store.records(run_id, "exclusions")
    for document in store.records(run_id, "documents"):
        if "input_record_count" not in document:
            continue
        sha = document["source_sha256"]
        document_cases = [c for c in cases if c["source_sha256"] == sha]
        document_excluded = [e for e in exclusions if e.get("source_sha256") == sha]
        document_ids = {c["case_id"] for c in document_cases}
        document_refs = [r for r in refs if r["case_id"] in document_ids and r["discovered_by"] == "importer"]
        if len(document_cases) != document["case_count"] or len(document_excluded) != document["excluded_count"] or (
            len(document_cases) + len(document_excluded) != document["input_record_count"]
        ):
            errors.append("Input row reconciliation failed: " + document["source_file"])
        if len(document_refs) != document["reference_count"]:
            errors.append("Original reference reconciliation failed: " + document["source_file"])
    for snapshot in snapshots:
        errors.extend(store.verify_snapshot(snapshot))
        if snapshot["status"] != "COMPLETE":
            pending.append(f"{snapshot['snapshot_id']}: {snapshot['status']}")
    for ref in refs:
        if ref["case_id"] not in case_by_id:
            errors.append("Reference belongs to a missing case")
        if ref.get("status") != "PARSED":
            pending.append(f"Malformed reference {ref['ref_id']}")
    pairs, missing = associations(store, run_id)
    pending.extend(f"No snapshot for reference {r['ref_id']}" for r in missing)
    js = current_judgments(store, run_id)
    for j in js:
        stripped = {key: j[key] for key in Judgment.model_fields}
        try:
            gate_judgment(case_by_id[j["case_id"]], snap_by_id[j["snapshot_id"]], stripped)
        except Exception as exc:
            errors.append(str(exc))
        if j["model_mode"] == "mock":
            pending.append(f"{j['judgment_id']}: mock workflow only, semantic verification pending")
        if j["case_attribution"] in {"UNKNOWN", "PARTIAL"} or j["support_level"] in {"PENDING", "CONFLICT"}:
            pending.append(f"{j['judgment_id']}: attribution or conflict unresolved")
        if j.get("review_status") != "ACCEPT":
            pending.append(f"{j['judgment_id']}: human review {j.get('review_status')}")
    pair_keys = {(c["case_id"], s["snapshot_id"]) for c, s in pairs}
    judged_keys = {(j["case_id"], j["snapshot_id"]) for j in js}
    pending.extend(f"Unjudged association {cid}|{sid}" for cid, sid in sorted(pair_keys - judged_keys))
    for case in cases:
        if not any(r["case_id"] == case["case_id"] for r in refs):
            pending.append(f"{case['case_id']}: no references; search or evidence needed")
        if case["root_cause_origin"] == "LEGACY_DERIVED_UNKNOWN":
            pending.append(f"{case['case_id']}: legacy root-cause provenance not restored")
    for task in tasks:
        if task["status"] in {"PENDING", "BLOCKED", "FAILED", "RUNNING"}:
            pending.append(f"{task['task_id']}: {task['status']} {task['error']}")
    catalog = store.records(run_id, "catalog")
    if not catalog:
        pending.append("No frozen catalog imported; 98-item coverage not evaluated")
    statuses = {t["task_id"]: t["status"] for t in tasks}
    current_maps = [m for m in store.records(run_id, "mappings") if statuses.get(m["task_id"]) == "SUCCEEDED"]
    for mapping in current_maps:
        if mapping["overall"] == "UNDETERMINED":
            pending.append(f"{mapping['case_id']}: catalog coverage undetermined")
    if catalog:
        mapped = {m["case_id"] for m in current_maps}
        pending.extend(f"{c['case_id']}: catalog comparison missing" for c in cases if c["case_id"] not in mapped)
    pending = list(dict.fromkeys(pending))
    return {"run_id": run_id, "valid": not errors, "complete": not errors and not pending,
            "batch_status": "FAILED" if errors else "COMPLETE_WITH_PENDING" if pending else "COMPLETE",
            "counts": {"cases": len(cases), "reference_occurrences": len(refs), "active_snapshots": len(snapshots),
                       "excluded_records": len(exclusions),
                       "all_snapshots": len(store.records(run_id, "snapshots")), "planned_associations": len(pair_keys),
                       "judged_associations": len(judged_keys), "catalog_items": len(catalog),
                       "catalog_versions": len({i['source_sha256'] for i in catalog}),
                       "tasks": len(tasks), "task_states": dict(Counter(t["status"] for t in tasks))},
            "errors": list(dict.fromkeys(errors)), "pending": pending, "rule_version": RULE_VERSION}


def report_data(store: Store, run_id: str) -> dict:
    data = {kind: store.records(run_id, kind) for kind in
            ("cases", "references", "snapshots", "summaries", "judgments", "catalog", "mappings", "exclusions", "documents",
             "model_tasks", "model_results")}
    active = {s["snapshot_id"] for s in store.active_snapshots(run_id)}
    statuses = {t["task_id"]: t["status"] for t in store.tasks(run_id)}
    for key in ("snapshots", "summaries", "judgments"):
        for value in data[key]:
            value["is_stale"] = value.get("snapshot_id") not in active or (
                "task_id" in value and statuses.get(value["task_id"]) != "SUCCEEDED")
    for value in data["mappings"]:
        value["is_stale"] = statuses.get(value["task_id"]) != "SUCCEEDED"
    current_ids = {j["judgment_id"] for j in current_judgments(store, run_id)}
    reviews = {e["judgment_id"]: e["verdict"] for e in store.events(run_id, "review")}
    for value in data["judgments"]:
        value["is_stale"] = value["judgment_id"] not in current_ids
        value["review_status"] = reviews.get(value["judgment_id"], value.get("review_status", "NEEDS_REVIEW"))
    case_ids = {c["case_id"] for c in data["cases"]}
    task_values = store.tasks(run_id)
    for task in task_values:
        cid = task["target_id"].split("|", 1)[0]
        if cid in case_ids:
            task["case_id"] = cid
    for case in data["cases"]:
        gaps = []
        if case["root_cause_origin"] == "LEGACY_DERIVED_UNKNOWN":
            gaps.append("旧根因来源未恢复，不能当作周报原文")
        if not any(r["case_id"] == case["case_id"] for r in data["references"]):
            gaps.append("没有资料引用，需要补搜或补充证据")
        case["missing_information"] = gaps
    data.update({"run": store.run_info(run_id), "tasks": task_values,
                 "review_events": store.events(run_id, "review"), "validation": validate(store, run_id)})
    return data
