"""One-workbook projection for the structured-XLSX investigation workflow.

Ranking is an explainable processing order, never an inferred severity score.
The existing report projection owns evidence/review labels; this module reuses it.
"""
from __future__ import annotations

import re
from collections import Counter

from .catalog_drafts import COLUMNS
from .exporters import (_fact_comparison_rows, _flat, _involves_case, _needs_attention, _reference_audit_rows,
                        _required, _review_status, _summary_rows, _table, _text)

RANKING_BASIS = ("原表明确优先级（P0/P1/数字，小值优先）→整理处理组→来源文件/Sheet/Excel行/case_id。"
                 "这是整理优先级，不代表已验证故障严重程度或风险评分。")


def _unique(records: list[dict], *keys: str) -> list[dict]:
    result, seen = [], set()
    for index, record in enumerate(records):
        identity = next((record.get(key) for key in keys if record.get(key)), ("unnumbered", index))
        if identity not in seen:
            seen.add(identity)
            result.append(record)
    return result


def _current_data(data: dict) -> dict:
    result = dict(data)
    result["cases"] = _unique([_flat(case) for case in data.get("cases", [])], "case_id")
    tasks = {task.get("task_id"): task for task in data.get("tasks", [])}
    for kind, keys in (("judgments", ("judgment_id", "task_id")), ("mappings", ("mapping_id", "task_id")),
                       ("summaries", ("task_id",)), ("snapshots", ("snapshot_id",))):
        values = [_flat(value) for value in data.get(kind, [])]
        result[kind] = _unique([value for value in values if not value.get("is_stale")
                              and _required(value, tasks)], *keys)
    return result


def _priority(case: dict) -> tuple[int, str]:
    raw = case.get("raw", {})
    for key in ("优先级", "priority", "source_priority", "优先级组"):
        value = raw.get(key, case.get(key, ""))
        if value is None or not str(value).strip():
            continue
        label = str(value).strip()
        match = re.fullmatch(r"(?:P\s*)?(\d+)", label, re.IGNORECASE)
        if match:
            return int(match[1]), label
    return 10**9, ""


def _original_id(case: dict, summary: dict) -> str:
    return _text(case.get("external_id") or summary.get("统一ID") or summary.get("序号"))


def _wiki(checks: dict, case_id: str) -> dict:
    return checks.get(case_id) or {"status": "MISSING", "reason": "尚未完成本轮Wiki检查"}


def _group(summary: dict, has_material: bool, proposals: list[dict]) -> tuple[int, str]:
    if summary["处理状态"] == "EXCEPTION":
        return 0, "异常待核对"
    coverage = str(summary["库覆盖（98条）"])
    if any(p.get("action") == "ADD" for p in proposals) or coverage.startswith("NOT_COVERED"):
        return 1, "未覆盖或新增候选"
    if any(p.get("action") == "REFINE" for p in proposals) or coverage.startswith("PARTIALLY_COVERED"):
        return 2, "部分覆盖或细化候选"
    if coverage.startswith("COVERED"):
        return 5, "已有模式覆盖"
    if has_material:
        return 3, "已有资料，待模式判断"
    return 4, "资料待补充"


def _citations(refs: list[dict]) -> str:
    return "\n".join(dict.fromkeys(f"{ref.get('segment_id', '')}: {ref.get('quote', '')}" for ref in refs))


def _independent_summary(issues: list[dict], applicable: dict | None) -> str:
    label = (applicable or {}).get("label")
    values = []
    for issue in issues:
        if label and issue.get("label") != label:
            continue
        facts = [f"{fact.get('field', '')}：{_text(fact.get('value'))}" for fact in issue.get("facts", [])]
        if facts:
            values.append(f"[{issue.get('label', '')}] " + "；".join(facts))
    return "\n".join(dict.fromkeys(values))


def build_ranked_workbook(data: dict, wiki_checks: dict | None = None,
                          proposals: list[dict] | dict | None = None) -> dict:
    """Build the existing ArtifactTool workbook_data schema, without I/O/state writes.

    ``data`` is pipeline.report_data(), whose current/stale flags are authoritative.
    Proposal semantic validation stays at its existing entry point, not in this view.
    """
    checks = wiki_checks or {}
    supplied = proposals.get("proposals", []) if isinstance(proposals, dict) else proposals or []
    proposals = _unique([_flat(p) for p in supplied if not p.get("is_stale")], "proposal_id")
    current = _current_data(data)
    cases = {case["case_id"]: case for case in current["cases"]}
    summaries = {row["case_id"]: row for row in _summary_rows(current)}
    current_snapshots = {snapshot["snapshot_id"]: snapshot for snapshot in current.get("snapshots", [])}
    prepared = []
    for case_id, case in cases.items():
        summary = summaries[case_id]
        selected_proposals = [p for p in proposals if case_id in p.get("case_ids", [])]
        relevant = [j for j in current["judgments"] if _involves_case(j, case_id)]
        urls = {r["url"] for r in current.get("references", []) if r.get("case_id") == case_id and r.get("url")}
        has_material = any(snapshot.get("status", snapshot.get("retrieval_status")) in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"}
            and (snapshot.get("url") in urls or any(j.get("snapshot_id") == snapshot["snapshot_id"] for j in relevant))
            for snapshot in current_snapshots.values())
        group_order, group = _group(summary, has_material, selected_proposals)
        priority, priority_label = _priority(case)
        check = _wiki(checks, case_id)
        location = "；".join(f"{field}={cell}" for field, cell in case.get("cell_locations", {}).items())
        row = {"排名": 0, "原编号": _original_id(case, summary), "case_id": case_id,
            "整理分组": group, "原优先级": priority_label,
            "原优先级组": summary.get("优先级组", ""),
            "来源": summary.get("来源", ""), "来源文件": case.get("source_file", ""),
            "Sheet": case.get("sheet", ""), "Excel行": case.get("row"), "单元格定位": location,
            "客户/模型": summary.get("客户/模型", ""), "问题描述原文": summary.get("问题描述", ""),
            "算子原文": summary.get("算子", ""), "根因/进展原文": summary.get("根因", ""),
            "原归因来源": summary.get("根因来源", ""), "Wiki检查": check.get("status", "MISSING"),
            "Wiki检查说明": check.get("reason", ""), "证据强度": summary["证据强度"],
            "当前证据判断": summary["证据判断"], "模式库覆盖": summary["库覆盖（98条）"],
            "模式建议动作": "；".join(dict.fromkeys(p.get("action", "") for p in selected_proposals)),
            "提案编号": "；".join(p.get("proposal_id", "") for p in selected_proposals),
            "处理状态": summary["处理状态"], "需人工裁决": summary["需人工"],
            "缺口": summary["缺口"], "排序依据": (f"原表优先级 {priority_label}；" if priority_label else "无明确原表优先级；")
                         + group + "；同组按来源文件、Sheet和Excel行排序"}
        prepared.append(((priority, group_order, str(case.get("source_file", "")).casefold(),
            str(case.get("sheet", "")).casefold(), case.get("row") or 0, case_id), row))
    ranked = []
    for rank, (_, row) in enumerate(sorted(prepared, key=lambda item: item[0]), 1):
        ranked.append({**row, "排名": rank})
    by_case = {row["case_id"]: row for row in ranked}

    evidence_rows = []
    for detail in _reference_audit_rows(current):
        case_id = detail.get("case_id")
        case = cases.get(case_id, {})
        row = by_case.get(case_id, {})
        evidence_rows.append({"排名": row.get("排名"), "原编号": row.get("原编号", ""), "case_id": case_id,
            "来源文件": case.get("source_file", ""), "Sheet": case.get("sheet", ""), "Excel行": case.get("row"),
            "引用编号": detail.get("ref_id"), "URL": detail.get("url"), "来源关系": detail.get("source_grade"),
            "最初来源": detail.get("origin"), "来源单元格": detail.get("location"),
            "已由用户确认": detail.get("user_confirmed"), "本轮必要引用": detail.get("required"),
            "快照编号": detail.get("snapshot_id"), "采集状态": detail.get("capture_status"),
            "适用子问题": (detail.get("applicable_issue") or {}).get("label", ""),
            "资料独立摘要（不等于故障根因）": _independent_summary(detail.get("summary_issues", []), detail.get("applicable_issue")),
            "判断编号": detail.get("judgment_id"), "工作编号": detail.get("work_id"),
            "正文精确引文": _citations(detail.get("evidence", [])), "判断状态": detail.get("judgment_status"),
            "Wiki检查": _wiki(checks, case_id).get("status"), "Wiki查询词": _wiki(checks, case_id).get("query", ""),
            "Wiki查询范围": _wiki(checks, case_id).get("scope", "")})
    evidence_rows.sort(key=lambda row: (row.get("排名") or 10**9, str(row.get("引用编号") or ""), str(row.get("判断编号") or "")))

    judgments_by_id = {j.get("judgment_id"): j for j in current["judgments"]}
    fact_columns = ["排名", "原编号", "case_id", "关联case_id", "来源文件", "Sheet", "Excel行", "原文归属说明",
                    "判断编号", "工作编号", "快照编号", "适用子问题", "对照类型", "原记录字段", "原记录单元格",
                    "原记录引文", "原记录值", "原记录含义", "采集原文值", "采集原文含义", "正文精确引文",
                    "判断", "理由", "处理状态", "审核状态"]
    fact_rows = []
    for fact in _fact_comparison_rows(current):
        case_id = fact.get("source_case_id")
        case, row = cases.get(case_id, {}), by_case.get(case_id, {})
        fact_rows.append({"排名": row.get("排名"), "原编号": row.get("原编号", ""), "case_id": case_id,
            "关联case_id": "；".join(fact.get("member_case_ids", [])),
            "来源文件": case.get("source_file", ""), "Sheet": case.get("sheet", ""), "Excel行": case.get("row"),
            "原文归属说明": fact.get("source_scope"), "判断编号": fact.get("judgment_id"),
            "工作编号": fact.get("work_id"), "快照编号": fact.get("snapshot_id"),
            "适用子问题": (fact.get("applicable_issue") or {}).get("label", ""),
            "对照类型": fact.get("category"), "原记录字段": fact.get("source_field"),
            "原记录单元格": fact.get("source_cell"), "原记录引文": fact.get("source_quote"),
            "原记录值": fact.get("source_value"), "原记录含义": fact.get("source_meaning"),
            "采集原文值": fact.get("evidence_value"), "采集原文含义": fact.get("evidence_meaning"),
            "正文精确引文": _citations(fact.get("evidence", [])), "判断": fact.get("relation"),
            "理由": fact.get("reason"), "处理状态": fact.get("processing_status"),
            "审核状态": _review_status(judgments_by_id.get(fact.get("judgment_id"), {}))})
    fact_rows.sort(key=lambda row: (row.get("排名") or 10**9, str(row.get("判断编号") or "")))

    proposal_rows = []
    for proposal in proposals:
        item = {"提案编号": proposal.get("proposal_id"), "修订": proposal.get("revision"),
            "关联原编号": "；".join(by_case[cid]["原编号"] for cid in proposal.get("case_ids", []) if cid in by_case),
            "case_id": "；".join(proposal.get("case_ids", [])), "建议动作": proposal.get("action"),
            "目标模式编号": proposal.get("target_item_id"), "实现归属": proposal.get("implementation_owner"),
            "证据范围": proposal.get("evidence_scope"), "状态": "草案，未正式入库"}
        for field, label in COLUMNS.items():
            value = proposal.get("row", {}).get(field, "")
            kind = proposal.get("field_bases", {}).get(field, {}).get("kind")
            if kind == "PROPOSED":
                value = "建议（未验证、未执行）：" + str(value)
            elif kind == "SOURCE_CELL":
                value = "原表陈述（未核验）：" + str(value)
            elif field == "root_cause" and proposal.get("evidence_scope") == "INDEPENDENT_TECHNICAL_PATTERN":
                value = "资料机制（客户关联未确认）：" + ("代码推断：" if kind == "CODE_INFERENCE" else "") + str(value)
            elif kind == "CODE_INFERENCE":
                value = "代码推断：" + str(value)
            item[label] = value
        item.update({"缺口": "\n".join(proposal.get("unknowns", [])), "冲突": "\n".join(proposal.get("conflicts", []))})
        proposal_rows.append(item)

    exceptions = []
    for row in ranked:
        wiki = _wiki(checks, row["case_id"])
        if row["处理状态"] != "AUTO_PROCESSED" or row["缺口"] or wiki.get("status") != "FOUND":
            exceptions.append({"排名": row["排名"], "原编号": row["原编号"], "case_id": row["case_id"],
                "类型": "人工异常" if row["需人工裁决"] == "是" else "Agent待处理/采集缺口",
                "处理状态": row["处理状态"], "需人工裁决": row["需人工裁决"], "Wiki检查": wiki.get("status"),
                "说明": "；".join(value for value in (row["缺口"], row["当前证据判断"], wiki.get("reason", "")) if value)})
    for task in current.get("tasks", []):
        if _needs_attention(task):
            exceptions.append({"排名": by_case.get(task.get("case_id"), {}).get("排名"),
                "原编号": by_case.get(task.get("case_id"), {}).get("原编号", ""), "case_id": task.get("case_id", ""),
                "类型": "必要任务", "处理状态": task.get("status"), "需人工裁决": "否",
                "任务编号": task.get("task_id"), "说明": task.get("error", "")})

    judgments = current["judgments"]
    supports = [j for j in judgments if _review_status(j) != "REJECT"]
    wiki_counts = Counter(_wiki(checks, cid).get("status", "MISSING") for cid in cases)
    stats = [{"指标": "排序口径", "值": RANKING_BASIS},
        {"指标": "运行编号", "值": data.get("run", {}).get("run_id", "")},
        {"指标": "运行验收状态", "值": data.get("validation", {}).get("status", "未提供")},
        {"指标": "故障记录数量", "值": len(ranked), "口径": "唯一case_id；一条记录可有多个判断"},
        {"指标": "当前判断数量", "值": len(judgments), "口径": "唯一judgment_id，排除过期/非必要结果，包含当前人工拒绝项"},
        {"指标": "可支持结论的判断数量", "值": len(supports), "口径": "当前判断排除人工REJECT；不表示事件已确认"},
        {"指标": "过期判断留档数量", "值": len(_unique([j for j in data.get("judgments", []) if j.get("is_stale")], "judgment_id", "task_id"))},
        {"指标": "当前库映射数量", "值": len(current["mappings"])},
        {"指标": "原库模式数量", "值": len({item["item_id"] for item in data.get("catalog", [])})},
        {"指标": "模式建议数量", "值": len(proposals), "口径": "唯一proposal_id，排除已标过期草案；不代表正式新增"},
        {"指标": "ADD建议数量", "值": sum(p.get("action") == "ADD" for p in proposals)},
        {"指标": "自动处理记录数量", "值": sum(row["处理状态"] == "AUTO_PROCESSED" for row in ranked)},
        {"指标": "需人工裁决记录数量", "值": sum(row["需人工裁决"] == "是" for row in ranked)},
        {"指标": "必要待处理任务数量", "值": sum(_needs_attention(task) for task in current.get("tasks", []))},
        *[{"指标": "Wiki检查：" + status, "值": count} for status, count in sorted(wiki_counts.items())]]
    return {"schema_version": "1.0", "kind": "STRUCTURED_XLSX_RANKING", "ranking_basis": RANKING_BASIS,
        "run": data.get("run", {}), "sheets": [
            _table("整体故障排名", ranked, list(ranked[0]) if ranked else ["排名", "原编号", "case_id", "来源文件", "Sheet", "Excel行", "问题描述原文"]),
            _table("来源与证据", evidence_rows),
            _table("事实对照", fact_rows, fact_columns),
            _table("模式库建议", proposal_rows, list(proposal_rows[0]) if proposal_rows else ["提案编号", "关联原编号", "case_id", "建议动作", "模式名称", "状态"]),
            _table("异常与待处理", exceptions, list(dict.fromkeys(key for row in exceptions for key in row)) if exceptions else ["排名", "原编号", "case_id", "类型", "需人工裁决", "说明"]),
            _table("运行统计", stats, ["指标", "值", "口径"])]}
