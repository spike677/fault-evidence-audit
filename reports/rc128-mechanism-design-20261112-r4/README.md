# 128条失效机理、稀疏条件及测试设计

主要入口：[完整离线HTML](report.html)。本包复用R3检索、正文、Diff和SHA，不声称重新搜索或设备复现。

128条记录，147个原记录子问题，11个独立公开代码子问题。
代表案例为 RC-002, RC-024, RC-029, RC-030, RC-031, RC-099, RC-122，先经过同策略pilot，再展开128条。原始输入与旧归档未改写。

当前分析：`mechanism_analyses.jsonl`；原记录：`results.jsonl`；原生卡：`design_cards.jsonl`；稀疏类别：`condition_relations.jsonl`；原30比较：`mode_comparison.jsonl`。
`history/r3/`为旧策略材料，不作为本轮重新确认；`source_corrections.json`保留本轮原文字段纠偏。

原42、V4类及55构造分别保留。具体构造提案见condition_notes；完整Requires/Skip未核清时类别保持PARTIAL或UNKNOWN，不把测试提案当成历史触发事实。
DESIGN_READY只指可继续实现的离线设计，不代表执行器已实现、路径已命中或设备通过。NEEDS_FACTS同样保留具体路径、判据及缺口。
所有归卡仍PENDING，无自动ACCEPT、正式入库、Baseline冻结或设备执行。内部Wiki/DTS仍为转交摘要。

复现（仓库根目录，Python3.12+及requirements）：
```
python scripts/rc128_mechanism_review.py pilot NEW_DIR --source-bundle reports/rc128-evidence-review-20261112-r3
python scripts/rc128_mechanism_review.py build NEW_DIR --source-bundle reports/rc128-evidence-review-20261112-r3
python scripts/rc128_mechanism_review.py verify reports/rc128-mechanism-design-20261112-r4
python scripts/rc128_mechanism_review.py verify reports/rc128-mechanism-design-20261112-r4 --git-index
python scripts/rc128_mechanism_review.py package reports/rc128-mechanism-design-20261112-r4
```
build拒绝已有manifest的输出目录；不操作现场run/state。预算160000检查包含指令、序列化输入、原30、两库全文及选段，超限标记BLOCKED，不截断。预算检查不证明Agent会话未发生上下文截断。
历史材料按旧manifest保留；代码升级只能新建归档，旧validation不重写。
