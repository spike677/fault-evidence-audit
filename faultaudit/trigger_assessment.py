"""Evidence-grounded trigger classification, separate from incident identity.

The 42 input-trigger predicates and the existing mechanism catalog are different
axes. These responses describe historical evidence; they never execute tests,
adopt a library change, or create a human ACCEPT.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, ValidationError

from .contracts import CatalogDraftProducer, Contract, EvidenceRef, SelfCheck
from .store import AuditError


Basis = Literal["SOURCE_DEFINITION", "SOURCE_REPORTED", "CODE_INFERENCE", "UNKNOWN"]
CoverageKind = Literal["HISTORICAL_EVIDENCE", "SOURCE_DEFINITIONS"]


class SourceCell(Contract):
    field: str = Field(min_length=1)
    cell: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class Grounded(Contract):
    evidence: list[EvidenceRef] = Field(default_factory=list)
    source_cells: list[SourceCell] = Field(default_factory=list)


class PredicateCheck(Grounded):
    clause: str = Field(min_length=1)
    clause_role: Literal["INCLUSION", "EXCLUSION"] = "INCLUSION"
    result: Literal["MET", "NOT_MET", "UNKNOWN"]


class TriggerRow(Grounded):
    trigger_id: str = Field(min_length=1)
    applicability: Literal["APPLICABLE", "NOT_APPLICABLE", "UNKNOWN"]
    relation: Literal["MATCH", "PARTIAL", "NOT_MATCHED", "UNKNOWN"]
    evidence_basis: Basis
    predicate_checks: list[PredicateCheck] = Field(default_factory=list)
    reason: str = Field(min_length=1)
    detail_ids: list[str] = Field(default_factory=list)


class Detail(Grounded):
    detail_id: str = Field(min_length=1)
    mode_id: str | None = None
    name: str = Field(min_length=1)
    mechanism: str = Field(min_length=1)
    operator: str = ""
    conditions: list[str] = Field(default_factory=list)
    trigger_ids: list[str] = Field(default_factory=list)
    evidence_basis: Basis
    unknowns: list[str] = Field(default_factory=list)
    coverage_kind: CoverageKind = "HISTORICAL_EVIDENCE"
    execution_verified: Literal[False] = False


class OutsideBranch(Grounded):
    branch_id: Literal["2", "3"]
    relation: Literal["APPLICABLE", "NOT_APPLICABLE", "UNKNOWN"]
    category_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class SourceAlignment(Grounded):
    dimension: Literal["mechanism", "trigger", "operator", "symptom", "context"]
    relation: Literal["MATCH", "DIFFERENT", "UNKNOWN"]
    reason: str = Field(min_length=1)


class FactConflict(Grounded):
    reason: str = Field(min_length=1)


class Decision(Contract):
    action: Literal["INIT_ONLY", "CLASSIFY_EXISTING", "EXTEND_DETAIL", "PROPOSE_NEW_MODE", "UNDETERMINED"]
    target_mode_ids: list[str] = Field(default_factory=list)
    target_detail_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class DeclaredComparisonRow(Grounded):
    mode_id: str = Field(min_length=1)
    result: Literal["COVERED", "PARTIALLY_COVERED", "NOT_COVERED", "UNKNOWN"]
    mechanism_relation: Literal["SAME", "PARTIAL", "DIFFERENT", "UNKNOWN"]
    baseline_detail_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class DeclaredDecision(Contract):
    action: Literal["CLASSIFY_DECLARED", "EXTEND_DECLARED", "PROPOSE_DECLARED_MODE", "UNDETERMINED"]
    target_mode_ids: list[str] = Field(default_factory=list)
    target_detail_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class DeclaredComparison(Contract):
    basis: Literal["SOURCE_DEFINITIONS"] = "SOURCE_DEFINITIONS"
    scope_relation: Literal["IN_SCOPE", "OUT_OF_SCOPE", "UNKNOWN"] = "UNKNOWN"
    scope_reason: str = Field(min_length=1)
    rows: list[DeclaredComparisonRow]
    decision: DeclaredDecision
    adoption_status: Literal["SUGGESTION_ONLY"] = "SUGGESTION_ONLY"
    case_confirmation: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"


class TriggerAssessment(Contract):
    schema_version: Literal["1.0"] = "1.0"
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    executor: Literal["opencode", "codex"]
    producer: CatalogDraftProducer
    case_id: str = Field(min_length=1)
    source_relation: Literal["MATCH", "PARTIAL", "UNKNOWN", "NOT_RELATED"] = "UNKNOWN"
    source_alignment: list[SourceAlignment] = Field(default_factory=list)
    rows: list[TriggerRow]
    details: list[Detail] = Field(default_factory=list)
    external_branches: list[OutsideBranch]
    decision: Decision
    declared_comparison: DeclaredComparison | None = None
    fact_conflicts: list[FactConflict] = Field(default_factory=list)
    self_check: SelfCheck
    coverage_kind: CoverageKind = "HISTORICAL_EVIDENCE"
    execution_verified: Literal[False] = False


def response_schema() -> dict:
    return TriggerAssessment.model_json_schema()


def instructions() -> str:
    return """Classify exactly the 42 frozen INPUT trigger predicates; keep Branch 2/3 outside their count.
Return one TriggerAssessment JSON bound to the OUTER request_hash and supplied case_id.
Use every unique taxonomy item id once. Read each item, its family Requires/Skip and global
applicability rules. For each row list the complete predicate conditions in predicate_checks;
check all roles, values, units, controls and constraints. Similar words or one equal constant
do not establish the whole predicate. Missing information stays UNKNOWN, never NOT_MET or
NOT_APPLICABLE. A negative decision needs a positively evidenced NOT_MET condition.
Each predicate_checks.clause must quote a whole canonical item definition or whole local/family
Requires/Skip clause, not an arbitrary substring. Use clause_role INCLUSION for the definition
and Requires, EXCLUSION for Skip if. MATCH must check the definition and every local/family
Requires as MET, and every Skip if as NOT_MET; UNKNOWN essential checks prevent MATCH.
A cited INCLUSION NOT_MET or EXCLUSION MET can justify exclusion. Satisfying Skip if never
supports inclusion. An OR inside one canonical clause remains a semantic whole for the Agent.
The original mechanism catalog is a separate axis. A MODE_ENTRY is not an incident: establish
source_relation by comparing its source cells to this source_issue's actual mechanism/trigger,
not by inventing SAME_EVENT. source_relation MATCH needs a grounded mechanism MATCH with
both exact source cells and webpage quotes. Generic operator or trigger-category matches are
insufficient. NOT_RELATED needs positive mechanism DIFFERENT evidence, not absent fields.
Do not retain DIFFERENT alignments under source_relation MATCH. An unresolved positive
fact difference under PARTIAL/UNKNOWN belongs in grounded fact_conflicts, not a silent
normal result. An unrelated search candidate may be NOT_RELATED without manufacturing a
conflict in the original mode. Technical differences never alone negate the original fault.
Quotes must be exact within the supplied issue's facts, provided original segments and scope;
source_cells must quote source_case.raw at its exact cell_locations. A summary is an index,
not extra evidence. Do not borrow another issue, stale response or historical root attribution.
Strong trigger MATCH needs APPLICABLE, all required predicate_checks MET, actual web evidence,
and source_relation MATCH. SOURCE_DEFINITION alone is at most PARTIAL. Distinguish source
statements from CODE_INFERENCE and preserve opposing facts. Do not infer a kernel path from
input constants. This is HISTORICAL_EVIDENCE, execution_verified=false: no local reproduction,
injection, N allocation, test coverage, formal library adoption or human ACCEPT is authorized.
Undefined outside branches must be UNKNOWN with empty category_ids; never invent their leaves.
In INIT use INIT_ONLY and retain original mode IDs. In INCREMENTAL use the supplied initialized
baseline: CLASSIFY_EXISTING needs an actual current COVERED mode and a known baseline detail;
EXTEND_DETAIL needs a COVERED/PARTIALLY_COVERED parent plus a new web-grounded mechanism detail.
Every positive incremental action also needs source_relation MATCH without fact_conflicts;
PARTIAL/UNKNOWN uses UNDETERMINED. NOT_RELATED material cannot supply any web-derived mechanism
detail, including a proposed new mode without an existing mode_id.
PROPOSE_NEW_MODE requires every original mode positively NOT_COVERED and a current confirmed
same-event DIRECT/root-SUPPORTED judgment. Failure to match the 42 triggers does not prove a
new fault mechanism. Insufficient evidence uses UNDETERMINED. Suggestions never edit the library.
Give each proposed detail a unique detail_id. Row detail_ids link only this response's details
or existing baseline details; target_detail_ids identify known details for CLASSIFY_EXISTING,
or proposed new details for EXTEND_DETAIL/PROPOSE_NEW_MODE. Separate ordinary verification,
revision, version and collection unknowns from grounded fact_conflicts. Unknowns do not require
human ACCEPT. Perform the five self-checks once, retaining exact quotes and unresolved facts.
Read the complete request. If it exceeds execution capacity, report transport blocking instead
of returning a successful truncated classification.
When assessment_basis is SOURCE_DEFINITIONS and phase INIT, read only the frozen original
definition and supplied chat/source cells. No search, webpage capture, SAME_EVENT, or incident
confirmation is part of this initialization. Keep source_relation UNKNOWN, all 42 trigger rows
PARTIAL or UNKNOWN, and retain at least one concrete SOURCE_DEFINITION detail for this mode.
Do not omit the definition's mechanism because it lacks webpage verification. Mark coverage_kind
SOURCE_DEFINITIONS; execution_verified remains false. Exact source_cells also anchor chat fields.
An incremental baseline may separately contain declared_details. If so, declared_comparison is
required: semantically compare the new case/current issue against EVERY original mode exactly once,
reading each complete frozen definition and declared detail. The mechanism_catalog comparison view
includes every mode's full description/operator/mechanism/trigger plus category/boundary/unknown/
representative-example fields and provenance. Repeated original chapters and quote bundles remain
frozen in Store; this task is not a full source-document audit. This is a second, declared-definition
axis, independent of the 42 trigger rows and the evidence-gated decision above. COVERED requires
mechanism_relation SAME, PARTIALLY_COVERED requires SAME/PARTIAL, and NOT_COVERED requires a positive
DIFFERENT mechanism; absent information is UNKNOWN. For any non-UNKNOWN comparison cite the relevant
baseline_detail_ids and exact new-case source_cells or current issue evidence. Generic operator,
symptom or trigger overlap alone never proves mechanism coverage. All current issue evidence remains
scoped and NOT_RELATED material cannot support the comparison. CLASSIFY_DECLARED uses known declared
details under COVERED modes. EXTEND_DECLARED uses new grounded details under COVERED/PARTIALLY_COVERED
modes. PROPOSE_DECLARED_MODE requires every original definition positively NOT_COVERED and a concrete
new grounded detail. Such a proposal is only relative to the declared catalog_scope: an inference
library excludes training mechanisms by scope, so a training-only case outside that library uses
UNDETERMINED with the scope gap in its reason rather than proposing a new inference mode.
Declared suggestions have adoption_status SUGGESTION_ONLY and case_confirmation NOT_ESTABLISHED;
they never authorize formal ADD, source MATCH, SAME_EVENT or bypass the original decision's gates.
If there are no declared_details, leave declared_comparison null.
"""


def _unique(values: list[str], label: str) -> set[str]:
    if len(values) != len(set(values)):
        raise AuditError(label + " must be unique")
    return set(values)


def validate_assessment(payload: dict, response: dict, request_hash: str) -> dict:
    """Validate grounded structure and return a normalized, non-adopted result.

    Semantic entailment remains the Agent's responsibility. Mechanical gates
    check provenance, scope, completeness and the explicit decision prerequisites.
    """
    try:
        result = TriggerAssessment.model_validate(response)
    except ValidationError as exc:
        raise AuditError("Invalid trigger assessment: " + str(exc)) from exc
    subject = payload["subject"]
    case = subject["source_case"]
    if result.request_hash != request_hash or result.case_id != subject["case_id"]:
        raise AuditError("Trigger assessment identity does not match the current request/subject")
    phase = payload.get("phase")
    if phase not in {"INIT", "INCREMENTAL"}:
        raise AuditError("Trigger classification phase must be INIT or INCREMENTAL")
    assessment_basis = payload.get("assessment_basis", "HISTORICAL_EVIDENCE")
    if assessment_basis not in {"HISTORICAL_EVIDENCE", "SOURCE_DEFINITIONS"}:
        raise AuditError("Unknown trigger assessment basis")
    definition_init = phase == "INIT" and assessment_basis == "SOURCE_DEFINITIONS"
    if definition_init and (payload.get("source_issue") or result.source_relation != "UNKNOWN"
            or any(r.relation not in {"UNKNOWN", "PARTIAL"} for r in result.rows)):
        raise AuditError("Source-definition Init has no webpage alignment and only PARTIAL/UNKNOWN trigger rows")
    items = payload["taxonomy"]["items"]
    expected = [item["id"] for item in items]
    if len(expected) != 42 or len(set(expected)) != 42:
        raise AuditError("Trigger taxonomy must have 42 unique item IDs")
    ids = [row.trigger_id for row in result.rows]
    if len(ids) != 42 or _unique(ids, "Trigger row IDs") != set(expected):
        raise AuditError("Assessment must include all 42 trigger IDs exactly once")
    issue = payload.get("source_issue") or {}
    snapshot = issue.get("snapshot") or {}
    segments = {s["segment_id"]: s["text"] for s in snapshot.get("segments", [])}
    scope = issue.get("input_scope") or snapshot.get("input_scope") or {}
    if "provided_segment_ids" in scope:
        selected = set(scope["provided_segment_ids"])
        segments = {key: text for key, text in segments.items() if key in selected}
    allowed = [ref for fact in issue.get("facts", []) for ref in fact.get("evidence", [])]
    raw, cells = case.get("raw", {}), case.get("cell_locations", {})

    def grounded(value: Grounded, label: str, *, needed: bool = False) -> None:
        if needed and not (value.evidence or value.source_cells):
            raise AuditError(label + " requires positive cited evidence or source cells")
        for ref in value.evidence:
            if (snapshot.get("status") not in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"}
                    or ref.segment_id not in segments or ref.quote not in segments[ref.segment_id]
                    or not any(ref.segment_id == outer.get("segment_id")
                               and ref.quote in outer.get("quote", "") for outer in allowed)):
                raise AuditError(label + " quote is outside the current issue facts or provided snapshot scope")
        for cell in value.source_cells:
            if (cell.field not in raw or cells.get(cell.field) != cell.cell
                    or not cell.quote.strip() or cell.quote not in raw[cell.field]):
                raise AuditError(label + " source cell/quote does not match the immutable source")

    for alignment in result.source_alignment:
        grounded(alignment, "Source alignment", needed=alignment.relation != "UNKNOWN")
        if alignment.relation in {"MATCH", "DIFFERENT"} and not (alignment.evidence and alignment.source_cells):
            raise AuditError("Source alignment requires both source cells and current webpage evidence")
    for conflict in result.fact_conflicts:
        grounded(conflict, "Fact conflict", needed=True)
        if not conflict.evidence:
            raise AuditError("Fact conflict requires current webpage evidence")
    mechanisms = [a for a in result.source_alignment if a.dimension == "mechanism"]
    differences = [a for a in result.source_alignment if a.relation == "DIFFERENT"]
    if result.source_relation == "MATCH" and (not issue or result.fact_conflicts
            or differences or not any(a.relation == "MATCH" for a in mechanisms)):
        raise AuditError("Source MATCH requires a grounded mechanism alignment without unresolved fact conflicts")
    if result.source_relation == "NOT_RELATED" and not any(a.relation == "DIFFERENT" for a in mechanisms):
        raise AuditError("NOT_RELATED requires positive grounded mechanism difference, not missing information")
    # An unbound candidate's differences need not contradict the original facts.
    if differences and result.source_relation not in {"UNKNOWN", "NOT_RELATED"} and not result.fact_conflicts:
        raise AuditError("Unresolved DIFFERENT source alignments require grounded fact_conflicts")
    rows = {row.trigger_id: row for row in result.rows}
    definitions = {item["id"]: item for item in items}
    families = {family["family_id"]: family for family in payload["taxonomy"].get("families", [])}
    for row in result.rows:
        grounded(row, row.trigger_id)
        _unique(row.detail_ids, "Row detail IDs")
        item = definitions[row.trigger_id]
        family = families.get(item.get("family_id"), {})
        inclusions = {item["definition"].strip()}
        inclusions.update(text.strip() for entry in (item, family) for text in entry.get("requires", []))
        exclusions = {text.strip() for entry in (item, family) for text in entry.get("skip_if", [])}
        inclusions.discard("")
        exclusions.discard("")
        for check in row.predicate_checks:
            canonical = inclusions if check.clause_role == "INCLUSION" else exclusions
            if check.clause not in canonical:
                raise AuditError("Predicate clause must quote a whole canonical definition/Requires/Skip clause in its proper role")
            grounded(check, row.trigger_id + " predicate", needed=check.result != "UNKNOWN")
        if row.relation == "MATCH":
            met = {c.clause for c in row.predicate_checks if c.clause_role == "INCLUSION" and c.result == "MET"}
            ruled_out = {c.clause for c in row.predicate_checks if c.clause_role == "EXCLUSION" and c.result == "NOT_MET"}
            if (row.applicability != "APPLICABLE" or not row.predicate_checks
                    or not inclusions <= met or not exclusions <= ruled_out
                    or any(c.result != ("MET" if c.clause_role == "INCLUSION" else "NOT_MET") for c in row.predicate_checks)
                    or any(not c.evidence for c in row.predicate_checks)
                    or not row.evidence or row.evidence_basis in {"SOURCE_DEFINITION", "UNKNOWN"}
                    or result.source_relation != "MATCH"):
                raise AuditError("Trigger MATCH requires source MATCH, APPLICABLE, all predicates MET and grounded web evidence")
        if row.relation == "PARTIAL" and not (row.evidence or row.source_cells):
            raise AuditError("PARTIAL requires observed source/evidence facts")
        if row.applicability == "NOT_APPLICABLE" or row.relation == "NOT_MATCHED":
            if not any((c.clause_role == "INCLUSION" and c.result == "NOT_MET")
                    or (c.clause_role == "EXCLUSION" and c.result == "MET") for c in row.predicate_checks):
                raise AuditError("NOT_APPLICABLE/NOT_MATCHED requires a cited INCLUSION NOT_MET or EXCLUSION MET predicate")
        if row.applicability == "NOT_APPLICABLE" and row.relation in {"MATCH", "PARTIAL"}:
            raise AuditError("A non-applicable trigger cannot be positively matched")
        if row.evidence_basis in {"SOURCE_REPORTED", "CODE_INFERENCE"} and not row.evidence:
            raise AuditError("Web-derived trigger facts require current issue evidence")
        if row.evidence_basis == "SOURCE_DEFINITION" and not row.source_cells:
            raise AuditError("SOURCE_DEFINITION requires exact original source cells")
        if (result.source_relation == "NOT_RELATED" and row.relation in {"MATCH", "PARTIAL"}
                and row.evidence_basis in {"SOURCE_REPORTED", "CODE_INFERENCE"}):
            raise AuditError("Unrelated source material cannot positively classify the original subject")

    catalog_ids = {item["item_id"] for item in payload.get("mechanism_catalog", [])}
    baseline = payload.get("baseline") or {}
    known_details = {d["detail_id"]: d for d in baseline.get("coverage_details", [])}
    declared_details = {d["detail_id"]: d for d in baseline.get("declared_details", [])}
    linkable_details = {**known_details, **declared_details}
    detail_ids = _unique([d.detail_id for d in result.details], "Proposed detail IDs")
    if detail_ids.intersection(linkable_details):
        raise AuditError("Existing detail IDs are referenced from the baseline, not rewritten as new details")
    for detail in result.details:
        grounded(detail, "Mechanism detail", needed=detail.evidence_basis != "UNKNOWN")
        if detail.mode_id is not None and detail.mode_id not in catalog_ids:
            raise AuditError("Detail mode ID is outside the frozen mechanism catalog")
        if phase == "INIT" and detail.mode_id != subject.get("mode_id"):
            raise AuditError("Init details must retain this original mode ID")
        if not set(detail.trigger_ids) <= set(rows) or len(set(detail.trigger_ids)) != len(detail.trigger_ids):
            raise AuditError("Detail trigger IDs must be unique known trigger categories")
        if detail.evidence_basis in {"SOURCE_REPORTED", "CODE_INFERENCE"} and not detail.evidence:
            raise AuditError("A web-derived mechanism detail requires current issue quotes")
        if detail.evidence_basis == "SOURCE_DEFINITION" and not detail.source_cells:
            raise AuditError("A source-defined detail requires original source cells")
        if (result.source_relation == "NOT_RELATED"
                and detail.evidence_basis in {"SOURCE_REPORTED", "CODE_INFERENCE"}):
            raise AuditError("Unrelated material cannot supply a mechanism detail for the subject")
        if definition_init and detail.evidence_basis != "SOURCE_DEFINITION":
            raise AuditError("Source-definition Init details require SOURCE_DEFINITION and exact source cells")
    if definition_init and not result.details:
        raise AuditError("Source-definition Init must retain at least one original mechanism detail")
    for row in result.rows:
        if not set(row.detail_ids) <= detail_ids | set(linkable_details):
            raise AuditError("Row refers to an unknown detail ID")
        for did in row.detail_ids:
            detail = next((d.model_dump() for d in result.details if d.detail_id == did), linkable_details.get(did))
            if row.trigger_id not in detail.get("trigger_ids", []):
                raise AuditError("Row/detail trigger links must agree")

    branch_defs = {b["branch_id"]: b for b in payload["taxonomy"].get("branches", [])}
    if _unique([b.branch_id for b in result.external_branches], "Outside branch IDs") != {"2", "3"}:
        raise AuditError("Outside branches 2 and 3 must be assessed separately from the 42 triggers")
    for branch in result.external_branches:
        grounded(branch, "Outside branch")
        definition = branch_defs.get(branch.branch_id, {})
        if definition.get("status") != "DEFINED":
            if branch.relation != "UNKNOWN" or branch.category_ids:
                raise AuditError("Undefined outside branches require UNKNOWN and no invented categories")
        else:
            leaves = {str(c["id"]) for c in definition.get("categories", [])}
            allowed_categories = leaves or {branch.branch_id}
            if not _unique(branch.category_ids, "Outside category IDs") <= allowed_categories:
                raise AuditError("Outside category IDs must come from their explicit definitions")
            if branch.relation != "UNKNOWN":
                grounded(branch, "Outside branch", needed=True)

    check = result.self_check
    if not all(getattr(check, name) for name in ("numeric_meaning_checked", "citations_checked",
            "counterevidence_checked", "issue_scope_checked", "event_vs_technical_checked")):
        raise AuditError("The agent must complete all five bounded self-checks")
    if (not check.passed or check.issues) and not result.fact_conflicts:
        raise AuditError("Ordinary unknowns belong in reasons, not ungrounded review conflicts")
    decision = result.decision
    modes = _unique(decision.target_mode_ids, "Target mode IDs")
    targets = _unique(decision.target_detail_ids, "Target detail IDs")
    if not targets <= detail_ids | set(known_details):
        raise AuditError("Decision refers to an unknown detail ID")
    if not modes <= catalog_ids:
        raise AuditError("Decision targets are outside the frozen mechanism catalog")
    if phase == "INIT":
        if decision.action != "INIT_ONLY":
            raise AuditError("Init classifies existing modes; it cannot propose an incremental library action")
        if modes and modes != {subject.get("mode_id")}:
            raise AuditError("Init must preserve this original mode identity")
    elif decision.action == "INIT_ONLY":
        raise AuditError("Incremental assessment cannot claim INIT_ONLY")
    elif decision.action != "UNDETERMINED":
        if result.source_relation != "MATCH" or result.fact_conflicts:
            raise AuditError("A positive incremental decision requires source MATCH without fact conflicts; otherwise use UNDETERMINED")
        if not baseline.get("baseline_id") or not catalog_ids <= set(baseline.get("mode_ids", [])):
            raise AuditError("Incremental decisions require the initialized baseline for the complete mechanism catalog")
        mappings = [m for m in payload.get("mappings", []) if not m.get("is_stale")
                    and m.get("required") is not False and m.get("review_status") != "REJECT"
                    and m.get("model_mode") != "mock" and (m.get("case_id") == result.case_id
                        or result.case_id in m.get("member_case_ids", []))]
        mapped = {}
        for mapping in mappings:
            for row in mapping.get("catalog_results", []):
                mapped.setdefault(row["item_id"], set()).add(row["result"])
        if decision.action == "CLASSIFY_EXISTING":
            if not modes or not targets or not targets <= set(known_details):
                raise AuditError("CLASSIFY_EXISTING requires known baseline details and parent modes")
            if any(mapped.get(mode) != {"COVERED"} for mode in modes):
                raise AuditError("CLASSIFY_EXISTING requires current COVERED parent mappings")
            if any(known_details[did].get("mode_id") not in modes for did in targets):
                raise AuditError("Existing detail targets must belong to the target modes")
        elif decision.action == "EXTEND_DETAIL":
            proposed = [d for d in result.details if d.detail_id in targets]
            if (not modes or not targets or not targets <= detail_ids or targets.intersection(known_details)
                    or len(proposed) != len(targets)):
                raise AuditError("EXTEND_DETAIL requires new proposed details under existing modes")
            if any(not mapped.get(mode) or not mapped[mode] <= {"COVERED", "PARTIALLY_COVERED"} for mode in modes):
                raise AuditError("EXTEND_DETAIL requires COVERED/PARTIALLY_COVERED parents")
            if any(d.mode_id not in modes or not d.evidence
                    or d.evidence_basis not in {"SOURCE_REPORTED", "CODE_INFERENCE"} for d in proposed):
                raise AuditError("EXTEND_DETAIL needs a new grounded mechanism detail for its parent")
        elif decision.action == "PROPOSE_NEW_MODE":
            if not catalog_ids or any(mapped.get(mode) != {"NOT_COVERED"} for mode in catalog_ids):
                raise AuditError("A new mode requires every original mechanism positively NOT_COVERED")
            confirming = [j for j in payload.get("judgments", []) if not j.get("is_stale")
                and j.get("required") is not False and j.get("review_status") != "REJECT"
                and j.get("model_mode") != "mock" and j.get("case_id") == result.case_id
                and j.get("case_attribution") == "CONFIRMED" and j.get("event_relation") == "SAME_EVENT"
                and j.get("support_level") == "DIRECT" and not j.get("conflicting_dimensions")
                and j.get("claim_support", {}).get("root_cause") == "SUPPORTED" and j.get("evidence")]
            if not confirming or result.fact_conflicts or modes:
                raise AuditError("A new mode requires a confirmed DIRECT root-supported judgment without conflicts")
            if not targets or not targets <= detail_ids or any(d.mode_id is not None or not d.evidence
                    or d.evidence_basis not in {"SOURCE_REPORTED", "CODE_INFERENCE"}
                    for d in result.details if d.detail_id in targets):
                raise AuditError("A new mode requires grounded proposed details, not an existing mode identity")
    comparison = result.declared_comparison
    if phase == "INCREMENTAL" and declared_details:
        if not comparison:
            raise AuditError("A declared-definition baseline requires a complete declared_comparison")
        if (_unique([r.mode_id for r in comparison.rows], "Declared comparison mode IDs") != catalog_ids
                or not catalog_ids <= set(baseline.get("mode_ids", []))):
            raise AuditError("Declared comparison must assess every frozen original mode exactly once")
        compared = {r.mode_id: r for r in comparison.rows}
        for row in comparison.rows:
            grounded(row, "Declared comparison", needed=row.result != "UNKNOWN")
            referenced = _unique(row.baseline_detail_ids, "Declared baseline detail IDs")
            if not referenced <= set(declared_details) or any(
                    declared_details[did].get("mode_id") != row.mode_id for did in referenced):
                raise AuditError("Declared comparison references unknown details or another parent mode")
            if row.result != "UNKNOWN" and not referenced:
                raise AuditError("A decided declared comparison needs the original mode's declared details")
            allowed_relation = {"COVERED": {"SAME"}, "PARTIALLY_COVERED": {"SAME", "PARTIAL"},
                                "NOT_COVERED": {"DIFFERENT"}, "UNKNOWN": {"UNKNOWN", "PARTIAL"}}
            if row.mechanism_relation not in allowed_relation[row.result]:
                raise AuditError("Declared coverage requires an explicit consistent mechanism relation")
            if row.evidence and result.source_relation == "NOT_RELATED":
                raise AuditError("Unrelated webpage material cannot support a declared comparison")
        proposed = comparison.decision
        if result.fact_conflicts and proposed.action != "UNDETERMINED":
            raise AuditError("Unresolved fact conflicts require an UNDETERMINED declared suggestion")
        parent_ids = _unique(proposed.target_mode_ids, "Declared target mode IDs")
        target_ids = _unique(proposed.target_detail_ids, "Declared target detail IDs")
        if not parent_ids <= catalog_ids or not target_ids <= detail_ids | set(declared_details):
            raise AuditError("Declared decision targets must use known original modes and declared/proposed details")
        if proposed.action == "CLASSIFY_DECLARED":
            if (not parent_ids or not target_ids or not target_ids <= set(declared_details)
                    or any(compared[mid].result != "COVERED" for mid in parent_ids)
                    or any(declared_details[did].get("mode_id") not in parent_ids for did in target_ids)):
                raise AuditError("CLASSIFY_DECLARED requires COVERED parents and their known declared details")
        elif proposed.action in {"EXTEND_DECLARED", "PROPOSE_DECLARED_MODE"}:
            new_details = [d for d in result.details if d.detail_id in target_ids]
            if not target_ids or not target_ids <= detail_ids or len(new_details) != len(target_ids):
                raise AuditError("A declared extension/proposal needs new proposed mechanism details")
            if any(d.evidence_basis == "UNKNOWN" or not (d.evidence or d.source_cells) for d in new_details):
                raise AuditError("Declared proposed details need exact source cells or current issue evidence")
            if proposed.action == "EXTEND_DECLARED":
                if (not parent_ids or any(compared[mid].result not in {"COVERED", "PARTIALLY_COVERED"}
                        for mid in parent_ids) or any(d.mode_id not in parent_ids for d in new_details)):
                    raise AuditError("EXTEND_DECLARED requires covered/partial parents and their new details")
            elif (comparison.scope_relation != "IN_SCOPE" or parent_ids
                    or any(row.result != "NOT_COVERED" for row in comparison.rows)
                    or any(d.mode_id is not None for d in new_details)):
                raise AuditError("PROPOSE_DECLARED_MODE requires an in-scope case and every original definition NOT_COVERED")
    elif comparison is not None:
        raise AuditError("Declared comparison requires an incremental baseline with frozen declared details")
    output = result.model_dump()
    output["coverage_kind"] = assessment_basis
    for value in output["details"]:
        value["coverage_kind"] = ("SOURCE_DEFINITIONS" if value["evidence_basis"] == "SOURCE_DEFINITION"
                                  else "HISTORICAL_EVIDENCE")
    output["declared_processing_status"] = ("AUTO_PROCESSED" if comparison
        and comparison.decision.action != "UNDETERMINED" and not result.fact_conflicts else "PENDING")
    output.update(processing_status="EXCEPTION" if result.fact_conflicts else "PENDING"
        if decision.action == "UNDETERMINED" or all(r.relation == "UNKNOWN" for r in result.rows) else "AUTO_PROCESSED",
        review_required=bool(result.fact_conflicts),
        review_reasons=[c.reason for c in result.fact_conflicts])
    return output
