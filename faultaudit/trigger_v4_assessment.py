"""Shared V4 checks: semantic labels, capability and execution are separate."""
from __future__ import annotations

from .store import AuditError
from .trigger_v4 import INPUT_ROLES, V4_VERSION, canonical_conditions


def instructions() -> str:
    return """This request contains independently frozen ORIGINAL V4 and API42 frames.
For v4_rows use the exact original definition/Requires/Skip for all 31 condition classes
and every mounted construction (55 unique codes, 64 mounts). For rows use the exact
original API42 clauses and family requirements. No revised definitions or crosswalk
are supplied. Never transfer applicability, evidence or coverage between the frames.
Original prerequisites remain binding even when they describe executor or resource
limits; do not split, override or reinterpret them into a broader applicability rule.
Record gaps, conflicts and uncertain interpretation as PARTIAL/UNKNOWN with evidence.
E1-E5 are the original design protocols, not additional input classes or root causes.
Construction capability and planned paths are reported separately without overriding
any original prerequisite. This phase has no device adapter: execution stays NOT_RUN.
A formula, supported capability declaration or design card is not proof of reproduction.
Every label and predicate check must cite local condition facts and exact permitted
source cells or immutable quotations. An unrelated search candidate cannot classify the
original record. No invented device result, human ACCEPT or formal adoption is allowed.
All 195 reference guides are retained separately for design selection; they are not
claimed as observed failures or as necessary classification predicates.
"""


def _known(value):
    return bool(value.strip()) and value.strip().casefold() not in {"unknown", "未知", "未提供", "待确认", "none"}


def validate_derivation(fact, facts, *, complete=False, dispatch=False):
    d = fact.derivation
    if d is None:
        if complete:
            raise AuditError("Full derived-condition applicability needs a cited derivation")
        return
    if len(set(d.driving_input_fact_ids)) != len(d.driving_input_fact_ids):
        raise AuditError("Derivation input fact IDs must be unique")
    for key in d.driving_input_fact_ids:
        if key == fact.fact_id or key not in facts or facts[key].role not in INPUT_ROLES:
            raise AuditError("Derived values must be driven by known local legal input facts, not internal aliases")
    if not set(d.path_fact_ids) <= set(facts) or fact.fact_id in d.path_fact_ids:
        raise AuditError("Derivation path evidence must identify distinct local facts")
    if complete and (not d.driving_input_fact_ids or not _known(d.expression)):
        raise AuditError("A full derived condition needs legal driver facts and its formula")
    if complete and dispatch and (not _known(d.dispatch_predicate) or not d.path_fact_ids):
        raise AuditError("Input-driven dispatch needs its whole predicate and cited path evidence")
    if complete and not dispatch and (not d.arithmetic_types or not all(_known(v) for v in d.arithmetic_types)
            or not all(_known(v) for v in (d.promotion, d.boundary, d.unit, d.capacity))):
        raise AuditError("Address analysis needs arithmetic widths, promotion position, boundary/unit and capacity")


def validate_v4(payload, result, grounded):
    taxonomy = payload.get("v4_taxonomy")
    if not taxonomy:
        if result.v4_rows:
            raise AuditError("V4 results need an explicitly frozen V4 definition set")
        return
    if taxonomy.get("definition_version") != V4_VERSION:
        raise AuditError("V4 definition version does not match the original-source profile")
    definitions = {v["id"]: v for v in taxonomy["items"]}
    if len(definitions) != 31 or len(result.v4_rows) != 31 or {r.trigger_id for r in result.v4_rows} != set(definitions):
        raise AuditError("V4 requires every one of its 31 category IDs exactly once")
    constructions = {c["id"]: c for c in taxonomy["constructions"]}
    if len(constructions) != 55 or sum(len(v["construction_ids"]) for v in definitions.values()) != 64:
        raise AuditError("V4 must retain all 55 definitions and 64 category mounts")
    facts = {f.fact_id: f for f in result.condition_facts}
    issue = payload.get("source_issue") or {}
    linked = issue.get("reference_relation") in {"SOURCE_CELL_LINKED", "LEGACY_TABLE_LINKED", "USER_CONFIRMED"}

    def support(value, *, decided=False):
        ids = value.condition_fact_ids
        if len(ids) != len(set(ids)) or not set(ids) <= set(facts) or decided and not ids:
            raise AuditError("V4 decided checks need unique local condition fact IDs")
        selected = [facts[key] for key in ids]
        if decided and any(f.subject == "CURRENT_ISSUE" and not (result.source_relation == "MATCH"
                or linked and result.source_relation != "NOT_RELATED") for f in selected):
            raise AuditError("An unbound search issue cannot supply the original record's V4 labels")
        grounded(value, "V4 condition", needed=False)
        for ref in value.evidence:
            if not any(ref.segment_id == r.segment_id and ref.quote in r.quote for f in selected for r in f.evidence):
                raise AuditError("V4 evidence is outside its selected local condition facts")
        for cell in value.source_cells:
            if not any(cell.field == r.field and cell.cell == r.cell and cell.quote in r.quote for f in selected for r in f.source_cells):
                raise AuditError("V4 cell quote is outside its selected local condition facts")
        return selected

    for fact in facts.values():
        validate_derivation(fact, facts)
    for row in result.v4_rows:
        item = definitions[row.trigger_id]
        wanted = canonical_conditions(item)
        checks = [(c.clause_role, c.clause) for c in row.predicate_checks]
        if len(checks) != len(set(checks)) or set(checks) != wanted:
            raise AuditError("V4 must check every whole semantic definition/Requires/Skip exactly once")
        selected = support(row, decided=row.applicability != "UNKNOWN")
        for check in row.predicate_checks:
            check_facts = support(check, decided=check.result != "UNKNOWN")
        negative = any(c.result == ("NOT_MET" if c.clause_role == "INCLUSION" else "MET") for c in row.predicate_checks)
        complete = all(c.result == ("MET" if c.clause_role == "INCLUSION" else "NOT_MET") for c in row.predicate_checks)
        if row.applicability == "APPLICABLE" and not complete:
            raise AuditError("V4 full applicability needs all semantic prerequisites, independently of capability")
        if row.applicability in {"APPLICABLE", "PARTIAL"} and negative:
            raise AuditError("A positive semantic exclusion cannot be mapped into V4 applicability")
        if row.applicability == "NOT_APPLICABLE" and not negative:
            raise AuditError("V4 non-applicability needs a positive semantic exclusion, not an executor limitation")
        if row.applicability == "NOT_APPLICABLE" and row.relation in {"MATCH", "PARTIAL"}:
            raise AuditError("A semantically excluded V4 condition cannot be evidence-matched")
        if row.relation == "MATCH" and (row.applicability != "APPLICABLE" or not complete or not row.evidence
                or row.evidence_basis not in {"SOURCE_REPORTED", "CODE_INFERENCE"}
                or result.source_relation != "MATCH" or any(not c.evidence for c in row.predicate_checks)):
            raise AuditError("V4 strong MATCH keeps the original full, grounded evidence gate")
        if row.relation == "NOT_MATCHED" and not negative:
            raise AuditError("V4 negative evidence relation needs a positive semantic exclusion")
        if row.relation == "PARTIAL" and not (row.evidence or row.source_cells):
            raise AuditError("V4 PARTIAL evidence needs observed facts")
        if row.evidence_basis == "SOURCE_DEFINITION" and not row.source_cells:
            raise AuditError("V4 SOURCE_DEFINITION needs exact source cells")
        if row.evidence_basis in {"SOURCE_REPORTED", "CODE_INFERENCE"} and not row.evidence:
            raise AuditError("V4 webpage basis needs scoped evidence")
        if result.source_relation == "NOT_RELATED" and row.relation in {"MATCH", "PARTIAL"} and row.evidence:
            raise AuditError("Unrelated issue evidence cannot confirm a V4 condition of the original")
        if row.applicability == "PARTIAL" and not row.unknowns:
            raise AuditError("Partial V4 applicability must state its missing semantic conditions")
        if payload.get("assessment_basis") == "SOURCE_DEFINITIONS" and row.relation not in {"UNKNOWN", "PARTIAL"}:
            raise AuditError("Definition-only V4 classification never establishes strong or negative webpage matching")
        capability = ((payload.get("execution_capabilities") or {}).get("classes") or {}).get(row.trigger_id, {})
        if row.coverage.construction != "UNKNOWN" and row.coverage.construction != capability.get("construction"):
            raise AuditError("Construction support/blocking needs the explicit capability profile; it is not semantic applicability")
        mounts = [c.construction_id for c in row.construction_checks]
        if len(mounts) != len(set(mounts)) or set(mounts) != set(item["construction_ids"]):
            raise AuditError("V4 must independently assess every mounted construction code")
        for check in row.construction_checks:
            selected_child = support(check, decided=check.applicability != "UNKNOWN")
            definition = constructions[check.construction_id]["definition"]
            predicate = check.definition_check
            if predicate.clause_role != "INCLUSION" or predicate.clause != definition:
                raise AuditError("Construction checks must retain their whole frozen definition")
            support(predicate, decided=predicate.result != "UNKNOWN")
            if check.applicability == "APPLICABLE" and (predicate.result != "MET" or row.applicability != "APPLICABLE"):
                raise AuditError("A fully applicable construction needs its own definition and the parent prerequisites")
            if check.applicability == "NOT_APPLICABLE" and predicate.result != "NOT_MET":
                raise AuditError("Construction exclusion needs its own positive counterevidence")
            if check.applicability in {"APPLICABLE", "PARTIAL"} and predicate.result == "NOT_MET":
                raise AuditError("Construction labels cannot contradict their original definition")


def validate_target_scope(payload, result):
    if payload.get("taxonomy", {}).get("branch_comparison_scope") != "TARGET_CALL":
        return
    facts = {f.fact_id: f for f in result.condition_facts}
    for branch in result.external_branches:
        if branch.branch_id != "3":
            continue
        for category in branch.category_checks:
            if category.applicability != "APPLICABLE":
                continue
            target = category.comparison_target_call_id
            selected = [facts[key] for key in category.condition_fact_ids]
            if not target or any(not any(f.role == role and f.target_call_id == target for f in selected)
                    for role in ("SAME_ARGUMENTS", "SAME_BINARY")):
                raise AuditError("Branch 3 full applicability must bind same inputs/binary to the compared target call")
