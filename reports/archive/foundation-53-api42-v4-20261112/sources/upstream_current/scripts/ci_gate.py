#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地/CI 统一网关（ci_gate.py）

为什么要有这一层
----------------
C1–C50 全在 `check_fault_patterns.py` 里，但**没有任何机制保证它被跑**——仓里原无 CI
（v6.19 才补）。其余 23 项检查散落在 `scripts/` 下（生成物新鲜度、自检、可视化站点等），
同样只能靠人记。本脚本是「一条命令跑完所有门禁」的唯一入口，
CI（`.gitlab-ci.yml`）和本地（`python3 scripts/ci_gate.py`）共用同一份清单，
避免「CI 绿了但本地口径不同」这类分裂。

当前清单 **24 项**：23 个 blocking + 1 个 advisory（锚点存活率，依赖算子仓是否挂载）。
第三方依赖只有 `scripts/scan_dataflow.py --self-test` 需要的 tree-sitter / tree-sitter-cpp，
清单见仓根 `requirements-ci.txt`——CI 的 before_script 与本地装的是同一份。

分级
----
  blocking   必须过；任一失败 → 退出码 1。改了库/脚本/技能就必须全绿才能合。
  advisory   不过只警告；多依赖外部环境（算子仓是否挂载、上板实测），当前不阻断。

算子仓相关检查（`check_anchors`）默认是 advisory：CI 里往往不克隆四个算子仓，
硬拦会让所有 MR 都红。本地有仓时它会真跑；要强制，加 `--strict-repos`。

用法
----
python3 scripts/ci_gate.py                     # 全部 blocking + advisory
python3 scripts/ci_gate.py --blocking-only     # 只跑阻断项（快速）
python3 scripts/ci_gate.py --strict-repos      # 把锚点检查升级为阻断（需挂载算子仓）
python3 scripts/ci_gate.py --json              # 机读结果
python3 scripts/ci_gate.py --list              # 只列出检查项

退出码
------
0 = 全部 blocking 通过 ｜1 = 有 blocking 失败 ｜2 = 参数错误
"""

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (名称, 命令, 级别, 说明)
CHECKS = [
    ("全库守门 C1–C50", [sys.executable, "check_fault_patterns.py"],
     "blocking", "结构/索引/技能/L2L3/组合/工作流/文档计数一致性"),
    ("评测集结构", [sys.executable, "scripts/run_eval.py", "--validate"],
     "blocking", "53 模式 × 3 类用例"),
    ("评测判分器自检", [sys.executable, "scripts/run_eval.py", "--self-test"],
     "blocking", "全对/错判/缺失/strict 三态"),
    ("L2 判据层", [sys.executable, "scripts/gen_detect.py", "--check"],
     "blocking", "53/53 齐备 + 索引↔真源全等"),
    ("L2/L3 进技能", [sys.executable, "scripts/sync_detect_section.py", "--check"],
     "blocking", "指针段 + references 与索引逐字一致"),
    ("签名扫描器", [sys.executable, "scripts/scan_fp.py", "--self-test"],
     "blocking", "118 条签名卫生 + 冒烟"),
    ("同步配对检查", [sys.executable, "scripts/scan_sync.py", "--self-test"],
     "blocking", "孤儿原语扫描"),
    ("同步作用域审计", [sys.executable, "scripts/scan_sync_scope.py", "--self-test"],
     "blocking", "四件套被分支独占"),
    ("行号校验器", [sys.executable, "scripts/verify_lines.py", "--self-test"],
     "blocking", "报告引用可达"),
    ("分诊表", [sys.executable, "scripts/gen_triage.py", "--check"],
     "blocking", "7 入口 / 53 模式覆盖"),
    ("评测集生成物", [sys.executable, "scripts/gen_evals.py", "--check"],
     "blocking", "生成器 ↔ 文件一致"),
    ("案例库", [sys.executable, "scripts/gen_cases.py", "--check"],
     "blocking", "100 案例 / 深度档覆盖"),
    ("评分卡", [sys.executable, "scripts/score_skills.py", "--check"],
     "blocking", "53 份 / 十维一致"),
    ("签名产出基线", [sys.executable, "scripts/sig_yield.py", "--check",
                  "cases/sig_yield-ops-math.json"],
     "blocking", "118 签名 / 9 子型判据有记录"),
    ("组合/未知候选单测", [sys.executable, "scripts/test_query_patterns.py"],
     "blocking", "8 项"),
    ("第二 oracle 覆盖", [sys.executable, "scripts/check_secondary_oracle.py", "--check"],
     "blocking", "高优先级模式须有第二判据"),
    ("计数配平判据", [sys.executable, "scripts/scan_counts.py", "--self-test"],
     "blocking", "规则可加载 + 亏空可标出 + 样本不足不出结论"),
    ("跨语句数据流工具", [sys.executable, "scripts/scan_dataflow.py", "--self-test"],
     "blocking", "direct/via 两通路 + guard 豁免（工具级，未挂为模式判据）"),
    ("变异测试可执行性", [sys.executable, "scripts/mutate_ops.py", "--self-test"],
     "blocking", "变异算子库 + 注入/回滚冒烟"),
    ("可视化站点", [sys.executable, "scripts/gen_site.py", "--check"],
     "blocking", "site/index.html 与真源一致（库改了没重生成即失败）"),
    ("README 入口分流图", [sys.executable, "scripts/gen_readme_diagram.py", "--check"],
     "blocking", "README 图内数字由真源注入（库改了没重生成即失败）"),
    ("AGENTS 尾部计数", [sys.executable, "scripts/gen_agents_tail.py", "--check"],
     "blocking", "AGENTS.md 末行 14 项计数与真源一致（该行此前无门禁，曾漂 6 个版本）"),
    ("元信息门禁自检", [sys.executable, "scripts/test_meta_gates.py"],
     "blocking", "C47/C48 反向验证：造漂移必须报错、删掉必须恢复（防「永远绿」的装饰门禁）"),
    ("锚点存活率", [sys.executable, "scripts/check_anchors.py"],
     "advisory", "真实锚在算子仓 HEAD 是否仍可复算"),
]


def run_one(cmd):
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=900)
        return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 124, "超时（900s）"
    except (OSError, subprocess.SubprocessError) as e:
        return 125, "无法执行：%s" % e


def tail(text, n=3):
    lines = [l for l in text.split("\n") if l.strip()]
    return "\n".join(lines[-n:])


def main(argv=None):
    ap = argparse.ArgumentParser(description="统一门禁网关（CI 与本地同源）")
    ap.add_argument("--blocking-only", action="store_true")
    ap.add_argument("--strict-repos", action="store_true",
                    help="把锚点存活率升级为 blocking（要求已挂载算子仓）")
    ap.add_argument("--repos", default="", help="算子仓父目录，透传给 check_anchors")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    checks = []
    for name, cmd, level, desc in CHECKS:
        if args.blocking_only and level == "advisory":
            continue
        if args.strict_repos and name == "锚点存活率":
            level = "blocking"
        if name == "锚点存活率" and args.repos:
            cmd = cmd + ["--repos", args.repos]
        checks.append((name, cmd, level, desc))

    if args.list:
        for name, _cmd, level, desc in checks:
            print("[%-8s] %-22s %s" % (level, name, desc))
        return 0

    results = []
    failed_blocking = 0
    for name, cmd, level, desc in checks:
        code, out = run_one(cmd)
        ok = code == 0
        if not ok and level == "blocking":
            failed_blocking += 1
        results.append({"name": name, "level": level, "code": code,
                        "ok": ok, "tail": tail(out) if not ok else ""})
        mark = "OK  " if ok else ("FAIL" if level == "blocking" else "WARN")
        print("[%s] %-22s %s" % (mark, name, desc if ok else ""))
        if not ok:
            for line in results[-1]["tail"].split("\n"):
                print("       " + line)

    total = len(results)
    okn = sum(1 for r in results if r["ok"])
    print("-" * 74)
    print("[SUMMARY] %d/%d 通过｜blocking 失败 %d" % (okn, total, failed_blocking))
    if args.json:
        print(json.dumps({"results": results, "passed": okn, "total": total,
                          "blocking_failed": failed_blocking},
                         ensure_ascii=False, indent=2))
    return 1 if failed_blocking else 0


if __name__ == "__main__":
    sys.exit(main())
