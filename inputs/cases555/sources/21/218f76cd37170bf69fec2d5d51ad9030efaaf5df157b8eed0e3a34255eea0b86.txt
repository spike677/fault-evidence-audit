/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "reduce_all.h"
#include "aclnn_kernels/reshape.h"
#include "opdev/make_op_executor.h"
#include "opdev/op_dfx.h"
#include "opdev/op_log.h"
#include "opdev/shape_utils.h"
#include "aclnn_kernels/common/op_error_check.h"

namespace l0op {
OP_TYPE_REGISTER(ReduceAll);

const aclTensor* ReduceAll(const aclTensor* self, const aclIntArray* dim, bool keepdim, aclOpExecutor* executor)
{
    L0_DFX(ReduceAll, self, dim, keepdim);
    // 固定写法，创建OpExecutor
    auto dims = executor->ConvertToTensor(dim, op::DataType::DT_INT64);
    auto out = executor->AllocTensor(self->GetViewShape(), op::DataType::DT_BOOL);
    if (self->GetViewShape().GetDimNum() != 0 || !keepdim) {
        auto ret = INFER_SHAPE(ReduceAll, OP_INPUT(self, dims), OP_OUTPUT(out), OP_ATTR(keepdim));
        if (ret != ACLNN_SUCCESS) {
            return nullptr;
        }
    }
    auto retAicore =
        ADD_TO_LAUNCHER_LIST_AICORE(ReduceAll, op::AI_CORE, OP_INPUT(self, dims), OP_ATTR(keepdim), OP_OUTPUT(out));
    OP_CHECK_ADD_TO_LAUNCHER_LIST_AICORE(
        retAicore != ACLNN_SUCCESS, return nullptr, "ReduceAll ADD_TO_LAUNCHER_LIST_AICORE failed.");
    return out;
}
} // namespace l0op
