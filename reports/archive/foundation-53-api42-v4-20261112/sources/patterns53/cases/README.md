# cases/ 目录（案例库 cases.json + 误判台账 misjudgments.jsonl）

## 案例库 cases.json（机读，v5.6）

> **这是什么**：把深度档 skill 里**人读**的「已知缺陷案例库」（v5.1）与「实证加深」（v5.4）的「反向排除项 / 真实修复锚」，抽成**机读**的案例表，供 `scan_fp.py --cases`（候选回挂已知案例）与分诊表（标注已立案数）消费。
> **生成**：`python3 scripts/gen_cases.py`（`--check` 供 CI）从 `skills/FP-*/*/SKILL.md` 抽取；**只做抽取与结构化，不新增任何 issue 编号 / 行号 / 路径**，由守门 **C33** 校验（字段齐全 / `library_version` == 索引版本 / 深度档全覆盖 / 真锚 `verified_anchors` 结构合法 / 案例 issue 回链卡片语料）。

### 顶层字段

| 字段 | 说明 |
|---|---|
| `schema_version` | 本表结构版本（`1.0`） |
| `library_version` | 生成时的库版本，须 == `fault_patterns_index.json` 的 `version`（C33） |
| `updated` | 与索引 `updated` 同源 |
| `generated_by` | 固定 `scripts/gen_cases.py` |
| `evidence_commits` | **真锚回填（v5.6）**：`{仓: 实测 commit 缩写 sha}`，全表真实锚的取证基线（如 `{"ops-cv": "79680a9", "ops-nn": "a7539b"}`）；取自各 skill「实证加深」节的 `@<sha>` |
| `sync_pairs` | **同步模式（FP-G02）专属**：规范配对表（`SetFlag↔WaitFlag` / `AllocEventID↔ReleaseEventID` / `CrossCoreSetFlag↔CrossCoreWaitFlag` / `SyncAll↔SetScheduleMode(1)`），取自 `patterns/FP-G/FP-G02.md` |
| `reverse_exclusions` | 按模式给出「反向排除项 → 所需负向证据」，取自 skill 的 `### N.M 反向排除项` 表 |
| `stats` | 计数：`total` / `depth_patterns` / `by_fp` / `with_issue` / `with_verified_anchor` / `verified_anchors` / `sync_cases` |
| `cases` | 案例数组，见下 |

### 单条案例字段

| 字段 | 说明 |
|---|---|
| `case_id` | `FP-X##-Cn`，全表唯一；`n` 为 skill 中的「案例 n」序号 |
| `fp_id` / `skill` | 归属模式与 skill 注册名 |
| `title` / `subtype` | 案例标题；若标题含「子型①」则记 `subtype` |
| `trigger` | 触发条件 |
| `root_cause` | 根因（含 `文件:行号` 定位锚） |
| `criteria` | **可执行判据**：`locators`（`{file, lines}` 定位锚，机读可比对）+ `check`（「针对性发现」按 ①②③ 拆成的检查动作） |
| `fix_pattern` / `fix_pattern_code` | 修复范式文字 + 代码围栏（**无真实修复来源者标注「示意」**） |
| `min_repro` | 最小复现锚 |
| `evidence` / `issues` | 实证文字 + 提取出的 `#NNN`（回链由 C33 校验） |
| `verified_anchors` | **真锚回填（v5.6）**：`[{file, lines, commit, repo, issue, note}]`——取自该 skill「实证加深」§N.1 的**真实修复锚**（`文件:行号 @commit`）；`issue` 为命中的 `#NNN`，`note` 为该行要点列。**抽不到即空数组**（该案例的修复码仍为「示意」），C33 校验其结构合法（`commit` 5-40 位 hex / `file` 合文件正则 / `issue` 在案例 `issues` 内） |
| `paired_primitives` | **仅同步模式（`FP-G02`）案例**：与本案例相关的 `set↔wait` 配对（`{a, b, kind, source}`；`kind` ∈ `event` / `event_id` / `cross_core` / `schedule` / `same_pipe_barrier`）。**空数组表示该案例的缺陷形态是「缺失同步」而非「某对原语不配平」**，其判据见 `criteria` |
| `merge_rule` | **告警→根因簇的归并规则**（v6.15 新增，v1.0）。记录「N 条 racecheck/memcheck 告警如何收敛为 M 个根因」的判据，供报告阶段自动聚类。结构见下节。**空对象表示该案例尚无归并实证** |

#### `merge_rule` 结构（v6.15）

一条 sanitizer 报告的价值不在告警条数，而在**根因簇数**。同一根因会由一个 buffer 上的
一组同址访问反复触发，产生多条措辞相似的告警；若按条数派工，同一根因会被拆给多人。
本字段把这套归并判据机读化。

| 键 | 说明 |
|---|---|
| `alarm_count` | 归并前的原始告警条数（如 `6`） |
| `cluster_count` | 归并后的根因簇数（如 `2`） |
| `keys` | 归并键，**按序生效**（先命中者先合簇）：`address`（告警地址相同）/ `file_line_pair`（两侧 `文件:行号` 相同）/ `pipe_pair`（pipe 对相同，如 `MTE2↔V`）/ `event_domain`（`HardEvent::X` 相同）/ `buffer_symbol`（源码中同名的 buffer 变量） |
| `evidence` | 一条真实案例的原文摘录（脱敏后的告警块），用于回归比对 |

**归并示例（`#12578`：6 条告警 → 2 类根因）**：

```json
{
  "alarm_count": 6,
  "cluster_count": 2,
  "keys": ["address", "pipe_pair"],
  "evidence": "stage1PingBuf 上 V-V 同址：PipeBarrier<PIPE_V> 缺失簇；commonTBuf 上 MTE2 复用：V_MTE2 事件边缺失簇"
}
```

> **口径**：`alarm_count / cluster_count` 之比是该案例的「归并收益」。汇报时应给
> **簇数**（2 类根因）而非条数（6 条告警）——后者会把同一根因重复计数。

### 消费

- `python3 scripts/scan_fp.py <文件或目录> --cases --format json`：候选按「同模式 + 同名文件锚（basename）」回挂已知案例，输出 `known_cases` 字段（文本模式标 `[CASE FP-X##-Cn]`）。**回挂 ≠ 判成立**，仍须按对应 skill 第 7 节走正负证据判定。
- `python3 scripts/gen_triage.py`：分诊表在候选模式括号内标注「，N 案」（该模式已立案数）。
- 手工：按 `stats.by_fp` 取某模式的全部已知案例及其定位锚。

---

## 签名产出基线（sig_yield-<语料>.json/.md，v6.6）

> **生成物，勿手改**：`python3 scripts/sig_yield.py <语料目录> --json cases/sig_yield-<语料>.json --md cases/sig_yield-<语料>.md`。

记录「每条签名在这份语料上实际产出多少候选」，用来抓**匹配一切的伪指纹**：

- `entries[]`：逐签名 `{pattern, signature, hits, files_hit, density, coverage, verdict}`；
- `subtypes[]`：子型级 `{pattern, subtype, kind: sig|pair, candidates, files_hit, verdict}`（v6.8）——
  配对判据按**失衡文件数**计候选，这是它实际产出的条数；
- `patterns[]`：模式级 `{pattern, candidates, broad_hits, n_signatures, verdict, waiver}`——
  `candidates` 是**非宽泛签名命中的行去重**，即消费方真正会看到的候选数；
- 守门 **C38**：每条非宽泛签名都必须能在基线里找到记录（改签名不重跑审计即报错）、基线判 `noisy` 的模式必须有 `yield_waiver`。

当前基线：`sig_yield-ops-math.json/.md`（6610 文件 / 118 条签名 / 9 条子型判据 / 51 个模式；noisy 0 · watch 9 · ok 28 · 豁免 14）。

# 误判台账（cases/misjudgments.jsonl）

> **这是什么**：记录检视过程中**被推翻的判断**——不是记录缺陷，而是记录"我们曾经怎么想错了"。
> 目的：让同一类误判不在不同接口上重复发生，并为判定标准（SKILL 第 7 节）提供可追溯的修订依据。
> **格式**：JSON Lines，每行一条，UTF-8，字段固定；由守门脚本 **C19d** 校验。

## 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | 是 | `MJ-YYYYMMDD-NN`，全库唯一，一经分配不复用 |
| `date` | 是 | 发现日期，`YYYY-MM-DD` |
| `fp_id` | 是 | 归属模式编号（必须在库内存在，如 `FP-B03`） |
| `type` | 是 | 误判类型，见下表枚举 |
| `claim` | 是 | 当时的主张（如「拟升 O3」「判为命中」） |
| `evidence` | 是 | 推翻它的证据：公开 issue/PR 编号、`[文件]:[行号]`、实测输出；**禁止内部缺陷单号与本地路径** |
| `correction` | 是 | 修正后的结论（档位、判定、或判定标准的新增防线） |
| `status` | 是 | `已关闭` / `观察中` / `已升级为防线` |
| `source` | 是 | 出处（CHANGELOG 条目、复扫批次、报告文件名） |

## 误判类型枚举

`实证重复计数`（同一 issue/PR 被算作多条独立实证）｜`机理误归`（判到了相邻模式）｜`证据不足即命中`（推导链缺环即出卡）｜`相邻模式误判`（边界表未覆盖的第三种情形）｜`三方漂移`（卡片/总览/索引不一致）｜`行号失真`（引用偏移或不存在）｜`其他`（须在 `correction` 说明）

## 登记时机（三条硬规则）

1. **每次检视报告必须写「Agent 误判记录」**：本次被推翻的假设 + 推翻证据；无推翻写「无」。报告级记录是台账的原料。
2. **同类误判在 3 次检视中重复出现** → 必须登记台账，并在对应 SKILL 第 7 节新增一条防线（不是改卡片正文，除非机理判断本身错了）。
3. **台账不是垃圾桶**：只登记"改变了结论"的误判；措辞含混、证据不足但未改判的不登记（它们在报告里作为观察项存在）。

## 与其它机制的关系

- **S×O 定级**：实证重复计数类误判直接改 O 值与风险档，须按定级纪律三方同步（卡片 / 总览 / 索引）并在 CHANGELOG 登记。
- **守门 C19d**：校验每行 JSON 可解析、字段齐全、`fp_id` 在库内、`type`/`status` 在枚举内、`id` 唯一且格式合法。
- **季度回顾**：把 `type` 的分布作为"哪类判断最容易错"的体检指标；`已升级为防线` 的条目应能在对应 SKILL 第 7 节找到对应措辞。
