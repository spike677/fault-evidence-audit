/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

/* !
 * \file resize_bicubic_v2.cpp
 * \brief resize_bicubic_v2
 */

#include "./arch35/resize_bicubic_v2_simt_base.h"
#include "./arch35/resize_bicubic_v2_simt_nchw.h"
#include "./arch35/resize_bicubic_v2_simt_nhwc.h"
#include "./arch35/resize_bicubic_v2_tiling_key.h"
#include "./arch35/resize_bicubic_v2_base.h"
#include "./arch35/resize_bicubic_v2_all_copy.h"
#include "./arch35/resize_bicubic_v2_point_copy.h"

using namespace AscendC;
using namespace ResizeBicubicV2;

template <uint64_t schId, uint64_t isInt32, uint64_t isHalfPixel, uint64_t isNchw>
__global__ __aicore__ void resize_bicubic_v2(GM_ADDR x, GM_ADDR size, GM_ADDR y, GM_ADDR workspace, GM_ADDR tiling)
{
    KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY);
    GET_TILING_DATA(tilingData, tiling);
    TPipe pipe;
    if constexpr (schId == RESIZE_BICUBIC_V2_TPL_SCH_MODE_5) {
        ResizeBicubicV2::ResizeBicubicV2AllCopy<DTYPE_X, isHalfPixel, schId, uint32_t, int32_t> op;
        op.Init(x, size, y, &pipe, &tilingData);
        op.Process();
        return;
    } else if (schId == RESIZE_BICUBIC_V2_TPL_SCH_MODE_6) {
        ResizeBicubicV2::ResizeBicubicV2PointCopy<DTYPE_X, isHalfPixel, schId, uint32_t, int32_t> op;
        op.Init(x, size, y, &pipe, &tilingData);
        op.Process();
        return;
    }
    if constexpr (isNchw == 1) {
        if constexpr (isInt32 == 1) {
            ResizeBicubicV2::ResizeBicubicV2SimtNCHW<DTYPE_X, isHalfPixel, schId, uint32_t, int32_t> op;
            op.Init(x, size, y, &tilingData);
            op.Process();
        } else {
            ResizeBicubicV2::ResizeBicubicV2SimtNCHW<DTYPE_X, isHalfPixel, schId, uint64_t, int64_t> op;
            op.Init(x, size, y, &tilingData);
            op.Process();
        }
        return;
    } else {
        if constexpr (isInt32 == 1) {
            ResizeBicubicV2::ResizeBicubicV2SimtNHWC<DTYPE_X, isHalfPixel, schId, uint32_t, int32_t> op;
            op.Init(x, size, y, &tilingData);
            op.Process();
        } else {
            ResizeBicubicV2::ResizeBicubicV2SimtNHWC<DTYPE_X, isHalfPixel, schId, uint64_t, int64_t> op;
            op.Init(x, size, y, &tilingData);
            op.Process();
        }
        return;
    }
}
