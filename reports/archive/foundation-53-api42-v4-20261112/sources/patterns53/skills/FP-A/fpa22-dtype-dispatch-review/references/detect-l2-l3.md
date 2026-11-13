# FP-A22 判据层：L2 怎么测 / L3 会怎么骗你

> 由 `scripts/sync_detect_section.py` 从 `fault_patterns_index.json` 生成，**勿手改**；守门 **C42** 校验与索引逐字一致。
> 改判据：真源 `fault_patterns_detect.json` → `python3 scripts/gen_detect.py` → `python3 scripts/sync_detect_section.py`。

## L2：怎么测才测得出

| 项 | 内容 |
|---|---|
| 遍历轴 `axes` | dtype（dtype 分支） / shape（shape 维度） |
| 观测手段 `oracle` | `golden-canary` / `golden-utol` |
| 信号类型 `signal` | `canary` |
| 执行线 `lines` | `precision` / `valid-fuzz` |
| 最少用例数 `min_cases` | 4 |
| 造数据 `constructor` | dtype × shape 全组合矩阵（每受支持 dtype 至少「1 元素 / 非整除行宽 / 带 diagonal 边界」三档）；输出 buffer 预填魔数 0x7FC07FC0；同宽度兄弟 dtype 成对对照。 |
| 判据 `judge` | 返回码 + 输出全量正确；魔数残留比例为 0（禁止只断言返回码）。 |
| 判别力 `kill` | 若 dtype→模板映射条目错配，则同宽度兄弟 dtype（int32 vs uint32）结果不同，或输出部分未写致魔数残留。 |

> 只读 L1 机理卡会产出「不得复现该现象」的空壳用例；按上表 `axes` 铺开、按 `min_cases` 定量、按 `judge` 判成立才算可上板。

## L3：这些 oracle 本身会怎么骗你（判读前必查）

### `golden-canary`（共 5 条）

- `K128`（假 PASS）随机/索引类接口的输出整块未写只能靠独立金丝雀发现，分布判据会假 PASS
- `K129`（假 PASS）金丝雀图案不能与合法输出重合：掩码类 0xFF 就是 prob=0 的正确输出
- `K427`（假阳）mssanitizer 对 aclnn 直调缓冲的 OOB 判定是 shadow 假象，须哨兵+块对齐阴性对照定案

### `golden-utol`（共 17 条）

- `K91`（假 FAIL）inf==inf 被判超容差；溢出类用例整批假 FAIL
- `K171`（假 FAIL）容差必须按 dtype 与 mode 分级，一套 fp32 阈值不能判所有
- `K508`（假 PASS）judge 列写成 JSON 会被静默忽略 → 回落 dtype 默认容差（fp16 rtol=1e-3）
- `K700`（假 PASS）judge 空串与 None 语义不同：空串会回落 dtype 默认容差

---

判 FAIL 前先排除该 oracle 的「假 FAIL」类失效；判 PASS 前先排除「假 PASS / 假绿 / 漏检」类失效。**不查 L3 就报缺陷或报通过，报告作废。**

全文不在本库复制：拿 K 号去 `aclnn-bug-hunt` 的 `references/pitfalls/` grep。本节共引用 22 条 L3 判据。 <!-- END DETECT-SECTION -->