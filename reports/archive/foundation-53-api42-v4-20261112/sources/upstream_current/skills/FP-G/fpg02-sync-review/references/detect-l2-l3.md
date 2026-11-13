# FP-G02 判据层：L2 怎么测 / L3 会怎么骗你

> 由 `scripts/sync_detect_section.py` 从 `fault_patterns_index.json` 生成，**勿手改**；守门 **C42** 校验与索引逐字一致。
> 改判据：真源 `fault_patterns_detect.json` → `python3 scripts/gen_detect.py` → `python3 scripts/sync_detect_section.py`。

## L2：怎么测才测得出

| 项 | 内容 |
|---|---|
| 遍历轴 `axes` | concurrency（并发/同步） / sequence（执行序列） / memory（内存） |
| 观测手段 `oracle` | `sanitizer-racecheck` / `bitwise` |
| 信号类型 `signal` | `concurrency` |
| 执行线 `lines` | `memory` / `multithread-fuzz` / `determinism` |
| 最少用例数 `min_cases` | 4 |
| 造数据 `constructor` | mssanitizer racecheck 零告警门禁；同步原语 set/wait 配平静态统计；事件 ID 池审计（Alloc/Release 成对、申请不在循环体内、常量互异）；双 AIV/多核共享 workspace 单独成类；批跑轮换 + 新进程首调。 |
| 判据 `judge` | racecheck 零告警；set/wait 次数与分支都配平；AllocEventID 与 ReleaseEventID 成对且 ID 两两互异。 |
| 判别力 `kill` | 若 SetFlag/WaitFlag 未配平或跨核覆盖不全，则 racecheck 报 WAW/RAW，或批跑轮换下偶现结果错而单跑首次通过。 |

> 只读 L1 机理卡会产出「不得复现该现象」的空壳用例；按上表 `axes` 铺开、按 `min_cases` 定量、按 `judge` 判成立才算可上板。

## L3：这些 oracle 本身会怎么骗你（判读前必查）

### `sanitizer-racecheck`（共 4 条）

- `K2`（假绿）san 符号数必须实测为 0，否则 racecheck 同样假绿
- `K28`（假绿）AICPU 算子的插桩是空跑，「0 告警」不等于无竞争
- **注意**：该类目前未登记「假 FAIL」侧——不代表该方向不存在，实测踩到后请回补 L3（D29 只要求全库两类都覆盖，不强制每类双向）。

### `bitwise`（共 4 条）

- `K638`（假 FAIL）+inf 的 log-sigmoid 输出是 -0.0：按位比对必须先归一符号零
- `K1189`（假 FAIL）mtfuzz 的 none 腿对重叠累加算子刷出上千假 FAIL，判据只看 acl 腿
- **注意**：该类目前未登记「假 PASS / 假绿」侧——不代表该方向不存在，实测踩到后请回补 L3（D29 只要求全库两类都覆盖，不强制每类双向）。

---

判 FAIL 前先排除该 oracle 的「假 FAIL」类失效；判 PASS 前先排除「假 PASS / 假绿 / 漏检」类失效。**不查 L3 就报缺陷或报通过，报告作废。**

全文不在本库复制：拿 K 号去 `aclnn-bug-hunt` 的 `references/pitfalls/` grep。本节共引用 8 条 L3 判据。 <!-- END DETECT-SECTION -->