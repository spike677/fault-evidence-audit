# 官方仓与Side：5条取证试跑

阅读入口：`report.html`。本轮是128条任务之前的小规模搜索路径验证，不是128条完成报告。

- RC-002：已有CANN PR原链接直读；Side下载的原始Diff和Email Patch在`evidence/side/`。
- RC-003、RC-009、RC-030、RC-111：比较候选搜索、无匹配范围、独立代码修复及API合同。
- `repository_policy.json`登记核实过的官方owner/repo；“仓库核实”与“实际搜索过”独立。
- `search_audit.jsonl`登记实际查询，`resource_audit.jsonl`说明实际读取范围。
- `pilot_results.jsonl`保存Agent逐条判断；不以关键词程序自动生成机理归类。
- `receipts/`包括工作区已有预检回执及本次新回执。搜索API返回正文，不等于Agent审读过全文。
- `side_observations.json`是实际浏览器观察的选段转录，不冒充完整DOM快照。
- 保留通用Web工具受阻历史；CANN #10622现已通过Side成功读取并下载，两者不冲突。
- 代码变更hunk完整不等于完整函数语义、客户事件确认或硬件验证。所有五条事件关系保持待定。

复建命令：

```powershell
python scripts/official_repo_pilot.py build
python -m unittest discover -s tests -p test_official_repo_pilot.py -v
node scripts/verify_official_repo_pilot_ui.cjs
python scripts/official_repo_pilot.py verify
python scripts/official_repo_pilot.py package
```

本轮未修改R1/R2归档、原30条定义、42/V4、现场state或人工历史；无自动ACCEPT、入库或设备测试。
