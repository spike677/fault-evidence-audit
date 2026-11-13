# FP-A16 aclop 与 aclnn 编译阶段精度差异

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：精度 ｜ 风险：高（S3×O3=9） ｜ 状态：活跃

- **元数据**：类别 精度 ｜ 风险 高（S3×O3=9）｜ 状态 活跃 ｜ 来源 团队笔记 + CANN issue 检索（2026-09-16）
- **适用**：仓 All ｜ 侧别 Host ｜ 载体 aclnn源码,IR与图配置 ｜ 触发 aclop|GEIR ｜ 默认启用 true
- **故障机理**：两条调用路径编译期常量折叠/精度决策不同，同一算子同输入结果不同。
- **触发条件**：同一算子分别经 aclop 与 aclnn 调用（实证中对应 aclnn 单算子与 GE 图/GEIR 两条路径）。
- **典型表现**：同一算子两条调用路径精度不同。
- **源码审查映射点**：编译期常量折叠/精度决策差异点；调用路径间补 pad/对齐等预处理决策差异。
- **测试拦截建议**：aclop/aclnn 双路径同输入一致性用例。
- **实证案例**：ops-transformer #4254 RotaryPositionEmbeddingGrad 同一 kernel 两条调用路径结果不同——ACLNN 单算子路径 97/3 FAIL（仅 mode=2 + **常量输入** + cos 全 broadcast 的 3 例，output[1] dcos 输出符号反转、MARE=2.0），GEIR 图路径 10/0 PASS；根因为 **ACLNN API 对常量输入触发优化路径，编译产物行为与源码不一致**（源码正确用原始 x 算 dcos，产物却用 rotate(x)），而 GEIR 经 GE 图框架直接调 kernel 不经过该优化；ops-transformer #4141 FlashAttentionScore aclnn 单算子路径含 V 尾轴非对齐的补 pad/消 pad 预处理（PadAiCore 48→64 → FA → Slice 64→48），GE 图路径 dense_v 直连无 pad，GE 图走 48 非对齐触发 kernel 缺陷致 27/30 batch 精度异常，而 aclnn 单算子同输入精度正常。**共性特征：同一算子经不同调用路径时，编译期常量优化与对齐/预处理决策不同，同输入结果不同；修复方向均为路径行为对齐而非单侧修数。**
- **关联**：[FP-A14](FP-A14.md)、[FP-D02](../FP-D/FP-D02.md)。
