// Offline report interaction checks, separate from actual Side source inspection.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const dir=path.resolve('reports/rc128-official-repo-pilot-20261112'),html=fs.readFileSync(path.join(dir,'report.html'),'utf8');
const raw=html.match(/<script id="data" type="application\/json">([\s\S]*?)<\/script>/)[1];
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1],nodes=new Map();
function node(id){if(!nodes.has(id))nodes.set(id,{textContent:id==='data'?raw:'',innerHTML:'',value:'',listeners:new Map(),addEventListener(k,f){this.listeners.set(k,f)}});return nodes.get(id)}
const ctx=vm.createContext({document:{getElementById:node}});vm.runInContext(script,ctx,{timeout:10000});const run=s=>vm.runInContext(s,ctx),checks=[];
function check(name,f){try{f();checks.push({name,status:'PASS'})}catch(e){checks.push({name,status:'FAIL',error:e.message})}}
check('five_complete_case_cards',()=>assert.equal((node('cases').innerHTML.match(/<article id="RC-/g)||[]).length,5));
check('record_filter_and_reset',()=>{node('q').value='RC-030';run('draw()');assert.ok(node('count').textContent.includes('1 / 5'));node('reset').listeners.get('click')();assert.ok(node('count').textContent.includes('5 / 5'))});
check('official_sources_and_searched_scope_separate',()=>{assert.ok(node('repos').innerHTML.includes('deepseek-ai'));assert.ok(node('repos').innerHTML.includes('false'));assert.ok(node('repos').innerHTML.includes('cann/ops-nn'))});
check('blocked_and_successful_reads_both_visible',()=>{assert.ok(node('resources').innerHTML.includes('FETCH_BLOCKED_IN_WEB_TOOL'));assert.ok(node('resources').innerHTML.includes('SIDE_DOWNLOADED_RAW_DIFF_AND_EMAIL_PATCH'))});
check('API_contract_not_confirmed_customer_bug',()=>{const h=run('caseCard(D.cases.find(x=>x.task_id==="RC-111"))');assert.ok(h.includes('M019'));assert.ok(h.includes('UNDETERMINED'));assert.ok(h.includes('API_CONTRACT_REFERENCE'))});
check('actual_query_scope_and_bounded_no_match_visible',()=>{assert.ok(node('searches').innerHTML.includes('NO_MATCH_IN_THIS_QUERY'));assert.ok(node('searches').innerHTML.includes('exhaustive_repository_review'));assert.ok(node('searches').innerHTML.includes('TITLE_AND_METADATA_ONLY'))});
check('source_text_escaped',()=>{const h=run('(()=>{const r=JSON.parse(JSON.stringify(D.cases[0]));r.finding="<script>alert(1)</script>";return caseCard(r)})()');assert.ok(!h.includes('<script>alert'));assert.ok(h.includes('&lt;script&gt;'))});
check('report_data_equals_jsonl',()=>{const expected=fs.readFileSync(path.join(dir,'pilot_results.jsonl'),'utf8').trim().split('\n').map(JSON.parse);assert.deepEqual(JSON.parse(raw).cases,expected)});
check('no_network_requests_or_external_dependencies',()=>{assert.ok(!/\bfetch\s*\(|XMLHttpRequest|WebSocket/.test(script));assert.ok(!/<script[^>]*src=/.test(html))});
const result={status:checks.every(c=>c.status==='PASS')?'PASS':'FAIL',scope:'OFFLINE_HTML_LOGIC_NOT_LIVE_SOURCE_REPRODUCTION',node:process.version,check_count:checks.length,checks};
fs.writeFileSync(path.join(dir,'ui_validation.json'),JSON.stringify(result,null,2)+'\n');process.stdout.write(JSON.stringify(result,null,2)+'\n');process.exitCode=result.status==='PASS'?0:1;
