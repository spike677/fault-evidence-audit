/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "grid_sampler3d_grad.h"
#include "opdev/make_op_executor.h"
#include "opdev/aicpu/aicpu_task.h"
#include "opdev/op_def.h"
#include "opdev/op_dfx.h"
#include "opdev/op_executor.h"
#include "opdev/op_log.h"
#include "opdev/shape_utils.h"
#include "aclnn/aclnn_base.h"
#include "acl/acl_rt.h"

using namespace op;

namespace l0op {
OP_TYPE_REGISTER(GridSampler3DGrad);

static const string INTERPOLATION_BILINEAR = "bilinear";
static const string INTERPOLATION_NEAREST = "nearest";

static const string PADDING_ZEROS = "zeros";
static const string PADDING_BORDER = "border";
static const string PADDING_REFLECTION = "reflection";

static const size_t SECOND_DIM = 1;
static const size_t FIFTH_DIM = 4;
static const int64_t AICORE_CHANNEL_LIMIT = 2048;

static const std::initializer_list<op::DataType> AICORE_DTYPE_SUPPORT_LIST = {
    op::DataType::DT_FLOAT, op::DataType::DT_FLOAT16, op::DataType::DT_BF16};

inline const string& GetInterpolationModeStr(int64_t interpolationMode)
{
    if (interpolationMode == 0) {
        return INTERPOLATION_BILINEAR;
    }
    return INTERPOLATION_NEAREST;
}

inline const string& GetPaddingModeStr(int64_t paddingMode)
{
    if (paddingMode == 1) {
        return PADDING_BORDER;
    }
    if (paddingMode == 0) {
        return PADDING_ZEROS;
    }
    return PADDING_REFLECTION;
}

const std::tuple<aclTensor*, aclTensor*> GridSampler3DGrad(
    const aclTensor* gradOutput, const aclTensor* input, const aclTensor* grid, int64_t interpolationMode,
    int64_t paddingMode, bool alignCorners, aclOpExecutor* executor)
{
    L0_DFX(GridSampler3DGrad, gradOutput, input, grid, interpolationMode, paddingMode, alignCorners);
    auto inputGrad = executor->AllocTensor(input->GetViewShape(), input->GetDataType(), input->GetStorageFormat());
    auto gridGrad = executor->AllocTensor(grid->GetViewShape(), grid->GetDataType(), grid->GetStorageFormat());
    if (inputGrad == nullptr || gridGrad == nullptr) {
        OP_LOGE(ACLNN_ERR_INNER_NULLPTR, "alloc gridGrad or inputGrad tensor failed.");
        return std::tie(inputGrad, gridGrad);
    }
    const auto& inputShape = input->GetViewShape();
    auto channel = input->GetStorageFormat() == op::Format::FORMAT_NCDHW ? inputShape.GetDim(SECOND_DIM) :
                                                                           inputShape.GetDim(FIFTH_DIM);
    auto curArch = GetCurrentPlatformInfo().GetCurNpuArch();
    bool checkDtypeSupport = CheckType(gradOutput->GetDataType(), AICORE_DTYPE_SUPPORT_LIST) &&
                             CheckType(input->GetDataType(), AICORE_DTYPE_SUPPORT_LIST) &&
                             CheckType(grid->GetDataType(), AICORE_DTYPE_SUPPORT_LIST);
    if ((curArch == NpuArch::DAV_2201) && checkDtypeSupport && channel <= AICORE_CHANNEL_LIMIT ||
        (curArch == NpuArch::DAV_3510) && checkDtypeSupport) {
        // aicore kernel
        OP_LOGD("GridSampler3DGrad AiCore Kernel.");
        auto ret = ADD_TO_LAUNCHER_LIST_AICORE(
            GridSampler3DGrad, OP_ATTR_NAMES({"interpolation_mode", "padding_mode", "align_corners"}),
            OP_INPUT(gradOutput, input, grid), OP_OUTPUT(inputGrad, gridGrad),
            OP_ATTR(GetInterpolationModeStr(interpolationMode), GetPaddingModeStr(paddingMode), alignCorners));
        if (ret != ACLNN_SUCCESS) {
            OP_LOGE(ACLNN_ERR_INNER_NULLPTR, "GridSampler3DGrad AiCore ADD_TO_LAUNCHER_LIST_AICORE failed.");
            return std::tuple<aclTensor*, aclTensor*>(nullptr, nullptr);
        }
        return std::tie(inputGrad, gridGrad);
    } else {
        // aicpu
        OP_LOGD("GridSampler3DGrad AiCpu Kernel.");
        static internal::AicpuTaskSpace space("GridSampler3DGrad", ge::DEPEND_IN_SHAPE, false);
        auto ret = ADD_TO_LAUNCHER_LIST_AICPU(
            GridSampler3DGrad, OP_ATTR_NAMES({"interpolation_mode", "padding_mode", "align_corners"}),
            OP_INPUT(gradOutput, input, grid), OP_OUTPUT(inputGrad, gridGrad),
            OP_ATTR(GetInterpolationModeStr(interpolationMode), GetPaddingModeStr(paddingMode), alignCorners));
        if (ret != ACLNN_SUCCESS) {
            OP_LOGE(ACLNN_ERR_INNER_NULLPTR, "GridSampler3DGrad AiCpu ADD_TO_LAUNCHER_LIST_AICPU failed.");
            return std::tuple<aclTensor*, aclTensor*>(nullptr, nullptr);
        }
        return std::tie(inputGrad, gridGrad);
    }
}
} // namespace l0op
