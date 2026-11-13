// Execute published HTML's real JS/data against a minimal DOM. No browser-render claim.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const out = path.resolve(process.argv[2] || 'reports/current');
const log = path.resolve(process.argv[3] || 'reports/evidence/interaction_validation.json');
const html = fs.readFileSync(path.join(out, 'report.html'), 'utf8');
const dataText = html.match(/<script id="data" type="application\/json">([\s\S]*?)<\/script>/)[1];
const data = JSON.parse(dataText);
const script = html.match(/<script>([\s\S]*?)<\/script><\/html>/)[1];
const cards = [...html.matchAll(/<article class="case" id="(RC-\d{3})">([\s\S]*?)<\/article>/g)].map(m => ({
  id: m[1], hidden: false, textContent: m[1]+' '+m[2].replace(/<[^>]*>/g, ' '),
  details: {open: false}, querySelector(s) {assert.equal(s, 'details'); return this.details;},
}));
const controls = Object.fromEntries(['q','code','mode','source','shown','expand','collapse'].map(id => [id, {value:'', textContent:'', listeners:{}, addEventListener(k,f){this.listeners[k]=f;}}]));
controls.data = {textContent:dataText};
const document = {
  getElementById(id) {return controls[id];},
  querySelectorAll(s) {if(s==='article.case')return cards; assert.equal(s,'nav input,nav select');return ['q','code','mode','source'].map(k=>controls[k]);},
};
vm.runInNewContext(script,{document,JSON,console});
function set(k,v){controls[k].value=v;controls[k].listeners.input();}
const visible=()=>cards.filter(c=>!c.hidden);
const checks=[];
function check(label,ok){assert.ok(ok,label);checks.push({label,passed:true});}
const count=f=>Object.values(data).filter(f).length;
check('128 unique initial cards',cards.length===128 && new Set(cards.map(c=>c.id)).size===128 && visible().length===128);
set('q','RC-023');check('exact ID ignores IDs quoted in other records',visible().length===1&&visible()[0].id==='RC-023');
set('q','');set('source','ADOPTED_WEEKLY');check('trusted root filter',visible().length===110);
set('source','EMPTY_IN_HANDOFF');check('empty original root filter',visible().length===18);
set('source','');set('code','SUPPORTED');check('code support uses serialized data',visible().length===count(r=>r.code==='SUPPORTED'));
set('code','PARTIAL');set('mode','M010');check('code/mode intersection',visible().length===count(r=>r.code==='PARTIAL'&&r.modes.includes('M010')));
controls.expand.onclick();check('expand only visible',visible().every(c=>c.details.open)&&cards.filter(c=>c.hidden).every(c=>!c.details.open));
controls.collapse.onclick();check('collapse all',cards.every(c=>!c.details.open));
set('code','');set('mode','');set('q','WholeReduceMax');check('responsibility-code text searchable',visible().some(c=>c.id==='RC-030'));
set('q','THIS_QUERY_CANNOT_MATCH_172945');check('no match stays zero',visible().length===0&&controls.shown.textContent==='0 / 128');
set('q','');check('reset preserves 128',visible().length===128&&controls.shown.textContent==='128 / 128');
const result={passed:true,method:'ACTUAL_CURRENT_HTML_JS_WITH_SERIALIZED_DATA_AND_MINIMAL_DOM',checks,browser_render_verified:false};
fs.mkdirSync(path.dirname(log),{recursive:true});fs.writeFileSync(log,JSON.stringify(result,null,2)+'\n');
process.stdout.write(JSON.stringify(result)+'\n');
