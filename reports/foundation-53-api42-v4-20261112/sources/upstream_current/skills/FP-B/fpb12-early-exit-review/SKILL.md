---
name: "fpb12-early-exit-review"
description: "对指定 aclnn 接口做 FP-B12 专项检视：核查 IsEmpty() 判空早退路径是否写了非空输出，识别“返回 SUCCESS 但输出为未初始化内存”的静默脏数据缺陷，产出带证据链的 Bug 卡与报告。当用户遇到反向算子梯度为 NaN/随机值、同用例重复执行结果不同、空输入用例通过但数值异常时使用。"
---

# FP-B12 aclnn 接口检视（fpb12-early-exit-review）

对指定 aclnn 接口做 FP-B12 专项检视：核查**判空早退路径是否给非空输出写了值**，命中即出 Bug 卡，输出报告。

## 0. 与相邻模式的边界

| 相邻模式 | 分工 |
|---|---|
| FP-B06（空 tensor 分支缺失） | B06 是"**没有**空 tensor 分支"（崩溃/误拦截）；本模式是"**有**分支但早退体不写输出"，修复落点（加分支 vs 改早退体）与测试形态完全不同 |
| FP-B04（空指针校验） | 对象是 `nullptr`；本模式对象是"张量非空但未被写" |
| FP-A04（静默精度故障） | A04 是"有结果但精度不对"；本模式是"**结果从未被写入**"，属于更底层的数据来源问题，最终常以 A04 形态暴露 |
| FP-A05（脏数据/踩踏） | A05 是缓冲区复用/越界写入造成的脏读；本模式是输出从未被初始化 |
| FP-E01（golden/UT 失配） | 只断言返回码的 UT 会把本缺陷判成 PASS，属测试资产层面的协同问题 |

## 1. FP-B12 模式卡摘要（检视依据，源自库内 `patterns/FP-B/FP-B12.md`）

- **编号 / 名称**：FP-B12 空/退化输入早退路径未写非空输出（SUCCESS + 未初始化输出）｜ **类别**：功能/兼容 ｜ **风险**：高（S3×O3=9）｜ **状态**：活跃
- **适用声明头**（照抄卡片）：仓 All ｜ 侧别 Host ｜ 载体 aclnn源码 ｜ 触发 IsEmpty() ｜ 默认启用 true
- **故障机理**：接口**已有** `IsEmpty()` 判空分支（故不属 FP-B06），但早退体只做 `*workspaceSize = 0; uniqueExecutor.ReleaseTo(executor); return ACLNN_SUCCESS;`，**不写任何输出**。而输出 shape 与输入强绑定，存在"输入为空、输出非空"的合法组合——尤其反向算子：`gradOutput` 为空而正向输入非空时，梯度输出与之同形且非空。调用方拿到预分配的未初始化内存（NaN/随机值），却被当作合法梯度返回。
- **触发条件**：至少一个输入 `numel==0`，且至少一个输出非空；以反向/梯度类算子为主（`*Backward`、`*Grad`）；正向算子输入全空时输出也为空（no-op 成立，不触发）。
- **典型表现**：**返回 `ACLNN_SUCCESS` 但输出为未初始化内存**——重复调用结果不同、换机结果不同、canary/mssanitizer 观察到未写区域；PyTorch 语义下无采样点/无 ROI 的梯度应为 0，NPU 侧返回随机值或 NaN，表现为"loss 偶发 NaN""梯度爆炸"这类难归因现象。
- **实证案例**：ops-cv **#1252** `aclnnGridSampler3DBackward`（`grid`/`gradOutput` 空而 `inputGrad` 非空 → NaN 梯度）；**#1247** `aclnnIm2colBackward`；**#1243** `aclnnThreeInterpolateBackward`（`n==0` 早退不写 `grad_y`）；**#1230** `aclnnRoiPoolingGradWithArgMax`（`roisN==0` 未写 `gradInputRef`）；**#1124** `aclnnUpsampleBilinear2dAABackward`。五条分布在 image 与 objdetect 两目录。
- **关联**：FP-B06、FP-B04、FP-A04、FP-A05、FP-E01。

## 2. 检视输入与算子定位

**输入**：aclnn 接口名（优先 `*Backward`/`*Grad`）或算子目录；可选 ref。
**接口名 → 目录**：去 `aclnn` 前缀 + 驼峰转下划线，如 `aclnnRoiPoolingGradWithArgMax` → `roi_pooling_grad_with_arg_max`。

## 3. 取数方式

优先本地克隆；否则走 API（`contents` 列目录、`raw` 取文件，带 `User-Agent`，重试 2 次间隔 5 秒）。本地读时记录 commit 以保证行号可追溯。

## 4. 检视清单（每点：查什么 → 何处 → 命中判据）

### ① 早退块存在性
- 查什么：`GetWorkspaceSize` 内所有 `IsEmpty()` 分支及其早退体。
- 命中判据：存在"`return ACLNN_SUCCESS` 且块内无任何写输出调用"的路径 → 进入 ② 复核。

### ② 输出非空可能性
- 查什么：该接口的每个 `aclTensor*` 输出，其 shape 是否可能与"为空的输入"解耦（是否与别的非空输入同形）。
- 命中判据：存在"输入空 × 输出非空"的组合 → 命中。

### ③ 逐输出处理完整性
- 查什么：早退前是否遍历所有输出，非空者是否 `l0op::Duplicate/InitOutput/Memset` 清零。
- 命中判据：只处理部分输出，或只 `ReleaseTo` 不写任何输出 → 命中。

### ④ 语义基线
- 查什么：PyTorch 同名反向 API 在该组合下的期望值（无贡献点应为 0）。
- 命中判据：PyTorch 给出 0 而 NPU 为未初始化 → 命中。

### ⑤ 输出 shape 域解耦（B12-3 必做）
- 查什么：每个 `aclTensor*` 输出的 shape 由谁决定——`attr`（如 `outputScale` 恒 `[m]`、`amax` 强制 `[1]`）、非空输入（如 `gradWeight` 同 `weight`）、还是触发早退的那个输入。
- 命中判据：输出 shape **与触发早退的空维无关**且 numel>0，而早退块内找不到该输出变量名 ⇒ 命中 B12-3。
- 反例排除：该输出本身 `IsEmpty()`（主输出为空是正确行为），或早退块内确实写了它。

### ⑥ 平台对称
- 查什么：arch22（非 regbase）与 regbase 两条实现是否都做了输出初始化。
- 命中判据：一侧做了一侧没做 → 命中（且解释"仅某平台复现"）。

## 5. 检视流程

1. **定界**：确认接口与仓/ref。
2. **枚举**：`op_api/aclnn_*.cpp`、`op_host/op_api/`、kernel 入口。
3. **定位早退块**：grep `IsEmpty()`，逐块读上下文。
4. **构造组合**：列出"输入空 × 输出非空"的所有合法组合。
5. **反证排除**：确认 `CheckShape` 是否已把该组合判非法（若已判非法则不成立）、确认输出是否被 kernel 兜底写。
6. **判定**：命中 / 观察项 / 反证排除。
7. **GitCode 查重**：按接口名与"早退/未初始化"检索。
8. **业务可达性核查**（见第 6 节 B 轴）。
9. **出报告**：运行时结论标注「静态推演，需 NPU 实测确认」。

## 6. 风险定级（S×O）与业务影响评估（B 轴）

- **S**：S4 致命（数据静默损坏：梯度全为随机值）、S3 结果错误（部分输出脏）、S2 功能受限、S1 资源浪费。
- **O**：O3 ≥2 条独立实证；O2 1 条；O1 仅静态。
- **风险 = S×O**：≥6 高；3/4 中；1/2 低。FP-B12 基准 S3×O3=9（高）。

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

- **有判空 ≠ 安全**：必须看早退体是否写输出；`*workspaceSize=0` 只是告诉框架"没有 kernel"，不等于输出已定义。
- **区分"输出本来就空"**：若该组合下输出也为空（numel==0），不存在"未写"问题，判反证排除。
- **不臆造行号**；**静态推演声明**必写。
- **拒绝"框架会清"**：调用方预分配内存不在框架职责内，不能作为反证。

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
  - `{文件}:{行号}`：早退块（列出 return 语句）
  - 对照样板（反证）：{文件}:{行号}（同仓正确做法：早退前清零）
- **FP-B12 模式编号**：FP-B12 早退不写非空输出
- **S×O 风险定级**：S3×O3=9，高
- **证据等级**：{静态可证 / 需实测确认}｜{一句话理由}
- **业务影响评估（B 轴）**：可达性 B{3|2|1}（一句话判据）｜ 业务影响：{静默精度损失/任务失败中断/性能退化/仅可观测性}｜ 证据：{调用方/负载/为何不可达}｜ 处置建议：{尽快修/排期修/记录}
- **故障机理推导链**：输入空组合 → 早退分支 → 输出未被写 → 调用方读未初始化内存 → 表现为 NaN/随机梯度
- **触发条件可达性分析**：具体空/非空组合与 shape。静态推演，需 NPU 实测确认
- **复现用例**：两段式调用 + 空输入 shape + 输出 canary 预填 + 断言输出全 0
- **建议修复方案**：早退前对每个非空输出 `l0op::Duplicate(zero)`；或改为不早退、交给 kernel 处理 0 元素
- **测试拦截建议**：空输入 × 输出非空矩阵 + canary 魔数检查；禁止只断言返回码
- **Agent 误判记录**：{被推翻的假设 → 推翻证据 `[文件]:[行号] [代码行]`；无则「无」}
- **GitCode 查重**：{检索结论}
```

### 检视报告结构

```markdown
# FP-B12 检视报告：{aclnn 接口名}（YYYY-MM-DD）
## 一、执行概览（仓/ref/HEAD、早退块数、判定统计：命中 X / 观察项 Y / 反证排除 Z）
## 二、命中明细（Bug 卡，每卡含 B 轴业务影响评估）
## 三、观察项
## 四、反证排除
## 五、实测建议（空输入矩阵 + canary 方案）
```

> 报告须在「执行概览」标注证据等级分布（静态可证 X / 需实测确认 Y），并在文末单列「Agent 误判记录」小节（无则写「无」）。

## 9. 示例速览：aclnnGridSampler3DBackward

- **定位**：`ops-cv` → `image/grid_sampler3_d_grad/op_host/op_api/aclnn_grid_sampler3d_backward.cpp`。
- **检视面提示**：早退条件 `gradOutput->IsEmpty() || input->IsEmpty() || grid->IsEmpty()` 是否为"或"；早退体是否写 `inputGrad`/`gridGrad`；`CheckShape` 是否拦"空/非空交叉"。
- 最终判定以第 4/5/7 节为准。

## 10. 能力边界与自检（v3.8）

### 能力边界

- **静态可证**：清单里能在源码内给出「`文件:行号` + 推导链」的部分，按第 7 节判据出卡。
- **需实测确认**：依赖运行时输入规模、设备行为或环境差异的结论，只能记观察项并附实测用例（证据等级见第 7 节）。
- **不覆盖**：本模式以外的机理（边界见第 0 节）与仓外框架侧行为；`TRIAGE.md` 只负责收敛候选，不构成判定依据。
- **找不到 ≠ 没有**：按清单未命中只说明「本轮未发现」，不得表述为「该算子无此缺陷」；抽样核查须在报告写明抽样口径。

### 自检

```bash
python3 scripts/gen_triage.py --check                          # 分诊表与映射一致
python3 scripts/scan_fp.py --only FP-B12 --format json <目标文件>  # 签名候选（非结论）
python3 scripts/verify_lines.py <报告.md> --root <被检仓>        # 行号校验
python3 check_fault_patterns.py                                # 全库守门
```

### 工作量与抽样（v4.0）

- **深度档：深度**（索引 `depth` 字段）——全量核查，不抽样。全部映射点 / 分支逐条过；单模式命中 > 50 处时按文件分片，并在报告写明分片口径。
- **报告必填**：抽样口径（全量 / 每点前 N 处 / 每类 N 例）+ 停止点记录；未写口径视为未完成。

## 11. 子型对照、量化基线与探针矩阵

### 子型对照

| # | 子型 / 检查面 | 检视落点 | 命中判据 |
|---|---|---|---|
| ① | 单输入为空 | 逐输入 `IsEmpty()` 早退块 | 早退体不写任何输出 |
| ② | 多输入交叉为空 | `gradOutput` 空 × `input` 非空 | 输出非空但未初始化 |
| ③ | 输出非空断言缺失 | UT 只断言返回码 | SUCCESS + 未初始化输出被判 PASS |
| ④ | **B12-3 非空辅助输出** | 早退块对 `*Scale` / `amax` / `rstd` / `gradWeight` / `bagSize` / `maxIndices` 等**形状由属性或非空输入决定**的输出 | 主输出为空（正确），但辅助输出非空且早退块内未出现其变量名 |

### 量化基线（数字来自卡片实证，引用须注明来源）

- ops-cv **5 连发**（2026-09~10，全部 `进行中`）：#1252 / #1247 / #1243 / #1230 / #1124，**全部为反向/梯度算子**——说明是范式缺口而非单点疏忽。
- PyTorch 语义基线：无贡献点的梯度应为 **0**，不是随机值或 NaN。

### 探针矩阵（最小可执行集）

| 探针 | 构造 | 期望 / 判据 |
|---|---|---|
| 逐输入置空 | 对每个输入单独置空（shape 含 0 维） | 返回 0 且非空输出每个元素为 0 |
| canary 预填 | 输出 buffer 预填魔数后运行 | 无残留魔数（说明确实写过） |
| 返回码断言 | 只断言 `ACLNN_SUCCESS` 的用例 | 必须补内容断言，否则天然漏检 |
| 组合矩阵 | 空 × 非空的所有输入组合 | 输出与 PyTorch 对照一致 |

### 证据锚点

- ``image/grid_sampler3_d_grad/op_host/op_api/aclnn_grid_sampler3d_backward.cpp:230-237`` —— grid/gradOutput 空而 inputGrad 非空 → NaN
- `ops-cv #1252` —— GridSampler3DBackward
- `ops-cv #1247` —— Im2colBackward
- `ops-cv #1124` —— UpsampleBilinear2dAABackward

### 交接边界

| 交给 | 遇到 | 理由 |
|---|---|---|
| [FP-B06](../fpb06-aclnn-review/SKILL.md) | 没有判空分支（本条是有分支但不写输出） | 边界见第 0 节 |
| [FP-A04](../../FP-A/fpa04-aclnn-review/SKILL.md) | 有结果但精度不对（本条是结果从未写入） | 边界见第 0 节 |
| [FP-E01](../../FP-E/fpe01-golden-review/SKILL.md) | 只断言返回码的 UT | 边界见第 0 节 |

### 复核清单（按子型）

- ① `IsEmpty()` 早退块是否写入每个非空输出
- ② 判空条件是否逐输入（而非任一为空即早退）
- ③ UT 是否断言输出内容（而非只断言返回码）
- ④ canary 预填魔数后是否有残留（说明未写）
- ⑤ **B12-3**：逐个输出标注 shape 域来源；凡「与触发早退的空维无关且非空」者，早退块内是否出现写它的调用（**不能只看主输出**）

## 12. 已知缺陷案例库：触发条件 / 根因 / 修复范式 / 针对性深挖（v5.1）

> 本节把本型**已确认缺陷**拆到「触发条件 → 根因（具体路径）→ 修复范式（✅ 正确代码）→ 针对性发现步骤 → 最小复现锚」的代码级颗粒度。修复范式为**正确形态示意**；含 `文件:行号` 的引用取自卡片实证，行号以被检仓本地 HEAD 为准，**不得臆造**。

### 案例 1｜`grid`/`gradOutput` 为空而 `inputGrad` 非空，早退不写输出 → NaN 梯度 —— #1252（aclnnGridSampler3DBackward）

- **触发条件**：`grid` 或 `gradOutput` 为 `numel==0`，而 `input`/输出非空。
- **根因（具体路径）**：`image/grid_sampler3_d_grad/op_host/op_api/aclnn_grid_sampler3d_backward.cpp:230-237` 的判空早退体（`gradOutput->IsEmpty() || input->IsEmpty() || grid->IsEmpty()`）只做 `*workspaceSize=0; ReleaseTo(executor); return ACLNN_SUCCESS;`，**从不写 `inputGrad`** → 调用方读到预分配的未初始化内存（NaN/随机值）。
- **修复范式（✅，示意）**：
```cpp
// ❌ 判空早退：只置 workspaceSize 后返回，输出未写
if (grid->IsEmpty()) { *workspaceSize = 0; return ACLNN_SUCCESS; }
// ✅ 早退前对每个非空输出显式清零（grad 语义：无贡献点应为 0）
l0op::Duplicate(zeroTensor, inputGrad, executor);
```
- **针对性发现（可执行）**：① grep `IsEmpty()` 定位所有早退块，逐块检查 `return ACLNN_SUCCESS` 前是否遍历并写每个非 inplace `aclTensor*` 输出；② 该接口输出是否与某个非空输入同形（存在「输入空 × 输出非空」组合）；③ 早退块内无任何写输出调用 ⇒ 命中。
- **最小复现锚**：`grid` 置空、输出 buffer 预填魔数，断言返回 0 且非空输出全 0、无残留魔数。
- **实证**：#1252（ops-cv，进行中）。

### 案例 2｜`n==0` 早退不写 `grad_y` —— #1243（aclnnThreeInterpolateBackward）

- **触发条件**：`n==0`（采样点数为 0），而正向输入非空。
- **根因（具体路径）**：`op_host/op_api/aclnn_three_interpolate_backward.cpp:109-113` 的 `n==0` 早退分支不写 `grad_y` → 未初始化输出被当作合法梯度返回。
- **修复范式（✅，示意）**：早退前对非空 `grad_y` 清零（`l0op::Duplicate`），或不早退、交由 kernel 处理 0 元素。
- **针对性发现（可执行）**：① 核对早退条件是否逐输入（此处以 `n==0` 触发）；② 检查早退体是否写 `grad_y`；③ 未写且 `grad_y` 非空 ⇒ 命中。
- **最小复现锚**：`n=0` 输入 + canary 预填 `grad_y`，断言输出全 0。
- **实证**：#1243（ops-cv，进行中）。

### 案例 3｜`roisN==0` 未写 `gradInputRef` —— #1230（aclnnRoiPoolingGradWithArgMax）

- **触发条件**：`roisN==0`（无 ROI），而 `gradInput` 非空。
- **根因（具体路径）**：`objdetect/roi_pooling_grad_with_arg_max/op_api/aclnn_roi_pooling_grad_with_arg_max.cpp:183-188` 的 `roisN==0` 早退块未写 `gradInputRef`。
- **修复范式（✅，示意）**：早退前对 `gradInputRef` 清零；`CheckShape` 不能把「空 ROI × 非空 gradInput」判合法放行后又不产出输出。
- **针对性发现（可执行）**：① grep `IsEmpty()`/`roisN` 早退；② 确认输出 `gradInputRef` 是否与别的非空输入同形；③ 早退不写 ⇒ 命中。
- **最小复现锚**：`roisN=0` + 预填魔数，断言 `gradInputRef` 全 0。
- **实证**：#1230（ops-cv，进行中）。

### 案例 4｜同范式跨目录复现（image / objdetect），非单点疏忽 —— #1247（Im2colBackward）、#1124（UpsampleBilinear2dAABackward）

- **触发条件**：反向算子任一输入 `numel==0` 而输出非空。
- **根因（具体路径）**：`image/col2im/op_api/aclnn_im2col_backward.cpp:245-250`（#1247）与 `op_host/op_api/aclnn_upsample_bilinear2d_aa_backward.cpp:204-208`（#1124）同属「有判空分支但早退体不写输出」的**同一范式**——五条 issue 分布在 image 与 objdetect 两个目录，说明是范式缺口而非单点缺失。
- **修复范式（✅，示意）**：统一在早退前对每个非空输出清零（可抽公共 `InitEmptyGradOutputs` 辅助函数逐输出遍历）；两条平台实现（arch22 非 regbase 与 regbase）共用同一逻辑，避免一侧做一侧没做导致「仅某平台复现」。
- **针对性发现（可执行）**：① 对每个 `*Backward`/`*Grad` 逐输入置空，检查早退块写输出的覆盖度；② 反证：该组合下输出也为空（`numel==0`）时不存在「未写」，判反证排除。
- **最小复现锚**：空输入 × 输出非空矩阵 + canary 魔数残留检查。
- **实证**：#1247、#1124（ops-cv，进行中）。

### 案例 5｜主输出为空是对的，受害的是非空辅助输出 —— B12-3（2026-11-06 四连发）

- **触发条件**：早退由「主输入 / 主输出为空」触发，而**至少一个辅助输出的 shape 由属性或非空输入决定**、numel>0。典型：`n==0` / `batch==0` / 空 `x` / 空 `offsets`。
- **根因（具体路径）**：早退体只处理了主输出（或主输出本来就该为空、什么都不用写），辅助输出被整块跳过。四例：`aclnnEmbeddingBag` 的 `bagSize`/`maxIndices`（形状由 `offsets`+attr 决定，#8239）、`aclnnGroupedMatmulSwigluQuantV2` 的 `outputScale`（恒 `[m]`，#7164）、`aclnnPreluBackward` 的 `gradWeight`（形状 == weight，#8246）、`aclnnQuantMax` 的 `amax`（强制 `[1]`，#8249）。
- **修复范式（✅，示意）**：早退块内**按输出逐个判空**，非空者写 0——主输出为空不是跳过其余输出的理由：
```cpp
// ❌ 只照看主输出（output 空 → 什么都不写），辅助输出 outputScale 被跳过
if (output->IsEmpty()) { *workspaceSize = 0; return ACLNN_SUCCESS; }
// ✅ 逐个输出判空，非空者清零（辅助输出与触发早退的空维无关）
if (output->IsEmpty()) {
    if (!outputScale->IsEmpty()) {
        auto fill = GetOutTensorWithValueZero(outputScale, uniqueExecutor.get());
        CHECK_RET(l0op::ViewCopy(fill, outputScale, uniqueExecutor.get()) != nullptr, ACLNN_ERR_INNER_NULLPTR);
    }
    *workspaceSize = 0; uniqueExecutor.ReleaseTo(executor); return ACLNN_SUCCESS;
}
```
- **针对性发现（可执行）**：① 先给每个输出标 shape 域来源（attr / 非空输入 / 触发早退的输入）；② 挑出「与空维无关且非空」者；③ 在早退块文本内检索其变量名，找不到写调用 ⇒ 命中；④ 反证：该输出在早退条件下本身也 `IsEmpty()`。
- **最小复现锚**：把触发早退的维度置 0，**所有输出 buffer 逐个预填不同魔数**，跑后逐输出检查残留——只查主输出正是本子型长期漏检的原因。
- **实证**：ops-nn #8239（`bagSize`/`maxIndices`）、ops-transformer #7164（`outputScale`，基线 256/256 写、变异 0/256）、ops-nn #8246（`gradWeight`，基线 8/8 写、变异 0/8）、ops-nn #8249（`amax`，A5 双 device + 910C 三路复核）。

### 语料基线与深挖起手式

- 语料基线：ops-cv **5 连发**（2026-09~10，全部 `进行中`）：#1252 / #1247 / #1243 / #1230 / #1124，**全部为反向/梯度算子**；PyTorch 语义基线：无贡献点的梯度应为 **0**，不是随机值或 NaN。
- 深挖起手式：`python3 scripts/scan_fp.py --only FP-B12 --format json <目标文件>` —— 扫描「函数体内含 `IsEmpty()` 且其后 `return ACLNN_SUCCESS` 的早退块」×「签名存在非 inplace `aclTensor*` 输出」×「早退块内无 `Duplicate|InitOutput|Memset|l0op::` 写输出调用」，再核对 `CheckShape` 是否已排除「空输入 × 非空输出」。
- **禁止只断言返回码**——这正是 5 条 issue 长期未被发现的原因；建议 ST 中输出 buffer 预填魔数，跑后检查残留魔数比例。

## 13. 实证加深（v5.4）：真实修复锚 · 同根因连发完整清单 · 反向排除项

> 本节在 §12 之上做**取证加深**：① 用被检仓**真实代码**替换案例里的「示意」修复代码；② 补齐同根因连发的**完整清单**；③ 给出**反向排除项**（须附 `[文件]:[行号] [代码行]` 负向证据，口径同 §7 非对称规则）。行号取自公开仓实测 commit（标 `@<sha>`）；与 issue 时点已漂移者逐条注明；**未取到真实来源者一律标「示意」，不配虚构行号**。

### 13.1 真实修复锚（替换「示意」）

**关键取证结论**：本型 5 条 issue 的修复**已全部合入** `cann/ops-cv` `@79680a9`（2026-10-16），且代码内注释直接写明修复意图（非推测）。统一修复范式为「早退块三分支」，真实代码（`image/col2im/op_api/aclnn_im2col_backward.cpp:260-276`）：

```cpp
// An empty gradOutput contributes no values. Explicitly zero a non-empty output instead of leaving it unwritten.
if (gradOutput->IsEmpty()) {
    if (out->IsEmpty()) {                        // ① 输出也空 → 无事可做，空转返回
        *workspaceSize = 0; uniqueExecutor.ReleaseTo(executor); return ACLNN_SUCCESS;
    }
    auto fillOut = GetOutTensorWithValueZero(out, uniqueExecutor.get());   // ② 输出非空 → Duplicate 零张量
    CHECK_RET(fillOut != nullptr, ACLNN_ERR_INNER_NULLPTR);
    auto viewCopyResult = l0op::ViewCopy(fillOut, out, uniqueExecutor.get());  // ③ 零张量写回输出
    CHECK_RET(viewCopyResult != nullptr, ACLNN_ERR_INNER_NULLPTR);
    *workspaceSize = uniqueExecutor->GetWorkspaceSize(); uniqueExecutor.ReleaseTo(executor); return ACLNN_SUCCESS;
}
```

`image/upsample_bilinear2d_aa_backward/op_host/op_api/aclnn_upsample_bilinear2d_aa_backward.cpp:215-232` 同一范式（另一处注释「Empty gradOutput with non-empty out must produce zeros instead of leaving out uninitialized」）——**两处独立实现均自带说明注释，可作范式模板直接复用**。

逐条真实锚（`@79680a9`；案例库原引用为 issue 时点行号，**均已漂移**）：

| issue | 案例库原名（时点锚） | 真实锚 @79680a9 | 差异 |
|---|---|---|---|
| #1252 | `image/grid_sampler3_d_grad/op_host/op_api/aclnn_grid_sampler3d_backward.cpp:230-237` | 同路径 `:244-265`（helper 定义 `:207`） | 已修，且比统一范式多一层掩码条件：`:249-250`（`outputMask[0] && !inputGrad->IsEmpty()` → 写 `inputGrad`）、`:256-257`（`outputMask[1] && !gridGrad` → 写 `gridGrad`） |
| #1247 | `image/im2col_backward/op_host/op_api/…:245-250` | `image/col2im/op_api/aclnn_im2col_backward.cpp:260-276` | **路径已迁移**：`im2col_backward`→`col2im`、`op_host/op_api`→`op_api`，**旧锚已不可达** |
| #1243 | `…/op_host/op_api/aclnn_three_interpolate_backward.cpp:109-113` | `image/three_interpolate_backward/op_host/op_api/aclnn_three_interpolate_backward.cpp:121-133`（helper `:88`，外层判空 `:121`，内层 `:124`，写回 `:129`） | 已修 |
| #1230 | `…/op_api/aclnn_roi_pooling_grad_with_arg_max.cpp:183-188` | `objdetect/roi_pooling_grad_with_arg_max/op_api/aclnn_roi_pooling_grad_with_arg_max.cpp:218-233`（helper `:189`，`gradOutput` 判空 `:218`，`gradInputRef` 判空 `:219`，写回 `:224`） | 已修 |
| #1124 | `…/op_host/op_api/aclnn_upsample_bilinear2d_aa_backward.cpp:204-208` | `image/upsample_bilinear2d_aa_backward/op_host/op_api/aclnn_upsample_bilinear2d_aa_backward.cpp:215-232`（helper `:187`） | 已修 |

**卡片状态漂移提示**：卡片与 §12 仍记这 5 条为「进行中」，但 `@79680a9` 已含修复实现——建议人工复核卡片状态；本 skill 不改卡片元数据。

### 13.2 同根因连发完整清单（ops-cv @79680a9）

**真实计数**：`ops-cv` 全部 `/op_api/` 路径下共 **158 个 .cpp**，其中采用 `GetOutTensorWithValueZero` 零张量写回范式者 **10 处**——**10 处全部属本型**，即「5 条 issue 之外另有 5 处同机理点位」：

| # | 文件（@79680a9） | 归属 |
|---|---|---|
| 1 | `image/grid_sampler3_d_grad/op_host/op_api/aclnn_grid_sampler3d_backward.cpp` | **#1252** |
| 2 | `image/col2im/op_api/aclnn_im2col_backward.cpp` | **#1247** |
| 3 | `image/three_interpolate_backward/op_host/op_api/aclnn_three_interpolate_backward.cpp` | **#1243** |
| 4 | `objdetect/roi_pooling_grad_with_arg_max/op_api/aclnn_roi_pooling_grad_with_arg_max.cpp` | **#1230** |
| 5 | `image/upsample_bilinear2d_aa_backward/op_host/op_api/aclnn_upsample_bilinear2d_aa_backward.cpp` | **#1124** |
| 6 | `image/grid_sampler2_d_grad/op_host/op_api/aclnn_grid_sampler2d_backward.cpp` | 同族（3D 版的 2D 孪生） |
| 7 | `objdetect/roi_align_grad/op_api/aclnn_roi_align_v2_backward.cpp` | 同族 |
| 8 | `experimental/objdetect/roi_align_grad/op_host/op_api/aclnn_roi_align_v2_backward.cpp` | 同族（experimental 副本，**须单独核**） |
| 9 | `objdetect/roi_align/op_api/aclnn_roi_align.cpp` | 同族（正算子入口） |
| 10 | `objdetect/roi_align/op_api/aclnn_roi_align_v2.cpp` | 同族（正算子入口） |

→ 检视启示：高发面是 **`*Backward`/`*Grad` 反向算子的 `IsEmpty()` 早退块**，但**正算子入口与 `experimental/` 副本同样复用该范式**，查全清单时不得只扫 `Backward` 目录；第 8 项目前**未与主副本同步**，应优先核。

### 13.3 反向排除项（须附负向证据）

按 §7 非对称规则，宣称「不属本型」须给出 `[文件]:[行号] [代码行]`：

| 排除项 | 排除所需负向证据 |
|---|---|
| 早退块已写输出 | 给出早退块内写该输出的 `[file]:[line]`：`l0op::ViewCopy` / `GetOutTensorWithValueZero` / `Duplicate` / `InitOutput` 之一 |
| 输出为可选/不参与语义 | proto 或 def 中该输出的 `optional=true` 声明行 |
| 空输入语义即「输出保持未写」 | 接口头注释或文档中对空输入 → 输出语义的显式声明行（如「undefined」） |
| 早退发生在 kernel 下发之后 | 该 `return` 位于 `ADD_TO_LAUNCHER_LIST_AICORE`/launcher 调用之后的 `[file]:[line]` |

### 13.4 扫描基线（真实计数 @79680a9）

- `ops-cv` `/op_api/` **158 个 .cpp** 中 `GetOutTensorWithValueZero` **10 处**（本型写回范式，见 13.2）——可作为「已修复」进度对照。
- 判据签名（`IsEmpty()` 后 `return ACLNN_SUCCESS` 且无写回）在 `ops-cv` 需逐处人工确认：`IsEmpty()` 单独出现 ≥ **9 处**属正常防御，不得直接判缺陷。

## 14. 判据层（L2/L3）：出用例与判读前必读 <!-- BEGIN DETECT-SECTION (generated by scripts/sync_detect_section.py; do not edit) -->

> 生成物，勿手改（C42 校验）。完整判据见 [references/detect-l2-l3.md](references/detect-l2-l3.md)。

- **L2**：轴 shape 维度/内容取值｜观测 golden-canary｜至少 4 例
- **L3 `golden-canary`**：K128(假 PASS)随机/索引类接口的输出整块未写只能靠独立金丝雀发现，分布判据会假 PASS；K427(假阳)mssanitizer 对 aclnn 直调缓冲的 OOB 判定是 shadow 假象，须哨兵+块对齐阴性对照定案

> 判 FAIL 先排「假 FAIL」、判 PASS 先排「假 PASS/假绿」。**不查 L3 就出结论 = 报告作废。** <!-- END DETECT-SECTION -->
