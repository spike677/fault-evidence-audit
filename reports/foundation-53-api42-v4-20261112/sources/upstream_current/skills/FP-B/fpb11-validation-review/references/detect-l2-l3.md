# FP-B11 判据层：L2 怎么测 / L3 会怎么骗你

> 由 `scripts/sync_detect_section.py` 从 `fault_patterns_index.json` 生成，**勿手改**；守门 **C42** 校验与索引逐字一致。
> 改判据：真源 `fault_patterns_detect.json` → `python3 scripts/gen_detect.py` → `python3 scripts/sync_detect_section.py`。

## L2：怎么测才测得出

| 项 | 内容 |
|---|---|
| 遍历轴 `axes` | input-validity（入参合法性） / contract（契约一致性） / boundary（边界值） |
| 观测手段 `oracle` | `error-code` |
| 信号类型 `signal` | `error-code` |
| 执行线 `lines` | `error-scenario` |
| 最少用例数 `min_cases` | 4 |
| 造数据 `constructor` | 非法输入六轴矩阵：rank × ListInt 长度 × 维度符号 × 属性量级 × 有限性 × dtype 组合；空数组/空 ListInt 单独建例；每算子补一组「InferShape 与 tiling 结论必须一致」的双阶段断言。 |
| 判据 `judge` | 第一段接口即返回 161002（ACLNN_ERR_PARAM_INVALID），而非落到 561002；两阶段接受集合完全相同。 |
| 判别力 `kill` | 若契约校验缺失/写反/校验对象选错，则非法 shape 返回 0 或被接受，或落到内部错误 561002。 |

> 只读 L1 机理卡会产出「不得复现该现象」的空壳用例；按上表 `axes` 铺开、按 `min_cases` 定量、按 `judge` 判成立才算可上板。

## L3：这些 oracle 本身会怎么骗你（判读前必查）

### `error-code`（共 6 条）

- `K583`（假 FAIL）inplace 接口「广播变宽」是 161002 正确拒绝，纯 doc 基线会成片假 FAIL
- `K866`（漏检）dtype 变异只改张量不改 aclScalar → 结构上抓不到标量 dtype 不校验
- `K990`（假 FAIL）CanCast 三条禁令须先读：float→int / →bool 被拒是正确行为

---

判 FAIL 前先排除该 oracle 的「假 FAIL」类失效；判 PASS 前先排除「假 PASS / 假绿 / 漏检」类失效。**不查 L3 就报缺陷或报通过，报告作废。**

全文不在本库复制：拿 K 号去 `aclnn-bug-hunt` 的 `references/pitfalls/` grep。本节共引用 6 条 L3 判据。 <!-- END DETECT-SECTION -->