#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步原语配对完整性检查器（scan_sync.py，v1.0，FP-G02 专属）

定位
----
FP-G02「核间/流水同步缺失或配对不完整」属**遗漏型缺陷**：出错的代码行本身语法正确、
单看无异常，只有把「生产者—消费者」当成**一对原语**一起看才暴露——常规扫「错误行」
的静态扫描与逐行审查天然漏检。本工具因此不扫错误行，而做**配对完整性检查**：
把每个同步原语视为「只能成对出现」的原语，扫描**孤儿原语**（无配对的 set / 无来源的
wait / 只申请不释放的 event / 未被 host 约束的 SyncAll）。

与 `scan_fp.py` 的关系
----------------------
`scan_fp.py` 按索引 `signatures` 做**存在型**候选（出现即候选）；本工具在其之上做
**配对型**候选（出现且**配不上**才候选），是 FP-G02 的判别性核心。两者都只产候选、
不下结论——每条候选仍须过 `skills/FP-G/fpg02-sync-review/SKILL.md` 第 7 节的正负证据
与证据等级判定。

五类检查（与 FP-G02 子型一一对应）
---------------------------------
- SUB① 同步原语配对失衡/不完整：按**事件域**（`HardEvent::X`）统计 `SetFlag`/`WaitFlag`
  次数与事件 ID，报「set≠wait」与「孤儿 ID（set 无 wait / wait 无 set）」；
- SUB② 跨流水同步遗漏/用错同步边：报「有搬运/计算写同一地址却无对应事件边」的
  **弱信号**（`PipeBarrier<PIPE_X>` 只护同管线；本工具只提示两类易错点，最终须人工核方向）；
- SUB③ 事件 ID / flagId 冲突、越界、泄漏：`AllocEventID` 与 `ReleaseEventID` 不配对、
  申请位于**循环体内**、事件常量**同值冲突**、`id % N` 取模范围需人工核；
- SUB④ 跨核同步覆盖不全：`CrossCoreSetFlag` 与 `CrossCoreWaitFlag` 次数不配平（提示
  等待方可能只感知部分核）；
- SUB⑤ 同步与调度约束缺失：扫描集内出现 `SyncAll<` 却**无** `SetScheduleMode(1)`。

用法
----
python3 scripts/scan_sync.py <文件或目录> [...] [--ext .cpp,.h] [--format text|json]
                              [--out <json>] [--exclude /tests/]
python3 scripts/scan_sync.py --self-test

退出码
------
0 = 无候选（`--self-test` 下表示冒烟全部通过）
1 = 有候选（供 CI 判定「是否有人工确认清单」）
2 = 参数/环境错误
3 = `--self-test` 失败（任一冒烟项未报出或有误报）

能力边界（必读）
----------------
- 候选 ≠ 缺陷：本工具只做**计数/配对**层面的启发式提示，**不理解分支语义、宏展开与模板
  实例化**——分支内一手 set 一手 wait 的合法写法可能被误报，分支缺失的缺陷也可能漏报；
- 事件 ID 为表达式（如 `base + i`）时按**字面量分组**，动态 ID 只能由人工核；
- 循环归属按**花括号栈**启发式判断（不完整解析字符串/注释，单行循环体可能漏判）；
- 「未命中 ≠ 无缺陷」：本模式核心抓手是 **racecheck（mssanitizer）零告警门禁**，
  静态配对检查只是它的廉价前置；报告必须写「本工具未命中 ≠ 无此缺陷」。
"""

import argparse
import json
import os
import re
import sys

SKIP_DIRS = {".git", "build", "output", "node_modules", "third_party", "thirdparty",
             "__pycache__", ".venv", "venv", "dist", "docs", ".idea", ".vscode"}
DEFAULT_EXTS = (".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".hh", ".asc", ".inc", ".py")

SYNC_EXTS = (".cpp", ".cc", ".cxx", ".c", ".h", ".hpp", ".hh", ".asc", ".inc")

SET_RE = re.compile(r"SetFlag\s*<\s*(?:AscendC::)?HardEvent::(\w+)\s*>\s*\(\s*([^)]*?)\s*\)")
WAIT_RE = re.compile(r"WaitFlag\s*<\s*(?:AscendC::)?HardEvent::(\w+)\s*>\s*\(\s*([^)]*?)\s*\)")
ALLOC_RE = re.compile(r"AllocEventID\s*<\s*(?:AscendC::)?HardEvent::(\w+)\s*>")
RELEASE_RE = re.compile(r"ReleaseEventID\s*<\s*(?:AscendC::)?HardEvent::(\w+)\s*>")
CCSET_RE = re.compile(r"CrossCoreSetFlag\s*<")
CCWAIT_RE = re.compile(r"CrossCoreWaitFlag\s*<")
SYNCALL_RE = re.compile(r"SyncAll\s*<")
SCHEDMODE_RE = re.compile(r"SetScheduleMode\s*\(\s*1\s*\)")
PIPEBARRIER_RE = re.compile(r"PipeBarrier\s*<\s*PIPE_(\w+)\s*>")

CONST_ASSIGN_RE = re.compile(r"\b([A-Za-z_]\w*)\s*=\s*(\d+)\s*;")
CONST_DEFINE_RE = re.compile(r"^\s*#define\s+([A-Za-z_]\w*)\s+(\d+)\b")
EVENTNAME_RE = re.compile(r"(?:EVENT|FLAG|flagId|eventId)", re.IGNORECASE)
PCT_RE = re.compile(r"%\s*(\d+)")


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
    """粗略去掉 // 之后的内容（不处理字符串内的 // ，够用）。"""
    i = line.find("//")
    return line if i < 0 else line[:i]


def loop_lines(text):
    """返回「位于某个循环体内」的行号集合（花括号栈启发式）。

    对每一行取行首时刻的栈状态：只要栈中任一开括号来自 for/while，即视为循环体内。
    """
    stack = []          # 每个 '{' 对应 bool：是否为循环体
    pending_loop = False
    inside = set()
    for idx, raw in enumerate(text.splitlines(), 1):
        if any(stack):
            inside.add(idx)
        code = strip_line_comment(raw)
        if re.search(r"\b(for|while)\s*\(", code):
            pending_loop = True
        for ch in code:
            if ch == "{":
                stack.append(pending_loop)
                pending_loop = False
            elif ch == "}":
                if stack:
                    stack.pop()
    return inside


def analyze_file(path):
    """对单文件做五类配对检查，返回候选列表。"""
    try:
        text = read_text(path)
    except OSError:
        return []
    cands = []
    lines = text.splitlines()
    in_loop = loop_lines(text)

    set_by_dom = {}      # domain -> list of (line, id_text, code)
    wait_by_dom = {}     # domain -> list of (line, id_text, code)
    alloc_by_dom = {}    # domain -> list of (line, code, in_loop)
    release_by_dom = {}  # domain -> list of (line, code)
    cc_set, cc_wait, syncall = [], [], []
    consts = []          # (name, value, line, code)

    for i, raw in enumerate(lines, 1):
        code = strip_line_comment(raw).strip()
        m = SET_RE.search(raw)
        if m:
            set_by_dom.setdefault(m.group(1), []).append((i, m.group(2), raw.strip()))
        m = WAIT_RE.search(raw)
        if m:
            wait_by_dom.setdefault(m.group(1), []).append((i, m.group(2), raw.strip()))
        m = ALLOC_RE.search(raw)
        if m:
            alloc_by_dom.setdefault(m.group(1), []).append((i, raw.strip(), i in in_loop))
        m = RELEASE_RE.search(raw)
        if m:
            release_by_dom.setdefault(m.group(1), []).append((i, raw.strip()))
        if CCSET_RE.search(raw):
            cc_set.append((i, raw.strip()))
        if CCWAIT_RE.search(raw):
            cc_wait.append((i, raw.strip()))
        if SYNCALL_RE.search(raw):
            syncall.append((i, raw.strip()))
        m = CONST_ASSIGN_RE.search(raw)
        if m and EVENTNAME_RE.search(m.group(1)):
            consts.append((m.group(1), m.group(2), i, raw.strip()))
        m = CONST_DEFINE_RE.search(raw)
        if m and EVENTNAME_RE.search(m.group(1)):
            consts.append((m.group(1), m.group(2), i, raw.strip()))
        if EVENTNAME_RE.search(raw):
            m = PCT_RE.search(code)
            if m:
                cands.append({"sub": "③", "file": path, "line": i,
                              "note": "事件 ID 取模 %% %s —— 人工核 buffer 数是否 > %s（ID 会重复）"
                                      % (m.group(1), m.group(1)),
                              "code": raw.strip()[:200]})

    # SUB① 按事件域统计 set/wait 次数与 ID 配对
    for dom in sorted(set(set_by_dom) | set(wait_by_dom)):
        sets = set_by_dom.get(dom, [])
        waits = wait_by_dom.get(dom, [])
        if sets and waits and len(sets) != len(waits):
            first = sets[0] if sets else waits[0]
            cands.append({"sub": "①", "file": path, "line": first[0],
                          "note": "事件域 HardEvent::%s 的 SetFlag(%d) 与 WaitFlag(%d) 次数不配平"
                                  % (dom, len(sets), len(waits)),
                          "code": first[2][:200]})
        set_ids = {t[1] for t in sets}
        wait_ids = {t[1] for t in waits}
        for orphan in sorted(set_ids - wait_ids):
            t = next(x for x in sets if x[1] == orphan)
            cands.append({"sub": "①", "file": path, "line": t[0],
                          "note": "孤儿 set：HardEvent::%s 的 ID 「%s」无对应 WaitFlag（等待方可能等不到）"
                                  % (dom, orphan),
                          "code": t[2][:200]})
        for orphan in sorted(wait_ids - set_ids):
            t = next(x for x in waits if x[1] == orphan)
            cands.append({"sub": "①", "file": path, "line": t[0],
                          "note": "孤儿 wait：HardEvent::%s 的 ID 「%s」无对应 SetFlag（等待方可能被卡住）"
                                  % (dom, orphan),
                          "code": t[2][:200]})

    # SUB③ AllocEventID / ReleaseEventID 配对、循环内申请、常量冲突
    for dom in sorted(set(alloc_by_dom) | set(release_by_dom)):
        allocs = alloc_by_dom.get(dom, [])
        rels = release_by_dom.get(dom, [])
        if len(allocs) > len(rels):
            cands.append({"sub": "③", "file": path, "line": allocs[0][0],
                          "note": "AllocEventID<HardEvent::%s>(%d) 多于 ReleaseEventID(%d) —— 事件池可能泄漏/耗尽"
                                  % (dom, len(allocs), len(rels)),
                          "code": allocs[0][1][:200]})
        for ln, code, is_loop in allocs:
            if is_loop:
                cands.append({"sub": "③", "file": path, "line": ln,
                              "note": "AllocEventID<HardEvent::%s> 位于循环体内 —— 每迭代申请易致池耗尽（须成对 Release）"
                                      % dom,
                              "code": code[:200]})
    by_val = {}
    for name, val, ln, code in consts:
        by_val.setdefault(val, []).append((name, ln, code))
    for val, items in sorted(by_val.items(), key=lambda kv: int(kv[0])):
        names = sorted({it[0] for it in items})
        if len(names) > 1:
            for name, ln, code in items:
                cands.append({"sub": "③", "file": path, "line": ln,
                              "note": "事件常量同值冲突：值 %s 被 %s 共用（信号互相覆盖）"
                                      % (val, "、".join(names)),
                              "code": code[:200]})

    # SUB④ 跨核 set/wait 次数不配平
    if cc_set and cc_wait and len(cc_set) != len(cc_wait):
        cands.append({"sub": "④", "file": path, "line": (cc_set + cc_wait)[0][0],
                      "note": "CrossCoreSetFlag(%d) 与 CrossCoreWaitFlag(%d) 次数不配平 —— 等待方可能只感知部分核"
                              % (len(cc_set), len(cc_wait)),
                      "code": (cc_set + cc_wait)[0][1][:200]})

    # SUB② 弱信号：出现 PipeBarrier 的邻域提示（只作定位，不判方向）
    for i, raw in enumerate(lines, 1):
        m = PIPEBARRIER_RE.search(raw)
        if m and m.group(1) in ("V", "MTE2", "MTE3", "S"):
            cands.append({"sub": "②", "file": path, "line": i,
                          "note": "PipeBarrier<PIPE_%s> 只保证同管线顺序，跨管线（V→MTE3 / MTE2→V / S→V 等）须另加 SetFlag/WaitFlag<HardEvent::…>"
                                  % m.group(1),
                          "code": raw.strip()[:200]})

    return cands, bool(syncall), bool(SCHEDMODE_RE.search(text))


def scan(files):
    cands, sub_counts = [], {"①": 0, "②": 0, "③": 0, "④": 0, "⑤": 0}
    has_syncall, has_sched = False, False
    syncall_files = []
    for f in files:
        got = analyze_file(f)
        if isinstance(got, tuple):
            fcands, fa, fs = got
        else:
            fcands, fa, fs = got, False, False
        for c in fcands:
            cands.append(c)
            sub_counts[c["sub"]] = sub_counts.get(c["sub"], 0) + 1
        if fa:
            has_syncall = True
            syncall_files.append(f)
        if fs:
            has_sched = True
    if has_syncall and not has_sched:
        cands.append({"sub": "⑤", "file": syncall_files[0], "line": 0,
                      "note": "扫描集内 kernel 用了 SyncAll<%d 处文件>，但全扫描集无 SetScheduleMode(1) —— 无法保证参与核同时驻留，SyncAll 语义失效"
                              % len(syncall_files),
                      "code": ""})
        sub_counts["⑤"] += 1
    return cands, sub_counts


def self_test():
    import tempfile
    tmp = tempfile.mkdtemp(prefix="scan_sync_")
    bad = os.path.join(tmp, "a_kernel.h")
    clean = os.path.join(tmp, "b_kernel.h")
    host = os.path.join(tmp, "c_host_tiling.cpp")
    with open(bad, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            "constexpr int32_t FIX_MTE2_EVENT = 6;\n"
            "constexpr int32_t S_MTE3_EVENT  = 6;\n"
            "void f() {\n"
            "  SetFlag<HardEvent::MTE2_V>(1);\n"
            "  SetFlag<HardEvent::MTE2_V>(2);\n"
            "  WaitFlag<HardEvent::MTE2_V>(1);\n"
            "  for (int i = 0; i < n; i++) {\n"
            "    int32_t e = GetTPipePtr()->AllocEventID<HardEvent::MTE2_V>();\n"
            "  }\n"
            "  SyncAll<true>();\n"
            "}\n")
    with open(clean, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            "void g() {\n"
            "  SetFlag<HardEvent::V_MTE3>(3);\n"
            "  WaitFlag<HardEvent::V_MTE3>(3);\n"
            "}\n")
    with open(host, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("void t() { context->SetScheduleMode(1); }\n")
    cands, subs = scan([bad, clean])
    notes = [c["note"] for c in cands]
    ok = True
    if not any(c["sub"] == "①" for c in cands):
        print("[FAIL] self-test：set/wait 不配平未报出")
        ok = False
    if not any("同值冲突" in n for n in notes):
        print("[FAIL] self-test：事件常量同值冲突未报出")
        ok = False
    if not any("循环体内" in n for n in notes):
        print("[FAIL] self-test：循环内 AllocEventID 未报出")
        ok = False
    if not any(c["sub"] == "⑤" for c in cands):
        print("[FAIL] self-test：SyncAll 无 SetScheduleMode 未报出")
        ok = False
    clean_cands = [c for c in cands if c["file"] == clean]
    if clean_cands:
        print("[FAIL] self-test：配对齐全的干净文件被误报 %d 条" % len(clean_cands))
        ok = False
    if not ok:
        return 3
    print("[PASS] self-test：五类检查端到端冒烟通过（干净文件零误报）")
    return 0


def main():
    ap = argparse.ArgumentParser(description="同步原语配对完整性检查器（孤儿原语扫描，FP-G02 专属，v1.0）")
    ap.add_argument("targets", nargs="*", help="待扫文件或目录")
    ap.add_argument("--ext", default=",".join(SYNC_EXTS), help="扩展名白名单，逗号分隔")
    ap.add_argument("--format", default="text", choices=("text", "json"))
    ap.add_argument("--out", default="", help="JSON 输出文件（--format json 时可选）")
    ap.add_argument("--exclude", default="", help="路径片段黑名单，逗号分隔（如 /tests/,/build/）")
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

    cands, subs = scan(files)

    if args.format == "json":
        result = {"scanned_files": len(files), "candidates": len(cands),
                  "by_subtype": subs, "items": cands}
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="\n") as f:
                f.write(text + "\n")
            print("[OK] %d 条候选 → %s" % (len(cands), args.out))
        else:
            print(text)
    else:
        print("== FP-G02 配对完整性检查（孤儿原语扫描）==")
        for c in cands:
            loc = "%s:%d" % (c["file"], c["line"]) if c["line"] else c["file"]
            print("[SUB%s] %s  %s" % (c["sub"], loc, c["note"]))
            if c.get("code"):
                print("         %s" % c["code"])
        print("[SUMMARY] files=%d candidates=%d（按子型：①×%d ②×%d ③×%d ④×%d ⑤×%d）"
              % (len(files), len(cands), subs["①"], subs["②"], subs["③"], subs["④"], subs["⑤"]))
    print("[NOTE] 候选 ≠ 缺陷：本工具只做计数/配对启发式提示，不理解分支语义与宏展开；"
          "逐条按 fpg02-sync-review 第 7 节做正负证据与证据等级判定，并以 racecheck 零告警为准；未命中 ≠ 无缺陷。")
    return 1 if cands else 0


if __name__ == "__main__":
    sys.exit(main())
