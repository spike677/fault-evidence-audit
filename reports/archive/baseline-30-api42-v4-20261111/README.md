# 原30条CANN模式：API42与V4逐条说明

2026-11-11讨论更新版。按原表顺序保留M编号。分类依据为原模式声明、既有Wiki/DTS摘要及已记录技术推导；历史网页原始快照尚未在本机重新核验。

[完整离线HTML](CANN_30_MODES_API42_V4_REVIEW.html) · [完整结构化数据](review_data.json) · [OpenChamber续接说明](CHAMBER_HANDOFF.md) · [本机Init查找结果](local_init_search.json)

## 状态与口径

- 数据Init：30/30完成；该COMPLETE只表示数据初始化，不是A1–A5工作流完成或Baseline冻结。
- API42：L1技术相关18/42，L2历史摘要代表3/42，L3测试设计3/42，L4设备验证0/42。
- V4：L1技术相关21/55，L2历史摘要代表6/55，L3测试设计4/55，L4设备验证0/55。
- 62条稀疏关系：API42 25条、V4 37条。关系数、模式数和唯一条件数分别统计，各层不相加。
- V4保持6主题、31条件类、55种构造、64挂载、195指导案例及独立E1–E5；真实机理另列，不把55称为失效机理。
- M006的minus_one为本次讨论暂记；M026保留待补证；M004增加参数传播机理说明。三项更新未静默升级历史代表或设备覆盖。

## 原始资料和state

本次按用户明确指示附原始数据Init、现有本机来源转录和历史预检state。ZIP内保留原字节及逐文件SHA；没有伪造或恢复缺失的现场数据库。

- [原始Init及来源资料](original_init_and_sources.zip)：数据Init、原模式字段、证据/来源台账、两份Markdown转录、原API42及V4。
- [原30条历史预检state](legacy_original30_preflight.zip)：0.1.17数据库、两个run的任务目录、原输入JSON。每run 30条记录、30个请求、0个完成结果。
- [逐文件SHA-256](archive_manifest.json) · [可用性及缺失清单](availability.json)。
- 现场run `run-20261109T065009Z-37f05b15`、原始`cann_modes.xlsx`和28份原始网页采集快照未在可读本机范围找到。
- 已找到的旧`init_frozen_baseline.json`对应15类`INF-*`，不作为本轮30条基线。

## 按原表顺序逐条说明

|原序／M编号|原模式名称|API42关联|V4构造关联|最新讨论|
|---|---|---|---|---|
|1／M020|空tensor处理不当|1.1.1|zero_extent, positive_extent|无本次讨论改动|
|2／M006|越界读写：shape错误|暂无已建立关系|暂无已建立关系；讨论暂记：minus_one|按用户指示先记录为V4的-1；原记录描述InferShape输出-1，合法输入标记、传播链及具体修复点仍待确认。|
|3／M026|越界读写：tiling切分策略的逻辑错误|1.2.2|tile_shape, power_shape|原序第3条M026按用户指示先保留，继续收集证据；现有对齐分类保持候选，不升级为根因或越界已证实。|
|4／M004|越界读写：偏移量计算错误|暂无已建立关系|暂无已建立关系|用户补充：MC2未传入useBufferType；AllGatherMatmul调用SetSkipBufferWindowCopy设置该配置，HCCL获取该值并更新。先按通信缓冲区模式参数漏传或状态传播不一致整理，不直接认定为偏移算式错误。|
|5／M007|缺少同步|1.2.7|geometry|无本次讨论改动|
|6／M022|搬运逻辑错误：blocktable有错误|1.6.1|position|无本次讨论改动|
|7／M024|数据排布转换错误|1.4.3, 1.C.6|enum_layout|无本次讨论改动|
|8／M001|算子实现精度不一致：低精度误差累积|1.7.6, 1.C.2|intermediate_overflow, enum_dtype|无本次讨论改动|
|9／M019|数学等价但计算结果不等价|暂无已建立关系|cancellation|无本次讨论改动|
|10／M005|浮点数累加序不当|1.C.7|enum_dtype, long_reduce|无本次讨论改动|
|11／M023|tiling切分策略的逻辑异常|暂无已建立关系|暂无已建立关系|无本次讨论改动|
|12／M011|tiling切分策略分支错误|1.2.6|tile_shape|无本次讨论改动|
|13／M012|确定性计算未实现|暂无已建立关系|暂无已建立关系|无本次讨论改动|
|14／M008|浮点数累加序不当|1.2.6|tile_shape, long_reduce, cancellation|无本次讨论改动|
|15／M029|硬件导致算子不支持未拦截|1.7.2|special_values, enum_dtype|无本次讨论改动|
|16／M013|NPU适配引入额外参数|暂无已建立关系|暂无已建立关系|无本次讨论改动|
|17／M014|tensor下标超出数值范围|1.2.4|huge_shape, index_overflow|无本次讨论改动|
|18／M009|精度溢出：数值格式精度不够导致精度溢出|1.7.6|intermediate_overflow, enum_dtype|无本次讨论改动|
|19／M025|算子实现精度不一致：指数函数精度实现错误|暂无已建立关系|暂无已建立关系|无本次讨论改动|
|20／M028|确定性计算未实现|暂无已建立关系|暂无已建立关系|无本次讨论改动|
|21／M015|越界读写：内存踩踏覆盖|暂无已建立关系|buffer_fit|无本次讨论改动|
|22／M027|竞品实现不一致：特定私有数据排列格式|1.4.1, 1.4.3, 1.C.6|view_stride, enum_layout|无本次讨论改动|
|23／M003|tiling切分策略的逻辑异常|1.6.1, 1.8.2|enum_mask, tile_shape|无本次讨论改动|
|24／M016|精度溢出：特定硬件数值格式导致精度溢出|1.7.4|near_singular, enum_dtype|无本次讨论改动|
|25／M002|边界值异常|1.1.3|zeros, near_singular|无本次讨论改动|
|26／M010|融合算子反量化位置不当|暂无已建立关系|enum_quant|无本次讨论改动|
|27／M030|输入数据类型强转低精丢失|暂无已建立关系|enum_dtype, rounding|无本次讨论改动|
|28／M017|tiling切分策略不同分支处理精度不一致|1.6.1, 1.2.6|tile_shape|无本次讨论改动|
|29／M021|矩阵乘加融合后数据格式转换精度丢失|暂无已建立关系|enum_dtype, rounding|无本次讨论改动|
|30／M018|浮点数累加序不当|1.5.1, 1.5.2|暂无已建立关系|无本次讨论改动|

### 原第1条／M020：空tensor处理不当

**原始定义：** embedding前向输入为空导致反向NaN

**机理整理：** 空输入的边界处理未满足后续梯度计算要求，导致NaN。

**输入／实现情境：** 空 tensor 输入；训练反向

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.1.1`** · L1 / L3 · MODEL_INFERRED
  - 理由：原模式是空Tensor处理，可独立构造合法零长度索引。
  - 限制：摘要“空值”未明确shape=[0]；Embedding也仅为推断。
  - 证据：A-W12
- **V4 `zero_extent`** · L1 / L3 · MODEL_INFERRED
  - 理由：原空输入定义与零元素路径技术相关。
  - 限制：历史shape和空值语义未知；设计不反填为历史。
  - 证据：A-W12
- **V4 `positive_extent`** · L1 / L3 · MODEL_INFERRED
  - 理由：空/非空成对对照能检验该类边界处理。
  - 限制：这是新设计，而非文档保存的历史对照。
  - 证据：A-W12

**待确认项：** W12只有输入空值、总梯度NaN，未给embedding具体写回机制；输出未初始化是待扩展详情。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：PARTIALLY_SUPPORTED；原文独立核验=False；设备验证=False。

### 原第2条／M006：越界读写：shape错误

**原始定义：** SetSize算子的infershape接口存在问题，output shape是-1，导致其后面的算子ReduceSum推导出的shape是个标量，进而导致分配内存异常；

**机理整理：** 原表声明infer-shape返回-1，后续算子推导为标量，导致内存分配异常。

**输入／实现情境：** infershape 返回 -1 的算子链；虚机+容器精度测试

**分类说明：** -1由infer-shape返回，标量是下游推断结果；输入构造与内部结果分开。

**2026-11-11讨论更新：** 按用户指示先记录为V4的-1；原记录描述InferShape输出-1，合法输入标记、传播链及具体修复点仍待确认。

```json
{
  "recorded_on": "2026-11-11",
  "origin": "USER_DISCUSSION",
  "v4_scenario_ids": [
    "minus_one"
  ],
  "v4_scenario_name": "-1：推断维度 / 动态标记 / 哨兵",
  "classification_scope": "PROVISIONAL_FROM_DESCRIPTION",
  "note": "按用户指示先记录为V4的-1；原记录描述InferShape输出-1，合法输入标记、传播链及具体修复点仍待确认。",
  "evidence_confirmed": false,
  "hardware_validated": false,
  "counts_toward_historical_coverage": false,
  "fix_version": {
    "value": "CANN 6.3 RC1 B060",
    "origin": "USER_PROVIDED",
    "verified": false
  }
}
```

当前没有已建立的API42/V4稀疏关系；这不表示全局不适用。


**待确认项：** D02仅称目录问题、待确认，未证明SetSize/ReduceSum链。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：UNCONFIRMED；原文独立核验=False；设备验证=False。

### 原第3条／M026：越界读写：tiling切分策略的逻辑错误

**原始定义：** 测试脚本中输入的indices的tensor大小未对齐32b

**机理整理：** 原表声明测试脚本提供的indices大小未按32B对齐。

**输入／实现情境：** indices 未 32B 对齐；ATB KVSelect BlockHashTopk

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

**2026-11-11讨论更新：** 原序第3条M026按用户指示先保留，继续收集证据；现有对齐分类保持候选，不升级为根因或越界已证实。

```json
{
  "recorded_on": "2026-11-11",
  "origin": "USER_DISCUSSION",
  "status": "RETAIN_PENDING_EVIDENCE",
  "note": "原序第3条M026按用户指示先保留，继续收集证据；现有对齐分类保持候选，不升级为根因或越界已证实。",
  "evidence_confirmed": false,
  "hardware_validated": false
}
```

- **API42 `1.2.2`** · L1 · MODEL_INFERRED
  - 理由：原声明indices未按32B对齐，可指导尾块分析。
  - 限制：缺indices dtype/元素数及字节换算；D03未证。
  - 证据：DECL:M026
- **V4 `tile_shape`** · L1 · MODEL_INFERRED
  - 理由：32B对齐声明可能关联完整块/尾块处理。
  - 限制：尚无真实tile与边界谓词。
  - 证据：DECL:M026
- **V4 `power_shape`** · L1 · MODEL_INFERRED
  - 理由：32B粒度为二次幂边界分析提供特定线索。
  - 限制：需证明其对应哪条合法轴及真实路径；不是见32就算覆盖。
  - 证据：DECL:M026

**待确认项：** D03没有32B细节，且未证明Kernel越界；可能是测试输入契约问题，不能把触发条件当成失效机理闭环。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：UNCONFIRMED；原文独立核验=False；设备验证=False。

### 原第4条／M004：越界读写：偏移量计算错误

**原始定义：** window区偏移计算存在问题,导致地址有踩踏，从而导致精度问题

**机理整理：** 原表声明window区偏移计算错误，写入覆盖其他地址，导致MC2反向NaN。

**输入／实现情境：** 使能 MC2 + 8 机训练；现网 CANN 8.0.0 + MC2

**分类说明：** 原声明是通信window偏移，摘要内部冲突；没有已知API输入触发，不强配窗口几何。

**2026-11-11讨论更新：** 用户补充：MC2未传入useBufferType；AllGatherMatmul调用SetSkipBufferWindowCopy设置该配置，HCCL获取该值并更新。先按通信缓冲区模式参数漏传或状态传播不一致整理，不直接认定为偏移算式错误。

```json
{
  "recorded_on": "2026-11-11",
  "origin": "USER_DISCUSSION",
  "classification_scope": "MECHANISM_REFINEMENT_FROM_USER_REPAIR_ACCOUNT",
  "mechanism_refinement": "用户补充：MC2未传入useBufferType；AllGatherMatmul调用SetSkipBufferWindowCopy设置该配置，HCCL获取该值并更新。先按通信缓冲区模式参数漏传或状态传播不一致整理，不直接认定为偏移算式错误。",
  "input_dependency": "CONTROL_CONFIGURATION_AND_IMPLEMENTATION_PATH; TENSOR_SHAPE_OR_VALUE_TRIGGER_UNKNOWN",
  "reproduction_status": "CONDITIONS_REQUIRED_RATE_UNKNOWN",
  "v4_class_candidates": [
    "C4"
  ],
  "v4_scenario_ids": [],
  "api42_ids": [],
  "classification_note": "C4显式模式分派作为待核对方向；不把内部必需字段漏传直接当成合法可选参数省略，也不直接增加API42或55构造覆盖。",
  "public_api_reference": {
    "url": "https://www.hiascend.com/doc_center/source/zh/canncommercial/800/apiref/ascendcopapi/atlasascendc_api_07_10044.html",
    "supports": "SetSkipBufferWindowCopy设置通信算法获取输入数据的位置；只支持接口语义，不是本故障的修复提交。"
  },
  "evidence_confirmed": false,
  "hardware_validated": false,
  "counts_toward_historical_coverage": false
}
```

当前没有已建立的API42/V4稀疏关系；这不表示全局不适用。


**待确认项：** Part4 D07根因括号引用原表窗口偏移，Part5/6却明确DTS未提该细节；不将回填原表的文字作为独立DTS证明。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：UNCONFIRMED；原文独立核验=False；设备验证=False。

### 原第5条／M007：缺少同步

**原始定义：** 多核同时搬运可能会导致偶现精度问题

**机理整理：** 原表推定多核同时搬运缺少必要同步，使相同调用偶现错误。

**输入／实现情境：** 多核并发搬运（indices 与 grad_out 特定 shape）；AICORE 池化反向，tilingKey=2

**分类说明：** 同输入偶现优先用执行规程分析；池化几何仅有候选关系。

- **API42 `1.2.7`** · L1 · MODEL_INFERRED
  - 理由：MaxPool反向的输入/indices/grad_out形状可作为几何对照起点。
  - 限制：kernel/stride/pad/dilation未知，未满足完整几何谓词。
  - 证据：A-D05
- **V4 `geometry`** · L1 · MODEL_INFERRED
  - 理由：池化反向的空间映射可指导边缘几何补证。
  - 限制：未保存有效窗口和padding关系。
  - 证据：A-D05

**待确认项：** D05复现同输入第一次对第二次错，但未给同步根因。算子名不同不能单独证明DIFFERENT_EVENT。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：PARTIALLY_SUPPORTED；原文独立核验=False；设备验证=False。

### 原第6条／M022：搬运逻辑错误：blocktable有错误

**原始定义：** Block Table 目前的索引和但kvCacheOut 的batch 偏移不一致

**机理整理：** BlockTable索引与KV输出batch偏移不一致，发生错误搬运。

**输入／实现情境：** batch=143 / [2896,128,59,128]；ATB KVSelect

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.6.1`** · L1 · MODEL_INFERRED
  - 理由：原模式有batch=143及batch偏移声明。
  - 限制：D04根因空白，不能确认多batch造成此机制。
  - 证据：A-D04
- **V4 `position`** · L1 · MODEL_INFERRED
  - 理由：不同batch填入可区分内容可揭示BlockTable偏移串用。
  - 限制：原历史数据分布未知，属于技术推导。
  - 证据：DECL:M022

**待确认项：** D04原因分析空白，只证明特定shape精度问题，不能核实偏移根因。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：UNCONFIRMED；原文独立核验=False；设备验证=False。

### 原第7条／M024：数据排布转换错误

**原始定义：** 数据在内存排布转换发生错误，如NZ排布转换实现方案存在问题。

**机理整理：** 内存排布转换实现错误，改变数据对应关系。

**输入／实现情境：** NZ 排布转换路径；aclnnFlashAttentionScoreGrad BNSD

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.4.3`** · L1 · MODEL_INFERRED
  - 理由：原声明是NZ排布转换。
  - 限制：D08只给FAG BNSD精度异常，不证NZ路径。
  - 证据：A-D08
- **API42 `1.C.6`** · L1 · MODEL_INFERRED
  - 理由：NZ格式可能作为合法format输入控制。
  - 限制：缺目标接口格式实参，不能确认可构造。
  - 证据：DECL:M024
- **V4 `enum_layout`** · L1 · MODEL_INFERRED
  - 理由：原声明NZ转换与布局构造相关。
  - 限制：DTS未说明真实布局转换机理。
  - 证据：A-D08

**待确认项：** D08只定位FAG精度问题，未说明NZ转换；附件fa.zip缺失，不能确认转换根因。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：PARTIALLY_SUPPORTED；原文独立核验=False；设备验证=False。

### 原第8条／M001：算子实现精度不一致：低精度误差累积

**原始定义：** 混合精度模式下npu和gpu的实现行为不一致，如混精下gpu默认先转fp32再计算，npu先fp16计算再转fp32，单算子相同输入gpu侧输出可以正常（超fp16没超fp32）npu溢出

**机理整理：** 混精路径的类型提升顺序不同：GPU先提升至FP32再计算，NPU在低精度计算后再提升，可能先产生溢出或误差。

**输入／实现情境：** 混精训练中 FP16 输入路径（如 prod/matmul）；混合精度训练开关；未设置输入转 FP32 的处理

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.7.6`** · L1 / L2 / L3 · WIKI_DTS_SUMMARY
  - 理由：摘要明确先FP16计算后提升导致prod中间溢出。
  - 限制：历史shape与具体边界未保存；不是本轮原文核验。
  - 证据：A-W01
- **API42 `1.C.2`** · L1 / L3 · MODEL_INFERRED
  - 理由：输入FP16/输出FP32与输出dtype控制技术相关。
  - 限制：摘要未给原调用dtype实参；L3新设计不补成L2。
  - 证据：A-W01
- **V4 `intermediate_overflow`** · L1 / L2 / L3 · WIKI_DTS_SUMMARY
  - 理由：类型提升时机晚于低精乘积，先出现范围溢出。
  - 限制：历史输入值未知；新设计为合成回归。
  - 证据：A-W01
- **V4 `enum_dtype`** · L1 / L2 / L3 · WIKI_DTS_SUMMARY
  - 理由：混精FP16输入、FP32输出及输入转FP32规避有摘要记录。
  - 限制：未验证历史框架版本或实际kernel。
  - 证据：A-W01

**待确认项：** 尚无本机历史正文及精确shape/数值域；不能由此确认每个同算子事件。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：REFINED_WITH_EVIDENCE；原文独立核验=False；设备验证=False。

### 原第9条／M019：数学等价但计算结果不等价

**原始定义：** FA反向计算时顺序不合适（数学等价）导致精度不足

**机理整理：** 数学等价的求值顺序在有限精度下不等价，导致精度不足。

**输入／实现情境：** UNKNOWN；UNKNOWN

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **V4 `cancellation`** · L1 · MODEL_INFERRED
  - 理由：原定义求值次序敏感，近消减可作为技术假设。
  - 限制：没有具体公式和数据，不能计为历史抵消案例。
  - 证据：DECL:M019

**待确认项：** 没有历史链接、公式与复现；不覆盖bool逻辑归约语义错误。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：UNCONFIRMED；原文独立核验=False；设备验证=False。

### 原第10条／M005：浮点数累加序不当

**原始定义：** 通信累加顺序不一致导致测试不通过，如不同测试脚本目前是只按照一种求和顺序来比较，而集合通信ReduceScatter实现不同rank天然就会有不同的加法顺序，出现结果不相等的情况。

**机理整理：** 不同rank的浮点求和顺序与单一顺序测试标杆不一致，fp16/bf16 sum结果出现差异。

**输入／实现情境：** fp16/bf16 + reducetype=sum；HCCL/集合通信 ReduceScatterV

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.C.7`** · L1 · MODEL_INFERRED
  - 理由：D06明确fp16/bf16的reducetype=sum。
  - 限制：只有精度不过，未证归约模式导致原累加序机理。
  - 证据：A-D06
- **V4 `enum_dtype`** · L1 · MODEL_INFERRED
  - 理由：fp16/bf16 sum精度问题具有dtype相关线索。
  - 限制：DTS根因空白，不能确认为混精选择缺陷。
  - 证据：A-D06
- **V4 `long_reduce`** · L1 · MODEL_INFERRED
  - 理由：原声明涉及通信求和顺序，长归约可以放大该类误差。
  - 限制：没有实际归约长度和切换阈值，属技术推导。
  - 证据：DECL:M005

**待确认项：** D06只给精度不过，未给累加顺序根因；上游Part5的SUPPORTS过强。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：PARTIALLY_SUPPORTED；原文独立核验=False；设备验证=False。

### 原第11条／M023：tiling切分策略的逻辑异常

**原始定义：** tiling逻辑计算有误，如未适配多种芯片核数，例310P3 8个核，310P1 10个核，前者能正常执行但后者报错

**机理整理：** Tiling未正确适配不同芯片可用核数，导致特定平台执行错误。

**输入／实现情境：** 310P1/310P3 核数差异；多芯片核数适配

**分类说明：** 芯片核数/tiling适配属于平台与参与者情境；没有输入标签不代表模式无效。

当前没有已建立的API42/V4稀疏关系；这不表示全局不适用。


**待确认项：** D10无权限；上游九条未确认清单漏列此项，不能因列表遗漏视为已确认。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：UNCONFIRMED；原文独立核验=False；设备验证=False。

### 原第12条／M011：tiling切分策略分支错误

**原始定义：** tiling逻辑判断或具体条件判断错误，导致走入错误分支

**机理整理：** Tiling条件判定错误，选择不适用的执行分支。

**输入／实现情境：** 固定 shape + scatter_ 特定输入；fastvideo 迁移；索引计算

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.2.6`** · L1 · MODEL_INFERRED
  - 理由：原模式定义为tiling条件分支错误，可优先定位模板边界。
  - 限制：D09只给固定shape scatter_报错，缺分支阈值。
  - 证据：A-D09
- **V4 `tile_shape`** · L1 · MODEL_INFERRED
  - 理由：tiling分支声明为分块条件审查提供方向。
  - 限制：不能把通用tiling一词当作完整tile谓词。
  - 证据：A-D09

**待确认项：** D09只证明scatter_特定shape报错；不能据算子/描述差异判不同事件，也未证明具体分支。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：PARTIALLY_SUPPORTED；原文独立核验=False；设备验证=False。

### 原第13条／M012：确定性计算未实现

**原始定义：** RMSNorm小算子（Pow + ReduceMean + Add +Rsqrt）实现与RMSNorm算子不同；ReduceMean的确定性未能固定

**机理整理：** 归约过程未固定确定性，导致相同图推理重复调用结果随机。

**输入／实现情境：** MOE 模型入图推理；两次入图推理；小算子组合

**分类说明：** 内部非确定性优先E1，不自动归类API deterministic。

当前没有已建立的API42/V4稀疏关系；这不表示全局不适用。


**待确认项：** W06/W07只作两个资料，不计两个故障；不与LCCL通信确定性自动合并。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：REFINED_WITH_EVIDENCE；原文独立核验=False；设备验证=False。

### 原第14条／M008：浮点数累加序不当

**原始定义：** 累加序实现不一致，如二分累加对比顺序累加，导致精度差异，如未设置export CLOSE_MATMUL_K_SHIFT=1时会有计算误差，具体可能是在router选择时容易出现较大偏差，导致评分下降

**机理整理：** 浮点累加次序随实现/tiling变化，微小差异在router选路中放大。

**输入／实现情境：** 特定 shape 使 matmul 走 K 错峰 tiling；推理；MoE router

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.2.6`** · L1 · MODEL_INFERRED
  - 理由：shape驱动Matmul K错峰tiling在摘要中明确。
  - 限制：未给模板阈值，不能认为±1边界已覆盖。
  - 证据：A-W04
- **V4 `tile_shape`** · L1 · MODEL_INFERRED
  - 理由：shape到K错峰tiling路径有历史线索。
  - 限制：没有真实分块尺寸及其两侧输入。
  - 证据：A-W04
- **V4 `long_reduce`** · L1 · MODEL_INFERRED
  - 理由：K累加次序变化可以指导长归约敏感性对照。
  - 限制：K长度未知，不计历史长归约代表。
  - 证据：A-W04
- **V4 `cancellation`** · L1 · MODEL_INFERRED
  - 理由：浮点求和次序改变对抵消数据可能敏感，可形成定向假设。
  - 限制：原文无正负抵消输入，不能认作历史触发。
  - 证据：A-W04

**待确认项：** W04的TopK/pow及单算子合格linear只是排查分支，不能一并认作根因。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：REFINED_WITH_EVIDENCE；原文独立核验=False；设备验证=False。

### 原第15条／M029：硬件导致算子不支持未拦截

**原始定义：** 如300I系列机器均不支持处理fp32的dtype数据，matmul算子先将输入cast为FP16后进行计算；如310P不支持inf nan；如reshapeAndCacheNd在输入shape较大时走入了使用DataCopyPad分支，在310p上不支持该指令

**机理整理：** 原定义混列FP32不支持而降精度、Inf/NaN不支持及DataCopyPad指令不支持三种能力约束。

**输入／实现情境：** 300I DUO fp32 输入；310P inf/nan；tp8 推理；外积 @ 算子

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.7.2`** · L1 · MODEL_INFERRED
  - 理由：exp/where子算子输入含Inf与平台不支持特殊值相关。
  - 限制：Inf来自图内上游；尚非明确API输入注入且契约未知。
  - 证据：A-W17
- **V4 `special_values`** · L1 · MODEL_INFERRED
  - 理由：特定子算子接收Inf造成平台能力问题。
  - 限制：需固定调用边界及允许特殊值契约，不能从最终NaN反推。
  - 证据：A-W17
- **V4 `enum_dtype`** · L1 / L2 · WIKI_DTS_SUMMARY
  - 理由：300I matmul对FP32输入降为FP16，换outer后改善。
  - 限制：只支持cast子声明，不覆盖DataCopyPad或全部硬件约束。
  - 证据：A-W08

**待确认项：** W08支持cast、W17支持Inf/NaN摘要，DataCopyPad子声明未取证。分别保留，不自动拆分或把软件dtype缺支持等同于硬件不支持。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：PARTIALLY_SUPPORTED；原文独立核验=False；设备验证=False。

### 原第16条／M013：NPU适配引入额外参数

**原始定义：** tik底层对coreNum特性，block_dim为scalar时支持不够导致的，需添加常量折叠配置。

**机理整理：** 原表声明scalar形式block_dim的支持不足，需要常量折叠配置。

**输入／实现情境：** block_dim 为 scalar；310P3；ascend-toolkit 修改引入

**分类说明：** coreNum/block_dim scalar与编译适配相关，不是张量rank-zero输入。

当前没有已建立的API42/V4稀疏关系；这不表示全局不适用。


**待确认项：** D01是自动扫描的BERT精度退化，只初步定位toolkit修改，不能证明tik细节或客户事件身份。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：UNCONFIRMED；原文独立核验=False；设备验证=False。

### 原第17条／M014：tensor下标超出数值范围

**原始定义：** 偏移量超出INT32数值范围

**机理整理：** 地址/元素偏移超出INT32可表示范围，导致索引失真。

**输入／实现情境：** tensor 下标/偏移量超 INT32；UNKNOWN

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.2.4`** · L1 · MODEL_INFERRED
  - 理由：原声明INT32地址偏移超限与大规模算址相关。
  - 限制：缺合法shape/offset公式/逐步位宽和容量。
  - 证据：DECL:M014
- **V4 `huge_shape`** · L1 · MODEL_INFERRED
  - 理由：V4允许地址跨度规模变化，不要求额外显式索引参数。
  - 限制：原声明无实际输入及公式，L1不等于历史已确认。
  - 证据：DECL:M014
- **V4 `index_overflow`** · L1 · MODEL_INFERRED
  - 理由：原声明明确INT32偏移范围；与V4内部窄整数算址定义相符。
  - 限制：缺驱动实参、位宽提升点与容量，不升L2。
  - 证据：DECL:M014

**待确认项：** 缺偏移公式、位宽提升位置及实际容量，不因大shape就确认溢出。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：UNCONFIRMED；原文独立核验=False；设备验证=False。

### 原第18条／M009：精度溢出：数值格式精度不够导致精度溢出

**原始定义：** baddbmm公式out=β input +α (batch1@batch2),计算时括号内为中间变量，超出fp16表示范围

**机理整理：** 中间乘积在低精度范围外，转换/保存为FP16时变为Inf，后续缩放无法恢复。

**输入／实现情境：** baddbmm 中间变量超 FP16 范围；aclnn 拆为 mm + mul 两步

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.7.6`** · L1 / L2 / L3 · WIKI_DTS_SUMMARY
  - 理由：中间batch1@batch2约-70000，cast到FP16溢出。
  - 限制：原始alpha/beta及shape未保存。
  - 证据：A-W05
- **V4 `intermediate_overflow`** · L1 / L2 / L3 · WIKI_DTS_SUMMARY
  - 理由：低精中间乘积超范围，后续缩放不能恢复。
  - 限制：新合成设计不是客户实际输入。
  - 证据：A-W05
- **V4 `enum_dtype`** · L1 / L2 / L3 · WIKI_DTS_SUMMARY
  - 理由：FP16中间cast溢出，转FP32后正常，具有类型路径对照。
  - 限制：未独立读修复代码。
  - 证据：A-W05

**待确认项：** 不把中间结果Inf误归为输入原本含Inf；无本机历史修复Diff。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：REFINED_WITH_EVIDENCE；原文独立核验=False；设备验证=False。

### 原第19条／M025：算子实现精度不一致：指数函数精度实现错误

**原始定义：** Tensor.exponoential_算子实现精度不一致

**机理整理：** 采样实现/随机数生成质量差异影响推理输出和评分。

**输入／实现情境：** vllm 采样 temperature=1 路径；vllm 推理采样

**分类说明：** 采样随机性按随机契约分析，不使用逐次输出完全相同作为通用验收。

当前没有已建立的API42/V4稀疏关系；这不表示全局不适用。


**待确认项：** 原表exponoential_拼写原样保留；不把普通指数函数近似误差与随机采样实现混为一谈。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：REFINED_WITH_EVIDENCE；原文独立核验=False；设备验证=False。

### 原第20条／M028：确定性计算未实现

**原始定义：** reducescatter算子，HCCL场景支持确定性计算，LCCL场景不支持确定性计算

**机理整理：** 通信后端未实现确定性累加/执行，造成重复推理随机波动。

**输入／实现情境：** 并行方式含 reducescatter（dp/tp/ep 组合）；MindIE 服务化；DP 上移特性

**分类说明：** 通信backend及rank参与者属于执行情境，保持与API输入轴独立。

当前没有已建立的API42/V4稀疏关系；这不表示全局不适用。


**待确认项：** W16另含MLA重复和DP上移两个子问题，不可把它们都归为ReduceScatter。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：REFINED_WITH_EVIDENCE；原文独立核验=False；设备验证=False。

### 原第21条／M015：越界读写：内存踩踏覆盖

**原始定义：** FIA算子踩踏reducesum的内存，导致传入残差入口（add_3算子）的数据发生误差，导致残差之后的误差会不断放大

**机理整理：** FIA写入覆盖ReduceSum使用的内存，残差入口错误进一步放大。

**输入／实现情境：** UNKNOWN：上游该字段混入W08的matmul cast事件，不能用于FIA内存踩踏定义。；UNKNOWN：上游该字段混入W08的matmul cast事件，不能用于FIA内存踩踏定义。

**分类说明：** W08与原FIA根因不同，不能继承cast/dtype标签；workspace仅技术候选。

- **V4 `buffer_fit`** · L1 · MODEL_INFERRED
  - 理由：FIA覆盖ReduceSum的原声明可指导workspace容量/复用验证。
  - 限制：W08不支持该根因；没有容量公式或内存图。
  - 证据：DECL:M015

**待确认项：** W08解释的是300I matmul FP32→FP16 cast，未支持FIA踩踏；剔除该证据对本模式的根因支持，保留原引用。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：UNCONFIRMED；原文独立核验=False；设备验证=False。

### 原第22条／M027：竞品实现不一致：特定私有数据排列格式

**原始定义：** 特定私有格式（NC1HWC0、NDHWC、NDC1HWC0、Z_3D）， 不支持as_strided的改变stride的view操作

**机理整理：** 私有格式未适配改变stride的view，使inplace copy未正确作用于预期数据。

**输入／实现情境：** 开启私有格式 + as_strided/copy_；CANN 8.0.RC3 + Atlas 200T A2 Box16

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.4.1`** · L1 · MODEL_INFERRED
  - 理由：历史明确as_strided改stride与copy_失效。
  - 限制：原42 schema/执行器可表达stride的完整条件未绑定。
  - 证据：A-W15
- **API42 `1.4.3`** · L1 · MODEL_INFERRED
  - 理由：私有物理格式与view不兼容有摘要记录。
  - 限制：本项要求SEM-LAYOUT可选参数，目标调用未保存。
  - 证据：A-W15
- **API42 `1.C.6`** · L1 · MODEL_INFERRED
  - 理由：开启/关闭私有格式改变行为，可定向核对format接口。
  - 限制：配置开关不自动等于API实参。
  - 证据：A-W15
- **V4 `view_stride`** · L1 / L2 · WIKI_DTS_SUMMARY
  - 理由：W15明确私有格式as_strided改stride后inplace copy_不生效。
  - 限制：限该子问题；执行器是否保留私有storage尚未验收。
  - 证据：A-W15
- **V4 `enum_layout`** · L1 / L2 · WIKI_DTS_SUMMARY
  - 理由：私有格式启用/关闭与view/copy差异有摘要因果记录。
  - 限制：不把group_norm排查项合并进本根因。
  - 证据：A-W15

**待确认项：** W15中group_norm约0.002差异是排查项，不并入该根因。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：REFINED_WITH_EVIDENCE；原文独立核验=False；设备验证=False。

### 原第23条／M003：tiling切分策略的逻辑异常

**原始定义：** reduce轴没有切多核，但m轴在多batch下切分不同，由于FA是下三角的sparse计算，导致核内的reduce轴切分粒度不同

**机理整理：** m轴随batch改变切分，改变核内reduce粒度和计算顺序，导致单/多batch结果差异。

**输入／实现情境：** 多 batch 推理（同一 query）；图模式推理 + 融合算子

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.6.1`** · L1 / L2 · WIKI_DTS_SUMMARY
  - 理由：摘要明确单/多batch改变m轴切分和核内reduce粒度。
  - 限制：历史batch具体值和kernel未保留。
  - 证据：A-W03
- **API42 `1.8.2`** · L1 · MODEL_INFERRED
  - 理由：下三角sparse与Attention有效域模式技术相关。
  - 限制：缺实际mask编码、模式实参和契约。
  - 证据：A-W03
- **V4 `enum_mask`** · L1 · MODEL_INFERRED
  - 理由：下三角sparse是有效区域选择的明确线索。
  - 限制：未给接口中的模式枚举和参考。
  - 证据：A-W03
- **V4 `tile_shape`** · L1 · MODEL_INFERRED
  - 理由：多batch使m/reduce切分粒度变化，可指导目标tile边界分析。
  - 限制：缺tile长度及kA±1输入。
  - 证据：A-W03

**待确认项：** 不能把同shape、同二进制的随机竞争等同于输入变化后的计算差异。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：REFINED_WITH_EVIDENCE；原文独立核验=False；设备验证=False。

### 原第24条／M016：精度溢出：特定硬件数值格式导致精度溢出

**原始定义：** 调用的是BNInferenceD算子，该算子在310P fp16场景有概率发生精度溢出

**机理整理：** 倒数等中间运算超出FP16表示范围，造成归一化精度溢出。

**输入／实现情境：** 310P fp16 + weight 极小；onnx→om 转换

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.7.4`** · L1 / L2 · WIKI_DTS_SUMMARY
  - 理由：W09明确极小weight进入1/weight，FP16倒数溢出。
  - 限制：未保存实际weight、阈值或完整接口。
  - 证据：A-W09
- **V4 `near_singular`** · L1 / L2 · WIKI_DTS_SUMMARY
  - 理由：分母weight趋小与倒数溢出的因果在摘要中明确。
  - 限制：不能把这条支持转给M002的负方差。
  - 证据：A-W09
- **V4 `enum_dtype`** · L1 / L2 · WIKI_DTS_SUMMARY
  - 理由：310P FP16计算范围与该失效直接相关。
  - 限制：具体高精开关是否API参数未证，不映射enum_compute。
  - 证据：A-W09

**待确认项：** 只在摘要所述310P、极小weight条件下支持；精确阈值及实现仍未知。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：REFINED_WITH_EVIDENCE；原文独立核验=False；设备验证=False。

### 原第25条／M002：边界值异常

**原始定义：** INTrainingUpdataV2算子variance算出来有负值，导致开根后变为nan

**机理整理：** 方差计算结果出现负值，随后开平方产生NaN。

**输入／实现情境：** 纯黑/大部分为 0 的输入（in1 大部分为 0）；onnx→om 离线推理

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.1.3`** · L1 · MODEL_INFERRED
  - 理由：纯黑/大部分0输入与零分布技术相关。
  - 限制：未保留实际整行/块全0张量；不从V4 zeros自动转换。
  - 证据：A-W02
- **V4 `zeros`** · L1 / L2 · WIKI_DTS_SUMMARY
  - 理由：W02将in1大部分0和负方差开根NaN联系起来。
  - 限制：仅摘要级代表；具体算子签名、shape和阈值未知。
  - 证据：A-W02
- **V4 `near_singular`** · L1 · MODEL_INFERRED
  - 理由：方差及sqrt定义域边界可指导低方差定向分析。
  - 限制：负方差不自动证明合法近零量输入，仍需原值与公式。
  - 证据：A-W02

**待确认项：** 方差公式、负值阈值及修复代码未取得。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：REFINED_WITH_EVIDENCE；原文独立核验=False；设备验证=False。

### 原第26条／M010：融合算子反量化位置不当

**原始定义：** 图优化阶段因反量化（Dequantize）节点摆放位置错误，导致本应以纯INT8执行的融合算子退化为“反量化+高精度计算+再量化”路径，或使量化参数（scale/zero_point）传递断裂，最终引发精度异常

**机理整理：** 反量化节点位置或量化参数传递错误，改变融合图的计算路径。

**输入／实现情境：** UNKNOWN；图融合优化

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **V4 `enum_quant`** · L1 · MODEL_INFERRED
  - 理由：反量化节点与量化语义相关，可定位待核输入控制。
  - 限制：只有图层声明，不证明API提供量化模式选择。
  - 证据：DECL:M010

**待确认项：** 原定义完整保留；没有图样例或历史链接，不等同于模式不存在。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：UNCONFIRMED；原文独立核验=False；设备验证=False。

### 原第27条／M030：输入数据类型强转低精丢失

**原始定义：** conv2d算子在进行计算之前，会把输入的tensor强制转换成FP16格式的，因为算子内部不支持FP32格式。所以计算出的结果和onnx就不对齐

**机理整理：** 计算前将FP32输入降为FP16，损失信息并在后续argmax等非线性决策处放大。

**输入／实现情境：** conv2d 输入含 FP32 精度需求；encoder 小模型转 om

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **V4 `enum_dtype`** · L1 / L2 · WIKI_DTS_SUMMARY
  - 理由：Conv2d计算前FP32转FP16与精度损失有摘要因果联系。
  - 限制：平台和框架路径限制保留；不是输出dtype问题。
  - 证据：A-W18
- **V4 `rounding`** · L1 · MODEL_INFERRED
  - 理由：输入窄化会丢失可表示精度，可指导临界值设计。
  - 限制：历史输入数值未给，不计为已存在中点边界代表。
  - 证据：A-W18

**待确认项：** 不把其他算子输出类型/接口标记错误一律等同于输入cast。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：REFINED_WITH_EVIDENCE；原文独立核验=False；设备验证=False。

### 原第28条／M017：tiling切分策略不同分支处理精度不一致

**原始定义：** PageAttention blockSize 不同时，会有不同的tiling选择，结果精度不能保持二进制一致

**机理整理：** 不同分块/算法更新路径产生不同舍入累加结果，不能保证跨配置二进制一致。

**输入／实现情境：** batch/headnum/blockSize 触发不同 tiling 分支；服务化推理；batchsize 变化

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.6.1`** · L1 / L2 · WIKI_DTS_SUMMARY
  - 理由：服务化batchsize变化引起PA/FA切分及结果变化。
  - 限制：摘要说符合精度标准，代表数值敏感情形而非已证实Bug。
  - 证据：A-W10
- **API42 `1.2.6`** · L1 · MODEL_INFERRED
  - 理由：batch/headnum/blockSize会选不同tiling。
  - 限制：没有实际模板阈值和±1对照。
  - 证据：A-W10
- **V4 `tile_shape`** · L1 · MODEL_INFERRED
  - 理由：PA blockSize不同与逐步softmax更新策略相关。
  - 限制：缺tile边界谓词；不是固定实参随机竞争。
  - 证据：A-W10

**待确认项：** W10明确符合算子精度标准；不能当作已证实Kernel Bug或同实参随机竞争。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：REFINED_WITH_EVIDENCE；原文独立核验=False；设备验证=False。

### 原第29条／M021：矩阵乘加融合后数据格式转换精度丢失

**原始定义：** MatmulAtomicAddUbFusion打开矩阵乘法加法融合，特定shape下matmul算子 在线编译和二进制的输出会有精度差距

**机理整理：** 融合及编译路径改变Cast和计算顺序，导致在线编译与二进制路径输出不一致。

**输入／实现情境：** input0[201,11008]×input1[11008,4096]；在线编译 vs 二进制编译

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **V4 `enum_dtype`** · L1 · MODEL_INFERRED
  - 理由：在线编译Cast fp16→fp32→fp16涉及类型路径。
  - 限制：是内部融合行为，未证API精度选项。
  - 证据：A-W13
- **V4 `rounding`** · L1 · MODEL_INFERRED
  - 理由：Cast有效位损失与窄化转换相关。
  - 限制：没有中点或转换临界值数据；ULP在摘要标准内。
  - 证据：A-W13

**待确认项：** 历史摘要同时写门禁拦截和ULP达标，应分别保留指标/判定口径；不自动推成不合格Bug。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：REFINED_WITH_EVIDENCE；原文独立核验=False；设备验证=False。

### 原第30条／M018：浮点数累加序不当

**原始定义：** attention算子输入shape不一样导致Tiling 策略并行粒度变化，输出微小差异带来精度误差

**机理整理：** 原表将不同shape下的输出微差归因于Tiling并行粒度变化。

**输入／实现情境：** 输入 shape 不同；attention 推理/训练大算子差异

**分类说明：** 逐条对照原定义、输入条件和摘要；只保存下列实际候选关系，未列出的组合未逐格作语义否定。

- **API42 `1.5.1`** · L1 · MODEL_INFERRED
  - 理由：4096/91上下文比较可提供非对齐序列审查线索。
  - 限制：上下文不同且未闭环，不能把91直接计为非对齐故障。
  - 证据：A-W11
- **API42 `1.5.2`** · L1 · MODEL_INFERRED
  - 理由：文档出现4096上下文，具有长序列分析入口。
  - 限制：缺同情景长短序列因果对照。
  - 证据：A-W11

**待确认项：** W11自述不再定位，没有闭环，不能确认具体累加序。；冻结工作簿和28份原始快照未在本机取得；引用为Markdown转录/摘要，不是重新核验网页。

证据状态：UNCONFIRMED；原文独立核验=False；设备验证=False。

## 复现本报告

```sh
python scripts/render_baseline30_review.py render reports/baseline-30-api42-v4-20261111
python scripts/render_baseline30_review.py verify reports/baseline-30-api42-v4-20261111
node scripts/verify_baseline30_ui.cjs reports/baseline-30-api42-v4-20261111
```

命令仅重放已冻结的数据和检查离线报告，不重新运行Init、采集、模型或设备。历史验证回执保留其原日期和范围，新发布检查单独记录。
