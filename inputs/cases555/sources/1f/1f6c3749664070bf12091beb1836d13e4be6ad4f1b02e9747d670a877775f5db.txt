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
 * \file resize_bilinear_v2_simt_nhwc.h
 * \brief resize_bilinear_v2_simt_nhwc
 */

#ifndef CANN_RESIZE_BILINEAR_V2_SIMT_NHWC_H
#define CANN_RESIZE_BILINEAR_V2_SIMT_NHWC_H

#include "kernel_operator.h"
#include "kernel_tiling/kernel_tiling.h"
#include "resize_bilinear_v2_base.h"
#include "simt_api/asc_simt.h"

namespace ResizeBilinearV2 {
using namespace AscendC;

template <typename T1, typename T2, bool halfPixel, int mode, typename T_IDX>
class ResizeBilinearV2SimtNHWC {
public:
    __aicore__ inline ResizeBilinearV2SimtNHWC(){};

    __aicore__ inline void Init(GM_ADDR grads, GM_ADDR size, GM_ADDR y, const ResizeBilinearV2TilingData* tilingData);
    __aicore__ inline void Process();

private:
    const ResizeBilinearV2TilingData* tilingData_;

    int64_t blockIdx_;
    GlobalTensor<T1> inputGm_;
    GlobalTensor<T2> outputGm_;
};

template <typename T1, typename T2, bool halfPixel, int mode, typename T_IDX>
__aicore__ inline void ResizeBilinearV2SimtNHWC<T1, T2, halfPixel, mode, T_IDX>::Init(
    GM_ADDR x, GM_ADDR size, GM_ADDR y, const ResizeBilinearV2TilingData* tilingData)
{
    blockIdx_ = GetBlockIdx();

    tilingData_ = tilingData;

    inputGm_.SetGlobalBuffer(
        (__gm__ T1*)x, tilingData_->lenN * tilingData_->lenC * tilingData_->lenSrcH * tilingData_->lenSrcW);
    outputGm_.SetGlobalBuffer(
        (__gm__ T2*)y, tilingData_->lenN * tilingData_->lenC * tilingData_->lenDesH * tilingData_->lenDesW);
}

template <typename T_IDX>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void QuickDivForSimtComputenhwc(
    T_IDX& N, T_IDX& H, T_IDX& W, T_IDX& C, T_IDX tmp, T_IDX mC_, T_IDX shiftC_, T_IDX lenC_, T_IDX mW_, T_IDX shiftW_,
    T_IDX lenDesW_, T_IDX mH_, T_IDX shiftH_, T_IDX lenDesH_, T_IDX mN_, T_IDX shiftN_, T_IDX lenN_)
{
    // 快速整除计算 tmp/lenC_
    T_IDX tmpRes = Simt::UintDiv(tmp, mC_, shiftC_);
    C = tmp - tmpRes * lenC_;
    tmp = tmpRes;

    tmpRes = Simt::UintDiv(tmp, mW_, shiftW_);
    W = tmp - tmpRes * lenDesW_;
    tmp = tmpRes;

    tmpRes = Simt::UintDiv(tmp, mH_, shiftH_);
    H = tmp - tmpRes * lenDesH_;
    tmp = tmpRes;

    tmpRes = Simt::UintDiv(tmp, mN_, shiftN_);
    N = tmp - tmpRes * lenN_;
}

template <typename T1, typename T2, bool halfPixel, int mode, typename T_IDX>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void SimtCompute(
    float scaleW_, float scaleH_, T_IDX lenN_, T_IDX lenC_, T_IDX lenSrcH_, T_IDX lenSrcW_, T_IDX lenDesH_,
    T_IDX lenDesW_, T_IDX splitBlockFactor_, T_IDX splitBlockTailFactor_, T_IDX shiftN_, T_IDX mN_, T_IDX shiftC_,
    T_IDX mC_, T_IDX shiftH_, T_IDX mH_, T_IDX shiftW_, T_IDX mW_, __gm__ T1* input, __gm__ T2* output,
    T_IDX blkStartOffset, T_IDX blkProcessNum)
{
    for (T_IDX idx = static_cast<T_IDX>(threadIdx.x); idx < blkProcessNum;
         idx += static_cast<T_IDX>(blockDim.x)) {
        T_IDX yGmIdx = blkStartOffset + idx;
        T_IDX tmp = yGmIdx;

        T_IDX N = 0, H = 0, W = 0, C = 0;

        QuickDivForSimtComputenhwc(
            N, H, W, C, tmp, mC_, shiftC_, lenC_, mW_, shiftW_, lenDesW_, mH_, shiftH_, lenDesH_, mN_, shiftN_, lenN_);

        float origHeight_ = 0.0f, origWidth_ = 0.0f, deltaX = 0.0f, deltaY = 0.0f;
        T_IDX leftX = 0, rightX = 0, topY = 0, bottomY = 0, lenSrcWC_ = lenSrcW_ * lenC_;
        // 场景1：输入输出大小相等，直接赋值
        // 场景2：输入是1个点，输出是多个点
        // 场景3：输入是多个点，输出是1个点
        if constexpr (mode == SIMT_SCENE_ALL_COPY) {
            output[yGmIdx] = input[N * lenSrcH_ * lenSrcWC_ + H * lenSrcWC_ + W * lenC_ + C];
            continue;
        } else if constexpr (mode == SIMT_SCENE_INPUT_ONE) {
            output[yGmIdx] = input[N * lenSrcWC_ + C];
            continue;
        } else if constexpr (mode == SIMT_SCENE_OUTPUT_ONE) {
            output[yGmIdx] = input[N * lenSrcH_ * lenSrcWC_ + C];
            continue;
        }

        // 计算原图中坐标点
        if constexpr (halfPixel) {
            origHeight_ = static_cast<float>((H + HALF_PIXEL) * scaleH_) - HALF_PIXEL;
            origWidth_ = static_cast<float>((W + HALF_PIXEL) * scaleW_) - HALF_PIXEL;
        } else {
            origHeight_ = static_cast<float>(H * scaleH_);
            origWidth_ = static_cast<float>(W * scaleW_);
        }
        if (origHeight_ < 0.0f) {
            origHeight_ = 0.0;
        }
        if (origWidth_ < 0.0f) {
            origWidth_ = 0.0;
        }

        // 计算原图坐标点附近四点的横坐标以及权重值
        leftX = (origWidth_ > 0.0f) ? floorf(origWidth_) : 0.0f;
        leftX = (leftX < lenSrcW_ - 1) ? leftX : lenSrcW_ - 1;
        rightX = (origWidth_ > 0.0f) ? ceilf(origWidth_) : 0.0f;
        rightX = (rightX < lenSrcW_ - 1) ? rightX : lenSrcW_ - 1;
        deltaX = origWidth_ - floorf(origWidth_);

        // 计算原图坐标点附近四点的纵坐标以及权重值
        topY = (origHeight_ > 0.0f) ? floorf(origHeight_) : 0.0f;
        topY = (topY < lenSrcH_ - 1) ? topY : lenSrcH_ - 1;
        bottomY = (origHeight_ > 0.0f) ? ceilf(origHeight_) : 0.0f;
        bottomY = (bottomY < lenSrcH_ - 1) ? bottomY : lenSrcH_ - 1;
        deltaY = origHeight_ - floorf(origHeight_);

        // 计算原图坐标点附近四个点的像素值
        T_IDX origBaseIdx = N * (lenSrcH_ * lenSrcWC_) + C;
        float pixelLeftTop = input[origBaseIdx + topY * lenSrcWC_ + leftX * lenC_];
        float pixelRightTop = input[origBaseIdx + topY * lenSrcWC_ + rightX * lenC_];
        float pixelLeftBottom = input[origBaseIdx + bottomY * lenSrcWC_ + leftX * lenC_];
        float pixelRightBottom = input[origBaseIdx + bottomY * lenSrcWC_ + rightX * lenC_];

        // 根据周围四个点像素值进行双线性差值，计算出输出像素值
        output[yGmIdx] = (1.0f - deltaY) * ((1.0f - deltaX) * pixelLeftTop + deltaX * pixelRightTop) +
                         deltaY * ((1.0f - deltaX) * pixelLeftBottom + deltaX * pixelRightBottom);
    }
}

template <typename T1, typename T2, bool halfPixel, int mode, typename T_IDX>
__simt_vf__ LAUNCH_BOUND(THREAD_NUM) __aicore__ void calleeInt32nhwc(
    float scaleW_, float scaleH_, T_IDX lenN_, T_IDX lenC_, T_IDX lenSrcH_, T_IDX lenSrcW_, T_IDX lenDesH_,
    T_IDX lenDesW_, T_IDX splitBlockFactor_, T_IDX splitBlockTailFactor_, T_IDX shiftN_, T_IDX mN_, T_IDX shiftC_,
    T_IDX mC_, T_IDX shiftH_, T_IDX mH_, T_IDX shiftW_, T_IDX mW_, __gm__ T1* input, __gm__ T2* output,
    T_IDX blkStartOffset, T_IDX blkProcessNum)
{
    SimtCompute<T1, T2, halfPixel, mode, T_IDX>(
        scaleW_, scaleH_, lenN_, lenC_, lenSrcH_, lenSrcW_, lenDesH_, lenDesW_, splitBlockFactor_,
        splitBlockTailFactor_, shiftN_, mN_, shiftC_, mC_, shiftH_, mH_, shiftW_, mW_, input, output, blkStartOffset,
        blkProcessNum);
}

template <typename T1, typename T2, bool halfPixel, int mode, typename T_IDX>
__simt_vf__ LAUNCH_BOUND(THREAD_NUM_MIDDLE) __aicore__ void calleeInt64nhwc(
    float scaleW, float scaleH, T_IDX lenN, T_IDX lenC, T_IDX lenSrcH, T_IDX lenSrcW, T_IDX lenDesH, T_IDX lenDesW,
    T_IDX splitBlockFactor, T_IDX splitBlockTailFactor, T_IDX shiftN, T_IDX mN, T_IDX shiftC, T_IDX mC, T_IDX shiftH,
    T_IDX mH, T_IDX shiftW, T_IDX mW, __gm__ T1* input, __gm__ T2* output, T_IDX blkStartOffset, T_IDX blkProcessNum)
{
    SimtCompute<T1, T2, halfPixel, mode, T_IDX>(
        scaleW, scaleH, lenN, lenC, lenSrcH, lenSrcW, lenDesH, lenDesW, splitBlockFactor, splitBlockTailFactor, shiftN,
        mN, shiftC, mC, shiftH, mH, shiftW, mW, input, output, blkStartOffset, blkProcessNum);
}

template <typename T1, typename T2, bool halfPixel, int mode, typename T_IDX>
__aicore__ inline void ResizeBilinearV2SimtNHWC<T1, T2, halfPixel, mode, T_IDX>::Process()
{
    T_IDX splitBlockFactor_ = tilingData_->splitBlockFactor;
    T_IDX splitBlockTailFactor_ = tilingData_->splitBlockTailFactor;

    T_IDX shiftN_ = 1;
    T_IDX mN_ = 1;
    T_IDX shiftC_ = 1;
    T_IDX mC_ = 1;
    T_IDX shiftH_ = 1;
    T_IDX mH_ = 1;
    T_IDX shiftW_ = 1;
    T_IDX mW_ = 1;

    GetUintDivMagicAndShift(mC_, shiftC_, static_cast<T_IDX>(tilingData_->lenC));
    GetUintDivMagicAndShift(mW_, shiftW_, static_cast<T_IDX>(tilingData_->lenDesW));
    GetUintDivMagicAndShift(mH_, shiftH_, static_cast<T_IDX>(tilingData_->lenDesH));
    GetUintDivMagicAndShift(mN_, shiftN_, static_cast<T_IDX>(tilingData_->lenN));

    T_IDX blkProcessNum = static_cast<T_IDX>(splitBlockFactor_);
    T_IDX blkStartOffset = static_cast<T_IDX>(blockIdx_ * splitBlockFactor_);
    if (blockIdx_ < splitBlockTailFactor_) {
        blkProcessNum += 1;
        blkStartOffset += blockIdx_;
    } else {
        blkStartOffset += splitBlockTailFactor_;
    }

    if constexpr (sizeof(T_IDX) == sizeof(uint64_t)) {
        asc_vf_call<calleeInt64nhwc<T1, T2, halfPixel, mode, T_IDX>>(
            dim3{THREAD_NUM_MIDDLE, 1, 1}, tilingData_->scaleW, tilingData_->scaleH, tilingData_->lenN,
            tilingData_->lenC, tilingData_->lenSrcH, tilingData_->lenSrcW, tilingData_->lenDesH, tilingData_->lenDesW,
            splitBlockFactor_, splitBlockTailFactor_, shiftN_, mN_, shiftC_, mC_, shiftH_, mH_, shiftW_, mW_,
            (__gm__ T1*)(inputGm_.GetPhyAddr()), (__gm__ T2*)(outputGm_.GetPhyAddr()), blkStartOffset, blkProcessNum);
    } else {
        asc_vf_call<calleeInt32nhwc<T1, T2, halfPixel, mode, T_IDX>>(
            dim3{THREAD_NUM, 1, 1}, tilingData_->scaleW, tilingData_->scaleH, tilingData_->lenN,
            tilingData_->lenC, tilingData_->lenSrcH, tilingData_->lenSrcW, tilingData_->lenDesH, tilingData_->lenDesW,
            splitBlockFactor_, splitBlockTailFactor_, shiftN_, mN_, shiftC_, mC_, shiftH_, mH_, shiftW_, mW_,
            (__gm__ T1*)(inputGm_.GetPhyAddr()), (__gm__ T2*)(outputGm_.GetPhyAddr()), blkStartOffset, blkProcessNum);
    }
}
} // namespace ResizeBilinearV2

#endif // CANN_RESIZE_BILINEAR_V2_SIMT_NHWC_H