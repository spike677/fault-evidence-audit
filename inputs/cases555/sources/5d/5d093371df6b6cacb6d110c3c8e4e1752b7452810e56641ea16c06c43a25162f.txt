/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

/*!
 * \file stateless_normal.h
 * \brief StatelessNormal V4 SIMT kernel implementation
 *        Uses common PhiloxSimtKernelDiscontinuous + ProcessWithSplitBlocks templates.
 *        Strict GPU parity: Philox4x32-10 + Box-Muller, same seed+offset → same output.
 *        L2 layer broadcasts Size=1 mean/stdev to output shape, so kernel only needs BothTensor path.
 *        mean/stdev are always DT_FLOAT (float*) regardless of output dtype T.
 *        For bf16/fp16: three-step rounding to match GPU normal_()→mul_(std)→add_(mean).
 */

#ifndef STATELESS_NORMAL_IMPL_H
#define STATELESS_NORMAL_IMPL_H

#include "kernel_operator.h"
#include "../../random_common/arch35/random_kernel_base.h"
#include "../../random_common/arch35/random_unified_tiling_data_arch35.h"

namespace StatelessNormalSimt {

using namespace AscendC;
using namespace RandomKernelBase;

// Box-Muller normal transform functor
// mean/stdev are always float* (DT_FLOAT from L2 layer), output is T* (may be bf16/fp16/fp32)
// For bf16/fp16: three-step rounding to match GPU normal_()→mul_(std)→add_(mean)
template <typename T>
struct NormalTransform {
    __gm__ volatile float* meanGM_;
    __gm__ volatile float* stdevGM_;

    __aicore__ NormalTransform(__gm__ volatile float* meanGM, __gm__ volatile float* stdevGM)
        : meanGM_(meanGM), stdevGM_(stdevGM) {}

    __simt_callee__ __aicore__ inline void operator()(
        __gm__ volatile T* outputGm, uint64_t li, const uint32_t* results, uint32_t iStep,
        [[maybe_unused]] uint32_t unroll = 1)
    {
        uint32_t pairBase = (iStep / 2) * 2;
        float u1 = results[pairBase] * RAND_2POW32_INV + RAND_2POW32_INV_HALF;
        float u2 = results[pairBase + 1] * RAND_2POW32_INV + RAND_2POW32_INV_HALF;
        float z0, z1;
        // 使用对齐torch版本的BoxMullerFloat，无需eps保护
        BoxMullerFloat(u1, u2, &z0, &z1);
        float z = (iStep % 2 == 0) ? z0 : z1;
        if constexpr (IsSameType<T, float>::value) {
            // fp32: 无中间舍入，直接计算
            outputGm[li] = z * stdevGM_[li] + meanGM_[li];
        } else {
            // bf16/fp16: 严格对标 PyTorch GPU 三步舍入
            // GPU 内部: output.normal_(0,1) → output.mul_(std) → output.add_(mean)
            // 每步都在目标 dtype 上存储，产生中间舍入
            T zT = static_cast<T>(z);                                       // step1: normal_() 存为目标dtype
            T mulT = static_cast<T>(static_cast<float>(zT) * stdevGM_[li]); // step2: mul_(std) 在目标dtype下
            outputGm[li] = static_cast<T>(static_cast<float>(mulT) + meanGM_[li]); // step3: add_(mean) 在目标dtype下
        }
    }
};

// Launcher: wraps VF_CALL for each split block, adjusts GM pointers by gmOffset
// mean/stdev pointers are always float* (DT_FLOAT), output is T*
template <typename T>
struct NormalLauncher {
    int64_t seed_;
    int64_t realOffset_;
    GM_ADDR yAddr_;
    GM_ADDR meanAddr_;
    GM_ADDR stdevAddr_;

    __aicore__ NormalLauncher(int64_t seed, int64_t realOffset, GM_ADDR y, GM_ADDR mean, GM_ADDR stdev)
        : seed_(seed), realOffset_(realOffset), yAddr_(y), meanAddr_(mean), stdevAddr_(stdev) {}

    __aicore__ inline void operator()(
        const ExecutionPolicyKernel& policy,
        int64_t gmOffset,
        int64_t kernelOffset,
        int64_t numel,
        [[maybe_unused]] int64_t grid,
        int64_t totalThreads)
    {
        __gm__ volatile T* gmPtr = reinterpret_cast<__gm__ volatile T*>(yAddr_) + gmOffset;
        // mean/stdev 始终按 float* 读取（L2 传入 DT_FLOAT tensor）
        __gm__ volatile float* meanPtr = reinterpret_cast<__gm__ volatile float*>(meanAddr_) + gmOffset;
        __gm__ volatile float* stdevPtr = reinterpret_cast<__gm__ volatile float*>(stdevAddr_) + gmOffset;

        NormalTransform<T> transform(meanPtr, stdevPtr);
        Simt::VF_CALL<PhiloxSimtKernelDiscontinuous<T, NormalTransform<T>>>(
            Simt::Dim3(DEFAULT_SIMT_THREAD_NUM),
            gmPtr, realOffset_ + kernelOffset, seed_, static_cast<uint64_t>(numel),
            policy.magic, policy.shift, static_cast<uint64_t>(totalThreads), transform);
    }
};

// Entry point: called from stateless_normal.cpp
template <typename T>
__aicore__ inline void Process(
    GM_ADDR seed, GM_ADDR offset,
    GM_ADDR y, GM_ADDR mean, GM_ADDR stdev,
    const RandomUnifiedSimtTilingDataStruct* __restrict tilingData)
{
    if (GetBlockIdx() >= static_cast<uint32_t>(tilingData->usedCoreNum)) {
        return;
    }

    // 从 GM 直接读取真实 seed/offset（tiling 不再读取）
    int64_t realSeed = *(reinterpret_cast<__gm__ int64_t*>(seed));
    int64_t realOffset = *(reinterpret_cast<__gm__ int64_t*>(offset));

    NormalLauncher<T> launcher(realSeed, realOffset, y, mean, stdev);
    ProcessWithSplitBlocks(tilingData, launcher);
}

} // namespace StatelessNormalSimt

#endif // STATELESS_NORMAL_IMPL_H
