---
name: "fpf01-build-review"
description: "基于 FP-F01「构建/工程配置不一致致编译与产物缺陷」故障模式对算子构建配置做检视：定位 CMakeLists/build.sh/def/binary.json，按跨仓原型重复、去重宏缺失、include 路径不一致、def 注册而 binary.json 缺失、SoC 列表双源、别名 fallback 六成因核查并定级。当用户遇编译失败、产物缺失、REG_OP 重复注册时使用。"
---

# FP-F01 构建配置检视（fpf01-build-review）

对用户指定的算子 / 构建目标 / 仓做 FP-F01 专项构建配置检视：先定位构建体系（CMakeLists、build.sh、def 注册面、binary.json、样例与头文件引用），再按六成因清单逐项核查，每个结论给出**文件 + 行号 + 推导链**证据，命中即出 Bug 卡，输出检视报告。**本模式特殊纪律：① 本型的失败多为**静默**——`if(EXISTS)` 静默 `continue()`、SoC 校验通过而 CMake 不识别、别名表缺失静默 fallback，构建退出码常为 0，仅查顶层退出码永远查不出本型；② 检视动作是**多源清单差集**（def × binary.json、build.sh × CMake 的 SoC 列表、跨仓同名原型），不是单文件走查；③ 「配置了但产物静默跳过」与「编译/链接失败」同族，须同时核查。**

## 0. 与相邻模式的边界

| 相邻模式 | 分工 |
|---|---|
| FP-F04（交付面缺失） | **共用同一套 def × binary.json 门禁但断言方向相反**：F01 断言「**注册了就必须有产物**」（配置不一致致编译/链接失败或产物静默跳过）；F04 断言「**产物里必须有符号**」（交付清单缺失致接口不可用）。缺口方向相反，门禁可合并实现 |
| FP-F02（维测/错误上报缺陷） | 配置缺失的**静默表现**属「无告警/告警不足」家族——F01 管配置面差集，F02 管告警与错误码面 |
| FP-F03（文档/声明面与实现面不一致） | 支持声明 vs binary.json 产物面同源：F01 管**产物面**（编译与打包），F03 管**文档声明面**（README/支持矩阵 vs def 注册） |
| FP-B02（SOC 适配遗漏） | SoC 适配遗漏在 **tiling 侧**的姊妹型；F01 是 SoC 列表/注册/构建侧的遗漏 |
| FP-G01 / FP-F04 | 同属「退出码不可信」家族：F01 静默跳过产物，F04 不报错地失败，G01 不返回地卡住 |

**症状反查定位**：`fatal error: xxx.h: No such file or directory` 批量编译失败 → 成因③；重复注册/符号冲突链接错误 → 成因①②；`--soc=X` 校验通过但 CMake 阶段失败 → 成因⑤；算子在声明支持的平台上**无产物且构建无报错**（静默跳过）→ 成因④；自动评测用错误平台基线计分且仅一条 WARNING → 成因⑥。

## 1. FP-F01 模式卡摘要（检视依据，源自本库 `patterns/FP-F/FP-F01.md`，v3.1）

- **编号 / 名称**：FP-F01 构建/工程配置不一致致编译与产物缺陷 ｜ **类别**：工程/交付 ｜ **风险**：高（S2×O3=6）｜ **状态**：活跃
- **适用声明头**（照抄卡片）：仓 All ｜ 侧别 All ｜ 载体 构建配置与日志 ｜ 触发 CMakeLists|REG_OP|AddConfig|build.sh ｜ 默认启用 true
- **skill 核查面**：载体为构建配置与日志——skill 落地为六类构建面文件：`op_host/*_def.cpp`（`REG_OP` / `AddConfig` 注册面）、`op_host/config/<soc>/*_binary.json`（产物配置面）、`CMakeLists.txt` 与 `cmake/*.cmake`（编译/打包逻辑）、`build.sh`（SoC 校验与 include 路径）、`op_graph/*_proto*.h`（原型注册与去重宏）、`examples/` 与 `docs/`（样例头文件引用）；构建日志由用户提供后纳入核查
- **故障机理**：构建体系中的**双源/多源配置不一致**与**配置面缺失**，使编译期/链接期失败或产物静默缺失。六种独立成因：① **原型跨仓重复定义**——同一 `REG_OP` 在两仓头文件并存，同编译单元包含即重复注册符号链接冲突；② **注册块缺独立去重宏**——仅靠头文件级 include guard，多包含路径下 `REG_OP` 多次展开；③ **构建脚本 include 路径与头文件实际位置不一致**、**样例引用已废弃头文件**——批量 example 编译失败；④ **def 已注册而 binary.json 配置缺失**——cmake 以 `if(EXISTS)` 为门槛静默 `continue`，kernel 不进编译打包，且退化为按算子名推断 op_type 弱化注册绑定；⑤ **SoC/架构列表双处维护不一致**——build.sh 校验通过而 CMake 侧不识别、或编译器分支硬编码架构锁死无法出其他 SoC 产物；⑥ **评测平台别名表缺失时静默 fallback**——用错误平台基线计分且仅一条 WARNING。**共性：配置不一致而构建不报错、或只打 WARNING 仍继续。**
- **触发条件**：跨仓编译（同时依赖多仓头文件）、新增 SoC/编译器分支、CANN 包裁剪后样例引用失效头文件、算子新增平台注册漏配置文件、双源列表（脚本/CMake）独立演化。
- **典型表现**：`fatal error: xxx.h: No such file or directory` 批量编译失败；重复注册/符号冲突链接错误；`--soc=X` 校验通过但 CMake 阶段失败；算子在声明支持的平台上无产物且构建无报错（静默跳过）。
- **源码审查映射点**：`REG_OP` 注册块是否带独立 `#ifndef/#define` 去重宏；跨仓同名原型归属唯一性；build.sh/CMakeLists 的 SoC 列表、include 路径单一来源；`op_host/config/<soc>/*_binary.json` 与 def 中 `AddConfig("<soc>")` 一一对应；fallback 分支是否有告警升级/失败出口。
- **检测签名**：`grep -rn "REG_OP\(" 多仓同名比对`；`AddConfig\(\"([a-z0-9_]+)\"` 与 `op_host/config/` 目录清单差集；`if\s*\(\s*EXISTS[^)]*binary\.json`（静默跳过点）；build.sh 与 CMake 中 SOC 列表双源比对。
- **测试拦截建议**：CI 增加「def 注册 soc × binary.json 存在性」一致性门禁（缺失即失败而非跳过）；跨仓原型符号冲突用联合编译冒烟捕获；SoC 列表收敛单一源；样例头文件引用随 CANN 包变更批量静态扫描；fallback 必须可配置升级为 FAIL。
- **实证案例**：ops-nn **#5469**（closed）`REG_OP(Rsqrt)` 同时存在于 ops-math `rsqrt_proto.h` 与 ops-nn `op_nn_proto_extend.h`，同编译单元包含即链接符号冲突（PR #9693 迁移 stub 修复）；ops-math **#2886**（closed）AbsGrad/ComplexAbs/Rsqrt proto 缺 `OPS_PROTO_DEF_*` 去重宏致重复注册风险（PR #5096）、**#3036** 同根因；ops-math **#1821**（closed）build.sh `INC_INCLUDE_PATH` 指向 `op_proto/inc` 而 `experiment_ops.h` 在 `op_graph/inc`，114 个 graph 模式 example 编译失败、**#3157**（open）68 个样例引用商发 cann 包已不存在的 `experiment_ops.h` 批量编译失败；ops-nn **#4483**（closed）4 算子 def 已 `AddConfig("ascend950")` 而 `ascend950/*_binary.json` 缺失，`custom_kernel.cmake` 以 `if(EXISTS)` 静默 `continue` 致 950 kernel 不进编译打包、ut.cmake 退化为按名推断 op_type；ops-cv **#405**（closed）build.sh `SUPPORT_COMPUTE_UNIT_SHORT` 含 `ascend910_55` 而 CMakeLists `ASCEND_ALL_COMPUTE_UNIT` 无，校验通过 CMake 编译失败、**#408** 同文件 CORE_NUMS 死代码与 `ascedn910_93` 拼写错误；ops-collections **#28**（closed）bisheng 编译器分支硬编码 `--npu-arch=dav-3510` 锁死架构，非 950 目标静默编出错误架构产物；cann-bench **#63**（open）`PLATFORM_ALIAS` 无 910b3 映射，自动评测静默 fallback 到 910b2 基线计分失真。
- **关联**：FP-F02（配置缺失的静默表现属「无告警/告警不足」）、FP-B02（SOC 适配遗漏在 tiling 侧的姊妹型）、FP-F03（声明面与产物面不一致）、FP-F04（门禁方向相反）。

## 2. 检视输入与检视对象定位

**输入**：算子名 / 构建目标 / 仓名（必填，如 `Rsqrt`、`ops-nn` 的 950 构建目标）；可选 ref（默认 master）、目标 SoC/架构（如 ascend950、ascend910_55）、编译器分支（bisheng 等）；可选**构建日志**（用户提供，静态检视无法自取——`fatal error`、`undefined symbol`、WARNING 行）；可选**样例目录 / CANN 包版本**（成因③ 的引用失效面）。

**算子名 → 目录换算**：去 `aclnn` 前缀 + 驼峰转下划线小写；`Rsqrt → rsqrt`、`AbsGrad → abs_grad`。

**仓定位顺序**（GitCode `cann` 组织，逐仓用目录列表确认）：`ops-nn`（matmul/norm/loss/activation 类）→ `ops-math`（math/conversion 类）→ `ops-cv`（image/vision 类）→ `ops-transformer`（attention/moe 类）；实证来源另含 `ops-collections`（编译器分支）、`cann-bench`（平台别名表）。**跨仓原型核查**：命中 `REG_OP` 同名后须在多仓同时定位（如 Rsqrt 同时在 ops-math 与 ops-nn）。**类目名不总与直觉一致**，以目录列表为准。

**构建配置面结构约定**（示例 `cann/ops-nn`）：

```text
{repo}/
├── build.sh                      # SoC 校验列表、include 路径（成因③⑤）
├── CMakeLists.txt、cmake/*.cmake # 编译/打包逻辑（成因④⑤，如 cmake/custom_kernel.cmake）
├── {类别}/{op_name}/
│   ├── op_host/{op}_def.cpp      # REG_OP / AddConfig("<soc>") 注册面（成因①②④）
│   ├── op_host/config/<soc>/{op}_binary.json   # 产物配置面（与 def 差集，成因④）
│   └── op_graph/*_proto*.h       # 原型注册与 OPS_PROTO_DEF_* 去重宏（成因①②）
├── common/inc/op_graph/*_proto_extend.h   # 跨仓同名原型高发面（成因①）
└── examples/                     # 样例头文件引用（成因③）
```

## 3. 取数方式（Important）

公开网页端点被拦截，**必须走 API**（均需带 `User-Agent`；失败重试 2 次、间隔 5 秒）：

| 用途 | 端点 |
|---|---|
| 目录列表 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/contents/{path}?ref={ref}` |
| 单文件内容 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/raw/{path}?ref={ref}` |
| Issue 查重 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/issues?q={关键词}` |

**已实测不可用（截至 2026-09 实测）**：`https://gitcode.com/{repo}/raw/{sha}/{path}`、`https://raw.gitcode.com/...` → 403 或拦截页；端点策略如有变化可复测。若本地已有算子仓克隆，优先直接读本地文件，行号证据以本地 HEAD 为准并记录 commit。**本模式特有取数限制**：实际编译/链接结果与产物清单**需构建日志或产物实测**——静态检视产出「配置差集 + 静默跳过点」，由日志/产物才能从「嫌疑」升级为「实证命中」；skill 默认产出「差集嫌疑点 + 验证命令（构建命令 / 日志正则）」。

## 4. 六成因检视清单（每点：查什么 → 何处 → 命中判据）

对六类构建面文件逐点核查，**每点先做差集、再做反证排除**；配置正确的面也要记录（作为反证依据）。

### 成因① 原型跨仓重复定义
- 查什么：`REG_OP(<Op>)` 同名是否在**多仓**头文件并存（实证 #5469：`REG_OP(Rsqrt)` 同时在 ops-math `rsqrt_proto.h` 与 ops-nn `op_nn_proto_extend.h`）；同编译单元是否会同时包含两处 → 重复注册符号链接冲突。
- 何处：各仓 `op_graph/*_proto*.h`、`common/inc/op_graph/*_proto_extend.h` 的 `REG_OP` 全量清单（跨仓比对）。
- 命中判据：跨仓同名 `REG_OP` 清单非空且存在同一编译单元包含路径 ⇒ 命中；反证：其一为 stub / 条件编译隔离（须读出隔离宏）。

### 成因② 注册块缺独立去重宏
- 查什么：`REG_OP` 注册块是否带独立 `#ifndef/#define` 去重宏（`OPS_PROTO_DEF_*` 类）——仅靠头文件级 include guard，多包含路径下 `REG_OP` 会多次展开（实证 ops-math #2886/#3036：AbsGrad/ComplexAbs/Rsqrt proto 缺去重宏）。
- 何处：`op_graph/*_proto*.h` 的注册块头部宏。
- 命中判据：注册块无独立去重宏且存在多路径包含 ⇒ 命中。

### 成因③ 构建脚本 include 路径不一致 / 样例引用废弃头文件
- 查什么：build.sh / CMake 的 `INC_INCLUDE_PATH` 等 include 路径与头文件**实际位置**是否一致（实证 ops-math #1821：路径指 `op_proto/inc` 而 `experiment_ops.h` 在 `op_graph/inc`）；`examples/` 引用的头文件在**当前 CANN 包**中是否仍存在（实证 #3157：68 个样例引用商发包已不存在的 `experiment_ops.h`）。
- 何处：`build.sh` 的 include 路径变量、`CMakeLists.txt` 的 `include_directories`、`examples/**` 的 `#include` 全量清单 × 头文件实际位置。
- 命中判据：路径指向与实际位置差集非空，或样例引用头文件在目标包/仓中查无 ⇒ 命中（附批量编译失败日志更佳）。

### 成因④ def 已注册而 binary.json 配置缺失
- 查什么：`{op}_def.cpp` 中 `AddConfig("<soc>")` 的 SoC 集合 × `op_host/config/<soc>/{op}_binary.json` 的**存在性差集**；cmake 是否以 `if(EXISTS)` 静默 `continue()` 跳过（实证 #4483：`custom_kernel.cmake` 的 `if(EXISTS ${binary_json})` + `continue()`，致 950 kernel 不进编译打包，并退化为 `get_op_type_from_binary_json` 按名推断 op_type）。
- 何处：`{op}_def.cpp` 的 `AddConfig` 清单、`op_host/config/<soc>/` 目录清单、`cmake/*.cmake`（如 `custom_kernel.cmake`）的 `if(EXISTS)` 分支。
- 命中判据：`AddConfig` 声明的 SoC 无对应 binary.json（差集非空）⇒ 命中；**静默跳过点**（`if(EXISTS)` 无 else/告警升级）单独记录为横切面证据。

### 成因⑤ SoC/架构列表双处维护不一致
- 查什么：`build.sh` 的 SoC 列表（如 `SUPPORT_COMPUTE_UNIT_SHORT`）与 CMakeLists 的列表（如 `ASCEND_ALL_COMPUTE_UNIT`）**双源比对**（实证 ops-cv #405：build.sh 含 `ascend910_55` 而 CMakeLists 无，校验通过 CMake 失败）；编译器分支是否**硬编码架构**锁死（实证 ops-collections #28：bisheng 分支硬编码 `--npu-arch=dav-3510`）；同文件死代码与拼写错误（实证 #408：CORE_NUMS 死代码、`ascedn910_93` 拼写错误）。
- 何处：`build.sh` 的 SoC/架构变量、`CMakeLists.txt` 的 SoC 列表、编译器分支的 `--npu-arch` 参数。
- 命中判据：两处 SoC 列表差集非空，或架构硬编码致非目标 SoC 静默编出错误产物 ⇒ 命中。

### 成因⑥ 评测平台别名表缺失时静默 fallback
- 查什么：平台别名表（如 `PLATFORM_ALIAS`）是否覆盖目标平台（实证 cann-bench #63：无 910b3 映射 → 静默 fallback 到 910b2 基线）；fallback 分支是否有**告警升级/失败出口**（仅一条 WARNING 仍继续 = 静默失真）。
- 何处：平台别名/基线映射表、fallback 分支代码。
- 命中判据：目标平台在别名表中查无 + fallback 静默继续 ⇒ 命中。

### 横切面：构建静默成功 / 静默跳过
- 查什么：构建门禁只看退出码的盲区——`if(EXISTS)` 静默 `continue()`（成因④）、SoC 校验通过但 CMake 不识别（成因⑤）、别名 fallback 仅 WARNING（成因⑥）均使**构建退出码为 0 而产物缺失/失真**。
- 何处：`cmake/*.cmake` 的跳过分支、`build.sh` 的校验分支、构建日志（若用户提供）。
- 命中判据：静默跳过/降级分支无告警升级且退出码仍为 0 ⇒ 该证据同时提升对应成因的判定置信度。

## 5. 检视流程

1. **定界**：换算算子/构建目标，确认所在仓与 ref、目标 SoC/架构、编译器分支；确认构建日志是否提供（决定成因①④⑤ 能否升级为实证）；跨仓同名原型是否需多仓定位。
2. **枚举**：列出六类构建面文件清单（build.sh / CMakeLists 与 cmake / def / binary.json / proto 头文件 / examples），产出文件清单。
3. **触发词扫描**：按 `REG_OP\(`、`AddConfig\(`、`if\s*\(\s*EXISTS[^)]*binary\.json`、`SUPPORT_COMPUTE_UNIT|ASCEND_ALL_COMPUTE_UNIT|npu-arch|PLATFORM_ALIAS|INC_INCLUDE_PATH` 定位风险面（本地仓用 grep；API 模式逐文件拉取后检查）。
4. **六成因差集核查**：每点记录命中面与防护面证据（文件:行号）；成因① 跨仓比对、成因④ def × binary.json 双向差集、成因⑤ build.sh × CMake 双源比对。
5. **反证排除**：stub/条件编译隔离、注册在别处完成、选择性打包属预期、SoC 差异属预期裁剪、样例头文件由外部包提供 → 明确写出反证理由。
6. **判定**：按第 7 节标准给出 命中 / 观察项 / 反证排除。
7. **GitCode 查重**（仅命中项）：issues API 按算子名/文件 + `编译|链接|REG_OP|AddConfig|binary.json|soc|arch` 检索，逐条比对是否同机理；无同机理才立卡。
8. **业务可达性核查**（仅命中项）：判 B 等级、定业务影响类型、给处置建议；默认保守（无法证明不可达即记 B3），降档须附证据；B 不改 S×O 档位。
9. **出报告**：按第 8 节模板落盘；静态差集结论标注「需构建/日志确认」并附验证命令（构建命令、日志正则断言）。

## 6. 风险定级（S×O）与业务影响评估（B 轴）

- **S**：S2（编译/链接失败致构建中断，或产物静默缺失致平台能力缺失）；S1 仅当影响面局限于样例/单平台且已有绕行。
- **O**：O3 = ≥2 条独立实证；O2 = 1 条独立实证；O1 = 仅静态扫描命中或团队笔记（实证 = 确认对应的 issue / PR，或经跨仓、跨分支核验确认的缺陷记录，同权计入）。静态推演命中且无实证默认 **O1**；升档须在报告中给出实证依据。
- **风险 = S×O**：≥6 高；3/4 中；1/2 低。FP-F01 基准：模式卡整体 S2×O3=6（高）；纯静态命中 S2×O1=2（低，差集嫌疑待构建/日志升级）。

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

- **差集必须双向**：成因④ 要同时查「def 注册了没产物」（F01 方向）与「产物里没符号」（F04 方向）；成因⑤ 要同时比 build.sh 与 CMake 两个列表——单向扫描会漏。
- **三种判定**：
  - **命中**（可静态证差集或已有日志证据）：差集可静态指认 + 触发路径可达（目标 SoC/构建目标下确实会走到），或用户提供了 `fatal error` / 符号冲突日志 → 立 Bug 卡；
  - **观察项**：差集依赖构建产物/日志才能确认、或选择性打包属预期 → 记录并附验证命令，按 S2×O1 暂定；
  - **反证排除**：stub/条件编译隔离、注册在别处完成、SoC 差异属预期裁剪、样例头文件由外部包提供 → 明确写出反证理由。
- **静默跳过与合法跳过区分**：判据是「该配置**本应存在**而缺失」且跳过分支无告警升级，不是「存在跳过逻辑」本身。
- **不臆造清单内容**：差集两边都必须实际读取（`AddConfig` 清单、config 目录、build.sh 与 CMake 列表），引用具体文件与行号；历史 issue 时点的行号（如 #1821 的 `INC_INCLUDE_PATH`、#405 的 `ascend910_55`）与当前 HEAD 漂移时须注明「历史形态，以本地 HEAD 复核」。
- **构建日志不可自取时**：所有运行时构建结论标注「静态差集，需构建/日志确认」，并附验证命令。

### 判定纪律补充（v3.6）：非对称增减、证据等级与误判记录

**增减不对称**：允许追加候选（有据即可，错了可由用户排除）；**撤销或否决候选必须附 `[文件]:[行号] [代码行]` 负向证据**。无证据的「看起来没问题」一律记为「未核查」，不得计入反证排除，也不得据此下调等级——否决造成的漏报用户不可见、不可恢复。

- **证据等级**（Bug 卡必填）：`静态可证` = 推导链完整且触发输入可静态构造；`需实测确认` = 依赖运行时输入规模、设备行为或环境差异。标 `需实测确认` 的条目**不得以「命中」名义出卡**，按观察项记录并附实测用例。
- **Agent 误判记录**（Bug 卡必填）：本次被推翻的假设、推翻它的证据（`[文件]:[行号] [代码行]` 或实测输出）、判定标准是否随之修订；无推翻写「无」。
- **误判回流**：同类误判在 3 次检视中重复出现，登记至 `cases/misjudgments.jsonl`（字段见 `cases/README.md`），并在本模式判定标准中新增对应防线；守门 C19d 校验台账字段合法。

## 8. 产出模板

### Bug 卡字段（命中项必备）

```markdown
### BUG-YYYYMMDD-XX {算子/构建目标}（{仓}，{新增/存量}）
- **检视对象**：{build.sh / CMakeLists / cmake/*.cmake / {op}_def.cpp / config/<soc> / *_proto.h / examples}
- **文件路径与行号证据**：
  - `{文件}:{行号}`：{现象（跨仓重复 REG_OP / 缺去重宏 / include 路径不一致 / def 有 binary.json 无 / SoC 列表差集 / 架构硬编码 / 别名缺失 fallback）}
  - 对照面（应配置而未配置的旁证 / 静默跳过点）：{文件}:{行号}
- **FP-F01 模式编号**：FP-F01 构建配置不一致（成因①~⑥ + 横切面编号）
- **S×O 风险定级**：S2（构建/产物缺陷）× O1（静态差集无实测）= 2，低（暂定，构建/日志后复评）
- **证据等级**：{静态可证 / 需实测确认}｜{一句话理由}
- **业务影响评估（B 轴）**：可达性 B{3|2|1}（{一句话判据}）｜ 业务影响：{静默精度损失/任务失败中断/性能退化/仅可观测性}｜ 证据：{调用方/公开负载/为何不可达}｜ 处置建议：{尽快修/排期修/记录}
- **故障机理推导链**：{配置差集 → 编译/链接失败或静默跳过 → 产物缺失 的推导}
- **触发条件可达性分析**：{目标 SoC / 构建目标 / CANN 包版本}。{静态差集/已有日志证据}
- **建议修复方案**：{补去重宏 / 收敛 SoC 单一源 / 补 binary.json / 修 include 路径 / 移除硬编码架构 / fallback 升级为 FAIL}
- **测试拦截建议**：CI 加「def 注册 soc × binary.json 存在性」门禁（缺失即 FAIL）；跨仓原型符号冲突联合编译冒烟；SoC 列表单一源；样例头文件引用批量静态扫描；fallback 可配置升级为 FAIL
- **Agent 误判记录**：{被推翻的假设 → 推翻证据 `[文件]:[行号] [代码行]`；无则「无」}
- **GitCode 查重**：{issues API 检索结论，无同机理 issue 才立卡}
```

### 检视报告结构

```markdown
# FP-F01 检视报告：{算子/构建目标}（YYYY-MM-DD）
## 一、执行概览（仓/ref/HEAD、目标 SoC/构建目标、六类构建面文件清单、判定统计：命中 X / 观察项 Y / 反证排除 Z；命中项 B 轴分布 B3×a / B2×b / B1×c）
## 二、命中明细（Bug 卡，按第 8 节字段，每卡含 B 轴业务影响评估）
## 三、观察项（表：# / 成因 / 文件:行号 / 差集缺口 / 验证命令）
## 四、反证排除（表：成因点 / 反证理由）
## 五、门禁建议（def×binary.json 双向差集接入点、跨仓原型符号冲突冒烟、SoC 单一源、样例头文件扫描）
```

> 报告须在「执行概览」标注证据等级分布（静态可证 X / 需实测确认 Y），并在文末单列「Agent 误判记录」小节（无则写「无」）。

报告落盘到当前任务工作区，建议命名 `FP-F01检视_{算子或构建目标}_YYYYMMDD.md`。

## 9. 示例速览：REG_OP(Rsqrt) 跨仓重复与 def×binary.json 差集

- **定位**：`cann/ops-nn` → `common/inc/op_graph/op_nn_proto_extend.h`（`REG_OP(Rsqrt)` 跨仓重复面，成因①）与 `cmake/custom_kernel.cmake`（`if(EXISTS)` 静默跳过点，成因④）；`cann/ops-math` → `math/rsqrt/op_graph/rsqrt_proto.h`（同名原型另一侧）、`build.sh`（include 路径，成因③）；`cann/ops-cv` → `build.sh`（SoC 列表双源，成因⑤）；`cann/ops-collections` → bisheng 分支（架构硬编码，成因⑤）；`cann/cann-bench` → `PLATFORM_ALIAS`（别名表，成因⑥）。
- **检视面提示**（引导，不预设结论，仍须逐点核查；行号以本地 HEAD 为准）：
  - 成因①：`op_nn_proto_extend.h` 与 `rsqrt_proto.h` 的 `REG_OP(Rsqrt)` 跨仓同名比对，核同一编译单元是否同时包含（实证 #5469：链接符号冲突，PR #9693 迁移 stub 修复）；
  - 成因②：`rsqrt_proto.h` / AbsGrad / ComplexAbs 注册块是否带 `OPS_PROTO_DEF_*` 去重宏（实证 ops-math #2886/#3036）；
  - 成因④：`cmake/custom_kernel.cmake:18` `if(EXISTS ${binary_json})` → `:21` `continue()` → `:23` `get_op_type_from_binary_json`（按名推断 op_type）——核 def `AddConfig("ascend950")` × `op_host/config/ascend950/` 存在性差集（实证 #4483：950 kernel 静默不进编译打包）；
  - 成因③：`build.sh` include 路径 × `experiment_ops.h` 实际位置（实证 #1821/#3157，历史形态以本地 HEAD 复核）；
  - 成因⑤：`build.sh` 的 SoC 列表 × `CMakeLists.txt` 的 SoC 列表双向比对（实证 ops-cv #405/#408、ops-collections #28）。
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
python3 scripts/scan_fp.py --only FP-F01 --format json <目标文件>  # 签名候选（非结论）
python3 scripts/verify_lines.py <报告.md> --root <被检仓>        # 行号校验
python3 check_fault_patterns.py                                # 全库守门
```

### 工作量与抽样（v4.0）

- **深度档：标准**（索引 `depth` 字段）——每映射点取前 20 处命中；同一映射点连续 20 处反证排除即停止该点并记录。报告须写「抽样口径：每点前 20 处」。
- **报告必填**：抽样口径（全量 / 每点前 N 处 / 每类 N 例）+ 停止点记录；未写口径视为未完成。
