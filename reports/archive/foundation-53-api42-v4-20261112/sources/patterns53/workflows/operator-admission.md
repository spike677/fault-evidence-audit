# operator-admission：新算子 / 新接口准入体检

> 用于**新增算子、新增 aclnn 接口、大版本合入**前的体检：不是全库 52 条都跑，而是「必须触发项无条件 + 高风险按相关度」。
> 产出是一份可归档的准入报告，含命中、观察项、反证排除与**跳过清单**。
>
> **必须触发项不在这里硬编码**：以索引 `applicability.trigger == "必须触发"` 为准（当前 6 条，上限由守门 C14 约束）。
> 硬编码清单的历史教训——v6.16 的本文只写了 4 条，而索引已有 6 条，**FP-A22（dtype 分派错配）与 FP-G02（同步缺失）被整段漏检**，
> 且守门当时不校验工作流与索引的一致性。取当前清单：

```bash
python3 -c "import json;idx=json.load(open('fault_patterns_index.json',encoding='utf-8'));\
print([p['id'] for p in idx['patterns'] if (p.get('applicability') or {}).get('trigger')=='必须触发'])"
```

## 输入

- 仓（`ops-nn` / `ops-math` / `ops-cv` / `ops-transformer` / `hccl` …）与算子目录或 aclnn 接口名；
- ref（默认 master）与本地 HEAD 记录；
- 可选：本算子已知 issue / 历史缺陷，用于优先排序。

## 阶段

### Stage 0 — 圈定范围

1. 接口名 → 算子目录（去 `aclnn` 前缀 + 驼峰转下划线）；
2. 列目录：`op_host/`（tiling / infershape / config）、`op_kernel/`、`op_api/`、`tests/ut/`、`docs/`；
3. **适用面筛选**：读每条模式「适用」头（仓 / 侧别 / 载体），不匹配 → 跳过清单（写编号 + 理由）；
4. 按 `depth` 预置工作量：本任务默认「标准」，接口含 kernel 大模板时升「深度」。

### Stage 1 — 必须触发项（无条件，不依赖签名）

**清单由索引 `applicability.trigger == "必须触发"` 决定，不在此处写死。** 当前 6 条（v6.18）：

| 模式 | skill | 查什么 |
|---|---|---|
| FP-A22 | [fpa22-dtype-dispatch-review](../skills/FP-A/fpa22-dtype-dispatch-review/SKILL.md) | kernel dtype 分派 / 模板映射错配（特定 dtype 静默走错分支） |
| FP-B04 | [fpb04-aclnn-review](../skills/FP-B/fpb04-aclnn-review/SKILL.md) | 必选入参判空矩阵（SIGSEGV / rc=139 面） |
| FP-B06 | [fpb06-aclnn-review](../skills/FP-B/fpb06-aclnn-review/SKILL.md) | 空 tensor / 零元素分支（numel==0） |
| FP-B07 | [fpb07-aclnn-review](../skills/FP-B/fpb07-aclnn-review/SKILL.md) | 索引 / 偏移越界（含 2^32 上界反推） |
| FP-G01 | [fpg01-hang-review](../skills/FP-G/fpg01-hang-review/SKILL.md) | 挂死五子型（循环推进 / 回绕 / 超时 / 泄漏） |
| FP-G02 | [fpg02-sync-review](../skills/FP-G/fpg02-sync-review/SKILL.md) | 核间 / 流水同步缺失或配对不完整（六子型） |

> 这六条与算子形态无关：全部过完才进入 Stage 2；任一命中即按 Bug 卡流程出卡（证据等级 + B 轴）。
> **改索引后必须回到本节核对**——表与索引不一致时以索引为准，并同步本表。

### Stage 2 — 高风险模式（按相关度排序）

1. 取索引 `risk.level = 高` 且适用面匹配的模式；
2. 按输入输出契约挑前 6~10 条：有 dtype 转换 → A03/A12/A18；有归约 → A02/A20；有 tiling 分支 → A07/A19；有构建/交付变更 → F01/F04；有图模式 → B08/B14；
3. 每条跑 skill 第 4 节清单，**记录防护面证据**（反证排除也要留痕）；
4. 命中进入 Stage 4，观察项单列。

### Stage 3 — 文档与交付面

- [fpf03-doc-review](../skills/FP-F/fpf03-doc-review/SKILL.md)：README 支持表 vs `AddConfig`、示例可编译性；
- [fpf04-delivery-review](../skills/FP-F/fpf04-delivery-review/SKILL.md)：符号导出 / 原型注册 / 派发表 / 商分清单；
- [fpe01-golden-review](../skills/FP-E/fpe01-golden-review/SKILL.md)：golden 来源与用例命名（新算子最常见的是「没有反例用例」）。

### Stage 4 — 合并与报告

**去重规则**：同一 `文件:行号` 多模式命中 → 合并一条，主模式取「证据等级最高 + 触发最具体」者，其余记关联模式。

准入报告结构：

```markdown
# {算子} 准入体检报告（YYYY-MM-DD）
## 一、范围与口径（仓 / ref / HEAD、适用面筛选结果、深度档、跳过清单）
## 二、必须触发项（逐条：通过 / 命中 / 观察，附证据）
## 三、高风险模式（命中明细 + Bug 卡；观察项表）
## 四、文档与交付面（支持表差集、交付清单核对）
## 五、反证排除汇总（模式 / 反证理由 / 防护面证据）
## 六、证据等级分布（静态可证 X / 需实测确认 Y）与 B 轴分布
## 七、准入结论（可合入 / 有条件合入 / 阻断）+ 待办
```

## 停止条件与边界

- 单算子体检总时长上限按深度档：标准 ≈ 8 条 skill，深度 ≈ 16 条；超出须在报告声明「未覆盖项」；
- 本 workflow **不做**性能与内存专项（C/D 类只在有变更证据时抽检）；
- 报告不写「该算子无缺陷」，只写「本轮未发现（覆盖 N 条模式 / M 处映射点）」。
