"""Standalone offline mechanism-report renderer; no inherited report template.

Public controls: query, basis, readiness, scheme, label, mode, reset, tabs,
metrics, count, content, payload. Public JS helpers are deliberately usable by
the offline Node VM checks: selectRows, renderView, caseCard, analysisCard,
setView, draw, esc, safeHref and link. The only output is report.html.
"""
from __future__ import annotations

import json
from pathlib import Path


CSS = r"""
:root{color-scheme:light;--ink:#142b3b;--muted:#536875;--line:#d9e2e8;--blue:#145b79;--pale:#edf5f8;--warn:#fff6df}
*{box-sizing:border-box}body{margin:0;background:#f4f7f9;color:var(--ink);font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif}
header{background:#12384c;color:#fff;padding:30px max(24px,calc((100vw - 1420px)/2))}header h1{font-size:27px;line-height:1.35;margin:0 0 12px}header p{max-width:1080px;margin:8px 0;color:#e2edf3}
main{max-width:1480px;margin:auto;padding:24px}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:20px}.metric{background:white;border:1px solid var(--line);border-radius:9px;padding:14px 18px;color:var(--muted)}.metric strong{font-size:28px;color:var(--blue);display:block;line-height:1.3}
.controls{display:flex;flex-wrap:wrap;align-items:end;gap:10px;background:white;border:1px solid var(--line);padding:16px;border-radius:9px}.controls label{display:flex;flex-direction:column;gap:4px;color:var(--muted);font-size:12px}.controls label:first-child{flex:1;min-width:220px}input,select,button{font:inherit;color:var(--ink);border:1px solid #b8cbd6;border-radius:5px;background:white;min-height:38px;padding:7px 10px}input{width:100%}select{max-width:225px}button{cursor:pointer}button:hover{background:var(--pale)}button.active{color:white;background:var(--blue);border-color:var(--blue)}
nav{display:flex;flex-wrap:wrap;gap:7px;margin:20px 0 10px}#count{color:var(--muted);margin:10px 0}h2{font-size:21px;margin:0 0 12px}h3{font-size:18px;margin:0 0 10px}h4{font-size:15px;margin:14px 0 6px}p{margin:8px 0}a{color:#076a99;overflow-wrap:anywhere}code{font-size:.9em;background:#edf2f5;padding:2px 4px;border-radius:3px}.muted{color:var(--muted);font-size:13px}.notice{background:var(--warn);border-left:4px solid #bc852b;padding:12px 16px;margin:14px 0}.panel,.card{background:white;border:1px solid var(--line);border-radius:8px;padding:20px;margin:14px 0}.analysis{border-left:4px solid var(--blue)}.line{border-top:1px solid var(--line);padding:12px 0}.tag{display:inline-block;background:var(--pale);border:1px solid #d1e1e9;border-radius:4px;padding:1px 6px;margin:2px 4px 2px 0;font-size:12px;overflow-wrap:anywhere}.unknown{background:var(--warn);border-color:#e6d39d}
.scroll{overflow:auto;max-width:100%}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:10px;border:1px solid var(--line);vertical-align:top;text-align:left;overflow-wrap:anywhere}th{background:var(--pale);font-weight:600}.case-table{min-width:1000px;table-layout:fixed}.case-table th:first-child{width:100px}.case-table th:nth-child(2){width:240px}.case-table th:nth-child(3){width:210px}.case-table th:nth-child(4){width:200px}.case-table td{background:white}.case-table details[open]{min-width:650px}.case-detail{max-width:1050px}.case-detail .card{margin:10px 0}.four{table-layout:fixed;min-width:600px}.four th{width:25%}summary{cursor:pointer;color:var(--blue);font-weight:600}details{margin:8px 0}details>summary{padding:5px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:8px 0;font:12px/1.6 Consolas,monospace;background:#f3f6f8;padding:12px;border-radius:5px;max-height:440px;overflow:auto}blockquote{margin:12px 0;padding:6px 14px;border-left:3px solid #91b5c7;background:#f7fafb}ul,ol{padding-left:22px;margin:8px 0}.empty{padding:40px;text-align:center;color:var(--muted)}.sequence{display:grid;grid-template-columns:150px 1fr;gap:5px 15px;margin:12px 0}.sequence dt{font-weight:600;color:var(--muted)}.sequence dd{margin:0;overflow-wrap:anywhere}footer{color:var(--muted);font-size:12px;padding:20px 0}
@media(max-width:850px){main{padding:14px}header{padding:24px 18px}.metrics{grid-template-columns:repeat(2,1fr)}.metric strong{font-size:23px}.controls label{flex:1;min-width:145px}select{max-width:100%}.sequence{grid-template-columns:1fr}.sequence dd{margin-bottom:8px}.card,.panel{padding:14px}}@media print{header{background:white;color:black}header p{color:#333}.controls,nav{display:none}main{max-width:none}.scroll,pre{overflow:visible;max-height:none}details{break-inside:avoid}.metrics{grid-template-columns:repeat(4,1fr)}}
"""


JS = r"""
function $(id){return document.getElementById(id)}
const D=JSON.parse($('payload').textContent);
for(const key of ['results','analyses','definitions','quotes','excerpts','resources','searches','baseline30','public_findings','evidence_relations','corrections'])if(!Array.isArray(D[key]))D[key]=[];
function fmt(value){return typeof value==='string'?value:JSON.stringify(value===undefined?null:value,null,2)}
function esc(value){return String(value===undefined||value===null?'':value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function safeHref(value){
 if(typeof value!=='string'||!value||/[\u0000-\u0020<>"'\\]/.test(value))return '';
 if(/^https?:\/\//i.test(value)){try{const u=new URL(value);return /^(https?:)$/.test(u.protocol)&&!u.username&&!u.password?u.href:''}catch(e){return ''}}
 if(value.startsWith('#'))return /^#[A-Za-z0-9_.:%-]+$/.test(value)?value:'';
 let decoded;try{decoded=decodeURIComponent(value)}catch(e){return ''}
 if(/[\u0000-\u001f<>"'\\:?#]/.test(decoded)||decoded.startsWith('/')||decoded.split('/').some(p=>p==='.'||p==='..'||p===''))return '';
 return /^[A-Za-z0-9_][A-Za-z0-9_./% -]*$/.test(value)?value:'';
}
function link(url,label){const href=safeHref(url);return href?'<a href="'+esc(href)+'" target="_blank" rel="noopener noreferrer">'+esc(label||url)+'</a>':esc(label||url||'')}
function tags(values){return (Array.isArray(values)?values:[values]).filter(v=>v!==undefined&&v!==null&&v!=='').map(v=>'<span class="tag'+(/UNKNOWN|NEEDS_FACTS|PENDING|未|待/.test(String(v))?' unknown':'')+'">'+esc(v)+'</span>').join('')}
function list(values){return Array.isArray(values)&&values.length?'<ul>'+values.map(v=>'<li>'+esc(fmt(v))+'</li>').join('')+'</ul>':'<p class="muted">未列出</p>'}
function pretty(value){return '<pre>'+esc(fmt(value))+'</pre>'}
function text(value,fallback='未提供，保持未知'){return value===undefined||value===null||value===''?fallback:fmt(value)}
function uniq(values){return [...new Set(values.filter(v=>v!==undefined&&v!==null&&v!==''))].sort()}
const analysisById=new Map(D.analyses.map(a=>[a.analysis_id,a]));
const evidenceById=new Map([...D.quotes,...D.excerpts].map(e=>[e.evidence_id||e.excerpt_id||e.id,e]));
const resourceById=new Map(D.resources.map(r=>[r.resource_id||r.id,r]));
function analysesFor(row){const ids=new Set(row.analysis_ids||[]);return D.analyses.filter(a=>ids.has(a.analysis_id)&&a.task_id===row.task_id)}
function hasTask(item,task){return item.task_id===task||(Array.isArray(item.task_ids)&&item.task_ids.includes(task))}
function findingsFor(task){return D.public_findings.filter(f=>hasTask(f,task))}
function relationsFor(task){return D.evidence_relations.filter(r=>hasTask(r,task))}
function sourceBases(a){return uniq((a.source_claims||[]).map(c=>c.basis))}
function mechanismBasis(a){return (a.mechanism_chain||{}).basis||(a.mechanism||{}).basis||''}
function bases(a){return uniq([...sourceBases(a),mechanismBasis(a)])}
function labelNames(a){return uniq((a.selected_labels||[]).map(l=>l.scheme+':'+l.trigger_id+' · '+l.semantic_applicability))}
function readiness(a){return uniq((a.design_cards||[]).map(c=>c.status))}
function analysisMatches(a,basis='',ready='',scheme='',label='',mode=''){
 return (!basis||bases(a).includes(basis))&&(!ready||readiness(a).includes(ready))&&
  (!scheme||(a.selected_labels||[]).some(l=>l.scheme===scheme&&(!label||l.trigger_id===label)))&&
  (!label||(a.selected_labels||[]).some(l=>l.trigger_id===label&&(!scheme||l.scheme===scheme)))&&
  (!mode||(a.mode_comparisons||[]).some(m=>m.mode_id===mode)||((a.mode_decision||{}).action===mode));
}
function selectRows(q='',basis='',ready='',scheme='',label='',mode=''){
 const key=String(q).trim().toLowerCase(),exact=/^rc-\d{3}$/.test(key);
 return D.results.filter(r=>{const aa=analysesFor(r);return (!key||(exact?String(r.task_id).toLowerCase()===key:JSON.stringify([r,aa,findingsFor(r.task_id),relationsFor(r.task_id)]).toLowerCase().includes(key)))&&
  (!(basis||ready||scheme||label||mode)||aa.some(a=>analysisMatches(a,basis,ready,scheme,label,mode)))});
}
function activeRows(){return selectRows($('query').value,$('basis').value,$('readiness').value,$('scheme').value,$('label').value,$('mode').value)}
function matching(value,q){return !String(q||'').trim()||JSON.stringify(value).toLowerCase().includes(String(q).trim().toLowerCase())}
function sourceLinks(value){
 const urls=[];function walk(v){if(typeof v==='string'){if(/^https?:\/\//i.test(v))urls.push(v)}else if(Array.isArray(v))v.forEach(walk);else if(v&&typeof v==='object')Object.values(v).forEach(walk)}walk(value);
 return uniq(urls).map(u=>link(u,u)).join(' · ');
}
function evidenceCard(e){
 const id=e.evidence_id||e.excerpt_id||e.id||'无ID';
 const location=[e.json_pointer,e.source_location,e.line_start?'L'+e.line_start+(e.line_end?'–'+e.line_end:''):''].filter(Boolean).join(' · ');
 return '<section class="line evidence"><h4>'+esc(id)+'</h4>'+tags([e.task_id,e.basis,e.entity_type])+'<p class="muted">'+esc(location)+'</p><blockquote><pre>'+esc(text(e.quote===undefined?e.text:e.quote))+'</pre></blockquote><p>'+link(e.file||e.source_file,'打开归档原文 / 代码')+' '+link(e.url||e.source_url,'打开原文 / PR')+'</p><p class="muted">'+esc(e.sha256?'SHA256 '+e.sha256:'')+'</p><details><summary>锚点、范围与来源元数据</summary>'+pretty(e)+'</details></section>';
}
function predicateTable(checks){
 return '<div class="scroll"><table><thead><tr><th>条款</th><th>完整定义 / Requires / Skip</th><th>检查</th><th>本分析事实</th></tr></thead><tbody>'+(checks||[]).map(c=>'<tr><td>'+esc(c.clause_role)+'</td><td>'+esc(c.clause)+'</td><td>'+tags(c.result)+'</td><td>'+tags(c.condition_fact_ids||[])+'</td></tr>').join('')+'</tbody></table></div>';
}
function conditionCard(l,a){
 const links=(a.label_links||[]).filter(x=>x.scheme===l.scheme&&x.trigger_id===l.trigger_id);
 const frozen=D.definitions.find(d=>d.scheme===l.scheme&&d.id===l.trigger_id&&d.definition_version===l.definition_version);
 return '<section class="line condition"><h4>'+esc(l.scheme+' / '+l.trigger_id)+'</h4>'+tags([l.definition_version,l.semantic_applicability])+
  '<p><b>语义分类：</b>'+esc(l.semantic_applicability)+'；<b>构造状态：</b>'+esc(text((l.construction_feasibility||{}).status))+' · '+esc(text((l.construction_feasibility||{}).reason))+'</p>'+
  (frozen?'<p><b>冻结定义：</b>'+esc(frozen.definition)+'</p>':'<p class="notice">未找到版本一致的冻结定义，保持缺口。</p>')+
  predicateTable(l.predicate_checks)+'<p class="muted">完整条款逐项保留；UNKNOWN表示未定。语义分类与构造能力分别记录。</p>'+
  (l.construction_checks||[]).map(c=>'<details><summary>构造码 '+esc(c.construction_id)+' · '+esc(c.applicability)+'</summary><p>'+esc(c.reason)+'</p>'+predicateTable([c.definition_check])+'<p>构造事实 '+tags(c.condition_fact_ids||[])+'</p><p>'+esc(text(c.construction_recipe))+'</p></details>').join('')+
  '<details><summary>本地 Scenario / LabelLink 与事实绑定</summary>'+pretty(links)+'<h4>条件事实</h4>'+pretty((a.condition_facts||[]).filter(f=>(l.condition_fact_ids||[]).includes(f.fact_id)))+'</details></section>';
}
function designCard(c){
 return '<section class="line design"><h4>'+esc(c.card_id)+'</h4>'+tags([c.status,c.execution_status,'execution_implemented='+String(c.execution_implemented),c.path_coverage])+
  '<p class="muted">assessment_id '+esc(c.assessment_id)+' · scenario_id '+esc(c.scenario_id||'无正向场景：待补事实')+'</p>'+
  '<dl class="sequence"><dt>目标路径</dt><dd>'+esc(c.target_path)+'</dd><dt>Reference</dt><dd>'+esc(c.reference)+'</dd></dl><h4>检查 / 可证伪判据</h4>'+list(c.checks)+
  '<details><summary>拟构造变量、边界与协议（设计值不是历史输入）</summary>'+pretty(c.variables||[])+'<p><b>边界</b></p>'+list(c.boundaries||[])+
  '<p><b>协议步骤</b></p>'+list(c.protocol_steps||[])+'<p><b>参与者及目标不变量</b></p>'+pretty({participants:c.participants||[],target_invariant:c.target_invariant||null,serial_baseline:c.serial_baseline,event_record:c.event_record,consumer_wait:c.consumer_wait})+'</details>'+
  '<h4>所需能力</h4>'+list(c.required_capabilities)+'<h4>能力缺口与未知</h4>'+list([...(c.capability_gaps||[]),...(c.unknowns||[])])+'</section>';
}
function readScopePanel(a){
 const scopes=Array.isArray(a.code_read_scopes)?a.code_read_scopes:[],limits=Array.isArray(a.source_read_limitations)?a.source_read_limitations:(a.source_read_limitations?[a.source_read_limitations]:[]);
 if(!scopes.length&&!limits.length)return '';
 return '<section class="line code-read-scopes"><h4>代码审读范围、来源状态与合入限制</h4>'+
  (scopes.length?'<div class="scroll"><table><thead><tr><th>资源 / PR</th><th>来源状态</th><th>合入状态</th><th>已审读代码范围</th><th>版本</th></tr></thead><tbody>'+scopes.map(s=>'<tr><td>'+esc(s.resource_id)+'<br>'+link(s.url,'打开原文 / PR')+'</td><td>'+esc(text(s.source_status))+'</td><td>'+esc(s.merged===false?'未合入（merged=false）':s.merged===true?'已合入（merged=true）':'合入状态未知')+'</td><td>'+esc(text(s.diff_read_scope||s.code_evidence_scope||s.review_scope))+'</td><td>'+esc(text(s.head_sha))+'</td></tr>').join('')+'</tbody></table></div>':'')+
  (scopes.some(s=>s.merged===false)?'<p class="notice">这里包含未合入来源。可见改动只支持注明范围内的代码观察，不代表已部署到原故障环境。</p>':'')+
  '<h4>来源审读限制</h4>'+list(limits)+'</section>';
}
function analysisCard(a){
 const chain=a.mechanism_chain||{},claims=a.source_claims||[],refs=uniq([...claims.flatMap(c=>c.evidence_ids||[]),...(a.mode_comparisons||[]).flatMap(c=>c.evidence_ids||[])]);
 const carrier=a.implementation_carrier||chain.implementation_carrier||chain.carrier;
 const mechanism=(a.mechanism||{}).statement||a.candidate_mechanism;
 return '<article class="card analysis" id="'+esc(a.analysis_id)+'"><h3>'+esc(a.analysis_id)+'</h3>'+tags([a.task_id,a.subproblem_id,a.entity_type])+'<p><b>来源属性：</b>'+tags(sourceBases(a))+' <b>机理依据：</b>'+tags(mechanismBasis(a)||'UNKNOWN')+'</p>'+
  '<h4>1 · 机理关系与来源边界</h4><p>'+esc(text(mechanism))+'</p><div class="scroll"><table class="four"><thead><tr><th>候选机理</th><th>实现载体</th><th>依据 / 层级</th><th>原30条边界</th></tr></thead><tbody><tr><td>'+esc(text(mechanism))+'</td><td>'+esc(text(carrier))+'</td><td><p><b>来源属性：</b>'+tags(sourceBases(a))+'</p><p><b>机理依据：</b>'+tags(mechanismBasis(a)||'UNKNOWN')+'</p><p>'+esc(text(a.evidence_level))+'</p></td><td>'+esc(text(a.original30_boundary))+'</td></tr></tbody></table></div>'+
  '<dl class="sequence"><dt>预期成立的关系</dt><dd>'+esc(text(chain.expected_relation))+'</dd><dt>来源观察到的变化</dt><dd>'+esc(text(chain.observed_change))+'</dd><dt>消费者</dt><dd>'+esc(text(chain.consumer))+'</dd><dt>推导依据</dt><dd>'+esc(text(chain.basis))+'</dd><dt>来源范围</dt><dd>'+esc(text(a.source_scope))+'</dd></dl>'+
  '<h4>2 · 稀疏42 / V4关联与 Requires / Skip</h4>'+
  ((a.selected_labels||[]).length?(a.selected_labels||[]).map(l=>conditionCard(l,a)).join(''):'<p class="notice">没有可正向绑定的条件标签，保留待补事实的测试卡。</p>')+
  (a.condition_notes?'<p>'+esc(text(a.condition_notes))+'</p>':'')+
  '<details><summary>本分析本地 Scenario（不跨子问题拼接）</summary>'+pretty(a.scenarios||[])+'</details>'+
  '<h4>3 · 目标路径、判据与原生 DesignCard</h4><dl class="sequence"><dt>目标路径</dt><dd>'+esc(text(chain.target_path))+'</dd><dt>Oracle / 判据</dt><dd>'+esc(text(chain.oracle))+'</dd></dl>'+
  (a.design_cards||[]).map(designCard).join('')+
  '<h4>4 · 来源主张、精确引文与未知</h4>'+readScopePanel(a)+claims.map(c=>'<section class="line claim"><p>'+tags([c.claim_id,c.basis,c.task_id,c.subproblem_id])+'</p><p>'+esc(c.statement)+'</p><p class="muted">证据 '+tags(c.evidence_ids||[])+'</p></section>').join('')+
  refs.map(id=>evidenceById.has(id)?evidenceCard(evidenceById.get(id)):'<p class="notice">证据ID未在当前离线锚点集中解析：'+esc(id)+'</p>').join('')+
  '<h4>原30条比较与建议</h4>'+pretty({comparisons:a.mode_comparisons||[],decision:a.mode_decision,original30_boundary:a.original30_boundary,adoption_status:a.adoption_status,formal_adoption:a.formal_adoption})+
  '<p class="muted">来源声明、代码事实、分析推断和 HYPOTHESIS 独立标记。测试卡全部仅设计；未知不能成为新增模式裁决。</p></article>';
}
function publicFindingCard(f){
 const refs=f.evidence_ids||[];
 return '<section class="line r3-finding"><h4>'+esc(f.finding_id||f.id||'公开观察')+'</h4>'+tags(['R3_REUSED_OBSERVATION',f.basis,f.entity_type,f.event_relation])+
  '<p><b>R3公开代码观察：</b>'+esc(text(f.finding))+'</p><p><b>具体关系：</b>'+esc(text(f.failed_or_required_relation))+'</p><p><b>原30条边界：</b>'+esc(text(f.original30_boundary))+'</p>'+
  '<p><b>实际代码审读范围：</b>'+esc(text(f.source_read_scope||f.code_evidence_scope))+'</p><p>'+link(f.url,'打开原文 / PR')+'</p><p><b>evidence_ids：</b>'+tags(refs.length?refs:['未列出，保持证据缺口'])+'</p>'+
  (refs.length?'<details><summary>展开R3已保存精确选段</summary>'+refs.map(id=>evidenceById.has(id)?evidenceCard(evidenceById.get(id)):'<p class="notice">当前离线锚点未解析 '+esc(id)+'</p>').join('')+'</details>':'')+'</section>';
}
function evidenceRelationCard(r){
 const resource=resourceById.get(r.resource_id)||{},refs=r.evidence_ids||[];
 const scope=r.code_evidence_scope||r.source_read_scope||resource.diff_read_scope||resource.review_scope||resource.body_semantics_reviewed;
 return '<section class="line r3-relation"><h4>'+esc(r.relation_id||r.resource_id||'逐资料关系')+'</h4>'+tags([r.resource_id,r.source_relation,r.event_relation,r.mechanism_relation])+
  '<p><b>source_status：</b>'+esc(text(r.source_status||r.support_status||r.source_relation))+'</p><p><b>关系判断：</b>'+esc(text(r.reason))+'</p><p><b>子问题范围：</b>'+esc(text(r.issue_scope))+'</p>'+
  '<p><b>code scope：</b>'+esc(text(scope))+'</p><p><b>evidence_ids：</b>'+tags(refs.length?refs:['R3未列出独立证据ID；以原资源及注明范围为限'])+'</p>'+
  '<p>'+link(r.url||resource.url,'打开原文 / PR')+' '+link(resource.receipt,'R3回执')+' '+link(resource.raw_diff||resource.body_file||resource.file,'R3归档代码 / 原文')+'</p>'+
  (r.missing?'<p class="notice"><b>仍缺：</b>'+esc(text(r.missing))+'</p>':'')+'<details><summary>完整R3关系记录</summary>'+pretty(r)+'</details></section>';
}
function r3Context(row){
 const findings=findingsFor(row.task_id),relations=relationsFor(row.task_id);
 return '<section class="panel r3-context"><h3>R3复用公开观察与逐资料关系</h3><p class="notice">以下为R3已记录观察、关联和注明审读范围的复用，不表示本轮重新深审所有代码；公开技术观察、原周报事件身份和本轮机理分析分别记录。</p>'+
  '<h4>本Task已有公开观察（'+findings.length+'）</h4>'+(findings.length?findings.map(publicFindingCard).join(''):'<p class="muted">R3没有为本Task列出公开finding。</p>')+
  '<h4>本Task逐资料事件 / 机理关系（'+relations.length+'）</h4>'+(relations.length?relations.map(evidenceRelationCard).join(''):'<p class="muted">R3没有为本Task列出独立逐资料关系。</p>')+'</section>';
}
function caseCard(r){
 const aa=analysesFor(r);
 const correction=D.corrections.find(c=>c.task_id===r.task_id);
 const currentGaps=Array.isArray(r.current_design_gaps)?r.current_design_gaps:(r.current_design_gaps?[r.current_design_gaps]:[]);
 const historicalGaps=Array.isArray(r.historical_unresolved_gaps)?r.historical_unresolved_gaps:(r.historical_unresolved_gaps?[r.historical_unresolved_gaps]:[]);
 return '<div class="case-detail"><h3>'+esc(r.task_id)+' · '+aa.length+'个独立机理分析</h3>'+
  '<details><summary>原始转交输入（完整保留）</summary>'+pretty(r.original_input)+'<p>'+sourceLinks(r.original_input)+'</p></details>'+
  (correction?'<section class="line current-corrections"><h3>本轮原文纠偏</h3>'+pretty(correction.corrections||correction)+'</section>':'')+
  aa.map(analysisCard).join('')+
  '<section class="line current-design-gaps"><h3>本轮设计缺口</h3>'+list(currentGaps)+'</section>'+r3Context(r)+
  '<details class="historical-gaps"><summary>历史遗留缺口（独立保留，默认折叠）</summary>'+list(historicalGaps)+'</details>'+
  ((r.historical_mode_comparisons||[]).length?'<details class="historical-mode-comparisons"><summary>R3历史归卡讨论（不作当前新判定）</summary><p class="muted">以下保留R3历史比较，当前判断以本轮独立分析中的原30条比较与建议为准。</p>'+pretty(r.historical_mode_comparisons)+'</details>':'')+
  (r.field_audit?'<details><summary>R3资料核验范围与缺口</summary>'+pretty(r.field_audit)+'</details>':'')+'</div>';
}
function caseRow(r){
 const aa=analysesFor(r),fault=(r.original_input||{}).fault||{};
 const overview=typeof fault==='string'?fault:(fault.description||fault.reported_root_cause||r.description||r.task_id);
 return '<tr class="case-row" id="'+esc(r.task_id)+'"><td><b>'+esc(r.task_id)+'</b><br><span class="muted">'+aa.length+'个分析</span></td><td>'+esc(overview)+'</td><td><p><b>来源属性：</b>'+tags(uniq(aa.flatMap(sourceBases)))+'</p><p><b>机理依据：</b>'+tags(uniq(aa.map(mechanismBasis)))+'</p><p>'+tags(uniq(aa.flatMap(readiness)))+'</p></td><td>'+tags(uniq(aa.flatMap(labelNames)))+'<p>'+tags(uniq(aa.map(a=>(a.mode_decision||{}).action)))+'</p></td><td><details><summary>按机理展开条件、路径及证据</summary>'+caseCard(r)+'</details></td></tr>';
}
function baselineCard(m){return '<article class="card"><h3>'+esc(m.mode_id||m.item_id||m.id||'原30条')+' · '+esc(m.name||m.pattern_name||'')+'</h3><p>'+esc(text(m.mechanism||m.root_cause||m.definition))+'</p>'+pretty(m)+'</article>'}
function definitionCard(d){
 return '<article class="card"><h3>'+esc(d.scheme+' / '+d.id)+'</h3>'+tags(d.definition_version)+'<p><b>完整定义：</b>'+esc(d.definition)+'</p><h4>Requires</h4>'+list(d.requires)+'<h4>Skip if</h4>'+list(d.skip_if)+
  '<h4>构造能力、路径与分析要求</h4>'+pretty({construction_requires:d.construction_requires||[],path_requires:d.path_requires||[],analysis_requires:d.analysis_requires||[]})+
  '<h4>选中构造码 / 指导来源</h4>'+pretty({construction_ids:d.construction_ids||[],constructions:d.constructions||[],guides:d.guides||[]})+'<details><summary>完整冻结条目元数据</summary>'+pretty(d)+'</details></article>';
}
function resourceCard(r){
 const files=['receipt','body_file','raw_diff','file','email_patch'];
 return '<article class="card"><h3>'+esc(r.resource_id||r.id||'来源资料')+' · '+esc(r.title||r.url||'')+'</h3>'+tags([r.kind,r.body_capture||r.capture_status,r.origin,...(r.task_ids||[])])+'<p>'+link(r.url,'打开原文 / PR')+'</p><p><b>实际审读范围：</b>'+esc(text(r.diff_read_scope||r.review_scope||r.body_semantics_reviewed))+'</p><p>'+files.filter(k=>r[k]).map(k=>link(r[k],k)).join(' · ')+'</p>'+pretty(r)+'</article>';
}
function searchCard(s){return '<article class="card"><h3>'+esc(s.query_id||s.search_id||s.id||'查询')+' · '+esc(s.query||'')+'</h3>'+tags([s.outcome,s.origin,s.resource_type,...(s.task_ids||[])])+'<p>'+link(s.receipt,'打开检索回执')+'</p>'+pretty(s)+'<p>'+sourceLinks(s.candidates||[])+'</p><p class="muted">候选标题不是正文审读；无匹配仅限已记录的查询和范围。</p></article>'}
const VIEWS=[['cases','128条主视图'],['analyses','独立机理分析'],['baseline30','原30条独立对照'],['definitions','42 / V4冻结定义'],['evidence','原文锚点 / 精确代码'],['resources','R3来源审计'],['searches','R3检索台账'],['summary','统计与范围']];
let currentView='cases';
function renderView(view,q=''){
 if(view==='cases'){const rows=selectRows(q,$('basis').value,$('readiness').value,$('scheme').value,$('label').value,$('mode').value);return '<div class="scroll"><table class="case-table"><thead><tr><th>Task</th><th>原输入摘要</th><th>依据 / 测试卡状态</th><th>稀疏条件 / 模式建议</th><th>机理分析入口</th></tr></thead><tbody>'+rows.map(caseRow).join('')+'</tbody></table></div>'+(rows.length?'':'<p class="empty">没有匹配的输入记录。</p>')}
 if(view==='analyses'){const ids=new Set(selectRows(q,$('basis').value,$('readiness').value,$('scheme').value,$('label').value,$('mode').value).flatMap(r=>r.analysis_ids||[]));return D.analyses.filter(a=>ids.has(a.analysis_id)&&analysisMatches(a,$('basis').value,$('readiness').value,$('scheme').value,$('label').value,$('mode').value)).map(analysisCard).join('')||'<p class="empty">没有匹配的机理分析。</p>'}
 if(view==='baseline30')return '<div class="panel"><h2>原30条独立对照</h2><p>保留原模式机理定义。相同算子、同一症状或检索UNKNOWN不构成同模式或新增模式裁决。</p></div>'+D.baseline30.filter(m=>matching(m,q)).map(baselineCard).join('');
 if(view==='definitions')return '<div class="panel"><h2>版本化42 / V4定义</h2><p>下列为报告携带的完整规则条目。只展示选中定义时，未选规则保持 NOT_ASSESSED；API42与V4各自检查，不由crosswalk传递标签。</p></div>'+D.definitions.filter(d=>matching(d,q)).map(definitionCard).join('');
 if(view==='evidence')return '<div class="panel"><h2>来源原文与精确代码选段</h2><p>原输入引文与已保存代码范围分别保留。选段、完整文件获取和完整语义审读分别计量。</p></div>'+[...D.quotes,...D.excerpts].filter(e=>matching(e,q)).map(e=>'<article class="card">'+evidenceCard(e)+'</article>').join('');
 if(view==='resources')return '<div class="panel"><h2>R3来源审计</h2><p>沿用已取得资料、实际读取范围和历史尝试回执；本版离线分析不新增抓取。</p></div>'+D.resources.filter(r=>matching(r,q)).map(resourceCard).join('');
 if(view==='searches')return '<div class="panel"><h2>R3检索台账</h2><p>复用实际查询及其回执，不据索引候选宣称完整正文已读。</p></div>'+D.searches.filter(s=>matching(s,q)).map(searchCard).join('');
 if(view==='summary')return '<article class="card"><h2>统计、口径与缺口</h2>'+pretty(D.summary)+'<p>分析记录以 task / 子问题分别绑定来源主张；同一输入中的独立机理不拼成共同触发条件。</p><p>语义适用、构造能力、路径覆盖、执行结果、原事件确认和模式采纳各自记录。NOT_RUN与execution_implemented=false是设计卡状态，不能计作复现成功。</p><p>HYPOTHESIS仅为待核解释或拟构造设计；UNKNOWN不能成为新增模式裁决。</p></article>';
 return '<p class="empty">未知视图。</p>';
}
function options(id,values,label){$(''+id).innerHTML='<option value="">'+esc(label)+'</option>'+uniq(values).map(v=>'<option value="'+esc(v)+'">'+esc(v)+'</option>').join('')}
function draw(){
 $('tabs').innerHTML=VIEWS.map(([id,name])=>'<button type="button" data-view="'+id+'" class="'+(id===currentView?'active':'')+'" aria-pressed="'+String(id===currentView)+'">'+esc(name)+'</button>').join('');
 $('content').innerHTML=renderView(currentView,$('query').value);
 $('count').textContent=(currentView==='cases'||currentView==='analyses')?'匹配输入 '+activeRows().length+' / '+D.results.length+'；筛选条件在同一个独立分析内匹配。':'独立资料视图 · 关键词筛选；状态与标签筛选仅作用于输入和机理视图。';
}
function setView(view){if(VIEWS.some(v=>v[0]===view)){currentView=view;draw()}}
options('basis',D.analyses.flatMap(bases),'全部来源依据');
options('readiness',D.analyses.flatMap(readiness),'全部测试卡状态');
options('scheme',D.analyses.flatMap(a=>(a.selected_labels||[]).map(l=>l.scheme)),'全部42 / V4体系');
options('label',D.analyses.flatMap(a=>(a.selected_labels||[]).map(l=>l.trigger_id)),'全部稀疏标签');
options('mode',D.analyses.flatMap(a=>[...(a.mode_comparisons||[]).map(m=>m.mode_id),(a.mode_decision||{}).action]),'全部原30 / 模式建议');
const allCards=D.analyses.flatMap(a=>a.design_cards||[]);
$('metrics').innerHTML=[[D.results.length,'原始输入'],[D.analyses.length,'独立机理分析'],[allCards.length,'原生测试设计卡'],[allCards.filter(c=>c.execution_status==='NOT_RUN'&&c.execution_implemented===false).length,'NOT_RUN设计卡']].map(([v,n])=>'<div class="metric"><strong>'+esc(v)+'</strong>'+esc(n)+'</div>').join('');
for(const id of ['query','basis','readiness','scheme','label','mode'])$(id).addEventListener(id==='query'?'input':'change',draw);
$('reset').addEventListener('click',()=>{for(const id of ['query','basis','readiness','scheme','label','mode'])$(id).value='';draw()});
$('tabs').addEventListener('click',event=>{const target=event.target.closest('button[data-view]');if(target)setView(target.getAttribute('data-view'))});
draw();
"""


HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>128条独立机理分析 · 42 / V4条件与测试设计 · R4</title><style>__CSS__</style></head>
<body><header><h1>128条 · 独立机理、条件关联与测试设计</h1>
<p>从每条输入的独立子问题出发，依次查看机理关系、版本化42 / V4条件、目标路径与判据，以及来源引文和未知。</p>
<p>来源声明、代码事实、推断与假设分别标记。原30条独立对照；测试卡仅为设计，未进行设备执行或正式模式采纳。</p></header>
<main><div id="metrics" class="metrics"></div>
<div class="controls" role="search"><label>关键词 / Task<input id="query" placeholder="例如 RC-104、目标路径或证据ID" aria-label="关键词或Task"></label>
<label>依据<select id="basis" aria-label="来源依据"></select></label>
<label>测试设计<select id="readiness" aria-label="测试卡状态"></select></label>
<label>条件体系<select id="scheme" aria-label="条件体系"></select></label>
<label>稀疏标签<select id="label" aria-label="稀疏条件标签"></select></label>
<label>原30 / 建议<select id="mode" aria-label="原30模式或建议"></select></label>
<button id="reset" type="button">清空筛选</button></div>
<nav id="tabs" aria-label="报告视图"></nav><p id="count" aria-live="polite"></p>
<div id="content"></div><footer>完整离线报告 · 相对链接打开随包原文，外部原文 / PR仅在点击链接时打开。</footer></main>
<script type="application/json" id="payload">__PAYLOAD__</script>
<script>__JS__</script></body></html>
"""


def render(folder, data):
    """Write one standalone report; caller supplies all captured report data."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # Script elements terminate before JSON parsing; escape their delimiters.
    for char, replacement in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"),
                              ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        payload = payload.replace(char, replacement)
    # Insert user data last so literal template markers in a quote stay data.
    html = HTML.replace("__CSS__", CSS).replace("__JS__", JS).replace("__PAYLOAD__", payload)
    (Path(folder) / "report.html").write_text(html, encoding="utf-8", newline="\n")
