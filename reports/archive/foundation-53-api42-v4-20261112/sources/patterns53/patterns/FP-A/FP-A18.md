# FP-A18 int32 边界值转 float 舍入致比较语义偏差

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：精度 ｜ 风险：高（S3×O2=6） ｜ 状态：活跃

- **元数据**：类别 精度 ｜ 风险 高（S3×O2=6）｜ 状态 活跃 ｜ 来源 ops-nn #5562 + 内部缺陷检视记录 2026-09-05
- **适用**：仓 All ｜ 侧别 All ｜ 载体 Tiling源码,Kernel源码 ｜ 触发 numeric_limits<int32_t>|INT32_MAX|INT32_MIN ｜ 默认启用 true
- **故障机理**：`int32` 大整数（>2^24）转 `float` 时尾数位不足，舍入后比较/索引语义偏差。
- **触发条件**：int32 输入接近或超过 2^24；参与比较、索引、阈值判断。
- **典型表现**：边界值用例精度失败或分支选择错误。
- **源码审查映射点**：int32→float 的隐式转换点；比较/索引前的类型提升；`static_cast<float>/<double>(std::numeric_limits<int32_t/int64_t>::min()/max())` 等整型极值转换点；整型值与浮点阈值直接比较；混合 int/float 表达式的隐式提升；标杆参考是否在整数域比较。
- **检测签名**：`static_cast<(float|double)>\(\s*std::numeric_limits<(int32_t|int64_t)>::(min|max)`；`constexpr\s+(float|double)\s+\w*(Min|Max)\w*As(Float|Double)`。（静态扫描 int32 与 float 混合运算处的类型转换；两条正则系拆分时自 master 遗留无标题 v1 卡合并补全，与索引 JSON 保持一致）
- **测试拦截建议**：int32 边界值用例集（2^24 两侧、INT32_MAX/MIN）。
- **实证案例**：ops-nn #5562（int32 边界舍入致比较语义偏差），另 58 处静态扫描命中。ops-nn #5562 / PR !9773 threshold_grad_v2_d 比较语义与标杆不一致——`threshold_grad_v2_d_tiling_arch35.cpp:92-93` 的 `constexpr float int32MinAsFloat/int32MaxAsFloat = static_cast<float>(std::numeric_limits<int32_t>::min()/max())`；golden.py 随修复同步修改，证明 UT 期望值曾按错误实现编写；2026-09-05 跨仓追溯命中 58 处同型风险点（ops-nn 37 / ops-transformer 14 / ops-math 7，P1）。（末段细节自 master 遗留无标题 v1 卡合并）
- **关联**：[FP-A12](FP-A12.md)、[FP-A15](FP-A15.md)、[FP-E01](../FP-E/FP-E01.md)（#5562 的 golden.py 曾按错误实现编写——边界比较语义偏差依赖对比基准正确性，测试有效性面归 E01）。

> 备注：单文件版中本库 FP-A20 卡之后遗留一块无标题的 v1 重复卡（v2.0 转标准卡片时未删除，v2.17 中仍在），拆分时已将其检测签名、映射点与实证细节合并入本卡并消除重复。
