---
description: "通过OpenCode采集证据并执行模型任务，回传本地核验核心并生成复核报告"
---

使用 fault-evidence-audit Skill 处理以下任务：$ARGUMENTS

通过 Skill 的 scripts/run_audit.py 调用核心 CLI，使用现有 run ID 继续任务。
核心版本0.1.7管理导入、快照、证据计划、文件任务协议、本地门禁及只读统计；本命令的模型provider/model与实际执行由OpenCode环境负责。
先以--state <state> evidence-plan --run <id> --out preview.json只读预览。整理全部已有原表/旧汇总引用及显式确认资料，不只选一份；已有可用内容就提事实并停止新增补链，不取消其他已有引用。未选搜索候选留档。
来源分级SOURCE_CELL_LINKED/LEGACY_TABLE_LINKED/SEARCH_DISCOVERED/PROVENANCE_PENDING与user_confirmed独立，旧表引用不升级为周报原链；来源待恢复由Agent先处理。同case/snapshot多issue按work_id分开，逐引用和逐子问题完整展示，不改任务work标识或跨issue复用结果。
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
