"""Pure, one-workbook projection of initialized trigger coverage and proposals.

The caller supplies current validated assessments. Historical evidence labels
describe concrete source issues; they never establish executor/path coverage.
"""
from __future__ import annotations

from .exporters import _table, _text
from .trigger_assessment import CLASSIFICATION_FRAMEWORK
from . import __version__


COVERAGE_SCOPE = "历史资料证据归类；非算子执行、路径或测试覆盖；多标签数量不可相加为故障数"
SOURCE_DEFINITION_SCOPE = "原始描述及聊天记录的声明定义整理；未经网页核验；不确认事件、根因或执行覆盖"
_BASIS = {"SOURCE_DEFINITION": "原模式定义（尚未经网页核验）", "SOURCE_REPORTED": "资料陈述",
          "CODE_INFERENCE": "代码推断", "UNKNOWN": "未知"}


def _unique(records: list[dict], key: str) -> list[dict]:
    seen, result = set(), []
    for record in records:
        identity = record[key]
        if identity not in seen:
            result.append(record)
            seen.add(identity)
    return result


def _citations(value: dict) -> str:
    return "\n".join(dict.fromkeys(
        [f"{ref.get('segment_id', '')}: {ref.get('quote', '')}" for ref in value.get("evidence", [])]
        + [f"{ref.get('field', '')} [{ref.get('cell', '')}]: {ref.get('quote', '')}"
           for ref in value.get("source_cells", [])]))


def _condition_refs(value: dict, result: dict) -> str:
    facts = {f["fact_id"]: f for f in result.get("condition_facts", [])}
    return "\n".join(dict.fromkeys(filter(None, [_citations(value)] + [
        _citations(facts[fid]) for fid in value.get("condition_fact_ids", []) if fid in facts])))


def _confirmation(row: dict) -> str:
    if row.get("evidence_basis") == "SOURCE_DEFINITION":
        return "原文声明归类；未由资料核验"
    return {"MATCH": "强条件证据匹配；不代表根因或入库确认", "PARTIAL": "部分资料支持；未完整确认",
            "NOT_MATCHED": "有具体条件反证", "UNKNOWN": "资料未确认"}.get(row.get("relation"), "资料未确认")


def _labels(result: dict, prefix: str = "") -> dict:
    return {prefix + "条件处理状态": result.get("condition_processing_status", "PENDING"),
        prefix + "42项适用": "；".join(r["trigger_id"] for r in result.get("rows", []) if r.get("applicability") == "APPLICABLE"),
        prefix + "42项部分": "；".join(r["trigger_id"] for r in result.get("rows", []) if r.get("applicability") == "PARTIAL"),
        prefix + "Branch适用": "；".join(c["category_id"] for b in result.get("external_branches", [])
            for c in b.get("category_checks", []) if c.get("applicability") == "APPLICABLE"),
        prefix + "Branch部分": "；".join(c["category_id"] for b in result.get("external_branches", [])
            for c in b.get("category_checks", []) if c.get("applicability") == "PARTIAL")}


def _source(subject: dict) -> dict:
    case = subject.get("source_case", {})
    return {"原编号": case.get("external_id", ""), "模式编号": subject.get("mode_id", ""),
            "case_id": subject.get("case_id", ""), "来源文件": case.get("source_file", ""),
            "Sheet": case.get("sheet", ""), "原始行": case.get("row", ""),
            "单元格定位": "；".join(f"{key}={cell}" for key, cell in case.get("cell_locations", {}).items())}


def _state(assessments: list[dict], field: str = "processing_status") -> str:
    if not assessments:
        return "UNASSESSED"
    states = {a["result"].get(field, "PENDING") for a in assessments}
    if "EXCEPTION" in states:
        return "EXCEPTION"
    return "AUTO_PROCESSED" if states == {"AUTO_PROCESSED"} else "PENDING"


def build_workbook(data: dict) -> dict:
    """Return the existing ArtifactTool workbook-data schema without I/O.

    Assessment IDs are deduplicated and explicit stale records are excluded.
    Currentness policy and semantic gates remain the workflow's responsibility.
    A MODE_ENTRY is not projected as a historical incident.
    """
    subjects = _unique(data.get("subjects", []), "subject_id")
    by_subject = {s["subject_id"]: s for s in subjects}
    by_case = {s["case_id"]: s for s in subjects}
    assessments = _unique([a for a in data.get("assessments", []) if not a.get("is_stale")
                           and a["subject_id"] in by_subject], "assessment_id")
    taxonomy = data.get("taxonomy", {})
    items = {item["id"]: item for item in taxonomy.get("items", [])}
    checks = data.get("wiki_checks", {})
    coverage_kind = data.get("coverage_kind", "HISTORICAL_EVIDENCE")
    conditions_first = data.get("classification_framework") == CLASSIFICATION_FRAMEWORK
    coverage_scope = SOURCE_DEFINITION_SCOPE if coverage_kind == "SOURCE_DEFINITIONS" else COVERAGE_SCOPE
    supplied_gap_keys = {(g.get("case_id"), g.get("kind")) for g in data.get("gaps", [])}
    overview, coverage, details, branches, gaps, declared, facts = [], [], [], [], [], [], []
    for subject in subjects:
        relevant = [a for a in assessments if a["subject_id"] == subject["subject_id"]]
        matched = {r["trigger_id"] for a in relevant for r in a["result"].get("rows", []) if r["relation"] == "MATCH"}
        partial = {r["trigger_id"] for a in relevant for r in a["result"].get("rows", []) if r["relation"] == "PARTIAL"} - matched
        check = checks.get(subject["case_id"], {})
        case = subject.get("source_case", {})
        overview.append({**_source(subject), "对象编号": subject["subject_id"],
            "对象类型": subject.get("subject_kind", ""), "原模式/问题描述": case.get("description", ""),
            "原故障原因": case.get("root_cause_raw", ""), "处理状态": _state(relevant),
            "当前逐资料子问题判断数": len(relevant), "匹配触发类数": len(matched),
            "匹配触发类": "；".join(sorted(matched)), "部分触发类数": len(partial),
            "部分触发类": "；".join(sorted(partial)), "Wiki检查": check.get("status", "MISSING"),
            "Wiki说明": check.get("reason", ""), "建议动作": "；".join(sorted({
                a["result"].get("decision", {}).get("action", "") for a in relevant} - {""})),
            "声明整理建议": "；".join(sorted({(a["result"].get("declared_comparison") or {}).get("decision", {}).get("action", "")
                for a in relevant} - {""})),
            "声明整理状态": _state(relevant, "declared_processing_status"),
            "声明目标模式": "；".join(sorted({mode for a in relevant
                for mode in (a["result"].get("declared_comparison") or {}).get("decision", {}).get("target_mode_ids", [])})),
            "需人工裁决": "是" if any(a["result"].get("review_required") for a in relevant) else "否",
            "覆盖种类": coverage_kind, "覆盖范围": coverage_scope})
        if conditions_first:
            labels = [_labels(a["result"]) for a in relevant]
            early = {"原编号": case.get("external_id", ""), "模式编号": subject.get("mode_id", ""),
                "case_id": subject["case_id"], "条件分类尝试数": len(relevant),
                "条件处理状态": "已评估，未知保留" if relevant else "未评估"}
            for field in ("42项适用", "42项部分", "Branch适用", "Branch部分"):
                early[field] = "；".join(sorted({v for row in labels for v in row[field].split("；") if v}))
            early["条件未知项数"] = sum(r.get("applicability") == "UNKNOWN" for a in relevant for r in a["result"].get("rows", []))
            early["Branch未知项数"] = sum(c.get("applicability") == "UNKNOWN" for a in relevant
                for b in a["result"].get("external_branches", []) for c in b.get("category_checks", []))
            early["分类与证实区别"] = "描述标签可据原单元格成立；证据确认、根因及正式入库分别受门禁约束"
            overview[-1] = {**early, **{k: v for k, v in overview[-1].items() if k not in early}}
        if not relevant and (subject["case_id"], "UNASSESSED") not in supplied_gap_keys:
            gaps.append({**_source(subject), "类型": "UNASSESSED", "说明": "尚无当前有效逐资料分类；不能推定未覆盖或新增模式", "需人工裁决": "否"})
        if (check.get("status") not in {"FOUND", "NO_MATCH", "NOT_REQUESTED"}
                and (subject["case_id"], "WIKI_" + check.get("status", "MISSING")) not in supplied_gap_keys):
            gaps.append({**_source(subject), "类型": "WIKI_" + check.get("status", "MISSING"),
                         "说明": check.get("reason", "Wiki检查尚未完成"), "需人工裁决": "否"})

    for assessment in assessments:
        result = assessment["result"]
        source = _source(by_subject[assessment["subject_id"]])
        aid = assessment["assessment_id"]
        context = {**source, "判断编号": aid, "快照编号": assessment.get("snapshot_id", ""),
                   "子问题序号": assessment.get("issue_index", ""), "子问题": assessment.get("issue_label", ""),
                   ("资料子问题机理对应" if conditions_first else "资料对应关系"): result.get("source_relation", "UNKNOWN")}
        if conditions_first:
            context["分类策略指纹"] = assessment.get("policy_hash", "")
        if conditions_first:
            for fact in result.get("condition_facts", []):
                facts.append({**context, "事实编号": fact["fact_id"], "事实角色": fact["role"],
                    "事实适用对象": fact["subject"], "事实原义": fact["statement"],
                    "依据类型": _BASIS.get(fact.get("evidence_basis"), fact.get("evidence_basis")),
                    "原文及位置": _citations(fact)})
        local_details = {d["detail_id"] for d in result.get("details", [])}
        for row in result.get("rows", []):
            item = items.get(row["trigger_id"], {})
            predicates = "\n".join(f"[{p.get('clause_role', 'INCLUSION')}] {p.get('clause', '')} => {p.get('result', 'UNKNOWN')}"
                                    + ("\n" + (_condition_refs(p, result) if conditions_first else _citations(p))
                                       if (_condition_refs(p, result) if conditions_first else _citations(p)) else "")
                                    for p in row.get("predicate_checks", []))
            coverage.append({**context, "触发类编号": row["trigger_id"], "触发族": item.get("family_id", ""),
                "触发类名称": item.get("name", ""), "完整定义": item.get("definition", ""),
                "适用性": row.get("applicability", "UNKNOWN"), "对应判断": row.get("relation", "UNKNOWN"),
                "依据类型": _BASIS.get(row.get("evidence_basis", "UNKNOWN"), row.get("evidence_basis")),
                "完整谓词检查": predicates, "精确引文及单元格": _citations(row), "判断说明": row.get("reason", ""),
                "关联明细编号": "；".join((aid + ":" + did) if did in local_details else ("baseline:" + did)
                                         for did in row.get("detail_ids", [])),
                "覆盖种类": result.get("coverage_kind", coverage_kind), "本地执行验证": "未执行", "覆盖范围": coverage_scope})
            if conditions_first:
                coverage[-1] = {**context, "触发类编号": row["trigger_id"], "触发类名称": item.get("name", ""),
                    "描述条件归类": row.get("applicability", "UNKNOWN"), "证据确认": _confirmation(row),
                    "条件事实编号": "；".join(row.get("condition_fact_ids", [])),
                    "原文及位置": _condition_refs(row, result), **coverage[-1]}
        for detail in result.get("details", []):
            details.append({**context, "明细编号": aid + ":" + detail["detail_id"],
                "响应内明细编号": detail["detail_id"], "所属模式编号": detail.get("mode_id", ""),
                "明细名称": detail.get("name", ""), "具体机理": detail.get("mechanism", ""),
                "算子": detail.get("operator", ""), "适用条件": "\n".join(detail.get("conditions", [])),
                "触发类": "；".join(detail.get("trigger_ids", [])),
                "触发类判断": "；".join(r["trigger_id"] + ":" + r["relation"] for r in result.get("rows", [])
                    if r["trigger_id"] in detail.get("trigger_ids", [])),
                "依据类型": _BASIS.get(detail.get("evidence_basis", "UNKNOWN"), detail.get("evidence_basis")),
                "精确引文及单元格": _citations(detail), "未确定项": "\n".join(detail.get("unknowns", [])),
                "建议动作": result.get("decision", {}).get("action", ""),
                "声明整理建议": (result.get("declared_comparison") or {}).get("decision", {}).get("action", ""),
                "覆盖种类": detail.get("coverage_kind", "SOURCE_DEFINITIONS"
                    if detail.get("evidence_basis") == "SOURCE_DEFINITION" else "HISTORICAL_EVIDENCE"),
                "状态": "分类明细/建议，未自动正式入库", "本地执行验证": "未执行"})
        comparison = result.get("declared_comparison") or {}
        proposed = comparison.get("decision", {})
        for row in comparison.get("rows", []):
            declared.append({**context, "对照模式编号": row["mode_id"], "声明覆盖判断": row["result"],
                "机理关系": row.get("mechanism_relation", "UNKNOWN"),
                "原定义明细编号": "；".join(row.get("baseline_detail_ids", [])),
                "语义对照说明": row.get("reason", ""), "新案例精确依据": _citations(row),
                "库范围关系": comparison.get("scope_relation", "UNKNOWN"), "范围说明": comparison.get("scope_reason", ""),
                "声明整理建议": proposed.get("action", ""), "建议目标模式": "；".join(proposed.get("target_mode_ids", [])),
                "建议目标明细": "；".join(proposed.get("target_detail_ids", [])), "建议说明": proposed.get("reason", ""),
                "依据种类": "SOURCE_DEFINITIONS", "采用状态": "SUGGESTION_ONLY", "事件确认": "NOT_ESTABLISHED",
                "正式证据建议": result.get("decision", {}).get("action", ""), "本地执行验证": "未执行"})
        for branch in result.get("external_branches", []):
            if conditions_first:
                for category in branch.get("category_checks", []):
                    branches.append({**context, "记录类型": "条件分类", "分支编号": branch["branch_id"],
                        "子类编号": category["category_id"], "描述条件归类": category["applicability"],
                        "对应判断": branch.get("relation", "UNKNOWN"), "说明": category["reason"],
                        "条件事实编号": "；".join(category.get("condition_fact_ids", [])),
                        "精确引文及单元格": _condition_refs(category, result),
                        "未知项": "\n".join(category.get("unknowns", [])),
                        "证据确认": "叶子条件声明/资料依据见引文；不据此确认根因", "计入42类": "否"})
            else:
                branches.append({**context, "记录类型": "分类判断", "分支编号": branch["branch_id"],
                    "对应判断": branch.get("relation", "UNKNOWN"), "子类编号": "；".join(branch.get("category_ids", [])),
                    "说明": branch.get("reason", ""), "精确引文及单元格": _citations(branch), "计入42类": "否"})
        for reason in result.get("review_reasons", []):
            gaps.append({**context, "类型": "FACT_CONFLICT", "说明": _text(reason),
                         "需人工裁决": "是" if result.get("review_required") else "否"})

    for branch in taxonomy.get("branches", []):
        branches.append({"记录类型": "分支定义", "分支编号": branch["branch_id"],
            "名称": branch.get("name", ""), "对应判断": branch.get("status", "UNDEFINED"),
            "子类编号": "；".join(c["id"] for c in branch.get("categories", [])),
            "说明": branch.get("definition", ""), "子类定义": _text(branch.get("categories", [])),
            "定义来源": branch.get("provenance", branch.get("source_file", "")), "计入42类": "否"})
    for gap in data.get("gaps", []):
        subject = by_case.get(gap.get("case_id"), {})
        if gap.get("kind") == "FACT_CONFLICT" and any(
                row.get("case_id") == gap.get("case_id") and row["类型"] == "FACT_CONFLICT" for row in gaps):
            continue  # Current assessment reasons already retain the individual conflicts.
        gaps.append({**_source(subject), "类型": gap.get("kind", "GAP"), "说明": gap.get("reason", ""),
                     "需人工裁决": "是" if gap.get("review_required") else "否"})
    for resource in data.get("resources", []):
        subject = by_case.get(resource.get("case_id"), {})
        gaps.append({**_source(subject), "类型": "资料台账", "说明": resource.get("reason", ""),
            "引用编号": resource.get("ref_id", ""), "URL/原始引用": resource.get("url") or resource.get("raw_text", ""),
            "最初来源": resource.get("origin", ""), "来源单元格": resource.get("location", ""),
            "快照编号": resource.get("snapshot_id", ""), "采集状态": resource.get("capture_status", resource.get("status", "")),
            "资料对应关系": resource.get("source_relation", ""), "需人工裁决": "否"})

    gaps = _unique([{"_row_identity": _text(row), **row} for row in gaps], "_row_identity")
    gaps = [{key: value for key, value in row.items() if key != "_row_identity"} for row in gaps]

    modes = {s["mode_id"] for s in subjects if s.get("mode_id")}
    mode_count_scope = "初始化对象中的唯一mode_id；模式条目不是故障事件"
    if data.get("phase") == "INCREMENTAL" and "mode_ids" in (data.get("baseline") or {}):
        modes = set(data["baseline"]["mode_ids"])
        mode_count_scope = "冻结基线中的唯一mode_id；不以本批故障对象数替代原库模式数"
    matched_ids = {r["触发类编号"] for r in coverage if r["对应判断"] == "MATCH"}
    source_issues = {(a.get("snapshot_id"), a.get("summary_task_id"), a.get("issue_index")) for a in assessments if a.get("snapshot_id")}
    stats = [{"指标": "运行编号", "值": data.get("run_id", "")},
        {"指标": "流程阶段", "值": data.get("phase", "INIT")},
        {"指标": "42类唯一项数", "值": len(items), "口径": "唯一trigger_id；Branch2/3在此数之外"},
        {"指标": "输入触发族数", "值": len({i.get("family_id") for i in items.values()} - {None, ""})},
        {"指标": "原模式数量", "值": len(modes), "口径": mode_count_scope},
        {"指标": "来源记录数量", "值": len({s["case_id"] for s in subjects}), "口径": "唯一case_id"},
        {"指标": "当前分类判断数量", "值": len(assessments), "口径": "唯一assessment_id；排除显式过期项"},
        {"指标": "涉及资料子问题数量", "值": len(source_issues), "口径": "唯一(snapshot_id,summary_task_id,issue_index)，跨模式共享同摘要不重复计数"},
        {"指标": "有匹配证据的触发类数", "值": len(matched_ids), "口径": "唯一trigger_id；仅已列具体条件的历史证据，不代表全类或执行覆盖"},
        {"指标": "逐项匹配标签数", "值": sum(r["对应判断"] == "MATCH" for r in coverage), "口径": "逐判断逐触发类的标签；不能当作故障数量"},
        {"指标": "分类明细数量", "值": len(details), "口径": "assessment_id:detail_id，不自动合并不同资料机理"},
        {"指标": "声明定义明细数", "值": len((data.get("baseline") or {}).get("declared_details", [])), "口径": "保留原定义及聊天锚点；不代表网页或事件确认"},
        {"指标": "声明对照行数", "值": len(declared), "口径": "逐案例/子问题逐原模式；仅整理建议"},
        {"指标": "未分类来源数量", "值": sum(r["处理状态"] == "UNASSESSED" for r in overview)},
        {"指标": "需人工裁决来源数量", "值": sum(r["需人工裁决"] == "是" for r in overview)},
        {"指标": "覆盖范围", "值": coverage_scope},
        {"指标": "覆盖种类", "值": coverage_kind},
        {"指标": "本地执行验证", "值": "未执行"},
        {"指标": "初始化基线", "值": (data.get("baseline") or {}).get("baseline_id", "未冻结")},
        {"指标": "基线状态", "值": (data.get("baseline") or {}).get("status", "未冻结")},
        {"指标": "基线依据", "值": (data.get("baseline") or {}).get("coverage_kind", "未冻结")},
        {"指标": "基线库范围", "值": ((data.get("baseline") or {}).get("catalog_scope") or {}).get("scope", "未声明"),
         "口径": "子集实验基线外候选不等于正式全库新增模式"},
        {"指标": "基线采集来源", "值": "；".join(((data.get("baseline") or {}).get("collection_source_policy") or {}).get("collection_sources", []))}]
    if conditions_first:
        branch_labels = [c for a in assessments for b in a["result"].get("external_branches", [])
                         for c in b.get("category_checks", [])]
        stats[0:0] = [
            {"指标": "软件版本", "值": __version__},
            {"指标": "当前分类策略指纹", "值": "；".join(sorted({a.get("policy_hash", "") for a in assessments} - {""})), "口径": "来自当前有效评估；旧策略历史不在当前集合"},
            {"指标": "分类框架", "值": CLASSIFICATION_FRAMEWORK, "口径": "42项和Branch2/3优先；原模式用于后续机理关联"},
            {"指标": "资料对照口径", "值": "source_relation仅表达当前资料子问题对原机理的对应", "口径": "不代替事件身份、资料整体归属、DIRECT或正式入库裁决"},
            {"指标": "条件分类尝试来源数", "值": len({a["case_id"] for a in assessments}), "口径": "唯一case_id；不以标签数替代"},
            {"指标": "条件分类子问题评估数", "值": len(assessments), "口径": "唯一assessment_id；来源声明评估也单列，不代表故障数"},
            {"指标": "描述适用触发类数", "值": len({r["触发类编号"] for r in coverage if r["描述条件归类"] == "APPLICABLE"}), "口径": "唯一trigger_id；同类在不同案例可另有部分标签，不相加为故障数"},
            {"指标": "描述部分触发类数", "值": len({r["触发类编号"] for r in coverage if r["描述条件归类"] == "PARTIAL"}), "口径": "唯一trigger_id；仍有前提缺口，不代表资料已证实"},
            {"指标": "有描述正向标签的来源数", "值": len({r["case_id"] for r in coverage if r["描述条件归类"] in {"APPLICABLE", "PARTIAL"}}), "口径": "唯一case_id；每条可有多标签和多子问题"},
            {"指标": "42项描述适用标签数", "值": sum(r["描述条件归类"] == "APPLICABLE" for r in coverage), "口径": "逐评估逐trigger_id；非证据确认数"},
            {"指标": "42项描述部分标签数", "值": sum(r["描述条件归类"] == "PARTIAL" for r in coverage), "口径": "逐评估逐trigger_id；条件仍有缺口"},
            {"指标": "42项描述未知数", "值": sum(r["描述条件归类"] == "UNKNOWN" for r in coverage), "口径": "逐评估逐trigger_id；未知不是排除"},
            {"指标": "描述正向条件对数", "值": len({(r["case_id"], r["触发类编号"]) for r in coverage if r["描述条件归类"] in {"APPLICABLE", "PARTIAL"}}), "口径": "唯一(case_id,trigger_id)；多子问题重复标签只计一次；不能当作故障数量"},
            {"指标": "Branch适用标签数", "值": sum(c["applicability"] == "APPLICABLE" for c in branch_labels), "口径": "逐评估逐Branch叶子；不计入42项"},
            {"指标": "Branch部分标签数", "值": sum(c["applicability"] == "PARTIAL" for c in branch_labels), "口径": "逐评估逐Branch叶子；不计入42项"},
            {"指标": "条件事实数", "值": len(facts), "口径": "逐评估局部fact_id；同一引文的多个事实不代表独立证据"}]
        def columns(rows, leading):
            available = list(dict.fromkeys(k for r in rows for k in r))
            return ([k for k in leading if k in available] + [k for k in available if k not in leading]
                    if rows else leading)
        sheets = [
            _table("条件分类索引" if data.get("phase") == "INIT" else "故障条件分类总览", overview,
                   columns(overview, ["原编号", "模式编号", "case_id", "条件处理状态",
                       "42项适用", "42项部分", "Branch适用", "Branch部分"])),
            _table("条件事实", facts, columns(facts, ["原编号", "case_id", "事实编号", "事实角色", "事实原义", "原文及位置"])),
            _table("42项条件分类", coverage, columns(coverage, ["原编号", "case_id", "触发类编号", "触发类名称", "描述条件归类", "证据确认"])),
            _table("Branch2和3", branches, columns(branches, ["原编号", "case_id", "分支编号", "子类编号", "描述条件归类", "未知项"])),
            _table("机理明细", details, columns(details, ["原编号", "case_id", "明细编号", "所属模式编号", "具体机理", "状态"])),
            _table("声明定义对照", declared, columns(declared, ["原编号", "case_id", "对照模式编号", "声明覆盖判断", "机理关系", "库范围关系"])),
            _table("证据与缺口", gaps, columns(gaps, ["原编号", "case_id", "类型", "说明", "需人工裁决"])),
            _table("运行统计", stats, ["指标", "值", "口径"])]
        frozen = data.get("baseline") or {}
        index = (frozen.get("condition_index", []) if frozen.get("status") != "STALE"
                 and frozen.get("classification_framework") == CLASSIFICATION_FRAMEWORK else [])
        if data.get("phase") == "INCREMENTAL" and index:
            init_overview, init_rows, init_branches = [], [], []
            for entry in index:
                context = {**_source(entry), "判断编号": entry["assessment_id"],
                    "子问题": entry.get("issue_label", ""), "依据范围": SOURCE_DEFINITION_SCOPE
                    if entry.get("coverage_kind") == "SOURCE_DEFINITIONS" else COVERAGE_SCOPE}
                init_overview.append({**context, **_labels(entry),
                    "原模式定义": entry.get("source_case", {}).get("description", ""),
                    "原故障原因": entry.get("source_case", {}).get("root_cause_raw", ""),
                    "机理及未知边界": "\n".join(d["detail_id"] + " " + d.get("name", "") + "：" + d.get("mechanism", "")
                        + "\n" + "；".join(d.get("unknowns", []))
                        for d in frozen.get("declared_details", []) if d.get("mode_id") == entry.get("mode_id")),
                    "原文定位": "\n".join(dict.fromkeys(_citations(f) for f in entry.get("condition_facts", [])))})
                for row in entry.get("rows", []):
                    init_rows.append({**context, "触发类编号": row["trigger_id"], "触发类名称": items.get(row["trigger_id"], {}).get("name", ""),
                        "描述条件归类": row["applicability"], "证据确认": _confirmation(row), "说明": row["reason"],
                        "原文及位置": _condition_refs(row, entry), "完整条件核对": "\n".join(
                            p.get("clause_role", "INCLUSION") + ": " + p["clause"] + " => " + p["result"] + "\n" + _condition_refs(p, entry)
                            for p in row.get("predicate_checks", []))})
                for branch in entry.get("external_branches", []):
                    for category in branch.get("category_checks", []):
                        init_branches.append({**context, "子类编号": category["category_id"], "描述条件归类": category["applicability"],
                            "说明": category["reason"], "未知项": "\n".join(category.get("unknowns", [])),
                            "原文及位置": _condition_refs(category, entry)})
            init_headers = {
                "Init条件索引": ["模式编号", "原编号", "case_id", "条件处理状态",
                    "42项适用", "42项部分", "Branch适用", "Branch部分"],
                "Init42项核对": ["模式编号", "触发类编号", "触发类名称", "描述条件归类", "证据确认", "说明"],
                "Init Branch2和3": ["模式编号", "子类编号", "描述条件归类", "未知项", "说明", "原文及位置"]}
            sheets.extend([_table(name, rows, columns(rows, init_headers[name])) for name, rows in (
                ("Init条件索引", init_overview), ("Init42项核对", init_rows), ("Init Branch2和3", init_branches))])
        previous = data.get("previous_classification")
        if previous is not None:
            old_by_case = {}
            for assessment in _unique([a for a in previous.get("assessments", []) if not a.get("is_stale")], "assessment_id"):
                old_by_case.setdefault(assessment["case_id"], []).append(assessment)
            comparison = []
            for subject in subjects:
                old = old_by_case.get(subject["case_id"], [])
                current = [a for a in assessments if a["case_id"] == subject["case_id"]]
                labels = [_labels(a["result"]) for a in current]
                comparison.append({**_source(subject), "旧评估数": len(old), "新评估数": len(current),
                    "旧机理归类建议": "；".join(sorted({mid for a in old for mid in
                        ((a["result"].get("declared_comparison") or {}).get("decision") or {}).get("target_mode_ids", [])})),
                    "旧42项描述适用": "；".join(sorted({r["trigger_id"] for a in old
                        for r in a["result"].get("rows", []) if r.get("applicability") == "APPLICABLE"})),
                    "旧42项描述部分": "；".join(sorted({r["trigger_id"] for a in old
                        for r in a["result"].get("rows", []) if r.get("applicability") == "PARTIAL"})),
                    "旧证据MATCH数": sum(r["relation"] == "MATCH" for a in old for r in a["result"].get("rows", [])),
                    "旧证据PARTIAL数": sum(r["relation"] == "PARTIAL" for a in old for r in a["result"].get("rows", [])),
                    **{k: "；".join(sorted({v for label in labels for v in label[k].split("；") if v}))
                       for k in ("42项适用", "42项部分", "Branch适用", "Branch部分")},
                    "对比口径": "旧证据关系与新描述分类是不同维度；不能以标签增多声称根因证实或分类准确率提升"})
            sheets.append(_table("分类前后对照", comparison, columns(comparison, ["case_id", "旧评估数", "新评估数"])))
        book = {"schema_version": "1.0", "kind": "TRIGGER_CLASSIFICATION", "run": {"run_id": data.get("run_id", "")}, "sheets": sheets}
        if data.get("v4_taxonomy"):
            from .trigger_v4_report import extend_workbook
            return extend_workbook(book, data)
        return book
    return {"schema_version": "1.0", "kind": "TRIGGER_CLASSIFICATION", "run": {"run_id": data.get("run_id", "")},
        "sheets": [
            _table("模式初始化总览" if data.get("phase", "INIT") == "INIT" else "故障分类总览", overview,
                   list(overview[0]) if overview else ["原编号", "模式编号", "case_id", "处理状态", "覆盖范围"]),
            _table("42类覆盖详情", coverage, list(coverage[0]) if coverage else ["判断编号", "模式编号", "触发类编号", "对应判断", "覆盖范围"]),
            _table("机理明细", details, list(details[0]) if details else ["明细编号", "所属模式编号", "具体机理", "触发类", "状态"]),
            _table("Branch2和3", branches, list(dict.fromkeys(key for row in branches for key in row)) if branches else ["记录类型", "分支编号", "对应判断", "计入42类"]),
            _table("证据与缺口", gaps, list(dict.fromkeys(key for row in gaps for key in row)) if gaps else ["case_id", "类型", "说明", "需人工裁决"]),
            _table("运行统计", stats, ["指标", "值", "口径"])] +
            ([_table("声明定义对照", declared, list(dict.fromkeys(key for row in declared for key in row)))] if declared else [])}
