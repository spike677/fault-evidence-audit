# FP-A01 硬件指令精度不足，未与竞品对齐

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：精度 ｜ 风险：高（S3×O3=9） ｜ 状态：活跃

- **元数据**：类别 精度 ｜ 风险 高（S3×O3=9）｜ 状态 活跃 ｜ 来源 团队笔记（2026-09-06）+ CANN issue 检索（2026-09-16）
- **适用**：仓 All ｜ 侧别 Kernel ｜ 载体 Kernel源码 ｜ 触发 Exp|Log1p|Rsqrt|Tanh|Power\( ｜ 默认启用 true
- **故障机理**：所选硬件指令（近似超越函数、低精度乘加等）的精度规格低于竞品同类指令，且未做软件补偿。
- **触发条件**：依赖特定指令路径的算子（exp/sin/cos/rsqrt 等近似指令实现）。
- **典型表现**：精度差异、网络精度波动。
- **源码审查映射点**：指令选型与精度对齐逻辑；降精度路径是否有补偿。
- **测试拦截建议**：含超越函数/近似指令的算子与 GPU 参考逐元素比对 utol；关键网络级 E2E 精度基线看护。
- **检测签名**：`Exp\s*\(\s*Muls\s*\(\s*Log`（exp/log 组合近似 pow）；`log1p|Log1p`（数值稳定补偿缺失排查点）。
- **实证案例**：ops-math #2110 cdist_grad 的 GENERAL(0<p<2)/LARGEP(p>2) 两条 DAG 用 `Exp(Muls(Log(ratio), p-1))` 近似 pow（误差 2-4 ULP），对标 `torch.ops.aten._cdist_backward` 的 `std::pow`（表驱动、内部扩展精度，<1 ULP）均方根误差劣化 **4.65 倍**（NPU fp32 3.91e-4 vs GPU A100 8.40e-5），ATK 双标杆精度不达标，修复改用高精度 `Vec::Power`（DOUBLE_FLOAT_TECH，约 1 ULP）与 torch 对齐；ops-math #2271 bessel_i1e（arch35）`exp(-|x|/4)` 的 Taylor 级数仅 9 项截断误差大 + 有理多项式系数有效位不足，最大误差 2.6e-6 远超 fp32 精度预期，修复将 Taylor 扩至 13 项、提升系数精度并分段 Horner 规避编译器限制，误差降至 6.1e-10（约 4000 倍，PR #4131）；ops-nn #3589 SoftplusV2 直接 `log(1+exp(x))` 无数值稳定补偿，输入 -16.619（exp≈6e-8，fp32 下 1+x 舍入为 1）NPU 输出 0 而 torch CPU 非 0。**共性特征：近似/低精度实现路径的精度规格低于标杆（GPU/CPU 库）且未做软件补偿，修复方式均为换用高精度指令、扩展级数项数或改用数值稳定实现。**
**索引类输出不得对标杆**：离散选择输出在并列时取值不唯一，拿它逐元素比参考值会产出假 FAIL——见 [EVIDENCE_DISCIPLINE.md](../../EVIDENCE_DISCIPLINE.md) D11。
- **参考实现前置（v6.30）**：判 aclnn 层必须用 `golden.py` 的 `__golden__["aclnn"]` 入口；只有 `kernel` 入口时**不得**用于 aclnn 层判定（层间 dtype/校验/布局差异会被误判成算子缺陷）；连 `aclnn` 入口都没有时记「判据不成立」而非「未覆盖」。实测 `ops-nn` 全仓 362 个 `golden.py` 仅 **80 个（22.1%）**含 `aclnn` 键——见 [EVIDENCE_DISCIPLINE.md](../../EVIDENCE_DISCIPLINE.md) D12/D13。
- **关联**：[FP-A14](FP-A14.md)、[FP-A17](FP-A17.md)。
