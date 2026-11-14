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
 * \file grid_sample_tiling_arch35.h
 * \brief grid_sample_tiling_arch35 info
 */
#ifndef GRID_SAMPLE_TILING_ARCH35_H
#define GRID_SAMPLE_TILING_ARCH35_H

#include <cstdint>
#include <vector>
#include "register/tilingdata_base.h"
#include "log/log.h"
#include "register/op_impl_registry.h"
#include "util/math_util.h"
#include "tiling/platform/platform_ascendc.h"
#include "platform/platform_infos_def.h"
#include "op_common/op_host/util/platform_util.h"
#include "op_host/tiling_templates_registry.h"
#include "op_host/tiling_key.h"
#include "op_host/tiling_util.h"
#include "grid_sample_tiling.h"
#include "op_host/tiling_base.h"

namespace optiling {

class GridSampleArch35Tiling : public GridSampleTiling {
public:
    explicit GridSampleArch35Tiling(gert::TilingContext *context) : GridSampleTiling(context)
    {}

protected:
    bool IsCapable() override;
    // 3、计算数据切分TilingData
    ge::graphStatus DoOpTiling() override;
    // 5、计算TilingKey
    uint64_t GetTilingKey() const override;
    // 6、计算Workspace 大小
    ge::graphStatus GetWorkspaceSize() override;
    // 7、保存Tiling数据
    ge::graphStatus PostTiling() override;

private:
    GridSampleTilingData tilingData;
    int64_t inputSize;
    int64_t gridSize;
};

}
#endif