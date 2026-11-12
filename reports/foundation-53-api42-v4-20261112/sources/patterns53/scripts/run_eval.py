#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
评测判分器（run_eval.py，v3.8）

两种模式
--------
1. `--validate`：只做结构与覆盖校验（CI 用，不需要模型）——
   51/51 覆盖、每份三类用例各 ≥1、id 全局唯一、expected_verdict 合法、
   positive/neighbor/out-of-scope 的期望值与语义一致。
2. `--transcripts <dir>`：对已有作答判分。每个用例对应 `<case-id>.md`，
   文件内须有一行 `verdict: <FP-XX | OUT_OF_SCOPE>`（取最后一处）；
   输出通过率、分类型准确率与混淆对（期望 → 实际）。

用法与退出码
------------
python3 scripts/run_eval.py --validate
python3 scripts/run_eval.py --transcripts <dir> [--json] [--out <json>]
  0 = 全部用例存在且判对
  1 = 存在判错
  2 = 参数/环境错误
  3 = 存在缺失作答（仅在无判错时返回）

为什么判分只认 `verdict:` 行
----------------------------
自由文本判分不可复现；把「判成哪条模式」压成一行机读结论，才能量化路由准确率。
报告正文仍按 skill 的产出模板写，`verdict:` 只是评测钩子。
"""

import argparse
import json
import os
import re
import sys

VERDICT_RE = re.compile(r"^\s*verdict\s*:\s*(FP-[A-G]\d{2}|OUT_OF_SCOPE)\s*$", re.I | re.M)
KINDS = ("positive", "neighbor-negative", "out-of-scope")


def read_text(p):
    with open(p, encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def load_all(root):
    idx = json.loads(read_text(os.path.join(root, "fault_patterns_index.json")))
    ids = [p["id"] for p in idx["patterns"]]
    cases, errs = [], []
    for pid in ids:
        p = os.path.join(root, "evals", pid, "evals.json")
        if not os.path.isfile(p):
            errs.append("%s 缺 evals/%s/evals.json" % (pid, pid))
            continue
        try:
            d = json.loads(read_text(p))
        except json.JSONDecodeError as e:
            errs.append("%s evals.json 不可解析：%s" % (pid, e))
            continue
        for c in d.get("evals", []):
            c["_pattern"] = pid
            c["_file"] = p
            cases.append(c)
    return idx, ids, cases, errs


def validate(root):
    idx, ids, cases, errs = load_all(root)
    idset = set(ids)
    if len(ids) != len(idset):
        errs.append("索引编号重复")
    kinds_seen = {}
    case_ids = set()
    for c in cases:
        pid = c["_pattern"]
        cid = c.get("id", "")
        kind = c.get("kind", "")
        exp = c.get("expected_verdict", "")
        if not cid or not kind or not c.get("prompt"):
            errs.append("%s 用例缺 id/kind/prompt：%r" % (pid, cid or "?"))
            continue
        if cid in case_ids:
            errs.append("用例 id 全局重复：%s" % cid)
        case_ids.add(cid)
        if not cid.startswith(pid + "-"):
            errs.append("%s 的用例 id 未以模式编号开头：%s" % (pid, cid))
        if kind not in KINDS:
            errs.append("%s 用例 kind 非法：%s" % (cid, kind))
            continue
        kinds_seen.setdefault(pid, set()).add(kind)
        if exp != "OUT_OF_SCOPE" and exp not in idset:
            errs.append("%s expected_verdict 不在库内：%s" % (cid, exp))
        if kind == "positive" and exp != pid:
            errs.append("%s positive 期望应为 %s，实为 %s" % (cid, pid, exp))
        if kind == "neighbor-negative":
            if exp == pid:
                errs.append("%s neighbor-negative 期望不能是本模式" % cid)
            if exp == "OUT_OF_SCOPE":
                errs.append("%s neighbor-negative 期望不能是 OUT_OF_SCOPE" % cid)
            if "请勿误判" in c.get("prompt", ""):
                errs.append("%s neighbor-negative prompt 含泄题句「请勿误判」" % cid)
        if kind == "out-of-scope" and exp != "OUT_OF_SCOPE":
            errs.append("%s out-of-scope 期望应为 OUT_OF_SCOPE，实为 %s" % (cid, exp))
    pos_prompts = {c["prompt"] for c in cases if c.get("kind") == "positive"}
    for c in cases:
        if c.get("kind") == "neighbor-negative" and c.get("prompt") in pos_prompts:
            errs.append("%s neighbor prompt 与某条 positive 完全重复（测不出区分度）" % c.get("id"))
    for pid in ids:
        missing = set(KINDS) - kinds_seen.get(pid, set())
        if missing:
            errs.append("%s 缺用例类型：%s" % (pid, "、".join(sorted(missing))))
    return ids, cases, errs


def _match_all(pats, text):
    """must_include：全部须命中；返回未命中的正则（空列表 = 通过）。"""
    miss = []
    for p in pats or []:
        try:
            if not re.search(p, text, re.I):
                miss.append(p)
        except re.error:
            miss.append(p)          # 坏正则按未命中处理（C36 另行拦截）
    return miss


def _match_any(pats, text):
    """forbidden：命中任一即返回（空列表 = 未触发）。"""
    hit = []
    for p in pats or []:
        try:
            if re.search(p, text, re.I):
                hit.append(p)
        except re.error:
            continue
    return hit


def score(root, tdir, strict=False):
    ids, cases, errs = validate(root)
    if errs:
        return 2, None, errs
    rows, missing = [], 0
    for c in cases:
        f = os.path.join(tdir, c["id"] + ".md")
        if not os.path.isfile(f):
            missing += 1
            rows.append({"id": c["id"], "kind": c["kind"], "expected": c["expected_verdict"],
                         "got": None, "ok": False, "must_missing": [], "forbidden_hit": []})
            continue
        text = read_text(f)
        got = None
        for m in VERDICT_RE.finditer(text):
            got = m.group(1).upper()
        verdict_ok = got == c["expected_verdict"]
        miss, hit = [], []
        if strict:
            miss = _match_all(c.get("must_include"), text)
            hit = _match_any(c.get("forbidden"), text)
        rows.append({"id": c["id"], "kind": c["kind"], "expected": c["expected_verdict"],
                     "got": got, "ok": verdict_ok and not miss and not hit,
                     "verdict_ok": verdict_ok, "must_missing": miss, "forbidden_hit": hit})
    found = [r for r in rows if r["got"] is not None]
    passed = [r for r in found if r["ok"]]
    ev_fail = [r for r in found if r["verdict_ok"] and not r["ok"]]
    acc = round(100.0 * len(passed) / len(found), 1) if found else 0.0
    per_kind = {}
    for k in KINDS:
        ks = [r for r in found if r["kind"] == k]
        per_kind[k] = {"total": len(ks), "pass": sum(1 for r in ks if r["ok"])}
    conf = {}
    for r in found:
        if not r["verdict_ok"]:
            key = "%s→%s" % (r["expected"], r["got"] or "NONE")
            conf[key] = conf.get(key, 0) + 1
    summary = {"cases": len(cases), "found": len(found), "missing": missing,
               "pass": len(passed), "accuracy": acc, "strict": bool(strict),
               "evidence_fail": len(ev_fail),
               "per_kind": per_kind, "confusions": conf}
    return (0 if len(passed) == len(found) and not missing else (3 if not conf and missing else 1)), summary, rows


def self_test(root):
    """自检：全对 → 0；错一条 → 1；缺一条 → 3。"""
    import tempfile
    ids, cases, errs = validate(root)
    if errs:
        print("[FAIL] 校验未通过：%s" % errs[0])
        return 1
    tmp = tempfile.mkdtemp(prefix="run_eval_")
    for c in cases:
        with open(os.path.join(tmp, c["id"] + ".md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("# 作答\n\nverdict: %s\n" % c["expected_verdict"])
    code, summary, _ = score(root, tmp)
    if code != 0 or summary["accuracy"] != 100.0:
        print("[FAIL] 全对场景：code=%s accuracy=%s" % (code, summary and summary["accuracy"]))
        return 1
    # 篡改一条 verdict
    c0 = cases[0]
    with open(os.path.join(tmp, c0["id"] + ".md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("verdict: OUT_OF_SCOPE\n" if c0["expected_verdict"] != "OUT_OF_SCOPE" else "verdict: FP-A01\n")
    code, summary, _ = score(root, tmp)
    if code != 1 or summary["confusions"] == {}:
        print("[FAIL] 错判场景：code=%s confusions=%s" % (code, summary and summary["confusions"]))
        return 1
    os.remove(os.path.join(tmp, c0["id"] + ".md"))
    code, summary, _ = score(root, tmp)
    if code != 3 or summary["missing"] != 1:
        print("[FAIL] 缺失场景：code=%s missing=%s" % (code, summary and summary["missing"]))
        return 1
    # 证据级判据（--strict）：有 verdict 但没动作/证据 → 判失败；出现禁词 → 判失败
    for c in cases:
        body = ("不在本库适用面：属环境问题，需先定界。\n" if c["kind"] == "out-of-scope"
                else "首查：核对清单①；证据等级：静态可证。\n")
        with open(os.path.join(tmp, c["id"] + ".md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("%sverdict: %s\n" % (body, c["expected_verdict"]))
    code, summary, _ = score(root, tmp, strict=True)
    if code != 0 or summary["evidence_fail"] != 0:
        print("[FAIL] strict 全优场景：code=%s evidence_fail=%s"
              % (code, summary and summary["evidence_fail"]))
        return 1
    c1 = cases[1]
    with open(os.path.join(tmp, c1["id"] + ".md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("我觉得是这条。\nverdict: %s\n" % c1["expected_verdict"])
    code, summary, _ = score(root, tmp, strict=True)
    if code != 1 or summary["evidence_fail"] < 1:
        print("[FAIL] strict 缺证据场景：code=%s evidence_fail=%s"
              % (code, summary and summary["evidence_fail"]))
        return 1
    c2 = cases[2]
    with open(os.path.join(tmp, c2["id"] + ".md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("首查：核对；证据等级：静态可证。详见 BUG-20260901-01\nverdict: %s\n"
                % c2["expected_verdict"])
    code, summary, _ = score(root, tmp, strict=True)
    if code != 1 or not any(r["forbidden_hit"] for r in score(root, tmp, strict=True)[2]):
        print("[FAIL] strict 禁词场景：未检出内部单号")
        return 1
    print("[PASS] self-test：全对 0 / 错判 1 / 缺失 3 / strict 三态（优、缺证据、禁词）通过")
    return 0


def main():
    ap = argparse.ArgumentParser(description="评测判分器（v3.8）")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--transcripts", default="", help="作答目录（每个用例一个 <case-id>.md）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="启用证据级判据：must_include 全部须命中、forbidden 命中即扣（v6.4）")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    root = os.path.abspath(args.root)

    if args.self_test:
        return self_test(root)

    if args.validate:
        ids, cases, errs = validate(root)
        if errs:
            for e in errs:
                print("[ERROR] " + e)
            return 2
        print("[OK] 评测集校验通过：%d 条模式 / %d 个用例（%s）"
              % (len(ids), len(cases), "、".join(KINDS)))
        return 0

    if not args.transcripts:
        ap.print_help()
        return 2
    if not os.path.isdir(args.transcripts):
        print("[ERROR] 作答目录不存在：%s" % args.transcripts)
        return 2

    code, summary, rows = score(root, args.transcripts, strict=args.strict)
    if summary is None:
        for e in rows:
            print("[ERROR] " + e)
        return 2
    if args.json:
        text = json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="\n") as f:
                f.write(text + "\n")
            print("[OK] 结果 → %s" % args.out)
        else:
            print(text)
    else:
        for r in rows:
            if not r["ok"]:
                if r["got"] is None:
                    print("[MISS] %-14s %-18s 无作答" % (r["id"], r["kind"]))
                elif not r.get("verdict_ok", True):
                    print("[FAIL] %-14s %-18s expected=%s got=%s"
                          % (r["id"], r["kind"], r["expected"], r["got"]))
                else:
                    print("[EVID] %-14s %-18s verdict 对但证据不合格：缺 %s%s"
                          % (r["id"], r["kind"],
                             "、".join(r["must_missing"]) or "—",
                             "；触发禁词 " + "、".join(r["forbidden_hit"]) if r["forbidden_hit"] else ""))
        print("[SUMMARY]%s cases=%d found=%d missing=%d pass=%d accuracy=%.1f%% 证据不合格=%d"
              % (" strict" if summary.get("strict") else "",
                 summary["cases"], summary["found"], summary["missing"],
                 summary["pass"], summary["accuracy"], summary.get("evidence_fail", 0)))
        for k, v in summary["per_kind"].items():
            print("  %-18s %d/%d" % (k, v["pass"], v["total"]))
        if summary["confusions"]:
            print("  confusions: " + "；".join("%s×%d" % (k, v) for k, v in sorted(summary["confusions"].items())))
    return code


if __name__ == "__main__":
    sys.exit(main())
