# PrecisionTesting 独立 Bridge 0.1.18

Bridge复用已有Builder、原始42/V4、文件任务和PrecisionTesting原生校验器。新增模块只负责导出、绑定和验收，不实现模型/网站客户端、ATK设备执行器或正式知识库修改。原有分类策略指纹不因本次接入改变；Bridge有独立策略Hash和版本。全程只读打开SQLite，输出存放在state和原PrecisionTesting资产之外，旧文件内容不同时拒绝覆盖。

## 1. 当前有效的Baseline导出

已备份并完成现场A1–A4、横向审查及finalize后，使用实际run_id。只接受当前`READY`的Builder Baseline、原始42及冻结V4；缺失、过期或`READY_WITH_GAPS`不会被本Bridge自动提升。普通模式定义可以没有客户Wiki，导出不会将其升级为来源已核验或实机已验证。

```powershell
python run_faultaudit.py --state STATE precision-bridge export `
  --baseline-run INIT_RUN_ID --repo 'PrecisionTesting本地路径' `
  --task-slug 'ops-math-v910-aclnnExpm1' --out work/precision/context.json
```

默认导出完整冻结模式集合；用重复的`--mode-id`明确选少量代表模式时，记录完整集合、选用和省略范围，不能把选段说成全库完成。每条保留`failure_mechanism`、来源、分类理由、原42、V4类/构造、E方法及验证状态。V4完整31类、55构造、195指导案例及E方法分层保存；独立的condition-link键防止跨模式/子问题串用，不靠映射文件补标签。

本版固定接入审查的`yunqixuan/PrecisionTesting`、提交`72c62d2deab7cac9cce2061034167e22ef45a140`，按本地Git核对身份、原生脚本和任务资产。新commit应先复审，再更新Bridge。两份原42的文件字节Hash分别保存，HTML实体、Markdown转义/表格空白仅用于明确记录的内容比较；目标coverage的规范化文本Hash单列，绝不替换原库或冒充同一文件字节Hash。

## 2. 已知模式与盲测

`export`永远输出`KNOWN_PATTERN_VALIDATION`和`blind_evaluation=false`。另用下列命令创建不含Baseline、真实机理、V4历史案例或模式链接的盲测上下文，不需要打开state：

```powershell
python run_faultaudit.py precision-bridge blind --repo 'PrecisionTesting本地路径' `
  --task-slug 'ops-math-v910-aclnnExpm1' --out work/precision/blind-context.json
```

两条路线使用不同的独立Agent会话；不能把已经看到故障机理的会话重新标为盲测。程序验证文件中的知识隔离和purpose一致性，不能证明执行器实际没有历史上下文，报告明确保留`actual_agent_context_isolation_attested=false`。已知模式任务使用独立协调指令和上下文，不改写原盲测Prompt，不计为盲测成绩。

## 3. 由现有Agent生成溯源草案

先按PrecisionTesting现有`create_workspace.py`在独立workspace复制原task，在其中生成原生`test_suite.json`、完整trigger账本并同步本地Trigger Library。原Prompt、tasks、复制来的接口/源码/template/config/runnable均不改。Bridge本身不会生成测试输入或暗改max_cases。

```powershell
python run_faultaudit.py --state STATE precision-bridge draft --context work/precision/context.json `
  --suite WORKSPACE/01_generate/submission/test_suite.json --out work/precision/binding-task.json
```

任务完整包含上下文、规则、指令、response_schema和逐case输入Hash。复用`FAULTAUDIT_MAX_INPUT_CHARS`检查最终序列化输入，默认48,000不变；超限输出`BLOCKED / INPUT_TOO_LARGE`，不截断、不删库或段落。按实际执行器能力显式设置预算，并在Baseline维护、导出及绑定中保持一致；变更预算可能使旧Baseline/任务失效。导出一个大型数据包并不表示模型能完整处理它。外部源码阅读的实际会话容量仍需现场验收，执行器处理不了时返回BLOCKED。

把这一个request交现有OpenChamber原生`fault-audit-worker`新会话，或现有CLI适配器；主协调器只保留ID/状态/路径，不每10条申请继续。子Agent按`BindingDraft`返回OUTER request_hash及实际producer，用`NEEDS_FACTS/CONFLICT`保留缺口，执行一次自检，不提交SQLite、不造人工ACCEPT。

每条规则必须绑定实际case ID/输入Hash、对应mode_id、限定作用域的evidence_keys与condition_link_keys。引用选中算子原始源码/API的相对路径、行号和精确引文。代码只验证引文/范围与结构一致性，语义检查仍是Agent声明，不是假设存在一个自动判真器。

```powershell
python run_faultaudit.py --state STATE precision-bridge bind --context work/precision/context.json `
  --suite WORKSPACE/01_generate/submission/test_suite.json --assignments work/precision/assignments.json `
  --out work/precision/bindings.json
```

`bind`完整覆盖suite的全部唯一case，拒收缺行、输入变化、错Hash、跨模式依据、无独立分类证明、V4类充当构造或自动转API等情况。保存的binding是不可变溯源，不代表门禁或实机通过。同输入规范/目标资产/seed/执行协议共享稳定work_id；模式标签不进该ID，所有原case及模式归属仍保留。刻意重复或不同seed/协议保留区别，这不是实际随机张量或设备结果的去重证明。

## 4. 原生校验、WARNING和非API路径

Bridge只调用固定的上游`verify_schema.py`、`verify_trigger_coverage.py verify`及`prepare_atk_submission.py prepare`。prepare写入独立临时位置作为JSON物化对照，不启动ATK/Queue/SSH/容器。需要PyYAML的实际Python可用`--python`指定；可在自己的环境安装本项目`[precision]`可选依赖，Bridge不会自动修改全局环境。检查原task与workspace复制资产一致性，防止改任务或执行器迁就测试。

```powershell
python run_faultaudit.py --state STATE precision-bridge check --context work/precision/context.json `
  --bindings work/precision/bindings.json --workspace WORKSPACE `
  --suite WORKSPACE/01_generate/submission/test_suite.json `
  --atk-suite WORKSPACE/02_atk_run/atk_input/test_suite.atk.json --out work/precision/checks
```

每次保留带唯一ID的HTML主报告和完整JSON，保留原stdout/stderr、退出码、WARNING及输入Hash，不覆盖旧报告。

| 场景 | Bridge验收 |
| --- | --- |
| 原生错误、依赖缺失、未知WARNING | BLOCKED；退出0也不能升级 |
| 正式suite不足max_cases | BLOCKED，不改任务配置 |
| 显式`--diagnostic-smoke` | 只解释已识别的数量WARNING，标为DIAGNOSTIC_ONLY，永不冒充正式完成 |
| CODE-only、冻结A3有积极非API依据，或有独立`non_api_basis`及真实源码引用 | 独立非API规则绑定；可完成JSON验收，不强加42标签 |
| CODE-only、只是缺API信息 | 不放行缺主trigger的WARNING，保留缺口 |
| E1–E5完整设计、原模式方法和源码有依据 | 可自动完成协议设计验收；保持PROTOCOL_DESIGN_ONLY、NOT_RUN，`formal_suite_ready=false` |
| 缺E协议、伪造执行成功或目标/串行参考不一致 | 拒收 |
| 缺最终ATK JSON或与上游物化不同 | 不标原生正式suite就绪 |

非API仅解释当前确切的“缺主API trigger预算归属”WARNING，逐case核对；不会清除其他覆盖告警。E1需要重复/复位，E2有P/Q前序及目标对照，E3说明输出预填，E4为目标/干扰者各保留自己的串行参考、实参和输出归属，E5明确参与者配置。所有方法都约束被比较的目标调用；干扰/前序调用允许不同参数。协议是设计结构，当前Bridge没有执行这些方法的能力。

盲测CODE-only不能借用Baseline；可用独立`non_api_basis`记录非API事实角色、原文中实际存在的`positive_fact`、该规则的范围解释和源码精确引用，并由Agent明确核对。程序验证事实原文、范围和声明结构，仍不代替语义判真。仅仅没找到API字段或填入输入形状角色，不会因此放行。盲测不从已有模式继承V4/E方法或历史结论。

单调用CODE路径只接受明确的内部计算依据；输出状态、流、竞态或设备调度仍需要执行协议，不能换成CODE_PATH标签就冒充原生单调用已能表达。盲测原生路线不继承已有E方法知识，缺相应独立能力时保持阻塞。

`formal_suite_ready`仅表示当前原生规则/JSON与绑定验收就绪，不表示模式已复现。分类、生成、JSON物化、路径覆盖、执行、故障复现和根因确认分别记录；`hardware_validated=false`、`path_coverage=NOT_VERIFIED`、`mechanism_confirmation=NOT_ESTABLISHED`始终保持。本版没有结果回写或自动正式知识库修改。

CLI：0表示相应阶段完成（也可能只是明确的诊断/协议设计完成，需看具体状态）；2表示门禁/缺口未满足；1表示输入合同错误或工具异常。正常来源、格式错误与信息不足不生成待人工ACCEPT队列；只有真实语义冲突标记`review_required`。

## 5. 现场边界

本轮只用合成模式/任务/规则验证程序。原30条、实际模型语义能力、现场子agent权限/上下文、真实任务生成与设备路径均不能由合成测试替代。现场仍先备份state，核验当前冻结Baseline及少量代表样本，再接续正式处理。原42/V4定义、旧模型响应和人工历史保持保留。

验证回执见[`examples/precision_bridge_validation.json`](../examples/precision_bridge_validation.json)：30项Bridge合成验收、159项保留定向回归及5项受影响报告复查通过；实际上游三个格式/JSON脚本的1条合成规则smoke通过，正式预算不足仍阻塞。没有做完整回归或设备执行。此前`repository_audit.html/json`是只读审查时的历史快照，其“Adapter尚未实现”不代表本版当前能力。
