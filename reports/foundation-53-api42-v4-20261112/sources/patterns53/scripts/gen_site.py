#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可视化站点生成器（gen_site.py，v1.0）

定位
----
把库的**结构化真源**渲染成一份可直接双击打开的单文件站点 `site/index.html`：
不需要装环境、不需要起服务、可整份发给同事或贴进评审。

数据源（只读，不新增事实）
--------------------------
- `fault_patterns_index.json`      模式主数据（名称 / 类别 / 风险 / 适用 / 签名 / 症状 / 子型）
- `patterns/FP-X/FP-XX.md`         八要素卡片正文（机理 / 条件 / 表现 / 映射点 / 拦截建议 / 实证）
- `fault_patterns_detect.json`     L2 判据层 + L3 oracle 失效清单
- `fault_patterns_secondary_oracle.json` 第二判据（v6.19，可选）
- `cases/cases.json`               实证案例（触发 / 根因 / 判据 / 修复范式 / 真实锚）
- `triage_map.json`                症状分诊映射
- `pattern_compositions.json`      组合故障
- `README.md`                      规模声明与总览表（实证列）

与仓内其他生成器的关系
----------------------
同 `gen_triage.py` / `gen_cases.py` / `gen_detect.py` 一样是**单向渲染**：本脚本只读真源、
只写 `site/index.html`，不回写任何真源文件。因此不存在「页面改了库」的反向漂移，
唯一风险是「库改了页面没重生成」——由 `--check` 拦下（接入 `ci_gate.py`）。

用法
----
python3 scripts/gen_site.py            # 重新生成 site/index.html
python3 scripts/gen_site.py --check    # 只校验（页面是否为最新），供 CI
python3 scripts/gen_site.py --root <库根> --out <输出路径>

退出码
------
0 = 通过（--check 模式下表示页面最新）
1 = 数据源不合法（缺文件 / JSON 不可解析 / 模式与卡片对不上）
2 = 参数或环境错误
3 = --check 模式下 site/index.html 与重算结果不一致（需重跑）

体积约定
--------
产物约 0.6 MB（数据全内嵌，换取「零依赖可分发」）。这是本仓最大的文件，
因此**不手改产物**：任何展示变更都改本脚本或 `scripts/site/` 下的模板，再重生成。
"""

import argparse
import glob
import json
import os
import re
import sys

CAT_ZH = {
    "accuracy": "精度",
    "compatibility": "功能/兼容",
    "performance": "性能",
    "resource": "资源/内存",
    "test_effectiveness": "测试有效性",
    "engineering": "工程/交付",
    "reliability": "执行可靠性",
}
CAT_ORDER = ["accuracy", "compatibility", "performance", "reliability",
             "resource", "test_effectiveness", "engineering"]

FIELD_MAP = [
    ("元数据", "meta_info"),
    ("适用", "applicability_text"),
    ("故障机理", "mechanism"),
    ("触发条件", "conditions"),
    ("典型表现", "manifest"),
    ("源码审查映射点", "mapping"),
    ("测试拦截建议", "intercept"),
    ("实证案例", "evidence_text"),
    ("关联", "related_text"),
]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_card(path):
    """把一张卡片的 `- **字段**：正文` 结构拆成 dict（与卡片 8 要素格式一一对应）。"""
    txt = read(path)
    lines = txt.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else ""
    body = {"extras": []}
    cur_key, cur_buf = None, []

    def assign(key, val):
        k = key.replace("**", "").strip()
        for zh, en in FIELD_MAP:
            if k.startswith(zh):
                if "故障机理" in k and "（" in k:
                    val = k[k.index("（"):] + "：" + val
                body[en] = val
                return
        if "检测签名" in k:
            body["signatures_text"] = val
        elif "审查关键词" in k:
            body["keywords_text"] = val
        elif "子型划分" in k:
            body["subtypes_text"] = val
        elif "实证状态" in k:
            body["evidence_status"] = val
        else:
            body["extras"].append({"k": k, "v": val})

    def flush():
        nonlocal cur_key, cur_buf
        if cur_key is None:
            return
        val = "\n".join(cur_buf).strip()
        if val:
            assign(cur_key, val)
        cur_key, cur_buf = None, []

    for ln in lines[1:]:
        if ln.startswith("> "):
            continue
        m = re.match(r"^- \*\*(.+)$", ln)
        if m:
            flush()
            raw = m.group(1)
            i = raw.find("**")
            key = raw[:i] if i >= 0 else raw
            rest = raw[i + 2:] if i >= 0 else ""
            m2 = re.match(r"^\s*(（[^）]*）)?\s*[：:]\s*(.*)$", rest)
            if m2:
                cur_key = key + (m2.group(1) or "")
                cur_buf = [m2.group(2)]
            else:
                cur_key = key
                cur_buf = [rest.lstrip("（").rstrip("）")]
            continue
        if cur_key is not None:
            cur_buf.append(ln)
    flush()
    return title, body


def load_toc(root):
    """README 总览表：取「实证」列（页面上与索引 evidence 互为佐证）。"""
    md = read(os.path.join(root, "README.md"))
    rows = {}
    for ln in md.splitlines():
        m = re.match(r"^\|\s*\[(FP-[A-G]\d{2})\]\([^)]*\)\s*\|(.+)\|\s*$", ln)
        if not m:
            continue
        cells = [c.strip() for c in m.group(2).split("|")]
        if len(cells) >= 6:
            rows[m.group(1)] = {
                "name": cells[0],
                "trigger": cells[5],
                "evidence": cells[6] if len(cells) > 6 else "",
            }
    return rows


def build_payload(root):
    idx = load_json(os.path.join(root, "fault_patterns_index.json"))
    cases_doc = load_json(os.path.join(root, "cases", "cases.json"))
    detect_doc = load_json(os.path.join(root, "fault_patterns_detect.json"))
    triage = load_json(os.path.join(root, "triage_map.json"))
    comp_doc = load_json(os.path.join(root, "pattern_compositions.json"))
    toc = load_toc(root)

    sec_path = os.path.join(root, "fault_patterns_secondary_oracle.json")
    sec_doc = load_json(sec_path) if os.path.exists(sec_path) else None

    cases_by_fp = {}
    for c in cases_doc["cases"]:
        cases_by_fp.setdefault(c["fp_id"], []).append(c)

    patterns = []
    for p in idx["patterns"]:
        fp = p["id"]
        card = os.path.join(root, p["file"].replace("/", os.sep))
        if not os.path.exists(card):
            raise ValueError("模式 %s 的卡片文件不存在：%s" % (fp, p["file"]))
        title, body = parse_card(card)
        if not body.get("mechanism"):
            raise ValueError("模式 %s 卡片缺「故障机理」字段：%s" % (fp, p["file"]))
        app = p.get("applicability") or {}
        t = toc.get(fp, {})
        patterns.append({
            "id": fp,
            "name": p["name"],
            "file": p.get("file", ""),
            "cat": p["category"],
            "catZh": CAT_ZH.get(p["category"], p["category"]),
            "s": p["risk"]["s"], "o": p["risk"]["o"], "level": p["risk"]["level"],
            "score": p["risk"]["s"] * p["risk"]["o"],
            "depth": p.get("depth", ""),
            "status": p.get("status", ""),
            "trigger": app.get("trigger", ""),
            "triggerZh": t.get("trigger", ""),
            "repos": app.get("repos", []),
            "sides": app.get("sides", []),
            "carriers": app.get("carriers", []),
            "enabled": app.get("enabled", True),
            "evidence": p.get("evidence", []),
            "tocEvidence": t.get("evidence", ""),
            "signatures": p.get("signatures", []),
            "keywords": p.get("keywords", []),
            "absence": p.get("absence_signatures", []),
            "broad": p.get("broad_signatures", []),
            "logSig": p.get("log_signatures", []),
            "symptoms": p.get("symptoms", []),
            "detectors": p.get("detectors", []),
            "related": p.get("related", []),
            "subtypes": p.get("subtypes", []) or [],
            "waiver": p.get("yield_waiver", ""),
            "detect": p.get("detect"),
            "detectability": p.get("detectability"),
            "secondary": (sec_doc or {}).get("patterns", {}).get(fp),
            "body": body,
            "caseCount": len(cases_by_fp.get(fp, [])),
        })

    slim_cases = []
    for c in cases_doc["cases"]:
        slim_cases.append({
            "id": c["case_id"], "fp": c["fp_id"], "title": c["title"],
            "subtype": c.get("subtype"), "trigger": c.get("trigger", ""),
            "root": c.get("root_cause", ""), "fix": c.get("fix_pattern", ""),
            "code": c.get("fix_pattern_code", ""), "repro": c.get("min_repro", ""),
            "evidence": c.get("evidence", ""), "issues": c.get("issues", []),
            "skill": c.get("skill", ""),
            "criteria": c.get("criteria", {}),
            "anchors": c.get("verified_anchors", []) or [],
            "paired": c.get("paired_primitives"),
        })

    meta = {
        "version": idx.get("version"),
        "updated": idx.get("updated"),
        "sourceVersion": idx.get("source_version"),
        "layout": idx.get("source_layout"),
        "gates": idx.get("gates"),
        "nPatterns": len(patterns),
        "nCases": len(slim_cases),
        "cats": CAT_ORDER,
        "catZh": CAT_ZH,
        "riskRubric": idx.get("risk_rubric"),
        "businessImpact": idx.get("business_impact"),
        "applicabilityVocab": idx.get("applicability_vocab"),
        "consumers": idx.get("consumers", []),
        "caseStats": cases_doc.get("stats", {}),
        "detectVersion": detect_doc.get("version"),
        "detectUpdated": detect_doc.get("updated"),
        "nL3": sum(len(v) for v in detect_doc["oracle_failures"]["by_oracle"].values()),
        "nSkills": len(glob.glob(os.path.join(root, "skills", "FP-*", "*"))),
        "nEvals": len(glob.glob(os.path.join(root, "evals", "*"))),
        "nSecondary": len(sec_doc["patterns"]) if sec_doc else 0,
        "secondaryVersion": sec_doc.get("version") if sec_doc else "",
        "secondaryKinds": sec_doc.get("kinds") if sec_doc else {},
        "secondaryPurpose": sec_doc.get("purpose") if sec_doc else "",
        "detectabilityRubric": idx.get("detectability_rubric"),
    }

    return {
        "meta": meta,
        "patterns": patterns,
        "cases": slim_cases,
        "triage": triage,
        "l3": detect_doc["oracle_failures"],
        "detectVocab": detect_doc.get("vocab", {}),
        "secondary": sec_doc,
        "compositions": comp_doc.get("compositions", []),
    }


def render(root, payload):
    """把模板、样式、脚本与数据合成单文件 HTML。"""
    tpl_dir = os.path.join(root, "scripts", "site")
    html = read(os.path.join(tpl_dir, "index.html"))
    app = read(os.path.join(tpl_dir, "app.js"))
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    meta = payload["meta"]
    n_sig = sum(len(p.get("signatures") or []) for p in payload["patterns"])

    out = html.replace("__DATA__", "window.__FP__ = " + data + ";")
    out = out.replace("__APP__", app)
    for k, v in (
        ("__VERSION__", meta.get("version") or ""),
        ("__UPDATED__", meta.get("updated") or ""),
        ("__N__", str(meta["nPatterns"])),
        ("__NC__", str(meta["nCases"])),
        ("__SIG__", str(n_sig)),
    ):
        out = out.replace(k, v)

    # 模板占位符检查：形如 __VERSION__ / __DATA__ 的全大写占位符。
    # 注意 `window.__FP__` 是页面的全局变量名，不是占位符，须排除。
    left = [m for m in re.findall(r"__[A-Z]+__", out) if m != "__FP__"]
    if left:
        raise ValueError("模板占位符未全部替换：%s" % sorted(set(left)))
    return out


def main():
    ap = argparse.ArgumentParser(description="生成 site/index.html（库的可视化单文件站点）")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="库根目录（默认为本脚本上一级）")
    ap.add_argument("--out", default=None, help="输出路径（默认 <root>/site/index.html）")
    ap.add_argument("--check", action="store_true", help="只校验页面是否最新，不写文件")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    out_path = args.out or os.path.join(root, "site", "index.html")

    try:
        payload = build_payload(root)
        content = render(root, payload)
    except FileNotFoundError as e:
        print("[ERROR] 缺少数据源：%s" % e, file=sys.stderr)
        return 2
    except (json.JSONDecodeError, ValueError) as e:
        print("[ERROR] 数据源不合法：%s" % e, file=sys.stderr)
        return 1

    if args.check:
        if not os.path.exists(out_path):
            print("[FAIL] 页面不存在，需先运行 python3 scripts/gen_site.py", file=sys.stderr)
            return 3
        old = read(out_path)
        if old != content:
            print("[FAIL] site/index.html 与重算结果不一致（库已变更，需重跑 gen_site.py）",
                  file=sys.stderr)
            return 3
        print("[OK] site/index.html 最新（v%s，%d 模式 / %d 案例，%.0f KB）"
              % (payload["meta"]["version"], payload["meta"]["nPatterns"],
                 payload["meta"]["nCases"], len(content.encode("utf-8")) / 1024))
        return 0

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print("[OK] 已生成 %s（v%s，%d 模式 / %d 案例 / %d 第二判据，%.0f KB）"
          % (os.path.relpath(out_path, root), payload["meta"]["version"],
             payload["meta"]["nPatterns"], payload["meta"]["nCases"],
             payload["meta"]["nSecondary"], len(content.encode("utf-8")) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
