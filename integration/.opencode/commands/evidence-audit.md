---
description: "通过OpenCode采集证据并执行模型任务，回传本地核验核心并生成复核报告"
---

使用 fault-evidence-audit Skill 处理以下任务：$ARGUMENTS

通过 Skill 的 scripts/run_audit.py 调用核心 CLI，使用现有 run ID 继续任务。
核心版本0.1.3只管理导入、快照、文件任务协议和本地门禁；模型provider/model与实际执行由OpenCode环境负责。
采集并提交正文后，model-tasks导出就绪任务，按instructions/payload/expected_contract执行，
以原run/task/request hash及实际producer信息提交submit-model-results，再run --mode opencode继续。
按摘要、逐关联、全库阶段循环，任务为空时核对是否有blocked或缺失项。
先确认输入、采集工具和实际执行模型。指定DeepSeek时不得将其他当前模型的输出标作DeepSeek。
报告实际退出码、run ID、完成与待处理数；不声称本地CLI已经直连OpenCode服务。
不得只生成一段“整理完成”的文字代替程序运行；mock 不代表真实语义核验。
