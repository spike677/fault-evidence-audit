---
name: "fpb04-aclnn-review"
description: "基于 FP-B04「aclnn 必选入参空指针校验缺失」故障模式对指定 aclnn 接口做源码检视：定位算子实现，按必选参数判空矩阵、共享校验函数自校验、校验先于使用、校验命中即返回等清单核查，产出证据链与 S×O 定级报告。当用户给出接口名要求做空指针、nullptr、SIGSEGV、rc=139 或校验缺失排查时使用。"
---

# FP-B04 aclnn 接口检视（fpb04-aclnn-review）

对用户指定的 aclnn 接口（如 aclnnFusedQuantMatmul）做 FP-B04 专项源码检视：先定位算子实现，再按清单逐项核查，每个结论给出**文件 + 行号 + 推导链**证据，命中即出 Bug 卡，输出检视报告。**本模式特殊纪律：① 卡片适用声明为「必须触发」——不依赖签名命中，对被检接口无条件执行判空清单（`nullptr` 探针面全量过一遍）；② 判定口径只覆盖**必选**入参——可选参数（`Optional` 后缀）传 `nullptr` 是合法用法，不算缺陷，必选性以接口签名与 `docs/aclnn*.md` 约束说明为准；③ 「校验写了但命中不 return」与「未校验」同族，审查须跟踪校验命中后的控制流；④ 崩溃与否、错误码实际取值需运行时探针确认——静态只能立「无判空的解引用路径」。**

## 0. 与相邻模式的边界

| 相邻模式 | 分工 |
|---|---|
| FP-B06（空 tensor 分支缺失） | **最易混淆项**：B04 是**指针本身为空**（`nullptr`）；B06 是指针有效但**元素数为 0**（`numel==0`）的语义分支缺失。两者可共现于同一 `CheckParams`，探针用例须分别构造 |
| FP-B01（过拦） | 方向相反：B01 拦了**不该拦的合法输入**；B04 该拦没拦 |
| FP-B03（迁移丢失防御） | 成因层面：迁移丢失的防御逻辑中常含空指针拦截；B04 是「防御缺失」在 aclnn 层的通用形态，不限迁移场景 |
| FP-B05（校验覆盖度参差） | B05 是**文件级**范差（有无校验骨架）；B04 聚焦**单接口内**「校验存在但漏参数 / 晚 / 不生效」 |
| FP-A04（静默错误） | 未拦截若未崩溃则演变为静默错误结果——B04 是「响」面（SIGSEGV），A04 是「静」面 |
| FP-G01（挂死） | SIGSEGV 有退出码地终止；G01 是不返回地卡住，以「是否终止」分 |

**症状反查定位**：SIGSEGV / rc=139 必现 → 首查入口解引用点；gdb 栈落在 `strcmp` / `GetDataType` / `ToFloat` / `GetData` → 共享校验函数不自校验或先用后校验；返回 **561103** 而非 161001 → 错误码面缺陷（易被误判为「已校验」而漏提）；透传 GE/tiling 后才 coredump → 校验位置晚于首次解引用。

## 1. FP-B04 模式卡摘要（检视依据，源自本库 `patterns/FP-B/FP-B04.md`，v3.1）

- **编号 / 名称**：FP-B04 aclnn 必选入参空指针校验缺失 ｜ **类别**：功能/兼容 ｜ **风险**：高（S2×O3=6）｜ **状态**：活跃
- **适用声明头**（照抄卡片）：仓 All ｜ 侧别 Host ｜ 载体 aclnn源码 ｜ 触发 必须触发 ｜ 默认启用 true
- **skill 核查面**：侧别 Host——skill 落地为 `op_api/aclnn_*.cpp` 的两段式公开入口与被多入口共享的静态校验函数；延伸至 tiling / infershape 中 `GetData()` 返回值与属性字符串指针的判空（卡片映射点列明）
- **故障机理**：aclnn 两段式接口（GetWorkspaceSize / Execute）对必选入参（输入 tensor、scalar、属性数组、属性字符串）未做 `nullptr` 拦截即向下透传，下游解引用空地址。典型成因：适配层由模板脚本生成导致校验宏漏插；多接口共享的公共校验函数内直接解引用（如 `strcmp`），入口仅校验了部分参数；校验位置晚于首次解引用；tiling / infershape 层 `GetData()` 返回值未判空。
- **触发条件**：任一必选入参传 `nullptr`；GetWorkspaceSize 或 Execute 阶段任一阶段；尤其易发于共享校验函数被多入口复用的算子族。
- **典型表现**：**SIGSEGV（rc=139，必现）**；或算子侧未拦截透传给 GE/tiling 后 coredump；或返回非 161001 的错误码（如 561103）——后者易被误判为「已校验」而漏提缺陷。
- **源码审查映射点**：`GetWorkspaceSize` 入口的参数解引用点（`strcmp`/`GetDataType`/`ToFloat` 等）是否前置了 `OP_CHECK_NULL`；多入口共享的公共校验函数（如 `CheckFusedOpType`）内部是否自校验，而非依赖各入口分别校验；`CheckParams` 中 `CHECK_RET(..., ACLNN_ERR_PARAM_NULLPTR)` 是否覆盖全部必选参数；tiling / infershape 中 `GetData()` 返回值、属性字符串指针是否判空；校验顺序（是否存在「先用后校验」）。
- **测试拦截建议**：`nullptr` 探针用例覆盖「算子 × 入参位置 × 两段式阶段」全矩阵；判读 rc=139（崩溃）/ 1（断言 FAIL）= 缺陷存在，期望返回 `161001`（`ACLNN_ERR_PARAM_NULLPTR`）；特别针对共享校验函数的算子族，须逐个入口独立置空验证（不可只测其中一个入口）；gdb 取栈定位解引用点。
- **实证案例**：ops-nn #5531 / #5532 `aclnnFusedQuantMatmulWeightNz` 与 `aclnnFusedQuantMatmul` 共享 `CheckFusedOpType`，入口仅 `OP_CHECK_NULL(x1/x2)`，`fusedOpType=nullptr` 触发 SIGSEGV（gdb 栈 `strcmp → aclnnFusedQuantMatmulGetWorkspaceSizeCommonProcess`），期望 161001 实测 rc=139；#5372 / #5373 同根因另有两次记录（**同一根因四连发**）；#4784 fqmm x1/x2 空指针**校验过晚** Segmentation Fault；#4586 wqbmm 在空指针校验**前**通过 x1 调用函数致 coredump；#5644 `biasSizes=nullptr` 未拦截透传 GE 致 coredump（环境 **950**）；#5329 foreach 系列缺少 tensor list 空指针校验；#3383 aclnn_add_rms_norm_quant_v2 缺校验；#4555 aclnnBatchNorm 空 input + nullptr saveMean/saveInvstd 触发 core dump；#4697 GRU 传 nullptr coredump；#1293 aclnnIndexCopy 部分空指针未校验致多线程报错。ops-cv #912/#842/#294/#491/#295（Upsample 系列 `outputSize` 数组、GridSampler3D）、#852（NMS）、#221（IouV2 **先使用 attrs 后检验**）；ops-math #2776（`aclnn_logdet.cpp:165`）等「空指针解引用」批量审计 #2762–#2777、#864（exp/sqrt 缺校验 coredump）、#2501（aclnnArange 预期 161001 实测 561103）；ops-transformer #4516/#4375/#4216/#4728（grouped_matmul 系列、BSAG、FAG 的 `layout` 类属性字符串）。补充变体：ops-nn #5705（closed）convolution_forward `CheckDisContinuousStride` 校验命中后仅 `OP_LOGE` **缺 return**，防御形同虚设，后续按 `dims` 访问 vector 越界 UB——「校验写了但未生效」与「未校验」同族，审查时须核对校验命中后的控制流。
- **关联**：FP-B03、FP-B01（方向相反）、FP-A04（未拦截若未崩溃则演变为静默错误结果）、FP-B05。

## 2. 检视输入与算子定位

**输入**：aclnn 接口名（必填，如 `aclnnFusedQuantMatmul`）；可选 ref（默认 master）、指定仓（默认自动定位）；可选现象描述（崩溃栈 / 实测错误码——用于症状反查）；可选参数清单（接口含多入口时逐入口核对）。

**接口名 → 算子目录换算**：去 `aclnn` 前缀 + 驼峰转下划线小写：
`aclnnFusedQuantMatmul → fused_quant_mat_mul`、`aclnnInplaceMaskedScatter → inplace_masked_scatter`（若目录名带 inplace 而接口族共用目录，以目录列表为准，如 masked_scatter）。

**仓定位顺序**（GitCode `cann` 组织，逐仓用目录列表确认）：`ops-nn`（norm/loss/activation/matmul/index 类）→ `ops-math`（math/conversion 类）→ `ops-cv`（image/vision 类）→ `ops-transformer`（attention/moe 类）。**类目名不总与直觉一致**，以目录列表为准。FP-B04 高发面：多入口共享静态校验函数的算子族（fused / 组合类命名）、带属性字符串或属性数组入参的接口（`layout` 类）、tensor list 类入参（foreach 系列）、由模板脚本生成适配层的接口。

**算子目录结构约定**（已验证示例 `cann/ops-nn` → `matmul/fused_quant_mat_mul/`；注意 `op_api` 的实际位置随算子而异——fused_quant_mat_mul 在 `op_host/op_api/`，masked_scatter 在顶层 `op_api/`，以目录列表为准）：

```text
{类别}/{op_name}/
├── op_api/（或 op_host/op_api/）  # aclnn_*.cpp——两段式公开入口 + 共享静态校验函数：主检视面
├── op_host/                  # def / infershape / tiling——GetData() 与属性指针判空的延伸面
├── docs/                     # aclnn*.md——必选性（空指针约束）与判空行为的文档依据
└── examples/ tests/
```

## 3. 取数方式（Important）

公开网页端点被拦截，**必须走 API**（均需带 `User-Agent`；失败重试 2 次、间隔 5 秒）：

| 用途 | 端点 |
|---|---|
| 目录列表 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/contents/{path}?ref={ref}` |
| 单文件内容 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/raw/{path}?ref={ref}` |
| Issue 查重 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/issues?q={关键词}` |

**已实测不可用（截至 2026-09 实测）**：`https://gitcode.com/{repo}/raw/{sha}/{path}`、`https://raw.gitcode.com/...` → 403 或拦截页；端点策略如有变化可复测。若本地已有算子仓克隆，优先直接读本地文件，行号证据以本地 HEAD 为准并记录 commit。**本模式特有取数限制**：崩溃是否实际发生、错误码实际取值、gdb 栈均需**运行时探针**取证——静态检视产出「无判空的解引用路径」与「探针方案」，不可把静态缺失直接表述为「必现 SIGSEGV」；实证引用的 gdb 栈以 issue 原文为准，不复述为本仓测量结果。

## 4. 判空与可选输出检视清单（①~⑧ 必选入参判空；⑨ 可选输出反向依赖）

对 `aclnn_*.cpp` 全部入口与共享静态函数逐点核查，**每点先查命中面、再做反证排除**，已有的判空防护也要记录（防护面证据）。

### ① 入口逐参数判空覆盖矩阵
- 查什么：`GetWorkspaceSize` 公开入口对**每个**参数（必选输入 tensor、inplace tensor、scalar、属性数组、属性字符串、出参 `workspaceSize`/`executor`）是否有判空；可选参数（`Optional` 后缀）传 `nullptr` 属合法，不纳入缺陷。
- 何处：公开入口函数体开头到首个向下透传调用之间；必选性以接口签名与 `docs/aclnn*.md` 约束说明（如「传入的 xxx 是空指针」→ 161001）交叉确认。
- 命中判据：任一必选参数在判空前即被解引用或透传到会解引用的函数 ⇒ 命中（给出「参数 → 首次使用行 → 判空行（或缺失）」对表）。

### ② 共享校验函数自校验性
- 查什么：被多入口复用的静态校验函数（`CheckFusedOpType` / `CheckXxxType` 类）**内部**是否直接解引用形参（`strcmp` / `GetDataType` / `ToFloat`），而不做自校验——此时函数正确性完全依赖每个调用入口先行判空，任一入口漏判即崩溃。
- 何处：`static` 校验函数定义体；`std::get` 解包元组后直传参数的公共处理函数（CommonProcess 类）。
- 命中判据：函数体内存在对形参的无判空解引用，且存在至少一个调用入口未先行判空同一参数 ⇒ 命中（实证样板 #5531/#5532 同根因四连发）。

### ③ 校验先于首次使用（先用后校验）
- 查什么：判空语句与其保护参数的**首次解引用 / 首次透传**的相对位置——「先用后校验」使校验形同虚设（实证 #4586 wqbmm 在校验前通过 x1 调用函数、#221 IouV2 先使用 attrs 后检验）。
- 何处：入口内从函数开头起的语句顺序；`L2_DFX_PHASE_1` 等日志宏内部的参数解引用也要计入「使用」。
- 命中判据：存在「使用行号 < 判空行号」的参数 ⇒ 命中。

### ④ 校验命中后的控制流完整性
- 查什么：判空 / 校验**命中分支**是否携带有效控制流——`OP_LOGE` 后是否 `return`（错误码或 false）；#5705 变体：校验命中后仅打日志继续执行，防御形同虚设，后续按非法值访问越界 UB。
- 何处：所有 `if (xxx == nullptr)` / `CHECK_RET` 命中分支的函数体。
- 命中判据：命中分支无 `return`（或 `return` 后仍有使用该参数的路径可达）⇒ 命中。

### ⑤ CheckParams 覆盖度与错误码正确性
- 查什么：`CheckParams` 中 `CHECK_RET(..., ACLNN_ERR_PARAM_NULLPTR)` 是否覆盖全部必选参数；拦截后返回的错误码是否为 161001——返回 561103 等「看起来拦了」的错误码仍属错误码面缺陷（实证 #2501 Arange 预期 161001 实测 561103），易被误判为已校验而漏提。
- 何处：`CheckParams` 与各校验函数的错误码取值点。
- 命中判据：必选参数无对应 `ACLNN_ERR_PARAM_NULLPTR` 分支，或拦截返回码 ≠ 161001 ⇒ 命中。

### ⑥ tiling / infershape 层GetData() 与属性指针判空
- 查什么：`op_host` 的 tiling / infershape 中 `GetData()` 返回值是否判空；属性字符串 / 属性数组指针在解引用前是否判空（卡片映射点列明的延伸面）。
- 何处：`*_tiling.cpp` / `*_infershape.cpp` 中 `GetShape()->GetData()`、`GetString` 类调用。
- 命中判据：`GetData()` 返回值直接 `->` 解引用或下标访问 ⇒ 命中。

### ⑦ 多入口算子族的逐入口对称性
- 查什么：同一文件内多个公开入口（如 `aclnnFusedQuantMatmul` 与 `aclnnFusedQuantMatmulWeightNz`）是否**各自**完成判空——修复常只补一个入口（实证同根因四连发即两入口共享一函数、入口各漏一处）；`Inplace` 与非 `Inplace` 变体同理。
- 何处：全部 `aclnnStatus aclnn*GetWorkspaceSize` / `aclnn*` 公开函数。
- 命中判据：逐入口对表后存在覆盖差 ⇒ 命中。

### ⑧ Execute 阶段与出参
- 查什么：Execute 公开入口对 `workspace` / `executor` 入参的判空；两段式的判空职责是否明确（Execute 通常依赖第一段已校验，但公开入口自身参数仍须防御）。
- 何处：`aclnnStatus aclnn*(void* workspace, ...)` 函数体。
- 命中判据：公开 Execute 入口对自身参数无判空即解引用 ⇒ 命中。

### ⑨ 可选输出反向依赖（output-mask，v2.18 新增，对应子型 B04-2）
- 查什么：接口若带 `aclBoolArray* outputMask`（或多输出可选语义），**未被请求的输出指针为 `nullptr` 是合法状态**。此时必须确认：每一条只服务于某个输出的计算路径，是否读取了**另一个**输出的 shape / view / 元信息。典型错误形态是「本路径只需 dw，却用 `gradInput->GetViewShape()` 推 dw 的 view，或把 `gradInput` 当 `ViewWithShape` 的源」。**这类缺陷不会被任何 `CheckNotNull` 拦住**——因为按契约它本来就可以为空。
- 何处：`op_api/aclnn_*.cpp` 中 `OutputViewProcess` / `OutputPostProcess` / `OpExecute` 类输出后处理函数；按输出名分派的专用计算函数（`xxxGradOnly`、`CalcGradWeight` 等）；`(*outputMask)[i]` 判断之后仍被跨引用读取的其他输出变量。
- 命中判据：存在对某个 `outputTensor.<name>` 的 `GetViewShape()` / `GetDataType()` / `ViewWithShape(...)` / `GetShapeSize()` 读取，而该输出的写入路径已被 `(*outputMask)[i]` 门控（即它可能为 `nullptr`），且读取方**不是**该输出自己的后处理 ⇒ 命中。**反向误报排除**：若该输出在同一路径上必被请求（mask 恒真或有前置断言/首段校验保证），须给出「mask 恒真」的 `[文件]:[行号]` 证据方可排除；无证据只能记观察项。
- 探针：对支持 output-mask 的接口跑「仅请求输出 i」全组合；backward 类必须有「只算 dx」「只算 dw」「全算」三档，逐档验证未请求输出不被触碰、已请求输出数值与参考一致、无 coredump。

## 5. 检视流程

1. **定界**：换算 op 目录、确认所在仓与 ref；按用户现象（崩溃栈 / 错误码）反查优先清单点。
2. **枚举**：目录列表列出 `aclnn_*.cpp` 全部入口函数、共享静态校验函数、`docs/aclnn*.md`，产出文件与函数清单。
3. **参数表构建**：从接口签名列出全部参数并标注必选 / 可选（与 docs 约束交叉确认）——后续所有清单点都在此表上对表。
4. **清单逐项核查**：按第 4 节 ①~⑨ 逐点记录命中面与防护面证据（文件:行号）；**卡片触发为「必须触发」：签名零命中时清单仍须逐项核查完毕**。
5. **反证排除**：每必选参数判空齐全、共享函数自校验或调用面全覆盖、校验命中即 return、错误码为 161001、无先用后校验 → 明确写出反证理由。
6. **判定**：按第 7 节标准给出 命中 / 观察项 / 反证排除。
7. **GitCode 查重**（仅命中项）：issues API 按接口名 + `空指针|nullptr|SIGSEGV|coredump|139` 检索，逐条比对是否同机理；无同机理才立卡。
8. **业务可达性核查**（仅命中项）：判 B 等级、定业务影响类型、给处置建议；默认保守（无法证明不可达即记 B3），降档须附证据；B 不改 S×O 档位。
9. **出报告**：按第 8 节模板落盘；静态结论一律附 `nullptr` 探针方案（参数位置 × 两段式阶段矩阵）。

## 6. 风险定级（S×O）与业务影响评估（B 轴）

- **S**：S2（必选参数 `nullptr` 致 SIGSEGV / coredump——接口必现崩溃；若透传 GE 后崩溃归并同档）；S1（仅错误码取值错误如 561103，不影响崩溃与否）。
- **O**：O3 = ≥2 条独立实证；O2 = 1 条独立实证；O1 = 仅静态扫描命中或团队笔记（实证 = 确认对应的 issue / PR，或经跨仓、跨分支核验确认的缺陷记录，同权计入）。静态推演命中且无实证默认 **O1**；升档须在报告中给出实证依据。
- **风险 = S×O**：≥6 高；3/4 中；1/2 低。FP-B04 基准：模式卡整体 S2×O3=6（高）；纯静态命中 S2×O1=2（低，暂定，探针实证后复评）。

### B 轴：业务影响评估（与 S×O 正交；报告层新增，不改卡片定级）

S×O 回答"多严重、多常见"，**不回答"真实业务能不能碰到"**。B 轴补这一问，只决定**修复优先级建议**，**不参与 S/O 取值、不改 S×O 档位与卡片元数据**。

**业务可达性（B）**——触发条件在真实负载中的可达程度：

| 等级 | 判据 | 证据要求 |
|---|---|---|
| B3 现实可达 | 主流框架/公开模型默认路径即可命中（如 PTA/torch_npu、vLLM、MindIE 常规调用） | 调用方或公开负载来源 |
| B2 条件可达 | 需特定 attr/dtype/shape 组合，业务中存在但非默认 | 该组合的业务来源 |
| B1 边界/不可达 | 需极端、超规格或非法参数（超出接口合理上限的 shape、退化/非法输入） | "为何不可达"的说明 |

- **默认保守**：无法证明不可达 → 记 **B3**；降为 B1/B2 必须附证据，**不得仅凭"业务应该不会这么用"**。
- 超规格参数是否算 B1 取决于**接口契约**：契约允许但业务不用 → B1；契约不允许（本应报错）→ 属校验缺失（FP-B04/B05 类），另行归属。

**业务影响类型**（命中后对用户可见结果的后果，用业务语言表述）：静默精度损失（模型效果下降 / loss 不收敛 / 偶发 NaN）｜ 任务失败中断（报错 / 崩溃 / 挂死）｜ 性能退化 ｜ 仅可观测性（日志 / 错误码 / 文档，不影响结果）。

**处置建议**（由两轴推导的报告结论，非新档位）：

| S×O \ B | B3 现实可达 | B2 条件可达 | B1 边界/不可达 |
|---|---|---|---|
| 高（≥6） | 尽快修 | 尽快修 | 排期修 |
| 中（3/4） | 尽快修 | 排期修 | 记录（业务难以触达） |
| 低（1/2） | 排期修 | 记录 | 记录 |

## 7. 判定标准与反误报原则

- **三种判定**：
  - **命中**（可静态证缺陷路径）：任一必选参数存在「判空前使用」「共享函数无自校验 + 入口漏判」「校验命中不 return」「错误码 ≠ 161001」的完整推导链 → 立 Bug 卡；
  - **观察项**：判空存在但依赖调用次序 / 宏展开才能确认顺序 → 记录并附探针方案，暂定档级；
  - **反证排除**：参数表全覆盖 + 共享函数自校验 + 命中即 return + 161001 → 写出防护面证据。
- **可选参数不算缺陷**：`x3Optional` / `biasOptional` 类参数传 `nullptr` 是合法语义；判定前必须先构建必选 / 可选参数表。
- **「返回了错误码」≠「校验正确」**：非 161001 的返回码（如 561103）仍是本型命中（错误码面），不能因「有报错」而排除。
- **崩溃未实测不下「必现」结论**：静态立「无判空的解引用路径」，SIGSEGV 判读留给探针（rc=139 / 1 = 缺陷存在）。
- **不臆造行号**：每条证据必须是实际读到的 文件:行号；引用实证样板时同样给出路径与行号，issue 时点行号与本仓 HEAD 漂移时注明。

### 判定纪律补充（v3.6）：非对称增减、证据等级与误判记录

**增减不对称**：允许追加候选（有据即可，错了可由用户排除）；**撤销或否决候选必须附 `[文件]:[行号] [代码行]` 负向证据**。无证据的「看起来没问题」一律记为「未核查」，不得计入反证排除，也不得据此下调等级——否决造成的漏报用户不可见、不可恢复。

- **证据等级**（Bug 卡必填）：`静态可证` = 推导链完整且触发输入可静态构造；`需实测确认` = 依赖运行时输入规模、设备行为或环境差异。标 `需实测确认` 的条目**不得以「命中」名义出卡**，按观察项记录并附实测用例。
- **Agent 误判记录**（Bug 卡必填）：本次被推翻的假设、推翻它的证据（`[文件]:[行号] [代码行]` 或实测输出）、判定标准是否随之修订；无推翻写「无」。
- **误判回流**：同类误判在 3 次检视中重复出现，登记至 `cases/misjudgments.jsonl`（字段见 `cases/README.md`），并在本模式判定标准中新增对应防线；守门 C19d 校验台账字段合法。

## 8. 产出模板

### Bug 卡字段（命中项必备）

```markdown
### BUG-YYYYMMDD-XX {接口名}（{仓}，{新增/存量}）
- **接口名**：aclnnXxx（{类别}/{op_name}/）
- **命中清单点**：①~⑨ 中的编号与名称
- **文件路径与行号证据**：
  - `{文件}:{行号}`：{首次使用点（解引用/透传）}
  - `{文件}:{行号}`：{判空点（或标注「缺失」）}
  - 防护面记录（反证检查结果）：{文件}:{行号}
- **FP-B04 模式编号**：FP-B04 aclnn 必选入参空指针校验缺失
- **S×O 风险定级**：S2（nullptr 崩溃）× O1（静态命中无实证）= 2，低（暂定，探针实证后复评）
- **证据等级**：{静态可证 / 需实测确认}｜{一句话理由}
- **业务影响评估（B 轴）**：可达性 B{3|2|1}（{一句话判据}）｜ 业务影响：{静默精度损失/任务失败中断/性能退化/仅可观测性}｜ 证据：{调用方/公开负载/为何不可达}｜ 处置建议：{尽快修/排期修/记录}
- **故障机理推导链**：{必选参数 → 入口未判空 → 共享函数 strcmp/GetData 解引用 → SIGSEGV}
- **必选/可选参数表**：{参数 → 必选/可选 → 判空行号 → 首次使用行号}
- **探针方案**：{参数位置 × 两段式阶段} 的 nullptr 用例，判读 rc=139 / 1，期望 161001
- **建议修复方案**：{入口补 OP_CHECK_NULL / 共享函数自校验 / 校验命中补 return / 错误码改 161001}
- **Agent 误判记录**：{被推翻的假设 → 推翻证据 `[文件]:[行号] [代码行]`；无则「无」}
- **GitCode 查重**：{issues API 检索结论，无同机理 issue 才立卡}
```

### 检视报告结构

```markdown
# FP-B04 检视报告：{aclnn 接口名}（YYYY-MM-DD）
## 一、执行概览（仓/ref/HEAD、现象、入口与共享函数清单、判定统计：命中 X / 观察项 Y / 反证排除 Z；命中项 B 轴分布 B3×a / B2×b / B1×c）
## 二、命中明细（Bug 卡，按第 8 节字段，每卡含 B 轴业务影响评估）
## 三、观察项（表：# / 清单点 / 文件:行号 / 存疑点 / 探针方案）
## 四、反证排除（表：清单点 / 反证理由 / 防护面证据）
## 五、探针用例建议（参数位置 × 两段式阶段矩阵、逐入口独立置空）
```

> 报告须在「执行概览」标注证据等级分布（静态可证 X / 需实测确认 Y），并在文末单列「Agent 误判记录」小节（无则写「无」）。

报告落盘到当前任务工作区，建议命名 `FP-B04检视_{接口名}_YYYYMMDD.md`。

## 9. 示例速览：aclnnFusedQuantMatmul

- **定位**：`cann/ops-nn` → `matmul/fused_quant_mat_mul/`（op_host/op_api/aclnn_fused_quant_matmul.cpp——本算子 op_api 在 op_host/ 之下；同目录两个公开入口 `aclnnFusedQuantMatmul` 与 `aclnnFusedQuantMatmulWeightNz`；docs/aclnnFusedQuantMatmul.md 与 aclnnFusedQuantMatmulWeightNz.md）。
- **检视面提示**（引导，不预设结论，仍须逐点核查；行号以本地 HEAD 为准）：
  - 共享判空函数 `CheckInputExistence`（:39 定义）：对必选 x1/x2/x1Scale/x2Scale/out 判空（:53-57），在 CommonProcess 内 :138 `CHECK_RET(CheckInputExistence(...), ACLNN_ERR_PARAM_NULLPTR)` 兜底——核对它是否覆盖**全部**必选 tensor、fusedOpType 是否不在其职责内；
  - 共享校验函数 `CheckFusedOpType`（:164 定义）：:166 直接 `std::strcmp(fusedOpType, ...)` 解引用，**无自校验**——正确性完全依赖入口先行判空；
  - CommonProcess（:214 定义）：:232 从元组解包 `fusedOpType` → :236 `CHECK_RET(CheckFusedOpType(fusedOpType), ACLNN_ERR_PARAM_INVALID)`——修复前入口无判空即到此处，实证 #5531/#5532 即 `fusedOpType=nullptr` 触发 SIGSEGV（gdb 栈 `strcmp → aclnnFusedQuantMatmulGetWorkspaceSizeCommonProcess`，期望 161001 实测 rc=139）；
  - 两个入口当前均含 `fusedOpType == nullptr` → `ACLNN_ERR_PARAM_NULLPTR` 判空（:298-300 与 :333-335）——修复后形态；检视时核对两入口判空是否对称、x1/x2 的 `OP_CHECK_NULL`（:296-297 与 :331-332）与其余必选参数是否全部被 CheckInputExistence 兜住；
  - 对照实证样板：#2501 aclnnArange 预期 161001 实测 561103 的错误码面；#5705 校验命中缺 return 的变体。
- 任何一点的最终判定以第 4/5/7 节口径为准，禁止凭算子类型直接下结论。

## 10. 能力边界与自检（v3.8）

### 能力边界

- **静态可证**：清单里能在源码内给出「`文件:行号` + 推导链」的部分，按第 7 节判据出卡。
- **需实测确认**：依赖运行时输入规模、设备行为或环境差异的结论，只能记观察项并附实测用例（证据等级见第 7 节）。
- **不覆盖**：本模式以外的机理（边界见第 0 节）与仓外框架侧行为；`TRIAGE.md` 只负责收敛候选，不构成判定依据。
- **找不到 ≠ 没有**：按清单未命中只说明「本轮未发现」，不得表述为「该算子无此缺陷」；抽样核查须在报告写明抽样口径。

### 自检

```bash
python3 scripts/gen_triage.py --check                          # 分诊表与映射一致
python3 scripts/scan_fp.py --only FP-B04 --format json <目标文件>  # 签名候选（非结论）
python3 scripts/verify_lines.py <报告.md> --root <被检仓>        # 行号校验
python3 check_fault_patterns.py                                # 全库守门
```

### 工作量与抽样（v4.0）

- **深度档：深度**（索引 `depth` 字段）——全量核查，不抽样。全部映射点 / 分支逐条过；单模式命中 > 50 处时按文件分片，并在报告写明分片口径。
- **报告必填**：抽样口径（全量 / 每点前 N 处 / 每类 N 例）+ 停止点记录；未写口径视为未完成。

## 11. 已知缺陷案例库：触发条件 / 根因 / 修复范式 / 针对性深挖（v5.1）

> 本节把本型**已确认缺陷**拆到代码级：触发 → 根因 → 修复范式（✅）→ 针对性发现 → 最小复现锚；行号取自卡片实证（§9），以本地 HEAD 为准，不得臆造。

### 案例 1｜多入口共享校验函数不自校验 + 入口漏判（同根因四连发）—— #5531 / #5532

- **触发**：GetWorkspaceSize 阶段属性串 `fusedOpType` 传 `nullptr`。
- **根因**：入口仅 `OP_CHECK_NULL(x1/x2)`（:296-297 / :331-332），`fusedOpType` 未判空即经 :232 解包 → :236 调 `CheckFusedOpType`(:164)，:166 `strcmp(fusedOpType,...)` 解空址 → SIGSEGV（期望 161001 实测 rc=139）。
- **修复范式（✅，示意）**：

```cpp
// ❌ 入口只判 x1/x2；共享函数内直接解引用属性串
OP_CHECK_NULL(x1, ...); OP_CHECK_NULL(x2, ...);
CHECK_RET(CheckFusedOpType(fusedOpType), ACLNN_ERR_PARAM_INVALID);   // :236 → :166 strcmp 崩溃
// ✅ 每个必选参数都判空（含属性串/数组、tensor list）；或共享函数自校验
if (fusedOpType == nullptr) return ACLNN_ERR_PARAM_NULLPTR;          // 161001（:298-300/:333-335 即修复后形态）
```

- **针对性发现**：① 枚举文件**全部**入口；② 找多入口共享的 `static` 校验函数；③ 对表「参数→判空行(或缺)→首次使用行」，**函数体内无判空解引用 + 任一入口漏判 ⇒ 命中**。
- **最小复现锚**：逐入口把 `fusedOpType` 置空，期望 161001（rc=139 / 断言 FAIL=缺陷）。
- **实证**：#5531/#5532（四连发）、#5372/#5373。

### 案例 2｜校验命中后缺 return（防御形同虚设）—— #5705

- **触发**：校验命中分支只 `OP_LOGE` 打日志、**无 return**，控制流继续按非法值访问。
- **根因**：`CheckDisContinuousStride` 命中后未返回错误 → 后续按非法 `dims` 访问 vector 越界 UB。
- **修复范式（✅，示意）**：

```cpp
// ❌ 命中只打日志，继续执行
if (!CheckDisContinuousStride(attrs)) { OP_LOGE(ACLNN_ERR_PARAM_INVALID, "discontinuous"); }   // 缺 return
// ✅ 命中即带控制流返回
if (!CheckDisContinuousStride(attrs)) { OP_LOGE(ACLNN_ERR_PARAM_INVALID, "discontinuous"); return ACLNN_ERR_PARAM_INVALID; }
```

- **针对性发现**：遍历 `if (xxx == nullptr)` / `CHECK_RET` 命中分支，查**return 之后**是否仍有使用该参数的路径可达。
- **最小复现锚**：构造命中该校验的非法 attrs，看是否在后续访问处崩溃而非命中处干净返回。
- **实证**：#5705（closed，convolution_forward）。

### 案例 3｜错误码面：「有报错」≠「校验正确」—— #2501

- **触发**：拦截返回码 ≠ 161001（如 561103）。
- **根因**：返回「看起来拦了」的错误码，语义与 `ACLNN_ERR_PARAM_NULLPTR` 不符 → 易误判为「已校验」而漏提。
- **修复范式（✅）**：`CHECK_RET(..., ACLNN_ERR_PARAM_NULLPTR)`（=161001），必选参数逐个覆盖。
- **发现 / 复现锚**：逐必选参数核对「有对应 `ACLNN_ERR_PARAM_NULLPTR` 分支且返回码 == 161001」；置空实测期望 161001。
- **实证**：#2501（aclnnArange 预期 161001 实测 561103）。

### 案例 4｜先用后校验（校验晚于首次解引用）—— #4586 / #221

- **触发**：判空位置**晚于**该参数首次解引用 / 透传（含 `L2_DFX_PHASE_1` 宏内解引用）。
- **根因**：入口顺序错误——先用后校验，校验形同虚设。
- **修复范式（✅）**：判空**前置到函数开头、任何解引用 / 透传之前**。
- **发现 / 复现锚**：逐参数比较「首次使用行号 < 判空行号」⇒ 命中；参数置空看是否在判空前崩溃。
- **实证**：#4586（wqbmm）、#221（IouV2）、#4784（fqmm）。

### 案例 5｜可选输出（output-mask）反向依赖：只算 dw 时读 dx 的 shape —— 子型 B04-2

> 来源：现网修复复盘 26-02（ops-nn PR #1001）。**这是本卡唯一「不是忘记判空」而崩溃的形态**，`CheckNotNull` 覆盖再全也拦不住。

- **触发**：`aclnnConvolutionBackward` 只请求 `gradWeight`（dw），`gradInput`（dx）按 output-mask 契约传 `nullptr`。
- **根因**：dw 专用计算路径按「两侧梯度都存在」的所有权假设，读取 `gradInput` 的 shape 并用它作 `ViewWithShape` 的源创建视图；`gradInput == nullptr` 时解引用空地址 → **core dump**。缺陷不在校验层，在**输出的所有权边界**。
- **修复范式（✅，修复后形态，本仓实测锚）**：

```cpp
// ✅ 各输出后处理逐个被 outputMask 门控（aclnn_convolution_backward.cpp:911-935 OutputViewProcess）
if ((*outputMask)[0]) { l0op::ViewCopy(ResultTensor.gradInput,  outputTensor.gradInput,  executor); }
if ((*outputMask)[1]) { l0op::ViewCopy(ResultTensor.gradWeight, outputTensor.gradWeight, executor); }
if ((*outputMask)[2]) { l0op::ViewCopy(ResultTensor.gradBias,   outputTensor.gradBias,   executor); }
// ❌ 反例：dw 路径读 gradInput 的 shape —— gradInput 可为 nullptr，契约上完全合法
//    auto dxShape = outputTensor.gradInput->GetViewShape();   // core dump
```

- **针对性发现**：① 找出所有 `(*outputMask)[i]` 门控点，划出「可能为 nullptr」的输出集合；② 在这些输出集合内，搜索**跨角色读取**——`outputTensor.<B>->GetViewShape()/GetDataType()/GetShapeSize()` 出现在名为 `<A>` 的计算函数里；③ 反向误报排除必须给出「该 mask 恒真」的 `[文件]:[行号]`，无证据只能记观察项。
- **最小复现锚**：只用 dw、`gradInput=nullptr` 调 `aclnnConvolutionBackward` 两段式，期望不崩溃且 dw 与 CPU/CUDA 参考一致；再补「只算 dx」「全算」两档对照，确认三档都正确。
- **实证**：ops-nn PR #1001。修复后形态锚：`conv/convolution_backward/op_api/aclnn_convolution_backward.cpp:911-935`（@ops-nn HEAD `b27fda2`，2026-11-05 本地核验）。

## 12. 实证加深（v5.4）

> 本节给**真实修复锚**（`文件:行号 @commit`）与**反向排除项**（撤一条候选需要什么负向证据）。
> 取证基线：ops-nn `@b27fda2`（2026-11-05 本地核验，当前 master HEAD）。**仓为浅克隆**，故 commit 列记 HEAD 而非修复提交 SHA——修复提交本身通过 PR 号引用（见「真实锚」列的 issue 位）。

### 12.1 真实锚（修复后形态）

| 案例 / issue | 真实锚（文件:行号 @commit） | 要点 |
|---|---|---|
| #1001 `aclnnConvolutionBackward` 只算 dw 时崩溃（子型 B04-2） | `conv/convolution_backward/op_api/aclnn_convolution_backward.cpp:911-935` @b27fda2 | `OutputViewProcess` 内 gradInput(:916-923) / gradWeight(:924-931) / gradBias(:932-939) 各自被 `if ((*outputMask)[i])` 门控——**修复后形态**。缺陷形态是 dw 路径读 `gradInput->GetViewShape()` 并作 `ViewWithShape` 源，`gradInput==nullptr` 时 core dump。判据：`outputMask[i]` 可假 ⇒ 该输出可为 nullptr ⇒ 任何跨该输出的 shape/view 读取都是候选。 |

### 12.2 反向排除项

| 反向排除项 | 所需负向证据 |
|---|---|
| 该参数本就允许为空（`Optional` 语义） | 给出接口签名或 `docs/aclnn*.md` 中「可为空指针」的原文，并指出**空值时的合法分支** `[文件]:[行号]`；只说「文档是可选参数」不算 |
| 该输出在本次调用中不可能被省略 | 给出「mask 恒真」的证据 `[文件]:[行号]`：如 `outputMask` 由框架固定构造、或首段校验强制全部为 true |
| 校验已由上游入口完成 | 给出**该入口自身**的判空行 `[文件]:[行号]`；不得以「另一个入口校验了」代替（多入口族必须逐入口） |
| 校验命中后已有有效控制流 | 给出命中分支的 `return` / `CHECK_RET` `[文件]:[行号]`；仅 `OP_LOGE` 不算 |
| 读取的是本输出自己的元信息 | 给出门控条件与该读取在同一分支内的 `[文件]:[行号]`，证明读取方即该输出的后处理 |
| 非连续性已被正确处理 | 给出 `TensorContiguousProcess` / `Contiguous` 调用点 `[文件]:[行号]`，且其产物确实被下游消费（不是算了没用） |

## 13. 判据层（L2/L3）：出用例与判读前必读 <!-- BEGIN DETECT-SECTION (generated by scripts/sync_detect_section.py; do not edit) -->

> 生成物，勿手改（C42 校验）。完整判据见 [references/detect-l2-l3.md](references/detect-l2-l3.md)。

- **L2**：轴 入参合法性/契约一致性｜观测 error-code｜至少 4 例
- **L3 `error-code`**：K583(假 FAIL)inplace 接口「广播变宽」是 161002 正确拒绝，纯 doc 基线会成片假 FAIL；K866(漏检)dtype 变异只改张量不改 aclScalar → 结构上抓不到标量 dtype 不校验

> 判 FAIL 先排「假 FAIL」、判 PASS 先排「假 PASS/假绿」。**不查 L3 就出结论 = 报告作废。** <!-- END DETECT-SECTION -->
