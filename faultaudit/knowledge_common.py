"""Shared grounded statements for knowledge tasks, not adoption or device claims."""
from __future__ import annotations

from typing import Literal
from pydantic import Field, ValidationError
from .contracts import Contract, CatalogDraftProducer, SelfCheck
from .trigger_assessment import ConditionFact
from .store import AuditError

PROFILE = "CANN_BASELINE_BUILDER_V1"
SEMANTIC_KINDS = {"baseline_define", "baseline_v4", "baseline_api42", "baseline_execution", "baseline_review"}


class Claim(Contract):
    text: str = Field(min_length=1)
    status: Literal["STATED", "INFERRED", "UNKNOWN"]
    condition_fact_ids: list[str] = Field(default_factory=list)


class KnowledgeResponse(Contract):
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_id: str = Field(min_length=1)
    executor: Literal["opencode", "codex"]
    producer: CatalogDraftProducer
    condition_facts: list[ConditionFact]
    self_check: SelfCheck


def validate_common(payload, response, model, request_hash):
    try:
        value = model.model_validate(response)
    except ValidationError as exc:
        raise AuditError("Invalid knowledge response: " + str(exc)) from exc
    if value.request_hash != request_hash or value.case_id != payload["subject"]["case_id"]:
        raise AuditError("Knowledge response identity differs from the assigned source")
    if not value.self_check.passed:
        raise AuditError("Knowledge task self-check failed; preserve the attempt and review it")
    case = payload["subject"]["source_case"]
    raw, cells = case.get("raw", {}), case.get("cell_locations", {})
    issue = payload.get("source_issue") or {}
    snapshot = issue.get("snapshot") or {}
    segments = {s["segment_id"]: s["text"] for s in snapshot.get("segments", [])}
    scope = issue.get("input_scope") or snapshot.get("input_scope") or {}
    if "provided_segment_ids" in scope:
        segments = {k: v for k, v in segments.items() if k in scope["provided_segment_ids"]}
    allowed = [r for f in issue.get("facts", []) for r in f.get("evidence", [])]
    facts = {f.fact_id: f for f in value.condition_facts}
    if len(facts) != len(value.condition_facts):
        raise AuditError("Knowledge fact IDs must be unique")
    for fact in facts.values():
        if fact.subject == "SOURCE_RECORD":
            if fact.evidence_basis != "SOURCE_DEFINITION" or not fact.source_cells or fact.evidence:
                raise AuditError("Original declarations need exact source cells, not webpage assertions")
        elif fact.evidence_basis not in {"SOURCE_REPORTED", "CODE_INFERENCE"} or not fact.evidence:
            raise AuditError("Current material facts require scoped webpage quotations")
        for cell in fact.source_cells:
            if cells.get(cell.field) != cell.cell or not cell.quote.strip() or cell.quote not in raw.get(cell.field, ""):
                raise AuditError("Knowledge source cell or quote differs from the frozen original")
        for ref in fact.evidence:
            if snapshot.get("status") not in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"} or ref.quote not in segments.get(ref.segment_id, "") or not ref.quote.strip() or not any(
                    ref.segment_id == r["segment_id"] and ref.quote in r["quote"] for r in allowed):
                raise AuditError("Knowledge quote is outside the current material issue/input scope")
    return value, facts


def checked_claim(claim, facts):
    ids = claim.condition_fact_ids
    if len(ids) != len(set(ids)) or not set(ids) <= set(facts):
        raise AuditError("Knowledge claim references unknown or duplicate facts")
    if claim.status != "UNKNOWN" and not ids:
        raise AuditError("A stated or inferred knowledge claim needs cited local facts")


def enabled(store, run_id):
    cfg = store.get(run_id, "trigger_config", "config") or {}
    return cfg.get("knowledge_profile") == PROFILE
