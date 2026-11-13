---
name: "fpb14-graph-path-review"
description: "对指定 aclnn 接口/算子做 FP-B14 专项检视：比对图模式（GEIR/aclGraph）与 aclnn 单算子两条通路的入口契约，找出只有图模式失败的缺陷，产出带证据链的 Bug 卡与报告。当用户遇到 aclnn 正常但图模式报 E40021/GRAPH_FAILED/Run graph failed 时使用。"
---

# FP-B14 算子检视（fpb14-graph-path-review）

对指定算子做 FP-B14 专项检视：比对**图模式通路**与 **aclnn 单算子通路**的入口契约，命中即出 Bug 卡，输出报告。

## 0. 与相邻模式的边界

| 相邻模式 | 分工 |
|---|---|
| FP-B08（节点属性未参与派发） | B08 是属性在 **pass 链路**里被丢弃（fallback 回调 / 前端插件 / fusion pass）；本模式是**两条入口路径的契约不同步**（proto 默认值 / format 白名单 / dtype 属性下发），修复落点分别是 pass 代码 vs proto-校验对齐 |
| FP-A16（aclop 与 aclnn 精度差异） | A16 是**精度**双路径差异；本模式是**功能**双路径失败（编译/推导/执行失败或结果不一致） |
| FP-F01（构建配置不一致） | 图编译的符号缺失、链接失败、`*_proto.h` 未编入 so 属构建面，归 F01 |
| FP-F03（文档与实现不一致） | proto 与文档/实现三方不一致时双向命中；本条特指"aclnn 侧已修、图模式侧未同步" |
| FP-B11（参数契约校验缺失） | B11 是"没有校验"；本条是"两条路径校验口径不同" |

## 1. FP-B14 模式卡摘要（检视依据，源自库内 `patterns/FP-B/FP-B14.md`）

- **编号 / 名称**：FP-B14 图模式（GEIR/aclGraph）通路与 aclnn 单算子通路未同步适配 ｜ **类别**：功能/兼容 ｜ **风险**：高（S2×O3=6）｜ **状态**：活跃
- **适用声明头**（照抄卡片）：仓 All ｜ 侧别 Host ｜ 载体 IR与图配置,aclnn源码,Tiling源码 ｜ 触发 图模式|GEIR|aclnnGraph|op_graph ｜ 默认启用 true
- **故障机理**：同一算子有两条交付路径——aclnn（`op_api` → tiling → kernel）与图模式（`op_graph` proto → GE 推导 → tiling → kernel）。二者共享 tiling/kernel，但**入口契约各自维护**：proto 里 attr 默认值、输入输出的 format 元数据、可选输入缺省形态、L0 的 dtype 属性、infershape 注册，都不经过 aclnn 的 `CheckShape`。只覆盖 aclnn 路径时，图模式会在编译（E40021）、推导（GRAPH_FAILED）、执行（Run graph failed / 507011）任一阶段失败，而 aclnn 全部通过。
- **触发条件**：proto attr 默认值不在 tiling 接受域内；图优化插入 `NC1HWC0` 等未列入白名单的格式；图编译需 L0 显式传 dtype 属性；可选输入缺省；infershape 注册名错/缺；图模式专用常量折叠路径不通。
- **典型表现**：**aclnn/TTK 直调全 PASS，图模式失败**；错误码 `E40021` / `GRAPH_FAILED` / `Run graph failed` / `507011`；或图模式结果与单算子不一致。特征信号：`torch.compile` / aclGraph 复现、eager 正常。
- **实证案例**：ops-nn **#5201**（`swiglu_group_grad` proto 默认值 0 与 tiling 校验 -1/>0 不同步）、**#5477**（`BNInferGrad` format 白名单过严致 GEIR 失败）、**#5922**（`matmulEmuSplitWeight` aclGraph 调用失败）、**#6017**（A5 图模式 `Run graph failed`）；ops-math **#3188**（`ArgMaxV2` 需 L0 传 dtype 属性）、**#3361**（`fillv2` geir 失败）；ops-transformer **#5736**（aclgraph 507011）。
- **关联**：FP-B08、FP-A16、FP-F01、FP-F03、FP-B11。

## 2. 检视输入与算子定位

**输入**：算子目录名或 aclnn 接口名；可选 ref。
**定位**：`op_graph/*_proto.h`（REG_OP 与 attr 默认值）、`op_host/*_def.cpp`（Attr 声明与 dtype 分派）、`op_host/*_tiling*.cpp`（ParseAttrs 校验）、`op_host/*_infershape.cpp`（注册与推导）、`tests/**/*geir*|*graph*`（图模式用例是否存在）。

## 3. 取数方式

优先本地克隆；否则 API（`contents`/`raw`，带 `User-Agent`，重试 2 次间隔 5 秒）。行号证据绑定 commit。

## 4. 检视清单（每点：查什么 → 何处 → 命中判据）

### ① proto 默认值 vs tiling 校验
- 查什么：`REG_OP` 中每个 `Attr().DefaultValue(x)` 是否落在 tiling `ParseAttrs` 的合法域内。
- 命中判据：默认值 ∉ 接受域 ⇒ 图模式缺省即失败，命中。

### ② format 元数据白名单
- 查什么：`CheckFormat`/`ValidateTensorDescs` 允许的 format 是否覆盖图优化常见格式（`NC1HWC0`、`FRACTAL_Z` 等）。
- 命中判据：白名单只有 ND/NCHW/NHWC 且算子进入图后会插格式 ⇒ 命中。

### ③ 属性下发完整性
- 查什么：950/L0 路径是否需要 `def.cpp` 声明额外属性（如 dtype）才能编译。
- 命中判据：缺该声明时 aclnngraph 编译失败 ⇒ 命中。

### ④ 可选输入/输出缺省
- 查什么：图模式下可选输入不传时的分支；`GetOptionalInputShape` 与 `GetOptionalInputDesc` 是否配对正确。
- 命中判据：缺省即崩溃/推导失败 ⇒ 命中。

### ⑤ infershape 注册
- 查什么：`IMPL_OP_INFERSHAPE`/注册名与算子名一致；推导返回值语义（GRAPH_FAILED 是否被改写）。
- 命中判据：注册名不符、或把 GRAPH_FAILED 收窄成非标准码 ⇒ 命中。

### ⑥ 双路径结果一致性
- 查什么：同一输入下 aclnn 与图模式输出是否一致。
- 命中判据：一致性问题且非精度容差导致 ⇒ 命中（若纯精度差异转 FP-A16）。

## 5. 检视流程

1. **定界**：确认算子与仓/ref。
2. **枚举**：op_graph / op_host（def / tiling / infershape）/ tests 中图模式用例。
3. **静态比对**：①~⑤ 逐项做差集。
4. **反证排除**：确认问题是否属构建面（F01）、pass 丢弃（B08）、纯精度（A16）。
5. **判定**：命中 / 观察项 / 反证排除。
6. **GitCode 查重**：检索"图模式/GEIR/该算子"。
7. **业务可达性核查**（见第 6 节 B 轴）。
8. **出报告**：运行时结论标注「静态推演，需 NPU 实测确认」。

## 6. 风险定级（S×O）与业务影响评估（B 轴）

- **S**：S3 结果错误（图模式结果与单算子不一致）、S2 功能受限（图模式不可用，但 eager 可用）、S1 资源浪费。
- **O**：O3 ≥2 条独立实证；O2 1 条；O1 仅静态。
- **风险 = S×O**：≥6 高；3/4 中；1/2 低。FP-B14 基准 S2×O3=6（高）。

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

- **图模式失败不都是本条**：先排除构建（F01）、pass 丢弃（B08）、精度（A16）。
- **必须证明 aclnn 路径正常**：否则可能是共享 tiling/kernel 的通用缺陷。
- **不臆造行号**；**静态推演声明**必写。

### 判定纪律补充（v3.6）：非对称增减、证据等级与误判记录

**增减不对称**：允许追加候选（有据即可，错了可由用户排除）；**撤销或否决候选必须附 `[文件]:[行号] [代码行]` 负向证据**。无证据的「看起来没问题」一律记为「未核查」，不得计入反证排除，也不得据此下调等级——否决造成的漏报用户不可见、不可恢复。

- **证据等级**（Bug 卡必填）：`静态可证` = 推导链完整且触发输入可静态构造；`需实测确认` = 依赖运行时输入规模、设备行为或环境差异。标 `需实测确认` 的条目**不得以「命中」名义出卡**，按观察项记录并附实测用例。
- **Agent 误判记录**（Bug 卡必填）：本次被推翻的假设、推翻它的证据（`[文件]:[行号] [代码行]` 或实测输出）、判定标准是否随之修订；无推翻写「无」。
- **误判回流**：同类误判在 3 次检视中重复出现，登记至 `cases/misjudgments.jsonl`（字段见 `cases/README.md`），并在本模式判定标准中新增对应防线；守门 C19d 校验台账字段合法。

## 8. 产出模板

### Bug 卡字段（命中项必备）

```markdown
### BUG-YYYYMMDD-XX {算子名}（{仓}，{新增/存量}）
- **接口名**：aclnnXxx / 算子名（{类别}/{op_name}/）
- **文件路径与行号证据**：
  - `{文件}:{行号}`：图模式侧契约（proto 默认值 / format 白名单 / 属性声明）
  - 对照样板（反证）：`{文件}:{行号}`（aclnn 侧对应校验）
- **FP-B14 模式编号**：FP-B14 图模式通路未同步适配（子形态：默认值/格式/属性/可选/注册/一致性）
- **S×O 风险定级**：S2×O3=6，高（若图模式结果错误则 S3×O3=9）
- **证据等级**：{静态可证 / 需实测确认}｜{一句话理由}
- **业务影响评估（B 轴）**：可达性 B{3|2|1}（一句话判据）｜ 业务影响：{静默精度损失/任务失败中断/性能退化/仅可观测性}｜ 证据：{调用方/负载/为何不可达}｜ 处置建议：{尽快修/排期修/记录}
- **故障机理推导链**：aclnn 路径如何通过 → 图模式走到哪个契约点 → 失败阶段（编译/推导/执行）→ 后果
- **触发条件可达性分析**：具体图模式调用组合。静态推演，需 NPU 实测确认
- **复现用例**：图模式（ptgraph/aclGraph）最小脚本 + 同输入 aclnn 对照，断言"两者结果一致且不抛 GRAPH_FAILED"
- **建议修复方案**：proto 默认值与 tiling 校验对齐；format 白名单补图优化格式；补属性声明；修 infershape 注册
- **测试拦截建议**：每算子一条图模式冒烟 + 与 aclnn 结果对比；新增 attr 加静态断言
- **Agent 误判记录**：{被推翻的假设 → 推翻证据 `[文件]:[行号] [代码行]`；无则「无」}
- **GitCode 查重**：{检索结论}
```

### 检视报告结构

```markdown
# FP-B14 检视报告：{算子名}（YYYY-MM-DD）
## 一、执行概览（仓/ref/HEAD、契约比对项数、判定统计：命中 X / 观察项 Y / 反证排除 Z；证据等级分布（静态可证 X / 需实测确认 Y））
## 二、命中明细（Bug 卡，每卡含 B 轴业务影响评估）
## 三、观察项
## 四、反证排除（归入 F01/B08/A16 的理由）
## 五、实测建议（图模式冒烟 + aclnn 对照矩阵）
```

## 9. 示例速览：swiglu_group_grad（ops-nn #5201）

- **定位**：`ops-nn` → `activation/swiglu_group_grad/`（`op_graph/*_proto.h` + `op_host/*tiling*.cpp`）。
- **检视面提示**：`clamp_limit` 的 `DefaultValue` 是否在 tiling `ParseAttrs` 的接受域内；#8844 收紧校验后 proto 是否同步。
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
python3 scripts/scan_fp.py --only FP-B14 --format json <目标文件>  # 签名候选（非结论）
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
| ① | 默认值不同步 | proto attr 默认值 vs tiling 接受域 | 图模式缺省值被拒（如 clamp_limit=0） |
| ② | format 白名单过窄 | 图模式 format 校验（含 NC1HWC0 元数据） | 合法 format 被判非法 |
| ③ | 属性未下发 | L0/节点属性到图执行体的透传链 | 属性在某一跳丢失 |
| ④ | 调用/执行失败 | GEIR/aclGraph 执行入口 | 图模式失败而 aclnn 直调正常 |

### 量化基线（数字来自卡片实证，引用须注明来源）

- 检索到 **9 条**相关 issue：ops-nn #5201（proto 默认值 0 与 tiling 接受域不同步）、#5477（format 校验过严）、ops-math #3188（L0 属性下发缺失）、#5922/#6017、ops-transformer #5736 等。
- 判据：**同一输入、图模式与 aclnn 直调结果/行为不一致**；单条通路正常不构成反证。

### 探针矩阵（最小可执行集）

| 探针 | 构造 | 期望 / 判据 |
|---|---|---|
| 图 vs 直调 | 同输入分别走 GEIR/aclGraph 与 aclnn | 结果一致；差异可定位到入口契约 |
| 默认值矩阵 | 不传 attr / 传 proto 默认值 / 传 tiling 默认值 | 三种写法均被接受或均明确报错 |
| format 矩阵 | ND/NZ/NC1HWC0 等逐个 format | 合法 format 不被误拒 |
| 属性透传 | 节点级属性设置后读执行侧 | 属性值原样到达 |

### 证据锚点

- `ops-nn #5201` —— swiglu_group_grad 默认 clamp_limit 被拒
- `ops-nn #5477` —— BNInferGrad format 校验过严
- `ops-math #3188` —— L0 属性下发缺失
- `ops-transformer #5736` —— 图模式调用失败

### 交接边界

| 交给 | 遇到 | 理由 |
|---|---|---|
| [FP-B08](../fpb08-fallback-review/SKILL.md) | pass 链路属性丢弃（本条是入口契约不同步） | 边界见第 0 节 |
| [FP-A16](../../FP-A/fpa16-aclop-aclnn-review/SKILL.md) | aclop/aclnn 精度差异 | 边界见第 0 节 |
| [FP-F01](../../FP-F/fpf01-build-review/SKILL.md) | 图编译符号缺失 | 边界见第 0 节 |

### 复核清单（按子型）

- ① proto attr 默认值是否落在 tiling 接受域内
- ② 图模式 format 白名单是否与 aclnn 一致
- ③ 节点/L0 属性是否原样到达执行侧
- ④ 同输入图模式与 aclnn 直调结果是否一致

## 12. 已知缺陷案例库：触发条件 / 根因 / 修复范式 / 针对性深挖（v5.1）

> 本节把本型**已确认缺陷**拆到「触发条件 → 根因（具体路径）→ 修复范式（✅ 正确代码）→ 针对性发现步骤 → 最小复现锚」的代码级颗粒度。修复范式为**正确形态示意**；含 `文件:行号` 的引用取自卡片实证，行号以被检仓本地 HEAD 为准，**不得臆造**。本型多依赖配置/契约同步，故按「哪种配置 → 根因 → 探针定位」写实。

### 案例 1｜proto attr 默认值不在 tiling 接受域内 → 图模式缺省被拒 —— #5201（swiglu_group_grad）

- **触发条件**：图模式不传 `clamp_limit`，取 proto 默认值 **0**。
- **根因（具体路径）**：`op_graph/*_proto.h` 的 `Attr(...).DefaultValue(0)` 与 `op_host/*tiling*.cpp` 的 `ParseAttrs` 合法值域（tiling 在 **#8844** 后要求 **-1 或 >0**）**不同步** → 图模式缺省即被拒；aclnn 侧显式传合法值不受影响，故**仅图模式暴露**。
- **修复范式（✅，示意）**：
```cpp
// ❌ proto 默认 0，tiling 只收 -1 或 >0
Attr("clamp_limit").DefaultValue(0);          // 图模式缺省即失败
// ✅ 默认值对齐 tiling 接受域
Attr("clamp_limit").DefaultValue(-1);         // 与 ParseAttrs 一致
```
- **针对性发现（可执行）**：① 逐项比对 proto `DefaultValue` 与 tiling `ParseAttrs` 合法值域，做差集；② 默认值 ∉ 接受域 ⇒ 命中（子型①）；③ 新增 attr 后加「proto 默认值 ∈ tiling 接受域」的静态断言。
- **最小复现锚**：图模式不传 `clamp_limit` 跑冒烟，与同输入 aclnn 对拍，断言不抛 GRAPH_FAILED。
- **实证**：#5201（ops-nn）。

### 案例 2｜format 白名单过窄 → 图优化插格式被判非法 —— #5477（BNInferGrad）

- **触发条件**：图优化插入 `NC1HWC0` 元数据。
- **根因（具体路径）**：`ValidateTensorDescs`/`CheckFormat` 的 format 白名单**过严**，把 `NC1HWC0` 元数据判为非法 → GEIR **GRAPH_FAILED**；aclnn 直调不走该插格式路径，故正常。
- **修复范式（✅，示意）**：
```cpp
// ❌ 白名单只有 ND/NCHW/NHWC，图优化插 NC1HWC0 被判非法
if (!IsOneOf(format, {ND, NCHW, NHWC})) { return GRAPH_FAILED; }
// ✅ 白名单覆盖图优化常见格式
if (!IsOneOf(format, {ND, NCHW, NHWC, NC1HWC0, FRACTAL_Z})) { return GRAPH_FAILED; }
```
- **针对性发现（可执行）**：① 读 `CheckFormat`/`ValidateTensorDescs` 白名单，核对是否覆盖图优化常见格式；② 白名单只有 ND/NCHW/NHWC 且算子进图会插格式 ⇒ 命中（子型②）。
- **最小复现锚**：图模式用例构造 `NC1HWC0` 输入元数据，断言不被误拒。
- **实证**：#5477（ops-nn）。

### 案例 3｜L0 路径缺 dtype 属性声明 → aclnngraph 编译失败 —— #3188（ArgMaxV2）

- **触发条件**：950/L0 图模式编译需显式传 dtype 属性。
- **根因（具体路径）**：`op_host/*_def.cpp` **未为 950/L0 声明必需属性（dtype）** → 图编译缺属性/符号，`aclnngraph` 编译失败（E40021 类）；aclnn 直调不经该声明路径，故正常。
- **修复范式（✅，示意）**：
```cpp
// ✅ def.cpp 为 L0 显式声明编译所需属性
REG_OP(ArgMaxV2)
    .INPUT(x, ...)
    .ATTR(dtype, Int, 0)          // L0 编译必需，缺失即编译失败
    .OP_END_FACTORY_REG(ArgMaxV2);
```
- **针对性发现（可执行）**：① 核对 `def.cpp` 是否为 950/L0 声明了图编译必需属性；② 缺该声明时 aclnngraph 编译失败 ⇒ 命中（子型③ 属性未声明/未下发）。
- **最小复现锚**：L0 图模式编译该算子，断言不报 E40021 且属性到达执行侧。
- **实证**：#3188（ops-math）。

### 案例 4｜aclgraph 执行期失败（device fault） —— #5736（qfa quant_mode=6）

- **触发条件**：`quant_mode=6`，`torch.compile`/aclgraph 路径。
- **根因（具体路径）**：图模式执行阶段报 **507011 AICore device fault**，而 eager 正常——图模式通路的入口契约（属性/format/属性透传）与执行侧期望不一致，走到与 aclnn 直调不同的实现分支。
- **修复范式（✅，示意）**：图模式侧属性/format 透传与执行侧期望对齐，属性值原样到达执行体，避免走到不支持的 `quant_mode` 分支。
- **针对性发现（可执行）**：① 属性透传探针：节点级设置 `quant_mode` 后读执行侧，确认原样到达；② 图模式失败而 aclnn 直调正常且非精度差异 ⇒ 命中（子型③/④）。
- **最小复现锚**：aclgraph 下同输入分别跑图模式与 aclnn，断言结果一致且无 507011。
- **实证**：#5736（ops-transformer）。

### 语料基线与深挖起手式

- 语料基线：ops-math/ops-nn/ops-transformer 全量 issue（2026-10-17，16 270 条中 3 011 条 bug-report），图模式相关 **69 条**（math 13 / nn 26 / transformer 30）。其余同型实证（aclnn 正常、图模式失败）：**#5922** `matmulEmuSplitWeight`、**#6017** `deformable_offsets_grad`（ops-nn）、**#2619** `reducesum/reducemean`、**#3361** `fillv2`（ops-math）。
- 深挖起手式：`python3 scripts/scan_fp.py --only FP-B14 --format json <目标文件>` —— 静态比对「proto attr 默认值 ⊄ tiling 接受值域」；扫描 `GetOptionalInputShape` 与 `GetOptionalInputDesc` 误用；核查仓内图模式用例覆盖。
- 结论纪律：**单条通路正常不构成反证**；同一输入图模式与 aclnn 直调结果/行为不一致才是判据。

## 13. 实证加深（v5.4）：真实修复锚 · 同簇完整清单 · 反向排除项

> 本节在 §11/§12 之上做**取证加深**：① 用被检仓**真实代码**替换案例里的「示意」修复代码；② 补齐双路径同簇的**完整清单**（区分「已核实锚」与「待人工复核」）；③ 给出**反向排除项**（须附 `[文件]:[行号] [代码行]` 负向证据，口径同 §7 非对称规则）。行号取自公开仓实测 commit（标 `@<sha>`）；**未取到真实来源者一律标「示意/待复核」，不配虚构行号**。

### 13.1 真实修复锚（替换「示意」）

本轮核实 **3 处**真实修复锚（`cann/ops-nn` `@a7539b` 2026-10-17、`cann/ops-math` 同批），修复范式统一为「**把图模式侧的属性/校验与 tiling 侧对齐**」：

| issue | 真实锚（仓见行内） | 真实修复要点（引真实代码） |
|---|---|---|
| #5201 `SwigluGroupGrad` | `ops-nn` `activation/swiglu_group_grad/op_graph/swiglu_group_grad_proto.h:61`；文档 `:20`、`:51` | **proto 默认值已从 0 同步为 `-1.0f`**：`.ATTR(clamp_limit, Float, -1.0f)`；文档 `:20`「Attribute: clamp_limit (Float, default=-1 → no clamp)」、`:51`「default -1 means no clamp (c=+∞)」——与 tiling 侧要求一致 |
| #5201 对照（tiling 侧） | `ops-nn` `activation/swiglu_group_grad/op_host/arch35/swiglu_group_grad_tiling_base.cpp:205-209` | `OP_CHECK_IF(*clampLimitAttr != -1.0f && !(*clampLimitAttr > 0.0f), OP_LOGE(… "clamp_limit must be -1.0 (no clamp) or > 0.0, but got %f" …), return ge::GRAPH_FAILED)` —— tiling **要求 -1 或 >0**，正是 proto 默认 0 被拒的根源（#8844 后收口） |
| #5477 `BNInferGrad` | `ops-nn` `norm/bn_infer_grad/op_host/bn_infer_grad_def.cpp:37-49`；tiling `norm/bn_infer_grad/op_host/arch35/bn_infer_grad_tiling_arch35.cpp:286-291` | def 声明 `grads`/`x_backprop` 为 `{FORMAT_NCHW, …, FORMAT_NHWC}`、`scale`/`batch_variance` 为 `{FORMAT_ND}`；tiling 侧 `ValidateOutputTensorDesc(ge::DataType gradsDtype, ge::Format gradsFormat)` **`:290 (void)gradsFormat;` 显式不使用 format**，仅 `:291` 校 dtype 相等 —— 即缺陷修复形态是「**tiling 不再按 format 拦 GEIR 元数据**」 |
| #3188 `ArgMaxV2` | **`ops-math@f94a6cd6d`** `math/arg_max_v2/op_graph/arg_max_v2_proto.h:48`；文档 `:32` | `.ATTR(dtype, Type, DT_INT64)` —— **L0 已声明 `dtype` 属性**；文档 `:32`「dtype: The output type, either "int32" or "int64". Defaults to "int64"」——图模式编译失败所需的属性已补齐。**v6.19 修正**：本行原与上三行同标 `@a7539b`（ops-nn），但 `arg_max_v2` 实际位于 **ops-math**，ops-nn 无此算子——属跨仓错用；行号 `:48`/`:32` 已在 ops-math HEAD 逐字复核吻合 |

### 13.2 同簇完整清单（图模式双路径属性/校验缺口）

语料基线沿用 §11：三仓图模式相关 **69 条**（math 13 / nn 26 / transformer 30）。本轮**已核实锚 3 处**（上表），**其余同簇 5 条未定位到具体行号**，如实列名**待人工复核**（不臆造路径）：

| # | 算子在案描述（引自 §11 卡片语料） | 锚状态 |
|---|---|---|
| 1 | **#5201** `swiglu_group_grad` 图模式缺省 `clamp_limit` 被 proto 默认值拒 | ✅ 已核实（13.1） |
| 2 | **#5477** `BNInferGrad` format 校验过严致 GEIR `GRAPH_FAILED` | ✅ 已核实（13.1） |
| 3 | **#3188** `ArgMaxV2` L0 未传 `dtype` 致 aclnngraph 编译失败 | ✅ 已核实（13.1） |
| 4 | **#5922** `matmulEmuSplitWeight` aclGraph 调用失败 | ⏳ 待人工复核 |
| 5 | **#6017** `deformable_offsets_grad` A5 图模式 example `Run graph failed` | ⏳ 待人工复核 |
| 6 | **#2619** `reducesum/reducemean` geir 功能失败 | ⏳ 待人工复核 |
| 7 | **#3361** `fillv2` geir 通路失败 | ⏳ 待人工复核 |
| 8 | **#5736** `qfa quant_mode=6` aclgraph 下报 507011 AICore device fault | ⏳ 待人工复核 |

→ 检视时**必须做四仓（ops-nn/ops-math/ops-transformer/op-plugin）proto ↔ tiling ↔ 注册三处交叉比对**；仅核单仓单通路会漏掉跨仓同簇项。

### 13.3 反向排除项（须附负向证据）

按 §7 非对称规则，宣称「双路径已对齐/不属本型」须给出 `[文件]:[行号] [代码行]`：

| 排除项 | 排除所需负向证据 |
|---|---|
| proto 默认值落在 tiling 接受域内 | 给出 proto `.ATTR(...)` 默认值行 + tiling 值域校验行**两处** `[file]:[line]`，并证明默认值 ∈ 校验域 |
| attr 可选且缺省即合法 | 给出 proto 中该 attr 未声明 default（optional）的 `[file]:[line]` |
| format 差异由框架统一抹平 | 给出 def 中 `Format`/`UnknownShapeFormat` 两处一致的 `[file]:[line]`（**仅一处一致不足以排除**，`UnknownShapeFormat` 缺失是常见漏洞） |
| 图模式通路不在被检算子支持范围 | 给出算子注册/支持矩阵中未注册图模式的声明行 |

### 13.4 扫描基线（真实计数 @a7539b）

- 本轮在 `@a7539b` 核实 **3 处**真实修复锚（13.1），涉及 proto/def 属性声明与 tiling 校验两类载体；`proto attr 默认值 ⊄ tiling 接受值域` 的静态比对仍是**最高命中率**起手式。
- `Format` 与 `UnknownShapeFormat` 必须**成对**核查：`norm/bn_infer_grad/op_host/bn_infer_grad_def.cpp:39-42` 两处成对出现即为**正确样板**，缺失其一即为候选。

## 14. 判据层（L2/L3）：出用例与判读前必读 <!-- BEGIN DETECT-SECTION (generated by scripts/sync_detect_section.py; do not edit) -->

> 生成物，勿手改（C42 校验）。完整判据见 [references/detect-l2-l3.md](references/detect-l2-l3.md)。

- **L2**：轴 执行序列/属性｜观测 golden-utol/error-code｜至少 2 例
- **L3 `golden-utol`**：K91(假 FAIL)inf==inf 被判超容差；溢出类用例整批假 FAIL；K508(假 PASS)judge 列写成 JSON 会被静默忽略 → 回落 dtype 默认容差（fp16 rtol=1e-3）
- **L3 `error-code`**：K583(假 FAIL)inplace 接口「广播变宽」是 161002 正确拒绝，纯 doc 基线会成片假 FAIL；K866(漏检)dtype 变异只改张量不改 aclScalar → 结构上抓不到标量 dtype 不校验

> 判 FAIL 先排「假 FAIL」、判 PASS 先排「假 PASS/假绿」。**不查 L3 就出结论 = 报告作废。** <!-- END DETECT-SECTION -->
