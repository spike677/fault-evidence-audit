# AGENTS.md —— 给 agent 的一页速查

> 你被要求「用这个库找算子缺陷」。这页只讲**怎么用**，不讲模式内容。看完这一页就该能开始干活，**不要**先去通读 README（20 KB，只含入口与总览表）或 53 张卡（约 220 KB）。

## 1. 30 秒决策：先读哪一份

| 你手上的输入 | 先读 | 不要读 |
|---|---|---|
| 只有现象（卡死/超差/慢/OOM/偶发） | [TRIAGE.md](TRIAGE.md) 的对应入口 → 候选 ≤6 条 | 全部卡片 |
| 指定了接口名（如 `aclnnFlashAttentionScore`） | 该接口所属类别的 skill（见下表） | 索引 JSON |
| 指定了模式编号（如 `FP-G02`） | `skills/FP-X/<skill>/SKILL.md` + `patterns/FP-X/FP-XX.md` | 其余 51 条 |
| 要批量扫代码仓 | `scripts/scan_fp.py <dir> --only FP-XX[,FP-YY]` | 逐卡人工阅读 |
| 要判断某条候选是不是真缺陷 | 该 skill 第 7 节「判定标准与反误报原则」+ `cases/cases.json` 的 `reverse_exclusions` | — |
| **要设计用例 / 写复现脚本**（问「怎么测」） | 索引里该模式的 `detect` 字段（L2：axes / oracle / min_cases / constructor / judge / kill） | 只读机理卡就造用例 |
| **要判读一个 FAIL 是不是真缺陷** | `detect_layer.oracle_failures.by_oracle[<该 oracle>]`（L3：这手段本身怎么骗你） | 直接信 FAIL / 直接信 PASS |
| **拿不准算不算缺陷 / 两卡都能套 / 想撤销候选但缺反证依据** | [INVARIANTS.md](INVARIANTS.md) 四问（对象·单位·生命周期·消费者） | 反复翻多张卡试图「感觉」归类 |
| **已有锚点，想查兄弟实现有没有同款病** | [workflows/sibling-diff.md](workflows/sibling-diff.md) | 全仓相似度扫描 |
| **要判 found / clean / uncovered 的成色，或怀疑自己证据用歪了** | [EVIDENCE_DISCIPLINE.md](EVIDENCE_DISCIPLINE.md) 十条纪律（T1 只能来自本接口实测 / 阴性不外推 / 观测不到≠阴性 / 算子级 vs 接口级） | 拿「别的接口同款」当本接口证据 |
| **失败无已知模式命中，或疑似多机理叠加** | `scripts/query_patterns.py --hits …` / `--failure …` | 硬套一条模式 |

> **三层不可混用（v6.17/v6.18）**：L1 机理层答「为什么会坏」（`patterns/` + `signatures`）｜L2 判据层答「怎么测才测得出」（索引 `detect`）｜L3 失效模式答「这个观测手段本身会怎么骗你」（索引 `detect_layer.oracle_failures`）。**取错层是开不出可上板用例的第一原因**：只读 L1 只能产出「不得复现该现象」的空壳用例。


## 2. 四步流程（每次只做一条模式）

1. **筛适用**：读卡首行 `- **适用**：仓 / 侧别 / 载体 / 触发`。仓或侧别不匹配 → **跳过并记理由**，不要硬套。
2. **定位实现**：`op_api/`（aclnn 侧）· `op_host/`（tiling/infershape）· `op_kernel/`（kernel 侧）。按「载体」列决定先看哪层。
3. **逐条核查**：照 skill 的「检视清单」走，每条给出 `[文件]:[行号] [代码行]`。**清单项未命中也要记**（观察项 / 反证排除）。拿不准时先过 [INVARIANTS.md](INVARIANTS.md) 四问（对象/单位/生命周期/消费者）——**答不出的那一行就是可疑点**，且四问的答案决定该归哪张卡。
4. **定级出卡**：S×O（见索引 `risk_rubric`）→ 风险档；B 轴（`business_impact`）→ 处置建议。命中才出 Bug 卡，观察项单列。

> 要**出实测用例**时在第 3 步后插一步：读该模式的 `detect`（L2）造反例，并先查所涉 oracle 的 L3 条目——`oracle` 存在 ≠ `oracle` 可信。

> 要**下强结论**（尤其「这个算子没问题」）时再加一步：查该模式的**第二 oracle**（`fault_patterns_secondary_oracle.json`）。单点判据的根本问题不是不准，而是**错了没人知道**——返回码对但错误码选错、racecheck 零告警但连接口都没进 kernel，这类「正确且错误」在单判据下不可见。两个判据结论不一致时，一律升级为「必须实测」，不得二选一。

## 3. 四条硬纪律（违反即报告作废）

- **命中 ≠ 成立**（库标准第 6 条）：签名命中只是候选；须过正向 + 负向两侧证据才判成立。
- **否决必须附负向证据**：撤销/排除一条候选，必须给 `[文件]:[行号] [代码行]`，不许写「上游已校验」。
- **找不到 ≠ 没有**：未命中只能表述为「本轮未发现」，并写明抽样口径与停止点。
- **判读 FAIL/PASS 前先查 L3**：任何 FAIL 都要先确认该 oracle 类别没有已知失效（`inf==inf` 假 FAIL、缺 `equal_nan` 假 FAIL、AICPU memcheck 0 字节空跑等）。**不查 L3 就报缺陷 = 报告作废**；同理，PASS 也要查「假 PASS」类失效，否则漏报。

## 4. 产出格式（缺字段视为不合格）

```markdown
# FP-XX 检视报告：<接口名>（YYYY-MM-DD）
## 一、执行概览：仓 / ref / HEAD、文件清单、命中 X / 观察 Y / 反证排除 Z、抽样口径
## 二、命中明细：每条含 模式编号+子型 / 证据等级（静态可证|需实测确认） / S×O / B 轴 / 复现方案
## 三、观察项：表（清单项 | 文件:行号 | 存疑点 | 复现方案）
## 四、反证排除：表（清单项 | 反证理由 | 防护面证据）
## 五、建议：测试拦截 / 熔断 / 修复优先级
```

模板细节见各 skill 第 8 节。报告交付前跑 `python3 scripts/verify_lines.py <报告>.md --root <被检仓根>`（行号越界/空行/纯注释会被抓出来）。

## 5. 别做这些事

- ❌ 一次读 52 张卡：先按「适用」筛选、再按候选展开（上下文开销约为全量 20%）。
- ❌ 把 `[BROAD]` 候选当结论：`half` / `double` / `Tiling` 这类 token 命中数是缺陷数的几十倍。
- ❌ 凭机理相似合并两条模式：每条卡都有「与相邻模式的边界」段，先读它。
- ❌ 改库（卡片/索引/评测集）却不跑门禁：`python3 check_fault_patterns.py`，要求 **0 ERROR**。

## 6. 自检命令

```bash
python3 check_fault_patterns.py                 # 全库一致性（C1~C50）
python3 scripts/scan_fp.py --subtypes --only FP-XX  # 子型清单（扫描/人工 两类）
python3 scripts/scan_fp.py <dir> --only FP-XX   # 单模式候选（子型可扫的带 [X-1] 标注）
python3 scripts/scan_fp.py <dir> --absence      # 缺失型（「该有却没有」）
python3 scripts/sig_yield.py <dir> --top 20      # 签名产出审计（哪条指纹在刷屏）
python3 scripts/verify_lines.py <report>.md --root <repo>
python3 scripts/run_eval.py --validate            # 评测集结构
python3 scripts/run_eval.py --transcripts <dir> --strict  # 判分 + 证据级判据（v6.4）
python3 scripts/gen_detect.py --check             # L2 齐备 + 索引↔真源一致（含 L3 逐条全等）
python3 scripts/query_patterns.py --hits FP-A05,FP-A21   # 组合故障与 next_experiment
python3 scripts/test_query_patterns.py            # 组合/未知候选的单测
python3 scripts/check_secondary_oracle.py --check  # 第二 oracle 覆盖 + 机理独立性
python3 scripts/check_anchors.py --repos <父目录>   # 真实锚在算子仓 HEAD 是否仍可复算
python3 scripts/mutate_ops.py --run --repos <父目录>  # 变异测试：量化 kill rate
python3 scripts/ci_gate.py                        # 一条命令跑完全部门禁（与 CI 同源）
```

> 版本：v6.63 ｜ 规模：54 条 ｜ 有可扫签名：50/54 ｜ 已机读化子型：23 模式 / 105 条 ｜ 深度档：21 ｜ L2 判据：54/54 ｜ L3 失效：11 类 / 69 条 ｜ 组合：3 条 ｜ 第二 oracle：25 模式 / 47 关系
