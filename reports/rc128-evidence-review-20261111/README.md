# 128条证据核验与失效关系审读

[下载完整离线HTML](report.html)是主要阅读入口，也可[下载完整资料包ZIP](../rc128-evidence-review-20261111.zip)。GitHub文件页显示源码，请下载后用浏览器打开；无需服务器或网络。全部128条原文、逐资料判断、四维关系、分类理由和最强选段都在HTML中，完整来源另行归档。

## 实际完成与边界

- 128/128条完成真实定向检索，141轮检索原始返回已保存；原始组为16公开线索、12 Wiki摘要、23 DTS摘要、77描述记录。
- 原21个唯一GitCode PR均实际尝试打开，网页工具不可访问，API预检418。没有将其写为“PR不存在”或“无修复”。历史选段与本轮GitHub原文分开。
- 原记录按子问题形成141个失效关系评估；每条都有对象、计量/表示域、生命周期、消费者及缺口。不是这些关系都已证实。
- 原记录草案：补充案例3、扩展详情21、新增候选6、待确认98；候选中框架/模型侧项目独立标范围。
- 原记录及独立TC共有8条新增建议，归7组待审方向。RC029和公开V-scale案例保留各自身份，不当作两个独立新模式，也未确认同一具体事件/根因。
- 独立技术案例22条：保留原19条，新增3条公开来源审读。技术建议：{"PENDING": 3, "NEW_CANDIDATE": 2, "ADD_CASE": 1, "EXTEND": 16}。不计为128条之外新增的客户事件。
- 原42采用`D:\project\typora\trigger_library.md`的原字节版本，SHA见清单。仓库同名文件保留作未选用参考；不使用V5修订版替换。
- V4保持6主题、31条件类、55种构造情形、195参考案例及E1–E5。原42和V4独立，未做自动标签转换。
- 0条新确认WB事件、0条正式入库、0次设备执行、0条人工ACCEPT；没有修改现场state、历史或原知识库，没有冻结Baseline。

## 重要纠偏

- RC002：原周报中间FP16溢出与beta=0精度标志PR不直接等同；保留beat/batch/beta冲突。
- RC023：负索引/未激活专家被消费，不是反向grad_probs.dtype修复；后者独立技术价值保留。
- RC030：dequant与MegaMoE槽复用分开。新取#12123含3个变更文件，x=[2,192]本身对齐64，半宽96和内部UbFactorDimy分开；归约步长与scale临时区共同修复，不计为两次独立因果验证。
- RC049/064：kernel二进制缺失或拼写修改不证明当前权重差异/decode读错根因。
- RC065：EMA、repeat反向dtype、rmsnorm三子问题分开；INT32选路案例不能替代这些根因。
- RC069：图像输入丢失与BOOL归约PR无已证对应。
- RC110/128：“未初始化/初始化”转录冲突保留；不静默修正文句。
- RC094：从Wiki摘要中发现a3a3d38，实际取得2025-06-21公开提交/PR1332；两处图模式seq_len补乘scaling_factor，补到RoPE缓存切片范围机理，不冒充原事件确认。
- M006的V4 minus_one暂记、M026对齐单位待查、M004 useBufferType讨论及其与旧偏移归因的边界继续保留。

## 文件

|文件|用途|
|---|---|
|[results.jsonl](results.jsonl)|128条原输入、检索回执、逐资料关系和结论|
|[failure_relations.jsonl](failure_relations.jsonl)|逐子问题的四维关系、应有/实际关系与证据层级|
|[condition_relations.jsonl](condition_relations.jsonl)|API42/V4稀疏关联；Requires/Skip与支持范围|
|[mode_comparison.jsonl](mode_comparison.jsonl)|原30条比较及新增候选，包含独立TC|
|[baseline_30_index.json](baseline_30_index.json)|原30条定义与关系审读索引，不替换原库|
|[technical_cases.json](technical_cases.json)|独立技术案例，全部不冒充周报事件|
|[summary.json](summary.json)|去重统计、条件增量及范围|
|[cross_review.json](cross_review.json)|横向比较与重复文本线索，未合事件|
|[evidence/current_source_index.json](evidence/current_source_index.json)|本轮GitHub完整响应/文件及精确审读选段|
|[evidence/quote_index.json](evidence/quote_index.json)|原文JSON指针、行号与精确引文|
|[search_index.json](search_index.json)|逐条实际检索范围、候选与原始返回|
|[unresolved_gaps.json](unresolved_gaps.json)|缺口和转录问题|
|[input_manifest.json](input_manifest.json)|输入路径、SHA、来源分组|
|[manifest.json](manifest.json)|完整交付字节清单与分析代码指纹|
|[validation.json](validation.json)|数据、原文引文、预算及Git暂存字节校验|
|[ui_validation.json](ui_validation.json)|离线交互检查，不冒充真实浏览器或设备执行|
|[test_results.txt](test_results.txt)|实际解释器、完整命令输出和针对性回归日志|

`sources/original/`保留用户授权提交的原始MD/JSONL、原库基线MD和原42/V4。`sources/`含既有30条及19条技术案例数据。`evidence/github/`为本轮工具响应，`evidence/decoded/`为完整响应中解出的文件/补丁，`evidence/search/`保留全部检索返回，`evidence/fetches/`保存失败及访问范围。

`summary.json`分别对照原30条和之前19条公开技术案例。`1.C.3`代码分支关系和`1.C.1`测试配置在之前19案例中已经存在，不再算作本轮新发现。新增来源上下文、逻辑构造方向和确切代码谓词不混算为覆盖率。

## 复现和验证

```text
python scripts/rc128_review.py build reports/rc128-evidence-review-20261111
python scripts/rc128_review.py verify reports/rc128-evidence-review-20261111
python -m unittest discover -s tests -p test_rc128_review.py -v
node scripts/verify_rc128_ui.cjs reports/rc128-evidence-review-20261111
```

发布包可离线复建，不需要内网原文、模型服务或设备。`init`仅用于开发机第一次从本机原路径冻结输入，不是Baseline初始化。
本工具复现本轮已审读数据及报告，不自动重跑联网检索或生成模型判断。审读决定绑定本批输入SHA；不能更换128条内容后仅按RC编号继承旧判断。

`input_budget_receipts.json`检查可复建的整条分析资料包，含指令和序列化数据，预算160000字符；不证明会话无截断，也不声称提交了128个生产模型请求。下载的大文件只采用注明范围的选段进行本轮判断。

后续优先补真正缺失的原始身份、关键修复函数和故障实参，复用已有资料；不为补齐Wiki/DTS/PR类型重新全库采集。明确新源码/合同和证据变化后再重算受影响项，不继承历史ACCEPT。
