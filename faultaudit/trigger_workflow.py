"""Initialize historical mechanism/trigger coverage, then assess new cases.

This layer reuses the collection, independent summary and fresh-context driver.
A library definition is an evidence subject, never an invented incident. All
indexes are projections of current cited assessments; formal adoption is separate.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from .contracts import SourceCase
from .importers import import_cases, import_catalog
from .resource_identity import resource_key, snapshot_index
from .store import AuditError, Store, digest
from .trigger_assessment import instructions, response_schema, validate_assessment
from .trigger_taxonomy import builtin_user_branches, load_taxonomy

RULE_VERSION = "trigger-workflow-1"


def _settings(store, run_id):
    value = store.get(run_id, "trigger_config", "config")
    if not value:
        raise AuditError("Start a trigger initialization/classification run first")
    return value


def _catalog(store, run_id):
    return sorted(store.records(run_id, "catalog"), key=lambda x: x["item_id"])


def start_init(store: Store, modes: Path, taxonomy: Path, work_root: Path, *,
               executor="opencode", branch_source=None, user_branches=True,
               catalog_scope="ORIGINAL_MECHANISM_LIBRARY") -> dict:
    from .evidence_plan import register_search_policy
    from .pipeline import import_into
    if executor not in {"opencode", "codex"}:
        raise AuditError("Executor must be opencode or codex")
    library = import_catalog(modes, scope=catalog_scope)
    if not library["items"] or len({i["item_id"] for i in library["items"]}) != len(library["items"]):
        raise AuditError("Initialization requires a nonempty library with unique original mode IDs")
    frozen = load_taxonomy(taxonomy, branch_source,
        user_branch_definitions=builtin_user_branches() if user_branches and not branch_source else None)
    imported = import_cases(modes, "LEGACY_TABLE")
    by_row = {(c["sheet"], c["row"]): c for c in imported["cases"]}
    subjects = []
    for item in library["items"]:
        case = by_row.get((item["sheet"], item["row"]))
        if not case:
            raise AuditError("Every mode must retain its original source row")
        case["external_id"] = item["item_id"]
        SourceCase.model_validate(case)
        subjects.append({"subject_id": "mode-subject-" + digest(item["item_id"])[:24],
            "case_id": case["case_id"], "mode_id": item["item_id"], "subject_kind": "MODE_ENTRY"})
    run_id = store.create_run({"workflow": RULE_VERSION, "purpose": "TRIGGER_INIT"})
    import_into(store, run_id, imported)
    import_into(store, run_id, library, catalog=True)
    store.put(run_id, "trigger_taxonomies", frozen["taxonomy_id"], frozen)
    for subject in subjects:
        store.put(run_id, "trigger_subjects", subject["subject_id"], subject)
    directory = (work_root / run_id).resolve()
    if directory.is_relative_to(store.root):
        raise AuditError("Workflow files must be outside state")
    selected = sorted(s["case_id"] for s in subjects)
    cfg = {"run_id": run_id, "directory": str(directory), "executor": executor,
        "source_hash": imported["documents"][0]["source_sha256"], "rule_version": RULE_VERSION,
        "purpose": "TRIGGER_INIT", "selected_case_ids": selected, "scope_hash": digest(selected),
        "capture_quality_required": True, "max_search_rounds": 3, "capture_attempts_per_resource": 3}
    store.put(run_id, "xlsx_workflow", "config", cfg)
    store.put(run_id, "trigger_config", "config", {"phase": "INIT", "taxonomy_id": frozen["taxonomy_id"],
        "catalog_hash": digest(_catalog(store, run_id)), "rule_version": RULE_VERSION})
    register_search_policy(store, run_id, {"required_sources": ["WIKI"]})
    return {**cfg, "mode_count": len(subjects), "trigger_count": len(frozen["items"]),
        "branch_categories": [c["id"] for b in frozen["branches"] for c in b.get("categories", [])]}


def _taxonomy(store, run_id):
    return store.get(run_id, "trigger_taxonomies", _settings(store, run_id)["taxonomy_id"])


def _model_taxonomy(frozen):
    """All 42 predicates and applicability rules, without repeated quote copies.

    The source and full parsed document remain frozen in SQLite. Generator/N
    allocation instructions govern a different execution workflow, not this
    historical evidence classifier. They are explicitly outside this task.
    """
    value = {k: frozen[k] for k in ("taxonomy_id", "taxonomy_hash", "source_file", "source_sha256", "item_count")}
    value["items"] = [{k: item[k] for k in ("id", "family_id", "name", "definition", "requires", "skip_if", "line_start", "line_end") if k in item}
                       for item in frozen["items"]]
    value["families"] = frozen.get("families", [])
    value["context"] = {k: v for k, v in frozen.get("context", {}).items() if k in {"scope", "applicability"}}
    value["branches"] = [{k: v for k, v in b.items() if k not in {"source_sha256", "source_file"}}
                         for b in frozen.get("branches", [])]
    value["input_scope"] = {"trigger_ids": [i["id"] for i in frozen["items"]], "item_count": 42,
        "included": "All definitions, local/family Requires/Skip and global scope/applicability",
        "excluded": "Duplicate item source_quote copies; generator N-allocation/execution instructions outside historical classification"}
    return value


def _linked_snapshots(store, run_id, case_id):
    from .evidence_plan import collection_source_policy, resource_kind
    policy = collection_source_policy(store, run_id)
    active = snapshot_index(store.active_snapshots(run_id))
    selected = {}
    for ref in store.records(run_id, "references"):
        if ref["case_id"] == case_id and ref.get("url"):
            snapshot = active.get(resource_key(ref["url"]))
            if (snapshot and not store.verify_snapshot(snapshot) and (not policy["explicit_override"]
                    or resource_kind(snapshot=snapshot) in policy["collection_sources"])):
                selected[snapshot["snapshot_id"]] = snapshot
    for relation in store.records(run_id, "evidence_associations"):
        if relation["case_id"] == case_id and relation.get("user_confirmed"):
            snapshot = store.get(run_id, "snapshots", relation.get("snapshot_id", ""))
            if (snapshot and snapshot["snapshot_id"] in {s["snapshot_id"] for s in active.values()}
                    and (not policy["explicit_override"] or resource_kind(snapshot=snapshot) in policy["collection_sources"])):
                selected[snapshot["snapshot_id"]] = snapshot
    return selected


def _issues(store, run_id, case_id):
    """Only complete, current independent summaries; each issue gets its own task."""
    from .pipeline import current_summaries, check_citations
    from .model import validate_task_result
    from .contracts import EvidenceSummary
    snapshots = _linked_snapshots(store, run_id, case_id)
    issues = []
    for summary in sorted(current_summaries(store, run_id), key=lambda s: s["task_id"]):
        snapshot = snapshots.get(summary["snapshot_id"])
        if not snapshot or summary.get("model_mode") == "mock":
            continue
        if summary.get("segments_processed") != len(snapshot.get("segments", [])):
            continue
        try:
            validate_task_result("summarize", {k: summary[k] for k in EvidenceSummary.model_fields}, snapshot=snapshot)
        except ValueError:
            continue
        for index, issue in enumerate(summary.get("issues", [])):
            facts = []
            for fact in issue.get("facts", []):
                refs = fact.get("evidence", [])
                if fact.get("value") in (None, "", [], {}) or not refs or check_citations(refs, snapshot):
                    continue
                identity = {"summary_task_id": summary["task_id"], "issue_label": issue["label"],
                    "issue_index": index, "field": fact["field"], "value": fact["value"], "evidence": refs}
                facts.append({"fact_id": "fact-" + digest(identity)[:24], **identity})
            selected = {r["segment_id"] for f in facts for r in f["evidence"]}
            view = {k: snapshot[k] for k in ("snapshot_id", "url", "status", "title", "text_sha256") if k in snapshot}
            view["segments"] = [s for s in snapshot["segments"] if s["segment_id"] in selected]
            scope = {"scope": "ISSUE_CITED_SEGMENTS", "provided_segment_ids": sorted(selected),
                "total_snapshot_segments": len(snapshot["segments"]), "full_text_verified": False}
            issues.append({"snapshot_id": snapshot["snapshot_id"], "summary_task_id": summary["task_id"],
                "issue_index": index, "label": issue["label"], "facts": facts,
                "snapshot": view, "input_scope": scope})
    return issues


def _basis(store, run_id, subject, snapshot_id=None):
    """No plan calls: source routing calls this function, so it cannot recurse."""
    from .pipeline import current_summaries
    from .evidence_plan import collection_source_policy
    cid = subject["case_id"]
    settings = _settings(store, run_id)
    snapshots = _linked_snapshots(store, run_id, cid)
    if snapshot_id:
        snapshots = {sid: s for sid, s in snapshots.items() if sid == snapshot_id}
    resource_ids = {resource_key(s["url"]) for s in snapshots.values()}
    base = {"subject": subject, "source": store.get(run_id, "cases", cid),
        "taxonomy": digest(_taxonomy(store, run_id)), "catalog": digest(_catalog(store, run_id)),
        "references": sorted([r for r in store.records(run_id, "references") if r["case_id"] == cid
            and (not snapshot_id or r.get("url") and resource_key(r["url"]) in resource_ids)], key=lambda r: r["ref_id"]),
        "snapshots": sorted(snapshots),
        "summaries": sorted([digest(s) for s in current_summaries(store, run_id) if s["snapshot_id"] in snapshots]),
        "baseline": settings.get("baseline_id"),
        "collection_policy": collection_source_policy(store, run_id)["policy_hash"]}
    if not snapshot_id:
        base["wiki_checks"] = sorted(digest(c) for c in store.records(run_id, "wiki_checks") if c["case_id"] == cid)
    if settings["phase"] == "INCREMENTAL":
        from .pipeline import current_judgments, current_mappings
        # Include the live maintained source identity, not only its old ID.
        base["baseline_live_hash"] = _index_identity(store, settings["baseline_run"])
        base["judgments"] = sorted(digest(j) for j in current_judgments(store, run_id) if j["case_id"] == cid)
        base["mappings"] = sorted(digest(m) for m in current_mappings(store, run_id) if m["case_id"] == cid)
    return digest(base)


def current_assessments(store, run_id):
    from .xlsx_workflow import _policy
    subjects = {s["subject_id"]: s for s in store.records(run_id, "trigger_subjects")}
    bases = {}
    def basis(record):
        key = (record["subject_id"], record.get("snapshot_id"))
        if key not in bases and key[0] in subjects:
            bases[key] = _basis(store, run_id, subjects[key[0]], key[1])
        return bases.get(key)
    return sorted([a for a in store.records(run_id, "trigger_assessments")
        if a.get("policy_hash") == _policy() and a.get("basis_hash") == basis(a)],
        key=lambda a: a["assessment_id"])


def source_relations(store, run_id):
    """Current MODE_ENTRY/material alignments; not incident or root confirmations."""
    if not store.get(run_id, "trigger_config", "config"):
        return {}
    grouped = {}
    for value in current_assessments(store, run_id):
        if value.get("snapshot_id"):
            grouped.setdefault((value["case_id"], value["snapshot_id"]), []).append(value)
    result = {}
    for pair, values in grouped.items():
        relations = {v["result"]["source_relation"] for v in values}
        if "MATCH" in relations:
            result[pair] = "MATCH"
            continue
        expected = {(i["summary_task_id"], i["issue_index"]) for i in _issues(store, run_id, pair[0]) if i["snapshot_id"] == pair[1]}
        if expected and {(v["summary_task_id"], v["issue_index"]) for v in values} == expected:
            result[pair] = "NOT_RELATED" if relations == {"NOT_RELATED"} else "PARTIAL" if "PARTIAL" in relations else "UNKNOWN"
    active = {s["snapshot_id"] for s in store.active_snapshots(run_id)}
    for lookup in store.records(run_id, "trigger_source_lookups"):
        for sid in lookup.get("snapshot_ids", []):
            if sid in active:
                result.setdefault((lookup["case_id"], sid), "SUPPLIED_IDENTIFIER")
    return result


def classification_payloads(store, run_id):
    from .pipeline import current_judgments, current_mappings
    settings, taxonomy = _settings(store, run_id), _model_taxonomy(_taxonomy(store, run_id))
    baseline = store.get(run_id, "trigger_baseline_refs", "baseline")
    catalog = _catalog(store, run_id)
    assessments = current_assessments(store, run_id)
    for subject in sorted(store.records(run_id, "trigger_subjects"), key=lambda s: s["subject_id"]):
        cid = subject["case_id"]
        issues = _issues(store, run_id, cid) or [None]
        for issue in issues:
            key = (subject["subject_id"], (issue or {}).get("snapshot_id"), (issue or {}).get("summary_task_id"), (issue or {}).get("issue_index"))
            if any((a["subject_id"], a.get("snapshot_id"), a.get("summary_task_id"), a.get("issue_index")) == key for a in assessments):
                continue
            judgments, mappings = [], []
            if settings["phase"] == "INCREMENTAL":
                sid, label = (issue or {}).get("snapshot_id"), (issue or {}).get("label")
                judgments = [j for j in current_judgments(store, run_id) if j["case_id"] == cid
                    and j["snapshot_id"] == sid and (j.get("applicable_issue") or {}).get("label") == label]
                mappings = [m for m in current_mappings(store, run_id) if m["case_id"] == cid]
            yield {"phase": settings["phase"], "subject": {**subject, "source_case": store.get(run_id, "cases", cid)},
                "taxonomy": taxonomy, "source_issue": issue,
                "wiki_check": {"records": [c for c in store.records(run_id, "wiki_checks") if c["case_id"] == cid],
                    "rule": "Wiki first; blocked access is a collection gap, not a negative mechanism judgment"},
                "mechanism_catalog": [c for c in catalog if settings["phase"] != "INIT" or c["item_id"] == subject["mode_id"]],
                "baseline": baseline, "judgments": judgments, "mappings": mappings,
                "basis_hash": _basis(store, run_id, subject, (issue or {}).get("snapshot_id")),
                "case_ids": [cid], "response_schema": response_schema()}


def accept_assessment(store, run_id, request, response):
    from .xlsx_workflow import _policy, config
    payload = request["payload"]
    subject = store.get(run_id, "trigger_subjects", payload["subject"]["subject_id"])
    if not subject or payload["basis_hash"] != _basis(store, run_id, subject, (payload.get("source_issue") or {}).get("snapshot_id")):
        raise AuditError("Classification input/baseline changed; request a fresh task")
    if response.get("executor") != config(store, run_id)["executor"]:
        raise AuditError("Classification executor differs from configured Agent")
    if payload.get("baseline"):
        _baseline(store, _settings(store, run_id)["baseline_run"], payload["baseline"]["baseline_id"],
                  allow_pending=_settings(store, run_id).get("allow_pending_baseline", False))
    result = validate_assessment(payload, response, request["request_hash"])
    issue = payload.get("source_issue") or {}
    record = {"assessment_id": request["task_id"], "subject_id": subject["subject_id"], "case_id": subject["case_id"],
        "snapshot_id": issue.get("snapshot_id"), "issue_index": issue.get("issue_index"),
        "issue_label": issue.get("label", "Source definition only"),
        "summary_task_id": issue.get("summary_task_id"), "basis_hash": payload["basis_hash"],
        "policy_hash": _policy(), "raw_response": response, "result": result}
    store.put(run_id, "trigger_assessments", record["assessment_id"], record)
    return record


def source_lookups(store, run_id):
    """Resolve only original identifiers, never manufacture an internal URL."""
    from .wiki_checks import wiki_plan
    from .evidence_plan import collection_source_policy
    policy = collection_source_policy(store, run_id)
    cases = {c["case_id"]: c for c in store.records(run_id, "cases")}
    for cid, case in cases.items():
        # Wiki work is generated first; an access gap must not stop other sources.
        if wiki_plan(store, run_id, case)["status"] == "SEARCH_REQUIRED":
            continue
        identifiers = {}
        for ref in store.records(run_id, "references"):
            if ref["case_id"] != cid or ref.get("url"):
                continue
            for value in re.findall(r"\b(?:DTS\d{10,}|WIKI\d{10,})\b", ref["raw_text"], flags=re.I):
                identifiers.setdefault(value.upper(), []).append(ref["ref_id"])
        for identifier, refs in identifiers.items():
            kind = "WIKI" if identifier.startswith("WIKI") else "DTS"
            if policy["explicit_override"] and kind not in policy["collection_sources"]:
                continue
            key = digest([cid, identifier])
            if store.get(run_id, "trigger_source_lookups", key):
                continue
            yield {"case": case, "case_ids": [cid], "source_lookup": {"lookup_key": key,
                "identifier": identifier, "reference_ids": sorted(set(refs))}}


def validate_source_lookup(payload, response):
    identifier = payload["source_lookup"]["identifier"]
    if response.get("outcome") == "FOUND":
        kind = "WIKI" if identifier.startswith("WIKI") else "DTS"
        from .evidence_plan import resource_kind
        for package in response.get("packages", []):
            url_ids = set(re.findall(r"(?:DTS\d{10,}|WIKI\d{10,})", package.get("url", "").upper()))
            if (resource_kind(snapshot=package) != kind
                    or url_ids and url_ids != {identifier}
                    or identifier not in (package.get("url", "") + " " + package.get("title", "")).upper()):
                raise AuditError("Original identifier lookup must capture that actual Wiki/DTS page, not a mention elsewhere")


def record_source_lookup(store, run_id, payload, response, snapshots):
    lookup = payload["source_lookup"]
    record = {**lookup, "case_id": payload["case_ids"][0], "outcome": response["outcome"],
        "reason": response["reason"], "snapshot_ids": [s["snapshot_id"] for s in snapshots]}
    store.put(run_id, "trigger_source_lookups", lookup["lookup_key"], record, mutable=True)


def _projection(store, run_id):
    from .wiki_checks import wiki_plan
    from .evidence_plan import collection_source_policy, resource_kind
    policy = collection_source_policy(store, run_id)
    cfg = _settings(store, run_id)
    assessments = current_assessments(store, run_id)
    subjects = [{**s, "source_case": store.get(run_id, "cases", s["case_id"])}
                for s in store.records(run_id, "trigger_subjects")]
    checks = {s["case_id"]: wiki_plan(store, run_id, s["source_case"]) for s in subjects}
    gaps = []
    for subject in subjects:
        cid = subject["case_id"]
        if checks[cid]["status"] not in {"FOUND", "NO_MATCH"}:
            gaps.append({"case_id": cid, "kind": "WIKI_" + checks[cid]["status"], "reason": checks[cid].get("reason", "Wiki check pending")})
        values = [a for a in assessments if a["subject_id"] == subject["subject_id"]]
        if not values:
            gaps.append({"case_id": cid, "kind": "UNASSESSED", "reason": "No current classification result"})
        for issue in _issues(store, run_id, cid):
            if not any(a.get("snapshot_id") == issue["snapshot_id"] and a.get("summary_task_id") == issue["summary_task_id"]
                       and a.get("issue_index") == issue["issue_index"] for a in values):
                gaps.append({"case_id": cid, "kind": "ISSUE_UNASSESSED",
                    "reason": issue["snapshot_id"] + ":" + str(issue["issue_index"])})
        for a in values:
            same_material_match = any(v.get("snapshot_id") == a.get("snapshot_id")
                and v["result"]["source_relation"] == "MATCH" for v in values)
            if a["result"]["source_relation"] != "MATCH" and not (
                    a["result"]["source_relation"] == "NOT_RELATED" and same_material_match):
                gaps.append({"case_id": cid, "kind": "SOURCE_" + a["result"]["source_relation"],
                    "reason": "Current material does not establish this mode's concrete mechanism"})
            if a["result"]["review_required"]:
                gaps.append({"case_id": cid, "kind": "FACT_CONFLICT", "reason": "; ".join(a["result"]["review_reasons"])})
            if any(r["relation"] in {"UNKNOWN", "PARTIAL"} for r in a["result"]["rows"]):
                gaps.append({"case_id": cid, "kind": "TRIGGER_UNKNOWNS", "reason": "Classification completed with explicit unknown/partial predicates"})
        for snapshot in _linked_snapshots(store, run_id, cid).values():
            if snapshot["status"] != "COMPLETE":
                gaps.append({"case_id": cid, "kind": "CAPTURE_" + snapshot["status"], "reason": snapshot["url"]})
            if not any(i["snapshot_id"] == snapshot["snapshot_id"] for i in _issues(store, run_id, cid)):
                gaps.append({"case_id": cid, "kind": "SUMMARY_MISSING", "reason": snapshot["url"]})
        for ref in store.records(run_id, "references"):
            if ref["case_id"] != cid:
                continue
            if policy["explicit_override"] and resource_kind(ref, case=subject["source_case"]) not in policy["collection_sources"]:
                gaps.append({"case_id": cid, "kind": "SOURCE_NOT_AVAILABLE_USER_POLICY",
                    "reason": ref["raw_text"] + ": " + policy["reason"]})
                continue
            if ref.get("url"):
                if resource_key(ref["url"]) not in snapshot_index(list(_linked_snapshots(store, run_id, cid).values())):
                    gaps.append({"case_id": cid, "kind": "SOURCE_NOT_CAPTURED", "reason": ref["raw_text"]})
            else:
                resolved = any(ref["ref_id"] in l.get("reference_ids", []) and l["outcome"] == "FOUND"
                               for l in store.records(run_id, "trigger_source_lookups"))
                if not resolved:
                    gaps.append({"case_id": cid, "kind": "SOURCE_IDENTIFIER_UNRESOLVED", "reason": ref["raw_text"]})
    state = store.get(run_id, "workflow_state", "current") or {}
    for bid in state.get("block_ids", []):
        block = store.get(run_id, "workflow_blocks", bid)
        gaps.append({"case_id": ";".join(block.get("case_ids", [])), "kind": block["reason"], "reason": str(block.get("details", block.get("input_budget", "")))})
    for tid in state.get("task_ids", []):
        if not store.get(run_id, "workflow_results", tid):
            gaps.append({"case_id": "", "kind": "TASK_PENDING", "reason": tid})
    relations = source_relations(store, run_id) if cfg["phase"] == "INIT" else {}
    active = snapshot_index(store.active_snapshots(run_id))
    resources = []
    for ref in store.records(run_id, "references"):
        snapshot = active.get(resource_key(ref["url"])) if ref.get("url") else None
        resources.append({**ref, "snapshot_id": (snapshot or {}).get("snapshot_id"),
            "capture_status": (snapshot or {}).get("status", "NOT_FETCHED"),
            "source_relation": relations.get((ref["case_id"], (snapshot or {}).get("snapshot_id")), "UNASSESSED")})
    baseline = store.get(run_id, "trigger_baseline_refs", "baseline")
    if cfg["phase"] == "INIT":
        head = store.get(run_id, "trigger_baseline_heads", "current") or {}
        baseline = store.get(run_id, "trigger_baselines", head.get("baseline_id", ""))
    if baseline:
        source_run = baseline["run_id"]
        if baseline["index_hash"] != _index_identity(store, source_run):
            baseline = {**baseline, "status": "STALE"}
            gaps.append({"case_id": "", "kind": "BASELINE_STALE", "reason": "Maintain initialization before incremental decisions"})
    gaps = list({digest(g): g for g in gaps}.values())
    return {"run_id": run_id, "phase": cfg["phase"], "taxonomy": _taxonomy(store, run_id), "subjects": subjects,
        "assessments": assessments, "wiki_checks": checks, "resources": resources,
        "gaps": gaps, "baseline": baseline}


def status(store, run_id):
    data = _projection(store, run_id)
    values = data["assessments"]
    return {"run_id": run_id, "phase": data["phase"], "subject_count": len(data["subjects"]),
        "assessment_count": len(values), "assessed_subject_count": len({a["subject_id"] for a in values}),
        "trigger_count": len(data["taxonomy"]["items"]), "gap_count": len(data["gaps"]),
        "gaps": data["gaps"], "review_count": sum(a["result"]["review_required"] for a in values),
        "coverage_kind": "HISTORICAL_EVIDENCE", "execution_verified": False}


def _index_identity(store, run_id):
    from .xlsx_workflow import _policy
    return digest({"catalog": _catalog(store, run_id), "taxonomy": _taxonomy(store, run_id),
        "policy": _policy(), "subjects": store.records(run_id, "trigger_subjects"),
        "bases": [_basis(store, run_id, s) for s in store.records(run_id, "trigger_subjects")],
        "assessments": [a["assessment_id"] for a in current_assessments(store, run_id)]})


def finalize(store, run_id, *, allow_pending=False):
    from .evidence_plan import collection_source_policy
    if _settings(store, run_id)["phase"] != "INIT":
        raise AuditError("Only an initialization run can maintain a baseline")
    data = _projection(store, run_id)
    missing = {s["subject_id"] for s in data["subjects"]} - {a["subject_id"] for a in data["assessments"]}
    if missing or any(g["kind"] in {"ISSUE_UNASSESSED", "TASK_PENDING"} for g in data["gaps"]):
        raise AuditError("Every original mode and current source issue needs an assessment; pending tasks cannot be finalized")
    informational = {"TRIGGER_UNKNOWNS", "CAPTURE_PARTIAL", "CAPTURE_CONTENT_CAPTURED", "BASELINE_STALE",
                     "WIKI_NOT_SUPPORTED", "SOURCE_NOT_AVAILABLE_USER_POLICY"}
    blocking = [g for g in data["gaps"] if g["kind"] not in informational]
    if blocking and not allow_pending:
        raise AuditError("Initialization has explicit gaps; finish them or finalize a provisional baseline with --allow-pending")
    details = []
    for a in data["assessments"]:
        if a["result"]["source_relation"] != "MATCH" or a["result"]["review_required"]:
            continue
        for detail in a["result"]["details"]:
            if detail["evidence_basis"] in {"SOURCE_REPORTED", "CODE_INFERENCE"}:
                labels = [r for r in a["result"]["rows"] if r["trigger_id"] in detail["trigger_ids"]]
                details.append({**detail, "trigger_ids": [r["trigger_id"] for r in labels if r["relation"] == "MATCH"],
                    "trigger_assessments": labels, "detail_id": a["assessment_id"] + ":" + detail["detail_id"],
                    "assessment_id": a["assessment_id"], "snapshot_id": a["snapshot_id"], "issue_index": a["issue_index"]})
    identity = _index_identity(store, run_id)
    baseline = {"baseline_id": "trigger-baseline-" + identity[:24], "run_id": run_id,
        "status": "READY_WITH_GAPS" if blocking else "READY", "index_hash": identity,
        "taxonomy_id": _settings(store, run_id)["taxonomy_id"], "mode_ids": [i["item_id"] for i in _catalog(store, run_id)],
        "catalog_scope": store.get(run_id, "catalog_selections", "frozen"),
        "collection_source_policy": collection_source_policy(store, run_id),
        "assessment_ids": [a["assessment_id"] for a in data["assessments"]], "coverage_details": details,
        "gaps": data["gaps"], "coverage_kind": "HISTORICAL_EVIDENCE", "execution_verified": False}
    store.put(run_id, "trigger_baselines", baseline["baseline_id"], baseline)
    store.put(run_id, "trigger_baseline_heads", "current", {"baseline_id": baseline["baseline_id"]}, mutable=True)
    return baseline


def _baseline(store, run_id, baseline_id=None, *, allow_pending=False):
    head = store.get(run_id, "trigger_baseline_heads", "current") or {}
    baseline = store.get(run_id, "trigger_baselines", baseline_id or head.get("baseline_id", ""))
    if not baseline:
        raise AuditError("Initialize and finalize the original library before classifying new cases")
    if baseline["index_hash"] != _index_identity(store, run_id):
        raise AuditError("Initialized baseline is stale; maintain/finalize it again without deleting history")
    if baseline["status"] != "READY" and not allow_pending:
        raise AuditError("Baseline has gaps; complete initialization or explicitly allow a provisional baseline")
    return baseline


def start_incremental(store, source, baseline_run, work_root, *, executor="opencode", baseline_id=None,
                      allow_pending_baseline=False):
    from .pipeline import import_into
    from .evidence_plan import register_search_policy
    baseline = _baseline(store, baseline_run, baseline_id, allow_pending=allow_pending_baseline)
    catalog = _catalog(store, baseline_run)
    if source.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise AuditError("New cases require structured XLSX; arbitrary layouts/Word/PPT remain TODO")
    if executor not in {"codex", "opencode"}:
        raise AuditError("Executor must be codex or opencode")
    imported = import_cases(source, "LEGACY_TABLE")
    if not imported["cases"] or not any(c["description"] for c in imported["cases"]):
        raise AuditError("Structured XLSX needs a recognized problem-description header")
    run_id = store.create_run({"workflow": RULE_VERSION, "purpose": "TRIGGER_INCREMENTAL"})
    directory = (work_root / run_id).resolve()
    if directory.is_relative_to(store.root):
        raise AuditError("Workflow files must be outside state")
    import_into(store, run_id, imported)
    # Copy the frozen original catalog, its identity and source anchors verbatim.
    catalog_meta = store.get(baseline_run, "catalog_selections", "frozen")
    library = {"items": catalog, "documents": [d for d in store.records(baseline_run, "documents") if d.get("source_kind") == "CATALOG"],
               "warnings": [], "catalog_identity": catalog_meta}
    import_into(store, run_id, library, catalog=True)
    selected = sorted(c["case_id"] for c in imported["cases"])
    cfg = {"run_id": run_id, "directory": str(directory), "executor": executor,
        "source_hash": imported["documents"][0]["source_sha256"], "rule_version": RULE_VERSION,
        "selected_case_ids": selected, "scope_hash": digest(selected), "purpose": "TRIGGER_INCREMENTAL",
        "capture_quality_required": True, "max_search_rounds": 3, "capture_attempts_per_resource": 3}
    store.put(run_id, "xlsx_workflow", "config", cfg)
    source_policy = baseline.get("collection_source_policy", {})
    if source_policy.get("explicit_override"):
        from .xlsx_workflow import configure_collection
        configure_collection(store, run_id, source_policy["collection_sources"],
            wiki_policy=source_policy["wiki_policy"], reason=source_policy["reason"])
    else:
        register_search_policy(store, run_id, {"required_sources": ["WIKI"]})
    frozen = _taxonomy(store, baseline_run)
    store.put(run_id, "trigger_taxonomies", frozen["taxonomy_id"], frozen)
    store.put(run_id, "trigger_baseline_refs", "baseline", baseline)
    store.put(run_id, "trigger_config", "config", {"phase": "INCREMENTAL", "taxonomy_id": frozen["taxonomy_id"],
        "baseline_run": baseline_run, "baseline_id": baseline["baseline_id"], "allow_pending_baseline": allow_pending_baseline,
        "catalog_hash": digest(catalog), "rule_version": RULE_VERSION})
    for case in store.records(run_id, "cases"):
        subject = {"subject_id": "case-subject-" + digest(case["case_id"])[:24],
            "case_id": case["case_id"], "subject_kind": "FAULT_CASE"}
        store.put(run_id, "trigger_subjects", subject["subject_id"], subject)
    return {**cfg, "purpose": "TRIGGER_INCREMENTAL", "baseline_id": baseline["baseline_id"]}


def export(store, run_id):
    from .xlsx_workflow import config
    from .trigger_report import build_workbook
    from .exporters import export_workbook_xlsx
    cfg = config(store, run_id)
    data = _projection(store, run_id)
    workbook = build_workbook(data)
    output = Path(cfg["directory"]) / "output"
    output.mkdir(parents=True, exist_ok=True)
    name = "模式初始化及覆盖详情.xlsx" if data["phase"] == "INIT" else "故障分类及分支建议.xlsx"
    with tempfile.TemporaryDirectory(prefix="trigger-xlsx-", dir=Path(cfg["directory"])) as scratch:
        source = Path(scratch) / "workbook.json"
        source.write_text(json.dumps(workbook, ensure_ascii=False), encoding="utf-8")
        result = export_workbook_xlsx(source, Path(scratch) / name)
        Path(result["xlsx"]).replace(output / name)
    result.update(xlsx=str(output / name), status="COMPLETE_WITH_PENDING" if data["gaps"] else "COMPLETE",
                  gap_count=len(data["gaps"]), coverage_kind="HISTORICAL_EVIDENCE", execution_verified=False)
    store.event(run_id, "trigger_export", result)
    return result
