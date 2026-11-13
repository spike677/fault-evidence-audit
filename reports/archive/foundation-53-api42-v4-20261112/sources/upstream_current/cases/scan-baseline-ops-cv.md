# 签名语料基线：cann/ops-cv（v4.5）

> ⚠️ **已归档，不可作为当前回归口径**（v6.10 标注）。口径已连续变更四次，本文件数值与现库不可比：
> ① v6.5 起默认**跳过纯注释行**（命中自然变少）；② v6.6 起**宽泛签名不再列成候选**（只计数）、并加 `--max-per-signature 200`；
> ③ v6.5/v6.7 起签名支持 `files/within/exclude` 约束与 `pair` 结构判据（本基线时代还没有）；
> ④ 本机也没有 ops-cv 语料，无法重跑。
> **当前口径的基线是 [sig_yield-ops-math.md](sig_yield-ops-math.md)**（由 `scripts/sig_yield.py` 生成，守门 C38 保证它跟着索引走）。
> 本文件仅作「v4.5 时点签名资产长什么样」的历史记录保留，**不要拿它判断签名是否回归**。

> **这是什么**：第一次用**真实算子仓**回归 `scripts/scan_fp.py` 的签名，回答「索引里的 81 条签名在真实代码上到底命不命中、命中了是不是有用的候选」。
> 这不是评测（评测测判定），这是**测签名资产本身**——死签名、宽泛签名、方向错的签名都在这份基线里现形。
>
> **版本快照**：本基线为 **v4.5** 时点数据（候选 **49 条** / 签名 **81 条**）；库当前为 **50 条** / **88 条** 签名，下方数值**不随库版本刷新**，保留为历史记录。

## 语料与口径

| 项 | 值 |
|---|---|
| 仓 | `cann/ops-cv`（gitcode），`HEAD = 79680a9`（2026-10-16），`--depth 1` |
| 范围 | 产品代码：`image/`、`objdetect/`、`experimental/`、`common/` 等；**排除** `tests/`、`examples/`、`build/`、`docs/`、`cmake/` |
| 文件 | **1301** 个 C/C++ 文件（`.cpp/.h/.hpp/.cc/.c/.inc`），合计约 10.3 MB |
| 签名 | **81** 条（v4.5 前为 85，本轮移出 4 条非源码指纹） |
| 总命中 | **12,409** 处 |
| 有命中的模式 | **20 / 49** |

复现命令：

```bash
python3 scripts/scan_fp.py <ops-cv 路径> \
  --ext .cpp,.h,.hpp,.cc,.c,.inc \
  --exclude /tests/,/examples/,/build/,/docs/,/cmake/ --stats
```

## 命中分布（按模式）

| 模式 | 命中 | 模式 | 命中 |
|---|---:|---|---:|
| FP-F02 维测与错误上报 | 5282 | FP-B12 早退不写输出 | 37 |
| FP-B07 索引/偏移越界 | 2047 | FP-A15 inf/nan | 29 |
| FP-B04 必选入参判空 | 1629 | FP-F04 交付面 | 25 |
| FP-B13 int64→int32 窄化 | 1098 | FP-C01 端到端耗时 | 17 |
| FP-B11 参数契约校验 | 990 | FP-B01 支持面误拦截 | 14 |
| FP-B09 动态 shape 哨兵 | 841 | FP-A01 超越函数精度 | 4 |
| FP-B14 图模式双路径 | 219 | FP-B10 集合通信 | 3 |
| FP-B08 节点配置未生效 | 60 | FP-G01 挂死 | 2 |
| FP-A12 大整数转 float | 56 | FP-A18 int32 边界舍入 | 2 |
| FP-B06 空 tensor | 53 | FP-A19 tiling 覆盖盲区 | 1 |

## 零命中签名（35 / 81）与归因

### 1）仓范围不适用（8 条，预期内，不修）

`FP-B08`（3 条）、`FP-B09`（4 条）、`FP-B10`（1 条）——这三条模式的「适用」头分别是 `canndev` / `canndev` / `hccl`，ops-cv 本就不该命中。

### 2）构建 / 日志 / 工具面（5 条，源码扫描天然不命中）

`FP-F04` 的 `undefined symbol`、`libopapi\.so|liboptiling\.so`、`dlsym`（构建日志/动态加载面），`FP-F02` 的 `DUMP_(SCENES|TENSOR)...`（dump 代码面）。这类签名**需要日志扫描或构建产物扫描**，不是源码正则。

### 3）本仓确实没有该类代码形态（22 条）

`FP-A20` 的 3 条（`dgammaUsedCoreNum` 等属特定算子）、`FP-B06` 的 3 条（`IsRegbase` 组合 / `totalUpdatesNum`）、`FP-B07` 的 2 条（`CeilDiv+idx`、`cubeMathType[`）、`FP-B02` 的 `SetBlockDim/SetScheduleMode`、`FP-B03` 的 `skipCheck`、`FP-C01` 的 2 条循环形态、`FP-G01` 的 `for(;;)`、`FP-A19` 的 `IsCapable...return false` 片段等。
**这类「死」是语料覆盖问题，不是签名错**——要在更多仓（ops-nn/ops-math/ops-transformer）上复测后才能判定为死签名。

## 宽泛签名（≥100 命中）与方向问题

| 模式 | 签名 | 命中 | 判断 |
|---|---|---:|---|
| FP-F02 | `OP_LOGE(...)` | 3008 | 日志调用，**存在是常态**，不能作缺陷候选 |
| FP-B04 | `OP_CHECK_NULL` | 1469 | **方向反了**：缺陷是「没有它」，这是防护面标记 |
| FP-F02 | `ACLNN_ERR_(PARAM\|INNER)_...` | 1301 | 错误码常量，存在是常态 |
| FP-B07 | `int32_t ... (idx\|offset)` | 1251 | 类型声明极常见，只能作定位提示 |
| FP-B13 | `static_cast<int32_t>(` | 817 | 同上，需配合「无范围判断」才有意义 |
| FP-B09 | `GetShapeSize()\|GetDimNum()` | 747 | API 调用，存在是常态 |
| FP-F02 | `return GRAPH_FAILED...` | 664 | 错误返回，存在是常态 |
| FP-B11 | `GetDimNum()` | 639 | API 调用，存在是常态 |

**根因**：本库相当一部分模式是「**缺失型**」——缺陷是「少了某个检查/日志/写入」，而签名是「出现了某个 token」。扫描器只会查「有」，对缺失型只能反向用（文件里有 `OP_CHECK_NULL` ≠ 校验完整；没有才可疑）。

## 结论与后续

1. **签名分两类并已落地一部分**：`presence`（出现即候选，如 `static_cast<int32_t>`、`for(;;)`）与 `absence`（缺失即候选，如 `CheckNotNull`）。v4.6 已给索引加 `absence_signatures`、给扫描器加 `--absence`，并把 **FP-B05** 两条规则切过去（见下节）；B04/B06/B11/B12 仍需按同一模式改造。
2. **签名需要 `scope`**：源码 / 构建日志 / dump / 工具。v4.6 已给索引加 `log_signatures`、给扫描器加 `--log`，并把 FP-F04 的 `undefined symbol`、`libopapi\.so|liboptiling\.so` 移出源码扫描。
3. **宽泛签名只作定位提示**：≥100 命中的 8 条建议降级进 `keywords`，或保留但标注「不可单独作候选」。
4. **死签名不等于坏签名**：本轮只清理了 4 条**明确不是源码指纹**的（A07 概念词、A10 issue 标题、A19 命令、F02 工具名，已移入 `keywords`）；其余 35 条需跨 3~4 个仓复测后再定。
5. 本轮新增 `scan_fp.py --stats` 与 `--exclude`，语料回归从此可一条命令复现。

## 缺失型检查（v4.6 新增 `--absence`）

`absence_signatures` 的语义：**文件路径命中 `files` 正则、但正文缺少 `must` 正则 → 文件级候选**。B05 的两条规则：

| 规则 | 命中文件 | 缺失 | 结论 |
|---|---:|---:|---|
| `op_api/aclnn_*.cpp` 含 `CheckNotNull` | 47 | **0** | ops-cv 的 aclnn 文件全部具备判空骨架 |
| `op_api/aclnn_*.cpp` 含 `CheckParams` | 47 | **0** | 全部有聚合入口 |

复现：

```bash
python3 scripts/scan_fp.py <ops-cv> --absence \
  --ext .cpp,.h,.hpp,.cc,.c,.inc --exclude /tests/,/examples/,/build/,/docs/,/cmake/
```

**解读**：ops-cv 的 47 个 aclnn 接口文件骨架齐全，与 B05 卡片里「ops-transformer 236 个文件中 136 个（57.6%）无 `CheckNotNull`」形成鲜明对照——说明 B05 是**仓级差异**，不是普遍现象。

## 跨仓验证：ops-transformer（v4.7）

为验证「缺失型机制能复现 B05 缺口」，稀疏拉取 `cann/ops-transformer @fd659b0`（2026-10-17，`--filter=blob:none --sparse`，只取 `**/op_host/op_api/*` 与 `**/op_api/*`，检出 578 个 cpp）。

```bash
python3 scripts/scan_fp.py <ops-transformer> --absence \
  --ext .cpp,.h,.hpp,.cc,.c,.inc --exclude /tests/,/examples/,/build/,/docs/,/cmake/
```

| 规则 | 命中文件 | 缺失 | 缺失率 | 对照 |
|---|---:|---:|---:|---|
| B05 `CheckNotNull` | 255 | **166** | **65.1%** | 卡片记录 136/236 = 57.6%（更早 HEAD） |
| B05 `CheckParams` | 255 | **157** | **61.6%** | 卡片同款「聚合入口缺失」 |
| B06 空 tensor 分支（`IsEmpty`/`shapeSize==0`） | 255 | 191 | 74.9% | 文件级粗筛，噪声高，仅作 `info` |
| B12 早退 `return ACLNN_SUCCESS` 但无写输出 | 37 | **1** | 2.7% | 收紧 `when` 后从 11 降到 1 |

**结论**：B05 的 57.6% 缺口在 4 个月后的 HEAD 上复现为 **65.1%**（同量级、略升，符合「新算子未对齐范式」的趋势）——**absence 机制有效，且缺口的仓级差异被证实**。

**两条规则的调参教训**（已写入索引注释）：

- B12 最初用「有 `IsEmpty` 即要求写输出」，在 ops-transformer 上误报 11 条——抽查发现很多接口是「`IsEmpty` → 报参数错」，根本不该写输出；收紧为「`IsEmpty` 且 400 字符内 `return ACLNN_SUCCESS`」后，只剩 1 条，误报率大幅下降。
- B06 用文件级「没有 `IsEmpty`」仍偏粗（74.9%）：很多算子用 `GetShapeSize()==0` 或走公共 executor，文件级判定只能当 `info` 线索，不能当结论。

机制自检：`scan_fp --self-test` 构造「有骨架 / 无骨架 / 早退无写入」样本，断言完整文件不误报、缺失文件必报出。

## 跨仓死签名复核（v4.8）

同一套 79 条签名，扫两个仓：

| 语料 | 文件 | 命中 | 零命中 |
|---|---:|---:|---:|
| `ops-cv @79680a9`（产品代码） | 1301 | 12,653 | **31 / 79** |
| `ops-transformer @fd659b0`（稀疏：op_api + tiling/infershape） | 868 | 16,734 | **55 / 79** |
| **两仓都零命中** | — | — | **29** |

注意：ops-transformer 是稀疏检出，「零命中」只代表**这批文件**没有，不代表全仓没有。

### 29 条两仓零命中的归因

| 归因 | 条数 | 例子 |
|---|---:|---|
| 仓范围不适用（canndev / hccl） | 9 | B08 的 `strcmp(NodeType)`、B09 的 `GetShapeRange()`、B10 的 `float(sliceCount)` |
| 插件 / 交付面 | 1 | F04 `m.def|TORCH_LIBRARY|register_op`（在 op-plugin，不在算子仓） |
| dump 面 | 1 | F02 `DUMP_(SCENES|TENSOR)` |
| 稀有形态 / 本批语料未覆盖 | 18 | A20 的 `dgammaUsedCoreNum`、B06 的 `totalUpdatesNum`、G01 的 `for(;;)`、C01 的循环形态 |

### 只有单仓零命中的 28 条——证明「单仓死 ≠ 死」

| 方向 | 条数 | 例子（在另一仓命中） |
|---|---:|---|
| 仅 ops-transformer 零命中 | 26 | A15 `isnan`、B07 `DataCopy(...offset...)`、B14 `REG_OP(`、G01 `while(true)`——都在 ops-cv 命中 |
| 仅 ops-cv 零命中 | 2 | B13 `size_t ... size()`、F04 `dlsym` |

**结论**：单仓回归只能发现「当前语料没有」，跨两仓后仍死的才值得怀疑；本轮 29 条里 11 条是仓范围/交付面决定的（本来就不该在这两个仓出现），18 条才是「需要更多语料或人工复核」的候选。

### 顺带修掉的两个签名 bug

| 模式 | 原签名 | 问题 | 修复后 | 影响 |
|---|---|---|---|---|
| FP-B01 | `Not supported` | 大小写敏感；ops-transformer 里 **119 处**是 `not supported` 小写 | `(?i)not\s+supported` | 两仓命中 +244 / +180 |
| FP-B02 | `SetBlockDim/SetScheduleMode` | **字面斜杠**，不是正则或；永远匹配不到 | `SetBlockDim\|SetScheduleMode` | 修复后 sparse 的 tiling 文件里开始命中 |

修复后两仓零命中从 31 条降到 29 条，总命中 12,409 → 12,653（ops-cv）、16,554 → 16,734（ops-transformer）。

## 四仓回归 + 宽泛标记（v4.9）

补拉 `ops-math @8ade379`（稀疏 op_api，352 个 aclnn 文件）与 `op-plugin @f305f38`（gitee，835 个文件，插件/适配层）：

| 语料 | HEAD | 文件 | 命中 | 其中 **broad 标记** | 零命中 | absence 候选 |
|---|---|---:|---:|---:|---:|---:|
| ops-cv | 79680a9 | 1301 | 12,653 | 9,896（78%） | 31 | 3 |
| ops-transformer | fd659b0 | 868 | 16,734 | 14,260（85%） | 55 | 514 |
| ops-math | 8ade379 | 1327 | 14,228 | 11,286（79%） | 53 | 61 |
| op-plugin | f305f38 | 835 | 281 | 4（1%） | 64 | 0 |

**最重要的数字是 broad 占比**：三个算子仓 **78%~85% 的命中来自「宽泛标记」签名**（`OP_LOGE`、`OP_CHECK_NULL`、`static_cast<int32_t>` 这类「存在即常态」的 token）。也就是说，扫描器给出的候选里，绝大多数只能当**定位提示**，真正有判别力的命中是少数。v4.9 起这些签名带 `broad_signatures` 标记，文本输出加 `[BROAD]` 前缀、`--stats` 单列统计，报告引用时必须区分。

### absence 矩阵（四仓）

| 规则 | ops-cv | ops-transformer | ops-math | op-plugin |
|---|---:|---:|---:|---:|
| B05 `CheckNotNull` | 0/47 | 166/255（65.1%） | 28/352（8.0%） | 0/0 |
| B05 `CheckParams` | 0/47 | 157/255（61.6%） | 14/352（4.0%） | 0/0 |
| B06 空 tensor 分支 | 3/47 | 191/255（74.9%） | 19/352（5.4%） | 0/0 |
| B12 早退不写输出 | 0 | 0 | 0 | 0 |

**B05 的仓级差异现在是三仓数据**：transformer 65.1%、math 8.0%、cv 0%——同一个库、同一规则，差出 8 倍到 65 倍。

### B12 的三次调参：为什么最终是 0

B12（早退不写输出）的规则在四仓上最终 **0 候选**，过程值得记录：

| 版本 | 规则 | 结果 | 问题 |
|---|---|---|---|
| v4.7 文件级 | 文件有 `IsEmpty` 且 300 字符内有 `return ACLNN_SUCCESS` | transformer 11 条 | 很多是「空输入 → 报参数错」，不写输出是对的 |
| v4.9 函数级（第一版） | `aclnn\w+GetWorkspaceSize` 函数体内判断 | transformer 26/56 | **GetWorkspaceSize 本来就不写输出**，盯错了函数 |
| v4.9 函数级（第二版） | `aclnn(?!\w*GetWorkspaceSize)` | transformer 4、math 16 | 漏掉 `GetMaxWorkspaceSize`；math 的 `aclnnClampCommon` 是 workspace 辅助函数 |
| v4.9 函数内分支级 | `aclnn(?!\w*WorkspaceSize)` + `exclude_sig: workspaceSize` + 分支体内判断 | **四仓 0** | 当前 HEAD 已无该缺陷 |

**0 不代表规则无效**：`--self-test` 内置「第二阶段 API 的 `if (IsEmpty()) { return ACLNN_SUCCESS; }` 且不写输出」样本，规则必须报出；同时确认 ops-cv 历史上的 B12 案例（`aclnnGridSampler3DBackward`）在当前 HEAD 已修复——空输入分支里先 `GetOutTensorWithValueZero` + `l0op::ViewCopy` 清零再返回 SUCCESS。

### 四仓都零命中的 27 条

比两仓时的 29 条少 2 条（`F04` 的插件面签名与 `G01` 的 `while(true)` 在新增语料中命中）。27 条里：

- **9 条仓范围决定**（B08/B09 = canndev，B10 = hccl）——本来就不该出现在这四个仓；
- **1 条 dump 面**（F02 `DUMP_...`）；
- **17 条稀有形态**（A20 的 `dgammaUsedCoreNum`、B06 的 `totalUpdatesNum`、C01 的循环形态、G01 的 `for(;;)` 等）——保留，标注「待更多语料或人工复核」。

## 六仓总表（v5.0）

再补 `ops-nn @a7539b1`（1688 文件）与 `hccl @3868603`（1118 文件，610 个 `.cc`）：

| 语料 | HEAD | 文件 | 命中 | broad 标记 | 零命中 | absence 候选 |
|---|---|---:|---:|---:|---:|---:|
| ops-cv | 79680a9 | 1301 | 12,653 | 9,896 | 31 | 3 |
| ops-transformer | fd659b0 | 868 | 16,734 | 14,260 | 55 | 514 |
| ops-math | 8ade379 | 1327 | 14,228 | 11,286 | 53 | 61 |
| **ops-nn** | a7539b1 | **1688** | **25,534** | 22,094 | 47 | 170 |
| op-plugin | f305f38 | 835 | 281 | 4 | 64 | 0 |
| **hccl** | 3868603 | **1118** | 1,268 | 572 | 57 | 0 |
| **合计** | — | **7,137** | **70,698** | **58,112（82%）** | — | **748** |

**结论一**：六仓 7,137 个源文件、7 万条命中，**82% 是 broad 标记**（定位提示），真正可作判别性候选的不到两成——这印证了 v4.9 的宽泛标记是必要的，也说明「签名命中数」不能当覆盖率卖点。

**结论二**：六仓都零命中的签名收敛到 **25 条**（比四仓少 2 条：`F04` 的 `m.def|register_op` 在 op-plugin 命中、`G01` 的 `while(true)` 在 hccl 命中）。其中 9 条仓范围决定（B08/B09 = canndev、B10 = hccl）、1 条 dump 面（F02）、15 条稀有形态。

**结论三**：B05 的仓级差异扩展为四仓——transformer **65.1%**、ops-nn **9.6%**（39/408）、ops-math **8.0%**、ops-cv **0%**。同一个库同一条规则，跨仓差出 65 个百分点。

### B06 抽样：候选是真的吗

B06（空 tensor 分支缺失）在 ops-transformer 命中 191/255（74.9%）、ops-nn 96/408（23.5%）。抽 20 条候选人工核对：

| 检查 | 结果 |
|---|---|
| 文件内有**其他**空处理形式（`shapeSize==0`/`Numel()==0`/`EmptyTensor` 等） | **1 / 20（5%）** |
| 文件内完全没有空 tensor 分支 | 19 / 20 |

也就是说，B06 的候选**不是正则误报**——这些 aclnn 文件确实没有任何空 tensor 分支。但是否构成缺陷取决于算子语义：部分算子对空输入**应当报错**而不是返回空输出。所以 B06 维持 `info` 级，报告口径写「文件内无任何空 tensor 分支，需按算子语义确认是否应支持空输入」。

## 已执行的清理（v4.5）

| 模式 | 移出的签名 | 原因 | 去向 |
|---|---|---|---|
| FP-A07 | `off-by-one` | 概念词，非代码 | keywords |
| FP-A10 | `Epsilon Debug Interpreted as 32-bit float` | issue 标题片段 | keywords |
| FP-A19 | `git diff --name-only ...` | shell 命令 | keywords |
| FP-F02 | `cann-log-evaluation` | 工具名 | keywords |

签名总数 85 → 81；`scan_fp --self-test` 仍通过（81 条卫生检查 + 冒烟）。
