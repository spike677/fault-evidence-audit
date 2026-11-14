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
 * \file resize_linear_grad_tiling_arch35.cpp
 * \brief resize_linear_grad_tiling_arch35
 */

#include "register/op_impl_registry.h"
#include "log/log.h"
#include "image/resize_linear_grad/op_kernel/arch35/resize_linear_grad_tiling_key.h"
#include "resize_linear_grad_tiling_arch35.h"

namespace optiling {
constexpr size_t WORK_SPACE_SIZE = static_cast<size_t>(16 * 1024 * 1024);
static const uint64_t DIM_0 = 0;
static const uint64_t DIM_1 = 1;
static const uint64_t DIM_3 = 3;
static const uint64_t DIM_2 = 2;
static const uint64_t DIM_4 = 4;
static const uint64_t DIM_5 = 5;
static const int32_t EVEN_FACTOR = 2;
static const int32_t DB = 2;
static const float LOWER_DETERMINE = 0.8f; // scale小于此值走确定性实现
static const int64_t HIGH_DETERMINE = 100; // 重复个数大于此值走确定性实现
class ResizeLinearGradTiling {
public:
    explicit ResizeLinearGradTiling(gert::TilingContext* context) : context_(context) {};
    void LinearGetPlatformData(const ResizeLinearGradCompileInfo* compileInfo);
    ge::graphStatus LinearComputeGrad();
    ge::graphStatus CheckParams();
    ge::graphStatus CheckShapeDtypeParams();
    float ComputeScale(float scale, int64_t lenSrc, int64_t lenDes);
    float ComputeInverseScale(float scale, int64_t lenSrc, int64_t lenDes);
    ge::graphStatus SetTilingData();
    void PrintTilingData();
    void ComputeKey();
    void ComputeDataCopy();
    void CalculateCoreNum(
        int64_t inputSize, int64_t& realCoreNum, int64_t& ubLoopSizeT, int64_t& ubLoopSizeB, int64_t& blkProcessNum);
    void ComputeDesL1();
    void ComputeDesL1AndIntScale();
    void ComputeLenSrcL1();
    void ComputeOther(bool oddScale, bool isIntScale);

private:
    ResizeLinearGradTilingData tilingData_;
    gert::TilingContext* context_ = nullptr;
    int32_t blockSize_ = 0;
    uint64_t schId_ = 0;
    uint64_t isInt32_ = 0;
    uint64_t alignCorners_ = 0;
    uint64_t isDetermine_ = 0;
    int32_t dtypeSize_ = 0;
    int32_t coreNum_ = 0;
    int64_t ubSize_ = 0;
    int64_t ubSizeDb_ = 0;
    int64_t realCoreNum_ = 0;
    int64_t initCoreNum_ = 0;
    int64_t blkProcessNum_ = 0;
    int64_t ubLoopSizeB_ = 0;
    int64_t ubLoopSizeT_ = 0;
    int64_t ubFactor_ = 0;
    int32_t oneBlockNum_ = 0;
    int64_t ubFactorTailB_ = 0;
    int64_t ubFactorTailT_ = 0;
    int64_t lenSrcLOrUb_ = 0;
    int64_t lenDesL_ = 0;
    int64_t ySize_ = 0;
    int64_t xSize_ = 0;
    float scaleL_ = 0.0f;
    float inverseScaleL_ = 0.0f;
};

void ResizeLinearGradTiling::CalculateCoreNum(
    int64_t inputSize, int64_t& realCoreNum, int64_t& ubLoopSizeT, int64_t& ubLoopSizeB, int64_t& blkProcessNum)
{
    realCoreNum = (inputSize < (static_cast<int64_t>(coreNum_))) ? inputSize : coreNum_;
    OP_CHECK_IF((realCoreNum == 0), OP_LOGE("CalculateCoreNum", "realCoreNum is zero"), return);
    ubLoopSizeT = Ops::Base::FloorDiv(inputSize, realCoreNum); // 后面的每个核处理的个数
    ubLoopSizeB = inputSize - ubLoopSizeT * realCoreNum;       // 前面的核个数
    blkProcessNum = ubLoopSizeT + 1;                           // 前面的核每个核处理个数
    if (inputSize % realCoreNum == 0) {
        blkProcessNum = ubLoopSizeT;
    }
    return;
}

void ResizeLinearGradTiling::ComputeDataCopy()
{
    // 纯datacopy场景用simd的datacopy做
    OP_LOGI(context_->GetNodeName(), "enter ComputeDataCopy");
    schId_ = static_cast<uint64_t>(1);
    isInt32_ = static_cast<uint64_t>(0);
    isDetermine_ = static_cast<uint64_t>(0);
    alignCorners_ = static_cast<uint64_t>(0);
    ubSizeDb_ = ubSize_ / DB / blockSize_ * blockSize_; // 开db
    int64_t coreNumNew =
        xSize_ < static_cast<int64_t>(DB * coreNum_) ? static_cast<int64_t>(1) : static_cast<int64_t>(coreNum_);
    blkProcessNum_ = (xSize_ + coreNumNew - 1) / coreNumNew;
    realCoreNum_ = (xSize_ + blkProcessNum_ - 1) / blkProcessNum_;
    int64_t lastCoreProcessNum = xSize_ - (realCoreNum_ - 1) * blkProcessNum_;
    ubFactor_ = ubSizeDb_ / dtypeSize_ / oneBlockNum_ * oneBlockNum_;
    ubLoopSizeB_ = (blkProcessNum_ + ubFactor_ - 1) / ubFactor_;
    ubFactorTailB_ = blkProcessNum_ - (ubLoopSizeB_ - 1) * ubFactor_;
    ubLoopSizeT_ = (lastCoreProcessNum + ubFactor_ - 1) / ubFactor_;
    ubFactorTailT_ = lastCoreProcessNum - (ubLoopSizeT_ - 1) * ubFactor_;
    return;
}

void ResizeLinearGradTiling::ComputeDesL1()
{
    OP_LOGI(context_->GetNodeName(), "enter lenDesL 1 mode, alignCorners is True");
    schId_ = DIM_3;
    isDetermine_ = static_cast<uint64_t>(0);
    alignCorners_ = static_cast<uint64_t>(0);
    CalculateCoreNum(xSize_, initCoreNum_, ubFactorTailT_, ubFactorTailB_, ubFactor_);
    return;
}

void ResizeLinearGradTiling::ComputeDesL1AndIntScale()
{
    // output_l == 1,奇整数的scale，所以输出的nc直接搬出到输入的某个L点即可，无确定性问题
    OP_LOGI(context_->GetNodeName(), "enter lenDesL 1 and alignCorners_ is zero mode");
    schId_ = DIM_4;
    isDetermine_ = static_cast<uint64_t>(0);
    alignCorners_ = static_cast<uint64_t>(0);
    CalculateCoreNum(xSize_, initCoreNum_, ubFactorTailT_, ubFactorTailB_, ubFactor_);
    return;
}

void ResizeLinearGradTiling::ComputeLenSrcL1()
{
    // input_l == 1 直接输出的L 做reducesum得到输出, 存在非确定性，直接走确定性实现的
    OP_LOGI(context_->GetNodeName(), "enter lenSrcL == 1 mode");
    schId_ = DIM_2;
    alignCorners_ = static_cast<uint64_t>(0);
    isDetermine_ = static_cast<uint64_t>(1);
    CalculateCoreNum(xSize_, realCoreNum_, ubLoopSizeT_, ubLoopSizeB_, blkProcessNum_);
    return;
}

void ResizeLinearGradTiling::ComputeOther(bool oddScale, bool isIntScale)
{
    int64_t repeatNum = 0;
    if (alignCorners_ == static_cast<uint64_t>(0)) {
        repeatNum = static_cast<int64_t>(static_cast<float>(lenDesL_) * scaleL_) - lenSrcLOrUb_;
    }
    OP_LOGI(context_->GetNodeName(), "repeatNum is %ld", repeatNum);
    if (scaleL_ < LOWER_DETERMINE || repeatNum >= HIGH_DETERMINE) {
        OP_LOGI(
            context_->GetNodeName(), "scaleL is small than LOWER_DETERMINE or repeatNum greater than HIGH_DETERMINE");
        isDetermine_ = static_cast<uint64_t>(1);
    }
    if (isDetermine_ == static_cast<uint64_t>(1)) {
        OP_LOGI(context_->GetNodeName(), "enter isDetermine mode");
        CalculateCoreNum(xSize_, realCoreNum_, ubLoopSizeT_, ubLoopSizeB_, blkProcessNum_);
        if (oddScale || (alignCorners_ == static_cast<uint64_t>(1) && isIntScale)) {
            // 逐点copy场景，存在确定性问题
            OP_LOGI(context_->GetNodeName(), "enter isDetermine point copy mode");
            schId_ = DIM_5;
            return;
        }
        // 正常lineargrad操作，存在确定性
        OP_LOGI(context_->GetNodeName(), "enter isDetermine linear_grad mode");
        schId_ = DIM_0;
        return;
    } else {
        OP_LOGI(context_->GetNodeName(), "enter no determine mode");
        CalculateCoreNum(xSize_, initCoreNum_, ubFactorTailT_, ubFactorTailB_, ubFactor_);
        if (oddScale || (alignCorners_ == static_cast<uint64_t>(1) && isIntScale)) {
            // 逐点copy场景，存在确定性问题
            OP_LOGI(context_->GetNodeName(), "enter noDetermine point copy mode");
            schId_ = DIM_5;
            return;
        }
        OP_LOGI(context_->GetNodeName(), "enter noDetermine linear_grad mode");
        schId_ = DIM_0;
        return;
    }
    return;
}

void ResizeLinearGradTiling::ComputeKey()
{
    if (lenSrcLOrUb_ == lenDesL_) {
        ComputeDataCopy();
        return;
    }
    // 分核信息
    CalculateCoreNum(ySize_, realCoreNum_, ubLoopSizeT_, ubLoopSizeB_, blkProcessNum_);
    if (lenDesL_ == static_cast<int64_t>(1) && alignCorners_ == static_cast<uint64_t>(1)) {
        // 输出的nc直接搬到输入的nc即可，无确定性问题
        ComputeDesL1();
        return;
    }
    // 判断scaleL是否是1.0的整数倍
    float result = scaleL_ / 1.0f;
    int32_t int_result = static_cast<int32_t>(result);
    float reconstructedA = int_result * 1.0f;
    bool isIntScale = std::fabs(scaleL_ - reconstructedA) < 1e-6;
    OP_LOGI(context_->GetNodeName(), "isIntScale is %d", isIntScale);
    // 判断是否是奇数整数倍
    bool oddScale = false;
    if (alignCorners_ == static_cast<uint64_t>(0) && isIntScale) {
        int32_t intScaleL = static_cast<int32_t>(scaleL_);
        oddScale = intScaleL % EVEN_FACTOR == 1;
        OP_LOGI(context_->GetNodeName(), "oddScale is %d, intScaleL is %d", oddScale, intScaleL);
    }
    if (lenDesL_ == static_cast<int64_t>(1) && isIntScale && oddScale) {
        ComputeDesL1AndIntScale();
        return;
    }

    if (lenSrcLOrUb_ == static_cast<int64_t>(1)) {
        ComputeLenSrcL1();
        return;
    }
    ComputeOther(oddScale, isIntScale);
    return;
}

ge::graphStatus ResizeLinearGradTiling::CheckShapeDtypeParams()
{
    auto grads = context_->GetInputShape(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, grads);
    auto gradsDesc = context_->GetInputDesc(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, gradsDesc);
    ge::DataType dtypeGrads = gradsDesc->GetDataType();
    auto oriDesc = context_->GetInputDesc(DIM_1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, oriDesc);
    ge::DataType dtypeOri = oriDesc->GetDataType();
    auto outDesc = context_->GetOutputDesc(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, outDesc);
    ge::DataType dtypeOut = outDesc->GetDataType();
    if ((dtypeOut != dtypeOri) || (dtypeGrads != dtypeOri)) {
        std::string dtypeMsg = Ops::Base::ToString(dtypeGrads) + ", " + Ops::Base::ToString(dtypeOri) + " and " +
                               Ops::Base::ToString(dtypeOut);
        OP_LOGE_FOR_INVALID_DTYPES_WITH_REASON(context_->GetNodeName(), "grads, original_image and y", dtypeMsg.c_str(),
            "The dtypes of input grads, original_image and output y must be the same");
        return ge::GRAPH_FAILED;
    }
    auto ori = context_->GetInputShape(DIM_1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, ori);
    gert::Shape gradsShape = grads->GetStorageShape();
    gert::Shape oriShape = ori->GetStorageShape();
    int32_t gradsDims = gradsShape.GetDimNum();
    dtypeSize_ = static_cast<int32_t>(GetSizeByDataType(dtypeGrads));
    oneBlockNum_ = blockSize_ / dtypeSize_;
    auto y = context_->GetOutputShape(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, y);
    gert::Shape yShape = y->GetStorageShape();
    int32_t yshapeDims = yShape.GetDimNum();
    if (gradsDims != DIM_3 || yshapeDims != DIM_3) {
        std::string dimMsg = std::to_string(gradsDims) + " and " + std::to_string(yshapeDims);
        OP_LOGE_FOR_INVALID_SHAPEDIMS_WITH_REASON(
            context_->GetNodeName(), "grads and y", dimMsg.c_str(), "The shapes of grads and y must be 3D");
        return ge::GRAPH_FAILED;
    }
    if (oriShape != yShape) {
        std::string shapeMsg = Ops::Base::ToString(oriShape) + " and " + Ops::Base::ToString(yShape);
        OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(
            context_->GetNodeName(), "original_image and y", shapeMsg.c_str(), "The shapes of original_image and y must be the same");
        return ge::GRAPH_FAILED;
    }
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeLinearGradTiling::CheckParams()
{
    OP_CHECK_IF(
        CheckShapeDtypeParams() != ge::GRAPH_SUCCESS, OP_LOGE(context_->GetNodeName(), "CheckShapeDtypeParams failed"),
        return ge::GRAPH_FAILED);
    gert::Shape yShape = context_->GetOutputShape(DIM_0)->GetStorageShape();
    gert::Shape gradsShape = context_->GetInputShape(DIM_0)->GetStorageShape();
    lenSrcLOrUb_ = yShape.GetDim(DIM_2);
    lenDesL_ = gradsShape.GetDim(DIM_2);

    OP_LOGD(context_->GetNodeName(), "lenDesL is %ld, lenSrcL is %ld", lenDesL_, lenSrcLOrUb_);
    int64_t n = gradsShape.GetDim(DIM_0);
    int64_t c = gradsShape.GetDim(DIM_1);
    int64_t oN = yShape.GetDim(DIM_0);
    int64_t oC = yShape.GetDim(DIM_1);
    if (n != oN || c != oC) {
        std::string shapeMsg = Ops::Base::ToString(gradsShape) + " and " + Ops::Base::ToString(yShape);
        std::string reasonMsg = "The N-dimension and C-dimension of grads and y must be the same, "
                                "where N is the 0th axis and C is the 1st axis";
        OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(
            context_->GetNodeName(), "grads and y", shapeMsg.c_str(), reasonMsg.c_str());
        return ge::GRAPH_FAILED;
    }
    OP_LOGI(context_->GetNodeName(), "n is %ld, c is %ld", n, c);
    ySize_ = gradsShape.GetShapeSize();
    xSize_ = yShape.GetShapeSize();
    OP_LOGI(context_->GetNodeName(), "xSize is %ld, ySize is %ld", xSize_, ySize_);
    if (n <= 0 || c <= 0 || lenDesL_ <= 0 || lenSrcLOrUb_ <= 0) {
        std::string shapeMsg = Ops::Base::ToString(gradsShape) + " and " + Ops::Base::ToString(yShape);
        std::string reasonMsg = "All axes of grads and y must be greater than zero";
        OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(
            context_->GetNodeName(), "grads and y", shapeMsg.c_str(), reasonMsg.c_str());
        return ge::GRAPH_FAILED;
    }
    return ge::GRAPH_SUCCESS;
}

float ResizeLinearGradTiling::ComputeScale(float scale, int64_t lenSrc, int64_t lenDes)
{
    float newScale = 0.0f;
    if (scale > 0.0f) {
        newScale = static_cast<float>(1.0f) / scale;
    } else {
        newScale = static_cast<float>(lenSrc) / static_cast<float>(lenDes);
    }
    return newScale;
}

float ResizeLinearGradTiling::ComputeInverseScale(float scale, int64_t lenSrc, int64_t lenDes)
{
    float inverseScale = 0.0f;
    if (scale > 0.0f) {
        inverseScale = scale;
    } else {
        inverseScale = static_cast<float>(lenDes) / static_cast<float>(lenSrc);
    }
    return inverseScale;
}

ge::graphStatus ResizeLinearGradTiling::LinearComputeGrad()
{
    OP_CHECK_IF(
        CheckParams() != ge::GRAPH_SUCCESS, OP_LOGE(context_->GetNodeName(), "CheckParams failed"),
        return ge::GRAPH_FAILED);
    isDetermine_ = context_->GetDeterministic() == 1 ? static_cast<uint64_t>(1) : static_cast<uint64_t>(0);
    OP_LOGI(context_->GetNodeName(), "isDetermine_ is %ld", isDetermine_);
    auto attrs = context_->GetAttrs();
    OP_CHECK_NULL_WITH_CONTEXT(context_, attrs);
    const bool* alignCornersPtr = attrs->GetAttrPointer<bool>(DIM_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, alignCornersPtr);
    alignCorners_ = *alignCornersPtr ? static_cast<uint64_t>(1) : static_cast<uint64_t>(0);

    const float* scale = attrs->GetAttrPointer<float>(DIM_1);

    OP_CHECK_NULL_WITH_CONTEXT(context_, scale);
    scaleL_ = *scale;
    OP_LOGI(context_->GetNodeName(), "ori scaleL is %f, alignCorners is %ld", scaleL_, alignCorners_);
    if (alignCorners_ == static_cast<uint64_t>(0)) {
        inverseScaleL_ = ComputeInverseScale(scaleL_, lenSrcLOrUb_, lenDesL_);
        scaleL_ = ComputeScale(scaleL_, lenSrcLOrUb_, lenDesL_);
        OP_LOGI(
            context_->GetNodeName(), "alignCorners is False and new scaleL is %f, inverseScaleL_ is %f", scaleL_,
            inverseScaleL_);
    } else {
        scaleL_ = static_cast<float>(lenSrcLOrUb_) / static_cast<float>(lenDesL_);
        inverseScaleL_ = static_cast<float>(lenDesL_) / static_cast<float>(lenSrcLOrUb_);
        if (lenDesL_ > static_cast<int64_t>(1)) {
            scaleL_ = static_cast<float>(lenSrcLOrUb_ - 1) / static_cast<float>(lenDesL_ - 1);
        }
        if (lenSrcLOrUb_ > static_cast<int64_t>(1)) {
            inverseScaleL_ = static_cast<float>(lenDesL_ - 1) / static_cast<float>(lenSrcLOrUb_ - 1);
        }
        OP_LOGI(
            context_->GetNodeName(), "alignCorners is True, new scaleL is %f, inverseScaleL_ is %f", scaleL_,
            inverseScaleL_);
    }
    isInt32_ = DIM_1;
    if (ySize_ > UINT32_MAX || xSize_ > UINT32_MAX) {
        OP_LOGI(context_->GetNodeName(), "ySize or xSize is large than UINT32_MAX");
        isInt32_ = DIM_0;
    }
    if (lenSrcLOrUb_ > INT32_MAX || lenDesL_ > INT32_MAX) {
        isInt32_ = DIM_0;
    }
    ComputeKey();
    return ge::GRAPH_SUCCESS;
}

void ResizeLinearGradTiling::LinearGetPlatformData(const ResizeLinearGradCompileInfo* compileInfo)
{
    coreNum_ = compileInfo->totalCoreNum;
    ubSize_ = static_cast<int64_t>(compileInfo->totalUbSize);
    blockSize_ = compileInfo->blockSize;
    OP_LOGI(
        context_->GetNodeName(), "LinearGetPlatformData ubSize is %ld, coreNum_ is %d, blockSize_ is %d", ubSize_,
        coreNum_, blockSize_);
    return;
}

void ResizeLinearGradTiling::PrintTilingData()
{
    OP_LOGI(
        context_->GetNodeName(),
        "ResizeLinearGrad tilingData realCoreNum is %ld, initCoreNum is %ld, blkProcessNum is %ld,"
        "ubLoopSizeB is %ld, ubLoopSizeT is %ld, ubFactor is %ld, ubFactorTailB is %ld, ubFactorTailT is %ld,"
        "lenSrcLOrUb is %ld, lenDesL is %ld, scaleL is %f, inverseScaleL is %f",
        realCoreNum_, initCoreNum_, blkProcessNum_, ubLoopSizeB_, ubLoopSizeT_, ubFactor_, ubFactorTailB_,
        ubFactorTailT_, tilingData_.get_lenSrcLOrUb(), lenDesL_, scaleL_, inverseScaleL_);
    return;
}

ge::graphStatus ResizeLinearGradTiling::SetTilingData()
{
    int64_t srcLOrUbNum = lenSrcLOrUb_;
    if (lenSrcLOrUb_ == lenDesL_) {
        srcLOrUbNum = ubSizeDb_;
    }
    OP_LOGI(context_->GetNodeName(), "srcLOrUbNum is %ld", srcLOrUbNum);
    tilingData_.set_realCoreNum(realCoreNum_);
    tilingData_.set_initCoreNum(initCoreNum_);
    tilingData_.set_blkProcessNum(blkProcessNum_);
    tilingData_.set_ubLoopSizeB(ubLoopSizeB_);
    tilingData_.set_ubLoopSizeT(ubLoopSizeT_);
    tilingData_.set_ubFactor(ubFactor_);
    tilingData_.set_ubFactorTailB(ubFactorTailB_);
    tilingData_.set_ubFactorTailT(ubFactorTailT_);
    tilingData_.set_lenSrcLOrUb(srcLOrUbNum);
    tilingData_.set_lenDesL(lenDesL_);
    tilingData_.set_scaleL(scaleL_);
    tilingData_.set_inverseScaleL(inverseScaleL_);

    tilingData_.SaveToBuffer(context_->GetRawTilingData()->GetData(), context_->GetRawTilingData()->GetCapacity());
    context_->GetRawTilingData()->SetDataSize(tilingData_.GetDataSize());
    int64_t setNum = (realCoreNum_ < initCoreNum_) ? initCoreNum_ : realCoreNum_;
    context_->SetBlockDim(setNum);
    OP_LOGI(
        context_->GetNodeName(), "schId is %ld, isInt32 is %ld, alignCorners is %ld, isDetermine is %ld", schId_,
        isInt32_, alignCorners_, isDetermine_);
    const uint64_t tilingKey = GET_TPL_TILING_KEY(schId_, isInt32_, alignCorners_, isDetermine_);
    context_->SetTilingKey(tilingKey);
    context_->SetScheduleMode(1);
    size_t* workspaces = context_->GetWorkspaceSizes(1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, workspaces);
    workspaces[0] = WORK_SPACE_SIZE;
    PrintTilingData();
    return ge::GRAPH_SUCCESS;
}

static ge::graphStatus Tiling4ResizeLinearGrad(gert::TilingContext* context)
{
    auto compileInfo = static_cast<const ResizeLinearGradCompileInfo*>(context->GetCompileInfo());
    OP_CHECK_NULL_WITH_CONTEXT(context, compileInfo);
    ResizeLinearGradTiling tilingObject(context);
    tilingObject.LinearGetPlatformData(compileInfo);
    if (tilingObject.LinearComputeGrad() != ge::GRAPH_SUCCESS) {
        OP_LOGE(context->GetNodeName(), "LinearComputeGrad return failed.");
        return ge::GRAPH_FAILED;
    }
    if (tilingObject.SetTilingData() != ge::GRAPH_SUCCESS) {
        OP_LOGE(context->GetNodeName(), "SetTilingData return failed.");
        return ge::GRAPH_FAILED;
    }
    return ge::GRAPH_SUCCESS;
}

static ge::graphStatus TilingPrepare4ResizeLinearGrad(gert::TilingParseContext* context)
{
    OP_LOGI(context->GetNodeName(), "TilingPrepare4ResizeLinearGrad running.");
    auto compileInfo = context->GetCompiledInfo<ResizeLinearGradCompileInfo>();
    OP_CHECK_NULL_WITH_CONTEXT(context, compileInfo);
    auto platformInfo = context->GetPlatformInfo();
    OP_CHECK_NULL_WITH_CONTEXT(context, platformInfo);
    auto ascendcPlatform = platform_ascendc::PlatformAscendC(platformInfo);
    compileInfo->totalCoreNum = static_cast<int32_t>(ascendcPlatform.GetCoreNumAiv());
    OP_CHECK_IF(
        (compileInfo->totalCoreNum <= 0), OP_LOGE(context->GetNodeName(), "coreNum is invalid, must greater than zero"),
        return ge::GRAPH_FAILED);

    uint64_t ubSizePlatForm = 0;
    ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::UB, ubSizePlatForm);
    compileInfo->totalUbSize = static_cast<int32_t>(ubSizePlatForm);
    OP_CHECK_IF(
        (compileInfo->totalUbSize <= 0), OP_LOGE(context->GetNodeName(), "ubSize is invalid, must greater than zero"),
        return ge::GRAPH_FAILED);
    compileInfo->blockSize = static_cast<int32_t>(Ops::Base::GetUbBlockSize(context));
    OP_CHECK_IF(
        (compileInfo->blockSize <= 0), OP_LOGE(context->GetNodeName(), "blockSize is invalid, must greater than zero"),
        return ge::GRAPH_FAILED);
    return ge::GRAPH_SUCCESS;
}

IMPL_OP_OPTILING(ResizeLinearGrad)
    .Tiling(Tiling4ResizeLinearGrad)
    .TilingParse<ResizeLinearGradCompileInfo>(TilingPrepare4ResizeLinearGrad);
} // namespace optiling
