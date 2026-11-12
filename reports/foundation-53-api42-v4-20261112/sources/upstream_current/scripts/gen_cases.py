#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
案例库机读化生成器（gen_cases.py，v1.1，v5.6）

定位
----
把深度档 skill 里**人读的**「已知缺陷案例库」（v5.1）与「实证加深」（v5.4）的
「反向排除项 / 真实修复锚」抽成**机读的** `cases/cases.json`：每条案例给「触发条件 →
根因 → 可执行判据（定位锚 + 检查动作 + 反证排除）」三段结构化字段，并把 §「实证加深」
实测的**真实修复锚**（`文件:行号 @commit`）回填为 `verified_anchors`（v5.6），供
`scan_fp.py --cases`（候选回挂已知案例）与 `gen_triage.py`（分诊表标注已立案数）消费。

数据源（只读，不新增事实）
--------------------------
- `skills/FP-*/<name>/SKILL.md`：`## N. 已知缺陷案例库` 节内的 `### 案例 N｜…` 块
  （字段标签：触发条件 / 根因 / 修复范式 / 针对性发现 / 最小复现锚 / 实证）；
- 同文件 `## N. 实证加深（v5.4）` 节：`### N.M 反向排除项`（负向证据要求表 →
  `reverse_exclusions`）与表头含「真实锚」的表（真实修复锚 → 案例的 `verified_anchors`）；
- `patterns/FP-G/FP-G02.md`：同步原语配对表 → `sync_pairs`（FP-G02 专属）；
- `fault_patterns_index.json`：`updated` / `version` / `depth`（决定收录范围）。

素材边界（硬约束，同 skills/README 编写规范第 11/12 条）
------------------------------------------------------
本脚本**只做抽取与结构化**，不生成任何新的 issue 编号、行号或路径——`issues` 直接
来自案例文本里的 `#NNN`，`locators` 直接来自文本里的 `文件:行号` 字面量，
`paired_primitives` 直接来自案例文本里的同步原语 token。抽不到即为空，
**不得臆造**；`issues` 的回链由守门 C33 复核（须能在模式卡语料中找到）。

用法
----
python3 scripts/gen_cases.py            # 校验并重写 cases/cases.json
python3 scripts/gen_cases.py --check    # 只校验（数据源合法 + cases.json 最新），供 CI

退出码
------
0 = 通过（--check 模式下表示文件最新且数据源合法）
1 = 数据源不合法（深度档 skill 缺案例库 / 案例块字段缺失）
2 = 参数或环境错误
3 = --check 模式下 cases.json 与重算结果不一致（需重跑）
"""

import argparse
import json
import os
import re
import sys

SCHEMA_VERSION = "1.0"

CASE_SEC_RE = re.compile(r"^##\s+\d+\.\s*已知缺陷案例库")
CASE_HDR_RE = re.compile(r"^###\s+案例\s*(\d+)\s*[｜|]\s*(.+?)\s*$")
BULLET_RE = re.compile(
    r"^[-*]\s*\*\*(触发条件|触发|根因|修复范式|针对性发现|最小复现锚|实证)[^：]{0,24}：\s*(.*)$")
# 字段标签词表存在 A 组「触发条件/根因（具体路径）」与 B 组「触发/根因」两种写法，统一归一到标准名
LABEL_MAP = {"触发条件": "触发条件", "触发": "触发条件", "根因": "根因", "修复范式": "修复范式",
             "针对性发现": "针对性发现", "最小复现锚": "最小复现锚", "实证": "实证"}
EXCL_SEC_RE = re.compile(r"^###\s+\d+\.\d+\s*反向排除项")
DEEP_SEC_RE = re.compile(r"^##\s+\d+\.\s*实证加深")
REPO_RE = re.compile(r"\b(ops-cv|ops-nn|ops-math|ops-transformer|op-plugin|hccl)\b")
SHA_RE = re.compile(r"@([0-9a-f]{5,40})\b")
SUBTYPE_RE = re.compile(r"子型\s*([①②③④⑤])")
ISSUE_RE = re.compile(r"#\d{3,}")
FILELINE_RE = re.compile(
    r"([A-Za-z0-9_][\w./\-]*\.(?:cpp|cc|cxx|c|hpp|hxx|hh|h|py|json|asc|inc|txt))"
    r"(?::(\d+(?:[-–,/]\d+)*))?")
EDGE_OK = re.compile(r"^(?:V|S|MTE1|MTE2|MTE3|FIX)(?:_(?:V|S|MTE1|MTE2|MTE3|FIX)){1,2}$")

# 同步原语配对表（FP-G02 专属；取自 patterns/FP-G/FP-G02.md 的「检测签名 / 源码审查映射点」段）
SYNC_PAIRS_CANON = [
    {"a": "SetFlag<HardEvent::X>", "b": "WaitFlag<HardEvent::X>", "kind": "event",
     "note": "同一事件域的 set/wait 次数与分支须配平（只 set 不 wait / wait 多于 set 即失衡）"},
    {"a": "AllocEventID<HardEvent::X>", "b": "ReleaseEventID<HardEvent::X>", "kind": "event_id",
     "note": "申请与释放成对，且不得在循环体内申请（事件池有限，每迭代申请即泄漏）"},
    {"a": "CrossCoreSetFlag<mode,pipe>", "b": "CrossCoreWaitFlag<mode,pipe>", "kind": "cross_core",
     "note": "mode+flagId 须让等待方感知全部参与核（双 AIV 的 AIV0/AIV1 都要覆盖）"},
    {"a": "SyncAll<...>", "b": "SetScheduleMode(1)", "kind": "schedule",
     "note": "kernel 用 SyncAll 合并各核结果时，host 侧须设 schedule_mode=1 保证核同时驻留"},
]

COVER_RE = re.compile(r"^\|\s*\[(FP-[A-G]\d{2})\]\(([^)]+)\)\s*\|[^|]+\|\s*`([^`]+)`\s*\|")


def read_text(p):
    with open(p, encoding="utf-8-sig") as f:
        return f.read()


def load_skill_map(root):
    """skills/README.md 覆盖表 → {fp_id: (skill_name, SKILL.md 相对路径)}。"""
    out = {}
    p = os.path.join(root, "skills", "README.md")
    if not os.path.isfile(p):
        return out
    for line in read_text(p).splitlines():
        m = COVER_RE.match(line)
        if m:
            out[m.group(1)] = (m.group(3), os.path.normpath(os.path.join("skills", m.group(2))))
    return out


def section(lines, start_re):
    """返回 (起始行, 结束行) 区间；未命中返回 None。"""
    s = None
    for i, l in enumerate(lines):
        if start_re.match(l):
            s = i
            break
    if s is None:
        return None
    e = len(lines)
    for j in range(s + 1, len(lines)):
        if lines[j].startswith("## "):
            e = j
            break
    return s, e


def parse_exclusions(lines):
    """抽 `### N.M 反向排除项` 下的负向证据表 → [{item, evidence}]（无则 []）。"""
    sec = section(lines, EXCL_SEC_RE)
    if sec is None:
        return []
    rows = []
    for l in lines[sec[0]:sec[1]]:
        if not l.strip().startswith("|"):
            continue
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= set("-: ") or cells[0].startswith("排除项"):
            continue
        rows.append({"item": cells[0], "evidence": cells[1]})
    return rows


def parse_deep(lines):
    """§「实证加深（v5.4）」→ (锚表, repo, commit)。

    锚表 = {issue(#NNN): [{file, lines, commit, repo, note}]}。扫描本节内**所有**表头含
    「真实锚」的表，逐行抽取：issue 取该行**任意位置**的 `#NNN`；锚取「真实锚」列，若该列
    只写「同路径 :行号」则从同行其它单元格**回借文件名**（行号仍取锚列）。抽不到即不登记。

    **repo / commit 必须逐行判定（v6.19 修正）**：原实现取整节的**第一个** `ops-*` 与
    **第一个** `@sha` 套给本节全部行，导致同一表格里混排多个仓时批量串味——实测把
    `ops-math` 的 `math/arg_max_v2/...` 记成 `ops-nn`，把 ops-math/ops-transformer 的锚
    统一记成 ops-nn 的 `a7539b`（该 sha 只在 ops-nn 存在）。现在：
    ① 行内出现 `ops-xx` 时以该行为准（`**`ops-math`**`、`\`ops-math\`` 都可识别）；
    ② 行内出现 `@<sha>` 时覆盖节级默认 commit；
    ③ 都没有才回退到节级默认，并在 note 里保留原文。
    """
    sec = section(lines, DEEP_SEC_RE)
    if sec is None:
        return {}, None, None
    body = lines[sec[0]:sec[1]]
    text = "\n".join(body)
    m_sha, m_repo = SHA_RE.search(text), REPO_RE.search(text)
    default_commit = m_sha.group(1) if m_sha else None
    default_repo = m_repo.group(1) if m_repo else None

    anchors, header = {}, None
    for l in body:
        if not l.strip().startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        if set("".join(cells)) <= set("-: |"):
            continue
        if header is None:
            header = cells
            continue
        issues = ISSUE_RE.findall(l)
        if not issues:
            continue
        idxs = [k for k, c in enumerate(header) if "真实锚" in c]
        if not idxs:
            continue  # v6.19：回到「只认真实锚表」。放宽到全表会把案例正文/示例代码里的
                      # 文件名（如 #1577 的通用 block 实现）误当锚，产出 4 条假锚
        cand = [cells[k] for k in idxs if k < len(cells)]
        got = next((case_locators(c) for c in cand if case_locators(c)), [])
        if not got:
            files = [x["file"] for c in cells for x in case_locators(c)]
            lt = [m for c in cand for m in re.findall(r":(\d+(?:[-–,/]\d+)*)", c)]
            if files and lt:
                got = [{"file": files[0], "lines": "/".join(lt)}]
        if not got:
            continue
        # ---- 逐行判定 repo / commit（见 docstring）----
        row_repo = default_repo
        row_commit = default_commit
        row_repo_hit = REPO_RE.search(l)
        if row_repo_hit:
            row_repo = row_repo_hit.group(1)
        row_sha_hit = SHA_RE.search(l)
        if row_sha_hit:
            row_commit = row_sha_hit.group(1)
        notes = cells[-1]
        for iss in issues:
            for g in got:
                anchors.setdefault(iss, []).append(
                    {"file": g["file"], "lines": g["lines"], "commit": row_commit,
                     "repo": row_repo, "note": notes})
    return anchors, default_repo, default_commit


def parse_block(block_lines):
    """案例块 → 字段字典（含修复范式代码围栏）。"""
    fields, codes = {}, {}
    cur = None
    fence = None
    for l in block_lines:
        if fence is not None:
            if l.strip().startswith("```"):
                fence = None
            else:
                codes[cur] = (codes.get(cur, "") + ("\n" if codes.get(cur) else "") + l)
            continue
        m = BULLET_RE.match(l)
        if m:
            cur = LABEL_MAP[m.group(1)]
            fields[cur] = m.group(2).strip()
            continue
        if cur is not None and l.strip().startswith("```"):
            fence = cur
            continue
        if cur is not None and l.strip():
            fields[cur] = (fields[cur] + "\n" + l.strip()).strip()
    return fields, codes


def case_locators(text):
    out, seen = [], set()
    for m in FILELINE_RE.finditer(text):
        key = (m.group(1), m.group(2) or "")
        if key in seen:
            continue
        seen.add(key)
        out.append({"file": m.group(1), "lines": m.group(2) or ""})
    return out


def sync_pairs_of(text):
    """从案例文本抽同步原语配对（只抽取，不新增）。"""
    pairs, seen = [], set()

    def add(a, b, kind, src):
        k = (a, b, kind)
        if k in seen:
            return
        seen.add(k)
        pairs.append({"a": a, "b": b, "kind": kind, "source": src})

    domains = set(re.findall(r"HardEvent::(\w+)", text))
    domains |= {e for e in re.findall(r"`([A-Z0-9_]+)`", text) if EDGE_OK.match(e)}
    domains |= {"_".join(p) for p in re.findall(r"\b([A-Z0-9]{1,4})→([A-Z0-9]{1,4})\b", text)
                if EDGE_OK.match(p[0] + "_" + p[1])}
    for d in sorted(domains):
        add("SetFlag<HardEvent::%s>" % d, "WaitFlag<HardEvent::%s>" % d, "event", "case")
    if not domains and re.search(r"\bSetFlag\b", text) and re.search(r"\bWaitFlag\b", text):
        add("SetFlag<HardEvent::X>", "WaitFlag<HardEvent::X>", "event", "case")
    if re.search(r"AllocEventID", text):
        add("AllocEventID<HardEvent::X>", "ReleaseEventID<HardEvent::X>", "event_id", "case")
    for c in sorted(set(re.findall(r"\b([A-Z][A-Z0-9_]*_EVENT)\b", text))):
        add(c, "（同类信号常量）", "event_id_conflict", "case")
    if re.search(r"CrossCoreSetFlag|CrossCoreWaitFlag", text):
        add("CrossCoreSetFlag<mode,pipe>", "CrossCoreWaitFlag<mode,pipe>", "cross_core", "case")
    if re.search(r"\bSyncAll\b", text):
        add("SyncAll<...>", "SetScheduleMode(1)", "schedule", "case")
    for pipe in sorted(set(re.findall(r"PipeBarrier\s*<\s*PIPE_(\w+)", text))):
        add("（同管线两次内存访问）", "PipeBarrier<PIPE_%s>" % pipe, "same_pipe_barrier", "case")
    return pairs


def parse_skill(root, fp_id, skill_name, rel_file):
    skill_md = os.path.join(root, rel_file)
    if not os.path.isfile(skill_md):
        return [], ({}, None, None)
    lines = read_text(skill_md).replace("\r\n", "\n").split("\n")
    deep = parse_deep(lines)

    # 案例来源优先级（v6.24，渐进式披露第 3 层）：
    #   ① <skill>/references/case-library.md —— 案例库已外置时以它为准；
    #   ② 否则回落到 SKILL.md 内的 `## N. 已知缺陷案例库` 节（存量 51 份的形态）。
    # 约束：references 文件里必须用**一级标题 `# 案例库`** 起头，案例块仍是 `### 案例 N｜…`，
    # 这样 section() 以「下一个 `## `」为界才能圈住整段；缺该文件即静默回落，不报错。
    case_lines, sec = lines, section(lines, CASE_SEC_RE)
    ref_cases = os.path.join(os.path.dirname(skill_md), "references", "case-library.md")
    if os.path.isfile(ref_cases):
        ref_lines = read_text(ref_cases).replace("\r\n", "\n").split("\n")
        if any(CASE_HDR_RE.match(l) for l in ref_lines):
            case_lines, sec = ref_lines, (0, len(ref_lines))

    if sec is None:
        return [], deep
    blocks, cur = [], None
    for l in case_lines[sec[0] + 1:sec[1]]:
        m = CASE_HDR_RE.match(l)
        if m:
            if cur:
                blocks.append(cur)
            cur = {"n": int(m.group(1)), "title": m.group(2), "lines": []}
        elif cur is not None:
            cur["lines"].append(l)
    if cur:
        blocks.append(cur)

    cases = []
    for b in blocks:
        fields, codes = parse_block(b["lines"])
        blob = "\n".join([b["title"]] + b["lines"])
        issues = sorted(set(ISSUE_RE.findall(b["title"] + "\n" + fields.get("实证", ""))))
        sub = SUBTYPE_RE.search(b["title"])
        case = {
            "case_id": "%s-C%d" % (fp_id, b["n"]),
            "fp_id": fp_id,
            "skill": skill_name,
            "title": b["title"].strip(),
            "subtype": sub.group(1) if sub else None,
            "trigger": fields.get("触发条件", ""),
            "root_cause": fields.get("根因", ""),
            "criteria": {
                "locators": case_locators(blob),
                "check": [x.strip() for x in re.split(r"[①②③④⑤⑥⑦⑧⑨⑩]", fields.get("针对性发现", "")) if x.strip()],
            },
            "fix_pattern": fields.get("修复范式", ""),
            "fix_pattern_code": codes.get("修复范式", ""),
            "min_repro": fields.get("最小复现锚", ""),
            "evidence": fields.get("实证", ""),
            "issues": issues,
        }
        if fp_id == "FP-G02":
            case["paired_primitives"] = sync_pairs_of(blob)
        # 真锚回填（v5.6）：把 §「实证加深」§N.1 的真实锚按 issue 挂到案例上；抽不到即空数组。
        # 同一 file:lines@commit 被多个 issue 命中时只保留一条（issue 取首个命中者）。
        va, seen_va = [], set()
        for iss in issues:
            for a in deep[0].get(iss, []):
                key = (a["file"], a["lines"], a.get("commit"))
                if key in seen_va:
                    continue
                seen_va.add(key)
                va.append(dict(a, issue=iss))
        case["verified_anchors"] = va
        cases.append(case)
    return cases, deep


def collect(root):
    idx = json.loads(read_text(os.path.join(root, "fault_patterns_index.json")))
    smap = load_skill_map(root)
    depth_ids = [p["id"] for p in idx.get("patterns", []) if (p.get("depth") == "深度")]
    reverse = {}
    evidence_commits = {}
    cases = []
    for fp_id in depth_ids:
        if fp_id not in smap:
            continue
        name, rel = smap[fp_id]
        got, deep = parse_skill(root, fp_id, name, rel)
        cases.extend(got)
        repo, commit = deep[1], deep[2]
        if repo and commit:
            evidence_commits[repo] = commit
        skill_md = os.path.join(root, rel)
        if os.path.isfile(skill_md):
            rl = read_text(skill_md).replace("\r\n", "\n").split("\n")
            ex = parse_exclusions(rl)
            if ex:
                reverse[fp_id] = ex
    return idx, cases, reverse, depth_ids, evidence_commits


def render(idx, cases, reverse, depth_ids, evidence_commits):
    by_fp = {}
    for c in cases:
        by_fp[c["fp_id"]] = by_fp.get(c["fp_id"], 0) + 1
    out = {
        "schema_version": SCHEMA_VERSION,
        "library_version": idx.get("version"),
        "updated": idx.get("updated"),
        "generated_by": "scripts/gen_cases.py",
        "source": "skills/FP-*/*/SKILL.md §「已知缺陷案例库（v5.1）」+ §「实证加深（v5.4）反向排除项/真实修复锚」"
                  "；patterns/FP-G/FP-G02.md（同步配对表）",
        "evidence_commits": dict(sorted(evidence_commits.items())),
        "sync_pairs": {"FP-G02": SYNC_PAIRS_CANON},
        "reverse_exclusions": dict(sorted(reverse.items())),
        "stats": {
            "total": len(cases),
            "depth_patterns": len(depth_ids),
            "by_fp": dict(sorted(by_fp.items())),
            "with_issue": sum(1 for c in cases if c["issues"]),
            "with_verified_anchor": sum(1 for c in cases if c["verified_anchors"]),
            "verified_anchors": sum(len(c["verified_anchors"]) for c in cases),
            "sync_cases": sum(1 for c in cases if "paired_primitives" in c),
        },
        "cases": cases,
    }
    return json.dumps(out, ensure_ascii=False, indent=2) + "\n"


def check(idx, cases, depth_ids):
    errs = []
    seen = set()
    by_fp = {c["fp_id"] for c in cases}
    for c in cases:
        if c["case_id"] in seen:
            errs.append("case_id 重复：%s" % c["case_id"])
        seen.add(c["case_id"])
        if not re.match(r"^FP-[A-G]\d{2}-C\d+$", c["case_id"]):
            errs.append("case_id 格式非法：%s" % c["case_id"])
        if not c["trigger"] or not c["root_cause"]:
            errs.append("%s 缺触发条件或根因（案例块字段不全）" % c["case_id"])
    miss = [f for f in depth_ids if f not in by_fp]
    if miss:
        errs.append("以下深度档模式无案例（案例库缺失）：%s" % "、".join(miss))
    for c in cases:
        if c["fp_id"] == "FP-G02" and "paired_primitives" not in c:
            errs.append("%s 为同步模式案例但缺 paired_primitives 字段" % c["case_id"])
        va = c.get("verified_anchors")
        if not isinstance(va, list):
            errs.append("%s 的 verified_anchors 非 list" % c["case_id"])
            continue
        for a in va:
            if not re.match(r"^[0-9a-f]{5,40}$", a.get("commit") or ""):
                errs.append("%s 真实锚 commit 非法（须为 5-40 位 hex）：%r" % (c["case_id"], a.get("commit")))
            if not FILELINE_RE.fullmatch(a.get("file") or ""):
                errs.append("%s 真实锚 file 非法：%r" % (c["case_id"], a.get("file")))
    return errs


def main():
    ap = argparse.ArgumentParser(description="案例库机读化生成器（v1.0）")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    try:
        idx, cases, reverse, depth_ids, evidence_commits = collect(root)
    except (OSError, ValueError) as e:
        print("[ERROR] 读取数据源失败：%s" % e)
        return 2
    errs = check(idx, cases, depth_ids)
    if errs:
        for e in errs:
            print("[ERROR] " + e)
        return 1
    text = render(idx, cases, reverse, depth_ids, evidence_commits)
    target = os.path.join(root, "cases", "cases.json")
    if args.check:
        if not os.path.isfile(target):
            print("[ERROR] cases/cases.json 不存在，请先运行 gen_cases.py")
            return 3
        if read_text(target).replace("\r\n", "\n") != text:
            print("[ERROR] cases/cases.json 与 skills 案例库不一致（改 skill 后未重跑生成器）")
            return 3
        print("[OK] 案例库校验通过：%d 条案例 / %d 个深度档模式 / 同步案例 %d 条 / 真实锚 %d 个"
              % (len(cases), len(depth_ids),
                 sum(1 for c in cases if c["fp_id"] == "FP-G02"),
                 sum(len(c["verified_anchors"]) for c in cases)))
        return 0
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("[OK] 已生成 %s：%d 条案例 / %d 个深度档模式 / 真实锚 %d 个"
          % (target, len(cases), len(depth_ids),
             sum(len(c["verified_anchors"]) for c in cases)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
