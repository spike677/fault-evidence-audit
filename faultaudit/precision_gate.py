"""Separate native format, non-API protocol design and hardware coverage gates."""
from __future__ import annotations

from collections import defaultdict
import html
import json
from pathlib import Path
import re

from .store import AuditError, digest, now
from .precision_contracts import BoundRules
from . import precision_bridge as bridge, precision_target as target, precision_native as native


def _warnings(results, non_api, *, diagnostic):
    outcomes = []
    for result in results:
        for warning in result["warnings"]:
            resolution = "UNRESOLVED_BLOCKING"
            prefix = "suite cases missing a primary trigger budget entry: "
            if warning.startswith(prefix):
                raw = warning[len(prefix):].split(",")
                if all(re.fullmatch(r"\s*\d+\s*", p) for p in raw) and {int(p) for p in raw} <= non_api:
                    resolution = "NON_API_DESIGN_PATH; NATIVE_EXECUTION_CAPABILITY_NOT_CONFIRMED"
            elif diagnostic and (re.fullmatch(r"rule count \d+ is not a complete count \[\d+\]", warning)
                    or re.fullmatch(r"submission count \d+ is not an allowed complete count: \[\d+\]", warning)
                    or re.fullmatch(r"coverage suite.expected_case_count=\d+ does not match submission count \d+", warning)):
                resolution = "DIAGNOSTIC_ONLY; NOT_FORMAL_SUITE_COMPLETION"
            outcomes.append({"checker": result["checker"], "warning": warning, "resolution": resolution})
    return outcomes


def _input_hashes(workspace, suite, atk_suite=None):
    files = {"suite": Path(suite), "library": Path(workspace) / "01_generate/report/trigger_library.md",
        "ledger": Path(workspace) / "01_generate/report/trigger_coverage.json"}
    if atk_suite is not None: files["atk_suite"] = Path(atk_suite)
    return {key: target.file_hash(path) if path.is_file() else None for key,path in files.items()}


def check(store, context_value, bound_value, workspace, *, suite=None, atk_suite=None,
          python=None, diagnostic=False, timeout=30):
    context = bridge.current_context(context_value, store)
    bound = bridge._parse(BoundRules, bound_value)
    if bound.bridge_policy_hash != bridge.policy_hash():
        raise AuditError("BRIDGE_POLICY_CHANGED: regenerate bindings without deleting old files")
    workspace = Path(workspace).resolve()
    suite = Path(suite) if suite else workspace / "01_generate/submission/test_suite.json"
    if suite.resolve() != (workspace / "01_generate/submission/test_suite.json").resolve():
        raise AuditError("Native verification must check the exact bound workspace test_suite.json")
    draft, works, non_api = bridge.validate_draft(context, bound.draft, suite)
    if works != bound.execution_work_ids:
        raise AuditError("Execution work IDs differ from the actual rules/protocols")
    target.verify_workspace(context, workspace)
    before = _input_hashes(workspace, suite, atk_suite)
    results, witness = native.validate_native(context, workspace, python=python, timeout=timeout)
    errors = []
    if any(not r["core_passed"] for r in results): errors.append("NATIVE_CHECK_FAILED_OR_DEPENDENCY_UNAVAILABLE")
    if not isinstance(witness, list) or len(witness) != len(draft.rules):
        errors.append("NATIVE_MATERIALIZATION_INCOMPLETE")
    target.verify_workspace(context, workspace)
    if before != _input_hashes(workspace, suite, atk_suite):
        errors.append("INPUT_CHANGED_DURING_CHECK")
    # A state/source change while an external checker was running cannot be hidden.
    bridge.current_context(context, store)
    warning_outcomes = _warnings(results, non_api, diagnostic=diagnostic)
    if any(w["resolution"] == "UNRESOLVED_BLOCKING" for w in warning_outcomes):
        errors.append("UNRESOLVED_NATIVE_WARNING")
    expected_count = context.target["task_config"].get("max_cases", 1000)
    if type(expected_count) is not int or expected_count < 1:
        errors.append("INVALID_NATIVE_CASE_BUDGET")
    elif len(draft.rules) != expected_count and not diagnostic:
        errors.append("FORMAL_CASE_BUDGET_NOT_MET")
    elif diagnostic and len(draft.rules) > expected_count:
        errors.append("DIAGNOSTIC_CASE_BUDGET_EXCEEDED")
    reviews = {str(b.case_id): b.semantic_review.status for b in draft.rules}
    semantic_pending = [k for k,v in reviews.items() if v != "CHECKED"]
    methods = sorted({p.method_id for b in draft.rules for p in b.protocols})
    materialized_matches = False
    if atk_suite is not None:
        materialized_matches = digest(target.read_json(atk_suite)) == digest(witness)
        if not materialized_matches: errors.append("ATK_JSON_DIFFERS_FROM_UPSTREAM_MATERIALIZATION")
    duplicate = defaultdict(list)
    for case_id, identity in works.items(): duplicate[identity].append(int(case_id))
    used_modes = {l.mode_id for b in draft.rules for l in b.mode_links}
    source_modes = [{k:m[k] for k in ("mode_id", "mode_name", "failure_mechanism", "validation_status", "evidence_index")}
        for m in context.modes if m["mode_id"] in used_modes]
    api_selected = {k for b in draft.rules for k in b.api_trigger_ids}
    v4_selected = {k for b in draft.rules for l in b.mode_links for k in l.v4_class_ids}
    construction_selected = {k for b in draft.rules for l in b.mode_links for k in l.v4_scenario_ids}
    api_taxonomy = context.api42.get("taxonomy", context.api42)
    condition_definitions = {"api42": [i for i in api_taxonomy["items"] if i["id"] in api_selected],
        "v4_classes": [i for i in (context.v4 or {}).get("items", []) if i["id"] in v4_selected],
        "v4_constructions": [i for i in (context.v4 or {}).get("constructions", []) if i["id"] in construction_selected]}
    ready = not errors and not semantic_pending
    native_status = ("BLOCKED" if errors else "NEEDS_SEMANTIC_FACTS" if semantic_pending else
        "PROTOCOL_DESIGN_ONLY" if methods else "DIAGNOSTIC_ONLY" if diagnostic else
        ("FORMAL_READY_WITH_NON_API_BINDING" if non_api else "FORMAL_READY") if materialized_matches else "MATERIALIZATION_CHECKED_FINAL_ARTIFACT_MISSING")
    report = {"schema_version": "cann_precision_check.v1", "checked_at": now(), "context_hash": context.context_hash,
        "binding_hash": bound.binding_hash, "bridge_policy_hash": bridge.policy_hash(), "purpose": context.purpose,
        "blind_evaluation": context.blind_evaluation, "actual_agent_context_isolation_attested": False,
        "baseline": context.baseline, "status": "BLOCKED" if errors else "NEEDS_FACTS" if semantic_pending else "DESIGN_READY",
        "native_suite_status": native_status, "delivery": "DIAGNOSTIC_SMOKE" if diagnostic else "FORMAL",
        "formal_suite_ready": ready and not diagnostic and not methods and materialized_matches,
        "rule_design_ready": ready, "semantic_review": {"kind": "AGENT_DECLARATION_WITH_VERIFIED_QUOTES_NOT_A_TRUTH_ORACLE", "case_status": reviews},
        "errors": errors, "semantic_pending_case_ids": semantic_pending, "warning_outcomes": warning_outcomes,
        "native_results": results, "inputs_sha256": before, "native_materialization_sha256": digest(witness) if witness is not None else None,
        "native_materialization_hash_kind": "CANONICAL_JSON_UNICODE_SHA256; distinct from raw file-byte hashes",
        "provided_atk_json_matches_materialization": materialized_matches, "code_only_accepted_design_case_ids": sorted(non_api),
        "execution_method_ids": methods, "execution_capability": "NOT_IMPLEMENTED_BY_BRIDGE", "device_execution": "NOT_RUN",
        "hardware_validated": False, "path_coverage": "NOT_VERIFIED", "mechanism_confirmation": "NOT_ESTABLISHED",
        "root_cause_or_event_confirmed": False, "automatic_adoption": False, "human_accept_created": False, "state_written": False,
        "mode_sources": source_modes, "selected_condition_definitions": condition_definitions,
        "attribution_semantics": "NEW_TEST_DESIGN_LINKS; NO_SAME_EVENT_OR_HISTORICAL_SAME_SCENARIO_INHERITANCE",
        "review_required": "CONFLICT" in reviews.values(),
        "statistics": {"unique_native_case_ids": len(draft.rules), "unique_input_spec_work_ids": len(duplicate),
            "mode_ids_with_rules": sorted({l.mode_id for b in draft.rules for l in b.mode_links}),
            "unbound_selected_mode_ids": sorted({m["mode_id"] for m in context.modes} - {l.mode_id for b in draft.rules for l in b.mode_links}),
            "duplicate_input_spec_groups": [ids for ids in duplicate.values() if len(ids)>1],
            "unit": "RULE_DESIGN_AND_INPUT_SPECIFICATION; NOT_MODE_OR_DEVICE_COVERAGE"},
        "binding_details": draft.model_dump(), "input_scope": context.input_scope}
    report["validation_id"] = "precision-check-" + digest(report)[:24]
    return report


def write_report(report, output, *, store=None, repo=None):
    output = target.protect_output(output, store=store, repo=repo)
    path = output / (report["validation_id"] + ".json")
    html_path = output / (report["validation_id"] + ".html")
    target.immutable_json(path, report)
    esc = lambda v: html.escape(str(v), quote=True)
    pre = lambda v: "<pre>" + esc(json.dumps(v, ensure_ascii=False, indent=2)) + "</pre>"
    content = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Precision Bridge 验收</title><style>body{font:15px/1.7 system-ui,sans-serif;background:#f5f7fa;color:#18314a;margin:0}main{max-width:1050px;margin:auto;padding:24px}section{background:white;border:1px solid #dae3eb;border-radius:8px;padding:20px;margin:16px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 ui-monospace,monospace}h1{font-size:26px}summary{cursor:pointer}</style></head><body><main>'
    content += '<h1>Precision Bridge · ' + esc(report["status"]) + '</h1><p>' + esc(report["purpose"]) + ' · ' + esc(report["native_suite_status"]) + '</p><p>设计、原生JSON就绪与实机验证分别记录。CODE-only及E1-E5设计通过不等于目标路径已命中。本工具没有执行NPU/GPU或创建人工ACCEPT。</p>'
    content += '<section><h2>CANN真实失效机理与来源</h2><p>以下是已有模式的原始声明及引用，不是本次新增的根因确认。新测试中的标签组合不继承历史资料的同一事件或同情景关系。</p>'
    if not report["mode_sources"]:
        content += '<p>盲测上下文没有导出已有模式知识。</p>'
    for mode in report["mode_sources"]:
        content += '<h3>' + esc(mode["mode_id"] + ' · ' + mode["mode_name"]) + '</h3><p>' + esc(mode["failure_mechanism"]["text"]) + '</p>' + pre(mode)
    content += '</section>'
    for title, value in (("门禁与缺口", {k:report[k] for k in ("errors","semantic_pending_case_ids","formal_suite_ready","rule_design_ready","execution_method_ids")}),
        ("计数口径",report["statistics"]), ("WARNING逐项处理（原文保留）",report["warning_outcomes"]),
        ("规则到模式、条件及执行规程的溯源",report["binding_details"]), ("所选条件的完整定义（各轴独立）",report["selected_condition_definitions"]),
        ("Baseline与输入身份",{k:report[k] for k in ("baseline","context_hash","binding_hash","inputs_sha256")}),
        ("原生校验器记录",report["native_results"])):
        content += '<section><h2>' + esc(title) + '</h2>' + pre(value) + '</section>'
    content += '<p>完整数据：<a href="' + esc(path.name) + '">' + esc(path.name) + '</a>。状态与历史保留；未执行结果不计实机覆盖。</p></main></body></html>'
    if html_path.exists() and html_path.read_text(encoding="utf-8") != content:
        raise AuditError("Existing validation HTML differs; retain the old report")
    if not html_path.exists():
        with html_path.open("x", encoding="utf-8", newline="\n") as stream: stream.write(content)
    return {"report_html": str(html_path), "report_json": str(path), "status": report["status"],
        "native_suite_status": report["native_suite_status"], "formal_suite_ready": report["formal_suite_ready"],
        "device_execution": "NOT_RUN", "state_written": False}
