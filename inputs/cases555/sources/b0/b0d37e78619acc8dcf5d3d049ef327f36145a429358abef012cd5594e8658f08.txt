/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

#include "aclnn_grid_sampler3d.h"
#include "aclnn_kernels/contiguous.h"
#include "image/grid_sample3_d/op_host/op_api/grid_sampler3d.h"
#include "image/grid_sample/op_api/grid_sample.h"
#include "aclnn_kernels/transpose.h"
#include "opdev/common_types.h"
#include "opdev/data_type_utils.h"
#include "opdev/format_utils.h"
#include "opdev/op_dfx.h"
#include "opdev/op_executor.h"
#include "opdev/op_log.h"
#include "opdev/shape_utils.h"
#include "opdev/tensor_view_utils.h"
#include "opdev/make_op_executor.h"
#include "op_api/aclnn_check.h"
#include "aclnn_kernels/common/op_error_check.h"

using namespace op;
#ifdef __cplusplus
extern "C" {
#endif

static const size_t FIRST_DIM = 0;
static const size_t SECOND_DIM = 1;
static const size_t THIRD_DIM = 2;
static const size_t FOURTH_DIM = 3;
static const size_t FIFTH_DIM = 4;

static const size_t INT_3 = 3;
static const size_t INT_4 = 4;
static const size_t INT_16 = 16;
static const size_t INT_22 = 22;
static const size_t INT_64 = 64;
static const size_t INT_88 = 88;

static const int64_t INTERPOLATION_MODE_MIN_VALUE = 0;
static const int64_t INTERPOLATION_MODE_MAX_VALUE = 1;
static const int64_t PADDING_MODE_MIN_VALUE = 0;
static const int64_t PADDING_MODE_MAX_VALUE = 2;
static const int64_t VOLUMETRIC_GRID_LAST_DIM_SIZE = 3;
static const int64_t VOLUMETRIC_DIM_NUM = 5;

// 根据API定义，需要列出所能支持的所有dtype
static const std::initializer_list<op::DataType> DTYPE_SUPPORT_LIST = {
    op::DataType::DT_FLOAT16, op::DataType::DT_FLOAT, op::DataType::DT_DOUBLE, op::DataType::DT_BF16};

static const std::initializer_list<op::Format> FORMAT_SUPPORT_LIST = {
    op::Format::FORMAT_NCDHW, op::Format::FORMAT_NDHWC, op::Format::FORMAT_ND};

static bool CheckNotNull(const aclTensor *input, const aclTensor *grid, const aclTensor *out)
{
    OP_CHECK_NULL(input, return false);
    OP_CHECK_NULL(grid, return false);
    OP_CHECK_NULL(out, return false);
    return true;
}

static bool CheckRegBaseSuppport(const aclTensor *input, int64_t interpolationMode)
{
    if (input->GetDataType() != op::DataType::DT_FLOAT && input->GetDataType() != op::DataType::DT_FLOAT16 && input->GetDataType() != op::DataType::DT_BF16) {
        OP_LOGD("Only support float16, float32 or bfloat16 on AICore, but got data type is %s", op::ToString(input->GetDataType()).GetString());
        return false;
    }
    bool isRegBaseArchFlag = IsRegBase();
    if (isRegBaseArchFlag && interpolationMode == INTERPOLATION_MODE_MIN_VALUE) {
        return true;
    }
    return false;
}

static bool CheckDtypeValid(const aclTensor *input, const aclTensor *grid, const aclTensor *out)
{
    // 检查input、grid、out的数据类型是否一致
    OP_CHECK_DTYPE_NOT_MATCH(grid, input->GetDataType(), return false);
    OP_CHECK_DTYPE_NOT_MATCH(out, input->GetDataType(), return false);

    // 检查input的数据类型是否在算子的支持列表内
    OP_CHECK_DTYPE_NOT_SUPPORT(input, DTYPE_SUPPORT_LIST, return false);

    return true;
}

static bool CheckFormat(const op::Format format, const std::initializer_list<op::Format> &valid_formats)
{
    return std::find(valid_formats.begin(), valid_formats.end(), format) != valid_formats.end();
}

namespace {
static bool CheckFormatValid(const aclTensor *input, const aclTensor *out)
{
    const op::Format inputFormat = input->GetStorageFormat();
    if (!CheckFormat(inputFormat, FORMAT_SUPPORT_LIST)) {
        OP_LOGE(ACLNN_ERR_PARAM_INVALID,
            "Input format only supports [NCDHW, NDHWC, ND] format, but format is [%s]",
            op::ToString(inputFormat).GetString());
        return false;
    }

    const op::Format outFormat = out->GetStorageFormat();
    if (!CheckFormat(outFormat, FORMAT_SUPPORT_LIST)) {
        OP_LOGE(ACLNN_ERR_PARAM_INVALID,
            "Out format only supports [NCDHW, NDHWC, ND] format, but format is [%s]",
            op::ToString(outFormat).GetString());
        return false;
    }

    return true;
}
}  // namespace

static bool CheckAttrValid(int64_t interpolationMode, int64_t paddingMode)
{
    // 检查interpolationMode 、paddingMode是否在支持范围内
    if (paddingMode < PADDING_MODE_MIN_VALUE || paddingMode > PADDING_MODE_MAX_VALUE) {
        OP_LOGE(ACLNN_ERR_PARAM_INVALID,
            "paddingMode %ld should be in range [%ld, %ld].",
            paddingMode,
            PADDING_MODE_MIN_VALUE,
            PADDING_MODE_MAX_VALUE);
        return false;
    }

    if (interpolationMode < INTERPOLATION_MODE_MIN_VALUE || interpolationMode > INTERPOLATION_MODE_MAX_VALUE) {
        OP_LOGE(ACLNN_ERR_PARAM_INVALID,
            "interpolationMode %ld should be in range [%ld, %ld].",
            interpolationMode,
            INTERPOLATION_MODE_MIN_VALUE,
            INTERPOLATION_MODE_MAX_VALUE);
        return false;
    }
    return true;
}

static bool CheckShape(const aclTensor *input, const aclTensor *grid, const aclTensor *out)
{
    const auto &inputShape = input->GetViewShape();
    const auto &gridShape = grid->GetViewShape();
    const auto &outShape = out->GetViewShape();

    OP_CHECK_WRONG_DIMENSION(input, VOLUMETRIC_DIM_NUM, return false);
    OP_CHECK_WRONG_DIMENSION(grid, VOLUMETRIC_DIM_NUM, return false);
    OP_CHECK_WRONG_DIMENSION(out, VOLUMETRIC_DIM_NUM, return false);

    if (inputShape.GetDim(FIRST_DIM) != gridShape.GetDim(FIRST_DIM) ||
        inputShape.GetDim(FIRST_DIM) != outShape.GetDim(FIRST_DIM)) {
        OP_LOGE(ACLNN_ERR_PARAM_INVALID,
            "expect input grid and out to have same batch size, but got input with shape [%s] \
            grid with shape [%s] and out with shape [%s]",
            op::ToString(inputShape).GetString(),
            op::ToString(gridShape).GetString(),
            op::ToString(outShape).GetString());
        return false;
    }

    const op::Format inputFormat = input->GetStorageFormat();
    const size_t channelIndex = inputFormat == op::Format::FORMAT_NDHWC ? FIFTH_DIM : SECOND_DIM;
    if (inputShape.GetDim(channelIndex) != outShape.GetDim(channelIndex)) {
        OP_LOGE(ACLNN_ERR_PARAM_INVALID,
            "expect input and out to have same channel size, but got input with shape [%s] \
            and out with shape [%s]",
            op::ToString(inputShape).GetString(),
            op::ToString(outShape).GetString());
        return false;
    }

    const size_t deepIndex = inputFormat == op::Format::FORMAT_NDHWC ? SECOND_DIM : THIRD_DIM;
    const size_t heightIndex = inputFormat == op::Format::FORMAT_NDHWC ? THIRD_DIM : FOURTH_DIM;
    const size_t widthIndex = inputFormat == op::Format::FORMAT_NDHWC ? FOURTH_DIM : FIFTH_DIM;
    if ((gridShape.GetDim(SECOND_DIM) != outShape.GetDim(deepIndex)) ||
        (gridShape.GetDim(THIRD_DIM) != outShape.GetDim(heightIndex)) ||
        (gridShape.GetDim(FOURTH_DIM) != outShape.GetDim(widthIndex))) {
        OP_LOGE(ACLNN_ERR_PARAM_INVALID,
            "expect grid and out to have same D H W size, but got grid with shape [%s] \
            and out with shape [%s]",
            op::ToString(gridShape).GetString(),
            op::ToString(outShape).GetString());
        return false;
    }

    if (inputShape.GetDim(FOURTH_DIM) == 0 || inputShape.GetDim(FIFTH_DIM) == 0) {
        OP_LOGE(ACLNN_ERR_PARAM_INVALID,
            "expect input to have non-empty spatial dimensions, but got input with shape [%s]",
            op::ToString(inputShape).GetString());
        return false;
    }
    if (gridShape.GetDim(FIFTH_DIM) != VOLUMETRIC_GRID_LAST_DIM_SIZE) {
        OP_LOGE(ACLNN_ERR_PARAM_INVALID,
            "expect grid to have size %ld in last dimension, but got grid with shape [%s]",
            VOLUMETRIC_GRID_LAST_DIM_SIZE,
            op::ToString(gridShape).GetString());
        return false;
    }
    return true;
}

static aclnnStatus CheckParams(
    const aclTensor *input, const aclTensor *grid, int64_t interpMode, int64_t padMode, const aclTensor *out)
{
    // 1. 检查参数是否为空指针
    CHECK_RET(CheckNotNull(input, grid, out), ACLNN_ERR_PARAM_NULLPTR);

    // 2. 检查输入、输出的数据类型是否在API支持的数据类型范围之内，需要根据api定义校验
    CHECK_RET(CheckDtypeValid(input, grid, out), ACLNN_ERR_PARAM_INVALID);

    // 3. 检查输入、输出的format是否在算子的支持范围之内
    CHECK_RET(CheckFormatValid(input, out), ACLNN_ERR_PARAM_INVALID);

    // 4. 检查属性参数是否在支持范围内
    CHECK_RET(CheckAttrValid(interpMode, padMode), ACLNN_ERR_PARAM_INVALID);

    // 5. 检查输入、输出的shape匹配关系
    CHECK_RET(CheckShape(input, grid, out), ACLNN_ERR_PARAM_INVALID);

    return ACLNN_SUCCESS;
}

namespace {
static bool CheckAiCoreSuppport(const aclTensor *input, int64_t interpolationMode)
{
    if (input->GetDataType() != op::DataType::DT_FLOAT && input->GetDataType() != op::DataType::DT_FLOAT16 &&
        input->GetDataType() != op::DataType::DT_BF16) {
        OP_LOGD("Only support float16, float32 or bfloat16 on AICore, but got data type is %s",
            op::ToString(input->GetDataType()).GetString());
        return false;
    }
    auto curArch = GetCurrentPlatformInfo().GetCurNpuArch();
    bool is2201Arch = curArch == NpuArch::DAV_2201;
    if (is2201Arch) {
        return true;
    }

    // 950芯片非bilinear场景，走到老模板
    bool isRegBaseArch = IsRegBase(curArch);
    if (isRegBaseArch && interpolationMode != INTERPOLATION_MODE_MIN_VALUE) {
        return true;
    }
    return false;
}

static bool CheckAiCpuSuppport(const aclTensor *input)
{
    if (input->GetDataType() != op::DataType::DT_FLOAT && input->GetDataType() != op::DataType::DT_FLOAT16 &&
        input->GetDataType() != op::DataType::DT_DOUBLE) {
        OP_LOGD("Only support float16, float32 or double on AICpu, but got data type is %s",
            op::ToString(input->GetDataType()).GetString());
        return false;
    }
    return true;
}
}  // namespace

static const aclTensor *CheckAndTranspose(
    const aclTensor *target, const op::Format inputFormat, bool isInput, bool isSpecialcase, aclOpExecutor *executor)
{
    if (isInput) {
        if (inputFormat == op::Format::FORMAT_NCDHW || inputFormat == op::Format::FORMAT_ND) {
            if (!isSpecialcase) {
                int64_t perm[5] = {0, 2, 3, 4, 1};
                auto valuePerm = executor->AllocIntArray(perm, 5);
                target = l0op::Transpose(target, valuePerm, executor);
            }
        } else if (inputFormat == op::Format::FORMAT_NDHWC) {
            if (isSpecialcase) {
                int64_t perm[5] = {0, 4, 1, 2, 3};
                auto valuePerm = executor->AllocIntArray(perm, 5);
                target = l0op::Transpose(target, valuePerm, executor);
            }
        }
    } else {
        if (inputFormat == op::Format::FORMAT_NDHWC) {
            int64_t perm[5] = {0, 2, 3, 4, 1};
            auto valuePerm = executor->AllocIntArray(perm, 5);
            target = l0op::Transpose(target, valuePerm, executor);
        }
    }
    return target;
}

static bool CheckSpecialCase(const aclTensor *input, const aclTensor *grid)
{
    const auto &inputDType = input->GetDataType();
    if (inputDType != op::DataType::DT_FLOAT16 && inputDType != op::DataType::DT_FLOAT) {
        return false;
    }
    const auto &inputShape = input->GetViewShape();
    const auto &gridShape = grid->GetViewShape();
    auto xshape_N = inputShape.GetDim(FIRST_DIM);
    int64_t xshape_C = 0;
    int64_t xshape_D = 0;
    int64_t xshape_H = 0;
    int64_t xshape_W = 0;
    auto gridshape_N = gridShape.GetDim(FIRST_DIM);
    auto gridshape_D = gridShape.GetDim(SECOND_DIM);
    auto gridshape_H = gridShape.GetDim(THIRD_DIM);
    auto gridshape_W = gridShape.GetDim(FOURTH_DIM);
    auto gridshape_3 = gridShape.GetDim(FIFTH_DIM);
    const op::Format inputFormat = input->GetStorageFormat();
    if (inputFormat == op::Format::FORMAT_NCDHW || inputFormat == op::Format::FORMAT_ND) {
        xshape_C = inputShape.GetDim(SECOND_DIM);
        xshape_D = inputShape.GetDim(THIRD_DIM);
        xshape_H = inputShape.GetDim(FOURTH_DIM);
        xshape_W = inputShape.GetDim(FIFTH_DIM);
    } else if (inputFormat == op::Format::FORMAT_NDHWC) {
        xshape_D = inputShape.GetDim(SECOND_DIM);
        xshape_H = inputShape.GetDim(THIRD_DIM);
        xshape_W = inputShape.GetDim(FOURTH_DIM);
        xshape_C = inputShape.GetDim(FIFTH_DIM);
    }
    if (xshape_N != gridshape_N || xshape_D != gridshape_D || xshape_H != gridshape_H || xshape_W != gridshape_W ||
        xshape_D != INT_16 || xshape_H != INT_64 || xshape_W != INT_64 || gridshape_3 != INT_3) {
        return false;
    }
    return xshape_C == INT_4 && (xshape_N == INT_22 || xshape_N == INT_88);
}

aclnnStatus aclnnGridSampler3DGetWorkspaceSize(const aclTensor *input, const aclTensor *grid, int64_t interpolationMode,
    int64_t paddingMode, bool alignCorners, aclTensor *out, uint64_t *workspaceSize, aclOpExecutor **executor)
{
    L2_DFX_PHASE_1(aclnnGridSampler3D, DFX_IN(input, grid, interpolationMode, paddingMode, alignCorners), DFX_OUT(out));
    auto uniqueExecutor = CREATE_EXECUTOR();  // 固定写法，创建OpExecutor
    CHECK_RET(uniqueExecutor.get() != nullptr, ACLNN_ERR_INNER_CREATE_EXECUTOR);
    auto ret = CheckParams(input, grid, interpolationMode, paddingMode, out);
    CHECK_RET(ret == ACLNN_SUCCESS, ret);
    if (input->IsEmpty() || grid->IsEmpty()) {
        *workspaceSize = 0;
        uniqueExecutor.ReleaseTo(executor);
        return ACLNN_SUCCESS;
    }
    // 固定写法，将输入input转换成连续的tensor
    auto inputTensor = l0op::Contiguous(input, uniqueExecutor.get());
    CHECK_RET(inputTensor != nullptr, ACLNN_ERR_INNER_NULLPTR);
    // 固定写法，将输入grid转换成连续的tensor
    auto gridTensor = l0op::Contiguous(grid, uniqueExecutor.get());
    CHECK_RET(gridTensor != nullptr, ACLNN_ERR_INNER_NULLPTR);
    bool supportAiCore = CheckAiCoreSuppport(input, interpolationMode);
    bool supportAiCpu = CheckAiCpuSuppport(input);
    const op::Format inputFormat = input->GetStorageFormat();
    bool isSpecialcase = interpolationMode == 0 && CheckSpecialCase(input, grid);
    bool regBase = CheckRegBaseSuppport(input, interpolationMode);
    const aclTensor *gridSampler3DOut = nullptr;
    if (supportAiCore) {
        inputTensor = CheckAndTranspose(inputTensor, inputFormat, true, isSpecialcase, uniqueExecutor.get());
        gridSampler3DOut = l0op::GridSample3D(inputTensor,
            gridTensor,
            interpolationMode,
            paddingMode,
            alignCorners,
            !isSpecialcase,
            uniqueExecutor.get());
    } else if (regBase) {
        gridSampler3DOut = l0op::GridSample3D(inputTensor,
            gridTensor,
            interpolationMode,
            paddingMode,
            alignCorners,
            false,
            uniqueExecutor.get());
    } else if (supportAiCpu) {
        gridSampler3DOut = l0op::GridSampler3D(
            inputTensor, gridTensor, interpolationMode, paddingMode, alignCorners, uniqueExecutor.get());
    } else {
        std::string alignCornerStr = alignCorners ? "true" : "false";
        OP_LOGE(ACLNN_ERR_PARAM_INVALID,
            "The op info is not supported. Plsease check op info! DataType support list is %s, got data type is %s. \
            interpolationMode support 0(bilinear) , 1(nearest) or 2(bicubic), got interpolationMode is %ld. \
            paddingMode support 0(zeros) , 1(border) or 2(reflection), got paddingMode is %ld. \
            alignCorners support false and true, got alignCorners is %s. \
            Notice that when data type is bfloat16, only support by ascend910B or ascend910_93.",
            op::ToString(DTYPE_SUPPORT_LIST).GetString(),
            op::ToString(input->GetDataType()).GetString(),
            interpolationMode,
            paddingMode,
            alignCornerStr.c_str());
        return ACLNN_ERR_PARAM_INVALID;
    }
    CHECK_RET(gridSampler3DOut != nullptr, ACLNN_ERR_INNER_NULLPTR);
    gridSampler3DOut = CheckAndTranspose(gridSampler3DOut, inputFormat, false, isSpecialcase, uniqueExecutor.get());
    // 固定写法，将计算结果拷贝到输出out上，out可能是非连续的tensor
    auto viewCopyResult = l0op::ViewCopy(gridSampler3DOut, out, uniqueExecutor.get());
    CHECK_RET(viewCopyResult != nullptr, ACLNN_ERR_INNER_NULLPTR);
    // 固定写法，获取计算过程中需要使用的workspace大小
    *workspaceSize = uniqueExecutor->GetWorkspaceSize();
    uniqueExecutor.ReleaseTo(executor);
    return ACLNN_SUCCESS;
}

aclnnStatus aclnnGridSampler3D(void *workspace, uint64_t workspaceSize, aclOpExecutor *executor, aclrtStream stream)
{
    L2_DFX_PHASE_2(aclnnGridSampler3D);
    // 固定写法，调用框架能力，完成计算
    return CommonOpExecutorRun(workspace, workspaceSize, executor, stream);
}

#ifdef __cplusplus
}

#endif
