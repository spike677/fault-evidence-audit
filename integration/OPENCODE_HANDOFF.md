# 0.1.17：原30条 Baseline Builder

本段优先于历史的单任务Init说明。保留现场state、原始资料、旧请求和人工记录；备份后在原Init上维护，不清空或自动入库。当前只处理原30条，不派发62条增量，也不新增采集、模型或设备客户端。

新Init使用实际原库、`D:\project\typora\trigger_library.md`及原V4文件。程序解析实际42个ID、名称和定义，校验SHA和原冻结内容，导出原42核对清单；不能用文件名代替内容核对。V4源文件不改。暂缺的`42_vs_55_mapping.md`不阻塞，也不作自动标签转换。

若当前42文件的字节SHA与旧Init冻结版本不同，`configure-baseline`会拒绝直接复用；不要改旧记录或伪造SHA。保留旧Init，以当前已核对原文件运行新Init，并在现场接续记录中注明前后run_id。定义是否一致可比较旧导出的`original_taxonomy.items`与新回执；不能据此宣称源文件字节完全相同。

```powershell
python run_faultaudit.py --state STATE trigger-workflow init `
  --modes '原30条CANN模式库.xlsx' --taxonomy 'D:\project\typora\trigger_library.md' `
  --v4 '原V4.md' --expected-mode-count 30 --work-root work/runs --executor opencode
# 已有原库Init：先配置实际原V4（如尚未配置），再启用Builder。
python run_faultaudit.py --state STATE trigger-workflow configure-baseline --run INIT_RUN_ID --expected-mode-count 30
python run_faultaudit.py --state STATE xlsx-workflow next --run INIT_RUN_ID
```

`init`默认Builder且要求V4；`--simple-v5`保留0.1.16单项稀疏流程，`--legacy-dense`保留旧密集流程。Python API的`start_init`仍须显式`baseline_builder=True`。A1完成一条后，该条即可派发独立A2/A3/A4，不等待其他条的历史证据：

- `baseline_define`：原定义、真实`failure_mechanism`、对象、表现、输入/执行前提、范围和排除边界；每个明确陈述引用本地原单元格。
- `baseline_v4`：独立评估V4主题/条件类/构造，选中构造给出可读的设计建议和缺失条件，S5只是条件类，不继承其全部构造。
- `baseline_api42`：使用原始42，独立判断，不读取映射补标签。缺条件为信息不足；明确非API依赖才可整体不适用。
- `baseline_execution`：E1-E5、可用引用/采集元数据和证据缺口。它没有实际读取网页或执行硬件的能力，不会伪造核验状态。
- `baseline_review`：四阶段全完成后，在同一完整模式集合上审查六维关系；每个维度必须说明发现或缺口。证据键按阶段/评估限定，避免把两项任务的F1当同一事实。不自动合并。

仍由主协调器通过`next/submit/drive`推进，现有新上下文子agent返回指定schema及OUTER hash；新CLI适配器已识别全部五种任务。不要在每10条之后申请继续。程序检查完整序列化请求预算；默认48,000不变。根据现场真实执行器容量设置`FAULTAUDIT_MAX_INPUT_CHARS`，所有操作保持同值，变更会使旧任务失效。超限/执行器上下文不足明确BLOCKED，不删定义/模式/段落。只有完成四阶段与横向审查后才允许finalize；REWORK_REQUIRED不能冻结，READY_WITH_GAPS需要显式`--allow-pending`且版本仍标临时，不变成来源证实。

```powershell
python run_faultaudit.py --state STATE trigger-workflow export --run INIT_RUN_ID
python run_faultaudit.py --state STATE trigger-workflow finalize --run INIT_RUN_ID
# 存在已审查、明确保留的缺口时，由操作者明确选择finalize --allow-pending。
```

只输出`baseline_30_modes.html`（主要入口）、`baseline_30_modes.json`、`baseline_42_api_mapping.tsv`、`baseline_v4_mapping.tsv`。阶段未完成时允许导出进度，显示UNASSESSED/NOT_FROZEN，不能当作30条分类已完成。Baseline v1绑定原42回执、模式定义、A2/A3/A4、横向审查及策略，输入/证据/策略变化使当前头失效，保留旧版本。MODE_DEFINITION、SOURCE_VERIFIED、HARDWARE_VALIDATED分开；缺历史Wiki不会让原定义及条件归类全部变UNKNOWN。

Codex本轮仅做合成数据的定向验证和原30条输入/派发预检；实际30条语义分类、内网访问、执行器上下文容量及新worker现场安装由OpenCode验收。不得把合成响应或文件桥接跑通说成模型完成了30条。

# OpenChamber / OpenCode 接入与验收

对应核心0.1.16，以下保留底层文件协议验收步骤。结构化XLSX的采集入口仍是xlsx-workflow，模式归类用trigger-workflow，主审查报告为HTML；Word/PPT、任意布局XLSX和时间范围收集为TODO。OpenChamber是现场前端，文件任务由它连接的OpenCode执行；OpenCode可完成采集与模型判断。本包只安装项目模板、发布文件任务、接收结果并运行本地门禁，不启动OpenChamber，也不包含服务客户端。

以下步骤是执行手册，尚不代表真实OpenChamber 2.5.2、OpenCode 2.1.4/2.2.0、内网登录或DeepSeek已联调。`doctor`通过只证明本地依赖可用。

## 0.1.16 / V5：先原30条，后62条候选

本轮按用户要求先上传代码，只做部分验证，不跑完整回归或Codex端到端。以examples/v5_partial_validation.json为本版记录，前版696项不可作新版证明。原30条语义分类未验收前，不恢复62条批量分类。原库、V4正文、Init、现场state、私有响应和工作簿不公开上传。

备份state和任务目录后，在原Init启用V5；原15项聊天候选目录不是原30条CANN库。新建CLI Init默认稀疏，Python API为兼容旧调用需sparse=True。已有V4/42定义原样冻结，V5只是分类合同，不是改写分类库。

```powershell
python run_faultaudit.py --state STATE trigger-workflow configure-v5 --run INIT_RUN_ID
python run_faultaudit.py --state STATE trigger-workflow next --run INIT_RUN_ID
# 每个trigger_classify请求交现有独立fault-audit-worker，再按原文件协议submit。
python run_faultaudit.py --state STATE trigger-workflow export --run INIT_RUN_ID
# report.html是主要审查入口，report.json保留当前完整审计；--xlsx按需生成四表索引。
```

保持既有显式预算；本版不自动提高默认48K。完整定义仍传入，超限仍阻塞。V5返回SparseAssessment：只列有据类别，所选类别完整核对Requires/Skip；正标签均有label_links，scheme/version/detail/fact/scenario一致。所有scenario_id均为本assessment局部ID，同名s1不跨资料合并。未选择是NOT_ASSESSED，不是排除；BRANCH_ONLY只说明当前识别到实现/执行/环境依赖。无标签保留具体信息缺口。候选建议与正式decision分开，无自动ACCEPT或入库。

设计是单独可选阶段；需要时用configure-v5 --with-designs，复用既有子Agent，卡片绑定一个本地情景。组合统计由程序计算，case与mode、规则版本和描述/确认轴分开；旧结果无情景时不推断同情景。HTML图柱和数量可反查来源，灰点只表示未关联。停止任务不等于根因已证实。

合同变更沿用哈希失效机制；旧请求拒收，原响应/人工历史保留。完成原30条语义复核再finalize；信息不足可形成READY_WITH_GAPS，不能自动当正式基线完成。后续确需临时基线时明确使用已有--allow-pending-baseline；62条来源全集重审、算子根因分层及目标机器实际执行留给下一阶段，不把本轮前置检查冒充完成。

## 0.1.15：V4规则与设计卡接入

本阶段没有E方法的设备执行器。先备份state与任务文件，在Init使用`configure-v4 --run INIT_RUN_ID --source 实际V4.md`，或初始化时增加`--v4`。原42、修订42、V4及映射分版本冻结，不改旧定义。新策略会使旧请求、分类、设计卡和基线失效，原文及人工历史保留；完成新版分类和设计后重新finalize，再建立绑定新基线的关联增量run。禁止把旧人工ACCEPT转移为新版裁决。

分类响应新增完整`v4_rows`及逐构造检查；`rows`仍为独立修订42兼容轴。原文与规范Requires/Skip同时提供；族覆盖条款以`family_requires_override/family_skip_override`为准。映射方向和规则版本明确，但不得据映射复制标签。I3完整适用要有合法驱动实参、算址公式、位宽/提升、边界单位和容量；C2/C4的输入驱动分派需派生事实与完整路径谓词，不能把loopRpSize填成API控制。Branch3对照绑定目标调用，同实参/同二进制不要求干扰者使用相同参数。

`trigger_design`直接使用OUTER hash和DesignResponse，由现有新子会话执行；不使用model envelope。任务完整提供选中类别规则及对应指导案例，说明未选范围。设计卡保留单一子问题事实，记录变量、边界、参考、路径、检查、规程和能力缺口。E2/E4/跨流要明确目标、参与者实参与输出归属及串行基准；跨流另列event记录/wait位置。能力不足不是语义不适用，未命中路径不是已覆盖；当前执行只能NOT_RUN。

文件响应必须是`payload.response_schema`规定的原始对象。`validate_assessment`返回系统内部normalized结构，包含派生版本/处理状态等字段，不能把返回值再当模型响应发布；应校验原始对象后写原始对象本身。格式拒收后保留原attempt，使用`next`返回的新attempt路径修正，不覆盖旧文件，也不提交`review_required`等系统字段。

已接收的解释如发现明确错误，用`trigger-workflow reassess --run RUN_ID --subject-id SUBJECT_ID --reason "具体解释错误及需重核的边界" --requested-by opencode`请求定向重评。该操作仅推进目标subject的输入修订，理由不是来源证据或人工裁决；原始单元格、旧请求/响应及人工历史不改。重复的待执行请求保持幂等。随后使用`next/submit`实际重判；若影响Init，重新维护并finalize后，以新基线建立明确关联的增量run。不要直接改写已接受响应，不为普通未知或补齐字段反复重评。

先验收文件调度、分类和设计卡，再单独验收实际输出预填、线程交错、跨流等待、存储复用、多rank及NPU执行。本机代码先上传后的Codex批次验收已完成：15项声明Init；30条、72个必要子问题中71项当前有效，1项完整输入246,540字符超过240,000试验预算而阻塞；30份设计只覆盖选中的36个子问题，均未设备执行。定向Init重评后，旧基线与依赖实际失效；新run显式复核复用不受影响的结果，未伪称全部重新调用模型。重复next和submit无重复工作，strict退出2对应60项待核、0错误。这些是Codex隔离验收，不是实际OpenChamber/OpenCode/DeepSeek或Wiki/DTS联调；详见VALIDATION。默认预算48K未变，现场完整输入或会话容量不足都明确阻塞；不修改hash强行接纳旧响应。

## 0.1.14：条件优先分类与升级

先备份现场 state 和任务目录，再运行本机实际解释器的完整回归。此版变更分类策略，原 0.1.13 分类请求、判断和冻结基线会过期，原资料、旧响应和人工历史保留。Init 可在原运行维护：重新 `next/submit` 完成新分类，再 `finalize` 冻结当前条件索引。增量运行若绑定旧冻结基线，应保留其历史，使用新 Init 基线建立明确关联的后续 `classify` 运行；不要直接改写旧基线或自动继承人工 ACCEPT。

已有资料和摘要优先复用，不因条件未知增加搜索。分类请求的 `evaluation_order` 为条件事实、42项、Branch、机理、原库对照、建议；每项仍是一份完整请求。外部 Agent 需理解新增的 `condition_facts`、逐谓词 `condition_fact_ids` 和 Branch `category_checks`，完整核对 42 项及已定义六个叶子。原单元格明确的条件可以先按描述分类，网页证实另列。训练仍分类、入库范围另判；未明确输入边界、API参数、构建路径或同实参同二进制时，不猜测标签。多子问题仍各自执行，不能拼接。

新规则不要求换模型或采集客户端，原 OpenChamber 原生子 Agent、`next/submit/drive` 和命令适配器继续使用。默认 48,000 字符预算保持；完整请求超限则 `INPUT_TOO_LARGE`，会话读不全则 `EXECUTOR_CONTEXT_LIMIT`。本机 160,000 字符试验配置不应自动带到现场。先用偏移溢出、平台差异、中间 Inf、内部非确定性和多子问题等代表记录验证，再恢复整批推进。

后续 run 的续跑对账还须包含既有检索停止记录。仅搬入快照和比较，可能再次派发检索或选中另一份已保留候选；不要把“已完成分类”当作队列已结束。复用原检索时核对原记录、已执行查询及范围，保留原执行时间、人员和轨迹，明确注明本轮没有新检索。新资料或比较使依赖过期时，重评实际受影响的子问题，保留旧响应；最终再连续两次 `next` 检查无重复任务。停止检索不代表 `NO_MATCH`、根因证实或未知条件已消除。

## 0.1.13：来源定义初始化与续跑

Init 如明确只依据用户提供的描述，使用 `trigger-workflow init --basis SOURCE_DEFINITIONS`；默认的历史网页取证路径保持不变。声明明细、42 类输入触发判断和正式网页核验分别保存，不把声明基线 READY 当作故障根因已证实。后续新案例仍按来源策略检索和对照，完整 `declared_comparison` 只产生整理建议；报告的“声明定义对照”与正式模式建议分列。Init 输入、冻结内容与私有响应不在公开仓库中，目标机器需要另行接收或重新初始化。

本机隔离验证显式使用 160,000 字符预算，产品默认仍为 48,000。这不是现场模型容量保证。先确认目标会话能完整读取请求；若读不全，返回 `BLOCKED/EXECUTOR_CONTEXT_LIMIT`。不要删库条目、只读前缀或把摘要选段说成全文。预算、规则或实际输入变化会使旧请求失效；应重新生成受影响任务并实际复核，不能修改旧 hash 冒充新执行。保留旧 run、响应和人工历史，备份后再续跑。

## 2026-11-06：25+5 历史试验异机继续

以下是 0.1.12 的历史停止点，与 0.1.13 新的独立验证 run 分开。停止点和未完成事项见 [VALIDATION](../VALIDATION.md)；公开仓库不含私有 SQLite、原库、内部链接或模型原始响应。升级后以代码、策略和输入身份检查结果是否仍有效，不把版本号当作输入身份。

私有交接包需另行拷贝到目标机器；仅克隆 GitHub 不能恢复这批历史。包中的 `checkpoint.json` 是停止点，旧 `manifest.json` 是准备阶段记录，不能用它的初始状态判断试验是否执行。包保留原始尝试、未提交文件和两个相关 run；不得自动把未提交文件接纳为结果，也不得把协调器的隐藏留出答案交给检索子 Agent。

优先在 Windows 按原绝对路径恢复项目及 `work/pilot-25plus5-20261106`。采集快照和工作流目录包含绝对路径，当前没有通用路径迁移命令；路径不同或不能安全复用时，保留旧库为历史，建立明确关联的后续 run，重新导入资料并生成受影响的语义任务，不用批量替换已签名 JSON 或修改旧 hash。私有包包含原输入与触发定义的副本及 hash，原文件路径只是来源身份，不能为了恢复而改写出处。

在项目根目录使用目标机器实际 Python，先执行完整回归。下面仅查看现有试验并生成当前合法任务，不自动启动真实搜索：

```powershell
$PythonExe = 'python' # 目标机器实际解释器，安装 requirements.txt
$PilotRoot = Join-Path (Get-Location) 'work/pilot-25plus5-20261106'
$PilotState = Join-Path $PilotRoot 'state'
$PilotRun = 'run-20261106T111207Z-99fa76e5'
$env:FAULTAUDIT_MAX_INPUT_CHARS = '48000'
& $PythonExe -m unittest discover -s tests -v
& $PythonExe run_faultaudit.py --state $PilotState trigger-workflow status --run $PilotRun
& $PythonExe run_faultaudit.py --state $PilotState trigger-workflow next --run $PilotRun
```

`run-20261106T110521Z-6c3ec768` 只是保留的准备阶段 run，不是本次继续的目标。保存代码字节、预算及来源配置决定任务有效性；`.gitattributes` 要求 LF。目标机器指纹不一致时按正常失效机制重新生成请求，保留旧响应，不能强行恢复旧判断为当前。当前执行者仍为 `codex`；OpenChamber 可先代协调这个原 run 的文件任务，但结果 `producer.executor` 必须满足请求合同，不能把实际 OpenCode 改名为 Codex。需要原生 `opencode` 执行身份时另建关联后续 run，使用 `--executor opencode`，保留旧试验以便对账。

续跑顺序：先核对那条说明与绑定不一致的抓取阻塞，再恢复有效任务；完成或明确阻塞 25 条 Init 后才可尝试维护试验基线，之后用保留的 5 条无链接输入走正式增量流程。试验基线始终不是正式 30 条基线，不能据此修改正式库。5 份留出预检可以作为线索，不可冒充已通过正式映射。Wiki 本轮显式 `NOT_SUPPORTED`，GitCode/GitHub 可用；恢复 Wiki 时通过 `set-sources` 显式改策略，重新生成旧策略依赖，不把未检索写为 `NO_MATCH`。站点登录失败保留阻塞，其他记录继续推进，不每十条请求继续授权。

正文必须保留实际取得的原文；翻译、分析与猜测放在采集说明中。引文在快照里存在不等于网站原文真实，需核对采集观察与实际页面。公开报告的 632 项回归是本机证据，目标机仍需重跑同一命令并记录解释器、依赖、实际 provider/model 与工具权限。

## 0.1.11 默认：原生子 Agent 或真实 CLI 适配，整批持续推进

OpenChamber/OpenCode **支持原生子 Agent 和 Agent 搜索**，不是只能由用户逐条取证。OpenChamber 2.5.2 的[发布记录](https://github.com/openchamber/openchamber/releases/tag/v2.5.2)列出子 Agent 会话；OpenCode 的 [Agents](https://opencode.ai/v2/docs/agents/) 和 [Tools](https://opencode.ai/v2/docs/tools/) 文档说明独立子会话、搜索及工具权限。现场实际服务版本和工具目录仍须确认，不能把功能存在等同于本项目已接通。

两种执行路线选一条，使用同一套核心任务和门禁：

1. **OpenChamber 原生路线**：主会话循环调用 `xlsx-workflow next`，只持有任务 ID/状态/文件路径。以现场可用的 `subagent`/Task 工具启动 `fault-audit-worker` 新子会话，给一项 request 路径、指定 response 路径与完整处理要求；不要传整批正文，也不要继续另一任务 session。子会话完整读资料、实际搜索/采集或判断后写响应，返回 ID、状态和路径，由主协调器 submit。语义并发 2，Edge 采集串行 1。已有整批授权不每 10 条询问继续；登录按站点集中交接，真实争议保留异常。持续至所有目标已处理或明确阻塞且没有可执行工作，最后 export。
2. **CLI driver 路线**：下面的适配器真实执行 `opencode run`，一项任务新建一次 CLI 会话，不使用 `--continue`、`--session` 或 `--fork`。程序调用 CLI，模型服务、搜索和浏览器仍由 OpenCode 管理，不另建 HTTP/模型客户端。任务出错只隔离该项，子任务不写 SQLite。

先用原安装器安装包含 `.opencode/agents/fault-audit-worker.md` 的项目模板。其 mode=all 可作为原生子 Agent，也可由 CLI 选择；不硬编码 provider/model，不改变全局权限。旧模板有改动时安装器仍保留冲突并拒绝覆盖，先合并本项目模板，不能靠删除现场 state 解决。

### CLI 预检与命令配置

`$PythonExe`、`$CoreRoot`、`$ProjectRoot`、`$OpenCodeExe` 必须是实际后端可访问的解释器、核心、项目和 CLI 路径。`$AuditState`、`$AuditRunId` 使用原现场明确运行或独立试验运行，先备份再升级。

```powershell
& $PythonExe (Join-Path $CoreRoot 'scripts/run_opencode_agent.py') `
  --project $ProjectRoot --opencode $OpenCodeExe --preflight

$AgentArgv = @($PythonExe, (Join-Path $CoreRoot 'scripts/run_opencode_agent.py'),
  '--opencode', $OpenCodeExe, '--project', $ProjectRoot,
  '--request', '{request}', '--response', '{response}', '--timeout', '900')
$AgentCommandFile = Join-Path $ProjectRoot 'work/opencode-agent-command.json'
New-Item -ItemType Directory -Force -Path (Split-Path $AgentCommandFile) | Out-Null
$AgentArgv | ConvertTo-Json | Set-Content -LiteralPath $AgentCommandFile -Encoding utf8
& $PythonExe (Join-Path $CoreRoot 'run_faultaudit.py') --state $AuditState `
  xlsx-workflow drive --run $AuditRunId --agent-command-file $AgentCommandFile `
  --workers 2 --max-attempts 2 --timeout 1000 --browser-timeout 1000
```

适配器先检查实际 CLI 的 `--version`、`run --help` 和 `--help`，确认文件、JSON 输出及 Agent 参数后才启动任务。需要连接 OpenChamber 已运行的同机服务时，可在适配器 argv 增加 `--server-url <实际无凭据服务地址>`；根据现场 help 选择受支持的 attach/server 选项，不猜版本。项目 cwd 始终显式；若服务在别机，服务目录和文件路径必须另行核验。CLI 版本不冒充所连后端版本；预检中的 Edge、搜索、子 Agent 工具及实际模型均为 NOT_PROBED。认证沿用既有 OpenCode 环境，不把密钥放进命令文件。

### 现场必须完成的能力验收

- 当前后端能读取一个完整请求并写指定响应；实际新 session 与生产者信息可追溯，不把其他模型标成 DeepSeek。
- 主会话能启动独立子 Agent，或 CLI 每次新 run 确实不继承另一案例聊天；单条失败后其他任务继续，中断续跑不重复派发。
- 附加到已有 OpenCode 后端时，实际验证超时/取消能停止对应远端子会话及 Edge 操作；本机进程超时测试只证明本地命令退出。后端未确认停止前不要重试该浏览器任务，避免遗留操作与新任务争用页面。
- 配置的 Agent 搜索工具实际可用。由原单元格抽取 `search_facets`，依据结果有限调整查询，记录 `search_attempts`；不能只列一套未执行的搜索词。
- 既有 Edge 工具能读取登录后的 Wiki 正文。用户手动登录；同站点集中交接一次，恢复相关任务。官方 [Browser 说明](https://opencode.ai/v2/docs/tools/#browser)不保证自动附加任意现有 Edge 会话，必须使用现场已有连接验收。
- Wiki 目录、仅标题、登录、未渲染、提取失败都有实际 `capture_observation`，不会被当成完整正文或查无匹配；相关目录子页能定向读取。
- 读工具可能限制整页大小及单行长度。原 JSON 的长字符串必须完整读取；必要时通过本地工具/Python/Node 按字符切片补读，不能误把翻页当成恢复被截短的一行。输入读不全则阻塞，不静默删段或库条目。
- 同资源链接别名只抓一次、同快照摘要共享，但不同适用子问题仍独立执行；目标范围和冻结库完整唯一。

当前 Codex 回归与公开资料实机不能代替上述内网/真实模型现场验收。最终只交付一个排名 XLSX，保留真实阻塞；`COMPLETE_WITH_PENDING` 或严格校验退出 2 不等于程序崩溃。下面为旧版本底层接口的兼容验收，不覆盖本节默认入口。

## 1. 在实际工具执行端安装

填写已存在的核心目录、OpenCode项目目录和实际Python。OpenChamber与OpenCode后端不在同一机器时，路径必须是后端工具能访问的路径，不能把前端电脑路径当作后端路径。

```powershell
$PythonExe = 'python'
$CoreRoot = '实际核心目录'
$ProjectRoot = '实际OpenCode项目目录'
$CoreEntry = Join-Path $CoreRoot 'run_faultaudit.py'
& $PythonExe $CoreEntry --version
& $PythonExe -m pip install -r (Join-Path $CoreRoot 'requirements.txt')
& $PythonExe $CoreEntry doctor
& $PythonExe (Join-Path $CoreRoot 'scripts/install_opencode.py') --project $ProjectRoot
$AuditEntry = Join-Path $ProjectRoot '.opencode/skills/fault-evidence-audit/scripts/run_audit.py'
& $PythonExe $AuditEntry doctor
```

安装器生成项目`.opencode`技能、命令和`core-location.json`，不改全局设置或AGENTS.md，不覆盖不同内容的旧模板。发现冲突时先保存旧文件再合并或在干净项目安装，不能用清空state来处理模板冲突。

## 2. 在OpenChamber确认实际会话

在OpenChamber打开同一项目，确认实际连接的OpenCode服务版本、项目路径，以及会话是否能读取技能并执行本地命令。PATH中的`opencode --version`不能替代所连服务的版本。若项目命令加载成功，可使用`/evidence-audit <具体任务>`；未加载时先检查项目模板和服务端目录，不声称命令已生效。

在该OpenCode环境配置provider/model、采集工具与站点登录态。指定DeepSeek时，必须实际选择或委派到DeepSeek并保留现场执行记录；其他当前模型不能改名为DeepSeek。核心只记录producer报告的路由信息，不验证服务后台的真实路由。

Wiki、DTS、GitCode、GitHub、CodeHub的搜索、正文/分页/附件/评论/Diff读取与失败重试都由现场工具完成。登录和正文读取要单独验证；本地依赖、模板安装和模型文件协议通过都不能代替这项验收。

## 3. 先做隔离的OpenCode合成执行

使用新的测试目录和state，不操作真实批次。现有`seed_codex_pilot.py`只生成合成输入、资料包和独立验收预期，不生成模型答案、不创建state；文件名不限制执行者。此处选择OpenCode。不要把`expectations.json`交给执行模型，也不要使用历史固定数量的`verify_codex_pilot.py`证明本版OpenCode通过。

```powershell
$PilotRoot = Join-Path $ProjectRoot 'work/opencode_pilot_018_new'
$PilotState = Join-Path $PilotRoot 'state'
& $PythonExe (Join-Path $CoreRoot 'scripts/seed_codex_pilot.py') --out $PilotRoot
$PilotImport = & $PythonExe $AuditEntry --state $PilotState import --input (Join-Path $PilotRoot 'inputs/cases.json') --source-kind ORIGINAL_WEEKLY --catalog (Join-Path $PilotRoot 'inputs/catalog.json') --catalog-sheet INFERENCE --catalog-scope INFERENCE --expected-catalog-count 98 | Out-String | ConvertFrom-Json
$PilotRunId = $PilotImport.run_id
if (-not $PilotRunId) { throw '未取得run_id，请先查看导入错误。' }
& $PythonExe $AuditEntry --state $PilotState ingest-evidence --run $PilotRunId --package (Join-Path $PilotRoot 'inputs/evidence.json')
& $PythonExe $AuditEntry --state $PilotState evidence-plan --run $PilotRunId --out (Join-Path $PilotRoot 'plan_01.json')
& $PythonExe $AuditEntry --state $PilotState model-tasks --executor opencode --run $PilotRunId --out (Join-Path $PilotRoot 'requests_01.json')
```

合成资料已经在本地，不访问其`example.invalid`网址。请OpenCode会话只读取`requests_01.json`，按每项instructions、payload与expected_contract生成`results_01.json`。完整保留run_id/task_id/request_hash以及比较任务的work_id；producer使用executor=opencode、实际opencode_version/provider/model/session_id。未知版本如实说明，不伪造登录、工具访问或模型身份。空result、旧答案或只在聊天中说“完成”都不是有效提交。

```powershell
& $PythonExe $AuditEntry --state $PilotState submit-model-results --executor opencode --run $PilotRunId --file (Join-Path $PilotRoot 'results_01.json')
& $PythonExe $AuditEntry --state $PilotState model-tasks --executor opencode --run $PilotRunId --out (Join-Path $PilotRoot 'requests_02.json')
```

继续由OpenCode执行下一批，再用新的results/requests文件名提交和导出。摘要、逐work比较、全库映射按依赖解锁，不预设只有三批或固定任务数。无法完整处理时报告BLOCKED与原任务标识，不能裁剪payload后复用原Hash提交。

```powershell
& $PythonExe $AuditEntry --state $PilotState status --run $PilotRunId
& $PythonExe $AuditEntry --state $PilotState validate --run $PilotRunId --strict
$LASTEXITCODE
& $PythonExe $AuditEntry --state $PilotState export --run $PilotRunId --out (Join-Path $PilotRoot 'report')
```

严格退出2表示仍有缺口或异常，不靠批量ACCEPT清空。由独立检查者核对任务/结果绑定、原引文和单元格、多issue工作隔离、98个冻结库ID不漏项、未知与部分资料保留。分别记录“文件协议已验收”“实际OpenCode执行已验收”“真实站点采集已验收”，未执行的项写未验证。合成通过不能当作真实故障准确率或内网采集通过。

## 4. 切换为真实资料流程

按核心README导入真实来源并保存明确run_id；已有批次先备份完整state，优先在原路径同run继续，不使用latest猜批次，不将真实内容加入公开样例或交付包。

```powershell
$AuditState = '实际state目录'
$AuditRunId = '实际run_id'
& $PythonExe $AuditEntry --state $AuditState evidence-plan --run $AuditRunId --out 'work/plan_real.json'
& $PythonExe $AuditEntry --state $AuditState fetch-tasks --run $AuditRunId --out 'work/fetch_real.json'
```

现场工具读取清单中的已有资料，并按[采集合同](.opencode/skills/fault-evidence-audit/references/collection.md)生成本地包；随后运行：

```powershell
& $PythonExe $AuditEntry --state $AuditState ingest-evidence --run $AuditRunId --package 'work/evidence_real.json'
& $PythonExe $AuditEntry --state $AuditState model-tasks --executor opencode --run $AuditRunId --out 'work/requests_real_01.json'
```

OpenCode执行、保存并提交结果，循环方式与合成流程相同；显式推进可用`run --run <id> --mode opencode --resume`。文件导出不会自动启动或调用模型会话。

默认最少一份资料，无强制来源；已有Wiki/GitCode/GitHub/CodeHub或DTS任一可用资料就停止新增搜索，DTS不默认补Wiki或PR。已有未读/失败资料先处理，所有已有引用仍整理。需要强制数量或来源时使用README的set-search-policy；required_sources为AND，required_any_sources为OR，case策略完整覆盖run策略。一满足就停止，不为填齐证据类型扩搜，不伪造user_confirmed。

`search_control.satisfied`只控制搜索目标；根因归属、故障库覆盖、Agent待补和人工异常仍分别判断。认证失败、仅搜索摘要、资料冲突和容量不足要保留真实原因。真实服务的验收证据以现场实际工具和模型执行记录为准，本机doctor或合成协议回归不提供该证明。
