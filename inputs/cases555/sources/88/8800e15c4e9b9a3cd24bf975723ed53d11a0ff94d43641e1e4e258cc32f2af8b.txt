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
 * \file random_unified_tiling_data_arch35.h
 * \brief tiling base data
 */

#ifndef RANDOM_UNIFIED_TILING_DATA_STRUCT_H
#define RANDOM_UNIFIED_TILING_DATA_STRUCT_H

#include <sstream>
class RandomUnifiedTilingDataStruct {
public:
    int64_t usedCoreNum = 0;
    int64_t normalCoreProNum = 0;
    int64_t tailCoreProNum = 0;
    int64_t singleBufferSize = 0;
    uint32_t key[2] = {0};
    uint32_t counter[4] = {0};
    int64_t outputSize = 0;
    int64_t probTensorSize = 0;
    int64_t sharedTmpBufSize = 0;
    float keepProb = 0;
    uint32_t reserved = 0;

    std::ostringstream DumpTilingInfo() {
        std::ostringstream info;
        info << " usedCoreNum: " << usedCoreNum;
        info << " normalCoreProNum: " << normalCoreProNum;
        info << " tailCoreProNum: " << tailCoreProNum;
        info << " singleBufferSize: " << singleBufferSize;
        info << " key: [" << key[0] << ", " << key[1] << "]";
        info << " counter: [" << counter[0] << ", " << counter[1] << ", "
        << counter[2] << ", " << counter[3] << "]";
        info << " outputSize: " << outputSize;
        info << " probTensorSize: " << probTensorSize;
        info << " sharedTmpBufSize: " << sharedTmpBufSize;
        info << " keepProb: " << keepProb;

        return info;
    }
};

#endif