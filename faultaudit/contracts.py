"""Versioned interchange contracts for the first fault evidence audit core.

These contracts validate structure, not the truth of a model's conclusions.
Saved snapshots and business gates must additionally verify every citation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceCase(Contract):
    case_id: str
    external_id: str = ""
    source_file: str
    source_sha256: str
    sheet: str
    row: int = Field(ge=1)
    source_kind: str = "LEGACY_TABLE"
    raw: dict[str, str] = Field(default_factory=dict)
    cell_locations: dict[str, str] = Field(default_factory=dict)
    description: str = ""
    customer_model: str = ""
    operator_raw: str = ""
    root_cause_raw: str = ""
    root_cause_origin: str = "LEGACY_DERIVED_UNKNOWN"


class ReferenceOccurrence(Contract):
    ref_id: str
    case_id: str
    raw_text: str
    url: str | None = None
    origin: str
    location: str
    status: Literal["PARSED", "MALFORMED", "UNRESOLVED"] = "PARSED"
    discovered_by: str = "importer"
    parent_ref_id: str | None = None
    discovery_query: str = ""
    parent_url: str | None = None
    discovered_at: str | None = None


RetrievalStatus = Literal[
    "COMPLETE", "PARTIAL", "AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND",
    "TIMEOUT", "PARSE_FAILED", "UNSUPPORTED",
]


class EvidencePackage(Contract):
    schema_version: Literal["1.0"] = "1.0"
    url: str
    title: str = ""
    text: str = ""
    status: RetrievalStatus = "COMPLETE"
    components: dict[str, str] = Field(default_factory=dict)
    retrieved_by: str = "manual-import"
    retrieved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    derived_from: list[str] = Field(default_factory=list)
    is_synthetic: bool = False
    case_ids: list[str] = Field(default_factory=list)
    origin: str = "HUMAN_ADDED"
    raw_file: str | None = None
    requested_url: str | None = None
    final_url: str | None = None
    record_discovery: bool = False
    discovery_query: str = ""
    discovered_from_url: str | None = None


class EvidenceRef(Contract):
    segment_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def nonblank_reference(self) -> "EvidenceRef":
        if not self.segment_id.strip() or not self.quote.strip():
            raise ValueError("evidence segment_id and quote must not be blank")
        return self


class EvidenceSummary(Contract):
    snapshot_id: str
    issues: list[dict[str, Any]] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)
    model_mode: str
    model_id: str

    @model_validator(mode="after")
    def cited_issue_facts(self) -> "EvidenceSummary":
        for issue in self.issues:
            facts = issue.get("facts")
            if facts is not None:
                if not isinstance(facts, list):
                    raise ValueError("issue facts must be a list")
                for fact in facts:
                    if not isinstance(fact, dict):
                        raise ValueError("each fact must be an object")
                    refs = fact.get("evidence") or fact.get("evidence_refs")
                    if fact.get("value") not in (None, "", [], {}) and not refs:
                        raise ValueError("every nonempty fact must carry evidence references")
                    for ref in refs or []:
                        EvidenceRef.model_validate(ref)
            else:
                refs = issue.get("evidence") or issue.get("evidence_refs")
                nonempty = any(value not in (None, "", [], {}) for key, value in issue.items()
                               if key not in {"label", "title", "issue_id", "evidence", "evidence_refs"})
                if nonempty and not refs:
                    raise ValueError("a nonempty issue must carry evidence references")
                for ref in refs or []:
                    EvidenceRef.model_validate(ref)
        return self


class Judgment(Contract):
    case_id: str
    snapshot_id: str
    case_attribution: Literal["CONFIRMED", "PARTIAL", "UNKNOWN", "MISMATCH"]
    event_relation: Literal["SAME_EVENT", "DIFFERENT_EVENT", "UNDETERMINED"]
    pattern_relation: Literal["SAME_PATTERN", "DIFFERENT_PATTERN", "POSSIBLY_RELATED", "UNDETERMINED"]
    support_level: Literal["DIRECT", "PARTIAL", "INDIRECT", "NONE", "PENDING", "CONFLICT"]
    claim_support: dict[str, Literal["SUPPORTED", "PARTIAL", "CONTRADICTED", "NOT_MENTIONED", "UNKNOWN"]] = Field(default_factory=dict)
    matched_dimensions: list[str] = Field(default_factory=list)
    conflicting_dimensions: list[str] = Field(default_factory=list)
    unknown_dimensions: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    event_anchor: str = ""
    short_reason: str
    missing_information: list[str] = Field(default_factory=list)
    model_mode: str
    model_id: str

    @model_validator(mode="after")
    def positive_judgment_requirements(self) -> "Judgment":
        invalid_claim_keys = set(self.claim_support) - {"symptom", "root_cause", "fix", "verification"}
        if invalid_claim_keys:
            raise ValueError(f"unsupported claim_support keys: {sorted(invalid_claim_keys)}")
        if (self.support_level == "DIRECT" or self.case_attribution == "CONFIRMED") and not self.evidence:
            raise ValueError("direct or confirmed judgments require evidence")
        if self.event_relation == "SAME_EVENT" and not self.event_anchor.strip():
            raise ValueError("SAME_EVENT requires an explicit event anchor")
        return self


class CatalogItem(Contract):
    item_id: str
    description: str = ""
    operator: str = ""
    mechanism: str = ""
    trigger: str = ""
    raw: dict[str, str] = Field(default_factory=dict)
    source_file: str
    source_sha256: str
    source_location: str
