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
 * \file grid_sampler3_d_grad_simt_base.h
 * \brief
 */
#ifndef GRID_SAMPLER3D_GRAD_SIMT_BASE_H_
#define GRID_SAMPLER3D_GRAD_SIMT_BASE_H_

#include "simt_api/asc_simt.h"
#include "simt_api/math_functions.h"
#include "kernel_operator.h"

using namespace AscendC;

namespace GridSampler3DGradSimtBase {
    constexpr int32_t GRAD_INPUT_INDEX_SIMT = 0;
    constexpr int32_t X_INPUT_INDEX_SIMT = 1;
    constexpr int32_t GRID_INPUT_INDEX_SIMT = 2;
    constexpr int32_t DX_INPUT_INDEX_SIMT = 3;
    constexpr int32_t DGRID_INPUT_INDEX_SIMT = 4;
    constexpr int32_t WORKSPACE_INDEX = 5;
    constexpr int32_t TMP_OUT_INDEX = 0;
    constexpr int32_t GM_PARAMS_SIZE = 6;
    constexpr int32_t DX_OUTPUT_INDEX = 0;
    constexpr int32_t DGRID_OUTPUT_INDEX = 1;
    constexpr int32_t BILINEAR = 0;
    constexpr int32_t NEAREST = 1;
    constexpr int32_t BICUBIC = 2;
    constexpr int32_t ZEROS = 0;
    constexpr int32_t BORDER = 1;
    constexpr int32_t REFLECTION = 2;
    constexpr int32_t CONST_TWO = 2;
    constexpr int32_t INDEX_ZERO = 0;
    constexpr int32_t INDEX_ONE = 1;
    constexpr int32_t INDEX_TWO = 2;
    constexpr int32_t INDEX_THREE = 3;
    constexpr int32_t COEFFS_LENS = 4;
    constexpr uint32_t VF_MAX_THREAD_NUM = 256;
    constexpr float DEFAULT_FAULT_VALUE = -100.0f;

__simt_callee__ __aicore__ __attribute__((always_inline)) inline float UnnormalizeSetGrad(
    float coord, uint32_t size, uint32_t alignCorners, float* gradInValue)
{
    if (alignCorners == 1) {
        // unnormalize coord from [-1, 1] to [0, size - 1]
        coord = (coord + 1) / CONST_TWO * (size - 1);
        *gradInValue = static_cast<float>(size - 1) / CONST_TWO;
    } else {
        // unnormalize coord from [-1, 1] to [-0.5, size - 0.5]
        coord = ((coord + 1) * size - 1) / CONST_TWO;
        *gradInValue = static_cast<float>(size) / CONST_TWO;
    }
    return coord;
}

__simt_callee__ __aicore__ __attribute__((always_inline)) inline float ClipCoorDinatesSetGrad(
    float coord, uint32_t clip_limit, float* gradClipValue)
{
    if (coord <= static_cast<float>(0)) {
        *gradClipValue = static_cast<float>(0);
        return static_cast<float>(0);
    } else {
        float max = static_cast<float>(clip_limit - 1);
        if (coord >= max) {
            *gradClipValue = static_cast<float>(0);
            return max;
        } else {
            *gradClipValue = static_cast<float>(1);
            return coord;
        }
    }
}

__simt_callee__ __aicore__ __attribute__((always_inline)) inline float ReflectCoordinatesSetGrad(
    float coord, int twiceLow, uint32_t twiceHigh, float* gradReflValue)
{
    if (twiceLow == twiceHigh) {
        *gradReflValue = static_cast<float>(0);
        return static_cast<float>(0);
    }
    float gradInMult = 0;
    float min = static_cast<float>(twiceLow) / 2;
    float span = static_cast<float>(twiceHigh - twiceLow) / 2;
    coord = coord - min;
    if (coord < static_cast<float>(0)) {
        gradInMult = static_cast<float>(-1);
        coord = -coord;
    } else {
        gradInMult = static_cast<float>(1);
    }
    // `fmod` returns same sign as `in`, which is positive after the `if` above.
    float extra = fmodf(coord, span);
    int32_t flips = static_cast<int32_t>(floorf(coord / span));
    if (flips % 2 == 0) {
        *gradReflValue = gradInMult;
        return extra + min;
    } else {
        *gradReflValue = -gradInMult;
        return span - extra + min;
    }
}

__simt_callee__ __aicore__ __attribute__((always_inline)) inline float SafeDowngradeToIntRange(float coord)
{
    if (!isfinite(coord)) {
        return DEFAULT_FAULT_VALUE;
    }
    return coord;
}

__simt_callee__ __aicore__ __attribute__((always_inline)) inline int32_t GetFloorValue(float x)
{
    float negativeValue = static_cast<float>(0.0);
    float floorFactor = static_cast<float>(-1);
    return (x >= negativeValue ? static_cast<int32_t>(x) : static_cast<int32_t>(floorFactor + x));
}

template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void GetGradOutPointValueAndDxIndex(
    __gm__ T* gradOutGmAddr, int32_t inputXDepth, int32_t inputXHeight, int32_t inputXWidth, uint32_t gridD,
    uint32_t gridH, uint32_t gridW, uint32_t batchNum, uint32_t depthCol, uint32_t heightCol, uint32_t widthCol,
    uint32_t channelIndex, uint32_t gridoffsetBaseAddr, uint32_t xD, uint32_t xH, uint32_t xW, uint32_t channel,
    uint32_t newInputIndex, float* gradOutValue, uint32_t* dxIndex)
{
    if (inputXDepth >= 0 && inputXHeight >= 0 && inputXWidth >= 0 && inputXDepth < xD && inputXHeight < xH &&
        inputXWidth < xW) {
        uint32_t gradOutValueIndex = batchNum * channel * gridD * gridH * gridW + channelIndex * gridD * gridH * gridW +
                                     depthCol * gridH * gridW + heightCol * gridW + widthCol;
        *gradOutValue = static_cast<float>(gradOutGmAddr[gradOutValueIndex]);
        *dxIndex = static_cast<uint32_t>(
            newInputIndex + channelIndex * xD * xH * xW + inputXDepth * xH * xW + inputXHeight * xW + inputXWidth);
    }
}

template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void GetGradOutValueAndDxIndex(
    __gm__ T* gradOutGmAddr, int32_t inputXHeight, int32_t inputXWidth, uint32_t gridH, uint32_t gridW,
    uint32_t batchNum, uint32_t heightCol, uint32_t widthCol, uint32_t channelIndex,
    uint32_t newInputIndex, uint32_t xH, uint32_t xW, uint32_t channel, float* gradOutValue, uint32_t* dxIndex)
{
    if (inputXHeight >= 0 && inputXWidth >= 0 && inputXHeight < xH && inputXWidth < xW) {
        uint32_t gradOutValueIndex = batchNum * channel * gridH * gridW + channelIndex * gridH * gridW +
                                    heightCol * gridW + widthCol;
        *gradOutValue = static_cast<float>(gradOutGmAddr[gradOutValueIndex]);
        *dxIndex = static_cast<uint32_t>(newInputIndex + channelIndex * xH * xW + inputXHeight * xW + inputXWidth);
    }
}

__simt_callee__ __aicore__ __attribute__((always_inline)) inline float ComputeSourceIndexSetGrad(
    float coord, uint32_t size, uint32_t padding, uint32_t alignCorners, float* gradInValue)
{
    float gradClipValue = 0;
    float gradReflValue = 0;
    coord = UnnormalizeSetGrad(coord, size, alignCorners, gradInValue);

    if (padding == BORDER) {
        // clip coordinates to image borders
        coord = ClipCoorDinatesSetGrad(coord, size, &gradClipValue);
        *gradInValue = (*gradInValue) * gradClipValue;
    } else if (padding == REFLECTION) {
        // reflect coordinates by image borders
        if (alignCorners) {
            coord = ReflectCoordinatesSetGrad(coord, 0, 2 * (size - 1), &gradReflValue);
        } else {
            coord = ReflectCoordinatesSetGrad(coord, -1, 2 * size - 1, &gradReflValue);
        }
        // clip coordinates to image borders
        coord = ClipCoorDinatesSetGrad(coord, size, &gradClipValue);
        *gradInValue = (*gradInValue) * gradReflValue * gradClipValue;
    }
    coord = SafeDowngradeToIntRange(coord);
    return coord;
}

// Bicubic interpolation helper functions for SIMT kernel
// Cubic convolution for |x| <= 1: f(x) = (A+2)*|x|^3 - (A+3)*|x|^2 + 1, A=-0.75
__simt_callee__ __aicore__ __attribute__((always_inline)) inline float CubicConvolution1(float x)
{
    float A = -0.75f;
    return ((A + 2.0f) * x - (A + 3.0f)) * x * x + 1.0f;
}

// Cubic convolution for 1 < |x| < 2: f(x) = A*|x|^3 - 5A*|x|^2 + 8A*|x| - 4A, A=-0.75
__simt_callee__ __aicore__ __attribute__((always_inline)) inline float CubicConvolution2(float x)
{
    float A = -0.75f;
    return ((A * x - 5.0f * A) * x + 8.0f * A) * x - 4.0f * A;
}

// Compute 4 cubic interpolation coefficients for forward pass (used for grad_input)
// coeffs[0] = CubicConv2(t+1), coeffs[1] = CubicConv1(t), coeffs[2] = CubicConv1(1-t), coeffs[3] = CubicConv2(2-t)
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void GetCubicUpsampleCoefficients(
    float coeffs[4], float t, size_t coeffsLen)
{
    if (coeffsLen == COEFFS_LENS) {
        coeffs[INDEX_ZERO] = CubicConvolution2(t + 1.0f);
        coeffs[INDEX_ONE] = CubicConvolution1(t);
        coeffs[INDEX_TWO] = CubicConvolution1(1.0f - t);
        coeffs[INDEX_THREE] = CubicConvolution2(2.0f - t);
    }
}

// Compute derivatives of cubic coefficients w.r.t. t (used for grad_grid)
// d(CubicConv1(x))/dx = 3*(A+2)*x^2 - 2*(A+3)*x
// d(CubicConv2(x))/dx = 3*A*x^2 - 10*A*x + 8*A
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void GetCubicCoefficientsGrad(
    float coeffs[4], float t, size_t coeffsLen)
{
    float A = -0.75f;
    float x;
    if (coeffsLen == COEFFS_LENS) {
        // d(CubicConv2(t+1))/dt = CubicConv2Grad(t+1)
        x = t + 1.0f;
        coeffs[INDEX_ZERO] = (3.0f * A * x - 10.0f * A) * x + 8.0f * A;

        // d(CubicConv1(t))/dt = CubicConv1Grad(t)
        x = t;
        coeffs[INDEX_ONE] = (3.0f * (A + 2.0f) * x - 2.0f * (A + 3.0f)) * x;

        // d(CubicConv1(1-t))/dt = -CubicConv1Grad(1-t) (chain rule: d(1-t)/dt = -1)
        x = 1.0f - t;
        coeffs[INDEX_TWO] = -((3.0f * (A + 2.0f) * x - 2.0f * (A + 3.0f)) * x);

        // d(CubicConv2(2-t))/dt = -CubicConv2Grad(2-t) (chain rule: d(2-t)/dt = -1)
        x = 2.0f - t;
        coeffs[INDEX_THREE] = -((3.0f * A * x - 10.0f * A) * x + 8.0f * A);
    }
}

// Apply padding (clip/reflect) to a single neighbor coordinate and return the clipped integer index
// Returns -1 if the point is out of bounds (for zeros padding)
__simt_callee__ __aicore__ __attribute__((always_inline)) inline int32_t ComputeBicubicNeighborIndex(
    float coord, uint32_t size, uint32_t padding, uint32_t alignCorners)
{
    if (padding == ZEROS) { // zeros
        int32_t idx = GetFloorValue(coord);
        if (idx < 0 || idx >= static_cast<int32_t>(size)) {
            return -1; // out of bounds
        }
        return idx;
    } else if (padding == BORDER) { // border
        float clipped = coord;
        if (clipped < 0.0f) clipped = 0.0f;
        float maxVal = static_cast<float>(size - 1);
        if (clipped > maxVal) clipped = maxVal;
        return static_cast<int32_t>(clipped);
    } else { // reflection
        float gradReflValue = 0;
        float gradClipValue = 0;
        if (alignCorners) {
            coord = ReflectCoordinatesSetGrad(coord, 0, CONST_TWO * (size - 1), &gradReflValue);
        } else {
            coord = ReflectCoordinatesSetGrad(coord, -1, CONST_TWO * size - 1, &gradReflValue);
        }
        coord = ClipCoorDinatesSetGrad(coord, size, &gradClipValue);
        return static_cast<int32_t>(coord);
    }
}

// Get value from input with boundary handling (for grad_grid computation)
template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline float GetValueBounded(
    __gm__ T* data, float x, float y, uint32_t W, uint32_t H,
    uint32_t sW, uint32_t sH, uint32_t padding, uint32_t alignCorners)
{
    if (padding == ZEROS) { // zeros
        if (x < 0 || x >= static_cast<float>(W) || y < 0 || y >= static_cast<float>(H)) {
            return 0.0f;
        }
    } else if (padding == BORDER) { // border
        x = x < 0 ? 0 : (x >= static_cast<float>(W) ? static_cast<float>(W) - 1 : x);
        y = y < 0 ? 0 : (y >= static_cast<float>(H) ? static_cast<float>(H) - 1 : y);
    } else { // reflection
        float gradReflX = 0, gradClipX = 0, gradReflY = 0, gradClipY = 0;
        if (alignCorners) {
            x = ReflectCoordinatesSetGrad(x, 0, 2 * (W - 1), &gradReflX);
            y = ReflectCoordinatesSetGrad(y, 0, 2 * (H - 1), &gradReflY);
        } else {
            x = ReflectCoordinatesSetGrad(x, -1, 2 * W - 1, &gradReflX);
            y = ReflectCoordinatesSetGrad(y, -1, 2 * H - 1, &gradReflY);
        }
        x = ClipCoorDinatesSetGrad(x, W, &gradClipX);
        y = ClipCoorDinatesSetGrad(y, H, &gradClipY);
    }

    int32_t ix = static_cast<int32_t>(SafeDowngradeToIntRange(x));
    int32_t iy = static_cast<int32_t>(SafeDowngradeToIntRange(y));
    if (ix >= 0 && ix < static_cast<int32_t>(W) && iy >= 0 && iy < static_cast<int32_t>(H)) {
        return static_cast<float>(data[iy * sH + ix * sW]);
    }
    return 0.0f;
}

// Add value to grad_input with boundary handling (for grad_input computation)
template <typename T>
__simt_callee__ __aicore__ __attribute__((always_inline)) inline void AddValueBounded(
    __gm__ T* data, float x, float y, uint32_t W, uint32_t H,
    uint32_t sW, uint32_t sH, float delta, uint32_t padding, uint32_t alignCorners)
{
    if (padding == ZEROS) { // zeros
        if (x < 0 || x >= static_cast<float>(W) || y < 0 || y >= static_cast<float>(H)) {
            return;
        }
    } else if (padding == BORDER) { // border
        y = y < 0 ? 0 : (y >= static_cast<float>(H) ? static_cast<float>(H) - 1 : y);
        x = x < 0 ? 0 : (x >= static_cast<float>(W) ? static_cast<float>(W) - 1 : x);
    } else { // reflection
        float gradReflX = 0, gradClipX = 0, gradReflY = 0, gradClipY = 0;
        if (alignCorners) {
            y = ReflectCoordinatesSetGrad(y, 0, 2 * (H - 1), &gradReflY);
            x = ReflectCoordinatesSetGrad(x, 0, 2 * (W - 1), &gradReflX);
        } else {
            y = ReflectCoordinatesSetGrad(y, -1, 2 * H - 1, &gradReflY);
            x = ReflectCoordinatesSetGrad(x, -1, 2 * W - 1, &gradReflX);
        }
        y = ClipCoorDinatesSetGrad(y, H, &gradClipY);
        x = ClipCoorDinatesSetGrad(x, W, &gradClipX);
    }

    int32_t iy = static_cast<int32_t>(SafeDowngradeToIntRange(y));
    int32_t ix = static_cast<int32_t>(SafeDowngradeToIntRange(x));
    if (ix >= 0 && ix < static_cast<int32_t>(W) && iy >= 0 && iy < static_cast<int32_t>(H)) {
        asc_atomic_add(data + iy * sH + ix * sW, static_cast<T>(delta));
    }
}

} // namespace GridSampler3DGradSimtBase
#endif // GRID_SAMPLER3D_GRAD_SIMT_BASE_H_
