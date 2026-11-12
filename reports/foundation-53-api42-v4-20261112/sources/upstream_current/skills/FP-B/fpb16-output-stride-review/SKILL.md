---
name: "fpb16-output-stride-review"
description: "对指定 aclnn 接口做 FP-B16 专项检视：核查出参张量的 stride 是否真正参与了寻址，识别「非连续 view 被按连续布局回写」导致的前 numel 个正确、其后全旧值的静默错值缺陷，产出带物理内存 dump 证据链的 Bug 卡与报告。当用户遇到出参传非连续视图时一半元素为旧值、返回码却是 0、跨版本逐位一致时使用。"
---

# FP-B16 aclnn 接口检视（fpb16-output-stride-review）

对指定 aclnn 接口做 FP-B16 专项检视：核查**出参 stride 是否参与寻址**，命中即出 Bug 卡，输出报告。

## 0. 与相邻模式的边界

| 相邻模式 | 分工 |
|---|---|
| [FP-B12](../fpb12-early-exit-review/SKILL.md)（早退不写非空输出） | B12-2 是「返回 SUCCESS 但输出未写全」的**结果面**；本模式给出其中一类**确定根因**——出参 stride 未参与寻址。判据分界：**做了物理 dump 且「前 numel 个 == 连续基线」→ 归本条**；仅观察到「未写全」而未定位到着落位置 → 暂记 B12-2，补 dump 后再归 |
| [FP-A22](../../FP-A/fpa22-dtype-dispatch-review/SKILL.md)（dtype 分派错配，子型③输出覆盖不全） | A22 的未写**随 dtype 变化**（换个兄弟 dtype 就对）；本条的未写**与 dtype 无关**，只随出参 stride 变化。控制变量不同即可一刀分开 |
| [FP-B07](../fpb07-aclnn-review/SKILL.md)（索引/偏移计算错误致越界） | B07 **越界**（`max_offset >= numel(storage)`，memcheck 有告警、可能 aic error）；本条**严格不越界**（`max_offset < numel(storage)` 已自检），memcheck 全绿、无任何告警。这是最快的判别式：**memcheck 干净 + 结果错 = 优先怀疑本条** |
| [FP-B05](../fpb05-coverage-review/SKILL.md)（入参校验覆盖度参差） | B05 只管**入参**且限定 `op_api/*.cpp`；本条的 25 个接口**全都没有 `op_api` 目录**，不适用 |
| [FP-B11](../fpb11-validation-review/SKILL.md)（第一段参数契约校验缺失） | B11 的对象是 shape/rank/attr **取值**非法被放行；本条对象是 **stride 布局**未被使用。前者靠"该报 161002 没报"，后者靠"算对了但写错位置" |
| [FP-B04](../fpb04-aclnn-review/SKILL.md)（空指针校验缺失） | B04 里那条 `CheckDisContinuousStride` 案例是**该检查自身缺 `return`**（防御形同虚设）；本条是**根本没有这道检查** |
| [FP-E01](../../FP-E/fpe01-golden-review/SKILL.md)（golden/UT 失配） | 只断言返回码、或只测连续出参的 UT 会把本条长期判 PASS |

## 1. FP-B16 模式卡摘要（检视依据，源自库内 `patterns/FP-B/FP-B16.md`）

- **编号 / 名称**：FP-B16 出参 stride 未参与寻址（非连续 view 被按连续布局回写）｜ **类别**：功能/兼容 ｜ **风险**：高（S3×O3=9）｜ **状态**：活跃
- **适用声明头**（照抄卡片）：仓 ops-nn ｜ 侧别 Host ｜ 载体 aclnn源码,Host源码 ｜ 触发 AutoContiguous ｜ 默认启用 true
- **故障机理**：kernel 按"出参是行主序连续"的假设，把**完全正确的 `view.numel()` 个结果**依次写到 `storage` 基址起的连续位置；`aclCreateTensor(..., strides, storageShape)` 里的 `strides`/`storageShape` 在整条回写链路上被丢弃（既无 `IsContiguous()` 拦一道，也无 ViewCopy 回写视图）。`view` 与 `storage` 之间存在任何空洞时，按 stride 读回就有一半偏移落在未写区。**不越界、不报错、跨版本逐位一致。**
- **触发条件**：出参以带空洞 stride 的合法 view 传入（`max_offset < numel(storage)`），且算子 `ACLNNTYPE` 为 `aclnn`（**无手写 `op_host/op_api/`**，回写走 autogen）。
- **典型表现**：① 出参**恰好一半**（或 `1/stride比`）元素为预填值；② **物理 dump 显示前 `numel(view)` 个与连续基线逐元素相同、其后全旧值**；③ 返回 `0/0`、无告警、A2/9.2.0 与 A3/9.3.0 逐位一致；④ 同算子 in-out 出参非连续时**完全正确**（内部对照）。
- **三个子型**：① 该算对却没算对（资料非连续列 `√`/`x`/`-`）；② 该拒绝却未拒绝（资料标 `×`）；③ 声明了 `AutoContiguous` 却不生效。
- **实证案例**：`ops-nn` 19 issue / 25 接口（全部 open）—— **#8663**（7 接口同族）、**#8674** `AddRmsNormCast`、**#8675** `InplaceAddRmsNorm`、**#8677/#8679/#8680/#8681** `Foreach*ScalarList`、**#8682** `GroupNormSwish`、**#8686/#8687** `SwiGlu` 族、**#8688/#8689** `SituGlu` 族、**#8693** `DequantBias`、**#8698** `DynamicBlockQuant`、**#8699** `SwiGluQuant`、**#8701** `DequantSwigluQuant`、**#8702** `CrossEntropyLoss`、**#8704** `DeepNormGrad`、**#8706** `GroupNormSwishGrad`。
- **关联**：FP-B12、FP-A22、FP-B07、FP-B05、FP-B11、FP-B04、FP-E01、FP-A05。

## 2. 检视输入与算子定位

**输入**：aclnn 接口名或算子目录；可选 ref。
**接口名 → 目录**：去 `aclnn` 前缀 + 驼峰转下划线，如 `aclnnGroupNormSwishGrad` → `group_norm_swish_grad`。
**先判通路**：`grep -n 'ACLNNTYPE' <op>/op_host/CMakeLists.txt`。取值为 `aclnn` → 本条适用；`aclnn_exclude` → **跳过并记理由**（实测该族抽样 15 个全部正常）。

## 3. 取数方式

优先本地克隆；否则走 API（`contents` 列目录、`raw` 取文件，带 `User-Agent`，重试 2 次间隔 5 秒）。本地读时记录 commit 以保证行号可追溯（本轮实测 commit 为 `9b3be291`）。

## 4. 检视清单（每点：查什么 → 何处 → 命中判据）

### ① 通路与 op_api 存在性（前提判定）
- 查什么：`op_host/CMakeLists.txt` 的 `ACLNNTYPE`；`op_host/op_api/` 是否存在。
- 命中判据：`ACLNNTYPE aclnn` **且**无 `op_host/op_api/` ⇒ 回写完全由 autogen 承担，进入后续检查。二者缺一则本条不适用。

### ② 出参 AutoContiguous 声明（子型③）
- 查什么：`op_host/*_def.cpp` 里每个 `Output("...")` 链尾是否 `.AutoContiguous()`。
- 命中判据：**声明了**却实测不生效 ⇒ 子型③（最强的"实现声称支持"证据）。
- 注意：**无声明也可能失效**（`GroupNormSwish` 的 `y`/`mean` 无声明同样失效），故"无声明"不能作为反证。

### ③ 出参路径上的 stride 处理（核心）
- 查什么：`GetStrides` / `GetStorageShape` / `IsContiguous` / `ViewCopy` 出现在**入参**还是**出参**。
- 命中判据：**只在入参出现、出参一处不见** ⇒ 命中。（实测 `cross_entropy_loss` 6 处 `AutoContiguous` 全在 `input`/`target`/`weight`；`deep_norm_grad` 12 处全在入参。）
- 反例排除：出参侧存在显式 ViewCopy 回写 ⇒ 记反证排除，须给 `[文件]:[行号]`。

### ④ 资料口径核对（定子型）
- 查什么：`docs/aclnn*.md` 参数表里每个**出参**的「非连续Tensor」列取值。
- 命中判据：`√` / 张量名（如 `x`，表示跟随该输入）/ `-`（未标注）⇒ 子型①；`×` ⇒ 子型②（期望首段返回 `161002`）。

### ⑤ 物理 dump 定位着落（决定性）
- 查什么：出参 `storage` 前 `numel(view)` 个物理元素 vs 连续基线的 `numel(view)` 个逻辑值。
- 命中判据：**逐元素全等** ⇒ 坐实"值对位置错"，归本条。**不全等** ⇒ 不是本条（可能是"没算"，回 B12-2 或 A22）。

### ⑥ 内部对照（in-out 出参）
- 查什么：同一次调用里另有一个 in-out 出参（`x1Ref` / `var` 等），把它也传非连续。
- 命中判据：in-out **正确**而常规出参**失效** ⇒ 缺陷局限在出参回写这一路，可排除"整个算子不支持非连续"。

## 5. 检视流程

1. **定界**：确认接口、仓、ref；确认 `ACLNNTYPE` 与 `op_api` 存在性。
2. **枚举出参**：从 def 与资料两头列出所有出参及其 dtype/shape 约束。
3. **静态核查**：走清单 ②③④，给出 `[文件]:[行号]`。
4. **构造合法 view**：`stride = {H*2, 2}`、`storage = [B, H*2]`、`view = [B, H]`；**先自检** `max_offset < numel(storage)`，不满足即构造错、不是缺陷。
5. **跑基线**：出参全连续 + 哨兵预填，**基线哨兵必须为 0**；非 0 先查是构造错还是该出参本就不输出（见 §7）。
6. **跑非连续**：一次只改一个出参的 stride。
7. **物理 dump**：前 `numel(view)` 个 vs 基线，逐元素比。
8. **跨版本复跑**：至少两个 CANN 版本 / 两种硬件，逐位比对。
9. **GitCode 查重**：按接口名 + "非连续 / stride / 未写入" 检索。
10. **业务可达性核查**（见第 6 节 B 轴）。
11. **出报告**：标注证据等级。

## 6. 风险定级（S×O）与业务影响评估（B 轴）

- **S**：S4 致命（进程崩溃/挂死/完全无结果）、S3 结果错误（静默错值）、S2 功能受限、S1 资源浪费。本条基准 **S3**（有结果但错，且不越界不崩）。
- **O**：O3 ≥2 条独立实证；O2 1 条；O1 仅静态。
- **风险 = S×O**：≥6 高；3/4 中；1/2 低。FP-B16 基准 S3×O3=9（高）。

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

- **基线哨兵非 0 ≠ 缺陷**：先查两件事——① 构造是否合法（`view.numel() <= numel(storage)`、`max_offset < numel(storage)`）；② 该出参在**当前 attr/mode** 下是否本就该输出。已踩过的两个坑：`DequantSwigluQuant` 在 `quantMode="static"` 下 `scaleOut` 本就不输出；`CrossEntropyLoss` 的 `zloss`/`lseForZloss` 资料明示"当前暂不支持，计算时必须传入但不参与计算"。**这两类基线未写是正常行为。**
- **"一半为 0" ≠ 缺陷**：必须结合数学语义。`GRU` 的 `hnOut` 前 15 个全 0 是**正确**的（`isbias=false`、`hn[t=0] = W·h(-1)` 而 `h(-1)=0`）。
- **出参元素太少时证据不足**：出参 numel < 8 时物理 dump 命中数太少（如 2/3、1/3）不具说服力，**放大中间维（通道 C）而非 batch 维**，可同时兼顾多个小出参（实测 `GroupNormSwishGrad` C=3→8 后由 2/3、1/3 变为 8/8、6/8）。
- **只比"非连续 vs 基线"不够**：必须**检查基线本身是否写满**——`ClippedSwiglu`（#8691）就是基线自身 `out[1]` 整行未写，属另一类缺陷，不归本条。
- **不臆造行号**；**静态推演声明**必写。
- **找不到 ≠ 没有**：未命中只表述为「本轮未发现」，须写明抽样口径与停止点。

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
  - `{def.cpp}:{行号}`：出参 Output 声明（是否带 AutoContiguous）
  - `{op_host}/` 无 `op_api/` 目录（autogen 回写）
  - 对照样板（反证）：{仓内正确做法}
- **FP-B16 模式编号与子型**：FP-B16 / B16-{1|2|3}
- **S×O 风险定级**：S3×O3=9，高
- **证据等级**：{静态可证 / 需实测确认}｜{一句话理由}
- **业务影响评估（B 轴）**：可达性 B{3|2|1}（一句话判据）｜ 业务影响：静默精度损失｜ 证据：{...}｜ 处置建议：{...}
- **故障机理推导链**：非连续出参 → stride 未参与寻址 → 结果连续写 storage 基址 → 按 stride 读回一半落未写区 → 读到旧值
- **物理 dump 证据**：物理[0..N-1] = 与基线相同 N/N；物理[N..M] = 全哨兵
- **复现用例**：view/stride/storage 三要素 + 哨兵值 + 基线对照 + 按 stride 读回对拍
- **建议修复方案**：出参回写走「转连续计算 → ViewCopy 回视图」；或首段返回 161002 拒绝并同步资料
- **测试拦截建议**：出参一律传带空洞 stride 的合法 view + 哨兵预填 + 基线必须为 0
- **Agent 误判记录**：{...}
- **GitCode 查重**：{检索结论}
```

### 检视报告结构

```markdown
# FP-B16 检视报告：{aclnn 接口名}（YYYY-MM-DD）
## 一、执行概览（仓/ref/HEAD、出参数、通路判定、命中 X / 观察项 Y / 反证排除 Z、抽样口径）
## 二、命中明细（Bug 卡，每卡含 B 轴业务影响评估与物理 dump）
## 三、观察项
## 四、反证排除
## 五、实测建议（非连续 view 矩阵 + 物理 dump 方案）
```

> 报告须在「执行概览」标注**证据等级分布（静态可证 X / 需实测确认 Y）**，并在文末单列「Agent 误判记录」小节（无则写「无」）。

## 9. 示例速览：aclnnGroupNormSwishGrad

- **定位**：`ops-nn` → `norm/group_norm_swish_grad/`，`ACLNNTYPE aclnn`，**无 `op_api/`**。
- **检视面提示**：3 个出参（`dxOut`/`dgammaOut`/`dbetaOut`）的 Output 声明是否带 `AutoContiguous`；def 里 9 处 `AutoContiguous` 是否全在入参；资料三个出参的非连续列是否为 `x`（跟随输入）。
- **实测结论**：`dx` 128/256 未写、物理 256/256 命中；`dgamma` 4/8、物理 8/8；`dbeta` 4/8、物理 6/8；A2/A3 逐位一致。
- 最终判定以第 4/5/7 节为准。

## 10. 能力边界与自检

### 能力边界

- **静态可证**：清单 ①②③④ 能在源码内给出「`文件:行号` + 推导链」的部分。
- **需实测确认**：出参是否真的失效、失效比例、物理着落位置——**必须上板**，本条的结论主体是实测而非静态。
- **不覆盖**：`aclnn_exclude` 通路；仓外框架侧行为；kernel 自身第 0 维偏移错（那是 #8691 型基线缺陷，另案）。
- **找不到 ≠ 没有**：按清单未命中只说明「本轮未发现」。

### 自检

```bash
python3 scripts/gen_triage.py --check                          # 分诊表与映射一致
python3 scripts/scan_fp.py --only FP-B16 --format json <目标>   # 本条无签名，仅供定位提示
python3 scripts/verify_lines.py <报告.md> --root <被检仓>        # 行号校验
python3 check_fault_patterns.py                                # 全库守门
```

### 工作量与抽样（v4.0）

- **深度档：深度**——全量核查，不抽样。全部出参逐个过；单模式命中 > 50 处时按文件分片并写明口径。
- **报告必填**：抽样口径 + 停止点记录；未写口径视为未完成。

## 11. 子型对照、量化基线与探针矩阵

### 子型对照

| # | 子型 / 检查面 | 检视落点 | 命中判据 |
|---|---|---|---|
| B16-1 | 该算对却没算对 | 资料非连续列 `√` / `x` / `-` | 两段返回 0 但按 stride 读回有未写区 |
| B16-2 | 该拒绝却未拒绝 | 资料非连续列 `×` | 首段应返回 `161002` 实返回 0，且产出错值 |
| B16-3 | 声明 AutoContiguous 却不生效 | `op_host/*_def.cpp` 的 `Output().AutoContiguous()` | 声明存在但实测失效 |

### 量化基线（数字来自卡片实证，引用须注明来源）

- 规模口径：2026-11-12 实测 `ACLNNTYPE aclnn` 族 **69 个接口**，本条命中 **25 个（36%）**；`aclnn_exclude` 族抽样 **15 个全部正常**。
- 典型失效比例：`y1Out` 16/32、`out` 12/24、`yOut` 64/128、`logProbOut` 20/40、`y` 5120/10240 —— **恒为 1/stride比**。
- 跨版本：A2-910B3 + CANN 9.2.0 与 A3 + 9.3.0 **逐位一致**。

### 探针矩阵（最小可执行集）

| 探针 | 构造 | 期望 / 判据 |
|---|---|---|
| 连续基线 | 出参全连续 + 哨兵预填 | 哨兵 **0**；非 0 先查构造与"本就不输出" |
| 末维切片 | `view=[B,H]`、`stride={H*2,2}`、`storage=[B,H*2]` | 按 stride 读回与基线逐元素一致 |
| 中间维空洞 | `view=[8,8,4]`、`stride={64,8,2}`、`storage=[8,8,8]` | 同上；出参数足够多时证据更强 |
| 物理 dump | 直读 storage 前 `numel(view)` 个 | 与基线全等 ⇒ 坐实"值对位置错" |
| in-out 对照 | 同调用里另测一个 in-out 出参 | 正确 ⇒ 排除"整算子不支持非连续" |
| 跨版本 | 两版本/两硬件各跑一次 | 逐位一致 ⇒ 非偶发 |

### 证据锚点

- `norm/add_rms_norm_cast/op_host/add_rms_norm_cast_def.cpp:95-98` —— `Output("...")` 与其 `.AutoContiguous()` **跨行**书写（这也是本条无单行签名的原因）@9b3be291
- `norm/inplace_add_rms_norm/op_host/*_def.cpp:46` —— `Output("rstd")` 带 `.AutoContiguous()` @9b3be291
- `norm/deep_norm_grad/op_host/*_def.cpp:58/63/68/73` —— 4 个出参 `dx`/`dgx`/`dbeta`/`dgamma` @9b3be291
- 上述三个算子 **均无 `op_host/op_api/` 目录**

### 交接边界

| 交给 | 遇到 | 理由 |
|---|---|---|
| [FP-B12](../fpb12-early-exit-review/SKILL.md) | 只观察到"未写全"、未做物理 dump | B12-2 是结果面 |
| [FP-A22](../../FP-A/fpa22-dtype-dispatch-review/SKILL.md) | 未写随 dtype 变化 | A22 是派发表错 |
| [FP-B07](../fpb07-aclnn-review/SKILL.md) | memcheck 有越界告警 | B07 越界，本条不越界 |
| [FP-B11](../fpb11-validation-review/SKILL.md) | 对象是 shape/rank/attr 取值非法 | 契约校验 vs 布局使用 |

### 复核清单（按子型）

- B16-1 出参资料非连续列取值？实测是否按 stride 读回一致？
- B16-2 首段返回码是否应为 `161002`？实测返回什么？
- B16-3 出参 Output 链尾是否 `.AutoContiguous()`？实测是否生效？
- 通用：基线哨兵是否为 0？物理 dump 前 numel 是否全等？

## 12. 已知缺陷案例库：触发条件 / 根因 / 修复范式 / 针对性深挖

> 本节把本型**已确认缺陷**拆到「触发条件 → 根因（具体路径）→ 修复范式 → 针对性发现 → 最小复现锚」。含 `文件:行号` 的引用取自实测 commit `9b3be291`，**不得臆造**。

### 案例 1｜4 个出参全错，且 4/4 都声明了 AutoContiguous 却不生效 —— #8674（aclnnAddRmsNormCast）

- **触发条件**：`y1Out`（FLOAT, `[2,16]`）传 `stride={32,2}`、`storage=[2,32]`；`max_offset=62 < numel(storage)=64`。
- **根因（具体路径）**：`norm/add_rms_norm_cast/op_host/add_rms_norm_cast_def.cpp:95-98` 等 4 处出参 `Output(...)` 链尾均有 `.AutoContiguous()`，但该算子**无 `op_host/op_api/` 目录**，回写由 autogen 承担，出参 stride 未参与寻址 ⇒ 16/32 元素保持预填哨兵 `-777000`。
- **修复范式（✅，示意）**：
```cpp
// ❌ 只声明 AutoContiguous，回写仍按连续布局
this->Output("y1").ParamType(REQUIRED).DataType({DT_FLOAT}).AutoContiguous();
// ✅ 回写路径实际消费 stride：转连续计算后 ViewCopy 回视图
auto contiguous = l0op::Contiguous(y1, executor);
// ... kernel 写 contiguous ...
CHECK_RET(l0op::ViewCopy(contiguous, y1, executor) != nullptr, ACLNN_ERR_INNER_NULLPTR);
```
- **针对性发现（可执行）**：① `ls <op>/op_host/op_api/` 不存在；② `grep -n 'AutoContiguous' op_host/*_def.cpp` 出参出现；③ 实测非连续 16/32 未写；④ 物理 dump 前 32 个与基线 32/32 相同 ⇒ 命中。
- **最小复现锚**：`view=[2,16]`/`stride={32,2}`/`storage=[2,32]`，哨兵 `-777000`，先跑连续基线确认 0/32。
- **实证**：#8674（ops-nn，open），A2/9.2.0 与 A3/9.3.0 逐位一致。

### 案例 2｜in-out 出参正确、常规出参失效的内部对照 —— #8675（aclnnInplaceAddRmsNorm）

- **触发条件**：`rstd`（`[8,1]`）传 `stride={2,2}`、`storage=[8,2]`；`max_offset=14 < 16`。
- **根因（具体路径）**：`norm/inplace_add_rms_norm/op_host/*_def.cpp:46` 的 `Output("rstd")` 带 `.AutoContiguous()` 但不生效；**同一次调用**里 `x1Ref`（同为 in-out 出参）非连续时 **128/128 完全正确**，`rstd` **4/8 未写**。
- **修复范式（✅，示意）**：与案例 1 同；额外要点是**不能只修 in-out 那一路**——in-out 恰好走了另一条已支持 stride 的路径，常规出参没有。
- **针对性发现（可执行）**：① 选一个既有 in-out 出参又有常规出参的算子（`InplaceAddRmsNorm`、`ScatterList` 都符合）；② 两者都传非连续；③ **in-out 对而常规出参错 ⇒ 缺陷局限在常规出参回写**，这条对照能一举排除"整个算子不支持非连续"。
- **最小复现锚**：`rstd` 放大 B 到 8 使观测窗口从 2 增至 8；哨兵 `-777000`。
- **实证**：#8675（ops-nn，open）。

### 案例 3｜声明了 AutoContiguous 但资料标 ×，资料与实现互相矛盾 —— #8677（aclnnForeachMinimumScalarList）

- **触发条件**：TensorList 出参 `out[0]`（FLOAT, `[4,6]`）传 `stride={12,2}`、`storage=[4,12]`；`max_offset=22 < 24`。
- **根因（具体路径）**：`foreach/foreach_minimum_scalar_list/op_host/*_def.cpp` 的 `Output("y")` 带 `.AutoContiguous()`，而 `docs/aclnnForeachMinimumScalarList.md` 把 `out` 的非连续列标 **×**（不支持）。实测两段 `0/0`，**12/24 未写**。**资料与代码本身就矛盾**：一边声明支持、一边声明不支持，实现两头都没做到。
- **修复范式（✅，示意）**：二者择一并保持自洽——若要支持，出参补 ViewCopy 并把资料 `×` 改 `√`；若不支持，去掉 `.AutoContiguous()` 并在 `GetWorkspaceSize` 返回 `161002`。
- **针对性发现（可执行）**：① 对 `foreach_*` 全族（`add`/`sub`/`pow`/`minimum`/`maximum` 等 scalar_list 变体）逐个核 def 与资料；② 四者同构，实测均 12/24 未写（#8677/#8679/#8680/#8681）。
- **最小复现锚**：TensorList 单元素出参传带空洞 stride；哨兵 `-777000`。
- **实证**：#8677、#8679、#8680、#8681（ops-nn，均 open）。

### 案例 4｜3 个出参同时失效，且其中只有 1 个声明了 AutoContiguous —— #8682（aclnnGroupNormSwish）

- **触发条件**：`yOut`（`[2,3,4]`）传 `stride={24,8,2}`、`storage=[2,3,8]`；`max_offset=46 < 48`。
- **根因（具体路径）**：`norm/group_norm_swish/op_host/*_def.cpp` 中**仅 `rstd`** 声明了 `.AutoContiguous()`，`y`/`mean` 没有；但三者**实测失效方式一致**（`y` 12/24、`mean` 1/2、`rstd` 1/2）。物理 dump：前 24 个与基线 **24/24 相同**。⇒ **问题不止于声明，而是出参回写路径整体未处理非连续视图**。
- **修复范式（✅，示意）**：修复必须以**出参回写路径**为单位，而非逐个补 `.AutoContiguous()` 声明——补声明对 `y`/`mean` 无效。
- **针对性发现（可执行）**：① 找"部分出参有声明、部分没有"的算子；② 两者都测；③ **若失效方式相同 ⇒ 根因在回写路径共性处**，这是本条最有价值的判据推论。
- **最小复现锚**：`view=[2,3,4]`/`stride={24,8,2}`；`mean`/`rstd` 用 `[2,1]`/`stride={2,2}`/`storage=[2,2]`。
- **实证**：#8682（ops-nn，open）。

### 案例 5｜4 个出参全错、各一半未写的反向算子 —— #8704（aclnnDeepNormGrad）

- **触发条件**：`dxOut`/`dgxOut`（`[8,1,4]`）传 `stride={8,8,2}`、`storage=[8,1,8]`；`dbetaOut`/`dgammaOut`（`[4]`）传 `stride={2}`、`storage=[8]`。
- **根因（具体路径）**：`norm/deep_norm_grad/op_host/deep_norm_grad_def.cpp:58/63/68/73` 的 4 个出参 `dx`/`dgx`/`dbeta`/`dgamma`；def 里 **12 处 `.AutoContiguous()` 全在入参**，出参一处不见。物理 dump：前 32 个与基线 **32/32 相同**（4 项全命中）。资料 4 个出参非连续列**全标 ×**。
- **修复范式（✅，示意）**：出参回写统一走 ViewCopy；短期内若不支持，应在首段返回 `161002`——**不能让「资料标 ×、实现放行、结果错」三者并存**。
- **针对性发现（可执行）**：① `grep -c AutoContiguous op_host/*_def.cpp` 得到数量，再逐处看作用对象是入参还是出参——**数量多不等于出参有**（本例 12 处全在入参）；② 反向算子多出参，一次调用即可测出 4 条独立证据。
- **最小复现锚**：4 个出参逐个传带空洞 stride，各自预填哨兵；断言按 stride 读回与连续基线一致（或首段返回非 0）。
- **实证**：#8704（ops-nn，open）。

### 语料基线与深挖起手式

- 语料基线：2026-11-12 对 `ops-nn` `ACLNNTYPE aclnn` 族实测 **69 个接口**，本条命中 **25 个（36%）**；`aclnn_exclude` 族抽样 **15 个全部正常**。
- 深挖起手式：
  ```bash
  # ① 圈高危池：aclnn 通路且无手写 op_api
  grep -rlE 'ACLNNTYPE aclnn( |\))' --include=CMakeLists.txt . | while read f; do
      d=$(dirname $(dirname $f)); [ -d "$d/op_host/op_api" ] || echo "$d"; done
  # ② 出参是否声明 AutoContiguous（注意跨行，用 -A 而非单行正则）
  grep -n -A6 'Output(' <op>/op_host/*_def.cpp | grep -E 'Output|AutoContiguous'
  # ③ 出参路径有无 stride 处理（只在入参出现即命中）
  grep -nE 'GetStrides|GetStorageShape|IsContiguous|ViewCopy' <op>/op_host/*_def.cpp
  ```
- **禁止只断言返回码或只测连续出参**——这正是这批缺陷长期未被发现的原因。

## 13. 实证加深：真实锚 · 同根因完整清单 · 反向排除项

> 本节做**取证加深**：用真实代码替换"示意"，补齐清单，给出反向排除项。行号取自 `cann/ops-nn` `@9b3be291`（2026-11-12 实测）。

### 13.1 真实锚（替换"示意"）

| 算子 | 出参 Output 声明锚 @9b3be291 | op_api 存在性 |
|---|---|---|
| `norm/add_rms_norm_cast` | `add_rms_norm_cast_def.cpp:95-98`（`Output("x1")` 起，`.AutoContiguous()` 在 :98；出参组在 :95 之后） | **无** |
| `norm/inplace_add_rms_norm` | `*_def.cpp:46`（`Output("rstd")`） | **无** |
| `norm/deep_norm_grad` | `*_def.cpp:58/63/68/73`（`dx`/`dgx`/`dbeta`/`dgamma`） | **无** |

**关键取证结论**：三个算子的出参回写均无手写 `op_api/`，说明**本条不是个别接口的疏忽，而是 `ACLNNTYPE aclnn` 自动生成通路的范式缺口**。

### 13.2 同根因完整清单（25 接口 / 19 issue @2026-11-12）

| issue | 接口 | 失效比例 | 子型 |
|---|---|---|---|
| #8663 | RmsNorm / GemmaRmsNorm / RmsNormGrad / AddLayerNormGrad / MaskedSoftmaxWithRelPosBias / ExpandIntoJaggedPermute / TopKTopPSample（7 个） | 错位倍率 = stride | B16-1 |
| #8674 | AddRmsNormCast | 16/32（4 出参全错） | B16-3 |
| #8675 | InplaceAddRmsNorm | 4/8 | B16-3 |
| #8677/#8679/#8680/#8681 | Foreach{Minimum,Add,Sub,Pow}ScalarList | 各 12/24 | B16-3（资料标 × ⇒ 兼 B16-2） |
| #8682 | GroupNormSwish | y 12/24（3 出参全错） | B16-1 |
| #8686/#8687 | SwiGlu / SwiGluGrad | 16/32、32/64 | B16-2 |
| #8688/#8689 | SituGlu / SituGluGrad | 16/32、32/64 | B16-2 |
| #8693 | DequantBias | 5120/10240 | B16-2 |
| #8698 | DynamicBlockQuant | y 64/128 + scale 8/16 | B16-2 |
| #8699 | SwiGluQuant | out 24/48 + scaleOut 1/3 | B16-2 |
| #8701 | DequantSwigluQuant | yOut 64/128 + scaleOut 4/8 | B16-1 |
| #8702 | CrossEntropyLoss | logProbOut 20/40 | B16-1（资料 `-` 未标注） |
| #8704 | DeepNormGrad | 4 出参各一半 | B16-2 |
| #8706 | GroupNormSwishGrad | dx 128/256（3 出参全错） | B16-1 |

→ 检视启示：**`norm/` 与 `foreach/`、`quant/` 三个目录都是重灾区**；反向算子（`*Grad`）常一次暴露多个出参。

### 13.3 反向排除项（须附负向证据）

| 排除项 | 排除所需负向证据 |
|---|---|
| 出参回写已消费 stride | 出参侧存在 `GetStrides`/`ViewCopy`/`Contiguous` 的 `[file]:[line]` |
| 该出参在本 attr/mode 下本就不输出 | 资料明文（如"当前暂不支持，计算时必须传入但不参与计算"）或源码分支的 `[file]:[line]` |
| 失效随 dtype 变化而非 stride | 换兄弟 dtype 复测仍错/变对 的实测输出 |
| memcheck 报越界 | 若有越界告警 ⇒ 转 FP-B07，不是本条 |
| 基线本身就没写满（与 stride 无关） | 连续出参基线哨兵非 0 的实测输出（如 #8691 型） |

### 13.4 扫描基线（真实计数）

- `ops-nn` @9b3be291 共 **12363 文件**（`sig_yield.py` 口径）；`ACLNNTYPE aclnn` 非 experimental **57** 个算子目录。
- 本条**无判别性签名**：`\.Output\([^;]{0,200}\.AutoContiguous\(\)` 实测 **0 命中**（真实代码跨行书写）；放宽为单行 `AutoContiguous\(\)` 则 **2085 次**，属超量。故只能人工按 13.2 起手式圈池后实测。

## 14. 判据层（L2/L3）：出用例与判读前必读 <!-- BEGIN DETECT-SECTION (generated by scripts/sync_detect_section.py; do not edit) -->

> 生成物，勿手改（C42 校验）。完整判据见 [references/detect-l2-l3.md](references/detect-l2-l3.md)。

- **L2**：轴 shape 维度/内容取值｜观测 golden-canary｜至少 4 例
- **L3 `golden-canary`**：K128(假 PASS)随机/索引类接口的输出整块未写只能靠独立金丝雀发现，分布判据会假 PASS；K427(假阳)mssanitizer 对 aclnn 直调缓冲的 OOB 判定是 shadow 假象，须哨兵+块对齐阴性对照定案

> 判 FAIL 先排「假 FAIL」、判 PASS 先排「假 PASS/假绿」。**不查 L3 就出结论 = 报告作废。** <!-- END DETECT-SECTION -->
