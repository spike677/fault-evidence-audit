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
 * \file grid_sampler3_d_grad_simt.h
 * \brief
 */
#ifndef GRID_SAMPLER3D_GRAD_SIMT_DET_H_
#define GRID_SAMPLER3D_GRAD_SIMT_DET_H_

#include "simt_api/asc_simt.h"
#include "kernel_operator.h"
#include "grid_sampler3_d_grad_simt_base.h"

using namespace AscendC;
using namespace GridSampler3DGradSimtBase;

namespace GridSampler3DGradSimtDetNS {

template <typename T>
class GridSampler3DGradSimtDet {
public:
    __aicore__ inline GridSampler3DGradSimtDet(){};
    __aicore__ inline void Init(const GridSampler3DGradTilingData* tilingData, GM_ADDR inputTensors[GM_PARAMS_SIZE]);
    __aicore__ inline void Process();

private:
    GlobalTensor<T> inputGm[GM_PARAMS_SIZE];
    GlobalTensor<uint32_t> tmpOutGm[1];
    GlobalTensor<T> tmpOutValueGm[1];
    uint32_t blockId_ = GetBlockIdx();
    const GridSampler3DGradTilingData* tiling_;
};

template <typename T>
__aicore__ inline void GridSampler3DGradSimtDet<T>::Init(
    const GridSampler3DGradTilingData* tilingData, GM_ADDR inputTensors[GM_PARAMS_SIZE])
{
    tiling_ = tilingData;
    uint64_t tmpOutSize = static_cast<uint64_t>(VF_MAX_THREAD_NUM * 8 * tiling_->blockNum * tiling_->batch);
    // init inputTensor
    inputGm[GRAD_INPUT_INDEX_SIMT].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[GRAD_INPUT_INDEX_SIMT]));
    inputGm[X_INPUT_INDEX_SIMT].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[X_INPUT_INDEX_SIMT]));
    inputGm[GRID_INPUT_INDEX_SIMT].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[GRID_INPUT_INDEX_SIMT]));
    inputGm[DX_INPUT_INDEX_SIMT].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[DX_INPUT_INDEX_SIMT]));
    inputGm[DGRID_INPUT_INDEX_SIMT].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[DGRID_INPUT_INDEX_SIMT]));
    tmpOutGm[TMP_OUT_INDEX].SetGlobalBuffer(
        reinterpret_cast<__gm__ uint32_t*>(inputTensors[WORKSPACE_INDEX]), tmpOutSize);
    tmpOutValueGm[TMP_OUT_INDEX].SetGlobalBuffer(
        reinterpret_cast<__gm__ T*>(inputTensors[WORKSPACE_INDEX] + static_cast<uint64_t>(tmpOutSize * 4)), tmpOutSize);
}

template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void deterministicCompute(
    __gm__ uint32_t* dxOutGmAddr, __gm__ T* dxOutValueGmAddr, __gm__ T* dxGmAddr, uint32_t dxGmIndex, float dxOutValue,
    uint32_t blockNum, uint32_t batchNum, uint32_t blockId, uint32_t pointIndex)
{
    uint32_t threadNum = blockDim.x; // VF_MAX_THREAD_NUM
    uint32_t thread_idx = threadIdx.x;
    uint32_t tmpOutOffset = pointIndex * VF_MAX_THREAD_NUM + blockId * VF_MAX_THREAD_NUM * 8;

    if (thread_idx >= 0 && thread_idx < VF_MAX_THREAD_NUM) {
        if (dxGmIndex != -100) {
            dxOutGmAddr[thread_idx + tmpOutOffset] = dxGmIndex;
            dxOutValueGmAddr[thread_idx + tmpOutOffset] = dxOutValue;
        } else {
            dxOutGmAddr[thread_idx + tmpOutOffset] = static_cast<uint32_t>(0);
            dxOutValueGmAddr[thread_idx + tmpOutOffset] = static_cast<float>(0.0);
        }
    }
    asc_syncthreads();

    if (thread_idx == 0) {
        for (uint32_t i = 0; i < VF_MAX_THREAD_NUM; i++) {
            uint32_t dxOutIndex = dxOutGmAddr[i + tmpOutOffset];
            float dxOutRes = dxOutValueGmAddr[i + tmpOutOffset];
            asc_atomic_add(dxGmAddr + dxOutIndex, static_cast<T>(dxOutRes));
            dxOutGmAddr[i + tmpOutOffset] = static_cast<uint32_t>(0);
            dxOutValueGmAddr[i + tmpOutOffset] = static_cast<float>(0.0);
        }
    }
    asc_syncthreads();
}

template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void ComputeTop1Points(
    __gm__ T* gradOutGmAddr, __gm__ T* xGmAddr, __gm__ T* dxGmAddr, __gm__ uint32_t* dxOutGmAddr,
    __gm__ T* dxOutValueGmAddr, float iz, float iy, float ix, uint32_t gridD, uint32_t gridH, uint32_t gridW,
    uint32_t batchNum, uint32_t channelIndex, uint32_t depthCol, uint32_t heightCol, uint32_t widthCol,
    uint32_t newInputIndex, uint32_t offsetBaseAddr, uint32_t xD, uint32_t xH, uint32_t xW, uint32_t channel, float tnw,
    float tne, int32_t iz_tnw, int32_t iy_tnw, int32_t ix_tnw, int32_t iz_t1, int32_t iy_t1, int32_t ix_t1, float* gix,
    float* giy, float* giz, uint32_t blockNum, uint32_t blockId)
{
    // tnw
    uint32_t tnwDxIndex = static_cast<uint32_t>(-100);
    float tnwGradOutValue = static_cast<float>(0.0);
    GetGradOutPointValueAndDxIndex(
        gradOutGmAddr, iz_tnw, iy_tnw, ix_tnw, gridD, gridH, gridW, batchNum, depthCol, heightCol, widthCol,
        channelIndex, offsetBaseAddr, xD, xH, xW, channel, newInputIndex, &tnwGradOutValue, &tnwDxIndex);
    float tnwDxValue = tnw * tnwGradOutValue;
    deterministicCompute(
        (__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, (__gm__ T*)dxGmAddr, tnwDxIndex, tnwDxValue,
        blockNum, batchNum, blockId, static_cast<uint32_t>(0));
    if (tnwDxIndex != -100) {
        float tnw_val = static_cast<float>(xGmAddr[tnwDxIndex]);
        *gix -= tnw_val * (iy_t1 - iy) * (iz_t1 - iz) * tnwGradOutValue;
        *giy -= tnw_val * (ix_t1 - ix) * (iz_t1 - iz) * tnwGradOutValue;
        *giz -= tnw_val * (ix_t1 - ix) * (iy_t1 - iy) * tnwGradOutValue;
    }

    // tne
    uint32_t tneDxIndex = static_cast<uint32_t>(-100);
    float tneGradOutValue = static_cast<float>(0.0);
    GetGradOutPointValueAndDxIndex(
        gradOutGmAddr, iz_tnw, iy_tnw, ix_t1, gridD, gridH, gridW, batchNum, depthCol, heightCol, widthCol,
        channelIndex, offsetBaseAddr, xD, xH, xW, channel, newInputIndex, &tneGradOutValue, &tneDxIndex);
    float tneDxValue = tne * tneGradOutValue;
    deterministicCompute(
        (__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, (__gm__ T*)dxGmAddr, tneDxIndex, tneDxValue,
        blockNum, batchNum, blockId, static_cast<uint32_t>(1));
    if (tneDxIndex != -100) {
        float tne_val = static_cast<float>(xGmAddr[tneDxIndex]);
        *gix += tne_val * (iy_t1 - iy) * (iz_t1 - iz) * tneGradOutValue;
        *giy -= tne_val * (ix - ix_tnw) * (iz_t1 - iz) * tneGradOutValue;
        *giz -= tne_val * (ix - ix_tnw) * (iy_t1 - iy) * tneGradOutValue;
    }
}

template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void ComputeTop2Points(
    __gm__ T* gradOutGmAddr, __gm__ T* xGmAddr, __gm__ T* dxGmAddr, __gm__ uint32_t* dxOutGmAddr,
    __gm__ T* dxOutValueGmAddr, float iz, float iy, float ix, uint32_t gridD, uint32_t gridH, uint32_t gridW,
    uint32_t batchNum, uint32_t channelIndex, uint32_t depthCol, uint32_t heightCol, uint32_t widthCol,
    uint32_t newInputIndex, uint32_t offsetBaseAddr, uint32_t xD, uint32_t xH, uint32_t xW, uint32_t channel, float tsw,
    float tse, int32_t iz_tnw, int32_t iy_tnw, int32_t ix_tnw, int32_t iz_t1, int32_t iy_t1, int32_t ix_t1, float* gix,
    float* giy, float* giz, uint32_t blockNum, uint32_t blockId)
{
    // tsw
    uint32_t tswDxIndex = static_cast<uint32_t>(-100);
    float tswGradOutValue = static_cast<float>(0.0);
    GetGradOutPointValueAndDxIndex(
        gradOutGmAddr, iz_tnw, iy_t1, ix_tnw, gridD, gridH, gridW, batchNum, depthCol, heightCol, widthCol,
        channelIndex, offsetBaseAddr, xD, xH, xW, channel, newInputIndex, &tswGradOutValue, &tswDxIndex);
    float tswDxValue = tsw * tswGradOutValue;
    deterministicCompute(
        (__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, (__gm__ T*)dxGmAddr, tswDxIndex, tswDxValue,
        blockNum, batchNum, blockId, static_cast<uint32_t>(2));
    if (tswDxIndex != -100) {
        float tsw_val = static_cast<float>(xGmAddr[tswDxIndex]);
        *gix -= tsw_val * (iy - iy_tnw) * (iz_t1 - iz) * tswGradOutValue;
        *giy += tsw_val * (ix_t1 - ix) * (iz_t1 - iz) * tswGradOutValue;
        *giz -= tsw_val * (ix_t1 - ix) * (iy - iy_tnw) * tswGradOutValue;
    }

    // tse
    uint32_t tseDxIndex = static_cast<uint32_t>(-100);
    float tseGradOutValue = static_cast<float>(0.0);
    GetGradOutPointValueAndDxIndex(
        gradOutGmAddr, iz_tnw, iy_t1, ix_t1, gridD, gridH, gridW, batchNum, depthCol, heightCol, widthCol, channelIndex,
        offsetBaseAddr, xD, xH, xW, channel, newInputIndex, &tseGradOutValue, &tseDxIndex);
    float tseDxValue = tse * tseGradOutValue;
    deterministicCompute(
        (__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, (__gm__ T*)dxGmAddr, tseDxIndex, tseDxValue,
        blockNum, batchNum, blockId, static_cast<uint32_t>(3));
    if (tseDxIndex != -100) {
        float tse_val = static_cast<float>(xGmAddr[tseDxIndex]);
        *gix += tse_val * (iy - iy_tnw) * (iz_t1 - iz) * tseGradOutValue;
        *giy += tse_val * (ix - ix_tnw) * (iz_t1 - iz) * tseGradOutValue;
        *giz -= tse_val * (ix - ix_tnw) * (iy - iy_tnw) * tseGradOutValue;
    }
}

template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void ComputeBottom1Points(
    __gm__ T* gradOutGmAddr, __gm__ T* xGmAddr, __gm__ T* dxGmAddr, __gm__ uint32_t* dxOutGmAddr,
    __gm__ T* dxOutValueGmAddr, float iz, float iy, float ix, uint32_t gridD, uint32_t gridH, uint32_t gridW,
    uint32_t batchNum, uint32_t channelIndex, uint32_t depthCol, uint32_t heightCol, uint32_t widthCol,
    uint32_t newInputIndex, uint32_t offsetBaseAddr, uint32_t xD, uint32_t xH, uint32_t xW, uint32_t channel, float bnw,
    float bne, int32_t iz_tnw, int32_t iy_tnw, int32_t ix_tnw, int32_t iz_t1, int32_t iy_t1, int32_t ix_t1, float* gix,
    float* giy, float* giz, uint32_t blockNum, uint32_t blockId)
{
    // bnw
    uint32_t bnwDxIndex = static_cast<uint32_t>(-100);
    float bnwGradOutValue = static_cast<float>(0.0);
    GetGradOutPointValueAndDxIndex(
        gradOutGmAddr, iz_t1, iy_tnw, ix_tnw, gridD, gridH, gridW, batchNum, depthCol, heightCol, widthCol,
        channelIndex, offsetBaseAddr, xD, xH, xW, channel, newInputIndex, &bnwGradOutValue, &bnwDxIndex);
    float bnwDxValue = bnw * bnwGradOutValue;
    deterministicCompute(
        (__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, (__gm__ T*)dxGmAddr, bnwDxIndex, bnwDxValue,
        blockNum, batchNum, blockId, static_cast<uint32_t>(4));
    if (bnwDxIndex != -100) {
        float bnw_val = static_cast<float>(xGmAddr[bnwDxIndex]);
        *gix -= bnw_val * (iy_t1 - iy) * (iz - iz_tnw) * bnwGradOutValue;
        *giy -= bnw_val * (ix_t1 - ix) * (iz - iz_tnw) * bnwGradOutValue;
        *giz += bnw_val * (ix_t1 - ix) * (iy_t1 - iy) * bnwGradOutValue;
    }

    // bne
    uint32_t bneDxIndex = static_cast<uint32_t>(-100);
    float bneGradOutValue = static_cast<float>(0.0);
    GetGradOutPointValueAndDxIndex(
        gradOutGmAddr, iz_t1, iy_tnw, ix_t1, gridD, gridH, gridW, batchNum, depthCol, heightCol, widthCol, channelIndex,
        offsetBaseAddr, xD, xH, xW, channel, newInputIndex, &bneGradOutValue, &bneDxIndex);
    float bneDxValue = bne * bneGradOutValue;
    deterministicCompute(
        (__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, (__gm__ T*)dxGmAddr, bneDxIndex, bneDxValue,
        blockNum, batchNum, blockId, static_cast<uint32_t>(5));
    if (bneDxIndex != -100) {
        float bne_val = static_cast<float>(xGmAddr[bneDxIndex]);
        *gix += bne_val * (iy_t1 - iy) * (iz - iz_tnw) * bneGradOutValue;
        *giy -= bne_val * (ix - ix_tnw) * (iz - iz_tnw) * bneGradOutValue;
        *giz += bne_val * (ix - ix_tnw) * (iy_t1 - iy) * bneGradOutValue;
    }
}

template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void ComputeBottom2Points(
    __gm__ T* gradOutGmAddr, __gm__ T* xGmAddr, __gm__ T* dxGmAddr, __gm__ uint32_t* dxOutGmAddr,
    __gm__ T* dxOutValueGmAddr, float iz, float iy, float ix, uint32_t gridD, uint32_t gridH, uint32_t gridW,
    uint32_t batchNum, uint32_t channelIndex, uint32_t depthCol, uint32_t heightCol, uint32_t widthCol,
    uint32_t newInputIndex, uint32_t offsetBaseAddr, uint32_t xD, uint32_t xH, uint32_t xW, uint32_t channel, float bsw,
    float bse, int32_t iz_tnw, int32_t iy_tnw, int32_t ix_tnw, int32_t iz_t1, int32_t iy_t1, int32_t ix_t1, float* gix,
    float* giy, float* giz, uint32_t blockNum, uint32_t blockId)
{
    // bsw
    uint32_t bswDxIndex = static_cast<uint32_t>(-100);
    float bswGradOutValue = static_cast<float>(0.0);
    GetGradOutPointValueAndDxIndex(
        gradOutGmAddr, iz_t1, iy_t1, ix_tnw, gridD, gridH, gridW, batchNum, depthCol, heightCol, widthCol, channelIndex,
        offsetBaseAddr, xD, xH, xW, channel, newInputIndex, &bswGradOutValue, &bswDxIndex);
    float bswDxValue = bsw * bswGradOutValue;
    deterministicCompute(
        (__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, (__gm__ T*)dxGmAddr, bswDxIndex, bswDxValue,
        blockNum, batchNum, blockId, static_cast<uint32_t>(6));
    if (bswDxIndex != -100) {
        float bsw_val = static_cast<float>(xGmAddr[bswDxIndex]);
        *gix -= bsw_val * (iy - iy_tnw) * (iz - iz_tnw) * bswGradOutValue;
        *giy += bsw_val * (ix_t1 - ix) * (iz - iz_tnw) * bswGradOutValue;
        *giz += bsw_val * (ix_t1 - ix) * (iy - iy_tnw) * bswGradOutValue;
    }

    // bse
    uint32_t bseDxIndex = static_cast<uint32_t>(-100);
    float bseGradOutValue = static_cast<float>(0.0);
    GetGradOutPointValueAndDxIndex(
        gradOutGmAddr, iz_t1, iy_t1, ix_t1, gridD, gridH, gridW, batchNum, depthCol, heightCol, widthCol, channelIndex,
        offsetBaseAddr, xD, xH, xW, channel, newInputIndex, &bseGradOutValue, &bseDxIndex);
    float bseDxValue = bse * bseGradOutValue;
    deterministicCompute(
        (__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, (__gm__ T*)dxGmAddr, bseDxIndex, bseDxValue,
        blockNum, batchNum, blockId, static_cast<uint32_t>(7));
    if (bseDxIndex != -100) {
        float bse_val = static_cast<float>(xGmAddr[bseDxIndex]);
        *gix += bse_val * (iy - iy_tnw) * (iz - iz_tnw) * bseGradOutValue;
        *giy += bse_val * (ix - ix_tnw) * (iz - iz_tnw) * bseGradOutValue;
        *giz += bse_val * (ix - ix_tnw) * (iy - iy_tnw) * bseGradOutValue;
    }
}

template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void ComputeBilinear(
    __gm__ T* gradOutGmAddr, __gm__ T* xGmAddr, __gm__ T* dxGmAddr, __gm__ T* dgridGmAddr, __gm__ uint32_t* dxOutGmAddr,
    __gm__ T* dxOutValueGmAddr, float iz, float iy, float ix, uint32_t gridD, uint32_t gridH, uint32_t gridW,
    uint32_t batchNum, uint32_t depthCol, uint32_t heightCol, uint32_t widthCol, uint32_t newInputIndex,
    uint32_t offsetBaseAddr, uint32_t xD, uint32_t xH, uint32_t xW, uint32_t channel, uint32_t pNumPerCore,
    uint32_t blockNum, float* ixGradMultValue, float* iyGradMultValue, float* izGradMultValue, uint32_t blockId)
{
    int32_t ix_tnw = GetFloorValue(ix);
    int32_t iy_tnw = GetFloorValue(iy);
    int32_t iz_tnw = GetFloorValue(iz);

    int32_t ix_t1 = ix_tnw + 1;
    int32_t iy_t1 = iy_tnw + 1;
    int32_t iz_t1 = iz_tnw + 1;

    // get surfaces to each neighbor:
    float bnw = (ix_t1 - ix) * (iy_t1 - iy) * (iz - iz_tnw);
    float bne = (ix - ix_tnw) * (iy_t1 - iy) * (iz - iz_tnw);
    float bsw = (ix_t1 - ix) * (iy - iy_tnw) * (iz - iz_tnw);
    float bse = (ix - ix_tnw) * (iy - iy_tnw) * (iz - iz_tnw);
    float tnw = (ix_t1 - ix) * (iy_t1 - iy) * (iz_t1 - iz);
    float tne = (ix - ix_tnw) * (iy_t1 - iy) * (iz_t1 - iz);
    float tsw = (ix_t1 - ix) * (iy - iy_tnw) * (iz_t1 - iz);
    float tse = (ix - ix_tnw) * (iy - iy_tnw) * (iz_t1 - iz);

    float gix = static_cast<float>(0);
    float giy = static_cast<float>(0);
    float giz = static_cast<float>(0);

    // calculate and set grad_input.
    for (uint32_t channelIndex = 0; channelIndex < channel; channelIndex++) {
        ComputeTop1Points(
            (__gm__ T*)gradOutGmAddr, (__gm__ T*)xGmAddr, (__gm__ T*)dxGmAddr, (__gm__ uint32_t*)dxOutGmAddr,
            (__gm__ T*)dxOutValueGmAddr, iz, iy, ix, gridD, gridH, gridW, batchNum, channelIndex, depthCol, heightCol,
            widthCol, newInputIndex, offsetBaseAddr, xD, xH, xW, channel, tnw, tne, iz_tnw, iy_tnw, ix_tnw, iz_t1,
            iy_t1, ix_t1, &gix, &giy, &giz, blockNum, blockId);
        ComputeTop2Points(
            (__gm__ T*)gradOutGmAddr, (__gm__ T*)xGmAddr, (__gm__ T*)dxGmAddr, (__gm__ uint32_t*)dxOutGmAddr,
            (__gm__ T*)dxOutValueGmAddr, iz, iy, ix, gridD, gridH, gridW, batchNum, channelIndex, depthCol, heightCol,
            widthCol, newInputIndex, offsetBaseAddr, xD, xH, xW, channel, tsw, tse, iz_tnw, iy_tnw, ix_tnw, iz_t1,
            iy_t1, ix_t1, &gix, &giy, &giz, blockNum, blockId);
        ComputeBottom1Points(
            (__gm__ T*)gradOutGmAddr, (__gm__ T*)xGmAddr, (__gm__ T*)dxGmAddr, (__gm__ uint32_t*)dxOutGmAddr,
            (__gm__ T*)dxOutValueGmAddr, iz, iy, ix, gridD, gridH, gridW, batchNum, channelIndex, depthCol, heightCol,
            widthCol, newInputIndex, offsetBaseAddr, xD, xH, xW, channel, bnw, bne, iz_tnw, iy_tnw, ix_tnw, iz_t1,
            iy_t1, ix_t1, &gix, &giy, &giz, blockNum, blockId);
        ComputeBottom2Points(
            (__gm__ T*)gradOutGmAddr, (__gm__ T*)xGmAddr, (__gm__ T*)dxGmAddr, (__gm__ uint32_t*)dxOutGmAddr,
            (__gm__ T*)dxOutValueGmAddr, iz, iy, ix, gridD, gridH, gridW, batchNum, channelIndex, depthCol, heightCol,
            widthCol, newInputIndex, offsetBaseAddr, xD, xH, xW, channel, bsw, bse, iz_tnw, iy_tnw, ix_tnw, iz_t1,
            iy_t1, ix_t1, &gix, &giy, &giz, blockNum, blockId);

        dgridGmAddr[offsetBaseAddr] = static_cast<T>((*ixGradMultValue) * gix);
        dgridGmAddr[offsetBaseAddr + 1] = static_cast<T>((*iyGradMultValue) * giy);
        dgridGmAddr[offsetBaseAddr + 2] = static_cast<T>((*izGradMultValue) * giz);
    }
}

template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void ComputeNearest(
    __gm__ T* gradOutGmAddr, __gm__ T* xGmAddr, __gm__ T* dxGmAddr, __gm__ T* dgridGmAddr, __gm__ uint32_t* dxOutGmAddr,
    __gm__ T* dxOutValueGmAddr, float iz, float iy, float ix, uint32_t gridD, uint32_t gridH, uint32_t gridW,
    uint32_t batchNum, uint32_t depthCol, uint32_t heightCol, uint32_t widthCol, uint32_t newInputIndex,
    uint32_t offsetBaseAddr, uint32_t xD, uint32_t xH, uint32_t xW, uint32_t channel, uint32_t pNumPerCore,
    uint32_t blockNum, uint32_t blockId)
{
    int32_t iz_nearest = rintf(iz);
    int32_t iy_nearest = rintf(iy);
    int32_t ix_nearest = rintf(ix);

    for (uint32_t channelIndex = 0; channelIndex < channel; channelIndex++) {
        float gradOutValue = static_cast<float>(0.0);
        uint32_t dxIndex = static_cast<uint32_t>(-100);
        GetGradOutPointValueAndDxIndex(
            gradOutGmAddr, iz_nearest, iy_nearest, ix_nearest, gridD, gridH, gridW, batchNum, depthCol, heightCol,
            widthCol, channelIndex, offsetBaseAddr, xD, xH, xW, channel, newInputIndex, &gradOutValue, &dxIndex);
        deterministicCompute(
            (__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, (__gm__ T*)dxGmAddr, dxIndex, gradOutValue,
            blockNum, batchNum, blockId, 0);

        dgridGmAddr[offsetBaseAddr] = static_cast<T>(0);
        dgridGmAddr[offsetBaseAddr + 1] = static_cast<T>(0);
        dgridGmAddr[offsetBaseAddr + 2] = static_cast<T>(0);
    }
}

// LAUNCH_BOUND
template <typename T>
__simt_vf__ LAUNCH_BOUND(VF_MAX_THREAD_NUM) __aicore__ void ComputeGridSampler3DGrad(
    __gm__ T* gradOutGmAddr, __gm__ T* xGmAddr, __gm__ T* gridGmAddr, __gm__ T* dxGmAddr, __gm__ T* dgridGmAddr,
    __gm__ uint32_t* dxOutGmAddr, __gm__ T* dxOutValueGmAddr, uint32_t blockNum, uint32_t batch, uint32_t channel,
    uint32_t xD, uint32_t xH, uint32_t xW, uint32_t gridD, uint32_t gridH, uint32_t gridW, uint32_t interpolation,
    uint32_t padding, uint32_t alignCorners, uint32_t pNumPerCore, uint32_t gridSize, uint32_t shiftD_, uint32_t mD_,
    uint32_t shiftH_, uint32_t mH_, uint32_t shiftW_, uint32_t mW_, uint32_t blockId_)
{
    // pNumPerCore : 每个核计算的N的个数
    for (uint32_t index = blockId_ * gridSize * pNumPerCore + threadIdx.x;
         (index < (blockId_ + 1) * gridSize * pNumPerCore) && (index < gridSize * batch); index += VF_MAX_THREAD_NUM) {
        // output info (N D K_d H K_h W K_w, groups, groupC)
        uint32_t batchNum, depthCol, heightCol, widthCol;
        // fast division, addr/factor
        batchNum = Simt::UintDiv(index, mD_, shiftD_);
        uint32_t remain = index - batchNum * gridSize;

        depthCol = Simt::UintDiv(remain, mH_, shiftH_);
        remain = remain - depthCol * (gridH * gridW);

        heightCol = Simt::UintDiv(remain, mW_, shiftW_);
        widthCol = remain - heightCol * gridW;

        uint32_t offsetBaseAddr =
            (batchNum * gridD * gridH * gridW + depthCol * gridH * gridW + heightCol * gridW + widthCol) * 3;
        uint32_t newInputIndex = batchNum * channel * xD * xH * xW;

        // multipliers for gradients on ix, iy, and iz
        float ixGradMultValue = 0;
        float iyGradMultValue = 0;
        float izGradMultValue = 0;

        // get the corresponding input x, y, z co-ordinates from grid
        float ix = static_cast<float>(gridGmAddr[offsetBaseAddr]);     // ix
        float iy = static_cast<float>(gridGmAddr[offsetBaseAddr + 1]); // iy
        float iz = static_cast<float>(gridGmAddr[offsetBaseAddr + 2]); // iz

        ix = ComputeSourceIndexSetGrad(ix, xW, padding, alignCorners, &ixGradMultValue);
        iy = ComputeSourceIndexSetGrad(iy, xH, padding, alignCorners, &iyGradMultValue);
        iz = ComputeSourceIndexSetGrad(iz, xD, padding, alignCorners, &izGradMultValue);

        if (interpolation == BILINEAR) {
            // get corner pixel values from (x, y, z)
            // for 5d, we add top-bottom
            ComputeBilinear(
                (__gm__ T*)gradOutGmAddr, (__gm__ T*)xGmAddr, (__gm__ T*)dxGmAddr, (__gm__ T*)dgridGmAddr,
                (__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, iz, iy, ix, gridD, gridH, gridW, batchNum,
                depthCol, heightCol, widthCol, newInputIndex, offsetBaseAddr, xD, xH, xW, channel, pNumPerCore,
                blockNum, &ixGradMultValue, &iyGradMultValue, &izGradMultValue, blockId_);
        } else if (interpolation == NEAREST) {
            ComputeNearest(
                (__gm__ T*)gradOutGmAddr, (__gm__ T*)xGmAddr, (__gm__ T*)dxGmAddr, (__gm__ T*)dgridGmAddr,
                (__gm__ uint32_t*)dxOutGmAddr, (__gm__ T*)dxOutValueGmAddr, iz, iy, ix, gridD, gridH, gridW, batchNum,
                depthCol, heightCol, widthCol, newInputIndex, offsetBaseAddr, xD, xH, xW, channel, pNumPerCore,
                blockNum, blockId_);
        }
    }
}

template <typename T>
__aicore__ inline void GridSampler3DGradSimtDet<T>::Process()
{
    uint32_t shiftD_, mD_, shiftH_, mH_, shiftW_, mW_;
    uint32_t gridSize = tiling_->gridD * tiling_->gridH * tiling_->gridW;
    GetUintDivMagicAndShift(mD_, shiftD_, gridSize);
    GetUintDivMagicAndShift(mH_, shiftH_, static_cast<uint32_t>(tiling_->gridH * tiling_->gridW));
    GetUintDivMagicAndShift(mW_, shiftW_, static_cast<uint32_t>(tiling_->gridW));
    asc_vf_call<ComputeGridSampler3DGrad<T>>(
        dim3{VF_MAX_THREAD_NUM, 1, 1}, (__gm__ T*)(inputGm[GRAD_INPUT_INDEX_SIMT].GetPhyAddr()),
        (__gm__ T*)(inputGm[X_INPUT_INDEX_SIMT].GetPhyAddr()), (__gm__ T*)(inputGm[GRID_INPUT_INDEX_SIMT].GetPhyAddr()),
        (__gm__ T*)(inputGm[DX_INPUT_INDEX_SIMT].GetPhyAddr()), (__gm__ T*)(inputGm[DGRID_INPUT_INDEX_SIMT].GetPhyAddr()),
        (__gm__ uint32_t*)(tmpOutGm[TMP_OUT_INDEX].GetPhyAddr()),
        (__gm__ T*)(tmpOutValueGm[TMP_OUT_INDEX].GetPhyAddr()), tiling_->blockNum, tiling_->batch, tiling_->channel,
        tiling_->xD, tiling_->xH, tiling_->xW, tiling_->gridD, tiling_->gridH, tiling_->gridW, tiling_->interpolation,
        tiling_->padding, tiling_->alignCorners, tiling_->pNumPerCore, gridSize, shiftD_, mD_, shiftH_, mH_, shiftW_,
        mW_, blockId_);
}
} // namespace GridSampler3DGradSimtDetNS
#endif // GRID_SAMPLER3D_GRAD_SIMT_DET_H_
