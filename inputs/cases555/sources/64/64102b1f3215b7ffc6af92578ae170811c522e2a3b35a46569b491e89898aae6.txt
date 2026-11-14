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
 * \file grid_sampler_2d_grad_tiling.cc
 * \brief
 */

#include <iostream>
#include <map>
#include <vector>
#include "grid_sampler_2d_grad_tiling_data.h"
#include "op_host/tiling_util.h"

namespace optiling {

constexpr uint32_t BYTE_BLOCK = 32;
constexpr uint32_t FP32_BLOCK_NUM = 8;
constexpr uint32_t FP16_BLOCK_NUM = 16;
constexpr size_t INTERPOLATION_MODE_INDEX = 0;
constexpr size_t PADDING_MODE_INDEX = 1;
constexpr size_t ALIGN_CORNERS_INDEX = 2;
constexpr int32_t GRAD_INPUT_INDEX = 0;
constexpr int32_t X_INPUT_INDEX = 1;
constexpr int32_t GRID_INPUT_INDEX = 2;
constexpr int32_t DTYPE_SIZE_32 = 4;
constexpr int32_t DTYPE_SIZE_16 = 2;
constexpr size_t CHECK_DIM_NUM = 4;
constexpr int BILINEAR = 0;
constexpr int NEAREST = 1;
constexpr int BICUBIC = 2;
constexpr int ZEROS = 0;
constexpr int BORDER = 1;
constexpr int REFLECTION = 2;
constexpr int TILINGKEY_2 = 2;
constexpr int BILINEAR_DIVIDE_UB_NUM = 57;
constexpr int NEAREST_DIVIDE_UB_NUM = 27;
constexpr int CAST_DIVIDE_UB_NUM = 3;
constexpr uint32_t FP32_GROUP_SIZE_LT_256 = 32;
constexpr uint32_t FP32_GROUP_SIZE_GT_256_LT_512 = 16;
constexpr uint32_t FP32_GROUP_SIZE_GT_512_LT_1024 = 8;
constexpr uint32_t FLOAT_BILINEAR_TILING_KEY = 1;
constexpr uint32_t FLOAT_NEAREST_TILING_KEY = 2;
constexpr uint32_t FLOAT16_BILINEAR_TILING_KEY = 3;
constexpr uint32_t FLOAT16_NEAREST_TILING_KEY = 4;
constexpr uint32_t BFLOAT16_BILINEAR_TILING_KEY = 5;
constexpr uint32_t BFLOAT16_NEAREST_TILING_KEY = 6;
constexpr uint32_t CHANNEL_256 = 256;
constexpr uint32_t CHANNEL_512 = 512;
constexpr uint32_t CHANNEL_1024 = 1024;
constexpr uint32_t BUFFER_NUM = 2;
constexpr uint32_t CONST_SEVENTEEN = 17;
constexpr uint32_t CONST_TWO = 2;
constexpr uint32_t DIM_INDEX0 = 0;
constexpr uint32_t DIM_INDEX1 = 1;
constexpr uint32_t DIM_INDEX2 = 2;
constexpr uint32_t DIM_INDEX3 = 3;
constexpr uint32_t RESERVED_UB = 2U * 1024U;
constexpr uint32_t RESERVED_UB_CAST = 20U * 1024U;
constexpr uint32_t ALIGN_256_BYTES = 256;
constexpr uint8_t SCHEDULE_MODE = 1;
constexpr uint32_t GRID_LAST_NUM = 2;
constexpr uint32_t VF_MAX_THREAD_NUM = 1024;
constexpr uint32_t VF_MAX_THREAD_NUM_DET = 256;
constexpr uint32_t REGBASE_MAX_CORE_NUM = 56;
constexpr uint32_t WORKSPACE_SIZE = 16 * 1024 * 1024;
constexpr uint32_t DETERMINISTIC_BATCH_NORM = 1;

static std::map<std::string, int> INTER_MODE_MAP = {{"bilinear", 0}, {"nearest", 1}, {"bicubic", 2}};
static std::map<std::string, int> PADDING_MODE_MAP = {{"zeros", 0}, {"border", 1}, {"reflection", 2}};
static std::map<bool, int> ALIGN_MODE_MAP = {{true, 1}, {false, 0}};
static std::map<ge::DataType, uint64_t> TILINGKEY_MAP = {{ge::DT_FLOAT16, 1}, {ge::DT_FLOAT, 2}};

template <typename TilingData, int32_t dataTypeLen>
class GridSampler2DGradTiling {
public:
    explicit GridSampler2DGradTiling(InputParamsInfo& param, const uint32_t inputCoreNum, const uint32_t inputUbSize,
        const uint32_t deterministic)
    {
        this->batch = param.batch;
        this->coreNum = inputCoreNum;
        this->channel = param.channel;
        this->height = param.height;
        this->width = param.width;
        this->gridH = param.gridH;
        this->gridW = param.gridW;
        this->interpolation = param.interpolation;
        this->padding = param.padding;
        this->alignCorners = param.alignCorners;
        this->tilingKey = param.tilingKey;
        this->ubSize = FloorAlign(inputUbSize, BYTE_BLOCK);
        this->dataTypeSize = dataTypeLen;
        this->elementsPerBlock = BYTE_BLOCK / dataTypeSize;
        this->isDeterministic = deterministic;
        this->regBase = param.regBase;
        return;
    }

    void GetTiling(TilingData* tilingData);

private:
    void GetUsedCore();
    void GetUsedCoreCast();
    void SplitUb();
    void FillTilingData(TilingData* tilingData);
    template <typename T1, typename T2>
    inline auto CeilDiv(T1 a, T2 b) -> T1
    {
        if (b == 0) {
            throw std::invalid_argument("CeilDiv Division by zero");
        }
        return (a + b - 1) / b;
    }
    template <typename T1, typename T2>
    inline auto FloorDiv(T1 a, T2 b) -> T1
    {
        return (a) / (b);
    }
    template <typename T1, typename T2>
    inline auto CeilAlign(T1 a, T2 b) -> T1
    {
        if (b == 0) {
            throw std::invalid_argument("CeilAlign Division by zero");
        }
        return (a + b - 1) / b * b;
    }
    template <typename T1, typename T2>
    inline auto FloorAlign(T1 a, T2 b) -> T1
    {
        if (b == 0) {
            throw std::invalid_argument("FloorAlign Division by zero");
        }
        return (a) / b * b;
    }
    inline uint32_t Ceil(uint32_t a, uint32_t b)
    {
        if (b == 0) {
            throw std::invalid_argument("Ceil Division by zero");
        }
        uint32_t tmp = a % b;
        if (tmp > 0) {
            return a / b + 1;
        } else {
            return a / b;
        }
    }

private:
    uint32_t batch = 0;
    uint32_t usedCoreNum = 0;
    uint32_t pNumPerCore = 0;
    uint32_t tailPNum = 0;
    uint32_t ubFactorElement = 0;
    uint32_t usedCoreNumCast = 0;
    uint32_t pNumPerCoreCast = 0;
    uint32_t tailPNumCast = 0;
    uint32_t castElement = 0;
    uint32_t channel = 0;
    uint32_t height = 0;
    uint32_t width = 0;
    uint32_t gridH;
    uint32_t gridW;
    uint32_t ubSize = 0;
    uint32_t coreNum = 0;
    uint32_t interpolation = 0;
    uint32_t padding = 0;
    uint32_t alignCorners = 0;
    uint32_t group = 0;
    uint32_t tilingKey = 0;
    uint8_t dataTypeSize = 0;
    uint8_t elementsPerBlock = 0;
    uint32_t divideUbNum = 1;
    uint32_t extraUbSize = 0;
    uint32_t isDeterministic = 0;
    uint32_t tailBNum = 0;
    bool regBase = false;
};

template <typename TilingData, int32_t dataTypeLen>
void GridSampler2DGradTiling<TilingData, dataTypeLen>::GetUsedCore()
{
    if (regBase) {
        uint32_t mulNCHW = static_cast<uint32_t>(batch * gridH * gridW * GRID_LAST_NUM);
        uint32_t tmpCoreNum = Ceil(mulNCHW, VF_MAX_THREAD_NUM);
        usedCoreNum = tmpCoreNum <= REGBASE_MAX_CORE_NUM ? tmpCoreNum : REGBASE_MAX_CORE_NUM;
        pNumPerCore = 0;
        tailPNum = 0;
        if (isDeterministic == 1){
            tmpCoreNum = Ceil(mulNCHW, VF_MAX_THREAD_NUM_DET);
            usedCoreNum = tmpCoreNum <= REGBASE_MAX_CORE_NUM ? tmpCoreNum : REGBASE_MAX_CORE_NUM;
            if (batch > coreNum) {
                usedCoreNum = coreNum;
                pNumPerCore = Ceil(batch, usedCoreNum);
                return;
            }
            usedCoreNum = batch;
            pNumPerCore = 1;
        }
        return;
    }
    if (isDeterministic == 0) {
        uint64_t mulBHW = static_cast<uint64_t>(batch) * static_cast<uint64_t>(gridH) * static_cast<uint64_t>(gridW);
        if (mulBHW <= this->coreNum) {
            this->usedCoreNum = mulBHW;
            this->pNumPerCore = 1;
            this->tailPNum = 0;
            return;
        }
        this->pNumPerCore = FloorDiv(mulBHW, this->coreNum);
        this->usedCoreNum = this->coreNum;
        this->tailPNum = mulBHW % usedCoreNum;
    } else {
        if (batch > coreNum) {
            usedCoreNum = coreNum;
            uint32_t bNumPerCore = FloorDiv(batch, usedCoreNum);
            tailBNum = static_cast<uint32_t>(batch % usedCoreNum);
            pNumPerCore = gridH * gridW * bNumPerCore;
            return;
        }
        usedCoreNum = batch;
        pNumPerCore = gridH * gridW;
    }
}

template <typename TilingData, int32_t dataTypeLen>
void GridSampler2DGradTiling<TilingData, dataTypeLen>::GetUsedCoreCast()
{
    size_t size = static_cast<size_t>(batch) * static_cast<size_t>(channel) * static_cast<size_t>(height) *
                  static_cast<size_t>(width);
    if (size <= this->usedCoreNum) {
        this->usedCoreNumCast = size;
        this->pNumPerCoreCast = 1;
        this->tailPNumCast = 0;
        return;
    }
    this->pNumPerCoreCast = FloorDiv(size, this->usedCoreNum);
    this->usedCoreNumCast = this->usedCoreNum;
    this->tailPNumCast = size % usedCoreNumCast;
}

template <typename TilingData, int32_t dataTypeLen>
void GridSampler2DGradTiling<TilingData, dataTypeLen>::SplitUb()
{
    uint32_t alignChannel = 0;
    if (tilingKey <= static_cast<uint32_t>(TILINGKEY_2)) {
        alignChannel = CeilAlign(channel, FP32_BLOCK_NUM);
    } else {
        alignChannel = CeilAlign(channel, FP16_BLOCK_NUM);
    }
    if (interpolation == 0U) {
        divideUbNum = static_cast<uint32_t>(BILINEAR_DIVIDE_UB_NUM);
        extraUbSize = CONST_SEVENTEEN * alignChannel * static_cast<uint32_t>(DTYPE_SIZE_32);
        group = 1U;
    } else if (interpolation == 1U) {
        divideUbNum = static_cast<uint32_t>(NEAREST_DIVIDE_UB_NUM);
        if (channel <= CHANNEL_256) {
            extraUbSize =
                BUFFER_NUM * (FP32_GROUP_SIZE_LT_256 + 1U) * alignChannel * static_cast<uint32_t>(DTYPE_SIZE_32);
            group = FP32_GROUP_SIZE_LT_256;
        } else if (channel <= CHANNEL_512) {
            extraUbSize =
                BUFFER_NUM * (FP32_GROUP_SIZE_GT_256_LT_512 + 1U) * alignChannel * static_cast<uint32_t>(DTYPE_SIZE_32);
            group = FP32_GROUP_SIZE_GT_256_LT_512;
        } else if (channel <= CHANNEL_1024) {
            extraUbSize = BUFFER_NUM * (FP32_GROUP_SIZE_GT_512_LT_1024 + 1U) * alignChannel *
                          static_cast<uint32_t>(DTYPE_SIZE_32);
            group = FP32_GROUP_SIZE_GT_512_LT_1024;
        } else {
            extraUbSize = BUFFER_NUM * CONST_TWO * alignChannel * static_cast<uint32_t>(DTYPE_SIZE_32);
            group = 1U;
        }
    }
    uint32_t tilingDataSize = CeilAlign(sizeof(TilingData), BYTE_BLOCK);
    uint32_t canUseUbSize = FloorAlign(ubSize - tilingDataSize, BYTE_BLOCK);
    if (canUseUbSize <= extraUbSize) {
        ubFactorElement = 0U;
        return;
    }
    ubFactorElement = FloorAlign((canUseUbSize - extraUbSize) / divideUbNum, ALIGN_256_BYTES) / DTYPE_SIZE_32;
    castElement = (canUseUbSize - RESERVED_UB_CAST) / static_cast<uint32_t>(CAST_DIVIDE_UB_NUM) /
                  static_cast<uint32_t>(DTYPE_SIZE_16);
}

template <typename TilingData, int32_t dataTypeLen>
void GridSampler2DGradTiling<TilingData, dataTypeLen>::FillTilingData(TilingData* tilingData)
{
    tilingData->set_batch(batch);
    tilingData->set_pNumPerCore(pNumPerCore);
    tilingData->set_tailPNum(tailPNum);
    tilingData->set_channel(channel);
    tilingData->set_height(height);
    tilingData->set_width(width);
    tilingData->set_gridH(gridH);
    tilingData->set_gridW(gridW);
    tilingData->set_blockNum(usedCoreNum);
    tilingData->set_ubFactorElement(ubFactorElement);
    tilingData->set_interpolation(interpolation);
    tilingData->set_padding(padding);
    tilingData->set_alignCorners(alignCorners);
    tilingData->set_group(group);
    tilingData->set_tilingKey(tilingKey);
    tilingData->set_usedCoreNumCast(usedCoreNumCast);
    tilingData->set_pNumPerCoreCast(pNumPerCoreCast);
    tilingData->set_tailPNumCast(tailPNumCast);
    tilingData->set_castElement(castElement);
    tilingData->set_isDeterministic(isDeterministic);
    tilingData->set_tailBNum(tailBNum);
}

template <typename TilingData, int32_t dataTypeLen>
void GridSampler2DGradTiling<TilingData, dataTypeLen>::GetTiling(TilingData* tilingData)
{
    GetUsedCore();
    GetUsedCoreCast();
    SplitUb();
    FillTilingData(tilingData);
}

template <typename TilingData, int32_t dataTypeLen>
void GetGridSampler2DGradTiling(TilingData* tilingData, InputParamsInfo& params, uint32_t coreNum, uint32_t ubSize,
    uint32_t deterministic)
{
    class GridSampler2DGradTiling<TilingData, dataTypeLen> tilingObj(params, coreNum, ubSize, deterministic);
    tilingObj.GetTiling(tilingData);
}

static void PrintTilingData(gert::TilingContext* tilingContext, GridSampler2DGradTilingData& tilingData)
{
    OP_LOGI(tilingContext->GetNodeName(), "Start printing");
    OP_LOGI(tilingContext->GetNodeName(), "batch is %u.", tilingData.get_batch());
    OP_LOGI(tilingContext->GetNodeName(), "channel is %u.", tilingData.get_channel());
    OP_LOGI(tilingContext->GetNodeName(), "height is %u.", tilingData.get_height());
    OP_LOGI(tilingContext->GetNodeName(), "width is %u.", tilingData.get_width());
    OP_LOGI(tilingContext->GetNodeName(), "gridH is %u.", tilingData.get_gridH());
    OP_LOGI(tilingContext->GetNodeName(), "gridW is %u.", tilingData.get_gridW());
    OP_LOGD(tilingContext->GetNodeName(), "blockNum is %u.", tilingData.get_blockNum());
    OP_LOGI(tilingContext->GetNodeName(), "pNumPerCore is %u.", tilingData.get_pNumPerCore());
    OP_LOGI(tilingContext->GetNodeName(), "tailPNum is %u.", tilingData.get_tailPNum());
    OP_LOGI(tilingContext->GetNodeName(), "ubFactorElement is %u.", tilingData.get_ubFactorElement());
    OP_LOGI(tilingContext->GetNodeName(), "interpolation is %u.", tilingData.get_interpolation());
    OP_LOGI(tilingContext->GetNodeName(), "padding is %u.", tilingData.get_padding());
    OP_LOGI(tilingContext->GetNodeName(), "alignCorners is %u.", tilingData.get_alignCorners());
    OP_LOGI(tilingContext->GetNodeName(), "group is %u.", tilingData.get_group());
    OP_LOGI(tilingContext->GetNodeName(), "tilingKey is %u.", tilingData.get_tilingKey());
    OP_LOGI(tilingContext->GetNodeName(), "usedCoreNumCast is %u.", tilingData.get_usedCoreNumCast());
    OP_LOGI(tilingContext->GetNodeName(), "pNumPerCoreCast is %u.", tilingData.get_pNumPerCoreCast());
    OP_LOGI(tilingContext->GetNodeName(), "tailPNumCast is %u.", tilingData.get_tailPNumCast());
    OP_LOGI(tilingContext->GetNodeName(), "castElement is %u.", tilingData.get_castElement());
    OP_LOGI(tilingContext->GetNodeName(), "End printing");
}

static ge::graphStatus GetNCHWInfo(gert::TilingContext* tilingContext, InputParamsInfo& params){
    const gert::StorageShape* gradShape = tilingContext->GetInputShape(GRAD_INPUT_INDEX);
    OP_CHECK_IF(
        (gradShape == nullptr), OP_LOGE(tilingContext->GetNodeName(), "Get StorageShape Failed."), return false);
    const gert::StorageShape* xShape = tilingContext->GetInputShape(X_INPUT_INDEX);
    OP_CHECK_IF((xShape == nullptr), OP_LOGE(tilingContext->GetNodeName(), "Get xShape Failed."), return false);
    const gert::StorageShape* gridShape = tilingContext->GetInputShape(GRID_INPUT_INDEX);
    OP_CHECK_IF((gridShape == nullptr), OP_LOGE(tilingContext->GetNodeName(), "Get gridShape Failed."), return false);
    if (xShape->GetStorageShape().GetDimNum() != CHECK_DIM_NUM) {
        OP_LOGD(tilingContext->GetNodeName(), "input dim is not 4, please check input");
        return ge::GRAPH_FAILED;
    }
    auto compileInfo = reinterpret_cast<const Tiling4GridSampler2DGradCompileInfo*>(tilingContext->GetCompileInfo());
    params.regBase = compileInfo->regBase;
    uint32_t outH = gradShape->GetStorageShape().GetDim(DIM_INDEX1);
    uint32_t outW = gradShape->GetStorageShape().GetDim(DIM_INDEX2);
    params.batch = xShape->GetStorageShape().GetDim(DIM_INDEX0);
    params.channel = xShape->GetStorageShape().GetDim(DIM_INDEX3);
    params.height = xShape->GetStorageShape().GetDim(DIM_INDEX1);
    params.width = xShape->GetStorageShape().GetDim(DIM_INDEX2);
    params.gridH = gridShape->GetStorageShape().GetDim(DIM_INDEX1);
    params.gridW = gridShape->GetStorageShape().GetDim(DIM_INDEX2);
    if (params.regBase) {
        outH = gradShape->GetStorageShape().GetDim(DIM_INDEX2);
        outW = gradShape->GetStorageShape().GetDim(DIM_INDEX3);
        params.channel = xShape->GetStorageShape().GetDim(DIM_INDEX1);
        params.height = xShape->GetStorageShape().GetDim(DIM_INDEX2);
        params.width = xShape->GetStorageShape().GetDim(DIM_INDEX3);
    }
    if (outH != params.gridH || outW != params.gridW) {
        OP_LOGW(tilingContext->GetNodeName(), "Please check grad's dims and grid's dims");
        return ge::GRAPH_FAILED;
    }
    return ge::GRAPH_SUCCESS;
}

static ge::graphStatus CheckInputInfo(gert::TilingContext* tilingContext, InputParamsInfo& params)
{
    if (GetNCHWInfo(tilingContext, params) != ge::GRAPH_SUCCESS) {
        OP_LOGW(tilingContext->GetNodeName(), "Failed to Parse input params NCHW, please check inputs");
        return ge::GRAPH_FAILED;
    }
    
    const gert::RuntimeAttrs* attrs = tilingContext->GetAttrs();
    OP_CHECK_IF((attrs == nullptr), OP_LOGE(tilingContext->GetNodeName(), "Get attrs Failed."), return false);
    const string interpolationMode = string(attrs->GetAttrPointer<char>(INTERPOLATION_MODE_INDEX));
    if (interpolationMode != "bilinear" && interpolationMode != "nearest") {
        OP_LOGW(tilingContext->GetNodeName(), "%s is not supported", interpolationMode.c_str());
        return ge::GRAPH_FAILED;
    }
    const string paddingMode = string(attrs->GetAttrPointer<char>(PADDING_MODE_INDEX));
    bool alignCorners = *tilingContext->GetAttrs()->GetAttrPointer<bool>(ALIGN_CORNERS_INDEX);
    params.interpolation = INTER_MODE_MAP[interpolationMode];
    params.padding = PADDING_MODE_MAP[paddingMode];
    params.alignCorners = ALIGN_MODE_MAP[alignCorners];

    if (params.padding < ZEROS || params.padding > REFLECTION) {
        OP_LOGW(tilingContext->GetNodeName(), "paddingMode %d is not supported", params.padding);
        return ge::GRAPH_FAILED;
    }
    return ge::GRAPH_SUCCESS;
}

static ge::graphStatus GetInputInfo(gert::TilingContext* tilingContext, InputParamsInfo& params, ge::DataType dtype)
{
    OP_LOGI(tilingContext->GetNodeName(), "strat to get input dims");
    if (CheckInputInfo(tilingContext, params) != ge::GRAPH_SUCCESS) {
        OP_LOGW(tilingContext->GetNodeName(), "Check inputs info failed, please check inputs");
        return ge::GRAPH_FAILED;
    }

    size_t xWorkspaceSize = params.batch * params.channel * params.height * params.width * sizeof(float);
    size_t sysWorkspaceSize = 16 * 1024 * 1024;

    if (dtype == ge::DT_FLOAT && params.interpolation == 0) {
        params.tilingKey = FLOAT_BILINEAR_TILING_KEY; // mode1: float, bilinear
    } else if (dtype == ge::DT_FLOAT && params.interpolation == 1) {
        params.tilingKey = FLOAT_NEAREST_TILING_KEY; // mode2: float, nearest
    } else if (dtype == ge::DT_FLOAT16 && params.interpolation == 0) {
        sysWorkspaceSize += xWorkspaceSize;
        params.tilingKey = FLOAT16_BILINEAR_TILING_KEY; // mode1: float16, bilinear
        tilingContext->SetScheduleMode(SCHEDULE_MODE);
    } else if (dtype == ge::DT_FLOAT16 && params.interpolation == 1) {
        sysWorkspaceSize += xWorkspaceSize;
        params.tilingKey = FLOAT16_NEAREST_TILING_KEY; // mode2: float16, nearest
        tilingContext->SetScheduleMode(SCHEDULE_MODE);
    } else if (dtype == ge::DT_BF16 && params.interpolation == 0) {
        sysWorkspaceSize += xWorkspaceSize;
        params.tilingKey = BFLOAT16_BILINEAR_TILING_KEY; // mode1: bfloat16, bilinear
        tilingContext->SetScheduleMode(SCHEDULE_MODE);
    } else if (dtype == ge::DT_BF16 && params.interpolation == 1) {
        sysWorkspaceSize += xWorkspaceSize;
        params.tilingKey = BFLOAT16_NEAREST_TILING_KEY; // mode2: bfloat16, nearest
        tilingContext->SetScheduleMode(SCHEDULE_MODE);
    }
    size_t* currentWorkspace = tilingContext->GetWorkspaceSizes(1);
    OP_CHECK_IF(
        (currentWorkspace == nullptr), OP_LOGE(tilingContext->GetNodeName(), "Get currentWorkspace Failed."),
        return false);
    currentWorkspace[0] = sysWorkspaceSize;
    if (params.regBase) {
        uint32_t isDeterministic = tilingContext->GetDeterministic();
        if (isDeterministic == 1) {
            params.tilingKey += 6;
            uint32_t batchNumPerCore = params.batch > REGBASE_MAX_CORE_NUM ? (params.batch / REGBASE_MAX_CORE_NUM) : 1;
            currentWorkspace[0] = WORKSPACE_SIZE + VF_MAX_THREAD_NUM_DET * sizeof(int32_t) * 2 * 4 * params.batch * batchNumPerCore;
        } else {
            currentWorkspace[0] = 0;
        }
    }
    OP_LOGI(tilingContext->GetNodeName(), "sysWorkspaceSize is %zu.", sysWorkspaceSize);
    return ge::GRAPH_SUCCESS;
}

static ge::graphStatus Tiling4GridSampler2DGrad(gert::TilingContext* tilingContext)
{
    OP_LOGI(tilingContext->GetNodeName(), "Tiling4GridSampler2DGrad start.");
    uint32_t deterministic = tilingContext->GetDeterministic();
    if (deterministic == 0) {
        OP_LOGI(tilingContext->GetNodeName(), "Deterministic status is closed.");
    } else {
        OP_LOGI(tilingContext->GetNodeName(), "Deterministic status is open.");
    }
    // get corenum and ubsize
    auto compileInfo = reinterpret_cast<const Tiling4GridSampler2DGradCompileInfo*>(tilingContext->GetCompileInfo());
    uint64_t ubSizePlatForm = compileInfo->ubSizePlatForm;
    uint32_t ubSize = static_cast<uint32_t>(ubSizePlatForm);
    uint32_t availableUb = ubSize - RESERVED_UB;
    uint32_t coreNum = 0;

    OP_LOGI(tilingContext->GetNodeName(), "ubSizePlatForm:%lu, coreNum:%u", ubSizePlatForm, coreNum);
    ge::DataType inputDatatype = tilingContext->GetInputDesc(0)->GetDataType();
    if (inputDatatype != ge::DT_FLOAT && !compileInfo->regBase) {
        coreNum = 1;
    } else { 
         coreNum = compileInfo->coreNum; 
    }
    tilingContext->SetNeedAtomic(true);

    InputParamsInfo params;
    if (GetInputInfo(tilingContext, params, inputDatatype) != ge::GRAPH_SUCCESS) {
        OP_LOGW(tilingContext->GetNodeName(), "Failed to Parse input params , please check inputs");
        return ge::GRAPH_FAILED;
    }
    GridSampler2DGradTilingData tilingData;
    if (inputDatatype == ge::DT_FLOAT16) {
        GetGridSampler2DGradTiling<GridSampler2DGradTilingData, DTYPE_SIZE_16>(
            &tilingData, params, coreNum, availableUb, deterministic);
    } else if (inputDatatype == ge::DT_FLOAT) {
        GetGridSampler2DGradTiling<GridSampler2DGradTilingData, DTYPE_SIZE_32>(
            &tilingData, params, coreNum, availableUb, deterministic);
    } else if (inputDatatype == ge::DT_BF16) {
        GetGridSampler2DGradTiling<GridSampler2DGradTilingData, DTYPE_SIZE_16>(
            &tilingData, params, coreNum, availableUb, deterministic);
    }
    OP_CHECK_IF(tilingData.get_ubFactorElement() <= 0, OP_LOGE(tilingContext->GetNodeName(), "ub space is not enough, please check input."), return ge::GRAPH_FAILED);
    // set tilingdata
    tilingContext->SetTilingKey(params.tilingKey);
    tilingContext->SetBlockDim(tilingData.get_blockNum());
    tilingData.SaveToBuffer(tilingContext->GetRawTilingData()->GetData(), tilingContext->GetRawTilingData()->GetCapacity());
    tilingContext->GetRawTilingData()->SetDataSize(tilingData.GetDataSize());
    PrintTilingData(tilingContext, tilingData);
    OP_LOGI(tilingContext->GetNodeName(), "GridSampler2DGrad tiling end running");
    return ge::GRAPH_SUCCESS;
}

static ge::graphStatus TilingPrepare4GridSampler2DGrad(gert::TilingParseContext* context)
{
    OP_LOGI(context->GetNodeName(), "TilingPrepare4GridSampler2DGrad start.");
    auto compileInfo = context->GetCompiledInfo<Tiling4GridSampler2DGradCompileInfo>();
    OP_CHECK_NULL_WITH_CONTEXT(context, compileInfo);
    auto platformInfo = context->GetPlatformInfo();
    OP_CHECK_NULL_WITH_CONTEXT(context, platformInfo);
    auto ascendcPlatform = platform_ascendc::PlatformAscendC(platformInfo);
    compileInfo->coreNum = ascendcPlatform.GetCoreNumAiv();
    compileInfo->regBase = Ops::Cv::OpTiling::IsRegbaseSocVersion(context);
    OP_CHECK_IF(
        (compileInfo->coreNum <= 0), OP_LOGE(context->GetNodeName(), "Failed to get core num."),
        return ge::GRAPH_FAILED);

    uint64_t ubSizePlatForm;
    ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::UB, ubSizePlatForm);
    compileInfo->ubSizePlatForm = ubSizePlatForm;
    OP_CHECK_IF(
        (compileInfo->ubSizePlatForm <= 0), OP_LOGE(context->GetNodeName(), "Failed to get ub size."),
        return ge::GRAPH_FAILED);
    OP_LOGI(context->GetNodeName(), "TilingPrepare4GridSampler2DGrad end.");

    return ge::GRAPH_SUCCESS;
}

IMPL_OP_OPTILING(GridSampler2DGrad)
    .Tiling(Tiling4GridSampler2DGrad)
    .TilingParse<Tiling4GridSampler2DGradCompileInfo>(TilingPrepare4GridSampler2DGrad);

} // namespace optiling