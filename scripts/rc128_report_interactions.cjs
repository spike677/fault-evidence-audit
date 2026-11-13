// Run the actual generated report script against its actual serialized data/cards.
// This checks interactions with a small DOM harness; it is not a browser-render claim.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const out = path.resolve(process.argv[2] || 'reports/rc128-actual-rework-20261113');
const html = fs.readFileSync(path.join(out, 'report.html'), 'utf8');
const dataText = html.match(/<script id="data" type="application\/json">([\s\S]*?)<\/script>/)[1];
const script = html.match(/<script>([\s\S]*?)<\/script><\/html>/)[1];
const sections = [...html.matchAll(/<article class="case" id="(RC-\d{3})">([\s\S]*?)<\/article>/g)];
const cards = sections.map(m => ({
  id: m[1], hidden: false, textContent: m[1] + ' ' + m[2].replace(/<[^>]*>/g, ' '),
  details: { open: false }, querySelector(selector) { assert.equal(selector, 'details'); return this.details; },
}));
const controls = Object.fromEntries(['q', 'decision', 'level', 'mode', 'shown', 'expand', 'collapse'].map(id => [id, {
  value: '', textContent: '', listeners: {}, addEventListener(type, f) { this.listeners[type] = f; },
}]));
controls.data = { textContent: dataText };
const document = {
  getElementById(id) { return controls[id]; },
  querySelectorAll(selector) {
    if (selector === 'article.case') return cards;
    assert.equal(selector, 'nav input,nav select');
    return ['q', 'decision', 'level', 'mode'].map(id => controls[id]);
  },
};
vm.runInNewContext(script, { document, JSON, console });
function set(id, value) { controls[id].value = value; controls[id].listeners.input(); }
const visible = () => cards.filter(c => !c.hidden);
const checks = [];
function check(label, expression) { assert.ok(expression, label); checks.push({ label, passed: true }); }
check('initial 128', visible().length === 128);
set('q', 'RC-023');
check('ID search', visible().length === 1 && visible()[0].id === 'RC-023');
set('q', ''); set('decision', 'PENDING');
check('definition advice filter 119', visible().length === 119);
controls.expand.onclick();
check('expand visible cases', visible().every(c => c.details.open));
controls.collapse.onclick();
check('collapse cases', visible().every(c => !c.details.open));
set('decision', 'COVERED'); set('mode', 'M009');
check('decision and mode intersection', visible().length === 2 && visible().every(c => ['RC-002', 'RC-075'].includes(c.id)));
set('mode', ''); set('decision', ''); set('level', 'PUBLIC_CODE_CORROBORATES_PART_OF_RELATION');
check('source level filter', visible().length === 2);
set('level', ''); set('q', 'THIS_QUERY_CANNOT_MATCH_172945');
check('no match', visible().length === 0);
set('q', '');
check('reset 128', visible().length === 128);
const result = { passed: true, method: 'ACTUAL_REPORT_JS_WITH_REAL_CARDS_AND_MINIMAL_DOM_HARNESS', checks,
  browser_render_verified: false,
  headless_edge_attempt: 'Process returned exit 0 but no DOM was captured; no browser-render success claimed.' };
fs.writeFileSync(path.join(out, 'interaction_validation.json'), JSON.stringify(result, null, 2) + '\n');
process.stdout.write(JSON.stringify(result) + '\n');
