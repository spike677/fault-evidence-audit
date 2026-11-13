"""Current report entry point and read-only validators for the archived report.

The old RC-ID evidence grading and classification inheritance were retired.
Legacy helpers validate the immutable old policy; they never regenerate it.
"""
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_OUT=ROOT/'reports/archive/rc128-actual-rework-20261113'
EXPECTED_INPUT_SHA='683de7190a421fc56ab10c50e7edcc1d29d03f02dfd58b8f7b4fb95b34db5812'


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]



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



if __name__=='__main__':
    from rc128_trusted_report import main
    main()
