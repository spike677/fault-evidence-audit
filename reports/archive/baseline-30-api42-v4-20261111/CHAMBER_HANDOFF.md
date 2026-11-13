# OpenChamber：原30条资料续接

本包应用代码仍为0.1.20；报告为2026-11-11讨论更新版。原42、V4定义和旧记录均未改写，没有执行driver、模型、设备测试、人工ACCEPT或Baseline冻结。

## 先核对实际完成范围

|资料|本次交付|完成状态|
|---|---|---|
|30条数据Init|`original_init_and_sources.zip` 内 `init/cann_30_init.json`|30/30，`DATA_INITIALIZATION_ONLY`；不是已冻结的工作流Baseline|
|原30条API42/V4总结|`review_data.json`、README和完整HTML|30条逐条说明、62条稀疏关联、97项条件账本；证据层级和缺口保留|
|本机原30预检state|`legacy_original30_preflight.zip`|0.1.17，两个run各30个请求、0个完成结果；仅历史预检|
|旧冻结文件|本机找到，但未作为30条基线提交|对应15类INF模式，不可替代本包的30条|
|现场run `run-20261109T065009Z-37f05b15`|可读本机范围未找到|其数据库、任务历史和28份原始采集快照均不能从本包恢复|
|原`cann_modes.xlsx`|本机未找到|交付现有Markdown逐字段转录和历史`original_cann_30.json`，不能宣称已取得原工作簿|

本机查找覆盖可读C/D目录，部分系统目录无权限；目录清单和数据库run核对见 `local_init_search.json`。没有拿开发测试state冒充现场state。

ZIP内原文件按字节保留，SHA-256见 `archive_manifest.json`。旧回执中的`public_upload=false`等字段表示当时的历史状态，不能改写为本轮状态；本轮公开交付以本包manifest和验证回执为准。原文来源是现有已脱敏Markdown转录/摘要，不是28份原网页快照。

## 在其他机器读取

1. 检出GitHub分支`codex/investigation-plan`，先运行本包的只读verify命令，核对压缩包及文件SHA。
2. 把两份ZIP分别解压到新的资料目录。保留压缩包，不覆盖任何已有state。
3. 将`original_init_and_sources.zip`中的两份来源Markdown、来源注册表、证据台账、原42/V4文件和数据Init作为Agent可读取的已有资料。用本包逐条报告作为分类导航；不要重新抽取全部30条或生成30×42/55矩阵。
4. 历史预检包包含旧绝对路径和旧策略请求。`review_data.json`中的`legacy_id_cross_reference`仅把原表顺序、`CANN-ORIG-*`和M编号对应起来，不是自动事件合并或正式模式映射。历史请求不能跨策略直接提交。

## 有现场原run时沿原run继续

保持driver/worker停止，先备份完整state和任务目录；若有WAL，使用一致性备份。确认现场实际源码版本、解释器、run_id及路径，然后只读检查：

```powershell
python run_faultaudit.py --version
python run_faultaudit.py --state STATE trigger-workflow recovery-plan --run run-20261109T065009Z-37f05b15
```

该现场run此前要求的160000预算，应从原run配置和历史请求核对。仅在它确实是原现场run、历史预算一致且尚未固定时，按现有恢复协议固定预算。不要把160000强加给本包0.1.17预检run，也不要把旧请求或JSON数据Init写成当前策略下的已接受结果。

代表记录先核对M006、M026、M004及一个有历史摘要支持的正常模式。通过后由现场已有OpenCode/子Agent执行链连续推进剩余30条范围，不再每10条申请继续。只把无法消解的冲突、真实输入缺失、预算或执行上下文限制单独报告。

A1–A5的当前有效状态、兼容复核和冻结前提以现场当前Validator为准。没有现场原state时，可以在资料层继续分类与补证；不能宣称已恢复旧run或已完成A1–A5。

## 三项讨论更新

- **原第2条／M006**：按用户指示暂记V4 `minus_one`。保留原记录“内部InferShape输出−1”的事实角色；合法输入标记、传播链及CANN 6.3 RC1 B060合入证据待确认。暂记不自动升级L2历史代表。
- **原第3条／M026**：保留现有对齐关联，继续补证。`32b`单位、dtype、元素数、合法输入契约和实际访问范围仍需确认；不能仅凭未对齐断言Kernel越界。
- **原第4条／M004**：用户补充MC2漏传`useBufferType`，AllGatherMatmul通过`SetSkipBufferWindowCopy`设置，HCCL读取并更新。先按缓冲区模式参数传播缺失整理，C4为待核对方向；不是已确认的Shape触发或低概率判断，原“偏移计算错误”声明保留。

已有引用优先整理；未知字段不要求凑齐Wiki/DTS/PR类型。分开来源关系、事件关联、机理支持和条件构造。一个Wiki的多个子问题不能混用根因；同条件不自动合并机理。

## 保留的边界

不自动ACCEPT，不自动正式入库，不自动冻结Baseline，不运行NPU/GPU测试。E1–E5是执行设计方法；没有设备记录时不得标运行覆盖。API42与V4独立，映射文件不自动转换标签。

重放与校验：

```sh
python scripts/render_baseline30_review.py verify reports/baseline-30-api42-v4-20261111
node scripts/verify_baseline30_ui.cjs reports/baseline-30-api42-v4-20261111
```
