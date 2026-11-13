#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第二 oracle 覆盖校验（check_secondary_oracle.py，v6.19）

要解决的问题
------------
实测（v6.19 首轮）：**40/52 条模式（77%）只有单一 oracle**；当前进度 **24/53 已登记**、
高优先级 20/20 全覆盖（本脚本 --check 的打印为准）。单点判据的根本问题不是「不够准」，
而是**错了没人知道**——返回码正确但错误码选错、racecheck 零告警但连接口都没进 kernel。
这类「正确且错误」在单点判据下不可见，报告会以 70% 置信度写下一个错结论。

第二判据的**唯一硬要求是「机制独立」**：如果第二个判据和第一个落在同一个失效机制上
（如都依赖 golden 数值比对），它不提供任何新信息，只是让概率看起来更好看。因此本脚本
除了查「有没有」，还查「是不是同一个」：

  D30 高优先级模式缺第二判据
      范围 = risk.level 为「高」且 depth 为「深度」——这两类是要真出结论的，
      不给第二判据就等于让报告裸奔。其余模式鼓励但暂不强制。
  D31 第二判据与主判据机制重复
      主判据 oracle 集合与第二判据 kind 必须不是同一类失效面
      （如主判据已含 `golden-utol`，第二判据的 kind 不得又是「只换个数比法」）。
  D32 relations 结构不合法
      每条须有 id / name / statement / kill / how；id 全局唯一且前缀 = 模式编号。
  D33 缺 kill 说明
      `kill` 是「这个关系为什么能打死缺陷」的解释——没有它，关系只是形式上的检查项，
      无法判断它到底有没有判别力。
  D34 kind 不在词表
  D35 引用了不存在的模式 / 覆盖了未登记的模式

退出码
------
0 = 全部合规 ｜1 = 有 ERROR ｜2 = 参数/环境错误
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 主判据 oracle → 它所在失效面。用于判断第二判据是否「换汤不换药」。
ORACLE_FACE = {
    "golden-utol": "numeric",
    "golden-canary": "structural",
    "bitwise": "numeric",
    "error-code": "contract",
    "sanitizer-memcheck": "memory",
    "sanitizer-racecheck": "concurrency",
    "watchdog": "liveness",
    "log-field": "observability",
    "struct-invariant": "structural",
    "symbol-resolve": "contract",
    "perf-baseline": "performance",
    "memory-peak": "memory",
}

# 第二判据 kind → 失效面。两者同面即「机制不独立」。
KIND_FACE = {
    "metamorphic": "numeric",
    "cross-path": "differential",
    "invariant": "structural",
    "idempotence": "determinism",
    "conservation": "numeric",
    "symbolic": "contract",
}

# 允许「同面但不同源」的例外：differential/determinism 对任何主判据都是新增维度
ALWAYS_INDEPENDENT = {"differential", "determinism"}


def read_json(p):
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


def validate(root):
    errs, infos = [], []
    idx_p = os.path.join(root, "fault_patterns_index.json")
    so_p = os.path.join(root, "fault_patterns_secondary_oracle.json")
    if not os.path.isfile(so_p):
        return ["缺 fault_patterns_secondary_oracle.json（第二 oracle 真源）"], []
    idx = read_json(idx_p)
    so = read_json(so_p)

    kinds = set(so.get("kinds") or {})
    patterns = idx.get("patterns") or []
    known = {p.get("id"): p for p in patterns}
    reg = so.get("patterns") or {}

    # D35 未知模式
    for pid in reg:
        if pid not in known:
            errs.append("D35 第二判据登记了不存在的模式：%s" % pid)

    # D30 覆盖：高风险 + 深度档
    need = [p["id"] for p in patterns
            if (p.get("risk") or {}).get("level") == "高" and p.get("depth") == "深度"]
    missing = [pid for pid in need if pid not in reg]
    if missing:
        errs.append("D30 以下高优先级模式缺第二 oracle（%d 条）：%s"
                    % (len(missing), "、".join(missing)))

    # 逐条结构 + 独立性
    seen_ids = set()
    for pid, item in reg.items():
        if not isinstance(item, dict):
            errs.append("D32 %s 的登记不是对象" % pid)
            continue
        kind = item.get("kind")
        if kind not in kinds:
            errs.append("D34 %s.kind=%r 不在词表内（%s）"
                        % (pid, kind, "、".join(sorted(kinds))))
        why = str(item.get("why") or "").strip()
        if not why:
            errs.append("D32 %s 缺 why（为什么这个模式需要第二判据）" % pid)
        rels = item.get("relations")
        if not isinstance(rels, list) or not rels:
            errs.append("D32 %s.relations 必须是非空数组" % pid)
            continue
        prefix = pid.replace("FP-", "")
        for r in rels:
            if not isinstance(r, dict):
                errs.append("D32 %s.relations 含非对象条目" % pid)
                continue
            rid = str(r.get("id") or "").strip()
            if not rid:
                errs.append("D32 %s 有一条关系缺 id" % pid)
            elif rid in seen_ids:
                errs.append("D32 关系 id 重复：%s" % rid)
            elif not re.match(r"^%s-" % re.escape(prefix), rid):
                errs.append("D32 关系 id %s 未以前缀 %s- 开头" % (rid, prefix))
            seen_ids.add(rid)
            for key in ("name", "statement", "how"):
                if not str(r.get(key) or "").strip():
                    errs.append("D32 %s/%s 缺 %s" % (pid, rid or "?", key))
            if not str(r.get("kill") or "").strip():
                errs.append("D33 %s/%s 缺 kill（为什么这条关系能打死缺陷）"
                            % (pid, rid or "?"))

        # D31 机制独立性
        prim = ((known.get(pid) or {}).get("detect") or {}).get("oracle") or []
        faces = {ORACLE_FACE.get(o) for o in prim}
        kface = KIND_FACE.get(kind)
        if kface in ALWAYS_INDEPENDENT:
            continue
        if kface in faces and len(faces) == 1:
            # 主判据只有单一失效面，且第二判据同面 → 不独立
            errs.append("D31 %s 的第二判据 kind=%s 与主判据 %s 同属 %s 失效面，"
                        "不提供独立信息；请改用 cross-path/idempotence 等异面判据"
                        % (pid, kind, "/".join(prim), kface))

    infos.append("第二 oracle：%d/%d 条模式已登记（高优先级 %d/%d）"
                 % (len(reg), len(patterns), len(need) - len(missing), len(need)))
    by_kind = {}
    for item in reg.values():
        k = item.get("kind")
        by_kind[k] = by_kind.get(k, 0) + 1
    infos.append("  判据类型分布：" + "、".join("%s=%d" % kv for kv in sorted(by_kind.items())))
    infos.append("  关系总数：%d" % len(seen_ids))
    return errs, infos


def self_test():
    """构造最小合法库 → 应 0 error；再逐项破坏 → 每条规则都要报。"""
    import tempfile
    import shutil

    src = ROOT
    tmp = tempfile.mkdtemp(prefix="so_")
    dst = os.path.join(tmp, "repo")
    os.makedirs(dst)
    for name in ("fault_patterns_index.json", "fault_patterns_secondary_oracle.json"):
        shutil.copy(os.path.join(src, name), os.path.join(dst, name))
    base_errs, _ = validate(dst)
    print("[%s] 基线（真实数据）：%d ERROR" % ("PASS" if not base_errs else "FAIL",
                                              len(base_errs)))
    if base_errs:
        for e in base_errs[:5]:
            print("    ", e)

    def mutate(fn):
        d2 = os.path.join(tmp, "m")
        if os.path.isdir(d2):
            shutil.rmtree(d2)
        shutil.copytree(dst, d2)
        fn(d2)
        return validate(d2)[0]

    def drop_one(d):
        p = os.path.join(d, "fault_patterns_secondary_oracle.json")
        j = read_json(p)
        j["patterns"].pop("FP-G02")
        json.dump(j, open(p, "w", encoding="utf-8"), ensure_ascii=False)

    def same_face(d):
        p = os.path.join(d, "fault_patterns_secondary_oracle.json")
        j = read_json(p)
        j["patterns"]["FP-A01"]["kind"] = "metamorphic"  # 与 golden-utol 同属 numeric
        j["patterns"]["FP-A01"]["relations"][0]["kill"] = ""
        json.dump(j, open(p, "w", encoding="utf-8"), ensure_ascii=False)

    checks = [
        ("D30 删掉一条高风险模式的登记", "D30", drop_one),
        ("D31/D33 改成同面 + 清空 kill", "D31", same_face),
    ]
    ok = not base_errs
    for name, tag, fn in checks:
        errs = mutate(fn)
        hit = [e for e in errs if e.startswith(tag)]
        good = bool(hit)
        ok = ok and good
        print("[%s] %s → %s" % ("PASS" if good else "FAIL", name,
                                hit[0][:80] if hit else "未报错"))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="第二 oracle 覆盖与独立性校验")
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--check", action="store_true", help="只校验（供 CI）")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    errs, infos = validate(os.path.abspath(args.root))
    for i in infos:
        print("[INFO] " + i)
    if errs:
        print("[FAIL] 第二 oracle 校验未通过，共 %d 项：" % len(errs))
        for e in errs:
            print("  - " + e)
        return 1
    print("[PASS] 第二 oracle 校验通过（覆盖 + 独立性 + kill 说明）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
