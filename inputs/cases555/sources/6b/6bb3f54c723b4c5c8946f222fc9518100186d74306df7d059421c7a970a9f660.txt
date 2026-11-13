/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef IM2COL_GATHER_CUT_HW_H
#define IM2COL_GATHER_CUT_HW_H
#include "kernel_operator_list_tensor_intf.h"
#include "op_kernel/platform_util.h"
#include "op_kernel/math_util.h"
#include "im2col_tilingdata.h"

namespace Im2col {
using namespace AscendC;

/**
 * @tparam T 原始数据类型
 * @tparam U 做datacopygather的数据类型
 * @tparam Y 做vci的数据类型
 * @tparam isPadding 是否需要补pad
 */
template <typename T, typename U, typename Y, bool isPadding>
class Im2colGatherCutHw {
public:
    __aicore__ inline Im2colGatherCutHw(TPipe& pipe) : pipe_(pipe){};
    __aicore__ inline void Init(GM_ADDR x, GM_ADDR y, const Im2ColNCHWTilingData* tilingData);
    __aicore__ inline void Process();
    __aicore__ inline void ProcessPad();
    __aicore__ inline void ProcessNoPad();
    __aicore__ inline void NoPadInWInH();
    __aicore__ inline void NoPadOutWInH();
    __aicore__ inline void NoPadInWOutH();
    __aicore__ inline void NoPadOutWOutH();
    __aicore__ inline void PadInWInH();
    __aicore__ inline void PadOutWInH();
    __aicore__ inline void PadInWOutH();
    __aicore__ inline void PadOutWOutH();
    __aicore__ inline void DataCopyIn(
        int64_t blockCount, int64_t blockLen, int64_t srcOffset, int64_t srcStride, int64_t dstStride,
        LocalTensor<T>& xUb);
    __aicore__ inline void DataCopyInPad(
        int64_t blockCount, int64_t blockLen, int64_t srcOffset, int64_t dstOffset, int64_t srcStride,
        int64_t dstStride, LocalTensor<T>& xUb);
    __aicore__ inline void DataCopyOut(
        int64_t localOffset, int64_t blockCount, int64_t blockLen, int64_t dstOffset, int64_t srcStride,
        int64_t dstStride, LocalTensor<T>& yUb);
    __aicore__ inline void DataCopyOutZero(
        int64_t blockCount, int64_t blockLen, int64_t dstOffset, int64_t srcStride, int64_t dstStride);
    __aicore__ inline void CalcIdxAndGather(
        int64_t wBlockCount, int64_t hBlockCount, int64_t blockLen, int64_t wFactor, int64_t hFactor, int64_t wUbFactor,
        LocalTensor<T>& xUb);
    __aicore__ inline void CalcIdxAndGatherPad(
        int64_t wBlockCount, int64_t hBlockCount, int64_t blockLen, int64_t wFactor, int64_t hFactor,
        LocalTensor<T>& xUb);
    __aicore__ inline void CalcOneUBIdxAndGather(
        int64_t wBlockCount, int64_t hBlockCount, int64_t blockLen, int64_t wFactor, int64_t hFactor,
        LocalTensor<T>& xUb);
    __aicore__ inline void IsDataCopyPad(int64_t wBlockCount, int64_t hBlockCount, int64_t blockLen);

private:
    __aicore__ inline __gm__ T* GetTensorAddr(int64_t index);

private:
    TPipe& pipe_;
    constexpr static int32_t BUFFER_NUM = 2;
    constexpr static int64_t BLOCK_ELENUM = Ops::Base::GetUbBlockSize() / sizeof(T);
    constexpr static int64_t VL_LEN = Ops::Base::GetVRegSize();
    constexpr static int32_t DATA_COPY_GATHER = 128; // DataCopyGather并行度
    const Im2ColNCHWTilingData* tilingData_;
    const Im2ColInputInfo* inputInfo_;
    TQue<QuePosition::VECIN, 1> inQueueX_;
    TQue<QuePosition::VECOUT, 1> outQueueY_;
    GlobalTensor<T> xGm_;
    GlobalTensor<T> yGm_;
    LocalTensor<T> yLocal_;
    LocalTensor<T> yUb_;

    int64_t inWOffset_ = 0;
    int64_t inHOffset_ = 0;
    int64_t inWOffsetPad_ = 0;
    int64_t inHOffsetPad_ = 0;
    int64_t outWOffset_ = 0;
    int64_t outHOffset_ = 0;
    int64_t batchOffset_ = 0;
    int32_t blockLen_ = 0;   // burstLen
    int64_t batchSize_ = 0;  // NC的大小
    int64_t ubCount_ = 0;    // 输出单个HW切的UB块数
    int64_t kernelOutW_ = 0; // 单kernel的W方向上有效elem个数
    int64_t kernelNumW_ = 0; // 输入W方向上卷积核个数
    int64_t kernelNumH_ = 0; // 输入H方向上卷积核个数
    int32_t ubLineW_ = 0;    // UB内处理的W行数
    int32_t ubLineH_ = 0;    // UB内处理的H行数
    int32_t ubFactorW_ = 0;  // W方向上ubFactor
    int32_t ubFactorH_ = 0;  // H方向上ubFactor
    int64_t outW_ = 0;
    int64_t outH_ = 0;
    int64_t inKernelW_ = 0;
    int64_t inKernelH_ = 0;
    int64_t xGmOffset_ = 0;
    int64_t xGmOffsetPad_ = 0;
    int64_t yGmOffset_ = 0;
    int64_t dtypeSize_ = sizeof(T);
    int32_t isPad_ = 0;
    int64_t wPadTop_ = 0; // 当前UB输入W方向上TOP pad大小
    int64_t hPadTop_ = 0; // 当前UB输入H方向上TOP pad大小
    int32_t maxGatherNum_ = DATA_COPY_GATHER / sizeof(T);
    int64_t blockFactor_ = 0;
    int64_t blockCount_ = 0;
    int64_t rectAnglesPerCore_ = 0;

    int32_t uVL_ = Ops::Base::GetVRegSize() / sizeof(U);
    int32_t blockIdx_ = 0;
    int32_t coreNum_ = 0;
    DataCopyExtParams copyInParam_{0, 0, 0, 0, 0};
    DataCopyPadExtParams<T> padParam_{false, 0, 0, 0};
    DataCopyExtParams copyOutParam_{0, 0, 0, 0, 0};
    LoopModeParams loopMode_{1, 1, 0, 0, 0, 0};
};

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::Init(
    GM_ADDR x, GM_ADDR y, const Im2ColNCHWTilingData* tilingData)
{
    blockIdx_ = GetBlockIdx();
    tilingData_ = tilingData;
    inputInfo_ = &tilingData_->input;
    ubCount_ = tilingData_->outHWrectAngles;
    kernelNumW_ = tilingData_->convKernelNumInWidth;
    kernelNumH_ = tilingData_->convKernelNumInHeight;
    blockLen_ = tilingData_->w4ubFactorW;
    batchSize_ = inputInfo_->N * inputInfo_->C;
    kernelOutW_ = Ops::Base::CeilDiv(inputInfo_->wKernelSize, inputInfo_->wDilation);
    ubLineW_ = tilingData_->lines4ubFactorW;
    ubLineH_ = tilingData_->lines4ubFactorH;
    outW_ = tilingData_->convKernelNumInWidth * tilingData_->convKernelNumInHeight;
    outH_ = inputInfo_->hKernelSize * inputInfo_->wKernelSize;
    ubFactorH_ = tilingData_->ubFactorH;
    ubFactorW_ = tilingData_->ubFactorW;

    int64_t inputSize = tilingData_->inputBufferSize;
    int64_t outputSize = tilingData_->outputBufferSize;
    xGm_.SetGlobalBuffer((__gm__ T*)x);
    yGm_.SetGlobalBuffer((__gm__ T*)y);
    pipe_.InitBuffer(inQueueX_, BUFFER_NUM, inputSize);
    pipe_.InitBuffer(outQueueY_, BUFFER_NUM, outputSize);
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::DataCopyIn(
    int64_t blockCount, int64_t blockLen, int64_t srcOffset, int64_t srcStride, int64_t dstStride, LocalTensor<T>& xUb)
{
    SetLoopModePara(loopMode_, DataCopyMVType::OUT_TO_UB);
    copyInParam_.blockCount = blockCount;
    copyInParam_.blockLen = blockLen * dtypeSize_;
    copyInParam_.srcStride = srcStride * dtypeSize_;
    copyInParam_.dstStride = dstStride / BLOCK_ELENUM;
    DataCopyPad(xUb, xGm_[srcOffset], copyInParam_, padParam_);
    ResetLoopModePara(DataCopyMVType::OUT_TO_UB);
    inQueueX_.EnQue(xUb);
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::DataCopyInPad(
    int64_t blockCount, int64_t blockLen, int64_t srcOffset, int64_t dstOffset, int64_t srcStride, int64_t dstStride,
    LocalTensor<T>& xUb)
{
    copyInParam_.blockCount = blockCount;
    copyInParam_.blockLen = blockLen * dtypeSize_;
    copyInParam_.srcStride = srcStride * dtypeSize_;
    copyInParam_.dstStride = dstStride / BLOCK_ELENUM;
    DataCopyPad(xUb[dstOffset], xGm_[srcOffset], copyInParam_, padParam_);
    inQueueX_.EnQue(xUb);
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::IsDataCopyPad(
    int64_t wBlockCount, int64_t hBlockCount, int64_t blockLen)
{
    int64_t srcWOffsetPad = inWOffsetPad_;
    int64_t dstWOffsetPad = 0;
    int64_t srcHOffsetPad = inHOffsetPad_;
    int64_t dstHOffsetPad = 0;
    int64_t gmOffset = 0;
    int64_t ubOffset = 0;
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::DataCopyOut(
    int64_t localOffset, int64_t blockCount, int64_t blockLen, int64_t dstOffset, int64_t srcStride, int64_t dstStride,
    LocalTensor<T>& yUb)
{
    copyOutParam_.blockCount = blockCount;
    copyOutParam_.blockLen = blockLen * dtypeSize_;
    copyOutParam_.srcStride = srcStride / BLOCK_ELENUM;
    copyOutParam_.dstStride = dstStride * dtypeSize_;
    DataCopyPad(yGm_[dstOffset], yUb[localOffset], copyOutParam_);
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::DataCopyOutZero(
    int64_t blockCount, int64_t blockLen, int64_t dstOffset, int64_t srcStride, int64_t dstStride)
{
    yLocal_ = outQueueY_.AllocTensor<T>();
    int64_t blockLenAlign = (blockLen + BLOCK_ELENUM - 1) / BLOCK_ELENUM * BLOCK_ELENUM;
    int32_t count = blockLenAlign * blockCount;
    Duplicate(yLocal_, static_cast<T>(0), count);
    outQueueY_.EnQue(yLocal_);
    LocalTensor<T> yUb = outQueueY_.DeQue<T>();
    copyOutParam_.blockCount = blockCount;
    copyOutParam_.blockLen = blockLen * dtypeSize_;
    copyOutParam_.srcStride = srcStride / BLOCK_ELENUM;
    copyOutParam_.dstStride = dstStride * dtypeSize_;
    DataCopyPad(yGm_[dstOffset], yUb, copyOutParam_);
    outQueueY_.FreeTensor(yUb);
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::CalcOneUBIdxAndGather(
    int64_t wBlockCount, int64_t hBlockCount, int64_t blockLen, int64_t wFactor, int64_t hFactor, LocalTensor<T>& xUb)
{
    int64_t blockLenAlign = (blockLen + BLOCK_ELENUM - 1) / BLOCK_ELENUM * BLOCK_ELENUM;
    int64_t wStride = inputInfo_->wStride;
    int64_t wUbFactor = ubFactorW_;
    uint16_t loop1 = uVL_ / wUbFactor;
    uint16_t loop2 = loop1 / hFactor;
    uint32_t maskSize = uVL_;
    uint32_t count = wUbFactor / wFactor;
    int64_t hwAlign = hBlockCount * blockLenAlign;
    int64_t dilation = inputInfo_->wDilation;
    int64_t stride = 0;
    yLocal_ = outQueueY_.AllocTensor<T>();
    __ubuf__ T* srcPtr = (__ubuf__ T*)xUb.GetPhyAddr();
    __ubuf__ U* dstPtrU = (__ubuf__ U*)yLocal_.GetPhyAddr();
    __ubuf__ T* dstPtrT = (__ubuf__ T*)yLocal_.GetPhyAddr();

    if (loop2 == 0) {
        uint16_t loop = hFactor / loop1;
        uint16_t tail = (hFactor - loop1 * loop) * wUbFactor;
        uint16_t loopH = hBlockCount;
        uint32_t maskTailSize = tail;
        uint32_t factor = loop1 * wUbFactor;
        uint32_t maskLoop = factor;
        uint32_t strideH = blockLenAlign;
        stride = dilation * loop1;
        __VEC_SCOPE__
        {
            AscendC::MicroAPI::RegTensor<Y> indexReg;
            AscendC::MicroAPI::RegTensor<U> tmp;
            AscendC::MicroAPI::RegTensor<U> tmp1;
            AscendC::MicroAPI::RegTensor<U> addReg;
            AscendC::MicroAPI::RegTensor<U> addReg1;
            AscendC::MicroAPI::RegTensor<U> subReg;
            AscendC::MicroAPI::RegTensor<U> subReg1;
            AscendC::MicroAPI::RegTensor<U> divReg;
            AscendC::MicroAPI::RegTensor<U> divReg2;
            AscendC::MicroAPI::RegTensor<U> mulsReg;
            AscendC::MicroAPI::RegTensor<U> mulsReg0;
            AscendC::MicroAPI::RegTensor<U> mulsReg1;
            AscendC::MicroAPI::RegTensor<U> mulsReg2;
            AscendC::MicroAPI::RegTensor<U> mulsReg3;
            AscendC::MicroAPI::RegTensor<U> dstReg;
            AscendC::MicroAPI::RegTensor<U> movReg;
            AscendC::MicroAPI::RegTensor<T> dstRegT;
            AscendC::MicroAPI::UnalignReg uDst;
            AscendC::MicroAPI::MaskReg mask;
            AscendC::MicroAPI::MaskReg maskOut;
            AscendC::MicroAPI::MaskReg maskTail;

            mask = AscendC::MicroAPI::UpdateMask<U>(maskSize);
            maskOut = AscendC::MicroAPI::UpdateMask<U>(maskLoop);
            maskTail = AscendC::MicroAPI::UpdateMask<U>(maskTailSize);
            Y startIdx = (Y)0;
            AscendC::MicroAPI::Arange(indexReg, startIdx);
            AscendC::MicroAPI::Duplicate(tmp, (U)wFactor, mask);
            AscendC::MicroAPI::Duplicate(tmp1, (U)wUbFactor, mask);
            AscendC::MicroAPI::Div(divReg, (AscendC::MicroAPI::RegTensor<U>&)indexReg, tmp, mask);
            AscendC::MicroAPI::Div(divReg2, (AscendC::MicroAPI::RegTensor<U>&)indexReg, tmp1, mask);
            AscendC::MicroAPI::Muls(mulsReg0, divReg2, (U)count, mask);
            AscendC::MicroAPI::Muls(mulsReg, divReg, (U)wFactor, mask);
            AscendC::MicroAPI::Muls(mulsReg1, divReg2, (U)dilation, mask);
            AscendC::MicroAPI::Sub(subReg, (AscendC::MicroAPI::RegTensor<U>&)indexReg, mulsReg, mask);
            AscendC::MicroAPI::Sub(subReg1, divReg, mulsReg0, mask);
            AscendC::MicroAPI::Muls(mulsReg2, subReg, (U)wStride, mask);
            AscendC::MicroAPI::Muls(mulsReg3, subReg1, (U)hwAlign, mask);
            AscendC::MicroAPI::Add(addReg, mulsReg3, mulsReg2, mask);
            AscendC::MicroAPI::Add(addReg1, addReg, mulsReg1, mask);
            AscendC::MicroAPI::Move(movReg, addReg1);
            for (uint16_t j = 0; j < loopH; j++) {
                for (uint16_t i = 0; i < loop; i++) {
                    AscendC::MicroAPI::Gather(dstReg, srcPtr, addReg1, maskOut);
                    // Copy out
                    if constexpr (sizeof(T) == sizeof(int8_t)) {
                        // Convert B16 to B8
                        AscendC::MicroAPI::Pack(dstRegT, dstReg);
                        AscendC::MicroAPI::DataCopyUnAlign(dstPtrT, dstRegT, uDst, factor);
                        AscendC::MicroAPI::DataCopyUnAlignPost(dstPtrT, uDst, 0);
                    } else {
                        AscendC::MicroAPI::DataCopyUnAlign(dstPtrU, dstReg, uDst, factor);
                        AscendC::MicroAPI::DataCopyUnAlignPost(dstPtrU, uDst, 0);
                    }
                    AscendC::MicroAPI::Adds(addReg1, addReg1, (U)stride, mask);
                }
                AscendC::MicroAPI::Gather(dstReg, srcPtr, addReg1, maskTail);
                if constexpr (sizeof(T) == sizeof(int8_t)) {
                    // Convert B16 to B8
                    AscendC::MicroAPI::Pack(dstRegT, dstReg);
                    AscendC::MicroAPI::DataCopyUnAlign(dstPtrT, dstRegT, uDst, tail);
                    AscendC::MicroAPI::DataCopyUnAlignPost(dstPtrT, uDst, 0);
                } else {
                    AscendC::MicroAPI::DataCopyUnAlign(dstPtrU, dstReg, uDst, tail);
                    AscendC::MicroAPI::DataCopyUnAlignPost(dstPtrU, uDst, 0);
                }
                AscendC::MicroAPI::Adds(movReg, movReg, (U)strideH, mask);
                AscendC::MicroAPI::Move(addReg1, movReg);
            }
        }
    } else {
        uint16_t loopH = hBlockCount / loop2;
        uint16_t tail = hBlockCount - loopH * loop2;
        uint32_t maskTail = tail * hFactor * wUbFactor;
        uint32_t tailFactor = maskTail;
        uint32_t factor = loop2 * hFactor * wUbFactor;
        maskSize = factor;
        stride = blockLenAlign * loop2;
        uint32_t strideH = blockLenAlign;
        uint32_t hwFactor = hFactor * wUbFactor;

        __VEC_SCOPE__
        {
            AscendC::MicroAPI::RegTensor<Y> indexReg;
            AscendC::MicroAPI::RegTensor<U> tmp;
            AscendC::MicroAPI::RegTensor<U> tmp1;
            AscendC::MicroAPI::RegTensor<U> addReg;
            AscendC::MicroAPI::RegTensor<U> addReg1;
            AscendC::MicroAPI::RegTensor<U> addReg2;
            AscendC::MicroAPI::RegTensor<U> hwReg;
            AscendC::MicroAPI::RegTensor<U> subReg;
            AscendC::MicroAPI::RegTensor<U> subReg1;
            AscendC::MicroAPI::RegTensor<U> subReg2;
            AscendC::MicroAPI::RegTensor<U> divReg;
            AscendC::MicroAPI::RegTensor<U> divReg1;
            AscendC::MicroAPI::RegTensor<U> divReg2;
            AscendC::MicroAPI::RegTensor<U> divReg3;
            AscendC::MicroAPI::RegTensor<U> mulsReg;
            AscendC::MicroAPI::RegTensor<U> mulsReg0;
            AscendC::MicroAPI::RegTensor<U> mulsReg1;
            AscendC::MicroAPI::RegTensor<U> mulsReg2;
            AscendC::MicroAPI::RegTensor<U> mulsReg4;
            AscendC::MicroAPI::RegTensor<U> mulsReg5;
            AscendC::MicroAPI::RegTensor<U> mulsReg6;
            AscendC::MicroAPI::RegTensor<U> dstReg;
            AscendC::MicroAPI::RegTensor<T> dstRegT;
            AscendC::MicroAPI::UnalignReg uDst;
            AscendC::MicroAPI::MaskReg mask;
            AscendC::MicroAPI::MaskReg maskOutTail;

            mask = AscendC::MicroAPI::UpdateMask<U>(maskSize);
            maskOutTail = AscendC::MicroAPI::UpdateMask<U>(maskTail);
            Y startIdx = (Y)0;
            AscendC::MicroAPI::Arange(indexReg, startIdx);
            AscendC::MicroAPI::Duplicate(hwReg, (U)hwFactor, mask);
            AscendC::MicroAPI::Duplicate(tmp, (U)wFactor, mask);
            AscendC::MicroAPI::Duplicate(tmp1, (U)wUbFactor, mask);
            AscendC::MicroAPI::Div(divReg, (AscendC::MicroAPI::RegTensor<U>&)indexReg, hwReg, mask);
            AscendC::MicroAPI::Div(divReg1, (AscendC::MicroAPI::RegTensor<U>&)indexReg, tmp1, mask);
            AscendC::MicroAPI::Div(divReg2, (AscendC::MicroAPI::RegTensor<U>&)indexReg, tmp, mask);
            AscendC::MicroAPI::Muls(mulsReg, divReg2, (U)wFactor, mask);
            AscendC::MicroAPI::Muls(mulsReg0, divReg1, (U)count, mask);
            AscendC::MicroAPI::Sub(subReg, (AscendC::MicroAPI::RegTensor<U>&)indexReg, mulsReg, mask);
            AscendC::MicroAPI::Sub(subReg1, divReg2, mulsReg0, mask);
            AscendC::MicroAPI::Muls(mulsReg2, subReg, (U)wStride, mask);
            AscendC::MicroAPI::Muls(mulsReg4, divReg, (U)strideH, mask);
            AscendC::MicroAPI::Muls(mulsReg5, subReg1, (U)hwAlign, mask);
            AscendC::MicroAPI::Muls(mulsReg6, divReg, (U)hFactor, mask);
            AscendC::MicroAPI::Sub(subReg2, divReg1, mulsReg6, mask);
            AscendC::MicroAPI::Muls(mulsReg1, subReg2, (U)dilation, mask);
            AscendC::MicroAPI::Add(addReg, mulsReg5, mulsReg2, mask);
            AscendC::MicroAPI::Add(addReg1, addReg, mulsReg1, mask);
            AscendC::MicroAPI::Add(addReg2, addReg1, mulsReg4, mask);

            for (uint16_t i = 0; i < loopH; i++) {
                AscendC::MicroAPI::Gather(dstReg, srcPtr, addReg2, mask);
                // Copy out
                if constexpr (sizeof(T) == sizeof(int8_t)) {
                    // Convert B16 to B8
                    AscendC::MicroAPI::Pack(dstRegT, dstReg);
                    AscendC::MicroAPI::DataCopyUnAlign(dstPtrT, dstRegT, uDst, factor);
                    AscendC::MicroAPI::DataCopyUnAlignPost(dstPtrT, uDst, 0);
                } else {
                    AscendC::MicroAPI::DataCopyUnAlign(dstPtrU, dstReg, uDst, factor);
                    AscendC::MicroAPI::DataCopyUnAlignPost(dstPtrU, uDst, 0);
                }
                AscendC::MicroAPI::Adds(addReg2, addReg2, (U)stride, mask);
            }
            AscendC::MicroAPI::Gather(dstReg, srcPtr, addReg2, maskOutTail);
            if constexpr (sizeof(T) == sizeof(int8_t)) {
                // Convert B16 to B8
                AscendC::MicroAPI::Pack(dstRegT, dstReg);
                AscendC::MicroAPI::DataCopyUnAlign(dstPtrT, dstRegT, uDst, tailFactor);
                AscendC::MicroAPI::DataCopyUnAlignPost(dstPtrT, uDst, 0);
            } else {
                AscendC::MicroAPI::DataCopyUnAlign(dstPtrU, dstReg, uDst, tailFactor);
                AscendC::MicroAPI::DataCopyUnAlignPost(dstPtrU, uDst, 0);
            }
        }
    }
    outQueueY_.EnQue(yLocal_);
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::CalcIdxAndGatherPad(
    int64_t wBlockCount, int64_t hBlockCount, int64_t blockLen, int64_t wFactor, int64_t hFactor, LocalTensor<T>& xUb)
{
    int64_t blockLenAlign = (blockLen + BLOCK_ELENUM - 1) / BLOCK_ELENUM * BLOCK_ELENUM;
    int64_t wStride = inputInfo_->wStride;
    uint32_t wUbFactor = ubFactorW_;
    uint16_t loop = hBlockCount;
    uint16_t loop1 = hFactor;
    uint32_t maskSize = blockLen;
    int64_t hwAlign = hBlockCount * blockLenAlign;
    int64_t dilation = inputInfo_->wDilation;
    int64_t stride = blockLenAlign - dilation * loop1;
    yLocal_ = outQueueY_.AllocTensor<T>();
    __ubuf__ T* srcPtr = (__ubuf__ T*)xUb.GetPhyAddr();
    __ubuf__ U* dstPtrU = (__ubuf__ U*)yLocal_.GetPhyAddr();
    __ubuf__ T* dstPtrT = (__ubuf__ T*)yLocal_.GetPhyAddr();
    __VEC_SCOPE__
    {
        AscendC::MicroAPI::RegTensor<Y> indexReg;
        AscendC::MicroAPI::RegTensor<U> tmp;
        AscendC::MicroAPI::RegTensor<U> tmp1;
        AscendC::MicroAPI::RegTensor<U> tmp2;
        AscendC::MicroAPI::RegTensor<U> addReg;
        AscendC::MicroAPI::RegTensor<U> addReg1;
        AscendC::MicroAPI::RegTensor<U> kernelReg;
        AscendC::MicroAPI::RegTensor<U> subReg;
        AscendC::MicroAPI::RegTensor<U> divReg;
        AscendC::MicroAPI::RegTensor<U> divReg2;
        AscendC::MicroAPI::RegTensor<U> mulsReg;
        AscendC::MicroAPI::RegTensor<U> mulsReg2;
        AscendC::MicroAPI::RegTensor<U> mulsReg3;
        AscendC::MicroAPI::RegTensor<U> mulReg;
        AscendC::MicroAPI::RegTensor<U> dstReg;
        AscendC::MicroAPI::RegTensor<U> wReg;
        AscendC::MicroAPI::RegTensor<U> hReg;
        AscendC::MicroAPI::RegTensor<T> dstRegT;
        AscendC::MicroAPI::UnalignReg uDst;
        AscendC::MicroAPI::MaskReg mask;
        AscendC::MicroAPI::MaskReg maskOut;
        AscendC::MicroAPI::MaskReg maskWTop;
        AscendC::MicroAPI::MaskReg maskWBot;
        AscendC::MicroAPI::MaskReg maskHTop;
        AscendC::MicroAPI::MaskReg maskHBot;

        mask = AscendC::MicroAPI::UpdateMask<U>(maskSize);
        maskOut = AscendC::MicroAPI::UpdateMask<U>(wUbFactor);
        Y startIdx = (Y)0;
        AscendC::MicroAPI::Arange(indexReg, startIdx);
        AscendC::MicroAPI::Duplicate(kernelReg, (U)hFactor, mask);
        AscendC::MicroAPI::Duplicate(tmp, (U)wFactor, mask);
        AscendC::MicroAPI::Div(divReg, (AscendC::MicroAPI::RegTensor<U>&)indexReg, kernelReg, mask);
        AscendC::MicroAPI::Div(divReg2, (AscendC::MicroAPI::RegTensor<U>&)indexReg, tmp, mask);
        AscendC::MicroAPI::Muls(mulsReg, divReg, (U)wStride, mask);
        AscendC::MicroAPI::Muls(mulsReg2, divReg, (U)hFactor, mask);
        AscendC::MicroAPI::Muls(mulsReg3, divReg2, (U)hwAlign, mask);
        AscendC::MicroAPI::Sub(subReg, (AscendC::MicroAPI::RegTensor<U>&)indexReg, mulsReg2, mask);
        AscendC::MicroAPI::Mul(mulReg, subReg, kernelReg, mask);
        AscendC::MicroAPI::Add(addReg, mulReg, mulsReg, mask);
        AscendC::MicroAPI::Add(addReg1, addReg, mulsReg3, mask);
        AscendC::MicroAPI::Duplicate(tmp, (U)blockLen, mask);

        for (uint16_t i = 0; i < loop; i++) {
            for (uint16_t j = 0; j < loop1; j++) {
                AscendC::MicroAPI::Gather(dstReg, srcPtr, addReg1, maskOut);
                // Copy out
                if constexpr (sizeof(T) == sizeof(int8_t)) {
                    // Convert B16 to B8
                    AscendC::MicroAPI::Pack(dstRegT, dstReg);
                    AscendC::MicroAPI::StoreAlign(dstPtrT, dstRegT, maskOut);
                } else {
                    AscendC::MicroAPI::StoreAlign(dstPtrU, dstReg, maskOut);
                }
                AscendC::MicroAPI::Adds(addReg1, addReg1, (U)dilation, mask);
            }
            AscendC::MicroAPI::Adds(addReg1, addReg1, (U)stride, mask);
        }
    }
    outQueueY_.EnQue(yLocal_);
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::CalcIdxAndGather(
    int64_t wBlockCount, int64_t hBlockCount, int64_t blockLen, int64_t wFactor, int64_t hFactor, int64_t wUbFactor,
    LocalTensor<T>& xUb)
{
    if (isPad_) {
        CalcIdxAndGatherPad(wBlockCount, hBlockCount, blockLen, wFactor, hFactor, xUb);
    } else {
        int64_t blockLenAlign = (blockLen + BLOCK_ELENUM - 1) / BLOCK_ELENUM * BLOCK_ELENUM;
        int64_t wStride = inputInfo_->wStride;
        uint32_t ubFactor = wUbFactor;
        uint32_t offset = (wUbFactor + BLOCK_ELENUM - 1) / BLOCK_ELENUM * BLOCK_ELENUM;
        uint16_t loop = hBlockCount;
        uint16_t loop1 = hFactor;
        uint32_t maskSize = wUbFactor;
        uint32_t maskB8 = wUbFactor;
        int64_t hwAlign = hBlockCount * blockLenAlign;
        int64_t dilation = inputInfo_->wDilation;
        int64_t stride = blockLenAlign - dilation * loop1;
        yLocal_ = outQueueY_.AllocTensor<T>();
        __ubuf__ T* srcPtr = (__ubuf__ T*)xUb.GetPhyAddr();
        __ubuf__ U* dstPtrU = (__ubuf__ U*)yLocal_.GetPhyAddr();
        __ubuf__ T* dstPtrT = (__ubuf__ T*)yLocal_.GetPhyAddr();
        __VEC_SCOPE__
        {
            AscendC::MicroAPI::RegTensor<Y> indexReg;
            AscendC::MicroAPI::RegTensor<U> tmp;
            AscendC::MicroAPI::RegTensor<U> addReg;
            AscendC::MicroAPI::RegTensor<U> subReg;
            AscendC::MicroAPI::RegTensor<U> divReg;
            AscendC::MicroAPI::RegTensor<U> mulsReg;
            AscendC::MicroAPI::RegTensor<U> mulsReg2;
            AscendC::MicroAPI::RegTensor<U> mulsReg3;
            AscendC::MicroAPI::RegTensor<U> dstReg;
            AscendC::MicroAPI::RegTensor<T> dstRegT;
            AscendC::MicroAPI::UnalignReg uDst;
            AscendC::MicroAPI::MaskReg mask;
            AscendC::MicroAPI::MaskReg maskOut;
            AscendC::MicroAPI::MaskReg maskT;

            mask = AscendC::MicroAPI::UpdateMask<U>(maskSize);
            maskOut = AscendC::MicroAPI::UpdateMask<U>(ubFactor);
            maskT = AscendC::MicroAPI::UpdateMask<T>(maskB8);
            Y startIdx = (Y)0;
            AscendC::MicroAPI::Arange(indexReg, startIdx);
            AscendC::MicroAPI::Duplicate(tmp, (U)wFactor, mask);
            AscendC::MicroAPI::Div(divReg, (AscendC::MicroAPI::RegTensor<U>&)indexReg, tmp, mask);
            AscendC::MicroAPI::Muls(mulsReg, divReg, (U)wFactor, mask);
            AscendC::MicroAPI::Sub(subReg, (AscendC::MicroAPI::RegTensor<U>&)indexReg, mulsReg, mask);
            AscendC::MicroAPI::Muls(mulsReg2, subReg, (U)wStride, mask);
            AscendC::MicroAPI::Muls(mulsReg3, divReg, (U)hwAlign, mask);
            AscendC::MicroAPI::Add(addReg, mulsReg3, mulsReg2, mask);
            for (uint16_t i = 0; i < loop; i++) {
                for (uint16_t j = 0; j < loop1; j++) {
                    AscendC::MicroAPI::Gather(dstReg, srcPtr, addReg, maskOut);
                    // Copy out
                    if constexpr (sizeof(T) == sizeof(int8_t)) {
                        // Convert B16 to B8
                        AscendC::MicroAPI::Pack(dstRegT, dstReg);
                        AscendC::MicroAPI::StoreAlign<T, MicroAPI::PostLiteral::POST_MODE_UPDATE>(
                            dstPtrT, dstRegT, offset, maskT);
                    } else {
                        AscendC::MicroAPI::StoreAlign<U, MicroAPI::PostLiteral::POST_MODE_UPDATE>(
                            dstPtrU, dstReg, offset, maskOut);
                    }
                    AscendC::MicroAPI::Adds(addReg, addReg, (U)dilation, mask);
                }
                AscendC::MicroAPI::Adds(addReg, addReg, (U)stride, mask);
            }
        }
        outQueueY_.EnQue(yLocal_);
    }
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::NoPadInWInH()
{
    int32_t ubFactorH = tilingData_->ubFactorH;
    int32_t ubFactorW = tilingData_->ubFactorW;
    int32_t procUbCount = rectAnglesPerCore_;
    int64_t perMatrixWUbCnt = Ops::Base::CeilDiv(kernelNumW_, static_cast<int64_t>(ubFactorW));
    int64_t perMatrixHUbCnt = Ops::Base::CeilDiv(inputInfo_->wKernelSize, static_cast<int64_t>(ubFactorH));
    int64_t wUbCount = perMatrixWUbCnt * kernelNumH_;
    int64_t hUbCount = perMatrixHUbCnt * inputInfo_->hKernelSize;
    int64_t blockUbCount = tilingData_->rectAnglesPerCore * blockIdx_;
    int64_t ncIdx = blockUbCount / tilingData_->outHWrectAngles;
    int64_t hUbCountOffset = (blockUbCount - ncIdx * tilingData_->outHWrectAngles) / wUbCount;
    int64_t wUbCountOffset = blockUbCount - ncIdx * tilingData_->outHWrectAngles - hUbCountOffset * wUbCount;
    int64_t ubCountOffset = 0;      // 当前HW的ub块索引
    int64_t matrixWUbCntOffset = 0; // 当前HW的矩阵块W方向索引
    int64_t matrixHUbCntOffset = 0; // 当前HW的矩阵块H方向索引
    int64_t nowMatrixWUbOffset = 0; // 矩阵块内W方向UB索引
    int64_t nowMatrixHUbOffset = 0; // 矩阵块内H方向UB索引
    inKernelW_ = inputInfo_->W - (kernelNumW_ - 1) * inputInfo_->wStride;
    inKernelH_ = inputInfo_->H - (kernelNumH_ - 1) * inputInfo_->hStride;

    while (procUbCount > 0) {
        ubFactorW = tilingData_->ubFactorW;
        ubFactorH = tilingData_->ubFactorH;
        ubCountOffset = hUbCountOffset * wUbCount + wUbCountOffset;
        matrixWUbCntOffset = wUbCountOffset / perMatrixWUbCnt;
        matrixHUbCntOffset = hUbCountOffset / perMatrixHUbCnt;
        nowMatrixWUbOffset = (wUbCountOffset - matrixWUbCntOffset * perMatrixWUbCnt) * ubFactorW;
        nowMatrixHUbOffset = (hUbCountOffset - matrixHUbCntOffset * perMatrixHUbCnt) * ubFactorH;
        outWOffset_ = matrixWUbCntOffset * kernelNumW_ + nowMatrixWUbOffset;
        outHOffset_ = matrixHUbCntOffset * inputInfo_->wKernelSize + nowMatrixHUbOffset;
        inWOffset_ = (outWOffset_ - outWOffset_ / kernelNumW_ * kernelNumW_) * inputInfo_->wStride +
                     nowMatrixHUbOffset * inputInfo_->wDilation;
        inHOffset_ = outWOffset_ / kernelNumW_ * inputInfo_->hStride +
                     outHOffset_ / inputInfo_->wKernelSize * inputInfo_->hDilation;
        xGmOffset_ = ncIdx * inputInfo_->H * inputInfo_->W + inHOffset_ * inputInfo_->W + inWOffset_;
        yGmOffset_ = ncIdx * outW_ * outH_ + outHOffset_ * outW_ + outWOffset_;
        int64_t blockLen = (inputInfo_->W - inWOffset_) >= tilingData_->w4ubFactorW ? tilingData_->w4ubFactorW :
                                                                                      (inputInfo_->W - inWOffset_);
        ubFactorW =
            nowMatrixWUbOffset == (perMatrixWUbCnt - 1) * ubFactorW ? kernelNumW_ - nowMatrixWUbOffset : ubFactorW;
        ubFactorH = nowMatrixHUbOffset == (perMatrixHUbCnt - 1) * ubFactorH ?
                        inputInfo_->wKernelSize - nowMatrixHUbOffset :
                        ubFactorH;
        int64_t srcStride = 0;
        int64_t dstStride = 0;
        LocalTensor<T> xUb = inQueueX_.AllocTensor<T>();
        DataCopyIn(1, blockLen, xGmOffset_, srcStride, dstStride, xUb);
        LocalTensor<T> srcUb = inQueueX_.DeQue<T>();
        CalcIdxAndGather(1, 1, blockLen, ubFactorW, ubFactorH, ubFactorW, srcUb);
        LocalTensor<T> yUb = outQueueY_.DeQue<T>();
        DataCopyOut(0, ubFactorH, ubFactorW, yGmOffset_, 0, outW_ - ubFactorW, yUb);
        if (wUbCountOffset == wUbCount - 1) {
            wUbCountOffset = 0;
            hUbCountOffset = hUbCountOffset == hUbCount - 1 ? 0 : hUbCountOffset + 1;
            ncIdx = hUbCountOffset == 0 ? ncIdx + 1 : ncIdx;
        } else {
            wUbCountOffset++;
        }
        procUbCount--;
        outQueueY_.FreeTensor(yUb);
        inQueueX_.FreeTensor(srcUb);
    }
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::NoPadOutWInH()
{
    int32_t ubFactorH = tilingData_->ubFactorH;
    int32_t ubFactorW = tilingData_->ubFactorW;
    int32_t procUbCount = rectAnglesPerCore_;
    int64_t perMatrixHUbCnt = Ops::Base::CeilDiv(inputInfo_->wKernelSize, static_cast<int64_t>(ubFactorH));
    int64_t perWUbMatrixCnt = Ops::Base::CeilDiv(static_cast<int64_t>(ubFactorW), kernelNumW_);
    int64_t wUbCount = Ops::Base::CeilDiv(outW_, static_cast<int64_t>(ubFactorW));
    int64_t hUbCount = perMatrixHUbCnt * inputInfo_->hKernelSize;
    int64_t blockUbCount = tilingData_->rectAnglesPerCore * blockIdx_;
    int64_t ncIdx = blockUbCount / tilingData_->outHWrectAngles;
    int64_t hUbCountOffset = (blockUbCount - ncIdx * tilingData_->outHWrectAngles) / wUbCount; // H方向上UB块偏移
    int64_t wUbCountOffset =
        blockUbCount - ncIdx * tilingData_->outHWrectAngles - hUbCountOffset * wUbCount; // W方向上UB块偏移
    int64_t ubCountOffset = 0;                                                           // 当前HW的ub块索引
    int64_t matrixWUbCntOffset = 0;                                                      // 当前HW的矩阵块W方向索引
    int64_t matrixHUbCntOffset = 0;                                                      // 当前HW的矩阵块H方向索引
    int64_t nowMatrixHUbOffset = 0;                                                      // 矩阵块内H方向UB索引
    int64_t inKernelHOffset = 0;                                                         // 输入H方向上卷积核所在行数
    int64_t perWUbMatrixCntReal = 0;
    inKernelW_ = inputInfo_->W - (kernelNumW_ - 1) * inputInfo_->wStride;
    inKernelH_ = inputInfo_->H - (kernelNumH_ - 1) * inputInfo_->hStride;
    while (procUbCount > 0) {
        ubFactorW = tilingData_->ubFactorW;
        ubFactorH = tilingData_->ubFactorH;
        ubCountOffset = hUbCountOffset * wUbCount + wUbCountOffset;
        matrixWUbCntOffset = wUbCountOffset * perWUbMatrixCnt;
        matrixHUbCntOffset = hUbCountOffset / perMatrixHUbCnt;
        perWUbMatrixCntReal =
            kernelNumH_ - matrixWUbCntOffset >= perWUbMatrixCnt ? perWUbMatrixCnt : kernelNumH_ - matrixWUbCntOffset;
        nowMatrixHUbOffset = (hUbCountOffset - matrixHUbCntOffset * perMatrixHUbCnt) * ubFactorH;
        outWOffset_ = matrixWUbCntOffset * kernelNumW_;
        outHOffset_ = matrixHUbCntOffset * inputInfo_->wKernelSize + nowMatrixHUbOffset;
        inWOffset_ = (outWOffset_ - outWOffset_ / kernelNumW_ * kernelNumW_) * inputInfo_->wStride +
                     nowMatrixHUbOffset * inputInfo_->wDilation;
        inHOffset_ = outWOffset_ / kernelNumW_ * inputInfo_->hStride +
                     outHOffset_ / inputInfo_->wKernelSize * inputInfo_->hDilation;
        xGmOffset_ = ncIdx * inputInfo_->H * inputInfo_->W + inHOffset_ * inputInfo_->W + inWOffset_;
        yGmOffset_ = ncIdx * outW_ * outH_ + outHOffset_ * outW_ + outWOffset_;
        int64_t blockLen = (inputInfo_->W - inWOffset_) >= tilingData_->w4ubFactorW ? tilingData_->w4ubFactorW :
                                                                                      (inputInfo_->W - inWOffset_);
        ubFactorW = wUbCountOffset == wUbCount - 1 ? outW_ - outWOffset_ : ubFactorW;
        ubFactorH = nowMatrixHUbOffset == (perMatrixHUbCnt - 1) * ubFactorH ?
                        inputInfo_->wKernelSize - nowMatrixHUbOffset :
                        ubFactorH;
        int64_t srcStride = (inputInfo_->hStride - 1) * inputInfo_->W + inputInfo_->W - blockLen;
        int64_t dstStride = 0;
        int64_t blockCount = perWUbMatrixCntReal;
        LocalTensor<T> xUb = inQueueX_.AllocTensor<T>();
        DataCopyIn(blockCount, blockLen, xGmOffset_, srcStride, dstStride, xUb);
        LocalTensor<T> srcUb = inQueueX_.DeQue<T>();
        if (wUbCount == 1 && outW_ <= maxGatherNum_) {
            CalcOneUBIdxAndGather(1, 1, blockLen, kernelNumW_, ubFactorH, srcUb);
            yUb_ = outQueueY_.DeQue<T>();
            DataCopyOut(0, 1, ubFactorW * ubFactorH, yGmOffset_, 0, 0, yUb_);
        } else {
            CalcIdxAndGather(blockCount, 1, blockLen, kernelNumW_, ubFactorH, ubFactorW, srcUb);
            yUb_ = outQueueY_.DeQue<T>();
            DataCopyOut(0, ubFactorH, ubFactorW, yGmOffset_, 0, outW_ - ubFactorW, yUb_);
        }
        if (wUbCountOffset == wUbCount - 1) {
            wUbCountOffset = 0;
            hUbCountOffset = hUbCountOffset == hUbCount - 1 ? 0 : hUbCountOffset + 1;
            ncIdx = hUbCountOffset == 0 ? ncIdx + 1 : ncIdx;
        } else {
            wUbCountOffset++;
        }
        procUbCount--;
        outQueueY_.FreeTensor(yUb_);
        inQueueX_.FreeTensor(srcUb);
    }
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::NoPadInWOutH()
{
    int32_t ubFactorH = tilingData_->ubFactorH;
    int32_t ubFactorW = tilingData_->ubFactorW;
    int32_t procUbCount = rectAnglesPerCore_;
    int64_t perHUbMatrixCnt = Ops::Base::CeilDiv(static_cast<int64_t>(ubFactorH), inputInfo_->wKernelSize);
    int64_t perMatrixWUbCnt = Ops::Base::CeilDiv(kernelNumW_, static_cast<int64_t>(ubFactorW));
    int64_t wUbCount = kernelNumH_ * perMatrixWUbCnt;
    int64_t hUbCount =
        Ops::Base::CeilDiv(inputInfo_->wKernelSize * inputInfo_->hKernelSize, static_cast<int64_t>(ubFactorH));
    int64_t blockUbCount = tilingData_->rectAnglesPerCore * blockIdx_;
    int64_t ncIdx = blockUbCount / tilingData_->outHWrectAngles;
    int64_t hUbCountOffset = (blockUbCount - ncIdx * tilingData_->outHWrectAngles) / wUbCount;
    int64_t wUbCountOffset = blockUbCount - ncIdx * tilingData_->outHWrectAngles - hUbCountOffset * wUbCount;
    int64_t ubCountOffset = 0;      // 当前HW的ub块索引
    int64_t matrixWUbCntOffset = 0; // 当前HW的矩阵块W方向索引
    int64_t matrixHUbCntOffset = 0; // 当前HW的矩阵块H方向索引
    int64_t nowMatrixWUbOffset = 0; // 矩阵块内W方向UB索引
    int64_t perHUbMatrixCntReal = 0;
    inKernelW_ = inputInfo_->W - (kernelNumW_ - 1) * inputInfo_->wStride;
    inKernelH_ = inputInfo_->H - (kernelNumH_ - 1) * inputInfo_->hStride;
    while (procUbCount > 0) {
        ubFactorW = tilingData_->ubFactorW;
        ubFactorH = tilingData_->ubFactorH;
        ubCountOffset = hUbCountOffset * wUbCount + wUbCountOffset;
        matrixWUbCntOffset = wUbCountOffset / perMatrixWUbCnt;
        matrixHUbCntOffset = hUbCountOffset * perHUbMatrixCnt;
        nowMatrixWUbOffset = (wUbCountOffset - matrixWUbCntOffset * perMatrixWUbCnt) * ubFactorW;
        perHUbMatrixCntReal = inputInfo_->hKernelSize - matrixHUbCntOffset >= perHUbMatrixCnt ?
                                  perHUbMatrixCnt :
                                  inputInfo_->hKernelSize - matrixHUbCntOffset;
        outWOffset_ = matrixWUbCntOffset * kernelNumW_ + nowMatrixWUbOffset;
        outHOffset_ = matrixHUbCntOffset * inputInfo_->wKernelSize;
        inWOffset_ = (outWOffset_ - outWOffset_ / kernelNumW_ * kernelNumW_) * inputInfo_->wStride;
        inHOffset_ = outWOffset_ / kernelNumW_ * inputInfo_->hStride +
                     outHOffset_ / inputInfo_->wKernelSize * inputInfo_->hDilation;
        xGmOffset_ = ncIdx * inputInfo_->H * inputInfo_->W + inHOffset_ * inputInfo_->W + inWOffset_;
        yGmOffset_ = ncIdx * outW_ * outH_ + outHOffset_ * outW_ + outWOffset_;
        int64_t blockLen = (inputInfo_->W - inWOffset_) >= tilingData_->w4ubFactorW ? tilingData_->w4ubFactorW :
                                                                                      (inputInfo_->W - inWOffset_);
        ubFactorW =
            nowMatrixWUbOffset == (perMatrixWUbCnt - 1) * ubFactorW ? kernelNumW_ - nowMatrixWUbOffset : ubFactorW;
        ubFactorH = hUbCountOffset == hUbCount - 1 ? outH_ - outHOffset_ : ubFactorH;
        int64_t srcStride = (inputInfo_->hDilation - 1) * inputInfo_->W + inputInfo_->W - blockLen;
        int64_t dstStride = 0;
        int64_t blockCount = perHUbMatrixCntReal;
        LocalTensor<T> xUb = inQueueX_.AllocTensor<T>();
        DataCopyIn(blockCount, blockLen, xGmOffset_, srcStride, dstStride, xUb);
        LocalTensor<T> srcUb = inQueueX_.DeQue<T>();
        CalcIdxAndGather(1, blockCount, blockLen, ubFactorW, inputInfo_->wKernelSize, ubFactorW, srcUb);
        LocalTensor<T> yUb = outQueueY_.DeQue<T>();
        DataCopyOut(0, ubFactorH, ubFactorW, yGmOffset_, 0, outW_ - ubFactorW, yUb);
        if (wUbCountOffset == wUbCount - 1) {
            wUbCountOffset = 0;
            hUbCountOffset = hUbCountOffset == hUbCount - 1 ? 0 : hUbCountOffset + 1;
            ncIdx = hUbCountOffset == 0 ? ncIdx + 1 : ncIdx;
        } else {
            wUbCountOffset++;
        }
        procUbCount--;
        outQueueY_.FreeTensor(yUb);
        inQueueX_.FreeTensor(srcUb);
    }
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::NoPadOutWOutH()
{
    int32_t ubFactorH = tilingData_->ubFactorH;
    int32_t ubFactorW = tilingData_->ubFactorW;
    int32_t procUbCount = rectAnglesPerCore_;
    int64_t perHUbMatrixCnt = Ops::Base::CeilDiv(static_cast<int64_t>(ubFactorH), inputInfo_->wKernelSize);
    int64_t perWUbMatrixCnt = Ops::Base::CeilDiv(static_cast<int64_t>(ubFactorW), kernelNumW_);
    int64_t wUbCount = Ops::Base::CeilDiv(outW_, static_cast<int64_t>(ubFactorW));
    int64_t hUbCount =
        Ops::Base::CeilDiv(inputInfo_->wKernelSize * inputInfo_->hKernelSize, static_cast<int64_t>(ubFactorH));
    int64_t blockUbCount = tilingData_->rectAnglesPerCore * blockIdx_;
    int64_t ncIdx = blockUbCount / tilingData_->outHWrectAngles;
    int64_t hUbCountOffset = (blockUbCount - ncIdx * tilingData_->outHWrectAngles) / wUbCount;
    int64_t wUbCountOffset = blockUbCount - ncIdx * tilingData_->outHWrectAngles - hUbCountOffset * wUbCount;
    int64_t ubCountOffset = 0;      // 当前HW的ub块索引
    int64_t matrixWUbCntOffset = 0; // 当前HW的矩阵块W方向索引
    int64_t matrixHUbCntOffset = 0; // 当前HW的矩阵块H方向索引
    int64_t perHUbMatrixCntReal = 0;
    int64_t perWUbMatrixCntReal = 0;
    while (procUbCount > 0) {
        ubFactorW = tilingData_->ubFactorW;
        ubFactorH = tilingData_->ubFactorH;
        ubCountOffset = hUbCountOffset * wUbCount + wUbCountOffset;
        matrixWUbCntOffset = wUbCountOffset * perWUbMatrixCnt;
        matrixHUbCntOffset = hUbCountOffset * perHUbMatrixCnt;
        perHUbMatrixCntReal = inputInfo_->hKernelSize - matrixHUbCntOffset >= perHUbMatrixCnt ?
                                  perHUbMatrixCnt :
                                  inputInfo_->hKernelSize - matrixHUbCntOffset;
        perWUbMatrixCntReal =
            kernelNumH_ - matrixWUbCntOffset >= perWUbMatrixCnt ? perWUbMatrixCnt : kernelNumH_ - matrixWUbCntOffset;
        outWOffset_ = matrixWUbCntOffset * kernelNumW_;
        outHOffset_ = matrixHUbCntOffset * inputInfo_->wKernelSize;
        inWOffset_ = (outWOffset_ - outWOffset_ / kernelNumW_ * kernelNumW_) * inputInfo_->wStride;
        inHOffset_ = outWOffset_ / kernelNumW_ * inputInfo_->hStride +
                     outHOffset_ / inputInfo_->wKernelSize * inputInfo_->hDilation;
        xGmOffset_ = ncIdx * inputInfo_->H * inputInfo_->W + inHOffset_ * inputInfo_->W + inWOffset_;
        yGmOffset_ = ncIdx * outW_ * outH_ + outHOffset_ * outW_ + outWOffset_;
        int64_t blockLen = (inputInfo_->W - inWOffset_) >= tilingData_->w4ubFactorW ? tilingData_->w4ubFactorW :
                                                                                      (inputInfo_->W - inWOffset_);
        ubFactorW = wUbCountOffset == wUbCount - 1 ? outW_ - outWOffset_ : ubFactorW;
        ubFactorH = hUbCountOffset == hUbCount - 1 ? outH_ - outHOffset_ : ubFactorH;
        int64_t blockLenAlign = (blockLen + BLOCK_ELENUM - 1) / BLOCK_ELENUM * BLOCK_ELENUM;
        int64_t srcStride = (inputInfo_->hStride - 1) * inputInfo_->W + inputInfo_->W - blockLen;
        int64_t dstStride = blockLenAlign * (perHUbMatrixCntReal - 1);
        int64_t blockCount = perWUbMatrixCntReal;
        loopMode_.loop1Size = perHUbMatrixCntReal;
        loopMode_.loop1SrcStride = inputInfo_->W * inputInfo_->hDilation * dtypeSize_;
        loopMode_.loop1DstStride = blockLenAlign * dtypeSize_;
        LocalTensor<T> xUb = inQueueX_.AllocTensor<T>();
        DataCopyIn(blockCount, blockLen, xGmOffset_, srcStride, dstStride, xUb);
        LocalTensor<T> srcUb = inQueueX_.DeQue<T>();
        if (wUbCount == 1 && outW_ <= maxGatherNum_) {
            CalcOneUBIdxAndGather(1, perHUbMatrixCntReal, blockLen, kernelNumW_, inputInfo_->wKernelSize, srcUb);
            yUb_ = outQueueY_.DeQue<T>();
            DataCopyOut(0, 1, ubFactorW * ubFactorH, yGmOffset_, 0, 0, yUb_);
        } else {
            CalcIdxAndGather(
                perWUbMatrixCntReal, perHUbMatrixCntReal, blockLen, kernelNumW_, inputInfo_->wKernelSize, ubFactorW,
                srcUb);
            yUb_ = outQueueY_.DeQue<T>();
            DataCopyOut(0, ubFactorH, ubFactorW, yGmOffset_, 0, outW_ - ubFactorW, yUb_);
        }
        if (wUbCountOffset == wUbCount - 1) {
            wUbCountOffset = 0;
            hUbCountOffset = hUbCountOffset == hUbCount - 1 ? 0 : hUbCountOffset + 1;
            ncIdx = hUbCountOffset == 0 ? ncIdx + 1 : ncIdx;
        } else {
            wUbCountOffset++;
        }
        procUbCount--;
        outQueueY_.FreeTensor(yUb_);
        inQueueX_.FreeTensor(srcUb);
    }
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::PadInWInH()
{
    int32_t procUbCount = tilingData_->rectAnglesPerCore;
    int64_t perMatrixWUbCnt = Ops::Base::CeilDiv(kernelNumW_, static_cast<int64_t>(ubFactorW_));
    int64_t perMatrixHUbCnt = Ops::Base::CeilDiv(inputInfo_->wKernelSize, static_cast<int64_t>(ubFactorH_));
    int64_t wUbCount = perMatrixWUbCnt * kernelNumH_;
    int64_t hUbCount = perMatrixHUbCnt * inputInfo_->hKernelSize;
    int64_t blockUbCount = tilingData_->rectAnglesPerCore * blockIdx_;
    int64_t ncIdx = blockUbCount / tilingData_->outHWrectAngles;
    int64_t hUbCountOffset = (blockUbCount - ncIdx * tilingData_->outHWrectAngles) / wUbCount;
    int64_t wUbCountOffset = blockUbCount - ncIdx * tilingData_->outHWrectAngles - hUbCountOffset * wUbCount;
    int64_t ubCountOffset = 0;      // 当前HW的ub块索引
    int64_t matrixWUbCntOffset = 0; // 当前HW的矩阵块W方向索引
    int64_t matrixHUbCntOffset = 0; // 当前HW的矩阵块H方向索引
    int64_t nowMatrixWUbOffset = 0; // 矩阵块内W方向UB索引
    int64_t nowMatrixHUbOffset = 0; // 矩阵块内H方向UB索引
    int64_t wPadTopAlign = 0;

    while (procUbCount > 0) {
        ubFactorW_ = tilingData_->ubFactorW;
        ubFactorH_ = tilingData_->ubFactorH;
        ubCountOffset = hUbCountOffset * wUbCount + wUbCountOffset;
        matrixWUbCntOffset = wUbCountOffset / perMatrixWUbCnt;
        matrixHUbCntOffset = hUbCountOffset / perMatrixHUbCnt;
        nowMatrixWUbOffset = (wUbCountOffset - matrixWUbCntOffset * perMatrixWUbCnt) * ubFactorW_;
        nowMatrixHUbOffset = (hUbCountOffset - matrixHUbCntOffset * perMatrixHUbCnt) * ubFactorH_;
        outWOffset_ = matrixWUbCntOffset * kernelNumW_ + nowMatrixWUbOffset;
        outHOffset_ = matrixHUbCntOffset * inputInfo_->wKernelSize + nowMatrixHUbOffset;
        inWOffsetPad_ = (outWOffset_ - outWOffset_ / kernelNumW_ * kernelNumW_) * inputInfo_->wStride +
                        (nowMatrixHUbOffset - 1) * inputInfo_->wDilation;
        wPadTop_ = inputInfo_->wPaddingBefore - inWOffsetPad_ > 0 ? inputInfo_->wPaddingBefore - inWOffsetPad_ : 0;
        wPadTopAlign = (wPadTop_ + BLOCK_ELENUM - 1) / BLOCK_ELENUM * BLOCK_ELENUM;
        inHOffsetPad_ = outWOffset_ / kernelNumW_ * inputInfo_->hStride +
                        outHOffset_ / inputInfo_->wKernelSize * inputInfo_->wDilation;
        hPadTop_ = inputInfo_->hPaddingBefore - inHOffsetPad_ > 0 ? inputInfo_->hPaddingBefore - inHOffsetPad_ : 0;
        inWOffset_ = inWOffsetPad_ - inputInfo_->wPaddingBefore + wPadTop_;
        inHOffset_ = inHOffsetPad_ - inputInfo_->hPaddingBefore + hPadTop_;
        xGmOffset_ = ncIdx * inputInfo_->H * inputInfo_->W + inHOffset_ * inputInfo_->W + inWOffset_;
        xGmOffsetPad_ =
            inHOffsetPad_ * (inputInfo_->W + inputInfo_->wPaddingBefore + inputInfo_->wPaddingAfter) + inWOffsetPad_;
        yGmOffset_ = ncIdx * outW_ * outH_ + outHOffset_ * outW_ + outWOffset_;
        int64_t blockLen = (inputInfo_->W - inWOffset_) >= tilingData_->w4ubFactorW ? tilingData_->w4ubFactorW :
                                                                                      (inputInfo_->W - inWOffset_);
        ubFactorW_ = nowMatrixWUbOffset == perMatrixWUbCnt - 1 ? kernelNumW_ - nowMatrixWUbOffset : ubFactorW_;
        ubFactorH_ =
            nowMatrixHUbOffset == perMatrixWUbCnt - 1 ? inputInfo_->wKernelSize - nowMatrixHUbOffset : ubFactorH_;
        if (inHOffsetPad_ < inputInfo_->hPaddingBefore ||
            inHOffsetPad_ >= (inputInfo_->H + inputInfo_->hPaddingBefore) ||
            inWOffsetPad_ >= (inputInfo_->W + inputInfo_->wPaddingBefore) ||
            inWOffsetPad_ + blockLen < inputInfo_->wPaddingBefore) {
            DataCopyOutZero(ubFactorH_, ubFactorW_, yGmOffset_, 0, outW_ - ubFactorW_);
            if (wUbCountOffset == wUbCount - 1) {
                wUbCountOffset = 0;
                hUbCountOffset = hUbCountOffset == hUbCount - 1 ? 0 : hUbCountOffset + 1;
                ncIdx = hUbCountOffset == 0 ? ncIdx + 1 : ncIdx;
            } else {
                wUbCountOffset++;
            }
            procUbCount--;
            continue;
        }
        int64_t srcStride = 0;
        int64_t dstStride = 0;
        int64_t srcOffset = wPadTopAlign;
        LocalTensor<T> xUb = inQueueX_.AllocTensor<T>();
        DataCopyInPad(1, blockLen, xGmOffset_, srcOffset, srcStride, dstStride, xUb);
        LocalTensor<T> srcUb = inQueueX_.DeQue<T>();
        CalcIdxAndGatherPad(1, 1, blockLen, ubFactorW_, ubFactorH_, srcUb);
        LocalTensor<T> yUb = outQueueY_.DeQue<T>();
        DataCopyOut(0, ubFactorH_, ubFactorW_, yGmOffset_, 0, outW_ - ubFactorW_, yUb);
        if (wUbCountOffset == wUbCount - 1) {
            wUbCountOffset = 0;
            hUbCountOffset = hUbCountOffset == hUbCount - 1 ? 0 : hUbCountOffset + 1;
            ncIdx = hUbCountOffset == 0 ? ncIdx + 1 : ncIdx;
        } else {
            wUbCountOffset++;
        }
        procUbCount--;
        outQueueY_.FreeTensor(yUb);
        inQueueX_.FreeTensor(srcUb);
    }
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::PadOutWInH()
{
    int32_t procUbCount = tilingData_->rectAnglesPerCore;
    int64_t perMatrixHUbCnt = Ops::Base::CeilDiv(inputInfo_->wKernelSize, static_cast<int64_t>(ubFactorH_));
    int64_t perWUbMatrixCnt = Ops::Base::CeilDiv(static_cast<int64_t>(ubFactorW_), kernelNumW_);
    int64_t wUbCount = Ops::Base::CeilDiv(outW_, static_cast<int64_t>(ubFactorW_));
    int64_t hUbCount = perMatrixHUbCnt * inputInfo_->hKernelSize;
    int64_t blockUbCount = tilingData_->rectAnglesPerCore * blockIdx_;
    int64_t ncIdx = blockUbCount / tilingData_->outHWrectAngles;
    int64_t hUbCountOffset = (blockUbCount - ncIdx * tilingData_->outHWrectAngles) / wUbCount; // H方向上UB块偏移
    int64_t wUbCountOffset =
        blockUbCount - ncIdx * tilingData_->outHWrectAngles - hUbCountOffset * wUbCount; // W方向上UB块偏移
    int64_t ubCountOffset = 0;                                                           // 当前HW的ub块索引
    int64_t matrixWUbCntOffset = 0;                                                      // 当前HW的矩阵块W方向索引
    int64_t matrixHUbCntOffset = 0;                                                      // 当前HW的矩阵块H方向索引
    int64_t nowMatrixHUbOffset = 0;                                                      // 矩阵块内H方向UB索引
    int64_t inKernelHOffset = 0;                                                         // 输入H方向上卷积核所在行数
    int64_t wPadTopAlign = 0;

    while (procUbCount > 0) {
        ubFactorW_ = tilingData_->ubFactorW;
        ubFactorH_ = tilingData_->ubFactorH;
        ubCountOffset = hUbCountOffset * wUbCount + wUbCountOffset;
        matrixWUbCntOffset = wUbCountOffset * perWUbMatrixCnt;
        matrixHUbCntOffset = hUbCountOffset / perMatrixHUbCnt;
        nowMatrixHUbOffset = (hUbCountOffset - matrixHUbCntOffset * perMatrixHUbCnt) * ubFactorH_;
        outWOffset_ = matrixWUbCntOffset * kernelNumW_;
        outHOffset_ = matrixHUbCntOffset * inputInfo_->wKernelSize + nowMatrixHUbOffset;
        inWOffsetPad_ = (outWOffset_ - outWOffset_ / kernelNumW_ * kernelNumW_) * inputInfo_->wStride;
        wPadTop_ = inputInfo_->wPaddingBefore - inWOffsetPad_ > 0 ? inputInfo_->wPaddingBefore - inWOffsetPad_ : 0;
        wPadTopAlign = (wPadTop_ + BLOCK_ELENUM - 1) / BLOCK_ELENUM * BLOCK_ELENUM;
        inHOffsetPad_ = outWOffset_ / kernelNumW_ * inputInfo_->hStride +
                        outHOffset_ / inputInfo_->wKernelSize * inputInfo_->wDilation;
        hPadTop_ = inputInfo_->hPaddingBefore - inHOffsetPad_ > 0 ? inputInfo_->hPaddingBefore - inHOffsetPad_ : 0;

        xGmOffset_ = ncIdx * inputInfo_->H * inputInfo_->W + inHOffset_ * inputInfo_->W + inWOffset_;
        yGmOffset_ = ncIdx * outW_ * outH_ + outHOffset_ * outW_ + outWOffset_;
        int64_t blockLen = (inputInfo_->W - inWOffset_) >= tilingData_->w4ubFactorW ? tilingData_->w4ubFactorW :
                                                                                      (inputInfo_->W - inWOffset_);
        ubFactorW_ = wUbCountOffset == wUbCount - 1 ? outW_ - outWOffset_ : ubFactorW_;
        ubFactorH_ =
            nowMatrixHUbOffset == perMatrixHUbCnt - 1 ? inputInfo_->wKernelSize - nowMatrixHUbOffset : ubFactorH_;
    }
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::PadInWOutH()
{}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::PadOutWOutH()
{}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::ProcessPad()
{
    if (ubFactorW_ < tilingData_->convKernelNumInWidth && ubFactorH_ < inputInfo_->wKernelSize) {
        // W和H都截断
        PadInWInH();
    } else if (ubFactorW_ >= tilingData_->convKernelNumInWidth && ubFactorH_ < inputInfo_->wKernelSize) {
        // W不截断，H截断
        PadOutWInH();
    } else if (ubFactorW_ < tilingData_->convKernelNumInWidth && ubFactorH_ >= inputInfo_->wKernelSize) {
        // W截断，H不截断
        PadInWOutH();
    } else {
        // W和H都不截断
        PadOutWOutH();
    }
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::ProcessNoPad()
{
    if (ubFactorW_ < tilingData_->convKernelNumInWidth && ubFactorH_ < inputInfo_->wKernelSize) {
        // W和H都截断
        NoPadInWInH();
    } else if (ubFactorW_ >= tilingData_->convKernelNumInWidth && ubFactorH_ < inputInfo_->wKernelSize) {
        // W不截断，H截断
        NoPadOutWInH();
    } else if (ubFactorW_ < tilingData_->convKernelNumInWidth && ubFactorH_ >= inputInfo_->wKernelSize) {
        // W截断，H不截断
        NoPadInWOutH();
    } else {
        // W和H都不截断
        NoPadOutWOutH();
    }
}

template <typename T, typename U, typename Y, bool isPadding>
__aicore__ inline void Im2colGatherCutHw<T, U, Y, isPadding>::Process()
{
    if (blockIdx_ * tilingData_->rectAnglesPerCore > tilingData_->totalRectAngles) {
        return;
    }
    rectAnglesPerCore_ =
        tilingData_->totalRectAngles - blockIdx_ * tilingData_->rectAnglesPerCore < tilingData_->rectAnglesPerCore ?
            tilingData_->totalRectAngles - blockIdx_ * tilingData_->rectAnglesPerCore :
            tilingData_->rectAnglesPerCore;
    if constexpr (isPadding) {
        ProcessPad();
    } else {
        ProcessNoPad();
    }
}
} // namespace Im2col
#endif // namespace Im2col
