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
EXTRA_COLUMNS = ["case_id", "run_id", "根因来源", "缺口", "模型模式"]

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
]


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


def _review_status(record: dict) -> str:
    return _text(record.get("review_status", "NEEDS_REVIEW")).upper()


def _support_label(judgment: dict) -> str:
    level = _text(judgment.get("support_level", "UNDETERMINED"))
    positive = level.upper() in {"DIRECT", "CONFIRMED"} or judgment.get("case_attribution") == "CONFIRMED"
    if positive and _review_status(judgment) != "ACCEPT":
        return level + "（模型建议，待复核）"
    return level


def _mapping_label(mapping: dict) -> str:
    result = _text(mapping.get("overall", mapping.get("coverage", mapping.get("result", mapping.get("status", "UNDETERMINED")))))
    if result.upper() in {"COVERED", "PARTIALLY_COVERED", "已覆盖", "部分覆盖"} and _review_status(mapping) != "ACCEPT":
        return result + "（模型建议，待复核）"
    return result


def _summary_rows(data: dict) -> list[dict]:
    run = _flat(data.get("run", {}))
    run_id = run.get("run_id", run.get("id", ""))
    judgments = _records(data, "judgments")
    references = _records(data, "references")
    tasks = _records(data, "tasks")
    rows = []
    for source in _records(data, "cases"):
        raw = _raw_case(source)
        identity = _case_id(source)
        all_related = [j for j in judgments if _case_id(j) == identity and identity]
        related = [j for j in all_related if not j.get("is_stale")]
        supporting = [j for j in related if _review_status(j) != "REJECT"]
        refs = [r for r in references if _case_id(r) == identity and identity]
        pending = [t for t in tasks if _case_id(t) == identity and identity and
                   _text(t.get("status", "")).upper() not in {"COMPLETE", "COMPLETED", "SUCCEEDED", "DONE", "SUCCESS", "SKIPPED"}]
        row = {column: _scalar(_get_original(source, raw, column)) for column in COMPAT_COLUMNS}
        # Legacy aggregate judgments are inputs, never current verified results.
        row["证据强度"] = "待核验"
        row["证据判断"] = "待核验：尚无本轮关联判断"
        row["库覆盖（98条）"] = "待核验"
        row["证据来源"] = "待核验：引用来源尚未登记"
        if all_related and not related:
            row["证据判断"] = "待重算：仅有过期关联判断"
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
                elif status != "ACCEPT" and (judgment.get("support_level") == "DIRECT" or judgment.get("case_attribution") == "CONFIRMED"):
                    reason = "模型建议，待复核：" + _text(reason)
                reasons.append(reason)
            if reasons:
                row["证据判断"] = "\n".join(_text(reason) for reason in reasons)
        mappings = [m for m in _records(data, "mappings") if _case_id(m) == identity and identity
                    and not m.get("is_stale") and _review_status(m) != "REJECT"]
        if mappings:
            row["库覆盖（98条）"] = "；".join(dict.fromkeys(_mapping_label(m) for m in mappings))
        if refs:
            origins = Counter(_text(r.get("discovery_method", r.get("origin", r.get("discovered_from", "UNKNOWN")))) for r in refs)
            row["证据来源"] = "；".join(f"{origin}: {count}" for origin, count in sorted(origins.items()))
        missing = []
        if len(all_related) != len(related):
            missing.append("存在过期关联判断，已从当前结论排除")
        for value in [source.get("missing_information", []), source.get("gaps", [])]:
            missing.extend(value if isinstance(value, list) else [value] if value else [])
        for judgment in related:
            value = judgment.get("missing_information", judgment.get("unknown_dimensions", []))
            missing.extend(value if isinstance(value, list) else [value] if value else [])
        missing.extend(f"任务 {t.get('task_id', t.get('id', ''))}: {t.get('status', 'UNKNOWN')} {_text(t.get('error', ''))}" for t in pending)
        modes = sorted({_text(j.get("model_mode", j.get("mode", "UNKNOWN"))) for j in related})
        row.update({
            "case_id": identity,
            "run_id": source.get("run_id", run_id),
            "根因来源": source.get("root_cause_origin", source.get("root_cause_provenance", "LEGACY_DERIVED_UNKNOWN")),
            "缺口": "；".join(dict.fromkeys(_text(x) for x in missing if x not in (None, ""))),
            "模型模式": "；".join(modes) if modes else run.get("model_mode", run.get("mode", "NOT_RUN")),
        })
        rows.append(row)
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
    status = _text(data.get("validation", {}).get("status", run.get("status", "UNKNOWN")))
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
<body><h1>故障证据核验报告</h1><p class="meta">运行：{html.escape(identity)}<br>状态：{html.escape(status)}<br>根因列保留原始值。拒绝关联和未完成任务保留在明细中。</p><nav>{nav}</nav>{''.join(sections)}</body></html>'''


def _write(path: Path, content: str, encoding: str = "utf-8") -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding=encoding)
    temporary.replace(path)


def export_report(data: dict, output_dir: Path) -> dict:
    """Write JSON, HTML, all TSV tables and workbook_data without Node imports.

    Return absolute paths. ``workbook_data`` is consumed by the optional
    ``scripts/export_xlsx.mjs`` builder; no XLSX is claimed by this function.
    """
    if not isinstance(data, dict):
        raise TypeError("report data must be a dictionary")
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = [_table("汇总", _summary_rows(data), COMPAT_COLUMNS + EXTRA_COLUMNS)]
    tables.extend(_table(name, _records(data, key)) for name, key in _TABLES)
    for name, key in (("源文档", "documents"), ("排除记录", "exclusions")):
        if data.get(key):
            tables.append(_table(name, _records(data, key)))
    failed = [record for record in _records(data, "tasks")
              if _text(record.get("status", "")).upper() not in {"COMPLETE", "COMPLETED", "DONE", "SUCCEEDED", "SUCCESS", "SKIPPED"}]
    tables.append(_table("失败与待办", failed))
    validation = data.get("validation", {})
    tables.append(_table("运行对账", [{"类别": "run", **_flat(data.get("run", {}))},
                                   {"类别": "validation", **(validation if isinstance(validation, dict) else {"value": validation})}]))
    files = {
        "report_json": str(output_dir / "report.json"),
        "report_html": str(output_dir / "report.html"),
        "summary_tsv": str(output_dir / "summary.tsv"),
        "workbook_data": str(output_dir / "workbook_data.json"),
    }
    _write(Path(files["report_json"]), json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n")
    _write(Path(files["report_html"]), _html_report(data, tables))
    _write(Path(files["summary_tsv"]), _tsv(tables[0]), "utf-8-sig")
    workbook = {"schema_version": "1.0", "run": data.get("run", {}),
                "source_report": "report.json", "sheets": tables}
    _write(Path(files["workbook_data"]), json.dumps(workbook, ensure_ascii=False, indent=2, default=str) + "\n")
    for index, table in enumerate(tables[1:], start=1):
        _write(output_dir / f"{index:02d}_{table['name']}.tsv", _tsv(table), "utf-8-sig")
    return files
