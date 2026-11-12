"""Rebuild the five-case official-source pilot from actual tool receipts.

Offline packaging only: semantic decisions are explicitly Agent-curated in
pilot_reviews.json. This is not a keyword classifier or a new website client.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
import zipfile

from rc128_review import REPO, read, rows, sha, check_patch_hunks

PILOT=REPO/'reports/rc128-official-repo-pilot-20261112'
SOURCE=REPO/'reports/rc128-evidence-review-20261112-r2'
CASE_IDS=['RC-002','RC-003','RC-009','RC-030','RC-111']
REPO_RECEIPTS={
 'deepseek-ai/DeepSeek-R1':'REPO-DEEPSEEK', 'vllm-project/vllm':'REPO-VLLM',
 'vllm-project/vllm-ascend':'REPO-VLLM-ASCEND', 'Ascend/op-plugin':'REPO-OPPLUGIN',
 'Ascend/pytorch':'REPO-PTA','pytorch/pytorch':'REPO-PYTORCH'}


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


def jsonl(path,values):
    path.write_text(''.join(json.dumps(v,ensure_ascii=False,separators=(',',':'))+'\n'for v in values),encoding='utf-8',newline='\n')


def repository_key(url):
    """Canonical resource owner/repo, not a keyword found anywhere in a URL."""
    u=urlsplit(url);parts=u.path.strip('/').split('/')
    if u.scheme!='https':return None
    if u.hostname=='api.github.com'and len(parts)>=3 and parts[0]=='repos':
        return 'github.com/'+('/'.join(parts[1:3])).lower()
    if u.hostname in ['github.com','raw.githubusercontent.com']and len(parts)>=2:
        return 'github.com/'+('/'.join(parts[:2])).lower()
    if u.hostname=='gitcode.com'and len(parts)>=2:
        return 'gitcode.com/'+('/'.join(parts[:2])).lower()
    return None


def primary_source(url,registry):
    return repository_key(url)in {r['repository_key']for r in registry if r['verification_status']=='VERIFIED_NAMESPACE_AND_REPOSITORY'}


def receipt(id):return read(PILOT/'receipts'/(id+'.json'))
def structured(id):return receipt(id)['result']['structuredContent']


def registry():
    out=[]
    for name,id in REPO_RECEIPTS.items():
        value=structured(id)
        if value.get('repository_full_name','').lower()!=name.lower():raise ValueError('Repository identity mismatch: '+name)
        out.append(dict(repository_key='github.com/'+name.lower(),canonical_url='https://github.com/'+name,
            owner=value['owner']['login'],verification_status='VERIFIED_NAMESPACE_AND_REPOSITORY',
            basis='GitHub API owner identity plus user-approved official namespace; not a GitHub brand-verification badge.',
            receipt='receipts/'+id+'.json',searched_in_pilot=False))
    for name,basis in [('cann/ops-nn','SIDE-CANN-10622'),('cann/opbase','SIDE-OPBASE-RMSNORM')]:
        out.append(dict(repository_key='gitcode.com/'+name,canonical_url='https://gitcode.com/'+name,owner='CANN',
            verification_status='VERIFIED_NAMESPACE_AND_REPOSITORY',basis='Side repository header, canonical URL and user-approved CANN namespace.',
            receipt='side_observations.json#'+basis,searched_in_pilot=name.endswith('opbase')))
    return out


def split_diff(text):
    parts=[x for x in re.split(r'(?=^diff --git )',text,flags=re.M)if x.startswith('diff --git ')]
    return [dict(filename=re.search(r'^\+\+\+ b/(.*)$',p,re.M)[1],patch=p,hunks_complete=check_patch_hunks(p))for p in parts]


def search_audit(reg):
    out=[]
    for path in sorted((PILOT/'receipts').glob('*.json')):
        r=read(path)
        if r['tool']not in ['mcp__codex_apps__github_search_issues','mcp__codex_apps__github_search_prs']:continue
        match=re.search(r'RC(\d{3})-R(\d+)',r['id'])
        if not match:continue
        args=r['args'];resource_url='https://github.com/'+args['repository_full_name']
        if not primary_source(resource_url,reg):raise ValueError('Search outside verified pilot repositories')
        result=r['result'];candidates=result.get('structuredContent',{}).get('issues',[])
        out.append(dict(query_id=r['id'],task_id='RC-'+match[1],evidence_cycle=int(match[2]),
            repository=resource_url,query=args['query'],resource_type='ISSUE'if r['tool'].endswith('search_issues')else'PR',
            tool=r['tool'],receipt=path.relative_to(PILOT).as_posix(),executed=True,checked_at=r['captured_at'],
            outcome='FETCH_BLOCKED'if result.get('isError')else'CANDIDATES_RETURNED'if candidates else'NO_MATCH_IN_THIS_QUERY',
            candidate_count=len(candidates),result_limit=args['topn'],exhaustive_repository_review=False,
            candidates=[dict(url=c['url'],title=c['title'],primary_source=primary_source(c['url'],reg),
                body_returned_in_search_response=bool(c.get('body')),review_scope='TITLE_AND_METADATA_ONLY_UNLESS_SELECTED_RESOURCE_AUDIT_SAYS_OTHERWISE')for c in candidates]))
    for obs in read(PILOT/'side_observations.json')['observations']:
        if obs['kind']!='REPOSITORY_SEARCH':continue
        out.append(dict(query_id=obs['id'],task_id='RC-009',evidence_cycle=2,repository=obs['url'],query=obs['query'],
            resource_type='ISSUE',tool='CUA_SIDE_BROWSER_NATIVE_REPOSITORY_SEARCH',receipt='side_observations.json#'+obs['id'],
            executed=True,checked_at='2026-11-12 (client date; exact UI timestamp not recorded)',outcome=obs['outcome'],
            candidate_count=obs['total_results'],inspected_title_count=obs['inspected_title_count'],
            exhaustive_repository_review=False,filters=obs['filters'],candidates=obs.get('selected_issue_urls',[])))
    return out


def snapshot(name,text):
    p=PILOT/'evidence/decoded'/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(text,encoding='utf-8',newline='')
    return p.relative_to(PILOT).as_posix()


def build():
    reg=registry();queries=search_audit(reg);reviews=read(PILOT/'pilot_reviews.json')['cases']
    inputs={r['task_id']:r for r in rows(SOURCE/'results.jsonl')}
    for r in reviews:
        r['original_input']=inputs[r['task_id']]['original_input'];r['source_jsonl_line']=int(r['task_id'][-3:])
        r['manual_accept_created']=False;r['hardware_validated']=False
    resources=[]
    def add(id,url,kind,capture,scope,**extra):
        if not primary_source(url,reg):raise ValueError('Primary evidence outside official allowlist: '+url)
        resources.append(dict(resource_id=id,url=url,kind=kind,primary_source=True,capture_status=capture,review_scope=scope,**extra))
    for id,name,kind,url in [
        ('SIDE-DEEPSEEK-README','DeepSeek-R1-README.md','MODEL_GUIDANCE','https://github.com/deepseek-ai/DeepSeek-R1'),
        ('SIDE-RC111-PINNED-SCHEMA','npu-schema.yaml','API_CONTRACT','https://github.com/Ascend/op-plugin/blob/80fed808369177247c42095b345160a1ecee432d/op_plugin/config/op_plugin_functions.yaml'),
        ('SIDE-RC111-TORCH-SDPA','torch-v2.6-functional.py','API_CONTRACT','https://github.com/pytorch/pytorch/blob/v2.6.0/torch/nn/functional.py')]:
        text=structured(id)['content'];path=snapshot(name,text)
        markers={'MODEL_GUIDANCE':'Set the temperature within the range','API_CONTRACT':'- func: npu_fusion_attention('if name.endswith('.yaml')else'scale_factor = 1 / math.sqrt(query.size(-1)) if scale is None else scale'}
        marker=markers[kind];start=text.index(marker)
        end=text.index('\n',start)
        add(id,url,kind,'FULL_TEXT_CAPTURED_REVIEWED_SELECTED_RANGE','Side核对选段；全文件语义未审读',file=path,sha256=sha(PILOT/path),
            quote=text[start:end],line_start=text[:start].count('\n')+1,quote_exact_in_snapshot=True,
            receipt='receipts/'+id+'.json',full_source_semantics_reviewed=False)
    issue=structured('SIDE-RC003-CONCURRENCY-ISSUE')['issue'];path=snapshot('vllm-ascend-14118.md',issue['body'])
    add('GH14118',issue['url'],'ISSUE','BODY_CAPTURED_SELECTED_REPRODUCTION_REVIEWED','标题及复现段落；长脚本与全部评论未审读',
        file=path,sha256=sha(PILOT/path),title=issue['title'],receipt='receipts/SIDE-RC003-CONCURRENCY-ISSUE.json',weekly_event_confirmed=False)
    filelist=structured('SIDE-PR12123-FILES')['filenames'];pr=structured('PR-DEQUANT-12123')['pull_request']
    files=[]
    for n in range(1,len(filelist)+1):
        id=f'SIDE-PR12123-FILE-{n}';p=structured(id)['patch']
        path=snapshot(f'vllm-12123-{n}.patch',p['patch'])
        files.append(dict(filename=p['filename'],file=path,sha256=sha(PILOT/path),hunks_complete=check_patch_hunks(p['patch']),receipt='receipts/'+id+'.json'))
    if {f['filename']for f in files}!=set(filelist)or len(files)!=pr['changed_files']or not all(f['hunks_complete']for f in files):
        raise ValueError('PR12123 per-file completeness is not proven')
    path=snapshot('vllm-12123-body.md',pr['body'])
    add('GH12123','https://github.com/vllm-project/vllm-ascend/pull/12123','PR','ALL_CHANGED_FILES_PATCHES_CAPTURED',
        'Side读最终3文件Diff；API逐文件核验，不等同完整函数/仓库审读',files=files,body_file=path,
        head_sha=pr['head_sha'],merge_commit_sha=pr['merge_commit_sha'],changed_file_count=3,hardware_validated=False,weekly_event_confirmed=False)
    raw=PILOT/'evidence/side/CANN-10622.diff';parts=split_diff(raw.read_text(encoding='utf-8'));patch=PILOT/'evidence/side/CANN-10622.patch'
    text=patch.read_text(encoding='utf-8');commit=re.search(r'^From ([0-9a-f]{40}) ',text)[1]
    if len(parts)!=2 or not all(p['hunks_complete']for p in parts):raise ValueError('CANN raw diff is incomplete')
    add('CANN10622','https://gitcode.com/cann/ops-nn/pull/10622','PR','SIDE_DOWNLOADED_RAW_DIFF_AND_EMAIL_PATCH',
        '2文件、2个完整hunk；未走读GEMM内核完整实现',file=raw.relative_to(PILOT).as_posix(),sha256=sha(raw),
        email_patch=patch.relative_to(PILOT).as_posix(),commit=commit,changed_file_count=2,
        files=[{k:v for k,v in p.items()if k!='patch'}for p in parts],
        quote='enableGemm16In32Out',public_issue='https://gitcode.com/cann/ops-nn/issues/5928',
        public_pr_issue_link='EXPLICIT_PUBLIC_TRACKING_LINK_NOT_WEEKLY_EVENT_IDENTITY',weekly_event_confirmed=False,
        capture_attempts=[dict(tool='web__run.open',status='FETCH_BLOCKED',receipt='receipts/GITCODE-DIRECT.json'),
                          dict(tool='CUA_SIDE_BROWSER',status='BODY_AND_RAW_DIFF_READ',receipt='side_observations.json#SIDE-CANN-10622')])
    for number in [8752,8766]:
        resources.append(dict(resource_id=f'CANN-UNREAD-{number}',url=f'https://gitcode.com/cann/ops-transformer/pull/{number}',kind='PR',
            primary_source=False,source_status='USER_SUPPLIED_CANN_NAMESPACE_REPOSITORY_NOT_SIDE_VERIFIED_IN_PILOT',
            capture_status='FETCH_BLOCKED_IN_WEB_TOOL',review_scope='未获取正文或Diff；Side未尝试，不能宣称Side也受阻。',
            receipt='receipts/GITCODE-DIRECT.json',supports_weekly_root=False,weekly_event_confirmed=False))
    for obs in read(PILOT/'side_observations.json')['observations']:
        if obs['kind']=='ISSUE'and'gitcode.com'in obs['url']:
            add(obs['id'],obs['url'],'ISSUE','BROWSER_VISIBLE_BODY_READ_SELECTED_QUOTES_ARCHIVED',obs['read_scope'],
                quotes=obs['quotes'],receipt='side_observations.json#'+obs['id'],complete_raw_page_snapshot=False)
    for row in reg:
        row['searched_in_pilot']=any(repository_key(q['repository'])==row['repository_key']for q in queries)
    policy=dict(primary_repositories=reg,selection_rule='先按核实过的owner/repo筛选，再由Agent比对事实；官方来源不等于同事件。',
        personal_forks_and_blogs='LOCATOR_ONLY_NOT_PRIMARY_ROOT_CAUSE_EVIDENCE',
        contribution_rule='上游官方PR可来自个人head fork，以目标官方仓与固定提交/文件为准。',
        unresolved_github_cann='cann/ops-nn GitHub API返回404；不能推断GitCode同仓不存在或把同PR号移植过去。',
        allowlist_is_pilot_scope_not_all_official_repositories=True)
    write(PILOT/'repository_policy.json',policy);jsonl(PILOT/'search_audit.jsonl',queries)
    jsonl(PILOT/'resource_audit.jsonl',resources);jsonl(PILOT/'pilot_results.jsonl',reviews)
    summary=dict(cases=len(reviews),case_ids=CASE_IDS,source_commit=read(PILOT/'pilot_reviews.json')['source_commit'],
        search_requests=len(queries),search_requests_by_case=dict(Counter(q['task_id']for q in queries)),
        evidence_cycles=sum(len(r['cycles'])for r in reviews),official_repositories_verified=len(reg),
        searched_repositories=len({repository_key(q['repository'])for q in queries}),
        bounded_empty_queries=sum(q['outcome']=='NO_MATCH_IN_THIS_QUERY'for q in queries),
        resource_records=len(resources),reviewed_resource_records=sum('FETCH_BLOCKED'not in r['capture_status']for r in resources),
        blocked_web_tool_url_attempts=3,code_prs_with_changed_file_patch_coverage=2,
        independently_confirmed_weekly_events=0,formal_adoptions=0,device_runs=0,
        source_input_sha256=sha(SOURCE/'sources/original/handoff.jsonl'),
        full128_rerun=False,observations_cannot_be_counted_as_independent_corroboration=True,
        blocked_vs_success='保留Web工具受阻原回执；本次CANN #10622 Side读取和下载成功，不能把工具级错误写成站点全局不可访问。')
    write(PILOT/'summary.json',summary)
    render(dict(summary=summary,cases=reviews,searches=queries,resources=resources,policy=policy))
    hashes={p.relative_to(PILOT).as_posix():sha(p)for p in sorted(PILOT.rglob('*'))if p.is_file()and p.name not in ['manifest.json','validation.json','test_results.txt','ui_validation.json']}
    write(PILOT/'manifest.json',dict(schema_version='OFFICIAL-SOURCE-PILOT-1',payload_sha256=hashes,
        analysis_script_sha256=sha(Path(__file__)),old_archives_modified=False,source_input_sha256=summary['source_input_sha256']))
    result=verify();write(PILOT/'validation.json',result);return result


HTML=r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>官方仓与Side：5条证据试跑</title><style>body{font:16px/1.7 system-ui,"Microsoft YaHei";background:#f4f6fa;color:#1d2b3a;margin:0}main{max-width:1300px;margin:auto;padding:28px}article,section{background:white;border:1px solid #d4dfe7;border-radius:8px;padding:20px;margin:16px 0}h1{font-size:28px}h2{font-size:21px}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:8px;border:1px solid #d4dfe7;text-align:left;vertical-align:top}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f8;padding:12px;font-size:13px}.muted{color:#576777}.warn{color:#944600}input{font:inherit;padding:9px;width:75%;max-width:750px}a{color:#145d83;overflow-wrap:anywhere}.scroll{overflow:auto}blockquote{border-left:3px solid #468bb0;padding-left:12px}button{padding:9px;font:inherit}.metrics{display:flex;gap:12px;flex-wrap:wrap}.metrics strong{font-size:24px}details{margin:10px 0}</style><main><h1>官方仓优先＋Side实读：5条试跑</h1><p>先筛选来源，再核对具体事实。已有证据足够则停止扩搜。本报告不声称128条已完成，也不把代码技术案例认作客户事件。</p><div id="metrics" class="metrics"></div><section><b>关键发现</b><p>CANN官方#10622已通过Side读取正文、Issue和两个文件Diff，并下载原始Diff/Email Patch；此前Web工具失败不代表当前Side失败。vLLM-Ascend #12123已核对三个文件及最终测试。官方仓内仍存在大量只同名、同模型或同数字的无关候选。</p><p>所有客户事件身份及入库仍待确认；未知、无匹配查询、工具受阻与资料不支持分别保留。机器人评论、旧版评论和最终源码分开处理。</p><a href="manifest.json">SHA清单</a> · <a href="pilot_results.jsonl">逐条JSONL</a> · <a href="resource_audit.jsonl">实际读取范围</a></section><input id="q" aria-label="筛选" placeholder="RC编号、仓库、算子或失效关系"><button id="reset">清除</button><div id="count"></div><div id="cases"></div><section><h2>官方来源筛选</h2><p>核实过的仓库不等于本轮全部搜索过；按实际查询单列。</p><div id="repos" class="scroll"></div><p>个人Fork、博客、同名仓不能作为主要根因证据；官方PR允许个人贡献分支，仍核对目标仓和固定代码。GitHub CANN仓404不传播成GitCode故障不存在。</p></section><section><h2>实际查询（命中不等于已读）</h2><div id="searches" class="scroll"></div></section><section><h2>实际审读资料及代码</h2><div id="resources"></div></section><section><h2>统计与范围</h2><pre id="summary"></pre><p>源码选段、API返回正文、完整变更hunk和设备验证属于不同层级。本报告设备执行、人工ACCEPT、正式入库均为0。</p></section></main><script id="data" type="application/json">__DATA__</script><script>
const D=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id),esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function anchor(url,label=url){if(!/^https:\/\/|^(evidence|receipts)\//.test(url))return esc(label);return '<a href="'+esc(url)+'">'+esc(label)+'</a>'}
function caseCard(r){return '<article id="'+esc(r.task_id)+'"><h2>'+esc(r.task_id+' '+r.title)+'</h2><p><b>实际发现：</b>'+esc(r.finding)+'</p><p><b>具体关系：</b>'+esc(r.failed_relation)+'</p><p><b>证据范围：</b>'+esc(r.evidence_level)+'</p><p><b>搜索合理性：</b>'+esc(r.search_assessment)+'</p><p><b>事件／机理：</b>'+esc(r.event_relation)+' / '+esc(r.mechanism_relation)+'</p><p>'+esc(r.entity_type)+'</p><ol>'+r.cycles.map(c=>'<li><b>取证循环'+c.round+'：</b>'+esc(c.question)+'<p>'+esc(c.outcome)+'</p></li>').join('')+'</ol>'+r.resources.map(u=>'<p>'+anchor(u)+'</p>').join('')+'<p class="warn"><b>仍缺：</b>'+esc(r.missing.join('；'))+'</p>'+(r.mode_boundary?'<p class="warn">'+esc(r.mode_boundary)+'</p>':'')+'<details><summary>原始输入</summary><pre>'+esc(JSON.stringify(r.original_input,null,2))+'</pre></details></article>'}
function draw(){const q=$('q').value.toLowerCase().trim(),rs=D.cases.filter(x=>!q||JSON.stringify(x).toLowerCase().includes(q));$('cases').innerHTML=rs.map(caseCard).join('');$('count').textContent=rs.length+' / 5 条；未扩跑128条'}
$('metrics').innerHTML=[['5','试跑记录'],[D.summary.search_requests,'实际查询'],['2','已核对变更文件的PR'],['0','客户事件确认 / 设备执行']].map(([v,n])=>'<section><strong>'+v+'</strong><br>'+esc(n)+'</section>').join('');
$('repos').innerHTML='<table><tr><th>核实仓库</th><th>实际搜索</th><th>核实依据</th></tr>'+D.policy.primary_repositories.map(r=>'<tr><td>'+anchor(r.canonical_url)+'</td><td>'+esc(r.searched_in_pilot)+'</td><td>'+esc(r.basis)+'</td></tr>').join('')+'</table>';
$('searches').innerHTML='<table><tr><th>记录／循环</th><th>仓库／类型／查询</th><th>实际结果与范围</th></tr>'+D.searches.map(q=>'<tr><td>'+esc(q.task_id)+' / '+q.evidence_cycle+'</td><td>'+esc(q.repository)+'<br>'+esc(q.resource_type)+'<br>'+esc(q.query)+'</td><td>'+esc(q.outcome)+' / '+q.candidate_count+'<details><summary>工具回执与候选范围</summary><pre>'+esc(JSON.stringify(q,null,2))+'</pre></details></td></tr>').join('')+'</table>';
$('resources').innerHTML=D.resources.map(r=>'<details><summary>'+esc(r.resource_id+' / '+r.kind+' / '+r.capture_status)+'</summary><p>'+anchor(r.url)+'</p><p>'+esc(r.review_scope)+'</p>'+((r.file)?'<p>'+anchor(r.file,r.file)+'</p>':'')+'<pre>'+esc(JSON.stringify(r,null,2))+'</pre></details>').join('');$('summary').textContent=JSON.stringify(D.summary,null,2);$('q').addEventListener('input',draw);$('reset').addEventListener('click',()=>{$('q').value='';draw()});draw();
</script></html>'''


def render(data):
    wire=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    (PILOT/'report.html').write_text(HTML.replace('__DATA__',wire),encoding='utf-8',newline='\n')


def verify():
    manifest=read(PILOT/'manifest.json');reviews=rows(PILOT/'pilot_results.jsonl');resources=rows(PILOT/'resource_audit.jsonl');queries=rows(PILOT/'search_audit.jsonl')
    checks=[]
    def check(name,ok):
        checks.append(dict(name=name,status='PASS'if ok else'FAIL'))
    check('five_unique_pilot_ids',[r['task_id']for r in reviews]==CASE_IDS)
    original={r['task_id']:r['original_input']for r in rows(SOURCE/'results.jsonl')}
    check('original_inputs_preserved',all(r['original_input']==original[r['task_id']]for r in reviews))
    check('official_repository_scope_before_primary_evidence',all(primary_source(r['url'],read(PILOT/'repository_policy.json')['primary_repositories'])for r in resources if r['primary_source']))
    check('all_five_keep_event_unknown_no_accept_device_adoption',all(r['event_relation']=='UNDETERMINED'and not any(r[k]for k in ['confirmed_root_cause','formal_adoption','manual_accept_created','hardware_validated'])for r in reviews))
    check('actual_queries_have_receipts_and_scope',all(q['executed']and q['receipt']and q['repository']and q['checked_at']for q in queries))
    check('bounded_empty_query_not_global_negative',all(not q['exhaustive_repository_review']for q in queries))
    check('CANN_two_file_complete_hunks',len(split_diff((PILOT/'evidence/side/CANN-10622.diff').read_text(encoding='utf-8')))==2 and all(p['hunks_complete']for p in split_diff((PILOT/'evidence/side/CANN-10622.diff').read_text(encoding='utf-8'))))
    check('GH12123_all_three_file_patches_complete',all(len(r['files'])==3 and all(f['hunks_complete']for f in r['files'])for r in resources if r['resource_id']=='GH12123'))
    check('exact_snapshot_quotes_and_hashes',all((not r.get('file')or sha(PILOT/r['file'])==r['sha256'])and(not r.get('quote_exact_in_snapshot')or r['quote']in(PILOT/r['file']).read_text(encoding='utf-8'))for r in resources))
    data=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',(PILOT/'report.html').read_text(encoding='utf-8'),re.S)[1])
    check('HTML_JSON_statistics_identical',data['cases']==reviews and data['resources']==resources and data['searches']==queries and data['summary']['search_requests']==len(queries))
    check('all_payload_bytes_match_manifest',all(sha(PILOT/p)==h for p,h in manifest['payload_sha256'].items()))
    check('analysis_script_matches_manifest',sha(Path(__file__))==manifest['analysis_script_sha256'])
    result=dict(status='PASS'if all(c['status']=='PASS'for c in checks)else'FAIL',check_count=len(checks),checks=checks,python=sys.version,
        scope='OFFLINE_PROVENANCE_AND_REPORT_CHECKS; not hardware or all128 review')
    if result['status']!='PASS':raise ValueError(json.dumps(result,ensure_ascii=False))
    return result


def package():
    verify();target=PILOT.with_suffix('.zip')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED)as z:
        for p in sorted(PILOT.rglob('*')):
            if p.is_file():z.write(p,PILOT.name+'/'+p.relative_to(PILOT).as_posix())
    with zipfile.ZipFile(target)as z:
        assert z.testzip()is None
        for p in PILOT.rglob('*'):
            if p.is_file():assert hashlib.sha256(z.read(PILOT.name+'/'+p.relative_to(PILOT).as_posix())).hexdigest()==sha(p)
    target.with_suffix('.zip.sha256').write_text(sha(target)+'  '+target.name+'\n',encoding='utf-8',newline='\n')
    return dict(file=str(target),bytes=target.stat().st_size,sha256=sha(target))


if __name__=='__main__':
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('command',choices=['build','verify','package'])
    args=parser.parse_args();print(json.dumps(globals()[args.command](),ensure_ascii=False,indent=2))
