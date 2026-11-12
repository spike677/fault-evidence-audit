# FP-A04 功能问题演变为精度静默故障

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：精度 ｜ 风险：高（S3×O3=9，2026-10-02 复评：ops-math 空分组簇（#3044/#2867/#5590）与 ops-transformer #3799 两类独立实证，O2→O3） ｜ 状态：活跃

- **元数据**：类别 精度 ｜ 风险 高（S3×O3=9，2026-10-02 复评：ops-math 空分组簇（#3044/#2867/#5590）与 ops-transformer #3799 两类独立实证，O2→O3）｜ 状态 活跃 ｜ 来源 团队笔记
- **适用**：仓 All ｜ 侧别 All ｜ 载体 Tiling源码,Kernel源码 ｜ 触发 OP_LOGE|GRAPH_SUCCESS|return false ｜ 默认启用 true
- **故障机理**：错误分支吞掉返回值或输出部分结果而不报错，错误以数值偏差形式静默流出。
- **触发条件**：异常分支、tiling 不匹配时的降级路径、部分失败未中断。
- **典型表现**：静默出错数值、无报错。
- **源码审查映射点**：错误分支是否静默吞掉返回部分结果而非报错。
- **测试拦截建议**：错误注入用例（非法输入必须报错而非出数）；输出 NaN/inf 哨兵检查。
- **实证案例**：ops-math #3044 / #2867 / #5590（9.2.0-beta.2）reduction Group 模板 `rGroupCnt > rOuter` 产生空分组，对应核早退不写 workspace 行，Phase2 却以 `rGroupCnt` 全行 Reduce 把未写入的**脏 GM 数据**当 partial sum 读入，**不报错地**输出 NaN/超大值（data_compare、reduce_std_v2_update、bn_training_reduce、euclidean_norm、act_ulq_clamp_max_grad、act_ulq_clamp_min_grad 多算子同源；master 已由 cann/ops-math!5068 修复，issue 用于跟踪分支同步）；ops-transformer #3799 `chunk_gated_delta_rule_tiling.cpp:83-86` `GetPlatformInfo()` 空实现恒返回 `GRAPH_SUCCESS`，`InitCompileInfo()`（L64-81）出错仅 `OP_LOGE` 后 `return`，**错误状态无法传出**，后续 `SetBlockDim(0)` 进入未定义行为（关联 PR 8802）。**共性特征：错误分支不是返回错误码而是「静默早退 + 继续执行」，错误以数值偏差形式流出。**
- **关联**：[FP-B03](../FP-B/FP-B03.md)、[FP-E01](../FP-E/FP-E01.md)、[FP-A05](FP-A05.md)（同为脏数据/未初始化数据被当作有效输入读入，A04 侧重「不报错」，A05 侧重「数据源本身脏」）。
