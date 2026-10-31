---
name: fault-evidence-audit
description: "在OpenCode环境采集故障证据并执行faultaudit模型任务，逐份总结、逐关联判断，或只读核对判断数量与轮次增量。适用于周报、Wiki、DTS、代码证据及故障库映射，不用于普通Excel排版。"
---

# 故障证据核验

本 Skill 对应核心版本 0.1.5。通过 `scripts/run_audit.py` 调用本地核验核心。用核心的 `scripts/install_opencode.py --project <工作区>` 安装后，入口通过本地 `core-location.json` 定位核心，无需设置环境变量；同一磁盘优先保存相对路径，整个工作区与核心一起移动后仍可调用。跨磁盘安装保存本地绝对路径，迁移后可设置 FAULTAUDIT_HOME；如需重装，先保留并移走旧定位配置，安装器不会覆盖不同内容。可用 `FAULTAUDIT_HOME` 显式指定含 `run_faultaudit.py` 的核心目录，配置无效时直接报错，不回退到其他核心。核心只导入、保存快照、发布任务及运行本地门禁；本 Skill 的模型执行及内网采集在 OpenCode 环境完成。

DTS、Wiki、GitCode、GitHub、CodeHub 等目标网站访问统一由 OpenChamber 环境负责，使用其连接的 OpenCode 与现场工具执行。网站登录、搜索、正文/分页/附件/评论/Diff 读取及网络重试不进入 Codex 核心。`fetch-tasks` 仅导出清单，不能当作已经读取网页的证明。

当前使用文件任务往返，不假设核心已直连 OpenCode 服务。现场可以接 SDK 或使用已配置的模型委派能力，但需先验证该能力及其实际 provider/model。

本 Skill 默认执行 OpenCode 流程。核心另支持 Codex 会话，通过 `model-tasks/submit-model-results --executor codex` 和 `run --mode codex` 使用同一文件协议；Codex 的生产者使用 executor=codex 与 codex_version，不冒充 OpenCode 或 DeepSeek。精确模型/后台版本未知时明确标注 unreported。

## 操作

1. 运行核心 `doctor` 检查本地依赖；另在现场确认实际 OpenCode 服务版本、模型执行能力、采集工具及输入文件。OpenChamber 2.5.2 内置 2.1.4，不能仅凭 PATH 中 2.2.0 推定实际后端。
2. 导入原始周报或旧汇总表，明确 `--source-kind`。旧表根因默认来源未知。保存 run ID，后续会话继续该 run。
3. 导出 `fetch-tasks`。优先使用现场已有工具逐条读取，正文、评论、附件、Diff 的缺失分别登记。证据包字段见 [采集合同](references/collection.md)。
4. 用 `ingest-evidence` 提交实际内容。搜索补链标记来源和搜索词；原链抓取不改成搜索来源。不得用模型摘要冒充网页正文。
5. 用 `model-tasks --run <id> --out requests.json` 导出当前依赖就绪任务。按每项 `instructions`、`payload` 和 `expected_contract`，在 OpenCode 中执行模型任务。要求 DeepSeek 时，先确认实际执行模型；当前聊天或委派模型不是 DeepSeek，不得声称已使用 DeepSeek。
6. 将任务结果与原始 run/task/request hash、执行方元数据保存为 `results.json`，用 `submit-model-results --run <id> --file results.json` 回传，再用 `run --run <id> --mode opencode` 推进。结果协议见 [现场任务合同](references/collection.md)。
7. 重复导出、执行、提交、继续，依次完成摘要、逐关联及全库阶段。没有就绪任务时检查状态：可能完成，也可能等待采集、补充信息或处理失败，不将空清单当作成功证明。
8. 查看 `validate`、冲突、来源未知和失败任务。用 `export` 生成 JSON、HTML、TSV；XLSX 依赖可选 runtime。mock 仅演示流程，不提供真实核验结论。

升级时先暂停写入并备份整个现场 state 及原请求/结果，再使用原 state、原路径与明确的原 run ID 续跑、重新导出就绪任务。保留旧请求、结果与裁决历史，不为普通升级新建批次或改旧 Hash。真实现场和 Python 3.14.3 尚未验证，先用独立合成 state 核对环境。快照保存绝对路径，备份用于恢复原路径，本次不迁移 state 路径，不能直接在另一目录打开副本续跑。

## 关键约束

- 每份资料独立总结，再与每条引用记录比较。按具体章节和子问题关联，不以同模型、同算子或同链接合并故障。
- 原文根因、资料声明和模型推断分别保留；反证或拒绝关联保留，不删除整份资料。
- 引文必须属于本次保存的快照片段。缺版本、触发或事件身份时保持待判断。
- 全库映射需固定版本；检索未命中不能写未覆盖。同源转载不是多份独立证据。
- 模型结果是待复核建议。需要用户裁决的争议列入报告，不冒充已确认；不自动归并事件。
- 输入超限或 OpenCode 无法完整处理请求时报告 `BLOCKED`，保留原任务及原因；不能删减 payload、段落或库条目后当作完整结果提交。
- 查看请求 `input_budget` 的字符预算；核心超限会以 `INPUT_TOO_LARGE` 阻塞父任务。执行者容量不足只报告任务ID和原因，不提交伪造成功结果，也不自行构造blocked结果封装。
- 采集 `PARTIAL` 仍须保留已取得的全部正文，它只描述组件缺口；不能视为缺失全文，不能用该状态掩盖执行容量不足。
- 不在核心、任务文件或Skill中配置模型服务地址和密钥。生产者填写实际OpenCode版本、provider、model及会话；无法确认执行来源时列为缺口。
- 完成报告同时给出输入行数、链接数、比较数、失败与待处理数、run ID 和产物路径。所有任务执行成功也可能仍有语义待核验项。

若用户要求真实核验而缺少内网读取权限，应继续完成导入、清单和可执行任务，明确受阻项，不猜测页面内容。核心命令的完整用法在核心目录 README；这里不复制一份实现说明。

## 只读统计对账

只读对账时读取指定 run 的既有 SQLite、报告、基线和本轮清单，另存统计结果；不运行导入、证据或模型结果提交、人工裁决等写入流程。

优先以现场已有完整report JSON执行核心`reconcile-report --input <报告> --baseline <同run基线报告> --round-manifest <本轮清单> --out <统计文件>`。该命令不初始化Store或打开SQLite。常规export可附带统计参数，但不是对SQLite绝对只读的命令。

- judgment_id、case_id、snapshot_id 分别去重，明确统计单位；不拿案例数加减判断数。
- “当前有效”只按输入报告导出时的is_stale和task状态，离线工具不重查今天数据库或新版策略。真实当前数须先用现场工具只读核对SQLite元数据，不把老报告当live DB验证；新导出由report_data按现行策略标记过期。
- 当前记录排除过期项，明确是否包含 REJECT。拒绝关联保留历史，分类可交叉，类别加总不自动等于总数。
- 本轮增量须由基线报告和本轮清单核对；缺基线为 UNKNOWN，不用累计数代替。
- 清单使用run_id及judgment_ids、mapping_ids、snapshot_ids列表，也可用pipeline_task_ids代判断/映射列表；按完整差集核对。缺输入时轮次数量UNKNOWN/null，清单不一致则RECONCILIATION_FAILED/退出2。
- 新增历史记录与current_new分开；new_case_count只指新增判断涉及的case，pending_reason_entries是理由条目，不是独立故障或任务数。
- 没有现场 SQLite，不猜真实数量。若只有 JSON 报告，只说明其中记录与该文件口径，不冒称数据库全量对账。
- 复用现场既有网关和工具流程；网站访问、采集及实际模型执行仍由 OpenChamber/OpenCode 负责。
