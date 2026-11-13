# RC128 公开证据实际重审（2026-11-13）

主要阅读入口：[完整离线 HTML](report.html)。下载 ZIP 后解压打开 HTML，可以同时浏览每条记录、原30条定义、原文选段、固定版本代码及完整回执。

这次执行了新的公开查询和正文审读，没有使用 computer_use。先处理72条以前没有正文审读记录的条目，再复核剩余56条。原输入21个唯一 GitCode PR 已全部重新获取正文和 Diff/Patch。查询是有边界的，不宣称穷尽所有仓库或全部讨论。

## 本轮结果的含义

- `results.jsonl`：128个唯一原ID及原始输入，逐条新审读说明、诊断链、与原30条的建议和具体缺口。
- `public_findings.jsonl`：公开技术机理单独登记，不能当作新增客户事件或正式新增模式。
- `resource_audit.jsonl`：逐组件的URL、固定提交、正文/Diff/源码文件、SHA-256和实际已读字符范围。
- `search_audit.jsonl`：官方仓范围、查询词、轮次、返回候选及原始回执。查询记录含本轮跨记录复用，与独立网络请求数分开。
- `failure_relations.jsonl`、`mode_comparison.jsonl`：来源层诊断链、原30条比较及新取证说明。
- `summary.json`、`validation.json`：统一统计及一致性检查。
- `http/`、`github/`：实际取得的响应。抓到完整响应不代表审读了全文；未读组件明确标记。
- `inputs/`：原128条、原30条和原42/V4的冻结副本，以及明确标作历史的上轮分类结果。

完整数据的统计以 `summary.json` 为准。`PENDING` 是原30条模式归属仍待审，不是128条没有执行查询。原有7条覆盖、1条扩展和1条新增候选均只是受来源层级限制的建议；其余仍可保留机理线索。公开代码不能替代原记录的输入、路径和版本对照。

根因/证据层级、事件身份、模式建议、实机验证分别记录。正式入库、自动人工ACCEPT、现场drive、NPU/GPU执行均为0。原30条、42、V4、state和历史没有改写。

## 重要补证与纠偏

- RC-023：新检索得到官方 vllm-ascend [PR #10579](https://github.com/vllm-project/vllm-ascend/pull/10579)。补丁及修改前后固定源码确认A5不再统一对索引取绝对值；Base适配仍保留abs。它支持具体转换行为的对应，但槽位填充、掩码及NaN影响链仍未完整确认。原挂接的op-plugin #4833只支持梯度dtype问题。
- RC-010：opbase #279正文、完整返回Diff及固定构造函数共同支持取消TPipe后ctrl设置责任遗漏。寄存器编码含义、复位范围和原现场二进制仍待核。
- RC-029：#8005选段及固定代码说明scale读取索引和FlashUpdate传参变化；保留n2Idx的具体表达，不臆测前块/当前块或时间步。
- RC-031：#16674与#16699明确互引，修改前后源码可核对RoPE位置从UB读改为GM标量读。竞争阈值和设备复现为报告者声明，PR当前未合并；原事件仍未确认。
- MegaMoE、BOOL ReduceProd、RepeatInterleave大轴、测试Golden等独立修复，不再被当成原dequant、图像输入、反向dtype或RMSNorm生产修复。
- `EmbeddingDenseGradV2 #90`及MindSpeed-LLM #1734中的维护者反证保留，不能只采用最初的缺陷主张。

本文及HTML中的“完整Diff”指该URL的完整返回响应，并另做返回hunk长度校验，不表示所有文件均已语义审读，也不证明服务端绝无裁剪。折叠讨论、附件和未读文件不支持未读范围的结论。

## 可复现校验

在仓库根目录使用实际Python解释器：

```text
python scripts/rc128_actual_report.py build
node scripts/rc128_report_interactions.cjs reports/rc128-actual-rework-20261113
python -m unittest discover -s tests -p test_rc128_actual_rework.py -v
python scripts/rc128_actual_report.py verify
python scripts/rc128_actual_report.py package
```

`build`默认写入本独立目录，优先使用已经冻结的inputs，不覆盖旧包；实际网络采集由独立HTTP脚本及连接器完成，生成报告不会自动检索或运行模型/设备。

本轮新增11项针对性测试通过。实际提交 `c64acc5ee29caca25926774aa1aa669d43d75845` 的干净隔离树完整回归为998项通过，命令为 `python -m unittest discover -s tests -v`；日志与实际命令保存在 `commit_tree_test_results.txt`、`commit_tree_regression.json`。这次隔离运行不依赖未提交的实验脚本。当前开发工作区另有7项此前的未提交实验测试，连同它们运行时是1005项通过；该次记录另存于 `test_results.txt`，不混作发布树测试数量。实际解释器为Python 3.12.14，依赖版本见 `runtime_versions.json`。

交互检查直接执行报告生成的JS，对真实128条数据验证搜索、证据层级、模式交集、展开/收起和复位共9项。此为DOM测试框架检查，未声称浏览器渲染验收成功；无界面Edge尝试退出0但未取得DOM。

`history_integrity.json`按旧包原manifest只读核对563份文件，SHA-256全部一致，旧validation未被新版代码改写。
