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
 * \file grid_sampler2_d_grad_bicubic.h
 * \brief GridSampler2D backward with bicubic interpolation mode
 */
#ifndef GRID_SAMPLER_2D_GRAD_BICUBIC_H_
#define GRID_SAMPLER_2D_GRAD_BICUBIC_H_

#include "kernel_operator.h"

using namespace AscendC;

constexpr static int32_t BUFFER_NUM_ONE = 1;

template <typename T, typename GridSamplerGradTilingData>
class GridSampler2DGradBicubic {
public:
    __aicore__ inline GridSampler2DGradBicubic(){};
    __aicore__ inline void Init(
        const GridSamplerGradTilingData& __restrict tilingData, GM_ADDR inputTensors[INPUT_NUM + OUTPUT_NUM + 1]);
    __aicore__ inline void InitBuffer(TPipe* inputPipe);
    __aicore__ inline void InitBicubicLocalTensor();
    __aicore__ inline void CopyOut(const int32_t offset, const int32_t calCount);
    __aicore__ inline void CopyIn(const int64_t offset, const int32_t calCount, const int32_t inputIndex);
    __aicore__ inline void Process();
    __aicore__ inline void Compute(const int32_t computeCount, const int64_t curGridPointIndex);

    // cubic convolution functions
    __aicore__ inline void CubicConvolution1(
        LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount);
    __aicore__ inline void CubicConvolution2(
        LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount);
    __aicore__ inline void CubicConvolution1Grad(
        LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount);
    __aicore__ inline void CubicConvolution2Grad(
        LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount);
    __aicore__ inline void GetCubicUpsampleCoefficients(
        LocalTensor<T> coeffTx0, LocalTensor<T> coeffTx1, LocalTensor<T> coeffTx2, LocalTensor<T> coeffTx3,
        LocalTensor<T> coeffTy0, LocalTensor<T> coeffTy1, LocalTensor<T> coeffTy2, LocalTensor<T> coeffTy3,
        LocalTensor<T> cubicTx, LocalTensor<T> cubicTy, const int32_t calCount);

    // coordinate and index functions (reuse from bilinear)
    __aicore__ inline void ComputeSourceIndexSetGrad(
        LocalTensor<T> dataTensor, LocalTensor<T> dupTensor, const T size, const int32_t calCount);
    __aicore__ inline T ReflectCoordinatesCommon(T coord, int32_t size_val, bool align_corners_flag);
    __aicore__ inline void DupValue();

    template <typename T1, typename T2>
    __aicore__ inline T1 CeilDiv(T1 a, T2 b)
    {
        return (a + b - 1) / b;
    };
    template <typename T1, typename T2>
    __aicore__ inline T1 CeilAlign(T1 a, T2 b)
    {
        return (a + b - 1) / b * b;
    };

private:
    TPipe* pipe;
    TQue<QuePosition::VECIN, BUFFER_NUM_ONE> dataInQueue[INPUT_NUM];
    TQue<QuePosition::VECOUT, BUFFER_NUM_ONE> dataOutQueue[OUTPUT_NUM];

    // coordinate buffers
    TBuf<TPosition::VECCALC> xCoordinateBuf;
    TBuf<TPosition::VECCALC> yCoordinateBuf;
    TBuf<TPosition::VECCALC> xGradInBuf;
    TBuf<TPosition::VECCALC> yGradInBuf;

    // 4x4 neighborhood float coordinates: ixNw, ixNe, ixSw, ixSe, iyNw, iyNe, iySw, iySe
    TBuf<TPosition::VECCALC> ixNwBuf;
    TBuf<TPosition::VECCALC> iyNwBuf;
    TBuf<TPosition::VECCALC> ixNeBuf;
    TBuf<TPosition::VECCALC> iyNeBuf;
    TBuf<TPosition::VECCALC> ixSwBuf;
    TBuf<TPosition::VECCALC> iySwBuf;
    TBuf<TPosition::VECCALC> ixSeBuf;
    TBuf<TPosition::VECCALC> iySeBuf;

    // integer coordinates
    TBuf<TPosition::VECCALC> ixNwIntBuf;
    TBuf<TPosition::VECCALC> iyNwIntBuf;
    TBuf<TPosition::VECCALC> ixNeIntBuf;
    TBuf<TPosition::VECCALC> iyNeIntBuf;
    TBuf<TPosition::VECCALC> ixSwIntBuf;
    TBuf<TPosition::VECCALC> iySwIntBuf;
    TBuf<TPosition::VECCALC> ixSeIntBuf;
    TBuf<TPosition::VECCALC> iySeIntBuf;

    // cubic coefficients
    TBuf<TPosition::VECCALC> coeffTx0Buf;
    TBuf<TPosition::VECCALC> coeffTx1Buf;
    TBuf<TPosition::VECCALC> coeffTx2Buf;
    TBuf<TPosition::VECCALC> coeffTx3Buf;
    TBuf<TPosition::VECCALC> coeffTy0Buf;
    TBuf<TPosition::VECCALC> coeffTy1Buf;
    TBuf<TPosition::VECCALC> coeffTy2Buf;
    TBuf<TPosition::VECCALC> coeffTy3Buf;

    // weight buffer for bicubic
    TBuf<TPosition::VECCALC> weightBuf;

    // temporary buffers
    TBuf<TPosition::VECCALC> tmp1Buf;
    TBuf<TPosition::VECCALC> tmp2Buf;
    TBuf<TPosition::VECCALC> tmp5Buf;
    TBuf<TPosition::VECCALC> tmp6Buf;
    TBuf<TPosition::VECCALC> tmp7Buf;
    TBuf<TPosition::VECCALC> tmp8Buf;
    TBuf<TPosition::VECCALC> tmp9Buf;

    // mask buffers
    TBuf<TPosition::VECCALC> mask1Buf;
    TBuf<TPosition::VECCALC> mask2Buf;
    TBuf<TPosition::VECCALC> mask3Buf;

    // select and dup buffers
    TBuf<TPosition::VECCALC> dupOneBuf;
    TBuf<TPosition::VECCALC> selBuf1;
    TBuf<TPosition::VECCALC> selBuf2;
    TBuf<TPosition::VECCALC> selBuf3;
    TBuf<TPosition::VECCALC> selBuf4;

    // compute index buffers
    TBuf<TPosition::VECCALC> computeIndexBuf1;
    TBuf<TPosition::VECCALC> computeIndexBuf2;
    TBuf<TPosition::VECCALC> computeIndexBuf3;
    TBuf<TPosition::VECCALC> computeIndexBuf4;
    TBuf<TPosition::VECCALC> computeIndexBuf5;
    TBuf<TPosition::VECCALC> computeIndexBuf6;
    TBuf<TPosition::VECCALC> computeIndexBuf7;
    TBuf<TPosition::VECCALC> computeIndexBuf8;
    TBuf<TPosition::VECCALC> computeIndexBuf9;

    // gix/giy accumulation buffers
    TBuf<TPosition::VECCALC> gixBuf;
    TBuf<TPosition::VECCALC> giyBuf;
    TBuf<TPosition::VECCALC> sumXBuf;
    TBuf<TPosition::VECCALC> sumYBuf;
    TBuf<TPosition::VECCALC> clipLimitBuf;

    // temporary buffer for inner loop (inputX only - for MTE2 direction)
    TBuf<TPosition::VECCALC> inputXLocalBuf;

    GlobalTensor<T> inputGm[INPUT_NUM + OUTPUT_NUM];

    uint32_t batch = 0;
    uint32_t pNumPerCore = 0;
    uint32_t tailPNum = 0;
    int32_t channel = 0;
    int32_t alignChannel = 0;
    int32_t height = 0;
    int32_t width = 0;
    T fheight = 0;
    T fwidth = 0;
    uint32_t blockNum = 0;
    uint32_t ubFactorElement = 0;
    uint32_t interpolation = 0;
    uint32_t padding = 0;
    uint32_t alignCorners = 0;
    uint32_t gridH = 0;
    uint32_t gridW = 0;
    uint32_t outH = 0;
    uint32_t outW = 0;
    uint32_t perBlockCount = 0;
    uint32_t blockIdx = 0;
    uint32_t dataCount = 0;
    uint32_t batchOffset = 0;
    uint32_t baseOffset = 0;
    uint32_t alignBufferNum = 0;
    uint32_t xStrideC = 0;
    uint32_t dxStrideN = 0;
    uint32_t dxStrideC = 0;
    int32_t dxStrideH = 0;
    uint32_t dxStrideW = 0;
    uint32_t gradStrideC = 0;
    uint32_t gradStrideH = 0;
    uint32_t gradStrideW = 0;
    uint32_t maskSize = 0;
    uint32_t maskNum = 0;
    int32_t inputStrideH = 0;
    uint32_t inputStrideW = 0;
    uint32_t inputStrideN = 0;
    int64_t pointIndex = 0;
    int64_t baseGradGmOffset = 0;
    int64_t gradGmOffset = 0;
    int64_t baseGmOffset = 0;
    int32_t pointOffset = 0;
    int64_t xGmOffset = 0;
    int32_t ncOffset = 0;
    int32_t group = 0;
    uint32_t isDeterministic = 0;
    uint32_t tailBNum = 0;
    T gix = static_cast<T>(0);
    T giy = static_cast<T>(0);

    LocalTensor<uint8_t> mask1Tensor;
    LocalTensor<uint8_t> mask2Tensor;
    LocalTensor<uint8_t> mask3Tensor;
    LocalTensor<uint16_t> int8ToInt16Mask1;
    LocalTensor<uint16_t> int8ToInt16Mask2;
    LocalTensor<T> dupOneTensor;
    LocalTensor<T> selTensor1;
    LocalTensor<T> selTensor2;
    LocalTensor<T> selTensor3;
    LocalTensor<T> selTensor4;
    LocalTensor<T> tmp1Tensor;
    LocalTensor<T> tmp2Tensor;
    LocalTensor<int32_t> tmpIndex;
    LocalTensor<T> gixLocalTensor;
    LocalTensor<T> giyLocalTensor;
    LocalTensor<T> sumX;
    LocalTensor<T> sumY;
    LocalTensor<T> clipLimit;
};

template <typename T, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubic<T, GridSamplerGradTilingData>::Init(
    const GridSamplerGradTilingData& __restrict tilingData, GM_ADDR inputTensors[INPUT_NUM + OUTPUT_NUM + 1])
{
    batch = tilingData.batch;
    pNumPerCore = tilingData.pNumPerCore;
    tailPNum = tilingData.tailPNum;
    channel = tilingData.channel;
    height = tilingData.height;
    width = tilingData.width;
    fheight = static_cast<T>(height);
    fwidth = static_cast<T>(width);
    blockNum = tilingData.blockNum;
    ubFactorElement = tilingData.ubFactorElement;
    interpolation = tilingData.interpolation;
    padding = tilingData.padding;
    alignCorners = tilingData.alignCorners;
    group = tilingData.group;
    gridH = tilingData.gridH;
    gridW = tilingData.gridW;
    isDeterministic = tilingData.isDeterministic;
    tailBNum = tilingData.tailBNum;
    outW = gridW;
    outH = gridH;
    dataCount = gridH * gridW;
    maskSize = CeilAlign(CeilDiv(ubFactorElement, UINT8_BITS), BLOCK_BYTES);
    maskNum = maskSize / sizeof(uint8_t);
    xStrideC = width * height;
    dxStrideN = channel * width * height;
    dxStrideC = width * height;
    dxStrideH = width;
    dxStrideW = 1;
    gradStrideC = gridH * gridW;
    inputStrideH = width;
    inputStrideW = 1;
    inputStrideN = channel * width * height;
    blockIdx = GetBlockIdx();
    perBlockCount = BLOCK_BYTES / sizeof(T);
    alignChannel = CeilAlign(channel, perBlockCount);

    inputGm[GRAD_INPUT_INDEX].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[GRAD_INPUT_INDEX]));
    inputGm[X_INPUT_INDEX].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[X_INPUT_INDEX]));
    inputGm[GRID_INPUT_INDEX].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[GRID_INPUT_INDEX]));
    inputGm[DX_INPUT_INDEX].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[DX_INPUT_INDEX]));
    inputGm[DGRID_INPUT_INDEX].SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[DGRID_INPUT_INDEX]));
}

template <typename T, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubic<T, GridSamplerGradTilingData>::InitBuffer(TPipe* inputPipe)
{
    pipe = inputPipe;
    // bicubic branch
    pipe->InitBuffer(dataInQueue[0], BUFFER_NUM_ONE, alignChannel * sizeof(T));
    pipe->InitBuffer(dataInQueue[1], BUFFER_NUM_ONE, alignChannel * sizeof(T));
    pipe->InitBuffer(dataInQueue[GRID_INPUT_INDEX], BUFFER_NUM_ONE, BUFFER_APPLY_NUM * ubFactorElement * sizeof(T));
    pipe->InitBuffer(dataOutQueue[0], BUFFER_NUM_ONE, alignChannel * sizeof(T));
    pipe->InitBuffer(dataOutQueue[1], BUFFER_NUM_ONE, BUFFER_APPLY_NUM * ubFactorElement * sizeof(T));

    pipe->InitBuffer(xCoordinateBuf, (ubFactorElement + ELE_NUM_PER_REPEAT) * sizeof(T));
    pipe->InitBuffer(yCoordinateBuf, (ubFactorElement + ELE_NUM_PER_REPEAT) * sizeof(T));
    pipe->InitBuffer(xGradInBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(yGradInBuf, ubFactorElement * sizeof(T));

    // 4x4 neighborhood float coordinates
    pipe->InitBuffer(ixNwBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iyNwBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(ixNeBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iyNeBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(ixSwBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iySwBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(ixSeBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iySeBuf, ubFactorElement * sizeof(T));

    // integer coordinates
    pipe->InitBuffer(ixNwIntBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iyNwIntBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(ixNeIntBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iyNeIntBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(ixSwIntBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iySwIntBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(ixSeIntBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iySeIntBuf, ubFactorElement * sizeof(T));

    // cubic coefficients
    pipe->InitBuffer(coeffTx0Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(coeffTx1Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(coeffTx2Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(coeffTx3Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(coeffTy0Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(coeffTy1Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(coeffTy2Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(coeffTy3Buf, ubFactorElement * sizeof(T));

    // weight buffer
    pipe->InitBuffer(weightBuf, ubFactorElement * sizeof(T));

    // temporary buffers
    pipe->InitBuffer(tmp1Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(tmp2Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(tmp5Buf, ubFactorElement * sizeof(int32_t));
    pipe->InitBuffer(tmp6Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(tmp7Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(tmp8Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(tmp9Buf, ubFactorElement * sizeof(T));

    // mask buffers
    pipe->InitBuffer(mask1Buf, maskSize);
    pipe->InitBuffer(mask2Buf, maskSize);
    pipe->InitBuffer(mask3Buf, maskSize);

    // select and dup buffers
    pipe->InitBuffer(dupOneBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(selBuf1, ubFactorElement * sizeof(T));
    pipe->InitBuffer(selBuf2, ubFactorElement * sizeof(T));
    pipe->InitBuffer(selBuf3, ubFactorElement * sizeof(T));
    pipe->InitBuffer(selBuf4, ubFactorElement * sizeof(T));

    // compute index buffers
    pipe->InitBuffer(computeIndexBuf1, ubFactorElement * sizeof(int32_t));
    pipe->InitBuffer(computeIndexBuf2, ubFactorElement * sizeof(T));  // reused as dCoeffTy0
    pipe->InitBuffer(computeIndexBuf3, ubFactorElement * sizeof(T));  // reused as dCoeffTy1
    pipe->InitBuffer(computeIndexBuf4, ubFactorElement * sizeof(T));  // reused as dCoeffTy2
    pipe->InitBuffer(computeIndexBuf5, ubFactorElement * sizeof(T));  // reused as dCoeffTy3
    pipe->InitBuffer(computeIndexBuf6, ubFactorElement * sizeof(int32_t));
    pipe->InitBuffer(computeIndexBuf7, ubFactorElement * sizeof(int32_t));
    pipe->InitBuffer(computeIndexBuf8, ubFactorElement * sizeof(int32_t));
    pipe->InitBuffer(computeIndexBuf9, ubFactorElement * sizeof(int32_t));

    // gix/giy accumulation
    pipe->InitBuffer(gixBuf, alignChannel * sizeof(T));
    pipe->InitBuffer(giyBuf, alignChannel * sizeof(T));
    pipe->InitBuffer(sumXBuf, alignChannel * sizeof(T));
    pipe->InitBuffer(sumYBuf, alignChannel * sizeof(T));
    pipe->InitBuffer(clipLimitBuf, ubFactorElement * sizeof(T));

    // temporary buffer for inner loop (inputX only - for MTE2 direction)
    pipe->InitBuffer(inputXLocalBuf, alignChannel * sizeof(T));
}

template <typename T, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubic<T, GridSamplerGradTilingData>::InitBicubicLocalTensor()
{
    mask1Tensor = mask1Buf.Get<uint8_t>(maskNum);
    mask2Tensor = mask2Buf.Get<uint8_t>(maskNum);
    mask3Tensor = mask3Buf.Get<uint8_t>(maskNum);
    dupOneTensor = dupOneBuf.Get<T>(ubFactorElement);
    tmpIndex = computeIndexBuf1.Get<int32_t>(ubFactorElement);
    selTensor1 = selBuf1.Get<T>(ubFactorElement);
    tmp1Tensor = tmp1Buf.Get<T>(ubFactorElement);
    tmp2Tensor = tmp2Buf.Get<T>(ubFactorElement);
    selTensor2 = selBuf2.Get<T>(ubFactorElement);
    selTensor3 = selBuf3.Get<T>(ubFactorElement);
    selTensor4 = selBuf4.Get<T>(ubFactorElement);
    sumX = sumXBuf.Get<T>(alignChannel);
    sumY = sumYBuf.Get<T>(alignChannel);
    clipLimit = clipLimitBuf.Get<T>(ubFactorElement);
}

// CubicConvolution1: f(x) = (A+2)*|x|^3 - (A+3)*|x|^2 + 1, A=-0.75
// => 1.25*x^3 - 2.25*x^2 + 1.0
template <typename T, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubic<T, GridSamplerGradTilingData>::CubicConvolution1(
    LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount)
{
    T alph = static_cast<T>(1.25);
    T beta = static_cast<T>(-2.25);

    Muls(coeff, x, alph, calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, beta, calCount);
    PipeBarrier<PIPE_V>();
    Mul(coeff, coeff, x, calCount);
    PipeBarrier<PIPE_V>();
    Mul(coeff, coeff, x, calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
}

// CubicConvolution2: f(x) = A*|x|^3 - 5A*|x|^2 + 8A*|x| - 4A, A=-0.75
// => -0.75*x^3 + 3.75*x^2 - 6.0*x + 3.0
template <typename T, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubic<T, GridSamplerGradTilingData>::CubicConvolution2(
    LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount)
{
    T A = static_cast<T>(-0.75);
    T alph = static_cast<T>(3.75);
    T beta = static_cast<T>(-6.0);
    T gama = static_cast<T>(3.0);

    Muls(coeff, x, A, calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, alph, calCount);
    PipeBarrier<PIPE_V>();
    Mul(coeff, coeff, x, calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, beta, calCount);
    PipeBarrier<PIPE_V>();
    Mul(coeff, coeff, x, calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, gama, calCount);
    PipeBarrier<PIPE_V>();
}

// CubicConvolution1Grad: f'(x) = 3*(A+2)*x^2 - 2*(A+3)*x, A=-0.75
// => 3.75*x^2 - 4.5*x
template <typename T, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubic<T, GridSamplerGradTilingData>::CubicConvolution1Grad(
    LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount)
{
    T alph = static_cast<T>(3.75);
    T beta = static_cast<T>(-4.5);

    Muls(coeff, x, alph, calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, beta, calCount);
    PipeBarrier<PIPE_V>();
    Mul(coeff, coeff, x, calCount);
    PipeBarrier<PIPE_V>();
}

// CubicConvolution2Grad: f'(x) = 3*A*x^2 - 10*A*x + 8*A, A=-0.75
// => -2.25*x^2 + 7.5*x - 6.0
template <typename T, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubic<T, GridSamplerGradTilingData>::CubicConvolution2Grad(
    LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount)
{
    T alph = static_cast<T>(-2.25);
    T beta = static_cast<T>(7.5);
    T gama = static_cast<T>(-6.0);

    Muls(coeff, x, alph, calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, beta, calCount);
    PipeBarrier<PIPE_V>();
    Mul(coeff, coeff, x, calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, gama, calCount);
    PipeBarrier<PIPE_V>();
}

// GetCubicUpsampleCoefficients: compute 8 cubic interpolation coefficients
template <typename T, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubic<T, GridSamplerGradTilingData>::GetCubicUpsampleCoefficients(
    LocalTensor<T> coeffTx0, LocalTensor<T> coeffTx1, LocalTensor<T> coeffTx2, LocalTensor<T> coeffTx3,
    LocalTensor<T> coeffTy0, LocalTensor<T> coeffTy1, LocalTensor<T> coeffTy2, LocalTensor<T> coeffTy3,
    LocalTensor<T> cubicTx, LocalTensor<T> cubicTy, const int32_t calCount)
{
    // Use sel buffers for intermediate values to avoid conflict with cubicTx/cubicTy
    // which are stored in tmp1Buf/tmp2Buf in the Compute function
    LocalTensor<T> cubicTx1 = selBuf1.Get<T>(ubFactorElement);
    LocalTensor<T> cubicTx2 = selBuf2.Get<T>(ubFactorElement);
    LocalTensor<T> cubicTx3 = tmp6Buf.Get<T>(ubFactorElement);
    LocalTensor<T> cubicTy1 = tmp7Buf.Get<T>(ubFactorElement);
    LocalTensor<T> cubicTy2 = tmp8Buf.Get<T>(ubFactorElement);
    LocalTensor<T> cubicTy3 = tmp9Buf.Get<T>(ubFactorElement);

    // cubicTx1 = tx + 1, cubicTx2 = 1 - tx, cubicTx3 = 2 - tx
    Adds(cubicTx1, cubicTx, static_cast<T>(1.0), calCount);
    Adds(cubicTy1, cubicTy, static_cast<T>(1.0), calCount);
    Muls(cubicTx2, cubicTx, static_cast<T>(-1.0), calCount);
    Muls(cubicTy2, cubicTy, static_cast<T>(-1.0), calCount);
    PipeBarrier<PIPE_V>();
    Adds(cubicTx2, cubicTx2, static_cast<T>(1.0), calCount);
    Adds(cubicTx3, cubicTx2, static_cast<T>(1.0), calCount);
    Adds(cubicTy2, cubicTy2, static_cast<T>(1.0), calCount);
    Adds(cubicTy3, cubicTy2, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();

    // coeffTx0 = CubicConv2(tx+1), coeffTx1 = CubicConv1(tx), coeffTx2 = CubicConv1(1-tx), coeffTx3 = CubicConv2(2-tx)
    CubicConvolution2(coeffTx0, cubicTx1, calCount);
    CubicConvolution1(coeffTx1, cubicTx, calCount);
    CubicConvolution1(coeffTx2, cubicTx2, calCount);
    CubicConvolution2(coeffTx3, cubicTx3, calCount);

    // coeffTy0~3 same pattern
    CubicConvolution2(coeffTy0, cubicTy1, calCount);
    CubicConvolution1(coeffTy1, cubicTy, calCount);
    CubicConvolution1(coeffTy2, cubicTy2, calCount);
    CubicConvolution2(coeffTy3, cubicTy3, calCount);
}

// ComputeSourceIndexSetGrad: same as bilinear
template <typename T, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubic<T, GridSamplerGradTilingData>::ComputeSourceIndexSetGrad(
    LocalTensor<T> dataTensor, LocalTensor<T> dupTensor, const T size, const int32_t calCount)
{
    if (alignCorners == 1) {
        T val = static_cast<T>(size - 1) / 2;
        Duplicate<T>(dupTensor, val, calCount);
        Adds(dataTensor, dataTensor, static_cast<T>(1), calCount);
        Muls(dataTensor, dataTensor, static_cast<T>(0.5), calCount);
        Muls(dataTensor, dataTensor, static_cast<T>(size - 1), calCount);
    } else {
        T val = static_cast<T>(size) / 2;
        Duplicate<T>(dupTensor, val, calCount);
        Adds(dataTensor, dataTensor, static_cast<T>(1), calCount);
        Muls(dataTensor, dataTensor, static_cast<T>(size), calCount);
        Adds(dataTensor, dataTensor, static_cast<T>(-1), calCount);
        Muls(dataTensor, dataTensor, static_cast<T>(0.5), calCount);
    }
    int32_t newCalCount =
        ((calCount * FLOAT_BYTES - 1 + ALGIN_256_BYTES) / ALGIN_256_BYTES * ALGIN_256_BYTES) / FLOAT_BYTES;

    // If the data is inf/-inf/nan, convert the data to -100.
    CompareScalar(mask1Tensor, dataTensor, static_cast<T>(INT_MAX - 1), CMPMODE::LE, newCalCount);
    PipeBarrier<PIPE_V>();
    Select(dataTensor, mask1Tensor, dataTensor, static_cast<T>(-100.0), SELMODE::VSEL_TENSOR_SCALAR_MODE, newCalCount);
    PipeBarrier<PIPE_V>();
    CompareScalar(mask1Tensor, dataTensor, static_cast<T>(INT_MIN), CMPMODE::GE, newCalCount);
    PipeBarrier<PIPE_V>();
    Select(dataTensor, mask1Tensor, dataTensor, static_cast<T>(-100.0), SELMODE::VSEL_TENSOR_SCALAR_MODE, newCalCount);
    PipeBarrier<PIPE_V>();
    Compare(mask1Tensor, dataTensor, dataTensor, CMPMODE::EQ, newCalCount);
    PipeBarrier<PIPE_V>();
    Select(dataTensor, mask1Tensor, dataTensor, static_cast<T>(-100.0), SELMODE::VSEL_TENSOR_SCALAR_MODE, newCalCount);
    PipeBarrier<PIPE_V>();
}

// Helper function for reflection computation (matches PyTorch's reflect_coordinates)
template <typename T, typename GridSamplerGradTilingData>
__aicore__ inline T GridSampler2DGradBicubic<T, GridSamplerGradTilingData>::ReflectCoordinatesCommon(
    T coord, int32_t size_val, bool align_corners_flag)
{
    T twiceLow = align_corners_flag ? 0 : -1;
    T twiceHigh = align_corners_flag ?
        2 * (static_cast<int64_t>(size_val) - 1) : 2 * static_cast<int64_t>(size_val) - 1;

    if (twiceLow == twiceHigh) return static_cast<T>(0);

    T min = twiceLow / 2;
    T span = static_cast<T>(twiceHigh - twiceLow) / 2;
    // Use conditional to compute absolute value (equivalent to fabs)
    T diff = coord - min;
    T in = (diff >= static_cast<T>(0)) ? diff : -diff;

    // Manual fmod for positive numbers
    T quotient = in / span;
    int32_t quotientInt = static_cast<int32_t>(quotient);
    T extra = in - static_cast<T>(quotientInt) * span;

    if (quotientInt % 2 == 0) {
        return extra + min;
    } else {
        return span - extra + min;
    }
}

template <typename T, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubic<T, GridSamplerGradTilingData>::DupValue()
{
    Duplicate<T>(dupOneTensor, 1, ubFactorElement);
    Duplicate<T>(sumX, 0, alignChannel);
    Duplicate<T>(sumY, 0, alignChannel);
}

template <typename T, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubic<T, GridSamplerGradTilingData>::CopyIn(
    const int64_t offset, const int32_t calCount, const int32_t inputIndex)
{
    LocalTensor<T> dataLocal = dataInQueue[inputIndex].AllocTensor<T>();
    DataCopyParams copyParams = {1, 0, 0, 0};
    DataCopyPadParams padParams = {true, 0, 0, 0};
    int32_t alignCalCount = CeilAlign(calCount, perBlockCount);
    copyParams.blockLen = calCount * sizeof(T);
    padParams.rightPadding = alignCalCount - calCount;
    padParams.paddingValue = GetScalarBitcodeValue((T)0);
    DataCopyPad(dataLocal, inputGm[inputIndex][offset], copyParams, padParams);
    dataInQueue[inputIndex].EnQue(dataLocal);
}

template <typename T, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubic<T, GridSamplerGradTilingData>::CopyOut(
    const int32_t offset, const int32_t calCount)
{
    LocalTensor<T> dstLocal = dataOutQueue[1].DeQue<T>();
    DataCopyParams copyParams{1, 0, 0, 0};
    copyParams.blockLen = calCount * sizeof(T);
    DataCopyPad(inputGm[DGRID_INPUT_INDEX][offset], dstLocal, copyParams);
    dataOutQueue[1].FreeTensor(dstLocal);
}

template <typename T, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubic<T, GridSamplerGradTilingData>::Compute(
    const int32_t computeCount, const int64_t curGridPointIndex)
{
    int64_t gridPointIndex = 0;
    int32_t gradStrideN = channel * outH * outW;
    int32_t gradStrideH = outW;
    int32_t gradStrideW = 1;
    int64_t w = 0;
    int64_t h = 0;
    int64_t n = 0;
    int64_t ncBaseOffset = 0;
    uint32_t mask = 0;
    uint64_t rsvdCnt = 0;
    uint8_t xPattern = 1;
    uint8_t yPattern = 2;
    bool reduceMode = false;
    uint16_t repeatTimes = CeilDiv(computeCount, ELE_NUM_PER_REPEAT);
    uint8_t src0RepeatStride = REPEAT_STRIDE;
    uint8_t src1RepeatStride = REPEAT_STRIDE;

    LocalTensor<T> xTensor = xCoordinateBuf.Get<T>(ubFactorElement + ELE_NUM_PER_REPEAT);
    LocalTensor<T> yTensor = yCoordinateBuf.Get<T>(ubFactorElement + ELE_NUM_PER_REPEAT);
    LocalTensor<T> xGradIn = xGradInBuf.Get<T>(ubFactorElement);
    LocalTensor<T> yGradIn = yGradInBuf.Get<T>(ubFactorElement);
    LocalTensor<T> inputCoordinate = dataInQueue[GRID_INPUT_INDEX].DeQue<T>();
    LocalTensor<T> dstLocal = dataOutQueue[1].AllocTensor<T>();

    DupValue();
    GatherMask(xTensor, inputCoordinate, xPattern, reduceMode, mask,
        {1, repeatTimes, src0RepeatStride, src1RepeatStride}, rsvdCnt);
    GatherMask(yTensor, inputCoordinate, yPattern, reduceMode, mask,
        {1, repeatTimes, src0RepeatStride, src1RepeatStride}, rsvdCnt);

    // gather ix and iy (unnormalize + padding)
    ComputeSourceIndexSetGrad(xTensor, xGradIn, fwidth, computeCount / 2);
    ComputeSourceIndexSetGrad(yTensor, yGradIn, fheight, computeCount / 2);

    int32_t calCount = computeCount / 2;

    // Get cubic coefficient buffers
    LocalTensor<T> coeffTx0 = coeffTx0Buf.Get<T>(ubFactorElement);
    LocalTensor<T> coeffTx1 = coeffTx1Buf.Get<T>(ubFactorElement);
    LocalTensor<T> coeffTx2 = coeffTx2Buf.Get<T>(ubFactorElement);
    LocalTensor<T> coeffTx3 = coeffTx3Buf.Get<T>(ubFactorElement);
    LocalTensor<T> coeffTy0 = coeffTy0Buf.Get<T>(ubFactorElement);
    LocalTensor<T> coeffTy1 = coeffTy1Buf.Get<T>(ubFactorElement);
    LocalTensor<T> coeffTy2 = coeffTy2Buf.Get<T>(ubFactorElement);
    LocalTensor<T> coeffTy3 = coeffTy3Buf.Get<T>(ubFactorElement);

    // Compute floor and fractional parts
    LocalTensor<T> ixNw = ixNwBuf.Get<T>(ubFactorElement);
    LocalTensor<T> iyNw = iyNwBuf.Get<T>(ubFactorElement);
    LocalTensor<int32_t> ixNwInt = ixNwIntBuf.Get<int32_t>(ubFactorElement);
    LocalTensor<int32_t> iyNwInt = iyNwIntBuf.Get<int32_t>(ubFactorElement);

    // ix_nw = floor(ix), iy_nw = floor(iy)
    Cast(ixNwInt, xTensor, RoundMode::CAST_FLOOR, calCount);
    Cast(iyNwInt, yTensor, RoundMode::CAST_FLOOR, calCount);
    Cast(ixNw, ixNwInt, RoundMode::CAST_NONE, calCount);
    Cast(iyNw, iyNwInt, RoundMode::CAST_NONE, calCount);

    // tx = ix - ix_nw, ty = iy - iy_nw
    LocalTensor<T> cubicTx = tmp1Buf.Get<T>(ubFactorElement);
    LocalTensor<T> cubicTy = tmp2Buf.Get<T>(ubFactorElement);
    Sub(cubicTx, xTensor, ixNw, calCount);
    Sub(cubicTy, yTensor, iyNw, calCount);
    PipeBarrier<PIPE_V>();

    // Compute cubic coefficients
    GetCubicUpsampleCoefficients(coeffTx0, coeffTx1, coeffTx2, coeffTx3,
        coeffTy0, coeffTy1, coeffTy2, coeffTy3, cubicTx, cubicTy, calCount);

    // Compute 4 x-coordinate offsets: xnw=ix_nw-1, xne=ix_nw, xsw=ix_nw+1, xse=ix_nw+2
    LocalTensor<T> xnwFp = ixNeBuf.Get<T>(ubFactorElement);
    LocalTensor<T> xneFp = ixNw;
    LocalTensor<T> xswFp = ixSwBuf.Get<T>(ubFactorElement);
    LocalTensor<T> xseFp = ixSeBuf.Get<T>(ubFactorElement);
    LocalTensor<int32_t> xnwInt = ixNeIntBuf.Get<int32_t>(ubFactorElement);
    LocalTensor<int32_t> xneInt = ixNwInt;
    LocalTensor<int32_t> xswInt = ixSwIntBuf.Get<int32_t>(ubFactorElement);
    LocalTensor<int32_t> xseInt = ixSeIntBuf.Get<int32_t>(ubFactorElement);

    Adds(xnwFp, xneFp, static_cast<T>(-1), calCount);
    Adds(xswFp, xneFp, static_cast<T>(1), calCount);
    Adds(xseFp, xneFp, static_cast<T>(2), calCount);
    Adds(xnwInt, xneInt, static_cast<int32_t>(-1), calCount);
    Adds(xswInt, xneInt, static_cast<int32_t>(1), calCount);
    Adds(xseInt, xneInt, static_cast<int32_t>(2), calCount);
    PipeBarrier<PIPE_V>();

    // Compute 4 y-coordinate offsets: ynw=iy_nw-1, yne=iy_nw, ysw=iy_nw+1, yse=iy_nw+2
    LocalTensor<T> ynwFp = iyNeBuf.Get<T>(ubFactorElement);
    LocalTensor<T> yneFp = iyNw;
    LocalTensor<T> yswFp = iySwBuf.Get<T>(ubFactorElement);
    LocalTensor<T> yseFp = iySeBuf.Get<T>(ubFactorElement);
    LocalTensor<int32_t> ynwInt = iyNeIntBuf.Get<int32_t>(ubFactorElement);
    LocalTensor<int32_t> yneInt = iyNwInt;
    LocalTensor<int32_t> yswInt = iySwIntBuf.Get<int32_t>(ubFactorElement);
    LocalTensor<int32_t> yseInt = iySeIntBuf.Get<int32_t>(ubFactorElement);

    Adds(ynwFp, yneFp, static_cast<T>(-1), calCount);
    Adds(yswFp, yneFp, static_cast<T>(1), calCount);
    Adds(yseFp, yneFp, static_cast<T>(2), calCount);
    Adds(ynwInt, yneInt, static_cast<int32_t>(-1), calCount);
    Adds(yswInt, yneInt, static_cast<int32_t>(1), calCount);
    Adds(yseInt, yneInt, static_cast<int32_t>(2), calCount);
    PipeBarrier<PIPE_V>();

    // Compute cubic coefficient derivatives for dgrid calculation
    // d(coeffTx[i])/d(tx) values
    LocalTensor<T> dCoeffTx0 = tmp6Buf.Get<T>(ubFactorElement);
    LocalTensor<T> dCoeffTx1 = tmp7Buf.Get<T>(ubFactorElement);
    LocalTensor<T> dCoeffTx2 = tmp8Buf.Get<T>(ubFactorElement);
    LocalTensor<T> dCoeffTx3 = tmp9Buf.Get<T>(ubFactorElement);

    // cubicTx1 = tx+1, cubicTx2 = 1-tx, cubicTx3 = 2-tx (reuse tmp buffers)
    LocalTensor<T> cubicTx1 = weightBuf.Get<T>(ubFactorElement);
    Adds(cubicTx1, cubicTx, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
    CubicConvolution2Grad(dCoeffTx0, cubicTx1, calCount);
    CubicConvolution1Grad(dCoeffTx1, cubicTx, calCount);

    // cubicTx2 = 1 - tx
    LocalTensor<T> cubicTx2 = weightBuf.Get<T>(ubFactorElement);
    Muls(cubicTx2, cubicTx, static_cast<T>(-1.0), calCount);
    Adds(cubicTx2, cubicTx2, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
    // d(CubicConv1(1-tx))/d(tx) = -CubicConv1Grad(1-tx) (chain rule: d(1-tx)/d(tx) = -1)
    CubicConvolution1Grad(dCoeffTx2, cubicTx2, calCount);
    Muls(dCoeffTx2, dCoeffTx2, static_cast<T>(-1.0), calCount);
    PipeBarrier<PIPE_V>();

    // cubicTx3 = 2 - tx
    LocalTensor<T> cubicTx3 = weightBuf.Get<T>(ubFactorElement);
    Adds(cubicTx3, cubicTx2, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
    // d(CubicConv2(2-tx))/d(tx) = -CubicConv2Grad(2-tx) (chain rule: d(2-tx)/d(tx) = -1)
    CubicConvolution2Grad(dCoeffTx3, cubicTx3, calCount);
    Muls(dCoeffTx3, dCoeffTx3, static_cast<T>(-1.0), calCount);
    PipeBarrier<PIPE_V>();

    // d(coeffTy[j])/d(ty) values
    LocalTensor<T> dCoeffTy0 = computeIndexBuf2.Get<T>(ubFactorElement);
    LocalTensor<T> dCoeffTy1 = computeIndexBuf3.Get<T>(ubFactorElement);
    LocalTensor<T> dCoeffTy2 = computeIndexBuf4.Get<T>(ubFactorElement);
    LocalTensor<T> dCoeffTy3 = computeIndexBuf5.Get<T>(ubFactorElement);

    LocalTensor<T> cubicTy1 = weightBuf.Get<T>(ubFactorElement);
    Adds(cubicTy1, cubicTy, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
    CubicConvolution2Grad(dCoeffTy0, cubicTy1, calCount);
    CubicConvolution1Grad(dCoeffTy1, cubicTy, calCount);

    LocalTensor<T> cubicTy2 = weightBuf.Get<T>(ubFactorElement);
    Muls(cubicTy2, cubicTy, static_cast<T>(-1.0), calCount);
    Adds(cubicTy2, cubicTy2, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
    // d(CubicConv1(1-ty))/d(ty) = -CubicConv1Grad(1-ty) (chain rule: d(1-ty)/d(ty) = -1)
    CubicConvolution1Grad(dCoeffTy2, cubicTy2, calCount);
    Muls(dCoeffTy2, dCoeffTy2, static_cast<T>(-1.0), calCount);
    PipeBarrier<PIPE_V>();

    LocalTensor<T> cubicTy3 = weightBuf.Get<T>(ubFactorElement);
    Adds(cubicTy3, cubicTy2, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
    // d(CubicConv2(2-ty))/d(ty) = -CubicConv2Grad(2-ty) (chain rule: d(2-ty)/d(ty) = -1)
    CubicConvolution2Grad(dCoeffTy3, cubicTy3, calCount);
    Muls(dCoeffTy3, dCoeffTy3, static_cast<T>(-1.0), calCount);
    PipeBarrier<PIPE_V>();

    // Weight buffer for bicubic: weight = coeffTy[j] * coeffTx[i]

    // Index arrays for 4x4 neighborhood
    // We need 16 index arrays for the 4x4 grid, but we reuse buffers
    // For each of the 16 points, we compute: ClipCoordinates -> ComputeIndex -> XGrad -> GridGrad
    // We process point-by-point in the inner loop

    gixLocalTensor = gixBuf.Get<T>(alignChannel);
    giyLocalTensor = giyBuf.Get<T>(alignChannel);

    // Arrays of x/y float and int coordinates for the 4x4 neighborhood
    LocalTensor<T> xFpArr[4] = {xnwFp, xneFp, xswFp, xseFp};
    LocalTensor<int32_t> xIntArr[4] = {xnwInt, xneInt, xswInt, xseInt};
    LocalTensor<T> yFpArr[4] = {ynwFp, yneFp, yswFp, yseFp};
    LocalTensor<int32_t> yIntArr[4] = {ynwInt, yneInt, yswInt, yseInt};
    LocalTensor<T> coeffTxArr[4] = {coeffTx0, coeffTx1, coeffTx2, coeffTx3};
    LocalTensor<T> coeffTyArr[4] = {coeffTy0, coeffTy1, coeffTy2, coeffTy3};
    LocalTensor<T> dCoeffTxArr[4] = {dCoeffTx0, dCoeffTx1, dCoeffTx2, dCoeffTx3};
    LocalTensor<T> dCoeffTyArr[4] = {dCoeffTy0, dCoeffTy1, dCoeffTy2, dCoeffTy3};

    // Index buffers - reuse computeIndexBuf for the 16 points
    LocalTensor<int32_t> idxBuf = computeIndexBuf6.Get<int32_t>(ubFactorElement);
    LocalTensor<int32_t> idx2Buf = computeIndexBuf7.Get<int32_t>(ubFactorElement);

    // Temporary LocalTensor for inner loop (use TBuf for MTE2 direction only)
    LocalTensor<T> inputXLocalTensor = inputXLocalBuf.Get<T>(alignChannel);

    // Allocate xGrad tensor once outside the loop (reuse for all 16 iterations)
    LocalTensor<T> xGradLocalTensor = dataOutQueue[0].AllocTensor<T>();

    for (int32_t i = 0; i < calCount; i++) {
        gridPointIndex = curGridPointIndex + i;
        w = gridPointIndex % outW;
        h = (gridPointIndex / outW) % outH;
        n = gridPointIndex / (outH * outW);
        ncBaseOffset = n * dxStrideN;
        gradGmOffset = n * gradStrideN + (h * gradStrideH + w * gradStrideW) * channel;

        LocalTensor<T> gOutLocalTensor = dataInQueue[0].AllocTensor<T>();
        DataCopyParams copyParams = {1, 0, 0, 0};
        DataCopyPadParams padParams = {true, 0, 0, 0};
        int32_t alignCalCount = CeilAlign(channel, perBlockCount);
        copyParams.blockLen = channel * sizeof(T);
        padParams.rightPadding = alignCalCount - channel;
        padParams.paddingValue = GetScalarBitcodeValue((T)0);
        DataCopyPad(gOutLocalTensor, inputGm[0][gradGmOffset], copyParams, padParams);
        event_t eventIDMte2V = static_cast<event_t>(GetTPipePtr()->FetchEventID(HardEvent::MTE2_V));
        SetFlag<HardEvent::MTE2_V>(eventIDMte2V);
        WaitFlag<HardEvent::MTE2_V>(eventIDMte2V);

        // Iterate over 4x4 neighborhood
        for (int32_t jy = 0; jy < 4; jy++) {
            for (int32_t jx = 0; jx < 4; jx++) {
                // Get the float and int coordinates for this neighborhood point
                T ixFpVal = xFpArr[jx].GetValue(i);
                T iyFpVal = yFpArr[jy].GetValue(i);
                int32_t ixIntVal = xIntArr[jx].GetValue(i);
                int32_t iyIntVal = yIntArr[jy].GetValue(i);
                PipeBarrier<PIPE_V>();

                // Clip coordinates for padding modes
                int32_t ixClipped = ixIntVal;
                int32_t iyClipped = iyIntVal;
                if (padding == 0) { // zeros
                    // Check bounds - if out of bounds, skip for both XGrad and GridGrad
                    if (ixIntVal < 0 || ixIntVal >= width || iyIntVal < 0 || iyIntVal >= height) {
                        continue;
                    }
                } else if (padding == 1) { // border
                    ixClipped = ixIntVal < 0 ? 0 : (ixIntVal >= width ? width - 1 : ixIntVal);
                    iyClipped = iyIntVal < 0 ? 0 : (iyIntVal >= height ? height - 1 : iyIntVal);
                } else { // reflection
                    // Apply reflection for each neighborhood point independently (following PyTorch)
                    // This is critical for correct gradient computation in bicubic interpolation

                    // Reflect x coordinate using float coordinate
                    T ixFpReflected = ReflectCoordinatesCommon(ixFpVal, width, alignCorners == 1);
                    // Clip to valid range
                    ixFpReflected = ixFpReflected < static_cast<T>(0) ? static_cast<T>(0) :
                                   (ixFpReflected >= static_cast<T>(width) ? static_cast<T>(width - 1) : ixFpReflected);
                    ixClipped = static_cast<int32_t>(ixFpReflected);

                    // Reflect y coordinate using float coordinate
                    T iyFpReflected = ReflectCoordinatesCommon(iyFpVal, height, alignCorners == 1);
                    // Clip to valid range
                    iyFpReflected = iyFpReflected < static_cast<T>(0) ? static_cast<T>(0) :
                                   (iyFpReflected >= static_cast<T>(height) ? static_cast<T>(height - 1) : iyFpReflected);
                    iyClipped = static_cast<int32_t>(iyFpReflected);
                }
                PipeBarrier<PIPE_ALL>();

                // Compute source index: srcIdx = (iyClipped * width + ixClipped) * channel
                int32_t srcIdx = (iyClipped * width + ixClipped) * channel;
                int32_t dxIdx = (iyClipped * width + ixClipped) * channel;

                // Compute weight = coeffTy[jy] * coeffTx[jx]
                T coeffTyVal = coeffTyArr[jy].GetValue(i);
                T coeffTxVal = coeffTxArr[jx].GetValue(i);
                T weightScalar = coeffTyVal * coeffTxVal;

                // ComputeBicubicXGrad: AtomicAdd grad_output * weight to dx
                // Reuse xGradLocalTensor allocated outside the loop
                {
                    int64_t offset = ncBaseOffset + dxIdx;
                    event_t eventID1 = static_cast<event_t>(GetTPipePtr()->FetchEventID(HardEvent::S_V));
                    SetFlag<HardEvent::S_V>(eventID1);
                    WaitFlag<HardEvent::S_V>(eventID1);
                    Muls(xGradLocalTensor, gOutLocalTensor, weightScalar, channel);
                    event_t eventID = static_cast<event_t>(GetTPipePtr()->FetchEventID(HardEvent::V_MTE3));
                    SetFlag<HardEvent::V_MTE3>(eventID);
                    WaitFlag<HardEvent::V_MTE3>(eventID);
                    DataCopyParams cp{1, 0, 0, 0};
                    cp.blockLen = channel * sizeof(T);
                    SetAtomicAdd<T>();
                    DataCopyPad(inputGm[DX_INPUT_INDEX][offset], xGradLocalTensor, cp);
                    SetAtomicNone();
                    PipeBarrier<PIPE_MTE3>();
                }
                PipeBarrier<PIPE_ALL>();

                // ComputeBicubicGridGrad: accumulate gix and giy
                // Use TBuf to avoid queue overflow in inner loop
                {
                    T dCoeffTxVal = dCoeffTxArr[jx].GetValue(i);
                    T dCoeffTyVal = dCoeffTyArr[jy].GetValue(i);

                    // d_weight_d_ix = coeffTy[jy] * dCoeffTx[jx]  (derivative w.r.t. ix, not grid_x)
                    // d_weight_d_iy = dCoeffTy[jy] * coeffTx[jx]  (derivative w.r.t. iy, not grid_y)
                    // xGradIn/yGradIn is applied at the final output step (chain rule)
                    T dWeightDIx = coeffTyVal * dCoeffTxVal;
                    T dWeightDIy = dCoeffTyVal * coeffTxVal;

                    int64_t xGmOffsetLocal = n * inputStrideN + srcIdx;
                    DataCopyParams cp2 = {1, 0, 0, 0};
                    DataCopyPadParams pp2 = {true, 0, 0, 0};
                    cp2.blockLen = channel * sizeof(T);
                    pp2.rightPadding = alignCalCount - channel;
                    pp2.paddingValue = GetScalarBitcodeValue((T)0);
                    DataCopyPad(inputXLocalTensor, inputGm[1][xGmOffsetLocal], cp2, pp2);
                    event_t eventID2 = static_cast<event_t>(GetTPipePtr()->FetchEventID(HardEvent::MTE2_V));
                    SetFlag<HardEvent::MTE2_V>(eventID2);
                    WaitFlag<HardEvent::MTE2_V>(eventID2);

                    Muls(gixLocalTensor, inputXLocalTensor, dWeightDIx, channel);
                    PipeBarrier<PIPE_V>();
                    Mul(gixLocalTensor, gOutLocalTensor, gixLocalTensor, channel);
                    PipeBarrier<PIPE_V>();
                    Muls(giyLocalTensor, inputXLocalTensor, dWeightDIy, channel);
                    PipeBarrier<PIPE_V>();
                    Mul(giyLocalTensor, gOutLocalTensor, giyLocalTensor, channel);
                    PipeBarrier<PIPE_V>();
                    Add(sumX, gixLocalTensor, sumX, channel);
                    PipeBarrier<PIPE_V>();
                    Add(sumY, giyLocalTensor, sumY, channel);
                    PipeBarrier<PIPE_V>();
                }
            }
        }

        ReduceSum<T>(sumY, sumY, sumY, channel);
        ReduceSum<T>(sumX, sumX, sumX, channel);
        gix += sumX.GetValue(0);
        giy += sumY.GetValue(0);
        dstLocal.SetValue(2 * i, gix * xGradIn.GetValue(i));
        dstLocal.SetValue(2 * i + 1, giy * yGradIn.GetValue(i));
        Duplicate<T>(sumX, 0, alignChannel);
        Duplicate<T>(sumY, 0, alignChannel);
        gix = static_cast<T>(0);
        giy = static_cast<T>(0);
        dataInQueue[0].FreeTensor(gOutLocalTensor);
    }

    // Free xGrad tensor allocated outside the loop
    dataOutQueue[0].FreeTensor(xGradLocalTensor);

    dataOutQueue[GRID_GRAD_OUTPUT_INDEX].EnQue(dstLocal);
    dataInQueue[GRID_INPUT_INDEX].FreeTensor(inputCoordinate);
}

template <typename T, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubic<T, GridSamplerGradTilingData>::Process()
{
    uint32_t computePNum = 0;
    int64_t gridGmOffset = 0;
    int32_t gridOffset = 0;
    int32_t cycleOffset = 0;
    int64_t curGridPointIndex = 0;
    int32_t copyCountPerTime = 2 * ubFactorElement;
    int32_t actualComputNum = copyCountPerTime;
    if (blockIdx < tailPNum) {
        computePNum = pNumPerCore + 1;
        gridOffset = blockIdx * computePNum;
    } else {
        computePNum = pNumPerCore;
        gridOffset = blockIdx * pNumPerCore + tailPNum;
        // 确定性计算处理N的尾块
        int64_t gridStride = gridH * gridW;
        int64_t tailCorePNum = pNumPerCore + gridStride;
        if (isDeterministic == 1 && blockIdx < tailBNum) {
            computePNum = tailCorePNum;
            gridOffset = blockIdx * computePNum;
        } else if (isDeterministic == 1 && blockIdx >= tailBNum) {
            computePNum = pNumPerCore;
            gridOffset = (blockIdx - tailBNum) * pNumPerCore + tailBNum * tailCorePNum;
        }
    }

    int32_t copyTimes = CeilDiv(computePNum * 2, copyCountPerTime);
    for (int j = 0; j < copyTimes; j++) {
        if (j == copyTimes - 1) {
            actualComputNum = computePNum * 2 - (copyTimes - 1) * copyCountPerTime;
        }
        cycleOffset = j * copyCountPerTime;
        gridGmOffset = cycleOffset + static_cast<int64_t>(gridOffset) * 2;
        curGridPointIndex = gridOffset + static_cast<int64_t>(j) * copyCountPerTime / 2;
        CopyIn(gridGmOffset, actualComputNum, GRID_INPUT_INDEX);
        Compute(actualComputNum, curGridPointIndex);
        CopyOut(gridGmOffset, actualComputNum);
    }
}
#endif // GRID_SAMPLER_2D_GRAD_BICUBIC_H_
