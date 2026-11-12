#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L2 判据层生成器：fault_patterns_detect.json → fault_patterns_index.json 的 detect 字段。

**为什么要有这一层**

库原本只有 L1（机理层）：applicability / mechanism / trigger / symptom 说明「为什么会坏」。
但用例设计需要的是「怎么测」——造什么数据、靠什么观测、几条起、怎么判。
缺这一层时：
  - `aclnn-test-design` 的 `pattern_case()` 只能生成「不得复现该现象」的空壳用例；
  - `aclnn-bug-hunt` 只能用 `category` 把 22 条机理迥异的 accuracy 模式一律映射到 precision 线。

L2 不进索引以外的新文件消费面：真源是 `fault_patterns_detect.json`，
本脚本把它合并进 `fault_patterns_index.json` 每个模式的 `detect` 字段，
使既有消费者（只读 index 的脚本）无需改路径即可拿到判据。

用法：

    python3 scripts/gen_detect.py              # 合并并写回 index
    python3 scripts/gen_detect.py --check      # 只校验不写（CI 用，不通过则退出码 1）
    python3 scripts/gen_detect.py --dry-run    # 打印将要写入的内容
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DETECT_PATH = os.path.join(ROOT, "fault_patterns_detect.json")
INDEX_PATH = os.path.join(ROOT, "fault_patterns_index.json")

DETECT_SCHEMA = "ascend-op-fault-patterns/detect@1"

# L2 必填字段。min_cases 允许缺省（默认 1），其余必须显式给出。
REQUIRED_FIELDS = ("axes", "oracle", "signal", "lines", "constructor", "judge", "kill")
OPTIONAL_FIELDS = ("min_cases", "sourced", "note")


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def collect_card_sections(patterns_dir: str) -> Dict[str, Dict[str, str]]:
    """从卡片正文抽取判据相关段落，供交叉校验 L2 是否凭空捏造。"""
    out: Dict[str, Dict[str, str]] = {}
    for fn in sorted(os.listdir(patterns_dir)):
        sub = os.path.join(patterns_dir, fn)
        if not os.path.isdir(sub):
            continue
        for name in sorted(os.listdir(sub)):
            if not name.endswith(".md"):
                continue
            pid = name[:-3]
            with open(os.path.join(sub, name), "r", encoding="utf-8") as f:
                text = f.read()
            secs: Dict[str, str] = {}
            for label in ("测试拦截建议", "源码审查映射点", "典型表现", "故障机理",
                          "检测签名", "触发条件"):
                # 段落名可带括注，如「**测试拦截建议**（v2.16 起…）：」，
                # 故 `**` 与冒号之间允许一段限定长度的说明文字。
                m = re.search(r"\*\*" + label + r"[^*]*\*\*[^：:\n]{0,120}[：:]\s*"
                              r"(.+?)(?=\n- \*\*|\n\n\Z|\Z)", text, re.S)
                if m:
                    secs[label] = re.sub(r"\s+", " ", m.group(1).strip())
            out[pid] = secs
    return out


def validate(detect: Dict[str, Any], index: Dict[str, Any],
             cards: Dict[str, Dict[str, str]]) -> List[str]:
    errs: List[str] = []
    vocab = detect.get("vocab") or {}
    axes_vocab = set((vocab.get("axes") or {}).keys())
    oracle_vocab = set((vocab.get("oracle") or {}).keys())
    signal_vocab = set(((vocab.get("signal") or {}).get("values")) or [])
    line_vocab = set(((vocab.get("line") or {}).get("values")) or [])

    if detect.get("schema") != DETECT_SCHEMA:
        errs.append("schema 不是 %s（实为 %r）" % (DETECT_SCHEMA, detect.get("schema")))

    index_ids = [p.get("id") for p in index.get("patterns", [])]
    detect_list = detect.get("patterns") or []
    detect_ids = [p.get("id") for p in detect_list]

    dup = [x for x in set(detect_ids) if detect_ids.count(x) > 1]
    if dup:
        errs.append("detect 里有重复 id：%s" % ", ".join(sorted(dup)))

    missing = [x for x in index_ids if x not in set(detect_ids)]
    extra = [x for x in detect_ids if x not in set(index_ids)]
    if missing:
        errs.append("索引里有 %d 条模式缺 L2 判据（D1）：%s"
                    % (len(missing), ", ".join(missing)))
    if extra:
        errs.append("detect 里有 %d 条 id 不在索引中：%s"
                    % (len(extra), ", ".join(extra)))

    for p in detect_list:
        pid = p.get("id") or "<无 id>"
        for field in REQUIRED_FIELDS:
            if field not in p:
                errs.append("%s 缺必填字段 %s（D2）" % (pid, field))
        for field in p:
            if field in ("id",) or field in REQUIRED_FIELDS or field in OPTIONAL_FIELDS:
                continue
            errs.append("%s 有未声明字段 %s（D3：新增字段须先进 schema）" % (pid, field))

        axes = p.get("axes") or []
        if not axes:
            errs.append("%s axes 为空（D4）：不知道遍历什么轴的判据不可用" % pid)
        bad_axes = [a for a in axes if a not in axes_vocab]
        if bad_axes:
            errs.append("%s axes 含词表外取值 %s（D5）" % (pid, bad_axes))
        if len(axes) != len(set(axes)):
            errs.append("%s axes 有重复项（D6）" % pid)

        oracle = p.get("oracle") or []
        if not oracle:
            errs.append("%s oracle 为空（D7）：没有观测手段的用例证明不了任何事" % pid)
        bad_oracle = [o for o in oracle if o not in oracle_vocab]
        if bad_oracle:
            errs.append("%s oracle 含词表外取值 %s（D8）" % (pid, bad_oracle))

        sig = p.get("signal")
        if sig not in signal_vocab:
            errs.append("%s signal=%r 不在词表（D9）" % (pid, sig))

        lines = p.get("lines") or []
        if not lines:
            errs.append("%s lines 为空（D10）：必须显式声明归哪条执行线或 none" % pid)
        bad_lines = [l for l in lines if l not in line_vocab]
        if bad_lines:
            errs.append("%s lines 含词表外取值 %s（D11）" % (pid, bad_lines))

        mc = p.get("min_cases", 1)
        if not isinstance(mc, int) or mc < 1:
            errs.append("%s min_cases=%r 必须为正整数（D12）" % (pid, mc))
        elif len(oracle) > 1 and mc < 2:
            # 两种观测手段至少要两条用例才可能都覆盖到
            errs.append("%s 有 %d 种 oracle 但 min_cases=1，覆盖不全（D13）"
                        % (pid, len(oracle)))

        for field in ("constructor", "judge", "kill"):
            v = p.get(field)
            if not isinstance(v, str) or len(v.strip()) < 8:
                errs.append("%s 的 %s 过短或为空（D14）：模板化文案不构成判据" % (pid, field))

        # 交叉校验：L2 声称的 sourced 段落必须在卡片里真实存在
        #
        # 逃逸回灌的中间态例外：`sourced` 全为「逃逸回灌」表示卡片尚未撰写
        # （pattern_proposal.py --apply 先落 L1+L2，卡片由人后补）。
        # 此时跳过 D16/D17，但仍要求 L2 七要素齐备——那部分才是下游真正消费的。
        src = p.get("sourced") or {}
        card = cards.get(pid) or {}
        escape_only = bool(src) and all(
            str(v).strip() == "逃逸回灌" for v in src.values())
        if not card and not escape_only:
            errs.append("%s 找不到卡片文件（D16）" % pid)
            continue
        if escape_only and not card:
            continue
        for field, ref in src.items():
            if field not in REQUIRED_FIELDS and field not in ("constructor",):
                errs.append("%s sourced 引用了未知字段 %s（D15）" % (pid, field))
            # sourced 值形如 "测试拦截建议+实证案例" / "detectors" / "子型划分"
            for token in re.split(r"[+＋、,/]", str(ref)):
                token = token.strip()
                if not token:
                    continue
                if token in card:
                    continue
                if token in ("实证案例", "detectors", "子型划分", "典型表现", "故障机理",
                             "逃逸回灌"):
                    continue  # 这些不是正文小节名，来源已在别处校验
                errs.append("%s sourced[%s]=%r 在卡片正文中找不到对应小节（D17）"
                            % (pid, field, token))

    # 产出率覆盖：axes 与 oracle 不能是全库同一套（否则等于没分型）
    if detect_list:
        axis_sets = {tuple(sorted(p.get("axes") or [])) for p in detect_list}
        if len(axis_sets) < 5:
            errs.append("全库 axes 组合仅 %d 种（D18）：判据未按机理分化" % len(axis_sets))
        oracle_sets = {tuple(sorted(p.get("oracle") or [])) for p in detect_list}
        if len(oracle_sets) < 5:
            errs.append("全库 oracle 组合仅 %d 种（D19）：观测手段未按机理分化" % len(oracle_sets))

    # ---- L3 oracle 失效模式（v6.18）----
    # 为什么要有这一层：L2 说了「靠什么观测」，但没说「这个观测手段本身会怎么骗你」。
    # 实测证据是压倒性的——pitfalls 里有 223 条记录的是判据失效（假 PASS / 假 FAIL / 假绿），
    # 其中 golden-utol 一类就有 63 条。不做这一层，用例设计会按「有 oracle 就等于可信」推进，
    # 而真实情况是「有 oracle 但 oracle 在这个情形下会给出相反结论」。
    of = detect.get("oracle_failures")
    if not isinstance(of, dict):
        errs.append("缺 oracle_failures（L3 失效模式层，D20）")
    else:
        by_oracle = of.get("by_oracle")
        if not isinstance(by_oracle, dict) or not by_oracle:
            errs.append("oracle_failures.by_oracle 为空或类型错（D21）")
        else:
            bad_cat = [c for c in by_oracle if c not in oracle_vocab]
            if bad_cat:
                errs.append("oracle_failures 含词表外类别 %s（D22）" % bad_cat)
            # 被 L2 实际用到的 oracle 类别必须有失效清单——用了却不知道它怎么失效，最危险
            used = {o for p in detect_list for o in (p.get("oracle") or [])}
            uncovered = sorted(used - set(by_oracle))
            if uncovered:
                errs.append("以下 oracle 被 L2 使用但无失效清单（D23）：%s。"
                            "新增观测手段时必须同时登记它会在什么情形下给错结论" % uncovered)
            fail_kinds = set()
            for cat, items in by_oracle.items():
                if not isinstance(items, list) or not items:
                    errs.append("oracle_failures[%s] 不是非空列表（D24）" % cat)
                    continue
                for it in items:
                    if not isinstance(it, dict):
                        errs.append("oracle_failures[%s] 含非对象条目（D25）" % cat)
                        continue
                    kid = str(it.get("id") or "").strip()
                    # 编号必须能在上游 pitfalls 里 grep 到；库不存全文，但编号是引用契约
                    if not re.fullmatch(r"K\d{1,4}", kid):
                        errs.append("oracle_failures[%s] 编号非法 %r（D26）" % (cat, kid))
                    if not str(it.get("rule") or "").strip():
                        errs.append("oracle_failures[%s] %s 缺 rule（D27）" % (cat, kid))
                    fk = str(it.get("fail") or "").strip()
                    if not fk:
                        errs.append("oracle_failures[%s] %s 缺 fail 类型（D28）" % (cat, kid))
                    fail_kinds.add(fk)
            # 失效类型必须覆盖「假 PASS」与「假 FAIL」两类——只记一类说明只踩过半边
            for want in ("假 PASS", "假 FAIL"):
                if not any(want in k or k in want for k in fail_kinds):
                    errs.append("oracle_failures 未覆盖「%s」类失效（D29）："
                                "只记一类说明策展不全" % want)

    return errs


def merge_into_index(index: Dict[str, Any], detect: Dict[str, Any]) -> Dict[str, Any]:
    """把 L2 写进每个模式的 detect 字段；保持原有字段与顺序，detect 追加在末尾。"""
    by_id = {p["id"]: p for p in detect.get("patterns") or []}
    for entry in index.get("patterns", []):
        pid = entry.get("id")
        d = by_id.get(pid)
        if not d:
            continue
        payload = {k: v for k, v in d.items() if k != "id"}
        payload.setdefault("min_cases", 1)
        entry["detect"] = payload
    index["detect_layer"] = {
        "schema": detect.get("schema"),
        "version": detect.get("version"),
        "source": "fault_patterns_detect.json",
        "generated_by": "scripts/gen_detect.py",
        # L3 失效模式是「按 oracle 类别」的全库共享表，不挂在单个模式上——
        # 复制进 52 条模式会产生 52 份可能不同步的副本。
        "oracle_failures": detect.get("oracle_failures"),
    }
    return index


def write_index(index: Dict[str, Any]) -> None:
    """按库既有风格回写：2 空格缩进，每条模式压成一行。"""
    header = {k: v for k, v in index.items() if k != "patterns"}
    lines = ["{"]
    for k, v in header.items():
        lines.append('  %s: %s,' % (json.dumps(k, ensure_ascii=False),
                                   json.dumps(v, ensure_ascii=False)))
    lines.append('  "patterns": [')
    pats = index.get("patterns", [])
    for i, p in enumerate(pats):
        comma = "," if i < len(pats) - 1 else ""
        lines.append("    %s%s" % (json.dumps(p, ensure_ascii=False), comma))
    lines.append("  ]")
    lines.append("}")
    with open(INDEX_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="L2 判据层合并与校验")
    ap.add_argument("--check", action="store_true", help="只校验，不写回 index")
    ap.add_argument("--dry-run", action="store_true", help="打印合并结果摘要，不写回")
    args = ap.parse_args(argv)

    if not os.path.isfile(DETECT_PATH):
        print("[FAIL] 找不到 %s" % DETECT_PATH)
        return 1
    detect = load_json(DETECT_PATH)
    index = load_json(INDEX_PATH)
    cards = collect_card_sections(os.path.join(ROOT, "patterns"))

    errs = validate(detect, index, cards)
    if errs:
        print("[FAIL] L2 判据层校验未通过，共 %d 项：" % len(errs))
        for e in errs:
            print("  - " + e)
        return 1

    n = len(detect.get("patterns") or [])
    print("[PASS] L2 判据层校验通过：%d 条模式均有 axes/oracle/signal/lines/constructor/judge/kill"
          % n)

    axes_hist: Dict[str, int] = {}
    oracle_hist: Dict[str, int] = {}
    line_hist: Dict[str, int] = {}
    for p in detect.get("patterns") or []:
        for a in p.get("axes") or []:
            axes_hist[a] = axes_hist.get(a, 0) + 1
        for o in p.get("oracle") or []:
            oracle_hist[o] = oracle_hist.get(o, 0) + 1
        for l in p.get("lines") or []:
            line_hist[l] = line_hist.get(l, 0) + 1
    print("  axes 分布：" + ", ".join("%s=%d" % kv for kv in
                                   sorted(axes_hist.items(), key=lambda x: -x[1])))
    print("  oracle 分布：" + ", ".join("%s=%d" % kv for kv in
                                     sorted(oracle_hist.items(), key=lambda x: -x[1])))
    print("  执行线分布：" + ", ".join("%s=%d" % kv for kv in
                                    sorted(line_hist.items(), key=lambda x: -x[1])))

    if args.check:
        # --check 还要确认 index 里已经合并过，防止「改了真源没重新生成」
        stale = []
        by_id = {p["id"]: p for p in detect.get("patterns") or []}
        for entry in index.get("patterns", []):
            pid = entry.get("id")
            want = by_id.get(pid)
            if not want:
                continue
            got = entry.get("detect") or {}
            if got.get("judge") != want.get("judge") or \
               sorted(got.get("axes") or []) != sorted(want.get("axes") or []):
                stale.append(pid)
        if stale:
            print("[FAIL] index 的 detect 与真源不一致（%d 条），请跑 gen_detect.py 重新合并：%s"
                  % (len(stale), ", ".join(stale[:10])))
            return 1
        # L3 内容漂移（v6.18.1）：只比 id 会漏掉「改了 rule 文本没重新合并」——
        # rule 是 L3 的全部信息量，必须逐条 (id, fail, rule) 全等。
        src_of = (detect.get("oracle_failures") or {}).get("by_oracle") or {}
        idx_of = ((index.get("detect_layer") or {}).get("oracle_failures") or {}).get("by_oracle") or {}

        def _sig(xs):
            return [(str(i.get("id") or "").strip(),
                     str(i.get("fail") or "").strip(),
                     str(i.get("rule") or "").strip())
                    for i in (xs or []) if isinstance(i, dict)]

        drift = [c for c in src_of if _sig(src_of[c]) != _sig(idx_of.get(c))]
        drift += [c for c in idx_of if c not in src_of]
        if drift:
            print("[FAIL] index 的 oracle_failures 与真源内容不一致（%d 类）：%s。"
                  "请跑 gen_detect.py 重新合并" % (len(drift), ", ".join(sorted(set(drift)))))
            return 1
        print("[PASS] index 内 detect 与真源一致（L3 逐条 id/fail/rule 全等）")
        return 0

    if args.dry_run:
        print("[DRY] 将写入 %d 条模式的 detect 字段（未落盘）" % n)
        return 0

    merged = merge_into_index(index, detect)
    write_index(merged)
    print("[OK] 已合并进 fault_patterns_index.json（%d 条）" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
