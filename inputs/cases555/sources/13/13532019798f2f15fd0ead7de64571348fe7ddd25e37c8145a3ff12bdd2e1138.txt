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
 * \file grid_sample_tiling.cpp
 * \brief
 */
#include "grid_sample_tiling.h"

using Ops::Cv::OpTiling::GET_TILINGKEY;

namespace optiling {
constexpr uint64_t TILING_OFFSET = 1000000000000UL;

uint64_t GridSampleTiling::GetTilingKey() const
{
    GridSampleDtypeKey dtypeKey = GridSampleDtypeKey::FLOAT32;
    if (xDtype == ge::DT_FLOAT16) {
        dtypeKey = GridSampleDtypeKey::FLOAT16;
    } else if (xDtype == ge::DT_BF16) {
        dtypeKey = GridSampleDtypeKey::BFLOAT16;
    }

    uint64_t tilingKey =
        GET_TILINGKEY(interpolationMode, dtypeKey, dimValue, schedulerMode, dimension, templateCNum, tempType);
    OP_LOGD(context_->GetNodeName(), "schedulerMode:%ld,tilingKey:%zu.", schedulerMode, tilingKey);

    return tilingKey % TILING_OFFSET;
}

ge::graphStatus GridSampleTiling::GetShapeAttrsInfo()
{
    OP_LOGD(context_->GetNodeName(), "GetShapeAttrsInfo begin.");
    auto inputX = context_->GetInputShape(0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, inputX);
    auto inputXDesc = context_->GetInputDesc(0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, inputXDesc);
    xDtype = inputXDesc->GetDataType();
    auto gridXDesc = context_->GetInputDesc(1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, gridXDesc);
    auto gridDtype = gridXDesc->GetDataType();
    auto xShape = Ops::Cv::OpTiling::EnsureNotScalar(inputX->GetStorageShape());
    auto inputGrid = context_->GetInputShape(1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, inputGrid);
    auto gridShape = Ops::Cv::OpTiling::EnsureNotScalar(inputGrid->GetStorageShape());
    OP_LOGD(context_->GetNodeName(),
        "x shape:%s,grid shape:%s",
        Ops::Base::ToString(xShape).c_str(),
        Ops::Base::ToString(gridShape).c_str());

    OP_CHECK_IF((xShape.GetDimNum() != DIM_NUM_4D && xShape.GetDimNum() != DIM_NUM_5D) ||
                    (gridShape.GetDimNum() != DIM_NUM_4D && gridShape.GetDimNum() != DIM_NUM_5D),
        OP_LOGE(context_->GetNodeName(), "x / grid shape length should be 4 or 5"),
        return ge::GRAPH_FAILED);
    OP_CHECK_IF(xShape.GetDimNum() != gridShape.GetDimNum(),
        OP_LOGE(context_->GetNodeName(), "x / grid shape length should be equal."),
        return ge::GRAPH_FAILED);

    OP_CHECK_IF(gridShape.GetDim(0) != xShape.GetDim(0),
        OP_LOGE(context_->GetNodeName(), "x / grid shape[0] should be same"),
        return ge::GRAPH_FAILED);

    if (xShape.GetDimNum() == DIM_NUM_5D) {
        dimension = 1;
        dimValue = gridShape.GetDim(DIM_4);
        OP_CHECK_IF(dimValue != DIM_3,
            OP_LOGE(context_->GetNodeName(), "only support (N, D, H, W, 3) for grid"),
            return ge::GRAPH_FAILED);
    } else {
        dimension = 0;
        dimValue = gridShape.GetDim(DIM_3);
        OP_CHECK_IF(dimValue != DIM_2,
            OP_LOGE(context_->GetNodeName(), "only support (N, H, W, 2) for grid"),
            return ge::GRAPH_FAILED);
    }

    auto compileInfo = reinterpret_cast<const GridSampleCompileInfo *>(context_->GetCompileInfo());
    OP_CHECK_NULL_WITH_CONTEXT(context_, compileInfo);
    regBase = compileInfo->regBase;

    OP_CHECK_IF((!regBase && dimension == 0 && xDtype != ge::DT_FLOAT && xDtype != ge::DT_FLOAT16),
        OP_LOGE(context_->GetNodeName(), "x datatype only support FLOAT32 or FLOAT16"),
        return ge::GRAPH_FAILED);
    OP_CHECK_IF((!regBase && dimension == 0 && gridDtype != ge::DT_FLOAT && gridDtype != ge::DT_FLOAT16),
        OP_LOGE(context_->GetNodeName(), "grid datatype only support FLOAT32 or FLOAT16"),
        return ge::GRAPH_FAILED);
    OP_CHECK_IF((regBase && dimension == 0 && xDtype != ge::DT_FLOAT && xDtype != ge::DT_FLOAT16 && xDtype != ge::DT_BF16),
        OP_LOGE(context_->GetNodeName(), "x datatype only support FLOAT32, FLOAT16, BFLOAT16"),
        return ge::GRAPH_FAILED);
    OP_CHECK_IF((regBase && dimension == 0 && gridDtype != ge::DT_FLOAT && gridDtype != ge::DT_FLOAT16 && gridDtype != ge::DT_BF16),
        OP_LOGE(context_->GetNodeName(), "grid datatype only support FLOAT32, FLOAT16, BFLOAT16"),
        return ge::GRAPH_FAILED);
    OP_CHECK_IF((dimension == 1 && xDtype != ge::DT_FLOAT && xDtype != ge::DT_FLOAT16 && xDtype != ge::DT_BF16),
        OP_LOGE(context_->GetNodeName(), "x datatype only support FLOAT32, FLOAT16, BFLOAT16"),
        return ge::GRAPH_FAILED);
    OP_CHECK_IF(
        (dimension == 1 && gridDtype != ge::DT_FLOAT && gridDtype != ge::DT_FLOAT16 && gridDtype != ge::DT_BF16),
        OP_LOGE(context_->GetNodeName(), "grid datatype only support FLOAT32, FLOAT16, BFLOAT16"),
        return ge::GRAPH_FAILED);

    auto *attrs = context_->GetAttrs();
    OP_CHECK_NULL_WITH_CONTEXT(context_, attrs);
    const char *pInterpolationMode = attrs->GetAttrPointer<char>(0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, pInterpolationMode);
    if (strcmp(pInterpolationMode, "bilinear") == 0) {
        interpolationMode = INTERPOLATION_MODE_BILINEAR;
    } else if (strcmp(pInterpolationMode, "bicubic") == 0) {
        interpolationMode = INTERPOLATION_MODE_BICUBIC;
    } else if (strcmp(pInterpolationMode, "nearest") == 0) {
        interpolationMode = INTERPOLATION_MODE_NEAREST;
    } else {
        OP_LOGE(context_->GetNodeName(), "interpolation_mode only support bilinear or nearest or bicubic.");
        return ge::GRAPH_FAILED;
    }

    OP_CHECK_IF(dimension == 1 && interpolationMode == INTERPOLATION_MODE_BICUBIC,
        OP_LOGE(context_->GetNodeName(), "GridSampler3D interpolation_mode only support bilinear or nearest"),
        return ge::GRAPH_FAILED);

    const char *pPaddingMode = attrs->GetAttrPointer<char>(1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, pPaddingMode);
    if (strcmp(pPaddingMode, "zeros") == 0) {
        paddingMode = PADDING_MODE_ZEROS;
    } else if (strcmp(pPaddingMode, "border") == 0) {
        paddingMode = PADDING_MODE_BORDER;
    } else if (strcmp(pPaddingMode, "reflection") == 0) {
        paddingMode = PADDING_MODE_REFLECTION;
    } else {
        OP_LOGE(context_->GetNodeName(), "padding_mode only support zeros or border or reflection.");
        return ge::GRAPH_FAILED;
    }

    const bool *pAlignCorners = attrs->GetAttrPointer<bool>(2);
    OP_CHECK_NULL_WITH_CONTEXT(context_, pAlignCorners);
    alignCorners = ALIGN_CORNERS_FALSE;
    if (*pAlignCorners) {
        alignCorners = ALIGN_CORNERS_TRUE;
    }

    const bool *pChannelLast = attrs->GetAttrPointer<bool>(3);
    OP_CHECK_NULL_WITH_CONTEXT(context_, pChannelLast);
    channelLast = CHANEL_LAST_FALSE;
    if (*pChannelLast) {
        channelLast = CHANEL_LAST_TRUE;
    }

    inN = xShape.GetDim(0);
    if (dimension == 0) {
        if (channelLast == 0) {
            inC = xShape.GetDim(1);
            inH = xShape.GetDim(DIM_2);
            inW = xShape.GetDim(DIM_3);
        } else {
            inH = xShape.GetDim(1);
            inW = xShape.GetDim(DIM_2);
            inC = xShape.GetDim(DIM_3);
        }
        outH = gridShape.GetDim(1);
        outW = gridShape.GetDim(DIM_2);

        if ((channelLast == 1) && (strcmp(pInterpolationMode, "bilinear") == 0) &&
            (inC * inH * inW <= X_MAX_HWC_FACTOR)) {
            tempType = FULL_LOAD_TYPE;
            hwFactor = TILING_HW_FACTOR;
            auto ascendc_platform = platform_ascendc::PlatformAscendC(context_->GetPlatformInfo());
            platform_ascendc::SocVersion gridSampleSocVersion = ascendc_platform.GetSocVersion();
            if ((outH * outW < BLOCK_NUM) && (inN < coreNumVar * BLOCK_NUM) && (gridSampleSocVersion == platform_ascendc::SocVersion::ASCEND310P)) {
                context_->SetScheduleMode(SCHEDULE_MODE);
            }
            OP_LOGD(context_->GetNodeName(), "Get in FullLoad Template.");
            if ((inC == 1) && (inH * inW < C1_X_COUNT)) {
                templateCNum = 1;
            } else if ((inC == NUM_C32) && (inH > MIN_HW_C32) && (inW > MIN_HW_C32)) {
                templateCNum = TEMPLATE_C32;
            } else {
                templateCNum = 0;
            }
        }

        OP_CHECK_IF(inN < 1 || inC < 1 || inH < 1 || inW < 1 || outW < 1 || outH < 1,
            OP_LOGE(context_->GetNodeName(), "Invalid shape. Maybe empty tensor."),
            return ge::GRAPH_FAILED);
        OP_CHECK_IF(inH * inW > static_cast<int64_t>(std::numeric_limits<int32_t>::max()),
            OP_LOGE(context_->GetNodeName(), "no support for H*W of x greater than int32 max value"),
            return ge::GRAPH_FAILED);

        const int32_t *pSchedulerMode = attrs->GetAttrPointer<int32_t>(4);
        OP_CHECK_NULL_WITH_CONTEXT(context_, pSchedulerMode);
        OP_LOGD(context_->GetNodeName(), "scheduler_mode is: %d", *pSchedulerMode);
        schedulerMode = *pSchedulerMode;
        OP_CHECK_IF(schedulerMode != 0 && schedulerMode != 1,
            OP_LOGE(context_->GetNodeName(), "scheduler_mode only support 0 or 1."),
            return ge::GRAPH_FAILED);
        OP_CHECK_IF(!(*pChannelLast) && schedulerMode == 1,
            OP_LOGE(context_->GetNodeName(), "scheduler_mode support 1 only in the channel last scenario."),
            return ge::GRAPH_FAILED);
    } else {
        if (channelLast == 0) {
            inC = xShape.GetDim(1);
            inD = xShape.GetDim(DIM_2);
            inH = xShape.GetDim(DIM_3);
            inW = xShape.GetDim(DIM_4);
        } else {
            inD = xShape.GetDim(1);
            inH = xShape.GetDim(DIM_2);
            inW = xShape.GetDim(DIM_3);
            inC = xShape.GetDim(DIM_4);
        }
        outD = gridShape.GetDim(1);
        outH = gridShape.GetDim(DIM_2);
        outW = gridShape.GetDim(DIM_3);

        OP_CHECK_IF(inN < 1 || inC < 1 || inD < 1 || inH < 1 || inW < 1 || outD < 1 || outW < 1 || outH < 1,
            OP_LOGE(context_->GetNodeName(), "Invalid shape. Maybe empty tensor."),
            return ge::GRAPH_FAILED);
        OP_CHECK_IF(inH * inW * inD > static_cast<int64_t>(std::numeric_limits<int32_t>::max()),
            OP_LOGE(context_->GetNodeName(), "no support for D*H*W of x greater than int32 max value"),
            return ge::GRAPH_FAILED);

        // 添加判断是否都为特例场景，若为特例场景schedulerMode为1，否则为默认值0
        if (inN == gridShape.GetDim(0) && inD == outD && inH == outH && inW == outW && inD == INT_16 && inH == INT_64 &&
            inW == INT_64 && dimValue == DIM_3 && inC == DIM_4 && (inN == INT_22 || inN == INT_88)) {
            schedulerMode = 1;
        }
    }

    OP_LOGD(context_->GetNodeName(), "GetShapeAttrsInfo end.");
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus GridSampleTiling::GetPlatformInfo()
{
    auto compileInfo = reinterpret_cast<const GridSampleCompileInfo *>(context_->GetCompileInfo());
    OP_CHECK_NULL_WITH_CONTEXT(context_, compileInfo);
    coreNumVar = compileInfo->coreNum;
    regBase = compileInfo->regBase;
    return ge::GRAPH_SUCCESS;
}

bool GridSampleTiling::IsCapable()
{
    if (regBase && interpolationMode == INTERPOLATION_MODE_BILINEAR && channelLast == 0) {
        OP_LOGD(context_->GetNodeName(),"GridSampleTiling template is not capabled, enter next template.");
        return false;
    }
    return true;
}

ge::graphStatus GridSampleTiling::DoLibApiTiling()
{
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus GridSampleTiling::GetWorkspaceSize()
{
    int64_t outHW = outH * outW;
    needCoreNum = coreNumVar;
    if (inN < coreNumVar && outHW <= hwFactor) {
        needCoreNum = inN;
    }
    workspaceSize_ = SIZE_16 * LENGTH_1024 * LENGTH_1024;
    if (xDtype == ge::DT_FLOAT16 || xDtype == ge::DT_BF16) {
        // 每个核使用inC * 512(1024) * dtype(float),再乘上核数
        size_t outputShapeSize =
            static_cast<size_t>(needCoreNum) * static_cast<size_t>(inC) * static_cast<size_t>(hwFactor) * sizeof(float);
        workspaceSize_ = workspaceSize_ + outputShapeSize;
    }
    if (tempType == FULL_LOAD_TYPE) {
        workspaceSize_ = workspaceSize_ * DOUBLE;
    }

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus GridSampleTiling::DoOpTiling()
{
    tilingData.set_coreNumVar(coreNumVar);
    tilingData.set_inN(inN);
    tilingData.set_inC(inC);
    tilingData.set_inD(inD);
    tilingData.set_inH(inH);
    tilingData.set_inW(inW);
    tilingData.set_outD(outD);
    tilingData.set_outH(outH);
    tilingData.set_outW(outW);
    tilingData.set_interpolationMode(interpolationMode);
    tilingData.set_paddingMode(paddingMode);
    tilingData.set_alignCorners(alignCorners);
    tilingData.set_channelLast(channelLast);

    // output format is [N, C, H, W]
    int64_t outputD = outD == 0 ? 1 : outD;
    int64_t outputHW = outH * outW * outputD;
    if (inN < coreNumVar && outputHW <= hwFactor) {
        tilingData.set_needCoreNum(inN);
    } else {
        tilingData.set_needCoreNum(coreNumVar);
    }

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus GridSampleTiling::PostTiling()
{
    context_->SetBlockDim(tilingData.get_needCoreNum());
    size_t *workspaces = context_->GetWorkspaceSizes(1);
    workspaces[0] = workspaceSize_;

    gert::TilingData *rawTilingData = context_->GetRawTilingData();
    OP_CHECK_IF(
        rawTilingData == nullptr, OP_LOGE(context_->GetNodeType(), "GetRawTilingData failed."), return ge::GRAPH_FAILED);
    OP_CHECK_IF(tilingData.GetDataSize() > rawTilingData->GetCapacity(),
        OP_LOGE(context_,
            "actual tiling data size %zu > context tiling data size %zu",
            tilingData.GetDataSize(),
            rawTilingData->GetCapacity()),
        return ge::GRAPH_FAILED);
    tilingData.SaveToBuffer(rawTilingData->GetData(), rawTilingData->GetCapacity());
    rawTilingData->SetDataSize(tilingData.GetDataSize());

    return ge::GRAPH_SUCCESS;
}

static ge::graphStatus Tiling4GridSample(gert::TilingContext *context)
{
    return Ops::Cv::OpTiling::TilingRegistry::GetInstance().DoTilingImpl(context);
}

static ge::graphStatus TilingPrepare4GridSample(gert::TilingParseContext *context)
{
    OP_LOGD(context->GetNodeName(), "TilingPrepare4GridSample running.");

    auto compileInfo = context->GetCompiledInfo<GridSampleCompileInfo>();
    OP_CHECK_NULL_WITH_CONTEXT(context, compileInfo);
    auto platformInfo = context->GetPlatformInfo();
    OP_CHECK_NULL_WITH_CONTEXT(context, platformInfo);
    auto ascendcPlatform = platform_ascendc::PlatformAscendC(platformInfo);
    compileInfo->coreNum = ascendcPlatform.GetCoreNumAiv();
    compileInfo->regBase = Ops::Cv::OpTiling::IsRegbaseSocVersion(context);
    OP_CHECK_IF((compileInfo->coreNum <= 0),
        OP_LOGE(
            context->GetNodeName(), "Get core num failed, core num: %u", static_cast<uint32_t>(compileInfo->coreNum)),
        return ge::GRAPH_FAILED);

    uint64_t ubSizePlatForm;
    ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::UB, ubSizePlatForm);
    compileInfo->ubSizePlatForm = ubSizePlatForm;
    OP_CHECK_IF((compileInfo->ubSizePlatForm <= 0),
        OP_LOGE(context->GetNodeName(),
            "Get ub size failed, ub size: %u",
            static_cast<uint32_t>(compileInfo->ubSizePlatForm)),
        return ge::GRAPH_FAILED);
    OP_LOGD(context->GetNodeName(), "TilingPrepare4GridSample end.");
    return ge::GRAPH_SUCCESS;
}
REGISTER_OPS_TILING_TEMPLATE(GridSample, GridSampleTiling, 1000);

IMPL_OP_OPTILING(GridSample).Tiling(Tiling4GridSample).TilingParse<GridSampleCompileInfo>(TilingPrepare4GridSample);
}  // namespace optiling