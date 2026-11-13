# FP-A14 判据层：L2 怎么测 / L3 会怎么骗你

> 由 `scripts/sync_detect_section.py` 从 `fault_patterns_index.json` 生成，**勿手改**；守门 **C42** 校验与索引逐字一致。
> 改判据：真源 `fault_patterns_detect.json` → `python3 scripts/gen_detect.py` → `python3 scripts/sync_detect_section.py`。

## L2：怎么测才测得出

| 项 | 内容 |
|---|---|
| 遍历轴 `axes` | dtype（dtype 分支） / content（内容取值） |
| 观测手段 `oracle` | `golden-utol` |
| 信号类型 `signal` | `golden` |
| 执行线 `lines` | `precision` |
| 最少用例数 `min_cases` | 2 |
| 造数据 `constructor` | 强制走两条路径（Vector FFMA / Cube MMAD）的开关级用例对比，同一输入切路径各跑一遍。 |
| 判据 `judge` | 两条指令路径各自与标杆一致，切路径前后无系统性偏差。 |
| 判别力 `kill` | 若 FFMA 与 MMAD 精度语义差异未补偿，则同一输入切路径后结果超出 utol。 |

> 只读 L1 机理卡会产出「不得复现该现象」的空壳用例；按上表 `axes` 铺开、按 `min_cases` 定量、按 `judge` 判成立才算可上板。

## L3：这些 oracle 本身会怎么骗你（判读前必查）

### `golden-utol`（共 17 条）

- `K91`（假 FAIL）inf==inf 被判超容差；溢出类用例整批假 FAIL
- `K171`（假 FAIL）容差必须按 dtype 与 mode 分级，一套 fp32 阈值不能判所有
- `K508`（假 PASS）judge 列写成 JSON 会被静默忽略 → 回落 dtype 默认容差（fp16 rtol=1e-3）
- `K700`（假 PASS）judge 空串与 None 语义不同：空串会回落 dtype 默认容差

---

判 FAIL 前先排除该 oracle 的「假 FAIL」类失效；判 PASS 前先排除「假 PASS / 假绿 / 漏检」类失效。**不查 L3 就报缺陷或报通过，报告作废。**

全文不在本库复制：拿 K 号去 `aclnn-bug-hunt` 的 `references/pitfalls/` grep。本节共引用 17 条 L3 判据。 <!-- END DETECT-SECTION -->