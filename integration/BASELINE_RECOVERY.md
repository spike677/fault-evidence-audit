# 0.1.19：原run上的Baseline恢复

本版固定运行预算，提供A1来源清单、显式历史兼容复核和当前下游规划。沿用原run、state和任务目录；不恢复旧Policy、不改写旧响应或人工裁决，不初始化新库，不修改原42/V4或PrecisionTesting，不运行设备测试。

下文`INIT_RUN_ID`须替换为原Init的实际run_id。**源码升级会产生新Policy，旧版本当前有效的结果也不能承诺升级后直接沿用。** 以只读预览及历史请求为准，分开当前有效、历史接受、仅拒绝和未规划阶段，不能用部分恢复队列代替完整范围。

## 1. 升级前

保持现场driver/worker停止，先备份原state、完整任务目录及Agent命令文件。有WAL时使用SQLite一致备份，不能只复制主DB。备份不上传公开GitHub。

从`codex/investigation-plan`取得0.1.19代码。原0.1.18运行副本没有`.git`时，在独立的新检出目录启用新版，不覆盖原副本；保留旧版本、文件SHA和Prompt。旁边另一个仓库的HEAD不能代表旧运行副本版本。

```powershell
python --version
python run_faultaudit.py --version
```

记录实际解释器和Pydantic/openpyxl版本。更新项目内的`fault-audit-worker.md`和`agent-command.json`所用`run_opencode_agent.py`路径；保留用户原有其他Agent配置。新任务`baseline_compatibility`绑定OUTER hash并返回其原始response_schema，不是model envelope。

## 2. 在原run固定历史预算

下面`STATE`必须替换为**原state路径**，不是新空目录。

```powershell
python run_faultaudit.py --state STATE xlsx-workflow pin-budget --run INIT_RUN_ID --chars 160000
python run_faultaudit.py --state STATE trigger-workflow recovery-plan --run INIT_RUN_ID
```

`pin-budget`仅追加不可变运行配置和事件。它检查历史workflow_requests的预算是否一致；不一致或预算缺失时明确拒绝，不猜测或回填。重复固定相同预算幂等，已有固定值不能静默更换。新Init可用`--input-budget 160000`；其他run仍使用自己的预算，默认48000不全局提高。

之后规划、提交、查询、冻结检查都使用run预算。终端环境变量回落到48000不会改变这个run的预算；外部worker收到当前请求中的预算，不改变父进程环境。完整请求超限仍为INPUT_TOO_LARGE；实际执行器读不全仍为EXECUTOR_CONTEXT_LIMIT，不能截断后宣称成功。

`recovery-plan`以SQLite只读模式打开state，不创建任务或修改历史。检查`budget.status=PINNED`、`budget.pinned.budget=160000`、`policy_hash`、每模式路径及`expected_downstream_units=90`。最终新Policy不应回填成旧版本值。

## 3. 先规划，再由现有Agent处理

```powershell
python run_faultaudit.py --state STATE trigger-workflow next --run INIT_RUN_ID
```

这一步生成当前请求文件，**不会调用模型或启动drive**。有可验证历史接受响应且源输入未变的模式走兼容复核；其他模式走定义整理。缺原始请求/响应或源输入变化时，预览给出原因，不预设固定数量。

- `baseline_compatibility`：程序先核验历史请求签名、预算测量、接受响应Hash、模式身份、原始cell/quote和Claim引用。预检PASS仍不是语义通过。Agent阅读当前冻结原文及全部历史版本，对七个字段和每版逐项给出依据。`REUSE`才追加一份带旧定义ID、旧Policy和新审查凭据的当前定义；`REGENERATE`转为新的A1整理；`CONFLICT`明确阻塞。旧结果不改标为新Policy或人工ACCEPT。
- `baseline_define`：使用程序提供的`source_manifest`。SOURCE_RECORD事实只选择`source_refs=[{source_id, quote}]`，程序绑定真实字段和坐标；无需猜测`__column_15`或多行表头。INFERRED字段需说明推导，缺失写UNKNOWN/evidence_gaps。旧Policy拒绝响应及未提交修复版若还在原任务目录，会作为有角色标记的历史输入提供；不得直接当作已接受事实。当前任务失败不再反过来改变它自己的输入，避免每次重试生成新task_id。

先选一两个代表任务做现场验收：一个历史接受复核、一个曾有表头引用错误的A1。现有OpenChamber/OpenCode用独立上下文执行完整request，按返回的OUTER hash提交：

```powershell
python run_faultaudit.py --state STATE trigger-workflow submit --run INIT_RUN_ID --task-id CURRENT_TASK_ID --response CURRENT_RESPONSE_JSON
python run_faultaudit.py --state STATE trigger-workflow recovery-plan --run INIT_RUN_ID
```

新兼容复核不是伪造一份旧A1响应；使用本次Agent的真实producer和语义核对。程序的workflow attempt `ACCEPTED`表示当前协议校验通过，与人工裁决表的`ACCEPT`不同；本版不创建人工裁决。

## 4. 下游和正式续跑

每个取得当前A1定义的模式即可独立派发A2、A3、A4。旧30条下游请求均未执行，保留历史，但不能跨Policy提交。原10个模式的30个当前请求与其余20个模式的60个阶段任务共同构成全范围90个单元；不是90个故障或90份已完成判断。

分类依赖每模式选定的一份技术定义和对应独立分类框架，不能把同一模式的两条历史记录一起累加为当前定义。A1证据元数据更新不自动重算A2/A3；实际证据清单变化可使A4重算；技术事实、范围或支撑来源变化仍正确失效。原42与V4独立判断，不通过映射转换。

现场代表任务验证通过、操作者决定恢复执行后，可使用原Agent命令文件连续推进；**Codex本轮不执行这条命令**：

```powershell
python run_faultaudit.py --state STATE trigger-workflow drive --run INIT_RUN_ID --agent-command-file AGENT_COMMAND_JSON --workers 2 --max-rounds 32 --max-attempts 2
python run_faultaudit.py --state STATE trigger-workflow status --run INIT_RUN_ID
python run_faultaudit.py --state STATE trigger-workflow export --run INIT_RUN_ID
```

CLI退出码2在BLOCKED/COMPLETE_WITH_PENDING时表示明确阻塞或待办，应读取JSON原因，不是工具失灵。

不再每10条询问继续。真正冲突、预算/上下文限制或缺少有效输入会单独呈现；不能通过提高重试次数、删除gap或改Policy消除待办。最终完成A1–A4及A5横向审查后再决定是否显式finalize；不自动冻结或入库。

## 5. 已完成与现场尚待验证

Codex验证使用合成工作簿和合成历史记录：预算固定、精确来源、历史保留、显式复核、冲突阻塞及30模式→90个当前阶段任务。测试不是30条真实故障的语义分类，也不是OpenChamber或硬件验收。

现场仍需验证旧state/响应是否完整、原任务目录能否读取、Agent是否完成全部七字段语义对照、新worker及真实上下文容量、多版本模式的技术内容差异。实际验收结果以现场原文和报告为准。验证记录见`examples/baseline_recovery_validation.json`。
