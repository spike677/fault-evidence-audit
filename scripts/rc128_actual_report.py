"""Build/verify the bounded public-source RC128 re-review, without mutating audit state."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

from rc128_actual_findings import CASE_NOTES, PUBLIC_FINDINGS

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / 'reports/rc128-actual-rework-20261113'
RULE_VERSION = 'rc128-public-source-rework-20261113.1'
EXPECTED_INPUT_SHA = '683de7190a421fc56ab10c50e7edcc1d29d03f02dfd58b8f7b4fb95b34db5812'


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def write_jsonl(path, rows):
    path.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in rows), encoding='utf-8')


def freeze_inputs(out):
    inputs = out/'inputs'
    inputs.mkdir(exist_ok=True)
    sources = {
        'handoff128.jsonl': ROOT.parent/'数据/CANN_WEEKLY_EXTERNEL_SEARCH_HANDOFF_FOR_CODEX_20261111.jsonl',
        'baseline_30_modes.json': ROOT.parent/'work/cann_catalog_staging_20261110/baseline_30_modes.json',
        'baseline30_relation_index.json': ROOT/'reports/operator-mechanism-pilot-20261112/baseline30.json',
        'prior_classification128.jsonl': ROOT/'reports/operator-mechanism-rc128-20261113/classification128.jsonl',
        'trigger_library.md': ROOT/'knowledge/trigger_library.md',
        'precision_trigger_knowledge_v4.md': ROOT/'knowledge/precision_trigger_knowledge_v4.md',
    }
    manifest=[]
    for name, source in sources.items():
        dest=inputs/name
        if not dest.exists():
            shutil.copyfile(source, dest)
        manifest.append({'path':dest.relative_to(out).as_posix(), 'original_path':str(source),
                         'sha256':sha256(dest.read_bytes()).hexdigest(), 'bytes':dest.stat().st_size,
                         'role':'HISTORICAL_NOT_CURRENT' if name.startswith('prior_') else 'FROZEN_INPUT'})
    write_json(out/'input_manifest.json',manifest)


def github_object(receipt):
    structured=receipt.get('response',{}).get('structuredContent',{})
    return structured.get('issue',structured.get('pull_request',{})),structured


def component_text(out, component):
    path=out/component['text_file']
    # Connector strings may contain CRLF. Keep those bytes and character offsets;
    # HTTP selections were made through the existing normalized visible-text reader.
    return path.read_bytes().decode('utf-8') if component['platform']=='GITHUB' else path.read_text(encoding='utf-8')


def check_diff_hunks(text):
    """Check returned hunk lengths; this does not prove server-side all-file coverage."""
    lines=text.splitlines()
    checks=[]
    for i,line in enumerate(lines):
        match=re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',line)
        if not match:continue
        expected=(int(match[2] or 1),int(match[4] or 1))
        old=new=0
        for following in lines[i+1:]:
            if following.startswith(('@@','diff --git')):break
            if following.startswith('\\'):continue
            if following.startswith(' '):old+=1;new+=1
            elif following.startswith('-'):old+=1
            elif following.startswith('+'):new+=1
            elif not following:break
        checks.append({'header_line':i+1,'expected':expected,'observed':(old,new),'passed':(old,new)==expected})
    return {'hunks':len(checks),'returned_hunks_structurally_complete':bool(checks) and all(x['passed'] for x in checks),
            'failed_hunks':[x for x in checks if not x['passed']],
            'full_pr_file_set_verified':False,'semantic_whole_diff_reviewed':False}


def gather(out):
    components={}
    queries=[]
    associations=defaultdict(set)
    for path in sorted((out/'collection').glob('*.json')):
        for j in json.loads(path.read_bytes()):
            receipt=path.relative_to(out).as_posix()
            if j['kind']=='SEARCH':
                queries.append({'query_id':j['job_id'],'task_ids':j['task_ids'],'round':j.get('round',1),
                                'url':j['url'],'repository':j.get('repository','/'.join(j['url'].split('/')[3:5])),
                                'query':j.get('query',''),'outcome':j['outcome'],
                                'candidates':j.get('candidates',[]),'receipt':receipt,
                                'source_id':j['resource_id'],'scope':'FIRST_RETURNED_HTML_PAGE; NOT_EXHAUSTIVE'})
                queries[-1]['reused_current_run_fetch']=j.get('reused_current_run_fetch',False)
                continue
            k=j['resource_id']
            associations[k].update(j['task_ids'])
            if k not in components:
                components[k]={**j,'receipt':receipt,'platform':'GITCODE','review_selections':[]}
            components[k].setdefault('round_by_case',{}).update({i:j.get('round',1) for i in j['task_ids']})
    for path in sorted((out/'github').glob('*.json')):
        data=json.loads(path.read_bytes())
        if not isinstance(data,list):continue
        for n,j in enumerate(data):
            if 'task_ids' not in j:continue
            receipt=path.relative_to(out).as_posix()
            obj,structured=github_object(j)
            if j.get('kind')=='SEARCH':
                args=j.get('args',{})
                candidates=structured.get('issues', structured.get('results',[]))
                queries.append({'query_id':path.stem+'-'+str(n),'task_ids':j['task_ids'],
                                'round':j.get('round',1),'repository':args.get('repository_full_name',args.get('repository_name','')),
                                'query':args.get('query',''),'outcome':'READ_BLOCKED' if j.get('error') or j.get('response',{}).get('isError') else 'READABLE',
                                'candidates':[{'url':c.get('url',''),'text':c.get('title',c.get('path',''))} for c in candidates],
                                'receipt':receipt,'tool':j.get('tool','GITHUB_CONNECTOR'),
                                'scope':'TOP_3_OR_4_RETURNED_RESULTS; NOT_EXHAUSTIVE'})
                continue
            if j.get('kind')=='VERSION_ANCHOR':continue
            url=j['url']; kind=j['kind']
            suffix='' if kind in ('BODY','SOURCE') else '-'+kind
            k='GH-'+sha256(url.encode()).hexdigest()[:20]+suffix
            associations[k].update(j['task_ids'])
            decoded=out/'github/decoded'
            decoded.mkdir(exist_ok=True)
            if kind=='BODY':
                text=obj.get('title','')+'\n'+obj.get('body','')
                capture='COMPLETE_CONNECTOR_BODY; COMMENTS/ATTACHMENTS_NOT_ASSUMED_COMPLETE'
            elif kind=='SOURCE':
                text=structured.get('content','')
                capture='RETURNED_FILE_RANGE; NOT_WHOLE_FILE_UNLESS_RANGE_COVERS_FILE'
            else:
                text='\n\n'.join('FILE: '+p['filename']+'\n'+p.get('patch','') for p in structured.get('patches',[]))
                capture='RETURNED_PER_FILE_PATCHES; NO_UNREAD_FILE_CLAIMS'
            file=decoded/(k+'.txt')
            file.write_bytes(text.encode('utf-8'))
            components[k]={'resource_id':k,'url':url,'platform':'GITHUB','kind':kind,
                           'outcome':'READABLE' if text and not j.get('response',{}).get('isError') else 'READ_BLOCKED',
                           'text_file':file.relative_to(out).as_posix(),'raw_response_file':receipt,
                           'receipt':receipt,'fetched_at':j.get('checked_at'),
                           'sha256':sha256(text.encode()).hexdigest(),'bytes':len(text.encode()),
                           'capture_scope':capture,'review_selections':[],
                           'head_sha':obj.get('head_sha'), 'base_sha':obj.get('base_sha'),
                           'head_repo_full_name':obj.get('head_repo_full_name'),
                           'merged':obj.get('merged'), 'draft':obj.get('draft'), 'state':obj.get('state'),
                           'args':j.get('args',{}),'parent_url':j.get('parent_url'),
                           'round_by_case':{i:j.get('round',1) for i in j['task_ids']}}
            # The fetch calls emitted these body prefixes to the Agent. This is a bounded read,
            # distinct from the complete connector capture. Shorten to a conservative prefix.
            if kind=='BODY' and text:
                end=min(len(text),len(obj.get('title',''))+1+1500)
                components[k]['review_selections'].append(selection(text,0,end,'FETCH_TOOL_DISPLAY_PREFIX'))
            if kind=='SOURCE' and text:
                components[k]['review_selections'].append(selection(text,0,len(text),'EXPLICIT_RETURNED_SOURCE_RANGE'))
            if kind=='DIFF' and text:
                offset=0
                for patch in structured.get('patches',[]):
                    prefix='FILE: '+patch['filename']+'\n'
                    start=offset+len(prefix)
                    end=start+min(850,len(patch.get('patch','')))
                    components[k]['review_selections'].append(selection(text,start,end,'FETCH_TOOL_DISPLAY_PER_FILE_PREFIX'))
                    offset=start+len(patch.get('patch',''))+2
    sessions=read_jsonl(out/'read_sessions.jsonl')
    for session in sessions:
        if session['resource_id'] not in components:continue
        c=components[session['resource_id']]
        text=component_text(out,c)
        start,end=session['start'],session['end']
        if sha256(text[start:end].encode()).hexdigest()!=session['selection_sha256']:
            raise ValueError('Read-selection identity mismatch: '+session['resource_id'])
        c['review_selections'].append({**session,'text':text[start:end]})
    for key,c in components.items():
        c['task_ids']=sorted(associations[key])
        c['review_selections']=list({(s['start'],s['end']):s for s in c['review_selections']}.values())
        c['semantic_read_scope']='SELECTED_RANGES_ONLY' if c['review_selections'] else 'CAPTURED_NOT_SEMANTICALLY_REVIEWED'
        if c['kind']=='DIFF' and c['outcome']=='READABLE':
            c['diff_integrity']=check_diff_hunks(component_text(out,c))
    return list(components.values()),queries


def selection(text,start,end,origin):
    return {'start':start,'end':end,'total_chars':len(text),'text':text[start:end],
            'selection_sha256':sha256(text[start:end].encode()).hexdigest(),'origin':origin}


def findings(resources):
    rows=[]
    for n,f in enumerate(PUBLIC_FINDINGS,1):
        case,url,name,relation,near,boundary,link,level=f
        comps=[r for r in resources if r['url']==url or r['url'].startswith(url+'.') or r.get('parent_url')==url]
        # Fixed GitCode source jobs include the PR parent; GitHub paired source files are explicit.
        if url.endswith('/16699'):
            comps += [r for r in resources if r['platform']=='GITHUB' and r['kind']=='SOURCE' and 'split_qkv_rmsnorm_rope.py' in r['url']]
        body=next((r for r in comps if r['kind']=='BODY'),{})
        rows.append({'finding_id':f'PUBLIC-{n:03d}','task_id':case,'resource_url':url,
                     'candidate_mechanism':name,'specific_failure_relation':relation,
                     'nearest_original_modes':near.split(),'comparison_boundary':boundary,
                     'mechanism_relation_to_record':link,'evidence_level':level,
                     'event_relation_to_record':'UNDETERMINED',
                     'entity_type':'PUBLIC_TECHNICAL_CASE_SEPARATELY_RECORDED',
                     'resource_ids':sorted({r['resource_id'] for r in comps}),
                     'reviewed_component_ids':sorted({r['resource_id'] for r in comps if r['review_selections']}),
                     'publication_state':{k:body.get(k) for k in ('state','merged','draft')},
                     'hardware_validated_by_this_review':False,'formal_adoption':False})
    return rows


def case_results(out,resources,queries,public):
    original=read_jsonl(out/'inputs/handoff128.jsonl')
    prior={r['task_id']:r for r in read_jsonl(out/'inputs/prior_classification128.jsonl')}
    plan={r['task_id']:r for r in json.loads((out/'plan.json').read_bytes())}
    lines=(out/'inputs/handoff128.jsonl').read_bytes().splitlines(keepends=True)
    result=[]
    for n,raw in enumerate(original):
        key=raw['task_id']; old=prior[key]; rs=[r for r in resources if key in r['task_ids']]
        qs=[q for q in queries if key in q['task_ids']]
        scope=[r for r in rs if r['review_selections']]
        outcomes=['BOUNDED_SEARCH_COMPLETED']
        if any(q['outcome']=='READABLE' and not q['candidates'] for q in qs):outcomes.append('FINITE_QUERY_NO_MATCH')
        if any(q['outcome']=='READ_BLOCKED' for q in qs) or any(r['outcome']!='READABLE' for r in rs):outcomes.append('READ_BLOCKED')
        if scope:outcomes.append('SELECTED_CONTENT_READ')
        else:outcomes.append('NO_APPLICABLE_BODY_SELECTED')
        # No body read, partial review and lack of mechanism proof are independent dimensions.
        if any(r['outcome']=='READABLE' and r['semantic_read_scope']=='CAPTURED_NOT_SEMANTICALLY_REVIEWED' for r in rs):outcomes.append('CAPTURED_COMPONENTS_NOT_REVIEWED')
        if any(r.get('diff_integrity',{}).get('returned_hunks_structurally_complete') is False for r in rs):outcomes.append('RETURNED_DIFF_INCOMPLETE_OR_UNVERIFIABLE')
        if any(q['candidates'] for q in qs):outcomes.append('CANDIDATES_RETURNED_IN_BOUNDED_QUERY')
        if key=='RC-010':root_level='PUBLIC_CODE_CORROBORATES_DECLARED_MECHANISM'
        elif key in ('RC-023','RC-029'):root_level='PUBLIC_CODE_CORROBORATES_PART_OF_RELATION'
        elif key=='RC-031':root_level='PUBLIC_MECHANISM_KNOWN_ORIGINAL_PATH_UNCONFIRMED'
        elif raw['fault'].get('reported_root_cause','').strip():root_level='SOURCE_DECLARATION_NOT_INDEPENDENTLY_CONFIRMED'
        else:root_level='ROOT_UNLOCATED'
        if root_level in ('SOURCE_DECLARATION_NOT_INDEPENDENTLY_CONFIRMED','ROOT_UNLOCATED'):outcomes.append('CASE_MECHANISM_EVIDENCE_INSUFFICIENT')
        advice=old['decision']
        result.append({'task_id':key,'source_line':n+1,'original_line_sha256':sha256(lines[n]).hexdigest(),
                       'original_input':raw,'phase':plan[key]['phase'],'execution_status':'BOUNDED_REVIEW_COMPLETED',
                       'root_evidence_level':root_level,'current_review_note':CASE_NOTES[key[-3:]],
                       'processing_outcomes':outcomes,'query_ids':[q['query_id'] for q in qs],
                       'resource_ids':[r['resource_id'] for r in rs],
                       'reviewed_resource_ids':[r['resource_id'] for r in scope],
                       'public_finding_ids':[f['finding_id'] for f in public if f['task_id']==key],
                       'subproblems':old['subproblems'],
                       'mode_advice':{'decision':advice,'basis':'ORIGINAL30_DEFINITION_COMPARISON_WITH_SOURCE_LEVEL_LIMITS',
                                      'limitation':'建议归类不是根因或同事件确认；历史机理解释与本轮新取证分别显示。'},
                       'event_relation':'UNDETERMINED','weekly_event_confirmed':False,
                       'historical_source_quality_issues':old.get('source_quality_issues',[]),
                       'historical_analysis_scope':'REUSED_SUBPROBLEM_CHAIN; FRESH_PUBLIC_EVIDENCE_REVIEW_ABOVE',
                       'hardware_validated':False,'human_decision':None,'formal_adoption':False})
    return result


def make_summary(rows,resources,queries):
    return {'records':len(rows),'unique_case_ids':len({r['task_id'] for r in rows}),
            'phase_counts':dict(Counter(str(r['phase']) for r in rows)),
            'query_case_associations':sum(len(q['task_ids']) for q in queries),
            'query_receipts':len(queries),
            'unique_queries':len({(q.get('url'),str(q.get('repository')),q['query'],q.get('tool','HTTP')) for q in queries}),
            'resource_components':len(resources),
            'resources_by_kind':dict(Counter(r['kind'] for r in resources)),
            'readable_components':sum(r['outcome']=='READABLE' for r in resources),
            'blocked_components':sum(r['outcome']!='READABLE' for r in resources),
            'semantically_reviewed_components':sum(bool(r['review_selections']) for r in resources),
            'cases_with_selected_body_read':sum(any(r['kind']=='BODY' and r['review_selections'] and x['task_id'] in r['task_ids'] for r in resources) for x in rows),
            'cases_with_selected_content_read':sum(bool(r['reviewed_resource_ids']) for r in rows),
            'cases_without_applicable_selected_content':[r['task_id'] for r in rows if not r['reviewed_resource_ids']],
            'root_evidence_levels':dict(Counter(r['root_evidence_level'] for r in rows)),
            'definition_advice':dict(Counter(r['mode_advice']['decision'] for r in rows)),
            'outcomes_overlapping':dict(Counter(o for r in rows for o in r['processing_outcomes'])),
            'weekly_event_confirmed':0,'formal_adoption':0,'device_tests_executed':0,
            'counting_notes':['查询回执含本轮跨记录复用；不是独立网络请求次数。',
                              '条件/受阻/无匹配按查询和组件记录，可重叠，不把其和当作故障总数。',
                              '资源组件是正文、Diff、Patch或固定版本源码；一次PR的多个组件不是多份独立验证。',
                              '来源层覆盖建议与独立代码证实分列；不把PENDING建议数称作未执行任务数。']}


STYLE='''body{font:15px/1.65 system-ui,sans-serif;margin:0;color:#172d3b;background:#f2f6f7}header,main{max-width:1240px;margin:auto;padding:24px}header{background:#133b4e;color:white}a{color:#096698}header a{color:#c1e9ff}h1{font-size:25px}h2{font-size:20px;margin-top:28px}h3{font-size:17px}nav{position:sticky;top:0;background:#e3edf1;padding:12px;z-index:1;border-bottom:1px solid #aac0cc}input,select{padding:8px;margin:4px;max-width:95%}article,section.panel{background:white;border:1px solid #cad9df;border-radius:8px;margin:12px 0;padding:16px}summary{cursor:pointer;font-weight:650}table{width:100%;border-collapse:collapse;font-size:14px;margin:10px 0}td,th{border:1px solid #cedae0;padding:8px;vertical-align:top;text-align:left}th{background:#edf4f7}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f5f7;padding:10px;font-size:12px;max-height:450px;overflow:auto}.muted{color:#526a77}.warn{border-left:4px solid #c47d0b;padding-left:12px}.tag{display:inline-block;padding:2px 7px;border-radius:5px;background:#e7f0f5;margin:2px;font-size:12px}.metrics{display:flex;gap:16px;flex-wrap:wrap}.metric{padding:12px;background:#fff;color:#172d3b;border-radius:6px}.metric strong{font-size:24px}button{padding:6px 10px}.case-note{background:#fff7e6;padding:12px}code{overflow-wrap:anywhere}[hidden]{display:none!important}@media(max-width:700px){td,th{padding:5px;font-size:12px}header,main{padding:12px}}'''


JS='''const DATA=JSON.parse(document.getElementById('data').textContent);const cards=[...document.querySelectorAll('article.case')];function applyFilters(){const q=document.getElementById('q').value.toLowerCase(),d=document.getElementById('decision').value,l=document.getElementById('level').value,m=document.getElementById('mode').value;let n=0;cards.forEach((el,i)=>{const r=DATA[i],text=el.textContent.toLowerCase(),ok=(!q||text.includes(q))&&(!d||r.decision===d)&&(!l||r.level===l)&&(!m||r.modes.includes(m));el.hidden=!ok;if(ok)n++;});document.getElementById('shown').textContent=n+' / '+cards.length;}for(const el of document.querySelectorAll('nav input,nav select'))el.addEventListener('input',applyFilters);document.getElementById('expand').onclick=()=>cards.filter(x=>!x.hidden).forEach(x=>x.querySelector('details').open=true);document.getElementById('collapse').onclick=()=>cards.forEach(x=>x.querySelector('details').open=false);applyFilters();'''


def html_report(out,rows,resources,queries,public,summary):
    E=lambda x:escape(str(x))
    byid={r['resource_id']:r for r in resources}; qby={q['query_id']:q for q in queries}
    modes=json.loads((out/'inputs/baseline30_relation_index.json').read_bytes())['modes']
    modeby={m['mode_id']:m for m in modes}
    parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
           '<title>RC128 公开证据实际重审 · 2026-11-13</title><style>'+STYLE+'</style><header><h1>128条公开证据实际重审</h1>',
           '<p>免 computer_use：公开HTTP + GitHub连接器；查询与已读选段均有回执。完成有限审查不等于全部根因证实。</p>',
           '<div class="metrics">'+''.join(f'<div class="metric"><strong>{v}</strong><br>{label}</div>' for label,v in [('已处理唯一记录',summary['records']),('有正文选段审读',summary['cases_with_selected_body_read']),('查询记录（含复用）',summary['query_receipts']),('正式入库',0)])+'</div>',
           '<p><a href="results.jsonl">128条结果</a> · <a href="public_findings.jsonl">公开技术机理</a> · <a href="resource_audit.jsonl">资源/版本/读取范围</a> · <a href="search_audit.jsonl">逐条查询</a> · <a href="validation.json">校验</a> · <a href="rc128-actual-rework-20261113.zip">完整下载包</a></p></header>',
           '<nav><input id="q" placeholder="记录、算子、根因、来源或模式全文搜索"><select id="decision"><option value="">全部模式建议</option>'+''.join(f'<option>{E(x)}</option>' for x in summary['definition_advice'])+'</select>',
           '<select id="level"><option value="">全部证据层级</option>'+''.join(f'<option>{E(x)}</option>' for x in summary['root_evidence_levels'])+'</select>',
           '<select id="mode"><option value="">全部原30模式</option>'+''.join(f'<option>{E(m)}</option>' for m in modeby)+'</select><span id="shown"></span> <button id="expand">展开结果</button> <button id="collapse">收起</button></nav><main>',
           '<section class="panel"><h2>本轮边界与统计</h2><p class="warn">72条未读正文记录优先，随后复核56条。原输入逐字节保留；未读正文、无匹配、无法读取、候选不适用、原故障机理证据不足分别记录。公开案例关联到原记录的事件身份均未独立确认。新PR未合并时保留提案身份；测试声明不等于本轮设备验证。</p>',
           '<p>诊断链沿用：合法/来源条件 → 派生量或状态 → 路径与消费者 → 契约关系及破坏方式 → 参考和判别点。42/V4定义未变，不另做标签转换。M006的minus_one暂记、M026对齐证据待补、M004缓冲配置讨论均不升级为已证实。</p>',
           '<pre>'+E(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre></section>',
           '<section class="panel"><h2>重点公开机理：与原事件分开</h2><table><tr><th>记录/公开资料</th><th>候选机理与具体关系</th><th>证据等级及状态</th><th>原30相似项与边界</th></tr>']
    for f in public:
        parts.append(f'<tr><td><a href="#{f["task_id"]}">{f["task_id"]}</a><br><a href="{E(f["resource_url"])}">公开Issue/PR</a></td><td><b>{E(f["candidate_mechanism"])}</b><br>{E(f["specific_failure_relation"])}</td><td>{E(f["evidence_level"])}<br>{E(f["mechanism_relation_to_record"])}<br>事件 UNDETERMINED<br>{E(f["publication_state"])}</td><td>{E(" / ".join(f["nearest_original_modes"]))}<br>{E(f["comparison_boundary"])}</td></tr>')
    parts.append('</table></section><h2>128条逐项结果</h2>')
    filterdata=[]
    for r in rows:
        key=r['task_id']; raw=r['original_input']; near=sorted({m for s in r['subproblems'] for m in s.get('target_mode_ids',[])+s.get('nearest_original_modes',[])})
        filterdata.append({'id':key,'decision':r['mode_advice']['decision'],'level':r['root_evidence_level'],'modes':near})
        parts.append(f'<article class="case" id="{key}"><details><summary>{key} · {E(raw["fault"]["description"])} · {E(r["mode_advice"]["decision"])}</summary><p class="case-note">{E(r["current_review_note"])}</p><p>{E(r["root_evidence_level"])} · 事件关系 UNDETERMINED · 正式入库0</p><p>'+''.join('<span class="tag">'+E(x)+'</span>' for x in r['processing_outcomes'])+'</p>')
        parts.append('<h3>来源声明及限定</h3><p>'+E(raw['fault'].get('reported_root_cause','') or '原记录未定位根因')+'</p><p class="muted">Wiki/DTS的READABLE等上游状态只说明交接声明；本轮没有内网正文独立读取能力。摘要、正文、Diff和本轮设备验证分列。</p>')
        for s in r['subproblems']:
            parts.append('<h3>'+E(s['subproblem_id'])+' · '+E(s['decision'])+'</h3><table><tr><th>机理解释（保留其来源层级）</th><th>原30比较与缺口</th></tr><tr><td>'+E(s.get('root_cause',''))+'<br>'+E(s.get('contract_and_violation',''))+'</td><td>'+E(' / '.join(s.get('target_mode_ids',[])+s.get('nearest_original_modes',[])))+'<br>'+E(s.get('comparison_and_gap',''))+'</td></tr></table>')
            parts.append('<details><summary>五段诊断链、判别点和原文引用</summary><pre>'+E(json.dumps({k:s.get(k) for k in ['chain','evidence_ids','basis','original30_exclusion_review']},ensure_ascii=False,indent=2))+'</pre></details>')
        parts.append('<h3>本轮实际查询</h3><table><tr><th>轮次/仓库/查询</th><th>本次范围与结果</th></tr>')
        for qid in r['query_ids']:
            q=qby[qid]; link=q.get('url') or q['receipt']
            parts.append(f'<tr><td>R{q["round"]} · {E(q["repository"])}<br><a href="{E(link)}">{E(q["query"])}</a></td><td>{E(q["outcome"])} · 返回候选{len(q["candidates"])}<br>{E(q["scope"])}<br><a href="{E(q["receipt"])}">原始回执</a></td></tr>')
        parts.append('</table><h3>逐资料审读：正文、Diff、固定代码</h3>')
        for rid in r['resource_ids']:
            c=byid[rid]
            parts.append(f'<details><summary>{E(c["kind"])} · {E(c["url"])} · {E(c["outcome"])} · 已读选段{len(c["review_selections"])}</summary><p><a href="{E(c["url"])}">原网页</a> · <a href="{E(c["text_file"])}">已取得完整响应/文件范围</a> · <a href="{E(c["receipt"])}">回执</a></p><p>SHA-256 {E(c["sha256"])}<br>提交 {E(c.get("commit") or c.get("head_sha") or c.get("args",{}).get("ref") or "正文未提供固定版本")}<br>{E(c["capture_scope"])} / {E(c["semantic_read_scope"])}</p>')
            for s in c['review_selections']:
                parts.append('<p class="muted">精确字符范围 '+str(s['start'])+'—'+str(s['end'])+'；全文/返回范围共'+str(s['total_chars'])+'字符</p><pre>'+E(s['text'])+'</pre>')
            if not c['review_selections']:parts.append('<p>该组件仅捕获，未计为语义审读，不支持未读代码的结论。</p>')
            parts.append('</details>')
        if not r['resource_ids']:parts.append('<p>本轮有限查询未选择到适用正文，不将此记为资料全文不存在。</p>')
        parts.append('<details><summary>原输入与全部上游声明（非本轮确认）</summary><pre>'+E(json.dumps(raw,ensure_ascii=False,indent=2))+'</pre></details></details></article>')
    parts.append('<section class="panel"><h2>原30条定义边界索引</h2>')
    for m in modes:parts.append('<details><summary>'+E(m['mode_id']+' · '+m['mode_name'])+'</summary><pre>'+E(json.dumps(m,ensure_ascii=False,indent=2))+'</pre></details>')
    data=json.dumps(filterdata,ensure_ascii=False).replace('<','\\u003c')
    parts.append('</section></main><script id="data" type="application/json">'+data+'</script><script>'+JS+'</script></html>')
    (out/'report.html').write_text('\n'.join(parts),encoding='utf-8')


def validate_data(out,rows,resources,queries):
    errors=[]
    if sha256((out/'inputs/handoff128.jsonl').read_bytes()).hexdigest()!=EXPECTED_INPUT_SHA:errors.append('Original input bytes changed')
    ids={f'RC-{n:03d}' for n in range(1,129)}
    if {r['task_id'] for r in rows}!=ids or len(rows)!=128:errors.append('RC128 identity coverage mismatch')
    if any(not any(r['task_id'] in q['task_ids'] for q in queries) for r in rows):errors.append('Case without new query receipt')
    if any(q['round']>3 for q in queries):errors.append('Round budget exceeded')
    if any(r['formal_adoption'] or r['human_decision'] is not None or r['hardware_validated'] for r in rows):errors.append('Unauthorized acceptance/adoption/device claim')
    original_links={c['link'] for r in rows for c in r['original_input'].get('public_code_clues',[])}
    body_links={r['url'] for r in resources if r['kind']=='BODY'}
    missing=sorted(original_links-body_links)
    if missing:errors.append('Original PR not re-fetched: '+str(missing))
    # PR body + diff + patch + pinned source are one resource family, not four new candidates.
    families=defaultdict(set)
    for c in resources:
        if c['kind'] not in ('BODY','SOURCE'):continue
        family=c.get('parent_url') or c['url']
        for case,round_no in c.get('round_by_case',{}).items():
            if c['kind']=='BODY':families[(case,round_no)].add(family)
        for s in c['review_selections']:
            text=component_text(out,c)
            if s['selection_sha256']!=sha256(text[s['start']:s['end']].encode()).hexdigest():errors.append('Invalid quote range: '+c['resource_id'])
    if any(len(v)>4 for v in families.values()):errors.append('More than four body resources in one case/round')
    return {'passed':not errors,'errors':errors,'records':len(rows),'original_unique_pr_clues':len(original_links),
            'original_pr_clues_re_fetched':len(original_links & body_links),'max_body_resources_per_case_round':max(map(len,families.values()),default=0),
            'query_rounds':sorted({q['round'] for q in queries}), 'formal_adoption':0,'hardware_tests':0,
            'limitations':['有限搜索，不是全仓穷尽；原事件未独立确认。','SSR折叠讨论、附件、未读文件不算已核验。','555条未在本轮重跑或新增源码核验。']}


def manifest(out):
    files=[]
    for path in sorted(out.rglob('*')):
        if path.is_file() and path.name not in {'evidence_sha256_manifest.json','rc128-actual-rework-20261113.zip','build_result.txt'} and not path.name.endswith('.tmp') and not (path.parent==out and path.name.endswith('_output.txt')):
            raw=path.read_bytes();files.append({'path':path.relative_to(out).as_posix(),'sha256':sha256(raw).hexdigest(),'bytes':len(raw)})
    write_json(out/'evidence_sha256_manifest.json',files)
    return files


def build(out):
    freeze_inputs(out)
    resources,queries=gather(out)
    public=findings(resources)
    rows=case_results(out,resources,queries,public)
    summary=make_summary(rows,resources,queries)
    validation=validate_data(out,rows,resources,queries)
    policy={'rule_version':RULE_VERSION,'max_rounds_per_case':3,'max_new_body_resources_per_round':4,
            'existing_model_bridge_input_budget_chars':160000,'model_bridge_tasks_emitted_by_this_report':0,
            'method':'bounded public HTTP and GitHub connector; no computer_use',
            'interpretation':'原事件、公开机理、独立技术案例、来源声明分开；不自动继承ACCEPT。'}
    policy['fingerprint']=sha256(json.dumps(policy,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    write_json(out/'policy.json',policy)
    write_jsonl(out/'results.jsonl',rows);write_jsonl(out/'resource_audit.jsonl',resources)
    write_jsonl(out/'search_audit.jsonl',queries);write_jsonl(out/'public_findings.jsonl',public)
    write_jsonl(out/'failure_relations.jsonl',[{'task_id':r['task_id'],'source_level':r['root_evidence_level'],'current_review_note':r['current_review_note'],**s} for r in rows for s in r['subproblems']])
    write_jsonl(out/'mode_comparison.jsonl',[{'task_id':r['task_id'],**r['mode_advice'],'event_relation':r['event_relation'],'subproblem_advice':[{'subproblem_id':s['subproblem_id'],'decision':s['decision'],'target_mode_ids':s.get('target_mode_ids',[]),'nearest_original_modes':s.get('nearest_original_modes',[]),'explanation':s.get('comparison_and_gap','')} for s in r['subproblems']]} for r in rows])
    write_json(out/'summary.json',summary);write_json(out/'validation.json',validation)
    html_report(out,rows,resources,queries,public,summary)
    manifest(out)
    if not validation['passed']:raise ValueError(validation['errors'])
    print(json.dumps({'summary':summary,'validation':validation},ensure_ascii=False,indent=2))


def verify(out):
    errors=[]
    for f in json.loads((out/'evidence_sha256_manifest.json').read_bytes()):
        path=out/f['path']
        if not path.is_file() or sha256(path.read_bytes()).hexdigest()!=f['sha256']:errors.append(f['path'])
    rows=read_jsonl(out/'results.jsonl'); resources=read_jsonl(out/'resource_audit.jsonl');queries=read_jsonl(out/'search_audit.jsonl')
    v=validate_data(out,rows,resources,queries)
    if errors or not v['passed']:raise ValueError({'manifest_mismatch':errors,'validation':v})
    html=(out/'report.html').read_text(encoding='utf-8')
    if len(re.findall(r'<article class="case" id="RC-\d{3}">',html))!=128:raise ValueError('HTML case count mismatch')
    if make_summary(rows,resources,queries)!=json.loads((out/'summary.json').read_bytes()):raise ValueError('Summary mismatch')
    print(json.dumps({'passed':True,'manifest_files':len(json.loads((out/'evidence_sha256_manifest.json').read_bytes())),'records':len(rows)},ensure_ascii=False))


def package(out):
    verify(out)
    files=json.loads((out/'evidence_sha256_manifest.json').read_bytes())
    dest=out/'rc128-actual-rework-20261113.zip'
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for f in files:z.write(out/f['path'],f['path'])
        z.write(out/'evidence_sha256_manifest.json','evidence_sha256_manifest.json')
    print(json.dumps({'zip':str(dest),'bytes':dest.stat().st_size,'sha256':sha256(dest.read_bytes()).hexdigest()}))


def verify_staged(out):
    files=json.loads((out/'evidence_sha256_manifest.json').read_bytes())
    files += [{'path':name,'sha256':sha256((out/name).read_bytes()).hexdigest()} for name in ['evidence_sha256_manifest.json','rc128-actual-rework-20261113.zip']]
    command=['git','-c','safe.directory='+ROOT.as_posix(),'cat-file','--batch']
    proc=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    mismatches=[]
    try:
        for entry in files:
            rel=(out/entry['path']).relative_to(ROOT).as_posix()
            proc.stdin.write((':'+rel+'\n').encode());proc.stdin.flush()
            header=proc.stdout.readline().decode().strip().split()
            if len(header)!=3 or header[1]!='blob':raise ValueError('Not a staged blob: '+rel)
            remaining=int(header[2]);digest=sha256()
            while remaining:
                part=proc.stdout.read(min(1024*1024,remaining))
                if not part:raise ValueError('Unexpected end of staged blob: '+rel)
                digest.update(part);remaining-=len(part)
            if proc.stdout.read(1)!=b'\n':raise ValueError('Invalid git batch separator')
            if digest.hexdigest()!=entry['sha256']:mismatches.append(rel)
    finally:
        proc.stdin.close();proc.stdout.close();proc.wait()
    if mismatches:raise ValueError({'staged_byte_mismatches':mismatches})
    print(json.dumps({'passed':True,'staged_evidence_files_checked':len(files),'mismatches':0}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['build','verify','package','verify-staged'])
    p.add_argument('--out',type=Path,default=DEFAULT_OUT)
    a=p.parse_args()
    {'build':build,'verify':verify,'package':package,'verify-staged':verify_staged}[a.action](a.out.resolve())
