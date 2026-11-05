## 故障证据核验

相关任务通过 fault-evidence-audit Skill 调用独立 faultaudit 核心，实际状态以 SQLite 和 run ID 为准。
目标网站访问由具备授权与登录态的现场工具执行；模型任务可由OpenCode或Codex会话执行。核心仅导出任务、接收资料与结果并本地校验，不维护网站登录或远程客户端。
0.1.6核心处理导入、原文快照、证据计划、文件任务协议、本地校验、报告和只读统计；默认执行者为OpenCode，Codex使用model-tasks/submit-model-results --executor codex及run --mode codex，分别保留生产者身份。核心不配置模型服务地址、密钥或网络客户端。
先用--state <state> evidence-plan --run <id> --out preview.json只读预览（mode=ro/query_only，不建state）。只处理选定必要资料，优先原链和已确认资料，已有可用内容便提事实并停止补链；未选引用和旧结果留档，不增加必要待办。
register-event-group、confirm-evidence为写入登记，仅将已有明确用户确认落到实际case_id并记录依据，不作为只读调用，不重复索要已有确认。事件组不合并原始case；同技术输入可共享工作，不同根因/场景继续各自判断并保留冲突。
使用model-tasks发布依赖就绪请求，由OpenCode按instructions/payload/expected_contract执行，再用submit-model-results提交保留原run/task/request hash的结果及实际producer元数据。run --mode opencode推进摘要、逐关联和全库阶段，任务空时仍检查受阻状态。
指定DeepSeek时确认实际provider/model；当前聊天或委派模型不同，不得声称已使用DeepSeek。当前桥接使用文件任务往返，不将其描述为已经直连OpenCode服务。
原始周报、旧汇总表、资料原文与模型建议分别保留。必要资料独立总结，按计划比较；同链接或同算子不能证明同事件。数字、术语、场景及技术结论逐项对比原字段/单元格/引文、证据片段和含义，指定多问题资料的applicable_issue并执行一次self_check；数字相同不等于含义一致。共享结果的原单元格始终属于代表source_case_id。
来源未知、部分读取、冲突和失败均可交付为明确待办，不补写不存在的证据。最终报告列输入、引用、采集、比较及待处理对账。
升级前暂停写入、备份现场state与请求/结果，优先以同state、明确的原run ID续跑；旧结果保留历史，过期结果不作当前支持。输入超限或无法完整处理时报告BLOCKED，不裁剪任务后提交；PARTIAL只描述真实采集缺口，仍保留已抓取全部正文。AUTO_PROCESSED/review_required=false/NOT_REQUIRED为普通自动处理，不伪造ACCEPT；PENDING/PENDING_AGENT由Agent完善，EXCEPTION/NEEDS_REVIEW交人工。真实现场与Python 3.14.3尚未验证。
仅做对账时只读既有SQLite/报告/基线/本轮清单，不触发导入、提交、复核或模型续跑。judgment_id、case_id、snapshot_id分别去重，current只计必要且非过期结果、REJECT口径显式；active摄取与selected快照另计，未选引用与自动/Agent待补/人工异常分别展示。一个共享judgment计一次，case数含member_case_ids；类别可交叉，缺基线的轮次变化为UNKNOWN。没有现场SQLite不猜真实总量，只有报告时限定其文件范围；现场数据保护沿用原流程。
纯JSON入口reconcile-report不初始化Store或打开SQLite；常规export可附统计但不是绝对只读。基线须同run完整report，manifest按完整差集核对；新历史项与current_new分开，new_case_count只指新增判断涉及case，pending_reason_entries只是待办理由条目。
current仅按输入报告导出时的is_stale和task状态，不重查今天数据库或新版策略；真实当前数需现场OpenCode先只读核对SQLite元数据，不把老报告当live DB验证。新导出由report_data按现policy标过期。
