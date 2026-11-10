# CANN Expansion：公开技术证据与审查结果

2026-11-10。本包发布19条公开代码技术案例、23条API42/V4稀疏关系及可复核源码定位。正式入库、WB客户事件确认、NPU/GPU执行均为0。
应用版本仍为0.1.20；本次提交增加独立审查数据及离线校验/报告工具。

## 先看结论

- 原30条完成审查；18/30模式有API42关系，25条原关系按条件去重为18/42。
- 原18＋新增明确分支关系为19/42（新增1.C.3）。再含quant_mode=1公开测试配置为20/42（另含1.C.1）。19不表示19项全部经过源码证实；20不表示配置单独致因。
- 原历史摘要代表3/42，原测试设计3/42，设备验证0/42；三种统计不混用。
- 当前草案动作为4条案例追加、10条机制详情、3条新候选、2条范围外。动作不是根因相同或精度影响已证实。
- 42项都有设计索引，其中5项有既有配方引用；不是42项可执行覆盖。宽口径22项、窄口径23项缺口仍保留，缺口历史检索未执行。

## 阅读与复现

[下载完整HTML结果](CANN_EXPANSION_FULL_RESULTS.html)（单文件，下载后在本地或远端机器打开） · [每案最强证据索引](evidence/STRONGEST_EVIDENCE.md) · [19案例完整数据](technical_cases.json) · [证据观察及定位](evidence/observations.json) · [42条件统计](api42_coverage.json) · [42设计索引](api42_test_catalog.json) · [验证记录](validation/publication_validation.json)

完整HTML包括案例、模式增量/候选、API42、V4、测试、缺口和所有公开证据；完整表示发布内容齐备，不表示42项已覆盖或设备已验收。旧HTML文件名保留为相同内容的兼容入口。GitHub文件页显示HTML源码，下载后打开才能使用交互视图。

```sh
python -m faultaudit.review_bundle evidence reports/expansion-v1-20261110
python -m faultaudit.review_bundle render reports/expansion-v1-20261110
python -m faultaudit.review_bundle manifest reports/expansion-v1-20261110
python -m faultaudit.review_bundle verify reports/expansion-v1-20261110
python -m unittest discover -s tests -p test_review_bundle.py -v
node scripts/verify_expansion_publication_ui.cjs reports/expansion-v1-20261110
```

这些命令只读取公开包、检查数据/Host算术/代码语法并生成静态报告，不执行所展示的设备配方。manifest仅在显式重建后更新哈希，verify不会自动修复或删改数据。

## 发布边界

原始Init、30条原定义正文/15列、内部Wiki/DTS、原周报、客户原文、现场state和模型请求响应未提交。原模式只保留不含定义正文的ID—条件关系索引，用于重算统计；公开读者不能据这些摘要计数声称重新验证了历史原文。
与原模式的比较是技术评审建议。源码证据只支持正文中的实际修改，不证明对应客户事件。GitCode多为选段观察，不冒充完整页面或完整PR核验。
API42采用本包冻结定义及其原SHA；仓库knowledge同名Markdown字节SHA不同，不自动互换。V4保持6主题、31条件类、55种构造情形、64挂载、195指导案例及E1–E5，42与V4不自动转换标签。

## 19条案例总览

|案例|算子/对象|机理关系|影响状态|草案动作|
|---|---|---|---|---|
|[TC-PLUGIN-ASYNC](#tc-plugin-async)|frequency_regulator|FUNCTIONAL_OUT_OF_SCOPE|RESOURCE_LIFECYCLE_FAILURE_REPORTED|RELATED_OUT_OF_SCOPE|
|[TC-GRADPROBS-DTYPE](#tc-gradprobs-dtype)|npu_moe_token_unpermute_grad|NEW_MECHANISM_CANDIDATE|OUTPUT_DTYPE_CONTRACT_CHANGE|NEW_CANDIDATE|
|[TC-RADIX-SYNC](#tc-radix-sync)|RadixTopK|SAME_MECHANISM|PRECISION_ISSUE_REPORTED|ADD_CASE_TO_EXISTING|
|[TC-RADIX-API-WORKSPACE](#tc-radix-api-workspace)|RadixTopK|FAMILY_RELATED|IMPACT_UNCONFIRMED|EXTEND_EXISTING_MODE|
|[TC-BOOL-REDUCE](#tc-bool-reduce)|ReduceProd/ReduceAll|NEW_MECHANISM_CANDIDATE|BOOL_REDUCTION_PATH_CHANGE|NEW_CANDIDATE|
|[TC-GEMM-PRECISION-FLAG](#tc-gemm-precision-flag)|addmm/baddbmm|FAMILY_RELATED|PRECISION_PATH_CHANGE_SUPPORTED|EXTEND_EXISTING_MODE|
|[TC-GATHER-SCALAR-COUNT](#tc-gather-scalar-count)|GatherV3|FAMILY_RELATED|DISPATCH_ERROR_SUPPORTED_PRECISION_UNCONFIRMED|ADD_CASE_TO_EXISTING|
|[TC-MATMUL-DISPATCH-DTYPE](#tc-matmul-dispatch-dtype)|MatMulV3|FUNCTIONAL_OUT_OF_SCOPE|BINARY_DISPATCH_FAILURE_REPORTED|RELATED_OUT_OF_SCOPE|
|[TC-REPEAT-INT32-ROUTE](#tc-repeat-int32-route)|RepeatInterleave|FAMILY_RELATED|DISPATCH_ERROR_SUPPORTED_PRECISION_UNCONFIRMED|ADD_CASE_TO_EXISTING|
|[TC-FIA-M-PIPE](#tc-fia-m-pipe)|IncreFlashAttention|FAMILY_RELATED|DEPENDENCY_REPAIR_SUPPORTED|EXTEND_EXISTING_MODE|
|[TC-GMM-K0](#tc-gmm-k0)|GroupedMatmul|FAMILY_RELATED|SPECIAL_PATH_REPAIR_OUTPUT_UNCONFIRMED|EXTEND_EXISTING_MODE|
|[TC-FAG-MTE2-DIM](#tc-fag-mte2-dim)|FlashAttentionScoreGrad|FAMILY_RELATED|OOM_REPORTED|EXTEND_EXISTING_MODE|
|[TC-NSA-TOPK-TMPUB](#tc-nsa-topk-tmpub)|NsaCompressAttention|FAMILY_RELATED|IMPACT_UNCONFIRMED|ADD_CASE_TO_EXISTING|
|[TC-SFAG-EVENT-ID](#tc-sfag-event-id)|SparseFlashAttentionGrad|FAMILY_RELATED|HANG_REPORTED|EXTEND_EXISTING_MODE|
|[TC-MEGAMOE-REUSE-SPAN](#tc-megamoe-reuse-span)|MegaMoE GMM1/SwiGLU|FAMILY_RELATED|UNREAD_INPUT_OVERWRITE_SUPPORTED|EXTEND_EXISTING_MODE|
|[TC-LI-DUPLICATE-SPACE](#tc-li-duplicate-space)|LightningIndexer|FAMILY_RELATED|MEMORY_FOOTPRINT_ERROR_REPORTED|EXTEND_EXISTING_MODE|
|[TC-FP8-VSCALE](#tc-fp8-vscale)|FP8 GQA FusedInferAttentionScore|NEW_MECHANISM_CANDIDATE|SCALE_BINDING_CHANGE_SUPPORTED|NEW_CANDIDATE|
|[TC-DEQUANT-REDUCE-STRIDE](#tc-dequant-reduce-stride)|npu_dequant_swiglu_quant|FAMILY_RELATED|COMBINED_FIX_PRECISION_REPORTED|EXTEND_EXISTING_MODE|
|[TC-DEQUANT-SCALE-BUFFER](#tc-dequant-scale-buffer)|npu_dequant_swiglu_quant|FAMILY_RELATED|CO_CHANGED_COMPONENT_ONLY|EXTEND_EXISTING_MODE|

### TC-PLUGIN-ASYNC

**调频plugin异步资源生命周期不一致**

- 根因/实现缺陷：手工管理的workspace/executor/ACL tensor生命周期与框架异步执行不一致，改由EXEC_NPU_CMD管理。
- 错误行为：手工创建/释放 workspace、executor、ACL tensor，显式同步与主机拷贝
- 修复机制：TensorWrapper + EXEC_NPU_CMD，由框架适配资源与异步生命周期
- 原模式关系：['M004', 'M015']；封装生命周期问题，未证明CANN数值kernel缺陷。
- 触发前提：框架异步调用与手工executor/workspace释放生命周期不匹配
- 待证：没有证明为CANN数值kernel缺陷；工程案例与精度模式范围分开
- 测试设计：DESIGN-PLUGIN-ASYNC（未执行）。

- [https://gitcode.com/Ascend/MindIE-SD/blob/f4537472b5a9ffefb47f5c10b8b8c05843c4b92a/csrc/plugin/frequency_regulator.cpp](https://gitcode.com/Ascend/MindIE-SD/blob/f4537472b5a9ffefb47f5c10b8b8c05843c4b92a/csrc/plugin/frequency_regulator.cpp)；文件 `csrc/plugin/frequency_regulator.cpp`；定位 `实现替换段`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: 手工 ACL executor/workspace 管理
after:  EXEC_NPU_CMD
```

### TC-GRADPROBS-DTYPE

**梯度输出dtype取错输入对象**

- 根因/实现缺陷：grad_probs应继承probs类型，却使用grad_unpermuted_tokens类型；混合类型下返回契约错误，meta和实际输出分配同时修正。
- 错误行为：grad_probs 沿用 grad_unpermuted_tokens 的 dtype
- 修复机制：grad_probs 使用 probs.scalar_type()/empty_like(probs) 的 dtype
- 原模式关系：['M001', 'M030']；输出类型归属对象有源码依据；接口层收录范围和设备返回仍待审查。
- 触发前提：probs.dtype != grad_unpermuted_tokens.dtype；grad_probs错误继承后者类型
- 待证：现场直接返回值/Meta运行；是否纳入CANN精度库的接口层范围
- 测试设计：DESIGN-GRAD-META, DESIGN-GRAD-DEVICE（未执行）。

- [https://gitcode.com/Ascend/op-plugin/blob/253d85bab82c94d6701542b45134cbb33d33690d/op_plugin/python/meta/_meta_registrations.py](https://gitcode.com/Ascend/op-plugin/blob/253d85bab82c94d6701542b45134cbb33d33690d/op_plugin/python/meta/_meta_registrations.py)；文件 `op_plugin/python/meta/_meta_registrations.py`；定位 `5992`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: torch.empty_like(probs, dtype=grad_unpermuted_tokens.dtype)
after:  torch.empty_like(probs)
```

### TC-RADIX-SYNC

**RadixTopK搬运/计算依赖缺同步**

- 根因/实现缺陷：批处理TopK的核间及搬运/计算依赖缺同步，增加SyncAll及SToV等同步。
- 错误行为：若干搬运/计算及核间依赖没有对应同步
- 修复机制：增加SyncAll、SToV、MTE3ToS等依赖同步
- 原模式关系：M007；多核及搬运/计算依赖缺同步，与M007相符；同PR另有空间修复，贡献尚未隔离。
- 触发前提：目标RadixTopK UB/WS分支存在未满足的生产者→消费者依赖
- 待证：失败shape/k/dtype、实际参与核和依赖trace；单独回退同步修复
- 测试设计：DESIGN-RADIX-SYNC（未执行）。

- [https://gitcode.com/cann/ops-math/blob/2486e024c457afbc49dbc266d418be71eaadfce1/math/radix_top_k/op_kernel/radix_top_k_ub.h](https://gitcode.com/cann/ops-math/blob/2486e024c457afbc49dbc266d418be71eaadfce1/math/radix_top_k/op_kernel/radix_top_k_ub.h)；文件 `math/radix_top_k/op_kernel/radix_top_k_ub.h`；定位 `200/297/377`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: 缺少所示同步
after:  SyncAll / SToV
```

### TC-RADIX-API-WORKSPACE

**RadixTopK未计入库API workspace**

- 根因/实现缺陷：workspace总量未加AscendC库API所需空间，修复通过GetLibApiWorkSpaceSize计入分配。
- 错误行为：workspace总量未计库API需求
- 修复机制：通过GetLibApiWorkSpaceSize把库API需求加进预算
- 原模式关系：M015；预算漏计成立，但没有实际访问区间/错误输出证明M015意义的踩踏。
- 触发前提：W_api>0 && W_alloc_old<W_kernel+W_api；旧总预算未包含库API需求
- 待证：W_api/W_kernel对应的合法输入、实际分配及访问区间
- 测试设计：DESIGN-RADIX-API-WORKSPACE（未执行）。

- [https://gitcode.com/cann/ops-math/blob/2486e024c457afbc49dbc266d418be71eaadfce1/math/radix_top_k/op_host/radix_top_k_tiling.cpp](https://gitcode.com/cann/ops-math/blob/2486e024c457afbc49dbc266d418be71eaadfce1/math/radix_top_k/op_host/radix_top_k_tiling.cpp)；文件 `math/radix_top_k/op_host/radix_top_k_tiling.cpp`；定位 `150–152`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: workspace 未加 API 需求
after:  GetLibApiWorkSpaceSize + workspaceSize
```

### TC-BOOL-REDUCE

**BOOL输出选错归约算法**

- 根因/实现缺陷：910B/910_93且out BOOL时原走数值ReduceProd，改向ExecuteProd传dimList并使用ReduceAll逻辑归约。
- 错误行为：bool 输出沿用一般 ReduceProd 路径
- 修复机制：条件成立则向 ExecuteProd 传 dimList，转至 ReduceAll；其他路径仍 ReduceProd
- 原模式关系：['M019', 'M001']；逻辑归约依赖有限精度连乘有独立抽象价值；仍需旧输出与转换链，不按候选强弱排序替代证据。
- 触发前提：SoC为910B/910_93 && out.dtype=显式dtype=BOOL；目标dimList进入ReduceAll
- 待证：历史失败输入、旧新输出、转换链；区分下溢与独立BOOL契约问题
- 测试设计：DESIGN-BOOL-ACL（未执行）。

- [https://gitcode.com/cann/ops-math/blob/adbf5a82f418507f1baf4e32020718571d9b5309/math/reduce_prod/op_api/aclnn_prod.cpp](https://gitcode.com/cann/ops-math/blob/adbf5a82f418507f1baf4e32020718571d9b5309/math/reduce_prod/op_api/aclnn_prod.cpp)；文件 `math/reduce_prod/op_api/aclnn_prod.cpp`；定位 `187–193`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: ReduceProd(selfCast, axes,...)
after:  dimList != nullptr 时 ReduceAll(selfCast, dimList,...)
```
- [https://gitcode.com/cann/ops-math/blob/adbf5a82f418507f1baf4e32020718571d9b5309/math/reduce_prod/op_api/aclnn_prod.cpp](https://gitcode.com/cann/ops-math/blob/adbf5a82f418507f1baf4e32020718571d9b5309/math/reduce_prod/op_api/aclnn_prod.cpp)；文件 `math/reduce_prod/op_api/aclnn_prod.cpp`；定位 `232–242/289–294`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: 未按 bool/SOC 选择
after:  useReduceAll = out BOOL && (910B || 910_93)
```
- [https://gitcode.com/cann/ops-math/blob/95e7a81e1eca655b98f598fcafe9cd090ec1b8e5/math/reduce_prod/op_api/aclnn_prod.cpp](https://gitcode.com/cann/ops-math/blob/95e7a81e1eca655b98f598fcafe9cd090ec1b8e5/math/reduce_prod/op_api/aclnn_prod.cpp)；文件 `math/reduce_prod/op_api/aclnn_prod.cpp`；定位 `187–193`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: ReduceProd(selfCast, axes,...)
after:  dimList != nullptr 时 ReduceAll(selfCast, dimList,...)
```
- [https://gitcode.com/cann/ops-math/blob/95e7a81e1eca655b98f598fcafe9cd090ec1b8e5/math/reduce_prod/op_api/aclnn_prod.cpp](https://gitcode.com/cann/ops-math/blob/95e7a81e1eca655b98f598fcafe9cd090ec1b8e5/math/reduce_prod/op_api/aclnn_prod.cpp)；文件 `math/reduce_prod/op_api/aclnn_prod.cpp`；定位 `232–242/289–294`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: 未按 bool/SOC 选择
after:  useReduceAll = out BOOL && (910B || 910_93)
```

### TC-GEMM-PRECISION-FLAG

**beta=0分支遗漏16入32出精度标记**

- 根因/实现缺陷：addmm/baddbmm的beta=0分支未把NeedEnableFp32Output结果传入ExecGemmV3WithAlphaBetaOp，导致计算精度请求未沿该分支生效。
- 错误行为：该分支未传 enableGemm16In32Out
- 修复机制：NeedEnableFp32Output 计算开关并传入执行函数
- 原模式关系：M001；M001精度路径的强扩展；控制信息遗漏不同于原例升精时点，不声称已发生Inf。
- 触发前提：beta=0 && cubeMathType=4 && NeedEnableFp32Output(...)为真；执行分支未接收该标记
- 待证：NeedEnableFp32Output的完整支持条件、输入输出dtype、旧新参考误差
- 测试设计：DESIGN-GEMM-PRECISION-FLAG（未执行）。

- [https://gitcode.com/cann/ops-nn/blob/36adda8717a669bd39d197c69e6b63130c6d2831/matmul/batch_mat_mul_v3/op_host/op_api/aclnn_baddbmm.cpp](https://gitcode.com/cann/ops-nn/blob/36adda8717a669bd39d197c69e6b63130c6d2831/matmul/batch_mat_mul_v3/op_host/op_api/aclnn_baddbmm.cpp)；文件 `matmul/batch_mat_mul_v3/op_host/op_api/aclnn_baddbmm.cpp`；定位 `319–322`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: ExecGemmV3WithAlphaBetaOp(...executor)
after:  NeedEnableFp32Output(...); ExecGemmV3WithAlphaBetaOp(..., enableGemm16In32Out)
```
- [https://gitcode.com/cann/ops-nn/blob/36adda8717a669bd39d197c69e6b63130c6d2831/matmul/mat_mul_v3/op_host/op_api/aclnn_addmm.cpp](https://gitcode.com/cann/ops-nn/blob/36adda8717a669bd39d197c69e6b63130c6d2831/matmul/mat_mul_v3/op_host/op_api/aclnn_addmm.cpp)；文件 `matmul/mat_mul_v3/op_host/op_api/aclnn_addmm.cpp`；定位 `636–638`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: 无此开关
after:  传 enableGemm16In32Out
```

### TC-GATHER-SCALAR-COUNT

**索引元素计数混入字节倍数导致Gather模式误选**

- 根因/实现缺陷：indexSize原由ge::GetSizeByDataType(index->GetDataType())初始化，再乘索引各维，误把带元素字节倍数的计数与1536元素阈值比较；修复从1计算numel。只证明模式判定缺陷，数值影响未证实。
- 错误行为：例如self FP32[32768]、INT32 index[1535]，旧计数6140>=1536可能保留mode=1；新numel1535<1536应转mode=0。
- 修复机制：indexSize=1个元素
- 原模式关系：M011；API实现模式分派不等于tiling模板；当前没有证实精度错误、性能回退或实际mode日志。
- 触发前提：non-Regbase && dim=0 && batchDims=0 && initial_mode=1；self_bytes>=102400；index_numel<1536<=index_numel*index_itemsize
- 待证：目标环境的index类型合法性、实际mode消费日志；INT64需单独核对接口类型契约
- 测试设计：DESIGN-GATHER-THRESHOLD（未执行）。

- [https://gitcode.com/cann/ops-nn/blob/f1359e5fbab5971b2aeeda58e2fdc5ec8e92fab0/index/gather_v2/op_api/aclnn_gather_v3.cpp](https://gitcode.com/cann/ops-nn/blob/f1359e5fbab5971b2aeeda58e2fdc5ec8e92fab0/index/gather_v2/op_api/aclnn_gather_v3.cpp)；文件 `index/gather_v2/op_api/aclnn_gather_v3.cpp`；定位 `204`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: auto indexSize = ge::GetSizeByDataType(index->GetDataType());
after:  indexSize = 1
```
- [https://gitcode.com/cann/ops-nn/pull/1562/diffs](https://gitcode.com/cann/ops-nn/pull/1562/diffs)；文件 `index/gather_v2/op_api/aclnn_gather_v3.cpp`；定位 `204`；EXACT_OBSERVED_DIFF_LINES。
```text
before: auto indexSize = ge::GetSizeByDataType(index->GetDataType());
after:  auto indexSize = 1;
```

### TC-MATMUL-DISPATCH-DTYPE

**二进制分派检查使用转换前类型**

- 根因/实现缺陷：MatMul支持性检查使用ori_info类型，实际执行类型已转换；改用support_info，避免找不到MatMulV3二进制。
- 错误行为：检查 ori_info 的 self/bias dtype
- 修复机制：改为实际支持信息 support_info 的 self/bias dtype
- 原模式关系：['M011', 'M001']；找不到二进制属于功能分派；只保留与M011的技术关系，不进入精度案例主表。
- 触发前提：API输入全FP16；内部转换后support_info与ori_info的类型不同；目标MatMulV3支持性检查仍读ori_info
- 待证：合法shape/格式、目标平台及实际二进制匹配记录
- 测试设计：DESIGN-MATMUL-DISPATCH-DTYPE（未执行）。

- [https://gitcode.com/cann/ops-nn/blob/e7ad2aa953c5b4d5d9e1262680e1045cabbff4e4/matmul/common/op_host/op_api/matmul_util.cpp](https://gitcode.com/cann/ops-nn/blob/e7ad2aa953c5b4d5d9e1262680e1045cabbff4e4/matmul/common/op_host/op_api/matmul_util.cpp)；文件 `matmul/common/op_host/op_api/matmul_util.cpp`；定位 `120`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: ori_info.self/bias dtype
after:  support_info.self/bias dtype
```

### TC-REPEAT-INT32-ROUTE

**超大单轴漏掉安全实现选路**

- 根因/实现缺陷：view shape某轴超过INT32_MAX且dtype受支持时需要选择V2；原分派遗漏该边界约束。
- 错误行为：边界大shape仍可能走存在int32类型溢出的路径
- 修复机制：满足大shape与dtype条件则选择V2路径
- 原模式关系：M011；大shape选路条件有据，内部溢出及错误数值未证实。
- 触发前提：exists(axis): xViewShape[axis]>INT32_MAX_NUM && CheckType(dtype)；需要选择V2
- 待证：实际大tensor资源、旧新路径；内部窄整数地址公式尚无
- 测试设计：DESIGN-REPEAT-INT32-ROUTE（未执行）。

- [https://gitcode.com/cann/ops-nn/blob/16c16335573d6086dbe7524ecb80e5c605692413/index/repeat_interleave/op_api/repeat_interleave.cpp](https://gitcode.com/cann/ops-nn/blob/16c16335573d6086dbe7524ecb80e5c605692413/index/repeat_interleave/op_api/repeat_interleave.cpp)；文件 `index/repeat_interleave/op_api/repeat_interleave.cpp`；定位 `49–57`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: 未见该大shape判定
after:  xViewShape[i] > INT32_MAX_NUM && CheckType(...) => true
```

### TC-FIA-M-PIPE

**矩阵计算段之间缺PIPE_M屏障**

- 根因/实现缺陷：ComputeMm1的相邻Mmad计算段之间缺少矩阵流水完成屏障；本轮补读#12716新行907加入PipeBarrier<PIPE_M>()。
- 错误行为：ComputeMm1相邻Mmad计算段间新行907处原为空行
- 修复机制：该处新增PipeBarrier<PIPE_M>()；其余大Diff不作全量核验声明
- 原模式关系：M007；核内矩阵流水与原M007多核搬运情境不同，改为机制详情，不共用原多核测试替代。
- 触发前提：命中IfaMatmulFullQuant::ComputeMm1中目标相邻Mmad计算段，且两段存在未完成的矩阵流水依赖
- 待证：合法API到目标模板的选择谓词、实际依赖trace、单独回退实验
- 测试设计：DESIGN-FIA-M-PIPE（未执行）。

- [https://gitcode.com/cann/ops-transformer/pull/12716/diffs](https://gitcode.com/cann/ops-transformer/pull/12716/diffs)；文件 `attention/incre_flash_attention/op_kernel/arch22/ifa_service_matmul_full_quant.h`；定位 `选定变更`；SELECTED_SOURCE_OBSERVATION_WITH_EXACT_TOKENS。
```text
before: blank line
after:  PipeBarrier<PIPE_M>();
```

### TC-GMM-K0

**Split-K空归约维度处理不当**

- 根因/实现缺陷：K=0的SPLIT_K路径仍走高阶Matmul tiling/通用空输入检查，修复按特殊空归约语义处理，代码注释说明由kernel清零。
- 错误行为：K=0仍调用高阶 Matmul tiling 或走通用空tensor处理
- 修复机制：SPLIT_K专用校验；K=0由kernel清零，跳过高阶API GetTiling
- 原模式关系：M020；K=0特殊tiling/空归约路径已定位，未证明某次错误输出未清零；同时比较M020与M011。
- 触发前提：groupType=SPLIT_K && maxK=0；M/N及其他接口条件合法
- 待证：完整列表/枚举契约、合法M/N及输出清零的实际结果
- 测试设计：DESIGN-GMM-K0（未执行）。

- [https://gitcode.com/cann/ops-transformer/blob/9888a6ca348359af8d03167e24483fe913354b7a/gmm/grouped_matmul/op_host/op_tiling/grouped_matmul_tiling.cpp](https://gitcode.com/cann/ops-transformer/blob/9888a6ca348359af8d03167e24483fe913354b7a/gmm/grouped_matmul/op_host/op_tiling/grouped_matmul_tiling.cpp)；文件 `gmm/grouped_matmul/op_host/op_tiling/grouped_matmul_tiling.cpp`；定位 `1387`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: 无K0跳过分支
after:  groupType_ == SPLIT_K && maxK_ == 0：kernel清零，不需要高阶APItiling
```

### TC-FAG-MTE2-DIM

**搬运尺寸取错矩阵维度**

- 根因/实现缺陷：FAG bn2 MM12的四处MTE2配置用mm1BaseK而非dimD，造成搬运范围与实际维度不符。
- 错误行为：四处配置使用 mm1BaseK
- 修复机制：四处改为实际 dimD
- 原模式关系：M004；搬运尺寸源错用不等于偏移算错或越界；仅作M004相关机制候选。
- 触发前提：命中FAG bn2 MM12 MTE2配置且mm1BaseK与实际dimD不一致
- 待证：外部headDim/shape到内部维度的关系、合法路径、真实搬运区间
- 测试设计：DESIGN-FAG-MTE2-DIM（未执行）。

- [https://gitcode.com/cann/ops-transformer/blob/f277be164030f3dd68cb041b2ab3f2b83e62d1d1/attention/flash_attention_score_grad/op_kernel/arch32/flash_attention_score_grad_s1s2_bn2.h](https://gitcode.com/cann/ops-transformer/blob/f277be164030f3dd68cb041b2ab3f2b83e62d1d1/attention/flash_attention_score_grad/op_kernel/arch32/flash_attention_score_grad_s1s2_bn2.h)；文件 `attention/flash_attention_score_grad/op_kernel/arch32/flash_attention_score_grad_s1s2_bn2.h`；定位 `1681/1683/2007/2009`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: mm1BaseK
after:  dimD
```

### TC-NSA-TOPK-TMPUB

**TopK临时UB需求预算不足**

- 根因/实现缺陷：以20*S2align估算TopK临时UB，不满足库API真实需求；通过GetTopKMaxMinTmpSize取得tmpUbSize并同时用于预算和分配。
- 错误行为：临时区按20*S2align估计
- 修复机制：GetTopKMaxMinTmpSize 获取所需tmpUbSize，同时扣除容量和按该值分配
- 原模式关系：M015；临时UB预算估算不足，不据此认定发生踩踏或精度错误。
- 触发前提：W_api_topk(S2,topK,dtype)>W_old_estimate(20*S2align)，并影响实际UB规划/分配
- 待证：合法API到S2align/topK的推导、字节单位及容量两侧输入
- 测试设计：DESIGN-NSA-TOPK-TMPUB（未执行）。

- [https://gitcode.com/cann/ops-transformer/blob/45600336cf2736eb677b4d12e0e75e2dee42c778/attention/nsa_compress_attention/op_host/nsa_compress_attention_tiling_general.cpp](https://gitcode.com/cann/ops-transformer/blob/45600336cf2736eb677b4d12e0e75e2dee42c778/attention/nsa_compress_attention/op_host/nsa_compress_attention_tiling_general.cpp)；文件 `attention/nsa_compress_attention/op_host/nsa_compress_attention_tiling_general.cpp`；定位 `775–787`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: 经验临时容量
after:  GetTopKMaxMinTmpSize(...); tmpUbSize
```
- [https://gitcode.com/cann/ops-transformer/blob/45600336cf2736eb677b4d12e0e75e2dee42c778/attention/nsa_compress_attention/op_kernel/nsa_compress_attention_s1s2_bn2gs1_sab.h](https://gitcode.com/cann/ops-transformer/blob/45600336cf2736eb677b4d12e0e75e2dee42c778/attention/nsa_compress_attention/op_kernel/nsa_compress_attention_s1s2_bn2gs1_sab.h)；文件 `attention/nsa_compress_attention/op_kernel/nsa_compress_attention_s1s2_bn2gs1_sab.h`；定位 `816–836`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: 20*S2align
after:  使用实际 tmpUbSize 预算及分配
```
- [https://gitcode.com/cann/ops-transformer/blob/5c0fd9b4125461ca9ef07d5677416f12e5778d80/attention/nsa_compress_attention/op_host/nsa_compress_attention_tiling_general.cpp](https://gitcode.com/cann/ops-transformer/blob/5c0fd9b4125461ca9ef07d5677416f12e5778d80/attention/nsa_compress_attention/op_host/nsa_compress_attention_tiling_general.cpp)；文件 `attention/nsa_compress_attention/op_host/nsa_compress_attention_tiling_general.cpp`；定位 `775–787`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: 经验临时容量
after:  GetTopKMaxMinTmpSize(...); tmpUbSize
```
- [https://gitcode.com/cann/ops-transformer/blob/5c0fd9b4125461ca9ef07d5677416f12e5778d80/attention/nsa_compress_attention/op_kernel/nsa_compress_attention_s1s2_bn2gs1_sab.h](https://gitcode.com/cann/ops-transformer/blob/5c0fd9b4125461ca9ef07d5677416f12e5778d80/attention/nsa_compress_attention/op_kernel/nsa_compress_attention_s1s2_bn2gs1_sab.h)；文件 `attention/nsa_compress_attention/op_kernel/nsa_compress_attention_s1s2_bn2gs1_sab.h`；定位 `816–836`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: 20*S2align
after:  使用实际 tmpUbSize 预算及分配
```

### TC-SFAG-EVENT-ID

**同步事件ID未写入执行状态**

- 根因/实现缺陷：runInfo中的4个scatterTmpK/V Mte2WaitV事件ID未赋值，修复在UpdateGmOffset补齐，作者报告偶现卡死。
- 错误行为：runInfo缺少4个scatterTmpK/V的eventId赋值
- 修复机制：UpdateGmOffset补齐WaitV及Pong事件ID
- 原模式关系：M007；同步事件状态传递不同于少写屏障；卡死与精度影响分开。
- 触发前提：目标SparseFAG路径消费runInfo中四个WaitV/Pong事件ID，但旧UpdateGmOffset未完整赋值
- 待证：事件分配→runInfo赋值→wait消费链、失败输入及单独回归
- 测试设计：DESIGN-SFAG-EVENT-ID（未执行）。

- [https://gitcode.com/cann/ops-transformer/blob/8946df0285b1cddb46acf501c951e8bb04eaad11/attention/sparse_flash_attention_grad/op_kernel/arch22/sparse_flash_attention_grad_bs1_basic.h](https://gitcode.com/cann/ops-transformer/blob/8946df0285b1cddb46acf501c951e8bb04eaad11/attention/sparse_flash_attention_grad/op_kernel/arch22/sparse_flash_attention_grad_bs1_basic.h)；文件 `attention/sparse_flash_attention_grad/op_kernel/arch22/sparse_flash_attention_grad_bs1_basic.h`；定位 `888–891`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: runInfo缺4个eventId赋值
after:  补 scatterTmpKMte2WaitV/VMte2WaitV 及Pong赋值
```
- [https://gitcode.com/cann/ops-transformer/blob/416787cc74933949b6b321cfc09aab03734fec24/attention/sparse_flash_attention_grad/op_kernel/arch22/sparse_flash_attention_grad_bs1_basic.h](https://gitcode.com/cann/ops-transformer/blob/416787cc74933949b6b321cfc09aab03734fec24/attention/sparse_flash_attention_grad/op_kernel/arch22/sparse_flash_attention_grad_bs1_basic.h)；文件 `attention/sparse_flash_attention_grad/op_kernel/arch22/sparse_flash_attention_grad_bs1_basic.h`；定位 `888–891`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: runInfo缺4个eventId赋值
after:  补 scatterTmpKMte2WaitV/VMte2WaitV 及Pong赋值
```

### TC-MEGAMOE-REUSE-SPAN

**复用工作区槽宽不足覆盖未读输入**

- 根因/实现缺陷：GMM1输入宽K与SwiGLU输出宽N/2共用空间，N/2>K时输出覆盖后续未读输入；按max(K,N/2)组织行/专家槽宽。
- 错误行为：输入行/地址仍按K组织，较宽SwiGLU输出覆盖未读输入；expert之间按M*K紧排，实际复用输出更宽
- 修复机制：GMM1预处理/寻址使用max(K,N/2)，SwiGLU/GMM2仍保持原紧排语义；expert槽宽max(K,N/2)，expert内部仍K密排；另补activationClamp属性赋值
- 原模式关系：M015；复用跨度/生命周期的强扩展；A2行布局与A3专家槽分别验收，不倒灌为原FIA事件根因。
- 触发前提：GMM1输入宽K与SwiGLU输出宽N/2共用空间 && N/2>K && 存在后续未消费输入
- 待证：完整合法API/量化/路由配置、实际rank与专家分布、未读输入覆盖trace
- 测试设计：DESIGN-MEGAMOE-REUSE-SPAN（未执行）。

- [https://gitcode.com/cann/ops-transformer/blob/351e0f8a622cc24d6e4f545b47597c1c1bdb9663/mc2/mega_moe/op_kernel/arch22/mega_moe_a2.h](https://gitcode.com/cann/ops-transformer/blob/351e0f8a622cc24d6e4f545b47597c1c1bdb9663/mc2/mega_moe/op_kernel/arch22/mega_moe_a2.h)；文件 `mc2/mega_moe/op_kernel/arch22/mega_moe_a2.h`；定位 `300–304`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: stride K
after:  W4A8使用 max(K,K2)
```
- [https://gitcode.com/cann/ops-transformer/blob/508baa1d9ad00c51287cc561fbf76b2bf0a2aec1/mc2/mega_moe/op_kernel/arch22/mega_moe_kernel_a3.hpp](https://gitcode.com/cann/ops-transformer/blob/508baa1d9ad00c51287cc561fbf76b2bf0a2aec1/mc2/mega_moe/op_kernel/arch22/mega_moe_kernel_a3.hpp)；文件 `mc2/mega_moe/op_kernel/arch22/mega_moe_kernel_a3.hpp`；定位 `130–134/211–212/725`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: gmGroupOffsetA += M*K
after:  gmm1InputExpertSlotWidth=max(K,N/2); gmGroupOffsetA += M*slotWidth
```

### TC-LI-DUPLICATE-SPACE

**向量Duplicate访问空间未充分预留**

- 根因/实现缺陷：Duplicate向量填充需要额外256字节访问空间；缓冲区未充分预留，修复加DUPSIZE，同时修改mask数组和尾部偏移。
- 错误行为：向量Duplicate填充所需额外空间不足；mask及尾部偏移配置亦有改动
- 修复机制：DUPSIZE=256，缓冲区加该字节空间；mask[1]→mask[2]，尾部uint16偏移64→128
- 原模式关系：M015；指令足迹与M015相关，但mask、偏移、空间三项贡献未隔离。
- 触发前提：目标Duplicate访问范围含额外DUPSIZE=256字节，旧临时区未充分预留；尾部mask/偏移需分别检查
- 待证：合法API到topkCountAlign256的推导、实际访问区间；三处改动贡献隔离
- 测试设计：DESIGN-LI-DUPLICATE-SPACE（未执行）。

- [https://gitcode.com/cann/ops-transformer/blob/48bcf8a97d2c4afd974d3709ac60503001208a3c/attention/lightning_indexer/op_kernel/arch35/lightning_indexer_service_vector.h](https://gitcode.com/cann/ops-transformer/blob/48bcf8a97d2c4afd974d3709ac60503001208a3c/attention/lightning_indexer/op_kernel/arch35/lightning_indexer_service_vector.h)；文件 `attention/lightning_indexer/op_kernel/arch35/lightning_indexer_service_vector.h`；定位 `34/166/177`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: 缺少Duplicate额外空间
after:  DUPSIZE=256，缓冲区加DUPSIZE
```
- [https://gitcode.com/cann/ops-transformer/blob/48bcf8a97d2c4afd974d3709ac60503001208a3c/attention/lightning_indexer/op_kernel/arch35/lightning_indexer_service_vector.h](https://gitcode.com/cann/ops-transformer/blob/48bcf8a97d2c4afd974d3709ac60503001208a3c/attention/lightning_indexer/op_kernel/arch35/lightning_indexer_service_vector.h)；文件 `attention/lightning_indexer/op_kernel/arch35/lightning_indexer_service_vector.h`；定位 `574–585`；NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS。
```text
before: mask[1]，尾偏移+64
after:  mask[2]，尾偏移+128
```

### TC-FP8-VSCALE

**V scale前位置值误用于当前更新**

- 根因/实现缺陷：FlashUpdateNew/FlashUpdateLastNew原传deScalePreVValue，修复传当前deScaleVValue；不自行推断该位置一定是head/batch索引。
- 错误行为：deScalePreVOffset = (deScaleVOffset < 1) ? 0 : deScaleVOffset - 1; FlashUpdate(...deScaleVValue, deScalePreVValue)
- 修复机制：FlashUpdateNew / FlashUpdateLastNew(...deScaleVValue, deScaleVValue)
- 原模式关系：['M010', 'M024']；错误scale对象不同于图Dequantize位置或物理排布；完整对象语义待补。
- 触发前提：目标FP8 GQA更新应使用deScaleVValue，但旧代码传deScalePreVValue；对象完整语义待补
- 待证：scale完整轴语义、合法不同scale值的输入、旧新数值和路径对照
- 测试设计：DESIGN-FP8-VSCALE（未执行）。

- [https://gitcode.com/cann/ops-transformer/blob/f4f1bafc2ffefc94306e0ea6403ff362e5259331/attention/common/op_kernel/arch35/fia_block_vec_fullquant_gqa.h](https://gitcode.com/cann/ops-transformer/blob/f4f1bafc2ffefc94306e0ea6403ff362e5259331/attention/common/op_kernel/arch35/fia_block_vec_fullquant_gqa.h)；文件 `attention/common/op_kernel/arch35/fia_block_vec_fullquant_gqa.h`；定位 `589–612`；SELECTED_SOURCE_OBSERVATION_WITH_EXACT_TOKENS。
```text
before: deScalePreVOffset = (deScaleVOffset < 1) ? 0 : deScaleVOffset - 1; FlashUpdate(...deScaleVValue, deScalePreVValue)
after:  FlashUpdateNew / FlashUpdateLastNew(...deScaleVValue, deScaleVValue)
```

### TC-DEQUANT-REDUCE-STRIDE

**归约重复步长计算过早整数截断**

- 根因/实现缺陷：向量归约重复步长计算过早整数截断：BLOCK_ELEM=8、MASK_NUM_T32=64、MASK_BLK_STRIDE=8，旧式(q//64)*8改为q//8；差值为(q%64)//8。实际q=UbFactorDimy尚未取得，错误间距不必越界。
- 错误行为：在真实UbFactorDimy使两式不等时，旧重复间距可能选错数据；不能由输入[2,192]直接断言q=96，也未证明越界或独立历史事故。
- 修复机制：srcRepStride = UbFactorDimy / BLOCK_ELEM
- 原模式关系：M004；过早整数截断导致重复间距模型错误；可能合法区间内错读，不等同M004越界踩踏。
- 触发前提：命中目标WholeReduceMax重复行路径 && (q%64)//8>0；q须取实际UbFactorDimy
- 待证：真实tiling q及访问区间；单独回退步长修改的旧新结果；错误访问未必越界
- 测试设计：DESIGN-DEQUANT-UPSTREAM（未执行）。

- [https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_kernel/dequant_swiglu_quant.h](https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_kernel/dequant_swiglu_quant.h)；文件 `csrc/moe/dequant_swiglu_quant/op_kernel/dequant_swiglu_quant.h`；定位 `/patches/1/patch`；SELECTED_SOURCE_OBSERVATION_WITH_EXACT_TOKENS。
- [https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_kernel/dequant_swiglu_quant.h](https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_kernel/dequant_swiglu_quant.h)；文件 `csrc/moe/dequant_swiglu_quant/op_kernel/dequant_swiglu_quant.h`；定位 `选定变更`；SELECTED_SOURCE_OBSERVATION_WITH_EXACT_TOKENS。

### TC-DEQUANT-SCALE-BUFFER

**scale广播临时区独立分配及预算**

- 根因/实现缺陷：为scale广播建立scaleBuf_/brcbTmp，替代把outLocal兼作广播临时区，并在host UB预算扣除所需空间。
- 错误行为：Brcb(outLocal, scaleOut,...); Copy(...outLocal...)
- 修复机制：分配scaleBuf_/brcbTmp；Brcb与Copy使用brcbTmp；释放临时tensor并计入host UB预算
- 原模式关系：M015；保留共变更临时区线索，独立故障因果未闭合。
- 触发前提：DynamicQuant执行Brcb/Copy；旧outLocal复用区域的容量/类型/生命周期不满足临时需求（独立因果待验证）
- 待证：原outLocal容量/类型和Brcb足迹、真实UB分配；与步长修复的独立贡献
- 测试设计：DESIGN-DEQUANT-UPSTREAM（未执行）。

- [https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_host/dequant_swiglu_quant_tiling.cpp](https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_host/dequant_swiglu_quant_tiling.cpp)；文件 `csrc/moe/dequant_swiglu_quant/op_host/dequant_swiglu_quant_tiling.cpp`；定位 `/patches/0/patch`；SELECTED_SOURCE_OBSERVATION_WITH_EXACT_TOKENS。
- [https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_kernel/dequant_swiglu_quant.h](https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_kernel/dequant_swiglu_quant.h)；文件 `csrc/moe/dequant_swiglu_quant/op_kernel/dequant_swiglu_quant.h`；定位 `/patches/1/patch`；SELECTED_SOURCE_OBSERVATION_WITH_EXACT_TOKENS。

## 两处精确源码纠错

Gather原diff旧语句为`ge::GetSizeByDataType(index->GetDataType())`，不是C++枚举变量sizeof。按Tensor元素字节数建立旧谓词模型有据；INT64合法性和真实mode日志仍待现场。见[evidence/gather_1562_diff.json](evidence/gather_1562_diff.json)。
dequant固定版本常量为BLOCK_SIZE=32、BLOCK_ELEM=8、MASK_NUM_T32=64、MASK_BLK_STRIDE=8；旧(q//64)*8与新q//8差为(q%64)//8。实际UbFactorDimy未取得，不能把派生输出96直接代入；错误间距不必越界。见[常量](evidence/dequant_constants.json)和[三文件patch](evidence/github_12123_patch.json)。

## 验证边界

私有来源工作区已运行57项Python检查及33项离线JavaScript检查，摘要和来源产物哈希保留在[source_review_receipt.json](validation/source_review_receipt.json)。该回执不是公开包可重跑的私有Init测试。
本包另有可独立重跑的发布检查、单元测试和离线交互检查，结果见[publication_validation.json](validation/publication_validation.json)。浏览器布局、设备内核、现场OpenCode和生产续跑均未在本次发布中验收。
