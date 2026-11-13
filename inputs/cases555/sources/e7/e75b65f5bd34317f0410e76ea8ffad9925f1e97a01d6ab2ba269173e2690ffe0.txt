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
 * \file resize_bicubic_v2_tiling_arch35.cpp
 * \brief resize_bicubic_v2_tiling_arch35
 */
#include "resize_bicubic_v2_tiling_arch35.h"
#include "register/op_impl_registry.h"
#include "log/log.h"
#include "util/math_util.h"
#include "op_host/tiling_util.h"
#include "image/resize_bicubic_v2/op_kernel/arch35/resize_bicubic_v2_tiling_key.h"

namespace optiling {
constexpr size_t WORK_SPACE_SIZE = static_cast<size_t>(16 * 1024 * 1024);
constexpr size_t INPUT_X_IDX = 0;
constexpr size_t OUTPUT_Y_IDX = 0;
static const uint64_t DIM_0 = 0;
static const uint64_t DIM_1 = 1;
static const uint64_t NUM_2 = 2;
static const int32_t DIM_2 = 2;
static const uint64_t DIM_3 = 3;
static const uint64_t DIM_4 = 4;
static const uint64_t DIM_5 = 5; // simd all copy
static const uint64_t DIM_6 = 6; // simd point copy
static const int64_t ONE_BLOCK_SIZE = 32;
static const int64_t RSV_BLOCK_NUM = 8;
static const int32_t EVEN_FACTOR = 2;
static const int64_t DB_BUFF_NUM = 2;
static const int64_t MIN_C_SIZE = 128;
static const int64_t N_DIM_IDX = 0;
static const int64_t C_DIM_IDX_NCHW = 1;
static const int64_t H_DIM_IDX_NCHW = 2;
static const int64_t W_DIM_IDX_NCHW = 3;
static const int64_t H_DIM_IDX_NHWC = 1;
static const int64_t W_DIM_IDX_NHWC = 2;
static const int64_t C_DIM_IDX_NHWC = 3;
static const float_t FLT_EPSILON = 1e-6;
class ResizeBicubicV2Tiling {
public:
    explicit ResizeBicubicV2Tiling(gert::TilingContext* context) : context_(context) {};
    void GetPlatformData(const ResizeBicubicV2CompileInfo* compileInfo);
    ge::graphStatus Compute();
    ge::graphStatus CheckParams();
    ge::graphStatus CheckShapeDimValid();
    ge::graphStatus CheckFormatValid();
    ge::graphStatus ExtractDimsFromShape();
    ge::graphStatus CheckDimsValid();
    ge::graphStatus GetInputSize();
    float ComputeScale(float scale, int64_t lenSrc, int64_t lenDes);
    ge::graphStatus SetTilingData();
    ge::graphStatus CheckDtype();
    void PrintTilingData();
    void ComputeKey();
    void SetDimsByFormat();
    void DoTilingPointCopy();
    bool IsMatchPointCopy(bool isIntScaleH, bool isIntScaleW, bool oddScales);
    bool IsMatchAllCopy();
    int64_t FindBest2DTiling(int64_t lenM, int64_t lenN);
    void DoTilingKeyPostProcess();

private:
    ResizeBicubicV2TilingData tilingData_;
    gert::TilingContext* context_ = nullptr;
    int32_t xDtypeSize_ = 0;
    int32_t yDtypeSize_ = 0;
    uint64_t schId_ = 0;
    uint64_t isInt32_ = 0;
    uint64_t isHalfPiex_ = 0;
    uint64_t isNchw_ = 0;
    int64_t coreNum_ = 0;
    int64_t ubSize_ = 0;
    int64_t ubBlockNum_ = 0;
    int32_t alignCorners_ = 0;
    int64_t realCoreNum_ = 0;
    int64_t blkProcessNum_ = 0;
    int64_t splitBlockTailFactor_ = 0;
    int64_t lenSrcH_ = 0;
    int64_t lenSrcW_ = 0;
    int64_t lenDesH_ = 0;
    int64_t lenDesW_ = 0;
    float scaleH_ = 0.0f;
    float scaleW_ = 0.0f;
    int64_t lenC_ = 0;
    int64_t lenN_ = 0;
    int64_t ySize_ = 0;
    int64_t xSize_ = 0;

    int64_t nFactor_ = 0;
    int64_t hFactor_ = 0;
    int64_t wFactor_ = 0;
    int64_t cFactor_ = 0;

    int64_t ubNFactor_ = 0;
    int64_t ubHFactor_ = 0;
    int64_t ubWFactor_ = 0;
    int64_t ubCFactor_ = 0;
    int64_t lenCAlign_ = 0;
    bool isAlign_ = false;

    ge::DataType xDtype_ = ge::DT_MAX;
    ge::DataType yDtype_ = ge::DT_MAX;
    ge::Format dataFormat = ge::FORMAT_MAX;
    gert::Shape xShape_;
    gert::Shape yShape_;
};

ge::graphStatus ResizeBicubicV2Tiling::GetInputSize()
{
    auto size = context_->GetInputShape(DIM_1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, size);
    gert::Shape sizeShape = size->GetStorageShape();
    int32_t sizeElms = sizeShape.GetShapeSize();
    OP_CHECK_IF(sizeElms != DIM_2,
                OP_LOGE_FOR_INVALID_SHAPESIZE(context_->GetNodeName(), "size", std::to_string(sizeElms).c_str(),
                                              std::to_string(DIM_2).c_str()),
                return ge::GRAPH_FAILED);
    const gert::Tensor* sizeTensor = context_->GetInputTensor(DIM_1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, sizeTensor);
    OP_CHECK_IF(sizeTensor->GetDataType() != ge::DT_INT32,
                OP_LOGE_FOR_INVALID_DTYPE(context_->GetNodeName(), "size",
                                          Ops::Base::ToString(sizeTensor->GetDataType()).c_str(), "int32"),
                return ge::GRAPH_FAILED);
    std::vector<int64_t> sizeList;
    sizeList.resize(DIM_2);
    auto* tensorData = sizeTensor->GetData<int32_t>();
    OP_CHECK_IF(tensorData == nullptr, OP_LOGE(context_->GetNodeName(), "GetData failed, tensorData is nullptr"),
                return ge::GRAPH_FAILED);

    for (int32_t i = 0; i < DIM_2; i++) {
        sizeList[i] = static_cast<int64_t>(*(tensorData + i));
    }
    if ((sizeList[0] != lenDesH_) || (sizeList[1] != lenDesW_)) {
        std::string sizeTensorDatas = "(" + std::to_string(sizeList[0]) + ", " + std::to_string(sizeList[1]) + ")";
        std::string reasonMsg = "The value of input size must be (H, W) - (" + std::to_string(lenDesH_) + ", " +
                                std::to_string(lenDesW_) +
                                "), where H and W are inferred from the 4D shape "
                                "of output y based on its format: axes 2/3 for NCHW, or axes 1/2 for NHWC";
        OP_LOGE_FOR_INVALID_VALUE_WITH_REASON(context_->GetNodeName(), "size", sizeTensorDatas.c_str(),
                                              reasonMsg.c_str());
        return ge::GRAPH_FAILED;
    }

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBicubicV2Tiling::CheckDtype()
{
    auto inputDesc = context_->GetInputDesc(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, inputDesc);
    auto outputDesc = context_->GetOutputDesc(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, outputDesc);
    xDtype_ = inputDesc->GetDataType();
    yDtype_ = outputDesc->GetDataType();
    xDtypeSize_ = GetSizeByDataType(xDtype_);
    yDtypeSize_ = GetSizeByDataType(yDtype_);
    if (xDtypeSize_ <= 0 || yDtypeSize_ <= 0) {
        std::string dtypeMsg = Ops::Base::ToString(xDtype_) + " and " + Ops::Base::ToString(yDtype_);
        OP_LOGE_FOR_INVALID_DTYPES_WITH_REASON(context_->GetNodeName(), "x and y", dtypeMsg.c_str(),
                                               "The dtype sizes of input x and output y must be greater than zero");
        return ge::GRAPH_FAILED;
    }
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBicubicV2Tiling::CheckShapeDimValid()
{
    auto images = context_->GetInputShape(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, images);
    gert::Shape imagesShape = images->GetStorageShape();
    auto y = context_->GetOutputShape(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, y);
    gert::Shape yShape = y->GetStorageShape();
    if (imagesShape.GetDimNum() != DIM_4 || yShape.GetDimNum() != DIM_4) {
        std::string dimMsg = std::to_string(imagesShape.GetDimNum()) + " and " + std::to_string(yShape.GetDimNum());
        OP_LOGE_FOR_INVALID_SHAPEDIMS_WITH_REASON(context_->GetNodeName(), "x and y", dimMsg.c_str(),
                                                  "The shapes of input x and output y must be 4D");
        return ge::GRAPH_FAILED;
    }

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBicubicV2Tiling::CheckFormatValid()
{
    auto inputDesc = context_->GetInputDesc(DIM_0);
    auto outputDesc = context_->GetOutputDesc(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, inputDesc);
    OP_CHECK_NULL_WITH_CONTEXT(context_, outputDesc);

    dataFormat = static_cast<ge::Format>(ge::GetPrimaryFormat(inputDesc->GetStorageFormat()));
    ge::Format outFormat = static_cast<ge::Format>(ge::GetPrimaryFormat(outputDesc->GetStorageFormat()));
    if (dataFormat != outFormat) {
        std::string formatMsg = Ops::Base::ToString(dataFormat) + " and " + Ops::Base::ToString(outFormat);
        OP_LOGE_FOR_INVALID_FORMATS_WITH_REASON(context_->GetNodeName(), "x and y", formatMsg.c_str(),
                                                "The formats of input x and output y must be the same");
        return ge::GRAPH_FAILED;
    }

    OP_CHECK_IF(((dataFormat != ge::FORMAT_NCHW) && (dataFormat != ge::FORMAT_NHWC) && (dataFormat != ge::FORMAT_ND)),
                OP_LOGE_FOR_INVALID_FORMAT(context_->GetNodeName(), "x", Ops::Base::ToString(dataFormat).c_str(),
                                           "NCHW, NHWC and ND"),
                return ge::GRAPH_FAILED);

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBicubicV2Tiling::ExtractDimsFromShape()
{
    auto images = context_->GetInputShape(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, images);
    gert::Shape imagesShape = images->GetStorageShape();
    auto y = context_->GetOutputShape(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, y);
    gert::Shape yShape = y->GetStorageShape();

    int64_t cDim = dataFormat == ge::FORMAT_NHWC ? DIM_3 : DIM_1;
    int64_t hDim = dataFormat == ge::FORMAT_NHWC ? DIM_1 : NUM_2;
    int64_t wDim = dataFormat == ge::FORMAT_NHWC ? NUM_2 : DIM_3;

    lenDesH_ = yShape.GetDim(hDim);
    lenDesW_ = yShape.GetDim(wDim);
    lenSrcH_ = imagesShape.GetDim(hDim);
    lenSrcW_ = imagesShape.GetDim(wDim);
    lenC_ = imagesShape.GetDim(cDim);
    lenN_ = imagesShape.GetDim(DIM_0);

    ySize_ = yShape.GetShapeSize();
    xSize_ = imagesShape.GetShapeSize();

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBicubicV2Tiling::CheckDimsValid()
{
    auto images = context_->GetInputShape(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, images);
    gert::Shape imagesShape = images->GetStorageShape();
    auto y = context_->GetOutputShape(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, y);
    gert::Shape yShape = y->GetStorageShape();
    int64_t cDim = dataFormat == ge::FORMAT_NHWC ? DIM_3 : DIM_1;

    if (lenDesH_ <= 0 || lenDesW_ <= 0 || lenSrcH_ <= 0 || lenSrcW_ <= 0) {
        std::string shapeMsg = Ops::Base::ToString(imagesShape) + " and " + Ops::Base::ToString(yShape);
        std::string reasonMsg = "The H-dimensions and W-dimensions of x and y must be greater than 0, "
                                "where H and W are inferred from the 4D shapes of input x and output y "
                                "based on their formats: axes 2/3 for NCHW, or axes 1/2 for NHWC";
        OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(context_->GetNodeName(), "x and y", shapeMsg.c_str(), reasonMsg.c_str());
        return ge::GRAPH_FAILED;
    }

    if (lenC_ <= 0 || lenN_ <= 0) {
        std::string reasonMsg = "The C-dimension and N-dimension of input x must be greater than 0, "
                                "where C is inferred from the 4D shape of input x based on its format "
                                "(axis 1 for NCHW, axis 3 for NHWC), and N is the size of axis 0";
        OP_LOGE_FOR_INVALID_SHAPE_WITH_REASON(context_->GetNodeName(), "x", Ops::Base::ToString(imagesShape).c_str(),
                                              reasonMsg.c_str());
        return ge::GRAPH_FAILED;
    }

    if (lenN_ != yShape.GetDim(DIM_0) || lenC_ != yShape.GetDim(cDim)) {
        std::string shapeMsg = Ops::Base::ToString(imagesShape) + " and " + Ops::Base::ToString(yShape);
        std::string reasonMsg = "The C-dimensions and N-dimensions of x and y must be the same, "
                                "where C is inferred from the 4D shape of x/y combined with their format "
                                "(axis 1 for NCHW, axis 3 for NHWC), and N is the size of axis 0 of x/y";
        OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(context_->GetNodeName(), "x and y", shapeMsg.c_str(), reasonMsg.c_str());
        return ge::GRAPH_FAILED;
    }

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBicubicV2Tiling::CheckParams()
{
    OP_CHECK_IF((CheckShapeDimValid() != ge::GRAPH_SUCCESS),
                OP_LOGE(context_->GetNodeName(), "CheckShapeDimValid failed."), return ge::GRAPH_FAILED);

    OP_CHECK_IF((CheckFormatValid() != ge::GRAPH_SUCCESS), OP_LOGE(context_->GetNodeName(), "CheckFormatValid failed."),
                return ge::GRAPH_FAILED);

    OP_CHECK_IF((ExtractDimsFromShape() != ge::GRAPH_SUCCESS),
                OP_LOGE(context_->GetNodeName(), "ExtractDimsFromShape failed."), return ge::GRAPH_FAILED);

    OP_CHECK_IF((CheckDimsValid() != ge::GRAPH_SUCCESS), OP_LOGE(context_->GetNodeName(), "CheckDimsValid failed."),
                return ge::GRAPH_FAILED);

    isNchw_ = DIM_1;
    if ((dataFormat == ge::FORMAT_NHWC) && (lenDesH_ != lenSrcH_ || lenDesW_ != lenSrcW_)) {
        isNchw_ = DIM_0;
    }

    OP_CHECK_IF(GetInputSize() != ge::GRAPH_SUCCESS, OP_LOGE(context_->GetNodeName(), "get input size failed"),
                return ge::GRAPH_FAILED);

    OP_CHECK_IF(CheckDtype() != ge::GRAPH_SUCCESS, OP_LOGE(context_->GetNodeName(), "check dtype failed"),
                return ge::GRAPH_FAILED);

    SetDimsByFormat();
    return ge::GRAPH_SUCCESS;
}

int64_t ResizeBicubicV2Tiling::FindBest2DTiling(int64_t lenM, int64_t lenN)
{
    int64_t bestM = 1;
    int64_t bestN = coreNum_;

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
        OP_CHECK_IF((nFactor == 0 || mFactor == 0), OP_LOGE("FindBest2DTiling", "nFactor or mFactor is zero"),
                    return ge::GRAPH_FAILED);
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

void ResizeBicubicV2Tiling::SetDimsByFormat()
{
    auto xStorage = context_->GetInputShape(INPUT_X_IDX);
    xShape_ = Ops::Cv::OpTiling::EnsureNotScalar(xStorage->GetStorageShape());
    auto yStorage = context_->GetOutputShape(OUTPUT_Y_IDX);
    yShape_ = Ops::Cv::OpTiling::EnsureNotScalar(yStorage->GetStorageShape());
    lenN_ = xShape_.GetDim(N_DIM_IDX);

    if (dataFormat == ge::FORMAT_NCHW || dataFormat == ge::FORMAT_ND) {
        lenC_ = xShape_.GetDim(C_DIM_IDX_NCHW);
    } else {
        lenC_ = xShape_.GetDim(C_DIM_IDX_NHWC);
    }

    if (dataFormat == ge::FORMAT_NCHW || dataFormat == ge::FORMAT_ND) {
        lenSrcH_ = xShape_.GetDim(H_DIM_IDX_NCHW);
        lenDesH_ = yShape_.GetDim(H_DIM_IDX_NCHW);
        lenSrcW_ = xShape_.GetDim(H_DIM_IDX_NCHW + 1);
        lenDesW_ = yShape_.GetDim(H_DIM_IDX_NCHW + 1);
    } else {
        lenSrcH_ = xShape_.GetDim(H_DIM_IDX_NHWC);
        lenDesH_ = yShape_.GetDim(H_DIM_IDX_NHWC);
        lenSrcW_ = xShape_.GetDim(H_DIM_IDX_NHWC + 1);
        lenDesW_ = yShape_.GetDim(H_DIM_IDX_NHWC + 1);
    }

    nFactor_ = lenN_;
    hFactor_ = lenDesH_;
    wFactor_ = lenDesW_;
    cFactor_ = lenC_;
    ubNFactor_ = nFactor_;
    ubHFactor_ = hFactor_;
    ubWFactor_ = wFactor_;
    ubCFactor_ = cFactor_;
}

bool ResizeBicubicV2Tiling::IsMatchAllCopy() { return lenDesH_ == lenSrcH_ && lenDesW_ == lenSrcW_; }

bool ResizeBicubicV2Tiling::IsMatchPointCopy(bool isIntScaleH, bool isIntScaleW, bool oddScales)
{
    if (dataFormat != ge::FORMAT_NHWC) {
        return false;
    }

    if (lenC_ * xDtypeSize_ < MIN_C_SIZE) {
        return false;
    }

    if (scaleH_ < 1.0 || scaleW_ < 1.0) {
        return false;
    }
    if (alignCorners_ == 1) { // alignCorners_=true => isHalfPiex_=false
        // 整数倍缩小
        if (lenDesH_ > 1 && lenDesW_ > 1 && ((lenSrcH_ - 1) % (lenDesH_ - 1) == 0) &&
            ((lenSrcW_ - 1) % (lenDesW_ - 1) == 0)) {
            return true;
        }
        return false;
    } else {
        // 整数倍缩小，且倍数为奇数
        if (isIntScaleH && isIntScaleW && oddScales && (std::fabs(lenSrcH_ / lenDesH_ - scaleH_) < FLT_EPSILON) &&
            (std::fabs(lenSrcW_ / lenDesW_ - scaleW_) < FLT_EPSILON)) {
            return true;
        }
        return false;
    }
}

void ResizeBicubicV2Tiling::DoTilingPointCopy()
{
    // N H多核双切分
    int64_t np = FindBest2DTiling(lenN_, lenDesH_);
    nFactor_ = Ops::Base::CeilDiv(lenN_, np);
    OP_CHECK_IF((np == 0), OP_LOGE("DoTilingPointCopy", "np is zero"), return);
    int64_t hp = coreNum_ / np;
    hFactor_ = Ops::Base::CeilDiv(lenDesH_, hp);

    realCoreNum_ = Ops::Base::CeilDiv(lenN_, nFactor_) * Ops::Base::CeilDiv(lenDesH_, hFactor_);
    if (realCoreNum_ <= coreNum_ / EVEN_FACTOR) {
        wFactor_ = Ops::Base::CeilDiv(lenDesW_, coreNum_ / realCoreNum_);
        realCoreNum_ *= Ops::Base::CeilDiv(lenDesW_, wFactor_);
        cFactor_ = Ops::Base::CeilDiv(lenC_, coreNum_ / realCoreNum_);
        realCoreNum_ *= Ops::Base::CeilDiv(lenC_, cFactor_);
    }

    realCoreNum_ = std::min(realCoreNum_, coreNum_);
    OP_CHECK_IF((cFactor_ == 0), OP_LOGE("DoTilingPointCopy", "cFactor_ is zero"), return);
    // UB切分
    int64_t wcLenAlign = Ops::Base::CeilAlign(wFactor_ * cFactor_, ONE_BLOCK_SIZE / xDtypeSize_);
    int64_t vol4AxisC = (ubBlockNum_ / DB_BUFF_NUM) * ONE_BLOCK_SIZE / xDtypeSize_;
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
}

void ResizeBicubicV2Tiling::DoTilingKeyPostProcess()
{
    isInt32_ = DIM_1;
    if (ySize_ > UINT32_MAX || xSize_ > UINT32_MAX) {
        OP_LOGI(context_->GetNodeName(), "ySize or xSize is too large");
        isInt32_ = DIM_0;
    }
    if (lenSrcH_ > INT32_MAX || lenSrcW_ > INT32_MAX || lenDesH_ > INT32_MAX || lenDesW_ > INT32_MAX) {
        isInt32_ = DIM_0;
    }
    if (schId_ == DIM_5 || schId_ == DIM_6) { // simd scenario ignores isInt32_ and isNchw_ params
        isInt32_ = DIM_0;
        isNchw_ = DIM_0;
    }
}

void ResizeBicubicV2Tiling::ComputeKey()
{
    // 判断scaleL是否是1.0的整数倍
    float result0 = scaleH_ / 1.0f;
    float result1 = scaleW_ / 1.0f;
    int32_t intResult0 = static_cast<int32_t>(result0);
    int32_t intResult1 = static_cast<int32_t>(result1);
    float reconstructedA = intResult0 * 1.0f;
    float reconstructedB = intResult1 * 1.0f;
    bool isIntScaleH = std::fabs(scaleH_ - reconstructedA) < FLT_EPSILON;
    bool isIntScaleW = std::fabs(scaleW_ - reconstructedB) < FLT_EPSILON;
    OP_LOGI(context_->GetNodeName(), "isIntScaleH is %d, isIntScaleW is %d", isIntScaleH, isIntScaleW);
    bool oddScales = false;
    if (isHalfPiex_ > DIM_0 && isIntScaleH && isIntScaleW) {
        int32_t intScaleH = static_cast<int32_t>(scaleH_);
        int32_t intScaleW = static_cast<int32_t>(scaleW_);
        oddScales = (intScaleH % EVEN_FACTOR == 1) && (intScaleW % EVEN_FACTOR == 1);
        OP_LOGI(context_->GetNodeName(), "oddScales is %d, intScaleL is %d, intScaleW is %d", oddScales, intScaleH,
                intScaleW);
    }
    if (IsMatchAllCopy()) {
        ubCFactor_ = ubBlockNum_ / DB_BUFF_NUM * ONE_BLOCK_SIZE / xDtypeSize_;
        schId_ = DIM_5;
    } else if (IsMatchPointCopy(isIntScaleH, isIntScaleW, oddScales)) {
        DoTilingPointCopy();
        schId_ = DIM_6;
    } else if (lenDesH_ == lenSrcH_ && lenDesW_ == lenSrcW_) {
        schId_ = DIM_1;
    } else if (lenDesH_ == 1 && lenDesW_ == 1 && isHalfPiex_ == DIM_0) {
        schId_ = DIM_3;
    } else if (lenSrcH_ == 1 && lenSrcW_ == 1) {
        schId_ = NUM_2;
    } else if ((isHalfPiex_ == DIM_0 && isIntScaleH && isIntScaleW) || (oddScales)) {
        schId_ = DIM_4;
    } else {
        schId_ = DIM_0;
    }
    DoTilingKeyPostProcess();
}

float ResizeBicubicV2Tiling::ComputeScale(float scale, int64_t lenSrc, int64_t lenDes)
{
    float newScale = 0.0f;
    if (scale > 0.0f) {
        newScale = static_cast<float>(1.0f) / scale;
    } else {
        newScale = static_cast<float>(lenSrc) / static_cast<float>(lenDes);
    }
    return newScale;
}

ge::graphStatus ResizeBicubicV2Tiling::Compute()
{
    OP_CHECK_IF(CheckParams() != ge::GRAPH_SUCCESS, OP_LOGE(context_->GetNodeName(), "input params is check failed"),
                return ge::GRAPH_FAILED);

    // Get attrs: alignCorners
    auto attrs = context_->GetAttrs();
    OP_CHECK_NULL_WITH_CONTEXT(context_, attrs);
    const bool* alignCornersPtr = attrs->GetAttrPointer<bool>(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, alignCornersPtr);

    alignCorners_ = *alignCornersPtr ? 1 : 0;
    isHalfPiex_ = *alignCornersPtr ? DIM_0 : DIM_1;

    auto xStorage = context_->GetInputShape(INPUT_X_IDX);
    OP_CHECK_NULL_WITH_CONTEXT(context_, xStorage);
    xShape_ = Ops::Cv::OpTiling::EnsureNotScalar(xStorage->GetStorageShape());
    auto yStorage = context_->GetOutputShape(OUTPUT_Y_IDX);
    OP_CHECK_NULL_WITH_CONTEXT(context_, yStorage);
    yShape_ = Ops::Cv::OpTiling::EnsureNotScalar(yStorage->GetStorageShape());

    ubBlockNum_ = Ops::Base::CeilDiv(ubSize_, ONE_BLOCK_SIZE) - RSV_BLOCK_NUM;

    auto scales = attrs->GetAttrPointer<gert::ContinuousVector>(DIM_1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, scales);
    int64_t scalesNum = scales->GetSize();
    const float* scalesData = static_cast<const float*>(scales->GetData());
    OP_CHECK_IF(scalesNum != DIM_2,
                OP_LOGE_FOR_INVALID_LISTSIZE(context_->GetNodeName(), "scales", std::to_string(scalesNum).c_str(),
                                             std::to_string(DIM_2).c_str()),
                return ge::GRAPH_FAILED);

    scaleH_ = scalesData[DIM_0];
    scaleW_ = scalesData[DIM_1];
    OP_LOGI(context_->GetNodeName(), "ori scaleH is %f, scaleW is %f", scaleH_, scaleW_);
    realCoreNum_ = (ySize_ < coreNum_) ? ySize_ : coreNum_;
    blkProcessNum_ = Ops::Base::FloorDiv(ySize_, realCoreNum_);
    splitBlockTailFactor_ = ySize_ - blkProcessNum_ * realCoreNum_;

    if (alignCorners_ == 0) {
        scaleH_ = ComputeScale(scaleH_, lenSrcH_, lenDesH_);
        scaleW_ = ComputeScale(scaleW_, lenSrcW_, lenDesW_);
        OP_LOGI(context_->GetNodeName(), "attr new scaleH is %f, scaleW is %f", scaleH_, scaleW_);
    } else {
        scaleH_ = static_cast<float>(lenSrcH_) / static_cast<float>(lenDesH_);
        scaleW_ = static_cast<float>(lenSrcW_) / static_cast<float>(lenDesW_);
        if (lenDesH_ > 1) {
            scaleH_ = static_cast<float>(lenSrcH_ - 1) / static_cast<float>(lenDesH_ - 1);
        }
        if (lenDesW_ > 1) {
            scaleW_ = static_cast<float>(lenSrcW_ - 1) / static_cast<float>(lenDesW_ - 1);
        }
        OP_LOGI(context_->GetNodeName(), "compute scaleH is %f, scaleW  is %f", scaleH_, scaleW_);
    }
    ComputeKey();
    return ge::GRAPH_SUCCESS;
}

void ResizeBicubicV2Tiling::GetPlatformData(const ResizeBicubicV2CompileInfo* compileInfo)
{
    coreNum_ = static_cast<int64_t>(compileInfo->totalCoreNum);
    ubSize_ = static_cast<int64_t>(compileInfo->totalUbSize);
    OP_LOGI(context_->GetNodeName(), "GetPlatformData ubSize is %ld, coreNum is %ld", ubSize_, coreNum_);
    return;
}

void ResizeBicubicV2Tiling::PrintTilingData()
{
    OP_LOGI(context_->GetNodeName(),
            "ResizeBicubicV2 tilingData realCoreNum is %ld, blkProcessNum is %ld, "
            "splitBlockTailFactor is %ld, lenSrcH is %ld, lenSrcW is %ld, "
            "lenDesH is %ld, lenDesW is %ld, lenC is %ld, lenN is %ld, "
            "scaleH is %f, scaleW is %f, nFactor is %ld,  hFactor is %ld, "
            "wFactor is %ld, cFactor is %ld, ubNFactor is %ld, "
            "ubHFactor is %ld, ubWFactor is %ld,  ubCFactor is %ld",
            tilingData_.get_realCoreNum(), tilingData_.get_blkProcessNum(), tilingData_.get_splitBlockTailFactor(),
            tilingData_.get_lenSrcH(), tilingData_.get_lenSrcW(), tilingData_.get_lenDesH(), tilingData_.get_lenDesW(),
            tilingData_.get_lenC(), tilingData_.get_lenN(), tilingData_.get_scaleH(), tilingData_.get_scaleW(),
            tilingData_.get_nFactor(), tilingData_.get_hFactor(), tilingData_.get_wFactor(), tilingData_.get_cFactor(),
            tilingData_.get_ubNFactor(), tilingData_.get_ubHFactor(), tilingData_.get_ubWFactor(),
            tilingData_.get_ubCFactor());
    return;
}

ge::graphStatus ResizeBicubicV2Tiling::SetTilingData()
{
    tilingData_.set_realCoreNum(realCoreNum_);
    tilingData_.set_blkProcessNum(blkProcessNum_);
    tilingData_.set_splitBlockTailFactor(splitBlockTailFactor_);
    tilingData_.set_lenSrcH(lenSrcH_);
    tilingData_.set_lenSrcW(lenSrcW_);
    tilingData_.set_lenDesH(lenDesH_);
    tilingData_.set_lenDesW(lenDesW_);
    tilingData_.set_lenC(lenC_);
    tilingData_.set_lenN(lenN_);
    tilingData_.set_scaleH(scaleH_);
    tilingData_.set_scaleW(scaleW_);
    tilingData_.set_nFactor(nFactor_);
    tilingData_.set_hFactor(hFactor_);
    tilingData_.set_wFactor(wFactor_);
    tilingData_.set_cFactor(cFactor_);
    tilingData_.set_ubNFactor(ubNFactor_);
    tilingData_.set_ubHFactor(ubHFactor_);
    tilingData_.set_ubWFactor(ubWFactor_);
    tilingData_.set_ubCFactor(ubCFactor_);

    tilingData_.SaveToBuffer(context_->GetRawTilingData()->GetData(), context_->GetRawTilingData()->GetCapacity());
    context_->GetRawTilingData()->SetDataSize(tilingData_.GetDataSize());

    context_->SetBlockDim(realCoreNum_);
    OP_LOGI(context_->GetNodeName(), "schId is %ld, isInt32 is %ld, isHalfPiex is %ld, isNchw is %ld", schId_, isInt32_,
            isHalfPiex_, isNchw_);
    const uint64_t tilingKey = GET_TPL_TILING_KEY(schId_, isInt32_, isHalfPiex_, isNchw_);
    context_->SetTilingKey(tilingKey);

    size_t* workspaces = context_->GetWorkspaceSizes(1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, workspaces);
    workspaces[0] = WORK_SPACE_SIZE;
    PrintTilingData();
    return ge::GRAPH_SUCCESS;
}

static ge::graphStatus Tiling4ResizeBicubicV2(gert::TilingContext* context)
{
    auto compileInfo = static_cast<const ResizeBicubicV2CompileInfo*>(context->GetCompileInfo());
    OP_CHECK_NULL_WITH_CONTEXT(context, compileInfo);
    ResizeBicubicV2Tiling tilingObject(context);
    tilingObject.GetPlatformData(compileInfo);
    if (tilingObject.Compute() != ge::GRAPH_SUCCESS) {
        OP_LOGE(context->GetNodeName(), "Compute return failed.");
        return ge::GRAPH_FAILED;
    }
    if (tilingObject.SetTilingData() != ge::GRAPH_SUCCESS) {
        OP_LOGE(context->GetNodeName(), "SetTilingData return failed.");
        return ge::GRAPH_FAILED;
    }

    return ge::GRAPH_SUCCESS;
}

static ge::graphStatus TilingPrepare4ResizeBicubicV2(gert::TilingParseContext* context)
{
    OP_LOGI(context->GetNodeName(), "TilingPrepare4ResizeBicubicV2 running.");
    auto compileInfo = context->GetCompiledInfo<ResizeBicubicV2CompileInfo>();
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

IMPL_OP_OPTILING(ResizeBicubicV2)
    .Tiling(Tiling4ResizeBicubicV2)
    .TilingParse<ResizeBicubicV2CompileInfo>(TilingPrepare4ResizeBicubicV2);
} // namespace optiling
