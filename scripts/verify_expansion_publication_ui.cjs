// Built-in Node VM checks; never launches a browser, device or model.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const folder=path.resolve(process.argv[2]||'reports/expansion-v1-20261110');
const html=fs.readFileSync(path.join(folder,'CANN_EXPANSION_FULL_RESULTS.html'),'utf8');
const payload=html.match(/<script type="application\/json" id="payload">([\s\S]*?)<\/script>/)[1];
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const nodes=new Map(),events=[];
function node(id){if(!nodes.has(id))nodes.set(id,{textContent:id==='payload'?payload:'',innerHTML:'',value:'',addEventListener:(n,f)=>events.push(['listen',id,n]),scrollIntoView:()=>events.push(['scroll',id])});return nodes.get(id)}
const ctx=vm.createContext({document:{getElementById:node},URL});vm.runInContext(script,ctx,{timeout:10000});
const run=s=>vm.runInContext(s,ctx,{timeout:10000}),checks=[];
function check(name,fn){try{fn();checks.push({name,status:'PASS'})}catch(e){checks.push({name,status:'FAIL',error:e.message})}}
check('nine_full_public_views',()=>{assert.equal(run('VIEWS.length'),9);for(const name of ['最强相关证据','模式增量 / 候选','缺口与阶段状态','全部源码证据'])assert.ok(node('nav').innerHTML.includes(name),name)});
check('18_19_20_metrics_and_scope',()=>{const h=run('overview()');for(const x of ['18/42','19/42','20/42','设备验证0/42','不表示19项全部'])assert.ok(h.includes(x),x)});
check('nineteen_cases_render',()=>assert.equal((run('renderView("cases")').match(/id="case-TC-/g)||[]).length,19));
check('exact_case_id_filter',()=>{assert.equal(run('selectCases("TC-GATHER-SCALAR-COUNT").length'),1);assert.equal(run('selectCases("NO-SUCH-CASE").length'),0)});
check('42_api_and_55_v4_definitions_render',()=>{assert.equal((run('renderView("api")').match(/<article class="card">/g)||[]).length,42);assert.equal((run('renderView("v4")').match(/<article class="card">/g)||[]).length,55)});
check('api_links_baseline_new_case_and_design',()=>{const h=run('renderView("api","1.1.1")');for(const x of ['M020','TC-GMM-K0','Oracle：'])assert.ok(h.includes(x),x)});
check('nineteen_unexecuted_design_cards',()=>{const h=run('renderView("designs")');assert.equal((h.match(/>NOT_EXECUTED</g)||[]).length,19)});
check('functional_scope_visible',()=>{const h=run('caseCard(CASES.find(c=>c.technical_case_id==="TC-MATMUL-DISPATCH-DTYPE"))');assert.ok(h.includes('FUNCTIONAL_OUT_OF_SCOPE'));assert.ok(h.includes('BINARY_DISPATCH_FAILURE_REPORTED'))});
check('gather_correct_source_visible',()=>{const h=run('caseCard(CASES.find(c=>c.technical_case_id==="TC-GATHER-SCALAR-COUNT"))');assert.ok(h.includes('ge::GetSizeByDataType'))});
check('source_evidence_not_empty',()=>assert.ok((run('renderView("evidence")').match(/<article class="card">/g)||[]).length>=19));
check('focus_case_links_work',()=>{node('query').value='old';run('focusCase("TC-BOOL-REDUCE")');assert.equal(run('view'),'cases');assert.equal(node('query').value,'');assert.ok(events.some(e=>e[0]==='scroll'&&e[1]==='case-TC-BOOL-REDUCE'))});
check('source_text_is_escaped',()=>{const h=run('(()=>{const c=JSON.parse(JSON.stringify(CASES[0]));c.title="<img src=x onerror=alert(1)>";return caseCard(c)})()');assert.ok(!h.includes('<img src=x'));assert.ok(h.includes('&lt;img src=x'))});
check('unsafe_urls_not_linked_no_network_script',()=>{assert.ok(!run('source("javascript:alert(1)")').includes('<a '));assert.ok(!/\bfetch\s*\(|XMLHttpRequest|WebSocket/.test(script));assert.ok(!/<script[^>]+src=|<link[^>]+href=/.test(html))});
check('embedded_case_data_equals_json',()=>assert.deepEqual(JSON.parse(payload).cases,JSON.parse(fs.readFileSync(path.join(folder,'technical_cases.json'),'utf8'))));
check('full_report_legacy_alias_is_identical',()=>assert.equal(html,fs.readFileSync(path.join(folder,'CANN_EXPANSION_CANDIDATE_CATALOG.html'),'utf8')));
check('19_primary_evidence_cards_and_limits',()=>{const h=run('renderView("best")');assert.equal((h.match(/id="best-TC-/g)||[]).length,19);assert.equal((h.match(/不能据此确认/g)||[]).length,19);assert.ok(h.includes('EXACT_OBSERVED_DIFF_LINES'))});
check('increment_candidate_and_scope_results_visible',()=>{const h=run('renderView("modes")');for(const x of ['案例追加 · 4','机制详情 · 10','范围外技术关系 · 2','新模式候选 · 3'])assert.ok(h.includes(x),x);assert.equal((h.match(/id="candidate-/g)||[]).length,3)});
check('22_gaps_and_unfinished_search_status_visible',()=>{const h=run('renderView("gaps")');assert.equal((h.match(/id="gap-/g)||[]).length,22);assert.ok(h.includes('23项窄口径'));assert.ok(h.includes('没有执行22项缺口的历史检索'))});
check('four_support_contexts_are_readable',()=>{const h=run('renderView("evidence")');for(const id of ['CAT-API-BOOL','CAT-TEST-GRAD-DEVICE','CAT-TEST-GRAD-META','CAT-API-GATHER'])assert.ok(h.includes(id),id);assert.ok(h.includes('PRIOR_TARGETED_OBSERVATION'))});
check('all_public_data_present_inside_one_html',()=>{const d=JSON.parse(payload);for(const key of ['cases','relations','definitions','baseline','coverage','tests','designs','increments','candidates','gaps','evidence','source_receipt','strongest','contexts'])assert.ok(d[key],key);assert.ok(!/<script[^>]+src=|<link[^>]+href=/.test(html))});
const failed=checks.filter(c=>c.status!=='PASS').length;
process.stdout.write(JSON.stringify({status:failed?'FAIL':'PASS',runtime:process.version,check_count:checks.length,passed:checks.length-failed,failed,scope:'OFFLINE_VM_LOGIC_NOT_BROWSER_OR_DEVICE',checks},null,2)+'\n');process.exitCode=failed?1:0;
