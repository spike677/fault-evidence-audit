#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重算 AGENTS.md 尾部那行计数（配合门禁 C47）。

## 为什么需要这个脚本

AGENTS.md 是 agent 进仓后**第一个读**的文件，末尾那行写了 14 项计数
（版本 / 规模 / 签名数 / 子型数 / 深度档 / L2 / L3 / 组合 / 第二 oracle）。
这行此前**没有任何门禁**，于是从 v6.21 一路漂到落后 6 个版本
（写「52 条 / 81 子型」，实际 53 条 / 91 子型），而 C1~C46 全绿。

漂移不会让门禁变红，只会让读者读到假数字——这类缺陷最难被发现，
因为**没有任何东西会失败**。所以做了两件事：C47 逐项比对 + 本脚本一键重算。

## 用法

    python3 scripts/gen_agents_tail.py            # 重写 AGENTS.md 末行
    python3 scripts/gen_agents_tail.py --check    # 只校验（C47 已内置，此为独立入口）

## 口径

所有数字**只从真源算**，不从其它 md 抄：
- 版本 / 规模 / 签名 / 子型 / 深度档 ← `fault_patterns_index.json`
- L2 判据数 / L3 失效率与条数     ← `fault_patterns_detect.json`
- 组合数                          ← `pattern_compositions.json`
- 第二 oracle 模式与关系数        ← `fault_patterns_secondary_oracle.json`
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TAIL_RE = re.compile(
    r"^> 版本：v([\d.]+) ｜ 规模：(\d+) 条 ｜ 有可扫签名：(\d+)/(\d+) "
    r"｜ 已机读化子型：(\d+) 模式 / (\d+) 条 ｜ 深度档：(\d+) "
    r"｜ L2 判据：(\d+)/(\d+) ｜ L3 失效：(\d+) 类 / (\d+) 条 "
    r"｜ 组合：(\d+) 条 ｜ 第二 oracle：(\d+) 模式 / (\d+) 关系", re.M)


def _load(name):
    path = os.path.join(ROOT, name)
    if not os.path.isfile(path):
        return {}
    with io.open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def compute():
    """按真源算出 14 项。返回 (行文本, [(名称, 值)])。"""
    idx = _load("fault_patterns_index.json")
    det = _load("fault_patterns_detect.json")
    comp = _load("pattern_compositions.json")
    so = _load("fault_patterns_secondary_oracle.json")

    pats = idx.get("patterns") or []
    n = len(pats)
    by_oracle = ((det.get("oracle_failures") or {}).get("by_oracle") or {})
    pairs = [
        ("版本", "v%s" % idx.get("version")),
        ("规模", n),
        ("有可扫签名", sum(1 for p in pats if p.get("signatures"))),
        ("规模(分母)", n),
        ("子型模式", sum(1 for p in pats if p.get("subtypes"))),
        ("子型条数", sum(len(p.get("subtypes") or []) for p in pats)),
        ("深度档", sum(1 for p in pats if p.get("depth") == "深度")),
        ("L2 判据", len(det.get("patterns") or [])),
        ("L2 分母", n),
        ("L3 类", len(by_oracle)),
        ("L3 条", sum(len(v) for v in by_oracle.values())),
        ("组合", len(comp.get("compositions") or [])),
        ("第二 oracle 模式", len(so.get("patterns") or {})),
        ("第二 oracle 关系", sum(len(v.get("relations") or [])
                                for v in (so.get("patterns") or {}).values())),
    ]
    tpl = ("> 版本：%s ｜ 规模：%d 条 ｜ 有可扫签名：%d/%d ｜ 已机读化子型：%d 模式 / %d 条 ｜ "
           "深度档：%d ｜ L2 判据：%d/%d ｜ L3 失效：%d 类 / %d 条 ｜ 组合：%d 条 ｜ "
           "第二 oracle：%d 模式 / %d 关系")
    return tpl % tuple(v for _, v in pairs), pairs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="重算 AGENTS.md 尾部计数（配合 C47）")
    ap.add_argument("--check", action="store_true", help="只校验不写")
    args = ap.parse_args(argv)

    path = os.path.join(ROOT, "AGENTS.md")
    if not os.path.isfile(path):
        print("[FAIL] 找不到 %s" % path)
        return 2
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        raw = fh.read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")

    want, pairs = compute()
    m = TAIL_RE.search(text)
    if not m:
        print("[FAIL] AGENTS.md 找不到尾部计数行（格式应为 `> 版本：vX ｜ 规模：N 条 ｜ …`）")
        return 2

    if args.check:
        # 逐项比对，定位是哪一项漂了（只报「不一致」等于让人自己找）
        nums = [m.group(1)] + [int(m.group(i)) for i in range(2, 15)]
        bad = []
        for (name, val), got in zip(pairs, nums):
            # 版本项在正则里不带 `v`、真源里带 `v`，比对前统一剥掉前缀
            got_v = str(got).lstrip("v")
            want_v = str(val).lstrip("v")
            if got_v != want_v:
                bad.append("%s 写 %s 实际 %s" % (name, got, want_v))
        if bad:
            print("[FAIL] AGENTS.md 尾部计数漂移 %d 项：%s" % (len(bad), "；".join(bad)))
            return 1
        print("[OK] AGENTS.md 尾部计数 14 项与真源一致")
        return 0

    if m.group(0) == want:
        print("[OK] 无需改动（尾部计数已是最新）")
        return 0
    text = text[:m.start()] + want + text[m.end():]
    with io.open(path, "w", encoding="utf-8", newline=nl) as fh:
        fh.write(text)
    print("[OK] 已重写 AGENTS.md 尾部计数：%s" % want)
    return 0


if __name__ == "__main__":
    sys.exit(main())
