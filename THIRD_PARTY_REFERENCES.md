# 开源复用与参考记录

核对日期为 2026 年 10 月 30 日。下列许可依据各项目或具体 Skill 目录的许可证。依赖版本以本包实际声明和验收记录为准，链接中的 main 不代表已锁定发布版本。

## 本轮直接使用与设计参考

| 项目 | 许可证与主源 | 本轮用途 | 边界 |
| --- | --- | --- | --- |
| Pydantic | [MIT](https://github.com/pydantic/pydantic/blob/main/LICENSE) | 直接依赖，pyproject声明`>=2.8,<3`；合同与模型输出已使用其校验 | 类型正确不能证明语义正确，引用归属与事件门禁由本项目实现 |
| python-jsonschema | [MIT](https://github.com/python-jsonschema/jsonschema/blob/main/COPYING) | 仅比较参考，没有加入当前依赖 | 首版使用Pydantic，不同时引入两套schema实现 |
| openpyxl | [官方文档及 MIT/Expat 许可](https://openpyxl.readthedocs.io/en/stable/) | XLSX导入的可选依赖，pyproject声明`>=3.1,<4` | 本轮XLSX作者不使用openpyxl |
| Google LangExtract | [项目](https://github.com/google/langextract)、[Apache-2.0](https://github.com/google/langextract/blob/main/LICENSE) | 参考原文grounding、分块及字符区间设计，未复制SDK源码 | 当前未作为强制依赖；不代替跨资料事件核验 |
| LangExtract Usage Skill | [原始Skill](https://github.com/google/langextract/blob/main/skills/langextract-usage/SKILL.md)，适用仓库Apache-2.0许可 | 参考精确提取值、char_interval和显式模型配置；未复制Skill正文 | 未对齐输出不可进入肯定证据；默认对齐警告不能代替硬门禁 |
| Instructor | [官方项目](https://github.com/567-labs/instructor)、[MIT](https://github.com/567-labs/instructor/blob/main/LICENSE)、[DeepSeek指南](https://python.useinstructor.com/integrations/deepseek/) | 仅参考结构化响应及执行方适配思路，未复制源码 | 0.1.1核心不引入其网络客户端；所有模型服务配置与执行由OpenCode现场负责 |
| Agent Skills | [规范](https://agentskills.io/specification)、[Apache-2.0](https://github.com/agentskills/agentskills/blob/main/LICENSE) | 项目Skill的目录与frontmatter格式参考 | 工作流说明与程序约束分别维护 |
| Anthropic mcp-builder及skill-creator | [mcp-builder](https://github.com/anthropics/skills/tree/main/skills/mcp-builder)、[该目录Apache-2.0许可](https://github.com/anthropics/skills/blob/main/skills/mcp-builder/LICENSE.txt)、[skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator)、[该目录Apache-2.0许可](https://github.com/anthropics/skills/blob/main/skills/skill-creator/LICENSE.txt) | 参考薄工具、分页、明确错误和可观测评测组织，未复制Skill源码 | 目录级许可须分别核对，不能推广到仓库内所有Skill |

本项目新增的导出器、证据业务规则和Skill指令为本轮原创实现；上表未列出任何已vendoring的第三方代码。依赖库本身的许可仍随其发行包保留。

## 0.1.1 模型执行边界

Codex侧交付本地任务协议、结构及原文校验，不接收模型服务地址或密钥，不运行模型网络客户端。OpenCode侧配置provider/model并执行模型任务，将带生产者元数据的结果文件交回核心。LangExtract、Instructor及相关指南是设计参考，没有引入直接调用模型服务的依赖链。

当前桥接为文件任务往返：生成依赖就绪请求、现场执行、提交结果、推进下一阶段。实际接入OpenCode服务SDK或模型委派工具由现场实现和验收；不能将本地CLI描述成已经与OpenCode服务建立连接。

## 未采用的受限内容

Anthropic的[xlsx Skill具体许可证](https://github.com/anthropics/skills/blob/main/skills/xlsx/LICENSE.txt)为保留权利并带复制、派生和分发限制的条款，不能按Apache或MIT Skill处理。本包没有复制、安装或分发其代码、提示词和资产。

## XLSX作者与可移植性

`scripts/export_xlsx.mjs`使用当前Codex环境提供的`@oai/artifact-tool`公开API，这不是本包所声称的开源依赖，也未复制或捆绑其运行时。基础JSON、HTML、TSV导出只依赖Python标准库，完全不需要Node或此运行时。

可选XLSX步骤需要目标环境提供可用的Node与`@oai/artifact-tool`，路径可由调用方配置；没有时明确报告不可用，基础报告仍正常生成。今后替换该可选作者时维持`workbook_data.json`协议即可。

## 版本相关官方参考

- [OpenChamber 2.5.2](https://github.com/openchamber/openchamber/releases/tag/v2.5.2)的发布记录写明内置OpenCode 2.1.4。PATH中的其他版本不代表应用实际连接版本。
- [OpenCode V2 Skills](https://opencode.ai/v2/docs/skills/)、[Commands](https://opencode.ai/v2/docs/commands/)、[MCP](https://opencode.ai/v2/docs/mcp-servers/)为接口参考；2.1.4、2.2.0分别需要现场能力验收。
- [V2 Policies](https://opencode.ai/v2/docs/policies/)包含2.3.0之后的动作，不能整份照搬到旧目标版本。
- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)是模型调用参考，格式保证不等同于业务或语义保证。
