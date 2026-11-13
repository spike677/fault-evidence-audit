---
name: "fpa22-dtype-dispatch-review"
description: "基于 FP-A22「kernel dtype 分派/模板映射错配」对指定算子做 dtype 派发检视：核对 dtype→模板/TilingKey 映射表与 def.cpp 支持集差集、各模板输出循环上界、bool/无符号特化语义，并用 dtype 全组合 + 魔数预填实测。当用户给出算子名要求查特定 dtype 结果错、部分输出未写、掩码错位或同宽度兄弟 dtype 表现分裂时使用。"
---

# FP-A22 dtype 分派映射检视（fpa22-dtype-dispatch-review）

对用户指定的算子做 FP-A22 专项源码检视：先建立「受支持 dtype 全集」，再把它与 kernel 的 `dtype → 模板 / TilingKey` 映射表做**差集**，逐模板核对输出循环上界与类型语义，最后给出 dtype 全组合实测方案。**本模式特殊纪律：① 本型命中的是「派发表条目错配」，不是「数值近似差一点」——任何输入只要落到该 dtype 就必现，不随 shape 波动；② 单 dtype 用例天然看不出来，必须做同宽度兄弟 dtype 对照（`int32` vs `uint32`、`int64` vs `uint64`）才能排除「按字节宽度搬运」的单一解释；③ 撤否必须有负向证据，见第 7 节。**

## 0. 与相邻模式的边界

| 模式 | 它管什么 | 本模式不管的部分 |
|---|---|---|
| FP-A19 多 tiling 路径覆盖盲区 | 新注册的模板从没被测试执行到 | 派发表本身缺条目 / 指错模板——归本模式 |
| FP-B01 支持面校验过严 | 合法 dtype 在**校验层**被误拦截 | 已放行、执行后算错——归本模式 |
| FP-B07 索引/偏移计算错误 | 下标、stride、偏移算错致越界 | 现象可能是「部分未写」，但根因是派发表而非偏移——归本模式 |
| FP-A05 脏数据/数据踩踏 | 结果层读到脏值 | 本模式给出可判定的 dtype 派发机理，A05 是其结果面之一 |
| FP-B12 早退不写输出 | `IsEmpty()` 早退不写非空输出 | 无早退、返回成功但只写部分元素——机理归本模式（B12-2 只记结果面） |

判不清时按「**缺陷的根因所在层**」归属：路径没测到→A19；校验层拦错→B01；下标算错→B07；**dtype 与模板对不上→本模式**。

## 1. FP-A22 模式卡摘要（检视依据，源自本库 `patterns/FP-A/FP-A22.md`，v6.13）

- **编号 / 名称**：FP-A22 kernel dtype 分派/模板映射错配（特定 dtype 静默走错分支）｜ **类别**：精度 ｜ **风险**：高（S3×O3=9）｜ **状态**：活跃 ｜ **来源**：ops-math #3747/#3748（2026-10-21，aclnnTril dtype 全组合实测）
- **适用声明头**（照抄卡片）：仓 All ｜ 侧别 Kernel,Tiling ｜ 载体 Kernel源码,Tiling源码 ｜ 触发 必须触发 ｜ 默认启用 true
- **一句话机理**：kernel 按 dtype 派发到不同的执行模板 / TilingKey / 类型特化分支，而 `dtype ↔ 模板` 的映射表**缺条目或指错**，该 dtype 静默落到默认分支或错误模板，返回 `ACLNN_SUCCESS` 但输出只写了一部分、或掩码按错误类型语义计算。
- **关键判据**：**同宽度兄弟 dtype 表现分裂**（`int32` 对而 `uint32` 错、`uint64` 对而 `int64` 错）——这一条把「按字节宽度搬运」的解释直接排除。

## 2. 检视输入与算子定位

输入：算子名 / aclnn 接口名（可选：指定仓库与分支）。

定位顺序：
1. **支持集**：`op_host/*_def.cpp` 的 `DataType(dtypeList)`、`op_graph/*_proto.h` 的 `TensorType(...)`、`docs/aclnn*.md` 参数表 dtype 列、`binary.json`；
2. **派发点**：`op_kernel/**` 里的 `switch (dtype)`、`TILING_KEY` 分支、模板实例化表、函数指针数组；
3. **输出写入点**：每个模板的 `for` 循环上界、`DataCopy`/`SetGlobalBuffer` 长度、`bool` 掩码比较。

```bash
git grep -nE "switch\s*\(\s*(dtype|dataType|DT_)" -- <op>/op_kernel/
git grep -nE "TILING_KEY|tilingKey|GetTypeSize|sizeof\(" -- <op>/op_kernel/
git grep -nE "default\s*:" -- <op>/op_kernel/
```

## 3. 取数方式（Important）

- 优先读**被检分支的真实 HEAD**（`git show <ref>:<path>` 或 sparse checkout），不要读本地陈旧副本；行号必须来自同一 commit。
- 行号证据用 `文件:行号` 字面量，报告末尾跑 `scripts/verify_lines.py` 校验。
- 支持集以 `def.cpp` 为准；文档 dtype 表与 proto 只作交叉核对，三者不一致时另按 FP-F03 记录。

## 4. 派发映射检视清单（每点：查什么 → 何处 → 命中判据）

### ① 映射表条目与支持集差集（子型 A22-1）

查：受支持 dtype 全集（def.cpp）vs 派发表条目集合。
判据：差集非空 ⇒ 命中。差集项落到 `default:` 静默兜底 = 高危；落到显式报错 = FP-B01（误拦截）而非本型。

### ② 每个模板的输出循环上界（子型 A22-3）

查：每个 dtype 模板的 `for`/`DataCopy` 上界、`SetGlobalBuffer` 长度。
判据：上界取自**其他 dtype** 的元素数/字节数（如按 8 字节算 4 字节 dtype），或只覆盖 `ceil(n/2)`、`floor(n/2)` ⇒ 命中「部分未写」。

### ③ bool / 无符号类型特化语义（子型 A22-2）

查：`bool` 的存储宽度、`true` 表示、掩码比较 `i + diagonal >= j` 的类型域；`uint32/uint64` 是否与有符号版本共用模板。
判据：按位与按字节混用、有符号比较用于无符号域、模板复用但语义不同 ⇒ 命中。

### ④ `default:` 静默兜底

查：`switch` / 映射表的 `default` 分支。
判据：兜底到某模板且不报错 ⇒ 高危（任何漏配 dtype 都会静默走错，且返回成功）。

### ⑤ 同接口其他 dtype 与同族算子连带

查：同一接口的其它 dtype 模板、同族算子（`tril`/`triu`、前向/反向）是否复制同一张表。
判据：一处命中必须连带核查镜像实现，同一报告并列给出。

## 5. 检视流程

**Step 0 定位**：确认算子目录、分支、HEAD；从 `def.cpp` 抄出受支持 dtype 全集。

**Step 1 建表**：把「dtype → 模板 / TilingKey / 输出上界」列成表，空条目与 `default` 显式标出。

**Step 2 逐点核查**：按 ①~⑤ 顺序过，每点给出「命中 / 观察项 / 反证排除」三态判定，每态都要有证据行号。

**Step 3 业务可达性核查**：对每个命中项判断真实业务能否走到（B3/B2/B1）——dtype 是否在 PTA/torch_npu 常规调用中出现、是否只在极端 dtype 下可达；无法证明不可达即记 B3。

**Step 4 实测设计**（本模式必做）：dtype 全组合 ×「1 元素 / 非整除行宽 / diagonal 边界」三档；输出 buffer 预填魔数，统计残留比例；同宽度兄弟 dtype 成对对照。

**Step 5 出卡**：按第 6 节模板产出；命中项与观察项分列。

## 6. 产出格式（Bug 卡必填字段）

```markdown
# FP-A22 检视报告：<接口名>（YYYY-MM-DD）

## 一、执行概览
仓 / ref / HEAD；受支持 dtype 全集（来源 def.cpp 行号）；派发点清单；命中 X / 观察 Y / 反证排除 Z。

## 二、命中明细（每卡含 B 轴业务影响评估）
- 模式编号 + 子型（A22-1/2/3）
- **业务影响评估（B 轴）**：B3/B2/B1 + 依据 + 影响类型（静默精度损失 / 任务失败中断 / 性能退化 / 仅可观测性）
- **证据等级**：静态可证 | 需实测确认
- **Agent 误判记录**：本次被推翻的假设 + 推翻证据；无推翻写「无」
- **增减不对称**：追加候选的理由；若撤销候选，必须附 `[文件]:[行号] [代码行]` 负向证据
- S×O 与复现方案（dtype / shape / 预填魔数）

## 三、观察项（需实测确认，不以「命中」出卡）
## 四、反证排除（表：清单项 | 反证理由 | 防护面证据）
## 五、建议（测试拦截 / 修复优先级）

证据等级分布（静态可证 X / 需实测确认 Y）
```

## 7. 判定纪律（全库统一）

### 业务可达性核查

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

### 判定纪律补充（v3.6）：非对称增减、证据等级与误判记录

**增减不对称**：允许追加候选（有据即可，错了可由用户排除）；**撤销或否决候选必须附 `[文件]:[行号] [代码行]` 负向证据**。无证据的「看起来没问题」一律记为「未核查」，不得计入反证排除，也不得据此下调等级——否决造成的漏报用户不可见、不可恢复。

- **证据等级**（Bug 卡必填）：`静态可证` = 推导链完整且触发输入可静态构造；`需实测确认` = 依赖运行时输入规模、设备行为或环境差异。标 `需实测确认` 的条目**不得以「命中」名义出卡**，按观察项记录并附实测用例。
- **Agent 误判记录**（Bug 卡必填）：本次被推翻的假设、推翻它的证据（`[文件]:[行号] [代码行]` 或实测输出）、判定标准是否随之修订；无推翻写「无」。
- **误判回流**：同类误判在 3 次检视中重复出现，登记至 `cases/misjudgments.jsonl`（字段见 `cases/README.md`），并在本模式判定标准中新增对应防线；守门 C19d 校验台账字段合法。

## 8. 报告结构（每卡含 B 轴业务影响评估）

按第 6 节模板输出；报告必须含「证据等级分布（静态可证 X / 需实测确认 Y）」，并逐卡给出 B 轴业务影响评估。

## 9. 工作量与抽样

### 工作量与抽样（v4.0）

深度档：**全量核查，不抽样**——受支持 dtype 全集逐个过映射表，每个 dtype 模板都要看输出上界与类型语义。

## 10. 能力边界与自检

- **本模式能静态判**：映射表条目与支持集差集、`default:` 兜底、输出上界取自错误 dtype、bool/无符号特化；**不能静态判**：某个模板在运行期实际写入了多少元素（需魔数预填实测）。
- **找不到 ≠ 没有**：`scan_fp.py --only FP-A22` 当前无机器签名（本版未重建产出基线），未命中只能表述为「本轮未发现」，并写明抽样口径与停止点。
- 自检命令：

```bash
python3 scripts/scan_fp.py --only FP-A22 <op_kernel_dir>
python3 scripts/verify_lines.py <报告>.md --root <被检仓根>
python3 check_fault_patterns.py
```

- 新增机器签名前必须先重跑 `scripts/sig_yield.py` 重建 `cases/sig_yield-*.json`，否则 C38 会拦截（改签名不重跑审计即 ERROR）。

## 11. 已知缺陷案例库：触发条件 / 根因 / 修复范式 / 针对性深挖（v5.1）

### 案例 1｜uint32 / int64 约一半输出未写 —— ops-math #3747

- **触发条件**：`aclnnTril` 的 `self` dtype 为 `uint32` 或 `int64`，`diagonal=0`，任意 2D shape；`out` 预填魔数后可观察到后 `ceil(n/2)` 个元素原样保留。
- **根因**：该算子按元素 dtype 分派执行模板，`uint32` / `int64` 的模板映射条目疑似错配，落到只覆盖一半元素的循环上界；同宽度兄弟 dtype（`int32` 对、`uint64` 对）正常，排除「按字节宽度搬运」的单一解释。具体 kernel 文件与行号 issue 未给出，需按第 2 节命令在 `experimental/conversion/tril/op_kernel/` 下定位。
- **修复范式**：把 dtype→模板映射表改为与 `def.cpp` 支持集逐项对齐；`default:` 分支改为显式报错而非静默兜底；输出循环上界一律取自该 dtype 自身元素数。
- **针对性发现**：单 dtype 用例（常用 fp32/int32）全绿；只断言返回码的 UT 完全看不出来——必须预填魔数并统计残留比例。同宽度兄弟 dtype 成对对照是最快判据。
- **最小复现锚**：`experimental/conversion/tril/op_kernel/`（dtype 派发表，行号待定位）；对拍输入 4×4 ramp `[0..15]`，`out` 预填 `0x7FC07FC0`。
- **实证**：ops-math #3747（2026-10-21，两段接口均返回 0）。

### 案例 2｜bool 掩码边界错位 —— ops-math #3748

- **触发条件**：`aclnnTril` 的 `self` dtype 为 `bool`，`diagonal=0`；输出全量写出，但保留/置零边界按错误类型语义计算，误差随规模放大（3×3 错 4/9、4×4 错 12/16、8×8 错 42/64）。
- **根因**：`bool` 与其它 dtype 走同一条按字节宽度分派的路径，但掩码比较 `i + diagonal >= j` 的类型域/边界条件按非 bool 语义实现；属于类型特化路径缺失（子型 A22-2）。
- **修复范式**：为 `bool` 建立独立掩码分支，比较在整型域完成、写回时归一为 `true/false`；或在统一模板中用 `if constexpr (IsSameType<T, bool>)` 特化。
- **针对性发现**：该接口其它 dtype 同条件全对，只有 bool 错——「按 dtype 全组合跑同一 shape」能一眼定位；只测 fp32 会漏。
- **最小复现锚**：`experimental/conversion/tril/op_kernel/`（bool 掩码分支，行号待定位）；4×4 ramp 输入 `[0,1,1,...]`。
- **实证**：ops-math #3748（2026-10-21）。

### 案例 3｜输出 dtype 被误当计算 dtype 推容量 —— 子型 A22-4

- **触发条件**：`aclnnLinSpace` 输出 dtype 为 BF16 / INT8 / UINT8 / INT16（实际计算在 FP32 / FP16 上做），且连续调用；tiling 的 `CalcMaxOutNum` 用输出位宽推容量 → 尺寸估算错 → 报错。
- **根因**：`ge::GetSizeByDataType(outDataType)` 把**输出存储 dtype** 的宽度喂给容量推导，而该处需要的是**实际计算 dtype** 的宽度。BF16(2B)/INT8(1B) 与 FP32(4B) 差 2~4 倍 → 每核元素数、单次处理量系统性偏离。
- **修复范式（✅，修复后形态，本仓实测锚）**：

```cpp
// ❌ 输出存储类型直接当计算类型
int32_t outTypeSize = ge::GetSizeByDataType(outDataType);
// ✅ calcDataType 映射后再取宽度（lin_space_tiling.cpp:124-132）
ge::DataType calcDataType = outDataType;
if (outDataType == ge::DT_BF16 || outDataType == ge::DT_INT32)          calcDataType = ge::DT_FLOAT;
else if (outDataType == ge::DT_INT8 || outDataType == ge::DT_UINT8 ||
         outDataType == ge::DT_INT16)                                    calcDataType = ge::DT_FLOAT16;
int32_t outTypeSize = ge::GetSizeByDataType(calcDataType);
```

- **针对性发现**：① grep `GetSizeByDataType\s*\(\s*(outDataType|outputDtype)`；② 看该尺寸喂给谁——若用于**临时 buffer 容量 / 每核元素数 / 单次处理量**而非输出分配，即须用计算 dtype；③ 同文件内已存在 `calcDataType` 却未用于该处 = 高危；④ **连续调用**场景更易暴露（tiling 每次重算，累积偏差放大）。
- **最小复现锚**：BF16/INT8/INT16/INT32 四种输出 dtype 各跑「单次 + 连续 2 次」，断言返回码与数值；再取输出元素数跨 tiling 分块边界的 shape。tiling UT 直接断言 `CalcMaxOutNum` 返回值最快。
- **实证**：ops-math issue #1004 `aclnnLinSpace连续调用导致报错`。修复后形态锚：`math/lin_space/op_host/lin_space_tiling.cpp:122-132`（@ops-math HEAD `9a37afe`，2026-11-05 本地核验）。**注意**：diff 只改了这一处尺寸推导、未清理任何跨调用状态，故本案不能按 FP-A21 跨调用残留定根因。

## 12. 实证加深（v5.4）

> 取证基线：ops-math `@9a37afe` / ops-nn `@b27fda2`（2026-11-05 本地核验）。仓为浅克隆，commit 列记当前 master HEAD，非修复提交 SHA。

### 12.1 真实锚（修复后形态）

| 案例 / issue | 真实锚（文件:行号 @commit） | 要点 |
|---|---|---|
| #1004 `aclnnLinSpace` 输出 dtype 当计算 dtype（子型 A22-4） | `math/lin_space/op_host/lin_space_tiling.cpp:122-132` @9a37afe | `CalcMaxOutNum` 内 `:124` `ge::DataType calcDataType = outDataType;`、`:126-130` BF16/INT32→`DT_FLOAT`、INT8/UINT8/INT16→`DT_FLOAT16` 映射、`:132` `int32_t outTypeSize = ge::GetSizeByDataType(calcDataType);`——**修复后形态**。`:351`/`:420` 两处调用 `CalcMaxOutNum` 共用该尺寸推导。判据：容量推导用输出位宽 ⇒ 若算子实际在更宽类型上计算即命中。 |

### 12.2 反向排除项

| 反向排除项 | 所需负向证据 |
|---|---|
| 该 dtype 路径的计算类型确实等于输出类型 | 给出 dtype 分派处「计算类型 = 输出类型」的 `[文件]:[行号]`；不得以「通常如此」代替 |
| 该尺寸只用于输出存储分配 | 给出该变量作为输出 tensor 分配参数的 `[文件]:[行号]`，且未流入容量/循环上界 |
| 位宽差在该处不影响结果 | 给出「尺寸仅作上界且下游另有 clamp」的 `[文件]:[行号]`；无证据记观察项 |
| 已有 calcDtype 映射且覆盖该输出 dtype | 给出映射表覆盖该 dtype 的分支 `[文件]:[行号]`，且该映射是该尺寸的实际输入 |

## 13. 判据层（L2/L3）：出用例与判读前必读 <!-- BEGIN DETECT-SECTION (generated by scripts/sync_detect_section.py; do not edit) -->

> 生成物，勿手改（C42 校验）。完整判据见 [references/detect-l2-l3.md](references/detect-l2-l3.md)。

- **L2**：轴 dtype 分支/shape 维度｜观测 golden-canary/golden-utol｜至少 4 例
- **L3 `golden-canary`**：K128(假 PASS)随机/索引类接口的输出整块未写只能靠独立金丝雀发现，分布判据会假 PASS；K427(假阳)mssanitizer 对 aclnn 直调缓冲的 OOB 判定是 shadow 假象，须哨兵+块对齐阴性对照定案
- **L3 `golden-utol`**：K91(假 FAIL)inf==inf 被判超容差；溢出类用例整批假 FAIL；K508(假 PASS)judge 列写成 JSON 会被静默忽略 → 回落 dtype 默认容差（fp16 rtol=1e-3）

> 判 FAIL 先排「假 FAIL」、判 PASS 先排「假 PASS/假绿」。**不查 L3 就出结论 = 报告作废。** <!-- END DETECT-SECTION -->
