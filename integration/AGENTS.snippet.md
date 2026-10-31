## 故障证据核验

相关任务通过 fault-evidence-audit Skill 调用独立 faultaudit 核心，实际状态以 SQLite 和 run ID 为准。
目标网站访问由具备授权与登录态的现场工具执行；模型任务可由OpenCode或Codex会话执行。核心仅导出任务、接收资料与结果并本地校验，不维护网站登录或远程客户端。
0.1.4核心只处理导入、原文快照、文件任务协议、本地校验和报告；默认执行者为OpenCode，Codex使用model-tasks/submit-model-results --executor codex及run --mode codex，分别保留生产者身份。核心不配置模型服务地址、密钥或网络客户端。
使用model-tasks发布依赖就绪请求，由OpenCode按instructions/payload/expected_contract执行，再用submit-model-results提交保留原run/task/request hash的结果及实际producer元数据。run --mode opencode推进摘要、逐关联和全库阶段，任务空时仍检查受阻状态。
指定DeepSeek时确认实际provider/model；当前聊天或委派模型不同，不得声称已使用DeepSeek。当前桥接使用文件任务往返，不将其描述为已经直连OpenCode服务。
原始周报、旧汇总表、资料原文与模型建议分别保留。每份资料独立总结，逐引用判断；同链接或同算子不能证明同事件。
来源未知、部分读取、冲突和失败均可交付为明确待办，不补写不存在的证据。最终报告列输入、引用、采集、比较及待处理对账。
升级前暂停写入、备份现场state与请求/结果，优先以同state、明确的原run ID续跑；旧结果保留历史，过期结果不作当前支持。输入超限或无法完整处理时报告BLOCKED，不裁剪任务后提交；PARTIAL只描述真实采集缺口，仍保留已抓取全部正文。所有模型建议继续人工审核，真实现场与Python 3.14.3尚未验证。
