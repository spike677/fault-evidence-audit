# FP-G02 案例库（渐进式披露第 3 层）

> **为什么在这里**：本文件原为 `SKILL.md` 的 `## 11. 已知缺陷案例库`（265 行，占整份 skill 的 49%）。
> 案例只在**确认命中之后**才需要翻（看同类怎么修），而清单/流程/定级/产出模板在前半部分就已完整——
> 典型「按需加载」内容，故外置为第 3 层，正文只留索引。
>
> **机读链路**：`scripts/gen_cases.py` 优先读本文件（v6.24 起），抽到 `cases/cases.json`；
> 案例块格式必须保持 `### 案例 N｜标题` + 标准字段（触发/根因/修复范式/针对性发现/最小复现锚/实证），
> 否则机读化会漏条。真锚在 `## 15. 实证加深` 节，**不**在本文件。

## 案例索引

- 案例 1｜标量写与 vector 读之间缺 S_V 硬事件同步 —— ops-nn #5960（group_norm_swish，PR !10683）
- 案例 2｜一核双 AIV 清同一 workspace 无同步（VerifyResult 通过但隐患） —— ops-nn #5513（conv3d_backprop_filter_v2）
- 案例 3｜同地址两次访问缺 PipeBarrier（WAW + RAW） —— ops-nn #3802（conv3d_v2，PR #6896）
- 案例 4｜固定 UB buffer 复用缺反向同步（V→MTE2） —— asc-devkit #1762（matmul_gelu）
- 案例 5｜用错同步边（SToMTE3Sync 覆盖不到 V→MTE3） —— ops-math #3604（RadixTopK）
- 案例 6｜SetFlag 用错 event ID 致永久等待 —— ops-nn #1606（quant_batch_matmul_v4 perblock）
- 案例 7｜两个事件常量共用同一 ID —— ops-transformer #3798（chunk_gated_delta_rule，PR #8802）
- 案例 8｜AllocEventID 泄漏（循环内申请不释放）+ V 链缺 PipeBarrier —— ops-transformer #6123（fused_infer_attention_score，PR #13801）
- 案例 9｜mode4 flagId 只覆盖部分 AIV（跨核覆盖不全） —— asc-devkit #1723（matmul_s4）
- 案例 10｜SyncAll 未配 SetScheduleMode(1)（调度约束缺失） —— ops-nn #3937（add_layer_norm_quant，PR #7200）
- 案例 11｜同步四件套被条件分支独占，另一路径整体失同步（作用域错配） —— ops-transformer #5836（FlashAttentionScore）
- 案例 12｜同 pipe 同址漏 PipeBarrier（「同管线天然安全」的误读） —— ops-transformer #12772 / #12555 / #13398（stage1PingBuf）
- 案例 13｜零迭代分支绕过循环体内的同步等待（zero-trip）—— 26-05（FlashAttentionScoreGrad）

---

> 本节把本型**已确认缺陷**拆到「触发条件 → 根因（具体路径）→ 修复范式（✅ 正确代码）→ 针对性发现步骤 → 最小复现锚」的代码级颗粒度。
> 修复范式为**正确形态示意**；路径引用取自卡片实证，行号以被检仓本地 HEAD 为准，**不得臆造**。

### 案例 1｜标量写与 vector 读之间缺 S_V 硬事件同步 —— ops-nn #5960（group_norm_swish，PR !10683）

- **触发条件**：`group_norm_swish` 走 `arch35` 分支，`CastMeanAndRstd` 用标量（S）写 mean/rstd、随后 vector（V）读同一 UB。
- **根因（具体路径）**：`arch35/group_norm_swish_base.h` 的 `CastMeanAndRstd` **标量写与 vector 读之间缺 `S_V` 硬事件同步** → V 可能先于 S 读到旧值。
- **修复范式（✅，示意）**：

```cpp
// ❌ 标量写 mean/rstd 后直接 vector 读，缺 S_V 同步
// ✅ 补 S_V 硬事件同步对
event_t e = GetTPipePtr()->AllocEventID<HardEvent::S_V>();
SetFlag<HardEvent::S_V>(e);
// ... 标量写 mean/rstd ...
WaitFlag<HardEvent::S_V>(e);
GetTPipePtr()->ReleaseEventID<HardEvent::S_V>(e);
// ... vector 读 ...
```

- **针对性发现（可执行）**：① 搜 `CastMeanAndRstd|MeanAndRstd` 与标量写、vector 读同段处；② 核该段有无 `HardEvent::S_V` 配对；③ `SetFlag`/`WaitFlag` 逐个人工确认配对。
- **最小复现锚**：跑 group_norm_swish arch35 用例，对比加/不加 `S_V` 同步时 mean/rstd 相关输出。
- **实证**：#5960（closed），修复 PR `!10683`。

### 案例 2｜一核双 AIV 清同一 workspace 无同步（VerifyResult 通过但隐患） —— ops-nn #5513（conv3d_backprop_filter_v2）

- **触发条件**：Ascend950 **一核双 AIV**，`ClearWorkspace` 对同一块 GM workspace 清零。
- **根因（具体路径）**：双 AIV 清同一块 GM workspace **无 AIV 间同步**，racecheck 检出 **28 条 GM `WAW`**；`conv3d_backprop_filter_v2.h:316`、`conv3d_dw_v2_basic_block.h:125,236` 的偏移**不含 `GetSubBlockIdx()`**，两 AIV 写同址。
- **修复范式（✅，示意）**：

```cpp
// ❌ 双 AIV 清同一 GM 地址，无核间同步
// ✅ AIV 间加同步，或使偏移含 GetSubBlockIdx() 使两 AIV 写不同地址（二选一，按语义定）
uint64_t off = base + GetSubBlockIdx() * blockSize;  // 分址
// 或：CrossCoreSetFlag/WaitFlag 保证两 AIV 清零串行
```

- **针对性发现（可执行）**：① 搜 `ClearWorkspace` 与 `GetSubBlockIdx` （是否缺失）；② 跑 racecheck 看 GM `WAW` 地址对；③ 核双 AIV 是否冗余写同址。
- **最小复现锚**：Ascend950 双 AIV 环境跑该算子 racecheck，观察 GM `WAW` 计数（实证为 28）。
- **实证**：#5513（closed）；`conv3d_backprop_filter_v2.h:316`、`conv3d_dw_v2_basic_block.h:125,236`。

### 案例 3｜同地址两次访问缺 PipeBarrier（WAW + RAW） —— ops-nn #3802（conv3d_v2，PR #6896）

- **触发条件**：`conv3d_v2` 的 `InitConstValue` 与 `DataCopy` 同 L1 地址；`Cast` 与 `TransDataTo5HD` 同 UB。
- **根因（具体路径）**：`conv3d_sub_api.h:56/61` 两处同 L1 地址访问之间**缺 `PipeBarrier<PIPE_MTE2>`** → `WAW`；`quant_conv3d_common_func.h:298/341` 同 UB 访问之间**缺 `PipeBarrier<PIPE_V>`** → `RAW`。
- **修复范式（✅，示意）**：

```cpp
// ❌ 同地址连续访问，无同管线 barrier
DataCopy(l1, ...);  InitConstValue(l1, ...);         // 同 L1，缺 PIPE_MTE2
// ✅ 同 pipe 内冲突访问之间补 PipeBarrier
DataCopy(l1, ...);
PipeBarrier<PIPE_MTE2>();
InitConstValue(l1, ...);
```

- **针对性发现（可执行）**：① 定位同地址的两次 `DataCopy`/计算；② 核两者之间是否同管线缺 `PipeBarrier<PIPE_*>`（注意：barrier 只护**同管线**）；③ racecheck 看 `WAW`/`RAW` 地址对。
- **最小复现锚**：对该算子跑 racecheck，观察 `conv3d_sub_api` / `quant_conv3d_common_func` 处 `WAW` / `RAW`。
- **实证**：#3802（closed），修复 PR #6896；`conv3d_sub_api.h:56/61`、`quant_conv3d_common_func.h:298/341`。

### 案例 4｜固定 UB buffer 复用缺反向同步（V→MTE2） —— asc-devkit #1762（matmul_gelu）

- **触发条件**：`matmul_gelu` 样例 `xUB` 被 tile 循环**反复复用**。
- **根因（具体路径）**：两次 `DataCopyPad` 之间**只有 `MTE2_V` 产出方 flag**，**缺 V→MTE2 反向同步**——MTE2 可能在 V 尚未读完 `xUB` 时就覆写 → racecheck 报 UB `WAW`（`mmad_gelu.asc:594` 写 / `:619` 后补同步；修复后 racecheck 1→0）。
- **修复范式（✅，示意）**：

```cpp
// ❌ 循环复用 xUB：只等 MTE2→V（产出方），不等 V 读完就覆写
DataCopyPad(xUB, xGm, ...); SetFlag<MTE2_V>(e); WaitFlag<MTE2_V>(e); /* compute */ 
DataCopyPad(xUB, xGmNext, ...);   // 未等 V 读完 → WAW
// ✅ 覆写前先等 V 读完（反向同步 V→MTE2）
WaitFlag<HardEvent::V_MTE2>(eV2mte2);
DataCopyPad(xUB, xGmNext, ...);
```

- **针对性发现（可执行）**：① 搜固定 UB buffer（如 `xUB`）在循环内的复用点；② 核两次搬运之间有无 `V_MTE2`（反向）同步——只有 `MTE2_V` 不够；③ racecheck 看 UB `WAW`。
- **最小复现锚**：跑 `mmad_gelu.asc` 样例 racecheck，观察 `xUB` 处 `WAW`（实证修复后 1→0）。
- **实证**：#1762（closed）；`mmad_gelu.asc:594` 写 / `:619` 补同步。

### 案例 5｜用错同步边（SToMTE3Sync 覆盖不到 V→MTE3） —— ops-math #3604（RadixTopK）

- **触发条件**：`RadixTopK` WS 变体走 `HandleLastRoundBoundary`。
- **根因（具体路径）**：V 写 `tileTopK` 后 MTE3 读同一 UB，原代码用 `SToMTE3Sync`——`PipeBarrier<PIPE_V>` 只保证 V 内部、`SToMTE3Sync` 只覆盖 S→MTE3，**两者都覆盖不到 V→MTE3** → k 配额错乱。
- **修复范式（✅，示意）**：

```cpp
// ❌ 用 SToMTE3Sync 护 V→MTE3 —— 方向错，覆盖不到
// ✅ 用真正对应方向的事件（V→MTE3）
SetFlag<HardEvent::V_MTE3>(e); // ... MTE3 读之前
WaitFlag<HardEvent::V_MTE3>(e);
```

- **针对性发现（可执行）**：① 列出「谁写、谁读、方向」三要素；② 核所用手写同步的**方向**是否匹配（S→MTE3 ≠ V→MTE3）；③ 核 `PipeBarrier` 是否被误当跨管线保护。
- **最小复现锚**：跑 RadixTopK WS 变体（尾轮边界），观察 k 配额结果。
- **实证**：#3604（closed）；`radix_top_k_ws.h` `HandleLastRoundBoundary`。

### 案例 6｜SetFlag 用错 event ID 致永久等待 —— ops-nn #1606（quant_batch_matmul_v4 perblock）

- **触发条件**：B 矩阵搬运路径 `CopyInBL1` 等待的 event ID 与实际 `SetFlag` 的 ID 不一致。
- **根因（具体路径）**：`quant_batch_matmul_v4/op_kernel/quant_batch_matmul_v4_perblock.h:281` 的 `CopyInBL1` **SetFlag 用错 event ID** → 等待方永远等不到正确信号 → **永久等待**。
- **修复范式（✅，示意）**：

```cpp
// ❌ set 的 ID 与 wait 的 ID 不一致 → 等待方永远等不到
// ✅ set/wait 用同一 ID
int32_t e = ...; SetFlag<HardEvent::MTE2_V>(e); WaitFlag<HardEvent::MTE2_V>(e);
```

- **针对性发现（可执行）**：① 逐对核 `SetFlag(e)` 与 `WaitFlag(e)` 的 **ID 是否相同**；② 核同一事件的 set/wait 是否跨分支；③ 定位「wait 无对应 set」的孤儿。
- **最小复现锚**：跑该算子 B 矩阵搬运路径，观察是否卡在 `CopyInBL1`。
- **实证**：#1606（closed）；`quant_batch_matmul_v4_perblock.h:281`。

### 案例 7｜两个事件常量共用同一 ID —— ops-transformer #3798（chunk_gated_delta_rule，PR #8802）

- **触发条件**：`chunk_gated_delta_rule` 同时使用 FIX→MTE2 与 S→MTE3 两个事件。
- **根因（具体路径）**：`chunk_gated_delta_rule_utils.h:32-33` 的 `FIX_MTE2_EVENT` 与 `S_MTE3_EVENT` **共用 ID 6** → 两类信号互相覆盖。
- **修复范式（✅，示意）**：

```cpp
// ❌ 两个语义不同的事件常量共用 ID 6
constexpr int32_t FIX_MTE2_EVENT = 6;
constexpr int32_t S_MTE3_EVENT  = 6;
// ✅ 各用互异 ID
constexpr int32_t FIX_MTE2_EVENT = 6;
constexpr int32_t S_MTE3_EVENT  = 7;
```

- **针对性发现（可执行）**：① 列出 kernel 全部事件常量定义，核**是否两两互异**；② 核 `id % N` 的 N 是否 ≥ 实际 buffer 数；③ 核 ID 是否落在池容量内。
- **最小复现锚**：跑该算子同时触发两类事件的用例，观察结果是否错乱。
- **实证**：#3798（closed），关联 PR #8802；`chunk_gated_delta_rule_utils.h:32-33`。

### 案例 8｜AllocEventID 泄漏（循环内申请不释放）+ V 链缺 PipeBarrier —— ops-transformer #6123（fused_infer_attention_score，PR #13801）

- **触发条件**：noquant 路径 S2 循环 + 长序列 MLA + attenMask。
- **根因（具体路径）**：`AllocEventID<MTE2_V>` 在 S2 循环内**每迭代申请且从不释放**，事件池仅 8 个，累计**越界**后 ID 直送 set/wait；且同块 UB 的 V 链（拷入/FlashUpdate → LastDivNew 原地除 → 就地 Cast）全走 `PIPE_V` 但中间**缺 `PipeBarrier<PIPE_V>`**，`RAW` 无保护 → 输出偶发错值 / 挂死。
- **修复范式（✅，示意）**：

```cpp
// ❌ Alloc 在循环内、不 Release → 池耗尽越界
// ✅ 循环外申请一次、或每次成对 Release
int32_t e = GetTPipePtr()->AllocEventID<HardEvent::MTE2_V>();  // 循环外
for (...) { SetFlag<HardEvent::MTE2_V>(e); /* ... */ WaitFlag<HardEvent::MTE2_V>(e); }
GetTPipePtr()->ReleaseEventID<HardEvent::MTE2_V>(e);
// V 链中间补：PipeBarrier<PIPE_V>();
```

- **针对性发现（可执行）**：① 搜 `AllocEventID` 是否位于循环体内且无配对 `ReleaseEventID`；② 核事件池容量与累计申请数；③ 核同 UB 同 pipe 连续操作间有无 `PipeBarrier<PIPE_V>`。
- **最小复现锚**：跑长序列 MLA + attenMask 用例（S2 循环多迭代），观察是否挂死 / 出错值。
- **实证**：#6123（open），关联 PR #13801。

### 案例 9｜mode4 flagId 只覆盖部分 AIV（跨核覆盖不全） —— asc-devkit #1723（matmul_s4）

- **触发条件**：`matmul_s4` 样例，两个 AIV 与一个 AIC。
- **根因（具体路径）**：两 AIV 都 `CrossCoreSetFlag<4, PIPE_MTE3>(8)`，AIC 只 `CrossCoreWaitFlag<4, PIPE_MTE2>(8)`——**mode 4 flagId 8 只覆盖 AIV0**，AIV1 的写未被 AIC 感知 → racecheck **1 条 `WAW` + 513 条 `RAW`**（`matmul_s4.asc:102-107/135/158`）。
- **修复范式（✅，示意）**：

```cpp
// ❌ mode 4 flagId 8 只让等待方感知 AIV0，AIV1 未覆盖
// ✅ 让等待方感知全部参与 AIV（按 mode 语义对每个 AIV 覆盖，或分 flagId）
```

- **针对性发现（可执行）**：① 核 `CrossCoreSetFlag`/`CrossCoreWaitFlag` 的 mode+flagId 映射；② 核等待方是否感知**全部** AIV；③ racecheck 看 RAW 计数与源 AIV。
- **最小复现锚**：跑 `matmul_s4.asc` 样例 racecheck，观察 RAW 条数（实证 513）。
- **实证**：#1723（closed）；`matmul_s4.asc:102-107/135/158`。

### 案例 10｜SyncAll 未配 SetScheduleMode(1)（调度约束缺失） —— ops-nn #3937（add_layer_norm_quant，PR #7200）

- **触发条件**：`add_layer_norm_quant` arch35 动态量化 full-load、`rowsPerCore==1`。
- **根因（具体路径）**：kernel 用 `SyncAll` 合并各核 outScale，但 host 侧 `add_layer_norm_quant_tiling_arch35.cpp` **未 `SetScheduleMode(1)`** → 无法保证所有参与核同时驻留，`SyncAll` 语义失效。
- **修复范式（✅，示意）**：

```cpp
// ❌ 用 SyncAll 合并各核结果，host 未设 schedule_mode
// ✅ host tiling 补 SetScheduleMode(1)，保证所有核同时驻留
context->SetScheduleMode(1);
```

- **针对性发现（可执行）**：① 搜 kernel 的 `SyncAll<` 调用与 host tiling 的 `SetScheduleMode`；② 核两者是否成对；③ 核涉及核间同步的算子是否都设了 `schedule_mode=1`。
- **最小复现锚**：跑 `rowsPerCore==1` 组合，观察 `SyncAll` 是否卡死。
- **实证**：#3937（closed），修复 PR #7200；`add_layer_norm_quant_tiling_arch35.cpp`。另见 #598（涉及核间同步的算子必须设 `schedule_mode=1`，防双流并发卡死）。

### 案例 11｜同步四件套被条件分支独占，另一路径整体失同步（作用域错配） —— ops-transformer #5836（FlashAttentionScore）

- **触发条件**：`FlashAttentionScore` 走 `arch22` 模板，`ProcessVec1` 内 `pseEndogenous`（内源 PSE）与外源 PSE 两条路径**复用同一 UB buffer**，PSE 丢弃 / 搬运走 V→MTE2 同步。
- **根因（具体路径）**：`op_kernel/arch22/flash_attention_score_bn2gs1s2_b.h` 的 `ProcessVec1` 中，`eventIdPseDropVToMte2B` 的 `AllocEventID` / `SetFlag` / `WaitFlag` / `ReleaseEventID` **四件套全部被 `!this->pseInfo.pseEndogenous` 包裹**——外源路径有这条 V→MTE2 边，内源路径走 `PseSlopeCopyIn` 时**整体丢失**该边。四件套各一次、ID 相同、方向正确、**完全配平**，配对完整性检查全部放行。
- **修复范式（✅，示意）**：

```cpp
// ❌ 四件套全在分支内 —— 另一分支复用同一 buffer 却无等价同步
if (!this->pseInfo.pseEndogenous) {
    int32_t e = AllocEventID<HardEvent::V_MTE2>();
    SetFlag<HardEvent::V_MTE2>(e);
    // ... MTE2 搬运 ...
    WaitFlag<HardEvent::V_MTE2>(e);
    ReleaseEventID<HardEvent::V_MTE2>(e);
}
// ✅ 把同步边提到分支外（两条路径都要）或为内源路径补一套等价四件套
int32_t e = AllocEventID<HardEvent::V_MTE2>();
if (!this->pseInfo.pseEndogenous) { /* 外源路径 */ } else { /* 内源路径：PseSlopeCopyIn */ }
SetFlag<HardEvent::V_MTE2>(e); /* ... 搬运 ... */ WaitFlag<HardEvent::V_MTE2>(e);
ReleaseEventID<HardEvent::V_MTE2>(e);
```

- **针对性发现（可执行）**：① 对每个同步四件套求**共同最内层块**，判断是否为 `if/else` / 三元 / 模板分支；② 在分支**外**搜同一 buffer / 同一地址的访问点（`DataCopy` / `PseSlopeCopyIn` / `Duplicate` 等）；③ 若有访问而该路径无等价同步 → 子型⑥ 成立；④ 注意别把它记成子型②——②是「边不存在」，⑥是「边存在但管不到」。
- **最小复现锚**：构造 `pseEndogenous=true`（内源 PSE）的 FlashAttentionScore 用例跑 racecheck，观察 `ProcessVec1` 处 UB/GM 的 `RAW`/`WAW`；再与 `pseEndogenous=false` 对比告警数量差异。
- **实证**：#5836（closed）；`op_kernel/arch22/flash_attention_score_bn2gs1s2_b.h` 的 `ProcessVec1`（`eventIdPseDropVToMte2B`）。

### 案例 12｜同 pipe 同址漏 PipeBarrier（「同管线天然安全」的误读） —— ops-transformer #12772 / #12555 / #13398（stage1PingBuf）

- **触发条件**：attention 类 kernel 用 `stage1PingBuf` 这类**固定复用** buffer，`ProcessVec1()` 的前序 PSE / `Muls` / `AttenMask` 写，与 `SoftMaxCompute()` 内 `Duplicate()` / `SoftmaxFlashV2()` 读**交替**发生在同一 `PIPE_V` 上。
- **根因（具体路径）**：同一 `PIPE_V` 上对**同一 UB 地址**的两次访问之间**既无 `PipeBarrier<PIPE_V>` 也无事件边**——被「`PipeBarrier` 只保证同管线内部顺序 ⇒ 同管线天然安全」这句**反向误读**放过；实际指令队列下写与读可能乱序，构成 `WAW` / `RAW`。
- **修复范式（✅，示意）**：

```cpp
// ❌ 同 PIPE_V 同址，两条访问之间无任何 barrier（被误认为「同管线天然安全」）
Muls(stage1PingBuf, ...);                 // 写
SoftmaxFlashV2(stage1PingBuf, ...);       // 读 —— 可能乱序
// ✅ 同 pipe 同址也必须显式串行
Muls(stage1PingBuf, ...);
PipeBarrier<PIPE_V>();
SoftmaxFlashV2(stage1PingBuf, ...);
```

- **针对性发现（可执行）**：① 列同一 `PIPE_*` 上命中**同一 buffer 名 / 同一地址表达式**的两次访问；② 核两者之间有无 `PipeBarrier<PIPE_该管线>` 或事件边；③ 无 → 候选 `WAW`/`RAW`，**禁止以「同管线」为由豁免**；④ 固定复用 buffer（`stage1PingBuf` 一类）优先审。
- **最小复现锚**：跑该 attention 模板 racecheck，观察 `stage1PingBuf` 处 `WAW`/`RAW`；补 `PipeBarrier<PIPE_V>()` 后对比告警是否归零。
- **实证**：#12772 / #12555 / #13398（三例同机理，均为 `ProcessVec1` 前序写与 `SoftMaxCompute` 内读写重叠，补 `PipeBarrier<PIPE_V>()` 修复）。

### 语料基线与深挖起手式

```bash
python3 scripts/scan_fp.py --only FP-G02 --format json <目标文件>   # 签名候选（set/wait/PipeBarrier/CrossCore/Alloc 等）
python3 scripts/scan_sync.py <目标文件或目录>                       # 配对完整性检查（孤儿原语，子型①~⑤）
python3 scripts/scan_sync_scope.py <目标文件或目录>                 # 作用域审计（四件套被分支独占，子型⑥）
# 检索基线：GitCode 全局 issue 检索 2026-10-18（23 组同步关键词）收敛 166 条 cann 候选，标题即点明同步根因者 45 条，
#   覆盖 ops-nn / ops-math / ops-transformer / asc-devkit / hccl 五仓；本卡收录 23 条为已确认对应实证。
# racecheck（mssanitizer）零告警是本模式的最高优先级门禁——多数实证均由一行地址级 WAW/RAW 报告直接暴露。
```

### 案例 13｜零迭代分支绕过循环体内的同步等待（zero-trip）—— 26-05（FlashAttentionScoreGrad）

> 与案例 11 的区别：案例 11 是「四件套被某分支**独占**」，本案例是「**零次循环**根本不进循环体，循环内的 Wait 一次都没执行」。
> 前者是作用域问题，后者是控制流覆盖问题——**同步原语总数配平也发现不了**，因为零迭代时 Set 侧同样在循环内、一起没执行。

- **触发**：`SFTS1Times`（S1 方向 SFT 迭代数）算出来为 **0**。此时 `for (SFTLoopS1 = 0; SFTLoopS1 < rp.SFTS1Times; ...)` 一次都不进，循环体内为 MM1 结果准备的 `WaitEvent(SYNC_C1_V1_FLAG)` 全部跳过，但**循环之前已经下发了 MM1 的 cube 侧工作**，后置条件不成立：下游拿到的 vec 结果是陈旧/未就绪的。
- **根因**：同步后置条件只装在**循环体内**，而循环可能零次执行。健全的写法要求「无论循环执行几次（含 0 次），出循环时 post-condition 都成立」。这属于**控制流覆盖**缺陷，不是配对缺失——`Set`/`Wait` 数量在非零路径上完全配平。
- **修复范式（✅，修复后形态，本仓实测锚）**：

```cpp
// ❌ 只在循环体内 Wait：Times==0 时一次都不执行
// ✅ 零迭代提前返回前，补齐与非零路径等价的后置等待（:3147-3151）
if (rp.SFTS1Times == 0) {
    AscendC::WaitEvent(SYNC_C1_V1_FLAG);
    AscendC::WaitEvent(SYNC_C1_V1_FLAG);   // 两次对应 MM1 的两笔在飞工作
    return;
}
for (uint32_t SFTLoopS1 = 0; SFTLoopS1 < rp.SFTS1Times; SFTLoopS1++) { ... }
```

- **针对性发现**：① 枚举所有 `for` / `while` 循环内的 `SetFlag`/`WaitFlag`/`WaitEvent`/`WaitIterateAll`；② 逐循环问「**迭代数能否为 0**」（`(x + unit - 1) / unit` 中 `x == 0`、`realSize` 为 0、尾块被整除后余数为 0）；③ 若能为 0，检查循环前是否已发出异步工作、以及零次路径上是否有等价等待；④ **等待次数要与在飞工作量对应**（本案两次 Wait 对应 MM1 两笔，只补一次同样错）。
- **最小复现锚**：`SFTS1Times = 0` 与 `= 1` 对照；记录实际 wait 次数与模板名；配时序压力（重复执行 + 输出毒化）与梯度数值对拍。**只断言「不崩溃」不够**，零迭代漏同步的典型表现是偶发错值而非崩溃。
- **实证**：现网 26-05（ops-transformer-dev PR #5966；该单无关联 issue，仅 PR）。修复后形态锚：`attention/flash_attention_score_grad/op_kernel/arch22/flash_attention_score_grad_s1s2_bn2.h:3147-3151`（@ops-transformer HEAD `d5c0683`，2026-11-05 本地核验）。同文件 `:3131` 与 `:3153` 是 `SFTS1Times` 的两个赋值来源（SAB 分支 / 普通分支），`:3159` 才是被绕过的循环——**零迭代路径与主路径的赋值来源不同，容易只测其中一条**。
