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
 * \file resize_bilinear_v2_grad_tiling_arch35.cpp
 * \brief resize_bilinear_v2_grad_tiling_arch35
 */
#include "resize_bilinear_v2_grad_tiling_arch35.h"
#include "op_host/tiling_util.h"
#include "register/op_impl_registry.h"
#include "log/log.h"
#include "util/math_util.h"

namespace optiling {
constexpr size_t INPUT_GRADS_IDX = 0;
constexpr size_t INPUT_ORIGINAL_IMAGE_IDX = 1;
constexpr size_t OUTPUT_Y_IDX = 0;
constexpr size_t ATTR_ALIGN_CORERS_IDX = 0;
constexpr size_t ATTR_HALF_PIXEL_CENTERS_IDX = 1;
constexpr size_t ATTR_SCALES_IDX = 2;
constexpr size_t SCALES_NUM = 2;
constexpr size_t SCALE_H = 0;
constexpr size_t SCALE_W = 1;
constexpr size_t DIM_LEN_4D = 4;
constexpr size_t N_DIM_IDX = 0;
constexpr size_t C_DIM_IDX_NCHW = 1;
constexpr size_t H_DIM_IDX_NCHW = 2;
constexpr size_t W_DIM_IDX_NCHW = 3;
constexpr size_t H_DIM_IDX_NHWC = 1;
constexpr size_t W_DIM_IDX_NHWC = 2;
constexpr size_t C_DIM_IDX_NHWC = 3;
constexpr size_t WORKSPACE_SIZE = 32;
constexpr int64_t TILING_KEY_SIMT_NCHW = 10000;
constexpr int64_t TILING_KEY_SIMT_NHWC = 10001;
constexpr int64_t TILING_KEY_SIMT_NCHW_DETERMINE = 10002;
constexpr int64_t TILING_KEY_SIMT_NHWC_DETERMINE = 10003;
constexpr int64_t TILING_KEY_SIMT_NCHW_DETERMINE_SCALES = 10012;
constexpr int64_t TILING_KEY_SIMT_NHWC_DETERMINE_SCALES = 10013;
constexpr int64_t TILING_KEY_SIMT_NCHW_IDX64 = 10004;
constexpr int64_t TILING_KEY_SIMT_NHWC_IDX64 = 10005;
constexpr int64_t TILING_KEY_SIMT_NCHW_DETERMINE_IDX64 = 10006;
constexpr int64_t TILING_KEY_SIMT_NCHW_DETERMINE_SCALES_IDX64 = 100016;
constexpr int64_t TILING_KEY_SIMT_NHWC_DETERMINE_IDX64 = 10007;
constexpr int64_t TILING_KEY_SIMT_NHWC_DETERMINE_SCALES_IDX64 = 100017;
constexpr int64_t TILING_KEY_C_PARALLEL = 20000;
constexpr int64_t TILING_KEY_ALL_COPY = 30000;
constexpr int64_t TILING_KEY_POINT_COPY = 30001;
constexpr int64_t ONE_BLOCK_SIZE = 32;
constexpr int64_t RSV_BLOCK_NUM = 8;
constexpr int64_t DB_BUFF_NUM = 2;
constexpr int64_t EVEN_FACTOR = 2;
constexpr int64_t C_PARALLEL_GRADS_TENSOR_NUM = 1;
constexpr int64_t C_PARALLEL_Y_TENSOR_NUM = 4;
constexpr int64_t MIN_C_SIZE = 128;
constexpr float FLT_EPSILON = 1e-6;

ge::graphStatus ResizeBilinearV2GradTilingAscendC::GetPlatformInfo(const ResizeBilinearV2GradCompileInfo* compileInfo)
{
    coreNum_ = static_cast<int64_t>(compileInfo->coreNum);
    OP_CHECK_IF(coreNum_ <= 0, OP_LOGE(nodeName_, "get aiv core num failed."), return ge::GRAPH_FAILED);

    ubSize_ = static_cast<int64_t>(compileInfo->ubSize);
    OP_CHECK_IF(ubSize_ <= 0, OP_LOGE(nodeName_, "get ub size failed."), return ge::GRAPH_FAILED);

    ubBlockNum_ = Ops::Base::CeilDiv(ubSize_, ONE_BLOCK_SIZE) - RSV_BLOCK_NUM;

    isDetermine_ = context_->GetDeterministic() == 1 ? 1 : 0;

    OP_LOGI(
        nodeName_, "coreNum is %ld, ubSize is %ld, ubBlockNum is %ld, isDetermine is %ld", coreNum_, ubSize_,
        ubBlockNum_, isDetermine_);

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBilinearV2GradTilingAscendC::GetTensorInfo()
{
    auto gradsShapePtr = context_->GetInputShape(INPUT_GRADS_IDX);
    OP_CHECK_NULL_WITH_CONTEXT(context_, gradsShapePtr);
    gradsShape_ = Ops::Cv::OpTiling::EnsureNotScalar(gradsShapePtr->GetOriginShape());
    auto gradsDescPtr = context_->GetInputDesc(INPUT_GRADS_IDX);
    OP_CHECK_NULL_WITH_CONTEXT(context_, gradsDescPtr);
    gradsDtype_ = gradsDescPtr->GetDataType();
    gradsFormat_ = gradsDescPtr->GetOriginFormat();

    auto originalImageShapePtr = context_->GetInputShape(INPUT_ORIGINAL_IMAGE_IDX);
    OP_CHECK_NULL_WITH_CONTEXT(context_, originalImageShapePtr);
    originalImageShape_ = Ops::Cv::OpTiling::EnsureNotScalar(originalImageShapePtr->GetOriginShape());
    auto originalImageDescPtr = context_->GetInputDesc(INPUT_ORIGINAL_IMAGE_IDX);
    OP_CHECK_NULL_WITH_CONTEXT(context_, originalImageDescPtr);
    originalImageDtype_ = originalImageDescPtr->GetDataType();
    originalImageFormat_ = originalImageDescPtr->GetOriginFormat();

    auto yShapePtr = context_->GetOutputShape(OUTPUT_Y_IDX);
    OP_CHECK_NULL_WITH_CONTEXT(context_, yShapePtr);
    yShape_ = Ops::Cv::OpTiling::EnsureNotScalar(yShapePtr->GetOriginShape());
    auto yDescPtr = context_->GetOutputDesc(OUTPUT_Y_IDX);
    OP_CHECK_NULL_WITH_CONTEXT(context_, yDescPtr);
    yDtype_ = yDescPtr->GetDataType();
    yFormat_ = yDescPtr->GetOriginFormat();

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBilinearV2GradTilingAscendC::GetAttrInfo()
{
    auto attrs = context_->GetAttrs();
    OP_CHECK_NULL_WITH_CONTEXT(context_, attrs);

    if (attrs->GetAttrNum() > ATTR_ALIGN_CORERS_IDX) {
        alignCorners_ = *(attrs->GetAttrPointer<bool>(ATTR_ALIGN_CORERS_IDX)) ? 1 : 0;
    }
    if (attrs->GetAttrNum() > ATTR_HALF_PIXEL_CENTERS_IDX) {
        halfPixelCenters_ = *(attrs->GetAttrPointer<bool>(ATTR_HALF_PIXEL_CENTERS_IDX)) ? 1 : 0;
    }
    OP_CHECK_IF(
        alignCorners_ && halfPixelCenters_,
        OP_LOGE_FOR_INVALID_VALUES_WITH_REASON(
            nodeName_.c_str(), "align_corners and half_pixel_centers", "true and true",
            "The values of attributes align_corners and half_pixel_centers cannot be true at the same time"),
        return ge::GRAPH_FAILED);

    if (attrs->GetAttrNum() > ATTR_SCALES_IDX) {
        auto scales = attrs->GetAttrPointer<gert::ContinuousVector>(ATTR_SCALES_IDX);
        int64_t scalesNum = scales->GetSize();
        OP_CHECK_IF(
            scalesNum != SCALES_NUM, OP_LOGE_FOR_INVALID_LISTSIZE(
                nodeName_.c_str(), "scales", std::to_string(scalesNum).c_str(),
                std::to_string(SCALES_NUM).c_str()),
            return ge::GRAPH_FAILED);
        const float* scalesData = reinterpret_cast<const float*>(scales->GetData());
        OP_CHECK_NULL_WITH_CONTEXT(context_, scalesData);
        originalScaleH_ = scalesData[SCALE_H];
        originalScaleW_ = scalesData[SCALE_W];
        OP_LOGI(nodeName_, "original scales(%f, %f)", originalScaleH_, originalScaleW_);
    }

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBilinearV2GradTilingAscendC::CheckDtypeValid()
{
    OP_CHECK_IF(
        gradsDtype_ != ge::DT_FLOAT && gradsDtype_ != ge::DT_FLOAT16 && gradsDtype_ != ge::DT_BF16,
        OP_LOGE_FOR_INVALID_DTYPE(nodeName_.c_str(), "grads", Ops::Base::ToString(gradsDtype_).c_str(),
            "FLOAT, FLOAT16 and BFLOAT16"), return ge::GRAPH_FAILED);

    if (originalImageDtype_ != yDtype_) {
        std::string dtypeMsg = Ops::Base::ToString(originalImageDtype_) + " and " +
                               Ops::Base::ToString(yDtype_);
        std::string reasonMsg = "The dtypes of input original_image and output y must be the same";
        OP_LOGE_FOR_INVALID_DTYPES_WITH_REASON(nodeName_.c_str(), "original_image and y", dtypeMsg.c_str(), reasonMsg.c_str());
        return ge::GRAPH_FAILED;
    }

    if (gradsDtype_ != ge::DT_FLOAT) {
        if (gradsDtype_ != yDtype_) {
            std::string dtypeMsg = Ops::Base::ToString(gradsDtype_) + " and " +
                                   Ops::Base::ToString(yDtype_);
            std::string reasonMsg = "The dtypes of input grads and output y must be the same, when the dtype of grads is not float";
            OP_LOGE_FOR_INVALID_DTYPES_WITH_REASON(nodeName_.c_str(), "grads and y", dtypeMsg.c_str(), reasonMsg.c_str());
            return ge::GRAPH_FAILED;
        }
    } else {
        OP_CHECK_IF(
            yDtype_ != ge::DT_FLOAT && yDtype_ != ge::DT_FLOAT16 && yDtype_ != ge::DT_BF16,
            OP_LOGE_FOR_INVALID_DTYPE_WITH_REASON(nodeName_.c_str(), "y", Ops::Base::ToString(yDtype_).c_str(),
                "The dtype of output y must be within the range of float, float16 and bfloat16, when the dtype of grads is float"),
            return ge::GRAPH_FAILED);
    }

    gradsDtypeSize_ = GetSizeByDataType(gradsDtype_);
    yDtypeSize_ = GetSizeByDataType(yDtype_);
    if (gradsDtypeSize_ <= 0 || yDtypeSize_ <= 0) {
        std::string dtypeMsg = Ops::Base::ToString(gradsDtype_) + " and " + Ops::Base::ToString(yDtype_);
        OP_LOGE_FOR_INVALID_DTYPES_WITH_REASON(
            nodeName_.c_str(), "grads and y", dtypeMsg.c_str(),
            "The dtype sizes of input grads and output y must be greater than zero");
        return ge::GRAPH_FAILED;
    }

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBilinearV2GradTilingAscendC::CheckFormatValid()
{
    if (gradsFormat_ != originalImageFormat_ || gradsFormat_ != yFormat_) {
        std::string formatMsg = Ops::Base::ToString(gradsFormat_) + ", " +
                                Ops::Base::ToString(originalImageFormat_) + " and " +
                                Ops::Base::ToString(yFormat_);
        OP_LOGE_FOR_INVALID_FORMATS_WITH_REASON(
            nodeName_.c_str(), "grads, original_image and y", formatMsg.c_str(),
            "The formats of inputs grads, original_image and output y must be the same");
        return ge::GRAPH_FAILED;
    }

    OP_CHECK_IF(
        (yFormat_ != ge::FORMAT_NCHW && yFormat_ != ge::FORMAT_NHWC),
        OP_LOGE_FOR_INVALID_FORMAT(nodeName_.c_str(), "y", Ops::Base::ToString(yFormat_).c_str(), "NCHW or NHWC"),
        return ge::GRAPH_FAILED);

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBilinearV2GradTilingAscendC::CheckShapeDimValid()
{
    if (gradsShape_.GetDimNum() != DIM_LEN_4D || yShape_.GetDimNum() != DIM_LEN_4D) {
        std::string shapedimMsg =
            std::to_string(gradsShape_.GetDimNum()) + " and " + std::to_string(yShape_.GetDimNum());
        OP_LOGE_FOR_INVALID_SHAPEDIMS_WITH_REASON(
            nodeName_.c_str(), "grads and y", shapedimMsg.c_str(), "The shapes of input grads and output y must be 4D");
        return ge::GRAPH_FAILED;
    }

    if (originalImageShape_ != yShape_) {
        std::string shapeMsg = Ops::Base::ToString(originalImageShape_) + " and " + Ops::Base::ToString(yShape_);
        OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(nodeName_.c_str(), "original_image and y", shapeMsg.c_str(),
            "The shapes of original_image and y must be the same");
        return ge::GRAPH_FAILED;
    }

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBilinearV2GradTilingAscendC::CheckAxesValid()
{
    if (gradsShape_.GetDim(N_DIM_IDX) != yShape_.GetDim(N_DIM_IDX)) {
        std::string shapeMsg = Ops::Base::ToString(gradsShape_) + " and " + Ops::Base::ToString(yShape_);
        OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(nodeName_.c_str(), "grads and y", shapeMsg.c_str(),
            "The N-dimension of input grads and output y must be the same, where N is the 0 axis of them");
        return ge::GRAPH_FAILED;
    }
    lenN_ = yShape_.GetDim(N_DIM_IDX);
    if (lenN_ <= 0) {
        std::string reasonMsg = "The N-dimension of y must be greater than zero, where N is the 0 axis of y";
        OP_LOGE_FOR_INVALID_SHAPE_WITH_REASON(
            nodeName_.c_str(), "y", Ops::Base::ToString(yShape_).c_str(), reasonMsg.c_str());
        return ge::GRAPH_FAILED;
    }

    if (yFormat_ == ge::FORMAT_NCHW) {
        if (gradsShape_.GetDim(C_DIM_IDX_NCHW) != yShape_.GetDim(C_DIM_IDX_NCHW)) {
            std::string shapeMsg = Ops::Base::ToString(gradsShape_) + " and " + Ops::Base::ToString(yShape_);
            OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(nodeName_.c_str(), "grads and y", shapeMsg.c_str(),
                "The C-dimension of input grads and output y must be the same, where C is the 1st axis when their formats are NCHW");
            return ge::GRAPH_FAILED;
        }
        lenC_ = yShape_.GetDim(C_DIM_IDX_NCHW);
        lenSrcH_ = yShape_.GetDim(H_DIM_IDX_NCHW);
        lenDesH_ = gradsShape_.GetDim(H_DIM_IDX_NCHW);
        lenSrcW_ = yShape_.GetDim(W_DIM_IDX_NCHW);
        lenDesW_ = gradsShape_.GetDim(W_DIM_IDX_NCHW);
    } else {
        if (gradsShape_.GetDim(C_DIM_IDX_NHWC) != yShape_.GetDim(C_DIM_IDX_NHWC)) {
            std::string shapeMsg = Ops::Base::ToString(gradsShape_) + " and " + Ops::Base::ToString(yShape_);
            OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(nodeName_.c_str(), "grads and y", shapeMsg.c_str(),
                "The C-dimension of input grads and output y must be the same, where C is the last axis when their formats are NHWC");
            return ge::GRAPH_FAILED;
        }
        lenSrcH_ = yShape_.GetDim(H_DIM_IDX_NHWC);
        lenDesH_ = gradsShape_.GetDim(H_DIM_IDX_NHWC);
        lenSrcW_ = yShape_.GetDim(W_DIM_IDX_NHWC);
        lenDesW_ = gradsShape_.GetDim(W_DIM_IDX_NHWC);
        lenC_ = yShape_.GetDim(C_DIM_IDX_NHWC);
    }

    if (lenSrcH_ <= 0 || lenSrcW_ <= 0 || lenDesH_ <= 0 || lenDesW_ <= 0) {
        std::string shapeMsg = Ops::Base::ToString(gradsShape_) + " and " + Ops::Base::ToString(yShape_);
        std::string reasonMsg = "The H-dimension and W-dimension of grads and y must be greater than 0, "
                                "where H and W are inferred from the 4D shapes of input grads and output y "
                                "based on their formats: axes 2/3 for NCHW, or axes 1/2 for NHWC";
        OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(nodeName_.c_str(), "grads and y", shapeMsg.c_str(), reasonMsg.c_str());
        return ge::GRAPH_FAILED;
    }

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBilinearV2GradTilingAscendC::CheckShapeValid()
{
    OP_CHECK_IF(
        (CheckShapeDimValid() != ge::GRAPH_SUCCESS), OP_LOGE(nodeName_, "CheckShapeDimValid failed."),
        return ge::GRAPH_FAILED);

    OP_CHECK_IF(
        (CheckAxesValid() != ge::GRAPH_SUCCESS), OP_LOGE(nodeName_, "CheckAxesValid failed."),
        return ge::GRAPH_FAILED);

    return ge::GRAPH_SUCCESS;
}

bool ResizeBilinearV2GradTilingAscendC::IsMatchSimtDetermine()
{
    return (isDetermine_ || (!alignCorners_ && !halfPixelCenters_) || (gradsDtype_ != yDtype_));
}

bool ResizeBilinearV2GradTilingAscendC::IsMatchCParallel()
{
    if (yFormat_ != ge::FORMAT_NHWC || lenC_ * gradsDtypeSize_ < MIN_C_SIZE || lenC_ * yDtypeSize_ < MIN_C_SIZE) {
        return false;
    }

    return true;
}

bool ResizeBilinearV2GradTilingAscendC::IsMatchAllCopy()
{
    return (lenSrcH_ == lenDesH_ && lenSrcW_ == lenDesW_ && gradsDtype_ == yDtype_);
}

bool ResizeBilinearV2GradTilingAscendC::IsMatchPointCopy()
{
    if (gradsDtype_ != yDtype_) {
        return false;
    }
    if (yFormat_ != ge::FORMAT_NHWC || lenC_ * gradsDtypeSize_ < MIN_C_SIZE || lenC_ * yDtypeSize_ < MIN_C_SIZE) {
        return false;
    }

    if (alignCorners_) {
        if (lenDesH_ == 1 && lenDesW_ == 1) {
            return true;
        }
        if (lenDesH_ > 1 && lenDesW_ > 1 && ((lenSrcH_ - 1) % (lenDesH_ - 1) == 0) &&
            ((lenSrcW_ - 1) % (lenDesW_ - 1) == 0)) {
            return true;
        }
        return false;
    }

    if (originalScaleH_ > 0.0f || originalScaleW_ > 0.0f) {
        return false;
    }

    if (lenSrcH_ % lenDesH_ == 0 && lenSrcW_ % lenDesW_ == 0) {
        if (halfPixelCenters_) {
            if ((lenSrcH_ / lenDesH_) % EVEN_FACTOR == 1 && (lenSrcW_ / lenDesW_) % EVEN_FACTOR == 1) {
                return true;
            }
            return false;
        }
        return true;
    }

    return false;
}

void ResizeBilinearV2GradTilingAscendC::SetScales(bool isDetermine)
{
    if (alignCorners_) {
        if (isDetermine) {
            if (lenSrcH_ > 1 && lenDesH_ > 1) {
                scaleH_ = static_cast<float>(lenSrcH_ - 1) / static_cast<float>(lenDesH_ - 1);
            } else {
                scaleH_ = static_cast<float>(lenSrcH_) / lenDesH_;
            }
            if (lenSrcW_ > 1 && lenDesW_ > 1) {
                scaleW_ = static_cast<float>(lenSrcW_ - 1) / static_cast<float>(lenDesW_ - 1);
            } else {
                scaleW_ = static_cast<float>(lenSrcW_) / lenDesW_;
            }
        } else {
            if (lenDesH_ > 1) {
                scaleH_ = static_cast<float>(lenSrcH_ - 1) / static_cast<float>(lenDesH_ - 1);
            } else {
                scaleH_ = 0.0f;
            }
            if (lenDesW_ > 1) {
                scaleW_ = static_cast<float>(lenSrcW_ - 1) / static_cast<float>(lenDesW_ - 1);
            } else {
                scaleW_ = 0.0f;
            }
        }
    } else {
        if (originalScaleH_ > 0.0f) {
            scaleH_ = 1.0f / originalScaleH_;
        } else {
            scaleH_ = static_cast<float>(lenSrcH_) / lenDesH_;
        }
        if (originalScaleW_ > 0.0f) {
            scaleW_ = 1.0f / originalScaleW_;
        } else {
            scaleW_ = static_cast<float>(lenSrcW_) / lenDesW_;
        }
    }
    if (isDetermine) {
        inverseScaleH_ = 1.0f / scaleH_;
        inverseScaleW_ = 1.0f / scaleW_;
    }
}

void ResizeBilinearV2GradTilingAscendC::SetFactors()
{
    nFactor_ = lenN_;
    hFactor_ = lenDesH_;
    wFactor_ = lenDesW_;
    cFactor_ = lenC_;
    hwFactor_ = lenDesH_ * lenDesW_;
    ubNFactor_ = nFactor_;
    ubHFactor_ = hFactor_;
    ubWFactor_ = wFactor_;
    ubCFactor_ = cFactor_;
    ubHWFactor_ = hwFactor_;

    isAlign_ = false;
    if ((lenC_ * gradsDtypeSize_) % ONE_BLOCK_SIZE == 0) {
        isAlign_ = true;
    }
    lenCAlign_ = Ops::Base::CeilAlign(lenC_ * gradsDtypeSize_, ONE_BLOCK_SIZE) / gradsDtypeSize_;
}

void ResizeBilinearV2GradTilingAscendC::SetSimtTilingKey(bool isDetermine)
{
    int64_t ySize_ = lenN_ * lenC_ * lenDesH_ * lenDesW_;
    int64_t xSize_ = lenN_ * lenC_ * lenSrcH_ * lenSrcW_;
    bool isIdx32 = ySize_ < UINT32_MAX && xSize_ < UINT32_MAX && lenSrcH_ <= INT32_MAX && lenSrcW_ <= INT32_MAX &&
                   lenDesH_ <= INT32_MAX && lenDesW_ <= INT32_MAX;
    if ((isDetermine && alignCorners_) ||
        (isDetermine && !alignCorners_ &&
         (std::fabs(static_cast<float>(lenSrcH_) / lenDesH_ - scaleH_) < FLT_EPSILON) &&
         (std::fabs(static_cast<float>(lenSrcW_) / lenDesW_ - scaleW_) < FLT_EPSILON))) {
        if (yFormat_ == ge::FORMAT_NCHW) {
            tilingKey_ = isIdx32 ? TILING_KEY_SIMT_NCHW_DETERMINE : TILING_KEY_SIMT_NCHW_DETERMINE_IDX64;
        } else {
            tilingKey_ = isIdx32 ? TILING_KEY_SIMT_NHWC_DETERMINE : TILING_KEY_SIMT_NHWC_DETERMINE_IDX64;
        }
    } else if (isDetermine && !alignCorners_) {
        if (yFormat_ == ge::FORMAT_NCHW) {
            tilingKey_ = isIdx32 ? TILING_KEY_SIMT_NCHW_DETERMINE_SCALES : TILING_KEY_SIMT_NCHW_DETERMINE_SCALES_IDX64;
        } else {
            tilingKey_ = isIdx32 ? TILING_KEY_SIMT_NHWC_DETERMINE_SCALES : TILING_KEY_SIMT_NHWC_DETERMINE_SCALES_IDX64;
        }
    } else {
        if (yFormat_ == ge::FORMAT_NCHW) {
            tilingKey_ = isIdx32 ? TILING_KEY_SIMT_NCHW : TILING_KEY_SIMT_NCHW_IDX64;
        } else {
            tilingKey_ = isIdx32 ? TILING_KEY_SIMT_NHWC : TILING_KEY_SIMT_NHWC_IDX64;
        }
    }
}

void ResizeBilinearV2GradTilingAscendC::SetTilingKey()
{
    if (IsMatchAllCopy()) {
        tilingKey_ = TILING_KEY_ALL_COPY;
        return;
    }
    if (IsMatchPointCopy()) {
        tilingKey_ = TILING_KEY_POINT_COPY;
        return;
    }

    if (IsMatchSimtDetermine()) {
        SetSimtTilingKey(true);
    } else {
        if (IsMatchCParallel()) {
            tilingKey_ = TILING_KEY_C_PARALLEL;
            return;
        }
        if ((scaleH_ > 0.0f && scaleH_ < 1.0f) || (scaleW_ > 0.0f && scaleW_ < 1.0f)) {
            SetSimtTilingKey(true);
            SetScales(true);
        } else {
            SetSimtTilingKey(false);
        }
    }
}

void ResizeBilinearV2GradTilingAscendC::DoTilingInitY()
{
    isNeedInitY_ = true;
    initYRealCoreNum_ = (yShape_.GetShapeSize() < coreNum_) ? yShape_.GetShapeSize() : coreNum_;
    initYSplitBlockFactor_ = Ops::Base::FloorDiv(yShape_.GetShapeSize(), initYRealCoreNum_);
    initYSplitBlockTailFactor_ = yShape_.GetShapeSize() - initYSplitBlockFactor_ * initYRealCoreNum_;
}

void ResizeBilinearV2GradTilingAscendC::DoTilingAllCopy()
{
    realCoreNum_ = (yShape_.GetShapeSize() < coreNum_) ? yShape_.GetShapeSize() : coreNum_;
    splitBlockFactor_ = Ops::Base::FloorDiv(yShape_.GetShapeSize(), realCoreNum_);
    splitBlockTailFactor_ = yShape_.GetShapeSize() - splitBlockFactor_ * realCoreNum_;
    ubCFactor_ = ubBlockNum_ / DB_BUFF_NUM * ONE_BLOCK_SIZE / yDtypeSize_;
}

int64_t ResizeBilinearV2GradTilingAscendC::FindBest2DTiling(int64_t lenM, int64_t lenN)
{
    int64_t bestM = 1;
    int64_t bestN = coreNum_ / bestM;

    int64_t bestDelta = lenM * lenN;
    if (bestDelta <= coreNum_) {
        return lenM;
    }

    for (int64_t m = 1; m <= coreNum_; m++) {
        int64_t n = coreNum_ / m;

        if (m > lenM || n > lenN) {
            continue;
        }

        int64_t mFactor = Ops::Base::CeilDiv(lenM, m);
        int64_t nFactor = Ops::Base::CeilDiv(lenN, n);

        int64_t delta = mFactor * nFactor;
        if (m * n == coreNum_) {
            if (lenM % m == 0 && lenN % n == 0) {
                delta = 0;
            } else if (lenM % m == 0) {
                delta = delta - mFactor * (lenN % nFactor);
            } else if (lenN % n == 0) {
                delta = delta - (lenM % mFactor) * nFactor;
            } else {
                delta = delta - (lenM % mFactor) * (lenN % nFactor);
            }
        }

        if (delta < bestDelta || (delta == bestDelta && n < bestN)) {
            bestM = m;
            bestN = n;
            bestDelta = delta;
        }
    }

    return bestM;
}

void ResizeBilinearV2GradTilingAscendC::DoTilingPointCopy()
{
    int64_t np = FindBest2DTiling(lenN_, lenDesH_);
    nFactor_ = Ops::Base::CeilDiv(lenN_, np);

    int64_t hp = coreNum_ / np;
    hFactor_ = Ops::Base::CeilDiv(lenDesH_, hp);

    realCoreNum_ = Ops::Base::CeilDiv(lenN_, nFactor_) * Ops::Base::CeilDiv(lenDesH_, hFactor_);
    if (realCoreNum_ <= coreNum_ / EVEN_FACTOR) {
        wFactor_ = Ops::Base::CeilDiv(lenDesW_, coreNum_ / realCoreNum_);
        realCoreNum_ *= Ops::Base::CeilDiv(lenDesW_, wFactor_);
    }

    if (realCoreNum_ <= coreNum_ / EVEN_FACTOR) {
        cFactor_ = Ops::Base::CeilDiv(lenC_, coreNum_ / realCoreNum_);
        realCoreNum_ *= Ops::Base::CeilDiv(lenC_, cFactor_);
    }
    realCoreNum_ = std::min(realCoreNum_, coreNum_);

    // UB divide
    int64_t wcLenAlign = Ops::Base::CeilAlign(wFactor_ * cFactor_, ONE_BLOCK_SIZE / gradsDtypeSize_);
    int64_t vol4AxisC = (ubBlockNum_ / DB_BUFF_NUM) * ONE_BLOCK_SIZE / gradsDtypeSize_;
    if (vol4AxisC < cFactor_) {
        ubNFactor_ = 1;
        ubHFactor_ = 1;
        ubWFactor_ = 1;
        ubCFactor_ = vol4AxisC;
    } else if (vol4AxisC < wcLenAlign) {
        ubNFactor_ = 1;
        ubHFactor_ = 1;
        ubWFactor_ = vol4AxisC / cFactor_;
        ubCFactor_ = cFactor_;
    } else if (vol4AxisC < hFactor_ * wcLenAlign) {
        ubNFactor_ = 1;
        ubHFactor_ = vol4AxisC / (wcLenAlign);
        ubWFactor_ = wFactor_;
        ubCFactor_ = cFactor_;
    } else {
        ubNFactor_ = vol4AxisC / (hFactor_ * wcLenAlign);
        ubHFactor_ = hFactor_;
        ubWFactor_ = wFactor_;
        ubCFactor_ = cFactor_;
    }

    DoTilingInitY();
}

void ResizeBilinearV2GradTilingAscendC::DoTilingCParallel()
{
    int64_t totalLen = lenDesH_ * lenDesW_;

    if (totalLen * lenN_ <= coreNum_) {
        int64_t tileNum = coreNum_ / (totalLen * lenN_);
        hwFactor_ = 1;
        nFactor_ = 1;
        cFactor_ = Ops::Base::CeilDiv(lenC_, tileNum);
        realCoreNum_ = totalLen * lenN_ * Ops::Base::CeilDiv(lenC_, cFactor_);
    } else if (totalLen <= coreNum_) {
        int64_t tileNum = coreNum_ / totalLen;
        hwFactor_ = 1;
        nFactor_ = Ops::Base::CeilDiv(lenN_, tileNum);
        cFactor_ = lenC_;
        realCoreNum_ = totalLen * Ops::Base::CeilDiv(lenN_, nFactor_);
    } else {
        hwFactor_ = Ops::Base::CeilDiv(totalLen, coreNum_);
        nFactor_ = lenN_;
        cFactor_ = lenC_;
        realCoreNum_ = Ops::Base::CeilDiv(totalLen, hwFactor_);
    }

    realCoreNum_ = std::min(realCoreNum_, coreNum_);

    int64_t gradsTensorSize = C_PARALLEL_GRADS_TENSOR_NUM * gradsDtypeSize_;
    int64_t yTensorSize = C_PARALLEL_Y_TENSOR_NUM * yDtypeSize_;
    int64_t vol4AxisC = ((ubBlockNum_ / DB_BUFF_NUM) * ONE_BLOCK_SIZE) / (gradsTensorSize + yTensorSize);
    int64_t align32LenC = Ops::Base::CeilDiv(lenC_, ONE_BLOCK_SIZE) * ONE_BLOCK_SIZE;
    if (vol4AxisC < align32LenC) {
        ubNFactor_ = 1;
        ubCFactor_ = vol4AxisC;
    } else {
        ubNFactor_ = vol4AxisC / align32LenC;
        ubNFactor_ = (ubNFactor_ < nFactor_) ? ubNFactor_ : nFactor_;
        ubCFactor_ = lenC_;
    }

    DoTilingInitY();
}

void ResizeBilinearV2GradTilingAscendC::DoTilingSimtDetermine()
{
    realCoreNum_ = (yShape_.GetShapeSize() < coreNum_) ? yShape_.GetShapeSize() : coreNum_;
    splitBlockFactor_ = Ops::Base::FloorDiv(yShape_.GetShapeSize(), realCoreNum_);
    splitBlockTailFactor_ = yShape_.GetShapeSize() - splitBlockFactor_ * realCoreNum_;
}

void ResizeBilinearV2GradTilingAscendC::DoTilingSimtNotDetermine()
{
    DoTilingInitY();

    realCoreNum_ = (gradsShape_.GetShapeSize() < coreNum_) ? gradsShape_.GetShapeSize() : coreNum_;
    splitBlockFactor_ = Ops::Base::FloorDiv(gradsShape_.GetShapeSize(), realCoreNum_);
    splitBlockTailFactor_ = gradsShape_.GetShapeSize() - splitBlockFactor_ * realCoreNum_;
}

void ResizeBilinearV2GradTilingAscendC::DoTilingStrategy()
{
    SetTilingKey();
    switch (tilingKey_) {
        case TILING_KEY_ALL_COPY:
            DoTilingAllCopy();
            break;
        case TILING_KEY_POINT_COPY:
            DoTilingPointCopy();
            break;
        case TILING_KEY_C_PARALLEL:
            DoTilingCParallel();
            break;
        case TILING_KEY_SIMT_NCHW:
        case TILING_KEY_SIMT_NHWC:
        case TILING_KEY_SIMT_NCHW_IDX64:
        case TILING_KEY_SIMT_NHWC_IDX64:
            DoTilingSimtNotDetermine();
            break;
        case TILING_KEY_SIMT_NCHW_DETERMINE:
        case TILING_KEY_SIMT_NHWC_DETERMINE:
        case TILING_KEY_SIMT_NCHW_DETERMINE_SCALES:
        case TILING_KEY_SIMT_NHWC_DETERMINE_SCALES:
        case TILING_KEY_SIMT_NCHW_DETERMINE_IDX64:
        case TILING_KEY_SIMT_NHWC_DETERMINE_IDX64:
        case TILING_KEY_SIMT_NCHW_DETERMINE_SCALES_IDX64:
        case TILING_KEY_SIMT_NHWC_DETERMINE_SCALES_IDX64:
            DoTilingSimtDetermine();
            break;
        default:
            break;
    }
}

void ResizeBilinearV2GradTilingAscendC::FillTilingData()
{
    tilingData_.set_tilingKey(tilingKey_);
    tilingData_.set_ubSize(ubSize_);
    tilingData_.set_alignCorners(alignCorners_);
    tilingData_.set_halfPixelCenters(halfPixelCenters_);
    tilingData_.set_lenN(lenN_);
    tilingData_.set_lenC(lenC_);
    tilingData_.set_lenSrcH(lenSrcH_);
    tilingData_.set_lenSrcW(lenSrcW_);
    tilingData_.set_lenDesH(lenDesH_);
    tilingData_.set_lenDesW(lenDesW_);
    tilingData_.set_nFactor(nFactor_);
    tilingData_.set_hFactor(hFactor_);
    tilingData_.set_wFactor(wFactor_);
    tilingData_.set_cFactor(cFactor_);
    tilingData_.set_hwFactor(hwFactor_);
    tilingData_.set_ubNFactor(ubNFactor_);
    tilingData_.set_ubHFactor(ubHFactor_);
    tilingData_.set_ubWFactor(ubWFactor_);
    tilingData_.set_ubCFactor(ubCFactor_);
    tilingData_.set_ubHWFactor(ubHWFactor_);
    tilingData_.set_scaleH(scaleH_);
    tilingData_.set_scaleW(scaleW_);
    tilingData_.set_inverseScaleH(inverseScaleH_);
    tilingData_.set_inverseScaleW(inverseScaleW_);
    tilingData_.set_initYRealCoreNum(initYRealCoreNum_);
    tilingData_.set_initYSplitBlockFactor(initYSplitBlockFactor_);
    tilingData_.set_initYSplitBlockTailFactor(initYSplitBlockTailFactor_);
    tilingData_.set_realCoreNum(realCoreNum_);
    tilingData_.set_splitBlockFactor(splitBlockFactor_);
    tilingData_.set_splitBlockTailFactor(splitBlockTailFactor_);

    tilingData_.SaveToBuffer(context_->GetRawTilingData()->GetData(), context_->GetRawTilingData()->GetCapacity());
    context_->GetRawTilingData()->SetDataSize(tilingData_.GetDataSize());
}

void ResizeBilinearV2GradTilingAscendC::PrintTilingData()
{
    OP_LOGI(
        nodeName_,
        "tilingData is tilingKey:%ld, halfPixelCenters:%ld, lenN:%ld, lenC:%ld, lenSrcH:%ld, lenSrcW:%ld, "
        "lenDesH:%ld, lenDesW:%ld, scaleH:%f, scaleW:%f, inverseScaleH:%f, inverseScaleW:%f, initYRealCoreNum:%ld, "
        "initYSplitBlockFactor:%ld, initYSplitBlockTailFactor:%ld, realCoreNum:%ld, splitBlockFactor:%ld, "
        "splitBlockTailFactor:%ld",
        tilingData_.get_tilingKey(), tilingData_.get_halfPixelCenters(), tilingData_.get_lenN(), tilingData_.get_lenC(),
        tilingData_.get_lenSrcH(), tilingData_.get_lenSrcW(), tilingData_.get_lenDesH(), tilingData_.get_lenDesW(),
        tilingData_.get_scaleH(), tilingData_.get_scaleW(), tilingData_.get_inverseScaleH(),
        tilingData_.get_inverseScaleW(), tilingData_.get_initYRealCoreNum(), tilingData_.get_initYSplitBlockFactor(),
        tilingData_.get_initYSplitBlockTailFactor(), tilingData_.get_realCoreNum(), tilingData_.get_splitBlockFactor(),
        tilingData_.get_splitBlockTailFactor());
}

ge::graphStatus ResizeBilinearV2GradTilingAscendC::Init(const ResizeBilinearV2GradCompileInfo* compileInfo)
{
    OP_LOGD(nodeName_, "Enter ResizeBilinearV2GradTilingAscendC init.");

    OP_CHECK_IF(
        (GetPlatformInfo(compileInfo) != ge::GRAPH_SUCCESS), OP_LOGE(nodeName_, "GetPlatformInfo failed."),
        return ge::GRAPH_FAILED);

    OP_CHECK_IF(
        (GetTensorInfo() != ge::GRAPH_SUCCESS), OP_LOGE(nodeName_, "GetTensorInfo failed."), return ge::GRAPH_FAILED);

    OP_CHECK_IF(
        (GetAttrInfo() != ge::GRAPH_SUCCESS), OP_LOGE(nodeName_, "GetAttrInfo failed."), return ge::GRAPH_FAILED);

    OP_CHECK_IF(
        (CheckDtypeValid() != ge::GRAPH_SUCCESS), OP_LOGE(nodeName_, "CheckDtypeValid failed."),
        return ge::GRAPH_FAILED);

    OP_CHECK_IF(
        (CheckFormatValid() != ge::GRAPH_SUCCESS), OP_LOGE(nodeName_, "CheckFormatValid failed."),
        return ge::GRAPH_FAILED);

    OP_CHECK_IF(
        (CheckShapeValid() != ge::GRAPH_SUCCESS), OP_LOGE(nodeName_, "CheckShapeValid failed."),
        return ge::GRAPH_FAILED);

    SetScales(IsMatchSimtDetermine());

    SetFactors();

    OP_LOGD(nodeName_, "Exit ResizeBilinearV2GradTilingAscendC init.");
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBilinearV2GradTilingAscendC::DoTiling()
{
    OP_LOGD(nodeName_, "Enter ResizeBilinearV2GradTilingAscendC DoTiling");

    DoTilingStrategy();
    FillTilingData();
    PrintTilingData();

    context_->SetBlockDim(realCoreNum_);
    if (isNeedInitY_ && realCoreNum_ < initYRealCoreNum_) {
        context_->SetBlockDim(initYRealCoreNum_);
    }

    context_->SetTilingKey(tilingKey_);
    context_->SetScheduleMode(1);
    size_t* workspaces = context_->GetWorkspaceSizes(1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, workspaces);
    workspaces[0] = WORKSPACE_SIZE;
    OP_LOGD(nodeName_, "Exit ResizeBilinearV2GradTilingAscendC DoTiling.");
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus Tiling4ResizeBilinearV2GradAscendC(gert::TilingContext* context)
{
    OP_LOGD(context->GetNodeName(), "Start Tiling4ResizeBilinearV2GradAscendC.");
    auto compileInfo = reinterpret_cast<const ResizeBilinearV2GradCompileInfo*>(context->GetCompileInfo());
    ResizeBilinearV2GradTilingAscendC tilingImpl = ResizeBilinearV2GradTilingAscendC(context);
    if (tilingImpl.Init(compileInfo) != ge::GRAPH_SUCCESS) {
        OP_LOGE(context->GetNodeName(), "Tiling4ResizeBilinearV2GradAscendC init failed.");
        return ge::GRAPH_FAILED;
    }
    if (tilingImpl.DoTiling() != ge::GRAPH_SUCCESS) {
        OP_LOGE(context->GetNodeName(), "Tiling4ResizeBilinearV2GradAscendC do tiling failed.");
        return ge::GRAPH_FAILED;
    }

    OP_LOGD(context->GetNodeName(), "End Tiling4ResizeBilinearV2GradAscendC.");
    return ge::GRAPH_SUCCESS;
}

static ge::graphStatus TilingPrepare4ResizeBilinearV2GradAscendC(gert::TilingParseContext* context)
{
    OP_LOGD(context->GetNodeName(), "Start TilingPrepare4ResizeBilinearV2GradAscendC.");
    auto compileInfo = context->GetCompiledInfo<ResizeBilinearV2GradCompileInfo>();
    auto platformInfo = context->GetPlatformInfo();
    OP_CHECK_NULL_WITH_CONTEXT(context, platformInfo);
    auto ascendcPlatform = platform_ascendc::PlatformAscendC(platformInfo);

    compileInfo->coreNum = ascendcPlatform.GetCoreNumAiv();
    OP_CHECK_IF(
        compileInfo->coreNum <= 0, OP_LOGE(context->GetNodeName(), "get aiv core num failed."),
        return ge::GRAPH_FAILED);

    uint64_t ubSize = 0;
    ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::UB, ubSize);
    compileInfo->ubSize = static_cast<int32_t>(ubSize);
    OP_CHECK_IF(
        compileInfo->ubSize <= 0, OP_LOGE(context->GetNodeName(), "get ub size failed."), return ge::GRAPH_FAILED);

    OP_LOGI(context->GetNodeName(), "coreNum is %d, ubSize is %d", compileInfo->coreNum, compileInfo->ubSize);

    return ge::GRAPH_SUCCESS;
}

IMPL_OP_OPTILING(ResizeBilinearV2Grad)
    .Tiling(Tiling4ResizeBilinearV2GradAscendC)
    .TilingParse<ResizeBilinearV2GradCompileInfo>(TilingPrepare4ResizeBilinearV2GradAscendC);
} // namespace optiling
