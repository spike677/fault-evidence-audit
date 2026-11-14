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
 * \file upsample_nearest3d_tiling_arch35.cpp
 * \brief
 */

#include <iostream>
#include <cmath>
#include "tiling/platform/platform_ascendc.h"
#include "op_common/op_host/util/platform_util.h"
#include "op_host/tiling_base.h"
#include "op_host/tiling_util.h"
#include "op_host/tiling_templates_registry.h"
#include "upsample_nearest3d_tiling.h"
#include "image/upsample_nearest3d/op_kernel/arch35/upsample_nearest3d_tiling_data.h"
#include "image/upsample_nearest3d/op_kernel/arch35/upsample_nearest3d_tiling_key.h"

namespace optiling {
using namespace Ops::Cv::OpTiling;

constexpr int32_t CONST_0 = 0;
constexpr int32_t CONST_1 = 1;
constexpr int32_t CONST_2 = 2;
constexpr int32_t CONST_3 = 3;
constexpr int32_t CONST_4 = 4;
constexpr int64_t INPUT_DIMS = 5;
constexpr int64_t THREAD_NUM = 2048; // simt开的线程数
constexpr int32_t CACHE_LINE = 128;
constexpr size_t WORKSPACE_SIZE = static_cast<size_t>(16 * 1024 * 1024);
constexpr const float EPSILON = 1e-8f;
const std::string EXACT_1D_TYPE = "UpsampleNearestExact1d";
const std::string EXACT_2D_TYPE = "UpsampleNearestExact2d";
const std::string EXACT_3D_TYPE = "UpsampleNearestExact3d";

constexpr int64_t SIMD_THRESHOLD_HIGH = 5000000; // SIMD模式高阈值
constexpr int64_t SIMD_THRESHOLD_LOW = 86400;    // SIMD模式低阈值
constexpr int64_t SIMD_WIDTH_THRESHOLD = 95;     // SIMD宽度阈值
constexpr int64_t OUTPUT_SIZE_EXPECTED = 3;      // 期望的输出尺寸数量
constexpr int64_t SIMD_SCHEDULE_ID = 4;          // SIMD调度ID

struct BaseTilingData {
    int64_t dimN = 0;
    int64_t dimC = 0;
    int64_t inD = 0;
    int64_t inH = 0;
    int64_t inW = 0;
    int64_t outD = 0;
    int64_t outH = 0;
    int64_t outW = 0;
    int64_t outSize = 0;
    int64_t blkProcessNum = 0;
    float scaleD = 0.0;
    float scaleH = 0.0;
    float scaleW = 0.0;
    int32_t isUint32 = 1;
    int32_t schId = 0;
    int32_t realCoreNum = 0;
    int32_t tailBlockNum = 0;
    int32_t coreNum = 0;
    int32_t ubSize = 0;
    int32_t ubFactor = 0;
    int32_t dtypeSize = 0;
    int32_t cacheLineNum = 0;
    int32_t oneBlockNum = 0;

    int64_t batches = 0;
    int64_t slideSizeW = 0;
    int64_t tensorSizeW = 0;
    int64_t tensorSizeH = 0;
    int64_t tensorSizeD = 0;
    int64_t slideNumH = 0;
    int64_t slideNumD = 0;
    int64_t eachCoreSlideNum = 0;
    int64_t remainder = 0;
    int64_t tailStartSlideNum = 0;
    int64_t groupCoreNum = 0;
    int64_t inputRow = 0;
    int64_t tailAvergingRow = 0;
    bool isView1DAndSmallW = false;
};

static const std::map<ge::DataType, int32_t> inputDtypeList = {
    {ge::DT_DOUBLE, 8}, {ge::DT_UINT8, 1}, {ge::DT_FLOAT, 4}, {ge::DT_FLOAT16, 2}, {ge::DT_BF16, 2}};
class UpsampleNearest3dRegbaseTiling {
public:
    explicit UpsampleNearest3dRegbaseTiling(gert::TilingContext* context) : context_(context) {};

    ge::graphStatus Init();
    ge::graphStatus DoTiling();

private:
    static constexpr int64_t BEST_PERFORMANCE_SIZE_1 = 256;
    static constexpr int64_t BEST_PERFORMANCE_SIZE_2 = 768;
    static constexpr int64_t BEST_PERFORMANCE_SIZE_3 = 1536;
    static constexpr int64_t BEST_PERFORMANCE_SIZE_4 = 2048;
    static constexpr float BEST_PERFORMANCE_SCALE_1 = 100.0f;
    static constexpr float BEST_PERFORMANCE_SCALE_2 = 24.0f;
    static constexpr float BEST_PERFORMANCE_SCALE_3 = 10.0f;
    static constexpr float BEST_PERFORMANCE_SCALE_4 = 6.0f;
    static constexpr float ZERO_FLOAT = 0.0f;
    static constexpr float ONE_FLOAT = 1.0f;
    static constexpr int64_t RESERVED_LENGTH = 4;
    static constexpr int64_t SMALL_W = 64;
    static constexpr size_t SHAPE_SIZE = 3;
    static constexpr uint8_t D_INDEX = 0;
    static constexpr uint8_t H_INDEX = 1;
    static constexpr uint8_t W_INDEX = 2;

    ge::graphStatus CheckInputParams();
    ge::graphStatus CheckDtypeAndFormat();
    ge::graphStatus GetAndCheckShapes();
    ge::graphStatus CheckInputShapeAndAttr();
    ge::graphStatus CheckInitTilingData();
    ge::graphStatus CheckNCAxesConsistency();
    ge::graphStatus GetAndCheckAttrs();
    void ComputeScales(float scaleD, float scaleH, float scaleW);
    void CalTilingData();
    void ComputeDataCopy();
    void FillTilingData();
    void PrintTilingData();

    void CalSimdTilingData();
    void FillSimdTilingData();
    void PrintSimdTilingData();
    bool GetIsSimd();
    void GetTensorSize();
    void GetRealCoreNum();
    bool GetISView1DAndSmallW();

    template <typename T1, typename T2>
    static T1 CeilA2B(T1 a, T2 b)
    {
        if (b != 0) {
            return (a + b - 1) / b;
        }
        return a;
    }

    template <typename T1>
    static int32_t Ceil(T1 x)
    {
        int32_t floorX = static_cast<int32_t>(x);
        if (FloatEqual(x, floorX)) {
            return floorX;
        }
        return floorX + 1;
    }

    static bool FloatEqual(float a, float b)
    {
        float closeTo0 = 1e-6f;
        if (a > b) {
            return a - b < closeTo0;
        }
        return b - a < closeTo0;
    }

private:
    BaseTilingData baseTiling_;

    gert::TilingContext* context_ = nullptr;
    UpsampleNearest3dRegBaseTilingData* tilingData_{nullptr};
    gert::Shape inputShape_;
    gert::Shape outShape_;
    UpsampleNearest3dRegBaseSimdTilingData* simDTilingData_{nullptr};

private:
    bool isSimd{false};
    bool isExact{false};
};

bool UpsampleNearest3dRegbaseTiling::GetIsSimd()
{
    if (!isExact) {
        return false;
    }
    bool isDataCopy = baseTiling_.outD == baseTiling_.inD && baseTiling_.outH == baseTiling_.inH &&
                      baseTiling_.outW == baseTiling_.inW && std::abs(baseTiling_.scaleD - 1.0f) <= EPSILON &&
                      std::abs(baseTiling_.scaleH - 1.0f) <= EPSILON && std::abs(baseTiling_.scaleW - 1.0f) <= EPSILON;
    if (isDataCopy) {
        return false;
    }

    int64_t outDHW = baseTiling_.outD * baseTiling_.outH * baseTiling_.outW;
    if (outDHW >= SIMD_THRESHOLD_HIGH) {
        return true;
    }

    if (outDHW >= SIMD_THRESHOLD_LOW && baseTiling_.outW >= SIMD_WIDTH_THRESHOLD) {
        return true;
    }

    return false;
}

void UpsampleNearest3dRegbaseTiling::ComputeDataCopy()
{
    int64_t coreNum = static_cast<int64_t>(baseTiling_.coreNum);
    if (baseTiling_.outSize <= static_cast<int64_t>(baseTiling_.cacheLineNum * baseTiling_.coreNum)) {
        baseTiling_.realCoreNum = static_cast<int32_t>(baseTiling_.outSize) / baseTiling_.cacheLineNum;
    }
    if (baseTiling_.realCoreNum == 0) {
        baseTiling_.realCoreNum = 1;
    }
    baseTiling_.blkProcessNum = baseTiling_.outSize / static_cast<int64_t>(baseTiling_.realCoreNum);
    baseTiling_.tailBlockNum = static_cast<int32_t>(baseTiling_.outSize %
                                                    static_cast<int64_t>(baseTiling_.realCoreNum));
    baseTiling_.ubFactor = (baseTiling_.ubSize - baseTiling_.oneBlockNum * baseTiling_.dtypeSize) /
                           (CONST_2 * baseTiling_.dtypeSize);
    baseTiling_.ubFactor = (baseTiling_.ubFactor / baseTiling_.oneBlockNum) * baseTiling_.oneBlockNum;
    return;
}

void UpsampleNearest3dRegbaseTiling::CalTilingData()
{
    int64_t outDHW = baseTiling_.outD * baseTiling_.outH * baseTiling_.outW;
    int64_t outCDHW = baseTiling_.dimC * outDHW;
    int64_t outNCDHW = baseTiling_.dimN * outCDHW;
    int64_t maxNum = static_cast<int64_t>(baseTiling_.coreNum) * THREAD_NUM;
    bool isDataCopy = baseTiling_.outD == baseTiling_.inD && baseTiling_.outH == baseTiling_.inH &&
                      baseTiling_.outW == baseTiling_.inW && std::abs(baseTiling_.scaleD - 1.0f) <= EPSILON &&
                      std::abs(baseTiling_.scaleH - 1.0f) <= EPSILON && std::abs(baseTiling_.scaleW - 1.0f) <= EPSILON;
    baseTiling_.realCoreNum = baseTiling_.coreNum;
    baseTiling_.cacheLineNum = CACHE_LINE / baseTiling_.dtypeSize;

    if (isDataCopy) {
        OP_LOGI(context_, "enter datacopy");
        baseTiling_.schId = 0; // 纯copy模板
        baseTiling_.isUint32 = 0;
        ComputeDataCopy();
    } else {
        int64_t allNum = 0;
        if (outDHW >= maxNum) {
            OP_LOGI(context_, "enter simt dhw");
            baseTiling_.schId = 1; // dhw 分线程， nc拉成一维
            baseTiling_.dimN = baseTiling_.dimN * baseTiling_.dimC;
            allNum = outDHW;
        } else if (outCDHW >= maxNum) {
            OP_LOGI(context_, "enter simt cdhw");
            baseTiling_.schId = CONST_2; // cdhw 分线程, 和竞品一致
            allNum = outCDHW;
        } else {
            OP_LOGI(context_, "enter simt ncdhw");
            int64_t coreNum = static_cast<int64_t>(baseTiling_.coreNum);
            if (outNCDHW < coreNum) {
                baseTiling_.realCoreNum = static_cast<int32_t>(outNCDHW);
            }
            allNum = outNCDHW;
            baseTiling_.schId = CONST_3; // ncdhw 分线程
        }
        baseTiling_.blkProcessNum = allNum / static_cast<int64_t>(baseTiling_.realCoreNum);
        baseTiling_.tailBlockNum = static_cast<int32_t>(allNum % static_cast<int64_t>(baseTiling_.realCoreNum));
    }
    return;
}

ge::graphStatus UpsampleNearest3dRegbaseTiling::CheckDtypeAndFormat()
{
    auto input = context_->GetInputDesc(CONST_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, input);
    auto inputDtype = input->GetDataType();
    OP_CHECK_IF(inputDtypeList.count(inputDtype) == 0,
                OP_LOGE_FOR_INVALID_DTYPE(context_->GetNodeName(), "x", Ops::Base::ToString(inputDtype).c_str(),
                                          "uint8, float, float16 and bfloat16"),
                return ge::GRAPH_FAILED);
    baseTiling_.dtypeSize = inputDtypeList.find(inputDtype)->second;
    int32_t ubBlockSize = static_cast<int32_t>(Ops::Base::GetUbBlockSize(context_));
    baseTiling_.oneBlockNum = ubBlockSize / baseTiling_.dtypeSize;
    auto outDescPtr0 = context_->GetOutputDesc(0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, outDescPtr0);
    auto outDtype = outDescPtr0->GetDataType();
    if (outDtype != inputDtype) {
        std::string dtypeMsg = Ops::Base::ToString(inputDtype) + " and " + Ops::Base::ToString(outDtype);
        OP_LOGE_FOR_INVALID_DTYPES_WITH_REASON(context_->GetNodeName(), "x and y", dtypeMsg.c_str(),
                                               "The dtypes of input x and output y must be the same");
        return ge::GRAPH_FAILED;
    }
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus UpsampleNearest3dRegbaseTiling::GetAndCheckShapes()
{
    auto inputX = context_->GetInputShape(0);
    auto outY = context_->GetOutputShape(0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, inputX);
    OP_CHECK_NULL_WITH_CONTEXT(context_, outY);
    inputShape_ = EnsureNotScalar(inputX->GetStorageShape());
    outShape_ = EnsureNotScalar(outY->GetStorageShape());
    if ((inputShape_.GetDimNum() != INPUT_DIMS) || (outShape_.GetDimNum() != INPUT_DIMS)) {
        std::string dimMsg = std::to_string(inputShape_.GetDimNum()) + " and " + std::to_string(outShape_.GetDimNum());
        OP_LOGE_FOR_INVALID_SHAPEDIMS_WITH_REASON(context_->GetNodeName(), "x and y", dimMsg.c_str(),
                                                  "The shapes of input x and output y must be 5D");
        return ge::GRAPH_FAILED;
    }
    int64_t inputSize = inputShape_.GetShapeSize();
    int64_t outputSize = outShape_.GetShapeSize();
    baseTiling_.dimN = inputShape_.GetDim(CONST_0);
    baseTiling_.dimC = inputShape_.GetDim(CONST_1);
    baseTiling_.inD = inputShape_.GetDim(CONST_2);
    baseTiling_.inH = inputShape_.GetDim(CONST_3);
    baseTiling_.inW = inputShape_.GetDim(CONST_4);
    baseTiling_.outD = outShape_.GetDim(CONST_2);
    baseTiling_.outH = outShape_.GetDim(CONST_3);
    baseTiling_.outW = outShape_.GetDim(CONST_4);
    baseTiling_.outSize = outputSize;
    if (inputSize == 0 || outputSize == 0) {
        std::string shapeMsg = Ops::Base::ToString(inputShape_) + " and " + Ops::Base::ToString(outShape_);
        OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(context_->GetNodeName(), "x and y", shapeMsg.c_str(),
                                               "Input x and output y cannot be empty tensors");
        return ge::GRAPH_FAILED;
    }
    int64_t uint32Max = static_cast<int64_t>(std::numeric_limits<uint32_t>::max());
    int64_t int32Max = static_cast<int64_t>(std::numeric_limits<int32_t>::max());
    int32_t isUint32 = static_cast<int32_t>((inputSize <= uint32Max) && (outputSize <= uint32Max) &&
                                            baseTiling_.inD <= int32Max && baseTiling_.inH <= int32Max &&
                                            baseTiling_.inW <= int32Max && baseTiling_.outD <= int32Max &&
                                            baseTiling_.outH <= int32Max && baseTiling_.outW <= int32Max);
    baseTiling_.isUint32 = isUint32;
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus UpsampleNearest3dRegbaseTiling::CheckInputParams()
{
    OP_CHECK_IF((CheckDtypeAndFormat() != ge::GRAPH_SUCCESS),
                OP_LOGE(context_->GetNodeName(), "CheckDtypeAndFormat failed."), return ge::GRAPH_FAILED);

    OP_CHECK_IF((GetAndCheckShapes() != ge::GRAPH_SUCCESS),
                OP_LOGE(context_->GetNodeName(), "GetAndCheckShapes failed."), return ge::GRAPH_FAILED);

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus UpsampleNearest3dRegbaseTiling::CheckInitTilingData()
{
    isSimd = GetIsSimd();
    if (isSimd) {
        if (simDTilingData_ == nullptr) {
            simDTilingData_ = context_->GetTilingData<UpsampleNearest3dRegBaseSimdTilingData>();
            OP_CHECK_IF(simDTilingData_ == nullptr, OP_LOGE(context_, "get tilingdata ptr failed"),
                        return ge::GRAPH_FAILED);
        }
        OP_CHECK_IF((memset_s(simDTilingData_, sizeof(UpsampleNearest3dRegBaseSimdTilingData), 0,
                              sizeof(UpsampleNearest3dRegBaseSimdTilingData)) != EOK),
                    OP_LOGE(context_, "memset tilingdata failed"), return ge::GRAPH_FAILED);
    } else {
        if (tilingData_ == nullptr) {
            tilingData_ = context_->GetTilingData<UpsampleNearest3dRegBaseTilingData>();
            OP_CHECK_IF(tilingData_ == nullptr, OP_LOGE(context_, "get tilingdata ptr failed"),
                        return ge::GRAPH_FAILED);
        }
        OP_CHECK_IF((memset_s(tilingData_, sizeof(UpsampleNearest3dRegBaseTilingData), 0,
                              sizeof(UpsampleNearest3dRegBaseTilingData)) != EOK),
                    OP_LOGE(context_, "memset tilingdata failed"), return ge::GRAPH_FAILED);
    }
    return ge::GRAPH_SUCCESS;
}

void UpsampleNearest3dRegbaseTiling::ComputeScales(float scaleD, float scaleH, float scaleW)
{
    baseTiling_.scaleD = static_cast<float>(baseTiling_.inD) / static_cast<float>(baseTiling_.outD);
    baseTiling_.scaleH = static_cast<float>(baseTiling_.inH) / static_cast<float>(baseTiling_.outH);
    baseTiling_.scaleW = static_cast<float>(baseTiling_.inW) / static_cast<float>(baseTiling_.outW);
    if (scaleD > 0.0f) {
        baseTiling_.scaleD = 1.0f / scaleD;
    }
    if (scaleH > 0.0f) {
        baseTiling_.scaleH = 1.0f / scaleH;
    }
    if (scaleW > 0.0f) {
        baseTiling_.scaleW = 1.0f / scaleW;
    }
    return;
}

ge::graphStatus UpsampleNearest3dRegbaseTiling::CheckNCAxesConsistency()
{
    int64_t outN = outShape_.GetDim(CONST_0);
    int64_t outC = outShape_.GetDim(CONST_1);
    if ((outN != baseTiling_.dimN) || (outC != baseTiling_.dimC)) {
        std::string shapeMsg = Ops::Base::ToString(inputShape_) + " and " + Ops::Base::ToString(outShape_);
        std::string reasonMsg = "The N-dimension and C-dimension of x and y must be the same, "
                                "where N is the 0th axis and C is the 1st axis";
        OP_LOGE_FOR_INVALID_SHAPES_WITH_REASON(context_->GetNodeName(), "x and y", shapeMsg.c_str(), reasonMsg.c_str());
        return ge::GRAPH_FAILED;
    }
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus UpsampleNearest3dRegbaseTiling::GetAndCheckAttrs()
{
    auto attrs = context_->GetAttrs();
    OP_CHECK_NULL_WITH_CONTEXT(context_, attrs);
    auto outputSize = attrs->GetAttrPointer<gert::ContinuousVector>(CONST_0);
    OP_CHECK_NULL_WITH_CONTEXT(context_, outputSize);
    const float* scaleDPtr = attrs->GetAttrPointer<float>(1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, scaleDPtr);
    float scaleD = *scaleDPtr;
    const float* scaleHPtr = attrs->GetAttrPointer<float>(CONST_2);
    OP_CHECK_NULL_WITH_CONTEXT(context_, scaleHPtr);
    float scaleH = *scaleHPtr;
    const float* scaleWPtr = attrs->GetAttrPointer<float>(CONST_3);
    OP_CHECK_NULL_WITH_CONTEXT(context_, scaleWPtr);
    float scaleW = *scaleWPtr;
    OP_LOGI(context_, "scaleD %f, scaleH %f, scaleW %f", scaleD, scaleH, scaleW);
    int64_t outSizeNum = outputSize->GetSize();
    OP_CHECK_IF(outSizeNum > 0 && (outSizeNum != CONST_3),
                OP_LOGE_FOR_INVALID_LISTSIZE(context_->GetNodeName(), "output_size", std::to_string(outSizeNum).c_str(),
                                             "0 or 3"),
                return ge::GRAPH_FAILED);
    const int64_t* outData = static_cast<const int64_t*>(outputSize->GetData());
    int64_t outD = baseTiling_.outD;
    int64_t outH = baseTiling_.outH;
    int64_t outW = baseTiling_.outW;
    if (outSizeNum == CONST_3) {
        outD = outData[0];
        outH = outData[CONST_1];
        outW = outData[CONST_2];
    }
    if ((baseTiling_.outD != outD) || (baseTiling_.outH != outH) || (baseTiling_.outW != outW)) {
        std::string reasonMsg = "The D/H/W-dimensions of output y must be the same as the value (" +
                                std::to_string(outD) + ", " + std::to_string(outH) + ", " + std::to_string(outW) +
                                ") of attribute output_size";
        OP_LOGE_FOR_INVALID_SHAPE_WITH_REASON(context_->GetNodeName(), "y", Ops::Base::ToString(outShape_).c_str(),
                                              reasonMsg.c_str());
        return ge::GRAPH_FAILED;
    }
    ComputeScales(scaleD, scaleH, scaleW);
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus UpsampleNearest3dRegbaseTiling::CheckInputShapeAndAttr()
{
    OP_CHECK_IF((CheckNCAxesConsistency() != ge::GRAPH_SUCCESS),
                OP_LOGE(context_->GetNodeName(), "CheckNCAxesConsistency failed."), return ge::GRAPH_FAILED);

    OP_CHECK_IF((GetAndCheckAttrs() != ge::GRAPH_SUCCESS), OP_LOGE(context_->GetNodeName(), "GetAndCheckAttrs failed."),
                return ge::GRAPH_FAILED);

    return ge::GRAPH_SUCCESS;
}

void UpsampleNearest3dRegbaseTiling::FillTilingData()
{
    tilingData_->ubFactor = baseTiling_.ubFactor;
    tilingData_->tailBlockNum = baseTiling_.tailBlockNum;
    tilingData_->blkProcessNum = baseTiling_.blkProcessNum;
    tilingData_->lenN = baseTiling_.dimN;
    tilingData_->lenC = baseTiling_.dimC;
    tilingData_->inD = baseTiling_.inD;
    tilingData_->inH = baseTiling_.inH;
    tilingData_->inW = baseTiling_.inW;
    tilingData_->outD = baseTiling_.outD;
    tilingData_->outH = baseTiling_.outH;
    tilingData_->outW = baseTiling_.outW;
    tilingData_->scaleD = baseTiling_.scaleD;
    tilingData_->scaleH = baseTiling_.scaleH;
    tilingData_->scaleW = baseTiling_.scaleW;
}

void UpsampleNearest3dRegbaseTiling::PrintTilingData()
{
    OP_LOGD(context_,
            "ubFactor %d, tailBlockNum %d, blkProcessNum %ld, lenN %ld, lenC %ld, inD %ld, inH %ld, inW %ld, outD %ld, "
            "outH %ld, outW %ld, scaleD %f, scaleH %f, scaleW %f",
            tilingData_->ubFactor, tilingData_->tailBlockNum, tilingData_->blkProcessNum, tilingData_->lenN,
            tilingData_->lenC, tilingData_->inD, tilingData_->inH, tilingData_->inW, tilingData_->outD,
            tilingData_->outH, tilingData_->outW, tilingData_->scaleD, tilingData_->scaleH, tilingData_->scaleW);
}

ge::graphStatus UpsampleNearest3dRegbaseTiling::Init()
{
    fe::PlatFormInfos* platformInfoPtr = context_->GetPlatformInfo();
    OP_CHECK_NULL_WITH_CONTEXT(context_, platformInfoPtr);
    auto ascendcPlatform = platform_ascendc::PlatformAscendC(platformInfoPtr);
    int32_t coreNum = ascendcPlatform.GetCoreNumAiv();
    OP_CHECK_IF(coreNum <= 0, OP_LOGE(context_, "coreNum must greater than zero, but is %d", coreNum),
                return ge::GRAPH_FAILED);
    baseTiling_.coreNum = coreNum;
    uint64_t ubSize = 0;
    ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::UB, ubSize);
    OP_CHECK_IF(ubSize <= 0UL, OP_LOGE(context_, "ubSize must greater than zero, but is %lu", ubSize),
                return ge::GRAPH_FAILED);
    OP_LOGI(context_, "coreNum is %ld, ubSize is %lu", coreNum, ubSize);
    baseTiling_.ubSize = static_cast<int32_t>(ubSize);
    std::string opType(context_->GetNodeType());
    if (opType == EXACT_3D_TYPE || opType == EXACT_2D_TYPE || opType == EXACT_1D_TYPE) {
        isExact = true;
    }
    return ge::GRAPH_SUCCESS;
}

void UpsampleNearest3dRegbaseTiling::GetTensorSize()
{
    float realScaleD = baseTiling_.scaleD;
    float realScaleH = baseTiling_.scaleH;

    int64_t slideNumH = baseTiling_.outH;
    int64_t tensorSizeH = 1;
    if (realScaleH > ZERO_FLOAT && realScaleH < ONE_FLOAT) {
        slideNumH = baseTiling_.inH;
        tensorSizeH = RESERVED_LENGTH;
    }

    int64_t slideNumD = baseTiling_.outD;
    int64_t tensorSizeD = 1;
    if (realScaleD > ZERO_FLOAT && realScaleD < ONE_FLOAT) {
        slideNumD = baseTiling_.inD;
        tensorSizeD = RESERVED_LENGTH;
    }

    baseTiling_.slideNumH = slideNumH;
    baseTiling_.slideNumD = slideNumD;
    baseTiling_.tensorSizeH = tensorSizeH;
    baseTiling_.tensorSizeD = tensorSizeD;
}

void UpsampleNearest3dRegbaseTiling::GetRealCoreNum()
{
    float realScaleW = baseTiling_.scaleW;
    int64_t batches = baseTiling_.batches;
    int64_t slideNumH = baseTiling_.slideNumH;
    int64_t slideNumD = baseTiling_.slideNumD;
    int64_t slideSizeW = baseTiling_.slideSizeW;
    int64_t coreNumPlatform = static_cast<int64_t>(baseTiling_.coreNum);

    int64_t slideNumW = CeilA2B(baseTiling_.outW, slideSizeW);
    int64_t tensorSizeW = Ceil(slideSizeW * std::min(realScaleW, BEST_PERFORMANCE_SCALE_1)) + RESERVED_LENGTH;

    int64_t slideNum = slideNumW * slideNumH * slideNumD;
    int64_t eachCoreSlideNum = coreNumPlatform > 0 ? slideNum / coreNumPlatform : 0;
    int64_t remainder = coreNumPlatform > 0 ? slideNum % coreNumPlatform : 0;
    int64_t inputRow = batches;
    int64_t groupCoreNum = coreNumPlatform;
    int64_t tailAvergingRow = 1;
    if (remainder > 0) {
        groupCoreNum = coreNumPlatform / remainder;
        tailAvergingRow = CeilA2B(inputRow, groupCoreNum);
        groupCoreNum = std::min(groupCoreNum, CeilA2B(inputRow, tailAvergingRow));
    }

    int32_t realCoreNum = coreNumPlatform;
    if (eachCoreSlideNum == 0 && remainder > 0) {
        realCoreNum = remainder * groupCoreNum;
    }

    baseTiling_.tensorSizeW = tensorSizeW;
    baseTiling_.eachCoreSlideNum = eachCoreSlideNum;
    baseTiling_.remainder = remainder;
    baseTiling_.tailStartSlideNum = eachCoreSlideNum * coreNumPlatform;
    baseTiling_.groupCoreNum = groupCoreNum;
    baseTiling_.inputRow = inputRow;
    baseTiling_.tailAvergingRow = tailAvergingRow;
    baseTiling_.realCoreNum = realCoreNum;
}

bool UpsampleNearest3dRegbaseTiling::GetISView1DAndSmallW()
{
    if (baseTiling_.inD != 1 || baseTiling_.outD != 1) {
        return false;
    }
    if (baseTiling_.inH != 1 || baseTiling_.outH != 1) {
        return false;
    }
    if (baseTiling_.scaleW > BEST_PERFORMANCE_SCALE_1) {
        return false;
    }
    if (baseTiling_.outW > SMALL_W) {
        return false;
    }
    return true;
}

void UpsampleNearest3dRegbaseTiling::CalSimdTilingData()
{
    OP_LOGI(context_, "enter simd");

    baseTiling_.realCoreNum = baseTiling_.coreNum;
    baseTiling_.batches = baseTiling_.dimN * baseTiling_.dimC;
    baseTiling_.schId = SIMD_SCHEDULE_ID;
    baseTiling_.isUint32 = 0;
    if (baseTiling_.scaleW <= BEST_PERFORMANCE_SCALE_4) {
        baseTiling_.slideSizeW = BEST_PERFORMANCE_SIZE_4;
    } else if (baseTiling_.scaleW <= BEST_PERFORMANCE_SCALE_3) {
        baseTiling_.slideSizeW = BEST_PERFORMANCE_SIZE_3;
    } else if (baseTiling_.scaleW <= BEST_PERFORMANCE_SCALE_2) {
        baseTiling_.slideSizeW = BEST_PERFORMANCE_SIZE_2;
    } else {
        baseTiling_.slideSizeW = BEST_PERFORMANCE_SIZE_1;
    }

    GetTensorSize();
    GetRealCoreNum();

    baseTiling_.isView1DAndSmallW = false;
    if (GetISView1DAndSmallW()) {
        baseTiling_.isView1DAndSmallW = true;
        baseTiling_.realCoreNum = static_cast<int64_t>(baseTiling_.coreNum);
        baseTiling_.tailAvergingRow = CeilA2B(baseTiling_.inputRow, static_cast<int64_t>(baseTiling_.coreNum));
        baseTiling_.realCoreNum = CeilA2B(baseTiling_.inputRow, baseTiling_.tailAvergingRow);
    }
}

void UpsampleNearest3dRegbaseTiling::FillSimdTilingData()
{
    simDTilingData_->lenN = baseTiling_.dimN;
    simDTilingData_->lenC = baseTiling_.dimC;
    simDTilingData_->inD = baseTiling_.inD;
    simDTilingData_->inH = baseTiling_.inH;
    simDTilingData_->inW = baseTiling_.inW;
    simDTilingData_->outD = baseTiling_.outD;
    simDTilingData_->outH = baseTiling_.outH;
    simDTilingData_->outW = baseTiling_.outW;
    simDTilingData_->scaleD = baseTiling_.scaleD;
    simDTilingData_->scaleH = baseTiling_.scaleH;
    simDTilingData_->scaleW = baseTiling_.scaleW;
    simDTilingData_->slideSizeW = baseTiling_.slideSizeW;
    simDTilingData_->tensorSizeW = baseTiling_.tensorSizeW;
    simDTilingData_->tensorSizeH = baseTiling_.tensorSizeH;
    simDTilingData_->tensorSizeD = baseTiling_.tensorSizeD;
    simDTilingData_->slideNumH = baseTiling_.slideNumH;
    simDTilingData_->slideNumD = baseTiling_.slideNumD;
    simDTilingData_->eachCoreSlideNum = baseTiling_.eachCoreSlideNum;
    simDTilingData_->remainder = baseTiling_.remainder;
    simDTilingData_->tailStartSlideNum = baseTiling_.tailStartSlideNum;
    simDTilingData_->groupCoreNum = baseTiling_.groupCoreNum;
    simDTilingData_->inputRow = baseTiling_.inputRow;
    simDTilingData_->tailAvergingRow = baseTiling_.tailAvergingRow;
    simDTilingData_->realCoreNum = baseTiling_.realCoreNum;
    simDTilingData_->isView1DAndSmallW = baseTiling_.isView1DAndSmallW;
}

void UpsampleNearest3dRegbaseTiling::PrintSimdTilingData()
{
    OP_LOGD(
        context_,
        "lenN %ld, lenC %ld, inD %ld, inH %ld, inW %ld, outD %ld, "
        "outH %ld, outW %ld, scaleD %f, scaleH %f, scaleW %f, slideSizeW %ld, tensorSizeW %ld, tensorSizeH %ld, "
        "tensorSizeD %ld, slideNumH %ld, slideNumD %ld, eachCoreSlideNum %ld, remainder %ld, tailStartSlideNum %ld, "
        "groupCoreNum %ld, inputRow %ld, tailAvergingRow %ld, realCoreNum %d, isView1DAndSmallW %d",
        simDTilingData_->lenN, simDTilingData_->lenC, simDTilingData_->inD, simDTilingData_->inH, simDTilingData_->inW,
        simDTilingData_->outD, simDTilingData_->outH, simDTilingData_->outW, simDTilingData_->scaleD,
        simDTilingData_->scaleH, simDTilingData_->scaleW, simDTilingData_->slideSizeW, simDTilingData_->tensorSizeW,
        simDTilingData_->tensorSizeH, simDTilingData_->tensorSizeD, simDTilingData_->slideNumH,
        simDTilingData_->slideNumD, simDTilingData_->eachCoreSlideNum, simDTilingData_->remainder,
        simDTilingData_->tailStartSlideNum, simDTilingData_->groupCoreNum, simDTilingData_->inputRow,
        simDTilingData_->tailAvergingRow, simDTilingData_->realCoreNum, simDTilingData_->isView1DAndSmallW);
}

ge::graphStatus UpsampleNearest3dRegbaseTiling::DoTiling()
{
    OP_CHECK_IF(CheckInputParams() != ge::GRAPH_SUCCESS, OP_LOGE(context_, "CheckInputParams is failed"),
                return ge::GRAPH_FAILED);
    OP_CHECK_IF(CheckInputShapeAndAttr() != ge::GRAPH_SUCCESS, OP_LOGE(context_, "CheckInputShapes is failed"),
                return ge::GRAPH_FAILED);
    OP_CHECK_IF(CheckInitTilingData() != ge::GRAPH_SUCCESS, OP_LOGE(context_, "CheckInitTilingData is failed"),
                return ge::GRAPH_FAILED);

    if (isSimd) {
        CalSimdTilingData();
        FillSimdTilingData();
        PrintSimdTilingData();
    } else {
        CalTilingData();
        FillTilingData();
        PrintTilingData();
    }

    uint64_t schId = static_cast<uint64_t>(baseTiling_.schId);
    uint64_t isUint32 = static_cast<uint64_t>(baseTiling_.isUint32);
    const uint64_t tilingKey = GET_TPL_TILING_KEY(schId, isUint32);
    OP_LOGI(context_, "tilingKey %lu, schId %lu, isUint32 %lu, realCoreNum %d", tilingKey, schId, isUint32,
            baseTiling_.realCoreNum);
    context_->SetTilingKey(tilingKey);
    context_->SetBlockDim(baseTiling_.realCoreNum);

    size_t* workspaces = context_->GetWorkspaceSizes(1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, workspaces);
    workspaces[0] = WORKSPACE_SIZE;
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus Tiling4UpsampleNearest3dRegbase(gert::TilingContext* context)
{
    UpsampleNearest3dRegbaseTiling tilingImpl = UpsampleNearest3dRegbaseTiling(context);
    if (tilingImpl.Init() != ge::GRAPH_SUCCESS) {
        OP_LOGE(context, "Tiling4UpsampleNearest3dRegbase init failed.");
        return ge::GRAPH_FAILED;
    }

    if (tilingImpl.DoTiling() != ge::GRAPH_SUCCESS) {
        OP_LOGE(context, "Tiling4UpsampleNearest3dRegbase do tiling failed.");
        return ge::GRAPH_FAILED;
    }
    OP_LOGI(context, "end Tiling4UpsampleNearest3dRegbase");
    return ge::GRAPH_SUCCESS;
}
} // namespace optiling