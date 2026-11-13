---
name: "fpb07-aclnn-review"
description: "基于 FP-B07「索引/偏移计算错误致越界」故障模式对指定 aclnn 接口（如 aclnnIndexAdd）做源码级缺陷检视：定位算子实现，按六成因清单核查整型溢出与偏移计算错误，产出带文件行号证据链与 S×O 定级的 Bug 卡与检视报告。当用户给出 aclnn 接口名要求做 FP-B07 检视、越界类缺陷排查或 aic error/coredump/后段输出全 0 根因定位时使用。"
---

# FP-B07 aclnn 接口检视（fpb07-aclnn-review）

对用户指定的 aclnn 接口（如 aclnnIndexAdd）做 FP-B07 专项源码检视：先定位算子实现，再按六成因清单逐项核查，每个结论给出**文件 + 行号 + 推导链**证据，命中即出 Bug 卡，输出检视报告。

## 0. 与相邻模式的边界

| 相邻模式 | 分工 |
|---|---|
| FP-A18（int32 边界值转 float 舍入） | **边界**：同一 int32 主题的两个面——FP-B07 管**整型承载与符号语义**（int32 存元素数/地址的溢出、截断、回绕、方向），FP-A18 管**转 float 后的舍入比较语义**；#1928 index_fill 数据量超 int32 两者交叠，按主导机理归属，报告双向关联 |
| FP-B04（空指针校验缺失） | 越界写常伴随空指针/未校验的指针基线：指针基线缺失归 FP-B04，**索引/偏移算错**致越界归 FP-B07 |
| FP-B06（空 tensor 分支缺失） | 空/0 元素输入是索引越界的**极端输入形态**：判空分支缺失归 FP-B06，非空输入下偏移算错归 FP-B07 |
| FP-A05（脏数据/数据踩踏） | 越界写是脏数据的**来源之一**：越界写本身归 FP-B07，其引入的未定义数据读用归 FP-A05，报告可双向关联 |
| FP-D01（容量） | workspace/偏移申请不足同源：**申请量算少**归 FP-D01，偏移算式本身错归 FP-B07 |
| FP-A04（静默精度错误） | 成因⑥ 的**静默型**表现（后段输出全 0、无任何报错）落在 FP-A04「不报错地输出部分结果」上——只按本条主症状（aic error / 错位）比对会整体漏判，须双向关联 |

**症状反查定位**（按库索引 `fault_patterns_index.json` 各卡 `symptoms`/`detectors` 字段反查归纳，跨模式先后次序为综合经验排序）：`aic error` / `AIC Error` → **FP-B07 优先**（再 FP-B06）；`SIGSEGV` / rc=139 / coredump → FP-B04 → **FP-B07** → FP-A05；`mssanitizer` / memcheck 报错 → FP-A05 → **FP-B07**；**后段输出全 0 且无任何报错** → 疑点成因⑥（再 FP-A04）。用户只给观测信号而无接口名时，按此顺序进卡比对机理。

## 1. FP-B07 模式卡摘要（检视依据，源自本库 `patterns/FP-B/FP-B07.md`，v3.1 含 v2.17 成因⑥）

- **编号 / 名称**：FP-B07 索引/偏移计算错误致越界 ｜ **类别**：功能/兼容 ｜ **风险**：高（S3×O3=9）｜ **状态**：活跃 ｜ **来源**：四仓 issue 全量语料对照（2026-09-14，缺陷类命中 125 条，已关闭 108）
- **适用声明头**（照抄卡片）：仓 All ｜ 侧别 Tiling,Kernel,Host ｜ 载体 Tiling源码,Kernel源码,aclnn源码 ｜ 触发 必须触发 ｜ 默认启用 true
- **skill 核查面**：与卡片机理范围一致——卡片机理原文即含 host（tiling / infershape / aclnn）与 kernel，skill 按仓内文件层落地为 op_api / op_host（tiling + infershape）/ op_kernel 全部相关文件，无额外扩面
- **故障机理**：索引/偏移量在 host（tiling / infershape / aclnn）或 kernel 内计算错误，导致越界读/写或取到错误数据。**六种典型成因**：① **整型宽度不足**——用 `int32_t` 承载元素数/地址（元素数 > 2^31 即溢出，单核偏移相乘更易溢出）；② **符号/方向翻转**——`idxOffset`、`startOffset` 等正负号或方向取反；③ **边界条件写错**——`>=`/`>` 混用、末块/尾块偏移计算漏 1、`CeilDiv/FloorDiv` 取整方向错；④ **对齐与分核偏移**——`DataCopy/DataCopyPad` 的 32B 对齐、多核分核偏移叠加未对齐；⑤ **检查次序颠倒**——先按连续性/对齐算偏移，后做维度值校验，非法值先参与偏移运算；⑥ **GM 偏移/长度 32 位计算域溢出（v2.17 增补）**——合法大 shape 下线性元素位置达 **`2^32`**（**uint32 域回绕**，与成因① 的 int32 溢出是不同档位），或 GM 起始地址/下标/搬运长度/`SetGlobalBuffer` 的 **size 参数**中 **≥2 个 32 位因子相乘**；**隐蔽特征是最终变量已声明为 `int64_t`/`uint64_t`，但右侧乘法仍全在 32 位域完成**——赋值时回绕已发生，再提升也无效；表现常为**后段输出全 0 的静默错误**（无 `aic error`、无 coredump，实证 ops-nn #4494）。
- **触发条件**：大 shape（元素数跨 2^31、单核偏移超 int32）；indices/offsets 取**边界值、负值、重复值**；末维/尾块非对齐（如 31/32/33）；分核数与 shape 不整除；模板分支（全载/切分/单核）切换处的偏移语义不同；多平台分支的检查次序差异；**合法大 shape 且 GM 偏移链路存在多因子乘法**。
- **典型表现**：`aic error` / `AIC Error` 报错；coredump；结果**错位**（部分位置取到相邻元素）而非整体偏差；偶发性（依赖分核与 shape，同一算子部分 case 才复现）；有时先被当成"部分用例精度不对"，掩盖越界根因；成因⑥ 型：后段输出全 0、无任何报错。
- **实证案例**：ops-nn **#1029** `EmbeddingDenseGradV2` idx 越界导致 aic 问题；**#1182** 同算子 `idxOffset` **翻转**导致 indices 取值越界致 aic（**同根因两连发**）；**#1359** `MatMulUnAlignedSingleCoreSplitKKernelGmToL1` 模板 `DataCopy` 指令读越界；**#1608** 32B `DataCopy` 越界；**#1483** `cubeMathType` 数组越界引发 coredump；#1928 index_fill 数据量超 int32 触发地址越界风险（与 FP-A18 交叠）；**#4494**（910B2）`rms_norm` 合法大 shape 下从元素位置 `4294969344`（紧贴 `2^32`）附近开始输出**全 0**——成因⑥ 静默型实证，修复把 GM 偏移链路改为 `uint64_t` 并在乘法前显式 `static_cast`。
- **关联**：FP-A18（int32 转 float 舍入）、FP-A04（越界取值错误常表现为"静默精度不对"；成因⑥ 的静默型表现）、FP-B04、FP-B06、FP-D01、FP-E01（只比数值不看 aic error 会漏判此类）。

## 2. 检视输入与算子定位

**输入**：aclnn 接口名（必填，如 `aclnnIndexAdd`）；可选 ref（默认 master）、指定仓（默认自动定位）。用户只给观测信号（aic error/coredump/错位/后段全 0）时，先据第 0 节症状反查锁定嫌疑接口，再按本流程走。

**接口名 → 算子目录换算**：去 `aclnn` 前缀 + 驼峰转下划线小写：
`aclnnIndexAdd → index_add`、`aclnnEmbeddingDenseGradV2 → embedding_dense_grad_v2`、`aclnnGridSampler2DBackward → grid_sampler2d_backward`。

**仓定位顺序**（GitCode `cann` 组织，逐仓用目录列表确认）：`ops-nn`（index/scatter/embedding 等高发类）→ `ops-math`（math/matmul 类）→ `ops-cv`（image 类）→ `ops-transformer`（attention/moe 类）。同一算子可能存在多仓同名目录，需按 def.cpp 原型与接口签名确认归属；跨仓多实现时全部纳入检视。FP-B07 高发面：索引敏感算子（index/scatter/gather/embedding 系列）、切块搬运类（matmul 非对齐/分核模板）、带 `cubeMathType` 枚举分支的算子、**GM 偏移链路多因子相乘的大 shape 算子（attention/moe 类，成因⑥）**。

**算子目录结构约定**（已验证示例 `cann/ops-math` → `math/add/`、`cann/ops-nn` → `index/inplace_scatter_add/`）：

```text
{类别}/{op_name}/
├── op_host/           # *_def.cpp（原型）、*_infershape.cpp、*_tiling*.cpp、arch35/ 子目录
│   └── op_api/        # aclnn_*.cpp（aclnn 出口实现：校验、早退、GetWorkspaceSize）
├── op_kernel/         # kernel 头文件（含 arch35 / regbase / SIMT 等架构变体）
├── op_graph/  op_kernel_aicpu/  tests/  docs/  examples/   # 视算子而定
```

## 3. 取数方式（Important）

公开网页端点被拦截，**必须走 API**（均需带 `User-Agent`；失败重试 2 次、间隔 5 秒）：

| 用途 | 端点 |
|---|---|
| 目录列表 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/contents/{path}?ref={ref}` |
| 单文件内容 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/raw/{path}?ref={ref}` |
| Issue 查重 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/issues?q={关键词}` |

**已实测不可用（截至 2026-09 实测）**：`https://gitcode.com/{repo}/raw/{sha}/{path}`、`https://raw.gitcode.com/...` → 403 或拦截页；端点策略如有变化可复测。若本地已有算子仓克隆，优先直接读本地文件，行号证据以本地 HEAD 为准并记录 commit。

## 4. 六成因检视清单（每点：查什么 → 何处 → 命中判据）

对算子的 op_api / op_host（tiling + infershape）/ op_kernel 全部相关文件逐点核查，**每点先查命中面、再做反证排除**，防护面也要记录（作为反证依据）。检测签名命中只产生**候选点位**，立卡须过第 7 节三关；`Stride` 类属审查关键词（高频词，仅作定位提示），不作命中判据。

### ① 整型宽度不足
- 查什么：地址/偏移变量的**声明类型**（`int32_t` vs `int64_t`）与元素数上界是否匹配（元素数 > 2^31 即溢出，单核偏移相乘更易溢出）；`GetShapeSize()` 与 `INT32_MAX` 比较处是否**已溢出之后才比**（比较本身失效）；host 侧 shape 各维相乘是否可能超 int32；uint32 下溢/回绕（如 `batch·num==0`）。
- 何处：op_host tiling/infershape 的 shape 乘积与块数计算、kernel 内偏移变量声明、op_api 校验比较。
- 检测签名：`int32_t[^\n]{0,40}(idx|Idx|offset|Offset|addr|Addr)`；`GetShapeSize\(\)\s*[<>]=?\s*INT32_MAX`。
- 实证样板：#1928 index_fill 数据量超 int32（与 FP-A18 交叠）。

### ② 符号/方向翻转
- 查什么：`idxOffset`、`startOffset` 等正负号或方向取反；`coefArr`、`*Stride` 的符号与方向。
- 何处：kernel 索引推进逻辑、tiling 分块起点计算。
- 检测签名：`idxOffset|startOffset|offsetIndex|coefArr`。
- 实证样板：#1182 `EmbeddingDenseGradV2` idxOffset 翻转致 indices 越界致 aic（与 #1029 同算子同根因两连发——同算子修复后须复核全部偏移方向语义）。

### ③ 边界条件写错
- 查什么：索引算式中的 `+1/-1`；除法与取模的取整方向；`>=`/`>` 混用；末块/尾块偏移计算漏 1；`CeilDiv/FloorDiv` 取整方向错。
- 何处：tiling 块数/offset 计算、kernel 循环边界与尾块处理。
- 检测签名：`CeilDiv\([^;]{0,60}(idx|offset)`。

### ④ 对齐与分核偏移
- 查什么：`DataCopy/DataCopyPad` 的 blockLen 与 32B 对齐、偏移叠加未对齐；多核分核偏移叠加；分核数与 shape 不整除时的尾核处理；模板分支（全载/切分/单核）切换处的偏移语义差异。
- 何处：kernel 搬运路径、tiling 分核逻辑。
- 检测签名：`DataCopy(Pad)?\([^;]{0,60}(offset|Offset)`。
- 实证样板：#1359 `MatMulUnAlignedSingleCoreSplitKKernelGmToL1` 模板 `DataCopy` 读越界；#1608 32B `DataCopy` 越界。

### ⑤ 检查次序颠倒
- 查什么：先按连续性/对齐算偏移、后做维度值校验，**非法值先参与偏移运算**（多平台分支检查次序差异）；`cubeMathType` 等枚举数组下标取值是否可能越界。
- 何处：op_api 校验序列、kernel 入口分支。
- 检测签名：`cubeMathType\s*\[`。
- 实证样板：#1483 `cubeMathType` 数组越界引发 coredump。

### ⑥ GM 偏移/长度 32 位计算域溢出（v2.17）
- 查什么：**枚举所有 GM 起始地址、GM 下标、GM 搬运长度表达式**——`SetGlobalBuffer((__gm__ T*)ptr + expr, size)`（**第二个 size 参数同样要查**）、`GlobalTensor[expr]` / `xGm[gmBias]` / `yGm[progress]`、`CopyIn(gmBias)` / `CopyOut(progress)`，以及名称含 `gmBias`/`gm_bias`/`blockOffset`/`progress` 与 stride 类变量的表达式；对每个表达式**同时看声明类型与右侧计算域**——若存在 `blockIdx`/`i_o`/`mIdx` 与 `blockFactor`/`rowFactor`/`numCol`/stride 等多因子相乘，**必须在第一次乘法之前**显式提升到 `int64_t`/`uint64_t`；**不能只看最终变量类型**——`uint64_t gmBias = i_o * rowFactor * numCol;` 右侧操作数全为 32 位时先回绕后赋值，**判 FAIL**；**反推最大可能值**：若合法 shape 或 tiling 可使线性元素位置达或超 `2^32` 且乘法前未进 64 位计算域 → FAIL；无法确认上界但表达式用于 GM 偏移且全为 32 位操作数 → 至少 SUSPICIOUS。
- 何处：kernel 的 GM 偏移注册与搬运路径（`SetGlobalBuffer` / `GlobalTensor[]` / `CopyIn` / `CopyOut`）。
- 检测签名：`SetGlobalBuffer\s*\([^;]{0,80}\*`；`(int32_t|uint32_t)\s+\w*(?i:gmBias|gm_bias|blockOffset|block_offset|progress)`。
- 实证样板：ops-nn **#4494**（910B2）`rms_norm` 合法大 shape 下从元素位置 `4294969344`（紧贴 `2^32`）起输出**全 0**——无 aic error、无 coredump 的静默型；修复把 `blockIdx_ * blockFactor * numCol`、`gmBias`、`CopyIn/CopyOut` 的 GM 偏移链路改为 `uint64_t` 并在乘法前 `static_cast`。

```cpp
// ❌ 错误 1：最终变量是 int64_t / uint64_t，但右侧操作数全是 32 位 —— 先回绕再赋值
int64_t offset = batchIdx * numHeads * seqLen * headDim;
uint64_t gmBias = i_o * rowFactor * numCol;
// ❌ 错误 2：GM 偏移 / 搬运长度变量直接用 32 位类型承载
uint32_t gmBias = i_o * rowFactor * numCol;
int32_t blockOffset = mIdx * numCol;
// ✅ 正确：第一次乘法前显式提升到 64 位计算域
int64_t offset = static_cast<int64_t>(batchIdx) * numHeads * seqLen * headDim;
uint64_t gmBias = static_cast<uint64_t>(i_o) * rowFactor * numCol;
```

## 5. 检视流程

1. **定界**：换算 op 目录、确认所在仓与 ref；多仓命中时列出全部实现并逐一检视。
2. **枚举**：目录列表列出 op_api / op_host / op_kernel（含架构子目录）全部相关文件，产出文件清单。
3. **触发词扫描**：按第 4 节八条检测签名 + `idx|Idx|offset|Offset|addr|Addr|Stride|CeilDiv|FloorDiv|DataCopy|cubeMathType` 定位风险面（本地仓用 grep；API 模式逐文件拉取后检查）。
4. **六成因逐项核查**：每点记录命中面与防护面证据（文件:行号）；对照第 4 节实证样板做同族反证。
5. **反证排除**：穷尽框架级防护（框架尾块处理、tiling 上游校验、`SafeMul`/`__int128` 类防护写法）、语义级分析（偏移算式可达上界推演）、同族已修复样板后再下结论。
6. **判定**：按第 7 节标准给出 命中 / 观察项 / 反证排除。
7. **GitCode 查重**（仅命中项）：issues API 按接口名检索，逐条比对是否同机理；无同机理才立卡。
8. **业务可达性核查**（仅命中项）：判 B 等级、定业务影响类型、给处置建议；默认保守（无法证明不可达即记 B3），降档须附证据；B 不改 S×O 档位。
9. **出报告**：按第 8 节模板落盘；所有运行时结论标注「静态推演，需 NPU 实测确认」；**命中立卡项必须附可执行复现用例**（Bug 卡「复现用例」字段缺失即视为未完成出报告）。

## 6. 风险定级（S×O）与业务影响评估（B 轴）

- **S**：S4 致命（coredump / `aic error` / 数据静默损坏——成因⑥ 的后段全 0 即数据静默损坏；实证见 #1182/#1483/#4494）、S3 结果错误（错位取数）、S2 功能受限、S1 资源浪费。
- **O**：O3 = ≥2 条独立实证；O2 = 1 条独立实证；O1 = 仅静态扫描命中或团队笔记（实证 = 确认对应的 issue / PR，或经跨仓、跨分支核验确认的缺陷记录，同权计入）。静态推演命中且无实证默认 **O1**；升档须在报告中给出实证依据。
- **风险 = S×O**：≥6 高；3/4 中；1/2 低。FP-B07 基准：模式卡整体 S3×O3=9（高）；纯静态命中 S3×O1=3（中）；可静态证 coredump/aic error 路径可达的按 **S4×O1=4（中）**起步，实证后随证据累积复评升档。

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

- 本模式特有：成因①/⑥ 的触发依赖"合法大 shape"，判 B 时须**区分"接口契约允许的大"与"业务真实使用的大"**——前者是 B1 的依据、后者才是 B3/B2。

## 7. 判定标准与反误报原则

- **签名/触发词命中 ≠ 成立**：必须过完整推导链 + 可达性分析 + 反证排除三关。特别地：`int32_t` 声明**不必然溢出**——须证明可达上界（元素数跨 2^31 或偏移乘积溢出）才立卡；`CeilDiv`/`DataCopy` 命中须推演具体偏移组合才会越界；成因⑥ 命中须反推出合法 shape 可达 `2^32`。
- **三种判定**：
  - **命中**：机理推导链完整 + 触发组合可静态证伪可达 + 反证排除失败 → 立 Bug 卡；
  - **观察项**：设计存疑但静态无法确证、契约依赖、存量非本次引入 → 记录不定级；
  - **反证排除**：防护在位 / 上界不可达 / 语义自洽 → 明确写出反证理由。
- **四类症状同看**：数值错位、aic error、coredump、**后段输出全 0（成因⑥ 静默型）**任一均须回溯索引/偏移算式；只比数值不看 aic error 会漏判（FP-E01 关联）。
- **同根因两连发警示**：#1029/#1182 同算子连发——对已修复过越界问题的算子，复核时须扩展检查**全部**偏移方向与取整语义，勿只验修复点。
- **可达性分析要给出可复现反例**：具体 shape/indices/分核组合与触发路径（如「元素数 2^31+K」「indices 取 -1 / 上界值 / 重复值」「末维 31/32/33」「分核数 = 1 / 2 / 实际核数 ± 1」「合法大 shape 线性位置跨 2^32 的 GM 多因子偏移链」五类探针组合）。
- **确认命中 = 必须给复现用例**：凡判定「命中」立卡，Bug 卡必须附**可直接执行的复现用例**——aclnn 两段式调用序列与全部入参（各 tensor 的 shape/dtype/layout/具体数值、attr 取值、可选输入传 null 还是占位指针须逐一明确）、触发组合的精确值、期望现象（aic error / coredump / 数值错位区间 / 后段全 0）与观测手段（mssanitizer、数值比对口径）。只有文字化的「触发条件描述」而无可执行构造的，降级为观察项，不得立卡。
- **不臆造行号**：每条证据必须是实际读到的 文件:行号；引用样板代码时同样给出路径与行号。
- **静态推演声明**：无 NPU 环境时，所有运行时行为结论必须标注「静态推演，需 NPU 实测确认」，并附实测用例建议。

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
- **文件路径与行号证据**：
  - `{文件}:{行号}`：{现象}
  - 对照样板（反证）：{文件}:{行号}（正确做法）
- **FP-B07 模式编号**：FP-B07 索引/偏移计算错误致越界（成因①~⑥）
- **S×O 风险定级**：S3（结果错误）× O1（静态命中无实证）= 3，中（可静态证崩溃路径可达则 S4×O1=4）
- **证据等级**：{静态可证 / 需实测确认}｜{一句话理由}
- **业务影响评估（B 轴）**：可达性 B{3|2|1}（{一句话判据}）｜ 业务影响：{静默精度损失/任务失败中断/性能退化/仅可观测性}｜ 证据：{调用方/公开负载/为何不可达}｜ 处置建议：{尽快修/排期修/记录}
- **故障机理推导链**：{逐步推导：变量声明/算式/取整方向/对齐假设/计算域 → 越界地址范围}
- **触发条件可达性分析**：{可复现反例组合：shape / indices 值 / 分核数 / GM 偏移链}。静态推演，需 NPU 实测确认
- **复现用例**（命中项必备，缺此字段不得立卡）：{可执行构造：aclnn 两段式调用序列 + 全部入参清单（各 tensor shape/dtype/layout/具体数值、attr、可选输入以 null 或占位指针明确）+ 触发精确值 + 期望现象（aic error/coredump/错位区间/后段全 0）+ 观测手段（mssanitizer/数值比对口径）}
- **建议修复方案**：{int64 承载 / 乘法前 static_cast 提升 64 位计算域 / 符号修正 / 取整方向修正 / DataCopyPad 对齐 / 校验前置，对齐同族已修复样板}
- **测试拦截建议**：五类探针（元素数跨 2^31、indices 边界/负值/重复、非对齐尾块 31/32/33、分核数 1/2/实际核数±1、合法大 shape 线性位置跨 2^32 的 GM 偏移链）；mssanitizer 内存越界检测；四类症状同看；大 shape 与 tiling 阈值两侧成对
- **Agent 误判记录**：{被推翻的假设 → 推翻证据 `[文件]:[行号] [代码行]`；无则「无」}
- **GitCode 查重**：{issues API 检索结论，无同机理 issue 才立卡}
```

### 检视报告结构

```markdown
# FP-B07 检视报告：{aclnn 接口名}（YYYY-MM-DD）
## 一、执行概览（仓/ref/HEAD、文件清单、判定统计：命中 X / 观察项 Y / 反证排除 Z；命中项 B 轴分布 B3×a / B2×b / B1×c）
## 二、命中明细（Bug 卡，按第 8 节字段，每卡含 B 轴业务影响评估）
## 三、观察项（表：# / 文件:行号 / 存疑点 / 性质）
## 四、反证排除（表：成因点 / 反证理由）
## 五、NPU 实测建议（五类探针用例清单 + mssanitizer 跑法 + tiling 阈值两侧 shape）
```

> 报告须在「执行概览」标注证据等级分布（静态可证 X / 需实测确认 Y），并在文末单列「Agent 误判记录」小节（无则写「无」）。

报告落盘到当前任务工作区，建议命名 `FP-B07检视_{接口名}_YYYYMMDD.md`。

## 9. 示例速览：aclnnIndexAdd

- **定位**：`cann/ops-nn` → `index/inplace_scatter_add/`（op_host 含 op_api/aclnn_index_add.cpp；op_kernel/）。
- **检视面提示**（引导，不预设结论，仍须逐点核查）：
  - ① indices/偏移承载类型与元素数上界（index 类算子 indices 值域 + 大 shape 双重越界源）；host 侧 `indices` 维度参与 shape 乘积是否超 int32。
  - ② scatter 方向的偏移推进正负号与写入方向是否一致。
  - ③ indices 取边界值/重复值时 `+1/-1` 与取整方向；尾块漏 1。
  - ④ 非对齐末维下 `DataCopyPad` 对齐与分核偏移叠加；同族 `InplaceIndexAddWithSorted` 与旧路径偏移语义差异。
  - ⑤ op_api 连续性/对齐检查与 indices 值域校验的先后次序。
  - ⑥ GM 偏移链路（`SetGlobalBuffer` 等）是否存在 32 位多因子乘法；大 shape 下线性位置上界。
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
python3 scripts/scan_fp.py --only FP-B07 --format json <目标文件>  # 签名候选（非结论）
python3 scripts/verify_lines.py <报告.md> --root <被检仓>        # 行号校验
python3 check_fault_patterns.py                                # 全库守门
```

### 工作量与抽样（v4.0）

- **深度档：深度**（索引 `depth` 字段）——全量核查，不抽样。全部映射点 / 分支逐条过；单模式命中 > 50 处时按文件分片，并在报告写明分片口径。
- **报告必填**：抽样口径（全量 / 每点前 N 处 / 每类 N 例）+ 停止点记录；未写口径视为未完成。

## 11. 已知缺陷案例库：触发条件 / 根因 / 修复范式 / 针对性深挖（v5.1）

> 本节把本型**已确认缺陷**拆到代码级颗粒度（触发条件 → 根因/路径 → 修复范式 ✅ → 发现步骤 → 复现锚）。修复范式为**示意**，路径取自卡片实证，**不臆造行号**。

### 案例 1｜idxOffset 方向翻转致 indices 越界（同根因两连发）—— #1029 / #1182（EmbeddingDenseGradV2）

- **触发**：indices 取边界/重复值；嵌入类算子（成因②）。
- **根因（路径）**：`EmbeddingDenseGradV2` idx 越界致 aic（#1029）修复后，同算子 `idxOffset` 翻转再致 indices 越界（#1182）——索引推进方向语义取反（成因②）。
- **修复范式（✅，示意）**：

```cpp
// ❌ int64_t idxOffset = -coef * stride;  // 方向取反
// ✅ int64_t idxOffset = coef * stride;   // 方向与 indices 语义一致
```

- **针对发现**：① 核 `idxOffset/startOffset/coefArr/*Stride` 符号方向；② 已修过越界的算子扩展核对全部方向与取整语义；③ grep `idxOffset|startOffset|offsetIndex|coefArr`。
- **复现锚**：复跑 indices 边界/重复值用例，观 aic error 或错位取数。
- **实证**：#1029 / #1182（同根因两连发）。

### 案例 2｜模板分支下 DataCopy 指令读越界 —— #1359（MatMulUnAlignedSingleCoreSplitKKernelGmToL1）

- **触发**：模板分支（全载/切分/单核）切换处偏移语义不同；非对齐尾块。
- **根因（路径）**：该模板 `DataCopy` 读越界——切分/K 分核模板偏移未按分支语义修正（成因④）。
- **修复范式（✅，示意）**：按模板分支修正偏移与尾块长度（32B 对齐 + 尾核处理）。
- **针对发现**：① 核 `DataCopy(Pad)?\([^;]{0,60}(offset|Offset)` 偏移组合；② 核模板切换处语义差异与尾核；③ 非对齐末维 32B 对齐。
- **复现锚**：末维/尾块 31/32/33 与分核数 1/2/±1 组合跑 mssanitizer。
- **实证**：#1359。

### 案例 3｜32B DataCopy 越界 —— #1608

- **触发**：搬运长度非 32B 对齐。
- **根因（路径）**：32B `DataCopy` blockLen 与 32B 对齐约束不符（成因④）。
- **修复范式（✅，示意）**：改 `DataCopyPad` 或补齐 blockLen 到 32B 对齐。
- **针对发现**：① 核 blockLen 与 32B 对齐；② 核分核偏移叠加未对齐。
- **复现锚**：非对齐末维用例跑 mssanitizer。
- **实证**：#1608。

### 案例 4｜cubeMathType 数组越界引发 coredump —— #1483

- **触发**：`cubeMathType` 枚举下标越界（成因⑤）。
- **根因（路径）**：`cubeMathType[<idx>]` 未做值域校验即取值 → 越界 → coredump。
- **修复范式（✅，示意）**：取值前值域校验，非法值先拦截（勿先参与下标运算）。
- **针对发现**：① grep `cubeMathType\s*\[`；② 核 op_api 校验序列先后次序（非法值先参与运算即命中）。
- **复现锚**：传入越界 `cubeMathType` 值观 coredump。
- **实证**：#1483。

### 案例 5｜数据量超 int32 承载不足致地址越界风险 —— #1928（index_fill，与 FP-A18 交叠）

- **触发**：元素数跨 2^31、单核偏移超 int32（成因①）。
- **根因（路径）**：`int32_t` 承载元素数/地址溢出；`GetShapeSize()` 与 `INT32_MAX` 比较可能已在溢出之后（比较失效）。
- **修复范式（✅，示意）**：

```cpp
// ❌ int32_t total = dim0 * dim1 * dim2; if (total < INT32_MAX) {...}
// ✅ int64_t total = static_cast<int64_t>(dim0) * dim1 * dim2;
```

- **针对发现**：① grep `int32_t[^\n]{0,40}(idx|Idx|offset|Offset|addr|Addr)`、`GetShapeSize\(\)\s*[<>]=?\s*INT32_MAX`；② host shape 各维相乘是否超 int32。
- **复现锚**：构造元素数跨 2^31 大 shape。
- **实证**：#1928（与 FP-A18 交叠）。

### 案例 6｜GM 偏移 32 位计算域回绕致后段全 0（成因⑥ 静默型）—— #4494（rms_norm，910B2）

- **触发**：合法大 shape，线性元素位置达 `2^32`（实测从 `4294969344` 起），GM 偏移链多因子相乘。
- **根因（路径）**：`uint64_t gmBias = i_o * rowFactor * numCol;` 右侧全 32 位 → 先 uint32 回绕再赋值；`blockIdx_*blockFactor*numCol`、`CopyIn/CopyOut` 同理——变量虽 64 位，回绕已发生。**无 aic error、无 coredump**，后段输出全 0（并看 FP-A04）。
- **修复范式（✅，示意）**：

```cpp
// ❌ uint64_t gmBias = i_o * rowFactor * numCol;
// ✅ uint64_t gmBias = static_cast<uint64_t>(i_o) * rowFactor * numCol;
```

- **针对发现**：① 枚举全部 `SetGlobalBuffer((__gm__ T*)ptr + expr, size)`（第二 size 参数同查）与 `xGm[gmBias]`/`CopyIn`/`CopyOut`；② 同时看声明类型与右侧计算域；③ 反推最大可能值 ≥ `2^32` 且乘法前未进 64 位 → FAIL（成因⑥ 专法）。
- **复现锚**：大 shape 从近 `2^32` 位置比对输出（后段全 0、无报错），跑 mssanitizer。
- **实证**：#4494（910B2；cannbot-skills 红线条例 9 收录）。

### 语料基线与深挖起手式
- 语料统计（2026-09-14，四仓缺陷类）：命中 125 条（已关闭 108）。
- 起手：`python3 scripts/scan_fp.py --only FP-B07 --format json <文件>`。

### 案例 7｜固定 unroll 因子在奇数尾块上多搬，cache 记账与 copy 同步失真 —— 26-03（FlashAttentionScore）

- **触发**：BMM2 的 K 维内部迭代数 `aColNum` 使某个 `curK` 之后只剩 1 个单元（`aColNum - curK == 1`），即奇数尾块；偶数或整除 shape 走主块完全正确，**放大小 shape 也测不出来**，因为可能全落在偶数路径。
- **根因**：搬运因子 `ndNum` 被硬编码为 2 个 ND 单元（`ndNum = 2`），尾块实际只剩 1 个单元时仍按 2 搬运——多读一个单元造成越界，同时 `cacheSize += ndNum` 与 `blockCount = mm2BaseK * ndNum / BLOCK_CUBE` 一并按 2 记账，导致 cache 水位与真实占用不符，后续 buffer 复用判断失效。
- **修复范式（✅，修复后形态，本仓实测锚）**：

```cpp
// ❌ 固定 2：尾块只剩 1 个单元时读越界 + cache 记账偏大
//    int32_t ndNum = 2;
// ✅ 按剩余单元数取值（flash_attention_score_s1s2_bn2gs1_sab.h:2353）
int32_t ndNum = aColNum - curK == 1 ? 1 : 2;
const uint16_t blockCount = mm2BaseK * ndNum / BLOCK_CUBE;
```

- **针对性发现**：① grep `ndNum = 2` / `cacheSize += 2` / `blockCount = ... * 2` 这类**硬编码因子**；② 反推 `curK` 循环能否只剩 1 个单元（`aColNum` 为奇数即命中）；③ `ndNum` / `blockCount` / `cacheSize` 三者必须**同源同变**，只改一处仍是缺陷；④ 小 shape 未必触发——要专门构造奇数尾块。
- **最小复现锚**：让内部 K 迭代数为 1、3、5 等奇数；断言 `ndNum`/`blockCount`/`cacheSize` 三者一致变化，配 guard/canary 与 NaN 统计。
- **实证**：现网 26-03（ops-transformer PR #2466；**该单无关联 issue，仅 PR**）。修复后形态锚：`attention/flash_attention_score/op_kernel/arch22/flash_attention_score_s1s2_bn2gs1_sab.h:2353`（@ops-transformer HEAD `d5c0683`，2026-11-05 本地核验）。同一函数内 `:2354` `blockCount`、`:2360` 与 `:2364` 两处 `mm2LoadData*(..., ndNum)` 均消费该变量——**这正是「改一处不够」的现场证据**。

### 案例 8｜UB 容量恰好相等时漏入降级分支（`>` 应为 `>=`）—— 25-09（ScatterAddWithSort）

- **触发**：`updatesAlign * inputSize` **恰好等于** `max_ub`。此时 UB 已经被占满，没有余量给 scratch，但 `>` 判断为假 → 不进入预留与重算分支 → 后续按 scratch 访问越界。
- **根因**：容量类比较用 `>`，把「刚好占满」误判为「还有余量」。等号边界是容量判断的经典 off-by-one：容量**等于**上限时必须走降级路径。
- **修复范式（✅，修复后形态，本仓实测锚）**：

```cpp
// ❌ 等号漏判：刚好占满仍当作有余量
//    if (updatesAlign * inputSize > max_ub) {
// ✅ 等于即视为占满（scatter_add_with_sorted_tiling.cpp:219）
if (updatesAlign * inputSize >= max_ub) {
    maxSize = MAX_SIZE;
    max_ub = max_ub - maxSize * (SIZE_OF_INT32 + SIZE_OF_INT32);
    updatesEach = max_ub / inputSize;
    ...
}
```

- **针对性发现**：① 枚举全部容量比较 `> max_ub` / `> ubSize` / `> l1Size` / `> L0ASize`；② 对每个判断问「**等于**上限时是否还需要额外空间（scratch / 临时 buffer / 对齐 padding）」——需要则必须 `>=`；③ 等号边界要**独立成例**，`B-1/B/B+1` 三档，B 由实测反推而非猜；④ 单位要对（元素 / 字节 / block），`updatesAlign*inputSize` 是元素×字节混合乘出字节数，确认与 `max_ub` 同单位。
- **最小复现锚**：精确构造 `updatesAlign * inputSize == max_ub` 的 shape，记录 tiling key 与实际 UB 高水位；`B-1` 应正常、`B` 与 `B+1` 应走降级且都不越界。
- **实证**：现网 25-09（canndev PR #69068；**该单无关联 issue，仅 PR**）。修复后形态锚：`index/scatter_add_with_sorted/op_host/scatter_add_with_sorted_tiling.cpp:219`（@ops-nn HEAD `b27fda2`，2026-11-05 本地核验）。同函数 `:202`/`:222`/`:228` 的 `updatesEach`、`maxSize` 计算均依赖该分支——**等号判断错了，后面整段降级逻辑都不会执行**。


## 15. 实证加深（v5.4）：真实修复锚 · 反向排除项

> 取证基线：ops-transformer `@d5c0683` / ops-nn `@b27fda2`（2026-11-05 本地核验）。仓为浅克隆，commit 列记当前 master HEAD，非修复提交 SHA。
> 本节只收**能逐行核对**的锚；其余现网案例（canndev / cann-ops-adv-dev 侧）标「待定位」，不臆造行号。

### 15.1 真实锚（修复后形态）

| 案例 / issue | 真实锚（文件:行号 @commit） | 要点 |
|---|---|---|
| #2466 `FlashAttentionScore` 奇数尾块多搬（现网 26-03；**仅 PR 无 issue**） | `attention/flash_attention_score/op_kernel/arch22/flash_attention_score_s1s2_bn2gs1_sab.h:2353` @d5c0683 | `int32_t ndNum = aColNum - curK == 1 ? 1 : 2;` ——**修复后形态**取代固定 `ndNum = 2`。同函数 `:2354` `blockCount = mm2BaseK * ndNum / BLOCK_CUBE`、`:2360`/`:2364` 两处 `mm2LoadData*(..., ndNum)` 均消费该变量 ⇒ **判据：搬运因子必须由剩余单元数推导，且 ndNum/blockCount/cacheSize 同源同变**。`cacheSize += ndNum` 见 `:1107`/`:1150`。 |
| #69068 `ScatterAddWithSort` UB 等号漏判（现网 25-09；**仅 PR 无 issue**） | `index/scatter_add_with_sorted/op_host/scatter_add_with_sorted_tiling.cpp:219` @b27fda2 | `if (updatesAlign * inputSize >= max_ub)` ——**修复后形态**取代 `>`。同函数 `:202`/`:222` 的 `updatesEach`、`:228` 的 `maxSize` 均在该分支内计算 ⇒ **等号漏判会让整段降级逻辑不执行**。判据：容量比较须问「等于上限时还需不需要额外空间」。 |

### 15.2 反向排除项

| 反向排除项 | 所需负向证据 |
|---|---|
| 该搬运因子不存在尾块（形状恒整除） | 给出「迭代数上界被 tiling 强制为偶数/整除」的 `[文件]:[行号]`，或该循环上界来源的约束行 |
| 容量比较处「等于上限」时确实无需额外空间 | 给出该分支后不使用 scratch/临时 buffer 的 `[文件]:[行号]`；仅凭「一般不会刚好相等」不算 |
| 已用 64 位承载且乘法前已提升 | 给出**第一次乘法前**的 `static_cast<int64_t>` / `static_cast<uint64_t>` `[文件]:[行号]`，而非只看左值声明类型 |
| 该偏移不参与 GM 寻址 | 给出该变量仅用于局部 UB 内定位、且上界远小于 2^31 的 `[文件]:[行号]` |

## 16. 判据层（L2/L3）：出用例与判读前必读 <!-- BEGIN DETECT-SECTION (generated by scripts/sync_detect_section.py; do not edit) -->

> 生成物，勿手改（C42 校验）。完整判据见 [references/detect-l2-l3.md](references/detect-l2-l3.md)。

- **L2**：轴 shape 维度/内存/边界值｜观测 sanitizer-memcheck｜至少 4 例
- **L3 `sanitizer-memcheck`**：K2(假绿)CANN 自带 .o 的 san 符号数必须实测为 0，否则 memcheck 假绿；K194(假阳)--heap-check cann 的 illegal free at serialNo:0 是算子执行前误报

> 判 FAIL 先排「假 FAIL」、判 PASS 先排「假 PASS/假绿」。**不查 L3 就出结论 = 报告作废。** <!-- END DETECT-SECTION -->
