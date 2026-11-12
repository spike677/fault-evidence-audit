// Offline VM checks of the actual self-contained report script and controls.
// No browser automation, network request, knowledge edits or device execution.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const folder = path.resolve(process.argv.slice(2).find(x => !x.startsWith('--')) || __dirname);
const html = fs.readFileSync(path.join(folder, 'index.html'), 'utf8');
const raw = html.match(/<script type="application\/json" id="payload">([\s\S]*?)<\/script>/)[1];
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const actualIds = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));
const nodes = new Map();
function node(id) {
  assert.ok(actualIds.has(id), 'Missing actual HTML control: ' + id);
  if (!nodes.has(id)) nodes.set(id, {
    textContent: id === 'payload' ? raw : '', innerHTML: '', value: '',
    listeners: new Map(),
    addEventListener(event, listener) { this.listeners.set(event, listener); }
  });
  return nodes.get(id);
}
const context = vm.createContext({ document: { getElementById: node } });
vm.runInContext(script, context, { timeout: 15000 });
const run = expression => vm.runInContext(expression, context, { timeout: 15000 });
const checks = [];
function check(name, action) {
  try { action(); checks.push({ name, status: 'PASS' }); }
  catch (error) { checks.push({ name, status: 'FAIL', error: error.message }); }
}
function count(markup, cls) {
  return (markup.match(new RegExp('<article class="card ' + cls + '">', 'g')) || []).length;
}
function navigate(view) {
  node('nav').listeners.get('click')({ target: {
    closest(selector) {
      assert.equal(selector, 'button[data-view]');
      return { dataset: { view } };
    }
  } });
}

check('six_actual_views_render', () => {
  assert.equal(run('VIEWS.length'), 6);
  for (const id of run('VIEWS.map(v => v[0])')) {
    assert.ok(run('render(' + JSON.stringify(id) + ')').length > 200, id);
  }
});
check('all_53_original_pattern_cards_and_ids_render', () => {
  const patterns = JSON.parse(run('JSON.stringify(D.patterns53.patterns)'));
  assert.equal(patterns.length, 53);
  assert.equal(new Set(patterns.map(p => p.id)).size, 53);
  const markup = run('render("patterns")');
  assert.equal(count(markup, 'pattern'), 53);
  for (const p of patterns) assert.ok(markup.includes(run('esc(' + JSON.stringify(p.id + ' · ' + p.name) + ')')), p.id);
});
check('each_pattern_keeps_l2_profile_and_exclusion_boundary', () => {
  assert.equal(run('D.patterns53.patterns.filter(p => p.source_profile && p.source_profile.detect && Object.keys(p.source_profile.detect).length && p.boundary).length'), 53);
  const markup = run('render("patterns")');
  assert.equal((markup.match(/排除边界/g) || []).length, 53);
  assert.ok(markup.includes('&quot;detect&quot;'));
  assert.ok(markup.includes('UPSTREAM_DECLARATION_NOT_REAUDITED'));
});
check('all_42_items_requires_skip_and_control_scope_render', () => {
  const items = JSON.parse(run('JSON.stringify(D.api42.items42)'));
  const markup = run('render("api42")');
  assert.equal(count(markup, 'api42'), 42);
  assert.equal((markup.match(/完整Requires（项＋族）/g) || []).length, 42);
  assert.equal((markup.match(/完整Skip if（项＋族）/g) || []).length, 42);
  for (const item of items) {
    assert.ok(markup.includes(run('esc(' + JSON.stringify(item.id + ' · ' + item.name) + ')')), item.id);
    for (const clause of [...item.requires, ...item.skip_if]) {
      assert.ok(markup.includes(run('esc(' + JSON.stringify(clause) + ')')), item.id + ': ' + clause);
    }
    if (item.family_scope_constraint) assert.ok(markup.includes(run('esc(' + JSON.stringify(item.family_scope_constraint) + ')')));
  }
});
check('all_31_v4_classes_and_55_unique_constructions_render', () => {
  const markup = run('render("v4")');
  assert.equal(count(markup, 'v4class'), 31);
  assert.equal(count(markup, 'construction'), 55);
  assert.equal(run('new Set(D.v4.constructions.map(c => c.id)).size'), 55);
  assert.equal(run('D.v4.constructions.reduce((n,c) => n+c.class_ids.length,0)'), 64);
  for (const item of JSON.parse(run('JSON.stringify([...D.v4.classes,...D.v4.constructions])'))) {
    assert.ok(markup.includes(run('esc(' + JSON.stringify(item.id + ' · ' + item.name) + ')')), item.id);
  }
});
check('original_five_execution_methods_and_supplement_separate', () => {
  assert.equal(run('D.v4.execution_methods.length'), 5);
  assert.equal(run('D.v4.execution_methods.map(m=>m.method_id).sort().join(",")'), 'E1,E2,E3,E4,E5');
  assert.equal(run('D.v4.supplementary_methods.length'), 1);
  const markup = run('render("v4")');
  assert.equal(count(markup, 'method'), 5);
  assert.ok(markup.includes('补充跨流规程：来自应用要求'));
  assert.ok(markup.includes('不算原文第6方法'));
});
check('guidance_and_combination_indices_retained_without_execution_claim', () => {
  assert.equal(run('D.v4.guidance_index.length'), 195);
  assert.equal(run('D.v4.combination_guides.length'), 10);
  const markup = run('render("v4")');
  assert.ok(markup.includes('指导案例不计为独立历史故障、已证根因或设备执行'));
  assert.ok(markup.includes('展开195指导案例索引'));
});
check('id_filter_and_clear_use_actual_control_events', () => {
  navigate('api42');
  node('query').value = '1.2.8';
  node('query').listeners.get('input')();
  assert.equal(count(node('content').innerHTML, 'api42'), 1);
  assert.ok(node('content').innerHTML.includes('1.2.8'));
  node('reset').listeners.get('click')();
  assert.equal(node('query').value, '');
  assert.equal(count(node('content').innerHTML, 'api42'), 42);
  navigate('patterns');
  node('query').value = 'FP-A01';
  node('query').listeners.get('input')();
  const matched = count(node('content').innerHTML, 'pattern');
  assert.ok(matched >= 1 && matched < 53);
  assert.ok(node('content').innerHTML.includes('FP-A01'));
  node('reset').listeners.get('click')();
  assert.equal(count(node('content').innerHTML, 'pattern'), 53);
});
check('new_b16_only_in_current_upstream_appendix', () => {
  assert.equal(run('D.patterns53.patterns.some(p => p.id === "FP-B16")'), false);
  assert.ok(!run('render("patterns")').includes('FP-B16 ·'));
  assert.equal(run('D.upstream.frozen_pattern_count'), 53);
  assert.equal(run('D.upstream.remote_pattern_count'), 54);
  assert.ok(run('render("upstream")').includes('FP-B16'));
  assert.ok(run('render("upstream")').includes('上游实测宣称不是本报告独立复现'));
});
check('foundation_keeps_q2_and_distinguishes_proposed_from_implemented', () => {
  const markup = run('render("foundation")');
  for (const term of ['单位与表示域', '生命周期', '消费者', '五段解释链', '尚非完整自动根因引擎', '局部x→x′扰动不是y_ref→y_fault误差']) {
    assert.ok(markup.includes(term), term);
  }
  assert.equal(run('D.foundation.five_stage_chain.length'), 5);
  assert.ok(run('D.foundation.capability_layers.some(l => l.status === "执行另验收")'));
});
check('comparison_remains_directions_not_automatic_label_mapping', () => {
  const markup = run('render("comparison")');
  for (const term of ['检查方向，不是自动匹配', '不自动转换标签', '不生成53×42或53×55', '原schema', '原42不因普通shape大就自动满足1.3']) {
    assert.ok(markup.includes(term), term);
  }
});
check('unsafe_hrefs_rejected_and_text_escaped', () => {
  for (const url of ['javascript:alert(1)', 'data:text/html,x', '../secret', 'sources/../secret', 'sources/a\\b', 'file:///C:/secret']) {
    assert.equal(run('safeHref(' + JSON.stringify(url) + ')'), null, url);
    assert.ok(!run('link(' + JSON.stringify(url) + ',"blocked")').includes('<a '), url);
  }
  assert.ok(run('link("sources/api42_trigger_library_original.md","source")').includes('<a '));
  assert.ok(run('link("https://gitcode.com/liuhanwen8/ascend-op-fault-patterns","upstream")').includes('<a '));
  const malicious = '<img src=x onerror=alert(1)><script>alert(1)</script>';
  const markup = run('table([{content:' + JSON.stringify(malicious) + '}],[["content","text"]])');
  assert.ok(!markup.includes('<img') && !markup.includes('<script>'));
  assert.ok(markup.includes('&lt;img'));
});
check('html_payload_equals_complete_structured_review', () => {
  assert.deepEqual(JSON.parse(raw), JSON.parse(fs.readFileSync(path.join(folder, 'review.json'), 'utf8')));
});
check('no_external_assets_or_network_execution', () => {
  assert.ok(!/<script[^>]+src\s*=|<link[^>]+href\s*=|<iframe\b|<img[^>]+src\s*=/i.test(html));
  assert.ok(!/\bfetch\s*\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon/.test(script));
});

check('confirmed_precision_goal_and_other_layers_routed', () => {
  assert.equal(run('D.target.decision'), 'USER_CONFIRMED');
  const h = run('render("foundation")');
  for(const s of ['先确定分类目标','CANN算子精度','应用/推理引擎','AI框架','硬件/平台','不能只截取A组']) assert.ok(h.includes(s),s);
  assert.ok(run('render("comparison")').includes('不能单靠现有库完成'));
});
check('53_layer_scope_keeps_hardware_reference_and_framework_exception', () => {
  assert.equal(run('D.layer_scope.patterns.length'),53);
  const h=run('render("patterns","FP-F04")');
  assert.ok(h.includes('FRAMEWORK_ADAPTATION_SUBTYPE_DEFINED'));
  const a=run('D.layer_scope.patterns.find(p=>p.id==="FP-A11").layer_assessment');
  assert.equal(a.actual_incident_attribution,'UNKNOWN_WITHOUT_CASE_SPECIFIC_CODE_AND_EXECUTION_EVIDENCE');
  assert.equal(a.external_layer_definition_basis.hardware_physical_fault.status,'NOT_DEFINED_BY_THIS_PATTERN');
});

const result = {
  status: checks.every(c => c.status === 'PASS') ? 'PASS' : 'FAIL',
  runtime: process.version,
  scope: 'OFFLINE_VM_INTERACTION_NOT_BROWSER_DEVICE_OR_HISTORICAL_FAULT_VALIDATION',
  check_count: checks.length, checks
};
if (process.argv.includes('--write')) {
  fs.writeFileSync(path.join(folder, 'ui_validation.json'), JSON.stringify(result, null, 2) + '\n');
}
process.stdout.write(JSON.stringify(result, null, 2) + '\n');
process.exitCode = result.status === 'PASS' ? 0 : 1;
