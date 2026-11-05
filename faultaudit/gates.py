"""Shared mechanical event-anchor requirements, separate from semantic truth."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re

FACT_CATEGORIES = {"NUMBER", "TERM", "SCENARIO", "TECHNICAL_CONCLUSION"}
SELF_CHECK_FIELDS = ("numeric_meaning_checked", "citations_checked", "counterevidence_checked",
                     "issue_scope_checked", "event_vs_technical_checked")


def _literal_present(value: str, quote: str, category: str) -> bool:
    """Check literal token bounds; never equate rope with part of npu_mrope."""
    if not value or not isinstance(quote, str):
        return False
    if category == "TERM" and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", value):
        return re.search(r"(?<![A-Za-z0-9_])" + re.escape(value) + r"(?![A-Za-z0-9_])", quote) is not None
    return value in quote


def _value_key(value: str, category: str):
    if category == "NUMBER":
        try:
            parsed = Decimal(value)
            if parsed.is_finite():
                return parsed
        except InvalidOperation:
            pass
    return value.strip().casefold()


def _exact_refs(refs: list[dict], snapshot: dict) -> bool:
    segments = {s.get("segment_id"): s.get("text", "") for s in snapshot.get("segments", [])}
    return bool(refs) and all(isinstance(ref.get("quote"), str) and ref["quote"].strip()
        and ref.get("segment_id") in segments and ref["quote"] in segments[ref["segment_id"]]
        and segments[ref["segment_id"]] in snapshot.get("text", "") for ref in refs)


def fact_comparison_errors(case: dict, snapshot: dict, judgment: dict) -> list[str]:
    """Mechanical source/cell/value/scope checks, independent of semantic truth."""
    errors = []
    raw, cells = case.get("raw", {}), case.get("cell_locations", {})
    issue = judgment.get("applicable_issue")
    if issue and not _exact_refs(issue.get("evidence", []), snapshot):
        errors.append("Applicable issue requires exact references from this snapshot")
    scopes = issue.get("evidence", []) if issue else []
    outer_refs = judgment.get("evidence", [])
    for index, fact in enumerate(judgment.get("fact_comparisons", [])):
        label = f"Fact comparison {index + 1}: "
        field, quote, cell = (fact.get(key, "") for key in ("source_field", "source_quote", "source_cell"))
        if field or quote or cell:
            if (not field or field not in raw or not quote.strip() or quote not in raw[field]
                    or not cell.strip() or not cells.get(field) or cell != cells[field]):
                errors.append(label + "source field, verbatim quote and exact source-cell locator must match the original case")
        refs = fact.get("evidence", [])
        if refs and not _exact_refs(refs, snapshot):
            errors.append(label + "evidence must quote exact segments from this snapshot")
        if refs and not all(any(ref.get("segment_id") == outer.get("segment_id") and ref.get("quote", "") in outer.get("quote", "")
                                for outer in outer_refs) for ref in refs):
            errors.append(label + "fact evidence must be retained in the judgment evidence")
        if scopes and not all(any(ref.get("segment_id") == scope.get("segment_id") and ref.get("quote", "") in scope.get("quote", "")
                                  for scope in scopes) for ref in refs):
            errors.append(label + "fact evidence falls outside the selected applicable issue")
        source_value, evidence_value = fact.get("source_value", ""), fact.get("evidence_value", "")
        category = fact.get("category", "")
        if source_value and not _literal_present(source_value, quote, category):
            errors.append(label + "source value must occur as the declared literal in the source quote")
        if evidence_value and not any(_literal_present(evidence_value, ref.get("quote", ""), category) for ref in refs):
            errors.append(label + "evidence value must occur as the declared literal in cited evidence")
        if fact.get("relation") == "MATCH":
            meanings = (fact.get("source_meaning", "").strip().casefold(), fact.get("evidence_meaning", "").strip().casefold())
            if not field or not quote or not cell or not refs or not meanings[0] or meanings[0] != meanings[1] or meanings[0] in {"unknown", "unreported", "unspecified"}:
                errors.append(label + "MATCH requires sourced cells, citations and the same explicit meaning on both sides")
            if category in {"NUMBER", "TERM"} and (not source_value or not evidence_value
                    or _value_key(source_value, category) != _value_key(evidence_value, category)):
                errors.append(label + "numeric/term MATCH requires equal explicit values as well as equal meanings")
    return list(dict.fromkeys(errors))


def processing_decision(case: dict, snapshot: dict, judgment: dict, source_relation: str | dict) -> dict:
    """Decide whether fact organization is done; never grant human ACCEPT."""
    context = source_relation if isinstance(source_relation, dict) else {"source_relation": source_relation}
    relation = context.get("source_relation", "PROVENANCE_PENDING")
    def decision(status: str, reasons: list[str]) -> dict:
        return {"processing_status": status, "review_required": status == "EXCEPTION", "review_reasons": reasons}
    if judgment.get("model_mode") == "mock":
        return decision("PENDING", ["Mock validates workflow only; an executing agent must complete factual comparison"])
    if (judgment.get("conflicting_dimensions") or judgment.get("claim_support", {}).get("root_cause") == "CONTRADICTED"
            or judgment.get("support_level") == "CONFLICT"):
        return decision("EXCEPTION", ["Known factual/root-cause contradictions require resolution even while fact comparisons are incomplete"])
    if relation in {"SOURCE_LINKED", "USER_CONFIRMED"} and (
            judgment.get("case_attribution") == "MISMATCH" or judgment.get("event_relation") == "DIFFERENT_EVENT"):
        return decision("EXCEPTION", ["Trusted source linkage conflicts with the artifact's proposed attribution"])
    facts, check = judgment.get("fact_comparisons", []), judgment.get("self_check") or {}
    if not facts or {fact.get("category") for fact in facts} != FACT_CATEGORIES:
        return decision("PENDING", ["The agent must complete all four fact-comparison categories"])
    errors = judgment_semantic_errors(case, snapshot, judgment)
    if errors:
        return decision("EXCEPTION", errors)
    conflicts = list(judgment.get("conflicting_dimensions") or [])
    if (conflicts or judgment.get("claim_support", {}).get("root_cause") == "CONTRADICTED"
            or any(fact.get("relation") == "CONFLICT" for fact in facts)):
        return decision("EXCEPTION", ["Observed factual/root-cause contradictions require resolution"])
    if check.get("issues"):
        return decision("EXCEPTION", list(check["issues"]))
    if check.get("attempt") != 1 or any(check.get(field) is not True for field in SELF_CHECK_FIELDS) or check.get("passed") is not True:
        return decision("PENDING", ["The agent must finish its single bounded factual self-check"])
    if snapshot.get("status") not in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"} or not snapshot.get("text", "").strip():
        return decision("PENDING", ["Captured evidence text is required"])
    issue = judgment.get("applicable_issue")
    if not issue or not _exact_refs(issue.get("evidence", []), snapshot):
        return decision("PENDING", ["The agent must select and cite the applicable issue scope"])
    if any(fact.get("relation") == "UNKNOWN" and not fact.get("reason", "").strip() for fact in facts):
        return decision("PENDING", ["Unknown dimensions need an explicit scoped explanation"])
    if not any(fact.get("source_field") and fact.get("source_quote") and fact.get("source_cell") and fact.get("evidence") for fact in facts):
        return decision("PENDING", ["At least one comparison needs original-cell and evidence traceability"])
    if relation in {"SOURCE_LINKED", "USER_CONFIRMED"}:
        return decision("AUTO_PROCESSED", [])
    if relation in {"SEARCH_CANDIDATE", "VERIFIED_SEARCH"}:
        if judgment.get("case_attribution") == "MISMATCH" or judgment.get("event_relation") == "DIFFERENT_EVENT":
            return decision("AUTO_PROCESSED", [])
        matched = {fact.get("source_meaning", "").strip().casefold() for fact in facts
                   if fact.get("relation") == "MATCH" and fact.get("source_value") and fact.get("evidence_value")
                   and ((fact.get("category") == "SCENARIO" and fact.get("source_meaning", "").strip().casefold() in {"symptom", "occurrence_context"})
                        or (fact.get("category") == "TECHNICAL_CONCLUSION" and fact.get("source_meaning", "").strip().casefold() in {"mechanism", "trigger", "fix"}))
                   and _value_key(fact["source_value"], fact.get("category", "")) == _value_key(fact["evidence_value"], fact.get("category", ""))}
        if {"symptom", "occurrence_context"}.issubset(matched) and matched.intersection({"mechanism", "trigger", "fix"}):
            return decision("AUTO_PROCESSED", [])
        return decision("PENDING", ["Search association needs specific symptom, occurrence-context and mechanism/trigger/fix matches; generic names or numbers are insufficient"])
    return decision("PENDING", ["Source provenance must be established by the agent"])


def _source_event_identities(case: dict) -> set[str]:
    """Use explicit event/incident fields only, excluding record and artifact IDs."""
    raw = case.get("raw", {})
    identities = {str(raw.get(key, "")).strip() for key in
                  ("事件编号", "事件ID", "故障编号", "incident_id", "event_id")}
    identities.discard("")
    return identities


def event_anchor_errors(case: dict, snapshot: dict, judgment: dict) -> list[str]:
    """An anchor establishes traceability; a human still reviews the proposal.

    Explicit event fields are accepted, or a sufficiently specific phrase from
    the original symptom must be corroborated by mechanism and trigger/fix/build
    dimensions. Operator names and shared URLs alone never identify an event.
    """
    errors = []
    anchor = str(judgment.get("event_anchor", "")).strip()
    raw = case.get("raw", {})
    source_text = "\n".join(str(v) for v in raw.values())
    refs = judgment.get("evidence", [])
    if len(anchor) < 4 or anchor not in source_text or anchor not in snapshot.get("text", "") or not any(
        anchor in ref.get("quote", "") for ref in refs
    ):
        errors.append("Same-event anchor must occur in source raw cells, snapshot and cited evidence")
    explicit = _source_event_identities(case)
    if anchor not in explicit:
        dims = set(judgment.get("matched_dimensions", []))
        description = str(case.get("description", ""))
        if (len(anchor) < 16 or anchor not in description or "http://" in anchor or "https://" in anchor
                or not dims.intersection({"mechanism", "root_cause"})
                or not dims.intersection({"trigger", "fix", "version", "build_version"})
                or "symptom" not in dims):
            errors.append("Generic names/links are not event anchors; need an explicit event ID or a specific corroborated incident signature")
    if judgment.get("conflicting_dimensions"):
        errors.append("Unresolved contradictions prevent same-event confirmation")
    return errors


def _negative_basis_errors(name: str, basis: dict, snapshot: dict, judgment: dict, case: dict) -> list[str]:
    """Check declared positive context and citations without classifying prose."""
    errors = []
    identity = str(basis.get("positive_identity", "")).strip()
    if name == "other_event" and identity in _source_event_identities(case):
        errors.append("other_event positive_identity matches the source event identity; it cannot identify another event. Keep the event relation UNDETERMINED or report the unresolved conflict")
    context = str(basis.get("context", "")).strip()
    dimensions = set(basis.get("dimensions", []))
    allowed = {"event_identity", "ownership", "symptom", "occurrence_context", "explicit_exclusion"}
    if not dimensions or dimensions - allowed:
        errors.append(name + " basis cannot consist of operator, mechanism, root cause, artifact number or link differences")
    has_context = {"symptom", "occurrence_context"}.issubset(dimensions)
    if name == "other_event":
        enough_dimensions = "event_identity" in dimensions and (has_context or "explicit_exclusion" in dimensions)
    else:
        enough_dimensions = "ownership" in dimensions and (has_context or "explicit_exclusion" in dimensions)
    if not enough_dimensions:
        errors.append(name + " requires positive identity/ownership plus occurrence context or an explicit exclusion statement")
    if not identity or len(context) < 16 or identity not in context or context == identity:
        errors.append(name + " requires a contextual positive identity statement, not an isolated token or identifier")
    refs = basis.get("evidence", [])
    all_refs = {(ref.get("segment_id"), ref.get("quote")) for ref in judgment.get("evidence", [])}
    segments = {s.get("segment_id"): s.get("text", "") for s in snapshot.get("segments", [])}
    grounded = False
    for ref in refs:
        sid, quote = ref.get("segment_id"), ref.get("quote", "")
        if (not isinstance(quote, str) or not quote.strip() or sid not in segments
                or quote not in segments[sid] or segments[sid] not in snapshot.get("text", "")
                or (sid, quote) not in all_refs):
            errors.append(name + " basis quote must be exact text in this snapshot and part of the judgment evidence")
            continue
        if identity in quote and context in quote:
            grounded = True
    if not refs or not grounded:
        errors.append(name + " positive identity and its context must occur together in an exact cited passage")
    return errors


def judgment_semantic_errors(case: dict, snapshot: dict, judgment: dict) -> list[str]:
    """Shared requirements for negative proposals, capture scope and conflicts.

    Dimensions are explicit producer declarations. This function does not infer
    event identities, ownership, negation, or semantic entailment from text.
    """
    errors = fact_comparison_errors(case, snapshot, judgment)
    bases = judgment.get("negative_basis") or {}
    other_event = bases.get("other_event")
    attribution = bases.get("attribution_mismatch")
    if judgment.get("event_relation") == "DIFFERENT_EVENT" and not other_event:
        errors.append("DIFFERENT_EVENT requires cited positive evidence identifying another event; missing fields or technical differences are insufficient")
    if judgment.get("case_attribution") == "MISMATCH" and not attribution:
        errors.append("MISMATCH requires cited positive ownership/exclusion evidence; missing fields or root-cause conflicts are insufficient")
    negative_material = judgment.get("event_relation") == "DIFFERENT_EVENT" or judgment.get("case_attribution") == "MISMATCH"
    if negative_material and (judgment.get("claim_support") or {}).get("root_cause") in {"SUPPORTED", "PARTIAL"}:
        errors.append("Different-event or mismatched material cannot support the original case's root cause; retain its technical facts in the independent summary")
    for name, basis in (("other_event", other_event), ("attribution_mismatch", attribution)):
        if basis is not None:
            errors.extend(_negative_basis_errors(name, basis, snapshot, judgment, case))
    if judgment.get("observation_scope", "CAPTURED_CONTENT") == "FULL_DOCUMENT":
        input_scope = snapshot.get("input_scope") or {}
        if snapshot.get("status") != "COMPLETE" or input_scope.get("scope") != "FULL_CAPTURED_SNAPSHOT":
            errors.append("FULL_DOCUMENT observations require COMPLETE retrieval and FULL_CAPTURED_SNAPSHOT input; unprovided text remains unknown")
    if judgment.get("support_level") == "DIRECT":
        if judgment.get("conflicting_dimensions") or "CONTRADICTED" in (judgment.get("claim_support") or {}).values():
            errors.append("DIRECT cannot coexist with unresolved dimension or claim contradictions")
    return list(dict.fromkeys(errors))
