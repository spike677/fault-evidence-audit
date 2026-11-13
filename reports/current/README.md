# 128条周报可信根因与代码补证

[完整HTML](report.html)是唯一主要阅读入口；[128条JSONL](results.jsonl)保存原输入、根因、来源对照、责任代码及模式建议。

周报描述、原根因、Wiki/DTS摘要按用户指定作为可信交接资料。110条非空原根因逐字采用；空白根因只有在摘要关联明确且一致时才补充。没有公开代码不降低根因状态。来源调查中的“怀疑/待定位”字样同样原样保留，不提升为新的确定性技术结论。

公开代码状态只说明支持、部分支持、不对应、未找到或受阻。未合并PR仍为提案。已抓取不等于全文审读；每个组件给出选段、重复比对或排除依据。历史关系和上轮119条待确认不直接继承为当前结论。

目录分为inputs（可信原件）、current（本目录3份主要文件）、evidence（回执/审读/验证）、archive（旧报告）。历史包整体迁移且字节未改，见evidence/layout_migration.json；本地实验未发布。

完整离线包位于 ../evidence/rc128-trusted-review.zip；解压后打开reports/current/report.html。包包含当前引用的原始公开响应，不含所有历史报告ZIP。

复现：python scripts/rc128_actual_report.py build；verify；package。构建只读可信输入、已采集证据及人工编写的审读数据，不自动上网、调用模型或运行设备。验证日志位于evidence/。

正式入库、自动人工ACCEPT、现场drive及设备执行均为0。原30条、42/V4定义与运行state未修改。
