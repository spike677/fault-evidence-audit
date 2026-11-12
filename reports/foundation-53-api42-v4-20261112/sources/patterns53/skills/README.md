# Skills：故障模式的可执行检视层

> `patterns/` 是**知识卡**：一模式一卡，回答"是什么、为什么、怎么防"；`skills/` 是**可执行消费层**：把单张卡转成"对某个接口/模块，按什么清单查、怎么判定、产出什么"的检视流程。两者并列、七类目录一一镜像。

## 目录约定

```text
skills/
├── README.md                   # 本文件：目录约定 / 编写规范 / 消费方式 / 覆盖索引
├── FP-A/fpa01-kernel-review/SKILL.md   # 精度类
├── FP-A/fpa02-kernel-review/SKILL.md
├── …                             # 每模式一目录一 SKILL.md（目录名 = frontmatter 注册名 name）
├── FP-B/fpb01-checker-review/SKILL.md  # 功能/兼容类
├── …
├── FP-C/fpc01-aclnn-review/SKILL.md    # 性能类
├── FP-D/fpd01-aclnn-review/SKILL.md    # 资源/内存类
├── FP-E/fpe01-golden-review/SKILL.md   # 测试有效性类
├── FP-F/fpf01-build-review/SKILL.md    # 工程/交付类
└── FP-G/fpg01-hang-review/SKILL.md ~ fpg02-sync-review/SKILL.md   # 执行可靠性类（2 条）
```

七类共 53 条已全部铺开，一模式一目录一 `SKILL.md`（完整清单见文末「当前覆盖」）。

- 路径对应：`skills/FP-X/<skill-name>/SKILL.md` ↔ `patterns/FP-X/FP-XX.md`；类别字母一致，**skill 目录名 = frontmatter 注册名 `name`**（业界 Agent Skills 规范：`name` 须等于 `SKILL.md` 父目录名），编号对照见文末覆盖表。
- 一个模式目录内除 `SKILL.md` 外，可按需增加 `references/`、`scripts/` 等附属文件（Agent Skills 的目录即技能单元）。**深度档的 `references/detect-l2-l3.md`（v6.18.1）是生成物**：L2 判据全字段 + 所涉 oracle 的 L3 失效条目，由 `scripts/sync_detect_section.py` 生成、守门 **C42** 校验；`SKILL.md` 内只留约 0.7 KB 指针段（体积约束：`score_skills.py` 的 `fit` 维度按技能体积打分，内联全文会把多份技能顶过 36 KB 阈值）。

## SKILL.md 编写规范

1. **文件名固定大写 `SKILL.md`**，首部为 YAML frontmatter：

   ```yaml
   ---
   name: "fp{编号}-{动作}"          # 如 fpa05-aclnn-review；小写字母+连字符（业界 Agent Skills 命名法，不含下划线），全库唯一、一经使用不改，且必须等于 SKILL.md 父目录名
   description: "做什么 + 何时触发"  # 两个值一律加引号；≤200 字符；触发条件必须写全（决定 skill 能否被正确调起）
   ---
   ```

2. **自包含**：对应模式卡的精华（适用头 / 机理 / 映射点或成因）必须**内嵌**进 SKILL.md 正文，不能只留链接——skill 被安装到库外环境后，仓内相对路径会失效。
3. **与卡片保持一致**：内嵌的模式卡摘要以 `patterns/FP-X/FP-XX.md` 当前版本为准；卡片演进（如 FP-B07 v2.17 增补成因⑥）时，对应 skill 须同步更新。
4. **零环境依赖**：不得出现本仓之外的环境专属内容——本地工具/任务名、内部缺陷单号（如 BUG-YYYYMMDD-XX）、本地克隆路径、内部日报引用等。新人拿到任一 SKILL.md 即可独立消费，不需要任何额外上下文；实证引用一律用公开仓 issue 编号（如 ops-nn #1182）。
5. **内容写动作，不抄整卡**：skill 的主体是流程（定位实现 → 清单逐项核查 → 判定 → 产出物模板），模式卡全文留在 `patterns/`，skill 只内嵌检视必需的摘要。
6. 语言与卡片一致（中文）；S×O 定级、判定三关等口径与 [docs/STANDARDS.md](../docs/STANDARDS.md)「库标准」保持一致。
7. **业务影响评估（B 轴，v3.4）**：定级节须内嵌 B 轴标准段（业务可达性 B1~B3 + 业务影响类型 + 处置建议矩阵），Bug 卡与报告模板须含 B 轴字段。B 轴与 S×O **正交**：只决定修复优先级建议，**不得参与 S/O 取值、不得改动卡片定级**；全库统一措辞以守门脚本 `check_fault_patterns.py` 的 `SKILL_BAXIS_CANON` 常量为权威源（与全部 SKILL.md 第 6 节逐字一致），新增/同步 skill 时逐字复制该段，不另行改写（模式特有补充只能追加在标准段之后）。守门脚本 C19 逐份校验（标准段逐字内嵌 + 流程步「业务可达性核查」+ Bug 卡 B 轴字段 + 报告 B 轴说明 + 数量/覆盖表/注册名三方对应），C19b 校验索引 `business_impact` 词表与标准段一致。

   B 轴判例校准（同机理、不同触发面 → 不同 B；判定时对照，防止一刀切降档）：

   | 判例 | 机理 | 触发条件 | B | 依据 | 处置建议 |
   |---|---|---|---|---|---|
   | aclnnMatmul 大 M 偏移回绕（构造演示） | FP-B07 成因⑥ | M×K ≥ 2^32（如 M=1e8、K≥43，单 fp16 操作数 ≥8.6 GB） | B1 | 超出业务自然构造路径：LLM 训练/推理中 matmul 的 M 为 batch×seq 量级（1e2~1e4） | 记录（业务难以触达） |
   | rms_norm 大 shape 静默全 0（ops-nn #4494） | FP-B07 成因⑥ / FP-A04 | 线性元素位置 ≥ 2^32（约 1M token 级张量） | B2 | 长上下文场景存在但非默认；实证 issue 本身即「曾真实发生」的证据，倾向 B2/B3 | 排期修 |
   | RmsNormGrad 空张量 dgamma NaN（ops-nn #5560） | FP-A05 | 空张量 / 退化 shape | B3 | 动态 shape / 零元素分片是框架常规路径 | 尽快修 |

   三判例技术档可同（如均 S3×O1=3 中），B 轴把处置建议拉开为 记录 / 排期修 / 尽快修——这正是 B 轴的区分度所在；降档（B3→B2/B1）必须给出上表「依据」列级别的证据，不得仅凭"业务应该不会这么用"。

8. **判定纪律（v3.6）**：第 7 节须逐字内嵌 `SKILL_JUDGMENT_CANON` 标准段（非对称增减 + 证据等级 + Agent 误判记录 + 误判回流），Bug 卡须含 `- **证据等级**：` 与 `- **Agent 误判记录**：` 两字段，报告模板须声明证据等级分布；权威源同为守门脚本常量，新增/同步 skill 时逐字复制、不另行改写。守门脚本 **C19c** 逐份校验（标准段逐字 + 三处机检片段），**C19d** 校验误判台账 `cases/misjudgments.jsonl`（字段 / 枚举 / fp_id 引用 / id 唯一 / 无内部单号）。**非对称规则的理由**：否决造成的漏报用户不可见、不可恢复；补查只增候选，错了可由用户排除——因此「加候选」只需有据，「减候选」必须附 `[文件]:[行号] [代码行]` 负向证据。

9. **能力边界与自检（v3.9）**：每份 skill 末尾须有 `## 10. 能力边界与自检` 一节，含四条边界声明（静态可证 / 需实测确认 / 不覆盖 / **找不到 ≠ 没有**）与四条自检命令（`gen_triage.py --check`、`scan_fp.py --only <本模式>`、`verify_lines.py`、`check_fault_patterns.py`）。**「找不到 ≠ 没有」是硬声明**：未命中只能表述为「本轮未发现」，抽样核查须在报告写明抽样口径；守门 **C24** 逐份校验。

10. **工作量与抽样（v4.0）**：第 10 节须含 `### 工作量与抽样（v4.0）`，规则由索引 `depth` 决定——**深度**=全量核查不抽样；**标准**=每映射点取前 20 处、同一映射点连续 20 处反证排除即停止；**宽浅**=签名定位 + 每类抽 3 例。报告必填抽样口径与停止点记录；守门 **C26** 校验「规则与索引 depth 一致」。质量基线见 [SCORECARD.md](SCORECARD.md)（v5.0 十维评分，含 **depth 内容深度** 30 分权重；顶部有三份人工基准锚定读分；`score_skills.py` 生成，守门 C27）。

11. **已知缺陷案例库（v5.1，深度档必备）**：`depth=深度` 的 skill 末尾须追加一节「已知缺陷案例库：触发条件 / 根因 / 修复范式 / 针对性深挖」，把本型**已确认缺陷**拆到代码级——每例按「触发条件 → 根因（具体路径，引 `文件:行号` + 公开 issue/PR）→ **✅ 修复范式代码**（无真实修复来源时标「示意」，**不得配虚构行号**）→ 针对性发现（可执行 grep + 代码级判据）→ 最小复现锚」写，末附本模式 `scan_fp.py --only FP-XX` 起手式与卡片语料数字。**素材只取自卡片既有实证与 skill 自身引用，严禁臆造 issue 编号或行号**（`verify_lines.py` 可校行号）。

12. **真取证加深（v5.4，深度档推进项）**：对 `depth` 分最低的深度档 skill，按「**实测代码替换示意代码**」推进，把案例库里的示意修复代码替换为**六仓实测 commit 的真实代码**（`git show HEAD:<path>` 取原文 + 记录 HEAD commit），行号一律重定位到 HEAD 锚，并补齐三件套：① **同根因连发完整清单**（本型在本仓/本目录的全部已知落点，含**镜像副本**——主目录与 `experimental/` 等同名副本须逐一对同名算子做交叉比对，主目录已修而副本未修即记为「漏插修复」）；② **反向排除项**（本型**不是**什么，给可核对的负向代码锚，避免一刀切误判）；③ **扫描基线真实计数**（本型标志符号在目标仓的真实命中数，供后续回归比对）。**素材边界（硬约束）**：只引卡片既有实证编号与 skill 自身引用，**严禁臆造 issue 编号/行号**；无法在实测 commit 定位的（编号/符号）一律标「**待人工复核**」并写明检索范围，不得补写虚构行号；与卡片元数据不一致处（如卡片记「进行中」而实测已含修复、卡片记「N 项」而实测项数不同）**只在 skill 内注明差异待复核，不改卡片元数据**。该节与第 11 条案例库衔接：案例库给出机理与范式，本节给出**可复算的真实证据**。样板见 [FP-B12 §13](FP-B/fpb12-early-exit-review/SKILL.md) 与 [FP-A01 §12](FP-A/fpa01-kernel-review/SKILL.md)。

## 消费方式

- **人工 / Agent 照做**：SKILL.md 本身就是一份完整检视手册，按其「检视流程」逐节执行即可。
- **安装为 Agent Skill**：把模式目录（如 `skills/FP-A/fpa05-aclnn-review/`，目录名即注册名）复制到所用 agent 的技能目录（如 `~/.trae-cn/skills/<name>/`），frontmatter 的 `name` 即注册名，`description` 即触发说明。

## 当前覆盖（52 / 52）

| 编号 | 模式 | skill name | 检视口径 |
|---|---|---|---|
| [FP-A01](FP-A/fpa01-kernel-review/SKILL.md) | 硬件指令精度不足，未与竞品对齐 | `fpa01-kernel-review` | 近似超越函数指令选型 / pow 组合近似 / log1p 补偿 / 级数截断与系数精度 |
| [FP-A02](FP-A/fpa02-kernel-review/SKILL.md) | 归约/累加实现顺序与竞品不一致 | `fpa02-kernel-review` | 归约拓扑（树形 vs 串行）/ 多核分组顺序 / 优化重排结合顺序 |
| [FP-A03](FP-A/fpa03-kernel-review/SKILL.md) | 竞品高精度中间计算，NPU 直接低精度 | `fpa03-kernel-review` | 中间变量位宽 / 高精度中间缓冲缺失 / fp16-bf16 逐层累积 |
| [FP-A04](FP-A/fpa04-aclnn-review/SKILL.md) | 功能问题演变为精度静默故障 | `fpa04-aclnn-review` | 静默早退 / 恒返回成功 / 吞错续跑 |
| [FP-A05](FP-A/fpa05-aclnn-review/SKILL.md) | 脏数据 / 数据踩踏 | `fpa05-aclnn-review` | 五映射点（缓冲初始化 / workspace 清零 / 未初始化先读 / 原地写 / 越界尾块） |
| [FP-A06](FP-A/fpa06-kernel-review/SKILL.md) | 确定性开关下结果不固定 | `fpa06-kernel-review` | 确定性分支生效性 / 原子加消除定序 / 多核归约定序 / 缓冲清零 |
| [FP-A07](FP-A/fpa07-aclnn-review/SKILL.md) | tiling 条件判断错误走入错误分支 | `fpa07-aclnn-review` | tiling 分支边界（算符方向 / off-by-one / 尾块与奇异 shape） |
| [FP-A08](FP-A/fpa08-kernel-review/SKILL.md) | 切块粒度差异致离群点精度问题 | `fpa08-kernel-review` | 切块粒度 / 尾块覆盖对齐 / padding 中性元 / 尾核分核不整除 |
| [FP-A09](FP-A/fpa09-aclnn-review/SKILL.md) | 对标 TF 语义与 PTA（torch_npu）不一致 | `fpa09-aclnn-review` | attr 默认值 / clip-epsilon 语义 / nan-inf 处理 / 对标框架选择 |
| [FP-A10](FP-A/fpa10-aclnn-review/SKILL.md) | 原型 Attr 不支持 Double | `fpa10-aclnn-review` | proto Attr 类型定义 / 解析分支 double 支持 / 静默降级下溢 |
| [FP-A11](FP-A/fpa11-aclnn-review/SKILL.md) | AiCore 不支持 double 类型 | `fpa11-aclnn-review` | 声明实现一致性 / float64 拆分模拟 / 明确拦截报错 / dtype 分派 |
| [FP-A12](FP-A/fpa12-intfloat-review/SKILL.md) | 大整数转 fp32 计算精度损失 | `fpa12-intfloat-review` | int64-int32→float 转换点 / 乘法前未升位 / 尾数 2^24 上界 |
| [FP-A13](FP-A/fpa13-input-rounding-review/SKILL.md) | 输入尾数截断才能通过精度标准 | `fpa13-input-rounding-review` | golden-UT 输入 round 截断 / 输入分布一致性 / 精度标准掩盖链 |
| [FP-A14](FP-A/fpa14-mmad-review/SKILL.md) | FFMA 与 MMAD 硬件指令差异 | `fpa14-mmad-review` | MMAD 指令配置 / stepK 搬运步长 / K 对齐补零 / 双路径对照 |
| [FP-A15](FP-A/fpa15-kernel-review/SKILL.md) | inf/nan 特殊值行为差异 | `fpa15-kernel-review` | isnan 比较分支 / inf 传播 / clamp 对 nan 行为 / 特殊值来源矩阵 |
| [FP-A16](FP-A/fpa16-aclop-aclnn-review/SKILL.md) | aclop 与 aclnn 编译阶段精度差异 | `fpa16-aclop-aclnn-review` | 调用入口清单 / 常量折叠 / pad 对齐预处理 / 双路径行为对齐 |
| [FP-A17](FP-A/fpa17-socgen-review/SKILL.md) | A1 与 A2 硬件代际精度差异 | `fpa17-socgen-review` | GetSocVersion 代际分支 / 精度硬编码对称性 / 多代基线覆盖 |
| [FP-A18](FP-A/fpa18-int32float-review/SKILL.md) | int32 边界值转 float 舍入致比较语义偏差 | `fpa18-int32float-review` | 整型极值转 float 常量 / 比较前类型提升 / 混合 int-float 表达式 |
| [FP-A19](FP-A/fpa19-aclnn-review/SKILL.md) | 同算子多 tiling 路径覆盖盲区 | `fpa19-aclnn-review` | 多 tiling 模板枚举 / IsCapable 阈值区间 / 用例分布映射 |
| [FP-A20](FP-A/fpa20-determinism-review/SKILL.md) | 确定性等级未分级标注 | `fpa20-determinism-review` | 逐输出归约方式 / 核内与跨核归约 / 平台参数依赖 / 切核维度分级表 |
| [FP-A21](FP-A/fpa21-tiling-state-review/SKILL.md) | tiling 状态跨调用/跨线程污染 | `fpa21-tiling-state-review` | 可变全局清点 / 路径赋值完备性 / TilingData 载体 / 成对实现连带 + 序列化与并发验证 |
| [FP-A22](FP-A/fpa22-dtype-dispatch-review/SKILL.md) | kernel dtype 分派/模板映射错配 | `fpa22-dtype-dispatch-review` | 支持集 vs 映射表差集 / 各模板输出上界 / bool 与无符号特化 / default 兜底 + dtype 全组合魔数实测 |
| [FP-B01](FP-B/fpb01-checker-review/SKILL.md) | 支持面校验过严误拦截合法输入 | `fpb01-checker-review` | dtype/format/shape/quant_mode 白名单一致性 / 新支持项同步 / 误判 |
| [FP-B02](FP-B/fpb02-corenum-review/SKILL.md) | tiling 未适配多种芯片核数 | `fpb02-corenum-review` | 核数-AIC-AIV 硬编码 / SOC 分支遗漏 / 核数假设未参数化 |
| [FP-B03](FP-B/fpb03-migration-review/SKILL.md) | 跨仓迁移丢失防御/拦截逻辑 | `fpb03-migration-review` | 迁移 diff 被删防御分支 / 显式 skip 检查 / 前后拦截比对 |
| [FP-B04](FP-B/fpb04-aclnn-review/SKILL.md) | aclnn 必选入参空指针校验缺失 | `fpb04-aclnn-review` | aclnn 接口必选入参判空矩阵检视（「必须触发」） |
| [FP-B05](FP-B/fpb05-coverage-review/SKILL.md) | 入参校验覆盖度参差（同仓内文件级） | `fpb05-coverage-review` | CheckNotNull 骨架存在性 / CheckParams 聚合入口 / 仓内范式一致性 |
| [FP-B06](FP-B/fpb06-aclnn-review/SKILL.md) | 空 tensor（numel==0）输入分支处理缺失 | `fpb06-aclnn-review` | 空 tensor 分支覆盖（判空 / 早退 / 平台对称 / kernel 适配，「必须触发」） |
| [FP-B07](FP-B/fpb07-aclnn-review/SKILL.md) | 索引/偏移计算错误致越界 | `fpb07-aclnn-review` | 六成因（含 v2.17 成因⑥） |
| [FP-B08](FP-B/fpb08-fallback-review/SKILL.md) | 节点级配置未参与派发决策 | `fpb08-fallback-review` | fallback 回调 / 前端插件 / fusion pass 三载体属性透传 |
| [FP-B09](FP-B/fpb09-dynamic-shape-review/SKILL.md) | 动态 shape 标签未参与校验决策 | `fpb09-dynamic-shape-review` | 哨兵值当实数用 / GetDims 越界 / GetShapeRange 前未 MakeUpRange |
| [FP-B10](FP-B/fpb10-hccl-review/SKILL.md) | 集合通信算子功能/兼容问题 | `fpb10-hccl-review` | 拓扑下标越界 / infershape 未 SetDim / 配置窄化 / 同族不对称 |
| [FP-B11](FP-B/fpb11-validation-review/SKILL.md) | 第一段接口/InferShape 参数契约校验缺失（非法 shape/rank/attr 放行） | `fpb11-validation-review` | 参数契约六类（rank/长度/值域/有限性/dtype 组合/前后段一致性） |
| [FP-B12](FP-B/fpb12-early-exit-review/SKILL.md) | 空/退化输入早退路径未写非空输出（SUCCESS + 未初始化输出） | `fpb12-early-exit-review` | 早退路径输出写入（逐输出/语义基线/平台对称） |
| [FP-B13](FP-B/fpb13-narrowing-review/SKILL.md) | host 侧 int64→int32 窄化/乘积溢出（参数值静默改变） | `fpb13-narrowing-review` | host 侧窄化（属性/维度/乘积/偏移/size_t 下溢） |
| [FP-B15](FP-B/fpb15-capacity-review/SKILL.md) | 定长容器容量无校验（入参索引 + 越界写 + 静默截断） | `fpb15-capacity-review` | 定长数组 × 入参索引 × 无上界校验，族内兄弟对拍 |
| [FP-B14](FP-B/fpb14-graph-path-review/SKILL.md) | 图模式（GEIR/aclGraph）通路与 aclnn 单算子通路未同步适配 | `fpb14-graph-path-review` | 图模式双路径契约（proto 默认值/format 白名单/属性下发/可选输入/注册/一致性） |
| [FP-C01](FP-C/fpc01-aclnn-review/SKILL.md) | 算子端到端耗时占比高且单次调用耗时高 | `fpc01-aclnn-review` | 性能三子型（实现层冗余 / 调度层膨胀 / 基线回归） |
| [FP-C02](FP-C/fpc02-dtype-perf-review/SKILL.md) | A2 上 fp16 Vector 算子性能不如 bf16 | `fpc02-dtype-perf-review` | dtype 派发对称性 / fp16 降级路径 / DAG 冗余 Cast |
| [FP-C03](FP-C/fpc03-dtype-specialization-review/SKILL.md) | bf16 与 fp16 性能差异大 | `fpc03-dtype-specialization-review` | dtype 特化完整性 / 硬件-API 缺口 / DAG 冗余软件 Cast |
| [FP-C04](FP-C/fpc04-board-variant-perf-review/SKILL.md) | A2 B2 机器性能劣于 A2 B3 | `fpc04-board-variant-perf-review` | 频率-带宽 tiling 假设 / 板型分流 / 分核配置 |
| [FP-C05](FP-C/fpc05-deterministic-perf-review/SKILL.md) | 确定性场景性能大幅劣于非确定性 | `fpc05-deterministic-perf-review` | 开关分叉 / 串行化与并行度禁用 / 排序去重 / 原子累加消除 |
| [FP-C06](FP-C/fpc06-soc-generation-perf-review/SKILL.md) | A5 性能劣于 A2 | `fpc06-soc-generation-perf-review` | 代际分支枚举与 default 落点 / 新代际路径迁移 / 旧代际误伤 |
| [FP-D01](FP-D/fpd01-aclnn-review/SKILL.md) | GPU 迁移 NPU 场景显存过度占用 | `fpd01-aclnn-review` | workspace 申请量推导 / 内存复用 / 缓存与图模式申请路径 |
| [FP-D02](FP-D/fpd02-aclnn-review/SKILL.md) | aclnn 内存占用高于 aclop | `fpd02-aclnn-review` | workspace-中间 tensor 复用 / lifetime 分析 / 场景化裁剪 |
| [FP-E01](FP-E/fpe01-golden-review/SKILL.md) | golden/UT 期望值失配或按错误实现编写 | `fpe01-golden-review` | 测试资产三类核查（命名失配 / golden 与实现同源 / 参照失真） |
| [FP-E02](FP-E/fpe02-benchmark-review/SKILL.md) | 精度测试判据与标杆口径设计缺陷 | `fpe02-benchmark-review` | 降精度误比全精度标杆 / 阈值落 1 ulp 带内 / 缺绝对误差地板 / 分母退化 |
| [FP-F01](FP-F/fpf01-build-review/SKILL.md) | 构建/工程配置不一致致编译与产物缺陷 | `fpf01-build-review` | 六成因（原型重复 / 去重宏 / include 路径 / binary.json 缺失 / SoC 双源 / 别名 fallback） |
| [FP-F02](FP-F/fpf02-observability-review/SKILL.md) | 维测与错误上报缺陷（含跨仓错误码不一致） | `fpf02-observability-review` | 五子型（日志-dump 缺失 / 跨仓错误码不一致 / 错误码选错 / 静默吞错 / 日志级别误用） |
| [FP-F03](FP-F/fpf03-doc-review/SKILL.md) | 文档/声明面与实现面不一致 | `fpf03-doc-review` | 四成因（支持矩阵 vs AddConfig / 确定性声明 / 复制残留 / help 与映射矛盾） |
| [FP-F04](FP-F/fpf04-delivery-review/SKILL.md) | 算子接口交付面缺失 | `fpf04-delivery-review` | 六成因差集（符号导出 / 注册 / 派发 / 降级 / 商分 / 开源同步） |
| [FP-G01](FP-G/fpg01-hang-review/SKILL.md) | 执行挂死与调度超时 | `fpg01-hang-review` | 挂死五子型（「必须触发」，无条件执行清单） |
| [FP-G02](FP-G/fpg02-sync-review/SKILL.md) | 核间/流水同步缺失或配对不完整 | `fpg02-sync-review` | 同步六子型（配对完整性检查：扫孤儿原语 + 作用域审计——先扫 set/wait 配平与 racecheck WAW/RAW，再核同步四件套是否被分支独占） |

全部 53 条已建 skill。新增/演进模式时按「编写规范」逐条自检后提交，并在本表登记。
