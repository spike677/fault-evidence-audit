# 128条修订版 · 2026-11-12

主要入口为 report.html；全部来源及最强可用选段随目录保留，可离线查看。

六条 RC-009、010、023、029、062、105 是待核关系分析＋暂定归卡讨论。
22个驱动量逐项记录Q1对象、Q2单位／编码／定义域、Q3创建／初始化／可写主体／复位、Q4消费者。
填写完整不代表关系证实，也不替代复现。六条新增与扩展决定全部待审。
RC-051、060、111以及TC-FP8-VSCALE、TC-SFAG-EVENT-ID仅纠正模板携带的断言；其余119条沿用历史。
原128输入字节、原30／42／V4定义、历史证据保持不变；未修改state或人工历史。

RC-029只有历史代码选段能定位参数替换；未核完整变量定义和调用合同。
其它五条根因目前主要来自转交声明／摘要，不能写作已独立证实。明确PR提示保留作定向补证，不重搜128条。
RC-062 N3／zeros为条件化来源层分类；不证明缺陷、恢复遗漏或新增模式。
semantic_applicability与construction_feasibility独立；Requires／Skip和每个挂载类别逐项保留。
旧模式建议的计数只表示历史草案，不能当成本版新增／扩展决策。

## 构建与核验

```powershell
python scripts/rc128_review.py build reports/rc128-evidence-review-20261112-r2 --source-bundle reports/rc128-evidence-review-20261111
python scripts/rc128_review.py verify reports/rc128-evidence-review-20261112-r2
python scripts/rc128_review.py verify reports/rc128-evidence-review-20261111
node scripts/verify_rc128_revision_ui.cjs reports/rc128-evidence-review-20261112-r2
```

build只允许独立输出目录，禁止写入旧归档。verify只读；旧包按原manifest核验并明确历史策略身份，不改旧validation。
history/r1保留原统计、策略及验证日志；source_revision.json记录源目录全部文件SHA和旧ZIP SHA。
整请求包含指令、原记录、原30定义、完整42／V4原文、分类定义以及本轮四问数据，预算160000字符。
超限标记BLOCKED／INPUT_TOO_LARGE，不截断；预算检查不证明执行会话未截断。本轮未调用生产模型桥接。

## 验证范围

test_results.txt、validation.json、ui_validation.json记录实际解释器／依赖和检查结果。
UI测试为离线Node VM逻辑检查，不冒充真实浏览器或设备执行。
本包无人工ACCEPT、Baseline冻结、正式入库或NPU／GPU测试。
