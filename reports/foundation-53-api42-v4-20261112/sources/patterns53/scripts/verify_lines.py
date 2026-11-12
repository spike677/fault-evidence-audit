#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报告行号校验（verify_lines.py，v3.5）

用途
----
检视报告的价值几乎全部押在 `文件:行号` 证据上，而 LLM 最典型的失真就是行号偏移、
张冠李戴或凭空捏造。本脚本把报告里的每一处 `path:line` 引用拉出来逐条核对：
文件是否存在、行号是否越界、该行是否为空白 / 纯括号 / 纯注释（无有效内容）。

用法
----
python3 verify_lines.py <报告.md> [<报告2.md> ...] [--root <被检仓根目录>]
                        [--json] [--strict] [--no-basename] [--quiet]
python3 verify_lines.py --self-test

退出码
------
0 = 全部引用可核对（可含 WARN：basename 唯一解析、空行/无有效内容）
1 = 存在错误（文件缺失 / 行号越界 / 行号非法）
2 = 参数或环境错误
3 = 仅有 WARN（默认）；--strict 时 WARN 升级为 1

口径
----
- 引用形式：`path/to/file.cpp:123`、`path/to/file.cpp:123-130`；反引号内或裸写均可，
  路径须以常见源码/文本扩展名结尾；http(s) 链接不计入。
- 路径解析：先按 --root 相对解析；缺失时按 basename 在 --root 下唯一匹配（WARN）；
  同名多处记为 ambiguous（WARN，不判错）；仍无命中记为 missing（ERROR）。
- 行内容：空白行、仅 `{`/`}`/`;`/`)` 等符号、仅 `//` `/*` `*` 注释起始 → WARN。
- 行号以 1 起始；范围引用核对起点与终点，且要求 终点 ≥ 起点。
"""

import argparse
import json
import os
import re
import sys
import tempfile

EXTS = r"(?:cpp|cc|cxx|c|hpp|hh|h|py|sh|jsonl|json|md|txt|cmake|yaml|yml|asc|inc|proto)"
BACKTICK_RE = re.compile(
    r"`(?P<path>[^`\s|]+?" + EXTS + r"):(?P<start>\d+)"
    r"(?:[-–~](?P<end>\d+))?`")
BARE_RE = re.compile(
    r"(?<![`\w/.\-])(?P<path>[A-Za-z0-9_][A-Za-z0-9_./\\\-]*?" + EXTS + r")"
    r":(?P<start>\d+)(?:[-–~](?P<end>\d+))?(?![\d`])")

SKIP_DIRS = {".git", "node_modules", "build", "output", "third_party", "thirdparty",
             "__pycache__", ".venv", "venv", "dist", ".idea", ".vscode"}

SYMBOL_ONLY_RE = re.compile(r"^[\s{}()\[\];,]+$")
COMMENT_ONLY_RE = re.compile(r"^\s*(?://|/\*|\*)")


def read_text(path):
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def extract_refs(text):
    """返回 [(path, start, end, matched_text)]，反引号优先，裸写去重。"""
    refs, seen = [], set()

    def add(m):
        path = m.group("path").replace("\\", "/")
        start = int(m.group("start"))
        end = int(m.group("end")) if m.group("end") else None
        key = (path, start, end)
        if key not in seen:
            seen.add(key)
            refs.append((path, start, end, m.group(0)))

    for m in BACKTICK_RE.finditer(text):
        add(m)
    masked = BACKTICK_RE.sub(lambda m: " " * len(m.group(0)), text)
    for m in BARE_RE.finditer(masked):
        add(m)
    return refs


def build_basename_index(root):
    index = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            index.setdefault(fn, []).append(os.path.join(dirpath, fn))
    return index


def resolve_path(path, root, basename_index):
    norm = os.path.normpath(os.path.join(root, path.replace("/", os.sep)))
    if os.path.isfile(norm):
        return norm, "direct"
    if basename_index is None:
        return None, "missing"
    hits = basename_index.get(os.path.basename(path), [])
    if len(hits) == 1:
        return hits[0], "basename"
    if len(hits) > 1:
        return None, "ambiguous"
    return None, "missing"


def line_status(lines, start, end):
    """返回 (status, snippet, note)。status ∈ ok/empty/comment/range_invalid。"""
    total = len(lines)
    if start < 1:
        return "range_invalid", "", "行号必须 ≥ 1"
    if start > total:
        return "range_invalid", "", "行号 %d 越界（文件共 %d 行）" % (start, total)
    if end is not None:
        if end < start:
            return "range_invalid", "", "范围终点 %d < 起点 %d" % (end, start)
        if end > total:
            return "range_invalid", "", "范围终点 %d 越界（文件共 %d 行）" % (end, total)
    raw = lines[start - 1]
    snippet = raw.strip()[:120]
    if not snippet:
        return "empty", snippet, "该行为空"
    if SYMBOL_ONLY_RE.match(raw):
        return "empty", snippet, "该行仅含括号/分号等符号"
    if COMMENT_ONLY_RE.match(raw):
        return "comment", snippet, "该行仅为注释"
    return "ok", snippet, ""


def verify(report_paths, root, use_basename=True):
    basename_index = build_basename_index(root) if use_basename else None
    records = []
    for report in report_paths:
        text = read_text(report)
        for path, start, end, raw in extract_refs(text):
            resolved, how = resolve_path(path, root, basename_index)
            rec = {"report": report, "ref": raw, "path": path, "start": start,
                   "end": end, "resolved": resolved, "resolve": how}
            if resolved is None:
                rec["status"] = "missing" if how == "missing" else "ambiguous"
                rec["snippet"] = ""
                rec["note"] = ("未在 --root 下找到同名文件" if how == "missing"
                               else "同名文件多处，需写全路径")
            else:
                lines = read_text(resolved).splitlines()
                st, snippet, note = line_status(lines, start, end)
                rec["status"] = st if st != "range_invalid" else "out_of_range"
                rec["snippet"] = snippet
                rec["note"] = note
            records.append(rec)

    errors = [r for r in records if r["status"] in ("missing", "out_of_range")]
    warns = [r for r in records if r["status"] in ("ambiguous", "empty", "comment")
             or r["resolve"] == "basename"]
    return records, errors, warns


def summarize(records, errors, warns):
    total = len(records)
    ok = total - len(errors) - len(warns)
    return {
        "total_refs": total,
        "ok": ok,
        "warn": len(warns),
        "error": len(errors),
        "ok_rate": round(100.0 * ok / total, 1) if total else 100.0,
    }


def print_text(records, errors, warns, quiet):
    order = {"missing": 0, "out_of_range": 1, "ambiguous": 2, "empty": 3, "comment": 4}
    for rec in sorted(records, key=lambda r: (order.get(r["status"], 9), r["path"], r["start"])):
        tag = {"missing": "[ERR] ", "out_of_range": "[ERR] ", "ambiguous": "[WARN]",
               "empty": "[WARN]", "comment": "[WARN]", "ok": "[OK]  "}.get(rec["status"], "[?]   ")
        if quiet and rec["status"] == "ok":
            continue
        loc = "%s:%s%s" % (rec["path"], rec["start"],
                           ("-%d" % rec["end"]) if rec["end"] else "")
        note = ("  ← " + rec["note"]) if rec["note"] else ""
        snip = ("  | " + rec["snippet"]) if rec["snippet"] else ""
        print("%s %-58s%s%s" % (tag, loc, snip, note))
    s = summarize(records, errors, warns)
    print("-" * 78)
    print("[SUMMARY] refs=%d ok=%d warn=%d error=%d ok_rate=%.1f%%"
          % (s["total_refs"], s["ok"], s["warn"], s["error"], s["ok_rate"]))


def run(report_paths, root, use_basename=True, as_json=False, strict=False, quiet=False):
    for rp in report_paths:
        if not os.path.isfile(rp):
            print("[ERROR] 报告不存在：%s" % rp)
            return 2
    records, errors, warns = verify(report_paths, root, use_basename)
    s = summarize(records, errors, warns)
    if as_json:
        print(json.dumps({"status": "error" if errors else ("warn" if warns else "ok"),
                          "root": root, "summary": s, "refs": records},
                         ensure_ascii=False, indent=2))
    else:
        print_text(records, errors, warns, quiet)
    if errors:
        return 1
    if warns:
        return 1 if strict else 3
    return 0


def self_test():
    tmp = tempfile.mkdtemp(prefix="verify_lines_")
    root = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(root, "src"))
    a = os.path.join(root, "src", "a.cpp")
    with open(a, "w", encoding="utf-8", newline="\n") as f:
        for i in range(1, 21):
            f.write("int line%d = %d;  // filler\n" % (i, i))
    with open(a, "a", encoding="utf-8") as f:
        f.write("\n{\n}\n// only comment\n")
    report = os.path.join(tmp, "report.md")
    with open(report, "w", encoding="utf-8", newline="\n") as f:
        f.write("证据：`src/a.cpp:5`\n")          # ok
        f.write("证据：`src/a.cpp:3-6`\n")        # ok
        f.write("证据：`src/a.cpp:99`\n")         # out_of_range
        f.write("证据：`src/nope.cpp:3`\n")       # missing
        f.write("证据：`src/a.cpp:21`\n")         # empty (blank line)
        f.write("证据：`src/a.cpp:22`\n")         # empty (brace)
        f.write("证据：`src/a.cpp:24`\n")         # comment
        f.write("证据：src/a.cpp:7\n")            # bare, ok
    records, errors, warns = verify([report], root, use_basename=True)
    got = [(r["path"], r["start"], r["status"]) for r in records]
    expect = {
        ("src/a.cpp", 5, "ok"),
        ("src/a.cpp", 3, "ok"),
        ("src/a.cpp", 99, "out_of_range"),
        ("src/nope.cpp", 3, "missing"),
        ("src/a.cpp", 21, "empty"),
        ("src/a.cpp", 22, "empty"),
        ("src/a.cpp", 24, "comment"),
        ("src/a.cpp", 7, "ok"),
    }
    if set(got) != expect:
        print("[FAIL] self-test: unexpected records")
        for g in got:
            print("   got:", g)
        print("   missing:", sorted(expect - set(got)))
        return 1
    if len(errors) != 2 or len(warns) != 3:
        print("[FAIL] self-test: errors=%d warns=%d (expect 2/3)"
              % (len(errors), len(warns)))
        return 1
    code = run([report], root, use_basename=True)
    if code != 1:
        print("[FAIL] self-test: exit=%d (expect 1)" % code)
        return 1
    print("[PASS] self-test：8 条引用 / 2 错误 / 3 警告，退出码 1 符合预期")
    return 0


def main():
    ap = argparse.ArgumentParser(description="检视报告行号校验（v3.5）")
    ap.add_argument("reports", nargs="*", help="报告 markdown 路径")
    ap.add_argument("--root", default=os.getcwd(), help="被检仓根目录（默认当前目录）")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--strict", action="store_true", help="WARN 计为失败")
    ap.add_argument("--no-basename", action="store_true", help="禁用 basename 回退解析")
    ap.add_argument("--quiet", action="store_true", help="仅输出 WARN/ERR 与汇总")
    ap.add_argument("--self-test", action="store_true", help="运行内置自检")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.reports:
        ap.print_help()
        return 2
    if not os.path.isdir(args.root):
        print("[ERROR] --root 不是目录：%s" % args.root)
        return 2
    return run(args.reports, os.path.abspath(args.root),
               use_basename=not args.no_basename, as_json=args.json,
               strict=args.strict, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
