# 消费方式（全量说明）

> 本文件是「怎么用这个库」的**完整说明**；[README.md](../README.md) 只保留一页导航。
> 想尽快开干 → [AGENTS.md](../AGENTS.md)（一页速查）；只有现象 → [TRIAGE.md](../TRIAGE.md)；
> 判定成色与证据纪律 → [EVIDENCE_DISCIPLINE.md](../EVIDENCE_DISCIPLINE.md)；四条不变量 → [INVARIANTS.md](../INVARIANTS.md)。
>
> 章节编号稳定，跨文件按「§N」引用。

---

## 一、取用总览（工作流 + 症状入口 + 渐进披露两段式 + Agent Skill 检视层 + 评测/扫描）

- **按「机理」还是按「判据」取用（v6.17 新增，先用这条分辨你要哪一层）**：库分两层，取错层是用例设计最常见的失效原因。

  | 层 | 回答什么 | 字段 | 谁在用 |
  |---|---|---|---|
  | **L1 机理层** | 为什么会坏 | `applicability` / `mechanism` / `trigger` / `symptom` / `signatures` | 代码审查、静态扫描（`scan_fp.py`） |
  | **L2 判据层** | 怎么测才能测出来 | `detect.axes` / `oracle` / `signal` / `lines` / `min_cases` / `constructor` / `judge` / `kill` | 用例设计（`aclnn-test-design`）、bug 挖掘（`aclnn-bug-hunt`） |
  | **L3 失效模式** | 这个观测手段**本身**会怎么骗你 | `detect_layer.oracle_failures.by_oracle`（按 oracle 类别，69 条实测） | 判读阶段：`FAIL` 是真缺陷还是判据假阳 |

  **只读 L1 会得到什么**：一条「该算子可能存在入库校验参差」的结论，和一句「不得复现该现象」的用例——无法上板。
  **读 L2 才得到**：要遍历哪些轴（`axes`）、靠什么观测（`oracle`：金丝雀 / racecheck / 位比对 / 错误码 / 看门狗…）、
  几条起（`min_cases`）、具体造什么数据（`constructor`）、怎么判成立（`judge`）、以及判别力陈述（`kill`）。
  **但 L2 还有一半没说**：`oracle` 存在 ≠ `oracle` 可信。L3 补的就是这一半——同一个 `golden-utol`，
  在 `inf==inf`、缺 `equal_nan`、容差按 `out` dtype 取这三种情形下都会给出与事实相反的结论
  （实测「396/396 全假 FAIL」）。**判读任何 FAIL 之前，先查对应 oracle 类别的 L3 条目。**
  取用方式：`fault_patterns_index.json` 每条模式的 `detect` 字段 + 顶层 `detect_layer.oracle_failures`；
  真源是 `fault_patterns_detect.json`（勿手改 index，改完真源跑 `python3 scripts/gen_detect.py` 合并）。
  词表见 `fault_patterns_detect.json` 的 `vocab`，守门 **C40** 保证 L2 53/53 齐备、L3 覆盖每个被使用的 oracle 类别且与真源一致。

  **L3 条目不存全文**：每条只有 `id`（`aclnn-bug-hunt` pitfalls 的 K 号）+ `fail` + 一句 `rule`。
  要细节就拿 K 号去 `aclnn-bug-hunt` 里 `grep -rn "## K91" references/pitfalls/`。单向策展，不做双向同步——
  pitfalls 有 2.8 万行全文，双向同步会互相覆盖。

- **按任务选编排（v4.0，推荐入口）**：先看 [workflows/README.md](../workflows/README.md)——新算子准入 → `operator-admission`；只有现象 → `symptom-triage`；迁移/重构 → `migration-audit`；**单跑通过、批跑/复跑/新进程首调才失败** → `stability-soak`（多调用探针矩阵，逼出累积型/间歇性缺陷）；**同一逻辑有多条实现路径、怀疑实现漂移** → `sibling-diff`（兄弟实现对拍）。五条工作流的名单以 `workflows/` 下的文件为准。工作流负责「先跑谁、怎么合并、什么时候停」，单个 skill 只管一条模式怎么查。
- **只有现象、不知道查哪条模式（v3.7）**：先读 [TRIAGE.md](../TRIAGE.md)——按「跑不完 / 报错 / 结果不对 / 不稳 / 慢 / 内存 / 交付」七个后果入口分流，每组给 ≤6 条候选 + 首查动作，再进对应 skill；分诊表只负责收敛候选，命中判定一律以卡片与 skill 为准。
- **LLM 辅助代码审查（推荐）**：
  1. 第一段只读根 [README.md](../README.md)（约 21 KB）：完成「编号 + 名称 + 风险 + 负载 + 触发」级初筛，**先按仓 / 侧别 / 载体用「适用」声明筛选**（不匹配的直接进跳过清单并记理由），圈定候选模式；
  2. 第二段按候选编号**按需**读取 `patterns/FP-X/FP-XX.md` 全卡（单卡约 2~7 KB），对照「源码审查映射点 / 检测签名」逐条分析代码；命中后按「库标准」第 6 条的命中判定流程核验（命中 ≠ 成立），在缺陷报告里标注 `FP-X## 名称`。**v3.4 起缺陷报告建议附 B 轴业务影响评估**（业务可达性 B1~B3 + 业务影响类型 + 处置建议；与 S×O 正交、不改卡片定级，词表见索引 `business_impact`，口径与判例校准见 [skills/README.md](../skills/README.md) 编写规范第 7 条）——卡片路径与 skill 路径产出同规格报告。
  3. 不建议一次性读全部 53 卡：先按「适用」筛选再展开，上下文开销约为全量阅读的 20%。
- **Agent Skill 检视（v3.2 新增，`skills/` 层）**：53 张卡各配一份可执行检视 skill（`skills/FP-X/<skill-name>/SKILL.md`，目录名 = 注册名），把「知识卡」转成「定位实现 → 清单逐项核查 → 判定 → 产出报告」的动作流程。把模式目录（如 `skills/FP-A/fpa05-aclnn-review/`，目录名即注册名）复制到所用 agent 的技能目录即可按 frontmatter 的 `name` / `description` 调起，或人工照其「检视流程」执行；编写规范与 53/53 覆盖表见 [skills/README.md](../skills/README.md)。**v3.4 起每份 skill 的报告层含 B 轴业务影响评估**（业务可达性 B1~B3 + 业务影响类型 + 处置建议矩阵）：与 S×O 正交，只决定修复优先级建议，**不参与 S/O 取值、不改卡片定级**；默认保守（无法证明不可达即记 B3），降档须附证据。
- **签名扫描（v4.5；v6.2 起覆盖 50/53；v6.5 起带上下文约束与注释降噪；v6.10 起可折叠）**：`python3 scripts/scan_fp.py <文件或目录> --only FP-G01 --format json`（存在型；缺失型用 `--absence`、日志型用 `--log`；语料回归用 `--stats --exclude ...`；`--collapse file` 把同模式同子型同文件的候选折成一条并给出合并数与行号样本，`--context 3` 打印候选前后 3 行——大仓里两者配合能把「看几千行」压到「看几百条」）——按索引 `signatures` 生成候选（退出码 1 表示有候选），自带卫生检查与冒烟自检；**默认跳过纯注释行**（`//`、块注释、`.py/.sh` 的 `#`），要复现历史基线时加 `--include-comments`；签名可带 `files` / `within` / `exclude` 约束（结构化对象形态，见库标准第 3 条）。带 `[BROAD]` 标记的候选来自 `broad_signatures`，**只作定位提示**，v6.6 起默认只计数不列出（`--broad list` 才列）。`keywords` 只作审查定位提示、不产生命中。**候选不是结论，未命中也不等于无缺陷**。语料基线（历史 v4.5 时代，口径已不可比）见 [cases/scan-baseline-ops-cv.md](../cases/scan-baseline-ops-cv.md)，当前回归口径看 [cases/sig_yield-ops-math.md](../cases/sig_yield-ops-math.md)。
- **评测（v3.9；v6.4 起带证据级判据）**：`python3 scripts/run_eval.py --validate` 校验 53×3 用例；agent 作答（每个用例一个 `<case-id>.md`，含 `verdict:` 行）放入同一目录后 `--transcripts <dir>` 判分（只判 verdict），加 `--strict` 则同时判 `must_include`（动作 + 证据等级，**全部须命中**）与 `forbidden`（内部单号/本地路径/绝对化断言，**命中任一即扣**），输出准确率、混淆矩阵与「证据不合格数」；`out-of-scope` 池 18 个独立剧本（任一复用 ≤3 次，守门 C36）。协议见 [evals/README.md](../evals/README.md)。
- **报告行号校验（v3.5）**：`python3 scripts/verify_lines.py <报告.md> --root <被检仓根>`——逐条核对报告里的 `文件:行号` 引用（文件存在 / 行号越界 / 空行与纯注释），退出码 0 全通过、1 有错误、3 仅警告；`--self-test` 自带回归。建议报告交付前必跑，未跑须在报告中声明「行号未校验」。
- **真锚回填（v5.6）**：`python3 scripts/gen_cases.py` 另把 v5.4 §「实证加深」实测的**真实修复锚**（`文件:行号 @commit`）机读回填进 [cases/cases.json](../cases/cases.json)——单条案例新增 `verified_anchors`（`[{file, lines, commit, repo, issue, note}]`），顶层新增 `evidence_commits`（`{仓: commit}`）；**抽不到即留空数组、不臆造**，`commit` 为被检仓实测缩写 sha（`ops-cv @79680a9`、`ops-nn`/`ops-math`/`ops-transformer @a7539b`）。守门 C33 增 `verified_anchors` 结构校验（list / `commit` 5-40 位 hex / `file` 合文件正则 / `issue` 在案例 `issues` 内）。schema 见 [cases/README.md](../cases/README.md)。
- **案例库机读化（v5.5）**：[cases/cases.json](../cases/cases.json) 由 `python3 scripts/gen_cases.py`（`--check` 供 CI）从深度档 skill 的「已知缺陷案例库」生成，每条给「触发条件 / 根因 / **可执行判据**（定位锚 `文件:行号` + 检查动作 + 反证排除）」；同步模式（`FP-G02`）案例另含 `paired_primitives`（`set↔wait` 配对，供配对完整性判定）。消费：`python3 scripts/scan_fp.py <文件或目录> --cases ...` 把候选按「同模式 + 同名文件锚」回挂已知案例 `FP-X##-Cn`；[TRIAGE.md](../TRIAGE.md) 在候选模式括号内标注「已立案数」。schema 见 [cases/README.md](../cases/README.md)。
- **子型检索线（v6.3；v6.7 起有判别型）**：`python3 scripts/scan_fp.py --subtypes [--only FP-G02,FP-B07]` 列出模式的子型与判据类型（`pair` 结构判据 / `扫描` 存在型指纹 / `人工`）。22 个模式已机读化 102 条子型：**4 条带存在型指纹**、**2 条带配对结构判据**（`G02-1` SetFlag↔WaitFlag、`G02-3` AllocEventID↔ReleaseEventID），其余靠 skill 清单人工核。扫到子型指纹时输出带 `[G02-3]` 标注，JSON 增 `subtype` 字段；配对判据的候选另带 `counts: {a, b}` 与 `[a=14 b=6]` 标记——**这是唯一能直接指出「哪一对没配平」的判据**（ops-math 实测：G02-1 53 条 / G02-3 7 条，而同类定位型指纹是 2543 条）。**同一条模式从「一个检查项」变成 N 条独立检索线**。
- **签名产出审计（v6.6）**：`python3 scripts/sig_yield.py <语料目录> --md cases/sig_yield-<语料>.md`——逐签名算「命中行 / 命中文件 / density / coverage」，并在**模式级**汇总「用户实际会看到多少条候选」（非宽泛签名命中去重）。用途：识别「一条签名刷屏整个仓」的伪指纹；基线见 [cases/sig_yield-ops-math.md](../cases/sig_yield-ops-math.md)（ops-math，6610 文件去 tests/examples/build 后：51 个模式中 noisy 0 / watch 9 / ok 28 / 显式豁免 14；子型判据见基线第二节（存在型 6 / 配对 2），配对阵据按**失衡文件数**计：G02-1 53、G02-3 7）。被记 noisy 的模式须降量或写 `yield_waiver`（守门 C38）；**子型判据同样纳入基线**，子型产出 >500 条直接报错。
- **人工按表检索**：直接用「总览表」按类别 / 风险 / 负载筛选，再打开对应卡片。
- **一致性守门**：`python3 check_fault_patterns.py [--root <本目录>]`，C1~C50（详见脚本头注释）；单项可单独校验：`python3 scripts/gen_triage.py --check` / `python3 scripts/gen_evals.py --check` / `python3 scripts/gen_cases.py --check` / `python3 scripts/gen_detect.py --check` / `python3 scripts/sync_detect_section.py --check` / `python3 scripts/scan_fp.py --self-test` / `python3 scripts/run_eval.py --validate` / `python3 scripts/score_skills.py --check` / `python3 scripts/test_query_patterns.py`。

  **v6.18.1 补齐的三处「全绿但没查」**（都是先复现再修的）：① **C40 的 L3 原先只比 id 序列**——把某条 `rule` 改成编造内容、id 不动，主守门仍 0 ERROR / 0 WARN；而 `rule` 才是 L3 的全部信息量，现改为逐条 `(id, fail, rule)` 全等，且 D20–D29 结构校验并入守门（不再依赖单独跑 `gen_detect.py`）。② **`pattern_compositions.json` 原先无任何门禁**——成员写错、id 重复、`next_experiment` 结构坏掉都不会报，现由 **C41** 复用 `query_patterns.load_compositions` 校验。③ **工作流把「必须触发」写死成 4 条**——而索引已增至 6 条，`FP-A22` / `FP-G02` 在准入体检中被整段漏检，现由 **C43** 核 `Stage 1` 表格与索引一致。
- **组合故障与未知候选（v6.18）**：`python3 scripts/query_patterns.py --hits FP-A05,FP-A21` 按**命中集合**取组合（只返回 `members` 全部命中的组合，不做文本相似度推断），并给出可直接执行的 `next_experiment`（`deep-experiment/v1`：actions / schedule / oracle / observations）。`--failure <json>` 在**无任何已知模式命中**时产出 `unknown-pattern` 候选——**只在全无命中时保留**，已有任一命中则不产出残余候选，这一限定是刻意的（避免把已定界问题重新拆散），但也意味着「多机理叠加且含未知成分」的场景需自行补记未覆盖部分。
- **L2/L3 进技能（v6.18.1）**：`python3 scripts/sync_detect_section.py` 把每模式 `detect`（L2）与所涉 oracle 的失效条目（L3）接到深度档技能上——**`SKILL.md` 只写指针段**（约 0.7 KB：轴 / 观测 / 最少用例数 + 每个 oracle 一句关键失效），**完整判据落 `references/detect-l2-l3.md`**。两份都是生成物、**勿手改**；**C42** 双校验（指针段与 references 均与索引逐字一致）。之所以不内联：`score_skills.py` 的 `fit` 按体积打分，内联 2.9 KB 会把 8 份技能顶过 36 KB、PASS 从 20 掉到 19。此前的状态是「L2/L3 只在 JSON 里，53 份技能一份都没引用」，Agent 走 `workflows → skills` 根本读不到。

### v6.19：三条「能不能真挖到深 bug」的基础设施

这一版不新增模式，只补**方法层**。起因是一次自问：这个库现在能发现什么，结构上又**不可能**发现什么？

- **第二 oracle（`fault_patterns_secondary_oracle.json`，C44）**：实测 **29/53 条模式只有单一判据**。单点判据的根本问题不是「不准」，而是**错了没人知道**——返回码对但错误码选错、racecheck 零告警但连接口都没进 kernel，这类「正确且错误」在单判据下不可见。第二判据的**唯一硬要求是机理独立**：同面判据（如主判据 `golden-utol`、第二判据又是数值比对）只是让概率看起来更好看。当前 **24 模式 / 45 条关系，高优先级 20/20 全覆盖**，类型分布 cross-path 9 / idempotence 7 / invariant 8。跨路径差分（aclnn vs aclop/GEIR、单算子 vs 图模式）、重放幂等、边界哨兵这三类是最有杀伤力的，因为它们**不依赖 golden**。
- **锚点可复算性（`check_anchors.py`）**：`verified_anchors` 是「这条缺陷当时真这样修」的证据，但上游持续重构会让它**静默失效**。本工具做两层核验，**commit 层优先**：声明的 sha 是否真在该仓（`COMMIT_MISSING` = 跨仓错用）、该 commit 树里是否真有此文件（`AT_COMMIT_ABSENT`），再看 HEAD 是否还在（`FAIL`/`DRIFT`）。**实测发现 31 个锚里 11 个不可信**（10 个把 ops-nn 的 `a7539b` 套用到 ops-math/ops-transformer，1 个指向不存在的文件）——现已全部修正或降级，**29/29 可信率 100%**。
- **变异测试（`mutate_ops.py`）**：「找不到 ≠ 没有」这条纪律正确但**不可证伪**。变异测试注入语义已知变化，看检视手段能否抓住：抓不住说明**判据本身不行**，而不是算子没问题。**20 条变异算子**全部从既有模式/L3 派生（`from_pattern` / `from_l3`），覆盖 **17 个模式**。

  **v6.20 关键修正：kill rate 必须分层，否则数字无意义。** 变异能否被抓取决于判据在哪一层——`static`（形态层：token 出现/消失/配平，静态本该判）与 `dynamic`（语义层：比较方向、默认值、索引指向，静态原理上判不了）。**分层是逐变异算子的属性**（`MUTATORS` 的 `detectable_by` 字段，缺省保守判 dynamic）：当前 20 条变异算子中 static 13 / dynamic 7。混在一起算会得到「看起来很差但归因错误」的结论。现在输出三个数：

  | 指标 | 实测（ops-nn，20 条算子，v6.20 原口径） | 含义 |
  |---|---|---|
  | `static_kill` | **80.0%**（注入 60 / 抓住 48） | 形态层真指标，**这是改进目标** |
  | `dynamic_gap` | 50%（注入 50 / 抓不到 25） | **层级事实，不是缺陷**，必须上板 |
  | `known_miss` | 5 类（M03/M12/M14/M16/M19） | 显式声明的正则能力边界，单列披露 |

  **v6.21 已改判定口径（上表三个数保留 v6.20 原值，用于对照口径差）**：kill 判定由「有候选」改为「变异前后候选指纹不同」，同一批算子的 `static_kill` 修正为 **96.2%**（注入 80 / 抓住 77）；`M18` 的归属修错（改 `ACLNN_ERR_PARAM_NULLPTR` 属 FP-B04 而非 FP-B11）后 6/6。逐条见 [CHANGELOG.md](../CHANGELOG.md) v6.21 条。

  **三条如实记录的盲区**（都写进 `observed_gap`，未改标粉饰）：
  ① **M02 判空取反 0/10**——FP-B04 签名全是存在型，`OP_CHECK_NULL` 取反后 token 一个不少，**存在型签名无法反映语义正确性**。
  ② **M11 删 SetAtomicAdd 仅 3/10**——逐例复查 7 个未捕获样本，**每个文件都残留 2~5 个同类 token**，故存在型签名照旧命中。这是「存在型 vs 计数配平」的结构性局限，要判「少了一处」必须做出现次数配平，当前扫描器不支持。
  ③ **M12/M14 0/10**——定序原语与模板注册的缺失属**跨文件配平**，文件级规则无法表达。曾尝试补 absence 判据，实测命中率 93/96 与 39/60（远超 noisy 阈值），**已撤销**并改在 `detectors` 里写明「当前无自动判据」，而不是留一个 97% 命中的假判据。

  唯一保留的 absence 补强：**FP-A06**（`files: op_kernel`，`when: AtomicAdd<`），ops-nn 命中 7/164（4.3%）、ops-math 6/46（13%），属可用范围。

- **CI（`.gitlab-ci.yml` + `scripts/ci_gate.py`）**：C1–C50 一直在，但**没有任何机制保证它被跑**——上面 11 个失效锚就是「门禁全绿但资产已烂」的实证。现在 `python3 scripts/ci_gate.py` 一条命令跑完全部 24 项（23 个 blocking + 1 个 advisory），CI 与本地**同源同一份清单**，避免「CI 绿了但本地口径不同」。`blocking` 项（23 个）必须全绿才能合；`advisory`（锚点存活率，依赖算子仓是否挂载）默认不阻断，本地有仓时会真跑。