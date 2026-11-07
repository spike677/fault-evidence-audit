"""V4-first report tables; crosswalk rows never generate classifications."""
from __future__ import annotations

from collections import Counter

from .exporters import _table


def extend_workbook(book, data):
    from .trigger_report import _citations, _condition_refs, _source, _confirmation
    v4 = data["v4_taxonomy"]
    items = {v["id"]: v for v in v4["items"]}
    subjects = {v["subject_id"]: v for v in data["subjects"]}
    assessments = [a for a in data["assessments"] if not a.get("is_stale")]
    overview = next(s for s in book["sheets"] if s["name"] in {"故障条件分类总览", "条件分类索引"})
    new_rows, constructions, designs, participants = [], [], [], []
    labels_by_case = {}
    for a in assessments:
        context = {**_source(subjects[a["subject_id"]]), "判断编号": a["assessment_id"],
            "子问题": a.get("issue_label", ""), "V4规则版本": v4["definition_version"],
            "资料子问题机理对应": a["result"]["source_relation"]}
        for row in a["result"].get("v4_rows", []):
            key = row["trigger_id"]
            item = items[key]
            cov = row["coverage"]
            new_rows.append({"原编号": context["原编号"], "case_id": a["case_id"], "V4类编号": key,
                "V4类名称": item["name"], "语义适用性": row["applicability"], "证据确认": _confirmation(row),
                "构造能力": cov["construction"], "构造能力说明": cov["construction_reason"],
                "路径覆盖": cov["path"], "路径说明": cov["path_reason"], "执行结果": cov["execution"],
                "原文及位置": _condition_refs(row, a["result"]), "完整条件核对": "\n".join(
                    p["clause_role"] + ": " + p["clause"] + " => " + p["result"] + "\n" + _condition_refs(p, a["result"])
                    for p in row["predicate_checks"]),
                "判断说明": row["reason"], "未知项": "\n".join(row.get("unknowns", [])), **context})
            if row["applicability"] in {"APPLICABLE", "PARTIAL"}:
                labels_by_case.setdefault(a["case_id"], {}).setdefault(row["applicability"], set()).add(key)
            for check in row["construction_checks"]:
                constructions.append({"原编号": context["原编号"], "case_id": a["case_id"],
                    "V4类编号": key, "构造代码": check["construction_id"],
                    "语义适用性": check["applicability"], "构造定义": check["definition_check"]["clause"],
                    "构造定义核对": check["definition_check"]["result"],
                    "原文及位置": _condition_refs(check, a["result"]), "说明": check["reason"], **context})
    for row in overview["rows"]:
        by_case = dict(zip(overview["columns"], row))
        labels = labels_by_case.get(by_case["case_id"], {})
        row[0:0] = ["；".join(sorted(labels.get("APPLICABLE", []))), "；".join(sorted(labels.get("PARTIAL", []))),
            v4["definition_version"], "语义/构造/路径/执行分别记录；未实机执行"]
    overview["columns"][0:0] = ["V4适用", "V4部分", "V4规则版本", "覆盖状态说明"]
    assessments_by_id = {a["assessment_id"]: a for a in assessments}
    for d in data.get("designs", []):
        for card in d["result"]["cards"]:
            a = assessments_by_id[card["assessment_id"]]
            source = _source(subjects[a["subject_id"]])
            facts = {f["fact_id"]: f for f in a["result"]["condition_facts"]}
            designs.append({"原编号": source["原编号"], "case_id": d["case_id"], "设计卡编号": card["card_id"],
                "设计状态": card["status"], "V4类": "；".join(card["category_ids"]),
                "构造代码": "；".join(card["construction_ids"]), "执行规程": "；".join(card["execution_method_ids"]),
                "变量及依据": "\n".join(v["kind"] + " " + v["name"] + ": " + "；".join(v["proposed_values"]) + "\n" + v["reason"] for v in card["variables"]),
                "边界": "\n".join(card["boundaries"]), "参考计算": card["reference"], "目标路径": card["target_path"],
                "检查项": "\n".join(card["checks"]), "执行步骤": "\n".join(card["protocol_steps"]),
                "能力要求": "\n".join(card["required_capabilities"]), "能力缺口": "\n".join(card["capability_gaps"]),
                "未知项": "\n".join(card["unknowns"]), "执行结果": card["execution_status"], "路径覆盖": card["path_coverage"],
                "指导案例": "；".join(card["guide_ids"]), "指导案例身份": "构造线索；配套来源审计未提供，非本机复现",
                "原文及位置": "\n".join(_citations(facts[key]) for key in card["condition_fact_ids"]),
                "判断编号": card["assessment_id"], "子问题": a["issue_label"], **source})
            for participant in card["participants"]:
                participants.append({"原编号": source["原编号"], "case_id": d["case_id"], "设计卡编号": card["card_id"],
                    "参与者": participant["participant_id"], "角色": participant["role"],
                    "目标调用": participant["target_call_id"], "实参归属": participant["input_assignment"],
                    "输出归属": participant["output_owner"], "context": participant["context"], "stream": participant["stream"],
                    "executor": participant["executor"], "生命周期": participant["lifecycle"],
                    "串行基准": card["serial_baseline"], "event记录位置": card["event_record"], "wait位置": card["consumer_wait"],
                    "执行结果": "NOT_RUN"})
    mapping = data["mapping"]
    mapping_rows = [{"来源规则版本": r["source_scheme"], "来源编号": r["source_id"],
        "目标规则版本": r["target_scheme"], "目标编号": r["target_id"] or "无对应",
        "映射语义": r["relation"], "说明": r["reason"], "传递适用性": "禁止", "传递覆盖": "禁止",
        "映射版本": mapping["mapping_version"]} for r in mapping["rows"]]
    definitions = [{"V4类编号": i["id"], "名称": i["name"], "完整定义": i["definition"],
        "原Requires": "\n".join(i["original_requires"]), "原Skip": "\n".join(i["original_skip_if"]),
        "规范Requires": "\n".join(i["requires"]), "规范Skip": "\n".join(i["skip_if"]),
        "构造能力条件": "\n".join(i["construction_requires"]), "路径前提": "\n".join(i["path_requires"]),
        "分析要求": "\n".join(i["analysis_requires"]), "解释修订原因": i["revision_reason"],
        "原文位置": f"{v4['source_file']}:{i['line_start']}", "规则版本": v4["definition_version"]} for i in v4["items"]]
    revisions = [{"原42编号": item["id"], "原定义版本": data["taxonomy"]["original_definition_version"],
        "修订规则版本": data["taxonomy"]["definition_version"], "原完整定义": item["original_definition"],
        "修订完整定义": item["definition"], "原因": item["revision_reason"],
        "族Requires覆盖": "\n".join(item.get("family_requires_override", [])),
        "族Skip覆盖": "\n".join(item.get("family_skip_override", []))} for item in data["taxonomy"]["items"]]
    protocol_rows = [{"规程编号": m["method_id"], "名称": m["name"], "完整执行规程": m["definition"],
        "执行能力": "未实现；仅设计规程", "计入输入类别": "否"} for m in v4["methods"]]
    extra = [_table("V4条件分类", new_rows, list(new_rows[0]) if new_rows else
                    ["原编号", "case_id", "V4类编号", "语义适用性", "证据确认", "构造能力", "路径覆盖", "执行结果"]),
        _table("V4构造情形", constructions, list(constructions[0]) if constructions else
                    ["原编号", "case_id", "V4类编号", "构造代码", "语义适用性", "说明"]),
        _table("用例设计卡", designs, list(designs[0]) if designs else ["case_id", "设计状态", "能力缺口", "执行结果"]),
        _table("参与者与对照", participants, list(participants[0]) if participants else ["case_id", "参与者", "目标调用", "执行结果"]),
        _table("42与V4映射", mapping_rows), _table("V4定义与解释", definitions),
        _table("42定义版本修订", revisions), _table("执行规程", protocol_rows)]
    frozen = data.get("baseline") or {}
    if frozen.get("status") != "STALE" and frozen.get("v4_definition_version") == v4["definition_version"]:
        init_rows = []
        for entry in frozen.get("condition_index", []):
            for row in entry.get("v4_rows", []):
                init_rows.append({"模式编号": entry["mode_id"], "case_id": entry["case_id"], "V4类编号": row["trigger_id"],
                    "语义适用性": row["applicability"], "证据确认": _confirmation(row),
                    "原文及位置": _condition_refs(row, entry), "说明": row["reason"],
                    "构造能力": row["coverage"]["construction"], "路径覆盖": row["coverage"]["path"], "执行结果": "NOT_RUN"})
        extra.append(_table("Init V4条件索引", init_rows))
    previous = data.get("previous_classification")
    if previous:
        old = {(a["case_id"], a.get("snapshot_id"), a.get("issue_label")): a for a in previous.get("assessments", [])}
        changes = []
        for a in assessments:
            prior = old.get((a["case_id"], a.get("snapshot_id"), a.get("issue_label")))
            source = _source(subjects[a["subject_id"]])
            before = {r["trigger_id"]: r for r in prior["result"]["rows"]} if prior else {}
            for row in a["result"]["rows"]:
                prior_row = before.get(row["trigger_id"])
                if prior_row and all(prior_row[k] == row[k] for k in ("applicability", "relation")):
                    continue
                item = next(i for i in data["taxonomy"]["items"] if i["id"] == row["trigger_id"])
                changes.append({**source, "子问题": a["issue_label"], "原42编号": row["trigger_id"],
                    "旧适用性": prior_row["applicability"] if prior_row else "无同范围旧评估", "旧理由": prior_row["reason"] if prior_row else "",
                    "新适用性": row["applicability"], "新理由": row["reason"], "定义修订原因": item["revision_reason"],
                    "新原文及位置": _condition_refs(row, a["result"]), "旧判断编号": prior["assessment_id"] if prior else "",
                    "新判断编号": a["assessment_id"], "旧定义版本": "TRIGGER42-ORIGINAL-v1",
                    "新定义版本": data["taxonomy"]["definition_version"], "覆盖传递": "无；新旧独立评估"})
        extra.append(_table("逐项分类变化", changes, list(changes[0]) if changes else ["case_id", "原42编号", "旧适用性", "新适用性", "说明"]))
    stats = next(s for s in book["sheets"] if s["name"] == "运行统计")
    stats["rows"].extend([["V4条件类", 31, "独立分类定义，不与原42相加"], ["V4唯一构造代码", 55, "按construction_id去重"],
        ["V4挂载数", 64, "类别-构造代码对；不是64种构造"], ["V4指导案例", 195, "构造建议编号，不是历史故障新增数"],
        ["V4当前子问题评估数", len(assessments), "唯一assessment_id"],
        ["V4有明确描述标签的case数", len(labels_by_case), "唯一case_id，多标签不相加"],
        ["当前设计case数", len({v["case_id"] for v in data.get("designs", [])}), "设计与执行分别验收"],
        ["当前设计卡数", len(designs), "case内card_id；多张卡不等于多个故障"],
        ["实际设备执行数", 0, "本阶段没有执行适配器；全部NOT_RUN"],
        ["V4规则版本", v4["definition_version"], "原文、解释修订和映射版本分别冻结"]])
    book["sheets"][1:1] = extra
    return book
