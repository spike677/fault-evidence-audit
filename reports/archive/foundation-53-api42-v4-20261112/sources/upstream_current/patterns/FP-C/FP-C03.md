# FP-C03 bf16 与 fp16 性能差异大

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：性能 ｜ 风险：高（S2×O3=6，2026-10-02 复评：#2535、#2993 两条独立实证；乘积已达 6，废除「证据间接」不升档例外） ｜ 状态：活跃

- **元数据**：类别 性能 ｜ 风险 高（S2×O3=6，2026-10-02 复评：#2535、#2993 两条独立实证；乘积已达 6，废除「证据间接」不升档例外）｜ 状态 活跃 ｜ 来源 团队笔记 + CANN issue 检索（2026-09-16）
- **适用**：仓 All ｜ 侧别 Kernel ｜ 载体 Kernel源码 ｜ 触发 bfloat16|bf16|half ｜ 默认启用 true
- **故障机理**：实现中 dtype 特化不完整。
- **触发条件**：双 dtype 支持的算子。
- **典型表现**：两种 dtype 性能差异异常。
- **源码审查映射点**：dtype 特化分支完整性。
- **测试拦截建议**：双 dtype 性能对比基线（与 FP-C02 合并执行）。
- **实证案例**：ops-math #2535 SquaredDifference（910B/DAV2201）**硬件无 BF16 原生算术指令**，公开 Ascend C API 亦无 BF16 Sub/Mul，为还原 TBE 的中间舍入语义须手写 5 次 VCONV 往返（TBE 编译器自动 lowering 仅 3 次），BF16 广播用例性能不达标（[11,41,53,89]→[..,1] bf16：TBE 17.77us vs AscendC 37.74us；多维广播 273.33→698.66us），issue 明示「影响所有需要 BF16 计算的算子」；ops-math #2993 tanh（arch35）FP16/BF16 路径 DAG 存在 `OpCopyIn0Cast`/`OpResultCast` 两个冗余软件 Cast 节点（`LoadAlign`/`StoreAlign` 硬件指令本可完成类型转换），额外寄存器搬运与转换指令开销致性能低于最优，PR #5250 移除冗余节点；同族现象另见 ops-nn #5303 leaky_relu 冗余 Cast DAG（收录于 FP-C02）。**共性特征：FP16/BF16 特化路径残缺（API 缺口/冗余 Cast DAG），致 dtype 间性能差异异常。**
- **关联**：[FP-C02](FP-C02.md)（同一现象的对称面）、[FP-C01](FP-C01.md)。
