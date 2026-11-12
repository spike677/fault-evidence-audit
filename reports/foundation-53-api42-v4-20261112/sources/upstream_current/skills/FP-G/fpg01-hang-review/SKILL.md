---
name: "fpg01-hang-review"
description: "基于 FP-G01「执行挂死与调度超时」故障模式对指定 aclnn 接口做源码检视：定位算子实现，按死循环不推进、回绕长循环、通信等待超时、设备侧超时、资源泄漏五子型清单核查推进变量、退出防护与成对释放，产出证据链与 S×O 定级报告。当用户给出接口名要求做挂死、卡死或超时排查时使用。"
---

# FP-G01 aclnn 接口检视（fpg01-hang-review）

对用户指定的 aclnn 接口（如 aclnnPromptFlashAttention）做 FP-G01 专项源码检视：定位算子实现，按五子型清单逐项核查，每个结论给出**文件 + 行号 + 推导链**证据，命中即出 Bug 卡并输出报告。**本模式特殊纪律：缺陷不是「算错了」而是「永远算不完」——数值断言等不到，UT 天然漏检；触发常依赖用例执行顺序（单例污染），「单独跑不复现」不是反证。卡片适用声明为「必须触发」：不依赖签名命中，对被检算子无条件执行五子型清单，`while(true)` 类签名仅为定位提示。**

## 0. 与相邻模式的边界

| 相邻模式 | 分工 |
|---|---|
| FP-C01（端到端耗时占比高） | **最易混淆**：C01 是「**慢但能完成**」（耗时非整数倍阶跃、日志持续推进），本条是「**根本没完成**」（日志无进展）。host 无退出循环异常分支不推进即空转归本条子型①；上界写错多算但收敛归 C01 子型② |
| FP-B10（集合通信功能/兼容面） | **边界约定**：集合通信的**等待超时**归本条子型②；通信库的功能/精度/兼容面归 B10 |
| FP-B07（索引/偏移越界） | 越界也会致异常终止，但本条特征是「**不终止**」——进程存活、永不返回 |
| FP-B06（空/0 元素输入防御缺失） | 空/0 元素输入是**回绕路径高发形态**：核 B06 空输入防御时，同步核本条子型③（同一输入、两个后果面） |
| FP-D01（显存/内存过度占用） | 资源泄漏致内存耗尽：D01 管**容量**（申请量推导），本条子型⑤ 管**后果**（耗尽后挂死/闪退） |
| FP-F04（交付面缺失） | 同属「**退出码不可信**」家族：F04 不报错地失败，本条不返回地卡住；实证 #5337 商分未合入（F04 成因⑤）直接表现为用例挂死（后果归本条） |
| FP-E01（golden/UT 期望值失配） | golden/UT 只断言数值时**天然漏检本型**——挂死发生在数值比较之前 |

**症状反查定位**：进程存活、CPU 空转（90%+）或 0% 占用、长时间无输出 → 子型①；`Exit code 124` / Host 线程 3s 超时退出 → 子型③；`vector core execution timed out` / `aic error` → 子型④；多卡随机掉线 / 连接超时 → 子型②；设备内存持续上涨、最终耗尽报错卡死/闪退 → 子型⑤。CI 单用例「**不动**（不是失败）」是本型关键识别特征。

## 1. FP-G01 模式卡摘要（检视依据，源自本库 `patterns/FP-G/FP-G01.md`，v3.1）

- **编号 / 名称**：FP-G01 执行挂死与调度超时（死循环 / 回绕长循环 / 通信等待 / kernel 超时） ｜ **类别**：执行可靠性 ｜ **风险**：高（S4×O3=12）｜ **状态**：活跃
- **适用声明头**（照抄卡片）：仓 All ｜ 侧别 Tiling,Kernel ｜ 载体 Tiling源码,Kernel源码 ｜ 触发 必须触发 ｜ 默认启用 true
- **skill 核查面**：侧别 Tiling,Kernel——落地为 op_host tiling / infershape（子型①③⑤ host 面）、op_kernel（子型④）、tests/ut 框架封装（横切面）；子型② 的通信等待超时主要在通信库 / 框架仓，算子仓仅核同步等待调用点与超时配置项
- **故障机理**：任务**无法完成**——进程存活但永不返回，或被超时强制中断。五种独立成因（与五子型一一对应）：① **迭代求解循环不推进**——host tiling 的 `while(true)` 异常分支不更新推进变量（如 `updateDivRect`）且无「不推进即退出」防护，CPU 空转死循环；② **集合通信与流同步等待超时**——多卡 `rank_table` 无误仍随机初始化连接超时 / rank 掉线，等待时长由 `HCCL_CONNECT_TIMEOUT` / `HCCL_EXEC_TIMEOUT` / `HCCL_RETRY_CNT` / `HCCL_DFS_CONFIG` 决定，缺失或换算错误致等待无界/超时；③ **循环上界由回绕值得出**——rank-0 / 空输入经 `size_t` 下溢回绕成 `SIZE_MAX`，按该上限循环，Host 长时不返回；④ **设备侧执行超时**——kernel 长时不返回，报 `vector core execution timed out` 升级为 `aic error`；⑤ **资源泄漏累积**——申请-释放不成对，长期调用致设备内存耗尽，推向挂死/闪退。另有**横切成因（独立于①~⑤、不单独成子型）：超时机制自身错误/死代码**——溢出检查为**死代码**（`double` 先截断为 `u32`，不可能大于 `UINT32_MAX`），大超时值被截断反而**误超时**，横切于②④ 的超时判定面。**共性：无单用例超时熔断的框架里表现为卡死而非失败。**
- **子型划分（报告卡片标注）**：① 死循环/迭代不推进；② 集合通信与流同步等待超时；③ 循环上界回绕致长循环不返回；④ 设备侧 kernel 超时；⑤ 资源泄漏累积致内存耗尽挂死。（超时机制错误/死代码为横切成因，横切于子型②④ 超时判定面，不单独成子型。）
- **触发条件**：host tiling / infershape 迭代求解循环（`while(true)` / `for(;;)`）遇异常输入或中间状态；整数下溢 / 回绕值用作循环上界；rank-0、空 tensor、退化 shape；分核 / 切分参数不收敛；设备侧大 shape 或异常模板致 kernel 长时占用；超时值配置超 `uint32_t`；长期高频调用累积泄漏；**测试框架缺单用例超时熔断**。
- **典型表现**：同第 0 节「症状反查定位」——进程存活、CPU 空转/0%、长时间无输出、CI 单用例「不动」、`Exit code 124`、`vector core execution timed out` / `aic error`、复现依赖用例执行顺序、设备内存持续上涨。**关键识别特征：日志完全无进展。**
- **实证案例**（详情见第 11 节案例库）：#5032（`PromptFlashAttention_310p_tiling_0` UT 卡死 / CPU 90%+，修复 PR #11411）、#933（NMSWithMask 对 rank-0 输入做 `x - 1` 回绕 `SIZE_MAX` 致长循环，MR `!1571`）、#5337（MoeInitRoutingV4 设备超时 `aic error`）、#567（`hccl_aiv_utils.cc:368-374` 超时溢出检查死代码致误超时）、#141（`BatchSendRecvOutPlace` 异常分支未释放致内存耗尽挂死）、#147（多卡 `rank_table` 无误仍随机连接超时 / rank 掉线）。
- **检测签名**（命中即候选点位）：`while\s*\(\s*(true|1)\s*\)`（**须人工确认循环体是否含推进变量更新与不推进退出**；hccl 实测 9 处）；`for\s*\(\s*;\s*;\s*\)`；`Exit code 124|execution timed out|vector core`；`malloc|new\s` 与多分支 `return` 同现且无统一释放；`setTimeout|SetTimeout|TIME_S_TO_US`。
- **审查关键词**（命中仅表示值得人工审）：`static_cast<size_t>|\(size_t\)` 与 `-` 同现（下溢回绕嫌疑，hccl 实测 31 处，多数正常，须逐个看是否用作循环上界）；`UINT32_MAX|numeric_limits<u32>::max\(\)` 之前的溢出判断（**须人工确认是否死代码**：先截断再比较必然为假；hccl 实测 34 处）。
- **测试拦截建议**：① **单用例超时熔断（最高优先级）**——CI 对每用例设硬超时（如 10 分钟），超时**转失败**并 dump 堆栈；② 断言「**不返回**」而非仅精度；③ UT 执行顺序随机化（顺序依赖的单例污染只在固定顺序下被掩盖）；④ fixture 强制重置全局单例 + 每 tiling 用例显式 `SetSocVersion`；⑤ 边界输入探针——rank-0 / 空 tensor / 退化 shape 单独成类；⑥ 迭代求解循环加**静态门禁**（循环体内须有推进语句与不推进退出）；⑦ 超时配置边界（超 2^32 微秒、负值）与**长稳看护**（设备内存上涨即告警）。
- **关联**：FP-C01、FP-B10（通信超时归本条子型②）、FP-B07、FP-B06、FP-D01（泄漏管后果）、FP-F04（退出码不可信家族）、FP-E01（UT 数值断言漏检本型）——分工见第 0 节。

## 2. 检视输入与算子定位

**输入**：aclnn 接口名（必填，如 `aclnnPromptFlashAttention`）；可选 ref（默认 master）、指定仓（默认自动定位）；可选现象（卡死点 / 超时日志 / 退出码——症状反查定子型）；可选复现条件（arch + quant/mode——子型④ 关键输入）。

**接口名 → 算子目录换算**：去 `aclnn` 前缀 + 驼峰转下划线小写：
`aclnnPromptFlashAttention → prompt_flash_attention`、`aclnnMoeInitRoutingV4 → moe_init_routing_v4`、`aclnnSwiGlu → swi_glu`。

**仓定位顺序**（GitCode `cann`，逐仓用目录列表确认）：`ops-nn`（norm/loss/activation/matmul）→ `ops-math`（math/conversion）→ `ops-cv`（image/vision）→ `ops-transformer`（attention/moe）。**类目名不总与直觉一致**（如 diag_v2 在 `conversion/`），以目录列表为准。FP-G01 高发面：带迭代求解的 tiling（`AdjustC*Tiling` / `AdjustNTiling`）、attention/moe 大模板 kernel、空/退化 shape 语义的 infershape、含动态申请的 op_api 出口。

**算子目录结构约定**（示例 `cann/ops-transformer` → `attention/prompt_flash_attention/`）：

```text
{类别}/{op_name}/
├── op_host/                  # *_def.cpp、*_infershape.cpp、*_tiling*.cpp——子型①②③
│   └── config/<soc>/         # *_binary.json（分核——循环不收敛切分面）
├── op_kernel/                # kernel 模板——子型④
├── op_api/（或 op_host/op_api/）  # aclnn 出口——子型⑤
├── tests/ut/                 # ut 框架与 fixture——横切面（超时熔断 / 单例重置）
└── docs/ CMakeLists.txt
```

## 3. 取数方式（Important）

公开网页端点被拦截，**必须走 API**（均需带 `User-Agent`；失败重试 2 次、间隔 5 秒）：

| 用途 | 端点 |
|---|---|
| 目录列表 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/contents/{path}?ref={ref}` |
| 单文件内容 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/raw/{path}?ref={ref}` |
| Issue 查重 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/issues?q={关键词}` |

**已实测不可用（2026-09）**：`https://gitcode.com/{repo}/raw/{sha}/{path}`、`https://raw.gitcode.com/...` → 403 或拦截页。若本地已有算子仓克隆，优先读本地文件，行号以本地 HEAD 为准并记录 commit。**本模式特有取数限制**：挂死是否发生、CPU 占用、设备内存走势均需**运行时观测**——静态检视产出「缺陷路径 + 复现/排除方案」，不可表述为「必然挂死」。

## 4. 五子型检视清单（每点：查什么 → 何处 → 命中判据）

对 op_host（tiling + infershape）/ op_kernel / op_api / tests/ut 全部相关文件逐点核查，**每点先查命中面、再做反证排除**，防护面（已有退出防护、统一释放）也须记录。

### 子型 ① host 迭代求解循环不推进（死循环）
- 查什么：`while(true)` / `for(;;)` 迭代求解循环（`AdjustC*Tiling` / `AdjustNTiling` 高发）——循环体内**是否更新推进变量**；异常分支是否「**不推进即 `return GRAPH_FAILED`**」，既不置推进变量又不退出 = 空转死循环。何处：op_host tiling / infershape 的求解循环全部分支。命中判据：可写出「异常输入下循环体一轮后状态不变 → 无限重复」推导链（实证 #5032：`CheckArgsLegal` 失败不置 `updateDivRect`、无该分支退出）。

### 子型 ② 集合通信与流同步等待超时（含超时机制自身正确性）
- 查什么：同步 / 等待调用（StreamS 类）与通信路径的**超时配置项**是否可设、换算链是否丢精度/宽度；**超时判定的溢出检查是否可达**——先截断为 `u32` 再比 `UINT32_MAX` 必然为假的**死代码**（实证 hccl #567）；多卡 `HCCL_CONNECT_TIMEOUT` / `HCCL_EXEC_TIMEOUT` / `HCCL_RETRY_CNT` / `HCCL_DFS_CONFIG` 配置面。何处：op_host / op_kernel 的同步等待与超时设置点、`setTimeout|SetTimeout|TIME_S_TO_US` 命中处。命中判据：溢出 / 截断检查不可达可静态证明；换算链存在宽度丢失点且用户配置可超过该宽度。

### 子型 ③ 循环上界由回绕值得出
- 查什么：循环上界**来源类型**——`size_t` / `uint32_t` 减法是否可能回绕（`x - 1` 在 `x == 0` 时回绕 `SIZE_MAX`）；rank-0、空 tensor、退化 shape 是高发形态；`static_cast<size_t>` 与 `-` 同现处逐个确认**是否用作循环上界**（正常转换占绝大多数）。何处：infershape / tiling 的 shape 推导段（实证 #933：InferShape 对 rank-0 输入直接 `x - 1`）。命中判据：给出「输入维度 0 → 上界回绕 `SIZE_MAX` → 按上限循环」的静态反例推导。

### 子型 ④ 设备侧 kernel 执行超时
- 查什么：kernel 在大 shape / 异常模板组合下是否长时占用且**无早退路径**；日志特征 `vector core execution timed out` → `aic error`；复现常为特定组合（实证 #5337：arch35 + quant + mode=0 + fullload）。何处：op_kernel 主循环、早退条件、tilingkey 模板特化组合清单 × binary.json 分核配置。命中判据：静态只能立「无早退路径的超大循环」观察项；与用户实测超时证据合并后方升级命中。

### 子型 ⑤ 资源泄漏累积致内存耗尽
- 查什么：`malloc` / `new` 与多分支 `return` 同现且**无统一释放**——异常分支 `return` 前是否释放；长期高频调用下设备内存持续上涨 → 耗尽 → 卡死/闪退完整链条（实证 hccl #141）。何处：op_api 出口、op_host 的动态申请点。命中判据：存在「申请成功 + 异常分支提前 `return` 未释放」的静态路径。

### 横切面：测试框架与单例污染
- 查什么：框架是否具备**单用例超时熔断**（缺失时挂死表现为「任务不动」，掩盖真实失败点——全库最贵排查成本来源）；全局单例（`PlatformAscendCManager` 类）是否有 **fixture 级重置**、用例是否显式 `SetSocVersion`；用例间是否顺序依赖（实证 #5032 触发依赖 FASG 前置用例单例污染，单独跑不复现）。何处：tests/ut 的框架封装、fixture、用例初始化代码。命中判据：框架无超时参数 / 熔断机制可静态确认；单例无重置点且用例读取其状态。

## 5. 检视流程

1. **定界**：换算 op 目录、确认仓与 ref；按现象（卡死点 / 超时日志 / 退出码）反查优先子型；确认是否提供复现条件（子型④）。
2. **枚举**：列出 op_host（tiling + infershape + config）/ op_kernel / op_api / tests/ut 全部相关文件。
3. **触发词扫描**：按 `while\s*\(\s*(true|1)\s*\)`、`for\s*\(\s*;\s*;\s*\)`、`static_cast<size_t>|\(size_t\)` 与 `-` 同现、`UINT32_MAX`、`malloc|new\s`、`setTimeout|SetTimeout|TIME_S_TO_US` 定位风险面（本地仓 grep；API 模式逐文件拉取后检查）。**「必须触发」：签名零命中时五子型清单仍须逐项核查完毕。**
4. **五子型逐项核查**：每点记录命中面与防护面证据（文件:行号）；循环类签名逐个人工确认推进 / 退出语义，回绕类逐个确认是否用作循环上界。
5. **反证排除**：循环体有推进 + 不推进退出防护、转换不参与上界、释放已由 RAII / 智能指针统一、kernel 有早退路径。
6. **判定**：按第 7 节标准给 命中 / 观察项 / 反证排除。
7. **查重**（仅命中项）：issues API 按接口名 + `卡死|挂死|timeout|timed out|aic error` 检索，比是否同机理；无同机理才立卡。
8. **业务可达性核查**（仅命中项）：判 B 等级、定业务影响类型、给处置建议；默认保守（无法证明不可达即记 B3），降档须附证据；B 不改 S×O。
9. **出报告**：按第 8 节模板落盘；静态结论附复现 / 排除方案（熔断参数、复现用例序列、边界输入探针）。

## 6. 风险定级（S×O）与业务影响评估（B 轴）

- **S**：S4（挂死 / 永不返回——host 空转、回绕长循环、设备超时，任务无法完成）；S3（超时死代码致误超时——任务被错误中断）；S2（异常分支泄漏——渐进累积，需长期调用显）。
- **O**：O3 = ≥2 条独立实证；O2 = 1 条独立实证；O1 = 仅静态扫描命中或团队笔记（实证 = 确认对应 issue / PR，或经跨仓、跨分支核验确认的缺陷记录，同权计入）。静态推演命中且无实证默认 **O1**；升档须在报告给出实证依据。
- **风险 = S×O**：≥6 高；3/4 中；1/2 低。FP-G01 基准：模式卡整体 S4×O3=12（高）；纯静态命中 S4×O1=4（中，暂定，复现实证后复评）。

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

- **签名 / 触发词命中 ≠ 成立**：`while(true)` 在大型仓命中量大（hccl 实测 9 处）多数正常——命中仅为定位提示，须人工确认「循环体含推进变量更新 + 不推进退出」两要素；`size_t` 转换与 `-` 同现（hccl 实测 31 处）多数正常，只核**用作循环上界**者；`UINT32_MAX` 前溢出判断（hccl 实测 34 处）须逐个确认是否死代码。
- **三种判定**：**命中**（可静态证缺陷路径）：「异常分支不推进且不退出」「上界回绕」「溢出检查不可达」「异常分支泄漏」任一推导链完整 + 触发输入静态可构造 → 立 Bug 卡；**观察项**：设备侧超时需实测复现、或回绕依赖运行时输入形态 → 记录并附复现方案，按 S4×O1 暂定；**反证排除**：循环有推进 + 退出防护、转换不参与上界、释放统一、kernel 有早退 → 写出反证理由（防护面证据）。
- **「单独跑不复现」不是反证**：实证 #5032 触发依赖前序用例单例污染——顺序依赖造成的不可复现恰是本型特征；判定须核对 fixture 重置与用例顺序，报告标注复现所需前置用例序列。
- **本型与 C01 的区分以「日志是否推进」为准**：量化耗时结论（慢多少）不属本条；「完全无进展」才立本条卡。
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
- **文件路径与行号证据**：
  - `{文件}:{行号}`：{现象（无推进异常分支 / 回绕表达式 / 死代码溢出检查 / 未释放异常分支）}
  - 防护面记录（反证检查结果）：{文件}:{行号}
- **FP-G01 模式编号**：FP-G01 执行挂死与调度超时（子型①~⑤ + 横切面编号）
- **S×O 风险定级**：S4（挂死）× O1（静态命中无实证）= 4，中（暂定，复现实证后复评）
- **证据等级**：{静态可证 / 需实测确认}｜{一句话理由}
- **业务影响评估（B 轴）**：可达性 B{3|2|1}（{一句话判据}）｜ 业务影响：{静默精度损失/任务失败中断/性能退化/仅可观测性}｜ 证据：{调用方/公开负载/为何不可达}｜ 处置建议：{尽快修/排期修/记录}
- **故障机理推导链**：{异常输入 → 循环状态不变/上界回绕/泄漏累积 → 永不返回 的逐步推导}
- **触发条件可达性分析**：{rank-0 / 空 tensor / 退化 shape / 异常校验输入的具体构造}
- **建议修复方案**：{异常分支不推进即 return GRAPH_FAILED / 上界下限钳制 / 修复溢出检查次序 / 异常分支补释放}
- **测试拦截建议**：单用例超时熔断（转失败 + dump 堆栈）；断言「不返回」；边界输入探针（rank-0/空 tensor/退化 shape 单独成类）；fixture 重置全局单例 + 显式 SetSocVersion
- **Agent 误判记录**：{被推翻的假设 → 推翻证据 `[文件]:[行号] [代码行]`；无则「无」}
- **GitCode 查重**：{issues API 检索结论，无同机理 issue 才立卡}
```

### 检视报告结构

```markdown
# FP-G01 检视报告：{aclnn 接口名}（YYYY-MM-DD）
## 一、执行概览（仓/ref/HEAD、现象与优先子型、文件清单、判定统计：命中 X / 观察项 Y / 反证排除 Z；命中项 B 轴分布 B3×a / B2×b / B1×c）
## 二、命中明细（Bug 卡，按第 8 节字段，每卡含 B 轴业务影响评估）
## 三、观察项（表：# / 子型 / 文件:行号 / 存疑点 / 复现方案）
## 四、反证排除（表：子型点 / 反证理由 / 防护面证据）
## 五、复现与熔断建议（超时熔断参数、前置用例序列、边界输入探针、长稳看护项）
```

> 报告须在「执行概览」标注证据等级分布（静态可证 X / 需实测确认 Y），并在文末单列「Agent 误判记录」小节（无则写「无」）。

报告落盘到当前任务工作区，建议命名 `FP-G01检视_{接口名}_YYYYMMDD.md`。

## 9. 示例速览：aclnnPromptFlashAttention

- **定位**：`cann/ops-transformer` → `attention/prompt_flash_attention/`（op_host：*_def.cpp / *_infershape.cpp / prompt_flash_attention_tiling.cpp + config/<soc>/*_binary.json；op_kernel：多模板变体；tests/ut：含 `PromptFlashAttention_310p_tiling_0`；docs/aclnnPromptFlashAttention.md）。
- **检视面提示**（引导，不预设结论，仍须逐点核查；行号以本地 HEAD 为准）：
  - 子型①：`prompt_flash_attention_tiling.cpp:6028` 起 `AdjustCVTiling`、`:6065` `while (true)`、`:6066` 声明推进变量 `updateDivRect = false`、`:6067` 调 `PromptFlashAttentionCheckArgsLegal`（定义 `:1483`）——核**校验失败分支**是否置位 `updateDivRect` 或直接退出；`:4965` / `:4973` 两处调用点一并核。实证 #5032 即此处失败不置位致空转（CPU 90%+），修复 PR #11411 于 `!updateDivRect` 直接 `return GRAPH_FAILED`——本地若已含该防护，记为防护面证据；
  - 横切面：该实证的触发依赖 FASG 前置用例（`FlashAttentionScoreGrad_tiling_1/2`）单例污染——核查 tests/ut 的 fixture 重置与 `SetSocVersion` 显式性；
  - 子型④：910P/950 各模板的大 shape 组合 × 无早退路径（对照 binary.json 分核）。
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
python3 scripts/scan_fp.py --only FP-G01 --format json <目标文件>  # 签名候选（非结论）
python3 scripts/verify_lines.py <报告.md> --root <被检仓>        # 行号校验
python3 check_fault_patterns.py                                # 全库守门
```

### 工作量与抽样（v4.0）

- **深度档：深度**（索引 `depth` 字段）——全量核查，不抽样。全部映射点 / 分支逐条过；单模式命中 > 50 处时按文件分片，并在报告写明分片口径。
- **报告必填**：抽样口径（全量 / 每点前 N 处 / 每类 N 例）+ 停止点记录；未写口径视为未完成。

## 11. 已知缺陷案例库：触发条件 / 根因 / 修复范式 / 针对性深挖（v5.1）

> 本节把本型**已确认缺陷**拆到「触发条件 → 根因（具体路径）→ 修复范式（✅ 正确代码）→ 针对性发现步骤 → 最小复现锚」的代码级颗粒度。
> 修复范式为**正确形态示意**；路径引用取自卡片实证，行号以被检仓本地 HEAD 为准，**不得臆造**。

### 案例 1｜迭代求解循环异常分支不推进致 CPU 空转死循环 —— ops-transformer #5032（PromptFlashAttention，PR #11411）

- **触发条件**：`PromptFlashAttentionTiling310P` UT（`PromptFlashAttention_310p_tiling_0`）`bash build.sh --PR_UT` 卡死（CPU 空转 90%+）；触发依赖 FASG 前置用例（`FlashAttentionScoreGrad_tiling_1/2`）单例污染，单独跑不复现。
- **根因（具体路径）**：`CheckArgsLegal` 失败且**不置 `updateDivRect`** → `AdjustCVTiling` 的 `while(true)` **无法推进**且无「不推进即退出」防护 → CPU 空转死循环（「死循环 + 无防护 + 无超时熔断」三件套叠加，卡死掩盖真实失败点）。
- **修复范式（✅，示意）**：

```cpp
// ❌ 校验失败不置推进变量、也不退出 → while(true) 空转
while (true) { PromptFlashAttentionCheckArgsLegal(...); /* 无退出 */ ... }
// ✅ 不推进即退出（PR #11411，产品代码 1 行防御修复）
while (true) {
    PromptFlashAttentionCheckArgsLegal(...);
    if (!updateDivRect) { return GRAPH_FAILED; }
    ...
}
```

- **针对性发现（可执行）**：① 搜 `while\s*\(\s*(true|1)\s*\)` / `for\s*\(\s*;\s*;\s*\)`；② 逐循环人工确认**循环体是否含推进变量更新 + 不推进退出**两要素；③ 核 fixture 是否重置全局单例、用例是否显式 `SetSocVersion`。
- **最小复现锚**：复现用例序列 = `FlashAttentionScoreGrad_tiling_1/2` → `PromptFlashAttention_310p_tiling_0`；若本地已含 `!updateDivRect → return GRAPH_FAILED` 防护，记为防护面证据。
- **实证**：#5032（closed），修复 PR #11411；`prompt_flash_attention_tiling.cpp:6028` `AdjustCVTiling`、`:6065` `while (true)`、`:6066` 声明 `updateDivRect = false`、`:6067` 调用校验（定义 `:1483`）、`:4965 / :4973` 两处调用点。

### 案例 2｜rank-0 输入 `size_t` 的 `x - 1` 回绕为 SIZE_MAX 致长循环 —— ops-cv #933（NMSWithMask，MR !1571）

- **触发条件**：experimental `NMSWithMask` InferShape 收到 rank-0（空）输入。
- **根因（具体路径）**：对 rank-0 输入做 `size_t` 的 `x - 1` → **回绕为 `SIZE_MAX`** → 按该上限循环 → Host 线程长时不返回（3s 超时、退出码 124）；同族 6 条（`#946` / `#938` / `#925` / `#923` / `#935` / `#915`）同基线 commit 同日关闭。
- **修复范式（✅，示意）**：

```cpp
// ❌ rank-0 输入直接做 size_t 减法 → 下溢回绕
size_t hi = dim - 1;                 // dim == 0 时 = SIZE_MAX
// ✅ 先判 rank / 零维度，再钳制下限
if (dim == 0) { return GRAPH_FAILED; }
size_t hi = (dim > 0) ? (dim - 1) : 0;
```

- **针对性发现（可执行）**：① 搜 `static_cast<size_t>|\(size_t\)` 与 `-` 同现处，逐个确认**是否用作循环上界**（正常转换占绝大多数）；② 定位 infershape / tiling 的 shape 推导段；③ 边界输入探针：rank-0 / 空 tensor / 退化 shape 单独成类。
- **最小复现锚**：对 `NMSWithMask` 传 rank-0 输入，观察 Host 线程是否长时不返回（`Exit code 124`）。
- **实证**：#933（closed），修复 MR `!1571`。

### 案例 3｜设备侧 kernel 执行超时（vector core timed out → aic error） —— ops-transformer #5337（MoeInitRoutingV4）

- **触发条件**：arch35（Ascend950）+ quant + mode=0（静态量化）+ fullload，**可复现挂死**。
- **根因（具体路径）**：kernel 在该模板组合 + 大 shape 下长时占用且**无早退路径** → 超时报 `vector core execution timed out` 并升级为 `aic error`（设备侧执行超时，子型④）。
- **修复范式（✅，示意）**：为 kernel 主循环增加早退路径 / 拆分模板或调整分核，使单核工作量有界（无真实修复代码来源，仅示意）。
- **针对性发现（可执行）**：① 核 op_kernel 主循环与早退条件；② 列 tilingkey 模板特化组合 × `config/<soc>/*_binary.json` 分核配置；③ 定位「无早退路径的超大循环」观察项，与用户实测超时证据合并后升级命中。
- **最小复现锚**：在 arch35 + quant + mode=0 + fullload 组合下跑，观察日志是否出现 `vector core execution timed out`。
- **实证**：#5337（closed）。

### 案例 4｜超时判定溢出检查是死代码致大超时值被截断误超时 —— cann/hccl #567（`hccl_aiv_utils.cc:368-374`）

- **触发条件**：用户配置的超时值较大（超过 `uint32_t` 可表示范围）。
- **根因（具体路径）**：`timeoutUs = execTimeOut * TIME_S_TO_US`（`double` 先截断为 `u32`）→ 第 369 行再判 `timeoutUs > UINT32_MAX` **必然为假**（死代码）→ 大超时值被截断，反而**误超时**；横切于子型②④ 的超时判定面。
- **修复范式（✅，示意）**：

```cpp
// ❌ double 已截断为 u32，再判 > UINT32_MAX 必然为假（死代码）
u32 timeoutUs = execTimeOut * TIME_S_TO_US;
if (timeoutUs > UINT32_MAX) { /* 不可达 */ }
// ✅ 先用宽类型判溢出，再安全转换
double timeoutUsD = static_cast<double>(execTimeOut) * TIME_S_TO_US;
if (timeoutUsD > static_cast<double>(UINT32_MAX)) { /* 报错 / 夹取 */ }
u32 timeoutUs = static_cast<u32>(timeoutUsD);
```

- **针对性发现（可执行）**：① 搜 `setTimeout|SetTimeout|TIME_S_TO_US`；② 核 `UINT32_MAX|numeric_limits<u32>::max()` 之前的溢出判断是否**先截断再比较**（必然为假 = 死代码）；③ 核超时换算链是否存在宽度丢失点。
- **最小复现锚**：配置超时值 > 2^32 微秒，观察是否被截断为小值而误超时。
- **实证**：#567（closed）；`src/ops/op_common/template/aiv/hccl_aiv_utils.cc:368-374` `GetAivTimeout`。

### 案例 5｜动态申请异常分支未释放、累积致内存耗尽后挂死 —— cann/hccl #141（`BatchSendRecvOutPlace`）

- **触发条件**：长期高频调用（累积型，子型⑤）。
- **根因（具体路径）**：动态申请堆内存后**异常分支未释放** → 设备内存随调用次数上涨 → **最终耗尽报错、任务卡死 / 闪退**（资源泄漏 → 挂死完整链条）；D01 管容量，本条管后果。
- **修复范式（✅，示意）**：

```cpp
// ❌ 异常分支提前 return 未释放
auto* buf = new Buffer(...);
if (err) { return ERR; }        // 泄漏
delete buf;
// ✅ 异常分支补释放 / 用 RAII 统一回收
auto buf = std::make_unique<Buffer>(...);
if (err) { return ERR; }        // 自动释放
```

- **针对性发现（可执行）**：① 搜 `malloc|new\s` 与多分支 `return` 同现且无统一释放；② 核申请-释放是否成对、异常分支 `return` 前是否释放；③ 长稳看护（设备内存持续上涨即告警）。
- **最小复现锚**：循环高频调用 `BatchSendRecvOutPlace`，观测设备内存是否持续上涨至耗尽。
- **实证**：#141（closed）。

### 案例 6｜多卡通信初始化连接超时 / rank 掉线（配置面） —— cann/hccl #147

- **触发条件**：多卡分布式训练，`rank_table` 配置无误仍**随机**出现初始化连接超时、个别 rank 掉线。
- **根因（具体路径）**：等待时长由超时 / 重传配置项决定——`HCCL_CONNECT_TIMEOUT`（建链超时）/ `HCCL_EXEC_TIMEOUT`（执行超时）/ `HCCL_RETRY_CNT` / `HCCL_DFS_CONFIG`；配置缺失或换算错误 → 等待无界 / 超时（子型②）。
- **修复范式（✅，示意）**：确保超时 / 重传配置项可设且换算链无宽度丢失，等待有界（无真实修复代码来源，仅示意）。
- **针对性发现（可执行）**：① 核算子内同步 / 等待调用点与超时配置项；② 核换算链是否丢精度 / 宽度；③ 结合横切面核超时判定是否死代码（对照案例 4）。
- **最小复现锚**：多卡场景重跑并采集 `HCCL_*_TIMEOUT` 取值，观察是否随机掉线。
- **实证**：#147（closed）。

### 语料基线与深挖起手式

```bash
python3 scripts/scan_fp.py --only FP-G01 --format json <目标文件>
# F5 指纹（无退出条件循环）2026-09-07 日报四仓命中 36 处：ops-transformer 28 / ops-nn 5 / ops-math 2 / ops-cv 1
```

## 12. 判据层（L2/L3）：出用例与判读前必读 <!-- BEGIN DETECT-SECTION (generated by scripts/sync_detect_section.py; do not edit) -->

> 生成物，勿手改（C42 校验）。完整判据见 [references/detect-l2-l3.md](references/detect-l2-l3.md)。

- **L2**：轴 shape 维度/并发/同步｜观测 watchdog｜至少 3 例
- **L3 `watchdog`**：K1061(静默漏判)子进程超时口径大于外层预算 → 子进程白跑、结果不落盘

> 判 FAIL 先排「假 FAIL」、判 PASS 先排「假 PASS/假绿」。**不查 L3 就出结论 = 报告作废。** <!-- END DETECT-SECTION -->
