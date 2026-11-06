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
    "TIMEOUT", "PARSE_FAILED", "UNSUPPORTED", "NOT_FETCHED",
    "NETWORK_BLOCKED", "CONTENT_CAPTURED",
]


class EvidencePackage(Contract):
    schema_version: Literal["1.0"] = "1.0"
    url: str
    title: str = ""
    text: str = ""
    status: RetrievalStatus = "COMPLETE"
    components: dict[str, str] = Field(default_factory=dict)
    artifact_type: Literal["GENERIC", "WIKI", "DTS", "PR"] = "GENERIC"
    required_components: list[str] = Field(default_factory=list)
    expected_file_count: int | None = Field(default=None, ge=0, strict=True)
    captured_file_count: int | None = Field(default=None, ge=0, strict=True)
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


class NegativeIdentityBasis(Contract):
    """A producer-declared positive identity statement, never an inferred gap.

    The gate checks structure and exact source grounding. Human review still
    decides whether the declared identity/ownership semantics are justified.
    """
    positive_identity: str = Field(min_length=1)
    context: str = Field(min_length=16)
    dimensions: list[Literal[
        "event_identity", "ownership", "symptom", "occurrence_context", "explicit_exclusion",
    ]] = Field(min_length=1)
    evidence: list[EvidenceRef] = Field(min_length=1)


class NegativeBasis(Contract):
    other_event: NegativeIdentityBasis | None = None
    attribution_mismatch: NegativeIdentityBasis | None = None


class FactComparison(Contract):
    category: Literal["NUMBER", "TERM", "SCENARIO", "TECHNICAL_CONCLUSION"]
    source_field: str = ""
    source_quote: str = ""
    source_cell: str = ""
    source_value: str = ""
    evidence_value: str = ""
    source_meaning: str = ""
    evidence_meaning: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)
    relation: Literal["MATCH", "CONFLICT", "UNKNOWN", "NAME_ONLY", "DIFFERENT"]
    reason: str = ""


class ApplicableIssue(Contract):
    label: str = Field(min_length=1)
    evidence: list[EvidenceRef] = Field(min_length=1)
    selection_reason: str = Field(min_length=1)


class SelfCheck(Contract):
    attempt: int = Field(ge=1, le=1, strict=True)
    numeric_meaning_checked: bool = Field(strict=True)
    citations_checked: bool = Field(strict=True)
    counterevidence_checked: bool = Field(strict=True)
    issue_scope_checked: bool = Field(strict=True)
    event_vs_technical_checked: bool = Field(strict=True)
    passed: bool = Field(strict=True)
    issues: list[str] = Field(default_factory=list)


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
    negative_basis: NegativeBasis | None = None
    observation_scope: Literal["CAPTURED_CONTENT", "FULL_DOCUMENT"] = "CAPTURED_CONTENT"
    fact_comparisons: list[FactComparison] = Field(default_factory=list)
    applicable_issue: ApplicableIssue | None = None
    self_check: SelfCheck | None = None
    short_reason: str
    missing_information: list[str] = Field(default_factory=list)
    model_mode: str
    model_id: str

    @model_validator(mode="after")
    def positive_judgment_requirements(self) -> "Judgment":
        invalid_claim_keys = set(self.claim_support) - {"symptom", "root_cause", "fix", "verification"}
        if invalid_claim_keys:
            raise ValueError(f"unsupported claim_support keys: {sorted(invalid_claim_keys)}")
        if self.event_relation == "DIFFERENT_EVENT" and (self.negative_basis is None or self.negative_basis.other_event is None):
            raise ValueError("DIFFERENT_EVENT requires positive other-event identity evidence")
        if self.case_attribution == "MISMATCH" and (self.negative_basis is None or self.negative_basis.attribution_mismatch is None):
            raise ValueError("MISMATCH requires positive attribution/exclusion evidence")
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
    catalog_scope: str = "UNSPECIFIED"
    catalog_version: str = ""
    sheet: str = ""
    row: int | None = Field(default=None, ge=1)


class CatalogDraftRow(Contract):
    """The user's fifteen columns; evidence and proposal status live alongside."""
    level1: Literal["芯片使能"]
    level2: Literal["CANN"]
    level3: Literal["计算算子", "通信算子", "图引擎"]
    level4: Literal["算子计算", "算子接口", "数据切分", "图融合优化"]
    pattern_name: str = Field(min_length=1)
    root_cause: str = Field(min_length=1)
    effect: str = Field(min_length=1)
    scenario: str = Field(min_length=1)
    precision_type: str = Field(min_length=1)
    detection: str = Field(min_length=1)
    mitigation: str = Field(min_length=1)
    constructibility: str = Field(min_length=1)
    injection_tool: str = Field(min_length=1)
    injection_method: str = Field(min_length=1)
    case_links: str = Field(min_length=1)

    @model_validator(mode="after")
    def nonblank_cells(self) -> "CatalogDraftRow":
        if any(not getattr(self, key).strip() for key in type(self).model_fields):
            raise ValueError("draft cells must not be blank; use an explicit unknown")
        return self


class CatalogSourceCell(Contract):
    case_id: str = Field(min_length=1)
    field: str = Field(min_length=1)
    cell: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class CatalogFieldBasis(Contract):
    kind: Literal["ABSTRACTION", "SOURCE_CELL", "CITED_FACT", "CODE_INFERENCE", "PROPOSED", "UNKNOWN"]
    fact_ids: list[str] = Field(default_factory=list)
    source_cells: list[CatalogSourceCell] = Field(default_factory=list)
    note: str = Field(min_length=1)


class CatalogCoverageComparison(Contract):
    item_id: str = Field(min_length=1)
    relation: Literal["SAME_PATTERN", "PARTIAL", "DIFFERENT", "UNKNOWN"]
    reason: str = Field(min_length=1)


class CatalogProposal(Contract):
    proposal_id: str = Field(min_length=1)
    revision: int = Field(ge=1, strict=True)
    action: Literal["ADD", "REFINE", "APPEND_CASE", "NO_CHANGE"]
    target_item_id: str | None = None
    case_ids: list[str] = Field(min_length=1)
    work_ids: list[str] = Field(default_factory=list)
    evidence_scope: Literal["CASE_ROOT_CAUSE", "INDEPENDENT_TECHNICAL_PATTERN"]
    implementation_owner: str = Field(min_length=1)
    row: CatalogDraftRow
    field_bases: dict[str, CatalogFieldBasis]
    coverage_comparisons: list[CatalogCoverageComparison] = Field(min_length=1)
    unknowns: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    self_check: SelfCheck
    injection_execution: Literal["NOT_EXECUTED"] = "NOT_EXECUTED"

    @model_validator(mode="after")
    def nonblank_identity(self) -> "CatalogProposal":
        if not self.proposal_id.strip() or not self.implementation_owner.strip():
            raise ValueError("proposal identity and implementation owner must not be blank")
        if any(not item.reason.strip() for item in self.coverage_comparisons):
            raise ValueError("every catalog comparison requires a nonblank reason")
        return self


class CatalogDraftProducer(Contract):
    executor_version: str = Field(default="UNREPORTED", min_length=1)
    provider: str = Field(default="UNREPORTED", min_length=1)
    model: str = Field(default="UNREPORTED", min_length=1)
    session_id: str = Field(default="UNREPORTED", min_length=1)


class CatalogDraft(Contract):
    """External Agent file response, never a human review or library update."""
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["CATALOG_DRAFT"] = "CATALOG_DRAFT"
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    executor: Literal["opencode", "codex", "manual"]
    created_by: str = Field(min_length=1)
    producer: CatalogDraftProducer
    proposals: list[CatalogProposal] = Field(min_length=1)
