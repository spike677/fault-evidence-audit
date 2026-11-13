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
 * \file polar_tiling.cpp
 * \brief polar broadcast tiling implementation
 */
#include <graph/utils/type_utils.h>
#include "op_host/math_tiling_templates_registry.h"
#include "log/log.h"
#include "atvoss/broadcast/broadcast_tiling.h"
#include "../../op_kernel/arch35/polar_dag.h"
#include "../../op_kernel/arch35/polar_struct.h"
#include "polar_tiling.h"

using namespace Ops::Base;
using namespace AscendC;
using namespace ge;

namespace optiling {

constexpr static uint64_t POLAR_COMMON_TILING_PRIORITY = 0;

ge::graphStatus PolarTiling::GetShapeAttrsInfo() { return ge::GRAPH_SUCCESS; }

bool PolarTiling::IsCapable() { return true; }

ge::graphStatus PolarTiling::DoOpTiling()
{
    auto outputDesc = context_->GetOutputDesc(0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, outputDesc);
    ge::DataType outputDtype = outputDesc->GetDataType();

    ge::graphStatus ret = ge::GRAPH_SUCCESS;
    if (outputDtype == ge::DT_COMPLEX64) {
        BroadcastBaseTiling<PolarOp::PolarBrcDag<complex64, float>::OpDag> brcBaseTiling(context_);
        ret = brcBaseTiling.DoTiling();
        tilingKey = GET_TPL_TILING_KEY(brcBaseTiling.GetSchMode());
    } else {
        OP_LOGE_FOR_INVALID_DTYPE(context_->GetNodeName(), "output", ge::TypeUtils::DataTypeToSerialString(outputDtype),
                                  "COMPLEX64");
        return ge::GRAPH_FAILED;
    }

    return ret;
}

ge::graphStatus PolarTiling::DoLibApiTiling() { return ge::GRAPH_SUCCESS; }

uint64_t PolarTiling::GetTilingKey() const { return tilingKey; }

ge::graphStatus PolarTiling::GetWorkspaceSize() { return ge::GRAPH_SUCCESS; }

ge::graphStatus PolarTiling::PostTiling() { return ge::GRAPH_SUCCESS; }

ge::graphStatus PolarTiling::GetPlatformInfo() { return ge::GRAPH_SUCCESS; }

ge::graphStatus TilingForPolar(gert::TilingContext* context)
{
    OP_LOGD("PolarTiling", "Enter TilingForPolar");
    if (context == nullptr) {
        OP_LOGE("PolarTiling", "Tiling context is nullptr");
        return ge::GRAPH_FAILED;
    }

    auto compileInfo = reinterpret_cast<const PolarCompileInfo*>(context->GetCompileInfo());
    OP_CHECK_NULL_WITH_CONTEXT(context, compileInfo);

    OP_LOGD(context, "Enter ascendc PolarTiling");
    return Ops::Math::OpTiling::TilingRegistry::GetInstance().DoTilingImpl(context);
}

ge::graphStatus TilingPrepareForPolar(gert::TilingParseContext* context)
{
    auto compileInfoPtr = context->GetCompiledInfo<PolarCompileInfo>();
    OP_CHECK_NULL_WITH_CONTEXT(context, compileInfoPtr);
    fe::PlatFormInfos* platformInfoPtr = context->GetPlatformInfo();
    OP_CHECK_NULL_WITH_CONTEXT(context, platformInfoPtr);
    auto ascendcPlatform = platform_ascendc::PlatformAscendC(platformInfoPtr);
    compileInfoPtr->coreNum = ascendcPlatform.GetCoreNumAiv();
    ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::UB, compileInfoPtr->ubSize);
    return ge::GRAPH_SUCCESS;
}

IMPL_OP_OPTILING(Polar).Tiling(TilingForPolar).TilingParse<PolarCompileInfo>(TilingPrepareForPolar);

REGISTER_OPS_TILING_TEMPLATE(Polar, PolarTiling, POLAR_COMMON_TILING_PRIORITY);
} // namespace optiling