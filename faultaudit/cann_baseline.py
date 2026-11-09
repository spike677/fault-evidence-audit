"""Normalize original CANN modes before sparse classification and freezing."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Literal
from pydantic import Field, ValidationError
from .contracts import Contract, CatalogDraftProducer, SelfCheck
from .knowledge_common import PROFILE, Claim, KnowledgeResponse, validate_common, checked_claim, enabled
from .store import AuditError, digest

FIELDS = ("fault_object", "failure_mechanism", "observable_symptoms", "input_trigger_conditions",
          "execution_trigger_conditions", "applicable_scope", "exclusion_boundaries")


def configure(store, run_id, *, expected_mode_count=None):
    """Select original API42 clauses without modifying any source definition."""
    from .trigger_workflow import _settings, _taxonomy, configure_v5
    from .trigger_v4 import LEGACY_VERSION
    settings = _settings(store, run_id)
    if settings["phase"] != "INIT":
        raise AuditError("Maintain the baseline before opening an incremental lifecycle")
    if not settings.get("v4_taxonomy_id"):
        raise AuditError("Baseline A2 requires the original V4 source; configure-v4 first")
    current = _taxonomy(store, run_id)
    mode_ids = [m["item_id"] for m in store.records(run_id, "catalog")]
    if len(mode_ids) != len(set(mode_ids)) or expected_mode_count is not None and len(mode_ids) != expected_mode_count:
        raise AuditError("Baseline mode IDs/count differ from the requested original library")
    original_id = current.get("original_taxonomy_id", current["taxonomy_id"])
    original = store.get(run_id, "trigger_taxonomies", original_id)
    from .trigger_taxonomy import load_taxonomy, EXPECTED_IDS
    source = Path(original["source_file"])
    actual = load_taxonomy(source)
    if actual["source_sha256"] != original["source_sha256"] or [(i["id"], i["name"], i["definition"]) for i in actual["items"]] != [(i["id"], i["name"], i["definition"]) for i in original["items"]]:
        raise AuditError("Original API42 file differs from the stored definitions; do not reuse by filename")
    ids = [i["id"] for i in actual["items"]]
    receipt = {"source_file": str(source.resolve()), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "actual_ids": ids, "items": [{k: i[k] for k in ("id", "name", "definition", "requires", "skip_if", "line_start", "line_end")} for i in actual["items"]],
        "duplicate_ids": sorted({k for k in ids if ids.count(k)>1}), "missing_ids": sorted(set(EXPECTED_IDS)-set(ids)),
        "unexpected_ids": sorted(set(ids)-set(EXPECTED_IDS)), "definition_version": LEGACY_VERSION}
    receipt_id = "original42-registry-" + digest(receipt)[:24]
    store.put(run_id, "api42_registry_receipts", receipt_id, receipt)
    if settings.get("knowledge_profile") == PROFILE and current.get("definition_version") == LEGACY_VERSION and settings.get("api42_registry_id") == receipt_id and settings.get("basis") == "SOURCE_DEFINITIONS":
        return {"run_id": run_id, "knowledge_profile": PROFILE, "api42_registry_id": receipt_id, "idempotent": True}
    configure_v5(store, run_id, with_designs=settings.get("design_tasks_enabled", False))
    settings = _settings(store, run_id)
    value = {**original, "definition_version": LEGACY_VERSION, "original_definition_version": LEGACY_VERSION,
        "original_taxonomy_id": original_id, "input_condition_scheme": "ORIGINAL42"}
    value["taxonomy_id"] = "original42-profile-" + digest(value)[:24]
    store.put(run_id, "trigger_taxonomies", value["taxonomy_id"], value)
    store.put(run_id, "trigger_config", "config", {**settings, "knowledge_profile": PROFILE,
        "input_condition_scheme": "ORIGINAL42", "taxonomy_id": value["taxonomy_id"],
        "classification_profile": "V4_AND_ORIGINAL42_BASELINE_v1",
        "api42_registry_id": receipt_id, "expected_mode_count": len(mode_ids), "basis": "SOURCE_DEFINITIONS"}, mutable=True)
    from .xlsx_workflow import config
    workflow = config(store, run_id)
    store.put(run_id, "xlsx_workflow", "config", {**workflow, "init_basis": "SOURCE_DEFINITIONS"}, mutable=True)
    store.event(run_id, "knowledge_lifecycle_configured", {"knowledge_profile": PROFILE,
        "previous_taxonomy_id": current["taxonomy_id"], "taxonomy_id": value["taxonomy_id"],
        "original_definitions_changed": False, "mapping_document_status": "NOT_PROVIDED"})
    return {"run_id": run_id, "knowledge_profile": PROFILE, "input_condition_scheme": "ORIGINAL42", "api42_registry_id": receipt_id}


class ModeDefinition(Contract):
    mode_id: str
    mode_name: str
    fault_object: Claim
    failure_mechanism: Claim
    observable_symptoms: Claim
    input_trigger_conditions: Claim
    execution_trigger_conditions: Claim
    applicable_scope: Claim
    exclusion_boundaries: Claim


class DefinitionResponse(KnowledgeResponse):
    definition: ModeDefinition


INSTRUCTIONS = """Normalize THIS existing CANN mode into DefinitionResponse. Preserve mode_id and
the original mode_name. This task defines the CANN failure_mechanism, NOT V4 classification.
V4 has 6 themes, 31 condition classes, 55 construction scenarios and 195 reference cases;
none is a failure-mechanism registry. API42 and E1-E5 are separate axes, assigned later.
For every field extract its technical meaning and scope, with exact source cells through
condition_facts. Known original claims may be STATED without customer-event confirmation.
Mark deductions INFERRED; missing facts UNKNOWN with an explanation, never fill plausible
parameters, boundaries or mechanisms. Preserve conflicting original descriptions visibly.
Do not assign V4/API labels or adopt changes here. MODE_DEFINITION is the basis, not source
verification or hardware validation. Do not search merely to make this definition complete.
Read the full source. Return the supplied raw schema at the OUTER request_hash; no ACCEPT.
"""


def definition_basis(store, run_id, subject):
    return digest({"profile": PROFILE, "subject": subject,
        "source": store.get(run_id, "cases", subject["case_id"])})


def current_definitions(store, run_id):
    from .xlsx_workflow import _policy
    subjects = {s["subject_id"]: s for s in store.records(run_id, "trigger_subjects")}
    return [r for r in store.records(run_id, "mode_definitions") if r["policy_hash"] == _policy()
        and r["subject_id"] in subjects and r["basis_hash"] == definition_basis(store, run_id, subjects[r["subject_id"]])]


def payloads(store, run_id):
    cfg = store.get(run_id, "trigger_config", "config") or {}
    if not enabled(store, run_id) or cfg["phase"] != "INIT":
        return
    done = {r["subject_id"] for r in current_definitions(store, run_id)}
    catalog = {r["item_id"]: r for r in store.records(run_id, "catalog")}
    for subject in store.records(run_id, "trigger_subjects"):
        if subject["subject_id"] in done:
            continue
        source = store.get(run_id, "cases", subject["case_id"])
        yield {"subject": {**subject, "source_case": source}, "original_mode": catalog[subject["mode_id"]],
            "case_ids": [subject["case_id"]], "basis_hash": definition_basis(store, run_id, subject),
            "input_scope": {"original_source_complete": True, "basis": "MODE_DEFINITION"},
            "response_schema": DefinitionResponse.model_json_schema()}


def accept(store, run_id, request, response):
    from .xlsx_workflow import _policy, config
    payload = request["payload"]
    subject = store.get(run_id, "trigger_subjects", payload["subject"]["subject_id"])
    if not enabled(store, run_id) or not subject or payload["basis_hash"] != definition_basis(store, run_id, subject):
        raise AuditError("Mode definition input changed; request a fresh task")
    value, facts = validate_common(payload, response, DefinitionResponse, request["request_hash"])
    mode = value.definition
    name = payload["original_mode"]["description"]
    if value.executor != config(store, run_id)["executor"] or mode.mode_id != subject["mode_id"] or mode.mode_name != name:
        raise AuditError("Normalized mode identity/name must preserve the original catalog")
    for field in FIELDS:
        checked_claim(getattr(mode, field), facts)
    result = mode.model_dump()
    result.update(condition_facts=[f.model_dump() for f in facts.values()], basis="MODE_DEFINITION",
        validation_status={"MODE_DEFINITION": "REVIEWED_BY_AGENT", "HISTORICAL_EVIDENCE": "NOT_VERIFIED",
            "SOURCE_VERIFIED": False, "HARDWARE_VALIDATED": False},
        evidence_refs=[r for r in store.records(run_id, "references") if r["case_id"] == value.case_id],
        source_case_id=value.case_id)
    record = {"definition_id": request["task_id"], "subject_id": subject["subject_id"], "case_id": value.case_id,
        "basis_hash": payload["basis_hash"], "policy_hash": _policy(), "raw_response": response, "result": result}
    store.put(run_id, "mode_definitions", record["definition_id"], record)
    return record


def mode_records(data):
    """Keep real failure mechanisms and each classification axis separate."""
    definitions = {d["case_id"]: d["result"] for d in data.get("mode_definitions", [])}
    result = []
    for subject in data["subjects"]:
        if subject["case_id"] not in definitions:
            continue
        mode = dict(definitions[subject["case_id"]])
        values = [a["result"] for a in data["assessments"] if a["case_id"] == subject["case_id"]]
        links = [l for v in values for l in v.get("label_links", [])]
        classes = {l["trigger_id"] for l in links if l["scheme"] == "V4"}
        mode.update(v4_theme_ids=sorted({key[0] for key in classes}), v4_class_ids=sorted(classes),
            v4_scenario_ids=sorted({key for l in links for key in l.get("construction_ids", [])}),
            api_trigger_ids=sorted({l["trigger_id"] for l in links if l["scheme"] == data.get("input_condition_scheme", "ORIGINAL42")}),
            execution_method_ids=sorted({m["method_id"] for e in data.get("baseline_execution", []) if e["case_id"] == subject["case_id"] for m in e["result"]["execution_method_links"]}),
            classification_links=links,
            execution_method_links=[m for e in data.get("baseline_execution", []) if e["case_id"] == subject["case_id"] for m in e["result"]["execution_method_links"]],
            execution_and_evidence=[e["result"] for e in data.get("baseline_execution", []) if e["case_id"] == subject["case_id"]],
            classification_rationales=[{"assessment_id": a["assessment_id"], "axis": a.get("baseline_axis"),
                "summary": a["result"].get("classification_summary"), "api_rows": a["result"]["rows"],
                "v4_rows": a["result"].get("v4_rows", [])} for a in data["assessments"] if a["case_id"] == subject["case_id"]],
            definition_versions={"API42": data["taxonomy"].get("definition_version"),
                "V4": (data.get("v4_taxonomy") or {}).get("definition_version")})
        mode["evidence_index"] = {"A1:" + f["fact_id"]: f for f in mode["condition_facts"]}
        for a in data["assessments"]:
            if a["case_id"] == subject["case_id"]:
                mode["evidence_index"].update({a["assessment_id"] + ":" + f["fact_id"]: f for f in a["result"].get("condition_facts", [])})
        for e in data.get("baseline_execution", []):
            if e["case_id"] == subject["case_id"]:
                mode["evidence_index"].update({e["execution_id"] + ":" + f["fact_id"]: f for f in e["result"]["condition_facts"]})
        result.append(mode)
    return result


def axis_payloads(store, run_id):
    from .trigger_workflow import classification_payloads, current_assessments
    if not enabled(store, run_id):
        return
    done = {(a["subject_id"], a.get("baseline_axis")) for a in current_assessments(store, run_id)}
    for base in classification_payloads(store, run_id, for_baseline_axes=True):
        if base["phase"] != "INIT":
            continue
        for axis in ("V4", "API42"):
            if (base["subject"]["subject_id"], axis) in done:
                continue
            if axis == "V4" and not base.get("v4_taxonomy"):
                raise AuditError("A2 needs the original frozen V4 source")
            payload = copy.deepcopy(base)
            payload.update(baseline_axis=axis, basis_hash=digest({"base": base["basis_hash"], "axis": axis}))
            if axis == "API42":
                payload.pop("v4_taxonomy", None)
            payload["input_scope"].update(classification_axis=axis, cross_axis_conversion="FORBIDDEN")
            yield "baseline_v4" if axis == "V4" else "baseline_api42", payload


def axis_instructions(axis):
    from .trigger_sparse import instructions
    return instructions() + ("\nA2 ONLY: organize V4 themes/condition classes/construction scenarios with independent reasons. Each selected positive construction needs construction_recipe: a readable test-design suggestion plus missing API/legal-domain facts, not a fabricated historical reproduction. Return rows=[], external_branches=[], execution_method_links=[]; no API42 labels.\n" if axis == "V4" else
        "\nA3 ONLY: classify the ORIGINAL42 API conditions. Return v4_rows=[], external_branches=[], execution_method_links=[]. Do not copy V4 labels. If known execution/internal dependencies cannot be expressed by this API axis, use summary NOT_APPLICABLE with exclusion_fact_ids and a specific explanation. Missing API details alone mean INSUFFICIENT_INFORMATION.\n")


class MethodEvidence(Contract):
    method_id: Literal["E1", "E2", "E3", "E4", "E5"]
    reason: str = Field(min_length=1)
    condition_fact_ids: list[str] = Field(min_length=1)


class ExecutionResponse(KnowledgeResponse):
    execution_conditions: Claim
    execution_method_links: list[MethodEvidence]
    evidence_gaps: list[str]
    source_verified: Literal[False] = False
    hardware_validated: Literal[False] = False


EXECUTION_INSTRUCTIONS = """A4 ONLY: organize execution conditions, E1-E5 methods and evidence gaps
for this existing CANN mode. Cite the original source through local condition_facts. V4
condition classes, concrete construction scenarios, API42 and the actual failure_mechanism
are separate. E1-E5 are not labels of any input taxonomy. Missing customer Wiki or hardware
tests do not invalidate the mode definition or condition classification. Existing links are
preserved by the program; do not claim they were read, search just to fill fields, invent
source verification or hardware validation. Select useful frozen E methods with reasons,
or an empty list with specific unknown execution conditions. Return ExecutionResponse at
the OUTER hash. This is a review/design note, never an execution result or human ACCEPT.
"""


def _execution_basis(store, run_id, subject):
    from .trigger_workflow import _basis, _v4
    return digest({"subject": _basis(store, run_id, subject), "axis": "EXECUTION",
        "methods": (_v4(store, run_id) or {}).get("methods", []), "available_evidence": _available_evidence(store, run_id, subject["case_id"])})


def _available_evidence(store, run_id, case_id):
    from .trigger_workflow import _linked_snapshots
    snapshots = _linked_snapshots(store, run_id, case_id)
    return {"original_references": [r for r in store.records(run_id, "references") if r["case_id"] == case_id],
        "capture_metadata": [{k: s[k] for k in ("snapshot_id", "url", "status", "title", "text_sha256") if k in s} for s in snapshots.values()],
        "scope": "REFERENCE_AND_CAPTURE_METADATA_ONLY; BODY_VERIFICATION_NOT_CLAIMED"}


def current_execution(store, run_id):
    from .xlsx_workflow import _policy
    subjects = {s["subject_id"]: s for s in store.records(run_id, "trigger_subjects")}
    return [r for r in store.records(run_id, "baseline_execution") if r["policy_hash"] == _policy()
        and r["subject_id"] in subjects and r["basis_hash"] == _execution_basis(store, run_id, subjects[r["subject_id"]])]


def execution_payloads(store, run_id):
    from .trigger_workflow import _v4, _settings
    if not enabled(store, run_id) or _settings(store, run_id)["phase"] != "INIT":
        return
    done = {r["subject_id"] for r in current_execution(store, run_id)}
    definitions = {r["subject_id"]: r for r in current_definitions(store, run_id)}
    for subject in store.records(run_id, "trigger_subjects"):
        if subject["subject_id"] in done or subject["subject_id"] not in definitions:
            continue
        yield {"subject": {**subject, "source_case": store.get(run_id, "cases", subject["case_id"])},
            "normalized_mode": definitions[subject["subject_id"]]["result"],
            "available_evidence": _available_evidence(store, run_id, subject["case_id"]),
            "methods": [m for m in (_v4(store, run_id) or {}).get("methods", []) if m["method_id"] in {"E1", "E2", "E3", "E4", "E5"}],
            "case_ids": [subject["case_id"]], "basis_hash": _execution_basis(store, run_id, subject),
            "response_schema": ExecutionResponse.model_json_schema()}


def accept_execution(store, run_id, request, response):
    from .xlsx_workflow import _policy, config
    payload = request["payload"]; subject = store.get(run_id, "trigger_subjects", payload["subject"]["subject_id"])
    if not enabled(store, run_id) or not subject or payload["basis_hash"] != _execution_basis(store, run_id, subject):
        raise AuditError("Execution review source/definition changed")
    value, facts = validate_common(payload, response, ExecutionResponse, request["request_hash"])
    if value.executor != config(store, run_id)["executor"]:
        raise AuditError("Execution review executor mismatch")
    checked_claim(value.execution_conditions, facts)
    known = {m["method_id"] for m in payload["methods"]}
    if len({l.method_id for l in value.execution_method_links}) != len(value.execution_method_links):
        raise AuditError("E1-E5 method links must be unique")
    for link in value.execution_method_links:
        if link.method_id not in known or not set(link.condition_fact_ids) <= set(facts) or len(link.condition_fact_ids) != len(set(link.condition_fact_ids)):
            raise AuditError("Execution method must cite local facts and a frozen E1-E5 definition")
    record = {"execution_id": request["task_id"], "subject_id": subject["subject_id"], "case_id": value.case_id,
        "basis_hash": payload["basis_hash"], "policy_hash": _policy(), "raw_response": response, "result": value.model_dump()}
    store.put(run_id, "baseline_execution", record["execution_id"], record)
    return record


def stage_gaps(data):
    gaps = []
    defined = {r["case_id"] for r in data.get("mode_definitions", [])}
    execution = {r["case_id"] for r in data.get("baseline_execution", [])}
    for subject in data["subjects"]:
        cid = subject["case_id"]
        if cid not in defined:
            gaps.append({"case_id": cid, "kind": "MODE_DEFINITION_PENDING", "reason": "A1 normalized definition is missing"})
        for axis in ("V4", "API42"):
            if not any(a["case_id"] == cid and a.get("baseline_axis") == axis for a in data["assessments"]):
                gaps.append({"case_id": cid, "kind": "BASELINE_AXIS_PENDING", "reason": "A2/A3 independent axis missing: " + axis})
        if cid not in execution:
            gaps.append({"case_id": cid, "kind": "BASELINE_EXECUTION_PENDING", "reason": "A4 execution/evidence review is missing"})
    return gaps


class CrossFinding(Contract):
    relation: Literal["SAME_MECHANISM_CANDIDATE", "SIMILAR_NAME_DIFFERENT_MECHANISM", "SHARED_CONSTRUCTION",
                      "DIFFERENT_API_CONDITIONS", "EXECUTION_DEPENDENT", "DEFINITION_UNCLEAR"]
    mode_ids: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)
    source_fact_ids: dict[str, list[str]]


class CrossDimensionReview(Contract):
    dimension: Literal["SAME_MECHANISM_CANDIDATE", "SIMILAR_NAME_DIFFERENT_MECHANISM", "SHARED_CONSTRUCTION",
                       "DIFFERENT_API_CONDITIONS", "EXECUTION_DEPENDENT", "DEFINITION_UNCLEAR"]
    status: Literal["REVIEWED", "NEEDS_CLARIFICATION"]
    reason: str = Field(min_length=1)
    finding_indexes: list[int] = Field(default_factory=list)


class CrossReviewResponse(Contract):
    request_hash: str
    executor: Literal["opencode", "codex"]
    producer: CatalogDraftProducer
    reviewed_mode_ids: list[str]
    findings: list[CrossFinding]
    comparison_checks: list[CrossDimensionReview]
    recommendation: Literal["READY", "READY_WITH_GAPS", "REWORK_REQUIRED"]
    reason: str = Field(min_length=1)
    self_check: SelfCheck
    automatic_merge: Literal[False] = False
    adoption_status: Literal["SUGGESTION_ONLY"] = "SUGGESTION_ONLY"


REVIEW_INSTRUCTIONS = """Cross-review the COMPLETE normalized original CANN mode collection.
This is not 30 unrelated summaries and not a dense pairwise matrix. Check whether mechanisms
are the same or different despite names; which modes share V4 construction scenarios while
requiring different API inputs; which depend on E1-E5; and which definitions need expert
clarification. V4 conditions/constructions are not failure_mechanisms. Shared labels never
merge modes. Cite keys in each named mode's evidence_index, retaining task-qualified scopes. Keep uncertainty visible and
do not invent equivalence, classifications, source verification or hardware results. Return
all reviewed_mode_ids exactly once; significant contradictions require REWORK_REQUIRED.
Return all six comparison_checks exactly once, with reasons even when there are no findings;
reference zero-based finding_indexes for the corresponding dimension. Missing information
means NEEDS_CLARIFICATION, not proof of mechanism equality/difference or a completed baseline.
No original mode is deleted, merged or changed. Candidate findings are SUGGESTION_ONLY.
Use the OUTER request_hash and actual producer. Report context limits as transport BLOCKED.
"""


def _review_basis(data):
    return digest({"profile": PROFILE, "registry": data.get("api42_registry"), "modes": data["mode_records"]})


def current_review(store, run_id, data=None):
    from .xlsx_workflow import _policy
    if data is None:
        # Do not project an existing baseline here: its validity check calls this
        # function through _index_identity. Hash only the review's direct inputs.
        from .trigger_workflow import _settings, _taxonomy, _v4, current_assessments
        cfg = _settings(store, run_id)
        data = {"subjects": store.records(run_id, "trigger_subjects"),
            "mode_definitions": current_definitions(store, run_id),
            "baseline_execution": current_execution(store, run_id),
            "assessments": current_assessments(store, run_id), "taxonomy": _taxonomy(store, run_id),
            "v4_taxonomy": _v4(store, run_id), "input_condition_scheme": cfg["input_condition_scheme"],
            "api42_registry": store.get(run_id, "api42_registry_receipts", cfg["api42_registry_id"])}
        data["mode_records"] = mode_records(data)
    basis = _review_basis(data)
    return next((r for r in store.records(run_id, "baseline_reviews") if r["policy_hash"] == _policy() and r["basis_hash"] == basis), None)


def review_payloads(store, run_id):
    from .trigger_workflow import _projection, _settings
    if not enabled(store, run_id) or _settings(store, run_id)["phase"] != "INIT":
        return
    data = _projection(store, run_id, include_baseline_review=False)
    if stage_gaps(data) or current_review(store, run_id, data):
        return
    yield {"mode_records": data["mode_records"], "api42_registry": data["api42_registry"],
        "case_ids": [s["case_id"] for s in data["subjects"]], "basis_hash": _review_basis(data),
        "input_scope": {"all_original_modes_complete": True, "original_raw_sources_frozen_in_store": True,
            "full_source_document_audit": False}, "response_schema": CrossReviewResponse.model_json_schema()}


def accept_review(store, run_id, request, response):
    from .xlsx_workflow import _policy, config
    from .trigger_workflow import _projection
    data = _projection(store, run_id, include_baseline_review=False)
    if not enabled(store, run_id) or stage_gaps(data) or request["payload"]["basis_hash"] != _review_basis(data):
        raise AuditError("Cross-review inputs changed or A1-A4 are incomplete")
    try:
        value = CrossReviewResponse.model_validate(response)
    except ValidationError as exc:
        raise AuditError("Invalid baseline cross-review: " + str(exc)) from exc
    ids = {m["mode_id"] for m in data["mode_records"]}
    if value.request_hash != request["request_hash"] or value.executor != config(store, run_id)["executor"] or not value.self_check.passed:
        raise AuditError("Cross-review identity, executor or self-check mismatch")
    if set(value.reviewed_mode_ids) != ids or len(value.reviewed_mode_ids) != len(ids):
        raise AuditError("Cross-review must review every original mode exactly once")
    dimensions = set(CrossDimensionReview.model_fields["dimension"].annotation.__args__)
    if {c.dimension for c in value.comparison_checks} != dimensions or len(value.comparison_checks) != len(dimensions):
        raise AuditError("Horizontal review must explicitly check all six comparison dimensions")
    indexed = set()
    for check in value.comparison_checks:
        if len(check.finding_indexes) != len(set(check.finding_indexes)) or any(i < 0 or i >= len(value.findings)
                or value.findings[i].relation != check.dimension for i in check.finding_indexes):
            raise AuditError("Horizontal comparison checks refer to the wrong findings")
        indexed.update(check.finding_indexes)
    if indexed != set(range(len(value.findings))):
        raise AuditError("Every horizontal finding needs its dimension check")
    facts = {m["mode_id"]: set(m["evidence_index"]) for m in data["mode_records"]}
    by_id = {m["mode_id"]: m for m in data["mode_records"]}
    if value.recommendation == "READY" and (any(m["failure_mechanism"]["status"] == "UNKNOWN" for m in by_id.values())
            or any(f.relation == "DEFINITION_UNCLEAR" for f in value.findings)
            or any(c.status == "NEEDS_CLARIFICATION" for c in value.comparison_checks)):
        raise AuditError("Unclear mechanisms/definitions require READY_WITH_GAPS or REWORK_REQUIRED")
    for finding in value.findings:
        modes = set(finding.mode_ids)
        if not modes <= ids or len(modes) != len(finding.mode_ids) or set(finding.source_fact_ids) != modes:
            raise AuditError("Cross-review findings must name distinct known modes and each one's support")
        if finding.relation not in {"EXECUTION_DEPENDENT", "DEFINITION_UNCLEAR"} and len(modes) < 2:
            raise AuditError("A cross-mode relationship needs at least two modes")
        for mode, refs in finding.source_fact_ids.items():
            if (not refs and not (finding.relation == "DEFINITION_UNCLEAR" and any(by_id[mode][f]["status"] == "UNKNOWN" for f in FIELDS))) or not set(refs) <= facts[mode]:
                raise AuditError("Cross-review references unknown definition facts")
        if finding.relation == "SHARED_CONSTRUCTION" and not set.intersection(*(set(by_id[m]["v4_scenario_ids"]) for m in modes)):
            raise AuditError("Shared construction findings need an actual shared V4 construction ID")
    record = {"review_id": request["task_id"], "basis_hash": _review_basis(data), "policy_hash": _policy(),
        "raw_response": response, "result": value.model_dump()}
    store.put(run_id, "baseline_reviews", record["review_id"], record)
    return record
