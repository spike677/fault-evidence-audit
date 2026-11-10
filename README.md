# Fault Evidence Audit

0.1.20定向修复Baseline协议：A1由程序物化原始SOURCE_RECORD，模型只选source_id及字段用途；A2保留三级事实门禁，增加正确/错误示例和具体ID反馈；A3明确稀疏UNKNOWN、特定排除与全轴非API依赖。历史UNKNOWN不能通过REUSE升级。完整原请求与同任务纠错上下文共同检查预算，旧attempt和进程日志保留。已完成A2/A3/A4只有依赖未变且通过当前Validator时才只读复用，旧Policy不改写，旧请求不可继续提交。升级及隔离复测见[SCHEMA_REMEDIATION.md](integration/SCHEMA_REMEDIATION.md)。现场真实OpenCode回放仍需单独验收，不自动ACCEPT、冻结或重采已有证据。

0.1.19修复原run的Baseline恢复：`pin-budget`固定历史160000预算，规划/提交/查询使用同一run配置；A1由程序来源清单绑定真实字段/坐标；`baseline_compatibility`要求Agent逐字段复核历史，结构通过不自动转当前结果。旧响应、旧Policy和人工历史保留，分类依赖每模式选用的一份技术定义，证据清单变化只重做必要阶段。`recovery-plan`提供只读进度和卡点，原30模式的A2/A3/A4应覆盖90个阶段单元。升级和续跑见[BASELINE_RECOVERY.md](integration/BASELINE_RECOVERY.md)，测试记录见[恢复验证回执](examples/baseline_recovery_validation.json)。本版不改42/V4、不扩展Bridge，不自动入库或启动现场drive。

0.1.18新增独立`precision-bridge`：只读导出当前有效的READY Baseline，生成完整输入预算检查的绑定任务，保存ATK规则到模式/原42/V4/E1–E5的溯源并运行原生格式/JSON校验。已知模式验证与盲测分开；WARNING逐项保留，CODE-only有依据时走非API路径，E协议通过只表示设计结构完成。它不修改PrecisionTesting的原tasks/Prompt/知识库，不写现场state，不运行设备或自动入库。命令和验收口径见[Bridge说明](integration/PRECISION_BRIDGE.md)。已完成30项Bridge合成测试、159项保留定向回归，以及真实上游三个校验器的合成smoke；具体提交、范围和限制见[验证回执](examples/precision_bridge_validation.json)。

0.1.17先维护原30条CANN Baseline：A1整理原定义及独立的`failure_mechanism`，A2归类V4条件/构造，A3独立归类原始42条API条件，A4整理E1–E5与证据/实机缺口，最后完成六维横向审查并显式冻结Baseline v1。原42从实际文件解析核对并记录路径、SHA-256及全部ID/名称/定义；原始知识库不改，不使用V5修订42，不等待缺失映射文件，不自动转换标签。没有历史Wiki不阻塞定义和条件分类，也不因此声称来源或硬件已验证。复用已有子agent和文件桥接，主要入口为HTML，交付四份指定文件。见[现场接续说明](integration/OPENCODE_HANDOFF.md)；本轮只做部分验证，尚未代替OpenCode完成原30条实际语义分类。

故障证据核验核心。核心测试使用合成数据，`examples/` 另保留不含原文的实机聚合验收记录；用户指定发布的模式库草案单独存放在 [`catalog/drafts/`](catalog/drafts/README.md)，与测试数据及正式库分开。

当前版本 0.1.20，2026 年 11 月 10 日。核心负责导入故障表、保存原文与引用来源、规划必要证据、生成采集和模型任务、检查返回结果并生成复核报告。模型任务可由 OpenCode 或 Codex 会话执行，内网采集仍由具备授权与登录态的现场环境完成。支持文件交接及外部 Agent 命令适配，不包含直连模型或网站的网络客户端。

V5首批接入：CLI的`trigger-workflow init`默认使用`SPARSE_SCENARIOS_V5`合同，完整提供冻结规则，但模型仅返回有依据的类别和所选构造，不再生成42/31条UNKNOWN矩阵。每个正向标签必须通过`label_links`关联规则版本、机理明细、事实和本地情景。未选项是NOT_ASSESSED，部分适用不变成强MATCH；正式入库与人工ACCEPT门禁不变。既有Python API默认保留旧合同兼容，使用`sparse=True`启用V5；CLI仅在明确`--legacy-dense`时使用旧合同。

主报告改为`report.html`，同目录`report.json`保留完整当前审计投影；旧原文、响应和裁决继续保存在state。组合统计区分精确已记录集合、包含式同案交集和同情景交集；按mode_id/case_id、规则版本及描述/证据确认轴分开去重。旧结果缺情景时不推断同情景。HTML支持搜索、组合反查、原定义/机理/引用/未知展开。`export --xlsx`才额外生成四表索引。设计任务默认不阻塞V5分类，确需已有设计阶段时在Init/configure-v5加`--with-designs`；设计卡须绑定一个情景，仍未设备执行。

本轮按用户要求先上传代码，只做定向验证与原30条输入/派发前置检查；不运行完整回归或Codex语义端到端，不开始62条候选。旧版本696项回归不能当作本版通过。当前状态见[部分验证记录](examples/v5_partial_validation.json)。候选全集重新发现、根因分层和现场30条语义验收仍需后续执行，不能以稀疏标签数量代替技术正确性。

升级先备份state与任务目录。对原Init执行`trigger-workflow configure-v5 --run INIT_RUN_ID`，然后沿用`next/submit/drive`及原生子Agent。合同/策略变化使旧结果失效，历史不删、不继承ACCEPT；完成原30条语义验收并finalize新基线后，才建立关联增量运行处理62条。不要把旧15项聊天目录试验替代原30条库。

0.1.15历史接入范围为“V4分类规则修订＋用例设计规程”。V4的31类、55种唯一构造、64次挂载、195个指导案例分别冻结；原42定义、修订42边界及解释映射独立保留，映射不传递适用性或覆盖结论。旧密集合同继续兼容；V5不改这些分类定义。E1—E5及跨流生产—消费仍仅生成设计，执行结果为NOT_RUN，未实现设备、线程或多rank执行器。

初始化时显式提供已核对的原42与V4文件；仓库knowledge/下已保存两份授权原文，Init内容仍不提交：

完整V4、修订42、响应schema及机制目录通常超过默认48,000字符预算。新Init用`--input-budget`固定预算，或在启动前设置`FAULTAUDIT_MAX_INPUT_CHARS`作为初始值；已有run用`pin-budget`固定其历史请求一致使用的预算。分类、设计、提交和导出读取run固定值，不再依赖每个终端环境；旧请求身份校验仍保留。本轮Codex隔离试验使用240,000字符，不代表现场模型已具备相同容量。保留默认值时，超限任务会如实阻塞。

```powershell
python run_faultaudit.py --state .faultaudit trigger-workflow init `
  --modes '原机制库.xlsx' --taxonomy '原trigger_library.md' --v4 '实际V4.md' `
  --basis SOURCE_DEFINITIONS --work-root work/runs --executor opencode
# 已有Init在备份后维护版本化定义；旧基线和响应保留。
python run_faultaudit.py --state .faultaudit trigger-workflow configure-v4 `
  --run INIT_RUN_ID --source '实际V4.md'
```

`next/submit/drive`自动衔接分类与设计任务。若有实际执行器能力声明，可在`init`或`configure-v4`增加`--capabilities-file`；文件只声明能力，不能当执行记录。示例结构为`{"provenance":"实际能力检查来源","classes":{"T1":{"construction":"BLOCKED","reason":"实际入口自动连续化"}},"methods":{}}`。预算仍检查完整序列化请求，默认48,000字符；超限明确阻塞，不删减31类定义或修订42条。

0.1.14 将 42 项输入触发条件与 Branch 2/3 作为主要分类框架，先分类条件，再整理机理和对照原库。原文声明归类与资料确认分开；保留 0.1.13 的来源定义 Init、采集、独立摘要和模型文件协议。完整回归和本轮实机结果见[验收记录](VALIDATION.md)，异机续跑见[交接说明](integration/OPENCODE_HANDOFF.md)。此前 0.1.12 的 25+5 停止点保留在[历史验证报告](reports/pilot-25plus5-20261106.xlsx)。公开仓库不包含本轮 Init、私有运行状态或原始响应。

## 结构化 XLSX 全流程（本轮默认入口）

`xlsx-workflow` 负责 Wiki 优先、采集与模型任务推进、模式归类和整体故障排名。默认交付一个 `故障整理及模式库建议.xlsx`，包含排名、来源与证据、事实对照、模式库建议、异常与待处理、运行统计。前三列固定“排名、原编号、case_id”，保留文件、Sheet、Excel 行、单元格和原始归因；事实对照保留两侧值与含义、原单元格和快照引文。排名是明确的整理优先级，不冒充故障严重程度。

```powershell
$PythonExe = 'python' # 使用具备 requirements.txt 依赖的实际解释器
& $PythonExe run_faultaudit.py --state .faultaudit xlsx-workflow start `
  --input '实际结构化故障表.xlsx' --catalog '实际原始模式库.xlsx' `
  --expected-catalog-count 30 --work-root work/runs --executor opencode
# 使用上一步返回的明确 run_id；库数量按实际冻结原库填写，不固定为30。
& $PythonExe run_faultaudit.py --state .faultaudit xlsx-workflow next --run RUN_ID
```

`next` 返回按 Wiki 优先排列的任务及准确的 `request`、`response` 路径。OpenChamber/OpenCode 读取完整请求，使用其已有网站工具或模型执行，把响应写到返回路径后提交；程序继续解锁下一阶段，不要求用户手工组织阶段文件。

来源类型沿用导入器的 `LEGACY_TABLE` 默认；确为原始周报/OBP 时显式指定 `--source-kind ORIGINAL_WEEKLY` 或 `ORIGINAL_OBP`。三类已有链接都直接进入整理，不将普通汇总表自动标成原始周报。

工作流冻结本次输入的 case 集合。已有混合 run 可在首次 start 时传 `--run RUN_ID --case-ids-file '目标case_id数组.json'`，目标范围贯穿计划、抓取、模型、校验与导出；历史记录留在原账本。范围确定后同批续跑不能改为另一个集合，换范围或不兼容的冻结库时建立明确关联的后续 run。空数组会拒绝，不会扩展为全库。

```powershell
& $PythonExe run_faultaudit.py --state .faultaudit xlsx-workflow submit --run RUN_ID `
  --task-id TASK_ID --response 'next返回的response路径'
# 循环 next/submit，直到 READY_TO_EXPORT；再生成唯一交付文件。
& $PythonExe run_faultaudit.py --state .faultaudit xlsx-workflow export --run RUN_ID
```

已具备现场 Agent 命令适配器时，使用 `drive` 自动循环并导出：

```powershell
& $PythonExe run_faultaudit.py --state .faultaudit xlsx-workflow drive --run RUN_ID `
  --agent-command-file '实际Agent命令配置.json' --workers 2 --max-attempts 2 `
  --timeout 1000 --browser-timeout 1000
```

配置是 argv JSON 数组，例如 `["实际解释器绝对路径", "现场适配脚本绝对路径", "{request}", "{response}"]`。程序以 `shell=False` 替换两个绝对文件路径，适配器按请求类型调用现场工具/模型并写响应；不是声称 OpenCode 原生命令支持这些参数。也可由 OpenChamber 会话直接循环调用 `next/submit`，无需进程适配器。

0.1.11 提供实际的 [OpenCode CLI 适配脚本](scripts/run_opencode_agent.py) 和项目 `fault-audit-worker` Agent；安装方式、预检及命令配置见[现场接入说明](integration/OPENCODE_HANDOFF.md)。OpenChamber/OpenCode 支持原生子 Agent 与 Agent 搜索：可由现场主会话按任务启动独立子 Agent，或由驱动每次调用新 OpenCode run。主会话只接收 ID/状态/响应路径，不积累全部正文。具体工具与 Edge 登录态仍须现场验证。

驱动连续处理整批，无每十条确认边界。默认两个语义 worker（可设 1–4），浏览器单队列；只有协调器写 SQLite。单项失败有限重试，其他任务继续；同站点登录等待集中交接，用户手动完成 Edge 登录后对对应 collection task 执行 `retry` 再续跑。文件、旧尝试和历史结果保留，OS 运行锁防止同 run 被两个驱动并发执行。

页面采集使用 `capture_observation` 保留请求/最终 URL、页面类型、正文位置和精确引文。标题、目录、登录或未渲染页面不能声明完整正文；目录可在 `linked_packages` 返回带父页导航引文及适用 case IDs 的子页，保留 `LINK_DISCOVERED` 来源并单独核验。补读有上限，明确网络阻塞不会自动反复抓取。搜索由 Agent 提取原单元格事实并按实际结果扩展，`search_facets/search_attempts` 留存来源、查询及轮次；不在核心生成固定搜索词。

每组摘要及每个 `work_id` 独立上下文。同快照/同策略共享摘要，支持所有分组同时就绪，全部组齐备才有完整摘要。模型请求正文只序列化一次为 `segments[].text`；草案的重复引文按身份引用，完整冻结库及独立事实仍保留。整请求预算默认 48,000 字符，现场按真实模型容量显式设置 `FAULTAUDIT_MAX_INPUT_CHARS`；字符数不等于 token 数，不能自动抬预算或删条目。执行者读不全时返回外层哈希绑定的 `BLOCKED/EXECUTOR_CONTEXT_LIMIT`，不产生模型成功记录；改善执行容量后可显式 `retry`。策略或语义输入改变则重发新任务，不能重绑旧答案。

原 Wiki 优先读取、不再重复补搜；没有 Wiki 时，即使已有 PR 也必须执行有范围的 Wiki 检查。`NO_MATCH` 留存查询后允许处理其他证据；登录失败保持 `BLOCKED`。已有引用全部整理，默认一份可用证据满足后停止新增搜索。需要重试访问时用 `xlsx-workflow retry --run RUN_ID --task-id TASK_ID`，保留旧响应。

工作文件固定在 `work/runs/<run_id>/tasks/<task_id>/request.json` 和 `attempt-<n>/response.json`，最终输出为 `work/runs/<run_id>/output/故障整理及模式库建议.xlsx`；摘要、Wiki 检查及判断保存在原 state，证据原文仍用现有 snapshots。导出用的临时 JSON/预览在完成后清理，不默认另产 HTML、Markdown、TSV 或重复 JSON 报告。可选 XLSX 依赖仍见下文；有待办时结果为 `COMPLETE_WITH_PENDING`、CLI 退出2，不能把待办说成工具失败或全部完成。

本轮模块分别是既有表格导入、`wiki_checks`、`agent_adapter`、`xlsx_workflow`、`catalog_drafts`、`ranking_report` 和既有 XLSX 适配器。**TODO：Word/PPT、任意布局 XLSX 的 Agent 抽取、时间范围收集**；这些入口本轮不支持。

2026 年 11 月 6 日交付：[新增 3 条模式 XLSX 与合并核对说明](catalog/drafts/README.md)。0.1.9 增加 [catalog-draft 操作说明](docs/catalog-draft.md)：准备 Agent 输入、校验模式草案、无损合并预览及 XLSX 导出。它不自动采集、调用模型或正式入库；[原工程化方案](docs/catalog-engineering-plan.md)保留为设计记录。

目标网站包括 DTS、Wiki、GitCode、GitHub、CodeHub。真实资料由具备授权与登录态的现场工具采集；现有现场方案使用 OpenChamber/OpenCode。登录认证、搜索、正文读取、分页、附件、评论、Diff、网络重试和权限故障处理均在采集环境完成。核验核心不访问这些网站，也不保存其认证凭据；选择 Codex 执行模型任务不会自动获得这些站点的访问能力。

`fetch-tasks` 只导出待访问 URL 及其引用来源清单，不发送网页请求；`ingest-evidence` 只读取现场返回的本地证据包。模型任务交给选定的执行会话，核心仅做结果验收。

## 先初始化条件索引，再判断新增案例

`trigger-workflow` 在同一核心上增加两个阶段：先逐条维护原 CANN 算子模式的证据与分类明细，冻结初始化基线；随后用该基线判断新案例属于已有明细、需要扩充分支，还是具有新模式依据。原模式编号保持不变，初始化条目是模式定义，不能冒充一条实际故障事件。

`trigger_library.md` 的 **9 族、42 类是输入触发条件**。实际顺序是原记录及已有证据、独立摘要、条件事实、42 项及 Branch 2/3、机理明细、原库对照、入库建议。原有 15 类推理模式用于后续机理关联，不是主要分类标签。同一机理可有多个条件，同一条件可涉及不同机理，均不自动合并。训练记录也完整分类，推理库范围只限制后续入库建议。默认初始化标记 `HISTORICAL_EVIDENCE`；显式的来源定义初始化标记 `SOURCE_DEFINITIONS`。两者均为 `execution_verified=false`，不表示已经运行算子、注入故障或覆盖所有内核路径。

条件分类使用 `applicability=APPLICABLE/PARTIAL/UNKNOWN/NOT_APPLICABLE`；资料支持仍使用独立的 `relation=MATCH/PARTIAL/UNKNOWN/NOT_MATCHED`。例如原单元格写明 INT32 偏移溢出，可按描述给出 `1.3.2 PARTIAL`，缺失的索引实参和地址公式保留未知；没有对应网页也不抹掉这条描述标签。强 `MATCH` 仍需完整的包含/排除条件和对应资料支持，正式根因、`DIRECT` 及新增门禁没有放宽。

每份分类先提取有角色和来源范围的 `condition_facts`，所有 42 项逐一核对完整定义、Requires 和 Skip，每个确定谓词和标签链接局部事实及精确原单元格或当前子问题引文。`INTERMEDIATE_VALUE` 不可冒充输入数值，`INTERNAL_COMPUTATION` 不可冒充 `API_CONTROL`；普通版本差别不是构建变体。Branch 3 的完全适用需要同实参、同二进制的具体依据，缺失时保留部分或未知。未匹配 42 项不会自动落入 Branch 2/3。

Init 冻结 `condition_index`，保留原模式 ID、条件核对、Branch、机理及声明/资料依据；过期索引不显示为当前分类。增量 XLSX 首先展示条件总览、事实、42 项及 Branch，然后展示机理和原模式关联；附带当前冻结 Init 索引，仍只交付一份工作簿。统计分别使用唯一 `case_id`、唯一 `assessment_id` 和逐项标签，不能把多标签或同页主题数当成故障数。条件已评估可同时存在未知、采集缺口或未定入库建议，不因未知字段自行补搜。

Branch 2/3 单独登记，不加入 42 类的分母。默认采用用户于 2026-11-06 明确提供的定义，来源与 Markdown 文件分开保存：

| 分支 | 子类 | 边界 |
| --- | --- | --- |
| 2：实现实例 | 2.1 平台/SoC；2.2 编译选项/宏；2.3 构建变体 | 固定单实例可为 0；这不表示已经验证无故障 |
| 3：执行情境 | 3.1 设备调度；3.2 流与异步；3.3 同步/竞态 | 在同实参、同二进制下考察 |

可用 `--branch-source '定义.json'` 提供显式结构化分支定义，或 `--no-user-branches` 保留未定义状态；没有定义的子类不能由 Agent 自行编造。分类表中的未知不自动变成人工审核事项。

实现按五个模块分工，复用已有采集、摘要、任务去重与输入预算：

| 模块 | 程序承担 | 需要独立子 Agent 的部分 |
| --- | --- | --- |
| 输入与分类基准 | `importers`、`trigger_taxonomy` 保留原编号、来源位置、文件 Hash，冻结完整原库、42 类及 Branch 定义 | 当前结构化输入无需模型抽取；Word/PPT、任意布局仍为 TODO |
| 取证编排 | `evidence_plan`、`wiki_checks`、`xlsx_workflow` 选择全部已有引用、Wiki 优先、同资源共享抓取、有界补读和续跑 | 浏览器 worker 搜索、读取 Wiki/DTS/GitCode/GitHub，核对正文、讨论与必要 Diff |
| 独立资料摘要 | `pipeline`、`bridge` 对同快照共享摘要、分组齐备后汇总，并按资料子问题拆开 | 每个摘要任务用独立上下文提取有原文引用的症状、算子、触发、机理、修复与未知项 |
| 事实对照与分类 | `trigger_assessment` 检查完整 42 项、原单元格和快照引文、Requires/Skip 条件及决策前提 | 每个模式/案例与资料子问题独立判断，比较含义，完成一次自检；不混用同页其他问题 |
| 基线与交付 | `trigger_workflow`、`trigger_report` 保存当前有效明细、冻结基线、检查失效，输出一份 XLSX | 新案例的语义归类复用原全库映射；明确且有引用的未解冲突才交人工 |

没有 Wiki 时，必须先以模式名称、故障原因、算子、症状等原单元格事实指导 Agent 搜索 Wiki；已有 Wiki 则先读原链接，不重复补搜。搜索词及扩展由 Agent 根据实际结果形成，核心不硬编码关键词。原记录提供的 Wiki、DTS、PR 等有效引用全部整理，一份可用资料只停止新增扩搜，不跳过其余原始资料。裸 DTS/Wiki 编号交给 Agent 实际查找并读取对应页面，程序核对编号与资料类型，不拼造内部 URL；查到的地址仍保留“搜索发现”身份和原编号来源链。

登录失败、空页、只读到目录或缺少 Diff 均保留具体采集缺口；`CONTENT_CAPTURED`/`PARTIAL` 中已有的精确引文仍可用于分类。缺失字段保持未知，不能据此认定不适用、另一事件或新增模式。Wiki 有界搜索的 `NO_MATCH` 只描述已查范围，登录失败不能写成 `NO_MATCH`。现场继续通过 OpenChamber/OpenCode 的浏览器和子 Agent 执行，Edge 登录仍由用户手动完成。

初始化示例（沿用上文 `$PythonExe`，路径改为现场实际值）：

```powershell
$TriggerState = 'work/trigger-state'
$Init = & $PythonExe run_faultaudit.py --state $TriggerState trigger-workflow init `
  --modes '原始CANN算子故障模式库.xlsx' --taxonomy 'trigger_library.md' `
  --work-root work/runs --executor opencode | Out-String | ConvertFrom-Json
$InitRunId = $Init.run_id
& $PythonExe run_faultaudit.py --state $TriggerState trigger-workflow next --run $InitRunId
# 现场主会话循环 next/submit，或复用已有 Agent 命令适配器整批推进：
& $PythonExe run_faultaudit.py --state $TriggerState trigger-workflow drive --run $InitRunId `
  --agent-command-file '实际Agent命令配置.json' --workers 2 --timeout 1000 --browser-timeout 1000
& $PythonExe run_faultaudit.py --state $TriggerState trigger-workflow status --run $InitRunId
& $PythonExe run_faultaudit.py --state $TriggerState trigger-workflow finalize --run $InitRunId
& $PythonExe run_faultaudit.py --state $TriggerState trigger-workflow export --run $InitRunId
```

`finalize` 要求每个原模式及每个当前资料子问题已有有效判断，未执行任务不能跳过。采集阻塞或来源机理仍不明确时，可显式加 `--allow-pending` 冻结 `READY_WITH_GAPS` 临时基线；普通触发谓词未知、可引用的部分正文不阻止维护基线，未知项逐条保留，不因此成为人工异常或技术否定结论。新增案例默认要求 `READY` 基线；若明确使用临时基线，`classify` 需指定 `--allow-pending-baseline`。输入、摘要、规则或基线依赖变化后，旧判断及旧基线保留为历史，不能继续充当当前有效结论。

没有网页访问条件、仅维护已提供的模式描述时，在 `init` 增加 `--basis SOURCE_DEFINITIONS`，并为实际库填写 `--catalog-scope`。该路径不派发初始化采集：Agent 引用原单元格整理声明明细，冻结 `declared_details`，网页 `coverage_details` 保持空。`READY` 表示声明基线已维护，不表示其历史根因已获外部证实。默认仍为 `--basis HISTORICAL_EVIDENCE`，不会自动降级。

后续 `classify` 继续执行已配置来源的搜索、独立摘要和事实对照。使用声明基线时，Agent 同时对完整冻结模式集合输出 `declared_comparison`：归入已有声明、扩充分支、建议新模式或待定，均为 `SUGGESTION_ONLY/NOT_ESTABLISHED`。范围不符的训练案例不能自动加入推理库；字段缺失或 42 类未知不能证明新颖性。正式决策继续使用原有事件、根因和直接证据门禁，声明建议不生成正式 ADD 或人工 ACCEPT。报告将两种结果分列；此路径不再重复派发要求网页直接支持的全库映射任务。

若用户明确说明本轮不支持 Wiki，可设置运行级来源可用性，不把未访问伪造为 `NO_MATCH`。例如 `trigger-workflow set-sources --run <id> --source GITCODE --source GITHUB --wiki-policy NOT_SUPPORTED --reason '用户明确本轮只能访问公开代码源'`。Wiki 显示 `NOT_SUPPORTED/checked=false`，原 Wiki/DTS 引用留档但不再派发采集或编号解析任务；GitCode 优先，GitHub 官方上游补充单列。旧请求因来源策略改变失效，历史不删除。默认流程仍然 Wiki 优先。来源设置随初始化基线传入后续批次。

子集试验在 `init` 时显式给 `--catalog-scope PILOT_SUBSET_25_OF_30`，冻结并在报告中保留该范围。对 25 条实验基线的排除不代表对原始 30 条正式库的排除，不能据此正式新增模式。原始模式定义也不能被当作具体客户事件，搜索到同机理资料不等于找到了原事件。

```powershell
$New = & $PythonExe run_faultaudit.py --state $TriggerState trigger-workflow classify `
  --baseline-run $InitRunId --input '新增结构化故障表.xlsx' `
  --work-root work/runs --executor opencode | Out-String | ConvertFrom-Json
$NewRunId = $New.run_id
& $PythonExe run_faultaudit.py --state $TriggerState trigger-workflow next --run $NewRunId
# 使用同一 next/submit 或 drive 接口完成该批次，再 export。
```

新案例先比较完整原机理库：`CLASSIFY_EXISTING` 需有实际库覆盖与已有明细；`EXTEND_DETAIL` 在已有机理下提出有依据的新条件/实现明细；`PROPOSE_NEW_MODE` 需完整原库逐项排除及当前同事件直接根因依据。仅 42 类未命中、Branch 2/3 不同或资料缺失，均不足以提出新机理；证据不足用 `UNDETERMINED`。所有动作是分类/维护建议，不自动正式入库，也不生成或继承人工 `ACCEPT`。

中间数据只用既有 `<state>/audit.sqlite3` 和 `<state>/snapshots/<snapshot_id>/`；任务文件固定在 `work/runs/<run_id>/tasks/<task_id>/request.json` 与 `attempt-<n>/response.json`。摘要、分类结果、基线及历史留在同一数据库，不再建第二套队列或数据库。对外每批只交付一个 XLSX：初始化为 `work/runs/<run_id>/output/模式初始化及覆盖详情.xlsx`，增量为 `故障分类及分支建议.xlsx`，含总览、42 类覆盖详情、机理明细、Branch 2/3、证据与缺口、运行统计。模型任务仍受整请求预算约束，处理不了时明确阻塞，不截取前缀后提交成功。

## 本版可用范围

- XLSX、CSV、TSV、JSON 导入；保留原文、文件 hash、sheet、行和单元格。
- Catalog 按工作表选择并核对预期数量，文件 Hash、工作表与作用域在同一 run 内冻结；识别“根因/进展”表头。
- 原始引用、搜索发现和人工补充分别登记；相同资料的不同引用来历保留。
- 先规划全部已有引用的整理工作，不只挑一份资料；已有适用内容时停止新增搜索，未选搜索候选和旧结果留档。
- 显式登记用户已确认的事件组；相同技术输入共享工作，不同根因或场景分别处理，原始 case 不合并。
- SQLite 台账、资料版本、任务依赖及请求 hash；输入变化后旧结果失效，支持恢复任务。
- 按依赖生成资料摘要、逐关联比较和全库映射任务，由 OpenCode 或 Codex 会话执行后提交结果。
- 本地结构、原文引用和业务校验；生产者元数据记录执行者、对应版本、provider、model 和会话。
- 原文引文、跨快照引用、同事件锚点、根因冲突、冻结库版本等门禁。
- 对数字、术语、场景及技术结论逐项列原单元格、原文、资料引文与含义；模型自查后区分正常自动处理、Agent 补充和人工异常。
- 组件完整性矛盾与 PR 文件计数门禁；未验收正文和网络阻塞状态分别保存。
- `evidence-index` 反查共享资料的所有引用者、各自判断及历史版本。
- 全库逐项比较合同；未确认事件与缺失机理不标为已覆盖或未覆盖。
- JSON、HTML、Excel 可打开的 TSV；可选 ArtifactTool XLSX 适配器。
- 追加人工复核记录；项目专用 Skill 和 OpenCode V2 命令安装模板。

核心不配置模型服务地址、凭据或模型网络客户端。OpenCode 的 provider/model、实际服务、委派工具及认证由现场配置；Codex 可直接读取导出的任务并提交文件结果。文件协议不会自动启动模型会话。`mock` 仅用于离线流程演示。

本版不自动合并故障，不包含内网采集器或已认证 MCP，也不自动恢复旧表根因来源。事件组只汇集明确登记的成员和选定证据，不掩盖成员间不同根因或场景；争议交人工处理。原 98 条库和原始周报需现场提供；内置 mock 演示库只有两条合成模式，另有可重建的 98 条合成模拟库，两者均不冒充真实故障库。

## 从源码开始

Python 3.10 及以上；核心依赖 Pydantic 2，读取 XLSX 另需 openpyxl。已有依赖时可直接运行源码，无需全局安装 faultaudit。先在含 `run_faultaudit.py` 的核心目录打开终端。以下完整流程使用 PowerShell；将 `$PythonExe` 设置为准备使用的 Python 命令或可执行文件绝对路径，安装依赖和运行工具始终使用同一个解释器。

`doctor` 和 `--version` 在缺少第三方依赖时也可运行。`doctor` 输出实际 Python 路径、`core_ready` 和 `xlsx_import_ready`，不创建运行台账；其他命令缺依赖时输出 JSON 错误。

```powershell
$PythonExe = 'python'
& $PythonExe --version
& $PythonExe -m pip install -r requirements.txt
& $PythonExe run_faultaudit.py doctor
```

确认 `doctor` 的 `core_ready=true`；需要 XLSX 导入时还应有 `xlsx_import_ready=true`。如果 Windows 的 `python` 指向商店占位程序，或另一套缺依赖的 Python，请将 `$PythonExe` 改为实际可执行文件的绝对路径。机器上的具体路径不写入可移植代码。

`doctor`只检查本地解释器与依赖，不验证OpenChamber连接、OpenCode登录态、Wiki/DTS权限或DeepSeek实际调用。现场安装、合成执行及真实服务验收见[OpenChamber/OpenCode接入步骤](integration/OPENCODE_HANDOFF.md)。

需要先确认本地流程时，可运行不调用模型的 mock 演示：

```powershell
& $PythonExe run_faultaudit.py --state demo_output/state demo --out demo_output
& $PythonExe run_faultaudit.py --state demo_output/state validate --run latest --strict
$LASTEXITCODE
```

严格验收预期退出 `2`。该演示使用合成资料和 mock，任务执行成功仍不等于真实语义核验完成。`demo_output/report/report.html` 为复核报告，`report.json` 保留明细。需要由 Codex 会话实际执行任务时，使用下文“Codex 合成模拟”，不要把 mock 当作替代。

## 选择模型任务执行者

| 执行者 | 导出／提交参数 | 显式推进参数 | 使用范围 |
| --- | --- | --- | --- |
| OpenCode | 默认，或 `--executor opencode` | `run --mode opencode` | 现场已配置的 OpenCode provider/model |
| Codex | `--executor codex` | `run --mode codex` | 当前 Codex 会话读取任务并生成结果文件 |
| mock | 不执行文件模型任务 | `run --mode mock` 或 `demo` | 本地流程演示，不证明真实故障关联 |

导出任务不会启动任何模型。操作者需要把请求交给选定会话，取得结果文件后再提交。请求与结果的执行者必须一致；不要通过改写 producer 或 request hash 将另一执行者的答案贴到旧任务。切换执行者、输入或规则后按当前依赖重新导出任务。

## 实际资料流程

### 1. 固定输入与 run ID

将输入文件放入受控目录，填写下面三个实际路径。原始周报、旧汇总和模式库分别承担原始来源、待核验历史结果与分类基准的角色。

```powershell
$AuditState = 'work/state'
$WeeklyFile = '实际路径/26年精度工厂周报.xlsx'
$LegacyFile = '实际路径/周报全表_故障清单.csv'
$CatalogFile = '实际路径/计算产品线精度故障模式库V0.3.xlsx'

$AuditImport = & $PythonExe run_faultaudit.py --state $AuditState import --input $WeeklyFile --source-kind ORIGINAL_WEEKLY --catalog $CatalogFile --catalog-sheet '推理精度故障模式汇总' --catalog-scope INFERENCE --expected-catalog-count 98 | Out-String | ConvertFrom-Json
$AuditRunId = $AuditImport.run_id
if (-not $AuditRunId) { throw '导入未成功返回 run_id，请先查看错误。' }
$AuditRunId

& $PythonExe run_faultaudit.py --state $AuditState import --run $AuditRunId --input $LegacyFile --source-kind LEGACY_TABLE
```

保存 `$AuditRunId`，后续导入、采集、模型任务、人工复核和导出都显式使用同一 ID。另一个终端继续时，重新设置 `$PythonExe`、`$AuditState` 和已保存的 `$AuditRunId`。`latest` 仅是本地便捷选择，不应代替正式批次编号。

旧汇总的根因默认 `LEGACY_DERIVED_UNKNOWN`。其 `Sheet`、`Excel行` 等声明保存在 `raw`，不替换该 CSV 自身的真实来源位置；跨文件来源恢复仍需另行对账。追加旧表不自动合并它与原始周报中的重复事件。相同文件、来源类型和原始行的重复导入幂等。

`--catalog-sheet` 使用精确工作表名，可重复指定；未知名称、空选择或 `--expected-catalog-count` 不符会拒绝导入。省略工作表参数时仍会全表导入，因此正式 98 条核验应显式选择推理汇总。一次 run 只使用一个 Catalog 选择，文件 Hash、所选工作表（含空表）和 `--catalog-scope` 一起冻结；错误选择会在追加故障记录之前拒绝。训练 43 条使用另一个 run，不能加入推理 98 条分母。库条目保存版本、作用域、Sheet 和物理行号。

### 2. 先预览证据计划，再采集必要原文

需要逐条核验 Issue、PR 与根因时，可额外导出只读调查计划：

```powershell
& $PythonExe run_faultaudit.py --state $AuditState investigation-plan --run $AuditRunId --out work/investigation_plan.json
```

计划包含每条原记录、出处、按 URL 去重的资料、现有 `work_id` 与适用子问题。OpenChamber/OpenCode 或 Codex 先读取已有正文、相关讨论、明确关联的 Issue 和必要修复 Diff，再用现有证据包、独立摘要和模型文件协议回传。搜索许可继续按 `search_control.search_allowed` 执行。

资料自身的技术事实与当前故障根因候选分别输出；标题、链接、历史归因和另一事件的根因均不能直接填入当前记录。缺依据时明确保留 `ROOT_CAUSE_UNCONFIRMED`。命令不联网、不执行模型、不新增人工 ACCEPT。详细字段和接续步骤见 [调查计划说明](docs/investigation-plan.md)。

现场升级后先运行只读预览，不提交资料或结果：

```powershell
& $PythonExe run_faultaudit.py --state $AuditState evidence-plan --run $AuditRunId --out work/evidence_plan_preview.json
```

该入口使用 SQLite 只读连接，不创建 state。逐 case 的 `path`、`selected_ref_ids`、`selected_snapshot_ids`、`required_actions` 与 `stop_reason` 说明下一步和停止原因。0.1.8整理原始表、旧汇总表及已确认关系中的全部已有引用，不只选首份；同URL可共享抓取和摘要，各来源仍分别保留。已有可用原文时先提事实，不为凑齐 Wiki/DTS/PR 类型继续搜索。`PARTIAL` 中已取得的正文可以处理，真实缺少的组件另记；访问失败保留真实状态，不能冒称没有证据而改成无目标搜索。

默认策略为`min_usable_evidence=1`、无强制来源。原表或旧表已有Wiki、GitCode、GitHub、CodeHub/PR或DTS任一可用资料即停止新增搜索；DTS不触发额外补Wiki或代码的默认规则。已有引用尚未读取或访问失败时，先采集或处理真实缺口，不当作无证据盲搜。所有已有引用继续整理，停止的是新增搜索。未选搜索候选不删除，也不增加必要任务或待办数。

### 按数量与来源配置搜索目标

仅在需要额外数量或指定来源时配置。以下都是写入策略的命令，不是只读预览；默认不需要运行。来源枚举为WIKI、DTS、GITCODE、GITHUB、CODEHUB。

```powershell
# 至少一份GitCode或GitHub资料；二者满足其一即可
& $PythonExe run_faultaudit.py --state $AuditState set-search-policy --run $AuditRunId --min-evidence 1 --require-any-source GITCODE GITHUB

# 至少两份资料，并且Wiki与DTS都要有
& $PythonExe run_faultaudit.py --state $AuditState set-search-policy --run $AuditRunId --min-evidence 2 --require-source WIKI --require-source DTS

# 重置run级策略为默认；已有case级覆盖继续以其自身策略为准
& $PythonExe run_faultaudit.py --state $AuditState set-search-policy --run $AuditRunId
& $PythonExe run_faultaudit.py --state $AuditState evidence-plan --run $AuditRunId --out work/evidence_plan_policy.json
```

`required_sources`是AND，全部指定来源都要满足；`required_any_sources`是OR，列表中满足一种即可。两组都设置时，两组条件与最少数量共同生效。一满足就停止新增搜索，不补齐未要求的资料类型。加`--case-id <实际case_id>`可设置单条记录的完整覆盖策略，不与run级字段逐项合并。也可用`--file policy.json`提交完整对象`{"min_usable_evidence":1,"required_sources":[],"required_any_sources":[]}`；文件与策略flags不能混用。

每条计划的`search_control`记录实际policy、scope、satisfied、search_allowed、status、reasons、可用数量/来源及缺少条件。数量单位以`counting_basis`为准，不把同URL的多个出处重复凑数。`satisfied=true`只说明搜索目标已满足，不代表根因已确认、故障库已覆盖或整条任务完成。现有资料仍须独立摘要、逐work比较和库映射；新增候选也须按这些门禁判断适用性。来源追溯与用户确认仍分别保存，不为满足策略伪造`user_confirmed`。

来源分级与用户确认相互独立：

| 来源等级 | 能证明的来源关系 |
| --- | --- |
| SOURCE_CELL_LINKED | 可追溯到原始周报/OBP文件、工作表、行与单元格 |
| LEGACY_TABLE_LINKED | 可追溯到旧汇总表单元格；不证明原始周报提供了该链接 |
| SEARCH_DISCOVERED | 搜索或追链发现的候选，保留查询词与父链接 |
| PROVENANCE_PENDING | 来源链尚待Agent恢复，不能自动变成人工异常或跳过资料 |

`user_confirmed`记录已有明确用户确认，不能替换来源等级。旧表链接即使确认可用，仍是LEGACY_TABLE_LINKED；`legacy_relation`仅保留历史兼容信息，不作为本版路由或证据强度。来源可追溯也不等于技术根因已证明。

同一case、同一快照的不同issue范围分别形成`work_id`，模型请求、比较结果和待办按work绑定，不能用case/snapshot二元组折叠。资料摘要共享不等于子问题判断共享；不同来源指向同URL时，抓取可共享，引用来历不合并。

需要恢复已确认的事件关系时，由现场把用户已有确认转成具体 `case_id` 注册；不要求用户重复确认。下面仅示意两条合成记录，不能直接用于真实 WB：

```powershell
& $PythonExe run_faultaudit.py --state $AuditState register-event-group --run $AuditRunId --case-ids 'synthetic-case-a' 'synthetic-case-b' --group-id 'synthetic-group' --user-confirmed --confirmed-by '已有用户确认的记录者' --reason '引用已有确认的具体依据'
& $PythonExe run_faultaudit.py --state $AuditState confirm-evidence --run $AuditRunId --case-id 'synthetic-case-a' --snapshot-id 'synthetic-snapshot' --issue '具体子问题标签' --user-confirmed --confirmed-by '已有用户确认的记录者' --reason '引用已有资料关联确认的依据'
```

这两个是写入登记命令，不是只读预览步骤；没有既有确认时不能加 `--user-confirmed` 冒充确认。`confirm-evidence` 可指定 `--ref-id` 或 `--snapshot-id`，可重复 `--issue` 限定多问题资料中实际适用的部分。确认事件组不等于确认所有成员根因相同：不同技术输入继续各自判断。

```powershell
& $PythonExe run_faultaudit.py --state $AuditState fetch-tasks --run $AuditRunId --out work/fetch_tasks.json
```

现场工具按清单采集选定的必要正文，保存原文、时间、落地 URL 和组件缺口，生成 `work/evidence.json`。该文件可以是单个证据包或证据包数组，字段见“采集证据包”。登录页、搜索摘要或模型摘要不能充当正文。访问失败也应提交准确状态。

```powershell
& $PythonExe run_faultaudit.py --state $AuditState ingest-evidence --run $AuditRunId --package work/evidence.json
```

### 3. 按依赖执行模型任务

以下使用默认的OpenCode执行者；在OpenChamber连接的实际OpenCode会话执行这些任务即可，无需另由Codex代做。核心也兼容显式选择Codex的文件协议。

```powershell
$AuditExecutor = 'opencode'
& $PythonExe run_faultaudit.py --state $AuditState model-tasks --executor $AuditExecutor --run $AuditRunId --out work/requests_01.json
```

现在由选定会话读取 `requests_01.json`：逐项按 `instructions`、`payload` 和 `expected_contract` 执行，保存 `work/results_01.json`。不要只在聊天中返回“完成”，也不要生成自由汇总表替代这些任务。

结果文件准备好后再执行：

```powershell
& $PythonExe run_faultaudit.py --state $AuditState submit-model-results --executor $AuditExecutor --run $AuditRunId --file work/results_01.json
& $PythonExe run_faultaudit.py --state $AuditState model-tasks --executor $AuditExecutor --run $AuditRunId --out work/requests_02.json
```

对下一批重复“读取请求 → 会话执行 → 保存结果 → 提交 → 导出”，每批使用新文件名留存原始请求和答案。阶段依赖为独立资料摘要 → 逐故障与资料比较 → 全库映射。实际批次数由资料分块、依赖和缺口决定，三个阶段不保证只需三批；以 `tasks[].kind` 和 `ready_model_tasks` 为准。

`submit-model-results` 和 `model-tasks` 本身会推进状态。需要显式恢复或重试时使用：

```powershell
& $PythonExe run_faultaudit.py --state $AuditState run --run $AuditRunId --mode $AuditExecutor --resume
& $PythonExe run_faultaudit.py --state $AuditState run --run $AuditRunId --mode $AuditExecutor --retry-failed
```

重试后重新导出当前任务；不要改旧请求 Hash 或覆盖第一份已验收结果。`tasks=[]` 可能表示当前依赖受阻，必须结合 `status`/`validate` 判断。

### 4. 反查、复核与导出

```powershell
& $PythonExe run_faultaudit.py --state $AuditState evidence-index --run $AuditRunId --out work/evidence_index.json
& $PythonExe run_faultaudit.py --state $AuditState status --run $AuditRunId
& $PythonExe run_faultaudit.py --state $AuditState export --run $AuditRunId --out work/report
```

反查保留原始链接、旧表链接、搜索补链、人工补链及各条记录的当前判断；共享链接只提示交叉核查，不证明同一事件。可加 `--url '实际证据URL'` 查询资料。报告的“逐引用整理”列出全部引用的来源分级、独立用户确认、采集/摘要状态和逐work结论；“逐资料子问题”展开各份摘要中的全部issues。未抓到的链接也会列出缺口。共享结果可在多个引用行重复展示，这些展示行不当作新增判断数量。

报告还保留“证据反查”“库选择基准”“证据计划”“未选引用留档”“事实对照”及“事件组结论”。事实对照同时注明work_id、issue范围和引文所属source_case_id；共享判断不把代表行的原单元格冒充其他成员原文。每个引用的user_confirmed与共享work的work_user_confirmed分列，不互相覆盖。

“搜索控制”单独展示每条记录的目标、缺口与停止原因；搜索目标已满足也不会改写证据强度或库覆盖。统计的search_goal_satisfied_case_count/search_goal_unsatisfied_case_count只是按case去重的采集目标状态，不能加到判断数或冒充覆盖完成数。

只把 `EXCEPTION` 中待人工处理的项交复核人；`PENDING` 先由 Agent 补充，`AUTO_PROCESSED` 不要求例行人工 ACCEPT。人工处理时读取具体关联的 `judgment_id` 和库映射的 `task_id`，填写结论、理由和姓名；示例见“判断边界”。修改关联裁决会使相关映射失效，需要重新推进并检查结果。

```powershell
& $PythonExe run_faultaudit.py --state $AuditState validate --run $AuditRunId --strict
$LASTEXITCODE
```

| 退出码 | 含义 |
| --- | --- |
| `0` | 普通 `validate` 表示结构合法；`--strict` 还要求没有待处理项 |
| `2` | `validate` 发现无效记录，或严格模式仍有缺口／待复核项；查看 `errors` 与 `pending` |
| `1` | 命令执行或输入校验失败，查看输出的 `error` 与 `message` |

必要证据不足、未知映射或未解决异常会让严格验收保持 `2`，不能靠批量 ACCEPT 清空真实缺口。未选引用和不阻塞的可选采集不增加必要待办。处理后重新导出报告，保留原始文件和旧版本产物。

### 模型任务协议

默认执行者仍为 OpenCode。使用 Codex 时显式指定执行者：

```text
python run_faultaudit.py --state work/state model-tasks --executor codex --run <id> --out work/requests.json
python run_faultaudit.py --state work/state submit-model-results --executor codex --run <id> --file work/results.json
python run_faultaudit.py --state work/state run --mode codex --run <id>
```

Codex 会话逐项读取请求的 instructions/payload，执行后按原始 run/task/request hash 回传。Codex 的 producer 使用 `executor=codex`、`codex_version`、`provider`、`model`、`session_id`；不填写假的 `opencode_version`，也不能把 Codex 结果标成 DeepSeek。精确运行版本或模型 ID 未暴露时明确写 `unreported`，不根据本机另一个 CLI 的版本推定后台版本。结果 `model_mode` 由核心保存为 `codex`。不同执行者的任务不可互相消费，默认接口继续兼容 OpenCode。

`requests.json` 顶层包含 `schema_version`、`run_id`、`executor` 和当前就绪的 `tasks` 数组。每个模型请求包含 `instructions`、`payload`、`expected_contract`、`run_id`、`task_id` 和 `request_hash`。请求不携带服务凭据。执行会话按任务类型分别执行资料摘要、逐关联比较和全库映射，不以自由整理表格替代这些任务。`schemas` 命令导出 EvidencePackage、EvidenceSummary 和 Judgment 的结构；全库响应 CatalogResponse 的完整合同在 `faultaudit/model.py`。

返回单任务结果的 envelope 如下，`result` 必须符合该请求的 `expected_contract`：

```json
{
  "schema_version": "1.0",
  "run_id": "<原请求run_id>",
  "task_id": "<原请求task_id>",
  "request_hash": "<原请求request_hash>",
  "result": {},
  "producer": {
    "executor": "opencode",
    "opencode_version": "2.1.4",
    "provider": "<实际provider>",
    "model": "<实际model>",
    "session_id": "<实际会话标识>"
  }
}
```

示例中的空 `result` 只是 envelope 示意，不能直接作为有效任务结果提交。不得重新计算或改写请求标识来绕过过期输入；本地核心将检查请求对应关系、结果结构、原文引用和业务门禁。

Codex 使用相同 envelope，仅将 `producer` 换成以下对象，并填写实际可核实的信息。下面的占位内容不是业务结果，也不是生产者信息的验证证明：

```json
{
  "executor": "codex",
  "codex_version": "<实际后台版本；未暴露则明确写unreported>",
  "provider": "<实际provider>",
  "model": "<实际模型ID；未暴露则明确写unreported>",
  "session_id": "<实际会话标识>"
}
```

提交文件支持单个 envelope、envelope 数组，或 `{"results": [envelope, ...]}` 包装；其中每个对象都须保留对应请求的标识。

文件桥接会根据 producer 为结果回填 `model_mode` 和 `model_id`，执行会话可在 `result` 中省略它们；如果提供，两者必须与执行者和 producer 的 model 一致。

如果要求 DeepSeek，现场必须通过 OpenCode 配置并确认实际使用的 provider/model。当前聊天或委派模型不是 DeepSeek 时，不能在结果或报告中声称已经使用 DeepSeek。`producer` 是执行方记录的来源信息，核心不会借此声称已经独立核实远端服务调用。

`run --resume` 按现有任务继续；失败任务用 `--retry-failed` 重试。`status` 与 `validate` 显示缺口；`validate --strict` 只在全部条件满足时返回 0。普通模式的 0 表示结构合法，仍可能存在待核验项。

## 采集证据包

以 `fetch-tasks` 输出为 OpenChamber 现场采集清单。由该环境的工具读取实际网站，正文、评论、附件、Diff 分别登记完整度；失败资料也提交状态。认证或访问失败须在现场处理，不让 Codex 核心补建爬虫或代读网页。

```json
{
  "schema_version": "1.0",
  "url": "https://example.invalid/wiki/one",
  "requested_url": "https://example.invalid/wiki/one",
  "final_url": "https://example.invalid/wiki/one",
  "title": "示例资料",
  "text": "采集工具实际读取的正文，不是模型代写的摘要。",
  "status": "COMPLETE",
  "components": {"body": "COMPLETE", "comments": "NOT_APPLICABLE"},
  "retrieved_by": "现场工具名及版本",
  "case_ids": [],
  "is_synthetic": false,
  "derived_from": []
}
```

原链凭 URL 与已有行匹配；搜索补链须填写明确的 `case_ids`，并设 `record_discovery=true`、`origin=SEARCH_DISCOVERED`、`discovery_query`。从其他资料追链还填写 `discovered_from_url`。普通抓取不会把原周报链接重新标记成人工添加。

`raw_file` 可引用证据包目录内的原始响应文件，程序复制并保存 hash。无法获取原始响应时保留实际提取文本，`raw_sha256=null` 明确表示未保存响应原件。

状态新增 `NOT_FETCHED`、`NETWORK_BLOCKED`、`CONTENT_CAPTURED`。`CONTENT_CAPTURED` 表示正文已取得但完整性尚未验收，可作初步摘要，不能建立直接支持或确认归属；`PARTIAL` 保留实际缺口。

`COMPLETE` 必须有正文且 `components.body=COMPLETE`，已声明的其他组件只能为 `COMPLETE` 或 `NOT_APPLICABLE`。`required_components` 可指定必须交代的章节、评论、附件或子页面等组件。Wiki/DTS 的站点完整性清单仍由现场适配器提供；旧 generic 的 body-only 包兼容接收，不代表已独立证明整个页面完整。

`artifact_type` 可为 `GENERIC`、`WIKI`、`DTS`、`PR`。显式 PR 或常见 PR URL 的完整包还必须包含：

```json
{
  "artifact_type": "PR",
  "components": {"body": "COMPLETE", "file_list": "COMPLETE", "diff": "COMPLETE"},
  "required_components": ["body", "file_list", "diff"],
  "expected_file_count": 1,
  "captured_file_count": 1
}
```

以上是补充字段，需与 URL、正文、状态等基本字段一起提交。文件计数须为实际非负整数且相等；Diff 不完整时提交 `PARTIAL`。计数核对的是采集器声明的一致性，仍需现场验证采集内容覆盖了远端实际文件及 Diff。认证重定向或明确登录页不能作为正文；失败状态可正常留档。

运行 `schemas --out schemas` 可导出本版 JSON schema。摘要可按保留原文覆盖的片段处理。输入超过核心任务上限，或 OpenCode 会话无法完整处理时，保留原始请求并报告 `BLOCKED` 与具体原因；不能删除段落、缩短 payload、漏掉库条目后提交为完整结果。具体上限与阻塞记录以当前任务和核心诊断为准，实际执行会话的大资料处理能力仍需在目标环境联调。

0.1.4 默认上限为 48,000 个字符，可用正整数环境变量 `FAULTAUDIT_MAX_INPUT_CHARS` 配置。计量对象是整个请求的 canonical JSON 字符数，包括 instructions、payload、作用域、Hash 和预算元数据，不是 token 数或仅正文长度。已导出任务的 `input_budget` 保存 `chars`、`budget` 和 `scope=WHOLE_MODEL_TASK`。超限时父任务记录 `BLOCKED`/`INPUT_TOO_LARGE`，`model_input_blocked` 事件保存测量详情；核心不生成删减版任务。

执行者自身容量不足时，向操作者报告原 task ID 和阻塞原因，不提交模型结果；协议没有新增可当作成功答案提交的 blocked envelope。提高本地字符上限不证明远端模型能完整处理，调整前须核实现场能力，调整后重新导出当前任务。

`PARTIAL` 描述采集资料的真实组件缺口，不表示已取得的正文不存在。必须保留并提交已经抓到的全部正文，同时记录缺失评论、附件或 Diff；执行者的上下文不足不能通过改标 `PARTIAL`、替换正文或只选摘要片段来解决。未在可见内容中读到某事实，也不能声称完整原文没有该事实。

## 判断边界

同一事件需明确事件编号，或源故障描述中足够具体、在证据引文中逐字出现的事件签名，同时匹配症状、机理及触发/修复/构建特征。共享链接和同算子不能作为事件身份。原文定位只是必要条件，不能证明语义正确。

0.1.6 将处理状态与人工裁决分开。模型需填写 `fact_comparisons`：数字、术语、场景和技术结论都要核对含义，不能只因数字或名称相同就写 MATCH。多问题资料注明 `applicable_issue`，完成一次 `self_check`；引文和单元格仍由本地门禁核对。

新文件协议的比较结果必须提交完整四类对照和一次五项自检。缺少这些结构时，核心拒收且不保存该答案，Agent可以在原任务ID及Hash下补齐后重新提交；不以空答案占住不可变响应。自检发现真实冲突时可以 `passed=false` 并保留 `issues`，进入异常队列。历史结果仍保留。

`validate.fact_organization_complete` 单独表示所有必要事实整理已完成；库覆盖未知仍保留在总体 `complete` 和严格验收缺口中。事实整理完成不等于库覆盖已确认，也不要求为了消除库覆盖待定而继续搜索。

| 处理状态 | 后续责任 | review_status |
| --- | --- | --- |
| AUTO_PROCESSED | 事实与引文门禁通过的普通结果，自动进入后续处理 | NOT_REQUIRED，review_required=false |
| PENDING | 资料或事实不足，由 Agent 补充 | PENDING_AGENT，review_required=false |
| EXCEPTION | 明确矛盾或异常，由人工处理 | NEEDS_REVIEW，review_required=true |

`CONFIRMED`、`DIRECT` 与覆盖是业务判断字段，不是人工 `ACCEPT`。自动处理始终不伪造人工裁决；人工可按实际证据另行复核。旧记录缺少新状态时沿用旧复核口径，不把旧建议直接升级为自动处理。

下面命令须由实际复核人在阅读证据后执行，将 ID、理由与姓名替换成真实值。`ACCEPT`、`REJECT`、`NEEDS_INFO` 是可选裁决；示例使用 `NEEDS_INFO`，不代替实际判断：

```powershell
& $PythonExe run_faultaudit.py --state $AuditState review --run $AuditRunId --judgment '待复核的judgment_id' --verdict NEEDS_INFO --reason '填写缺失证据或裁决依据' --reviewer '实际复核人'
& $PythonExe run_faultaudit.py --state $AuditState review --run $AuditRunId --mapping '待复核映射的task_id' --verdict NEEDS_INFO --reason '填写模式匹配依据或缺口' --reviewer '实际复核人'
```

裁决以追加记录保存，不改写原文或自动合并事件。必要项中的未知或未解决异常会使严格验收保持待处理。修改关联判断的裁决后，对应库映射立即失效，需重新推进任务，避免导出旧覆盖结论。

原文引文存在只是出处校验，不能机械证明结论含义正确。模型须核对模式机理、触发条件、计量含义和否定语境，并保留反证；明确冲突交人工。自动处理不意味着程序已证明所有语义正确。

## 历史 Codex 合成模拟：输入与执行步骤

以下保留2026-10-30的合成模拟输入和历史验收口径。当前版本按证据计划选择任务，实际任务数及处理状态应以新请求和validate为准，不能要求每轮仍有7个比较或复制历史数量充当本次验证。

`verify_codex_pilot.py` 保留历史固定任务数和 Codex 执行者的验收预期，不作为当前版本或OpenCode现场通过的证明。当前版本使用完整回归、只读证据计划、真实文件协议结果及轮次对账验收。

先完成“从源码开始”的 Python 依赖检查。为每次模拟选择独立目录，避免覆盖既有请求和结果。下例使用 `work/codex_pilot_new`；目录变量会贯穿整个流程。

### 1. 生成输入、导入并导出摘要任务

```powershell
$PilotRoot = 'work/codex_pilot_new'
$PilotState = "$PilotRoot/state"
& $PythonExe scripts/seed_codex_pilot.py --out $PilotRoot

$PilotImport = & $PythonExe run_faultaudit.py --state $PilotState import --input "$PilotRoot/inputs/cases.json" --source-kind ORIGINAL_WEEKLY --catalog "$PilotRoot/inputs/catalog.json" --catalog-sheet INFERENCE --catalog-scope INFERENCE --expected-catalog-count 98 | Out-String | ConvertFrom-Json
$PilotRunId = $PilotImport.run_id
if (-not $PilotRunId) { throw '模拟导入未成功返回 run_id，请先查看错误。' }
& $PythonExe run_faultaudit.py --state $PilotState ingest-evidence --run $PilotRunId --package "$PilotRoot/inputs/evidence.json"
& $PythonExe run_faultaudit.py --state $PilotState model-tasks --executor codex --run $PilotRunId --out "$PilotRoot/01_requests.json"
```

种子脚本只生成 5 条合成故障、5 份合成资料、7 个关联和 98 条合成模式，不生成答案、不访问网站。让 Codex 只读取 `01_requests.json`，按其中 5 个摘要任务独立生成 `$PilotRoot/01_results.json`。结果顶层使用 `{"results": [envelope, ...]}`。

执行模型不能读取 `expectations.json`、种子脚本、验收脚本或参考答案；这些文件只供独立验收。每条事实携带原文精确引文，两个子问题分别提取。请求/结果文件中的执行者保留为 Codex，不能调用 mock 或冒充 DeepSeek。

### 2. 提交摘要，执行七个逐关联任务

确认 `01_results.json` 已由会话生成后执行：

```powershell
& $PythonExe run_faultaudit.py --state $PilotState submit-model-results --executor codex --run $PilotRunId --file "$PilotRoot/01_results.json"
& $PythonExe run_faultaudit.py --state $PilotState model-tasks --executor codex --run $PilotRunId --out "$PilotRoot/02_requests.json"
```

让 Codex 只依据 `02_requests.json` 的 7 个比较任务判断，写入 `$PilotRoot/02_results.json`。共享 Wiki/DTS 的各个原始记录需要独立判断；相同算子、症状或 URL 不证明同一故障。完成文件后继续：

```powershell
& $PythonExe run_faultaudit.py --state $PilotState submit-model-results --executor codex --run $PilotRunId --file "$PilotRoot/02_results.json"
& $PythonExe run_faultaudit.py --state $PilotState model-tasks --executor codex --run $PilotRunId --out "$PilotRoot/03_requests.json"
```

### 3. 完成五轮全库比较并独立验收

让 Codex 读取 `03_requests.json`，对 5 条记录各比较全部 98 个模式，写入 `$PilotRoot/03_results.json`，合计 490 项。每项 ID 必须唯一且不漏项；引用只能复用该任务有效 judgment 中相同的 `segment_id + quote` 对。历史覆盖建议按当时口径待人工复核；0.1.6按处理状态分工，机制未确认的事件仍保持待定。

```powershell
& $PythonExe run_faultaudit.py --state $PilotState submit-model-results --executor codex --run $PilotRunId --file "$PilotRoot/03_results.json"
& $PythonExe scripts/verify_codex_pilot.py --root $PilotRoot --run $PilotRunId
& $PythonExe run_faultaudit.py --state $PilotState evidence-index --run $PilotRunId --out "$PilotRoot/evidence_index.json"
& $PythonExe run_faultaudit.py --state $PilotState validate --run $PilotRunId --strict
$LASTEXITCODE
```

若任务校验失败，保留原请求、原答案与错误记录，再处理对应问题；不要改 Hash 规避校验，也不要提前提交下一阶段。重复导出就绪任务不会代替尚未执行的模型任务。

验收输出包括 `$PilotRoot/verification_report.html`、`verification_result.json` 和 `report/` 下的完整 JSON/HTML/TSV。严格验收预期仍为 `2`：模拟中的部分 PR、未知条目和人工复核真实保留。不要为使退出码变为 0 而自动 ACCEPT。

2026-10-30 已完成的一轮 Codex 会话模拟：17 个有效模型任务（5 摘要＋7 比较＋5 全库）、31/31 验收检查通过，490 项输出中 3 项为覆盖建议、291 项为未覆盖建议、196 项为待定。过程中澄清过一次“模型建议与人工 ACCEPT 不同”的通用合同口径，未向执行模型提供独立预期。精确模型 ID 和后台版本未暴露，生产者如实记录 `unreported`。可公开的聚合结果见 [Codex 合成模拟验证摘要](examples/codex_pilot_validation.json)，完整范围见 [验收记录](VALIDATION.md)。

这验证了本次合成场景的协议、引文、目标关联与模式预期，不代表真实内网采集、真实 98 条库准确率或 DeepSeek 能力。运行数据库、原始任务/结果和完整报告保留在 `work/`，不进入公开源码包；公开摘要仅含聚合结果。

代码库覆盖在本版指知识模式覆盖。工具实现覆盖、真实环境验证覆盖、自动故障归并和完整诊断演进图均未实现，不能从当前覆盖字段推出这些能力已经存在。

## 可选 XLSX

基础报告不依赖 Node。需要 XLSX 时配置 `FAULTAUDIT_NODE` 和 `FAULTAUDIT_NODE_MODULES` 指向可用的 ArtifactTool runtime，再使用 `export --xlsx`。该适配器不是本项目声称可自由分发的开源依赖，交接包不包含其运行库。

当前 bundled runtime 在部分成功保存后仍返回退出码 1。CLI 只接受本轮新建且通过 ZIP 完整性和工作表数量检查的文件，同时保留 `xlsx_runtime_warning`；视觉预览另存于输出目录。超过 Excel 单元格长度时明确失败，完整 JSON/HTML 仍保留。

## OpenCode V2 与交接

OpenChamber可作为现场前端，由它连接的OpenCode完成采集和模型执行，替代Codex执行任务；本包的接入是已有文件任务桥接，不包含启动OpenChamber或直连其服务的客户端。逐步命令与合成验收清单见[现场接入手册](integration/OPENCODE_HANDOFF.md)。

```powershell
& $PythonExe scripts/install_opencode.py --project '实际工作区根目录'
```

该安装器复制本包的 Skill 和命令，并生成本地 `core-location.json`，不覆盖现有不同内容，也不修改全局配置或项目 AGENTS.md。全部文件和父目录冲突在写入前检查。项目长期规则的可选片段在 `integration/AGENTS.snippet.md`，由现场合并。

安装到父工作区后，Skill 内的 `scripts/run_audit.py` 按环境变量、安装定位配置、源码祖先依次定位同一核心。通常无需设置 `FAULTAUDIT_HOME`；显式设置时它优先，无效值直接报错。同盘配置使用相对路径，整个工作区一起迁移仍可调用；跨盘定位使用本机绝对路径，迁移后需重新配置。该脚本只运行本地核心，不负责建立模型服务连接。OpenChamber 2.5.2 可能连接其内置 OpenCode 2.1.4；PATH 的 2.2.0 不代表实际后端。命令加载、Skill 加载、模型任务执行及采集工具须在目标服务上分别验收，当前未完成现场联调。

## 升级并继续既有 run

0.1.4 的否定判断须提供 `negative_basis.other_event` 或 `negative_basis.attribution_mismatch`，包含积极身份、原文上下文、有效身份维度和精确引用。程序检查结构及引用是否存在，语义是否足以排除关联仍须人工复核；技术差异、资料编号不同或未出现字段不能独立成立 `DIFFERENT_EVENT` / `MISMATCH`。根因冲突单独保留，未解决冲突时不能给 `DIRECT`。`observation_scope` 默认为当前已采集内容，选段和部分资料不能声称核验了全文。

先暂停对现场 state 的写入，关闭正在使用该 SQLite 的程序，备份整个 state 目录及该批次的原始请求、结果和输入。不要只复制数据库而漏掉快照；备份完成前不替换现场文件。本包升级不要求清空台账。

安装新版代码后，优先使用原有 state 与显式保存的同一 `run_id` 续跑，保留原始证据、原答案及人工裁决历史。不要为普通升级重新导入一份记录，也不要使用 `latest` 猜测正式批次。示意命令中的路径和 ID 由现场填写：

```powershell
$AuditState = '既有state目录'
$AuditRunId = '原有run_id'
& $PythonExe run_faultaudit.py --version
& $PythonExe run_faultaudit.py doctor
& $PythonExe run_faultaudit.py --state $AuditState evidence-plan --run $AuditRunId --out work/evidence_plan_018_preview.json
& $PythonExe run_faultaudit.py --state $AuditState run --run $AuditRunId --mode opencode --resume --retry-failed
& $PythonExe run_faultaudit.py --state $AuditState model-tasks --executor opencode --run $AuditRunId --out work/requests_018_01.json
```

先检查只读预览，再由现场执行新导出的必要任务并按原 `task_id`、`request_hash` 提交，继续下一阶段。旧请求和旧结果不改写、不删除；策略或依赖变化后只作为历史记录，过期或未选结果不能继续作为当前必要关联、覆盖结论或已完成计数。正常结果自动处理、证据不足由 Agent 补充、异常交人工；不自动 ACCEPT。

若核心或执行者报告输入超限/无法完整处理，保留 `BLOCKED`，先按错误记录处理任务规模；不能删减该任务后复用原 Hash 提交。该升级流程尚未在真实现场 state 或 Python 3.14.3 环境验证，应先在独立合成 state 检查本机环境，再对已备份的原 state、原路径以同 run ID 续跑。

快照台账保存绝对文件路径，备份用于恢复到原路径；把 state 复制到另一目录后直接续跑会触发路径校验。本次升级不包含 state 路径迁移。Skill 入口随工作区迁移后仍可定位核心，也不等于既有 state 路径已经迁移。

### 旧版兼容边界

证据包 `schema_version` 保持 `1.0`，新增字段均有默认值；旧 generic 包的快照身份保持兼容。旧 SQLite 无需破坏性迁移即可读取。完整性规则也会重查已保存快照，不符合新规则的 PR/组件声明需补采或重新提交部分状态。策略指纹变化会使旧模型请求失效，应重新导出任务，不能改写旧请求 Hash。

0.1.1 的 Catalog 台账没有工作表选择冻结信息；已有此类 Catalog 的 run 可以查看和导出，继续导入 Catalog 时需新建 run。保留旧结果，不自动替换原始记录或旧库身份。已安装的旧 Skill 如与新版模板不同，安装器仍会报冲突；保留旧文件后，在干净目录安装或人工合并更新。

## 开源参考与验证

复用与参考的来源、许可、边界见 [THIRD_PARTY_REFERENCES.md](THIRD_PARTY_REFERENCES.md)。没有复制受限的 Anthropic xlsx Skill。

```powershell
& $PythonExe -m unittest discover -s tests -v
& $PythonExe scripts/validate_release.py
& $PythonExe scripts/build_delivery.py
```

0.1.8 的回归测试使用合成任务和结果文件，不运行模型 HTTP 客户端，也不调用外部模型。本轮实际环境、测试数量与结果以 [examples/validation_result.json](examples/validation_result.json) 和 [验收记录](VALIDATION.md) 为准。2026 年 10 月 30 日由 Codex 会话执行的 [合成模拟验证摘要](examples/codex_pilot_validation.json) 是单独的历史基线，与本版回归、mock 和现场验证分开。交接包排除凭据、SQLite 运行数据、原始证据和依赖运行库，包含 `.gitignore` 及逐文件 SHA-256 清单。

## 0.1.8 统计与现场只读对账

统计入口只从已有记录生成统计与差异报告，不重新提取事实、修改证据、生成业务判断或推进模型任务。网站认证、采集及实际模型执行仍由 OpenChamber/OpenCode 现场环境负责，沿用已有工具与流程。已有长正文分块、整请求预算、输入作用域和策略失效机制保留。

独立统计命令只读 JSON，在初始化任何 Store 之前执行，不打开 SQLite。先经现场既有流程取得完整的 `report.json`，再运行：

```powershell
& $PythonExe run_faultaudit.py reconcile-report --input '现场已有/report.json' --baseline '上一轮/report.json' --round-manifest '本轮清单.json' --out 'statistics.json'
```

只有本轮报告时可省略 `--baseline` 和 `--round-manifest`；此时可以统计文件内已见记录，但轮次增量为 `UNKNOWN`、相应数量为 null，不能把它解释为零变化或对账完成。基线必须是同一 run 的完整 `report_json`，不能用手填数量或 TSV 汇总代替。

本轮清单使用以下结构，ID 应来自实际记录；示例占位内容不能直接提交：

```json
{
  "run_id": "<与两份报告相同的run_id>",
  "judgment_ids": ["<本轮判断ID>"],
  "mapping_ids": ["<本轮映射ID>"],
  "snapshot_ids": ["<本轮快照ID>"]
}
```

没有新增项时对应列表为空。也可用 `pipeline_task_ids` 替代判断与映射 ID 列表，须填写实际父流水线任务 ID。工具按基线与本轮报告的完整差集核对清单，漏列或不一致时输出 `RECONCILIATION_FAILED` 并退出 `2`；重复的清单 ID 去重计一次并给出警告，不能重复增加数量。不能只列有利案例。缺基线或清单产生的轮次 `UNKNOWN` 与这种对账失败不同。

对账须区分以下单位，不能将其中一种数量当作另一种数量加减：

| 单位 | 去重键 | 用途 |
| --- | --- | --- |
| 关联判断 | judgment_id | 一次具体故障与资料关联的判断记录 |
| 原始故障记录 | case_id | 判断涉及了多少条来源记录 |
| 资料快照 | snapshot_id | 判断涉及了多少个内容版本 |
| 待办理由条目 | counts.pending_reason_entries | validate 的理由字符串条目数，不是独立故障或任务数量 |

“当前有效”依据输入报告导出时的 `is_stale` 与流水线任务状态，离线命令不重查今天的数据库或新版策略。真实当前数据需 OpenCode 先通过既有工具只读核对 SQLite 的记录与任务元数据，不能把老报告当作 live DB 验证。新导出的报告会由 `report_data` 按现行策略标记过期，但常规导出仍不是专门的 SQLite 只读入口。

0.1.8 的 current 判断及映射只纳入必要结果（记录和任务均未显式标为 `required=false`）；旧报告没有 required 元数据时沿用原口径。`snapshot_count` 仍为 active 摄取快照全集，`selected_snapshot_count` 单列计划选定快照，`unused_reference_count` 为未选引用数。缺少计划元数据时选择数量为 null，不假定为零。事件组共享一个 judgment_id 就计一次判断，涉及 case 数按该判断的 case_id 与 member_case_ids 去重，不合并原始记录。

`planned_work_count`按计划work_id去重，`current_work_count`按当前必要判断的work_id计量；旧判断缺少work_id时该数量为null。`current_case_snapshot_pair_count`另列case/snapshot二元组数，不能替代work数：一个资料的两个issue可以是同一对case/snapshot、两个work和两个判断。相同work出现多个当前judgment_id时对账失败，不悄悄任选一个。validate的planned_associations/judged_associations保留旧字段名，0.1.7口径为work_id，配套planned_work_ids/judged_work_ids列出具体集合。

`auto_processed_count`、`human_exception_count`、`agent_pending_count` 按当前必要判断分别计数，映射另有独立计数；前者不写成人工 ACCEPT。human_exception_count 包含已复核的异常记录，`pending_human_exception_count` 才是尚未 ACCEPT/REJECT 的人工异常。它们是判断记录数，不能加成唯一 case 数。

人工 REJECT 关联保留在原账与历史中；统计同时给出当前判断包含与排除 REJECT 的两种口径，不能混成一个总数。分类可能交叉，同一判断或故障可能进入多个类别，类别计数之和不必等于唯一判断总数；以明确列出的 ID 集合核对。待办理由也可能属于同一故障或同一任务，不能把理由条目数当成待处理故障数。

`confirmed_accepted` 在该报告的当前口径内，还要求 CONFIRMED、SAME_EVENT、DIRECT、人工 ACCEPT、对应快照 COMPLETE，且没有维度冲突或 claim CONTRADICTED。它是满足这些记录条件的数量，不代表离线统计重新证明了原文语义。

若报告缺少必要的过期标记、任务状态或分类元数据，当前统计也可以为 UNKNOWN/null；缺失信息不补成零，也不以旧汇总数字代填。

每轮增量要用上一轮基线报告与本轮清单共同核对。同 ID 的裁决变化、变为过期或仅重新导出不按新增判断计数。本轮新增历史记录包含本轮新增后又变为过期的项，当前仍有效的新增项另计，不能混合。`new_case_count` 指新增判断涉及的不同 case 数，不是新导入原始故障数。缺少基线时，累计已见记录可以展示，但本轮增量数量保持 `UNKNOWN`，不能将累计数量冒充本轮增量。

现场 OpenCode 做只读对账时，只读取指定 run 的现有 SQLite、报告与轮次清单，并另存派生报告；不调用导入、采集提交、模型结果提交或人工裁决来“修正”数量。记录所用文件 Hash、生成时间与口径。没有现场 SQLite 时，不猜其真实总量；若只能读到已有 JSON 报告，统计只描述该文件所含记录，不能声称已完成数据库全量核对。单凭聊天列出的数量与案例名称不足以纠正现场计数。

常规 `export` 也接受 `--baseline`、`--round-manifest`，可把统计附于 `report.statistics`。它仍走常规 Store 导出路径，不应称为对 SQLite 的绝对只读命令；现场纯对账优先使用已有 JSON 与独立 `reconcile-report`。
