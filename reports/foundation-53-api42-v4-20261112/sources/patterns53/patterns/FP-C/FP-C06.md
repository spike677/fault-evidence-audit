# FP-C06 A5 性能劣于 A2

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：性能 ｜ 风险：高（S2×O3=6，2026-10-02 复评：7 条独立实证，O2→O3） ｜ 状态：活跃

- **元数据**：类别 性能 ｜ 风险 高（S2×O3=6，2026-10-02 复评：7 条独立实证，O2→O3）｜ 状态 活跃 ｜ 来源 团队笔记
- **适用**：仓 All ｜ 侧别 All ｜ 载体 Tiling源码,Kernel源码 ｜ 触发 GetSocVersion|SOC_VERSION ｜ 默认启用 true
- **故障机理**：新 SOC 适配不完整的性能路径。
- **触发条件**：新代际芯片首发适配期。
- **典型表现**：新代际性能不升反降。
- **源码审查映射点**：新 SOC 适配中的性能路径完整性。
- **测试拦截建议**：跨代际性能基线对比。
- **实证案例**：ops-nn #3724 aclnnAdaptiveMaxPool3dBackward 存在用例 **A5 性能劣化于 A2/A3**；#3677 / #3822 convolution_backward 接口典型 case 在 A5 上性能劣于 A3；#4509 aclnnAdaptiveMaxPool3d 接口典型 case 在 A5 上性能劣于 A3；#5786 LSTM 算子精度、性能相对 A2 存在劣化；#2876 aclnn 接口调用 indexputv2 **未区分 A5 芯片**，导致影响了 A3 的性能（反向问题：代际分支缺失同时伤及旧代际）；ops-math #2148 A5 polar 算子性能达不到预期（Vector 算力 bound 场景仅 0.3x，对标 950DT 486T vs H100 989T）；ops-transformer #5213 MhcPresinkhorn 正向 A5 性能优化。**共性特征：新代际首发适配期，性能路径未完整迁移/未按代际分流，出现「新卡跑不过旧卡」。**
- **关联**：[FP-A17](../FP-A/FP-A17.md)、[FP-B02](../FP-B/FP-B02.md)（同为代际/型号分支遗漏，B02 侧重功能、C06 侧重性能）、[FP-C04](FP-C04.md)。
