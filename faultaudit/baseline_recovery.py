"""Explicit Agent review of historical definitions; never a policy/ACCEPT rewrite."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Literal
from pydantic import Field, ValidationError

from .contracts import Contract, CatalogDraftProducer, SelfCheck
from .knowledge_common import validate_common, checked_claim, enabled
from .run_budget import scoped as run_scoped
from .source_manifest import SourceReference, build, resolve, references_for_cells, canonical_fact
from .store import AuditError, digest

VERSION = "baseline-recovery-0.1.19"


@run_scoped
def rejected_contexts(store, run_id, subject):
    """Read old rejected originals/variants as review inputs, never as accepted facts."""
    from .xlsx_workflow import _policy, config
    requests = {r["task_id"]: r for r in store.records(run_id, "workflow_requests")
                if r["kind"] == "baseline_define" and r.get("policy_hash") != _policy()
                and r["payload"].get("subject", {}).get("subject_id") == subject["subject_id"]}
    root = Path(config(store, run_id)["directory"]).resolve() / "tasks"
    result = []
    for attempt in store.records(run_id, "workflow_attempts"):
        if attempt.get("status") != "REJECTED" or attempt["task_id"] not in requests:
            continue
        entry = {"task_id": attempt["task_id"], "original_response_hash": attempt.get("response_hash"),
                 "error": attempt.get("error", ""), "files": [], "status": "MISSING"}
        original_path = Path(attempt.get("response", ""))
        task_root = root / attempt["task_id"]
        if original_path.is_absolute() and original_path.resolve().is_relative_to(task_root):
            for path in (original_path.with_name("response.rejected.json"), original_path):
                if not path.is_file():
                    continue
                try:
                    value = json.loads(path.read_text(encoding="utf-8-sig"))
                    if not isinstance(value, dict):
                        raise ValueError("Historical response is not an object")
                    actual = digest(value)
                    entry["files"].append({"path": str(path), "response_hash": actual, "response": value,
                        "role": "ORIGINAL_REJECTED" if actual == attempt.get("response_hash") else "UNSUBMITTED_VARIANT"})
                    entry["status"] = "AVAILABLE_FOR_AGENT_REVIEW"
                except (OSError, UnicodeError, ValueError) as exc:
                    entry["files"].append({"path": str(path), "status": "UNREADABLE", "error": str(exc)})
        result.append(entry)
    return result


def technical_projection(result):
    from .cann_baseline import FIELDS
    return {"mode_id": result["mode_id"], "mode_name": result["mode_name"],
            **{field: {"text": result[field]["text"], "status": result[field]["status"],
                       "condition_fact_ids": sorted(result[field].get("condition_fact_ids", [])),
                       "derivation_reason": result[field].get("derivation_reason", "")} for field in FIELDS},
            "condition_facts": sorted([canonical_fact(f) for f in result.get("condition_facts", [])],
                                      key=lambda f: f["fact_id"])}


def technical_hash(result):
    return digest(technical_projection(result))


@run_scoped
def select_current(store, run_id):
    from .cann_baseline import definition_basis
    from .xlsx_workflow import _policy
    policy = _policy()
    results = []
    records = store.records(run_id, "mode_definitions")
    for subject in store.records(run_id, "trigger_subjects"):
        basis = definition_basis(store, run_id, subject)
        valid = [r for r in records if r["subject_id"] == subject["subject_id"]
                 and r["policy_hash"] == policy and r["basis_hash"] == basis
                 and r.get("technical_hash", technical_hash(r["result"])) == technical_hash(r["result"])]
        head = store.get(run_id, "mode_definition_heads", subject["subject_id"]) or {}
        selected = next((r for r in valid if r["definition_id"] == head.get("definition_id")), None)
        if selected is None and valid and len({technical_hash(r["result"]) for r in valid}) == 1:
            selected = min(valid, key=lambda r: r["definition_id"])
        if selected:
            results.append(selected)
    return results


def save_definition(store, run_id, record, manifest):
    record.update(technical_hash=technical_hash(record["result"]), source_manifest_hash=manifest["manifest_hash"],
                  evidence_hash=digest({"manifest": manifest["manifest_hash"],
                      "references": record["result"].get("evidence_refs", []),
                      "validation_status": record["result"].get("validation_status", {}),
                      "gaps": record["result"].get("evidence_gaps", [])}))
    store.put(run_id, "source_manifests", manifest["manifest_hash"], manifest)
    store.put(run_id, "mode_definitions", record["definition_id"], record)
    head = {"definition_id": record["definition_id"], "basis_hash": record["basis_hash"],
            "policy_hash": record["policy_hash"], "technical_hash": record["technical_hash"]}
    old = store.get(run_id, "mode_definition_heads", record["subject_id"])
    if old != head:
        store.put(run_id, "mode_definition_heads", record["subject_id"], head, mutable=bool(old))
        store.event(run_id, "mode_definition_selected", {"subject_id": record["subject_id"],
                    "previous": old, "current": head, "human_accept_created": False})


def precheck(store, run_id, subject, record):
    """Structural/anchor validation only; technical semantics remains Agent work."""
    from .cann_baseline import DefinitionResponse, FIELDS
    from .xlsx_workflow import check_archived_request, config
    errors = []
    try:
        request = store.get(run_id, "workflow_requests", record["definition_id"])
        if not request:
            raise AuditError("Historical request is missing")
        check_archived_request(request)
        if request["kind"] != "baseline_define":
            raise AuditError("Historical review contract requires a fresh compatibility assessment")
        case = store.get(run_id, "cases", subject["case_id"])
        mode = store.get(run_id, "catalog", subject["mode_id"])
        old_subject = request["payload"]["subject"]
        if (record["case_id"] != subject["case_id"] or old_subject["subject_id"] != subject["subject_id"]
                or old_subject["mode_id"] != subject["mode_id"] or old_subject["source_case"] != case
                or request["payload"]["original_mode"] != mode
                or record["basis_hash"] != request["payload"]["basis_hash"]):
            raise AuditError("Historical definition source/catalog differs from the frozen current input")
        response = record["raw_response"]
        accepted = store.get(run_id, "workflow_results", record["definition_id"])
        if not accepted or accepted.get("response_hash") != digest(response):
            raise AuditError("Historical accepted response integrity is not established")
        value, facts = validate_common(request["payload"], response, DefinitionResponse, request["request_hash"])
        if (value.executor != config(store, run_id)["executor"] or value.definition.mode_id != subject["mode_id"]
                or value.definition.mode_name != mode["description"]):
            raise AuditError("Historical mode identity or executor differs")
        for field in FIELDS:
            checked_claim(getattr(value.definition, field), facts)
        expected = {**value.definition.model_dump(), "condition_facts": [canonical_fact(f.model_dump()) for f in facts.values()]}
        if technical_hash(expected) != technical_hash(record["result"]):
            raise AuditError("Stored definition differs from its historical raw response")
        manifest = build(case)
        for fact in record["result"].get("condition_facts", []):
            references_for_cells(manifest, fact.get("source_cells", []))
    except (AuditError, ValidationError, KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    return {"structural_status": "PASS" if not errors else "FAIL", "errors": errors,
            "semantic_status": "NOT_REVIEWED", "human_accept_created": False}


def candidates(store, run_id, subject):
    return [{"definition_id": r["definition_id"], "policy_hash": r["policy_hash"],
             "raw_response_hash": digest(r["raw_response"]), "technical_hash": technical_hash(r["result"]),
             "result": r["result"], "raw_response": r["raw_response"], "precheck": precheck(store, run_id, subject, r)}
            for r in sorted(store.records(run_id, "mode_definitions"), key=lambda r: r["definition_id"])
            if r["subject_id"] == subject["subject_id"]]


def candidate_identity(values):
    return digest([{k: c[k] for k in ("definition_id", "policy_hash", "raw_response_hash", "technical_hash", "precheck")}
                   for c in values])


def current_review(store, run_id, subject, values=None):
    from .cann_baseline import definition_basis
    from .xlsx_workflow import _policy
    values = candidates(store, run_id, subject) if values is None else values
    basis, identity, policy = definition_basis(store, run_id, subject), candidate_identity(values), _policy()
    return next((r for r in store.records(run_id, "baseline_compatibility_reviews")
                 if r["subject_id"] == subject["subject_id"] and r["basis_hash"] == basis
                 and r["candidate_hash"] == identity and r["policy_hash"] == policy), None)


def route(store, run_id, subject, *, current_ids=None, values=None):
    current_ids = {r["subject_id"] for r in select_current(store, run_id)} if current_ids is None else current_ids
    if subject["subject_id"] in current_ids:
        return "CURRENT"
    values = candidates(store, run_id, subject) if values is None else values
    review = current_review(store, run_id, subject, values)
    if review:
        return "CONFLICT" if review["result"]["decision"] == "CONFLICT" else "DEFINE"
    return "COMPATIBILITY" if any(c["precheck"]["structural_status"] == "PASS" for c in values) else "DEFINE"


def regeneration_context(store, run_id, subject):
    values = candidates(store, run_id, subject)
    review = current_review(store, run_id, subject, values)
    if review and review["result"]["decision"] == "REGENERATE":
        return {"review_id": review["review_id"], "review": review["result"], "historical_definitions": values}
    return None


class FieldCheck(Contract):
    field: str
    verdict: Literal["SUPPORTED", "UNKNOWN", "CONFLICT"]
    reason: str = Field(min_length=1)
    source_refs: list[SourceReference] = Field(default_factory=list)


class VersionCheck(Contract):
    definition_id: str
    verdict: Literal["SELECTED", "EQUIVALENT", "DIFFERENT", "UNCERTAIN", "INVALID"]
    reason: str = Field(min_length=1)


class CompatibilityResponse(Contract):
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_id: str
    executor: Literal["codex", "opencode"]
    producer: CatalogDraftProducer
    self_check: SelfCheck
    decision: Literal["REUSE", "REGENERATE", "CONFLICT"]
    selected_definition_id: str | None = None
    field_checks: list[FieldCheck]
    version_checks: list[VersionCheck]
    reason: str = Field(min_length=1)


INSTRUCTIONS = """Review historical A1 definitions against THIS frozen original source.
This is an explicit semantic compatibility review, not a new classification or human ACCEPT.
All available versions are supplied; a precheck PASS proves structure/quotes only. Compare
each of the seven technical fields, supporting facts, counterevidence, scope and unknowns.
Choose REUSE only when one selected definition is supported. Cite source_manifest source_id
and verbatim quote for every known field; explain INFERRED reasoning. Unknown fields stay
UNKNOWN. Review every version, separating technical differences from evidence/metadata.
A second historical record alone never proves a technical change. Do not change a selected
definition's technical text or invent facts. Use REGENERATE if content needs changes, or
CONFLICT for unresolved contrary evidence. No new Wiki search or hardware execution.
Return CompatibilityResponse at the OUTER hash, actual producer, and one bounded self-check.
Do not submit SQL, migrate policies, remove history, or generate a human ACCEPT.
"""


@run_scoped
def compatibility_payloads(store, run_id):
    from .cann_baseline import definition_basis
    if not enabled(store, run_id):
        return
    done = {r["subject_id"] for r in select_current(store, run_id)}
    for subject in store.records(run_id, "trigger_subjects"):
        if route(store, run_id, subject, current_ids=done) != "COMPATIBILITY":
            continue
        values = candidates(store, run_id, subject)
        case = store.get(run_id, "cases", subject["case_id"])
        yield {"subject": {**subject, "source_case": case},
               "original_mode": store.get(run_id, "catalog", subject["mode_id"]),
               "source_manifest": build(case), "historical_definitions": values,
               "candidate_hash": candidate_identity(values), "basis_hash": definition_basis(store, run_id, subject),
               "case_ids": [subject["case_id"]], "response_schema": CompatibilityResponse.model_json_schema(),
               "input_scope": {"all_historical_definitions_for_subject": True,
                   "original_source_complete": True, "semantic_review_required": True,
                   "historical_requests": "Integrity checked by program; archived full requests retained in state"}}


@run_scoped
def accept_compatibility(store, run_id, request, response):
    from .cann_baseline import definition_basis, FIELDS
    from .xlsx_workflow import check_current_request, _policy, config
    check_current_request(store, run_id, request)
    if request["kind"] != "baseline_compatibility":
        raise AuditError("Compatibility review must use its assigned workflow kind")
    payload = request["payload"]
    subject = store.get(run_id, "trigger_subjects", payload["subject"]["subject_id"])
    if not enabled(store, run_id) or not subject:
        raise AuditError("Compatibility review requires the original Baseline subject")
    values = candidates(store, run_id, subject)
    if (payload["basis_hash"] != definition_basis(store, run_id, subject)
            or payload["candidate_hash"] != candidate_identity(values)
            or payload["historical_definitions"] != values
            or payload["source_manifest"] != build(store.get(run_id, "cases", subject["case_id"]))):
        raise AuditError("Historical definitions or their frozen source changed during review")
    try:
        value = CompatibilityResponse.model_validate(response)
    except ValidationError as exc:
        raise AuditError("Invalid compatibility review: " + str(exc)) from exc
    if (value.request_hash != request["request_hash"] or value.case_id != subject["case_id"]
            or value.executor != config(store, run_id)["executor"] or not value.self_check.passed):
        raise AuditError("Compatibility review identity/executor/self-check mismatch")
    if not all(getattr(value.self_check, key) for key in ("numeric_meaning_checked", "citations_checked",
            "counterevidence_checked", "issue_scope_checked", "event_vs_technical_checked")):
        raise AuditError("Compatibility review must complete every bounded self-check")
    checks = {c.field: c for c in value.field_checks}
    versions = {c.definition_id: c for c in value.version_checks}
    if len(checks) != len(value.field_checks) or set(checks) != set(FIELDS):
        raise AuditError("Review all seven definition fields exactly once")
    if len(versions) != len(value.version_checks) or set(versions) != {c["definition_id"] for c in values}:
        raise AuditError("Review every historical version exactly once; do not hide conflicting versions")
    for check in checks.values():
        resolve(payload["source_manifest"], check.source_refs)
    if any(v.verdict == "INVALID" and c["precheck"]["structural_status"] == "PASS"
           for c in values for v in [versions[c["definition_id"]]]):
        raise AuditError("Do not label a structurally valid historical version INVALID to avoid reviewing its content")
    selected = next((c for c in values if c["definition_id"] == value.selected_definition_id), None)
    if value.decision == "REUSE":
        if not selected or selected["precheck"]["structural_status"] != "PASS":
            raise AuditError("Reuse requires a valid selected historical definition")
        if versions[selected["definition_id"]].verdict != "SELECTED" or any(
                c.verdict in {"UNCERTAIN", "SELECTED"} for key, c in versions.items() if key != selected["definition_id"]):
            raise AuditError("Selected and alternative versions need an explicit resolved comparison")
        result = copy.deepcopy(selected["result"])
        facts = {f["fact_id"]: f for f in result["condition_facts"]}
        for field, check in checks.items():
            claim = result[field]
            if claim["status"] == "UNKNOWN":
                if check.verdict != "UNKNOWN":
                    raise AuditError("Do not promote an unknown historical claim through reuse")
            else:
                if check.verdict != "SUPPORTED" or not check.source_refs:
                    raise AuditError("Known historical fields need explicit semantic support and source references")
                cited = [cell for fid in claim["condition_fact_ids"] for cell in facts[fid].get("source_cells", [])]
                if any(not any(cell["field"] == prior["field"] and cell["cell"] == prior["cell"]
                               and cell["quote"] in prior["quote"] for prior in cited)
                       for cell in resolve(payload["source_manifest"], check.source_refs)):
                    raise AuditError("Review field citations must belong to its original supporting facts")
                if claim["status"] == "INFERRED" and not claim.get("derivation_reason"):
                    claim["derivation_reason"] = check.reason
        result["validation_status"] = {"MODE_DEFINITION": "REVIEWED_BY_AGENT", "HISTORICAL_EVIDENCE": "NOT_VERIFIED",
                                       "SOURCE_VERIFIED": False, "HARDWARE_VALIDATED": False}
        record = {"definition_id": request["task_id"], "subject_id": subject["subject_id"], "case_id": value.case_id,
                  "basis_hash": payload["basis_hash"], "policy_hash": _policy(), "raw_response": response,
                  "result": result, "historical_definition_id": selected["definition_id"],
                  "historical_policy_hash": selected["policy_hash"], "compatibility_review_id": request["task_id"]}
        save_definition(store, run_id, record, payload["source_manifest"])
    elif value.selected_definition_id is not None:
        raise AuditError("Non-reuse review must not select a current definition")
    review = {"review_id": request["task_id"], "subject_id": subject["subject_id"],
              "basis_hash": payload["basis_hash"], "candidate_hash": payload["candidate_hash"],
              "policy_hash": _policy(), "result": value.model_dump(), "human_accept_created": False}
    store.put(run_id, "baseline_compatibility_reviews", request["task_id"], review)
    return review


def definition_dependency(store, run_id, subject):
    subject = store.get(run_id, "trigger_subjects", subject["subject_id"])
    current = next((r for r in select_current(store, run_id) if r["subject_id"] == subject["subject_id"]), None)
    return {"subject": subject, "source": store.get(run_id, "cases", subject["case_id"]),
            "catalog_mode": store.get(run_id, "catalog", subject["mode_id"]),
            "technical_definition": technical_hash(current["result"]) if current else None}


def axis_basis(store, run_id, subject, axis):
    from .trigger_workflow import _taxonomy, _v4
    from .trigger_v4 import model_v4
    frame = _taxonomy(store, run_id) if axis == "API42" else model_v4(_v4(store, run_id))
    return digest({"definition": definition_dependency(store, run_id, subject), "axis": axis,
                   "frame": frame, "version": VERSION})


@run_scoped
def recovery_plan(store, run_id):
    from .cann_baseline import current_execution
    from .trigger_workflow import current_assessments, _settings
    from .xlsx_workflow import _policy
    from .run_budget import status as budget_status
    if not enabled(store, run_id) or _settings(store, run_id)["phase"] != "INIT":
        raise AuditError("Recovery planning requires an original-mode Baseline Init")
    definitions = {r["subject_id"]: r for r in select_current(store, run_id)}
    assessments = current_assessments(store, run_id)
    executions = current_execution(store, run_id)
    matrix = []
    for subject in store.records(run_id, "trigger_subjects"):
        historical = candidates(store, run_id, subject) if subject["subject_id"] not in definitions else []
        path = route(store, run_id, subject, current_ids=set(definitions), values=historical)
        review = current_review(store, run_id, subject, historical) if historical else None
        matrix.append({"mode_id": subject["mode_id"], "subject_id": subject["subject_id"], "case_id": subject["case_id"],
            "definition_path": path, "current_definition_id": definitions.get(subject["subject_id"], {}).get("definition_id"),
            "compatibility_review": {"review_id": review["review_id"], "decision": review["result"]["decision"],
                "reason": review["result"]["reason"]} if review else None,
            "historical_candidates": [{k: c[k] for k in ("definition_id", "policy_hash", "technical_hash", "precheck")} for c in historical],
            "completed_axes": [axis for axis in ("V4", "API42") if any(
                a["subject_id"] == subject["subject_id"] and a.get("baseline_axis") == axis for a in assessments)],
            "execution_current": any(e["subject_id"] == subject["subject_id"] for e in executions)})
    requests = store.records(run_id, "workflow_requests")
    policy = _policy()
    return {"run_id": run_id, "version": VERSION, "policy_hash": policy, "budget": budget_status(store, run_id),
            "mode_count": len(matrix), "current_definition_count": len(definitions),
            "compatibility_pending_modes": sum(m["definition_path"] == "COMPATIBILITY" for m in matrix),
            "definition_required_modes": sum(m["definition_path"] == "DEFINE" for m in matrix),
            "conflict_modes": sum(m["definition_path"] == "CONFLICT" for m in matrix),
            "expected_downstream_units": len(matrix) * 3,
            "current_downstream_units": len({(a["subject_id"], a.get("baseline_axis")) for a in assessments})
                + len({e["subject_id"] for e in executions}),
            "request_count_all_policies": len(requests),
            "request_count_current_policy": sum(r.get("policy_hash") == policy for r in requests),
            "matrix": matrix, "state_writes": 0, "human_accept_created": False}
