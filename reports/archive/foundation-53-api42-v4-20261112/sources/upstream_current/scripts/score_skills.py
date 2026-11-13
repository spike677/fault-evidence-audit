#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill 质量评分卡（score_skills.py，v5.0）

做什么
------
用**可复现的文本启发式**给 51 份 SKILL.md 打 10 维分，产出 `skills/SCORECARD.md`。
v4.2 相比 v4.0 的关键变化（v4.3 仅补内容、评分模型不变）：新增 **depth（内容深度）** 维并给到 30 分权重——
v4.0 的九维全是「结构有没有」，49 份被模板拉平后全员 PASS，无法回答问题；
depth 用子型/成因数、公开 issue 数、`文件:行号` 证据数、扫描基线数度量**内容厚度**，
把分数拉开（当前分布约 74~97），再配 3 份人工基准锚定读分。

十维与权重
----------
frontmatter 5 / structure 8 / boundary 8 / checkpoints 8 / specificity 10 /
resource 4 / fit 5 / trust 7 / evidence 15 / **depth 30**   （总分 = Σ(分×权)/10，满分 100）

评级：≥82 PASS ｜ 72~81 CONDITIONAL ｜ <72 REWRITE（进重写清单）

人工基准（固定三档，用于读分，不参与计算）
------------------------------------------
A ≈ 100 最强 ｜ B ≈ 90 强 ｜ C ≈ 70 最弱；三份基准与依据写在 SCORECARD 顶部。

用法
----
python3 scripts/score_skills.py            # 重新生成 skills/SCORECARD.md
python3 scripts/score_skills.py --check    # 校验文件与重算一致（CI 用）
python3 scripts/score_skills.py --json     # 只看分数

退出码：0 通过；2 参数/读取错误；3 --check 不一致
"""

import argparse
import glob
import json
import math
import os
import re
import sys

WEIGHTS = {"frontmatter": 5, "structure": 8, "boundary": 8, "checkpoints": 8,
           "specificity": 10, "resource": 4, "fit": 5, "trust": 7,
           "evidence": 15, "depth": 30}

# 人工基准：名称 → (人类定档, 依据)。分数本身由启发式算出，基准只用于解释刻度。
ANCHORS = {
    "fpb08-fallback-review": (100, "三载体（fallback/插件/fusion pass）× 属性透传，8 条实证，边界表最细"),
    "fpg01-hang-review": (90, "五子型 + 7 条实证 + 超时熔断与复现序列，检视面最深"),
    "fpa13-input-rounding-review": (70, "宽浅档 + 无确认实证 + 无扫描基线，仅一个检查面"),
}

COVER_RE = re.compile(r"^\|\s*\[(FP-[A-G]\d{2})\]\(([^)]+)\)\s*\|[^|]+\|\s*`([^`]+)`\s*\|")


def read(p):
    with open(p, encoding="utf-8-sig") as f:
        return f.read()


def dims(text):
    t = text
    fm = re.search(r"^---\n(.*?)\n---", t, re.S)
    desc = ""
    if fm:
        m = re.search(r'^description:\s*"(.+)"\s*$', fm.group(1), re.M)
        desc = m.group(1) if m else ""
    frontmatter = 10 if (fm and desc and len(desc) <= 200 and "当" in desc) else (6 if fm else 0)

    sections = len(re.findall(r"^## \d+\.", t, re.M))
    structure = 10 if sections >= 10 else round(10.0 * sections / 10, 1)

    boundary = min(10, 4 + len(re.findall(r"^\|\s*\[?FP-[A-G]\d{2}", t, re.M)) * 1.0)

    checkpoints = min(10, 2 + len(re.findall(r"查什么", t)) * 1.2)

    idents = re.findall(r"`[^`\n]{4,}`", t)
    file_lines = re.findall(r"[\w./-]+\.(?:cpp|h|hpp|py|json|md):\d+", t)
    specificity = min(10, 2 + 2 * math.log2(1 + len(idents) / 2.0 + len(file_lines)))

    links = len(re.findall(r"\]\(\.\.?/", t))
    fp_refs = len(set(re.findall(r"FP-[A-G]\d{2}", t)))
    resource = min(10, (links + fp_refs) / 3.0)

    kb = len(t.encode("utf-8")) / 1024.0
    fit = 10 if 18 <= kb <= 30 else (7 if 14 <= kb <= 36 else 4)

    trust = 10
    if not re.search(r"#\d{3,}", t):
        trust -= 4
    if re.search(r"BUG-\d{8}|[A-Za-z]:\\\\", t):
        trust -= 6
    trust = max(0, trust)

    evidence = 0
    if "scan_fp.py --only" in t:
        evidence += 4
    if "verify_lines.py" in t:
        evidence += 3
    if "证据等级" in t and "找不到 ≠ 没有" in t:
        evidence += 3
    evidence = min(10, evidence)

    circ = len(re.findall(r"[①②③④⑤⑥⑦⑧]", t))
    issues = len(set(re.findall(r"#\d{3,}", t)))
    scans = len(re.findall(r"\d+\s*处", t))
    depth_raw = circ * 1.0 + issues * 1.5 + len(file_lines) * 0.8 + scans * 0.8
    depth = min(10, round(depth_raw / 9.0, 1))

    return {"frontmatter": frontmatter, "structure": structure, "boundary": boundary,
            "checkpoints": checkpoints, "specificity": round(specificity, 1),
            "resource": round(resource, 1), "fit": fit, "trust": trust,
            "evidence": evidence, "depth": depth}


def total(d):
    return round(sum(d[k] * WEIGHTS[k] for k in WEIGHTS) / 10.0, 1)


def verdict(score):
    return "PASS" if score >= 82 else ("CONDITIONAL" if score >= 72 else "REWRITE")


def collect(root):
    idx = json.loads(read(os.path.join(root, "fault_patterns_index.json")))
    cov = {}
    for line in read(os.path.join(root, "skills", "README.md")).splitlines():
        m = COVER_RE.match(line)
        if m:
            cov[m.group(3)] = (m.group(1), m.group(2))
    rows = []
    for p in sorted(glob.glob(os.path.join(root, "skills", "*", "*", "SKILL.md"))):
        dn = os.path.basename(os.path.dirname(p))
        if dn not in cov:
            continue
        fp, _rel = cov[dn]
        d = dims(read(p))
        rows.append({"fp": fp, "name": dn, "dims": d, "total": total(d),
                     "verdict": verdict(total(d))})
    rows.sort(key=lambda r: (-r["total"], r["fp"]))
    return idx, rows


def render(idx, rows):
    out = ["# skill 质量评分卡（v5.0）", "",
           "> 由 `scripts/score_skills.py` 生成，**勿手改**；改 skill 后重跑，守门 **C27** 校验覆盖与一致性。",
           "> 十维权重：frontmatter 5 / structure 8 / boundary 8 / checkpoints 8 / specificity 10 / resource 4 / fit 5 / trust 7 / evidence 15 / **depth 30**；"
           "总分 = Σ(分×权)/10；≥82 PASS，72~81 CONDITIONAL，<72 REWRITE。", "",
           "## 人工基准（三档读分锚点，不参与计算）", "",
           "| 基准 | skill | 本卡得分 | 人工定档 | 依据 |",
           "|---|---|---|---|---|"]
    by_name = {r["name"]: r for r in rows}
    for i, (name, (human, why)) in enumerate(ANCHORS.items(), 1):
        r = by_name.get(name)
        out.append("| %s | `%s` | %s | %d | %s |"
                   % ("ABC"[i - 1], name, r["total"] if r else "—", human, why))
    out.append("")
    out.append("读分方式：A 档为上限参照、C 档为下限参照；其余 skill 的分数按这三档相对解读，"
               "**不要拿绝对分跨库比较**（权重是本库定的）。")
    out.append("")
    out.append("## 汇总")
    out.append("")
    n = len(rows)
    for v in ("PASS", "CONDITIONAL", "REWRITE"):
        c = sum(1 for r in rows if r["verdict"] == v)
        out.append("- %s：%d / %d" % (v, c, n))
    vals = sorted(r["total"] for r in rows)
    avg = round(sum(vals) / n, 1) if n else 0
    med = vals[len(vals) // 2] if vals else 0
    out.append("- 平均分：%s ｜ 区间：%s~%s ｜ 中位：%s" % (avg, vals[0] if vals else 0,
                                                          vals[-1] if vals else 0, med))
    weak = [r for r in rows if r["verdict"] == "REWRITE"]
    out.append("- 重写清单：%s" % ("、".join("%s(%s)" % (r["fp"], r["total"]) for r in weak) or "（无）"))
    watch = [r for r in rows if 72 <= r["total"] < 74]
    out.append("- 观察清单（72~73.9，虽达 CONDITIONAL 但仍是最薄一档）：%s"
               % ("、".join("%s(%s)" % (r["fp"], r["total"]) for r in watch) or "（无）"))
    out.append("")
    out.append("## 明细（按总分降序）")
    out.append("")
    out.append("| 编号 | skill | front | struct | bound | check | spec | res | fit | trust | evid | depth | 总分 | 评级 |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        d = r["dims"]
        out.append("| %s | `%s` | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | **%s** | %s |"
                   % (r["fp"], r["name"], d["frontmatter"], d["structure"], d["boundary"],
                      d["checkpoints"], d["specificity"], d["resource"], d["fit"],
                      d["trust"], d["evidence"], d["depth"], r["total"], r["verdict"]))
    out.append("")
    out.append("> 评分是**结构 + 内容厚度启发式**，不评价技术判断的对错；它回答「这份 skill 是否够厚、可执行」，"
               "不回答「它判得准不准」——后者由 `evals/` 与 `run_eval.py` 度量。")
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="skill 质量评分卡（v5.0）")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    try:
        idx, rows = collect(root)
    except (OSError, ValueError) as e:
        print("[ERROR] 读取失败：%s" % e)
        return 2
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    text = render(idx, rows)
    target = os.path.join(root, "skills", "SCORECARD.md")
    if args.check:
        if not os.path.isfile(target):
            print("[ERROR] skills/SCORECARD.md 不存在，请先运行 score_skills.py")
            return 3
        if read(target).replace("\r\n", "\n") != text:
            print("[ERROR] SCORECARD.md 与重算结果不一致（改 skill 后未重跑）")
            return 3
        print("[OK] 评分卡校验通过：%d 份" % len(rows))
        return 0
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    bad = [r["fp"] for r in rows if r["verdict"] == "REWRITE"]
    print("[OK] 已生成 skills/SCORECARD.md：%d 份，重写清单 %s" % (len(rows), "、".join(bad) or "（无）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
