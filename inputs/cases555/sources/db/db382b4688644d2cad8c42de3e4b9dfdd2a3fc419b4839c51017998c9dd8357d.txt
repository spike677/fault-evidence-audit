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
 * \file random_tiling_arch35.h
 * \brief
 */
#ifndef RANDOM_TILING_ARCH35_H
#define RANDOM_TILING_ARCH35_H

#include <unordered_map>
#include <vector>
#include <string>
#include <set>
#include "random/random_common/op_kernel/arch35/random_unified_tiling_data_arch35.h"
namespace optiling {

struct RandomOperatorCompileInfo {
    int64_t totalCoreNum = 0;
    int64_t ubSize = 0;
};

ge::graphStatus ExtractTensorValue(const gert::TilingContext* context, const int64_t constIdx, gert::Shape& constShape);

ge::graphStatus RandomTilingParseArch35(gert::TilingParseContext* context, const std::string& operatorName);

// 输入输出Tensor校验规则配置
struct TensorCheckRule {
    // 输入-1表示不校验
    std::set<ge::DataType> dtypeSet; // 允许的dtype列表
    int64_t shapeSize = -1;          // 要求的shapeSize
    std::set<int64_t> dimNumSet;     // 允许的维度数，为空时不做检查
    // 扩展校验（可按需添加）
    std::function<bool(gert::TilingContext*)> customCheck; // 自定义校验逻辑
};

// 算子私有配置
struct OpTilingConfig {
    // 输入tensor校验规则（key: 输入索引，value: 校验规则）
    std::unordered_map<int32_t, TensorCheckRule> inputCheckRules;
    // 输出tensor校验规则（key: 输出索引，value: 校验规则）
    std::unordered_map<int32_t, TensorCheckRule> outputCheckRules;
    // // 属性校验规则（key: 属性名，value: 自定义校验函数）
    std::unordered_map<int32_t, std::function<bool(gert::TilingContext*)>> attrCheckRules;

    // 字段映射函数（算子仅需实现这些函数，优先查看TilingUtils中公共代码是否可复用）
    std::function<ge::graphStatus(gert::TilingContext*, int64_t&)> getOutputSize;
    std::function<ge::graphStatus(gert::TilingContext*, uint32_t[2], uint32_t[4])> getKeyAndCounter;
    std::function<ge::graphStatus(gert::TilingContext*, int64_t&)> getBufferNum;

    // 启动相关
    bool isNeedSyncAll;

    // Dcache相关  默认为0 表示kernel代码没有simtvf
    int64_t DcacheSize = 0;
    int64_t sharedTmpBufSize = 0;
    int64_t coreAlignSize = 4;
    int64_t ubAlignSize = 0;
    int64_t keepProbNum = 0;
};

class RandomTilingArch35
{
public:
    explicit RandomTilingArch35(gert::TilingContext* context, const OpTilingConfig& config);
    virtual ~RandomTilingArch35() = default;

    // 主流程
    ge::graphStatus DoTiling();

protected:

    // 算子需要特殊的tilingData等处理  需要复写该函数
    virtual ge::graphStatus UniqueProcess()
    {
        // 根据算子特性实现该函数
        return ge::GRAPH_SUCCESS;
    }

    ge::graphStatus CheckInputsOutputsAndAttrs();
    ge::graphStatus GetPlatformInfo();
    ge::graphStatus FillUnifiedTilingData();
    ge::graphStatus DoBlockTiling();
    ge::graphStatus DoUbTiling();
    ge::graphStatus CalcTilingKeyAndWorkspace();
    ge::graphStatus WriteBackToContext();

    ge::graphStatus CheckTensor(const gert::CompileTimeTensorDesc* tensorDesc, const gert::Shape& tensorShape, const TensorCheckRule& rule, const std::string& tensorName);

    // 成员变量
    gert::TilingContext* context_ = nullptr;
    OpTilingConfig config_;
    RandomUnifiedTilingDataStruct tilingData_;

    std::string opName_;
    int64_t totalCoreNum_ = 0;
    int64_t ubSize_ = 0;
    uint64_t tilingKey_ = 0;
    uint64_t workspaceSize_ = 0;
    int64_t bufNum_= 0;
};

} // namespace optiling
#endif // RANDOM_TILING_ARCH35_H