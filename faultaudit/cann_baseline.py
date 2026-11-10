"""Normalize original CANN modes before sparse classification and freezing."""
from __future__ import annotations

from .run_budget import scoped as run_scoped

import copy
import hashlib
from pathlib import Path
from typing import Literal
from pydantic import Field, ValidationError
from .contracts import Contract, CatalogDraftProducer, SelfCheck
from .knowledge_common import PROFILE, Claim, KnowledgeResponse, validate_common, checked_claim, enabled
from .store import AuditError, digest
from .source_manifest import (ManifestFact, FieldBinding, SELECTION_CONTRACT, materialize_fields,
                              build as source_manifest, canonical_fact)

FIELDS = ("fault_object", "failure_mechanism", "observable_symptoms", "input_trigger_conditions",
          "execution_trigger_conditions", "applicable_scope", "exclusion_boundaries")


@run_scoped
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
    condition_facts: list[ManifestFact]
    definition: ModeDefinition
    evidence_gaps: list[str] = Field(default_factory=list)


class DefinitionBindings(Contract):
    fault_object: FieldBinding
    failure_mechanism: FieldBinding
    observable_symptoms: FieldBinding
    input_trigger_conditions: FieldBinding
    execution_trigger_conditions: FieldBinding
    applicable_scope: FieldBinding
    exclusion_boundaries: FieldBinding


class SourceSelectionResponse(Contract):
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_id: str = Field(min_length=1)
    executor: Literal["opencode", "codex"]
    producer: CatalogDraftProducer
    self_check: SelfCheck
    field_bindings: DefinitionBindings
    evidence_gaps: list[str] = Field(default_factory=list)


def materialize_response(payload, response):
    """Retain the historical schema for audit; new A1 submissions select IDs only."""
    if payload.get("source_contract") != SELECTION_CONTRACT:
        return response, None
    try:
        value = SourceSelectionResponse.model_validate(response)
    except ValidationError as exc:
        raise AuditError("Invalid A1 source selection: " + str(exc)) from exc
    claims, facts, receipt = materialize_fields(payload["subject"]["source_case"], payload["source_manifest"],
                                               {field: getattr(value.field_bindings, field) for field in FIELDS})
    out = value.model_dump(exclude={"field_bindings"})
    out.update(condition_facts=facts, definition={"mode_id": payload["subject"]["mode_id"],
        "mode_name": payload["original_mode"]["description"], **claims})
    return out, receipt


INSTRUCTIONS = """Normalize THIS existing CANN mode into SourceSelectionResponse. The program preserves mode_id and
the original mode_name. This task defines the CANN failure_mechanism, NOT V4 classification.
V4 has 6 themes, 31 condition classes, 55 construction scenarios and 195 reference cases;
none is a failure-mechanism registry. API42 and E1-E5 are separate axes, assigned later.
For each of the seven field_bindings select origin and supporting source_ids.
SOURCE_DECLARATION selects original declarations: the program creates STATED text and facts.
MODEL_DERIVED needs source_ids, derived_text and reason; the program marks the claim INFERRED.
UNKNOWN needs a specific reason, empty source_ids and no derived_text. Never fill plausible
parameters, boundaries or mechanisms. Preserve conflicting original descriptions visibly.
Read each selected original_value for its meaning; blank/placeholder/gap text is not
positive technical support. Use UNKNOWN rather than asserting an absent condition.
Do not assign V4/API labels or adopt changes here. MODE_DEFINITION is the basis, not source
verification or hardware validation. Do not search merely to make this definition complete.
Read the full source. Return the supplied raw schema at the OUTER request_hash; no ACCEPT.
The source_manifest is immutable. Select source_id only; do NOT submit condition_facts,
source_refs, source_cells, quotes, headers, workbook hash, row or coordinate. The program
materializes SOURCE_RECORD facts and their exact original_value, including multiline and
__column_15 keys. Do not normalize a header or invent a failure_mechanism column. If that
field is a technical deduction, use MODEL_DERIVED with the actual supporting IDs.
SOURCE_DECLARATION can only cite the frozen workbook, never a webpage assertion.
Historical material facts require captured body evidence in the separate evidence task;
SOURCE_DECLARATION is not SOURCE_VERIFIED. GAP and SELF_CHECK are not source facts.
Any historical_rejected_inputs are review material only, including unsubmitted mechanical
repairs. Reuse their technical content only after checking the current frozen original;
return a fresh response with this task's identity and your actual producer. Do not treat
a missing backup filename as a missing original when its response hash still matches.
If compatibility_regeneration is present, read its field checks and correction reasons;
use them to repair the identified content without copying its old response identity.
"""


@run_scoped
def definition_basis(store, run_id, subject):
    return digest({"profile": PROFILE, "subject": subject,
        "catalog_mode": store.get(run_id, "catalog", subject["mode_id"]),
        "source": store.get(run_id, "cases", subject["case_id"])})


@run_scoped
def current_definitions(store, run_id):
    from .baseline_recovery import select_current
    return select_current(store, run_id)


def save_definition(store, run_id, record, manifest):
    from .baseline_recovery import save_definition as save
    return save(store, run_id, record, manifest)


@run_scoped
def payloads(store, run_id):
    cfg = store.get(run_id, "trigger_config", "config") or {}
    if not enabled(store, run_id) or cfg["phase"] != "INIT":
        return
    done = {r["subject_id"] for r in current_definitions(store, run_id)}
    catalog = {r["item_id"]: r for r in store.records(run_id, "catalog")}
    for subject in store.records(run_id, "trigger_subjects"):
        if subject["subject_id"] in done:
            continue
        from .baseline_recovery import route
        if route(store, run_id, subject, current_ids=done) != "DEFINE":
            continue
        source = store.get(run_id, "cases", subject["case_id"])
        from .baseline_recovery import rejected_contexts, regeneration_context
        yield {"subject": {**subject, "source_case": source}, "original_mode": catalog[subject["mode_id"]],
            "source_manifest": source_manifest(source), "source_manifest_required": True,
            "source_contract": SELECTION_CONTRACT,
            "historical_rejected_inputs": rejected_contexts(store, run_id, subject),
            "compatibility_regeneration": regeneration_context(store, run_id, subject),
            "case_ids": [subject["case_id"]], "basis_hash": definition_basis(store, run_id, subject),
            "input_scope": {"original_source_complete": True, "basis": "MODE_DEFINITION"},
            "response_schema": SourceSelectionResponse.model_json_schema()}


@run_scoped
def accept(store, run_id, request, response):
    from .run_budget import require_pinned
    require_pinned(store, run_id)
    from .xlsx_workflow import _policy, config
    from .xlsx_workflow import check_current_request
    check_current_request(store, run_id, request)
    if request["kind"] != "baseline_define":
        raise AuditError("A1 definition must use its assigned workflow kind")
    payload = request["payload"]
    if payload.get("source_contract") != SELECTION_CONTRACT:
        raise AuditError("New A1 tasks must use the program-owned source selection contract")
    subject = store.get(run_id, "trigger_subjects", payload["subject"]["subject_id"])
    if not enabled(store, run_id) or not subject or payload["basis_hash"] != definition_basis(store, run_id, subject):
        raise AuditError("Mode definition input changed; request a fresh task")
    if (payload["subject"]["source_case"] != store.get(run_id, "cases", subject["case_id"])
            or payload["original_mode"] != store.get(run_id, "catalog", subject["mode_id"])):
        raise AuditError("A1 source manifest input differs from the frozen original row/catalog")
    materialized, bindings = materialize_response(payload, response)
    value, facts = validate_common(payload, materialized, DefinitionResponse, request["request_hash"])
    mode = value.definition
    name = payload["original_mode"]["description"]
    if value.executor != config(store, run_id)["executor"] or mode.mode_id != subject["mode_id"] or mode.mode_name != name:
        raise AuditError("Normalized mode identity/name must preserve the original catalog")
    for field in FIELDS:
        claim = getattr(mode, field)
        checked_claim(claim, facts)
        if claim.status == "INFERRED" and not claim.derivation_reason.strip():
            raise AuditError("An inferred A1 claim needs a derivation_reason, separate from the original quotation")
    result = mode.model_dump()
    result.update(condition_facts=[canonical_fact(f.model_dump()) for f in facts.values()], basis="MODE_DEFINITION",
        evidence_gaps=value.evidence_gaps,
        validation_status={"MODE_DEFINITION": "REVIEWED_BY_AGENT", "HISTORICAL_EVIDENCE": "NOT_VERIFIED",
            "SOURCE_VERIFIED": False, "HARDWARE_VALIDATED": False},
        evidence_refs=[r for r in store.records(run_id, "references") if r["case_id"] == value.case_id],
        source_case_id=value.case_id)
    if bindings:
        result["source_binding"] = bindings
    record = {"definition_id": request["task_id"], "subject_id": subject["subject_id"], "case_id": value.case_id,
        "basis_hash": payload["basis_hash"], "policy_hash": _policy(), "raw_response": response, "result": result}
    save_definition(store, run_id, record, payload["source_manifest"])
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


@run_scoped
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
            from .baseline_recovery import axis_basis
            payload.update(baseline_axis=axis, basis_hash=axis_basis(store, run_id, base["subject"], axis))
            if axis == "API42":
                payload.pop("v4_taxonomy", None)
            payload["input_scope"].update(classification_axis=axis, cross_axis_conversion="FORBIDDEN")
            yield "baseline_v4" if axis == "V4" else "baseline_api42", payload


def axis_instructions(axis, payload=None):
    from .trigger_sparse import instructions, citation_example
    if axis == "V4":
        return instructions() + """\nA2 ONLY: organize V4 themes/condition classes/construction scenarios with independent
reasons. Each selected positive construction needs construction_recipe: a readable test-design
suggestion plus missing API/legal-domain facts, not a fabricated historical reproduction.
Return rows=[], external_branches=[], execution_method_links=[]; no API42 labels.
""" + citation_example(payload or {})
    return instructions() + """\nA3 ONLY: classify ORIGINAL42 API input conditions, independently of V4.
Return v4_rows=[], external_branches=[], execution_method_links=[]. Preserve all 42 original
definitions; assess selected relevant rules, not a dense matrix. Three semantic states:
APPLICABLE needs grounded API input facts and all Requires/Skip checks. PARTIAL remains
available for grounded but incomplete conditions. NOT_APPLICABLE needs a positively evidenced
failed Requires/active exclusion for a specific rule, never mere lack of information.
UNKNOWN is valid: represent it with classification_summary.status=INSUFFICIENT_INFORMATION,
specific unknowns, and no fabricated positive/exclusion rows or links. Omitted rule rows are
NOT_ASSESSED, not 42 negative judgments. A completed attempt may legitimately remain unknown.
Whole-axis summary NOT_APPLICABLE is stronger: cite exclusion_fact_ids proving a non-API
dependency (e.g. an explicitly documented host-thread race). Failure to find shape, dtype,
API parameters or Wiki text does not prove that dependency. Never infer non-API from absence.
Example: description 'some precision failures', no API detail -> INSUFFICIENT_INFORMATION,
unknowns=['legal API inputs/trigger missing'], rows=[], scenarios=[], label_links=[].
Example: documented 'only host thread interleaving, same arguments/binary' may support a
whole-axis exclusion using actual quoted non-API facts; it is not a keyword shortcut.
definition_init does not require historical webpage confirmation to classify original claims.
source_relation is independent of applicability: without aligned captured body use UNKNOWN;
PARTIAL needs partial aligned support; MATCH still needs the existing direct body gates.
Do not upgrade UNKNOWN to a label, NOT_APPLICABLE or source MATCH to finish a task.
"""


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


@run_scoped
def _execution_basis(store, run_id, subject):
    from .trigger_workflow import _basis, _v4
    from .baseline_recovery import definition_dependency
    return digest({"subject": definition_dependency(store, run_id, subject), "axis": "EXECUTION",
        "methods": [m for m in (_v4(store, run_id) or {}).get("methods", []) if m["method_id"] in {"E1", "E2", "E3", "E4", "E5"}],
        "available_evidence": _available_evidence(store, run_id, subject["case_id"])})


@run_scoped
def _available_evidence(store, run_id, case_id):
    from .trigger_workflow import _linked_snapshots
    snapshots = _linked_snapshots(store, run_id, case_id)
    return {"original_references": [r for r in store.records(run_id, "references") if r["case_id"] == case_id],
        "capture_metadata": [{k: s[k] for k in ("snapshot_id", "url", "status", "title", "text_sha256") if k in s} for s in snapshots.values()],
        "scope": "REFERENCE_AND_CAPTURE_METADATA_ONLY; BODY_VERIFICATION_NOT_CLAIMED"}


@run_scoped
def current_execution(store, run_id):
    from .xlsx_workflow import _policy, config
    subjects = {s["subject_id"]: s for s in store.records(run_id, "trigger_subjects")}
    records = [r for r in store.records(run_id, "baseline_execution") if r["subject_id"] in subjects
        and r["basis_hash"] == _execution_basis(store, run_id, subjects[r["subject_id"]])]
    current = [r for r in records if r["policy_hash"] == _policy()]
    done = {r["subject_id"] for r in current}
    from .baseline_recovery import revalidate_stage
    for record in records:
        if record["subject_id"] in done:
            continue
        value = revalidate_stage(store, run_id, record, "execution_id", "baseline_execution",
            lambda p, r, h: validate_execution(p, r, h, config(store, run_id)["executor"]))
        if value:
            current.append(value); done.add(value["subject_id"])
    return current


@run_scoped
def execution_payloads(store, run_id):
    from .trigger_workflow import _v4, _settings
    from .baseline_recovery import technical_projection
    if not enabled(store, run_id) or _settings(store, run_id)["phase"] != "INIT":
        return
    done = {r["subject_id"] for r in current_execution(store, run_id)}
    definitions = {r["subject_id"]: r for r in current_definitions(store, run_id)}
    for subject in store.records(run_id, "trigger_subjects"):
        if subject["subject_id"] in done or subject["subject_id"] not in definitions:
            continue
        yield {"subject": {**subject, "source_case": store.get(run_id, "cases", subject["case_id"])},
            "normalized_mode": technical_projection(definitions[subject["subject_id"]]["result"]),
            "available_evidence": _available_evidence(store, run_id, subject["case_id"]),
            "methods": [m for m in (_v4(store, run_id) or {}).get("methods", []) if m["method_id"] in {"E1", "E2", "E3", "E4", "E5"}],
            "case_ids": [subject["case_id"]], "basis_hash": _execution_basis(store, run_id, subject),
            "response_schema": ExecutionResponse.model_json_schema()}


@run_scoped
def accept_execution(store, run_id, request, response):
    from .xlsx_workflow import _policy, config
    from .xlsx_workflow import check_current_request
    check_current_request(store, run_id, request)
    payload = request["payload"]; subject = store.get(run_id, "trigger_subjects", payload["subject"]["subject_id"])
    if not enabled(store, run_id) or not subject or payload["basis_hash"] != _execution_basis(store, run_id, subject):
        raise AuditError("Execution review source/definition changed")
    result = validate_execution(payload, response, request["request_hash"], config(store, run_id)["executor"])
    record = {"execution_id": request["task_id"], "subject_id": subject["subject_id"], "case_id": subject["case_id"],
        "basis_hash": payload["basis_hash"], "policy_hash": _policy(), "raw_response": response, "result": result}
    store.put(run_id, "baseline_execution", record["execution_id"], record)
    return record


def validate_execution(payload, response, request_hash, executor):
    value, facts = validate_common(payload, response, ExecutionResponse, request_hash)
    if value.executor != executor:
        raise AuditError("Execution review executor mismatch")
    checked_claim(value.execution_conditions, facts)
    known = {m["method_id"] for m in payload["methods"]}
    if len({l.method_id for l in value.execution_method_links}) != len(value.execution_method_links):
        raise AuditError("E1-E5 method links must be unique")
    for link in value.execution_method_links:
        if link.method_id not in known or not set(link.condition_fact_ids) <= set(facts) or len(link.condition_fact_ids) != len(set(link.condition_fact_ids)):
            raise AuditError("Execution method must cite local facts and a frozen E1-E5 definition")
    return value.model_dump()


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


@run_scoped
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


@run_scoped
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


@run_scoped
def accept_review(store, run_id, request, response):
    from .xlsx_workflow import _policy, config
    from .xlsx_workflow import check_current_request
    check_current_request(store, run_id, request)
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
