# FP-A19 同算子多 tiling 路径覆盖盲区（新增路径未纳入测试矩阵）

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：精度 ｜ 风险：高（S3×O2=6） ｜ 状态：活跃

- **元数据**：类别 精度 ｜ 风险 高（S3×O2=6）｜ 状态 活跃 ｜ 来源 rms_norm_grad 跨分支核验（2026-09-13）
- **适用**：仓 All ｜ 侧别 Tiling,Kernel ｜ 载体 Tiling源码,Kernel源码 ｜ 触发 REGISTER_TILING_TEMPLATE|IsCapable ｜ 默认启用 true
- **故障机理**：算子在同一平台上注册**多条 tiling 模板**（按 `REGISTER_TILING_TEMPLATE` 的优先级数字决定尝试顺序），各模板由其 `IsCapable()` 的 shape 阈值分流。新版本引入新模板时，**两条路径可能一条确定、一条非确定**，或归约实现不同（核内二叉树折叠 vs 跨核两段归约）。若测试用例的 shape 全部落在旧路径一侧，新路径**永远不被执行**，缺陷长期潜伏。
- **触发条件**：算子存在按 shape 阈值分流的多 tiling 模板；版本升级新增/修改了其中一条模板；测试 shape 分布集中在单一侧；分流阈值依赖平台参数（`vlFp32`、`aivCoreNum`、`UB_SIZE`）故**跨平台阈值不同**。
- **典型表现**：新路径在线上被特定 shape 触发后精度异常/结果不确定，而测试全绿；同一 shape 在 A 平台走路径 1、B 平台走路径 2 而表现不同，跨代际对比困难。
- **源码审查映射点**：① `REGISTER_TILING_TEMPLATE(op, Cls, PRIORITY)` 的**优先级数字**（越小越先尝试）；② 各模板 `IsCapable()` 的**全部阈值表达式**及其中引用的平台常量；③ 模板内 `DoOpTiling()` 里**二次能力检查**（不通过会返回 `GRAPH_PARAM_INVALID` 回退，形成隐式第三态）；④ 各路径 kernel 侧的归约方式差异（是否有 `SyncAll()` / 跨核 `ReduceSum` / 原子加）。
- **检测签名**：`git grep -n "REGISTER_TILING_TEMPLATE"` 定位多模板算子；对比 `IsCapable()` 中的 `return false` 分支收集阈值；跨分支 `diff` 新增的 `*_big_m_tiling.cpp` / `*_tail_tiling.cpp` 类文件。
- **测试拦截建议**：**按阈值两侧构造对照用例**（阈值 ±1、恰好命中、恰好不命中），而非随机 shape；建立「模板 → 触发 shape 区间 → 覆盖用例」映射表并纳入 CI；版本升级后**对比新旧分支的模板清单**，新增模板必须补齐用例；同 shape 跨平台验证是否命中同一 `tilingKey`。
- **实证案例**：ops-nn `norm/rms_norm_grad` 跨分支核验（2026-09-13）——`RmsNormGradBigMTiling`（优先级 100）在 **9.1.0 才引入**，8.5.0 无此文件；其 `IsCapable()` 要求 `rows_ >= 64×aivCoreNum/2`（950 上即 **M ≥ 2048**）且 `rows_ >= 2×cols_`。该路径的 dgamma 采用 `SyncAll()` + 0 核跨核 `ReduceSum<RA>`（非确定），而常规 `RmsNormGradRegbaseTiling`（优先级 200）按列切分、核间无交叉归约（数值确定）。**若测试 shape 的 M 全部 < 2048，则 big_m 路径 0 覆盖**。另：`9.1.0 → 9.2.0` 该文件 diff 全为格式化改动，阈值自引入起未变——说明**阈值稳定但版本引入点明确**，覆盖缺口不会随版本自然消失。
- **关联**：[FP-A06](FP-A06.md)（新路径的非确定性正是 A06 的一个具体来源）、[FP-A07](FP-A07.md)（阈值边界写错 = A07）、[FP-A08](FP-A08.md)（切块粒度致归约分组不同）、[FP-B02](../FP-B/FP-B02.md)（阈值依赖芯片核数、跨平台不一致）。
