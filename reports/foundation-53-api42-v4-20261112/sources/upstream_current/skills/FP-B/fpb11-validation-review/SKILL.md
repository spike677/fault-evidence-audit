---
name: "fpb11-validation-review"
description: "对指定 aclnn 接口/算子做 FP-B11 专项检视：按六类参数契约（rank/长度/值域/有限性/dtype 组合/前后段一致性）核查第一段接口与 InferShape，判定非法输入是否被放行，产出带证据链的 Bug 卡与报告。当用户要求排查非法 shape/rank/attr 被接受、561002 内部错误码掩盖参数错误、InferShape 与 tiling 结论不一致时使用。"
---

# FP-B11 aclnn 接口检视（fpb11-validation-review）

对指定 aclnn 接口或算子做 FP-B11 专项检视：核查**第一段接口（`aclnnXxxGetWorkspaceSize`）与图模式 `InferShape` 是否把非法参数拦在门口**，命中即出 Bug 卡，输出报告。

## 0. 与相邻模式的边界

| 相邻模式 | 分工 |
|---|---|
| FP-B04（必选入参空指针） | 对象是 `nullptr` 指针本体的判空缺失；本模式对象是**参数值非法**（指针非空但值不合法） |
| FP-B05（入参校验覆盖度参差） | 讲的是**校验骨架的文件级参差**（有的文件有 `CheckNotNull`/`CheckParams`、有的没有），风险低；本模式是**语义校验缺失**，落点在 InferShape/tiling，后果是非法 shape 流入或 coredump |
| FP-B06（空 tensor 分支缺失） | 空 tensor（numel==0）是**语义可能合法**的形态；本模式处理的是**非法**形态（含 0 维之外的负维、超长列表、非有限值） |
| FP-B09（动态 shape 标签） | 哨兵值（-2/-1）被当真实维度，是本模式的一个特例来源；哨兵语义本身的问题归 B09 |
| FP-B13（host 侧窄化/溢出） | 属性/维度在 host 被 `int32` 截断属 B13；本模式看的是"有没有校验"，B13 看的是"数值承载够不够" |
| FP-F03（文档与实现不一致） | 文档写了约束、代码没做 → 双向命中：资料缺陷记 F03，校验缺失记本条 |

## 1. FP-B11 模式卡摘要（检视依据，源自库内 `patterns/FP-B/FP-B11.md`）

- **编号 / 名称**：FP-B11 第一段接口/InferShape 参数契约校验缺失（非法 shape/rank/attr 放行）｜ **类别**：功能/兼容 ｜ **风险**：高（S3×O3=9）｜ **状态**：活跃
- **适用声明头**（照抄卡片）：仓 All ｜ 侧别 Host ｜ 载体 aclnn源码,Tiling源码 ｜ 触发 InferShape|CheckShape|GetDimNum|IsFinite|GetAttrPointer ｜ 默认启用 true
- **故障机理**：校验只覆盖"**形状之间的一致性**"（如 `grid[4]==3`、`inputC==gradOutputC`），不覆盖"**单个参数自身的合法性**"——rank 是否为契约值、`ListInt` 长度是否足/是否超、维度是否为正、属性是否落在 int32 可表达范围、`scale`/`sigma` 是否有限、dtype 组合是否被支持。三种子形态：① **未校验**——完全没有对应检查；② **放行**——有检查但条件写反或范围写宽（只判 `< 0` 不判 `== 0`）；③ **校验对象选错**——检查函数读了错误的张量（`CheckUplimit` 五个维度全取自 `gradOut`，`inputSize`/`gradInput` 从未参与）。叠加因素：同一契约在 op_api、InferShape、tiling 三处各写一遍且**不同步**。
- **触发条件**：rank 与契约不符（rank-0 当 rank-1、ND 当 4-D）；`ListInt` 属性长度不足（只传 1 个 `scales`）或超长（`output_size` 传 3 个）；维度 ≤ 0（零 batch、负 `pooled_h`）；属性超 int32；`scale`/`sigma` 为 NaN/Inf；dtype 组合不在支持矩阵内；可选输入与主输入的 batch/空间尺寸交叉不匹配。
- **典型表现**：**第一段接口返回 `ACLNN_SUCCESS`，到 tiling 才以 561002 失败**，真实原因被内部错误码掩盖；或非法 shape 被发布给下游；或 tiling 越界读取属性数组；或直接 coredump（空 `outputSize` 数组）。对照组特征：同一输入在 PyTorch 侧报错，NPU 侧"第一段通过、第二段挂"。
- **实证案例**：ops-cv **#1017** `aclnnUpsampleNearestExact3dBackward` 上限检查误用 `gradOut`（五个维度全取自 `gradOut`，放过 `inputSize`/`gradInput` 超 `INT32_MAX`）；**#1020** `ResizeLinear` InferShape 放行零 batch 而 arch35 tiling 拒绝；**#1004/#939** tiling 未校验 `output_size` 长度并越界读；**#951** `aclnnRoiAlignV2` `spatialScale` 边界写错并接受非有限值。ops-cv 全量语料中同簇 52 条。
- **关联**：FP-B04、FP-B05、FP-B06、FP-B09、FP-B13、FP-F03、FP-E01。

## 2. 检视输入与算子定位

**输入**：aclnn 接口名（如 `aclnnRoiAlignV2`）或算子目录名；可选 ref（默认 master）。
**接口名 → 算子目录**：去 `aclnn` 前缀 + 驼峰转下划线小写，如 `aclnnUpsampleBilinear2dAA` → `upsample_bilinear2d_aa`。
**仓定位顺序**：`ops-cv`（image/objdetect）→ `ops-nn` → `ops-math` → `ops-transformer`，以 `op_host/*_def.cpp` 的原型与接口签名为准。

```text
{op}/
├── op_host/           # *_infershape.cpp（图模式形状推导）、*_tiling.cpp、op_api/aclnn_*.cpp
├── op_api/            # 部分仓放在算子根目录
├── op_graph/          # *_proto.h（attr 类型与默认值）
└── docs/aclnn*.md     # 约束说明（校验的"合同"来源）
```

## 3. 取数方式

公开网页端点常被拦截，**优先 API 或本地克隆**（均带 `User-Agent`；失败重试 2 次、间隔 5 秒）：

| 用途 | 端点 |
|---|---|
| 目录列表 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/contents/{path}?ref={ref}` |
| 单文件内容 | `GET .../repos/cann/{repo}/raw/{path}?ref={ref}` |
| Issue 查重 | `GET .../repos/cann/{repo}/issues?q={关键词}` |

本地已克隆时直接读文件，行号证据以本地 HEAD 为准并记录 commit。注意 `repos/{repo}` 元信息端点可能返回 401，仓清单改走 `orgs/cann/repos`。

## 4. 检视清单（每点：查什么 → 何处 → 命中判据）

### ① rank 契约
- 查什么：`CheckShape`/InferShape 是否校验每个输入的 rank（含 `rank-0` 标量、图模式未知 rank）。
- 何处：`op_api/aclnn_*.cpp` 的 `CheckShape`、`op_host/*_infershape.cpp`。
- 命中判据：文档或 proto 声明了 rank，代码里无 `GetDimNum()/GetShapeDimNum()` 比较 → 立卡候选。

### ② ListInt/属性长度
- 查什么：`output_size`/`input_size`/`scales`/`pads` 等 `ListInt` 的长度是否校验上限与下限；读取前是否判长度。
- 何处：tiling 与 infershape 的属性读取点。
- 命中判据：`GetAttrPointer`/`GetValue` 直接按下标取而未判 `size()` → 命中（典型后果：越界读或读到下一个属性）。

### ③ 维度值域
- 查什么：维度是否允许 0/负数；`pooled_h/pooled_w`、`spatial_scale`、`iou_threshold` 等标量属性的取值范围。
- 何处：`CheckShape`、tiling 的 `OP_CHECK` 段。
- 命中判据：只判 `< 0` 未判 `== 0`（或反之）、未判 `<= 0` → 命中。

### ④ 有限性
- 查什么：`scale`/`sigma`/`spatial_scale`/`iou_threshold` 是否 `isnan/isinf` 校验。
- 命中判据：属性直接参与除法/取整而无 `std::isfinite` → 命中。

### ⑤ dtype 组合
- 查什么：多输入算子的 dtype 组合（`img` vs `lut_table`、`x` vs `grid`、`grad` vs `grid`）是否逐一比对。
- 命中判据：只检查单个输入 dtype 在支持列表，未检查跨输入一致性 → 命中。

### ⑥ 前后段一致性
- 查什么：`InferShape` 的接受集合 vs `tiling` 的接受集合是否相同；同一非法输入是否一侧放行、一侧拒绝。
- 命中判据：对同一输入两处结论不同 → 命中（无论哪侧"对"，都是契约未统一）。

## 5. 检视流程

1. **定界**：换算算子目录，确认仓与 ref；多仓同名时以 def.cpp 原型确认归属。
2. **枚举**：列出 `op_api/`、`op_host/`（infershape + tiling）、`op_graph/`、`docs/` 全部文件。
3. **提取合同**：从 `docs/aclnn*.md` 的「约束说明」与 `docs/zh/context/*` 抽取出可校验条款清单（rank/长度/值域/有限性/dtype/一致性）。
4. **逐条比对**：合同条款 ↔ 代码校验点，做差集；差集即候选。
5. **反证排除**：确认是否在上游（`l0op::` 公共校验、框架层）已拦；确认属性是否由框架保证合法。
6. **判定**：命中 / 观察项 / 反证排除。
7. **GitCode 查重**：按接口名与症状检索，同机理 issue 存在则不重复立卡，改为引用。
8. **业务可达性核查**（见第 6 节 B 轴）：判 B 等级、定影响类型、给处置建议。
9. **出报告**：按第 8 节模板落盘；运行时结论标注「静态推演，需 NPU 实测确认」。

## 6. 风险定级（S×O）与业务影响评估（B 轴）

- **S**：S4 致命（coredump / 数据静默损坏）、S3 结果错误（非法 shape 被接受并产出错误结果）、S2 功能受限（报错误导、内部错误码掩盖）、S1 资源浪费。
- **O**：O3 = ≥2 条独立实证；O2 = 1 条独立实证；O1 = 仅静态命中。
- **风险 = S×O**：≥6 高；3/4 中；1/2 低。FP-B11 基准 S3×O3=9（高）。

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

- **签名命中 ≠ 成立**：`CheckShape` 存在不等于校验齐全，必须逐条款比对合同；`GetAttrPointer` 命中不等于越界，须确认长度校验在何处。
- **三种判定**：命中（合同条款明确 + 代码缺失 + 反证失败）、观察项（契约本身模糊、上游责任待定）、反证排除（上游已拦/框架保证/该输入本就非法到不了这里）。
- **不臆造行号**：每条证据必须实际读到的 `文件:行号`。
- **拒绝率高不是免责**：若同仓同类 issue 大量被"已拒绝"，先确认契约是否明确，再决定是否立卡。
- **静态推演声明**：无 NPU 环境时所有运行时结论标注「静态推演，需 NPU 实测确认」。

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
  - `{文件}:{行号}`：缺失/写错的校验点
  - 对照样板（反证）：{文件}:{行号}（同仓正确做法或文档条款）
- **FP-B11 模式编号**：FP-B11 参数契约校验缺失（子形态：未校验/放行/对象选错/前后段不一致）
- **S×O 风险定级**：S3×O3=9，高
- **证据等级**：{静态可证 / 需实测确认}｜{一句话理由}
- **业务影响评估（B 轴）**：可达性 B{3|2|1}（一句话判据）｜ 业务影响：{静默精度损失/任务失败中断/性能退化/仅可观测性}｜ 证据：{调用方/负载/为何不可达}｜ 处置建议：{尽快修/排期修/记录}
- **故障机理推导链**：合同条款 → 代码缺失点 → 非法输入进入后的路径 → 后果（561002/coredump/非法 shape）
- **触发条件可达性分析**：具体非法参数组合（rank/长度/值域/有限性/dtype）。静态推演，需 NPU 实测确认
- **复现用例**：aclnn 两段式调用序列 + 全部入参（含非法参数的精确值）+ 期望现象（第一段应返回 161002）
- **建议修复方案**：补校验段落并前置到 `CheckShape`；InferShape 与 tiling 共用同一校验函数
- **测试拦截建议**：非法输入六轴矩阵；断言"第一段返回 161002 而非落到 561002"
- **Agent 误判记录**：{被推翻的假设 → 推翻证据 `[文件]:[行号] [代码行]`；无则「无」}
- **GitCode 查重**：{检索结论}
```

### 检视报告结构

```markdown
# FP-B11 检视报告：{aclnn 接口名}（YYYY-MM-DD）
## 一、执行概览（仓/ref/HEAD、合计条款数、判定统计：命中 X / 观察项 Y / 反证排除 Z）
## 二、命中明细（Bug 卡，每卡含 B 轴业务影响评估）
## 三、观察项（表：# / 条款 / 文件:行号 / 存疑点）
## 四、反证排除（表：条款 / 反证理由 / 上游证据）
## 五、实测建议（非法输入矩阵 + 期望错误码）
```

> 报告须在「执行概览」标注证据等级分布（静态可证 X / 需实测确认 Y），并在文末单列「Agent 误判记录」小节（无则写「无」）。

## 9. 示例速览：aclnnUpsampleNearestExact3dBackward

- **定位**：`ops-cv` → `image/upsample_nearest_exact3d_grad/`（`op_host/op_api/aclnn_upsample_nearest_exact3d_backward.cpp`）。
- **检视面提示**（引导，不预设结论）：文档声明 `gradOut` 与 `gradInput` 每维 ≤ `2^31-1`；`CheckUplimit` 的五个维度是否取自**正确张量**；RegBase 分支是否整体跳过上限检查；`inputSize` 是否参与。
- **实证**：ops-cv #1017 中该函数五个维度全取自 `gradOut`，`inputSize`/`gradInput` 超限被放行。
- 任何一点的最终判定以第 4/5/7 节口径为准，禁止凭"有 CheckShape"直接判定通过。

## 10. 能力边界与自检（v3.8）

### 能力边界

- **静态可证**：清单里能在源码内给出「`文件:行号` + 推导链」的部分，按第 7 节判据出卡。
- **需实测确认**：依赖运行时输入规模、设备行为或环境差异的结论，只能记观察项并附实测用例（证据等级见第 7 节）。
- **不覆盖**：本模式以外的机理（边界见第 0 节）与仓外框架侧行为；`TRIAGE.md` 只负责收敛候选，不构成判定依据。
- **找不到 ≠ 没有**：按清单未命中只说明「本轮未发现」，不得表述为「该算子无此缺陷」；抽样核查须在报告写明抽样口径。

### 自检

```bash
python3 scripts/gen_triage.py --check                          # 分诊表与映射一致
python3 scripts/scan_fp.py --only FP-B11 --format json <目标文件>  # 签名候选（非结论）
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
| ① | 未校验 | `CheckShape`/`InferShape` 无对应条款 | 非法 rank/长度/值域直接放行 |
| ② | 放行 | 条件写反或范围写宽（如只判 `<0` 不判 `==0`） | 边界值穿过校验 |
| ③ | 校验对象选错 | 检查函数读错张量（如五维全取 `gradOut`） | `inputSize`/`gradInput` 从未参与 |
| ④ | 前后段不一致 | `infershape.cpp` 与 `tiling.cpp` 接受集合不同 | 一段放行、另一段拒绝 |

### 量化基线（数字来自卡片实证，引用须注明来源）

- ops-cv 全量语料中 **52 条**同簇（20 已拒绝 / 20 进行中 / 12 已完成）——20 条「已拒绝」说明契约边界尚未固化，属流程层缺口。
- 判定口径：第一段接口应返回 **161002**，落到 561002 即真实原因被内部错误码掩盖。

### 探针矩阵（最小可执行集）

| 探针 | 构造 | 期望 / 判据 |
|---|---|---|
| 六轴矩阵 | rank × ListInt 长度 × 维度符号 × 属性量级 × 有限性 × dtype 组合 | 非法组合在第一段返回 161002 |
| 两段一致性 | 同一输入分别过 InferShape 与 tiling | 两侧结论一致 |
| 对象正确性 | 逐参数核对检查函数实参语义 | 无「读错张量」 |
| 文档对照 | docs 约束说明逐条对代码校验点 | 文档写了代码没做 → 命中 |

### 证据锚点

- ``image/upsample_nearest_exact3d_grad/op_host/op_api/aclnn_upsample_nearest_exact3d_backward.cpp:139-168`` —— 五个维度全取自 gradOut
- `ops-cv #1017` —— 上限检查误用 gradOut
- `ops-cv #1020` —— InferShape 放行零 batch 而 tiling 拒绝
- `ops-cv #1004` —— 未校验 output_size 长度并越界读

### 交接边界

| 交给 | 遇到 | 理由 |
|---|---|---|
| [FP-B05](../fpb05-coverage-review/SKILL.md) | 空校验骨架（文件级参差） | 边界见第 0 节 |
| [FP-B09](../fpb09-dynamic-shape-review/SKILL.md) | 动态 shape 哨兵当真实维度 | 边界见第 0 节 |
| [FP-B13](../fpb13-narrowing-review/SKILL.md) | 属性窄化（数值子型） | 边界见第 0 节 |

### 复核清单（按子型）

- ① `CheckShape`/`InferShape` 是否覆盖 rank / 长度 / 值域 / 有限性四类
- ② 校验条件是否写反或范围写宽（如只判 <0 不判 ==0）
- ③ 检查函数实参是否与形参语义对应（有无读错张量）
- ④ InferShape 与 tiling 对同一输入的接受集合是否一致

## 12. 已知缺陷案例库：触发条件 / 根因 / 修复范式 / 针对性深挖（v5.1）

> 本节把本型**已确认缺陷**拆到「触发条件 → 根因（具体路径）→ 修复范式（✅ 正确代码）→ 针对性发现步骤 → 最小复现锚」的代码级颗粒度。修复范式为**正确形态示意**；含 `文件:行号` 的引用取自卡片实证，行号以被检仓本地 HEAD 为准，**不得臆造**。

### 案例 1｜上限检查读错张量（校验对象选错） —— #1017（aclnnUpsampleNearestExact3dBackward）

- **触发条件**：`inputSize`/`gradInput` 的任一维超 `INT32_MAX`，而 `gradOut` 各维合法。
- **根因（具体路径）**：`image/upsample_nearest_exact3d_grad/op_host/op_api/aclnn_upsample_nearest_exact3d_backward.cpp:139-168` 的 `CheckUplimit` **五个维度全部取自 `gradOut`**，`inputSize`/`gradInput` 从未参与 → 超限输入被放行。
- **修复范式（✅，示意）**：
```cpp
// ❌ CheckUplimit 五个维度全取自 gradOut —— inputSize/gradInput 从未参与
CheckUplimit(gradOut);        // inputSize 超 INT32_MAX 被放行
// ✅ 逐实参张量分别检查，实参与形参语义对应
CheckUplimit(inputSize);      // 每个受约束张量都要过上限检查
CheckUplimit(gradInput);
```
- **针对性发现（可执行）**：① 打开该函数，逐参数核对检查实参是否与形参语义一致；② 确认 `inputSize`/`gradInput` 是否进入任一上限检查；③ 存在「读错张量」且合法语义未被覆盖 ⇒ 命中（子形态③）。
- **最小复现锚**：`inputSize` 单维设 `2^31`、`gradOut` 全合法，断言第一段返回 161002。
- **实证**：#1017（ops-cv）。

### 案例 2｜InferShape 放行、tiling 拒绝（前后段不一致） —— #1020（ResizeLinear）

- **触发条件**：零 batch（shape 首维为 0）。
- **根因（具体路径）**：`image/resize_linear/op_host/resize_linear_infershape.cpp` **放行零 batch**，而 arch35 的 tiling 拒绝 → 同一输入一侧放行、一侧拒绝 → 契约未统一。
- **修复范式（✅，示意）**：InferShape 与 tiling **共用同一校验函数**，对同一非法输入两侧结论一致（`OP_CHECK(dim0 > 0, ...)`）。
- **针对性发现（可执行）**：① 交叉读 `*_infershape.cpp` 与 `*_tiling.cpp` 对同一输入的接受集合；② 出现「A 放行 / B 拒绝」即命中（子形态④，无论哪侧「对」都是契约未统一）。
- **最小复现锚**：零 batch 输入分别过 InferShape 与 tiling，断言两侧结论一致。
- **实证**：#1020（ops-cv）。

### 案例 3｜ListInt 长度未校验 → 越界读属性数组 —— #1004 / #939（UpsampleNearest3d / UpsampleNearest）

- **触发条件**：`output_size` 属性长度不足（如只传 1 个）或为空数组。
- **根因（具体路径）**：`op_host/upsample_nearest3d_tiling.cpp`（#1004）与 UpsampleNearest 同类（#939，卡片记 `:138-139`）在读取属性数组前**未判长度**，直接按下标取 → 越界读（读到相邻属性）；空 `outputSize` 数组曾致 coredump。
- **修复范式（✅，示意）**：
```cpp
// ❌ 直接按下标取，未判长度
h = outputSize[0]; w = outputSize[1];      // size()<2 时越界读
// ✅ 读前校验长度上下限
OP_CHECK(outputSize.size() >= 2, ACLNN_ERR_PARAM_INVALID, "output_size length insufficient");
```
- **针对性发现（可执行）**：① grep `GetAttrPointer`/`GetValue` 后是否跟随 `size()` 判断；② 该属性长度不足/超长即命中（子形态① 未校验）。
- **最小复现锚**：`output_size` 只传 1 个 / 传空数组，断言第一段返回 161002（而非 coredump 或读到相邻属性）。
- **实证**：#1004、#939（ops-cv）。

### 案例 4｜标量属性值域写错 + 接受非有限值 —— #951（aclnnRoiAlignV2）

- **触发条件**：`spatialScale` 取边界值（如 0）或 NaN/Inf。
- **根因（具体路径）**：`objdetect/roi_align/op_host/op_api/aclnn_roi_align_v2.cpp` 的 `spatialScale` **校验边界写错**（如只判 `< 0` 未判 `== 0`）且**未做非有限性检查** → 边界值穿过校验、NaN/Inf 参与除法/取整。
- **修复范式（✅，示意）**：
```cpp
// ❌ 边界写宽且不拒非有限值
if (spatialScale < 0) { return error; }     // ==0 与非有限值穿过
// ✅ 值域 + 有限性一并校验
OP_CHECK(std::isfinite(spatialScale) && spatialScale > 0, ACLNN_ERR_PARAM_INVALID, "...");
```
- **针对性发现（可执行）**：① 核对 `spatial_scale`/`iou_threshold`/`pooled_h` 类标量的 `OP_CHECK` 条件（`<0` vs `<=0`）；② 参与除法/取整的属性是否 `std::isfinite`；③ 缺一即命中（子形态② 放行 / ④ 有限性）。
- **最小复现锚**：`spatialScale` 取 0 与 NaN 两例，断言第一段返回 161002。
- **实证**：#951（ops-cv）。

### 案例 5｜「一维即连续」的豁免假设，辅助输入切片未连续化 —— 26-04（QuantMatmul v4/v5）

- **触发**：`scale` / `offset` / `per-token scale` 这类**辅助输入**由用户以切片方式传入（如 `slice(64)[16:32]`），是非连续 view。主输入都做了连续化，唯独辅助输入因「一维张量天然连续」的假设被跳过。
- **根因**：把「rank == 1」当作「一定连续」。rank-1 张量**同样可以是非连续 view**（stride ≠ 1 或 storage offset ≠ 0）。一旦跳过连续化，下游按 origin shape 读取真实存储，读到的元素位置与预期错位——issue 给出 `origin shape=64`、切片后实际只想取 16 个，n 对不上。
- **修复范式（✅，修复后形态，本仓实测锚）**：

```cpp
// ❌ 按「一维不用连续化」跳过辅助输入
// ✅ 每个辅助输入都过 TensorContiguousProcess（aclnn_quant_matmul_v5.cpp:1003-1019）
CHECK_RET(TensorContiguousProcess(x1, transposeX1, executor), ACLNN_ERR_INNER_NULLPTR);
if (x1Scale != nullptr) {
    if (IsMicroScaling(...)) { CHECK_RET(MxScaleContiguousProcess(x1Scale, executor), ...); }
    else { CHECK_RET(TensorContiguousProcess(x1Scale, tempTransposeValue, executor), ...); }
}
...  // x2Scale / bias / x2Offset / yScale 逐个处理
```

- **针对性发现**：① 列出全部辅助输入（scale / offset / zeroPoint / bias / per-token / per-channel / yScale）；② 逐个确认是否有连续化调用，**不要因为是 rank-1 就豁免**；③ grep `GetDimNum() == 1` 附近的「跳过连续化」分支——这往往是豁免假设的落点；④ **v4 与 v5 要分别查**（本案 v4 漏处理、v5 把「一维」误当无需连续化，是同一缺陷的两个变体）；⑤ 连续化产物必须真正被下游消费，算了不用同样无效。
- **最小复现锚**：对 scale / offset / per-token scale **分别**做「等值非连续 view」单变量实验（同一份数据，只改变 stride 不改数值），contiguous 版作对照；原始切片路径 `64 → [16:32] → [:16]`；断言数值一致且返回码正常。
- **实证**：ops-nn issue #1516（`aclnnQuantMatmul` 未对输入 Tensor 做 contiguous 导致切片输入报错，issue 给出 origin shape=64、n=16 的报错现场）。修复后形态锚：`matmul/quant_batch_matmul_v4/op_host/op_api/aclnn_quant_matmul_v5.cpp:1003-1019`（@ops-nn HEAD `b27fda2`，2026-11-05 本地核验）。**注意**：`bias`、`x2Offset` 无条件走 `TensorContiguousProcess`，而 `x1Scale`/`x2Scale`/`yScale` 还要先判 `IsMicroScaling` 分流到 `MxScaleContiguousProcess`——**两条分支的连续化语义不同，只覆盖其中一条仍是缺陷**。

### 语料基线与深挖起手式

- 语料基线：ops-cv 全量 issue（2026-10-17，1 250 条中 232 条 bug-report）本簇 **52 条**，受理 32 条——20 条「已拒绝」说明契约边界尚未固化，属流程层缺口。
- 深挖起手式：`python3 scripts/scan_fp.py --only FP-B11 --format json <目标文件>` —— 扫描「aclnn 接口 × `CheckShape` 内是否出现 `rank`/`GetDimNum`/`size()`/`IsFinite`/`INT32_MAX`」，只有一致性比较而无上述任一者即 HIGH 候选。

## 13. 实证加深（v5.4）：真实修复锚 · 镜像副本同步缺口 · 反向排除项

> 本节在 §11/§12 之上做**取证加深**：① 用被检仓**真实代码**替换案例里的「示意」修复代码；② 补齐同根因连发的**完整清单**（含**镜像副本漏插修复**核查）；③ 给出**反向排除项**（须附 `[文件]:[行号] [代码行]` 负向证据，口径同 §7 非对称规则）。行号取自公开仓实测 commit（标 `@<sha>`）；与 issue 时点已漂移者逐条注明；**未取到真实来源者一律标「示意」，不配虚构行号**。

### 13.1 真实修复锚（替换「示意」）

本型代表 issue 的修复**已合入** `cann/ops-cv` `@79680a9`（2026-10-16）——修复范式为「**补上契约校验项**」，非重构：

| issue | 真实锚 @79680a9 | 真实修复要点（引真实代码） |
|---|---|---|
| #1017 `UpsampleNearestExact3dBackward` | `image/upsample_nearest_exact3d_grad/op_host/op_api/aclnn_upsample_nearest_exact3d_backward.cpp:139-167` | 签名已扩为 `CheckUplimit(const aclTensor* gradOut, const aclIntArray* inputSize, const aclTensor* gradInput)`；`:150-155` 校 `gradOut` 五维 ≤ `INT32_MAX`，**`:157-167` 新增 `inputSize` 五维校验**（`OP_CHECK(inputN <= INT32_MAX && … inputW <= INT32_MAX, …, return false)`）——这正是时点「五个维度全取自 `gradOut`」缺口的修复 |
| #951 `RoiAlignV2` | `objdetect/roi_align/op_api/aclnn_roi_align_v2.cpp:128-139` | `CheckAttr` 内新增 **`:134` `if (!std::isfinite(spatialScale) \|\| spatialScale <= 0.0f)`**，报错串为 `"spatialScale [%f] should be finite and greater than 0"`——同时补上「非有限值」与「边界比较方向」两处 |
| #1020 `ResizeLinear` InferShape | `image/resize_linear/op_host/resize_linear_infershape.cpp:61-62` | 新增 `OP_CHECK_IF((xShape->GetDim(IDX_L) == 0) \|\| (xShape->GetDim(IDX_L - 1) == 0), OP_LOGE(nodeName, "input size should be greater than 0"), return GRAPH_FAILED)` —— InferShape 侧显式拒绝零维，与 arch35 tiling 对齐 |
| #1004 / #939 `UpsampleNearest3d` tiling | `image/upsample_nearest3d/op_host/upsample_nearest3d_tiling.cpp:87-91` | 新增长度校验：`size_t outputSizeNum = outputSize->GetSize(); if (outputSizeNum != DIM) { OP_LOGE(… "output_size length must be %zu, but got %zu." …); return ge::GRAPH_FAILED; }` —— 堵住 `reinterpret_cast` 后按 `DIM` 越界读 |
| #1516 `aclnnQuantMatmul` 辅助输入切片未连续化 @b27fda2 | `matmul/quant_batch_matmul_v4/op_host/op_api/aclnn_quant_matmul_v5.cpp:1003-1019` | `x1` 无条件 `TensorContiguousProcess`(:1003)；`x1Scale` 先判 `IsMicroScaling` 分流 `MxScaleContiguousProcess`(:1006-1011)、否则 `TensorContiguousProcess`(:1012-1013)；`x2Scale`(:1014-1018)、`bias`(:1016)、`x2Offset`(:1017)、`yScale`(:1019) 逐个处理——**修复后形态**：所有辅助输入都不再享「rank-1 豁免」。注意两路连续化语义不同，只覆盖一路仍是缺陷。 |

**卡片/案例库行号漂移提示**：§11 所引 `:139-168`、`:138-139` 为 issue 时点锚，`@79680a9` 处已分别落到 `:139-167`（且函数签名已扩参）与 `:87-91`（文件已拆出 `_arch35` 变体）；旧锚不可再直接复用。

### 13.2 同根因连发完整清单含「镜像副本同步缺口」核查

**核心取证**：`ops-cv` 存在「**同一算子、两套目录副本**」结构（`image/` 主线 vs `experimental/image/` 副本）。#1004 的修复**只落到主线**，副本仍保留缺陷——这是「**漏插同步代码**」的真实样本：

| 副本 | output_size 长度校验 | 真实锚 @79680a9 |
|---|---|---|
| 主线 `image/upsample_nearest3d/op_host/upsample_nearest3d_tiling.cpp` | **有** | `:87-91` 显式 `GetSize() != DIM` 拦截 |
| 副本 `experimental/image/upsample_nearest3d/op_host/upsample_nearest3d_tiling.cpp` | **无**（仅 `:80` 判空，`:85` 直接 `reinterpret_cast<const int64_t*>(outputSize->GetData())`，`:86-88` 按 `DIM` 索引） | `:76-89` —— **越界读仍在** |

→ **检视纪律（本型最重要的一条）**：查契约校验缺口时**必须做「同名算子 × 全部目录副本」交叉比对**，只核一条通路会漏掉未同步副本。已知需交叉比对的同簇清单（`ops-cv`，粗筛后须逐个人工确认）：`upsample_nearest`、`upsample_nearest3d`、`upsample_nearest3d_grad`、`upsample_nearest_exact2d_grad`、`upsample_bicubic2d(_aa/_grad)`、`upsample_bilinear2d(_aa/_grad)`、`upsample_linear1d`、`upsample_trilinear3d_backward`、`resize_upsample_trilinear`——其中 `*_tiling_arch35.cpp` 与主 `*_tiling.cpp` **常成对出现且校验项不一致**，须逐一比对。

### 13.3 反向排除项（须附负向证据）

按 §7 非对称规则，宣称「校验已完备/不属本型」须给出 `[文件]:[行号] [代码行]`：

| 排除项 | 排除所需负向证据 |
|---|---|
| 该路径已整体跳过校验 | 给出**有意**跳过的真实代码行，如 `image/upsample_nearest_exact3d_grad/…/aclnn_upsample_nearest_exact3d_backward.cpp:141-143` 的 `if (IsRegBase()) { return true; }`——但**须说明 regbase 侧由谁兜底**，否则改为「降级路径校验缺失」候选 |
| 长度/值域已前置校验 | 给出前置 `CheckXXX` 中该校验项的 `[file]:[line]` |
| dtype 组合由平台模板兜底 | 给出模板/能力表中断言该组合的 `[file]:[line]` |
| 非有限值由算子语义允许 | 给出文档或头注释中显式允许 `inf/nan` 的声明行 |

### 13.4 扫描基线（真实计数 @79680a9）

- `ops-cv` `upsample*` 家族 `tiling`/`infershape` 实现文件 **> 30 个**（含 `_arch35` 变体），其中带 `GetSize()` 长度校验者与不带者**并存**——即「**校验项在副本间参差**」是常态而非例外，必须全副本比对。
- 主线与副本各 **1 处**已实测确认（见 13.2）；粗筛全族后仍须逐个人工确认，**粗筛不等于结论**。

## 14. 判据层（L2/L3）：出用例与判读前必读 <!-- BEGIN DETECT-SECTION (generated by scripts/sync_detect_section.py; do not edit) -->

> 生成物，勿手改（C42 校验）。完整判据见 [references/detect-l2-l3.md](references/detect-l2-l3.md)。

- **L2**：轴 入参合法性/契约一致性/边界值｜观测 error-code｜至少 4 例
- **L3 `error-code`**：K583(假 FAIL)inplace 接口「广播变宽」是 161002 正确拒绝，纯 doc 基线会成片假 FAIL；K866(漏检)dtype 变异只改张量不改 aclScalar → 结构上抓不到标量 dtype 不校验

> 判 FAIL 先排「假 FAIL」、判 PASS 先排「假 PASS/假绿」。**不查 L3 就出结论 = 报告作废。** <!-- END DETECT-SECTION -->
