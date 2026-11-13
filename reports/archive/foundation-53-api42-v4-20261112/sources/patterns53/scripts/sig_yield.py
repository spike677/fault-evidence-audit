#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
签名产出审计（sig_yield.py，v6.8）

问题
----
`scan_fp.py --stats` 只给「命中总数」，看不出**一条签名把整个仓刷成候选**。
典型反例：`int32_t[^\\n]{0,40}(idx|offset|addr)` 在 ops-math 上产出 4500+ 条候选——
等于"匹配一切"，候选列表失去筛选意义，而 --stats 只显示一个很大的数字，没人会去比对分母。

本工具补分母，并覆盖**三种候选来源**（模式签名 / 子型存在型指纹 / 子型配对判据）：
- 逐条算 `hits`（命中行）/ `files_hit`（命中文件）/ `density` / `coverage`；
- 配对阵据另算 `a` / `b` 总量与**失衡文件数**（这才等于它实际产出的候选数）；
- 模式级 `candidates` = 该模式全部非宽泛命中的 (文件,行) 去重 —— **用户真正会看到的量**。

机械判定（只是建议，人读过再定）：
- 模式级 >500 `noisy`、>200 `watch`；被记 noisy/watch 且索引写了 `yield_waiver` 的转 `waived`；
- 签名级 density>20 或 coverage>50% `demote`、>8 或 >20% `constrain`；
- 配对阵据按失衡文件数：>100 `noisy`、>30 `watch`。

用法
----
python3 scripts/sig_yield.py <语料目录> [--exclude /tests/,/build/] [--top 40]
                            [--json <输出.json>] [--md <输出.md>]
python3 scripts/sig_yield.py --check cases/sig_yield-ops-math.json   # CI：结构校验

产物
----
`cases/sig_yield-<语料名>.json`（机读基线）与 `.md`（人读表），均由本脚本生成，**勿手改**。
"""

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_fp  # noqa: E402


def read_text(p):
    with open(p, encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def git_commit(path):
    """语料目录所在 git 仓的 HEAD commit（读不到返回空串）。

    基线绑定 commit 才能跨机复现：同一份 ops-math，不同 commit 的文件数与
    内容分布不同，产出数字不可直接比较（实测：6610 vs 6083 文件，
    FP-A05 候选 3419 vs 7595）。
    """
    try:
        r = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def measure(root, corpus, exclude=(), skip_comments=True):
    _, pats = scan_fp.load_patterns(root)
    idx = json.loads(read_text(os.path.join(root, "fault_patterns_index.json")))
    waivers = {p["id"]: (p.get("yield_waiver") or "") for p in idx["patterns"]}
    files = list(scan_fp.iter_files([corpus], scan_fp.DEFAULT_EXTS))
    ex = [x.strip().replace("\\", "/") for x in exclude if x.strip()]
    if ex:
        files = [f for f in files if not any(e in f.replace("\\", "/") for e in ex)]

    sigs, subs, pairs = [], [], []
    for p in pats:
        broad = set(p.get("broad") or [])
        for sd in p["signatures"]:
            try:
                rx = re.compile(sd["re"])
                fre = re.compile(sd["files"]) if sd["files"] else None
                ere = re.compile(sd["exclude"]) if sd["exclude"] else None
                wre = re.compile(sd["within"]) if sd["within"] else None
            except re.error:
                continue
            sigs.append({"pid": p["id"], "re": sd["re"], "files": sd["files"],
                         "within": sd["within"], "rx": rx, "fre": fre, "ere": ere,
                         "wre": wre, "broad": sd["re"] in broad,
                         "hits": 0, "files_hit": 0})
        for st in p.get("subtypes") or []:
            for s in st["sig"]:
                try:
                    rx = re.compile(s)
                except re.error:
                    continue
                subs.append({"pid": p["id"], "sid": st["id"], "re": s, "rx": rx,
                             "hits": 0, "files_hit": 0})
            if st.get("pair"):
                try:
                    pa = re.compile(st["pair"]["a"])
                    pb = re.compile(st["pair"]["b"])
                except re.error:
                    continue
                pairs.append({"pid": p["id"], "sid": st["id"],
                              "a": st["pair"]["a"], "b": st["pair"]["b"],
                              "pa": pa, "pb": pb, "scope": st["pair"]["scope"],
                              "max_diff": st["pair"]["max_diff"],
                              "strict": st["pair"].get("strict", False),
                              "id_re": st["pair"].get("id_re", ""),
                              "a_total": 0, "b_total": 0, "files_hit": 0, "imbalanced": 0,
                              "strict_viol": 0})

    pat_lines = {}
    pat_broad = {}

    for path in files:
        rel = path.replace("\\", "/")
        try:
            text = read_text(path)
        except OSError:
            continue
        ext = os.path.splitext(path)[1].lower()
        lines = text.splitlines()
        keep = [i for i, l in enumerate(lines, 1)
                if not (skip_comments and scan_fp._is_comment_line(l, ext))]
        body = "\n".join(lines[i - 1] for i in keep)

        for s in sigs:
            if s["fre"] is not None and not s["fre"].search(rel):
                continue
            rngs = None
            if s["wre"] is not None:
                rngs = scan_fp._func_line_ranges(text, s["wre"])
            n = 0
            for i in keep:
                line = lines[i - 1]
                if s["ere"] is not None and s["ere"].search(line):
                    continue
                if rngs is not None and not any(a <= i <= b for a, b in rngs):
                    continue
                if s["rx"].search(line):
                    n += 1
                    if s["broad"]:
                        pat_broad[s["pid"]] = pat_broad.get(s["pid"], 0) + 1
                    else:
                        pat_lines.setdefault(s["pid"], set()).add((path, i))
            if n:
                s["hits"] += n
                s["files_hit"] += 1

        for s in subs:
            n = 0
            for i in keep:
                if s["rx"].search(lines[i - 1]):
                    n += 1
                    pat_lines.setdefault(s["pid"], set()).add((path, i))
            if n:
                s["hits"] += n
                s["files_hit"] += 1

        for pr in pairs:
            if pr["scope"] != "file":
                continue
            keep = [i for i, l in enumerate(lines, 1)
                    if not (skip_comments and scan_fp._is_comment_line(l, ext))]
            na, nb, viol = scan_fp.pair_stats(lines, keep, pr["pa"], pr["pb"],
                                              pr["strict"], pr["id_re"])
            if na == 0 and nb == 0:
                continue
            pr["files_hit"] += 1
            pr["a_total"] += na
            pr["b_total"] += nb
            pr["strict_viol"] += len(viol)
            if abs(na - nb) > pr["max_diff"]:
                pr["imbalanced"] += 1
                pat_lines.setdefault(pr["pid"], set()).add((path, 0))
            for ln, _key in viol:
                pat_lines.setdefault(pr["pid"], set()).add((path, ln))

    out = []
    for s in sigs:
        hits, fh = s["hits"], s["files_hit"]
        if s["broad"]:
            v = "broad"
        elif fh and (hits / fh > 20 or fh / len(files) > 0.5):
            v = "demote"
        elif fh and (hits / fh > 8 or fh / len(files) > 0.2):
            v = "constrain"
        else:
            v = "keep"
        out.append({"pattern": s["pid"], "signature": s["re"], "kind": "pattern",
                    "files_constraint": s["files"], "within": s["within"], "broad": s["broad"],
                    "hits": hits, "files_hit": fh,
                    "density": round(hits / fh, 1) if fh else 0.0,
                    "coverage": round(fh / len(files), 3) if files else 0.0,
                    "verdict": v})

    sub_rows = []
    for s in subs:
        hits, fh = s["hits"], s["files_hit"]
        if hits > 500:                     # v6.8：子型指纹同样看绝对量，不只看密度
            v = "noisy"
        elif hits > 200:
            v = "watch"
        elif fh and (hits / fh > 20 or fh / len(files) > 0.5):
            v = "demote"
        elif fh and (hits / fh > 8 or fh / len(files) > 0.2):
            v = "constrain"
        else:
            v = "keep"
        sub_rows.append({"pattern": s["pid"], "subtype": s["sid"], "kind": "sig",
                         "candidates": hits, "files_hit": fh,
                         "density": round(hits / fh, 1) if fh else 0.0,
                         "coverage": round(fh / len(files), 3) if files else 0.0,
                         "verdict": v})
    for pr in pairs:
        cand = pr["imbalanced"] + pr["strict_viol"] if pr["strict"] else pr["imbalanced"]
        v = "noisy" if cand > 100 else ("watch" if cand > 30 else "ok")
        sub_rows.append({"pattern": pr["pid"], "subtype": pr["sid"], "kind": "pair",
                         "candidates": cand, "files_hit": pr["files_hit"],
                         "a_total": pr["a_total"], "b_total": pr["b_total"],
                         "strict": pr["strict"], "strict_viol": pr["strict_viol"],
                         "density": round(cand / pr["files_hit"], 2) if pr["files_hit"] else 0.0,
                         "coverage": round(pr["files_hit"] / len(files), 3) if files else 0.0,
                         "verdict": v})

    out.sort(key=lambda r: (-r["hits"], r["pattern"]))
    sub_rows.sort(key=lambda r: (-r["candidates"], r["pattern"]))

    pats_out = []
    for p in pats:
        if not p["signatures"] and not p["subtypes"]:
            continue
        cand = len(pat_lines.get(p["id"], ()))
        v = "noisy" if cand > 500 else ("watch" if cand > 200 else "ok")
        w = waivers.get(p["id"]) or ""
        if w and v in ("noisy", "watch"):
            v = "waived"
        pats_out.append({"pattern": p["id"], "candidates": cand,
                         "broad_hits": pat_broad.get(p["id"], 0),
                         "n_signatures": len(p["signatures"]),
                         "verdict": v, "waiver": w})
    pats_out.sort(key=lambda r: -r["candidates"])
    return out, sub_rows, pats_out, len(files)


def render_md(rows, sub_rows, pats_rows, corpus, n_files, commit=""):
    tag = {"demote": "🔴 demote", "constrain": "🟠 constrain", "keep": "✅ keep",
           "broad": "⬜ broad", "noisy": "🔴 noisy", "watch": "🟠 watch",
           "ok": "✅ ok", "waived": "🟡 waived"}
    base = os.path.basename(corpus.rstrip("\\/"))
    lines = [
        "# 签名产出审计基线（%s）" % base,
        "",
        "> **生成物，勿手改**：`python3 scripts/sig_yield.py <语料目录> --md cases/sig_yield-%s.md`。" % base,
        "> 被扫文件 %d（默认排除 tests/examples/build 与纯注释行）。" % n_files,
        "> 语料 commit：`%s`%s" % (commit or "未知",
                                 "（跨机复现须用同一 commit 的语料，否则数字不可比）" if commit else ""),
        "> 口径：**模式级候选** = 该模式全部非宽泛命中的 (文件,行) 去重（= 用户实际会看到多少条）；"
        "配对阵据按**失衡文件数**计候选；**density** = 命中行 ÷ 命中文件；**coverage** = 命中文件 ÷ 被扫文件。",
        "> 阈值：模式级 >500 noisy、>200 watch；签名级 density>20 或 coverage>50% demote、>8 或 >20% constrain；配对阵据失衡 >100 noisy、>30 watch。",
        "",
        "## 一、模式级候选量（决定「这条模式能不能用」）",
        "",
        "| 模式 | 候选数 | 宽泛未计 | 签名数 | 判定 | 豁免理由 |",
        "|---|---|---|---|---|---|",
    ]
    for r in pats_rows[:40]:
        lines.append("| %s | %d | %d | %d | %s | %s |"
                     % (r["pattern"], r["candidates"], r["broad_hits"], r["n_signatures"],
                        tag[r["verdict"]], r.get("waiver", "") or "—"))
    n = {k: sum(1 for r in pats_rows if r["verdict"] == k) for k in ("noisy", "watch", "ok", "waived")}
    lines += ["", "**汇总**：%d 个模式 —— noisy %d / watch %d / ok %d / waived %d。"
              % (len(pats_rows), n["noisy"], n["watch"], n["ok"], n["waived"]), "",
              "## 二、子型级产出（v6.8：存在型指纹与配对阵据分别度量）", "",
              "| 模式 | 子型 | 类型 | 候选 | 命中文件 | density | coverage | 判定 |",
              "|---|---|---|---|---|---|---|---|"]
    for r in sub_rows[:60]:
        lines.append("| %s | %s | %s | %d | %d | %.2f | %.1f%% | %s |"
                     % (r["pattern"], r["subtype"], r["kind"], r["candidates"],
                        r["files_hit"], r["density"], r["coverage"] * 100, tag[r["verdict"]]))
    nsub = {k: sum(1 for r in sub_rows if r["verdict"] == k)
            for k in ("noisy", "watch", "ok", "demote", "constrain", "keep")}
    lines += ["", "**汇总**：%d 条子型判据（存在型 %d / 配对 %d）—— 配对 noisy %d / watch %d / ok %d；"
              "存在型 demote %d / constrain %d / keep %d。"
              % (len(sub_rows), sum(1 for r in sub_rows if r["kind"] == "sig"),
                 sum(1 for r in sub_rows if r["kind"] == "pair"),
                 nsub["noisy"], nsub["watch"], nsub["ok"],
                 nsub["demote"], nsub["constrain"], nsub["keep"]), "",
              "## 三、签名级产出（前 80 条，定位是哪条指纹在刷屏）", "",
              "| 模式 | 命中 | 命中文件 | density | coverage | 约束 | 判定 |",
              "|---|---|---|---|---|---|---|"]
    for r in rows[:80]:
        cons = "files=" + r["files_constraint"] if r["files_constraint"] else ""
        if r["within"]:
            cons += " within=" + r["within"]
        sig = r["signature"].replace("|", "\\|")
        lines.append("| %s `%s` | %d | %d | %.1f | %.1f%% | %s | %s |"
                     % (r["pattern"], sig[:70], r["hits"], r["files_hit"],
                        r["density"], r["coverage"] * 100, cons or "—", tag[r["verdict"]]))
    n2 = {k: sum(1 for r in rows if r["verdict"] == k) for k in ("demote", "constrain", "keep", "broad")}
    lines += ["", "**汇总**：共 %d 条模式签名 —— demote %d / constrain %d / keep %d / broad %d。"
              % (len(rows), n2["demote"], n2["constrain"], n2["keep"], n2["broad"]), ""]
    return "\n".join(lines)


def check(path):
    """结构校验（CI 用）：基线产物存在、可解析、字段齐全。"""
    if not os.path.isfile(path):
        print("[ERROR] 缺基线产物：%s" % path)
        return 2
    try:
        d = json.load(open(path, encoding="utf-8"))
    except ValueError as e:
        print("[ERROR] 基线不可解析：%s" % e)
        return 2
    need = {"corpus", "scanned_files", "generated_by", "entries", "patterns", "subtypes"}
    miss = need - set(d)
    if miss:
        print("[ERROR] 基线缺字段：%s" % ",".join(sorted(miss)))
        return 2
    if d.get("generated_by") != "scripts/sig_yield.py":
        print("[ERROR] generated_by 不是 scripts/sig_yield.py（产物可能被手改）")
        return 2
    if not d.get("entries") or not d.get("patterns"):
        print("[ERROR] 基线无条目")
        return 2
    print("[OK] 签名产出基线：%d 条模式签名 / %d 条子型判据 / %d 个模式 / 语料 %s / 被扫 %d 文件"
          % (len(d["entries"]), len(d["subtypes"]), len(d["patterns"]),
             os.path.basename(str(d["corpus"])), d["scanned_files"]))
    if d.get("corpus_commit"):
        print("[INFO] 基线绑定语料 commit：%s（跨机重跑须用同一 commit，否则数字不可比）"
              % d["corpus_commit"])
    return 0


def main():
    ap = argparse.ArgumentParser(description="签名产出审计（v6.8）")
    ap.add_argument("corpus", nargs="?", default="")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--exclude", default="/tests/,/examples/,/build/")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--json", default="")
    ap.add_argument("--md", default="")
    ap.add_argument("--include-comments", action="store_true")
    ap.add_argument("--check", default="")
    args = ap.parse_args()

    if args.check:
        return check(args.check)
    if not args.corpus or not os.path.isdir(args.corpus):
        ap.print_help()
        return 2

    rows, sub_rows, pats_rows, n_files = measure(
        os.path.abspath(args.root), os.path.abspath(args.corpus),
        exclude=args.exclude.split(","), skip_comments=not args.include_comments)
    name = os.path.basename(args.corpus.rstrip("\\/"))
    commit = git_commit(args.corpus)
    payload = {"corpus": args.corpus, "corpus_commit": commit, "scanned_files": n_files,
               "generated_by": "scripts/sig_yield.py",
               "patterns": pats_rows, "subtypes": sub_rows, "entries": rows}
    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("[OK] JSON → %s" % args.json)
    if args.md:
        with open(args.md, "w", encoding="utf-8", newline="\n") as f:
            f.write(render_md(rows, sub_rows, pats_rows, args.corpus, n_files, commit) + "\n")
        print("[OK] MD → %s" % args.md)

    print("[YIELD] corpus=%s files=%d signatures=%d subtypes=%d patterns=%d"
          % (name, n_files, len(rows), len(sub_rows), len(pats_rows)))
    print("\n== 模式级候选量 Top %d（用户真正会看到的量）==" % min(args.top, 20))
    for r in pats_rows[:min(args.top, 20)]:
        print("  %-8s cand=%5d  broad=%5d  sigs=%2d  %-6s"
              % (r["pattern"], r["candidates"], r["broad_hits"], r["n_signatures"], r["verdict"]))
    print("\n== 子型级 Top %d ==" % min(args.top, 20))
    for r in sub_rows[:min(args.top, 20)]:
        print("  %-8s %-8s %-4s cand=%4d files=%4d  %-6s"
              % (r["pattern"], r["subtype"], r["kind"], r["candidates"],
                 r["files_hit"], r["verdict"]))
    print("\n== 签名级 Top %d ==" % args.top)
    for r in rows[:args.top]:
        print("  %-8s %6d hits / %4d files  density=%6.1f  cov=%5.1f%%  %-9s %s"
              % (r["pattern"], r["hits"], r["files_hit"], r["density"],
                 r["coverage"] * 100, r["verdict"], r["signature"][:48]))
    n = {k: sum(1 for r in rows if r["verdict"] == k) for k in ("demote", "constrain", "keep", "broad")}
    np_ = {k: sum(1 for r in pats_rows if r["verdict"] == k) for k in ("noisy", "watch", "ok", "waived")}
    ns = {k: sum(1 for r in sub_rows if r["verdict"] == k) for k in ("noisy", "watch", "ok", "demote", "constrain", "keep")}
    print("\n[SUMMARY] patterns: noisy=%d watch=%d ok=%d waived=%d ｜ signatures: demote=%d constrain=%d keep=%d broad=%d"
          % (np_["noisy"], np_["watch"], np_["ok"], np_["waived"],
             n["demote"], n["constrain"], n["keep"], n["broad"]))
    print("[SUMMARY] subtypes: noisy=%d watch=%d ok=%d / demote=%d constrain=%d keep=%d"
          % (ns["noisy"], ns["watch"], ns["ok"], ns["demote"], ns["constrain"], ns["keep"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
