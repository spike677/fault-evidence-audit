# FP-B10 判据层：L2 怎么测 / L3 会怎么骗你

> 由 `scripts/sync_detect_section.py` 从 `fault_patterns_index.json` 生成，**勿手改**；守门 **C42** 校验与索引逐字一致。
> 改判据：真源 `fault_patterns_detect.json` → `python3 scripts/gen_detect.py` → `python3 scripts/sync_detect_section.py`。

## L2：怎么测才测得出

| 项 | 内容 |
|---|---|
| 遍历轴 `axes` | shape（shape 维度） / concurrency（并发/同步） |
| 观测手段 `oracle` | `golden-utol` |
| 信号类型 `signal` | `concurrency` |
| 执行线 `lines` | `multithread-fuzz` |
| 最少用例数 `min_cases` | 4 |
| 造数据 `constructor` | 多级拓扑矩阵（单机 2 卡 vs 多级 Mesh/UBX、非 2 的幂 rank、奇数 rank）；send_counts 作为图输入而非常量；数据量跨 2^24；AICPU 与 AICore 双路径对拍。 |
| 判据 `judge` | 各拓扑下通信结果与参考一致；IR 上未知维确实置为未知（只打日志不算）；配置越界给明确报错而非静默错配。 |
| 判别力 `kill` | 若通信域拓扑下标或配置窄化错配，则非 2 的幂 rank 或跨 2^24 数据量下结果错位、部分输出恒为 0。 |

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