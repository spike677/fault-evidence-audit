---
description: "通过OpenCode采集证据并执行模型任务，回传本地核验核心并生成复核报告"
---

使用 fault-evidence-audit Skill 处理以下任务：$ARGUMENTS

通过 Skill 的 scripts/run_audit.py 调用核心 CLI，使用现有 run ID 继续任务。
本轮仅支持结构化XLSX完整流程。用xlsx-workflow start导入明确的故障表和原始库，next取得带准确request/response路径的任务。按kind调用现场工具或模型，写响应后submit，再next推进到READY_TO_EXPORT；export默认只交付一个带来源编号的故障排名XLSX。已有外部Agent命令适配器可用drive自动循环。Word/PPT、任意布局XLSX、时间范围收集只列TODO，不生成额外说明文档。下面底层命令保留为兼容调试入口。
核心版本0.1.10管理导入、快照、证据计划、文件任务协议、本地门禁及只读统计；本命令的模型provider/model与实际执行由OpenCode环境负责。
从文档整理故障时Wiki为第一优先级：已有Wiki先读并核对，默认不另搜Wiki；没有Wiki时，即使已有其他站点证据，也必须先做有范围的Wiki补证检查。查无匹配记录查询范围与NO_MATCH；登录失败记录BLOCKED，不能算检查完成，其他资料继续整理。已有原链保留，最终核对发现错挂/冲突才定向补证。不把required_sources=WIKI当成“检查过Wiki”的替代，也不无限寻找。0.1.10 的 xlsx-workflow 已实现该前置检查，不能跳过 NO_MATCH/BLOCKED 记录。
新流水线文件命名与位置以docs/catalog-engineering-plan.md“固定存放位置与最少文件”为准：复用原state；任务只保留必要request.json及按尝试保存的response.json，最终交付一个故障整理及模式库建议.xlsx。不要额外撰写逐条Markdown/HTML总结或多版交付物；xlsx-workflow 默认只交付一份工作簿；旧通用export仅保留调试兼容，不作为本轮默认入口。
模式库草案使用 catalog-draft prepare --run <id> --case-id <内部caseID> [--expected-additions <可选数量>] --out <新目录>。完整读取request.json，按schema填写新response.json并如实声明producer；草案走catalog-draft validate/export，不能交给submit-model-results。只读状态、保留完整冻结库，旧表陈述不升级为已验证根因，不修改正式库或生成ACCEPT；操作说明见docs/catalog-draft.md。超限或读不全即阻塞，不删减任务。
先以--state <state> evidence-plan --run <id> --out preview.json只读预览。整理全部已有原表/旧汇总引用及显式确认资料，不只选一份；已有可用内容就提事实并停止新增补链，不取消其他已有引用。未选搜索候选留档。
逐条核验仓库Issue/PR和真实根因时，再以--state <state> investigation-plan --run <id> --out investigation.json导出只读调查计划。保留每条source_case及出处，按resources去重读取作者正文、相关讨论、适用关联Issue和必要修复Diff；按work_items的work_id和子问题处理。链接仅导航候选，不等于关联成立。independent_technical_facts是资料自身事实，root_cause_candidates只供当前工作候选；ROOT_CAUSE_UNCONFIRMED不可改成完成根因。仍由本环境执行采集和模型，使用原EvidencePackage和model-tasks/submit-model-results回传，不新增网站/模型客户端或人工ACCEPT。
来源分级SOURCE_CELL_LINKED/LEGACY_TABLE_LINKED/SEARCH_DISCOVERED/PROVENANCE_PENDING与user_confirmed独立，旧表引用不升级为周报原链；来源待恢复由Agent先处理。同case/snapshot多issue按work_id分开，逐引用和逐子问题完整展示，不改任务work标识或跨issue复用结果。
默认min_usable_evidence=1，无强制来源；无适用证据时按SEARCH执行，已有Wiki/GitCode/GitHub/CodeHub或DTS任一可用资料停止新增搜索，无DTS自动补证。未读/失败先处理。已有资料后，仅额外显式required_sources(AND)/required_any_sources(OR)/数量条件未满足且search_control允许时定向补搜，一满足就停，不凑类型。每次搜索前重读计划，取得候选后先摘要核验再决定下一次；可读URL或泛关键词相同不算满足。search_control.satisfied不代表根因确认或库覆盖，不伪造user_confirmed。
OpenChamber实际连接的OpenCode可执行全部文件任务替代Codex；本包不启动Chamber或直连服务。doctor只检查本地依赖，不证明网站登录/DeepSeek联调；接入与合成验收命令见核心integration/OPENCODE_HANDOFF.md。
register-event-group和confirm-evidence是写入登记命令，只登记已有用户确认并保留依据，不作为只读预览调用，也不要求用户重复确认已有关系。
采集并提交必要正文后，model-tasks导出就绪任务，按instructions/payload/expected_contract执行，
以原run/task/request hash及实际producer信息提交submit-model-results，再run --mode opencode继续。
按摘要、逐关联、全库阶段循环，任务为空时核对是否有blocked或缺失项。
先确认输入、采集工具和实际执行模型。指定DeepSeek时不得将其他当前模型的输出标作DeepSeek。
报告实际退出码、run ID、完成与待处理数；不声称本地CLI已经直连OpenCode服务。
不得只生成一段“整理完成”的文字代替程序运行；mock 不代表真实语义核验。
升级前备份现场state及原请求/结果，优先用原state、同run ID续跑，保留历史而不改旧Hash。
输入超限或无法完整执行时报告BLOCKED，不删减任务提交；PARTIAL仍保留已抓取全部正文，只说明真实组件缺口。
数字、术语、场景、技术结论逐项填原字段/单元格/引文与证据片段及含义，多问题资料选适用issue并做一次self_check。
正常AUTO_PROCESSED不要求例行人工ACCEPT，PENDING由Agent补充，EXCEPTION才交人工；不自动写ACCEPT。真实现场和Python 3.14.3未验证，不声称已联调通过。
事件组保留成员和不同根因；技术输入相同才共享工作。代表行的引文与单元格不能冒充其他行原文。
若请求仅为统计对账，只读既有SQLite、报告、基线和本轮清单，另存派生结果，不运行写入或模型续跑步骤。
优先使用现有完整JSON执行reconcile-report --input <报告> --baseline <同run基线> --round-manifest <本轮清单> --out <统计文件>，此入口不打开SQLite；不要把常规export称为绝对只读。
分别按唯一judgment_id/case_id/snapshot_id计数，current只计必要且非过期结果并说明REJECT口径；active摄取与selected快照另列，未选引用和自动/Agent待补/人工异常分列。共享判断计一次，case数包含member_case_ids；分类可交叉，不按案例数修正判断总数。
current仅指输入报告导出时的is_stale/task状态，不重查今天数据库或新版策略。真实当前数需OpenCode先只读核对SQLite元数据，不能把老报告当live DB验证。
缺基线则轮次变化UNKNOWN；没有现场SQLite不猜真实数量，只有报告时只描述该报告范围。沿用既有现场工具与数据保护流程。
新增历史项与current_new分开；new_case_count不是新导入case数，pending_reason_entries不是独立待处理数。清单差集不一致须报告RECONCILIATION_FAILED，不用调整口头数字解决。
