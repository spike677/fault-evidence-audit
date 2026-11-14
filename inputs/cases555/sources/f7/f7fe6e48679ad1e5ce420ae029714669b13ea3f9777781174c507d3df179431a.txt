/**
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

/*!
 * \file polar_dag.h
 * \brief polar operator BRC DAG definition for arch35 (ascend950)
 *
 * Polar operator: abs(float) and angle(float) -> out(complex64)
 * out.real = abs * cos(angle)
 * out.imag = abs * sin(angle)
 * Supports broadcast between abs and angle inputs via CopyInBrc.
 * Uses AscendC SIMD vector operations (Cos, Sin, Mul) and Interleave
 * with double buffer pipeline.
 */
#ifndef POLAR_DAG_H_
#define POLAR_DAG_H_

#include "atvoss/util/dag.h"
#include "atvoss/util/vec.h"
#include "atvoss/util/placeholder.h"
#include "atvoss/util/elems.h"

#ifndef __CCE_AICORE__
struct complex64 {
    float real;
    float imag;
};
#else
namespace PolarOp {
using namespace AscendC;
constexpr uint32_t POLAR_TAIL_THREAD_NUM = 1024;

template <typename T>
__simt_vf__ __aicore__ inline void PolarTailCompute(__ubuf__ T* dst, __ubuf__ T* abs, __ubuf__ T* angle,
                                                    uint64_t alignedCount, uint64_t count)
{
    for (uint64_t i = alignedCount + threadIdx.x; i < count; i += blockDim.x) {
        T cosVal = Simt::Cos(angle[i]);
        T sinVal = Simt::Sin(angle[i]);
        dst[i * 2] = abs[i] * cosVal;
        dst[i * 2 + 1] = abs[i] * sinVal;
    }
}
} // namespace PolarOp
#endif

namespace PolarOp {
using namespace Ops::Base;

template <class C, class T>
struct PolarMerge : public Vec::ElemwiseBinaryOP<C, T, T> {
    __aicore__ inline PolarMerge(LocalTensor<C>& dst, LocalTensor<T>& abs, LocalTensor<T>& angle, uint64_t count)
    {
#ifdef __CCE_AICORE__
        using namespace AscendC;
        constexpr uint32_t ALIGN_ELEMS = 32 / sizeof(T); // 32B的元素数量
        LocalTensor<T> dstT = dst.template ReinterpretCast<T>();

        uint64_t alignedCount = (count / ALIGN_ELEMS) * ALIGN_ELEMS;
        if (alignedCount > 0) {
            LocalTensor<T> tmpReal = dstT;
            LocalTensor<T> tmpImag = dstT[alignedCount];

            AscendC::Cos(tmpReal, angle, alignedCount);        // tmpReal = cos(angle)
            AscendC::Sin(tmpImag, angle, alignedCount);        // tmpImag = sin(angle)
            AscendC::Mul(tmpReal, abs, tmpReal, alignedCount); // tmpReal = abs * cos(angle)
            AscendC::Mul(tmpImag, abs, tmpImag, alignedCount); // tmpImag = abs * sin(angle)

            Interleave(dstT, dstT[alignedCount], tmpReal, tmpImag, alignedCount);
        }

        // 非32B对齐的尾部数据（<32B，VEC无法处理，用Simt::VF_CALL计算）
        if (count > alignedCount) {
            __ubuf__ T* dstAddr = (__ubuf__ T*)dstT.GetPhyAddr();
            __ubuf__ T* absAddr = (__ubuf__ T*)abs.GetPhyAddr();
            __ubuf__ T* angleAddr = (__ubuf__ T*)angle.GetPhyAddr();
            Simt::VF_CALL<PolarTailCompute<T>>(Simt::Dim3(POLAR_TAIL_THREAD_NUM), dstAddr, absAddr, angleAddr,
                                               alignedCount, count);
        }

#endif
    }
};

template <typename C, typename T>
struct PolarBrcDag {
    using OpCopyInAbs = Bind<Vec::CopyInBrc<T>, Placeholder::In0<T>>;
    using OpCopyInAngle = Bind<Vec::CopyInBrc<T>, Placeholder::In1<T>>;
    using OpMerge = Bind<PolarMerge<C, T>, OpCopyInAbs, OpCopyInAngle>;
    using OpCopyOut = Bind<Vec::CopyOut<C>, Placeholder::Out0<C>, OpMerge>;

    using Outputs = Elems<OpCopyOut>;
    using MemCfg = MemOptCfg<MemLevel::LEVEL_2>;
    using OpDag = DAGSch<Outputs, void, MemCfg>;
};

} // namespace PolarOp
#endif // POLAR_DAG_H_