# 128条官方源逐项核验 · 2026-11-12 R3

主要阅读入口是 report.html。离线完整HTML保留128条输入、逐条结论、实际检索台账、资源审读范围、代码选段、42/V4历史稀疏关系和原30条对照。

本轮只读官方/维护者仓及原链接；网页操作通过Side。GitHub API补存完整正文与已验证文件的补丁，GitCode原始Diff/Email Patch通过Side页面实际下载。collection内的Side材料明确是Agent对实际DOM的选段转录，不冒充完整页面快照。receipts保留工具原回执，evidence保留完整取得的文件。

128条有查询或原资料实读及明确缺口，并不代表所有候选正文读完或根因确认。原21个GitCode PR已取得Diff，不代表整个PR的所有函数和所有测试完成语义复审。部分大PR仅审注明文件/片段；完整下载、选段审读、来源声明和本机硬件验证独立。

公开技术案例、同机理讨论、周报事件身份分别记录；当前周报事件独立确认、自动ACCEPT、正式入库、NPU/GPU执行均为0。来源内作者的测试结果不是本机结果。未知不转成DIFFERENT_EVENT；读取受阻、限域无匹配、无关资料、材料不完整和输入身份缺口分别保留。

## 文件口径

- results.jsonl / field_audits.jsonl：128个唯一task_id的原输入、当前处置与缺口。
- search_audit.jsonl：本轮实际执行查询与试跑复用，分页合为一条查询，候选标题不是正文审读。
- resource_audit.jsonl：唯一URL、全部引用记录、Side/API方式、正文/补丁范围、版本和尝试历史。
- evidence_relations.jsonl：逐记录逐资源的来源、事件、机理、支持关系，不自动传递身份。
- public_findings.jsonl：有代码选段的独立公开技术观察，与历史根因分开。
- failure_relations.jsonl / mode_comparison.jsonl / condition_relations.jsonl：沿用R2稀疏分析并附本轮审读，未重新分类全部42/55；不新增覆盖或模式。
- driving_quantities.jsonl：R2六条22个驱动量四问仍为待核；新代码旁证不自动将所有未知填成已知。
- review_context.json / input_budget_receipts.json：完整指令、原记录、冻结知识库、注明范围选段的可复建输入包，160000字符预算；超限BLOCKED，不截断。不是生产模型提交日志，也不证明会话没截断。
- history/r2、evidence/pilot：历史材料原字节保留，旧读取受阻不冒充本轮Side也受阻。

## 重建、核验与打包

```powershell
python scripts/rc128_review.py build reports/rc128-evidence-review-20261112-r3 --source-bundle reports/rc128-evidence-review-20261112-r2 --field-audit
python scripts/rc128_review.py verify reports/rc128-evidence-review-20261112-r3
node scripts/verify_rc128_field_ui.cjs reports/rc128-evidence-review-20261112-r3
```

重建完全离线，复用本轮已保存的采集回执，不重新检索。必须明确独立输出和R2源目录，不默认覆盖R1/R2/试跑。原128 JSONL字节、原30、原42、V4、INVARIANTS及state和历史均不修改。

GitHub不能直接执行仓库中的HTML；下载ZIP解压打开report.html，可使用全部筛选和相对证据链接。摘要与内部Wiki/DTS正文缺口保持可见，不能据本报告声称内网全文已重新核验。
