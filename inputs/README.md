# 原始规则与续作输入

本目录只提供任务输入及来源定位，不提供历史分类答案或验证结论。

| 输入 | 身份与用途 | 保存方式 |
| --- | --- | --- |
| [cann30_original.txt](cann30_original.txt) | 最早用户提供的四字段30条原文；用于基础30库扩展 | 原字节复制，SHA256见manifest |
| [rc128_original.jsonl](rc128_original.jsonl) | 用户提供的128条handoff记录，身份字段为`task_id` | 原字节复制；与历史catalog中的`original128tests`不是同一数据集 |
| [cases555/cases.jsonl](cases555/cases.jsonl) | 555条历史案例的中性身份与来源清单 | 明确标记的输入投影，不是未经加工的原始555文档 |
| [cases555/source_receipts.jsonl](cases555/source_receipts.jsonl) | 每条案例的上游URL、固定提交、获取状态和哈希 | 原混合资料中来源元数据的受限投影，不含`finding`或历史判定 |
| [cases555/sources](cases555/sources) | 能从本地历史取证文件核验并提取的部分原始资料 | 内容去重保存；来源回执保留各自身份，不把同内容计作独立证据 |

原V4和原42由项目的`knowledge`目录提供，按其原件校验清单核对。基础30原文不等于后期15列压缩稿、staging JSON或V19整理库。

## 555投影的来源与边界

源文件为历史混合整理文件`V16规范数据.json`，SHA256为
`d8974ced8704b8e834b1f335472ca161984066253a0e90928f91b3068ae3aab0`。
该混合文件含案例身份、历史机理归属、模式、审查和测试描述；完整文件留在本地archive，未作为公开输入整体带入。

公开的555记录只选择`audit_id`、`case_id`、`repo`、`issue_url`和`source_pr_url`，另关联来源回执与当前材料缺口。未纳入历史718机制归类、55模式定义、审查结论、42/V4标签、测试设计及验证结果，也没有把`base_record`或`root_record`整块冒充原始事实。

当前覆盖为：

- 555条身份均保留。
- 397条案例附有至少一份可核验的部分原始资料；这不代表正文、评论、diff和责任源码均已完整。
- 158条案例没有随包的合格原始payload，须按URL重新取得资料后再做语义复核。
- 594个不同内容payload按SHA256保存；每个来源仍有独立回执。
- 这些数量只说明输入可用性，不说明根因已证、分类成立、测试成功或规则覆盖率。

保存方式分开记录：

1. `saved_response_body_utf8`：从既有取证容器的body字段还原UTF-8字节，并核对容器声明的body SHA256。
2. `decoded_upstream_content_field`：解码上游contents接口的base64字段；存在Git blob SHA时一并核对。
3. `parsed_upstream_api_payload_reencoded`：保存既有API解析结果的JSON值投影。它有新的文件SHA256，不能声称与原始HTTP响应字节相同。
4. `original_image_bytes`：保留能核验的原图片字节。

各回执的`captures`是历史获取元数据，不是本次重新联网下载。没有声明历史分页或附件读取完整；HTTP 200和文件存在也不能证明整个事件已完整取证。`FETCH_REQUIRED`不是规则的`NOT_APPLICABLE`或“无故障”。

## 接续顺序

1. 先运行输入校验。
2. 对555逐例补齐缺失的原始资料，区分作者声明、源码事实和审查推断，再用冻结原V4做语义复核。
3. 为具备输入、修复版本和环境的案例建设设备验证队列；其余保留缺口。
4. 用原128输入核对原30条基准，再提出新增或拆并候选；本目录不自动修改正式标准。

这些历史材料不构成新分类规则的独立留出集；参与规则制定后，不得重新标成独立盲测。

```bash
python inputs/verify.py
```

校验不联网、不运行模型、GPU或NPU，也不读取本地archive。
