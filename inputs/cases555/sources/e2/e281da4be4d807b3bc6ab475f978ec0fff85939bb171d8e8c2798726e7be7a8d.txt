/**
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 */

/*!
 * \file cdist_grad_dag.h
 * \brief cdist_grad dag — six DAGs, Compare+Select via custom MicroAPI operators
 *
 * Custom operators (MicroAPI CompareScalar + Select, avoids DAG multi-consumer):
 *   CdistGradSignOp:       sign(x) via GT/LT compare → 1.0 / -1.0 / 0.0
 *   CdistGradMaskEQOp:     a == b ? 1.0 : 0.0 via Sub + EQ compare
 *   CdistGradMaskNEZeroOp: x != 0 ? 1.0 : 0.0 via EQ compare (inverted)
 *
 * CdistGradP0Dag:      p == 0   → output zeros
 * CdistGradP1Dag:      p == 1   → grad * sign(diff)
 * CdistGradP2Dag:      p == 2   → grad * diff / cdist
 * CdistGradDag:        0<p<2    → sign * (|diff|/cdist)^(p-1) * grad * masks
 * CdistGradLargePDag:  p>2      → sign * (|diff|/cdist)^(p-1) * grad * mask_cdist
 * CdistGradInfDag:     p==inf   → grad * sign * mask(|diff| >= cdist)
 */

#ifndef CDIST_GRAD_DAG_H
#define CDIST_GRAD_DAG_H

#include "atvoss/util/elems.h"
#include "atvoss/util/dag.h"
#include "atvoss/util/vec.h"
#include "atvoss/util/placeholder.h"
#include "atvoss/reduce/reduce_operator.h"
#include "cdist_grad_operator.h"

namespace CdistGrad {
using namespace Ops::Base;

constexpr int CAST_MODE_NONE = 0;
constexpr int CAST_MODE_RINT = 1;

constexpr int32_t NORM_MODE_GENERAL  = 0;  // 0 < p < 2, p != 1
constexpr int32_t NORM_MODE_INF      = 1;  // p == inf
constexpr int32_t NORM_MODE_LARGE_P  = 2;  // p > 2
constexpr int32_t NORM_MODE_P0       = 3;  // p == 0
constexpr int32_t NORM_MODE_P1       = 4;  // p == 1
constexpr int32_t NORM_MODE_P2       = 5;  // p == 2

// ---------------------------------------------------------------------------
// CdistGradP0Dag — p == 0 → output zeros
// Var<0>: zero_scalar = 0.0
// ---------------------------------------------------------------------------
template <typename T, typename PromoteT>
struct CdistGradP0Dag {
    using OpCopyInGrad = Bind<Vec::CopyIn<T>, Placeholder::In0<T>>;
    using CastGrad     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, OpCopyInGrad>;

    using OpZero    = Bind<Vec::Muls<PromoteT>, CastGrad, Placeholder::Var<PromoteT, 0>>;
    using ReduceOp0 = Bind<Vec::ReduceSumOp<PromoteT>, OpZero>;
    using CastOut   = Bind<Vec::Cast<T, PromoteT, CAST_MODE_RINT>, ReduceOp0>;
    using OpCopyOut = Bind<Vec::CopyOut<T>, Placeholder::Out0<T>, CastOut>;

    using Outputs = Elems<OpCopyOut>;
    using MemCfg  = MemOptCfg<MemLevel::LEVEL_2>;
    using OpDag   = DAGSch<Outputs, void, MemCfg>;
};

// ---------------------------------------------------------------------------
// CdistGradP1Dag — p == 1
// sign = CdistGradSignOp(diff)   via MicroAPI CompareScalar GT/LT + Select
// result = grad * sign
// ---------------------------------------------------------------------------
template <typename T, typename PromoteT>
struct CdistGradP1Dag {
    using OpCopyInGrad = Bind<Vec::CopyIn<T>, Placeholder::In0<T>>;
    using CastGrad     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, OpCopyInGrad>;

    using OpCopyInX1 = Bind<Vec::CopyIn<T>, Placeholder::In1<T>>;
    using CastX1     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, OpCopyInX1>;

    using OpCopyInX2 = Bind<Vec::CopyIn<T>, Placeholder::In2<T>>;
    using CastX2     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, OpCopyInX2>;

    using OpDiff     = Bind<Vec::Sub<PromoteT>, CastX1, CastX2>;
    using OpSign     = Bind<CdistGradSignOp<PromoteT>, OpDiff>;

    using OpRes      = Bind<Vec::Mul<PromoteT>, CastGrad, OpSign>;

    using ReduceOp0  = Bind<Vec::ReduceSumOp<PromoteT>, OpRes>;
    using CastOut    = Bind<Vec::Cast<T, PromoteT, CAST_MODE_RINT>, ReduceOp0>;
    using OpCopyOut  = Bind<Vec::CopyOut<T>, Placeholder::Out0<T>, CastOut>;

    using Outputs = Elems<OpCopyOut>;
    using MemCfg  = MemOptCfg<MemLevel::LEVEL_2>;
    using OpDag   = DAGSch<Outputs, void, MemCfg>;
};

// ---------------------------------------------------------------------------
// CdistGradP2Dag — p == 2
// mask = CdistGradMaskNEZeroOp(cdist)   via MicroAPI
// result = grad * diff / (cdist + eps) * mask
// Matches PyTorch: dist == 0 ? 0 : grad * diff / dist
// ---------------------------------------------------------------------------
template <typename T, typename PromoteT>
struct CdistGradP2Dag {
    using Eps = MAKE_CONST(PromoteT, 1e-30);

    using OpCopyInGrad = Bind<Vec::CopyIn<T>, Placeholder::In0<T>>;
    using CastGrad     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, OpCopyInGrad>;

    using OpCopyInX1 = Bind<Vec::CopyIn<T>, Placeholder::In1<T>>;
    using CastX1     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, OpCopyInX1>;

    using OpCopyInX2 = Bind<Vec::CopyIn<T>, Placeholder::In2<T>>;
    using CastX2     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, OpCopyInX2>;

    using OpCopyInCdist = Bind<Vec::CopyIn<T>, Placeholder::In3<T>>;
    using CastCdist     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, OpCopyInCdist>;

    using OpDiff      = Bind<Vec::Sub<PromoteT>, CastX1, CastX2>;
    using SafeCdist   = Bind<Vec::Adds<PromoteT>, CastCdist, Eps>;      // cdist + eps
    using OpNumerator = Bind<Vec::Mul<PromoteT>, CastGrad, OpDiff>;     // grad * diff
    using OpDivResult = Bind<Vec::Div<PromoteT>, OpNumerator, SafeCdist>; // grad * diff / (cdist+eps)

    // mask: cdist != 0 ? 1.0 : 0.0 — zeros out when cdist=0
    using OpMask      = Bind<CdistGradMaskNEZeroOp<PromoteT>, CastCdist>;
    using OpResult    = Bind<Vec::Mul<PromoteT>, OpDivResult, OpMask>;

    using ReduceOp0  = Bind<Vec::ReduceSumOp<PromoteT>, OpResult>;
    using CastOut    = Bind<Vec::Cast<T, PromoteT, CAST_MODE_RINT>, ReduceOp0>;
    using OpCopyOut  = Bind<Vec::CopyOut<T>, Placeholder::Out0<T>, CastOut>;

    using Outputs = Elems<OpCopyOut>;
    using MemCfg  = MemOptCfg<MemLevel::LEVEL_2>;
    using OpDag   = DAGSch<Outputs, void, MemCfg>;
};

// ---------------------------------------------------------------------------
// CdistGradDag — 0 < p < 2, p != 1
// sign = CdistGradSignOp(diff)                     via MicroAPI
// safe_cdist = cdist + eps  (prevents div-by-0)
// ratio = |diff| / safe_cdist
// pow_ratio = exp(log(ratio + eps) * (p-1))        single log+exp chain
// mask_diff = CdistGradMaskNEZeroOp(|diff|)        via MicroAPI
// mask_cdist = CdistGradMaskNEZeroOp(cdist)        via MicroAPI
// result = sign * pow_ratio * grad * mask_cdist * mask_diff
//
// Optimization: (|diff|/cdist)^(p-1) replaces separate |diff|^(p-1)/cdist^(p-1),
// cutting transcendental ops from 2 log + 2 exp + 1 div → 1 log + 1 exp + 1 div.
// Var<0>: power = p - 1
// ---------------------------------------------------------------------------
template <typename T, typename PromoteT>
struct CdistGradDag {
    using DagEps = MAKE_CONST(PromoteT, 1e-30);

    using DagCopyInGrad = Bind<Vec::CopyIn<T>, Placeholder::In0<T>>;
    using DagCastGrad     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, DagCopyInGrad>;

    using DagCopyInX1 = Bind<Vec::CopyIn<T>, Placeholder::In1<T>>;
    using DagCastX1     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, DagCopyInX1>;

    using DagCopyInX2 = Bind<Vec::CopyIn<T>, Placeholder::In2<T>>;
    using DagCastX2     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, DagCopyInX2>;

    using DagCopyInCdist = Bind<Vec::CopyIn<T>, Placeholder::In3<T>>;
    using DagCastCdist     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, DagCopyInCdist>;

    // diff & abs
    using DagDiff      = Bind<Vec::Sub<PromoteT>, DagCastX1, DagCastX2>;
    using DagDiffAbs   = Bind<Vec::Abs<PromoteT>, DagDiff>;
    using DagSafeCdist   = Bind<Vec::Adds<PromoteT>, DagCastCdist, DagEps>;       // cdist + eps

    // sign via MicroAPI
    using DagSign      = Bind<CdistGradSignOp<PromoteT>, DagDiff>;

    // masks via MicroAPI: 0 when input=0, 1 otherwise
    using DagMaskDiff    = Bind<CdistGradMaskNEZeroOp<PromoteT>, DagDiffAbs>;
    using DagMaskCdist   = Bind<CdistGradMaskNEZeroOp<PromoteT>, DagCastCdist>;

    // Mask |diff| to 0 where cdist==0 BEFORE the ratio. When the forward cdist
    // underflows to 0 (large/tiny |diff|), ratio = |diff|/eps would explode and
    // exp(log(ratio)*(p-1)) overflows to +inf; the trailing mask then yields
    // inf*0 = NaN. Masking first makes ratio=0 -> pow_ratio=0 -> result=0,
    // matching PyTorch CPU's `dist==0 ? 0` short-circuit.
    using DagDiffAbsM  = Bind<Vec::Mul<PromoteT>, DagDiffAbs, DagMaskCdist>;
    // ratio = |diff|_masked / (cdist + eps), then (ratio)^(p-1) via single log+exp chain
    using DagRatio       = Bind<Vec::Div<PromoteT>, DagDiffAbsM, DagSafeCdist>;
    using DagSafeRatio   = Bind<Vec::Adds<PromoteT>, DagRatio, DagEps>;
    using DagPowRatio    = Bind<Vec::Exp<PromoteT>,
                             Bind<Vec::Muls<PromoteT>, Bind<Vec::Log<PromoteT>, DagSafeRatio>,
                              Placeholder::Var<PromoteT, 0>>>;

    // num = sign * (|diff|/cdist)^(p-1), result = num * grad * masks
    using DagNum       = Bind<Vec::Mul<PromoteT>, DagSign, DagPowRatio>;
    using DagNumerator = Bind<Vec::Mul<PromoteT>, DagNum, DagCastGrad>;

    // apply masks: zero-out when cdist=0 or |diff|=0
    using DagMaskedCdist = Bind<Vec::Mul<PromoteT>, DagNumerator, DagMaskCdist>;
    using DagResult      = Bind<Vec::Mul<PromoteT>, DagMaskedCdist, DagMaskDiff>;

    using DagReduceOp0  = Bind<Vec::ReduceSumOp<PromoteT>, DagResult>;
    using DagCastOut    = Bind<Vec::Cast<T, PromoteT, CAST_MODE_RINT>, DagReduceOp0>;
    using DagCopyOut  = Bind<Vec::CopyOut<T>, Placeholder::Out0<T>, DagCastOut>;

    using Outputs = Elems<DagCopyOut>;
    using MemCfg  = MemOptCfg<MemLevel::LEVEL_2>;
    using OpDag   = DAGSch<Outputs, void, MemCfg>;
};

// ---------------------------------------------------------------------------
// CdistGradLargePDag — p > 2
// Equivalent to: sign(diff) * (|diff|/cdist)^(p-1) * grad
//   since diff * |diff|^(p-2) / cdist^(p-1) = sign * |diff|^(p-1) / cdist^(p-1)
//                                            = sign * (|diff|/cdist)^(p-1)
//
// sign = CdistGradSignOp(diff)                     via MicroAPI
// safe_cdist = cdist + eps
// ratio = |diff| / safe_cdist
// pow_ratio = exp(log(ratio + eps) * (p-1))        single log+exp chain
// mask_cdist = CdistGradMaskNEZeroOp(cdist)        via MicroAPI
// result = sign * pow_ratio * grad * mask_cdist
//
// Optimization: same ratio approach as CdistGradDag, reducing from
// 2 log + 2 exp + 1 div → 1 log + 1 exp + 1 div.
// Var<0>: power = p - 1
// ---------------------------------------------------------------------------
template <typename T, typename PromoteT>
struct CdistGradLargePDag {
    using LpEps = MAKE_CONST(PromoteT, 1e-30);

    using LpCopyInGrad = Bind<Vec::CopyIn<T>, Placeholder::In0<T>>;
    using LpCastGrad     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, LpCopyInGrad>;

    using LpCopyInX1 = Bind<Vec::CopyIn<T>, Placeholder::In1<T>>;
    using LpCastX1     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, LpCopyInX1>;

    using LpCopyInX2 = Bind<Vec::CopyIn<T>, Placeholder::In2<T>>;
    using LpCastX2     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, LpCopyInX2>;

    using LpCopyInCdist = Bind<Vec::CopyIn<T>, Placeholder::In3<T>>;
    using LpCastCdist     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, LpCopyInCdist>;

    using LpDiff     = Bind<Vec::Sub<PromoteT>, LpCastX1, LpCastX2>;
    using LpDiffAbs  = Bind<Vec::Abs<PromoteT>, LpDiff>;
    using LpSafeCdist  = Bind<Vec::Adds<PromoteT>, LpCastCdist, LpEps>;       // cdist + eps

    // sign via MicroAPI
    using LpSign      = Bind<CdistGradSignOp<PromoteT>, LpDiff>;

    // mask via MicroAPI: cdist != 0 ? 1.0 : 0.0
    using LpMaskCdist  = Bind<CdistGradMaskNEZeroOp<PromoteT>, LpCastCdist>;

    // Mask |diff| to 0 where cdist==0 BEFORE the ratio (see CdistGradDag rationale).
    // Without this, forward cdist underflow (large p, tiny |diff|) makes ratio =
    // |diff|/eps explode -> exp overflow +inf -> trailing mask inf*0 = NaN.
    using LpDiffAbsM  = Bind<Vec::Mul<PromoteT>, LpDiffAbs, LpMaskCdist>;
    // ratio = |diff|_masked / (cdist + eps), then (ratio)^(p-1) via single log+exp chain
    using LpRatio       = Bind<Vec::Div<PromoteT>, LpDiffAbsM, LpSafeCdist>;
    using LpSafeRatio   = Bind<Vec::Adds<PromoteT>, LpRatio, LpEps>;
    using LpPowRatio    = Bind<Vec::Exp<PromoteT>,
                             Bind<Vec::Muls<PromoteT>, Bind<Vec::Log<PromoteT>, LpSafeRatio>,
                              Placeholder::Var<PromoteT, 0>>>;

    // num = sign * (|diff|/cdist)^(p-1), result = num * grad * mask
    using LpNum       = Bind<Vec::Mul<PromoteT>, LpSign, LpPowRatio>;
    using LpNumerator = Bind<Vec::Mul<PromoteT>, LpNum, LpCastGrad>;
    using LpResult    = Bind<Vec::Mul<PromoteT>, LpNumerator, LpMaskCdist>;

    using LpReduceOp0  = Bind<Vec::ReduceSumOp<PromoteT>, LpResult>;
    using LpCastOut    = Bind<Vec::Cast<T, PromoteT, CAST_MODE_RINT>, LpReduceOp0>;
    using LpCopyOut  = Bind<Vec::CopyOut<T>, Placeholder::Out0<T>, LpCastOut>;

    using Outputs = Elems<LpCopyOut>;
    using MemCfg  = MemOptCfg<MemLevel::LEVEL_2>;
    using OpDag   = DAGSch<Outputs, void, MemCfg>;
};

// ---------------------------------------------------------------------------
// CdistGradInfDag — p == inf
// sign = CdistGradSignOp(diff)       via MicroAPI CompareScalar GT/LT + Select
// mask = CdistGradMaskEQOp(|diff|, cdist)  via MicroAPI Sub + CompareScalar EQ + Select
// result = grad * sign * mask
// ---------------------------------------------------------------------------
template <typename T, typename PromoteT>
struct CdistGradInfDag {
    using InfCopyInGrad = Bind<Vec::CopyIn<T>, Placeholder::In0<T>>;
    using InfCastGrad     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, InfCopyInGrad>;

    using InfCopyInX1 = Bind<Vec::CopyIn<T>, Placeholder::In1<T>>;
    using InfCastX1     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, InfCopyInX1>;

    using InfCopyInX2 = Bind<Vec::CopyIn<T>, Placeholder::In2<T>>;
    using InfCastX2     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, InfCopyInX2>;

    using InfCopyInCdist = Bind<Vec::CopyIn<T>, Placeholder::In3<T>>;
    using InfCastCdist     = Bind<Vec::Cast<PromoteT, T, CAST_MODE_NONE>, InfCopyInCdist>;

    using InfDiff      = Bind<Vec::Sub<PromoteT>, InfCastX1, InfCastX2>;
    using InfDiffAbs   = Bind<Vec::Abs<PromoteT>, InfDiff>;

    // sign = MicroAPI sign(diff)
    using InfSign      = Bind<CdistGradSignOp<PromoteT>, InfDiff>;

    // mask = MicroAPI (|diff| == cdist) ? 1.0 : 0.0
    using InfMask      = Bind<CdistGradMaskEQOp<PromoteT>, InfDiffAbs, InfCastCdist>;

    // result = grad * sign * mask
    using InfGradSign  = Bind<Vec::Mul<PromoteT>, InfCastGrad, InfSign>;
    using InfResult    = Bind<Vec::Mul<PromoteT>, InfGradSign, InfMask>;

    using InfReduceOp0   = Bind<Vec::ReduceSumOp<PromoteT>, InfResult>;
    using InfCastOut     = Bind<Vec::Cast<T, PromoteT, CAST_MODE_RINT>, InfReduceOp0>;
    using InfCopyOut   = Bind<Vec::CopyOut<T>, Placeholder::Out0<T>, InfCastOut>;

    using Outputs = Elems<InfCopyOut>;
    using MemCfg  = MemOptCfg<MemLevel::LEVEL_2>;
    using OpDag   = DAGSch<Outputs, void, MemCfg>;
};

}  // namespace CdistGrad

#endif  // CDIST_GRAD_DAG_H
