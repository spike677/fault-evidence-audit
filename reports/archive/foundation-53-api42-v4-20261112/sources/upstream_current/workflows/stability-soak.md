# stability-soak：累积型 / 间歇性缺陷挖掘（多调用复现法）

> 用于「**单跑通过、批跑失败**」「**新进程首次调用才暴露**」「**同输入多次执行结果不同**」「**跑到第 N 次才报错**」的场景。
> 与 symptom-triage 的区别：symptom-triage 从**一次现象**收敛到模式；本 workflow 面对的是**现象在单次执行里不可见**的缺陷——必须先用「多调用探针矩阵」把它**逼出来**，再回挂模式。

## 为什么单次随机通过不能反证

这类缺陷的机制**多属 [FP-G02](../patterns/FP-G/FP-G02.md) 子型②③④**（跨流水同步遗漏 / 事件 ID 池泄漏 / 跨核覆盖不全），但有两个动力学把单次执行「洗白」：

- **工作区污染掩盖**：kernel 写 workspace 后无事件边，下游管线抢读。**首次调用** workspace 为新分配/全 0 → 立即暴露错值；**后续调用** workspace 残留上一次的正确数据 → 抢读也读对了，竞态被**掩盖**。（实证：ops-math #2868，STFT）
- **资源池耗尽**：`AllocEventID` 在循环体内只申请不释放，池容量有限（如 `MTE2_V` 池 = 8）；累计 > 池容量后越界。（实证：ops-transformer #6123）

推论：**「跑一次是好的」不是证据**。必须记录**序号与轮次**，并专门跑「冷进程首调」与「N 次 soak」两个窗口。

## 输入

- 目标算子 / kernel 文件（或嫌疑目录）；
- 现象与口径：单跑 x/N 通过、批跑是否轮换失败、失败用例是否固定、内存/耗时随次数是否上涨；
- 芯片与开关：arch35 / 950、确定性开关、图模式；能否上板或用软件仿真跑 mssanitizer。

## 阶段

### Stage 0 — 定性：先分「掩盖型 / 耗尽型 / 竞态型」

用三个区分性问题定机理，避免盲目扫：

1. **新进程只跑 1 次是否更易失败？** 是 → **掩盖型**（机理 A，工作区污染）。
2. **是否在 N 次 / 长序列后首现告警？** 是 → **耗尽型**（机理 B，资源池泄漏溢出）。
3. **是否与调用序号无关、纯随机？** → **竞态型**（机理 C，flagId 冲突 / 真随机调度）。
4. 打开 [TRIAGE.md](../TRIAGE.md) 的 **T4（稳定性）** 入口收敛候选，先落 FP-G02 为主模式，再看 [FP-G01](../patterns/FP-G/FP-G01.md)（挂死/超时）、[FP-A05](../patterns/FP-A/FP-A05.md)（脏数据）、[FP-A06](../patterns/FP-A/FP-A06.md)（确定性开关）作边界。

### Stage 1 — 静态前置：孤儿原语扫描（只作参考，非结论）

```bash
python3 ../scripts/scan_sync.py <kernel 文件或目录>
```

重点看三行输出：

- SUB③「循环内 `AllocEventID`」→ 指向**机理 B**；
- SUB③「事件常量同值冲突」→ 指向**机理 C**（flagId 冲突）；
- SUB①「`set ≠ wait` / 孤儿 ID」→ 配对失衡（单次内即可见，同时可给本类的**回挂锚**）。

**未命中 ≠ 无缺陷**：机理 A 的「写后抢读缺事件边」在本扫描里只可能给出弱提示，最终靠 Stage 2 逼出。命中/未命中都要在报告留痕。

### Stage 2 — 多调用探针矩阵（本 workflow 的核心）

按 Stage 0 的机理选探针；**每格必须记录：第几次出现 / 失败是否轮换 / 数值落点 / 内存或耗时曲线**。

| 探针 | 构造 | 观测判据 |
|---|---|---|
| **冷进程首调** | 全新进程，只跑 1 次目标算子 | 输出是否读出了「未写入的值 / 全 0」——机理 A 的**唯一暴露窗口** |
| **连续 N 次 soak** | 同算子、同输入连跑 N ≥ 事件池容量（`AllocEventID` 同名域如 `MTE2_V` = 8）**且** ≥ workspace 复用轮次（对齐多轮，如 N≥16） | 第 K 次首现告警/错值；峰值显存或 host 内存是否随次数**单调上涨**（泄漏叠加） |
| **规模扫描** | 同一用例逐步放大「尺度轴」（如 indices 元素数 M、KV 长度、`nfft`、批量） | 触发概率是否随规模**单调上升**（竞态窗口变宽，实证：ops-nn #5687） |
| **批跑轮换** | atk 批量跑 ≥5 用例、跑 ≥3 轮 | 失败用例是否**轮换出现**而非固定同一例 |
| **冷热对比** | 新进程只跑目标用例 vs 连续跑同族用例后再跑目标用例 | 结论相反 → 跨调用**状态残留**（实证：hccl #797） |
| **racecheck** | 上板/仿真跑 mssanitizer `racecheck` | `Potential WAW/RAW hazard` 的**地址级成对行号**——直接定位，可升级证据等级 |

### Stage 3 — 判定与回挂（子型 → 机理 → 探针）

| 机理 | 典型签名 | 回挂 |
|---|---|---|
| A 掩盖型 | 写 workspace/UB 后被另一管线（Cube/V）读，中间无 `SetFlag`/`WaitFlag`；首调暴露、后续掩盖 | FP-G02 子型②（跨流水同步遗漏） |
| B 耗尽型 | `AllocEventID` 在循环内、`ReleaseEventID` 不在同域/不在循环；N 次后越界 | FP-G02 子型③（事件 ID 泄漏） |
| C 竞态型 | 同一事件常量被两处 `SetFlag` 复用；OOM/优化版本才现 | FP-G02 子型③（flagId 冲突） |
| 跨核 | 等待方只覆盖部分参与核（双 AIV 的 AIV0/AIV1） | FP-G02 子型④（跨核覆盖不全） |

- **证据等级**：`racecheck` 给出成对行号 → 可记**静态可证**；仅有「复跑概率」→ 记**需实测确认**（观察项，附本探针矩阵的**具体构造与轮次**）。
- 与相邻边界：G01 管 host/集群级超时或死循环；A05 管脏数据**来源**（本 workflow 管依赖**顺序**）；A06 管确定性开关语义；机理 B 若表现为**显存/host 内存峰值累积**，定级走 [FP-D01](../patterns/FP-D/FP-D01.md) / [FP-D02](../patterns/FP-D/FP-D02.md)，本 workflow 只负责把它**逼出来**并给偏差口径。

### Stage 4 — 报告

```markdown
# {算子} 累积型/间歇性缺陷挖掘报告（YYYY-MM-DD）
## 一、现象与口径（单跑通过率 x/N / 批跑轮换 / 冷热对比 / 内存曲线）
## 二、定性结论（掩盖型 / 耗尽型 / 竞态型 + 依据）
## 三、静态扫描（scan_sync 三行输出 + 命中/未命中留痕）
## 四、探针矩阵结果（每格：第几次出现 / 是否轮换 / 数值落点 / 曲线）
## 五、判定与回挂（FP-G02 子型 → 机理 → 证据等级；边界排除 A05/A06/G01/D0x）
## 六、最小复现锚（可脚本化的轮次、N、规模）+ 建议补测项
```

## 停止条件与边界

- **单次随机通过不构成反证**；「本轮未命中」必须写明**跑了几轮 / 几次 / 冷热各几次**，否则视为未完成；
- 探针必须记录**序号与轮次**——不记序号就无法区分「掩盖」与「耗尽」；
- 现象与调用序号无关、且 racecheck 零告警 → 转 [symptom-triage](symptom-triage.md)；
- 本 workflow 只回答「是否是可复现的累积/间歇缺陷、属哪种子型」；**定级（S×O）与业务影响（B 轴）仍按目标 skill 第 6 节**。

## 实证锚（本 workflow 立论来源，均为仓内真实 issue）

- ops-math **#2868**（STFT）：MTE3 写 workspace 后无同步、Cube matmul 抢读；**首次调用 workspace 为 0 暴露、后续调用残留上次正确数据掩盖** → 批跑偶现。→ 机理 A / 子型②。
- ops-transformer **#6123**（fused_infer_attention_score）：`AllocEventID` 在 S2 循环内每迭代申请不释放（池仅 8），**累计 >8 次后越界**；并伴 V 流水未保序缺 `PipeBarrier`。→ 机理 B / 子型③。
- ops-nn **#5687**（SortLocalRuns，9.2.0 分支）：只发 `MTE3→MTE2`，**漏 `MTE3→V` / `MTE3→S`**；同一用例**连跑三次错行不同**、indices 数 M 越大概率越高。→ 机理 C / 子型②。
- ops-transformer **#4882**（Mlaprolog）：核间 `flagId` 冲突 → OOM 版本**偶现**精度失败。→ 机理 C / 子型③。
- ops-math **#3240**（FillDiagonalV2）：末核尾 tile GM 读越，间歇触发。→ 子型②（越界伴生）。
- hccl **#797**（AllGather）：**连续执行**时 1M 精度错误、**新进程只跑 1M 正常** → 跨调用缓冲复用残留。→ 机理 A / 子型④。

## 干跑示例（2026-10-18：linspace / STFT，静态层）

> **口径声明**：本机**无 NPU 工具链**（`torch_npu` / `torch` / `atk` / `npu-smi` 均不可用），故本示例只做到 **Stage 0 定性 + Stage 1 静态扫描**；Stage 2 的探针**构造**（可上板）见下节模板。**未跑设备侧，不给任何动态结论**——动态判定一律留待上板。
> 被检对象：`ops-math @8ade379`（`math/lin_space`、`math/stft`），代码取自 `git -C ops-math show HEAD:<path>`（**非** Read 工作树，避免浅克隆干扰）。

### linspace（`math/lin_space`：`op_kernel` 8 文件 + `op_kernel_aicpu` 2 文件）→ **反证排除**

- `python3 scripts/scan_sync.py math/lin_space/op_kernel` → `files=8 candidates=0`；`op_kernel_aicpu` → `files=2 candidates=0`（无 `SetFlag`/`WaitFlag`/`AllocEventID`/`CrossCore*`/`SyncAll`）。
- 三机理逐条**无静态证据**：机理 A 无「workspace 写后跨管线抢读」的原语；机理 B 无 `AllocEventID`、无跨调用静态状态（目录内 `static` 仅出现在 `static_cast`）；机理 C 无事件常量 / `flagId`。
- **负向证据**：kernel 入口 `math/lin_space/op_kernel/lin_space.cpp:24-34` 只 `GetUserWorkspace` 后按 `TILING_KEY` 分派，全程无同步原语。
- **结论**：本型在此算子**未留静态痕迹**（符合「找不到 ≠ 没有」——动态侧仍须用下节 A/B/C 模板跑冷热与 soak 才能给结论）。

### STFT（`math/stft/op_kernel` 5 文件）→ **22 候选 = SUB①×1 + SUB②×21**

- **SUB① ×1 —— 观察项（需实测确认，不进 Bug 卡）**：`math/stft/op_kernel/stft_generalized_complex.h:325` 在 `DataCopyPad`（`:323`）之后写的是 **`WaitFlag<MTE3_MTE2>(event_id)`**；而同文件 **4 个兄弟 gather 函数在对应位置均为 `SetFlag<MTE3_MTE2>(event_id)`**（`:401` / `:474` / `:544`，`NonAlign` 与 `LargeNFactorAlign` 族）—— **静态不对称**。按双缓冲 ping-pong 语义，该位应为 `SetFlag`（重新 arm「MTE3 已写完、该 buffer 可再被 MTE2 复用」）；若确为 `WaitFlag`，则 `MTE3(i) → MTE2(i+2)` 的 **RAW 依赖边未被 armed**。
  - **最小复现锚**：构造使 `GatherForSmallNFactorAlign` 的 `repeats ≥ 2`（即 `complexCount > maskCount`）的 STFT 输入，**冷进程单跑**，观测是否 hang / 输出错值；上板补 racecheck（见模板 C）。
  - **为何不直接出卡**：`repeats` 取值与 `SetFlag`/`WaitFlag` 的实际事件语义（是否阻塞、是否被硬件当 no-op）相关，**无设备无法判定**——按 v3.6 判定纪律记「需实测确认」观察项。
- **SUB② ×21 —— 反证排除**：全部为 `PipeBarrier<PIPE_V>`，位于**同管线**（V→V）算子之间，**非跨流水**。负向证据：`math/stft/op_kernel/stft_kernel.h:325-332`，连续 `AddsComputeAlignment` 之间插 `PipeBarrier<PIPE_V>`，其前后算子同属 V 管线。工具已声明 SUB② 为「弱信号、须人工核方向」——此 21 条经核为**误报**。
- **结论**：Stage 1 在真实算子上给出**可分辨**输出（1 条真不对称 + 21 条可一次性排除的弱信号），对「本型不适用」的算子给 0 候选——与通用纪律第 1 条（跳过须给理由）一致。

## 可上板探针模板（atk / torch_npu 脚手架）

> 模板**本机无 NPU 未验证**；上板后按目标算子接口替换 `CALL_OP` / `GOLDEN` / `TOL` / `CASE`。三段分别对应机理 A / B·C / 升级证据。

```python
# 模板 A —— 冷进程首调（机理 A 的唯一暴露窗口；进程内只调用一次）
import subprocess, sys, json
CASES = ["case_small.json", "case_align_repeats.json"]   # 至少含 1 个 repeats≥2 的用例
for k, case in enumerate(CASES * 4):                     # 记序号 k
    r = subprocess.run([sys.executable, __file__, "--once", "--case", case],
                       capture_output=True, text=True)
    print(json.dumps({"k": k, "case": case, "rc": r.returncode, "tail": r.stdout[-300:]}))
# --once 分支：构造输入 → CALL_OP 一次 → 与 GOLDEN 逐元素比 → 打印「首错位 index / 是否 hang」
```

```python
# 模板 B —— 连续 N 次 soak（机理 B/C；N ≥ 事件池容量且 ≥ workspace 复用轮次）
import torch, torch_npu
N, first_bad, CASE = 16, None, "case_small.json"
for k in range(N):
    out = CALL_OP(CASE)                                  # 同算子、同输入连跑
    ok  = bool(((out - GOLDEN).abs().max() <= TOL) and not torch.isnan(out).any())
    mem = torch.npu.memory_allocated()                   # 峰值曲线
    if not ok and first_bad is None: first_bad = k
    print(k, ok, mem)                                    # 第 K 次首现=耗尽型；mem 单调涨=泄漏叠加
```

```bash
# 模板 C —— racecheck（上板/仿真）：给出地址级成对行号 → 证据可升级为「静态可证」
mssanitizer --tool=racecheck -f ./run_case_align_repeats.sh
# 关注 'Potential RAW/WAW hazard' 的两条代码行；无告警 ≠ 无缺陷（覆盖不到所有竞态）
```

补充探针（机理 C 与跨调用）：**规模扫描**（同一用例放大 `nfft` / `repeats` 尺度轴，看触发概率是否单调上升）、**批跑轮换**（≥5 用例 × ≥3 轮，看失败用例是否轮换）、**冷热对比**（新进程只跑目标用例 vs 先连跑同族用例再跑，结论相反即跨调用残留）。
