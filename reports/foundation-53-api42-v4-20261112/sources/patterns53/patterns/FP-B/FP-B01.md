# FP-B01 支持面校验过严误拦截合法输入

> [← 库索引](../../README.md) ｜ [变更记录](../../CHANGELOG.md) ｜ 类别：功能/兼容 ｜ 风险：中（S2×O2=4） ｜ 状态：活跃

- **元数据**：类别 功能/兼容 ｜ 风险 中（S2×O2=4）｜ 状态 活跃 ｜ 来源 团队笔记 + 内部缺陷检视记录
- **适用**：仓 All ｜ 侧别 All ｜ 载体 Tiling源码,IR与图配置 ｜ 触发 Not supported|Unsupported|OP_CHECK ｜ 默认启用 true
- **故障机理**：checker 的 dtype/format/shape/quant_mode 白名单硬编码不全或漏登记新支持项，合法输入被错误拒绝。**子型 B01-1（v6.13）：可选输入/可选属性的缺省路径被误判为非法**——Proto 已声明 `OPTIONAL_INPUT`/`OPTIONAL`，但 `CheckNotNull` 无条件要求非空、InferShape 按固定下标读取可选输入、或 checker 不区分「未传」与「传了非法值」，导致合法的缺省调用在第一段接口或图推导阶段即失败。
- **触发条件**：新增 dtype/quant_mode/布局支持后 checker 未同步。
- **典型表现**：合法输入报 Not supported / Unsupported。
- **源码审查映射点**：dtype/format/shape 白名单、硬编码校验清单与实际支持面的一致性；新支持项合入时 checker 是否同步放开。
- **控制变量（v6.30）**：**必须固定**——保持同一 SoC / 同一 CANN / 同一编译选项，只把**一个**参数推到「合法但接近上限」的一侧；对照组必须用同版本、同编译产物 ｜ **允许变动**——单个参数的取值 ｜ **多变量同变的典型误判**——把「该被拒的非法输入」与「该被收的合法极值」混在同一批里跑 → 分不清是过严还是过松；换 SoC 后 features 表不同，旧结论不可复用
- **测试拦截建议**：每次放开新支持项后，二级冒烟必跑该 dtype/模式全矩阵（正反向）。
- **实证案例**：ops-transformer #4934 / PR !11201 quant_flash_attention quantmode=6 被 checker 硬编码白名单错误拦截（含 Not supported/Unsupported 关键词误判），放开校验 + 资料同步 + 二级冒烟验证。 **v6.13 补（子型 B01-1，均 closed）**：**ops-cv #1091**（closed+resolved，"对应 PR 已经合入"）SpatialTransformer 的 `theta` 在 proto 与 AICPU op-def 中均为可选输入，但 kernel 无条件检查第二输入，`use_default_theta` 六项全 1 且 `default_theta` 完整的合法 default-only 调用返回参数错误；**ops-nn #5069**（closed+resolved）aclnnModulate 把可选 `scale`/`shift` 无条件判为非法。判定要点：先确认该输入/属性在 Proto 里确实是 `OPTIONAL`，再看「省略」是否被当成「空指针错误」——二者混用即为本型。
- **关联**：**「不该拦却拦」与「该拦不拦」的完整分工（v2.16 扩写）**——本卡只承载**过拦**方向；**漏拦方向按机理拆到四条，不另立「支持面校验缺失」通用条目**（否则四条会与新条目互相抢料、维护者无从打标）：[FP-B03](FP-B03.md)（跨仓迁移丢失防御/拦截逻辑，含「校验被显式跳过」）、[FP-B04](FP-B04.md)（aclnn 必选入参空指针校验缺失）、[FP-B05](FP-B05.md)（入参校验覆盖度参差，同仓文件级）、[FP-B06](FP-B06.md)（空 tensor（numel==0）输入分支处理缺失）。判定「漏拦 / 该拦不拦」类问题时，**先问是哪一种机理（迁移丢失 / 指针 / 覆盖度 / 空输入），再打对应标签**。
