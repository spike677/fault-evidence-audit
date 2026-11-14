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
 * \file resize_nearest_neighbor_v2_grad_tiling.cc
 * \brief resize_nearest_neighbor_v2_grad_tiling
 */

#include <cmath>
#include "graph/utils/type_utils.h"
#include "../../op_kernel/arch35/resize_nearest_neighbor_v2_grad_tiling_key.h"
#include "resize_nearest_neighbor_v2_grad_tiling_base.h"
#include "log/log.h"
#include "op_host/tiling_util.h"
#include "util/math_util.h"
#include "util/platform_util.h"
#include "op_host/tiling_util.h"
#include <cmath>

using namespace ge;

namespace optiling {
constexpr int64_t INPUT_IDX_GRADS = 0;
constexpr int64_t INPUT_IDX_SIZE = 1;
constexpr int64_t OUTPUT_IDX_Y = 0;
constexpr int64_t ATTR_ALIGN_CORNERS_IDX = 0;
constexpr int64_t ATTR_HALF_PIXEL_CENTERS_IDX = 1;
constexpr int64_t ATTR_SCALES_IDX = 2;
constexpr int64_t SCALES_NUM = 2;
constexpr int64_t SCALE_H = 0;
constexpr int64_t SCALE_W = 1;
constexpr int64_t IDX_ORIG_H = 0;
constexpr int64_t IDX_ORIG_W = 1;
constexpr int64_t IDX_DIM_N = 0;
constexpr int64_t IDX_NCHW_C = 1;
constexpr int64_t IDX_NCHW_H = 2;
constexpr int64_t IDX_NCHW_W = 3;
constexpr int64_t IDX_NHWC_H = 1;
constexpr int64_t IDX_NHWC_W = 2;
constexpr int64_t IDX_NHWC_C = 3;
constexpr int64_t FALSE_NUM = 0;
constexpr int64_t TRUE_NUM = 1;
constexpr int64_t DIM_1 = 1;
constexpr int64_t DIM_4 = 4;
constexpr int64_t LEN_INPUT_SIZE = 2;
constexpr int64_t WORK_SPACE_SIZE = static_cast<int64_t>(16) * 1024 * 1024;
constexpr int64_t RSV_BLOCK_NUM = 8;
constexpr int64_t DB_BUFF_NUM = 2;
constexpr int32_t SIMT_RESERVED_SIZE = 32 * 1024;
constexpr int32_t SIMD_RESERVED_SIZE = 8 * 1024;
constexpr int64_t SIMT_DETERMINE_SRC_HW_THRESHOLD = 4096;     // SRC H*W shape >= 4096
constexpr int64_t SIMT_NOT_DETERMINE_SRC_HW_THRESHOLD = 4096; // SRC H*W shape >= 4096
constexpr int64_t SIMT_DETERMINE_DST_W_THRESHOLD = 2048;      // Dst W shape >= 2048
constexpr int64_t SIMT_NOT_DETERMINE_DST_W_THRESHOLD = 2048;  // Dst W shape >= 2048
constexpr int64_t SIMT_DETERMINE_DST_Y_W_RATIO = 12;          // Dst W shape / Src W shape >= 12
constexpr int64_t SIMT_NOT_DETERMINE_DST_Y_W_RATIO = 12;      // Dst W shape / Src W shape >= 12

class ResizeNearestNeighborV2GradTiling {
public:
    explicit ResizeNearestNeighborV2GradTiling(gert::TilingContext* context) : context_(context) {};
    ge::graphStatus Init(const ResizeNearestNeighborV2GradCompileInfo* compileInfo);
    ge::graphStatus RunResizeNearestNeighborV2GradTiling();

private:
    ge::graphStatus GetPlatformInfo(const ResizeNearestNeighborV2GradCompileInfo* compileInfo);
    ge::graphStatus CheckInOutShape();
    ge::graphStatus CheckInOutDtypeFormat();
    ge::graphStatus CheckInputSizeParams();
    ge::graphStatus CheckAttrsParams();
    ge::graphStatus SetDims();
    ge::graphStatus SetScales(bool isDetermine);

    bool IsMatchSimtDetermine();
    bool IsMatchAllCopy();
    void SetIndexType();
    bool IsSimtDetermineHW();
    bool IsSimtNotDetermineHW();
    void SetTilingKey();
    void DoTilingInitY();
    void DoTilingSimtNotDetermine();
    void DoTilingSimtNotDetermineHW();
    void DoTilingSimtDetermine();
    void DoTilingSimtDetermineHW();
    void DoTilingAllCopy();

    void DoTilingStrategy();
    void FillTilingData();
    void PrintTilingData();

private:
    ResizeNearestNeighborV2GradTilingData tilingData_;
    gert::TilingContext* context_ = nullptr;

    uint64_t schId_ = 0;
    uint64_t idxType_ = 0;
    int64_t alignCorners_ = FALSE_NUM;
    int64_t halfPixelCenters_ = FALSE_NUM;
    ge::Format format_ = ge::FORMAT_MAX;

    int64_t coreNum_ = 0;
    int64_t ubSize_ = 0;
    int64_t ubBlockNum_ = 0;
    int64_t blockSize_ = 0;
    int64_t isDetermine_ = 0;
    float originalScaleW_ = 0.0f;
    float originalScaleH_ = 0.0f;
    float scaleW_ = 0.0f;
    float scaleH_ = 0.0f;
    float inverseScaleW_ = 0.0f;
    float inverseScaleH_ = 0.0f;
    int64_t origHeight_ = 0;
    int64_t origWidth_ = 0;
    int32_t gradsDtypeSize_ = 0;
    int32_t yDtypeSize_ = 0;

    gert::Shape gradsShape_;
    gert::Shape yShape_;
    int64_t lenN_ = 0;
    int64_t lenC_ = 0;
    int64_t lenSrcH_ = 0;
    int64_t lenSrcW_ = 0;
    int64_t lenDstH_ = 0;
    int64_t lenDstW_ = 0;
    int64_t ubCFactor_ = 0;
    bool isNeedInitY_ = false;
    int64_t initYRealCoreNum_ = 0;
    int64_t initYSplitBlockFactor_ = 0;
    int64_t initYSplitBlockTailFactor_ = 0;
    int64_t realCoreNum_ = 0;
    int64_t splitBlockFactor_ = 0;
    int64_t splitBlockTailFactor_ = 0;
};

ge::graphStatus ResizeNearestNeighborV2GradTiling::GetPlatformInfo(
    const ResizeNearestNeighborV2GradCompileInfo* compileInfo)
{
    coreNum_ = static_cast<int64_t>(compileInfo->core_num);
    OP_CHECK_IF(coreNum_ <= 0, OP_LOGE(context_->GetNodeName(), "get aiv core num failed."), return ge::GRAPH_FAILED);

    ubSize_ = static_cast<int64_t>(compileInfo->ubSize);
    OP_CHECK_IF(ubSize_ <= 0, OP_LOGE(context_->GetNodeName(), "get ub size failed."), return ge::GRAPH_FAILED);

    blockSize_ = Ops::Base::GetUbBlockSize(context_);
    OP_CHECK_IF(blockSize_ <= 0, OP_LOGE(context_->GetNodeName(), "get ub block size failed."),
                return ge::GRAPH_FAILED);
    ubBlockNum_ = Ops::Base::CeilDiv(ubSize_, blockSize_) - RSV_BLOCK_NUM;
    isDetermine_ = context_->GetDeterministic() == 1 ? 1 : 0;
    OP_LOGI(context_->GetNodeName(), "coreNum is %ld, ubSize is %ld, ubBlockNum is %ld, isDetermine is %ld", coreNum_,
            ubSize_, ubBlockNum_, isDetermine_);

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeNearestNeighborV2GradTiling::CheckInOutShape()
{
    auto gradsShapePtr = context_->GetInputShape(INPUT_IDX_GRADS);
    OP_CHECK_NULL_WITH_CONTEXT(context_, gradsShapePtr);
    gradsShape_ = Ops::Cv::OpTiling::EnsureNotScalar(gradsShapePtr->GetOriginShape());
    auto gradsShapeSize = gradsShape_.GetShapeSize();
    auto gradsDims = gradsShape_.GetDimNum();

    auto yShapePtr = context_->GetOutputShape(OUTPUT_IDX_Y);
    OP_CHECK_NULL_WITH_CONTEXT(context_, yShapePtr);
    yShape_ = Ops::Cv::OpTiling::EnsureNotScalar(yShapePtr->GetOriginShape());
    auto yShapeSize = yShape_.GetShapeSize();
    auto yDims = yShape_.GetDimNum();

    OP_LOGI(context_->GetNodeName(), "gradsShapeSize is %ld, yShapeSize is %ld", gradsShapeSize, yShapeSize);
    if (gradsShapeSize <= 0 || yShapeSize <= 0) {
        std::string shapesizeMsg = std::to_string(gradsShapeSize) + " and " + std::to_string(yShapeSize);
        OP_LOGE_FOR_INVALID_SHAPESIZES_WITH_REASON(
            context_->GetNodeName(), "grads and y", shapesizeMsg.c_str(),
            "The shape sizes of input grads and output y must be greater than zero");
        return ge::GRAPH_FAILED;
    }

    if (gradsDims != DIM_4 || yDims != DIM_4) {
        std::string dimMsg = std::to_string(gradsDims) + " and " + std::to_string(yDims);
        OP_LOGE_FOR_INVALID_SHAPEDIMS_WITH_REASON(context_->GetNodeName(), "grads and y", dimMsg.c_str(),
                                                  "The shapes of input grads and output y must be 4D");
        return ge::GRAPH_FAILED;
    }

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeNearestNeighborV2GradTiling::CheckInOutDtypeFormat()
{
    auto gradsDstcPtr = context_->GetInputDesc(INPUT_IDX_GRADS);
    OP_CHECK_NULL_WITH_CONTEXT(context_, gradsDstcPtr);
    auto gradsFormat = gradsDstcPtr->GetOriginFormat();
    auto gradsDtype = gradsDstcPtr->GetDataType();

    auto yDstcPtr = context_->GetInputDesc(OUTPUT_IDX_Y);
    OP_CHECK_NULL_WITH_CONTEXT(context_, gradsDstcPtr);
    auto yFormat = yDstcPtr->GetOriginFormat();
    auto yDtype = gradsDstcPtr->GetDataType();
    if (gradsDtype != yDtype) {
        std::string dtypeMsg = Ops::Base::ToString(gradsDtype) + " and " + Ops::Base::ToString(yDtype);
        OP_LOGE_FOR_INVALID_DTYPES_WITH_REASON(context_->GetNodeName(), "grads and y", dtypeMsg.c_str(),
                                               "The dtypes of grads and y must be the same");
        return ge::GRAPH_FAILED;
    }
    OP_CHECK_IF(gradsDtype != ge::DT_FLOAT && gradsDtype != ge::DT_FLOAT16 && gradsDtype != ge::DT_BF16,
                OP_LOGE_FOR_INVALID_DTYPE(context_->GetNodeName(), "grads", Ops::Base::ToString(gradsDtype).c_str(),
                                          "FLOAT, FLOAT16 or BFLOAT16"),
                return ge::GRAPH_FAILED);

    gradsDtypeSize_ = GetSizeByDataType(gradsDtype);
    yDtypeSize_ = GetSizeByDataType(yDtype);
    if (gradsDtypeSize_ <= 0 || yDtypeSize_ <= 0) {
        std::string dtypeMsg = Ops::Base::ToString(gradsDtype) + " and " + Ops::Base::ToString(yDtype);
        OP_LOGE_FOR_INVALID_DTYPES_WITH_REASON(context_->GetNodeName(), "grads and y", dtypeMsg.c_str(),
                                               "The dtype sizes of input grads and output y must be greater than zero");
        return ge::GRAPH_FAILED;
    }
    if (gradsFormat != yFormat) {
        std::string formatMsg = Ops::Base::ToString(gradsFormat) + " and " + Ops::Base::ToString(yFormat);
        OP_LOGE_FOR_INVALID_FORMATS_WITH_REASON(context_->GetNodeName(), "grads and y", formatMsg.c_str(),
                                                "The formats of input grads and output y must be the same");
        return ge::GRAPH_FAILED;
    }
    if (gradsFormat != ge::FORMAT_NHWC && gradsFormat != ge::FORMAT_NCHW) {
        OP_LOGE_FOR_INVALID_FORMAT(context_->GetNodeName(), "grads", Ops::Base::ToString(gradsFormat).c_str(),
                                   "NHWC or NCHW");
        return ge::GRAPH_FAILED;
    }
    format_ = gradsFormat;
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeNearestNeighborV2GradTiling::CheckInputSizeParams()
{
    auto size = context_->GetInputShape(INPUT_IDX_SIZE);
    OP_CHECK_NULL_WITH_CONTEXT(context_, size);
    gert::Shape sizeShape = size->GetStorageShape();
    int32_t sizeElms = sizeShape.GetShapeSize();
    OP_CHECK_IF(sizeElms != LEN_INPUT_SIZE,
                OP_LOGE_FOR_INVALID_SHAPESIZE(context_->GetNodeName(), "size", std::to_string(sizeElms).c_str(),
                                              std::to_string(LEN_INPUT_SIZE).c_str()),
                return ge::GRAPH_FAILED);
    const gert::Tensor* sizeTensor = context_->GetInputTensor(DIM_1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, sizeTensor);
    OP_CHECK_IF(sizeTensor->GetDataType() != ge::DT_INT32,
                OP_LOGE_FOR_INVALID_DTYPE(context_->GetNodeName(), "size",
                                          Ops::Base::ToString(sizeTensor->GetDataType()).c_str(), "int32"),
                return ge::GRAPH_FAILED);

    std::vector<int64_t> sizeList(LEN_INPUT_SIZE);
    auto* tensorData = sizeTensor->GetData<int32_t>();
    OP_CHECK_IF(tensorData == nullptr, OP_LOGE(context_->GetNodeName(), "GetData failed, tensorData is nullptr"),
                return ge::GRAPH_FAILED);

    for (int32_t i = 0; i < LEN_INPUT_SIZE; i++) {
        sizeList[i] = static_cast<int64_t>(*(tensorData + i));
    }

    origHeight_ = sizeList[0];
    origWidth_ = sizeList[1];
    OP_LOGI(context_->GetNodeName(), "origHeight_: %ld, origWidth_: %ld", origHeight_, origWidth_);
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeNearestNeighborV2GradTiling::CheckAttrsParams()
{
    auto attrs = context_->GetAttrs();
    OP_CHECK_NULL_WITH_CONTEXT(context_, attrs);

    if (attrs->GetAttrNum() > ATTR_ALIGN_CORNERS_IDX) {
        alignCorners_ = *(attrs->GetAttrPointer<bool>(ATTR_ALIGN_CORNERS_IDX)) ? 1 : 0;
    }
    if (attrs->GetAttrNum() > ATTR_HALF_PIXEL_CENTERS_IDX) {
        halfPixelCenters_ = *(attrs->GetAttrPointer<bool>(ATTR_HALF_PIXEL_CENTERS_IDX)) ? 1 : 0;
    }
    OP_CHECK_IF(alignCorners_ && halfPixelCenters_,
                OP_LOGE_FOR_INVALID_VALUES_WITH_REASON(
                    context_->GetNodeName(), "align_corners and half_pixel_centers", "true and true",
                    "The values of attributes align_corners and half_pixel_centers cannot be true at the same time"),
                return ge::GRAPH_FAILED);

    if (attrs->GetAttrNum() > ATTR_SCALES_IDX) {
        auto scales = attrs->GetAttrPointer<gert::ContinuousVector>(ATTR_SCALES_IDX);
        int64_t scalesNum = scales->GetSize();
        OP_CHECK_IF(scalesNum != SCALES_NUM,
                    OP_LOGE_FOR_INVALID_LISTSIZE(context_->GetNodeName(), "scales", std::to_string(scalesNum).c_str(),
                                                 std::to_string(SCALES_NUM).c_str()),
                    return ge::GRAPH_FAILED);
        const float* scalesData = static_cast<const float*>(scales->GetData());
        OP_CHECK_NULL_WITH_CONTEXT(context_, scalesData);
        originalScaleH_ = scalesData[SCALE_H];
        originalScaleW_ = scalesData[SCALE_W];
        OP_LOGI(context_->GetNodeName(), "original scales(%f, %f)", originalScaleH_, originalScaleW_);
    }

    OP_LOGD(context_->GetNodeName(), "ResizeNearestNeighborV2Grad CheckAttrsParams success.");
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeNearestNeighborV2GradTiling::SetDims()
{
    OP_LOGD(context_->GetNodeName(), "Start ResizeNearestNeighborV2Grad SetDims.");
    if (gradsShape_.GetDim(IDX_DIM_N) != yShape_.GetDim(IDX_DIM_N)) {
        std::string shapeMsg = Ops::Base::ToString(gradsShape_) + " and " + Ops::Base::ToString(yShape_);
        OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(
            context_->GetNodeName(), "grads and y", shapeMsg.c_str(),
            "The N-dimension of input grads and output y must be the same, where N is the 0th axis of them");
        return ge::GRAPH_FAILED;
    }
    lenN_ = gradsShape_.GetDim(IDX_DIM_N);
    if (format_ == ge::FORMAT_NCHW) {
        if (gradsShape_.GetDim(IDX_NCHW_C) != yShape_.GetDim(IDX_NCHW_C)) {
            std::string shapeMsg = Ops::Base::ToString(gradsShape_) + " and " + Ops::Base::ToString(yShape_);
            OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(context_->GetNodeName(), "grads and y", shapeMsg.c_str(),
                                                   "The C-dimension of input grads and output y must be the same, "
                                                   "where C is the 1st axis when their formats are NCHW");
            return ge::GRAPH_FAILED;
        }
        lenC_ = gradsShape_.GetDim(IDX_NCHW_C);
        lenDstH_ = gradsShape_.GetDim(IDX_NCHW_H);
        lenDstW_ = gradsShape_.GetDim(IDX_NCHW_W);
        lenSrcH_ = yShape_.GetDim(IDX_NCHW_H);
        lenSrcW_ = yShape_.GetDim(IDX_NCHW_W);
    } else if (format_ == ge::FORMAT_NHWC) {
        if (gradsShape_.GetDim(IDX_NHWC_C) != yShape_.GetDim(IDX_NHWC_C)) {
            std::string shapeMsg = Ops::Base::ToString(gradsShape_) + " and " + Ops::Base::ToString(yShape_);
            OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(context_->GetNodeName(), "grads and y", shapeMsg.c_str(),
                                                   "The C-dimension of input grads and output y must be the same, "
                                                   "where C is the last axis when their formats are NHWC");
            return ge::GRAPH_FAILED;
        }
        lenC_ = gradsShape_.GetDim(IDX_NHWC_C);
        lenDstH_ = gradsShape_.GetDim(IDX_NHWC_H);
        lenDstW_ = gradsShape_.GetDim(IDX_NHWC_W);
        lenSrcH_ = yShape_.GetDim(IDX_NHWC_H);
        lenSrcW_ = yShape_.GetDim(IDX_NHWC_W);
    }
    if (origHeight_ != lenSrcH_ || origWidth_ != lenSrcW_) {
        std::string reasonMsg = "The H-dimension and W-dimension of output y must be equal to the value (" +
                                std::to_string(origHeight_) + ", " + std::to_string(origWidth_) +
                                ") of input parameter size";
        OP_LOGE_FOR_INVALID_SHAPE_WITH_REASON(context_->GetNodeName(), "y", Ops::Base::ToString(yShape_).c_str(),
                                              reasonMsg.c_str());
        return ge::GRAPH_FAILED;
    }
    OP_LOGI(context_->GetNodeName(), "lenN_:%ld , lenC_: %ld, srcH:%ld, srcW:%ld, dstH:%ld, dstW:%ld", lenN_, lenC_,
            lenSrcH_, lenSrcW_, lenDstH_, lenDstW_);
    OP_LOGD(context_->GetNodeName(), "ResizeNearestNeighborV2Grad SetDims success.");
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeNearestNeighborV2GradTiling::SetScales(bool isDetermine)
{
    OP_LOGD(context_->GetNodeName(), "Entering SetScales.");

    if (alignCorners_) {
        if (isDetermine) {
            scaleH_ = (lenSrcH_ > 1 && lenDstH_ > 1) ?
                          static_cast<float>(lenSrcH_ - 1) / static_cast<float>((lenDstH_ - 1)) :
                          static_cast<float>(lenSrcH_) / static_cast<float>(lenDstH_);
            scaleW_ = (lenSrcW_ > 1 && lenDstW_ > 1) ?
                          static_cast<float>(lenSrcW_ - 1) / static_cast<float>((lenDstW_ - 1)) :
                          static_cast<float>(lenSrcW_) / static_cast<float>(lenDstW_);
        } else {
            scaleH_ = (lenDstH_ > 1) ? static_cast<float>(lenSrcH_ - 1) / static_cast<float>((lenDstH_ - 1)) : 0.0f;
            scaleW_ = (lenDstW_ > 1) ? static_cast<float>(lenSrcW_ - 1) / static_cast<float>((lenDstW_ - 1)) : 0.0f;
        }
    } else {
        scaleH_ = (originalScaleH_ > 0.0f) ? 1.0f / originalScaleH_ :
                                             static_cast<float>(lenSrcH_) / static_cast<float>(lenDstH_);
        scaleW_ = (originalScaleW_ > 0.0f) ? 1.0f / originalScaleW_ :
                                             static_cast<float>(lenSrcW_) / static_cast<float>(lenDstW_);
    }
    if (isDetermine) {
        inverseScaleH_ = 1.0f / scaleH_;
        inverseScaleW_ = 1.0f / scaleW_;
    }
    OP_LOGI(context_->GetNodeName(), "SetScales scaleH_:%f , scaleW_:%f", scaleH_, scaleW_);
    return ge::GRAPH_SUCCESS;
}

/**
 * if hw shape is smaller than core number, use NCHW split the AIVs and threads; if HW shape is larger, use HW split.
 */
bool ResizeNearestNeighborV2GradTiling::IsSimtDetermineHW()
{
    if (format_ != FORMAT_NCHW) {
        return false;
    }

    if (lenDstW_ < SIMT_DETERMINE_DST_W_THRESHOLD) {
        return false;
    }

    if (1.0f / scaleW_ < SIMT_DETERMINE_DST_Y_W_RATIO) { // scale
        return false;
    }

    int64_t srcHWSize = lenSrcH_ * lenSrcW_;
    if (srcHWSize < SIMT_DETERMINE_SRC_HW_THRESHOLD) {
        return false;
    }

    return true;
}
bool ResizeNearestNeighborV2GradTiling::IsSimtNotDetermineHW()
{
    if (lenDstW_ < SIMT_NOT_DETERMINE_DST_W_THRESHOLD) {
        return false;
    }

    if (1.0f / scaleW_ < SIMT_NOT_DETERMINE_DST_Y_W_RATIO) { // scalew
        return false;
    }

    int64_t srcHWSize = lenSrcH_ * lenSrcW_;
    if (srcHWSize < SIMT_NOT_DETERMINE_SRC_HW_THRESHOLD) {
        return false;
    }

    return true;
}

void ResizeNearestNeighborV2GradTiling::SetIndexType()
{
    bool isIdx32 = yShape_.GetShapeSize() < UINT32_MAX && gradsShape_.GetShapeSize() < UINT32_MAX &&
                   lenSrcH_ <= INT32_MAX && lenSrcW_ <= INT32_MAX && lenDstH_ <= INT32_MAX && lenDstW_ <= INT32_MAX;
    idxType_ = static_cast<uint64_t>(isIdx32 ? TPL_IDX_INT32 : TPL_IDX_INT64);
}

// Using parameters to choose determine, determine compare to torch
bool ResizeNearestNeighborV2GradTiling::IsMatchSimtDetermine() { return !alignCorners_; }

void ResizeNearestNeighborV2GradTiling::SetTilingKey()
{
    SetIndexType();
    if ((lenSrcH_ == lenDstH_ && lenSrcW_ == lenDstW_)) {
        schId_ = static_cast<uint64_t>(TPL_SCH_ID_ALL_COPY);
        return;
    }

    if (((lenSrcH_ == lenDstH_ && lenSrcH_ == 1) || (lenSrcW_ == lenDstW_ && lenSrcW_ == 1)) &&
        IsMatchSimtDetermine()) {
        schId_ = static_cast<uint64_t>(TPL_SCH_ID_DETERMINE_1D);
        return;
    }

    if (!IsMatchSimtDetermine() && IsSimtNotDetermineHW()) {
        schId_ = static_cast<uint64_t>(TPL_SCH_ID_NOT_DETERMINE_HW);
        return;
    }

    if (!IsMatchSimtDetermine()) {
        schId_ = static_cast<uint64_t>(TPL_SCH_ID_NOT_DETERMINE);
        return;
    }

    if (IsMatchSimtDetermine() && IsSimtDetermineHW()) {
        schId_ = static_cast<uint64_t>(TPL_SCH_ID_DETERMINE_HW);
        return;
    }

    schId_ = static_cast<uint64_t>(TPL_SCH_ID_DETERMINE);
}

void ResizeNearestNeighborV2GradTiling::DoTilingInitY()
{
    isNeedInitY_ = true;
    initYRealCoreNum_ = (yShape_.GetShapeSize() < coreNum_) ? yShape_.GetShapeSize() : coreNum_;
    initYSplitBlockFactor_ = Ops::Base::FloorDiv(yShape_.GetShapeSize(), initYRealCoreNum_);
    initYSplitBlockTailFactor_ = yShape_.GetShapeSize() - initYSplitBlockFactor_ * initYRealCoreNum_;
}

void ResizeNearestNeighborV2GradTiling::DoTilingAllCopy()
{
    realCoreNum_ = (yShape_.GetShapeSize() < coreNum_) ? yShape_.GetShapeSize() : coreNum_;
    splitBlockFactor_ = Ops::Base::FloorDiv(yShape_.GetShapeSize(), realCoreNum_);
    splitBlockTailFactor_ = yShape_.GetShapeSize() - splitBlockFactor_ * realCoreNum_;
    ubCFactor_ = ubBlockNum_ / DB_BUFF_NUM * blockSize_ / yDtypeSize_;
}

void ResizeNearestNeighborV2GradTiling::DoTilingSimtDetermine()
{
    realCoreNum_ = (yShape_.GetShapeSize() < coreNum_) ? yShape_.GetShapeSize() : coreNum_;
    splitBlockFactor_ = Ops::Base::FloorDiv(yShape_.GetShapeSize(), realCoreNum_);
    splitBlockTailFactor_ = yShape_.GetShapeSize() - splitBlockFactor_ * realCoreNum_;
}

void ResizeNearestNeighborV2GradTiling::DoTilingSimtNotDetermine()
{
    DoTilingInitY();

    realCoreNum_ = (gradsShape_.GetShapeSize() < coreNum_) ? gradsShape_.GetShapeSize() : coreNum_;
    splitBlockFactor_ = Ops::Base::FloorDiv(gradsShape_.GetShapeSize(), realCoreNum_);
    splitBlockTailFactor_ = gradsShape_.GetShapeSize() - splitBlockFactor_ * realCoreNum_;
}

void ResizeNearestNeighborV2GradTiling::DoTilingSimtNotDetermineHW()
{
    DoTilingInitY();
    int64_t srcHWSize = lenDstH_ * lenDstW_;
    realCoreNum_ = (gradsShape_.GetShapeSize() < coreNum_) ? gradsShape_.GetShapeSize() : coreNum_;
    splitBlockFactor_ = Ops::Base::FloorDiv(srcHWSize, realCoreNum_);
    splitBlockTailFactor_ = srcHWSize - splitBlockFactor_ * realCoreNum_;
}

void ResizeNearestNeighborV2GradTiling::DoTilingSimtDetermineHW()
{
    int64_t srcHWSize = lenSrcH_ * lenSrcW_;
    realCoreNum_ = coreNum_;
    splitBlockFactor_ = Ops::Base::FloorDiv(srcHWSize, realCoreNum_);
    splitBlockTailFactor_ = srcHWSize - splitBlockFactor_ * realCoreNum_;
}

void ResizeNearestNeighborV2GradTiling::DoTilingStrategy()
{
    SetTilingKey();
    switch (schId_) {
        case TPL_SCH_ID_ALL_COPY:
            DoTilingAllCopy();
            break;
        case TPL_SCH_ID_NOT_DETERMINE:
            DoTilingSimtNotDetermine();
            break;
        case TPL_SCH_ID_NOT_DETERMINE_HW:
            DoTilingSimtNotDetermineHW();
            break;
        case TPL_SCH_ID_DETERMINE:
        case TPL_SCH_ID_DETERMINE_1D:
            DoTilingSimtDetermine();
            break;
        case TPL_SCH_ID_DETERMINE_HW:
            DoTilingSimtDetermineHW();
            break;
        default:
            break;
    }
}

void ResizeNearestNeighborV2GradTiling::FillTilingData()
{
    OP_LOGD(context_->GetNodeName(), "Entering FillTilingData.");
    tilingData_.set_ubSize(ubSize_);
    tilingData_.set_lenN(lenN_);
    tilingData_.set_lenC(lenC_);
    // schId_ = TPL_SCH_ID_DETERMINE_1D W=1
    if (lenSrcW_ == lenDstW_ && lenSrcW_ == 1 && IsMatchSimtDetermine()) {
        tilingData_.set_lenSrcH(lenSrcW_);
        tilingData_.set_lenSrcW(lenSrcH_);
        tilingData_.set_lenDstH(lenDstW_);
        tilingData_.set_lenDstW(lenDstH_);
        tilingData_.set_scaleH(scaleW_);
        tilingData_.set_scaleW(scaleH_);
        tilingData_.set_inverseScaleH(inverseScaleW_);
        tilingData_.set_inverseScaleW(inverseScaleH_);
    } else {
        tilingData_.set_lenSrcH(lenSrcH_);
        tilingData_.set_lenSrcW(lenSrcW_);
        tilingData_.set_lenDstH(lenDstH_);
        tilingData_.set_lenDstW(lenDstW_);
        tilingData_.set_scaleH(scaleH_);
        tilingData_.set_scaleW(scaleW_);
        tilingData_.set_inverseScaleH(inverseScaleH_);
        tilingData_.set_inverseScaleW(inverseScaleW_);
    }
    tilingData_.set_ubCFactor(ubCFactor_);
    tilingData_.set_initYRealCoreNum(initYRealCoreNum_);
    tilingData_.set_initYSplitBlockFactor(initYSplitBlockFactor_);
    tilingData_.set_initYSplitBlockTailFactor(initYSplitBlockTailFactor_);
    tilingData_.set_realCoreNum(realCoreNum_);
    tilingData_.set_splitBlockFactor(splitBlockFactor_);
    tilingData_.set_splitBlockTailFactor(splitBlockTailFactor_);

    tilingData_.SaveToBuffer(context_->GetRawTilingData()->GetData(), context_->GetRawTilingData()->GetCapacity());
    context_->GetRawTilingData()->SetDataSize(tilingData_.GetDataSize());
}

void ResizeNearestNeighborV2GradTiling::PrintTilingData()
{
    OP_LOGI(context_->GetNodeName(),
            "lenN:%ld, lenC:%ld, lenSrcH:%ld, lenSrcW:%ld, lenDstH:%ld, lenDstW:%ld, ubCFactor:%ld, \
        scaleH:%f, scaleW:%f, inverseScaleH:%f, inverseScaleW:%f, initYRealCoreNum:%ld, initYSplitBlockFactor:%ld, \
        initYSplitBlockTailFactor:%ld, realCoreNum:%ld, splitBlockFactor:%ld,splitBlockTailFactor:%ld",
            tilingData_.get_lenN(), tilingData_.get_lenC(), tilingData_.get_lenSrcH(), tilingData_.get_lenSrcW(),
            tilingData_.get_lenDstH(), tilingData_.get_lenDstW(), tilingData_.get_ubCFactor(), tilingData_.get_scaleH(),
            tilingData_.get_scaleW(), tilingData_.get_inverseScaleH(), tilingData_.get_inverseScaleW(),
            tilingData_.get_initYRealCoreNum(), tilingData_.get_initYSplitBlockFactor(),
            tilingData_.get_initYSplitBlockTailFactor(), tilingData_.get_realCoreNum(),
            tilingData_.get_splitBlockFactor(), tilingData_.get_splitBlockTailFactor());
}

ge::graphStatus ResizeNearestNeighborV2GradTiling::Init(const ResizeNearestNeighborV2GradCompileInfo* compileInfo)
{
    OP_LOGD(context_->GetNodeName(), "Enter ResizeNearestNeighborV2GradTiling init.");
    OP_CHECK_IF((GetPlatformInfo(compileInfo) != ge::GRAPH_SUCCESS),
                OP_LOGE(context_->GetNodeName(), "GetPlatformInfo failed."), return ge::GRAPH_FAILED);
    OP_CHECK_IF((CheckInOutShape() != ge::GRAPH_SUCCESS), OP_LOGE(context_->GetNodeName(), "CheckInOutShape failed."),
                return ge::GRAPH_FAILED);
    OP_CHECK_IF((CheckInOutDtypeFormat() != ge::GRAPH_SUCCESS),
                OP_LOGE(context_->GetNodeName(), "CheckInOutDtypeFormat failed."), return ge::GRAPH_FAILED);
    OP_CHECK_IF((CheckInputSizeParams() != ge::GRAPH_SUCCESS),
                OP_LOGE(context_->GetNodeName(), "CheckInputSizeParams failed."), return ge::GRAPH_FAILED);
    OP_CHECK_IF((CheckAttrsParams() != ge::GRAPH_SUCCESS), OP_LOGE(context_->GetNodeName(), "CheckAttrsParams failed."),
                return ge::GRAPH_FAILED);

    OP_CHECK_IF(SetDims() != ge::GRAPH_SUCCESS, OP_LOGE(context_->GetNodeName(), "Failed to SetDims!"),
                return ge::GRAPH_FAILED);
    OP_CHECK_IF(SetScales(IsMatchSimtDetermine()) != ge::GRAPH_SUCCESS,
                OP_LOGE(context_->GetNodeName(), "Failed to SetScales!"), return ge::GRAPH_FAILED);

    OP_LOGD(context_->GetNodeName(), "Exit ResizeNearestNeighborV2GradTiling init.");
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeNearestNeighborV2GradTiling::RunResizeNearestNeighborV2GradTiling()
{
    OP_LOGD(context_->GetNodeName(), "Start running Tiling4ResizeNearestNeighborV2Grad.");
    DoTilingStrategy();
    FillTilingData();
    PrintTilingData();

    context_->SetBlockDim(realCoreNum_);
    if (isNeedInitY_ && realCoreNum_ < initYRealCoreNum_) {
        context_->SetBlockDim(initYRealCoreNum_);
    }

    const uint64_t tilingKey = GET_TPL_TILING_KEY(schId_, static_cast<uint64_t>(format_),
                                                  static_cast<uint64_t>(alignCorners_),
                                                  static_cast<uint64_t>(halfPixelCenters_), idxType_);
    OP_LOGI(context_->GetNodeName(),
            "schId is %ld, format is %ld, alignCorners is %ld, halfPixelCenters is %ld, idxType is %ld",
            static_cast<int64_t>(schId_), static_cast<int64_t>(format_), static_cast<int64_t>(alignCorners_),
            static_cast<int64_t>(halfPixelCenters_), static_cast<int64_t>(idxType_));

    context_->SetTilingKey(tilingKey);

    size_t* workspaces = context_->GetWorkspaceSizes(1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, workspaces);
    workspaces[0] = static_cast<size_t>(WORK_SPACE_SIZE);
    // 32K for simt dcache and 8k for ascendc
    context_->SetLocalMemorySize(ubSize_ - SIMT_RESERVED_SIZE - SIMD_RESERVED_SIZE);
    OP_LOGD(context_->GetNodeName(), "ResizeNearestNeighborV2GradTiling success.");
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeNearestNeighborV2GradTilingForAscendC(gert::TilingContext* context,
                                                            const ResizeNearestNeighborV2GradCompileInfo* compileInfo)
{
    OP_LOGD(context->GetNodeName(), "Start ResizeNearestNeighborV2GradTilingForAscendC.");
    ResizeNearestNeighborV2GradTiling tilingObject(context);

    if (tilingObject.Init(compileInfo) != ge::GRAPH_SUCCESS) {
        OP_LOGE(context->GetNodeName(), "ResizeNearestNeighborV2GradTilingForAscendC init failed.");
        return ge::GRAPH_FAILED;
    }

    if (tilingObject.RunResizeNearestNeighborV2GradTiling() != ge::GRAPH_SUCCESS) {
        OP_LOGE(context->GetNodeName(), "ResizeNearestNeighborV2GradTilingForAscendC do tiling failed.");
        return ge::GRAPH_FAILED;
    }
    return ge::GRAPH_SUCCESS;
}

} // namespace optiling