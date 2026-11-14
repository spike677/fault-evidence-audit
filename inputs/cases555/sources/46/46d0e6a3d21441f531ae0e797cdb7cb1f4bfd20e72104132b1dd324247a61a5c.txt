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
 * \file grid_sampler2_d_grad_bicubic_fp16.h
 * \brief GridSampler2D backward with bicubic interpolation for fp16/bf16 data types
 */
#ifndef GRID_SAMPLER_2D_GRAD_BICUBIC_FP16_H_
#define GRID_SAMPLER_2D_GRAD_BICUBIC_FP16_H_

#include "kernel_operator.h"

using namespace AscendC;

constexpr static int32_t INT_MAX_FP16 = 2147483647;
constexpr static int32_t INT_MIN_FP16 = -2147483648;

template <typename T, typename Dtype, typename GridSamplerGradTilingData>
class GridSampler2DGradBicubicFP16 {
public:
    __aicore__ inline GridSampler2DGradBicubicFP16(){};
    __aicore__ inline void Init(
        const GridSamplerGradTilingData& __restrict tilingData, GM_ADDR inputTensors[INPUT_NUM + OUTPUT_NUM + 1]);
    __aicore__ inline void InitBuffer(TPipe* inputPipe);
    __aicore__ inline void InitBicubicLocalTensor();
    __aicore__ inline void CopyIn(const int64_t offset, const int32_t calCount, const int32_t inputIndex);
    __aicore__ inline void CopyOut(const int32_t offset, const int32_t calCount);
    __aicore__ inline void Compute(const int32_t computeCount, const int64_t curGridPointIndex);
    __aicore__ inline void Process();

    // cubic convolution functions
    __aicore__ inline void CubicConvolution1Grad(
        LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount);
    __aicore__ inline void CubicConvolution2Grad(
        LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount);
    __aicore__ inline void CubicConvolution1(
        LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount);
    __aicore__ inline void CubicConvolution2(
        LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount);
    __aicore__ inline void GetCubicUpsampleCoefficients(
        LocalTensor<T> coeffTx0, LocalTensor<T> coeffTx1, LocalTensor<T> coeffTx2, LocalTensor<T> coeffTx3,
        LocalTensor<T> coeffTy0, LocalTensor<T> coeffTy1, LocalTensor<T> coeffTy2, LocalTensor<T> coeffTy3,
        LocalTensor<T> cubicTx, LocalTensor<T> cubicTy, const int32_t calCount);

    // coordinate functions (same as bilinear)
    __aicore__ inline void ComputeSourceIndexSetGrad(
        LocalTensor<T> dataTensor, LocalTensor<T> dupTensor, const T size, const int32_t calCount);
    __aicore__ inline void DupValue();
    __aicore__ inline T ReflectCoordinatesCommonFp16(T coord, int32_t size_val, bool align_corners_flag);
    template <typename T1, typename T2>
    __aicore__ inline T1 CeilAlign(T1 a, T2 b)
    {
        return (a + b - 1) / b * b;
    };
    template <typename T1, typename T2>
    __aicore__ inline T1 CeilDiv(T1 a, T2 b)
    {
        return (a + b - 1) / b;
    };

private:
    TPipe* pipe;
    TQue<QuePosition::VECIN, BUFFER_NUM_ONE> dataInQueue[INPUT_NUM];
    TQue<QuePosition::VECOUT, BUFFER_NUM_ONE> dataOutQueue[OUTPUT_NUM];

    TBuf<TPosition::VECCALC> inputCoordinateBuf;
    TBuf<TPosition::VECCALC> xCoordinateBuf;
    TBuf<TPosition::VECCALC> yCoordinateBuf;
    TBuf<TPosition::VECCALC> xGradInBuf;
    TBuf<TPosition::VECCALC> yGradInBuf;

    // 4x4 neighborhood float coordinates
    TBuf<TPosition::VECCALC> ixNeBuf;
    TBuf<TPosition::VECCALC> iyNeBuf;
    TBuf<TPosition::VECCALC> ixNwBuf;
    TBuf<TPosition::VECCALC> iyNwBuf;
    TBuf<TPosition::VECCALC> ixSeBuf;
    TBuf<TPosition::VECCALC> iySeBuf;
    TBuf<TPosition::VECCALC> ixSwBuf;
    TBuf<TPosition::VECCALC> iySwBuf;

    // integer coordinates
    TBuf<TPosition::VECCALC> ixNeIntBuf;
    TBuf<TPosition::VECCALC> iyNeIntBuf;
    TBuf<TPosition::VECCALC> ixNwIntBuf;
    TBuf<TPosition::VECCALC> iyNwIntBuf;
    TBuf<TPosition::VECCALC> ixSeIntBuf;
    TBuf<TPosition::VECCALC> iySeIntBuf;
    TBuf<TPosition::VECCALC> ixSwIntBuf;
    TBuf<TPosition::VECCALC> iySwIntBuf;

    // cubic coefficients
    TBuf<TPosition::VECCALC> coeffTy0Buf;
    TBuf<TPosition::VECCALC> coeffTy1Buf;
    TBuf<TPosition::VECCALC> coeffTy2Buf;
    TBuf<TPosition::VECCALC> coeffTy3Buf;
    TBuf<TPosition::VECCALC> coeffTx0Buf;
    TBuf<TPosition::VECCALC> coeffTx1Buf;
    TBuf<TPosition::VECCALC> coeffTx2Buf;
    TBuf<TPosition::VECCALC> coeffTx3Buf;

    TBuf<TPosition::VECCALC> weightBuf;

    // temporary buffers
    TBuf<TPosition::VECCALC> tmp1Buf;
    TBuf<TPosition::VECCALC> tmp2Buf;
    TBuf<TPosition::VECCALC> tmp3Buf;
    TBuf<TPosition::VECCALC> tmp4Buf;
    TBuf<TPosition::VECCALC> tmp7Buf;
    TBuf<TPosition::VECCALC> tmp8Buf;
    TBuf<TPosition::VECCALC> tmp9Buf;

    TBuf<TPosition::VECCALC> mask1Buf;
    TBuf<TPosition::VECCALC> mask2Buf;
    TBuf<TPosition::VECCALC> mask3Buf;

    TBuf<TPosition::VECCALC> selBuf1;
    TBuf<TPosition::VECCALC> selBuf2;
    TBuf<TPosition::VECCALC> selBuf3;
    TBuf<TPosition::VECCALC> selBuf4;
    TBuf<TPosition::VECCALC> dupOneBuf;

    TBuf<TPosition::VECCALC> computeIndexBuf1;
    TBuf<TPosition::VECCALC> computeIndexBuf2;
    TBuf<TPosition::VECCALC> computeIndexBuf3;
    TBuf<TPosition::VECCALC> computeIndexBuf4;
    TBuf<TPosition::VECCALC> computeIndexBuf5;
    TBuf<TPosition::VECCALC> computeIndexBuf6;
    TBuf<TPosition::VECCALC> computeIndexBuf7;
    TBuf<TPosition::VECCALC> computeIndexBuf8;
    TBuf<TPosition::VECCALC> computeIndexBuf9;

    TBuf<TPosition::VECCALC> clipLimitBuf;
    TBuf<TPosition::VECCALC> gixBuf;
    TBuf<TPosition::VECCALC> giyBuf;
    TBuf<TPosition::VECCALC> sumXBuf;
    TBuf<TPosition::VECCALC> sumYBuf;

    // fp16-specific buffers
    TBuf<TPosition::VECCALC> dstLocalBuf;
    TBuf<TPosition::VECCALC> inputXLocalTensorBuf;
    TBuf<TPosition::VECCALC> gOutLocalTensorBuf;

    GlobalTensor<Dtype> inputGm[INPUT_NUM + OUTPUT_NUM];
    GlobalTensor<T> inputGmT;

    T fheight = 0;
    T fwidth = 0;
    uint32_t batch = 0;
    uint32_t pNumPerCore = 0;
    uint32_t tailPNum = 0;
    int32_t channel = 0;
    int32_t alignChannel = 0;
    int32_t height = 0;
    int32_t width = 0;
    uint32_t blockNum = 0;
    uint32_t ubFactorElement = 0;
    uint32_t alignCorners = 0;
    uint32_t interpolation = 0;
    uint32_t padding = 0;
    uint32_t outH = 0;
    uint32_t outW = 0;
    uint32_t gridH = 0;
    uint32_t gridW = 0;
    uint32_t perBlockCount = 0;
    uint32_t blockIdx = 0;
    uint32_t dataCount = 0;
    uint32_t baseOffset = 0;
    uint32_t batchOffset = 0;
    uint32_t alignBufferNum = 0;
    uint32_t gradStrideC = 0;
    uint32_t gradStrideH = 0;
    uint32_t gradStrideW = 0;
    uint32_t xStrideC = 0;
    uint32_t dxStrideN = 0;
    uint32_t dxStrideC = 0;
    int32_t dxStrideH = 0;
    uint32_t dxStrideW = 0;
    uint32_t maskSize = 0;
    uint32_t maskNum = 0;
    uint32_t inputStrideN = 0;
    int32_t inputStrideH = 0;
    uint32_t inputStrideW = 0;
    int64_t pointIndex = 0;
    int64_t baseGradGmOffset = 0;
    int64_t baseGmOffset = 0;
    int64_t gradGmOffset = 0;
    int32_t pointOffset = 0;
    int32_t ncOffset = 0;
    int64_t xGmOffset = 0;
    int32_t group = 0;
    uint32_t tailBNum = 0;
    uint32_t isDeterministic = 0;
    T giy = static_cast<T>(0);
    T gix = static_cast<T>(0);
    RoundMode mode;

    LocalTensor<uint16_t> int8ToInt16Mask1;
    LocalTensor<uint16_t> int8ToInt16Mask2;
    LocalTensor<uint8_t> mask1Tensor;
    LocalTensor<uint8_t> mask2Tensor;
    LocalTensor<uint8_t> mask3Tensor;
    LocalTensor<T> selTensor1;
    LocalTensor<T> selTensor2;
    LocalTensor<T> selTensor3;
    LocalTensor<T> selTensor4;
    LocalTensor<T> dupOneTensor;
    LocalTensor<T> tmp1Tensor;
    LocalTensor<T> tmp2Tensor;
    LocalTensor<int32_t> tmpIndex;
    LocalTensor<T> clipLimit;
    LocalTensor<T> gixLocalTensor;
    LocalTensor<T> giyLocalTensor;
    LocalTensor<T> sumX;
    LocalTensor<T> sumY;
};

template <typename T, typename Dtype, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubicFP16<T, Dtype, GridSamplerGradTilingData>::Init(
    const GridSamplerGradTilingData& __restrict tilingData, GM_ADDR inputTensors[INPUT_NUM + OUTPUT_NUM + 1])
{
    pNumPerCore = tilingData.pNumPerCore;
    batch = tilingData.batch;
    tailPNum = tilingData.tailPNum;
    blockNum = tilingData.blockNum;
    channel = tilingData.channel;
    height = tilingData.height;
    width = tilingData.width;
    fheight = static_cast<T>(height);
    fwidth = static_cast<T>(width);
    alignCorners = tilingData.alignCorners;
    padding = tilingData.padding;
    interpolation = tilingData.interpolation;
    group = tilingData.group;
    gridH = tilingData.gridH;
    gridW = tilingData.gridW;
    outW = gridW;
    outH = gridH;
    dataCount = gridH * gridW;
    isDeterministic = tilingData.isDeterministic;
    tailBNum = tilingData.tailBNum;
    ubFactorElement = tilingData.ubFactorElement;
    maskSize = CeilAlign(CeilDiv(ubFactorElement, 8), BLOCK_BYTES);
    maskNum = maskSize / sizeof(uint8_t);
    inputStrideH = width;
    inputStrideW = 1;
    inputStrideN = channel * width * height;
    xStrideC = width * height;
    dxStrideN = channel * width * height;
    dxStrideC = width * height;
    dxStrideH = width;
    dxStrideW = 1;
    gradStrideC = gridH * gridW;
    perBlockCount = BLOCK_BYTES / sizeof(Dtype);
    alignChannel = CeilAlign(channel, perBlockCount);
    blockIdx = GetBlockIdx();
    mode = RoundMode::CAST_NONE;

    inputGm[GRAD_INPUT_INDEX].SetGlobalBuffer(reinterpret_cast<__gm__ Dtype*>(inputTensors[GRAD_INPUT_INDEX]));
    inputGm[X_INPUT_INDEX].SetGlobalBuffer(reinterpret_cast<__gm__ Dtype*>(inputTensors[X_INPUT_INDEX]));
    inputGm[GRID_INPUT_INDEX].SetGlobalBuffer(reinterpret_cast<__gm__ Dtype*>(inputTensors[GRID_INPUT_INDEX]));
    inputGm[DX_INPUT_INDEX].SetGlobalBuffer(reinterpret_cast<__gm__ Dtype*>(inputTensors[DX_INPUT_INDEX]));
    inputGm[DGRID_INPUT_INDEX].SetGlobalBuffer(reinterpret_cast<__gm__ Dtype*>(inputTensors[DGRID_INPUT_INDEX]));
    inputGmT.SetGlobalBuffer(reinterpret_cast<__gm__ T*>(inputTensors[WORKSPACE_INPUT_INDEX]));
}

template <typename T, typename Dtype, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubicFP16<T, Dtype, GridSamplerGradTilingData>::InitBuffer(TPipe* inputPipe)
{
    pipe = inputPipe;
    // bicubic branch for fp16/bf16
    pipe->InitBuffer(dataOutQueue[0], BUFFER_NUM_ONE, alignChannel * sizeof(T));
    pipe->InitBuffer(dataOutQueue[1], BUFFER_NUM_ONE, 2 * ubFactorElement * sizeof(Dtype));
    pipe->InitBuffer(dataInQueue[0], BUFFER_NUM_ONE, alignChannel * sizeof(Dtype));
    pipe->InitBuffer(dataInQueue[1], BUFFER_NUM_ONE, alignChannel * sizeof(Dtype));
    pipe->InitBuffer(dataInQueue[2], BUFFER_NUM_ONE, 2 * ubFactorElement * sizeof(Dtype));

    pipe->InitBuffer(xGradInBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(yGradInBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(xCoordinateBuf, (ubFactorElement + ELE_NUM_PER_REPEAT) * sizeof(T));
    pipe->InitBuffer(yCoordinateBuf, (ubFactorElement + ELE_NUM_PER_REPEAT) * sizeof(T));

    pipe->InitBuffer(ixNeBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iyNeBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(ixNwBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iyNwBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(ixSeBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iySeBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(ixSwBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iySwBuf, ubFactorElement * sizeof(T));

    pipe->InitBuffer(ixNeIntBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iyNeIntBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(ixNwIntBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iyNwIntBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(ixSeIntBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iySeIntBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(ixSwIntBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(iySwIntBuf, ubFactorElement * sizeof(T));

    pipe->InitBuffer(coeffTy0Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(coeffTy1Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(coeffTy2Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(coeffTy3Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(coeffTx0Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(coeffTx1Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(coeffTx2Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(coeffTx3Buf, ubFactorElement * sizeof(T));

    pipe->InitBuffer(weightBuf, ubFactorElement * sizeof(T));

    pipe->InitBuffer(tmp1Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(tmp2Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(tmp3Buf, ubFactorElement * sizeof(int32_t));
    pipe->InitBuffer(tmp4Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(tmp7Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(tmp8Buf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(tmp9Buf, ubFactorElement * sizeof(T));

    pipe->InitBuffer(mask1Buf, maskSize);
    pipe->InitBuffer(mask2Buf, maskSize);
    pipe->InitBuffer(mask3Buf, maskSize);

    pipe->InitBuffer(selBuf1, ubFactorElement * sizeof(T));
    pipe->InitBuffer(selBuf2, ubFactorElement * sizeof(T));
    pipe->InitBuffer(selBuf3, ubFactorElement * sizeof(T));
    pipe->InitBuffer(selBuf4, ubFactorElement * sizeof(T));
    pipe->InitBuffer(dupOneBuf, ubFactorElement * sizeof(T));

    pipe->InitBuffer(computeIndexBuf1, ubFactorElement * sizeof(int32_t));
    pipe->InitBuffer(computeIndexBuf6, ubFactorElement * sizeof(int32_t));
    pipe->InitBuffer(computeIndexBuf7, ubFactorElement * sizeof(int32_t));
    pipe->InitBuffer(computeIndexBuf8, ubFactorElement * sizeof(int32_t));
    pipe->InitBuffer(computeIndexBuf9, ubFactorElement * sizeof(int32_t));
    pipe->InitBuffer(computeIndexBuf2, ubFactorElement * sizeof(T));  // reused as dCoeffTy0
    pipe->InitBuffer(computeIndexBuf3, ubFactorElement * sizeof(T));  // reused as dCoeffTy1
    pipe->InitBuffer(computeIndexBuf4, ubFactorElement * sizeof(T));  // reused as dCoeffTy2
    pipe->InitBuffer(computeIndexBuf5, ubFactorElement * sizeof(T));  // reused as dCoeffTy3

    pipe->InitBuffer(clipLimitBuf, ubFactorElement * sizeof(T));
    pipe->InitBuffer(gixBuf, alignChannel * sizeof(T));
    pipe->InitBuffer(giyBuf, alignChannel * sizeof(T));
    pipe->InitBuffer(sumXBuf, alignChannel * sizeof(T));
    pipe->InitBuffer(sumYBuf, alignChannel * sizeof(T));

    pipe->InitBuffer(inputXLocalTensorBuf, alignChannel * sizeof(T));
    pipe->InitBuffer(inputCoordinateBuf, (ubFactorElement * 2) * sizeof(T));
    pipe->InitBuffer(dstLocalBuf, (2 * ubFactorElement) * sizeof(T));
    pipe->InitBuffer(gOutLocalTensorBuf, alignChannel * sizeof(T));
}

template <typename T, typename Dtype, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubicFP16<T, Dtype, GridSamplerGradTilingData>::InitBicubicLocalTensor()
{
    dupOneTensor = dupOneBuf.Get<T>(ubFactorElement);
    mask1Tensor = mask1Buf.Get<uint8_t>(maskNum);
    mask2Tensor = mask2Buf.Get<uint8_t>(maskNum);
    mask3Tensor = mask3Buf.Get<uint8_t>(maskNum);
    selTensor1 = selBuf1.Get<T>(ubFactorElement);
    selTensor2 = selBuf2.Get<T>(ubFactorElement);
    selTensor3 = selBuf3.Get<T>(ubFactorElement);
    selTensor4 = selBuf4.Get<T>(ubFactorElement);
    tmp1Tensor = tmp1Buf.Get<T>(ubFactorElement);
    tmp2Tensor = tmp2Buf.Get<T>(ubFactorElement);
    sumX = sumXBuf.Get<T>(alignChannel);
    sumY = sumYBuf.Get<T>(alignChannel);
    clipLimit = clipLimitBuf.Get<T>(ubFactorElement);
    tmpIndex = computeIndexBuf1.Get<int32_t>(ubFactorElement);
}

// CubicConvolution1: 1.25*x^3 - 2.25*x^2 + 1.0 (A=-0.75)
template <typename T, typename Dtype, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubicFP16<T, Dtype, GridSamplerGradTilingData>::CubicConvolution1(
    LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount)
{
    Muls(coeff, x, static_cast<T>(1.25), calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, static_cast<T>(-2.25), calCount);
    PipeBarrier<PIPE_V>();
    Mul(coeff, coeff, x, calCount);
    PipeBarrier<PIPE_V>();
    Mul(coeff, coeff, x, calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
}

// CubicConvolution2: -0.75*x^3 + 3.75*x^2 - 6.0*x + 3.0
template <typename T, typename Dtype, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubicFP16<T, Dtype, GridSamplerGradTilingData>::CubicConvolution2(
    LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount)
{
    Muls(coeff, x, static_cast<T>(-0.75), calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, static_cast<T>(3.75), calCount);
    PipeBarrier<PIPE_V>();
    Mul(coeff, coeff, x, calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, static_cast<T>(-6.0), calCount);
    PipeBarrier<PIPE_V>();
    Mul(coeff, coeff, x, calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, static_cast<T>(3.0), calCount);
    PipeBarrier<PIPE_V>();
}

// CubicConvolution1Grad: 3.75*x^2 - 4.5*x (A=-0.75)
template <typename T, typename Dtype, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubicFP16<T, Dtype, GridSamplerGradTilingData>::CubicConvolution1Grad(
    LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount)
{
    Muls(coeff, x, static_cast<T>(3.75), calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, static_cast<T>(-4.5), calCount);
    PipeBarrier<PIPE_V>();
    Mul(coeff, coeff, x, calCount);
    PipeBarrier<PIPE_V>();
}

// CubicConvolution2Grad: -2.25*x^2 + 7.5*x - 6.0
template <typename T, typename Dtype, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubicFP16<T, Dtype, GridSamplerGradTilingData>::CubicConvolution2Grad(
    LocalTensor<T> coeff, LocalTensor<T> x, const int32_t calCount)
{
    Muls(coeff, x, static_cast<T>(-2.25), calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, static_cast<T>(7.5), calCount);
    PipeBarrier<PIPE_V>();
    Mul(coeff, coeff, x, calCount);
    PipeBarrier<PIPE_V>();
    Adds(coeff, coeff, static_cast<T>(-6.0), calCount);
    PipeBarrier<PIPE_V>();
}

// GetCubicUpsampleCoefficients
template <typename T, typename Dtype, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubicFP16<T, Dtype, GridSamplerGradTilingData>::GetCubicUpsampleCoefficients(
    LocalTensor<T> coeffTx0, LocalTensor<T> coeffTx1, LocalTensor<T> coeffTx2, LocalTensor<T> coeffTx3,
    LocalTensor<T> coeffTy0, LocalTensor<T> coeffTy1, LocalTensor<T> coeffTy2, LocalTensor<T> coeffTy3,
    LocalTensor<T> cubicTx, LocalTensor<T> cubicTy, const int32_t calCount)
{
    // Use sel buffers for intermediate values to avoid conflict with cubicTx/cubicTy
    // which are stored in tmp1Buf/tmp2Buf in the Compute function
    LocalTensor<T> cubicTy1 = tmp7Buf.Get<T>(ubFactorElement);
    LocalTensor<T> cubicTy2 = tmp8Buf.Get<T>(ubFactorElement);
    LocalTensor<T> cubicTy3 = tmp9Buf.Get<T>(ubFactorElement);
    LocalTensor<T> cubicTx1 = selBuf1.Get<T>(ubFactorElement);
    LocalTensor<T> cubicTx2 = selBuf2.Get<T>(ubFactorElement);
    LocalTensor<T> cubicTx3 = tmp4Buf.Get<T>(ubFactorElement);

    Adds(cubicTx1, cubicTx, static_cast<T>(1.0), calCount);
    Adds(cubicTy1, cubicTy, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
    Muls(cubicTx2, cubicTx, static_cast<T>(-1.0), calCount);
    Muls(cubicTy2, cubicTy, static_cast<T>(-1.0), calCount);
    PipeBarrier<PIPE_V>();
    Adds(cubicTx2, cubicTx2, static_cast<T>(1.0), calCount);
    Adds(cubicTx3, cubicTx2, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
    Adds(cubicTy2, cubicTy2, static_cast<T>(1.0), calCount);
    Adds(cubicTy3, cubicTy2, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();

    CubicConvolution2(coeffTx0, cubicTx1, calCount);
    CubicConvolution1(coeffTx1, cubicTx, calCount);
    CubicConvolution1(coeffTx2, cubicTx2, calCount);
    CubicConvolution2(coeffTx3, cubicTx3, calCount);
    PipeBarrier<PIPE_V>();
    CubicConvolution2(coeffTy0, cubicTy1, calCount);
    CubicConvolution1(coeffTy1, cubicTy, calCount);
    CubicConvolution1(coeffTy2, cubicTy2, calCount);
    CubicConvolution2(coeffTy3, cubicTy3, calCount);
}

// ComputeSourceIndexSetGrad - same as bilinear
template <typename T, typename Dtype, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubicFP16<T, Dtype, GridSamplerGradTilingData>::ComputeSourceIndexSetGrad(
    LocalTensor<T> dataTensor, LocalTensor<T> dupTensor, const T size, const int32_t calCount)
{
    if (alignCorners == 1) {
        T val = static_cast<T>(size - 1) / 2;
        Duplicate<T>(dupTensor, val, calCount);
        Adds(dataTensor, dataTensor, static_cast<T>(1), calCount);
        PipeBarrier<PIPE_V>();
        Muls(dataTensor, dataTensor, static_cast<T>(0.5), calCount);
        PipeBarrier<PIPE_V>();
        Muls(dataTensor, dataTensor, static_cast<T>(size - 1), calCount);
    } else {
        T val = static_cast<T>(size) / 2;
        Duplicate<T>(dupTensor, val, calCount);
        Adds(dataTensor, dataTensor, static_cast<T>(1), calCount);
        PipeBarrier<PIPE_V>();
        Muls(dataTensor, dataTensor, static_cast<T>(size), calCount);
        PipeBarrier<PIPE_V>();
        Adds(dataTensor, dataTensor, static_cast<T>(-1), calCount);
        PipeBarrier<PIPE_V>();
        Muls(dataTensor, dataTensor, static_cast<T>(0.5), calCount);
    }
    int32_t newCalCount = ((calCount * FLOAT_BYTES - 1 + ALGIN_256_BYTES) / ALGIN_256_BYTES * ALGIN_256_BYTES) / 4;

    CompareScalar(mask1Tensor, dataTensor, static_cast<T>(INT_MAX_FP16 - 1), CMPMODE::LE, newCalCount);
    PipeBarrier<PIPE_V>();
    Select(dataTensor, mask1Tensor, dataTensor, static_cast<T>(-100.0), SELMODE::VSEL_TENSOR_SCALAR_MODE, newCalCount);
    PipeBarrier<PIPE_V>();
    CompareScalar(mask1Tensor, dataTensor, static_cast<T>(INT_MIN_FP16), CMPMODE::GE, newCalCount);
    PipeBarrier<PIPE_V>();
    Select(dataTensor, mask1Tensor, dataTensor, static_cast<T>(-100.0), SELMODE::VSEL_TENSOR_SCALAR_MODE, newCalCount);
    PipeBarrier<PIPE_V>();
    Compare(mask1Tensor, dataTensor, dataTensor, CMPMODE::EQ, newCalCount);
    PipeBarrier<PIPE_V>();
    Select(dataTensor, mask1Tensor, dataTensor, static_cast<T>(-100.0), SELMODE::VSEL_TENSOR_SCALAR_MODE, newCalCount);
    PipeBarrier<PIPE_V>();
}

template <typename T, typename Dtype, typename GridSamplerGradTilingData>
__aicore__ inline T GridSampler2DGradBicubicFP16<T, Dtype, GridSamplerGradTilingData>::ReflectCoordinatesCommonFp16(
    T coord, int32_t size_val, bool align_corners_flag)
{
    float twiceLow = align_corners_flag ? 0 : -1;
    float twiceHigh = align_corners_flag ?
        2 * (static_cast<int64_t>(size_val) - 1) : 2 * static_cast<int64_t>(size_val) - 1;

    if (twiceLow == twiceHigh) return static_cast<T>(0);

    T min = twiceLow / 2;
    T span = static_cast<T>(twiceHigh - twiceLow) / 2;
    // Use conditional to compute absolute value (equivalent to fabs)
    T diff = coord - min;
    T in = (diff >= static_cast<T>(0)) ? diff : -diff;

    // Manual fmod for positive numbers
    float quotient = in / span;
    int32_t quotientInt = static_cast<int32_t>(quotient);
    T extra = in - static_cast<T>(quotientInt) * span;

    if (quotientInt % 2 == 0) {
        return extra + min;
    } else {
        return span - extra + min;
    }
}

template <typename T, typename Dtype, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubicFP16<T, Dtype, GridSamplerGradTilingData>::DupValue()
{
    Duplicate<T>(dupOneTensor, 1, ubFactorElement);
    Duplicate<T>(sumX, 0, alignChannel);
    Duplicate<T>(sumY, 0, alignChannel);
}

template <typename T, typename Dtype, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubicFP16<T, Dtype, GridSamplerGradTilingData>::CopyIn(
    const int64_t offset, const int32_t calCount, const int32_t inputIndex)
{
    LocalTensor<Dtype> dataLocal = dataInQueue[inputIndex].AllocTensor<Dtype>();
    DataCopyParams copyParams = {1, 0, 0, 0};
    DataCopyPadParams padParams = {true, 0, 0, 0};
    int32_t alignCalCount = CeilAlign(calCount, perBlockCount);
    padParams.rightPadding = alignCalCount - calCount;
    padParams.paddingValue = GetScalarBitcodeValue((Dtype)0);
    copyParams.blockLen = calCount * sizeof(Dtype);
    DataCopyPad(dataLocal, inputGm[inputIndex][offset], copyParams, padParams);
    dataInQueue[inputIndex].EnQue(dataLocal);
}

template <typename T, typename Dtype, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubicFP16<T, Dtype, GridSamplerGradTilingData>::CopyOut(
    const int32_t offset, const int32_t calCount)
{
    LocalTensor<Dtype> dstLocal = dataOutQueue[1].DeQue<Dtype>();
    DataCopyParams copyParams{1, 0, 0, 0};
    copyParams.blockLen = calCount * sizeof(Dtype);
    DataCopyPad(inputGm[DGRID_INPUT_INDEX][offset], dstLocal, copyParams);
    dataOutQueue[1].FreeTensor(dstLocal);
}

template <typename T, typename Dtype, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubicFP16<T, Dtype, GridSamplerGradTilingData>::Compute(
    const int32_t computeCount, const int64_t curGridPointIndex)
{
    int64_t gridPointIndex = 0;
    int32_t gradStrideW = 1;
    int64_t w = 0;
    int64_t h = 0;
    int64_t n = 0;
    int64_t ncBaseOffset = 0;
    uint32_t mask = 0;
    uint64_t rsvdCnt = 0;
    uint8_t xPattern = 1;
    uint8_t yPattern = 2;
    int32_t gradStrideN = channel * outH * outW;
    int32_t gradStrideH = outW;
    bool reduceMode = false;
    uint8_t src0RepeatStride = REPEAT_STRIDE;
    uint8_t src1RepeatStride = REPEAT_STRIDE;
    uint16_t repeatTimes = CeilDiv(computeCount, ELE_NUM_PER_REPEAT);

    LocalTensor<T> xGradIn = xGradInBuf.Get<T>(ubFactorElement);
    LocalTensor<T> yGradIn = yGradInBuf.Get<T>(ubFactorElement);
    LocalTensor<T> xTensor = xCoordinateBuf.Get<T>(ubFactorElement + ELE_NUM_PER_REPEAT);
    LocalTensor<T> yTensor = yCoordinateBuf.Get<T>(ubFactorElement + ELE_NUM_PER_REPEAT);
    LocalTensor<T> inputCoordinate = inputCoordinateBuf.Get<T>(ubFactorElement * 2);
    LocalTensor<T> dstLocal = dstLocalBuf.Get<T>(2 * ubFactorElement);
    LocalTensor<Dtype> dstTempLocal = dataOutQueue[1].AllocTensor<Dtype>();
    LocalTensor<Dtype> inputCoordinateTemp = dataInQueue[2].DeQue<Dtype>();

    // Cast grid from fp16/bf16 to fp32
    Cast(inputCoordinate, inputCoordinateTemp, mode, (ubFactorElement * 2));
    DupValue();
    GatherMask(yTensor, inputCoordinate, yPattern, reduceMode, mask,
        {1, repeatTimes, src0RepeatStride, src1RepeatStride}, rsvdCnt);
    GatherMask(xTensor, inputCoordinate, xPattern, reduceMode, mask,
        {1, repeatTimes, src0RepeatStride, src1RepeatStride}, rsvdCnt);

    ComputeSourceIndexSetGrad(xTensor, xGradIn, fwidth, computeCount / 2);
    ComputeSourceIndexSetGrad(yTensor, yGradIn, fheight, computeCount / 2);

    int32_t calCount = computeCount / 2;

    // Get cubic coefficient buffers
    LocalTensor<T> coeffTy0 = coeffTy0Buf.Get<T>(ubFactorElement);
    LocalTensor<T> coeffTy1 = coeffTy1Buf.Get<T>(ubFactorElement);
    LocalTensor<T> coeffTy2 = coeffTy2Buf.Get<T>(ubFactorElement);
    LocalTensor<T> coeffTy3 = coeffTy3Buf.Get<T>(ubFactorElement);
    LocalTensor<T> coeffTx0 = coeffTx0Buf.Get<T>(ubFactorElement);
    LocalTensor<T> coeffTx1 = coeffTx1Buf.Get<T>(ubFactorElement);
    LocalTensor<T> coeffTx2 = coeffTx2Buf.Get<T>(ubFactorElement);
    LocalTensor<T> coeffTx3 = coeffTx3Buf.Get<T>(ubFactorElement);

    // Compute floor and fractional parts
    LocalTensor<int32_t> ixNwInt = ixNwIntBuf.Get<int32_t>(ubFactorElement);
    LocalTensor<int32_t> iyNwInt = iyNwIntBuf.Get<int32_t>(ubFactorElement);
    LocalTensor<T> ixNw = ixNwBuf.Get<T>(ubFactorElement);
    LocalTensor<T> iyNw = iyNwBuf.Get<T>(ubFactorElement);

    Cast(ixNwInt, xTensor, RoundMode::CAST_FLOOR, calCount);
    Cast(iyNwInt, yTensor, RoundMode::CAST_FLOOR, calCount);
    PipeBarrier<PIPE_V>();
    Cast(ixNw, ixNwInt, RoundMode::CAST_NONE, calCount);
    Cast(iyNw, iyNwInt, RoundMode::CAST_NONE, calCount);

    LocalTensor<T> cubicTy = tmp2Buf.Get<T>(ubFactorElement);
    LocalTensor<T> cubicTx = tmp1Buf.Get<T>(ubFactorElement);
    Sub(cubicTx, xTensor, ixNw, calCount);
    PipeBarrier<PIPE_V>();
    Sub(cubicTy, yTensor, iyNw, calCount);
    PipeBarrier<PIPE_V>();

    GetCubicUpsampleCoefficients(coeffTx0, coeffTx1, coeffTx2, coeffTx3,
        coeffTy0, coeffTy1, coeffTy2, coeffTy3, cubicTx, cubicTy, calCount);

    // 4 x-coordinate offsets
    LocalTensor<int32_t> xnwInt = ixNeIntBuf.Get<int32_t>(ubFactorElement);
    LocalTensor<int32_t> xneInt = ixNwInt;
    LocalTensor<int32_t> xswInt = ixSwIntBuf.Get<int32_t>(ubFactorElement);
    LocalTensor<int32_t> xseInt = ixSeIntBuf.Get<int32_t>(ubFactorElement);
    LocalTensor<T> xnwFp = ixNeBuf.Get<T>(ubFactorElement);
    LocalTensor<T> xneFp = ixNw;
    LocalTensor<T> xswFp = ixSwBuf.Get<T>(ubFactorElement);
    LocalTensor<T> xseFp = ixSeBuf.Get<T>(ubFactorElement);

    Adds(xnwFp, xneFp, static_cast<T>(-1), calCount);
    Adds(xswFp, xneFp, static_cast<T>(1), calCount);
    Adds(xseFp, xneFp, static_cast<T>(2), calCount);
    PipeBarrier<PIPE_V>();
    Adds(xnwInt, xneInt, static_cast<int32_t>(-1), calCount);
    Adds(xswInt, xneInt, static_cast<int32_t>(1), calCount);
    Adds(xseInt, xneInt, static_cast<int32_t>(2), calCount);
    PipeBarrier<PIPE_V>();

    // 4 y-coordinate offsets
    LocalTensor<int32_t> ynwInt = iyNeIntBuf.Get<int32_t>(ubFactorElement);
    LocalTensor<int32_t> yneInt = iyNwInt;
    LocalTensor<int32_t> yswInt = iySwIntBuf.Get<int32_t>(ubFactorElement);
    LocalTensor<int32_t> yseInt = iySeIntBuf.Get<int32_t>(ubFactorElement);
    LocalTensor<T> ynwFp = iyNeBuf.Get<T>(ubFactorElement);
    LocalTensor<T> yneFp = iyNw;
    LocalTensor<T> yswFp = iySwBuf.Get<T>(ubFactorElement);
    LocalTensor<T> yseFp = iySeBuf.Get<T>(ubFactorElement);

    Adds(ynwFp, yneFp, static_cast<T>(-1), calCount);
    Adds(yswFp, yneFp, static_cast<T>(1), calCount);
    Adds(yseFp, yneFp, static_cast<T>(2), calCount);
    PipeBarrier<PIPE_V>();
    Adds(ynwInt, yneInt, static_cast<int32_t>(-1), calCount);
    Adds(yswInt, yneInt, static_cast<int32_t>(1), calCount);
    Adds(yseInt, yneInt, static_cast<int32_t>(2), calCount);
    PipeBarrier<PIPE_V>();

    // Compute cubic coefficient derivatives
    LocalTensor<T> dCoeffTx0 = tmp4Buf.Get<T>(ubFactorElement);
    LocalTensor<T> dCoeffTx1 = tmp7Buf.Get<T>(ubFactorElement);
    LocalTensor<T> dCoeffTx2 = tmp8Buf.Get<T>(ubFactorElement);
    LocalTensor<T> dCoeffTx3 = tmp9Buf.Get<T>(ubFactorElement);

    LocalTensor<T> dCoeffTy0 = computeIndexBuf2.Get<T>(ubFactorElement);
    LocalTensor<T> dCoeffTy1 = computeIndexBuf3.Get<T>(ubFactorElement);
    LocalTensor<T> dCoeffTy2 = computeIndexBuf4.Get<T>(ubFactorElement);
    LocalTensor<T> dCoeffTy3 = computeIndexBuf5.Get<T>(ubFactorElement);

    LocalTensor<T> cubicTx1 = weightBuf.Get<T>(ubFactorElement);
    Adds(cubicTx1, cubicTx, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
    CubicConvolution2Grad(dCoeffTx0, cubicTx1, calCount);
    PipeBarrier<PIPE_V>();
    CubicConvolution1Grad(dCoeffTx1, cubicTx, calCount);
    PipeBarrier<PIPE_V>();

    LocalTensor<T> cubicTx2 = weightBuf.Get<T>(ubFactorElement);
    Muls(cubicTx2, cubicTx, static_cast<T>(-1.0), calCount);
    PipeBarrier<PIPE_V>();
    Adds(cubicTx2, cubicTx2, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
    // d(CubicConv1(1-tx))/d(tx) = -CubicConv1Grad(1-tx) (chain rule)
    CubicConvolution1Grad(dCoeffTx2, cubicTx2, calCount);
    PipeBarrier<PIPE_V>();
    Muls(dCoeffTx2, dCoeffTx2, static_cast<T>(-1.0), calCount);
    PipeBarrier<PIPE_V>();

    LocalTensor<T> cubicTx3 = weightBuf.Get<T>(ubFactorElement);
    Adds(cubicTx3, cubicTx2, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
    // d(CubicConv2(2-tx))/d(tx) = -CubicConv2Grad(2-tx) (chain rule)
    CubicConvolution2Grad(dCoeffTx3, cubicTx3, calCount);
    PipeBarrier<PIPE_V>();
    Muls(dCoeffTx3, dCoeffTx3, static_cast<T>(-1.0), calCount);
    PipeBarrier<PIPE_V>();

    LocalTensor<T> cubicTy1 = weightBuf.Get<T>(ubFactorElement);
    Adds(cubicTy1, cubicTy, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
    CubicConvolution2Grad(dCoeffTy0, cubicTy1, calCount);
    PipeBarrier<PIPE_V>();
    CubicConvolution1Grad(dCoeffTy1, cubicTy, calCount);

    LocalTensor<T> cubicTy2 = weightBuf.Get<T>(ubFactorElement);
    Muls(cubicTy2, cubicTy, static_cast<T>(-1.0), calCount);
    PipeBarrier<PIPE_V>();
    Adds(cubicTy2, cubicTy2, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
    // d(CubicConv1(1-ty))/d(ty) = -CubicConv1Grad(1-ty) (chain rule)
    CubicConvolution1Grad(dCoeffTy2, cubicTy2, calCount);
    Muls(dCoeffTy2, dCoeffTy2, static_cast<T>(-1.0), calCount);
    PipeBarrier<PIPE_V>();

    LocalTensor<T> cubicTy3 = weightBuf.Get<T>(ubFactorElement);
    Adds(cubicTy3, cubicTy2, static_cast<T>(1.0), calCount);
    PipeBarrier<PIPE_V>();
    // d(CubicConv2(2-ty))/d(ty) = -CubicConv2Grad(2-ty) (chain rule)
    CubicConvolution2Grad(dCoeffTy3, cubicTy3, calCount);
    PipeBarrier<PIPE_V>();
    Muls(dCoeffTy3, dCoeffTy3, static_cast<T>(-1.0), calCount);
    PipeBarrier<PIPE_V>();

    LocalTensor<T> xFpArr[4] = {xnwFp, xneFp, xswFp, xseFp};
    LocalTensor<T> yFpArr[4] = {ynwFp, yneFp, yswFp, yseFp};
    LocalTensor<int32_t> xIntArr[4] = {xnwInt, xneInt, xswInt, xseInt};
    LocalTensor<int32_t> yIntArr[4] = {ynwInt, yneInt, yswInt, yseInt};
    LocalTensor<T> coeffTxArr[4] = {coeffTx0, coeffTx1, coeffTx2, coeffTx3};
    LocalTensor<T> coeffTyArr[4] = {coeffTy0, coeffTy1, coeffTy2, coeffTy3};
    LocalTensor<T> dCoeffTxArr[4] = {dCoeffTx0, dCoeffTx1, dCoeffTx2, dCoeffTx3};
    LocalTensor<T> dCoeffTyArr[4] = {dCoeffTy0, dCoeffTy1, dCoeffTy2, dCoeffTy3};

    giyLocalTensor = giyBuf.Get<T>(alignChannel);
    gixLocalTensor = gixBuf.Get<T>(alignChannel);

    // Temporary LocalTensor for inner loop (use TBuf for MTE2 direction only)
    LocalTensor<T> inputXLocalTensor = inputXLocalTensorBuf.Get<T>(alignChannel);

    // Allocate xGrad tensor once outside the loop (reuse for all 16 iterations)
    LocalTensor<T> xGradLocalTensor = dataOutQueue[0].AllocTensor<T>();

    for (int32_t i = 0; i < calCount; i++) {
        gridPointIndex = curGridPointIndex + i;
        w = gridPointIndex % outW;
        h = (gridPointIndex / outW) % outH;
        n = gridPointIndex / (outH * outW);
        ncBaseOffset = n * dxStrideN;
        gradGmOffset = n * gradStrideN + (h * gradStrideH + w * gradStrideW) * channel;

        // Read grad_output and cast to fp32
        LocalTensor<Dtype> gOutLocalTempTensor = dataInQueue[0].AllocTensor<Dtype>();
        LocalTensor<T> gOutLocalTensor = gOutLocalTensorBuf.Get<T>(alignChannel);
        DataCopyParams copyParams = {1, 0, 0, 0};
        DataCopyPadParams padParams = {true, 0, 0, 0};
        int32_t alignCalCount = CeilAlign(channel, perBlockCount);
        copyParams.blockLen = channel * sizeof(Dtype);
        padParams.rightPadding = alignCalCount - channel;
        padParams.paddingValue = GetScalarBitcodeValue((Dtype)0);
        DataCopyPad(gOutLocalTempTensor, inputGm[0][gradGmOffset], copyParams, padParams);
        event_t eventID1 = static_cast<event_t>(GetTPipePtr()->FetchEventID(HardEvent::MTE2_V));
        SetFlag<HardEvent::MTE2_V>(eventID1);
        WaitFlag<HardEvent::MTE2_V>(eventID1);
        Cast(gOutLocalTensor, gOutLocalTempTensor, mode, alignChannel);

        for (int32_t jy = 0; jy < 4; jy++) {
            for (int32_t jx = 0; jx < 4; jx++) {
                int32_t ixIntVal = xIntArr[jx].GetValue(i);
                int32_t iyIntVal = yIntArr[jy].GetValue(i);
                T ixFpVal = xFpArr[jx].GetValue(i);
                T iyFpVal = yFpArr[jy].GetValue(i);

                int32_t iyClipped = iyIntVal;
                int32_t ixClipped = ixIntVal;
                if (padding == 0) {
                    if (ixIntVal < 0 || ixIntVal >= width || iyIntVal < 0 || iyIntVal >= height) {
                        continue;
                    }
                } else if (padding == 1) {
                    iyClipped = iyIntVal < 0 ? 0 : (iyIntVal >= height ? height - 1 : iyIntVal);
                    ixClipped = ixIntVal < 0 ? 0 : (ixIntVal >= width ? width - 1 : ixIntVal);
                } else { // reflection
                    // Apply reflection for each neighborhood point independently (following PyTorch)
                    // This is critical for correct gradient computation in bicubic interpolation

                    // Reflect x coordinate using float coordinate
                    T ixFpReflected = ReflectCoordinatesCommonFp16(ixFpVal, width, alignCorners == 1);
                    // Clip to valid range
                    ixFpReflected = ixFpReflected < static_cast<T>(0) ? static_cast<T>(0) :
                                   (ixFpReflected >= static_cast<T>(width) ? static_cast<T>(width - 1) : ixFpReflected);
                    ixClipped = static_cast<int32_t>(ixFpReflected);

                    // Reflect y coordinate using float coordinate
                    T iyFpReflected = ReflectCoordinatesCommonFp16(iyFpVal, height, alignCorners == 1);
                    // Clip to valid range
                    iyFpReflected = iyFpReflected < static_cast<T>(0) ? static_cast<T>(0) :
                                   (iyFpReflected >= static_cast<T>(height) ? static_cast<T>(height - 1) : iyFpReflected);
                    iyClipped = static_cast<int32_t>(iyFpReflected);
                }
                PipeBarrier<PIPE_ALL>();

                int32_t dxIdx = (iyClipped * width + ixClipped) * channel;
                int32_t srcIdx = (iyClipped * width + ixClipped) * channel;

                T coeffTxVal = coeffTxArr[jx].GetValue(i);
                T coeffTyVal = coeffTyArr[jy].GetValue(i);
                T weightScalarFp16 = coeffTyVal * coeffTxVal;

                // ComputeBicubicXGrad: AtomicAdd grad_output * weight to dx
                // Reuse xGradLocalTensor allocated outside the loop
                {
                    int64_t offset = ncBaseOffset + dxIdx;
                    event_t eventID1 = static_cast<event_t>(GetTPipePtr()->FetchEventID(HardEvent::S_V));
                    SetFlag<HardEvent::S_V>(eventID1);
                    WaitFlag<HardEvent::S_V>(eventID1);
                    Muls(xGradLocalTensor, gOutLocalTensor, weightScalarFp16, channel);
                    event_t eventID = static_cast<event_t>(GetTPipePtr()->FetchEventID(HardEvent::V_MTE3));
                    SetFlag<HardEvent::V_MTE3>(eventID);
                    WaitFlag<HardEvent::V_MTE3>(eventID);
                    DataCopyParams cp{1, 0, 0, 0};
                    cp.blockLen = channel * sizeof(T);
                    SetAtomicAdd<T>();
                    DataCopyPad(inputGmT[offset], xGradLocalTensor, cp);
                    SetAtomicNone();
                    PipeBarrier<PIPE_MTE3>();
                }
                PipeBarrier<PIPE_ALL>();

                // ComputeBicubicGridGrad: accumulate gix and giy
                // Use TBuf to avoid queue overflow in inner loop
                {
                    T dCoeffTyVal = dCoeffTyArr[jy].GetValue(i);
                    T dCoeffTxVal = dCoeffTxArr[jx].GetValue(i);

                    // d_weight_d_ix = coeffTy[jy] * dCoeffTx[jx]  (derivative w.r.t. ix, not grid_x)
                    // d_weight_d_iy = dCoeffTy[jy] * coeffTx[jx]  (derivative w.r.t. iy, not grid_y)
                    // xGradIn/yGradIn is applied at the final output step (chain rule)
                    T dWeightDIyFp16 = dCoeffTyVal * coeffTxVal;
                    T dWeightDIxFp16 = coeffTyVal * dCoeffTxVal;

                    int64_t xGmOffsetLocal = n * inputStrideN + srcIdx;
                    DataCopyParams cp2 = {1, 0, 0, 0};
                    DataCopyPadParams pp2 = {true, 0, 0, 0};
                    cp2.blockLen = channel * sizeof(Dtype);
                    pp2.rightPadding = alignCalCount - channel;
                    pp2.paddingValue = GetScalarBitcodeValue((Dtype)0);
                    LocalTensor<Dtype> inputXLocalTempTensor = dataInQueue[1].AllocTensor<Dtype>();
                    DataCopyPad(inputXLocalTempTensor, inputGm[1][xGmOffsetLocal], cp2, pp2);
                    event_t eventID2 = static_cast<event_t>(GetTPipePtr()->FetchEventID(HardEvent::MTE2_V));
                    SetFlag<HardEvent::MTE2_V>(eventID2);
                    WaitFlag<HardEvent::MTE2_V>(eventID2);
                    Cast(inputXLocalTensor, inputXLocalTempTensor, mode, alignChannel);
                    dataInQueue[1].FreeTensor(inputXLocalTempTensor);

                    Muls(gixLocalTensor, inputXLocalTensor, dWeightDIxFp16, channel);
                    PipeBarrier<PIPE_V>();
                    Mul(gixLocalTensor, gOutLocalTensor, gixLocalTensor, channel);
                    PipeBarrier<PIPE_V>();
                    Muls(giyLocalTensor, inputXLocalTensor, dWeightDIyFp16, channel);
                    PipeBarrier<PIPE_V>();
                    Mul(giyLocalTensor, gOutLocalTensor, giyLocalTensor, channel);
                    PipeBarrier<PIPE_V>();
                    Add(sumY, giyLocalTensor, sumY, channel);
                    PipeBarrier<PIPE_V>();
                    Add(sumX, gixLocalTensor, sumX, channel);
                    PipeBarrier<PIPE_V>();
                }
            }
        }

        ReduceSum<T>(sumX, sumX, sumX, channel);
        ReduceSum<T>(sumY, sumY, sumY, channel);
        giy += sumY.GetValue(0);
        gix += sumX.GetValue(0);
        dstLocal.SetValue(2 * i, gix * xGradIn.GetValue(i));
        dstLocal.SetValue(2 * i + 1, giy * yGradIn.GetValue(i));
        Duplicate<T>(sumY, 0, alignChannel);
        Duplicate<T>(sumX, 0, alignChannel);
        giy = static_cast<T>(0);
        gix = static_cast<T>(0);
        dataInQueue[0].FreeTensor(gOutLocalTempTensor);
    }

    // Free xGrad tensor allocated outside the loop
    dataOutQueue[0].FreeTensor(xGradLocalTensor);

    Cast(dstTempLocal, dstLocal, RoundMode::CAST_RINT, 2 * ubFactorElement);
    dataOutQueue[1].EnQue(dstTempLocal);
    dataInQueue[2].FreeTensor(inputCoordinateTemp);
}

template <typename T, typename Dtype, typename GridSamplerGradTilingData>
__aicore__ inline void GridSampler2DGradBicubicFP16<T, Dtype, GridSamplerGradTilingData>::Process()
{
    uint32_t computePNum = 0;
    int64_t gridGmOffset = 0;
    int32_t gridOffset = 0;
    int32_t cycleOffset = 0;
    int64_t curGridPointIndex = 0;
    if (blockIdx < tailPNum) {
        computePNum = pNumPerCore + 1;
        gridOffset = blockIdx * computePNum;
    } else {
        computePNum = pNumPerCore;
        gridOffset = blockIdx * pNumPerCore + tailPNum;
        // 确定性计算处理N的尾块
        int64_t gridStride = gridH * gridW;
        int64_t tailCorePNumFp16 = pNumPerCore + gridStride;
        if (isDeterministic == 1 && blockIdx < tailBNum) {
            computePNum = tailCorePNumFp16;
            gridOffset = blockIdx * computePNum;
        } else if (isDeterministic == 1 && blockIdx >= tailBNum) {
            computePNum = pNumPerCore;
            gridOffset = (blockIdx - tailBNum) * pNumPerCore + tailBNum * tailCorePNumFp16;
        }
    }

    int32_t copyCountPerTime = 2 * ubFactorElement;
    int32_t actualComputNum = copyCountPerTime;
    int32_t copyTimes = CeilDiv(computePNum * 2, copyCountPerTime);
    for (int j = 0; j < copyTimes; j++) {
        if (j == copyTimes - 1) {
            actualComputNum = computePNum * 2 - (copyTimes - 1) * copyCountPerTime;
        }
        cycleOffset = j * copyCountPerTime;
        gridGmOffset = cycleOffset + static_cast<int64_t>(gridOffset) * 2;
        curGridPointIndex = gridOffset + static_cast<int64_t>(j) * copyCountPerTime / 2;
        CopyIn(gridGmOffset, actualComputNum, 2);
        Compute(actualComputNum, curGridPointIndex);
        CopyOut(gridGmOffset, actualComputNum);
    }
}
#endif // GRID_SAMPLER_2D_GRAD_BICUBIC_FP16_H_
