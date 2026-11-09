"""Initialize historical mechanism/trigger coverage, then assess new cases.

This layer reuses the collection, independent summary and fresh-context driver.
A library definition is an evidence subject, never an invented incident. All
indexes are projections of current cited assessments; formal adoption is separate.
"""
from __future__ import annotations

from .run_budget import scoped as run_scoped

import json
import re
import tempfile
from pathlib import Path

from .contracts import SourceCase
from .importers import import_cases, import_catalog
from .resource_identity import resource_key, snapshot_index
from .store import AuditError, Store, digest
from .trigger_assessment import CLASSIFICATION_FRAMEWORK, instructions, response_schema, validate_assessment
from .trigger_taxonomy import builtin_user_branches, load_taxonomy

RULE_VERSION = "cann-baseline-builder-0.1.19"


def _settings(store, run_id):
    value = store.get(run_id, "trigger_config", "config")
    if not value:
        raise AuditError("Start a trigger initialization/classification run first")
    return value


def _catalog(store, run_id):
    return sorted(store.records(run_id, "catalog"), key=lambda x: x["item_id"])


def start_init(store: Store, modes: Path, taxonomy: Path, work_root: Path, *,
               executor="opencode", branch_source=None, user_branches=True,
               catalog_scope="ORIGINAL_MECHANISM_LIBRARY", basis="HISTORICAL_EVIDENCE",
               v4_source=None, capabilities=None, sparse=False, with_designs=False, baseline_builder=False, expected_mode_count=None,
               input_budget_chars=None) -> dict:
    from .evidence_plan import register_search_policy
    from .pipeline import import_into
    if executor not in {"opencode", "codex"}:
        raise AuditError("Executor must be opencode or codex")
    if basis not in {"HISTORICAL_EVIDENCE", "SOURCE_DEFINITIONS"}:
        raise AuditError("Init basis must be HISTORICAL_EVIDENCE or SOURCE_DEFINITIONS")
    if baseline_builder:
        basis = "SOURCE_DEFINITIONS"
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
        "capture_quality_required": True, "max_search_rounds": 3, "capture_attempts_per_resource": 3,
        "init_basis": basis}
    store.put(run_id, "xlsx_workflow", "config", cfg)
    from .run_budget import pin
    from .input_budget import get_budget_chars
    pin(store, run_id, get_budget_chars() if input_budget_chars is None else input_budget_chars, reason="WORKFLOW_START")
    store.put(run_id, "trigger_config", "config", {"phase": "INIT", "taxonomy_id": frozen["taxonomy_id"],
        "catalog_hash": digest(_catalog(store, run_id)), "rule_version": RULE_VERSION, "basis": basis,
        "classification_framework": CLASSIFICATION_FRAMEWORK})
    register_search_policy(store, run_id, {"required_sources": ["WIKI"]})
    if v4_source is not None:
        configure_v4(store, run_id, v4_source, capabilities=capabilities)
    if sparse:
        configure_v5(store, run_id, with_designs=with_designs)
    if baseline_builder:
        from .cann_baseline import configure
        configure(store, run_id, expected_mode_count=expected_mode_count)
    return {**cfg, "classification_contract": _settings(store, run_id).get("classification_contract", "DENSE_V1"),
        **{k: _settings(store, run_id)[k] for k in ("knowledge_profile", "api42_registry_id", "input_condition_scheme") if k in _settings(store, run_id)},
        "mode_count": len(subjects), "trigger_count": len(frozen["items"]),
        "branch_categories": [c["id"] for b in frozen["branches"] for c in b.get("categories", [])]}


def _taxonomy(store, run_id):
    return store.get(run_id, "trigger_taxonomies", _settings(store, run_id)["taxonomy_id"])


def _v4(store, run_id):
    key = _settings(store, run_id).get("v4_taxonomy_id")
    return store.get(run_id, "trigger_v4_taxonomies", key) if key else None


@run_scoped
def configure_v5(store, run_id, *, with_designs=False):
    """Opt an Init into V5 without rewriting sources, responses or verdicts."""
    from .trigger_sparse import CONTRACT
    settings = _settings(store, run_id)
    if settings["phase"] != "INIT":
        raise AuditError("Maintain the Init in V5, then create a linked incremental run")
    if settings.get("classification_contract") == CONTRACT and settings.get("design_tasks_enabled", False) == with_designs:
        return {"run_id": run_id, "classification_contract": CONTRACT, "idempotent": True}
    store.put(run_id, "trigger_config", "config", {**settings,
        "classification_contract": CONTRACT, "rule_version": RULE_VERSION, "design_tasks_enabled": with_designs}, mutable=True)
    from .xlsx_workflow import config
    cfg = config(store, run_id)
    store.put(run_id, "xlsx_workflow", "config", {**cfg, "rule_version": RULE_VERSION}, mutable=True)
    store.event(run_id, "trigger_v5_configured", {"previous_contract": settings.get("classification_contract", "DENSE_V1"),
        "classification_contract": CONTRACT, "design_tasks_enabled": with_designs, "sources_rewritten": False, "human_accept_inherited": False})
    return {"run_id": run_id, "classification_contract": CONTRACT}


@run_scoped
def configure_v4(store, run_id, source, *, capabilities=None):
    """Freeze a versioned interpretation without overwriting any old definition."""
    from .trigger_v4 import load_v4, revise_42, freeze_mapping, PROFILE, LEGACY_VERSION
    from .xlsx_workflow import config
    settings = _settings(store, run_id)
    if settings["phase"] != "INIT":
        raise AuditError("Maintain V4 on Init, then use its newly frozen baseline for a linked incremental run")
    current = _taxonomy(store, run_id)
    original = store.get(run_id, "trigger_taxonomies", current.get("original_taxonomy_id", current["taxonomy_id"]))
    frozen = load_v4(Path(source))
    revised = revise_42(original)
    mapping = freeze_mapping(original, revised, frozen)
    capabilities = capabilities or {"classes": {}, "methods": {}, "provenance": "NOT_PROVIDED"}
    if not isinstance(capabilities, dict) or set(capabilities) - {"classes", "methods", "provenance"}:
        raise AuditError("Capabilities are declared design constraints, not execution results")
    if not capabilities.get("provenance") or not isinstance(capabilities.get("classes", {}), dict) or not isinstance(capabilities.get("methods", {}), dict):
        raise AuditError("Capabilities need provenance and class/method dictionaries")
    for key, entry in capabilities.get("classes", {}).items():
        if key not in {v["id"] for v in frozen["items"]} or entry.get("construction") not in {"UNKNOWN", "BLOCKED", "DECLARED_SUPPORTED"} or not entry.get("reason"):
            raise AuditError("Class capability needs a V4 ID, declared status and reason")
    for key, entry in capabilities.get("methods", {}).items():
        if key not in {v["method_id"] for v in frozen["methods"]} or entry.get("availability") not in {"UNKNOWN", "BLOCKED", "DECLARED_SUPPORTED"} or not entry.get("reason"):
            raise AuditError("Method capabilities describe declared availability, never successful execution")
    store.put(run_id, "trigger_original_definitions", original["taxonomy_id"],
        {"definition_version": LEGACY_VERSION, "taxonomy": original})
    store.put(run_id, "trigger_taxonomies", revised["taxonomy_id"], revised)
    store.put(run_id, "trigger_v4_taxonomies", frozen["taxonomy_id"], frozen)
    store.put(run_id, "trigger_mappings", mapping["mapping_id"], mapping)
    updated = {**settings, "taxonomy_id": revised["taxonomy_id"], "v4_taxonomy_id": frozen["taxonomy_id"],
        "mapping_id": mapping["mapping_id"], "classification_profile": PROFILE,
        "execution_capabilities": capabilities, "rule_version": RULE_VERSION}
    store.put(run_id, "trigger_config", "config", updated, mutable=True)
    cfg = config(store, run_id)
    store.put(run_id, "xlsx_workflow", "config", {**cfg, "rule_version": RULE_VERSION}, mutable=True)
    store.event(run_id, "trigger_v4_configured", {"previous_taxonomy_id": current["taxonomy_id"],
        "taxonomy_id": revised["taxonomy_id"], "v4_taxonomy_id": frozen["taxonomy_id"], "mapping_id": mapping["mapping_id"]})
    if settings.get("knowledge_profile"):
        from .cann_baseline import configure
        configure(store, run_id)
    return {"run_id": run_id, "classification_profile": PROFILE, "legacy_version": LEGACY_VERSION,
        "revised_version": revised["definition_version"], "v4_version": frozen["definition_version"],
        "categories": 31, "constructions": 55, "mounts": 64, "guides": 195,
        "execution_implemented": False}


def _model_taxonomy(frozen):
    """All 42 predicates and applicability rules, without repeated quote copies.

    The source and full parsed document remain frozen in SQLite. Generator/N
    allocation instructions govern a different execution workflow, not this
    historical evidence classifier. They are explicitly outside this task.
    """
    value = {k: frozen[k] for k in ("taxonomy_id", "taxonomy_hash", "source_file", "source_sha256", "item_count")}
    value["items"] = [{k: item[k] for k in ("id", "family_id", "name", "definition", "requires", "skip_if", "line_start", "line_end") if k in item}
                       for item in frozen["items"]]
    for item, source in zip(value["items"], frozen["items"]):
        item.update({k: source[k] for k in ("allowed_fact_roles", "family_requires_override", "family_skip_override",
            "construction_requires", "analysis_requires", "revision_reason") if k in source})
    value.update({k: frozen[k] for k in ("definition_version", "original_definition_version", "original_taxonomy_id",
        "branch_comparison_scope") if k in frozen})
    value["families"] = frozen.get("families", [])
    value["context"] = {k: v for k, v in frozen.get("context", {}).items() if k in {"scope", "applicability"}}
    value["branches"] = [{k: v for k, v in b.items() if k not in {"source_sha256", "source_file"}}
                         for b in frozen.get("branches", [])]
    value["input_scope"] = {"trigger_ids": [i["id"] for i in frozen["items"]], "item_count": 42,
        "included": "All definitions, local/family Requires/Skip and global scope/applicability",
        "excluded": "Duplicate item source_quote copies; generator N-allocation/execution instructions outside historical classification"}
    value["classification_boundaries"] = {
        "description_and_confirmation_separate": True,
        "input_values_are_not_intermediate_values": True,
        "control_arguments_require_exposed_api_controls": True,
        "ordinary_versions_are_not_build_variants": True,
        "branch3_full_applicability_requires": ["same arguments", "same binary"],
        "unknown_condition_fields_do_not_request_more_searches": True}
    return value


def _model_catalog(items):
    """Complete comparison definitions, separate from a full source-document audit.

    The original raw records remain immutable in Store. Normalized definition
    fields and all boundary/category/example fields are copied in full; repeated
    source chapters and quote bundles are not part of this comparison view.
    """
    result = []
    for item in items:
        raw = item.get("raw", {})
        value = {k: item[k] for k in ("item_id", "description", "operator", "mechanism", "trigger",
            "source_file", "source_sha256", "source_location", "sheet", "row") if k in item}
        value["raw"] = {key: raw[key] for key in ("三级", "四级", "边界", "未知", "代表子案例") if key in raw}
        result.append(value)
    return result


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
    from .evidence_plan import source_relation
    snapshots = _linked_snapshots(store, run_id, case_id)
    case = store.get(run_id, "cases", case_id)
    refs = [r for r in store.records(run_id, "references") if r["case_id"] == case_id and r.get("url")]
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
                fact_refs = fact.get("evidence", [])
                if fact.get("value") in (None, "", [], {}) or not fact_refs or check_citations(fact_refs, snapshot):
                    continue
                identity = {"summary_task_id": summary["task_id"], "issue_label": issue["label"],
                    "issue_index": index, "field": fact["field"], "value": fact["value"], "evidence": fact_refs}
                facts.append({"fact_id": "fact-" + digest(identity)[:24], **identity})
            selected = {r["segment_id"] for f in facts for r in f["evidence"]}
            view = {k: snapshot[k] for k in ("snapshot_id", "url", "status", "title", "text_sha256") if k in snapshot}
            view["segments"] = [s for s in snapshot["segments"] if s["segment_id"] in selected]
            scope = {"scope": "ISSUE_CITED_SEGMENTS", "provided_segment_ids": sorted(selected),
                "total_snapshot_segments": len(snapshot["segments"]), "full_text_verified": False}
            grades = {source_relation(case, r)["relation"] for r in refs
                      if resource_key(r["url"]) == resource_key(snapshot["url"])}
            confirmed = any(a["case_id"] == case_id and a.get("snapshot_id") == snapshot["snapshot_id"]
                and a.get("user_confirmed") for a in store.records(run_id, "evidence_associations"))
            reference_relation = ("USER_CONFIRMED" if confirmed else "SOURCE_CELL_LINKED" if "SOURCE_CELL_LINKED" in grades
                else "LEGACY_TABLE_LINKED" if "LEGACY_TABLE_LINKED" in grades else "SEARCH_DISCOVERED")
            issues.append({"snapshot_id": snapshot["snapshot_id"], "summary_task_id": summary["task_id"],
                "issue_index": index, "label": issue["label"], "facts": facts,
                "snapshot": view, "input_scope": scope, "reference_relation": reference_relation})
    return issues


@run_scoped
def _basis(store, run_id, subject, snapshot_id=None):
    """No plan calls: source routing calls this function, so it cannot recurse."""
    from .pipeline import current_summaries
    from .evidence_plan import collection_source_policy
    cid = subject["case_id"]
    settings = _settings(store, run_id)
    if settings.get("knowledge_profile") and settings["phase"] == "INIT":
        from .baseline_recovery import definition_dependency
        return digest({"definition": definition_dependency(store, run_id, subject),
                       "contract": settings.get("classification_contract"), "basis": "SOURCE_DEFINITIONS"})
    profile_identity = {k: settings[k] for k in ("classification_profile", "v4_taxonomy_id", "mapping_id", "execution_capabilities", "classification_contract", "knowledge_profile", "input_condition_scheme", "api42_registry_id") if k in settings}
    if settings.get("knowledge_profile") and settings["phase"] == "INIT":
        from .cann_baseline import current_definitions
        profile_identity["mode_definition"] = [digest(d["result"]) for d in current_definitions(store, run_id) if d["subject_id"] == subject["subject_id"]]
    if settings["phase"] == "INIT" and settings.get("basis") == "SOURCE_DEFINITIONS":
        return digest({"subject": subject, "source": store.get(run_id, "cases", cid),
            "taxonomy": _taxonomy(store, run_id), "catalog": _catalog(store, run_id),
            "assessment_basis": "SOURCE_DEFINITIONS", "classification_profile": profile_identity})
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
        "collection_policy": collection_source_policy(store, run_id)["policy_hash"],
        "assessment_basis": settings.get("basis", "HISTORICAL_EVIDENCE"), "classification_profile": profile_identity}
    if not snapshot_id:
        base["wiki_checks"] = sorted(digest(c) for c in store.records(run_id, "wiki_checks") if c["case_id"] == cid)
    if settings["phase"] == "INCREMENTAL":
        from .pipeline import current_judgments, current_mappings
        # Include the live maintained source identity, not only its old ID.
        base["baseline_live_hash"] = _index_identity(store, settings["baseline_run"])
        base["judgments"] = sorted(digest(j) for j in current_judgments(store, run_id) if j["case_id"] == cid)
        base["mappings"] = sorted(digest(m) for m in current_mappings(store, run_id) if m["case_id"] == cid)
    return digest(base)


@run_scoped
def current_assessments(store, run_id):
    from .xlsx_workflow import _policy
    subjects = {s["subject_id"]: s for s in store.records(run_id, "trigger_subjects")}
    bases = {}
    def basis(record):
        if record.get("baseline_axis") and _settings(store, run_id).get("knowledge_profile"):
            from .baseline_recovery import axis_basis
            return axis_basis(store, run_id, subjects[record["subject_id"]], record["baseline_axis"]) if record["subject_id"] in subjects else None
        key = (record["subject_id"], record.get("snapshot_id"))
        if key not in bases and key[0] in subjects:
            bases[key] = _basis(store, run_id, subjects[key[0]], key[1])
        value = bases.get(key)
        return digest({"base": value, "axis": record["baseline_axis"]}) if record.get("baseline_axis") else value
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


@run_scoped
def classification_payloads(store, run_id, *, for_baseline_axes=False):
    from .pipeline import current_judgments, current_mappings
    settings, taxonomy = _settings(store, run_id), _model_taxonomy(_taxonomy(store, run_id))
    if settings.get("knowledge_profile") and settings["phase"] == "INIT" and not for_baseline_axes:
        return
    baseline = store.get(run_id, "trigger_baseline_refs", "baseline")
    if baseline:
        # Gaps, source policy and assessment indexes are bookkeeping, not additional
        # semantic input. Keep the complete frozen mechanism/detail definitions.
        baseline = {k: baseline[k] for k in ("baseline_id", "run_id", "status", "index_hash", "mode_ids",
            "catalog_scope", "coverage_kind", "coverage_details", "declared_details", "execution_verified",
            "knowledge_profile", "mode_records", "input_condition_scheme") if k in baseline}
        if baseline.get("declared_details"):
            # Original partial trigger rationales are retained in state; the
            # complete mechanism/condition definitions and source anchors below
            # are the semantic baseline for this independent comparison axis.
            baseline["declared_details"] = [{k: v for k, v in detail.items() if k != "trigger_assessments"}
                for detail in baseline["declared_details"]]
    catalog = _catalog(store, run_id)
    definition_init = settings["phase"] == "INIT" and settings.get("basis") == "SOURCE_DEFINITIONS"
    v4 = _v4(store, run_id)
    assessments = current_assessments(store, run_id)
    definitions = {}
    if settings.get("knowledge_profile") and settings["phase"] == "INIT":
        from .cann_baseline import current_definitions
        definitions = {d["subject_id"]: d for d in current_definitions(store, run_id)}
    for subject in sorted(store.records(run_id, "trigger_subjects"), key=lambda s: s["subject_id"]):
        cid = subject["case_id"]
        if settings.get("knowledge_profile") and settings["phase"] == "INIT" and subject["subject_id"] not in definitions:
            continue
        issues = ([None] if definition_init else _issues(store, run_id, cid) or [None])
        for issue in issues:
            key = (subject["subject_id"], (issue or {}).get("snapshot_id"), (issue or {}).get("summary_task_id"), (issue or {}).get("issue_index"))
            if not for_baseline_axes and any((a["subject_id"], a.get("snapshot_id"), a.get("summary_task_id"), a.get("issue_index")) == key for a in assessments):
                continue
            judgments, mappings = [], []
            if settings["phase"] == "INCREMENTAL":
                sid, label = (issue or {}).get("snapshot_id"), (issue or {}).get("label")
                judgments = [j for j in current_judgments(store, run_id) if j["case_id"] == cid
                    and j["snapshot_id"] == sid and (j.get("applicable_issue") or {}).get("label") == label]
                mappings = [m for m in current_mappings(store, run_id) if m["case_id"] == cid]
            payload = {"phase": settings["phase"], "classification_framework": CLASSIFICATION_FRAMEWORK,
                "evaluation_order": ["condition_facts", "rows", "external_branches", "details", "declared_comparison", "decision"],
                "subject": {**subject, "source_case": store.get(run_id, "cases", cid)},
                "assessment_basis": settings.get("basis", "HISTORICAL_EVIDENCE"),
                "taxonomy": taxonomy, "source_issue": issue,
                "wiki_check": {"records": [c for c in store.records(run_id, "wiki_checks") if c["case_id"] == cid],
                    "rule": ("Not requested: explicit source-definition Init; no webpage verification claimed" if definition_init
                        else "Wiki first; blocked access is a collection gap, not a negative mechanism judgment")},
                "mechanism_catalog": ([{"item_id": subject["mode_id"], "definition_source": "subject.source_case.raw"}]
                    if settings["phase"] == "INIT" else _model_catalog(catalog)),
                "baseline": baseline, "judgments": judgments, "mappings": mappings,
                "input_scope": {"catalog_mode_ids": [subject["mode_id"]] if settings["phase"] == "INIT"
                    else [item["item_id"] for item in catalog], "catalog_definitions_complete": True,
                    "declared_detail_count": len((baseline or {}).get("declared_details", [])),
                    "definition_init_only": definition_init,
                    "catalog_view": "ORIGINAL_SUBJECT_RAW" if settings["phase"] == "INIT"
                        else "COMPLETE_DEFINITION_COMPARISON_PROJECTION",
                    "catalog_included_fields": ["item_id", "description", "operator", "mechanism", "trigger",
                        "三级", "四级", "边界", "未知", "代表子案例", "source_file", "source_sha256", "source_location", "sheet", "row"],
                    "subject_original_raw_complete": settings["phase"] == "INIT",
                    "full_source_document_audit": False,
                    "full_original_records_frozen_in_store": True,
                    "comparison_projection_excludes": "Repeated raw source chapters/quote bundles and prior trigger rationales; all definitions and mechanism detail fields are retained in full"},
                "basis_hash": _basis(store, run_id, subject, (issue or {}).get("snapshot_id")),
                "case_ids": [cid], "response_schema": response_schema(include_v4=bool(v4))}
            payload.update(input_condition_scheme=settings.get("input_condition_scheme", "REVISED42"))
            if settings.get("knowledge_profile"):
                payload["knowledge_profile"] = settings["knowledge_profile"]
                if subject["subject_id"] in definitions:
                    from .baseline_recovery import technical_projection
                    payload["normalized_mode"] = technical_projection(definitions[subject["subject_id"]]["result"])
            if v4:
                from .trigger_v4 import model_v4
                mapping = store.get(run_id, "trigger_mappings", settings["mapping_id"])
                payload.update(classification_profile=settings["classification_profile"], v4_taxonomy=model_v4(v4),
                    mapping={k: mapping[k] for k in ("mapping_id", "mapping_version", "source_definition_version",
                        "revised_definition_version", "relation_direction", "purpose", "rows")},
                    execution_capabilities=settings["execution_capabilities"],
                    evaluation_order=["condition_facts", "v4_rows", "rows", "external_branches", "details", "declared_comparison", "decision"])
            if settings.get("classification_contract") == "SPARSE_SCENARIOS_V5":
                from .trigger_sparse import CONTRACT, schema, frame_version
                payload.update(classification_contract=CONTRACT, response_schema=schema(),
                    frame_versions={scheme: frame_version(payload, scheme)
                        for scheme in ([settings.get("input_condition_scheme", "REVISED42"), "BRANCH", "V4"] if v4
                            else [settings.get("input_condition_scheme", "REVISED42"), "BRANCH"])},
                    evaluation_order=["condition_facts", "details", "scenarios", "rows", "v4_rows",
                        "external_branches", "label_links", "classification_summary", "declared_comparison", "candidate_proposal", "decision"])
                payload["input_scope"].update(output_rule_scope="SELECTED_RULES", omitted_rules="NOT_ASSESSED")
            if settings.get("knowledge_profile"):
                payload["mapping_document_status"] = "NOT_PROVIDED"
                if payload.get("mapping"):
                    payload["mapping"] = {k:v for k,v in payload["mapping"].items() if k != "rows"}
            yield payload


def classification_instructions(payload):
    if payload.get("classification_contract") == "SPARSE_SCENARIOS_V5":
        from .trigger_sparse import instructions as sparse_instructions
        return sparse_instructions()
    text = instructions()
    if payload.get("v4_taxonomy"):
        from .trigger_v4_assessment import instructions as v4_instructions
        text = text.replace("The primary framework is the 42 INPUT conditions plus Branch 2/3.",
            "The primary framework is V4's 31 categories/55 constructions plus Branch 2/3; rows is the independent revised-42 compatibility frame.")
        text = text.replace("extract condition_facts, assess all 42 rows and Branch 2/3, organize",
            "extract condition_facts, assess all V4 rows/constructions, independently assess revised 42 rows and Branch 2/3, organize")
        text = text.replace("All 1.C positives need a stated API-control fact, not an internal algorithm name.",
            "The revised-42 API-control items retain their own allowed-role metadata; V4 C2/C4 separately allow traced input-driven paths.")
        text = v4_instructions() + "\n" + text
        text += "\nFor revised rows use each item's allowed_fact_roles and family overrides. The original 1.3 family exclusion does not apply to revised 1.3.2.\n"
    return text


@run_scoped
def accept_assessment(store, run_id, request, response):
    from .xlsx_workflow import _policy, config
    payload = request["payload"]
    if payload.get("classification_framework") != CLASSIFICATION_FRAMEWORK:
        raise AuditError("Classification requires the current conditions-first policy; regenerate old requests")
    settings = _settings(store, run_id)
    if settings.get("knowledge_profile") and settings["phase"] == "INIT":
        from .xlsx_workflow import check_current_request
        check_current_request(store, run_id, request)
    if (payload.get("phase") != settings["phase"]
            or payload.get("assessment_basis", "HISTORICAL_EVIDENCE") != settings.get("basis", "HISTORICAL_EVIDENCE")):
        raise AuditError("Classification phase/basis differs from the frozen workflow configuration")
    if settings.get("knowledge_profile"):
        if payload.get("knowledge_profile") != settings["knowledge_profile"]:
            raise AuditError("Classification must use the current knowledge lifecycle contract")
        if settings["phase"] == "INIT" and not payload.get("normalized_mode"):
            raise AuditError("Normalize the original mode before classifying it")
    subject = store.get(run_id, "trigger_subjects", payload["subject"]["subject_id"])
    expected_basis = _basis(store, run_id, subject, (payload.get("source_issue") or {}).get("snapshot_id")) if subject else None
    if payload.get("baseline_axis"):
        if settings.get("knowledge_profile"):
            from .baseline_recovery import axis_basis
            expected_basis = axis_basis(store, run_id, subject, payload["baseline_axis"]) if subject else None
        else:
            expected_basis = digest({"base": expected_basis, "axis": payload["baseline_axis"]})
    if not subject or payload["basis_hash"] != expected_basis:
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
        **({"baseline_axis": payload["baseline_axis"]} if payload.get("baseline_axis") else {}),
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


@run_scoped
def _projection(store, run_id, *, include_baseline_review=True):
    from .wiki_checks import wiki_plan
    from .evidence_plan import collection_source_policy, resource_kind
    policy = collection_source_policy(store, run_id)
    cfg = _settings(store, run_id)
    definition_init = cfg["phase"] == "INIT" and cfg.get("basis") == "SOURCE_DEFINITIONS"
    assessments = current_assessments(store, run_id)
    subjects = [{**s, "source_case": store.get(run_id, "cases", s["case_id"])}
                for s in store.records(run_id, "trigger_subjects")]
    checks = {s["case_id"]: ({"status": "NOT_REQUESTED", "reason": "Explicit source-definition initialization"}
        if definition_init else wiki_plan(store, run_id, s["source_case"])) for s in subjects}
    gaps = []
    for subject in subjects:
        cid = subject["case_id"]
        if not definition_init and checks[cid]["status"] not in {"FOUND", "NO_MATCH"}:
            gaps.append({"case_id": cid, "kind": "WIKI_" + checks[cid]["status"], "reason": checks[cid].get("reason", "Wiki check pending")})
        values = [a for a in assessments if a["subject_id"] == subject["subject_id"]]
        if not values:
            gaps.append({"case_id": cid, "kind": "UNASSESSED", "reason": "No current classification result"})
        for issue in ([] if definition_init else _issues(store, run_id, cid)):
            if not any(a.get("snapshot_id") == issue["snapshot_id"] and a.get("summary_task_id") == issue["summary_task_id"]
                       and a.get("issue_index") == issue["issue_index"] for a in values):
                gaps.append({"case_id": cid, "kind": "ISSUE_UNASSESSED",
                    "reason": issue["snapshot_id"] + ":" + str(issue["issue_index"])})
        for a in values:
            summary = a["result"].get("classification_summary", {})
            if summary.get("status") == "INSUFFICIENT_INFORMATION":
                gaps.append({"case_id": cid, "kind": "CLASSIFICATION_INFORMATION_GAP", "reason": summary["reason"]})
            same_material_match = any(v.get("snapshot_id") == a.get("snapshot_id")
                and v["result"]["source_relation"] == "MATCH" for v in values)
            if not definition_init and a["result"]["source_relation"] != "MATCH" and not (
                    a["result"]["source_relation"] == "NOT_RELATED" and same_material_match):
                gaps.append({"case_id": cid, "kind": "SOURCE_" + a["result"]["source_relation"],
                    "reason": "Current material does not establish this mode's concrete mechanism"})
            if a["result"]["review_required"]:
                gaps.append({"case_id": cid, "kind": "FACT_CONFLICT", "reason": "; ".join(a["result"]["review_reasons"])})
            if any(r["relation"] in {"UNKNOWN", "PARTIAL"} for r in a["result"]["rows"]):
                gaps.append({"case_id": cid, "kind": "TRIGGER_UNKNOWNS", "reason": "Classification completed with explicit unknown/partial predicates"})
        for snapshot in ([] if definition_init else _linked_snapshots(store, run_id, cid).values()):
            if snapshot["status"] != "COMPLETE":
                gaps.append({"case_id": cid, "kind": "CAPTURE_" + snapshot["status"], "reason": snapshot["url"]})
            if not any(i["snapshot_id"] == snapshot["snapshot_id"] for i in _issues(store, run_id, cid)):
                gaps.append({"case_id": cid, "kind": "SUMMARY_MISSING", "reason": snapshot["url"]})
        for ref in ([] if definition_init else store.records(run_id, "references")):
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
    if cfg.get("knowledge_profile") and cfg["phase"] == "INIT":
        from .xlsx_workflow import _policy
        if state.get("plan_policy_hash") != _policy():
            state = {}
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
            "capture_status": "NOT_REQUESTED" if definition_init else (snapshot or {}).get("status", "NOT_FETCHED"),
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
    projection = {"run_id": run_id, "phase": cfg["phase"], "classification_framework": CLASSIFICATION_FRAMEWORK,
        "coverage_kind": cfg.get("basis", "HISTORICAL_EVIDENCE"),
        "taxonomy": _taxonomy(store, run_id), "subjects": subjects,
        "classification_contract": cfg.get("classification_contract", "DENSE_V1"),
        "input_condition_scheme": cfg.get("input_condition_scheme", "REVISED42"),
        "assessments": assessments, "wiki_checks": checks, "resources": resources,
        "gaps": gaps, "baseline": baseline}
    if _v4(store, run_id):
        from .trigger_design import current_designs
        designs = current_designs(store, run_id, assessments)
        designed = {d["case_id"] for d in designs}
        for subject in (subjects if cfg.get("classification_contract") != "SPARSE_SCENARIOS_V5" or cfg.get("design_tasks_enabled") else []):
            if subject["case_id"] not in designed:
                gaps.append({"case_id": subject["case_id"], "kind": "DESIGN_PENDING",
                    "reason": "Current scoped classification has not yet produced its separate design cards; no execution is claimed"})
        for a in assessments:
            if any(r["applicability"] in {"PARTIAL", "UNKNOWN"} for r in a["result"].get("v4_rows", [])):
                gaps.append({"case_id": a["case_id"], "kind": "V4_UNKNOWNS", "reason": "V4 semantic classification keeps explicit unknown prerequisites"})
        projection.update(v4_taxonomy=_v4(store, run_id),
            mapping=store.get(run_id, "trigger_mappings", cfg["mapping_id"]),
            execution_capabilities=cfg["execution_capabilities"], designs=designs,
            original_taxonomy=store.get(run_id, "trigger_taxonomies", _taxonomy(store, run_id)["original_taxonomy_id"]))
    if cfg.get("knowledge_profile"):
        from .cann_baseline import current_definitions, current_execution, mode_records, FIELDS, stage_gaps, current_review
        projection.update(knowledge_profile=cfg["knowledge_profile"], mapping_document_status="NOT_PROVIDED",
            mode_definitions=current_definitions(store, run_id), baseline_execution=current_execution(store, run_id),
            api42_registry=store.get(run_id, "api42_registry_receipts", cfg.get("api42_registry_id", "")))
        projection["mode_records"] = mode_records(projection) if cfg["phase"] == "INIT" else (baseline or {}).get("mode_records", [])
        if cfg["phase"] == "INIT":
            gaps.extend(stage_gaps(projection))
            if include_baseline_review:
                projection["baseline_review"] = current_review(store, run_id, projection)
                if not projection["baseline_review"]:
                    gaps.append({"case_id": "", "kind": "BASELINE_CROSS_REVIEW_PENDING", "reason": "Horizontal review across all original modes is required"})
            for mode in projection["mode_records"]:
                for field in FIELDS:
                    if mode[field]["status"] == "UNKNOWN":
                        gaps.append({"case_id": mode["source_case_id"], "kind": "MODE_MECHANISM_UNCLEAR" if field == "failure_mechanism" else "MODE_DEFINITION_INFORMATION_GAP",
                            "reason": field + ": " + mode[field]["text"]})
            from .baseline_recovery import recovery_plan
            projection["recovery"] = recovery_plan(store, run_id)
    return projection


@run_scoped
def status(store, run_id):
    data = _projection(store, run_id)
    values = data["assessments"]
    return {"run_id": run_id, "phase": data["phase"], "subject_count": len(data["subjects"]),
        "assessment_count": len(values), "assessed_subject_count": len({a["subject_id"] for a in values}),
        "trigger_count": len(data["taxonomy"]["items"]), "gap_count": len(data["gaps"]),
        "gaps": data["gaps"], "review_count": sum(a["result"]["review_required"] for a in values),
        "coverage_kind": data["coverage_kind"], "execution_verified": False}


@run_scoped
def _index_identity(store, run_id):
    from .xlsx_workflow import _policy
    dependencies = {}
    if _settings(store, run_id).get("knowledge_profile") and _settings(store, run_id)["phase"] == "INIT":
        from .cann_baseline import current_execution, current_review
        dependencies["execution"] = sorted(digest(r["result"]) for r in current_execution(store, run_id))
        review = current_review(store, run_id)
        dependencies["horizontal_review"] = digest(review["result"]) if review else None
    return digest({"catalog": _catalog(store, run_id), "taxonomy": _taxonomy(store, run_id),
        "policy": _policy(), "subjects": store.records(run_id, "trigger_subjects"),
        "baseline_dependencies": dependencies,
        "bases": [_basis(store, run_id, s) for s in store.records(run_id, "trigger_subjects")],
        "assessments": [a["assessment_id"] for a in current_assessments(store, run_id)]})


@run_scoped
def finalize(store, run_id, *, allow_pending=False):
    from .evidence_plan import collection_source_policy
    if _settings(store, run_id)["phase"] != "INIT":
        raise AuditError("Only an initialization run can maintain a baseline")
    data = _projection(store, run_id)
    if data.get("knowledge_profile"):
        from .cann_baseline import stage_gaps
        if {s["mode_id"] for s in data["subjects"]} != {m["item_id"] for m in _catalog(store, run_id)}:
            raise AuditError("Original catalog and Baseline subjects differ; maintain the mode collection first")
        if stage_gaps(data) or not data.get("baseline_review"):
            raise AuditError("Complete A1-A4 and the horizontal review before freezing Baseline v1")
        recommendation = data["baseline_review"]["result"]["recommendation"]
        if recommendation == "REWORK_REQUIRED":
            raise AuditError("Horizontal review requires rework; no baseline can be frozen")
        if recommendation == "READY_WITH_GAPS" and not allow_pending:
            raise AuditError("Horizontal review retains gaps; explicitly finalize a provisional baseline or resolve them")
    missing = {s["subject_id"] for s in data["subjects"]} - {a["subject_id"] for a in data["assessments"]}
    if missing or any(g["kind"] in {"ISSUE_UNASSESSED", "TASK_PENDING", "MODE_DEFINITION_PENDING"} for g in data["gaps"]):
        raise AuditError("Every original mode and current source issue needs an assessment; pending tasks cannot be finalized")
    informational = {"TRIGGER_UNKNOWNS", "V4_UNKNOWNS", "CAPTURE_PARTIAL", "CAPTURE_CONTENT_CAPTURED", "BASELINE_STALE",
                     "WIKI_NOT_SUPPORTED", "SOURCE_NOT_AVAILABLE_USER_POLICY", "CLASSIFICATION_INFORMATION_GAP", "MODE_DEFINITION_INFORMATION_GAP", "MODE_MECHANISM_UNCLEAR"}
    blocking = [g for g in data["gaps"] if g["kind"] not in informational]
    if blocking and not allow_pending:
        raise AuditError("Initialization has explicit gaps; finish them or finalize a provisional baseline with --allow-pending")
    details, declared_details = [], []
    definition_init = _settings(store, run_id).get("basis") == "SOURCE_DEFINITIONS"
    for a in data["assessments"]:
        if definition_init:
            for detail in a["result"]["details"]:
                if detail["evidence_basis"] == "SOURCE_DEFINITION":
                    labels = [r for r in a["result"]["rows"] if r["trigger_id"] in detail["trigger_ids"]]
                    declared_details.append({**detail, "trigger_assessments": labels,
                        "detail_id": a["assessment_id"] + ":" + detail["detail_id"],
                        "assessment_id": a["assessment_id"], "source_case_id": a["case_id"],
                        "coverage_kind": "SOURCE_DEFINITIONS", "execution_verified": False})
            continue
        if a["result"]["source_relation"] != "MATCH" or a["result"]["review_required"]:
            continue
        for detail in a["result"]["details"]:
            if detail["evidence_basis"] in {"SOURCE_REPORTED", "CODE_INFERENCE"}:
                labels = [r for r in a["result"]["rows"] if r["trigger_id"] in detail["trigger_ids"]]
                details.append({**detail, "trigger_ids": [r["trigger_id"] for r in labels if r["relation"] == "MATCH"],
                    "trigger_assessments": labels, "detail_id": a["assessment_id"] + ":" + detail["detail_id"],
                    "assessment_id": a["assessment_id"], "snapshot_id": a["snapshot_id"], "issue_index": a["issue_index"]})
    identity = _index_identity(store, run_id)
    condition_index = []
    subjects = {s["subject_id"]: s for s in data["subjects"]}
    for assessment in data["assessments"]:
        subject = subjects[assessment["subject_id"]]
        source = subject["source_case"]
        result = assessment["result"]
        condition_index.append({"assessment_id": assessment["assessment_id"],
            "mode_id": subject.get("mode_id"), "case_id": assessment["case_id"],
            "snapshot_id": assessment.get("snapshot_id"), "issue_index": assessment.get("issue_index"),
            "issue_label": assessment.get("issue_label"),
            "source_case": {key: source[key] for key in ("external_id", "description", "root_cause_raw",
                "source_file", "source_sha256", "sheet", "row", "cell_locations") if key in source},
            "condition_facts": result.get("condition_facts", []), "rows": result["rows"], "v4_rows": result.get("v4_rows", []),
            "external_branches": result["external_branches"],
            "condition_processing_status": result.get("condition_processing_status"),
            "source_relation": result["source_relation"], "coverage_kind": result["coverage_kind"],
            "execution_verified": False,
            **{k: result[k] for k in ("classification_contract", "classification_summary", "scenarios",
                "scenario_relation", "label_links", "classification_scope", "execution_method_links") if k in result}})
    baseline = {"baseline_id": "trigger-baseline-" + identity[:24], "run_id": run_id,
        "status": "READY_WITH_GAPS" if blocking or any(g["kind"] in {"CLASSIFICATION_INFORMATION_GAP", "MODE_MECHANISM_UNCLEAR"} for g in data["gaps"]) else "READY", "index_hash": identity,
        "taxonomy_id": _settings(store, run_id)["taxonomy_id"], "mode_ids": [i["item_id"] for i in _catalog(store, run_id)],
        "catalog_scope": store.get(run_id, "catalog_selections", "frozen"),
        "collection_source_policy": collection_source_policy(store, run_id),
        "assessment_ids": [a["assessment_id"] for a in data["assessments"]], "coverage_details": details,
        "declared_details": declared_details,
        "classification_framework": CLASSIFICATION_FRAMEWORK, "condition_index": condition_index,
        "classification_contract": _settings(store, run_id).get("classification_contract", "DENSE_V1"),
        "gaps": data["gaps"], "coverage_kind": data["coverage_kind"], "execution_verified": False}
    if data.get("knowledge_profile"):
        baseline.update(knowledge_profile=data["knowledge_profile"], mode_records=data["mode_records"],
            input_condition_scheme=data["input_condition_scheme"], mapping_document_status="NOT_PROVIDED",
            api42_registry=data["api42_registry"], baseline_review=data["baseline_review"],
            baseline_version="CANN-BASELINE-v1-" + identity[:16])
        if recommendation == "READY_WITH_GAPS":
            baseline["status"] = "READY_WITH_GAPS"
    if data.get("v4_taxonomy"):
        baseline.update(v4_taxonomy_id=data["v4_taxonomy"]["taxonomy_id"],
            v4_definition_version=data["v4_taxonomy"]["definition_version"],
            mapping_id=data["mapping"]["mapping_id"], revised_definition_version=data["taxonomy"]["definition_version"])
    if data.get("knowledge_profile"):
        baseline.pop("revised_definition_version", None)
        baseline["api_definition_version"] = data["taxonomy"]["definition_version"]
    store.put(run_id, "trigger_baselines", baseline["baseline_id"], baseline)
    store.put(run_id, "trigger_baseline_heads", "current", {"baseline_id": baseline["baseline_id"]}, mutable=True)
    return baseline


@run_scoped
def _baseline(store, run_id, baseline_id=None, *, allow_pending=False):
    head = store.get(run_id, "trigger_baseline_heads", "current") or {}
    baseline = store.get(run_id, "trigger_baselines", baseline_id or head.get("baseline_id", ""))
    if not baseline:
        raise AuditError("Initialize and finalize the original library before classifying new cases")
    if baseline["index_hash"] != _index_identity(store, run_id):
        raise AuditError("Initialized baseline is stale; maintain/finalize it again without deleting history")
    if baseline["status"] != "READY" and not allow_pending:
        raise AuditError("Baseline has gaps; complete initialization or explicitly allow a provisional baseline")
    if baseline.get("classification_framework") != CLASSIFICATION_FRAMEWORK or not baseline.get("condition_index"):
        raise AuditError("Maintain the conditions-first Init index before incremental classification")
    return baseline


def start_incremental(store, source, baseline_run, work_root, *, executor="opencode", baseline_id=None,
                      allow_pending_baseline=False, input_budget_chars=None):
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
    from .run_budget import pin
    from .input_budget import get_budget_chars
    pin(store, run_id, get_budget_chars() if input_budget_chars is None else input_budget_chars, reason="WORKFLOW_START")
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
        "catalog_hash": digest(catalog), "rule_version": RULE_VERSION, "basis": "HISTORICAL_EVIDENCE",
        "baseline_basis": baseline.get("coverage_kind", "HISTORICAL_EVIDENCE"),
        "classification_framework": CLASSIFICATION_FRAMEWORK})
    baseline_settings = _settings(store, baseline_run)
    if baseline_settings.get("classification_contract"):
        settings = _settings(store, run_id)
        store.put(run_id, "trigger_config", "config", {**settings,
            "classification_contract": baseline_settings["classification_contract"],
            "design_tasks_enabled": baseline_settings.get("design_tasks_enabled", False),
            **{k: baseline_settings[k] for k in ("knowledge_profile", "input_condition_scheme") if k in baseline_settings}}, mutable=True)
        if baseline_settings.get("api42_registry_id"):
            registry_id = baseline_settings["api42_registry_id"]
            store.put(run_id, "api42_registry_receipts", registry_id, store.get(baseline_run, "api42_registry_receipts", registry_id))
            store.put(run_id, "trigger_config", "config", {**_settings(store, run_id), "api42_registry_id": registry_id}, mutable=True)
    if baseline_settings.get("v4_taxonomy_id"):
        for kind, key in (("trigger_v4_taxonomies", baseline_settings["v4_taxonomy_id"]),
                          ("trigger_mappings", baseline_settings["mapping_id"]),
                          ("trigger_taxonomies", frozen["original_taxonomy_id"])):
            store.put(run_id, kind, key, store.get(baseline_run, kind, key))
        settings = _settings(store, run_id)
        store.put(run_id, "trigger_config", "config", {**settings,
            **{k: baseline_settings[k] for k in ("classification_profile", "v4_taxonomy_id", "mapping_id", "execution_capabilities")}}, mutable=True)
    for case in store.records(run_id, "cases"):
        subject = {"subject_id": "case-subject-" + digest(case["case_id"])[:24],
            "case_id": case["case_id"], "subject_kind": "FAULT_CASE"}
        store.put(run_id, "trigger_subjects", subject["subject_id"], subject)
    return {**cfg, "purpose": "TRIGGER_INCREMENTAL", "baseline_id": baseline["baseline_id"]}


@run_scoped
def export(store, run_id, *, previous_classification=None, xlsx=False):
    from .xlsx_workflow import config
    from .trigger_html import render, index_workbook
    from .trigger_combinations import analyze
    from .exporters import export_workbook_xlsx
    cfg = config(store, run_id)
    data = _projection(store, run_id)
    if previous_classification is not None:
        data["previous_classification"] = previous_classification
    output = Path(cfg["directory"]) / "output"
    output.mkdir(parents=True, exist_ok=True)
    if data.get("knowledge_profile") and data["phase"] == "INIT":
        from .baseline_reports import export as export_baseline
        head = store.get(run_id, "trigger_baseline_heads", "current") or {}
        frozen = store.get(run_id, "trigger_baselines", head.get("baseline_id", ""))
        data["baseline_freeze"] = ({"baseline_id": frozen["baseline_id"], "version": frozen["baseline_version"],
            "status": frozen["status"] if frozen["index_hash"] == _index_identity(store, run_id) else "STALE"} if frozen else {"status":"NOT_FROZEN"})
        result = export_baseline(data, output)
        store.event(run_id, "trigger_export", result)
        return result
    data["combination_analysis"] = analyze(data)
    (output / "report.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "report.html").write_text(render(data), encoding="utf-8")
    result = {"report_html": str(output / "report.html"), "report_json": str(output / "report.json"),
        "primary_report": "HTML", "classification_contract": data["classification_contract"]}
    if xlsx:
        name = "故障分类索引.xlsx"
        with tempfile.TemporaryDirectory(prefix="trigger-xlsx-", dir=Path(cfg["directory"])) as scratch:
            source = Path(scratch) / "workbook.json"
            source.write_text(json.dumps(index_workbook(data), ensure_ascii=False), encoding="utf-8")
            saved = export_workbook_xlsx(source, Path(scratch) / name)
            Path(saved["xlsx"]).replace(output / name)
        result.update(saved, xlsx=str(output / name))
    result.update(status="COMPLETE_WITH_PENDING" if data["gaps"] else "COMPLETE",
                  gap_count=len(data["gaps"]), coverage_kind=data["coverage_kind"], execution_verified=False)
    store.event(run_id, "trigger_export", result)
    return result
