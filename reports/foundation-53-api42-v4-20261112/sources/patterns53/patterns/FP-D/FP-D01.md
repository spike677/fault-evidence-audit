# FP-D01 GPU 迁移 NPU 场景显存过度占用

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：资源/内存 ｜ 风险：高（S2×O3=6，2026-10-02 复评：#408、#4932、#4021、#4001 四条独立实证，O2→O3） ｜ 状态：活跃

- **元数据**：类别 资源/内存 ｜ 风险 高（S2×O3=6，2026-10-02 复评：#408、#4932、#4021、#4001 四条独立实证，O2→O3）｜ 状态 活跃 ｜ 来源 团队笔记
- **适用**：仓 All ｜ 侧别 Tiling ｜ 载体 Tiling源码 ｜ 触发 workspace|GetWorkspaceSize ｜ 默认启用 true
- **故障机理**：workspace 大小计算过大、内存未复用、缓存未设上限；**图模式（aclGraph / 条件算子）下的内存申请路径未纳入容量评估**（v2.13 增补）。
- **触发条件**：GPU 训练 / 推理脚本直接迁移到 NPU；**aclGraph 等图模式下经条件算子触发的内存申请**（v2.13 增补——原卡片仅覆盖迁移场景，遗漏图模式申请路径）。
- **典型表现**：网络无法正常训练或推理（OOM）。
- **源码审查映射点**：workspace 大小计算、内存复用、缓存上限。
- **测试拦截建议**：峰值显存基线看护；大 batch/长序列场景内存压测。
- **实证案例**：ops-nn #408 FusedLinearCrossEntropyLossGrad **省显存分支申请了超出所需的显存大小**——tiling 计算 workspace 时最后两块 buffer 在不同流水下视图一致、不涉及 double buffer，却按双倍申请（A2/A3，期望 shape "4196,7168;64640,7168" 下约 2.5G）；#4932 embeddingdensegrad 使用 `zerolike` 导致 OOM，在 OOM 包下走 aclnn 通路 aicerror；#4021 max_pool3d_grad_with_argmax aclnn 接口内存检测时 OOM；#4001 dynamic_mx_quant 跑 OOM 报错。**共性特征：workspace/buffer 申请量按「最坏情况或错误假设」估算，未做复用与生命周期分析，属 tiling 侧可精确修复的问题。**
- **关联**：[FP-D02](FP-D02.md)（同源：均指向 workspace 计算与内存复用缺失，D01 关注迁移场景的绝对值超限，D02 关注双路径对比的相对值）、[FP-A05](../FP-A/FP-A05.md)。
