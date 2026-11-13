# 评测集（evals/）

> **这是什么**：54 条模式各一份 `evals.json`，每份 3 个用例，用来回答一个此前无法回答的问题——
> **「这个库的检视 skill 到底判得准不准」**。没有评测集时，「命中判定置信度 ≥70%」只是口号；
> 有了它，路由准确率、近邻误判、越界强行回答都可以量化并回归。

## 目录与结构

```text
evals/
├── README.md            # 本文件：协议 / 判分口径 / 如何跑
├── FP-A01/evals.json    # 每条模式一份（编号目录）
└── …
```

```json
{
  "skill_name": "fpa06-kernel-review",
  "pattern_id": "FP-A06",
  "eval_mode": "text",
  "verdict_convention": "回答末尾须有一行 `verdict: <FP-XX | OUT_OF_SCOPE>`",
  "evals": [
    {"id": "FP-A06-P1", "kind": "positive", "prompt": "…", "expected_verdict": "FP-A06", "expected_output": "…",
     "must_include": ["首查|检查项|核对|排查|扫描|查看|定位", "证据等级|静态可证|需实测确认|信息不足|缺.{0,6}证据", "FP-A06"],
     "forbidden": ["BUG-\\d{8}|[A-Za-z]:\\\\|内部日报|内部缺陷单", "已确认为缺陷|必然是缺陷|无条件确定是缺陷"]},
    {"id": "FP-A06-N1", "kind": "neighbor-negative", "prompt": "…", "expected_verdict": "FP-A02", "expected_output": "…"},
    {"id": "FP-A06-X1", "kind": "out-of-scope", "prompt": "…", "expected_verdict": "OUT_OF_SCOPE", "expected_output": "…"}
  ]
}
```

## 证据级判据（v6.4：`must_include` / `forbidden`）

> 只判 `verdict:` 的评测，测的是「症状词 → 编号」的查表能力，**测不出答案有没有据、有没有编**。v6.4 起每条用例带两组正则：

| 字段 | 语义 | 抓什么 |
|---|---|---|
| `must_include` | **全部须命中（AND）** | 动作侧（`首查/检查项/核对…`）+ 证据侧（`证据等级 / 静态可证 / 需实测确认 / 信息不足`）；OOS 用例改为「定界/环境/方案选型」措辞 |
| `forbidden` | **命中任一即扣** | ① 内部单号与本地路径泄漏（`BUG-YYYYMMDD-XX`、`C:\…`）② 绝对化断言（`已确认为缺陷`）③ OOS 用例里强行 `属 FP-XX` |

两组判据只在 `run_eval.py --strict` 下生效（默认仍只判 verdict，方便对比"只判路由"与"判到证据"的差距）。守门 **C36** 校验：每条用例两组均非空、正则均可编译、OOS 剧本去重 ≥12 个且任一剧本复用 ≤3 次。

## 三类用例（缺一不可）

| kind | 考什么 | 期望 |
|---|---|---|
| `positive` | **召回**：现象确实属于本模式 | 判给本模式 |
| `neighbor-negative` | **区分**：现象属于相邻模式（`related[0]`），且带该模式的**典型工具证据**；本模式是陷阱 | 判给相邻模式，**不得判本模式** |
| `out-of-scope` | **克制**：未定界到算子缺陷 / 环境或选型问题 | 声明不适用（`OUT_OF_SCOPE`），不得硬套任一模式 |

只有 positive 会掩盖误报；只有 negative 会掩盖召回——与 `ascendc-sync-audit` 的 defects/correct 双组同理。

### neighbor 用例的设计（v2，v4.4 起）

v1 的 neighbor 直接复用相邻模式的症状，等于把相邻模式的 positive 再考一遍，测不出区分度。v2 改为：

- `【现象】` 用相邻模式（`related[0]`）的症状（最多 3 条）；
- `【已有证据】` 给出**该模式的典型工具证据**（取自索引 `detectors[0]`，如 `mssanitizer` / `profiler` / `golden 命名扫描`）；
- 用例带 `discriminator` 字段，写明「Y 的证据类型是 X 不产生的」；
- **禁止泄题**：prompt 不得出现「请勿误判」之类的提示；`run_eval --validate` 会拦截；
- **禁止与 positive 重复**：neighbor 的 prompt 与任一 positive 完全相同即判错（同样由 `--validate` 拦截）。

这样 neighbor 考的是「现象相似、但证据类型指向另一个模式」时的判别能力，而不是背症状。

## 作答协议（任何 agent 通用）

1. 从 `evals/<FP-XX>/evals.json` 取一个用例的 `prompt`；
2. agent 可读本库（README / TRIAGE / 卡片 / 对应 skill），按 skill 的产出模板作答；
3. 回答**末尾必须有一行**机读结论：

   ```text
   verdict: FP-A06
   ```

   或 `verdict: OUT_OF_SCOPE`；
4. 把回答保存为 `<case-id>.md`（如 `FP-A06-P1.md`），放进同一个作答目录。

`verdict:` 行是判分钩子，不替代报告正文——正文仍按 skill 模板写（证据、定级、B 轴）。

## 判分

```bash
python3 scripts/run_eval.py --validate                    # 结构/覆盖校验（CI 用，不需要模型）
python3 scripts/run_eval.py --transcripts <作答目录>       # 判分 + 混淆矩阵（只判 verdict）
python3 scripts/run_eval.py --transcripts <dir> --strict   # 加判证据级判据（must/forbidden，v6.4）
python3 scripts/run_eval.py --transcripts <dir> --json --out result.json
python3 scripts/run_eval.py --self-test                   # 判分器自检（全对/错判/缺失/strict 三态）
```

输出指标：用例总数、已作答数、缺失数、通过数、准确率、分类型准确率、混淆对（期望→实际）、**证据不合格数**（verdict 对但 `must_include` 缺项或触发 `forbidden`）。`--strict` 下三类失败分行打印：`[FAIL]` 判错、`[EVID]` 判对但无据/踩禁词、`[MISS]` 无作答。

退出码：`0` 全对；`1` 有判错；`2` 参数/结构错误；`3` 有缺失且无判错。

## 维护

- 用例由 `scripts/gen_evals.py` 从索引 `symptoms` + `related` + `detectors` 生成（v2：neighbor 带相邻模式的工具证据与 `discriminator` 字段；v6.4：补 `must_include` / `forbidden` 证据级判据）；
- **改卡片 `symptoms` / `related` / `detectors` 后必须重跑生成器**：`python3 scripts/gen_evals.py`，守门 **C21** 会拦截「文件与生成结果不一致」；
- 人工精修用例时，改 `evals/<FP-XX>/evals.json` 后须同步改生成器，否则 `gen_evals.py --check` 会报漂移（当前以生成器为准，精修建议先改 `symptoms`）；
- **重复 prompt 的判定（v6.4 调整）**：`out-of-scope` 池已扩到 **18 个独立剧本**、按序轮转（任一剧本复用 ≤3 次，守门 **C36** 拦截超限）；v6.4 前只有 6 个剧本被复制 8~9 次，153 条用例的实际区分度仅约 108 条。`positive` 与 `neighbor-negative` 之间**不允许**重复，`run_eval --validate` 拦截；
- 评测结果不代表线上准确率：用例集小（153 条）、现象描述偏短，**它测的是路由与区分（加 `--strict` 时含证据纪律），不是完整判定质量**。
