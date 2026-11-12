# FP-B06 判据层：L2 怎么测 / L3 会怎么骗你

> 由 `scripts/sync_detect_section.py` 从 `fault_patterns_index.json` 生成，**勿手改**；守门 **C42** 校验与索引逐字一致。
> 改判据：真源 `fault_patterns_detect.json` → `python3 scripts/gen_detect.py` → `python3 scripts/sync_detect_section.py`。

## L2：怎么测才测得出

| 项 | 内容 |
|---|---|
| 遍历轴 `axes` | shape（shape 维度） / input-validity（入参合法性） |
| 观测手段 `oracle` | `golden-canary` / `error-code` |
| 信号类型 `signal` | `canary` |
| 执行线 `lines` | `valid-fuzz` / `error-scenario` |
| 最少用例数 `min_cases` | 4 |
| 造数据 `constructor` | 空 tensor 探针矩阵=「接口 × 输入位置 × 空形态（0 维标量 / 含 0 维 shape / 正常）」；优先覆盖「已写判空但漏了一个输入」的接口；空用例须同时跑 regbase 与非 regbase。 |
| 判据 `judge` | 合法空输入输出等价 no-op；非法组合明确报错而非静默 SUCCESS；以 PyTorch CPU 参考为准。 |
| 判别力 `kill` | 若判空只覆盖部分输入，则该输入置空时第一段报错或读越界，而同接口其他输入置空正常。 |

> 只读 L1 机理卡会产出「不得复现该现象」的空壳用例；按上表 `axes` 铺开、按 `min_cases` 定量、按 `judge` 判成立才算可上板。

## L3：这些 oracle 本身会怎么骗你（判读前必查）

### `golden-canary`（共 5 条）

- `K128`（假 PASS）随机/索引类接口的输出整块未写只能靠独立金丝雀发现，分布判据会假 PASS
- `K129`（假 PASS）金丝雀图案不能与合法输出重合：掩码类 0xFF 就是 prob=0 的正确输出
- `K427`（假阳）mssanitizer 对 aclnn 直调缓冲的 OOB 判定是 shadow 假象，须哨兵+块对齐阴性对照定案

### `error-code`（共 6 条）

- `K583`（假 FAIL）inplace 接口「广播变宽」是 161002 正确拒绝，纯 doc 基线会成片假 FAIL
- `K866`（漏检）dtype 变异只改张量不改 aclScalar → 结构上抓不到标量 dtype 不校验
- `K990`（假 FAIL）CanCast 三条禁令须先读：float→int / →bool 被拒是正确行为

---

判 FAIL 前先排除该 oracle 的「假 FAIL」类失效；判 PASS 前先排除「假 PASS / 假绿 / 漏检」类失效。**不查 L3 就报缺陷或报通过，报告作废。**

全文不在本库复制：拿 K 号去 `aclnn-bug-hunt` 的 `references/pitfalls/` grep。本节共引用 11 条 L3 判据。 <!-- END DETECT-SECTION -->