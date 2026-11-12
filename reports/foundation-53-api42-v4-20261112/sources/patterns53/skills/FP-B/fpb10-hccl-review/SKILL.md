---
name: "fpb10-hccl-review"
description: "基于 FP-B10「集合通信算子功能/兼容问题（通信域/拓扑/图模式契约/同族实现不对称）」故障模式对指定集合通信算子做源码检视：定位实现，按拓扑下标越界、infershape 未 SetDim、配置窄化、同族精度不对称清单核查，产出证据链与 S×O 定级报告。当用户排查集合通信、AllToAll/ReduceScatter、通信结果错位时使用。"
---

# FP-B10 集合通信算子检视（fpb10-hccl-review）

对用户指定集合通信算子（如 AllToAllV）做 FP-B10 专项源码检视：定位算法模板 / infershape / executor / 调优插件实现，按五维清单逐项核查，每个结论给出**文件 + 行号 + 推导链**证据，命中即出 Bug 卡并输出报告。**本模式特殊纪律：① 本型覆盖**计算算子不具备的四个维度**——通信域与 rank 拓扑、图模式 shape/维度契约、通信域匹配与配置校验、同族算法实现对称性（+ 跨模式/跨版本路径差异）；② 「声明了动态语义却没写进 IR」是形态② 的核心——**只打日志不算**，必须真的调用 `SetDim(i, ge::UNKNOWN_DIM)`；③ 判别性指纹与审查关键词必须分开——拓扑变量（`subCommRanks_` 等）实测命中 1952 次，**不可作判别性指纹**，只作定位提示；④ 集合通信**等待超时 / 挂死**按边界归 FP-G01，本条只承载功能 / 精度 / 性能 / 兼容面；⑤ 多级拓扑与多卡行为须实机验证，静态只能立候选点位。**

## 0. 与相邻模式的边界

| 相邻模式 | 分工 |
|---|---|
| FP-G01（执行挂死与调度超时） | **边界约定（互指避免重复收料）**：**等待超时 / 挂死**归 G01 子型②；本条只承载功能 / 精度 / 性能 / 兼容面。#141（`BatchSendRecvOutPlace` 泄漏）的**挂死/闪退后果**按 G01 子型⑤ 承载，本条承载其资源/功能面成因 |
| FP-B01（支持面校验过严误拦截合法输入） | #740「算法配置解析拒绝**已注册的** MeshSingleChannel 模板名」是校验过严的通信侧呈现——过拦归 B01，本条承载通信域/拓扑/契约面 |
| FP-B07（索引/偏移计算错误致越界） | #744 越界读机理同为索引/偏移错误，但**载体是通信域拓扑变量**而非 tensor 偏移——机理同、载体异，报告双向关联 |
| FP-A03（低精度中间量） | #275 的 u64→float 丢精度属低精度中间量——精度机理归 A03，本条承载同族实现不对称这一**成因面** |
| FP-A19（同算子多路径覆盖盲区） | 同一通信算子存在 AICPU/AICore 与多级拓扑**多条路径**，覆盖盲区同样适用——本条形态⑤ 的跨模式路径差异可视为 A19 的通信侧投影 |
| FP-F03（文档/声明面与实现面不一致） | #106 前向兼容声明与各版本实际支持面需逐一核对——声明面归 F03，本条承载版本错配下的功能表现 |

**症状反查定位**：通信结果错位、部分输出列恒为 0 → 多级拓扑下标与切分（形态①）；图编译期 shape 推导与实际不符、日志与代码不一致 → infershape 是否真的 `SetDim(..., UNKNOWN_DIM)`（形态②）；配置解析静默错配、schema 不报错但算法 cost 被改写 → 配置读取是否 `get<T>()` 直接窄化（形态③）；大数据量（跨 2^24）切片不均致精度不达标 → 同族 executor 精度类型/取整是否对称（形态④）；新功能在老 toolkit 下返回「不支持」、AICPU 与 AICore 行为不一 → 跨模式/跨版本路径差异（形态⑤）。**先按症状锁定形态，再进清单。**

## 1. FP-B10 模式卡摘要（检视依据，源自本库 `patterns/FP-B/FP-B10.md`，v3.1）

- **编号 / 名称**：FP-B10 集合通信算子功能/兼容问题（通信域 / 拓扑 / 图模式契约 / 同族实现不对称） ｜ **类别**：功能/兼容 ｜ **风险**：高（S3×O3=9）｜ **状态**：活跃
- **适用声明头**（照抄卡片）：仓 hccl ｜ 侧别 Host,Kernel ｜ 载体 Host源码,Kernel源码 ｜ 触发 Hccl|HCCL|AllReduce|AllGather|AllToAll|ReduceScatter ｜ 默认启用 true
- **skill 核查面**：与卡片载体一致——hccl 仓内集合通信算子的算法模板（`src/ops/{op}/algorithm/template/`）、图模式 infershape（`src/ops/{op}/op_graph`）、executor（`src/ops/{op}/executor/`）与调优插件（`examples/07_tuner_plugin/`）；覆盖 Host 与 Kernel 两侧。
- **故障机理**：集合通信算子（AllReduce / AllGather / AllToAllV / ReduceScatter / Scatter / Broadcast / Send / Recv）故障集中于**计算算子不具备的四个维度**：① **通信域与 rank 拓扑结构假设错误**——模板把多级 rank 结构（如二维 Mesh `subCommRanks_`）收缩后仍按下标取多级元素，越界读污染拓扑变量，下游取模可致整数除零；② **图模式 shape/维度契约未落实**——infershape 在 count 非常量（编译期不可知）时把输入形状**原样赋给输出并返回成功**，日志称已标记未知维而代码从未 `SetDim(0, ge::UNKNOWN_DIM)`，属「声明了动态语义却没写进 IR」；③ **通信域匹配与配置校验缺失**——调优插件用 `get<uint32_t>()` 直接取配置，不拒窄化与负数回绕，超大 rank 数被截断成真实 rank 数从而**错误命中通信域**并改写算法 cost；④ **同族算法实现不对称**——功能等价的 executor 精度类型选用不一致（Broadcast 用 `float()`、AllReduce 用 `double()`+`std::floor`），前者数据量 >2^24 时丢精度致切片不均；⑤ **跨模式/跨版本算法路径差异**——同一算子在 AICPU 与 AICore、单级与多级拓扑、不同 toolkit 版本下实现与约束各异（含 CCLBuffer 配置阈值与「新包在旧 toolkit 下不支持」）。
- **触发条件**：多级或复杂拓扑（Mesh 1D/2D、UBX、超大 rank 数、奇数 rank 数）；`send_counts`/`recv_count` 为非常量（图编译期不可知）；配置值超 `uint32_t` 或为负；数据量跨越 2^24 的 Broadcast / 切分类算子；**AICPU 模式 + CCLBuffer 配置 >2GB**；CANN 版本与 toolkit 版本错配；跨版本复用 tiling/kernel。
- **典型表现**：通信结果错位、部分输出列恒为 0；图编译期 shape 推导与实际不符（日志与代码不一致）；初始化连接超时、个别 rank 掉线；越界读污染通信域变量；大数据量切片不均致精度不达标；配置解析**静默错配**（schema 不报错、算法 cost 被改写）；新功能在老 toolkit 下返回「不支持」。
- **源码审查映射点**：多级 rank 结构（`subCommRanks_`、`commRanks_`、`templateRankSize_`、mesh 维度）规模与下标是否成对校验；`*InferShape*` 中未知维是否**真的**调用 `SetDim(i, ge::UNKNOWN_DIM)`（**只打日志不算**）；配置读取是否 `get<T>()` 直接窄化（应前置 `is_number_unsigned` 或范围校验）；同族 executor 精度类型与取整是否对称；AICPU 与 AICore 两条路径约束是否**分别**声明与校验；`HCCL_CONNECT_TIMEOUT`/`HCCL_EXEC_TIMEOUT`/`HCCL_RETRY_CNT`/`HCCL_DFS_CONFIG` 默认值与文档是否一致；跨版本复用（v4 复用 v3 tiling/kernel）时上游新增 tilingkey 是否同步适配。
- **检测签名（判别性指纹，命中即候选缺陷点位）**：`float\s*\(\s*\w*[Ss]lice[Cc]ount`（u64→float 丢精度，实测 **1 处**）；`get\s*<\s*(u?int(32|64)_t|size_t)\s*>\s*\(\s*\)`（配置读取直接窄化，**须人工确认同函数内无范围校验**，实测 13 处）。
- **审查关键词（`keywords` 字段；命中只表示该处值得按上文映射点人工审，非缺陷候选）**：`subCommRanks_|commRanks_|templateRankSize_`（拓扑变量——⚠️ 实测 **1952 次**，遍布拓扑模板基础设施，**不可作判别性指纹**）；`HCCL_(CONNECT|EXEC)_TIMEOUT|HCCL_RETRY_CNT|HCCL_DFS_CONFIG`（超时/重试配置项名，实测 15 处）；`SetDim\s*\(\s*\w+\s*,\s*ge::UNKNOWN_DIM`（**对照组锚点**：命中 = 已正确置未知维，真正缺陷是「声明支持动态 count 却**没有**它」，属跨行差集、单行正则表达不了）。
- **测试拦截建议**：① **多级拓扑矩阵**——同一算子在最简拓扑（单机 2 卡）与最复杂拓扑（多级 Mesh/UBX、非 2 的幂 rank、奇数 rank）下对拍；② **count 非常量用例**——`send_counts`/`recv_count` 作**图输入**（编译期不可知）非常量，断言 shape 推导并**在 IR 上校验**置未知维（不只看日志）；③ **配置边界**——rank 数类配置给 `2^32±k` 与负值，断言明确报错而非静默错配；④ 数据量跨 **2^24** 的 Broadcast / 切分类算子必须建例；⑤ **AICPU 与 AICore 双路径对拍**（含 CCLBuffer 跨 2GB）；⑥ **通信算子精度用例需单独建库**——现有精度矩阵几近只覆盖计算算子，HCCL 侧等同空白。
- **实证案例**：cann/hccl **#744**（open）多级结构收缩后仍取 `[1]` → 越界读污染拓扑变量；**#749**（open）声明动态 count 却从未 `SetDim(0, ge::UNKNOWN_DIM)`；**#738**（open）`get<T>()` 窄化致**错误命中通信域并改写 cost**；**#275**（closed）u64→float 丢精度致大数据量切片不均；**#609**（closed）ReduceScatter concurrent + AICPU + CCLBuffer>2GB 精度问题；**#141**（closed）`BatchSendRecvOutPlace` 异常分支泄漏致内存耗尽、**任务卡死/闪退**；**#106**（closed）新包在旧 toolkit 下新功能**返回错误（不支持）**。**语料统计（2026-09-19 全量抓取）**：cann/hccl 共 **714 条** issue（功能/异常/失败 **302**、集合通信关键词命中 **235**、超时/挂死 **16**、精度 **3**）——**证明「集合通信是独立且高发的故障域」**。各案文件路径、基线 commit 与修复范式详见 §11 案例库与 §9 示例速览。
- **关联**：FP-G01（**边界约定**：等待超时 / 挂死归 G01 子型②）、FP-B01（#740 校验过严在通信侧的呈现）、FP-B07（#744 越界读机理同为索引/偏移错误，载体是通信域拓扑变量）、FP-A03（#275 u64→float 丢精度）、FP-A19（AICPU/AICore 与多级拓扑多路径盲区）、FP-F03（#106 前向兼容声明与各版本支持面核对）。

## 2. 检视输入与算子定位

**输入**：集合通信算子名（必填，如 `AllToAllV`、`ReduceScatterV`、`Broadcast`、`ReduceScatter`、`Scatter`、`BatchSendRecv`）；可选 ref（默认 master）；可选现象描述（结果错位 / 部分列恒 0 / 编译期 shape 不符 / 精度不达标 / 返回不支持——症状反查用）；可选拓扑与版本信息（Mesh 维度 / rank 数 / AICPU 或 AICore / toolkit 版本——形态①⑤ 关键输入）。

**算子名 → 实现定位**（卡片适用声明为仓 `hccl`；GitCode 目录列表确认实际仓名）：

```text
cann/hccl/
├── src/ops/{op_name}/
│   ├── algorithm/template/   # 算法模板——形态① 多级 rank 拓扑下标主检视面（如 all_to_all_v）
│   ├── op_graph/             # 图模式 infershape——形态② 未知维契约主检视面（如 reduce_scatter_v）
│   └── executor/             # executor——形态④ 同族精度/取整对称性检视面（如 broadcast）
├── examples/07_tuner_plugin/ # 调优插件——形态③ 配置读取窄化主检视面（plugin.cpp）
└── （版本/兼容声明与 tiling/kernel 复用点）  # 形态⑤ 跨模式/跨版本路径
```

**定位顺序**（按症状反查确定优先面）：结果错位 / 部分列恒 0 → `algorithm/template/`；编译期 shape 不符 → `op_graph/` 的 `*InferShape*`；配置静默错配 → `examples/07_tuner_plugin/`；大数据量精度 → `executor/`；AICPU/AICore 或版本差异 → 算法路径与 tiling/kernel 复用点。

## 3. 取数方式（Important）

公开网页端点被拦截，**必须走 API**（均需带 `User-Agent`；失败重试 2 次、间隔 5 秒）：

| 用途 | 端点 |
|---|---|
| 目录列表 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/contents/{path}?ref={ref}` |
| 单文件内容 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/raw/{path}?ref={ref}` |
| Issue 查重 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/issues?q={关键词}` |

**已实测不可用（截至 2026-09 实测）**：`https://gitcode.com/{repo}/raw/{sha}/{path}`、`https://raw.gitcode.com/...` → 403 或拦截页；策略变化可复测。本地已有克隆则优先直接读，行号以本地 HEAD 为准并记录 commit。**本模式特有取数限制**：多级拓扑、多卡 rank 掉线、切片不均精度、AICPU/AICore 与版本错配等均需**多卡实机**验证——静态检视产出「拓扑下标未成对校验 / 未真的 `SetDim` / 配置窄化 / 同族精度不对称」候选点位与拓扑/配置矩阵方案；**精度类语料稀少**（2026-09-19 全仓仅 3 条），通信算子精度用例需单独建库，不得以「无 issue」推断无缺陷。

## 4. 五维检视清单（每点：查什么 → 何处 → 命中判据）

对 algorithm/template、op_graph、executor、调优插件逐点核查，**每点先查命中面、再做反证排除**，已有的拓扑校验与 `SetDim` 也记录（防护面证据）。**判别性指纹（`float(sliceCount)`、`get<T>()`）命中即候选点位；审查关键词（拓扑变量等）只作定位提示，不可单独作命中判据。**

### ① 通信域与 rank 拓扑结构假设（多级拓扑下标）
- 查什么：多级 rank 结构（`subCommRanks_`、`commRanks_`、`templateRankSize_`、mesh 维度）**规模与下标是否成对校验**——模板把多级结构收缩为单层后是否仍按下标取多级元素（#744：Mesh1D 收缩后仍取 `[1]`，越界读污染 `templateRankSize_`，下游取模可能除零）。
- 何处：`src/ops/{op}/algorithm/template/` 的拓扑变量下标访问点。
- 命中判据：存在「结构规模 N 但下标 ≥ N」的静态路径（或规模与下标未成对校验）⇒ 命中（样板 #744）。

### ② 图模式 shape / 维度契约落实（未知维真的写进 IR）
- 查什么：`*InferShape*` 在 count 非常量（编译期不可知）时是否**真的调用** `SetDim(i, ge::UNKNOWN_DIM)` 并把输出 shape 相应置未知维——**只打日志不算**（#749：日志称 "shape first dim is unknown"，代码从未 `SetDim(0, ge::UNKNOWN_DIM)`，且把输入形状原样赋给输出并返回成功）。
- 何处：`src/ops/{op}/op_graph` 的 `*InferShape*` 实现。
- 命中判据：存在「声明支持动态 count（日志/注释/契约）但无 `SetDim(..., UNKNOWN_DIM)`」的**跨行差集** ⇒ 命中（锚点 `SetDim(..., ge::UNKNOWN_DIM)` 命中处为已正确实现）。

### ③ 通信域匹配与配置校验（配置读取窄化）
- 查什么：配置读取是否用 `get<uint32_t|uint64_t|size_t>()` **直接窄化**、不拒负数回绕——应前置 `is_number_unsigned` 或范围校验（#738：`min_ranks`/`max_ranks` 设 `4294967304`（2^32+8）转成 8，schema 不报错，插件错误命中 8-rank 通信域并改写 cost）。
- 何处：`examples/07_tuner_plugin/plugin.cpp` 的 `ParseMatchField` 类配置解析函数；通信域匹配与算法 cost 计算点。
- 命中判据：`get<T>()` 直接取值且同函数内**无范围/无符号校验**，且该值参与通信域匹配或 cost 计算 ⇒ 命中（实测 13 处，须逐处确认）。

### ④ 同族算法实现的精度/取整对称性
- 查什么：功能等价 executor **精度类型与取整方式是否对称**——如 Broadcast 用 `float()` 转 u64 `sliceCount`、AllReduce 用 `double()`+`std::floor`；前者数据量 >2^24 时丢精度致切片不均（#275）。
- 何处：`src/ops/{op}/executor/` 各算子切片/取整实现；同族（AllReduce / Broadcast / ReduceScatter 等）横向比对。
- 命中判据：`float(sliceCount)` 类 u64→float 转换（判别性指纹）且无高位保护，或同族取整不一致 ⇒ 命中（样板 #275）。

### ⑤ 跨模式 / 跨版本算法路径差异
- 查什么：AICPU 与 AICore 两路径约束是否**分别**声明与校验；CCLBuffer 阈值（>2GB）在 AICPU 模式下的行为（#609）；跨版本复用 tiling/kernel（v4 复用 v3）时上游新增 tilingkey 是否同步适配；新包在旧 toolkit 返回「不支持」（#106）的支持面声明是否与实际一致。
- 何处：算法路径分叉点、CCLBuffer 配置处理、tiling/kernel 复用点、版本兼容声明。
- 命中判据：存在「两路径约束未分别校验」或「跨版本复用未适配新 tilingkey」或「声明支持但旧 toolkit 返回不支持」的静态路径 ⇒ 命中（或立观察项，视能否静态确证）。

### 横切面：超时/重试配置与语料基线
- 查什么：`HCCL_CONNECT_TIMEOUT`/`HCCL_EXEC_TIMEOUT`/`HCCL_RETRY_CNT`/`HCCL_DFS_CONFIG` 默认值与文档是否一致（实测 15 处）；**等待超时/挂死归 FP-G01**，本条只记录配置面一致性。语料基线（714 条 / 302 功能异常 / 235 关键词命中）作「高发故障域」佐证，引用须注明时点。
- 何处：配置项定义与文档。
- 命中判据：默认值与文档不一致 ⇒ 记观察项；挂死/超时后果按边界转 FP-G01。

## 5. 检视流程

1. **定界**：确定算子与优先检视面（按症状反查）、确认 ref 与目标仓（卡片 `hccl`，目录列表确认实际仓名）；记录拓扑与版本信息。
2. **枚举**：目录列表 + 文件名检索列出 `algorithm/template/`、`op_graph/`、`executor/`、`examples/07_tuner_plugin/` 文件清单。
3. **触发词扫描**：按判别性指纹 `float\s*\(\s*\w*[Ss]lice[Cc]ount`、`get\s*<\s*(u?int(32|64)_t|size_t)\s*>\s*\(\s*\)`，与审查关键词 `subCommRanks_|commRanks_|templateRankSize_`、`HCCL_(CONNECT|EXEC)_TIMEOUT|HCCL_RETRY_CNT|HCCL_DFS_CONFIG`、锚点 `SetDim\s*\(\s*\w+\s*,\s*ge::UNKNOWN_DIM` 定位风险面（本地 grep；API 模式逐文件拉取后查）。**拓扑变量命中量大（实测 1952 次），只作定位提示。**
4. **五维逐项核查**：按第 4 节 ①~⑤ + 横切面逐点记录命中面与防护面证据（文件:行号）；对 ② 做**「声明动态语义 vs 实际 SetDim」跨行差集**；对 ④ 做**同族 executor 横向比对**。
5. **反证排除**：拓扑规模与下标成对、真的 `SetDim(..., UNKNOWN_DIM)`、配置读取有范围校验、同族精度/取整对称、两路径约束分别校验 → 写出反证理由（防护面证据）。
6. **判定**：按第 7 节给 命中 / 观察项 / 反证排除。
7. **GitCode 查重**（仅命中项）：issues API 按算子名 + `拓扑|rank|shape|count|精度|窄化|不支持|错位` 检索，逐条比对同机理；无同机理才立卡。
8. **业务可达性核查**（仅命中项）：判 B 等级、定影响类型、给处置建议；默认保守（无法证明不可达即 B3），降档附证据；B 不改 S×O。
9. **出报告**：按第 8 节模板落盘；静态结论一律附**多级拓扑矩阵 + count 非常量 + 配置边界 + 2^24 数据量 + AICPU/AICore 对拍**方案（多卡实机）。

## 6. 风险定级（S×O）与业务影响评估（B 轴）

- **S**：S3（结果错位 / 部分输出列恒为 0 / 大数据量精度不达标——分布式训练结果错误，定位极难）；S2（配置静默错配、新功能在旧 toolkit 返回不支持——功能受限 / 性能劣化）；S1（配置默认值与文档不一致等一致性面）。
- **O**：O3 = ≥2 条独立实证；O2 = 1 条；O1 = 仅静态扫描命中或团队笔记（实证 = 确认对应 issue/PR，或经跨仓、跨分支核验确认的缺陷记录，同权计入）。静态推演无实证默认 **O1**；升档须给实证依据。
- **风险 = S×O**：≥6 高；3/4 中；1/2 低。FP-B10 基准：模式卡整体 S3×O3=9（高）；纯静态命中 S3×O1=3（中，暂定，多卡实测后复评）。

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

- **判别性指纹 vs 审查关键词必须分开**：`float(sliceCount)`、`get<T>()` 是**判别性指纹**（命中即候选点位）；`subCommRanks_|commRanks_|templateRankSize_` 是**审查关键词**（实测 1952 次，只作定位提示），**不可单独作命中判据**；`SetDim(..., UNKNOWN_DIM)` 是**对照组锚点**（命中 = 已正确实现），真正缺陷是「声明支持动态 count 却没有它」的跨行差集。
- **三种判定**：
  - **命中**（可静态证缺陷路径）：「拓扑规模与下标未成对」「声明动态语义但无 `SetDim`」「配置读取窄化无范围校验」「同族精度/取整不对称」的完整推导链 → 立 Bug 卡；
  - **观察项**：多卡行为/精度后果需实机验证、跨版本兼容需版本矩阵核对、配置默认值与文档不一致 → 记录并附实测方案；
  - **反证排除**：拓扑规模与下标成对、`SetDim` 在位、配置有范围校验、同族对称 → 写出防护面证据。
- **边界不许越界**：集合通信**等待超时 / 挂死**一律转 FP-G01（子型②；#141 泄漏致挂死后果按 G01 子型⑤），本条不重复收料。
- **无 issue 不是安全证据**：通信算子精度用例语料稀少（2026-09-19 仅 3 条），不得以「无 issue」推断无缺陷；须主动建多级拓扑 / 2^24 数据量用例。
- **语料统计须带时点**：714 条 / 302 / 235 / 16 / 3 为 2026-09-19 全量快照，引用须注明时点。
- **不臆造行号**：每条证据须实际读到的 文件:行号；引用实证样板（#744 / #749 / #738 / #275 / #609 / #141 / #106）须给出仓内文件位置，行号漂移时注明基线 commit（如 #744 基线 `27d0ea5a`）。

### 判定纪律补充（v3.6）：非对称增减、证据等级与误判记录

**增减不对称**：允许追加候选（有据即可，错了可由用户排除）；**撤销或否决候选必须附 `[文件]:[行号] [代码行]` 负向证据**。无证据的「看起来没问题」一律记为「未核查」，不得计入反证排除，也不得据此下调等级——否决造成的漏报用户不可见、不可恢复。

- **证据等级**（Bug 卡必填）：`静态可证` = 推导链完整且触发输入可静态构造；`需实测确认` = 依赖运行时输入规模、设备行为或环境差异。标 `需实测确认` 的条目**不得以「命中」名义出卡**，按观察项记录并附实测用例。
- **Agent 误判记录**（Bug 卡必填）：本次被推翻的假设、推翻它的证据（`[文件]:[行号] [代码行]` 或实测输出）、判定标准是否随之修订；无推翻写「无」。
- **误判回流**：同类误判在 3 次检视中重复出现，登记至 `cases/misjudgments.jsonl`（字段见 `cases/README.md`），并在本模式判定标准中新增对应防线；守门 C19d 校验台账字段合法。

## 8. 产出模板

### Bug 卡字段（命中项必备）

```markdown
### BUG-YYYYMMDD-XX {算子名}（hccl，{新增/存量}）
- **算子名**：{AllToAllV / ReduceScatterV / Broadcast / ReduceScatter / BatchSendRecv 等}
- **命中形态**：① 拓扑下标越界 / ② 未真的 SetDim / ③ 配置窄化 / ④ 同族精度不对称 / ⑤ 跨模式跨版本路径差异
- **文件路径与行号证据**：
  - `{文件}:{行号}`：{拓扑下标访问 / 原样赋输出 shape / get<T>() 窄化 / float(sliceCount) 转换}
  - `{文件}:{行号}`：{应处位置（或标注「缺失」）/ 同族正确实现（如 AllReduce 的 double()+std::floor）/ 对照组锚点 SetDim}
  - 防护面记录（反证检查结果）：{文件}:{行号}
- **FP-B10 模式编号**：FP-B10 集合通信算子功能/兼容问题（通信域 / 拓扑 / 图模式契约 / 同族实现不对称）
- **S×O 风险定级**：S3（结果错位 / 精度不达标）× O1（静态命中无实证）= 3，中（暂定，多卡实测后复评）
- **证据等级**：{静态可证 / 需实测确认}｜{一句话理由}
- **业务影响评估（B 轴）**：可达性 B{3|2|1}（{一句话判据}）｜ 业务影响：{静默精度损失/任务失败中断/性能退化/仅可观测性}｜ 证据：{调用方/公开负载/为何不可达}｜ 处置建议：{尽快修/排期修/记录}
- **故障机理推导链**：{多级结构收缩后下标越界 → 污染拓扑变量 → 取模除零 / 声明动态 count 但无 SetDim → IR 形状错误 / 配置窄化 → 错误命中通信域并改写 cost / float 转换 u64 → 大数据量切片不均}
- **触发条件可达性分析**：{拓扑（Mesh 维度/rank 数）/ count 是否非常量 / 配置取值（2^32±k、负值）/ 数据量是否跨 2^24 / AICPU 或 AICore / toolkit 版本}。静态推演，需多卡实机确认
- **复现与对拍方案**：{多级拓扑矩阵；count 非常量图输入并 IR 校验置未知维；配置边界；数据量跨 2^24；AICPU/AICore 双路径（含 CCLBuffer 跨 2GB）}
- **建议修复方案**：{拓扑规模与下标成对校验 / 补 SetDim(i, ge::UNKNOWN_DIM) 并置输出未知维 / 配置读取前置范围校验 / 同族统一 double()+std::floor}
- **Agent 误判记录**：{被推翻的假设 → 推翻证据 `[文件]:[行号] [代码行]`；无则「无」}
- **GitCode 查重**：{issues API 检索结论，无同机理 issue 才立卡}
```

### 检视报告结构

```markdown
# FP-B10 检视报告：{算子名}（YYYY-MM-DD）
## 一、执行概览（仓/ref/HEAD、现象与优先形态、拓扑/版本信息、文件清单、判定统计：命中 X / 观察项 Y / 反证排除 Z；命中项 B 轴分布 B3×a / B2×b / B1×c）
## 二、命中明细（Bug 卡，按第 8 节字段，每卡含 B 轴业务影响评估）
## 三、观察项（表：# / 形态 / 文件:行号 / 存疑点 / 多卡实测方案）
## 四、反证排除（表：形态点 / 反证理由 / 防护面证据，含同族对照）
## 五、多卡验证建议（多级拓扑矩阵、count 非常量 + IR 置未知维校验、配置边界、2^24 数据量、AICPU/AICore 双路径、通信精度用例建库）
```

> 报告须在「执行概览」标注证据等级分布（静态可证 X / 需实测确认 Y），并在文末单列「Agent 误判记录」小节（无则写「无」）。

报告落盘到当前任务工作区，建议命名 `FP-B10检视_{算子名}_YYYYMMDD.md`。

## 9. 示例速览：AllToAllV

- **定位**：`cann/hccl` → `src/ops/all_to_all_v/algorithm/template/`（#744 越界读位置，基线 `27d0ea5a`）；同仓对照：`reduce_scatter_v/op_graph`（#749 `HcomReduceScatterVInferShapeV2`）、`examples/07_tuner_plugin/plugin.cpp`（#738 `ParseMatchField`）、`broadcast/executor/ins_v2_broadcast_parallel_executor.cc`（#275）；另 #609（ReduceScatter concurrent + AICPU + CCLBuffer>2GB）、#141（`BatchSendRecvOutPlace` 泄漏）、#106（前向兼容）。
- **检视面提示**（引导，不预设结论，仍须逐点核查；行号以本地 HEAD 为准）：形态① 核 AllToAllV Mesh1D 模板 `subCommRanks_` 收缩为单层后是否仍取 `[1]`（#744 越界读污染 `templateRankSize_`，取模可能除零）；形态② 核 `HcomReduceScatterVInferShapeV2` 是否原样赋输出并返回成功且无 `SetDim(0, ge::UNKNOWN_DIM)`（#749）；形态③ 核 `ParseMatchField` 的 `get<uint32_t/size_t/uint64_t>()` 有无范围/无符号校验（#738 的 2^32+8 → 8 静默错配）；形态④ 核切片/取整是否与同族对称（#275）；形态⑤ 核 AICPU/AICore 两路径约束是否分别校验、CCLBuffer 阈值（#609）、跨版本 tilingkey 适配、旧 toolkit 支持面（#106）；横切面核超时/重试配置默认值与文档一致性（**挂死/超时按边界转 FP-G01**）。
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
python3 scripts/scan_fp.py --only FP-B10 --format json <目标文件>  # 签名候选（非结论）
python3 scripts/verify_lines.py <报告.md> --root <被检仓>        # 行号校验
python3 check_fault_patterns.py                                # 全库守门
```

### 工作量与抽样（v4.0）

- **深度档：深度**（索引 `depth` 字段）——全量核查，不抽样。全部映射点 / 分支逐条过；单模式命中 > 50 处时按文件分片，并在报告写明分片口径。
- **报告必填**：抽样口径（全量 / 每点前 N 处 / 每类 N 例）+ 停止点记录；未写口径视为未完成。

## 11. 已知缺陷案例库：触发条件 / 根因 / 修复范式 / 针对性深挖（v5.1）

> 颗粒度：触发条件 → 根因（具体路径）→ 修复范式（✅ 示意）→ 针对性发现 → 最小复现锚。修复范式为**示意**；路径取卡片实证，行号以本地 HEAD 为准，**不得臆造**。

### 案例 1｜多级结构收缩后取多级下标 → 越界读污染拓扑变量 —— #744（AllToAllV）

- **触发**：Mesh1D 多级拓扑走 AllToAllV 模板（基线 `27d0ea5a`）。
- **根因**：`src/ops/all_to_all_v/algorithm/template/` 把 `subCommRanks_` 收缩为单层后仍取 `[1]` → 越界读污染 `templateRankSize_` → 取模可致除零 → 结果错位。
- **修复范式（✅，示意）**：
```cpp
rank = subCommRanks_[1];                    // ❌ 越界读
if (subCommRanks_.size() <= idx) return HCCL_E_PARA;   // ✅ 规模与下标成对校验
```
- **针对性发现**：① grep `subCommRanks_` 定位下标点（全仓 1952 次，仅提示）；② 下标须 < 结构规模。
- **最小复现锚**：Mesh1D 多卡 vs 单机 2 卡对拍 AllToAllV。
- **实证**：#744（open）。

### 案例 2｜声明动态 count 却从未写 UNKNOWN_DIM —— #749（ReduceScatterV）

- **触发**：`recv_count`/`send_counts` 作**图输入**（编译期不可知）。
- **根因**：`src/ops/reduce_scatter_v/op_graph` 的 `HcomReduceScatterVInferShapeV2` 把输入形状**原样赋给输出并 return 成功**，日志称 unknown 却**从未** `SetDim(0, ge::UNKNOWN_DIM)`。
- **修复范式（✅，示意）**：
```cpp
outputShape->SetDim(0, ge::UNKNOWN_DIM);    // ✅ 真的写进 IR
```
- **针对性发现**：① grep 锚点 `SetDim(\w+, ge::UNKNOWN_DIM)`（命中=已正确）；② 跨行差集：有 unknown 日志无 `SetDim` ⇒ 命中（**只打日志不算**）。
- **最小复现锚**：count 作 graph 输入，IR 上校验置未知维。
- **实证**：#749（open）。

### 案例 3｜配置 get<T>() 直接窄化 → 错误命中通信域并改写 cost —— #738（调优插件）

- **触发**：`min_ranks`/`max_ranks` 超 `uint32_t` 或为负。
- **根因**：`examples/07_tuner_plugin/plugin.cpp::ParseMatchField` 用 `get<uint32_t>()` **不拒窄化**；`4294967304`（2^32+8）被转成 **8** → **错误命中 8-rank 通信域** → cost 2→0。
- **修复范式（✅，示意）**：
```cpp
uint32_t v = json.get<uint32_t>();          // ❌ 负数回绕 / 超大值截断
if (!json.is_number_unsigned() || json.get<uint64_t>() > kMaxRankSize) return false;  // ✅
```
- **针对性发现**：① grep 指纹 `get<(u?int(32|64)_t|size_t)>()`（实测 13 处）；② 无范围校验且值参与通信域匹配或 cost ⇒ 命中。
- **最小复现锚**：配置给 `2^32±k` 与负值，断言明确报错而非静默错配。
- **实证**：#738（open）。

### 案例 4｜同族 executor 精度类型不对称 → 大数据量切片不均 —— #275（Broadcast vs AllReduce）

- **触发**：Broadcast 数据量跨 **2^24（16M）**。
- **根因**：`src/ops/broadcast/executor/ins_v2_broadcast_parallel_executor.cc` 用 `float()` 转 u64 `sliceCount`，>2^24 丢精度致切片不均；AllReduce 却用 `double()`+`std::floor`——同族不对称。
- **修复范式（✅，示意）**：
```cpp
uint64_t slice = (uint64_t)std::floor((double)sliceCount);   // ✅ 与 AllReduce 对齐
```
- **针对性发现**：① grep 指纹 `float(\w*[Ss]lice[Cc]ount`（实测 1 处）；② 同族精度/取整不对称且无高位保护 ⇒ 命中。
- **最小复现锚**：数据量跨 2^24 的 Broadcast 与 AllReduce 对拍。
- **实证**：#275（closed）。

### 语料基线与深挖起手式

- 深挖：`python3 scripts/scan_fp.py --only FP-B10 --format json <目标文件>`；语料 cann/hccl **714 条**（2026-09-19：关键词 235、超时/挂死 16、精度 3，拓扑变量 1952 次仅定位提示）。同型其余 **#609**（AICPU+CCLBuffer>2GB）、**#106**、**#141**（泄漏，挂死归 FP-G01）。

## 12. 判据层（L2/L3）：出用例与判读前必读 <!-- BEGIN DETECT-SECTION (generated by scripts/sync_detect_section.py; do not edit) -->

> 生成物，勿手改（C42 校验）。完整判据见 [references/detect-l2-l3.md](references/detect-l2-l3.md)。

- **L2**：轴 shape 维度/并发/同步｜观测 golden-utol｜至少 4 例
- **L3 `golden-utol`**：K91(假 FAIL)inf==inf 被判超容差；溢出类用例整批假 FAIL；K508(假 PASS)judge 列写成 JSON 会被静默忽略 → 回落 dtype 默认容差（fp16 rtol=1e-3）

> 判 FAIL 先排「假 FAIL」、判 PASS 先排「假 PASS/假绿」。**不查 L3 就出结论 = 报告作废。** <!-- END DETECT-SECTION -->
