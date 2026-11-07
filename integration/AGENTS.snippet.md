## 故障证据核验

0.1.15可显式配置V4：31条件类、55唯一构造、64挂载、195指导案例分层计数；保留原42及修订42定义版本，映射只解释不传递适用/覆盖。按request.evaluation_order独立判断V4、修订42和Branch，再对照机理。输入/派生/上下文事实分开；I3可由普通shape/stride驱动但完整适用需公式/位宽/提升/边界单位/容量，C2/C4输入分派不能冒充API。后续trigger_design生成设计卡，E1-E5及跨流规程只作方案，execution_status=NOT_RUN、execution_implemented=false；实际执行另行验收。四种状态为语义适用、构造能力、路径覆盖、执行结果，能力受阻不能变不适用。新版本优先于以下历史说明。完整指令及实际能力仍以每份request为准。

0.1.14当前分类顺序：原记录/已有资料、独立摘要、condition_facts、完整42项及Branch2/3、机理明细、原模式对照、入库建议。42条件和6个已定义Branch叶是主框架，15类原模式只用于机理关联。描述applicability与证据relation分别判断，原文INT32偏移溢出可先1.3.2 PARTIAL，不等待网页证明才整理；未写出的Requires/Skip未知保留。每个确定谓词/标签绑定真实输入/API角色的局部condition_fact及原cell/当前资料子问题引文，内部Sparse/非确定性和中间Inf不冒充输入mask/API参数/输入Inf。版本不等于构建变体，Branch3完全适用必须有同实参同二进制依据；42未匹配不强塞Branch。训练同样分类，入库范围另判。已有证据不因未知补搜，原文分类不升级强MATCH、DIRECT、根因确认或正式新增。Init冻结条件索引，报告先条件后机理；新策略重发受影响请求，历史及人工记录保留。

0.1.12新增trigger-workflow：先init维护原CANN机制库×42类输入触发条件的历史证据覆盖索引，再classify新案例。Branch2实现实例（平台/SoC、编译选项/宏、构建变体）与Branch3执行情境（设备调度、流与异步、同步/竞态）单列，不计42。MODE_ENTRY不是故障事件，不虚构SAME_EVENT；每模式/每快照/每子问题用独立trigger_classify子Agent给出完整42项、完整谓词及引文。原始引用全部整理，缺Wiki必须先让Agent按原模式名/原因搜索Wiki；裸DTS/Wiki编号由Agent实际定位URL，不编URL。程序完成查重、派发、引用/范围/旧结果门禁与覆盖详情；子Agent负责摘要、语义关联、归类和一次自检。未知不等于未覆盖，42类未命中不证明新根因。Init覆盖详情是历史资料归类，不是注入/ATK执行覆盖。finalize冻结基线，增量分归入已有明细、扩充分支、新模式候选、待定；原源输入/策略变化需维护基线。复用audit.sqlite3和tasks请求/响应目录，最终只交付一个初始化覆盖XLSX或新案例分类XLSX；实际内网取证和登录仍由现场完成。

0.1.11默认使用xlsx-workflow整批推进，一次授权后不每10条申请继续。OpenChamber/OpenCode支持原生子agent和Agent搜索：主会话只调度ID/状态/路径，fault-audit-worker以新上下文完整读一项request、写独立response，语义并发2、Edge串行1；仅协调器提交SQLite。CLI适配器scripts/run_opencode_agent.py与原生子agent路线二选一，不同时控制同一run。实际服务/子agent工具权限、搜索和现有Edge登录态须现场预检，用户手动完成登录，同站点集中交接。Wiki仅标题/目录/未渲染不算完整正文；使用capture_observation及带原单元格依据的search_facets/search_attempts。正常来源/事实和库映射不例行要求ACCEPT，已有链接和工作复用不等于自动事件合并。最终仅交付一个排名XLSX；以下为兼容底层接口说明，不能覆盖本段Wiki优先和新默认入口。

相关任务通过 fault-evidence-audit Skill 调用独立 faultaudit 核心，实际状态以 SQLite 和 run ID 为准。
目标网站访问由具备授权与登录态的现场工具执行；模型任务可由OpenCode或Codex会话执行。核心仅导出任务、接收资料与结果并本地校验，不维护网站登录或远程客户端。
0.1.8核心处理导入、原文快照、证据计划、文件任务协议、本地校验、报告和只读统计；默认执行者为OpenCode，Codex使用model-tasks/submit-model-results --executor codex及run --mode codex，分别保留生产者身份。核心不配置模型服务地址、密钥或网络客户端。
先用--state <state> evidence-plan --run <id> --out preview.json只读预览（mode=ro/query_only，不建state）。整理全部已有原表/旧汇总引用和显式确认资料，不只选首份；同URL共享抓取/摘要但来历不合并。已有适用资料停止新增搜索，不取消其他已有引用；未选搜索候选和旧结果留档。
SOURCE_CELL_LINKED、LEGACY_TABLE_LINKED、SEARCH_DISCOVERED、PROVENANCE_PENDING保留来源等级，user_confirmed单列；确认旧表链接不使其成为原周报原链，legacy_relation只留历史。来源恢复先由Agent处理，不默认推成人工异常。不同issue范围按work_id隔离，同case/snapshot仍可有多个work；模型不改work标识，报告逐引用/逐子问题保留，统计不把展示行数当判断数量。
默认只需一份可用资料，无强制来源；已有Wiki/GitCode/GitHub/CodeHub或DTS任一可用资料即停止新增搜索，DTS不自动补证。已有未读/失败资料先处理，所有已有引用继续整理。显式set-search-policy的required_sources为AND、required_any_sources为OR，数量与来源都满足即停；case策略完整覆盖run，不能偷偷增加类型或伪造用户确认。search_control.satisfied只控制搜索，不等于根因/覆盖/整体完成。
OpenChamber连接的OpenCode可承担全部现场采集与模型执行；本包只做文件桥接，不启动Chamber或模型服务。doctor不证明真实登录、站点工具或DeepSeek联调；接入步骤见核心integration/OPENCODE_HANDOFF.md。
register-event-group、confirm-evidence为写入登记，仅将已有明确用户确认落到实际case_id并记录依据，不作为只读调用，不重复索要已有确认。事件组不合并原始case；同技术输入可共享工作，不同根因/场景继续各自判断并保留冲突。
使用model-tasks发布依赖就绪请求，由OpenCode按instructions/payload/expected_contract执行，再用submit-model-results提交保留原run/task/request hash的结果及实际producer元数据。run --mode opencode推进摘要、逐关联和全库阶段，任务空时仍检查受阻状态。
指定DeepSeek时确认实际provider/model；当前聊天或委派模型不同，不得声称已使用DeepSeek。当前桥接使用文件任务往返，不将其描述为已经直连OpenCode服务。
原始周报、旧汇总表、资料原文与模型建议分别保留。必要资料独立总结，按计划比较；同链接或同算子不能证明同事件。数字、术语、场景及技术结论逐项对比原字段/单元格/引文、证据片段和含义，指定多问题资料的applicable_issue并执行一次self_check；数字相同不等于含义一致。共享结果的原单元格始终属于代表source_case_id。
来源未知、部分读取、冲突和失败均可交付为明确待办，不补写不存在的证据。最终报告列输入、引用、采集、比较及待处理对账。
升级前暂停写入、备份现场state与请求/结果，优先以同state、明确的原run ID续跑；旧结果保留历史，过期结果不作当前支持。输入超限或无法完整处理时报告BLOCKED，不裁剪任务后提交；PARTIAL只描述真实采集缺口，仍保留已抓取全部正文。AUTO_PROCESSED/review_required=false/NOT_REQUIRED为普通自动处理，不伪造ACCEPT；PENDING/PENDING_AGENT由Agent完善，EXCEPTION/NEEDS_REVIEW交人工。真实现场与Python 3.14.3尚未验证。
仅做对账时只读既有SQLite/报告/基线/本轮清单，不触发导入、提交、复核或模型续跑。judgment_id、case_id、snapshot_id分别去重，current只计必要且非过期结果、REJECT口径显式；active摄取与selected快照另计，未选引用与自动/Agent待补/人工异常分别展示。一个共享judgment计一次，case数含member_case_ids；类别可交叉，缺基线的轮次变化为UNKNOWN。没有现场SQLite不猜真实总量，只有报告时限定其文件范围；现场数据保护沿用原流程。
纯JSON入口reconcile-report不初始化Store或打开SQLite；常规export可附统计但不是绝对只读。基线须同run完整report，manifest按完整差集核对；新历史项与current_new分开，new_case_count只指新增判断涉及case，pending_reason_entries只是待办理由条目。
current仅按输入报告导出时的is_stale和task状态，不重查今天数据库或新版策略；真实当前数需现场OpenCode先只读核对SQLite元数据，不把老报告当live DB验证。新导出由report_data按现policy标过期。
