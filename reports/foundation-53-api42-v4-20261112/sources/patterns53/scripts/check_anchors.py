#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
锚点存活率回归（check_anchors.py，v6.19）

问题
----
`cases/cases.json` 里的 `verified_anchors` 是「文件:行号 @commit」的真实修复锚，
被引用为「这条缺陷当时真的这样修的」的证据。但上游四个算子仓持续重构：文件改名、
目录重组、`experimental/` 迁移，锚点会**静默失效**——没有任何机制会报错，而报告里
仍然写着「锚定于 xxx.cpp:123」，读者无从判断它是否还存在。

实测（2026-11-04，本机四仓 HEAD）：31 个真实锚里有 **5 个已定位不到（16%）**：
  - ops-math     activation/softplus_v2/op_kernel/arch35/softplus_v2.h
  - ops-transformer block/block_mmad_pv_arch35_mxfp8.hpp
  - ops-nn       math/arg_max_v2/op_graph/arg_max_v2_proto.h

判定口径
--------
两层核验，**commit 层优先**——因为「文件在当前 HEAD 上存在」不代表它当年就长这样，
更不能证明锚点声明的 commit 是真的。

  COMMIT_OK      声明的 commit 在该仓存在，且该 commit 的树里有此文件（可信锚）
  COMMIT_MISSING 声明的 commit **在该仓根本不存在**（跨仓错用了别的仓的 sha）
  AT_COMMIT_ABSENT  commit 存在，但该 commit 的树里没有这个文件（路径或 sha 记错）
  存活 OK        文件在当前 HEAD 存在（仅 HEAD 层能确认；commit 层缺失时单列）
  行号漂移 DRIFT 当前 HEAD 文件存在但行号越界
  失效 FAIL      当前 HEAD 文件不存在
  跳过 SKIP      该仓不在本地或未给 --repos

实测（2026-11-04，本机四仓）发现的真实问题：
  31 个锚里只有 **20 个**（64.5%）在它们声明的 commit 上真实存在。
  - 10 个锚声明 `a7539b`，但该 sha **只存在于 ops-nn**；ops-math(6)/ops-transformer(4)
    的仓里没有它 → 跨仓错用了同一个 sha。
  - 1 个锚（FP-B14-C3）指向 `ops-nn@a7539b`，但该 commit 的树里没有
    `math/arg_max_v2/op_graph/arg_max_v2_proto.h`。
  这比「文件随重构移动」严重：它不是资产腐化，而是**取证基线本身记错了**。
  因此本工具默认把 commit 层缺失计为 FAIL，需要显式 `--head-only` 才只看 HEAD。

退出码
------
0 = 全部可信（SKIP 不计失败）｜1 = 有 FAIL/DRIFT/COMMIT_MISSING/AT_COMMIT_ABSENT
2 = 参数/环境错误｜3 = 加了 --require-all 且存在 SKIP

用法
----
python3 scripts/check_anchors.py --repos <父目录>            # 人读摘要（commit 层 + HEAD 层）
python3 scripts/check_anchors.py --repos <父目录> --json     # 机读
python3 scripts/check_anchors.py --repos <父目录> --min-rate 80  # 存活率门禁
python3 scripts/check_anchors.py --repos <父目录> --head-only    # 只核 HEAD（宽松）
python3 scripts/check_anchors.py --self-test                 # 内置回归
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 锚点里可能出现、但本机未必克隆的仓：给它一个可选的目录别名
REPO_ALIASES = {
    "ops-nn": ("ops-nn",),
    "ops-math": ("ops-math",),
    "ops-cv": ("ops-cv",),
    "ops-transformer": ("ops-transformer",),
}


def read_text(p):
    with open(p, encoding="utf-8-sig") as f:
        return f.read()


def load_cases(root):
    p = os.path.join(root, "cases", "cases.json")
    if not os.path.isfile(p):
        raise SystemExit("[ERROR] 找不到 cases/cases.json（先跑 scripts/gen_cases.py）")
    return json.loads(read_text(p))


def parse_lines(spec):
    """`note.lines` 可能是 "123" / "123-130" / "" —— 统一成 (start, end) 或 None。"""
    s = str(spec or "").strip()
    if not s:
        return None
    s = s.replace("–", "-").replace("—", "-")
    if "-" in s:
        a, _, b = s.partition("-")
        try:
            return int(a), int(b or a)
        except ValueError:
            return None
    try:
        n = int(s)
        return n, n
    except ValueError:
        return None


def resolve_repo_base(repos_dir, repo):
    """在 --repos 下找该仓目录；找不到返回 None（→ SKIP）。"""
    if not repos_dir:
        return None
    for name in REPO_ALIASES.get(repo, (repo,)):
        cand = os.path.join(repos_dir, name)
        if os.path.isdir(cand):
            return cand
    return None


def git(repo_dir, *args):
    """在仓目录跑 git，返回 (returncode, stdout)。失败不抛，由调用方判定。"""
    try:
        r = subprocess.run(["git", "-C", repo_dir] + list(args),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
        return r.returncode, (r.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def commit_state(base, sha, rel):
    """在 `base` 仓里核 sha 与「该 commit 树里是否有 rel」。

    返回 (state, detail)，state ∈ COMMIT_OK / COMMIT_MISSING / AT_COMMIT_ABSENT / ""（无法判定）
    """
    sha = str(sha or "").strip()
    if not sha:
        return "", "锚点未给 commit"
    rc, kind = git(base, "cat-file", "-t", sha)
    if rc != 0 or kind != "commit":
        return "COMMIT_MISSING", "声明的 commit %s 在该仓不存在" % sha
    rc2, _ = git(base, "cat-file", "-e", "%s:%s" % (sha, rel))
    if rc2 != 0:
        return "AT_COMMIT_ABSENT", "commit %s 的树里没有该文件" % sha
    return "COMMIT_OK", "commit %s 中存在" % sha


def check_one(anchor, repos_dir, head_only=False):
    """返回 dict(key, repo, file, state, head_state, detail)。

    state 取最严重者（commit 层优先，除非 head_only）。
    """
    repo = str(anchor.get("repo") or "").strip()
    rel = str(anchor.get("file") or "").strip()
    key = "%s @%s" % (rel or "?", anchor.get("commit") or "?")
    base = resolve_repo_base(repos_dir, repo)
    rec = {"key": key, "repo": repo, "file": rel,
           "commit": anchor.get("commit"), "issue": anchor.get("issue")}
    if not repo or not rel:
        rec.update(state="FAIL", head_state="FAIL", detail="锚点缺 repo 或 file 字段")
        return rec
    if base is None:
        rec.update(state="SKIP", head_state="SKIP", detail="仓不在 --repos 下，未验证")
        return rec

    # ---- HEAD 层：文件是否还在、行号是否越界 ----
    path = os.path.join(base, rel.replace("/", os.sep))
    if not os.path.isfile(path):
        head_state, head_detail = "FAIL", "当前 HEAD 上文件不存在"
    else:
        rng = parse_lines(anchor.get("lines"))
        if rng is None:
            head_state, head_detail = "OK", "当前 HEAD 存在（未给行号）"
        else:
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    n = sum(1 for _ in f)
            except OSError as e:
                head_state, head_detail = "FAIL", "文件不可读：%s" % e
            else:
                if rng[1] > n:
                    head_state = "DRIFT"
                    head_detail = "行号 %d 越界（文件共 %d 行）" % (rng[1], n)
                else:
                    head_state = "OK"
                    head_detail = "当前 HEAD 存在，行号 %d-%d 在界内" % rng

    # ---- commit 层：声明的 sha 是否真实、该 commit 里是否有这个文件 ----
    if head_only:
        rec.update(state=head_state, head_state=head_state,
                   detail=head_detail + "（--head-only，未核 commit）")
        return rec
    cstate, cdetail = commit_state(base, anchor.get("commit"), rel)
    if cstate in ("COMMIT_MISSING", "AT_COMMIT_ABSENT"):
        state, detail = cstate, cdetail
    elif cstate == "COMMIT_OK":
        state, detail = head_state, head_detail
    else:
        state, detail = head_state, head_detail + "（%s）" % cdetail
    rec.update(state=state, head_state=head_state, detail=detail)
    return rec


def collect(cases, repos_dir, head_only=False):
    out = []
    for case in cases.get("cases") or []:
        for a in case.get("verified_anchors") or []:
            rec = check_one(a, repos_dir, head_only=head_only)
            rec["case_id"] = case.get("case_id")
            rec["fp_id"] = case.get("fp_id")
            out.append(rec)
    return out


STATES = ("OK", "DRIFT", "FAIL", "COMMIT_MISSING", "AT_COMMIT_ABSENT", "SKIP")


def summarize(rows):
    n = dict((k, 0) for k in STATES)
    for r in rows:
        n[r["state"]] = n.get(r["state"], 0) + 1
    checked = len(rows) - n["SKIP"]
    rate = (100.0 * n["OK"] / checked) if checked else None
    return n, checked, rate


def report(rows, as_json=False):
    n, checked, rate = summarize(rows)
    if as_json:
        print(json.dumps({
            "total": len(rows), "checked": checked,
            "counts": n, "survival_rate": None if rate is None else round(rate, 1),
            "anchors": rows,
        }, ensure_ascii=False, indent=2))
        return n, checked, rate
    for r in rows:
        if r["state"] == "OK":
            continue
        print("[%s] %-8s %s:%s  %s"
              % (r["state"], r["case_id"], r["repo"], r["file"], r["detail"]))
    print("-" * 74)
    if rate is None:
        print("[SUMMARY] 共 %d 个锚点，全部 SKIP（未提供 --repos 或算子仓均未克隆）" % len(rows))
    else:
        print("[SUMMARY] 共 %d 个锚点｜可信 %d / 漂移 %d / HEAD失效 %d / "
              "commit不存在 %d / commit内无此文件 %d / 跳过 %d"
              "｜已核 %d 个，可信率 %.1f%%"
              % (len(rows), n["OK"], n["DRIFT"], n["FAIL"],
                 n["COMMIT_MISSING"], n["AT_COMMIT_ABSENT"], n["SKIP"],
                 checked, rate))
        if n["COMMIT_MISSING"]:
            print("[HINT] COMMIT_MISSING 表示该锚声明的 sha 在该仓根本不存在——"
                  "多见于把别的仓的 commit 套用过来（跨仓错用）")
    return n, checked, rate


def exit_code(n, checked, rate, min_rate=None, require_all=False):
    if require_all and n["SKIP"]:
        return 3
    if (n["FAIL"] or n["DRIFT"] or n["COMMIT_MISSING"]
            or n["AT_COMMIT_ABSENT"]):
        return 1
    if min_rate is not None and rate is not None and rate < min_rate:
        return 1
    return 0


def self_test():
    """构造临时 git 仓，覆盖 HEAD 与 commit 两层共六态。

    关键用例 T-5：文件在 HEAD 存在、但声明的 commit 在该仓不存在——
    这正是本库实测踩到的那类「跨仓错用 sha」，必须判 COMMIT_MISSING 而不是 OK。
    """
    tmp = tempfile.mkdtemp(prefix="anchor_")
    repo = os.path.join(tmp, "ops-nn")
    os.makedirs(os.path.join(repo, "op_api"))
    f = os.path.join(repo, "op_api", "aclnn_x.cpp")
    with open(f, "w", encoding="utf-8") as fh:
        fh.write("line1\nline2\nline3\n")
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    for cmd in (["git", "init", "-q"], ["git", "add", "."],
                ["git", "commit", "-q", "-m", "init"]):
        subprocess.run(cmd, cwd=repo, env=env, capture_output=True)
    rc, sha = git(repo, "rev-parse", "--short", "HEAD")
    sha = sha or "deadbeef"
    cases = {"cases": [
        {"case_id": "T-1", "verified_anchors": [
            {"file": "op_api/aclnn_x.cpp", "lines": "2", "repo": "ops-nn", "commit": sha}]},
        {"case_id": "T-2", "verified_anchors": [
            {"file": "op_api/aclnn_x.cpp", "lines": "99", "repo": "ops-nn", "commit": sha}]},
        {"case_id": "T-3", "verified_anchors": [
            {"file": "op_api/gone.cpp", "lines": "1", "repo": "ops-nn", "commit": sha}]},
        {"case_id": "T-4", "verified_anchors": [
            {"file": "a/b.cpp", "lines": "1", "repo": "ops-cv", "commit": sha}]},
        {"case_id": "T-5", "verified_anchors": [
            {"file": "op_api/aclnn_x.cpp", "lines": "2", "repo": "ops-nn",
             "commit": "0123456"}]},
    ]}
    rows = collect(cases, tmp)
    got = dict((r["case_id"], r["state"]) for r in rows)
    # T-3 期望 AT_COMMIT_ABSENT 而不是 FAIL：它的 commit 是真的，只是树里没有该文件——
    # 报 commit 层更本质（「当年就没这文件」不同于「后来被删了」）。
    want = {"T-1": "OK", "T-2": "DRIFT", "T-3": "AT_COMMIT_ABSENT",
            "T-4": "SKIP", "T-5": "COMMIT_MISSING"}
    ok = got == want
    print("[%s] self-test 六态判定：%s" % ("PASS" if ok else "FAIL", got))
    if not ok:
        print("      期望：%s" % want)
    # --head-only 应把 T-5 降级为 OK（只核 HEAD），用来验证宽松模式语义
    rows2 = collect(cases, tmp, head_only=True)
    got2 = dict((r["case_id"], r["state"]) for r in rows2)
    ok2 = got2.get("T-5") == "OK"
    print("[%s] self-test --head-only 语义：T-5=%s（期望 OK）"
          % ("PASS" if ok2 else "FAIL", got2.get("T-5")))
    return 0 if (ok and ok2) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="核验 cases.json 真实锚点在算子仓当前 HEAD 的存活率")
    ap.add_argument("--root", default=ROOT, help="本库根目录")
    ap.add_argument("--repos", default="", help="算子仓的父目录（其下有 ops-nn / ops-math …）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--min-rate", type=float, default=None,
                    help="存活率低于此值即失败（只对已核锚点计）")
    ap.add_argument("--require-all", action="store_true",
                    help="存在 SKIP 即失败（CI 里要求算子仓必须挂载时使用）")
    ap.add_argument("--head-only", action="store_true",
                    help="只核当前 HEAD，不核声明的 commit（宽松模式）")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    root = os.path.abspath(args.root)
    data = load_cases(root)
    rows = collect(data, os.path.abspath(args.repos) if args.repos else "",
                   head_only=args.head_only)
    if not rows:
        print("[ERROR] cases.json 里没有任何 verified_anchors")
        return 2
    n, checked, rate = report(rows, as_json=args.json)
    return exit_code(n, checked, rate, args.min_rate, args.require_all)


if __name__ == "__main__":
    sys.exit(main())
