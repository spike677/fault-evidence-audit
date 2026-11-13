// Offline VM interaction checks. No browser, live model or device execution.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const folder=path.resolve(process.argv[2]||'reports/archive/rc128-evidence-review-20261112-r2');
const html=fs.readFileSync(path.join(folder,'report.html'),'utf8');
const raw=html.match(/<script type="application\/json" id="payload">([\s\S]*?)<\/script>/)[1];
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];const nodes=new Map();
function node(id){if(!nodes.has(id))nodes.set(id,{textContent:id==='payload'?raw:'',innerHTML:'',value:'',listeners:new Map(),addEventListener(n,f){this.listeners.set(n,f)}});return nodes.get(id)}
const ctx=vm.createContext({document:{getElementById:node},URL});vm.runInContext(script,ctx,{timeout:15000});
const run=s=>vm.runInContext(s,ctx,{timeout:15000}),checks=[];
function check(name,f){try{f();checks.push({name,status:'PASS'})}catch(e){checks.push({name,status:'FAIL',error:e.message})}}
check('128_complete_case_cards',()=>assert.equal((run('renderView("cases")').match(/id="RC-\d{3}"/g)||[]).length,128));
check('all_nine_views_render',()=>{assert.equal(run('VIEWS.length'),9);for(const id of run('VIEWS.map(x=>x[0])'))assert.ok(run(`renderView(${JSON.stringify(id)})`).length>50,id)});
check('six_pending_reviews_not_new_modes',()=>{assert.equal(run('D.case_reviews.length'),6);assert.equal(run('D.comparisons.filter(x=>D.case_reviews.some(r=>r.task_id===x.task_id)&&x.action!=="PENDING").length'),0)});
check('22_quantity_sections_visible',()=>assert.equal((run('renderView("driving")').match(/id="RC-\d{3}:QTY-/g)||[]).length,22));
check('four_overview_columns_visible',()=>{const h=run('renderView("candidates","RC-029")');for(const t of ['候选机理','实现载体','证据等级','与原30关系','M010','M024','待审'])assert.ok(h.includes(t),t)});
check('all_questions_and_q3_roles_visible',()=>{const h=run('quantitiesCard("RC-105")');for(const t of ['Q1 对象','Q2 单位','Q3 生命周期','Q4 消费者','创建','初始化','可写主体','复位责任','未知原因','非计数量'])assert.ok(h.includes(t),t)});
check('rc062_neutral_relation_and_alternatives',()=>{const r=JSON.parse(raw).case_reviews.find(x=>x.task_id==='RC-062');assert.ok(!r.candidate_mechanism.name.includes('恢复遗漏'));assert.ok(!r.candidate_mechanism.expected_relation.includes('寄存器'));assert.equal(r.candidate_mechanism.alternatives.length,6)});
check('rc029_no_stage_in_derived_relation',()=>{const f=JSON.parse(raw).failures.filter(x=>['RC-029','TC-FP8-VSCALE'].includes(x.task_id||x.technical_case_id));assert.ok(!/前块|当前块|前位置|前\/当前/.test(JSON.stringify(f)))});
check('rc023_no_mlp_does_not_prove_uninitialized',()=>assert.ok(run('quantitiesCard("RC-023")').includes('未执行MLP不等于未初始化')));
check('separate_classification_axes_visible',()=>{const h=run('caseCard(D.results[8])');for(const x of ['semantic_applicability','construction_feasibility','SCHEMA_CONDITIONAL','CONDITIONALLY_APPLICABLE','EXECUTOR_CAPABILITY_UNKNOWN'])assert.ok(h.includes(x),x)});
check('applicable_semantics_and_executor_block_both_render',()=>{const h=run('(()=>{const c=JSON.parse(JSON.stringify(D.conditions.find(x=>x.task_id==="RC-009"&&x.system==="V4")));c.semantic_applicability.status="APPLICABLE";c.construction_feasibility.status="BLOCKED_AUTOCONTIGUOUS";return conditionCard(c)})()');assert.ok(h.includes('APPLICABLE'));assert.ok(h.includes('BLOCKED_AUTOCONTIGUOUS'));assert.ok(h.includes('不增加已证历史故障'))});
check('zeros_tag_conditionally_classified_not_confirmed',()=>{const h=run('caseCard(D.results[61])');for(const x of ['zeros','N3','CONDITIONAL_SOURCE_CLASSIFICATION','合法域'])assert.ok(h.includes(x),x)});
check('scale_structure_unknown_and_mounts_independent',()=>{const cs=JSON.parse(raw).conditions;assert.equal(cs.find(x=>x.task_id==='RC-029'&&x.condition_id==='scale_structure').semantic_applicability.status,'UNKNOWN');assert.equal(cs.find(x=>x.task_id==='RC-023'&&x.condition_id==='index_mask').class_assessments.find(x=>x.class_id==='C4').status,'UNKNOWN')});
check('review_depth_scope_visible',()=>{assert.ok(run('caseCard(D.results[50])').includes('SHARED_TEMPLATE_CORRECTION_ONLY'));assert.ok(run('caseCard(D.results[0])').includes('HISTORICAL_ANALYSIS_REUSED'))});
check('record_mode_group_filters_retained',()=>{assert.equal(run('selectRows("RC-094").length'),1);assert.equal(run('selectRows("","","WIKI_SUMMARY").length'),12);assert.equal(run('selectRows("","","PUBLIC_CODE_CLUE").length'),16);assert.ok(run('selectRows("","","","M007").length')>0)});
check('condition_and_quantity_search_include_six_reviews',()=>{assert.ok(run('selectRows("N3").some(r=>r.task_id==="RC-062")'));assert.ok(run('selectRows("stride按元素还是字节").some(r=>r.task_id==="RC-009")'))});
check('correction_search_and_diff_visible',()=>{const h=run('renderView("corrections","RC-062")');assert.ok(h.includes('previous_value'));assert.ok(h.includes('new_value'));assert.ok(h.includes('RC-062'))});
check('reset_and_navigation_interactions',()=>{node('query').value='RC-062';run('setView("driving")');assert.ok(node('content').innerHTML.includes('RC-062'));node('reset').listeners.get('click')();assert.equal(node('query').value,'');run('setView("cases")');assert.ok(node('count').textContent.includes('128 / 128'))});
check('html_and_jsonl_identical',()=>assert.deepEqual(JSON.parse(raw).results,fs.readFileSync(path.join(folder,'results.jsonl'),'utf8').trim().split('\n').map(JSON.parse)));
check('safe_content_escape',()=>{const h=run('(()=>{const r=JSON.parse(JSON.stringify(D.case_reviews[0]));r.candidate_mechanism.name="<img src=x onerror=alert(1)>";return fourColumns(r)})()');assert.ok(!h.includes('<img src=x'));assert.ok(h.includes('&lt;img src=x'));assert.ok(!run('link("javascript:alert(1)","bad")').includes('<a '))});
check('no_external_scripts_or_network',()=>{assert.ok(!/\bfetch\s*\(|XMLHttpRequest|WebSocket/.test(script));assert.ok(!/<script[^>]+src=|<link[^>]+href=/.test(html))});
check('all_card_ids_unique',()=>{const ids=[...run('renderView("cases")').matchAll(/id="([^"]+)"/g)].map(x=>x[1]);assert.equal(ids.length,new Set(ids).size)});
check('old30_and97_definitions_retained',()=>{assert.equal(run('D.baseline.length'),30);assert.equal(run('D.definitions.length'),97)});
check('evidence_range_and_exact_quote_visible',()=>{const h=run('quote("OBS:TC-FP8-VSCALE:1:after")');assert.ok(h.includes('deScaleVValue'));assert.ok(h.includes('原来源'))});
const result={status:checks.every(x=>x.status==='PASS')?'PASS':'FAIL',runtime:process.version,scope:'OFFLINE_VM_LOGIC_NOT_BROWSER_OR_DEVICE',check_count:checks.length,checks};
// Writing is explicit and disallowed for the historical report directory.
if(process.argv.includes('--write')){assert.notEqual(path.basename(folder),'rc128-evidence-review-20261111');fs.writeFileSync(path.join(folder,'ui_validation.json'),JSON.stringify(result,null,2)+'\n')}
process.stdout.write(JSON.stringify(result,null,2)+'\n');process.exitCode=result.status==='PASS'?0:1;
