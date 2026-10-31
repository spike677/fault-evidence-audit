---
description: "通过OpenCode采集证据并执行模型任务，回传本地核验核心并生成复核报告"
---

使用 fault-evidence-audit Skill 处理以下任务：$ARGUMENTS

通过 Skill 的 scripts/run_audit.py 调用核心 CLI，使用现有 run ID 继续任务。
核心版本0.1.5管理导入、快照、文件任务协议、本地门禁及只读统计；本命令的模型provider/model与实际执行由OpenCode环境负责。
采集并提交正文后，model-tasks导出就绪任务，按instructions/payload/expected_contract执行，
以原run/task/request hash及实际producer信息提交submit-model-results，再run --mode opencode继续。
按摘要、逐关联、全库阶段循环，任务为空时核对是否有blocked或缺失项。
先确认输入、采集工具和实际执行模型。指定DeepSeek时不得将其他当前模型的输出标作DeepSeek。
报告实际退出码、run ID、完成与待处理数；不声称本地CLI已经直连OpenCode服务。
不得只生成一段“整理完成”的文字代替程序运行；mock 不代表真实语义核验。
升级前备份现场state及原请求/结果，优先用原state、同run ID续跑，保留历史而不改旧Hash。
输入超限或无法完整执行时报告BLOCKED，不删减任务提交；PARTIAL仍保留已抓取全部正文，只说明真实组件缺口。
所有模型建议继续人工复核；真实现场和Python 3.14.3未验证，不声称已联调通过。
若请求仅为统计对账，只读既有SQLite、报告、基线和本轮清单，另存派生结果，不运行写入或模型续跑步骤。
优先使用现有完整JSON执行reconcile-report --input <报告> --baseline <同run基线> --round-manifest <本轮清单> --out <统计文件>，此入口不打开SQLite；不要把常规export称为绝对只读。
分别按唯一judgment_id/case_id/snapshot_id计数，current排除过期项并说明REJECT口径；分类可交叉，不按案例数修正判断总数。
current仅指输入报告导出时的is_stale/task状态，不重查今天数据库或新版策略。真实当前数需OpenCode先只读核对SQLite元数据，不能把老报告当live DB验证。
缺基线则轮次变化UNKNOWN；没有现场SQLite不猜真实数量，只有报告时只描述该报告范围。沿用既有现场工具与数据保护流程。
新增历史项与current_new分开；new_case_count不是新导入case数，pending_reason_entries不是独立待处理数。清单差集不一致须报告RECONCILIATION_FAILED，不用调整口头数字解决。
