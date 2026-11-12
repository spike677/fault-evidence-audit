# FP-B09 判据层：L2 怎么测 / L3 会怎么骗你

> 由 `scripts/sync_detect_section.py` 从 `fault_patterns_index.json` 生成，**勿手改**；守门 **C42** 校验与索引逐字一致。
> 改判据：真源 `fault_patterns_detect.json` → `python3 scripts/gen_detect.py` → `python3 scripts/sync_detect_section.py`。

## L2：怎么测才测得出

| 项 | 内容 |
|---|---|
| 遍历轴 `axes` | shape（shape 维度） / input-validity（入参合法性） |
| 观测手段 `oracle` | `error-code` |
| 信号类型 `signal` | `legal-accept` |
| 执行线 `lines` | `valid-fuzz` / `error-scenario` |
| 最少用例数 `min_cases` | 4 |
| 造数据 `constructor` | 每个算子必配动态 shape 最小集 {-2} / {-1} / {-1,-1,-1} / {-1,-1,-1,-1}，断言不报错（只比精度的用例走不到比较步）；另加动静一致性对拍。 |
| 判据 `judge` | 动态 shape 全部可编译可执行，不报 infershape/verifier 错误；动静结果一致。 |
| 判别力 `kill` | 若 -2/-1 被当真实维度参与校验，则动态最小集在 infershape/verifier 阶段报维度不为 N 的错。 |

> 只读 L1 机理卡会产出「不得复现该现象」的空壳用例；按上表 `axes` 铺开、按 `min_cases` 定量、按 `judge` 判成立才算可上板。

## L3：这些 oracle 本身会怎么骗你（判读前必查）

### `error-code`（共 6 条）

- `K583`（假 FAIL）inplace 接口「广播变宽」是 161002 正确拒绝，纯 doc 基线会成片假 FAIL
- `K866`（漏检）dtype 变异只改张量不改 aclScalar → 结构上抓不到标量 dtype 不校验
- `K990`（假 FAIL）CanCast 三条禁令须先读：float→int / →bool 被拒是正确行为

---

判 FAIL 前先排除该 oracle 的「假 FAIL」类失效；判 PASS 前先排除「假 PASS / 假绿 / 漏检」类失效。**不查 L3 就报缺陷或报通过，报告作废。**

全文不在本库复制：拿 K 号去 `aclnn-bug-hunt` 的 `references/pitfalls/` grep。本节共引用 6 条 L3 判据。 <!-- END DETECT-SECTION -->