#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
故障模式库健康检查（README 总览 + 单模式卡片 + 机器可读索引 + 分诊/评测/工作流 一致性守门）

适配 fault_patterns/ 拆分版目录结构。**C1~C50** 覆盖七类检查（版本号见
`fault_patterns_index.json` 的 `version`，不在本文重复，避免又一次漂移）：
结构一致性（文件存在性 / 编号集合与顺序 / 八要素 / 孤儿卡）、
机器读字段可用性（JSON schema / 正则可编译 / 词表合法性）、
交叉引用完整性（卡片 ↔ 索引 ↔ 总览表 三者互指 + 全局相对链接）、
skills 层与 B 轴一致性（**每个模式一份** SKILL.md 的 B 轴标准段逐字内嵌 + 索引 business_impact 词表，v3.4）、
消费层一致性（分诊表 / 评测集 / 签名卫生 / 能力边界，v3.6~v3.8）、
证据状态（未证实模式须显式标注，v4.1）。

  C1  文件存在性与 JSON 可解析（README / 主索引 / patterns 目录）
  C2  编号集合一致（README 总览表 / 卡片文件 / json patterns 三者）
  C3  编号唯一性（各自内部不得重复）
  C4  顺序一致（README 总览表顺序 == json 顺序 == 文件清单顺序）
  C5  编号连续性（同类别内序号无断层，WARN）
  C6  卡片要素完整性：5 项内容必备字段 + 元数据 / 实证案例（结构必备）+ v2.17「适用」头存在性（逐卡片文件）
  C7  json 条目 schema（id/name/category/risk/status/related/file/applicability/depth）
  C7b 卡片 / README 总览 / json 定级三方一致（S×O 档位 + 元数据行，v3.3）
  C8  signatures / absence_signatures / log_signatures 正则可编译；C30 broad_signatures ⊆ signatures
  C9  json 格式风格（patterns 每条一行紧凑风格）
  C10 版本与条目数一致性（README 头部 vs json；README 条目数 vs 实际卡数）
  C11 keywords 正则可编译（v2.15）
  C12 applicability 完整/词表合法/与卡片「适用」行双份一致（v2.17）
  C13 depth 取值合法（v2.17）
  C14 `必须触发` 上限 6 条（v2.17）
  C15 卡片体孤儿（逐文件探测）
  C16 signatures 含中文 ERROR（v3.3：审查要点归 keywords，signatures 须纯代码指纹）
  C17 README 总览表 风险/状态/负载/触发 与 json 双份一致（列名映射，不依赖列序）
  C18 拆分结构交叉引用：json file 字段存在、卡片「关联」编号均存在
  C18b 卡片「关联」编号集合与 json related 字段双向等值（无关联行 ⇔ related 为空集，v3.3）
  C19 skills 层 B 轴一致性（51 个 SKILL.md 须逐字内嵌 B 轴标准段 + 流程步「业务可达性核查」+ Bug 卡 B 轴字段 + 报告 B 轴说明 + 数量/覆盖表/注册名三方对应 + frontmatter description ≤200 字符；v3.4，v3.4 后修缮扩围）
  C19b 索引 business_impact 词表与 B 轴标准段一致（判据片段 / 影响类型 / 处置矩阵；v3.4 后修缮）
  C19c skills 层判定纪律（51 个 SKILL.md 须逐字内嵌 v3.6 判定纪律标准段 + Bug 卡「证据等级」「Agent 误判记录」字段 + 报告证据等级分布说明）
  C19d 误判台账 cases/misjudgments.jsonl（每行 JSON 合法、字段齐全、fp_id 在库内、type/status 在枚举、id 唯一且格式合法、evidence 无内部单号与本地路径；v3.6）
  C19e skill 适用声明头与卡片逐字一致（v4.0 后收口）
  C20 症状分诊表 TRIAGE.md（存在且带生成标记 / 51 条模式全覆盖 / 卡片与 skill 链接有效 / 单组候选 ≤6（超出须标 [WIDE]）/ 与 triage_map.json 生成结果一致；v3.7）
  C21 评测集 evals/（51/51 覆盖、每份 positive / neighbor-negative / out-of-scope 各 ≥1、id 全局唯一、expected_verdict 合法且与类型语义一致；v3.8）
  C22 行号校验器 scripts/verify_lines.py 在位且接口可用（v3.8）
  C23 签名扫描器 scripts/scan_fp.py 在位，签名卫生检查 0 ERROR（可编译 / 不匹配空串 / 跨模式不重复；判别性偏弱记 INFO，v3.8）
  C24 能力边界与自检（每份 SKILL.md 含「## 10. 能力边界与自检」+「找不到 ≠ 没有」+ 本模式 scan_fp 命令 + verify_lines 命令；v3.8）
  C25 任务级工作流 workflows/（README 路由表覆盖全部工作流 / 每个含 Stage 0 / 相对链接有效；v4.0）
  C26 工作量与抽样（每份 SKILL.md 含「### 工作量与抽样（v4.0）」且规则与索引 depth 一致；v4.0）
  C27 skill 评分卡 skills/SCORECARD.md（覆盖全部 skill、与 score_skills.py 重算一致；REWRITE 记 INFO；v4.2 起十维含 depth）
  C28 未证实模式标注（索引 evidence 为空的卡片须含「实证状态：未证实」；v4.1）
  C29 全局相对链接（全部 md 的相对链接可达 + 链接写法必须带「](」；忽略代码块内文本；v4.1，本轮补形态 2）
  C31 skill 摘要元数据与卡片/索引三方一致（类别 / 风险 S×O / 状态，防语义漂移；v5.1）
  C32 skill 案例回链校验（skill 引用的 `#NNN` 须能在模式卡语料中找到，防案例库铺开引入臆造 issue；v5.2）
  C33 案例库机读化 cases/cases.json（存在且可解析 / 字段齐全（case_id 唯一合法、fp_id 在库、触发+根因非空、同步模式案例含 paired_primitives、真锚 verified_anchors 结构合法）/ library_version == 索引 version / 深度档模式全覆盖 / 案例 issue 回链卡片语料（WARN）；v5.6）
  C34 applicability.trigger 正则可编译（v6.2：trigger 与 signatures 同为正则形态却此前不受门禁，
       FP-A05 的 `Init(` 括号未闭合即由此漏过；「必须触发」「无代码触发特征」为哨兵值，跳过）
  C35 subtypes 机读化（v6.3：list[dict]、id 形如 B07-6 且前缀=模式编号、全局唯一、name 非空、
       sig 可编译且不匹配空串；卡片出现 ≥3 处「子型/成因 ①②③」枚举时索引必须有 subtypes）
  C36 评测证据级判据与 OOS 去重（v6.4：每条用例 must_include/forbidden 均非空且正则可编译；
       out-of-scope 剧本去重 ≥12 且任一复用 ≤3 次）
  C37 结构化签名与 absence.subtype（v6.5：signatures 允许字符串或 {re,files,within,exclude} 对象，
       键白名单 + 各字段可编译；absence 规则的 subtype 必须已在本模式 subtypes 中定义）
  C38 签名产出基线（v6.6：cases/sig_yield-*.json 结构合法且 generated_by 正确；每条非宽泛签名都必须
       在基线中有记录——改签名不重跑 sig_yield.py 即报错；基线判 noisy 的模式必须有 yield_waiver）
  C39 文档引用的 scripts/*.py 必须在位（v6.16：所有 md 里出现的 `scripts/xxx.py` 逐个核在位性，
       防「卡片承诺了一个不存在的工具」——v6.15 曾把 scan_sync_scope.py 写进卡片却无该文件）
  C40 L2 判据层与 L3 失效模式（v6.17 / v6.18；v6.18.1 起 L3 改逐条 (id,fail,rule) 全等）：
       index 每条模式的 detect 字段齐备且与真源逐字段一致；L3 覆盖每个被 L2 使用的 oracle 类别，
       且 D20–D29 结构校验在守门内直接执行（不依赖 gen_detect.py 被单独调用）——
       只比 id 序列会让「改了 rule 文本」全绿通过，而 rule 才是 L3 的全部信息量
  C41 组合故障定义（v6.18.1：pattern_compositions.json 先前无任何门禁）：
       复用 scripts/query_patterns.load_compositions 作为唯一校验源（schema / id 唯一 /
       members ≥2 且均存在 / rationale 非空 / next_experiment 结构），主守门只调用不重写
  C42 深度档技能的 L2/L3 落地（v6.18.1）：指针段 + references/detect-l2-l3.md 与索引逐字一致
  C43 工作流「必须触发」清单与索引一致（v6.18.1）：核 Stage 1 表格（区块内行首匹配）
  C44 第二 oracle 覆盖与独立性（v6.19）：高优先级模式（risk=高 且 depth=深度）必须有第二判据；
       第二判据的失效面不得与主判据重复（同面 = 不提供独立信息，等于没加）
  C49 核心基线必带「控制变量」行（v6.30）：test-design 的 10 条核心基线（A05/A07/B01/B02/B04/B06/B07/
       B12/G01/G02）是每次设计必跑的检查表，而实测误判**几乎全部来自「多变量同时变」**：
       一次全填 NaN 得 47 例假「kernel 崩溃」、同时换芯片与 CANN 版本导致差异不可归因、
       只改 selfShape 不改 outShape 得 135 个假 161002。故要求这 10 张卡必须有「控制变量」行，
       且该行须同时含「允许变动」与「典型误判」两侧——只写「要控制变量」等于没说。
  C50 文档散文计数与真源一致（v6.31）：C47 只管 AGENTS.md 那一行**格式固定**的计数，
       而散文里的计数散落在句子中间、措辞各异，既无格式可锚也无生成器可重算。
       实测代价：为库做介绍 PPT 时引用 README 正文数字被自写脚本打脸——正文 20 处计数
       停在 v6.21~v6.26，而标题 / 生成块 / AGENTS 尾部 / 门禁全部已是 v6.30 准确值。
       **反向实测**：把「50/53 有可扫签名」改回「49/52」，C1~C49 与 ci_gate 双双仍全绿。
       本门禁覆盖 13 条可锚定语义的声明式短语（README / INVARIANTS / evals/README / AGENTS）
       + 3 条旧值黑名单（新旧双路：新值缺失报错、旧值残留也报错）。
       **能力边界**：不追求覆盖全部自然语言计数——只覆盖有固定措辞可锚的声明，
       其余仍在 CHANGELOG 里逐版人工登记。反向验证见 scripts/test_meta_gates.py。
  C48 根目录 md 必须至少有一个入链（v6.28）：根目录是「人/agent 第一眼看到的地方」，
       放进去的每个 md 都该被某处引用（README 目录树 / AGENTS 决策表 / CHANGELOG / 脚本）。
       实测两次孤儿的代价：`IMPROVEMENTS_20261106.md`（285 行副本）躺了 3 个小版本才被人工发现；
       紧接着并发会话又推进了 `EVIDENCE_DISCIPLINE.md`（127 行，入链 0）。
       两次都是「文件本身没问题，但没人知道它存在」——这种缺陷任何内容门禁都抓不到。
       白名单只放天然入口（README / CHANGELOG / LICENSE）。
  C47 AGENTS.md 尾部计数与真源一致（v6.28）：AGENTS.md 是给 agent 的一页速查，其末尾一行写死
       「版本 / 规模 / 签名数 / 子型数 / 深度档 / L2 / L3 / 组合 / 第二 oracle」共 9 类计数。
       此前该行**没有任何门禁**，于是从 v6.21 一路漂到落后 6 个版本（写 52 条 / 81 子型，
       实际 53 条 / 91 子型）而全库门禁全绿——「读者读到假数字」是最难被发现的一类缺陷。
       本门禁按真源逐项重算并逐字比对。
  C46 可检出性 D 维度一致性（v6.21）：D 字段齐备 / 取值合法 / 有 why /
       priority == S×O×D（防手改 priority 却不改 D，那会让排序失去可信度）
  C45 CI 网关与新增脚本在位（v6.19；v6.25 增 gen_readme_diagram.py；v6.28 增 gen_agents_tail.py / test_meta_gates.py）：scripts/ci_gate.py、
       check_anchors.py、check_secondary_oracle.py、mutate_ops.py、gen_readme_diagram.py 均须在位——
       防「写了工具但没接线」，v6.15 的 scan_sync_scope 就是这么丢的

用法
----
python3 check_fault_patterns.py [--root <fault_patterns 目录>] [--out <结果json>] [--quiet]
默认 --root 为脚本所在目录。

退出码
------
0 = 全部通过（可能含 WARN）
1 = 参数/环境错误（文件缺失、JSON 不可解析）
2 = 存在 ERROR（一致性被破坏，需人工修）
3 = 仅存在 WARN
"""

import argparse
import glob
import json
import os
import re
import sys

REQUIRED_FIELDS = ["故障机理", "触发条件", "典型表现", "源码审查映射点", "测试拦截建议"]
STRUCT_REQUIRED_FIELDS = ["元数据", "实证案例"]

VALID_CATEGORIES = {
    "accuracy", "compatibility", "performance", "resource", "test_effectiveness",
    "engineering",   # FP-F 工程/交付类（v2.5 起）
    "reliability",   # FP-G 执行可靠性类（v2.13 起）
}
VALID_STATUS = {"active", "retired", "deprecated"}

# ---- v2.17 <适用> 声明词表（与索引顶层 applicability_vocab 一致）----
VALID_REPOS = {"All", "ops-nn", "ops-math", "ops-cv", "ops-transformer", "op-plugin",
               "hccl", "canndev", "catlass", "cann-bench", "ops-collections", "ops-fft"}
VALID_SIDES = {"All", "Host", "Tiling", "Kernel"}
VALID_CARRIERS = {"Kernel源码", "Host源码", "Tiling源码", "aclnn源码", "IR与图配置",
                  "构建配置与日志", "文档与支持矩阵", "UT与golden资产"}
VALID_DEPTH = {"深度", "标准", "宽浅"}
MUST_TRIGGER_MAX = 6
APPL_KEYS = ("repos", "sides", "carriers", "trigger", "enabled")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")

APPL_LINE_RE = re.compile(
    r"^-\s*\*\*适用\*\*：仓\s*(.+?)\s*｜\s*侧别\s*(.+?)\s*｜\s*载体\s*(.+?)\s*"
    r"｜\s*触发\s*(.+?)\s*｜\s*默认启用\s*(\S+)\s*$", re.M)

# ---- C19 skills 层 B 轴标准段（权威措辞；与 skills/README 编写规范第 7 条一致）----
# 全库 51 个 SKILL.md 须逐字内嵌本段，不得改写；模式特有补充只能追加在本段之后。
SKILL_BAXIS_CANON = [
    "### B 轴：业务影响评估（与 S×O 正交；报告层新增，不改卡片定级）",
    "",
    'S×O 回答"多严重、多常见"，**不回答"真实业务能不能碰到"**。B 轴补这一问，只决定**修复优先级建议**，**不参与 S/O 取值、不改 S×O 档位与卡片元数据**。',
    "",
    "**业务可达性（B）**——触发条件在真实负载中的可达程度：",
    "",
    "| 等级 | 判据 | 证据要求 |",
    "|---|---|---|",
    "| B3 现实可达 | 主流框架/公开模型默认路径即可命中（如 PTA/torch_npu、vLLM、MindIE 常规调用） | 调用方或公开负载来源 |",
    "| B2 条件可达 | 需特定 attr/dtype/shape 组合，业务中存在但非默认 | 该组合的业务来源 |",
    '| B1 边界/不可达 | 需极端、超规格或非法参数（超出接口合理上限的 shape、退化/非法输入） | "为何不可达"的说明 |',
    "",
    '- **默认保守**：无法证明不可达 → 记 **B3**；降为 B1/B2 必须附证据，**不得仅凭"业务应该不会这么用"**。',
    "- 超规格参数是否算 B1 取决于**接口契约**：契约允许但业务不用 → B1；契约不允许（本应报错）→ 属校验缺失（FP-B04/B05 类），另行归属。",
    "",
    "**业务影响类型**（命中后对用户可见结果的后果，用业务语言表述）：静默精度损失（模型效果下降 / loss 不收敛 / 偶发 NaN）｜ 任务失败中断（报错 / 崩溃 / 挂死）｜ 性能退化 ｜ 仅可观测性（日志 / 错误码 / 文档，不影响结果）。",
    "",
    "**处置建议**（由两轴推导的报告结论，非新档位）：",
    "",
    "| S×O \\ B | B3 现实可达 | B2 条件可达 | B1 边界/不可达 |",
    "|---|---|---|---|",
    "| 高（≥6） | 尽快修 | 尽快修 | 排期修 |",
    "| 中（3/4） | 尽快修 | 排期修 | 记录（业务难以触达） |",
    "| 低（1/2） | 排期修 | 记录 | 记录 |",
]

# ---- C19c skills 层判定纪律标准段（v3.5；权威措辞，与 skills/README 编写规范第 8 条一致）----
# 全库 51 个 SKILL.md 须逐字内嵌本段，不得改写；模式特有补充只能追加在本段之后。
SKILL_JUDGMENT_CANON = [
    "### 判定纪律补充（v3.6）：非对称增减、证据等级与误判记录",
    "",
    "**增减不对称**：允许追加候选（有据即可，错了可由用户排除）；**撤销或否决候选必须附 `[文件]:[行号] [代码行]` 负向证据**。无证据的「看起来没问题」一律记为「未核查」，不得计入反证排除，也不得据此下调等级——否决造成的漏报用户不可见、不可恢复。",
    "",
    "- **证据等级**（Bug 卡必填）：`静态可证` = 推导链完整且触发输入可静态构造；`需实测确认` = 依赖运行时输入规模、设备行为或环境差异。标 `需实测确认` 的条目**不得以「命中」名义出卡**，按观察项记录并附实测用例。",
    "- **Agent 误判记录**（Bug 卡必填）：本次被推翻的假设、推翻它的证据（`[文件]:[行号] [代码行]` 或实测输出）、判定标准是否随之修订；无推翻写「无」。",
    "- **误判回流**：同类误判在 3 次检视中重复出现，登记至 `cases/misjudgments.jsonl`（字段见 `cases/README.md`），并在本模式判定标准中新增对应防线；守门 C19d 校验台账字段合法。",
]

# Bug 卡字段与报告说明的机检片段（C19c）
JUDGMENT_REQUIRED = [
    "**增减不对称**",
    "- **证据等级**：",
    "- **Agent 误判记录**：",
    "证据等级分布（静态可证 X / 需实测确认 Y）",
]

# ---- C19d 误判台账 schema ----
MISJ_KEYS = ("id", "date", "fp_id", "type", "claim", "evidence", "correction", "status", "source")
MISJ_TYPES = {"实证重复计数", "机理误归", "证据不足即命中", "相邻模式误判", "三方漂移", "行号失真", "其他"}
MISJ_STATUS = {"已关闭", "观察中", "已升级为防线"}
MISJ_ID_RE = re.compile(r"^MJ-\d{8}-\d{2}$")
MISJ_INTERNAL_RE = re.compile(r"BUG-\d{8}|[A-Za-z]:\\\\|[A-Za-z]:\\")

# ---- C19b 索引 business_impact 词表期望值（与 SKILL_BAXIS_CANON 判据/类型/矩阵逐项对齐）----
BAXIS_IMPACT_TYPES = [
    "静默精度损失（模型效果下降 / loss 不收敛 / 偶发 NaN）",
    "任务失败中断（报错 / 崩溃 / 挂死）",
    "性能退化",
    "仅可观测性（日志 / 错误码 / 文档，不影响结果）",
]
BAXIS_DISPOSITION = {
    "高（≥6）": ["尽快修", "尽快修", "排期修"],
    "中（3/4）": ["尽快修", "排期修", "记录（业务难以触达）"],
    "低（1/2）": ["排期修", "记录", "记录"],
}


def read_text(p):
    with open(p, encoding="utf-8-sig") as f:
        return f.read()


def parse_readme(rd_text):
    """README → (表头列名, 总览表 [(id, 行)], 头部版本, 头部条目数)。"""
    header = None
    m = re.search(r"^\|\s*编号\s*\|(.+)$", rd_text, re.M)
    if m:
        header = [c.strip() for c in ("编号|" + m.group(1)).split("|")]
    rows = []
    for mm in re.finditer(r"^\|\s*\[?(FP-[A-G]\d{2})\]?\s*[^|]*\|(.*)$", rd_text, re.M):
        rows.append((mm.group(1), mm.group(0)))
    ver = None
    m = re.search(r"\*\*版本\*\*：v([0-9]+\.[0-9]+)", rd_text)
    if m:
        ver = m.group(1)
    cnt = None
    m = re.search(r"\*\*条目数\*\*：(\d+)", rd_text)
    if m:
        cnt = int(m.group(1))
    return header, rows, ver, cnt


def parse_appl_line(body):
    m = APPL_LINE_RE.search(body)
    if not m:
        return None
    return {
        "repos": [x.strip() for x in m.group(1).split(",")],
        "sides": [x.strip() for x in m.group(2).split(",")],
        "carriers": [x.strip() for x in m.group(3).split(",")],
        "trigger": m.group(4).strip(),
        "enabled": m.group(5).strip().lower() == "true",
    }


def check_gaps(ids):
    gaps = []
    by_cat = {}
    for i in ids:
        by_cat.setdefault(i[3], []).append(int(i[4:]))
    for cat, nums in by_cat.items():
        nums = sorted(nums)
        for a, b in zip(nums, nums[1:]):
            if b - a > 1:
                for miss in range(a + 1, b):
                    gaps.append("FP-%s%02d" % (cat, miss))
    return gaps


def check_json_style(path):
    text = read_text(path)
    m = re.search(r'"patterns"\s*:\s*\[', text)
    if not m:
        return 0, 0, "not_found"
    start = m.end() - 1
    depth, end, in_str, esc = 0, None, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        return 0, 0, "unbalanced"
    body = text[start:end + 1]
    total, dep, in_str, esc = 0, 0, False, False
    for ch in body[1:]:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[" or ch == "{":
            if ch == "{" and dep == 0:
                total += 1
            dep += 1
        elif ch == "]" or ch == "}":
            dep -= 1
    solo = 0
    for ln in body.splitlines():
        s = ln.strip().rstrip(",")
        if s.startswith('{"id"') and s.endswith("}"):
            solo += 1
    ratio = (1 - solo / total) if total else 0.0
    return total, ratio, "ok"


def main():
    ap = argparse.ArgumentParser(description="故障模式库健康检查（拆分版）")
    ap.add_argument("--root", default=os.path.dirname(os.path.abspath(__file__)),
                    help="fault_patterns 目录（默认脚本所在目录）")
    ap.add_argument("--out", default="", help="结果 JSON 输出路径")
    ap.add_argument("--quiet", action="store_true", help="仅打印结论行")
    args = ap.parse_args()
    root = os.path.abspath(args.root)

    errors, warns, infos = [], [], []

    # ---- C1 存在性 ----
    readme_path = os.path.join(root, "README.md")
    js_path = os.path.join(root, "fault_patterns_index.json")
    pat_dir = os.path.join(root, "patterns")
    for p, label in ((readme_path, "README.md"), (js_path, "fault_patterns_index.json"), (pat_dir, "patterns/")):
        if not os.path.exists(p):
            print("[ERROR] 缺少 %s" % p)
            return 1
    try:
        js = json.loads(read_text(js_path))
    except json.JSONDecodeError as e:
        print("[ERROR] JSON 不可解析：%s" % e)
        return 1

    rd_text = read_text(readme_path)
    rd_header, ov_rows, rd_ver, rd_cnt = parse_readme(rd_text)

    cards = []  # [(id, path, body)]
    for dp, _, fs in os.walk(pat_dir):
        for f in sorted(fs):
            if f.endswith(".md"):
                p = os.path.join(dp, f)
                t = read_text(p)
                m = re.match(r"^#\s+(FP-[A-G]\d{2})\s+(.+?)\s*$", t, re.M)
                if m:
                    cards.append((m.group(1), p, t))
                else:
                    errors.append("C1 卡片文件缺少一级标题：%s" % os.path.relpath(p, root))
    cards.sort(key=lambda x: (x[0][3], x[0][4:]))
    file_order = [c[0] for c in cards]
    file_set = set(file_order)

    js_order = [p.get("id", "?") for p in js.get("patterns", [])]
    ov_order = [r[0] for r in ov_rows]

    # ---- C2 集合一致 ----
    s_file, s_js, s_ov = file_set, set(js_order), set(ov_order)
    if s_js - s_file:
        errors.append("C2 仅存在于 json 的条目：%s" % ", ".join(sorted(s_js - s_file)))
    if s_file - s_js:
        errors.append("C2 仅存在卡片文件的条目：%s" % ", ".join(sorted(s_file - s_js)))
    if s_ov != s_file:
        errors.append("C2 总览表与卡片集合不一致：表独有=%s 卡独有=%s"
                      % (sorted(s_ov - s_file), sorted(s_file - s_ov)))

    # ---- C3 唯一性 ----
    for name, seq in (("卡片文件", file_order), ("总览表", ov_order), ("json", js_order)):
        dup = sorted({x for x in seq if seq.count(x) > 1})
        if dup:
            errors.append("C3 %s 内编号重复：%s" % (name, ", ".join(dup)))

    # ---- C4 顺序一致 ----
    if file_order != js_order:
        diff_at = "未知"
        for i, (a, b) in enumerate(zip(file_order, js_order)):
            if a != b:
                diff_at = "第%d位 文件=%s json=%s" % (i, a, b)
                break
        errors.append("C4 卡片文件与 json 顺序不一致（首个差异：%s）" % diff_at)
    if ov_order != js_order:
        errors.append("C4 总览表与 json 顺序不一致")

    # ---- C5 连续性 ----
    gaps = check_gaps(file_order)
    if gaps:
        warns.append("C5 编号不连续，可能漏号：%s" % ", ".join(gaps))

    # ---- C6 要素完整性（内容必备 + 结构必备）+ 适用头 ----
    md_appl = {}
    for cid, p, body in cards:
        missing = [k for k in REQUIRED_FIELDS if ("**%s**" % k) not in body]
        if missing:
            errors.append("C6 %s 缺字段：%s" % (cid, ", ".join(missing)))
        missing_struct = [k for k in STRUCT_REQUIRED_FIELDS
                          if not re.search(r"^-\s*\*\*%s\*\*：" % k, body, re.M)]
        if missing_struct:
            errors.append("C6 %s 缺结构性必备字段：%s（单行 `- **字段**：` 形式）"
                          % (cid, ", ".join("`- **%s**：`" % k for k in missing_struct)))
        if len(re.findall(r"^#\s+FP-[A-G]\d{2}\s", body, re.M)) > 1:
            errors.append("C6 %s 卡片文件存在多个一级标题" % cid)
        n_meta = len(re.findall(r"^- \*\*元数据\*\*", body, re.M))
        if n_meta > 1:
            errors.append("C15 卡片体孤儿：%s 正文存在 %d 处 `- **元数据**`（应为 1）" % (cid, n_meta))
        ap = parse_appl_line(body)
        if ap is None:
            errors.append("C6 %s 卡片缺 `- **适用**：` 行（v2.17 起必备）" % cid)
        else:
            md_appl[cid] = ap

    # ---- C7 json schema ----
    for p in js.get("patterns", []):
        cid = p.get("id", "?")
        for k in ("id", "name", "category", "risk", "status", "related", "file",
                  "applicability", "depth"):
            if k not in p:
                errors.append("C7 %s 缺字段 %s" % (cid, k))
        if p.get("category") and p["category"] not in VALID_CATEGORIES:
            warns.append("C7 %s category 取值异常：%s" % (cid, p["category"]))
        if p.get("status") and p["status"] not in VALID_STATUS:
            warns.append("C7 %s status 取值异常：%s" % (cid, p["status"]))
        risk = p.get("risk") or {}
        if isinstance(risk, dict):
            if "level" not in risk:
                errors.append("C7 %s risk 缺 level" % cid)
            else:
                s, o = risk.get("s"), risk.get("o")
                if isinstance(s, int) and isinstance(o, int):
                    prod = s * o
                    want = "高" if prod >= 6 else ("中" if prod >= 3 else "低")
                    RANK = {"低": 1, "中": 2, "高": 3}
                    if risk["level"] not in RANK:
                        warns.append("C7 %s 风险等级取值异常：%s" % (cid, risk["level"]))
                    elif RANK[risk["level"]] != RANK[want]:
                        errors.append("C7 %s 风险等级偏离 S*O 公式（高>=6 / 中3,4 / 低1,2）：S%d*O%d=%d 应=%s 实=%s；"
                                      "确需调档请改 S/O 取值并在卡片括注理由、CHANGELOG 登记"
                                     % (cid, s, o, prod, want, risk["level"]))

    # ---- C7b 卡片 / 总览 / json 定级三方一致 ----
    card_risk = {}
    for cid, _p, body in cards:
        m = re.search(r"^- \*\*元数据\*\*：.*?风险\s*([高中低])（S([1-4])×O([1-3])", body, re.M)
        if m:
            card_risk[cid] = (m.group(1), int(m.group(2)), int(m.group(3)))
    ov_risk = {}
    for oid, row in ov_rows:
        cells = [c.strip() for c in row.split("|")]
        if len(cells) > 4:
            ov_risk[oid] = cells[4]
    for p in js.get("patterns", []):
        cid = p.get("id", "?")
        risk = p.get("risk") or {}
        lvl, s, o = risk.get("level"), risk.get("s"), risk.get("o")
        cm = card_risk.get(cid)
        if cm is None:
            warns.append("C7 %s 卡片元数据行无法解析定级（期望「风险 X（S#×O#=#」格式）" % cid)
        elif cm != (lvl, s, o):
            errors.append("C7 %s 卡片与 json 定级不一致：卡=%s(S%d×O%d) json=%s(S%s×O%s)"
                          % (cid, cm[0], cm[1], cm[2], lvl, s, o))
        if cid in ov_risk and lvl and ov_risk[cid] != lvl:
            errors.append("C7 %s README 总览风险列(%s)与 json level(%s)不一致"
                          % (cid, ov_risk[cid], lvl))

    # ---- C8 正则可编译（signatures / absence must+files / log_signatures，v4.6） ----
    for p in js.get("patterns", []):
        for sig in (p.get("signatures", []) or []):
            rx_text = sig if isinstance(sig, str) else (sig or {}).get("re")
            if not isinstance(rx_text, str):
                continue          # 结构问题由 C37 报，C8 只查可编译性
            try:
                re.compile(rx_text)
            except re.error as e:
                errors.append("C8 %s signatures 正则不可编译：%r (%s)"
                              % (p.get("id"), rx_text[:40], e))
        for r in p.get("absence_signatures", []) or []:
            for k in ("must", "files", "when", "func", "branch", "exclude_sig"):
                if k in ("when", "func", "branch", "exclude_sig") and not r.get(k):
                    continue
                try:
                    re.compile(r.get(k, ""))
                except re.error as e:
                    errors.append("C8 %s absence.%s 正则不可编译：%r (%s)"
                                  % (p.get("id"), k, str(r.get(k))[:40], e))
        for sig in p.get("log_signatures", []) or []:
            try:
                re.compile(sig)
            except re.error as e:
                errors.append("C8 %s log_signatures 正则不可编译：%r (%s)"
                              % (p.get("id"), sig[:40], e))
        broad = p.get("broad_signatures") or []
        _sig_re_set = {x if isinstance(x, str) else (x or {}).get("re")
                       for x in (p.get("signatures") or [])}
        for sig in broad:
            if sig not in _sig_re_set:
                errors.append("C30 %s broad_signatures 不在 signatures 中（叠加标记必须指向已有签名）：%r"
                              % (p.get("id"), sig[:40]))
            try:
                re.compile(sig)
            except re.error as e:
                errors.append("C30 %s broad_signatures 正则不可编译：%r (%s)"
                              % (p.get("id"), sig[:40], e))

    # ---- C34 applicability.trigger 正则可编译（v6.2） ----
    # trigger 在卡片与索引双份存在、且被当作「触发指纹」对外展示；它是正则形态，
    # 但 v6.2 前不受任何门禁约束——FP-A05 的 `Init(`（括号未闭合）就这样带病存活。
    for p in js.get("patterns", []):
        ap = p.get("applicability") or {}
        trig = ap.get("trigger")
        if not isinstance(trig, str) or not trig.strip():
            continue
        if trig in ("必须触发", "无代码触发特征"):
            continue
        try:
            re.compile(trig)
        except re.error as e:
            errors.append("C34 %s applicability.trigger 正则不可编译：%r (%s)"
                          % (p.get("id"), trig[:40], e))

    # ---- C35 subtypes 机读化（v6.3） ----
    # 结构：list[dict]，id 形如 B07-6（前缀 = 模式编号去掉 FP-）、全局唯一；name 非空；
    # 可选 evidence / sig（sig 为正则数组，须可编译且不匹配空串）。
    # 一致性：卡片里出现 ≥3 处「子型/成因 ①②③」枚举时，索引必须有 subtypes——
    # 防「卡片讲了五个形态、机器只能看见一个」。
    _sub_ids = {}
    _by_id_c35 = {p.get("id"): p for p in js.get("patterns", [])}
    for cid, _meta, body in cards:
        jsp = _by_id_c35.get(cid) or {}
        subs = jsp.get("subtypes")
        if subs is None:
            n_enum = len(re.findall(r"(?:子型|成因)\s*[①②③④⑤⑥⑦⑧⑨]", body))
            if n_enum >= 3:
                errors.append("C35 %s 卡片枚举了 %d 处子型/成因，但索引没有 subtypes（机读化缺失）"
                              % (cid, n_enum))
            continue
        if not isinstance(subs, list) or not subs:
            errors.append("C35 %s subtypes 须为非空数组" % cid)
            continue
        pref = cid[3:]                                  # FP-B07 -> B07
        for st in subs:
            if not isinstance(st, dict):
                errors.append("C35 %s subtypes 条目须为对象（id/name/…），实为 %r"
                              % (cid, type(st).__name__))
                continue
            sid = st.get("id") or ""
            if not re.match(r"^%s-\d+$" % re.escape(pref), sid):
                errors.append("C35 %s 子型 id 不合规（应 %s-<序号>）：%r" % (cid, pref, sid))
            if sid in _sub_ids:
                errors.append("C35 子型 id 重复：%s（%s 与 %s）" % (sid, _sub_ids[sid], cid))
            _sub_ids[sid] = cid
            name = st.get("name") or ""
            if not isinstance(name, str) or not name.strip():
                errors.append("C35 %s/%s name 为空" % (cid, sid))
            for s in (st.get("sig") or []):
                try:
                    rx = re.compile(s)
                except re.error as e:
                    errors.append("C35 %s/%s sig 正则不可编译：%r (%s)" % (cid, sid, s[:40], e))
                    continue
                if rx.search(""):
                    errors.append("C35 %s/%s sig 匹配空串（必然全命中）：%r" % (cid, sid, s[:40]))
            pr = st.get("pair")                    # v6.7：结构型配对判据
            if pr is not None:
                if not isinstance(pr, dict):
                    errors.append("C35 %s/%s pair 须为对象" % (cid, sid))
                else:
                    extra = set(pr) - {"a", "b", "scope", "max_diff", "strict", "id_re"}
                    if extra:
                        errors.append("C35 %s/%s pair 含未知键 %s"
                                      % (cid, sid, ",".join(sorted(extra))))
                    for k in ("a", "b"):
                        v = pr.get(k)
                        if not isinstance(v, str) or not v.strip():
                            errors.append("C35 %s/%s pair.%s 须为非空正则" % (cid, sid, k))
                            continue
                        try:
                            re.compile(v)
                        except re.error as e:
                            errors.append("C35 %s/%s pair.%s 不可编译：%r (%s)"
                                          % (cid, sid, k, v[:40], e))
                    if pr.get("scope") not in (None, "file", "func"):
                        errors.append("C35 %s/%s pair.scope 仅支持 file / func：%r"
                                      % (cid, sid, pr.get("scope")))
                    if pr.get("scope") == "func":
                        errors.append("C35 %s/%s pair.scope=func 尚未实现（scan_fp 只支持文件级），"
                                      "请改 file 或先在扫描器实现函数级计数" % (cid, sid))
                    md = pr.get("max_diff")
                    if md is not None and (not isinstance(md, int) or md < 0):
                        errors.append("C35 %s/%s pair.max_diff 须为 >=0 的整数：%r" % (cid, sid, md))
                    # v6.9：strict = 顺序判据（同一 id 连续两次 A 之间必须有 B）
                    if "strict" in pr and not isinstance(pr["strict"], bool):
                        errors.append("C35 %s/%s pair.strict 须为布尔" % (cid, sid))
                    idre = pr.get("id_re")
                    if pr.get("strict"):
                        if not isinstance(idre, str) or not idre.strip():
                            errors.append("C35 %s/%s pair.strict=true 时必须给 id_re（捕获组 1 = event id）"
                                          % (cid, sid))
                        else:
                            try:
                                rx_id = re.compile(idre)
                                if rx_id.groups < 1:
                                    errors.append("C35 %s/%s pair.id_re 至少要有 1 个捕获组" % (cid, sid))
                            except re.error as e:
                                errors.append("C35 %s/%s pair.id_re 不可编译：%r (%s)"
                                              % (cid, sid, idre[:40], e))
                    elif idre:
                        errors.append("C35 %s/%s pair.id_re 只在 strict=true 时有意义（已给但未开 strict）"
                                      % (cid, sid))
    if _sub_ids:
        n_have = len([p for p in js.get("patterns", []) if p.get("subtypes")])
        n_sig = sum(1 for p in js.get("patterns", []) for st in (p.get("subtypes") or [])
                    if isinstance(st, dict) and st.get("sig"))
        n_pair = sum(1 for p in js.get("patterns", []) for st in (p.get("subtypes") or [])
                     if isinstance(st, dict) and st.get("pair"))
        infos.append("子型机读化：%d 个模式 / %d 条子型 / 带存在型指纹 %d / 配对结构判据 %d"
                     % (n_have, len(_sub_ids), n_sig, n_pair))

    # ---- C37 结构化签名与 absence.subtype（v6.5） ----
    # signatures 允许两种形态：字符串（纯正则）或对象 {re, files?, within?, exclude?}。
    # 对象形态让「存在型」签名也能带上下文约束（文件角色 / 所在函数 / 排除行），
    # 与 absence 同级；键白名单外的字段一律拦下，避免拼错后静默失效。
    _SIG_KEYS = {"re", "files", "within", "exclude"}
    _n_struct = 0
    for p in js.get("patterns", []):
        for s in (p.get("signatures") or []):
            if isinstance(s, str):
                continue
            if not isinstance(s, dict):
                errors.append("C37 %s signatures 条目须为字符串或对象：%r"
                              % (p.get("id"), type(s).__name__))
                continue
            extra = set(s) - _SIG_KEYS
            if extra:
                errors.append("C37 %s 结构化签名含未知键 %s（允许：%s）"
                              % (p.get("id"), ",".join(sorted(extra)), "/".join(sorted(_SIG_KEYS))))
            if not isinstance(s.get("re"), str) or not s["re"].strip():
                errors.append("C37 %s 结构化签名缺 re" % p.get("id"))
                continue
            if any(k in s for k in ("files", "within", "exclude")):
                _n_struct += 1
            for k in ("re", "files", "within", "exclude"):
                if k not in s:
                    continue
                if not isinstance(s[k], str) or not s[k].strip():
                    errors.append("C37 %s 结构化签名 %s 须为非空字符串" % (p.get("id"), k))
                    continue
                try:
                    re.compile(s[k])
                except re.error as e:
                    errors.append("C37 %s 结构化签名 %s 正则不可编译：%r (%s)"
                                  % (p.get("id"), k, s[k][:40], e))
        _sub_ids_p = {st.get("id") for st in (p.get("subtypes") or []) if isinstance(st, dict)}
        for r in (p.get("absence_signatures") or []):
            if not isinstance(r, dict):
                continue
            st = r.get("subtype")
            if st and st not in _sub_ids_p:
                errors.append("C37 %s absence 规则挂了不存在的子型 %r（应先在本模式 subtypes 中定义）"
                              % (p.get("id"), st))
    if _n_struct:
        infos.append("结构化签名（带 files/within/exclude 约束）：%d 条" % _n_struct)

    # ---- C38 签名产出基线（v6.6） ----
    # 只有「命中数」没有分母时，一条匹配一切的签名看起来跟一条精准签名一样"有用"。
    # 基线把每条签名的 hits / files_hit / density 固定下来，并强制两件事：
    #   ① 索引里每条非宽泛签名都要能在基线里找到记录（改签名不重跑审计 → ERROR）；
    #   ② 基线里判为 noisy 的模式必须有 yield_waiver（显式豁免并写理由），不许沉默。
    _yield_json = os.path.join(root, "cases", "sig_yield-ops-math.json")
    _yield_md = os.path.join(root, "cases", "sig_yield-ops-math.md")
    if os.path.isfile(_yield_json):
        try:
            _y = json.loads(read_text(_yield_json))
        except ValueError as e:
            errors.append("C38 产出基线不可解析：%s" % e)
            _y = None
        if _y is not None:
            if _y.get("generated_by") != "scripts/sig_yield.py":
                errors.append("C38 产出基线 generated_by 不是 scripts/sig_yield.py（可能被手改）")
            _base_sigs = {(e.get("pattern"), e.get("signature")) for e in (_y.get("entries") or [])}
            _base_pats = {e.get("pattern"): e for e in (_y.get("patterns") or [])}
            _missing_base = []
            for p in js.get("patterns", []):
                pid = p.get("id")
                for sd in (p.get("signatures") or []):
                    rx = sd if isinstance(sd, str) else (sd or {}).get("re")
                    if not rx:
                        continue
                    if (pid, rx) not in _base_sigs:
                        _missing_base.append("%s `%s`" % (pid, rx[:40]))
            if _missing_base:
                errors.append("C38 有 %d 条签名未纳入产出基线（改签名后未重跑 scripts/sig_yield.py）：%s"
                              % (len(_missing_base), "；".join(_missing_base[:3])))
            # 反向：基线里还留着、索引里已经没有的签名——正则被改写或退役后没重跑审计，
            # 基线就多出「幽灵条目」：它不让任何检查变红，却让签名总数（119 vs 118）对不上索引。
            _idx_sigs = set()
            for p in js.get("patterns", []):
                for sd in (p.get("signatures") or []):
                    _rx = sd if isinstance(sd, str) else (sd or {}).get("re")
                    if _rx:
                        _idx_sigs.add((p.get("id"), _rx))
            _ghost_base = sorted("%s `%s`" % (pid, sig[:40])
                                 for pid, sig in _base_sigs if (pid, sig) not in _idx_sigs)
            if _ghost_base:
                errors.append("C38 基线里有 %d 条签名已不在索引（正则改写/退役后未重跑 "
                              "scripts/sig_yield.py）：%s"
                              % (len(_ghost_base), "；".join(_ghost_base[:3])))
            _bad_waive = []
            for pid, e in _base_pats.items():
                if e.get("verdict") == "noisy":     # watch（200~500）只观察，noisy（>500）必须交代
                    p = next((x for x in js.get("patterns", []) if x.get("id") == pid), {}) or {}
                    w = p.get("yield_waiver") or ""
                    if len(w.strip()) < 8:
                        _bad_waive.append(pid)
            if _bad_waive:
                errors.append("C38 以下模式候选量偏大却未显式豁免（加 yield_waiver 写理由，或加约束降量）：%s"
                              % "、".join(sorted(_bad_waive)))
            # v6.8：子型判据（存在型指纹 / 配对）同样必须纳入基线；被判 noisy 的子型须降量或删除
            _base_sub = {(e.get("pattern"), e.get("subtype"), e.get("kind"))
                         for e in (_y.get("subtypes") or [])}
            _miss_sub, _noisy_sub = [], []
            for p in js.get("patterns", []):
                for st in (p.get("subtypes") or []):
                    if not isinstance(st, dict):
                        continue
                    if st.get("sig"):
                        if (p.get("id"), st.get("id"), "sig") not in _base_sub:
                            _miss_sub.append("%s/%s(sig)" % (p.get("id"), st.get("id")))
                    if st.get("pair") and (p.get("id"), st.get("id"), "pair") not in _base_sub:
                        _miss_sub.append("%s/%s(pair)" % (p.get("id"), st.get("id")))
            for e in (_y.get("subtypes") or []):
                if e.get("verdict") == "noisy":
                    _noisy_sub.append("%s/%s" % (e.get("pattern"), e.get("subtype")))
            if _miss_sub:
                errors.append("C38 有 %d 条子型判据未纳入产出基线（改子型后未重跑 sig_yield.py）：%s"
                              % (len(_miss_sub), "、".join(_miss_sub[:3])))
            if _noisy_sub:
                errors.append("C38 以下子型判据产出过大（>500 条），须收紧约束或删除定位型指纹：%s"
                              % "、".join(sorted(set(_noisy_sub))))
            if os.path.isfile(_yield_md):
                if "勿手改" not in read_text(_yield_md):
                    errors.append("C38 基线 Markdown 缺「勿手改」生成标记")
            _n_pat = len([e for e in (_y.get("patterns") or [])])
            _n_noisy = len([e for e in (_y.get("patterns") or []) if e.get("verdict") == "noisy"])
            infos.append("签名产出基线：%d 条签名 / %d 条子型判据 / %d 个模式（noisy %d，被扫 %s 文件）"
                         % (len(_base_sigs), len(_y.get("subtypes") or []), _n_pat,
                            _n_noisy, _y.get("scanned_files")))

    # ---- C9 格式风格 ----
    total, ratio, why = check_json_style(js_path)
    if why != "ok":
        warns.append("C9 无法解析 patterns 区块（%s），跳过格式风格检查" % why)
    elif total and ratio > 0.5:
        warns.append("C9 json 格式风格漂移：%.0f%% 的 patterns 条目非『每条一行』，共 %d 条"
                     % (ratio * 100, total))

    # ---- C10 版本与条目数 ----
    if rd_ver and js.get("version") and rd_ver != str(js["version"]):
        errors.append("C10 版本不一致：README=v%s json=%s" % (rd_ver, js["version"]))
    if rd_cnt is not None and rd_cnt != len(file_order):
        errors.append("C10 README 头部声明条目数=%d，实际卡片=%d" % (rd_cnt, len(file_order)))
    if rd_cnt is not None and js.get("patterns") and rd_cnt != len(js["patterns"]):
        errors.append("C10 README 头部声明条目数=%d，json 条目=%d" % (rd_cnt, len(js["patterns"])))

    # ---- C11 keywords 正则可编译 ----
    for p in js.get("patterns", []):
        for kw in p.get("keywords", []) or []:
            try:
                re.compile(kw)
            except re.error as e:
                errors.append("C11 %s keywords 正则不可编译：%r (%s)"
                              % (p.get("id"), kw[:40], e))

    # ---- C12 applicability ----
    must_ids = []
    for p in js.get("patterns", []):
        cid = p.get("id", "?")
        ap = p.get("applicability")
        if not isinstance(ap, dict):
            errors.append("C12 %s 缺 applicability 对象" % cid)
            continue
        for k in APPL_KEYS:
            if k not in ap:
                errors.append("C12 %s applicability 缺键 %s" % (cid, k))
        for k, vocab in (("repos", VALID_REPOS), ("sides", VALID_SIDES),
                         ("carriers", VALID_CARRIERS)):
            vals = ap.get(k)
            if not isinstance(vals, list) or not vals:
                errors.append("C12 %s applicability.%s 必须为非空数组" % (cid, k))
                continue
            bad = [v for v in vals if v not in vocab]
            if bad:
                errors.append("C12 %s applicability.%s 取值越界：%s"
                              % (cid, k, ", ".join(map(str, bad))))
        trig = ap.get("trigger")
        if not trig or not isinstance(trig, str):
            errors.append("C12 %s applicability.trigger 缺失或非字符串" % cid)
        elif trig == "必须触发":
            must_ids.append(cid)
        if not isinstance(ap.get("enabled"), bool):
            errors.append("C12 %s applicability.enabled 必须为布尔" % cid)

        mdap = md_appl.get(cid)
        if mdap is None:
            if cid in file_set:
                errors.append("C12 %s md 卡片缺 `- **适用**：` 行" % cid)
            continue
        for k in ("repos", "sides", "carriers"):
            a, b = sorted(ap.get(k) or []), sorted(mdap.get(k) or [])
            if a != b:
                errors.append("C12 %s %s 双份不一致：json=%s 卡片=%s" % (cid, k, a, b))
        if (ap.get("trigger") or "") != mdap.get("trigger"):
            errors.append("C12 %s trigger 双份不一致：json=%r 卡片=%r"
                          % (cid, ap.get("trigger"), mdap.get("trigger")))
        if bool(ap.get("enabled")) != bool(mdap.get("enabled")):
            errors.append("C12 %s enabled 双份不一致：json=%s 卡片=%s"
                          % (cid, ap.get("enabled"), mdap.get("enabled")))

    # ---- C13 depth ----
    for p in js.get("patterns", []):
        if p.get("depth") not in VALID_DEPTH:
            errors.append("C13 %s depth 取值非法：%r（合法：%s）"
                          % (p.get("id"), p.get("depth"), ", ".join(sorted(VALID_DEPTH))))

    # ---- C14 必须触发 上限 ----
    if len(must_ids) > MUST_TRIGGER_MAX:
        errors.append("C14 `必须触发` %d 条 > 上限 %d（%s）" % (len(must_ids), MUST_TRIGGER_MAX, ", ".join(must_ids)))
    infos.append("必须触发 %d 条（上限 %d）：%s"
                 % (len(must_ids), MUST_TRIGGER_MAX, ", ".join(must_ids) or "（无）"))

    # ---- C16 signatures 含中文（ERROR，v3.3：审查要点归 keywords） ----
    cjk_items = [(p.get("id"), (s if isinstance(s, str) else (s or {}).get("re", "")))
                 for p in js.get("patterns", [])
                 for s in (p.get("signatures") or [])
                 if CJK_RE.search(s if isinstance(s, str) else (s or {}).get("re", "") or "")]
    if cjk_items:
        errors.append("C16 %d 条 signatures 含中文——signatures 须为可扫描代码指纹（正则可编译且能命中代码），审查要点/定位提示应写入 keywords 字段：%s"
                      % (len(cjk_items), ", ".join(sorted({i for i, _ in cjk_items}))))

    # ---- C17 README 表 vs json（风险/状态/负载/触发，列名映射） ----
    # 数据行按 | 切分后有行首空单元格：cells[0]=''，故列号 = 表头下标 + 1
    col_idx = {name: i + 1 for i, name in enumerate(rd_header or [])} if rd_header else {}
    js_by_id = {p.get("id"): p for p in js.get("patterns", [])}
    st_map = {"active": "活跃", "retired": "退役", "deprecated": "废弃"}

    def trig_enum(p):
        """总览表「触发」列取值：必须触发 / 无代码触发特征 / 签名 / 宽泛定位 / 关键词。

        v6.2 起把「有没有可扫描指纹」显式化——此前 26 条已带签名的模式在表里仍写「关键词」，
        读者无法判断这一行到底能不能机器扫。宽泛定位 = 只有 broad_signatures（存在即常态，
        仅作定位提示，见 scan_fp.py）。
        """
        t = (p.get("applicability") or {}).get("trigger")
        if t == "必须触发":
            return "必须触发"
        if t == "无代码触发特征":
            return "无代码触发特征"
        sigs = [x if isinstance(x, str) else (x or {}).get("re") for x in (p.get("signatures") or [])]
        sigs = [x for x in sigs if x]
        broad = set(p.get("broad_signatures") or [])
        if any(s not in broad for s in sigs):
            return "签名"
        if sigs:
            return "宽泛定位"
        return "关键词"

    for oid, row in ov_rows:
        p = js_by_id.get(oid)
        if not p or not col_idx:
            continue
        cells = [c.strip().strip("*") for c in row.split("|")]
        ap = p.get("applicability") or {}
        pairs = (("风险", (p.get("risk") or {}).get("level", "?")),
                 ("状态", st_map.get(p.get("status"), p.get("status"))),
                 ("负载", p.get("depth")),
                 ("触发", trig_enum(p) if ap.get("trigger") else None))
        for col, jval in pairs:
            idx = col_idx.get(col)
            if idx is None or jval is None or idx >= len(cells):
                continue
            if cells[idx] and cells[idx] != jval:
                warns.append("C17 %s %s 不一致：README 表=%s json=%s" % (oid, col, cells[idx], jval))

    # ---- C18 拆分结构交叉引用 ----
    for p in js.get("patterns", []):
        fp = p.get("file")
        if not fp:
            continue
        ap_ = os.path.join(root, fp.replace("/", os.sep))
        if not os.path.exists(ap_):
            errors.append("C18 %s file 指向不存在的文件：%s" % (p.get("id"), fp))
    for cid, p, body in cards:
        for ref in set(re.findall(r"FP-[A-G]\d{2}", body)) - {cid}:
            if ref not in file_set:
                errors.append("C18 %s 引用了不存在的编号：%s" % (cid, ref))

    # ---- C18b 卡片「关联」集合 ↔ json related 双向等值 ----
    for cid, p, body in cards:
        m = re.search(r"^-\s*\*\*关联\*\*：(.*)", body, re.M)
        card_rel = set(re.findall(r"FP-[A-G]\d{2}", m.group(1))) if m else set()
        js_rel = set((js_by_id.get(cid) or {}).get("related") or [])
        if card_rel != js_rel:
            errors.append("C18b %s 关联集合与 json related 不等值：卡片=%s json=%s"
                          % (cid, "、".join(sorted(card_rel)) or "（空）",
                             "、".join(sorted(js_rel)) or "（空）"))

    # ---- C19 skills 层 B 轴一致性（v3.4；skills/README 编写规范第 7 条） ----
    skills_dir = os.path.join(root, "skills")
    skill_files = []
    if os.path.isdir(skills_dir):
        for dp, _, fs in os.walk(skills_dir):
            for f in fs:
                if f == "SKILL.md":
                    skill_files.append(os.path.join(dp, f))
        skill_files.sort()
        canon = "\n".join(SKILL_BAXIS_CANON)
        n_bad = 0
        for sp in skill_files:
            st = read_text(sp).replace("\r\n", "\n")
            miss = []
            if canon not in st:
                miss.append("B 轴标准段缺失或与全库措辞不一致")
            if "业务可达性核查" not in st:
                miss.append("流程缺『业务可达性核查』步")
            if "**业务影响评估（B 轴）**" not in st:
                miss.append("Bug 卡缺 B 轴字段")
            if "每卡含 B 轴业务影响评估" not in st:
                miss.append("报告结构缺 B 轴说明")
            if miss:
                errors.append("C19 %s：%s" % (os.path.relpath(sp, root), "；".join(miss)))
                n_bad += 1

        # 数量与三方对应（v3.4 后修缮）：skill 数 == 卡片数；覆盖表 ↔ 实际目录 ↔ frontmatter 注册名
        if len(skill_files) != len(file_order):
            errors.append("C19 skills 数与卡片数不一致：skills=%d 卡片=%d"
                          % (len(skill_files), len(file_order)))
        dir_names = set()
        for sp in skill_files:
            dn = os.path.basename(os.path.dirname(sp))
            dir_names.add(dn)
            st_fm = read_text(sp).replace("\r\n", "\n")
            m = re.search(r'^name:\s*"([^"]+)"', st_fm, re.M)
            if not m or m.group(1) != dn:
                errors.append("C19 %s：frontmatter 注册名 %r 与目录名 %r 不一致"
                              % (os.path.relpath(sp, root), m.group(1) if m else "(缺失)", dn))
            fm_block = re.search(r"^---\n(.*?)\n---", st_fm, re.S)
            dm = re.search(r'^description:\s*"(.+)"\s*$', fm_block.group(1), re.M) if fm_block else None
            if dm and len(dm.group(1)) > 200:
                errors.append("C19 %s：frontmatter description 长 %d 字符 > 上限 200"
                              "（skills/README 编写规范第 1 条：触发条件写全但删减枚举细节）"
                              % (os.path.relpath(sp, root), len(dm.group(1))))
        sreadme = os.path.join(skills_dir, "README.md")
        dir_to_fp = {}
        if os.path.isfile(sreadme):
            cov_rows = []
            for line in read_text(sreadme).splitlines():
                mm = re.match(r"^\|\s*\[(FP-[A-G]\d{2})\]\(([^)]+)\)\s*\|[^|]+\|\s*`([^`]+)`\s*\|", line)
                if mm:
                    cov_rows.append((mm.group(1), mm.group(2), mm.group(3)))
            dir_to_fp = {r[2]: r[0] for r in cov_rows}
            cov_ids = set(r[0] for r in cov_rows)
            only_cards = sorted(file_set - cov_ids)
            only_cov = sorted(cov_ids - file_set)
            if only_cards:
                errors.append("C19 覆盖表缺编号：%s" % "、".join(only_cards))
            if only_cov:
                errors.append("C19 覆盖表多出编号：%s" % "、".join(only_cov))
            cov_names = set(r[2] for r in cov_rows)
            if cov_names != dir_names:
                errors.append("C19 覆盖表 skill name 集与实际目录集不等值：表=%s 实际=%s"
                              % ("、".join(sorted(cov_names - dir_names)) or "（空）",
                                 "、".join(sorted(dir_names - cov_names)) or "（空）"))
            for cid, rel, nm in cov_rows:
                tp = os.path.normpath(os.path.join(skills_dir, rel))
                if not os.path.isfile(tp):
                    errors.append("C19 覆盖表链接失效：%s → %s" % (cid, rel))
                elif os.path.basename(os.path.dirname(tp)) != nm:
                    errors.append("C19 覆盖表 name %r 与链接目录 %r 不一致"
                                  % (nm, os.path.basename(os.path.dirname(tp))))
        else:
            warns.append("C19 未找到 skills/README.md，跳过覆盖表对应检查")
        infos.append("skills 层：%d 个 SKILL.md，B 轴不一致 %d 个" % (len(skill_files), n_bad))
    else:
        warns.append("C19 未找到 skills/ 目录，跳过 B 轴一致性检查")

    # ---- C19b 索引 business_impact 词表与 B 轴标准段一致（v3.4 后修缮） ----
    bi = js.get("business_impact")
    if not isinstance(bi, dict):
        errors.append("C19b 索引缺 business_impact 词表（B3/B2/B1 判据 + impact_types + disposition_matrix）")
    else:
        for k, frag in (("B3", "主流框架/公开模型默认路径即可命中"),
                        ("B2", "需特定 attr/dtype/shape 组合"),
                        ("B1", "极端、超规格或非法参数")):
            v = bi.get(k)
            if not isinstance(v, str) or frag not in v:
                errors.append("C19b business_impact.%s 缺失或判据与 B 轴标准段不一致" % k)
        if bi.get("impact_types") != BAXIS_IMPACT_TYPES:
            errors.append("C19b business_impact.impact_types 与 B 轴标准段四种业务影响类型不一致")
        if bi.get("disposition_matrix") != BAXIS_DISPOSITION:
            errors.append("C19b business_impact.disposition_matrix 与处置建议矩阵不一致")

    # ---- C19c skills 层判定纪律（v3.5；skills/README 编写规范第 8 条） ----
    jcanon = "\n".join(SKILL_JUDGMENT_CANON)
    n_bad_j = 0
    for sp in skill_files:
        st = read_text(sp).replace("\r\n", "\n")
        miss = []
        if jcanon not in st:
            miss.append("判定纪律标准段缺失或与全库措辞不一致")
        for frag in JUDGMENT_REQUIRED:
            if frag not in st:
                miss.append("缺机检片段 %r" % frag)
        if miss:
            errors.append("C19c %s：%s" % (os.path.relpath(sp, root), "；".join(miss)))
            n_bad_j += 1
    if skill_files:
        infos.append("skills 层：判定纪律不一致 %d 个" % n_bad_j)

    # ---- C19d 误判台账（v3.5） ----
    cases_js = os.path.join(root, "cases", "misjudgments.jsonl")
    cases_readme = os.path.join(root, "cases", "README.md")
    if not os.path.isfile(cases_js):
        errors.append("C19d 缺 cases/misjudgments.jsonl（误判台账）")
    else:
        if not os.path.isfile(cases_readme):
            warns.append("C19d 缺 cases/README.md（台账字段说明）")
        seen_ids, n_mj = set(), 0
        for ln_no, line in enumerate(read_text(cases_js).splitlines(), 1):
            s = line.strip()
            if not s:
                continue
            n_mj += 1
            try:
                rec = json.loads(s)
            except json.JSONDecodeError as e:
                errors.append("C19d 台账第 %d 行不是合法 JSON：%s" % (ln_no, e))
                continue
            if not isinstance(rec, dict):
                errors.append("C19d 台账第 %d 行不是 JSON 对象" % ln_no)
                continue
            miss = [k for k in MISJ_KEYS if not str(rec.get(k, "")).strip()]
            if miss:
                errors.append("C19d 台账第 %d 行缺字段：%s" % (ln_no, ", ".join(miss)))
                continue
            if not MISJ_ID_RE.match(rec["id"]):
                errors.append("C19d 台账第 %d 行 id 非法（应 MJ-YYYYMMDD-NN）：%s" % (ln_no, rec["id"]))
            elif rec["id"] in seen_ids:
                errors.append("C19d 台账 id 重复：%s" % rec["id"])
            seen_ids.add(rec["id"])
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", rec["date"]):
                errors.append("C19d %s date 非法（应 YYYY-MM-DD）：%s" % (rec["id"], rec["date"]))
            if rec["fp_id"] not in file_set:
                errors.append("C19d %s fp_id 在库内不存在：%s" % (rec["id"], rec["fp_id"]))
            if rec["type"] not in MISJ_TYPES:
                errors.append("C19d %s type 不在枚举内：%s" % (rec["id"], rec["type"]))
            if rec["status"] not in MISJ_STATUS:
                errors.append("C19d %s status 不在枚举内：%s" % (rec["id"], rec["status"]))
            if MISJ_INTERNAL_RE.search(rec["evidence"]) or MISJ_INTERNAL_RE.search(rec["source"]):
                errors.append("C19d %s evidence/source 含内部单号或本地路径（应只用公开 issue/PR 与仓内相对路径）"
                              % rec["id"])
        infos.append("误判台账：%d 条（C19d 校验）" % n_mj)

    # ---- C19e skill 适用声明头与卡片逐字一致（v4.0 后收口） ----
    card_appl = {}
    for cid, _p, body in cards:
        m = re.search(r"^-\s*\*\*适用\*\*：(.+)$", body, re.M)
        if m:
            card_appl[cid] = m.group(1).strip()
    n_bad_a = 0
    for sp in skill_files:
        st = read_text(sp).replace("\r\n", "\n")
        dn = os.path.basename(os.path.dirname(sp))
        fp = dir_to_fp.get(dn, "")
        if fp not in card_appl:
            continue
        expect = "- **适用声明头**（照抄卡片）：" + card_appl[fp]
        if expect not in st:
            errors.append("C19e %s：适用声明头与卡片不逐字一致（期望：%s）"
                          % (os.path.relpath(sp, root), expect[:60]))
            n_bad_a += 1
    if skill_files:
        infos.append("适用声明头：不一致 %d 份（C19e）" % n_bad_a)

    # ---- C31 skill 摘要元数据与卡片 / 索引三方一致（v5.1；防语义漂移） ----
    # skill §1「模式卡摘要」的元数据行（类别 / 风险 S×O / 状态）是**手抄卡片**，
    # 最易随卡片演进失同步——结构性守门 C1~C43 防不住这类语义漂移，故做三方比对。
    def _meta_dig(rest):
        cat = re.search(r"类别\**\s*[：:]?\s*([^｜|\s]+)", rest or "")
        rk = re.search(r"风险\**\s*[：:]?\s*([高中低])（S(\d+)[×x]O(\d+)=(\d+)）", rest or "")
        stv = re.search(r"状态\**\s*[：:]?\s*([^｜|\s]+)", rest or "")
        return {"类别": cat.group(1) if cat else None,
                "风险": rk.group(1) if rk else None,
                "SO": (int(rk.group(2)), int(rk.group(3))) if rk else None,
                "状态": stv.group(1) if stv else None}
    st_cn = {"active": "活跃", "retired": "退役", "deprecated": "废弃"}
    n_bad_m = 0
    for sp in skill_files:
        st = read_text(sp).replace("\r\n", "\n")
        dn = os.path.basename(os.path.dirname(sp))
        fp = dir_to_fp.get(dn, "")
        if fp not in file_set:
            continue
        sm = re.search(r"^- \*\*编号\s*/\s*名称\*\*：(.*)$", st, re.M)
        if sm is None:
            warns.append("C31 %s：skill §1 缺「- **编号 / 名称**：」摘要行（摘要无固定锚，易漂移）"
                         % os.path.relpath(sp, root))
            n_bad_m += 1
            continue
        s = _meta_dig(sm.group(1))
        cbody = next((b for c, _p, b in cards if c == fp), "")
        cm = re.search(r"^- \*\*元数据\*\*：(.*)$", cbody, re.M)
        c = _meta_dig(cm.group(1)) if cm else {}
        for fld in ("类别", "风险", "SO", "状态"):
            if s[fld] and c.get(fld) and str(s[fld]) != str(c[fld]):
                warns.append("C31 %s：skill 摘要 %s=%s 与卡片不一致（卡片=%s）"
                             % (os.path.relpath(sp, root), fld, s[fld], c[fld]))
                n_bad_m += 1
        jp = js_by_id.get(fp) or {}
        jr = jp.get("risk") or {}
        if s["风险"] and jr.get("level") and s["风险"] != jr["level"]:
            warns.append("C31 %s：skill 摘要风险档(%s) 与 json level(%s) 不一致"
                         % (os.path.relpath(sp, root), s["风险"], jr["level"]))
            n_bad_m += 1
        if s["SO"] and None not in (jr.get("s"), jr.get("o")) and s["SO"] != (jr.get("s"), jr.get("o")):
            warns.append("C31 %s：skill 摘要 S×O%s 与 json S%s×O%s 不一致"
                         % (os.path.relpath(sp, root), s["SO"], jr.get("s"), jr.get("o")))
            n_bad_m += 1
        if s["状态"] and st_cn.get(jp.get("status")) and s["状态"] != st_cn[jp.get("status")]:
            warns.append("C31 %s：skill 摘要状态(%s) 与 json(%s) 不一致"
                         % (os.path.relpath(sp, root), s["状态"], st_cn[jp.get("status")]))
            n_bad_m += 1
    if skill_files:
        infos.append("skill 摘要元数据三方一致：不一致 %d 处（C31）" % n_bad_m)

    # ---- C32 skill 案例回链校验（v5.2；防案例库铺开引入臆造 issue） ----
    # v5.1 起深度档 skill 末尾追加「已知缺陷案例库」，会大量引用 `#NNN` issue 号。
    # 判据：skill 文本中出现的每个 `#NNN` 必须能在**任一**模式卡片里找到——跨模式
    # 引用（如 FP-A12 引 FP-B07 的 #4494）合法，故用「全部卡片语料」而非「本模式卡」；
    # 全局找不到即疑似臆造/抄错，WARN（不阻断，交由人工回链卡片实证）。
    card_corpus = "\n".join(b for _c, _p, b in cards)
    n_bad_i = 0
    for sp in skill_files:
        st = read_text(sp).replace("\r\n", "\n")
        dn = os.path.basename(os.path.dirname(sp))
        if not dir_to_fp.get(dn, ""):
            continue
        miss = sorted({i for i in re.findall(r"#\d{3,}", st) if i not in card_corpus})
        if miss:
            warns.append("C32 %s：skill 引用的 issue %s 在全部模式卡中均不存在（疑似臆造，须回链卡片实证）"
                         % (os.path.relpath(sp, root), ", ".join(miss)))
            n_bad_i += 1
    if skill_files:
        infos.append("skill 案例回链：未回链 issue 的 skill %d 份（C32）" % n_bad_i)

    # ---- C33 案例库机读化 cases/cases.json（v5.6） ----
    # 判据：cases/cases.json 存在、可解析、结构字段齐全（case_id 唯一且格式合法 /
    # fp_id 在库内 / trigger+root_cause 非空 / 同步模式案例含 paired_primitives /
    # 真锚 verified_anchors 为 list 且各项 commit 为 5-40 位 hex、file 合文件正则），
    # library_version 与索引 version 一致（升版须重跑 gen_cases.py），深度档模式全覆盖，
    # 案例引用的 `#NNN` 须回链模式卡语料（同 C32 口径，WARN）。
    cases_path = os.path.join(root, "cases", "cases.json")
    if not os.path.isfile(cases_path):
        errors.append("C33 cases/cases.json 不存在（机读案例库缺失，请运行 scripts/gen_cases.py）")
    else:
        try:
            cj = json.loads(read_text(cases_path))
        except json.JSONDecodeError as e:
            errors.append("C33 cases/cases.json 不可解析：%s" % e)
            cj = None
        if isinstance(cj, dict):
            if cj.get("library_version") != js.get("version"):
                errors.append("C33 cases.json library_version=%r 与索引 version=%r 不一致"
                              "（升版后未重跑 gen_cases.py）" % (cj.get("library_version"), js.get("version")))
            ccases = cj.get("cases") or []
            if (cj.get("stats") or {}).get("total") != len(ccases):
                errors.append("C33 cases.json stats.total=%r 与实际案例数 %d 不一致"
                              % ((cj.get("stats") or {}).get("total"), len(ccases)))
            cids = [c.get("case_id") for c in ccases]
            dup_c = sorted({i for i in cids if cids.count(i) > 1})
            if dup_c:
                errors.append("C33 case_id 重复：%s" % ", ".join(map(str, dup_c)))
            n_bad_c = 0
            for c in ccases:
                cid = c.get("case_id", "?")
                if not re.match(r"^FP-[A-G]\d{2}-C\d+$", str(cid)):
                    errors.append("C33 case_id 格式非法：%r" % cid)
                    n_bad_c += 1
                if c.get("fp_id") not in file_set:
                    errors.append("C33 %s 的 fp_id=%r 不在库内" % (cid, c.get("fp_id")))
                    n_bad_c += 1
                if not c.get("trigger") or not c.get("root_cause"):
                    errors.append("C33 %s 缺触发条件或根因（案例块字段不全）" % cid)
                    n_bad_c += 1
                if c.get("fp_id") == "FP-G02" and "paired_primitives" not in c:
                    errors.append("C33 %s 为同步模式案例但缺 paired_primitives 字段" % cid)
                    n_bad_c += 1
                # 真锚回填（v5.6）：verified_anchors 须为 list；每项 commit 为 5-40 位 hex、
                # file 合文件正则、issue 在案例 issues 内；抽不到即空数组（不得臆造）
                va = c.get("verified_anchors")
                if not isinstance(va, list):
                    errors.append("C33 %s 的 verified_anchors 非 list" % cid)
                    n_bad_c += 1
                else:
                    for a in va:
                        a = a if isinstance(a, dict) else {}
                        if not re.match(r"^[0-9a-f]{5,40}$", str(a.get("commit") or "")):
                            errors.append("C33 %s 真实锚 commit 非法（须 5-40 位 hex）：%r"
                                          % (cid, a.get("commit")))
                            n_bad_c += 1
                        if not re.match(r"^[A-Za-z0-9_][\w./\-]*\.(?:cpp|cc|cxx|c|hpp|hxx|hh|h|py|json|asc|inc|txt)$",
                                        str(a.get("file") or "")):
                            errors.append("C33 %s 真实锚 file 非法：%r" % (cid, a.get("file")))
                            n_bad_c += 1
                        if not a.get("issue") or a.get("issue") not in (c.get("issues") or []):
                            warns.append("C33 %s 真实锚 issue=%r 不在案例 issues 内" % (cid, a.get("issue")))
                miss_i = sorted({i for i in (c.get("issues") or []) if i not in card_corpus})
                if miss_i:
                    warns.append("C33 %s 引用 issue %s 在模式卡语料中不存在（疑似臆造，须回链卡片实证）"
                                 % (cid, ", ".join(miss_i)))
            depth_ids = [p.get("id") for p in js.get("patterns", []) if p.get("depth") == "深度"]
            covered = {c.get("fp_id") for c in ccases}
            miss_depth = [i for i in depth_ids if i not in covered]
            if miss_depth:
                errors.append("C33 以下深度档模式无案例（案例库缺失）：%s" % "、".join(miss_depth))
            infos.append("案例库机读化：%d 条案例 / %d 个深度档模式 / 字段异常 %d 处（C33）"
                         % (len(ccases), len(depth_ids), n_bad_c))

    # ---- C28 未证实模式标注（v4.1） ----
    n_bad_u = 0
    for cid, _p, body in cards:
        if (js_by_id.get(cid) or {}).get("evidence"):
            continue
        if not re.search(r"^-\s*\*\*实证状态\*\*：\s*未证实", body, re.M):
            errors.append("C28 %s 索引 evidence 为空，但卡片缺「实证状态：未证实」标注" % cid)
            n_bad_u += 1
    infos.append("未证实标注：%d 条缺失（C28）" % n_bad_u)

    # ---- C29 全局相对链接（v4.1） ----
    def _strip_code(t):
        t = re.sub(r"```.*?```", "", t, flags=re.S)
        return re.sub(r"`[^`\n]*`", "", t)

    md_files = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in (".git", "__pycache__", "build", "node_modules")]
        for fn in fns:
            if fn.endswith(".md"):
                md_files.append(os.path.join(dp, fn))
    bad_links, bad_forms = [], []
    for mp in md_files:
        base = os.path.dirname(mp)
        body = _strip_code(read_text(mp))
        for m in re.finditer(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", body):
            tgt = m.group(1)
            if re.match(r"^[A-Za-z]+://", tgt) or tgt.startswith("mailto:"):
                continue
            if not os.path.exists(os.path.normpath(os.path.join(base, tgt))):
                bad_links.append((os.path.relpath(mp, root), tgt))
        # 形态 2：`[标签../路径)` —— 丢了 `](`。原正则只认 `](`，这种写法渲染出来是
        # 纯文本、点不动，C29 却报「失效 0」。USAGE/STANDARDS 从 README 拆出时实测漏过 21 处。
        for m in re.finditer(r"\[[^\]\n]*\.\./[^)\n]*\)", body):
            bad_forms.append((os.path.relpath(mp, root), m.group(0)[:80]))
    for mp, tgt in bad_links:
        errors.append("C29 %s 链接失效：%s" % (mp, tgt))
    for mp, form in bad_forms:
        errors.append("C29 %s 链接写法丢失「](」：%s（应为 [标签](相对路径)）" % (mp, form))
    infos.append("链接：%d 个 md，失效 %d，写法坏 %d（C29）"
                 % (len(md_files), len(bad_links), len(bad_forms)))

    # ---- C20 症状分诊表（v3.6；skills/README 消费入口） ----
    triage_path = os.path.join(root, "TRIAGE.md")
    if not os.path.isfile(triage_path):
        errors.append("C20 缺 TRIAGE.md（症状分诊表，由 scripts/gen_triage.py 生成）")
    else:
        tt = read_text(triage_path).replace("\r\n", "\n")
        if "scripts/gen_triage.py" not in tt or "勿手改" not in tt:
            errors.append("C20 TRIAGE.md 缺生成标记（应为 gen_triage.py 生成，勿手改）")
        miss_tr = sorted(file_set - set(re.findall(r"FP-[A-G]\d{2}", tt)))
        if miss_tr:
            errors.append("C20 TRIAGE.md 未覆盖模式：%s" % "、".join(miss_tr))
        for rel in re.findall(r"\]\((patterns/[^)]+|skills/[^)]+SKILL\.md)\)", tt):
            if not os.path.isfile(os.path.join(root, rel)):
                errors.append("C20 TRIAGE.md 链接失效：%s" % rel)
        grp_title, grp_rows, wide_bad = None, 0, []
        for line in tt.splitlines() + ["### __END__"]:
            if line.startswith("### "):
                if grp_rows > 6 and grp_title and "[WIDE]" not in grp_title:
                    wide_bad.append("%s（%d 条）" % (grp_title, grp_rows))
                grp_title, grp_rows = line[4:].strip(), 0
            elif line.startswith("|") and "FP-" in line:
                grp_rows += 1
        if wide_bad:
            errors.append("C20 单组候选 >6 且未标 [WIDE]：%s" % "；".join(wide_bad))
        try:
            sys.path.insert(0, os.path.join(root, "scripts"))
            import gen_triage  # noqa: E402
            _idx, _tri, _skills = gen_triage.load(root)
            _errs = gen_triage.validate(_idx, _tri, _skills)
            if _errs:
                errors.extend("C20 triage_map 不合法：%s" % e for e in _errs)
            elif gen_triage.render(_idx, _tri, _skills, gen_triage.load_cases(root)) != tt:
                errors.append("C20 TRIAGE.md 与 triage_map.json 生成结果不一致（改映射后未重跑 gen_triage.py）")
        except Exception as e:  # 生成器缺失或环境异常时降级为结构检查
            warns.append("C20 未能复核 triage_map（%s），仅做结构检查" % e)
        infos.append("症状分诊：%d 个入口" % len(re.findall(r"^## T\d ", tt, re.M)))

    # ---- C21 评测集（v3.8） ----
    try:
        sys.path.insert(0, os.path.join(root, "scripts"))
        import run_eval  # noqa: E402
        _ids, _cases, _errs = run_eval.validate(root)
        if _errs:
            errors.extend("C21 %s" % e for e in _errs)
        else:
            infos.append("评测集：%d 条模式 / %d 个用例（三类）" % (len(_ids), len(_cases)))
    except Exception as e:
        errors.append("C21 评测集校验失败：%s" % e)

    # ---- C36 评测证据级判据与 OOS 去重（v6.4） ----
    # 只有 verdict 的评测只能测「症状词→编号」的查表能力，测不出「有没有给证据 / 有没有编」。
    # 因此：① 每条用例 must_include / forbidden 均不得为空且须可编译；
    #       ② out-of-scope 剧本必须有足够多样性（去重 ≥12 个）且任一剧本复用 ≤3 次。
    _ev_files = sorted(glob.glob(os.path.join(root, "evals", "FP-*", "evals.json")))
    _oos_prompts = {}
    _n_case = _n_empty = 0
    for _f in _ev_files:
        try:
            _d = json.loads(read_text(_f))
        except ValueError as e:
            errors.append("C36 %s 不可解析：%s" % (_f, e))
            continue
        _pid = _d.get("pattern_id", "")
        for _c in _d.get("evals") or []:
            _n_case += 1
            _must = _c.get("must_include") or []
            _forb = _c.get("forbidden") or []
            if not _must or not _forb:
                _n_empty += 1
                errors.append("C36 %s/%s 缺证据级判据（must_include=%d forbidden=%d，二者均须非空）"
                              % (_pid, _c.get("id"), len(_must), len(_forb)))
            for _rx in list(_must) + list(_forb):
                try:
                    re.compile(_rx)
                except re.error as e:
                    errors.append("C36 %s/%s 判据正则不可编译：%r (%s)"
                                  % (_pid, _c.get("id"), str(_rx)[:40], e))
            if _c.get("kind") == "out-of-scope":
                _oos_prompts.setdefault(_c.get("prompt", ""), []).append(_pid)
    if _ev_files:
        _dup = {k: v for k, v in _oos_prompts.items() if len(v) > 3}
        if len(_oos_prompts) < 12:
            errors.append("C36 out-of-scope 剧本只有 %d 个（去重后，需 ≥12）：%s"
                          % (len(_oos_prompts), "、".join(sorted(_oos_prompts)[:3]) + "…"))
        if _dup:
            errors.append("C36 out-of-scope 剧本复用超限（>3 次）：%s"
                          % "；".join("%s×%d" % (k[:24].replace("\n", " "), len(v))
                                     for k, v in sorted(_dup.items())))
        infos.append("评测证据级判据：%d 例，缺判据 %d 例；OOS 剧本去重 %d 个"
                     % (_n_case, _n_empty, len(_oos_prompts)))

    # ---- C22 行号校验器在位（v3.8） ----
    try:
        import verify_lines  # noqa: E402
        if not hasattr(verify_lines, "verify") or not hasattr(verify_lines, "extract_refs"):
            errors.append("C22 scripts/verify_lines.py 接口缺失（应有 extract_refs / verify）")
        else:
            infos.append("行号校验器：verify_lines.py 在位")
    except Exception as e:
        errors.append("C22 scripts/verify_lines.py 不可用：%s" % e)

    # ---- C41 组合故障定义（v6.18.1） ----    # 起因：pattern_compositions.json 原先没有任何门禁——改模式编号、写错 members、
    # 把 next_experiment 结构写坏，主守门都不会报错，只有运行时调 query_patterns 才炸。
    # 校验逻辑不在此处重写：唯一权威源是 scripts/query_patterns.load_compositions()，
    # 主守门只负责「调用它 + 把异常转成 ERROR」，避免两份标准各自漂移。
    try:
        import query_patterns  # noqa: E402
        _comps = query_patterns.load_compositions(root)
        _comp_ids = [c.get("id") for c in _comps]
        # load_compositions 已保证 id 唯一/成员合法/实验结构合法；这里补跨文件一致性：
        # 每条组合的成员必须在索引里真实存在（load 已校验，这里再核一次防未来放宽）
        _known_ids = {p.get("id") for p in js.get("patterns", [])}
        _bad_mem = [(c.get("id"), [m for m in c.get("members") or [] if m not in _known_ids])
                    for c in _comps]
        _bad_mem = [x for x in _bad_mem if x[1]]
        if _bad_mem:
            errors.append("C41 组合引用了不存在的模式：%s"
                          % "；".join("%s→%s" % (i, "、".join(m)) for i, m in _bad_mem))
        infos.append("组合故障：%d 条（C41 结构 + 成员 + next_experiment 校验）" % len(_comp_ids))
    except FileNotFoundError:
        errors.append("C41 缺 pattern_compositions.json（组合故障定义）")
    except Exception as e:
        errors.append("C41 组合故障定义不合格：%s" % e)

    # ---- C46 可检出性 D 维度一致性（v6.21） ----
    # D 是 FMEA 的 Detection 维度，**不改 S×O、不动 risk.level**，只产出 priority=S×O×D。
    # 校验点：D 字段齐备、取值合法、priority 与 S×O×D 严格一致（防止有人手改 priority
    # 却不改 D，那会让排序失去可信度）。
    _d_missing, _d_bad, _d_pri = [], [], []
    for p in js.get("patterns", []):
        de = p.get("detectability")
        if not isinstance(de, dict):
            _d_missing.append(p["id"])
            continue
        if de.get("d") not in (1, 2, 3):
            _d_bad.append("%s(d=%r)" % (p["id"], de.get("d")))
            continue
        if not str(de.get("why") or "").strip():
            _d_bad.append("%s(缺 why)" % p["id"])
        s = (p.get("risk") or {}).get("s") or 0
        o = (p.get("risk") or {}).get("o") or 0
        want = s * o * de["d"]
        if de.get("priority") != want:
            _d_pri.append("%s(%s≠%d)" % (p["id"], de.get("priority"), want))
    if _d_missing:
        errors.append("C46 以下模式缺 detectability 字段：%s" % "、".join(_d_missing[:8]))
    if _d_bad:
        errors.append("C46 detectability 取值非法或缺 why：%s" % "、".join(_d_bad[:8]))
    if _d_pri:
        errors.append("C46 priority ≠ S×O×D：%s" % "、".join(_d_pri[:8]))
    if not (_d_missing or _d_bad or _d_pri):
        from collections import Counter as _C
        _cnt = _C((p["detectability"]["level"] for p in js["patterns"]))
        infos.append("可检出性 D：D1=%d / D2=%d / D3=%d（C46；D 只用于 priority 排序，不改定级）"
                     % (_cnt.get("D1", 0), _cnt.get("D2", 0), _cnt.get("D3", 0)))

    # ---- C49 核心基线必带「控制变量」行（v6.30） ----
    # 10 条核心基线是 test-design 每次设计必跑的检查表，而实测误判几乎全部来自「多变量同时变」。
    # 只要求「有这一行」不够——只写「要控制变量」等于没说，必须同时含「允许变动」与「典型误判」。
    _core = ["FP-A05", "FP-A07", "FP-B01", "FP-B02", "FP-B04",
             "FP-B06", "FP-B07", "FP-B12", "FP-G01", "FP-G02"]
    _cv_missing, _cv_thin = [], []
    for _pid in _core:
        _rel = next((p.get("file") for p in js.get("patterns", []) if p.get("id") == _pid), "")
        if not _rel:
            continue
        _fp = os.path.join(root, _rel)
        if not os.path.isfile(_fp):
            _cv_missing.append("%s(文件缺失)" % _pid)
            continue
        _txt = read_text(_fp)
        _mt = re.search(r"^- \*\*控制变量.*$", _txt, re.M)
        if not _mt:
            _cv_missing.append(_pid)
            continue
        _line = _mt.group(0)
        if ("允许变动" not in _line) or not re.search(r"典型误判|反例", _line):
            _cv_thin.append(_pid)
    if _cv_missing:
        errors.append("C49 核心基线缺「控制变量」行：%s（这 10 条是设计必跑表，"
                      "缺了就等于默许「多变量同时变」）" % "、".join(_cv_missing))
    if _cv_thin:
        errors.append("C49 核心基线的「控制变量」行不完整：%s（须同时含「允许变动」与"
                      "「典型误判/反例」——只写「要控制变量」等于没说）" % "、".join(_cv_thin))
    if not _cv_missing and not _cv_thin:
        infos.append("核心基线控制变量：%d/%d 条齐备（C49：固定项 + 允许变动 + 典型误判）"
                     % (len(_core), len(_core)))

    # ---- C50 文档散文计数与真源一致（v6.31） ----
    # 起因：为库做介绍 PPT 时引用 README 正文数字，被取数脚本打脸——正文 20 处计数停在
    # v6.21~v6.26，而标题 / 生成块 / AGENTS 尾部 / 门禁全部已是 v6.30 准确值。
    # 与 C47 是同一个病，区别只在位置：C47 管 AGENTS 那一行**格式固定**的计数，
    # 而散文里的计数散落在句子中间、措辞各异，既无格式可锚也无生成器可重算——
    # 反向实测证实：把 README 的「50/53 有可扫签名」改回「49/52」，C1~C49 与 ci_gate
    # 双双仍全绿。故本门禁只覆盖**能锚定语义的声明式短语**（列表见 _CLAIMS），
    # 不追求覆盖全部自然语言计数——覆盖不到的部分仍在 CHANGELOG 里逐版人工登记。
    #
    # 设计纪律（防「永远绿」的装饰门禁，同 v6.29 C48 的教训）：每条断言必须
    # ① 从真源算期望值（不写死），② 有明确的「期望子串」，③ 允许声明「本条不适用」。
    _pats = js.get("patterns", [])
    _sig_n = sum(1 for p in _pats if p.get("signatures"))
    _sub_m = sum(1 for p in _pats if p.get("subtypes"))
    _sub_n = sum(len(p.get("subtypes") or []) for p in _pats)
    _tot = len(_pats)
    _no_sig = [p.get("id") for p in _pats if not p.get("signatures")]
    _so = {}
    if os.path.isfile(os.path.join(root, "fault_patterns_secondary_oracle.json")):
        try:
            _so = json.loads(read_text(os.path.join(root, "fault_patterns_secondary_oracle.json")))
        except ValueError:
            _so = {}
    _so_pat = len(_so.get("patterns") or {})
    _so_rel = sum(len(v.get("relations") or []) for v in (_so.get("patterns") or {}).values())
    _cases = {}
    _cases_path = os.path.join(root, "cases", "cases.json")
    if os.path.isfile(_cases_path):
        try:
            _cases = json.loads(read_text(_cases_path))
        except ValueError:
            _cases = {}
    _case_n = len(_cases.get("cases") or [])

    # 每条： (文档, 人类可读项名, 期望出现的子串, 是否必须出现)
    _CLAIMS = [
        ("README.md", "子型模式数与条数",
         "%d 个模式已机读化 %d 条子型" % (_sub_m, _sub_n), True),
        ("README.md", "可扫签名覆盖（概述行）",
         "%d/%d 有可扫签名" % (_sig_n, _tot), True),
        ("README.md", "可扫签名覆盖（签名扫描行）",
         "覆盖 %d/%d" % (_sig_n, _tot), True),
        ("README.md", "案例条目数",
         "%d 条案例" % _case_n, True),
        ("README.md", "评测集份数",
         "%d 份 × 3 类用例" % _tot, True),
        ("README.md", "评测用例数",
         "%d×3 用例" % _tot, True),
        ("README.md", "skills 建成数",
         "%d/%d 已建" % (_tot, _tot), True),
        ("README.md", "卡数表述",
         "%d 张卡" % _tot, True),
        ("README.md", "单一判据模式数与分母",
         "%d/%d 条模式只有单一判据" % (_tot - _so_pat, _tot), True),
        ("README.md", "第二 oracle 模式与关系数",
         "%d 模式 / %d 条关系" % (_so_pat, _so_rel), True),
        ("INVARIANTS.md", "模式总数表述",
         "库里的 %d 条模式" % _tot, True),
        ("evals/README.md", "评测集覆盖模式数",
         "%d 条模式各一份" % _tot, True),
        ("AGENTS.md", "守门范围",
         "C1~C50", True),
        # 本轮起 docs/ 下的正文也要管：README 拆成入口 + docs/ 后，现行数字跟着搬过去，
        # 而 C50 只盯着 README/AGENTS/INVARIANTS/evals，搬出去就等于没人看。
        ("docs/USAGE.md", "子型模式数与条数",
         "%d 个模式已机读化 %d 条子型" % (_sub_m, _sub_n), True),
        ("docs/USAGE.md", "卡数与 skill 建成数",
         "%d 张卡各配一份" % _tot, True),
        ("docs/USAGE.md", "可扫签名覆盖",
         "覆盖 %d/%d" % (_sig_n, _tot), True),
    ]
    # 旧值黑名单：即使新值短语恰好也出现，只要旧值仍在，说明有人回改或漏改
    _STALE = [
        ("README.md", "子型旧值", "15 个模式已机读化 71 条子型"),
        ("README.md", "签名旧值", "49/52 有可扫签名"),
        ("README.md", "案例旧值", "93 条案例"),
    ]

    _c50_missing, _c50_stale, _c50_checked = [], [], 0
    for _doc, _label, _want, _must in _CLAIMS:
        _dp = os.path.join(root, _doc)
        if not os.path.isfile(_dp):
            if _must:
                _c50_missing.append("%s（文件缺失）" % _doc)
            continue
        _dt = read_text(_dp).replace("\r\n", "\n")
        _c50_checked += 1
        if _want not in _dt:
            _c50_missing.append("%s·%s（期望「%s」）" % (_doc, _label, _want))
    for _doc, _label, _badw in _STALE:
        _dp = os.path.join(root, _doc)
        if os.path.isfile(_dp) and _badw in read_text(_dp).replace("\r\n", "\n"):
            _c50_stale.append("%s·%s（仍含「%s」）" % (_doc, _label, _badw))

    if _c50_missing:
        errors.append("C50 文档散文计数与真源不一致 %d 处：%s（按真源重算后改正）"
                      % (len(_c50_missing), "；".join(_c50_missing[:6])))
    if _c50_stale:
        errors.append("C50 文档仍残留旧计数 %d 处：%s（可能被回改或漏改）"
                      % (len(_c50_stale), "；".join(_c50_stale[:6])))
    if not _c50_missing and not _c50_stale:
        infos.append("文档散文计数：%d/%d 项与真源一致 + 3 项旧值零残留（C50）"
                     % (_c50_checked, len(_CLAIMS)))

    # ---- C48 根目录 md 必须至少有一个入链（v6.28） ----
    # 两次孤儿的代价：IMPROVEMENTS_20261106.md（285 行副本）躺了 3 个小版本才被人工发现；
    # 紧接着 EVIDENCE_DISCIPLINE.md（127 行）推进来时入链为 0。
    # 两次都是「文件内容没问题，但没人知道它存在」——内容门禁（C29 链接可达、C39 脚本在位）
    # 全抓不到，因为它们只查「已引用的东西是否有效」，不查「该被引用的有没有被引用」。
    _root_whitelist = {"README.md", "CHANGELOG.md", "LICENSE"}
    _root_mds = sorted(f for f in os.listdir(root)
                       if f.endswith(".md") and os.path.isfile(os.path.join(root, f)))
    _orphans = []
    for _f in _root_mds:
        if _f in _root_whitelist:
            continue
        # 在 md / json 里找「除自身之外」的提及（文件名出现即算，含相对链接与散文提及）。
        #
        # **不收 .py**：这条判据要排除「自指误判」——脚本/测试里为了创建或断言某个文件名而
        # 把它写进源码，会被算成「有入链」，等于门禁自己给自己发通行证。实测踩过：
        # test_meta_gates.py 里写了 `_ORPHAN_SELFTEST.md`，于是 C48 认为该孤儿「有引用」，
        # 反向验证直接失效——**一条永远绿的门禁比没有门禁更糟，因为它给人虚假的安心**。
        # 收 .json 是因为 cases/sig_yield 这类基线里确实会引用文件路径（真入链）。
        _hit = False
        for _dirpath, _dirnames, _filenames in os.walk(root):
            _dirnames[:] = [d for d in _dirnames if d not in (".git", "build", "node_modules")]
            for _fn in _filenames:
                if not _fn.endswith((".md", ".json")):
                    continue
                _fp = os.path.join(_dirpath, _fn)
                if os.path.abspath(_fp) == os.path.abspath(os.path.join(root, _f)):
                    continue
                try:
                    if _f in read_text(_fp):
                        _hit = True
                        break
                except Exception:
                    continue
            if _hit:
                break
        if not _hit:
            _orphans.append(_f)
    if _orphans:
        errors.append("C48 根目录孤儿 md（无任何入链，读者/agent 不会知道它存在）：%s "
                      "—— 要么补进 README 目录树 / AGENTS 决策表，要么删掉"
                      % "、".join(_orphans))
    else:
        infos.append("根目录 md 入链：%d 份全部有引用（C48，白名单 %d 份）"
                     % (len(_root_mds) - len(_root_whitelist), len(_root_whitelist)))

    # ---- C47 AGENTS.md 尾部计数与真源一致（v6.28） ----
    # 起因：AGENTS.md 末尾那行 9 类计数**从来没被任何门禁管过**，从 v6.21 一路漂到
    # 落后 6 个版本（写 52 条 / 81 子型 / 23 模式 43 关系，实际 53 / 91 / 24 模式 45 关系），
    # 而 C1~C46 全绿。这类「描述串漂移」不会让门禁变红，只会让读者读到假数字——
    # 而 AGENTS.md 恰好是 agent 进来第一个读的文件，假数字影响最大。
    _agents_path = os.path.join(root, "AGENTS.md")
    if not os.path.isfile(_agents_path):
        warns.append("C47 缺 AGENTS.md（agent 一页速查），无法校验尾部计数")
    else:
        _at = read_text(_agents_path).replace("\r\n", "\n")
        _m = re.search(r"^> 版本：v([\d.]+) ｜ 规模：(\d+) 条 ｜ 有可扫签名：(\d+)/(\d+) "
                       r"｜ 已机读化子型：(\d+) 模式 / (\d+) 条 ｜ 深度档：(\d+) "
                       r"｜ L2 判据：(\d+)/(\d+) ｜ L3 失效：(\d+) 类 / (\d+) 条 "
                       r"｜ 组合：(\d+) 条 ｜ 第二 oracle：(\d+) 模式 / (\d+) 关系",
                       _at, re.M)
        if not _m:
            errors.append("C47 AGENTS.md 尾部计数行格式不符（应为 `> 版本：vX ｜ 规模：N 条 ｜ …` 单行）")
        else:
            def _rj(name):
                fp = os.path.join(root, name)
                if not os.path.isfile(fp):
                    return {}
                try:
                    return json.loads(read_text(fp))
                except ValueError:
                    return {}
            _det = _rj("fault_patterns_detect.json")
            _so = _rj("fault_patterns_secondary_oracle.json")
            _comp = _rj("pattern_compositions.json")
            _pats = js.get("patterns", [])
            _want = [
                ("版本", str(js.get("version")), _m.group(1)),
                ("规模", len(_pats), int(_m.group(2))),
                ("有可扫签名", sum(1 for p in _pats if p.get("signatures")), int(_m.group(3))),
                ("规模(分母)", len(_pats), int(_m.group(4))),
                ("子型模式", sum(1 for p in _pats if p.get("subtypes")), int(_m.group(5))),
                ("子型条数", sum(len(p.get("subtypes") or []) for p in _pats), int(_m.group(6))),
                ("深度档", sum(1 for p in _pats if p.get("depth") == "深度"), int(_m.group(7))),
                ("L2 判据", len(_det.get("patterns") or []), int(_m.group(8))),
                ("L2 分母", len(_pats), int(_m.group(9))),
                ("L3 类", len((_det.get("oracle_failures") or {}).get("by_oracle") or {}), int(_m.group(10))),
                ("L3 条", sum(len(v) for v in ((_det.get("oracle_failures") or {}).get("by_oracle") or {}).values()), int(_m.group(11))),
                ("组合", len(_comp.get("compositions") or []), int(_m.group(12))),
                ("第二 oracle 模式", len(_so.get("patterns") or {}), int(_m.group(13))),
                ("第二 oracle 关系", sum(len(v.get("relations") or []) for v in (_so.get("patterns") or {}).values()), int(_m.group(14))),
            ]
            _bad = [(k, w, g) for k, w, g in _want if w != g]
            if _bad:
                errors.append("C47 AGENTS.md 尾部计数与真源不一致 %d 项：%s（跑 scripts/gen_agents_tail.py 重算）"
                              % (len(_bad), "；".join("%s 写 %s 实际 %s" % (k, g, w) for k, w, g in _bad[:6])))
            else:
                infos.append("AGENTS.md 尾部计数：14 项与真源一致（C47）")

    # ---- C44 第二 oracle 覆盖与独立性（v6.19） ----
    # 实测（v6.19 首轮）：40/52 条模式只有单一 oracle；当前 24/53 已登记、高优先级 20/20
    # （以本门禁自己的打印为准）。单点判据的根本问题不是「不准」，而是
    # 「错了没人知道」——返回码对但错误码选错、racecheck 零告警但连接口都没进 kernel。
    # 第二判据的唯一硬要求是「机制独立」：同面判据只是让概率看起来更好看。
    try:
        import check_secondary_oracle  # noqa: E402
        _so_errs, _so_infos = check_secondary_oracle.validate(root)
        if _so_errs:
            errors.extend("C44 %s" % e for e in _so_errs[:6])
        else:
            for _i in _so_infos:
                infos.append("C44 " + _i)
    except Exception as e:
        errors.append("C44 第二 oracle 校验失败：%s" % e)

    # ---- C45 CI 网关与新增脚本在位（v6.19） ----
    # 防「写了工具但没接线」：v6.15 曾把 scan_sync_scope.py 写进卡片却没有该文件。
    _need_scripts = ["ci_gate.py", "check_anchors.py", "check_secondary_oracle.py",
                     "mutate_ops.py", "sync_detect_section.py",
                     "gen_readme_diagram.py", "gen_agents_tail.py",
                     "test_meta_gates.py"]
    _miss = [s for s in _need_scripts
             if not os.path.isfile(os.path.join(root, "scripts", s))]
    if _miss:
        errors.append("C45 以下脚本缺失：%s" % "、".join(_miss))
    elif not os.path.isfile(os.path.join(root, ".gitlab-ci.yml")):
        errors.append("C45 缺 .gitlab-ci.yml（门禁不接 CI 等于没有门禁）")
    else:
        infos.append("CI 网关：%d 个检查项已接线（C45）" % len(_need_scripts))

    # ---- C42 深度档技能的 L2/L3 小节与索引一致（v6.18.1） ----
    # 起因：L2/L3 只存在于 JSON，52 份 SKILL.md 一份都没引用——Agent 走 workflows→skills
    # 读不到「怎么测」和「oracle 会怎么骗你」，新增两层在实际作业中等于不存在。
    # 这里不重写渲染逻辑：直接调 sync_detect_section 的同一函数比对，防两份标准漂移。
    try:
        import sync_detect_section  # noqa: E402
        _sec_items = sync_detect_section.targets(root)
        _sec_stale = []
        for _fp, _path, _want, _ref_path, _ref_want in _sec_items:
            if not os.path.isfile(_path):
                errors.append("C42 %s 的 SKILL.md 不存在：%s" % (_fp, _path))
                continue
            _txt = read_text(_path)
            # 用生成器自己的提取函数，别在这里另写切片：BEGIN 与 `## N.` 同行，
            # 从标记处切会丢标题前缀，导致恒报不一致。
            _got = sync_detect_section.extract_section(_txt)
            if _got is None:
                _sec_stale.append("%s(缺指针段)" % _fp)
            elif _got != _want:
                _sec_stale.append("%s(指针段不一致)" % _fp)
            # 完整判据落在 skills/<skill>/references/detect-l2-l3.md，也要核
            _ref_now = read_text(_ref_path) if os.path.isfile(_ref_path) else None
            if _ref_now is None:
                _sec_stale.append("%s(缺 references/%s)" % (_fp, sync_detect_section.REF_NAME))
            elif _ref_now != _ref_want:
                _sec_stale.append("%s(references 不一致)" % _fp)
        if _sec_stale:
            errors.append("C42 以下深度档技能的 L2/L3 小节与索引不一致"
                          "（跑 python3 scripts/sync_detect_section.py）：%s"
                          % "、".join(_sec_stale))
        else:
            infos.append("L2/L3 判据：%d 份深度档技能（指针段 + references/detect-l2-l3.md）"
                         "与索引逐字一致（C42）" % len(_sec_items))
    except Exception as e:
        errors.append("C42 L2/L3 小节校验失败：%s" % e)

    # ---- C43 工作流「必须触发」清单与索引一致（v6.18.1） ----
    # 起因：operator-admission 曾把必须触发写死成 4 条表格，而索引已增至 6 条——
    # FP-A22 / FP-G02 在准入体检里被整段漏检，守门却全绿。工作流是 Agent 的入口文档，
    # 入口写错等于后续所有检视都少了两条必查项，必须在门禁层面盯住。
    _wf = os.path.join(root, "workflows", "operator-admission.md")
    if not os.path.isfile(_wf):
        errors.append("C43 缺 workflows/operator-admission.md")
    else:
        _must = sorted(p.get("id") for p in js.get("patterns", [])
                       if (p.get("applicability") or {}).get("trigger") == "必须触发")
        # 必须核「Stage 1 区块内的表格行」而不是「全文出现」：编号在正文叙述与
        # Stage 2/3 的表里也会被提到，只查子串或全文行首都会让「删掉 Stage 1 表格行」照样通过。
        _wtxt = read_text(_wf).replace("\r\n", "\n")
        _s1 = re.search(r"^### Stage 1.*?(?=^### |\Z)", _wtxt, re.M | re.S)
        _rows = set()
        if _s1:
            _rows = {m.group(1) for m in re.finditer(r"^\|\s*(FP-[A-G]\d{2})\s*\|",
                                                     _s1.group(0), re.M)}
        _missing = [pid for pid in _must if pid not in _rows]
        if not _s1:
            errors.append("C43 operator-admission.md 缺「### Stage 1」区块，无法核必须触发清单")
        elif _missing:
            errors.append("C43 operator-admission.md 的 Stage 1 表格漏列必须触发模式"
                          "（索引 %d 条）：%s" % (len(_must), "、".join(_missing)))
        else:
            infos.append("工作流必须触发清单：Stage 1 表格与索引一致（%d 条，C43）" % len(_must))

    # ---- C23 签名扫描器与签名卫生（v3.8） ----
    try:
        import scan_fp  # noqa: E402
        _idx2, _pats = scan_fp.load_patterns(root)
        _serrs, _swarns = scan_fp.hygiene(_pats)
        if _serrs:
            errors.extend("C23 %s" % e for e in _serrs)
        n_sig = sum(len(p["signatures"]) for p in _pats)
        infos.append("签名：%d 条（跨模式去重；判别性偏弱 %d 条）" % (n_sig, len(_swarns)))
        for w in _swarns:
            infos.append("C23 提示 " + w)
    except Exception as e:
        errors.append("C23 scripts/scan_fp.py 不可用：%s" % e)

    # ---- C39 文档引用的 scripts/*.py 必须在位（v6.16） ----
    # 起因：v6.15 在 FP-G02 卡片里写了「机检脚本见 scripts/scan_sync_scope.py」，
    # 但仓里根本没有这个文件，而 C1~C43 全绿——「卡片承诺了一个不存在的工具」
    # 这类空头支票只有读者会撞上。本门禁把「所有 md 里出现的 scripts/*.py 路径」
    # 逐个核在位性。
    #
    # **能力边界（勿误以为覆盖全部工具名）**：只认带 `scripts/` 前缀的写法。不带前缀的
    # `.py` 名字放过——实测本仓 md 里这类名字有 9 个（`golden.py`、`test/test_ops.py`、
    # `ops/built-in/.../in_training_update_v2.py` 等），全部是 **算子仓里的文件名示例**，
    # 按「名字必须在 scripts/ 下存在」去判会 9/9 假报。真本仓工具一律写 `scripts/名字.py`
    # （C45 另有底线：几个关键脚本必须在位）。
    _md_files = []
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in (".git", "__pycache__", "build", "output")]
        for fn in fns:
            if fn.endswith(".md"):
                _md_files.append(os.path.join(dp, fn))
    _script_ref_re = re.compile(r"scripts/([A-Za-z_][\w\-]*\.py)")
    # 变更记录与归档报告里的 `scripts/xxx.py` 常是**泛指写法**（"所有被引用的 scripts/*.py"），
    # 不是具体引用；把它们纳入在位性检查会产出「xxx.py 不存在」的假 ERROR（实测踩过）。
    _C39_SKIP = {"CHANGELOG.md", "REFACTOR_REPORT.md"}
    _referenced = {}
    for _p in _md_files:
        _base = os.path.basename(_p)
        if _base in _C39_SKIP:
            continue
        try:
            _txt = read_text(_p)
        except OSError:
            continue
        for _m in _script_ref_re.finditer(_txt):
            _referenced.setdefault(_m.group(1), set()).add(os.path.relpath(_p, root))
    _missing_scripts = []
    for _sn, _where in sorted(_referenced.items()):
        if not os.path.isfile(os.path.join(root, "scripts", _sn)):
            _missing_scripts.append("%s（被 %s 引用）"
                                    % (_sn, "、".join(sorted(_where)[:3])))
    if _missing_scripts:
        errors.append("C39 以下被文档引用的脚本不存在（卡片承诺了不存在的工具）：%s"
                      % "；".join(_missing_scripts))
    else:
        infos.append("脚本引用：%d 个被 md 引用的 scripts/*.py 全部在位（C39）"
                     % len(_referenced))

    # ---- C40 L2 判据层一致性（v6.17） ----
    # 起因：库长期只有 L1 机理层（为什么会坏），没有 L2 判据层（怎么测）。
    # 后果是可测的：`aclnn-test-design` 的 pattern_case() 只能生成「不得复现该现象」的空壳，
    # `aclnn-bug-hunt` 只能用 category 把 22 条机理迥异的 accuracy 模式一律映射到 precision。
    # C40 保证 index 每条模式的 detect 字段齐备且与真源 fault_patterns_detect.json 一致，
    # 防止「改了真源忘了重新合并」和「新增模式忘了写判据」两类腐化。
    _detect_src = os.path.join(root, "fault_patterns_detect.json")
    _detect_errs = []
    if not os.path.isfile(_detect_src):
        errors.append("C40 缺 fault_patterns_detect.json（L2 判据层真源）")
    else:
        try:
            _dj = json.loads(read_text(_detect_src))
            _dpats = {p.get("id"): p for p in (_dj.get("patterns") or []) if p.get("id")}
            _vocab = _dj.get("vocab") or {}
            _axes_v = set((_vocab.get("axes") or {}).keys())
            _oracle_v = set((_vocab.get("oracle") or {}).keys())
            _signal_v = set(((_vocab.get("signal") or {}).get("values")) or [])
            _line_v = set(((_vocab.get("line") or {}).get("values")) or [])
            for _p in js.get("patterns", []):
                _pid = _p.get("id")
                _d = _p.get("detect") or {}
                _want = _dpats.get(_pid)
                if not _want:
                    _detect_errs.append("%s 无 L2 判据" % _pid)
                    continue
                for _f in ("axes", "oracle", "signal", "lines", "constructor", "judge", "kill"):
                    if not _d.get(_f):
                        _detect_errs.append("%s 的 detect.%s 为空" % (_pid, _f))
                for _a in _d.get("axes") or []:
                    if _a not in _axes_v:
                        _detect_errs.append("%s axes 越界:%s" % (_pid, _a))
                for _o in _d.get("oracle") or []:
                    if _o not in _oracle_v:
                        _detect_errs.append("%s oracle 越界:%s" % (_pid, _o))
                if _d.get("signal") and _d["signal"] not in _signal_v:
                    _detect_errs.append("%s signal 越界:%s" % (_pid, _d["signal"]))
                for _l in _d.get("lines") or []:
                    if _l not in _line_v:
                        _detect_errs.append("%s lines 越界:%s" % (_pid, _l))
                # 与真源逐字段对齐：防止手改 index 绕过真源
                for _f in ("axes", "oracle", "signal", "lines", "min_cases",
                           "constructor", "judge", "kill"):
                    _dv = _d.get(_f)
                    _wv = _want.get(_f, 1 if _f == "min_cases" else None)
                    if isinstance(_dv, list) or isinstance(_wv, list):
                        if sorted(_dv or []) != sorted(_wv or []):
                            _detect_errs.append("%s detect.%s 与真源不一致" % (_pid, _f))
                    elif _dv != _wv:
                        _detect_errs.append("%s detect.%s 与真源不一致" % (_pid, _f))
            _orphan = [k for k in _dpats if k not in {p.get("id") for p in js.get("patterns", [])}]
            if _orphan:
                _detect_errs.append("真源有定义但索引无此模式：%s" % "、".join(sorted(_orphan)))
            # L3 oracle 失效模式（v6.18；v6.18.1 起改内容全等，不再只比 id 序列）
            # 只比 id 的漏洞是可复现的：把某条 rule 改成编造内容、id 不动，主守门原先仍全绿——
            # 而 L3 的价值全在 rule 那句话上，id 只是「去上游 grep 全文」的引用锚。
            # 因此这里同时承担两件事：① D20–D29 结构校验（与 scripts/gen_detect.py 同口径，
            # 主守门不依赖外部脚本被调用）；② 索引 ↔ 真源逐条 (id, fail, rule) 全等。
            _src_of = (_dj.get("oracle_failures") or {}).get("by_oracle") or {}
            _idx_of = ((js.get("detect_layer") or {}).get("oracle_failures") or {}).get("by_oracle") or {}
            _used_oracle = {o for p in js.get("patterns", [])
                            for o in ((p.get("detect") or {}).get("oracle") or [])}
            _no_of = sorted(_used_oracle - set(_src_of))
            if _no_of:
                _detect_errs.append("oracle 被使用但无失效清单(L3/D23)：%s" % "、".join(_no_of))
            if not _src_of:
                _detect_errs.append("oracle_failures.by_oracle 为空或类型错(L3/D21)")
            _bad_cat = sorted(c for c in _src_of if c not in _oracle_v)
            if _bad_cat:
                _detect_errs.append("oracle_failures 含词表外类别(L3/D22)：%s" % "、".join(_bad_cat))
            _fail_kinds = set()
            for _c in _src_of:
                _items = _src_of[_c]
                if not isinstance(_items, list) or not _items:
                    _detect_errs.append("oracle_failures[%s] 不是非空列表(L3/D24)" % _c)
                    continue
                # 编号唯一限定在「类别内」：同一条 pitfalls 记录可以同时说明两个观测手段的失效
                # （README：69 条引用对应去重 63 个 K 号），跨类别复用是设计内的。
                _seen_ids = set()
                for _it in _items:
                    if not isinstance(_it, dict):
                        _detect_errs.append("oracle_failures[%s] 含非对象条目(L3/D25)" % _c)
                        continue
                    _kid = str(_it.get("id") or "").strip()
                    if not re.fullmatch(r"K\d{1,4}", _kid):
                        _detect_errs.append("oracle_failures[%s] 编号非法 %r(L3/D26)" % (_c, _kid))
                    if _kid in _seen_ids:
                        _detect_errs.append("oracle_failures[%s] 编号重复 %s(L3/D26)" % (_c, _kid))
                    _seen_ids.add(_kid)
                    if not str(_it.get("rule") or "").strip():
                        _detect_errs.append("oracle_failures[%s] %s 缺 rule(L3/D27)" % (_c, _kid))
                    _fk = str(_it.get("fail") or "").strip()
                    if not _fk:
                        _detect_errs.append("oracle_failures[%s] %s 缺 fail 类型(L3/D28)" % (_c, _kid))
                    _fail_kinds.add(_fk)
            for _want in ("假 PASS", "假 FAIL"):
                if not any(_want in _k or _k in _want for _k in _fail_kinds):
                    _detect_errs.append("oracle_failures 未覆盖「%s」类失效(L3/D29)："
                                        "只记一类说明策展不全" % _want)
            if sorted(_idx_of) != sorted(_src_of):
                _detect_errs.append("索引的 oracle_failures 与真源类别不一致"
                                    "（真源 %d 类 / 索引 %d 类）" % (len(_src_of), len(_idx_of)))
            else:
                for _c in _src_of:
                    _sig_of = lambda _xs: [(str(i.get("id") or "").strip(),
                                            str(i.get("fail") or "").strip(),
                                            str(i.get("rule") or "").strip())
                                           for i in (_xs or []) if isinstance(i, dict)]
                    if _sig_of(_src_of[_c]) != _sig_of(_idx_of[_c]):
                        _detect_errs.append(
                            "oracle_failures[%s] 条目与真源不一致（改真源后未跑 "
                            "scripts/gen_detect.py，或 rule/fail 被单独改动）" % _c)
        except Exception as e:
            _detect_errs.append("解析失败：%s" % e)
    if _detect_errs:
        errors.append("C40 L2 判据层不合格（%d 处，跑 scripts/gen_detect.py 重新合并）：%s"
                      % (len(_detect_errs), "；".join(_detect_errs[:8])))
    else:
        _js_pats = js.get("patterns", [])
        _n_oracle = len({o for p in _js_pats for o in ((p.get("detect") or {}).get("oracle") or [])})
        _n_axes = len({a for p in _js_pats for a in ((p.get("detect") or {}).get("axes") or [])})
        _of = ((js.get("detect_layer") or {}).get("oracle_failures") or {}).get("by_oracle") or {}
        _n_of = sum(len(v) for v in _of.values())
        infos.append("L2 判据层：%d 条模式齐备，用到 %d 种轴 / %d 种观测手段（C40）"
                     % (len(_js_pats), _n_axes, _n_oracle))
        infos.append("L3 失效模式：%d 个 oracle 类别 / %d 条实测失效判据，"
                     "%d 种被使用的观测手段全部有失效清单（C40）"
                     % (len(_of), _n_of, _n_oracle))

    # ---- C24 能力边界与自检（v3.8） ----
    n_bad_b = 0
    for sp in skill_files:
        st = read_text(sp).replace("\r\n", "\n")
        dn = os.path.basename(os.path.dirname(sp))
        fp = dir_to_fp.get(dn, "")
        miss = []
        if "## 10. 能力边界与自检" not in st:
            miss.append("缺「## 10. 能力边界与自检」节")
        if "找不到 ≠ 没有" not in st:
            miss.append("缺「找不到 ≠ 没有」声明")
        if "verify_lines.py" not in st:
            miss.append("自检缺行号校验命令")
        if fp and ("scan_fp.py --only %s" % fp) not in st:
            miss.append("自检缺本模式扫描命令（%s）" % fp)
        if miss:
            errors.append("C24 %s：%s" % (os.path.relpath(sp, root), "；".join(miss)))
            n_bad_b += 1
    if skill_files:
        infos.append("能力边界与自检：%d 份，缺失 %d 份" % (len(skill_files), n_bad_b))

    # ---- C25 任务级工作流（v4.0） ----
    wf_dir = os.path.join(root, "workflows")
    if not os.path.isdir(wf_dir):
        errors.append("C25 缺 workflows/ 目录（任务级编排）")
    else:
        wf_readme = os.path.join(wf_dir, "README.md")
        wf_body = read_text(wf_readme) if os.path.isfile(wf_readme) else ""
        if not wf_body:
            errors.append("C25 缺 workflows/README.md（路由表）")
        wf_files = sorted(f for f in os.listdir(wf_dir)
                          if f.endswith(".md") and f != "README.md")
        if not wf_files:
            errors.append("C25 workflows/ 下没有工作流文件")
        for rel in re.findall(r"\]\(([a-z0-9-]+\.md)\)", wf_body):
            if not os.path.isfile(os.path.join(wf_dir, rel)):
                errors.append("C25 workflows/README 链接失效：%s" % rel)
        for f in wf_files:
            p = os.path.join(wf_dir, f)
            body = read_text(p)
            if f not in wf_body:
                errors.append("C25 workflows/README 路由表未登记 %s" % f)
            if "## 阶段" not in body or "### Stage 0" not in body:
                errors.append("C25 %s 缺「## 阶段」或「### Stage 0」" % f)
            for rel in re.findall(r"\]\((\.\./[^)]+)\)", body):
                if not os.path.isfile(os.path.normpath(os.path.join(wf_dir, rel))):
                    errors.append("C25 %s 链接失效：%s" % (f, rel))
        if wf_files:
            infos.append("工作流：%d 条（%s）" % (len(wf_files), "、".join(wf_files)))

    # ---- C26 工作量与抽样（v4.0，depth 驱动） ----
    DEPTH_RULE = {"深度": "全量核查，不抽样",
                  "标准": "每映射点取前 20 处",
                  "宽浅": "每类抽 3 例"}
    n_bad_s = 0
    for sp in skill_files:
        st = read_text(sp).replace("\r\n", "\n")
        dn = os.path.basename(os.path.dirname(sp))
        fp = dir_to_fp.get(dn, "")
        depth = ((js_by_id.get(fp) or {}).get("depth") or "") if fp else ""
        miss = []
        if "### 工作量与抽样（v4.0）" not in st:
            miss.append("缺「### 工作量与抽样（v4.0）」")
        if depth and DEPTH_RULE.get(depth) and DEPTH_RULE[depth] not in st:
            miss.append("抽样规则与索引 depth=%s 不一致" % depth)
        if miss:
            errors.append("C26 %s：%s" % (os.path.relpath(sp, root), "；".join(miss)))
            n_bad_s += 1
    if skill_files:
        infos.append("抽样规则：%d 份，不一致 %d 份" % (len(skill_files), n_bad_s))

    # ---- C27 skill 评分卡（v4.0） ----
    try:
        import score_skills  # noqa: E402
        _idx3, _rows3 = score_skills.collect(root)
        sc_path = os.path.join(root, "skills", "SCORECARD.md")
        if not os.path.isfile(sc_path):
            errors.append("C27 缺 skills/SCORECARD.md（由 score_skills.py 生成）")
        elif read_text(sc_path).replace("\r\n", "\n") != score_skills.render(_idx3, _rows3):
            errors.append("C27 SCORECARD.md 与重算结果不一致（改 skill 后未重跑 score_skills.py）")
        bad_sc = [r["fp"] for r in _rows3 if r["verdict"] == "REWRITE"]
        if bad_sc:
            infos.append("C27 评分卡判 REWRITE（%d 份，工作清单非阻断）：%s"
                         % (len(bad_sc), "、".join(bad_sc)))
        infos.append("评分卡：%d 份，平均 %.1f，REWRITE %d"
                     % (len(_rows3), sum(r["total"] for r in _rows3) / len(_rows3) if _rows3 else 0,
                        len(bad_sc)))
    except Exception as e:
        errors.append("C27 scripts/score_skills.py 不可用：%s" % e)

    infos.append("条目总数：卡片=%d 总览=%d json=%d" % (len(file_order), len(ov_order), len(js_order)))
    infos.append("版本：README=v%s json=%s" % (rd_ver or "?", js.get("version", "?")))

    result = {
        "status": "error" if errors else ("warn" if warns else "ok"),
        "total_cards": len(file_order),
        "total_json": len(js_order),
        "total_overview": len(ov_order),
        "readme_version": rd_ver,
        "json_version": js.get("version"),
        "errors": errors,
        "warnings": warns,
        "infos": infos,
    }

    if not args.quiet:
        print("=" * 62)
        print("故障模式库健康检查（拆分版）")
        print("=" * 62)
        for i in infos:
            print("[INFO] " + i)
        for w in warns:
            print("[WARN] " + w)
        for e in errors:
            print("[ERROR] " + e)
        print("-" * 62)
    print("[OK] 检查完成 | status=%s | ERROR=%d WARN=%d | 条目=%d"
          % (result["status"], len(errors), len(warns), len(file_order)))

    if args.out:
        d = os.path.dirname(os.path.abspath(args.out))
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")

    if errors:
        return 2
    return 3 if warns else 0


if __name__ == "__main__":
    sys.exit(main())

