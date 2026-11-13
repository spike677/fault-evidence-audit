#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FP-B07-6 类型感知检测器：`int64_t/uint64_t x = <全 32 位操作数乘法>`。

定位的问题
-----------
正则签名只能捕捉 `SetGlobalBuffer(... * ...)` 这类**形状**，而成因⑥（GM 偏移 32 位计算域
溢出）的真实写法往往是一句普通赋值：

    uint64_t xOffset = mnConfig.mIdx * mnConfig.singleM * mnConfig.n + tailN;

左值已经是 64 位、右侧全为 `uint32_t` 字段 —— 先回绕再赋值，`SetGlobalBuffer` 那行反而
看不到乘法。本脚本用**轻量类型推断**补上这一面：

  1) 解析 `struct NAME { field; }` 建字段类型表；
  2) 解析 `Type var;` / 函数形参建变量类型表；
  3) 解析 `obj.field`（obj 的声明类型 → 字段类型）；
  4) 左值 64 位 + RHS 含 `*` + RHS 无显式宽化 + 参与乘法的操作数**全部 ≤32 位** → HIGH；
     含无法解析的操作数 → UNKNOWN（单列，默认不计入失败）。

不做值域分析：HIGH 只表示"类型域上可溢出"，是否可触发取决于合法 shape 上界（见卡片
「反推最大可能值」一步）。因此 HIGH 是**候选**，须按 FP-B07 卡片第 7 节判定标准过正向/
负向证据。

用法
----
    python3 scripts/scan_uint64_mul.py <仓根或目录> [<仓根> ...]
        [--json out.json] [--baseline baseline.json] [--include-unknown] [--quiet]

退出码：0=无未豁免 HIGH；1=存在未豁免 HIGH；2=参数/环境错误。

baseline.json：{"accepted": ["repo:path:line", ...]}，用于豁免已人工判定为安全的命中
（如 UB 内小偏移），每条应在评审记录中写明理由。

实证（2026-10-20，四仓 10,389 个 kernel 文件）
---------------------------------------------
ops-transformer 373 条候选 / 8 处确认；ops-nn 374 / 10；ops-math 157 / 13；
ops-cv 29 / 0（13 条 HIGH 逐条判读后为 UB 偏移或不可达）。
"""
import argparse
import json
import os
import re
import sys

EXCL = ("/experimental/", "/tests/", "/examples/", "/3rd/", "/build/")
INT32 = {"uint32_t", "int32_t", "unsigned", "int", "uint16_t", "int16_t",
         "uint8_t", "int8_t", "short", "char"}
INT64 = {"uint64_t", "int64_t", "size_t", "uintptr_t", "intptr_t",
         "long long", "unsigned long long", "int64", "uint64"}

ASSIGN64 = re.compile(r"^\s*(?:const\s+)?(?:u?int64_t|int64_t|uint64_t)\s+(\w+)\s*=\s*([^;]+);")
STRUCT = re.compile(r"\bstruct\s+(\w+)\s*\{")
FIELD = re.compile(r"^\s*(?:const\s+)?([A-Za-z_][\w:<>]*)\s+([^;{}]+);\s*$", re.M)
DECL = re.compile(r"\b(?:const\s+)?(uint32_t|int32_t|uint64_t|int64_t|unsigned|int|size_t|"
                  r"uint16_t|int16_t|uint8_t|int8_t)\s+(\w+)\s*(?:[;{=,])")
WIDENED = re.compile(r"(?:static_cast|uint64_t|int64_t|\(uint64_t\)|\(int64_t\))")


def strip(text):
    """去注释与字符串，保留行号。"""
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def match_brace(text, k):
    depth = 0
    while k < len(text):
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                return k
        k += 1
    return -1


_OP_STRUCT_CACHE = {}


def op_structs(op_root):
    """跨文件兜底：扫描同一 op_kernel 根下的 struct 定义（缓存）。"""
    if op_root in _OP_STRUCT_CACHE:
        return _OP_STRUCT_CACHE[op_root]
    merged = {}
    for dp, _dns, fns in os.walk(op_root):
        if any(x in dp.replace("\\", "/") + "/" for x in EXCL):
            continue
        for fn in fns:
            if not fn.endswith((".h", ".hpp", ".inc")):
                continue
            try:
                t = strip(open(os.path.join(dp, fn), encoding="utf-8", errors="replace").read())
            except OSError:
                continue
            if "struct" not in t:
                continue
            st, _, _ = collect_types(t)
            for k, v in st.items():
                merged.setdefault(k, v)
    _OP_STRUCT_CACHE[op_root] = merged
    return merged


def collect_types(text):
    structs, var2struct, var2type = {}, {}, {}
    for m in STRUCT.finditer(text):
        name = m.group(1)
        k = text.find("{", m.end() - 1)
        e = match_brace(text, k)
        if e < 0:
            continue
        fields = {}
        for fm in FIELD.finditer(text[k + 1:e]):
            typ, decls = fm.group(1), fm.group(2)
            for d in decls.split(","):
                mm = re.match(r"\*?\s*(\w+)", d.strip())
                if mm:
                    fields[mm.group(1)] = typ.replace("const ", "").strip()
        structs[name] = fields
    for m in re.finditer(r"\b([A-Z]\w*)\s+(\w+)\s*[;{=,)]", text):
        if m.group(1) in structs:
            var2struct[m.group(2)] = m.group(1)
    # 函数形参：`MNConfig& mnConfig` / `const MNConfig* cfg`
    for m in re.finditer(r"\b(?:const\s+)?([A-Z]\w*)\s*[&*]\s*(\w+)\s*[,)]", text):
        var2struct.setdefault(m.group(2), m.group(1))
    for m in DECL.finditer(text):
        var2type[m.group(2)] = m.group(1)
    # 符号常量：`static constexpr uint32_t X = 2;` —— 参与乘法时按声明类型计
    for m in re.finditer(r"constexpr\s+([A-Za-z_]\w*)\s+(\w+)\s*=", text):
        var2type.setdefault(m.group(2), m.group(1))
    return structs, var2struct, var2type


def operand_types(rhs, structs, var2struct, var2type):
    types = []
    for m in re.finditer(r"\b([A-Za-z_]\w*)(?:\s*\.\s*([A-Za-z_]\w*))?", rhs):
        base, field = m.group(1), m.group(2)
        if base in ("sizeof", "static_cast", "uint64_t", "int64_t",
                    "uint32_t", "int32_t", "true", "false"):
            continue
        if field:
            st = var2struct.get(base)
            types.append(structs.get(st, {}).get(field, "?"))
        elif base in var2type:
            types.append(var2type[base])
        elif base in var2struct:
            types.append("struct")
        else:
            types.append("?")
    return types


def scan_repo(root, repo):
    rows = []
    for dp, _dns, fns in os.walk(root):
        rel = dp.replace("\\", "/").replace(root, "")
        if any(x in rel + "/" for x in EXCL):
            continue
        for fn in fns:
            if not fn.endswith((".h", ".cpp", ".inc", ".hpp")):
                continue
            path = (rel + "/" + fn).lstrip("/")
            try:
                text = strip(open(os.path.join(root, path), encoding="utf-8", errors="replace").read())
            except OSError:
                continue
            if "*" not in text:
                continue
            structs, var2struct, var2type = collect_types(text)
            op_root = path.split("/op_kernel/")[0] if "/op_kernel/" in path else os.path.dirname(path)
            if var2struct and any(v not in structs for v in var2struct.values()):
                for st_name, fields in op_structs(os.path.join(root, op_root)).items():
                    structs.setdefault(st_name, fields)
            for i, line in enumerate(text.split("\n"), 1):
                m = ASSIGN64.match(line)
                if not m or "*" not in m.group(2) or WIDENED.search(m.group(2)):
                    continue
                ops = operand_types(m.group(2), structs, var2struct, var2type)
                known = [o for o in ops if o != "?"]
                if not known or any(o in INT64 or "64" in o for o in known):
                    continue
                if not all(o in INT32 or o == "struct" for o in known):
                    continue
                rows.append({"repo": repo, "file": path, "line": i,
                             "sev": "UNKNOWN" if "?" in ops else "HIGH",
                             "code": line.strip()[:160], "types": sorted(set(known))[:4]})
    return rows


def main():
    ap = argparse.ArgumentParser(description="FP-B07-6 类型感知检测器")
    ap.add_argument("roots", nargs="+", help="仓根或目录（可多个）")
    ap.add_argument("--json", dest="json_out", default=None, help="完整结果写入 json")
    ap.add_argument("--baseline", default=None, help="豁免清单 {\"accepted\": [repo:path:line]}")
    ap.add_argument("--include-unknown", action="store_true", help="UNKNOWN 也计入失败")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    for r in args.roots:
        if not os.path.isdir(r):
            print("[ERROR] 目录不存在：%s" % r)
            return 2

    accepted = set()
    if args.baseline:
        if not os.path.isfile(args.baseline):
            print("[ERROR] baseline 不存在：%s" % args.baseline)
            return 2
        accepted = set(json.load(open(args.baseline, encoding="utf-8")).get("accepted", []))

    rows = []
    for root in args.roots:
        ab = os.path.abspath(root).replace("\\", "/")
        name = os.path.basename(ab.rstrip("/")) or ab
        rows.extend(scan_repo(ab, name))

    sev = {"HIGH"} | ({"UNKNOWN"} if args.include_unknown else set())
    hits = [r for r in rows if r["sev"] in sev]
    new = [r for r in hits if "%s:%s:%d" % (r["repo"], r["file"], r["line"]) not in accepted]

    if args.json_out:
        json.dump({"total": len(rows), "hit": hits, "new": new},
                  open(args.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    if not args.quiet:
        print("[FP-B07-6] scanned=%d hit=%d baseline=%d new=%d"
              % (len(rows), len(hits), len(hits) - len(new), len(new)))
        for r in new[:50]:
            print("  %s:%s:%d  %s\n      %s" % (r["repo"], r["file"], r["line"],
                                                ",".join(r["types"]), r["code"][:120]))
        if len(new) > 50:
            print("  ... 其余 %d 条见 --json 输出" % (len(new) - 50))
        print("  提示：HIGH 仅是候选；按 patterns/FP-B/FP-B07.md 的判定标准过正向/负向证据。")

    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
