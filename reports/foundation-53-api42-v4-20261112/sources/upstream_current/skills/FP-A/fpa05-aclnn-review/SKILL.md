---
name: "fpa05-aclnn-review"
description: "基于 FP-A05「脏数据/数据踩踏」故障模式对指定 aclnn 接口（如 aclnnAdd）做源码级缺陷检视：定位算子实现，按五映射点清单核查缓冲区初始化/workspace 清零/未初始化先读/原地写/越界尾块，产出带文件行号证据链与 S×O 定级的 Bug 卡与检视报告。当用户给出 aclnn 接口名要求做 FP-A05 检视或脏数据类缺陷排查时使用。"
---

# FP-A05 aclnn 接口检视（fpa05-aclnn-review）

对用户指定的 aclnn 接口（如 aclnnAdd）做 FP-A05 专项源码检视：先定位算子实现，再按五映射点清单逐项核查，每个结论给出**文件 + 行号 + 推导链**证据，命中即出 Bug 卡，输出检视报告。

## 0. 与相邻模式的边界

| 相邻模式 | 分工 |
|---|---|
| FP-D01 / FP-D02（资源/内存） | **边界**：D01/D02 管内存**容量**（OOM/占用高），本模式管内存**正确性**（脏数据）——同一批"内存问题"按此二分归属 |
| FP-B07（越界） | 越界写是脏数据的**来源之一**：越界写本身归 FP-B07，其引入的未定义数据读用归 FP-A05，报告可双向关联 |

## 1. FP-A05 模式卡摘要（检视依据，源自本库 `patterns/FP-A/FP-A05.md`，v3.1）

- **编号 / 名称**：FP-A05 脏数据 / 数据踩踏 ｜ **类别**：精度 ｜ **风险**：高（S3×O2=6）｜ **状态**：活跃
- **适用声明头**（照抄卡片）：仓 All ｜ 侧别 All ｜ 载体 Kernel源码,Tiling源码 ｜ 触发 workspace|GetWorkspaceSize|SetGlobalBuffer|Init\( ｜ 默认启用 true
- **skill 核查面**：除卡片所列载体外，op_api 早退路径与 infershape 退化分支（空张量/退化 shape 早退的输出写入路径所在）一并纳入五映射点核查
- **故障机理**（**实质是内存安全正确性问题，不是容量问题**）：缓冲区未初始化、workspace 未清零、算子申请 CKE 内存后未做初始化、原地写覆盖输入、越界写引入未定义数据。
- **触发条件**：空张量/退化 shape、workspace 复用、inplace 路径、尾块覆盖不完整。
- **典型表现**：精度计算有误、网络 loss 不收敛、偶发 NaN。
- **实证案例**：ops-nn #5560 RmsNormGrad 空张量 dgamma 输出 NaN、Split-D 尾元素未覆盖，GM 清零 + bodyPart×2 修复（PR !9873）。
- **关联**：FP-A08（尾块/离群点）、FP-B07（越界写来源）、FP-G01（未初始化累积致耗尽挂死）、FP-D01/D02（容量二分边界）。

## 2. 检视输入与算子定位

**输入**：aclnn 接口名（必填，如 `aclnnAdd`）；可选 ref（默认 master）、指定仓（默认自动定位）。

**接口名 → 算子目录换算**：去 `aclnn` 前缀 + 驼峰转下划线小写：
`aclnnAdd → add`、`aclnnRmsNormGrad → rms_norm_grad`、`aclnnGridSampler2DBackward → grid_sampler2d_backward`。

**仓定位顺序**（GitCode `cann` 组织，逐仓用目录列表确认）：`ops-math`（math 类）→ `ops-nn`（norm/loss/activation 等）→ `ops-cv`（image 类）→ `ops-transformer`（attention/moe 类）。同一算子可能存在多仓同名目录，需按 def.cpp 原型与接口签名确认归属；跨仓多实现时全部纳入检视。

**算子目录结构约定**（已验证示例 `cann/ops-math` → `math/add/`）：

```text
{类别}/{op_name}/
├── op_host/           # add_def.cpp（原型）、add_infershape.cpp、*_tiling*.cpp、arch35/ 子目录
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

## 4. 五映射点检视清单（每点：查什么 → 何处 → 命中判据）

对算子的 op_api / op_host（tiling + infershape）/ op_kernel 全部相关文件逐点核查，**每点先查命中面、再做反证排除**，防护面也要记录（作为反证依据）。

### ① 输出/累加缓冲初始化（含空张量/退化 shape）
- 查什么：所有输出在**每条可达路径**上是否被完整写入；空张量/退化 shape 早退路径是否把**非空输出**也一并填满（FP-A05 实证同型：早退只填部分输出，其余输出保持未初始化流出脏值）；原子累加前是否清零（`InitOutput` 清零 + `SyncAll` + `SetAtomicAdd` 模式；`SetNeedAtomic(true)` 时框架对原子输出预清零）。
- 何处：op_api 的 `IsEmpty` 早退分支、infershape 退化分支、kernel 的 Init/Process 入口与累加路径。
- 样板反证（正确做法）：`ops-cv image/roi_align/op_api/aclnn_roi_align.cpp:189-197`（早退路径 GetOutWithValueZero + ViewCopy 填 0）；命中样板（缺陷做法）：`ops-cv image/grid_sampler2d_grad/op_api/aclnn_grid_sampler2d_backward.cpp:240-246`（任一输入空即 `*workspaceSize=0` 早退且不填任何输出）。

### ② workspace 清零
- 查什么：tiling 分配的 workspace 是否清零；kernel 是否存在「部分核不写 workspace × 消费方无条件按全量读」的组合（空闲组/空闲核提前 return，残留脏 GM 数据被当部分和读入）。
- 何处：tiling 的 workspace 申请处、kernel 各 Phase 对 workspace 的写/读范围。
- 样板反证（正确做法）：floor-div 等分使每组 ≥1 chunk 无空组，或 Phase1 写满后 `SyncAll` 再读；命中样板（历史例）：`ops-math reduce_std_with_mean`——Phase1 CeilDiv 出现空闲组不写、Phase2 无条件全行读，残留脏数据被当作部分和读入。

### ③ CKE/workspace 申请后未初始化先读
- 查什么：是否存在**先读后写**路径；多 Phase 间 `SyncAll` 同步链是否闭合（Phase1 写 workspace → SyncAll → Phase2 读）；确定性分支临时缓冲是否自清零。
- 何处：kernel 双 Phase 结构、workspace 读写时序。

### ④ 原地写覆盖输入
- 查什么：`dst==src` 别名、同址先读后写、UB 槽复用 RAW 冒险；op_api 是否有 overlap/别名检查；无检查时是否属契约依赖（用户契约禁止重叠）。
- 何处：op_api 参数校验、kernel 中输入复用为输出的路径。
- 注意：契约依赖型（如 RoiAlign 读 rois 越界产出脏值写合法位置）记**观察项**，不定为缺陷命中。

### ⑤ 越界 / 尾块覆盖不完整
- 查什么：尾块 mask/`DataCopyPad` 精确字节是否覆盖完整（FP-A05 实证：Split-D 尾元素未覆盖）；index/偏移的位数（uint32 在 ≥2³² 时回绕）、uint 下溢（batch·num==0）、负偏移读；写范围是否精确限定。
- 何处：kernel 搬运与归约路径、tiling 的块数/offset 计算。
- 关联：越界写机理本身同步关联 FP-B07。

## 5. 检视流程

1. **定界**：换算 op 目录、确认所在仓与 ref；多仓命中时列出全部实现并逐一检视。
2. **枚举**：目录列表列出 op_api / op_host / op_kernel（含架构子目录）全部相关文件，产出文件清单。
3. **触发词扫描**：对枚举文件按 `workspace|GetWorkspaceSize|SetGlobalBuffer|Init(` 等触发词定位风险面（本地仓用 grep；API 模式逐文件拉取后检查）。
4. **五映射点逐项核查**：每点记录命中面与防护面证据（文件:行号）；对照第 4 节样板做同族反证。
5. **反证排除**：穷尽框架级防护（`SetNeedAtomic`、框架尾块处理、`SetBlockDim` 短路）、语义级分析（fill 语义即全量写）、同族已修复样板后再下结论。
6. **判定**：按第 7 节标准给出 命中 / 观察项 / 反证排除。
7. **GitCode 查重**（仅命中项）：issues API 按接口名检索，逐条比对是否同机理；无同机理才立卡。
8. **业务可达性核查**（仅命中项）：判 B 等级、定业务影响类型、给处置建议；默认保守（无法证明不可达即记 B3），降档须附证据；B 不改 S×O 档位。
9. **出报告**：按第 8 节模板落盘；所有运行时结论标注「静态推演，需 NPU 实测确认」。

## 6. 风险定级（S×O）与业务影响评估（B 轴）

- **S**：S4 致命（进程崩溃/挂死/数据静默损坏）、S3 结果错误、S2 功能受限、S1 资源浪费。
- **O**：O3 = ≥2 条独立实证；O2 = 1 条独立实证；O1 = 仅静态扫描命中或团队笔记（实证 = 确认对应的 issue / PR，或经跨仓、跨分支核验确认的缺陷记录，同权计入）。静态推演命中且无实证默认 **O1**；升档须在报告中给出实证依据。
- **风险 = S×O**：≥6 高；3/4 中；1/2 低。FP-A05 基准：有 issue 实证 S3×O2=6（高）；纯静态命中 S3×O1=3（中）。

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

- **签名/触发词命中 ≠ 成立**：必须过完整推导链 + 可达性分析 + 反证排除三关。
- **三种判定**：
  - **命中**：机理推导链完整 + 触发组合可静态证伪可达 + 反证排除失败 → 立 Bug 卡；
  - **观察项**：设计存疑但静态无法确证、契约依赖、存量非本次引入 → 记录不定级；
  - **反证排除**：防护在位 / 无行为变化 / 语义即全量写 → 明确写出反证理由。
- **可达性分析要给出可复现反例**：具体 shape/attr 组合与触发路径，反例要写到具体参数取值（如 aLoopCntTotal=7、rLoopCntTotal=11、coreNum=40 这样的参数组合）。
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
- **FP-A05 模式编号**：FP-A05 脏数据/数据踩踏（映射点①~⑤）
- **S×O 风险定级**：S3（结果错误）× O1（静态命中无实证）= 3，中
- **证据等级**：{静态可证 / 需实测确认}｜{一句话理由}
- **业务影响评估（B 轴）**：可达性 B{3|2|1}（{一句话判据}）｜ 业务影响：{静默精度损失/任务失败中断/性能退化/仅可观测性}｜ 证据：{调用方/公开负载/为何不可达}｜ 处置建议：{尽快修/排期修/记录}
- **故障机理推导链**：{逐步推导}
- **触发条件可达性分析**：{可复现反例组合}。静态推演，需 NPU 实测确认
- **建议修复方案**：{对齐同族已修复样板}
- **测试拦截建议**：空张量/零元素用例；workspace 复用下连续两次调用结果一致性；mssanitizer/memcheck 内存检测
- **Agent 误判记录**：{被推翻的假设 → 推翻证据 `[文件]:[行号] [代码行]`；无则「无」}
- **GitCode 查重**：{issues API 检索结论，无同机理 issue 才立卡}
```

### 检视报告结构

```markdown
# FP-A05 检视报告：{aclnn 接口名}（YYYY-MM-DD）
## 一、执行概览（仓/ref/HEAD、文件清单、判定统计：命中 X / 观察项 Y / 反证排除 Z；命中项 B 轴分布 B3×a / B2×b / B1×c）
## 二、命中明细（Bug 卡，按第 8 节字段，每卡含 B 轴业务影响评估）
## 三、观察项（表：# / 文件:行号 / 存疑点 / 性质）
## 四、反证排除（表：映射点 / 反证理由）
## 五、NPU 实测建议（用例清单：空张量组合矩阵、workspace 复用一致性、尾块边界 shape）
```

> 报告须在「执行概览」标注证据等级分布（静态可证 X / 需实测确认 Y），并在文末单列「Agent 误判记录」小节（无则写「无」）。

报告落盘到当前任务工作区，建议命名 `FP-A05检视_{接口名}_YYYYMMDD.md`。

## 9. 示例速览：aclnnAdd

- **定位**：`cann/ops-math` → `math/add/`（op_host/add_def.cpp、add_infershape.cpp、arch35/；op_api/；op_kernel/）。
- **检视面提示**（引导，不预设结论，仍须逐点核查）：
  - ① op_api 空张量/零元素早退是否填满全部输出；广播推导（infershape）退化组合。
  - ②③ add 类简单逐元素算子通常无 workspace，若枚举证实无 workspace 引用则 ②③ 反证排除并写明依据。
  - ④ 输出与输入别名路径的覆盖写语义。
  - ⑤ 切块尾块（非对齐 shape、大张量 index 位数）覆盖完整性。
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
python3 scripts/scan_fp.py --only FP-A05 --format json <目标文件>  # 签名候选（非结论）
python3 scripts/verify_lines.py <报告.md> --root <被检仓>        # 行号校验
python3 check_fault_patterns.py                                # 全库守门
```

### 工作量与抽样（v4.0）

- **深度档：标准**（索引 `depth` 字段）——每映射点取前 20 处命中；同一映射点连续 20 处反证排除即停止该点并记录。报告须写「抽样口径：每点前 20 处」。
- **报告必填**：抽样口径（全量 / 每点前 N 处 / 每类 N 例）+ 停止点记录；未写口径视为未完成。

## 11. 子型对照、量化基线与探针矩阵

### 子型对照

| # | 子型 / 检查面 | 检视落点 | 命中判据（代码级，可静态判定） | 运行时信号（探针确认） |
|---|---|---|---|---|
| ① | 缓冲区初始化缺失 | op_kernel `Init`/`AllocTensor` 后、首次写出前 | 输出缓冲在写出前被读：`SetAtomicAdd` 前无 `InitOutput`/`Duplicate(0)` 清零；原子输出无框架预清零 | 输入全 0 输出非 0；未初始化读（memcheck） |
| ② | workspace 未清零 | `GetWorkspaceSize` → `Init` 之间 | 存在 `if (g * chunk >= total) return;` 类**空闲核早退**，而消费 Phase **无条件全量读**同一 workspace 段；写范围 ⊊ 读范围 | 复用 workspace 残留：连续两次调用结果不同 |
| ③ | 原地写覆盖输入 | 输入输出同地址、in-place 算子 | `dstPtr == srcPtr` 别名、或 op_api 无 overlap 检查而 kernel 先读后写同址 / UB 槽复用无 RAW 保护 | 调用后输入张量被改写 |
| ④ | 越界尾块 | Split-D 尾元素、非整除 shape | 搬运字节按**满块常量**计算而 `tail = total % blockSize != 0`：`DataCopy(..., fullBlockBytes)` 未按尾块精确 mask | 尾部元素未覆盖：尾部 NaN 或旧值 |
| ⑤ | 多核踩踏 | 核间写同一 buffer | 多核写 `SetGlobalBuffer` **同基点 + 核内偏移**解析出的同一段，各核 offset 计算未互斥 | 结果随机；msSanitizer multi-core overwrite |

### 量化基线（数字来自卡片实证，引用须注明来源）

- 确认实证 **1 条**：ops-nn #5560（RmsNormGrad 空张量 dgamma NaN，Split-D 尾元素未覆盖；GM 清零 + bodyPart×2 修复，PR !9873）。
- 本型以 memcheck 为主而非签名扫描，故无「N 处」静态基线；命中判定依赖运行时证据（证据等级 `需实测确认`）。

### 探针矩阵（最小可执行集）

| 探针 | 构造 | 期望 / 判据 |
|---|---|---|
| 空张量矩阵 | numel==0、含 0 维 shape 逐个输入置空 | 不崩溃，输出为约定值（通常全 0） |
| workspace 复用 | 同一 workspace 连续两次调用，第二次换 shape | 两次结果逐位一致 |
| 越界读写 | mssanitizer memcheck 全量跑 | 无 illegal read/write、无 heap 越界 |
| 尾块覆盖 | Split-D 尾元素 × 非整除尾块 | 尾部元素与 golden 一致 |
| 多核并发 | 多核同时写同一输出段 | 无 multi-core overwrite |

### 证据锚点

- `ops-nn #5560` —— RmsNormGrad 空张量 NaN，修复 PR !9873
- `PR !9873` —— GM 清零 + bodyPart×2

### 交接边界

| 交给 | 遇到 | 理由 |
|---|---|---|
| [FP-B06](../../FP-B/fpb06-aclnn-review/SKILL.md) | 空 tensor 分支缺失（无判空） | 边界见第 0 节 |
| [FP-B07](../../FP-B/fpb07-aclnn-review/SKILL.md) | 越界读写（索引/偏移算式错） | 边界见第 0 节 |
| [FP-D01](../../FP-D/fpd01-aclnn-review/SKILL.md) | 内存容量（申请量推导） | 边界见第 0 节 |

### 复核清单（按子型）

- ① 空张量 / 零元素输入：输出是否全 0（而非旧值或 NaN）
- ② workspace 复用：同 workspace 连续两次调用结果是否一致
- ③ mssanitizer memcheck：是否有 illegal read/write 或未初始化读
- ④ Split-D 尾元素 / 非整除尾块：尾部元素是否被覆盖
- ⑤ 原地写：调用后输入张量是否被改写

## 12. 已知缺陷案例库：触发条件 / 根因 / 修复范式 / 针对性深挖（v5.1）

> 本节把本型**已确认缺陷**拆到「触发条件 → 根因（具体路径）→ 修复范式（✅ 正确代码）→ 针对性发现步骤 → 最小复现锚」的代码级颗粒度，供检视时**直接对照**。
> 修复范式为**正确形态示意**；路径引用取自卡片实证与第 4 节样板，行号以被检仓本地 HEAD 为准，**不得臆造**。

### 案例 1｜空张量/退化 shape 早退只填部分输出 —— ops-nn #5560（RmsNormGrad）

- **触发条件**：任一输入 `Numel() == 0`（空张量 / 含 0 维 shape）→ 算子走 `IsEmpty` 早退；早退分支只对 **N 个输出中的 M 个（M < N）** 写入。
- **根因（具体路径）**：早退分支仅对部分输出调 `GetOutWithValueZero` / `ViewCopy`，其余输出保持未初始化 → 读出脏值 / NaN（dgamma 即未被写入者）。
- **修复范式（✅，示意）**：

```cpp
// ❌ 早退只填一个输出，其余输出未初始化即返回
if (IsEmpty(x)) { *workspaceSize = 0; return ACLNN_SUCCESS; }
// ✅ 早退时逐输出写约定值（GetOutWithValueZero / ViewCopy 填 0）
if (IsEmpty(x)) {
  for (auto* out : {y, dgamma}) {                 // 遍历该算子「全部」输出
    if (out != nullptr && out->Numel() > 0) GetOutWithValueZero(out);
  }
  *workspaceSize = 0; return ACLNN_SUCCESS;
}
```

- **针对性发现（可执行）**：① `grep -n "IsEmpty\|numel.*==\s*0"` 定位全部早退点；② 列出该算子**全部输出**（以 op_host 原型为准）；③ 逐早退点核对「早退内被写输出数 vs 总输出数」，**差集即嫌疑**；④ 与同族已修复样板对照。
- **最小复现锚**：构造 dgamma 相关输入 `numel == 0` 的调用，比对**全部**输出是否均为约定值（非 NaN / 旧值）。
- **实证 / 样板**：ops-nn **#5560**（修复 PR !9873：GM 清零 + bodyPart×2）；**缺陷做法样板** `ops-cv image/grid_sampler2d_grad/op_api/aclnn_grid_sampler2d_backward.cpp:240-246`（任一输入空即 `*workspaceSize=0` 早退且**不填任何输出**）；**正确样板** `ops-cv image/roi_align/op_api/aclnn_roi_align.cpp:189-197`（早退 `GetOutWithValueZero` + `ViewCopy` 填 0）。

### 案例 2｜workspace 未清零：空闲核不写 × 消费方全量读 —— 历史例 reduce_std_with_mean

- **触发条件**：Phase1 分核步进出现**空闲核 / 组**（提前 return 不写 workspace）；Phase2 **无条件**按全量读同一 workspace 当部分和；工作量与分核数不整除。
- **根因**：双 Phase kernel 中 Phase1 空闲核不写 → 残留脏 GM；Phase2 读范围 ⊋ Phase1 写范围，且缺 `SyncAll` 前置，残留被当作部分和读入。
- **修复范式（✅，示意）**：

```cpp
// ❌ CeilDiv 分组产生空闲组，组内越界即 return 不写 workspace；Phase2 无条件全行读
for (int g = blockIdx.x; g < CeilDiv(total, chunk); g += nCores) { if (g * chunk >= total) return; ... }
// ✅ 等分改 FloorDiv 使每组 ≥1 chunk（无空组）；或越界组显式写 0；Phase1 写满后 SyncAll 再读
```

- **针对性发现**：① `grep -n "CeilDiv\|FloorDiv"` 定位分组步进；② 判定是否存在「组内越界 return」；③ 核对 Phase2 读范围是否**严格等于** Phase1 写范围；④ 定位 `SyncAll` 是否位于读之前。
- **最小复现锚**：选分组数与工作量不整除的 shape，**同一 workspace 连续两次调用**（第二次换 shape），比对两次结果一致性。
- **实证 / 样板**：卡片历史例 `ops-math reduce_std_with_mean`（Phase1 CeilDiv 空闲组不写、Phase2 全行读残留脏数据当部分和）。

### 案例 3｜尾块覆盖不完整 —— Split-D 尾元素未覆盖（并入 ops-nn #5560）

- **触发条件**：末维非对齐（如 31 / 32 / 33）、Split-D 切分后尾块 < 满块；搬运字节按满块计算。
- **根因**：搬运字节数按**满块常量**取，尾块实际数据量 < 满块字节 → 尾部元素从未写出（或被相邻元素覆盖）。
- **修复范式（✅，示意）**：

```cpp
// ❌ 按满块字节搬运，尾块不足时尾部元素未覆盖
DataCopy(dst, src, fullBlockBytes);
// ✅ 按尾块实际字节精确搬运（DataCopyPad 精确 mask，或先算 tail 再裁字节）
int64_t tail = total - (blockCnt - 1) * blockSize;      // 末块实际元素数
DataCopyPad(dst, src, {1, static_cast<uint16_t>(tail * sizeof(T)), 0, 0});
```

- **针对性发现**：① 找全部 `DataCopy` / `DataCopyPad` 的字节 / 元素参数；② 与 `tail = total % blockSize` 比较；③ 尾块路径是否单独处理（是否复用满块参数）。
- **最小复现锚**：末维 31 / 32 / 33 + 尾块非整除，比对**尾部元素**与 golden（常表现为尾部 NaN / 旧值）。
- **实证**：ops-nn #5560 含「Split-D 尾元素未覆盖」；相邻机理（越界写）见 FP-B07。

### 案例 4｜原地写覆盖输入（别名 / UB 槽复用）

- **触发条件**：`dst` 与 `src` 同址（inplace 算子）；UB 槽复用且先读后写无 RAW 保护。
- **根因**：kernel 在输入尚未读完时即向同址写出；或 op_api 未做 overlap / 别名检查（契约为不重叠时降观察项）。
- **修复范式（✅，示意）**：

```cpp
// ❌ 复用同一 UB 槽：先向槽写出再读入下一段输入 → 覆盖未消费数据
// ✅ 输入 / 输出独立 UB 槽；或写前 SyncAll / 双缓冲隔离读写
```

- **针对性发现**：① 查 op_api 是否有 overlap / 别名检查；② 枚举 kernel 内「输入张量复用为输出」的路径；③ 契约依赖型记**观察项**（不立卡）。
- **最小复现锚**：调用后比对输入张量是否被改写（不可变输入应逐位不变）。

### 案例 5｜CKE / workspace 申请后未初始化先读

- **触发条件**：kernel 经 CKE 申请临时 / workspace 后未初始化即被读；多 Phase 间 `SyncAll` 链未闭合。
- **根因**：复用到的缓存保留上一轮残留；首读之前无清零、无 `SyncAll`。
- **修复范式（✅，示意）**：

```cpp
// ❌ 申请后直接使用，缓存保留上轮残留
auto tmp = cke::Alloc(...);  use(tmp);
// ✅ 申请 → 清零 → SyncAll → 使用
auto tmp = cke::Alloc(...);  Duplicate / ZerosLike(tmp);  SyncAll();  use(tmp);
```

- **针对性发现**：① `grep -n "Alloc\|SetGlobalBuffer"` 后定位其**首个读点**；② 核对清零点与 `SyncAll` 是否位于首读之前。
- **最小复现锚**：workspace 复用下连续两次调用，比对结果一致性。

### 语料基线与深挖起手式

- **语料基线**：日常测试集失败报告中「内存检测 / 内存安全」类 **422 条**（v2.13 卡片）；其中「内存未初始化 / CKE 申请后未初始化」归属本型。
- **深挖起手式（本模式固定顺序）**：
  1. `python3 scripts/scan_fp.py --only FP-A05 --format json <目标文件>` —— 先收敛候选面（memcheck 为主，签名仅辅助）；
  2. 按第 4 节 ①~⑤ 逐点核查，命中面 / 防护面均记 `文件:行号`；
  3. 对每处嫌疑**对照本节 5 个案例的「修复范式」**判断是否偏离正确形态；
  4. 出卡前跑 `python3 scripts/verify_lines.py <报告.md> --root <被检仓>` 校行号。
