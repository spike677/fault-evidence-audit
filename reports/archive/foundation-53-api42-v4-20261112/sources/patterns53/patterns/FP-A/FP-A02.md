# FP-A02 归约/累加实现顺序与竞品不一致

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：精度 ｜ 风险：高（S3×O3=9） ｜ 状态：活跃

- **元数据**：类别 精度 ｜ 风险 高（S3×O3=9）｜ 状态 活跃 ｜ 来源 团队笔记 + 内部缺陷检视记录
- **适用**：仓 All ｜ 侧别 Kernel ｜ 载体 Kernel源码 ｜ 触发 ReduceSum|WholeReduceSum|BlockReduce|ReduceMax ｜ 默认启用 true
- **故障机理**：浮点加法不满足结合律，二分归并式求和 vs 顺序累加、多核并行归约的分组顺序差异引入可复现偏差；性能优化重排结合顺序会放大该差异。
- **触发条件**：大规模归约（sum/mean/norm 梯度类）、多核并行归约、性能优化改写计算拓扑。
- **典型表现**：网络精度波动、精度差异、EVB 精度失败。
- **源码审查映射点**：归约/累加实现顺序；大规模求和的树形归约 vs 串行累加；性能优化 PR 是否改变浮点结合顺序。
- **测试拦截建议**：同输入多轮执行结果一致性；与标杆实现逐元素 utol 且覆盖大 shape 归纳场景。
- **实证案例**：ops-nn #5560 RmsNormGrad dx 计算顺序与 PyTorch CUDA 不一致（PR !9873，Reg::Axpy 对齐标杆拓扑修复）；ops-nn #5537 SwigluMxQuant EVB 精度失败——性能优化改变浮点结合顺序（PR #9828 已修）。
**索引类输出不得比 bit**：离散选择输出（TopK 索引 / ArgMax）在输入并列时逐轮不同，会被误判成「归约顺序未固定」——见 [EVIDENCE_DISCIPLINE.md](../../EVIDENCE_DISCIPLINE.md) D11。
- **关联**：[FP-A06](FP-A06.md)、[FP-A08](FP-A08.md)。
