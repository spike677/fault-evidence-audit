#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
症状分诊表生成器（gen_triage.py，v3.6）

用途
----
把「索引里的 156 条 symptoms」渲染成**按现象组织**的入口表 `TRIAGE.md`：
用户只知道「卡死 / 精度不对 / 内存高」时，先在这里收敛到 1~6 条候选模式，再进 skill 深挖。

数据源（两处，职责分离）
------------------------
- `triage_map.json`：人工维护的**分诊映射**（入口 / 分组 / 每条候选的典型症状 + 首查动作）；
- `fault_patterns_index.json`：模式名称、风险档、卡片路径（不在此重复抄写）。

用法
----
python3 scripts/gen_triage.py            # 校验映射并重写 TRIAGE.md
python3 scripts/gen_triage.py --check    # 只校验（映射合法 + TRIAGE.md 与生成结果一致），供 CI 用
python3 scripts/gen_triage.py --root <库根>

退出码
------
0 = 通过（--check 模式下表示文件最新且映射合法）
1 = 映射不合法（缺覆盖 / 组内候选 >6 / 引用不存在的模式）
2 = 参数或环境错误
3 = --check 模式下 TRIAGE.md 与生成结果不一致（需重跑）

映射约束（与守门 C20 对齐）
--------------------------
- 51 条模式**每条至少出现一次**（允许跨入口复用，如 FP-B08 同时出现在「组合」与「路径差异」）；
- 单个分组候选 **≤6 条**，超出须在组标题标 `[WIDE]` 并补一句二次筛选取向；
- 行序按风险（高→中→低）再按编号，生成器负责排序，映射表不必手排。
"""

import argparse
import json
import os
import re
import sys

RISK_ORDER = {"高": 0, "中": 1, "低": 2}
COVER_RE = re.compile(r"^\|\s*\[(FP-[A-G]\d{2})\]\(([^)]+)\)\s*\|[^|]+\|\s*`([^`]+)`\s*\|")


def read_text(p):
    with open(p, encoding="utf-8-sig") as f:
        return f.read()


def load(root):
    idx = json.loads(read_text(os.path.join(root, "fault_patterns_index.json")))
    tri = json.loads(read_text(os.path.join(root, "triage_map.json")))
    skills = {}
    sread = os.path.join(root, "skills", "README.md")
    if os.path.isfile(sread):
        for line in read_text(sread).splitlines():
            m = COVER_RE.match(line)
            if m:
                skills[m.group(1)] = (m.group(3), os.path.normpath(os.path.join("skills", m.group(2))))
    return idx, tri, skills


def load_cases(root):
    """cases/cases.json → {fp_id: 案例数}（v5.5，供分诊行标注「已立案数」；缺失则 {}）。"""
    p = os.path.join(root, "cases", "cases.json")
    if not os.path.isfile(p):
        return {}
    with open(p, encoding="utf-8-sig") as f:
        d = json.load(f)
    out = {}
    for c in d.get("cases", []):
        out[c.get("fp_id")] = out.get(c.get("fp_id"), 0) + 1
    return out


def validate(idx, tri, skills):
    errs = []
    by_id = {p["id"]: p for p in idx["patterns"]}
    seen = set()
    for ent in tri.get("entries", []):
        for grp in ent.get("groups", []):
            rows = grp.get("rows", [])
            if len(rows) > 6 and "[WIDE]" not in grp.get("title", ""):
                errs.append("%s / %s：候选 %d 条 > 6 且未标 [WIDE]"
                            % (ent.get("id"), grp.get("title"), len(rows)))
            for row in rows:
                fp = row.get("fp")
                if fp not in by_id:
                    errs.append("%s：引用不存在的模式 %r" % (ent.get("id"), fp))
                    continue
                if not row.get("symptom") or not row.get("first"):
                    errs.append("%s %s：缺 symptom 或 first" % (ent.get("id"), fp))
                seen.add(fp)
                if fp not in skills:
                    errs.append("%s：skills/README 覆盖表缺该模式的 skill 名" % fp)
    missing = sorted(set(by_id) - seen)
    if missing:
        errs.append("分诊表未覆盖的模式：%s" % "、".join(missing))
    for q in tri.get("quick_index", []):
        if not re.match(r"^T\d(\.\d)?$", q.get("entry", "")):
            errs.append("quick_index 入口非法：%r" % q.get("entry"))
    return errs


def render(idx, tri, skills, cases=None):
    by_id = {p["id"]: p for p in idx["patterns"]}
    version = tri.get("version", idx.get("version", "?"))
    out = []
    out.append("# 症状分诊（Triage，v%s）" % version)
    out.append("")
    out.append("> **这是什么**：库的「现象入口」。手上只有现象、不知道查哪条模式时先看这里——"
               "每个入口把候选收敛到 1~6 条，再进对应 skill 深挖。")
    out.append("> **与索引的分工**：根 `README.md` 的总览表按「模式」组织（已知要查什么时用）；"
               "本表按「现象」组织（只知道出了什么事时用）。两者都只是入口，判定一律以卡片与 skill 为准。")
    out.append("> **生成方式**：由 `scripts/gen_triage.py` 从 `fault_patterns_index.json` + `triage_map.json` 生成，"
               "**勿手改**；改映射后重跑本脚本，并跑守门 C20。")
    out.append("")
    out.append("## 30 秒用法")
    out.append("")
    out.append("1. 先找**后果入口**（T1~T7），不要一上来找模式名——按「出了什么事」而不是「像哪个 bug」分流。")
    out.append("2. 入口内按「症状」列对齐自己的现象；同组候选 ≤6 条，已按风险从高到低排。")
    out.append("3. 打开候选的 skill，**先核「适用」声明**（仓 / 侧别 / 载体不匹配 → 跳过并记理由）。")
    out.append("4. 候选都不像：回 [总览表](README.md#总览表快速索引) 按类别浏览，或用索引 `symptoms` 反查。")
    out.append("")
    out.append("## 症状速查（词 → 入口）")
    out.append("")
    out.append("| 现象词 / 同义词 | 入口 |")
    out.append("|---|---|")
    for q in tri.get("quick_index", []):
        out.append("| %s | %s |" % (q["words"], q["entry"]))
    out.append("")
    for ent in tri.get("entries", []):
        out.append("## %s %s" % (ent["id"], ent["title"]))
        out.append("")
        if ent.get("intro"):
            out.append("> " + ent["intro"])
            out.append("")
        for grp in ent.get("groups", []):
            out.append("### %s" % grp["title"])
            out.append("")
            out.append("| 症状（含同义词） | 候选模式 | 首查动作 | skill |")
            out.append("|---|---|---|---|")
            rows = sorted(grp.get("rows", []),
                          key=lambda r: RISK_ORDER.get((by_id.get(r["fp"], {}).get("risk") or {}).get("level"), 9))
            for row in rows:
                p = by_id[row["fp"]]
                risk = (p.get("risk") or {}).get("level", "?")
                card = p.get("file") or ("patterns/%s/%s.md" % (p["id"][3], p["id"]))
                skill_name, skill_path = skills[p["id"]]
                name = p["name"] if len(p["name"]) <= 30 else p["name"][:29] + "…"
                tagged = "（%s%s）" % (risk, ("，%d 案" % cases[p["id"]]) if cases and p["id"] in cases else "")
                out.append("| %s | [%s %s](%s)%s | %s | [`%s`](%s) |"
                           % (row["symptom"], p["id"], name, card.replace(os.sep, "/"),
                              tagged, row["first"], skill_name, skill_path.replace(os.sep, "/")))
            out.append("")
    out.append("---")
    out.append("")
    out.append("> 维护：新增模式时必须同时登记 `triage_map.json`（否则 C20 报「未覆盖」）；"
               "某组候选超过 6 条说明入口过粗，先拆组而不是硬塞。")
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="症状分诊表生成器（v3.6）")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    try:
        idx, tri, skills = load(root)
    except (OSError, ValueError) as e:
        print("[ERROR] 读取数据源失败：%s" % e)
        return 2
    errs = validate(idx, tri, skills)
    if errs:
        for e in errs:
            print("[ERROR] " + e)
        return 1
    text = render(idx, tri, skills, load_cases(root))
    target = os.path.join(root, "TRIAGE.md")
    if args.check:
        if not os.path.isfile(target):
            print("[ERROR] TRIAGE.md 不存在，请先运行 gen_triage.py")
            return 3
        if read_text(target).replace("\r\n", "\n") != text:
            print("[ERROR] TRIAGE.md 与映射不一致（映射改过但未重跑生成器）")
            return 3
        print("[OK] TRIAGE 校验通过：%d 入口 / %d 条模式全覆盖"
              % (len(tri.get("entries", [])), len(idx["patterns"])))
        return 0
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("[OK] 已生成 %s" % target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
