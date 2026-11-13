# 签名产出审计基线（ops-math）

> **生成物，勿手改**：`python3 scripts/sig_yield.py <语料目录> --md cases/sig_yield-ops-math.md`。
> 被扫文件 6610（默认排除 tests/examples/build 与纯注释行）。
> **增量追加说明（v6.26）**：本表不是整表重跑的结果——新增 FP-B15 时**只追加其 2 条签名与 1 行模式级记录**，其余数字保持 2026-11-05 口径（6610 文件）。理由同 v6.22 的记录：本地语料与基线口径不同，整表重跑会引入数百行与本次改动无关的数值漂移，让 diff 无法审阅。新增两条的实测值在同一份语料上单独跑出（见下）。
> **增量删行说明（v6.62）**：索引里 FP-A01 的旧正则 `Exp\s*\(\s*Muls\s*\(\s*Log` 已由带模板参数的写法替代（CHANGELOG v6.27），基线的同名旧条目（0 命中 / keep）随之删除，签名总数 119 → 118（keep 97 → 96）。其余数字仍为 2026-11-05 口径、未整表重跑（本地无语料；整表重跑会引入数百行与本次无关的漂移，理由同 v6.22 / v6.26）。
> 口径：**模式级候选** = 该模式全部非宽泛命中的 (文件,行) 去重（= 用户实际会看到多少条）；配对阵据按**失衡文件数**计候选；**density** = 命中行 ÷ 命中文件；**coverage** = 命中文件 ÷ 被扫文件。
> 阈值：模式级 >500 noisy、>200 watch；签名级 density>20 或 coverage>50% demote、>8 或 >20% constrain；配对阵据失衡 >100 noisy、>30 watch。

## 一、模式级候选量（决定「这条模式能不能用」）

| 模式 | 候选数 | 宽泛未计 | 签名数 | 判定 | 豁免理由 |
|---|---|---|---|---|---|
| FP-G02 | 4533 | 0 | 10 | 🟡 waived | 必须触发型：5 子型靠 skill 清单逐项核查，候选=定位清单（同步原语在 kernel 里本就密集），不做裁剪 |
| FP-B07 | 3940 | 4529 | 8 | 🟡 waived | 定位型：8 条指纹覆盖 int32 承载 / 偏移 / 对齐等六个成因，候选须逐一验算；最宽的 int32 承载指纹已降为 broad |
| FP-A05 | 3419 | 5945 | 2 | 🟡 waived | 定位型：workspace / 缓冲初始化核查必须先定位全部 workspace 使用点，候选即清单 |
| FP-D01 | 2248 | 0 | 1 | 🟡 waived | 定位型：显存占用须逐 workspace 公式推导，GetWorkspaceSize 是入口而非缺陷指纹 |
| FP-B05 | 1465 | 0 | 1 | 🟡 waived | 定位型：文件级校验骨架核查，真正判据在 absence 规则（缺 CheckNotNull），存在型签名只用来列文件 |
| FP-A11 | 1460 | 0 | 1 | 🟡 waived | 定位型：DT_DOUBLE 出现在每个算子的 dtype 分派表里，命中即须逐点确认是否真走 double 路径 |
| FP-B13 | 1264 | 1535 | 3 | 🟡 waived | 定位型：窄化点遍布 host 侧，须逐条比对源/目标位宽，非「命中即缺陷」 |
| FP-B11 | 1055 | 2002 | 4 | 🟡 waived | 定位型：契约校验函数各算子自写，名字各异；真正判据在 absence 规则与逐项对照 |
| FP-A08 | 994 | 0 | 1 | 🟡 waived | 定位型：凡切块归约必有 tileSize/tileNum，须结合标杆切块粒度比对才成立 |
| FP-B04 | 949 | 5317 | 3 | 🟡 waived | 定位型：判空核查须逐入口逐参数走矩阵，OP_CHECK_NULL 已降为 broad |
| FP-B14 | 935 | 0 | 4 | 🟡 waived | 定位型：图模式双路径对比需成对取样，命中只说明「有图模式代码」 |
| FP-B02 | 637 | 0 | 1 | 🟡 waived | 定位型：核数取值每个 tiling 都有，须对照目标芯片核数才知道是否硬编码 |
| FP-A17 | 599 | 0 | 1 | 🟡 waived | 定位型：代际分支每算子都有，须逐代核对称性与精度硬编码 |
| FP-A02 | 557 | 0 | 1 | 🟡 waived | 定位型：归约指令凡规约算子必用，判据是与标杆归约拓扑的位宽/顺序对比 |
| FP-C06 | 440 | 0 | 1 | 🟠 watch | — |
| FP-B06 | 418 | 0 | 4 | 🟠 watch | — |
| FP-A10 | 362 | 0 | 1 | 🟠 watch | — |
| FP-F02 | 330 | 16909 | 6 | 🟠 watch | — |
| FP-A06 | 271 | 0 | 1 | 🟠 watch | — |
| FP-C05 | 271 | 0 | 1 | 🟠 watch | — |
| FP-B08 | 260 | 0 | 6 | 🟠 watch | — |
| FP-B01 | 234 | 0 | 3 | 🟠 watch | — |
| FP-A01 | 221 | 0 | 2 | 🟠 watch | — |
| FP-A07 | 158 | 0 | 1 | ✅ ok | — |
| FP-A12 | 110 | 0 | 2 | ✅ ok | — |
| FP-A15 | 90 | 0 | 4 | ✅ ok | — |
| FP-F04 | 89 | 0 | 3 | ✅ ok | — |
| FP-F01 | 87 | 0 | 1 | ✅ ok | — |
| FP-F03 | 59 | 0 | 1 | ✅ ok | — |
| FP-B09 | 46 | 2535 | 7 | ✅ ok | — |
| FP-G01 | 19 | 0 | 3 | ✅ ok | — |
| FP-A16 | 15 | 0 | 1 | ✅ ok | — |
| FP-A14 | 11 | 0 | 1 | ✅ ok | — |
| FP-B15 | 7 | 0 | 2 | ✅ ok | — |
| FP-B10 | 2 | 0 | 2 | ✅ ok | — |
| FP-C01 | 2 | 0 | 3 | ✅ ok | — |
| FP-A03 | 0 | 4301 | 1 | ✅ ok | — |
| FP-A04 | 0 | 5543 | 1 | ✅ ok | — |
| FP-A09 | 0 | 437 | 1 | ✅ ok | — |
| FP-A13 | 0 | 2814 | 1 | ✅ ok | — |
| FP-A18 | 0 | 0 | 2 | ✅ ok | — |

**汇总**：51 个模式 —— noisy 0 / watch 9 / ok 28 / waived 14。

## 二、子型级产出（v6.8：存在型指纹与配对阵据分别度量）

| 模式 | 子型 | 类型 | 候选 | 命中文件 | density | coverage | 判定 |
|---|---|---|---|---|---|---|---|
| FP-B07 | B07-6 | sig | 411 | 81 | 5.10 | 1.2% | 🟠 watch |
| FP-B07 | B07-6 | sig | 236 | 103 | 2.30 | 1.6% | 🟠 watch |
| FP-G02 | G02-1 | pair | 53 | 214 | 0.25 | 3.2% | 🟠 watch |
| FP-G02 | G02-5 | sig | 47 | 39 | 1.20 | 0.6% | ✅ keep |
| FP-G02 | G02-3 | pair | 7 | 18 | 0.39 | 0.3% | ✅ ok |
| FP-G02 | G02-4 | sig | 6 | 2 | 3.00 | 0.0% | ✅ keep |
| FP-G02 | G02-4 | sig | 4 | 1 | 4.00 | 0.0% | ✅ keep |
| FP-G02 | G02-5 | sig | 2 | 2 | 1.00 | 0.0% | ✅ keep |

**汇总**：8 条子型判据（存在型 6 / 配对 2）—— 配对 noisy 0 / watch 3 / ok 1；存在型 demote 0 / constrain 0 / keep 4。

## 三、签名级产出（前 80 条，定位是哪条指纹在刷屏）

| 模式 | 命中 | 命中文件 | density | coverage | 约束 | 判定 |
|---|---|---|---|---|---|---|
| FP-F02 `OP_LOGE(_FOR_[A-Z_]+)?\(` | 7989 | 1335 | 6.0 | 20.2% | — | ⬜ broad |
| FP-F02 `ACLNN_ERR_(PARAM\|INNER)_[A-Z_]+` | 6832 | 585 | 11.7 | 8.9% | — | ⬜ broad |
| FP-A05 `workspace` | 5945 | 1650 | 3.6 | 25.0% | — | ⬜ broad |
| FP-A04 `GRAPH_SUCCESS` | 5543 | 1135 | 4.9 | 17.2% | — | ⬜ broad |
| FP-B04 `OP_CHECK_NULL` | 5317 | 1140 | 4.7 | 17.2% | — | ⬜ broad |
| FP-C03 `bfloat16\|bf16\|half` | 4585 | 780 | 5.9 | 11.8% | — | ⬜ broad |
| FP-B07 `int32_t[^\n]{0,40}(idx\|Idx\|offset\|Offset\|addr\|Addr)` | 4529 | 594 | 7.6 | 9.0% | — | ⬜ broad |
| FP-C02 `half\|float16` | 4524 | 756 | 6.0 | 11.4% | — | ⬜ broad |
| FP-A03 `half\|bfloat16_t\|bf16` | 4301 | 724 | 5.9 | 11.0% | — | ⬜ broad |
| FP-A05 `GetWorkspaceSize\|SetGlobalBuffer` | 3419 | 1346 | 2.5 | 20.4% | files=op_kernel|op_api | 🟠 constrain |
| FP-D02 `workspaceSize` | 3408 | 765 | 4.5 | 11.6% | — | ⬜ broad |
| FP-A13 `Round\|round\|Truncate` | 2814 | 483 | 5.8 | 7.3% | — | ⬜ broad |
| FP-G02 `HardEvent::\s*(V_MTE2\|V_MTE3\|MTE2_V\|MTE3_V\|S_V\|V_S\|MTE3_S\|S_MTE` | 2543 | 235 | 10.8 | 3.6% | — | 🟠 constrain |
| FP-B09 `GetShapeSize\(\)\|GetDimNum\(\)` | 2535 | 815 | 3.1 | 12.3% | — | ⬜ broad |
| FP-D01 `GetWorkspaceSize` | 2248 | 1246 | 1.8 | 18.9% | — | ✅ keep |
| FP-F02 `return\s+(ge::GRAPH_FAILED\|ACLNN_ERR_[A-Z_]+)\s*;` | 2088 | 562 | 3.7 | 8.5% | — | ⬜ broad |
| FP-B11 `GetDimNum\(\)` | 2002 | 685 | 2.9 | 10.4% | — | ⬜ broad |
| FP-B07 `SetGlobalBuffer\s*\([^;]{0,80}\*` | 1936 | 624 | 3.1 | 9.4% | files=op_kernel | ✅ keep |
| FP-B13 `static_cast<int32_t>\(` | 1535 | 359 | 4.3 | 5.4% | — | ⬜ broad |
| FP-B05 `CheckNotNull\|CheckParams` | 1465 | 357 | 4.1 | 5.4% | — | ✅ keep |
| FP-A11 `DT_DOUBLE` | 1460 | 588 | 2.5 | 8.9% | — | ✅ keep |
| FP-B07 `DataCopy(Pad)?\([^;]{0,60}(offset\|Offset)` | 1314 | 359 | 3.7 | 5.4% | files=op_kernel | ✅ keep |
| FP-B13 `int32_t\s+\w+\s*=\s*\w+\s*\*\s*\w+` | 1219 | 389 | 3.1 | 5.9% | — | ✅ keep |
| FP-G02 `PipeBarrier<\s*PIPE_(V\|MTE2\|MTE3\|S\|MTE1\|FIX)>` | 1182 | 120 | 9.8 | 1.8% | — | 🟠 constrain |
| FP-G02 `SetFlag<\s*(AscendC::)?HardEvent::` | 1168 | 214 | 5.5 | 3.2% | — | ✅ keep |
| FP-G02 `WaitFlag<\s*(AscendC::)?HardEvent::` | 1158 | 213 | 5.4 | 3.2% | — | ✅ keep |
| FP-A08 `tileSize\|tileNum` | 994 | 160 | 6.2 | 2.4% | — | ✅ keep |
| FP-B04 `CheckNotNull` | 669 | 331 | 2.0 | 5.0% | — | ✅ keep |
| FP-B11 `CheckShape\(` | 669 | 347 | 1.9 | 5.2% | — | ✅ keep |
| FP-B02 `SetBlockDim\|SetScheduleMode` | 637 | 425 | 1.5 | 6.4% | — | ✅ keep |
| FP-B04 `ACLNN_ERR_PARAM_NULLPTR` | 618 | 338 | 1.8 | 5.1% | — | ✅ keep |
| FP-A17 `GetSocVersion\|SOC_VERSION\|socVersion` | 599 | 217 | 2.8 | 3.3% | — | ✅ keep |
| FP-A02 `ReduceSum\|WholeReduceSum\|BlockReduce\|ReduceMax` | 557 | 113 | 4.9 | 1.7% | — | ✅ keep |
| FP-B14 `IMPL_OP_INFERSHAPE` | 514 | 513 | 1.0 | 7.8% | — | ✅ keep |
| FP-C06 `GetSocVersion\|SOC_VERSION` | 440 | 208 | 2.1 | 3.1% | — | ✅ keep |
| FP-A09 `epsilon\|clip` | 437 | 73 | 6.0 | 1.1% | — | ⬜ broad |
| FP-B07 `(int32_t\|uint32_t)\s+\w*(?i:gmBias\|gm_bias\|blockOffset\|block_offse` | 423 | 86 | 4.9 | 1.3% | — | ✅ keep |
| FP-B06 `IsEmpty\(\)` | 418 | 343 | 1.2 | 5.2% | — | ✅ keep |
| FP-B14 `REG_OP\(` | 412 | 387 | 1.1 | 5.9% | — | ✅ keep |
| FP-A10 `GetAttrPointer` | 362 | 206 | 1.8 | 3.1% | — | ✅ keep |
| FP-A06 `AtomicAdd\|SetAtomicAdd\|Deterministic\|GetDeterministic` | 271 | 61 | 4.4 | 0.9% | — | ✅ keep |
| FP-C05 `Deterministic\|AtomicAdd` | 271 | 61 | 4.4 | 0.9% | — | ✅ keep |
| FP-B07 `idxOffset\|startOffset\|offsetIndex\|coefArr` | 268 | 35 | 7.7 | 0.5% | — | ✅ keep |
| FP-B11 `INT32_MAX` | 226 | 63 | 3.6 | 1.0% | — | ✅ keep |
| FP-F02 `INT32_MAX\|UINT32_MAX` | 226 | 63 | 3.6 | 1.0% | — | ✅ keep |
| FP-A01 `log1p\|Log1p` | 221 | 39 | 5.7 | 0.6% | — | ✅ keep |
| FP-B11 `IsFinite\|isnan` | 162 | 48 | 3.4 | 0.7% | — | ✅ keep |
| FP-B08 `GetAttrPointer\s*<[^>]+>\s*\(\s*\d+\s*\)` | 161 | 102 | 1.6 | 1.5% | — | ✅ keep |
| FP-A07 `IsCapable` | 158 | 149 | 1.1 | 2.3% | — | ✅ keep |
| FP-B01 `(?i)not\s+supported` | 156 | 117 | 1.3 | 1.8% | — | ✅ keep |
| FP-A12 `numeric_limits<int` | 102 | 39 | 2.6 | 0.6% | — | ✅ keep |
| FP-B08 `ParseOpToGraph[A-Za-z0-9]+` | 99 | 38 | 2.6 | 0.6% | — | ✅ keep |
| FP-F02 `OP_LOGE[\s\S]{0,200}?return\s+(false\|SUCCESS\|GRAPH_SUCCESS)` | 89 | 32 | 2.8 | 0.5% | — | ✅ keep |
| FP-G02 `ReleaseEventID` | 88 | 19 | 4.6 | 0.3% | — | ✅ keep |
| FP-F01 `CMakeLists\|REG_OP\|AddConfig\|build.sh` | 87 | 10 | 8.7 | 0.2% | files=CMakeLists\.txt|\.cmake|\.sh$|/build/ | 🟠 constrain |
| FP-F04 `fall\s*back\|fallback.*cpu` | 87 | 24 | 3.6 | 0.4% | — | ✅ keep |
| FP-B01 `Unsupported` | 76 | 61 | 1.2 | 0.9% | — | ✅ keep |
| FP-G02 `AllocEventID` | 75 | 13 | 5.8 | 0.2% | — | ✅ keep |
| FP-A15 `IsNan` | 60 | 11 | 5.5 | 0.2% | — | ✅ keep |
| FP-F03 `TensorType::(Real)?NumberType\(\)` | 59 | 26 | 2.3 | 0.4% | — | ✅ keep |
| FP-G02 `SetScheduleMode\s*\(\s*1\s*\)` | 47 | 39 | 1.2 | 0.6% | — | ✅ keep |
| FP-B13 `size_t\s+\w+\s*=\s*[^;]*size\(\)` | 45 | 24 | 1.9 | 0.4% | — | ✅ keep |
| FP-A15 `isnan` | 30 | 24 | 1.2 | 0.4% | — | ✅ keep |
| FP-B09 `UNKNOWN_SHAPE\|UNKNOWN_RANK` | 22 | 10 | 2.2 | 0.2% | — | ✅ keep |
| FP-E01 `golden` | 21 | 5 | 4.2 | 0.1% | — | ⬜ broad |
| FP-A16 `aclop\|GEIR` | 15 | 1 | 15.0 | 0.0% | — | 🟠 constrain |
| FP-F02 `DUMP_(SCENES\|TENSOR)\|dump_cce\|TILING_?DUMP` | 15 | 4 | 3.8 | 0.1% | — | ✅ keep |
| FP-G01 `while\s*\(\s*(true\|1)\s*\)` | 14 | 8 | 1.8 | 0.1% | — | ✅ keep |
| FP-B09 `inputShape\s*\[\s*[1-9]` | 13 | 5 | 2.6 | 0.1% | — | ✅ keep |
| FP-A14 `Mmad\|MMAD\|SetMMAD` | 11 | 3 | 3.7 | 0.0% | — | ✅ keep |
| FP-B09 `(GetDim\w*\|GetShape\w*\|GetStorageDim\w*)\s*\([^)]*\)\s*(==\|!=)\s*-(` | 11 | 8 | 1.4 | 0.1% | — | ✅ keep |
| FP-B14 `GetOptionalInputShape` | 9 | 9 | 1.0 | 0.1% | — | ✅ keep |
| FP-A12 `static_cast<(float\|double)>\([^)]*\bint(32\|64)` | 8 | 3 | 2.7 | 0.0% | — | ✅ keep |
| FP-G02 `CrossCoreSetFlag` | 6 | 2 | 3.0 | 0.0% | — | ✅ keep |
| FP-G01 `Exit code 124\|execution timed out\|vector core` | 5 | 4 | 1.2 | 0.1% | — | ✅ keep |
| FP-B07 `CeilDiv\([^;]{0,60}(idx\|offset)` | 4 | 2 | 2.0 | 0.0% | — | ✅ keep |
| FP-G02 `CrossCoreWaitFlag` | 4 | 1 | 4.0 | 0.0% | — | ✅ keep |
| FP-B01 `OP_ERROR` | 2 | 1 | 2.0 | 0.0% | — | ✅ keep |
| FP-B10 `get\s*<\s*(u?int(32\|64)_t\|size_t)\s*>\s*\(\s*\)` | 2 | 2 | 1.0 | 0.0% | — | ✅ keep |
| FP-C01 `GetShapeSize\(\)\s*[<>]=?\s*[A-Za-z_]` | 2 | 2 | 1.0 | 0.0% | — | ✅ keep |
| FP-B15 `MAX_TENSOR_NUM` | 7 | 3 | 2.3 | 0.0% | — | ✅ keep |
| FP-B15 `int64_t\s+\w+\s*\[\s*(?:128|256)\s*\]` | 0 | 0 | 0.0 | 0.0% | — | ✅ keep |
| FP-A01 `Exp\s*(?:<[^>]{0,80}>)?\s*\(\s*Muls\s*(?:<[^>]{0,80}>)?\s*\(\s*Log` | 0 | 0 | 0.0 | 0.0% | — | ✅ keep |

**汇总**：共 118 条模式签名 —— demote 0 / constrain 5 / keep 96 / broad 17。

