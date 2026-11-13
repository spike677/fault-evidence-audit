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
 * \file iou3d.h
 * \brief Iou3D 主模板 kernel（TPL_MAIN，arch35 / DAV_3510）
 *
 * def 驱动 dtype：dtype 由 _def.cpp 的 DataType({ge::DT_FLOAT}) 声明，构建系统通过
 * -DDTYPE_BBOXES 等编译宏注入；bboxes/gtboxes/iou 均 float32，类内统一用 DTYPE_BBOXES。
 *
 * 逐对 (b,i,j) 3D 旋转框 IoU 完整路径：
 *   BEV 旋转顶点投影(向量 Sin/Cos) → 交集顶点收集(包含测试+边相交) →
 *   多边形面积(0/1/2 顶点置 0, 3 顶点直算三角形, >3 顶点质心分解 + 硬件 Sort32 极角排序 + 三角形叉积和) →
 *   Z 轴重叠 clamp 非负 → epsilon 除法 → 普通 DataCopyPad 写回（(b,i,j) 单点不相交写，无需原子加）。
 *
 * 编程模型：RegBase(arch35) kernel-shell + Scalar 混合。
 *   - 向量批算：AscendC::Sin / AscendC::Cos（逐 pair 的 theta，adv_api math）。
 *   - 硬件排序：>3 顶点走 AscendC::Sort32 + Extract（diamond-angle 极角键，替代标量选择排序）。
 *   - 标量几何：分支密集（corners_num∈{0..24}），逐对用 LocalTensor::GetValue 读标量控制。
 *   - 数值稳定三守卫：
 *       epsilon_guard_division   : iou = interVol / max(union, 1e-6)（对标 mmcv clamp，golden.py:377）
 *       clamp_z_overlap_nonneg   : real_d = max(min-max, 0)
 *       degenerate_polygon_guard : corners_num < 3 → area = 0
 *   - 候选点语义：CollectCorners 不去重，按 golden 顺序完整保留 16 组边交点、再收集 8 次包含点（最多 24 点）。
 *   - MMCV fan area: SortPolygonArea 以排序后首顶点为基准做有符号扇形累加，末尾一次 abs。
 *   - 红线 : 面积层严禁任何 NaN 守卫；NaN/inf 按 IEEE754 自然传播。
 *
 * 布局：bboxes[B,7,N] 索引(b,c,i)=b*7*N + c*N + i；gtboxes[B,7,K] 同理；iou[B,N,K] 索引(b,i,j)=b*N*K + i*K + j。
 * 每核负责 flatten (b,i,j) 的一段连续区间（不相交），每元素只被一个核写一次，输出连续段用普通 DataCopyPad 写回
 * （单点不相交写 → 无需原子加，也不依赖外部对输出 GM 零初始化）。
 */
#ifndef IOU3D_ARCH35_H
#define IOU3D_ARCH35_H

#include "kernel_operator.h"
#include "lib/math/sin.h"
#include "lib/math/cos.h"
#include "iou3d_tiling_data.h"

namespace NsIou3D {

using namespace AscendC;

constexpr uint32_t IOU3D_DOF = 7;     // 7-DoF 通道数
constexpr uint32_t IOU3D_CORNERS = 4; // 每框 BEV 顶点数
// 对齐 MMCV iou3d_cuda_kernel.cuh 的 Point cross_points[16]。
constexpr uint32_t IOU3D_MAX_INTER = 16;
constexpr float IOU3D_EPSILON = 1e-6f; // IoU 分母 clamp 下限（对标 mmcv golden.py:37 EPS_IOU=1e-6）
// 对齐 MMCV CUDA intersection 的退化分支阈值。
constexpr float IOU3D_EPS_KERNEL = 1e-8f;
// float32 最大有限值：仅用于区分有限输入与 NaN/Inf，不改变 NaN/Inf 传播语义。
constexpr float IOU3D_MAX_FINITE = 3.402823466e38f;
// 对标 mmcv：顶点包含测试绝对容差。反向旋转到框局部系后判 |rot|<half+MARGIN
//   （对标 mmcv golden.py:36/194-195 MARGIN=1e-2，严格 <）。
constexpr float IOU3D_MARGIN = 1e-2f;
// fp32 32B(one data block) = 8 元素。RegBase(arch35) 向量 adv_api Sin/Cos 要求 src/dst 32B 对齐
// （sin_3510_impl 用 Reg::StoreAlign<..,DIST_PACK_B32>），故所有参与向量计算的 UB 子段起址与长度按 8 对齐。
constexpr uint32_t IOU3D_ALIGN_ELEM = 8; // fp32 一个 datablock 的元素数（32B / 4B）
// Cos 精度修复只覆盖已确认存在默认角度归约缺口的窄角度域，并仅替换至少相差约 1 ULP 的结果。
// 其他角度完整保留默认 Cos；Sin 路径始终不变。
constexpr float IOU3D_COS_FIX_MIN_ABS_ANGLE = 2.8f;
constexpr float IOU3D_COS_FIX_MAX_ABS_ANGLE = 3.0f;
constexpr float IOU3D_COS_FIX_MIN_DELTA = 5.9e-8f;
// 硬件极角排序（Sort32）常量。
constexpr uint32_t IOU3D_SORT32_LEN = 32U; // Sort32 一趟固定处理 32 元素（最多 16 有效，其余 padding 沉底）
// 高精度 Cos：使用角度归约算法；默认 Cos 和 Sin 仍先按原路径计算。
constexpr AscendC::CosConfig IOU3D_HIGH_PRECISION_COS_CONFIG{AscendC::CosAlgo::RADIAN_REDUCTION};

constexpr float IOU3D_NEG_INF_KEY = -1.0e30f;    // padding 槽键值（沉底到排序末尾）
constexpr uint32_t IOU3D_IDX_MASK = 0x07FFFFFFu; // Sort32 index 位宽 27bit，回读时按位与还原原始下标

// 向上取整对齐到 IOU3D_ALIGN_ELEM 的倍数（32B 对齐）
__aicore__ inline uint32_t Iou3DCeilAlign(uint32_t n)
{
    return ((n + IOU3D_ALIGN_ELEM - 1U) / IOU3D_ALIGN_ELEM) * IOU3D_ALIGN_ELEM;
}

class Iou3D {
public:
    __aicore__ inline Iou3D(){};

    __aicore__ inline void Init(GM_ADDR bboxes, GM_ADDR gtboxes, GM_ADDR iou, const Iou3DTilingData* tilingData);
    __aicore__ inline void Process();

private:
    // 逐对计算一个 (b,i,j) 的 IoU（标量几何，theta 的 sin/cos 由 tile 向量批算后传入）
    __aicore__ inline float ComputePairIou(int64_t b, int64_t i, int64_t j, float sin1, float cos1, float sin2,
                                           float cos2);
    // BEV 旋转 4 顶点（rect: x,y,z,w,h,d；sinT/cosT 为该框 theta 的 sin/cos）
    __aicore__ inline void BoxCorners(float x, float y, float w, float h, float sinT, float cosT,
                                      float cx[IOU3D_CORNERS], float cy[IOU3D_CORNERS]);
    // 顶点包含测试（对标 mmcv 反向旋转法 golden.py:171-195）：把点旋转 -heading 到框局部系，
    //   判 |rot_x|<halfDx+MARGIN && |rot_y|<halfDy+MARGIN（MARGIN=1e-2 绝对，严格 <）。
    __aicore__ inline bool PointInRect(float px, float py, float cx, float cy, float halfDx, float halfDy, float sinT,
                                       float cosT);
    // 线段相交：逐分支对齐 MMCV check_rect_cross + 跨立实验 + 直线求交。
    __aicore__ inline bool SegIntersect(float a1x, float a1y, float a2x, float a2y, float b1x, float b1y, float b2x,
                                        float b2y, float& ox, float& oy);
    // 收集交集候选点（不去重，MMCV 固定 16 槽），返回候选数。
    // box1/box2 各传 (cx,cy,halfDx,halfDy,sinT,cosT) 供反向旋转包含测试。
    __aicore__ inline uint32_t CollectCorners(const float c1x[IOU3D_CORNERS], const float c1y[IOU3D_CORNERS],
                                              const float c2x[IOU3D_CORNERS], const float c2y[IOU3D_CORNERS],
                                              float box1cx, float box1cy, float box1hx, float box1hy, float box1sin,
                                              float box1cos, float box2cx, float box2cy, float box2hx, float box2hy,
                                              float box2sin, float box2cos, float px[IOU3D_MAX_INTER],
                                              float py[IOU3D_MAX_INTER]);
    // 多边形面积（0/1/2→0；>=3 均对齐 MMCV：质心极角排序 + 首顶点扇形叉积和）
    __aicore__ inline float PolygonArea(float px[IOU3D_MAX_INTER], float py[IOU3D_MAX_INTER], uint32_t m);
    // >=3 顶点：硬件 Sort32 极角排序（diamond-angle 单调等价 atan2）+ MMCV 首顶点扇形面积。
    __aicore__ inline float SortPolygonArea(float px[IOU3D_MAX_INTER], float py[IOU3D_MAX_INTER], uint32_t m);
    // 读取一个框的 7-DoF 标量（layout [B,DOF,D]）
    __aicore__ inline void LoadBox(const GlobalTensor<DTYPE_BBOXES>& gm, int64_t b, int64_t idx, int64_t dimSize,
                                   float box[IOU3D_DOF]);
    __aicore__ inline float ScalarAbs(float v) { return v < 0.0f ? -v : v; }
    __aicore__ inline float ScalarMax(float a, float b) { return a > b ? a : b; }
    __aicore__ inline float ScalarMin(float a, float b) { return a < b ? a : b; }

private:
    TPipe pipe;
    // theta 向量批算 sin/cos 缓冲（bbox 与 gtbox 各一路）
    TBuf<TPosition::VECCALC> angleBuf; // 存 bbox_theta | gtbox_theta | sin/cos 中间（各段 32B 对齐）
    TBuf<TPosition::VECCALC> tmpBuf;   // Sin/Cos adv_api 显式 sharedTmpBuffer（避免 PopStackBuffer 依赖）
    TBuf<TPosition::VECOUT> outBuf;    // iou tile 输出缓冲（32B 对齐）
    // 硬件极角排序（Sort32）缓冲（>3 顶点分支复用，Init 一次分配）：
    TBuf<TPosition::VECCALC> sortKeyBuf;    // 32 极角键（float）
    TBuf<TPosition::VECCALC> sortIdxBuf;    // 32 原始下标（uint32）
    TBuf<TPosition::VECCALC> sortedBuf;     // Sort32 输出 proposal 交织(value,index)：32*2 float
    TBuf<TPosition::VECCALC> sortOutValBuf; // Extract 输出排序 value（float）
    TBuf<TPosition::VECCALC> sortOutIdxBuf; // Extract 输出原始 index（uint32）

    GlobalTensor<DTYPE_BBOXES> bboxesGM;
    GlobalTensor<DTYPE_BBOXES> gtboxesGM;
    GlobalTensor<DTYPE_BBOXES> iouGM;

    uint32_t batch_ = 0;
    uint32_t numN_ = 0;
    uint32_t numK_ = 0;
    uint32_t tileLen_ = 0;
    uint32_t alignedTl_ = 0;  // 32B 对齐后的单批粒度（各 UB 子段步长）
    uint32_t isEmpty_ = 0;    // 空 Tensor 标志（从 tilingData 读取，用于运行时判断）
    uint32_t cosTmpSize_ = 0; // 高精度 Cos 显式 sharedTmpBuffer 字节数
    int64_t pairStart_ = 0;   // 本核 flatten (b,i,j) 起始
    int64_t pairCount_ = 0;   // 本核 flatten 对数
    int64_t totalPairs_ = 0;
};

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

__aicore__ inline void Iou3D::Init(GM_ADDR bboxes, GM_ADDR gtboxes, GM_ADDR iou, const Iou3DTilingData* tilingData)
{
    batch_ = tilingData->batch;
    numN_ = tilingData->numBboxes;
    numK_ = tilingData->numGtboxes;
    tileLen_ = tilingData->tileLen;
    isEmpty_ = tilingData->isEmpty; // 保存空 Tensor 标志
    cosTmpSize_ = tilingData->cosTmpSize;

    totalPairs_ = static_cast<int64_t>(batch_) * numN_ * numK_;
    const int64_t pairsPerCore = tilingData->pairsPerCore;
    const int64_t blockIdx = GetBlockIdx();
    pairStart_ = pairsPerCore * blockIdx;
    int64_t remain = totalPairs_ - pairStart_;
    pairCount_ = (remain > pairsPerCore) ? pairsPerCore : (remain > 0 ? remain : 0);

    bboxesGM.SetGlobalBuffer((__gm__ DTYPE_BBOXES*)bboxes);
    gtboxesGM.SetGlobalBuffer((__gm__ DTYPE_BBOXES*)gtboxes);
    iouGM.SetGlobalBuffer((__gm__ DTYPE_BBOXES*)iou);

    // 空 Tensor 运行时短路：无 (b,i,j) 对，不分配任何 UB（Process 直接短路返回）
    if (isEmpty_ != 0U) {
        return;
    }

    // theta / sin / cos 中间：6 段，每段步长 = 32B 对齐后的 alignedTl（保证每个子段起址 32B 对齐）
    //   [0]=theta1 [1]=theta2 [2]=sin1 [3]=cos1 [4]=sin2 [5]=cos2
    // RegBase(arch35) Sin/Cos 要求 src/dst 32B 对齐；1 元素(4B) 非对齐子张量会触发 AIV 向量核异常(err 340)。
    uint32_t tl = (tileLen_ == 0U) ? 1U : tileLen_;
    alignedTl_ = Iou3DCeilAlign(tl);
    pipe.InitBuffer(angleBuf, 6U * alignedTl_ * sizeof(float));
    // RADIAN_REDUCTION Cos 消耗 Host 按 tiling API 计算的显式 sharedTmpBuffer。
    pipe.InitBuffer(tmpBuf, cosTmpSize_);
    pipe.InitBuffer(outBuf, alignedTl_ * sizeof(float));

    // 硬件极角排序（Sort32）缓冲：一次分配、跨对复用（>3 顶点分支）。
    //   proposal 交织格式 (value,index)，故 sortedBuf 需 32*2 个 float。固定 32 元素布局。
    pipe.InitBuffer(sortKeyBuf, IOU3D_SORT32_LEN * sizeof(float));
    pipe.InitBuffer(sortIdxBuf, IOU3D_SORT32_LEN * sizeof(uint32_t));
    pipe.InitBuffer(sortedBuf, IOU3D_SORT32_LEN * 2U * sizeof(float));
    pipe.InitBuffer(sortOutValBuf, IOU3D_SORT32_LEN * sizeof(float));
    pipe.InitBuffer(sortOutIdxBuf, IOU3D_SORT32_LEN * sizeof(uint32_t));
}

// ---------------------------------------------------------------------------
// LoadBox：读取一个框的 7-DoF（layout [B, DOF, dimSize]，通道 stride = dimSize）
// ---------------------------------------------------------------------------

__aicore__ inline void Iou3D::LoadBox(const GlobalTensor<DTYPE_BBOXES>& gm, int64_t b, int64_t idx, int64_t dimSize,
                                      float box[IOU3D_DOF])
{
    int64_t base = b * static_cast<int64_t>(IOU3D_DOF) * dimSize + idx;
    for (uint32_t c = 0; c < IOU3D_DOF; ++c) {
        box[c] = static_cast<float>(gm.GetValue(base + static_cast<int64_t>(c) * dimSize));
    }
}

// ---------------------------------------------------------------------------
// BoxCorners（严格对齐 MMCV：左下、右下、右上、左上，先轴对齐后逐点旋转）
// ---------------------------------------------------------------------------

__aicore__ inline void Iou3D::BoxCorners(float x, float y, float w, float h, float sinT, float cosT,
                                         float cx[IOU3D_CORNERS], float cy[IOU3D_CORNERS])
{
    float halfW = w / 2.0f;
    float halfH = h / 2.0f;
    float x1 = x - halfW;
    float y1 = y - halfH;
    float x2 = x + halfW;
    float y2 = y + halfH;

    cx[0] = x1;
    cy[0] = y1;
    cx[1] = x2;
    cy[1] = y1;
    cx[2] = x2;
    cy[2] = y2;
    cx[3] = x1;
    cy[3] = y2;

    for (uint32_t k = 0; k < IOU3D_CORNERS; ++k) {
        float dx = cx[k] - x;
        float dy = cy[k] - y;
        float newX = dx * cosT - dy * sinT + x;
        float newY = dx * sinT + dy * cosT + y;
        cx[k] = newX;
        cy[k] = newY;
    }
}

// ---------------------------------------------------------------------------
// PointInRect（对标 mmcv 反向旋转法 golden.py:171-195 check_in_box2d）
//   把待测点 P 旋转 -heading 到框局部坐标系，检查是否在轴对齐矩形内（含 MARGIN=1e-2 绝对容差）。
//   golden.py: angle_cos=cos(-h)=cosT, angle_sin=sin(-h)=-sinT
//     rot_x = dpx*angle_cos + dpy*(-angle_sin) = dpx*cosT + dpy*sinT
//     rot_y = dpx*angle_sin + dpy*angle_cos    = -dpx*sinT + dpy*cosT
//     return |rot_x| < dx/2 + MARGIN && |rot_y| < dy/2 + MARGIN   （严格 <）
//   传入 sinT=sin(heading)、cosT=cos(heading)、halfDx=dx/2、halfDy=dy/2。
// ---------------------------------------------------------------------------

__aicore__ inline bool Iou3D::PointInRect(float px, float py, float cx, float cy, float halfDx, float halfDy,
                                          float sinT, float cosT)
{
    float dpx = px - cx;
    float dpy = py - cy;
    float rotX = dpx * cosT + dpy * sinT;
    float rotY = -dpx * sinT + dpy * cosT;
    return (ScalarAbs(rotX) < halfDx + IOU3D_MARGIN) && (ScalarAbs(rotY) < halfDy + IOU3D_MARGIN);
}

// ---------------------------------------------------------------------------
// SegIntersect（逐分支对齐 MMCV intersection）
//   p0=(a1x,a1y), p1=(a2x,a2y), q0=(b1x,b1y), q1=(b2x,b2y)。
//   ① check_rect_cross AABB 快速排斥；
//   ② s1*s2>0 && s3*s4>0 严格跨立；
//   ③ |s5-s1|>1e-8 用叉积公式，否则使用一般式直线方程。
// ---------------------------------------------------------------------------

__aicore__ inline bool Iou3D::SegIntersect(float a1x, float a1y, float a2x, float a2y, float b1x, float b1y, float b2x,
                                           float b2y, float& ox, float& oy)
{
    if (!(ScalarMin(a1x, a2x) <= ScalarMax(b1x, b2x) && ScalarMin(b1x, b2x) <= ScalarMax(a1x, a2x) &&
          ScalarMin(a1y, a2y) <= ScalarMax(b1y, b2y) && ScalarMin(b1y, b2y) <= ScalarMax(a1y, a2y))) {
        return false;
    }

    float s1 = (b1x - a1x) * (a2y - a1y) - (a2x - a1x) * (b1y - a1y);
    float s2 = (a2x - a1x) * (b2y - a1y) - (b2x - a1x) * (a2y - a1y);
    float s3 = (a1x - b1x) * (b2y - b1y) - (b2x - b1x) * (a1y - b1y);
    float s4 = (b2x - b1x) * (a2y - b1y) - (a2x - b1x) * (b2y - b1y);

    if (!(s1 * s2 > 0.0f && s3 * s4 > 0.0f)) {
        return false;
    }

    float s5 = (b2x - a1x) * (a2y - a1y) - (a2x - a1x) * (b2y - a1y);
    if (ScalarAbs(s5 - s1) > IOU3D_EPS_KERNEL) {
        ox = (s5 * b1x - s1 * b2x) / (s5 - s1);
        oy = (s5 * b1y - s1 * b2y) / (s5 - s1);
    } else {
        float a0 = a1y - a2y;
        float b0 = a2x - a1x;
        float c0 = a1x * a2y - a2x * a1y;
        float a1 = b1y - b2y;
        float b1 = b2x - b1x;
        float c1 = b1x * b2y - b2x * b1y;
        float d = a0 * b1 - a1 * b0;

        ox = (b0 * c1 - b1 * c0) / d;
        oy = (a1 * c0 - a0 * c1) / d;
    }
    return true;
}

// ---------------------------------------------------------------------------
// CollectCorners（16 组边相交 + 8 次顶点包含，不去重；追加顺序对齐 golden）
// ---------------------------------------------------------------------------

__aicore__ inline uint32_t Iou3D::CollectCorners(const float c1x[IOU3D_CORNERS], const float c1y[IOU3D_CORNERS],
                                                 const float c2x[IOU3D_CORNERS], const float c2y[IOU3D_CORNERS],
                                                 float box1cx, float box1cy, float box1hx, float box1hy, float box1sin,
                                                 float box1cos, float box2cx, float box2cy, float box2hx, float box2hy,
                                                 float box2sin, float box2cos, float px[IOU3D_MAX_INTER],
                                                 float py[IOU3D_MAX_INTER])
{
    uint32_t rawCnt = 0;

    // Golden 先追加 4x4 边交点，再追加包含点；不去重时保持该顺序可对齐质心累加与排序 tie。
    for (uint32_t i = 0; i < IOU3D_CORNERS; ++i) {
        float a1x = c1x[i], a1y = c1y[i];
        float a2x = c1x[(i + 1) % IOU3D_CORNERS], a2y = c1y[(i + 1) % IOU3D_CORNERS];
        for (uint32_t j = 0; j < IOU3D_CORNERS; ++j) {
            float b1x = c2x[j], b1y = c2y[j];
            float b2x = c2x[(j + 1) % IOU3D_CORNERS], b2y = c2y[(j + 1) % IOU3D_CORNERS];
            float ox, oy;
            if (SegIntersect(a1x, a1y, a2x, a2y, b1x, b1y, b2x, b2y, ox, oy)) {
                px[rawCnt] = ox;
                py[rawCnt] = oy;
                ++rawCnt;
            }
        }
    }

    // 每个 k 先收框2顶点 ∈ 框1，再收框1顶点 ∈ 框2，对齐 golden.py::_box_overlap。
    for (uint32_t k = 0; k < IOU3D_CORNERS; ++k) {
        if (PointInRect(c2x[k], c2y[k], box1cx, box1cy, box1hx, box1hy, box1sin, box1cos)) {
            px[rawCnt] = c2x[k];
            py[rawCnt] = c2y[k];
            ++rawCnt;
        }
        if (PointInRect(c1x[k], c1y[k], box2cx, box2cy, box2hx, box2hy, box2sin, box2cos)) {
            px[rawCnt] = c1x[k];
            py[rawCnt] = c1y[k];
            ++rawCnt;
        }
    }
    return rawCnt;
}

// ---------------------------------------------------------------------------
// PolygonArea：0/1/2 顶点 → 0；>=3 均进入 MMCV 的质心排序 + 首顶点扇形面积路径。
// ---------------------------------------------------------------------------

__aicore__ inline float Iou3D::PolygonArea(float px[IOU3D_MAX_INTER], float py[IOU3D_MAX_INTER], uint32_t m)
{
    if (m < 3)
        return 0.0f; // degenerate_polygon_guard
    if (m > IOU3D_MAX_INTER)
        m = IOU3D_MAX_INTER;
    return SortPolygonArea(px, py, m);
}

// ---------------------------------------------------------------------------
// SortPolygonArea：>=3 顶点，硬件 Sort32 极角排序（diamond-angle 键）+ MMCV 首顶点扇形面积。
//   1. 质心 (xc,yc)；相对质心坐标 (xr,yr)。
//   2. diamond-angle 键与 CUDA atan2(yr,xr) 的 [-pi,pi] 分支切点一致：
//      xr>=0 时 key=t；xr<0,yr>=0 时 key=2-t；xr<0,yr<0 时 key=-2-t，
//      其中 t=yr/(|xr|+|yr|)。Sort32 为降序，故送 -key 得 angle 升序（逆时针）；
//      padding 槽(idx>=m) 键置 -INF 沉底。
//   3. Sort32 + Extract 得排序后原始下标序 order[0..m-1]（逆时针环序）。
//   4. 面积：以 order[0] 为基准，按 MMCV 顺序累加相邻顶点有符号叉积，末尾一次 abs / 2。
//   排序键与 atan2 单调同序；面积累加的 float32 运算顺序与 MMCV box_overlap 对齐。
// ---------------------------------------------------------------------------

__aicore__ inline float Iou3D::SortPolygonArea(float px[IOU3D_MAX_INTER], float py[IOU3D_MAX_INTER], uint32_t m)
{
    LocalTensor<float> keyT = sortKeyBuf.Get<float>();
    LocalTensor<uint32_t> idxT = sortIdxBuf.Get<uint32_t>();
    LocalTensor<float> sortedT = sortedBuf.Get<float>();
    LocalTensor<float> outValT = sortOutValBuf.Get<float>();
    LocalTensor<uint32_t> outIdxT = sortOutIdxBuf.Get<uint32_t>();

    // 质心（float32 全程，与 golden 一致）
    float xc = 0.0f, yc = 0.0f;
    for (uint32_t k = 0; k < m; ++k) {
        xc += px[k];
        yc += py[k];
    }
    float invm = 1.0f / static_cast<float>(m);
    xc *= invm;
    yc *= invm;

    // diamond-angle 键 + 原始下标（padding 沉底）。32 槽全部填写，规避 Sort32 读到脏值。
    for (uint32_t i = 0; i < IOU3D_SORT32_LEN; ++i) {
        idxT.SetValue(i, i);
        float k;
        if (i < m) {
            float xr = px[i] - xc;
            float yr = py[i] - yc;
            float s = ScalarAbs(xr) + ScalarAbs(yr);
            float t = (s < 1.0e-20f) ? 0.0f : (yr / s);
            float keyRaw;
            if (xr >= 0.0f) {
                keyRaw = t;
            } else if (yr >= 0.0f) {
                keyRaw = 2.0f - t;
            } else {
                // 对齐 atan2 的负半轴分支：第三象限必须排在 [-pi,-pi/2)，不能循环移到 +pi 之后。
                keyRaw = -2.0f - t;
            }
            k = -keyRaw; // Sort32 降序 == angle 升序（逆时针）
        } else {
            k = IOU3D_NEG_INF_KEY; // padding 槽沉底
        }
        keyT.SetValue(i, k);
    }
    // SetValue(标量写 UB) → Sort32(向量读 UB) 之间同步
    PipeBarrier<PIPE_ALL>();
    Sort32<float>(sortedT, keyT, idxT, 1);
    PipeBarrier<PIPE_ALL>();
    Extract(outValT, outIdxT, sortedT, 1);
    // Extract(向量写 UB) → GetValue(标量读 UB) 之间同步
    PipeBarrier<PIPE_ALL>();

    // 取前 m 个排序后原始下标（逆时针环序），越界守卫
    uint32_t order[IOU3D_MAX_INTER];
    for (uint32_t i = 0; i < m; ++i) {
        uint32_t rawIdx = outIdxT.GetValue(i) & IOU3D_IDX_MASK;
        if (rawIdx >= m)
            rawIdx = 0U; // 守卫：非法下标回退（不应发生，padding 已沉底）
        order[i] = rawIdx;
    }

    // 面积严格对齐 MMCV box_overlap：以排序后第一个顶点为基准，依次累加
    // cross(points[k] - points[0], points[k + 1] - points[0])，末尾一次 abs / 2。
    // 不以质心为基准，避免数学等价但 float32 运算顺序不同而产生 1 ULP 偏差。
    //   ⚠️ 严禁任何面积层 NaN 守卫；NaN/inf 必须按 IEEE754 自然传播到输出。
    uint32_t base = order[0];
    float signedTwice = 0.0f;
    for (uint32_t k = 0; k + 1U < m; ++k) {
        uint32_t a = order[k];
        uint32_t bnext = order[k + 1U];
        float ax = px[a] - px[base];
        float ay = py[a] - py[base];
        float bx = px[bnext] - px[base];
        float by = py[bnext] - py[base];
        signedTwice += ax * by - ay * bx;
    }
    return ScalarAbs(signedTwice) * 0.5f;
}

// ---------------------------------------------------------------------------
// ComputePairIou：单框对 3D IoU（对齐 golden Iou3dPair）
// ---------------------------------------------------------------------------

__aicore__ inline float Iou3D::ComputePairIou(int64_t b, int64_t i, int64_t j, float sin1, float cos1, float sin2,
                                              float cos2)
{
    float rect1[IOU3D_DOF];
    float rect2[IOU3D_DOF];
    LoadBox(bboxesGM, b, i, static_cast<int64_t>(numN_), rect1);  // [B,7,N]
    LoadBox(gtboxesGM, b, j, static_cast<int64_t>(numK_), rect2); // [B,7,K]

    float v1 = rect1[3] * rect1[4] * rect1[5]; // w*h*d
    float v2 = rect2[3] * rect2[4] * rect2[5];
    // D10 对标 mmcv：移除 v<=0 负体积短路（golden.py 无 v<=0 特判）。正尺寸零体积框自然得 iou=0
    //   （interVol=0；D2 分母 clamp≥1e-6 保证不除零/nan）。

    float c1x[IOU3D_CORNERS], c1y[IOU3D_CORNERS], c2x[IOU3D_CORNERS], c2y[IOU3D_CORNERS];
    BoxCorners(rect1[0], rect1[1], rect1[3], rect1[4], sin1, cos1, c1x, c1y);
    BoxCorners(rect2[0], rect2[1], rect2[3], rect2[4], sin2, cos2, c2x, c2y);

    // Z 轴边界 + clamp 非负（clamp_z_overlap_nonneg）
    float z1Min = rect1[2] - 0.5f * rect1[5];
    float z1Max = rect1[2] + 0.5f * rect1[5];
    float z2Min = rect2[2] - 0.5f * rect2[5];
    float z2Max = rect2[2] + 0.5f * rect2[5];
    float realD = ScalarMax(ScalarMin(z1Max, z2Max) - ScalarMax(z1Min, z2Min), 0.0f);

    // 对有限输入，Z 轴无交集时 3D 交体积必为 0，与 BEV 形状无关。必须在
    // PolygonArea 前短路，否则超大但有限的坐标/尺寸可能先在 fp32 BEV 几何中
    // 溢出为 NaN/Inf，随后形成 NaN * 0，导致本应为 0 的 IoU 变成 NaN。
    // 仅有限输入允许短路；包含 NaN/Inf 的输入继续走原路径，保持既定传播语义。
    if (realD == 0.0f) {
        bool allFinite = true;
        for (uint32_t c = 0; c < IOU3D_DOF; ++c) {
            allFinite = allFinite && (rect1[c] == rect1[c]) && (rect2[c] == rect2[c]) &&
                        (ScalarAbs(rect1[c]) <= IOU3D_MAX_FINITE) && (ScalarAbs(rect2[c]) <= IOU3D_MAX_FINITE);
        }
        if (allFinite) {
            return 0.0f;
        }
    }

    float px[IOU3D_MAX_INTER], py[IOU3D_MAX_INTER];
    // 反向旋转包含测试需框中心/半尺寸/sin/cos：halfDx=0.5*w, halfDy=0.5*h。
    uint32_t m = CollectCorners(c1x, c1y, c2x, c2y, rect1[0], rect1[1], 0.5f * rect1[3], 0.5f * rect1[4], sin1, cos1,
                                rect2[0], rect2[1], 0.5f * rect2[3], 0.5f * rect2[4], sin2, cos2, px, py);
    float area = PolygonArea(px, py, m);

    float interVol = area * realD;
    float unionVol = v1 + v2 - interVol;
    // D2 对标 mmcv：分母 clamp（max(union, 1e-6)），对标 golden.py:377 clamp(min=1e-6)。
    float iou = interVol / ScalarMax(unionVol, IOU3D_EPSILON);
    return iou;
}

// ---------------------------------------------------------------------------
// Process：逐 tile 向量批算 theta 的 sin/cos，逐对标量几何，普通 DataCopyPad 写回（单点不相交写）
// ---------------------------------------------------------------------------

__aicore__ inline void Iou3D::Process()
{
    if (isEmpty_ != 0U) {
        return; // 空 Tensor：无输出（TPL_EMPTY 短路）
    }
    if (pairCount_ <= 0)
        return;

    const uint32_t atl = alignedTl_;                  // 32B 对齐步长，保证每个子段起址 32B 对齐
    LocalTensor<float> angle = angleBuf.Get<float>(); // [6*atl]
    LocalTensor<float> theta1 = angle[0];
    LocalTensor<float> theta2 = angle[atl];
    LocalTensor<float> sin1Buf = angle[2U * atl];
    LocalTensor<float> cos1Buf = angle[3U * atl];
    LocalTensor<float> sin2Buf = angle[4U * atl];
    LocalTensor<float> cos2Buf = angle[5U * atl];
    LocalTensor<float> outTile = outBuf.Get<float>();
    LocalTensor<uint8_t> sinTmp = tmpBuf.Get<uint8_t>(); // 默认与高精度 Cos 共用显式临时空间

    const int64_t nk = static_cast<int64_t>(numN_) * static_cast<int64_t>(numK_);

    const uint32_t tl = (tileLen_ == 0U) ? 1U : tileLen_; // 逻辑批大小（未对齐）
    int64_t processed = 0;
    while (processed < pairCount_) {
        int64_t cur = pairCount_ - processed;
        if (cur > static_cast<int64_t>(tl))
            cur = static_cast<int64_t>(tl);
        uint32_t curNum = static_cast<uint32_t>(cur);

        // 对齐后的向量计算长度（32B 倍数）。tail 元素(curNum..alignedCnt) 为 padding，
        // 预置为 0，使 Sin/Cos 在 padding 上产生合法值（sin0=0,cos0=1，无 NaN/Inf），结果不被读取。
        uint32_t alignedCnt = Iou3DCeilAlign(curNum);
        if (alignedCnt > atl)
            alignedCnt = atl; // 不超过子段容量

        // 1) 收集本 tile 每对的两 theta（bbox_i.theta 通道=6，gtbox_j.theta 通道=6），
        //    并把对齐 padding 段清零。
        for (uint32_t t = 0; t < alignedCnt; ++t) {
            if (t >= curNum) {
                theta1.SetValue(t, 0.0f);
                theta2.SetValue(t, 0.0f);
                continue;
            }
            int64_t flat = pairStart_ + processed + static_cast<int64_t>(t);
            int64_t b = flat / nk;
            int64_t rem = flat % nk;
            int64_t ii = rem / static_cast<int64_t>(numK_);
            int64_t jj = rem % static_cast<int64_t>(numK_);
            float th1 = static_cast<float>(
                bboxesGM.GetValue(b * static_cast<int64_t>(IOU3D_DOF) * numN_ + 6 * static_cast<int64_t>(numN_) + ii));
            float th2 = static_cast<float>(
                gtboxesGM.GetValue(b * static_cast<int64_t>(IOU3D_DOF) * numK_ + 6 * static_cast<int64_t>(numK_) + jj));
            theta1.SetValue(t, th1);
            theta2.SetValue(t, th2);
        }
        // SetValue(标量写 UB) → Sin/Cos(向量读 UB) 之间插同步，确保标量写完成后向量再读。
        PipeBarrier<PIPE_ALL>();

        // 2) 向量批算 sin/cos（32B 对齐子段 + 对齐计算长度 + 显式 sharedTmpBuffer）。
        //    src/dst 起址均 32B 对齐，规避 RegBase Sin/Cos 的对齐约束（AIV err 340）。
        Sin(sin1Buf, theta1, sinTmp, alignedCnt);
        Cos(cos1Buf, theta1, sinTmp, alignedCnt);
        Sin(sin2Buf, theta2, sinTmp, alignedCnt);
        Cos(cos2Buf, theta2, sinTmp, alignedCnt);
        // Sin/Cos(向量写 UB) → GetValue(标量读 UB) 之间插同步，确保向量结果对标量可见。
        PipeBarrier<PIPE_ALL>();

        // 仅修复 Cos：用 RADIAN_REDUCTION API 生成候选值到 outTile，
        // Sin 缓冲始终保留 AscendC Sin 的默认结果。
        Cos<float, false, IOU3D_HIGH_PRECISION_COS_CONFIG>(outTile, theta1, sinTmp, alignedCnt);
        PipeBarrier<PIPE_ALL>();
        for (uint32_t t = 0; t < curNum; ++t) {
            float th1 = theta1.GetValue(t);
            float absTh1 = ScalarAbs(th1);
            if (absTh1 >= IOU3D_COS_FIX_MIN_ABS_ANGLE && absTh1 <= IOU3D_COS_FIX_MAX_ABS_ANGLE) {
                float nativeCos1 = cos1Buf.GetValue(t);
                float highPrecisionCos1 = outTile.GetValue(t);
                if (ScalarAbs(highPrecisionCos1 - nativeCos1) > IOU3D_COS_FIX_MIN_DELTA) {
                    cos1Buf.SetValue(t, highPrecisionCos1);
                }
            }
        }
        PipeBarrier<PIPE_ALL>();

        Cos<float, false, IOU3D_HIGH_PRECISION_COS_CONFIG>(outTile, theta2, sinTmp, alignedCnt);
        PipeBarrier<PIPE_ALL>();
        for (uint32_t t = 0; t < curNum; ++t) {
            float th2 = theta2.GetValue(t);
            float absTh2 = ScalarAbs(th2);
            if (absTh2 >= IOU3D_COS_FIX_MIN_ABS_ANGLE && absTh2 <= IOU3D_COS_FIX_MAX_ABS_ANGLE) {
                float nativeCos2 = cos2Buf.GetValue(t);
                float highPrecisionCos2 = outTile.GetValue(t);
                if (ScalarAbs(highPrecisionCos2 - nativeCos2) > IOU3D_COS_FIX_MIN_DELTA) {
                    cos2Buf.SetValue(t, highPrecisionCos2);
                }
            }
        }

        // 3) 逐对标量几何计算 IoU
        for (uint32_t t = 0; t < curNum; ++t) {
            int64_t flat = pairStart_ + processed + static_cast<int64_t>(t);
            int64_t b = flat / nk;
            int64_t rem = flat % nk;
            int64_t ii = rem / static_cast<int64_t>(numK_);
            int64_t jj = rem % static_cast<int64_t>(numK_);
            float s1 = sin1Buf.GetValue(t);
            float c1 = cos1Buf.GetValue(t);
            float s2 = sin2Buf.GetValue(t);
            float c2 = cos2Buf.GetValue(t);
            float iou = ComputePairIou(b, ii, jj, s1, c1, s2, c2);
            outTile.SetValue(t, iou);
        }

        // outTile 标量写 → DataCopyPad(MTE3 读 UB) 之间插同步，确保写完成后再搬出。
        PipeBarrier<PIPE_ALL>();

        // 4) 写回：普通 DataCopyPad（本核连续段，(b,i,j) 单点写，无跨核冲突 → 无需原子加）。
        //    正确性论证（核实自 tiling 切分）：Host 侧 pairsPerCore=CeilDiv(total,coreNum)、
        //    usedCoreNum=CeilDiv(total,pairsPerCore)、SetBlockDim(usedCoreNum)；kernel 侧核 k 负责
        //    flatten 区间 [k*pairsPerCore, k*pairsPerCore + pairCount_)（pairCount_=min(pairsPerCore,remain)），
        //    相邻核区间连续且不相交，每个 (b,i,j) 输出元素恰被一个核写一次；核内 processed 单调递增，
        //    每元素只写一次。故写回为「不相交单点写」，普通 DataCopyPad 即完全正确。
        //    去掉 SetAtomicAdd/SetAtomicNone：原子累加语义要求目标 GM 预清零（累加到残留值），
        //    但算子自身不清零输出 GM，会对未零初始化的生产输出缓冲产生 garbage+value 错误；单点写
        //    无跨核累加需求，普通写既正确又消除「外部必须零初始化输出」的隐性契约、并省去原子开销。
        //    outTile 源 UB 起址 32B 对齐；DataCopyPad 支持 sub-32B GM 长度（blockLen 按字节），
        //    尾段 padding(curNum..alignedCnt) 不搬出。
        DataCopyExtParams copyParams;
        copyParams.blockCount = 1;
        copyParams.blockLen = curNum * sizeof(float);
        copyParams.srcStride = 0;
        copyParams.dstStride = 0;
        copyParams.rsv = 0;
        DataCopyPad(iouGM[pairStart_ + processed], outTile, copyParams);
        PipeBarrier<PIPE_ALL>();

        processed += cur;
    }
}

} // namespace NsIou3D
#endif // IOU3D_ARCH35_H
