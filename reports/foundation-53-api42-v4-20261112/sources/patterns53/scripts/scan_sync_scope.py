#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步原语作用域审计器（scan_sync_scope.py，v1.0，v6.15）

定位
----
`scan_sync.py` 做的是**配对完整性**审计（扫孤儿原语：无配对的 set / 无来源的 wait /
只申请不释放的 event），对应 FP-G02 子型①~⑤。但 FP-G02 在 v6.15 新增的**子型⑥**
问的是另一个维度：**「这对同步定义了哪条路径归它管」——是作用域问题，不是计数问题。**

两者关系（**互补且不可互相替代，必须分别跑**）：

| 检查 | 问的问题 | 放行条件 | 典型漏检 |
|---|---|---|---|
| `scan_sync.py`（配对） | set 与 wait 次数/ID 是否配平 | 四件套齐全、ID 互异、方向正确 | 四件套整体被某个 `if` 分支独占 |
| 本脚本（作用域） | 这条同步边的作用域覆盖了谁 | 作用域外的同 buffer 访问有独立同步 | —— |

因此**配对检查全部通过 ≠ 作用域正确**。#5836 即为典型：`eventIdPseDropVToMte2B` 的
`AllocEventID` / `SetFlag` / `WaitFlag` / `ReleaseEventID` 各一次、ID 相同、完全配平，
但因四行全部包在 `!this->pseInfo.pseEndogenous` 内，内源 PSE 路径（走 `PseSlopeCopyIn`）
**整体丢失**这条 V→MTE2 边。任何纯计数的检查器都会放行。

判别三步（与卡片 `patterns/FP-G/FP-G02.md` 子型⑥ 专项判据逐字对应）
--------------------------------------------------------------------
1. 取同步四件套，求其**共同最内层块**（能同时包住这四行的最小作用域）；
2. 若该块是 `if` / `else` 分支，则这条同步边**只覆盖该分支**；
3. 检查**该作用域之外**是否还有对**同一 buffer / 同一地址**的访问——有，则候选成立。

用法
----
python3 scripts/scan_sync_scope.py <文件或目录> [...] [--ext .cpp,.h] [--format text|json]
                                    [--out <json>] [--exclude /tests/] [--depth 1]
python3 scripts/scan_sync_scope.py --self-test

退出码
------
0 = 无候选（`--self-test` 下表示冒烟全部通过）
1 = 有候选（供 CI 判定「是否有人工作业清单」）
2 = 参数/环境错误
3 = `--self-test` 失败（任一冒烟项未报出或有误报）

能力边界（必读）
----------------
- **候选 ≠ 缺陷**：本工具只做**块结构 + buffer 名共现**的启发式提示，不完整解析 C++ AST。
  它给出的是「这条同步边可能管不到某个访问点」，须人工按 skill 第 7 节做正负证据判定；
- **⚠️ 不做跨函数分析，这是最主要的误报来源**：工具按**单文件单函数内视**。若「作用域外的
  访问」实际由**调用方**在更外层加了等价同步，工具看不到，会报假阳。实证案例：`grid_sample`
  的 `grid_sampler_2d_bicubic.h:880` 被判「`calCElems==1` 分支缺 `S_MTE3`」，但其调用方
  `interp1dCompute`（同文件 `:937-939`）在进入该分支所属函数前**已做完整 V→MTE3 同步**，
  分支内的 `S_MTE3` 只是冗余保险；真机 racecheck 9 组配置 18 次运行 **0 hazard**，确认为误报。
  **判定要求**：报出的每一条，都必须回到调用链上游确认「是否已有等价同步」；
- **同 buffer 判定按标识符**（如 `stage1PingBuf` / `xLocal` / `intermGm`），不做地址/别名分析——
  经 `ReinterpretCast` / 指针别名出的同址访问会漏；这属工具已知边界，不因此下调人工审查强度；
- **分支识别只认 `if` / `else` / `for` / `while` / `switch` 的规范花括号体**，`?:` 三元与
  `&&` 短路造成的隐式分支**识别不到**（这类须人工核）；
- **未命中 ≠ 无缺陷**：作用域外确实无同 buffer 访问、或该访问由另一条方向正确的同步边保护，
  才算反证排除。仅凭「另一分支看起来不会同时触发」**不构成反证**（走哪条路径由 tiling /
  属性决定，静态不可排除）——这一条与 skill 第 7 节的判定纪律一致；
- 本脚本是 **`scan_sync.py` 的补充**，不替代 racecheck（mssanitizer）零告警门禁。
  实测建议：**先跑本脚本收窄范围，再对候选逐条跑 racecheck**——单靠本脚本会把冗余同步
  报成缺失同步。
"""

import argparse
import json
import os
import re
import sys

SKIP_DIRS = {".git", "build", "output", "node_modules", "third_party", "thirdparty",
             "__pycache__", ".venv", "venv", "dist", "docs", ".idea", ".vscode"}
SYNC_EXTS = (".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".hh", ".asc", ".inc")

# ---- 四件套 ----
SET_RE = re.compile(r"SetFlag\s*<\s*(?:AscendC::)?HardEvent::(\w+)\s*>\s*\(")
WAIT_RE = re.compile(r"WaitFlag\s*<\s*(?:AscendC::)?HardEvent::(\w+)\s*>\s*\(")
ALLOC_RE = re.compile(r"AllocEventID\s*<\s*(?:AscendC::)?HardEvent::(\w+)\s*>")
RELEASE_RE = re.compile(r"ReleaseEventID\s*<\s*(?:AscendC::)?HardEvent::(\w+)\s*>")

# ---- 分支/作用域 ----
BRANCH_KW_RE = re.compile(r"\b(if|else|for|while|switch)\b")
IF_KW_RE = re.compile(r"\b(if|switch)\b")

# ---- buffer 访问提取 ----
# 目标：从一行代码里抽出「被访问的 buffer / tensor 标识符」，用于判「作用域外是否有同 buffer 访问」。
# 覆盖三类常见命名：
#   1) AscendC 队列/张量：xLocal / stage1PingBuf / outValueUb / intermGm / depthGM ...
#   2) UB/L1/GM 后缀：xxxUb / xxxGm / xxxQueue / xxxBuf / xxxTensor
#   3) 常见显式后缀：coefficientW / radioTensor ...
IDENT_RE = re.compile(r"\b([A-Za-z_]\w*)\b")
# buffer / tensor 命名模式。三类并列（都用 FULLMATCH，避免 part-match 误伤）：
#   ① 小写起头 + 后缀结尾（Local/Global/Tensor/Queue/Buf/Buffer/Ub/Gm）
#        —— xLocal / srcGlobal / outTensor / stage1Queue / weightUb / depthGM
#   ② 前缀 + 驼峰段（前缀后接「大写起头且至少含一个小写字母」的段）
#        —— outValueUb / inputXWFpLocalTmp / radioTensor_h / gradXGm
#   ③ 纯弱条件兜底：以 Tensor/Buf 结尾且含 ≥2 个驼峰段
#
# **刻意排除的形态**：`inputC_` / `outputW` / `batchSize_` / `channelLoop_` 这类
# 「前缀 + 单个大写字母 + 可选下划线」的**尺寸/计数标量**——它们不含小写驼峰段，
# ② 的 `[A-Z][a-z]` 要求会把它们正确排除（实测 inputC_/outputW/inputH 曾被误判）。
BUFFER_NAME_RE = re.compile(
    r"(?:"
    r"[a-z][A-Za-z0-9_]*?(?:Local|Global|Tensor|Queue|Buf|Buffer|Ub|Gm|GM|UB)$"
    r"|(?:x|y|z|in|out|src|dst|grad|input|output|interm|inter)[A-Z][a-z][A-Za-z0-9_]*"
    r"|(?:x|y|z|in|out|src|dst|grad|input|output|interm|inter)[A-Z][A-Za-z]+(?:Local|Global|Tensor|Queue|Buf|Ub|Gm)[A-Za-z0-9_]*"
    r"|(?:x|y|z|src|dst|grad)[A-Z]"          # gradY / xGm / yOut —— 短前缀+单大写结尾
    r")"
)
BUFFER_NAME_FULL_RE = re.compile(r"^(?:%s)$" % BUFFER_NAME_RE.pattern)
# 常见非 buffer 的假阳性词（变量名长得像但实为尺寸/计数/参数）
NON_BUFFER_WHITELIST = {
    "GetSize", "GetValue", "SetValue", "GetPhyAddr", "ReinterpretCast", "GetTPipePtr",
    "GetBlockIdx", "GetSubBlockIdx", "AllocTensor", "FreeTensor", "DeQue", "EnQue",
    "DataCopy", "DataCopyPad", "SetGlobalBuffer", "InitBuffer", "SetAtomicAdd", "SetAtomicNone",
}

CALL_LIKE_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")

# 纯声明行：`uint64_t dstList[16];` / `LocalTensor<T> srcList[16];` / `int32_t base[2], idx[16];`
# 这类行只是「声明一个装 tensor 句柄的局部数组」，本身不构成对 buffer 的访问，
# 若计入会把「数组声明」误当成「作用域外同 buffer 访问」（实测确实产生过此类误报）。
# 判据：整行只由 类型/限定符/标识符/下标/逗号/分号 组成，且不含任何函数调用 `(`。
PURE_DECL_RE = re.compile(
    r"^\s*(?:const\s+|static\s+|constexpr\s+|__aicore__\s+|inline\s+)*"
    r"(?:LocalTensor|GlobalTensor|AscendC::(?:Local|Global)Tensor)?\s*"
    r"[A-Za-z_][\w:]*\s*(?:<[^;()]*?>)?\s*[\*&]*\s*"
    r"[A-Za-z_]\w*\s*(?:\[\s*[\w\s\*\+\-]*\s*\])?\s*"
    r"(?:,\s*[A-Za-z_]\w*\s*(?:\[\s*[\w\s\*\+\-]*\s*\])?\s*)*;"
)


def is_pure_declaration(code):
    """判断一行是否为「纯声明」（不含函数调用、不含赋值表达式）。"""
    s = code.strip()
    if not s.endswith(";"):
        return False
    if "(" in s or "=" in s:
        return False          # 有调用或赋值 → 不是纯声明
    return bool(PURE_DECL_RE.match(s))


def read_text(p):
    with open(p, encoding="utf-8-sig", errors="replace") as f:
        return f.read()


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


def strip_line_comment(line):
    """粗略去掉 // 之后的内容。"""
    i = line.find("//")
    return line if i < 0 else line[:i]


def mask_strings(text):
    """把字符串/字符字面量内容替换成空白，避免里面的花括号和标识符干扰结构分析。

    保持长度与行数不变，这样行号、列号仍然对得上。
    """
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            i += 1
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    out.append(" ")
                    out.append(" ")
                    i += 2
                    continue
                out.append(c if c == quote else ("\n" if c == "\n" else " "))
                i += 1
                if c == quote:
                    break
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def build_block_index(text):
    """构建每个 `{` 对应的块信息，并给出每行所属的最内层块 id。

    返回
    ----
    blocks : dict[bid] -> {"open_line", "close_line", "parent", "kind", "header"}
        kind ∈ {"func", "if", "else", "for", "while", "switch", "other"}
        header 为该块开括号所在行（或前一行）的代码，用于识别分支条件
    line_owner : dict[line_no] -> bid（该行“行首时刻”的最内层块）
    """
    blocks = {}
    line_owner = {}
    stack = []          # list of bid
    pending = None      # 待绑定的块类型（由上一行/本行的关键字决定）
    pending_header = ""
    bid_seq = 0

    masked = mask_strings(text)
    lines = masked.splitlines()

    for ln, raw in enumerate(lines, 1):
        code = strip_line_comment(raw)
        # 行首时刻的最内层块
        line_owner[ln] = stack[-1] if stack else None

        # 先看本行是否引入分支关键字（可能在同一行既开块又闭块）
        m_kw = BRANCH_KW_RE.search(code)
        if m_kw:
            kw = m_kw.group(1)
            pending = kw
            pending_header = code.strip()

        for ch in code:
            if ch == "{":
                bid = "B%d" % bid_seq
                bid_seq += 1
                parent = stack[-1] if stack else None
                kind = pending if pending else "other"
                blocks[bid] = {
                    "open_line": ln,
                    "close_line": None,
                    "parent": parent,
                    "kind": kind,
                    "header": pending_header[:200],
                }
                stack.append(bid)
                pending = None
                pending_header = ""
            elif ch == "}":
                if stack:
                    bid = stack.pop()
                    blocks[bid]["close_line"] = ln

    return blocks, line_owner


def inner_most_common_block(lines_no, line_owner, blocks):
    """求一组行号的**共同最内层块**：即所有行都属于的、最深的那一层块。

    做法：取首行所属块，沿 parent 链上溯，找到第一个能覆盖所有行号的块。
    """
    if not lines_no:
        return None
    lo, hi = min(lines_no), max(lines_no)
    bid = line_owner.get(lo)
    while bid is not None:
        b = blocks.get(bid)
        if b and b["close_line"] is not None and b["open_line"] <= lo and b["close_line"] >= hi:
            return bid
        bid = blocks.get(bid, {}).get("parent")
    return None


ALLOC_STMT_RE = re.compile(
    r"^\s*(?:LocalTensor|GlobalTensor)\s*(?:<[^>]*>)?\s+([A-Za-z_]\w*)\s*=\s*"
    r"[A-Za-z_]\w*\s*\.\s*AllocTensor\s*<", re.M)


def strip_alloc_bindings(code):
    """剔除 `LocalTensor<T> x = queue.AllocTensor<T>();` 这类「新绑定」语句里的左值名。

    这不是「复用同一 buffer」而是「从队列取一个新 tensor 并命名」，若把它算作
    对同名 buffer 的访问，会把「每次循环都重新取 tensor」误报成「作用域外同址访问」。
    只剔除**左值变量名**，不剔除队列名（队列本身确实是共享资源）。
    """
    m = ALLOC_STMT_RE.match(code)
    if m:
        name = m.group(1)
        # 把左值名从行内抹掉（保留等号右侧，队列名仍在，仍可被识别）
        return re.sub(r"\b%s\b" % re.escape(name), " ", code, count=1)
    return code


def extract_buffers(code):
    """从一行代码里抽出疑似 buffer / tensor 标识符。

    纯声明行（`uint64_t dstList[16];`）不产出 buffer——声明不等于访问；
    `AllocTensor` 新绑定只剔除左值名——取新 tensor 不等于复用旧 buffer。
    """
    if is_pure_declaration(code):
        return set()
    code = strip_alloc_bindings(code)
    found = set()
    # 先剔掉「函数调用名」位置（xxx( 形式），它们是动作不是 buffer
    call_names = set(m.group(1) for m in CALL_LIKE_RE.finditer(code))
    for m in IDENT_RE.finditer(code):
        name = m.group(1)
        if name in NON_BUFFER_WHITELIST:
            continue
        if name in call_names:
            continue          # 调用名（DataCopy / Muls / InitOutput ...）
        if len(name) < 3:
            continue
        if BUFFER_NAME_FULL_RE.match(name):
            found.add(name)
    return found


def audit_file(path, depth):
    """对单文件做子型⑥ 作用域审计，返回候选列表。"""
    try:
        text = read_text(path)
    except OSError:
        return []

    blocks, line_owner = build_block_index(text)
    lines = text.splitlines()

    # ---- 收集四件套，按事件域聚合 ----
    prims = []   # (line, kind, domain, raw)
    for i, raw in enumerate(lines, 1):
        code = strip_line_comment(raw)
        if SET_RE.search(code):
            prims.append((i, "set", SET_RE.search(code).group(1), raw.strip()))
        if WAIT_RE.search(code):
            prims.append((i, "wait", WAIT_RE.search(code).group(1), raw.strip()))
        if ALLOC_RE.search(code):
            prims.append((i, "alloc", ALLOC_RE.search(code).group(1), raw.strip()))
        if RELEASE_RE.search(code):
            prims.append((i, "release", RELEASE_RE.search(code).group(1), raw.strip()))

    if not prims:
        return []

    # 按事件域分组；同一域的四件套若在同一「函数级」块内，视为同一条同步边
    by_dom = {}
    for ln, kind, dom, raw in prims:
        by_dom.setdefault(dom, []).append((ln, kind, raw))

    cands = []
    for dom, items in sorted(by_dom.items()):
        kinds = {k for _, k, _ in items}
        # 只处理「四件套至少含 set + wait」的完整同步边；单边（只有 set 或只有 wait）
        # 属配对检查（scan_sync.py 子型①）的地盘
        if not {"set", "wait"} <= kinds:
            continue
        lns = [ln for ln, _, _ in items]
        bid = inner_most_common_block(lns, line_owner, blocks)
        if bid is None:
            continue
        blk = blocks[bid]

        # 步骤②：共同最内层块是否为分支体？
        if blk["kind"] not in ("if", "else", "for", "while", "switch"):
            continue

        # 取「分支体」的父块作为作用域边界：分支外 = 父块范围内、且不在本分支块内
        scope_lo = blk["open_line"]
        scope_hi = blk["close_line"]
        if scope_hi is None:
            continue

        # 本分支内访问到的 buffer 集合（作为「这条同步边保护的 buffer」候选）
        buf_in_branch = set()
        for ln in range(scope_lo, min(scope_hi, len(lines)) + 1):
            buf_in_branch |= extract_buffers(strip_line_comment(lines[ln - 1]))
        if not buf_in_branch:
            continue

        # 步骤③：作用域外是否有同 buffer 访问？
        # 搜索范围 = 同一函数体（父块的父块）内、且落在 [scope_lo, scope_hi] 之外的行
        fn_bid = blk["parent"]
        # 沿 parent 上溯到「函数级」块（kind == other 且 open 处无分支关键字）
        guard = 0
        while fn_bid is not None and blocks[fn_bid]["kind"] in ("if", "else", "for", "while", "switch"):
            fn_bid = blocks[fn_bid]["parent"]
            guard += 1
            if guard > 64:
                break
        if fn_bid is None:
            fn_lo, fn_hi = 1, len(lines)
        else:
            fn_lo = blocks[fn_bid]["open_line"]
            fn_hi = blocks[fn_bid]["close_line"] or len(lines)

        outside_hits = []
        for ln in range(fn_lo, min(fn_hi, len(lines)) + 1):
            if scope_lo <= ln <= scope_hi:
                continue
            code = strip_line_comment(lines[ln - 1])
            if not code.strip():
                continue
            hit = buf_in_branch & extract_buffers(code)
            if hit:
                outside_hits.append((ln, sorted(hit), lines[ln - 1].strip()[:160]))

        if not outside_hits:
            continue

        # 只在 `--depth` 允许的规模内报（默认 1：只报最近的作用域外访问）
        for ln, hit, snippet in outside_hits[:max(1, depth)]:
            cands.append({
                "sub": "⑥",
                "file": path,
                "line": ln,
                "scope_line": scope_lo,
                "domain": dom,
                "branch_kind": blk["kind"],
                "buffers": hit,
                "note": ("同步四件套（HardEvent::%s）的共同最内层块是 %s 分支体（起于第 %d 行），"
                         "该同步边只覆盖此分支；但第 %d 行在作用域外访问了同一 buffer %s —— "
                         "另一条路径复用该 buffer 却无等价同步（配对检查会全部放行）"
                         % (dom, blk["kind"], scope_lo, ln, "、".join(hit))),
                "code": snippet,
            })

    return cands


def scan(files, depth=1):
    cands, n_anchors = [], 0
    for f in files:
        got = audit_file(f, depth)
        cands.extend(got)
    return cands, n_anchors


def self_test():
    """端到端冒烟：脏样例必须报出，干净样例必须零误报。"""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="scan_sync_scope_")
    bad = os.path.join(tmp, "a_scope_bad.h")
    clean = os.path.join(tmp, "b_scope_clean.h")
    nondom = os.path.join(tmp, "c_scope_outer.h")

    # ❌ #5836 形态：四件套齐全、完全配平，但整体被 !pseEndogenous 分支独占，
    #    内源路径（else 侧）复用同一 stage1PingBuf 却无等价同步
    with open(bad, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            "void ProcessVec1()\n"
            "{\n"
            "  if (!this->pseInfo.pseEndogenous) {\n"
            "    int32_t e = AllocEventID<HardEvent::V_MTE2>();\n"
            "    SetFlag<HardEvent::V_MTE2>(e);\n"
            "    DataCopy(stage1PingBuf, srcGm, len);\n"
            "    WaitFlag<HardEvent::V_MTE2>(e);\n"
            "    ReleaseEventID<HardEvent::V_MTE2>(e);\n"
            "  } else {\n"
            "    PseSlopeCopyIn(stage1PingBuf, slopeGm, len);\n"
            "  }\n"
            "}\n")

    # ✅ 干净形态：同步边在分支外，两条路径共用同一条边
    with open(clean, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            "void ProcessVec1()\n"
            "{\n"
            "  int32_t e = AllocEventID<HardEvent::V_MTE2>();\n"
            "  if (!this->pseInfo.pseEndogenous) {\n"
            "    SetFlag<HardEvent::V_MTE2>(e);\n"
            "    DataCopy(stage1PingBuf, srcGm, len);\n"
            "    WaitFlag<HardEvent::V_MTE2>(e);\n"
            "  } else {\n"
            "    PseSlopeCopyIn(stage1PingBuf, slopeGm, len);\n"
            "  }\n"
            "  ReleaseEventID<HardEvent::V_MTE2>(e);\n"
            "}\n")

    # ✅ 作用域外无同 buffer 访问 —— 不成立，不该报
    with open(nondom, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            "void f()\n"
            "{\n"
            "  if (cond) {\n"
            "    SetFlag<HardEvent::V_MTE3>(e);\n"
            "    DataCopy(outValueUb, innerUb, len);\n"
            "    WaitFlag<HardEvent::V_MTE3>(e);\n"
            "  }\n"
            "  DataCopy(otherGm, otherLocal, len);\n"
            "}\n")

    cands, _ = scan([bad, clean, nondom])
    ok = True
    bad_hits = [c for c in cands if c["file"] == bad]
    if not bad_hits:
        print("[FAIL] self-test：分支独占同步四件套（#5836 形态）未报出")
        ok = False
    elif not any("stage1PingBuf" in c["buffers"] for c in bad_hits):
        print("[FAIL] self-test：报出的候选未识别到 stage1PingBuf")
        ok = False
    clean_hits = [c for c in cands if c["file"] == clean]
    if clean_hits:
        print("[FAIL] self-test：同步边在分支外的干净文件被误报 %d 条" % len(clean_hits))
        ok = False
    nondom_hits = [c for c in cands if c["file"] == nondom]
    if nondom_hits:
        print("[FAIL] self-test：作用域外无同 buffer 访问的文件被误报 %d 条" % len(nondom_hits))
        ok = False
    if not ok:
        return 3
    print("[PASS] self-test：作用域审计端到端冒烟通过（分支独占必报、分支外同步与无同 buffer 访问零误报）")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="同步原语作用域审计器（FP-G02 子型⑥，与 scan_sync.py 的配对审计互补，v1.0）")
    ap.add_argument("targets", nargs="*", help="待扫文件或目录")
    ap.add_argument("--ext", default=",".join(SYNC_EXTS), help="扩展名白名单，逗号分隔")
    ap.add_argument("--format", default="text", choices=("text", "json"))
    ap.add_argument("--out", default="", help="JSON 输出文件（--format json 时可选）")
    ap.add_argument("--exclude", default="", help="路径片段黑名单，逗号分隔（如 /tests/,/build/）")
    ap.add_argument("--depth", type=int, default=1,
                    help="每处作用域外同 buffer 访问报几条（默认 1，按行号升序取前 N）")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.targets:
        ap.print_help()
        return 2

    exts = tuple(x.strip().lower() for x in args.ext.split(",") if x.strip())
    files = list(iter_files(args.targets, exts))
    ex = [x.strip().replace("\\", "/") for x in args.exclude.split(",") if x.strip()]
    if ex:
        files = [f for f in files if not any(e in f.replace("\\", "/") for e in ex)]

    cands, _ = scan(files, depth=args.depth)

    if args.format == "json":
        result = {"scanned_files": len(files), "candidates": len(cands), "items": cands}
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="\n") as f:
                f.write(text + "\n")
            print("[OK] %d 条候选 → %s" % (len(cands), args.out))
        else:
            print(text)
    else:
        print("== FP-G02 子型⑥ 作用域审计（同步四件套是否被分支独占）==")
        for c in cands:
            loc = "%s:%d" % (c["file"], c["line"]) if c["line"] else c["file"]
            print("[SUB⑥] %s  %s" % (loc, c["note"]))
            if c.get("code"):
                print("         %s" % c["code"])
        print("[SUMMARY] files=%d candidates=%d（子型⑥）" % (len(files), len(cands)))
    print("[NOTE] 候选 ≠ 缺陷：本工具只做块结构 + buffer 名共现的启发式提示，不做 AST/别名分析；"
          "同 buffer 判定按标识符，三元与短路隐式分支识别不到；"
          "「另一分支看起来不会同时触发」不构成反证，须给出作用域外无访问或另一条同步边保护的 文件:行号 证据；"
          "未命中 ≠ 无缺陷，最终以 racecheck 零告警为准。")
    return 1 if cands else 0


if __name__ == "__main__":
    sys.exit(main())
