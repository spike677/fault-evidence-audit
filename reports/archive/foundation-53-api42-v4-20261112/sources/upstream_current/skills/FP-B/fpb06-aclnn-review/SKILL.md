---
name: "fpb06-aclnn-review"
description: "基于 FP-B06「空 tensor 输入分支处理缺失」故障模式对指定 aclnn 接口做源码检视：定位算子实现，逐输入核对 IsEmpty 判空覆盖、早退完整性、平台两侧对称性与 kernel 0 元素适配，产出证据链与 S×O 定级报告。当用户给出接口名做空 tensor、numel==0、含 0 维 shape 输入或 PyTorch PASS 而 NPU 失败的排查时使用。"
---

# FP-B06 aclnn 接口检视（fpb06-aclnn-review）

对用户指定的 aclnn 接口（如 aclnnInplaceMaskedScatter）做 FP-B06 专项源码检视：先定位算子实现，再按清单逐项核查，每个结论给出**文件 + 行号 + 推导链**证据，命中即出 Bug 卡，输出检视报告。**本模式特殊纪律：① 卡片适用声明为「必须触发」——不依赖签名命中，对被检接口逐输入无条件执行判空清单；② 空输入是否**语义合法**以 PyTorch 参考实现为准——「误拦合法空输入」（应 no-op 却报错）与「放过非法组合」（应报错却静默 SUCCESS）是方向相反的两种缺陷，都要立卡；③ 平台分支常不对称（非 regbase 与 regbase 各一套实现），修复常只 gate 一侧——判空核对须**双平台分别立证**；④ 判空后必须「早退完整」（置 workspaceSize=0 + ReleaseTo + 返回 SUCCESS），只跳过 `Contiguous` 仍透传 0 元素 buffer 的半程保护同样是缺陷形态。**

## 0. 与相邻模式的边界

| 相邻模式 | 分工 |
|---|---|
| FP-B04（nullptr 校验缺失） | **最易混淆项**：B04 是**指针本身为空**；本条是 `numel==0` 的**语义分支**缺失（指针有效）。两者可共现于同一 `CheckParams`，探针分别构造 |
| FP-B05（校验覆盖度参差） | 同源——B05 是文件级校验范差不齐；本条聚焦空 tensor 这一**单语义**在接口内的覆盖 |
| FP-A04（静默错误） | 未拦截的空输入可能演变为静默结果 / 精度故障——「空输入被吞成 SUCCESS」正是 A04 的一种入口 |
| FP-A19（多 tiling 路径盲区） | 非 regbase 与 regbase 属**两条路径**，本条子型③的平台不对称可视为 A19 在空输入语义上的投影——修复只 gate 一侧时另一侧成盲区 |
| FP-G01（挂死） | 空 / 0 元素输入是**回绕长循环的高发形态**（G01 子型③）：同一输入、两个后果面，核本条时同步核 G01 |
| FP-E01（golden 失配） | golden/UT 未覆盖空输入时同样「与错误实现共错」——存量用例无 0 维 shape 不是安全证据 |

**症状反查定位**：失败用例的输入里必有一个**含 0 维的 shape** → 首查该输入的 `IsEmpty()` 分支；PyTorch CPU/CUDA 同用例 PASS 而 NPU 第一段接口报错 → 合法空输入被误拦；非法组合（如 mask 有 true 而 source 空）静默出「成功」→ 该报错没报错；内核读越界 / 读出 NaN → kernel 0 元素未适配；图模式下 shape / dtype 推导异常 → infershape 面。

## 1. FP-B06 模式卡摘要（检视依据，源自本库 `patterns/FP-B/FP-B06.md`，v3.1）

- **编号 / 名称**：FP-B06 空 tensor（numel==0）输入分支处理缺失 ｜ **类别**：功能/兼容 ｜ **风险**：高（S3×O2=6）｜ **状态**：活跃
- **适用声明头**（照抄卡片）：仓 All ｜ 侧别 Host,Tiling,Kernel ｜ 载体 aclnn源码,Tiling源码,Kernel源码 ｜ 触发 必须触发 ｜ 默认启用 true
- **skill 核查面**：侧别 Host,Tiling,Kernel——skill 落地为 `op_api/aclnn_*.cpp` 的 GetWorkspaceSize 判空（子型①②）、`op_host` 的 arch22 与 regbase 双侧 tiling（子型③ 的 host 面）、`op_kernel` 的 `Init()` / `SetGlobalBuffer` 长度来源、`docs/aclnn*.md` 的元素数约束自洽
- **故障机理**：aclnn 两段式接口对「空 tensor（numel==0，即 shape 含 0 维）」这一**语义可能合法的输入形态**缺少分支处理，三种子形态：① **判空覆盖不全**——同一接口只对部分输入调 `IsEmpty()`（典型：`selfRef`/`mask` 判了、`source`/`updates` 类第二输入漏判）；② **完全未判空**——空 tensor 被当正常输入继续 `l0op::Contiguous` / `Cast` / 算子构建（部分实现已有「判空后只跳过连续化」的半程保护，但仅跳过 `Contiguous`，仍把 0 元素 buffer 交给算子）；③ **平台分支不对称**——`!Ops::NN::AclnnUtil::IsRegbase()`（arch22 / A2A3）与 regbase（arch35 / 950）各有一套实现与 kernel，修复常只 gate 一侧。空输入进入 arch22 算子后，tiling/kernel 未适配 0 元素：kernel `Init()` 用**由 mask/shape 推导的元素数**（而非该 tensor 自身元素数）去 `SetGlobalBuffer`，等于把 0 字节分配注册成非 0 长度；source 元素数不足时更会读到分配外地址（越界/NaN）。
- **触发条件**：任一输入（尤其可选输入 / 第二输入：masked_scatter 的 `source`、Dropout 的 `mask`、量化类的 `scales`/`zeroPoints`/`smoothScale`）numel==0；平台为 A2/A3（非 regbase）；同算子 tiling/kernel 未对 0 元素早退。语义上「空输入是否合法」须以 PyTorch 为准（如 masked_scatter 中 `source` 为空**仅当 mask 无 true 元素时合法**，此时应为 no-op 而非报错）。
- **典型表现**：**PyTorch CPU/CUDA 同用例 PASS、NPU 侧第一段接口报错或执行失败**（合法空输入被误拦截）；或判空早退把**非法**组合（mask 有 true 而 source 空）静默吞成 SUCCESS，掩盖参数错误；或内核读越界 / 读出 NaN；或图模式下 shape/dtype 推导异常。特征信号：失败用例的输入里必有一个含 0 维的 shape。
- **源码审查映射点**：`op_api/aclnn_*.cpp` 的 `GetWorkspaceSize` 内逐参数核对——每个 `const aclTensor*`（输入）与 `aclTensor*`（inplace 张量如 `selfRef`）是否都有 `->IsEmpty()` 判断，判空后是否 `*workspaceSize = 0; uniqueExecutor.ReleaseTo(executor); return ACLNN_SUCCESS;` 早退；空 tensor 是否只跳过 `Contiguous` 却仍透传给 `l0op::Xxx`；`!Ops::NN::AclnnUtil::IsRegbase()` 两侧是否各自有空 tensor 策略（含 `ProcessBroadcast` 这类 regbase 专用分支）；arch22 `op_host/*_tiling.cpp` 是否对 0 元素校验/早退；kernel `Init()` 中 `SetGlobalBuffer(tensor, 长度)` 的长度是否取自该 tensor 自身元素数；`docs/aclnn*.md` 的元素数约束（如「source 元素数量需要大于等于 mask 中元素为 true 的数量」）与代码判空行为是否自洽。
- **检测签名**：静态扫描「aclnn 接口 × 每个输入参数 × 是否有 `IsEmpty()`」——接口内 `IsEmpty()` 覆盖的输入数 < 输入张量个数 ⇒ **判空遗漏（PARTIAL）**；接口与同算子 host/kernel 层均无 `IsEmpty|EmptyTensor|GetShapeSize()==0` 关键字 ⇒ **全链路无感知（HIGH）**。四仓基线（2026-09-14，1040 个 aclnn 接口）：**PARTIAL 141 / HIGH 461 / 有 kernel 感知 88 / 全覆盖 328**；其中 ops-transformer 全覆盖仅 8/250，ops-math 有 182 个 HIGH。
- **测试拦截建议**：空 tensor 探针矩阵 =「接口 × 输入位置 × 空形态（0 维标量 / 含 0 维 shape / 正常）」；期望值以 PyTorch CPU 参考实现为准（合法空输入 → 输出等价于 no-op；非法组合 → 明确报错而非静默 SUCCESS）；**优先覆盖「已写判空但漏了一个输入」的接口**（作者已具备空 tensor 意识，遗漏概率最高）；空用例须同时跑 regbase 与非 regbase 平台（修复常只 gate 一侧）；「mask 无 true + source 空」这类合法组合必须显式建例（PyTorch 侧全 PASS 而 NPU 曾失败）；建议把静态扫描纳入 CI，新增判空遗漏即失败。
- **实证案例**：ops-nn **PR #9197 / issue #5149**（2026-08-25 合入 master）——`index/masked_scatter/op_api/aclnn_masked_scatter.cpp` 的 `aclnnInplaceMaskedScatterGetWorkspaceSize` 原有 `if (selfRef->IsEmpty() || mask->IsEmpty())` 早退但**漏了 `source`**，修复新增 `if (!Ops::NN::AclnnUtil::IsRegbase() && source->IsEmpty()) { *workspaceSize = 0; uniqueExecutor.ReleaseTo(executor); return ACLNN_SUCCESS; }`（仅 gate arch22，950 走 `ProcessBroadcast` 自带保护）；issue 复现组合 `target=(4,8), mask=(4,1) 或 (4,8), mask_true=0, source=(0,8)` 在 PyTorch CPU/CUDA 四组全 PASS 而 **910b（A2）侧失败**。同仓 2026-04-29 issue「masked_scatter 当 updates 元素不够时存在内存访问越界或读取 NAN（A3）」为同源风险的另一侧（元素数不足而非恰为 0）。该修复的两点不足已记录：**未覆盖非 inplace 的 `aclnnMaskedScatter`**、**未沉淀 ST 用例**（现有 200 条 ST 用例无 0 维 shape，PR「测试」仅贴 PyTorch 参考输出）。
- **关联**：FP-B04（相邻但不同：B04 是 `nullptr` 指针缺失，本条是 numel==0 的**语义分支**缺失，两者可共现于同一 `CheckParams`）、FP-B05（同源——文件级校验范差不齐）、FP-A04（未拦截的空输入可能演变为静默结果/精度故障）、FP-A19（arch22 与 regbase 属两条路径，多路径覆盖盲区同样适用）、FP-E01（golden/UT 未覆盖空输入时同样会出现「与错误实现共错」）。

## 2. 检视输入与算子定位

**输入**：aclnn 接口名（必填，如 `aclnnInplaceMaskedScatter`）；可选 ref（默认 master）、指定仓（默认自动定位）；可选现象描述（PyTorch PASS 而 NPU 失败 / NaN / 误拦截——用于症状反查）；可选平台信息（A2/A3 还是 950——决定子型③ 先核哪一侧）。

**接口名 → 算子目录换算**：去 `aclnn` 前缀与 `Inplace` 中缀 + 驼峰转下划线小写，再以目录列表确认（`aclnnInplaceMaskedScatter` 与 `aclnnMaskedScatter` 同属 `index/masked_scatter/`）。

**仓定位顺序**（GitCode `cann` 组织，逐仓用目录列表确认）：`ops-nn`（norm/loss/activation/index/matmul 类）→ `ops-math`（math/conversion 类，实测 HIGH 数最大）→ `ops-cv`（image/vision 类）→ `ops-transformer`（attention/moe 类，实测全覆盖比例最低）。FP-B06 高发面：带可选输入 / 第二输入的接口（scatter / index 类、量化类的 scales/zeroPoints、Dropout 的 mask）、有 `Inplace` 与非 `Inplace` 双变体的接口、带 `ProcessBroadcast` 类 regbase 专用分支的接口。

**算子目录结构约定**（已验证示例 `cann/ops-nn` → `index/masked_scatter/`；`op_api` 位置随算子而异——masked_scatter 在顶层 `op_api/`，fused_quant_mat_mul 在 `op_host/op_api/`，以目录列表为准）：

```text
{类别}/{op_name}/
├── op_api/（或 op_host/op_api/）  # aclnn_*.cpp——逐输入 IsEmpty 判空与早退：子型①②③ 主检视面
├── op_host/                  # tiling（arch22/ 与 arch35/ 双侧目录）：0 元素校验/早退
├── op_kernel/                # kernel Init() 的 SetGlobalBuffer 长度来源：0 元素适配
├── docs/                     # aclnn*.md——元素数约束与判空行为自洽面
└── tests/                    # 存量用例是否含 0 维 shape（覆盖缺口的现存证据）
```

## 3. 取数方式（Important）

公开网页端点被拦截，**必须走 API**（均需带 `User-Agent`；失败重试 2 次、间隔 5 秒）：

| 用途 | 端点 |
|---|---|
| 目录列表 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/contents/{path}?ref={ref}` |
| 单文件内容 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/raw/{path}?ref={ref}` |
| Issue 查重 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/issues?q={关键词}` |

**已实测不可用（截至 2026-09 实测）**：`https://gitcode.com/{repo}/raw/{sha}/{path}`、`https://raw.gitcode.com/...` → 403 或拦截页；端点策略如有变化可复测。若本地已有算子仓克隆，优先直接读本地文件，行号证据以本地 HEAD 为准并记录 commit。**本模式特有取数限制**：「空输入是否语义合法」必须对照 **PyTorch 参考实现**（CPU 版行为），静态读 NPU 代码不可判定合法性；四仓判空基线（PARTIAL 141 / HIGH 461 等）是 2026-09-14 时点快照，引用时注明时点。

## 4. 空 tensor 分支检视清单（每点：查什么 → 何处 → 命中判据）

对 `op_api` / `op_host` 双侧 tiling / `op_kernel` / docs 逐点核查，**每点先查命中面、再做反证排除**，已有的判空与平台保护也要记录（防护面证据）。

### ① 判空覆盖矩阵（子型①）
- 查什么：`GetWorkspaceSize` 内**每个**输入张量（`const aclTensor*` 输入与 `selfRef` 类 inplace 张量）是否都有 `->IsEmpty()` 判断——「判了 A、B 漏了 C」即子型①（实证样板：masked_scatter 原有 selfRef/mask 判空漏 source）。
- 何处：`op_api/aclnn_*.cpp` 的 GetWorkspaceSize 函数体，从入口到首个算子构建调用之间。
- 命中判据：`IsEmpty()` 覆盖数 < 输入张量个数 ⇒ 命中（给出「输入 → 判空行号（或缺失）」对表）。

### ② 判空后早退完整性 + 半程保护识别（子型②）
- 查什么：判空命中后是否**早退完整**——`*workspaceSize = 0; uniqueExecutor.ReleaseTo(executor); return ACLNN_SUCCESS;`；同时识别**半程保护**：`if (source->IsEmpty()) sourceContiguous = source;` 只跳过 `Contiguous` 却仍把 0 元素 buffer 透传给算子构建——这不是有效防御。
- 何处：全部 `IsEmpty()` 命中分支；`l0op::Contiguous` / `l0op::Cast` / 算子构建调用点对空 tensor 的处理。
- 命中判据：命中分支早退不完整（缺 ReleaseTo / 缺 return），或空 tensor 绕过判空直接进入 `l0op::Xxx` ⇒ 命中。

### ③ 平台两侧对称性（子型③）
- 查什么：`!Ops::NN::AclnnUtil::IsRegbase()`（arch22）与 regbase（arch35）**两侧**是否各自有空 tensor 策略——修复常只 gate 一侧（实证样板：修复行 `!IsRegbase() && source->IsEmpty()` 仅 gate arch22，950 依赖 `ProcessBroadcast` 内 `!source->IsEmpty()` 的自有保护）；判空分支的平台条件写反（只 gate 了已有保护的一侧）同属命中。
- 何处：`op_api` 的平台分流点（`IsRegbase` / `curArch` 判断）、`ProcessBroadcast` 类 regbase 专用分支内部、`op_host` 的 arch22/ 与 arch35/ 双侧 tiling。
- 命中判据：一侧有保护、另一侧无，且无保护侧空输入会继续走算子构建 ⇒ 命中（双平台分别立证）。

### ④ arch22 tiling / kernel 的 0 元素适配
- 查什么：arch22 侧 `*_tiling.cpp` 是否对 0 元素校验/早退；kernel `Init()` 中 `SetGlobalBuffer(tensor, 长度)` 的**长度来源**——由 mask/shape 推导的元素数会把 0 字节分配注册成非 0 长度；「元素数不足」（updates 不够 mask 的 true 数）的同源越界面一并核。
- 何处：`op_host/arch22/*_tiling.cpp`、`op_kernel/*.cpp` 的 `Init()`。
- 命中判据：存在「元素数为 0 或推导长度 > 该 tensor 实际字节数」的静态路径 ⇒ 命中（越界/NaN 后果需实测，先立静态路径）。

### ⑤ 非法组合的拦截方向
- 查什么：判空早退是否**无条件放行**——「mask 有 true 而 source 空」属非法组合，静默 SUCCESS 会掩盖参数错误；早退分支应区分「合法空 → no-op」与「非法组合 → 报错」（对照 PyTorch 语义）。
- 何处：全部空 tensor 早退分支；docs 的元素数约束（如「source 元素数量需要大于等于 mask 中元素为 true 的数量」）与早退行为的自洽性。
- 命中判据：非法组合走早退返回 SUCCESS 且无参数错误提示 ⇒ 命中（方向：放过）。

### ⑥ 双变体与测试资产
- 查什么：`Inplace` 与非 `Inplace` 变体是否**都**有判空（实证修复未覆盖非 inplace 变体）；存量 ST 用例是否含 0 维 shape（200 条无 0 维 = 覆盖缺口现存证据）；issue「测试」是否只贴参考输出未沉淀用例。
- 何处：同目录全部 `aclnn_*.cpp` 变体；`tests/` 用例的 shape 清单。
- 命中判据：变体间判空覆盖差 ⇒ 命中；用例缺口记观察项（测试建设项）。

## 5. 检视流程

1. **定界**：换算 op 目录、确认所在仓与 ref；按用户现象（误拦截 / 静默成功 / NaN）反查优先子型；确认平台信息（先核对应侧）。
2. **枚举**：目录列表列出 `op_api` 全部变体、`op_host` 双侧 tiling、`op_kernel`、docs，产出文件清单；构建**输入参数表**（输入 / inplace / 可选，与 docs 约束交叉确认）。
3. **触发词扫描**：按 `IsEmpty\s*\(`、`EmptyTensor|GetShapeSize\(\)\s*==\s*0`、`IsRegbase|ProcessBroadcast`、`SetGlobalBuffer` 定位风险面（本地仓用 grep；API 模式逐文件拉取后检查）。**卡片触发为「必须触发」：签名零命中（无任何 `IsEmpty`）时清单仍须逐项核查完毕——零命中本身就是 HIGH 档信号。**
4. **清单逐项核查**：按第 4 节 ①~⑥ 逐点记录命中面与防护面证据（文件:行号）；`IsEmpty` 命中数与输入数逐一对表。
5. **反证排除**：每输入判空 + 早退完整 + 双平台各自保护 + 非法组合正确报错 → 明确写出反证理由（防护面证据）。
6. **判定**：按第 7 节标准给出 命中 / 观察项 / 反证排除。
7. **GitCode 查重**（仅命中项）：issues API 按接口名 + `空tensor|empty|numel|0维|IsEmpty` 检索，逐条比对是否同机理；无同机理才立卡。
8. **业务可达性核查**（仅命中项）：判 B 等级、定业务影响类型、给处置建议；默认保守（无法证明不可达即记 B3），降档须附证据；B 不改 S×O 档位。
9. **出报告**：按第 8 节模板落盘；静态结论一律附「PyTorch 对照 + 双平台」探针方案。

## 6. 风险定级（S×O）与业务影响评估（B 轴）

- **S**：S3（空输入致内核读越界 / NaN，或合法输入被误拦功能不可用）；S2（非法组合静默 SUCCESS 掩盖参数错误——渐进暴露）。
- **O**：O3 = ≥2 条独立实证；O2 = 1 条独立实证；O1 = 仅静态扫描命中或团队笔记（实证 = 确认对应的 issue / PR，或经跨仓、跨分支核验确认的缺陷记录，同权计入）。静态推演命中且无实证默认 **O1**；升档须在报告中给出实证依据。
- **风险 = S×O**：≥6 高；3/4 中；1/2 低。FP-B06 基准：模式卡整体 S3×O2=6（高）；纯静态命中 S3×O1=3（中，暂定，探针实证后复评）。

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

- **`IsEmpty()` 命中 ≠ 防御完整**：须核对**每个**输入（子型① 的对表法）；命中分支须早退完整（子型②）；两侧平台分别立证（子型③）——只 gate 一侧的判空不是完整防御。
- **「报错拦截」不一定是缺陷、也不一定不是**：判空方向必须对照 **PyTorch 语义**——合法空输入被报错拦截 = 命中（误拦）；非法组合被报错 = 正确行为（反证证据）；非法组合静默 SUCCESS = 命中（放过）。**不对照 PyTorch 就不下拦截方向结论。**
- **三种判定**：
  - **命中**（可静态证缺陷路径）：输入对表存在缺判空输入 / 半程保护 / 单侧 gate / 非法组合静默放行的完整推导链 → 立 Bug 卡；
  - **观察项**：越界 / NaN 后果依赖运行时形态（元素数推导 vs 实际字节）→ 记录并附 PyTorch 对照探针方案；
  - **反证排除**：全输入判空 + 早退完整 + 双侧各有策略 + 拦截方向与 PyTorch 一致 → 写出防护面证据。
- **四仓基线是时点快照**：PARTIAL/HIGH 计数引用时注明 2026-09-14 时点，不作为当前版本的实时状态。
- **不臆造行号**：每条证据必须是实际读到的 文件:行号；引用实证样板时同样给出路径与行号。

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
- **命中清单点**：①~⑥ 中的编号与子型（①判空覆盖不全 / ②半程保护或早退不完整 / ③平台不对称 / ④kernel 0 元素未适配 / ⑤非法组合放过 / ⑥变体覆盖差）
- **文件路径与行号证据**：
  - `{文件}:{行号}`：{已判空输入的 IsEmpty 行}
  - `{文件}:{行号}`：{漏判输入的首次使用行（或标注「全文件无判空」）}
  - 防护面记录（反证检查结果，含另一平台侧）：{文件}:{行号}
- **FP-B06 模式编号**：FP-B06 空 tensor（numel==0）输入分支处理缺失
- **S×O 风险定级**：S3（越界/误拦）× O1（静态命中无实证）= 3，中（暂定，探针实证后复评）
- **证据等级**：{静态可证 / 需实测确认}｜{一句话理由}
- **业务影响评估（B 轴）**：可达性 B{3|2|1}（{一句话判据}）｜ 业务影响：{静默精度损失/任务失败中断/性能退化/仅可观测性}｜ 证据：{调用方/公开负载/为何不可达}｜ 处置建议：{尽快修/排期修/记录}
- **故障机理推导链**：{空输入 → 缺判空/半程保护 → 0 元素 buffer 透传/推导长度注册 → 越界或误拦}
- **输入参数表**：{参数 → 判空行号（或缺失）→ 平台条件 → PyTorch 语义（合法 no-op / 非法报错）}
- **探针方案**：{接口 × 输入位置 × 空形态} 矩阵；合法组合（mask 无 true + source 空）显式建例；regbase 与非 regbase 双平台执行
- **建议修复方案**：{补 IsEmpty 早退（注意 gate 哪一侧）/ kernel 0 元素早退 / 非法组合报错}
- **Agent 误判记录**：{被推翻的假设 → 推翻证据 `[文件]:[行号] [代码行]`；无则「无」}
- **GitCode 查重**：{issues API 检索结论，无同机理 issue 才立卡}
```

### 检视报告结构

```markdown
# FP-B06 检视报告：{aclnn 接口名}（YYYY-MM-DD）
## 一、执行概览（仓/ref/HEAD、现象、输入参数表、判定统计：命中 X / 观察项 Y / 反证排除 Z；命中项 B 轴分布 B3×a / B2×b / B1×c）
## 二、命中明细（Bug 卡，按第 8 节字段，每卡含 B 轴业务影响评估）
## 三、观察项（表：# / 子型 / 文件:行号 / 存疑点 / PyTorch 对照探针方案）
## 四、反证排除（表：子型点 / 反证理由 / 防护面证据，含双平台）
## 五、测试建设建议（空形态探针矩阵、双变体补判空、存量用例 0 维 shape 缺口）
```

> 报告须在「执行概览」标注证据等级分布（静态可证 X / 需实测确认 Y），并在文末单列「Agent 误判记录」小节（无则写「无」）。

报告落盘到当前任务工作区，建议命名 `FP-B06检视_{接口名}_YYYYMMDD.md`。

## 9. 示例速览：aclnnInplaceMaskedScatter

- **定位**：`cann/ops-nn` → `index/masked_scatter/`（op_api/aclnn_masked_scatter.cpp——本算子 op_api 在顶层；op_host/arch22/masked_scatter_tiling.cpp 与 op_host/arch35/masked_scatter_tiling_arch35.cpp 双平台；op_kernel/masked_scatter.cpp；docs/aclnnInplaceMaskedScatter.md；tests/ 存量用例）。
- **检视面提示**（引导，不预设结论，仍须逐点核查；行号以本地 HEAD 为准）：
  - `aclnnInplaceMaskedScatterGetWorkspaceSize`（:480 定义）：:496 `if (selfRef->IsEmpty() || mask->IsEmpty())` 早退——**原有判空只覆盖 selfRef/mask**（实证 PR #9197 前形态）；
  - :503 `if (!Ops::NN::AclnnUtil::IsRegbase() && source->IsEmpty())` + :505-507 早退——**PR #9197 补的 source 判空，仅 gate arch22**；950 侧走 `ProcessBroadcast`（:380 定义，:403 `if (!source->IsEmpty())` 自有保护）——核对两侧保护是否真的各自完整（子型③）；
  - :531 `if (source->IsEmpty()) sourceContiguous = source;`——判空但**只跳过 Contiguous** 的半程保护形态（子型② 的识别样板：早退不在此处，须继续核后续是否仍透传）；
  - :548 `if (!IsRegbase())` 平台分流 → :551 `ProcessBroadcast`；arch22 侧继续走 l0op 构建链——子型④ 在 op_host/arch22/masked_scatter_tiling.cpp 与 op_kernel 的 0 元素路径上核查；
  - docs/aclnnInplaceMaskedScatter.md :98「source 元素数量需要大于等于 mask 中元素为 true 的数量」——与判空行为自洽性（子型⑤）；:146 空指针约束行与 B04 的分工；
  - 卡片记录的修复两点不足列为待复核项：非 inplace `aclnnMaskedScatter` 变体的判空覆盖、存量 ST 用例无 0 维 shape（子型⑥）。
  - 期望值参照：`mask_true=0 + source=(0,8)` 合法组合在 PyTorch CPU/CUDA 四组全 PASS 而 910b 曾失败（issue #5149）。
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
python3 scripts/scan_fp.py --only FP-B06 --format json <目标文件>  # 签名候选（非结论）
python3 scripts/verify_lines.py <报告.md> --root <被检仓>        # 行号校验
python3 check_fault_patterns.py                                # 全库守门
```

### 工作量与抽样（v4.0）

- **深度档：深度**（索引 `depth` 字段）——全量核查，不抽样。全部映射点 / 分支逐条过；单模式命中 > 50 处时按文件分片，并在报告写明分片口径。
- **报告必填**：抽样口径（全量 / 每点前 N 处 / 每类 N 例）+ 停止点记录；未写口径视为未完成。

## 11. 已知缺陷案例库：触发条件 / 根因 / 修复范式 / 针对性深挖（v5.1）

> 本节把本型**已确认缺陷**拆到代码级颗粒度（触发条件 → 根因/路径 → 修复范式 ✅ → 发现步骤 → 复现锚）。修复范式为**示意**，路径取自卡片实证，**不臆造行号**。

### 案例 1｜只判 selfRef/mask、漏判第二输入 source —— #5149（masked_scatter）

- **触发**：`aclnnInplaceMaskedScatter` 的 `source` 为 numel==0（如 `source=(0,8)`）而 `mask` 全 false、平台 A2/A3（非 regbase）。
- **根因（路径）**：`index/masked_scatter/op_api/aclnn_masked_scatter.cpp` 的 `aclnnInplaceMaskedScatterGetWorkspaceSize` 原早退 `if (selfRef->IsEmpty() || mask->IsEmpty())`（§9 例 :496）漏判 `source` → 0 元素 buffer 继续走 l0op → arch22 侧失败。修 PR #9197。
- **修复范式（✅，示意）**：

```cpp
// ❌ 只覆盖 selfRef / mask
if (selfRef->IsEmpty() || mask->IsEmpty()) { /* 早退 */ }
// ✅ 补第二输入并 gate arch22（950 走 ProcessBroadcast 自带保护）
if (!Ops::NN::AclnnUtil::IsRegbase() && source->IsEmpty()) {
    *workspaceSize = 0; uniqueExecutor.ReleaseTo(executor); return ACLNN_SUCCESS;
}
```

- **针对发现**：① 列 GetWorkspaceSize 全部输入张量（含 inplace/可选），逐个对表 `IsEmpty()`（§9 例 :496 selfRef/mask、:503 source）；② 覆盖数 < 输入数 ⇒ 子型①；③ grep `IsEmpty\s*\(` 与输入声明数比对。
- **复现锚**：`target=(4,8), mask=(4,1) 或 (4,8), mask_true=0, source=(0,8)`；PyTorch CPU/CUDA 全 PASS 而 910b（A2）失败。
- **实证**：#5149 / PR #9197（§9 例 :496/:503/:505-507）。

### 案例 2｜元素数不足（非恰为 0）致越界 / NaN —— 2026-04-29（masked_scatter，A3）

- **触发**：`updates`/`source` 元素数 >0 但小于 mask 中 true 的数量；A3。
- **根因（路径）**：kernel `Init()` 用由 mask/shape 推导的元素数（非该 tensor 自身元素数）`SetGlobalBuffer` → 注册长度 > 实际字节 → 读出分配外地址（越界/NaN）；子型④。
- **修复范式（✅，示意）**：`xGm.SetGlobalBuffer((__gm__ T*)src, src->GetShapeSize());`（长度取自身元素数），0/不足时早退。
- **针对发现**：① 核 `SetGlobalBuffer(tensor, 长度)` 长度来源；② 核 docs 元素数约束（§9 例 docs :98）与判空自洽。
- **复现锚**：`mask_true=N` 而 `source` 元素数 < N，A3 跑 mssanitizer。
- **实证**：卡内 2026-04-29 记录（同源另一侧，无 issue 号）。

### 案例 3｜判空仅跳过 Contiguous 的「半程保护」—— masked_scatter（子型②）

- **触发**：`source` 空，实现以「只跳过连续化」代替早退。
- **根因（路径）**：§9 例 :531 `if (source->IsEmpty()) sourceContiguous = source;` 只跳过 `l0op::Contiguous`，0 元素 buffer 仍透传给算子构建。
- **修复范式（✅，示意）**：空输入直接早退完整（置 `workspaceSize=0` + `ReleaseTo` + `return SUCCESS`）。
- **针对发现**：① 全部 `IsEmpty()` 分支是否早退完整（缺 `ReleaseTo`/`return` 即命中）；② 空 tensor 是否仍进 `l0op::Contiguous`/`l0op::Xxx`。
- **复现锚**：`source=(0,8)` 且 `mask` 全 false，核对早退前是否仍构建。
- **实证**：§9 例 :531（形态样板）。**本仓实测锚（2026-11-05 核验）**：`index/masked_scatter/op_api/aclnn_masked_scatter.cpp:409` `if (!source->IsEmpty()) { sourceProcessed = l0op::Contiguous(source, executor); ... }` @ops-nn HEAD `b27fda2`——**修复后形态**：空 source 时整段连续化被跳过，`sourceProcessed` 保持原指针。**判据要点**：这只是「跳过连续化」，并未早退整个算子——0 元素 buffer 仍可能透传给算子构建，须按子型②继续核「是否早退完整（`ReleaseTo` + `return SUCCESS`）」。对应的现网单为 ops-nn PR #9197 / issue #5149（与本章案例 4、5 同源）。

### 案例 4｜平台分支不对称：修复只 gate arch22 —— #5149 / PR #9197（950 侧）

- **触发**：同案例 1 输入，平台为 950（regbase / arch35）。
- **根因（路径）**：修复行 `!IsRegbase() && source->IsEmpty()` 仅 gate arch22（§9 例 :503）；950 靠 `ProcessBroadcast`（:380）内 `if (!source->IsEmpty())`（:403）自有保护——两侧须分别立证。
- **修复范式（✅，示意）**：两侧各自有空 tensor 策略；判空平台条件须覆盖真正无保护一侧。
- **针对发现**：① 双侧分核空 tensor 策略；② 核 `ProcessBroadcast` 是否自带保护；③ 空用例双平台同跑。
- **复现锚**：案例 1 输入在 950 侧跑，核对是否走 regbase 保护路径。
- **实证**：#5149 / PR #9197（§9 例 :503 / :380、:403）。

### 案例 5｜修复未覆盖非 inplace 变体 + 未沉淀 ST 用例 —— #5149 / PR #9197（子型⑥）

- **触发**：调用非 inplace 的 `aclnnMaskedScatter`。
- **根因（路径）**：修复仅作用 inplace 变体，非 inplace `aclnnMaskedScatter` 未同步补判空；200 条 ST 用例无 0 维 shape，未沉淀用例。
- **修复范式（✅，示意）**：同目录全部变体统一补 `source` 判空；新增 0 维 shape ST 用例。
- **针对发现**：① 列同目录 `aclnn_*.cpp` 变体比对判空差；② 列 `tests/` shape 检索 0 维。
- **复现锚**：对非 inplace 变体跑案例 1 输入。
- **实证**：#5149 / PR #9197。

### 语料基线与深挖起手式

- 四仓基线（2026-09-14，1040 接口）：PARTIAL 141 / HIGH 461 / kernel 感知 88 / 全覆盖 328；ops-transformer 全覆盖 8/250，ops-math 182 HIGH。
- 起手：`python3 scripts/scan_fp.py --only FP-B06 --format json <文件>`（四仓基线出自一次性审计脚本，该脚本**未收录本仓**、不能直接当 CI 门禁）。


## 15. 实证加深（v5.4）：真实修复锚 · 反向排除项

> 取证基线：ops-nn `@b27fda2`（2026-11-05 本地核验）。仓为浅克隆，commit 列记当前 master HEAD。

### 15.1 真实锚（修复后形态）

| 案例 / issue | 真实锚（文件:行号 @commit） | 要点 |
|---|---|---|
| #9197 `aclnnMaskedScatter` 空 source 仅跳过连续化（现网 26-10；issue #5149 / PR #9197） | `index/masked_scatter/op_api/aclnn_masked_scatter.cpp:409` @b27fda2 | `if (!source->IsEmpty()) { sourceProcessed = l0op::Contiguous(source, executor); CHECK_RET(...); }`——**修复后形态**：空 source 时整段连续化被跳过。**判据要点**：这只是「跳过连续化」，**并未早退整个算子**——0 元素 buffer 仍可能透传给算子构建，须按子型②继续核「早退是否完整（置 `workspaceSize=0` + `ReleaseTo` + `return SUCCESS`）」。同文件 `:386` `ProcessBroadcast` 是另一条受保护路径。 |

### 15.2 反向排除项

| 反向排除项 | 所需负向证据 |
|---|---|
| 空态在该路径已被完整早退 | 给出 `ReleaseTo(executor)` + `return ACLNN_SUCCESS` 同在空态分支内的 `[文件]:[行号]`；只跳过 `Contiguous` 不算 |
| 空态输入本身非法（应被拒绝而非早退） | 给出文档或首段校验明确拒绝 0 元素的 `[文件]:[行号]`，且与 CPU/GPU 参考行为一致 |
| 平台分支两侧都有保护 | 给出 arch22 与 arch35/regbase **各自**的空态处理行 `[文件]:[行号]`；只 gate 一侧不算 |
| 非 inplace 变体同样覆盖 | 给出非 inplace 入口的空态分支 `[文件]:[行号]`；同族入口必须逐入口核 |

## 16. 判据层（L2/L3）：出用例与判读前必读 <!-- BEGIN DETECT-SECTION (generated by scripts/sync_detect_section.py; do not edit) -->

> 生成物，勿手改（C42 校验）。完整判据见 [references/detect-l2-l3.md](references/detect-l2-l3.md)。

- **L2**：轴 shape 维度/入参合法性｜观测 golden-canary/error-code｜至少 4 例
- **L3 `golden-canary`**：K128(假 PASS)随机/索引类接口的输出整块未写只能靠独立金丝雀发现，分布判据会假 PASS；K427(假阳)mssanitizer 对 aclnn 直调缓冲的 OOB 判定是 shadow 假象，须哨兵+块对齐阴性对照定案
- **L3 `error-code`**：K583(假 FAIL)inplace 接口「广播变宽」是 161002 正确拒绝，纯 doc 基线会成片假 FAIL；K866(漏检)dtype 变异只改张量不改 aclScalar → 结构上抓不到标量 dtype 不校验

> 判 FAIL 先排「假 FAIL」、判 PASS 先排「假 PASS/假绿」。**不查 L3 就出结论 = 报告作废。** <!-- END DETECT-SECTION -->
