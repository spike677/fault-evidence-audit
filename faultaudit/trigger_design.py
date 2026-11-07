"""Bounded design-card tasks over current classifications; no device executor."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, ValidationError

from .contracts import Contract, CatalogDraftProducer, SelfCheck
from .store import AuditError, digest


class DesignVariable(Contract):
    name: str = Field(min_length=1)
    kind: Literal["INPUT", "DERIVED", "CONTEXT", "EXECUTION_PROTOCOL"]
    proposed_values: list[str] = Field(default_factory=list)
    condition_fact_ids: list[str] = Field(default_factory=list)
    guide_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class Participant(Contract):
    participant_id: str = Field(min_length=1)
    role: Literal["TARGET", "PREDECESSOR", "INTERFERER", "PRODUCER", "CONSUMER"]
    target_call_id: str = Field(min_length=1)
    input_assignment: str = Field(min_length=1)
    output_owner: str = Field(min_length=1)
    context: str = Field(min_length=1)
    stream: str = Field(min_length=1)
    executor: str = Field(min_length=1)
    lifecycle: str = Field(min_length=1)


class TargetInvariant(Contract):
    target_call_id: str = Field(min_length=1)
    same_target_arguments_required: Literal[True] = True
    same_target_binary_required: Literal[True] = True
    variable_participant_ids: list[str] = Field(default_factory=list)


class DesignCard(Contract):
    card_id: str = Field(min_length=1)
    assessment_id: str = Field(min_length=1)
    status: Literal["DESIGN_READY", "NEEDS_FACTS", "CAPABILITY_BLOCKED"]
    category_ids: list[str] = Field(default_factory=list)
    construction_ids: list[str] = Field(default_factory=list)
    guide_ids: list[str] = Field(default_factory=list)
    execution_method_ids: list[str] = Field(default_factory=list)
    condition_fact_ids: list[str] = Field(default_factory=list)
    variables: list[DesignVariable] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    reference: str = Field(min_length=1)
    target_path: str = Field(min_length=1)
    checks: list[str] = Field(min_length=1)
    protocol_steps: list[str] = Field(default_factory=list)
    participants: list[Participant] = Field(default_factory=list)
    target_invariant: TargetInvariant | None = None
    serial_baseline: str = ""
    event_record: str = ""
    consumer_wait: str = ""
    required_capabilities: list[str] = Field(default_factory=list)
    capability_gaps: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    execution_status: Literal["NOT_RUN"] = "NOT_RUN"
    path_coverage: Literal["UNKNOWN", "NOT_COVERED", "DESIGN_ONLY"] = "DESIGN_ONLY"
    execution_implemented: Literal[False] = False


class DesignResponse(Contract):
    schema_version: Literal["1.0"] = "1.0"
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    executor: Literal["codex", "opencode"]
    producer: CatalogDraftProducer
    case_id: str = Field(min_length=1)
    cards: list[DesignCard] = Field(min_length=1)
    self_check: SelfCheck


def instructions():
    return """Return a DesignResponse bound to this OUTER request_hash. This is phase-one
CASE DESIGN ONLY: no NPU, threads, memory reuse, output prefill or multi-rank execution occurs.
Read the complete current source record, provided classification facts, selected full category
definitions, frozen guidance and capability profile. Make a small useful set of cards; do not
expand every guide into a task or search for missing fields. At least one card is needed per
case; when no positive condition is known use NEEDS_FACTS with category_ids=[] and explain what
input/control facts are missing. A design is not a confirmed root cause or a new mode.
Each card belongs to exactly one provided assessment_id. Use only that assessment's condition
fact IDs; never stitch separate source issues into a completed match. Guidance gives proposed
construction, not observed historical inputs. Original declarations, code inference and actual
execution remain distinct. Every card states variables, boundary, reference, target path,
checks, required capabilities and missing conditions. Unknown values stay symbolic/unknown.
Do not call loopRpSize, offset formula, tiling or buffer capacity an exposed API argument.
Variables grounded only in DERIVED_CONTROL/PATH_PREDICATE facts must use kind DERIVED. Legal
proposed inputs may instead cite selected guidance explicitly. All outputs are NOT_RUN,
execution_implemented=false, path_coverage UNKNOWN/NOT_COVERED/DESIGN_ONLY. A formula-only
address design cannot claim device coverage. DESIGN_READY means the design is specified,
not executed or known to reproduce the original incident.
Choose E1-E5 or B3.2-PRODUCER-CONSUMER-v1 only when useful. A protocol is not a synchronization
root-cause label. E2 fixes target T; predecessors P/Q vary. E4 compares each target call to its
own serial reference; interfering threads may have different parameters. Keep each participant's
argument/output ownership, context, stream, executor and lifecycle. Do not falsely claim all
participants have the same arguments. E2/E4/cross-stream cards require target_invariant and a
serial_baseline. Distinct concurrent participants cannot share an output buffer accidentally.
Cross-stream plans need separate producer/consumer, event_record and consumer_wait positions.
E3 uses only a supported out/state binding; otherwise mark CAPABILITY_BLOCKED/NEEDS_FACTS.
Keep all existing capture and input-size gaps visible. Do not claim a selected guide is a
device-verified history case; companion source audit is unavailable. Complete one bounded
self_check for numeric meanings, quotes, counterevidence, issue scope and technical/event split.
If the full request exceeds execution capacity return the standard transport BLOCKED response;
never trim input or invent a successful partial read.
"""


def _basis(store, run_id, case_id, assessments=None):
    from .trigger_workflow import current_assessments, _settings
    settings = _settings(store, run_id)
    assessments = [a for a in (current_assessments(store, run_id) if assessments is None else assessments) if a["case_id"] == case_id]
    return digest({"case": store.get(run_id, "cases", case_id),
        "assessments": sorted((a["assessment_id"], digest(a["result"])) for a in assessments),
        "v4": settings.get("v4_taxonomy_id"), "mapping": settings.get("mapping_id"),
        "capabilities": settings.get("execution_capabilities")})


def current_designs(store, run_id, assessments=None):
    from .xlsx_workflow import _policy
    from .trigger_workflow import current_assessments
    assessments = current_assessments(store, run_id) if assessments is None else assessments
    bases = {}
    results = []
    for value in store.records(run_id, "trigger_designs"):
        cid = value["case_id"]
        if cid not in bases:
            bases[cid] = _basis(store, run_id, cid, assessments)
        if value["policy_hash"] == _policy() and value["basis_hash"] == bases[cid]:
            results.append(value)
    return sorted(results, key=lambda v: v["design_id"])


def payloads(store, run_id, *, pending_case_ids=()):
    from .trigger_workflow import _v4, _settings, current_assessments
    frozen = _v4(store, run_id)
    if not frozen:
        return
    settings = _settings(store, run_id)
    current = current_assessments(store, run_id)
    done = {v["case_id"] for v in current_designs(store, run_id, current)}
    from .xlsx_workflow import _policy
    policy = _policy()
    current_blocks = [b for b in store.records(run_id, "workflow_blocks") if b.get("policy_hash") == policy]
    for case in store.records(run_id, "cases"):
        cid = case["case_id"]
        if cid in done or cid in pending_case_ids:
            continue
        assessments = [a for a in current if a["case_id"] == cid]
        if not assessments:
            continue
        views = []
        categories = set()
        for a in assessments:
            result = a["result"]
            selected = [r for r in result["v4_rows"] if r["applicability"] in {"APPLICABLE", "PARTIAL"}]
            categories.update(r["trigger_id"] for r in selected)
            views.append({"assessment_id": a["assessment_id"], "result_sha256": digest(result),
                "issue_label": a["issue_label"], "snapshot_id": a.get("snapshot_id"),
                "source_relation": result["source_relation"], "condition_facts": result["condition_facts"],
                "selected_rows": [{k: r[k] for k in ("trigger_id", "applicability", "relation", "condition_fact_ids", "reason", "coverage", "unknowns")} for r in selected],
                "known_mechanisms": [{k: d[k] for k in ("name", "mechanism", "conditions", "unknowns", "evidence_basis")} for d in result["details"]]})
        guides = [g for g in frozen["guides"] if g["category_id"] in categories]
        selected_items = [v for v in frozen["items"] if v["id"] in categories]
        # Definitions/Requires/Skip are never clipped. Selection is a design
        # scope, not a claim to have classified only the selected categories.
        items = [{k: v[k] for k in ("id", "name", "definition", "requires", "skip_if", "construction_requires",
                    "path_requires", "analysis_requires", "construction_ids", "allowed_fact_roles")} for v in selected_items]
        ids = {code for item in items for code in item["construction_ids"]}
        blocks = [b for b in current_blocks if cid in b.get("case_ids", [])]
        yield {"case": case, "case_ids": [cid], "assessment_views": views,
            "v4_definition_version": frozen["definition_version"], "mapping_id": settings["mapping_id"],
            "selected_categories": items,
            "selected_constructions": [{k: c[k] for k in ("id", "name", "definition")} for c in frozen["constructions"] if c["id"] in ids],
            "guidance": [{k: g[k] for k in ("guide_id", "category_id", "title", "text", "source_status", "line_start", "line_end")} for g in guides],
            "methods": [{k: m[k] for k in ("method_id", "name", "definition", "execution_implemented")} for m in frozen["methods"]],
            "execution_capabilities": settings["execution_capabilities"], "blocking_gaps": blocks,
            "input_scope": {"kind": "SELECTED_DESIGN_GUIDANCE", "selected_category_ids": sorted(categories),
                "selected_guide_ids": [g["guide_id"] for g in guides], "total_frozen_guides": 195,
                "selected_category_definitions_complete": True, "full_document_audit": False,
                "unselected_predicate_checklists_remain_in_store": True},
            "basis_hash": _basis(store, run_id, cid, current), "response_schema": DesignResponse.model_json_schema()}


def validate_design(payload, response, request_hash):
    try:
        result = DesignResponse.model_validate(response)
    except ValidationError as exc:
        raise AuditError("Invalid design-card response: " + str(exc)) from exc
    if result.request_hash != request_hash or result.case_id != payload["case"]["case_id"]:
        raise AuditError("Design identity must match its current case and request")
    views = {v["assessment_id"]: v for v in payload["assessment_views"]}
    categories = {v["id"]: v for v in payload["selected_categories"]}
    guides = {v["guide_id"]: v for v in payload["guidance"]}
    methods = {v["method_id"] for v in payload["methods"]}
    ids = [c.card_id for c in result.cards]
    if len(ids) != len(set(ids)):
        raise AuditError("Design card IDs must be unique")
    for card in result.cards:
        if card.assessment_id not in views:
            raise AuditError("Design cannot borrow another case or stale issue assessment")
        view = views[card.assessment_id]
        facts = {f["fact_id"]: f for f in view["condition_facts"]}
        if not set(card.condition_fact_ids) <= set(facts):
            raise AuditError("Design facts must stay inside its one selected source issue")
        applicable = {r["trigger_id"] for r in view["selected_rows"]}
        if not set(card.category_ids) <= applicable or not set(card.category_ids) <= set(categories):
            raise AuditError("Design category is not independently classified for this issue")
        if not card.category_ids and (card.status != "NEEDS_FACTS" or not card.unknowns):
            raise AuditError("An unclassified case needs a visible missing-facts card, not inferred applicability")
        codes = {v for key in card.category_ids for v in categories[key]["construction_ids"]}
        if not set(card.construction_ids) <= codes or not set(card.guide_ids) <= set(guides):
            raise AuditError("Design construction/guidance is outside the complete selected scope")
        if any(guides[key]["category_id"] not in card.category_ids for key in card.guide_ids):
            raise AuditError("Guidance cannot transfer labels across categories")
        if not set(card.execution_method_ids) <= methods:
            raise AuditError("Unknown execution protocol; protocols are not new input classes")
        for variable in card.variables:
            if not set(variable.condition_fact_ids) <= set(facts) or not set(variable.guide_ids) <= set(card.guide_ids):
                raise AuditError("Design variable must use scoped facts or explicitly selected guidance")
            if not variable.condition_fact_ids and not variable.guide_ids:
                raise AuditError("Design variables need source/guidance provenance")
            if variable.kind == "INPUT" and variable.condition_fact_ids and any(facts[key]["role"] in {
                    "DERIVED_CONTROL", "PATH_PREDICATE", "CAPACITY", "INTERNAL_COMPUTATION"} for key in variable.condition_fact_ids):
                raise AuditError("An internal derived quantity cannot be relabeled as an API input")
        if card.status in {"NEEDS_FACTS", "CAPABILITY_BLOCKED"} and not (card.unknowns or card.capability_gaps):
            raise AuditError("Incomplete/blocked design must name its actual gap")
        participant_ids = [p.participant_id for p in card.participants]
        if len(participant_ids) != len(set(participant_ids)):
            raise AuditError("Participant IDs must be unique within a protocol")
        scoped = set(card.execution_method_ids) & {"E2", "E4", "B3.2-PRODUCER-CONSUMER-v1"}
        if scoped:
            invariant = card.target_invariant
            if not invariant or not card.serial_baseline or not card.protocol_steps:
                raise AuditError("State/concurrency plans need a target-scoped comparison and serial baseline")
            participants = {p.participant_id: p for p in card.participants}
            if not participants or not set(invariant.variable_participant_ids) <= set(participants):
                raise AuditError("Variable predecessor/interferer identities must be recorded")
            if not any(p.target_call_id == invariant.target_call_id and p.role in {"TARGET", "CONSUMER"} for p in card.participants):
                raise AuditError("The compared target call must have its own participant and output")
            if "E4" in scoped and (not any(p.role == "INTERFERER" for p in card.participants)
                    or len({p.output_owner for p in card.participants}) != len(card.participants)):
                raise AuditError("Host isolation needs an interfering participant and distinct output ownership")
            if "B3.2-PRODUCER-CONSUMER-v1" in scoped and (not card.event_record or not card.consumer_wait
                    or not {"PRODUCER", "CONSUMER"} <= {p.role for p in card.participants}):
                raise AuditError("Cross-stream design needs producer, consumer, event record and wait positions")
    check = result.self_check
    if not check.passed or check.issues or not all(getattr(check, key) for key in (
            "numeric_meaning_checked", "citations_checked", "counterevidence_checked", "issue_scope_checked", "event_vs_technical_checked")):
        raise AuditError("Complete the bounded design self-check; unknowns belong in explicit gaps")
    return result.model_dump()


def accept_design(store, run_id, request, response):
    from .xlsx_workflow import _policy, config
    payload = request["payload"]
    if response.get("executor") != config(store, run_id)["executor"] or payload["basis_hash"] != _basis(store, run_id, payload["case"]["case_id"]):
        raise AuditError("Design executor or classification inputs changed; regenerate without deleting history")
    result = validate_design(payload, response, request["request_hash"])
    value = {"design_id": request["task_id"], "case_id": result["case_id"], "basis_hash": payload["basis_hash"],
        "policy_hash": _policy(), "raw_response": response, "result": result}
    store.put(run_id, "trigger_designs", value["design_id"], value)
    return value
