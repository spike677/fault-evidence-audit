"""Offline validation gates and an explicit workflow simulator.

OpenCode owns all live model execution. This module performs no network calls,
reads no model credentials, and validates returned task payloads against evidence.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .contracts import EvidenceRef, EvidenceSummary, Judgment
from .gates import event_anchor_errors

MAX_INPUT_CHARS = 48000


class ModelError(RuntimeError):
    def __init__(self, message: str, code: str = "model_error"):
        super().__init__(message)
        self.code = code


class Judge(Protocol):
    calls: list[dict[str, Any]]

    def summarize(self, snapshot: dict[str, Any]) -> dict[str, Any]: ...
    def compare(self, case: dict[str, Any], snapshot: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]: ...
    def map_catalog(self, case: dict[str, Any], judgments: list[dict[str, Any]], items: list[dict[str, Any]]) -> dict[str, Any]: ...


CatalogResult = Literal["COVERED", "PARTIALLY_COVERED", "NOT_COVERED", "UNDETERMINED"]


class _CatalogRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str
    result: CatalogResult
    reason: str = Field(min_length=1)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class _CatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    catalog_results: list[_CatalogRow]
    overall: CatalogResult
    scope: Literal["FULL_CATALOG"]
    model_mode: str
    model_id: str


def _sha(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _readable(snapshot: dict[str, Any]) -> bool:
    return snapshot.get("status") in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"} and bool(str(snapshot.get("text", "")).strip())


def _segments(snapshot: dict[str, Any]) -> dict[str, str]:
    result = {}
    for segment in snapshot.get("segments", []):
        sid, text = segment.get("segment_id"), segment.get("text")
        if not isinstance(sid, str) or not isinstance(text, str) or sid in result:
            raise ModelError("证据段落格式错误或ID重复", "invalid_segments")
        if text not in snapshot.get("text", ""):
            raise ModelError("证据段落内容不属于该快照正文", "invalid_segments")
        result[sid] = text
    return result


def _check_refs(refs: list[dict[str, Any]], snapshot: dict[str, Any]) -> None:
    segments = _segments(snapshot)
    for ref in refs:
        parsed = EvidenceRef.model_validate(ref)
        if parsed.segment_id not in segments or parsed.quote not in segments[parsed.segment_id]:
            raise ModelError("模型引文不属于所引用的原文段落", "invalid_citation")


def _validate_summary(value: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    result = EvidenceSummary.model_validate(value).model_dump()
    if result["snapshot_id"] != snapshot["snapshot_id"]:
        raise ModelError("模型返回了其他资料的ID", "identity_mismatch")
    if not _readable(snapshot) and result["issues"]:
        raise ModelError("没有可用原文，不能提取事实", "ungrounded_summary")
    for issue in result["issues"]:
        if set(issue) != {"label", "facts"} or not isinstance(issue["label"], str) or not isinstance(issue["facts"], list) or not issue["facts"]:
            raise ModelError("资料摘要必须按label和facts逐事实输出", "invalid_summary")
        for fact in issue["facts"]:
            if not isinstance(fact, dict) or set(fact) != {"field", "value", "evidence"}:
                raise ModelError("事实字段结构无效", "invalid_summary")
            val = fact["value"]
            if not isinstance(fact["field"], str) or not fact["field"].strip() or not (
                isinstance(val, str) or (isinstance(val, list) and all(isinstance(x, str) for x in val))
            ):
                raise ModelError("事实必须是带引用的字符串或字符串数组", "invalid_summary")
            if val not in ("", []) and not fact["evidence"]:
                raise ModelError("非空事实缺少原文引用", "invalid_citation")
            _check_refs(fact["evidence"], snapshot)
    return result


def _case_event_anchor(case: dict[str, Any]) -> str:
    raw = case.get("raw", {})
    for key in ("事件编号", "event_id", "incident_id"):
        value = raw.get(key) if isinstance(raw, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _validate_judgment(value: dict[str, Any], case: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    result = Judgment.model_validate(value).model_dump()
    if result["case_id"] != case["case_id"] or result["snapshot_id"] != snapshot["snapshot_id"]:
        raise ModelError("模型判断绑定了其他故障或资料", "identity_mismatch")
    _check_refs(result["evidence"], snapshot)
    substantive = (result["case_attribution"] != "UNKNOWN" or result["event_relation"] != "UNDETERMINED"
                   or result["pattern_relation"] != "UNDETERMINED" or result["support_level"] != "PENDING"
                   or result["matched_dimensions"] or result["conflicting_dimensions"])
    if substantive and not result["evidence"]:
        raise ModelError("关联、排除或冲突结论必须引用原文", "invalid_citation")
    if not _readable(snapshot) and (result["case_attribution"] != "UNKNOWN" or result["support_level"] != "PENDING"
                                    or result["event_relation"] != "UNDETERMINED" or result["pattern_relation"] != "UNDETERMINED"):
        raise ModelError("无正文时必须保持待核验", "ungrounded_judgment")
    if result["event_relation"] == "SAME_EVENT":
        anchor_errors = event_anchor_errors(case, snapshot, result)
        if anchor_errors:
            raise ModelError("; ".join(anchor_errors), "unverified_event_anchor")
    if result["support_level"] == "DIRECT" and result["conflicting_dimensions"]:
        raise ModelError("存在冲突时不能给出直接支持", "conflicting_support")
    if result["case_attribution"] == "CONFIRMED" and snapshot.get("status") != "COMPLETE":
        raise ModelError("确认归属要求完整快照", "ungrounded_direct_support")
    if result["support_level"] == "DIRECT" and (result["case_attribution"] != "CONFIRMED"
            or result["event_relation"] != "SAME_EVENT" or snapshot.get("status") != "COMPLETE"):
        raise ModelError("直接支持要求完整快照及已确认的同一事件", "ungrounded_direct_support")
    claims = result.get("claim_support", {})
    if set(claims) != {"symptom", "root_cause", "fix", "verification"}:
        raise ModelError("必须分别判断症状、根因、修复与验证", "incomplete_claim_support")
    if any(v in {"SUPPORTED", "PARTIAL", "CONTRADICTED"} for v in claims.values()) and not result["evidence"]:
        raise ModelError("肯定claim缺少原文证据", "invalid_citation")
    return result


def _catalog_overall(rows: list[dict[str, Any]]) -> str:
    results = [row["result"] for row in rows]
    if "COVERED" in results:
        return "COVERED"
    if "PARTIALLY_COVERED" in results:
        return "PARTIALLY_COVERED"
    return "NOT_COVERED" if results and all(r == "NOT_COVERED" for r in results) else "UNDETERMINED"


def _validate_catalog(value: dict[str, Any], case: dict[str, Any], judgments: list[dict[str, Any]], items: list[dict[str, Any]]) -> dict[str, Any]:
    result = _CatalogResponse.model_validate(value).model_dump()
    expected = [item["item_id"] for item in items]
    actual = [row["item_id"] for row in result["catalog_results"]]
    if result["case_id"] != case["case_id"] or len(expected) != len(set(expected)) or len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise ModelError("故障库比较必须覆盖全部且唯一的条目ID", "incomplete_catalog")
    valid_judgments = [j for j in judgments if j.get("case_id") == case["case_id"] and j.get("review_status") != "REJECT"]
    confirming = [j for j in valid_judgments if j.get("case_attribution") == "CONFIRMED" and j.get("event_relation") == "SAME_EVENT"
                  and j.get("support_level") == "DIRECT" and j.get("evidence") and not j.get("conflicting_dimensions")
                  and j.get("claim_support", {}).get("root_cause") == "SUPPORTED"]
    confirmed = bool(confirming)
    allowed_refs = {(r.get("segment_id"), r.get("quote")) for j in valid_judgments for r in j.get("evidence", [])}
    supporting_refs = {(r.get("segment_id"), r.get("quote")) for j in confirming for r in j.get("evidence", [])}
    by_id = {item["item_id"]: item for item in items}
    for row in result["catalog_results"]:
        if not confirmed and row["result"] != "UNDETERMINED":
            raise ModelError("本事件尚未确认，故障库覆盖必须保持待核验", "unconfirmed_catalog")
        if row["result"] != "UNDETERMINED" and not str(by_id[row["item_id"]].get("mechanism", "")).strip():
            raise ModelError("故障库条目缺少机制定义，无法判断覆盖或排除", "ungrounded_catalog")
        for ref in row["evidence"]:
            if (ref["segment_id"], ref["quote"]) not in allowed_refs:
                raise ModelError("覆盖判断使用了核验结论之外的引文", "invalid_citation")
        if row["result"] in {"COVERED", "PARTIALLY_COVERED"}:
            item = by_id[row["item_id"]]
            if not row["evidence"] or not str(item.get("mechanism", "")).strip() or any(
                    (r["segment_id"], r["quote"]) not in supporting_refs for r in row["evidence"]):
                raise ModelError("正向覆盖缺少机制定义或事件证据", "ungrounded_catalog")
    if result["overall"] != _catalog_overall(result["catalog_results"]):
        raise ModelError("故障库总体判断与逐项结果不一致", "inconsistent_catalog")
    return result


def _pending(case: dict[str, Any], snapshot: dict[str, Any], mode: str, model: str) -> dict[str, Any]:
    return {"case_id": case["case_id"], "snapshot_id": snapshot["snapshot_id"], "case_attribution": "UNKNOWN",
            "event_relation": "UNDETERMINED", "pattern_relation": "UNDETERMINED", "support_level": "PENDING",
            "matched_dimensions": [], "conflicting_dimensions": [], "unknown_dimensions": ["event", "mechanism", "trigger"],
            "evidence": [], "event_anchor": "", "short_reason": "待核验；离线模拟结果不能证明真实故障关联" if mode == "mock" else "正文不可用，待重新获取证据",
            "claim_support": {"symptom": "UNKNOWN", "root_cause": "UNKNOWN", "fix": "UNKNOWN", "verification": "UNKNOWN"},
            "missing_information": ["明确事件身份与机制证据"], "model_mode": mode, "model_id": model}


class MockJudge:
    """An explicit simulator, never a replacement for semantic verification."""
    model_mode = "mock"
    model_id = "offline-mock-v1"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def summarize(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        issues = []
        if _readable(snapshot):
            # Copy segments as observations; do not infer root cause or operator.
            for sid, text in _segments(snapshot).items():
                if text.strip():
                    issues.append({"label": "离线原文摘录，未做语义提取", "facts": [
                        {"field": "raw_observation", "value": text, "evidence": [{"segment_id": sid, "quote": text}]}]})
        return _validate_summary({"snapshot_id": snapshot["snapshot_id"], "issues": issues,
                                  "unknown_fields": ["operator", "mechanism", "trigger", "event_identity", "fix_verification"],
                                  "model_mode": self.model_mode, "model_id": self.model_id}, snapshot)

    def compare(self, case: dict[str, Any], snapshot: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
        summary = _validate_summary({k: summary[k] for k in EvidenceSummary.model_fields if k in summary}, snapshot)
        result = _pending(case, snapshot, self.model_mode, self.model_id)
        anchor = _case_event_anchor(case)
        if snapshot.get("is_synthetic") is True and re.fullmatch(r"DEMO-[A-Za-z0-9_-]+", anchor or "") and snapshot.get("status") == "COMPLETE" and _readable(snapshot):
            refs = [{"segment_id": sid, "quote": text} for sid, text in _segments(snapshot).items() if anchor in text]
            if refs:
                result.update(case_attribution="CONFIRMED", event_relation="SAME_EVENT", pattern_relation="UNDETERMINED",
                              support_level="DIRECT", matched_dimensions=["event_id"], evidence=refs, event_anchor=anchor,
                              unknown_dimensions=["mechanism", "trigger"], short_reason="仅合成演示：原始事件编号与合成正文锚点一致，未验证真实故障",
                              missing_information=["真实资料及语义核验"])
        return _validate_judgment(result, case, snapshot)

    def map_catalog(self, case: dict[str, Any], judgments: list[dict[str, Any]], items: list[dict[str, Any]]) -> dict[str, Any]:
        result = {"case_id": case["case_id"], "catalog_results": [{"item_id": item["item_id"], "result": "UNDETERMINED",
                  "reason": "离线模拟不执行真实故障库覆盖判断", "evidence": []} for item in items], "overall": "UNDETERMINED",
                  "scope": "FULL_CATALOG", "model_mode": self.model_mode, "model_id": self.model_id}
        return _validate_catalog(result, case, judgments, items)


def _json_loads(text: str) -> Any:
    def duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("duplicate JSON key")
            obj[key] = value
        return obj
    def invalid_number(_: str) -> Any:
        raise ValueError("non-finite JSON number")
    return json.loads(text, object_pairs_hook=duplicate_guard, parse_constant=invalid_number)



class PendingModelResult(ModelError):
    """A task awaits a result produced in the OpenCode environment."""

    def __init__(self, task_id: str = "", operation: str = "") -> None:
        super().__init__("等待OpenCode环境返回模型任务结果", "MODEL_RESULT_PENDING")
        self.task_id = task_id
        self.operation = operation


def validate_task_result(
    operation: str,
    result: dict[str, Any],
    *,
    snapshot: dict[str, Any] | None = None,
    case: dict[str, Any] | None = None,
    judgments: list[dict[str, Any]] | None = None,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate a returned semantic payload; transport envelopes live in bridge.

    The caller binds task ID, input hashes, provider/model metadata and run before
    invoking this function. Validation never executes a model or upgrades a
    proposal to a human-reviewed conclusion.
    """
    if not isinstance(result, dict):
        raise ModelError("模型任务结果必须是json对象", "invalid_response")
    if not all(isinstance(result.get(key), str) and result[key].strip() for key in ("model_mode", "model_id")):
        raise ModelError("模型任务结果缺少实际模型来源标识", "invalid_response")
    try:
        if operation in {"summarize", "summary"}:
            if snapshot is None:
                raise ModelError("资料摘要核验缺少snapshot上下文", "missing_context")
            return _validate_summary(result, snapshot)
        if operation in {"compare", "judgment"}:
            if case is None or snapshot is None:
                raise ModelError("故障关联核验缺少case或snapshot上下文", "missing_context")
            return _validate_judgment(result, case, snapshot)
        if operation in {"map_catalog", "catalog"}:
            if case is None or judgments is None or items is None:
                raise ModelError("故障库核验缺少case、judgments或items上下文", "missing_context")
            return _validate_catalog(result, case, judgments, items)
        raise ModelError("未知模型任务操作", "unknown_operation")
    except (ValidationError, ValueError, TypeError, KeyError) as exc:
        raise ModelError("模型任务结果JSON结构或schema校验失败", "invalid_response") from exc
