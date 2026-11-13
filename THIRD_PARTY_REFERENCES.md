# 依赖与来源

## 当前程序依赖

| 依赖 | 来源与许可 | 用途 |
| --- | --- | --- |
| Pydantic 2 | [上游](https://github.com/pydantic/pydantic)，MIT | 数据合同校验；类型通过不等于语义成立 |
| openpyxl | [上游](https://openpyxl.readthedocs.io/)，MIT/Expat | 可选Excel导入 |
| PyYAML | [上游](https://github.com/yaml/pyyaml)，MIT | 可选PrecisionTesting配置读取 |
| setuptools | [上游](https://github.com/pypa/setuptools)，MIT | Python构建 |

可选XLSX作者使用接手环境提供的Node与`@oai/artifact-tool`，该运行时未复制或捆绑。基础JSON、HTML、TSV导出不需要Node。

## 输入和研究链接

原V4、原42、原30及128是用户提供的原始材料，来源与哈希见knowledge和inputs清单。555来源内容保留原作者、URL、提交和表示方式；本项目不将第三方原文重授权为自有源码。API结果的重序列化不冒充原HTTP字节。

研究目录只提供上游项目链接，不vendoring其源码、Skill或运行时。外部执行器由接手环境配置；核心不捆绑模型、网站登录客户端或DemonCATPFI工具。

本文件不为本项目或第三方原件新增许可证授权；使用时按各来源许可及适用权限处理。
