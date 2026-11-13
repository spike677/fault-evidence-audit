/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

/* !
 * \file tanh_dag.h
 * \brief
 */

#ifndef CANN_CUSTOM_OPS_TANH_DAG_H
#define CANN_CUSTOM_OPS_TANH_DAG_H

#include "atvoss/util/dag.h"
#include "atvoss/util/vec.h"
#include "atvoss/util/placeholder.h"
#include "atvoss/util/elems.h"

using namespace Ops::Base;
using namespace AscendC;
const int CAST_MODE_NONE = 0;
const int CAST_MODE_RINT = 1;

const float FP32_ZERO_015 = 0.0157396831;
const float FP32_ZERO_NEG_052 = -0.0523039624;
const float FP32_ZERO_133 = 0.133152977;
const float FP32_ZERO_NEG_333 = -0.333327681;
const float FP32_TWENTY = 20.0;
const float FP32_TWO = 2.0;
const float FP32_ONE = 1.0;
const float FP32_NEG_ONE = -1.0;
const float FP32_ZERO_55 = 0.55;

#ifdef __CCE_AICORE__
constexpr static AscendC::MicroAPI::CastTrait castTrait0 = { AscendC::MicroAPI::RegLayout::ZERO,
AscendC::MicroAPI::SatMode::UNKNOWN, AscendC::MicroAPI::MaskMergeMode::ZEROING, AscendC::RoundMode::UNKNOWN };
constexpr static AscendC::MicroAPI::CastTrait castTrait1 = { AscendC::MicroAPI::RegLayout::ZERO,
AscendC::MicroAPI::SatMode::NO_SAT, AscendC::MicroAPI::MaskMergeMode::ZEROING, AscendC::RoundMode::CAST_RINT };
#endif
namespace TanhDag1 {

template<class T>
struct TanhCustom : public Vec::ElemwiseUnaryOP<T, T> {
    __aicore__ inline TanhCustom(LocalTensor<T> &dst, LocalTensor<T> &src, uint32_t count) {
#ifdef __CCE_AICORE__
        uint32_t dtypeSize = sizeof(float);
        uint32_t vl = VECTOR_REG_WIDTH / dtypeSize;
        uint16_t loopNum = CeilDivision(count, vl);
        uint32_t vlSize = vl;
        __ubuf__ T* srcAddr = (__ubuf__ T*)src.GetPhyAddr();
        __ubuf__ T* dstAddr = (__ubuf__ T*)dst.GetPhyAddr();

        MicroAPI::RegTensor<float, MicroAPI::RegTraitNumOne> vregInput;
        MicroAPI::RegTensor<float, MicroAPI::RegTraitNumOne> vregInputAbs;
        MicroAPI::RegTensor<float, MicroAPI::RegTraitNumOne> vregInputSqr;
        MicroAPI::RegTensor<float, MicroAPI::RegTraitNumOne> vregInputMid;
        MicroAPI::RegTensor<float, MicroAPI::RegTraitNumOne> vregOutput;
        MicroAPI::RegTensor<float, MicroAPI::RegTraitNumOne> vregValue1;
        MicroAPI::RegTensor<float, MicroAPI::RegTraitNumOne> vregValue2;
        MicroAPI::MaskReg mask;
        MicroAPI::MaskReg cmpMaskReg;
        if constexpr(std::is_same_v<T, float>) {
            __VEC_SCOPE__ {
                MicroAPI::Duplicate(vregValue1, FP32_ZERO_133);
                MicroAPI::Duplicate(vregValue2, FP32_ZERO_NEG_333);
                for (uint16_t loopIdx = 0; loopIdx < loopNum; loopIdx++) {
                    mask = MicroAPI::UpdateMask<float, MicroAPI::RegTraitNumOne>(count);
                    // OpCopyIn
                    MicroAPI::DataCopy<T, MicroAPI::LoadDist::DIST_NORM>(vregInput, (__ubuf__ T*)(srcAddr + loopIdx * vlSize));

                    MicroAPI::Mul(vregInputSqr, vregInput, vregInput, mask);
                    MicroAPI::Muls(vregOutput, vregInputSqr, FP32_ZERO_015, mask);
                    MicroAPI::Adds(vregOutput, vregOutput, FP32_ZERO_NEG_052, mask);
                    MicroAPI::FusedMulDstAdd(vregOutput, vregInputSqr, vregValue1, mask);
                    MicroAPI::FusedMulDstAdd(vregOutput, vregInputSqr, vregValue2, mask);
                    MicroAPI::Mul(vregOutput, vregOutput, vregInputSqr, mask);
                    MicroAPI::FusedMulDstAdd(vregOutput, vregInput, vregInput, mask);

                    MicroAPI::Abs(vregInputAbs, vregInput, mask);
                    MicroAPI::Mins(vregInput, vregInput, FP32_TWENTY, mask);
                    MicroAPI::Muls(vregInput, vregInput, FP32_TWO, mask);
                    MicroAPI::Exp(vregInput, vregInput, mask);
                    MicroAPI::Adds(vregInputMid, vregInput, FP32_NEG_ONE, mask);
                    MicroAPI::Adds(vregInputSqr, vregInput, FP32_ONE, mask);
                    MicroAPI::Div(vregInputMid, vregInputMid, vregInputSqr, mask);

                    MicroAPI::CompareScalar<float, CMPMODE::LT>(cmpMaskReg, vregInputAbs, FP32_ZERO_55, mask);
                    MicroAPI::Select(vregOutput, vregOutput, vregInputMid, cmpMaskReg);
                    // OpCopyOut
                    MicroAPI::DataCopy<T, MicroAPI::StoreDist::DIST_NORM_B32>((__ubuf__ T*)(dstAddr + loopIdx * vlSize), vregOutput, mask);
                }
            }
        } else {
            MicroAPI::RegTensor<T, MicroAPI::RegTraitNumOne> vregInput16;
            MicroAPI::RegTensor<T, MicroAPI::RegTraitNumOne> vregOutput16;
            __VEC_SCOPE__ {
                MicroAPI::Duplicate(vregValue1, FP32_ZERO_133);
                MicroAPI::Duplicate(vregValue2, FP32_ZERO_NEG_333);
                for (uint16_t loopIdx = 0; loopIdx < loopNum; loopIdx++) {
                    mask = MicroAPI::UpdateMask<float, MicroAPI::RegTraitNumOne>(count);
                    // OpCopyIn
                    MicroAPI::DataCopy<T, MicroAPI::LoadDist::DIST_UNPACK_B16>(vregInput16, (__ubuf__ T*)(srcAddr + loopIdx * vlSize));
                    MicroAPI::Cast<float, T, castTrait0>(vregInput, vregInput16, mask);

                    MicroAPI::Mul(vregInputSqr, vregInput, vregInput, mask);
                    MicroAPI::Muls(vregOutput, vregInputSqr, FP32_ZERO_015, mask);
                    MicroAPI::Adds(vregOutput, vregOutput, FP32_ZERO_NEG_052, mask);
                    MicroAPI::FusedMulDstAdd(vregOutput, vregInputSqr, vregValue1, mask);
                    MicroAPI::FusedMulDstAdd(vregOutput, vregInputSqr, vregValue2, mask);
                    MicroAPI::Mul(vregOutput, vregOutput, vregInputSqr, mask);
                    MicroAPI::FusedMulDstAdd(vregOutput, vregInput, vregInput, mask);

                    MicroAPI::Abs(vregInputAbs, vregInput, mask);
                    MicroAPI::Mins(vregInput, vregInput, FP32_TWENTY, mask);
                    MicroAPI::Muls(vregInput, vregInput, FP32_TWO, mask);
                    MicroAPI::Exp(vregInput, vregInput, mask);
                    MicroAPI::Adds(vregInputMid, vregInput, FP32_NEG_ONE, mask);
                    MicroAPI::Adds(vregInputSqr, vregInput, FP32_ONE, mask);
                    MicroAPI::Div(vregInputMid, vregInputMid, vregInputSqr, mask);

                    MicroAPI::CompareScalar<float, CMPMODE::LT>(cmpMaskReg, vregInputAbs, FP32_ZERO_55, mask);
                    MicroAPI::Select(vregOutput, vregOutput, vregInputMid, cmpMaskReg);

                    MicroAPI::Cast<T, float, castTrait1>(vregOutput16, vregOutput, mask);
                    // OpCopyOut
                    MicroAPI::DataCopy<T, MicroAPI::StoreDist::DIST_PACK_B32>((__ubuf__ T*)(dstAddr + loopIdx * vlSize), vregOutput16, mask);
                }
            }
        }
#endif
    }
};
} // namespace TanhDag1

template <typename U, typename T=float>
struct TanhDAG {
    using OpCopyIn0 = Bind<Vec::CopyIn<U>, Placeholder::In0<U>>;

    using OpCopyIn0Cast = Bind<Vec::Cast<T, U, CAST_MODE_NONE>, OpCopyIn0>;
    using OpResult1 = Bind<TanhDag1::TanhCustom<T>, OpCopyIn0Cast>;
    using OpResultCast = Bind<Vec::Cast<U, T, CAST_MODE_RINT>, OpResult1>;

    using OpCopyOut = Bind<Vec::CopyOut<U>, Placeholder::Out0<U>, OpResultCast>;

    using Outputs = Elems<OpCopyOut>;
    using MemCfg = MemOptCfg<MemLevel::LEVEL_2>;
    using OpDag = DAGSch<Outputs, void, MemCfg>;
};

#endif  // CANN_CUSTOM_OPS_TANH_DAG_H
