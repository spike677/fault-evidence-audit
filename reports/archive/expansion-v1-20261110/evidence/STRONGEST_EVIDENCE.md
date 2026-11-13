# 每条技术案例的最强相关证据

最强指对当前代码级主张的贴近程度，不代表同客户事件或DIRECT/正式入库。
19个主证据入口、32条变更观察及4份先前定向API/测试上下文。它们不是相互独立的19/32/4起故障；GH12123两个子问题共享修复和测试，独立贡献未隔离。

[完整HTML](../CANN_EXPANSION_FULL_RESULTS.html) · [结构化索引](strongest_evidence.json) · [32条观察](observations.json) · [4份补充上下文](pinned_support_contexts.json)

## TC-GEMM-PRECISION-FLAG

**beta=0分支遗漏16入32出精度标记**

- 主证据：[https://gitcode.com/cann/ops-nn/blob/36adda8717a669bd39d197c69e6b63130c6d2831/matmul/batch_mat_mul_v3/op_host/op_api/aclnn_baddbmm.cpp](https://gitcode.com/cann/ops-nn/blob/36adda8717a669bd39d197c69e6b63130c6d2831/matmul/batch_mat_mul_v3/op_host/op_api/aclnn_baddbmm.cpp)
- 固定版本：[https://gitcode.com/cann/ops-nn/blob/36adda8717a669bd39d197c69e6b63130c6d2831/matmul/batch_mat_mul_v3/op_host/op_api/aclnn_baddbmm.cpp](https://gitcode.com/cann/ops-nn/blob/36adda8717a669bd39d197c69e6b63130c6d2831/matmul/batch_mat_mul_v3/op_host/op_api/aclnn_baddbmm.cpp)
- 定位：`matmul/batch_mat_mul_v3/op_host/op_api/aclnn_baddbmm.cpp` · `319–322` · NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS
- 支持的主张：addmm/baddbmm的beta=0分支未把NeedEnableFp32Output结果传入ExecGemmV3WithAlphaBetaOp，导致计算精度请求未沿该分支生效。
- 不证明：NeedEnableFp32Output的完整支持条件、输入输出dtype、旧新参考误差；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "ExecGemmV3WithAlphaBetaOp(...executor)",
  "after": "NeedEnableFp32Output(...); ExecGemmV3WithAlphaBetaOp(..., enableGemm16In32Out)"
}
```

## TC-MEGAMOE-REUSE-SPAN

**复用工作区槽宽不足覆盖未读输入**

- 主证据：[https://gitcode.com/cann/ops-transformer/blob/351e0f8a622cc24d6e4f545b47597c1c1bdb9663/mc2/mega_moe/op_kernel/arch22/mega_moe_a2.h](https://gitcode.com/cann/ops-transformer/blob/351e0f8a622cc24d6e4f545b47597c1c1bdb9663/mc2/mega_moe/op_kernel/arch22/mega_moe_a2.h)
- 固定版本：[https://gitcode.com/cann/ops-transformer/blob/351e0f8a622cc24d6e4f545b47597c1c1bdb9663/mc2/mega_moe/op_kernel/arch22/mega_moe_a2.h](https://gitcode.com/cann/ops-transformer/blob/351e0f8a622cc24d6e4f545b47597c1c1bdb9663/mc2/mega_moe/op_kernel/arch22/mega_moe_a2.h)
- 定位：`mc2/mega_moe/op_kernel/arch22/mega_moe_a2.h` · `300–304` · NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS
- 支持的主张：GMM1输入宽K与SwiGLU输出宽N/2共用空间，N/2>K时输出覆盖后续未读输入；按max(K,N/2)组织行/专家槽宽。
- 不证明：完整合法API/量化/路由配置、实际rank与专家分布、未读输入覆盖trace；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "stride K",
  "after": "W4A8使用 max(K,K2)"
}
```

## TC-GRADPROBS-DTYPE

**梯度输出dtype取错输入对象**

- 主证据：[https://gitcode.com/Ascend/op-plugin/blob/253d85bab82c94d6701542b45134cbb33d33690d/op_plugin/python/meta/_meta_registrations.py](https://gitcode.com/Ascend/op-plugin/blob/253d85bab82c94d6701542b45134cbb33d33690d/op_plugin/python/meta/_meta_registrations.py)
- 固定版本：[https://gitcode.com/Ascend/op-plugin/blob/253d85bab82c94d6701542b45134cbb33d33690d/op_plugin/python/meta/_meta_registrations.py](https://gitcode.com/Ascend/op-plugin/blob/253d85bab82c94d6701542b45134cbb33d33690d/op_plugin/python/meta/_meta_registrations.py)
- 定位：`op_plugin/python/meta/_meta_registrations.py` · `5992` · NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS
- 支持的主张：grad_probs应继承probs类型，却使用grad_unpermuted_tokens类型；混合类型下返回契约错误，meta和实际输出分配同时修正。
- 不证明：现场直接返回值/Meta运行；是否纳入CANN精度库的接口层范围；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "torch.empty_like(probs, dtype=grad_unpermuted_tokens.dtype)",
  "after": "torch.empty_like(probs)"
}
```
- 补充上下文：[CAT-TEST-GRAD-DEVICE](https://gitcode.com/Ascend/op-plugin/blob/253d85bab82c94d6701542b45134cbb33d33690d/test/test_custom_ops/test_npu_moe_token_permute_and_unpermute_backward.py)；选定mixed dtype及None回归测试；220–263。
  - TestNpuFusedPermuteAndUnpermute.test_unpermute_grad_mixed_dtype
  - num_tokens=1024; hidden_size=6144; topk=4; num_experts=8; token_dtype=BF16; probs_dtype=FP32
  - npu_moe_token_unpermute(permuted_tokens, sorted_indices, probs=probs)，ones_like输出作反向梯度。
  - 检查tokens.grad与probs.grad dtype。
- 补充上下文：[CAT-TEST-GRAD-META](https://gitcode.com/Ascend/op-plugin/blob/253d85bab82c94d6701542b45134cbb33d33690d/test/core_tests/test_fake_tensor.py)；直接反向Meta输出契约测试；4102–4129;4131–4156。
  - FakeTensorMode中num_tokens=100, hidden_size=64, num_experts=8, topk=4。
  - permuted_tokens, sorted_indices = torch_npu.npu_moe_token_permute(tokens, indices)
  - torch_npu.npu_moe_token_unpermute_grad(permuted_tokens=..., grad_unpermuted_tokens=..., sorted_indices=..., probs=..., padded_mode=False, restore_shape=None)
  - 直接断言grad_probs dtype和shape等于probs，避免仅看leaf .grad被自动转换后掩盖返回类型。

## TC-GATHER-SCALAR-COUNT

**索引元素计数混入字节倍数导致Gather模式误选**

- 主证据：[https://gitcode.com/cann/ops-nn/pull/1562/diffs](https://gitcode.com/cann/ops-nn/pull/1562/diffs)
- 固定版本：[https://gitcode.com/cann/ops-nn/blob/f1359e5fbab5971b2aeeda58e2fdc5ec8e92fab0/index/gather_v2/op_api/aclnn_gather_v3.cpp](https://gitcode.com/cann/ops-nn/blob/f1359e5fbab5971b2aeeda58e2fdc5ec8e92fab0/index/gather_v2/op_api/aclnn_gather_v3.cpp)
- 定位：`index/gather_v2/op_api/aclnn_gather_v3.cpp` · `204` · EXACT_OBSERVED_DIFF_LINES
- 支持的主张：indexSize原由ge::GetSizeByDataType(index->GetDataType())初始化，再乘索引各维，误把带元素字节倍数的计数与1536元素阈值比较；修复从1计算numel。只证明模式判定缺陷，数值影响未证实。
- 不证明：目标环境的index类型合法性、实际mode消费日志；INT64需单独核对接口类型契约；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "auto indexSize = ge::GetSizeByDataType(index->GetDataType());",
  "after": "auto indexSize = 1;"
}
```
- 补充上下文：[CAT-API-GATHER](https://gitcode.com/cann/ops-nn/blob/f1359e5fbab5971b2aeeda58e2fdc5ec8e92fab0/index/gather_v2/op_api/aclnn_gather_v3.cpp)；完整计数循环、模式阈值及公开入口/消费端的定向上下文；不声称完整PR核验；CheckParams及aclnnGatherV3GetWorkspaceSize。
  - HIGH_PRECISION=0; HIGH_PERFORMANCE=1; MIN_SELF_SIZE=102400; MIN_INDEX_SIZE=48*32。
  - CheckParams(..., int64_t& mode, ...)可修改调用处mode。
  - xsize=self元素字节数*product(self shape); indexSize=1; for(each index axis) indexSize*=dim;
  - if (xsize < MIN_SELF_SIZE || indexSize < MIN_INDEX_SIZE) mode=HIGH_PRECISION;
  - non-Regbase入口要求dim=0,batchDims=0,mode=1；其后mode可被上述条件改写。
  - aclnnGatherV3GetWorkspaceSize(self,dim,index,batchDims,mode,out,workspaceSize,executor)
  - non-Regbase执行GatherV2WithImplMode(...mode...)；Regbase路径使用GatherV2，不能据输入阈值假定命中同一模式。

## TC-DEQUANT-REDUCE-STRIDE

**归约重复步长计算过早整数截断**

- 主证据：[https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_kernel/dequant_swiglu_quant.h](https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_kernel/dequant_swiglu_quant.h)
- 固定版本：[https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_kernel/dequant_swiglu_quant.h](https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_kernel/dequant_swiglu_quant.h)
- 定位：`csrc/moe/dequant_swiglu_quant/op_kernel/dequant_swiglu_quant.h` · `/patches/1/patch` · SELECTED_SOURCE_OBSERVATION_WITH_EXACT_TOKENS
- 支持的主张：向量归约重复步长计算过早整数截断：BLOCK_ELEM=8、MASK_NUM_T32=64、MASK_BLK_STRIDE=8，旧式(q//64)*8改为q//8；差值为(q%64)//8。实际q=UbFactorDimy尚未取得，错误间距不必越界。
- 不证明：真实tiling q及访问区间；单独回退步长修改的旧新结果；错误访问未必越界；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "selected_patch_lines": [
    "     // repeatTimes:proDimsx, dstRepStride:1(dtype), srcBlkStride:1, srcRepStride:tl_->UbFactorDimy / 64 * 8",
    "     WholeReduceMax(",
    "-        tmpUbF32Gate, tmpUbF32Gate, MASK_NUM_T32, proDimsx, 1, 1, tl_->UbFactorDimy / MASK_NUM_T32 * MASK_BLK_STRIDE,",
    "+        tmpUbF32Gate, tmpUbF32Gate, MASK_NUM_T32, proDimsx, 1, 1, tl_->UbFactorDimy / BLOCK_ELEM,",
    "         {1, 0, static_cast<uint16_t>(tl_->UbFactorDimy / BLOCK_ELEM), 1});"
  ]
}
```

## TC-DEQUANT-SCALE-BUFFER

**scale广播临时区独立分配及预算**

- 主证据：[https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_host/dequant_swiglu_quant_tiling.cpp](https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_host/dequant_swiglu_quant_tiling.cpp)
- 固定版本：[https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_host/dequant_swiglu_quant_tiling.cpp](https://github.com/vllm-project/vllm-ascend/blob/70b9edfb452cb50ab01ab1bf206cf316ec477824/csrc/moe/dequant_swiglu_quant/op_host/dequant_swiglu_quant_tiling.cpp)
- 定位：`csrc/moe/dequant_swiglu_quant/op_host/dequant_swiglu_quant_tiling.cpp` · `/patches/0/patch` · SELECTED_SOURCE_OBSERVATION_WITH_EXACT_TOKENS
- 支持的主张：为scale广播建立scaleBuf_/brcbTmp，替代把outLocal兼作广播临时区，并在host UB预算扣除所需空间。
- 不证明：原outLocal容量/类型和Brcb足迹、真实UB分配；与步长修复的独立贡献；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "selected_patch_lines": [
    "-  int64_t numerator = static_cast<int64_t>(ubSize_) - UB_RESERVE - BLOCK_SIZE - db * BLOCK_SIZE - static_cast<int64_t>(sizeof(float));",
    "+  int64_t numerator = static_cast<int64_t>(ubSize_) - UB_RESERVE - BLOCK_SIZE - db * BLOCK_SIZE - static_cast<int64_t>(sizeof(float)) -",
    "+                       BLOCK_ELEM * BLOCK_ELEM * static_cast<int64_t>(sizeof(float));",
    "   numerator = static_cast<int64_t>(ubSize_) - UB_RESERVE - outDimy_ * static_cast<int64_t>(sizeof(float)) - BLOCK_SIZE - SWI_FACTOR * outDimy_ * static_cast<int64_t>(sizeof(float)) - biasBufferX - quantOffsetSpace;",
    "+                BLOCK_ELEM * static_cast<int64_t>(sizeof(float));"
  ]
}
```

## TC-BOOL-REDUCE

**BOOL输出选错归约算法**

- 主证据：[https://gitcode.com/cann/ops-math/blob/adbf5a82f418507f1baf4e32020718571d9b5309/math/reduce_prod/op_api/aclnn_prod.cpp](https://gitcode.com/cann/ops-math/blob/adbf5a82f418507f1baf4e32020718571d9b5309/math/reduce_prod/op_api/aclnn_prod.cpp)
- 固定版本：[https://gitcode.com/cann/ops-math/blob/adbf5a82f418507f1baf4e32020718571d9b5309/math/reduce_prod/op_api/aclnn_prod.cpp](https://gitcode.com/cann/ops-math/blob/adbf5a82f418507f1baf4e32020718571d9b5309/math/reduce_prod/op_api/aclnn_prod.cpp)
- 定位：`math/reduce_prod/op_api/aclnn_prod.cpp` · `187–193` · NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS
- 支持的主张：910B/910_93且out BOOL时原走数值ReduceProd，改向ExecuteProd传dimList并使用ReduceAll逻辑归约。
- 不证明：历史失败输入、旧新输出、转换链；区分下溢与独立BOOL契约问题；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "ReduceProd(selfCast, axes,...)",
  "after": "dimList != nullptr 时 ReduceAll(selfCast, dimList,...)"
}
```
- 补充上下文：[CAT-API-BOOL](https://gitcode.com/cann/ops-math/blob/adbf5a82f418507f1baf4e32020718571d9b5309/math/reduce_prod/op_api/aclnn_prod.cpp)；选定类型检查、转换和公开API签名，非全仓库核验；35–68;149–195;208–237;251–258;303–311。
  - 输入支持列表含FLOAT；out dtype必须与显式dtype参数相同。
  - aclnnProdDimGetWorkspaceSize(self, dim, keepDim, dtype, out, workspaceSize, executor)
  - aclnnProdGetWorkspaceSize(self, dtype, out, workspaceSize, executor)
  - aclnnProd(workspace, workspaceSize, executor, stream)
  - ExecuteProd先Contiguous；non-Regbase BOOL输出路径先Cast FLOAT，dimList非空时执行ReduceAll。

## TC-RADIX-SYNC

**RadixTopK搬运/计算依赖缺同步**

- 主证据：[https://gitcode.com/cann/ops-math/blob/2486e024c457afbc49dbc266d418be71eaadfce1/math/radix_top_k/op_kernel/radix_top_k_ub.h](https://gitcode.com/cann/ops-math/blob/2486e024c457afbc49dbc266d418be71eaadfce1/math/radix_top_k/op_kernel/radix_top_k_ub.h)
- 固定版本：[https://gitcode.com/cann/ops-math/blob/2486e024c457afbc49dbc266d418be71eaadfce1/math/radix_top_k/op_kernel/radix_top_k_ub.h](https://gitcode.com/cann/ops-math/blob/2486e024c457afbc49dbc266d418be71eaadfce1/math/radix_top_k/op_kernel/radix_top_k_ub.h)
- 定位：`math/radix_top_k/op_kernel/radix_top_k_ub.h` · `200/297/377` · NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS
- 支持的主张：批处理TopK的核间及搬运/计算依赖缺同步，增加SyncAll及SToV等同步。
- 不证明：失败shape/k/dtype、实际参与核和依赖trace；单独回退同步修复；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "缺少所示同步",
  "after": "SyncAll / SToV"
}
```

## TC-FIA-M-PIPE

**矩阵计算段之间缺PIPE_M屏障**

- 主证据：[https://gitcode.com/cann/ops-transformer/pull/12716/diffs](https://gitcode.com/cann/ops-transformer/pull/12716/diffs)
- 固定版本：[https://gitcode.com/cann/ops-transformer/blob/e7396160f89d8338af2c45bdd090dc50b5bad4db/attention/incre_flash_attention/op_kernel/arch22/ifa_service_matmul_full_quant.h](https://gitcode.com/cann/ops-transformer/blob/e7396160f89d8338af2c45bdd090dc50b5bad4db/attention/incre_flash_attention/op_kernel/arch22/ifa_service_matmul_full_quant.h)
- 定位：`attention/incre_flash_attention/op_kernel/arch22/ifa_service_matmul_full_quant.h` · `907` · SELECTED_SOURCE_OBSERVATION_WITH_EXACT_TOKENS
- 支持的主张：ComputeMm1的相邻Mmad计算段之间缺少矩阵流水完成屏障；本轮补读#12716新行907加入PipeBarrier<PIPE_M>()。
- 不证明：合法API到目标模板的选择谓词、实际依赖trace、单独回退实验；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "blank line",
  "after": "PipeBarrier<PIPE_M>();"
}
```

## TC-GMM-K0

**Split-K空归约维度处理不当**

- 主证据：[https://gitcode.com/cann/ops-transformer/blob/9888a6ca348359af8d03167e24483fe913354b7a/gmm/grouped_matmul/op_host/op_tiling/grouped_matmul_tiling.cpp](https://gitcode.com/cann/ops-transformer/blob/9888a6ca348359af8d03167e24483fe913354b7a/gmm/grouped_matmul/op_host/op_tiling/grouped_matmul_tiling.cpp)
- 固定版本：[https://gitcode.com/cann/ops-transformer/blob/9888a6ca348359af8d03167e24483fe913354b7a/gmm/grouped_matmul/op_host/op_tiling/grouped_matmul_tiling.cpp](https://gitcode.com/cann/ops-transformer/blob/9888a6ca348359af8d03167e24483fe913354b7a/gmm/grouped_matmul/op_host/op_tiling/grouped_matmul_tiling.cpp)
- 定位：`gmm/grouped_matmul/op_host/op_tiling/grouped_matmul_tiling.cpp` · `1387` · NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS
- 支持的主张：K=0的SPLIT_K路径仍走高阶Matmul tiling/通用空输入检查，修复按特殊空归约语义处理，代码注释说明由kernel清零。
- 不证明：完整列表/枚举契约、合法M/N及输出清零的实际结果；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "无K0跳过分支",
  "after": "groupType_ == SPLIT_K && maxK_ == 0：kernel清零，不需要高阶APItiling"
}
```

## TC-LI-DUPLICATE-SPACE

**向量Duplicate访问空间未充分预留**

- 主证据：[https://gitcode.com/cann/ops-transformer/blob/48bcf8a97d2c4afd974d3709ac60503001208a3c/attention/lightning_indexer/op_kernel/arch35/lightning_indexer_service_vector.h](https://gitcode.com/cann/ops-transformer/blob/48bcf8a97d2c4afd974d3709ac60503001208a3c/attention/lightning_indexer/op_kernel/arch35/lightning_indexer_service_vector.h)
- 固定版本：[https://gitcode.com/cann/ops-transformer/blob/48bcf8a97d2c4afd974d3709ac60503001208a3c/attention/lightning_indexer/op_kernel/arch35/lightning_indexer_service_vector.h](https://gitcode.com/cann/ops-transformer/blob/48bcf8a97d2c4afd974d3709ac60503001208a3c/attention/lightning_indexer/op_kernel/arch35/lightning_indexer_service_vector.h)
- 定位：`attention/lightning_indexer/op_kernel/arch35/lightning_indexer_service_vector.h` · `34/166/177` · NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS
- 支持的主张：Duplicate向量填充需要额外256字节访问空间；缓冲区未充分预留，修复加DUPSIZE，同时修改mask数组和尾部偏移。
- 不证明：合法API到topkCountAlign256的推导、实际访问区间；三处改动贡献隔离；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "缺少Duplicate额外空间",
  "after": "DUPSIZE=256，缓冲区加DUPSIZE"
}
```

## TC-NSA-TOPK-TMPUB

**TopK临时UB需求预算不足**

- 主证据：[https://gitcode.com/cann/ops-transformer/blob/45600336cf2736eb677b4d12e0e75e2dee42c778/attention/nsa_compress_attention/op_host/nsa_compress_attention_tiling_general.cpp](https://gitcode.com/cann/ops-transformer/blob/45600336cf2736eb677b4d12e0e75e2dee42c778/attention/nsa_compress_attention/op_host/nsa_compress_attention_tiling_general.cpp)
- 固定版本：[https://gitcode.com/cann/ops-transformer/blob/45600336cf2736eb677b4d12e0e75e2dee42c778/attention/nsa_compress_attention/op_host/nsa_compress_attention_tiling_general.cpp](https://gitcode.com/cann/ops-transformer/blob/45600336cf2736eb677b4d12e0e75e2dee42c778/attention/nsa_compress_attention/op_host/nsa_compress_attention_tiling_general.cpp)
- 定位：`attention/nsa_compress_attention/op_host/nsa_compress_attention_tiling_general.cpp` · `775–787` · NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS
- 支持的主张：以20*S2align估算TopK临时UB，不满足库API真实需求；通过GetTopKMaxMinTmpSize取得tmpUbSize并同时用于预算和分配。
- 不证明：合法API到S2align/topK的推导、字节单位及容量两侧输入；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "经验临时容量",
  "after": "GetTopKMaxMinTmpSize(...); tmpUbSize"
}
```

## TC-RADIX-API-WORKSPACE

**RadixTopK未计入库API workspace**

- 主证据：[https://gitcode.com/cann/ops-math/blob/2486e024c457afbc49dbc266d418be71eaadfce1/math/radix_top_k/op_host/radix_top_k_tiling.cpp](https://gitcode.com/cann/ops-math/blob/2486e024c457afbc49dbc266d418be71eaadfce1/math/radix_top_k/op_host/radix_top_k_tiling.cpp)
- 固定版本：[https://gitcode.com/cann/ops-math/blob/2486e024c457afbc49dbc266d418be71eaadfce1/math/radix_top_k/op_host/radix_top_k_tiling.cpp](https://gitcode.com/cann/ops-math/blob/2486e024c457afbc49dbc266d418be71eaadfce1/math/radix_top_k/op_host/radix_top_k_tiling.cpp)
- 定位：`math/radix_top_k/op_host/radix_top_k_tiling.cpp` · `150–152` · NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS
- 支持的主张：workspace总量未加AscendC库API所需空间，修复通过GetLibApiWorkSpaceSize计入分配。
- 不证明：W_api/W_kernel对应的合法输入、实际分配及访问区间；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "workspace 未加 API 需求",
  "after": "GetLibApiWorkSpaceSize + workspaceSize"
}
```

## TC-SFAG-EVENT-ID

**同步事件ID未写入执行状态**

- 主证据：[https://gitcode.com/cann/ops-transformer/blob/8946df0285b1cddb46acf501c951e8bb04eaad11/attention/sparse_flash_attention_grad/op_kernel/arch22/sparse_flash_attention_grad_bs1_basic.h](https://gitcode.com/cann/ops-transformer/blob/8946df0285b1cddb46acf501c951e8bb04eaad11/attention/sparse_flash_attention_grad/op_kernel/arch22/sparse_flash_attention_grad_bs1_basic.h)
- 固定版本：[https://gitcode.com/cann/ops-transformer/blob/8946df0285b1cddb46acf501c951e8bb04eaad11/attention/sparse_flash_attention_grad/op_kernel/arch22/sparse_flash_attention_grad_bs1_basic.h](https://gitcode.com/cann/ops-transformer/blob/8946df0285b1cddb46acf501c951e8bb04eaad11/attention/sparse_flash_attention_grad/op_kernel/arch22/sparse_flash_attention_grad_bs1_basic.h)
- 定位：`attention/sparse_flash_attention_grad/op_kernel/arch22/sparse_flash_attention_grad_bs1_basic.h` · `888–891` · NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS
- 支持的主张：runInfo中的4个scatterTmpK/V Mte2WaitV事件ID未赋值，修复在UpdateGmOffset补齐，作者报告偶现卡死。
- 不证明：事件分配→runInfo赋值→wait消费链、失败输入及单独回归；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "runInfo缺4个eventId赋值",
  "after": "补 scatterTmpKMte2WaitV/VMte2WaitV 及Pong赋值"
}
```

## TC-FP8-VSCALE

**V scale前位置值误用于当前更新**

- 主证据：[https://gitcode.com/cann/ops-transformer/blob/f4f1bafc2ffefc94306e0ea6403ff362e5259331/attention/common/op_kernel/arch35/fia_block_vec_fullquant_gqa.h](https://gitcode.com/cann/ops-transformer/blob/f4f1bafc2ffefc94306e0ea6403ff362e5259331/attention/common/op_kernel/arch35/fia_block_vec_fullquant_gqa.h)
- 固定版本：[https://gitcode.com/cann/ops-transformer/blob/f4f1bafc2ffefc94306e0ea6403ff362e5259331/attention/common/op_kernel/arch35/fia_block_vec_fullquant_gqa.h](https://gitcode.com/cann/ops-transformer/blob/f4f1bafc2ffefc94306e0ea6403ff362e5259331/attention/common/op_kernel/arch35/fia_block_vec_fullquant_gqa.h)
- 定位：`attention/common/op_kernel/arch35/fia_block_vec_fullquant_gqa.h` · `589–612` · SELECTED_SOURCE_OBSERVATION_WITH_EXACT_TOKENS
- 支持的主张：FlashUpdateNew/FlashUpdateLastNew原传deScalePreVValue，修复传当前deScaleVValue；不自行推断该位置一定是head/batch索引。
- 不证明：scale完整轴语义、合法不同scale值的输入、旧新数值和路径对照；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "deScalePreVOffset = (deScaleVOffset < 1) ? 0 : deScaleVOffset - 1; FlashUpdate(...deScaleVValue, deScalePreVValue)",
  "after": "FlashUpdateNew / FlashUpdateLastNew(...deScaleVValue, deScaleVValue)"
}
```

## TC-REPEAT-INT32-ROUTE

**超大单轴漏掉安全实现选路**

- 主证据：[https://gitcode.com/cann/ops-nn/blob/16c16335573d6086dbe7524ecb80e5c605692413/index/repeat_interleave/op_api/repeat_interleave.cpp](https://gitcode.com/cann/ops-nn/blob/16c16335573d6086dbe7524ecb80e5c605692413/index/repeat_interleave/op_api/repeat_interleave.cpp)
- 固定版本：[https://gitcode.com/cann/ops-nn/blob/16c16335573d6086dbe7524ecb80e5c605692413/index/repeat_interleave/op_api/repeat_interleave.cpp](https://gitcode.com/cann/ops-nn/blob/16c16335573d6086dbe7524ecb80e5c605692413/index/repeat_interleave/op_api/repeat_interleave.cpp)
- 定位：`index/repeat_interleave/op_api/repeat_interleave.cpp` · `49–57` · NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS
- 支持的主张：view shape某轴超过INT32_MAX且dtype受支持时需要选择V2；原分派遗漏该边界约束。
- 不证明：实际大tensor资源、旧新路径；内部窄整数地址公式尚无；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "未见该大shape判定",
  "after": "xViewShape[i] > INT32_MAX_NUM && CheckType(...) => true"
}
```

## TC-MATMUL-DISPATCH-DTYPE

**二进制分派检查使用转换前类型**

- 主证据：[https://gitcode.com/cann/ops-nn/blob/e7ad2aa953c5b4d5d9e1262680e1045cabbff4e4/matmul/common/op_host/op_api/matmul_util.cpp](https://gitcode.com/cann/ops-nn/blob/e7ad2aa953c5b4d5d9e1262680e1045cabbff4e4/matmul/common/op_host/op_api/matmul_util.cpp)
- 固定版本：[https://gitcode.com/cann/ops-nn/blob/e7ad2aa953c5b4d5d9e1262680e1045cabbff4e4/matmul/common/op_host/op_api/matmul_util.cpp](https://gitcode.com/cann/ops-nn/blob/e7ad2aa953c5b4d5d9e1262680e1045cabbff4e4/matmul/common/op_host/op_api/matmul_util.cpp)
- 定位：`matmul/common/op_host/op_api/matmul_util.cpp` · `120` · NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS
- 支持的主张：MatMul支持性检查使用ori_info类型，实际执行类型已转换；改用support_info，避免找不到MatMulV3二进制。
- 不证明：合法shape/格式、目标平台及实际二进制匹配记录；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "ori_info.self/bias dtype",
  "after": "support_info.self/bias dtype"
}
```

## TC-FAG-MTE2-DIM

**搬运尺寸取错矩阵维度**

- 主证据：[https://gitcode.com/cann/ops-transformer/blob/f277be164030f3dd68cb041b2ab3f2b83e62d1d1/attention/flash_attention_score_grad/op_kernel/arch32/flash_attention_score_grad_s1s2_bn2.h](https://gitcode.com/cann/ops-transformer/blob/f277be164030f3dd68cb041b2ab3f2b83e62d1d1/attention/flash_attention_score_grad/op_kernel/arch32/flash_attention_score_grad_s1s2_bn2.h)
- 固定版本：[https://gitcode.com/cann/ops-transformer/blob/f277be164030f3dd68cb041b2ab3f2b83e62d1d1/attention/flash_attention_score_grad/op_kernel/arch32/flash_attention_score_grad_s1s2_bn2.h](https://gitcode.com/cann/ops-transformer/blob/f277be164030f3dd68cb041b2ab3f2b83e62d1d1/attention/flash_attention_score_grad/op_kernel/arch32/flash_attention_score_grad_s1s2_bn2.h)
- 定位：`attention/flash_attention_score_grad/op_kernel/arch32/flash_attention_score_grad_s1s2_bn2.h` · `1681/1683/2007/2009` · NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS
- 支持的主张：FAG bn2 MM12的四处MTE2配置用mm1BaseK而非dimD，造成搬运范围与实际维度不符。
- 不证明：外部headDim/shape到内部维度的关系、合法路径、真实搬运区间；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "mm1BaseK",
  "after": "dimD"
}
```

## TC-PLUGIN-ASYNC

**调频plugin异步资源生命周期不一致**

- 主证据：[https://gitcode.com/Ascend/MindIE-SD/blob/f4537472b5a9ffefb47f5c10b8b8c05843c4b92a/csrc/plugin/frequency_regulator.cpp](https://gitcode.com/Ascend/MindIE-SD/blob/f4537472b5a9ffefb47f5c10b8b8c05843c4b92a/csrc/plugin/frequency_regulator.cpp)
- 固定版本：[https://gitcode.com/Ascend/MindIE-SD/blob/f4537472b5a9ffefb47f5c10b8b8c05843c4b92a/csrc/plugin/frequency_regulator.cpp](https://gitcode.com/Ascend/MindIE-SD/blob/f4537472b5a9ffefb47f5c10b8b8c05843c4b92a/csrc/plugin/frequency_regulator.cpp)
- 定位：`csrc/plugin/frequency_regulator.cpp` · `实现替换段` · NORMALIZED_OBSERVATION_WITH_SELECTED_EXACT_TOKENS
- 支持的主张：手工管理的workspace/executor/ACL tensor生命周期与框架异步执行不一致，改由EXEC_NPU_CMD管理。
- 不证明：没有证明为CANN数值kernel缺陷；工程案例与精度模式范围分开；没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。
```json
{
  "before": "手工 ACL executor/workspace 管理",
  "after": "EXEC_NPU_CMD"
}
```
