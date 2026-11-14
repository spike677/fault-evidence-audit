/**
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

/*!
 * \file iou3d_tiling_data.h
 * \brief Iou3D TilingData 结构体定义（arch35）
 *
 * ✅ 使用标准 C++ struct 定义 TilingData
 * ❌ 禁止使用废弃的 BEGIN_TILING_DATA_DEF 宏
 *
 * 字段职责：
 *   - batch/numBboxes/numGtboxes : 逻辑规模 B / N / K
 *   - coreNum/pairsPerCore       : 多核切分（总 (b,i,j) 对按核均分为不相交子集）
 *   - tileLen/tailLen            : 单核内 UB 批处理粒度（(i,j) 对数）
 *   - isEmpty                    : 空 Tensor 标志（batch==0 || N==0 || K==0），用于 TPL_EMPTY 短路
 *
 * 注：极角排序（Sort32）临时 buffer 由 kernel 侧按固定 IOU3D_SORT32_LEN(32) 分配，与逻辑规模无关，
 *     故无需 Host 侧动态精算 sortTmpSize（历史遗留字段已移除）。
 */

#ifndef _IOU3D_TILING_DATA_H_
#define _IOU3D_TILING_DATA_H_

#include <cstdint>

struct Iou3DTilingData {
    uint32_t batch = 0;        // B
    uint32_t numBboxes = 0;    // N（预测框数）
    uint32_t numGtboxes = 0;   // K（真值框数，D5 对标 mmcv 已移除上限）
    uint32_t coreNum = 0;      // 参与计算的核数
    uint32_t pairsPerCore = 0; // 每核负责的 (b,i,j) 对数（向上取整分配）
    uint32_t tileLen = 0;      // 单批处理的 (i,j) 对数（UB 批大小）
    uint32_t tailLen = 0;      // 尾批 (i,j) 对数
    uint32_t isEmpty = 0;      // 空 Tensor 标志（batch==0 || N==0 || K==0）
};
#endif // _IOU3D_TILING_DATA_H_
