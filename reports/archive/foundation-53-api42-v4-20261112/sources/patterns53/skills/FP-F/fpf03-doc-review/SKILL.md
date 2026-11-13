---
name: "fpf03-doc-review"
description: "基于 FP-F03「文档/声明面与实现面不一致」故障模式对算子文档与声明面做检视：定位 README/支持矩阵/def 注册面，按支持矩阵与 AddConfig 差集、确定性声明与 kernel 行为不符、文档整体复制兄弟算子、脚本 help 与映射表矛盾四成因核查并定级。当用户遇文档与实现不符、支持表声明而实际未适配、确定性开关不生效时使用。"
---

# FP-F03 文档/声明面检视（fpf03-doc-review）

对用户指定的算子 / 模块做 FP-F03 专项文档与声明面检视：先定位声明面（README 产品支持表、确定性声明、参数约束、脚本 help）与实现面（`AddConfig` 注册、kernel 行为、公式与 dtype 定义），再按六成因清单做**声明面 × 实现面差集核查**，每个结论给出**文件 + 行号 + 推导链**证据，命中即出 Bug 卡，输出检视报告。**本模式特殊纪律：① 检视对象是**声明与实现的一致性**，不是文档写得好不好——「文档声明支持而实际未适配」「确定性声明与 kernel 行为相反」才是缺陷；② 大量命中源于**兄弟算子复制**，故「复制残留检测」是本型第一扫描动作（README 首行 Op 名 ≠ 目录名、公式/dtype/链接指向兄弟算子）；③ 用户按声明接入才会踩坑，故判定须给出「用户按 README 在声明支持的产品上调用会得到什么」的推导。**

## 0. 与相邻模式的边界

| 相邻模式 | 分工 |
|---|---|
| FP-F01（构建配置不一致） | 支持声明 vs binary.json 产物面同源：F01 管**产物面**（def 注册了就必须有 binary.json 产物、能编译打包），F03 管**声明面**（README 支持表 vs def 注册清单）；门禁可合并 |
| FP-A20（确定性等级未分级标注） | 确定性等级未分级标注是「确定性声明」维度的特化——A20 管等级信息未暴露，F03 成因② 管**声明与 kernel 实际行为相反** |
| FP-B01（校验过严/声明与实现不符） | 镜像关系：B01 是校验拦截了**声明外**的输入；F03 是文档声明了**实现外**的能力 |
| FP-F04（交付面缺失） | 属两型**复合**：文档声明支持（F03 面）+ 接口实际不可用（F04 面），命中 F03 时同步核 F04 |
| FP-F02（维测/错误上报） | 声明面的错误码/文案 vs 实现——F02 管上报质量，F03 管文档声明与实现行为 |

**症状反查定位**：用户按 README 在声明支持的产品上调用报「未适配」→ 成因①；确定性开关不生效与文档矛盾 → 成因②；geir 示例 include/REG_OP 名指向兄弟算子编译失败、README 标题/公式/dtype 全错 → 成因③；脚本 help 文本声称的支持面与代码映射表矛盾 → 成因④；Proto 端口 dtype 用 `NumberType()` 兜底、宽于/窄于 OpDef 与 README → 成因⑤；按注释省略必填属性、或按文档省略实际必填的可选输入后构图/调用失败 → 成因⑥。

## 1. FP-F03 模式卡摘要（检视依据，源自本库 `patterns/FP-F/FP-F03.md`，v3.1）

- **编号 / 名称**：FP-F03 文档/声明面与实现面不一致 ｜ **类别**：工程/交付 ｜ **风险**：中（S1×O3=3）｜ **状态**：活跃
- **适用声明头**（照抄卡片）：仓 All ｜ 侧别 All ｜ 载体 文档与支持矩阵,IR与图配置 ｜ 触发 README|AddConfig|TensorType::(Real)?NumberType\(\) ｜ 默认启用 true
- **skill 核查面**：载体为文档与支持矩阵、IR 与图配置——skill 落地为四类声明面文件：`README.md`（产品支持表）、`op_host/{op}_def.cpp`（`AddConfig` 注册清单，实现面）、`docs/`（接口文档/确定性声明/参数约束）、geir 示例与 `op_graph`（include/`REG_OP` 名与构造）、`build.sh`（help 文本 vs `get_soc_version()` 映射）；kernel 行为面（`GetDeterministic()` / `SetAtomicAdd` / 同步机制）在判定成因② 时读取
- **故障机理**：README/产品支持矩阵/确定性声明/参数约束等**声明面**与代码实际（`AddConfig` 注册面、kernel 行为面、公式与 dtype 定义）脱节，误导用户接入与测试判定。四种独立成因：① **支持矩阵声明支持某产品而 def 仅注册单一 soc**（或反向，开源仓无对应 kernel）；② **确定性描述与代码实际行为不符**（声明支持开关实际不支持、声明非确定实际确定）；③ **文档整体复制自兄弟算子**——公式/dtype/Op 名/链接全错；④ **脚本 help 文本声称的支持面与代码映射表矛盾**；⑤ **Proto/IR 声明面与 OpDef/README 三方 dtype 或 rank 集合不一致**；⑥ **可选/必选/属性归属标注与执行端不一致**（Proto `OPTIONAL_INPUT`/`REQUIRED_ATTR` ↔ README 参数表 ↔ `CheckNotNull`/InferShape 实际要求）。
- **触发条件**：兄弟算子复制创建、新平台（如 ascend950）接入后文档未同步、产品矩阵人工维护滞后于注册代码变更。
- **典型表现**：用户按 README 在声明支持的产品上调用报「未适配」；确定性开关不生效与文档矛盾；geir 示例 include/`REG_OP` 名指向兄弟算子编译失败；误判平台支持范围放弃或误用。
- **源码审查映射点**：README 产品支持表 × `*_def.cpp` 中 `AddConfig` 注册清单比对；确定性描述 × kernel `GetDeterministic()` / `SetAtomicAdd` / 同步机制核查；文档公式 × kernel 注释/golden 实现一致性；文档 dtype 清单 × def/binary.json 注册 dtype 一致性。
- **检测签名**：README 支持表行与 `AddConfig\(\"([a-z0-9_]+)\"` 的自动差集扫描；文档标题/Op 名与本目录名比对（复制残留检测：`README.md` 首行 Op 名 ≠ 目录名）。
- **测试拦截建议**：将「README 支持表 vs def 注册」纳入 CI 静态门禁（与 FP-F01 的 binary.json 门禁同源）；算子复制创建类 PR 强制 diff 审查文档改名完整性（标题/公式/dtype/示例/链接五件套）；确定性声明变更须附 kernel 侧代码依据。
- **实证案例**：ops-nn **#4890**（closed）BatchNorm/BatchNormElemt/BatchNormBackward/GroupNormBackward/RmsNormGrad/RmsNormGradQuant 六算子文档统一声明「默认非确定、支持 aclrtCtxSetSysParamOpt 开启」，而 A5 arch35 kernel 实际默认确定性且不读取该开关（regbase tiling 不检查 `GetDeterministic()`）；ops-nn **#4504**（closed）index 目录 15 个算子 README 产品支持表声明支持 A3/A2/推理/训练等（3~6 个产品），def `AddConfig` 仅注册 `ascend950`；ops-cv **#567**（closed）resize_bilinear_v2 / resize_nearest_neighbor_v2 文档产品表对 Atlas 全标 √ 而开源仓无 Atlas kernel、**#570**（closed）普通 bilinear/bicubic 上采样 def 未注册 ascend950 而 `_aa` 变体已注册（同族不对称）；ops-math **#2922**（open）rsqrt_grad README 与 geir 示例整体复制自 sqrt_grad——标题、公式（`z=dy*0.5/y` 应为 `-0.5*y^3*dy`）、dtype 清单、950 支持标记、proto 链接、示例文件名与 `op::SqrtGrad` 构造全错，示例无法编译；ops-fft **#42**（closed）build.sh 帮助文本声称「仅支持 Ascend950」而 `get_soc_version()` 实际映射 6 种型号。
- **关联**：FP-F01（支持声明 vs binary.json 产物面同源）、FP-A20（确定性等级未分级标注是「确定性声明」维度的特化）、FP-B01（声明面与校验面不一致的镜像）、FP-F04（文档声明而接口不可用的复合）。

## 2. 检视输入与检视对象定位

**输入**：算子名 / 模块名（必填，如 `rsqrt_grad`、`index` 目录）；可选 ref（默认 master）、指定仓（默认自动定位）；可选**目标平台**（如 ascend950 / Atlas——决定支持矩阵差集方向）；可选**文档类型**（README 支持表 / 确定性声明 / geir 示例 / build.sh help——可定向核查）。

**算子名 → 目录换算**：去 `aclnn` 前缀 + 驼峰转下划线小写：
`aclnnRsqrtGrad → rsqrt_grad`、`aclnnResizeBilinearV2 → resize_bilinear_v2`、`aclnnBatchNorm → batch_norm`。

**仓定位顺序**（GitCode `cann` 组织，逐仓用目录列表确认）：`ops-nn`（norm/loss/index/activation 类）→ `ops-math`（math/conversion 类）→ `ops-cv`（image/vision 类）→ `ops-transformer`（attention/moe 类）；脚本 help 类实证来源另含 `ops-fft`。**复制残留识别**：算子是否由兄弟算子复制创建（同族 `sqrt_grad` / `rsqrt_grad`、`bilinear` / `bilinear_aa` 成对存在）——存在即触发成因③ 的复制差集核查。**类目名不总与直觉一致**（如 rsqrt_grad 在 `math/`、index 类在 `index/`），以目录列表为准。

**声明面 × 实现面结构约定**（示例 `cann/ops-math` → `math/rsqrt_grad/`）：

```text
{类别}/{op_name}/
├── README.md                     # 产品支持表、确定性声明、公式/dtype——声明面主对象
├── op_host/{op}_def.cpp          # AddConfig("<soc>") 注册清单——实现面（支持矩阵差集另一边）
├── op_graph/*_proto.h            # proto 链接与 REG_OP 名——成因③ 复制残留核对点
├── docs/                         # 接口文档、参数约束、确定性说明
├── examples/geir/                # geir 示例：include / op::Xxx 构造 / 文件名——成因③ 高发面
└── op_kernel/                    # 确定性行为面（GetDeterministic/SetAtomicAdd/同步）——成因② 对照面
{repo}/build.sh                   # help 文本 × get_soc_version() 映射——成因④
```

## 3. 取数方式（Important）

公开网页端点被拦截，**必须走 API**（均需带 `User-Agent`；失败重试 2 次、间隔 5 秒）：

| 用途 | 端点 |
|---|---|
| 目录列表 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/contents/{path}?ref={ref}` |
| 单文件内容 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/raw/{path}?ref={ref}` |
| Issue 查重 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/issues?q={关键词}` |

**已实测不可用（截至 2026-09 实测）**：`https://gitcode.com/{repo}/raw/{sha}/{path}`、`https://raw.gitcode.com/...` → 403 或拦截页；端点策略如有变化可复测。若本地已有算子仓克隆，优先直接读本地文件，行号证据以本地 HEAD 为准并记录 commit。**本模式特有取数限制**：① 支持矩阵差集两边（README 表 × `AddConfig` 清单）都必须**实际读到**，不得凭印象；② 成因② 的 kernel 行为（是否读取确定性开关）须读 kernel/tiling 代码确认，不能只看文档；③ geir 示例是否真能编译需实测或读 include/构造比对。

## 4. 四成因检视清单（每点：查什么 → 何处 → 命中判据）

对四类声明面文件逐点核查，**每点先做差集、再做反证排除**；声明与实现一致的面也要记录（作为反证依据）。

### 成因① 支持矩阵声明与 def 注册不一致
- 查什么：README 产品支持表声明支持的产品集合 × `{op}_def.cpp` 中 `AddConfig("<soc>")` 的注册集合——**双向差集**（声明支持而 def 未注册 / def 注册而声明未列）；反向亦含「开源仓无对应 kernel」（实证 ops-cv #567：文档产品表对 Atlas 全标 √ 而开源仓无 Atlas kernel）；同族不对称（实证 ops-cv #570：普通 bilinear/bicubic 未注册 ascend950 而 `_aa` 变体已注册）；批量形态（实证 ops-nn #4504：index 目录 15 算子 README 声明 3~6 个产品、def 仅注册 `ascend950`）。
- 何处：`README.md` 产品支持表行、`op_host/{op}_def.cpp` 的 `AddConfig` 清单、`op_host/config/<soc>/` 目录清单。
- 命中判据：支持表产品集合与 `AddConfig` 集合差集非空 ⇒ 命中；反证：产品由另一实现/kernel 路径支持（须读出对应注册）。

### 成因② 确定性描述与 kernel 实际行为不符
- 查什么：文档确定性描述（默认确定/非确定、是否支持 `aclrtCtxSetSysParamOpt` 开启）× kernel/tiling 实际行为（是否读取 `GetDeterministic()`、是否用 `SetAtomicAdd`、同步机制）——声明支持开关而实际不读取、声明非确定实际确定（实证 ops-nn #4890：六算子文档声明「默认非确定、支持开关开启」，A5 arch35 kernel 实际默认确定性且 regbase tiling 不检查 `GetDeterministic()`）。
- 何处：`docs/` 与 README 的确定性声明、kernel 的 `GetDeterministic()` / `SetAtomicAdd` / 同步机制、tiling 的确定性分支。
- 命中判据：文档声明与 kernel 行为相反（声明支持开关而代码不读取 / 声明非确定而实际确定）⇒ 命中；确定性声明变更须附 kernel 侧代码依据。

### 成因③ 文档整体复制自兄弟算子（复制残留）
- 查什么：**复制残留检测**——`README.md` 首行 Op 名 ≠ 本目录名；文档公式 × 本算子数学语义（实证 ops-math #2922：rsqrt_grad 公式 `z=dy*0.5/y` 应为 `-0.5*y^3*dy`，复制自 sqrt_grad）；dtype 清单、950 支持标记、proto 链接、geir 示例文件名与 `op::Xxx` 构造是否指向兄弟算子（实证 #2922：示例文件名与 `op::SqrtGrad` 构造全错致示例无法编译）。
- 何处：`README.md` 标题/公式/dtype 表、`docs/`、`op_graph/*_proto.h` 链接、`examples/geir/**` 的 include 与 `op::Xxx` 构造、示例文件名。
- 命中判据：能指认「某字段/链接/构造指向兄弟算子且与本算子语义不符」⇒ 命中（给出本算子正确语义对照）。

### 成因④ 脚本 help 文本与代码映射表矛盾
- 查什么：`build.sh` 帮助文本声称的支持面 × 代码中实际映射（如 `get_soc_version()` 的型号表）——实证 ops-fft #42：help 声称「仅支持 Ascend950」而 `get_soc_version()` 实际映射 6 种型号。
- 何处：`build.sh` 的 help/usage 文本、`get_soc_version()` 类映射函数。
- 命中判据：help 文本的支持面与映射表差集非空 ⇒ 命中。

### 横切面：复制残留与门禁
- 查什么：算子复制创建类 PR 是否强制 diff 审查文档改名完整性（标题/公式/dtype/示例/链接五件套）；「README 支持表 vs def 注册」是否纳入 CI 静态门禁（与 FP-F01 的 binary.json 门禁同源）。
- 何处：CI 配置、PR 模板、`README.md` 首行 Op 名与目录名比对脚本。
- 命中判据：门禁缺失 ⇒ 记录为流程缺陷观察项（本型批量命中的根因）。

### 防护面与反证（记录用）
- 查什么：支持表与 `AddConfig` 一致、确定性声明与 kernel 行为一致、文档非复制残留、help 与映射表一致——逐条记录（文件:行号）。

## 5. 检视流程

1. **定界**：换算算子/模块目录，确认所在仓与 ref、目标平台；识别是否由兄弟算子复制创建（同族目录成对存在）；确认文档类型是否定向。
2. **枚举**：目录列表列出声明面（README / docs / examples/geir / build.sh）与实现面（def / op_graph / kernel）文件清单。
3. **触发词扫描**：按 `AddConfig\("([a-z0-9_]+)"`、`README.md` 首行 Op 名 vs 目录名、`GetDeterministic|SetAtomicAdd`、`get_soc_version|usage|help` 定位风险面（本地仓用 grep；API 模式逐文件拉取后检查）。
4. **四成因差集核查**：每点记录命中面与防护面证据（文件:行号）；成因① 做 README × `AddConfig` 双向差集，成因② 读 kernel/tiling 确认行为，成因③ 做复制残留字段比对，成因④ 做 help × 映射表比对。
5. **反证排除**：产品由另一实现路径支持、确定性声明已随代码更新、复制残留字段经核对确属本算子语义、help 与映射表一致 → 明确写出反证理由。
6. **判定**：按第 7 节标准给出 命中 / 观察项 / 反证排除。
7. **GitCode 查重**（仅命中项）：issues API 按算子名 + `README|支持|确定性|文档|未适配` 检索，逐条比对是否同机理；无同机理才立卡。
8. **业务可达性核查**（仅命中项）：判 B 等级、定业务影响类型、给处置建议；默认保守（无法证明不可达即记 B3），降档须附证据；B 不改 S×O 档位。
9. **出报告**：按第 8 节模板落盘；静态差集结论标注「声明面/实现面均为实读」并附门禁接入建议。

## 6. 风险定级（S×O）与业务影响评估（B 轴）

- **S**：S1（声明误导——用户误判支持范围、确定性开关不生效、示例无法编译，通常不改变已交付算子功能）；S2 仅当误用导致功能性后果（按声明接入后失败且无绕行）时升级（须依据）。
- **O**：O3 = ≥2 条独立实证；O2 = 1 条独立实证；O1 = 仅静态扫描命中或团队笔记（实证 = 确认对应的 issue / PR，或经跨仓、跨分支核验确认的缺陷记录，同权计入）。静态推演命中且无实证默认 **O1**；升档须在报告中给出实证依据。
- **风险 = S×O**：≥6 高；3/4 中；1/2 低。FP-F03 基准：模式卡整体 S1×O3=3（中）；纯静态命中 S1×O1=1（低）。

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

- **差集必须双向且实读**：成因① 要同时查「声明支持而 def 未注册」与「def 注册而声明未列」；两边都必须实际读到（README 表 + `AddConfig` 清单），不得凭印象。
- **三种判定**：
  - **命中**（可静态证不一致）：「支持表 × AddConfig 差集非空」「确定性声明与 kernel 行为相反」「复制残留字段指向兄弟算子」「help × 映射表矛盾」任一推导链完整 + 用户按声明接入的后果可指认 → 立 Bug 卡；
  - **观察项**：支持面是否由外部实现提供、确定性行为依赖具体 SoC 分支 → 记录并附验证方案，按 S1×O1 暂定；
  - **反证排除**：产品由另一实现路径支持、声明已随代码更新、复制残留经核对属本算子语义、help 与映射表一致 → 明确写出反证理由。
- **复制残留检测是第一扫描动作**：`README.md` 首行 Op 名 ≠ 目录名即高危信号，须逐字段核对（标题/公式/dtype/示例/链接五件套）。
- **成因② 必须读 kernel 代码**：不能只看文档——须确认 kernel/tiling 是否**实际读取**确定性开关（实证 #4890 的反面教材是声明支持而代码不读取）。
- **不臆造行号与文档内容**：每条证据必须是实际读到的 文件:行号 / 字段；引用实证样板时同样给出路径与行号，issue 时点行号与本仓 HEAD 漂移时注明。
- **静态推演声明**：示例能否编译、用户接入是否报「未适配」等运行时结论标注「静态比对，需实测确认」。

### 判定纪律补充（v3.6）：非对称增减、证据等级与误判记录

**增减不对称**：允许追加候选（有据即可，错了可由用户排除）；**撤销或否决候选必须附 `[文件]:[行号] [代码行]` 负向证据**。无证据的「看起来没问题」一律记为「未核查」，不得计入反证排除，也不得据此下调等级——否决造成的漏报用户不可见、不可恢复。

- **证据等级**（Bug 卡必填）：`静态可证` = 推导链完整且触发输入可静态构造；`需实测确认` = 依赖运行时输入规模、设备行为或环境差异。标 `需实测确认` 的条目**不得以「命中」名义出卡**，按观察项记录并附实测用例。
- **Agent 误判记录**（Bug 卡必填）：本次被推翻的假设、推翻它的证据（`[文件]:[行号] [代码行]` 或实测输出）、判定标准是否随之修订；无推翻写「无」。
- **误判回流**：同类误判在 3 次检视中重复出现，登记至 `cases/misjudgments.jsonl`（字段见 `cases/README.md`），并在本模式判定标准中新增对应防线；守门 C19d 校验台账字段合法。

## 8. 产出模板

### Bug 卡字段（命中项必备）

```markdown
### BUG-YYYYMMDD-XX {算子/模块名}（{仓}，{新增/存量}）
- **检视对象**：{README / docs / examples/geir / build.sh / {op}_def.cpp}
- **命中成因**：①~④（+ 横切面）中的编号与名称
- **文件路径与行号证据**：
  - `{文件}:{行号}`：{现象（支持表声明 X / 确定性声明 Y / 复制残留字段 / help 文本）}
  - 对照面（实现面证据）：{文件}:{行号}（AddConfig 清单 / kernel 行为 / 映射表）
- **FP-F03 模式编号**：FP-F03 文档/声明面与实现面不一致（成因①~④）
- **S×O 风险定级**：S1（声明误导）× O1（静态差集无实测）= 1，低（有实测/后果依据后复评）
- **证据等级**：{静态可证 / 需实测确认}｜{一句话理由}
- **业务影响评估（B 轴）**：可达性 B{3|2|1}（{一句话判据}）｜ 业务影响：{静默精度损失/任务失败中断/性能退化/仅可观测性}｜ 证据：{调用方/公开负载/为何不可达}｜ 处置建议：{尽快修/排期修/记录}
- **故障机理推导链**：{声明面字段 → 实现面实际 → 用户按声明接入的后果 的差集推导}
- **触发条件可达性分析**：{目标平台 / 确定性开关 / geir 示例编译 的具体构造}
- **建议修复方案**：{改支持表 / 修确定性声明或补 kernel 依据 / 修公式与 dtype / 修示例构造与链接 / 对齐 help 与映射表}
- **测试拦截建议**：CI 加「README 支持表 vs def 注册」静态门禁；复制创建类 PR 强制 diff 五件套审查；确定性声明变更附 kernel 依据；geir 示例纳入编译冒烟
- **Agent 误判记录**：{被推翻的假设 → 推翻证据 `[文件]:[行号] [代码行]`；无则「无」}
- **GitCode 查重**：{issues API 检索结论，无同机理 issue 才立卡}
```

### 检视报告结构

```markdown
# FP-F03 检视报告：{算子/模块名}（YYYY-MM-DD）
## 一、执行概览（仓/ref/HEAD、目标平台、声明面/实现面文件清单、判定统计：命中 X / 观察项 Y / 反证排除 Z；命中项 B 轴分布 B3×a / B2×b / B1×c）
## 二、命中明细（Bug 卡，按第 8 节字段，每卡含 B 轴业务影响评估）
## 三、观察项（表：# / 成因 / 文件:行号 / 存疑点 / 验证方案）
## 四、反证排除（表：成因点 / 反证理由 / 防护面证据）
## 五、门禁建议（README 支持表 × AddConfig 差集接入点、复制残留五件套审查、确定性声明代码依据要求）
```

> 报告须在「执行概览」标注证据等级分布（静态可证 X / 需实测确认 Y），并在文末单列「Agent 误判记录」小节（无则写「无」）。

报告落盘到当前任务工作区，建议命名 `FP-F03检视_{算子或模块名}_YYYYMMDD.md`。

## 9. 示例速览：rsqrt_grad 复制残留与 index 目录支持矩阵

- **定位**：`cann/ops-math` → `math/rsqrt_grad/`（README / docs / examples/geir / `op_host/rsqrt_grad_def.cpp`；同族 `math/sqrt_grad/` 为复制源——成因③ 对照面）；`cann/ops-nn` → `index/`（15 算子 README 支持表 × def 注册，成因①）；`cann/ops-nn` → `norm/` 类目（BatchNorm/RmsNormGrad 等六算子确定性声明，成因②）；`cann/ops-cv` → `resize_bilinear_v2` / `resize_nearest_neighbor_v2`（Atlas 声明，成因①）；`cann/ops-fft` → `build.sh`（help 文本 × `get_soc_version()`，成因④）。
- **检视面提示**（引导，不预设结论，仍须逐点核查；行号以本地 HEAD 为准）：
  - 成因③：`rsqrt_grad/README.md` 首行 Op 名与目录名比对、公式 `z=dy*0.5/y` vs 本算子正确语义 `-0.5*y^3*dy`、dtype 清单、950 支持标记、proto 链接、`examples/geir/` 示例文件名与 `op::SqrtGrad` 构造（实证 ops-math #2922：整体复制自 sqrt_grad，示例无法编译）；
  - 成因①：`ops-nn/index/` 15 算子 README 产品支持表 × 各 `*_def.cpp` 的 `AddConfig` 清单双向差集（实证 #4504：支持表声明 3~6 个产品、def 仅注册 `ascend950`）；`ops-cv` resize 系列产品表 × 开源仓 kernel 存在性（实证 #567/#570）；
  - 成因②：`norm/` 类目 BatchNorm / BatchNormElemt / BatchNormBackward / GroupNormBackward / RmsNormGrad / RmsNormGradQuant 的确定性声明 × A5 arch35 kernel 是否读取 `GetDeterministic()`（实证 ops-nn #4890：声明「默认非确定、支持开关」，实际默认确定性且不读取）；
  - 成因④：`ops-fft/build.sh` 的 help 文本 × `get_soc_version()` 型号表（实证 #42：声称仅支持 Ascend950、实际映射 6 种型号）。
- 任何一点的最终判定以第 4/5/7 节口径为准，禁止凭对象类型直接下结论。

## 10. 能力边界与自检（v3.8）

### 能力边界

- **静态可证**：清单里能在源码内给出「`文件:行号` + 推导链」的部分，按第 7 节判据出卡。
- **需实测确认**：依赖运行时输入规模、设备行为或环境差异的结论，只能记观察项并附实测用例（证据等级见第 7 节）。
- **不覆盖**：本模式以外的机理（边界见第 0 节）与仓外框架侧行为；`TRIAGE.md` 只负责收敛候选，不构成判定依据。
- **找不到 ≠ 没有**：按清单未命中只说明「本轮未发现」，不得表述为「该算子无此缺陷」；抽样核查须在报告写明抽样口径。

### 自检

```bash
python3 scripts/gen_triage.py --check                          # 分诊表与映射一致
python3 scripts/scan_fp.py --only FP-F03 --format json <目标文件>  # 签名候选（非结论）
python3 scripts/verify_lines.py <报告.md> --root <被检仓>        # 行号校验
python3 check_fault_patterns.py                                # 全库守门
```

### 工作量与抽样（v4.0）

- **深度档：宽浅**（索引 `depth` 字段）——只跑签名定位 + 每类抽 3 例；报告必须写「抽样，非全量」，不得表述为全量检视。
- **报告必填**：抽样口径（全量 / 每点前 N 处 / 每类 N 例）+ 停止点记录；未写口径视为未完成。
