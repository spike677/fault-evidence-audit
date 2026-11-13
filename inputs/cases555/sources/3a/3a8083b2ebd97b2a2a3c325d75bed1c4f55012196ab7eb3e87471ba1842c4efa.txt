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
 * \file resize_bilinear_v2_simt_nchw.h
 * \brief resize_bilinear_v2_simt_nchw
 */

#ifndef CANN_RESIZE_BILINEAR_V2_SIMT_NCHW_H
#define CANN_RESIZE_BILINEAR_V2_SIMT_NCHW_H

#include "kernel_operator.h"
#include "kernel_tiling/kernel_tiling.h"
#include "resize_bilinear_v2_base.h"
#include "simt_api/asc_simt.h"

namespace ResizeBilinearV2 {
using namespace AscendC;

template <typename T1, typename T2, bool halfPixel, int mode, typename T_IDX>
class ResizeBilinearV2SimtNCHW {
public:
    __aicore__ inline ResizeBilinearV2SimtNCHW(){};

    __aicore__ inline void Init(GM_ADDR grads, GM_ADDR size, GM_ADDR y, const ResizeBilinearV2TilingData* tilingData);
    __aicore__ inline void Process();

private:
    const ResizeBilinearV2TilingData* tilingData_;
    int64_t blockIdx_;
    GlobalTensor<T1> inputGm_;
    GlobalTensor<T2> outputGm_;
};

template <typename T1, typename T2, bool halfPixel, int mode, typename T_IDX>
__aicore__ inline void ResizeBilinearV2SimtNCHW<T1, T2, halfPixel, mode, T_IDX>::Init(
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
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void QuickDivForSimtComputenchw(
    T_IDX& N, T_IDX& C, T_IDX& H, T_IDX& W, T_IDX tmp, T_IDX mW, T_IDX shiftW, T_IDX lenDesW, T_IDX mH, T_IDX shiftH,
    T_IDX lenDesH, T_IDX mC, T_IDX shiftC, T_IDX lenC, T_IDX mN, T_IDX shiftN, T_IDX lenN)
{
    // 快速整除计算 tmp/lenDesW
    T_IDX tmpRes = Simt::UintDiv(tmp, mW, shiftW);
    W = tmp - tmpRes * lenDesW;
    tmp = tmpRes;

    tmpRes = Simt::UintDiv(tmp, mH, shiftH);
    H = tmp - tmpRes * lenDesH;
    tmp = tmpRes;

    tmpRes = Simt::UintDiv(tmp, mC, shiftC);
    C = tmp - tmpRes * lenC;
    tmp = tmpRes;

    tmpRes = Simt::UintDiv(tmp, mN, shiftN);
    N = tmp - tmpRes * lenN;
}

template <typename T1, typename T2, bool halfPixel, int mode, typename T_IDX>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void SimtCompute(
    float scaleH, float scaleW, T_IDX lenN, T_IDX lenC, T_IDX lenDesH, T_IDX lenDesW, T_IDX lenSrcH, T_IDX lenSrcW,
    T_IDX shiftN, T_IDX mN, T_IDX shiftC, T_IDX mC, T_IDX shiftH, T_IDX mH, T_IDX shiftW, T_IDX mW, __gm__ T1* input,
    __gm__ T2* output, T_IDX blkStartOffset, T_IDX blkProcessNum)
{
    for (T_IDX idx = static_cast<T_IDX>(threadIdx.x); idx < blkProcessNum;
         idx += static_cast<T_IDX>(blockDim.x)) {
        T_IDX yGmIdx = blkStartOffset + idx;
        T_IDX tmp = yGmIdx;

        T_IDX N = 0, C = 0, H = 0, W = 0;

        QuickDivForSimtComputenchw(
            N, C, H, W, tmp, mW, shiftW, lenDesW, mH, shiftH, lenDesH, mC, shiftC, lenC, mN, shiftN, lenN);
        float origHeight_ = 0.0f, origWidth_ = 0.0f, deltaX = 0.0f, deltaY = 0.0f;

        T_IDX leftX = 0, rightX = 0, topY = 0, bottomY = 0, lenSrcWH_ = lenSrcW * lenSrcH;
        // 场景1：输入输出大小相等，直接赋值
        // 场景2：输入是1个点，输出是多个点
        // 场景3：输入是多个点，输出是1个点
        if constexpr (mode == SIMT_SCENE_ALL_COPY) {
            output[yGmIdx] = input[N * lenC * lenSrcWH_ + C * lenSrcWH_ + H * lenSrcW + W];
            continue;
        } else if constexpr (mode == SIMT_SCENE_INPUT_ONE) {
            output[yGmIdx] = input[N * lenC + C];
            continue;
        } else if constexpr (mode == SIMT_SCENE_OUTPUT_ONE) {
            output[yGmIdx] = input[N * lenC * lenSrcWH_ + C * lenSrcWH_];
            continue;
        }

        if constexpr (halfPixel) {
            origHeight_ = static_cast<float>((H + HALF_PIXEL) * scaleH) - HALF_PIXEL;
            origWidth_ = static_cast<float>((W + HALF_PIXEL) * scaleW) - HALF_PIXEL;
        } else {
            origHeight_ = static_cast<float>(H * scaleH);
            origWidth_ = static_cast<float>(W * scaleW);
        }
        if (origHeight_ < 0.0f) {
            origHeight_ = 0.0;
        }
        if (origWidth_ < 0.0f) {
            origWidth_ = 0.0;
        }

        // 计算原图坐标点附近四点的横坐标以及权重值
        leftX = (origWidth_ > 0.0f) ? floorf(origWidth_) : 0.0f;
        leftX = (leftX < lenSrcW - 1) ? leftX : lenSrcW - 1;
        rightX = (origWidth_ > 0.0f) ? ceilf(origWidth_) : 0.0f;
        rightX = (rightX < lenSrcW - 1) ? rightX : lenSrcW - 1;
        deltaX = origWidth_ - floorf(origWidth_);

        // 计算原图坐标点附近四点的纵坐标以及权重值
        topY = (origHeight_ > 0.0f) ? floorf(origHeight_) : 0.0f;
        topY = (topY < lenSrcH - 1) ? topY : lenSrcH - 1;
        bottomY = (origHeight_ > 0.0f) ? ceilf(origHeight_) : 0.0f;
        bottomY = (bottomY < lenSrcH - 1) ? bottomY : lenSrcH - 1;
        deltaY = origHeight_ - floorf(origHeight_);

        // 计算原图坐标点附近四个点的像素值
        T_IDX origBaseIdx = N * (lenC * lenSrcWH_) + C * lenSrcWH_;
        float pixelLeftTop = input[origBaseIdx + topY * lenSrcW + leftX];
        float pixelRightTop = input[origBaseIdx + topY * lenSrcW + rightX];
        float pixelLeftBottom = input[origBaseIdx + bottomY * lenSrcW + leftX];
        float pixelRightBottom = input[origBaseIdx + bottomY * lenSrcW + rightX];
        // 根据周围四个点像素值进行双线性差值，计算出输出像素值
        output[yGmIdx] = (1.0f - deltaY) * ((1.0f - deltaX) * pixelLeftTop + deltaX * pixelRightTop) +
                         deltaY * ((1.0f - deltaX) * pixelLeftBottom + deltaX * pixelRightBottom);
    }
}

// LAUNCH_BOUND
template <typename T1, typename T2, bool halfPixel, int mode, typename T_IDX>
__simt_vf__ LAUNCH_BOUND(THREAD_NUM) __aicore__ void calleeInt32nchw(
    float scaleH, float scaleW, T_IDX lenN, T_IDX lenC, T_IDX lenDesH, T_IDX lenDesW, T_IDX lenSrcH, T_IDX lenSrcW,
    T_IDX shiftN, T_IDX mN, T_IDX shiftC, T_IDX mC, T_IDX shiftH, T_IDX mH, T_IDX shiftW, T_IDX mW, __gm__ T1* input,
    __gm__ T2* output, T_IDX blkStartOffset, T_IDX blkProcessNum)
{
    SimtCompute<T1, T2, halfPixel, mode, T_IDX>(
        scaleH, scaleW, lenN, lenC, lenDesH, lenDesW, lenSrcH, lenSrcW, shiftN, mN, shiftC, mC, shiftH, mH, shiftW, mW,
        input, output, blkStartOffset, blkProcessNum);
}

template <typename T1, typename T2, bool halfPixel, int mode, typename T_IDX>
__simt_vf__ LAUNCH_BOUND(THREAD_NUM_MIDDLE) __aicore__ void calleeInt64nchw(
    float scaleH, float scaleW, T_IDX lenN, T_IDX lenC, T_IDX lenDesH, T_IDX lenDesW, T_IDX lenSrcH, T_IDX lenSrcW,
    T_IDX shiftN, T_IDX mN, T_IDX shiftC, T_IDX mC, T_IDX shiftH, T_IDX mH, T_IDX shiftW, T_IDX mW, __gm__ T1* input,
    __gm__ T2* output, T_IDX blkStartOffset, T_IDX blkProcessNum)
{
    SimtCompute<T1, T2, halfPixel, mode, T_IDX>(
        scaleH, scaleW, lenN, lenC, lenDesH, lenDesW, lenSrcH, lenSrcW, shiftN, mN, shiftC, mC, shiftH, mH, shiftW, mW,
        input, output, blkStartOffset, blkProcessNum);
}
// process
template <typename T1, typename T2, bool halfPixel, int mode, typename T_IDX>
__aicore__ inline void ResizeBilinearV2SimtNCHW<T1, T2, halfPixel, mode, T_IDX>::Process()
{
    T_IDX mW = 1;
    T_IDX mH = 1;
    T_IDX mC = 1;
    T_IDX mN = 1;
    T_IDX shiftW = 0;
    T_IDX shiftH = 0;
    T_IDX shiftC = 0;
    T_IDX shiftN = 0;

    // GetQuickDivParams
    GetUintDivMagicAndShift(mW, shiftW, static_cast<T_IDX>(tilingData_->lenDesW));
    GetUintDivMagicAndShift(mH, shiftH, static_cast<T_IDX>(tilingData_->lenDesH));
    GetUintDivMagicAndShift(mC, shiftC, static_cast<T_IDX>(tilingData_->lenC));
    GetUintDivMagicAndShift(mN, shiftN, static_cast<T_IDX>(tilingData_->lenN));

    T_IDX blkProcessNum = tilingData_->splitBlockFactor;
    T_IDX blkStartOffset = blockIdx_ * tilingData_->splitBlockFactor;
    if (blockIdx_ < tilingData_->splitBlockTailFactor) {
        blkProcessNum += 1;
        blkStartOffset += blockIdx_;
    } else {
        blkStartOffset += tilingData_->splitBlockTailFactor;
    }

    if constexpr (sizeof(T_IDX) == sizeof(uint64_t)) {
        asc_vf_call<calleeInt64nchw<T1, T2, halfPixel, mode, T_IDX>>(
            dim3(THREAD_NUM_MIDDLE), tilingData_->scaleH, tilingData_->scaleW, tilingData_->lenN,
            tilingData_->lenC, tilingData_->lenDesH, tilingData_->lenDesW, tilingData_->lenSrcH, tilingData_->lenSrcW,
            shiftN, mN, shiftC, mC, shiftH, mH, shiftW, mW, (__gm__ T1*)(inputGm_.GetPhyAddr()),
            (__gm__ T2*)(outputGm_.GetPhyAddr()), blkStartOffset, blkProcessNum);
    } else {
        asc_vf_call<calleeInt32nchw<T1, T2, halfPixel, mode, T_IDX>>(
            dim3(THREAD_NUM), tilingData_->scaleH, tilingData_->scaleW, tilingData_->lenN, tilingData_->lenC,
            tilingData_->lenDesH, tilingData_->lenDesW, tilingData_->lenSrcH, tilingData_->lenSrcW, shiftN, mN, shiftC,
            mC, shiftH, mH, shiftW, mW, (__gm__ T1*)(inputGm_.GetPhyAddr()), (__gm__ T2*)(outputGm_.GetPhyAddr()),
            blkStartOffset, blkProcessNum);
    }
}
} // namespace ResizeBilinearV2

#endif // CANN_RESIZE_BILINEAR_V2_SIMT_NCHW_H