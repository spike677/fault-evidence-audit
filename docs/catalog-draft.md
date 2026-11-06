# 模式草案工具（0.1.10，兼容 0.1.9）

0.1.10 的 `--expected-additions` 为可选：省略时由 Agent 根据完整原库自主决定动作和新增数量；明确指定“只新增3条”时仍严格执行。结构化 XLSX 的默认完整流程使用 README 中的 `xlsx-workflow`，自动连接本层并只交付一个排名工作簿；下面独立命令仍用于单独检查与调试。

`catalog-draft prepare / validate / export` 复用当前运行的来源、独立资料事实、`work_id`、冻结原库与有效性门禁，只读打开 SQLite。输出写到 state 之外的新位置；不更新正式库、不创建人工 ACCEPT。

## 1. 准备输入

先使用已有导入与采集流程，取得当前资料摘要和必要事实对照。`investigation-plan` 中可以查看内部 `case_id`、来源和缺口。这里的 `--case-id` 使用其内部 ID，不自动把 WB 编号当作 ID。

```powershell
$PythonExe = 'python' # 使用安装了 requirements.txt 的实际解释器
& $PythonExe run_faultaudit.py --state work/state investigation-plan --run RUN_ID --out work/investigation.json
& $PythonExe run_faultaudit.py --state work/state catalog-draft prepare --run RUN_ID `
  --case-id INTERNAL_CASE_ID_1 --case-id INTERNAL_CASE_ID_2 --case-id INTERNAL_CASE_ID_3 `
  --expected-additions 3 --out work/catalog-input-r1
```

`prepare` 必须指定本轮选定记录，预期新增条数可选，并保留完整冻结库。成功输出 `request.json` 与 `response_template.json`。请求包含指令、完整响应 schema、当前资料事实、原单元格、工作范围、库映射和来源缺口，并核算整份序列化请求的字符数。

默认预算仍为 48,000 字符，配置键沿用 `FAULTAUDIT_MAX_INPUT_CHARS`。超限时退出 2，仅输出 `blocked.json`，其中保留完整上下文及大小、预算和 `INPUT_TOO_LARGE` 原因，不生成可执行请求。不通过截取正文、事实或库条目让任务成功；执行会话读不全时也应报告阻塞。

原库不能为空、ID 必须唯一且具备冻结来源身份。旧运行缺少冻结库元数据时先按现有导入规则处理，不猜测或原地补造身份。升级前按现场流程备份；核心策略变化会使旧模型结果失效，按小量代表记录重新生成必要任务，不改旧 hash 或继承旧 ACCEPT。

## 2. Agent 填写草案

把完整 `request.json` 交给 OpenChamber/OpenCode 或 Codex。执行者复制模板到新的 `response.json`，依据请求内的 schema 填写 `proposals`，如实填写 `executor / created_by / producer`。未报告的 provider、模型或会话保留 `UNREPORTED`；这些信息是执行者声明，不证明实际服务路由或执行。

这一步是模式草案文件往返，使用下节 `catalog-draft validate` 验收，**不要**交给仅接受摘要/关联/库映射任务的 `submit-model-results`。没有启动模型服务的隐藏调用。

每个提案的主要内容：

- `action` 为 `ADD / REFINE / APPEND_CASE / NO_CHANGE`；后两类调整现有模式时指定 `target_item_id`。`REFINE` 也必须指定目标。
- `case_ids / work_ids` 保留原记录和具体子问题。每个选定 case 必须出现在草案中；多个案例可以共同支持一条模式。同一快照的不同子问题分别提案，不在一条提案中串用。
- `row` 填完整 15 列；三级仅“计算算子、通信算子、图引擎”，四级仅“算子计算、算子接口、数据切分、图融合优化”。模式名称抽象，具体机理写入根因。
- `field_bases` 为 15 个字段分别给依据类型、说明、当前 `fact_ids` 或准确 `source_cells`。来源单元格包含 `case_id / field / cell / quote`。引文必须存在于原表，不能用资料标题或 URL 替代机制。
- `coverage_comparisons` 对冻结库每个唯一 ID 比较一次，说明 `SAME_PATTERN / PARTIAL / DIFFERENT / UNKNOWN` 及理由；不得删减原库。存在同一模式时不用 ADD 重复新增。
- `evidence_scope=CASE_ROOT_CAUSE` 要求所涉每条记录有当前根因候选支持；`INDEPENDENT_TECHNICAL_PATTERN` 只描述资料技术机制，不确认客户事件。`implementation_owner` 单独记录实际实现归属，二级 CANN 不是内置缺陷证明。
- 事实依据为 `CITED_FACT / CODE_INFERENCE / SOURCE_CELL`；抽象分类用 `ABSTRACTION`。检查、处理与注入列只允许 `PROPOSED / UNKNOWN`，注入状态固定 `NOT_EXECUTED`。旧表根因陈述可以保留，但输出仍标“原表陈述（未核验）”。
- 未知字段显式填写“未知…／待核验…／暂无…”，不能把缺失变成否定。保留 `unknowns / conflicts`，完成一次 `self_check`。无法消解的冲突进入草案异常展示，不掩盖为成功归因。

程序检查结构、引文存在、当前依赖与范围，不能机械证明模式抽象或根因语义正确。资料作者验证、代码推断和本机复现不能互相替代。

## 3. 校验并导出

```powershell
& $PythonExe run_faultaudit.py --state work/state catalog-draft validate --run RUN_ID `
  --request work/catalog-input-r1/request.json --draft work/response.json --out work/validation-r1.json

& $PythonExe run_faultaudit.py --state work/state catalog-draft export --run RUN_ID `
  --request work/catalog-input-r1/request.json --draft work/response.json --out work/catalog-output-r1 --xlsx
```

两处入口共用校验。每次重新读取当前状态，对照请求 hash、策略/预算、原库、输入、快照、摘要、判断及复核依赖；过期请求拒收，历史保留。重复执行到新目录得到同样的内容，不重复追加；已有目录或文件拒绝覆盖，修改草案后使用新输出位置。

退出码 0 表示草案结构与来源校验通过或准备就绪；2 表示超限或业务校验阻塞；1 表示文件、合同结构、过期请求或可选运行时错误。`VALID_DRAFT` 是草案有效，不是正式入库或真实语义已证实。

基础输出不依赖 Node：

- `request.json / catalog_draft.json`：对应请求、原 Agent 草案及完整逐项覆盖理由。
- `baseline_original.json`：冻结库条目与原字段无损副本。
- `validation.json`：计数、依赖、证据范围、根因状态与异常。
- `workbook_data.json / merged_preview.tsv`：展示数据与共有字段合并核对。

指定 `--xlsx` 时复用现有 ArtifactTool 适配器生成 `catalog_draft.xlsx` 和预览。配置仍用 `FAULTAUDIT_NODE`、`FAULTAUDIT_NODE_MODULES`，见主 README。可选 XLSX 失败时基础文件仍保留，不静默截断长单元格；保存后运行时返回非零也会如实记录警告并检查新文件。

工作簿包含新增 15 列草案、共有字段合并核对、草案状态和字段依据；有既有模式调整时另列建议表。REFINE/APPEND_CASE 只展示建议，旧条目不改写；JSON 保留原字段，TSV/XLSX 只做公式注入的展示转义。原库只有四个核心字段时，30＋3 的核对视图不会冒充 33 条完整 15 列正式库。

本工具沿用证据计划的搜索条件：整理全部已有引用，默认一份可用证据满足新增搜索停止条件。库覆盖未知、缺版本或缺注入工具不触发额外补搜。正式库采用和现场批量执行另行明确安排。
