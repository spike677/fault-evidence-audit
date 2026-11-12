"""Offline HTML overlay; no external scripts, telemetry or live requests."""
import json
import rc128_revision as r2

JS=r'''
const auditById=new Map(D.field_audits.map(a=>[a.task_id,a]));
const resourceById=new Map(D.resource_audit.map(a=>[a.resource_id,a]));
const statusNames={CODE_REVIEWED_WEEKLY_IDENTITY_UNCONFIRMED:'已读代码：原事件身份待核',SOURCE_BODY_REVIEWED_ROOT_UNCONFIRMED:'已读正文：原根因待核',CANDIDATES_INDEX_ONLY:'仅候选标题/索引，未选中正文',BOUNDED_SEARCH_NO_MATCH:'限域查询无匹配',INPUT_IDENTITY_GAP_WITH_EXPLORATORY_SEARCH:'输入身份缺口：已作探索查询',SOURCE_DESCRIPTION_DIFF_CONFLICT:'正文与Diff冲突',CONTRACT_SOURCE_REVIEWED_DEPLOYMENT_UNCONFIRMED:'契约源码已读：现场调用待核'};
function auditLink(file,label){if(!file||!(/^(evidence|receipts|collection|sources|history)\//.test(file))||file.includes('..')||/[<>"\\]/.test(file))return esc(label||file||'');return '<a href="'+esc(file)+'" target="_blank" rel="noopener">'+esc(label||file)+'</a>'}
function fieldQuote(e){return '<details><summary>精确选段 · '+esc(e.evidence_id)+' · L'+e.line_start+'–'+e.line_end+'</summary><blockquote><pre>'+esc(e.quote)+'</pre></blockquote><p>'+auditLink(e.file,'归档代码/原文')+' · SHA256 '+esc(e.sha256)+'</p><p>选段范围：'+e.char_start+'–'+e.char_end+'；不是完整函数审读。</p></details>'}
function findingCard(f){return '<section class="line"><h4>'+esc(f.finding_id)+'</h4>'+tags([f.basis,f.entity_type])+'<p><b>代码事实：</b>'+esc(f.finding)+'</p><p><b>具体关系：</b>'+esc(f.failed_or_required_relation)+'</p><p><b>与原30边界：</b>'+esc(f.original30_boundary)+'</p><p>'+link(f.url,'官方PR')+' · '+esc(f.source_read_scope)+'</p>'+D.field_excerpts.filter(e=>f.evidence_ids.includes(e.evidence_id)).map(fieldQuote).join('')+'<p class="danger">公开技术观察；原周报事件、历史根因及硬件结果未确认，不自动入库。</p></section>'}
function resourceCard(r){return '<article class="card"><h3>'+esc(r.resource_id)+' · '+esc(r.title||r.url)+'</h3>'+tags([r.kind,r.body_capture||r.capture_status,r.origin])+'<p>'+link(r.url,'官方来源')+' · '+tags(r.task_ids)+'</p><p><b>实际审读范围：</b>'+esc(r.diff_read_scope||r.review_scope||r.body_semantics_reviewed||'见选段转录')+'</p><p>抓取到完整材料与完成全部语义审读分别计量。附件未读、未做设备执行。</p>'+(r.body_transcript?'<blockquote>'+esc(r.body_transcript)+'</blockquote>':'')+(r.notes?'<pre>'+esc(fmt(r.notes))+'</pre>':'')+'<div>'+auditLink(r.receipt,'原始回执 / Side选段转录')+' '+auditLink(r.body_file,'API完整正文')+' '+auditLink(r.raw_diff||r.file,'原始Diff / 来源文件')+' '+auditLink(r.email_patch,'Email Patch')+'</div>'+(r.reviewed_patches||[]).map(p=>'<p>'+auditLink(p.file,p.filename)+' · 完整已返回hunk，非完整函数</p>').join('')+'<details><summary>文件覆盖、commit、读取方式及尝试历史</summary><pre>'+esc(fmt(r))+'</pre></details></article>'}
function auditPanel(a){const rels=D.evidence_relations.filter(e=>e.task_id===a.task_id);return '<div class="panel current-audit"><h4>R3 本轮实际核验</h4>'+tags([statusNames[a.processing_status],a.processing_status])+'<p><b>当前结论：</b>'+esc(a.assessment)+'</p><p class="danger"><b>仍缺：</b>'+esc(a.remaining_gaps.join('；'))+'</p><p>同一事件：UNDETERMINED；根因层级：'+esc(a.root_evidence_status)+'。不自动入库。</p><details><summary>实际搜索 '+a.actual_search_ids.length+' 次查询 · '+a.repositories_searched.length+' 个范围</summary><pre>'+esc(fmt({query_ids:a.actual_search_ids,repositories:a.repositories_searched,outcomes:a.search_outcomes}))+'</pre><p>可在“逐项搜索台账”按 '+esc(a.task_id)+' 查看每个查询、回执与分页；无匹配仅限实际查询。</p></details><details><summary>逐资料关联与正文/Diff读取范围（'+rels.length+'）</summary>'+rels.map(e=>{const r=resourceById.get(e.resource_id);return '<section class="line"><p>'+link(e.url,e.resource_id)+'</p>'+tags([e.source_relation,e.event_relation,e.mechanism_relation,e.support_status])+'<p>'+esc(e.reason)+'</p><p>审读：'+esc(e.code_evidence_scope||r.review_scope||r.body_semantics_reviewed||'见来源转录')+'</p>'+auditLink(r.receipt,'回执')+' '+auditLink(r.raw_diff||r.body_file||r.file,'最强归档证据')+'</section>'}).join('')+'</details>'+D.public_findings.filter(f=>f.task_ids.includes(a.task_id)).map(findingCard).join('')+'<p class="muted">内网材料：仅沿用转交摘要，没有新读Wiki/DTS正文。R2四问深度：'+esc(a.four_question_review_scope)+'。</p></div>'}
const beforeFieldCase=caseCard;caseCard=function(r){const h=beforeFieldCase(r),cut=h.indexOf('</h3>')+5,last=h.lastIndexOf('</article>');return h.slice(0,cut)+auditPanel(auditById.get(r.task_id))+'<details><summary>展开R2原分析、原输入、42/V4及原30对照（旧读取状态只作历史）</summary>'+h.slice(cut,last)+'</details>'+h.slice(last)};
const beforeFieldSelect=selectRows;selectRows=function(q='',a='',g='',m=''){const key=q.toLowerCase().trim(),exact=/^rc-\d{3}$/.test(key),status=$('audit-status').value;return beforeFieldSelect('',a,g,m).filter(r=>(!status||auditById.get(r.task_id).processing_status===status)&&(!key||(exact?r.task_id.toLowerCase()===key:JSON.stringify([r,D.evidence_relations.filter(e=>e.task_id===r.task_id),D.public_findings.filter(f=>f.task_ids.includes(r.task_id))]).toLowerCase().includes(key))))};
function queryCard(q){return '<article class="card"><h3>'+esc(q.query_id)+' · '+esc(q.query)+'</h3>'+tags([q.outcome,q.origin,q.resource_type,...q.task_ids])+'<p><b>仓库范围：</b>'+esc(q.repository)+'</p><pre>'+esc(fmt({rounds:q.evidence_cycle_by_task,filters:q.filters,pages_observed:q.pages_observed,result_scope:q.result_scope}))+'</pre><p>'+auditLink(q.receipt,'原始工具回执 / Side逐页转录')+'</p><details><summary>返回候选（仅标题/索引，不代表正文已读）</summary>'+(q.candidates||[]).map(c=>typeof c==='string'?'<p>'+link(c,c)+'</p>':'<p>'+link(c.url,c.title||c.url)+' · '+esc(c.review_scope||'索引候选')+'</p>').join('')+'</details></article>'}
const beforeFieldView=renderView;renderView=function(v,q=''){
 const hit=x=>!q||JSON.stringify(x).toLowerCase().includes(q.toLowerCase());
 if(v==='search-audit')return '<div class="panel"><h2>逐项搜索台账</h2><p>每条查询保留仓库、Issue/PR范围、原词、状态、轮次及工具回执。分页不重复计数；镜像仓空结果不表示GitCode无记录；置顶路线图不计匹配。</p></div>'+D.search_audit.filter(hit).map(queryCard).join('');
 if(v==='resources')return '<div class="panel"><h2>正文、Issue、PR与Diff审读</h2><p>同URL只一项，保留所有引用；完整下载与实际审读范围分开。此前Web受阻而本轮Side成功的资源保留尝试历史。</p></div>'+D.resource_audit.filter(hit).map(resourceCard).join('');
 if(v==='public-findings')return '<div class="panel"><h2>公开代码支持的具体关系</h2><p>这些是独立公开技术观察。未确认周报事件身份，未决定新增或扩展；同一PR多个改动不算多份独立验证。</p></div>'+D.public_findings.filter(hit).map(f=>'<article class="card">'+tags(f.task_ids)+findingCard(f)+'</article>').join('');
 if(v==='summary')return '<article class="card"><h2>统计口径与限制</h2><pre>'+esc(fmt(D.summary.field_audit))+'</pre><p>128条均有实际查询或原链接审读、结果和缺口。只有列出的资源完成注明范围审读，其余仍是索引候选或限域无匹配，不声称128条根因已证实。</p><p>实际搜索、原事件确认、机理关系、模式采纳、实机验证是独立指标。数目有重叠，不能相加当故障数量。</p><details><summary>已验证官方来源与元数据受阻</summary><pre>'+esc(fmt({verified:D.repository_registry,unavailable:D.unavailable_repository_metadata}))+'</pre></details><details><summary>R1/R2历史统计，仅供追溯</summary><pre>'+esc(fmt(D.summary))+'</pre></details></article>';
 if(v==='evidence')return D.field_excerpts.filter(hit).map(e=>'<article class="card">'+fieldQuote(e)+'</article>').join('');
 return beforeFieldView(v,q);
};
VIEWS.splice(1,0,['search-audit','逐项搜索台账'],['resources','正文 / Issue / PR / Diff'],['public-findings','公开代码关系']);
VIEWS.find(x=>x[0]==='evidence')[1]='精确代码选段';
$('audit-status').innerHTML='<option value="">全部本轮核验状态</option>'+Object.entries(statusNames).map(([k,v])=>'<option value="'+k+'">'+v+'</option>').join('');
$('audit-status').addEventListener('change',draw);
'''


def render(folder,data):
    r2.render(folder,data)
    path=folder/'report.html';h=path.read_text(encoding='utf-8')
    h=h.replace('<title>128条修订版 · 六条逐驱动量四问 · 2026-11-12</title>',
        '<title>128条官方源逐项核验 · Side正文与代码审读 · 2026-11-12 R3</title>')
    h=h.replace('128条：证据核验、42/55与失效关系','128条：官方源检索、正文与代码关系核验 · R3')
    h=h.replace('本版复用前轮128条检索和证据，未重新搜索。六条完成逐驱动量审查（含未知）；3条仅纠正共享模板，119条沿用历史。原21个GitCode PR全文仍未取得。',
        '本轮128条均有逐条处理结论：优先读取原链接，在官方仓定向检索，Side实读选中正文与Diff。原21个GitCode PR均已取得原始Diff；实际语义审读限于注明文件/片段。其余候选未全部读正文，历史事件和根因不因此全部确认。')
    h=h.replace('<select id="action" ','<select id="audit-status" aria-label="本轮核验状态"></select><select id="action" ')
    h=h.replace('<b>本轮审查范围：</b>','<b>沿用R2关系审读深度：</b>')
    at=h.index("$('metrics').innerHTML=")
    h=h[:at]+JS+'\n'+h[at:]
    start=h.index("$('metrics').innerHTML=");end=h.index("for(const id of ['query'",start)
    h=h[:start]+"$('metrics').innerHTML=[['128','逐条处理结论'],[D.summary.field_audit.new_query_executions,'本轮实际新查询'],[D.summary.field_audit.resource_unique_urls,'唯一正文/代码来源'],['0','已确认历史事件 / 入库 / 设备执行']].map(([v,n])=>'<div class=\"metric\"><strong>'+v+'</strong>'+esc(n)+'</div>').join('');\n"+h[end:]
    # Reset the added filter together with existing controls, no remote request.
    h=h.replace("for(const id of ['query','action','group','mode'])$(id).value='';", "for(const id of ['query','action','group','mode','audit-status'])$(id).value='';")
    path.write_text(h,encoding='utf-8',newline='\n')


README='''# 128条官方源逐项核验 · 2026-11-12 R3

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
'''
