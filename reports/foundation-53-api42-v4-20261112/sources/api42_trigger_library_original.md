# Trigger Library

A structured checklist for precision bug discovery through **code-guided fuzzing**,
aligned with **parameter structural types** (`tensor` / `attr` / …) and **semantic roles**
(`SEM-*` / `TEN-*` / `CON-*`).

Each item is a fine-grained trigger category. Goal: **maximize coverage** of *applicable*
categories within the task's `max_cases` budget (default **1000**).

\---

\## 0. Scope: Input Construction Only

This library focuses exclusively on **what you feed as call arguments** — controllable via `inputs.*` in the test case schema.

**What we cover:**

\- Data values, shapes, indices, masks, sequences — anything expressible as a function argument
\- Control attributes (`format`, `quant_mode`, `cubeMathType`) that are API parameters

**What we do NOT cover:**

\- Build/compilation configuration (compiler flags, SoC toolchain selection)
\- Runtime environment (multi-stream, multi-device, repeated execution)

These aspects may affect operator behavior but are **outside the scope of ATK input-based testing**.

\---

\## 0.1 参数语义 → 风险项 映射原则

\> **核心命题：** 不是每个触发项对每个算子都适用。  
\> **适用性由「该算子 inputs 上出现的结构类型 × 语义角色 × 约束」决定。**  
\> 例：仅有 `TEN-PRIMARY`、没有任何 `TEN-INDEX` / 索引类 attr 时，**1.3 Index 整类应 skip（N=0）**——普通数据张量**不会**产生 index 触发。

\### 结构类型（L1）粗筛

| L1 结构                    | 可能打开的触发族                                             | 通常打不开                                       |
| -------------------------- | ------------------------------------------------------------ | ------------------------------------------------ |
| `tensor`                   | 1.1, 1.2, 1.4*, 1.5*, 1.6, 1.7, 1.8*（*依赖角色）            | 单独无法定义「index 值」类 1.3——除非角色是 INDEX |
| `tensors` / `tensor_tuple` | 同上 + 1.1.4/1.6.2（列表/路由）                              | —                                                |
| `scalar`                   | 1.1.2（计数/循环=0）, 1.7（极值系数）                        | 1.2 shape 主体、1.3 index 主体、1.4 layout       |
| `attr`                     | 1.C 控制；间接约束 1.2.7（geom）、1.4（format）、1.5（mode） | 不能单独充当 1.7 的「张量全零」                  |
| `attrs` / `attr_tuple`     | 1.2.7 GEOM、1.5 SEQ-LEN、1.8.3 负 padding、1.3.3 窗参数      | 1.7 张量值分布                                   |

\### 语义角色（L2）→ 1.x 可适用性（主表）

图例：● 直接适用　○ 条件适用　· 不适用

| 语义角色 \\ 触发族                      | 1.1 Empty | 1.2 Shape | 1.3 Index | 1.4 Layout | 1.5 Seq | 1.6 Batch | 1.7 Value | 1.8 Mask/Org |
| --------------------------------------- | :-------: | :-------: | :-------: | :--------: | :-----: | :-------: | :-------: | :----------: |
| **TEN-PRIMARY**                         |     ●     |     ●     |     ·     |     ○      |    ○    |     ●     |     ●     |      ○       |
| **TEN-OTHER-OPERAND**                   |     ●     |     ●     |     ·     |     ○      |    ·    |     ○     |     ●     |      ·       |
| **TEN-WEIGHT / BIAS**                   |     ○     |     ●     |     ·     |     ○      |    ·    |     ○     |     ●     |      ·       |
| **TEN-GRAD**                            |     ○     |     ●     |     ·     |     ·      |    ·    |     ○     |     ●     |      ·       |
| **TEN-INDEX**                           |     ○     |     ○     |   **●**   |     ·      |    ·    |     ·     |    ○†     |      ·       |
| **TEN-MASK**                            |     ○     |     ○     |     ·     |     ·      |    ○    |     ○     |     ○     |    **●**     |
| **TEN-SCALE-ZP**                        |     ○     |     ○     |     ·     |     ·      |    ·    |     ·     |   **●**   |      ·       |
| **TEN-ATTN-QKV / ROPE / SOFTMAX-STATE** |     ●     |     ●     |     ·     |     ○      |  **●**  |     ●     |     ●     |      ○       |
| **TEN-MOE-ROUTE**                       |   **●**   |     ○     |   **●**   |     ·      |    ·    |   **●**   |     ○     |      ○       |
| **TEN-SEQ-META**                        |     ○     |     ○     |     ·     |     ·      |  **●**  |     ○     |     ·     |      ○       |
| **TEN-LIST**                            |     ●     |     ●     |     ·     |     ·      |    ·    |     ○     |     ○     |      ·       |
| **SEM-LAYOUT**                          |     ·     |     ·     |     ·     |   **●**    |    ·    |     ·     |     ·     |      ·       |
| **SEM-AXIS / REDUCE / MATH-MODE**       |     ·     |     ○     |     ·     |     ·      |    ·    |     ·     |     ·     |      ·       |
| **SEM-GEOM**                            |     ○     |   **●**   |     ○     |     ·      |    ·    |     ·     |     ·     |    **●**     |
| **SEM-INDEX-CTRL**                      |     ·     |     ·     |   **●**   |     ·      |    ·    |     ·     |     ·     |      ·       |
| **SEM-SEQ-LEN / ATTN-STRUCT**           |     ○     |     ○     |     ○     |     ·      |  **●**  |     ○     |     ·     |      ○       |
| **SEM-QUANT / DTYPE-OUT**               |     ·     |     ·     |     ·     |     ·      |    ·    |     ·     |     ○     |      ·       |
| **SEM-SPARSE-MASK / PADDED-MODE**       |     ·     |     ·     |     ·     |     ·      |    ○    |     ·     |     ·     |    **●**     |
| **SEM-MOE-DIST**                        |   **●**   |     ○     |   **●**   |     ·      |    ·    |   **●**   |     ·     |      ○       |
| **SEM-SCALAR-COEFF**                    |     ○     |     ·     |     ·     |     ·      |    ·    |     ·     |   **●**   |      ·       |
| **SEM-TRANSPOSE**                       |     ·     |     ○     |     ·     |   **●**    |    ·    |     ·     |     ·     |      ·       |

† INDEX 张量的「值」是下标语义，归 **1.3**，不要用 1.7 的浮点溢出模板硬套（可用极端下标，而非 exp 溢出）。

\### 约束型（CON-*）→ 1.x

| 约束                            | 主要打开                         |
| ------------------------------- | -------------------------------- |
| `CON-SHAPE-*` / `max_length`    | 1.1.1, 1.2.*, 1.5.*, 1.6.*       |
| `CON-BOUNDARY-EMPTY`            | 1.1.1                            |
| `CON-BOUNDARY-INFNAN` / UB / LB | 1.7.2, 1.7.3                     |
| `CON-VALUE` / outlier           | 1.7.*                            |
| `CON-DTYPE` (fp*)               | 1.7.*；(int* 且角色 INDEX) → 1.3 |
| `CON-ALIGN`                     | 1.4.2 类对齐/跨步                |
| `CON-ARITY`                     | 1.1.4 / 列表组合                 |

\### 算法族 → 额外打开的 1.x（示意）

| 算法线索（来自算子/src）      | 加配触发                                       |
| ----------------------------- | ---------------------------------------------- |
| ReduceMax→scale 无 zero-guard | 1.1.3 + 1.7.1（+ 若有 quant attr → 1.C quant） |
| 偏移用 uint16/int32 存储      | 1.2.4 + 1.3.2 + 1.4.2                          |
| 尾块分支 ≠ 主循环             | 1.2.2                                          |
| Attention / 变长              | 1.5.* + 1.8.*                                  |
| MoE 路由                      | 1.1.4 + 1.3.4 + 1.6.2                          |
| Conv + GEOM attrs             | 1.2.7 + 1.8.3                                  |
| Gather/Scatter/Index          | **必须** 1.3.*；无 TEN-INDEX 则不测 1.3        |

\---

\## How to Use

\### Workspace copy and live coverage ledger

`docs/trigger_library.md` is the read-only master. New workspaces receive a copy at
`$TASK_DIR/01_generate/report/trigger_library.md`. For an older workspace, run
`verify_trigger_coverage.py init`; it refuses to overwrite existing state. The
workspace copy is a live coverage ledger, not passive reference material.

Use the workspace ledger to record applicable triggers, risk, evidence, and useful
case-ID allocations. Incomplete allocation is reported as a warning so a template
smoke case can still be materialized and executed.

Coverage is semantic, not textual. A case counts only when its concrete arguments
satisfy the complete source predicate and the generator/executor preserves those
arguments. Matching one threshold constant, copying an old intent string, or merely
executing successfully does not prove that a branch was covered. When path selection
still depends on unobserved tiling or platform state, record that limitation in the
design report instead of claiming confirmed kernel-path coverage.

Keep the machine-readable source of truth in
`$TASK_DIR/01_generate/report/trigger_coverage.json`. After every case addition,
deletion, or reassignment, update that trigger's planned count and primary case IDs,
then run:

\```bash
python3 scripts/verify_trigger_coverage.py sync --task-dir "$TASK_DIR"
python3 scripts/verify_trigger_coverage.py verify --task-dir "$TASK_DIR"
\```

The synchronized block appended to the workspace copy makes the current count and
case IDs visible beside this checklist. A missing or stale block is advisory; formal
deliverables should still review and resolve the warnings before completion.

The machine gate checks ledger consistency; it cannot prove that a human-authored
trigger annotation is semantically true. A reviewer must therefore inspect the
source predicate and executor behavior before authorizing Step 2.

\```
Phase 0 — Param inventory
  从 operator_schema / ATK YAML 列出每个 input 的:
    L1 结构 · SEM/TEN 角色 · CON 约束 · dtype
  用 §0.1 矩阵把 1.1–1.8 标成 applicable / skip。

Phase 1 — Risk Assessment
  读 src/。建议对 applicable 项估 N，skip 项保持 N=0。
  正式任务以 max_cases 作为总预算目标。

Phase 2 — Case Generation
  每案瞄准 1–2 个 applicable 类；优先「典型组合」§4。

Phase 3 — Review
  检查 applicable 项的覆盖预算，并处理校验器给出的分配 warning。
\```

\---

\## Universal Generators

| Generator            | Works on | Parameters            | Use for              |
| -------------------- | -------- | --------------------- | -------------------- |
| `constant`           | any rank | `value`               | 全零/全一/极值       |
| `explicit`           | any rank | `values`              | 精确注入 index/边界  |
| `row_linear`         | rank-2   | `base`, `step`        | 渐变、避极端或造大值 |
| `row_mod_fraction`   | rank-2   | `mod`, `add`, `scale` | 周期模式             |
| `row_special_values` | rank-2   | `default`, `rows`     | 混入 0/Inf 行        |
| `per_row_constant`   | rank-2   | `row_values`          | 每行 scale/bias      |

**int 下标类（TEN-INDEX）**：用 `explicit` / 直接 `values`，不要用浮点 generator 语义。

\---

\## Trigger Checklist

**适用性前缀**（写在每类标题下）：`Requires` = 至少具备其一才可 N>0；`Skip if` = 强制跳过。

\---

\### 1.1 Empty / Degenerate Input

**Requires:** 任一 `TEN-*` 带 `CON-SHAPE`，或控制循环次数的 `scalar`/`attr`，或 `TEN-MOE-ROUTE` / `SEM-MOE-DIST`。  
**Skip if:** 算子无张量 shape、无循环计数、无路由——无可退化对象。

`[ / ]` **1.1.1 Zero dimension** — 某维 shape=0。  
Requires: `CON-SHAPE` on tensor-like.  
Generator: shape 含 0。

`[ / ]` **1.1.2 Zero repeat/loop count** — repeat/loop/r=0。  
Requires: `SEM-SCALAR-COEFF` 或相关 attr/scalar 表示次数。  
Skip if: 无此类参数。

`[ / ]` **1.1.3 All-zero rows/blocks** — shape 非空但值全 0。  
Requires: 浮点/量化相关 `TEN-PRIMARY`（或参与 ReduceMax/scale 的张量）。  
Skip if: 无数据张量或纯布尔逻辑且无数值归约。

`[ / ]` **1.1.4 Empty expert (MoE)** — 某 expert token 数=0。  
Requires: `TEN-MOE-ROUTE` 或 `SEM-MOE-DIST`。  
Skip if: 非 MoE。

`[ / ]` **1.1.5 Empty partition/shard** — 分核后某核 0 数据（靠 shape 间接）。  
Requires: `CON-SHAPE` + 多核切分可能（大/怪 shape）。  

\---

\### 1.2 Shape & Dimension Boundary

**Requires:** 任一 tensor-like 的 `CON-SHAPE-*`，或 `SEM-GEOM`（卷积组合）。  
**Skip if:** 无 shape 可配（极罕见）。

`[ / ]` **1.2.1 Minimal dimension (M/N/K=1)** — 核心维=1。  
Requires: 存在可解释为 M/N/K/L 的 shape 维。

`[ / ]` **1.2.2 Tail-block misalignment** — 维长 ∉ 对齐（16/32/64/128/256）。  
Values: 1,3,7,13,17,33,65,69,127,129,255,257。

`[ / ]` **1.2.3 Split count exceeds limit** — split/chunk 数超内部数组。  
Requires: `SEM-SLICE` / split 类 attr 或可推导 split 的 shape。  
Skip if: 无 split。

`[ / ]` **1.2.4 Very large dimension (int overflow)** — 近 uint16/int32/2^24。  
Values: 65535, 65536, 16777217, 2^31 边界。  
代码信号: 窄整型存 offset。

`[ / ]` **1.2.5 Broadcast degeneration** — 广播维=1 / stride 0。  
Requires: ≥2 个可广播 tensor 操作数（PRIMARY+OTHER 或列表）。

`[ / ]` **1.2.6 Tiling template boundary (off-by-one)** — 落在模板选择边界 ±1。  
Requires: 从 src 读出边界常量 + `CON-SHAPE`。

`[ / ]` **1.2.7 Convolution special shape combo** — input×kernel×stride×dilation×pad。  
Requires: `SEM-GEOM`（attrs/attr_tuple）+ 特征/权重张量。  
Skip if: 非 conv/pool 几何类。

`[ / ]` **1.2.8 Output dim < minimum transfer granularity** — 输出 < 32B 等。  
Requires: 可推出 output 元素数与 dtype 宽度。

\---

\### 1.3 Index & Range Mapping

**Requires（硬条件）:**  

\- `TEN-INDEX` 或 `tensor_tuple` 索引，**或**  
\- `TEN-MOE-ROUTE` 中的 expert/token 下标，**或**  
\- `SEM-INDEX-CTRL` / `SEM-SLICE`（begin/end/window）且参与地址映射。  

**Skip if:** 仅有 `TEN-PRIMARY` 等数据张量、**无任何索引/下标/窗映射实参** —— **禁止**给 1.3 分配预算。  
（这是「张量输入不会有 index 触发」的形式化表述。）

`[ / ]` **1.3.1 Index OOB / extreme** — 0, -1, MAX_INT, ≥dim。  
Requires: `TEN-INDEX`（dtype 多为 int32/64）。

`[ / ]` **1.3.2 Offset overflow (>uint16 / >int32)** — 算址偏移溢出。  
Requires: shape/index 使 offset 公式 > 阈值；常与 1.2.4 组合。

`[ / ]` **1.3.3 Sliding window / attention window boundary** — 窗起止非法。  
Requires: `SEM-ATTN-STRUCT` / `SEM-GEOM` 窗参数或 mask 窗。  
Skip if: 无窗。

`[ / ]` **1.3.4 Expert/routing index combo (MoE)** — 极端/全同/重复路由。  
Requires: `TEN-MOE-ROUTE` 或 `SEM-MOE-DIST`。  
Skip if: 非 MoE。

\---

\### 1.4 Layout & Stride Format

**Requires:** `SEM-LAYOUT`，或 `SEM-TRANSPOSE` 导致非平凡 stride，或 schema 暴露 format/stride，或 `CON-ALIGN`。  
**Skip if:** 固定 ND、无 format/transpose/align 实参且框架不可控 stride（多项标 `[not testable]`）。

`[ / ]` **1.4.1 Non-contiguous tensor** `[not testable]` — 除非 schema 暴露 stride。  
`[ / ]` **1.4.2 Large stride (>65535)** — 由 shape 推出使 stride>65535。  
Requires: 高维大尾维 + 地址按 stride 计算的实现。  
`[ / ]` **1.4.3 Special format (NZ, TND)** —  
Requires: `SEM-LAYOUT` 可选 NZ/TND 等。  
Skip if: 仅 ND。

\---

\### 1.5 Sequence & Context Length

**Requires:** `SEM-SEQ-LEN` / `TEN-SEQ-META` / `SEM-ATTN-STRUCT` / `TEN-ATTN-QKV` 上可解释的 seq/head 维。  
**Skip if:** 无序列维语义（纯点对点 elemwise 且无 seq）。

`[ / ]` **1.5.1 Non-aligned sequence length** — seq ∉ 16/32/64/128 倍数。  
`[ / ]` **1.5.2 Very long sequence** — 2048/4096/8192…  
`[ / ]` **1.5.3 Decode-length (seq_len=1)** — 单步 decode 路径。  
`[ / ]` **1.5.4 Head dim not aligned** — dSize 非标准对齐。  
Requires: head 维存在（ATTN-STRUCT 或 QKV shape）。

\---

\### 1.6 Batch & Sample Composition

**Requires:** shape 上存在 batch/sample 维，或 MoE token 分配。  
**Skip if:** 无 batch 概念的标量核。

`[ / ]` **1.6.1 Batch > 1** — batch=2/4 激活不同 offset/workspace。  
`[ / ]` **1.6.2 Uneven expert/token allocation** —  
Requires: MoE 路由实参（同 1.1.4/1.3.4）。  
Skip if: 非 MoE。

\---

\### 1.7 Data Distribution & Value Pattern

**Requires:** 至少一数值型 `TEN-PRIMARY` / `OTHER-OPERAND` / `WEIGHT` / `SCALE-ZP` / `SEM-SCALAR-COEFF`（浮点或会转浮点）。  
**Skip if:** 无数值载荷（纯 shape 推导算子且无 data）。  
**Note:** `TEN-INDEX` 的值分布走 **1.3**，不占用 1.7 的 INF/exp 模板。

`[ / ]` **1.7.1 All-zero → div-by-zero (scale=INF)** — `constant(0)`；常与动态量化 attr 联用。  
`[ / ]` **1.7.2 NaN / Inf** — Requires: `CON-BOUNDARY-INFNAN` 或 dtype 为浮点。  
`[ / ]` **1.7.3 Extreme large values** — 近 FP 上限 / exp 溢出区。  
`[ / ]` **1.7.4 Near-zero denominator** — scale/除数 ~0。  
Requires: 除数角色张量或 scalar。  
`[ / ]` **1.7.5 Log-domain instability** — 概率近 0/1。  
Requires: 进入 log/softmax 的输入。  
`[ / ]` **1.7.6 Intermediate overflow (mul before div)** — 大值触发中间溢出。

\---

\### 1.8 Sample Organization & Masking

**Requires:** `TEN-MASK` / `SEM-SPARSE-MASK` / `SEM-PADDED-MODE` / packed 相关 attr / `SEM-GEOM` 负 padding。  
**Skip if:** 无 mask、无 pack/pad 组织、无 crop。

`[ / ]` **1.8.1 Packed variable-length sequence** — batchSizes/packed 实参。  
Requires: pack 相关 attr 或 SEQ-LEN 数组。  
`[ / ]` **1.8.2 Mask type/combination** — causal/SWA/custom + GQA 等。  
Requires: `TEN-MASK` 或 `SEM-SPARSE-MASK`。  
`[ / ]` **1.8.3 Negative padding (crop)** —  
Requires: `SEM-GEOM` padding 允许负值。

\---

\## 1.C Control Arguments

\> 仍属 **输入构造**（API 实参），但语义是「拨开关」而非「填数据」。  
\> 仅当 schema/`inputs` 暴露对应 attr 时 applicable。

| ID        | 项                           | Requires 语义                               | 常联合 1.x |
| --------- | ---------------------------- | ------------------------------------------- | ---------- |
| **1.C.1** | 动态/静态量化、quant 粒度    | `SEM-QUANT`                                 | 1.7.1      |
| **1.C.2** | 输出低精度 / out dtype       | `SEM-DTYPE-OUT` / `SEM-QUANT`               | 1.7        |
| **1.C.3** | cubeMathType / KEEP_DTYPE    | `SEM-MATH-MODE`                             | 1.2, 1.7   |
| **1.C.4** | RoPE / sink / dual-IO 等模式 | `SEM-ATTN-STRUCT` 等                        | 1.5, 1.8   |
| **1.C.5** | deterministic / accumulate   | `SEM-DETERMINISTIC` / `SEM-INDEX-CTRL`      | 1.3        |
| **1.C.6** | format / NZ                  | `SEM-LAYOUT`                                | 1.4        |
| **1.C.7** | reduction / dim / transpose  | `SEM-REDUCE` / `SEM-AXIS` / `SEM-TRANSPOSE` | 1.2        |

\---

\## Typical Combination Patterns

| Pattern              | 组合                | 参数前提                         | When                          |
| -------------------- | ------------------- | -------------------------------- | ----------------------------- |
| **A** Zero+scale=INF | 1.1.3+1.7.1(+1.C.1) | TEN-PRIMARY 浮点；可选 SEM-QUANT | ReduceMax→scale 无 zero-guard |
| **B** 大维整型溢出   | 1.2.4+1.3.2+1.4.2   | CON-SHAPE；代码窄整型            | offset/stride 截断            |
| **C** 尾块           | 1.2.2               | CON-SHAPE                        | 尾块分支                      |
| **D** Index 极端     | 1.3.1(+1.C.5)       | **TEN-INDEX 必须**               | gather/scatter                |
| **E** 变长+mask      | 1.5.1+1.8.2         | SEQ + MASK 语义                  | Attention                     |
| **F** MoE 空专家     | 1.1.4+1.3.4+1.6.2   | MOE 语义                         | 路由                          |
| **G** Conv 几何      | 1.2.7+1.8.3         | SEM-GEOM                         | 卷积/池化                     |
| **H** Dim=1 模板     | 1.2.1               | CON-SHAPE                        | 退化维 tiling                 |

\---

\## Counter Summary Template

\```
Budget: max_cases
Phase 0 roles: [list TEN-*/SEM-* present]
Applicable 1.x: [...]
Skipped 1.x: [...] (with reason, e.g. "1.3 skip — no TEN-INDEX")

High risk:
  \- 1.x.x: N — code evidence
Medium:
  \- ...
Low / skip:
  \- 1.3.*: 0 — no index-like inputs
\```

\---

\## Appendix: Quick Decision Tree

\```
是否有 TEN-INDEX / 索引 attr / MoE 路由下标？
  否 → 1.3 全 skip
  是 → 评估 1.3.1–1.3.4

是否有浮点（或量化）数据张量？
  否 → 1.7 大部 skip（保留整数极端若代码需要）
  是 → 1.7 打开

是否有 SEM-GEOM？
  否 → 1.2.7 / 1.8.3 skip
  是 → 打开

是否有序列/Attention 语义？
  否 → 1.5 与 1.8.1–1.8.2 部分 skip
  是 → 打开

是否有 SEM-LAYOUT 或可推 stride？
  否 → 1.4 多 skip / not testable
  是 → 1.4 打开
\```

\---

*与 CIDA 参数语义对齐：`atk_cida_project/docs/param_type_taxonomy.html` §2；  
精度故障触发规范：`atk_cida_project/docs/precision_trigger_rootcause_taxonomy.html`。*