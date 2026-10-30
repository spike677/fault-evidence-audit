---
name: fault-evidence-audit
description: "在OpenCode环境采集故障证据并执行faultaudit发布的模型任务，逐份总结和逐关联判断，提交可追溯结果并生成复核报告。适用于周报、Wiki、DTS、代码证据及故障库映射，不用于普通Excel排版。"
---

# 故障证据核验

本 Skill 对应核心版本 0.1.1。通过 `scripts/run_audit.py` 调用本地核验核心，`FAULTAUDIT_HOME` 指向含 `run_faultaudit.py` 的核心目录。核心只导入、保存快照、发布任务及运行本地门禁；所有模型服务配置、实际执行及内网采集均在 OpenCode 环境完成。

DTS、Wiki、GitCode、GitHub、CodeHub 等目标网站访问统一由 OpenChamber 环境负责，使用其连接的 OpenCode 与现场工具执行。网站登录、搜索、正文/分页/附件/评论/Diff 读取及网络重试不进入 Codex 核心。`fetch-tasks` 仅导出清单，不能当作已经读取网页的证明。

当前使用文件任务往返，不假设核心已直连 OpenCode 服务。现场可以接 SDK 或使用已配置的模型委派能力，但需先验证该能力及其实际 provider/model。

## 操作

1. 运行核心 `doctor` 检查本地依赖；另在现场确认实际 OpenCode 服务版本、模型执行能力、采集工具及输入文件。OpenChamber 2.5.2 内置 2.1.4，不能仅凭 PATH 中 2.2.0 推定实际后端。
2. 导入原始周报或旧汇总表，明确 `--source-kind`。旧表根因默认来源未知。保存 run ID，后续会话继续该 run。
3. 导出 `fetch-tasks`。优先使用现场已有工具逐条读取，正文、评论、附件、Diff 的缺失分别登记。证据包字段见 [采集合同](references/collection.md)。
4. 用 `ingest-evidence` 提交实际内容。搜索补链标记来源和搜索词；原链抓取不改成搜索来源。不得用模型摘要冒充网页正文。
5. 用 `model-tasks --run <id> --out requests.json` 导出当前依赖就绪任务。按每项 `instructions`、`payload` 和 `expected_contract`，在 OpenCode 中执行模型任务。要求 DeepSeek 时，先确认实际执行模型；当前聊天或委派模型不是 DeepSeek，不得声称已使用 DeepSeek。
6. 将任务结果与原始 run/task/request hash、执行方元数据保存为 `results.json`，用 `submit-model-results --run <id> --file results.json` 回传，再用 `run --run <id> --mode opencode` 推进。结果协议见 [现场任务合同](references/collection.md)。
7. 重复导出、执行、提交、继续，依次完成摘要、逐关联及全库阶段。没有就绪任务时检查状态：可能完成，也可能等待采集、补充信息或处理失败，不将空清单当作成功证明。
8. 查看 `validate`、冲突、来源未知和失败任务。用 `export` 生成 JSON、HTML、TSV；XLSX 依赖可选 runtime。mock 仅演示流程，不提供真实核验结论。

## 关键约束

- 每份资料独立总结，再与每条引用记录比较。按具体章节和子问题关联，不以同模型、同算子或同链接合并故障。
- 原文根因、资料声明和模型推断分别保留；反证或拒绝关联保留，不删除整份资料。
- 引文必须属于本次保存的快照片段。缺版本、触发或事件身份时保持待判断。
- 全库映射需固定版本；检索未命中不能写未覆盖。同源转载不是多份独立证据。
- 模型结果是待复核建议。需要用户裁决的争议列入报告，不冒充已确认；不自动归并事件。
- 不在核心、任务文件或Skill中配置模型服务地址和密钥。生产者填写实际OpenCode版本、provider、model及会话；无法确认执行来源时列为缺口。
- 完成报告同时给出输入行数、链接数、比较数、失败与待处理数、run ID 和产物路径。所有任务执行成功也可能仍有语义待核验项。

若用户要求真实核验而缺少内网读取权限，应继续完成导入、清单和可执行任务，明确受阻项，不猜测页面内容。核心命令的完整用法在核心目录 README；这里不复制一份实现说明。
