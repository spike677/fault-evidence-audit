"""Portable audit exports. XLSX authoring is an optional separate Node step.

The JSON export retains all input evidence and rejected associations. TSV adds
an apostrophe to formula-like strings; the unmodified values remain in JSON.
"""

from __future__ import annotations

import csv
import html
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


COMPAT_COLUMNS = [
    "序号", "优先级组", "统一ID", "来源", "客户/模型", "问题描述", "算子", "根因",
    "wiki", "DTS", "PR", "库覆盖（98条）", "证据强度", "训练/推理/无法确定", "证据来源", "证据判断",
]
EXTRA_COLUMNS = ["case_id", "run_id", "根因来源", "缺口", "模型模式", "处理状态", "需人工", "处理原因",
                 "事件组", "证据路径", "未选引用数", "关联判断ID", "引文来源case_id", "来源分级", "已有用户确认",
                 "工作ID", "子问题范围", "必要引用数", "搜索目标已满足", "搜索控制", "搜索策略"]

_ALIASES = {
    "序号": ("sequence", "display_id"),
    "优先级组": ("priority", "source_priority"),
    "统一ID": ("external_id", "source_id", "legacy_id"),
    "来源": ("source", "source_label", "source_file"),
    "客户/模型": ("customer_model", "customer_or_model", "model"),
    "问题描述": ("description", "description_raw", "source_description_raw"),
    "算子": ("operator_raw", "source_operator_raw", "operator", "operators"),
    # Deliberately exclude normalized/model-generated root causes.
    "根因": ("root_cause_raw", "source_root_cause_raw", "original_root_cause"),
    "wiki": ("wiki_urls", "source_wiki_urls"),
    "DTS": ("dts_urls", "source_dts_urls"),
    "PR": ("pr_urls", "source_pr_urls"),
    "库覆盖（98条）": ("catalog_mapping_raw", "source_catalog_mapping_raw"),
    "证据强度": ("evidence_strength_raw", "support_level"),
    "训练/推理/无法确定": ("phase_raw", "source_training_inference_raw", "phase"),
    "证据来源": ("evidence_source_raw",),
    "证据判断": ("evidence_judgment_raw",),
}

_TABLES = [
    ("原始记录", "cases"), ("引用来历", "references"), ("资料快照", "snapshots"),
    ("资料摘要", "summaries"), ("关联判断", "judgments"), ("故障库", "catalog"),
    ("库映射", "mappings"), ("任务台账", "tasks"), ("人工复核", "review_events"),
    ("证据反查", "evidence_index"), ("库选择基准", "catalog_selections"),
    ("事件组成员", "event_groups"),
    ("资料关联确认", "evidence_associations"),
]

_DONE_TASK_STATES = {"COMPLETE", "COMPLETED", "SUCCEEDED", "DONE", "SUCCESS", "SKIPPED", "STALE", "UNUSED"}


def _flat(record: Any) -> dict:
    if not isinstance(record, dict):
        return {"value": record}
    payload = record.get("payload")
    return {**(payload if isinstance(payload, dict) else {}), **record}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    return str(value)


def _scalar(value: Any) -> Any:
    return value if value is None or isinstance(value, (str, int, float, bool)) else _text(value)


def _raw_case(case: dict) -> dict:
    for key in ("raw", "raw_values", "source_values", "raw_cells", "original"):
        if isinstance(case.get(key), dict):
            return case[key]
    return {}


def _get_original(case: dict, raw: dict, column: str) -> Any:
    # An explicit blank original value stays blank, including the root cause.
    for container in (raw, case):
        if column in container:
            value = container[column]
            return value.get("value") if isinstance(value, dict) and "value" in value else value
    for name in _ALIASES[column]:
        if name in case:
            return case[name]
        if name in raw:
            return raw[name]
    return ""


def _records(data: dict, key: str) -> list[dict]:
    return [_flat(record) for record in data.get(key, [])]


def _case_id(record: dict) -> str:
    return _text(record.get("case_id", record.get("source_case_id", "")))


def _involves_case(record: dict, case_id: str) -> bool:
    members = record.get("member_case_ids")
    return bool(case_id) and (_case_id(record) == case_id or isinstance(members, list) and case_id in members)


def _review_status(record: dict) -> str:
    return _text(record.get("review_status", "NEEDS_REVIEW")).upper()


def _required(record: dict, tasks: dict | None = None) -> bool:
    if record.get("required") is False:
        return False
    task = (tasks or {}).get(record.get("task_id"), {})
    return task.get("required") is not False


def _needs_attention(task: dict) -> bool:
    return _required(task) and _text(task.get("status", "")).upper() not in _DONE_TASK_STATES


def _decision_suffix(record: dict) -> str:
    if _review_status(record) == "ACCEPT":
        return ""
    status = record.get("processing_status")
    if status == "AUTO_PROCESSED" and record.get("review_required") is False:
        return "（自动处理）"
    if status == "EXCEPTION":
        return "（异常，需人工）"
    if status == "PENDING":
        return "（证据不足，Agent待完善）"
    return ""


def _support_label(judgment: dict) -> str:
    level = _text(judgment.get("support_level", "UNDETERMINED"))
    suffix = _decision_suffix(judgment)
    if suffix:
        return level + suffix
    positive = level.upper() in {"DIRECT", "CONFIRMED"} or judgment.get("case_attribution") == "CONFIRMED"
    if positive and _review_status(judgment) != "ACCEPT":
        return level + "（模型建议，待复核）"
    return level


def _mapping_label(mapping: dict) -> str:
    result = _text(mapping.get("overall", mapping.get("coverage", mapping.get("result", mapping.get("status", "UNDETERMINED")))))
    suffix = _decision_suffix(mapping)
    if suffix:
        return result + suffix
    if result.upper() in {"COVERED", "PARTIALLY_COVERED", "已覆盖", "部分覆盖"} and _review_status(mapping) != "ACCEPT":
        return result + "（模型建议，待复核）"
    return result


def _case_plans(data: dict) -> dict[str, dict]:
    plans = data.get("evidence_plans")
    entries = plans.get("cases", []) if isinstance(plans, dict) else []
    return {_case_id(entry): entry for entry in entries if isinstance(entry, dict) and _case_id(entry)}


def _source_grade(record: dict) -> str:
    relation = record.get("source_relation")
    if isinstance(relation, dict):
        return _text(relation.get("relation", "UNCLASSIFIED"))
    return _text(record.get("source_grade", relation or "UNCLASSIFIED"))


def _work_metadata(record: dict) -> dict:
    context = record.get("processing_context")
    context = context if isinstance(context, dict) else {}
    return {"work_id": record.get("work_id", context.get("work_id")),
            "issue_scope": record.get("issue_scope", context.get("issue_scope", context.get("applicable_issue"))),
            "source_grades": record.get("source_grades", context.get("source_grades", [])),
            "user_confirmed": record.get("user_confirmed", context.get("user_confirmed"))}


def _reference_rows(data: dict) -> list[dict]:
    plans = _case_plans(data)
    rows = []
    for record in _records(data, "references"):
        record = {**record, "source_grade": _source_grade(record), "user_confirmed": record.get("user_confirmed")}
        plan = plans.get(_case_id(record))
        if plan is not None:
            selected = record.get("ref_id") in set(plan.get("selected_ref_ids", []))
            record = {**record, "required": selected, "plan_group_id": plan.get("group_id", ""),
                      "plan_path": plan.get("path", "")}
        rows.append(record)
    return rows


def _reference_audit_rows(data: dict) -> list[dict]:
    """Display every reference; shared content/results are linked, never counted here."""
    snapshots = _records(data, "snapshots")
    summaries = _records(data, "summaries")
    judgments = _records(data, "judgments")
    rows = []
    for reference in _reference_rows(data):
        base = {key: reference.get(key) for key in ("ref_id", "case_id", "url", "origin", "location", "source_grade", "user_confirmed", "required")}
        matched = [snapshot for snapshot in snapshots if reference.get("url") and snapshot.get("url") == reference["url"]]
        if not matched:
            rows.append({**base, "capture_status": "NOT_FETCHED", "summary_status": "NO_SUMMARY", "judgment_status": "NO_JUDGMENT"})
        for snapshot in matched:
            sid = snapshot.get("snapshot_id")
            snapshot_summaries = [summary for summary in summaries if summary.get("snapshot_id") == sid and not summary.get("is_stale")]
            related = [judgment for judgment in judgments if judgment.get("snapshot_id") == sid and _involves_case(judgment, _case_id(reference))]
            detail = {**base, "snapshot_id": sid, "snapshot_is_stale": snapshot.get("is_stale"),
                      "capture_status": snapshot.get("status", snapshot.get("retrieval_status", "UNKNOWN")),
                      "summary_status": "AVAILABLE" if snapshot_summaries else "NO_CURRENT_SUMMARY",
                      "summary_task_ids": [summary.get("task_id") for summary in snapshot_summaries],
                      "summary_issues": [issue for summary in snapshot_summaries for issue in summary.get("issues", [])]}
            if not related:
                rows.append({**detail, "judgment_status": "NO_JUDGMENT"})
            for judgment in related:
                work = _work_metadata(judgment)
                context = judgment.get("processing_context") or {}
                judgment_ref_ids = context.get("selected_ref_ids") if isinstance(context, dict) else None
                rows.append({**detail, "work_id": work["work_id"], "issue_scope": work["issue_scope"],
                             "work_source_grades": work["source_grades"], "work_user_confirmed": work["user_confirmed"],
                             "judgment_ref_ids": judgment_ref_ids,
                             "reference_used_by_judgment": reference.get("ref_id") in judgment_ref_ids if isinstance(judgment_ref_ids, list) else None,
                             "judgment_id": judgment.get("judgment_id"),
                             "source_case_id": _case_id(judgment), "judgment_is_stale": judgment.get("is_stale"),
                             "judgment_required": judgment.get("required"), "processing_status": judgment.get("processing_status"),
                             "review_status": judgment.get("review_status"), "applicable_issue": judgment.get("applicable_issue"),
                             "short_reason": judgment.get("short_reason"), "evidence": judgment.get("evidence", []),
                             "judgment_status": "HISTORY" if judgment.get("is_stale") else "AVAILABLE"})
    return rows


def _summary_issue_rows(data: dict) -> list[dict]:
    return [{"snapshot_id": summary.get("snapshot_id"), "summary_task_id": summary.get("task_id"),
             "is_stale": summary.get("is_stale"), "issue_label": issue.get("label"), "facts": issue.get("facts", [])}
            for summary in _records(data, "summaries") for issue in summary.get("issues", []) if isinstance(issue, dict)]


def _case_processing(records: list[dict], pending: list[dict]) -> tuple[str, str, str]:
    reasons = []
    for record in records:
        value = record.get("review_reasons", [])
        reasons.extend(value if isinstance(value, list) else [value] if value else [])
    statuses = {record.get("processing_status") for record in records}
    if "EXCEPTION" in statuses:
        return "EXCEPTION", "是", "；".join(dict.fromkeys(_text(value) for value in reasons))
    if "PENDING" in statuses or pending or not records:
        return "PENDING", "否", "；".join(dict.fromkeys(_text(value) for value in reasons))
    if statuses == {"AUTO_PROCESSED"} and all(record.get("review_required") is False for record in records):
        return "AUTO_PROCESSED", "否", "；".join(dict.fromkeys(_text(value) for value in reasons))
    return "LEGACY_REVIEW", "是" if any(_review_status(r) not in {"ACCEPT", "REJECT"} for r in records) else "否", "；".join(dict.fromkeys(_text(value) for value in reasons))


def _summary_rows(data: dict) -> list[dict]:
    run = _flat(data.get("run", {}))
    run_id = run.get("run_id", run.get("id", ""))
    judgments = _records(data, "judgments")
    references = _reference_rows(data)
    tasks = _records(data, "tasks")
    tasks_by_id = {task.get("task_id"): task for task in tasks}
    plans = _case_plans(data)
    rows = []
    for source in _records(data, "cases"):
        raw = _raw_case(source)
        identity = _case_id(source)
        all_related = [j for j in judgments if _involves_case(j, identity)]
        necessary_related = [j for j in all_related if _required(j, tasks_by_id)]
        related = [j for j in necessary_related if not j.get("is_stale")]
        supporting = [j for j in related if _review_status(j) != "REJECT"]
        refs = [r for r in references if _case_id(r) == identity and identity]
        pending = [t for t in tasks if _involves_case(t, identity) and _needs_attention(t)]
        row = {column: _scalar(_get_original(source, raw, column)) for column in COMPAT_COLUMNS}
        # Legacy aggregate judgments are inputs, never current verified results.
        row["证据强度"] = "待核验"
        row["证据判断"] = "待核验：尚无本轮关联判断"
        row["库覆盖（98条）"] = "待核验"
        row["证据来源"] = "待核验：引用来源尚未登记"
        if necessary_related and not related:
            row["证据判断"] = "待重算：仅有过期关联判断"
        elif all_related and not related:
            row["证据判断"] = "未选关联留档，当前不作为必要证据"
        if related:
            if supporting:
                row["证据强度"] = "；".join(dict.fromkeys(_support_label(j) for j in supporting))
            else:
                row["证据强度"] = "待核验：仅有已拒绝关联"
            reasons = []
            for judgment in related:
                reason = judgment.get("short_reason", judgment.get("reasoning_summary", judgment.get("conclusion", "")))
                if reason in (None, ""):
                    continue
                status = _review_status(judgment)
                if status == "REJECT":
                    reason = "已拒绝关联：" + _text(reason)
                elif judgment.get("processing_status") == "AUTO_PROCESSED" and judgment.get("review_required") is False:
                    reason = "自动处理：" + _text(reason)
                elif judgment.get("processing_status") == "EXCEPTION":
                    reason = "异常，需人工：" + _text(reason)
                elif judgment.get("processing_status") == "PENDING":
                    reason = "证据不足，Agent待完善：" + _text(reason)
                elif status != "ACCEPT" and (judgment.get("support_level") == "DIRECT" or judgment.get("case_attribution") == "CONFIRMED"):
                    reason = "模型建议，待复核：" + _text(reason)
                work = _work_metadata(judgment)
                if work["work_id"]:
                    reason = f"[{work['work_id']}；{_text(work['issue_scope'])}] " + _text(reason)
                reasons.append(reason)
            if reasons:
                row["证据判断"] = "\n".join(_text(reason) for reason in reasons)
        mappings = [m for m in _records(data, "mappings") if _involves_case(m, identity)
                    and not m.get("is_stale") and _required(m, tasks_by_id) and _review_status(m) != "REJECT"]
        if mappings:
            row["库覆盖（98条）"] = "；".join(dict.fromkeys(_mapping_label(m) for m in mappings))
        if refs:
            origins = Counter(_text(r.get("discovery_method", r.get("origin", r.get("discovered_from", "UNKNOWN")))) for r in refs)
            row["证据来源"] = "；".join(f"{origin}: {count}" for origin, count in sorted(origins.items()))
        missing = []
        if len(necessary_related) != len(related):
            missing.append("存在过期关联判断，已从当前结论排除")
        for value in [source.get("missing_information", []), source.get("gaps", [])]:
            missing.extend(value if isinstance(value, list) else [value] if value else [])
        for judgment in related:
            value = judgment.get("missing_information", judgment.get("unknown_dimensions", []))
            missing.extend(value if isinstance(value, list) else [value] if value else [])
        missing.extend(f"任务 {t.get('task_id', t.get('id', ''))}: {t.get('status', 'UNKNOWN')} {_text(t.get('error', ''))}" for t in pending)
        modes = sorted({_text(j.get("model_mode", j.get("mode", "UNKNOWN"))) for j in related})
        plan = plans.get(identity, {})
        processing, human, processing_reasons = _case_processing(related + mappings, pending)
        if plan.get("path") == "EXCEPTION":
            processing, human = "EXCEPTION", "是"
            processing_reasons = "；".join(value for value in (processing_reasons, _text(plan.get("issues") or plan.get("stop_reason"))) if value)
        search_control = plan.get("search_control") or {}
        row.update({
            "case_id": identity,
            "run_id": source.get("run_id", run_id),
            "根因来源": source.get("root_cause_origin", source.get("root_cause_provenance", "LEGACY_DERIVED_UNKNOWN")),
            "缺口": "；".join(dict.fromkeys(_text(x) for x in missing if x not in (None, ""))),
            "模型模式": "；".join(modes) if modes else run.get("model_mode", run.get("mode", "NOT_RUN")),
            "处理状态": processing, "需人工": human, "处理原因": processing_reasons,
            "事件组": plan.get("group_id", source.get("group_id", "")), "证据路径": plan.get("path", ""),
            "未选引用数": sum(ref.get("required") is False for ref in refs) if identity in plans else None,
            "关联判断ID": "；".join(dict.fromkeys(_text(j.get("judgment_id")) for j in related)),
            "引文来源case_id": "；".join(dict.fromkeys(_case_id(j) for j in related)),
            "来源分级": "；".join(sorted({_source_grade(ref) for ref in refs} | set(plan.get("source_grades", [])))),
            "已有用户确认": plan.get("user_confirmed"),
            "工作ID": "；".join(dict.fromkeys(_text(_work_metadata(j)["work_id"]) for j in related if _work_metadata(j)["work_id"])),
            "子问题范围": [_work_metadata(j) for j in related],
            "必要引用数": sum(ref.get("required") is True for ref in refs) if identity in plans else None,
            "搜索目标已满足": search_control.get("satisfied"), "搜索控制": search_control,
            "搜索策略": search_control.get("policy", (data.get("evidence_plans") or {}).get("search_policy")),
        })
        rows.append(row)
    return rows


def _fact_comparison_rows(data: dict) -> list[dict]:
    rows = []
    for judgment in _records(data, "judgments"):
        for fact in judgment.get("fact_comparisons", []):
            if not isinstance(fact, dict):
                continue
            rows.append({"source_case_id": _case_id(judgment), "member_case_ids": judgment.get("member_case_ids", []),
                "source_scope": "引文与单元格属于source_case_id；事件组成员不改写该原文来源",
                "judgment_id": judgment.get("judgment_id"),
                **_work_metadata(judgment),
                "snapshot_id": judgment.get("snapshot_id"), "required": judgment.get("required"),
                "is_stale": judgment.get("is_stale"), "processing_status": judgment.get("processing_status"),
                **{key: fact.get(key) for key in ("category", "source_field", "source_cell", "source_quote", "source_value",
                    "source_meaning", "evidence_value", "evidence_meaning", "relation", "reason", "evidence")},
                "applicable_issue": judgment.get("applicable_issue")})
    return rows


def _event_conclusion_rows(data: dict, summaries: list[dict]) -> list[dict]:
    cases = {_case_id(case): case for case in _records(data, "cases")}
    display = {row["case_id"]: row for row in summaries}
    plans = _case_plans(data)
    tasks = {task.get("task_id"): task for task in _records(data, "tasks")}
    judgments = _records(data, "judgments")
    rows = []
    for conclusion in _records(data, "event_conclusions"):
        members = conclusion.get("case_ids", [])
        selected_refs = sorted({ref_id for case_id in members for ref_id in plans.get(case_id, {}).get("selected_ref_ids", [])})
        selected_snapshots = sorted({snapshot_id for case_id in members for snapshot_id in plans.get(case_id, {}).get("selected_snapshot_ids", [])})
        selected_judgments = [j for j in judgments if _required(j, tasks) and not j.get("is_stale")
                              and any(_involves_case(j, case_id) for case_id in members)]
        conclusions = [{"judgment_id": j.get("judgment_id"), "source_case_id": _case_id(j),
                        **_work_metadata(j),
                        "member_case_ids": j.get("member_case_ids", [_case_id(j)]), "snapshot_id": j.get("snapshot_id"),
                        "applicable_issue": j.get("applicable_issue"), "short_reason": j.get("short_reason", ""),
                        "processing_status": j.get("processing_status"), "review_status": j.get("review_status"),
                        "conflicting_dimensions": j.get("conflicting_dimensions", []), "evidence": j.get("evidence", [])}
                       for j in selected_judgments]
        processing = [{"case_id": case_id, "processing_status": display.get(case_id, {}).get("处理状态", "PENDING"),
                       "review_required": display.get(case_id, {}).get("需人工", ""),
                       "reason": display.get(case_id, {}).get("处理原因", "")} for case_id in members]
        statuses = {member["processing_status"] for member in processing}
        conflicts = conclusion.get("conflicts", [])
        if conflicts or "EXCEPTION" in statuses:
            summary = "事件组存在冲突或异常，需人工处理；各成员记录分别保留。"
        elif not members or "PENDING" in statuses:
            summary = "事件组选定资料尚待补充或处理。"
        elif statuses == {"AUTO_PROCESSED"}:
            summary = "事件组选定资料已自动处理，保留各成员独立记录。"
        else:
            summary = "事件组选定资料已汇集，成员结论按各自状态保留。"
        roots = [{"case_id": case_id, "source_root_cause": _get_original(cases.get(case_id, {}), _raw_case(cases.get(case_id, {})), "根因")}
                 for case_id in members]
        different_roots = len({_text(value["source_root_cause"]).strip() for value in roots if _text(value["source_root_cause"]).strip()}) > 1
        rows.append({**conclusion, "事件组处理摘要": conclusion.get("summary", summary), "selected_ref_ids": selected_refs,
                     "selected_snapshot_ids": selected_snapshots, "事件组事实结论": conclusions,
                     "成员根因原文是否不同": different_roots,
                     "根因原文差异说明": "成员根因原文不同；保留各自技术输入和判断，不由组身份认定同一根因。" if different_roots else "",
                     "成员根因原文": roots, "成员处理": processing})
    return rows


def _table(name: str, rows: list[dict], columns: list[str] | None = None) -> dict:
    if columns is None:
        columns = list(dict.fromkeys(key for row in rows for key in row))
    columns = columns or ["记录"]
    return {"name": name, "columns": columns,
            "rows": [[_scalar(row.get(column)) for column in columns] for row in rows]}


def _safe_tsv_value(value: Any) -> Any:
    if not isinstance(value, str):
        return "" if value is None else value
    # Whitespace/BOM can be ignored by spreadsheet programs before formula detection.
    if value.lstrip("\ufeff \t\r\n\v\f").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _tsv(table: dict) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([_safe_tsv_value(column) for column in table["columns"]])
    for row in table["rows"]:
        writer.writerow([_safe_tsv_value(value) for value in row])
    return output.getvalue()


def _html_value(value: Any) -> str:
    value = _text(value)
    if value and not any(ord(char) < 32 for char in value):
        try:
            parsed = urlsplit(value)
        except ValueError:
            parsed = None
        if parsed and parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
            escaped = html.escape(value, quote=True)
            return f'<a href="{escaped}" target="_blank" rel="noopener noreferrer">{escaped}</a>'
    return html.escape(value, quote=True)


def _html_report(data: dict, tables: list[dict]) -> str:
    run = _flat(data.get("run", {}))
    identity = _text(run.get("run_id", run.get("id", "")))
    validation = data.get("validation", {})
    status = _text(validation.get("batch_status", validation.get("status", run.get("status", "UNKNOWN"))))
    nav = " ".join(f'<a href="#table-{i}">{html.escape(table["name"])}</a>' for i, table in enumerate(tables))
    sections = []
    for i, table in enumerate(tables):
        head = "".join(f"<th scope=\"col\">{html.escape(str(column))}</th>" for column in table["columns"])
        body = "".join("<tr>" + "".join(f"<td>{_html_value(value)}</td>" for value in row) + "</tr>" for row in table["rows"])
        if not body:
            body = f'<tr><td colspan="{len(table["columns"])}">无记录</td></tr>'
        sections.append(f'<section id="table-{i}"><h2>{html.escape(table["name"])} <small>{len(table["rows"])} 条</small></h2><div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></section>')
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>故障证据核验报告 {html.escape(identity)}</title>
<style>body{{font-family:system-ui,'Microsoft YaHei',sans-serif;margin:24px;color:#172b4d;background:#f7f9fc}}h1{{font-size:24px}}h2{{font-size:18px}}nav{{line-height:2.2;position:sticky;top:0;background:#fff;padding:8px}}nav a{{margin-right:16px}}section{{margin:28px 0}}.scroll{{overflow:auto;background:#fff;border:1px solid #dae1e9}}table{{border-collapse:collapse;min-width:100%;font-size:13px}}th{{position:sticky;top:0;background:#223f62;color:white;text-align:left;white-space:nowrap}}td,th{{padding:9px 12px;border-bottom:1px solid #e4e9ef;vertical-align:top}}td{{min-width:100px;max-width:560px;white-space:pre-wrap;overflow-wrap:anywhere}}tbody tr:nth-child(even){{background:#f5f7fa}}small{{font-size:12px;font-weight:normal}}a{{color:#1550a1}}.meta{{line-height:1.8}}</style></head>
<body><h1>故障证据核验报告</h1><p class="meta">运行：{html.escape(identity)}<br>状态：{html.escape(status)}<br>正常 AUTO_PROCESSED 为自动处理；PENDING 由 Agent 补充；EXCEPTION 需人工处理。自动处理不会写成人工 ACCEPT。<br>根因列保留原始值。来源等级与用户确认分别展示，旧表引用不升级为周报原链。已有引用逐项列出，多子问题按 work_id 分开；逐引用表可能重复展示共享结果，不作为判断数量。未选引用、拒绝关联及历史任务保留明细；待办只列必要任务。</p><nav>{nav}</nav>{''.join(sections)}</body></html>'''


def _write(path: Path, content: str, encoding: str = "utf-8") -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding=encoding)
    temporary.replace(path)


def _statistics_rows(statistics: dict) -> list[dict]:
    """Small count/definition table; ID-level reconciliation stays in JSON."""
    current = statistics.get("current", {})
    rows = [{"范围": "current", "指标": key, "值": current.get(key)}
            for key in ("status", "snapshot_count", "selected_snapshot_count", "planned_work_count", "current_work_count",
                        "current_case_snapshot_pair_count", "mapping_count", "unused_reference_count",
                        "required_reference_count", "event_group_count", "auto_processed_count", "human_exception_count",
                        "pending_human_exception_count", "agent_pending_count", "search_goal_satisfied_case_count",
                        "search_goal_unsatisfied_case_count",
                        "mapping_auto_processed_count", "mapping_human_exception_count", "mapping_agent_pending_count")]
    for scope in ("including_rejected", "excluding_rejected", "rejected", "confirmed_accepted"):
        for key, value in (current.get(scope) or {}).items():
            rows.append({"范围": "current/" + scope, "指标": key, "值": value})
    for axis, categories in (current.get("classifications") or {}).items():
        for category, counts in categories.items():
            rows.append({"范围": "current/" + axis, "指标": category, "值": counts})
    for name in ("processing", "mapping_processing"):
        for status, counts in (current.get(name) or {}).items():
            rows.append({"范围": "current/" + name, "指标": status, "值": counts})
    for key, value in statistics.get("round", {}).items():
        if key in {"status", "reason"} or key.endswith("_count"):
            rows.append({"范围": "round", "指标": key, "值": value})
    for key, value in statistics.get("definitions", {}).items():
        rows.append({"范围": "口径", "指标": key, "值": value})
    if statistics.get("errors"):
        rows.append({"范围": "对账", "指标": "errors", "值": statistics["errors"]})
    return rows


def export_report(data: dict, output_dir: Path) -> dict:
    """Write JSON, HTML, all TSV tables and workbook_data without Node imports.

    Return absolute paths. ``workbook_data`` is consumed by the optional
    ``scripts/export_xlsx.mjs`` builder; no XLSX is claimed by this function.
    """
    if not isinstance(data, dict):
        raise TypeError("report data must be a dictionary")
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_rows = _summary_rows(data)
    tables = [_table("汇总", summary_rows, COMPAT_COLUMNS + EXTRA_COLUMNS),
              _table("事件组结论", _event_conclusion_rows(data, summary_rows)),
              _table("事实对照", _fact_comparison_rows(data)),
              _table("逐引用整理", _reference_audit_rows(data)),
              _table("逐资料子问题", _summary_issue_rows(data))]
    tables.extend(_table(name, _reference_rows(data) if key == "references" else _records(data, key)) for name, key in _TABLES)
    plans = data.get("evidence_plans")
    if isinstance(plans, dict):
        tables.append(_table("证据计划", [_flat(value) for value in plans.get("cases", [])]))
        tables.append(_table("搜索控制", [{"case_id": value.get("case_id"), "path": value.get("path"),
            **value["search_control"]} for value in plans.get("cases", []) if isinstance(value.get("search_control"), dict)]))
        tables.append(_table("必要工作项", [_flat(value) for value in plans.get("work_items", [])]))
        tables.append(_table("未选引用留档", [ref for ref in _reference_rows(data) if ref.get("required") is False]))
    for name, key in (("源文档", "documents"), ("排除记录", "exclusions")):
        if data.get(key):
            tables.append(_table(name, _records(data, key)))
    failed = [record for record in _records(data, "tasks") if _needs_attention(record)]
    tables.append(_table("失败与待办", failed))
    validation = data.get("validation", {})
    tables.append(_table("运行对账", [{"类别": "run", **_flat(data.get("run", {}))},
                                   {"类别": "validation", **(validation if isinstance(validation, dict) else {"value": validation})}]))
    statistics = data.get("statistics")
    if isinstance(statistics, dict):
        tables.append(_table("统计口径", _statistics_rows(statistics)))
    files = {
        "report_json": str(output_dir / "report.json"),
        "report_html": str(output_dir / "report.html"),
        "summary_tsv": str(output_dir / "summary.tsv"),
        "workbook_data": str(output_dir / "workbook_data.json"),
    }
    if isinstance(statistics, dict):
        files["statistics_json"] = str(output_dir / "statistics.json")
        _write(Path(files["statistics_json"]), json.dumps(statistics, ensure_ascii=False, indent=2) + "\n")
    _write(Path(files["report_json"]), json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n")
    _write(Path(files["report_html"]), _html_report(data, tables))
    _write(Path(files["summary_tsv"]), _tsv(tables[0]), "utf-8-sig")
    workbook = {"schema_version": "1.0", "run": data.get("run", {}),
                "source_report": "report.json", "sheets": tables}
    _write(Path(files["workbook_data"]), json.dumps(workbook, ensure_ascii=False, indent=2, default=str) + "\n")
    for index, table in enumerate(tables[1:], start=1):
        _write(output_dir / f"{index:02d}_{table['name']}.tsv", _tsv(table), "utf-8-sig")
    return files
