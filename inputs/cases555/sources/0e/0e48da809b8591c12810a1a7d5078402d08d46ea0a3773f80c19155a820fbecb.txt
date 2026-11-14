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
 * \file iou3d_tiling_arch35.cpp
 * \brief Iou3D Host 侧 Tiling（arch35 / DAV_3510）
 *
 * def 驱动 dtype：dtype 由 _def.cpp 的 DataType({ge::DT_FLOAT}) 声明，构建系统按 dtype
 * 展开 kernel 变体；无 TilingKey 参数，空 Tensor 短路在 kernel 内部运行时判断。
 *   - 多核切分：总 (b,i,j) 对数 = B*N*K，按 coreNum 均分为不相交子集
 *   - UB 批处理：每核内按 tileLen 分批
 *   - shape 校验：channel==7、同 batch（D5 对标 mmcv 已移除 K<=2000 上限）
 *   - 空 Tensor：batch==0 || N==0 || K==0 → isEmpty=1 → kernel 侧运行时短路
 *   - 极角排序（>3 顶点 Sort32）临时 buffer 由 kernel 侧按固定 32 元素分配，与逻辑规模无关，
 *     Host 侧无需动态精算（历史遗留的 GetSortTmpSize 调用与 sortTmpSize 字段已移除）。
 */

#include "register/op_def_registry.h"
#include "op_common/log/log.h"
#include "op_common/op_host/util/math_util.h"
#include "op_common/op_host/util/platform_util.h"
#include "lib/math/cos_tiling.h"
#include "../../op_kernel/arch35/iou3d_tiling_data.h"

namespace optiling {

using Ops::Base::CeilAlign;
using Ops::Base::CeilDiv;
using Ops::Base::FloorAlign;
using Ops::Base::FloorDiv;

constexpr uint32_t WS_SYS_SIZE = 0U; // 不使用 GM workspace（顶点/排序缓冲均 UB 内驻留）
constexpr size_t WORKSPACE_NUM = 1;
constexpr int64_t IOU3D_DOF = 7; // 7-DoF 通道
// 单批处理的 (i,j) 对数（UB 批大小）。保守取 256（UB 预算 ~180KB < 248KB）。
constexpr uint32_t IOU3D_TILE_LEN = 256U;

// 对齐 kernel 侧配置：仅 Cos 使用高精度角度归约算法，Sin 路径保持不变。
constexpr AscendC::CosConfig IOU3D_HIGH_PRECISION_COS_CONFIG{AscendC::CosAlgo::RADIAN_REDUCTION};

// 获取平台信息（coreNum, ubSize）。
static ge::graphStatus GetPlatformInfo(gert::TilingContext* context, uint64_t* ubSize, int64_t* coreNum)
{
    fe::PlatFormInfos* platformInfoPtr = context->GetPlatformInfo();
    OP_CHECK_NULL_WITH_CONTEXT(context, platformInfoPtr);
    auto ascendcPlatform = platform_ascendc::PlatformAscendC(platformInfoPtr);
    *coreNum = ascendcPlatform.GetCoreNumAiv();
    OP_CHECK_IF(*coreNum == 0, OP_LOGE(context, "coreNum is 0"), return ge::GRAPH_FAILED);
    ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::UB, *ubSize);
    OP_CHECK_IF(*ubSize == 0, OP_LOGE(context, "ubSize is 0"), return ge::GRAPH_FAILED);
    return ge::GRAPH_SUCCESS;
}

// 获取并校验 shape 信息，输出 B/N/K（dtype 校验内置：非 float32 直接报错，不编码进 tiling_key）
static ge::graphStatus GetShapeInfo(gert::TilingContext* context, int64_t* batch, int64_t* numN, int64_t* numK)
{
    auto bboxes = context->GetInputShape(0); // [B, 7, N]
    OP_CHECK_NULL_WITH_CONTEXT(context, bboxes);
    auto gtboxes = context->GetInputShape(1); // [B, 7, K]
    OP_CHECK_NULL_WITH_CONTEXT(context, gtboxes);

    const auto& bShape = bboxes->GetStorageShape();
    const auto& gShape = gtboxes->GetStorageShape();

    // rank-3 校验
    OP_CHECK_IF(
        bShape.GetDimNum() != 3 || gShape.GetDimNum() != 3,
        OP_LOGE(context, "Iou3D: bboxes/gtboxes must be rank-3, got %zu/%zu", bShape.GetDimNum(), gShape.GetDimNum()),
        return ge::GRAPH_FAILED);

    *batch = bShape.GetDim(0);
    *numN = bShape.GetDim(2);
    *numK = gShape.GetDim(2);

    // channel==7 校验
    OP_CHECK_IF(bShape.GetDim(1) != IOU3D_DOF || gShape.GetDim(1) != IOU3D_DOF,
                OP_LOGE(context, "Iou3D: channel dim must be 7 (7-DoF), got bboxes=%ld, gtboxes=%ld", bShape.GetDim(1),
                        gShape.GetDim(1)),
                return ge::GRAPH_FAILED);
    // 同 batch 校验
    OP_CHECK_IF(bShape.GetDim(0) != gShape.GetDim(0),
                OP_LOGE(context, "Iou3D: bboxes/gtboxes must share batch B, got %ld vs %ld", bShape.GetDim(0),
                        gShape.GetDim(0)),
                return ge::GRAPH_FAILED);
    // D5 对标 mmcv：移除 K≤2000 上限（mmcv 无 K 限制）。多核切分按 totalPairs=B*N*K（int64）均分，
    //   UB 批处理按固定 tileLen(256) 分批，Sort32 固定 32 元素（有效顶点 <=16），均与 K 无耦合，任意 K 成立。

    // dtype 校验（float32）。dtype 由 def 文件驱动展开 kernel 变体，此处仅运行时友好报错，
    // 不再编码进 tiling_key（避免与 def 的 DataType 声明重复编码 dtype 维度）。
    auto inputDesc = context->GetInputDesc(0);
    OP_CHECK_NULL_WITH_CONTEXT(context, inputDesc);
    ge::DataType dataType = inputDesc->GetDataType();
    OP_CHECK_IF(dataType != ge::DT_FLOAT,
                OP_LOGE(context, "Iou3D: only float32 supported, got dtype=%d", static_cast<int>(dataType)),
                return ge::GRAPH_FAILED);

    return ge::GRAPH_SUCCESS;
}

// 声明 workspace slot（即使为 0 也必须声明，否则运行时不分配 workspace 指针）
static ge::graphStatus GetWorkspaceSize(gert::TilingContext* context)
{
    size_t* currentWorkspace = context->GetWorkspaceSizes(WORKSPACE_NUM);
    OP_CHECK_NULL_WITH_CONTEXT(context, currentWorkspace);
    currentWorkspace[0] = WS_SYS_SIZE;
    return ge::GRAPH_SUCCESS;
}

static ge::graphStatus Iou3DTilingFunc(gert::TilingContext* context)
{
    // 1、平台信息（coreNum, ubSize）
    uint64_t ubSize;
    int64_t coreNum;
    OP_CHECK_IF(GetPlatformInfo(context, &ubSize, &coreNum) != ge::GRAPH_SUCCESS,
                OP_LOGE(context, "GetPlatformInfo error"), return ge::GRAPH_FAILED);

    // 2、shape 信息 + 校验
    int64_t batch, numN, numK;
    OP_CHECK_IF(GetShapeInfo(context, &batch, &numN, &numK) != ge::GRAPH_SUCCESS,
                OP_LOGE(context, "GetShapeInfo error"), return ge::GRAPH_FAILED);

    // 3、workspace slot
    OP_CHECK_IF(GetWorkspaceSize(context) != ge::GRAPH_SUCCESS, OP_LOGE(context, "GetWorkspaceSize error"),
                return ge::GRAPH_FAILED);

    // 4、填 TilingData
    Iou3DTilingData* tiling = context->GetTilingData<Iou3DTilingData>();
    OP_CHECK_NULL_WITH_CONTEXT(context, tiling);
    OP_CHECK_IF(memset_s(tiling, sizeof(Iou3DTilingData), 0, sizeof(Iou3DTilingData)) != EOK,
                OP_LOGE(context, "set tiling data error"), return ge::GRAPH_FAILED);

    tiling->batch = static_cast<uint32_t>(batch);
    tiling->numBboxes = static_cast<uint32_t>(numN);
    tiling->numGtboxes = static_cast<uint32_t>(numK);

    const uint32_t isEmpty = (batch == 0 || numN == 0 || numK == 0) ? 1U : 0U;
    tiling->isEmpty = isEmpty;

    // 空 Tensor（batch==0 || N==0 || K==0）→ 短路：输出为空矩阵，无 (b,i,j) 对，
    // 单核占位（block=1），kernel 侧运行时判断 isEmpty 直接返回。
    // 注：batch==0 时 totalPairs==0 → pairsPerCore==0 → usedCoreNum==0，若不短路会 SetBlockDim(0) 非法。
    if (isEmpty != 0U) {
        context->SetBlockDim(1);
        return ge::GRAPH_SUCCESS;
    }

    // 多核切分：总 (b,i,j) 对数按核均分，每核负责不相交子集
    const int64_t totalPairs = batch * numN * numK;
    const int64_t pairsPerCore = CeilDiv(totalPairs, coreNum);
    const int64_t usedCoreNum = CeilDiv(totalPairs, pairsPerCore);

    tiling->coreNum = static_cast<uint32_t>(usedCoreNum);
    tiling->pairsPerCore = static_cast<uint32_t>(pairsPerCore);

    // UB 批处理粒度：每核内按 tileLen 分批（不超过本核 pairsPerCore）
    const uint32_t tileLen = (pairsPerCore < static_cast<int64_t>(IOU3D_TILE_LEN)) ?
                                 static_cast<uint32_t>(pairsPerCore) :
                                 IOU3D_TILE_LEN;
    tiling->tileLen = tileLen;
    tiling->tailLen = (tileLen == 0U) ? 0U : static_cast<uint32_t>(pairsPerCore % static_cast<int64_t>(tileLen));

    // 使用与 kernel 相同的 RADIAN_REDUCTION 配置计算最大临时空间。
    // kernel 的向量长度按 32B 对齐，所以这里也使用对齐后的 tile shape。
    const uint32_t alignedTileLen = ((tileLen + 7U) / 8U) * 8U;
    const ge::Shape cosTileShape({static_cast<int64_t>(alignedTileLen)});
    uint32_t cosMaxTmpSize = 0U;
    uint32_t cosMinTmpSize = 0U;
    AscendC::GetCosMaxMinTmpSize(IOU3D_HIGH_PRECISION_COS_CONFIG, cosTileShape, sizeof(float), false, cosMaxTmpSize,
                                 cosMinTmpSize);
    // 部分 CANN 版本 CosConfig 重载可能返回 0（stub 未实现），回退到无 config 重载。
    // 无 config 重载返回 POLYNOMIAL_APPROXIMATION 的 max tmp，该值 >= RADIAN_REDUCTION 的 max tmp
    // （实测 8 elem: 768 vs 288；256 elem: 3072 vs 2080），作为上界安全。
    if (cosMaxTmpSize == 0U) {
        AscendC::GetCosMaxMinTmpSize(cosTileShape, sizeof(float), false, cosMaxTmpSize, cosMinTmpSize);
    }
    OP_CHECK_IF(cosMaxTmpSize == 0U || cosMaxTmpSize > ubSize,
                OP_LOGE(context, "Iou3D: invalid high-precision Cos tmp size %u (UB=%lu)", cosMaxTmpSize, ubSize),
                return ge::GRAPH_FAILED);
    tiling->cosTmpSize = cosMaxTmpSize;

    context->SetBlockDim(static_cast<uint32_t>(usedCoreNum));

    return ge::GRAPH_SUCCESS;
}

static ge::graphStatus TilingParseForIou3D([[maybe_unused]] gert::TilingParseContext* context)
{
    return ge::GRAPH_SUCCESS;
}

struct Iou3DCompileInfo {}; // 必须定义，入图场景依赖

IMPL_OP_OPTILING(Iou3D).Tiling(Iou3DTilingFunc).TilingParse<Iou3DCompileInfo>(TilingParseForIou3D);

} // namespace optiling
