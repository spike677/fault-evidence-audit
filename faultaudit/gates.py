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
