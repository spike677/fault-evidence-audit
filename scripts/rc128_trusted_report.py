"""Publish trusted handoff causes separately from public-code corroboration."""
import argparse
from collections import Counter
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import subprocess
import zipfile

from rc128_report_layout import verify as verify_layout
from rc128_component_reader import hunk_signatures

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'reports/archive/rc128-actual-rework-20261113'
EVIDENCE=ROOT/'reports/evidence'
CURRENT=ROOT/'reports/current'
INPUTS=ROOT/'reports/inputs'
VERSION='trusted-handoff-code-review-20261113.1'
INPUT_SHA='683de7190a421fc56ab10c50e7edcc1d29d03f02dfd58b8f7b4fb95b34db5812'
CODE_LABELS={'SUPPORTED':'支持','PARTIAL':'部分支持','NOT_CORRESPONDING':'不对应','NOT_FOUND':'未找到','READ_BLOCKED':'读取受阻'}
MODE_LABELS={'COVERED':'原模式覆盖建议','EXTENSION_DISCUSSION':'扩展详情讨论','NEW_CANDIDATE_DISCUSSION':'新增模式讨论',
             'CONDITIONAL':'条件化归类建议','RELATED':'相似机理参考','OTHER_LAYER':'其他层分流',
             'MIXED':'多子问题分别处理','NO_DEFECT_DECLARED':'原文判非问题','DETAILS_NEEDED':'细机理待补充',
             'SOURCE_TEXT_VARIANT':'原文字样差异保留'}


def read_jsonl(p):
    return [json.loads(s) for s in p.read_text(encoding='utf-8-sig').splitlines() if s.strip()]


def write_json(p,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def write_jsonl(p,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in data),encoding='utf-8')


def trusted_sources(raw):
    out=[]
    for field in ['confirmed_internal_facts','related_internal_facts','dts_facts']:
        for i,fact in enumerate(raw.get(field,[])):
            out.append({'source_id':raw['task_id']+':'+field+':'+str(i),'json_pointer':'/'+field+'/'+str(i),
                        'trusted_as_handoff':True,'internal_original_read_in_this_stage':False,'content':fact})
    return out


def adopt_root(raw,review):
    original=raw['fault'].get('reported_root_cause','')
    chosen=review.get('adopt_from_source_id')
    primary=original
    status='ADOPTED_WEEKLY' if original.strip() else 'EMPTY_IN_HANDOFF'
    source_id=raw['task_id']+':fault:reported_root_cause'
    if not original.strip() and chosen:
        source=next(x for x in trusted_sources(raw) if x['source_id']==chosen)
        if review['source_consistency']['status'] not in ['CONSISTENT','CONSISTENT_COMPLEMENT']:
            raise ValueError('Cannot fill from an unresolved source association')
        primary=source['content']['root_cause'];status='ADOPTED_CONSISTENT_SUMMARY';source_id=chosen
    return {'original_text':original,'adopted_text':primary,'status':status,'source_id':source_id,
            'policy':'USER_TRUSTED_WEEKLY_AND_WIKI_DTS_SUMMARIES','independently_reproduced':False}


def read_sessions():
    p=EVIDENCE/'supplemental_read_sessions.jsonl'
    return read_jsonl(p) if p.exists() else []


def resource_text(r):
    return (SOURCE/r['text_file']).read_bytes().decode('utf-8') if r['platform']=='GITHUB' else (SOURCE/r['text_file']).read_text(encoding='utf-8')


def make_rows(raw_rows,notes,components,sessions,followups):
    indexed={r['task_id']:r for r in notes}
    if len(indexed)!=len(notes) or set(indexed)!={r['task_id'] for r in raw_rows}:
        raise ValueError('Authored review identities do not match the frozen input')
    baseline={m['mode_id']:m for m in json.loads((INPUTS/'baseline_30_modes.json').read_bytes())['modes']}
    reviews={r['resource_id']:r for r in components}
    old_resources=read_jsonl(SOURCE/'resource_audit.jsonl')
    lines=(INPUTS/'handoff128.jsonl').read_bytes().splitlines(keepends=True)
    rows=[]
    for i,raw in enumerate(raw_rows):
        key=raw['task_id'];review=indexed[key]
        root=adopt_root(raw,review)
        associated=[r for r in old_resources if key in r['task_ids']]
        urls=set(review['code_assessment']['accepted_urls'])
        evidence=[]
        for r in associated:
            accepted=any(r['url']==u or r['url'].startswith(u+'.') or r.get('parent_url')==u for u in urls)
            ranges=[{k:v for k,v in s.items() if k!='text'} for s in r['review_selections']]
            ranges += [s for s in sessions if s['resource_id']==r['resource_id']]
            evidence.append({'resource_id':r['resource_id'],'url':r['url'],'kind':r['kind'],'sha256':r['sha256'],
                             'source_path':(SOURCE/r['text_file']).relative_to(ROOT).as_posix(),
                             'commit':r.get('commit') or r.get('args',{}).get('ref'),
                             'code_relation':'ACCEPTED_FOR_STATED_CLAIM' if accepted else 'NOT_ADOPTED_AS_WEEKLY_FIX',
                             'read_ranges':ranges,'supplemental_review':reviews.get(r['resource_id']),
                             'capture_scope':r.get('capture_scope'), 'merged':r.get('merged'),
                             'retrieval_outcome':r['outcome']})
        new=[f for f in followups if key in f.get('task_ids',[])]
        comparisons=[]
        for mid in review['mode_assessment']['similar_mode_ids']:
            m=baseline[mid]
            comparisons.append({'mode_id':mid,'mode_name':m['mode_name'],
                'original_definition_fields':[f for f in m['original_fields'] if f['column'] in ['E','F','G','H']],
                'comparison':review['mode_assessment']['explanation'],'basis':'TRUSTED_CAUSE_VS_ORIGINAL_MODE_DEFINITION',
                'original_definition_not_modified':True})
        rows.append({'task_id':key,'source_line':i+1,'original_line_sha256':sha256(lines[i]).hexdigest(),
                     'original_input':raw,'trusted_root':root,'trusted_sources':trusted_sources(raw),
                     'source_consistency':review['source_consistency'],'code_assessment':review['code_assessment'],
                     'mode_assessment':review['mode_assessment'],
                     'original_mode_comparisons':comparisons,
                     'diagnosis':{'basis':'TRUSTED_SOURCE_STATEMENTS','stated_cause':root['adopted_text'],
                                  'object_clues_from_handoff':raw['fault'].get('operator_or_function',[]),
                                  'failure_relation_review':review['mode_assessment']['explanation'],
                                  'public_code_review':review['code_assessment']['explanation'],
                                  'unknowns_do_not_invalidate_adopted_cause':True},
                     'evidence':evidence,'followup_evidence':new,'public_code_event_relation':'UNDETERMINED',
                     'formal_adoption':False,'human_decision':None,'hardware_validated':False})
    return rows


def summarize(rows,components):
    return {'records':len(rows),'unique_case_ids':len({r['task_id'] for r in rows}),
            'root_status':dict(Counter(r['trusted_root']['status'] for r in rows)),
            'source_consistency':dict(Counter(r['source_consistency']['status'] for r in rows)),
            'code_corroboration':dict(Counter(r['code_assessment']['status'] for r in rows)),
            'mode_advice':dict(Counter(r['mode_assessment']['decision'] for r in rows)),
            'supplemental_components':len(components),
            'component_dispositions':dict(Counter(r['disposition'] for r in components)),
            'component_kinds':dict(Counter(r['kind'] for r in components)),
            'cases_with_supplemental_component_handling':len({k for c in components for k in c['task_ids']}),
            'historical_read_blocks_preserved':len({e['resource_id'] for r in rows for e in r['evidence'] if e['retrieval_outcome']!='READABLE'}),
            'component_pending':sum(r['disposition']=='PENDING' for r in components),
            'formal_adoption':0,'device_tests':0,
            'notes':['原根因可信采用与代码补证是两个独立指标。','空白原根因不是公开搜索无结果。',
                     '组件处理包含相关范围审读、比对共享及有依据排除，不声称所有文件逐行全文审读。']}


STYLE='''body{font:15px/1.65 system-ui,sans-serif;background:#f2f5f6;color:#173448;margin:0}header,main{max-width:1280px;margin:auto;padding:22px}header{background:#153b50;color:white}header a{color:#d4eeff}a{color:#096b97}h1{font-size:25px}h2{font-size:19px}nav{position:sticky;top:0;padding:10px;background:#e5eef2;z-index:1}input,select,button{padding:8px;margin:4px}article,.panel{padding:18px;margin:14px 0;border:1px solid #ccd9df;background:white;border-radius:7px}summary{cursor:pointer;font-weight:600}table{width:100%;border-collapse:collapse}td,th{border:1px solid #ccd9df;padding:9px;vertical-align:top;text-align:left}th{background:#edf3f6}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f5f7;padding:12px;max-height:450px;overflow:auto;font:13px/1.5 monospace}.root{border-left:5px solid #248771;padding:12px;background:#edf8f3}.warning{background:#fff4dc;padding:10px}.tag{background:#e8eff4;padding:2px 6px;border-radius:4px;margin:2px;display:inline-block}[hidden]{display:none!important}@media(max-width:700px){header,main{padding:12px}td,th{font-size:12px;padding:5px}}'''
JS='''const data=JSON.parse(document.getElementById('data').textContent);const cards=[...document.querySelectorAll('article.case')];function apply(){const q=document.getElementById('q').value.trim().toLowerCase(),code=document.getElementById('code').value,mode=document.getElementById('mode').value,source=document.getElementById('source').value;let n=0;for(const c of cards){const r=data[c.id],matches=/^rc-\\d{3}$/.test(q)?c.id.toLowerCase()===q:c.textContent.toLowerCase().includes(q);c.hidden=!!((q&&!matches)||(code&&r.code!==code)||(mode&&!r.modes.includes(mode))||(source&&r.source!==source));if(!c.hidden)n++;}document.getElementById('shown').textContent=n+' / 128';}for(const x of document.querySelectorAll('nav input,nav select'))x.addEventListener('input',apply);document.getElementById('expand').onclick=()=>cards.filter(c=>!c.hidden).forEach(c=>c.querySelector('details').open=true);document.getElementById('collapse').onclick=()=>cards.forEach(c=>c.querySelector('details').open=false);apply();'''


def html_report(rows,summary):
    E=lambda s:escape(str(s),quote=True)
    parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>128条周报可信根因与代码补证</title><style>'+STYLE+'</style><header><h1>128条周报可信根因与代码补证</h1><p>110条原根因逐字采用；18条原根因空白单列。Wiki/DTS摘要按可信交接资料使用，先区分对应范围。没有公开代码，不等于没有根因。</p><p>仅资料审读与代码补证；没有自动ACCEPT、正式入库或设备执行。</p><a href="results.jsonl">128条结构化结果</a> · <a href="README.md">阅读及复现说明</a> · <a href="../evidence/rc128-trusted-review.zip">完整离线下载包</a></header>',
           '<nav><input id="q" placeholder="编号、算子、原根因、代码关键词"><select id="code"><option value="">全部代码补证状态</option>'+''.join('<option value="'+k+'">'+v+'</option>' for k,v in CODE_LABELS.items())+'</select><select id="mode"><option value="">全部原模式</option>'+''.join('<option>M'+str(n).zfill(3)+'</option>' for n in range(1,31))+'</select><select id="source"><option value="">全部根因来源</option><option value="ADOPTED_WEEKLY">原周报根因</option><option value="EMPTY_IN_HANDOFF">原根因空白</option></select><button id="expand">展开筛选结果</button><button id="collapse">收起</button><span id="shown"></span></nav><main>',
           '<section class="panel"><h2>四个独立进度指标</h2><pre>'+E(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre><p>“代码支持”限定到明确主张；未合并PR按提案显示。组件处理包含适用范围审读、重复比对和排除，不表示所有响应都全文语义审读。</p></section>']
    filterdata={}
    for r in rows:
        key=r['task_id'];root=r['trusted_root'];fault=r['original_input']['fault'];code=r['code_assessment'];mode=r['mode_assessment']
        filterdata[key]={'code':code['status'],'modes':mode['similar_mode_ids'],'source':root['status']}
        parts.append('<article class="case" id="'+key+'"><details><summary>'+E(key+' · '+fault['description'])+' · '+CODE_LABELS[code['status']]+'</summary>')
        parts.append('<h2>1．周报描述、原根因及来源</h2><p>'+E(fault['description'])+'</p><p>原JSONL第'+str(r['source_line'])+'行；指针 /fault/reported_root_cause；原行SHA '+r['original_line_sha256']+'</p><pre>'+E(root['original_text'] or '【原文空白】')+'</pre>')
        parts.append('<h2>2．可信资料一致性</h2><p class="warning">'+E(r['source_consistency']['status']+'：'+r['source_consistency']['explanation'])+'</p><p>摘要按可信资料采用；本阶段未重新读取内部Wiki/DTS原文。</p>')
        for s in r['trusted_sources']:
            parts.append('<details><summary>'+E(s['source_id'])+'</summary><pre>'+E(json.dumps(s['content'],ensure_ascii=False,indent=2))+'</pre></details>')
        parts.append('<h2>3．采用根因与关系解释</h2><div class="root">'+E(root['adopted_text'] or '原文未给出可采用根因；不从相似PR猜测填入。')+'</div><p>'+E(mode['explanation'])+'</p><p>对象线索：'+E(', '.join(r['diagnosis']['object_clues_from_handoff']))+'。尚未写出的具体变量、时点、跨度及调用前提保持未说明。</p>')
        parts.append('<h2>4．Issue／PR、责任代码与修复</h2><p>'+E(code['explanation'])+'</p>')
        for url in code['accepted_urls']:parts.append('<p><a href="'+E(url)+'">'+E(url)+'</a></p>')
        for e in r['evidence']:
            href='../'+e['source_path'].removeprefix('reports/')
            parts.append('<details><summary>'+E(e['kind']+' · '+e['code_relation']+' · '+e['url'])+'</summary><p><a href="'+E(e['url'])+'">原始网页</a> · <a href="'+E(href)+'">已保存响应</a></p><p>读取状态 '+E(e['retrieval_outcome'])+'；固定提交 '+E(e['commit'])+'；SHA '+E(e['sha256'])+'</p>')
            if e['supplemental_review']:parts.append('<pre>'+E(json.dumps(e['supplemental_review'],ensure_ascii=False,indent=2))+'</pre>')
            # Exact quotes are shown within an explicit selection, never as a whole-file review.
            for s in e['read_ranges'][-3:]:
                if 'source_path' in s:p=ROOT/s['source_path']
                else:p=ROOT/e['source_path']
                t=p.read_bytes().decode('utf-8') if e['resource_id'].startswith('GH-') else p.read_text(encoding='utf-8')
                quote=t[s['start']:s['end']]
                if len(quote)>7000:quote=quote[:7000]+'\n【页面仅显示前7000字符；完整选段及原件见对应文件】'
                parts.append('<p>实际选段 '+str(s['start'])+'—'+str(s['end'])+'；选段SHA '+E(s.get('sha256',s.get('selection_sha256')))+'</p><pre>'+E(quote)+'</pre>')
            parts.append('</details>')
        # New public captures keep their own exact read ranges and links. A
        # captured full response is not labelled as a full semantic review.
        for s in read_sessions():
            if r['task_id'] not in s.get('task_ids',[]) or s['source_path'].startswith('reports/archive/'):
                continue
            p=ROOT/s['source_path'];t=p.read_text(encoding='utf-8');quote=t[s['start']:s['end']]
            href='../'+s['source_path'].removeprefix('reports/')
            parts.append('<details><summary>新责任代码/正文实际选段 '+E(s['resource_id'])+'</summary><a href="'+E(href)+'">完整保存文件</a><p>范围 '+str(s['start'])+'—'+str(s['end'])+'；SHA '+E(s['sha256'])+'</p><pre>'+E(quote)+'</pre></details>')
        for f in r['followup_evidence']:
            href='../'+f['path'].removeprefix('reports/')
            parts.append('<details><summary>本次定向补证：'+E(f['label'])+'</summary><a href="'+E(href)+'">完整回执</a><p>'+E(f.get('publication_state',''))+'</p><p>'+E(f['scope'])+'</p><pre>'+E(f.get('review_excerpt',''))+'</pre></details>')
        parts.append('<h2>5．代码补证状态</h2><p><b>'+CODE_LABELS[code['status']]+'</b>。该状态不改变已采用的原根因；公开代码事件身份未独立确认。</p><h2>6．与原30条关系</h2><p>'+E(MODE_LABELS[mode['decision']])+' · '+E(', '.join(mode['similar_mode_ids']) or '无直接对应')+'</p><p>'+E(mode['explanation'])+'</p>')
        for m in r['original_mode_comparisons']:
            parts.append('<details><summary>'+E(m['mode_id']+' '+m['mode_name'])+' 原定义</summary><pre>'+E(json.dumps(m,ensure_ascii=False,indent=2))+'</pre></details>')
        parts.append('<details><summary>原始handoff完整记录</summary><pre>'+E(json.dumps(r['original_input'],ensure_ascii=False,indent=2))+'</pre></details></details></article>')
    parts.append('</main><script id="data" type="application/json">'+json.dumps(filterdata,ensure_ascii=False).replace('<','\\u003c')+'</script><script>'+JS+'</script></html>')
    (CURRENT/'report.html').write_text('\n'.join(parts),encoding='utf-8')


def followup_index():
    rows=[]
    for p in sorted((EVIDENCE/'followup_github').glob('*.json')):
        j=json.loads(p.read_bytes());s=j['response'].get('structuredContent',{});obj=s.get('pull_request',s.get('commit',s))
        excerpt=obj.get('body') or obj.get('content') or obj.get('message') or json.dumps(s,ensure_ascii=False)
        if p.name=='RC094-API.json':excerpt='完整提交元数据；父提交85aa6c88b73d80d3cf15d932c2bc63b89e24740c。'
        rows.append({'task_ids':j['task_ids'],'path':p.relative_to(ROOT).as_posix(),'label':j['id'],
                     'url':s.get('display_url',s.get('url')),'review_excerpt':excerpt[:10000],
                     'publication_state':{k:obj.get(k) for k in ['state','merged','draft','head_sha','base_sha'] if obj.get(k) is not None},
                     'display_excerpt_complete':len(excerpt)<=10000,
                     'scope':'RECEIPT_CAPTURE; ONLY EXPLICITLY DISCUSSED CLAIMS ADOPTED; UI EXCERPT NOT FULL REVIEW'})
    for p in sorted((EVIDENCE/'followup_http/collection').glob('*.json')):
        for j in json.loads(p.read_bytes()):
            rows.append({'task_ids':j['task_ids'],'path':p.relative_to(ROOT).as_posix(),'label':j['job_id']+' '+j['url'],
                         'url':j['url'],'parent_url':j.get('parent_url'),
                         'review_excerpt':'查询/采集回执；'+j['outcome']+'；返回候选'+str(len(j.get('candidates',[]))),
                         'resource_id':j['resource_id'],'scope':'BOUNDED_QUERY_OR_CAPTURE'})
    return rows


def validate(rows,components):
    errors=[]
    if sha256((INPUTS/'handoff128.jsonl').read_bytes()).hexdigest()!=INPUT_SHA:errors.append('Input bytes changed')
    original=read_jsonl(INPUTS/'handoff128.jsonl')
    if len(rows)!=128 or [r['task_id'] for r in rows]!=[r['task_id'] for r in original]:errors.append('RC identity mismatch')
    if [r['original_input'] for r in rows]!=original:errors.append('Original fields changed')
    for r in rows:
        if r['trusted_root']['original_text']!=r['original_input']['fault'].get('reported_root_cause',''):errors.append('Root overwritten')
        if r['trusted_root']['original_text'].strip() and r['trusted_root']['adopted_text']!=r['trusted_root']['original_text']:errors.append('Trusted root downgraded/replaced')
        if r['code_assessment']['status'] not in CODE_LABELS:errors.append('Invalid code state')
        if r['code_assessment']['status'] in ['SUPPORTED','PARTIAL'] and not r['code_assessment']['accepted_urls']:
            errors.append('Corroboration without explicit source: '+r['task_id'])
        captured={e['url'].removesuffix('.diff').removesuffix('.patch') for e in r['evidence']}
        captured.update(e.get('url') for e in r['followup_evidence'])
        if any(url not in captured for url in r['code_assessment']['accepted_urls']):
            errors.append('Accepted URL has no captured material: '+r['task_id'])
        if r['formal_adoption'] or r['human_decision'] is not None or r['hardware_validated']:errors.append('Unauthorized claim')
    targets={r['resource_id'] for r in read_jsonl(SOURCE/'resource_audit.jsonl') if r['outcome']=='READABLE' and not r['review_selections']}
    if len(components)!=153 or {r['resource_id'] for r in components}!=targets:errors.append('153 component coverage mismatch')
    if any(r['disposition']=='PENDING' or not r['reason'] or not r['case_scope_review'] or
           (not r['exact_read_ranges'] and not r['shared_review_resources']) for r in components):errors.append('Unhandled component')
    resources={r['resource_id']:r for r in read_jsonl(SOURCE/'resource_audit.jsonl')}
    for c in components:
        if c['disposition'] not in ['PATCH_HUNKS_SHARED','DUPLICATE_CAPTURE']:continue
        own=resource_text(resources[c['resource_id']])
        other=[resource_text(resources[rid]) for rid in c['shared_review_resources']]
        try:
            if c['disposition']=='DUPLICATE_CAPTURE':valid=own in other
            else:
                signatures=hunk_signatures(own)
                valid=bool(signatures) and any(signatures==hunk_signatures(t) for t in other)
        except ValueError:valid=False
        if not valid:errors.append('Unproved sharing: '+c['resource_id'])
    for s in read_sessions():
        p=ROOT/s['source_path'];t=p.read_bytes().decode('utf-8') if s['resource_id'].startswith('GH-') else p.read_text(encoding='utf-8')
        if sha256(t[s['start']:s['end']].encode()).hexdigest()!=s['sha256']:errors.append('Quote mismatch: '+s['resource_id'])
    return {'passed':not errors,'errors':errors,'records':len(rows),'original_roots_retained':sum(bool(r['trusted_root']['original_text'].strip()) for r in rows),
            'components_handled':len(components),'formal_adoption':0,'device_tests':0}


def current_policy():
    policy={'version':VERSION,'input_sha256':INPUT_SHA,'trusted_weekly':True,'trusted_wiki_dts_summaries':True,
            'public_code_may_not_replace_original_root':True,'model_input_budget_chars':160000,
            'model_tasks_emitted':0,'rules':'Root adoption, code corroboration, event identity and mode advice are separate.'}
    inputs=[INPUTS/'handoff128.jsonl',INPUTS/'baseline_30_modes.json',EVIDENCE/'case_review_notes.jsonl',
            EVIDENCE/'component_reviews.jsonl',EVIDENCE/'supplemental_read_sessions.jsonl',
            Path(__file__),ROOT/'scripts/rc128_component_reader.py']
    policy['analysis_inputs_sha256']={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in inputs}
    policy['fingerprint']=sha256(json.dumps(policy,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return policy


def build():
    CURRENT.mkdir(exist_ok=True)
    notes=read_jsonl(EVIDENCE/'case_review_notes.jsonl');components=read_jsonl(EVIDENCE/'component_reviews.jsonl')
    rows=make_rows(read_jsonl(INPUTS/'handoff128.jsonl'),notes,components,read_sessions(),followup_index())
    result=validate(rows,components)
    if not result['passed']:raise ValueError(result)
    summary=summarize(rows,components)
    policy=current_policy()
    write_jsonl(CURRENT/'results.jsonl',rows);write_json(EVIDENCE/'summary.json',summary)
    write_json(EVIDENCE/'validation.json',result);write_json(EVIDENCE/'policy.json',policy)
    html_report(rows,summary)
    (CURRENT/'README.md').write_text('''# 128条周报可信根因与代码补证

[完整HTML](report.html)是唯一主要阅读入口；[128条JSONL](results.jsonl)保存原输入、根因、来源对照、责任代码及模式建议。

周报描述、原根因、Wiki/DTS摘要按用户指定作为可信交接资料。110条非空原根因逐字采用；空白根因只有在摘要关联明确且一致时才补充。没有公开代码不降低根因状态。来源调查中的“怀疑/待定位”字样同样原样保留，不提升为新的确定性技术结论。

公开代码状态只说明支持、部分支持、不对应、未找到或受阻。未合并PR仍为提案。已抓取不等于全文审读；每个组件给出选段、重复比对或排除依据。历史关系和上轮119条待确认不直接继承为当前结论。

目录分为inputs（可信原件）、current（本目录3份主要文件）、evidence（回执/审读/验证）、archive（旧报告）。历史包整体迁移且字节未改，见evidence/layout_migration.json；本地实验未发布。

完整离线包位于 ../evidence/rc128-trusted-review.zip；解压后打开reports/current/report.html。包包含当前引用的原始公开响应，不含所有历史报告ZIP。

复现：python scripts/rc128_actual_report.py build；verify；package。构建只读可信输入、已采集证据及人工编写的审读数据，不自动上网、调用模型或运行设备。验证日志位于evidence/。

正式入库、自动人工ACCEPT、现场drive及设备执行均为0。原30条、42/V4定义与运行state未修改。
''',encoding='utf-8')
    make_manifest();print(json.dumps({'validation':result,'summary':summary},ensure_ascii=False))


def make_manifest():
    files=[]
    paths=[p for folder in [CURRENT,INPUTS,EVIDENCE] for p in folder.rglob('*') if p.is_file()]
    # Include the immutable capture bundle required by relative evidence links, without old report ZIPs.
    paths += [p for p in SOURCE.rglob('*') if p.is_file() and p.suffix!='.zip']
    for p in sorted(set(paths)):
        if p.name in ['current_manifest.json','rc128-trusted-review.zip'] or p.suffix=='.tmp':continue
        raw=p.read_bytes();files.append({'path':p.relative_to(ROOT).as_posix(),'sha256':sha256(raw).hexdigest(),'bytes':len(raw)})
    write_json(EVIDENCE/'current_manifest.json',files)
    return files


def verify():
    rows=read_jsonl(CURRENT/'results.jsonl');components=read_jsonl(EVIDENCE/'component_reviews.jsonl')
    result=validate(rows,components)
    if not result['passed']:raise ValueError(result)
    if current_policy()!=json.loads((EVIDENCE/'policy.json').read_bytes()):
        raise ValueError('Current report is stale for its code, authored review or input policy; rebuild, never rewrite history.')
    for f in json.loads((EVIDENCE/'current_manifest.json').read_bytes()):
        p=ROOT/f['path']
        if not p.is_file() or sha256(p.read_bytes()).hexdigest()!=f['sha256']:raise ValueError('Manifest mismatch: '+f['path'])
    if summarize(rows,components)!=json.loads((EVIDENCE/'summary.json').read_bytes()):raise ValueError('Summary mismatch')
    html=(CURRENT/'report.html').read_text(encoding='utf-8')
    if len(re.findall(r'<article class="case" id="RC-\d{3}">',html))!=128:raise ValueError('HTML rows mismatch')
    for href in re.findall(r'href="([^"]+)"',html):
        if href.startswith(('http:','https:','#')) or href.endswith('rc128-trusted-review.zip'):continue
        if not (CURRENT/href).resolve().is_file():raise ValueError('Broken evidence link: '+href)
    if sorted(p.name for p in CURRENT.iterdir() if p.is_file())!=['README.md','report.html','results.jsonl']:raise ValueError('Extra current documents')
    print(json.dumps({'passed':True,'validation':result,'history':verify_layout()},ensure_ascii=False))


def package():
    verify();dest=EVIDENCE/'rc128-trusted-review.zip'
    files=json.loads((EVIDENCE/'current_manifest.json').read_bytes())
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for f in files:z.write(ROOT/f['path'],f['path'])
        z.write(EVIDENCE/'current_manifest.json','reports/evidence/current_manifest.json')
    print(json.dumps({'zip':dest.relative_to(ROOT).as_posix(),'bytes':dest.stat().st_size,'sha256':sha256(dest.read_bytes()).hexdigest()}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['build','verify','package','verify-staged'])
    a=p.parse_args()
    if a.action=='verify-staged':
        files=json.loads((EVIDENCE/'current_manifest.json').read_bytes())
        files += [{'path':x.relative_to(ROOT).as_posix(),'sha256':sha256(x.read_bytes()).hexdigest()} for x in [EVIDENCE/'current_manifest.json',EVIDENCE/'rc128-trusted-review.zip']]
        proc=subprocess.Popen(['git','-c','safe.directory='+ROOT.as_posix(),'cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        for f in files:
            proc.stdin.write((':'+f['path']+'\n').encode());proc.stdin.flush();head=proc.stdout.readline().decode().split()
            if len(head)!=3 or head[1]!='blob':raise ValueError('Not staged: '+f['path'])
            data=proc.stdout.read(int(head[2]));proc.stdout.read(1)
            if sha256(data).hexdigest()!=f['sha256']:raise ValueError('Staged byte mismatch: '+f['path'])
        proc.stdin.close();proc.stdout.close();proc.wait();print(json.dumps({'passed':True,'staged_files':len(files)}))
    else:{'build':build,'verify':verify,'package':package}[a.action]()


if __name__=='__main__':main()
