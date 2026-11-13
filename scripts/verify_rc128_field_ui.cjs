// Offline interaction logic, plus real DOM ids checked before VM stubs exist.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const folder=path.resolve(process.argv[2]||'reports/archive/rc128-evidence-review-20261112-r3');
const html=fs.readFileSync(path.join(folder,'report.html'),'utf8');
const raw=html.match(/<script type="application\/json" id="payload">([\s\S]*?)<\/script>/)[1];
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const ids=new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(x=>x[1]));const nodes=new Map();
function node(id){assert.ok(ids.has(id),'Missing actual HTML control '+id);if(!nodes.has(id))nodes.set(id,{textContent:id==='payload'?raw:'',innerHTML:'',value:'',listeners:new Map(),addEventListener(n,f){this.listeners.set(n,f)}});return nodes.get(id)}
const ctx=vm.createContext({document:{getElementById:node},URL});vm.runInContext(script,ctx,{timeout:15000});
const run=s=>vm.runInContext(s,ctx,{timeout:15000}),checks=[];
function check(name,f){try{f();checks.push({name,status:'PASS'})}catch(e){checks.push({name,status:'FAIL',error:e.message})}}
check('128_current_audit_cards_render',()=>assert.equal((run('renderView("cases")').match(/class="panel current-audit"/g)||[]).length,128));
check('all12_views_render',()=>{assert.equal(run('VIEWS.length'),12);for(const id of run('VIEWS.map(x=>x[0])'))assert.ok(run(`renderView(${JSON.stringify(id)})`).length>50,id)});
check('actual_status_control_and_reset',()=>{node('audit-status').value='SOURCE_DESCRIPTION_DIFF_CONFLICT';node('audit-status').listeners.get('change')();assert.equal(run('selectRows().length'),1);assert.ok(node('content').innerHTML.includes('RC-026'));node('reset').listeners.get('click')();assert.equal(node('audit-status').value,'');assert.equal(run('selectRows().length'),128)});
check('record_filter_search_queries_resources_and_sources',()=>{node('query').value='RC-029';run('setView("search-audit")');assert.ok(node('content').innerHTML.length>100);run('setView("resources")');assert.ok(node('content').innerHTML.includes('8005'));run('setView("cases")');assert.equal(run('selectRows("RC-029").length'),1);node('reset').listeners.get('click')()});
check('strong_code_evidence_exact_quote_and_links',()=>{const h=run('renderView("public-findings","RC-010")');assert.ok(h.includes('set_ctrl'));assert.ok(h.includes('opbase/pull/279'));assert.ok(h.includes('归档代码'));assert.ok(h.includes('未知'))});
check('public_claim_weekly_identity_separate',()=>{const h=run('caseCard(D.results[22])');assert.ok(h.includes('前向'));assert.ok(h.includes('反向'));assert.ok(h.includes('UNDETERMINED'));assert.ok(h.includes('DOES_NOT_SUPPORT_ORIGINAL_CLAIM'))});
check('source_description_diff_conflict_visible',()=>{const h=run('caseCard(D.results[25])');assert.ok(h.includes('正文与Diff冲突'));assert.ok(h.includes('单kernel'))});
check('source_test_log_counterexample_visible',()=>{const h=run('renderView("resources","5929")');assert.ok(h.includes('与配置是否透传无关'));assert.ok(h.includes('不改产品代码'))});
check('six_unknowns_preserved_with_current_source_audit',()=>{assert.equal(run('D.driving_quantities.length'),22);assert.ok(run('renderView("driving","RC-062")').includes('目标调用'));const h=run('caseCard(D.results[61])');assert.ok(h.includes('sin/cos'));assert.ok(h.includes('API'))});
check('historical_blocked_attempt_does_not_replace_side_success',()=>{const h=run('renderView("resources","8752")');assert.ok(h.includes('FETCH_BLOCKED'));assert.ok(h.includes('SUCCESS'));assert.ok(h.includes('raw_diff'))});
check('no_title_only_query_claim_full_body',()=>{const h=run('renderView("search-audit","SIDE-SEARCH-24")');assert.ok(h.includes('CURRENT_PAGE_TITLE'));assert.ok(h.includes('pages_observed'));assert.ok(h.includes('正文已读'))});
check('summary_scope_not_128_confirmed',()=>{const h=run('renderView("summary")');assert.ok(h.includes('records_with_only_search_or_input_gap'));assert.ok(h.includes('confirmed_weekly_roots'));assert.ok(h.includes('不声称128条根因已证实'))});
check('source_no_match_input_gap_distinct',()=>{const d=JSON.parse(raw);assert.ok(d.field_audits.some(a=>a.processing_status==='BOUNDED_SEARCH_NO_MATCH'));assert.ok(d.field_audits.some(a=>a.processing_status==='INPUT_IDENTITY_GAP_WITH_EXPLORATORY_SEARCH'));assert.ok(d.resource_audit.some(r=>(r.capture_attempts||[]).some(a=>a.status.includes('BLOCKED'))))});
check('classification_axes_and_original30_retained',()=>{assert.equal(run('D.baseline.length'),30);assert.equal(run('D.definitions.length'),97);assert.ok(run('caseCard(D.results[8])').includes('construction_feasibility'));assert.ok(run('caseCard(D.results[61])').includes('N3'))});
check('all_report_json_results_equal',()=>assert.deepEqual(JSON.parse(raw).results,fs.readFileSync(path.join(folder,'results.jsonl'),'utf8').trim().split('\n').map(JSON.parse)));
check('safe_text_and_local_links',()=>{assert.ok(!run('auditLink("../secrets","bad")').includes('<a'));assert.ok(!run('auditLink("javascript:alert(1)","bad")').includes('<a'));assert.ok(!run('(()=>{const f=JSON.parse(JSON.stringify(D.public_findings[0]));f.finding="<script>alert(1)</script>";return findingCard(f)})()').includes('<script>alert'));});
check('no_network_code_or_external_script',()=>{assert.ok(!/\bfetch\s*\(|XMLHttpRequest|WebSocket/.test(script));assert.ok(!/<script[^>]+src=|<link[^>]+href=/.test(html))});
check('all_case_article_ids_unique',()=>{const ids=[...run('renderView("cases")').matchAll(/id="(RC-\d{3})"/g)].map(x=>x[1]);assert.equal(ids.length,128);assert.equal(new Set(ids).size,128)});
const result={status:checks.every(x=>x.status==='PASS')?'PASS':'FAIL',runtime:process.version,scope:'OFFLINE_VM_INTERACTION_NOT_BROWSER_OR_DEVICE',check_count:checks.length,checks};
if(process.argv.includes('--write')){assert.equal(path.basename(folder),'rc128-evidence-review-20261112-r3');fs.writeFileSync(path.join(folder,'ui_validation.json'),JSON.stringify(result,null,2)+'\n')}
process.stdout.write(JSON.stringify(result,null,2)+'\n');process.exitCode=result.status==='PASS'?0:1;
