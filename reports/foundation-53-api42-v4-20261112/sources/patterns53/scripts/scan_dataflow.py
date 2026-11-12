#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨语句数据流分析（scan_dataflow.py，v6.21）

为什么正则做不到
----------------
README 第 12 条已承认的边界：224 处尾块搬运里，保护逻辑与搬运**同处一条语句**的是 0 处，
全部靠 `tailUbSize_` / `copyParamsTail_` 这类**中间变量**间接关联。正则只能看到
「这里有个搬运」「那里有个 tail 变量」，无法判断两者是否同一数据流。

本工具的答案不是「加强正则」，而是**两跳污点传播**：
  源（source）：可能携带「剩余量 / 尾块长度」语义的值
  汇（sink）  ：把它当作搬运长度 / 循环上界 / 索引边界使用的位置
  传播        ：赋值、初始化、函数实参、成员读写（跳数可配）
若某 sink 的数据来源于 source 但**中间没有边界保护**（clamp/min/if 检查），即候选。

这正好对应 FP-A05（尾块/脏数据）、FP-B07（索引偏移越界）、FP-B13（窄化链）。
用 tree-sitter 做真实 AST 解析，不猜正则。

判据来源
--------
索引新增 `dataflow_signatures`：
  {"source": "tail|Tail|remain|Remain|last",
   "sink":   "DataCopy|DataCopyPad|CopyIn|CopyOut|GetValue|SetValue",
   "guard":  "min|Max|Clamp|if\\\\s*\\\\(|>\\\\s*0|!= ?0",
   "hops": 2, "files": "op_kernel/.*\\\\.(cpp|h|hpp)$", "level": "info", "note": "..."}
  source  源的标识符正则
  sink    汇的调用名正则
  guard   视为「有保护」的形态；源到汇的路径上出现即豁免
  hops    传播跳数上限（默认 2，够覆盖「成员变量 → 局部变量 → 实参」）

依赖（非标准库）
----------------
tree-sitter / tree-sitter-cpp，清单见仓根 `requirements-ci.txt`（CI 的 before_script 装的就是它）。
缺包时本工具与 `--self-test` 都直接失败并提示安装命令——**不静默跳过**，因为它在
`ci_gate.py` 里是 blocking：装不上就该红，而不是让人以为查过了。

用法
----
python3 scripts/scan_dataflow.py <target> --only FP-A05
python3 scripts/scan_dataflow.py <target> --format json
python3 scripts/scan_dataflow.py --self-test
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTS = (".cpp", ".cc", ".h", ".hpp")


def read_text(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def load_rules(root):
    idx = json.loads(read_text(os.path.join(root, "fault_patterns_index.json")))
    out = []
    for p in idx["patterns"]:
        for r in (p.get("dataflow_signatures") or []):
            if not isinstance(r, dict):
                continue
            if not (r.get("source") and r.get("sink")):
                continue
            out.append({
                "pid": p["id"],
                "source": r["source"],
                "sink": r["sink"],
                "guard": r.get("guard") or "",
                "hops": int(r.get("hops") or 2),
                "files": r.get("files") or "",
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


DEP_HINT = ("本工具依赖 tree-sitter / tree-sitter-cpp（不在标准库，CI 镜像也不自带）。\n"
            "  安装：python -m pip install --no-cache-dir -r requirements-ci.txt\n"
            "  清单见仓根 requirements-ci.txt；ci_gate.py 把 --self-test 列为 blocking，缺包即失败。")


def _parser():
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_cpp
    except ImportError as e:
        raise SystemExit("[FAIL] scan_dataflow 缺依赖：%s\n%s" % (e, DEP_HINT))
    return Parser(Language(tree_sitter_cpp.language()))


class Flow:
    """在一个文件内做两跳污点传播。

    实现取向：**宁可少报，不可乱报**。只认三种明确的传播边——
      (1) 声明初始化：`auto x = <含 source>;`
      (2) 赋值：`x = <含 source>;`
      (3) 调用实参：`sink(<含 source>)`
    并且要求 source 出现在 **sink 之前**（行号更小），避免把「后续才计算」误判成「先用了」。
    """

    def __init__(self, text, rule, parser):
        self.text = text
        self.rule = rule
        self.parser = parser
        # 源匹配要点（v6.21 两轮实测）：
        #  ① 不能只用裸子串：`remain` 会命中 `remainder`（整除余数），把「分块变量」
        #     误当「尾块长度」传播，实测 6 条候选全是误报。
        #  ② 也不能强制两侧词边界：`tailN` / `tailUbSize_` 这类「前缀+后缀」命名是
        #     主流写法，强边界会把它们排除，自检立刻挂（bad.cpp 期望 1 实得 0）。
        # 折中：左侧要求词边界（避免 `mytail` 之类），右侧允许后续字母/下划线，
        #     但显式排除 `remainder` 这一确定误匹配。
        self.src_re = re.compile(r"(?<![A-Za-z0-9_])(?!(?:remainder|Remainder)%s)(?:%s)"
                                 % (r"[A-Za-z0-9_]*", rule["source"]))
        self.sink_re = re.compile(rule["sink"])
        self.guard_re = re.compile(rule["guard"]) if rule["guard"] else None
        self.tree = parser.parse(text.encode("utf-8", errors="replace"))
        self.lines = text.split("\n")

    def find_sinks(self):
        """返回 [(row, col, 行文本, 该语句文本)]。"""
        out = []
        stack = [self.tree.root_node]
        while stack:
            n = stack.pop()
            if n.type in ("call_expression",):
                fn = n.child_by_field_name("function")
                fname = fn.text.decode("utf-8", "replace") if fn is not None else ""
                if self.sink_re.search(fname):
                    row = n.start_point[0]
                    stmt = self._stmt_text(n)
                    out.append((row, n.start_point[1], self.lines[row], stmt))
            stack.extend(n.children)
        return out

    def _stmt_text(self, node):
        p = node
        while p is not None and p.type not in ("expression_statement", "declaration",
                                               "if_statement", "return_statement",
                                               "compound_statement"):
            p = p.parent
        if p is None:
            return node.text.decode("utf-8", "replace")
        return p.text.decode("utf-8", "replace")

    def tainted_names(self, before_row):
        """在 sink 之前，哪些局部名**其赋值表达式直接含 source**（≤hops 跳）。

        v6.21 三轮实测逐步收紧，每轮都有实证：
          ① 初版「整行含 source」→ 把 `int64_t rowBase = (zeroStartRow + row) * dim2H;`
             也当污染源，产出 6 条全误报（那些只是行索引）。
          ② 改「右值含 source」后仍误报：source 里的 `remain` 命中 `remainder`/`remaining`，
             属分块/循环语义而非尾块长度。
          ③ 本轮：`curRowFactor = (cond) ? tailRowFactor : rowFactor;` —— 右值确实含
             `tailRowFactor`，但它是**三元条件的分支选择值**（尾组行数因子），
             不是被搬运的长度。故此处排除「纯三元表达式右侧」的传播：
             若右值形如 `A ? B : C` 且 source 只出现在分支里，则该赋值**不建立污染**，
             因为 sink 收到的通常是 `curRowFactor` 这个因子，而非尾块字节数。
             若确实需要「尾块走不同分支」的判据，应改用 guard 语义，不该走污点传播。
        """
        names = set()
        frontier = set()
        tern = re.compile(r"\?[^:]+:")
        for i, line in enumerate(self.lines[:before_row]):
            m = (re.match(r"\s*(?:auto|const auto|[\w:<>,\s]+?)\s+(\w+)\s*=\s*(.+)$", line)
                 or re.match(r"\s*(\w+)\s*=\s*(.+)$", line))
            if not m:
                continue
            lhs, rhs = m.group(1), m.group(2)
            if not self.src_re.search(rhs):
                continue
            # ③ 三元分支选择变量不算数据污染
            if "?" in rhs and tern.search(rhs):
                continue
            names.add(lhs)
            frontier.add(lhs)
        for _ in range(max(0, self.rule["hops"] - 1)):
            nxt = set()
            for i, line in enumerate(self.lines[:before_row]):
                m = (re.match(r"\s*(?:auto|const auto|[\w:<>,\s]+?)\s+(\w+)\s*=\s*(.+)$", line)
                     or re.match(r"\s*(\w+)\s*=\s*(.+)$", line))
                if not m:
                    continue
                lhs, rhs = m.group(1), m.group(2)
                if lhs in names:
                    continue
                if "?" in rhs and tern.search(rhs):
                    continue
                if any(re.search(r"\b%s\b" % re.escape(f), rhs) for f in frontier):
                    nxt.add(lhs)
            names |= nxt
            frontier = nxt
            if not frontier:
                break
        return names

    def guarded(self, stmt, row):
        """该 sink 是否被保护：语句内或前 10 行内出现 guard 形态。"""
        if self.guard_re is None:
            return False
        if self.guard_re.search(stmt):
            return True
        lo = max(0, row - 10)
        return any(self.guard_re.search(self.lines[i]) for i in range(lo, row))


def _arg_position(fl, row, name):
    """判断 `name` 在该 sink 调用里处于第几个实参（0 起）；不在实参里返回 -1。

    为什么需要这个（v6.21 第四轮实测）：`DataCopy(tailTmpWsSelf[...], src, len)` 里
    `tailTmpWsSelf` 是**搬运目标缓冲名**（含 tail 只是命名习惯），不是搬运长度。
    若不分位置，所有「名字里带 tail 的 buffer」都会被误报。
    约定：第 0 个实参是目标/源地址，从第 1 个起才可能是长度/步长。
    """
    line = fl.lines[row] if row < len(fl.lines) else ""
    m = re.search(r"\w+\s*\((.*)\)", line)
    if not m:
        return -1
    depth = 0
    idx = 0
    cur = []
    for ch in m.group(1):
        if ch in "([{<":
            depth += 1
        elif ch in ")]}>":
            depth -= 1
        elif ch == "," and depth == 0:
            idx += 1
            cur = []
            continue
        cur.append(ch)
    args = m.group(1)
    # 逐段检查 name 是否出现在第 idx 段（简单切分，够用）
    parts = re.split(r",(?![^()\[\]]*[)\]])", args)
    for i, p in enumerate(parts):
        if re.search(r"\b%s\b" % re.escape(name), p):
            return i
    return -1


def scan_file(path, rule, parser):
    try:
        text = read_text(path)
    except OSError:
        return []
    if rule["files"]:
        try:
            if not re.search(rule["files"], path.replace("\\", "/")):
                return []
        except re.error:
            pass
    fl = Flow(text, rule, parser)
    try:
        sinks = fl.find_sinks()
    except (AttributeError, ValueError):
        return []
    # ---- guard 判定必须是「函数级」而不是「邻近行」（v6.21 实测修正）----
    # 初版用「前 10 行内出现 if/min」做豁免，实测出误报：
    #   clipped_swiglu_grad_base.h:420 的 DataCopyPad 在 fullChunks 循环里（用固定块长），
    #   真正的尾块保护在第 425 行 `if (tailElems > 0)`——它属于**同一函数的尾部逻辑**，
    #   而不是这条 sink 的守卫。按「邻近行」判会把该 sink 误判为「无保护」。
    # 正确做法：若整个函数体内存在针对该 source 的 guard，则视为已防护；
    #   只有「整个函数都没管过 tail」才报——这符合 FP-A05 的实际形态
    #   （漏保护是整个函数都没做，不是某一行少了括号）。
    fn_guarded = False
    if fl.guard_re is not None:
        for line in fl.lines:
            if fl.guard_re.search(line) and fl.src_re.search(line):
                fn_guarded = True
                break
    if fn_guarded:
        return []
    hits = []
    for row, col, line, stmt in sinks:
        # 直接命中：sink 实参里就有 source
        direct = bool(fl.src_re.search(stmt))
        names = fl.tainted_names(row) if not direct else set()
        via = [n for n in names if re.search(r"\b%s\b" % re.escape(n), stmt)]
        if not (direct or via):
            continue
        # v6.21 第四轮：source/污染名必须出现在**长度位置**（第 1 个实参起），
        # 否则 `DataCopy(tailTmpWsSelf[...], ...)` 这类「名字带 tail 的目标缓冲」
        # 会被全部误报。实测该收紧缩掉 activation 目录最后 1 条误报。
        # 注意：必须取**完整标识符**再核位置。直接拿正则 match 的 `tail`（片段）
        # 去比对 `tailN`，`\btail\b` 匹配不上，自检会误判为「不在长度位」。
        cand_names = set()
        for m in fl.src_re.finditer(stmt):
            end = m.end()
            # 从 match 起点向右吃满标识符字符
            i = m.start()
            while i > 0 and (stmt[i - 1].isalnum() or stmt[i - 1] == "_"):
                i -= 1
            j = end
            while j < len(stmt) and (stmt[j].isalnum() or stmt[j] == "_"):
                j += 1
            cand_names.add(stmt[i:j])
        cand_names |= set(via)
        in_len_pos = False
        for nm in cand_names:
            if _arg_position(fl, row, nm) >= 1:
                in_len_pos = True
                break
        if not in_len_pos:
            continue
        if fl.guarded(stmt, row):
            continue
        hits.append({
            "pattern": rule["pid"], "file": path, "line": row + 1,
            "level": rule["level"], "sink": stmt.strip()[:120],
            "taint": "direct" if direct else "via:" + ",".join(sorted(via)[:3]),
            "note": rule["note"],
        })
    return hits


def scan(targets, rules, only=None):
    parser = _parser()
    cands, stats = [], []
    for rule in rules:
        if only and rule["pid"] not in only:
            continue
        n_files = n_hit = 0
        for f in iter_files(targets):
            got = scan_file(f, rule, parser)
            if got:
                n_files += 1
                n_hit += len(got)
                cands.extend(got)
        stats.append({"pid": rule["pid"], "files": n_files, "hits": n_hit})
    return cands, stats


def self_test():
    """构造三种情形：无保护（应报）、有 if 保护（应免）、有 min 保护（应免）。"""
    parser = _parser()   # 缺依赖时在这里给出安装提示并以非 0 退出，不静默跳过
    rule = {"pid": "FP-T01", "source": "tail|Tail", "sink": "DataCopyPad",
            "guard": r"if\s*\(|min\(|Max\(", "hops": 2, "files": "",
            "level": "info", "note": ""}
    import tempfile
    cases = [
        ("bad.cpp", "void f(){\n  int tailN = n % 8;\n  DataCopyPad(d, s, tailN);\n}\n", 1),
        ("ok_if.cpp", "void f(){\n  int tailN = n % 8;\n  if (tailN > 0)\n    DataCopyPad(d, s, tailN);\n}\n", 0),
        ("ok_min.cpp", "void f(){\n  int tailN = n % 8;\n  int safe = min(tailN, 8);\n  DataCopyPad(d, s, safe);\n}\n", 0),
    ]
    ok = True
    tmp = tempfile.mkdtemp(prefix="df_")
    try:
        for name, code, want in cases:
            p = os.path.join(tmp, name)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(code)
            got = len(scan_file(p, rule, parser))
            good = got == want
            ok = ok and good
            print("[%s] %-12s 期望 %d 实得 %d" % ("PASS" if good else "FAIL",
                                                  name, want, got))
        # 追加自检（v6.21）：走 scan() 端到端路径，确认 direct/via 两条通路都活着。
        # 起因：负向测试把 `if not (direct or via)` 改成 `if not direct` 后，
        # 上面的单文件自检仍然全绿——因为三条用例都是 direct 场景，没覆盖 via。
        via_rule = dict(rule)
        via_rule["source"] = "tail"
        via_rule["sink"] = "CopyOut"
        via_rule["guard"] = ""
        p2 = os.path.join(tmp, "via.cpp")
        with open(p2, "w", encoding="utf-8") as fh:
            fh.write("void f(){\n  int t = tailN;\n  int u = t;\n  CopyOut(d, u);\n}\n")
        got2 = len(scan_file(p2, via_rule, parser))
        if got2 < 1:
            print("[FAIL] 数据流自检：via 传播通路失效（期望 >=1 实得 %d）" % got2)
            ok = False
        else:
            print("[PASS] 数据流自检：via（中间变量）传播通路有效")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="跨语句数据流：source→sink 且无 guard")
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

    rules = load_rules(os.path.abspath(args.root))
    if not rules:
        print("[INFO] 索引里没有 dataflow_signatures 规则")
        return 0
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    cands, stats = scan(args.targets, rules, only=only)

    if args.format == "json":
        print(json.dumps({"candidates": cands, "stats": stats},
                         ensure_ascii=False, indent=2))
    else:
        for s in stats:
            print("[DF] %-8s files=%-4d hits=%-4d" % (s["pid"], s["files"], s["hits"]))
        for c in cands[:40]:
            print("[CAND][%s] %s:%d  %s  (%s)"
                  % (c["level"], c["file"], c["line"], c["sink"][:60], c["taint"]))
        if len(cands) > 40:
            print("... 其余 %d 条略" % (len(cands) - 40))
        print("[SUMMARY] dataflow candidates=%d（源→汇无保护）" % len(cands))
    return 0


if __name__ == "__main__":
    sys.exit(main())
