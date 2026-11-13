---
name: "fpb08-fallback-review"
description: "基于 FP-B08「节点级配置未参与派发决策（属性在某一跳被丢弃：fallback 回调 / 前端插件 / fusion pass）」故障模式对指定算子做源码检视：定位实现，按 fallback 回调/前端插件/fusion pass 三载体的属性透传差集核查，产出证据链与 S×O 定级报告。当用户遇到节点属性未生效、opImplMode/HF32、图模式与 aclnn 直调不一致时使用。"
---

# FP-B08 算子检视（fpb08-fallback-review）

对用户指定的算子（如 MatMulV3）做 FP-B08 专项源码检视：先定位三载体（fallback 回调 / 前端插件 / fusion pass）实现，再按清单逐项核查，每个结论给出**文件 + 行号 + 推导链**证据，命中即出 Bug 卡并输出报告。**本模式特殊纪律：① 本型不是「读取逻辑本身错」，而是「属性在某一跳被丢弃」——判定核心是**属性透传链路断在哪一跳**，须做「属性名清单 × proto 声明集合」的差集并核对跨函数读写配对；② 最典型定位特征是**aclnn 直调正常、GE 图模式 fallback 异常**——先确认路径差异再定位载体；③ 属性按**位置索引**取值（`GetAttrPointer<T>(N)`）是高危写法，顺序/语义变更即静默取错；④ 版本边界不可统一按「某版本前都带 bug」构造——三载体修复时机不同（见卡摘要）；⑤ 节点级配置「未生效但无报错」，静态只能立「未读属性」候选点位，生效性须图模式实跑 + profiler 反查。**

## 0. 与相邻模式的边界

| 相邻模式 | 分工 |
|---|---|
| FP-B01（支持面校验过严误拦截合法输入） | **方向相反的镜像**：B01 是校验过严拦掉合法输入；本型是校验/派发读取不全，把**节点配置静默忽略**——同属「配置面与判定面不一致」 |
| FP-B03（跨仓迁移丢失防御/拦截逻辑） | 本型可视为「迁移时丢失节点属性读取」的特化——迁移丢防御分支归 B03，属性在某跳未透传归本条 |
| FP-A16（aclop 与 aclnn 编译阶段精度差异） | **同属多通路一致性族**：A16 是 aclop vs aclnn 的编译阶段差异；本型是「图模式 fallback vs aclnn 直调」的路径差异 |
| FP-A20（确定性等级未分级标注） | 同属「配置粒度未正确传递/暴露」：A20 是确定性等级未分级，本型是节点级配置未参与决策 |
| FP-F02（可观测性不足） | 属性读取失败仅 `OP_LOGE` 后静默 `return false` 属可观测性面（归 F02），**属性未被读取**的成因归本条；#1660「降级分支误报 error」是其对称面 |
| FP-F01（构建/产物类缺陷） | #1639 的表现为 ATC 编译失败，与构建/产物类缺陷交叠——表现为编译失败时可与 F01 关联，成因仍按本条 |

**症状反查定位**（先定优先载体，再进清单）：**aclnn 直调正常、GE 图模式（经 fallback）异常** → 回调漏读节点属性；节点级配置（`opImplMode` / `enable_hf32` / `groups`）不生效而全局能生效 → 回调/插件/Pass 只读全局；无 error 日志而模式不符预期 → 静默降级；前端升级后新属性（如 ONNX13+ `noop_with_empty_axes`）不生效 → 插件透传清单未更新；融合后编译失败 / 下游异常 → Pass 漏拷源节点属性。载体定位顺序见第 2 节。

## 1. FP-B08 模式卡摘要（检视依据，源自本库 `patterns/FP-B/FP-B08.md`，v3.1）

- **编号 / 名称**：FP-B08 节点级配置未参与派发决策（属性在某一跳被丢弃：fallback 回调 / 前端插件 / fusion pass） ｜ **类别**：功能/兼容 ｜ **风险**：高（S2×O3=6，2026-09-16 由中升档）｜ **状态**：活跃
- **适用声明头**（照抄卡片）：仓 canndev ｜ 侧别 Host ｜ 载体 IR与图配置 ｜ 触发 GetAttrPointer|ParseOpToGraph|fallback|AddNode ｜ 默认启用 true
- **skill 核查面**：与卡片载体一致——canndev 仓内三类「属性需跨越一跳传递」的实现：① aclnn fallback 回调（`ops/built-in/op_fallback/`）；② 前端插件解析函数（`ops/built-in/framework/onnx_plugin/` 等）；③ 图 fusion pass（`ops/*/*/graph_plugin/fusion_pass/` 与 `ops/built-in/fusion_pass/`）；并延伸至算子 proto（属性声明顺序，作按位置索引取值的比对基准）
- **故障机理**：图模式下算子经 aclnn fallback 回调执行时，回调只读**全局配置**（`allow_hf32`、`precision_mode`）决定派发/执行模式，**未读节点级属性**（`opImplMode`、`enable_hf32`、`groups`），致节点配置**不参与**决策。① 节点级开而全局未开 → **节点配置被静默忽略**、走默认路径；② 反向：全局开而节点显式关 → 仍按全局开执行（无节点级否决权）；③ 与直接 aclnn 调用路径不一致——**aclnn 直调正常、图模式 fallback 异常**，是本型最典型定位特征。根因多为回调按 `GetNodeType()` 分支只覆盖部分算子（如仅 `MatMulV3`），或**属性按位置索引取值**（`GetAttrPointer<T>(3)`）顺序变更后静默取错。同一机理三载体均有实证且**修复时机不同**：① fallback 回调（#1790）；② ONNX 插件解析函数新增属性未纳入透传清单（#1647）；③ 图 fusion pass 新建节点未拷源节点属性（#1639）——载体③修复最早（`9.1.0-beta.2`，早于 ①②）。共性为**「属性在某一跳被丢弃」**，而非读取逻辑本身错误；**版本矩阵不可统一按「9.1.0 前都带 bug」构造**（逐载体版本边界见实证案例与第 7 节）。
- **触发条件**：**四元组同时成立**——① 走 **GE 图模式**（非 aclnn 直调）；② 该算子**经 aclnn fallback 回调**执行；③ 节点上**设置了节点级配置属性**（且与全局不一致）；④ 该回调分支**已实现但未读该属性**。**aclnn 直调不触发**。**载体泛化**：任一「属性需跨越一跳传递」的环节（见核查面三载体）只要该跳**未显式透传属性**即可能触发；**前端框架版本升级新增属性**（如 ONNX13+ `noop_with_empty_axes`）是高频场景。
- **典型表现**：节点级配置**未生效但无报错**——执行模式不符预期（可能性能下降或精度差异，取决于配置项语义）；图模式与 aclnn 直调**结果/性能不一致**（全局能生效、节点级不生效）；无 error 日志（读取失败仅 `OP_LOGE` 后 `return false`）。
- **源码审查映射点**：① 派发模式函数是否**既读全局也读节点属性**（合理组合 OR/AND）；② `GetNodeType()` 分支是否覆盖全部会走该回调的算子（`MatMulV3` / `BatchMatMulV3` 等）；③ **属性取值方式**（`attrs->GetAttrPointer<T>(N)` **按位置索引**高危）；④ 属性读取失败（`attrs == nullptr`）是否**静默降级 return false**；⑤ 全局配置指针（如 `GetAllowHf32()` 返回 `nullptr`）是否**判空**；⑥ 前端插件解析函数（如 `ParseOpToGraph*`）是否把**新增属性**纳入透传清单；⑦ **fusion pass 新建/替换节点**是否把**源节点全部相关属性**拷到新节点。**逐点「查什么/何处/命中判据」见第 4 节。**
- **检测签名**：`GetAttrPointer\s*<[^>]+>\s*\(\s*\d+\s*\)`（**按数字索引取属性**）；`strcmp\s*\(\s*\w*[Nn]odeType\s*,\s*"`（节点类型硬编码分支）；`strcmp\s*\(\s*\w*[Aa]llow_?[Hh]f32`；含 `_hf32|Hf32|HF32` 的布尔判定函数中**是否出现 `attrs`/`GetAttr` 调用**（整函数无 `GetAttr` 即「只看全局」嫌疑）；`GetAttrPointer` 失败分支为 `return false;` 且无 `OP_LOGE`；**`ParseOpToGraph[A-Za-z0-9]+` 函数内**：属性名清单与目标算子 proto 声明属性集做**差集扫描**（差集非空即漏透传）；**fusion pass** 的「**属性读端与写端不在同一函数**」断链——存在 `SetInt(<新节点 opDesc>, <ATTR>, <局部变量>)` 而**找不到**同名 `GetInt(<源节点 desc>, <ATTR>, <同一变量>)`（或反向）即嫌疑；**变量名可作跨函数线索**（#1639 读端 `CheckConv2dTransposeDescInfo()`、写端 `CreateRearrangeOp()`，两侧均名 `attrGroups`）。⚠️ 仅扫 `AddNode`/`CreateNode` 前后若干行**会漏判**——#1639 读写分落两函数且都不紧邻 `AddNode`。
- **测试拦截建议**：① **节点级 × 全局级交叉矩阵**——`{节点开,全局关} / {节点关,全局开} / {双开} / {双关}` 四组，**断言两两可区分**；② **图模式 vs aclnn 直调对拍**——同 shape/dtype 比对**执行模式（profiler 反查 kernel 类型/耗时）与数值结果**；③ 按位置索引取属性处补「**属性顺序变更单测**」或静态门禁（比对 N 与 proto 顺序）；④ 节点级配置生效性纳入**泛化用例矩阵**（勿只测全局开关）。**详见第 8 节模板。**
- **实证案例**：canndev **#1790**（closed）「MM 算子经 GE aclnn fallback 回调执行时 HF32 属性未正确传递」——回调**未读 MatMulV3 节点的 `opImplMode`**，HF32 判断只依赖全局 `allow_hf32`，致**节点级 HF32 未参与 `cubeMathType` 生成**；影响：该场景 HF32 未按节点配置生效（**可能性能下降或精度差异**），**aclnn 直调不受影响**；复现：`ge 图设 matmul 节点 opImplMode=0x40`；环境 A2/A3/A5；修复 PR **#82099**（master）+ **#82101**（`9.2.0-beta.1` 回合），改 `ops/built-in/op_fallback/fallback_common_2stages.cpp`（+44/−4）：新增 `OpImplMode` 位枚举（`ENABLE_HF32 = 0x40`）与 `IsMatMulV3Hf32Enabled()`，`GetMatmulPrecisionMode()` 由「只看全局」改「**节点级 OR 全局**」并补 `GetAllowHf32()` 判空。**同机理独立实证（O2→O3 依据）**：**#1647**（open）「ReduceSum Onnx 插件未正确处理 `noop_with_empty_axes`」——ONNX13 后 `reduceSum` 取到该属性**未往下传递**，路径 `ops/built-in/framework/onnx_plugin/reduce_sum_plugin.cc` 函数 `ParseOpToGraphReduceSum13`，未透传到 GE 的 OP（Ascend910C / CANN8.5）；**#1639**（closed）「Fix ExtendConvTranspose A16W8 group」——A16W8 下算子缺少 `groups` 正确处理：**fusion pass 未取 conv2dtranspose 的 `groups`**、**建 rearrange 时未把 `groups` 设到新节点**，致 ATC 编译失败；路径 `ops/convolution/extend_conv_transpose/graph_plugin/fusion_pass/conv2d_transpose_fixpipe_fusion_pass.cc`（**在算子自有 `graph_plugin/` 下，非 `ops/built-in/fusion_pass/`**）；修复提交 `1f65a691`（+7 行，2026-05-12，MR `!81593`），三处改动「读 `GetInt(conv2dtransposeDesc_, GROUPS, attrGroups)` + 写 `SetInt(opDesc, GROUPS, attrGroups)` + 初始化 `attrGroups = 1`」并引入 `InsertA16W8WeightFzTransferOp()`。**版本边界实测（2026-09-16）**：9.0.0 / 9.0.0-beta.2 / 9.1.0-beta.1 **带 bug**，**9.1.0-beta.2 起修复**（beta.3 / 9.1.0 / 9.2.0 / master 同）。**#1647 版本边界**：9.0.0 / 9.0.0-beta.2 / 9.1.0-beta.1 / 9.1.0-beta.3 **带 bug**；9.1.0 / 9.2.0 / master **已修复**（提交 `cce77adb`，2026-06-01，MR `!81676`；⚠️ 该提交描述关联 issue **#1674** 而非 #1647，关系待确认）。**#1771**（open，同族待查）「BatchMatMulV3 原型修改：attr `enable_hf32` 改 `opImplMode`」——同族**属性语义迁移**，是本型③「按位置索引取属性」的直接风险来源。
- **关联**：FP-B01（方向相反的镜像）、FP-B03（迁移丢失节点属性读取的特化）、FP-A16（多通路一致性族）、FP-A20（配置粒度未正确传递/暴露）、FP-F02（属性读取失败静默 `return false`，属可观测性不足）、FP-F01（#1639 表现为 ATC 编译失败，与构建/产物类交叠）——分工详见第 0 节。

## 2. 检视输入与算子定位

**输入**：算子名 / 节点类型（必填，如 `MatMulV3`、`ReduceSum`、`ExtendConvTranspose`）；可选 ref（默认 master）、指定载体（默认三载体全查）；可选现象描述（节点配置不生效 / 图模式与 aclnn 直调不一致 / 编译失败——症状反查用）；可选前端框架与版本（ONNX 版本——新增属性触发场景的关键输入）。

**算子名 → 实现定位**：本型不在 `ops-*` 算子仓，而在 **canndev** 仓三类载体路径中：

```text
cann/canndev/
├── ops/built-in/op_fallback/                 # 载体①：aclnn fallback 回调
├── ops/built-in/framework/onnx_plugin/       # 载体②：前端插件解析（ParseOpToGraph*）
├── ops/built-in/fusion_pass/                 # 载体③a：通用图 fusion pass
├── ops/{域}/{op_name}/graph_plugin/fusion_pass/   # 载体③b：算子自有 graph_plugin
└── ops/{域}/{op_name}/                        # 算子 proto（属性声明与顺序：按位置索引取值的比对基准）
```

**载体定位顺序**（按症状反查，见第 0 节）：图模式 fallback 异常而 aclnn 直调正常 → 载体① `op_fallback/`；前端新增属性不生效 → 载体② `onnx_plugin/`（或其他前端插件目录）；融合后编译失败 / 下游异常 → 载体③（`graph_plugin/fusion_pass/` 与 `ops/built-in/fusion_pass/`）。**载体③注意**：Pass 可能在算子自有 `graph_plugin/` 下，须用文件名检索确认。

## 3. 取数方式（Important）

公开网页端点被拦截，**必须走 API**（均需带 `User-Agent`；失败重试 2 次、间隔 5 秒）：

| 用途 | 端点 |
|---|---|
| 目录列表 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/contents/{path}?ref={ref}` |
| 单文件内容 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/raw/{path}?ref={ref}` |
| Issue 查重 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/issues?q={关键词}` |

**已实测不可用（截至 2026-09）**：`https://gitcode.com/{repo}/raw/{sha}/{path}`、`https://raw.gitcode.com/...` → 403 或拦截页。若本地已有算子仓克隆，优先读本地文件，行号以本地 HEAD 为准并记录 commit（本型目标仓 `canndev`）。**本模式特有取数限制**：节点级配置**是否生效**须走 **GE 图模式实跑 + profiler 反查执行模式**（kernel 类型/耗时）并与 aclnn 直调对拍；静态检视只产出候选点位与交叉矩阵方案，不可把静态缺失表述为「必然不生效」；**版本边界**引用卡片结论须注明时点（2026-09-16）与版本号。

## 4. 属性透传检视清单（每点：查什么 → 何处 → 命中判据）

对三载体实现与 proto 逐点核查，**每点先查命中面、再做反证排除**；已有属性读取与空指针防护也记入防护面证据。

### ① 派发模式函数是否既读全局也读节点属性
- 查什么：fallback 回调中决定派发/执行模式的函数（如 `GetMatmulPrecisionMode`）是否**既读全局又读节点属性**、判定是否为二者**合理组合**（OR/AND 与语义一致否）；节点级开而全局关时是否仍生效（#1790 修复前只读全局 `allow_hf32`）。
- 何处：`ops/built-in/op_fallback/` 下决定精度/执行模式的函数体。
- 命中判据：函数内无 `GetAttr`/`attrs` 调用（整函数只看全局）⇒ 命中（给出「函数 → 全局读取行 → 缺失的节点属性读取」链）。

### ② `GetNodeType()` 分支覆盖度
- 查什么：回调按 `GetNodeType()` 分支是否覆盖**全部会走该回调的算子**（#1790 仅 `MatMulV3`，`BatchMatMulV3` 等遗漏否）。
- 何处：`strcmp(<nodeType>, "...")` 类节点类型分支。
- 命中判据：存在会走该回调但无对应分支的算子 ⇒ 命中（给出「算子 → 分支清单 → 落默认路径」链）。

### ③ 属性取值方式（按位置索引高危）
- 查什么：`attrs->GetAttrPointer<T>(N)` **按数字索引**取值——顺序变更/语义迁移（#1771 原型把 `enable_hf32` 改 `opImplMode`）即静默取错；是否改按属性名获取，或索引常量与 proto 顺序有校验。
- 何处：全部 `GetAttrPointer<T>(<数字>)` 调用点；算子 proto 的属性声明顺序。
- 命中判据：按数字索引取属性且无一致性校验 ⇒ 命中（须结合 proto 顺序确证）。

### ④ 属性读取失败的处理（静默降级）
- 查什么：`attrs == nullptr` / 指针为空时——静默 `return false`（无 `OP_LOGE`）还是上报；降级是否导致「节点配置被忽略」。
- 何处：`GetAttrPointer` 的失败分支。
- 命中判据：失败分支静默降级且致节点配置被忽略 ⇒ 命中（可观测性面与 FP-F02 关联）。

### ⑤ 全局配置指针的空指针校验
- 查什么：全局配置指针（如 `GetAllowHf32()` 返回 `nullptr`）是否判空——原实现直接 `strcmp` 会崩（#1790 修复补了该防护）。
- 何处：`strcmp(<allow_hf32>)` 类调用点、全局配置 getter 使用处。
- 命中判据：指针未判空即解引用 ⇒ 命中（可静态证崩溃路径）。

### ⑥ 前端插件解析透传清单（新增属性差集）
- 查什么：`ParseOpToGraph*` 内解析并透传的属性名清单与算子 proto 声明属性集做**差集**——非空即漏透传（#1647 `noop_with_empty_axes`）；前端版本升级新增属性是高频场景。
- 何处：`ops/built-in/framework/onnx_plugin/`（及 TF 等）的 `ParseOpToGraph*` 函数体、目标算子 proto。
- 命中判据：`proto 属性集合 ∖ 解析透传集合 ≠ ∅` ⇒ 命中（给出差集条目与函数行号）。

### ⑦ fusion pass 属性读写配对（跨函数断链）
- 查什么：Pass 新建/替换节点是否把**源节点全部相关属性**拷到新节点——「读端与写端不在同一函数」的断链：存在 `SetInt(<新节点 opDesc>, <ATTR>, <局部变量>)` 而找不到同名 `GetInt(<源节点 desc>, <ATTR>, <同一变量>)`（或反向）。**变量名是跨函数线索**（#1639 读端 `CheckConv2dTransposeDescInfo()`、写端 `CreateRearrangeOp()`，均名 `attrGroups`）。⚠️ **仅扫 `AddNode`/`CreateNode` 前后若干行会漏判**——读写分落两函数且都不紧邻 AddNode。
- 何处：算子自有 `graph_plugin/fusion_pass/` 与 `ops/built-in/fusion_pass/` 下 Pass 全函数体。
- 命中判据：存在读写断链（写端无对应读端，或读端值未传到写端）⇒ 命中（#1639：`groups` 未读/未写致 ATC 编译失败）。

## 5. 检视流程

1. **定界**：定算子/节点类型与目标载体（症状反查：图模式 vs aclnn 直调不一致 → 载体①；前端新增属性 → 载体②；融合后异常 → 载体③）；确认 ref 与目标仓 `canndev`。
2. **枚举**：目录列表 + 文件名检索列出三载体相关文件与算子 proto（属性声明顺序作比对基准）。
3. **触发词扫描**：按 `GetAttrPointer\s*<[^>]+>\s*\(\s*\d+\s*\)`、`strcmp\s*\(\s*\w*[Nn]odeType`、`strcmp\s*\(\s*\w*[Aa]llow_?[Hh]f32`、含 `_hf32|Hf32|HF32` 的判定函数、`ParseOpToGraph[A-Za-z0-9]+`、`SetInt|GetInt`（Pass 内）定位风险面（本地仓 grep；API 模式逐文件拉取后检查）。
4. **清单逐项核查**：按第 4 节 ①~⑦ 逐点记录命中面与防护面证据（文件:行号）；对 ⑥ 做**属性名差集对表**；对 ⑦ 做**读写配对表**（按变量名跨函数关联）。
5. **反证排除**：派发函数既读全局也读节点属性、`GetNodeType()` 分支全覆盖、按名取属性、失败有上报、全局指针判空、透传集合 == proto 属性集、Pass 读写配对完整 → 写出反证理由（防护面证据）。
6. **判定**：按第 7 节标准给 命中 / 观察项 / 反证排除。
7. **查重**（仅命中项）：issues API 按算子名 + `fallback|节点属性|opImplMode|HF32|属性未传递|noop_with_empty_axes|groups` 检索，比对是否同机理；无同机理才立卡。
8. **业务可达性核查**（仅命中项）：判 B 等级、定业务影响类型、给处置建议；默认保守（无法证明不可达即记 B3），降档须附证据；B 不改 S×O。
9. **出报告**：按第 8 节模板落盘；静态结论一律附**节点级 × 全局级交叉矩阵 + 图模式 vs aclnn 直调对拍**方案（含 profiler 反查）。

## 6. 风险定级（S×O）与业务影响评估（B 轴）

- **S**：S2（节点级配置静默忽略——可能性能下降或精度差异，不崩溃、不报错）；S1（属性读取失败静默降级无日志等可观测性面）；S3（漏拷属性致 ATC 编译失败等构建/产物中断，与 FP-F01 交叠时按主导机理归属）。
- **O**：O3 = ≥2 条独立实证；O2 = 1 条独立实证；O1 = 仅静态扫描命中或团队笔记（实证 = 确认对应的 issue / PR，或跨仓、跨分支核验确认的缺陷记录，同权计入）。静态推演且无实证默认 **O1**；升档须在报告中给出依据。
- **风险 = S×O**：≥6 高；3/4 中；1/2 低。FP-B08 基准：模式卡整体 S2×O3=6（高）；纯静态命中 S2×O1=2（低，暂定）。

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

- **属性相关签名命中 ≠ 成立**：`GetAttrPointer` / `GetNodeType` 在 canndev 中量大，命中只作定位提示；须证明「该属性会被节点设置 + 该跳未读取/未透传」才立卡——触发四元组缺一不可（GE 图模式 / 经 fallback 回调 / 节点设了该属性 / 分支已实现但未读）。
- **三种判定**：
  - **命中**（可静态证缺陷路径）：「派发函数只看全局」「`GetNodeType` 分支遗漏」「按位置索引取属性」「插件透传差集非空」「Pass 读写断链」推导链完整 → 立 Bug 卡；
  - **观察项**：属性是否被设置依赖调用方、执行模式差异需 profiler 实测、静默降级后果需对拍 → 记录并附交叉矩阵方案；
  - **反证排除**：派发函数读节点属性、分支全覆盖、按名取属性、失败上报、透传集合 == proto 属性集、Pass 读写配对完整 → 写防护面证据。
- **版本边界不可一刀切**：三载体修复时机不同（载体③ `9.1.0-beta.2` 已修复，早于 ①② 的 9.1.0）——判定当前 ref 须逐载体核对修复提交。
- **aclnn 直调正常不构成反证**：本型定义即**图模式 fallback 与 aclnn 直调不一致**，须以「两条通路对拍」判定。
- **Pass 检视范围不许窄化**：fusion pass 的属性读写常分落两函数（#1639），禁止只扫 `AddNode`/`CreateNode` 邻域——须按变量名跨函数核对读端与写端。
- **不臆造行号**：每条证据须为实际读到的 文件:行号；引用实证样板（#1790 / #1647 / #1639 及修复提交/PR）时给出本仓位置，行号漂移时注明基准版本。

### 判定纪律补充（v3.6）：非对称增减、证据等级与误判记录

**增减不对称**：允许追加候选（有据即可，错了可由用户排除）；**撤销或否决候选必须附 `[文件]:[行号] [代码行]` 负向证据**。无证据的「看起来没问题」一律记为「未核查」，不得计入反证排除，也不得据此下调等级——否决造成的漏报用户不可见、不可恢复。

- **证据等级**（Bug 卡必填）：`静态可证` = 推导链完整且触发输入可静态构造；`需实测确认` = 依赖运行时输入规模、设备行为或环境差异。标 `需实测确认` 的条目**不得以「命中」名义出卡**，按观察项记录并附实测用例。
- **Agent 误判记录**（Bug 卡必填）：本次被推翻的假设、推翻它的证据（`[文件]:[行号] [代码行]` 或实测输出）、判定标准是否随之修订；无推翻写「无」。
- **误判回流**：同类误判在 3 次检视中重复出现，登记至 `cases/misjudgments.jsonl`（字段见 `cases/README.md`），并在本模式判定标准中新增对应防线；守门 C19d 校验台账字段合法。

## 8. 产出模板

### Bug 卡字段（命中项必备）

```markdown
### BUG-YYYYMMDD-XX {算子/节点类型}（canndev，{新增/存量}）
- **算子 / 节点类型**：{MatMulV3 / ReduceSum / ExtendConvTranspose 等}
- **命中载体**：① fallback 回调 / ② 前端插件解析 / ③ fusion pass
- **命中清单点**：①~⑦ 中的编号与名称
- **文件路径与行号证据**：
  - `{文件}:{行号}`：{只看全局的派发函数 / 按位置索引取属性 / 插件透传缺失项 / Pass 读写断链}
  - `{文件}:{行号}`：{节点属性应被读取处（proto 属性声明 / 源节点读端）}
  - 防护面记录（反证检查结果）：{文件}:{行号}
- **FP-B08 模式编号**：节点级配置未参与派发决策（属性在某一跳被丢弃：fallback 回调 / 前端插件 / fusion pass）
- **S×O 风险定级**：S2（节点配置静默忽略）× O1（静态命中无实证）= 2，低（暂定）
- **证据等级**：{静态可证 / 需实测确认}｜{一句话理由}
- **业务影响评估（B 轴）**：可达性 B{3|2|1}（{一句话判据}）｜ 业务影响：{静默精度损失/任务失败中断/性能退化/仅可观测性}｜ 证据：{调用方/公开负载/为何不可达}｜ 处置建议：{尽快修/排期修/记录}
- **故障机理推导链**：{节点设节点级属性 → 该跳（回调/插件/Pass）未读取/未透传 → 节点配置不参与决策 → 走默认路径 / 新节点漏属性 → 性能下降或精度差异 / 编译失败}
- **触发四元组核对**：{GE 图模式 / 经 fallback 回调 / 节点设了该属性 / 分支已实现但未读} 逐项确认
- **属性差集 / 读写配对表**：{属性名 → proto 声明 → 透传处（或「缺失」）}；{ATTR → 读端行号 → 写端行号}
- **交叉矩阵与对拍方案**：{节点开/全局关、节点关/全局开、双开、双关 四组断言两两可区分}；{GE 图 vs aclnn 直调对拍（profiler 反查执行模式）}
- **建议修复方案**：{派发函数改为节点级 OR/AND 全局 / 补 GetNodeType 分支 / 改按名取属性 + 索引一致性校验 / 插件补透传新增属性 / Pass 补读源节点属性并写新节点 + 初始化默认值}
- **Agent 误判记录**：{被推翻的假设 → 推翻证据 `[文件]:[行号] [代码行]`；无则「无」}
- **GitCode 查重**：{issues API 检索结论，无同机理 issue 才立卡}
```

### 检视报告结构

```markdown
# FP-B08 检视报告：{算子/节点类型}（YYYY-MM-DD）
## 一、执行概览（仓/ref/HEAD、现象与优先载体、三载体文件清单、版本边界核对、判定统计 命中 X / 观察项 Y / 反证排除 Z；命中项 B 轴分布 B3×a / B2×b / B1×c）
## 二、命中明细（Bug 卡，按第 8 节字段，每卡含 B 轴业务影响评估）
## 三、观察项（表：# / 清单点 / 载体 / 文件:行号 / 存疑点 / 实测方案）
## 四、反证排除（表：清单点 / 反证理由 / 防护面证据）
## 五、验证建议（节点级 × 全局级交叉矩阵、图模式 vs aclnn 直调对拍 + profiler 反查、属性顺序变更单测/门禁）
```

> 报告须在「执行概览」标注证据等级分布（静态可证 X / 需实测确认 Y），文末单列「Agent 误判记录」（无则「无」）。落盘到任务工作区，建议命名 `FP-B08检视_{算子名}_YYYYMMDD.md`。

## 9. 示例速览：MatMulV3（GE aclnn fallback 回调）

- **定位**：`cann/canndev` → 载体① `ops/built-in/op_fallback/fallback_common_2stages.cpp`（#1790 修复文件，含 `OpImplMode` 位枚举 `ENABLE_HF32 = 0x40`、`IsMatMulV3Hf32Enabled()`、`GetMatmulPrecisionMode()`、`GetAllowHf32()` 判空）；对照载体② `ops/built-in/framework/onnx_plugin/reduce_sum_plugin.cc` 的 `ParseOpToGraphReduceSum13`（#1647）、载体③ `ops/convolution/extend_conv_transpose/graph_plugin/fusion_pass/conv2d_transpose_fixpipe_fusion_pass.cc`（#1639，读写分落 `CheckConv2dTransposeDescInfo()` / `CreateRearrangeOp()`）。
- **检视面提示**（引导，不预设结论；行号以本地 HEAD 为准）：
  - 清单点①：`GetMatmulPrecisionMode()` 是否**既读全局 `allow_hf32` 又读节点 `opImplMode`**（#1790 修复即改「节点级 OR 全局」）；核当前 ref 是否含该修复（PR #82099 / #82101）；
  - 清单点②：`GetNodeType()` 分支是否只覆盖 `MatMulV3`（`BatchMatMulV3` 等遗漏否；#1771 属性语义迁移是风险来源）；
  - 清单点③：是否存在 `GetAttrPointer<T>(<数字>)` 按位置索引取属性；
  - 清单点④⑤：失败分支是否静默 `return false`；`GetAllowHf32()` 返回值是否判空；
  - 清单点⑥：以 `ParseOpToGraphReduceSum13` 为样板，核对目标插件属性透传集合与 proto 属性集的差集（#1647 的 `noop_with_empty_axes` 即差集条目）；
  - 清单点⑦：以 `conv2d_transpose_fixpipe_fusion_pass.cc` 为样板，核对 Pass「读源节点属性 → 写新节点属性」是否配对（#1639 的 `attrGroups` 读/写跨函数，勿只扫 AddNode 邻域）；
  - 版本边界：载体③ `9.1.0-beta.2` 起已修复，载体①② `9.1.0` 起修复（实测 2026-09-16）——按当前 ref 逐载体核对修复提交。
- 最终判定以第 4/5/7 节口径为准，禁止凭算子类型直接下结论。

## 10. 能力边界与自检（v3.8）

### 能力边界

- **静态可证**：清单里能在源码内给出「`文件:行号` + 推导链」的部分，按第 7 节判据出卡。
- **需实测确认**：依赖运行时输入规模、设备行为或环境差异的结论，只能记观察项并附实测用例（证据等级见第 7 节）。
- **不覆盖**：本模式以外的机理（边界见第 0 节）与仓外框架侧行为；`TRIAGE.md` 只负责收敛候选，不构成判定依据。
- **找不到 ≠ 没有**：按清单未命中只说明「本轮未发现」，不得表述为「该算子无此缺陷」；抽样核查须在报告写明抽样口径。

### 自检

```bash
python3 scripts/gen_triage.py --check                          # 分诊表与映射一致
python3 scripts/scan_fp.py --only FP-B08 --format json <目标文件>  # 签名候选（非结论）
python3 scripts/verify_lines.py <报告.md> --root <被检仓>        # 行号校验
python3 check_fault_patterns.py                                # 全库守门
```

### 工作量与抽样（v4.0）

- **深度档：深度**（索引 `depth` 字段）——全量核查，不抽样。全部映射点 / 分支逐条过；单模式命中 > 50 处时按文件分片，并在报告写明分片口径。
- **报告必填**：抽样口径（全量 / 每点前 N 处 / 每类 N 例）+ 停止点记录；未写口径视为未完成。

## 11. 已知缺陷案例库：触发条件 / 根因 / 修复范式 / 针对性深挖（v5.1）

> 本节把本型**已确认缺陷**拆到代码级颗粒度（触发 → 根因/路径 → 修复范式 ✅ → 发现 → 复现锚）。修复范式为**示意**，路径取自卡片实证，**不臆造行号**。

### 案例 1｜fallback 回调只看全局 allow_hf32、漏读节点 opImplMode —— #1790（MatMulV3）

- **触发**：GE 图模式经 aclnn fallback 执行 MatMulV3，节点传 `opImplMode=0x40`（HF32）而全局 `allow_hf32` 关；aclnn 直调不触发。
- **根因**：`ops/built-in/op_fallback/fallback_common_2stages.cpp` 的 `GetMatmulPrecisionMode()` 只看全局 `GetAllowHf32()`，未读节点 `opImplMode` → HF32 未参与 `cubeMathType`。
- **修复范式（✅，示意）**：读节点 `opImplMode`（`ENABLE_HF32=0x40`）与全局 OR，并判空 `GetAllowHf32()`。
- **发现**：① 派发函数无 `GetAttr` ⇒ 只看全局；② `GetAllowHf32()` 未判空即 `strcmp` 会崩；③ `GetNodeType()` 仅 `MatMulV3`，`BatchMatMulV3` 漏。
- **复现锚**：`ge 图设 opImplMode=0x40`，GE 图 vs aclnn 直调对拍。
- **实证**：#1790 / PR #82099（master）+ #82101。

### 案例 2｜ONNX 插件未透传新增属性 noop_with_empty_axes —— #1647（ReduceSum）

- **触发**：ONNX13+ 新增 `noop_with_empty_axes`；前端升级引入新属性。
- **根因**：`ops/built-in/framework/onnx_plugin/reduce_sum_plugin.cc` 的 `ParseOpToGraphReduceSum13` 解析后未透传到 GE OP。
- **修复范式（✅，示意）**：属性纳入解析透传清单（属性名集 == proto 属性集）。
- **发现**：① 属性名清单 vs proto 差集（非空即漏）；② 核对修复提交 `cce77adb`。
- **复现锚**：ONNX13 reduceSum 带 `noop_with_empty_axes`，核对属性是否到 GE OP。
- **实证**：#1647（open；提交 `cce77adb`，MR !81676）。

### 案例 3｜fusion pass 未读源节点 groups / 未写新节点 —— #1639（ExtendConvTranspose）

- **触发**：A16W8 量化，conv2dtranspose 融合出 rearrange。
- **根因**：`conv2d_transpose_fixpipe_fusion_pass.cc` 未取源 `groups`（`CheckConv2dTransposeDescInfo`），建 rearrange 未写 `groups`（`CreateRearrangeOp`）→ ATC 失败；两侧变量 `attrGroups`，跨函数。
- **修复范式（✅，示意）**：

```cpp
GetInt(conv2dtransposeDesc_, GROUPS, attrGroups);  // 读端
SetInt(opDesc, GROUPS, attrGroups);                // 写端（另一函数）
```

- **发现**：① 按变量名跨函数核对读/写配对；② **只扫 AddNode 邻域会漏判**。
- **复现锚**：A16W8 + `groups>1` 走 ATC。
- **实证**：#1639（closed；提交 `1f65a691`，MR !81593）。

### 案例 4｜同族原型改属性（按位置索引风险）—— #1771（BatchMatMulV3）

- **触发**：原型把 `enable_hf32` 改 `opImplMode`。
- **根因**：`GetAttrPointer<T>(N)` 按位置索引，顺序/语义变更后静默取错。
- **修复范式（✅，示意）**：按属性名取，或索引与 proto 顺序一致性校验。
- **发现**：① grep `GetAttrPointer\s*<[^>]+>\s*\(\s*\d+\s*\)`；② 比对索引 N 与 proto 顺序。
- **复现锚**：属性顺序变更单测/门禁。
- **实证**：#1771（open）。

### 语料基线与深挖起手式
- 版本边界：载体③ 9.1.0-beta.2 起修复（早于 ①②）；①② 9.1.0 起修复。
- 起手：`python3 scripts/scan_fp.py --only FP-B08 --format json <文件>`。

## 12. 判据层（L2/L3）：出用例与判读前必读 <!-- BEGIN DETECT-SECTION (generated by scripts/sync_detect_section.py; do not edit) -->

> 生成物，勿手改（C42 校验）。完整判据见 [references/detect-l2-l3.md](references/detect-l2-l3.md)。

- **L2**：轴 属性/执行序列/内容取值｜观测 golden-utol｜至少 4 例
- **L3 `golden-utol`**：K91(假 FAIL)inf==inf 被判超容差；溢出类用例整批假 FAIL；K508(假 PASS)judge 列写成 JSON 会被静默忽略 → 回落 dtype 默认容差（fp16 rtol=1e-3）

> 判 FAIL 先排「假 FAIL」、判 PASS 先排「假 PASS/假绿」。**不查 L3 就出结论 = 报告作废。** <!-- END DETECT-SECTION -->
