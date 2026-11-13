/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#ifndef SPLIT_V_PURE_COPY_H
#define SPLIT_V_PURE_COPY_H
#include "op_kernel/platform_util.h"
namespace SplitV {
using namespace AscendC;
const int32_t SPLIT_LIST_MAX_LEN = 64;

template <typename T>
class SplitVPureCopyMode
{
public:
    __aicore__ inline SplitVPureCopyMode(TPipe& pipe) : pipe_(pipe){};
    __aicore__ inline void Init(GM_ADDR x, GM_ADDR y, const SplitVTilingData* tilingData);
    __aicore__ inline void Process();

private:
    __aicore__ inline __gm__ T* GetTensorAddr(int64_t index);
    __aicore__ inline int64_t SplitPrefix(int64_t index);
    __aicore__ inline int64_t CurSplitSize(int64_t index);
    __aicore__ inline void CalcUbAndProcessCopy(int32_t i);
    __aicore__ inline void CopyArray(const int64_t* src, int64_t* dst, int32_t size);
    __aicore__ inline void CopyOutToGm(
        int64_t blockCount, int64_t blockLen, int64_t dstOffset, int64_t srcStride, int64_t dstStride);
    __aicore__ inline void CopyInToUb(
        int64_t blockCount, int64_t blockLen, int64_t srcOffset_, int64_t srcStride, int64_t dstStride);
    __aicore__ inline void CopyOfM(int64_t factor, int32_t i);
    __aicore__ inline int32_t min(int32_t a, int32_t b);
    __aicore__ inline void CalcCurDstOffset(int32_t i);
    __aicore__ inline void CalcNSplitSize(int32_t i);

private:
    TPipe& pipe_;
    const SplitVTilingData* tilingData_;
    constexpr static int32_t BUFFER_NUM = 2;
    constexpr static int64_t BLOCK_ELENUM = Ops::Base::GetUbBlockSize() / sizeof(T);
    TBuf<> inXBuf_;
    GlobalTensor<T> xGm_;
    GlobalTensor<T> yGm_;
    ListTensorDesc inputList_;
    LocalTensor<T> inTensorX_;

    int32_t blockIdx_ = 0;
    int64_t ubSize_ = 0;
    int64_t realCoreNum_ = 0;       // 真实使用的核数
    int64_t dtypeSize_ = sizeof(T); // 输入dtype所占的字节数
    int64_t nSplitSize_ = 0;        // 当前分块n轴的大小
    int64_t nBlockOffset_ = 0;
    int64_t mBlockOffset_ = 0;
    int64_t blockOffset_ = 0;

    // n轴每个切分factor 在第几个split块上,start，且按照索引为开始位置
    int64_t nBlockSplitOffset_[SPLIT_LIST_MAX_LEN] = {0};
    int64_t nBlockSplitOffsetEnd_[SPLIT_LIST_MAX_LEN] = {0}; // end -start = 处理的split块数

    int64_t nUbFactor_ = 0;     // Ub切分n轴主块大小
    int64_t nUbFactorTail_ = 0; // Ub切分n轴尾块大小
    int64_t nSplitUbTimes_ = 0; // Ub切分n轴处理次数
    int64_t nFactor_ = 0;       // block切分n轴大小

    int64_t mUbFactor_ = 0;     // Ub切分m轴主块大小
    int64_t mUbFactorTail_ = 0; // Ub切分m轴尾块大小
    int64_t mSplitUbTimes_ = 0; // Ub切分m轴处理次数
    int64_t mFactor_ = 0;       // block切分m轴大小

    int64_t ubSizeNum_ = 0; // Ub可以放个数
    int64_t startOffset_ = 0;
    int64_t splitNumPerCore_ = 0;
    int64_t srcOffset_ = 0;
    int64_t dstOffset_ = 0;
    int64_t curDstOffset_ = 0;

    DataCopyExtParams copyInParam_{0, 0, 0, 0, 0};
    DataCopyPadExtParams<T> padParam_{false, 0, 0, 0};
    DataCopyExtParams copyOutParam_{0, 0, 0, 0, 0};

    int32_t isNBlockMain_ = 0;
    int32_t isMBlockMain_ = 0;
    int32_t nIdx_ = 0;
    int32_t mIdx_ = 0;
    int64_t prefixBlock_ = 0;
    int64_t prefixSplitI_ = 0;
    int64_t prefixBlockBefore_ = 0;
};

template <typename T>
__aicore__ inline void SplitVPureCopyMode<T>::Init(GM_ADDR x, GM_ADDR y, const SplitVTilingData* tilingData)
{
    blockIdx_ = GetBlockIdx();
    tilingData_ = tilingData;
    ubSize_ = tilingData_->ubSize;
    CopyArray(tilingData->nBlockSplitOffset, nBlockSplitOffset_, SPLIT_LIST_MAX_LEN);
    CopyArray(tilingData->nBlockSplitOffsetEnd, nBlockSplitOffsetEnd_, SPLIT_LIST_MAX_LEN);
    realCoreNum_ = tilingData_->realCoreNum; // 真实使用的核数
    ubSizeNum_ = ubSize_ / dtypeSize_;
    pipe_.InitBuffer(inXBuf_, ubSize_);
    inTensorX_ = inXBuf_.template Get<T>();
    xGm_.SetGlobalBuffer((__gm__ T*)x);
    inputList_ = ListTensorDesc(reinterpret_cast<__gm__ void*>(y));

    nIdx_ = blockIdx_ % tilingData_->nBlockCount;
    mIdx_ = blockIdx_ / tilingData_->nBlockCount;
    isNBlockMain_ = (nIdx_ < tilingData_->nBlockFactorNum) ? 1 : 0;
    isMBlockMain_ = (mIdx_ < tilingData_->mBlockFactorNum) ? 1 : 0;
    nBlockOffset_ = isNBlockMain_ == 1 ? nIdx_ * tilingData_->nBlockFactor :
                                         tilingData_->nBlockFactorNum * tilingData_->nBlockFactor +
                                             (nIdx_ - tilingData_->nBlockFactorNum) * tilingData_->nBlockFactorTail;
    mBlockOffset_ = isMBlockMain_ == 1 ? mIdx_ * tilingData_->mBlockFactor :
                                         tilingData_->mBlockFactorNum * tilingData_->mBlockFactor +
                                             (mIdx_ - tilingData_->mBlockFactorNum) * tilingData_->mBlockFactorTail;
    splitNumPerCore_ = nBlockSplitOffsetEnd_[blockIdx_] - nBlockSplitOffset_[blockIdx_];
    blockOffset_ = mBlockOffset_ * tilingData_->nSize + nBlockOffset_;
    mFactor_ = isMBlockMain_ == 1 ? tilingData_->mBlockFactor : tilingData_->mBlockFactorTail;
    nFactor_ = isNBlockMain_ == 1 ? tilingData_->nBlockFactor : tilingData_->nBlockFactorTail;
    prefixBlock_ = SplitPrefix(nBlockSplitOffset_[blockIdx_]);
    prefixBlockBefore_ = nBlockSplitOffset_[blockIdx_] > 0 ? SplitPrefix(nBlockSplitOffset_[blockIdx_] - 1) : 0;
}

template <typename T>
__aicore__ inline void SplitVPureCopyMode<T>::Process()
{
    if (blockIdx_ >= realCoreNum_) {
        return;
    }
    for (int32_t i = 0; i < splitNumPerCore_; i++) {
        yGm_.SetGlobalBuffer(GetTensorAddr(nBlockSplitOffset_[blockIdx_] + i));
        prefixSplitI_ =
            (nBlockSplitOffset_[blockIdx_] + i) > 0 ? SplitPrefix(nBlockSplitOffset_[blockIdx_] + i - 1) : 0;
        CalcNSplitSize(i);
        // 计算n轴ub切分参数
        nSplitUbTimes_ = (nSplitSize_ + ubSizeNum_ - 1) / ubSizeNum_;
        nUbFactor_ = nSplitSize_ >= ubSizeNum_ ? ubSizeNum_ : 0;
        nUbFactorTail_ = nSplitSize_ - nUbFactor_ * (nSplitUbTimes_ - 1);
        // 计算m轴ub切分参数
        mUbFactor_ =
            nSplitSize_ >= ubSizeNum_ ?
                1 :
                min(mFactor_, ubSizeNum_ / (((nUbFactorTail_ + BLOCK_ELENUM - 1) / BLOCK_ELENUM) * BLOCK_ELENUM));
        mSplitUbTimes_ = (mFactor_ + mUbFactor_ - 1) / mUbFactor_;
        mUbFactorTail_ = mFactor_ - mUbFactor_ * (mSplitUbTimes_ - 1);
        CalcUbAndProcessCopy(i);
    }
}

template <typename T>
__aicore__ inline void SplitVPureCopyMode<T>::CalcNSplitSize(int32_t i)
{
    if (i == 0) {
        startOffset_ = blockOffset_;
        nSplitSize_ = min(prefixBlock_ - nBlockOffset_, nFactor_);
    } else if (i < splitNumPerCore_ - 1) {
        startOffset_ = mBlockOffset_ * tilingData_->nSize + prefixSplitI_;
        nSplitSize_ = CurSplitSize(nBlockSplitOffset_[blockIdx_] + i);
    } else {
        startOffset_ = mBlockOffset_ * tilingData_->nSize + prefixSplitI_;
        nSplitSize_ = nBlockOffset_ + nFactor_ - prefixSplitI_;
    }
}

template <typename T>
__aicore__ inline void SplitVPureCopyMode<T>::CalcUbAndProcessCopy(int32_t i)
{
    srcOffset_ = startOffset_; // 更新Split切分块初始srcOffset_
    CalcCurDstOffset(i);
    dstOffset_ = curDstOffset_;
    if (i > 0) {
        event_t eventID = static_cast<event_t>(GetTPipePtr()->FetchEventID(HardEvent::MTE3_MTE2));
        SetFlag<HardEvent::MTE3_MTE2>(eventID);
        WaitFlag<HardEvent::MTE3_MTE2>(eventID);
    }

    for (int32_t mIdx = 0; mIdx < mSplitUbTimes_ - 1; mIdx++) {
        // ub主块搬运
        srcOffset_ = startOffset_ + mUbFactor_ * tilingData_->nSize * mIdx;
        dstOffset_ = curDstOffset_ + mUbFactor_ * CurSplitSize(nBlockSplitOffset_[blockIdx_] + i) * mIdx;
        CopyOfM(mUbFactor_, i);
        event_t eventID0 = static_cast<event_t>(GetTPipePtr()->FetchEventID(HardEvent::MTE3_MTE2));
        SetFlag<HardEvent::MTE3_MTE2>(eventID0);
        WaitFlag<HardEvent::MTE3_MTE2>(eventID0);
    }
    // ub尾块搬运
    srcOffset_ = startOffset_ + mUbFactor_ * tilingData_->nSize * (mSplitUbTimes_ - 1);
    dstOffset_ = curDstOffset_ + mUbFactor_ * CurSplitSize(nBlockSplitOffset_[blockIdx_] + i) * (mSplitUbTimes_ - 1);
    CopyOfM(mUbFactorTail_, i);
}

template <typename T>
__aicore__ inline void SplitVPureCopyMode<T>::CopyOfM(int64_t factor, int32_t i)
{
    int64_t blockCount = 0;
    int64_t blockLen = 0;
    int64_t srcStride = 0;
    int64_t dstStride = 0;
    for (int32_t nIdx = 0; nIdx < nSplitUbTimes_ - 1; nIdx++) {
        srcStride = tilingData_->nSize - nUbFactor_;
        dstStride = 0;
        blockCount = factor;
        blockLen = nUbFactor_;
        CopyInToUb(blockCount, blockLen, srcOffset_, srcStride, dstStride);
        srcStride = 0;
        dstStride = CurSplitSize(nBlockSplitOffset_[blockIdx_] + i) - nUbFactor_;
        event_t eventID1 = static_cast<event_t>(GetTPipePtr()->FetchEventID(HardEvent::MTE2_MTE3));
        SetFlag<HardEvent::MTE2_MTE3>(eventID1);
        WaitFlag<HardEvent::MTE2_MTE3>(eventID1);
        CopyOutToGm(blockCount, blockLen, dstOffset_, srcStride, dstStride);
        event_t eventID2 = static_cast<event_t>(GetTPipePtr()->FetchEventID(HardEvent::MTE3_MTE2));
        SetFlag<HardEvent::MTE3_MTE2>(eventID2);
        WaitFlag<HardEvent::MTE3_MTE2>(eventID2);
        srcOffset_ = srcOffset_ + nUbFactor_;
        dstOffset_ = dstOffset_ + nUbFactor_;
    }
    srcStride = tilingData_->nSize - nUbFactorTail_;
    dstStride = 0;
    blockCount = factor;
    blockLen = nUbFactorTail_;
    CopyInToUb(blockCount, blockLen, srcOffset_, srcStride, dstStride);
    srcStride = 0;
    dstStride = CurSplitSize(nBlockSplitOffset_[blockIdx_] + i) - nUbFactorTail_;
    event_t eventID4 = static_cast<event_t>(GetTPipePtr()->FetchEventID(HardEvent::MTE2_MTE3));
    SetFlag<HardEvent::MTE2_MTE3>(eventID4);
    WaitFlag<HardEvent::MTE2_MTE3>(eventID4);
    CopyOutToGm(blockCount, blockLen, dstOffset_, srcStride, dstStride);
}

template <typename T>
__aicore__ inline void SplitVPureCopyMode<T>::CalcCurDstOffset(int32_t i)
{
    int64_t curCoreNDstOffset = 0;
    int64_t curCoreMDstOffset = mBlockOffset_;
    if (i == 0) {
        curCoreNDstOffset = nBlockOffset_ - prefixBlockBefore_;
    } else {
        curCoreNDstOffset = 0;
    }
    curDstOffset_ = curCoreMDstOffset * CurSplitSize(nBlockSplitOffset_[blockIdx_] + i) + curCoreNDstOffset;
}

template <typename T>
__aicore__ inline void SplitVPureCopyMode<T>::CopyInToUb(
    int64_t blockCount, int64_t blockLen, int64_t srcOffset_, int64_t srcStride, int64_t dstStride)
{
    copyInParam_.blockCount = blockCount;
    copyInParam_.blockLen = blockLen * dtypeSize_;
    copyInParam_.srcStride = srcStride * dtypeSize_;
    copyInParam_.dstStride = 0;
    DataCopyPad(inTensorX_, xGm_[srcOffset_], copyInParam_, padParam_);
}

template <typename T>
__aicore__ inline void SplitVPureCopyMode<T>::CopyOutToGm(
    int64_t blockCount, int64_t blockLen, int64_t dstOffset, int64_t srcStride, int64_t dstStride)
{
    copyOutParam_.blockCount = blockCount;
    copyOutParam_.blockLen = blockLen * dtypeSize_;
    copyOutParam_.srcStride = 0;
    copyOutParam_.dstStride = dstStride * dtypeSize_;
    DataCopyPad(yGm_[dstOffset], inTensorX_, copyOutParam_);
}

template <typename T>
__aicore__ inline __gm__ T* SplitVPureCopyMode<T>::GetTensorAddr(int64_t index)
{
    return inputList_.GetDataPtr<T>(index);
}

template <typename T>
__aicore__ inline int64_t SplitVPureCopyMode<T>::SplitPrefix(int64_t index)
{
    uint64_t buf[10] = {0};
    TensorDesc<T> desc;
    desc.SetShapeAddr(&buf[0]);
    int64_t tensorSize = 0;
    for (int64_t j = 0; j < index + 1; j++) {
        inputList_.GetDesc(desc, j);
        tensorSize = tensorSize + tilingData_->sizeAfterSplitDim * desc.GetShape(tilingData_->splitDim);
    }
    return tensorSize;
}

template <typename T>
__aicore__ inline int64_t SplitVPureCopyMode<T>::CurSplitSize(int64_t index)
{
    uint64_t buf[10] = {0};
    TensorDesc<T> desc;
    desc.SetShapeAddr(&buf[0]);
    inputList_.GetDesc(desc, index);
    int64_t tensorSize = tilingData_->sizeAfterSplitDim * desc.GetShape(tilingData_->splitDim);
    return tensorSize;
}

template <typename T>
__aicore__ inline void SplitVPureCopyMode<T>::CopyArray(const int64_t* src, int64_t* dst, int32_t size)
{
    for (int32_t i = 0; i < size; i++) {
        dst[i] = src[i];
    }
}

template <typename T>
__aicore__ inline int32_t SplitVPureCopyMode<T>::min(int32_t a, int32_t b)
{
    return a > b ? b : a;
}
} // namespace SplitV
#endif