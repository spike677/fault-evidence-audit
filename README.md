# Fault Evidence Audit

故障证据核验核心。所有示例均为虚构数据，不包含客户故障记录或内部网页内容。

版本 0.1.1，2026 年 10 月 30 日。Codex 侧核心负责导入故障表、保存原文与引用来源、生成采集和模型任务、检查返回结果并生成复核报告。所有模型执行及内网采集均由 OpenCode 所在环境完成。当前使用文件任务往返，不包含直连 OpenCode 服务的网络客户端。

所有目标网站访问统一由 OpenChamber 环境负责，通过其连接的 OpenCode 和现场工具执行，包括 DTS、Wiki、GitCode、GitHub、CodeHub。登录认证、搜索、正文读取、分页、附件、评论、Diff、网络重试和权限故障处理都在该环境完成。Codex 核心不访问这些网站，也不保存其认证凭据。

`fetch-tasks` 只导出待访问 URL 及其引用来源清单，不发送网页请求；`ingest-evidence` 只读取现场返回的本地证据包。模型任务同样交给 OpenChamber 环境执行，核心仅做结果验收。

## 本版可用范围

- XLSX、CSV、TSV、JSON 导入；保留原文、文件 hash、sheet、行和单元格。
- 原始引用、搜索发现和人工补充分别登记；相同资料的不同引用来历保留。
- SQLite 台账、资料版本、任务依赖及请求 hash；输入变化后旧结果失效，支持恢复任务。
- 按依赖生成资料摘要、逐关联比较和全库映射任务，由 OpenCode 执行后提交结果。
- 本地结构、原文引用和业务校验；生产者元数据记录 OpenCode 版本、provider、model 和会话。
- 原文引文、跨快照引用、同事件锚点、根因冲突、冻结库版本等门禁。
- 全库逐项比较合同；未确认事件与缺失机理不标为已覆盖或未覆盖。
- JSON、HTML、Excel 可打开的 TSV；可选 ArtifactTool XLSX 适配器。
- 追加人工复核记录；项目专用 Skill 和 OpenCode V2 命令安装模板。

Codex 侧不配置模型服务地址、凭据或模型网络客户端。OpenCode 的 provider/model、实际服务、委派工具及认证由现场配置。`mock` 仅用于离线流程演示。

本版不自动合并故障，不包含内网采集器或已认证 MCP，不自动恢复旧表根因来源，也不执行跨资料联合最终裁决。逐资料判断和冲突线索均保留，争议交人工复核。原 98 条库和原始周报需现场提供；示例库只有两条合成数据，不冒充 98 条实际核验。

## 安装与零网络演示

Python 3.10 及以上；核心依赖 Pydantic 2，读取 XLSX 另需 openpyxl。已有依赖时可直接运行源码，无需安装包。

```text
python -m pip install -r requirements.txt
python run_faultaudit.py doctor
python run_faultaudit.py --state demo_output/state demo --out demo_output
python run_faultaudit.py --state demo_output/state validate --run latest --strict
```

最后一条预期退出码为 2：演示明确使用合成资料和 mock，所有模拟任务成功也不等于真实语义核验完成。`report.html` 提供可阅读的复核报告；`report.json` 保留完整明细。

如果 Windows 的 python 指向商店占位程序，请使用实际 Python 可执行文件的绝对路径。当前开发测试使用 Codex bundled Python，不把该机器路径写入可移植代码。

## 实际资料流程

```text
python run_faultaudit.py --state work/state import --input 原始周报.xlsx --source-kind ORIGINAL_WEEKLY --catalog 故障库.xlsx
python run_faultaudit.py --state work/state fetch-tasks --run latest --out work/fetch_tasks.json
python run_faultaudit.py --state work/state ingest-evidence --run latest --package work/evidence.json
python run_faultaudit.py --state work/state model-tasks --run latest --out work/requests.json
```

现场 OpenCode 读取 `requests.json`，使用已配置的 provider/model 执行其中任务，将结果保存为 `results.json`。然后继续：

```text
python run_faultaudit.py --state work/state submit-model-results --run latest --file work/results.json
python run_faultaudit.py --state work/state run --run latest --mode opencode
python run_faultaudit.py --state work/state model-tasks --run latest --out work/requests.json
```

重复“导出就绪任务 → OpenCode 执行 → 提交结果 → 继续”直到没有待执行任务，或依赖缺失而明确受阻。摘要通过本地校验后才解锁逐关联任务，逐关联通过后再解锁全库任务。任务空不等于核验完成，须检查状态和待办：

```text
python run_faultaudit.py --state work/state validate --run latest
python run_faultaudit.py --state work/state export --run latest --out work/report
```

旧汇总表使用 `--source-kind LEGACY_TABLE`，其根因默认 `LEGACY_DERIVED_UNKNOWN`。相同输入可通过 `import --run <run-id>` 追加，记录幂等；同一 run 的故障库版本固定，换库使用新 run。

### 模型任务协议

`requests.json` 顶层包含 `schema_version`、`run_id` 和当前就绪的 `tasks` 数组。每个模型请求包含 `instructions`、`payload`、`expected_contract`、`run_id`、`task_id` 和 `request_hash`。请求不携带服务凭据。OpenCode 根据任务类型分别执行资料摘要、逐关联比较和全库映射，不以自由整理表格替代这些任务。

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

提交文件支持单个 envelope、envelope 数组，或 `{"results": [envelope, ...]}` 包装；其中每个对象都须保留对应请求的标识。

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

运行 `schemas --out schemas` 可导出本版 JSON schema。超长正文按片段完成独立提取；任何阶段无法覆盖请求中提供的内容时明确报告受阻，不静默截掉后半段。实际 OpenCode 委派方式与大资料处理能力需现场联调。

## 判断边界

同一事件需明确事件编号，或源故障描述中足够具体、在证据引文中逐字出现的事件签名，同时匹配症状、机理及触发/修复/构建特征。共享链接和同算子不能作为事件身份。原文定位只是必要条件，不能证明语义正确。

所有模型结果均为建议，等待人工复核。可用 `review --run <id> --judgment <id> --verdict ACCEPT|REJECT|NEEDS_INFO --reason <理由> --reviewer <姓名>` 追加裁决；该操作不会改写原文、伪造资料或自动合并事件。

代码库覆盖在本版指知识模式覆盖。工具实现覆盖、真实环境验证覆盖、自动故障归并和完整诊断演进图均未实现，不能从当前覆盖字段推出这些能力已经存在。

## 可选 XLSX

基础报告不依赖 Node。需要 XLSX 时配置 `FAULTAUDIT_NODE` 和 `FAULTAUDIT_NODE_MODULES` 指向可用的 ArtifactTool runtime，再使用 `export --xlsx`。该适配器不是本项目声称可自由分发的开源依赖，交接包不包含其运行库。

当前 bundled runtime 在部分成功保存后仍返回退出码 1。CLI 只接受本轮新建且通过 ZIP 完整性和工作表数量检查的文件，同时保留 `xlsx_runtime_warning`；视觉预览另存于输出目录。超过 Excel 单元格长度时明确失败，完整 JSON/HTML 仍保留。

## OpenCode V2 与交接

```text
python scripts/install_opencode.py --project <现场项目目录>
```

该安装器只复制本包的 Skill 和命令，不覆盖现有不同内容，也不修改全局配置或项目 AGENTS.md。项目长期规则的可选片段在 `integration/AGENTS.snippet.md`，由现场合并。

设置 `FAULTAUDIT_HOME` 为核心包根目录，Skill 内的 `scripts/run_audit.py` 即可调用同一 CLI。该脚本只运行本地核心，不负责建立模型服务连接。OpenChamber 2.5.2 可能连接其内置 OpenCode 2.1.4；PATH 的 2.2.0 不代表实际后端。命令加载、Skill 加载、模型任务执行及采集工具须在两个目标服务上分别验收，当前未完成现场联调。

## 开源参考与验证

复用与参考的来源、许可、边界见 [THIRD_PARTY_REFERENCES.md](THIRD_PARTY_REFERENCES.md)。没有复制受限的 Anthropic xlsx Skill。

```text
python -m unittest discover -s tests -v
python scripts/build_delivery.py
```

0.1.1 的模型协议测试使用合成任务和结果文件，不运行模型 HTTP 客户端，也不调用外部模型。交接包排除凭据、SQLite 运行数据、原始证据和依赖运行库，并包含逐文件 SHA-256 清单。
