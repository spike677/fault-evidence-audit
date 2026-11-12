# FP-A10 原型 Attr 不支持 Double

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：精度 ｜ 风险：高（S3×O3=9，2026-10-02 复评：#1952、#2006 两条独立实证，O2→O3） ｜ 状态：活跃

- **元数据**：类别 精度 ｜ 风险 高（S3×O3=9，2026-10-02 复评：#1952、#2006 两条独立实证，O2→O3）｜ 状态 活跃 ｜ 来源 团队笔记
- **适用**：仓 All ｜ 侧别 All ｜ 载体 IR与图配置 ｜ 触发 GetAttrPointer|Attr ｜ 默认启用 true
- **故障机理**：算子原型（proto）Attr 类型不含 double，或解析分支静默降级为 float，精度丢失。
- **触发条件**：含标量 attr（scale/eps/阈值）且用户传入 double。
- **典型表现**：Double 数据类型精度问题。
- **源码审查映射点**：Attr 解析分支中 double 类型的支持与静默降级。
- **测试拦截建议**：attr 传高精度敏感值（如 1e-8 级 eps）边界用例。
- **实证案例**：ops-transformer #1952 qkv_rms_norm_rope_cache 在 aclnn 侧**没有把传入的 epsilon 从 double 转换成 float**，导致特定场景精度问题（910C，输入取值范围 [-1e-10, 1e-10]；日志显示 `[Epsilon Debug] Interpreted as 32-bit float: 0.000000000000000e+00`——double 未转换致下溢为 0，精度直接失效）；ops-math #2006 truncate_div 在 tensor/scalar 的 **fp16/double 场景**下精度丢失。**共性特征：double 标量 attr 未做显式转换/未纳入 proto Attr 类型定义，静默降级致精度失效。**
- **关联**：[FP-A11](FP-A11.md)、[FP-A13](FP-A13.md)（同源于「高精度值在低精度链路上被静默降级」，A13 侧重输入预处理截断）。
