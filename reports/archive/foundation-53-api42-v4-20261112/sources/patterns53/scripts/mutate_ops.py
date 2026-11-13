#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
变异测试（mutate_ops.py，v6.19）——把「找不到 ≠ 没有」从口号变成可测指标

要解决的问题
------------
库里反复强调「未命中只能表述为本轮未发现」。这个纪律是对的，但它**不可证伪**：
没有任何机制能回答「这次没找到，是用例/判据不够强，还是真的没有」。

变异测试给出量化答案：往算子源码里注入**语义已知变化**的变异，看检视手段能不能抓住。
抓不住说明**判据本身不行**，而不是算子没问题。

与库的嫁接点（这是本工具的设计核心）
----------------------------------
变异算子不是凭空编的，每个都挂到已有的知识资产上：
  `from_pattern`  —— 对应哪条模式（FP-X##）
  `from_l3`       —— 对应哪条 L3 失效判据（K##），说明「为什么这类变异会被误判漏掉」
  `detector`      —— 用什么手段抓（scan_fp 签名 / absence 规则 / 人工清单项）
  `expect_catch`  —— 该变异**应当**被抓到；若未抓到，记 `survived` 并计入 kill rate 缺口
  `expect_miss`   —— 已知抓不到（正则能力边界），单独统计，**不计入缺口**——
                     把它单列出来，才是对「能力边界」的诚实量化，而不是拿它掩盖 kill rate

kill rate 口径（v6.20 修正：必须分层，否则数字无意义）
----------------------------------------------------
**同一份 kill rate 不能混跨越检测层级统计**。变异能否被抓，取决于「判据在哪一层」：

  tier=static   判据只依赖代码形态 → 静态扫描（scan_fp / scan_sync_scope）就能判。
                这类变异"抓不到"才说明**签名体系真的弱**。
  tier=dynamic  判据必须上板实测（bitwise 重复跑、golden-utol 比标杆、watchdog 超时）→
                静态扫描**原理上不可能**判定。这类变异计入 static kill rate 只会
                把「层级错配」误报成「判据不行」。

实测依据：52 条模式里 **37 条**的 oracle 是 dynamic 类（bitwise/golden-utol/watchdog/
sanitizer），只有 15 条偏静态。若不分层，kill rate 会被 dynamic 类的必然失败拉低，
得到一个"看起来很差但归因错误"的结论。

因此本工具输出**三个数**：
  static_kill   —— static tier 的 kill rate，**这是衡量签名体系的真指标**
  dynamic_gap   —— dynamic tier 中静态必然抓不到的比例，**不是缺陷，是层级事实**
  known_miss    —— 显式声明 `expect_catch=False` 的（正则能力边界），单列披露

只有 `static_kill` 值得作为改进目标；`dynamic_gap` 的意义是提醒：
**这部分必须上板，静态报 0 不代表没问题**。

用法
----
python3 scripts/mutate_ops.py --list                       # 变异算子清单
python3 scripts/mutate_ops.py --self-test                  # 注入/回滚冒烟（不碰真实仓）
python3 scripts/mutate_ops.py --run --repos <父目录>        # 在真实仓上跑（只读副本，不污染）
python3 scripts/mutate_ops.py --run --repos <父目录> --json # 机读

退出码
------
0 = kill rate 达阈值或仅统计 ｜1 = kill rate 低于 --min-kill ｜2 = 参数/环境错误
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 逐例打印差分详情（--verbose）
VERBOSE = False

# ---------------------------------------------------------------------------
# 变异算子库：每条都从「已知模式 / 已知 L3 失效」派生
# ---------------------------------------------------------------------------
MUTATORS = [
    {
        "id": "M01",
        "name": "边界比较反向（<= → <）",
        "from_pattern": "FP-B07",
        "from_l3": "K91",
        "why": "边界差一（off-by-one）是索引越界最经典的形态；L3 K91 记录 inf==inf 被判超容差导致溢出类假 FAIL，说明边界类判据极易失效。",
        "find": r"<=\s*(\w+)",
        "repl": r"< \1",
        "detectable_by": "dynamic",
        "detector": "signature",
        "expect_catch": True,
        "hint": "scan_fp 的 FP-B07 签名覆盖 `idx|Offset` 承载；边界比较反向本身不在签名内，"
                "但改了边界通常会连带改变 `<=` 附近的偏移表达式，需人工清单项确认。",
    },
    {
        "id": "M02",
        "name": "判空条件取反（== nullptr → != nullptr）",
        "from_pattern": "FP-B04",
        "from_l3": "K171",
        "why": "判空取反会让必选参数为空时放行、非空时反而报错。L3 K171 记录容差须按 dtype/mode 分级",
         "find": r"==\s*nullptr",
        "repl": "!= nullptr",
        "detectable_by": "dynamic",
        "detector": "signature",
        # 实测（ops-nn，2026-11-04）：注入 8 处判空取反，scan_fp 抓 0 处。
        # 原因不是 bug 而是判据形态限制——FP-B04 的签名全是「存在型」
        # （OP_CHECK_NULL / CheckNotNull / ACLNN_ERR_PARAM_NULLPTR），取反后这些 token
        # 一个不少，存在型匹配照样命中，**无法反映语义正确性**。
        # 这类缺陷只能靠「反模式签名」（同时匹配解引用与缺判空）或实测置空。
        # 保留为 expect_catch=True 是为了让它持续在报告里显示为 0%——
        # 把缺口摊在明面上，比悄悄改成 expect_miss 更有价值。
        "expect_catch": True,
        "observed_gap": "ops-nn 实测 0/8：存在型签名无法识别判空取反",
    },
    {
        "id": "M03",
        "name": "循环上界 +1（重复调度）",
        "from_pattern": "FP-C01",
        "from_l3": "",
        "why": "host 侧循环上界写错导致同一 kernel 下发 N 倍，单次耗时正常、总耗时线性放大——"
               "性能类单点判据完全看不见。",
        "find": r"for\s*\(\s*(?:size_t|int32_t|int64_t|int|uint32_t)\s+(\w+)\s*=\s*0\s*;\s*\1\s*<",
        "repl": None,  # 特殊处理：把 < 改成 <=  见 apply_special
        "detectable_by": "static",
        "detector": "signature",
        "expect_catch": False,
        "observed_gap": "ops-nn 实测 0/10：循环上界属跨语句语义（需知道理论迭代次数），无签名可判",
        "hint": "当前签名体系没有「循环上界」指纹（属跨语句语义），必然漏——这正是 expect_miss 的意义。",
    },
    {
        "id": "M04",
        "name": "移除待清零（Delete 一行 barrier）",
        "from_pattern": "FP-G02",
        "from_l3": "K2",
        "why": "删掉一处 PipeBarrier 造成流水乱序。L3 K2 记录 san 符号数为 0 时 racecheck 也假绿，"
               "因此「删了同步但 racecheck 没报」是真实存在的漏检路径。",
        "find": r"^\s*PipeBarrier<\s*PIPE_V\s*>\s*\(\s*\)\s*;\s*$",
        "repl": "// [MUTATED] PipeBarrier removed",
        "detectable_by": "static",
        "detector": "pair",
        "expect_catch": True,
        "hint": "scan_sync_scope 的作用域审计与 set/wait 配平可发现一部分；纯 PipeBarrier 缺失"
                "需 racecheck 实测才确证。",
    },
    {
        "id": "M05",
        "name": "窄化丢精度（int64 → int32 强转）",
        "from_pattern": "FP-B13",
        "from_l3": "",
        "why": "host 侧 int64→int32 窄化使参数值静默改变；只在超大 shape 暴露。",
        "find": r"static_cast<int32_t>\s*\(\s*(\w+)\s*\)",
        "repl": r"static_cast<int32_t>(\1)",
        "detectable_by": "static",
        "detector": "signature",
        "expect_catch": True,
        "hint": "FP-B13 已有 `static_cast<int32_t>` 签名（虽为 broad），可定位。",
    },
    {
        "id": "M06",
        "name": "默认属性值改动（0 → -1）",
        "from_pattern": "FP-B14",
        "from_l3": "",
        "why": "proto 默认值与 tiling 期望不一致，是图模式编译失败的典型根因（#5201 实测形态）。",
        "find": r"\.ATTR\(\s*(\w+)\s*,\s*Int\s*,\s*0\s*\)",
        "repl": r".ATTR(\1, Int, -1)",
        "detectable_by": "dynamic",
        "detector": "signature",
        "expect_catch": True,
    },
    {
        "id": "M07",
        "name": "空分支早退不写输出",
        "from_pattern": "FP-B12",
        "from_l3": "K128",
        "why": "numel==0 早退直接 return，返回 SUCCESS 但输出未初始化。L3 K128 记录"
               "「输出整块未写只能靠独立金丝雀发现，分布判据会假 PASS」。",
        "find": r"if\s*\(\s*(\w*(?:numel|Numel|isEmpty|IsEmpty)[\w()]*)\s*\)\s*\{\s*return",
        "repl": None,
        "detectable_by": "static",
        "detector": "absence",
        "expect_catch": True,
        "hint": "FP-B12 的 absence 规则可发现「早退路径缺输出写」，但需逐函数上下文，当前只能部分覆盖。",
    },
    {
        "id": "M08",
        "name": "dtype 映射表条目错配（int32 → uint32）",
        "from_pattern": "FP-A22",
        "from_l3": "K129",
        "why": "模板映射表把同宽度兄弟 dtype 指错，特定 dtype 静默走错分支；L3 K129 记录金丝雀与合法输出重合会假 PASS。",
        "find": r"DT_INT32\s*,\s*DT_UINT32",
        "repl": "DT_UINT32, DT_UINT32",
        "detectable_by": "dynamic",
        "detector": "signature",
        "expect_catch": False,
        "observed_gap": "ops-nn 实测 0/10：dtype 映射是数据表内容，形态与正确表完全一致，静态不可判",
        "hint": "映射表条目是数据而非代码形态，签名扫不到；必须靠 dtype 全组合实测。属已知边界。",
    },
    {
        "id": "M09",
        "name": "workapce 未清零先读",
        "from_pattern": "FP-A05",
        "from_l3": "K590",
        "why": "未初始化 workspace 读导致随机结果；L3 K590 记录「真检判据看 per-case 日志有无本算子 kernel，不是 started 计数」。",
        "find": r"GetWorkspaceSize\s*\(",
        "repl": "GetWorkspaceSize(",
        "detectable_by": "dynamic",
        "detector": "signature",
        "expect_catch": False,
        "observed_gap": "ops-nn 实测：workspace 读写时序属数据流，签名只能定位 GetWorkspaceSize 存在",
        "hint": "这是定位型签名（必然命中），改了不构成可判缺陷——说明「命中」与「判据」是两件事。",
    },
    {
        "id": "M10",
        "name": "tiling 常量硬编码核数",
        "from_pattern": "FP-B02",
        "from_l3": "",
        "why": "核数写死导致跨芯片核数不适配，功能可能仍正确、性能严重退化。",
        "find": r"SetBlockDim\s*\(\s*(\d+)\s*\)",
        "repl": r"SetBlockDim(\1)",
        "detectable_by": "dynamic",
        "detector": "signature",
        "expect_catch": False,
        "observed_gap": "ops-nn 实测：SetBlockDim 数值正确性需对照目标芯片核数，非形态特征",
        "hint": "SetBlockDim 恒被调用，改数值不产生形态差异；需对照目标芯片核数才知道是否硬编码。",
    },

    # ================= v6.20 扩充：补齐高风险模式的形态级注入 =================
    # 原则：只收「语义已知 + 可机械注入 + 注入后形态可判」的变异。
    # 语义级变异（改方向 / 改默认值 / 改索引指向）虽也能注入，但 static 层原理上判不了，
    # 前 10 条里已保留若干作为 dynamic 样本，此处不再重复堆数量。

    {
        "id": "M11",
        "name": "原子加失效（SetAtomicAdd 被删）",
        "from_pattern": "FP-A06",
        "from_l3": "K79",
        "why": "确定性开关要求消除原子加的浮点累加乱序。删掉 SetAtomicAdd 后该 token 消失，"
               "而 FP-A06 签名正是匹配 AtomicAdd/SetAtomicAdd → 形态层应可定位。"
               "L3 K79 记录「多线程位模式不一致先做串行 digest 对照」，说明这是真实踩坑面。",
        "find": r"^\s*(?:AscendC::)?SetAtomicAdd<[^>]*>\s*\([^)]*\)\s*;\s*$",
        "repl": "// [MUTATED] atomic-add gate removed",
        "detectable_by": "static",
        "detector": "signature",
        "expect_catch": True,
        "hint": "签名匹配 AtomicAdd/SetAtomicAdd，删除后同文件其他原子加仍仍命中——"
                "这是存在型签名的固有局限：能报「还有」，不能报「这里没了」。",
        # v6.20 实测 3/10。逐例复查 7 个未抓到样本：**每个文件都残留 2~5 个**
        # AtomicAdd/SetAtomic/Deterministic token，故存在型签名照旧命中。
        # 这不是某条签名写错，而是「存在型 vs 计数配平」的结构性局限：
        # 要判「删了一处」必须做**出现次数配平/基线对比**，当前扫描器不支持。
        "observed_gap": "ops-nn 实测 3/10：未捕获样本均残留 2~5 个同类 token，存在型签名无法判「少了一处」",
    },
    {
        "id": "M12",
        "name": "跨核定序失效（SetScheduleMode 被删）",
        "from_pattern": "FP-A20",
        "from_l3": "",
        "why": "确定性等级依赖 SetScheduleMode(1) 保证跨核下发顺序。删除后 token 消失，形态可观测。",
        # 真实写法是对象调用（context_->SetScheduleMode(BATCH_MODE)），
        # 最初只写了 AscendC:: 静态调用形态，实测命中 0 次
        "find": r"^[ \t]*[\w>\-.]+SetScheduleMode\s*\([^)]*\)\s*;[ \t]*$",
        "repl": "// [MUTATED] schedule-order call removed",
        "detectable_by": "static",
        "detector": "signature",
        "expect_catch": False,
        # v6.20 实测 0/10。已排除装置与写法问题：补 absence 判据后仍抓不到，
        # 根因是「定序原语缺失」属**跨文件配平**（host 与 kernel 两侧、多文件之间），
        # 文件级/函数级规则无法表达。标 expect_miss 使 kill rate 不再把它算作签名缺陷。
        "observed_gap": "ops-nn 实测 0/10（含计数配平判据）：该算子目录内定序调用通常只有 1 处，"
                          "注入后变成 0，但组内无其他非零同伴（实测同伴计数多为 [0,0,1,0]），"
                          "无法建立基线。这是计数配平的结构性边界——它只能发现「本该有 N 处却只有 N-1 处」，"
                          "发现不了「本该有 1 处却没有」。",
    },
    {
        "id": "M13",
        "name": "跨核同步删除（CrossCoreSetFlag 被删）",
        "from_pattern": "FP-G02",
        "from_l3": "K28",
        "why": "双 AIV 跨核等待缺失。L3 K28 记录「AICPU 算子插桩空跑，0 告警不等于无竞争」——"
               "正说明静态看到 flag 消失比依赖 racecheck 更可靠。",
        "find": r"^\s*(?:AscendC::)?CrossCoreSetFlag<[^>]*>\s*\([^)]*\)\s*;\s*$",
        "repl": "// [MUTATED] cross-core set-flag removed",
        "detectable_by": "static",
        "detector": "pair",
        "expect_catch": True,
        "hint": "CrossCoreSetFlag 与 CrossCoreWaitFlag 构成配对判据，删一侧造成配平失衡——"
                "判别型优于定位型的典型场景。",
    },
    {
        "id": "M14",
        "name": "tiling 模板注册被注释（新增路径漏测根源）",
        "from_pattern": "FP-A19",
        "from_l3": "",
        "why": "FP-A19 判据是「每个 REGISTER_TILING_TEMPLATE 都有用例命中」。"
               "注释掉一条注册即模拟「模板新增但未纳入测试矩阵」的形态。",
        "find": r"^\s*REGISTER_TILING_TEMPLATE\s*\([^)]*\)\s*;\s*$",
        "repl": "// [MUTATED] tiling-template registration removed",
        "detectable_by": "static",
        "detector": "signature",
        "expect_catch": True,
        # v6.20 实测 0/10。同理：注释掉一条注册后，同文件/同目录其余注册仍在，
        # 存在型签名照旧命中；而「注册数 < IsCapable 实现数」需跨文件计数。
        "observed_gap": "ops-nn 实测 0/10：模板注册缺失属跨文件配平，存在型签名只报「还有」",
    },
    {
        "id": "M15",
        "name": "tiling 条件恒假（IsCapable 首行 return false）",
        "from_pattern": "FP-A07",
        "from_l3": "",
        "why": "FP-A07 是「tiling 条件判断错误走入错误分支」。在 IsCapable 首行插 return false，"
               "使该模板永不命中，形态即「IsCapable 后紧跟 return false」。",
        # 必须容忍限定名（bool OpTiling::IsCapable()）——最初写成 \w*IsCapable，
        # 在 `::` 前就断了，实测命中 0 次
        "find": r"(bool\s+(?:[\w:]+::)?\w*IsCapable\s*\([^)]*\)\s*(?:const\s*)?\{)",
        "repl": r"\1\n        return false;  // [MUTATED]",
        "detectable_by": "static",
        "detector": "signature",
        "expect_catch": True,
        "hint": "该形态与 FP-A19 的 IsCapable→return false 签名高度相似，可顺带检验签名误报率。",
    },
    {
        "id": "M16",
        "name": "属性读取未判空（GetAttrPointer 结果直接使用）",
        "from_pattern": "FP-A10",
        "from_l3": "",
        "why": "FP-A10 类问题根因常是 GetAttrPointer 返空后直接解引用。",
        # 真实写法：const float* p = attrs->GetAttrPointer<float>(0);
        "find": r"(=\s*[\w>\-.]+GetAttrPointer<[^>]*>\s*\([^)]*\)\s*;)",
        "repl": r"\1  // [MUTATED] null-check removed",
        "detectable_by": "static",
        "detector": "signature",
        "expect_catch": True,
        # v6.21 差分判定实测 10/10：删除判空后，GetAttrPointer 附近
        # 的候选行内容变化，差分可见。v6.20 记 0/10 是旧口径误判。
        "hint": "签名只匹配 GetAttrPointer 存在（2142 处），无法判「是否判空」——跨语句语义，已知边界。",
    },
    {
        "id": "M17",
        "name": "workspace 大小少算一个对齐块",
        "from_pattern": "FP-D01",
        "from_l3": "",
        "why": "显存占用不足导致越界写。形态：返回的 size 减去固定量。",
        "find": r"(return\s+)(\w*(?:[Ww]orkspace|[Ss]ize)\w*\s*;\s*$)",
        "repl": r"\1(\2 - 1024);  // [MUTATED]",
        "detectable_by": "dynamic",
        "detector": "signature",
        "expect_catch": False,
        "observed_gap": "ops-nn 实测：workspace 公式正确性须逐算子推导，静态只定位公式所在行",
        "hint": "workspace 公式正确性须逐算子推导（FP-D01 判据），静态只能定位公式所在行。",
    },
    {
        "id": "M18",
        "name": "错误码降级为通用失败（PARAM_NULLPTR → INNER）",
        # v6.21 修正：原标 FP-B11，但改的 ACLNN_ERR_PARAM_NULLPTR 属 FP-B04 签名；
        # FP-B11 的签名是 CheckShape/GetDimNum/INT32_MAX/IsFinite（形状维度校验）。
        # 标错模式会让「抓不到」被误记为 FP-B11 的缺陷，实则是检测器对的不是这条路。
        "from_pattern": "FP-B04",
        "from_l3": "K171",
        "why": "契约校验的关键不只是「报错」，而是「报对错误码」。改成通用失败后返回码仍非 0，"
               "但下游无法据此分支。",
        "find": r"ACLNN_ERR_PARAM_NULLPTR",
        "repl": "ACLNN_ERR_INNER",
        "detectable_by": "static",
        "detector": "signature",
        "expect_catch": True,
        "hint": "FP-B04/B11 签名均含 ACLNN_ERR_PARAM_NULLPTR；改成 INNER 后该 token 消失。",
    },
    {
        "id": "M19",
        "name": "对齐搬运退化为普通搬运（DataCopyPad → DataCopy）",
        "from_pattern": "FP-A05",
        "from_l3": "K638",
        "why": "尾块/非对齐搬运依赖 DataCopyPad 处理边界，退化为 DataCopy 会越界。",
        "find": r"DataCopyPad\s*\(",
        "repl": "DataCopy(",
        "detectable_by": "static",
        "detector": "signature",
        "expect_catch": False,
        "observed_gap": "ops-nn 实测 0/10（含计数配平）：DataCopyPad 在 kernel 内密度极高（万级），"
                          "替换一处后同文件仍有大量同类调用，计数配平与存在型均无感；"
                          "且「该用 Pad 却用普通搬运」需知 shape 是否对齐，属语义判断。",
        "hint": "签名无 DataCopyPad 指纹（14027 处，加了会刷屏）；且「该用 Pad 却用普通搬运」"
                "需知 shape 是否对齐，属语义判断。已知边界。",
    },
    {
        "id": "M20",
        "name": "平台分支漏一个 SoC 版本",
        "from_pattern": "FP-C06",
        "from_l3": "",
        "why": "新平台未适配时 GetSocVersion 的 if-else 链漏分支，落到默认分支行为。",
        "find": r"(GetSocVersion\s*\(\s*\)\s*==\s*)(\w+)",
        "repl": r"\1SOC_VERSION_UNKNOWN_\2",
        "detectable_by": "static",
        "detector": "signature",
        "expect_catch": True,
    },
]


# ---------------------------------------------------------------------------
# 可静态判定性：每个变异声明「这个变异要被抓到，最低需要哪一层手段」。
#
# 这个字段的判定标准是**客观的**：看变异是否改变了签名正则能观测到的代码形态。
#   签名能观测到的形态 = token 的出现/消失/配平/计数（存在型 · 缺失型 · 配对型）
#   签名观测不到的     = 语义正确性（比较方向对不对、默认值该是几、映射表该指哪）
#
# 例：M01 `<=` → `<` 改变了 token（`<=` 消失），但 FP-B07 的签名匹配的是
#     `idx|Offset` 这类承载词，不匹配比较符号本身 → 静态签名**观测不到**该变化，
#     故 detectable_by="dynamic"。这不是签名写差了，而是「比较方向是否正确」
#     属于语义层，只能靠边界 shape 实测。
#
# 分层口径（v6.20）：
#   static  —— 变异改变了签名能观测的**形态**（如整行被删、token 消失、配平被打破），
#              静态扫描本该抓到；抓不到 = 签名体系真的弱，**这才是改进目标**。
#   dynamic —— 变异只改变**语义**（方向、默认值、索引指向），形态不变；
#              静态扫描原理上不可能判定，必须上板。抓不到是**层级事实，不是缺陷**。
# ---------------------------------------------------------------------------
DETECT_TIERS = ("static", "dynamic")


def tier_of(m):
    """返回该变异的可静态判定层级；缺字段时保守判 dynamic 并显式报错。"""
    return m.get("detectable_by") or "dynamic"


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)


def iter_sources(base, exts=(".cpp", ".h", ".hpp", ".cc")):
    for dirpath, _dirs, files in os.walk(base):
        if any(x in dirpath.replace("\\", "/") for x in ("/tests/", "/build/", "/.git/")):
            continue
        for fn in files:
            if fn.endswith(exts):
                yield os.path.join(dirpath, fn)


def apply_mutator(m, text):
    """返回 (new_text, count)。M03/M07 有特殊逻辑。"""
    if m["id"] == "M03":
        pat = re.compile(m["find"], re.M)
        out, n = [], 0
        pos = 0
        for mt in pat.finditer(text):
            seg = text[pos:mt.end()]
            seg2 = seg[:-1] + "<="
            out.append(seg2)
            pos = mt.end()
            n += 1
        out.append(text[pos:])
        return "".join(out), n
    if m["id"] == "M02":
        new, n = re.subn(m["find"], m["repl"], text)
        return new, n
    if m["repl"] is None:
        return text, 0
    new, n = re.subn(m["find"], m["repl"], text, flags=re.M)
    return new, n


def run_on_corpus(repos_dir, sample_limit=60, use_scan=True):
    """在真实仓的**临时副本**上注入变异，统计 kill rate。

    只取前 sample_limit 个含目标形态的文件，避免全仓变异过慢。

    **检测装置必须保留路径结构**（v6.20 修）：absence 规则的 `files` 字段是
    「相对路径正则」（如 `op_host`、`op_api/aclnn_.*\\.cpp$`），scan_fp 用
    `fre.search(相对路径)` 判定。若把变异文件丢到临时目录根下（如 `/tmp/x/a.cpp`），
    路径里没有 `op_host` 段 → 规则直接不生效 → 该抓到的一律报「抓不到」。
    实测踩到过：M12 补了 absence 判据仍 0/10，根因就是这个，不是判据弱。
    现在按 `rel` 在临时根下重建目录树，并把**临时根**作为扫描目标。
    """
    import tempfile
    import shutil as sh
    results = []
    scan_fp = os.path.join(ROOT, "scripts", "scan_fp.py")
    repo_map = {"ops-nn": "ops-nn", "ops-math": "ops-math",
                "ops-cv": "ops-cv", "ops-transformer": "ops-transformer"}

    for m in MUTATORS:
        pat = re.compile(m["find"], re.M) if m.get("find") else None
        if pat is None:
            results.append(dict(m, injected=0, killed=0, survived=0, note="无匹配式"))
            continue
        # 找一个可用仓里的样本文件
        picked, base = [], None
        for repo in repo_map:
            cand = os.path.join(repos_dir, repo)
            if not os.path.isdir(cand):
                continue
            base = cand
            for fp in iter_sources(cand):
                try:
                    if pat.search(read(fp)):
                        picked.append(fp)
                        if len(picked) >= sample_limit:
                            break
                except OSError:
                    continue
            if picked:
                break
        if not picked:
            results.append(dict(m, injected=0, killed=0, survived=0,
                                note="本机语料未出现该形态"))
            continue

        injected = killed = 0
        tmp = tempfile.mkdtemp(prefix="mut_")
        try:
            for fp in picked:
                text = read(fp)
                new, n = apply_mutator(m, text)
                if n == 0 or new == text:
                    continue
                injected += 1
                rel = os.path.relpath(fp, base)
                dst = os.path.join(tmp, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                write(dst, new)

                caught = False
                if use_scan and os.path.isfile(dst):
                    # ---- v6.21 差分判定（这是本工具最关键的口径修正）----
                    # 旧实现：只要变异文件的 scan_fp 返回 1 就算「抓到」。
                    # 但存在型签名对**原文件本来就会命中**——实测 M04/M11/M13/M15/M20
                    # 的样本原文件全部 6/6 已命中，于是「一直没变过的候选」被误算成
                    # 「抓到了注入的缺陷」，static_kill 被系统性高估。
                    # 正确口径：**只有变异前后的扫描结果不同，才算判据感知到了这次修改**。
                    before = scan_fingerprint(fp, m["from_pattern"])
                    after = scan_fingerprint(dst, m["from_pattern"])
                    if before is not None and after is not None and before != after:
                        caught = True
                        if VERBOSE:
                            print("      [diff] %s: %d -> %d 候选"
                                  % (os.path.basename(fp),
                                     before.count("\n"), after.count("\n")))
                    # ---- 计数配平（v6.21 新增第二判据）----
                    # 存在型/缺失型都看不见「少了一处」，计数配平能看见：
                    # 该文件的 token 计数低于同目录同伴下界即候选。见 scan_counts.py。
                    if not caught:
                        cb = count_fingerprint(os.path.dirname(fp),
                                               os.path.basename(fp), new,
                                               m["from_pattern"])
                        if cb:
                            caught = True
                            if VERBOSE:
                                print("      [count] %s 计数低于同伴下界"
                                      % os.path.basename(fp))
                if caught:
                    killed += 1
        finally:
            sh.rmtree(tmp, ignore_errors=True)

        results.append(dict(m, injected=injected, killed=killed,
                            survived=injected - killed,
                            note=""))
    return results


def count_fingerprint(src_dir, fname, new_text, pattern_id):
    """计数配平判定：把变异后的文件放回**同目录副本**里，看是否低于同伴下界。

    单独抽成函数是因为它必须重建目录上下文：`count_signatures.files` 是路径正则
    （如 `op_host/.*_tiling.*.cpp$`），文件若脱离 `op_host` 段就匹配不上——
    v6.20 已在这上面栽过一次（变异文件丢临时目录根导致 absence 规则失效）。
    """
    import tempfile
    import shutil as _sh
    try:
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import scan_counts
    except ImportError:
        return False
    rules = [r for r in scan_counts.load_counts(ROOT)
             if r["pid"] == pattern_id]
    if not rules:
        return False
    tmp = tempfile.mkdtemp(prefix="cnt_")
    try:
        # 用原路径的末两级重建目录（保证能在路径里出现 op_host / op_kernel 等段）
        tail = os.path.basename(src_dir)
        dd = os.path.join(tmp, tail)
        os.makedirs(dd, exist_ok=True)
        for fn in os.listdir(src_dir):
            s = os.path.join(src_dir, fn)
            if os.path.isfile(s) and fn.endswith((".cpp", ".h", ".hpp", ".cc")):
                _sh.copy(s, os.path.join(dd, fn))
        write(os.path.join(dd, fname), new_text)
        cands, _ = scan_counts.scan([tmp], rules)
        return bool(cands)
    except (OSError, ValueError):
        return False
    finally:
        _sh.rmtree(tmp, ignore_errors=True)


def scan_fingerprint(path, pattern_id):
    """返回该文件在指定模式下的**候选指纹**（稳定、可比较）；扫描失败返回 None。

    指纹取「候选的 行号+签名+代码」集合，而非完整 JSON——完整 JSON 含绝对路径
    （原文件与临时副本路径不同），直接比会永远不相等，把一切都判成「抓到了」。
    """
    scan = os.path.join(ROOT, "scripts", "scan_fp.py")
    rows = []
    ok = False
    for extra in ([], ["--absence"]):
        try:
            r = subprocess.run(
                [sys.executable, scan, path, "--only", pattern_id,
                 "--format", "json"] + extra,
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=90)
        except (OSError, subprocess.SubprocessError):
            continue
        ok = True
        try:
            data = json.loads(r.stdout)
        except (ValueError, TypeError):
            # absence 模式输出的是文本，退化为去空白比对
            rows.append("ABS:" + re.sub(r"\s+", " ", r.stdout.strip()))
            continue
        for c in data.get("candidates") or []:
            rows.append("%s|%s|%s" % (c.get("line"), c.get("signature"),
                                      (c.get("code") or "").strip()))
    if not ok:
        return None
    return "\n".join(sorted(rows))


def summarize(results):
    """分层统计。**不要把它们合并成一个 kill rate**——那会把层级错配算成判据缺陷。

    返回 dict：
      static_kill    —— static tier 且 expect_catch 的 kill rate，衡量签名体系强弱（改进目标）
      dynamic_gap    —— dynamic tier 的「静态抓不到」比例。这是层级事实，不是缺陷
      known_miss     —— 显式 expect_catch=False 的条数（正则能力边界）
      static_detail / dynamic_detail —— 明细，供报告逐条列出
    """
    ran = [r for r in results if r["injected"] > 0]
    static_up = [r for r in ran if tier_of(r) == "static" and r.get("expect_catch")]
    static_nm = [r for r in ran if tier_of(r) == "static" and not r.get("expect_catch")]
    dyn_all = [r for r in ran if tier_of(r) == "dynamic"]

    sk = sum(r["killed"] for r in static_up)
    ss = sum(r["survived"] for r in static_up)
    s_total = sk + ss
    static_kill = (100.0 * sk / s_total) if s_total else None

    dk = sum(r["killed"] for r in dyn_all)
    ds = sum(r["survived"] for r in dyn_all)
    d_total = dk + ds
    dynamic_gap = (100.0 * ds / d_total) if d_total else None

    return {
        "static_kill": static_kill,
        "static_killed": sk, "static_survived": ss, "static_total": s_total,
        "static_up": static_up, "static_known_miss": static_nm,
        "dynamic_gap": dynamic_gap,
        "dynamic_killed": dk, "dynamic_survived": ds, "dynamic_total": d_total,
        "dynamic_detail": dyn_all,
        "known_miss": len(static_nm),
        "ran": len(ran),
    }


def self_test():
    """验证：注入→检出→回滚 三件事都成立，且不碰真实仓。"""
    ok = True
    # 1) 变异算子库结构合法
    for m in MUTATORS:
        for key in ("id", "name", "from_pattern", "detector", "expect_catch",
                    "detectable_by"):
            if key not in m:
                print("[FAIL] 变异 %s 缺字段 %s" % (m.get("id"), key))
                ok = False
        # detectable_by 必须是词表内值；缺失会静默按 dynamic 处理，分层就失真了
        if m.get("detectable_by") not in DETECT_TIERS:
            print("[FAIL] 变异 %s 的 detectable_by=%r 不在 %s 内"
                  % (m.get("id"), m.get("detectable_by"), DETECT_TIERS))
            ok = False
        # expect_catch=False 必须写 observed_gap 说明「为什么抓不到」——
        # 不写就会变成「悄悄标成已知漏来美化 kill rate」
        if not m.get("expect_catch") and not str(m.get("observed_gap") or "").strip():
            print("[FAIL] 变异 %s 标了 expect_catch=False 但没写 observed_gap"
                  % m.get("id"))
            ok = False
    n_static = sum(1 for m in MUTATORS if tier_of(m) == "static")
    print("[%s] 变异算子库结构：%d 条（static %d / dynamic %d）"
          % ("PASS" if ok else "FAIL", len(MUTATORS), n_static,
             len(MUTATORS) - n_static))

    # 2) 每个可注入变异至少能改一段构造样本
    # 样本要覆盖每类注入点的真实代码形状，否则「注入器可作用」这条自检形同虚设。
    sample = (
        "int i = 0;\n"
        "for (int j = 0; j < 10; j++) {}\n"
        "if (p == nullptr) return;\n"
        "PipeBarrier<PIPE_V>();\n"
        "auto v = static_cast<int32_t>(total);\n"
        ".ATTR(axis, Int, 0)\n"
        "SetBlockDim(48);\n"
        "AscendC::SetAtomicAdd<float>();\n"
        "AscendC::SetScheduleMode(1);\n"
        "AscendC::CrossCoreSetFlag<0x2, PIPE_MTE3>(0x8);\n"
        "REGISTER_TILING_TEMPLATE(\"op\", OpTiling, 1);\n"
        "bool OpTiling::IsCapable()\n{\n    return true;\n}\n"
        "auto attr = GetAttrPointer<int64_t>(0);\n"
        "return workspaceSize;\n"
        "CHECK_RET(x != nullptr, ACLNN_ERR_PARAM_NULLPTR);\n"
        "DataCopyPad(dst, src, params);\n"
        "if (GetSocVersion() == SOC_VERSION_ASCEND910B) {}\n"
    )
    hit = 0
    for m in MUTATORS:
        new, n = apply_mutator(m, sample)
        if n > 0:
            hit += 1
    print("[%s] 注入器可作用于构造样本：%d/%d 条命中"
          % ("PASS" if hit >= 5 else "FAIL", hit, len(MUTATORS)))
    if hit < 5:
        ok = False

    # 3) 回滚：写临时文件 → 变异 → 读回 → 确认原文件未变
    #    注意：不能写死 MUTATORS[0]——M01 匹配 `<=`，而样本里没有 `<=`，注入数会是 0，
    #    自检就会误报「变异未生效」。这里挑「第一个在本样本上真能命中」的变异。
    tmp = tempfile.mkdtemp(prefix="muts_")
    try:
        target = None
        for m in MUTATORS:
            _new, _n = apply_mutator(m, sample)
            if _n > 0:
                target = m
                break
        if target is None:
            print("[FAIL] 回滚测试：没有任何变异能作用于构造样本")
            ok = False
        else:
            f = os.path.join(tmp, "a.cpp")
            write(f, sample)
            before = read(f)
            new, n = apply_mutator(target, before)
            if n == 0:
                print("[FAIL] 回滚测试：%s 变异未生效" % target["id"])
                ok = False
            else:
                after = read(f)
                same = after == before
                print("[%s] 回滚：%s 注入 %d 处；写回前原文件未被改动"
                      % ("PASS" if same else "FAIL", target["id"], n))
                ok = ok and same
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="变异测试：量化检视手段的 kill rate")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--run", action="store_true", help="在 --repos 上实跑")
    ap.add_argument("--repos", default="")
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--min-kill", type=float, default=None,
                    help="kill rate 低于此值即失败")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="逐例打印差分详情")
    args = ap.parse_args(argv)

    if args.list:
        for m in MUTATORS:
            flag = "可抓" if m.get("expect_catch") else "已知漏"
            print("[%s][%s] %-4s %-28s <- %s" %
                  ("X" if m.get("expect_catch") else " ", flag, m["id"], m["name"],
                   m["from_pattern"]))
        return 0
    if args.self_test:
        return self_test()
    if not args.run:
        ap.print_help()
        return 2
    if not args.repos or not os.path.isdir(args.repos):
        print("[ERROR] --repos 必须是存在的算子仓父目录")
        return 2

    global VERBOSE
    VERBOSE = args.verbose
    results = run_on_corpus(args.repos, sample_limit=args.sample)
    st = summarize(results)

    print("%-4s %-30s %-9s %-8s %5s %5s" %
          ("id", "变异", "模式", "层级", "注入", "抓住"))
    for r in results:
        if r["injected"] == 0:
            continue
        flag = "" if r.get("expect_catch") else "[已知漏]"
        print("%-4s %-30s %-9s %-8s %5d %5d %s"
              % (r["id"], r["name"][:28], r["from_pattern"],
                 tier_of(r), r["injected"], r["killed"], flag))
    print("-" * 74)

    if st["static_kill"] is not None:
        print("[STATIC ] 形态层 kill rate **%.1f%%**（注入 %d｜抓住 %d｜存活 %d）"
              " ← 这是衡量签名体系的真指标"
              % (st["static_kill"], st["static_total"], st["static_killed"],
                 st["static_survived"]))
        if st["static_known_miss"]:
            print("           已知漏检 %d 类（不计入）：%s"
                  % (len(st["static_known_miss"]),
                     "、".join(r["id"] for r in st["static_known_miss"])))
    else:
        print("[STATIC ] 本次无 static 层样本可注入（语料未命中）")

    if st["dynamic_gap"] is not None:
        print("[DYNAMIC] 语义层：注入 %d，静态抓不到 %d（%.1f%%）"
              "——**这是层级事实，不是判据缺陷**，必须上板实测"
              % (st["dynamic_total"], st["dynamic_survived"], st["dynamic_gap"]))
        miss_ids = [r["id"] for r in st["dynamic_detail"] if r["survived"] > 0]
        if miss_ids:
            print("           未抓到：%s" % "、".join(miss_ids))

    print("[NOTE   ] 两个数**不可合并**：static 低=签名弱（要修）；"
          "dynamic 高=该上板（本来就抓不到）")

    if args.json:
        print(json.dumps({
            "results": results,
            "static_kill_rate": st["static_kill"],
            "static_total": st["static_total"],
            "dynamic_gap_rate": st["dynamic_gap"],
            "dynamic_total": st["dynamic_total"],
            "known_miss": st["known_miss"],
        }, ensure_ascii=False, indent=2))
    if args.min_kill is not None:
        # 阈值只对 static 层生效：dynamic 层永远抓不到，拿它卡阈值毫无意义
        if st["static_kill"] is not None and st["static_kill"] < args.min_kill:
            print("[FAIL] static kill rate %.1f%% < 阈值 %.1f%%"
                  % (st["static_kill"], args.min_kill))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
