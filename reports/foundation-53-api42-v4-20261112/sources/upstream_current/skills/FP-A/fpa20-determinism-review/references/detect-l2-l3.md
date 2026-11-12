# FP-A20 判据层：L2 怎么测 / L3 会怎么骗你

> 由 `scripts/sync_detect_section.py` 从 `fault_patterns_index.json` 生成，**勿手改**；守门 **C42** 校验与索引逐字一致。
> 改判据：真源 `fault_patterns_detect.json` → `python3 scripts/gen_detect.py` → `python3 scripts/sync_detect_section.py`。

## L2：怎么测才测得出

| 项 | 内容 |
|---|---|
| 遍历轴 `axes` | bitwise（逐位一致） / shape（shape 维度） / sequence（执行序列） |
| 观测手段 `oracle` | `bitwise` / `golden-utol` |
| 信号类型 `signal` | `bitwise` |
| 执行线 `lines` | `determinism` / `precision` |
| 最少用例数 `min_cases` | 3 |
| 造数据 `constructor` | 按「输出 × 路径 × shape 区间」三级矩阵设定比对策略；严格确定的输出用 torch.equal 重复 100 次全等。 |
| 判据 `judge` | 确定输出 bitwise 全等；非确定输出容差比对且结论显式标注触发 shape 区间。 |
| 判别力 `kill` | 若确定性被二元描述掩盖，则被判「确定」的输出在重复执行中出现 bit 不一致。 |

> 只读 L1 机理卡会产出「不得复现该现象」的空壳用例；按上表 `axes` 铺开、按 `min_cases` 定量、按 `judge` 判成立才算可上板。

## L3：这些 oracle 本身会怎么骗你（判读前必查）

### `bitwise`（共 4 条）

- `K638`（假 FAIL）+inf 的 log-sigmoid 输出是 -0.0：按位比对必须先归一符号零
- `K1189`（假 FAIL）mtfuzz 的 none 腿对重叠累加算子刷出上千假 FAIL，判据只看 acl 腿
- **注意**：该类目前未登记「假 PASS / 假绿」侧——不代表该方向不存在，实测踩到后请回补 L3（D29 只要求全库两类都覆盖，不强制每类双向）。

### `golden-utol`（共 17 条）

- `K91`（假 FAIL）inf==inf 被判超容差；溢出类用例整批假 FAIL
- `K171`（假 FAIL）容差必须按 dtype 与 mode 分级，一套 fp32 阈值不能判所有
- `K508`（假 PASS）judge 列写成 JSON 会被静默忽略 → 回落 dtype 默认容差（fp16 rtol=1e-3）
- `K700`（假 PASS）judge 空串与 None 语义不同：空串会回落 dtype 默认容差

---

判 FAIL 前先排除该 oracle 的「假 FAIL」类失效；判 PASS 前先排除「假 PASS / 假绿 / 漏检」类失效。**不查 L3 就报缺陷或报通过，报告作废。**

全文不在本库复制：拿 K 号去 `aclnn-bug-hunt` 的 `references/pitfalls/` grep。本节共引用 21 条 L3 判据。 <!-- END DETECT-SECTION -->