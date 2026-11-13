#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
计数配平判据（scan_counts.py，v6.21）

要解决的盲区
------------
存在型签名只能回答「还有没有」，不能回答「是不是少了一处」。v6.20 变异实测暴露：
  M11 删 SetAtomicAdd → 旧口径 3/10，因为**每个未捕获文件都残留 2~5 个同类 token**，
       存在型签名照旧命中，看不出「少了一个」。
  M14 注释模板注册 → 同理。

这类缺陷的正确判据是**计数配平**：某类 token 在本文件/本目录的出现次数应落在
同类文件的正常区间内，低于区间即候选。它回答的是「数量对不对」，而存在型回答「有无」。

为什么必须用同类文件做基线，而不是写死数字
------------------------------------------
绝对阈值换一个仓就失效（有的算子 1 个 kernel 文件，有的 12 个）。本工具的做法：
  1. 按 `scope` 取出同目录（或同仓同后缀）文件作为**同伴组**；
  2. 对每个文件算该 token 的出现次数；
  3. 用同伴组的中位数与 MAD（中位数绝对偏差，抗离群）建正常区间；
  4. 某文件计数显著低于同伴组下界 → 候选。

MAD 而非标准差：文件之间规模差异极大（几十行到上万行），标准差会被长尾拉爆。

判据来源（挂在索引里，与其它判据同源）
--------------------------------------
索引新增 `count_signatures` 字段：
  {"token": "REGISTER_TILING_TEMPLATE", "files": "op_host.*\\.cpp$",
   "scope": "dir", "min_ratio": 0.5, "level": "info",
   "note": "..."}
  token      要计数的正则
  files      参与统计的文件路径正则
  scope      dir（同目录同伴）| repo（同仓同 files 全集合）
  min_ratio  低于「同伴组中位数 × 该比例」即候选（默认 0.5）
  level      候选等级

用法
----
python3 scripts/scan_counts.py <target> --only FP-A19
python3 scripts/scan_counts.py <target> --format json
python3 scripts/scan_counts.py --self-test
"""

import argparse
import json
import os
import re
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTS = (".cpp", ".cc", ".h", ".hpp")


def read_text(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def load_counts(root):
    """从索引读 count_signatures，返回 [{pid, token, files, scope, min_ratio, level, note}]。"""
    idx = json.loads(read_text(os.path.join(root, "fault_patterns_index.json")))
    out = []
    for p in idx["patterns"]:
        for r in (p.get("count_signatures") or []):
            if not isinstance(r, dict):
                continue
            if not (r.get("token") and r.get("files")):
                continue
            out.append({
                "pid": p["id"],
                "token": r["token"],
                "files": r["files"],
                "scope": r.get("scope") or "dir",
                "min_ratio": float(r.get("min_ratio") or 0.5),
                "level": r.get("level") or "info",
                "note": r.get("note") or "",
            })
    return out


def iter_files(targets):
    for t in targets:
        if os.path.isfile(t):
            yield t
        elif os.path.isdir(t):
            for dp, dns, fns in os.walk(t):
                dns[:] = [d for d in dns
                          if d not in (".git", "build", "__pycache__", "third_party")]
                for fn in fns:
                    if os.path.splitext(fn)[1].lower() in EXTS:
                        yield os.path.join(dp, fn)


def group_key(path, scope):
    """同伴组键：dir = 同目录；repo = 同一仓根（用前两级目录近似）。"""
    p = path.replace("\\", "/")
    if scope == "repo":
        parts = p.split("/")
        return "/".join(parts[:3])
    return os.path.dirname(p)


def peer_band(counts):
    """由同伴组计数算正常下界。用中位数 ± MAD，抗离群。

    返回 (low, med, n)；n<3 时不给结论（样本太少，任何阈值都是噪声）。
    """
    vals = [c for c in counts]
    n = len(vals)
    if n < 3:
        return None, (statistics.median(vals) if vals else 0), n
    med = statistics.median(vals)
    devs = [abs(v - med) for v in vals]
    mad = statistics.median(devs)
    # 1.4826*MAD ≈ 正态下的 σ；下界取 med - 3σ，但不得低于 0
    low = max(0.0, med - 3 * 1.4826 * mad)
    return low, med, n


def scan(targets, rules, only=None):
    """返回 (candidates, stats)。

    两级同伴组（v6.21）：先按 `scope`（dir/repo）分组；若某组样本 <3 无法建区间，
    **回退到全局同伴组**（本次扫描的全部匹配文件）。理由：算子目录常只有 1~2 个
    tiling 文件，只按目录分组会让大量样本落在「样本不足」，白白丢掉检出机会；
    而「同类文件的注册数分布」在全仓范围内依然是有意义的参照。
    回退在后文中标记 `fallback=True`，便于判读者知道该候选的基线范围。
    """
    files = [f for f in iter_files(targets)]
    rel = [f.replace("\\", "/") for f in files]
    cands, stats = [], []
    for rule in rules:
        if only and rule["pid"] not in only:
            continue
        try:
            tok = re.compile(rule["token"])
            fre = re.compile(rule["files"])
        except re.error:
            continue
        picked = [(f, r) for f, r in zip(files, rel) if fre.search(r)]
        if not picked:
            stats.append({"pid": rule["pid"], "token": rule["token"],
                          "files": 0, "flagged": 0, "note": "无匹配文件"})
            continue
        per = []
        for f, r in picked:
            try:
                cnt = len(tok.findall(read_text(f)))
            except OSError:
                continue
            per.append((f, r, cnt))
        if not per:
            stats.append({"pid": rule["pid"], "token": rule["token"],
                          "files": 0, "flagged": 0, "note": "无可读文件"})
            continue

        # 全局基线（回退用）——只在「**本来就有该 token** 的文件」之间比。
        # 关键：同伴组不能混入天然不该有该 token 的文件（def/infershape/tiling.h），
        # 否则中位数被拉成 0，阈值变成 0，`count < 0` 永不成立，判据直接失效。
        # 实测踩到：clipped_swiglu 的 5 个同伴里 4 个计数为 0，median=0 → 全部漏报。
        nonzero = [c for _f, _r, c in per if c > 0]
        g_low, g_med, g_n = peer_band(nonzero) if len(nonzero) >= 3 else (None, 0, len(nonzero))
        # 判据门槛：该 token 在同类文件里「通常至少出现几次」
        typical = statistics.median(nonzero) if nonzero else 0

        groups = {}
        for f, r, c in per:
            groups.setdefault(group_key(r, rule["scope"]), []).append((f, r, c))
        flagged = 0
        fb = 0
        for gk, members in groups.items():
            # 组内也只用「有该 token 的同伴」建基线，理由同上
            g_nonzero = [c for _f, _r, c in members if c > 0]
            low, med, n = peer_band(g_nonzero) if len(g_nonzero) >= 3 else (None, 0, len(g_nonzero))
            use_fallback = False
            if low is None and g_low is not None:
                low, med, n = g_low, g_med, g_n
                use_fallback = True
            if low is None:
                # 连全局都没有足够样本：退化为「同类通常有、本文件为 0」这一条最保守判据
                if typical <= 0:
                    continue
                low, med, n = 0.0, typical, 0
            thresh = max(low, med * rule["min_ratio"])
            if thresh <= 0 and typical > 0:
                thresh = typical * rule["min_ratio"]
            for f, r, c in members:
                if c >= thresh:
                    continue
                if use_fallback and c > 0:
                    continue          # 回退模式下只报「完全没有」，不报「偏少」
                # **回退模式下不报 c==0**（实测两次，结论一致）：
                #   - 允许时报：ops-nn 候选 2051/2279（90%），fallback 占 1987，
                #     而 M14 命中仍是 5/10 —— 净增全是噪声，零检出收益。
                #   - 禁止时：候选 64/2279（2.8%），M14 命中同样 5/10。
                # 原因：`files` 正则匹配到的文件本就多数不含该 token（def/infershape/
                # tiling.h），对它们报「缺这个 token」没有意义。
                if use_fallback and c == 0:
                    continue
                flagged += 1
                if use_fallback:
                    fb += 1
                cands.append({
                    "pattern": rule["pid"], "file": f, "level": rule["level"],
                    "count": c, "threshold": round(thresh, 2),
                    "peer_median": med, "peers": n,
                    "fallback": use_fallback,
                    "token": rule["token"], "note": rule["note"],
                })
        stats.append({"pid": rule["pid"], "token": rule["token"],
                      "files": len(per), "flagged": flagged,
                      "fallback": fb, "groups": len(groups)})
    return cands, stats


def self_test():
    """构造两组文件：一组正常（都有 3 个 token），一组亏空（只有 1 个），
    验证只标出亏空的那个，且同伴组 <3 时不出结论。"""
    import tempfile
    import shutil
    ok = True
    tmp = tempfile.mkdtemp(prefix="cnt_")
    try:
        d1 = os.path.join(tmp, "a", "op_host")
        os.makedirs(d1)
        for i in range(3):
            with open(os.path.join(d1, "t%d_tiling.cpp" % i), "w", encoding="utf-8") as f:
                f.write("REGISTER_TILING_TEMPLATE(x)\n" * 3)
        # 亏空文件
        with open(os.path.join(d1, "bad_tiling.cpp"), "w", encoding="utf-8") as f:
            f.write("REGISTER_TILING_TEMPLATE(x)\n")
        # 单独目录只有一个文件 → 样本不足，不应出结论
        d2 = os.path.join(tmp, "b", "op_host")
        os.makedirs(d2)
        with open(os.path.join(d2, "only_tiling.cpp"), "w", encoding="utf-8") as f:
            f.write("REGISTER_TILING_TEMPLATE(x)\n")
        rules = [{"pid": "FP-T01", "token": "REGISTER_TILING_TEMPLATE",
                  "files": "op_host/.*_tiling\\.cpp$", "scope": "dir",
                  "min_ratio": 0.5, "level": "info", "note": ""}]
        cands, _ = scan([tmp], rules)
        got = [os.path.basename(c["file"]) for c in cands]
        want = ["bad_tiling.cpp"]
        if got != want:
            print("[FAIL] 计数配平自检：应只标 bad_tiling.cpp，实得 %s" % got)
            ok = False
        else:
            print("[PASS] 计数配平自检：亏空文件被标出，样本不足组不出结论")

        # 追加自检（v6.21）：真实索引里的 count_signatures 必须真的被加载。
        # 起因：负向测试把加载条件改成 `if False` 后，上面的功能自检仍然通过——
        # 因为它只验证「函数逻辑对不对」，没验证「规则到底有没有读进来」。
        # 这一条防的是「机制静默失效但测试全绿」。
        real = load_counts(ROOT)
        if not real:
            print("[FAIL] 计数配平自检：索引里读不到任何 count_signatures"
                  "（规则未登记，或加载条件被改坏）")
            ok = False
        else:
            pids = sorted({r["pid"] for r in real})
            print("[PASS] 计数配平自检：索引加载到 %d 条规则（%s）"
                  % (len(real), "、".join(pids)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="计数配平判据：某类 token 出现次数低于同类文件下界")
    ap.add_argument("targets", nargs="*")
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--only", default="")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.targets:
        ap.print_help()
        return 2

    rules = load_counts(os.path.abspath(args.root))
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    cands, stats = scan(args.targets, rules, only=only)

    if args.format == "json":
        print(json.dumps({"candidates": cands, "stats": stats},
                         ensure_ascii=False, indent=2))
    else:
        for s in stats:
            print("[CNT] %-8s files=%-5d flagged=%-3d groups=%-3d token=%s"
                  % (s["pid"], s["files"], s["flagged"], s.get("groups", 0),
                     s["token"][:40]))
        for c in cands:
            print("[CAND][%s] %s  计数=%d < 阈值=%s（同伴中位 %s / n=%d）"
                  % (c["level"], c["file"], c["count"], c["threshold"],
                     c["peer_median"], c["peers"]))
        print("[SUMMARY] count-balance candidates=%d（计数配平：低于同类文件下界）"
              % len(cands))
    return 0


if __name__ == "__main__":
    sys.exit(main())
