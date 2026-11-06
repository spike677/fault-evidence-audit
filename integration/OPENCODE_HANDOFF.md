# OpenChamber / OpenCode 接入与验收

对应核心0.1.11，以下保留底层文件协议验收步骤。结构化XLSX的当前默认入口是README中的xlsx-workflow；Word/PPT、任意布局XLSX和时间范围收集为TODO。OpenChamber是现场前端，文件任务由它连接的OpenCode执行；OpenCode可完成采集与模型判断，无需Codex再代做一遍。本包只安装项目模板、发布文件任务、接收结果并运行本地门禁，不启动OpenChamber，也不包含OpenChamber/OpenCode服务客户端。

以下步骤是执行手册，尚不代表真实OpenChamber 2.5.2、OpenCode 2.1.4/2.2.0、内网登录或DeepSeek已联调。`doctor`通过只证明本地依赖可用。

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
