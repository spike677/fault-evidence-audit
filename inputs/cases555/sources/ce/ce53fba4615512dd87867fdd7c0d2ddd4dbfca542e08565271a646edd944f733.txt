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
* \file grid_sampler2_d_grad_simt_det.h
* \brief
*/
#ifndef GRID_SAMPLER2D_GRAD_SIMT_DET_H_
#define GRID_SAMPLER2D_GRAD_SIMT_DET_H_

#include "simt_api/asc_simt.h"
#include "simt_api/asc_fp16.h"
#include "simt_api/asc_bf16.h"
#include "simt_api/device_atomic_functions.h"
#include "kernel_operator.h"
#ifdef __CCE_KT_TEST__
#include "../../../grid_sampler3_d_grad/op_kernel/arch35/grid_sampler3_d_grad_simt_base.h"
#else
#include "../../grid_sampler3_d_grad/arch35/grid_sampler3_d_grad_simt_base.h"
#endif

using namespace AscendC;
using namespace GridSampler3DGradSimtBase;

namespace GridSampler2DSimtA5Det {
constexpr int32_t WORKSPACE_INDEX = 5;
constexpr int32_t TMP_OUT_INDEX = 0;
constexpr int32_t GM_PARAMS_SIZE = 6;
constexpr uint32_t VF_MAX_THREAD_NUM = 256;

template <typename T>
class GridSampler2DGradSimtDet {
public:
    __aicore__ inline GridSampler2DGradSimtDet(){};
    __aicore__ inline void Init(
        const GridSampler2DGradTilingData* tilingData, GM_ADDR inputTensors[GM_PARAMS_SIZE + 1]);
    __aicore__ inline void Process();

private:
    GlobalTensor<T> inputGm[GM_PARAMS_SIZE];
    GlobalTensor<uint32_t> tmpOutGm[1];
    GlobalTensor<T> tmpOutValueGm[1];
    
    uint32_t blockId_ = GetBlockIdx();
    const GridSampler2DGradTilingData* tiling_;
};

template <typename T>
__aicore__ inline void GridSampler2DGradSimtDet<T>::Init(
    const GridSampler2DGradTilingData* tilingData, GM_ADDR inputTensors[GM_PARAMS_SIZE + 1])
{
    tiling_ = tilingData;
    // init inputTensor
    inputGm[GRAD_INPUT_INDEX_SIMT].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[GRAD_INPUT_INDEX_SIMT]));
    inputGm[X_INPUT_INDEX_SIMT].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[X_INPUT_INDEX_SIMT]));
    inputGm[GRID_INPUT_INDEX_SIMT].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[GRID_INPUT_INDEX_SIMT]));
    inputGm[DX_INPUT_INDEX_SIMT].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[DX_INPUT_INDEX_SIMT]));
    inputGm[DGRID_INPUT_INDEX_SIMT].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[DGRID_INPUT_INDEX_SIMT]));
    tmpOutGm[TMP_OUT_INDEX].SetGlobalBuffer(reinterpret_cast<__gm__ uint32_t*>(inputTensors[WORKSPACE_INDEX]), static_cast<uint64_t>(VF_MAX_THREAD_NUM * 16 * tiling_->blockNum));
    tmpOutValueGm[TMP_OUT_INDEX].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[WORKSPACE_INDEX] + static_cast<uint64_t>(VF_MAX_THREAD_NUM * sizeof(uint32_t) * 16 * tiling_->blockNum)), static_cast<uint64_t>(VF_MAX_THREAD_NUM * 4 * tiling_->blockNum));
}

template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void DeterministicCompute(
    __gm__ uint32_t* dxOutGmAddr, __gm__ T* dxOutValueGmAddr, __gm__ T* dxGmAddr, uint32_t dxGmIndex, float dxOutValue, uint32_t gridSize, uint32_t blockNum, uint32_t batchNum, uint32_t blockId, uint32_t pointIndex, uint32_t channelIndex)
{
    uint32_t threadNum = blockDim.x;
    uint32_t threadIdx_ = threadIdx.x;
    uint32_t tmpOutOffset = pointIndex * VF_MAX_THREAD_NUM + blockId * VF_MAX_THREAD_NUM * 16;
    if (threadIdx_ >= 0 && threadIdx_ < VF_MAX_THREAD_NUM) {
        if (dxGmIndex != -100) {
            dxOutGmAddr[threadIdx_ + tmpOutOffset] = dxGmIndex;
            dxOutValueGmAddr[threadIdx_ + tmpOutOffset] = dxOutValue;
        } else {
            dxOutGmAddr[threadIdx_ + tmpOutOffset] = 0;
            dxOutValueGmAddr[threadIdx_ + tmpOutOffset] = 0;
        }
    }
    asc_syncthreads();
    if (threadIdx_ == 0) {
        for (uint32_t i = 0; i < VF_MAX_THREAD_NUM; ++i){
            uint32_t dxOutIndex = dxOutGmAddr[i + tmpOutOffset];
            float dxOutRes = dxOutValueGmAddr[i + tmpOutOffset];
            asc_atomic_add(dxGmAddr + dxOutIndex, static_cast<T>(dxOutRes));
            dxOutGmAddr[i + tmpOutOffset] = 0;
            dxOutValueGmAddr[i + tmpOutOffset] = 0;
        }
    }
    asc_syncthreads();
}

template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void ComputePoints(
        __gm__ T* gradOutGmAddr, __gm__ T* xGmAddr, __gm__ T* dxGmAddr ,__gm__ uint32_t* dxOutGmAddr, __gm__ T* dxOutValueGmAddr, float iy, float ix, uint32_t gridH, uint32_t gridW, uint32_t batchNum, uint32_t channelIndex, uint32_t heightCol,
        uint32_t widthCol, uint32_t newInputIndex, uint32_t offsetBaseAddr, uint32_t xH, uint32_t xW, uint32_t channel, float tnw, float tne, float tsw, float tse, int32_t iy_tnw, int32_t ix_tnw,
        float* gix, float* giy, uint32_t pNumPerCore, uint32_t blockNum, uint32_t blockId)
{
    uint32_t gridSize = gridH * gridW; 
    float tnwGradOutValue = static_cast<float>(0.0);
    uint32_t tnwDxIndex = static_cast<uint32_t>(-100);
    GetGradOutValueAndDxIndex(gradOutGmAddr, iy_tnw, ix_tnw, gridH, gridW, batchNum, heightCol, widthCol, channelIndex, newInputIndex, xH, xW, channel, &tnwGradOutValue, &tnwDxIndex);
    DeterministicCompute((__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, (__gm__ T*)dxGmAddr, tnwDxIndex, tnw * tnwGradOutValue, gridSize, blockNum, batchNum, blockId, static_cast<uint32_t>(0), channelIndex);
    if (tnwDxIndex != -100) {
        float tnw_val = xGmAddr[tnwDxIndex];
        *gix -= tnw_val * (iy_tnw + 1 - iy) * tnwGradOutValue;
        *giy -= tnw_val * (ix_tnw + 1 - ix) * tnwGradOutValue;
    }

    // tne
    float tneGradOutValue = static_cast<float>(0.0);
    uint32_t tneDxIndex = static_cast<uint32_t>(-100);
    GetGradOutValueAndDxIndex(gradOutGmAddr, iy_tnw, ix_tnw + 1, gridH, gridW, batchNum, heightCol, widthCol, channelIndex, newInputIndex, xH, xW, channel, &tneGradOutValue, &tneDxIndex);
    DeterministicCompute((__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, (__gm__ T*)dxGmAddr, tneDxIndex, tne * tneGradOutValue, gridSize, blockNum, batchNum, blockId, static_cast<uint32_t>(1), channelIndex);
    if (tneDxIndex != -100) {
        float tne_val = xGmAddr[tneDxIndex];
        *gix += tne_val * (iy_tnw + 1 - iy) * tneGradOutValue;
        *giy -= tne_val * (ix - ix_tnw) * tneGradOutValue;
    }

    // tsw
    float tswGradOutValue = static_cast<float>(0.0);
    uint32_t tswDxIndex = static_cast<uint32_t>(-100);
    GetGradOutValueAndDxIndex(gradOutGmAddr, iy_tnw + 1, ix_tnw, gridH, gridW, batchNum, heightCol, widthCol, channelIndex, newInputIndex, xH, xW, channel, &tswGradOutValue, &tswDxIndex);
    DeterministicCompute((__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, (__gm__ T*)dxGmAddr, tswDxIndex, tsw * tswGradOutValue, gridSize, blockNum, batchNum, blockId, static_cast<uint32_t>(2), channelIndex);
    if (tswDxIndex != -100) {
        float tsw_val = xGmAddr[tswDxIndex];
        *gix -= tsw_val * (iy - iy_tnw) * tswGradOutValue;
        *giy += tsw_val * (ix_tnw + 1 - ix) * tswGradOutValue;
    }

    // tse
    float tseGradOutValue = static_cast<float>(0.0);
    uint32_t tseDxIndex = static_cast<uint32_t>(-100);
    GetGradOutValueAndDxIndex(gradOutGmAddr, iy_tnw + 1, ix_tnw + 1, gridH, gridW, batchNum, heightCol, widthCol, channelIndex, newInputIndex, xH, xW, channel, &tseGradOutValue, &tseDxIndex);
    DeterministicCompute((__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, (__gm__ T*)dxGmAddr, tseDxIndex, tse * tseGradOutValue, gridSize, blockNum, batchNum, blockId, static_cast<uint32_t>(3), channelIndex);
    if (tseDxIndex != -100) {
        float tse_val = xGmAddr[tseDxIndex];
        *gix += tse_val * (iy - iy_tnw) * tseGradOutValue;
        *giy += tse_val * (ix - ix_tnw) * tseGradOutValue;
    }
}


template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void ComputeBilinear(
    __gm__ T* gradOutGmAddr, __gm__ T* xGmAddr, __gm__ T* dxGmAddr, __gm__ T* dgridGmAddr,  __gm__ uint32_t* dxOutGmAddr, __gm__ T* dxOutValueGmAddr,
float iy, float ix, uint32_t gridH, uint32_t gridW, uint32_t batchNum, uint32_t heightCol, uint32_t widthCol, uint32_t newInputIndex, uint32_t offsetBaseAddr, 
uint32_t xH, uint32_t xW, uint32_t channel, float* ixGradMultValue, float* iyGradMultValue, uint32_t pNumPerCore, uint32_t blockNum, uint32_t blockId)
{
    int32_t ix_tnw = static_cast<int32_t>(floorf(ix));
    int32_t iy_tnw = static_cast<int32_t>(floorf(iy));

    // get surfaces to each neighbor:
    float tnw = (ix_tnw + 1 - ix) * (iy_tnw + 1 - iy);
    float tne = (ix - ix_tnw) * (iy_tnw + 1 - iy);
    float tsw = (ix_tnw + 1 - ix) * (iy - iy_tnw);
    float tse = (ix - ix_tnw) * (iy - iy_tnw);
    float gix = static_cast<float>(0.0);
    float giy = static_cast<float>(0.0);

    // calculate and set grad_input.
    for (uint32_t channelIndex = 0; channelIndex < channel; channelIndex++) {
        ComputePoints((__gm__ T*)gradOutGmAddr, (__gm__ T*)xGmAddr, (__gm__ T*)dxGmAddr, (__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, iy, ix, gridH, gridW,
                 batchNum, channelIndex, heightCol, widthCol, newInputIndex, offsetBaseAddr, xH, xW, channel,
                 tnw, tne, tsw, tse, iy_tnw, ix_tnw, &gix, &giy, pNumPerCore, blockNum, blockId);

        dgridGmAddr[offsetBaseAddr] = static_cast<T>((*ixGradMultValue) * gix);
        dgridGmAddr[offsetBaseAddr + 1] = static_cast<T>((*iyGradMultValue) * giy);
    }
}

template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void ComputeNearest(
    __gm__ T* gradOutGmAddr, __gm__ T* xGmAddr, __gm__ T* dxGmAddr, __gm__ T* dgridGmAddr,  __gm__ uint32_t* dxOutGmAddr, __gm__ T* dxOutValueGmAddr, float iy, float ix,
    uint32_t gridH, uint32_t gridW, uint32_t batchNum, uint32_t heightCol,
    uint32_t widthCol, uint32_t newInputIndex, uint32_t offsetBaseAddr, uint32_t xH, uint32_t xW,
    uint32_t channel, uint32_t pNumPerCore, uint32_t blockNum, uint32_t blockId)
{
    uint32_t gridSize = gridH * gridW;
    int32_t ix_nearest = rintf(ix);
    int32_t iy_nearest = rintf(iy);

    for (uint32_t channelIndex = 0; channelIndex < channel; channelIndex++) {
        float gradOutValue = static_cast<float>(0.0);
        uint32_t dxIndex = static_cast<uint32_t>(-100);
        GetGradOutValueAndDxIndex(gradOutGmAddr, iy_nearest, ix_nearest, gridH, gridW, batchNum, heightCol, widthCol, channelIndex, newInputIndex, xH, xW, channel, &gradOutValue, &dxIndex);
        DeterministicCompute((__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, (__gm__ T*)dxGmAddr, dxIndex, gradOutValue, gridSize, blockNum, batchNum, blockId, static_cast<uint32_t>(0), channelIndex);

        dgridGmAddr[offsetBaseAddr] = static_cast<T>(0);
        dgridGmAddr[offsetBaseAddr + 1] = static_cast<T>(0);
    }
}

template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void ComputeBicubicGradInput(
    __gm__ uint32_t* dxOutGmAddr, __gm__ T* dxOutValueGmAddr, __gm__ T* dxGmAddr,
    float neighbor_x, float neighbor_y, uint32_t xW, uint32_t xH,
    uint32_t padding, uint32_t alignCorners, uint32_t newInputIndex, uint32_t channelIndex,
    float delta, uint32_t gridSize, uint32_t blockNum, uint32_t batchNum, uint32_t blockId,
    int32_t i, int32_t j)
{
    bool inBounds = true;

    if (padding == 0) {
        if (neighbor_x < 0 || neighbor_x >= static_cast<float>(xW) ||
            neighbor_y < 0 || neighbor_y >= static_cast<float>(xH)) {
            inBounds = false;
        }
    } else if (padding == 1) {
        neighbor_x = neighbor_x < 0 ? 0 : (neighbor_x >= static_cast<float>(xW) ? static_cast<float>(xW) - 1 : neighbor_x);
        neighbor_y = neighbor_y < 0 ? 0 : (neighbor_y >= static_cast<float>(xH) ? static_cast<float>(xH) - 1 : neighbor_y);
    } else {
        float gradReflX = 0, gradClipX = 0, gradReflY = 0, gradClipY = 0;
        if (alignCorners) {
            neighbor_x = ReflectCoordinatesSetGrad(neighbor_x, 0, 2 * (xW - 1), &gradReflX);
            neighbor_y = ReflectCoordinatesSetGrad(neighbor_y, 0, 2 * (xH - 1), &gradReflY);
        } else {
            neighbor_x = ReflectCoordinatesSetGrad(neighbor_x, -1, 2 * xW - 1, &gradReflX);
            neighbor_y = ReflectCoordinatesSetGrad(neighbor_y, -1, 2 * xH - 1, &gradReflY);
        }
        neighbor_x = ClipCoorDinatesSetGrad(neighbor_x, xW, &gradClipX);
        neighbor_y = ClipCoorDinatesSetGrad(neighbor_y, xH, &gradClipY);
    }

    int32_t clipped_x = static_cast<int32_t>(SafeDowngradeToIntRange(neighbor_x));
    int32_t clipped_y = static_cast<int32_t>(SafeDowngradeToIntRange(neighbor_y));

    if (inBounds && clipped_x >= 0 && clipped_x < static_cast<int32_t>(xW) &&
        clipped_y >= 0 && clipped_y < static_cast<int32_t>(xH)) {
        uint32_t dxIndex = newInputIndex + channelIndex * xH * xW + clipped_y * xW + clipped_x;
        DeterministicCompute((__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr,
            (__gm__ T*)dxGmAddr, dxIndex, delta, gridSize, blockNum, batchNum, blockId,
            static_cast<uint32_t>(i * 4 + j), channelIndex);
    }
}

template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void ComputeBicubic(
    __gm__ T* gradOutGmAddr, __gm__ T* xGmAddr, __gm__ T* dxGmAddr, __gm__ T* dgridGmAddr,
    __gm__ uint32_t* dxOutGmAddr, __gm__ T* dxOutValueGmAddr,
    float iy, float ix, uint32_t gridH, uint32_t gridW, uint32_t batchNum, uint32_t heightCol,
    uint32_t widthCol, uint32_t newInputIndex, uint32_t offsetBaseAddr, uint32_t xH, uint32_t xW,
    uint32_t channel, uint32_t padding, uint32_t alignCorners, float* ixGradMultValue, float* iyGradMultValue,
    uint32_t pNumPerCore, uint32_t blockNum, uint32_t blockId)
{
    float iy_nw_f = floorf(iy);
    float ix_nw_f = floorf(ix);

    float ty = iy - iy_nw_f;
    float tx = ix - ix_nw_f;

    // Compute forward cubic coefficients (for grad_input)
    float y_coeffs[4];
    float x_coeffs[4];
    GetCubicUpsampleCoefficients(y_coeffs, ty, sizeof(y_coeffs) / sizeof(float));
    GetCubicUpsampleCoefficients(x_coeffs, tx, sizeof(x_coeffs) / sizeof(float));

    // Compute gradient cubic coefficients (for grad_grid)
    float y_coeffs_grad[4];
    float x_coeffs_grad[4];
    GetCubicCoefficientsGrad(y_coeffs_grad, ty, sizeof(y_coeffs_grad) / sizeof(float));
    GetCubicCoefficientsGrad(x_coeffs_grad, tx, sizeof(x_coeffs_grad) / sizeof(float));

    float giy = static_cast<float>(0);
    float gix = static_cast<float>(0);

    uint32_t gridSize = gridH * gridW;

    for (uint32_t channelIndex = 0; channelIndex < channel; channelIndex++) {
        float gradOutValue = static_cast<float>(0.0);
        uint32_t gradOutValueIndex = batchNum * channel * gridH * gridW + channelIndex * gridH * gridW +
                                     heightCol * gridW + widthCol;
        gradOutValue = static_cast<float>(gradOutGmAddr[gradOutValueIndex]);

        // Pointer to current (n, c) slice of x
        __gm__ T* xPtrNC = xGmAddr + newInputIndex + channelIndex * xH * xW;

        for (int32_t i = 0; i < 4; i++) {
            for (int32_t j = 0; j < 4; j++) {
                float neighbor_x = ix_nw_f - 1 + i;
                float neighbor_y = iy_nw_f - 1 + j;

                float weight = x_coeffs[i] * y_coeffs[j];
                float delta = gradOutValue * weight;

                ComputeBicubicGradInput<T>((__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr,
                    (__gm__ T*)dxGmAddr, neighbor_x, neighbor_y, xW, xH, padding, alignCorners,
                    newInputIndex, channelIndex, delta, gridSize, blockNum, batchNum, blockId, i, j);

                // Set grad_grid: get_value_bounded (data pointer already at NC offset)
                float val = GetValueBounded<T>(xPtrNC,
                    neighbor_x, neighbor_y, xW, xH, 1, xW, padding, alignCorners);

                giy += val * y_coeffs_grad[j] * x_coeffs[i] * gradOutValue;
                gix += val * x_coeffs_grad[i] * y_coeffs[j] * gradOutValue;
            }
        }
    }

    dgridGmAddr[offsetBaseAddr + 1] = static_cast<T>((*iyGradMultValue) * giy);
    dgridGmAddr[offsetBaseAddr] = static_cast<T>((*ixGradMultValue) * gix);
}

// LAUNCH_BOUND
template <typename T>
__simt_vf__ LAUNCH_BOUND(VF_MAX_THREAD_NUM)
__aicore__ void ComputeGridSampler2DGradDet(
    __gm__ T* gradOutGmAddr, __gm__ T* xGmAddr, __gm__ T* gridGmAddr, __gm__ T* dxGmAddr, __gm__ T* dgridGmAddr,__gm__ uint32_t* dxOutGmAddr, __gm__ T* dxOutValueGmAddr,
    uint32_t blockNum, uint32_t batch, uint32_t channel, uint32_t xH, uint32_t xW, uint32_t gridH,
    uint32_t gridW, uint32_t interpolation, uint32_t padding, uint32_t alignCorners, uint32_t pNumPerCore, uint32_t gridSize,
    uint32_t shiftH_, uint32_t mH_, uint32_t shiftW_, uint32_t mW_, uint32_t blockId_)
{
    for (uint32_t index = blockId_ * gridSize * pNumPerCore + threadIdx.x; index < (blockId_ + 1) * gridSize * pNumPerCore && (index < gridSize * batch); index += VF_MAX_THREAD_NUM) {
        uint32_t batchNum, heightCol, widthCol;
        batchNum = Simt::UintDiv(index, mH_, shiftH_);
        uint32_t remain = index - batchNum * gridSize;

        heightCol = Simt::UintDiv(remain, mW_, shiftW_);
        widthCol = remain - heightCol * gridW;

        uint32_t newInputIndex = batchNum * channel * xH * xW;
        uint32_t offsetBaseAddr = (batchNum * gridH * gridW + heightCol * gridW + widthCol) * 2;

        // get the corresponding input x, y co-ordinates from grid
        float iy = static_cast<float>(gridGmAddr[offsetBaseAddr + 1]); // iy
        float ix = static_cast<float>(gridGmAddr[offsetBaseAddr]);     // ix

        // multipliers for gradients on ix, iy
        float ixGradMultValue = 0;
        float iyGradMultValue = 0;
        if (interpolation == BICUBIC) {
            // For bicubic, only unnormalize (no clip/reflect on the coordinate itself)
            iy = UnnormalizeSetGrad(iy, xH, alignCorners, &iyGradMultValue);
            ix = UnnormalizeSetGrad(ix, xW, alignCorners, &ixGradMultValue);
        } else {
            iy = ComputeSourceIndexSetGrad(iy, xH, padding, alignCorners, &iyGradMultValue);
            ix = ComputeSourceIndexSetGrad(ix, xW, padding, alignCorners, &ixGradMultValue);
        }

        if (interpolation == BILINEAR) {
            ComputeBilinear(
                (__gm__ T*)gradOutGmAddr, (__gm__ T*)xGmAddr, (__gm__ T*)dxGmAddr, (__gm__ T*)dgridGmAddr, (__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, iy, ix,
                gridH, gridW, batchNum, heightCol, widthCol, newInputIndex, offsetBaseAddr, xH, xW,
                channel, &ixGradMultValue, &iyGradMultValue, pNumPerCore, blockNum, blockId_);
        } else if (interpolation == NEAREST) {
            ComputeNearest(
                (__gm__ T*)gradOutGmAddr, (__gm__ T*)xGmAddr, (__gm__ T*)dxGmAddr, (__gm__ T*)dgridGmAddr, (__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, iy, ix,
                gridH, gridW, batchNum, heightCol, widthCol, newInputIndex, offsetBaseAddr, xH, xW,
                channel, pNumPerCore, blockNum, blockId_);
        } else if (interpolation == BICUBIC) {
            ComputeBicubic(
                (__gm__ T*)gradOutGmAddr, (__gm__ T*)xGmAddr, (__gm__ T*)dxGmAddr, (__gm__ T*)dgridGmAddr,
                (__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, iy, ix,
                gridH, gridW, batchNum, heightCol, widthCol, newInputIndex, offsetBaseAddr, xH, xW,
                channel, padding, alignCorners, &ixGradMultValue, &iyGradMultValue, pNumPerCore, blockNum, blockId_);
        }
    }
}

template <typename T>
__aicore__ inline void GridSampler2DGradSimtDet<T>::Process()
{
    uint32_t gridSize =  tiling_->gridH * tiling_->gridW;
    uint32_t shiftH_, mH_, shiftW_, mW_;
    GetUintDivMagicAndShift(mH_, shiftH_, static_cast<uint32_t>(tiling_->gridH * tiling_->gridW));
    GetUintDivMagicAndShift(mW_, shiftW_, static_cast<uint32_t>(tiling_->gridW));
    asc_vf_call<ComputeGridSampler2DGradDet<T>>(
        dim3{VF_MAX_THREAD_NUM, 1, 1}, (__gm__ T*)(inputGm[GRAD_INPUT_INDEX_SIMT].GetPhyAddr()),
        (__gm__ T*)(inputGm[X_INPUT_INDEX_SIMT].GetPhyAddr()), (__gm__ T*)(inputGm[GRID_INPUT_INDEX_SIMT].GetPhyAddr()),
        (__gm__ T*)(inputGm[DX_INPUT_INDEX_SIMT].GetPhyAddr()), (__gm__ T*)(inputGm[DGRID_INPUT_INDEX_SIMT].GetPhyAddr()),
        (__gm__ uint32_t*)(tmpOutGm[TMP_OUT_INDEX].GetPhyAddr()), (__gm__ T*)(tmpOutValueGm[TMP_OUT_INDEX].GetPhyAddr()), tiling_->blockNum, tiling_->batch, tiling_->channel, tiling_->height, tiling_->width, 
        tiling_->gridH, tiling_->gridW, tiling_->interpolation, tiling_->padding, tiling_->alignCorners, tiling_->pNumPerCore, gridSize,
        shiftH_, mH_, shiftW_, mW_, blockId_);
}
} // namespace GridSampler2DSimtA5Det
#endif // GRID_SAMPLER2D_GRAD_SIMT_DET_H_