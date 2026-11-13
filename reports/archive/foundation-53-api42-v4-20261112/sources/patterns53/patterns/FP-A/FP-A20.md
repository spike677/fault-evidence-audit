# FP-A20 确定性等级未分级标注（「确定/非确定」二元描述掩盖条件确定性）

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：精度 ｜ 风险：高（S2×O3=6，2026-10-02 复评：废除表达型降档例外——表达型已由 S2 体现，#4890 与 rms_norm_grad 核验独立实证支撑 O3） ｜ 状态：活跃

- **元数据**：类别 精度 ｜ 风险 高（S2×O3=6，2026-10-02 复评：废除表达型降档例外——表达型已由 S2 体现，#4890 与 rms_norm_grad 核验独立实证支撑 O3）｜ 状态 活跃 ｜ 来源 rms_norm_grad 跨分支核验（2026-09-13）+ CANN issue 检索（2026-09-16）
- **适用**：仓 All ｜ 侧别 Tiling,Kernel ｜ 载体 Tiling源码,Kernel源码 ｜ 触发 SyncAll|AtomicAdd|ReduceSum ｜ 默认启用 true
- **故障机理**：算子文档/测试结论仅以「确定性算子」「非确定性算子」二元标注，但实际存在**条件确定性**——同一算子不同 tiling 路径、不同输出（如 `dx` 与 `dgamma`）、不同 shape 区间的确定性等级不同。二元描述使测试用例的比对策略（`torch.equal` 严格比对 vs 容差比对）选错：对严格确定的输出用了容差比对 → **掩盖真实缺陷**（假阴性）；对非确定的输出用了 bitwise 比对 → 误报。
- **触发条件**：算子含多条 tiling 路径；同一 kernel 内不同输出走不同归约实现；跨核归约与核内归约混用；测试用例的比对策略按「算子级」而非「输出级 + 路径级」设定。
- **典型表现**：① 该 bitwise 的没 bitwise，缺陷被容差吞掉；② 不该 bitwise 的做了 bitwise，长期误报导致用例被标记为 flaky 后关停；③ 测试结论写「该算子非确定」但线上抱怨「同样输入两次结果不同」而无法复现，实际是特定 shape 才走非确定路径。
- **源码审查映射点**：① 逐**输出**（非逐算子）确定归约方式；② 区分「核内归约」（`ReduceSum<AR/RA>`、二叉树折叠、`WholeReduceSum`）与「跨核归约」（`SyncAll()` 后单核累加、原子加 float、workspace 二次归约）；③ 归约顺序是否依赖**运行时平台参数**（核数、`blockDim`、`vlFp32`）——依赖则非确定；④ 归约切分维度：按**输出不重叠维度**（如 N 轴列切分）切核 = 确定，按**归约维度**（M 轴行切分）切核 = 非确定。
- **检测签名**：搜索 kernel 中的 `SyncAll()` + 后续 `if (blockIdx != 0)` 单核累加模式；搜索 `ReduceSum` 的 `srcShape` 是否包含核数维度（如 `{usedCoreNum, ...}`）；搜索原子加 float 路径。
- **测试拦截建议**：**按「输出 × 路径 × shape 区间」三级矩阵设定比对策略**；严格确定用 `torch.equal`（重复 100 次全等）；数值确定用同 tiling 多次比对 + 跨 tiling 容差；非确定只能容差并**在结论中显式标注触发 shape 区间**；对判定为「确定」的输出，建议在回归中保留 bitwise 用例作看护（一旦失效即暴露实现变更）。
- **实证案例**：ops-nn `norm/rms_norm_grad`（950，2026-09-13）——**同一算子内三种等级并存**：`dx` 两条路径（`RegbaseDxFullLoad` / `RegbaseDxSplitD`）分别用 `ReduceSum<AR>` 与 `ReduceSumImpl`，均**严格确定**；常规 `dgamma` 按 N 轴列切分、核间无交叉归约，**数值确定**；`big_m` `dgamma`（tilingKey 9000/9010）用 `SyncAll()` + 0 核跨核 `ReduceSum<RA>`，且核内累加顺序随 `BasicBlockLoop` 动态变化、参与核数随 M 变化，属**非确定**。若按算子级二元标注为「确定」并对全部输出做 bitwise 比对，big_m 路径用例将误报；反之标注为「非确定」则 dx 的严格确定性看护丢失。补充实证：ops-nn #4890（closed）BatchNorm/BatchNormElemt/BatchNormBackward/GroupNormBackward/RmsNormGrad/RmsNormGradQuant 六算子 A5 文档声明「默认非确定、支持 aclrtCtxSetSysParamOpt 开启」，代码核查实际默认确定性且 tiling 不读取该开关——声明面与行为面整体错位（另收录于 FP-F03）。
- **关联**：[FP-A06](FP-A06.md)（A06 是「确定性开关失效」的缺陷型，本型是「确定性等级描述不足」的表达型，二者互补）、[FP-A02](FP-A02.md)（归约顺序差异）、[FP-A19](FP-A19.md)（多路径是分级的载体）、[FP-C05](../FP-C/FP-C05.md)（确定性场景性能劣化，其前提也是先分清哪些算子是确定的）、[FP-F03](../FP-F/FP-F03.md)（#4890 声明面与行为面整体错位已另录 F03——二元标注掩盖条件确定性，属「文档/声明面与实现面不一致」）。
