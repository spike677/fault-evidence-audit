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
 * \file resize_linear_tiling_arch35.cpp
 * \brief resize_linear_tiling_arch35
 */
#include "resize_linear_tiling_arch35.h"
#include "image/resize_linear/op_kernel/arch35/resize_linear_tiling_key.h"

namespace optiling {
constexpr size_t WORK_SPACE_SIZE = static_cast<size_t>(16 * 1024 * 1024);
static const uint64_t DIM_0 = 0;
static const uint64_t DIM_1 = 1;
static const uint64_t DIM_3 = 3;
static const uint64_t DIM_2 = 2;
static const uint64_t DIM_4 = 4;
static const int32_t EVEN_FACTOR = 2;
class ResizeLinearTiling {
public:
    explicit ResizeLinearTiling(gert::TilingContext* context) : context_(context) {};
    void LinearGetPlatformData(const ResizeLinearCompileInfo* compileInfo);
    ge::graphStatus LinearCompute();
    ge::graphStatus CheckParams();
    ge::graphStatus CheckShapeAndAxes();
    ge::graphStatus CheckSizeInput();
    float ComputeScale(float scale, int64_t lenSrc, int64_t lenDes);
    ge::graphStatus SetTilingData();
    void PrintTilingData();
    void ComputeKey();

private:
    ResizeLinearTilingData tilingData_;
    gert::TilingContext* context_ = nullptr;
    uint64_t schId_ = 0;
    uint64_t isInt32_ = 0;
    uint64_t isHalfPiex_ = 0;
    int32_t coreNum_ = 0;
    int64_t ubSize_ = 0;
    int32_t alignCorners_ = 0;
    int64_t realCoreNum_ = 0;
    int64_t blkProcessNum_ = 0;
    int64_t splitBlockTailFactor_ = 0;
    int64_t lenSrcL_ = 0;
    int64_t lenDesL_ = 0;
    int64_t ySize_ = 0;
    int64_t xSize_ = 0;
    float scaleL_ = 0.0f;
};

void ResizeLinearTiling::ComputeKey()
{
    // 判断scaleL是否是1.0的整数倍
    float result = scaleL_ / 1.0f;
    int32_t int_result = static_cast<int32_t>(result);
    float reconstructedA = int_result * 1.0f;
    bool isIntScale = std::fabs(scaleL_ - reconstructedA) < 1e-6;
    OP_LOGI(context_->GetNodeName(), "isIntScale is %d", isIntScale);
    bool oddScale = false;
    if (alignCorners_ == 0 && isIntScale) {
        int32_t intScaleL = static_cast<int32_t>(scaleL_);
        oddScale = intScaleL % EVEN_FACTOR == 1;
        OP_LOGI(context_->GetNodeName(), "oddScale is %d, intScaleL is %d", oddScale, intScaleL);
    }
    if (lenDesL_ == lenSrcL_) {
        schId_ = DIM_1;
    } else if (lenDesL_ == 1 && alignCorners_ > 0) {
        schId_ = DIM_3;
    } else if (lenSrcL_ == 1) {
        schId_ = DIM_2;
    } else if ((alignCorners_ > 0 && isIntScale) || (oddScale)) {
        schId_ = DIM_4;
    } else {
        schId_ = DIM_0;
    }
    return;
}

ge::graphStatus ResizeLinearTiling::CheckShapeAndAxes()
{
    auto images = context_->GetInputShape(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, images);
    gert::Shape imagesShape = images->GetStorageShape();
    int32_t imagesDims = imagesShape.GetDimNum();
    auto y = context_->GetOutputShape(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, y);
    gert::Shape yShape = y->GetStorageShape();

    int32_t yshapeDims = yShape.GetDimNum();
    if (imagesDims != DIM_3 || yshapeDims != DIM_3) {
        std::string dimMsg = std::to_string(imagesDims) + " and " + std::to_string(yshapeDims);
        OP_LOGE_FOR_INVALID_SHAPEDIMS_WITH_REASON(context_->GetNodeName(), "x and y", dimMsg.c_str(),
                                                  "The shapes of x and y must be 3D");
        return ge::GRAPH_FAILED;
    }

    lenSrcL_ = imagesShape.GetDim(DIM_2);
    lenDesL_ = yShape.GetDim(DIM_2);
    OP_LOGD(context_->GetNodeName(), "lenDesL is %ld, lenSrcL is %ld", lenDesL_, lenSrcL_);

    int64_t n = imagesShape.GetDim(DIM_0);
    int64_t c = imagesShape.GetDim(DIM_1);
    int64_t oN = yShape.GetDim(DIM_0);
    int64_t oC = yShape.GetDim(DIM_1);
    if (n != oN || c != oC) {
        std::string shapeMsg = Ops::Base::ToString(imagesShape) + " and " + Ops::Base::ToString(yShape);
        std::string reasonMsg = "The N-dimension and C-dimension of x and y must be the same, where N is the 0th axis "
                                "and C is the 1st axis";
        OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(context_->GetNodeName(), "x and y", shapeMsg.c_str(), reasonMsg.c_str());
        return ge::GRAPH_FAILED;
    }

    OP_LOGI(context_->GetNodeName(), "n is %ld, c is %ld", n, c);
    ySize_ = yShape.GetShapeSize();
    xSize_ = imagesShape.GetShapeSize();
    if (n <= 0 || c <= 0 || lenDesL_ <= 0 || lenSrcL_ <= 0) {
        std::string shapeMsg = Ops::Base::ToString(imagesShape) + " and " + Ops::Base::ToString(yShape);
        std::string reasonMsg = "All axes of x and y must be greater than zero";
        OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(context_->GetNodeName(), "x and y", shapeMsg.c_str(), reasonMsg.c_str());
        return ge::GRAPH_FAILED;
    }

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeLinearTiling::CheckSizeInput()
{
    auto y = context_->GetOutputShape(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, y);
    gert::Shape yShape = y->GetStorageShape();

    auto size = context_->GetInputShape(DIM_1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, size);
    gert::Shape sizeShape = Ops::Cv::OpTiling::EnsureNotScalar(size->GetStorageShape());
    int32_t sizeDims = sizeShape.GetDimNum();
    OP_CHECK_IF(sizeDims != DIM_1,
                OP_LOGE_FOR_INVALID_SHAPEDIM(context_->GetNodeName(), "size", std::to_string(sizeDims).c_str(), "1D"),
                return ge::GRAPH_FAILED);
    int64_t sizeL = 0;
    OP_CHECK_IF(!Ops::Base::GetConstInt(context_, DIM_1, sizeL), OP_LOGE(context_->GetNodeName(), "get size failed"),
                return ge::GRAPH_FAILED);
    OP_LOGI(context_->GetNodeName(), "sizeL is %ld", sizeL);
    if (sizeL != lenDesL_) {
        std::string reasonMsg = "The linear-dimension of output y must be equal to the value (" +
                                std::to_string(sizeL) + ") of input parameter size";
        OP_LOGE_FOR_INVALID_SHAPE_WITH_REASON(context_->GetNodeName(), "y", Ops::Base::ToString(yShape).c_str(),
                                              reasonMsg.c_str());
        return ge::GRAPH_FAILED;
    }
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeLinearTiling::CheckParams()
{
    OP_CHECK_IF((CheckShapeAndAxes() != ge::GRAPH_SUCCESS),
                OP_LOGE(context_->GetNodeName(), "CheckShapeAndAxes failed."), return ge::GRAPH_FAILED);

    OP_CHECK_IF((CheckSizeInput() != ge::GRAPH_SUCCESS), OP_LOGE(context_->GetNodeName(), "CheckSizeInput failed."),
                return ge::GRAPH_FAILED);

    return ge::GRAPH_SUCCESS;
}

float ResizeLinearTiling::ComputeScale(float scale, int64_t lenSrc, int64_t lenDes)
{
    float newScale = 0.0f;
    if (scale > 0.0f) {
        newScale = static_cast<float>(1.0f) / scale;
    } else {
        newScale = static_cast<float>(lenSrc) / static_cast<float>(lenDes);
    }
    return newScale;
}

ge::graphStatus ResizeLinearTiling::LinearCompute()
{
    OP_CHECK_IF(CheckParams() != ge::GRAPH_SUCCESS, OP_LOGE(context_->GetNodeName(), "input params is error"),
                return ge::GRAPH_FAILED);
    // Get attrs: alignCorners
    auto attrs = context_->GetAttrs();
    OP_CHECK_NULL_WITH_CONTEXT(context_, attrs);
    const bool* alignCornersPtr = attrs->GetAttrPointer<bool>(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, alignCornersPtr);
    alignCorners_ = *alignCornersPtr ? 1 : 0;
    isHalfPiex_ = *alignCornersPtr ? DIM_0 : DIM_1;

    const float* scale = attrs->GetAttrPointer<float>(DIM_1);

    OP_CHECK_NULL_WITH_CONTEXT(context_, scale);
    scaleL_ = *scale;
    OP_LOGI(context_->GetNodeName(), "ori scaleL is %f, alignCorners is %d", scaleL_, alignCorners_);
    realCoreNum_ = (ySize_ < coreNum_) ? ySize_ : coreNum_;
    blkProcessNum_ = Ops::Base::FloorDiv(ySize_, realCoreNum_);
    splitBlockTailFactor_ = ySize_ - blkProcessNum_ * realCoreNum_;
    if (alignCorners_ == 0) {
        scaleL_ = ComputeScale(scaleL_, lenSrcL_, lenDesL_);
        OP_LOGI(context_->GetNodeName(), "attr new scaleL is %f", scaleL_);
    } else {
        scaleL_ = static_cast<float>(lenSrcL_) / static_cast<float>(lenDesL_);
        if (lenDesL_ > 1) {
            scaleL_ = static_cast<float>(lenSrcL_ - 1) / static_cast<float>(lenDesL_ - 1);
        }
        OP_LOGI(context_->GetNodeName(), "compute scaleL is %f", scaleL_);
    }
    isInt32_ = DIM_1;
    if (ySize_ > UINT32_MAX || xSize_ > UINT32_MAX) {
        OP_LOGI(context_->GetNodeName(), "ySize or xSize is too large");
        isInt32_ = DIM_0;
    }
    if (lenSrcL_ > INT32_MAX || lenDesL_ > INT32_MAX) {
        isInt32_ = DIM_0;
    }
    ComputeKey();
    return ge::GRAPH_SUCCESS;
}

void ResizeLinearTiling::LinearGetPlatformData(const ResizeLinearCompileInfo* compileInfo)
{
    coreNum_ = compileInfo->totalCoreNum;
    ubSize_ = static_cast<int64_t>(compileInfo->totalUbSize);
    OP_LOGI(context_->GetNodeName(), "LinearGetPlatformData ubSize is %ld, coreNum_ is %d", ubSize_, coreNum_);
    return;
}

void ResizeLinearTiling::PrintTilingData()
{
    OP_LOGI(context_->GetNodeName(),
            "ResizeLinear tilingData realCoreNum is %ld, blkProcessNum is %ld,"
            "splitBlockTailFactor is %ld, lenSrcL is %ld, lenDesL is %ld, scaleL is %f",
            realCoreNum_, blkProcessNum_, splitBlockTailFactor_, lenSrcL_, lenDesL_, scaleL_);
    return;
}

ge::graphStatus ResizeLinearTiling::SetTilingData()
{
    tilingData_.set_realCoreNum(realCoreNum_);
    tilingData_.set_blkProcessNum(blkProcessNum_);
    tilingData_.set_splitBlockTailFactor(splitBlockTailFactor_);
    tilingData_.set_lenSrcL(lenSrcL_);
    tilingData_.set_lenDesL(lenDesL_);
    tilingData_.set_scaleL(scaleL_);

    tilingData_.SaveToBuffer(context_->GetRawTilingData()->GetData(), context_->GetRawTilingData()->GetCapacity());
    context_->GetRawTilingData()->SetDataSize(tilingData_.GetDataSize());

    context_->SetBlockDim(realCoreNum_);
    OP_LOGI(context_->GetNodeName(), "schId is %ld, isInt32 is %ld, isHalfPiex is %ld", schId_, isInt32_, isHalfPiex_);
    const uint64_t tilingKey = GET_TPL_TILING_KEY(schId_, isInt32_, isHalfPiex_);
    context_->SetTilingKey(tilingKey);

    size_t* workspaces = context_->GetWorkspaceSizes(1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, workspaces);
    workspaces[0] = WORK_SPACE_SIZE;
    PrintTilingData();
    return ge::GRAPH_SUCCESS;
}

static ge::graphStatus Tiling4ResizeLinear(gert::TilingContext* context)
{
    auto compileInfo = static_cast<const ResizeLinearCompileInfo*>(context->GetCompileInfo());
    OP_CHECK_NULL_WITH_CONTEXT(context, compileInfo);
    ResizeLinearTiling tilingObject(context);
    tilingObject.LinearGetPlatformData(compileInfo);
    if (tilingObject.LinearCompute() != ge::GRAPH_SUCCESS) {
        OP_LOGE(context->GetNodeName(), "LinearCompute return failed.");
        return ge::GRAPH_FAILED;
    }
    if (tilingObject.SetTilingData() != ge::GRAPH_SUCCESS) {
        OP_LOGE(context->GetNodeName(), "SetTilingData return failed.");
        return ge::GRAPH_FAILED;
    }
    return ge::GRAPH_SUCCESS;
}

static ge::graphStatus TilingPrepare4ResizeLinear(gert::TilingParseContext* context)
{
    OP_LOGI(context->GetNodeName(), "TilingPrepare4ResizeLinear running.");
    auto compileInfo = context->GetCompiledInfo<ResizeLinearCompileInfo>();
    OP_CHECK_NULL_WITH_CONTEXT(context, compileInfo);
    auto platformInfo = context->GetPlatformInfo();
    OP_CHECK_NULL_WITH_CONTEXT(context, platformInfo);
    auto ascendcPlatform = platform_ascendc::PlatformAscendC(platformInfo);
    compileInfo->totalCoreNum = ascendcPlatform.GetCoreNumAiv();
    OP_CHECK_IF((compileInfo->totalCoreNum <= 0), OP_LOGE(context->GetNodeName(), "coreNum is error"),
                return ge::GRAPH_FAILED);

    uint64_t ubSizePlatForm;
    ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::UB, ubSizePlatForm);
    compileInfo->totalUbSize = static_cast<int32_t>(ubSizePlatForm);
    OP_CHECK_IF((compileInfo->totalUbSize <= 0), OP_LOGE(context->GetNodeName(), "ubSize is small than zero"),
                return ge::GRAPH_FAILED);
    return ge::GRAPH_SUCCESS;
}

IMPL_OP_OPTILING(ResizeLinear)
    .Tiling(Tiling4ResizeLinear)
    .TilingParse<ResizeLinearCompileInfo>(TilingPrepare4ResizeLinear);
} // namespace optiling
