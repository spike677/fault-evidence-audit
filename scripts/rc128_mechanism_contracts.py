"""Pure, assessment-local contracts for offline mechanism reports.

``validate_analysis(record, definitions, evidence_ids)`` returns located errors;
it never reads files, writes state, retrieves evidence, or executes a design.
Only selected definitions are needed. Each definition is a mapping with
``scheme, definition_version, id, definition, requires, skip_if`` and optional
``construction_ids, constructions, guides, allowed_fact_roles``. Definitions
may be a list or a mapping keyed by ``(scheme, id)``. V4 constructions retain
their native ``id, definition`` and guides their ``guide_id, category_id``.

The analysis shape is intentionally small: identity, source_claims, mechanism,
condition_facts, selected_labels, native scenarios/label_links/design_cards,
mode_comparisons and mode_decision. ``analysis_id`` is the one mechanism detail
ID and the native cards' assessment_id. Additional report prose is permitted.
These checks establish provenance and internal consistency, not entailment or
incident confirmation. A source declaration remains a source declaration.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from faultaudit.contracts import Contract
from faultaudit.trigger_assessment import ConditionFact, ConstructionCheck, PredicateCheck
from faultaudit.trigger_design import DesignCard, DesignVariable
from faultaudit.trigger_sparse import LabelLink, Scenario
from faultaudit.trigger_v4 import canonical_conditions


Basis = Literal["SOURCE_DECLARED", "CAPTURED_FACT", "CODE_INFERENCE", "HYPOTHESIS"]
Scheme = Literal["ORIGINAL42", "REVISED42", "V4"]
POSITIVE = {"APPLICABLE", "PARTIAL"}
INTERNAL_ROLES = {"DERIVED_CONTROL", "PATH_PREDICATE", "CAPACITY", "INTERNAL_COMPUTATION"}


class SourceClaim(Contract):
    claim_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    subproblem_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    basis: Basis
    evidence_ids: list[str] = Field(min_length=1)


class AnalysisFact(Contract):
    fact_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    role: str = Field(min_length=1)
    basis: Basis
    source_claim_ids: list[str] = Field(min_length=1)


class Mechanism(Contract):
    statement: str = Field(min_length=1)
    source_claim_ids: list[str] = Field(min_length=1)


class Feasibility(Contract):
    status: Literal["UNKNOWN", "DECLARED_SUPPORTED", "BLOCKED", "NOT_ASSESSED"]
    reason: str = Field(min_length=1)


class SelectedLabel(Contract):
    scheme: Scheme
    definition_version: str = Field(min_length=1)
    trigger_id: str = Field(min_length=1)
    semantic_applicability: Literal["APPLICABLE", "PARTIAL", "NOT_APPLICABLE", "UNKNOWN"]
    construction_feasibility: Feasibility
    condition_fact_ids: list[str] = Field(default_factory=list)
    predicate_checks: list[PredicateCheck]
    construction_checks: list[ConstructionCheck] = Field(default_factory=list)


class ModeComparison(Contract):
    mode_id: str = Field(min_length=1)
    relation: Literal["SAME", "PARTIAL", "DIFFERENT", "UNKNOWN"]
    reason: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class ModeDecision(Contract):
    action: Literal["PENDING", "EXISTING", "EXTEND", "NEW"]
    reason: str = Field(min_length=1)


class MechanismAnalysis(BaseModel):
    model_config = ConfigDict(extra="allow")
    analysis_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    subproblem_id: str = Field(min_length=1)
    source_claims: list[SourceClaim] = Field(min_length=1)
    mechanism: Mechanism
    condition_facts: list[AnalysisFact] = Field(default_factory=list)
    selected_labels: list[SelectedLabel] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    label_links: list[LabelLink] = Field(default_factory=list)
    design_cards: list[DesignCard] = Field(min_length=1)
    mode_comparisons: list[ModeComparison] = Field(default_factory=list)
    mode_decision: ModeDecision
    adoption_status: Literal["SUGGESTION_ONLY"] = "SUGGESTION_ONLY"
    formal_adoption: Literal[False] = False


def validate_analysis(record: Mapping, definitions: Iterable[Mapping] | Mapping,
                      evidence_ids: Iterable[str]) -> list[dict[str, str]]:
    """Return ``[{code, path, message}]``; an empty list means contract-valid.

    Evidence IDs are supplied by the caller's already captured source index.
    No full catalog matrix, R4 directory, store, or device is required.
    """
    errors: list[dict[str, str]] = []

    def error(code, path, message):
        errors.append(dict(code=code, path=path, message=message))

    try:
        analysis = MechanismAnalysis.model_validate(record)
    except ValidationError as exc:
        return [dict(code="SCHEMA", path=".".join(map(str, item["loc"])), message=item["msg"])
                for item in exc.errors(include_url=False)]

    # Native minimum lengths do not reject whitespace-only prose.
    def nonblank(value, path):
        if isinstance(value, str) and not value.strip():
            error("BLANK", path, "A nonblank value is required")
        elif isinstance(value, Mapping):
            for key, item in value.items():
                nonblank(item, f"{path}.{key}" if path else key)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                nonblank(item, f"{path}[{i}]")

    # Empty native optional strings are valid; check only explicitly required prose.
    for key in ("analysis_id", "task_id", "subproblem_id"):
        nonblank(getattr(analysis, key), key)
    for key in ("source_claims", "mechanism", "condition_facts", "mode_comparisons", "mode_decision"):
        nonblank(getattr(analysis, key).model_dump() if key in {"mechanism", "mode_decision"}
                 else [v.model_dump() for v in getattr(analysis, key)], key)

    known_evidence = set(evidence_ids)

    def refs(values, known, path, code="UNKNOWN_REFERENCE", required=False):
        if required and not values:
            error("MISSING_REFERENCE", path, "At least one local reference is required")
        if len(values) != len(set(values)):
            error("DUPLICATE_REFERENCE", path, "References must be unique")
        unknown = set(values) - set(known)
        if unknown:
            error(code, path, "Unknown or out-of-scope references: " + ", ".join(sorted(unknown)))

    def index(values, key, path):
        result = {}
        for i, item in enumerate(values):
            value = getattr(item, key)
            if value in result:
                error("DUPLICATE_ID", f"{path}[{i}].{key}", "IDs must be unique within one analysis")
            result[value] = item
        return result

    claims = index(analysis.source_claims, "claim_id", "source_claims")
    facts = index(analysis.condition_facts, "fact_id", "condition_facts")
    scenarios = index(analysis.scenarios, "scenario_id", "scenarios")
    index(analysis.design_cards, "card_id", "design_cards")
    index(analysis.mode_comparisons, "mode_id", "mode_comparisons")
    for i, claim in enumerate(analysis.source_claims):
        path = f"source_claims[{i}]"
        if (claim.task_id, claim.subproblem_id) != (analysis.task_id, analysis.subproblem_id):
            error("CLAIM_SCOPE", path, "A claim must bind this task and this one subproblem")
        refs(claim.evidence_ids, known_evidence, path + ".evidence_ids", required=True)
    refs(analysis.mechanism.source_claim_ids, claims, "mechanism.source_claim_ids", required=True)
    roles = set(get_args(ConditionFact.model_fields["role"].annotation))
    for i, fact in enumerate(analysis.condition_facts):
        path = f"condition_facts[{i}]"
        refs(fact.source_claim_ids, claims, path + ".source_claim_ids", required=True)
        bases = {claims[key].basis for key in fact.source_claim_ids if key in claims}
        if fact.role not in roles:
            error("FACT_ROLE", path + ".role", "Use a native ConditionFact semantic role")
        if fact.basis != "HYPOTHESIS" and bases and bases <= {"HYPOTHESIS"}:
            error("HYPOTHESIS_AS_FACT", path, "A hypothesis cannot become an observed or declared fact")
        if fact.basis in {"SOURCE_DECLARED", "CAPTURED_FACT"} and fact.basis not in bases:
            error("FACT_BASIS", path, "Preserve the supporting source claim's evidence level")

    # Only cited definitions are validated; omitted rules mean NOT_ASSESSED.
    definition_values = definitions.values() if isinstance(definitions, Mapping) else definitions
    rule_index = {}
    for i, definition in enumerate(definition_values):
        path = f"definitions[{i}]"
        if not isinstance(definition, Mapping) or not all(
                key in definition for key in ("scheme", "definition_version", "id", "definition", "requires", "skip_if")):
            error("DEFINITION_SHAPE", path, "Retain the version, full definition, Requires and Skip")
            continue
        if not all(isinstance(definition[key], list) and all(isinstance(v, str) for v in definition[key])
                   for key in ("requires", "skip_if")) or not isinstance(definition["definition"], str):
            error("DEFINITION_SHAPE", path, "Definition must be text; Requires and Skip must be text lists")
            continue
        for name in ("scheme", "definition_version", "id", "definition", "requires", "skip_if"):
            nonblank(definition[name], path + "." + name)
        key = (definition["scheme"], definition["id"])
        if key in rule_index:
            error("DUPLICATE_DEFINITION", path, "A selected rule must have one frozen definition")
        rule_index[key] = definition

    def fact_refs(values, path, allowed=None, observed=False, required=False):
        refs(values, facts if allowed is None else allowed, path, required=required)
        if observed and any(facts[key].basis == "HYPOTHESIS" for key in values if key in facts):
            error("HYPOTHESIS_AS_OBSERVATION", path, "Hypotheses cannot supply observed scenario or label facts")

    selected = {}
    for i, label in enumerate(analysis.selected_labels):
        path = f"selected_labels[{i}]"
        key = (label.scheme, label.trigger_id)
        if key in selected:
            error("DUPLICATE_LABEL", path, "A rule is selected at most once per analysis")
        selected[key] = label
        definition = rule_index.get(key)
        if definition is None:
            error("MISSING_DEFINITION", path, "Provide the complete frozen definition for this selected rule")
            continue
        if label.definition_version != definition["definition_version"]:
            error("DEFINITION_VERSION", path + ".definition_version", "The selected rule must preserve its frozen version")
        nonblank(label.construction_feasibility.reason, path + ".construction_feasibility.reason")
        fact_refs(label.condition_fact_ids, path + ".condition_fact_ids", observed=True,
                  required=label.semantic_applicability != "UNKNOWN")
        expected = canonical_conditions(definition, definition.get("family"))
        actual = [(c.clause_role, c.clause) for c in label.predicate_checks]
        if len(actual) != len(set(actual)) or set(actual) != expected:
            error("PREDICATE_COMPLETENESS", path + ".predicate_checks", "Check every definition/Requires/Skip clause exactly once")
        for j, check in enumerate(label.predicate_checks):
            cpath = f"{path}.predicate_checks[{j}]"
            fact_refs(check.condition_fact_ids, cpath + ".condition_fact_ids", label.condition_fact_ids,
                      observed=True, required=check.result != "UNKNOWN")
            refs([r.segment_id for r in check.evidence], known_evidence, cpath + ".evidence")
        negative = any(c.result == ("NOT_MET" if c.clause_role == "INCLUSION" else "MET") for c in label.predicate_checks)
        complete = bool(label.predicate_checks) and all(
            c.result == ("MET" if c.clause_role == "INCLUSION" else "NOT_MET") for c in label.predicate_checks)
        if label.semantic_applicability == "APPLICABLE" and not complete:
            error("APPLICABLE_WITH_UNKNOWN", path, "Full applicability needs all Requires and Skip checks resolved")
        if label.semantic_applicability in POSITIVE and negative:
            error("POSITIVE_WITH_EXCLUSION", path, "A positive label cannot override a known failed requirement or Skip")
        if label.semantic_applicability == "NOT_APPLICABLE" and not negative:
            error("EXCLUSION_WITHOUT_FACT", path, "Missing information does not establish an exclusion")
        allowed_roles = set(definition.get("allowed_fact_roles", []))
        if label.semantic_applicability != "UNKNOWN" and allowed_roles and not allowed_roles & {
                facts[k].role for k in label.condition_fact_ids if k in facts}:
            error("LABEL_FACT_ROLE", path, "The label needs its own allowed semantic role")
        constructions = {c["id"]: c for c in definition.get("constructions", [])}
        seen_constructions = set()
        for j, construction in enumerate(label.construction_checks):
            cpath = f"{path}.construction_checks[{j}]"
            cid = construction.construction_id
            if cid in seen_constructions:
                error("DUPLICATE_CONSTRUCTION", cpath, "Check a selected construction once")
            seen_constructions.add(cid)
            if label.scheme != "V4" or cid not in definition.get("construction_ids", []) or cid not in constructions:
                error("CONSTRUCTION_SCOPE", cpath, "Use a mounted V4 construction and its full frozen definition")
                continue
            check = construction.definition_check
            if check.clause_role != "INCLUSION" or check.clause != constructions[cid]["definition"].strip():
                error("CONSTRUCTION_DEFINITION", cpath, "Retain the complete selected construction definition")
            if construction.applicability == "UNKNOWN":
                error("SPARSE_UNKNOWN_CONSTRUCTION", cpath, "Omit unselected UNKNOWN constructions")
            if construction.applicability in POSITIVE and check.result != "MET":
                error("CONSTRUCTION_WITHOUT_CLUE", cpath, "Positive construction needs its independently supported definition check")
            fact_refs(construction.condition_fact_ids, cpath + ".condition_fact_ids", label.condition_fact_ids,
                      observed=True, required=construction.applicability != "UNKNOWN")
            fact_refs(check.condition_fact_ids, cpath + ".definition_check.condition_fact_ids",
                      construction.condition_fact_ids, observed=True, required=check.result != "UNKNOWN")
            for name, evidence in (("evidence", construction.evidence), ("definition_check.evidence", check.evidence)):
                refs([r.segment_id for r in evidence], known_evidence, cpath + "." + name)

    for i, scenario in enumerate(analysis.scenarios):
        fact_refs(scenario.condition_fact_ids, f"scenarios[{i}].condition_fact_ids", observed=True, required=True)
        for name in ("scenario_id", "title", "reason"):
            nonblank(getattr(scenario, name), f"scenarios[{i}]." + name)
    covered = {}
    linked_constructions = set()
    used_scenarios = set()
    for i, link in enumerate(analysis.label_links):
        path = f"label_links[{i}]"
        key = (link.scheme, link.trigger_id)
        label = selected.get(key)
        if label is None or label.semantic_applicability not in POSITIVE:
            error("LINK_REQUIRES_POSITIVE", path, "Link only an independently selected positive rule")
            continue
        if link.definition_version != label.definition_version:
            error("LINK_VERSION", path + ".definition_version", "Links must retain the selected rule's version")
        refs(link.detail_ids, {analysis.analysis_id}, path + ".detail_ids", required=True)
        fact_refs(link.condition_fact_ids, path + ".condition_fact_ids", label.condition_fact_ids, observed=True, required=True)
        refs(link.scenario_ids, scenarios, path + ".scenario_ids", required=True)
        for sid in link.scenario_ids:
            used_scenarios.add(sid)
            if sid in scenarios and not set(link.condition_fact_ids) <= set(scenarios[sid].condition_fact_ids):
                error("LINK_SCENARIO_FACTS", path, "Link facts must occur together in every linked local scenario")
        if label.semantic_applicability == "APPLICABLE" and set(link.condition_fact_ids) != set(label.condition_fact_ids):
            error("APPLICABLE_SCENARIO_STITCH", path, "Every fully applicable link must carry all required row facts")
        covered.setdefault(key, set()).update(link.condition_fact_ids)
        checks = {c.construction_id: c for c in label.construction_checks}
        refs(link.construction_ids, checks, path + ".construction_ids")
        for cid in link.construction_ids:
            check = checks.get(cid)
            if link.scheme != "V4" or check is None or check.applicability not in POSITIVE or not set(check.condition_fact_ids) <= set(link.condition_fact_ids):
                error("CONSTRUCTION_LINK_FACTS", path, "A construction needs its own positive check and facts in this link")
            linked_constructions.add((key, cid))
    for key, label in selected.items():
        if label.semantic_applicability in POSITIVE and covered.get(key, set()) != set(label.condition_fact_ids):
            error("POSITIVE_LABEL_UNLINKED", "selected_labels", "Every positive rule fact needs explicit local mechanism/scenario links")
        for check in label.construction_checks:
            if check.applicability in POSITIVE and (key, check.construction_id) not in linked_constructions:
                error("POSITIVE_CONSTRUCTION_UNLINKED", "selected_labels", "Every positive construction must be explicitly linked")
    if used_scenarios != set(scenarios):
        error("UNLINKED_SCENARIO", "scenarios", "Scenarios must belong to this analysis's explicit label links")

    guides = {g["guide_id"]: g for d in rule_index.values() for g in d.get("guides", [])}
    for i, card in enumerate(analysis.design_cards):
        path = f"design_cards[{i}]"
        raw = record["design_cards"][i]
        if isinstance(raw, BaseModel):
            raw = raw.model_dump(exclude_unset=True)
        if card.assessment_id != analysis.analysis_id:
            error("CARD_ANALYSIS_SCOPE", path + ".assessment_id", "A card belongs to this one analysis and subproblem")
        for key in ("card_id", "assessment_id", "reference", "target_path", "checks", "required_capabilities", "capability_gaps", "unknowns"):
            nonblank(getattr(card, key), path + "." + key)
        for key in ("required_capabilities", "capability_gaps"):
            if key not in raw:
                error("CARD_CAPABILITY_EXPLICIT", path + "." + key, "State capabilities and gaps explicitly, including an empty list")
        if raw.get("execution_status") != "NOT_RUN" or raw.get("execution_implemented") is not False:
            error("OFFLINE_ONLY", path, "Every card must explicitly be NOT_RUN with execution_implemented=false")
        allowed = set(facts)
        if scenarios:
            if card.scenario_id not in scenarios:
                error("CARD_SCENARIO_SCOPE", path + ".scenario_id", "Bind one local scenario")
                allowed = set()
            else:
                allowed = set(scenarios[card.scenario_id].condition_fact_ids)
        elif card.scenario_id or card.category_ids or card.status != "NEEDS_FACTS":
            error("NO_SCENARIO_NEEDS_FACTS", path, "Without a positive classified scenario keep an unlabelled NEEDS_FACTS card")
        fact_refs(card.condition_fact_ids, path + ".condition_fact_ids", allowed, observed=True)
        category_links = [l for l in analysis.label_links if l.scheme == "V4" and card.scenario_id in l.scenario_ids]
        refs(card.category_ids, {l.trigger_id for l in category_links}, path + ".category_ids")
        card_codes = {cid for l in category_links if l.trigger_id in card.category_ids for cid in l.construction_ids}
        refs(card.construction_ids, card_codes, path + ".construction_ids")
        refs(card.guide_ids, guides, path + ".guide_ids")
        if any(guides[g]["category_id"] not in card.category_ids for g in card.guide_ids if g in guides):
            error("GUIDE_LABEL_TRANSFER", path, "Guidance cannot transfer a category label")
        if not card.category_ids and (card.status != "NEEDS_FACTS" or not card.unknowns):
            error("NO_LABEL_NEEDS_FACTS", path, "An unlabelled card must name its missing facts")
        if card.status in {"NEEDS_FACTS", "CAPABILITY_BLOCKED"} and not (card.unknowns or card.capability_gaps):
            error("CARD_GAP", path, "Incomplete or blocked designs must name their gap")
        for j, variable in enumerate(card.variables):
            assert isinstance(variable, DesignVariable)  # Native DesignCard owns this model.
            vpath = f"{path}.variables[{j}]"
            for name in ("name", "reason", "proposed_values"):
                nonblank(getattr(variable, name), vpath + "." + name)
            fact_refs(variable.condition_fact_ids, vpath + ".condition_fact_ids", allowed)
            refs(variable.guide_ids, card.guide_ids, vpath + ".guide_ids")
            if not variable.condition_fact_ids and not variable.guide_ids:
                error("VARIABLE_PROVENANCE", vpath, "Use local facts or explicitly selected construction guidance")
            if variable.kind == "INPUT" and any(facts[f].basis == "HYPOTHESIS" or facts[f].role in INTERNAL_ROLES
                                                for f in variable.condition_fact_ids if f in facts):
                error("ASSUMPTION_AS_INPUT", vpath, "An internal quantity or hypothesis cannot become an original API input")

    for i, comparison in enumerate(analysis.mode_comparisons):
        refs(comparison.evidence_ids, known_evidence, f"mode_comparisons[{i}].evidence_ids",
             required=comparison.relation != "UNKNOWN")
    if analysis.mode_decision.action == "NEW" and (not analysis.mode_comparisons or any(
            c.relation != "DIFFERENT" for c in analysis.mode_comparisons)):
        error("UNKNOWN_IS_NOT_NOVELTY", "mode_decision", "NEW needs grounded differences in the selected comparisons; UNKNOWN proves no novelty")
    if analysis.mode_decision.action == "EXISTING" and not any(c.relation == "SAME" for c in analysis.mode_comparisons):
        error("EXISTING_WITHOUT_COMPARISON", "mode_decision", "An existing-mode suggestion needs a supported SAME comparison")
    if analysis.mode_decision.action == "EXTEND" and not any(c.relation == "PARTIAL" for c in analysis.mode_comparisons):
        error("EXTEND_WITHOUT_COMPARISON", "mode_decision", "An extension suggestion needs a supported PARTIAL comparison")
    return errors
