"""Versioned V4 definitions and explanatory crosswalk; no result propagation."""
from __future__ import annotations

import copy
import re
from pathlib import Path

from .store import AuditError, digest
from .trigger_taxonomy import EXPECTED_IDS, condition_role_requirements

V4_VERSION = "V4-INPUT-RULES-0.1.15"
LEGACY_VERSION = "TRIGGER42-ORIGINAL-v1"
REVISED_VERSION = "TRIGGER42-BOUNDARIES-0.1.15"
MAPPING_VERSION = "TRIGGER42-V4-CROSSWALK-0.1.15"
PROFILE = "V4_AND_REVISED42_v1"
CLASS_IDS = tuple(f"{prefix}{i}" for prefix, n in (("D", 4), ("N", 6), ("S", 9), ("I", 4), ("T", 3), ("C", 5)) for i in range(1, n + 1))
INPUT_ROLES = {"INPUT_VALUE", "INPUT_SHAPE", "INPUT_DTYPE", "INPUT_LAYOUT", "INDEX_OR_OFFSET", "API_CONTROL"}
CLASS_ROLES = {
    "D1": {"API_CONTROL", "INPUT_VALUE"}, "D2": {"API_CONTROL", "INPUT_VALUE"},
    "D3": {"INPUT_SHAPE"}, "D4": {"INPUT_VALUE", "INDEX_OR_OFFSET"},
    "N1": {"INPUT_VALUE", "API_CONTROL"}, "N2": {"INPUT_VALUE", "INTERMEDIATE_VALUE", "DERIVED_CONTROL"},
    "N3": {"INPUT_VALUE", "INPUT_LAYOUT"}, "N4": {"INPUT_VALUE", "INTERMEDIATE_VALUE", "INTERNAL_COMPUTATION"},
    "N5": {"INPUT_VALUE", "INPUT_DTYPE", "API_CONTROL", "PATH_PREDICATE"},
    "N6": {"INPUT_VALUE", "INPUT_LAYOUT", "INDEX_OR_OFFSET"},
    "S1": {"INPUT_SHAPE", "DERIVED_CONTROL"}, "S2": {"INPUT_SHAPE", "CAPACITY", "DERIVED_CONTROL"},
    "S3": {"INPUT_SHAPE"}, "S4": {"INPUT_SHAPE", "DERIVED_CONTROL"},
    "S5": {"INPUT_SHAPE", "DERIVED_CONTROL", "PATH_PREDICATE"},
    "S6": {"INPUT_SHAPE", "API_CONTROL", "INDEX_OR_OFFSET"},
    "S7": {"INPUT_SHAPE", "API_CONTROL"}, "S8": {"INPUT_SHAPE", "INDEX_OR_OFFSET", "API_CONTROL"},
    "S9": {"INPUT_SHAPE", "DERIVED_CONTROL"},
    "I1": {"INDEX_OR_OFFSET", "API_CONTROL"}, "I2": {"INDEX_OR_OFFSET", "INPUT_SHAPE", "API_CONTROL"},
    "I3": {"INDEX_OR_OFFSET", "INPUT_SHAPE", "INPUT_LAYOUT", "DERIVED_CONTROL"},
    "I4": {"INDEX_OR_OFFSET", "INPUT_VALUE", "INPUT_LAYOUT", "API_CONTROL", "PATH_PREDICATE"},
    "T1": {"INPUT_LAYOUT"}, "T2": {"INPUT_LAYOUT", "API_CONTROL"},
    "T3": {"INPUT_LAYOUT", "INPUT_DTYPE", "API_CONTROL"},
    "C1": {"INPUT_DTYPE", "API_CONTROL", "PATH_PREDICATE"},
    "C2": {"API_CONTROL", "PATH_PREDICATE", "DERIVED_CONTROL"},
    "C3": {"API_CONTROL"},
    "C4": INPUT_ROLES | {"DERIVED_CONTROL", "PATH_PREDICATE", "CAPACITY"},
    "C5": {"API_CONTROL", "INPUT_VALUE", "DERIVED_CONTROL"}}

# These are explicit, versioned interpretations authorized for this release.
# Original Requires/Skip text is retained alongside each interpretation.
INTERPRETATIONS = {
    "D1": {"requires": ["接口允许省略目标输入或显式传入相应合法值。"],
        "skip_if": ["目标参数在接口契约中没有可选或缺省语义。"],
        "construction_requires": ["执行器能够保留省略与显式传值的差别。"]},
    "D3": {"construction_requires": ["执行器能够表达契约允许的标量或零元素形状。"]},
    "S1": {"skip_if": ["接口没有可控的关键形状或对应粒度语义。"],
        "construction_requires": ["执行器不会自动补齐并改变目标小尺寸。"]},
    "S2": {"skip_if": ["实现没有相应容量、表示范围或规模分支。"],
        "construction_requires": ["可用存储和执行器能够承载目标规模；否则保留公式和资源估计。"]},
    "S5": {"skip_if": ["实现没有目标分块或尾块语义。"],
        "path_requires": ["取得真实分块尺寸及完整路径谓词；仅有猜测不能声称路径覆盖。"]},
    "I3": {"requires": ["合法 shape、stride 或 index 驱动内部窄整数计数、乘积或地址偏移。"],
        "skip_if": ["实现不存在目标地址或计数的位宽边界。"],
        "construction_requires": ["实际存储容量能够承载目标地址跨度；公式样本不计为设备执行。"],
        "analysis_requires": ["合法驱动实参", "元素或字节偏移公式", "逐步运算位宽", "类型提升位置", "容量估计", "目标边界及单位"]},
    "T1": {"requires": ["调用入口契约允许目标合法 stride 或 storage_offset。"],
        "skip_if": ["调用入口契约不支持目标视图寻址。"],
        "construction_requires": ["执行器在真实调用入口保留 stride、offset 和足够的底层存储，不自动实体化。"]},
    "T2": {"requires": ["API 允许目标 layout、format 或物理打包表示。"],
        "skip_if": ["接口契约不支持目标布局或物理表示。"],
        "construction_requires": ["执行器能够构造并保留匹配的物理存储。"]},
    "C2": {"requires": ["存在显式数值策略 API 控制，或合法实参通过可追踪谓词选择相应数值实现。"],
        "skip_if": ["既没有显式数值控制，也没有合法输入驱动的目标数值实现路径。"],
        "path_requires": ["输入驱动策略须保存驱动实参、分派条件及路径证据，不能把内部指令当作 API 参数。"]},
    "C4": {"path_requires": ["输入驱动路径保存派生公式、完整分派谓词及目标路径依据；内部派生量不冒充实参。"]}}

def _anchor(path, lines, start, end):
    return {"source_file": str(path), "line_start": start + 1, "line_end": end,
            "source_quote": "".join(lines[start:end]).rstrip()}

def load_v4(path: Path) -> dict:
    path = Path(path).resolve()
    raw = path.read_bytes()
    lines = raw.decode("utf-8-sig").splitlines(keepends=True)
    text = "".join(lines)
    starts = [(n, m[1], m[2]) for n, line in enumerate(lines)
              if (m := re.match(r"^### ([DNSITC]\d+) (.+?)\s*$", line))]
    if [key for _, key, _ in starts] != list(CLASS_IDS):
        raise AuditError("V4 needs the complete ordered 31 condition classes")
    items, mounts, guides, constructors = [], [], [], {}
    for position, (start, key, name) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else next(
            (n for n in range(start + 1, len(lines)) if lines[n].startswith("## ")), len(lines))
        body = lines[start:end]
        fields = {}
        for label, field in (("条件定义", "definition"), ("检验目的", "purpose"),
                             ("适用前提（Requires）", "requires"), ("跳过/能力限制（Skip if）", "skip_if")):
            prefix = "- **" + label + "**："
            matches = [v.strip()[len(prefix):] for v in body if v.strip().startswith(prefix)]
            if len(matches) != 1:
                raise AuditError(f"V4 {key} needs exactly one complete {label}")
            fields[field] = matches[0]
        construction_ids = []
        for offset, line in enumerate(body):
            match = re.match(r"^  - `([^`]+)` — \*\*(.+?)\*\*：(.*)$", line.rstrip())
            if match:
                cid, cname, definition = match.groups()
                value = {"id": cid, "name": cname, "definition": definition.strip()}
                if cid in constructors and any(constructors[cid][f] != value[f] for f in value):
                    raise AuditError("Shared V4 construction code has inconsistent definitions: " + cid)
                constructors.setdefault(cid, {**value, "source_occurrences": []})["source_occurrences"].append(
                    _anchor(path, lines, start + offset, start + offset + 1))
                construction_ids.append(cid)
                mounts.append({"category_id": key, "construction_id": cid})
            example = re.match(r"^\d+\. \*\*(" + key + r"-\d+)\*\*：\*\*(.+?)\*\*(.*)$", line.rstrip())
            if example:
                guides.append({"guide_id": example[1], "category_id": key,
                    "title": example[2], "text": example[3].strip(),
                    "source_status": "CONSTRUCTION_LEAD_NOT_DEVICE_VERIFIED",
                    **_anchor(path, lines, start + offset, start + offset + 1)})
        if not construction_ids or len(construction_ids) != len(set(construction_ids)):
            raise AuditError("V4 category needs unique mounted construction codes: " + key)
        interpretation = INTERPRETATIONS.get(key, {})
        items.append({"id": key, "family_id": key[0], "name": name,
            "definition": fields["definition"], "purpose": fields["purpose"],
            "original_requires": [fields["requires"]], "original_skip_if": [fields["skip_if"]],
            "requires": interpretation.get("requires", [fields["requires"]]),
            "skip_if": interpretation.get("skip_if", [fields["skip_if"]]),
            "construction_requires": interpretation.get("construction_requires", []),
            "path_requires": interpretation.get("path_requires", []),
            "analysis_requires": interpretation.get("analysis_requires", []),
            "revision_reason": "用户授权拆分语义适用、构造能力和路径条件；原文完整保留" if interpretation else "原文语义条件保留",
            "allowed_fact_roles": sorted(CLASS_ROLES[key]), "construction_ids": construction_ids,
            **_anchor(path, lines, start, end)})
    if len(constructors) != 55 or len(mounts) != 64 or len(guides) != 195 or len({v["guide_id"] for v in guides}) != 195:
        raise AuditError("V4 counts must be 55 unique constructions, 64 mounts and 195 unique guidance IDs")
    methods = []
    for key in ("E1", "E2", "E3", "E4", "E5"):
        start = next((i for i, line in enumerate(lines) if line.startswith("### " + key + " ")), None)
        if start is None:
            raise AuditError("V4 execution protocol missing: " + key)
        end = next((i for i in range(start + 1, len(lines)) if re.match(r"^#{1,3} ", lines[i])), len(lines))
        methods.append({"method_id": key, "name": lines[start].strip()[4:],
            "definition": "".join(lines[start + 1:end]).strip(), "execution_implemented": False,
            **_anchor(path, lines, start, end)})
    methods.append({"method_id": "B3.2-PRODUCER-CONSUMER-v1", "name": "跨流生产—消费补充规程",
        "definition": "固定目标消费者及串行参考；记录生产者/消费者、参数与输出归属、context/stream/executor、event record位置、consumer wait位置。仅设计支持的合法依赖对照，保存实际目标路径和能力缺口。此规程不计为新的输入类别。",
        "source_file": "USER_INSTRUCTION", "source_quote": "跨流生产—消费补充协议：生产者、消费者、event记录、wait位置和串行基准。",
        "execution_implemented": False})
    identity = {"definition_version": V4_VERSION, "source_sha256": digest(raw),
                "interpretations": INTERPRETATIONS, "roles": {k: sorted(v) for k, v in CLASS_ROLES.items()}, "methods": methods}
    hashed = digest(identity)
    return {"schema_version": "1.0", "definition_version": V4_VERSION,
        "taxonomy_id": "trigger-v4-" + hashed[:24], "taxonomy_hash": hashed,
        "source_file": str(path), "source_sha256": digest(raw), "original_document": text,
        "item_count": 31, "construction_count": 55, "mount_count": 64, "guide_count": 195,
        "items": items, "constructions": list(constructors.values()), "mounts": mounts, "guides": guides,
        "methods": methods, "global_rules": text[:text.index("## D 退化输入")],
        "source_audit_status": "COMPANION_AUDIT_NOT_PROVIDED", "execution_implemented": False}

def revise_42(original: dict) -> dict:
    value = copy.deepcopy(original)
    value.update(definition_version=REVISED_VERSION, original_definition_version=LEGACY_VERSION,
                 original_taxonomy_id=original["taxonomy_id"], branch_comparison_scope="TARGET_CALL")
    for item in value["items"]:
        item["allowed_fact_roles"] = sorted(condition_role_requirements(item["id"]))
        item["original_definition"] = item["definition"]
        item["original_requires"] = list(item.get("requires", []))
        item["original_skip_if"] = list(item.get("skip_if", []))
        item["revision_reason"] = "原定义保留；允许事实角色由项目元数据声明"
        if item["id"] == "1.3.2":
            item.update(definition="合法 shape、stride 或 index 驱动的内部地址或计数超出目标窄整数范围。",
                allowed_fact_roles=["INDEX_OR_OFFSET", "INPUT_SHAPE", "INPUT_LAYOUT", "DERIVED_CONTROL"],
                family_requires_override=[], family_skip_override=[],
                requires=["合法 shape、stride 或 index 使实际地址或计数公式接近或跨越目标位宽边界。"],
                analysis_requires=INTERPRETATIONS["I3"]["analysis_requires"],
                revision_reason="解除原1.3族必须有显式索引/窗映射实参的统一限制；普通张量的合法内部算址同样可分析。")
        elif item["id"] == "1.7.6":
            item.update(allowed_fact_roles=["INPUT_VALUE", "INTERMEDIATE_VALUE", "INTERNAL_COMPUTATION"],
                revision_reason="中间值及运算顺序可作为中间溢出声明依据；仍不能据此归为输入NaN/Inf。")
        elif item["id"] == "1.4.1":
            item.update(definition="合法非连续视图进入支持相应寻址的调用入口；执行器构造能力另记。",
                family_requires_override=[], family_skip_override=[],
                requires=["调用入口契约允许目标非连续视图寻址。"], skip_if=["接口契约不支持目标非连续视图。"],
                construction_requires=["执行器实际保留合法 stride、offset 和底层存储，不自动连续化。"],
                revision_reason="接口语义适用与执行器是否能够保留非连续输入分开。")
    identity = {"original": original["taxonomy_id"], "version": REVISED_VERSION,
                "items": value["items"], "branch_comparison_scope": "TARGET_CALL"}
    value["taxonomy_hash"] = digest(identity)
    value["taxonomy_id"] = "trigger-revised42-" + value["taxonomy_hash"][:24]
    return value

def canonical_conditions(item: dict, family: dict | None = None) -> set[tuple[str, str]]:
    family = family or {}
    includes = [item["definition"], *item.get("requires", []),
                *item.get("family_requires_override", family.get("requires", []))]
    excludes = [*item.get("skip_if", []), *item.get("family_skip_override", family.get("skip_if", []))]
    return {("INCLUSION", v.strip()) for v in includes if v.strip()} | {("EXCLUSION", v.strip()) for v in excludes if v.strip()}

# Direction: TARGET_BROADER means the V4 target includes more than the 42 source.
_CROSSWALK = {
    "1.1.1": [("D3", "TARGET_BROADER", "零长度轴只是退化形状的一种，标量与单元素不能继承其结论。")],
    "1.1.2": [("D2", "TARGET_BROADER", "零次数是退化控制的一种，其他控制取值需独立判断。")],
    "1.1.3": [("N3", "TARGET_BROADER", "全零行块是稀疏分布的子情形。")],
    "1.1.4": [("S8", "TARGET_BROADER", "空专家是分组结构的专项，保留MoE和空专家条件。")],
    "1.1.5": [("I4", "PARTIAL_OVERLAP", "空分核与无效块选择有关，但需要真实分派及参与核证据。")],
    "1.2.1": [("S1", "TARGET_BROADER", "关键维为1是微小形状的一种，不涵盖所有处理粒度。")],
    "1.2.2": [("S5", "TARGET_BROADER", "非对齐尾块属于真实分块边界；二次幂另行判断。"), ("S4", "PARTIAL_OVERLAP", "只有明确二次幂语义才与S4重叠。")],
    "1.2.3": [("S2", "PARTIAL_OVERLAP", "split计数容量与大规模分支部分重叠，不能从大shape推断内部数组上限。")],
    "1.2.4": [("S2", "TARGET_BROADER", "大维整数范围只是规模和容量问题的一种。"), ("I3", "PARTIAL_OVERLAP", "只有进入实际地址/计数公式才关联地址溢出。")],
    "1.2.5": [("S7", "TARGET_BROADER", "广播退化是合法输入形状对应的一种。"), ("T1", "PARTIAL_OVERLAP", "零stride广播还需实际视图存储依据。")],
    "1.2.6": [("C4", "TARGET_BROADER", "模板边界是输入驱动分派的子情形。"), ("S5", "PARTIAL_OVERLAP", "只有与实际tile边界重合时才共同成立。")],
    "1.2.7": [("S6", "TARGET_BROADER", "卷积组合保留几何契约，S6还含其他窗口操作。")],
    "1.2.8": [("S1", "TARGET_BROADER", "小输出字节数是处理粒度不足的子情形。")],
    "1.3.1": [("I1", "PARTIAL_OVERLAP", "负索引须区分合法归一化与越界拒绝。"), ("I2", "PARTIAL_OVERLAP", "索引端点与非法极值不等价，非法输入只验契约拒绝。")],
    "1.3.2": [("I3", "TARGET_BROADER", "V4也允许普通张量shape/stride驱动内部算址，原硬性索引入口更窄。")],
    "1.3.3": [("S6", "PARTIAL_OVERLAP", "窗口几何与窗端点部分重叠，合法构造与非法契约测试分开。"), ("I2", "PARTIAL_OVERLAP", "窗口端点保留对应几何语义。")],
    "1.3.4": [("S8", "PARTIAL_OVERLAP", "保留MoE路由语义，不能从一般分组结构证明路由专项。"), ("D4", "PARTIAL_OVERLAP", "重复路由只与目标集中情形重叠。")],
    "1.4.1": [("T1", "TARGET_BROADER", "视图还包含连续非零offset；非连续性须单独确认。")],
    "1.4.2": [("T1", "PARTIAL_OVERLAP", "大stride与一般视图不等价。"), ("I3", "PARTIAL_OVERLAP", "需实际窄整数公式才能判断地址范围。")],
    "1.4.3": [("T2", "TARGET_BROADER", "特殊格式属于布局和物理打包的一部分。")],
    "1.5.1": [("S5", "PARTIAL_OVERLAP", "保留序列长度语义及真实对齐粒度。"), ("S8", "PARTIAL_OVERLAP", "变长组织不能替代序列非对齐条件。")],
    "1.5.2": [("S2", "PARTIAL_OVERLAP", "通用大维不自动覆盖长序列专项。"), ("S9", "PARTIAL_OVERLAP", "长序列可能引起多轮，但需实际路径。")],
    "1.5.3": [("S1", "PARTIAL_OVERLAP", "decode必须保留执行阶段与seq_len=1，不能从任意维为1继承。")],
    "1.5.4": [("S5", "PARTIAL_OVERLAP", "保留head维及其真实对齐规则。")],
    "1.6.1": [("S9", "TARGET_BROADER", "多batch只是单次调用多轮处理的一种，跨调用序列另记E2。")],
    "1.6.2": [("S8", "TARGET_BROADER", "保留专家/token分配语义。")],
    "1.7.1": [("N3", "PARTIAL_OVERLAP", "全零输入与scale除零不是同一个断言。"), ("N2", "PARTIAL_OVERLAP", "还须确认数据驱动分母和稳定项。")],
    "1.7.2": [("N1", "TARGET_BROADER", "N1还包括正负零、次正规和有限值范围，前序污染另记E2。")],
    "1.7.3": [("N1", "PARTIAL_OVERLAP", "极大有限值与其他特殊值分开。"), ("N4", "PARTIAL_OVERLAP", "实际中间求值范围需单独核对。")],
    "1.7.4": [("N2", "TARGET_BROADER", "近零分母是近奇异数值的一种。")],
    "1.7.5": [("N2", "PARTIAL_OVERLAP", "保留log/softmax的定义域语义。"), ("C5", "PARTIAL_OVERLAP", "只有已知分段阈值才与控制边界重叠。")],
    "1.7.6": [("N4", "TARGET_BROADER", "中间溢出是求值顺序和范围敏感问题的一种，不是输入含Inf。")],
    "1.8.1": [("S8", "PARTIAL_OVERLAP", "保留packed元数据和有效长度。"), ("T2", "PARTIAL_OVERLAP", "还须核对packed物理布局。")],
    "1.8.2": [("C3", "PARTIAL_OVERLAP", "mask模式须由真实控制/输入表达。"), ("I4", "PARTIAL_OVERLAP", "有效集合与模式枚举不等价。")],
    "1.8.3": [("S6", "TARGET_BROADER", "负padding裁剪是窗口几何的专项。")],
    "1.C.1": [("C2", "TARGET_BROADER", "保留原API量化开关身份，V4还允许输入驱动策略。")],
    "1.C.2": [("C1", "TARGET_BROADER", "输出dtype控制只是低/混合精度组合的一部分。")],
    "1.C.3": [("C2", "TARGET_BROADER", "显式compute控制与内部输入分派分别记录。")],
    "1.C.4": [("C3", "PARTIAL_OVERLAP", "保留RoPE/sink等专项模式，不能从普通操作枚举继承。"), ("C4", "PARTIAL_OVERLAP", "模板功能支持还须核对完整分派条件。")],
    "1.C.5": [("C2", "TARGET_BROADER", "API确定性/累加与同步根因、重复实验方法分别记录。")],
    "1.C.6": [("T2", "TARGET_BROADER", "显式format控制与物理存储能力分开。")],
    "1.C.7": [("C3", "PARTIAL_OVERLAP", "归约种类只覆盖该组合项的一部分。"), ("T3", "PARTIAL_OVERLAP", "transpose及轴变换还需各自语义。"), ("I1", "PARTIAL_OVERLAP", "负轴只是dim控制的一种。")],
}

def freeze_mapping(original: dict, revised: dict, v4: dict) -> dict:
    if set(_CROSSWALK) != set(EXPECTED_IDS):
        raise AuditError("Crosswalk must explain every original 42 ID")
    rows = [{"source_scheme": LEGACY_VERSION, "source_id": source,
        "target_scheme": V4_VERSION, "target_id": target, "relation": relation, "reason": reason,
        "propagate_applicability": False, "propagate_coverage": False}
        for source, targets in _CROSSWALK.items() for target, relation, reason in targets]
    rows += [{**row, "source_scheme": REVISED_VERSION,
        "relation": "EQUIVALENT" if row["source_id"] == "1.3.2" and row["target_id"] == "I3" else row["relation"],
        "reason": "修订42与V4均允许合法shape/stride/index驱动内部窄整数算址；仍各自核对完整条件，不能传递结论。"
            if row["source_id"] == "1.3.2" and row["target_id"] == "I3" else row["reason"]}
        for row in list(rows)]
    rows += [{"source_scheme": V4_VERSION, "source_id": source, "target_scheme": LEGACY_VERSION,
        "target_id": None, "relation": "NO_COUNTERPART", "reason": reason,
        "propagate_applicability": False, "propagate_coverage": False} for source, reason in (
            ("D1", "原42没有独立的可选输入省略/显式提供类别。"),
            ("N5", "原42没有独立覆盖数据舍入中点与小数转布尔语义的同义类别。"))]
    value = {"mapping_version": MAPPING_VERSION, "source_taxonomy_id": original["taxonomy_id"],
        "source_definition_version": LEGACY_VERSION, "revised_definition_version": REVISED_VERSION,
        "revised_taxonomy_id": revised["taxonomy_id"], "target_taxonomy_id": v4["taxonomy_id"],
        "relation_direction": "SOURCE_TO_TARGET; TARGET_BROADER means target includes a broader set",
        "allowed_relations": ["EQUIVALENT", "TARGET_BROADER", "TARGET_NARROWER", "PARTIAL_OVERLAP", "NO_COUNTERPART"],
        "purpose": "EXPLANATION_AND_NAVIGATION_ONLY", "rows": rows}
    return {**value, "mapping_id": "trigger-mapping-" + digest(value)[:24]}

def model_v4(frozen: dict) -> dict:
    """Complete classification rules; all 195 guides stay frozen for design tasks."""
    keys = ("id", "family_id", "name", "definition", "purpose", "original_requires", "original_skip_if",
            "requires", "skip_if", "construction_requires", "path_requires", "analysis_requires",
            "revision_reason", "allowed_fact_roles", "construction_ids", "line_start", "line_end")
    return {k: frozen[k] for k in ("taxonomy_id", "taxonomy_hash", "definition_version", "source_sha256", "item_count",
        "construction_count", "mount_count", "guide_count", "source_audit_status")} | {
        "items": [{k: v[k] for k in keys} for v in frozen["items"]],
        "constructions": [{k: c[k] for k in ("id", "name", "definition")} for c in frozen["constructions"]],
        "methods": [{k: m[k] for k in ("method_id", "name", "definition")} for m in frozen["methods"] if m["method_id"] in {"E1", "E2", "E3", "E4", "E5"}],
        "global_rules": frozen["global_rules"],
        "input_scope": {"all_31_definitions_complete": True, "all_55_constructions_complete": True,
            "all_64_mounts_included": True, "guidance_examples_included": False,
            "exclusion_reason": "195 guidance examples are a separate frozen design index, not classification prerequisites"}}
