// Pure JavaScript unit harness. This does not launch or control a browser.
'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const dir=path.resolve(process.argv[2]||'reports/archive/baseline-30-api42-v4-20261111'),file=path.join(dir,'CANN_30_MODES_API42_V4_REVIEW.html');
const html=fs.readFileSync(file,'utf8');
const payload=html.match(/<script id="coverage-data" type="application\/json">([\s\S]*?)<\/script>/)[1];
const js=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
const elements=new Map(),listeners=new Map();
function element(id){if(!elements.has(id)){const e={id,innerHTML:'',textContent:'',value:id.endsWith('-level')||id==='review-kind'?'ALL':id==='gap-kind'?'NO_L2':'',attributes:{},handlers:{},dataset:{},active:id==='overview',open:false,addEventListener(type,fn){this.handlers[type]=fn},setAttribute(k,v){this.attributes[k]=v},scrollIntoView(){},classList:{toggle(){}}};e.classList.toggle=(_cls,on)=>{e.active=on};elements.set(id,e)}return elements.get(id)}
const ids=['overview','api','v4','modes','gaps','review','discussion','handoff'];
const nav=ids.map(tab=>({...element('nav-'+tab),dataset:{tab}}));
const doc={getElementById:element,querySelectorAll(selector){if(selector==='nav button')return nav;if(selector==='.panel')return ids.map(element);throw Error('Unsupported unit facade selector '+selector)},querySelector(selector){if(selector==='nav')return element('nav');if(selector.endsWith('.condition-row'))return element('focused-condition');throw Error('Unsupported unit facade selector '+selector)},addEventListener(type,fn){listeners.set(type,fn)}};
element('coverage-data').textContent=payload;
const context=vm.createContext({document:doc,console,JSON,Object,String,Array});
vm.runInContext(js,context,{filename:'coverage-report-inline.js',timeout:15000});
let checks=[];
function check(name,fn){fn();checks.push(name)}
function call(code){return vm.runInContext(code,context,{timeout:15000})}
function rows(id){return (element(id).innerHTML.match(/class="row condition-row"/g)||[]).length}
check('all42Rendered',()=>assert.equal(rows('api-list'),42));
check('all55Rendered',()=>assert.equal(rows('v4-list'),55));
check('all30ModeCards',()=>assert.equal((element('modes-list').innerHTML.match(/class="row mode-row"/g)||[]).length,30));
check('metricCounts',()=>{const t=element('overview').innerHTML;assert.match(t,/data-metric="API42-L2"><strong>3\/42/);assert.match(t,/data-metric="V4-L2"><strong>6\/55/);assert.match(t,/data-metric="V4-L4"><strong>0\/55/)});
check('apiHistoryFilter',()=>{element('api-level').value='L2';call("renderConditions('api')");assert.equal(rows('api-list'),3)});
check('apiExecutionEmpty',()=>{element('api-level').value='L4';call("renderConditions('api')");assert.equal(rows('api-list'),0);assert.match(element('api-list').innerHTML,/没有匹配/) });
check('v4DesignFilter',()=>{element('v4-level').value='L3';call("renderConditions('v4')");assert.equal(rows('v4-list'),4)});
check('v4UnknownHistoryFilter',()=>{element('v4-level').value='NO_L2';call("renderConditions('v4')");assert.equal(rows('v4-list'),49)});
check('searchOneCondition',()=>{element('v4-q').value='rank_zero';element('v4-level').value='ALL';call("renderConditions('v4')");assert.equal(rows('v4-list'),1)});
check('modeSearch',()=>{element('modes-q').value='M015';call('renderModes()');assert.equal((element('modes-list').innerHTML.match(/class="row mode-row"/g)||[]).length,1)});
check('gapHistoryNoDesign',()=>{element('gap-kind').value='HISTORY_NO_DESIGN';call('renderGaps()');assert.match(element('gaps-count').textContent,/^6 /)});
check('gapDesignNoRun',()=>{element('gap-kind').value='DESIGN_NO_RUN';call('renderGaps()');assert.match(element('gaps-count').textContent,/^7 /)});
check('searchPublicPR',()=>{element('review-q').value='12123';call('renderReview()');assert.match(element('review-list').innerHTML,/EXT-GH-12123/)});
check('searchWeekly',()=>{element('review-q').value='WB-036';call('renderReview()');assert.match(element('review-list').innerHTML,/WEEKLY:WB-036/)});
check('searchRejectedPredicate',()=>{element('review-q').value='minus_one';element('review-kind').value='REJECT';call('renderReview()');assert.match(element('review-list').innerHTML,/infer-shape/)});
check('crossViewConditionFocus',()=>{call("focusCondition('V4','near_singular')");assert.equal(element('v4-q').value,'near_singular');assert.equal(element('v4').active,true);assert.equal(element('focused-condition').open,true);assert.equal(rows('v4-list'),1)});
check('eightViewNavigation',()=>{for(const id of ids){call('navigate('+JSON.stringify(id)+')');assert.equal(ids.filter(id=>element(id).active).length,1);assert.equal(element(id).active,true)}});
check('escapeUntrustedFacts',()=>assert.equal(call("esc('<script>')"),'&lt;script&gt;'));

check('originalOrderPreserved',()=>{element('modes-q').value='';call('renderModes()');const h=element('modes-list').innerHTML;assert.ok(h.indexOf('原第1条／M020')<h.indexOf('原第2条／M006'));assert.ok(h.indexOf('原第2条／M006')<h.indexOf('原第3条／M026'));assert.ok(h.indexOf('原第3条／M026')<h.indexOf('原第4条／M004'))});
check('M006DiscussionVisible',()=>assert.match(element('discussion').innerHTML,/minus_one/));
check('M026Retained',()=>assert.match(element('discussion').innerHTML,/先保留/));
check('M004ConfigurationAndUnknownRateVisible',()=>{const h=element('discussion').innerHTML;assert.match(h,/useBufferType/);assert.match(h,/CONDITIONS_REQUIRED_RATE_UNKNOWN/);assert.match(h,/尚未指定新的55构造/)});
check('minusOneConditionShowsProvisionalNote',()=>{call("focusCondition('V4','minus_one')");assert.match(element('v4-list').innerHTML,/M006 · 2026-11-11讨论更新/);assert.match(element('v4-list').innerHTML,/不据此增加L2/)});
check('dataInitAndLegacyStateAreSeparated',()=>{const h=element('handoff').innerHTML;assert.match(h,/DATA_INITIALIZATION_ONLY/);assert.match(h,/0个完成结果/);assert.match(h,/15类INF/);assert.match(h,/37f05b15/)});
check('embeddedDataComplete',()=>assert.deepEqual(JSON.parse(payload),JSON.parse(fs.readFileSync(path.join(dir,'review_data.json'),'utf8'))));

const result={status:'PASSED',check_count:checks.length,checks,scope:'PURE_NODE_VM_UI_FUNCTION_UNIT_TEST_NOT_REAL_BROWSER',html_sha256:crypto.createHash('sha256').update(html).digest('hex'),actual_browser_control:false,device_execution:false};

process.stdout.write(JSON.stringify(result)+'\n');
