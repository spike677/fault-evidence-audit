# 签名产出审计基线（ops-nn）

> **生成物，勿手改**：`python3 scripts/sig_yield.py <语料目录> --md cases/sig_yield-ops-nn.md`。
> 被扫文件 12363（默认排除 tests/examples/build 与纯注释行）。
> 语料 commit：`9b3be291175ab88fabfdc4610ca894511d50adf1`（跨机复现须用同一 commit 的语料，否则数字不可比）
> 口径：**模式级候选** = 该模式全部非宽泛命中的 (文件,行) 去重（= 用户实际会看到多少条）；配对阵据按**失衡文件数**计候选；**density** = 命中行 ÷ 命中文件；**coverage** = 命中文件 ÷ 被扫文件。
> 阈值：模式级 >500 noisy、>200 watch；签名级 density>20 或 coverage>50% demote、>8 或 >20% constrain；配对阵据失衡 >100 noisy、>30 watch。

## 一、模式级候选量（决定「这条模式能不能用」）

| 模式 | 候选数 | 宽泛未计 | 签名数 | 判定 | 豁免理由 |
|---|---|---|---|---|---|
| FP-G02 | 27885 | 0 | 10 | 🟡 waived | 必须触发型：5 子型靠 skill 清单逐项核查，候选=定位清单（同步原语在 kernel 里本就密集），不做裁剪 |
| FP-B07 | 14739 | 13339 | 8 | 🟡 waived | 定位型：8 条指纹覆盖 int32 承载 / 偏移 / 对齐等六个成因，候选须逐一验算；最宽的 int32 承载指纹已降为 broad |
| FP-A05 | 10501 | 12113 | 2 | 🟡 waived | 定位型：workspace / 缓冲初始化核查必须先定位全部 workspace 使用点，候选即清单 |
| FP-B13 | 4213 | 5068 | 3 | 🟡 waived | 定位型：窄化点遍布 host 侧，须逐条比对源/目标位宽，非「命中即缺陷」 |
| FP-D01 | 3721 | 0 | 1 | 🟡 waived | 定位型：显存占用须逐 workspace 公式推导，GetWorkspaceSize 是入口而非缺陷指纹 |
| FP-A02 | 2977 | 0 | 1 | 🟡 waived | 定位型：归约指令凡规约算子必用，判据是与标杆归约拓扑的位宽/顺序对比 |
| FP-B14 | 2055 | 0 | 4 | 🟡 waived | 定位型：图模式双路径对比需成对取样，命中只说明「有图模式代码」 |
| FP-B05 | 1798 | 0 | 1 | 🟡 waived | 定位型：文件级校验骨架核查，真正判据在 absence 规则（缺 CheckNotNull），存在型签名只用来列文件 |
| FP-A10 | 1735 | 0 | 1 | 🔴 noisy | — |
| FP-A14 | 1707 | 0 | 1 | 🔴 noisy | — |
| FP-A06 | 1691 | 0 | 1 | 🔴 noisy | — |
| FP-C05 | 1691 | 0 | 1 | 🔴 noisy | — |
| FP-B02 | 1609 | 0 | 1 | 🟡 waived | 定位型：核数取值每个 tiling 都有，须对照目标芯片核数才知道是否硬编码 |
| FP-B11 | 1451 | 6929 | 4 | 🟡 waived | 定位型：契约校验函数各算子自写，名字各异；真正判据在 absence 规则与逐项对照 |
| FP-A17 | 1232 | 0 | 1 | 🟡 waived | 定位型：代际分支每算子都有，须逐代核对称性与精度硬编码 |
| FP-B04 | 1210 | 9178 | 3 | 🟡 waived | 定位型：判空核查须逐入口逐参数走矩阵，OP_CHECK_NULL 已降为 broad |
| FP-F02 | 1169 | 40253 | 6 | 🔴 noisy | — |
| FP-A07 | 1130 | 0 | 1 | 🔴 noisy | — |
| FP-A08 | 904 | 0 | 1 | 🟡 waived | 定位型：凡切块归约必有 tileSize/tileNum，须结合标杆切块粒度比对才成立 |
| FP-C06 | 781 | 0 | 1 | 🟡 waived | 定位型：GetSocVersion 是代际分支的通用入口，每个跨代算子都有；须配实测性能比值才能判定，签名只用来列候选文件 |
| FP-B01 | 585 | 0 | 3 | 🔴 noisy | — |
| FP-A11 | 549 | 0 | 1 | 🟡 waived | 定位型：DT_DOUBLE 出现在每个算子的 dtype 分派表里，命中即须逐点确认是否真走 double 路径 |
| FP-B06 | 547 | 0 | 4 | 🔴 noisy | — |
| FP-B08 | 470 | 0 | 6 | 🟡 waived | 定位型：属性在 fallback 回调 / 前端插件 / fusion pass 任一跳被丢弃，须逐跳核 GetAttrPointer 与节点创建；命中只说明「这里有属性搬运代码」，非「命中即缺陷」 |
| FP-F04 | 360 | 0 | 3 | 🟠 watch | — |
| FP-F03 | 356 | 0 | 1 | 🟠 watch | — |
| FP-A12 | 269 | 0 | 2 | 🟠 watch | — |
| FP-A19 | 215 | 0 | 2 | 🟠 watch | — |
| FP-B15 | 215 | 0 | 2 | 🟠 watch | — |
| FP-B09 | 162 | 8226 | 7 | ✅ ok | — |
| FP-F01 | 113 | 0 | 1 | ✅ ok | — |
| FP-A15 | 100 | 0 | 4 | ✅ ok | — |
| FP-A01 | 88 | 0 | 2 | ✅ ok | — |
| FP-G01 | 68 | 0 | 3 | ✅ ok | — |
| FP-C01 | 27 | 0 | 3 | ✅ ok | — |
| FP-A20 | 14 | 0 | 3 | ✅ ok | — |
| FP-B10 | 8 | 0 | 2 | ✅ ok | — |
| FP-A18 | 7 | 0 | 2 | ✅ ok | — |
| FP-B03 | 4 | 0 | 1 | ✅ ok | — |
| FP-A16 | 2 | 0 | 1 | ✅ ok | — |

**汇总**：53 个模式 —— noisy 8 / watch 5 / ok 24 / waived 16。

## 二、子型级产出（v6.8：存在型指纹与配对阵据分别度量）

| 模式 | 子型 | 类型 | 候选 | 命中文件 | density | coverage | 判定 |
|---|---|---|---|---|---|---|---|
| FP-B07 | B07-6 | sig | 1153 | 355 | 3.20 | 2.9% | 🔴 noisy |
| FP-G02 | G02-4 | sig | 359 | 117 | 3.10 | 0.9% | 🟠 watch |
| FP-G02 | G02-4 | sig | 359 | 114 | 3.10 | 0.9% | 🟠 watch |
| FP-B07 | B07-6 | sig | 348 | 71 | 4.90 | 0.6% | 🟠 watch |
| FP-G02 | G02-1 | pair | 217 | 955 | 0.23 | 7.7% | 🔴 noisy |
| FP-G02 | G02-5 | sig | 201 | 175 | 1.10 | 1.4% | 🟠 watch |
| FP-G02 | G02-5 | sig | 53 | 23 | 2.30 | 0.2% | ✅ keep |
| FP-G02 | G02-3 | pair | 27 | 104 | 0.26 | 0.8% | ✅ ok |
| FP-A22 | A22-4 | sig | 0 | 0 | 0.00 | 0.0% | ✅ keep |

**汇总**：9 条子型判据（存在型 7 / 配对 2）—— 配对 noisy 2 / watch 4 / ok 1；存在型 demote 0 / constrain 0 / keep 2。

## 三、签名级产出（前 80 条，定位是哪条指纹在刷屏）

| 模式 | 命中 | 命中文件 | density | coverage | 约束 | 判定 |
|---|---|---|---|---|---|---|
| FP-F02 `OP_LOGE(_FOR_[A-Z_]+)?\(` | 21391 | 2275 | 9.4 | 18.4% | — | ⬜ broad |
| FP-A04 `GRAPH_SUCCESS` | 15086 | 2422 | 6.2 | 19.6% | — | ⬜ broad |
| FP-C03 `bfloat16\|bf16\|half` | 14496 | 2099 | 6.9 | 17.0% | — | ⬜ broad |
| FP-C02 `half\|float16` | 14158 | 2000 | 7.1 | 16.2% | — | ⬜ broad |
| FP-A03 `half\|bfloat16_t\|bf16` | 14006 | 1878 | 7.5 | 15.2% | — | ⬜ broad |
| FP-B07 `int32_t[^\n]{0,40}(idx\|Idx\|offset\|Offset\|addr\|Addr)` | 13339 | 1707 | 7.8 | 13.8% | — | ⬜ broad |
| FP-G02 `HardEvent::\s*(V_MTE2\|V_MTE3\|MTE2_V\|MTE3_V\|S_V\|V_S\|MTE3_S\|S_MTE` | 13273 | 887 | 15.0 | 7.2% | — | 🟠 constrain |
| FP-A13 `Round\|round\|Truncate` | 12599 | 1805 | 7.0 | 14.6% | — | ⬜ broad |
| FP-A05 `workspace` | 12113 | 3423 | 3.5 | 27.7% | — | ⬜ broad |
| FP-F02 `ACLNN_ERR_(PARAM\|INNER)_[A-Z_]+` | 11855 | 745 | 15.9 | 6.0% | — | ⬜ broad |
| FP-A05 `GetWorkspaceSize\|SetGlobalBuffer` | 10501 | 2484 | 4.2 | 20.1% | files=op_kernel|op_api | 🟠 constrain |
| FP-G02 `PipeBarrier<\s*PIPE_(V\|MTE2\|MTE3\|S\|MTE1\|FIX)>` | 9760 | 691 | 14.1 | 5.6% | — | 🟠 constrain |
| FP-B04 `OP_CHECK_NULL` | 9178 | 1582 | 5.8 | 12.8% | — | ⬜ broad |
| FP-B07 `SetGlobalBuffer\s*\([^;]{0,80}\*` | 8500 | 1581 | 5.4 | 12.8% | files=op_kernel | ✅ keep |
| FP-B09 `GetShapeSize\(\)\|GetDimNum\(\)` | 8226 | 1575 | 5.2 | 12.7% | — | ⬜ broad |
| FP-F02 `return\s+(ge::GRAPH_FAILED\|ACLNN_ERR_[A-Z_]+)\s*;` | 7007 | 1353 | 5.2 | 10.9% | — | ⬜ broad |
| FP-B11 `GetDimNum\(\)` | 6929 | 1432 | 4.8 | 11.6% | — | ⬜ broad |
| FP-G02 `WaitFlag<\s*(AscendC::)?HardEvent::` | 6492 | 968 | 6.7 | 7.8% | — | ✅ keep |
| FP-G02 `SetFlag<\s*(AscendC::)?HardEvent::` | 6296 | 954 | 6.6 | 7.7% | — | ✅ keep |
| FP-B07 `DataCopy(Pad)?\([^;]{0,60}(offset\|Offset)` | 5127 | 1028 | 5.0 | 8.3% | files=op_kernel | ✅ keep |
| FP-B13 `static_cast<int32_t>\(` | 5068 | 965 | 5.3 | 7.8% | — | ⬜ broad |
| FP-B13 `int32_t\s+\w+\s*=\s*\w+\s*\*\s*\w+` | 4111 | 971 | 4.2 | 7.9% | — | ✅ keep |
| FP-D02 `workspaceSize` | 3930 | 1239 | 3.2 | 10.0% | — | ⬜ broad |
| FP-D01 `GetWorkspaceSize` | 3721 | 2162 | 1.7 | 17.5% | — | ✅ keep |
| FP-A02 `ReduceSum\|WholeReduceSum\|BlockReduce\|ReduceMax` | 2977 | 609 | 4.9 | 4.9% | — | ✅ keep |
| FP-A09 `epsilon\|clip` | 2907 | 979 | 3.0 | 7.9% | — | ⬜ broad |
| FP-B05 `CheckNotNull\|CheckParams` | 1798 | 473 | 3.8 | 3.8% | — | ✅ keep |
| FP-A10 `GetAttrPointer` | 1735 | 611 | 2.8 | 4.9% | — | ✅ keep |
| FP-A14 `Mmad\|MMAD\|SetMMAD` | 1707 | 254 | 6.7 | 2.1% | — | ✅ keep |
| FP-A06 `AtomicAdd\|SetAtomicAdd\|Deterministic\|GetDeterministic` | 1691 | 349 | 4.8 | 2.8% | — | ✅ keep |
| FP-C05 `Deterministic\|AtomicAdd` | 1691 | 349 | 4.8 | 2.8% | — | ✅ keep |
| FP-B02 `SetBlockDim\|SetScheduleMode` | 1609 | 1039 | 1.5 | 8.4% | — | ✅ keep |
| FP-A17 `GetSocVersion\|SOC_VERSION\|socVersion` | 1232 | 373 | 3.3 | 3.0% | — | ✅ keep |
| FP-A07 `IsCapable` | 1130 | 888 | 1.3 | 7.2% | — | ✅ keep |
| FP-B11 `CheckShape\(` | 936 | 497 | 1.9 | 4.0% | — | ✅ keep |
| FP-A08 `tileSize\|tileNum` | 904 | 166 | 5.4 | 1.3% | — | ✅ keep |
| FP-B04 `CheckNotNull` | 788 | 396 | 2.0 | 3.2% | — | ✅ keep |
| FP-C06 `GetSocVersion\|SOC_VERSION` | 781 | 302 | 2.6 | 2.4% | — | ✅ keep |
| FP-B04 `ACLNN_ERR_PARAM_NULLPTR` | 771 | 432 | 1.8 | 3.5% | — | ✅ keep |
| FP-B07 `idxOffset\|startOffset\|offsetIndex\|coefArr` | 761 | 65 | 11.7 | 0.5% | — | 🟠 constrain |
| FP-B14 `IMPL_OP_INFERSHAPE` | 742 | 661 | 1.1 | 5.3% | — | ✅ keep |
| FP-B14 `REG_OP\(` | 737 | 613 | 1.2 | 5.0% | — | ✅ keep |
| FP-F02 `OP_LOGE[\s\S]{0,200}?return\s+(false\|SUCCESS\|GRAPH_SUCCESS)` | 718 | 125 | 5.7 | 1.0% | — | ✅ keep |
| FP-G02 `AllocEventID` | 637 | 101 | 6.3 | 0.8% | — | ✅ keep |
| FP-G02 `ReleaseEventID` | 600 | 93 | 6.5 | 0.8% | — | ✅ keep |
| FP-B14 `GetOptionalInputShape` | 567 | 200 | 2.8 | 1.6% | — | ✅ keep |
| FP-A11 `DT_DOUBLE` | 549 | 243 | 2.3 | 2.0% | — | ✅ keep |
| FP-B06 `IsEmpty\(\)` | 547 | 330 | 1.7 | 2.7% | — | ✅ keep |
| FP-B01 `(?i)not\s+supported` | 475 | 271 | 1.8 | 2.2% | — | ✅ keep |
| FP-B11 `INT32_MAX` | 435 | 208 | 2.1 | 1.7% | — | ✅ keep |
| FP-F02 `INT32_MAX\|UINT32_MAX` | 435 | 208 | 2.1 | 1.7% | — | ✅ keep |
| FP-B07 `(int32_t\|uint32_t)\s+\w*(?i:gmBias\|gm_bias\|blockOffset\|block_offse` | 378 | 83 | 4.6 | 0.7% | — | ✅ keep |
| FP-B08 `GetAttrPointer\s*<[^>]+>\s*\(\s*\d+\s*\)` | 376 | 191 | 2.0 | 1.5% | — | ✅ keep |
| FP-G02 `CrossCoreSetFlag` | 359 | 117 | 3.1 | 0.9% | — | ✅ keep |
| FP-G02 `CrossCoreWaitFlag` | 359 | 114 | 3.1 | 0.9% | — | ✅ keep |
| FP-F03 `TensorType::(Real)?NumberType\(\)` | 356 | 49 | 7.3 | 0.4% | — | ✅ keep |
| FP-F04 `fall\s*back\|fallback.*cpu` | 298 | 70 | 4.3 | 0.6% | — | ✅ keep |
| FP-A12 `numeric_limits<int` | 241 | 132 | 1.8 | 1.1% | — | ✅ keep |
| FP-G02 `SetScheduleMode\s*\(\s*1\s*\)` | 201 | 175 | 1.1 | 1.4% | — | ✅ keep |
| FP-A19 `REGISTER_TILING_TEMPLATE\s*\(\s*\"[A-Za-z0-9_]+\"\s*,\s*\w+Tiling\s*,\` | 199 | 154 | 1.3 | 1.2% | — | ✅ keep |
| FP-B15 `MAX_TENSOR_NUM` | 192 | 79 | 2.4 | 0.6% | — | ✅ keep |
| FP-F01 `CMakeLists\|REG_OP\|AddConfig\|build.sh` | 113 | 13 | 8.7 | 0.1% | files=CMakeLists\.txt|\.cmake|\.sh$|/build/ | 🟠 constrain |
| FP-B01 `Unsupported` | 108 | 74 | 1.5 | 0.6% | — | ✅ keep |
| FP-B13 `size_t\s+\w+\s*=\s*[^;]*size\(\)` | 102 | 41 | 2.5 | 0.3% | — | ✅ keep |
| FP-B09 `UNKNOWN_SHAPE\|UNKNOWN_RANK` | 90 | 39 | 2.3 | 0.3% | — | ✅ keep |
| FP-A01 `log1p\|Log1p` | 88 | 20 | 4.4 | 0.2% | — | ✅ keep |
| FP-B11 `IsFinite\|isnan` | 80 | 40 | 2.0 | 0.3% | — | ✅ keep |
| FP-A15 `isnan` | 63 | 37 | 1.7 | 0.3% | — | ✅ keep |
| FP-B08 `ParseOpToGraph[A-Za-z0-9]+` | 60 | 31 | 1.9 | 0.3% | — | ✅ keep |
| FP-F04 `m\.def\(\|TORCH_LIBRARY\|register_op` | 56 | 49 | 1.1 | 0.4% | — | ✅ keep |
| FP-G02 `SyncAll\s*<` | 53 | 23 | 2.3 | 0.2% | — | ✅ keep |
| FP-G01 `while\s*\(\s*(true\|1)\s*\)` | 44 | 28 | 1.6 | 0.2% | — | ✅ keep |
| FP-A15 `IsNan` | 37 | 12 | 3.1 | 0.1% | — | ✅ keep |
| FP-A12 `static_cast<(float\|double)>\([^)]*\bint(32\|64)` | 35 | 23 | 1.5 | 0.2% | — | ✅ keep |
| FP-B08 `AddNode\|CreateNode` | 31 | 12 | 2.6 | 0.1% | — | ✅ keep |
| FP-B09 `inputShape\s*\[\s*[1-9]` | 27 | 12 | 2.2 | 0.1% | — | ✅ keep |
| FP-B09 `(GetDim\w*\|GetShape\w*\|GetStorageDim\w*)\s*\([^)]*\)\s*(==\|!=)\s*-(` | 27 | 21 | 1.3 | 0.2% | — | ✅ keep |
| FP-C01 `GetShapeSize\(\)\s*[<>]=?\s*[A-Za-z_]` | 27 | 19 | 1.4 | 0.2% | — | ✅ keep |
| FP-B15 `int64_t\s+\w+\s*\[\s*(?:128\|256)\s*\]` | 23 | 23 | 1.0 | 0.2% | — | ✅ keep |
| FP-G01 `Exit code 124\|execution timed out\|vector core` | 20 | 19 | 1.1 | 0.2% | — | ✅ keep |

**汇总**：共 119 条模式签名 —— demote 0 / constrain 6 / keep 96 / broad 17。

