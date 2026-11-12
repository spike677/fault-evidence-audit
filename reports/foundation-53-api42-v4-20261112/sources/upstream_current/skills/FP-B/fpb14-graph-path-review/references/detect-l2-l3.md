# FP-B14 判据层：L2 怎么测 / L3 会怎么骗你

> 由 `scripts/sync_detect_section.py` 从 `fault_patterns_index.json` 生成，**勿手改**；守门 **C42** 校验与索引逐字一致。
> 改判据：真源 `fault_patterns_detect.json` → `python3 scripts/gen_detect.py` → `python3 scripts/sync_detect_section.py`。

## L2：怎么测才测得出

| 项 | 内容 |
|---|---|
| 遍历轴 `axes` | sequence（执行序列） / attr（属性） |
| 观测手段 `oracle` | `golden-utol` / `error-code` |
| 信号类型 `signal` | `sequence` |
| 执行线 `lines` | `precision` / `error-scenario` |
| 最少用例数 `min_cases` | 2 |
| 造数据 `constructor` | 每个算子至少一条图模式冒烟（ptgraph 或 aclGraph），断言「与 aclnn 结果一致 + 不抛 GRAPH_FAILED」；对新增 attr 补「proto 默认值 ∈ tiling 接受域」静态断言。 |
| 判据 `judge` | 图模式与 aclnn 直调结果一致，不抛 GRAPH_FAILED / E40021 / 507011。 |
| 判别力 `kill` | 若图模式通路未同步适配，则 aclnn 正常而图模式报 GRAPH_FAILED 或结果与 aclnn 不一致。 |

> 只读 L1 机理卡会产出「不得复现该现象」的空壳用例；按上表 `axes` 铺开、按 `min_cases` 定量、按 `judge` 判成立才算可上板。

## L3：这些 oracle 本身会怎么骗你（判读前必查）

### `golden-utol`（共 17 条）

- `K91`（假 FAIL）inf==inf 被判超容差；溢出类用例整批假 FAIL
- `K171`（假 FAIL）容差必须按 dtype 与 mode 分级，一套 fp32 阈值不能判所有
- `K508`（假 PASS）judge 列写成 JSON 会被静默忽略 → 回落 dtype 默认容差（fp16 rtol=1e-3）
- `K700`（假 PASS）judge 空串与 None 语义不同：空串会回落 dtype 默认容差

### `error-code`（共 6 条）

- `K583`（假 FAIL）inplace 接口「广播变宽」是 161002 正确拒绝，纯 doc 基线会成片假 FAIL
- `K866`（漏检）dtype 变异只改张量不改 aclScalar → 结构上抓不到标量 dtype 不校验
- `K990`（假 FAIL）CanCast 三条禁令须先读：float→int / →bool 被拒是正确行为

---

判 FAIL 前先排除该 oracle 的「假 FAIL」类失效；判 PASS 前先排除「假 PASS / 假绿 / 漏检」类失效。**不查 L3 就报缺陷或报通过，报告作废。**

全文不在本库复制：拿 K 号去 `aclnn-bug-hunt` 的 `references/pitfalls/` grep。本节共引用 23 条 L3 判据。 <!-- END DETECT-SECTION -->