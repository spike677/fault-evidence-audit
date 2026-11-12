# FP-A14 FFMA 与 MMAD 硬件指令差异

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：精度 ｜ 风险：高（S3×O3=9，2026-10-02 复评：#1246、#1577、#3503 三条独立实证，O2→O3） ｜ 状态：活跃

- **元数据**：类别 精度 ｜ 风险 高（S3×O3=9，2026-10-02 复评：#1246、#1577、#3503 三条独立实证，O2→O3）｜ 状态 活跃 ｜ 来源 团队笔记
- **适用**：仓 All ｜ 侧别 Kernel ｜ 载体 Kernel源码 ｜ 触发 Mmad|MMAD|SetMMAD ｜ 默认启用 true
- **故障机理**：Vector(FFMA) 与 Cube(MMAD) 的浮点语义（累加器精度、舍入模式）不同，同一数学在两条路径结果有差。
- **触发条件**：同一算子存在 Vector/Cube 两条实现路径且可切换。
- **典型表现**：精度结果与 GPU 不一致；路径切换前后结果差异。
- **源码审查映射点**：Vector(FFMA) 与 Cube(MMAD) 路径的精度语义差异点。
- **测试拦截建议**：强制走两条路径的开关级用例对比。
- **实证案例**：ops-nn #3503 conv2d（c04 + innerbatch + 1x1 卷积 + NCHW）**mmad 指令配置错误**致精度问题（950PR，fp16，通路经 pytorch 执行，精度比对最大相对误差 100%）；#1577 `block_mmad_mx_weight_from_ub.h` / `block_prologue_b_cast_scsc_nn.h` 两处 `stepKb` 从 `stepKa` 错误初始化；ops-transformer #1246 mxfp8 blockmmad 在 A 转置/B 不转置且 ND 场景下的泛化精度问题（值域拼接处的 K 对齐补零缺失）。**共性特征：缺陷位于 Cube（MMAD）侧的搬运/指令配置/对齐环节，而非 Vector 侧；A14 关注的「同一数学在 FFMA 与 MMAD 两路径结果有差」在四仓 issue 中体现为 Cube 侧配置错误导致的精度失败，属本型的一种呈现形式。**
**索引类输出不得对标杆**：同 A01，见 [EVIDENCE_DISCIPLINE.md](../../EVIDENCE_DISCIPLINE.md) D11。
- **参考实现前置（v6.30）**：判 aclnn 层必须用 `golden.py` 的 `__golden__["aclnn"]` 入口；只有 `kernel` 入口时**不得**用于 aclnn 层判定（层间 dtype/校验/布局差异会被误判成算子缺陷）；连 `aclnn` 入口都没有时记「判据不成立」而非「未覆盖」。实测 `ops-nn` 全仓 362 个 `golden.py` 仅 **80 个（22.1%）**含 `aclnn` 键——见 [EVIDENCE_DISCIPLINE.md](../../EVIDENCE_DISCIPLINE.md) D12/D13。
- **关联**：[FP-A01](FP-A01.md)、[FP-A16](FP-A16.md)、[FP-A08](FP-A08.md)（#1246 的 K 对齐补零缺失与尾块/对齐问题同源）。注：FFMA 为 Vector 融合乘加指令、MMAD 为 Cube 矩阵乘指令。
