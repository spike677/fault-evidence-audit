/**
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

/*!
 * \file cdist_grad_operator.h
 * \brief Custom Vec operators for cdist_grad — Compare+Select via MicroAPI
 *
 * By encapsulating CompareScalar + Select inside a single Vec operator node,
 * we avoid the multi-consumer buffer conflicts that occur when Compare and Select
 * are separate DAG nodes.
 *
 * Operators:
 *   CdistGradSignOp       — sign(x): 1.0 / -1.0 / 0.0  (ElemwiseUnaryOP)
 *   CdistGradMaskGEOp     — a >= b ? 1.0 : 0.0          (ElemwiseBinaryOP)
 *   CdistGradMaskNEZeroOp — x != 0 ? 1.0 : 0.0          (ElemwiseUnaryOP)
 */

#ifndef CDIST_GRAD_OPERATOR_H
#define CDIST_GRAD_OPERATOR_H

#include "atvoss/util/vec.h"

namespace CdistGrad {
using namespace Ops::Base;

/**
 * \brief sign(x): 1.0 if x > 0, -1.0 if x < 0, 0.0 if x == 0
 *
 * Uses CompareScalar GT/LT to detect positive/negative, Select to choose values.
 * Replaces arithmetic approximation: diff / (|diff| + eps)
 */
template <typename PromoteT>
struct CdistGradSignOp : public Vec::ElemwiseUnaryOP<PromoteT, PromoteT> {
    __aicore__ inline CdistGradSignOp(LocalTensor<PromoteT>& dst, LocalTensor<PromoteT>& src, uint32_t count)
    {
#ifdef __CCE_AICORE__
        uint32_t dtypeSize = sizeof(PromoteT);
        uint32_t VL = AscendC::VECTOR_REG_WIDTH / dtypeSize;
        uint16_t loopNum = CeilDivision(count, VL);
        uint32_t vlSize = VL;
        __VEC_SCOPE__
        {
            __ubuf__ PromoteT* srcAddr = (__ubuf__ PromoteT*)src.GetPhyAddr();
            __ubuf__ PromoteT* dstAddr = (__ubuf__ PromoteT*)dst.GetPhyAddr();

            AscendC::MicroAPI::RegTensor<PromoteT, AscendC::MicroAPI::RegTraitNumOne> vregSrc;
            AscendC::MicroAPI::RegTensor<PromoteT, AscendC::MicroAPI::RegTraitNumOne> vregDst;
            AscendC::MicroAPI::RegTensor<PromoteT, AscendC::MicroAPI::RegTraitNumOne> vregOne;
            AscendC::MicroAPI::RegTensor<PromoteT, AscendC::MicroAPI::RegTraitNumOne> vregNegOne;
            AscendC::MicroAPI::RegTensor<PromoteT, AscendC::MicroAPI::RegTraitNumOne> vregZero;
            AscendC::MicroAPI::MaskReg opMask;
            AscendC::MicroAPI::MaskReg posMask;
            AscendC::MicroAPI::MaskReg negMask;

            AscendC::MicroAPI::Duplicate(vregOne, static_cast<PromoteT>(1.0));
            AscendC::MicroAPI::Duplicate(vregNegOne, static_cast<PromoteT>(-1.0));
            AscendC::MicroAPI::Duplicate(vregZero, static_cast<PromoteT>(0.0));

            for (uint16_t loopIdx = 0; loopIdx < loopNum; loopIdx++) {
                opMask = AscendC::MicroAPI::UpdateMask<PromoteT, AscendC::MicroAPI::RegTraitNumOne>(count);

                AscendC::MicroAPI::DataCopy(vregSrc, srcAddr + loopIdx * vlSize);

                // posMask = (x > 0)
                AscendC::MicroAPI::CompareScalar<PromoteT, CMPMODE::GT>(
                    posMask, vregSrc, static_cast<PromoteT>(0), opMask);
                // negMask = (x < 0)
                AscendC::MicroAPI::CompareScalar<PromoteT, CMPMODE::LT>(
                    negMask, vregSrc, static_cast<PromoteT>(0), opMask);

                // Select(dst, true_val, false_val, mask): mask=1 → true_val, mask=0 → false_val
                // Step 1: posMask=1 → 1.0, posMask=0 → 0.0
                AscendC::MicroAPI::Select(vregDst, vregOne, vregZero, posMask);
                // Step 2: negMask=1 → -1.0, negMask=0 → keep step1 result
                AscendC::MicroAPI::Select(vregDst, vregNegOne, vregDst, negMask);

                AscendC::MicroAPI::DataCopy(dstAddr + loopIdx * vlSize, vregDst, opMask);
            }
        }
#endif
    }
};

/**
 * \brief a == b ? 1.0 : 0.0  (binary mask: exact equality)
 *
 * Computes diff = a - b, then CompareScalar EQ(diff, 0) → mask.
 * Select(1.0, 0.0, mask) gives 1.0 where a == b, 0.0 otherwise.
 * Matches PyTorch's p=inf backward: mask = 1 - min(1, ceil(| |diff| - dist |))
 */
template <typename PromoteT>
struct CdistGradMaskEQOp : public Vec::ElemwiseBinaryOP<PromoteT, PromoteT, PromoteT> {
    __aicore__ inline CdistGradMaskEQOp(LocalTensor<PromoteT>& dst, LocalTensor<PromoteT>& src1,
                                         LocalTensor<PromoteT>& src2, uint32_t count)
    {
#ifdef __CCE_AICORE__
        uint32_t dtypeSize = sizeof(PromoteT);
        uint32_t VL = AscendC::VECTOR_REG_WIDTH / dtypeSize;
        uint16_t loopNum = CeilDivision(count, VL);
        uint32_t vlSize = VL;
        __VEC_SCOPE__
        {
            __ubuf__ PromoteT* src1Addr = (__ubuf__ PromoteT*)src1.GetPhyAddr();
            __ubuf__ PromoteT* src2Addr = (__ubuf__ PromoteT*)src2.GetPhyAddr();
            __ubuf__ PromoteT* dstAddr = (__ubuf__ PromoteT*)dst.GetPhyAddr();

            AscendC::MicroAPI::RegTensor<PromoteT, AscendC::MicroAPI::RegTraitNumOne> vregA;
            AscendC::MicroAPI::RegTensor<PromoteT, AscendC::MicroAPI::RegTraitNumOne> vregB;
            AscendC::MicroAPI::RegTensor<PromoteT, AscendC::MicroAPI::RegTraitNumOne> vregDiff;
            AscendC::MicroAPI::RegTensor<PromoteT, AscendC::MicroAPI::RegTraitNumOne> vregOne;
            AscendC::MicroAPI::RegTensor<PromoteT, AscendC::MicroAPI::RegTraitNumOne> vregZero;
            AscendC::MicroAPI::RegTensor<PromoteT, AscendC::MicroAPI::RegTraitNumOne> vregResult;
            AscendC::MicroAPI::MaskReg opMask;
            AscendC::MicroAPI::MaskReg eqMask;

            AscendC::MicroAPI::Duplicate(vregOne, static_cast<PromoteT>(1.0));
            AscendC::MicroAPI::Duplicate(vregZero, static_cast<PromoteT>(0.0));

            for (uint16_t loopIdx = 0; loopIdx < loopNum; loopIdx++) {
                opMask = AscendC::MicroAPI::UpdateMask<PromoteT, AscendC::MicroAPI::RegTraitNumOne>(count);

                AscendC::MicroAPI::DataCopy(vregA, src1Addr + loopIdx * vlSize);
                AscendC::MicroAPI::DataCopy(vregB, src2Addr + loopIdx * vlSize);

                // diff = a - b
                AscendC::MicroAPI::Sub(vregDiff, vregA, vregB, opMask);

                // eqMask = (diff == 0)  i.e. a == b
                AscendC::MicroAPI::CompareScalar<PromoteT, CMPMODE::EQ>(
                    eqMask, vregDiff, static_cast<PromoteT>(0), opMask);

                // vregResult = 1.0 where eqMask=1(a==b), 0.0 where eqMask=0(a!=b)
                AscendC::MicroAPI::Select(vregResult, vregOne, vregZero, eqMask);
                AscendC::MicroAPI::DataCopy(dstAddr + loopIdx * vlSize, vregResult, opMask);
            }
        }
#endif
    }
};

/**
 * \brief x != 0 ? 1.0 : 0.0  (non-zero mask)
 *
 * CompareScalar EQ(x, 0) → eqMask, then Select(1.0, 0.0, eqMask).
 * Where x==0: eqMask=1 → Select picks 0.0 (true branch = first arg).
 * Where x!=0: eqMask=0 → Select picks 1.0 (false branch = second arg).
 * Replaces arithmetic approximation: x / (x + eps)
 */
template <typename PromoteT>
struct CdistGradMaskNEZeroOp : public Vec::ElemwiseUnaryOP<PromoteT, PromoteT> {
    __aicore__ inline CdistGradMaskNEZeroOp(LocalTensor<PromoteT>& dst, LocalTensor<PromoteT>& src, uint32_t count)
    {
#ifdef __CCE_AICORE__
        uint32_t elemSize = sizeof(PromoteT);
        uint32_t vecLen = AscendC::VECTOR_REG_WIDTH / elemSize;
        uint16_t loopCnt = CeilDivision(count, vecLen);
        uint32_t vlLen = vecLen;
        __VEC_SCOPE__
        {
            __ubuf__ PromoteT* inputAddr = (__ubuf__ PromoteT*)src.GetPhyAddr();
            __ubuf__ PromoteT* outputAddr = (__ubuf__ PromoteT*)dst.GetPhyAddr();

            AscendC::MicroAPI::RegTensor<PromoteT, AscendC::MicroAPI::RegTraitNumOne> vregIn;
            AscendC::MicroAPI::RegTensor<PromoteT, AscendC::MicroAPI::RegTraitNumOne> vregValOne;
            AscendC::MicroAPI::RegTensor<PromoteT, AscendC::MicroAPI::RegTraitNumOne> vregValZero;
            AscendC::MicroAPI::RegTensor<PromoteT, AscendC::MicroAPI::RegTraitNumOne> vregOut;
            AscendC::MicroAPI::MaskReg cmpMask;
            AscendC::MicroAPI::MaskReg zeroMask;

            AscendC::MicroAPI::Duplicate(vregValOne, static_cast<PromoteT>(1.0));
            AscendC::MicroAPI::Duplicate(vregValZero, static_cast<PromoteT>(0.0));

            for (uint16_t idx = 0; idx < loopCnt; idx++) {
                cmpMask = AscendC::MicroAPI::UpdateMask<PromoteT, AscendC::MicroAPI::RegTraitNumOne>(count);

                AscendC::MicroAPI::DataCopy(vregIn, inputAddr + idx * vlLen);

                // zeroMask = (x == 0)
                AscendC::MicroAPI::CompareScalar<PromoteT, CMPMODE::EQ>(
                    zeroMask, vregIn, static_cast<PromoteT>(0), cmpMask);

                // vregOut = 0.0 where zeroMask=1(x==0), 1.0 where zeroMask=0(x!=0)
                AscendC::MicroAPI::Select(vregOut, vregValZero, vregValOne, zeroMask);
                AscendC::MicroAPI::DataCopy(outputAddr + idx * vlLen, vregOut, cmpMask);
            }
        }
#endif
    }
};

}  // namespace CdistGrad

#endif  // CDIST_GRAD_OPERATOR_H
