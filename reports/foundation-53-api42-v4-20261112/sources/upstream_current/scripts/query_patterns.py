#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按显式模式命中闭包查询组合实验，并生成待验证的未知模式候选。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSITION_SCHEMA = "ascend-op-fault-patterns/compositions@1"
QUERY_SCHEMA = "ascend-op-fault-patterns/query@1"
UNKNOWN_SCHEMA = "ascend-op-fault-patterns/unknown-pattern@1"
ACTION_TYPES = frozenset({
    "GetWorkspaceSize", "Execute", "PoisonWorkspace", "ReuseWorkspace",
    "ReuseExecutor", "Free", "SwitchStream", "RecordEvent", "WaitEvent",
    "GraphCapture", "Replay",
})


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _validate_experiment(raw: Any, owner: str) -> None:
    if not isinstance(raw, Mapping):
        raise ValueError("%s.next_experiment 必须是 object" % owner)
    if raw.get("schema_version") != "deep-experiment/v1":
        raise ValueError("%s.next_experiment.schema_version 必须是 deep-experiment/v1" % owner)
    if not str(raw.get("experiment_id") or "").strip():
        raise ValueError("%s.next_experiment.experiment_id 不能为空" % owner)
    if not str(raw.get("operation") or "").strip():
        raise ValueError("%s.next_experiment.operation 不能为空" % owner)
    actions = raw.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("%s.next_experiment.actions 必须是非空数组" % owner)
    seen = set()
    for index, action in enumerate(actions):
        if not isinstance(action, Mapping):
            raise ValueError("%s action[%d] 必须是 object" % (owner, index))
        if action.get("type") not in ACTION_TYPES:
            raise ValueError("%s action[%d].type 不支持：%r" % (owner, index, action.get("type")))
        action_id = str(action.get("id") or "a%d" % index)
        if action_id in seen:
            raise ValueError("%s action id 重复：%s" % (owner, action_id))
        seen.add(action_id)
    for field in ("initial_state", "schedule", "oracle", "provenance"):
        if field in raw and not isinstance(raw[field], Mapping):
            raise ValueError("%s.next_experiment.%s 必须是 object" % (owner, field))
    if "observations" in raw and not isinstance(raw["observations"], list):
        raise ValueError("%s.next_experiment.observations 必须是数组" % owner)
    _canonical(raw)


def load_compositions(root: str = ROOT) -> List[Dict[str, Any]]:
    """读取并校验显式关系；关系不存在时不做任何文本推断。"""
    root = os.path.abspath(root)
    index = _load_json(os.path.join(root, "fault_patterns_index.json"))
    data = _load_json(os.path.join(root, "pattern_compositions.json"))
    if data.get("schema") != COMPOSITION_SCHEMA:
        raise ValueError("pattern_compositions.json schema 不正确")
    known = {p.get("id") for p in index.get("patterns", [])}
    compositions = data.get("compositions")
    if not isinstance(compositions, list):
        raise ValueError("compositions 必须是数组")
    ids = set()
    for item in compositions:
        if not isinstance(item, Mapping):
            raise ValueError("组合条目必须是 object")
        cid = str(item.get("id") or "").strip()
        if not cid or cid in ids:
            raise ValueError("组合 id 为空或重复：%r" % cid)
        ids.add(cid)
        members = item.get("members")
        if not isinstance(members, list) or len(members) < 2 or len(set(members)) != len(members):
            raise ValueError("%s.members 至少含两个不重复模式" % cid)
        unknown = [pid for pid in members if pid not in known]
        if unknown:
            raise ValueError("%s.members 含未知模式：%s" % (cid, unknown))
        if not str(item.get("rationale") or "").strip():
            raise ValueError("%s.rationale 不能为空" % cid)
        _validate_experiment(item.get("next_experiment"), cid)
    return copy.deepcopy(compositions)


def _normalize_hits(hit_pattern_ids: Iterable[str], known: set) -> List[str]:
    if isinstance(hit_pattern_ids, str):
        hit_pattern_ids = hit_pattern_ids.split(",")
    hits = {str(pid).strip().upper() for pid in hit_pattern_ids if str(pid).strip()}
    unknown = sorted(hits - known)
    if unknown:
        raise ValueError("未知模式编号：%s" % ", ".join(unknown))
    return sorted(hits)


def failure_fingerprint(failure: Mapping[str, Any]) -> str:
    """只对稳定失败语义取指纹，排除 trace、地址、时间戳与 shape。"""
    if not isinstance(failure, Mapping):
        raise ValueError("failure 必须是 object")
    explicit = failure.get("fingerprint")
    if explicit:
        return "explicit:" + str(explicit)
    stable = {key: copy.deepcopy(failure.get(key)) for key in (
        "operation", "oracle", "code", "actual_path", "signature",
    ) if failure.get(key) is not None}
    if not stable:
        raise ValueError("failure 至少需要 operation/oracle/code/actual_path/signature 之一")
    return "sha256:" + hashlib.sha256(_canonical(stable).encode("utf-8")).hexdigest()


def build_unknown_pattern_candidate(failure: Mapping[str, Any], *,
                                    trace_ref: Any = None,
                                    observed_oracle: Optional[str] = None) -> Dict[str, Any]:
    """生成回灌候选；它不修改索引，也不代表已确认的新模式事实。"""
    if not isinstance(failure, Mapping):
        raise ValueError("failure 必须是 object")
    if trace_ref is None:
        trace_ref = failure.get("trace_ref")
    if observed_oracle is None:
        observed_oracle = failure.get("observed_oracle") or failure.get("oracle")
    if trace_ref is None or (isinstance(trace_ref, str) and not trace_ref.strip()):
        raise ValueError("unknown-pattern 候选必须保留非空 trace_ref")
    if not str(observed_oracle or "").strip():
        raise ValueError("unknown-pattern 候选必须保留非空 observed_oracle")
    fingerprint = failure_fingerprint(failure)
    candidate_id = "UP-" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
    candidate = {
        "schema": UNKNOWN_SCHEMA,
        "id": candidate_id,
        "candidate_type": "unknown-pattern",
        "fingerprint": fingerprint,
        "trace_ref": copy.deepcopy(trace_ref),
        "observed_oracle": str(observed_oracle),
        "coverage_state": "designed",
        "status": "pending_verification",
        "is_pattern_fact": False,
    }
    _canonical(candidate)
    return candidate


def query_patterns(hit_pattern_ids: Iterable[str] = (), *, root: str = ROOT,
                   failure: Optional[Mapping[str, Any]] = None,
                   trace_ref: Any = None,
                   observed_oracle: Optional[str] = None) -> Dict[str, Any]:
    """仅返回 members 全部命中的组合；无命中且给失败时返回未知候选。"""
    root = os.path.abspath(root)
    index = _load_json(os.path.join(root, "fault_patterns_index.json"))
    known = {p.get("id") for p in index.get("patterns", [])}
    hits = set(_normalize_hits(hit_pattern_ids, known))
    matched = [item for item in load_compositions(root) if set(item["members"]).issubset(hits)]
    unknown = None
    if not hits and failure is not None:
        unknown = build_unknown_pattern_candidate(
            failure, trace_ref=trace_ref, observed_oracle=observed_oracle)
    result = {
        "schema": QUERY_SCHEMA,
        "hit_patterns": sorted(hits),
        "compositions": matched,
        "unknown_pattern_candidate": unknown,
    }
    _canonical(result)
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="故障模式组合与未知失败候选查询")
    parser.add_argument("--root", default=ROOT)
    parser.add_argument("--hits", default="", help="已确认命中的模式编号，逗号分隔；不读自由文本")
    parser.add_argument("--failure", default="", help="未匹配失败的 JSON object 文件")
    parser.add_argument("--trace-ref", default=None, help="失败 trace 引用；也可放在 failure.trace_ref")
    parser.add_argument("--observed-oracle", default=None,
                        help="实际观测 oracle；也可放在 failure.observed_oracle/oracle")
    parser.add_argument("--out", default="", help="可选：把查询 JSON 写入文件")
    args = parser.parse_args(argv)
    if not args.hits.strip() and not args.failure:
        parser.error("至少提供 --hits 或 --failure")
    try:
        failure = _load_json(args.failure) if args.failure else None
        if failure is not None and not isinstance(failure, Mapping):
            raise ValueError("--failure 文件必须包含 JSON object")
        result = query_patterns(args.hits, root=args.root, failure=failure,
                                trace_ref=args.trace_ref,
                                observed_oracle=args.observed_oracle)
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text + "\n")
        print(text)
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print("[query-patterns] %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
