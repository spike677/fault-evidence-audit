# 0.1.20：A1来源物化、A2引用反馈与A3未知分类

本版基于0.1.19（55e2d53）定向修复。不更改原42、V4、CANN模式库或PrecisionTesting，不操作现场state，不启动drive或finalize。

## A1：原始事实由程序生成

新`baseline_define`使用`A1_SOURCE_SELECTION_V2`。模型返回`field_bindings`七个字段，来源选择格式如下；实际必须返回完整的任务Schema、OUTER request_hash和真实producer。

```json
{
  "failure_mechanism": {
    "origin": "MODEL_DERIVED",
    "source_ids": ["<本次manifest中的source_id>"],
    "derived_text": "从原始说明提炼的失效机理",
    "reason": "哪些原始事实支持该推导，哪些边界仍未知"
  },
  "input_trigger_conditions": {
    "origin": "UNKNOWN",
    "reason": "原定义未给出合法API参数和触发边界"
  }
}
```

- `SOURCE_DECLARATION`：只选`source_ids`，程序从原始值生成STATED声明、SOURCE_RECORD事实及完整原文引文。模型不能填写`derived_text`、字段别名、坐标、引文或`condition_facts`。
- `MODEL_DERIVED`：选真实`source_ids`并给出`derived_text/reason`，结果标为INFERRED；不要求原表有同名`failure_mechanism`列。
- `UNKNOWN`：给具体缺口，不带断言或支撑ID。

物化收据`source_binding`保留workbook_hash、sheet_name、row_number、cell_address、column_key、original_value及字段绑定；`__column_15`、多行表头不重命名。完整单元格引用不是对单元格内每个技术断言的独立认证。声明整理不等于历史网页或实机验证。

旧A1响应仍按其原始协议审查，不能用新Schema覆写旧JSON。历史兼容的七字段逐项审查保持不变：Claim实际状态是STATED/INFERRED/UNKNOWN；SUPPORTED只是兼容审查的verdict。REUSE保留原文及范围，UNKNOWN不升级；需改技术内容则REGENERATE，有未消解矛盾则CONFLICT。

## A2：三级引用及定向重试

保持`construction_check facts ⊆ link facts ⊆ 每个关联scenario facts`，所有正向行事实必须至少有一个link覆盖。PARTIAL行允许不同构造情形用不同事实和情景；APPLICABLE行的每个link仍须包含该行全部必要事实。完整Requires/Skip、原文引用、角色及子问题范围门禁不变。

Prompt正确/错误示例使用当前冻结库的真实构造代码；指导案例ID（如S5-07）不能充当构造代码。拒绝反馈包含row_id、JSON路径形式link_id、construction_id、scenario_id、missing_fact_ids、unexpected_fact_ids和violated_rule，归档到workflow_attempts。

协调器只把同一不可变任务最近的拒绝响应和诊断送入新上下文。`retry_context.json`与完整原请求一起测量，记录`retry_input_budget.json`；超限为INPUT_TOO_LARGE，不丢弃旧响应或原始段落。不复用Agent会话，不从诊断推导新事实，不无限重试。OpenCode和适配器stdout/stderr按attempt保留，包括超时已捕获的内容；再次执行使用新attempt目录。

## A3：未知是合法结果

沿用稀疏格式，不增加42行UNKNOWN矩阵：

| 情况 | 表达 |
| --- | --- |
| 全部前提有正向依据 | APPLICABLE；原MATCH门禁不变 |
| 有线索但前提未全明 | PARTIAL，具体未知保持可见 |
| 特定类别有失败Requires或命中Skip的正向事实 | 该行NOT_APPLICABLE |
| 无法决定类别 | INSUFFICIENT_INFORMATION及具体unknowns；未选规则为NOT_ASSESSED |
| 整个API轴确实依赖非API执行情境 | summary NOT_APPLICABLE，提供grounded exclusion_fact_ids |

没有Wiki、shape或dtype不构成排除依据。definition_init可以按原始定义分类；没有对齐正文时source_relation仍UNKNOWN。PARTIAL需要对应部分支持，MATCH仍走原直接正文门禁。

## 升级、历史与现场隔离复测

1. 停止现场driver/worker，备份整个state和任务目录及Agent命令文件。有WAL用SQLite一致备份，不能只复制主DB。备份及原始证据不上传公开仓库。
2. 使用独立检出目录核对Git HEAD和`python run_faultaudit.py --version`为0.1.20；记录解释器及Pydantic/openpyxl。同步项目内`fault-audit-worker.md`到本版模板，核对不再有“select source_refs={source_id, quote}”旧A1指令，保留其他个人配置；更新Agent命令文件到本版`run_opencode_agent.py`。沿用原state、工作目录、run_id及源文件，禁止重新Init。
3. 在原run执行下列检查。`pin-budget`对相同160000幂等；不允许更换已固定预算、改历史request_hash或Policy。

```powershell
python run_faultaudit.py --state STATE xlsx-workflow pin-budget --run INIT_RUN_ID --chars 160000
python run_faultaudit.py --state STATE trigger-workflow recovery-plan --run INIT_RUN_ID
```

4. 先在隔离备份副本进行真实任务验证。A1选M025/M008/M017，A2选M012/M019/M022，A3选M004/M026/M005，并核查一条历史UNKNOWN。旧完整request/响应保留为对照，新执行必须用程序生成的新request及新hash，不能把旧hash改成新hash。真实OpenCode、完整输入、真实producer，不用合成响应替代。
5. A1须显式语义兼容审查，预检PASS不代表已通过。A2/A3/A4已完成结果在输入技术依赖未变时可**只读重校验**：历史请求/预算/响应Hash正确、来源及当前A1技术定义一致，并通过当前原Validator且与已存规范化结果完全相同。保留原ID/Policy，仅投影增加`current_validation=READ_ONLY_REVALIDATED`，不追加接受响应或人工ACCEPT。旧请求仍不能重新提交；失败项才重算。技术、来源或框架变化仍失效。`recovery-plan.read_only_revalidated_stage_ids`列出这类保留项。
6. 验证通过后，现场按现有外部Agent命令文件整批推进原30条，不按10条询问继续。设置有限尝试次数；外层timeout应大于OpenCode内层timeout。遇到冲突、上下文/预算不足或接口故障，留证并报告阻塞。不要通过增加重试次数或改低Validator消除待办。

```powershell
python run_faultaudit.py --state STATE trigger-workflow next --run INIT_RUN_ID
python run_faultaudit.py --state STATE trigger-workflow submit --run INIT_RUN_ID --task-id CURRENT_TASK_ID --response CURRENT_RESPONSE_JSON
# 代表任务验收通过后由现场执行；Codex本轮未执行现场drive：
python run_faultaudit.py --state STATE trigger-workflow drive --run INIT_RUN_ID --agent-command-file AGENT_COMMAND_JSON --workers 2 --max-rounds 32 --max-attempts 2 --timeout 1200
python run_faultaudit.py --state STATE trigger-workflow recovery-plan --run INIT_RUN_ID
python run_faultaudit.py --state STATE trigger-workflow export --run INIT_RUN_ID
```

Policy仍由源码及运行预算决定，所有旧待提交请求都须重新规划，不能仅替换hash后提交。只读结果兼容不更换历史Policy，也不自动转移人工裁决。A5依赖当前阶段集合，需重新审查。阶段B采集快照保持保留，无须因阶段A升级重采已有149个URL；完整度计数不是故障认证数。

本机合成测试不构成真实OpenCode验收。现场请求、拒绝响应和执行环境未取得时，真实任务回放必须标NOT_RUN；先完成上述隔离验收，再恢复正式执行。不要自动ACCEPT、冻结Baseline或正式入库。
