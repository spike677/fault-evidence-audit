---
name: "fpa21-tiling-state-review"
description: "基于 FP-A21「tiling 状态跨调用/跨线程污染」对指定算子做 tiling 状态生命周期检视：清点匿名 namespace 可变全局与全局 TilingData，核查路径赋值完备性、载体归属、链接性、成对实现连带，并给序列化与并发验证方案。当用户给出算子名要求查 tiling 状态残留、连续执行不同 shape 后结果不对、tiling 失败或并发偶发精度问题时使用。"
---

# FP-A21 tiling 状态污染检视（fpa21-tiling-state-review）

对用户指定的算子做 FP-A21 专项源码检视：先清点 tiling 里**语义属于 per-call、载体却是 per-process** 的状态，再按清单逐项核查「每条路径是否都给它赋值」「它跟着对象走还是跟着动态库走」「成对实现是否复制了同一写法」，产出状态生命周期表 + 序列化/并发验证方案。**本模式特殊纪律：① 命中的是「载体选错」，不是「某一行写错」——只改赋值位置（如把 `flag = true` 提到 if 外）只是治标，载体仍是全局就必须在报告里点明；② 候选是「非 constexpr 的可变全局」本身，它在多数算子里确实无害（只写一次、或每次全路径覆盖），判据是**是否存在某条路径不写它**或**是否可能并发进入**，两者都不成立才能反证排除；③ 撤否必须有负向证据，见第 7 节。**

## 0. 与相邻模式的边界

| 模式 | 它管什么 | 本模式不管的部分 |
|---|---|---|
| FP-A07 tiling 条件判断错误 | 条件表达式本身写错（`<`/`<=`、off-by-one、奇异 shape） | 条件是对的、但**读到的状态来自另一次调用**——归本模式 |
| FP-A19 多 tiling 路径覆盖盲区 | 新注册的模板从没被测试执行到 | 单条模板内即可复现的状态污染——归本模式 |
| FP-G02 核间/流水同步缺失 | kernel/host 侧 `SetFlag`/`WaitFlag` 配对、事件 ID、跨核覆盖 | host 侧变量生命周期（本模式**没有同步边可缺**）；但 racecheck 等检测手段可复用 |
| FP-A05 脏数据/数据踩踏 | 结果层「读到脏值」的现象 | 本模式给出可扫描的机理判据（TU 级可变全局），A05 是其结果面 |

判不清时按「缺陷的**根因所在层**」归属：条件写错→A07；路径没测到→A19；同步边缺了→G02；**状态该归谁搞错了→本模式**。

## 1. FP-A21 模式卡摘要（检视依据，源自本库 `patterns/FP-A/FP-A21.md`，v3.1）

- **编号 / 名称**：FP-A21 tiling 可重入性缺失致跨调用/跨线程污染（TU 级可变全局）｜ **类别**：精度 ｜ **风险**：高（S3×O3=9）｜ **状态**：活跃 ｜ **来源**：rope_grad PR #8705 根因复核 + 四仓静态扫描（2026-10-19）
- **适用声明头**（照抄卡片）：仓 All ｜ 侧别 Tiling,Host ｜ 载体 Tiling源码,aclnn源码 ｜ 触发 TilingData|tilingKey|namespace ｜ 默认启用 true
- **一句话机理**：per-call 的状态被放进 per-process 的容器。串行表现为「上一次调用的值残留到这一次」（分支不写它就永远读旧值），并发表现为「两个线程在同一块内存上读写改写」。
- **关键判据**：静态存储期变量的复位只有两个时机——静态初始化（模块加载时一次）、显式赋值真的被执行。**不存在「调用结束自动清空全局变量」这种机制。**

## 2. 检视输入与算子定位

输入：算子名 / aclnn 接口名（可选：指定仓库与分支）。
定位：`<repo>/<算子目录>/op_host/`，重点文件为 `*tiling*.cpp`，以及 `*_tiling.h`（判断状态是不是类成员）。

```bash
git grep -n "namespace *{" -- <op>/op_host/*tiling*.cpp       # 找匿名 namespace 边界
git grep -nE "^\s*(uint64_t|int64_t|uint32_t|int32_t|bool|size_t)\s+\w+\s*(=|;)" -- <op>/op_host/*tiling*.cpp
git grep -n "TilingData\s\+tiling\s*;" -- <op>/op_host/*tiling*.cpp
```

## 3. 取数方式（Important）

- 优先读**被检分支的真实 HEAD**（`git show <ref>:<path>` 或 sparse checkout），不要读本地陈旧副本；行号必须来自同一 commit。
- 行号证据用 `文件:行号` 字面量，报告末尾跑 `scripts/verify_lines.py` 校验。
- 类成员 vs 全局必须看头文件确认：`isTndLayout_` 带下划线且在 class body 内才是成员，`isTndLayout` 在 `.cpp` 顶层就是全局。

## 4. 状态污染检视清单（每点：查什么 → 何处 → 命中判据）

### ① 可变全局清点（映射点①）

查：`op_host/*tiling*.cpp` 文件作用域 / 匿名 `namespace` 内的**非 constexpr 可变变量**。
何处：`.cpp` 顶部 `namespace {` 块、`namespace optiling` 块内的顶层定义。
判据：命中即列清单（**候选，不是缺陷**）。`constexpr` / `static const` / `thread_local` / 类成员一律不计。

### ② 路径赋值完备性（映射点②）——本模式的判别核心

查：清单里每个变量，**是否在每一条执行路径上都被赋值**。
何处：所有写点 + 所有分叉（`if (xDimNum == 3)`、`layout ==` 系列、`hasX` 判断）。
判据：存在一条路径**不写**该变量、后续又要读它 → **命中**（这正是 #3758 的形态：4D 分支压根没有写操作）。
记录格式：`变量名 | 写点行号清单 | 未覆盖路径 | 该路径读取点行号 | 后果`。

### ③ TilingData 载体归属（映射点③）

查：`XxxTilingData tiling;` 是全局还是类成员；若是全局，`set_*` 与 `SaveToBuffer` 之间隔了多少行/多少个函数调用。
判据：全局 + 窗口跨越函数调用（如 `set_batchSize` 在 `TilingLayoutSplit`、`SaveToBuffer` 在 `DoOpTiling` 末尾）→ 命中（串写窗口大）。窗口内还有可选输入分支、二次 set，风险更高。

### ④ 链接性与声明位置（映射点④）

查：变量声明在匿名 `namespace {}` 内（内链接、每 TU 一份）还是 `namespace optiling` 内（**外链接**）。
判据：外链接的全局更暴露（任何引用该名字的 TU 都指向同一块内存），在报告里单列。同型实现分处两个 TU 时，**两份状态互不影响**，不要把它们当成一处缺陷合并定级。

### ⑤ 成对实现连带核查（映射点⑤）

查：同一算子的**前向 / 反向 / 镜像实现**（如 `rope_interleaved_tiling.cpp` 与 `rope_interleaved_grad_tiling.cpp`、`tril_tiling.cpp` 与 `triu_tiling.cpp`）是否复制了同一写法。
判据：一处命中 → 必须连带核查其成对实现，同一份报告里并列给出。**这是本模式最容易漏的一步**：修了后向、前向还在。

### 横切面：并发可重入性

查：`DoOpTiling` 及其调用的所有 `static` 函数是否读写上述全局；框架侧是否有锁。
判据：无锁 + 读写全局 → 结构上不可重入（**确凿**）；「并发是否真的发生」需打桩确认（见第 5 节 Step 4），未确认前只记观察项，不以「命中并发缺陷」出卡。

## 5. 检视流程

**Step 0 定位**：确认算子目录、分支、HEAD，记录 `文件:行号` 基准。

**Step 1 清点**：跑第 4 节 ① 的命令，产出可变全局清单（变量名 / 类型 / 声明行 / 链接性 / 是否 TilingData）。

**Step 2 逐点核查**：按 ①~⑤ 顺序过，每点给出「命中 / 观察项 / 反证排除」三态判定，每态都要有证据行号。

**Step 3 业务可达性核查**：对每个命中项判断真实业务能否走到（B3/B2/B1），依据是主流框架默认路径、典型 shape 组合、多流并发形态；无法证明不可达即记 B3。

**Step 4 验证方案设计**（本模式必做，缺此项视为未完成）：
- 序列化用例：同进程连续调用，顺序覆盖「3D→4D」「带可选输入→不带」「fp16→fp32」「新路径→旧路径」；
- UT 顺序：`--gtest_shuffle --gtest_repeat=50`；
- 并发压测：多线程每线程独立 stream，只调 aclnn 第一段 `GetWorkspaceSize`（tiling 入口，host 同步）；
- 并发自证：`DoOpTiling` 首尾 `atomic` 进入计数，`peak > 1` 才算并发成立。

**Step 5 定级出报告**：S×O 取固有风险，修复状态单列，B 轴只给优先级建议。

## 6. 风险定级（S×O）与业务影响评估（B 轴）

- **S**：串行路径可稳定复现静默错算记 **S3**；并发变体若能坐实越界（`tilingKey` 与 `dtypeSize` 独立串味，组合出真实 dtype 不存在的错配）可升 **S4**，**未坐实不升**。仅导致 tiling 报错且无错误结果产出，按 S2 复核。
- **O**：真实训练/推理存在多 shape 混合调用 → O3；仅图模式可达 → O2；仅在特定编译顺序下可达 → O1。
- **修复状态单列**，不回写 P 级（PR 只改赋值位置 = 治标，标「部分修复」）。

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

- **出卡条件**：① 存在一条路径不写该状态却读它（映射点②），或 ② 全局 TilingData 的 `set_*`→`SaveToBuffer` 窗口跨越函数调用且窗口内可能被并发进入（映射点③，需 Step 4 自证）。
- **观察项**：命中 ① 但**该路径必然返回失败**（读到的脏值不影响任何有效输出）；或并发结构上不安全但未自证并发发生。
- **反证排除**：变量是 `constexpr` / `static const` / `thread_local` / 类成员；或**每条路径都无条件赋值且无并发可能**——后者须给出全部写点行号。
- **不要这样判**：把「用了全局变量」直接等于缺陷；把「`isTndLayout` 这类单个 flag」当成全部问题（同文件其余 16 个标量 + TilingData 对象才是大头）；把前向与后向的两份全局合并成一处定级。

### 判定纪律补充（v3.6）：非对称增减、证据等级与误判记录

**增减不对称**：允许追加候选（有据即可，错了可由用户排除）；**撤销或否决候选必须附 `[文件]:[行号] [代码行]` 负向证据**。无证据的「看起来没问题」一律记为「未核查」，不得计入反证排除，也不得据此下调等级——否决造成的漏报用户不可见、不可恢复。

- **证据等级**（Bug 卡必填）：`静态可证` = 推导链完整且触发输入可静态构造；`需实测确认` = 依赖运行时输入规模、设备行为或环境差异。标 `需实测确认` 的条目**不得以「命中」名义出卡**，按观察项记录并附实测用例。
- **Agent 误判记录**（Bug 卡必填）：本次被推翻的假设、推翻它的证据（`[文件]:[行号] [代码行]` 或实测输出）、判定标准是否随之修订；无推翻写「无」。
- **误判回流**：同类误判在 3 次检视中重复出现，登记至 `cases/misjudgments.jsonl`（字段见 `cases/README.md`），并在本模式判定标准中新增对应防线；守门 C19d 校验台账字段合法。

## 8. 产出模板

### Bug 卡字段（命中项必备）

```text
BUG-YYYYMMDD-XX {算子名}（{仓}，{新增/存量}）
- 映射点：①/②/③/④/⑤（可多选）+ 子型编号
- 触发条件：{具体调用顺序或并发形态，必须是可构造的}
- 根因：{哪个状态、语义是 per-call 却存在 per-process 载体}（`文件:行号`）
- 证据链：写点清单 → 未覆盖路径 → 读取点（三处行号）
- **业务影响评估（B 轴）**：B3/B2/B1 + 业务影响类型 + 处置建议
- **证据等级**：静态可证 / 需实测确认（+ 实测用例）
- **Agent 误判记录**：{被推翻的假设 + 推翻证据；无则写「无」}
- 修复建议：状态类成员化（首选）/ 加锁 / `thread_local`（仅治串行残留）
- 处置状态：未修复 / 部分修复（只改赋值位置）/ 已修复
```

### 检视报告结构

```text
# FP-A21 检视报告：{算子名}（YYYY-MM-DD）
## 一、执行概览（仓/ref/HEAD、可变全局清单规模、判定统计：命中 X / 观察项 Y / 反证排除 Z；
        证据等级分布（静态可证 X / 需实测确认 Y）；命中项 B 轴分布 B3×a / B2×b / B1×c）
## 二、状态生命周期表（变量 | 声明行 | 链接性 | 写点 | 未覆盖路径 | 读取点 | 后果）
## 三、命中明细（Bug 卡，每卡含 B 轴业务影响评估）
## 四、观察项（表：# / 映射点 / 文件:行号 / 存疑点 / 实测方案）
## 五、反证排除（表：映射点 / 反证理由 / 负向证据行号）
## 六、验证方案（序列化顺序矩阵 / UT shuffle / 并发压测 / 打桩自证）
## 七、成对实现连带结论（前向/反向/镜像是否同型）
```

## 9. 示例速览：RotaryPositionEmbeddingGrad（ops-transformer）

`posembedding/rotary_position_embedding_grad/op_host/` 下两个 TU，各一份状态：

- `rope_half_grad_tiling.cpp:57` `bool isTndLayout = false;`（匿名 namespace，内链接），唯一写点在 `:150` 的 3D 分支内 → **4D 路径不写，读到上一次的 `true`**。
- 污染后的实际后果（4D BNSD `{2,4,64,10}`）：`dimB=2, dimS=1, dimN=4, dimD=64`（D 取到原 S）；4D BSND `{2,64,4,10}` 则是 D 取到原 N（`1/64/2/4`）。命中 SBND 分支后多为**静默错算**，仅少数形状落 `else` 报 tiling failed。
- 同文件 `:56` 全局 `RotaryPositionEmbeddingGradTilingData tiling;`；`rope_interleaved_grad_tiling.cpp:106` 的同类对象在 `namespace optiling` 内（**外链接**），且该文件另有 16 个可变全局（`:64-80`）。
- 修复 PR #8705 把写点提到分支外做无条件求值（`isTndLayout = (xDimNum == DIM_THREE)`）——串行问题解掉，**载体未换，并发仍在**。

## 10. 能力边界与自检（v3.8）

### 能力边界

- **静态可证**：能给出「写点清单 + 未覆盖路径 + 读取点」三段行号的，按第 7 节出卡。
- **需实测确认**：并发是否真的发生、越界是否真的出现，属运行时行为，只能记观察项并附实测用例（见第 5 节 Step 4）。
- **不覆盖**：kernel 侧同步原语配对（FP-G02）、条件表达式写错（FP-A07）、多模板覆盖盲区（FP-A19）。
- **找不到 ≠ 没有**：未命中只说明「本轮的清单命中的文件里没有」，不得表述为「该算子无状态污染」；抽样核查须写明抽样口径。

### 自检

```bash
python3 scripts/scan_fp.py --only FP-A21 --format json <目标文件>   # 签名候选（非结论）
python3 scripts/verify_lines.py <报告.md> --root <被检仓>           # 行号校验
python3 scripts/gen_triage.py --check                              # 分诊表与映射一致
python3 check_fault_patterns.py                                    # 全库守门
```

### 工作量与抽样（v4.0）

- **深度档：深度**（索引 `depth` 字段）——全量核查，不抽样。清单 ① 全文件清点，②~⑤ 逐变量逐路径过；单个算子可变全局 > 50 处时按文件分片，并在报告写明分片口径。
- **报告必填**：抽样口径（全量 / 每点前 N 处 / 每类 N 例）+ 停止点记录；未写口径视为未完成。

## 11. 已知缺陷案例库：触发条件 / 根因 / 修复范式 / 针对性深挖（v5.1）

### 案例 1｜连续执行 3D TND → 4D BNSD，4D 被按 TND 解析 —— ops-transformer #3758

- **触发条件**：同一进程内先调用 3D TND（`xDimNum == 3`），再调用 4D BNSD/BSND；单算子用例因「一进程一 shape」无法复现。
- **根因**：`isTndLayout` 是匿名 namespace 内的 TU 级可变全局，唯一写点在 3D 分支体内；4D 路径没有任何写操作，读到上一次的 `true`，于是 `dimD` 从 `GetDim(3)` 变成 `GetDim(2)`，D 维取到原 S 或原 N。
- **修复范式**：把赋值改为无条件求值 `isTndLayout = (xDimNum == DIM_THREE);`（PR #8705）。**这是治标**：载体仍是全局，并发与其余 16 个标量未处理；正解是把状态搬进 tiling 类成员，与同仓 regbase 类的 `isTndLayout_` 一致。
- **针对性发现**：UT 用例按「4D 在前、3D 在后」的声明序编写（`test_rotary_position_embedding_grad_tiling.cpp` 前三个 4D、TND 放最后），gtest 按声明序执行 → 顺序依赖被掩盖，全绿属运气；`--gtest_shuffle` 可当场证伪。
- **最小复现锚**：`rope_half_grad_tiling.cpp:57`（声明）、`:150`（唯一写点）、`:330`/`:355`（读取点）；同型 `rope_interleaved_grad_tiling.cpp:80`/`:248`/`:359-364`。
- **实证**：ops-transformer #3758（PR #8705 已合入）；2026-10-19 复核确认载体未换。
- **本仓实测锚（2026-11-05 核验，@ops-transformer HEAD `d5c0683`）**：
  - `posembedding/rotary_position_embedding_grad/op_host/rope_half_grad_tiling.cpp:57`（`bool isTndLayout = false;` 匿名 namespace 内 TU 级全局）、`:150`（**修复后形态** `isTndLayout = (xDimNum == DIM_THREE);` 无条件求值）、`:337`/`:362`（读取点，`:362` 即 `dimD = isTndLayout ? GetDim(DIM_TWO) : GetDim(DIM_THREE)` 的 D 维错取现场）。
  - **同族兄弟算子**：`posembedding/apply_rotary_pos_emb_grad/op_host/apply_rotary_pos_emb_grad_tiling.cpp:199` 已把状态做成**类成员** `isTndLayout_` 并无条件赋值，且 `:202`/`:209` 对「attr 与 shape 维度不匹配」显式返回 `GRAPH_FAILED`——**这是本案的正确解法样板**（治本 = 状态进类成员，而非修全局赋值），查同型缺陷时优先找这类同族实现做对照。

### 案例 2｜全局 TilingData 对象跨调用串写 —— 静态命中，成簇分布

- **触发条件**：tiling 用全局 `XxxTilingData tiling;` 承接本次参数，`set_*` 分散在多个 static 函数里，`SaveToBuffer` 在 `DoOpTiling` 末尾；并发 tiling 或中途返回失败后再次进入。
- **根因**：TilingData 语义是「本次调用的产物」，载体却是进程级单例；`set_*`→`SaveToBuffer` 窗口跨越整个切分计算，另一个线程的写入会混进来，device 侧收到「batchSize 来自 A、headDim 来自 B」这种单线程不可能出现的组合，索引计算越界。
- **修复范式**：改为 tiling 类的私有成员（框架每次 tiling 新建实例）；退路是 `DoOpTiling` 全程持锁。
- **针对性发现**：`rope_interleaved_grad_tiling.cpp:106` 的对象声明在 `namespace optiling` 内、匿名 namespace 之外，属**外链接**，比内链接更暴露；前向算子 `rotary_position_embedding/op_host/rope_interleaved_tiling.cpp:47` 有同款，ops-math `tril_tiling.cpp` / `triu_tiling.cpp` 是另一对镜像副本。
- **最小复现锚**：`rope_interleaved_grad_tiling.cpp:106`（声明）、`:369-386`（set_* 写点）、`:436`（SaveToBuffer）；`tril_tiling.cpp:45-56`（11 个全局标量，`key_value` 为事实 tilingKey）。
- **实证**：四仓静态扫描 2026-10-19（ops-transformer 1482 个 `op_host/*.cpp` 命中生产侧 3 个 / ops-math 2393 个命中 4 个，成簇：rope 前向+后向、tril+triu）；**逐条 issue 未立案**。

### 案例 3｜`tilingKey` 与 `dtypeSize` 独立串味，组合出真实 dtype 不存在的错配 —— 并发变体（需实测）

- **触发条件**：两个线程分别以 fp16 / fp32 调用同一算子（mode=1 路径），并发进入 `DoOpTiling`。
- **根因**：`tilingKey` 与 `dtypeSize` 是两个**独立**全局，各自被 `+=` / `=` 改写；交错后可能出现「`tilingKey` 已是 fp32 的 20020，但 `dtypeSize` 仍是 fp16 的 2」，或反之。任何单线程执行都不会产生这个组合，kernel 按该组合推导的元素数与 stride 必然错，fp16 数据被按 fp32 步长访问即越界。
- **修复范式**：状态类成员化；仅在上板确认越界后按 S4 出卡。
- **针对性发现**：`tilingKey` 的基址在 `:416`、dtype 加成在 `:420/423/426`、needBackward 加成在 `:397/399`、最终使用在 `:435`——四处写入分散在一条长路径上，交错窗口极大。
- **最小复现锚**：`rope_interleaved_grad_tiling.cpp:79`（`tilingKey` 声明）、`:64`（`dtypeSize`）、`:416-435`（读写链）。
- **实证**：**推演，未实测**。须按第 5 节 Step 4 跑并发压测 + 打桩自证，确认后再升 S4；未坐实前只作观察项。

### 语料基线与深挖起手式

- 扫描命令：`python3 scripts/scan_fp.py --only FP-A21 --format json <op_host 目录>`，命中即候选。
- 起手式：先看命中文件是否在**同一算子族内成簇**（前向/反向/镜像），再挑「写点在分支体内」的那个变量做路径完备性核查。
- 负向基线：`constexpr` 常量表、`thread_local`、类成员 `xxx_`、UT fixture 的 `CompileInfo` 均不算候选，扫描器自带排除。


## 15. 实证加深（v5.4）：真实修复锚 · 反向排除项

> 取证基线：ops-transformer `@d5c0683`（2026-11-05 本地核验）。仓为浅克隆，commit 列记当前 master HEAD。

### 15.1 真实锚（修复后形态）

| 案例 / issue | 真实锚（文件:行号 @commit） | 要点 |
|---|---|---|
| #3758 `RotaryPositionEmbeddingGrad` TND 布局跨调用残留（现网 26-09；PR #8705） | `posembedding/rotary_position_embedding_grad/op_host/rope_half_grad_tiling.cpp:57,150,337,362` @d5c0683 | `:57` `bool isTndLayout = false;`（匿名 namespace 内 **TU 级可变全局**）；`:150` `isTndLayout = (xDimNum == DIM_THREE);`——**修复后形态：无条件求值**，取代「只在 TND 分支置 true」；`:337` 与 `:362` 是读取点，`:362` 即 `dimD = isTndLayout ? GetDim(DIM_TWO) : GetDim(DIM_THREE)` 的 D 维错取现场。**注意**：这是治标——载体仍是全局，并发场景与其余同类标量未处理。**同族兄弟样板**：`posembedding/apply_rotary_pos_emb_grad/op_host/apply_rotary_pos_emb_grad_tiling.cpp:199` 已把状态做成类成员 `isTndLayout_` 并无条件赋值，且 `:202`/`:209` 对 attr 与 shape 维度不匹配显式返回 `GRAPH_FAILED`——**正解是把状态搬进类成员**。 |

### 15.2 反向排除项

| 反向排除项 | 所需负向证据 |
|---|---|
| 该状态在每次进入时都无条件赋值 | 给出赋值语句位于**所有分支之外**的 `[文件]:[行号]`，而非某个 `if` 体内 |
| 状态载体是 per-call 对象（类成员/局部），非 TU 全局 | 给出声明所在作用域 `[文件]:[行号]`：类成员需证明对象每次调用新建；匿名 namespace / 文件作用域全局直接算命中 |
| 该状态只有单一写点且写点在无条件路径上 | 给出唯一写点 `[文件]:[行号]` 及其所在控制流层级 |
| 同族其他标量也已处理（并发面） | 给出并发场景下无共享写的证据；仅修主状态不覆盖并发 |

## 16. 判据层（L2/L3）：出用例与判读前必读 <!-- BEGIN DETECT-SECTION (generated by scripts/sync_detect_section.py; do not edit) -->

> 生成物，勿手改（C42 校验）。完整判据见 [references/detect-l2-l3.md](references/detect-l2-l3.md)。

- **L2**：轴 执行序列/并发/同步｜观测 golden-utol/bitwise｜至少 4 例
- **L3 `golden-utol`**：K91(假 FAIL)inf==inf 被判超容差；溢出类用例整批假 FAIL；K508(假 PASS)judge 列写成 JSON 会被静默忽略 → 回落 dtype 默认容差（fp16 rtol=1e-3）
- **L3 `bitwise`**：K638(假 FAIL)+inf 的 log-sigmoid 输出是 -0.0：按位比对必须先归一符号零

> 判 FAIL 先排「假 FAIL」、判 PASS 先排「假 PASS/假绿」。**不查 L3 就出结论 = 报告作废。** <!-- END DETECT-SECTION -->
