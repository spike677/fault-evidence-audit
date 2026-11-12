#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C47 / C48 两条「元信息新鲜度」门禁的离线自检。

这两条门禁的共同点：它们要抓的缺陷**不会让任何别的东西失败**——
`AGENTS.md` 写着落后 6 个版本的假数字，`C1~C46` 照样全绿；
根目录躺着一个没人引用的 285 行副本，链接检查（C29）照样全绿，
因为 C29 只查「已引用的链接是否可达」，不查「该被引用的有没有被引用」。

所以必须**主动造出漂移**来验证门禁真的会红，否则等于又加了一条「永远绿」的装饰。

## 覆盖

- C48：根目录出现无名入链的 md ⇒ 报错；删除后 ⇒ 恢复；白名单（README/CHANGELOG/LICENSE）不算孤儿。
- C47 + `gen_agents_tail.py`：篡改 `/AGENTS.md` 尾部任一计数 ⇒ `--check` 失败并**指出是哪一项**；
  `gen_agents_tail.py`（不带 `--check`）⇒ 修回并幂等。

用法：python3 scripts/test_meta_gates.py
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.join(ROOT, "AGENTS.md")
README = os.path.join(ROOT, "README.md")
INVARIANTS_MD = os.path.join(ROOT, "INVARIANTS.md")

PASS, FAIL = "  PASS", "  FAIL"
_results = {"pass": 0, "fail": []}


def check(name, cond, detail=""):
    if cond:
        _results["pass"] += 1
        print("%s  %s" % (PASS, name))
    else:
        _results["fail"].append(name)
        print("%s  %s%s" % (FAIL, name, ("  ← " + detail) if detail else ""))


def run(args, timeout=180):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def gate():
    return run([sys.executable, "check_fault_patterns.py"])


# ---------------- C48 ----------------

def test_c48_orphan_is_caught():
    """根目录凭空多一个 md 且无人引用 ⇒ C48 必须报错。"""
    victim = os.path.join(ROOT, "_ORPHAN_SELFTEST.md")
    try:
        with io.open(victim, "w", encoding="utf-8") as fh:
            fh.write("# selftest orphan\n\n无人引用。\n")
        r = gate()
        out = (r.stdout or "") + (r.stderr or "")
        check("C48 能抓到根目录孤儿 md", "C48" in out and "_ORPHAN_SELFTEST.md" in out,
              out[-300:])
        check("C48 报错时退出码非 0", r.returncode != 0, "rc=%d" % r.returncode)
    finally:
        if os.path.isfile(victim):
            os.remove(victim)


def test_c48_recovers_after_removal():
    """删掉孤儿后必须恢复全绿 —— 否则门禁会一直红，等于逼人加白名单绕过。"""
    r = gate()
    out = (r.stdout or "") + (r.stderr or "")
    check("删孤儿后 C48 恢复", "C48" not in out or "孤儿" not in out, out[-300:])
    check("删孤儿后门禁整体通过", r.returncode == 0, "rc=%d" % r.returncode)


def test_c48_whitelist_not_flagged():
    """README / CHANGELOG / LICENSE 是天然入口，不该被当孤儿。"""
    r = gate()
    out = (r.stdout or "") + (r.stderr or "")
    for name in ("README.md", "CHANGELOG.md", "LICENSE"):
        check("C48 白名单不误报 %s" % name,
              ("孤儿" not in out) or (name not in out.split("孤儿")[-1][:40]),
              out[-200:])


# ---------------- C47 ----------------

def test_c47_detects_count_drift():
    """篡改 AGENTS 尾部任一计数 ⇒ gen_agents_tail --check 必须失败并指明哪一项。"""
    if not os.path.isfile(AGENTS):
        check("C47 AGENTS.md 存在", False, "文件缺失")
        return
    backup = AGENTS + ".selftest.bak"
    shutil.copy2(AGENTS, backup)
    try:
        with io.open(AGENTS, encoding="utf-8-sig", newline="") as fh:
            raw = fh.read()
        nl = "\r\n" if "\r\n" in raw else "\n"
        text = raw.replace("\r\n", "\n")
        # 把「规模：N 条」里的 N 加 1，制造必然漂移
        import re
        m = re.search(r"规模：(\d+) 条", text)
        if not m:
            check("C47 尾部行可解析", False, "找不到「规模：N 条」")
            return
        bad = int(m.group(1)) + 1
        text = text[:m.start(1)] + str(bad) + text[m.end(1):]
        with io.open(AGENTS, "w", encoding="utf-8", newline=nl) as fh:
            fh.write(text)

        r = run([sys.executable, "scripts/gen_agents_tail.py", "--check"])
        check("C47 能抓到计数漂移", r.returncode != 0, "rc=%d" % r.returncode)
        out = (r.stdout or "") + (r.stderr or "")
        check("C47 报错时指出具体项（不是只说「不一致」）",
              "规模" in out and str(bad) in out, out[-300:])

        # 修回：不带 --check 应重写并幂等
        r2 = run([sys.executable, "scripts/gen_agents_tail.py"])
        check("gen_agents_tail 能修回", r2.returncode == 0, (r2.stdout or "")[-200:])
        r3 = run([sys.executable, "scripts/gen_agents_tail.py", "--check"])
        check("修回后 C47 通过", r3.returncode == 0, (r3.stdout or "")[-200:])
        r4 = run([sys.executable, "scripts/gen_agents_tail.py"])
        check("gen_agents_tail 幂等（第二次无需改动）",
              "无需改动" in ((r4.stdout or "") + (r4.stderr or "")), (r4.stdout or "")[-200:])
    finally:
        if os.path.isfile(backup):
            shutil.copy2(backup, AGENTS)
            os.remove(backup)


def test_all_green_after_restore():
    r = gate()
    check("全部自检跑完后门禁回到全绿", r.returncode == 0,
          ((r.stdout or "") + (r.stderr or ""))[-300:])


def test_c50_detects_prose_drift():
    """篡改 README 散文里的计数 ⇒ C50 必须报错并指明是哪一项。

    这是 v6.31 补的门禁：此前把「50/53 有可扫签名」改回「49/52」，
    C1~C49 与 ci_gate 双双仍全绿——散文计数完全没有覆盖。
    """
    if not os.path.isfile(README):
        check("C50 README.md 存在", False, "文件缺失")
        return
    backup = README + ".selftest.bak"
    shutil.copy2(README, backup)
    try:
        with io.open(README, encoding="utf-8-sig", newline="") as fh:
            raw = fh.read()
        nl = "\r\n" if "\r\n" in raw else "\n"
        text = raw.replace("\r\n", "\n")
        import re
        m = re.search(r"(\d+)/(\d+) 有可扫签名", text)
        if not m:
            check("C50 「N/M 有可扫签名」可解析", False, "找不到该短语")
            return
        good = m.group(0)
        # 造一个必然漂移的值（分子减 1，分母加 1）
        bad = "%d/%d 有可扫签名" % (int(m.group(1)) - 1, int(m.group(2)) + 1)
        text = text[:m.start()] + bad + text[m.end():]
        with io.open(README, "w", encoding="utf-8", newline=nl) as fh:
            fh.write(text)

        r = gate()
        out = (r.stdout or "") + (r.stderr or "")
        check("C50 能抓到散文计数漂移", r.returncode != 0, "rc=%d" % r.returncode)
        check("C50 报错时指出具体项（不是只说「不一致」）",
              "C50" in out and "可扫签名" in out, out[-300:])

        # 恢复后必须回到全绿——证明它抓的是漂移本身，不是误报
        shutil.copy2(backup, README)
        r2 = gate()
        check("C50 修回后门禁回到全绿", r2.returncode == 0,
              ((r2.stdout or "") + (r2.stderr or ""))[-300:])
    finally:
        if os.path.isfile(backup):
            shutil.copy2(backup, README)
            os.remove(backup)


def test_c50_stale_value_is_caught():
    """把旧值短语写回文档 ⇒ C50 的「旧值黑名单」必须报错（双路防回改）。"""
    if not os.path.isfile(INVARIANTS_MD):
        check("C50 INVARIANTS.md 存在", False, "文件缺失")
        return
    backup = INVARIANTS_MD + ".selftest.bak"
    shutil.copy2(INVARIANTS_MD, backup)
    try:
        with io.open(INVARIANTS_MD, encoding="utf-8-sig", newline="") as fh:
            raw = fh.read()
        nl = "\r\n" if "\r\n" in raw else "\n"
        text = raw.replace("\r\n", "\n")
        import re
        m = re.search(r"库里的 (\d+) 条模式", text)
        if not m:
            check("C50 INVARIANTS 计数可解析", False, "找不到该短语")
            return
        text = text[:m.start()] + "库里的 52 条模式" + text[m.end():]
        with io.open(INVARIANTS_MD, "w", encoding="utf-8", newline=nl) as fh:
            fh.write(text)

        r = gate()
        out = (r.stdout or "") + (r.stderr or "")
        check("C50 能抓到 INVARIANTS 模式数漂移", r.returncode != 0, "rc=%d" % r.returncode)
        check("C50 报错定位到 INVARIANTS.md", "INVARIANTS" in out, out[-300:])
    finally:
        if os.path.isfile(backup):
            shutil.copy2(backup, INVARIANTS_MD)
            os.remove(backup)


def main():
    print("== C48 根目录孤儿门禁")
    test_c48_orphan_is_caught()
    test_c48_recovers_after_removal()
    test_c48_whitelist_not_flagged()
    print("== C47 AGENTS 尾部计数门禁")
    test_c47_detects_count_drift()
    print("== C50 文档散文计数门禁")
    test_c50_detects_prose_drift()
    test_c50_stale_value_is_caught()
    test_all_green_after_restore()

    total = _results["pass"] + len(_results["fail"])
    print("\n%d passed, %d failed" % (_results["pass"], len(_results["fail"])))
    if _results["fail"]:
        print("失败项：" + "、".join(_results["fail"]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
