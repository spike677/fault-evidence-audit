# 症状分诊（Triage，v5.4）

> **这是什么**：库的「现象入口」。手上只有现象、不知道查哪条模式时先看这里——每个入口把候选收敛到 1~6 条，再进对应 skill 深挖。
> **与索引的分工**：根 `README.md` 的总览表按「模式」组织（已知要查什么时用）；本表按「现象」组织（只知道出了什么事时用）。两者都只是入口，判定一律以卡片与 skill 为准。
> **生成方式**：由 `scripts/gen_triage.py` 从 `fault_patterns_index.json` + `triage_map.json` 生成，**勿手改**；改映射后重跑本脚本，并跑守门 C20。

## 30 秒用法

1. 先找**后果入口**（T1~T7），不要一上来找模式名——按「出了什么事」而不是「像哪个 bug」分流。
2. 入口内按「症状」列对齐自己的现象；同组候选 ≤6 条，已按风险从高到低排。
3. 打开候选的 skill，**先核「适用」声明**（仓 / 侧别 / 载体不匹配 → 跳过并记理由）。
4. 候选都不像：回 [总览表](README.md#总览表快速索引) 按类别浏览，或用索引 `symptoms` 反查。

## 症状速查（词 → 入口）

| 现象词 / 同义词 | 入口 |
|---|---|
| 卡死 / 不动 / 没有输出 / 超时 / 退出码 124 | T1 |
| 编译失败 / 链接冲突 / undefined symbol / 未注册 tilingkey / 示例跑不起来 | T2.1 |
| SIGSEGV / rc=139 / coredump / 161001 / 161002 / Not supported / 非法 shape 被放行 | T2.2 |
| double 输入或 double 属性不支持 | T2.3 |
| aic error / 偶发崩溃 | T2.4 |
| 通信 / rank / AllReduce / 集合通信 | T2.5 |
| 错误码不符 / 日志缺失 / 维度不为 N | T2.6 |
| 精度 / 超差 / 数值不对 / NaN / inf | T3 |
| 偶发 / 两次结果不同 / flaky / 无法复现 | T4 |
| racecheck / WAW / RAW / 同步 / SetFlag / WaitFlag / 竞态 / 核间同步 | T4 |
| 慢 / 耗时 / 性能退化 / 不如 bf16 | T5 |
| OOM / 内存 / 显存 / workspace | T6 |
| 测试全绿但线上异常 / golden / 判据 / README 与实现不符 / 迁移 | T7 |

## T1 跑不完 / 卡死 / 超时

> 进程还活着但不返回，或被超时中断。与「慢」（T5）的区别是**没有完成**：日志完全无进展、退出码 124、CPU 空转。

### 无进展 / 超时 / 设备侧超时

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| 日志完全无进展 / CPU 空转 / 退出码 124 / `vector core execution timed out` / aic error | [FP-G01 执行挂死与调度超时（死循环/回绕长循环/通信等待/kern…](patterns/FP-G/FP-G01.md)（高，6 案） | 看日志是否推进；查 `while(true)` 推进变量与不推进退出；单用例超时熔断 | [`fpg01-hang-review`](skills/FP-G/fpg01-hang-review/SKILL.md) |
| SetFlag/WaitFlag 不配平致**永久等待** / 同步卡死 / 同步超时 aic error | [FP-G02 核间/流水同步缺失或配对不完整（SetFlag/WaitF…](patterns/FP-G/FP-G02.md)（高，13 案） | 扫同步原语配平（set↔wait 次数与分支）；`scripts/scan_sync.py` + racecheck | [`fpg02-sync-review`](skills/FP-G/fpg02-sync-review/SKILL.md) |
| 通信等待卡住 / 初始化连接超时 / 个别 rank 掉线 | [FP-B10 集合通信算子功能/兼容问题（通信域/拓扑/图模式契约/同族…](patterns/FP-B/FP-B10.md)（高，4 案） | 核通信域与超时配置（CONNECT/EXEC_TIMEOUT）；多级拓扑对拍 | [`fpb10-hccl-review`](skills/FP-B/fpb10-hccl-review/SKILL.md) |

## T2 报错退出

> 有明确错误出口：编译/链接失败、返回码非 0、崩溃或显式报错。先按**报错发生的阶段**分组，再按错误码/符号定位。

### T2.1 构建 / 链接 / 交付期

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| 编译失败 / `REG_OP` 重复注册 / CMake 报错 / `No such file or directory` | [FP-F01 构建/工程配置不一致致编译与产物缺陷](patterns/FP-F/FP-F01.md)（高） | def × binary.json 差集；读构建日志 | [`fpf01-build-review`](skills/FP-F/fpf01-build-review/SKILL.md) |
| `undefined symbol` / `dlsym` 为空 / `torch.ops` 不可用 / 未注册 tilingkey | [FP-F04 算子接口交付面缺失（符号未导出/原型未注册/未纳入商分）](patterns/FP-F/FP-F04.md)（高） | 构建日志查符号与注册；dlsym 冒烟 | [`fpf04-delivery-review`](skills/FP-F/fpf04-delivery-review/SKILL.md) |
| README 声明支持但调用报未适配 / 示例编译失败 | [FP-F03 文档/声明面与实现面不一致](patterns/FP-F/FP-F03.md)（中） | README 支持表与 AddConfig 差集 | [`fpf03-doc-review`](skills/FP-F/fpf03-doc-review/SKILL.md) |

### T2.2 参数校验与会话契约（161xxx）

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| SIGSEGV / rc=139 / coredump / 161001 | [FP-B04 aclnn 必选入参空指针校验缺失](patterns/FP-B/FP-B04.md)（高，5 案） | 必选参数判空矩阵；gdb 栈回溯 | [`fpb04-aclnn-review`](skills/FP-B/fpb04-aclnn-review/SKILL.md) |
| 非法 shape/rank/ListInt 长度/属性超界被放行：第一段返回 ACLNN_SUCCESS，到 tiling 才报 561002 或直接 coredump | [FP-B11 第一段接口/InferShape 参数契约校验缺失（非法 …](patterns/FP-B/FP-B11.md)（高，5 案） | 比对 CheckShape 的 rank/长度/值域/有限性四类检查；InferShape 与 tiling 校验集合是否一致 | [`fpb11-validation-review`](skills/FP-B/fpb11-validation-review/SKILL.md) |
| 含 0 维 shape 报错 / 空 tensor 在第一段接口失败 | [FP-B06 空 tensor（numel==0）输入分支处理缺失](patterns/FP-B/FP-B06.md)（高，5 案） | 空 tensor 探针矩阵（0 维 / 零元素） | [`fpb06-aclnn-review`](skills/FP-B/fpb06-aclnn-review/SKILL.md) |
| 部分芯片可执行、部分报错（如 310P 系列） | [FP-B02 tiling 未适配多种芯片核数](patterns/FP-B/FP-B02.md)（高） | 核数来源是否硬编码；全型号矩阵 | [`fpb02-corenum-review`](skills/FP-B/fpb02-corenum-review/SKILL.md) |
| 合法输入报 Not supported / Unsupported（误拦截） | [FP-B01 支持面校验过严误拦截合法输入](patterns/FP-B/FP-B01.md)（中） | 核白名单与 AddConfig 差集 | [`fpb01-checker-review`](skills/FP-B/fpb01-checker-review/SKILL.md) |

### T2.3 dtype / attr 支持面

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| double 属性报 161002 / attr 精度异常 | [FP-A10 原型 Attr 不支持 Double](patterns/FP-A/FP-A10.md)（高） | proto attr 类型与解析分支 | [`fpa10-aclnn-review`](skills/FP-A/fpa10-aclnn-review/SKILL.md) |
| double 输入报不支持 | [FP-A11 AiCore 不支持 double 类型](patterns/FP-A/FP-A11.md)（高） | dtype 分派与声明一致性 | [`fpa11-aclnn-review`](skills/FP-A/fpa11-aclnn-review/SKILL.md) |

### T2.4 运行期崩溃 / 异常终止

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| aic error / coredump / 结果错位 / 非对齐尾块 | [FP-B07 索引/偏移计算错误致越界](patterns/FP-B/FP-B07.md)（高，8 案） | mssanitizer + 偏移表达式上界反推 | [`fpb07-aclnn-review`](skills/FP-B/fpb07-aclnn-review/SKILL.md) |
| 偶发崩溃 / `mssanitizer` 报内存错误 | [FP-A05 脏数据/数据踩踏](patterns/FP-A/FP-A05.md)（高） | memcheck；连续两次调用一致性 | [`fpa05-aclnn-review`](skills/FP-A/fpa05-aclnn-review/SKILL.md) |
| 列表长度超过内部容量时机率性 coredump 或 `sync 507035` 但两段返回码都是 0 | [FP-B15 定长容器容量无校验（入参索引 + 越界写 + 静默截断）](patterns/FP-B/FP-B15.md)（高） | 查 tiling_data 定长数组容量；n=N+1 起逐级复测 | [`fpb15-capacity-review`](skills/FP-B/fpb15-capacity-review/SKILL.md) |

### T2.5 通信 / 集合通信

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| 通信等待卡住 / 初始化连接超时 / 个别 rank 掉线 | [FP-B10 集合通信算子功能/兼容问题（通信域/拓扑/图模式契约/同族…](patterns/FP-B/FP-B10.md)（高，4 案） | 核通信域与超时配置（CONNECT/EXEC_TIMEOUT）；多级拓扑对拍 | [`fpb10-hccl-review`](skills/FP-B/fpb10-hccl-review/SKILL.md) |

### T2.6 错误码 / 日志语义

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| infershape/verifier 编译期报错 / 「维度不为 N」 | [FP-B09 动态 shape 标签未参与校验决策（`-2`/`-1` …](patterns/FP-B/FP-B09.md)（高，5 案） | 动态 shape {-2}/{-1} 最小集；GetDims 下标 | [`fpb09-dynamic-shape-review`](skills/FP-B/fpb09-dynamic-shape-review/SKILL.md) |
| 错误码不符 / 跨仓错误码不一致 / 日志缺失 / error 日志误报 | [FP-F02 维测与错误上报缺陷（含跨仓错误码不一致）](patterns/FP-F/FP-F02.md)（中） | 跨仓返回码对照；日志级别核查 | [`fpf02-observability-review`](skills/FP-F/fpf02-observability-review/SKILL.md) |

### 图模式（GEIR/aclGraph）专用失败

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| aclnn 正常但图模式报 E40021 / GRAPH_FAILED / Run graph failed / 507011 | [FP-B14 图模式（GEIR/aclGraph）通路与 aclnn 单…](patterns/FP-B/FP-B14.md)（高，4 案） | 比对 proto 默认值与 tiling 接受域、format 白名单、属性下发；图模式冒烟对拍 aclnn | [`fpb14-graph-path-review`](skills/FP-B/fpb14-graph-path-review/SKILL.md) |

## T3 结果不对（精度 / 数值）

> 能跑完、能出结果，但数值不对。先看**误差形态**（大面积 / 边界 / 组合 / 静默 / 路径），形态决定候选顺序——不要一上来读全部精度模式。

### T3.1 大面积 / 系统性偏差

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| bf16/fp16 大面积超阈值 / 低精度 dtype 整体劣化 | [FP-A03 竞品高精度中间计算，NPU 直接低精度](patterns/FP-A/FP-A03.md)（高） | 查中间量位宽与累加 dtype | [`fpa03-kernel-review`](skills/FP-A/fpa03-kernel-review/SKILL.md) |
| 超越函数精度超标 / 网络精度波动 | [FP-A01 硬件指令精度不足，未与竞品对齐](patterns/FP-A/FP-A01.md)（高，4 案） | 与 GPU 或参考库逐元素 utol | [`fpa01-kernel-review`](skills/FP-A/fpa01-kernel-review/SKILL.md) |
| 偏差稳定可复现、随 reduce 维增长 | [FP-A02 归约/累加实现顺序与竞品不一致](patterns/FP-A/FP-A02.md)（高，4 案） | 对齐归约拓扑与分组顺序 | [`fpa02-kernel-review`](skills/FP-A/fpa02-kernel-review/SKILL.md) |
| 与 GPU 结果不一致 / 切 MMAD-FFMA 路径后变化 | [FP-A14 FFMA 与 MMAD 硬件指令差异](patterns/FP-A/FP-A14.md)（高，4 案） | 路径切换对拍；核 stepK 与 K 补零 | [`fpa14-mmad-review`](skills/FP-A/fpa14-mmad-review/SKILL.md) |
| INT32_MAX/MIN 边界值失败 / 分支选错 | [FP-A18 int32 边界值转 float 舍入致比较语义偏差](patterns/FP-A/FP-A18.md)（高） | 比较前是否提升类型 | [`fpa18-int32float-review`](skills/FP-A/fpa18-int32float-review/SKILL.md) |
| 大数值场景结果偏差 / 偏差量级约「大数 × 1 ulp」 | [FP-A12 大整数转 fp32 计算精度损失](patterns/FP-A/FP-A12.md)（中） | 扫 int→float 转换点，反推可达上界 | [`fpa12-intfloat-review`](skills/FP-A/fpa12-intfloat-review/SKILL.md) |

### T3.2 边界 / 离群 / 尾块

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| 离群点 / 极端 shape 才失败 / 大 shape 超阈值 | [FP-A08 切块粒度差异致离群点精度问题](patterns/FP-A/FP-A08.md)（高，6 案） | 极端值分布 + 切块边界探针 | [`fpa08-kernel-review`](skills/FP-A/fpa08-kernel-review/SKILL.md) |
| 特定 shape 失败 / 分支阈值附近异常 | [FP-A07 tiling 条件判断错误走入错误分支](patterns/FP-A/FP-A07.md)（高） | 阈值 ±1 成对用例；IsCapable 验算 | [`fpa07-aclnn-review`](skills/FP-A/fpa07-aclnn-review/SKILL.md) |
| 空 tensor / 零元素输入产生 NaN 或读越界 | [FP-B06 空 tensor（numel==0）输入分支处理缺失](patterns/FP-B/FP-B06.md)（高，5 案） | 空 tensor 探针（0 维 / 零元素） | [`fpb06-aclnn-review`](skills/FP-B/fpb06-aclnn-review/SKILL.md) |

### T3.3 特定 shape / dtype / attr / 平台组合

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| 节点级配置未生效但无报错 / 全局生效节点级不生效 | [FP-B08 节点级配置未参与派发决策（属性在某一跳被丢弃：fallba…](patterns/FP-B/FP-B08.md)（高，4 案） | 节点 × 全局四组交叉 | [`fpb08-fallback-review`](skills/FP-B/fpb08-fallback-review/SKILL.md) |
| nan/inf 用例失败 / 特殊值结果不一致 | [FP-A15 inf/nan 特殊值行为差异](patterns/FP-A/FP-A15.md)（高） | 特殊值用例集；核 isnan 分支 | [`fpa15-kernel-review`](skills/FP-A/fpa15-kernel-review/SKILL.md) |
| 动态 shape 下维度 / 维数不对 | [FP-B09 动态 shape 标签未参与校验决策（`-2`/`-1` …](patterns/FP-B/FP-B09.md)（高，5 案） | {-2}/{-1} 最小集；GetShapeRange 前 MakeUpRange | [`fpb09-dynamic-shape-review`](skills/FP-B/fpb09-dynamic-shape-review/SKILL.md) |
| 特定 dtype 返回 0 但部分输出未写 / 同宽度兄弟 dtype 表现分裂（int32 对而 uint32 错）/ bool 掩码边界错位 | [FP-A22 kernel dtype 分派/模板映射错配（特定 dty…](patterns/FP-A/FP-A22.md)（高，3 案） | 按 def.cpp 支持集核对 kernel dtype→模板映射表；dtype 全组合 + 输出魔数预填 | [`fpa22-dtype-dispatch-review`](skills/FP-A/fpa22-dtype-dispatch-review/SKILL.md) |
| 与 TF / PTA 语义不一致（epsilon、clip、默认值） | [FP-A09 对标 TF 语义与 PTA（torch_npu）不一致](patterns/FP-A/FP-A09.md)（中） | 双标杆对拍；核 attr 默认值 | [`fpa09-aclnn-review`](skills/FP-A/fpa09-aclnn-review/SKILL.md) |
| 跨代芯片精度不一致（A1 vs A2） | [FP-A17 A1 与 A2 硬件代际精度差异](patterns/FP-A/FP-A17.md)（中） | 跨代同用例对拍；扫 GetSocVersion 分支 | [`fpa17-socgen-review`](skills/FP-A/fpa17-socgen-review/SKILL.md) |

### T3.4 静默错（无报错）[WIDE]

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| 无报错但数值错 / NaN / 错误被吞 | [FP-A04 功能问题演变为精度静默故障](patterns/FP-A/FP-A04.md)（高） | 查错误分支是否静默早退或恒返回成功 | [`fpa04-aclnn-review`](skills/FP-A/fpa04-aclnn-review/SKILL.md) |
| 空/退化输入返回 SUCCESS 但输出未写（NaN 或随机值）/ 反向算子梯度偶发 NaN | [FP-B12 空/退化输入早退路径未写非空输出（SUCCESS + 未初…](patterns/FP-B/FP-B12.md)（高，5 案） | 查 IsEmpty 早退块是否写非空输出；跑「空输入 × 非空输出」矩阵 | [`fpb12-early-exit-review`](skills/FP-B/fpb12-early-exit-review/SKILL.md) |
| 超大属性值（2^31 / 2^32 附近）才错 / 输出 shape 与入参不一致 / 返回码 SUCCESS | [FP-B13 host 侧 int64→int32 窄化/乘积溢出（参数…](patterns/FP-B/FP-B13.md)（高） | 扫 static_cast<int32_t> 与 32 位乘积；改小值复测是否消失 | [`fpb13-narrowing-review`](skills/FP-B/fpb13-narrowing-review/SKILL.md) |
| 列表长度超过内部容量后返回 SUCCESS 但尾部结果静默错 / n 再大时 sync 507035 kernel fault / 同族接口一个报错一个放行 | [FP-B15 定长容器容量无校验（入参索引 + 越界写 + 静默截断）](patterns/FP-B/FP-B15.md)（高） | 扫 tiling_data 定长数组 × 入参索引 × 全 op_host 无 MAX 校验；跑容量扫描 1/N-1/N/N+1/2N | [`fpb15-capacity-review`](skills/FP-B/fpb15-capacity-review/SKILL.md) |
| 迁移后应拦截未拦截 / 错误结果静默产出 | [FP-B03 跨仓迁移丢失防御/拦截逻辑](patterns/FP-B/FP-B03.md)（高） | 迁移 diff 前后拦截点比对 | [`fpb03-migration-review`](skills/FP-B/fpb03-migration-review/SKILL.md) |
| 偶发崩溃 / `mssanitizer` 报内存错误 | [FP-A05 脏数据/数据踩踏](patterns/FP-A/FP-A05.md)（高） | memcheck；连续两次调用一致性 | [`fpa05-aclnn-review`](skills/FP-A/fpa05-aclnn-review/SKILL.md) |
| 同一进程连续跑不同 shape 后结果不对（如 3D TND → 4D BNSD）/ 报 `do tiling failed` / D 维取到原 S 维的值 / 输出错但全链路无报错 | [FP-A21 tiling 可重入性缺失致跨调用/跨线程污染（TU 级可…](patterns/FP-A/FP-A21.md)（高，3 案） | 查 tiling 内匿名 namespace 可变全局与全局 TilingData；补同进程序列化用例（3D→4D / 带x→不带x / fp16→fp32），顺序敏感即命中 | [`fpa21-tiling-state-review`](skills/FP-A/fpa21-tiling-state-review/SKILL.md) |
| 出参传非连续 view（带空洞 stride）时恰好一半元素为旧值 / 返回码 0 / 跨版本逐位一致 | [FP-B16 出参 stride 未参与寻址（非连续 view 被按连续…](patterns/FP-B/FP-B16.md)（高，5 案） | 先查 ACLNNTYPE 是否 aclnn 且无 op_host/op_api；再物理 dump 出参 storage 前 numel 个与连续基线对拍 | [`fpb16-output-stride-review`](skills/FP-B/fpb16-output-stride-review/SKILL.md) |

### T3.5 路径 / 口径差异

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| aclnn 与 aclop / GEIR 结果不同 | [FP-A16 aclop 与 aclnn 编译阶段精度差异](patterns/FP-A/FP-A16.md)（高） | 双路径同输入对拍 | [`fpa16-aclop-aclnn-review`](skills/FP-A/fpa16-aclop-aclnn-review/SKILL.md) |
| 图模式与 aclnn 直调不一致 | [FP-B08 节点级配置未参与派发决策（属性在某一跳被丢弃：fallba…](patterns/FP-B/FP-B08.md)（高，4 案） | 图 vs 直调对拍；核属性透传 | [`fpb08-fallback-review`](skills/FP-B/fpb08-fallback-review/SKILL.md) |
| 同 shape 换 cubeMathType 即大面积 PASS/FAIL 翻转 / rmse 远大于 mare | [FP-E02 精度测试判据与标杆口径设计缺陷](patterns/FP-E/FP-E02.md)（高） | 双标杆复核 + 判据分母检查 | [`fpe02-benchmark-review`](skills/FP-E/fpe02-benchmark-review/SKILL.md) |

### T3.6 精度验证本身可疑

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| 精度验证静默失效 / golden 与实现同时被改 | [FP-E01 golden/UT 期望值失配或按错误实现编写](patterns/FP-E/FP-E01.md)（高） | golden 来源与命名核查 | [`fpe01-golden-review`](skills/FP-E/fpe01-golden-review/SKILL.md) |
| 仅截断输入才能过测试 / 精度勉强达标 | [FP-A13 输入尾数截断才能通过精度标准](patterns/FP-A/FP-A13.md)（中） | 看 golden/UT 是否对输入 round | [`fpa13-input-rounding-review`](skills/FP-A/fpa13-input-rounding-review/SKILL.md) |

## T4 结果不稳 / 可复现性

> 同一输入、同一环境，两次结果不同，或时好时坏。先做**稳定性分流**（连跑 3~5 次两两比对），再区分确定性、脏数据与等级未分级。

### 两次不一致 / 偶发

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| 确定性开关下两次运行结果不同 / 同输入不同结果 | [FP-A06 确定性开关下结果不固定](patterns/FP-A/FP-A06.md)（高） | 开关开-关对照；同输入多轮 bitwise 比对 | [`fpa06-kernel-review`](skills/FP-A/fpa06-kernel-review/SKILL.md) |
| flaky 误报 / 缺陷被容差吞掉 / 无法复现 | [FP-A20 确定性等级未分级标注（二元描述掩盖条件确定性）](patterns/FP-A/FP-A20.md)（高，4 案） | 按输出 × 路径 × shape 分级复核 | [`fpa20-determinism-review`](skills/FP-A/fpa20-determinism-review/SKILL.md) |
| 偶发精度错 / NaN 随机出现 / 单跑过批量失败 | [FP-A05 脏数据/数据踩踏](patterns/FP-A/FP-A05.md)（高） | memcheck；固定用例顺序复跑 | [`fpa05-aclnn-review`](skills/FP-A/fpa05-aclnn-review/SKILL.md) |
| 并发多流 / 多线程下偶发精度失败；单跑通过、压测失败；结果随并发度或调用顺序变化（与 shape 无因果关系） | [FP-A21 tiling 可重入性缺失致跨调用/跨线程污染（TU 级可…](patterns/FP-A/FP-A21.md)（高，3 案） | 多线程只调 `GetWorkspaceSize` 压测 tiling；`DoOpTiling` 首尾 atomic 打桩确认 peak 并发数 > 1 | [`fpa21-tiling-state-review`](skills/FP-A/fpa21-tiling-state-review/SKILL.md) |
| 同步缺失 / 事件 ID 冲突致**偶发结果不同** / racecheck 报 `WAW`/`RAW` hazard | [FP-G02 核间/流水同步缺失或配对不完整（SetFlag/WaitF…](patterns/FP-G/FP-G02.md)（高，13 案） | mssanitizer racecheck 零告警门禁；事件 ID 池审计；批跑轮换 + 新进程首调 | [`fpg02-sync-review`](skills/FP-G/fpg02-sync-review/SKILL.md) |

## T5 慢 / 性能退化

> 结果正确但耗时变长。先分清**绝对慢**（端到端占比高）与**相对慢**（同 shape 比另一 dtype / 板型 / 代际 / 上一次版本慢）。

### 耗时与性能

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| 端到端性能瓶颈 / 耗时变长但精度全对 / 跨版本耗时回归 | [FP-C01 算子端到端耗时占比高且单次调用耗时高（含 host 侧循环…](patterns/FP-C/FP-C01.md)（高，4 案） | profiler kernel_details 聚合；跨版本比值 >1.15 | [`fpc01-aclnn-review`](skills/FP-C/fpc01-aclnn-review/SKILL.md) |
| A2 上 fp16 Vector 算子慢于 bf16 | [FP-C02 A2 上 fp16 Vector 算子性能不如 bf16](patterns/FP-C/FP-C02.md)（高） | fp16/bf16 对照；查 dtype 特化 | [`fpc02-dtype-perf-review`](skills/FP-C/fpc02-dtype-perf-review/SKILL.md) |
| bf16 与 fp16 性能差异异常 | [FP-C03 bf16 与 fp16 性能差异大](patterns/FP-C/FP-C03.md)（高） | 对照测试；查 Cast DAG 冗余 | [`fpc03-dtype-specialization-review`](skills/FP-C/fpc03-dtype-specialization-review/SKILL.md) |
| 开确定性开关性能骤降 | [FP-C05 确定性场景性能大幅劣于非确定性](patterns/FP-C/FP-C05.md)（高） | 确定性开关性能对照；查串行化 | [`fpc05-deterministic-perf-review`](skills/FP-C/fpc05-deterministic-perf-review/SKILL.md) |
| 新代际（A5）性能不升反降 | [FP-C06 A5 性能劣于 A2](patterns/FP-C/FP-C06.md)（高） | 跨代基线对比；查新代际路径 | [`fpc06-soc-generation-perf-review`](skills/FP-C/fpc06-soc-generation-perf-review/SKILL.md) |
| 同芯片不同板型（B2 vs B3）性能差异 | [FP-C04 A2 B2 机器性能劣于 A2 B3](patterns/FP-C/FP-C04.md)（低） | 板型矩阵对比；查频率/带宽假设 | [`fpc04-board-variant-perf-review`](skills/FP-C/fpc04-board-variant-perf-review/SKILL.md) |

## T6 内存 / 资源

> 结果对、能跑完，但占用高或 OOM。先分清**峰值超基线**与**双路径（aclnn vs aclop）差异**。

### 内存占用

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| OOM / 峰值内存超基线 / 显存过度占用 | [FP-D01 GPU 迁移 NPU 场景显存过度占用](patterns/FP-D/FP-D01.md)（高） | profiler 峰值内存；workspace 申请量推导 | [`fpd01-aclnn-review`](skills/FP-D/fpd01-aclnn-review/SKILL.md) |
| aclnn 比 aclop 内存高 / 内存占用偏高 | [FP-D02 aclnn 内存占用高于 aclop](patterns/FP-D/FP-D02.md)（中） | aclnn/aclop 双路径内存对比 | [`fpd02-aclnn-review`](skills/FP-D/fpd02-aclnn-review/SKILL.md) |

## T7 编译 / 交付 / 文档 / 测试资产

> 代码可能没错，但**声明面、测试面或交付面**出了问题：测试全绿却线上异常、文档说支持却没适配、迁移后丢了拦截。

### 测试资产与交付面

| 症状（含同义词） | 候选模式 | 首查动作 | skill |
|---|---|---|---|
| 测试全绿而线上特定 shape 异常 / 同 shape 跨平台表现不同 | [FP-A19 同算子多 tiling 路径覆盖盲区（新增路径未纳入测试矩…](patterns/FP-A/FP-A19.md)（高，4 案） | 三表：tiling 模板 × 阈值 × 用例 | [`fpa19-aclnn-review`](skills/FP-A/fpa19-aclnn-review/SKILL.md) |
| golden 失配 / 精度验证静默失效 | [FP-E01 golden/UT 期望值失配或按错误实现编写](patterns/FP-E/FP-E01.md)（高） | golden 来源与命名；看是否与实现同改 | [`fpe01-golden-review`](skills/FP-E/fpe01-golden-review/SKILL.md) |
| 迁移 / 重构后应拦截未拦截 | [FP-B03 跨仓迁移丢失防御/拦截逻辑](patterns/FP-B/FP-B03.md)（高） | 迁移 diff 的拦截点前后比对 | [`fpb03-migration-review`](skills/FP-B/fpb03-migration-review/SKILL.md) |
| 支持矩阵与注册不符 / 文档整体复制兄弟算子 | [FP-F03 文档/声明面与实现面不一致](patterns/FP-F/FP-F03.md)（中） | README 支持表与 AddConfig 差集 | [`fpf03-doc-review`](skills/FP-F/fpf03-doc-review/SKILL.md) |
| 部分算子崩溃、部分正常（文件级参差） | [FP-B05 入参校验覆盖度参差（同仓内文件级）](patterns/FP-B/FP-B05.md)（低） | CheckNotNull / CheckParams 横向比对 | [`fpb05-coverage-review`](skills/FP-B/fpb05-coverage-review/SKILL.md) |

---

> 维护：新增模式时必须同时登记 `triage_map.json`（否则 C20 报「未覆盖」）；某组候选超过 6 条说明入口过粗，先拆组而不是硬塞。
