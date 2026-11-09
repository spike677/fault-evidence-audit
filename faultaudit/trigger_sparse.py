"""V5 sparse, scenario-bound classification over the existing evidence gates.

Unselected rules are NOT_ASSESSED. Temporary unknown rows adapt the old shared
validators in memory only; they are never requested, stored or counted.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, ValidationError

from .contracts import Contract
from .store import AuditError
from .trigger_assessment import TriggerAssessment
from .trigger_v4 import canonical_conditions

CONTRACT = "SPARSE_SCENARIOS_V5"
POSITIVE = {"APPLICABLE", "PARTIAL"}


class ClassificationSummary(Contract):
    status: Literal["CLASSIFIED", "BRANCH_ONLY", "EXECUTION_ONLY", "NOT_APPLICABLE", "INSUFFICIENT_INFORMATION"]
    reason: str = Field(min_length=1)
    unknowns: list[str] = Field(default_factory=list)
    exclusion_fact_ids: list[str] = Field(default_factory=list)


class Scenario(Contract):
    scenario_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    condition_fact_ids: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)


class LabelLink(Contract):
    scheme: Literal["ORIGINAL42", "REVISED42", "V4", "BRANCH"]
    definition_version: str = Field(min_length=1)
    trigger_id: str = Field(min_length=1)
    detail_ids: list[str] = Field(min_length=1)
    scenario_ids: list[str] = Field(min_length=1)
    condition_fact_ids: list[str] = Field(min_length=1)
    construction_ids: list[str] = Field(default_factory=list)


class ExecutionMethodLink(Contract):
    method_id: Literal["E1", "E2", "E3", "E4", "E5"]
    condition_fact_ids: list[str] = Field(min_length=1)
    scenario_ids: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)


class CandidateProposal(Contract):
    action: Literal["CLASSIFY_EXISTING_CANDIDATE", "EXTEND_DETAIL_CANDIDATE",
                    "PROPOSE_NEW_MODE_CANDIDATE", "INSUFFICIENT_EVIDENCE"]
    closest_mode_ids: list[str] = Field(default_factory=list)
    detail_ids: list[str] = Field(default_factory=list)
    difference: str = ""
    reason: str = Field(min_length=1)
    adoption_status: Literal["SUGGESTION_ONLY"] = "SUGGESTION_ONLY"


class SparseAssessment(TriggerAssessment):
    classification_contract: Literal["SPARSE_SCENARIOS_V5"]
    classification_summary: ClassificationSummary
    scenarios: list[Scenario]
    scenario_relation: Literal["OR", "UNKNOWN"] = "UNKNOWN"
    label_links: list[LabelLink]
    candidate_proposal: CandidateProposal | None = None
    execution_method_links: list[ExecutionMethodLink] = Field(default_factory=list)


def schema():
    return SparseAssessment.model_json_schema()


def frame_version(payload, scheme):
    taxonomy = payload.get("v4_taxonomy") if scheme == "V4" else payload["taxonomy"]
    if not taxonomy:
        raise AuditError("V4 labels require frozen V4 definitions")
    version = taxonomy.get("definition_version") or taxonomy.get("taxonomy_hash") or taxonomy.get("taxonomy_id") or "UNVERSIONED"
    return version + ("/BRANCH23" if scheme == "BRANCH" else "")


def input_scheme(payload):
    return payload.get("input_condition_scheme", "REVISED42")


def instructions():
    return """V5 SPARSE CLASSIFICATION, not a dense 42/31 matrix. Return SparseAssessment,
classification_contract=SPARSE_SCENARIOS_V5. Read the full frozen rule catalogs, but output only
grounded relevant APPLICABLE/PARTIAL rules or specific evidenced exclusions. Omit unselected
UNKNOWN rows, construction checks and branch leaves; omission means NOT_ASSESSED, never false.
For every SELECTED rule retain its complete definition/Requires/Skip checks. Unknown checks
remain unknown and prohibit full APPLICABLE/MATCH. Known source clues may support PARTIAL
without incident confirmation. All original evidence, semantic-role and formal-adoption gates
remain in force. This is classification/design, not device execution or human ACCEPT.
V4 has 6 themes, 31 CONDITION classes, 55 CONSTRUCTION scenarios and 195 reference cases.
S5 is a condition class. Actual causal mechanisms belong to CANN failure_mechanism/details,
not V4 classes or constructions. Do not redefine any frozen knowledge source.
Use payload.input_condition_scheme for rows: ORIGINAL42 preserves the original API42 clauses;
REVISED42 is only the separately versioned compatibility profile. Crosswalks never assign labels.
Extract local condition_facts, mechanism details, then scenarios and typed label_links. Each
positive 42/V4/Branch label MUST have a link with the supplied scheme/version, detail IDs,
condition fact IDs and local scenario IDs. Never infer links by taxonomy crosswalk. Detail
trigger_ids is the derived current API42 list; V4/Branch links stay separate.
Each selected positive construction must be explicitly named in a V4 label_link.construction_ids,
with its own checked definition and fact support; do not inherit every construction of a class.
E1-E5 execution_method_links are independent: cite local facts/scenarios and explain why useful.
They do not claim execution or become API42/V4 labels. Method-only organization can be EXECUTION_ONLY.
Scenarios belong to THIS assessment/current source issue. Within a scenario the cited facts
are observed/reported together, NOT proven sufficient to cause failure. Different scenarios
must not be stitched together. Use scenario_relation OR only when the source supports alternative
scenarios, otherwise UNKNOWN. Same case co-occurrence is not same-scenario co-occurrence.
If only implementation/execution/environment dependencies are identified, return BRANCH_ONLY
with grounded branch links; this does not prove all input categories inapplicable. If no label
can be grounded, use INSUFFICIENT_INFORMATION with a specific reason and unknowns, empty rows,
empty scenarios/links where appropriate, and preserve the original mechanism detail in Init.
For each selected V4 category assess only relevant construction codes, retaining full definitions
for those selected. Construction capability, path and execution remain separate; NOT_RUN only.
Use the existing formal decision unchanged. In incremental runs candidate_proposal may separately
propose an extension/new mechanism with a quoted current detail, closest known modes and concrete
differences. Unknown comparisons do not prove novelty; candidates are SUGGESTION_ONLY and do not
require pretending every old mode NOT_COVERED. Never use an unrelated search candidate's root cause.
Continue to compare the declared mechanism baseline independently where supplied. Do not inherit
preassigned target labels as evidence. Preserve conflicts, input/capture gaps and original sources.
No search merely to fill unknown fields. If the complete request cannot be read, report BLOCKED.
"""


def _unique(values, name):
    if len(values) != len(set(values)):
        raise AuditError(name + " must be unique")
    return set(values)


def _unknown(item, family=None):
    return {"trigger_id": item["id"], "applicability": "UNKNOWN", "relation": "UNKNOWN",
        "evidence_basis": "UNKNOWN", "reason": "Unselected; not assessed",
        "predicate_checks": [{"clause_role": role, "clause": text, "result": "UNKNOWN"}
            for role, text in sorted(canonical_conditions(item, family))]}


def validate_sparse(payload, response, request_hash):
    from .trigger_assessment import validate_assessment
    try:
        sparse = SparseAssessment.model_validate(response)
    except ValidationError as exc:
        raise AuditError("Invalid V5 sparse assessment: " + str(exc)) from exc
    raw = sparse.model_dump()
    stage = payload.get("baseline_axis")
    if stage == "V4" and (sparse.rows or sparse.external_branches or sparse.execution_method_links or any(l.scheme != "V4" for l in sparse.label_links)):
        raise AuditError("A2 classifies V4 only; API42 and execution methods are independent tasks")
    if stage == "API42" and (sparse.v4_rows or sparse.external_branches or sparse.execution_method_links or any(l.scheme != "ORIGINAL42" for l in sparse.label_links)):
        raise AuditError("A3 classifies original API42 only; no crosswalk-derived V4 labels")
    if stage and sparse.candidate_proposal:
        raise AuditError("Baseline axis tasks do not propose new CANN modes")
    axis = input_scheme(payload)
    selected = {axis: {r.trigger_id: r for r in sparse.rows},
                "V4": {r.trigger_id: r for r in sparse.v4_rows},
                "BRANCH": {c.category_id: c for b in sparse.external_branches for c in b.category_checks}}
    for name, values in (("REVISED42", sparse.rows), ("V4", sparse.v4_rows)):
        _unique([r.trigger_id for r in values], name + " labels")
        if any(r.applicability == "UNKNOWN" for r in values):
            raise AuditError("Omit UNKNOWN rules in sparse output; put unresolved facts in the summary")
    for b in sparse.external_branches:
        _unique([c.category_id for c in b.category_checks], "Branch labels")
        if any(c.applicability == "UNKNOWN" for c in b.category_checks):
            raise AuditError("Omit unselected UNKNOWN branch leaves")
    facts = {f.fact_id: f for f in sparse.condition_facts}
    _unique([f.fact_id for f in sparse.condition_facts], "Condition fact IDs")
    _unique([s.scenario_id for s in sparse.scenarios], "Scenario IDs")
    scenarios = {s.scenario_id: s for s in sparse.scenarios}
    for scenario in scenarios.values():
        if not _unique(scenario.condition_fact_ids, "Scenario facts") <= set(facts):
            raise AuditError("Scenario refers to unknown local facts")
    known = {d["detail_id"] for k in ("declared_details", "coverage_details")
             for d in (payload.get("baseline") or {}).get(k, [])}
    detail_ids = {d.detail_id for d in sparse.details} | known
    linked = {}; linked_facts = {}; used_scenarios = set()
    for link in sparse.label_links:
        key = (link.scheme, link.trigger_id)
        row = selected.get(link.scheme, {}).get(link.trigger_id)
        if not row or row.applicability not in POSITIVE:
            raise AuditError("Label links require a selected positive description label")
        if link.definition_version != frame_version(payload, link.scheme):
            raise AuditError("Label link definition version differs from its frozen rule frame")
        if not _unique(link.detail_ids, "Linked details") <= detail_ids:
            raise AuditError("Label link refers to unknown mechanism details")
        fids = _unique(link.condition_fact_ids, "Label link facts")
        if not fids <= set(row.condition_fact_ids):
            raise AuditError("Label link facts must belong to that rule")
        if row.applicability == "APPLICABLE" and fids != set(row.condition_fact_ids):
            raise AuditError("A fully applicable label cannot split required facts between scenarios")
        for sid in _unique(link.scenario_ids, "Linked scenarios"):
            if sid not in scenarios or not fids <= set(scenarios[sid].condition_fact_ids):
                raise AuditError("Label facts must occur together in every linked local scenario")
            used_scenarios.add(sid)
        if link.construction_ids:
            if link.scheme != "V4":
                raise AuditError("V4 construction scenarios are not API42 or Branch labels")
            checks = {c.construction_id: c for c in row.construction_checks}
            for cid in _unique(link.construction_ids, "Construction links"):
                if cid not in checks or checks[cid].applicability not in POSITIVE or not set(checks[cid].condition_fact_ids) <= fids:
                    raise AuditError("Construction links require their own positive, cited checks in that scenario")
        linked.setdefault(key, set()).update(link.detail_ids)
        linked_facts.setdefault(key, set()).update(fids)
    positive = {(scheme, key) for scheme, values in selected.items() for key, row in values.items()
                if row.applicability in POSITIVE}
    if set(linked) != positive:
        raise AuditError("Every positive sparse label requires explicit scenario/mechanism links")
    for scheme, key in positive:
        if linked_facts[(scheme, key)] != set(selected[scheme][key].condition_fact_ids):
            raise AuditError("Positive label facts cannot be silently omitted from scenario links")
    methods = {m["method_id"] for m in (payload.get("v4_taxonomy") or {}).get("methods", [])}
    for method in sparse.execution_method_links:
        fids = _unique(method.condition_fact_ids, "Execution method facts")
        if method.method_id not in methods or not fids <= set(facts):
            raise AuditError("Execution methods require frozen E1-E5 definitions and local facts")
        for sid in _unique(method.scenario_ids, "Execution method scenarios"):
            if sid not in scenarios or not fids <= set(scenarios[sid].condition_fact_ids):
                raise AuditError("Execution method facts must belong to its local scenario")
            used_scenarios.add(sid)
    if used_scenarios != set(scenarios):
        raise AuditError("Unlinked scenarios are not classification observations")
    input_labels = {k for k in positive if k[0] != "BRANCH"}
    expected = "CLASSIFIED" if input_labels else "BRANCH_ONLY" if positive else "EXECUTION_ONLY" if sparse.execution_method_links else "INSUFFICIENT_INFORMATION"
    if sparse.classification_summary.status == "NOT_APPLICABLE":
        exclusion = sparse.classification_summary.exclusion_fact_ids
        roles = {"INTERNAL_COMPUTATION", "SYNC_RACE", "STREAM_ASYNC", "DEVICE_SCHEDULING", "PLATFORM", "COMPILER_OPTION", "BUILD_VARIANT"}
        if stage != "API42" or positive or not exclusion or not set(exclusion) <= set(facts) or not any(facts[k].role in roles for k in exclusion):
            raise AuditError("Whole API-axis non-applicability needs positive non-API dependency facts; missing input information is UNKNOWN")
        expected = "NOT_APPLICABLE"
    if sparse.classification_summary.status != expected:
        raise AuditError("Sparse summary must agree with the actual linked labels")
    if expected == "INSUFFICIENT_INFORMATION" and not sparse.classification_summary.unknowns:
        raise AuditError("Insufficient information must state the specific missing facts")

    # Reuse the proven gates; unknown adapter rows never leave this function.
    legacy = {k: v for k, v in raw.items() if k in TriggerAssessment.model_fields}
    for scheme, field in ((axis, "rows"), ("V4", "v4_rows")):
        for row in legacy[field]:
            wanted = sorted(linked.get((scheme, row["trigger_id"]), set()))
            if row["detail_ids"] and set(row["detail_ids"]) != set(wanted):
                raise AuditError("Row detail IDs conflict with explicit label links")
            row["detail_ids"] = wanted
    for detail in legacy["details"]:
        wanted = sorted(key for (scheme, key), ids in linked.items()
                        if scheme == axis and detail["detail_id"] in ids)
        if detail["trigger_ids"] and set(detail["trigger_ids"]) != set(wanted):
            raise AuditError("Legacy detail trigger IDs conflict with typed revised42 links")
        detail["trigger_ids"] = wanted
    families = {f["family_id"]: f for f in payload["taxonomy"].get("families", [])}
    actual42 = {r["trigger_id"]: r for r in legacy["rows"]}
    expected42 = {i["id"] for i in payload["taxonomy"]["items"]}
    if not set(actual42) <= expected42:
        raise AuditError("Unknown revised42 rule")
    legacy["rows"] = [actual42.get(i["id"]) or _unknown(i, families.get(i.get("family_id"), {}))
                       for i in payload["taxonomy"]["items"]]
    v4 = payload.get("v4_taxonomy")
    if v4:
        actual4 = {r["trigger_id"]: r for r in legacy["v4_rows"]}
        if not set(actual4) <= {i["id"] for i in v4["items"]}:
            raise AuditError("Unknown V4 rule")
        constructions = {c["id"]: c for c in v4["constructions"]}
        vrows = []
        for item in v4["items"]:
            row = actual4.get(item["id"]) or {**_unknown(item), "coverage": {
                "construction": "UNKNOWN", "construction_reason": "Unselected",
                "path": "UNKNOWN", "path_reason": "Unselected", "execution": "NOT_RUN"}, "construction_checks": []}
            checks = {c["construction_id"]: c for c in row["construction_checks"]}
            if len(checks) != len(row["construction_checks"]) or not set(checks) <= set(item["construction_ids"]):
                raise AuditError("Selected construction IDs must be unique mounts of the selected V4 rule")
            row["construction_checks"] = [checks.get(key) or {"construction_id": key, "applicability": "UNKNOWN",
                "definition_check": {"clause": constructions[key]["definition"], "result": "UNKNOWN"},
                "reason": "Unselected; not assessed"} for key in item["construction_ids"]]
            vrows.append(row)
        legacy["v4_rows"] = vrows
    actual_branches = {b["branch_id"]: b for b in legacy["external_branches"]}
    _unique([b["branch_id"] for b in legacy["external_branches"]], "Branches")
    branches = []
    for b in payload["taxonomy"].get("branches", []):
        row = actual_branches.get(b["branch_id"]) or {"branch_id": b["branch_id"], "relation": "UNKNOWN",
            "reason": "Unselected; not assessed", "category_ids": [], "category_checks": []}
        checks = {c["category_id"]: c for c in row["category_checks"]}
        leaves = b.get("categories", []) if b.get("status") == "DEFINED" else []
        if not set(checks) <= {c["id"] for c in leaves}:
            raise AuditError("Unknown branch category")
        row["category_checks"] = [checks.get(c["id"]) or {"category_id": c["id"], "applicability": "UNKNOWN",
            "reason": "Unselected; not assessed"} for c in leaves]
        branches.append(row)
    legacy["external_branches"] = branches
    context = {k: v for k, v in payload.items() if k != "classification_contract"}
    out = validate_assessment(context, legacy, request_hash)
    out["rows"] = [r for r in out["rows"] if r["trigger_id"] in selected[axis]]
    out["v4_rows"] = [r for r in out["v4_rows"] if r["trigger_id"] in selected["V4"]]
    for row in out["v4_rows"]:
        requested = next(r for r in sparse.v4_rows if r.trigger_id == row["trigger_id"])
        ids = {c.construction_id for c in requested.construction_checks}
        row["construction_checks"] = [c for c in row["construction_checks"] if c["construction_id"] in ids]
        for check in row["construction_checks"]:
            if stage == "V4" and check["applicability"] in POSITIVE and not check.get("construction_recipe", "").strip():
                raise AuditError("A2 positive construction needs a design recipe and explicit missing conditions")
            if check["applicability"] in POSITIVE and not any(l["scheme"] == "V4" and l["trigger_id"] == row["trigger_id"]
                    and check["construction_id"] in l["construction_ids"] for l in raw["label_links"]):
                raise AuditError("Every positive construction requires an explicit scenario link")
    out["external_branches"] = [b for b in out["external_branches"] if b["branch_id"] in actual_branches]
    for branch in out["external_branches"]:
        branch["category_checks"] = [c for c in branch["category_checks"] if c["category_id"] in selected["BRANCH"]]
    for detail in out["details"]:
        detail["condition_links"] = [l for l in raw["label_links"] if detail["detail_id"] in l["detail_ids"]]
    proposal = sparse.candidate_proposal
    if proposal and proposal.action != "INSUFFICIENT_EVIDENCE":
        modes = {m["item_id"] for m in payload.get("mechanism_catalog", [])}
        if payload["phase"] != "INCREMENTAL" or not proposal.closest_mode_ids or not set(proposal.closest_mode_ids) <= modes:
            raise AuditError("Incremental candidate proposals must compare named known closest modes")
        proposed = {d["detail_id"]: d for d in out["details"]}
        if not proposal.detail_ids or not set(proposal.detail_ids) <= set(proposed):
            raise AuditError("Candidate proposals require current quoted mechanism details")
        if any(not (proposed[k]["source_cells"] or proposed[k]["evidence"]) for k in proposal.detail_ids):
            raise AuditError("Candidate mechanisms must have original support")
        if not proposal.difference.strip() or out["fact_conflicts"]:
            raise AuditError("Resolve contradictions and explain candidate differences first")
        comparison = out.get("declared_comparison") or {}
        if proposal.action == "PROPOSE_NEW_MODE_CANDIDATE" and any(
                row["result"] == "COVERED" and row["mechanism_relation"] == "SAME" for row in comparison.get("rows", [])):
            raise AuditError("An already covered same mechanism cannot simultaneously be a new-mode candidate")
        if out["source_relation"] == "NOT_RELATED" and any(proposed[k]["evidence"] for k in proposal.detail_ids):
            raise AuditError("Unrelated material cannot propose the original fault's mechanism")
    out.update({k: raw[k] for k in ("classification_contract", "classification_summary", "scenarios",
                                  "scenario_relation", "label_links", "candidate_proposal", "execution_method_links")})
    out["input_condition_scheme"] = axis
    if axis == "ORIGINAL42" and "definition_versions" in out:
        out["definition_versions"].pop("revised42", None)
        out["definition_versions"]["original42"] = frame_version(payload, axis)
    out["classification_scope"] = {"kind": "SELECTED_RULES", "omitted_rules": "NOT_ASSESSED",
        "selected_rule_ids": {scheme: sorted(values) for scheme, values in selected.items()},
        "full_rule_catalogs_supplied": True}
    out["processing_status"] = "EXCEPTION" if out["fact_conflicts"] else "PENDING" if expected == "INSUFFICIENT_INFORMATION" else "AUTO_PROCESSED"
    out["condition_processing_status"] = expected
    if v4:
        out["v4_processing_status"] = ("NOT_ASSESSED" if not out["v4_rows"] else
            "ASSESSED_WITH_UNKNOWNS" if any(r["applicability"] == "PARTIAL" or any(
                c["result"] == "UNKNOWN" for c in r["predicate_checks"]) for r in out["v4_rows"])
            else "ASSESSED_SELECTED_RULES")
    out["label_links_scope"] = "ASSESSMENT_LOCAL"
    return out
