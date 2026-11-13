# FP-C01 判据层：L2 怎么测 / L3 会怎么骗你

> 由 `scripts/sync_detect_section.py` 从 `fault_patterns_index.json` 生成，**勿手改**；守门 **C42** 校验与索引逐字一致。
> 改判据：真源 `fault_patterns_detect.json` → `python3 scripts/gen_detect.py` → `python3 scripts/sync_detect_section.py`。

## L2：怎么测才测得出

| 项 | 内容 |
|---|---|
| 遍历轴 `axes` | perf（性能） / shape（shape 维度） |
| 观测手段 `oracle` | `perf-baseline` |
| 信号类型 `signal` | `perf` |
| 执行线 `lines` | `none` |
| 最少用例数 `min_cases` | 2 |
| 造数据 `constructor` | profiler kernel_details 聚合；跨版本耗时比值 >1.15 看护；先校验基线四要素（shape/dtype/芯片/编译选项）可比性。 |
| 判据 `judge` | 跨版本耗时比值 ≤1.15；无整数倍台阶式劣化。 |
| 判别力 `kill` | 若 host 循环上界或派发条件算错致重复调度，则耗时呈非整数倍台阶而精度全对。 |

> 只读 L1 机理卡会产出「不得复现该现象」的空壳用例；按上表 `axes` 铺开、按 `min_cases` 定量、按 `judge` 判成立才算可上板。

## L3：这些 oracle 本身会怎么骗你（判读前必查）

### `perf-baseline`（共 4 条）

- `K480`（假 PASS）设计门禁 G6/G16 是字面量匹配，params 缺约定串会静默不判
- `K154`（假 FAIL）基线只取属性不取形状：属性依赖 rank，会造出成批非法组合
- `K1039`（假 FAIL）「out 缩维」接口的自动基线把 out 造成与 self 同形，基线自检必败

---

判 FAIL 前先排除该 oracle 的「假 FAIL」类失效；判 PASS 前先排除「假 PASS / 假绿 / 漏检」类失效。**不查 L3 就报缺陷或报通过，报告作废。**

全文不在本库复制：拿 K 号去 `aclnn-bug-hunt` 的 `references/pitfalls/` grep。本节共引用 4 条 L3 判据。 <!-- END DETECT-SECTION -->