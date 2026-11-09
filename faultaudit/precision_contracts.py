"""Independent Bridge contracts; no changes to evidence or classification rules."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import Field, StrictInt, model_validator
from .contracts import Contract, CatalogDraftProducer, SelfCheck
from .store import digest

Purpose = Literal["KNOWN_PATTERN_VALIDATION", "BLIND_DISCOVERY"]


class PrecisionContext(Contract):
    schema_version: Literal["cann_precision_context.v1"] = "cann_precision_context.v1"
    purpose: Purpose
    blind_evaluation: bool
    bridge_policy_hash: str
    baseline: dict[str, Any] | None
    modes: list[dict[str, Any]]
    api42: dict[str, Any]
    v4: dict[str, Any] | None
    condition_links: dict[str, dict[str, Any]]
    target: dict[str, Any]
    input_scope: dict[str, Any]
    context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def identity(self):
        if self.context_hash != digest(self.model_dump(exclude={"context_hash"})):
            raise ValueError("Context hash differs from its complete contents")
        if self.purpose == "BLIND_DISCOVERY":
            if not self.blind_evaluation or self.baseline or self.modes or self.v4 or self.condition_links:
                raise ValueError("Blind context must not contain known-mode/Baseline/V4 case knowledge")
        elif self.blind_evaluation or not self.baseline or not self.modes:
            raise ValueError("Known-pattern validation must identify its frozen Baseline and exposure")
        return self


class CodeCitation(Contract):
    path: str = Field(min_length=1)
    line: int = Field(ge=1)
    quote: str = Field(min_length=1)


class ModeLink(Contract):
    mode_id: str
    evidence_keys: list[str] = Field(min_length=1)
    condition_link_keys: list[str] = Field(default_factory=list)
    api_trigger_ids: list[str] = Field(default_factory=list)
    v4_class_ids: list[str] = Field(default_factory=list)
    v4_scenario_ids: list[str] = Field(default_factory=list)
    execution_method_ids: list[Literal["E1", "E2", "E3", "E4", "E5"]] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class Participant(Contract):
    call_id: str = Field(min_length=1)
    case_id: StrictInt = Field(ge=0)
    role: Literal["TARGET", "PREDECESSOR", "CONTROL", "INTERFERER", "RANK"]
    context: str = Field(min_length=1)
    stream: str = Field(min_length=1)
    executor: str = Field(min_length=1)
    output_owner: str = Field(min_length=1)


class ExecutionProtocol(Contract):
    method_id: Literal["E1", "E2", "E3", "E4", "E5"]
    target_case_id: StrictInt = Field(ge=0)
    target_call_id: str = Field(min_length=1)
    same_target_arguments_required: Literal[True]
    same_target_binary_required: Literal[True]
    participants: list[Participant] = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    oracle: str = Field(min_length=1)
    repeats: int = Field(default=1, ge=1)
    reset_policy: str = ""
    output_prefill: str = ""
    participation_config: str = ""
    execution_status: Literal["NOT_RUN"] = "NOT_RUN"
    executor_capability: Literal["NOT_IMPLEMENTED_BY_BRIDGE"] = "NOT_IMPLEMENTED_BY_BRIDGE"


class CodeJustification(Contract):
    code_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    kind: Literal["CODE_PATH", "EXECUTION_METHOD"]
    reason: str = Field(min_length=1)
    source_evidence: list[CodeCitation] = Field(min_length=1)


class SemanticReview(Contract):
    status: Literal["CHECKED", "NEEDS_FACTS", "CONFLICT"]
    reason: str = Field(min_length=1)
    source_evidence: list[CodeCitation] = Field(default_factory=list)


class RuleBinding(Contract):
    case_id: StrictInt = Field(ge=0)
    inputs_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode_links: list[ModeLink]
    api_trigger_ids: list[str]
    code_ids: list[str]
    code_justifications: list[CodeJustification] = Field(default_factory=list)
    protocols: list[ExecutionProtocol] = Field(default_factory=list)
    semantic_review: SemanticReview
    experiment_seed: StrictInt | None = None


class BindingDraft(Contract):
    schema_version: Literal["cann_precision_binding_draft.v1"] = "cann_precision_binding_draft.v1"
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    purpose: Purpose
    producer: CatalogDraftProducer
    self_check: SelfCheck
    rules: list[RuleBinding] = Field(min_length=1)


class BoundRules(Contract):
    schema_version: Literal["cann_precision_bindings.v1"] = "cann_precision_bindings.v1"
    bridge_policy_hash: str
    draft: BindingDraft
    execution_work_ids: dict[str, str]
    binding_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def identity(self):
        if self.binding_hash != digest(self.model_dump(exclude={"binding_hash"})):
            raise ValueError("Binding receipt hash differs from its complete contents")
        return self
