# FP-D02 aclnn 内存占用高于 aclop

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：资源/内存 ｜ 风险：中（S1×O3=3，2026-10-02 复评：#5033、#3606 两条独立实证，O2→O3） ｜ 状态：活跃

- **元数据**：类别 资源/内存 ｜ 风险 中（S1×O3=3，2026-10-02 复评：#5033、#3606 两条独立实证，O2→O3）｜ 状态 活跃 ｜ 来源 团队笔记
- **适用**：仓 All ｜ 侧别 Host ｜ 载体 aclnn源码 ｜ 触发 workspace|GetWorkspaceSize ｜ 默认启用 true
- **故障机理**：workspace/中间 tensor 复用逻辑缺失、lifetime 分析缺失。
- **触发条件**：同一算子 aclop 与 aclnn 双路径对比。
- **典型表现**：aclnn 路径内存占用偏高。
- **源码审查映射点**：workspace/中间 tensor 复用逻辑、lifetime 分析。
- **测试拦截建议**：双路径峰值内存对比基线。
- **实证案例**：ops-nn #5033 **aclnnMatmul 部分场景内存 A5 比 A2 大**（非量化 cube 模板**无效内存占用**，用 `torch.npu.memory_allocated` 前后打点量化，期望「算子内存 A5 不比 A2 差」）；ops-transformer #3606 MegaMoe A2 **Workspace 占用比例大**，可优化项明确列出（gmm2/gmm1 复用输出地址、非量化场景不再申请 scale workspace、删除未使用的 `ptrTokenPerExpert` 块、W4A8 场景取消未使用的 GMM 切分）。**共性特征：优化手段高度一致——地址复用 + 删除未使用块 + 按场景裁剪申请；证明 aclnn/新模板路径的内存申请普遍缺少 lifetime 分析与场景化裁剪。**
- **关联**：[FP-A16](../FP-A/FP-A16.md)（同属双路径对比类：A16 比精度、D02 比内存）、[FP-D01](FP-D01.md)。
