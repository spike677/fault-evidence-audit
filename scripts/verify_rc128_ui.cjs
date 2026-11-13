// Offline VM checks, not a real browser, model or NPU/GPU run.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const folder=path.resolve(process.argv[2]||'reports/archive/rc128-evidence-review-20261111');
const html=fs.readFileSync(path.join(folder,'report.html'),'utf8');
const raw=html.match(/<script type="application\/json" id="payload">([\s\S]*?)<\/script>/)[1];
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const nodes=new Map();
function node(id){if(!nodes.has(id))nodes.set(id,{textContent:id==='payload'?raw:'',innerHTML:'',value:'',listeners:new Map(),addEventListener(n,f){this.listeners.set(n,f)}});return nodes.get(id)}
const ctx=vm.createContext({document:{getElementById:node},URL});
vm.runInContext(script,ctx,{timeout:10000});
const run=s=>vm.runInContext(s,ctx,{timeout:10000}),checks=[];
function check(name,fn){try{fn();checks.push({name,status:'PASS'})}catch(e){checks.push({name,status:'FAIL',error:e.message})}}
check('128_full_records_render_without_paging',()=>assert.equal((run('renderView("cases")').match(/id="RC-\d{3}"/g)||[]).length,128));
check('all_seven_views_render',()=>{assert.equal(run('VIEWS.length'),7);for(const id of ['cases','technical','candidates','baseline','conditions','evidence','summary'])assert.ok(run(`renderView(${JSON.stringify(id)})`).length>50,id)});
check('record_filter_exact_id_and_no_match',()=>{assert.equal(run('selectRows("RC-094").length'),1);assert.equal(run('selectRows("NO-SUCH-RC").length'),0)});
check('six_weekly_candidates_not_eight_independent_mechanisms',()=>assert.equal(run('selectRows("","NEW_CANDIDATE").length'),6));
check('mode_filter_and_source_filter_apply',()=>{assert.ok(run('selectRows("","","","M007").length')>0);assert.equal(run('selectRows("","","PUBLIC_CODE_CLUE").length'),16)});
check('wiki_only_group_12_not_skipped',()=>assert.equal(run('selectRows("","","WIKI_SUMMARY").length'),12));
check('original30_index_renders_in_source_order',()=>{const h=run('renderView("baseline")');assert.equal((h.match(/<article class="card">/g)||[]).length,30);assert.ok(h.indexOf('M020')<h.indexOf('M006'))});
check('42_plus55_independent_definition_cards',()=>assert.equal((run('renderView("conditions")').match(/<article class="card">/g)||[]).length,97));
check('new_knowledge_is_not_called_failure_mechanism_taxonomy',()=>{const h=run('renderView("conditions")');assert.ok(!h.includes('55类故障机理'));assert.ok(h.includes('类别、构造情形与失效机理不互换'))});
check('all_independent_technical_cases_render',()=>assert.equal((run('renderView("technical")').match(/id="TC-/g)||[]).length,22));
check('four_dimensions_and_actual_required_relation_visible',()=>{const h=run('caseCard(D.results[8])');for(const x of ['对象角色','计量与表示域','生命周期','消费者','应有关系','实际失效','缓存'])assert.ok(h.includes(x),x)});
check('128_transcription_conflict_visible',()=>{const h=run('caseCard(D.results[127])');assert.ok(h.includes('INITIALIZED_UNINITIALIZED'));assert.ok(h.includes('初始化的空间'))});
check('094_wiki_commit_source_and_api_condition_visible',()=>{const h=run('caseCard(D.results[93])');for(const x of ['a3a3d38','scaling_factor','1.5.2','TC-ROPE-CACHE-EXTENT'])assert.ok(h.includes(x),x)});
check('104_four_subproblem_scopes_visible',()=>{const h=run('caseCard(D.results[103])');for(const x of ['RC-104:REL-01','RC-104:REL-02','RC-104:REL-03','RC-104:REL-04'])assert.ok(h.includes(x),x)});
check('gather_unit_and_dequant_formula_visible',()=>{let h=run('technicalCard(D.technical_cases.find(x=>x.technical_case_id==="TC-GATHER-SCALAR-COUNT"))');assert.ok(h.includes('1536'));assert.ok(h.includes('itemsize'));h=run('technicalCard(D.technical_cases.find(x=>x.technical_case_id==="TC-DEQUANT-REDUCE-STRIDE"))');assert.ok(h.includes('UbFactorDimy'));assert.ok(h.includes('(q%64)//8'))});
check('source_quote_is_exact_and_range_visible',()=>{const h=run('quote("GH-ROPE-a3a3d38:1:Q1")');assert.ok(h.includes('max_position_embeddings'));assert.ok(h.includes('scaling_factor'));assert.ok(h.includes('原来源'));assert.match(h,/L\d+–\d+/)});
check('source_output_and_json_are_escaped',()=>{const h=run('(()=>{const r=JSON.parse(JSON.stringify(D.results[0]));r.original_input.fault.description="<img src=x onerror=alert(1)>";return caseCard(r)})()');assert.ok(!h.includes('<img src=x'));assert.ok(h.includes('&lt;img src=x'))});
check('unsafe_protocol_is_not_linked',()=>{assert.ok(!run('link("javascript:alert(1)","bad")').includes('<a '));assert.ok(!run('link("data:text/html,test","bad")').includes('<a '))});
check('no_network_or_external_dependency',()=>{assert.ok(!/\bfetch\s*\(|XMLHttpRequest|WebSocket/.test(script));assert.ok(!/<script[^>]+src=|<link[^>]+href=/.test(html))});
check('reset_filters_works_without_new_task',()=>{node('query').value='RC-094';node('action').value='PENDING';node('reset').listeners.get('click')();assert.equal(node('query').value,'');assert.equal(node('action').value,'');assert.ok(node('count').textContent.includes('128 / 128'))});
check('embedded_full_data_equal_published_jsonl',()=>{const input=fs.readFileSync(path.join(folder,'results.jsonl'),'utf8').trim().split('\n').map(JSON.parse);assert.deepEqual(JSON.parse(raw).results,input)});
check('unknown_and_evidence_limits_not_hidden',()=>{const h=run('caseCard(D.results[3])');assert.ok(h.includes('根因未知'));assert.ok(h.includes('暂未建立可成立关联'));assert.ok(h.includes('仍缺'))});
check('nested_shared_evidence_card_ids_are_unique',()=>{const ids=[...run('renderView(\"cases\")').matchAll(/id=\"([^\"]+)\"/g)].map(x=>x[1]);assert.equal(ids.length,new Set(ids).size)});
const failed=checks.filter(x=>x.status!=='PASS').length;
const result={status:failed?'FAIL':'PASS',runtime:process.version,check_count:checks.length,failed,scope:'OFFLINE_VM_LOGIC_NOT_BROWSER_OR_DEVICE',checks};
// Historical validation is immutable. This runner reports to stdout only.
process.stdout.write(JSON.stringify(result,null,2)+'\n');process.exitCode=failed?1:0;
