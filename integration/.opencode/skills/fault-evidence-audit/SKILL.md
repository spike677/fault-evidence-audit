---
name: fault-evidence-audit
description: "在OpenCode环境按必要证据计划采集并执行faultaudit模型任务，提取事实、核对含义与事件组，或只读对账数量及轮次增量。适用于周报、Wiki、DTS、代码证据及故障库映射，不用于普通Excel排版。"
---

# 故障证据核验

本 Skill 对应核心版本 0.1.8。通过 `scripts/run_audit.py` 调用本地核验核心。用核心的 `scripts/install_opencode.py --project <工作区>` 安装后，入口通过本地 `core-location.json` 定位核心，无需设置环境变量；同一磁盘优先保存相对路径，整个工作区与核心一起移动后仍可调用。跨磁盘安装保存本地绝对路径，迁移后可设置 FAULTAUDIT_HOME；如需重装，先保留并移走旧定位配置，安装器不会覆盖不同内容。可用 `FAULTAUDIT_HOME` 显式指定含 `run_faultaudit.py` 的核心目录，配置无效时直接报错，不回退到其他核心。核心只导入、保存快照、规划证据、发布任务及运行本地门禁；本 Skill 的模型执行及内网采集在 OpenCode 环境完成。

DTS、Wiki、GitCode、GitHub、CodeHub 等目标网站访问统一由 OpenChamber 环境负责，使用其连接的 OpenCode 与现场工具执行。网站登录、搜索、正文/分页/附件/评论/Diff 读取及网络重试不进入 Codex 核心。`fetch-tasks` 仅导出清单，不能当作已经读取网页的证明。

当前使用文件任务往返，不假设核心已直连 OpenCode 服务。现场可以接 SDK 或使用已配置的模型委派能力，但需先验证该能力及其实际 provider/model。

OpenChamber可由其连接的OpenCode执行本Skill，替代Codex执行模型与采集步骤；本包不启动OpenChamber。安装、合成执行和现场验收分步命令见核心`integration/OPENCODE_HANDOFF.md`。doctor只检查本地依赖，不证明网站登录、工具权限或DeepSeek联调。

本 Skill 默认执行 OpenCode 流程。核心另支持 Codex 会话，通过 `model-tasks/submit-model-results --executor codex` 和 `run --mode codex` 使用同一文件协议；Codex 的生产者使用 executor=codex 与 codex_version，不冒充 OpenCode 或 DeepSeek。精确模型/后台版本未知时明确标注 unreported。

## 操作

1. 运行核心 `doctor` 检查本地依赖；另在现场确认实际 OpenCode 服务版本、模型执行能力、采集工具及输入文件。OpenChamber 2.5.2 可能连接内置 OpenCode 2.1.4，不能仅凭 PATH 中 2.2.0 推定实际后端。
2. 导入原始周报或旧汇总表，明确 `--source-kind`。旧表根因默认来源未知。保存 run ID，后续会话继续该 run。
3. 先以 `--state <既有state> evidence-plan --run <id> --out preview.json` 只读预览，检查选定引用、必要动作与停止原因。该入口 SQLite mode=ro/query_only，不创建 state。只有已有关系确需登记时，才另行使用 `register-event-group` 或 `confirm-evidence` 写命令；已有用户确认直接按实际 case_id 登记，不重复索要确认，不凭同模型/同链接自行造组。
4. 每次新增搜索前重新读取计划：无适用证据时按`SEARCH`执行；显式条件未满足时按`SEARCH_SUPPORT`定向执行。只有`search_control.search_allowed=true`才调用搜索工具，一次取得候选后先保存、摘要和比较，再检查计划；`satisfied=true`立即停止新搜。已完成但支持不足的候选保留来历与缺口，不把同算子名或可读URL当成条件满足。
5. 导出 `fetch-tasks`，整理原表、旧汇总表和显式确认关系中的全部已有引用，不只取一份。相同URL可共享抓取/摘要，来历分别保留。已有适用内容就停止新增补链，这不取消其他已有引用的整理；不为填齐证据类型搜索。使用现场工具读取，正文、评论、附件、Diff 缺失分别登记。证据包字段见 [采集合同](references/collection.md)。
6. 用 `ingest-evidence` 提交实际内容。搜索补链标记来源和搜索词；原链抓取不改成搜索来源。不得用模型摘要冒充网页正文。
7. 用 `model-tasks --run <id> --out requests.json` 导出当前依赖就绪任务。按每项 `instructions`、`payload` 和 `expected_contract` 在 OpenCode 执行。对数字、术语、场景和技术结论填写原字段/单元格/引文、证据片段及各自含义；数字同值不能代替含义一致。多问题资料注明 applicable_issue，执行一次 self_check。指定 DeepSeek 时确认实际执行模型，不能将其他模型产物标为 DeepSeek。
8. 将任务结果与原始 run/task/request hash、执行方元数据保存为 `results.json`，用 `submit-model-results --run <id> --file results.json` 回传，再用 `run --run <id> --mode opencode` 推进。结果协议见 [现场任务合同](references/collection.md)。
9. 重复导出、执行、提交、继续，依次完成必要资料摘要、比较及全库阶段。没有就绪任务时检查状态：可能完成，也可能等待采集、Agent 补充或异常处理，不将空清单当作成功证明。
10. 查看 `validate` 与报告：正常 AUTO_PROCESSED 自动处理，不写人工 ACCEPT；PENDING 由 Agent 完善；EXCEPTION 交人工。用 `export` 生成 JSON、HTML、TSV，保留事实对照、事件组成员与根因冲突、未选引用及历史；XLSX 依赖可选 runtime。mock 不证明真实核验。

升级时先暂停写入并备份整个现场 state 及原请求/结果，再使用原 state、原路径与明确的原 run ID 续跑、重新导出就绪任务。保留旧请求、结果与裁决历史，不为普通升级新建批次或改旧 Hash。真实现场和 Python 3.14.3 尚未验证，先用独立合成 state 核对环境。快照保存绝对路径，备份用于恢复原路径，本次不迁移 state 路径，不能直接在另一目录打开副本续跑。

## 关键约束

- 每份必要资料独立总结，再与计划选定的来源记录比较。按具体章节和子问题关联，不以同模型、同算子或同链接合并故障；未选引用和判断留档，不增加必要任务或待办。
- 原文根因、资料声明和模型推断分别保留；反证或拒绝关联保留，不删除整份资料。
- 来源分级为SOURCE_CELL_LINKED/LEGACY_TABLE_LINKED/SEARCH_DISCOVERED/PROVENANCE_PENDING，user_confirmed是独立确认标记；旧表单元格可追溯也不升级为原始周报原链。来源待恢复由Agent先处理，不默认推成人工异常。legacy_relation仅留历史，不用于本版路由。
- 默认搜索策略min_usable_evidence=1、required_sources=[]、required_any_sources=[]；已有Wiki/GitCode/GitHub/CodeHub或DTS任一可用资料即停止新增搜索，DTS不自动补Wiki/代码。已有未读/失败资料先采集或处理真实缺口，其他已有引用仍整理。
- 默认没有适用证据时按计划搜索；已有资料后，只有额外显式数量或来源条件未满足且计划允许时才补搜。required_sources是AND、required_any_sources是OR，数量与两组约束共同满足即停。set-search-policy可设run默认或case完整覆盖；不能偷偷增加来源要求或伪造user_confirmed。search_control.satisfied不是根因确认、库覆盖或整体完成。
- 同case/snapshot的不同issue范围有不同work_id，按核心任务原封执行，不改work标识或把一份答案贴到其他issue。报告逐引用与逐资料子问题均保留，重复展示的共享结果不重复计判断。
- 引文必须属于本次保存的快照片段。缺版本、触发或事件身份时保持待判断。
- 全库映射需固定版本；检索未命中不能写未覆盖。同源转载不是多份独立证据。
- 普通门禁通过的结果为 AUTO_PROCESSED/review_required=false/NOT_REQUIRED，不要求例行人工 ACCEPT；缺事实为 PENDING/PENDING_AGENT，由 Agent 补充；冲突异常为 EXCEPTION/NEEDS_REVIEW，交人工。旧记录无这些字段时沿用旧复核口径，不能自动升级。
- 事件组只登记已有明确用户确认。相同技术输入共享一次工作和 judgment_id，原 case 不合并；不同根因或场景各自处理并在事件组结论保留冲突。事实对照的原单元格属于代表 source_case_id，不冒充其他成员原文。
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
- planned_work_count/current_work_count按work_id计，case-snapshot pair另列；validate的planned_associations/judged_associations在0.1.8为work口径，查看planned_work_ids/judged_work_ids。不因多个issue共享一份快照就折叠其工作，旧报告无work时该口径unknown。
- “当前有效”只按输入报告导出时的is_stale和task状态，离线工具不重查今天数据库或新版策略。真实当前数须先用现场工具只读核对SQLite元数据，不把老报告当live DB验证；新导出由report_data按现行策略标记过期。
- 当前判断和映射只计必要、非过期项，明确是否包含 REJECT；未选及拒绝关联保留历史。snapshot_count保留active摄取全集，selected_snapshot_count另计，未选引用与AUTO/PENDING/EXCEPTION分别展示。分类可交叉，类别加总不自动等于总数。
- 一个共享judgment_id计一次判断，涉及case数按case_id及member_case_ids去重；不因事件组把原始case数量合并。human_exception_count含已复核异常，pending_human_exception_count只计尚未人工ACCEPT/REJECT的异常。
- 本轮增量须由基线报告和本轮清单核对；缺基线为 UNKNOWN，不用累计数代替。
- 清单使用run_id及judgment_ids、mapping_ids、snapshot_ids列表，也可用pipeline_task_ids代判断/映射列表；按完整差集核对。缺输入时轮次数量UNKNOWN/null，清单不一致则RECONCILIATION_FAILED/退出2。
- 新增历史记录与current_new分开；new_case_count只指新增判断涉及的case，pending_reason_entries是理由条目，不是独立故障或任务数。
- 没有现场 SQLite，不猜真实数量。若只有 JSON 报告，只说明其中记录与该文件口径，不冒称数据库全量对账。
- 复用现场既有网关和工具流程；网站访问、采集及实际模型执行仍由 OpenChamber/OpenCode 负责。
