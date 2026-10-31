# Fault Evidence Audit

故障证据核验核心。所有示例均为虚构数据，不包含客户故障记录或内部网页内容。

版本 0.1.5，2026 年 10 月 31 日。核心负责导入故障表、保存原文与引用来源、生成采集和模型任务、检查返回结果并生成复核报告。模型任务可由 OpenCode 或 Codex 会话执行，内网采集仍由具备授权与登录态的现场环境完成。当前使用文件任务往返，不包含直连模型服务的网络客户端。

目标网站包括 DTS、Wiki、GitCode、GitHub、CodeHub。真实资料由具备授权与登录态的现场工具采集；现有现场方案使用 OpenChamber/OpenCode。登录认证、搜索、正文读取、分页、附件、评论、Diff、网络重试和权限故障处理均在采集环境完成。核验核心不访问这些网站，也不保存其认证凭据；选择 Codex 执行模型任务不会自动获得这些站点的访问能力。

`fetch-tasks` 只导出待访问 URL 及其引用来源清单，不发送网页请求；`ingest-evidence` 只读取现场返回的本地证据包。模型任务交给选定的执行会话，核心仅做结果验收。

## 本版可用范围

- XLSX、CSV、TSV、JSON 导入；保留原文、文件 hash、sheet、行和单元格。
- Catalog 按工作表选择并核对预期数量，文件 Hash、工作表与作用域在同一 run 内冻结；识别“根因/进展”表头。
- 原始引用、搜索发现和人工补充分别登记；相同资料的不同引用来历保留。
- SQLite 台账、资料版本、任务依赖及请求 hash；输入变化后旧结果失效，支持恢复任务。
- 按依赖生成资料摘要、逐关联比较和全库映射任务，由 OpenCode 或 Codex 会话执行后提交结果。
- 本地结构、原文引用和业务校验；生产者元数据记录执行者、对应版本、provider、model 和会话。
- 原文引文、跨快照引用、同事件锚点、根因冲突、冻结库版本等门禁。
- 组件完整性矛盾与 PR 文件计数门禁；未验收正文和网络阻塞状态分别保存。
- `evidence-index` 反查共享资料的所有引用者、各自判断及历史版本。
- 全库逐项比较合同；未确认事件与缺失机理不标为已覆盖或未覆盖。
- JSON、HTML、Excel 可打开的 TSV；可选 ArtifactTool XLSX 适配器。
- 追加人工复核记录；项目专用 Skill 和 OpenCode V2 命令安装模板。

核心不配置模型服务地址、凭据或模型网络客户端。OpenCode 的 provider/model、实际服务、委派工具及认证由现场配置；Codex 可直接读取导出的任务并提交文件结果。文件协议不会自动启动模型会话。`mock` 仅用于离线流程演示。

本版不自动合并故障，不包含内网采集器或已认证 MCP，不自动恢复旧表根因来源，也不执行跨资料联合最终裁决。逐资料判断和冲突线索均保留，争议交人工复核。原 98 条库和原始周报需现场提供；内置 mock 演示库只有两条合成模式，另有可重建的 98 条合成模拟库，两者均不冒充真实故障库。

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

### 2. 导出采集清单并提交原文

```powershell
& $PythonExe run_faultaudit.py --state $AuditState fetch-tasks --run $AuditRunId --out work/fetch_tasks.json
```

现场工具按清单采集实际正文，保存原文、时间、落地 URL 和组件缺口，生成 `work/evidence.json`。该文件可以是单个证据包或证据包数组，字段见“采集证据包”。登录页、搜索摘要或模型摘要不能充当正文。访问失败也应提交准确状态。

```powershell
& $PythonExe run_faultaudit.py --state $AuditState ingest-evidence --run $AuditRunId --package work/evidence.json
```

### 3. 按依赖执行模型任务

以下设置为 Codex；现场使用 OpenCode 时改为 `opencode`，其余参数保持一致。

```powershell
$AuditExecutor = 'codex'
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

反查保留原始链接、搜索补链、人工补链及每条故障各自的当前判断；共享链接只提示需要交叉核查，不证明同一事件。可加 `--url '实际证据URL'` 查询一份资料。JSON、HTML 和表格数据中保留“证据反查”“库选择基准”、拒绝关联与待办。

先在 `report.json` 或 `report.html` 读取具体关联的 `judgment_id` 和库映射的 `task_id`，由实际复核人填写结论、理由和姓名；复核示例见“判断边界”。先处理关联判断，再处理依赖它的库映射。修改关联裁决会使相关映射失效，需要重新推进、执行并复核。

```powershell
& $PythonExe run_faultaudit.py --state $AuditState validate --run $AuditRunId --strict
$LASTEXITCODE
```

| 退出码 | 含义 |
| --- | --- |
| `0` | 普通 `validate` 表示结构合法；`--strict` 还要求没有待处理项 |
| `2` | `validate` 发现无效记录，或严格模式仍有缺口／待复核项；查看 `errors` 与 `pending` |
| `1` | 命令执行或输入校验失败，查看输出的 `error` 与 `message` |

部分 PR、未知映射或待人工复核会让严格验收保持 `2`，不能靠批量 ACCEPT 清空真实缺口。完成复核后重新导出报告，保留原始文件和旧版本产物。

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

所有模型结果均为建议，等待人工复核。`case_attribution=CONFIRMED` 表示模型按当前证据提出确认归属建议，仍可同时处于 `review_status=NEEDS_REVIEW`；它不是人工 `ACCEPT`。库映射也可基于有效的确认归属判断提出覆盖建议，随后独立复核，不能因“待人审”就假装原文证据不存在，也不能据此自动通过终审。

下面命令须由实际复核人在阅读证据后执行，将 ID、理由与姓名替换成真实值。`ACCEPT`、`REJECT`、`NEEDS_INFO` 是可选裁决；示例使用 `NEEDS_INFO`，不代替实际判断：

```powershell
& $PythonExe run_faultaudit.py --state $AuditState review --run $AuditRunId --judgment '待复核的judgment_id' --verdict NEEDS_INFO --reason '填写缺失证据或裁决依据' --reviewer '实际复核人'
& $PythonExe run_faultaudit.py --state $AuditState review --run $AuditRunId --mapping '待复核映射的task_id' --verdict NEEDS_INFO --reason '填写模式匹配依据或缺口' --reviewer '实际复核人'
```

裁决以追加记录保存，不改写原文或自动合并事件。未复核的映射、逐项未知及部分证据会使严格验收保持待处理。修改关联判断的裁决后，对应库映射立即失效，需重新推进任务，避免导出旧覆盖结论。

原文引文存在只是出处校验，不能机械证明结论含义正确。把真实引文错误地关联到另一个模式，仍可能通过结构校验；模式机理、触发条件和否定语境需要模型及人工语义复核。

## Codex 合成模拟：完整复现步骤

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

让 Codex 读取 `03_requests.json`，对 5 条记录各比较全部 98 个模式，写入 `$PilotRoot/03_results.json`，合计 490 项。每项 ID 必须唯一且不漏项；引用只能复用该任务有效 judgment 中相同的 `segment_id + quote` 对。模型提出的覆盖建议仍待人工复核，机制未确认的事件保持待定。

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
& $PythonExe run_faultaudit.py --state $AuditState run --run $AuditRunId --mode opencode --resume --retry-failed
& $PythonExe run_faultaudit.py --state $AuditState model-tasks --executor opencode --run $AuditRunId --out work/requests_014_01.json
```

然后由现场执行新导出的任务并按原 `task_id`、`request_hash` 提交，再继续下一阶段。旧请求和旧结果不改写、不删除；策略或依赖变化后它们只作为历史记录，过期结果不能继续作为当前关联、覆盖结论或已完成计数。任何模型建议，包括确认归属与正向覆盖，仍需真实人工复核，不自动 ACCEPT。

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

0.1.5 的回归测试使用合成任务和结果文件，不运行模型 HTTP 客户端，也不调用外部模型。本轮实际环境、测试数量与结果以 [examples/validation_result.json](examples/validation_result.json) 和 [验收记录](VALIDATION.md) 为准。2026 年 10 月 30 日由 Codex 会话执行的 [合成模拟验证摘要](examples/codex_pilot_validation.json) 是单独的历史基线，与本版回归、mock 和现场验证分开。交接包排除凭据、SQLite 运行数据、原始证据和依赖运行库，包含 `.gitignore` 及逐文件 SHA-256 清单。

## 0.1.5 统计与现场只读对账

本轮统计修复只从已有记录生成统计与差异报告，不重新提取事实、修改证据、生成业务判断或推进模型任务。网站认证、采集及实际模型执行仍由 OpenChamber/OpenCode 现场环境负责，沿用已有工具与流程。0.1.4 已有的长正文分块、整请求预算、输入作用域和策略失效机制保留，不为统计目的重写。

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

人工 REJECT 关联保留在原账与历史中；统计同时给出当前判断包含与排除 REJECT 的两种口径，不能混成一个总数。分类可能交叉，同一判断或故障可能进入多个类别，类别计数之和不必等于唯一判断总数；以明确列出的 ID 集合核对。待办理由也可能属于同一故障或同一任务，不能把理由条目数当成待处理故障数。

`confirmed_accepted` 在该报告的当前口径内，还要求 CONFIRMED、SAME_EVENT、DIRECT、人工 ACCEPT、对应快照 COMPLETE，且没有维度冲突或 claim CONTRADICTED。它是满足这些记录条件的数量，不代表离线统计重新证明了原文语义。

若报告缺少必要的过期标记、任务状态或分类元数据，当前统计也可以为 UNKNOWN/null；缺失信息不补成零，也不以旧汇总数字代填。

每轮增量要用上一轮基线报告与本轮清单共同核对。同 ID 的裁决变化、变为过期或仅重新导出不按新增判断计数。本轮新增历史记录包含本轮新增后又变为过期的项，当前仍有效的新增项另计，不能混合。`new_case_count` 指新增判断涉及的不同 case 数，不是新导入原始故障数。缺少基线时，累计已见记录可以展示，但本轮增量数量保持 `UNKNOWN`，不能将累计数量冒充本轮增量。

现场 OpenCode 做只读对账时，只读取指定 run 的现有 SQLite、报告与轮次清单，并另存派生报告；不调用导入、采集提交、模型结果提交或人工裁决来“修正”数量。记录所用文件 Hash、生成时间与口径。没有现场 SQLite 时，不猜其真实总量；若只能读到已有 JSON 报告，统计只描述该文件所含记录，不能声称已完成数据库全量核对。单凭聊天列出的数量与案例名称不足以纠正现场计数。

常规 `export` 也接受 `--baseline`、`--round-manifest`，可把统计附于 `report.statistics`。它仍走常规 Store 导出路径，不应称为对 SQLite 的绝对只读命令；现场纯对账优先使用已有 JSON 与独立 `reconcile-report`。
