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
 * \file resize_bilinear_v2_tiling_arch35.cpp
 * \brief resize_bilinear_v2_tiling_arch35
 */
#include "resize_bilinear_v2_tiling_arch35.h"
#include "op_host/tiling_util.h"
#include "register/op_impl_registry.h"
#include "log/log.h"
#include "util/math_util.h"

namespace optiling {
constexpr size_t ATTR_ALIGN_CORERS_IDX = 0;
constexpr size_t ATTR_HALF_PIXEL_CENTERS_IDX = 1;
constexpr size_t ATTR_SCALES_IDX = 3;
constexpr size_t SCALES_NUM = 2;
constexpr size_t INPUT_X_IDX = 0;
constexpr size_t OUTPUT_Y_IDX = 0;
constexpr size_t DIM_LEN_4D = 4;
constexpr size_t C_DIM_IDX_NHWC = 3;
constexpr size_t C_DIM_IDX_NCHW = 1;
constexpr size_t N_DIM_IDX = 0;
constexpr size_t H_DIM_IDX_NCHW = 2;
constexpr size_t H_DIM_IDX_NHWC = 1;
constexpr size_t H_DIM_IDX_NCDHW = 3;
constexpr size_t WORKSPACE_SIZE = 32;
constexpr int64_t TILING_KEY_C_PARALLEL = 10000;
constexpr int64_t TILING_KEY_SIMT_NHWC = 30000;
constexpr int64_t TILING_KEY_SIMT_NCHW = 30001;
constexpr int64_t TILING_KEY_SIMT_NHWC_IDX64 = 30002;
constexpr int64_t TILING_KEY_SIMT_NCHW_IDX64 = 30003;
constexpr int64_t TILING_KEY_SIMT_HW = 30004;
constexpr int64_t TILING_KEY_SIMT_HW_IDX64 = 30005;
constexpr int64_t TILING_KEY_ALL_COPY = 40000;
constexpr int64_t TILING_KEY_POINT_COPY = 40001;
constexpr int64_t TILING_KEY_NCHW_BROADCAST = 40002;
constexpr int64_t TILING_KEY_NHWC_BROADCAST = 40003;
constexpr int64_t ONE_BLOCK_SIZE = 32;
constexpr int64_t RSV_BLOCK_NUM = 8;
constexpr int64_t DB_BUFF_NUM = 2;
constexpr int64_t EVEN_FACTOR = 2;
constexpr float C_PARALLEL_SCALE_THRES = 2.0f;
constexpr int64_t HW_CACHE_DB_FACTOR = 1;
constexpr int64_t C_PARALLEL_X_TENSOR_NUM = 4;
constexpr int64_t C_PARALLEL_Y_TENSOR_NUM = 1;
constexpr float HALF_PIXEL = 0.5;
constexpr int64_t MIN_C_SIZE = 128;
constexpr int64_t SIMT_C_SIZE = 64;
constexpr int64_t IDX_DST_H = 0;
constexpr int64_t IDX_DST_W = 1;
constexpr int64_t SIMT_DEFAULT_THREAD_NUM = 1024;
constexpr int64_t SIMT_DEFAULT_THREAD_NUM_IDX64 = 512;
static const float FLT_EPSILON = 1e-6;

class ResizeBilinearV2AscendCTilingImpl {
public:
    explicit ResizeBilinearV2AscendCTilingImpl(gert::TilingContext* context) : context_(context) {};

    ge::graphStatus Init(const ResizeBilinearV2CompileInfo* compileInfo);
    ge::graphStatus DoTiling();

private:
    ge::graphStatus CheckFormatMatchDims();
    void MatchTilingStrategyAndSetTilingKey();

    int64_t FindBest2DTiling(int64_t lenM, int64_t lenN);
    void TilingStrategy();
    void SetDimsByFormat();

    void DoTilingAllCopy();
    void DoTilingPointCopy();
    void DoTilingBroadCastNCHW();
    void DoTilingBroadCastNHWC();
    void DoTilingCParallel();
    void DoTilingSIMT_HW();
    void DoTilingSIMT();
    bool IsMatchCParallel();
    bool IsMatchAllCopy();
    bool IsMatchPointCopy();
    bool IsMatchBroadCastNCHW();
    bool IsMatchBroadCastNHWC();
    void FillTilingData();
    void PrintTilingData();
    ge::graphStatus SetScales();
    ge::graphStatus CheckDtypeAndFormat();
    ge::graphStatus SetShape();
    inline int64_t Min(int64_t x, int64_t y);
    float ComputeScale(float scale, int64_t lenSrc, int64_t lenDes);
    bool MatchPointCopyCondition();

private:
    int32_t dtypeSizeX_ = 0;
    int32_t dtypeSizeY_ = 0;
    int64_t coreNum_ = 0;
    int64_t ubSize_ = 0;
    int64_t ubBlockNum_ = 0;
    int64_t tilingKey_ = 0;
    int64_t realCoreNum_ = 0;
    int64_t lenC_ = 0;
    int64_t lenN_ = 0;
    int64_t lenSrcH_ = 0;
    int64_t lenSrcW_ = 0;
    int64_t lenDesH_ = 0;
    int64_t lenDesW_ = 0;

    int64_t nFactor_ = 0;
    int64_t hFactor_ = 0;
    int64_t wFactor_ = 0;
    int64_t cFactor_ = 0;
    int64_t hwFactor_ = 0;

    int64_t ubNFactor_ = 0;
    int64_t ubHFactor_ = 0;
    int64_t ubWFactor_ = 0;
    int64_t ubCFactor_ = 0;
    int64_t ubHWFactor_ = 0;

    int64_t splitBlockFactor_ = 0;
    int64_t splitBlockTailFactor_ = 0;
    int64_t alignCorners_ = 0;
    int64_t halfPixelCenters_ = 0;
    float scaleW_ = 0.0f;
    float scaleH_ = 0.0f;
    bool scaleValid_ = false;

    int64_t lenCAlign_ = 0;
    bool isAlign_ = false;

    ge::DataType dtypeX_ = ge::DT_MAX;
    ge::DataType dtypeY_ = ge::DT_MAX;
    ge::Format format_ = ge::FORMAT_MAX;
    gert::Shape xShape_;
    gert::Shape yShape_;
    gert::TilingContext* context_ = nullptr;
    ResizeBilinearV2TilingData tilingData_;
};

inline int64_t ResizeBilinearV2AscendCTilingImpl::Min(int64_t x, int64_t y) { return (x < y) ? x : y; }

ge::graphStatus ResizeBilinearV2AscendCTilingImpl::CheckFormatMatchDims()
{
    OP_CHECK_IF(alignCorners_ && halfPixelCenters_,
                OP_LOGE_FOR_INVALID_VALUES_WITH_REASON(
                    context_->GetNodeName(), "align_corners and half_pixel_centers", "true and true",
                    "The values of attributes align_corners and half_pixel_centers cannot be true at the same time"),
                return ge::GRAPH_FAILED);

    if (xShape_.GetDimNum() != DIM_LEN_4D || yShape_.GetDimNum() != DIM_LEN_4D) {
        std::string dimMsg = std::to_string(xShape_.GetDimNum()) + " and " + std::to_string(yShape_.GetDimNum());
        OP_LOGE_FOR_INVALID_SHAPEDIMS_WITH_REASON(context_->GetNodeName(), "x and y", dimMsg.c_str(),
                                                  "The shape of input x and output y must be 4D");
        return ge::GRAPH_FAILED;
    }

    const int64_t inputSize = xShape_.GetShapeSize();
    const int64_t outSize = yShape_.GetShapeSize();
    if (inputSize == 0 || outSize == 0) {
        std::string shapesizeMsg = std::to_string(inputSize) + " and " + std::to_string(outSize);
        OP_LOGE_FOR_INVALID_SHAPESIZES_WITH_REASON(context_->GetNodeName(), "x and y", shapesizeMsg.c_str(),
                                                   "Input x and output y do not support empty tensors");
        return ge::GRAPH_FAILED;
    }
    return ge::GRAPH_SUCCESS;
}

float ResizeBilinearV2AscendCTilingImpl::ComputeScale(float scale, int64_t lenSrc, int64_t lenDes)
{
    float newScale = 0.0f;
    if (scale > 0.0f) {
        newScale = static_cast<float>(1.0f) / scale;
    } else {
        newScale = static_cast<float>(lenSrc) / static_cast<float>(lenDes);
    }
    return newScale;
}

void ResizeBilinearV2AscendCTilingImpl::SetDimsByFormat()
{
    lenN_ = xShape_.GetDim(N_DIM_IDX);

    if (format_ == ge::FORMAT_NCHW) {
        lenC_ = xShape_.GetDim(C_DIM_IDX_NCHW);
    } else if (format_ == ge::FORMAT_NHWC) {
        lenC_ = xShape_.GetDim(C_DIM_IDX_NHWC);
    }

    if (format_ == ge::FORMAT_NCHW) {
        lenSrcH_ = xShape_.GetDim(H_DIM_IDX_NCHW);
        lenDesH_ = yShape_.GetDim(H_DIM_IDX_NCHW);
        lenSrcW_ = xShape_.GetDim(H_DIM_IDX_NCHW + 1);
        lenDesW_ = yShape_.GetDim(H_DIM_IDX_NCHW + 1);
    } else if (format_ == ge::FORMAT_NHWC) {
        lenSrcH_ = xShape_.GetDim(H_DIM_IDX_NHWC);
        lenDesH_ = yShape_.GetDim(H_DIM_IDX_NHWC);
        lenSrcW_ = xShape_.GetDim(H_DIM_IDX_NHWC + 1);
        lenDesW_ = yShape_.GetDim(H_DIM_IDX_NHWC + 1);
    }

    nFactor_ = lenN_;
    hFactor_ = lenDesH_;
    wFactor_ = lenDesW_;
    cFactor_ = lenC_;
    hwFactor_ = lenDesH_ * lenDesW_;
    ubNFactor_ = nFactor_;
    ubHFactor_ = hFactor_;
    ubWFactor_ = wFactor_;
    ubCFactor_ = cFactor_;
    ubHWFactor_ = hwFactor_;

    OP_LOGI(context_->GetNodeName(), "lenN_:%ld , lenC_: %ld, srcH:%ld, srcW:%ld, dstH:%ld, dstW:%ld", lenN_, lenC_,
            lenSrcH_, lenSrcW_, lenDesH_, lenDesW_);

    isAlign_ = false;
    if ((lenC_ * dtypeSizeX_) % ONE_BLOCK_SIZE == 0) {
        isAlign_ = true;
    }
    lenCAlign_ = Ops::Base::CeilAlign(lenC_ * dtypeSizeX_, ONE_BLOCK_SIZE) / dtypeSizeX_;

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
}

bool ResizeBilinearV2AscendCTilingImpl::IsMatchAllCopy()
{
    if (dtypeX_ != dtypeY_) {
        return false;
    }

    return (lenSrcH_ == lenDesH_ && lenSrcW_ == lenDesW_);
}

bool ResizeBilinearV2AscendCTilingImpl::MatchPointCopyCondition()
{
    if (dtypeX_ != dtypeY_) {
        return false;
    }

    if (format_ != ge::FORMAT_NHWC) {
        return false;
    }

    if (lenC_ * dtypeSizeX_ < MIN_C_SIZE) {
        return false;
    }

    if (scaleH_ < 1.0 || scaleW_ < 1.0) {
        return false;
    }
    return true;
}

bool ResizeBilinearV2AscendCTilingImpl::IsMatchPointCopy()
{
    if (!MatchPointCopyCondition()) {
        return false;
    }

    int64_t FloorScaleH = static_cast<int64_t>(scaleH_ + FLT_EPSILON);
    int64_t FloorScaleW = static_cast<int64_t>(scaleW_ + FLT_EPSILON);

    if (abs(scaleH_ - FloorScaleH) >= FLT_EPSILON || abs(scaleW_ - FloorScaleW) >= FLT_EPSILON) {
        return false;
    }

    if (alignCorners_ != ATTR_ALIGN_CORERS_IDX) {
        return true;
    } else {
        // alignCorners_ = False
        if (halfPixelCenters_ != ATTR_HALF_PIXEL_CENTERS_IDX) {
            return true;
        } else {
            // 整数倍缩小，且倍数为奇数
            if (FloorScaleH % EVEN_FACTOR == 1 && FloorScaleW % EVEN_FACTOR == 1) {
                return true;
            }
            return false;
        }
    }
}

bool ResizeBilinearV2AscendCTilingImpl::IsMatchBroadCastNCHW()
{
    if (dtypeX_ != dtypeY_) {
        return false;
    }

    if (format_ != ge::FORMAT_NCHW) {
        return false;
    }

    if (lenDesH_ * lenDesW_ * dtypeSizeY_ < MIN_C_SIZE) {
        return false;
    }

    return (lenSrcH_ == 1 && lenSrcW_ == 1);
}

bool ResizeBilinearV2AscendCTilingImpl::IsMatchBroadCastNHWC()
{
    if (dtypeX_ != dtypeY_) {
        return false;
    }

    if (lenC_ * dtypeSizeX_ < MIN_C_SIZE) {
        return false;
    }

    if (format_ != ge::FORMAT_NHWC) {
        return false;
    }

    return (lenSrcH_ == 1 && lenSrcW_ == 1);
}

bool ResizeBilinearV2AscendCTilingImpl::IsMatchCParallel()
{
    if (format_ != ge::FORMAT_NHWC) {
        return false;
    }

    if (lenC_ * dtypeSizeX_ < MIN_C_SIZE) {
        return false;
    }

    if (scaleW_ < C_PARALLEL_SCALE_THRES || scaleH_ < C_PARALLEL_SCALE_THRES) {
        return false;
    }

    return true;
}

void ResizeBilinearV2AscendCTilingImpl::DoTilingAllCopy()
{
    realCoreNum_ = (yShape_.GetShapeSize() < coreNum_) ? yShape_.GetShapeSize() : coreNum_;
    splitBlockFactor_ = Ops::Base::FloorDiv(yShape_.GetShapeSize(), realCoreNum_);
    splitBlockTailFactor_ = yShape_.GetShapeSize() - splitBlockFactor_ * realCoreNum_;
    ubCFactor_ = ubBlockNum_ / DB_BUFF_NUM * ONE_BLOCK_SIZE / dtypeSizeX_;
}

void ResizeBilinearV2AscendCTilingImpl::DoTilingPointCopy()
{
    // N H多核双切分
    int64_t np = FindBest2DTiling(lenN_, lenDesH_);
    nFactor_ = Ops::Base::CeilDiv(lenN_, np);

    int64_t hp = coreNum_ / np;
    hFactor_ = Ops::Base::CeilDiv(lenDesH_, hp);

    realCoreNum_ = Ops::Base::CeilDiv(lenN_, nFactor_) * Ops::Base::CeilDiv(lenDesH_, hFactor_);
    if (realCoreNum_ <= coreNum_ / EVEN_FACTOR) {
        wFactor_ = Ops::Base::CeilDiv(lenDesW_, coreNum_ / realCoreNum_);
        realCoreNum_ *= Ops::Base::CeilDiv(lenDesW_, wFactor_);
    }

    if (realCoreNum_ <= coreNum_ / EVEN_FACTOR) {
        cFactor_ = Ops::Base::CeilDiv(lenC_, coreNum_ / realCoreNum_);
        realCoreNum_ *= Ops::Base::CeilDiv(lenC_, cFactor_);
    }

    realCoreNum_ = Min(realCoreNum_, coreNum_);

    // UB切分
    int64_t wcLenAlign = Ops::Base::CeilAlign(wFactor_ * cFactor_, ONE_BLOCK_SIZE / dtypeSizeX_);
    int64_t vol4AxisC = (ubBlockNum_ / DB_BUFF_NUM) * ONE_BLOCK_SIZE / dtypeSizeX_;
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

void ResizeBilinearV2AscendCTilingImpl::DoTilingBroadCastNCHW()
{
    // HW合轴 N->C->HW依次分核
    int64_t lenHW = lenDesH_ * lenDesW_;
    if (lenN_ * lenC_ <= coreNum_) {
        int64_t tileNum = coreNum_ / (lenN_ * lenC_);
        nFactor_ = 1;
        cFactor_ = 1;
        hwFactor_ = Ops::Base::CeilDiv(lenHW, tileNum);
        realCoreNum_ = lenN_ * lenC_ * Ops::Base::CeilDiv(lenHW, hwFactor_);
    } else if (lenN_ <= coreNum_) {
        int64_t tileNum = coreNum_ / lenN_;
        nFactor_ = 1;
        cFactor_ = Ops::Base::CeilDiv(lenC_, tileNum);
        realCoreNum_ = lenN_ * Ops::Base::CeilDiv(lenC_, cFactor_);
    } else {
        nFactor_ = Ops::Base::CeilDiv(lenN_, coreNum_);
        realCoreNum_ = Ops::Base::CeilDiv(lenN_, nFactor_);
    }
    realCoreNum_ = Min(realCoreNum_, coreNum_);

    // UB内切分，依次判断各个单轴是否能放下
    int64_t blockSingleN = Ops::Base::CeilDiv(cFactor_ * dtypeSizeX_, ONE_BLOCK_SIZE) +
                           cFactor_ * Ops::Base::CeilDiv(hwFactor_ * dtypeSizeX_, ONE_BLOCK_SIZE);
    int64_t blockSingleC = 1 + Ops::Base::CeilDiv(hwFactor_ * dtypeSizeX_, ONE_BLOCK_SIZE);

    int64_t ubBlockVol = ubBlockNum_ / DB_BUFF_NUM;
    if (blockSingleC > ubBlockVol) {
        ubNFactor_ = 1;
        ubCFactor_ = 1;
        ubHWFactor_ = (ubBlockVol - 1) * ONE_BLOCK_SIZE / dtypeSizeX_;
    } else if (cFactor_ * blockSingleC > ubBlockVol) {
        ubNFactor_ = 1;
        ubCFactor_ = ubBlockVol / blockSingleC;
    } else if (nFactor_ * blockSingleN > ubBlockNum_) {
        ubNFactor_ = ubBlockVol / blockSingleN;
    }

    ubNFactor_ = Min(ubNFactor_, nFactor_);
    ubCFactor_ = Min(ubCFactor_, cFactor_);
    ubHWFactor_ = Min(ubHWFactor_, hwFactor_);
}

void ResizeBilinearV2AscendCTilingImpl::DoTilingBroadCastNHWC()
{
    // HW合轴 N->HW->C依次分核
    int64_t lenHW = lenDesH_ * lenDesW_;
    if (lenN_ * lenHW <= coreNum_) {
        int64_t tileNum = coreNum_ / (lenN_ * lenHW);
        nFactor_ = 1;
        hwFactor_ = 1;
        cFactor_ = Ops::Base::CeilDiv(lenC_, tileNum);
        realCoreNum_ = lenN_ * lenHW * Ops::Base::CeilDiv(lenC_, cFactor_);
    } else if (lenN_ <= coreNum_) {
        int64_t tileNum = coreNum_ / lenN_;
        nFactor_ = 1;
        hwFactor_ = Ops::Base::CeilDiv(lenHW, tileNum);
        realCoreNum_ = lenN_ * Ops::Base::CeilDiv(lenHW, hwFactor_);
    } else {
        nFactor_ = Ops::Base::CeilDiv(lenN_, coreNum_);
        realCoreNum_ = Ops::Base::CeilDiv(lenN_, nFactor_);
    }
    realCoreNum_ = Min(realCoreNum_, coreNum_);

    // UB内切分，依次判断各个单轴是否能放下
    int64_t blockSingleN = Ops::Base::CeilDiv(cFactor_ * dtypeSizeX_, ONE_BLOCK_SIZE) +
                           hwFactor_ * Ops::Base::CeilDiv(cFactor_ * dtypeSizeX_, ONE_BLOCK_SIZE);
    int64_t blockSingleHW = Ops::Base::CeilDiv(cFactor_ * dtypeSizeX_, ONE_BLOCK_SIZE) * DB_BUFF_NUM;

    int64_t ubBlockVol = ubBlockNum_ / DB_BUFF_NUM;
    if (blockSingleHW > ubBlockVol) {
        ubNFactor_ = 1;
        ubHWFactor_ = 1;
        ubCFactor_ = (ubBlockVol / DB_BUFF_NUM) * ONE_BLOCK_SIZE / dtypeSizeX_;
    } else if (hwFactor_ * blockSingleHW > ubBlockVol) {
        ubNFactor_ = 1;
        ubHWFactor_ = ubBlockVol / blockSingleHW;
    } else if (nFactor_ * blockSingleN > ubBlockNum_) {
        ubNFactor_ = ubBlockVol / blockSingleN;
    }

    ubNFactor_ = Min(ubNFactor_, nFactor_);
    ubHWFactor_ = Min(ubHWFactor_, hwFactor_);
    ubCFactor_ = Min(ubCFactor_, cFactor_);
}

void ResizeBilinearV2AscendCTilingImpl::DoTilingCParallel()
{
    int64_t totalLen = lenDesH_ * lenDesW_;

    if (totalLen * lenN_ <= coreNum_) {
        int64_t tileNum = coreNum_ / (totalLen * lenN_);
        hwFactor_ = 1;
        nFactor_ = 1;
        cFactor_ = Ops::Base::CeilDiv(lenC_, tileNum);
        realCoreNum_ = totalLen * lenN_ * Ops::Base::CeilDiv(lenC_, cFactor_);
    } else if (totalLen <= coreNum_) {
        int64_t tileNum = coreNum_ / totalLen;
        hwFactor_ = 1;
        nFactor_ = Ops::Base::CeilDiv(lenN_, tileNum);
        cFactor_ = lenC_;
        realCoreNum_ = totalLen * Ops::Base::CeilDiv(lenN_, nFactor_);
    } else {
        hwFactor_ = Ops::Base::CeilDiv(totalLen, coreNum_);
        nFactor_ = lenN_;
        cFactor_ = lenC_;
        realCoreNum_ = Ops::Base::CeilDiv(totalLen, hwFactor_);
    }

    realCoreNum_ = Min(realCoreNum_, coreNum_);

    int64_t vol4AxisC = ((ubBlockNum_ / DB_BUFF_NUM) * ONE_BLOCK_SIZE) /
                        (C_PARALLEL_X_TENSOR_NUM * dtypeSizeX_ + C_PARALLEL_Y_TENSOR_NUM * dtypeSizeY_);

    if (vol4AxisC < lenC_) {
        ubNFactor_ = 1;
        ubCFactor_ = vol4AxisC;
    } else {
        ubNFactor_ = vol4AxisC / lenC_;
        ubNFactor_ = (ubNFactor_ < nFactor_) ? ubNFactor_ : nFactor_;
        ubCFactor_ = lenC_;
    }
}

int64_t ResizeBilinearV2AscendCTilingImpl::FindBest2DTiling(int64_t lenM, int64_t lenN)
{
    int64_t bestM = 1;
    int64_t bestN = coreNum_ / bestM;

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

void ResizeBilinearV2AscendCTilingImpl::DoTilingSIMT()
{
    realCoreNum_ = (yShape_.GetShapeSize() < coreNum_) ? yShape_.GetShapeSize() : coreNum_;
    splitBlockFactor_ = Ops::Base::FloorDiv(yShape_.GetShapeSize(), realCoreNum_);
    splitBlockTailFactor_ = yShape_.GetShapeSize() - splitBlockFactor_ * realCoreNum_;
}

void ResizeBilinearV2AscendCTilingImpl::DoTilingSIMT_HW()
{
    int64_t DesHWSize = lenDesH_ * lenDesW_;
    realCoreNum_ = coreNum_;
    splitBlockFactor_ = Ops::Base::FloorDiv(DesHWSize, realCoreNum_);
    splitBlockTailFactor_ = DesHWSize - splitBlockFactor_ * realCoreNum_;
}

void ResizeBilinearV2AscendCTilingImpl::MatchTilingStrategyAndSetTilingKey()
{
    bool useIdx32 = yShape_.GetShapeSize() < UINT32_MAX && xShape_.GetShapeSize() < UINT32_MAX &&
                    lenSrcH_ <= INT32_MAX && lenSrcW_ <= INT32_MAX && lenDesH_ <= INT32_MAX && lenDesW_ <= INT32_MAX;
    if (IsMatchAllCopy()) {
        tilingKey_ = TILING_KEY_ALL_COPY;
    } else if (IsMatchPointCopy()) {
        tilingKey_ = TILING_KEY_POINT_COPY;
    } else if (IsMatchBroadCastNCHW()) {
        tilingKey_ = TILING_KEY_NCHW_BROADCAST;
    } else if (IsMatchBroadCastNHWC()) {
        tilingKey_ = TILING_KEY_NHWC_BROADCAST;
    } else if (IsMatchCParallel()) {
        tilingKey_ = TILING_KEY_C_PARALLEL;
    } else if (format_ == ge::FORMAT_NCHW) {
        int64_t hwSizeThreshold = useIdx32 ? coreNum_ * SIMT_DEFAULT_THREAD_NUM :
                                             coreNum_ * SIMT_DEFAULT_THREAD_NUM_IDX64;
        bool needHWSplit = xShape_.GetShapeSize() != 1 && (lenSrcW_ != lenDesW_ || lenSrcH_ != lenDesH_) &&
                           lenDesH_ * lenDesW_ >= hwSizeThreshold;
        if (useIdx32) {
            tilingKey_ = (needHWSplit) ? TILING_KEY_SIMT_HW : TILING_KEY_SIMT_NCHW;
        } else {
            tilingKey_ = (needHWSplit) ? TILING_KEY_SIMT_HW_IDX64 : TILING_KEY_SIMT_NCHW_IDX64;
        }
    } else if (format_ == ge::FORMAT_NHWC) {
        if (useIdx32) {
            tilingKey_ = TILING_KEY_SIMT_NHWC;
        } else {
            tilingKey_ = TILING_KEY_SIMT_NHWC_IDX64;
        }
    }
}

void ResizeBilinearV2AscendCTilingImpl::TilingStrategy()
{
    MatchTilingStrategyAndSetTilingKey();
    switch (tilingKey_) {
        case TILING_KEY_ALL_COPY: {
            DoTilingAllCopy();
            break;
        }
        case TILING_KEY_POINT_COPY: {
            DoTilingPointCopy();
            break;
        }
        case TILING_KEY_NCHW_BROADCAST: {
            DoTilingBroadCastNCHW();
            break;
        }
        case TILING_KEY_NHWC_BROADCAST: {
            DoTilingBroadCastNHWC();
            break;
        }
        case TILING_KEY_C_PARALLEL: {
            DoTilingCParallel();
            break;
        }
        case TILING_KEY_SIMT_NHWC:
        case TILING_KEY_SIMT_NHWC_IDX64:
        case TILING_KEY_SIMT_NCHW:
        case TILING_KEY_SIMT_NCHW_IDX64: {
            DoTilingSIMT();
            break;
        }
        case TILING_KEY_SIMT_HW:
        case TILING_KEY_SIMT_HW_IDX64: {
            DoTilingSIMT_HW();
            break;
        }
        default: {
            break;
        }
    }
}

void ResizeBilinearV2AscendCTilingImpl::FillTilingData()
{
    tilingData_.set_tilingKey(tilingKey_);
    tilingData_.set_realCoreNum(realCoreNum_);
    tilingData_.set_ubSize(ubSize_);
    tilingData_.set_alignCorners(alignCorners_);
    tilingData_.set_halfPixelCenters(halfPixelCenters_);
    tilingData_.set_lenN(lenN_);
    tilingData_.set_lenC(lenC_);
    tilingData_.set_lenSrcH(lenSrcH_);
    tilingData_.set_lenSrcW(lenSrcW_);
    tilingData_.set_lenDesH(lenDesH_);
    tilingData_.set_lenDesW(lenDesW_);
    tilingData_.set_nFactor(nFactor_);
    tilingData_.set_hFactor(hFactor_);
    tilingData_.set_wFactor(wFactor_);
    tilingData_.set_cFactor(cFactor_);
    tilingData_.set_hwFactor(hwFactor_);
    tilingData_.set_ubNFactor(ubNFactor_);
    tilingData_.set_ubHFactor(ubHFactor_);
    tilingData_.set_ubWFactor(ubWFactor_);
    tilingData_.set_ubCFactor(ubCFactor_);
    tilingData_.set_ubHWFactor(ubHWFactor_);
    tilingData_.set_splitBlockFactor(splitBlockFactor_);
    tilingData_.set_splitBlockTailFactor(splitBlockTailFactor_);
    tilingData_.set_scaleW(scaleW_);
    tilingData_.set_scaleH(scaleH_);

    tilingData_.SaveToBuffer(context_->GetRawTilingData()->GetData(), context_->GetRawTilingData()->GetCapacity());
    context_->GetRawTilingData()->SetDataSize(tilingData_.GetDataSize());
}

void ResizeBilinearV2AscendCTilingImpl::PrintTilingData()
{
    OP_LOGI(context_->GetNodeName(),
            "tilingData is tilingKey:%ld, realCoreNum:%ld, ubSize: %ld, alignCorners:%ld, halfPixelCenters:%ld,"
            "lenN:%ld, lenC:%ld, lenSrcH:%ld, lenSrcW:%ld, lenDesH:%ld, lenDesW:%ld, "
            "nFactor:%ld, hFactor:%ld, wFactor:%ld, cFactor:%ld, hwFactor:%ld, ubNFactor:%ld, ubHFactor:%ld, "
            "ubWFactor:%ld, ubCFactor:%ld, "
            "splitBlockFactor:%ld, splitBlockTailFactor: %ld, scaleW: %f, scaleH: %f",
            tilingData_.get_tilingKey(), tilingData_.get_realCoreNum(), tilingData_.get_ubSize(),
            tilingData_.get_alignCorners(), tilingData_.get_halfPixelCenters(), tilingData_.get_lenN(),
            tilingData_.get_lenC(), tilingData_.get_lenSrcH(), tilingData_.get_lenSrcW(), tilingData_.get_lenDesH(),
            tilingData_.get_lenDesW(), tilingData_.get_nFactor(), tilingData_.get_hFactor(), tilingData_.get_wFactor(),
            tilingData_.get_cFactor(), tilingData_.get_hwFactor(), tilingData_.get_ubNFactor(),
            tilingData_.get_ubHFactor(), tilingData_.get_ubWFactor(), tilingData_.get_ubCFactor(),
            tilingData_.get_splitBlockFactor(), tilingData_.get_splitBlockTailFactor(), tilingData_.get_scaleW(),
            tilingData_.get_scaleH());
}

ge::graphStatus ResizeBilinearV2AscendCTilingImpl::SetScales()
{
    auto attrs = context_->GetAttrs();
    OP_CHECK_NULL_WITH_CONTEXT(context_, attrs);

    auto scales = attrs->GetAttrPointer<gert::ContinuousVector>(ATTR_SCALES_IDX);

    if (scales != nullptr) {
        int64_t scales_num = scales->GetSize();
        const float* scales_data = reinterpret_cast<const float*>(scales->GetData());
        OP_CHECK_NULL_WITH_CONTEXT(context_, scales_data);
        OP_CHECK_IF(scales_num != SCALES_NUM,
                    OP_LOGE_FOR_INVALID_LISTSIZE(context_->GetNodeName(), "scales", std::to_string(scales_num).c_str(),
                                                 std::to_string(SCALES_NUM).c_str()),
                    return ge::GRAPH_FAILED);
        OP_LOGI(context_->GetNodeName(), "ResizeBilinearV2AscendCTilingImpl init: num[%ld]scales(%f %f)", scales_num,
                scales_data[0], scales_data[1]);
        scaleH_ = scales_data[IDX_DST_H];
        scaleW_ = scales_data[IDX_DST_W];
        if (scaleH_ > 0 || scaleW_ > 0) {
            scaleValid_ = true;
        }
    } else {
        OP_LOGI(context_->GetNodeName(), "ResizeBilinearV2AscendCTilingImpl init: There is no scales attr.");
    }

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBilinearV2AscendCTilingImpl::CheckDtypeAndFormat()
{
    auto inputXDesc = context_->GetInputDesc(INPUT_X_IDX);
    OP_CHECK_NULL_WITH_CONTEXT(context_, inputXDesc);
    auto outputYDesc = context_->GetOutputDesc(OUTPUT_Y_IDX);
    OP_CHECK_NULL_WITH_CONTEXT(context_, outputYDesc);
    dtypeX_ = inputXDesc->GetDataType();
    dtypeY_ = outputYDesc->GetDataType();
    dtypeSizeX_ = GetSizeByDataType(dtypeX_);
    dtypeSizeY_ = GetSizeByDataType(dtypeY_);
    if (dtypeSizeX_ <= 0 || dtypeSizeY_ <= 0) {
        std::string dtypeMsg = Ops::Base::ToString(dtypeX_) + " and " + Ops::Base::ToString(dtypeY_);
        OP_LOGE_FOR_INVALID_DTYPES_WITH_REASON(context_->GetNodeName(), "x and y", dtypeMsg.c_str(),
                                               "The dtype sizes of input x and output y must be greater than zero");
        return ge::GRAPH_FAILED;
    }

    format_ = static_cast<ge::Format>(ge::GetPrimaryFormat(inputXDesc->GetStorageFormat()));
    auto outFormat = static_cast<ge::Format>(ge::GetPrimaryFormat(outputYDesc->GetStorageFormat()));
    if (format_ != outFormat) {
        std::string formatMsg = Ops::Base::ToString(format_) + " and " + Ops::Base::ToString(outFormat);
        OP_LOGE_FOR_INVALID_FORMATS_WITH_REASON(context_->GetNodeName(), "x and y", formatMsg.c_str(),
                                                "The formats of input x and output y must be the same");
        return ge::GRAPH_FAILED;
    }
    OP_CHECK_IF(
        (format_ != ge::FORMAT_NCHW && format_ != ge::FORMAT_NHWC),
        OP_LOGE_FOR_INVALID_FORMAT(context_->GetNodeName(), "x", Ops::Base::ToString(format_).c_str(), "NCHW or NHWC"),
        return ge::GRAPH_FAILED);

    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBilinearV2AscendCTilingImpl::SetShape()
{
    // Get xshape, yshape
    auto xStorage = context_->GetInputShape(INPUT_X_IDX);
    OP_CHECK_NULL_WITH_CONTEXT(context_, xStorage);
    xShape_ = Ops::Cv::OpTiling::EnsureNotScalar(xStorage->GetStorageShape());
    auto yStorage = context_->GetOutputShape(OUTPUT_Y_IDX);
    OP_CHECK_NULL_WITH_CONTEXT(context_, yStorage);
    yShape_ = Ops::Cv::OpTiling::EnsureNotScalar(yStorage->GetStorageShape());
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBilinearV2AscendCTilingImpl::Init(const ResizeBilinearV2CompileInfo* compileInfo)
{
    OP_LOGD(context_->GetNodeName(), "Enter ResizeBilinearV2AscendCTilingImpl init.");
    coreNum_ = compileInfo->core_num;
    ubSize_ = compileInfo->ubSize;
    OP_CHECK_IF(coreNum_ <= 0 || ubSize_ <= 0, OP_LOGE(context_->GetNodeName(), "coreNum or ubSize is small than zero"),
                return ge::GRAPH_FAILED);
    ubBlockNum_ = Ops::Base::CeilDiv(ubSize_, ONE_BLOCK_SIZE) - RSV_BLOCK_NUM;
    OP_LOGI(context_->GetNodeName(), "coreNum_ is %ld, ubSize_ is %ld, ubBlockNum_ is %ld", coreNum_, ubSize_,
            ubBlockNum_);
    // Get attrs: alignCorners, halfPixelCenters
    auto attrs = context_->GetAttrs();
    OP_CHECK_NULL_WITH_CONTEXT(context_, attrs);
    const bool* alignCornersPtr = attrs->GetAttrPointer<bool>(ATTR_ALIGN_CORERS_IDX);
    OP_CHECK_NULL_WITH_CONTEXT(context_, alignCornersPtr);
    const bool* halfPixelCentersPtr = attrs->GetAttrPointer<bool>(ATTR_HALF_PIXEL_CENTERS_IDX);
    OP_CHECK_NULL_WITH_CONTEXT(context_, halfPixelCentersPtr);
    alignCorners_ = *alignCornersPtr ? 1 : 0;
    halfPixelCenters_ = *halfPixelCentersPtr ? 1 : 0;

    if (SetScales() != ge::GRAPH_SUCCESS) {
        return ge::GRAPH_FAILED;
    }

    if (CheckDtypeAndFormat() != ge::GRAPH_SUCCESS) {
        return ge::GRAPH_FAILED;
    }

    if (SetShape() != ge::GRAPH_SUCCESS) {
        return ge::GRAPH_FAILED;
    }

    // Check format and dims match or not.
    if (CheckFormatMatchDims() != ge::GRAPH_SUCCESS) {
        return ge::GRAPH_FAILED;
    }

    // Set N,C,H,W dim length
    SetDimsByFormat();

    OP_LOGD(context_->GetNodeName(), "Exit ResizeBilinearV2AscendCTilingImpl init.");
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus ResizeBilinearV2AscendCTilingImpl::DoTiling()
{
    OP_LOGD(context_->GetNodeName(), "Enter ResizeBilinearV2AscendCTilingImpl DoTiling.v1.1");

    TilingStrategy();
    FillTilingData();
    PrintTilingData();

    context_->SetBlockDim(realCoreNum_);
    context_->SetTilingKey(tilingKey_);

    size_t* workspaces = context_->GetWorkspaceSizes(1);
    OP_CHECK_NULL_WITH_CONTEXT(context_, workspaces);
    workspaces[0] = WORKSPACE_SIZE;
    OP_LOGD(context_->GetNodeName(), "Exit ResizeBilinearV2AscendCTilingImpl DoTiling.");
    return ge::GRAPH_SUCCESS;
}

ge::graphStatus Tiling4ResizeBilinearV2(gert::TilingContext* context)
{
    OP_LOGD(context->GetNodeName(), "Start Tiling4ResizeBilinearV2.");
    auto compileInfo = reinterpret_cast<const ResizeBilinearV2CompileInfo*>(context->GetCompileInfo());
    ResizeBilinearV2AscendCTilingImpl tilingImpl = ResizeBilinearV2AscendCTilingImpl(context);
    if (tilingImpl.Init(compileInfo) != ge::GRAPH_SUCCESS) {
        OP_LOGE(context->GetNodeName(), "Tiling4ResizeBilinearV2 init failed.");
        return ge::GRAPH_FAILED;
    }

    if (tilingImpl.DoTiling() != ge::GRAPH_SUCCESS) {
        OP_LOGE(context->GetNodeName(), "Tiling4ResizeBilinearV2 do tiling failed.");
        return ge::GRAPH_FAILED;
    }
    return ge::GRAPH_SUCCESS;
}

static ge::graphStatus TilingPrepare4ResizeBilinearV2(gert::TilingParseContext* context)
{
    OP_LOGD(context->GetNodeName(), "Start TilingPrepare4ResizeBilinearV2.");
    auto compileInfo = context->GetCompiledInfo<ResizeBilinearV2CompileInfo>();
    auto platformInfo = context->GetPlatformInfo();
    OP_CHECK_NULL_WITH_CONTEXT(context, platformInfo);
    auto ascendcPlatform = platform_ascendc::PlatformAscendC(platformInfo);
    compileInfo->core_num = ascendcPlatform.GetCoreNumAiv();
    OP_CHECK_IF((compileInfo->core_num <= 0), OP_LOGE(context->GetNodeName(), "core num invalid."),
                return ge::GRAPH_FAILED);
    uint64_t ubSize = 0;
    ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::UB, ubSize);
    compileInfo->ubSize = static_cast<int64_t>(ubSize);
    OP_CHECK_IF((compileInfo->ubSize <= 0), OP_LOGE(context->GetNodeName(), "ub size invalid."),
                return ge::GRAPH_FAILED);

    return ge::GRAPH_SUCCESS;
}

// register tiling interface of the ResizeBilinearV2 op.
IMPL_OP_OPTILING(ResizeBilinearV2)
    .Tiling(Tiling4ResizeBilinearV2)
    .TilingParse<ResizeBilinearV2CompileInfo>(TilingPrepare4ResizeBilinearV2);
} // namespace optiling
