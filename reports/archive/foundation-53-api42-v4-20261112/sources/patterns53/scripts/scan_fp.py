#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
签名扫描器（scan_fp.py，v6.7）

定位
----
把索引 `signatures`（存在型指纹，支持字符串与结构化对象）、`subtypes[].sig`（子型指纹）、
`subtypes[].pair`（子型配对结构判据）、`absence_signatures`（缺失型规则）与
`log_signatures`（日志指纹）分别变成**候选生成器**：只产候选、不下结论。
README 的立场与本工具一致——「命中 ≠ 成立」，每条候选仍须过 skill 第 7 节
的正负证据与证据等级判定；`keywords` 只作审查定位提示，**不产生命中**。

三种扫描模式
------------
- 默认（存在型）：`signatures` 逐行匹配，出现即候选；其中 `broad_signatures` 标记的签名是
  「存在即常态」的定位提示（如 `OP_LOGE`、`OP_CHECK_NULL`），候选带 `[BROAD]` 标记；
- **配对结构判据（v6.7）**：子型可写 `pair: {a, b, scope: file, max_diff: 0}`——统计文件内
  A、B 两个正则的出现次数，**次数失衡即候选**（带 `counts: {a, b}`）。这是本工具唯一
  **判别型**判据：`SetFlag` 出现 10 次、`WaitFlag` 出现 4 次，任何单行都不异常，只有计数关系异常。
  `max_diff` 允许容忍差（如管线前导/收尾各差 1 时可设 1）；`scope` 目前只支持 `file`（函数级未实现，C35 拦截）。
  **结构型候选在截断时优先保留**（排序：pair > 子型指纹 > 模式级指纹），否则定位型指纹会先吃光配额。
- **结构化签名（v6.5）**：签名可写成对象 `{"re": ..., "files": ..., "within": ..., "exclude": ...}`——
  `files` 限定路径（如 `op_kernel`）、`within` 限定所在函数（正则匹配函数头，按花括号取体）、
  `exclude` 命中该行的正则则跳过；字符串形态继续支持（等价于只给 `re`）。守门 C37 校验结构与可编译性；
- **注释降噪（v6.5）**：默认跳过纯注释行（`//`、块注释与续行 `*`、`.py/.sh` 的 `#`）；
  `--include-comments` 关闭该过滤（与历史基线对齐时用）；
- **宽泛签名默认不列候选（v6.6）**：`broad_signatures` 只计数（`[BROAD]` 汇总行），`--broad list`
  才把它们列进候选、`--broad off` 连计数也不管；`--max-per-signature 200`（0=不限）防单条刷屏；
- **子型级定性（v6.3）**：模式内某子型配了 `subtypes[].sig` 时，同一行优先由子型指纹定性，
  候选带子型号（如 `[G02-3]`），JSON 增 `subtype` 字段；模式级指纹在同行为命中时不再重复报。
  没有 `sig` / `pair` 的子型不产候选——**子型只负责把一条模式拆成 N 条检索线，不负责凭空造命中**；
- `--absence`（缺失型，v4.6+）：文件路径命中 `files` 正则、但正文缺少 `must` 正则 → 候选。
  规则字段：`when`（前置条件）、`func`（函数签名，函数内判断）、`branch`（分支锚点，
  花括号体内判断；带不带 `{` 都可以，v6.5 起自动归一）、`exclude_sig`（签名含该正则则跳过）、
  `subtype`（v6.5：把候选挂到本模式的某个子型上，须在 `subtypes` 中已定义，C37 校验）；
  `func` + `branch` 同时给定时为「函数内分支级」，用于「早退 SUCCESS 但不写输出」这类缺陷；
- `--log`（日志型，v4.6）：用 `log_signatures` 扫 `.log/.txt`（如 `undefined symbol`），不混入源码扫描；
- `--stats`：语料回归统计（按模式/签名计数、零命中、宽泛标记、absence 汇总），用于死签名复核。

用法
----
python3 scripts/scan_fp.py <文件或目录> [...] [--only FP-A06,FP-G01] [--ext .cpp,.h]
                            [--format text|json] [--max-per-pattern 50] [--out <json>]
                            [--exclude /tests/,/build/] [--include-comments]
                            [--collapse file|subtype] [--context 3]   # v6.10：折叠 + 上下文
python3 scripts/scan_fp.py <目录> --absence --exclude /tests/
python3 scripts/scan_fp.py <日志文件或目录> --log
python3 scripts/scan_fp.py <目录> --stats --exclude /tests/,/examples/
python3 scripts/scan_fp.py --subtypes [--only FP-G02,FP-B07]   # 列出子型与是否有可扫指纹
python3 scripts/scan_fp.py --self-test

退出码
------
0 = 无候选
1 = 有候选（供 CI 判定「是否有人工确认清单」）
2 = 参数/环境错误
3 = 仅 --self-test 通过

能力边界（必读）
----------------
- 只保证正则「可编译、不匹配空串、有足够字面量、跨模式不重复」；
- **不能**证明签名在真实代码上有效（死签名需用真实语料回归，见 cases/scan-baseline-ops-cv.md）；
- 正则扫描不理解语义、宏展开与模板实例化，**漏报是常态**；报告必须写「本工具未命中 ≠ 无缺陷」；
- 单条签名在大型仓命中数可达成百上千（见 FP-G01 的 `size_t` 例子），用 `--max-per-pattern` 截断并标注；
- `absence` 只证明「文件里没有这个 token」，不证明「校验完整」——仍需人工确认检查对象与顺序。
"""

import argparse
import json
import os
import re
import sys

SKIP_DIRS = {".git", "build", "output", "node_modules", "third_party", "thirdparty",
             "__pycache__", ".venv", "venv", "dist", "docs", ".idea", ".vscode"}
DEFAULT_EXTS = (".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".hh", ".py", ".sh", ".asc", ".inc")


def read_text(p):
    with open(p, encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def _norm_sig(s):
    """签名归一（v6.5）：字符串 → {"re": s}；对象形式支持 re / files / within / exclude。"""
    if isinstance(s, str):
        return {"re": s, "files": "", "within": "", "exclude": ""}
    if isinstance(s, dict) and isinstance(s.get("re"), str) and s["re"].strip():
        return {"re": s["re"],
                "files": s.get("files") or "",
                "within": s.get("within") or "",
                "exclude": s.get("exclude") or ""}
    return None


def load_patterns(root):
    idx = json.loads(read_text(os.path.join(root, "fault_patterns_index.json")))
    pats = []
    for p in idx["patterns"]:
        sigs = [x for x in (_norm_sig(s) for s in (p.get("signatures") or [])) if x]
        broad = [s for s in (p.get("broad_signatures") or []) if s.strip()]
        absence = [r for r in (p.get("absence_signatures") or [])
                   if isinstance(r, dict) and r.get("must") and r.get("files")]
        logs = [s for s in (p.get("log_signatures") or []) if s.strip()]
        subs = []
        for st in (p.get("subtypes") or []):          # v6.3：子型级签名（可选）
            if not isinstance(st, dict):
                continue
            ss = [x for x in (st.get("sig") or []) if isinstance(x, str) and x.strip()]
            pr = st.get("pair")
            pair = None
            if isinstance(pr, dict) and pr.get("a") and pr.get("b"):
                pair = {"a": pr["a"], "b": pr["b"],
                        "scope": pr.get("scope") or "file",
                        "max_diff": int(pr.get("max_diff") or 0),
                        "strict": bool(pr.get("strict")),
                        "id_re": pr.get("id_re") or ""}
            subs.append({"id": st.get("id") or "", "name": st.get("name") or "",
                         "sig": ss, "pair": pair})
        pats.append({"id": p["id"], "name": p["name"], "signatures": sigs,
                     "broad": broad, "absence": absence, "log_signatures": logs,
                     "subtypes": subs})
    return idx, pats


def iter_files(targets, exts):
    for t in targets:
        if os.path.isfile(t):
            yield t
        elif os.path.isdir(t):
            for dp, dns, fns in os.walk(t):
                dns[:] = [d for d in dns if d not in SKIP_DIRS]
                for fn in fns:
                    if os.path.splitext(fn)[1].lower() in exts:
                        yield os.path.join(dp, fn)
        else:
            print("[WARN] 路径不存在，已跳过：%s" % t)


def _is_comment_line(line, ext):
    """纯注释行判定（v6.5 降噪）：// 、块注释行首与续行 * ；.py/.sh 另跳 #。"""
    t = line.lstrip()
    if not t:
        return False
    if t.startswith("//") or t.startswith("/*") or t.startswith("*"):
        return True
    if ext in (".py", ".sh") and t.startswith("#"):
        return True
    return False


def _func_line_ranges(text, rx):
    """`within` 支持：返回匹配函数定义的行区间列表（粗略，按花括号配对）。"""
    out = []
    for m in rx.finditer(text):
        body = _extract_braced(text, _brace_pos(text, m.end()))
        if not body:
            continue
        start = text.count("\n", 0, m.start()) + 1
        out.append((start, start + body.count("\n")))
    return out


def pair_stats(lines, keep, pa, pb, strict=False, id_re=""):
    """配对统计（v6.9 抽出，供 scan_files 与 sig_yield 共用，避免两处逻辑漂移）。

    返回 (a 出现次数, b 出现次数, strict 违规列表 [(行号, id)])。
    strict：同一 id 的两次 A 之间必须有 B（SetFlag 同一 event id 连发会覆盖等待语义）。
    """
    idx_re = re.compile(id_re) if (strict and id_re) else None
    na = nb = 0
    viol = []
    state = {}
    for i in keep:
        line = lines[i - 1]
        for m in pa.finditer(line):
            na += 1
            if idx_re is None:
                continue
            ev = idx_re.search(line[m.start():])
            key = ev.group(1) if ev else "?"
            if state.get(key) == "a":
                viol.append((i, key))
            state[key] = "a"
        k = len(pb.findall(line))
        if k:
            nb += k
            if idx_re is not None:
                ev = idx_re.search(line)
                state[ev.group(1) if ev else "?"] = "b"
    return na, nb, viol


def scan_files(files, patterns, only=None, max_per=50, skip_comments=True, max_per_sig=0):
    hits, truncated = [], []
    compiled = []              # (pid, sig_dict, rx, files_rx, exc_rx, within_rx)
    sub_compiled = []          # (pid, sid, sig, rx)：子型级指纹（v6.3）
    pair_items = []            # (pid, sid, a_rx, b_rx, scope, max_diff)：子型配对判据（v6.7）
    broad_of = {}
    for p in patterns:
        if only and p["id"] not in only:
            continue
        broad_of[p["id"]] = set(p.get("broad") or [])
        for sd in p["signatures"]:
            try:
                rx = re.compile(sd["re"])
                fre = re.compile(sd["files"]) if sd["files"] else None
                ere = re.compile(sd["exclude"]) if sd["exclude"] else None
                wre = re.compile(sd["within"]) if sd["within"] else None
            except re.error:
                continue
            compiled.append((p["id"], sd, rx, fre, ere, wre))
        for st in (p.get("subtypes") or []):
            for s in st["sig"]:
                try:
                    sub_compiled.append((p["id"], st["id"], s, re.compile(s)))
                except re.error:
                    continue
            if st.get("pair"):
                try:
                    pa = re.compile(st["pair"]["a"])
                    pb = re.compile(st["pair"]["b"])
                except re.error:
                    continue
                pair_items.append((p["id"], st["id"], pa, pb,
                                   st["pair"]["scope"], st["pair"]["max_diff"],
                                   st["pair"]["strict"], st["pair"]["id_re"]))
    for path in files:
        try:
            text = read_text(path)
        except OSError:
            continue
        lines = text.splitlines()
        rel = path.replace("\\", "/")
        ext = os.path.splitext(path)[1].lower()
        # 仅为确实用到 within 的签名预计算行区间
        ranges = {}
        for pid, sd, rx, fre, ere, wre in compiled:
            if wre is not None and (pid, sd["within"]) not in ranges:
                ranges[(pid, sd["within"])] = _func_line_ranges(text, wre)
        # 子型配对判据（v6.7）：A↔B 计数失衡即候选。这是**结构判据**而非"出现即命中"——
        # SetFlag 出现 10 次、WaitFlag 出现 4 次，任何单行都不异常，只有计数关系异常。
        if pair_items:
            keep = [i for i, l in enumerate(lines, 1)
                    if not (skip_comments and _is_comment_line(l, ext))]
            for pid, sid, pa, pb, scope, max_diff, strict, id_re in pair_items:
                if scope != "file":       # 目前只支持文件级（函数级 pair 见 README 能力边界）
                    continue
                na, nb, viol = pair_stats(lines, keep, pa, pb, strict, id_re)
                if strict:
                    for ln, key in viol:
                        hits.append({"pattern": pid, "subtype": sid, "file": path,
                                     "line": ln,
                                     "signature": "strict %s (id=%s)" % (pa.pattern[:20], key[:24]),
                                     "counts": {"a": 1, "b": 0}, "broad": False,
                                     "code": lines[ln - 1].strip()[:200]})
                if na == nb or abs(na - nb) <= max_diff:
                    continue
                ln = next((i for i in keep if pa.search(lines[i - 1]) or pb.search(lines[i - 1])), 0)
                hits.append({"pattern": pid, "subtype": sid, "file": path, "line": ln,
                             "signature": "pair %s↔%s" % (pa.pattern[:24], pb.pattern[:24]),
                             "counts": {"a": na, "b": nb}, "broad": False,
                             "code": (lines[ln - 1].strip()[:200] if ln else "")})
        for i, line in enumerate(lines, 1):
            if skip_comments and _is_comment_line(line, ext):
                continue
            sub_hit = {}
            for pid, sid, sig, rx in sub_compiled:
                if pid in sub_hit:
                    continue
                if rx.search(line):
                    sub_hit[pid] = (sid, sig)
            for pid, sd, rx, fre, ere, wre in compiled:
                if fre is not None and not fre.search(rel):
                    continue
                if ere is not None and ere.search(line):
                    continue
                if wre is not None:
                    rngs = ranges.get((pid, sd["within"])) or []
                    if not any(a <= i <= b for a, b in rngs):
                        continue
                if pid in sub_hit:          # 同一行已由子型指纹定性，不重复报模式级
                    continue
                if rx.search(line):
                    hits.append({"pattern": pid, "subtype": None, "file": path, "line": i,
                                 "signature": sd["re"],
                                 "broad": sd["re"] in broad_of.get(pid, set()),
                                 "code": line.strip()[:200]})
            for pid, (sid, sig) in sub_hit.items():
                hits.append({"pattern": pid, "subtype": sid, "file": path, "line": i,
                             "signature": sig, "broad": False,
                             "code": line.strip()[:200]})
    # 截断前排序（v6.7）：结构型候选（pair，带 counts）> 子型指纹候选 > 模式级指纹候选。
    # 否则一条定位型指纹会在遍历早期把配额吃光，后面真正的结构失衡反而被截掉。
    hits.sort(key=lambda h: 0 if h.get("counts") else (1 if h.get("subtype") else 2))
    per = {}
    per_sig = {}
    kept = []
    broad_total = sum(1 for h in hits if h.get("broad"))
    for h in hits:
        n = per.get(h["pattern"], 0)
        if max_per is not None and n >= max_per:
            if h["pattern"] not in truncated:
                truncated.append(h["pattern"])
            continue
        if max_per_sig:
            k = (h["pattern"], h["signature"])
            m = per_sig.get(k, 0)
            if m >= max_per_sig:
                if k not in truncated:
                    truncated.append(k)
                continue
            per_sig[k] = m + 1
        kept.append(h)
        per[h["pattern"]] = n + 1
    return kept, truncated, broad_total


def _extract_braced(text, start):
    """从 start 起找第一个 '{'，按花括号配对返回函数体（粗略跳过字符串与注释）。"""
    i = text.find("{", start)
    if i < 0:
        return ""
    depth = 0
    j = i
    n = len(text)
    while j < n:
        ch = text[j]
        if ch == '"':
            j += 1
            while j < n and text[j] != '"':
                if text[j] == "\\":
                    j += 1
                j += 1
        elif ch == "'":
            j += 1
            while j < n and text[j] != "'":
                if text[j] == "\\":
                    j += 1
                j += 1
        elif ch == "/" and j + 1 < n and text[j + 1] == "/":
            while j < n and text[j] != "\n":
                j += 1
        elif ch == "/" and j + 1 < n and text[j + 1] == "*":
            j += 2
            while j + 1 < n and not (text[j] == "*" and text[j + 1] == "/"):
                j += 1
            j += 1
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
        j += 1
    return text[i:]


def _brace_pos(text, pos):
    r"""锚点归一（v6.5）：若锚点前一个字符正是 `{`，就从该 `{` 起配对。

    absence 规则的 `branch` 允许写成带开括号（`catch\s*\([^)]*\)\s*\{`）或不带（`catch\s*\([^)]*\)`）。
    带括号时若仍从 pos 往后找下一个 `{`，会误取内层块——这会让「有日志的 catch」被误报为「静默吞」。
    """
    if pos > 0 and text[pos - 1] == "{":
        return pos - 1
    return pos


def scan_absence(files, patterns, only=None):
    """缺失型检查：文件命中 files 正则、但 must 正则不出现 → 候选（文件级或函数级）。

    规则字段：files（路径正则）、must（必须有）、可选 when（前置条件）、
    可选 func（函数签名正则；给定时在函数体内判断 when/must，函数级候选更精确）。
    """
    cands, stats = [], []
    for p in patterns:
        if only and p["id"] not in only:
            continue
        for rule in p["absence"]:
            try:
                must = re.compile(rule["must"])
                fre = re.compile(rule["files"])
                when = re.compile(rule["when"]) if rule.get("when") else None
                func = re.compile(rule["func"]) if rule.get("func") else None
                branch = re.compile(rule["branch"]) if rule.get("branch") else None
                exclude_sig = re.compile(rule["exclude_sig"]) if rule.get("exclude_sig") else None
            except re.error:
                continue
            matched = missing = 0
            for f in files:
                rel = f.replace("\\", "/")
                if not fre.search(rel):
                    continue
                try:
                    text = read_text(f)
                except OSError:
                    continue
                if branch is not None and func is None:
                    for m in branch.finditer(text):
                        body = _extract_braced(text, _brace_pos(text, m.end()))
                        if not body:
                            continue
                        if when is not None and not when.search(body):
                            continue
                        matched += 1
                        if not must.search(body):
                            missing += 1
                            cands.append({"pattern": p["id"], "file": f, "must": rule["must"],
                                          "when": rule.get("when", ""),
                                          "branch": m.group(0).strip()[:80],
                                          "level": rule.get("level", "high"),
                                          "note": rule.get("note", "")})
                    continue
                if func is not None:
                    for m in func.finditer(text):
                        body = _extract_braced(text, _brace_pos(text, m.end()))
                        if not body:
                            continue
                        if exclude_sig is not None:
                            brace = text.find("{", m.end())
                            sig_text = text[m.start():brace if brace >= 0 else m.end() + 200]
                            if exclude_sig.search(sig_text):
                                continue
                        if branch is not None:
                            for m2 in branch.finditer(body):
                                b2 = _extract_braced(body, _brace_pos(body, m2.end()))
                                if not b2:
                                    continue
                                if when is not None and not when.search(b2):
                                    continue
                                matched += 1
                                if not must.search(b2):
                                    missing += 1
                                    cands.append({"pattern": p["id"], "file": f,
                                                  "must": rule["must"],
                                                  "when": rule.get("when", ""),
                                                  "func": m.group(0).strip()[:60],
                                                  "branch": m2.group(0).strip()[:60],
                                                  "level": rule.get("level", "high"),
                                                  "note": rule.get("note", "")})
                            continue
                        if when is not None and not when.search(body):
                            continue
                        matched += 1
                        if not must.search(body):
                            missing += 1
                            cands.append({"pattern": p["id"], "file": f, "must": rule["must"],
                                          "when": rule.get("when", ""),
                                          "func": m.group(0).strip()[:80],
                                          "level": rule.get("level", "high"),
                                          "note": rule.get("note", "")})
                    continue
                if when is not None and not when.search(text):
                    continue
                matched += 1
                if not must.search(text):
                    missing += 1
                    cands.append({"pattern": p["id"], "file": f, "must": rule["must"],
                                  "when": rule.get("when", ""),
                                  "level": rule.get("level", "high"),
                                  "note": rule.get("note", "")})
            stats.append({"pattern": p["id"], "files": matched, "missing": missing,
                          "rule": rule["files"], "when": rule.get("when", ""),
                          "branch": rule.get("branch", ""),
                          "func": rule.get("func", "")})
    # v6.5：absence 规则可挂 subtype（候选落到子型，便于按子型收敛）
    sub_of = {}
    for p in patterns:
        for r in p["absence"]:
            if r.get("subtype"):
                sub_of[(p["id"], r["must"])] = r["subtype"]
    for c in cands:
        c["subtype"] = sub_of.get((c["pattern"], c["must"]))
    return cands, stats


def hygiene(patterns):
    """签名卫生检查。

    ERROR：不可编译 / 匹配空串 / 跨模式重复（必然失效或噪声爆炸）
    WARN ：缺少 ≥3 字符字面量（判别性不足，可能是宽泛表达式）
    """
    errs, warns, seen = [], [], {}
    items = []
    for p in patterns:
        for sd in p["signatures"]:
            items.append((p["id"], sd["re"], "signature"))
        for r in p["absence"]:
            items.append((p["id"], r["must"], "absence.must"))
            items.append((p["id"], r["files"], "absence.files"))
        for s in p["log_signatures"]:
            items.append((p["id"], s, "log"))
    for pid, s, kind in items:
        try:
            rx = re.compile(s)
        except re.error as e:
            errs.append("%s %s 不可编译：%r（%s）" % (pid, kind, s, e))
            continue
        if rx.search(""):
            errs.append("%s %s 匹配空串（必然全命中）：%r" % (pid, kind, s))
        if kind != "absence.files":
            literals = re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]{3,}", s)
            if not literals:
                warns.append("%s %s 缺少 ≥3 字符字面量，判别性不足：%r" % (pid, kind, s))
        if kind == "signature":
            if s in seen and seen[s] != pid:
                errs.append("签名跨模式重复：%s 与 %s 共用 %r" % (seen[s], pid, s))
            seen[s] = pid
    return errs, warns


def _sample_from_regex(s):
    """把一个简单正则反推成示例文本（仅供自检冒烟用）；推不出可匹配样本时返回 None。"""
    t = s.replace("\\s*", "").replace("\\s+", " ").replace("\\s", " ")
    t = t.replace("\\w*", "x").replace("\\w+", "x").replace("\\d+", "1").replace("\\d", "1")
    t = re.sub(r"\[\^;\]\{0,\d+\}", "x", t)
    for a, b in (("\\(", "("), ("\\)", ")"), ("\\[", "["), ("\\]", "]"),
                 ("\\.", "."), ("\\|", "|")):
        t = t.replace(a, b)
    t = re.sub(r"\(([^()|]+)\|([^()|]+)\)", r"\1", t)
    t = re.sub(r"\(([^()]*)\)\?", r"\1", t)
    t = re.sub(r"\{0,\d+\}", "", t)
    try:
        if re.search(s, t):
            return t
    except re.error:
        pass
    return None


def self_test(root):
    _, patterns = load_patterns(root)
    errs, warns = hygiene(patterns)
    if errs:
        for f in errs:
            print("[FAIL] " + f)
        return 2
    total = sum(len(p["signatures"]) for p in patterns)
    if total == 0:
        print("[FAIL] 索引里没有任何签名")
        return 2
    # 端到端冒烟：FP-G01 的 while(true) 类签名必须能在合成样本上出候选
    g01 = next((p for p in patterns if p["id"] == "FP-G01"), None)
    if g01 and g01["signatures"]:
        import tempfile
        tmp = tempfile.mkdtemp(prefix="scan_fp_")
        f = os.path.join(tmp, "probe.cpp")
        with open(f, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("void f() {\n  while (true) { x += 1; }\n}\n")
        hits, _, _ = scan_files([f], patterns, only={"FP-G01"})
        if not hits:
            print("[FAIL] 冒烟失败：while(true) 未在 FP-G01 上产生候选")
            return 2
    # 子型冒烟（v6.3）：带子型指纹的模式，命中须落到「子型级」而非模式级
    sub_pats = [p for p in patterns if any(st["sig"] for st in p.get("subtypes") or [])]
    if sub_pats:
        import tempfile
        probe_pat = sub_pats[0]
        probe_st = next(st for st in probe_pat["subtypes"] if st["sig"])
        sample = _sample_from_regex(probe_st["sig"][0])
        if sample is not None:
            tmp = tempfile.mkdtemp(prefix="scan_sub_")
            f = os.path.join(tmp, "probe_sub.cpp")
            with open(f, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("void f() {\n  %s\n}\n" % sample)
            hits, _, _ = scan_files([f], patterns, only={probe_pat["id"]})
            if not hits or not hits[0].get("subtype"):
                print("[FAIL] 子型冒烟失败：%s 的子型指纹未产出子型级候选" % probe_pat["id"])
                return 2
    # absence 冒烟：有规则时，缺 must 的文件必须被报出、完整文件不得误报
    # 配对判据冒烟（v6.7）：A/B 计数失衡出候选、配平不出
    pair_pats = [p for p in patterns if any(st.get("pair") for st in p.get("subtypes") or [])]
    if pair_pats:
        import tempfile
        pp = pair_pats[0]
        st = next(s for s in pp["subtypes"] if s.get("pair"))
        sa = _sample_from_regex(st["pair"]["a"])
        sb = _sample_from_regex(st["pair"]["b"])
        if sa and sb and sa != sb:
            tmp = tempfile.mkdtemp(prefix="scan_pair_")
            bad = os.path.join(tmp, "bad.cpp")
            good = os.path.join(tmp, "good.cpp")
            with open(bad, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("void f() {\n  %s\n  %s\n  %s\n}\n" % (sa, sa, sb))
            with open(good, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("void f() {\n  %s\n  %s\n}\n" % (sa, sb))
            hb, _, _ = scan_files([bad], patterns, only={pp["id"]})
            hg, _, _ = scan_files([good], patterns, only={pp["id"]})
            if not any(h.get("counts") for h in hb):
                print("[FAIL] 配对冒烟失败：失衡文件未产出带 counts 的候选")
                return 2
            if any(h.get("counts") for h in hg):
                print("[FAIL] 配对冒烟失败：配平文件被误报")
                return 2
            # strict 冒烟（v6.9）：同 id 连续两次 A 必须报；A/B 交替不得报
            if st["pair"]["strict"] and st["pair"]["id_re"]:
                sid_re = re.compile(st["pair"]["id_re"])
                sa_s, sb_s = sa, sb
                if not sid_re.search(sa_s):
                    sa_s, sb_s = sa + "(E0)", sb + "(E0)"      # 补出参数位，供 id 提取
                if sid_re.search(sa_s):
                    tmp2 = tempfile.mkdtemp(prefix="scan_strict_")
                    f2 = os.path.join(tmp2, "s.cpp")
                    with open(f2, "w", encoding="utf-8", newline="\n") as fh:
                        fh.write("void f() {\n  %s\n  %s\n  %s\n}\n" % (sa_s, sa_s, sb_s))
                    hs, _, _ = scan_files([f2], patterns, only={pp["id"]})
                    if not any(h.get("signature", "").startswith("strict") for h in hs):
                        print("[FAIL] strict 冒烟失败：同 id 连续两次 A 未报出")
                        return 2
                    f3 = os.path.join(tmp2, "ok.cpp")
                    with open(f3, "w", encoding="utf-8", newline="\n") as fh:
                        fh.write("void f() {\n  %s\n  %s\n  %s\n  %s\n}\n" % (sa_s, sb_s, sa_s, sb_s))
                    hs2, _, _ = scan_files([f3], patterns, only={pp["id"]})
                    if any(h.get("signature", "").startswith("strict") for h in hs2):
                        print("[FAIL] strict 冒烟失败：A/B 交替的正常序列被误报")
                        return 2
    abs_pats = [p for p in patterns if p["absence"]]
    if abs_pats:
        import tempfile
        tmp = tempfile.mkdtemp(prefix="scan_abs_")
        os.makedirs(os.path.join(tmp, "op_api"))
        bad = os.path.join(tmp, "op_api", "aclnn_bad.cpp")
        good = os.path.join(tmp, "op_api", "aclnn_good.cpp")
        funcbad = os.path.join(tmp, "op_api", "aclnn_funcbad.cpp")
        for path, body in ((bad, "void f() {}\n"),
                           (good, "void g() {\n"
                                  "  CheckNotNull(x); CheckParams(y);\n"
                                  "  if (x->IsEmpty()) { Duplicate(y); }\n"
                                  "}\n"),
                           (funcbad, "aclnnStatus aclnnFoo(int x) {\n"
                                     "  CheckNotNull(x); CheckParams(x);\n"
                                     "  if (x->IsEmpty()) { return ACLNN_SUCCESS; }\n"
                                     "}\n")):
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body)
        cands, _ = scan_absence([bad, good, funcbad], abs_pats)
        if not any(c["file"] == bad for c in cands):
            print("[FAIL] absence 冒烟失败：缺 must 的文件未被报出")
            return 2
        if any(c["file"] == good for c in cands):
            print("[FAIL] absence 冒烟失败：完整文件被误报")
            return 2
        if any((r.get("func") or r.get("branch")) for p in abs_pats for r in p["absence"]):
            if not any(c.get("func") or c.get("branch") for c in cands):
                print("[FAIL] absence 冒烟失败：函数/分支级规则未报出「早退 SUCCESS 无写输出」")
                return 2
    # 折叠冒烟（v6.10）：同一文件多条候选应折成一条并带 count
    collapse_ran = False
    probe_sig = None
    for p in patterns:
        for sd in p["signatures"]:
            if not sd["files"] and not sd["within"] and not sd["exclude"]:
                probe_sig = (p["id"], sd["re"])
                break
        if probe_sig:
            break
    if probe_sig:
        sample = _sample_from_regex(probe_sig[1])
        if sample:
            import tempfile
            tmp = tempfile.mkdtemp(prefix="scan_collapse_")
            f = os.path.join(tmp, "c.cpp")
            with open(f, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("%s\n%s\n" % (sample, sample))
            hc, _, _ = scan_files([f], patterns, only={probe_sig[0]})
            folded = collapse_hits(hc, "file")
            collapse_ran = True
            if len(hc) >= 2 and not (len(folded) == 1 and folded[0].get("count") == len(hc)):
                print("[FAIL] 折叠冒烟失败：%d 条候选未折成 1 条（count 不符）" % len(hc))
                return 2
    _parts = ["端到端冒烟"]
    if pair_pats:
        _parts.append("配对判据")
    if abs_pats:
        _parts.append("absence")
    if collapse_ran:
        _parts.append("折叠")
    print("[PASS] self-test：%d 条签名通过卫生检查（WARN %d 条判别性偏弱），%s 通过"
          % (total, len(warns), "、".join(_parts)))
    return 0


def load_case_index(root):
    """cases/cases.json → {fp_id: {文件 basename: [case_id, ...]}}（v5.5，供 --cases 回挂）。"""
    p = os.path.join(root, "cases", "cases.json")
    if not os.path.isfile(p):
        return {}
    with open(p, encoding="utf-8-sig") as f:
        d = json.load(f)
    out = {}
    for c in d.get("cases", []):
        for loc in ((c.get("criteria") or {}).get("locators") or []):
            base = os.path.basename(str(loc.get("file", "")).replace("\\", "/"))
            if base:
                out.setdefault(c["fp_id"], {}).setdefault(base, []).append(c["case_id"])
    return out


def collapse_hits(hits, mode):
    """折叠候选（v6.10）：阅读量与筛选效率问题——4533 行候选按文件折叠后通常只剩几百条。"""
    if mode == "none":
        return hits
    out, idx = [], {}
    for h in hits:
        key = (h["pattern"], h.get("subtype"))
        if mode == "file":
            key = key + (h["file"],)
        if key in idx:
            e = out[idx[key]]
            e["count"] += 1
            if len(e["lines"]) < 5:
                e["lines"].append(h["line"])
            if mode == "subtype" and h["file"] not in e["files"]:
                if len(e["files"]) < 5:
                    e["files"].append(h["file"])
                e["file_count"] = e.get("file_count", 1) + 1
            continue
        e = dict(h)
        e["count"] = 1
        e["lines"] = [h["line"]]
        if mode == "subtype":
            e["files"] = [h["file"]]
            e["file_count"] = 1
        idx[key] = len(out)
        out.append(e)
    return out


def _print_hit(h, ctx):
    tag = ""
    if h.get("broad"):
        tag += "[BROAD] "
    if h.get("subtype"):
        tag += "[%s] " % h["subtype"]
    if h.get("counts"):
        tag += "[a=%(a)d b=%(b)d] " % h["counts"]
    extra = ""
    if h.get("count", 1) > 1:
        extra = "（合并 %d 处：行 %s）" % (h["count"], ",".join(str(x) for x in h["lines"]))
    elif h.get("file_count", 1) > 1:
        extra = "（合并 %d 个文件）" % h["file_count"]
    print("  %s%s:%d  %s%s" % (tag, h["file"], h["line"], h["code"], extra))
    if ctx > 0:
        try:
            lines = read_text(h["file"]).splitlines()
        except OSError:
            return
        lo = max(0, h["line"] - 1 - ctx)
        hi = min(len(lines), h["line"] + ctx)
        for k in range(lo, hi):
            mark = ">" if k == h["line"] - 1 else " "
            print("       %s%5d %s" % (mark, k + 1, lines[k].strip()[:120]))


def main():
    ap = argparse.ArgumentParser(description="故障模式签名扫描器（候选生成，非判定，v3.8）")
    ap.add_argument("targets", nargs="*", help="待扫文件或目录")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--only", default="", help="只扫指定模式，逗号分隔（如 FP-A06,FP-G01）")
    ap.add_argument("--ext", default=",".join(DEFAULT_EXTS), help="扩展名白名单，逗号分隔")
    ap.add_argument("--format", default="text", choices=("text", "json"))
    ap.add_argument("--max-per-pattern", type=int, default=50)
    ap.add_argument("--out", default="", help="JSON 输出文件（--format json 时可选）")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--subtypes", action="store_true",
                    help="列出子型（id / 名称 / 是否带可扫指纹），不扫文件（v6.3）")
    ap.add_argument("--cases", action="store_true",
                    help="把候选回挂 cases/cases.json 的已知案例（同模式 + 同名文件锚，v5.5）")
    ap.add_argument("--stats", action="store_true",
                    help="语料回归统计：按模式/签名计数，列出零命中与宽泛签名（不截断）")
    ap.add_argument("--exclude", default="",
                    help="路径片段黑名单，逗号分隔（如 /tests/,/examples/,/build/）")
    ap.add_argument("--absence", action="store_true",
                    help="缺失型检查：文件命中 files 正则但缺少 must 正则 → 文件级候选")
    ap.add_argument("--include-comments", action="store_true",
                    help="不跳过纯注释行（默认跳过 // 、块注释与 .py/.sh 的 #，v6.5 降噪）")
    ap.add_argument("--broad", default="count", choices=("count", "list", "off"),
                    help="宽泛签名（broad_signatures）的处置：count=只报命中数（默认）/ list=也列候选 / off=完全忽略（v6.6）")
    ap.add_argument("--max-per-signature", type=int, default=200,
                    help="单条签名的候选上限（0 = 不限，v6.6；防一条宽泛签名刷屏）")
    ap.add_argument("--collapse", default="none", choices=("none", "file", "subtype"),
                    help="折叠候选（v6.10）：file=同模式同子型同文件合成一条（带 count/lines）/ "
                         "subtype=再跨文件合成一条（带 files）；默认 none")
    ap.add_argument("--context", type=int, default=0,
                    help="文本模式下打印候选前后 N 行（v6.10，默认 0）")
    ap.add_argument("--log", action="store_true",
                    help="日志型检查：用 log_signatures 扫描 .log/.txt 文件")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    try:
        _, patterns = load_patterns(root)
    except (OSError, ValueError) as e:
        print("[ERROR] 读取索引失败：%s" % e)
        return 2

    if args.self_test:
        return self_test(root)
    if args.subtypes:
        want = {x.strip() for x in args.only.split(",") if x.strip()}
        n_pat = n_sub = n_sig = 0
        for p in patterns:
            if want and p["id"] not in want:
                continue
            if not p["subtypes"]:
                continue
            n_pat += 1
            print("== %s %s（%d 子型）" % (p["id"], p["name"], len(p["subtypes"])))
            for st in p["subtypes"]:
                n_sub += 1
                kind = ("pair+序" if st.get("pair") and st["pair"].get("strict")
                        else ("pair" if st.get("pair") else ("扫描" if st["sig"] else "人工")))
                if st["sig"] or st.get("pair"):
                    n_sig += 1
                print("  %-8s %-4s %s" % (st["id"], kind, st["name"][:90]))
        print("[SUMMARY] 模式 %d / 子型 %d / 其中带可扫指纹 %d"
              % (n_pat, n_sub, n_sig))
        return 0
    if not args.targets:
        ap.print_help()
        return 2

    only = {x.strip() for x in args.only.split(",") if x.strip()}
    exts = tuple(x.strip().lower() for x in args.ext.split(",") if x.strip())
    skip_comments = not args.include_comments
    files = list(iter_files(args.targets, exts))
    ex = [x.strip().replace("\\", "/") for x in args.exclude.split(",") if x.strip()]
    if ex:
        files = [f for f in files if not any(e in f.replace("\\", "/") for e in ex)]
    if args.absence:
        cands, astats = scan_absence(files, patterns, only=only)
        for s in astats:
            print("[ABS] %-8s files=%-5d missing=%-5d rule=%s"
                  % (s["pattern"], s["files"], s["missing"], s["rule"]))
        for c in cands:
            tag = "[%s] " % c["subtype"] if c.get("subtype") else ""
            print("[CAND][%s] %s%s  缺少：%s" % (c["level"], tag, c["file"], c["must"]))
        print("[SUMMARY] absence candidates=%d（缺失型：文件级候选，仍需逐条确认）" % len(cands))
        return 1 if cands else 0

    if args.log:
        log_files = []
        for t in args.targets:
            if os.path.isfile(t):
                log_files.append(t)
            elif os.path.isdir(t):
                for dp, dns, fns in os.walk(t):
                    dns[:] = [d for d in dns if d not in SKIP_DIRS]
                    for fn in fns:
                        if os.path.splitext(fn)[1].lower() in (".log", ".txt"):
                            log_files.append(os.path.join(dp, fn))
        hits = 0
        for path in log_files:
            lines = read_text(path).splitlines()
            for i, line in enumerate(lines, 1):
                for p in patterns:
                    if only and p["id"] not in only:
                        continue
                    for s in p["log_signatures"]:
                        if re.search(s, line):
                            hits += 1
                            print("[LOG][%s] %s:%d  %s" % (p["id"], path, i, line.strip()[:160]))
        print("[SUMMARY] log files=%d hits=%d" % (len(log_files), hits))
        return 1 if hits else 0

    if args.stats:
        hits, _, _ = scan_files(files, patterns, only=only, max_per=None, skip_comments=skip_comments)
        per_sig, per_pat, per_file = {}, {}, {}
        for h in hits:
            per_sig[(h["pattern"], h["signature"])] = per_sig.get((h["pattern"], h["signature"]), 0) + 1
            per_pat[h["pattern"]] = per_pat.get(h["pattern"], 0) + 1
            per_file[h["file"]] = per_file.get(h["file"], 0) + 1
        total_sig = sum(len(p["signatures"]) for p in patterns if not only or p["id"] in only)
        dead = [(p["id"], sd["re"]) for p in patterns if not only or p["id"] in only
                for sd in p["signatures"] if per_sig.get((p["id"], sd["re"]), 0) == 0]
        broad = sorted(((k[0], k[1], v) for k, v in per_sig.items() if v >= 100),
                       key=lambda x: -x[2])
        broad_set = {(p["id"], s) for p in patterns if not only or p["id"] in only
                     for s in p["broad"]}
        b_total = sum(v for k, v in per_sig.items() if k in broad_set)
        print("[STATS] files=%d signatures=%d hits=%d patterns_hit=%d/%d broad_hits=%d"
              % (len(files), total_sig, len(hits), len(per_pat), len(patterns), b_total))
        print("\n== 命中分布（按模式，降序）==")
        for pid, n in sorted(per_pat.items(), key=lambda x: -x[1]):
            print("  %-8s %6d" % (pid, n))
        print("\n== 零命中签名（%d / %d）==" % (len(dead), total_sig))
        for pid, s in dead:
            print("  %-8s %s" % (pid, s[:100]))
        print("\n== 宽泛标记命中（broad_signatures，%d 处；只作定位提示）==" % b_total)
        for (pid, s), v in sorted(((k, v) for k, v in per_sig.items() if k in broad_set),
                                  key=lambda x: -x[1]):
            print("  %-8s %6d  %s" % (pid, v, s[:90]))
        print("\n== 宽泛签名（≥100 命中，未标记者也列出）==")
        for pid, s, v in broad:
            if (pid, s) not in broad_set:
                print("  %-8s %6d  %s" % (pid, v, s[:90]))
        print("\n== 命中最多文件 ==")
        for f, n in sorted(per_file.items(), key=lambda x: -x[1])[:10]:
            print("  %5d  %s" % (n, f))
        _, astats = scan_absence(files, patterns, only=only)
        if astats:
            print("\n== 缺失型规则（absence）==")
            for s in astats:
                mode = "branch" if s.get("branch") else ("func" if s.get("func") else "file")
                print("  %-8s %-6s files=%-5d missing=%-5d  %s"
                      % (s["pattern"], mode, s["files"], s["missing"], s["rule"]))
        print("\n[NOTE] 零命中可能是「本仓不适用」或「签名不是源码指纹」（命令/日志/概念）；"
              "宽泛签名只宜作定位提示，不宜作为候选生成依据。")
        return 0
    hits, truncated, n_broad = scan_files(files, patterns, only=only, max_per=args.max_per_pattern,
                                          skip_comments=skip_comments,
                                          max_per_sig=args.max_per_signature)
    if args.broad != "list":
        hits = [h for h in hits if not h.get("broad")]
    if args.cases:
        cmap = load_case_index(root)
        for h in hits:
            base = os.path.basename(h["file"].replace("\\", "/"))
            ids = cmap.get(h["pattern"], {}).get(base)
            if ids:
                h["known_cases"] = sorted(ids)
    n_raw = len(hits)
    hits = collapse_hits(hits, args.collapse)
    result = {"scanned_files": len(files), "hits": len(hits), "hits_before_collapse": n_raw,
              "collapse": args.collapse,
              "broad_hits": n_broad, "broad_mode": args.broad,
              "truncated": truncated, "candidates": hits}
    if args.format == "json":
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="\n") as f:
                f.write(text + "\n")
            print("[OK] %d 条候选 → %s" % (len(hits), args.out))
        else:
            print(text)
    else:
        by = {}
        for h in hits:
            by.setdefault(h["pattern"], []).append(h)
        for pid in sorted(by):
            print("== %s（%d 条候选）" % (pid, len(by[pid])))
            for h in by[pid][:args.max_per_pattern]:
                if h.get("known_cases"):
                    print("  [CASE %s] %s:%d  %s"
                          % (",".join(h["known_cases"]), h["file"], h["line"], h["code"]))
                    continue
                _print_hit(h, args.context)
        if truncated:
            print("[WARN] 以下模式/签名候选超过上限，已截断：%s"
                  % ", ".join(sorted(str(x) for x in truncated)))
        print("[SUMMARY] files=%d hits=%d%s patterns=%d"
              % (len(files), len(hits),
                 ("（折叠前 %d）" % n_raw) if args.collapse != "none" else "",
                 len(by)))
        if n_broad and args.broad == "count":
            print("[BROAD] 另有 %d 处宽泛签名命中未计入候选（只作定位提示；--broad list 可列出）" % n_broad)
    if args.format != "json":       # JSON 模式不混尾注，便于管道消费（v6.6）
        print("[NOTE] 候选 ≠ 缺陷：逐条按对应 skill 第 7 节做正负证据与证据等级判定；未命中 ≠ 无缺陷。")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
