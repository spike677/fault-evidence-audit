# FP-C02 A2 上 fp16 Vector 算子性能不如 bf16

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：性能 ｜ 风险：高（S2×O3=6，2026-10-02 复评：#2930、#5303 两条独立实证，O2→O3） ｜ 状态：活跃

- **元数据**：类别 性能 ｜ 风险 高（S2×O3=6，2026-10-02 复评：#2930、#5303 两条独立实证，O2→O3）｜ 状态 活跃 ｜ 来源 团队笔记
- **适用**：仓 All ｜ 侧别 Kernel ｜ 载体 Kernel源码 ｜ 触发 half|float16 ｜ 默认启用 true
- **故障机理**：dtype 分支走了非优化路径。
- **触发条件**：fp16 Vector 类算子。
- **典型表现**：同算子 fp16 慢于 bf16。
- **源码审查映射点**：dtype 分支实现差异，fp16 是否走降级路径。
- **测试拦截建议**：fp16/bf16 双 dtype 性能对比基线。
- **实证案例**：ops-nn #2930 【aclnnIndexAdd】在 Atlas A2（910B/910_93）上 **FP16 走旧 `InplaceIndexAdd` 路径**（先 Cast 到 FP32 再 Cast 回），而 BF16 走带排序的新算子 `InplaceIndexAddWithSorted`，导致相同 shape 下 FP16 性能明显差于 BF16（`index/inplace_scatter_add/op_host/op_api/aclnn_index_add.cpp`）；#5303 leaky_relu arch35 上 FP16/BF16 路径使用 `LeakyReluCastDag`（外层两次冗余 Cast）而 FP32 直接走 `LeakyReluDag`，带来冗余寄存器搬运与类型转换开销。**共性特征：dtype 分支指向了不同的算子实现/不同的 DAG 拓扑，而非同一实现内的数据类型差异——即「dtype 派发到未优化路径」。**
- **关联**：[FP-C03](FP-C03.md)（同一现象的对称面）、[FP-C01](FP-C01.md)、[FP-B01](../FP-B/FP-B01.md)（派发白名单/条件硬编码同源）。
