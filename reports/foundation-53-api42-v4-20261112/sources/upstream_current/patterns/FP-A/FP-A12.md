# FP-A12 大整数转 fp32 计算精度损失

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：精度 ｜ 风险：中（S3×O1=3） ｜ 状态：活跃

- **元数据**：类别 精度 ｜ 风险 中（S3×O1=3）｜ 状态 活跃 ｜ 来源 团队笔记 + 跨仓扫描
- **适用**：仓 All ｜ 侧别 All ｜ 载体 Tiling源码,Kernel源码 ｜ 触发 static_cast<float>|static_cast<double> ｜ 默认启用 true
- **故障机理**：int64/int32 数值超出 float 24 位尾数精确表示范围（|x|>2^24），转换后参与计算产生偏差；先转后乘与先乘后转的结果不同。
- **姊妹型 A12-1「签名 double、实现 float」**（v6.27）：与主型**方向相反**——主型是「大整数（≥2^24）转 float 丢低位」，丢的是**整数精度**（错值可达 1 个 ULP 的千万倍）；A12-1 是「属性本来就是 `double`，实现用 `static_cast<float>` 收窄」，丢的是**浮点位宽**（相对误差 ~1.2e-7，**通常小于任何算子的精度容差**）。所以**A12-1 单独不构成精度缺陷**，它的价值在另外两件事：① **契约不一致**——`aclnn` 签名对外承诺 `double`，调用方按 double 传非 float 可表示值，实际按 7 位十进制算；② **可静态枚举**——凡是「签名 `double` 形参 + 实现 `static_cast<float>`」的组合都能机器扫出，不必上板。2026-11-06 实测：`ops-transformer` 的 attention 族 **57 个接口里 53 个的 `scale` 是 `double`**，典型 `aclnnBlockSparseAttention`（`aclnn_block_sparse_attention.h:25` `double scaleValue`）在 `block_sparse_attention.cpp:82` 被 `static_cast<float>(scaleValue)` 送进 `OP_ATTR`，而 tiling 侧 `TILING_DATA_FIELD_DEF(float, scaleValue)`（`block_sparse_attention_tiling.h:64`）也按 float 收——**上下游一致地窄了**。**定级口径**：默认 P2（契约/可观测性），只有能构造出「float 与 double 结果差异超出该接口 ST 容差」的输入时才升 P1。
- **触发条件**：大数值索引/计数/求和后转 float 参与计算。
- **典型表现**：大数值场景结果偏差。
- **源码审查映射点**：int64→fp32/int32 转换点、乘法前未升位（先乘后转 vs 先转后乘）。
- **检测签名**：`grep -rnE "static_cast<(float|double)>\([^)]*\bint(32|64)"`；`grep -rn "numeric_limits<int"` 后检查邻近 float 赋值。 **A12-1 签名（v6.27）**：先取「签名里是 `double <name>`」的形状（`grep -nE "aclnnStatus\s+aclnn\w+GetWorkspaceSize" ` 后同段内 `double\s+\w+`），再在实现里找 `static_cast<float>\(<name>\)`；两者同时成立即候选——**不需要上板**。实测基线：`ops-transformer` attention 族 `double scale` 签名 **53 处 / 57 个接口**；但**只有实现了 `static_cast<float>` 的才是 A12-1**（多数接口透传 double 给 tiling），所以必须两步都跑，不能按签名比例推。
- **测试拦截建议**：含 2^24±1、INT32_MAX/MIN 边界值的数值用例。
- **实证案例**：2026-09-05 跨仓追溯扫描 P1 命中 58 处 int→float 截断同源风险点（ops-nn 37 / ops-transformer 14 / ops-math 7），其中部分属本型（具体 issue 归属待逐点复核）。
- **关联**：[FP-A18](FP-A18.md)（同源不同焦点：A12 关注数值计算损失，A18 关注比较语义偏差）。
