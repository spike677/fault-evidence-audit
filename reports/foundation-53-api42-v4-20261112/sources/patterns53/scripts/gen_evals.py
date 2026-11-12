#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
评测集生成器（gen_evals.py，v6.4）

用途
----
为 51 条模式各生成一份 `evals/<FP-XX>/evals.json`，每份 **3 类用例**：

- `positive`：现象指向本模式 → 期望 `verdict: FP-XX`
- `neighbor-negative`：现象属于相邻模式（`related[0]`）→ 期望判给相邻模式，**不得误判为本模式**
- `out-of-scope`：未定界到算子缺陷 / 属环境与选型 → 期望 `verdict: OUT_OF_SCOPE`

评测协议见 `evals/README.md`：任何 agent 按用例作答后，把回答存为 `<case-id>.md`，
其中须有一行 `verdict: <FP-XX | OUT_OF_SCOPE>`；`scripts/run_eval.py` 负责判分与混淆矩阵。

证据级判据（v6.4）
-----------------
每条用例带 `must_include`（**全部须命中**，AND）与 `forbidden`（**命中任一即扣**）：
`must_include` 强制答案给出「动作 + 证据等级」两侧（OOS 用例改为「定界/环境/选型」措辞），
`forbidden` 抓三类硬伤：内部单号/本地路径泄漏、绝对化断言（「已确认为缺陷」）、
OOS 用例里强行「属 FP-XX」。`run_eval.py --strict` 才启用这两项；不加 `--strict` 仍只判 verdict。

用法
----
python3 scripts/gen_evals.py            # 生成/覆盖 51 份 evals.json
python3 scripts/gen_evals.py --check    # 校验现存文件与生成结果一致（CI 用）
python3 scripts/gen_evals.py --root <库根>

设计约束（与守门 C21 / C36 对齐）
--------------------------------
- 现象描述取自索引 `symptoms`（用户可见现象），**不抄卡片机理**，避免用答案考答案；
- 每份必须含三类用例各 ≥1；用例 id 全局唯一；`expected_verdict` 必须是库内编号或 OUT_OF_SCOPE；
- **OOS 池 18 个独立剧本**、按序轮转分配：任一剧本复用 ≤3 次（v6.4 前只有 6 个剧本、被复制 8~9 次，
  「153 个用例」的实际区分度只有约 108 条——C36 拦截复用超限）；
- 生成器只保证结构与覆盖，用例质量随卡片 `symptoms` 演进——改卡片后重跑本脚本即可刷新。
"""

import argparse
import json
import os
import sys

OUT_OF_SCOPE_POOL = [
    "整网训练 loss 不收敛，尚未定界到单算子，也拿不出最小复现用例。",
    "驱动/固件版本不匹配，device 起不来，任何算子都跑不了。",
    "需求评审：新算子该用 Ascend C 还是 TBE 实现，目前没有任何缺陷现象。",
    "模型精度下降，但数据分布与训练超参尚未排除。",
    "CI 机器磁盘满导致构建失败，换机器后恢复正常。",
    "想在模型侧做量化压缩，咨询精度损失评估方法（未定界到算子缺陷）。",
    "训练脚本 OOM，排查发现是 dataloader 的 pin_memory 配置过大，与算子无关。",
    "换新机器后吞吐翻倍，怀疑旧机器 CPU 降频，尚未定位到任何算子。",
    "咨询 CANN 版本与 PyTorch 版本的兼容矩阵怎么选，没有提到任何报错。",
    "算子要从 A2 迁到 A3，问迁移工作量评估（当前无缺陷现象）。",
    "集群网络抖动致通信偶发超时，交换机侧已定位到丢包，非软件缺陷。",
    "文档措辞想改成中英双语并统一排版，属编辑规范诉求而非内容不一致。",
    "clang-format 检查不通过，想统一仓内代码格式。",
    "单元测试覆盖率统计口径是什么、怎么接入流水线，无缺陷现象。",
    "想给算子增加性能打点，问 profiler 的使用方式。",
    "数据集标注错误导致训练指标异常，已确认与算子计算无关。",
    "许可证合规问询：能否把该仓代码引入商业产品。",
    "提测流程问询：新算子合入前需要走哪些评审节点。",
]

# 证据级判据（v6.4）：判分不只看 verdict，还要看答案是否「有据」且「不编」。
# must_include 为 **全部须命中**（AND）；forbidden 为 **命中任一即扣**。
MUST_ACTION = "首查|检查项|核对|排查|扫描|查看|定位"
MUST_EVIDENCE = "证据等级|静态可证|需实测确认|信息不足|缺.{0,6}证据"
MUST_OOS = ("不在(本库)?适用面|超出(本库)?(适用|范围)|不属(于)?(算子|本库)|未定界|"
            "环境问题|方案选型|选型问题|流程问题|与算子(计算)?无关")
PROMPT_TAIL_OOS = ("请判定是否属于本库适用面；若不适用，须说明定界理由（如环境 / 流程 / 方案选型 / 与算子无关），"
                   "不得强行套用任一 FP 模式。回答末尾须有一行 `verdict: <FP-XX | OUT_OF_SCOPE>`。")
FORBID_LEAK = "BUG-\\d{8}|[A-Za-z]:\\\\|内部日报|内部缺陷单"
FORBID_ABSOLUTE = "已确认为缺陷|必然是缺陷|无条件确定是缺陷"
FORBID_OOS = "属\\s?FP-[A-G]\\d{2}|应判\\s?FP-[A-G]\\d{2}"

PROMPT_TAIL = ("请判定属于本库哪条故障模式（给出 FP 编号与子型），并给出首查动作与需要补齐的证据；"
               "信息不足时说明还缺什么。回答末尾须有一行 `verdict: <FP-XX | OUT_OF_SCOPE>`。")


def read_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load(root):
    idx = read_json(os.path.join(root, "fault_patterns_index.json"))
    cov = {}
    import re
    cover_re = re.compile(r"^\|\s*\[(FP-[A-G]\d{2})\]\(([^)]+)\)\s*\|[^|]+\|\s*`([^`]+)`\s*\|")
    with open(os.path.join(root, "skills", "README.md"), encoding="utf-8") as f:
        for line in f:
            m = cover_re.match(line)
            if m:
                cov[m.group(1)] = m.group(3)
    return idx, cov


def short(s, n=90):
    s = s.strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def build_case(cid, kind, prompt, expected, expected_output, must=None, forbidden=None):
    return {"id": cid, "kind": kind, "prompt": prompt,
            "expected_verdict": expected, "expected_output": expected_output,
            "must_include": must or [], "forbidden": forbidden or []}


def case_files(idx, cov):
    by_id = {p["id"]: p for p in idx["patterns"]}
    order = [p["id"] for p in idx["patterns"]]
    out = {}
    for i, pid in enumerate(order):
        p = by_id[pid]
        symptoms = p.get("symptoms") or []
        ap = p.get("applicability") or {}
        ctx = "仓：%s；侧别：%s；载体：%s。" % (
            ",".join(ap.get("repos") or ["All"]),
            ",".join(ap.get("sides") or ["All"]),
            ",".join(ap.get("carriers") or ["All"]))
        s = "；".join(short(x) for x in symptoms[:3]) or short(p["name"])
        must_base = [MUST_ACTION, MUST_EVIDENCE]
        forbid_base = [FORBID_LEAK, FORBID_ABSOLUTE]
        pos = build_case(pid + "-P1", "positive",
                         "【现象】%s\n【上下文】%s\n%s" % (s, ctx, PROMPT_TAIL),
                         pid,
                         "应判 %s；给出该模式子型与首查动作；结论须附证据等级。" % pid,
                         must=must_base + [pid], forbidden=forbid_base)
        rel = (p.get("related") or [])
        nid = rel[0] if rel else order[(i + 1) % len(order)]
        np_ = by_id.get(nid, p)
        ns = "；".join(short(x) for x in (np_.get("symptoms") or [])[:3]) or short(np_["name"])
        det = (np_.get("detectors") or [""])[0]
        neg = build_case(pid + "-N1", "neighbor-negative",
                         "【现象】%s\n【已有证据】%s 指向该机制。\n【上下文】%s\n%s"
                         % (ns, det or "（待补工具证据）", ctx, PROMPT_TAIL),
                         nid,
                         "应判 %s；该现象带有 %s 的典型工具证据（%s），应据此归 %s；"
                         "若判 %s，须给出 [文件]:[行号] 级负向证据。"
                         % (nid, nid, det or "工具证据", nid, pid),
                         must=must_base + [nid], forbidden=forbid_base)
        neg["discriminator"] = "证据类型偏向 %s（%s）；判 %s 须给出负向证据" % (nid, det or "工具证据", pid)
        xs = OUT_OF_SCOPE_POOL[i % len(OUT_OF_SCOPE_POOL)]
        out[pid] = {
            "skill_name": cov.get(pid, ""),
            "pattern_id": pid,
            "eval_mode": "text",
            "verdict_convention": "回答末尾须有一行 `verdict: <FP-XX | OUT_OF_SCOPE>`",
            "evals": [
                pos,
                neg,
                build_case(pid + "-X1", "out-of-scope",
                           "【现象】%s\n%s" % (xs, PROMPT_TAIL_OOS), "OUT_OF_SCOPE",
                           "应声明不在本库适用面（未定界到算子缺陷 / 属环境或方案选型），"
                           "不得强行套用任一 FP 模式。",
                           must=[MUST_OOS], forbidden=[FORBID_LEAK, FORBID_OOS]),
            ],
        }
    return out


def render(files):
    return {pid: json.dumps(obj, ensure_ascii=False, indent=2) + "\n" for pid, obj in files.items()}


def main():
    ap = argparse.ArgumentParser(description="评测集生成器（v3.8）")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    idx, cov = load(root)
    files = case_files(idx, cov)
    texts = render(files)
    if args.check:
        bad = []
        for pid, text in texts.items():
            p = os.path.join(root, "evals", pid, "evals.json")
            if not os.path.isfile(p):
                bad.append("%s 缺 evals.json" % pid)
            elif open(p, encoding="utf-8").read().replace("\r\n", "\n") != text:
                bad.append("%s 与生成结果不一致（改卡片后未重跑 gen_evals.py）" % pid)
        for b in bad:
            print("[ERROR] " + b)
        if bad:
            return 3
        print("[OK] 评测集校验通过：%d 份，每份 3 类用例" % len(texts))
        return 0
    for pid, text in texts.items():
        d = os.path.join(root, "evals", pid)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "evals.json"), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print("[OK] 已生成 %d 份 evals.json（每份 positive / neighbor-negative / out-of-scope 各 1）" % len(texts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
