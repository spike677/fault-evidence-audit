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
 *   - 向量批算：AscendC::Sin / AscendC::Cos（4/pair 顶点 theta，adv_api math）。
 *   - 硬件排序：>3 顶点走 AscendC::Sort32 + Extract（diamond-angle 极角键，替代标量选择排序）。
 *   - 标量几何：分支密集（corners_num∈{0..8}），逐对用 LocalTensor::GetValue 读标量控制。
 *   - 数值稳定三守卫：
 *       epsilon_guard_division   : iou = interVol / max(union, 1e-6)（对标 mmcv clamp，golden.py:377）
 *       clamp_z_overlap_nonneg   : real_d = max(min-max, 0)
 *       degenerate_polygon_guard : corners_num < 3 → area = 0
 *   - 近同旋转框 bowtie 半面积退化修复（fp32 特有）：
 *       幅值相对强去重 : CollectCorners 去重容差 tol=max(1e-6, 1e-4·max(1,|x|,|y|))，
 *                        坍缩 fp32 向量 Sin/Cos 逐 lane 微差产生的近重复顶点（m=6/8→4），
 *                        相对幅值以兼容大坐标场景（不误并真顶点）。
 *       signed shoelace: SortPolygonArea 面积用有符号鞋带（不 per-triangle 取 abs，末尾一次 abs），
 *                        对残留错序/自交鲁棒（错序正负抵消，不放大成半面积）。
 *       红线 : 面积层严禁任何 NaN 守卫；NaN/inf 按 IEEE754 自然传播。
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

constexpr uint32_t IOU3D_DOF = 7;       // 7-DoF 通道数
constexpr uint32_t IOU3D_CORNERS = 4;   // 每框 BEV 顶点数
constexpr uint32_t IOU3D_MAX_INTER = 8; // 交集多边形顶点数上限（两凸四边形交集 <= 8）
constexpr float IOU3D_EPSILON = 1e-6f;  // IoU 分母 clamp 下限（对标 mmcv golden.py:37 EPS_IOU=1e-6）
// 对标 mmcv：边相交退化判据阈值。|s5-s1|>EPS_KERNEL 用叉积公式，否则退化一般式直线方程
//   （对标 mmcv golden.py:35/153 EPS_KERNEL=1e-8）。
constexpr float IOU3D_EPS_KERNEL = 1e-8f;
// 对标 mmcv：顶点包含测试绝对容差。反向旋转到框局部系后判 |rot|<half+MARGIN
//   （对标 mmcv golden.py:36/194-195 MARGIN=1e-2，严格 <）。
constexpr float IOU3D_MARGIN = 1e-2f;
constexpr float IOU3D_DEDUP_TOL = 1e-6f; // 顶点去重绝对容差下限（小坐标场景，D6 保留现状）
// 幅值相对强去重容差（D6 保留现状）。fp32 向量 Sin/Cos 逐 lane 微差使「同一角点」在 bbox/gtbox 两通道间
//   偏差 ~1e-7~1e-5·幅值，叠加近共线边额外交点，使 identical box 去重后仍残留 m∈{6,8} 近重复
//   顶点 → Sort32 tie-break bowtie → 半面积 → IoU=1/3。用相对幅值容差 tol=max(ABS, REL·max(1,|x|,|y|))
//   把近重复坍缩回 4 真角点；相对而非绝对以兼容大坐标（1e20 场景不被误并——真顶点间距 >> REL·幅值）。
constexpr float IOU3D_DEDUP_REL = 1e-4f; // 顶点去重相对幅值容差（D6 保留现状）
// fp32 32B(one data block) = 8 元素。RegBase(arch35) 向量 adv_api Sin/Cos 要求 src/dst 32B 对齐
// （sin_3510_impl 用 Reg::StoreAlign<..,DIST_PACK_B32>），故所有参与向量计算的 UB 子段起址与长度按 8 对齐。
constexpr uint32_t IOU3D_ALIGN_ELEM = 8; // fp32 一个 datablock 的元素数（32B / 4B）
// 硬件极角排序（Sort32）常量。
constexpr uint32_t IOU3D_SORT32_LEN = 32U;    // Sort32 一趟固定处理 32 元素（8 有效 + 24 padding 沉底）
constexpr float IOU3D_NEG_INF_KEY = -1.0e30f; // padding 槽键值（沉底到排序末尾）
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
    // 线段相交（对标 mmcv check_rect_cross + 跨立实验 + 直线求交 golden.py:104-168），相交返回 true 并写 (ox, oy)
    __aicore__ inline bool SegIntersect(float a1x, float a1y, float a2x, float a2y, float b1x, float b1y, float b2x,
                                        float b2y, float& ox, float& oy);
    // 收集交集顶点（含去重），返回顶点数。box1/box2 各传 (cx,cy,halfDx,halfDy,sinT,cosT) 供反向旋转包含测试。
    __aicore__ inline uint32_t CollectCorners(const float c1x[IOU3D_CORNERS], const float c1y[IOU3D_CORNERS],
                                              const float c2x[IOU3D_CORNERS], const float c2y[IOU3D_CORNERS],
                                              float box1cx, float box1cy, float box1hx, float box1hy, float box1sin,
                                              float box1cos, float box2cx, float box2cy, float box2hx, float box2hy,
                                              float box2sin, float box2cos, float px[IOU3D_MAX_INTER],
                                              float py[IOU3D_MAX_INTER]);
    // 三角形面积（叉积法）
    __aicore__ inline float TriArea(float x1, float y1, float x2, float y2, float x3, float y3);
    // 多边形面积（0/1/2→0 守卫；3→三角形直算；>3→质心分解 + 硬件 Sort32 极角排序 + 三角形叉积和）
    __aicore__ inline float PolygonArea(float px[IOU3D_MAX_INTER], float py[IOU3D_MAX_INTER], uint32_t m);
    // >3 顶点：硬件 Sort32 极角排序（diamond-angle 键）+ 质心分解叉积面积。
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
    uint32_t alignedTl_ = 0; // 32B 对齐后的单批粒度（各 UB 子段步长）
    uint32_t isEmpty_ = 0;   // 空 Tensor 标志（从 tilingData 读取，用于运行时判断）
    int64_t pairStart_ = 0;  // 本核 flatten (b,i,j) 起始
    int64_t pairCount_ = 0;  // 本核 flatten 对数
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
    // Sin/Cos fp32 主路径不消耗 sharedTmpBuffer，但显式提供 32B 对齐的 tmp 以规避 PopStackBuffer 栈依赖。
    pipe.InitBuffer(tmpBuf, alignedTl_ * sizeof(float));
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
// BoxCorners（与 golden BoxCorners 顺序一致：P1 左上, P2 右上, P3 右下, P4 左下）
// ---------------------------------------------------------------------------

__aicore__ inline void Iou3D::BoxCorners(float x, float y, float w, float h, float sinT, float cosT,
                                         float cx[IOU3D_CORNERS], float cy[IOU3D_CORNERS])
{
    float halfW = 0.5f * w;
    float halfH = 0.5f * h;
    float hwCos = halfW * cosT;
    float hwSin = halfW * sinT;
    float hhCos = halfH * cosT;
    float hhSin = halfH * sinT;

    float xSubW = x - hwCos;
    float ySubW = y - hwSin;
    float xAddW = x + hwCos;
    float yAddW = y + hwSin;

    cx[0] = xSubW - hhSin;
    cy[0] = ySubW + hhCos; // P1 左上
    cx[1] = xAddW - hhSin;
    cy[1] = yAddW + hhCos; // P2 右上
    cx[2] = xAddW + hhSin;
    cy[2] = yAddW - hhCos; // P3 右下
    cx[3] = xSubW + hhSin;
    cy[3] = ySubW - hhCos; // P4 左下
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
// SegIntersect（对标 mmcv intersection golden.py:104-168，逐分支复刻）
//   ⚠️ 已知会重引入 θ=π fp32 伪交点风险（用户明确接受，为逐分支对标 mmcv 的权衡）。
//   变量映射（我方边 a=(a1→a2) 对应 mmcv p0→p1，边 b=(b1→b2) 对应 q0→q1）：
//     p0=(a1x,a1y) p1=(a2x,a2y) q0=(b1x,b1y) q1=(b2x,b2y)
//   ① check_rect_cross 快速排斥（golden.py:104-112 / 139）
//   ② 跨立实验 s1*s2>0 && s3*s4>0（严格 >，共线/相切拒绝）（golden.py:143-149）
//        cross_3pts(a,b,c)=(a.x-c.x)*(b.y-c.y)-(b.x-c.x)*(a.y-c.y)（golden.py:120）
//   ③ |s5-s1|>EPS_KERNEL 用叉积公式，否则退化一般式直线方程（不判 D==0）（golden.py:152-166）
// ---------------------------------------------------------------------------

__aicore__ inline bool Iou3D::SegIntersect(float a1x, float a1y, float a2x, float a2y, float b1x, float b1y, float b2x,
                                           float b2y, float& ox, float& oy)
{
    // p0=(a1x,a1y) p1=(a2x,a2y) q0=(b1x,b1y) q1=(b2x,b2y)
    // ① check_rect_cross 快速排斥（AABB 包围盒重叠判定），对标 golden.py:104-112
    if (!(ScalarMin(a1x, a2x) <= ScalarMax(b1x, b2x) && ScalarMin(b1x, b2x) <= ScalarMax(a1x, a2x) &&
          ScalarMin(a1y, a2y) <= ScalarMax(b1y, b2y) && ScalarMin(b1y, b2y) <= ScalarMax(a1y, a2y))) {
        return false;
    }

    // cross_3pts(a,b,c) = (a.x-c.x)*(b.y-c.y) - (b.x-c.x)*(a.y-c.y)，对标 golden.py:115-120
    // ② 跨立实验（叉积判别），对标 golden.py:143-146
    float s1 = (b1x - a1x) * (a2y - a1y) - (a2x - a1x) * (b1y - a1y); // cross(q0, p1, p0)
    float s2 = (a2x - a1x) * (b2y - a1y) - (b2x - a1x) * (a2y - a1y); // cross(p1, q1, p0)
    float s3 = (a1x - b1x) * (b2y - b1y) - (b2x - b1x) * (a1y - b1y); // cross(p0, q1, q0)
    float s4 = (b2x - b1x) * (a2y - b1y) - (a2x - b1x) * (b2y - b1y); // cross(q1, p1, q0)

    // 严格 >：共线/相切被拒（对标 golden.py:148）
    if (!(s1 * s2 > 0.0f && s3 * s4 > 0.0f)) {
        return false;
    }

    // ③ 交点坐标计算（对标 golden.py:152-166）
    float s5 = (b2x - a1x) * (a2y - a1y) - (a2x - a1x) * (b2y - a1y); // cross(q1, p1, p0)
    if (ScalarAbs(s5 - s1) > IOU3D_EPS_KERNEL) {
        ox = (s5 * b1x - s1 * b2x) / (s5 - s1);
        oy = (s5 * b1y - s1 * b2y) / (s5 - s1);
    } else {
        // 退化情况：一般式直线方程（mmcv 不判 D==0，可产 inf/nan 并自然传播）
        float a0 = a1y - a2y;
        float b0 = a2x - a1x;
        float c0 = a1x * a2y - a2x * a1y;
        float a1c = b1y - b2y;
        float b1c = b2x - b1x;
        float c1c = b1x * b2y - b2x * b1y;
        float D = a0 * b1c - a1c * b0;
        ox = (b0 * c1c - b1c * c0) / D;
        oy = (a1c * c0 - a0 * c1c) / D;
    }
    return true;
}

// ---------------------------------------------------------------------------
// CollectCorners（框1顶点∈框2 + 框2顶点∈框1 + 16 边对相交，含去重）
// ---------------------------------------------------------------------------

__aicore__ inline uint32_t Iou3D::CollectCorners(const float c1x[IOU3D_CORNERS], const float c1y[IOU3D_CORNERS],
                                                 const float c2x[IOU3D_CORNERS], const float c2y[IOU3D_CORNERS],
                                                 float box1cx, float box1cy, float box1hx, float box1hy, float box1sin,
                                                 float box1cos, float box2cx, float box2cy, float box2hx, float box2hy,
                                                 float box2sin, float box2cos, float px[IOU3D_MAX_INTER],
                                                 float py[IOU3D_MAX_INTER])
{
    float rawX[IOU3D_MAX_INTER + IOU3D_MAX_INTER + 16];
    float rawY[IOU3D_MAX_INTER + IOU3D_MAX_INTER + 16];
    uint32_t rawCnt = 0;

    // 框1顶点 ∈ 框2（反向旋转到框2局部系测试），对标 mmcv golden.py:245 check_in_box2d(box_b, corners_a[k])
    for (uint32_t i = 0; i < IOU3D_CORNERS; ++i) {
        if (PointInRect(c1x[i], c1y[i], box2cx, box2cy, box2hx, box2hy, box2sin, box2cos)) {
            rawX[rawCnt] = c1x[i];
            rawY[rawCnt] = c1y[i];
            ++rawCnt;
        }
    }
    // 框2顶点 ∈ 框1，对标 mmcv golden.py:241 check_in_box2d(box_a, corners_b[k])
    for (uint32_t i = 0; i < IOU3D_CORNERS; ++i) {
        if (PointInRect(c2x[i], c2y[i], box1cx, box1cy, box1hx, box1hy, box1sin, box1cos)) {
            rawX[rawCnt] = c2x[i];
            rawY[rawCnt] = c2y[i];
            ++rawCnt;
        }
    }
    for (uint32_t i = 0; i < IOU3D_CORNERS; ++i) {
        float a1x = c1x[i], a1y = c1y[i];
        float a2x = c1x[(i + 1) % IOU3D_CORNERS], a2y = c1y[(i + 1) % IOU3D_CORNERS];
        for (uint32_t j = 0; j < IOU3D_CORNERS; ++j) {
            float b1x = c2x[j], b1y = c2y[j];
            float b2x = c2x[(j + 1) % IOU3D_CORNERS], b2y = c2y[(j + 1) % IOU3D_CORNERS];
            float ox, oy;
            if (SegIntersect(a1x, a1y, a2x, a2y, b1x, b1y, b2x, b2y, ox, oy)) {
                rawX[rawCnt] = ox;
                rawY[rawCnt] = oy;
                ++rawCnt;
            }
        }
    }

    // 去重（幅值相对强去重）。tol = max(ABS_TOL, REL·max(1,|x|,|y|))，
    //   顶点自身幅值决定容差：小坐标退化为绝对 1e-6，大坐标（1e20）随幅值放大避免误并真顶点，
    //   fp32 近重复顶点（identical box m=6/8）被坍缩回 4 真角点 → Sort32 键分离 → 稳定环序。
    //   最多保留 IOU3D_MAX_INTER 个。
    uint32_t m = 0;
    for (uint32_t k = 0; k < rawCnt; ++k) {
        float magK = ScalarMax(1.0f, ScalarMax(ScalarAbs(rawX[k]), ScalarAbs(rawY[k])));
        float tolK = ScalarMax(IOU3D_DEDUP_TOL, IOU3D_DEDUP_REL * magK);
        bool dup = false;
        for (uint32_t u = 0; u < m; ++u) {
            if (ScalarAbs(rawX[k] - px[u]) < tolK && ScalarAbs(rawY[k] - py[u]) < tolK) {
                dup = true;
                break;
            }
        }
        if (!dup && m < IOU3D_MAX_INTER) {
            px[m] = rawX[k];
            py[m] = rawY[k];
            ++m;
        }
    }
    return m;
}

// ---------------------------------------------------------------------------
// TriArea（叉积法）
// ---------------------------------------------------------------------------

__aicore__ inline float Iou3D::TriArea(float x1, float y1, float x2, float y2, float x3, float y3)
{
    float v = x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2);
    return ScalarAbs(v) * 0.5f;
}

// ---------------------------------------------------------------------------
// PolygonArea：0/1/2 顶点 → 0（degenerate_polygon_guard）；3 → 三角形；
//   >3 → 硬件 Sort32 极角排序（SortPolygonArea）
// ---------------------------------------------------------------------------

__aicore__ inline float Iou3D::PolygonArea(float px[IOU3D_MAX_INTER], float py[IOU3D_MAX_INTER], uint32_t m)
{
    if (m < 3)
        return 0.0f; // degenerate_polygon_guard
    if (m == 3)
        return TriArea(px[0], py[0], px[1], py[1], px[2], py[2]);
    if (m > IOU3D_MAX_INTER)
        m = IOU3D_MAX_INTER; // 顶点数上限守卫（两凸四边形交集 <=8）
    return SortPolygonArea(px, py, m);
}

// ---------------------------------------------------------------------------
// SortPolygonArea：>3 顶点，硬件 Sort32 极角排序（diamond-angle 键）+ 质心分解叉积面积。
//   1. 质心 (xc,yc)；相对质心坐标 (xr,yr)。
//   2. diamond-angle 键 key = (xr>=0)? t : (2-t)，t = yr/(|xr|+|yr|)，与 atan2(yr,xr) 单调同序；
//      Sort32 为降序，故送 -key 得 angle 升序（逆时针）；padding 槽(idx>=m) 键置 -INF 沉底。
//   3. Sort32 + Extract 得排序后原始下标序 order[0..m-1]（逆时针环序）。
//   4. 质心分解：相邻 (C, v[order[i]], v[order[i+1]]) 三角形叉积绝对值累加。
//   面积对环序方向（顺/逆）不敏感（叉积取绝对值），与 atan2 升序等价。
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
            float keyRaw = (xr >= 0.0f) ? t : (2.0f - t);
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

    // 面积（signed shoelace 收尾）。质心分解累加**有符号**叉积（不 per-triangle 取 abs），
    //   末尾对总和取一次 abs。去重已保证只剩真顶点、Sort32 环序为简单多边形，signed-shoelace
    //   与 per-triangle abs-fan 结果一致（对方向鲁棒）；但对「万一残留的近重复点/方向错序」多一层符号
    //   自洽保护——错序下正负三角形自然抵消，不会像 per-triangle abs-fan 那样把 bowtie 放大成半面积。
    //   ⚠️ 严禁任何面积层 NaN 守卫；NaN/inf 必须按 IEEE754 自然传播到输出。
    float signedTwice = 0.0f; // 2·有符号面积（相对质心的鞋带和）
    for (uint32_t k = 0; k < m; ++k) {
        uint32_t a = order[k];
        uint32_t bnext = order[(k + 1U == m) ? 0U : (k + 1U)];
        float ax = px[a] - xc;
        float ay = py[a] - yc;
        float bx = px[bnext] - xc;
        float by = py[bnext] - yc;
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
    LocalTensor<uint8_t> sinTmp = tmpBuf.Get<uint8_t>(); // 显式 sharedTmpBuffer（32B 对齐）

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
