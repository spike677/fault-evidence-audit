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
 * \file reduce_sch_aux.h
 * \brief aux for reduce schedule, include reduce addr calc, handle pre/post op
 */

#ifndef _REDUCE_SCH_AUX_H_
#define _REDUCE_SCH_AUX_H_
#include "reduce_sch_aux_util.h"
#include "reduce_tiling_data.h"

namespace Ops {
namespace Base {
namespace ReduceOpTmpl
{
template <auto LoopInfo, class ReduceSch, bool IsStageOne, class OpDag = void>
struct ReduceSchAux {
    using ReduceOpBind = typename OpDag::FunList::template At<OpDag::ReduceOpPos>;
    using ReduceOp = typename ReduceOpBind::Fun;
    using Pattern = typename __reducePattern::GetPattern<LoopInfo->patternID>::T;
    using InnerPattern = typename __reducePattern::GetPattern<LoopInfo->innerPatternID>::T;
    using DataType = typename ReduceSch::DataType;
    // 输入数据类型
    using InDType = typename InputDType<OpDag, DataType, IsStageOne, IsSameType<OpDag, void>::value>::T;
    // reduce计算的数据类型
    using PromoteDType =
    	typename OutputDType<OpDag, DataType, OpDag::ReduceOpPos, IsSameType<OpDag, void>::value>::T;
    // 输出数据类型 
    using OutDType = 
        typename OutputDType<OpDag, DataType, OpDag::FunList::Size - 1, IsSameType<OpDag, void>::value>::T;
    constexpr static int32_t Dim = Pattern::Dim;
    constexpr static int32_t VL_ELEMS = Ops::Base::GetVRegSize() / sizeof(DataType);
    constexpr static uint64_t UB_BLOCK = Ops::Base::GetUbBlockSize();

public:
    uint64_t loopAStartIndex_ = 0;
    uint64_t loopAEndIndex_ = 0;
    uint64_t loopAAxisStep_ = 0;
    uint64_t ubFactorA_ = 0;

    uint64_t loopRStartIndex_ = 0;
    uint64_t loopREndIndex_ = 0;
    uint64_t loopRAxisStep_ = 0;
    uint64_t ubFactorR_ = 0;

    GlobalTensor<uint8_t>* input_;
    GlobalTensor<uint8_t>* output_;
    GlobalTensor<uint8_t>* workspace_;
    LocalTensor<PromoteDType> reduceOut_;

    // 二分算法的二分点
    uint64_t bisectionPos_ = 0;
    uint64_t cacheCount_ = 0;
    uint64_t bisectionTail_ = 0;

    uint64_t eleNum_ = 0;

    struct {
        uint64_t start = 0;
        uint64_t stride = 1;
    } iterAddr_[Dim];

    const ReduceOpTilingData* tiling_;
    ReduceSch* sch_;
    ReduceOp* op_;

public:
    __aicore__ constexpr static int32_t GetPreBufferNum()
    {
        if constexpr (OpDag::ReduceOpPos == 1) {
            return OpDag::template GetBufferNumImpl<typename OpDag::PreReduceNodeInfo, true, false>() * CONST2;
        } else {
            return OpDag::template GetBufferNumImpl<typename OpDag::PreReduceNodeInfo, true, false>();
        }
    }

    constexpr static auto preBufferIds_ = OpDag::template GetReduceBufferIds<true>();
    constexpr static auto postBufferIds_ = OpDag::template GetReduceBufferIds<false>();
    constexpr static int32_t preBufNum_ = GetPreBufferNum();

public:
    __aicore__ inline ReduceSchAux(ReduceSch* sch, GlobalTensor<uint8_t>* input, GlobalTensor<uint8_t>* output,
                                   GlobalTensor<uint8_t>* workspace, const ReduceOpTilingData* tiling)
    {
        this->sch_ = sch;
        this->input_ = input;
        this->output_ = output;
        this->workspace_ = workspace;
        this->tiling_ = tiling;
        for (uint64_t i = 0; i < Dim; i++) {
            iterAddr_[i].stride = tiling_->shape[i];
        }
        eleNum_ = tiling_->basicBlock / sizeof(InDType);
    }

    __aicore__ inline void SetLoopRange()
    {
        int32_t blockId = GetBlockIdx();
        if constexpr (IsBlockCutA<LoopInfo>()) {
            loopAStartIndex_ = blockId * tiling_->factorACntPerCore;
            loopAEndIndex_ = loopAStartIndex_ + tiling_->factorACntPerCore;
            if (unlikely(loopAEndIndex_ > tiling_->factorATotalCnt)) {
                loopAEndIndex_ = tiling_->factorATotalCnt;
            }
            constexpr int32_t aAxisIdx = LoopInfo->loopACount - 1;
            constexpr int32_t aAxis = LoopInfo->loopAAxis[aAxisIdx];
            loopAAxisStep_ = Ops::Base::CeilDiv(tiling_->shape[aAxis], tiling_->ubFactorA);
            if constexpr (LoopInfo->loopInnerRCount > 0) {
                constexpr int32_t rAxisIdx = LoopInfo->loopInnerRCount - 1;
                constexpr int32_t rAxis = LoopInfo->loopInnerRAxis[rAxisIdx];
                loopRAxisStep_ = Ops::Base::CeilDiv(tiling_->shape[rAxis], tiling_->ubFactorR);
            }
        } else {
            loopRStartIndex_ = blockId / tiling_->groupR * tiling_->factorRTotalCnt +
                               blockId % tiling_->groupR * tiling_->factorRCntPerCore;
            loopREndIndex_ = loopRStartIndex_ + tiling_->factorRCntPerCore;
            uint64_t maxRCnt = (blockId / tiling_->groupR + 1) * tiling_->factorRTotalCnt;
            uint64_t totalCnt = tiling_->factorATotalCnt * tiling_->factorRTotalCnt;
            maxRCnt = maxRCnt > totalCnt ? totalCnt : maxRCnt;
            if (unlikely(loopRStartIndex_ > maxRCnt)) {
                loopRStartIndex_ = maxRCnt;
            }
            if (unlikely(loopREndIndex_ > maxRCnt)) {
                loopREndIndex_ = maxRCnt;
            }

            constexpr int32_t rAxisIdx = LoopInfo->loopRCount - 1;
            constexpr int32_t rAxis = LoopInfo->loopRAxis[rAxisIdx];
            loopRAxisStep_ = Ops::Base::CeilDiv(tiling_->shape[rAxis], tiling_->ubFactorR);  // 切分轴Rfactor的个数

            if constexpr (LoopInfo->loopACount > 0) {
                constexpr int32_t aAxisIdx = LoopInfo->loopACount - 1;
                constexpr int32_t aAxis = LoopInfo->loopAAxis[aAxisIdx];
                loopAAxisStep_ = Ops::Base::CeilDiv(tiling_->shape[aAxis], tiling_->ubFactorA);
            }
        }
        ubFactorA_ = tiling_->ubFactorA;
        ubFactorR_ = tiling_->ubFactorR;
        RUN_LOG(
            "loopAStartIndex:%ld, loopAEndIndex:%ld, loopAAxisStep:%ld, ubFactorA:%ld, loopRStartIndex:%ld, "
            "loopREndIndex:%ld, loopRAxisStep:%ld, ubFactorR:%ld\n",
            loopAStartIndex_, loopAEndIndex_, loopAAxisStep_, ubFactorA_, loopRStartIndex_, loopREndIndex_,
            loopRAxisStep_, ubFactorR_);
    }

    __aicore__ inline void SetIterRRange()
    {
        uint64_t rCount = 0;
        if constexpr (LoopInfo->loopRCount == 0) {
            rCount = tiling_->factorRCntPerCore;
        } else {
            rCount = loopREndIndex_ - loopRStartIndex_;
        }
        bisectionPos_ = FindNearestPower2(rCount);
        cacheCount_ = CalLog2(bisectionPos_) + 1;
        bisectionTail_ = rCount - bisectionPos_;
    }

    template <class... Args>
    __aicore__ inline void Process(Args... args)
    {
        SetLoopRange();
        SetIterRRange();

        if constexpr (LoopInfo->loopRCount == 0) {
            for (uint64_t i = loopAStartIndex_; i < loopAEndIndex_; i++) {
                CalculateIterA<LoopInfo->loopACount>(i);
                IterateInnerA<0, LoopInfo->loopInnerACount>(i - loopAStartIndex_, args...);
            }
        } else {
            if (loopRStartIndex_ == loopREndIndex_) {
                return;
            }
            IterateInnerA<0, LoopInfo->loopInnerACount>(0, args...);
        }
    }

    template <int32_t LoopAIdx>
    __aicore__ inline void CalculateIterA(uint64_t step)
    {
        if constexpr (LoopAIdx != 0) {
            constexpr auto axis = LoopInfo->loopAAxis[LoopAIdx - 1];
            if constexpr (LoopAIdx == LoopInfo->loopACount) {
                // 切分轴
                auto cur = step % this->loopAAxisStep_;
                this->iterAddr_[axis].start = cur * this->ubFactorA_;
                this->iterAddr_[axis].stride = tiling_->shape[axis] - this->iterAddr_[axis].start;
                if (likely(this->iterAddr_[axis].stride >= this->ubFactorA_)) {
                    this->iterAddr_[axis].stride = this->ubFactorA_;
                }

                if constexpr (LoopAIdx > 0) {
                    CalculateIterA<LoopAIdx - 1>(step / this->loopAAxisStep_);
                }
            } else {
                this->iterAddr_[axis].start = step % tiling_->shape[axis];
                this->iterAddr_[axis].stride = 1;
                CalculateIterA<LoopAIdx - 1>(step / tiling_->shape[axis]);
            }
        }
    }

    template <int32_t start = 0, int32_t end = 0, class... Args>
    __aicore__ inline void IterateInnerA(int32_t aIndex, Args... args)
    {
        if constexpr (start == end) {
            // R轴拉平
            int32_t startIdx = 0;
            if constexpr (LoopInfo->reduceDichotomy) {
                Shape<InnerPattern::Dim> shape = {.value = {0, 0}, .innerR = 0, .outerR = 0};
                SliceView<MAX_DIM> view;
                if constexpr (LoopInfo->loopRCount == 0) {
                    LinearComputeR(aIndex, startIdx, view, shape);
                    PostReduce(aIndex, view, shape);
                } else {
                    LinearComputeR(aIndex, startIdx, view, shape);
                    CopyOutGroup(view, shape);
                }
            }
        } else {
            constexpr int32_t axis = LoopInfo->loopInnerAAxis[start];
            uint64_t shape = tiling_->shape[axis];
            if constexpr (start + 1 == end) {  // 为最内轴
                uint64_t loopSize = shape / this->ubFactorA_;
                uint64_t tail = shape - loopSize * this->ubFactorA_;
                this->iterAddr_[axis].start = 0;
                this->iterAddr_[axis].stride = this->ubFactorA_;

                for (uint64_t i = 0; i < loopSize; i++) {  // 整块
                    IterateInnerA<start + 1, end>(aIndex, args...);
                    this->iterAddr_[axis].start += this->ubFactorA_;
                }

                if (tail) {
                    this->iterAddr_[axis].stride = shape - this->iterAddr_[axis].start;
                    IterateInnerA<start + 1, end>(aIndex, args...);
                }
            } else {
                for (uint64_t i = 0; i < shape; i++) {
                    this->iterAddr_[axis].start = i;
                    IterateInnerA<start + 1, end>(aIndex, args...);
                }
            }
        }
    }

    template <class S, class V>
    __aicore__ inline void LinearComputeR(int32_t aIndex, int32_t& startIdx, V& view, S& shape)
    {
        PaddingParam padParam0;
        PaddingParam padParam1;
        PaddingParam padParam;
        int32_t idx = startIdx;
        // 对于ReduceOpPos = 1的场景，共有4份输入空间，ping两份，pong两份，idx是为了计算pingpong索引的下标
        for (uint64_t i = 0; i < bisectionTail_; i++) {
            PreReduce(view, shape, padParam0, i, idx, 0);                  // ping
            PreReduce(view, shape, padParam1, i + bisectionPos_, idx, 1);  // pong
            ReduceComputeMerge(view, shape, padParam0, padParam1, idx);
            UpdateCache(i, shape);
            idx = (idx + 1) & 1;
        }

        int32_t preIdx = idx;
        for (uint64_t i = bisectionTail_; i < bisectionPos_; i++) {
            int32_t pingPong = 0;
            if constexpr (LoopInfo->loopRCount == 0 && LoopInfo->loopInnerRCount == 0) {
                // normal R轴全载, 使用A轴索引开pingpong
                pingPong = aIndex & 1;
                idx = (aIndex / CONST2) & 1;
            } else {
                pingPong = ((i - bisectionTail_) & 1);
                idx = (preIdx + (i - bisectionTail_) / CONST2) & 1;
            }
            PreReduce(view, shape, padParam, i, idx, pingPong);
            ReduceCompute(view, shape, padParam, idx, pingPong);
            UpdateCache(i, shape);
        }
        startIdx = idx;
    }

    template <class V, class S, class P>
    __aicore__ inline void PreReduce(V& view, S& shape, P& padding, uint64_t rIndex, uint64_t idx, int32_t pingPong)
    {
        if constexpr (LoopInfo->loopRCount > 0) {
            CalculateIterR<LoopInfo->loopRCount>(rIndex + loopRStartIndex_);
        } else {
            CalculateInnerIterR<LoopInfo->loopInnerRCount>(rIndex);
        }
        InitView(view);
        if constexpr (IsSameType<OpDag, void>::value || !IsStageOne) {
            RUN_LOG("no preop defined or group reduce stage two.\n");
            CopyInNoPreOp(view, shape, pingPong, idx);
        } else {
            RunPreOp<0>(view, shape, pingPong, idx);
        }

        CalculatePadding(view, shape, padding);
    }

    template <class V, class S>
    __aicore__ inline void CalculataRDetails(V& view, S& shape, int32_t burstLen, int32_t rRepeats)
    {
        if constexpr (!Pattern::TailA) {
            if (view.isBlockAligned == 1U) {
                const int32_t blkSize = static_cast<int32_t>(UB_BLOCK / sizeof(InDType));
                const int32_t busrtLenAlign = Ops::Base::CeilAlign(burstLen, blkSize);
                shape.innerR = burstLen;
                shape.outerR = shape.value[1] / busrtLenAlign;
            } else {
                shape.innerR = rRepeats;
                shape.outerR = 1UL;
            }
        }
    }

    template <class V, class S, class P>
    __aicore__ inline void ReduceCompute(V& view, S& shape, P& padParam, int32_t idx, int32_t pingPong)
    {
        static_assert(IsSameType<PromoteDType, DataType>::value, "reduce calc dtype must be same with pre dag out.");
        if constexpr (Pattern::ID != PATTERN_A) {
            CalculataRDetails(view, shape, padParam.burstPaddingStart, padParam.rPaddingStart);
            LocalTensor<PromoteDType> input = GetReduceInputTensor<PromoteDType>(pingPong, idx, eleNum_);
            sch_->ReduceSch::template PadValueAux<Pattern, InDType>(input, shape, padParam);
            sch_->ReduceSch::template ComputeAux<InnerPattern>(input, shape);
            ReleaseReduceInputTensor(pingPong, idx);
        }
    }

    template <class V, class S, class P>
    __aicore__ inline void ReduceComputeMerge(V& view, S& shape, P& padParam0, P& padParam1, int32_t idx)
    {
        static_assert(IsSameType<PromoteDType, DataType>::value, "reduce calc dtype must be same with pre dag out.");
        const int32_t innerR =
            (padParam0.burstPaddingStart > padParam1.burstPaddingStart ? padParam0.burstPaddingStart
                                                                       : padParam1.burstPaddingStart);
        const int32_t rRepeats =
            (padParam0.rPaddingStart > padParam1.rPaddingStart ? padParam0.rPaddingStart : padParam1.rPaddingStart);
        CalculataRDetails(view, shape, innerR, rRepeats);

        LocalTensor<PromoteDType> input0 = GetReduceInputTensor<PromoteDType>(0, idx, eleNum_);
        LocalTensor<PromoteDType> input1 = GetReduceInputTensor<PromoteDType>(1, idx, eleNum_);
        sch_->ReduceSch::template PadValueAux<Pattern, InDType>(input0, shape, padParam0);
        sch_->ReduceSch::template PadValueAux<Pattern, InDType>(input1, shape, padParam1);
        op_->BisectionPreHandle(input1, input0, input1, shape.value[0] * shape.value[1]);
        ReleaseReduceInputTensor(0, idx);

        sch_->ReduceSch::template ComputeAux<InnerPattern>(input1, shape);
        ReleaseReduceInputTensor(1, idx);
    }

    template <class S>
    __aicore__ inline void UpdateCache(uint64_t rIndex, S& shape)
    {
        static_assert(IsSameType<PromoteDType, DataType>::value, "reduce calc dtype must be same with pre dag out.");
        if constexpr (Pattern::ID != PATTERN_A) {
            SetEvent<HardEvent::MTE3_V>(HardEvent::MTE3_V);
            sch_->ReduceSch::template UpdateCacheAux<Pattern, DataType>(rIndex, shape);
        }
    }

    template <class V, class S, class P>
    __aicore__ inline void CalculatePadding(V& view, S& shape, P& padding)
    {
        if constexpr (!InnerPattern::TailA) {
            CalculatePatternARPadding(view, shape, padding);
        } else {
            CalculatePatternRAPadding(view, shape, padding);
        }
        RUN_LOG(
            "burstPaddingStart:%ld, burstPaddingLen:%ld, burstPaddingRepeat:%ld, rPaddingStart:%ld, "
            "rPaddingLen:%ld, "
            "rPaddingRepeat:%ld, aPaddingStart:%ld, aPaddingLen:%ld, aPaddingRepeat:%ld\n",
            padding.burstPaddingStart, padding.burstPaddingLen, padding.burstPaddingRepeat, padding.rPaddingStart,
            padding.rPaddingLen, padding.rPaddingRepeat, padding.aPaddingStart, padding.aPaddingLen,
            padding.aPaddingRepeat);
    }

    template <class V, class S, class P>
    __aicore__ inline void CalculatePatternARPadding(V& view, S& shape, P& padding)
    {
        const uint64_t blkSize = static_cast<uint64_t>(UB_BLOCK / sizeof(InDType));
        const uint64_t alignSize = view.isBlockAligned == 1U ? blkSize : 1UL;
        const bool isLastSplit = IsLoopSpliteRAxis<LoopInfo>(Dim - 1);
        const uint64_t mainBurstLen = isLastSplit ? this->ubFactorR_ : view.axis[0].repeat;
        const uint64_t busrtLen = view.axis[0].repeat;
        const uint64_t mainBurstLenAlign = Ops::Base::CeilAlign(mainBurstLen, alignSize);
        const uint64_t dimRAlign = Ops::Base::CeilAlign(static_cast<uint64_t>(shape.value[1]), blkSize);
        int32_t burstPaddingRepeat = 1;
        int32_t rPaddingRepeat = 1;
        int32_t rPaddingStart = 1;
        int32_t aPaddingStart = 1;
        int32_t aPaddingTimes = 0;
        for (uint64_t i = 1; i < view.axisSize; i++) {
            if (!view.axis[i].isAxisA) {
                if (IsLoopSpliteRAxis<LoopInfo>(view.axis[i].idx)) {
                    rPaddingStart = view.axis[i].repeat;
                    break;
                } else {
                    burstPaddingRepeat *= view.axis[i].repeat;
                }
            }
        }
        // busrtLen补pad的起始位置
        padding.burstPaddingStart = view.axis[0].repeat;
        // busrtLen补pad长度为主块长度-尾块长度
        padding.burstPaddingLen = mainBurstLenAlign - busrtLen;
        // busrtLen补pad循环次数为R轴切分相同部分的大小
        padding.burstPaddingRepeat = burstPaddingRepeat * rPaddingStart;
        // R轴补pad的起始位置，即主块/尾块R轴切分的最后位置
        padding.rPaddingStart = rPaddingStart * burstPaddingRepeat * mainBurstLenAlign;
        // R轴pad的长度
        padding.rPaddingLen = dimRAlign - padding.rPaddingStart;
        // R轴补pad的循环次数，为A轴切分相同部分的大小
        // 因为以A轴为外循环，A轴大小在R轴循环过程中始终一致，每次A轴循环时，会重新计算shape大小
        padding.rPaddingRepeat = shape.value[0];
        // A轴补pad的起始位置，即主块/尾块A轴切分的最后位置
        padding.aPaddingStart = rPaddingRepeat * shape.value[1];
        // A轴pad的长度
        padding.aPaddingLen = 0;
        padding.aPaddingRepeat = 1;
    }

    template <class V, class S, class P>
    __aicore__ inline void CalculatePatternRAPadding(V& view, S& shape, P& padding)
    {
        const uint64_t blkSize = static_cast<uint64_t>(UB_BLOCK / sizeof(InDType));
        const uint64_t alignSize = view.isBlockAligned == 1U ? blkSize : 1UL;
        const uint64_t mainBurstLen = view.axis[0].repeat;
        const uint64_t busrtLen = view.axis[0].repeat;
        const uint64_t mainBurstLenAlign = Ops::Base::CeilAlign(mainBurstLen, alignSize);
        const uint64_t dimAAlign = Ops::Base::CeilAlign(static_cast<uint64_t>(shape.value[1]), blkSize);
        int32_t burstPaddingRepeat = 1;
        int32_t aPaddingRepeat = 1;
        int32_t rPaddingStart = 1;
        int32_t rPaddingTimes = 0;
        int32_t aPaddingStart = 1;
        for (uint64_t i = 1; i < view.axisSize; i++) {
            if (view.axis[i].isAxisA) {
                burstPaddingRepeat *= view.axis[i].repeat;
            }
        }
        padding.burstPaddingStart = view.axis[0].repeat;
        // busrtLen补pad长度为主块长度-尾块长度
        padding.burstPaddingLen = mainBurstLenAlign - busrtLen;
        // busrtLen补pad循环次数为A轴切分相同部分的大小
        padding.burstPaddingRepeat = burstPaddingRepeat * aPaddingStart;
        // A轴补pad的起始位置，即主块/尾块A轴切分的最后位置
        padding.aPaddingStart = aPaddingStart * burstPaddingRepeat * mainBurstLenAlign;
        // A轴pad的长度
        padding.aPaddingLen = dimAAlign - padding.aPaddingStart;
        for (uint64_t i = 1; i < view.axisSize; i++) {
            if (!view.axis[i].isAxisA) {
                if (IsLoopSpliteRAxis<LoopInfo>(view.axis[i].idx)) {
                    rPaddingStart = view.axis[i].repeat;
                    rPaddingTimes = this->ubFactorR_ - view.axis[i].repeat;
                    break;
                } else {
                    aPaddingRepeat *= view.axis[i].repeat;
                }
            }
        }
        // A轴补pad的循环次数，为R轴切分相同部分的大小，rPaddingStart=0时，表示R轴切分主块
        padding.aPaddingRepeat = aPaddingRepeat * rPaddingStart;
        // R轴补pad的起始位置，即主块/尾块R轴切分的最后位置
        padding.rPaddingStart = rPaddingStart * aPaddingRepeat * shape.value[1];
        // R轴pad的长度
        padding.rPaddingLen = rPaddingTimes * aPaddingRepeat * shape.value[1];
        padding.rPaddingRepeat = 1;
    }

    template <int32_t LoopInnerRIdx>
    __aicore__ inline void CalculateInnerIterR(uint64_t basicBlockIdx)
    {
        if constexpr (LoopInnerRIdx != 0) {
            constexpr auto axis = LoopInfo->loopInnerRAxis[LoopInnerRIdx - 1];
            if constexpr (LoopInnerRIdx == LoopInfo->loopInnerRCount) {
                auto cur = basicBlockIdx % this->loopRAxisStep_;
                this->iterAddr_[axis].start = cur * this->ubFactorR_;
                this->iterAddr_[axis].stride = tiling_->shape[axis] - this->iterAddr_[axis].start;
                if (likely(this->iterAddr_[axis].stride >= this->ubFactorR_)) {
                    this->iterAddr_[axis].stride = this->ubFactorR_;
                }
                CalculateInnerIterR<LoopInnerRIdx - 1>(basicBlockIdx / this->loopRAxisStep_);
            } else {
                this->iterAddr_[axis].start = basicBlockIdx % tiling_->shape[axis];
                this->iterAddr_[axis].stride = 1;
                CalculateInnerIterR<LoopInnerRIdx - 1>(basicBlockIdx / tiling_->shape[axis]);
            }
        }
    }

    template <int32_t LoopRIdx>
    __aicore__ inline void CalculateIterR(uint64_t step)
    {
        uint64_t temp = step;
        if constexpr (LoopRIdx != 0) {
            for (auto idx = LoopInfo->loopRCount - 1; idx > -1; --idx) {
                if (idx == LoopInfo->loopRCount - 1) {
                    constexpr auto axis = LoopInfo->loopRAxis[LoopInfo->loopRCount - 1];
                    auto cur = temp % this->loopRAxisStep_;
                    this->iterAddr_[axis].start = cur * this->ubFactorR_;
                    this->iterAddr_[axis].stride = tiling_->shape[axis] - this->iterAddr_[axis].start;
                    if (likely(this->iterAddr_[axis].stride >= this->ubFactorR_)) {
                        this->iterAddr_[axis].stride = this->ubFactorR_;
                    }
                    temp = temp / this->loopRAxisStep_;
                } else {
                    auto axis = LoopInfo->loopRAxis[idx];
                    if (IsLoopSpliteAAxis<LoopInfo>(axis)) {
                        // axis both in AAxis and RAxis
                        auto cur = temp % this->loopAAxisStep_;
                        this->iterAddr_[axis].start = cur * this->ubFactorA_;
                        this->iterAddr_[axis].stride = tiling_->shape[axis] - this->iterAddr_[axis].start;
                        if (likely(this->iterAddr_[axis].stride >= this->ubFactorA_)) {
                            this->iterAddr_[axis].stride = this->ubFactorA_;
                        }
                        temp = temp / this->loopAAxisStep_;
                    } else {
                        this->iterAddr_[axis].start = temp % tiling_->shape[axis];
                        this->iterAddr_[axis].stride = 1;
                        temp = temp / tiling_->shape[axis];
                    }
                }
            }
        }
    }

    template <class V>
    __aicore__ inline void InitView(V& view)
    {
        constexpr static auto burstLenAxis = Dim - 1;  // 获取第一个循环轴
        view.axis[0].start = iterAddr_[burstLenAxis].start;
        view.axis[0].srcStride = 1;
        view.axis[0].repeat = GetBurstLen<LoopInfo, burstLenAxis>(iterAddr_, tiling_);
        view.axis[0].idx = burstLenAxis;
        view.axis[0].isAxisA = IsAxisA<Pattern::FirstA>(view.axis[0].idx);
        view.axisSize = 1;

        if constexpr (burstLenAxis > 0) {
            int32_t axis = burstLenAxis;
            for (int32_t i = 1; i < Dim; i++) {
                view.axisSize = i + 1;
                view.axis[i].start = iterAddr_[axis - 1].start;
                view.axis[i].repeat =
                    GetRepeatStride<LoopInfo>(axis - 1, iterAddr_, tiling_, view.axis[i].srcStride);
                view.axis[i].idx = axis - 1;
                view.axis[i].isAxisA = IsAxisA<Pattern::FirstA>(view.axis[i].idx);
                if (view.axis[i].idx <= 0) {
                    break;
                }
                axis = view.axis[i].idx;
            }
        }
        view.isBlockAligned = (tiling_->useNddma == 0);
    }

    template <class V, class S>
    __aicore__ inline void CalculateInnerShapeARMode(V& view, S& shape)
    {
        int64_t rSize = 1;
        int64_t aSize = 1;
        for (uint64_t i = 1; i < view.axisSize; i++) {
            if (view.axis[i].isAxisA) {
                // 第一个A轴的dstStride就是R轴大小
                rSize = (rSize == 1) ? view.axis[i].dstStride : rSize;
                aSize = aSize * view.axis[i].repeat;
            }
        }
        shape.value[InnerPattern::Dim - 1] = rSize;
        shape.value[InnerPattern::Dim - 2] = aSize;
    }

    template <class V, class S>
    __aicore__ inline void CalculateInnerShapeRAMode(V& view, S& shape)
    {
        int64_t rSize = 1;
        int64_t aSize = 1;
        if constexpr (Pattern::ID == PATTERN_A) {
            aSize = view.axis[0].repeat;
        }
        for (uint64_t i = 1; i < view.axisSize; i++) {
            if (!view.axis[i].isAxisA) {
                // 第一个R轴的dstStride就是A轴大小
                aSize = (aSize == 1) ? view.axis[i].dstStride : aSize;
                if (IsLoopSpliteRAxis<LoopInfo>(view.axis[i].idx)) {
                    rSize = rSize * this->ubFactorR_;
                } else {
                    rSize = rSize * view.axis[i].repeat;
                }
            }
        }

        shape.value[InnerPattern::Dim - 1] = aSize;
        shape.value[InnerPattern::Dim - 2] = rSize;
    }

    // 根据copyIn的view参数计算内部shape大小
    template <class V, class S>
    __aicore__ inline void CalculateInnerShape(V& view, S& shape)
    {
        // 每次A轴循环时，value为0
        if (shape.value[0] != 0) {
            return;
        }
        if constexpr (!InnerPattern::TailA) {
            CalculateInnerShapeARMode(view, shape);
        } else {
            CalculateInnerShapeRAMode(view, shape);
        }
    }

    template <int32_t pos, class V, class S>
    __aicore__ inline void RunPreOp(V& view, S& shape, int32_t pingPong, int32_t idx)
    {
        using ElemOp = typename OpDag::FunList::template At<pos>;
        using Func = typename ElemOp::Fun;
        RUN_LOG("RUN.Func[%s]: ArgsSize:%ld, InArgsSize:%ld\n", PRINT_TYPE(Func), ElemOp::Args::Size,
                ElemOp::InArgs::Size);
        if constexpr (__aux::IsSameTemplateType<Func, Vec::CopyIn>::Value) {
            CopyIn<ElemOp, pos>(view, shape, pingPong, idx);
        } else if constexpr (Vec::IsCastOp<Func>::Value &&
                             IsSameType<typename ElemOp::template FunRetArgType<1>,
                                        typename ElemOp::template FunRetArgType<0>>::value) {
            RUN_LOG("Cast with same src and dst type, skip cast.\n");
        } else {
            RunNormalOp<ElemOp, pos>(shape, pingPong);
        }
        if constexpr (pos + 1 < OpDag::ReduceOpPos) {
            RunPreOp<pos + 1>(view, shape, pingPong, idx);
        }
    }

    template <int32_t pos, class V, class S>
    __aicore__ inline void RunPostOp(int32_t aIndex, V& view, S& shape)
    {
        using ElemOp = typename OpDag::FunList::template At<pos>;
        using Func = typename ElemOp::Fun;
        RUN_LOG("RUN.Func[%s]: ArgsSize:%ld, InArgsSize:%ld, Pos:%d\n", PRINT_TYPE(Func), ElemOp::Args::Size,
                ElemOp::InArgs::Size, pos);
        if constexpr (Vec::IsReduceOp<Func>::Value) {
            CopyFromReduce<ElemOp>(aIndex, shape);
        } else if constexpr (__aux::IsSameTemplateType<Func, Vec::CopyOut>::Value) {
            CopyOut<ElemOp, pos>(view, shape);
        } else if constexpr (__aux::IsSameTemplateType<Func, Vec::CopyIn>::Value) {
            PostCopyIn<ElemOp, pos>(shape);
        } else if constexpr (Vec::IsCastOp<Func>::Value &&
                             IsSameType<typename ElemOp::template FunRetArgType<1>,
                                        typename ElemOp::template FunRetArgType<0>>::value) {
            RUN_LOG("Cast with same src and dst type, skip cast.\n");
        } else {
            RunNormalOp<ElemOp, pos>(shape, 0);
        }
        if constexpr (pos + 1 < OpDag::FunList::Size) {
            RunPostOp<pos + 1>(aIndex, view, shape);
        }
    }

    template <class ElemOp, int32_t pos, class V, class S>
    __aicore__ inline void CopyIn(V& view, S& shape, int32_t pingPong, int32_t idx)
    {
        static_assert(ElemOp::InHolders::Size == 1, "CopyIn input inHolders num should be 1.");
        using Input = typename ElemOp::InHolders::template At<0>;
        using InputType = typename ElemOp::template FunInArgType<0>;
        static_assert(IsSameType<typename Input::DType, InputType>::value,
                      "CopyIn data type is inconsistent with Opdata type.");

        // Prepare Input args
        uint8_t bufId = GetPreBufId<pos>(pingPong, idx);
        LocalTensor<InputType> inTensor = sch_->ReduceSch::template AllocTensorAux<InputType, pos>(bufId);
#ifndef __CCE_KT_TEST__
        inTensor.SetBufferLen(eleNum_);
#endif

        GlobalTensor<InputType> globalTensor;
        globalTensor.SetGlobalBuffer(reinterpret_cast<__gm__ InputType*>(input_[Input::Pos].GetPhyAddr(0)));
        CalculateInView<InputType>(view);
        // Run copyIn
        GetTensor<TPosition::VECIN>(bufId);
        sch_->ReduceSch::template CopyInAux<pos, InnerPattern>(inTensor, globalTensor, view);
        ReleaseTensor<TPosition::VECIN>(bufId);

        CalculateInnerShape(view, shape);
    }

    template <class ElemOp, class S>
    __aicore__ inline void CopyFromReduce(int32_t aIndex, S& shape)
    {
        using InputType = typename ElemOp::template FunInArgType<0>;
        static_assert(IsSameType<DataType, InputType>::value, "CopyIn data type is inconsistent with Opdata type.");

        if constexpr (Pattern::ID == PATTERN_A) {
            // 纯A场景属于normal R轴全载, 使用A轴索引开pingpong
            SetEvent<HardEvent::MTE3_V>(HardEvent::MTE3_V);
            reduceOut_ = sch_->ReduceSch::template GetReduceResAux<InputType>();
            int32_t pingPong = aIndex & 1;
            int32_t idx = (aIndex / CONST2) & 1;
            auto input = GetInputTensor<ElemOp, 0>(pingPong, eleNum_, idx);
            DataCopy(reduceOut_, input, shape.value[0] * shape.value[1]);
            ReleaseInputTensor<ElemOp, 0>(pingPong, idx);
        } else {
            int64_t dimAAlign = Ops::Base::CeilAlign(shape.value[1], static_cast<int64_t>(VL_ELEMS));
            sch_->ReduceSch::template GetCacheAux(reduceOut_, (cacheCount_ - 1) * dimAAlign);
        }
    }

    template <class ElemOp, int32_t pos, class S>
    __aicore__ inline void PostCopyIn(S& shape)
    {   
        using Input = typename ElemOp::InHolders::template At<0>;
        using RetType = typename ElemOp::template FunRetArgType<0>;
        uint8_t bufId = GetBufId<pos>(0);
        uint8_t syncId = bufId + preBufNum_;
        LocalTensor<RetType> out = sch_->ReduceSch::template AllocTensorAux<RetType, pos>(bufId);
        GlobalTensor<RetType> globalTensor;
        globalTensor.SetGlobalBuffer(reinterpret_cast<__gm__ RetType*>(input_[Input::Pos].GetPhyAddr(0)));
#ifndef __CCE_KT_TEST__
        int32_t eleNum = tiling_->resultBlock / sizeof(PromoteDType);
        out.SetBufferLen(eleNum);
#endif
        GetTensor<TPosition::VECIN>(syncId);
        DataCopy(out, globalTensor, shape.value[0] * shape.value[1]);
        ReleaseTensor<TPosition::VECIN>(syncId);
    }

    template <typename ElemOp, int32_t pos, int ArgPos>
    __aicore__ inline auto ConvertArgs(int32_t pingPong)
    {
        using InputOp = typename ElemOp::InArgs::template At<ArgPos>;
        using TensorType = typename ElemOp::template FunInArgType<ArgPos>;
        if constexpr (__aux::TypeIsFunBind<InputOp>::Value) {
            if constexpr (InputOp::IsScalarOp) {
                TensorType scalar = sch_->ReduceSch::template GetScalar<TensorType, InputOp>();
                return scalar;
            } else {
                // 判断当前输入是否是同一个操作的多引用输出，避免重复插入同步
                int32_t eleNum = pos < OpDag::ReduceOpPos ? tiling_->basicBlock / sizeof(InDType)
                                                          : tiling_->resultBlock / sizeof(PromoteDType);
                auto inputTensor = GetInputTensor<ElemOp, ArgPos>(pingPong, eleNum);
                return inputTensor;
            }
        } else {
            TensorType scalar = sch_->ReduceSch::template GetScalar<TensorType, InputOp>();
            return scalar;
        }
    }

    template <typename ElemOp, int ArgPos>
    __aicore__ inline void TryReleaseArgs(int32_t pingPong)
    {
        using InputOp = typename ElemOp::InArgs::template At<ArgPos>;
        if constexpr (__aux::TypeIsFunBind<InputOp>::Value) {
            if constexpr (!InputOp::IsScalarOp) {
                ReleaseInputTensor<ElemOp, ArgPos>(pingPong);
            }
        }
    }

    template <typename ElemOp, int32_t pos, size_t... I>
    __aicore__ inline auto MakeArgs(int32_t pingPong, AscendC::Std::index_sequence<I...>)
    {
        return AscendC::Std::make_tuple(ConvertArgs<ElemOp, pos, I>(pingPong)...);
    }

    template <class ElemOp, int32_t pos>
    __aicore__ inline auto PrepareArgs(int32_t pingPong)
    {
        return MakeArgs<ElemOp, pos>(pingPong, AscendC::Std::make_index_sequence<ElemOp::InputSize>{});
    }

    template <typename Func, typename OutputType, typename Tuple, size_t... I>
    __aicore__ inline auto CallImpl(LocalTensor<OutputType>& outTensor, Tuple& inputs, uint64_t tileLength,
                                    AscendC::Std::index_sequence<I...>)
    {
        return Func(outTensor, AscendC::Std::get<I>(inputs)..., tileLength);
    }

    template <typename Func, typename OutputType, typename Tuple>
    __aicore__ inline auto Call(LocalTensor<OutputType>& outTensor, Tuple& inputs, uint64_t tileLength)
    {
        return CallImpl<Func, OutputType>(outTensor, inputs, tileLength,
                                          AscendC::Std::make_index_sequence<AscendC::Std::tuple_size<Tuple>::value>{});
    }

    template <typename Func, typename OutputType, typename Tuple, size_t... I>
    __aicore__ inline auto CallImpl(OutputType& outScalar, Tuple& inputs, uint64_t tileLength,
                                    AscendC::Std::index_sequence<I...>)
    {
        return Func(outScalar, AscendC::Std::get<I>(inputs)..., tileLength);
    }

    template <typename Func, typename OutputType, typename Tuple>
    __aicore__ inline auto Call(OutputType& outScalar, Tuple& inputs, uint64_t tileLength)
    {
        return CallImpl<Func, OutputType>(outScalar, inputs, tileLength,
                                          AscendC::Std::make_index_sequence<AscendC::Std::tuple_size<Tuple>::value>{});
    }

    template <typename ElemOp, size_t... I>
    __aicore__ inline void DoPostArgs(int32_t pingPong, AscendC::Std::index_sequence<I...>)
    {
        (TryReleaseArgs<ElemOp, I>(pingPong), ...);
    }

    template <class ElemOp>
    __aicore__ inline void PostArgs(int32_t pingPong)
    {
        DoPostArgs<ElemOp>(pingPong, AscendC::Std::make_index_sequence<ElemOp::InputSize>{});
    }

    template <class ElemOp, int32_t pos, typename OutputType, class S>
    __aicore__ inline constexpr void RunOp(LocalTensor<OutputType>& outTensor, S& shape, int32_t pingPong)
    {
        using Func = typename ElemOp::Fun;
        uint64_t tileLength = shape.value[0] * shape.value[1];
        auto inputArgs = PrepareArgs<ElemOp, pos>(pingPong);
        Call<Func, OutputType>(outTensor, inputArgs, tileLength);
        PostArgs<ElemOp>(pingPong);
    }

    template <class ElemOp, int32_t pos, class S>
    __aicore__ inline constexpr void RunNormalOp(S& shape, int32_t pingPong)
    {
        constexpr bool isPre = pos < OpDag::ReduceOpPos;
        using RetType = typename ElemOp::template FunRetArgType<0>;
        uint8_t bufId = GetBufId<pos>(pingPong);
        uint8_t syncId = isPre ? bufId : bufId + preBufNum_;
        LocalTensor<RetType> out = sch_->ReduceSch::template AllocTensorAux<RetType, pos>(bufId);
#ifndef __CCE_KT_TEST__
        int32_t eleNum = pos < OpDag::ReduceOpPos ? tiling_->basicBlock / sizeof(InDType)
                                                  : tiling_->resultBlock / sizeof(PromoteDType);
        out.SetBufferLen(eleNum);
#endif
        GetTensor<TPosition::VECCALC>(syncId);

        RunOp<ElemOp, pos>(out, shape, pingPong);

        ReleaseTensor<TPosition::VECCALC>(syncId);
    }

    template <class V, class S>
    __aicore__ inline void CopyInNoPreOp(V& view, S& shape, int32_t pingPong, int32_t idx)
    {
        uint8_t bufId = GetPreBufId<0>(pingPong, idx);
        LocalTensor<InDType> inTensor = sch_->ReduceSch::template AllocTensorAux<InDType, 0>(bufId);
#ifndef __CCE_KT_TEST__
        inTensor.SetBufferLen(eleNum_);
#endif
        CalculateInView<InDType>(view);
        GlobalTensor<InDType> globalTensor;
        globalTensor.SetGlobalBuffer(reinterpret_cast<__gm__ InDType*>(workspace_[0].GetPhyAddr(0)));
        // Run copyIn
        GetTensor<TPosition::VECIN>(bufId);
        sch_->ReduceSch::template CopyInAux<0, InnerPattern>(inTensor, globalTensor, view);
        ReleaseTensor<TPosition::VECIN>(bufId);

        CalculateInnerShape(view, shape);
    }

    template <class T, class V>
    __aicore__ inline void CalculateViewARMode(V& view)
    {
        uint64_t alignedValue = (view.isBlockAligned == 1 ? (UB_BLOCK / sizeof(T)) : 1UL);
        int64_t value = Ops::Base::CeilAlign(view.axis[0].repeat, alignedValue);
        view.axis[0].dstStride = 1;
        if (IsLoopSpliteRAxis<LoopInfo>(Pattern::Dim - 1)) {
            // R是切分轴时, 主尾块会先add起来, 所以R轴按照factorR算
            value = Ops::Base::CeilAlign(tiling_->ubFactorR, alignedValue);
        }
        // 因A轴循环会重新触发shape计算，所以A轴的shape不需要统一到ubFactorA,但是R轴shape需要统一到ubFactorR
        for (uint64_t i = 1; i < view.axisSize; i++) {
            if (!view.axis[i].isAxisA) {
                view.axis[i].dstStride = value;
                if (IsLoopSpliteRAxis<LoopInfo>(view.axis[i].idx)) {
                    value = value * tiling_->ubFactorR;
                } else {
                    value = value * view.axis[i].repeat;
                }
            }
        }
        // nddma 整个R轴乘积block对齐
        if (view.isBlockAligned != 1) {
            value = Ops::Base::CeilAlign(static_cast<uint64_t>(value), UB_BLOCK / sizeof(T));
        }
        for (uint64_t i = 1; i < view.axisSize; i++) {
            if (view.axis[i].isAxisA) {
                view.axis[i].dstStride = value;
                value = value * view.axis[i].repeat;
            }
        }
    }

    template <class T, class V>
    __aicore__ inline void CalculateViewRAMode(V& view)
    {
        uint64_t alignedValue = (view.isBlockAligned == 1 ? (UB_BLOCK / sizeof(T)) : 1UL);
        int64_t value = Ops::Base::CeilAlign(view.axis[0].repeat, alignedValue);
        view.axis[0].dstStride = 1;
        // 因A轴循环会重新触发shape计算，所以A轴的shape不需要统一到ubFactorA,但是R轴shape需要统一到ubFactorR
        for (uint64_t i = 1; i < view.axisSize; i++) {
            if (view.axis[i].isAxisA) {
                view.axis[i].dstStride = value;
                value = value * view.axis[i].repeat;
            }
        }
        // nddma 整个A轴乘积block对齐
        if (view.isBlockAligned != 1) {
            value = Ops::Base::CeilAlign(static_cast<uint64_t>(value), UB_BLOCK / sizeof(T));
        }
        for (uint64_t i = 1; i < view.axisSize; i++) {
            if (!view.axis[i].isAxisA) {
                view.axis[i].dstStride = value;
                if (IsLoopSpliteRAxis<LoopInfo>(view.axis[i].idx)) {
                    value = value * tiling_->ubFactorR;
                } else {
                    value = value * view.axis[i].repeat;
                }
            }
        }
    }

    template <class T, class V>
    __aicore__ inline void CalculateView(V& view)
    {
        if constexpr (!Pattern::TailA) {
            CalculateViewARMode<T>(view);
        } else {
            CalculateViewRAMode<T>(view);
        }
    }

    template <class T, class V>
    __aicore__ inline void CalculateInView(V& view)
    {
        uint64_t addrOffset = 0;
        for (int32_t i = 0; i < Pattern::Dim; i++) {
            addrOffset += view.axis[i].start * view.axis[i].srcStride;
        }
        view.addr = addrOffset;  // 搬运地址
        if (view.axis[0].dstStride == 0) {
            CalculateView<T>(view);
        }
    }

    template <class V, class S>
    __aicore__ inline void CalculateOutView(V& view, S& shape, uint64_t& outLen, uint64_t& outRepeat)
    {
        if constexpr (Pattern::TailA) {
            outLen = view.axis[0].repeat;
            outRepeat = 1;
            for (uint64_t i = 1; i < view.axisSize; i++) {
                if (view.axis[i].isAxisA) {
                    outRepeat = outRepeat * view.axis[i].repeat;
                }
            }
            if (view.isBlockAligned == 0) {
                outLen = outLen * outRepeat;
                outRepeat = 1;
            }
        } else {
            outLen = shape.value[0];
            outRepeat = 1;
        }
    }

    template <class V, class S>
    __aicore__ inline void PostReduce(int32_t aIndex, V& view, S& shape)
    {
        constexpr int32_t axis = Pattern::FirstA ? 0 : 1;
        uint64_t addrOffset = 0;
        for (int32_t i = axis; i < Dim; i += CONST2) {
            addrOffset += this->iterAddr_[i].start * tiling_->dstStride[i];
        }

        SliceView<CONST2> newView;
        newView.addr = addrOffset;

        uint64_t outLen = 1;
        uint64_t outRepeat = 1;
        CalculateOutView(view, shape, outLen, outRepeat);
        newView.axis[0].repeat = outLen;
        newView.axis[1].repeat = outRepeat;

        S newShape;
        newShape.value[0] = 1;
        newShape.value[1] = outRepeat * Ops::Base::CeilAlign(outLen, UB_BLOCK / sizeof(InDType));
        RunPostOp<OpDag::ReduceOpPos>(aIndex, newView, newShape);
    }

    template <typename ElemOp, int pos, class V, class S>
    __aicore__ inline void CopyOut(V& view, S& shape)
    {
        static_assert(ElemOp::Args::Size == 2, "Input args should be 2");
        using Input = typename ElemOp::Args::template At<1>;
        using Output = typename ElemOp::Args::template At<0>;
        static_assert(Placeholder::IsOutHolder<Output>::Value, "output args should be out holder");
        static_assert(IsSameType<typename Output::DType, OutDType>::value,	 
                      "CopyOut data type is inconsistent with Op data type.");

        GlobalTensor<OutDType> globalTensor;
        globalTensor.SetGlobalBuffer(reinterpret_cast<__gm__ OutDType*>(output_[Output::Pos].GetPhyAddr(0)));

        if constexpr (Vec::IsReduceOp<typename Input::Fun>::Value) {
            SetEvent<HardEvent::V_MTE3>(HardEvent::V_MTE3);
            sch_->ReduceSch::template CopyOutAux(globalTensor, reduceOut_, view);
        } else {
            uint8_t bufId = GetPostBufId<GetFunOutputPos<Input>()>();
            uint8_t syncId = bufId + preBufNum_;
            LocalTensor<OutDType> src =
                sch_->ReduceSch::template AllocTensorAux<OutDType, GetFunOutputPos<Input>()>(bufId);
            GetTensor<TPosition::VECOUT>(syncId);
            sch_->ReduceSch::template CopyOutAux(globalTensor, src, view);
            ReleaseTensor<TPosition::VECOUT>(syncId);
        }
    }

    template <class V, class S>
    __aicore__ inline void CopyOutGroup(V& view, S& shape)
    {
        static_assert(IsSameType<PromoteDType, DataType>::value, "group copy out dtype must be same with pre dag out.");
        // CopyOut As RA Pattern
        SliceView<CONST2> newView;
        int32_t blockId = GetBlockIdx();
        int32_t innerA = CaculateInnerA<LoopInfo, Pattern::TailA, Pattern::Dim>(iterAddr_);
        uint64_t outLen = 1;
        uint64_t outRepeat = 1;
        CalculateOutView(view, shape, outLen, outRepeat);
        newView.axis[0].repeat = outLen;
        newView.axis[1].repeat = outRepeat;
        if constexpr (Pattern::TailA) {
            newView.axis[1].srcStride = Ops::Base::CeilAlign(outLen, UB_BLOCK / sizeof(InDType));
        } else {
            newView.axis[1].srcStride = outLen;
        }
        int32_t axis = Pattern::FirstA ? 0 : 1;
        if constexpr (LoopInfo->loopACount > 0) {
            axis = LoopInfo->loopAAxis[LoopInfo->loopACount - 1];
        }

        uint64_t addrOffset = 0;
        if constexpr (LoopInfo->loopInnerACount > 0) {
            for (int32_t i = axis; i < Dim; i += CONST2) {
                addrOffset += this->iterAddr_[i].start * tiling_->dstStride[i];
            }
        }

        uint64_t axisStep = LoopInfo->loopACount > 0 ? this->loopAAxisStep_ : 1;
        newView.addr = (blockId % tiling_->groupR) *
                           Ops::Base::CeilAlign(tiling_->outSize, static_cast<uint64_t>(VL_ELEMS)) +     // group offset
                       (blockId / (tiling_->groupR * axisStep)) * tiling_->shape[axis] * innerA +  // AAxis offset
                       (blockId / tiling_->groupR % axisStep) * this->ubFactorA_ * innerA +        // main offset
                       addrOffset;                                                                 // innerA offset

        SetEvent<HardEvent::V_MTE3>(HardEvent::V_MTE3);
        LocalTensor<PromoteDType> outTensor;
        int64_t dimA = Pattern::TailA ? shape.value[1] : shape.value[0];
        int64_t dimAAlign = Ops::Base::CeilAlign(dimA, static_cast<int64_t>(VL_ELEMS));
        sch_->ReduceSch::template GetCacheAux(outTensor, (cacheCount_ - 1) * dimAAlign);
        GlobalTensor<PromoteDType> globalTensor;
        globalTensor.SetGlobalBuffer(reinterpret_cast<__gm__ PromoteDType*>(workspace_[0].GetPhyAddr(0)));
        sch_->ReduceSch::template CopyOutAuxGroup(globalTensor, outTensor, newView);
    }

    template <typename T>
    __aicore__ inline constexpr LocalTensor<T> GetReduceInputTensor(int32_t pingPong, int32_t idx, int32_t tileLength)
    {
        if constexpr (IsSameType<OpDag, void>::value || !IsStageOne) {
            uint8_t bufId = GetPreBufId<0>(pingPong, idx);
            GetTensor<TPosition::VECCALC>(bufId);
            LocalTensor<T> tensor = sch_->ReduceSch::template AllocTensorAux<T, 0>(bufId);
#ifndef __CCE_KT_TEST__
            tensor.SetBufferLen(tileLength);
#endif
            return tensor;
        } else {
            using OpReduce = typename OpDag::FunList::template At<OpDag::ReduceOpPos>;
            LocalTensor<T> tensor = GetInputTensor<OpReduce, 0>(pingPong, tileLength, idx);
            return tensor;
        }
    }

    __aicore__ inline constexpr void ReleaseReduceInputTensor(int32_t pingPong, int32_t idx)
    {
        if constexpr (IsSameType<OpDag, void>::value || !IsStageOne) {
            uint8_t bufId = GetPreBufId<0>(pingPong, idx);
            ReleaseTensor<TPosition::VECCALC>(bufId);
        } else {
            using OpReduce = typename OpDag::FunList::template At<OpDag::ReduceOpPos>;
            ReleaseInputTensor<OpReduce, 0>(pingPong, idx);
        }
    }

    template <int32_t pos>
    __aicore__ inline constexpr uint8_t GetPreBufId(int32_t pingPong, int32_t idx = 0)
    {
        if constexpr (preBufferIds_[0][pos] == preBufferIds_[1][pos]) {
            return preBufferIds_[0][pos];
        } else {
            if constexpr (OpDag::ReduceOpPos == 1 || !IsStageOne) {
                return pingPong == 0 ? preBufferIds_[0][idx] : preBufferIds_[1][idx];
            } else {
                return pingPong == 0 ? preBufferIds_[0][pos] : preBufferIds_[1][pos];
            }
        }
    }

    template <int32_t pos>
    __aicore__ inline constexpr uint8_t GetPostBufId()
    {
        return postBufferIds_[0][pos - OpDag::ReduceOpPos - 1];
    }

    template <int32_t pos>
    __aicore__ inline constexpr uint8_t GetBufId(int32_t pingPong, int32_t idx = 0)
    {
        constexpr bool isPre = pos < OpDag::ReduceOpPos;
        uint8_t bufId = 0;
        if constexpr (isPre) {
            bufId = GetPreBufId<pos>(pingPong, idx);
        } else {
            bufId = GetPostBufId<pos>();
        }
        return bufId;
    }

    template <class Op, int32_t ArgPos>
    __aicore__ inline constexpr auto GetInputTensor(int32_t pingPong, int32_t tileLength, int32_t idx = 0)
    {
        using InputOp = typename Op::InArgs::template At<ArgPos>;
        using TensorType = typename Op::template FunInArgType<ArgPos>;
        if constexpr (Vec::IsReduceOp<typename InputOp::Fun>::Value) {
            return reduceOut_;
        } else {
            constexpr int32_t pos = GetFunOutputPos<InputOp>();
            constexpr bool isPre = pos < OpDag::ReduceOpPos;
            constexpr bool isDuplicate = Op::InArgs::template IsExist<InputOp, ArgPos + 1>();
            uint8_t bufId = GetBufId<pos>(pingPong, idx);
            if constexpr (!isDuplicate) {
                uint8_t syncId = isPre ? bufId : bufId + preBufNum_;
                GetTensor<TPosition::VECCALC>(syncId);
            }
            LocalTensor<TensorType> tensor = sch_->ReduceSch::template AllocTensorAux<TensorType, pos>(bufId);
#ifndef __CCE_KT_TEST__
            tensor.SetBufferLen(tileLength);
#endif
            return tensor;
        }
    }

    template <class ElemOp, int32_t ArgPos>
    __aicore__ inline constexpr void ReleaseInputTensor(int32_t pingPong, int32_t idx = 0)
    {
        using InputOp = typename ElemOp::InArgs::template At<ArgPos>;
        if constexpr (Vec::IsReduceOp<typename InputOp::Fun>::Value) {
            return;
        } else {
            constexpr int32_t pos = GetFunOutputPos<InputOp>();
            constexpr bool isPre = pos < OpDag::ReduceOpPos;
            constexpr bool isDuplicate = ElemOp::InArgs::template IsExist<InputOp, ArgPos + 1>();
            uint8_t bufId = GetBufId<pos>(pingPong, idx);
            if constexpr (!isDuplicate) {
                uint8_t syncId = isPre ? bufId : bufId + preBufNum_;
                ReleaseTensor<TPosition::VECCALC>(syncId);
            }
        }
    }

    template <class ElemOp, int start = 0>
    __aicore__ constexpr static inline int GetFunOutputPos()
    {
        if constexpr (IsSameType<typename OpDag::FunList::template At<start>, ElemOp>::value) {
            return start;
        } else if constexpr (start + 1 < OpDag::FunList::Size) {
            return GetFunOutputPos<ElemOp, start + 1>();
        }
        static_assert(start + 1 < OpDag::FunList::Size, "The required output in FunList is not found.");
        return -1;
    }
};
}  // namespace ReduceOpTmpl
} // namespace Base
} // namespace Ops
#endif