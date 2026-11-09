"""Primary, standalone V5 review report; dense audit data stays in JSON."""
from __future__ import annotations

import html
import json
import re

from .trigger_combinations import analyze, _current


def _esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def _pre(value):
    return "<pre>" + _esc(value if isinstance(value, str) else _json(value)) + "</pre>"


def _links(value):
    urls = sorted(set(re.findall(r'https?://[^\s<>"\\]+', _json(value))))
    return '<p>' + ' · '.join('<a target="_blank" rel="noopener noreferrer" href="' + _esc(u) + '">' + _esc(u) + '</a>' for u in urls) + '</p>' if urls else ''


def render(data):
    statistics = analyze(data)
    assessments = _current(data)
    cards = []
    mode_records = {m["source_case_id"]: m for m in data.get("mode_records", [])}
    for subject in data["subjects"]:
        source = subject["source_case"]
        cid = subject["case_id"]
        unit = subject.get("mode_id") if data["phase"] == "INIT" else cid
        unit = unit or cid
        values = [a for a in assessments if a["case_id"] == cid]
        sections = []
        for a in values:
            result = a["result"]
            summary = result.get("classification_summary", {})
            labels = []
            for scheme, key in ((data.get("input_condition_scheme", "REVISED42"), "rows"), ("V4", "v4_rows")):
                for row in result.get(key, []):
                    if row["applicability"] in {"APPLICABLE", "PARTIAL"}:
                        title = "V4条件类" if scheme == "V4" else "42条API输入条件（原版）" if scheme == "ORIGINAL42" else "42条API输入条件（修订版）"
                        constructions = ''.join('<li>' + _esc(c['construction_id']) + ' · ' + _esc(c.get('construction_recipe') or c['reason']) + '</li>' for c in row.get('construction_checks', []) if c['applicability'] in {'APPLICABLE','PARTIAL'})
                        labels.append(f'<details class="label"><summary>{title} {_esc(row["trigger_id"])} · {_esc(row["applicability"])} · 证据 {_esc(row["relation"])}</summary>'
                            + ('<h4>V4具体构造情形 · 设计建议</h4><ul>' + constructions + '</ul>' if constructions else '')
                            + _pre({k: row.get(k) for k in ("reason", "condition_fact_ids", "predicate_checks", "construction_checks", "coverage", "unknowns") if k in row}) + '</details>')
            for branch in result.get("external_branches", []):
                for leaf in branch.get("category_checks", []):
                    if leaf["applicability"] in {"APPLICABLE", "PARTIAL"}:
                        labels.append('<details class="label"><summary>Branch ' + _esc(leaf["category_id"]) + ' · ' + _esc(leaf["applicability"]) + '</summary>' + _pre(leaf) + '</details>')
            scenario_html = []
            for scenario in result.get("scenarios", []):
                links = [l for l in result.get("label_links", []) if scenario["scenario_id"] in l["scenario_ids"]]
                scenario_html.append('<details><summary>情景 ' + _esc(scenario["scenario_id"]) + ' · ' + _esc(scenario["title"]) + '</summary>'
                    + _pre({"情景依据": scenario, "条件关联": links}) + '</details>')
            facts = result.get("condition_facts", [])
            sections.append('<section class="assessment"><h3>' + _esc(a.get("issue_label", "原始定义")) + '</h3><p>'
                + _esc(summary.get("status", result.get("condition_processing_status", "LEGACY"))) + ' · '
                + _esc(summary.get("reason", "旧合同结果；没有情景记录时不推断同情景共现")) + '</p>'
                + ''.join(labels) + '<h4>技术机理</h4>' + _pre(result.get("details", []))
                + '<h4>情景与条件</h4>' + (''.join(scenario_html) or '<p>情景尚未确定；不据此声称条件同时触发。</p>')
                + '<p>情景间关系：' + _esc(result.get("scenario_relation", "UNKNOWN")) + '；情景内共现不等于充分触发。</p>'
                + '<details><summary>事实、原文引用及位置</summary>' + _pre(facts) + _links(facts) + '</details>'
                + '<h4>候选建议与正式状态</h4>' + _pre({"候选": result.get("candidate_proposal"),
                    "原模式定义对照": result.get("declared_comparison"), "正式建议": result["decision"],
                    "冲突": result.get("fact_conflicts", []), "未知项": summary.get("unknowns", []),
                    "输入范围": result.get("classification_scope"), "人工裁决": "未自动生成ACCEPT"}) + '</section>')
        origin = {"来源文件": source.get("source_file"), "Sheet": source.get("sheet"), "行": source.get("row"),
            "单元格": source.get("cell_locations"), "SHA256": source.get("source_sha256")}
        normalized = mode_records.get(cid)
        definition = ''
        if normalized:
            definition = '<h3>CANN真实失效机理 · failure_mechanism</h3><p>' + _esc(normalized['failure_mechanism']['text']) + ' · ' + _esc(normalized['failure_mechanism']['status']) + '</p>'
            definition += '<details><summary>A1 标准化模式定义、适用范围与排除边界</summary>' + _pre({k:normalized[k] for k in ('mode_id','mode_name','fault_object','failure_mechanism','observable_symptoms','input_trigger_conditions','execution_trigger_conditions','applicable_scope','exclusion_boundaries','validation_status')}) + '</details>'
            definition += '<h3>A4 执行条件与 E1–E5 方法</h3>' + _pre(normalized.get('execution_and_evidence', []))
        cards.append('<article class="case" data-unit="' + _esc(unit) + '"><h2>' + _esc(source.get("external_id") or subject.get("mode_id") or cid)
            + ' · ' + _esc(source.get("description", "")) + '</h2><p>' + _esc(source.get("root_cause_raw", "")) + '</p>'
            + '<details><summary>原始定义／周报记录与来源锚点</summary>' + _pre(origin) + _pre(source.get("raw", source)) + '</details>'
            + _links(source.get("raw", source))
            + definition
            + (''.join(sections) or '<p class="pending">UNASSESSED：没有当前有效分类。旧结果不自动继承。</p>')
            + '<details><summary>相关设计卡（未执行）</summary>' + _pre([d for d in data.get("designs", []) if d["case_id"] == cid]) + '</details></article>')
    definitions = []
    for scheme, taxonomy in ((data.get("input_condition_scheme", "REVISED42"), data["taxonomy"]), ("V4", data.get("v4_taxonomy"))):
        if taxonomy:
            definitions.append('<details><summary>' + scheme + ' · ' + _esc(taxonomy.get("definition_version", taxonomy.get("taxonomy_id")))
                + '</summary>' + ''.join('<details><summary>' + _esc(i["id"]) + ' · ' + _esc(i.get("name", "")) + '</summary>'
                    + _pre(i) + '</details>' for i in taxonomy["items"]) + '</details>')
    embedded = _json(statistics).replace('&', r'\u0026').replace('<', r'\u003c').replace('>', r'\u003e')
    baseline_section = ''
    if data.get('knowledge_profile'):
        registry = data.get('api42_registry') or {}
        counts = {axis:len({a['case_id'] for a in assessments if a.get('baseline_axis')==axis}) for axis in ('V4','API42')}
        baseline_section = '<section class="panel" id="baseline"><h2>Baseline 阶段进度</h2>' + _pre({
            'A1模式定义数':len(mode_records),'A2_V4归类模式数':counts['V4'],'A3_原始API42归类模式数':counts['API42'],
            'A4执行证据整理模式数':len({e['case_id'] for e in data.get('baseline_execution',[])}),
            '基线冻结':data.get('baseline_freeze',{'status':'NOT_FROZEN'}),
            '42原始基准':{**{k:registry.get(k) for k in ('source_file','actual_ids','duplicate_ids','missing_ids','unexpected_ids')},'SHA-256':registry.get('source_sha256')},
            '映射文件':'暂缺，不阻塞分类；禁止自动转换标签'}) + '<h3>运行预算、历史兼容与剩余阶段</h3>' + _pre(data.get('recovery', {})) + '<h3>横向审查</h3>' + _pre(data.get('baseline_review') or '尚未完成横向审查，不可冻结Baseline v1') + '</section>'
    header = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CANN V5 故障模式与条件审查</title><style>
body{{font:15px/1.6 system-ui,sans-serif;color:#172b4d;background:#f5f7fa;margin:0}}main{{max-width:1280px;margin:auto;padding:24px}}
nav{{position:sticky;top:0;background:#fff;padding:10px;z-index:2}}nav a{{margin-right:20px}}h1{{font-size:25px}}h2{{font-size:20px}}h3{{font-size:17px}}
article,section.panel{{background:#fff;border:1px solid #dce3ed;border-radius:8px;padding:20px;margin:16px 0}}details{{margin:8px 0}}summary{{cursor:pointer}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 ui-monospace,monospace;background:#f7f9fc;padding:10px}}
.label{{border-left:3px solid #476b9d;padding-left:10px}}.pending{{color:#8b5700}}.scroll{{overflow:auto}}button,input,select{{font:inherit;padding:6px;margin:4px}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;border-bottom:1px solid #ddd;padding:7px}}small,.muted{{color:#526477}}[hidden]{{display:none!important}}svg text{{font-family:system-ui,sans-serif}}a{{color:#205b9b}}
</style></head><body><main><h1>CANN V5 故障模式与条件审查</h1><p>运行 {_esc(data['run_id'])} · {_esc(data['phase'])} · {_esc(data.get('classification_contract', 'DENSE_V1'))}</p>
<p>{len(statistics['unit_ids'])} 个{('模式' if data['phase']=='INIT' else '来源case')}，{len(assessments)} 个当前子问题评估。描述归类、证据确认、候选建议、正式入库及实机执行分别记录。</p>
<nav><a href="#baseline">Baseline进度与横向审查</a><a href="#cases">模式／案例</a><a href="#combinations">组合分析</a><a href="#rules">分类定义</a><a href="#gaps">缺口与证据</a></nav>
{baseline_section}
<section id="cases"><h2>模式／案例详情</h2><input id="query" aria-label="搜索" placeholder="编号、算子、机理、来源或原文"><button id="reset">清除组合筛选</button><p id="case-count"></p>{''.join(cards)}</section>
<section id="combinations" class="panel"><h2>组合分析</h2><p>精确组合是已记录标签集合。灰点仅表示未关联，不能解释为不适用。同案共现不等于同情景，更不证明因果或充分触发。</p><select id="frame" aria-label="规则及证据口径"></select><select id="limit" aria-label="显示组合数量"><option value="20">前20个</option><option value="40">前40个</option><option value="all">全部</option></select><p id="combo-note"></p><div id="upset" class="scroll"></div><h3>精确组合</h3><div id="exact"></div><h3>两类共现：包含式交集</h3><div id="pairs"></div><p>点击数量或图柱回查模式／案例。未处理与已处理但无标签分别列明；空集合计入总数。</p></section>
<section id="rules" class="panel"><h2>独立冻结的分类定义</h2>{''.join(definitions)}<details><summary>版本映射（不传递覆盖）</summary>{_pre(data.get('mapping', {}))}</details></section>
<section id="gaps" class="panel"><h2>缺口与证据</h2>{_pre(data.get('gaps', []))}<details><summary>资料与采集状态</summary>{_pre(data.get('resources', []))}{_links(data.get('resources', []))}</details><p>完整当前投影见同目录 {_esc(data.get('report_json_name', 'report.json'))}；旧响应及人工历史保留在state。本报告不执行入库或设备实验。</p></section>
<script id="combination-data" type="application/json">{embedded}</script>'''
    return header + SCRIPT + '</main></body></html>'


SCRIPT = r'''<script>
'use strict';
const DATA=JSON.parse(document.getElementById('combination-data').textContent),$=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let selected=null;
function filter(){let count=0;for(const card of document.querySelectorAll('.case')){const show=(!selected||selected.has(card.dataset.unit))&&card.textContent.toLowerCase().includes($('query').value.toLowerCase());card.hidden=!show;if(show)count++;}$('case-count').textContent=`显示 ${count} / ${document.querySelectorAll('.case').length} 条来源记录。`;}
$('query').addEventListener('input',filter);$('reset').onclick=()=>{selected=null;$('query').value='';filter();};
function choose(ids){selected=new Set(ids);$('query').value='';filter();$('cases').scrollIntoView();}
document.addEventListener('click',e=>{const t=e.target.closest('[data-units]');if(t)choose(JSON.parse(t.dataset.units));});
document.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){const t=e.target.closest('g[data-units]');if(t){e.preventDefault();choose(JSON.parse(t.dataset.units));}}});
const button=ids=>`<button data-units="${esc(JSON.stringify(ids))}">${ids.length}</button>`;
DATA.frames.forEach((f,i)=>{$('frame').add(new Option(`${f.scheme} · ${f.definition_version} · ${f.axis}`,i));});
function render(){const f=DATA.frames[Number($('frame').value)];if(!f)return;const names=new Map(f.categories.map(c=>[c.id,c.name]));
const name=ks=>ks.length?ks.map(k=>k+' '+names.get(k)).join(' + '):'空集合（未关联标签）';
const n=$('limit').value,shown=n==='all'?f.exact_combinations:f.exact_combinations.slice(0,Number(n));
$('combo-note').textContent=`${f.unit_count} 个唯一 ${f.counting_unit}；已评估 ${f.assessed_unit_count}，未评估 ${f.unassessed_unit_ids.length}，已评估无标签 ${f.unlabeled_unit_ids.length}。完整 ${f.exact_combinations.length} 个组合互斥并合计 ${f.unit_count}；当前显示 ${shown.length} 个。旧合同缺情景 ${f.legacy_labeled_units_without_scenarios.length} 个，不推断同情景。`;
const left=300,top=155,step=44,row=19,W=Math.max(1000,left+shown.length*step+15),H=top+f.categories.length*row+20,max=Math.max(1,...shown.map(g=>g.count));
let svg=`<svg width="${W}" height="${H}" role="img" aria-label="已记录标签精确组合">`;
f.categories.forEach((c,i)=>{const y=top+i*row;svg+=`<text x="4" y="${y+4}" font-size="12">${esc(c.id+' '+c.name+' ('+c.count+')')}</text>`;});
shown.forEach((g,i)=>{const x=left+i*step,h=g.count/max*105;svg+=`<g tabindex="0" role="button" data-units="${esc(JSON.stringify(g.unit_ids))}" aria-label="${esc(name(g.categories))}: ${g.count}"><title>${esc(name(g.categories))}</title><rect x="${x-11}" y="${125-h}" width="22" height="${h}" fill="#466e9d"/><text x="${x}" y="${118-h}" text-anchor="middle" font-size="12">${g.count}</text>`;f.categories.forEach((c,j)=>{svg+=`<circle cx="${x}" cy="${top+j*row}" r="4" fill="${g.categories.includes(c.id)?'#172b4d':'#dce3ed'}"/>`;});svg+='</g>';});$('upset').innerHTML=svg+'</svg>';
$('exact').innerHTML='<table><thead><tr><th>已记录标签集合</th><th>去重数</th></tr></thead><tbody>'+shown.map(g=>`<tr><td>${esc(name(g.categories))}</td><td>${button(g.unit_ids)}</td></tr>`).join('')+'</tbody></table>';
$('pairs').innerHTML='<table><thead><tr><th>两类（可含其他类）</th><th>同案／模式</th><th>同情景</th></tr></thead><tbody>'+f.pairs.map(p=>`<tr><td>${esc(name(p.categories))}</td><td>${button(p.unit_ids)}</td><td>${button(p.same_scenario_unit_ids)}</td></tr>`).join('')+'</tbody></table>';}
$('frame').onchange=render;$('limit').onchange=render;filter();render();
</script>'''


def index_workbook(data):
    """Optional compact index; complete raw audit remains in report.json."""
    from .exporters import _table
    values = _current(data)
    cases = []
    for subject in data["subjects"]:
        source = subject["source_case"]
        current = [a for a in values if a["case_id"] == subject["case_id"]]
        cases.append({"case_id": subject["case_id"], "原编号": source.get("external_id", ""),
            "模式编号": subject.get("mode_id", ""), "描述": source.get("description", ""),
            "当前子问题数": len(current), "分类状态": "; ".join(a["result"].get("classification_summary", {}).get("status", "LEGACY") for a in current) or "UNASSESSED",
            "来源文件": source.get("source_file", ""), "Sheet": source.get("sheet", ""), "行": source.get("row", "")})
    mode_rows = cases if data["phase"] == "INIT" else [{"模式编号": r["mode_id"], "原定义": r.get("source_case", {}).get("description", "")}
        for r in (data.get("baseline") or {}).get("condition_index", [])]
    return {"schema_version": "1.0", "sheets": [
        _table("模式索引", mode_rows, list(mode_rows[0]) if mode_rows else ["模式编号", "原定义"]),
        _table("案例索引", cases, list(cases[0]) if cases else ["case_id", "描述", "分类状态"]),
        _table("证据清单", data.get("resources", []), list(dict.fromkeys(k for r in data.get("resources", []) for k in r)) or ["case_id", "url", "采集状态"]),
        _table("待解决问题", data.get("gaps", []), list(dict.fromkeys(k for r in data.get("gaps", []) for k in r)) or ["case_id", "kind", "reason"])]}
