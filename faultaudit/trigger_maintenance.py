"""Request a fresh assessment without changing source facts or past results."""
from __future__ import annotations

from .store import AuditError, digest
from .workflow_scope import scoped_store


def request_reassessment(store, run_id: str, subject_id: str, *, reason: str, requested_by: str) -> dict:
    """Advance one subject's input identity; the existing dependency hashes expire it.

    This is an Agent maintenance request, not a human verdict or a correction
    written directly into a model result. The executor must answer a new task.
    """
    from .trigger_workflow import current_assessments

    store = scoped_store(store, run_id)
    if not store.get(run_id, "trigger_config", "config"):
        raise AuditError("Start a trigger workflow before requesting reassessment")
    if not isinstance(reason, str) or not reason.strip() or not isinstance(requested_by, str) or not requested_by.strip():
        raise AuditError("Reassessment requires a reason and actual requesting actor")
    subject = store.get(run_id, "trigger_subjects", subject_id)
    if not subject:
        raise AuditError("Trigger subject is missing or outside the selected workflow scope")
    current = [a for a in current_assessments(store, run_id) if a["subject_id"] == subject_id]
    previous = subject.get("reassessment", {})
    if (not current and previous.get("reason") == reason.strip()
            and previous.get("requested_by") == requested_by.strip()):
        return {"subject_id": subject_id, "case_id": subject["case_id"],
                "revision": previous["revision"], "idempotent": True, "human_review_created": False}
    revision = {"revision": previous.get("revision", 0) + 1,
                "reason": reason.strip(), "requested_by": requested_by.strip(),
                "previous_subject_hash": digest(subject), "source_evidence": False}
    store.event(run_id, "trigger_reassessment_requested", {
        "subject_id": subject_id, "previous_subject": subject, "reassessment": revision,
        "previous_assessment_ids": [a["assessment_id"] for a in current]})
    store.put(run_id, "trigger_subjects", subject_id, {**subject, "reassessment": revision}, mutable=True)
    return {"subject_id": subject_id, "case_id": subject["case_id"], "revision": revision["revision"],
            "idempotent": False, "history_retained": True, "human_review_created": False,
            "next_action": "Run next/submit; maintain and finalize an affected Init before a linked incremental run"}
