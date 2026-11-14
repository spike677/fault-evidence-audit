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
 * \file im2col_gather_cut_nc.h
 * \brief
 */

#ifndef _IM2COL_GATHER_CUT_NC_
#define _IM2COL_GATHER_CUT_NC_

#include "kernel_operator.h"
#include "op_kernel/platform_util.h"
#include "op_kernel/math_util.h"
#include "im2col_tilingdata.h"

namespace Im2col {
using namespace AscendC;

constexpr int32_t BUFFER_NUM = 2;
constexpr int32_t ALIGN_NUM = 32;

template <typename T, bool isPadding>
class Im2ColGatherCutNc {
public:
    __aicore__ inline Im2ColGatherCutNc(){};
    __aicore__ inline void Init(GM_ADDR x, GM_ADDR y, const Im2ColNCHWTilingData* tilingData, TPipe* pipe);
    __aicore__ inline void Process();

private:
    __aicore__ inline void CopyIn(int32_t ubFactorNC, int64_t loopIdx);
    __aicore__ inline void Compute(int32_t ubFactorNC);
    __aicore__ inline void CopyOut(int64_t peerloopElementsOut, int64_t loopIdx);
    __aicore__ inline void SetInputInfo(const Im2ColInputInfo& input);
    __aicore__ inline void GatherWithPadding(LocalTensor<T>& input, LocalTensor<T>& output, int32_t ubFactorNC);
    __aicore__ inline void GatherNoPaddingVFCrossNc(LocalTensor<T>& input, LocalTensor<T>& output, int32_t ubFactorNC);
    __aicore__ inline void GatherNoPaddingVFWithinNc(LocalTensor<T>& input, LocalTensor<T>& output, int32_t ubFactorNC);
    __aicore__ inline void GatherNoPadding(LocalTensor<T>& input, LocalTensor<T>& output, int32_t ubFactorNC);

private:
    int64_t blockIdx_;

    // buffer
    TQue<QuePosition::VECIN, BUFFER_NUM> inputQueue_;
    TQue<QuePosition::VECOUT, BUFFER_NUM> outputQueue_;
    GlobalTensor<T> inputGM_;
    GlobalTensor<T> outputGM_;

    // tiling params
    const Im2ColNCHWTilingData* tilingData_;
    int64_t N_ = 0;
    int64_t C_ = 0;
    int64_t H_ = 0;
    int64_t W_ = 0;
    int64_t hStride_ = 0;
    int64_t wStride_ = 0;
    int64_t hKernelSize_ = 0;
    int64_t wKernelSize_ = 0;
    int64_t hDilation_ = 0;
    int64_t wDilation_ = 0;
    int64_t hPaddingBefore_ = 0;
    int64_t hPaddingAfter_ = 0;
    int64_t wPaddingBefore_ = 0;
    int64_t wPaddingAfter_ = 0;

    int32_t ubLoopNum_ = 0;
    int32_t ubFactorNC_ = 0;
    int32_t ubTailFactorNC_ = 0;
    int64_t inUbFactor_ = 0;
    int64_t outUbFactor_ = 0;
    int64_t inputOffset_ = 0;
    int64_t outputOffset_ = 0;
    int64_t convW_ = 0;
    int64_t convH_ = 0;
    int64_t inputHwSize_ = 0;
    int64_t inputHwAlignSize_ = 0;
    int64_t outputHwSize_ = 0;
    using RangeType_ = std::conditional_t<sizeof(T) <= sizeof(int16_t), int16_t, int32_t>;
    using IdxType_ = std::conditional_t<sizeof(T) <= sizeof(int16_t), uint16_t, uint32_t>;
    using CastType_ =
        std::conditional_t<sizeof(T) == 1, std::conditional_t<std::is_same_v<T, uint8_t>, uint16_t, int16_t>, T>;
    uint32_t vlSize_ = static_cast<uint32_t>(Ops::Base::GetVRegSize() / sizeof(CastType_));
};

template <typename T, bool isPadding>
__aicore__ inline void Im2ColGatherCutNc<T, isPadding>::Init(
    GM_ADDR x, GM_ADDR y, const Im2ColNCHWTilingData* tilingData, TPipe* pipe)
{
    tilingData_ = tilingData;
    SetInputInfo(tilingData_->input);
    blockIdx_ = GetBlockIdx();
    if (blockIdx_ * tilingData_->rectAnglesPerCore > tilingData_->totalRectAngles) {
        return;
    }
    int64_t leftAngles = tilingData_->totalRectAngles - blockIdx_ * tilingData_->rectAnglesPerCore;
    ubLoopNum_ =
        leftAngles < static_cast<int64_t>(tilingData_->rectAnglesPerCore) ? leftAngles : tilingData_->rectAnglesPerCore;

    convW_ = tilingData_->convKernelNumInWidth;
    convH_ = tilingData_->convKernelNumInHeight;
    inputHwSize_ = H_ * W_;
    inputHwAlignSize_ = (inputHwSize_ + ALIGN_NUM / sizeof(T) - 1) / (ALIGN_NUM / sizeof(T)) * (ALIGN_NUM / sizeof(T));
    outputHwSize_ = convH_ * convW_ * hKernelSize_ * wKernelSize_;

    inUbFactor_ = inputHwSize_ * tilingData_->ubFactorNC;
    inputOffset_ = inUbFactor_ * tilingData_->rectAnglesPerCore * blockIdx_;
    outUbFactor_ = outputHwSize_ * tilingData_->ubFactorNC;
    outputOffset_ = outUbFactor_ * tilingData_->rectAnglesPerCore * blockIdx_;

    inputGM_.SetGlobalBuffer((__gm__ T*)x);
    outputGM_.SetGlobalBuffer((__gm__ T*)y);
    pipe->InitBuffer(inputQueue_, BUFFER_NUM, tilingData_->inputBufferSize);
    pipe->InitBuffer(outputQueue_, BUFFER_NUM, tilingData_->outputBufferSize);
}

template <typename T, bool isPadding>
__aicore__ inline void Im2ColGatherCutNc<T, isPadding>::Process()
{
    if (blockIdx_ * tilingData_->rectAnglesPerCore > tilingData_->totalRectAngles) {
        return;
    }

    for (int32_t i = 0; i < ubLoopNum_; i++) {
        int64_t leftFactorNC = N_ * C_ - tilingData_->ubFactorNC * tilingData_->rectAnglesPerCore * blockIdx_ -
                               i * tilingData_->ubFactorNC;
        int32_t ubFactorNC =
            leftFactorNC < static_cast<int64_t>(tilingData_->ubFactorNC) ? leftFactorNC : tilingData_->ubFactorNC;
        int64_t peerloopElementsOut = outputHwSize_ * ubFactorNC;
        CopyIn(ubFactorNC, i);
        Compute(ubFactorNC);
        CopyOut(peerloopElementsOut, i);
    }
}

template <typename T, bool isPadding>
__aicore__ inline void Im2ColGatherCutNc<T, isPadding>::SetInputInfo(const Im2ColInputInfo& input)
{
    N_ = input.N;
    C_ = input.C;
    H_ = input.H;
    W_ = input.W;
    hStride_ = input.hStride;
    wStride_ = input.wStride;
    hKernelSize_ = input.hKernelSize;
    wKernelSize_ = input.wKernelSize;
    hDilation_ = input.hDilation;
    wDilation_ = input.wDilation;
    hPaddingBefore_ = input.hPaddingBefore;
    hPaddingAfter_ = input.hPaddingAfter;
    wPaddingBefore_ = input.wPaddingBefore;
    wPaddingAfter_ = input.wPaddingAfter;
}

template <typename T, bool isPadding>
__aicore__ inline void Im2ColGatherCutNc<T, isPadding>::CopyIn(int32_t ubFactorNC, int64_t loopIdx)
{
    LocalTensor<T> input = inputQueue_.AllocTensor<T>();
    DataCopyPadExtParams<T> padParams{false, 0, 0, 0};
    DataCopyExtParams copyInParams{
        static_cast<uint16_t>(ubFactorNC), static_cast<uint32_t>(inputHwSize_ * sizeof(T)), 0, 0, 0};
    if (vlSize_ / outputHwSize_ > 1) {
        DataCopyPad<T, PaddingMode::Compact>(
            input, inputGM_[inputOffset_ + loopIdx * inUbFactor_], copyInParams, padParams);
    } else {
        DataCopyPad(input, inputGM_[inputOffset_ + loopIdx * inUbFactor_], copyInParams, padParams);
    }
    inputQueue_.EnQue(input);
}

template <typename T, bool isPadding>
__aicore__ inline void Im2ColGatherCutNc<T, isPadding>::Compute(int32_t ubFactorNC)
{
    LocalTensor<T> input = inputQueue_.DeQue<T>();
    LocalTensor<T> output = outputQueue_.AllocTensor<T>();

    if constexpr (!isPadding) {
        GatherNoPadding(input, output, ubFactorNC);
    } else {
        GatherWithPadding(input, output, ubFactorNC);
    }

    outputQueue_.EnQue<T>(output);
    inputQueue_.FreeTensor(input);
}

template <typename T, bool isPadding>
__aicore__ inline void Im2ColGatherCutNc<T, isPadding>::CopyOut(int64_t peerloopElementsOut, int64_t loopIdx)
{
    LocalTensor<T> output = outputQueue_.DeQue<T>();
    DataCopyExtParams copyInParams{1, static_cast<uint32_t>(peerloopElementsOut * sizeof(T)), 0, 0, 0};
    DataCopyPad(outputGM_[outputOffset_ + loopIdx * outputHwSize_ * tilingData_->ubFactorNC], output, copyInParams);
    outputQueue_.FreeTensor(output);
}

template <typename T, bool isPadding>
__aicore__ inline void Im2ColGatherCutNc<T, isPadding>::GatherWithPadding(
    LocalTensor<T>& input, LocalTensor<T>& output, int32_t ubFactorNC)
{
    uint16_t loopNum = static_cast<uint16_t>(Ops::Base::CeilDiv(static_cast<uint32_t>(outputHwSize_), vlSize_));
    uint32_t maskSize = static_cast<uint32_t>(outputHwSize_);
    uint32_t postUpdateStride = static_cast<uint32_t>(outputHwSize_);

    IdxType_ scalarHPadBfr = static_cast<IdxType_>(hPaddingBefore_);
    IdxType_ scalarHPadAft = static_cast<IdxType_>(H_ + hPaddingBefore_);
    IdxType_ scalarWPadBfr = static_cast<IdxType_>(wPaddingBefore_);
    IdxType_ scalarWPadAft = static_cast<IdxType_>(W_ + wPaddingBefore_);
    __local_mem__ T* inputAddr = (__local_mem__ T*)input.GetPhyAddr();
    __local_mem__ T* outputAddr = (__local_mem__ T*)output.GetPhyAddr();
    __VEC_SCOPE__
    {
        MicroAPI::RegTensor<RangeType_> tmpIdxReg;
        MicroAPI::RegTensor<IdxType_> idxReg;

        MicroAPI::RegTensor<IdxType_> convWReg;
        MicroAPI::RegTensor<IdxType_> convHReg;
        MicroAPI::RegTensor<IdxType_> kWReg;
        MicroAPI::RegTensor<IdxType_> iConvWReg;
        MicroAPI::RegTensor<IdxType_> iConvHReg;
        MicroAPI::RegTensor<IdxType_> iKWReg;
        MicroAPI::RegTensor<IdxType_> iKHReg;
        MicroAPI::RegTensor<IdxType_> outLReg;
        MicroAPI::RegTensor<IdxType_> iWReg;
        MicroAPI::RegTensor<IdxType_> iHReg;
        MicroAPI::RegTensor<IdxType_> inputIdxReg;
        MicroAPI::RegTensor<IdxType_> divReg;
        MicroAPI::RegTensor<IdxType_> divReg1;
        MicroAPI::RegTensor<IdxType_> mulReg;
        MicroAPI::RegTensor<IdxType_> mulReg1;
        MicroAPI::RegTensor<IdxType_> subReg;
        MicroAPI::RegTensor<T> dstReg;
        MicroAPI::RegTensor<T> dstRegT;
        MicroAPI::RegTensor<CastType_> zeroReg;
        MicroAPI::UnalignReg uReg;
        MicroAPI::MaskReg mask;
        MicroAPI::MaskReg mask1;
        MicroAPI::MaskReg mask2;
        MicroAPI::MaskReg wPadMask;
        MicroAPI::MaskReg hPadMask;
        MicroAPI::MaskReg padMask;

        MicroAPI::Duplicate(convWReg, IdxType_(convW_));
        MicroAPI::Duplicate(convHReg, IdxType_(convH_));
        MicroAPI::Duplicate(kWReg, IdxType_(wKernelSize_));
        MicroAPI::Duplicate(zeroReg, 0);
        MicroAPI::Arange(tmpIdxReg, 0);
        idxReg = (MicroAPI::RegTensor<IdxType_>&)tmpIdxReg;

        for (uint16_t ncIdx = 0; ncIdx < static_cast<uint16_t>(ubFactorNC); ncIdx++) {
            for (uint16_t loopIdx = 0; loopIdx < loopNum; loopIdx++) {
                mask = MicroAPI::UpdateMask<IdxType_>(maskSize);
                // iConvW = idx % convW
                MicroAPI::Div(divReg, idxReg, convWReg, mask);
                MicroAPI::Mul(mulReg, divReg, convWReg, mask);
                MicroAPI::Sub(iConvWReg, idxReg, mulReg, mask);

                // iConvH = idx % (convW*convH) / convW
                MicroAPI::Mul(outLReg, convWReg, convHReg, mask);
                MicroAPI::Div(divReg, idxReg, outLReg, mask);
                MicroAPI::Mul(mulReg, divReg, outLReg, mask);
                MicroAPI::Sub(subReg, idxReg, mulReg, mask);
                MicroAPI::Div(iConvHReg, subReg, convWReg, mask);

                // iKW = idx / (convW*convH) % kW
                MicroAPI::Div(divReg, idxReg, outLReg, mask);
                MicroAPI::Div(divReg1, divReg, kWReg, mask);
                MicroAPI::Mul(mulReg, divReg1, kWReg, mask);
                MicroAPI::Sub(iKWReg, divReg, mulReg, mask);

                // iKH = idx / (convW*convH) / kW
                MicroAPI::Move(iKHReg, divReg1, mask);

                // iW = iConvW * Sw + iKW * Dw
                MicroAPI::Muls(mulReg, iConvWReg, IdxType_(wStride_), mask);
                MicroAPI::Muls(mulReg1, iKWReg, IdxType_(wDilation_), mask);
                MicroAPI::Add(iWReg, mulReg, mulReg1, mask);

                // iH = iConvH * Sh + iKH * Dh
                MicroAPI::Muls(mulReg, iConvHReg, IdxType_(hStride_), mask);
                MicroAPI::Muls(mulReg1, iKHReg, IdxType_(hDilation_), mask);
                MicroAPI::Add(iHReg, mulReg, mulReg1, mask);

                // inputIdx = iH * W + iW
                MicroAPI::Muls(mulReg, iHReg, IdxType_(W_), mask);
                MicroAPI::Add(inputIdxReg, mulReg, iWReg, mask);

                // gather
                MicroAPI::DataCopyGather(
                    (MicroAPI::RegTensor<CastType_>&)dstReg, inputAddr + ncIdx * inputHwAlignSize_, inputIdxReg, mask);

                // Padding
                MicroAPI::CompareScalar<IdxType_, CMPMODE::GE>(mask1, iWReg, scalarWPadBfr, mask);
                MicroAPI::CompareScalar<IdxType_, CMPMODE::LT>(mask2, iWReg, scalarWPadAft, mask);
                MicroAPI::MaskAnd(wPadMask, mask1, mask2, mask);
                MicroAPI::CompareScalar<IdxType_, CMPMODE::GE>(mask1, iHReg, scalarHPadBfr, mask);
                MicroAPI::CompareScalar<IdxType_, CMPMODE::LT>(mask2, iHReg, scalarHPadAft, mask);
                MicroAPI::MaskAnd(hPadMask, mask1, mask2, mask);
                MicroAPI::MaskAnd(padMask, wPadMask, hPadMask, mask);
                MicroAPI::Select(
                    (MicroAPI::RegTensor<CastType_>&)dstReg, (MicroAPI::RegTensor<CastType_>&)dstReg, zeroReg, padMask);

                __local_mem__ T* outputAddrTmp = outputAddr + ncIdx * outputHwSize_ + loopIdx * vlSize_;
                if constexpr (sizeof(T) == 1) {
                    MicroAPI::Pack(dstRegT, (MicroAPI::RegTensor<CastType_>&)dstReg);
                    MicroAPI::DataCopyUnAlign(outputAddrTmp, dstRegT, uReg, postUpdateStride);
                } else {
                    MicroAPI::DataCopyUnAlign(outputAddrTmp, dstReg, uReg, postUpdateStride);
                }
                MicroAPI::DataCopyUnAlignPost(outputAddrTmp, uReg, 0);
                MicroAPI::Adds(idxReg, idxReg, static_cast<IdxType_>(vlSize_), mask);
            }
        }
    }
}

template <typename T, bool isPadding>
__aicore__ inline void Im2ColGatherCutNc<T, isPadding>::GatherNoPaddingVFCrossNc(
    LocalTensor<T>& input, LocalTensor<T>& output, int32_t ubFactorNC)
{
    uint32_t vfFactorNC = vlSize_ / outputHwSize_;
    uint16_t loopNum = static_cast<uint16_t>(ubFactorNC / vfFactorNC);
    uint32_t loopSize = vfFactorNC * outputHwSize_;
    uint32_t maskSize = loopSize;
    uint32_t gatherMaskSize = loopSize;
    uint32_t tailSize = static_cast<uint32_t>((ubFactorNC - vfFactorNC * loopNum) * outputHwSize_);
    uint16_t loopTailNum = tailSize != 0 ? 1 : 0;
    uint32_t tailGatherMaskSize = tailSize;
    uint32_t outputHwSize = outputHwSize_;
    uint32_t wStride = wStride_;
    uint32_t wDilation = wDilation_;
    uint32_t hStride = hStride_;
    uint32_t hDilation = hDilation_;
    uint32_t convW = convW_;
    uint32_t convH = convH_;
    uint32_t wKernelSize = wKernelSize_;
    uint32_t W = W_;
    uint32_t inputHW = H_ * W_;
    uint32_t inputInc = inputHW * vfFactorNC;

    __ubuf__ T* inputAddr = (__ubuf__ T*)input.GetPhyAddr();
    __ubuf__ T* outputAddr = (__ubuf__ T*)output.GetPhyAddr();
    __ubuf__ T* outputAddrTmp = outputAddr;
    __VEC_SCOPE__
    {
        MicroAPI::RegTensor<RangeType_> tmpIdxReg;
        MicroAPI::RegTensor<IdxType_> idxReg;
        MicroAPI::RegTensor<IdxType_> convWReg;
        MicroAPI::RegTensor<IdxType_> convHReg;
        MicroAPI::RegTensor<IdxType_> kWReg;
        MicroAPI::RegTensor<IdxType_> outputHwReg;
        MicroAPI::RegTensor<IdxType_> iConvWReg;
        MicroAPI::RegTensor<IdxType_> iConvHReg;
        MicroAPI::RegTensor<IdxType_> iKWReg; // iWReg复用
        MicroAPI::RegTensor<IdxType_> iKHReg; // iHReg复用
        MicroAPI::RegTensor<IdxType_> divReg;
        MicroAPI::RegTensor<IdxType_> mulReg;
        MicroAPI::RegTensor<IdxType_> mulReg1;
        MicroAPI::RegTensor<IdxType_> coeffReg;
        MicroAPI::RegTensor<T> dstReg;
        MicroAPI::RegTensor<T> dstRegT;
        MicroAPI::UnalignReg uReg;
        MicroAPI::MaskReg mask = MicroAPI::UpdateMask<IdxType_>(maskSize);
        MicroAPI::MaskReg gatherMask = MicroAPI::UpdateMask<CastType_>(gatherMaskSize);
        MicroAPI::MaskReg tailGatherMask = MicroAPI::UpdateMask<CastType_>(tailGatherMaskSize);

        MicroAPI::Duplicate(convWReg, IdxType_(convW));
        MicroAPI::Duplicate(convHReg, IdxType_(convH));
        MicroAPI::Duplicate(kWReg, IdxType_(wKernelSize));
        MicroAPI::Duplicate(outputHwReg, IdxType_(outputHwSize));

        MicroAPI::Arange(tmpIdxReg, 0);
        idxReg = (MicroAPI::RegTensor<IdxType_>&)tmpIdxReg;

        // idx % outputHwSize
        MicroAPI::Div(coeffReg, idxReg, outputHwReg, mask); // idx / outputHwSize
        MicroAPI::Mul(mulReg, coeffReg, outputHwReg, mask);
        MicroAPI::Sub(idxReg, idxReg, mulReg, mask);

        // iConvW = idx % convW
        MicroAPI::Div(iConvHReg, idxReg, convWReg, mask); // idx / convW
        MicroAPI::Mul(mulReg, iConvHReg, convWReg, mask);
        MicroAPI::Sub(iConvWReg, idxReg, mulReg, mask);

        // iConvH = (idx / convW) % convH
        MicroAPI::Div(divReg, iConvHReg, convHReg, mask);
        MicroAPI::Mul(mulReg, divReg, convHReg, mask);
        MicroAPI::Sub(iConvHReg, iConvHReg, mulReg, mask);

        // iKW = idx / (convW*convH) % kW
        MicroAPI::Mul(mulReg, convWReg, convHReg, mask);
        MicroAPI::Div(divReg, idxReg, mulReg, mask);
        MicroAPI::Div(iKHReg, divReg, kWReg, mask); // iKH = idx / (convW*convH) / kW
        MicroAPI::Mul(mulReg, iKHReg, kWReg, mask);
        MicroAPI::Sub(iKWReg, divReg, mulReg, mask);

        // iW = iConvW * Sw + iKW * Dw
        MicroAPI::Muls(mulReg, iConvWReg, IdxType_(wStride), mask);
        MicroAPI::Muls(mulReg1, iKWReg, IdxType_(wDilation), mask);
        MicroAPI::Add(iKWReg, mulReg, mulReg1, mask);

        // iH = iConvH * Sh + iKH * Dh
        MicroAPI::Muls(mulReg, iConvHReg, IdxType_(hStride), mask);
        MicroAPI::Muls(mulReg1, iKHReg, IdxType_(hDilation), mask);
        MicroAPI::Add(iKHReg, mulReg, mulReg1, mask);

        // inputIdx = iH * W + iW
        MicroAPI::Muls(mulReg, iKHReg, IdxType_(W), mask);
        MicroAPI::Add(idxReg, mulReg, iKWReg, mask);

        // inputIdx + 000...0111..1222..2333..3...n * inputHW
        MicroAPI::Muls(coeffReg, coeffReg, IdxType_(inputHW), mask);
        MicroAPI::Add(idxReg, idxReg, coeffReg, mask);

        for (uint16_t loopIdx = 0; loopIdx < loopNum; loopIdx++) {
            // vfFactorNC * outputHwSize_的索引拼接+gather
            MicroAPI::Gather(
                (MicroAPI::RegTensor<CastType_>&)dstReg, inputAddr + loopIdx * inputInc, idxReg, gatherMask);
            outputAddrTmp = outputAddr + loopIdx * loopSize;
            if constexpr (sizeof(T) == 1) {
                MicroAPI::Pack(dstRegT, (MicroAPI::RegTensor<CastType_>&)dstReg);
                MicroAPI::StoreUnAlign(outputAddrTmp, dstRegT, uReg, loopSize);
            } else {
                MicroAPI::StoreUnAlign(outputAddrTmp, dstReg, uReg, loopSize);
            }
        }
        MicroAPI::StoreUnAlignPost(outputAddrTmp, uReg, 0);
        // tail处理
        for (uint16_t loopIdx = 0; loopIdx < loopTailNum; loopIdx++) {
            MicroAPI::Gather(
                (MicroAPI::RegTensor<CastType_>&)dstReg, inputAddr + loopNum * inputInc, idxReg, tailGatherMask);
            outputAddrTmp = outputAddr + loopNum * loopSize;
            if constexpr (sizeof(T) == 1) {
                MicroAPI::Pack(dstRegT, (MicroAPI::RegTensor<CastType_>&)dstReg);
                MicroAPI::StoreUnAlign(outputAddrTmp, dstRegT, uReg, tailSize);
            } else {
                MicroAPI::StoreUnAlign(outputAddrTmp, dstReg, uReg, tailSize);
            }
        }
        MicroAPI::StoreUnAlignPost(outputAddrTmp, uReg, 0);
    }
}

template <typename T, bool isPadding>
__aicore__ inline void Im2ColGatherCutNc<T, isPadding>::GatherNoPaddingVFWithinNc(
    LocalTensor<T>& input, LocalTensor<T>& output, int32_t ubFactorNC)
{
    uint16_t loopNum = static_cast<uint16_t>(outputHwSize_ / vlSize_);
    uint32_t tailSize = static_cast<uint32_t>(outputHwSize_ - vlSize_ * loopNum);
    uint16_t loopTailNum = tailSize != 0 ? 1 : 0;
    uint32_t tailMaskSize = tailSize;
    uint32_t tailGatherMaskSize = tailSize;
    uint32_t postUpdateStride = static_cast<uint32_t>(outputHwSize_);
    uint32_t inputHwAlignSize = inputHwAlignSize_;
    uint32_t outputHwSize = outputHwSize_;
    uint32_t vlSize = vlSize_;
    uint32_t wStride = wStride_;
    uint32_t wDilation = wDilation_;
    uint32_t hStride = hStride_;
    uint32_t hDilation = hDilation_;
    uint32_t convW = convW_;
    uint32_t convH = convH_;
    uint32_t wKernelSize = wKernelSize_;
    uint32_t W = W_;

    uint32_t convWInc = vlSize - (vlSize / convW) * convW; // 卷积W维度的增量
    uint32_t convHInc = vlSize / convW % convH;            // 卷积H维度的基础增量
    uint32_t kWInc = vlSize / convW / convH % wKernelSize; // kernel W维度的基础增量
    uint32_t kHInc = vlSize / convW / convH / wKernelSize; // kernel H维度的基础增量

    __ubuf__ T* inputAddr = (__ubuf__ T*)input.GetPhyAddr();
    __ubuf__ T* outputAddr = (__ubuf__ T*)output.GetPhyAddr();
    __ubuf__ T* outputAddrTmp = outputAddr;
    __VEC_SCOPE__
    {
        MicroAPI::RegTensor<RangeType_> tmpIdxReg;
        MicroAPI::RegTensor<IdxType_> idxReg;
        MicroAPI::RegTensor<IdxType_> convWReg; // iWReg复用
        MicroAPI::RegTensor<IdxType_> convHReg; // iHReg复用
        MicroAPI::RegTensor<IdxType_> kWReg;
        MicroAPI::RegTensor<IdxType_> iConvWReg;
        MicroAPI::RegTensor<IdxType_> iConvHReg;
        MicroAPI::RegTensor<IdxType_> iConvWBaseReg;
        MicroAPI::RegTensor<IdxType_> iConvHBaseReg;
        MicroAPI::RegTensor<IdxType_> iKWReg;
        MicroAPI::RegTensor<IdxType_> iKHReg;
        MicroAPI::RegTensor<IdxType_> iKWBaseReg;
        MicroAPI::RegTensor<IdxType_> iKHBaseReg;
        MicroAPI::RegTensor<IdxType_> divReg;
        MicroAPI::RegTensor<IdxType_> mulReg;
        MicroAPI::RegTensor<IdxType_> mulReg1;
        MicroAPI::RegTensor<T> dstReg;
        MicroAPI::RegTensor<T> dstRegT;
        MicroAPI::UnalignReg uReg;
        MicroAPI::MaskReg mask = MicroAPI::CreateMask<IdxType_, MicroAPI::MaskPattern::ALL>();
        MicroAPI::MaskReg tailMask = MicroAPI::UpdateMask<IdxType_>(tailMaskSize);
        MicroAPI::MaskReg tailGatherMask = MicroAPI::UpdateMask<CastType_>(tailGatherMaskSize);
        MicroAPI::MaskReg selMask;

        MicroAPI::Duplicate(convWReg, IdxType_(convW));
        MicroAPI::Duplicate(convHReg, IdxType_(convH));
        MicroAPI::Duplicate(kWReg, IdxType_(wKernelSize));

        MicroAPI::Arange(tmpIdxReg, 0);
        idxReg = (MicroAPI::RegTensor<IdxType_>&)tmpIdxReg;

        // iConvW = idx % convW
        MicroAPI::Div(iConvHBaseReg, idxReg, convWReg, mask); // idx / convW
        MicroAPI::Mul(mulReg, iConvHBaseReg, convWReg, mask);
        MicroAPI::Sub(iConvWBaseReg, idxReg, mulReg, mask);

        // iConvH = (idx / convW) % convH
        MicroAPI::Div(divReg, iConvHBaseReg, convHReg, mask);
        MicroAPI::Mul(mulReg, divReg, convHReg, mask);
        MicroAPI::Sub(iConvHBaseReg, iConvHBaseReg, mulReg, mask);

        // iKW = idx / (convW*convH) % kW
        MicroAPI::Mul(mulReg, convWReg, convHReg, mask);
        MicroAPI::Div(divReg, idxReg, mulReg, mask);
        MicroAPI::Div(iKHBaseReg, divReg, kWReg, mask); // iKH = idx / (convW*convH) / kW
        MicroAPI::Mul(mulReg, iKHBaseReg, kWReg, mask);
        MicroAPI::Sub(iKWBaseReg, divReg, mulReg, mask);

        MicroAPI::RegTensor<IdxType_> zeroReg;
        MicroAPI::RegTensor<IdxType_> oneReg;
        MicroAPI::RegTensor<IdxType_> cmpReg;
        MicroAPI::Duplicate(zeroReg, 0);
        MicroAPI::Duplicate(oneReg, 1);
        for (uint16_t ncIdx = 0; ncIdx < static_cast<uint16_t>(ubFactorNC); ncIdx++) {
            MicroAPI::Move(iConvWReg, iConvWBaseReg, mask);
            MicroAPI::Move(iConvHReg, iConvHBaseReg, mask);
            MicroAPI::Move(iKWReg, iKWBaseReg, mask);
            MicroAPI::Move(iKHReg, iKHBaseReg, mask);
            for (uint16_t loopIdx = 0; loopIdx < loopNum; loopIdx++) {
                // iW = iConvW * Sw + iKW * Dw
                MicroAPI::Muls(mulReg, iConvWReg, IdxType_(wStride), mask);
                MicroAPI::Muls(mulReg1, iKWReg, IdxType_(wDilation), mask);
                MicroAPI::Add(convWReg, mulReg, mulReg1, mask);

                // iH = iConvH * Sh + iKH * Dh
                MicroAPI::Muls(mulReg, iConvHReg, IdxType_(hStride), mask);
                MicroAPI::Muls(mulReg1, iKHReg, IdxType_(hDilation), mask);
                MicroAPI::Add(convHReg, mulReg, mulReg1, mask);

                // inputIdx = iH * W + iW
                MicroAPI::Muls(mulReg, convHReg, IdxType_(W), mask);
                MicroAPI::Add(mulReg, mulReg, convWReg, mask);

                // gather
                MicroAPI::Gather(
                    (MicroAPI::RegTensor<CastType_>&)dstReg, inputAddr + ncIdx * inputHwAlignSize, mulReg, mask);
                outputAddrTmp = outputAddr + ncIdx * outputHwSize + loopIdx * vlSize;
                if constexpr (sizeof(T) == 1) {
                    MicroAPI::Pack(dstRegT, (MicroAPI::RegTensor<CastType_>&)dstReg);
                    MicroAPI::StoreUnAlign(outputAddrTmp, dstRegT, uReg, vlSize);
                } else {
                    MicroAPI::StoreUnAlign(outputAddrTmp, dstReg, uReg, vlSize);
                }

                /*   iConvWReg += convWInc
                 *   cmp = iConvWReg >= convW
                 *   iConvWReg = iConvWReg - cmp * convW
                 */
                MicroAPI::Adds(iConvWReg, iConvWReg, IdxType_(convWInc), mask);
                MicroAPI::Compares<IdxType_, CMPMODE::GE>(selMask, iConvWReg, IdxType_(convW), mask);
                MicroAPI::Select(cmpReg, oneReg, zeroReg, selMask);
                MicroAPI::Muls(mulReg, cmpReg, IdxType_(convW), mask);
                MicroAPI::Sub(iConvWReg, iConvWReg, mulReg, mask);

                /*   iConvHReg += (convHInc + cmp_w)
                 *   cmp_h = iConvHReg >= convH
                 *   iConvHReg = iConvHReg - cmp_h * convH
                 */
                MicroAPI::Adds(cmpReg, cmpReg, IdxType_(convHInc), mask);
                MicroAPI::Add(iConvHReg, iConvHReg, cmpReg, mask);
                MicroAPI::Compares<IdxType_, CMPMODE::GE>(selMask, iConvHReg, IdxType_(convH), mask);
                MicroAPI::Select(cmpReg, oneReg, zeroReg, selMask);
                MicroAPI::Muls(mulReg, cmpReg, IdxType_(convH), mask);
                MicroAPI::Sub(iConvHReg, iConvHReg, mulReg, mask);
                // iKW每循环结果
                MicroAPI::Adds(cmpReg, cmpReg, IdxType_(kWInc), mask);
                MicroAPI::Add(iKWReg, iKWReg, cmpReg, mask);
                MicroAPI::Compares<IdxType_, CMPMODE::GE>(selMask, iKWReg, IdxType_(wKernelSize), mask);
                MicroAPI::Select(cmpReg, oneReg, zeroReg, selMask);
                MicroAPI::Muls(mulReg, cmpReg, IdxType_(wKernelSize), mask);
                MicroAPI::Sub(iKWReg, iKWReg, mulReg, mask);
                // iKH每循环结果
                MicroAPI::Adds(cmpReg, cmpReg, IdxType_(kHInc), mask);
                MicroAPI::Add(iKHReg, iKHReg, cmpReg, mask);
            }
            MicroAPI::StoreUnAlignPost(outputAddrTmp, uReg, 0);
            // loopTailNum
            for (uint16_t loopIdx = 0; loopIdx < loopTailNum; loopIdx++) {
                // iW = iConvW * Sw + iKW * Dw
                MicroAPI::Muls(mulReg, iConvWReg, IdxType_(wStride), tailMask);
                MicroAPI::Muls(mulReg1, iKWReg, IdxType_(wDilation), tailMask);
                MicroAPI::Add(iKWReg, mulReg, mulReg1, tailMask);

                // iH = iConvH * Sh + iKH * Dh
                MicroAPI::Muls(mulReg, iConvHReg, IdxType_(hStride), tailMask);
                MicroAPI::Muls(mulReg1, iKHReg, IdxType_(hDilation), tailMask);
                MicroAPI::Add(iKHReg, mulReg, mulReg1, tailMask);

                // inputIdx = iH * W + iW
                MicroAPI::Muls(mulReg, iKHReg, IdxType_(W), tailMask);
                MicroAPI::Add(mulReg, mulReg, iKWReg, tailMask);

                // gather
                MicroAPI::Gather(
                    (MicroAPI::RegTensor<CastType_>&)dstReg, inputAddr + ncIdx * inputHwAlignSize, mulReg,
                    tailGatherMask);
                outputAddrTmp = outputAddr + ncIdx * outputHwSize + loopNum * vlSize;
                if constexpr (sizeof(T) == 1) {
                    MicroAPI::Pack(dstRegT, (MicroAPI::RegTensor<CastType_>&)dstReg);
                    MicroAPI::StoreUnAlign(outputAddrTmp, dstRegT, uReg, tailSize);
                } else {
                    MicroAPI::StoreUnAlign(outputAddrTmp, dstReg, uReg, tailSize);
                }
            }
            MicroAPI::StoreUnAlignPost(outputAddrTmp, uReg, 0);
        }
    }
}

template <typename T, bool isPadding>
__aicore__ inline void Im2ColGatherCutNc<T, isPadding>::GatherNoPadding(
    LocalTensor<T>& input, LocalTensor<T>& output, int32_t ubFactorNC)
{
    if (vlSize_ / outputHwSize_ > 1) {
        // VF跨NC
        GatherNoPaddingVFCrossNc(input, output, ubFactorNC);
    } else {
        // VF不跨NC
        GatherNoPaddingVFWithinNc(input, output, ubFactorNC);
    }
}

} // namespace Im2col

#endif // _IM2COL_GATHER_CUT_NC_
