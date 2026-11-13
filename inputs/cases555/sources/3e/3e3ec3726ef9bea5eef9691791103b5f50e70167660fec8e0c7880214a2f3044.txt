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
 * \file top_k_v2_tiling_arch35.cpp
 * \brief top_k_v2 impl
 */
#include "top_k_v2_tiling_arch35.h"
#include "log/log.h"
#include "util/math_util.h"
#include "util/platform_util.h"
#include "atvoss/broadcast/broadcast_tiling.h"
#include "sort_with_index_tiling.h"

namespace optiling {
namespace topkV2 {
namespace topkV2DataInfo {
const uint32_t CONST_ZERO = 0;
const uint32_t CONST_TWO = 2;
const uint32_t CONST_THREE = 3;
const uint32_t MAX_K_FOR_INT64 = 2000;
const uint32_t BIN_NUM = 256;
const uint32_t TILE_SIZE_DECREASING_FACTOR = 32;
const uint32_t TMP_DATA_NUM = 7680;     // 默认UB一次性能处理的非64位数据的个数，可根据场景动态调整
const uint32_t TMP_DATA_NUM_B64 = 5120; // 默认UB一次性能处理的64位数据的个数，可根据场景动态调整
const uint64_t AGLIN_FACTOR = 32;
const uint32_t SMALL_MAX_DATA_SZIE = 1024;
const uint32_t MERGE_SORT_TILING_OFFSET = 10000;
const uint32_t SINGLE_CORE_MODE = 1;
const uint32_t MULT_CORE_MODE = 2;
const uint32_t MULT_CORE_OPTIM_MODE = 4;
const uint32_t SINGLE_BLOCK_MODE = 3;
const uint32_t SORT_AND_TOP_K_MODE = 5;
const uint32_t INT64_BYTE = 8;
const uint32_t INT32_BYTE = 4;
// SortAndTopk的阈值，排序轴大于该阈值的场景，走sortAndTopK模板
const uint32_t SORT_AND_TOP_K_THRESHOLD = 10000000;
const uint32_t CONST_SIMT_SPACE = 32768; // 获取到的UB大小需要预留32KB给simt
const uint32_t SUPPORT_SORT_MAX_BYTE_SIZE = 8000;
const uint32_t SUPPORT_SORT_MAX_SIZE = 2000;
const float LAST_LOOP_CORE_UTILIZATION = 0.7;
const uint32_t SMALL_LOOP_UPPER_NUM = 4;
const uint32_t SMALL_LOOP_LOWER_NUM = 2;
const uint32_t SIMT_UB = 32768;       // SortAndTopK模板需要预留32k给simt使用
const uint32_t UB_CONST_INT32 = 4096; // 输出idx为int32时kernel侧需要的固定ub大小
const uint32_t UB_CONST_INT64 = 7168; // 输出idx为int64时kernel侧需要的固定ub大小
const uint32_t CONST_10 = 10;
const uint32_t CONST_14 = 14;
const uint32_t CONST_2 = 2;
const uint32_t SMALL_TILE_DATA_NUM = 1024; // 测试数据得出一次至少处理1024，sort性能比较好
// 排序轴在int32范围内的最大值, 超过这个值, cutsum，前缀和就要用int64数据范围表示              
const uint32_t INT32_MAX_RANGE_VALUE_FOR_SORT = 1073741823; 

constexpr size_t SYS_WORK_SPACE_SIZE = static_cast<size_t>(16 * 1024 * 1024);
struct TopkTileInfo {
    uint32_t coreNumNeed = 0;
    int64_t lastDimTileNum = 0;
    uint32_t unsortedDimParallel = 1;
    uint32_t ubRealLoadDataNum = 0;
    uint32_t oneCoreRowNum = 1;
    uint32_t batchNumInUb = 1;
    uint32_t tailLoopBatchNum = 0;
    uint32_t tailBatchNum = 0;
    uint32_t tailTileNum = 0;
    int64_t topKOutLastAxisNum = 0;
};
struct SortTileInfo {
    uint32_t coreNumNeed = 0;
    uint32_t lastDimTileNum = 0;
    uint32_t unsortedDimParallel = 1;
    uint32_t oneCoreRowNum = 1;
    uint32_t ubSize = 0;
    uint32_t blockUbSize = 0;
    uint32_t dtypeSize = 0;
    uint32_t y2DtypeSize = 0;
    uint32_t maxCoreNum = 0;
    uint32_t numTileDataSize = 0;
    uint32_t sortLoopTimes = 0;
    uint32_t lastDimNeedCore = 0;
    uint32_t keyParams0 = 0;
    uint32_t keyParams1 = 0;
    uint32_t keyParams2 = 0;
    uint32_t keyParams3 = 0;
    uint32_t keyParams4 = 0;
    uint32_t keyParams5 = 0;
    uint32_t tmpUbSize = 0;
    bool isDescend = false;
    ge::DataType dataType = ge::DT_UINT8;
    uint32_t isInt32 = 0;
    int32_t xDimNum = 0;
    int64_t sortAxisNum = 1;
    int64_t unSortDimNum = 1;
    int64_t topKRealValue = 0;
    uint32_t tileDataSize = 0;
    uint32_t blockTileNum = 0;
    uint32_t tailTileNum = 0;
};
struct TopkComputingNowTileSizeInfo {
    ge::DataType dataType;
    ge::DataType indicesDType;
    bool isLargest = true;
    bool isSort = true;
    bool isInInt32Range = true;
    int64_t lastAxisNum = 0;
    int64_t kValue = 0;
    uint32_t maxCoreNum = 0;
    uint64_t ubSizePlatForm = 0;
    uint64_t ubBlockAlignSize = 0; // ub的对齐数值，当前为32
};
static const std::map<ge::DataType, uint32_t> tilingDataTypeKeyMap = {
    {ge::DT_INT64, 1004},  {ge::DT_INT32, 1003},   {ge::DT_INT16, 1002},  {ge::DT_INT8, 1001},
    {ge::DT_UINT64, 2004}, {ge::DT_UINT32, 2003},  {ge::DT_UINT16, 2002}, {ge::DT_UINT8, 2001},
    {ge::DT_FLOAT, 3003},  {ge::DT_FLOAT16, 3002}, {ge::DT_BF16, 4002}};
static const std::map<ge::DataType, uint32_t> tilingDataTypeBitMap = {
    {ge::DT_INT64, 8},  {ge::DT_INT32, 4},   {ge::DT_INT16, 2},  {ge::DT_INT8, 1},
    {ge::DT_UINT64, 8}, {ge::DT_UINT32, 4},  {ge::DT_UINT16, 2}, {ge::DT_UINT8, 1},
    {ge::DT_FLOAT, 4},  {ge::DT_FLOAT16, 2}, {ge::DT_BF16, 2}};
static const std::map<ge::DataType, uint32_t> optDataTypeBitMap = {
    {ge::DT_FLOAT, 4}, {ge::DT_FLOAT16, 2}, {ge::DT_BF16, 2}};
static const std::map<ge::DataType, uint32_t> b64DataTypeBitMap = {{ge::DT_INT64, 8}, {ge::DT_UINT64, 8}};
} // namespace topkV2DataInfo

uint32_t CeilAlignDiv(int64_t a, int64_t b)
{
    if (b == 0) {
        return static_cast<uint32_t>(a);
    }
    return static_cast<uint32_t>((a + b - 1) / b);
}

template <typename T>
auto CeilAlignDivMul(int64_t a, int64_t b) -> T const
{
    if (b == 0) {
        return static_cast<T>(a);
    }
    return static_cast<T>(((a + b - 1) / b) * b);
}

ge::graphStatus GetTopkApiTmpBufferSize(
    gert::TilingContext* context, TopKV2TilingDataSimd& topkTilingData, uint32_t needDataNum, int64_t kValue,
    bool isLargest, ge::DataType dtype, bool isSort, uint32_t nowTileSize)
{
    uint32_t maxBufferSize = 0;
    uint32_t minBufferSize = 0;
    uint32_t aglinInnerValue = ((needDataNum + topkV2DataInfo::AGLIN_FACTOR - 1) / topkV2DataInfo::AGLIN_FACTOR) *
                               topkV2DataInfo::AGLIN_FACTOR;
    uint32_t aglinKValue = 0;
    if (topkTilingData.get_modeType() == topkV2DataInfo::SINGLE_CORE_MODE) {
        aglinKValue = std::min(static_cast<int64_t>(needDataNum), kValue);
    } else {
        aglinKValue = std::min(static_cast<int64_t>(nowTileSize), kValue);
    }
    AscendC::TopKConfig topkConfig;
    topkConfig.algo = AscendC::TopKAlgo::RADIX_SELECT;
    topkConfig.order = AscendC::TopKOrder::UNSET;
    topkConfig.sorted = isSort;
    bool isSuccess = AscendC::GetTopKMaxMinTmpSize(
        aglinInnerValue, 1, aglinKValue, false, false, AscendC::TopKMode::TOPK_NORMAL, isLargest, dtype, topkConfig,
        maxBufferSize, minBufferSize);
    OP_LOGI("TopKV2TilingForAscendC", "Need tmp buffer %u byte for ac sort topk api", maxBufferSize);
    OP_LOGI(
        "TopKV2TilingForAscendC", "Init kValue=%ld aglinKValue=%u aglinInnerValue=%u", kValue, aglinKValue,
        aglinInnerValue);
    OP_CHECK_IF(
        false == isSuccess, OP_LOGE(context->GetNodeName(), "Get topk api temp buffer fail"), return ge::GRAPH_FAILED);
    topkTilingData.set_topkAcApiTmpBufferSize(maxBufferSize);
    return ge::GRAPH_SUCCESS;
}

uint32_t GetTopkTempBuffer(
    int64_t lastAxisNum, uint32_t tileData, uint32_t maxCoreNum, uint32_t xDtypeSize, uint32_t indexToDtypeSize,
    uint32_t indexDtypeSize, int64_t kValue, uint64_t ubSizePlatForm)
{
    OP_CHECK_IF(tileData == 0, OP_LOGE("TopkV2", "tileData is 0"), return ge::GRAPH_FAILED);
    uint32_t lastDimTileNum = (static_cast<uint32_t>(lastAxisNum) + tileData - 1) / tileData;
    OP_CHECK_IF(maxCoreNum == 0, OP_LOGE("TopkV2", "maxCoreNum is 0"), return ge::GRAPH_FAILED);
    uint32_t lastDimTileNumTimes = (lastDimTileNum + maxCoreNum - 1) / maxCoreNum;
    uint64_t initUb = indexDtypeSize * topkV2DataInfo::BIN_NUM * (lastDimTileNumTimes + 1) +
                      Ops::Base::CeilAlign(
                          static_cast<uint64_t>(sizeof(uint32_t) * lastDimTileNumTimes), topkV2DataInfo::AGLIN_FACTOR) *
                          topkV2DataInfo::CONST_TWO;
    uint32_t factor = xDtypeSize * topkV2DataInfo::CONST_TWO + indexDtypeSize + indexToDtypeSize;

    if (tileData < kValue) {
        factor += xDtypeSize + indexToDtypeSize + sizeof(int32_t);
    } else {
        initUb += Ops::Base::CeilAlign(static_cast<uint64_t>(kValue * sizeof(int32_t)), topkV2DataInfo::AGLIN_FACTOR) +
                  Ops::Base::CeilAlign(static_cast<uint64_t>(kValue * xDtypeSize), topkV2DataInfo::AGLIN_FACTOR) +
                  Ops::Base::CeilAlign(static_cast<uint64_t>(kValue * indexToDtypeSize), topkV2DataInfo::AGLIN_FACTOR);
    }
    OP_LOGI(
        "TopKV2TilingForAscendC", "GetTopkTempBuffer tileData=%u, initUb=%u, factor = %u, ubSizePlatForm=%u", tileData,
        initUb, factor, ubSizePlatForm);
    return ubSizePlatForm - initUb - factor * tileData;
}

uint32_t ComputeTopkTileData(
    gert::TilingContext* context, TopKV2TilingDataSimd& topkTilingData, ge::DataType dataType,
    ge::DataType indicesDType, bool isLargest, bool isSort, int64_t lastAxisNum, int64_t kValue, uint32_t maxCoreNum,
    uint64_t ubSizePlatForm)
{
    uint32_t xDtypeSize = static_cast<uint32_t>(topkV2DataInfo::tilingDataTypeBitMap.find(dataType)->second);
    uint32_t indexToDtypeSize = static_cast<uint32_t>(topkV2DataInfo::tilingDataTypeBitMap.find(indicesDType)->second);
    uint32_t indexDtypeSize = indexToDtypeSize;
    uint32_t tileData = (topkV2DataInfo::b64DataTypeBitMap.count(dataType) != 0) ? topkV2DataInfo::TMP_DATA_NUM_B64 :
                                                                                   topkV2DataInfo::TMP_DATA_NUM;
    uint32_t tmpUb = GetTopkTempBuffer(
        lastAxisNum, tileData, maxCoreNum, xDtypeSize, indexToDtypeSize, indexDtypeSize, kValue, ubSizePlatForm);
    OP_CHECK_IF(tileData == 0, OP_LOGE("TopkV2", "tileData is 0"), return ge::GRAPH_FAILED);
    int64_t lastDimTileNum = (static_cast<uint32_t>(lastAxisNum) + tileData - 1) / tileData;
    int64_t maxInputK = std::max(lastDimTileNum, kValue);
    GetTopkApiTmpBufferSize(context, topkTilingData, tileData, maxInputK, isLargest, dataType, isSort, tileData);
    uint32_t topkAcApiNeedBuffer = topkTilingData.get_topkAcApiTmpBufferSize();
    while (topkAcApiNeedBuffer > tmpUb) {
        tileData = tileData - topkV2DataInfo::BIN_NUM;
        OP_CHECK_IF(tileData == 0, OP_LOGE("TopkV2", "tileData is 0"), return ge::GRAPH_FAILED);
        lastDimTileNum = (static_cast<uint32_t>(lastAxisNum) + tileData - 1) / tileData;
        maxInputK = std::max(lastDimTileNum, kValue);
        GetTopkApiTmpBufferSize(context, topkTilingData, tileData, maxInputK, isLargest, dataType, isSort, tileData);
        topkAcApiNeedBuffer = topkTilingData.get_topkAcApiTmpBufferSize();
        tmpUb = GetTopkTempBuffer(
            lastAxisNum, tileData, maxCoreNum, xDtypeSize, indexToDtypeSize, indexDtypeSize, kValue, ubSizePlatForm);
    }

    OP_LOGI(
        "TopKV2TilingForAscendC", "tileData %u TempBuffer %u ApiTempBuffer %u", tileData, tmpUb, topkAcApiNeedBuffer);
    return tileData;
}

// 判断尾loop的核数利用率是否达标
bool IsLastLoopCoreUtilizationSuccess(uint32_t unsortedDimNum, uint32_t tmpOneCoreRowNum, uint32_t maxCoreNum)
{
    uint32_t virUnsortedDimNeedCoreNum = (unsortedDimNum + tmpOneCoreRowNum - 1) / tmpOneCoreRowNum;
    uint32_t sortLoopTimes = (virUnsortedDimNeedCoreNum + maxCoreNum - 1) / maxCoreNum;
    uint32_t lastLoopDimNum = unsortedDimNum % (maxCoreNum * tmpOneCoreRowNum);
    uint32_t lastLoopDimNeedCoreNum = lastLoopDimNum / tmpOneCoreRowNum;
    // 没有尾loop
    if (lastLoopDimNum == 0) {
        return true;
    }
    // 最后一次loop剩余待处理的轴数量/每个核处理的dim要大于0.7，确保最后一个loop有超过一半的核在处理，尽可能提高利用率
    if (sortLoopTimes >= topkV2DataInfo::SMALL_LOOP_LOWER_NUM && sortLoopTimes <= topkV2DataInfo::SMALL_LOOP_UPPER_NUM && 
        lastLoopDimNeedCoreNum < maxCoreNum * topkV2DataInfo::LAST_LOOP_CORE_UTILIZATION) {
        return false;
    }
    return true;
}

uint32_t ComputeMergeSortTileData(
    TopKV2TilingDataSimd& topkTilingData, ge::DataType dataType, ge::DataType indicesDType, int64_t lastAxisNum,
    uint32_t maxCoreNum, uint32_t unsortedDimNum, uint64_t ubSizePlatForm)
{
    uint32_t xDtypeSize = static_cast<uint32_t>(topkV2DataInfo::tilingDataTypeBitMap.find(dataType)->second);
    uint32_t indexToDtypeSize = static_cast<uint32_t>(topkV2DataInfo::tilingDataTypeBitMap.find(indicesDType)->second);
    uint32_t convertTypeSize = (dataType == ge::DT_BF16) ?
                                   topkV2DataInfo::optDataTypeBitMap.find(ge::DT_FLOAT)->second :
                                   topkV2DataInfo::optDataTypeBitMap.find(dataType)->second;

    uint32_t mergeSortAcApiNeedBuffer = topkTilingData.get_mergSortAcApiNeedBufferSize();
    uint32_t initUb = ubSizePlatForm - mergeSortAcApiNeedBuffer;
    uint32_t aglinNum = (static_cast<uint32_t>(lastAxisNum) + topkV2DataInfo::AGLIN_FACTOR - 1) /
                        topkV2DataInfo::AGLIN_FACTOR * topkV2DataInfo::AGLIN_FACTOR;
    uint32_t oneCoreRowNumSize = initUb - aglinNum * sizeof(uint32_t) -
                                 aglinNum * topkV2DataInfo::CONST_TWO * convertTypeSize * topkV2DataInfo::INT64_BYTE;
    uint32_t oneCoreRowNumMax =
        oneCoreRowNumSize / (aglinNum * topkV2DataInfo::CONST_TWO *
                             (topkV2DataInfo::CONST_TWO * xDtypeSize + indexToDtypeSize + convertTypeSize));
    uint32_t tileMaxData = oneCoreRowNumMax * aglinNum * 2;
    OP_LOGI("TopKV2TilingForAscendC", "tileMaxData=%u, maxCoreNum=%u", tileMaxData, maxCoreNum);


    // 思路：1.占满核,均匀分核 2.循环数尽可能小
    uint32_t tileData = topkV2DataInfo::TMP_DATA_NUM;
    uint32_t oneCoreRowNum = (tileData / topkV2DataInfo::CONST_TWO) / aglinNum;
    oneCoreRowNum = (oneCoreRowNum == 0 ? 1 : oneCoreRowNum);
    uint32_t virUnsortedDimNeedCoreNum = (unsortedDimNum + oneCoreRowNum - 1) / oneCoreRowNum;
    if (virUnsortedDimNeedCoreNum < maxCoreNum) {
        // 均匀分核
        OP_CHECK_IF(maxCoreNum == 0, OP_LOGE("TopkV2", "maxCoreNum is 0"), return ge::GRAPH_FAILED);
        oneCoreRowNum = (unsortedDimNum + maxCoreNum - 1) / maxCoreNum;
        oneCoreRowNum = (oneCoreRowNum == 0 ? 1 : oneCoreRowNum);
        virUnsortedDimNeedCoreNum = (unsortedDimNum + oneCoreRowNum - 1) / oneCoreRowNum;
        tileData = oneCoreRowNum * topkV2DataInfo::CONST_TWO * aglinNum;
        tileData = std::min(tileData, tileMaxData - topkV2DataInfo::BIN_NUM);
    } else {
        // 原先占满了核则增大tileData，但必须使核占满
        while (virUnsortedDimNeedCoreNum >= maxCoreNum && tileData < tileMaxData - topkV2DataInfo::BIN_NUM) {
            tileData += topkV2DataInfo::BIN_NUM;
            oneCoreRowNum = (tileData / topkV2DataInfo::CONST_TWO) / aglinNum;
            oneCoreRowNum = (oneCoreRowNum == 0 ? 1 : oneCoreRowNum);
            virUnsortedDimNeedCoreNum = (unsortedDimNum + oneCoreRowNum - 1) / oneCoreRowNum;
        }
        uint32_t tmpTileData = tileData;
        while (!IsLastLoopCoreUtilizationSuccess(unsortedDimNum, oneCoreRowNum, maxCoreNum)) {
            tileData -= topkV2DataInfo::BIN_NUM;
            // 若自减到0,说明没有合适的tileData,放弃均匀分核,采用前值
            if (tileData <= 0) {
                OP_LOGD("TopKV2TilingForAscendC", "final tileData=%u", tmpTileData);
                return tmpTileData;
            }
            oneCoreRowNum = (tileData / topkV2DataInfo::CONST_TWO) / aglinNum;
            oneCoreRowNum = (oneCoreRowNum == 0 ? 1 : oneCoreRowNum);
            virUnsortedDimNeedCoreNum = (unsortedDimNum + oneCoreRowNum - 1) / oneCoreRowNum;
        }
    }

    return tileData;
}

void SetMergeSortTmpSize(
    gert::TilingContext* context, ge::DataType dataType, int64_t lastAxisNum, TopKV2TilingDataSimd& topkTilingData)
{
    uint32_t aglinDataSize = (static_cast<uint32_t>(lastAxisNum) + topkV2DataInfo::AGLIN_FACTOR - 1) /
                             topkV2DataInfo::AGLIN_FACTOR * topkV2DataInfo::AGLIN_FACTOR;
    uint32_t dataTypeSize = (dataType == ge::DT_BF16) ? topkV2DataInfo::optDataTypeBitMap.find(ge::DT_FLOAT)->second :
                                                        topkV2DataInfo::optDataTypeBitMap.find(dataType)->second;
    auto platform_info = context->GetPlatformInfo();
    if (nullptr == platform_info) {
        OP_LOGE("TopKV2TilingForAscendC", "platform_info is nullptr.");
    }
    auto plat = platform_ascendc::PlatformAscendC(platform_info);
    uint32_t dataSizeNeed = AscendC::GetConcatTmpSize(plat, aglinDataSize, dataTypeSize);
    OP_LOGI("TopKV2TilingForAscendC", "Allocal buffer mergesort element len = %ld ac merge api", lastAxisNum);
    OP_LOGI("TopKV2TilingForAscendC", "Merge sort need tmp buffer %u byte for ac merge api", dataSizeNeed);
    topkTilingData.set_mergSortAcApiNeedBufferSize(dataSizeNeed);
}

void TileModeSmallSizeOptim(
    uint32_t unsortedDimNum, uint32_t maxCoreNum, int64_t lastAxisNum, TopKV2TilingDataSimd& topkTilingData,
    topkV2DataInfo::TopkTileInfo& topkTileInfo, uint32_t nowTileSize)
{
    uint32_t aglinNum = (static_cast<uint32_t>(lastAxisNum) + topkV2DataInfo::AGLIN_FACTOR - 1) /
                        topkV2DataInfo::AGLIN_FACTOR * topkV2DataInfo::AGLIN_FACTOR;
    uint32_t oneCoreRowNum = (nowTileSize / 2) / aglinNum;
    oneCoreRowNum = (oneCoreRowNum == 0 ? 1 : oneCoreRowNum);
    uint32_t virUnsortedDimNum = (unsortedDimNum + oneCoreRowNum - 1) / oneCoreRowNum;
    uint32_t coreNumNeed = 0;
    OP_CHECK_IF(maxCoreNum == 0, OP_LOGE("TopkV2", "maxCoreNum is 0"), return);
    uint32_t sortLoopTimes = (virUnsortedDimNum + maxCoreNum - 1) / maxCoreNum;
    if (sortLoopTimes == 1) {
        uint32_t realCoreNum = virUnsortedDimNum % maxCoreNum;
        if (realCoreNum == 0) {
            realCoreNum = maxCoreNum;
        }
        coreNumNeed = realCoreNum;
    } else {
        coreNumNeed = maxCoreNum;
    }
    topkTilingData.set_sortLoopTimes(sortLoopTimes);
    topkTilingData.set_lastDimTileNum(1);
    topkTilingData.set_unsortedDimParallel(coreNumNeed);
    topkTilingData.set_lastDimNeedCore(1);
    topkTilingData.set_numTileDataSize(lastAxisNum);
    topkTileInfo.ubRealLoadDataNum = lastAxisNum;
    topkTileInfo.coreNumNeed = coreNumNeed;
    topkTileInfo.lastDimTileNum = 1;
    topkTileInfo.unsortedDimParallel = coreNumNeed;
    topkTileInfo.oneCoreRowNum = oneCoreRowNum;
    OP_LOGI("TopKV2TilingForAscendC", "Small size opt mode oneCoreRowNum=%u", oneCoreRowNum);
    OP_LOGI(
        "TopKV2TilingForAscendC", "Small size opt mode coreNumNeed=%u sortLoopTimes=%u lastAxisNum=%ld", coreNumNeed,
        sortLoopTimes, lastAxisNum);
}

uint64_t GetSingleBlockTopkRunTimeNeedSpace(
    int64_t lastAxisNum, uint32_t tileData, uint32_t xDtypeSize, uint32_t indexToDtypeSize, int64_t kValue)
{
    OP_CHECK_IF(lastAxisNum == 0, OP_LOGE("TopkV2", "lastAxisNum is 0"), return ge::GRAPH_FAILED);
    uint32_t batchNumInUb = tileData / lastAxisNum;
    uint64_t aglinkValue = Ops::Base::CeilAlign(static_cast<uint64_t>(kValue), topkV2DataInfo::AGLIN_FACTOR);
    uint64_t aglinkValueMultDtypeSize =
        Ops::Base::CeilAlign(static_cast<uint64_t>(kValue * xDtypeSize), topkV2DataInfo::AGLIN_FACTOR);
    uint64_t aglinkValueMultIndexDtypeSize =
        Ops::Base::CeilAlign(static_cast<uint64_t>(kValue * indexToDtypeSize), topkV2DataInfo::AGLIN_FACTOR);
    uint64_t aglinIndicesOutTbuf =
        Ops::Base::CeilAlign(static_cast<uint64_t>(kValue * sizeof(int32_t)), topkV2DataInfo::AGLIN_FACTOR);
    uint64_t initUb = batchNumInUb * (aglinkValue * xDtypeSize + aglinkValueMultDtypeSize +
                                      aglinkValueMultIndexDtypeSize + aglinIndicesOutTbuf);
    return initUb;
}

uint32_t ComputeSingleBlockTileData(
    gert::TilingContext* context, TopKV2TilingDataSimd& topkTilingData, ge::DataType dataType,
    ge::DataType indicesDType, bool isLargest, bool isSort, int64_t lastAxisNum, int64_t kValue,
    uint64_t ubSizePlatForm)
{
    uint32_t xDtypeSize = static_cast<uint32_t>(topkV2DataInfo::tilingDataTypeBitMap.find(dataType)->second);
    uint32_t indexToDtypeSize = static_cast<uint32_t>(topkV2DataInfo::tilingDataTypeBitMap.find(indicesDType)->second);
    uint32_t tileData = (topkV2DataInfo::b64DataTypeBitMap.count(dataType) != 0) ? topkV2DataInfo::TMP_DATA_NUM_B64 :
                                                                                   topkV2DataInfo::TMP_DATA_NUM;
    GetTopkApiTmpBufferSize(context, topkTilingData, tileData, kValue, isLargest, dataType, isSort, tileData);
    uint32_t topkAcApiNeedBuffer = topkTilingData.get_topkAcApiTmpBufferSize();
    uint64_t needSpace =
        GetSingleBlockTopkRunTimeNeedSpace(lastAxisNum, tileData, xDtypeSize, indexToDtypeSize, kValue);
    while (topkAcApiNeedBuffer + needSpace > ubSizePlatForm) {
        tileData = tileData - topkV2DataInfo::BIN_NUM;
        GetTopkApiTmpBufferSize(context, topkTilingData, tileData, kValue, isLargest, dataType, isSort, tileData);
        topkAcApiNeedBuffer = topkTilingData.get_topkAcApiTmpBufferSize();
        needSpace = GetSingleBlockTopkRunTimeNeedSpace(lastAxisNum, tileData, xDtypeSize, indexToDtypeSize, kValue);
    }
    OP_LOGI(
        "TopKV2TilingForAscendC", "single block model tileData=%u, TempBuffer=%lu, ApiTempBuffer=%u", tileData,
        needSpace, topkAcApiNeedBuffer);
    return tileData;
}

uint64_t GetTopkMultiCoreOptimModeRunTimeNeedSpace(
    int64_t lastAxisNum, uint32_t tileData, uint32_t xDtypeSize, uint32_t indexToDtypeSize, int64_t kValue,
    uint64_t ubBlockAlignSize)
{
    uint64_t dataSpace = Ops::Base::CeilAlign(static_cast<uint64_t>(tileData), ubBlockAlignSize) * xDtypeSize;
    uint64_t indexSpace = Ops::Base::CeilAlign(static_cast<uint64_t>(tileData), ubBlockAlignSize) * sizeof(int32_t);
    uint64_t topkOutDataSpace = Ops::Base::CeilAlign(static_cast<uint64_t>(kValue * xDtypeSize), ubBlockAlignSize);
    uint64_t topkOutIndexSpace =
        Ops::Base::CeilAlign(static_cast<uint64_t>(kValue * sizeof(int32_t)), ubBlockAlignSize);
    uint64_t tempConversionSpace =
        Ops::Base::CeilAlign(static_cast<uint64_t>(kValue * indexToDtypeSize), ubBlockAlignSize);
    uint64_t initUb = dataSpace + indexSpace + topkOutDataSpace + topkOutIndexSpace + tempConversionSpace;
    OP_LOGI(
        "TopKV2TilingForAscendC",
        "compute runTime space lastAxisNum =%u, tileData=%lu, xDtypeSize=%u, indexToDtypeSize=%u, kValue=%u, initUb=%u",
        lastAxisNum, tileData, xDtypeSize, indexToDtypeSize, kValue, initUb);
    return initUb;
}

bool IsMultiCoreOptimMode(
    gert::TilingContext* context, uint32_t& inputNowTileSize, TopKV2TilingDataSimd& topkTilingData,
    topkV2DataInfo::TopkComputingNowTileSizeInfo& computingNowTileSizeInfo)
{
    // get variable
    ge::DataType dataType = computingNowTileSizeInfo.dataType;
    ge::DataType indicesDType = computingNowTileSizeInfo.indicesDType;
    int64_t kValue = computingNowTileSizeInfo.kValue;
    bool isLargest = computingNowTileSizeInfo.isLargest;
    bool isSort = computingNowTileSizeInfo.isSort;
    int64_t lastAxisNum = computingNowTileSizeInfo.lastAxisNum;
    uint64_t ubBlockAlignSize = computingNowTileSizeInfo.ubBlockAlignSize;

    // computing runtime local tensor need space and topk api need space
    uint32_t xDtypeSize = static_cast<uint32_t>(topkV2DataInfo::tilingDataTypeBitMap.find(dataType)->second);
    uint32_t indexToDtypeSize = static_cast<uint32_t>(topkV2DataInfo::tilingDataTypeBitMap.find(indicesDType)->second);
    int32_t tileData = (topkV2DataInfo::b64DataTypeBitMap.count(dataType) != 0) ? topkV2DataInfo::TMP_DATA_NUM_B64 :
                                                                                  topkV2DataInfo::TMP_DATA_NUM;
    if (tileData < kValue) {
        OP_LOGD("TopKV2TilingForAscendC", "k is greater than init tileData.");
        return false;
    }
    GetTopkApiTmpBufferSize(context, topkTilingData, tileData, kValue, isLargest, dataType, isSort, tileData);
    uint32_t topkAcApiNeedBuffer = topkTilingData.get_topkAcApiTmpBufferSize();
    uint64_t needSpace = GetTopkMultiCoreOptimModeRunTimeNeedSpace(
        lastAxisNum, tileData, xDtypeSize, indexToDtypeSize, kValue, ubBlockAlignSize);
    OP_LOGD(
        "TopKV2TilingForAscendC",
        "multi core optim model init tileData=%u, init tempBuffer=%lu, init apiTempBuffer=%u, xDtypeSize=%u, "
        "indexToDtypeSize=%u",
        tileData, needSpace, topkAcApiNeedBuffer, xDtypeSize, indexToDtypeSize);
    while (topkAcApiNeedBuffer + needSpace > computingNowTileSizeInfo.ubSizePlatForm) {
        tileData = tileData - topkV2DataInfo::TILE_SIZE_DECREASING_FACTOR;
        if (tileData < kValue) {
            OP_LOGD("TopKV2TilingForAscendC", "k value is greater than tilingData.");
            return false;
        }
        GetTopkApiTmpBufferSize(context, topkTilingData, tileData, kValue, isLargest, dataType, isSort, tileData);
        topkAcApiNeedBuffer = topkTilingData.get_topkAcApiTmpBufferSize();
        needSpace = GetTopkMultiCoreOptimModeRunTimeNeedSpace(
            lastAxisNum, tileData, xDtypeSize, indexToDtypeSize, kValue, ubBlockAlignSize);
        OP_LOGD(
            "TopKV2TilingForAscendC",
            "multi core optim model now tileData=%u, now tempBuffer=%lu, now apiTempBuffer=%u.", tileData, needSpace,
            topkAcApiNeedBuffer);
    }

    // 在确定正确的tileData之后，必须确保尾轴是多核模式，否则会出现多核的tiling模式，走的是singleBlock的模板
    if (tileData >= lastAxisNum) {
        OP_LOGD("TopKV2TilingForAscendC", "tileData is greater than lastAxisNum.");
        return false;
    }

    // compute tileNum multiply by kValue
    OP_CHECK_IF(tileData == 0, OP_LOGE("TopkV2", "tileData is 0"), return ge::GRAPH_FAILED);
    uint32_t lastDimTileNum = (lastAxisNum + tileData - 1) / tileData;
    uint32_t inputTopkSize = kValue * lastDimTileNum;
    if (inputTopkSize <= static_cast<uint32_t>(tileData)) {
        inputNowTileSize = tileData;
        OP_LOGI(
            "TopKV2TilingForAscendC", "multi core optim model final inputNowTileSize=%u, inputTopkSize=%u",
            inputNowTileSize, inputTopkSize);
        return true;
    }
    return false;
}

uint64_t GetSingleCoreTopkRunTimeNeedSpace(
    int64_t lastAxisNum, uint32_t nowTileSize, uint32_t xDtypeSize, uint32_t indexToDtypeSize, int64_t kValue,
    bool isSort)
{
    OP_CHECK_IF(nowTileSize == 0, OP_LOGE("TopkV2", "nowTileSize is 0"), return ge::GRAPH_FAILED);
    uint32_t lastDimTileNum = (lastAxisNum + nowTileSize - 1) / nowTileSize;
    uint32_t tileNum = lastAxisNum / lastDimTileNum;
    uint32_t tailTileNum = lastAxisNum % lastDimTileNum;
    tileNum = tailTileNum == 0 ? tileNum : tileNum + 1;
    uint32_t outQueueNum = std::min(tileNum, static_cast<uint32_t>(kValue));

    int64_t int32Max = static_cast<int64_t>(std::numeric_limits<int32_t>::max());
    uint32_t isInInt32Range = static_cast<uint32_t>(lastAxisNum <= int32Max);
    uint32_t indexTypeSize = isInInt32Range ? sizeof(int32_t) : sizeof(int64_t);

    uint64_t initUb = 0;
    uint64_t inputXQueValue =
        Ops::Base::CeilAlign(static_cast<uint64_t>(tileNum), topkV2DataInfo::AGLIN_FACTOR) * xDtypeSize;
    initUb += inputXQueValue;
    uint64_t valuesQueValue =
        Ops::Base::CeilAlign(static_cast<uint64_t>(outQueueNum * xDtypeSize), topkV2DataInfo::AGLIN_FACTOR);
    initUb += valuesQueValue;
    uint64_t indicesQueValue =
        Ops::Base::CeilAlign(static_cast<uint64_t>(outQueueNum * indexToDtypeSize), topkV2DataInfo::AGLIN_FACTOR);
    initUb += indicesQueValue;
    uint64_t outBufValue =
        Ops::Base::CeilAlign(static_cast<uint64_t>(outQueueNum * sizeof(int32_t)), topkV2DataInfo::AGLIN_FACTOR);
    initUb += outBufValue;

    uint64_t tileCusumTBufValue = topkV2DataInfo::BIN_NUM * sizeof(int32_t);
    initUb += tileCusumTBufValue;
    uint64_t cusumTBufValue = topkV2DataInfo::BIN_NUM * indexTypeSize;
    initUb += cusumTBufValue;
    uint64_t tileKTBufValue =
        Ops::Base::CeilAlign(static_cast<uint64_t>(lastDimTileNum * sizeof(int32_t)), topkV2DataInfo::AGLIN_FACTOR);
    initUb += tileKTBufValue;
    uint64_t unsignedInputXTBufValue =
        Ops::Base::CeilAlign(static_cast<uint64_t>(tileNum * sizeof(int32_t)), topkV2DataInfo::AGLIN_FACTOR);
    initUb += unsignedInputXTBufValue;
    uint64_t tileCusumInt64TBufValue = topkV2DataInfo::BIN_NUM * indexTypeSize;
    initUb += tileCusumInt64TBufValue;

    uint64_t sortSrcIndexTBufValue = 0;
    if (isSort && kValue * xDtypeSize <= topkV2DataInfo::SUPPORT_SORT_MAX_BYTE_SIZE) {
        sortSrcIndexTBufValue =
            Ops::Base::CeilAlign(static_cast<uint64_t>(kValue * indexToDtypeSize), topkV2DataInfo::AGLIN_FACTOR);
    }
    initUb += sortSrcIndexTBufValue;
    return initUb;
}

uint32_t ComputeSingleCoreTileData(
    gert::TilingContext* context, TopKV2TilingDataSimd& topkTilingData, ge::DataType dataType,
    ge::DataType indicesDType, bool isLargest, bool isSort, int64_t lastAxisNum, int64_t kValue,
    uint64_t ubSizePlatForm)
{
    uint32_t xDtypeSize = static_cast<uint32_t>(topkV2DataInfo::tilingDataTypeBitMap.find(dataType)->second);
    uint32_t indexToDtypeSize = static_cast<uint32_t>(topkV2DataInfo::tilingDataTypeBitMap.find(indicesDType)->second);
    uint32_t tileData = (topkV2DataInfo::b64DataTypeBitMap.count(dataType) != 0) ? topkV2DataInfo::TMP_DATA_NUM_B64 :
                                                                                   topkV2DataInfo::TMP_DATA_NUM;
    GetTopkApiTmpBufferSize(context, topkTilingData, tileData, kValue, isLargest, dataType, isSort, tileData);
    uint32_t topkAcApiNeedBuffer = topkTilingData.get_topkAcApiTmpBufferSize();
    uint64_t needSpace =
        GetSingleCoreTopkRunTimeNeedSpace(lastAxisNum, tileData, xDtypeSize, indexToDtypeSize, kValue, isSort);
    OP_LOGI(
        "TopKV2TilingForAscendC", "single core model init tileData=%u, init TempBuffer=%lu, now ApiTempBuffer=%u",
        tileData, needSpace, topkAcApiNeedBuffer);
    while (topkAcApiNeedBuffer + needSpace > ubSizePlatForm) {
        tileData = tileData - topkV2DataInfo::BIN_NUM;
        OP_CHECK_IF(tileData == 0, OP_LOGE("TopkV2", "tileData is 0"), return ge::GRAPH_FAILED);
        GetTopkApiTmpBufferSize(context, topkTilingData, tileData, kValue, isLargest, dataType, isSort, tileData);
        topkAcApiNeedBuffer = topkTilingData.get_topkAcApiTmpBufferSize();
        needSpace =
            GetSingleCoreTopkRunTimeNeedSpace(lastAxisNum, tileData, xDtypeSize, indexToDtypeSize, kValue, isSort);
        OP_LOGI(
            "TopKV2TilingForAscendC", "single core model now tileData=%u, now TempBuffer=%lu, now ApiTempBuffer=%u",
            tileData, needSpace, topkAcApiNeedBuffer);
    }
    OP_LOGI(
        "TopKV2TilingForAscendC", "single core model tileData=%u, TempBuffer=%lu, ApiTempBuffer=%u", tileData,
        needSpace, topkAcApiNeedBuffer);
    return tileData;
}

void TileModeSmallSize(
    uint32_t unsortedDimNum, uint32_t maxCoreNum, int64_t lastAxisNum, TopKV2TilingDataSimd& topkTilingData,
    topkV2DataInfo::TopkTileInfo& topkTileInfo, uint32_t nowTileSize)
{
    OP_CHECK_IF(lastAxisNum == 0, OP_LOGE("TopkV2", "lastAxisNum is 0"), return);
    uint32_t batchNumInUb = nowTileSize / lastAxisNum;
    uint32_t batchNumSingleLoop = maxCoreNum * batchNumInUb;
    uint32_t sortLoopTimes = unsortedDimNum / batchNumSingleLoop;

    uint32_t tailBatchNumTotal = unsortedDimNum % batchNumSingleLoop;
    uint32_t tailBatchNumSingleCore = 0;
    uint32_t tailBatchNum = 0;
    OP_CHECK_IF(maxCoreNum == 0, OP_LOGE("TopkV2", "maxCoreNum is 0"), return);
    uint32_t coreNumNeed = maxCoreNum;
    if (tailBatchNumTotal != 0) {
        tailBatchNumSingleCore = tailBatchNumTotal / maxCoreNum;
        tailBatchNum = tailBatchNumTotal % maxCoreNum;
        sortLoopTimes += 1;
    }
    topkTilingData.set_sortLoopTimes(sortLoopTimes);
    topkTilingData.set_unsortedDimParallel(coreNumNeed);
    topkTilingData.set_numTileDataSize(lastAxisNum);
    topkTilingData.set_lastDimTileNum(1);
    topkTilingData.set_lastDimNeedCore(1);
    topkTileInfo.batchNumInUb = batchNumInUb;
    topkTileInfo.tailLoopBatchNum = tailBatchNumSingleCore;
    topkTileInfo.tailBatchNum = tailBatchNum;

    topkTileInfo.ubRealLoadDataNum = lastAxisNum;
    topkTileInfo.coreNumNeed = coreNumNeed;
    topkTileInfo.lastDimTileNum = 1;
    topkTileInfo.unsortedDimParallel = coreNumNeed;
    OP_LOGI(
        "TopKV2TilingForAscendC", "Small size mode coreNumNeed=%u sortLoopTimes=%u lastAxisNum=%ld", coreNumNeed,
        sortLoopTimes, lastAxisNum);
}

void TileModeSingleCore(
    uint32_t unsortedDimNum, uint32_t maxCoreNum, uint32_t lastAxisNum, TopKV2TilingDataSimd& topkTilingData,
    topkV2DataInfo::TopkTileInfo& topkTileInfo, uint32_t nowTileSize)
{
    OP_CHECK_IF(nowTileSize == 0, OP_LOGE("TopkV2", "nowTileSize is 0"), return);
    uint32_t lastDimTileNum = (lastAxisNum + nowTileSize - 1) / nowTileSize;
    OP_CHECK_IF(maxCoreNum == 0, OP_LOGE("TopkV2", "maxCoreNum is 0"), return);
    uint32_t sortLoopTimes = unsortedDimNum / maxCoreNum;
    uint32_t tailBatchNum = unsortedDimNum % maxCoreNum;
    uint32_t tileNum = lastAxisNum / lastDimTileNum;
    uint32_t tailTileNum = lastAxisNum % lastDimTileNum;

    topkTilingData.set_lastDimTileNum(lastDimTileNum);
    topkTilingData.set_sortLoopTimes(sortLoopTimes);
    topkTilingData.set_numTileDataSize(tileNum);
    topkTilingData.set_unsortedDimParallel(maxCoreNum);

    topkTilingData.set_modeType(topkV2DataInfo::SINGLE_CORE_MODE);

    topkTileInfo.tailBatchNum = tailBatchNum;
    topkTileInfo.tailTileNum = tailTileNum;

    topkTileInfo.ubRealLoadDataNum = tileNum + 1;
    topkTileInfo.coreNumNeed = maxCoreNum;
    topkTileInfo.lastDimTileNum = lastDimTileNum;
    topkTileInfo.unsortedDimParallel = maxCoreNum;

    OP_LOGI(
        "TopKV2TilingForAscendC", "Single core mode coreNumNeed=%u sortLoopTimes=%u lastAxisNum=%u",
        topkTileInfo.coreNumNeed, sortLoopTimes, lastAxisNum);
}

void TileModeMediumSize(
    uint32_t unsortedDimNum, uint32_t maxCoreNum, int64_t lastAxisNum, TopKV2TilingDataSimd& topkTilingData,
    topkV2DataInfo::TopkTileInfo& topkTileInfo, uint32_t nowTileSize)
{
    if (topkTileInfo.topKOutLastAxisNum > topkV2DataInfo::MAX_K_FOR_INT64) {
        nowTileSize /= topkV2DataInfo::CONST_TWO;
    }
    OP_CHECK_IF(nowTileSize == 0, OP_LOGE("TopkV2", "nowTileSize is 0"), return);
    uint32_t lastDimTileNum = (static_cast<uint32_t>(lastAxisNum) + nowTileSize - 1) / nowTileSize;
    uint32_t unsortedDimParallel = maxCoreNum / lastDimTileNum;
    uint32_t coreNumNeed = lastDimTileNum * unsortedDimParallel;
    uint32_t sortLoopTimes = (unsortedDimNum + unsortedDimParallel - 1) / unsortedDimParallel;
    if (sortLoopTimes == 1) {
        coreNumNeed = unsortedDimNum * lastDimTileNum;
        unsortedDimParallel = unsortedDimNum;
    }
    topkTilingData.set_modeType(topkV2DataInfo::MULT_CORE_MODE);
    topkTilingData.set_sortLoopTimes(sortLoopTimes);
    topkTilingData.set_lastDimTileNum(lastDimTileNum);
    topkTilingData.set_unsortedDimParallel(unsortedDimParallel);
    topkTilingData.set_lastDimNeedCore(lastDimTileNum);
    topkTilingData.set_numTileDataSize(nowTileSize);
    topkTileInfo.ubRealLoadDataNum = nowTileSize;
    // 为了适配TopK拼接sortwithindex，TopK MediumSize Mode需要满核运行
    topkTileInfo.coreNumNeed = maxCoreNum;
    topkTileInfo.lastDimTileNum = lastDimTileNum;
    topkTileInfo.unsortedDimParallel = unsortedDimParallel;
    OP_LOGI(
        "TopKV2TilingForAscendC", "Medium size mode coreNumNeed=%u sortLoopTimes=%u lastAxisNum=%ld", coreNumNeed,
        sortLoopTimes, lastAxisNum);
    OP_LOGI(
        "TopKV2TilingForAscendC", "Medium size mode lastDimTileNum=%u unsortedDimParallel=%u lastDimRealCore=%u",
        lastDimTileNum, unsortedDimParallel, lastDimTileNum);
}
void TileModeBigSize(
    uint32_t unsortedDimNum, uint32_t maxCoreNum, int64_t lastAxisNum, TopKV2TilingDataSimd& topkTilingData,
    topkV2DataInfo::TopkTileInfo& topkTileInfo, uint32_t nowTileSize)
{
    if (topkTileInfo.topKOutLastAxisNum > topkV2DataInfo::MAX_K_FOR_INT64) {
        nowTileSize /= topkV2DataInfo::CONST_TWO;
    }
    OP_CHECK_IF(nowTileSize == 0, OP_LOGE("TopkV2", "nowTileSize is 0"), return);
    int64_t lastDimTileNum = (lastAxisNum + nowTileSize - 1) / nowTileSize;
    uint32_t coreNumNeed = static_cast<uint32_t>(std::min(static_cast<int64_t>(maxCoreNum), lastDimTileNum));
    topkTilingData.set_modeType(topkV2DataInfo::MULT_CORE_MODE);
    topkTilingData.set_sortLoopTimes(unsortedDimNum);
    topkTilingData.set_lastDimTileNum(lastDimTileNum);
    topkTilingData.set_unsortedDimParallel(1);
    topkTilingData.set_lastDimNeedCore(coreNumNeed);
    topkTilingData.set_numTileDataSize(nowTileSize);
    topkTileInfo.ubRealLoadDataNum = nowTileSize;
    // 为了适配TopK拼接sortwithindex，TopK  BigSize Mode需要满核运行
    topkTileInfo.coreNumNeed = maxCoreNum;
    topkTileInfo.lastDimTileNum = lastDimTileNum;
    topkTileInfo.unsortedDimParallel = 1;
    OP_LOGI(
        "TopKV2TilingForAscendC", "Big size mode coreNumNeed=%u sortLoopTimes=%u lastAxisNum=%ld", coreNumNeed,
        unsortedDimNum, lastAxisNum);
    OP_LOGI(
        "TopKV2TilingForAscendC", "Big size mode lastDimTileNum=%ld unsortedDimParallel=1 lastDimRealCore=%u",
        lastDimTileNum, coreNumNeed);
}

void TileMultiCoreOptimSize(
    uint32_t unsortedDimNum, uint32_t maxCoreNum, int64_t lastAxisNum, TopKV2TilingDataSimd& topkTilingData,
    topkV2DataInfo::TopkTileInfo& topkTileInfo, uint32_t nowTileSize)
{
    const uint32_t sortedDimParallelData = (nowTileSize * maxCoreNum) / 2;
    if (topkTileInfo.topKOutLastAxisNum > topkV2DataInfo::MAX_K_FOR_INT64) {
        nowTileSize *= topkV2DataInfo::CONST_TWO;
    }
    if (lastAxisNum <= sortedDimParallelData) {
        TileModeMediumSize(unsortedDimNum, maxCoreNum, lastAxisNum, topkTilingData, topkTileInfo, nowTileSize);
    } else {
        TileModeBigSize(unsortedDimNum, maxCoreNum, lastAxisNum, topkTilingData, topkTileInfo, nowTileSize);
    }
}

ge::graphStatus IsValidParam(gert::TilingContext* context)
{
    OP_CHECK_IF(context == nullptr, OP_LOGE("TopKV2", "Tiling Context is nullptr"), return ge::GRAPH_FAILED);
    OP_CHECK_IF(
        context->GetInputDesc(0) == nullptr || context->GetInputDesc(1) == nullptr,
        OP_LOGE(context->GetNodeName(), "Input desc is nullptr"), return ge::GRAPH_FAILED);
    auto inputDataType = context->GetInputDesc(0)->GetDataType();
    auto kDataType = context->GetInputDesc(1)->GetDataType();
    OP_CHECK_IF(
        context->GetOutputShape(0) == nullptr || context->GetOutputShape(1) == nullptr,
        OP_LOGE(context->GetNodeName(), "Output Shape is nullptr"), return ge::GRAPH_FAILED);
    const gert::Shape outValueShape = context->GetOutputShape(0)->GetStorageShape();
    const gert::Shape outIndexShape = context->GetOutputShape(1)->GetStorageShape();
    OP_CHECK_IF(
        context->GetOutputDesc(0) == nullptr || context->GetOutputDesc(1) == nullptr,
        OP_LOGE(context->GetNodeName(), "Output desc is nullptr"), return ge::GRAPH_FAILED);
    auto outputValueDataType = context->GetOutputDesc(0)->GetDataType();
    auto outputIndexDataType = context->GetOutputDesc(1)->GetDataType();
    OP_CHECK_IF(
        topkV2DataInfo::tilingDataTypeKeyMap.count(inputDataType) == 0,
        OP_LOGE(context->GetNodeName(), "Not support data type"), return ge::GRAPH_FAILED);
    OP_CHECK_IF(
        inputDataType != outputValueDataType,
        OP_LOGE(context->GetNodeName(), "Input data type should equal to output value type"), return ge::GRAPH_FAILED);
    OP_CHECK_IF(
        kDataType != ge::DT_INT32 && kDataType != ge::DT_INT64,
        OP_LOGE(context->GetNodeName(), "Input k data type should equal to int32 or int64"), return ge::GRAPH_FAILED);
    OP_CHECK_IF(
        outputIndexDataType != ge::DT_INT32 && outputIndexDataType != ge::DT_INT64,
        OP_LOGE(context->GetNodeName(), "Output index data type should equal to int32 or int64"),
        return ge::GRAPH_FAILED);
    OP_CHECK_IF(
        outValueShape != outIndexShape,
        OP_LOGE(context->GetNodeName(), "Output value shape should equal to output index shape"),
        return ge::GRAPH_FAILED);
    return ge::GRAPH_SUCCESS;
}

bool IsModeSingleCore(uint32_t unsortedDimNum, uint32_t maxCoreNum)
{
    // B轴小于核数，则不走该模板
    if (unsortedDimNum < maxCoreNum) {
        return false;
    }
    // B轴均匀分核确定是有性能收益；
    // 均匀分核场景，需要考虑尾行处理的时间与核间同步时间的均衡；
    // 目前测试非均匀分核性能也有提升，故不区分是否均匀分核，直接返回true，后面如果有性能走这个模板有性能劣化可以考虑这一点
    return true;
}

// sort核间模板tiling计算相关函数
uint32_t ComputeRemainUb(topkV2DataInfo::SortTileInfo &sortTileInfo, uint32_t tileData, uint32_t ubExtra, uint32_t tileFactor)
{
    uint32_t tmpUb = sortTileInfo.ubSize - (ubExtra + tileFactor * tileData);
    return tmpUb;
}

void SetSortTmpSize(ge::DataType dataType, uint32_t tileData, bool isDescend, topkV2DataInfo::SortTileInfo &sortTileInfo)
{
    int64_t realLen = std::min(sortTileInfo.sortAxisNum, static_cast<int64_t>(tileData));
    std::vector<int64_t> shapeVec = { realLen };
    ge::Shape srcShape(shapeVec);
    AscendC::SortConfig config;
    config.type = AscendC::SortType::RADIX_SORT;
    config.isDescend = isDescend;
    config.hasSrcIndex = false;
    config.hasDstIndex = true;
    uint32_t maxValue = 0, minValue = 0;
    AscendC::GetSortMaxMinTmpSize(srcShape, dataType, ge::DT_UINT32, false, config, maxValue, minValue);
    OP_LOGI("RadixSortTiling", "api of sort shape is %ld, maxUb is %u", realLen, maxValue);
    sortTileInfo.tmpUbSize = maxValue;
    return;
}

void AdjTmpUb(topkV2DataInfo::SortTileInfo &sortTileInfo, uint32_t tileData, uint32_t ubExtra, uint32_t tileFactor)
{
    uint32_t remainUbNew = ComputeRemainUb(sortTileInfo, tileData, ubExtra, tileFactor) - sortTileInfo.tmpUbSize;
    remainUbNew = remainUbNew > sortTileInfo.blockUbSize ? (remainUbNew - sortTileInfo.blockUbSize) : uint32_t(0);
    uint32_t alignUbSize = (remainUbNew / sortTileInfo.blockUbSize) * sortTileInfo.blockUbSize;
    OP_LOGI("RadixSortTiling", "alignUbSize %u", alignUbSize);
    sortTileInfo.tmpUbSize = sortTileInfo.tmpUbSize + alignUbSize; // 剩余的ub都给tmpUbsize
}

void ComputeTileDataOne(topkV2DataInfo::SortTileInfo &sortTileInfo, uint32_t lastDimTileNum,  uint32_t ubExtra,
                        uint32_t &tileData, uint32_t tileFactor)
{
    uint32_t allCore = CeilAlignDivMul<uint32_t>(int64_t(lastDimTileNum), int64_t(sortTileInfo.maxCoreNum));
    uint32_t newTileData = CeilAlignDiv(sortTileInfo.sortAxisNum, int64_t(allCore));
    tileData = CeilAlignDivMul<uint32_t>(int64_t(newTileData), int64_t(topkV2DataInfo::BIN_NUM));
    tileData = std::max(tileData, topkV2DataInfo::SMALL_TILE_DATA_NUM);
    SetSortTmpSize(ge::DT_UINT8, tileData, false, sortTileInfo);
    AdjTmpUb(sortTileInfo, tileData, ubExtra, tileFactor);
    return;
}

bool NeedAdjTileData(topkV2DataInfo::SortTileInfo &sortTileInfo, uint32_t &tileData, uint32_t lastDimTileNum,
                     uint32_t ubExtra, uint32_t tileFactor)
{
    if (sortTileInfo.unSortDimNum == int64_t(1) && lastDimTileNum == uint32_t(1)) {
        OP_LOGI("RadixSortTiling", "unSortDimNum and lastDimTileNum is 1");
        uint32_t newTileData = CeilAlignDiv(sortTileInfo.sortAxisNum, int64_t(sortTileInfo.maxCoreNum));
        newTileData = CeilAlignDivMul<uint32_t>(int64_t(newTileData), int64_t(topkV2DataInfo::BIN_NUM));
        tileData = std::max(newTileData, topkV2DataInfo::SMALL_TILE_DATA_NUM);
        SetSortTmpSize(ge::DT_UINT8, tileData, false, sortTileInfo);
        AdjTmpUb(sortTileInfo, tileData, ubExtra, tileFactor);
        return true;
    }
    if (sortTileInfo.unSortDimNum == int64_t(1) || (lastDimTileNum >= sortTileInfo.maxCoreNum)) {
        // b为1时，尽量均匀分核，同时保证处理的最小的tile_data为1024
        OP_LOGI("RadixSortTiling", "unSortDimNum is 1 and lastDimTileNum greater than allCore");
        ComputeTileDataOne(sortTileInfo, lastDimTileNum, ubExtra, tileData, tileFactor);
        return true;
    }
    if (sortTileInfo.unSortDimNum > int64_t(1) && sortTileInfo.unSortDimNum < int64_t(sortTileInfo.maxCoreNum) &&
        lastDimTileNum == uint32_t(1)) {
        OP_LOGI("RadixSortTiling", "unSortDimNum greater than 1,and unSortDimNum small and lastDimTileNum is one");
        uint32_t hCore = sortTileInfo.maxCoreNum / static_cast<uint32_t>(sortTileInfo.unSortDimNum);
        uint32_t hTileData = static_cast<uint32_t>(sortTileInfo.sortAxisNum) / hCore;
        tileData = CeilAlignDivMul<uint32_t>(int64_t(hTileData), int64_t(topkV2DataInfo::BIN_NUM));
        SetSortTmpSize(ge::DT_UINT8, tileData, false, sortTileInfo);
        AdjTmpUb(sortTileInfo, tileData, ubExtra, tileFactor);
        return tileData;
    }
    if (sortTileInfo.unSortDimNum > int64_t(1) && lastDimTileNum > uint32_t(1)) {
        // b大于1且h轴循环次数小于总核数，也就是b轴核数大于1
        OP_LOGI("RadixSortTiling", "unSortDimNum is one, lastDimTileNum greater than one");
        int64_t newTileData = sortTileInfo.sortAxisNum / int64_t(lastDimTileNum);
        tileData = CeilAlignDivMul<uint32_t>(newTileData, int64_t(topkV2DataInfo::BIN_NUM));
        lastDimTileNum = CeilAlignDiv(sortTileInfo.sortAxisNum, int64_t(tileData));
        uint32_t bCore = lastDimTileNum == 0 ? sortTileInfo.maxCoreNum : sortTileInfo.maxCoreNum / lastDimTileNum;
        if (lastDimTileNum < sortTileInfo.maxCoreNum && sortTileInfo.unSortDimNum < int64_t(sortTileInfo.maxCoreNum)) {
            if (sortTileInfo.unSortDimNum < int64_t(bCore)) {
                bCore = static_cast<uint32_t>(sortTileInfo.unSortDimNum);
                uint32_t hCore = sortTileInfo.maxCoreNum / bCore;
                uint32_t tileDataNew = CeilAlignDiv(int64_t(sortTileInfo.sortAxisNum), int64_t(hCore));
                tileData = CeilAlignDivMul<uint32_t>(int64_t(tileDataNew), int64_t(topkV2DataInfo::BIN_NUM));
            }
        }
        if (bCore == static_cast<uint32_t>(1) && lastDimTileNum < sortTileInfo.maxCoreNum) {
            ComputeTileDataOne(sortTileInfo, lastDimTileNum, ubExtra, tileData, tileFactor);
        }
        SetSortTmpSize(ge::DT_UINT8, tileData, false, sortTileInfo);
        AdjTmpUb(sortTileInfo, tileData, ubExtra, tileFactor);
        return true;
    }
    return false;
}

uint32_t ComputeTileData(topkV2DataInfo::SortTileInfo &sortTileInfo)
{
    uint32_t ubExtra;
    uint32_t tileFactor;
    if (sortTileInfo.isInt32 == static_cast<uint32_t>(0)) {
        ubExtra = topkV2DataInfo::UB_CONST_INT64;
        tileFactor = topkV2DataInfo::CONST_14 + sortTileInfo.dtypeSize;
    } else {
        ubExtra = topkV2DataInfo::UB_CONST_INT32;
        tileFactor = topkV2DataInfo::CONST_10 + sortTileInfo.dtypeSize;
    }

    uint32_t tileData = (sortTileInfo.ubSize - ubExtra) / tileFactor;
    tileData = (tileData / topkV2DataInfo::BIN_NUM) * topkV2DataInfo::BIN_NUM;

    uint32_t remainUb = ComputeRemainUb(sortTileInfo, tileData, ubExtra, tileFactor);
    SetSortTmpSize(ge::DT_UINT8, tileData, false, sortTileInfo);

    uint32_t tmpUbSize = sortTileInfo.tmpUbSize;
    while (tmpUbSize > remainUb) {
        tileData = tileData - topkV2DataInfo::BIN_NUM;
        remainUb = ComputeRemainUb(sortTileInfo, tileData, ubExtra, tileFactor);
        SetSortTmpSize(ge::DT_UINT8, tileData, false, sortTileInfo);
        tmpUbSize = sortTileInfo.tmpUbSize;
    }
    uint32_t lastDimTileNum = CeilAlignDiv(sortTileInfo.sortAxisNum, int64_t(tileData));
    OP_LOGI("RadixSortTiling", "tileData %u, lastDimTileNum %u, tmpUbSize %u", tileData, lastDimTileNum, tmpUbSize);
    bool smallTile = (sortTileInfo.sortAxisNum <= static_cast<int64_t>(topkV2DataInfo::SMALL_TILE_DATA_NUM)) &&
        lastDimTileNum == uint32_t(1);
    if ((lastDimTileNum % sortTileInfo.maxCoreNum == static_cast<uint32_t>(0)) || smallTile) {
        OP_LOGI("RadixSortTiling", "lastDimTileNum align or smallTile");
        AdjTmpUb(sortTileInfo, tileData, ubExtra, tileFactor);
        return tileData;
    }
    if (NeedAdjTileData(sortTileInfo, tileData, lastDimTileNum, ubExtra, tileFactor)) {
        return tileData;
    }
    AdjTmpUb(sortTileInfo, tileData, ubExtra, tileFactor);
    return tileData;
}

void ComputeWorkSpace(gert::TilingContext *context, topkV2DataInfo::SortTileInfo &sortTileInfo)
{
    uint32_t dtypeSizeWk = static_cast<uint32_t>(sizeof(int32_t));
    if (sortTileInfo.isInt32 == static_cast<uint32_t>(0)) {
        dtypeSizeWk = static_cast<uint32_t>(sizeof(int64_t));
    }
    size_t excusiveBinsGmWkSize = static_cast<size_t>(sortTileInfo.keyParams1) * sortTileInfo.keyParams4 * dtypeSizeWk;
    excusiveBinsGmWkSize = CeilAlignDivMul<size_t>(int64_t(excusiveBinsGmWkSize), int64_t(sortTileInfo.blockUbSize));

    size_t globalHistGmWkSize =
        static_cast<size_t>(sortTileInfo.keyParams3) * sortTileInfo.keyParams2 * sortTileInfo.keyParams0 * dtypeSizeWk;
    globalHistGmWkSize = CeilAlignDivMul<size_t>(int64_t(globalHistGmWkSize), int64_t(sortTileInfo.blockUbSize));

    size_t outIdxDbWK = static_cast<size_t>(sortTileInfo.sortAxisNum) * sortTileInfo.unsortedDimParallel * dtypeSizeWk;
    outIdxDbWK = CeilAlignDivMul<size_t>(int64_t(outIdxDbWK), int64_t(sortTileInfo.blockUbSize));

    size_t sortOutIdxGMWK = static_cast<size_t>(sortTileInfo.sortAxisNum) * sortTileInfo.unsortedDimParallel *
        sortTileInfo.y2DtypeSize;
    sortOutIdxGMWK = CeilAlignDivMul<size_t>(int64_t(sortOutIdxGMWK), int64_t(sortTileInfo.blockUbSize));

    size_t histTileGmWk = static_cast<size_t>(sortTileInfo.lastDimTileNum) * topkV2DataInfo::BIN_NUM *
        sortTileInfo.unsortedDimParallel * sizeof(int16_t) * topkV2DataInfo::CONST_2;

    size_t xB8GmWkSize = static_cast<size_t>(sortTileInfo.lastDimTileNum) * sortTileInfo.numTileDataSize *
        sortTileInfo.unsortedDimParallel;
    xB8GmWkSize = CeilAlignDivMul<size_t>(int64_t(xB8GmWkSize), int64_t(sortTileInfo.blockUbSize));

    size_t outValueDbWKSize = static_cast<size_t>(sortTileInfo.sortAxisNum) * sortTileInfo.unsortedDimParallel *
        sortTileInfo.dtypeSize *topkV2DataInfo::CONST_2;
    outValueDbWKSize = CeilAlignDivMul<size_t>(int64_t(outValueDbWKSize), int64_t(sortTileInfo.blockUbSize));

    OP_LOGI("RadixSortTiling",
        "excusiveBinsGmWkSize %lu, globalHistGmWkSize %lu, outIdxDbWK %lu, sortOutIdxGMWK %lu, histTileGmWk %lu,"
        " xB8GmWkSize %lu, outValueDbWKSize %lu ",
        excusiveBinsGmWkSize, globalHistGmWkSize, outIdxDbWK, sortOutIdxGMWK, histTileGmWk, xB8GmWkSize, outValueDbWKSize);
    size_t *userWorkSpaceSize = context->GetWorkspaceSizes(1);
    size_t usrSize = excusiveBinsGmWkSize + globalHistGmWkSize + outIdxDbWK + sortOutIdxGMWK + histTileGmWk +
        xB8GmWkSize + outValueDbWKSize;
    userWorkSpaceSize[0] = usrSize + topkV2DataInfo::SYS_WORK_SPACE_SIZE;
    return;
}

ge::graphStatus GetRadixSortMoreCore(gert::TilingContext *context, topkV2DataInfo::SortTileInfo &sortTileInfo)
{
    sortTileInfo.ubSize = sortTileInfo.ubSize - topkV2DataInfo::SIMT_UB;
    uint32_t tileData = ComputeTileData(sortTileInfo);
    uint32_t lastDimTileNum = CeilAlignDiv(int64_t(sortTileInfo.sortAxisNum), int64_t(tileData));
    if (sortTileInfo.maxCoreNum <= lastDimTileNum) {
        sortTileInfo.unsortedDimParallel = static_cast<uint32_t>(1);
    } else {
        sortTileInfo.unsortedDimParallel = lastDimTileNum == 0 ? sortTileInfo.maxCoreNum : sortTileInfo.maxCoreNum /
            lastDimTileNum;
        if (sortTileInfo.unSortDimNum < static_cast<int64_t>(sortTileInfo.unsortedDimParallel)) {
            sortTileInfo.unsortedDimParallel = static_cast<uint32_t>(sortTileInfo.unSortDimNum);
        }
    }
    sortTileInfo.numTileDataSize = tileData;
    sortTileInfo.sortLoopTimes = CeilAlignDiv(int64_t(sortTileInfo.unSortDimNum), int64_t(sortTileInfo.unsortedDimParallel));
    sortTileInfo.lastDimNeedCore = std::min(sortTileInfo.maxCoreNum, lastDimTileNum);
    sortTileInfo.coreNumNeed = sortTileInfo.unsortedDimParallel * sortTileInfo.lastDimNeedCore;
    sortTileInfo.lastDimTileNum = lastDimTileNum;

    uint32_t ubSizeNum = sortTileInfo.tmpUbSize / static_cast<uint32_t>(sizeof(uint32_t));
    if (sortTileInfo.isInt32 == static_cast<uint32_t>(0)) {
        ubSizeNum = sortTileInfo.tmpUbSize / static_cast<uint32_t>(sizeof(int64_t));
    }
    uint32_t allNumGloblHist = topkV2DataInfo::BIN_NUM * lastDimTileNum * sortTileInfo.dtypeSize *
        sortTileInfo.unsortedDimParallel;
    uint32_t allNumExcusiveBin = topkV2DataInfo::BIN_NUM * sortTileInfo.dtypeSize * sortTileInfo.unsortedDimParallel;
    uint32_t oneCoreSize = CeilAlignDiv(int64_t(allNumGloblHist), int64_t(sortTileInfo.coreNumNeed));
    sortTileInfo.keyParams5 =
        std::max(static_cast<int64_t>(oneCoreSize), static_cast<int64_t>(sortTileInfo.blockUbSize));
    sortTileInfo.keyParams0 = CeilAlignDiv(int64_t(allNumGloblHist), int64_t(sortTileInfo.keyParams5));
    sortTileInfo.keyParams3 = CeilAlignDiv(int64_t(sortTileInfo.keyParams5), int64_t(ubSizeNum));
    sortTileInfo.keyParams2 = sortTileInfo.keyParams5 > ubSizeNum ? ubSizeNum : sortTileInfo.keyParams5;

    uint32_t oneCoreSize1 = CeilAlignDiv(int64_t(allNumExcusiveBin), int64_t(sortTileInfo.coreNumNeed));
    sortTileInfo.keyParams4 =
        std::max(static_cast<int64_t>(oneCoreSize1), static_cast<int64_t>(sortTileInfo.blockUbSize));

    sortTileInfo.keyParams1 = CeilAlignDiv(int64_t(allNumExcusiveBin), int64_t(sortTileInfo.keyParams4));

    // 取前k个结果相关流程的tile计算
    uint32_t avilableUbSize = (sortTileInfo.ubSize - 1) / topkV2DataInfo::AGLIN_FACTOR * topkV2DataInfo::AGLIN_FACTOR;
    OP_CHECK_IF(avilableUbSize == 0, 
        OP_LOGE("TopKV2", "sortAndTopK Tiling avilableUbSize is zero"), return ge::GRAPH_FAILED);
    auto dataType = context->GetInputDesc(0)->GetDataType();
    auto indicesDType = context->GetOutputDesc(1)->GetDataType();
    uint32_t xDtypeSize = static_cast<uint32_t>(topkV2DataInfo::tilingDataTypeBitMap.find(dataType)->second);
    uint32_t indexToDtypeSize = static_cast<uint32_t>(topkV2DataInfo::tilingDataTypeBitMap.find(indicesDType)->second);
    uint32_t kGetDtypeSize = std::max(xDtypeSize, indexToDtypeSize);
    OP_CHECK_IF(kGetDtypeSize == 0, OP_LOGE("GetRadixSortMoreCore", "kGetDtypeSize is zero"), return ge::GRAPH_FAILED);
    sortTileInfo.tileDataSize = avilableUbSize / kGetDtypeSize;
    uint32_t totalTileNum = (sortTileInfo.topKRealValue + sortTileInfo.tileDataSize - 1) / sortTileInfo.tileDataSize;
    sortTileInfo.blockTileNum = totalTileNum / sortTileInfo.maxCoreNum;
    sortTileInfo.tailTileNum = totalTileNum % sortTileInfo.maxCoreNum;
    OP_CHECK_IF(sortTileInfo.blockTileNum  == 0 && sortTileInfo.tailTileNum  == 0, 
        OP_LOGE("TopKV2", "sortAndTopK blockTileNum & tailTileNum is wrong!"), return ge::GRAPH_FAILED);

    ComputeWorkSpace(context, sortTileInfo);
    context->SetScheduleMode(1);
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus CheckInputAndOutput(gert::TilingContext *context, topkV2DataInfo::SortTileInfo &sortTileInfo)
{
    auto platformInfo = context->GetPlatformInfo();
    OP_CHECK_NULL_WITH_CONTEXT(context, platformInfo); 
    auto ascendcPlatform = platform_ascendc::PlatformAscendC(platformInfo);
    uint64_t ubSize = 0;
    ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::UB, ubSize);
    OP_CHECK_IF(ubSize <= static_cast<uint64_t>(topkV2DataInfo::SIMT_UB),
        OP_LOGE(context->GetNodeName(), "allUb must greater than simtUb, but is %lu", ubSize),
        return ge::GRAPH_FAILED);
    sortTileInfo.blockUbSize = Ops::Base::GetUbBlockSize(context);
    OP_LOGI(context->GetNodeName(), "ubSize is %ld, blockUbSize %u", ubSize, sortTileInfo.blockUbSize);
    sortTileInfo.ubSize = ubSize;
    auto inputShapePtr = context->GetInputShape(0);
    OP_CHECK_NULL_WITH_CONTEXT(context, inputShapePtr);
    const gert::Shape &inputShape = Ops::Base::EnsureNotScalar(inputShapePtr->GetStorageShape());
    auto yStorage = context->GetOutputShape(0);
    OP_CHECK_NULL_WITH_CONTEXT(context, yStorage);
    const gert::Shape &outShape = Ops::Base::EnsureNotScalar(yStorage->GetStorageShape());
    OP_CHECK_IF(inputShape.GetShapeSize() == 0 || outShape.GetShapeSize() == 0,
        OP_LOGE(context->GetNodeName(), "not support empty input or output"),
        return ge::GRAPH_FAILED);
    int32_t xDimNum = inputShape.GetDimNum();
    sortTileInfo.xDimNum = xDimNum;
    int64_t sortAxisNum = inputShape.GetDim(xDimNum - 1);
    sortTileInfo.sortAxisNum = sortAxisNum;
    int64_t unSortDimNum = static_cast<int64_t>(1);
    for (uint32_t i = 0; i < static_cast<uint32_t>((xDimNum - 1)); i++) {
        int64_t dimSize = static_cast<int64_t>(inputShape.GetDim(i));
        unSortDimNum *= dimSize;
    }
    sortTileInfo.unSortDimNum = unSortDimNum;
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus SortCheckParams(gert::TilingContext *context, topkV2DataInfo::SortTileInfo &sortTileInfo)
{
    OP_CHECK_IF(CheckInputAndOutput(context, sortTileInfo) != ge::GRAPH_SUCCESS,
        OP_LOGE(context->GetNodeName(), "CheckInputAndOutput failed"), return ge::GRAPH_FAILED);
    auto inputDescPtr = context->GetInputDesc(0);
    OP_CHECK_NULL_WITH_CONTEXT(context, inputDescPtr);
    ge::DataType dataType = inputDescPtr->GetDataType();
    OP_CHECK_IF(topkV2DataInfo::tilingDataTypeBitMap.count(dataType) == 0,
        OP_LOGE(context->GetNodeName(), "Not support data type"), return ge::GRAPH_FAILED);
    sortTileInfo.dataType = dataType;
    sortTileInfo.dtypeSize = topkV2DataInfo::tilingDataTypeBitMap.find(dataType)->second;
    auto outDescPtr = context->GetOutputDesc(1);
    OP_CHECK_NULL_WITH_CONTEXT(context, outDescPtr);
    auto y2DType = outDescPtr->GetDataType();
    auto outDescPtr0 = context->GetOutputDesc(0);
    OP_CHECK_NULL_WITH_CONTEXT(context, outDescPtr0);
    auto y1DType = outDescPtr0->GetDataType();
    OP_CHECK_IF((y2DType != ge::DT_INT64) && (y2DType != ge::DT_INT32),
        OP_LOGE(context->GetNodeName(), "Not support y2 type"), return ge::GRAPH_FAILED);
    OP_CHECK_IF(y1DType != dataType,
        OP_LOGE(context->GetNodeName(), "input0 dtype must be same as output0 dtype"),
        return ge::GRAPH_FAILED);
    sortTileInfo.y2DtypeSize = topkV2DataInfo::tilingDataTypeBitMap.find(y2DType)->second;
    return ge::GRAPH_SUCCESS;
}

void FillTilingDataSort(gert::TilingContext *context, topkV2DataInfo::SortTileInfo &sortTileInfo,
    TopKV2TilingDataSimd &topkTilingData)
{
    if (sortTileInfo.isDescend) {
        topkTilingData.set_isLargest(topkV2DataInfo::CONST_TWO);
    } else {
        topkTilingData.set_isLargest(topkV2DataInfo::CONST_ZERO);
    }
    topkTilingData.set_isInInt32Range(sortTileInfo.isInt32);
    topkTilingData.set_numTileDataSize(sortTileInfo.numTileDataSize);
    topkTilingData.set_unsortedDimParallel(sortTileInfo.unsortedDimParallel);
    topkTilingData.set_lastDimTileNum(sortTileInfo.lastDimTileNum);
    topkTilingData.set_sortLoopTimes(sortTileInfo.sortLoopTimes);
    topkTilingData.set_lastDimNeedCore(sortTileInfo.lastDimNeedCore);
    topkTilingData.set_keyParams0(sortTileInfo.keyParams0);
    topkTilingData.set_keyParams1(sortTileInfo.keyParams1);
    topkTilingData.set_keyParams2(sortTileInfo.keyParams2);
    topkTilingData.set_keyParams3(sortTileInfo.keyParams3);
    topkTilingData.set_keyParams4(sortTileInfo.keyParams4);
    topkTilingData.set_keyParams5(sortTileInfo.keyParams5);
    topkTilingData.set_tmpUbSize(sortTileInfo.tmpUbSize);
    topkTilingData.set_lastAxisNum(sortTileInfo.sortAxisNum);
    topkTilingData.set_unsortedDimNum(sortTileInfo.unSortDimNum);
    topkTilingData.set_topKRealValue(sortTileInfo.topKRealValue);
    topkTilingData.set_sortAndTopkTileDataSize(sortTileInfo.tileDataSize);
    topkTilingData.set_sortAndTopkBlockTileNum(sortTileInfo.blockTileNum);
    topkTilingData.set_sortAndTopkTailTileNum(sortTileInfo.tailTileNum);
    topkTilingData.SaveToBuffer(context->GetRawTilingData()->GetData(), context->GetRawTilingData()->GetCapacity());
    context->GetRawTilingData()->SetDataSize(topkTilingData.GetDataSize());
    return;
}

void PrintTilindDataSort(gert::TilingContext *context, topkV2DataInfo::SortTileInfo &sortTileInfo)
{
    OP_LOGI(context->GetNodeName(),
        "realCoreNum %u, numTileDataSize %u, unsortedDimParallel %u, "
        "lastDimTileNum %u, sortLoopTimes %u, lastDimNeedCore %u, keyParams0 %u, keyParams1 %u "
        "keyParams2 %u, keyParams3 %u, keyParams4 %u, keyParams5 %u, tmpUbSize %u, "
        "lastAxisNum %ld, unsortedDimNum %ld, topKRealValue %ld, tileDataSize %u, blockTileNum %u, tailTileNum %u",
        sortTileInfo.coreNumNeed, sortTileInfo.numTileDataSize, sortTileInfo.unsortedDimParallel,
        sortTileInfo.lastDimTileNum, sortTileInfo.sortLoopTimes, sortTileInfo.lastDimNeedCore, sortTileInfo.keyParams0,
        sortTileInfo.keyParams1, sortTileInfo.keyParams2, sortTileInfo.keyParams3, sortTileInfo.keyParams4,
        sortTileInfo.keyParams5, sortTileInfo.tmpUbSize, sortTileInfo.sortAxisNum, sortTileInfo.unSortDimNum,
        sortTileInfo.topKRealValue, sortTileInfo.tileDataSize, sortTileInfo.blockTileNum, sortTileInfo.tailTileNum);
    return;
}

bool needSortWithIndex(TopKV2TilingDataSimd& topkTilingData, bool isSorted, ge::DataType dataType)
{
    if (isSorted && topkTilingData.get_modeType() == topkV2DataInfo::MULT_CORE_MODE) {
        if(topkTilingData.get_topKRealValue() <= topkV2DataInfo::SUPPORT_SORT_MAX_SIZE) {
            return false;
        }
        return true;
    }
    uint32_t xDtypeSize = static_cast<uint32_t>(topkV2DataInfo::tilingDataTypeBitMap.find(dataType)->second);
    if (isSorted && topkTilingData.get_modeType() == topkV2DataInfo::SINGLE_CORE_MODE) {
        if (topkTilingData.get_topKRealValue() <= topkV2DataInfo::SUPPORT_SORT_MAX_SIZE &&
            topkTilingData.get_topKRealValue() * xDtypeSize <= topkV2DataInfo::SUPPORT_SORT_MAX_BYTE_SIZE) {
            return false;
        }
        return true;
    }
    return false;
}

ge::graphStatus TopKV2Tiling(gert::TilingContext* context, int32_t maxCoreNum)
{
    OP_LOGI("TopKV2TilingForAscendC", "TopKV2Tiling start");
    TopKV2TilingDataSimd topkTilingData;
    OP_CHECK_IF(
        IsValidParam(context) == ge::GRAPH_FAILED, OP_LOGE("TopkV2", "Input param is invalid"),
        return ge::GRAPH_FAILED);
    const gert::Shape inputShape = context->GetInputShape(0)->GetStorageShape();
    auto dataType = context->GetInputDesc(0)->GetDataType();
    const gert::Shape outShape = context->GetOutputShape(0)->GetStorageShape();
    auto dataTypeKey = topkV2DataInfo::tilingDataTypeKeyMap.find(dataType)->second;
    auto indicesDType = context->GetOutputDesc(1)->GetDataType();
    std::string opType(context->GetNodeType());
    auto const attrs = context->GetAttrs();
    OP_CHECK_NULL_WITH_CONTEXT(context, attrs);
    const bool* isSorted = attrs->GetAttrPointer<bool>(0);
    OP_CHECK_NULL_WITH_CONTEXT(context, isSorted);
    OP_LOGI(context->GetNodeName(), "isSorted=%u", *isSorted);
    const int* dimValuePtr = attrs->GetAttrPointer<int>(1);
    OP_CHECK_NULL_WITH_CONTEXT(context, dimValuePtr);
    OP_LOGI(context->GetNodeName(), "dimValuePtr=%d", *dimValuePtr);
    const bool* isLargest = attrs->GetAttrPointer<bool>(2);
    OP_CHECK_NULL_WITH_CONTEXT(context, isLargest);
    OP_LOGI(context->GetNodeName(), "isLargest=%d", *isLargest);
    // check the indices_dtype attr and actual value of indices output
    const int* indicesDTypeValuePtr = attrs->GetAttrPointer<int>(3);
    OP_CHECK_NULL_WITH_CONTEXT(context, indicesDTypeValuePtr);
    OP_LOGI(context->GetNodeName(), "indicesDTypeValuePtr=%d, outPutIndexType=%ld.", *indicesDTypeValuePtr, 
        static_cast<int64_t>(indicesDType));

    size_t inputDimNum = inputShape.GetDimNum();
    OP_CHECK_IF(
        *dimValuePtr < static_cast<int32_t>(-inputDimNum) || *dimValuePtr >= static_cast<int32_t>(inputDimNum),
        OP_LOGE(context->GetNodeName(), "Attr dim is out of range"), return ge::GRAPH_FAILED);
    int64_t lastAxisNum = inputShape.GetDim(inputDimNum - 1);
    uint32_t unsortedDimNum = 1;
    for (uint32_t i = 0; i < (inputDimNum - 1); i++) {
        unsortedDimNum *= inputShape.GetDim(i);
    }
    size_t outputDimNum = outShape.GetDimNum();
    int64_t outLastAxisNum = outShape.GetDim(outputDimNum - 1);
    int64_t int32Max = static_cast<int64_t>(std::numeric_limits<int32_t>::max());
    uint32_t isInInt32Range = static_cast<uint32_t>(lastAxisNum <= int32Max);
    // Get Platform Info
    uint64_t ubSizePlatForm = 0;
    auto ascendcPlatform = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
    ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::UB, ubSizePlatForm);

    uint64_t ubBlock = static_cast<uint64_t>(Ops::Base::GetUbBlockSize(context));
    OP_LOGI("[TopKV2Tiling]", "ubBlock size = : %u", ubBlock);

    // 校验ubSizePlatForm
    ubSizePlatForm -= topkV2DataInfo::CONST_SIMT_SPACE;
    uint32_t nowTileSize = ComputeTopkTileData(
        context, topkTilingData, dataType, indicesDType, *isLargest, *isSorted, lastAxisNum, outLastAxisNum, maxCoreNum,
        ubSizePlatForm);
    topkV2DataInfo::TopkTileInfo topkTileInfo;
    topkTileInfo.topKOutLastAxisNum = outLastAxisNum;

    // 用于核间优化模板 tilingSize计算流程
    topkV2DataInfo::TopkComputingNowTileSizeInfo computingNowTileSizeInfo;
    computingNowTileSizeInfo.isLargest = *isLargest;
    computingNowTileSizeInfo.isSort = *isSorted;
    computingNowTileSizeInfo.isInInt32Range = lastAxisNum <= int32Max;
    computingNowTileSizeInfo.lastAxisNum = lastAxisNum;
    computingNowTileSizeInfo.kValue = outLastAxisNum;
    computingNowTileSizeInfo.maxCoreNum = maxCoreNum;
    computingNowTileSizeInfo.ubSizePlatForm = ubSizePlatForm;
    computingNowTileSizeInfo.dataType = dataType;
    computingNowTileSizeInfo.indicesDType = indicesDType;
    computingNowTileSizeInfo.ubBlockAlignSize = ubBlock;
    OP_LOGI(
        "[TopKV2Tiling]",
        "computingNowTileSizeInfo isLargest: %u, isSort: %u, isInInt32Range: %u, lastAxisNum: %u, kValue: %u, "
        "maxCoreNum: %u, ubSizePlatForm: %u",
        computingNowTileSizeInfo.isLargest, computingNowTileSizeInfo.isSort, computingNowTileSizeInfo.isInInt32Range,
        computingNowTileSizeInfo.lastAxisNum, computingNowTileSizeInfo.kValue, computingNowTileSizeInfo.maxCoreNum,
        computingNowTileSizeInfo.ubSizePlatForm);

    const uint32_t sortedDimParallelData = (nowTileSize * maxCoreNum) / 2;
    if (lastAxisNum <= topkV2DataInfo::SMALL_MAX_DATA_SZIE && topkV2DataInfo::optDataTypeBitMap.count(dataType) != 0) {
        SetMergeSortTmpSize(context, dataType, lastAxisNum, topkTilingData);
        uint32_t nowTileSizeTmp = ComputeMergeSortTileData(
            topkTilingData, dataType, indicesDType, lastAxisNum, maxCoreNum, unsortedDimNum, ubSizePlatForm);
        TileModeSmallSizeOptim(unsortedDimNum, maxCoreNum, lastAxisNum, topkTilingData, topkTileInfo, nowTileSizeTmp);
        dataTypeKey += topkV2DataInfo::MERGE_SORT_TILING_OFFSET;
    } else if (lastAxisNum <= nowTileSize) {
        uint32_t nowTileSizeTmp = ComputeSingleBlockTileData(
            context, topkTilingData, dataType, indicesDType, *isLargest, *isSorted, lastAxisNum, outLastAxisNum,
            ubSizePlatForm);
        TileModeSmallSize(unsortedDimNum, maxCoreNum, lastAxisNum, topkTilingData, topkTileInfo, nowTileSizeTmp);
    } else if (lastAxisNum > topkV2DataInfo::SORT_AND_TOP_K_THRESHOLD) {
        topkV2DataInfo::SortTileInfo sortTileInfo;
        OP_CHECK_IF(SortCheckParams(context, sortTileInfo) != ge::GRAPH_SUCCESS,
            OP_LOGE(context->GetNodeName(), "sort and topk check params failed"), return ge::GRAPH_FAILED);
        topkTilingData.set_modeType(topkV2DataInfo::SORT_AND_TOP_K_MODE);
        OP_LOGI("[TopKV2Tiling]", "topkTilingData.set_modeType is: %u, SORT_AND_TOP_K_MODE: %u",
            topkTilingData.get_modeType() , topkV2DataInfo::SORT_AND_TOP_K_MODE);
        sortTileInfo.maxCoreNum = static_cast<uint32_t>(maxCoreNum);
        sortTileInfo.isDescend = static_cast<bool>(*isLargest);
        sortTileInfo.isInt32 = static_cast<uint32_t>(lastAxisNum <= topkV2DataInfo::INT32_MAX_RANGE_VALUE_FOR_SORT);
        sortTileInfo.topKRealValue = outLastAxisNum;
        OP_CHECK_IF(GetRadixSortMoreCore(context, sortTileInfo) != ge::GRAPH_SUCCESS,
            OP_LOGE(context->GetNodeName(), "Get RadixSortMoreCore tiling failed"), return ge::GRAPH_FAILED);
        context->SetTilingKey(dataTypeKey);
        context->SetBlockDim(sortTileInfo.coreNumNeed);
        context->SetLocalMemorySize(sortTileInfo.ubSize);
        FillTilingDataSort(context, sortTileInfo, topkTilingData);
        PrintTilindDataSort(context, sortTileInfo);
        // sortAndTopK模板核心是Sort，不需要后续Topk相关的tiling计算过程
        OP_LOGI("TopKV2TilingForAscendC", "TopKV2Tiling end");
        return ge::GRAPH_SUCCESS;
    } else if (IsModeSingleCore(unsortedDimNum, maxCoreNum)) {
        uint32_t nowTileSizeTmp = ComputeSingleCoreTileData(
            context, topkTilingData, dataType, indicesDType, *isLargest, *isSorted, lastAxisNum, outLastAxisNum,
            ubSizePlatForm);
        OP_CHECK_IF(nowTileSizeTmp == 0, OP_LOGE("TopkV2", "nowTileSizeTmp is 0"), return ge::GRAPH_FAILED);
        TileModeSingleCore(
            unsortedDimNum, maxCoreNum, static_cast<uint32_t>(lastAxisNum), topkTilingData, topkTileInfo,
            nowTileSizeTmp);
    } else if (IsMultiCoreOptimMode(context, nowTileSize, topkTilingData, computingNowTileSizeInfo)) {
        // topk核间模板优化，修改modelType, tilling不变
        TileMultiCoreOptimSize(unsortedDimNum, maxCoreNum, lastAxisNum, topkTilingData, topkTileInfo, nowTileSize);
        topkTilingData.set_modeType(topkV2DataInfo::MULT_CORE_OPTIM_MODE);
    } else if (lastAxisNum <= sortedDimParallelData) {
        TileModeMediumSize(unsortedDimNum, maxCoreNum, lastAxisNum, topkTilingData, topkTileInfo, nowTileSize);
    } else {
        TileModeBigSize(unsortedDimNum, maxCoreNum, lastAxisNum, topkTilingData, topkTileInfo, nowTileSize); // 核间模板
    }
    int64_t maxInputK = std::max(outLastAxisNum, topkTileInfo.lastDimTileNum);

    if (topkTilingData.get_modeType() == topkV2DataInfo::MULT_CORE_MODE &&
        topkTileInfo.topKOutLastAxisNum > topkV2DataInfo::MAX_K_FOR_INT64) {
        nowTileSize /= topkV2DataInfo::CONST_TWO;
    }

    GetTopkApiTmpBufferSize(
        context, topkTilingData, topkTileInfo.ubRealLoadDataNum, maxInputK, *isLargest, dataType, *isSorted,
        nowTileSize);
    OP_CHECK_IF(maxCoreNum == 0, OP_LOGE("TopkV2", "maxCoreNum is 0"), return ge::GRAPH_FAILED);
    int64_t lastDimTileNumTimesValue = (topkTileInfo.lastDimTileNum + maxCoreNum - 1) / maxCoreNum;
    OP_LOGI(
        "[TopKV2Tiling]", "lastAxisNum: %ld, int32Max: %ld, isInInt32Range: %u, nowTileSize: %u", lastAxisNum, int32Max,
        isInInt32Range, nowTileSize);

    // fill the topkTilingData
    context->SetTilingKey(dataTypeKey);
    context->SetBlockDim(topkTileInfo.coreNumNeed);
    context->SetScheduleMode(1);
    topkTilingData.set_isLargest(*isLargest);
    topkTilingData.set_isSort(*isSorted);
    topkTilingData.set_isInInt32Range(isInInt32Range);
    topkTilingData.set_lastAxisNum(lastAxisNum);
    topkTilingData.set_unsortedDimNum(unsortedDimNum);
    topkTilingData.set_lastDimTileNumTimes(lastDimTileNumTimesValue);
    topkTilingData.set_platformCoreNum(maxCoreNum);
    topkTilingData.set_topKRealValue(outLastAxisNum);
    topkTilingData.set_oneCoreRowNum(topkTileInfo.oneCoreRowNum);
    topkTilingData.set_outputLastDimValue(outLastAxisNum);
    topkTilingData.set_batchNumInUb(topkTileInfo.batchNumInUb);
    topkTilingData.set_tailLoopBatchNum(topkTileInfo.tailLoopBatchNum);
    topkTilingData.set_tailBatchNum(topkTileInfo.tailBatchNum);
    topkTilingData.set_tailTileNum(topkTileInfo.tailTileNum);
    OP_LOGI(
        context->GetNodeName(),
        "TopK V2 tilingData tilingKey is %u, isLargest is %u, modelType is %u,"
        "isSorted is %u, lastAxisNum is %ld, unsortedDimNum is %u, lastDimTileNumTimesValue is %ld, outLastAxisNum is "
        "%ld,"
        "oneCoreRowNum is %u, sortLoopTimes is %u, lastDimTileNum is %ld, unsortedDimParallel is %u, modeType is %u,"
        "lastDimNeedCore is %u, numTileDataSize is %u, batchNumInUb is %u, tailLoopBatchNum is %u, tailBatchNum is %u,"
        "tailTileNum is %u, coreNumNeed is %u",
        dataTypeKey, topkTilingData.get_isLargest(), topkTilingData.get_modeType(), topkTilingData.get_isSort(),
        topkTilingData.get_lastAxisNum(), topkTilingData.get_unsortedDimNum(), topkTilingData.get_lastDimTileNumTimes(),
        topkTilingData.get_topKRealValue(), topkTilingData.get_oneCoreRowNum(), topkTilingData.get_sortLoopTimes(),
        topkTilingData.get_lastDimTileNum(), topkTilingData.get_unsortedDimParallel(), topkTilingData.get_modeType(),
        topkTilingData.get_lastDimNeedCore(), topkTilingData.get_numTileDataSize(), topkTilingData.get_batchNumInUb(),
        topkTilingData.get_tailLoopBatchNum(), topkTilingData.get_tailBatchNum(), topkTilingData.get_tailTileNum(),
        topkTileInfo.coreNumNeed);

    // TopKV2 Workspace计算流程
    size_t usrSize = 0;
    OP_LOGI("[TopKV2Tiling]", "begin to calc TopKV2 Workspace size.");
    if (isInInt32Range) {
        if (topkTilingData.get_modeType() == topkV2DataInfo::SINGLE_CORE_MODE) {
            usrSize = topkTileInfo.lastDimTileNum * topkV2DataInfo::BIN_NUM * topkTileInfo.unsortedDimParallel *
                      sizeof(int32_t);
            OP_LOGI("[TopKV2Tiling]", "TopK V2 Workspace size is : %u", usrSize);
        } else if (topkTilingData.get_modeType() == topkV2DataInfo::MULT_CORE_OPTIM_MODE) {
            uint32_t xDtypeSize = static_cast<uint32_t>(topkV2DataInfo::tilingDataTypeBitMap.find(dataType)->second);
            size_t tempSortResultNeedSize = Ops::Base::CeilAlign(
                static_cast<uint64_t>(
                    xDtypeSize * topkTileInfo.lastDimTileNum * topkTileInfo.unsortedDimParallel *
                    topkTilingData.get_topKRealValue()),
                topkV2DataInfo::AGLIN_FACTOR);
            size_t tempSortIndexNeedSize = Ops::Base::CeilAlign(
                static_cast<uint64_t>(
                    sizeof(int32_t) * topkTileInfo.lastDimTileNum * topkTileInfo.unsortedDimParallel *
                    topkTilingData.get_topKRealValue()),
                topkV2DataInfo::AGLIN_FACTOR);
            usrSize = tempSortResultNeedSize + tempSortIndexNeedSize;
            OP_LOGI("[TopKV2Tiling]", "Workspace size for Radix Sort perf template within Int32Range is : %u", usrSize);
        } else {
            size_t dataSetCumSumHistNeedSize =
                topkV2DataInfo::BIN_NUM * sizeof(int32_t) * topkTileInfo.unsortedDimParallel;
            size_t dataSetTileTopkNeedSize = Ops::Base::CeilAlign(
                static_cast<uint64_t>(topkTileInfo.lastDimTileNum * sizeof(int32_t) * topkTileInfo.unsortedDimParallel),
                topkV2DataInfo::AGLIN_FACTOR);
            usrSize = dataSetCumSumHistNeedSize + dataSetTileTopkNeedSize * topkV2DataInfo::CONST_TWO;
            OP_LOGI("[TopKV2Tiling]", "Workspace size for Radix Sort more core within Int32Range is : %u", usrSize);
        }
    } else {
        if (topkTilingData.get_modeType() == topkV2DataInfo::SINGLE_CORE_MODE) {
            usrSize = topkTileInfo.lastDimTileNum * topkV2DataInfo::BIN_NUM * topkTileInfo.unsortedDimParallel *
                      sizeof(int64_t);
            OP_LOGI("[TopKV2Tiling]", "TopK V2 Workspace size is : %u", usrSize);
        } else {
            size_t dataSetCumSumHistNeedSize =
                topkV2DataInfo::BIN_NUM * sizeof(int64_t) * topkTileInfo.unsortedDimParallel;
            size_t dataSetTileTopkNeedSize = Ops::Base::CeilAlign(
                topkTileInfo.lastDimTileNum * sizeof(int64_t) * topkTileInfo.unsortedDimParallel,
                topkV2DataInfo::AGLIN_FACTOR);
            usrSize = dataSetCumSumHistNeedSize + dataSetTileTopkNeedSize * topkV2DataInfo::CONST_TWO;
            OP_LOGI("[TopKV2Tiling]", "Workspace size for Radix Sort more core beyond Int32Range is : %u", usrSize);
        }
    }

    // sortWithIndex tiling&workspace计算流程，
    if (needSortWithIndex(topkTilingData, *isSorted, dataType)) {
        OP_CHECK_IF(sortWithIndex::RadixSortTilingOfIdx(context, topkTilingData, maxCoreNum, &usrSize) != ge::GRAPH_SUCCESS,
            OP_LOGE(context->GetNodeName(), "SortWithIndex Tiling Simt calc failed"), return ge::GRAPH_FAILED);
    }

    // save tilingdata
    topkTilingData.SaveToBuffer(context->GetRawTilingData()->GetData(), context->GetRawTilingData()->GetCapacity());
    context->GetRawTilingData()->SetDataSize(topkTilingData.GetDataSize());

    // set userWorkSpaceSize
    size_t* userWorkSpaceSize = context->GetWorkspaceSizes(1);
    userWorkSpaceSize[0] = usrSize + topkV2DataInfo::SYS_WORK_SPACE_SIZE;
    OP_LOGI("[TopKV2Tiling]", "user & system WorkSpace Size is : %u", userWorkSpaceSize[0]);
    context->SetLocalMemorySize(ubSizePlatForm);
    context->SetScheduleMode(1);
    OP_LOGI("TopKV2TilingForAscendC", "TopKV2Tiling end");
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus TilingPrepareForTopKV2(gert::TilingParseContext* context)
{
    OP_LOGI(context->GetNodeName(), "AscendC Tiling starting GRAPH_SUCCESS");
    auto compileInfo = context->GetCompiledInfo<TopKV2CompileInfo>();
    OP_CHECK_NULL_WITH_CONTEXT(context, compileInfo);
    auto platformInfo = context->GetPlatformInfo();
    OP_CHECK_NULL_WITH_CONTEXT(context, platformInfo);
    auto ascendcPlatform = platform_ascendc::PlatformAscendC(platformInfo);
    compileInfo->coreNum = ascendcPlatform.GetCoreNumAiv();
    OP_CHECK_IF(
        (compileInfo->coreNum <= 0), OP_LOGE(context->GetNodeName(), "The core num is invaild."),
        return ge::GRAPH_FAILED);
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus Tiling4TopKV2(gert::TilingContext* context)
{
    auto compile_info = reinterpret_cast<const TopKV2CompileInfo*>(context->GetCompileInfo());
    OP_LOGI(context->GetNodeName(), "AscendC topk simd tiling");
    OP_CHECK_IF(
        TopKV2Tiling(context, compile_info->coreNum) != ge::GRAPH_SUCCESS,
        OP_LOGE(context->GetNodeName(), "Topk simd tiling function failed"), return ge::GRAPH_FAILED);
    return ge::GRAPH_SUCCESS;
}

IMPL_OP_OPTILING(TopKV2).Tiling(Tiling4TopKV2).TilingParse<TopKV2CompileInfo>(TilingPrepareForTopKV2);
} // namespace topkV2
} // namespace optiling
