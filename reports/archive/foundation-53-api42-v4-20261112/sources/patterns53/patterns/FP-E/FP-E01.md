# FP-E01 golden/UT 期望值失配或按错误实现编写

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：测试有效性 ｜ 风险：高（S3×O3=9） ｜ 状态：活跃

- **元数据**：类别 测试有效性 ｜ 风险 高（S3×O3=9）｜ 状态 活跃 ｜ 来源 内部缺陷检视记录（v2.0 新增）
- **适用**：仓 All ｜ 侧别 All ｜ 载体 UT与golden资产 ｜ 触发 golden ｜ 默认启用 true
- **故障机理**：① golden 生成脚本与用例命名/约定失配，精度验证静默失效（用例永远通过）；② golden 按（曾经的错误）实现逆向编写，缺陷被 UT「合法化」——修复 PR 中 golden 与实现同步修改即是强信号。
- **触发条件**：测试基础设施代码（golden.py、st csv）与用例演进不同步；缺陷修复未审视 golden 正确性。
- **典型表现**：精度验证静默失效；修复 PR 的 diff 中 golden 与实现同时修改。
- **源码审查映射点**：`tests/asserts/golden*.py` 与 st csv 约定名匹配复核；修复类 PR 的 diff 中 golden 与实现是否同步改动（同步改动 = 历史 golden 按错误实现编写的强信号）。
- **检测签名**：golden 文件名/约定名与用例集命名的自动比对扫描（参考例行缺陷检视中的 golden 失配扫描）。
- **测试拦截建议**：golden 必须由独立参考实现（numpy/torch CPU）生成而非待测实现回放；golden-用例失配纳入 CI 静态扫描。
- **实证案例**：ops-math #3048 / PR !5384 DiagV2 kernel 模式 golden 命名与用例命名失配，精度验证静默失效（golden.py + st csv 整改）；ops-nn #5562 golden.py 随修复同步修改，证明 UT 期望值曾按错误实现编写；ops-nn #5635 11 个 foreach/scatter/lamb 算子 TTK golden 四类缺陷致精度结论失真（①空张量崩溃与算子 no-op 口径不一致；②整型入参强转 fp32 静默丢位，`2^30+100`→`2^30+128`，整型精度结论从未被验证；③golden 与三方标杆逐位相等致双标杆塌陷、RMSE 比值分母失效产生与 NPU 无关的假红；④三方 compose 与被测内核中间量精度/运算序列不对等，竞品凭空更准把内核判成缺陷）；ops-nn #4483 中 23 个算子 golden.py 为 numpy 纯公式（违反 golden 红线 R3），与被测 kernel 同类有损、把精度短板伪装成达标，另有整型走 fp32 尾数不足、Python min/max 静默丢 NaN、除法未做 Subnormal FTZ 等参照失真。
- **关联**：[FP-A04](../FP-A/FP-A04.md)、[FP-A13](../FP-A/FP-A13.md)、[FP-A18](../FP-A/FP-A18.md)、[FP-E02](FP-E02.md)（E01 是 golden 本身错，E02 是判据/标杆口径设计错——二者常叠加放大）。
