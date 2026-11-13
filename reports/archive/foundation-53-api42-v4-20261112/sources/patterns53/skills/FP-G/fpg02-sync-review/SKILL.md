---
name: "fpg02-sync-review"
description: "基于 FP-G02「核间/流水同步缺失或配对不完整」故障模式对指定 aclnn 接口做源码检视：定位算子实现，用配对完整性检查（扫孤儿原语）核查 SetFlag/WaitFlag 配平、跨流水事件同步、事件 ID 冲突泄漏、跨核覆盖、调度约束与同步作用域六子型，产出证据链与 S×O 定级报告。当用户要求排查漏插同步、同步不完整、racecheck WAW/RAW 或偶发结果不同时使用。"
---

# FP-G02 aclnn 接口检视（fpg02-sync-review）

对用户指定的 aclnn 接口（如 aclnnFlashAttentionScore）做 FP-G02 专项源码检视：定位算子实现，按六子型清单**以「配对完整性检查」逐项核查**，每个结论给出**文件 + 行号 + 推导链**证据，命中即出 Bug 卡并输出报告。**本模式特殊纪律：缺陷不是「算错了」而是「没按序」——错在两条指令之间的依赖顺序，出错的代码行本身语法正确、单看无异常，只有把「生产者—消费者」当成一对一起看才暴露，常规逐行审查与扫「错误行」的静态扫描天然漏检。因此本模式的核查单位是「原语对」（`SetFlag`↔`WaitFlag`、`AllocEventID`↔`ReleaseEventID`、`CrossCoreSetFlag`↔`CrossCoreWaitFlag`、同一地址两次访问之间的事件边），判据是**扫孤儿原语**（无配对的 set / 无来源的 wait / 只申请不释放的 event），而不是扫单个可疑行。缺陷常「时隐时现」：双 AIV 冗余写结果一致时聚合断言照样通过、新进程首调才触发、批跑轮换复现，「单跑通过」不是反证。卡片适用声明为「必须触发」：不依赖签名命中，对被检算子无条件执行六子型清单。**
> **本模式是库内最缺的覆盖**：v5.3 前 49 张卡对 `SetFlag`/`WaitFlag`/`PipeBarrier`/`双缓冲`/`核间同步`/`同步缺失` 零命中——kernel 级同步竞态此前**完全没有覆盖**（`FP-G01` 只覆盖 host / 集群级通信等待超时）。本模式即为此立项，实证达 23 条 / 5 仓；v6.15 增补子型⑥（同步作用域）三例——#12772 / #12555 / #13398。
> **v6.15 两条纪律必读**：① 子型⑥ 是**作用域**判据而非计数判据——四件套配平、ID 不冲突、方向也对，仍可能因同步整体被 `if/else` 分支独占而漏掉另一条路径，单纯「配对完整性检查」会**全部放行**；② 「同管线天然安全」是**误读**——同一 `PIPE_V` 对同一 UB 地址的两次访问仍需显式 `PipeBarrier<PIPE_V>()`。

## 0. 与相邻模式的边界

| 相邻模式 | 分工 |
|---|---|
| FP-G01（执行挂死与调度超时） | **最易混淆**：G01 是 host / 集群级「死循环不推进 / 回绕长循环 / 通信等待超时 / 设备侧超时（`HCCL_*_TIMEOUT`）」，本条是 **kernel 级同步原语**缺失。两者都致挂死，但 G01 的指纹是「无退出条件循环 / 超时配置」，本条的指纹是「`set`/`wait` 不配平、racecheck `WAW`/`RAW`」。判定：先看有无 racecheck 地址级报告或 set/wait 配平异常，有则本条 |
| FP-A06（确定性开关下结果不固定） | **边界**：A06 是确定性**开关语义**下的结果不固定，本条是**并发序竞争**致不固定——先在 racecheck 上找 `WAW`/`RAW` 证据再落本条 |
| FP-A05（脏数据 / 数据踩踏） | 缺同步致「写覆盖尚未被读的数据」在现象上极似数据踩踏：A05 管**脏数据来源**（越界 / 未初始化读），本条管**数据依赖顺序**——同一块 buffer、地址合法，只是顺序错 |
| FP-A04（功能问题演变为精度静默故障） | 本条后果常表现为「无报错但数值错」：A04 是**后果面**，本条是**机理面** |
| FP-C05（确定性场景性能骤降） | 关闭自动同步的性能优化是本条**高发诱因**——为提速关自动同步却未补齐手写同步，即落入本条 |
| FP-B10（集合通信功能/兼容面） | **跨卡边界**：通信 **kernel 内的 AIV 间同步**归本条子型④；通信库的功能 / 精度 / 兼容面归 B10 |
| FP-B07（索引/偏移越界） | 越界也会致异常结果，但本条特征是「**地址合法、顺序错**」——不越界、不崩溃，只是读到旧值 |

**症状反查定位**：`SetFlag`/`WaitFlag` 不配平、`WaitFlag` 永久等待 → 子型①；`racecheck` 报 `WAW`/`RAW` hazard（含地址与行号）→ 子型②；精度**偶现**失败、首次调用输出整段为 0 → 子型②；事件给满 / 非法 ID / 常量共用同值 → 子型③；双 AIV 冗余写同址、`VerifyResult` 通过但存在隐患 → 子型②④；`SyncAll` 卡死（未设 schedule_mode）→ 子型⑤；**配平无误但某条业务路径整体缺同步**（同步四件套全在某分支内）→ 子型⑥。**关键识别特征：缺陷复现性差、越并发越不稳定，但一旦命中 racecheck 一行地址级报告即可直接定位。**

## 1. FP-G02 模式卡摘要（检视依据，源自本库 `patterns/FP-G/FP-G02.md`，含 v6.15 子型⑥ 与同管线同址补正）

- **编号 / 名称**：FP-G02 核间/流水同步缺失或配对不完整（SetFlag/WaitFlag 未配平 / 流水同步遗漏 / 事件 ID 冲突 / 跨核覆盖不全） ｜ **类别**：执行可靠性 ｜ **风险**：高（S4×O3=12）｜ **状态**：活跃
- **适用声明头**（照抄卡片）：仓 All ｜ 侧别 Kernel,Host,Tiling ｜ 载体 Kernel源码,Host源码,Tiling源码 ｜ 触发 必须触发 ｜ 默认启用 true
- **skill 核查面**：侧别 Kernel,Host,Tiling——落地为 op_kernel（子型①②③④⑥）、op_host tiling / infershape（子型⑤ 的 `SetScheduleMode`）、tests/ut（racecheck 门禁与批跑轮换）
- **故障机理**：缺陷不是「算错了」而是**「没按序」**——同一块 buffer / 地址上的生产者与消费者之间，缺少**以等待方为视角**的同步边，导致「读先于写」或「写覆盖了尚未被读的数据」。属**遗漏型缺陷**：出错行语法正确、单看无异常，只有把「生产者—消费者」当一对一起看才暴露。六种独立成因（与六子型一一对应）：① **同步原语配对失衡 / 不完整**（`SetFlag`/`WaitFlag` 次数或分支不配平、同步对放错语句之后）；② **跨流水同步遗漏或用错同步边**（`PipeBarrier` 只保证同管线内部顺序，跨管线必须 `SetFlag/WaitFlag<HardEvent::…>`；用错方向事件覆盖不到真实依赖）；③ **事件 ID / flagId 冲突、越界、泄漏**（常量共用 ID、`id % N` 取模重复、循环内 `AllocEventID` 不 `Release` 致池耗尽）；④ **跨核同步覆盖不全**（`CrossCore*` 的 mode+flagId 只让等待方感知部分核）；⑤ **同步与调度约束缺失**（`SyncAll` 依赖核同时驻留但 host 未 `SetScheduleMode(1)`）；⑥ **同步原语的作用域与消费者不匹配**（同步四件套整体被某一业务分支独占，另一分支复用同一 buffer 却无等价同步）。**共性：单看每一行都「没错」，错在两条指令之间的依赖顺序，或错在这条同步边管不到的那条路径。**
- **子型划分（报告卡片标注）**：① 同步原语配对失衡 / 不完整；② 跨流水同步遗漏或用错同步边；③ 事件 ID / flagId 冲突、越界、泄漏；④ 跨核同步覆盖不全；⑤ 同步与调度约束缺失；⑥ 同步原语的作用域与消费者不匹配。
- **触发条件**：手写同步的 kernel；双缓冲 / 流水复用固定 UB / L1 / GM buffer；一核双 AIV 并行（Ascend950 / arch35）；多核共享同一 workspace 或同一 GM 地址；事件 ID 池有限且循环内反复申请；同步对落在条件分支内致另一分支缺失；host `SyncAll` 未设 `schedule_mode`；同一地址两次访问之间只放了产出方 flag 而无等待方反向同步；同一 pipe 对同一地址两次访问之间既无 barrier 也无事件。
- **典型表现**：racecheck 报 `WAW`/`RAW` hazard（含地址与行号）；精度**偶现**失败（批跑轮换 / 新进程首调易触发）；输出整段为 0 或错值；`WaitFlag` 永久等待 / 同步卡死 / 超时 `aic error`；`VerifyResult` 通过但存在隐患。**关键识别特征：复现性差、越并发越不稳定。**
- **实证案例**（详情见第 11 节案例库）：#5960（`group_norm_swish` 缺 `S_V` 同步，PR `!10683`）、#5513（`ClearWorkspace` 双 AIV 无同步，racecheck 28 条 GM `WAW`）、#3802（`conv3d_v2` 缺 `PipeBarrier`，PR #6896）、#1762（`matmul_gelu` 缺 V→MTE2 反向同步，racecheck UB `WAW`）、#3604（RadixTopK 用错 `SToMTE3Sync`）、#2868（STFT 缺 `MTE3_S` 致输出帧为 0）、#1606（SetFlag 用错 event ID 永久等待）、#3798（事件常量共用 ID 6，PR #8802）、#6123（`AllocEventID` 泄漏，PR #13801）、#1723（mode4 flagId 只覆盖 AIV0，513 `RAW`）、#3937（`SyncAll` 未配 `SetScheduleMode(1)`，PR #7200）、**#5836 / #12772 / #12555 / #13398（子型⑥ 与同管线同址补正）**。
- **检测签名**（命中即候选点位）：`SetFlag<\s*(AscendC::)?HardEvent::`；`WaitFlag<\s*(AscendC::)?HardEvent::`；`CrossCoreSetFlag`；`CrossCoreWaitFlag`；`AllocEventID`；`ReleaseEventID`；`PipeBarrier<\s*PIPE_(V|MTE2|MTE3|S|MTE1|FIX)>`；`HardEvent::\s*(V_MTE2|V_MTE3|MTE2_V|MTE3_V|S_V|V_S|MTE3_S|S_MTE3)`；`SyncAll\s*<`；`SetScheduleMode\s*\(\s*1\s*\)`。**核心方法见子型清单的「配对完整性检查」。**
- **审查关键词**（命中仅表示值得人工审）：`双缓冲|double\s*buffer`；`核间同步|核内同步`；`同步缺失|同步不完整|漏同步|漏插`；`事件 ?ID|flagId|flag_id`；`buffer\s*复用|复用.*UB`；`竞态|竞争|racing`；`WAW|RAW|hazard`；`SetScheduleMode|schedule_mode`；`workspace.*清零|清零.*workspace`。
- **测试拦截建议**：① **racecheck 常态化（最高优先级）**——mssanitizer `racecheck` 零告警门禁；② 同步原语配平断言（set≠wait 即告警）；③ 事件 ID 池审计（Alloc/Release 成对、申请不在循环体内、常量两两互异、池容量不越界）；④ 双 AIV / 多核共享 workspace 场景单独成类；⑤ **批跑轮换 + 新进程首调**（单次随机通过不代表无缺陷）；⑥ 自动同步勿随意关闭。
- **关联**：FP-G01（挂死，分工见第 0 节）、FP-A06（确定性边界）、FP-A05（脏数据 vs 顺序）、FP-A04（后果面）、FP-C05（关自动同步是诱因）、FP-B10（跨卡边界）。

## 2. 检视输入与算子定位

**输入**：aclnn 接口名（必填，如 `aclnnFlashAttentionScore`）；可选 ref（默认 master）、指定仓（默认自动定位）；可选现象（卡死点 / racecheck 报告 / 偶现精度失败 / 输出为 0）；可选复现条件（arch + 双 AIV / 批跑轮换——子型④ 关键输入）。

**接口名 → 算子目录换算**：去 `aclnn` 前缀 + 驼峰转下划线小写：
`aclnnFlashAttentionScore → flash_attention_score`、`aclnnGroupNormSwish → group_norm_swish`、`aclnnConv3dV2 → conv3d_v2`。

**仓定位顺序**（GitCode `cann`，逐仓用目录列表确认）：`ops-nn`（norm/loss/activation/matmul/conv）→ `ops-math`（math/conversion）→ `ops-cv`（image/vision）→ `ops-transformer`（attention/moe）→ `asc-devkit`（样例 / 公共模板）。**类目名不总与直觉一致**，以目录列表为准。FP-G02 高发面：手写 `SetFlag/WaitFlag/PipeBarrier/CrossCore*` 的 op_kernel；双缓冲 / 流水复用固定 UB 的 kernel 模板；arch35 双 AIV 算子；`ClearWorkspace` 类多核共享 workspace 清零；attention / moe 大模板与 STFT / RadixTopK 类多段流水算子。

**算子目录结构约定**（示例 `cann/ops-transformer` → `attention/flash_attention_score/`）：

```text
{类别}/{op_name}/
├── op_host/                  # *_def.cpp、*_infershape.cpp、*_tiling*.cpp——子型⑤（SetScheduleMode）
│   └── config/<soc>/         # *_binary.json（分核——跨核覆盖面）
├── op_kernel/                # kernel 模板——子型①②③④（arch22/arch35 目录区分代际）
├── op_api/（或 op_host/op_api/）  # aclnn 出口
├── tests/ut/                 # ut 框架（racecheck 门禁 / 批跑轮换）
└── docs/ CMakeLists.txt
```

## 3. 取数方式（Important）

公开网页端点被拦截，**必须走 API**（均需带 `User-Agent`；失败重试 2 次、间隔 5 秒）：

| 用途 | 端点 |
|---|---|
| 目录列表 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/contents/{path}?ref={ref}` |
| 单文件内容 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/raw/{path}?ref={ref}` |
| Issue 查重 | `GET https://api.gitcode.com/api/v5/repos/cann/{repo}/issues?q={关键词}` |
| 全局同步检索（**本模式推荐**） | `GET https://api.gitcode.com/api/v5/search/issues?q={关键词}&per_page=50&page={n}`（`q` 为全文匹配；仓库 issue 列表端点的 `q` 参数**不生效**，勿用） |

**已实测不可用（2026-09）**：`https://gitcode.com/{repo}/raw/{sha}/{path}`、`https://raw.gitcode.com/...` → 403 或拦截页。若本地已有算子仓克隆，优先读本地文件，行号以本地 HEAD 为准并记录 commit。**本模式特有取数限制**：`racecheck` 报告、双 AIV 是否冗余写、竞态是否触发均需**运行时观测**——静态检视产出「孤儿原语缺陷 + 复现/排除方案」，不可表述为「必然出错」。

## 4. 六子型检视清单（每点：查什么 → 何处 → 命中判据）

对 op_kernel / op_host / op_api / tests/ut 全部相关文件逐点核查。**本模式核查方法（贯穿子型①~⑤）：配对完整性检查（扫孤儿原语）——把每个同步原语视为只能成对出现的原语，找出「孤儿」；每点先查命中面、再做反证排除，防护面（已有配对、统一释放）也须记录。**子型⑥ 用的是**另一套判据**（作用域审计，见该节），配对检查对它**天然放行**——两条判据必须分别跑一遍，不可互相替代。

### 子型 ① 同步原语配对失衡 / 不完整
- 查什么：每个 `SetFlag<HardEvent::X>(id)` 是否在**同一路径**有匹配 `WaitFlag<HardEvent::X>(id)`（次数与分支都配平）；发起侧与等待侧的**同步信号个数**是否一致（`round_` 分支下易失衡）；同步对是否被**放在错误语句之后**（如 `SetFlag/WaitFlag<V_MTE3>` 放在 `DataCopyPad` 之后）。何处：op_kernel 全部 `SetFlag`/`WaitFlag`/`CrossCore*` 调用点。命中判据：可写出「某路径 set 次数 ≠ wait 次数 / wait 所在分支无对应 set → 永久等待或搬运先于计算」的推导链（实证 #5611 setflag 与 waitflag 未配平；#385 同步个数不匹配致 kfc 卡死；#5477 同步对放错位置）。
- **孤儿原语扫描**：统计每个事件域的 `set`/`wait` 出现次数与所在分支；`set` 无 `wait`（信号丢失、等待方永远等不到）或 `wait` 无 `set`（等待方被卡）即孤儿。

### 子型 ② 跨流水同步遗漏或用错同步边
- 查什么：`PipeBarrier<PIPE_X>` **只保证同一管线内部**顺序，**不跨管线**——跨管线（V→MTE2 / V→MTE3 / MTE2→V / MTE3→S / S→MTE3 / S→V 等）必须 `SetFlag/WaitFlag<HardEvent::…>` 显式事件同步；只写同管线 barrier、或用**错误方向**的事件（如用 `SToMTE3Sync` 去护 V→MTE3）覆盖不到真实依赖；**反向同步**是否缺失（循环复用固定 UB buffer 时，MTE2 覆写前是否等到 V 读完）；同一块 UB / L1 / GM 地址上两次访问之间是否有**以该 pipe 为等待方**的同步边。何处：op_kernel 数据搬运与计算交错处、双缓冲切换点、共享 buffer 复用点。命中判据：给出「地址 A 被 pipe P1 写、pipe P2 读，两者之间无 P1→P2 事件边」的静态推导（实证 #5960 缺 `S_V`；#5513 双 AIV 无同步；#3802 缺 `PipeBarrier`；#5836 同步被条件分支包裹；#3604 用错 `SToMTE3Sync`；#2868 缺 `MTE3_S`；#1762 缺 V→MTE2 反向同步；#5712/#5740 缺 `PipeBarrier<PIPE_V>`；#4085 只用 `MTE2_V` 不具备 VV 同步）。
- **⚠️ 同管线同址也必须显式串行（v6.15 补正，最易踩的反向误读）**：上文「`PipeBarrier<PIPE_X>` 只保证同一管线内部顺序」**不等于「同管线天然安全」**。同一 `PIPE_V` 上对**同一 UB 地址**的两次访问，在指令队列中仍可能乱序（`Duplicate`/`Muls`/`PSE` 这类写与 `SoftmaxFlashV2` 这类读交替时尤甚），必须显式 `PipeBarrier<PIPE_V>()` 建立顺序；`stage1PingBuf` 一类固定复用 buffer 是**重灾区**（实证 #12772 / #12555 / #13398：`ProcessVec1()` 的前序 PSE / Muls / AttenMask 写与 `SoftMaxCompute()` 内 `Duplicate()`、`SoftmaxFlashV2()` 重叠）。**判据：同一 pipe + 同一地址 + 两条访问之间既无 barrier 也无事件 → 候选 WAW/RAW，禁止用「同管线」当豁免理由。**

### 子型 ③ 事件 ID / flagId 冲突、越界、泄漏
- 查什么：两个不同事件常量是否**共用同一 ID**（如 `FIX_MTE2_EVENT` 与 `S_MTE3_EVENT` 同为 `6`）；`id % N` 取模而 buffer 数 **> N** 致 ID 重复；`AllocEventID<…>` 是否与 `ReleaseEventID<…>` 成对、申请是否在**循环体内**（每迭代申请 = 泄漏）；ID 是否越出池容量（如 `MTE2_V` 池 8 个、合法 `[0,8)`）。何处：op_kernel 事件常量定义、`AllocEventID`/`ReleaseEventID` 调用点、取模计算处。命中判据：常量两两冲突 / 取模范围小于实际 buffer 数 / 申请点无对应释放且位于循环内（实证 #3798 常量共用 ID 6；#2555 `id%11` 而 buffer>11；#1606 用错 event ID；#6123 `AllocEventID` 泄漏致池耗尽）。

### 子型 ④ 跨核同步覆盖不全
- 查什么：`CrossCoreSetFlag/CrossCoreWaitFlag` 的 **mode + flagId 映射**是否让等待方感知**全部**参与核——一核双 AIV 场景下 mode 4 flagId 8 只覆盖 AIV0、AIV1 的写未被等待方感知即构成核间 `RAW`/`WAW`；多核共享同一 GM 地址（如 `ClearWorkspace` 清零）时核间是否同步。何处：op_kernel 的 `CrossCore*` 调用与 AIV 分核逻辑、workspace 清零段。命中判据：给出「AIV_x 的写未被 AIC / 对端等待方感知」的静态推导（实证 #1723 mode4 flagId 8 只覆盖 AIV0，racecheck 1 `WAW` + 513 `RAW`；#797 少核路径只对首次 AIV 操作做入口同步）。

### 子型 ⑤ 同步与调度约束缺失
- 查什么：kernel 用 `SyncAll` 合并各核结果时，host 侧 tiling 是否 `SetScheduleMode(1)`——不设则无法保证所有参与核**同时驻留**，`SyncAll` 语义失效致卡死；涉及核间同步的算子是否如期设置调度模式。何处：op_host 的 `*_tiling*.cpp` 与 kernel 的 `SyncAll` 调用点成对核查。命中判据：kernel 有 `SyncAll` 而 host tiling 无对应 `SetScheduleMode(1)`（实证 #3937 full-load `rowsPerCore==1` 用 `SyncAll` 但 host 未设；#598 涉及核间同步的算子必须设 `schedule_mode=1`）。

### 子型 ⑥ 同步原语的作用域与消费者不匹配（v6.15 新增，**判据不是计数，是作用域**）
- **为什么单列**：前五子型问的都是「配不配平 / 方向对不对 / ID 冲不冲突 / 覆盖全不全 / 调度配没配」，本质是**计数与方向**问题；子型⑥ 问的是「**这对同步定义了哪条路径归它管**」——是**作用域**问题。四件套 `AllocEventID` / `SetFlag` / `WaitFlag` / `ReleaseEventID` 齐全、ID 互异、方向正确、完全不配平时，配对完整性检查会**全部放行**，缺陷就藏在这里。
- **判别三步（逐算子必跑）**：① 取同步四件套，求其**共同最内层块**（能同时包住这四行的最小作用域）；② 若该块是 `if` / `else` / 三元 / 模板分支，则这条同步边**只覆盖该分支**；③ 检查**该作用域之外**是否还有对**同一 buffer / 同一地址**的访问——有，则子型⑥ 成立（另一条路径复用同一 buffer 却无等价同步）。
- **命中判据**：可写出「同步四件套整体位于分支 X 内 → 分支 ¬X 复用同一 buffer 且无等价同步 → 该路径缺 P1→P2 边」的推导链。
- **实证**：#5836（FlashAttentionScore 内源 PSE 路径：`eventIdPseDropVToMte2B` 的申请 / Set / Wait / Release 全部被 `!this->pseInfo.pseEndogenous` 包裹，各一次、完全配平，但内源 PSE 路径走 `PseSlopeCopyIn` 时**完全丢失**这条 V→MTE2 边；`op_kernel/arch22/flash_attention_score_bn2gs1s2_b.h` 的 `ProcessVec1`）。
- **反证方式（防误判）**：证明分支外的同 buffer 访问（a）不存在，或（b）已被**另一条独立同步边**保护（须给出 `文件:行号` 与事件方向），或（c）该 buffer 在分支外被前序同步统一覆盖。**仅凭「另一分支看起来不会同时触发」不算反证**——两条路径在同一 kernel 内共存时，触发哪个由 tiling / 属性决定，静态不可排除。
- **与子型② 的分界**：子型② 是「边**根本不存在**或**方向错**」；子型⑥ 是「边**存在且正确**，但**管不到那条路径**」。同一处缺陷常被报成②，若四件套齐全则改判⑥——Gemini 发现的 #5836 即此类（早期多按②记）。

### 横切面：racecheck 门禁与事件 ID 池审计
- 查什么：新增 / 改动 kernel 是否跑 mssanitizer `racecheck` 且以**零告警**为门禁（本模式绝大多数实证均由 racecheck 一行地址级报告直接暴露）；事件 ID 池是否有容量审计；测试是否**批跑轮换 + 新进程首调**（竞态在「单跑首次」与「批跑轮换」下暴露最充分）。何处：tests/ut 框架与 CI 配置。命中判据：无 racecheck 步骤 / 无事件池容量检查 / 只跑单次随机 → 记为盲区（漏检面）。

## 5. 检视流程

1. **定界**：换算 op 目录、确认仓与 ref；按现象（卡死点 / racecheck 报告 / 偶现精度 / 输出为 0）反查优先子型；确认是否提供复现条件（子型④ 的双 AIV / 批跑）。
2. **枚举**：列出 op_kernel（按 arch 目录）/ op_host tiling / op_api / tests/ut 全部相关文件。
3. **触发词扫描**：按 `SetFlag`/`WaitFlag`/`CrossCore*`/`AllocEventID`/`ReleaseEventID`/`PipeBarrier`/`SyncAll`/`SetScheduleMode` 定位风险面（本地仓 grep；API 模式逐文件拉取后检查）。**「必须触发」：签名零命中时六子型清单仍须逐项核查完毕。**
4. **配对完整性检查（核心，覆盖子型①~⑤）**：对每个事件域统计 `set`/`wait` 次数与分支、对每个 `AllocEventID` 找 `ReleaseEventID`、对每块共享 buffer 找两次访问之间的同步边——找出**孤儿原语**。所有同步原语逐个人工确认配对与方向语义；事件常量逐个确认互异。
5. **作用域审计（子型⑥，与上一步并行、不可省）**：对每个「四件套齐全」的同步对，求共同最内层块 → 判断是否为分支 → 检查分支外是否有同 buffer 访问。**配对检查通过 ≠ 作用域正确**；只跑第 4 步会系统性漏掉这类缺陷。
6. **反证排除**：同步对已配平且方向正确、反向同步齐备（复用点有 V→MTE2 类反向边）、event 申请-释放成对且不在循环内、跨核覆盖全部核、`SyncAll` 有对应 `SetScheduleMode(1)`、子型⑥ 的作用域外访问已证明不存在或有独立同步保护。
7. **判定**：按第 7 节标准给 命中 / 观察项 / 反证排除。
8. **查重**（仅命中项）：用全局检索 API 按接口名 + `同步|SetFlag|WaitFlag|racecheck|WAW|RAW` 检索，比是否同机理；无同机理才立卡。
9. **业务可达性核查**（仅命中项）：判 B 等级、定业务影响类型、给处置建议；默认保守（无法证明不可达即记 B3），降档须附证据；B 不改 S×O。
10. **出报告**：按第 8 节模板落盘；静态结论附复现 / 排除方案（racecheck 命令、双 AIV / 批跑复现条件、事件池审计项）。

## 6. 风险定级（S×O）与业务影响评估（B 轴）

- **S**：S4（挂死 / 永不返回——`WaitFlag` 永久等待、同步卡死；或**静默错误结果**——缺同步读到旧值，任务"算完"但结果错）；S3（偶发精度错——竞态时隐时现，批跑通过率轮换）；S2（隐患 / 未被触发的覆盖不全——双 AIV 冗余一致掩盖 `WAW`）。
- **O**：O3 = ≥2 条独立实证；O2 = 1 条独立实证；O1 = 仅静态扫描命中或团队笔记（实证 = 确认对应 issue / PR，或经跨仓、跨分支核验确认的缺陷记录，同权计入）。静态推演命中且无实证默认 **O1**；升档须在报告给出实证依据。
- **风险 = S×O**：≥6 高；3/4 中；1/2 低。FP-G02 基准：模式卡整体 S4×O3=12（高）；纯静态命中 S4×O1=4（中，暂定，复现实证后复评）。

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

- **签名 / 触发词命中 ≠ 成立**：`SetFlag`/`WaitFlag`/`PipeBarrier` 在算子仓命中量极大（绝大多数正常同步）——命中仅为定位提示，须人工确认「配对是否完整、方向是否正确、覆盖是否全核」；`PipeBarrier<PIPE_V>` 存在**不代表**跨管线依赖被保护（它只保证 V 内部）。
- **三种判定**：**命中**（可静态证缺陷路径）：「某路径 set≠wait」「共享地址两次访问间无对应事件边」「事件常量冲突 / 取模范围不足 / Alloc 在循环内无 Release」「`CrossCore*` 未覆盖全核」「有 `SyncAll` 无 `SetScheduleMode(1)`」「同步四件套齐全但整体被分支独占、作用域外复用同一 buffer」任一推导链完整 + 触发输入静态可构造 → 立 Bug 卡；**观察项**：竞态需实测 racecheck 复现、或依赖运行时双 AIV 冗余 → 记录并附复现方案，按 S4×O1 暂定；**反证排除**：同步配对齐备方向正确、反向同步齐备、事件申请释放成对、全核覆盖、调度约束齐备、作用域外访问不存在或有独立同步保护 → 写出反证理由（防护面证据）。
- **子型⑥ 的反证门槛更高**：证明「另一分支不会同时触发」**不构成反证**（走哪条路径由 tiling / 属性决定，静态不可排除）；须给出「作用域外无同 buffer 访问」或「该访问由另一条方向正确的同步边保护」的 `文件:行号` 证据。
- **「单跑通过」不是反证**：竞态在「单跑首次」与「批跑轮换」下暴露最充分——单次随机通过与双 AIV 冗余写一致**都不能证明无缺陷**；须以 racecheck 零告警为准。
- **本型与 G01 的区分以「有无 racecheck 地址级报告 / set-wait 配平异常」为准**：纯 host 级超时 / 死循环不属本条。
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
  - `{文件}:{行号}`：{现象（孤儿 set/wait、共享地址缺事件边、事件常量冲突、Alloc 无 Release、CrossCore 覆盖不全、有 SyncAll 无 SetScheduleMode、同步四件套被分支独占）}
  - 防护面记录（反证检查结果）：{文件}:{行号}
- **FP-G02 模式编号**：FP-G02 核间/流水同步缺失或配对不完整（子型①~⑥ + 横切面编号）
- **S×O 风险定级**：S4（挂死 / 静默错误结果）× O1（静态命中无实证）= 4，中（暂定，复现实证后复评）
- **证据等级**：{静态可证 / 需实测确认}｜{一句话理由}
- **业务影响评估（B 轴）**：可达性 B{3|2|1}（{一句话判据}）｜ 业务影响：{静默精度损失/任务失败中断/性能退化/仅可观测性}｜ 证据：{调用方/公开负载/为何不可达}｜ 处置建议：{尽快修/排期修/记录}
- **故障机理推导链**：{共享地址 A 被 P1 写、P2 读 → 两者间无 P1→P2 事件边 → P2 读到旧值 / 永久等待 的逐步推导}；子型⑥ 另须写明：{四件套共同最内层块 → 该块是哪个分支 → 作用域外的同 buffer 访问点}
- **触发条件可达性分析**：{双 AIV / 批跑轮换 / 新进程首调 / 固定 UB 复用 的具体构造}
- **建议修复方案**：{补齐 set/wait 配对、改用正确方向事件、常量改互异 ID、Alloc 移出循环并配对 Release、CrossCore 覆盖全核、host 补 SetScheduleMode(1)、把同步四件套提到分支外或为另一分支补等价同步；同管线同址补 PipeBarrier<PIPE_X>}
- **测试拦截建议**：mssanitizer racecheck 零告警门禁；同步原语配平断言；事件 ID 池审计；双 AIV / 多核 workspace 场景单独成类；批跑轮换 + 新进程首调
- **Agent 误判记录**：{被推翻的假设 → 推翻证据 `[文件]:[行号] [代码行]`；无则「无」}
- **GitCode 查重**：{全局检索 API 结论，无同机理 issue 才立卡}
```

### 检视报告结构

```markdown
# FP-G02 检视报告：{aclnn 接口名}（YYYY-MM-DD）
## 一、执行概览（仓/ref/HEAD、现象与优先子型、文件清单、判定统计：命中 X / 观察项 Y / 反证排除 Z；命中项 B 轴分布 B3×a / B2×b / B1×c）
## 二、命中明细（Bug 卡，按第 8 节字段，每卡含 B 轴业务影响评估）
## 三、观察项（表：# / 子型 / 文件:行号 / 存疑点 / 复现方案）
## 四、反证排除（表：子型点 / 反证理由 / 防护面证据）
## 五、复现与熔断建议（racecheck 命令、双 AIV / 批跑复现条件、事件池审计项）
```

> 报告须在「执行概览」标注证据等级分布（静态可证 X / 需实测确认 Y），并在文末单列「Agent 误判记录」小节（无则写「无」）。

报告落盘到当前任务工作区，建议命名 `FP-G02检视_{接口名}_YYYYMMDD.md`。

## 9. 示例速览：aclnnGroupNormSwish

- **定位**：`cann/ops-nn` → `norm/group_norm_swish/`（op_host：*_def.cpp / *_infershape.cpp / *_tiling*.cpp + config/<soc>/*_binary.json；op_kernel：`arch35/group_norm_swish_base.h`；tests/ut；docs）。
- **检视面提示**（引导，不预设结论，仍须逐点核查；行号以本地 HEAD 为准）：
  - 子型②：`arch35/group_norm_swish_base.h` 的 `CastMeanAndRstd`——**标量（S）写 mean/rstd 之后、vector（V）读之前**是否 `SetFlag/WaitFlag<HardEvent::S_V>`。实证 #5960 即此处缺 `S_V` 硬事件同步（修复 PR `!10683`），本地若已含该同步对，记为防护面证据；
  - 子型③：核事件常量定义是否两两互异、`AllocEventID` 是否配对 `ReleaseEventID` 且不在循环内；
  - 子型①②：核「同一块 UB 的两次访问之间」是否放了**以等待方为视角**的事件边，`PipeBarrier<PIPE_V>` 是否被误当作跨管线保护。
- 任何一点的最终判定以第 4/5/7 节口径为准，禁止凭算子类型直接下结论。

## 10. 能力边界与自检（v3.8）

### 能力边界

- **静态可证**：清单里能在源码内给出「`文件:行号` + 推导链」的部分，按第 7 节判据出卡。
- **需实测确认**：竞态是否触发、双 AIV 是否冗余一致、racecheck 报告，均依赖运行时观测——只能记观察项并附实测用例（证据等级见第 7 节）。
- **不覆盖**：本模式以外的机理（边界见第 0 节）与仓外框架侧行为；`TRIAGE.md` 只负责收敛候选，不构成判定依据。
- **找不到 ≠ 没有**：按清单未命中只说明「本轮未发现」，不得表述为「该算子无此缺陷」；无 racecheck 门禁时「未见告警」不得作为无缺陷证据。
- **本模式不覆盖 host / 集群级同步**（`HCCL_*_TIMEOUT`、通信等待超时）——那属 FP-G01；本模式只管 **kernel 级同步原语**。

### 自检

```bash
python3 scripts/gen_triage.py --check                          # 分诊表与映射一致
python3 scripts/scan_fp.py --only FP-G02 --format json <目标文件>  # 签名候选（非结论）
python3 scripts/scan_sync.py <目标文件或目录>                      # 配对完整性检查（孤儿原语，子型①~⑤）
python3 scripts/scan_sync_scope.py <目标文件或目录>                # 作用域审计（四件套是否被分支独占，子型⑥）
python3 scripts/scan_sync_scope.py --self-test                   # 作用域审计冒烟（分支独占必报 / 干净样例零误报）
python3 scripts/verify_lines.py <报告.md> --root <被检仓>        # 行号校验
python3 check_fault_patterns.py                                # 全库守门
```

> **两条检查必须分别跑**：`scan_sync.py` 判「配不配平 / ID 冲不冲突」，`scan_sync_scope.py` 判「这条同步边管不管得到那条路径」。
> 前者全绿**不代表**后者无候选——子型⑥ 的典型形态（#5836）恰恰是四件套完全配平、被纯计数检查无条件放行的那一类。

### 工作量与抽样（v4.0）

- **深度档：深度**（索引 `depth` 字段）——全量核查，不抽样。全部映射点 / 分支逐条过；单模式命中 > 50 处时按文件分片，并在报告写明分片口径。
- **报告必填**：抽样口径（全量 / 每点前 N 处 / 每类 N 例）+ 停止点记录；未写口径视为未完成。

## 11. 已知缺陷案例库（**已外置**，见 references/case-library.md）

> **本型共 %d 条已确认缺陷**，完整内容（触发 / 根因 / ✅ 修复范式 / 针对性发现 / 最小复现锚 / 实证）
> 已移至第 3 层：[`references/case-library.md`](references/case-library.md)（289 行）。
>
> **为什么外置**：案例只在**确认命中之后**才需要翻（看同类怎么修），前半部分的清单/流程/定级/产出模板
> 已完整可用。原内联时占本 skill 的 49%（265/536 行），是唯一该拆未拆的巨型章节。
>
> **怎么用**：① 先按第 4 节清单核查出候选 → ② 命中后按下方索引跳转，看同类缺陷的修复范式与复现锚；
> ③ 真锚在 [§15 实证加深](#15-实证加深v54真实修复锚--反向排除项)，**不在**案例库里。

### 案例索引

- [案例 1｜标量写与 vector 读之间缺 S_V 硬事件同步 —— ops-nn #5960（group_norm_swish，PR !10683）](references/case-library.md)
- [案例 2｜一核双 AIV 清同一 workspace 无同步（VerifyResult 通过但隐患） —— ops-nn #5513（conv3d_backprop_filter_v2）](references/case-library.md)
- [案例 3｜同地址两次访问缺 PipeBarrier（WAW + RAW） —— ops-nn #3802（conv3d_v2，PR #6896）](references/case-library.md)
- [案例 4｜固定 UB buffer 复用缺反向同步（V→MTE2） —— asc-devkit #1762（matmul_gelu）](references/case-library.md)
- [案例 5｜用错同步边（SToMTE3Sync 覆盖不到 V→MTE3） —— ops-math #3604（RadixTopK）](references/case-library.md)
- [案例 6｜SetFlag 用错 event ID 致永久等待 —— ops-nn #1606（quant_batch_matmul_v4 perblock）](references/case-library.md)
- [案例 7｜两个事件常量共用同一 ID —— ops-transformer #3798（chunk_gated_delta_rule，PR #8802）](references/case-library.md)
- [案例 8｜AllocEventID 泄漏（循环内申请不释放）+ V 链缺 PipeBarrier —— ops-transformer #6123（fused_infer_attention_score，PR #13801）](references/case-library.md)
- [案例 9｜mode4 flagId 只覆盖部分 AIV（跨核覆盖不全） —— asc-devkit #1723（matmul_s4）](references/case-library.md)
- [案例 10｜SyncAll 未配 SetScheduleMode(1)（调度约束缺失） —— ops-nn #3937（add_layer_norm_quant，PR #7200）](references/case-library.md)
- [案例 11｜同步四件套被条件分支独占，另一路径整体失同步（作用域错配） —— ops-transformer #5836（FlashAttentionScore）](references/case-library.md)
- [案例 12｜同 pipe 同址漏 PipeBarrier（「同管线天然安全」的误读） —— ops-transformer #12772 / #12555 / #13398（stage1PingBuf）](references/case-library.md)
- [案例 13｜零迭代分支绕过循环体内的同步等待（zero-trip）—— 26-05（FlashAttentionScoreGrad）](references/case-library.md)

## 15. 实证加深（v5.4）：真实修复锚 · 反向排除项

> 取证基线：ops-transformer `@d5c0683`（2026-11-05 本地核验）。仓为浅克隆，commit 列记当前 master HEAD，非修复提交 SHA。

### 15.1 真实锚（修复后形态）

| 案例 / issue | 真实锚（文件:行号 @commit） | 要点 |
|---|---|---|
| #5966 零迭代绕过循环内同步（现网 26-05，**仅 PR 无 issue**） | `attention/flash_attention_score_grad/op_kernel/arch22/flash_attention_score_grad_s1s2_bn2.h:3147-3151` @d5c0683 | `if (rp.SFTS1Times == 0) { AscendC::WaitEvent(SYNC_C1_V1_FLAG); AscendC::WaitEvent(SYNC_C1_V1_FLAG); return; }`——**修复后形态**：零迭代提前返回前补齐两笔后置等待。判据：① 循环上界能否为 0；② 循环前是否已下达异步工作；③ 零次路径是否有**等价且等量**的等待（本案两次对应 MM1 两笔，只补一次同样错）。同文件 `:3131`/`:3153` 是 `SFTS1Times` 的两个赋值来源，`:3159` 才是被绕过的循环。 |

### 15.2 反向排除项

| 反向排除项 | 所需负向证据 |
|---|---|
| 循环上界数学上不可能为 0 | 给出上界来源的约束行 `[文件]:[行号]`（如由 `CeilDiv` 且被除数恒 ≥1、或前置校验拒绝空态） |
| 零迭代时循环前没有在飞工作 | 给出循环前无 `IterateAll`/`SetFlag`/异步搬运的 `[文件]:[行号]` 区间说明 |
| 零迭代路径已被更外层的等待覆盖 | 给出外层 Wait 位置与它晚于零迭代返回点的 `[文件]:[行号]`；「外层总会等」不算 |
| 该循环非「有后置条件」型（纯计算无异步） | 给出循环体内无任何跨 pipe 原语的 `[文件]:[行号]` |

## 16. 判据层（L2/L3）：出用例与判读前必读 <!-- BEGIN DETECT-SECTION (generated by scripts/sync_detect_section.py; do not edit) -->

> 生成物，勿手改（C42 校验）。完整判据见 [references/detect-l2-l3.md](references/detect-l2-l3.md)。

- **L2**：轴 并发/同步/执行序列/内存｜观测 sanitizer-racecheck/bitwise｜至少 4 例
- **L3 `sanitizer-racecheck`**：K2(假绿)san 符号数必须实测为 0，否则 racecheck 同样假绿
- **L3 `bitwise`**：K638(假 FAIL)+inf 的 log-sigmoid 输出是 -0.0：按位比对必须先归一符号零

> 判 FAIL 先排「假 FAIL」、判 PASS 先排「假 PASS/假绿」。**不查 L3 就出结论 = 报告作废。** <!-- END DETECT-SECTION -->
