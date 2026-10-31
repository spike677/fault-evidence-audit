"""Shared mechanical event-anchor requirements, separate from semantic truth."""
from __future__ import annotations


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
    explicit = {str(raw.get(key, "")).strip() for key in
                ("事件编号", "事件ID", "故障编号", "incident_id", "event_id")}
    explicit.discard("")
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


def _negative_basis_errors(name: str, basis: dict, snapshot: dict, judgment: dict) -> list[str]:
    """Check declared positive context and citations without classifying prose."""
    errors = []
    identity = str(basis.get("positive_identity", "")).strip()
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
    errors = []
    bases = judgment.get("negative_basis") or {}
    other_event = bases.get("other_event")
    attribution = bases.get("attribution_mismatch")
    if judgment.get("event_relation") == "DIFFERENT_EVENT" and not other_event:
        errors.append("DIFFERENT_EVENT requires cited positive evidence identifying another event; missing fields or technical differences are insufficient")
    if judgment.get("case_attribution") == "MISMATCH" and not attribution:
        errors.append("MISMATCH requires cited positive ownership/exclusion evidence; missing fields or root-cause conflicts are insufficient")
    for name, basis in (("other_event", other_event), ("attribution_mismatch", attribution)):
        if basis is not None:
            errors.extend(_negative_basis_errors(name, basis, snapshot, judgment))
    if judgment.get("observation_scope", "CAPTURED_CONTENT") == "FULL_DOCUMENT":
        input_scope = snapshot.get("input_scope") or {}
        if snapshot.get("status") != "COMPLETE" or input_scope.get("scope") != "FULL_CAPTURED_SNAPSHOT":
            errors.append("FULL_DOCUMENT observations require COMPLETE retrieval and FULL_CAPTURED_SNAPSHOT input; unprovided text remains unknown")
    if judgment.get("support_level") == "DIRECT":
        if judgment.get("conflicting_dimensions") or "CONTRADICTED" in (judgment.get("claim_support") or {}).values():
            errors.append("DIRECT cannot coexist with unresolved dimension or claim contradictions")
    return list(dict.fromkeys(errors))
