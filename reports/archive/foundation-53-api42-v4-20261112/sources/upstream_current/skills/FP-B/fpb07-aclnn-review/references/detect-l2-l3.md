# FP-B07 判据层：L2 怎么测 / L3 会怎么骗你

> 由 `scripts/sync_detect_section.py` 从 `fault_patterns_index.json` 生成，**勿手改**；守门 **C42** 校验与索引逐字一致。
> 改判据：真源 `fault_patterns_detect.json` → `python3 scripts/gen_detect.py` → `python3 scripts/sync_detect_section.py`。

## L2：怎么测才测得出

| 项 | 内容 |
|---|---|
| 遍历轴 `axes` | shape（shape 维度） / memory（内存） / boundary（边界值） |
| 观测手段 `oracle` | `sanitizer-memcheck` |
| 信号类型 `signal` | `memory` |
| 执行线 `lines` | `memory` |
| 最少用例数 `min_cases` | 4 |
| 造数据 `constructor` | 四类探针：元素数跨 2^31 / indices 取边界负值重复 / 非对齐尾块（末维 31/32/33、尾块非整除）/ 分核数=1、2、实际核数±1；大 shape 需与 tiling 阈值两侧成对构造。 |
| 判据 `judge` | mssanitizer 无越界告警；不出现 aic error / coredump / 数值错位三类症状（避免只报「精度不一致」）。 |
| 判别力 `kill` | 若 int32 承载元素数/地址或偏移符号方向翻转，则元素数跨 2^31 时越界，或尾块数值错位。 |

> 只读 L1 机理卡会产出「不得复现该现象」的空壳用例；按上表 `axes` 铺开、按 `min_cases` 定量、按 `judge` 判成立才算可上板。

## L3：这些 oracle 本身会怎么骗你（判读前必查）

### `sanitizer-memcheck`（共 8 条）

- `K2`（假绿）CANN 自带 .o 的 san 符号数必须实测为 0，否则 memcheck 假绿
- `K28`（假绿）AICPU 算子的 memcheck 是 0 字节空跑，「0 告警」不能读作「无内存异常」
- `K194`（假阳）--heap-check cann 的 illegal free at serialNo:0 是算子执行前误报
- `K427`（假阳）aclnn 直调缓冲的 OOB 判定是 shadow 假象，须阴性对照

---

判 FAIL 前先排除该 oracle 的「假 FAIL」类失效；判 PASS 前先排除「假 PASS / 假绿 / 漏检」类失效。**不查 L3 就报缺陷或报通过，报告作废。**

全文不在本库复制：拿 K 号去 `aclnn-bug-hunt` 的 `references/pitfalls/` grep。本节共引用 8 条 L3 判据。 <!-- END DETECT-SECTION -->