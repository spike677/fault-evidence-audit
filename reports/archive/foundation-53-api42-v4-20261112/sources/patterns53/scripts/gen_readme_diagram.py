#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
README 入口分流图生成器（gen_readme_diagram.py，v1.0）

定位
----
把**结构化真源**渲染成 README 开头的「一张图看懂」区块，解决一个具体问题：
库有 53 模式 / 5 工作流 / 5 类消费入口，但读者进 README 要读上百行才拼得出
「我该走哪条路」。本脚本产出一张分流图 + 一份选路表，放在版本行之后。

与 issue-analysis 那张图的关系
------------------------------
对方是**单线流水线**（定档 → 根因 → 报告），一张 flowchart LR 足够。
本库是**多入口分叉**（现象 / 接口名 / 模式号 / 批量扫），路线并行、终点汇聚，
故画成「四路并行 → 汇聚到 L2/L3 判据 → Bug 卡 + 门禁」，而非单线。

数据源（只读，不新增事实）
--------------------------
- `fault_patterns_index.json`   模式数 / 深度档数 / 版本
- `cases/cases.json`            案例数 / 真实锚数
- `workflows/*.md`              工作流条数与名字（不含 README.md；名字取文件名主干）
- `TRIAGE.md`                   分诊入口数（`## T<数字> ` 入口，与 C20 同一正则）与每组候选行数
- `skills/*/*/SKILL.md`         skill 份数

写回范围
--------
只改 `README.md` 中 `<!-- BEGIN ENTRY-DIAGRAM ... -->` 与 `<!-- END ENTRY-DIAGRAM -->`
之间的内容，**块外一个字都不动**。块不存在则报错退出，不擅自插入。

用法
----
python3 scripts/gen_readme_diagram.py            # 重新生成块内内容
python3 scripts/gen_readme_diagram.py --check    # 只校验（块内是否为最新），供 CI

退出码
------
0 = 通过（--check 模式下表示块内已最新）
1 = 运行错误（README 缺失 / 标记块缺失或不配对）
3 = --check 模式下块内与重算结果不一致（需重跑）
"""

import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, "README.md")

BEGIN_RE = re.compile(r"<!--\s*BEGIN ENTRY-DIAGRAM[^>]*-->")
END_MARK = "<!-- END ENTRY-DIAGRAM -->"


CAP = 6  # 单组候选上限（与 check_fault_patterns.py 的 C20 一致；标题带 [WIDE] 的组可超）


def cap_text(d):
    """按 TRIAGE 实际分组渲染「每组 ≤N 条候选」；宽组例外必须写明，不能写成无例外。"""
    parts = []
    if d["wide_over"]:
        parts.append("%d 个宽组标 [WIDE]，最多 %d 条"
                     % (len(d["wide_over"]), max(r for _t, r in d["wide_over"])))
    if d["nonwide_over"]:
        parts.append("%d 个未标 [WIDE] 的组超限（C20 应报错）" % len(d["nonwide_over"]))
    base = "每组 ≤%d 条候选" % CAP
    return base + ("（%s）" % "；".join(parts) if parts else "")


def read_text(p):
    with open(p, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def collect():
    """从真源取数；任一真源缺失即抛错，绝不退化为硬编码。"""
    idx = json.loads(read_text(os.path.join(ROOT, "fault_patterns_index.json")))
    cases = json.loads(read_text(os.path.join(ROOT, "cases", "cases.json")))

    version = str(idx.get("version") or "")
    n_pat = len(idx.get("patterns") or [])
    n_depth = sum(1 for p in (idx.get("patterns") or []) if p.get("depth") == "深度")
    st = cases.get("stats") or {}
    n_case = st.get("total")
    n_anchor = st.get("verified_anchors")
    if not (version and n_pat and n_case is not None and n_anchor is not None):
        raise SystemExit("真源字段缺失：version/patterns/cases 至少一项为空")

    wf_dir = os.path.join(ROOT, "workflows")
    wf_files = [f for f in sorted(glob.glob(os.path.join(wf_dir, "*.md")))
                if os.path.basename(f) != "README.md"]
    if not wf_files:
        raise SystemExit("workflows/ 下没有任何工作流文件")
    n_wf = len(wf_files)
    wf_names = [os.path.splitext(os.path.basename(f))[0] for f in wf_files]

    triage = read_text(os.path.join(ROOT, "TRIAGE.md")).replace("\r\n", "\n")
    # 入口数用与 check_fault_patterns.py 中 C20 打印相同的那条正则，避免「图上 18、门禁 7」
    n_triage = len(re.findall(r"^## T\d ", triage, re.M))

    # 每组候选行数（`### ` 分组）：上限是 CAP，标题带 [WIDE] 的组显式例外——同 C20 判据
    _grp_title, _grp_rows, _groups = None, 0, []
    for _line in triage.split("\n") + ["### __END__"]:
        if _line.startswith("### "):
            if _grp_title:
                _groups.append((_grp_title, _grp_rows))
            _grp_title, _grp_rows = _line[4:].strip(), 0
        elif _line.startswith("|") and "FP-" in _line:
            _grp_rows += 1
    wide_over = [(t, r) for t, r in _groups if r > CAP and "[WIDE]" in t]
    nonwide_over = [(t, r) for t, r in _groups if r > CAP and "[WIDE]" not in t]

    n_skill = len(glob.glob(os.path.join(ROOT, "skills", "*", "*", "SKILL.md")))

    return {
        "version": version, "n_pat": n_pat, "n_depth": n_depth,
        "n_case": n_case, "n_anchor": n_anchor, "n_wf": n_wf,
        "wf_names": wf_names, "n_triage": n_triage, "n_skill": n_skill,
        "wide_over": wide_over, "nonwide_over": nonwide_over,
    }


def render(d):
    """生成块内全文（含 BEGIN/END 标记）。数字全部来自 d，不写死。"""
    mermaid = f"""```mermaid
flowchart LR
  A["手上只有线索<br/>现象 · 接口名 · 模式号 · 整个仓"] --> B{{"线索够到哪一步"}}
  B -->|"只有现象"| T["TRIAGE 分诊<br/>{d['n_triage']} 入口 · {cap_text(d)}<br/>跑不完 / 报错 / 超差 / 不稳 / 慢 / 内存"]
  B -->|"知道接口名"| O["总览表 / 索引<br/>按类别 · 风险 · 负载筛候选"]
  B -->|"知道模式号"| P["patterns/FP-X/FP-XX.md<br/>单卡机理 + 源码映射点"]
  B -->|"要批量扫"| S["scan_fp 签名扫描<br/>候选行 + 上下文（≠ 缺陷）"]
  T --> W["workflow 任务编排<br/>{d['n_wf']} 条：{(' / '.join(d['wf_names']))}"]
  O --> W
  W --> K["skill 检视清单<br/>{d['n_skill']} 份 · 命中 ≠ 成立"]
  P --> K
  S --> E["候选清单<br/>存在型 · 计数配平 · 状态机"]
  K --> L2["L2 判据<br/>轴 · oracle · 最少用例 · 构造 · 判定"]
  E --> L2
  L2 --> L3["L3 反查<br/>这个 oracle 本身会怎么骗你"]
  L3 --> G{{"证据闸门<br/>正向 + 负向 file:line<br/>置信度 ≥ 70%"}}
  G -->|"成立"| BUG["Bug 卡<br/>S×O 定级 + B 轴业务影响"]
  G -->|"不成立"| X["候选 / 误判台账<br/>写待验证，不下结论"]
  BUG --> R["缺陷报告<br/>对照 {d['n_case']} 条案例 · 锚可复算 · 门禁全绿"]
```"""

    table = f"""**选路表**（按你手上已有的信息选一条，不必全走）：

| 你手上有什么 | 去哪 | 得到什么 |
|---|---|---|
| 只有现象（跑不完 / 超差 / 偶发 / OOM） | [TRIAGE.md](TRIAGE.md) | {d['n_triage']} 个入口；{cap_text(d)} |
| 知道接口名或算子名 | 下方[总览表](#总览表快速索引) | 按类别筛出的候选模式 |
| 知道模式编号 | `patterns/FP-X/FP-XX.md` | 单卡机理 + 映射点 |
| 要批量扫代码仓 | `scripts/scan_fp.py` | 带行号的候选（≠缺陷） |
| 要让 agent 自主挖 | [AGENTS.md](AGENTS.md) | 一页速查：读什么 / 跳过什么 |
| 想先逛一遍全库 | [site/index.html](site/index.html) | 单文件站点，双击即开 |

**库里有什么**（数字由 `scripts/gen_readme_diagram.py` 从真源注入，勿手改）：
{d['n_pat']} 条模式（其中 {d['n_depth']} 条深度档带完整检视 skill）· {d['n_skill']} 份 skill · {d['n_wf']} 条工作流 · {d['n_case']} 条实证案例（{d['n_anchor']} 个真实锚）。"""

    return (f"<!-- BEGIN ENTRY-DIAGRAM（由 scripts/gen_readme_diagram.py 生成，勿手改；"
            f"新鲜度由 ci_gate.py 校验；脚本在位由 C45 守）） -->\n\n"
            f"## 一张图看懂\n\n{mermaid}\n\n{table}\n\n{END_MARK}")


def splice(text, block, check_only=False):
    """把 block 替换进 README 标记区间。返回 (是否变化, 新全文)。"""
    b = BEGIN_RE.search(text)
    e = text.find(END_MARK)
    if not b or e < 0 or e < b.start():
        raise SystemExit("README 中缺 BEGIN/END ENTRY-DIAGRAM 标记（或次序颠倒），"
                         "拒绝擅自插入；请先手动放置空标记块。")
    new = text[:b.start()] + block + text[e + len(END_MARK):]
    return new != text, new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = ap.parse_args()

    if not os.path.isfile(README):
        print("[FAIL] 缺 README.md")
        return 1

    d = collect()
    block = render(d)
    old = read_text(README)
    changed, new = splice(old, block, args.check)

    if args.check:
        if changed:
            print("[FAIL] README 入口分流图与真源不一致（库已变更，需重跑 "
                  "scripts/gen_readme_diagram.py）")
            return 3
        print("[OK] README 入口分流图最新（v%s，%d 模式 / %d 案例 / %d 工作流）"
              % (d["version"], d["n_pat"], d["n_case"], d["n_wf"]))
        return 0

    if changed:
        with open(README, "w", encoding="utf-8", newline="\n") as f:
            f.write(new)
        print("[OK] 已生成 README 入口分流图（v%s，%d 模式 / %d 案例 / %d 工作流 / "
              "%d 入口）" % (d["version"], d["n_pat"], d["n_case"], d["n_wf"], d["n_triage"]))
    else:
        print("[OK] 无需改动（已是最新）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
