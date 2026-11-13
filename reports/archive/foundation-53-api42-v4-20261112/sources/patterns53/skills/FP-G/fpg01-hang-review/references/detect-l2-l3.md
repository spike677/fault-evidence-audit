# FP-G01 判据层：L2 怎么测 / L3 会怎么骗你

> 由 `scripts/sync_detect_section.py` 从 `fault_patterns_index.json` 生成，**勿手改**；守门 **C42** 校验与索引逐字一致。
> 改判据：真源 `fault_patterns_detect.json` → `python3 scripts/gen_detect.py` → `python3 scripts/sync_detect_section.py`。

## L2：怎么测才测得出

| 项 | 内容 |
|---|---|
| 遍历轴 `axes` | shape（shape 维度） / concurrency（并发/同步） |
| 观测手段 `oracle` | `watchdog` |
| 信号类型 `signal` | `hang` |
| 执行线 `lines` | `error-scenario` / `multithread-fuzz` |
| 最少用例数 `min_cases` | 3 |
| 造数据 `constructor` | 单用例硬超时（如 10 分钟）转失败并 dump 堆栈；UT 执行顺序随机化；边界输入探针 rank-0 / 空 tensor / 退化 shape 单独成类；超时配置边界（>2^32 微秒、负值）。 |
| 判据 `judge` | 单用例在硬超时内返回；超时转失败而非挂起（断言「不返回」而不仅断言精度）。 |
| 判别力 `kill` | 若循环推进变量缺失或上界回绕，则用例不返回直至硬超时，而精度比对根本走不到。 |

> 只读 L1 机理卡会产出「不得复现该现象」的空壳用例；按上表 `axes` 铺开、按 `min_cases` 定量、按 `judge` 判成立才算可上板。

## L3：这些 oracle 本身会怎么骗你（判读前必查）

### `watchdog`（共 7 条）

- `K1061`（静默漏判）子进程超时口径大于外层预算 → 子进程白跑、结果不落盘
- `K523`（假通过）started>0 且无 finished ≠ 通过（大 kernel 被 SIGKILL）
- **注意**：该类目前未登记「假 FAIL」侧——不代表该方向不存在，实测踩到后请回补 L3（D29 只要求全库两类都覆盖，不强制每类双向）。

---

判 FAIL 前先排除该 oracle 的「假 FAIL」类失效；判 PASS 前先排除「假 PASS / 假绿 / 漏检」类失效。**不查 L3 就报缺陷或报通过，报告作废。**

全文不在本库复制：拿 K 号去 `aclnn-bug-hunt` 的 `references/pitfalls/` grep。本节共引用 7 条 L3 判据。 <!-- END DETECT-SECTION -->