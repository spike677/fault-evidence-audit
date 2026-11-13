# FP-A08 切块粒度差异致离群点精度问题

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：精度 ｜ 风险：高（S3×O3=9） ｜ 状态：活跃

- **元数据**：类别 精度 ｜ 风险 高（S3×O3=9）｜ 状态 活跃 ｜ 来源 团队笔记
- **适用**：仓 All ｜ 侧别 Tiling,Kernel ｜ 载体 Tiling源码,Kernel源码 ｜ 触发 tileSize|tileNum|Tail|tail ｜ 默认启用 true
- **故障机理**：不同切块大小下浮点归约分组不同；尾块 padding 值参与计算引入偏差。
- **触发条件**：极端 shape、离群点数据、尾块场景。
- **典型表现**：离群点/极端 shape 下精度失败。
- **源码审查映射点**：切块大小计算、尾块处理、padding 值选择。
- **测试拦截建议**：同 shape 换 tiling 粒度对比；含 ±inf/极大极小值的离群点用例。
- **实证案例**：ops-nn #5519 aclnnBatchMatMul fp32 且 K=65533（紧贴 ND2NZ on-the-fly 上限 65535）时**尾块路径**精度超阈（相对误差比例 3.099 > 阈值 2.0）；#3391 slice 场景 m 方向**尾块切块 slicem 对齐**与负载均衡修复；#5061 conv2d FM 非全载 Cin 尾块计算错误；#3281 Conv weightUb 模板 K 轴尾块处理异常；#5138 singlecorebatch 尾块、尾核场景；#3273 尾核尾块场景 L0B 全载 weight 时搬进搬出指令偏移错误；#4239 dynamic_quant 尾块场景精度不达标；ops-transformer #3081 AllGatherMatmulV2 尾块 `preCoreNum` 未清零致某些 shape 的 UpdateBasicIndex 计算 index 时 uint64_t 负数溢出。**共性特征：缺陷集中在「尾块/尾核」这一非对齐边界，而非均匀主块。**
- **参考实现前置（v6.30）**：判 aclnn 层必须用 `golden.py` 的 `__golden__["aclnn"]` 入口；只有 `kernel` 入口时**不得**用于 aclnn 层判定（层间 dtype/校验/布局差异会被误判成算子缺陷）；连 `aclnn` 入口都没有时记「判据不成立」而非「未覆盖」。实测 `ops-nn` 全仓 362 个 `golden.py` 仅 **80 个（22.1%）**含 `aclnn` 键——见 [EVIDENCE_DISCIPLINE.md](../../EVIDENCE_DISCIPLINE.md) D12/D13。
- **关联**：[FP-A02](FP-A02.md)、[FP-A05](FP-A05.md)、[FP-A07](FP-A07.md)。
