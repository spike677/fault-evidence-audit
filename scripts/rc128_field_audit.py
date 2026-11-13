"""R3: offline reconciliation of actual Side/API search and source receipts.

No network, model, production-state, event merger or device client lives here.
Source selection and semantic notes are Agent-curated, with explicit read scope.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

import rc128_review as core
import rc128_revision as r2
import official_repo_pilot as pilot
from rc128_field_decisions import INPUT_SHA256, FINDINGS, MISMATCH_FINDINGS, SIX, notes

VERSION='RC128-OFFICIAL-SOURCE-AUDIT-3'
SOURCE=core.DEFAULT
PILOT=pilot.PILOT
OUTPUT=core.REPO/'reports/archive/rc128-evidence-review-20261112-r3'
CODE=['scripts/rc128_review.py','scripts/rc128_revision.py','scripts/rc128_field_audit.py',
      'scripts/rc128_field_decisions.py','scripts/rc128_field_html.py','scripts/official_repo_pilot.py']
EXCLUDED={'manifest.json','validation.json','ui_validation.json','test_results.txt','git_publication.json','browser_validation.json'}


def independent_output(folder, source):
    folder=core.writable_output(folder);source=Path(source).resolve()
    for old in [source,core.LEGACY_BUNDLE.resolve(),PILOT.resolve()]:
        if folder==old or old in folder.parents or folder in old.parents:
            raise ValueError('Source archive and output must be independent; historical archives are read-only.')
    return folder


def payload(folder):
    return json.loads(re.search(r'<script type="application/json" id="payload">(.*?)</script>',
        (folder/'report.html').read_text(encoding='utf-8'),re.S)[1])


def stamp_paths(value,prefix):
    if isinstance(value,list):return [stamp_paths(x,prefix)for x in value]
    if isinstance(value,dict):return {k:stamp_paths(v,prefix)for k,v in value.items()}
    if isinstance(value,str)and value.startswith(('receipts/','evidence/','side_observations.json')):return prefix+value
    return value


def registry(folder):
    reg=stamp_paths(pilot.registry(),'evidence/pilot/')
    unavailable=[]
    for path in sorted((folder/'receipts').glob('REPO-*.json')):
        rec=core.read(path);s=rec['result'].get('structuredContent',{});name=rec['args']['repository_full_name']
        if rec['result'].get('isError')or s.get('repository_full_name','').lower()!=name.lower():
            unavailable.append(dict(url='https://github.com/'+name,status='REPOSITORY_METADATA_UNAVAILABLE_IN_TOOL',
                receipt=path.relative_to(folder).as_posix(),not_proof_repository_absent=True));continue
        reg.append(dict(repository_key='github.com/'+name.lower(),canonical_url='https://github.com/'+name,
            owner=s['owner']['login'],verification_status='VERIFIED_NAMESPACE_AND_REPOSITORY',
            basis='Actual GitHub metadata and user-approved maintainer namespace; not a GitHub brand badge.',
            receipt=path.relative_to(folder).as_posix()))
    for name in ['cann/ops-transformer','cann/ops-math','cann/ascend-transformer-boost','Ascend/op-plugin','Ascend/pytorch','Ascend/MindIE-SD']:
        reg.append(dict(repository_key='gitcode.com/'+name.lower(),canonical_url='https://gitcode.com/'+name,
            owner=name.split('/')[0],verification_status='VERIFIED_NAMESPACE_AND_REPOSITORY',
            basis='Actual Side canonical repository header and user-approved namespace; PR head forks do not change official target ownership.',
            receipt='collection/side_pr_transcripts.json'))
    by={r['repository_key']:r for r in reg}
    return list(by.values()),unavailable


def searches(folder,reg):
    out=[]
    for path in sorted((folder/'receipts').glob('SEARCH-*.json')):
        rec=core.read(path)
        if rec['tool']=='web__run':
            for i,q in enumerate(rec['queries'],1):
                ids=q['task_ids'];out.append(dict(query_id=rec['id']+f':{i}',task_ids=ids,
                    evidence_cycle_by_task={c:3 if c=='RC-009'else rec['round']for c in ids},
                    repository='OFFICIAL_NAMESPACE_WEB_RESTRICTED_QUERY',query=q['q'],
                    tool=rec['tool'],receipt=path.relative_to(folder).as_posix(),executed=True,
                    checked_at=rec['captured_at'],outcome='RESULTS_RETURNED_NO_MATCHING_PRIMARY_FIX_SELECTED',
                    candidates=[],result_scope='Merged four-query index response; result-to-query attribution unavailable. Forks/blogs not primary evidence.',
                    origin='R3_NEW',exhaustive_repository_review=False))
            continue
        args=rec['args'];s=rec['result'].get('structuredContent',{});candidates=s.get('issues',[])
        ids=rec['task_ids'];repo='https://github.com/'+args['repository_full_name']
        if not pilot.primary_source(repo,reg):raise ValueError('Unverified search repo '+repo)
        out.append(dict(query_id=rec['id'],task_ids=ids,evidence_cycle_by_task={c:rec['round']for c in ids},
            repository=repo,query=args['query'],resource_type='ISSUE'if rec['tool'].endswith('search_issues')else'PR',
            filters={k:v for k,v in args.items()if k not in ['query','repository_full_name']},tool=rec['tool'],
            receipt=path.relative_to(folder).as_posix(),executed=True,checked_at=rec['captured_at'],
            outcome='FETCH_BLOCKED'if rec['result'].get('isError')else'CANDIDATES_RETURNED'if candidates else'NO_MATCH_IN_THIS_QUERY',
            candidate_count=len(candidates),candidates=[dict(url=c['url'],title=c['title'],primary_source=pilot.primary_source(c['url'],reg),
                review_scope='SEARCH_TITLE_AND_METADATA; BODY_REVIEW_ONLY_WHEN_RESOURCE_AUDIT_EXISTS')for c in candidates],
            result_scope='Bounded connector query; empty mirror query is not absence in GitCode/CANN.',
            origin='R3_NEW',exhaustive_repository_review=False))
    # Pagination is one query, not multiple search rounds or independent sources.
    group={}
    for obs in core.read(folder/'collection/side_search_transcripts.json')['queries']:
        k=(obs['repository'],obs['query'],json.dumps(obs['filters'],sort_keys=True))
        if k not in group:
            group[k]=dict(query_id=obs['query_id'],task_ids=obs['task_ids'],evidence_cycle_by_task=obs['evidence_cycle_by_task'],
                repository=obs['repository'],query=obs['query'],filters=obs['filters'],tool='CUA_SIDE_NATIVE_REPOSITORY_SEARCH',
                receipt='collection/side_search_transcripts.json',executed=True,checked_at=obs['observed_date'],
                outcome=obs['outcome'],candidate_count=obs['total_results'],candidates=[],observations=[],
                origin='R3_NEW',result_scope=obs['scope_note'],exhaustive_repository_review=False)
        g=group[k];g['observations'].append(obs['query_id'])
        for url in obs['visible_issue_urls']:
            if url not in obs['pinned_issue_urls']and url not in [c['url']for c in g['candidates']]:
                g['candidates'].append(dict(url=url,primary_source=pilot.primary_source(url,reg),review_scope='CURRENT_PAGE_TITLE_ONLY_UNLESS_RESOURCE_AUDIT_EXISTS'))
        g['pages_observed']=sorted(set(g.get('pages_observed',[])+[obs['page']]))
    out+=list(group.values())
    for rec in core.rows(folder/'evidence/pilot/search_audit.jsonl'):
        rec=stamp_paths(rec,'evidence/pilot/');rec['task_ids']=[rec.pop('task_id')]
        rec['evidence_cycle_by_task']={rec['task_ids'][0]:rec.pop('evidence_cycle')};rec['origin']='PILOT_REUSED';out.append(rec)
    if len({x['query_id']for x in out})!=len(out):raise ValueError('Duplicate query ids')
    return out


def split_raw_diff(text):
    """Account for deleted files, /dev/null and non-text entries without invention."""
    parts=[x for x in re.split(r'(?=^diff --git )',text,flags=re.M)if x.startswith('diff --git ')]
    out=[]
    for part in parts:
        m=re.search(r'^diff --git a/(.*?) b/(.*?)$',part,re.M)
        if not m:raise ValueError('Unsupported diff header')
        out.append(dict(filename=m[2],old_filename=m[1],deleted=bool(re.search(r'^\+\+\+ /dev/null$',part,re.M)),
            hunks_complete=core.check_patch_hunks(part)if '@@ 'in part else None,
            text_hunks_present='@@ 'in part,patch=part))
    return out


def snapshot(folder,name,text):
    p=folder/'evidence/decoded'/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(text,encoding='utf-8',newline='')
    return p.relative_to(folder).as_posix()


def resources(folder,reg):
    obs=core.read(folder/'collection/side_github_transcripts.json')
    follow=core.read(folder/'collection/side_final_followups.json')
    side={o['url']:o for o in obs['observations']};out=[]
    for path in sorted((folder/'receipts').glob('BODY-*.json')):
        rec=core.read(path);s=rec['result']['structuredContent'];ispr='pull_request'in s;v=s.get('pull_request',s.get('issue'))
        url=v['url'];repo=rec['args'].get('repo_full_name',rec['args'].get('repository_full_name'));number=int(url.rsplit('/',1)[-1])
        rid=('GH-PR-'if ispr else'GH-ISSUE-')+repo.replace('/','-')+'-'+str(number)
        r=dict(resource_id=rid,url=url,title=s.get('title',v.get('title')),kind='PR'if ispr else'ISSUE',
            repository_key=pilot.repository_key(url),task_ids=rec['task_ids'],primary_source=pilot.primary_source(url,reg),
            origin='R3_NEW',body_capture='API_BODY_CAPTURED_UNABRIDGED',
            body_file=snapshot(folder,path.stem+'.txt',v.get('body')or''),receipt=path.relative_to(folder).as_posix(),
            source_status=v['state'],body_semantics_reviewed='SELECTED_REPRODUCTION_OR_PURPOSE_SECTIONS',
            side=side.get(url),full_source_semantics_reviewed=False,attachments_read=False,
            comments_read_scope='Selected rendered discussion only; returned comments are not all semantically reviewed.',
            capture_attempts=[dict(tool=rec['tool'],status='SUCCESS',receipt=path.relative_to(folder).as_posix())])
        if ispr:
            r.update(head_sha=v.get('head_sha'),merge_commit_sha=v.get('merge_commit_sha'),merged=v['merged'],
                draft=v.get('draft'),reviewed_patches=[],changed_file_count=v.get('changed_files'))
            files=core.read(folder/('receipts/FILES-'+path.stem.removeprefix('BODY-')+'.json'))['result']['structuredContent']['filenames']
            r['changed_filenames']=files
            if len(files)!=r['changed_file_count']:raise ValueError('Changed file list mismatch '+rid)
            for pp in sorted((folder/'receipts').glob('PATCH-'+path.stem.removeprefix('BODY-')+'-*.json')):
                pr=core.read(pp);p=pr['result']['structuredContent']['patch']
                if p['filename']not in files or not core.check_patch_hunks(p['patch']):raise ValueError('Invalid patch '+str(pp))
                r['reviewed_patches'].append(dict(filename=p['filename'],file=snapshot(folder,pp.stem+'.diff',p['patch']),
                    hunks_complete=True,receipt=pp.relative_to(folder).as_posix(),scope='Whole returned per-file hunks, not complete surrounding functions.'))
            r['reviewed_file_count']=len(r['reviewed_patches'])
            r['diff_capture']='ALL_LISTED_FILES_PATCHES'if len(files)==r['reviewed_file_count']else'SELECTED_VALIDATED_FILE_PATCHES'
            r['diff_read_scope']='Selected '+str(r['reviewed_file_count'])+'/'+str(len(files))+' changed files; unread files cannot support claims.'
            # fetch_pr's diff lacks file headers: archive but never use it as a
            # completeness proof or cite unreviewed hunks from this aggregate.
            r['aggregate_diff_file']=snapshot(folder,path.stem+'.diff',s.get('diff',''))
            r['aggregate_diff_reviewed_as_complete']=False
            r['side_diff_observations']=[o for o in obs['diff_observations']if o['url'].split('/files')[0]==url]
        for comments in (folder/'receipts').glob('COMMENTS-'+path.stem.removeprefix('BODY-')+'.json'):
            r['comments_receipt']=comments.relative_to(folder).as_posix()
            r['comments_read_scope']='Selected commenter diagnosis and maintainer replies; complete API response retained, no attachment review.'
        out.append(r)
    for o in [*core.read(folder/'collection/side_pr_transcripts.json')['observations'],*follow['prs']]:
        text=(folder/o['raw_diff']).read_text(encoding='utf-8');fs=split_raw_diff(text)
        if any(f['hunks_complete']is False for f in fs):raise ValueError('Incomplete raw Diff '+o['url'])
        patch=(folder/o['email_patch']).read_text(encoding='utf-8');m=re.search(r'^From ([0-9a-f]{40}) ',patch)
        r=dict(resource_id=o['resource_id'],url=o['url'],title=o['title'],kind='PR',task_ids=o['task_ids'],
            repository_key=pilot.repository_key(o['url']),primary_source=pilot.primary_source(o['url'],reg),origin='R3_NEW',
            body_capture=o['body_capture'],body_transcript=o['selected_body_quote'],receipt='collection/side_final_followups.json'if o in follow['prs']else'collection/side_pr_transcripts.json',
            raw_diff=o['raw_diff'],email_patch=o['email_patch'],commit=m[1]if m else None,changed_file_count=len(fs),
            file_inventory=[{k:v for k,v in f.items()if k!='patch'}for f in fs],
            diff_capture='RAW_DIFF_AND_EMAIL_PATCH_DOWNLOADED_BY_SIDE',diff_read_scope=o['read_scope'],
            source_status=o['pr_status'],full_source_semantics_reviewed=False,attachments_read=False,
            capture_attempts=[dict(tool=o['method'],status='SUCCESS',observed_at=o['observed_at'])])
        if r['resource_id']=='GC-Ascend-pytorch-49092':r['source_status']='MERGED_IN_SIDE_UI'
        out.append(r)
    extra=[dict(o,body_capture='SELECTED_AGENT_TRANSCRIPTION_NOT_FULL_DOM_OR_ATTACHMENT_CAPTURE',
                read_scope='MAIN_BODY_AND_SELECTED_DISCUSSION_READ',method='CUA_SIDE_NATIVE_DOM')for o in follow['issues']]
    for o in [*core.read(folder/'collection/side_issue_transcripts.json')['observations'],*extra]:
        out.append(dict(resource_id=o['resource_id'],url=o['url'],title=o['title'],kind='ISSUE',task_ids=o['task_ids'],
            repository_key=pilot.repository_key(o['url']),primary_source=pilot.primary_source(o['url'],reg),origin='R3_NEW',
            body_capture=o['body_capture'],body_transcript=o['selected_quote'],notes=o['notes'],
            body_semantics_reviewed=o['read_scope'],receipt='collection/side_final_followups.json'if o in extra else'collection/side_issue_transcripts.json',
            observed_at=o['observed_at'],full_source_semantics_reviewed=False,attachments_read=False,
            capture_attempts=[dict(tool=o['method'],status='SUCCESS')]))
    # Pilot resources that have since been read in Side are merged by URL; the
    # earlier Web failure remains an attempt, not the current capture status.
    by={r['url']:r for r in out}
    assignments={'SIDE-DEEPSEEK-README':['RC-003'],'SIDE-RC111-PINNED-SCHEMA':['RC-111'],
        'SIDE-RC111-TORCH-SDPA':['RC-111'],'GH14118':['RC-003'],'GH12123':['RC-030'],
        'CANN10622':['RC-002'],'SIDE-CANN-5928':['RC-002'],
        'SIDE-OPBASE-569':['RC-009'],'SIDE-OPBASE-528':['RC-009']}
    for old in core.rows(folder/'evidence/pilot/resource_audit.jsonl'):
        r=stamp_paths(old,'evidence/pilot/')
        if r['url']in by:
            by[r['url']]['capture_attempts']+=r.get('capture_attempts',[dict(tool='PILOT_WEB',status=r['capture_status'],receipt=r.get('receipt'))]);continue
        r['origin']='PILOT_REUSED';r['task_ids']=assignments.get(r['resource_id'],[])
        r['repository_key']=pilot.repository_key(r['url']);r['capture_attempts']=r.get('capture_attempts',[])
        if r['resource_id']=='CANN10622':r['raw_diff']=r['file']
        if r['resource_id']=='GH12123':
            r['reviewed_patches']=r['files'];r['changed_filenames']=[p['filename']for p in r['files']]
            r['reviewed_file_count']=3;r['diff_read_scope']=r['review_scope']
        out.append(r);by[r['url']]=r
    for i,o in enumerate(obs['other_source_reads'],1):
        rid='SIDE-REFERENCE-'+str(i)
        # The exact pinned source bytes are already part of R2.
        keys=['GH-ORT-CANN.source.txt','GH-ORT-CANN-OPTIONS.source.txt','GH-ROPE-a3a3d38-1.patch']
        f='evidence/decoded/'+keys[i-1]
        if o['quote']not in (folder/f).read_text(encoding='utf-8'):raise ValueError('Source reference quote missing')
        out.append(dict(resource_id=rid,url=o['url'],kind='SOURCE',task_ids=o['task_ids'],title=o['url'].split('/')[-1],
            repository_key=pilot.repository_key(o['url']),primary_source=pilot.primary_source(o['url'],reg),origin='R3_SIDE_REREAD_PRIOR_BYTES',
            file=f,body_capture='FULL_PRIOR_FILE_CAPTURED_SIDE_SELECTED_OR_HEADER_FULL_READ',quote=o['quote'],
            review_scope=o['read_scope'],limitation=o['limitation'],receipt='collection/side_github_transcripts.json',
            full_source_semantics_reviewed=False,capture_attempts=[dict(tool='CUA_SIDE',status='SUCCESS_AFTER_RAW_FALLBACK')]))
    if len(out)!=len({r['url']for r in out}):raise ValueError('Resource URL deduplication failed')
    for r in out:
        if not r['primary_source']:raise ValueError('Unverified primary '+r['url'])
        r['collection_task_ids']=list(r['task_ids'])
        # Explicit semantic cross-references from the Agent's finding list;
        # retain the original fetch target so reuse is not misreported as a
        # second collection or an original weekly citation.
        compared={c for rid,ids,*rest in FINDINGS if rid==r['resource_id']for c in ['RC-'+n for n in ids.split()]}
        r['additional_comparison_task_ids']=sorted(compared-set(r['task_ids']))
        r['task_ids']=sorted(set(r['task_ids'])|compared)
        r['weekly_event_confirmed']=False;r['hardware_validated']=False
    return out


# Explicit hunk locators selected during the Agent's code reading. They do not
# decide a fault or classify it by keyword. Each is checked against raw bytes.
MARKERS={
 '12509':['PipeBarrier<PIPE_M>();','PipeBarrier<PIPE_V>();'],
 '12716':['PipeBarrier<PIPE_M>();','PipeBarrier<PIPE_V>();'],
 '279':['uint64_t preCtrl','set_ctrl(newCtrl);'],
 '4871':['GetLibApiWorkSpaceSize','SToVSync','SyncAll();'],
 '4833':['probs->scalar_type()','dtype=probs.dtype'],
 '8365':['GetTopKMaxMinTmpSize','tmpUbSize'], '8367':['GetTopKMaxMinTmpSize','tmpUbSize'],
 '7443':['deleted file mode'], '8752':['layoutA1RowStride','gmmA1PreRowStride'], '8766':['max','K2'],
 '548':['aclrtSynchronizeStream','EXEC_NPU_CMD'], '2285':['mmOpInfo.support_info.self_dtype'],
 '3901':['dimD'], '4152':['FlashAttentionScoreGradTilingData'],
 '8443':['eventId','PIPE','uint64_t'], '8445':['eventId','PIPE','uint64_t'],
 '2207':['CALC_TYPE_FIRST_RING'], '6170':['xViewShape[i] > INT32_MAX_NUM'],
 '9834':['DUPSIZE','mask[2]','+ 128'], '1562':['auto indexSize = 1','[IndexFill]','optional'],
 '6026':['bool useReduceAll','l0op::ReduceAll'],
 '8005':['deScaleVValue, deScaleVValue','ext.deq_v.reshape','deq_v'],
 '49092':['patch_cse_rand_ops','rand_ops'],
 '49099':['_compute_fusion_metadata','prologue_nodes'], '10622':['enableGemm16In32Out'],
}

PATCH_MARKERS={
 'PATCH-RC-025-19674-1':['# Grouped weight','grouped_wo_a ='],
 'PATCH-RC-025-19674-2':['+            layer.weight.data = reshape_wo_a_to_3d'],
 'PATCH-RC-026-6827-1':['UB_SIZE','IS_PARTIAL_ROPE','split_qkv_rmsnorm_rope_kernel[grid]'],
 'PATCH-RC-031-16699-1':['+    last_row','+            pos = tl.load'],
 'PATCH-RC-031-16699-2':['+      - name: split-qkv'],
 'PATCH-RC-045-10507-1':['+     LocalTensor<float> ringF','+                 Cast(ringF'],
 'PATCH-RC-045-10507-2':['+__aicore__ inline void ComputeFnRollingOutputRegbase'],
 'PATCH-RC-053-21494-1':['+TRANSPOSE_BMM_CHUNK','+def _transpose_batchmatmul_on_grid'],
 'PATCH-RC-053-21494-2':['+class _RecordingTBMM'],
 'PATCH-RC-060-17180-1':['+def fill_mxfp_v_scale_cache','+def mxfp_v_scale_cache_shape'],
 'PATCH-RC-060-17180-2':['+    max_seqlen_q is the longest single query'],
 'PATCH-RC-062-7620-1':['+    query_states, key_states = apply_rotary_pos_emb'],
 'PATCH-RC-077-12649-1':['+class _RangeBoundFusionPass'],
 'PATCH-RC-077-12649-2':['+def _is_supported_910c_down_proj_match'],
 'PATCH-RC-099-15018-1':['+        topk_weights = topk_weights.to(activation_dtype)','+        activation_dtype = hidden_states.dtype'],
 'PATCH-RC-099-15613-1':['+    router_weights = torch.tensor([[0.6, 0.4]]'],
 'PATCH-RC-099-15613-2':['+        if hidden_states.dtype in','+            topk_weights = topk_weights.to(torch.float32)'],
 'PATCH-RC-099-15613-3':['+        if hidden_states.dtype in'],
 'PATCH-RC-122-4946-1':['-        rank = None'],
 'PATCH-RC-122-7371-1':['+                if not get_accelerator().resolves_data_dependency()'],
}


def exact_excerpt(folder,rid,file,marker,index=0,context=220):
    text=(folder/file).read_bytes().decode('utf-8');positions=[m.start()for m in re.finditer(re.escape(marker),text)]
    if not positions:raise ValueError(f'Locator missing: {rid} / {file} / {marker}')
    pos=positions[min(index,len(positions)-1)];start=text.rfind('\n',0,max(0,pos-context))+1
    end=text.find('\n',min(len(text),pos+len(marker)+context));end=len(text)if end<0 else end
    return dict(evidence_id=rid+':'+hashlib.sha256((file+str(start)).encode()).hexdigest()[:12],resource_id=rid,
        file=file,sha256=core.sha(folder/file),char_start=start,char_end=end,quote=text[start:end],
        line_start=text.count('\n',0,start)+1,line_end=text.count('\n',0,end)+1,
        selection='EXPLICITLY_SCOPED_SOURCE_EXCERPT_NOT_FULL_SOURCE_VERIFICATION')


def excerpts(folder,rs):
    out=[]
    for r in rs:
        rid=r['resource_id']
        if r.get('raw_diff'):
            key=r['url'].rsplit('/',1)[-1]
            for marker in MARKERS[key]:out.append(exact_excerpt(folder,rid,r['raw_diff'],marker))
        for p in r.get('reviewed_patches',[]):
            text=(folder/p['file']).read_text(encoding='utf-8')
            # All returned selected-file hunks were read; excerpt the change
            # lines, keep the full selected-file patch alongside them.
            additions=[x for x in text.splitlines()if x.startswith('+')and not x.startswith('+++')and len(x.strip())>4]
            markers=PATCH_MARKERS.get(Path(p['file']).stem,[additions[0]if additions else'@@ '])
            for marker in markers:out.append(exact_excerpt(folder,rid,p['file'],marker,context=500))
        if r.get('quote')and r.get('file'):out.append(exact_excerpt(folder,rid,r['file'],r['quote'],context=0))
    # Keep only distinct exact ranges; identical content across different URLs
    # remains referenced by each URL, never counted as corroboration.
    return list({e['evidence_id']:e for e in out}.values())


def public_findings(rs,es):
    by={r['resource_id']:r for r in rs};out=[]
    for i,(rid,ids,finding,relation,boundary)in enumerate(FINDINGS,1):
        r=by[rid];refs=[e['evidence_id']for e in es if e['resource_id']==rid]
        if not refs:raise ValueError('Unanchored code finding '+rid)
        out.append(dict(finding_id=f'PUBLIC-{i:03}',resource_id=rid,url=r['url'],
            task_ids=['RC-'+n for n in ids.split()],finding=finding,failed_or_required_relation=relation,
            original30_boundary=boundary,basis='CODE_CHANGE_OBSERVED_WITH_BOUNDED_INTERPRETATION',
            evidence_ids=refs,source_read_scope=r.get('diff_read_scope',r.get('review_scope')),
            entity_type='INDEPENDENT_PUBLIC_TECHNICAL_OBSERVATION',event_relation='UNDETERMINED',
            weekly_root_confirmed=False,hardware_validated=False,adoption_status='NOT_SUBMITTED_FOR_ADOPTION'))
    return out


def case_audits(data,qs,rs,findings):
    reviews=notes();out=[]
    for r in data['results']:
        cid=r['task_id'];sources=[s for s in rs if cid in s['task_ids']]
        queries=[q for q in qs if cid in q['task_ids']]
        if not queries and not sources:raise ValueError('Unaudited record '+cid)
        found=[f for f in findings if cid in f['task_ids']]
        outcomes=[q['outcome']for q in queries]
        # Processing status is an audit scope, not a fault/event classifier.
        state='SOURCE_BODY_REVIEWED_ROOT_UNCONFIRMED'if sources else'CANDIDATES_INDEX_ONLY'if any(q.get('candidate_count',0)for q in queries)else'BOUNDED_SEARCH_NO_MATCH'
        if cid in ['RC-050','RC-052','RC-059','RC-101','RC-107']:state='INPUT_IDENTITY_GAP_WITH_EXPLORATORY_SEARCH'
        if found:state='CODE_REVIEWED_WEEKLY_IDENTITY_UNCONFIRMED'
        if cid=='RC-026':state='SOURCE_DESCRIPTION_DIFF_CONFLICT'
        if cid in ['RC-074','RC-075','RC-111']:state='CONTRACT_SOURCE_REVIEWED_DEPLOYMENT_UNCONFIRMED'
        # Preserve the R2 original claims and all historical subproblem detail.
        audit=dict(task_id=cid,policy_version=VERSION,processing_status=state,
            actual_search_ids=[q['query_id']for q in queries],repositories_searched=sorted({q['repository']for q in queries}),
            search_outcomes=dict(Counter(outcomes)),resource_ids=[s['resource_id']for s in sources],
            body_reviewed_resource_ids=[s['resource_id']for s in sources],
            code_resource_ids=[s['resource_id']for s in sources if s.get('raw_diff')or s.get('reviewed_patches')or s.get('kind')in ['SOURCE','API_CONTRACT']],
            public_finding_ids=[f['finding_id']for f in found],assessment=reviews[cid]['assessment'],
            remaining_gaps=[reviews[cid]['remaining_gap']],
            root_evidence_status='SOURCE_DECLARED_PLUS_SEPARATE_PUBLIC_CODE_FACTS'if found else'SOURCE_DECLARED_OR_UNKNOWN',
            root_independently_confirmed=False,event_relation='UNDETERMINED',
            search_is_exhaustive=False,review_depth='OFFICIAL_SOURCE_SEARCH_AND_SELECTED_RESOURCE_AUDIT',
            four_question_review_scope=r['review_scope'],
            internal_evidence_status='TRANSFERRED_SUMMARY_ONLY_NO_NEW_INTERNAL_BODY_READ',
            stop_reason='Existing resource read to declared scope; remaining identity/contract gaps cannot be repaired by collecting arbitrary extra types.'if sources else'Bounded official-source search completed; no specific repair selected. Unknown fields retained.',
            historical_analysis_reused=True,manual_accept_created=False,formal_adoption=False,hardware_validated=False)
        out.append(audit);r['field_audit']=audit;r['previous_root_cause']=deepcopy(r['root_cause'])
        r['root_cause']=dict(conclusion=reviews[cid]['assessment'],basis=audit['root_evidence_status'],independently_confirmed=False)
        r['unresolved_gaps']=list(dict.fromkeys([*r['unresolved_gaps'],*audit['remaining_gaps']]))
        r['review_policy']=VERSION
    return out


def relations(data,rs,findings):
    out=[];bycase={r['task_id']:r for r in data['results']}
    for s in rs:
        for cid in s['task_ids']:
            original=bycase[cid]['original_input'];clues=json.dumps(original['public_code_clues'],ensure_ascii=False)
            supplied=s['url']in clues
            mechanism='UNDETERMINED';support='INSUFFICIENT_INFORMATION'
            if any(cid in f['task_ids']and f['resource_id']==s['resource_id']for f in findings):
                mechanism='RELATED_TECHNICAL_RELATION_NOT_CONFIRMED_SAME_MECHANISM';support='PUBLIC_CODE_FACTS_ONLY'
            if cid in MISMATCH_FINDINGS and s.get('kind')=='PR':support='DOES_NOT_SUPPORT_ORIGINAL_CLAIM_AS_SCOPED'
            if cid=='RC-010'and s['resource_id']=='GC-cann-opbase-279':
                mechanism='SOURCE_REPORTED_MECHANISM_HAS_CORRESPONDING_PUBLIC_CODE_CHANGE';support='MECHANISM_PARTIAL_SUPPORT_IDENTITY_UNKNOWN'
            out.append(dict(relation_id=cid+':'+s['resource_id'],task_id=cid,resource_id=s['resource_id'],url=s['url'],
                issue_scope='Only the stated public subproblem and the record claim compared; no whole-page root inheritance.',
                source_relation='HANDOFF_CODE_LINK'if supplied else'PILOT_REFERENCE_REUSED'if s['origin']=='PILOT_REUSED'else'TARGETED_SEARCH_OR_EXISTING_CLUE_FOLLOWUP',
                event_relation='UNDETERMINED',mechanism_relation=mechanism,support_status=support,
                entity_type='PUBLIC_TECHNICAL_CASE_OR_CONTRACT_REFERENCE_NOT_CONFIRMED_WEEKLY_EVENT',
                reason=notes()[cid]['assessment'],missing=notes()[cid]['remaining_gap'],
                code_evidence_scope=s.get('diff_read_scope',s.get('review_scope',s.get('body_semantics_reviewed'))),
                manual_accept_created=False))
    return out


def summary(data,folder):
    audits=data['field_audits'];q=data['search_audit'];r=data['resource_audit']
    s=deepcopy(core.read(folder/'history/r2/summary.json'))
    s['schema_version']='RC128-RELATION-REVIEW-3'
    s['historical_revision_summary']=s.pop('revision',{})
    s['search_count_scope']='R1索引141次为历史；本轮新检索与试跑复用分列，分页不重复计数，搜索结果不等于正文审读。'
    s['technical_case_count_scope']='沿用22条旧技术案例；R3另列公开代码观察，不自动新增模式或客户事件。'
    s['field_audit']=dict(policy_version=VERSION,unique_records=len(audits),new_query_executions=sum(x['origin']=='R3_NEW'for x in q),
        pilot_queries_reused=sum(x['origin']=='PILOT_REUSED'for x in q),unique_repositories_searched=len({pilot.repository_key(x['repository'])for x in q}-{None}),
        bounded_no_match_queries=sum(x['outcome']=='NO_MATCH_IN_THIS_QUERY'for x in q),
        query_fetch_blocked=sum(x['outcome']=='FETCH_BLOCKED'for x in q),side_page_observations=26,
        prior_web_read_blocked_attempts=sum('BLOCKED'in a.get('status','')for x in r for a in x.get('capture_attempts',[])),
        repository_metadata_unavailable=len(data['unavailable_repository_metadata']),current_internal_body_reads=0,
        resource_unique_urls=len(r),body_or_contract_resources_reviewed=len(r),
        records_with_source_reads=sum(bool(a['resource_ids'])for a in audits),
        records_with_only_search_or_input_gap=sum(not a['resource_ids']for a in audits),
        pr_resources=sum(x['kind']=='PR'for x in r),
        downloaded_gitcode_pr_diffs=sum(bool(x.get('raw_diff'))for x in r),
        github_pr_resources_with_per_file_patches=sum(bool(x.get('reviewed_patches'))or x['resource_id']=='GH12123'for x in r),
        explicit_public_code_observations=len(data['public_findings']),
        per_record_processing_status=dict(Counter(a['processing_status']for a in audits)),
        historical_events_independently_confirmed=0,confirmed_weekly_roots=0,
        formal_adoption=0,manual_accepts=0,device_runs=0,
        counts_are_overlapping_scopes_not_additive=True,
        all_128_semantically_reproduced=False,all_related_candidates_exhaustively_read=False,
        new_definition_or_condition_coverage_claims=0)
    return s


def archive_verify(folder):
    """Historical policy self-consistency, never replay current semantic rules."""
    m=core.read(folder/'manifest.json');policy=core.read(folder/'review_policy.json')
    fp=hashlib.sha256(json.dumps(dict(code=m['analysis_code_sha256'],policy=policy),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if fp!=m['policy_fingerprint']or not all(core.sha(folder/f)==h for f,h in m['payload_sha256'].items()):
        raise ValueError('Historical payload/policy no longer matches its original manifest')
    return dict(status='PASS',policy_version=policy['version'],policy_fingerprint=fp,read_only=True,
        policy_status='HISTORICAL_POLICY_NOT_CURRENT_REVIEW',scope='ORIGINAL_MANIFEST_BYTES_AND_POLICY_SELF_CONSISTENCY_ONLY')


def fingerprint(folder):
    code={p:core.sha(core.REPO/p)for p in CODE};policy=core.read(folder/'review_policy.json')
    fp=hashlib.sha256(json.dumps(dict(code=code,policy=policy),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return code,fp


def manifest(folder):
    code,fp=fingerprint(folder)
    core.write(folder/'manifest.json',dict(schema_version='RC128-BUNDLE-3',policy_version=VERSION,
        analysis_code_sha256=code,policy_fingerprint=fp,payload_sha256={p:h for p,h in r2.file_hashes(folder).items()if p not in EXCLUDED},
        source_input_sha256=INPUT_SHA256,state_modified=False,formal_adoption=False))


def build(folder,source):
    folder=independent_output(folder,source);source=Path(source).resolve()
    if core.read(source/'manifest.json')['schema_version']!='RC128-BUNDLE-2':raise ValueError('R3 requires the immutable R2 archive.')
    if core.sha(source/'sources/original/handoff.jsonl')!=INPUT_SHA256:raise ValueError('Input identity mismatch')
    before=r2.file_hashes(source);archive_verify(source)
    # Copy only inputs/evidence/reference data. Current conclusions are rebuilt
    # from the complete R2 payload with the explicit R3 audit overlay.
    for p in source.rglob('*'):
        if not p.is_file()or p.name in EXCLUDED:continue
        rel=p.relative_to(source)
        if rel.parts[0]not in ['sources','evidence','history']and p.name not in ['input_manifest.json','condition_definitions.json','baseline_30_index.json']:
            continue
        t=folder/rel;t.parent.mkdir(parents=True,exist_ok=True)
        if t.exists()and core.sha(t)!=core.sha(p):raise ValueError('Collection/input collision '+str(rel))
        if not t.exists():shutil.copyfile(p,t)
    for name in ['manifest.json','validation.json','ui_validation.json','test_results.txt','summary.json','review_policy.json','search_index.json','cross_review.json','corrections.json']:
        t=folder/'history/r2'/name;t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,t)
    shutil.copytree(PILOT,folder/'evidence/pilot',dirs_exist_ok=True)
    data=payload(source);reg,unavailable=registry(folder);qs=searches(folder,reg);rs=resources(folder,reg);es=excerpts(folder,rs)
    finding=public_findings(rs,es);audits=case_audits(data,qs,rs,finding)
    data.update(field_audits=audits,search_audit=qs,resource_audit=rs,public_findings=finding,field_excerpts=es,
                repository_registry=reg,unavailable_repository_metadata=unavailable)
    data['evidence_relations']=relations(data,rs,finding)
    # Original R2 classifications and four-question records remain explicitly
    # historical. Public test input shape/scale is not transferred to a customer.
    for f in data['failures']:
        f['r3_source_audit_ids']=[a['task_id']for a in audits if a['task_id']==f.get('task_id')]
        f['r3_relation_status']='HISTORICAL_ANALYSIS_PLUS_SEPARATE_SOURCE_AUDIT_NOT_FULL_REPROOF'
    for c in data['conditions']:c['r3_classification_status']='HISTORICAL_SPARSE_CLASSIFICATION_NOT_NEW_COVERAGE'
    for c in data['comparisons']:
        c['r3_adjudication_status']='PENDING_NOT_FORMAL_ADOPTION'
        c['r3_source_review']=next((a['assessment']for a in audits if a['task_id']==c.get('task_id')),None)
    data['summary']=summary(data,folder)
    for filename,key in [('results','results'),('failure_relations','failures'),('condition_relations','conditions'),
        ('mode_comparison','comparisons'),('driving_quantities','driving_quantities'),('field_audits','field_audits'),
        ('search_audit','search_audit'),('resource_audit','resource_audit'),('public_findings','public_findings'),('evidence_relations','evidence_relations')]:
        core.jsonl(folder/(filename+'.jsonl'),data[key])
    core.write(folder/'summary.json',data['summary']);core.write(folder/'case_reviews.json',dict(reviews=data['case_reviews'],status='R2_PENDING_WITH_R3_SOURCE_AUDIT_SEPARATE'))
    core.write(folder/'corrections.json',dict(corrections=data['corrections'],r3_assessments=audits))
    core.write(folder/'technical_cases.json',dict(cases=data['technical_cases'],status='HISTORICAL_22_NOT_NEW_ADOPTIONS'))
    core.write(folder/'repository_policy.json',dict(verified=reg,unavailable_metadata=unavailable,
        personal_forks_as_primary=False,official_source_does_not_prove_event_relation=True))
    core.write(folder/'source_revision.json',dict(source_path=str(source),source_commit='303ef7ce3217245d5d8905c42e3e2766fde06d75',
        all_file_sha256=before,policy_status='HISTORICAL_POLICY_NOT_CURRENT_REVIEW',pilot_commit='b998fb5e207ec689a183813739013ae1b92ab561'))
    core.write(folder/'review_policy.json',dict(version=VERSION,input_budget_chars=160000,source_archive_read_only=True,
        event_identity_not_inherited=True,no_automatic_accept=True,no_adoption=True,no_device_runs=True,
        source_capture_separate_from_semantic_review=True,official_repo_filter=True,partial_input_scope_explicit=True,
        no_new_128_searches_on_rebuild=True,api42_v4_not_modified=True))
    # Entire analysis envelope including instructions, frozen definitions and
    # selected read scope; full raw patches are archived, not silently truncated.
    context={a['task_id']:dict(audit=a,public_findings=[f for f in finding if a['task_id']in f['task_ids']],
        selected_resource_scope=[dict(resource_id=s['resource_id'],scope=s.get('diff_read_scope',s.get('review_scope',s.get('body_semantics_reviewed'))))
            for s in rs if a['task_id']in s['task_ids']],
        original_r2_quantity_review=next((v for v in data['case_reviews']if v['task_id']==a['task_id']),None),
        evidence_text=[e for e in es if e['resource_id']in a['code_resource_ids']])for a in audits}
    core.write(folder/'review_context.json',context)
    core.write(folder/'input_budget_receipts.json',core.input_budget_receipts(core.rows(folder/'sources/original/handoff.jsonl'),data['baseline'],data['definitions'],folder,context))
    core.write(folder/'evidence_sha256_manifest.json',dict(files={p:h for p,h in r2.file_hashes(folder).items()if p.startswith(('sources/','evidence/','receipts/','collection/'))},
        full_capture_not_equal_full_semantic_review=True))
    from rc128_field_html import render,README
    render(folder,data);(folder/'README.md').write_text(README,encoding='utf-8',newline='\n')
    manifest(folder)
    result=verify(folder)
    if before!=r2.file_hashes(source):raise ValueError('Source archive changed')
    core.write(folder/'validation.json',result)
    return result


def verify(folder,git_index=False):
    folder=Path(folder);m=core.read(folder/'manifest.json');data=payload(folder);checks=[]
    def check(name,f):
        try:
            if f()is False:raise ValueError(name)
            checks.append(dict(name=name,status='PASS'))
        except Exception as exc:checks.append(dict(name=name,status='FAIL',error=str(exc)))
    inputs=core.rows(folder/'sources/original/handoff.jsonl');rs=data['results'];qs=data['search_audit'];rr=data['resource_audit'];es=data['field_excerpts']
    check('128_original_unique_ids_and_input_bytes',lambda:[r['task_id']for r in rs]==[f'RC-{n:03}'for n in range(1,129)]and
        [r['original_input']for r in rs]==inputs and core.sha(folder/'sources/original/handoff.jsonl')==INPUT_SHA256)
    check('all128_have_actual_query_or_resource_read_and_explicit_gap',lambda:len(data['field_audits'])==128 and
        all((a['actual_search_ids']or a['resource_ids'])and a['remaining_gaps']and a['assessment']for a in data['field_audits']))
    check('one_resource_per_url_without_reference_loss',lambda:len(rr)==len({r['url']for r in rr})and
        all({r['task_id']for r in data['evidence_relations']if r['resource_id']==s['resource_id']}==set(s['task_ids'])for s in rr))
    check('all_primary_resources_on_verified_canonical_repo',lambda:all(pilot.primary_source(r['url'],data['repository_registry'])for r in rr))
    check('query_outcome_not_global_repo_absence',lambda:all(q['executed']and not q['exhaustive_repository_review']for q in qs))
    check('max3_cycles_and4_query_requests_per_record_cycle',lambda:query_limits(qs))
    check('paging_not_duplicate_query_execution',lambda:sum(len(q.get('observations',[]))for q in qs if q['origin']=='R3_NEW')==26 and len({q['query_id']for q in qs})==len(qs))
    check('source_event_mechanism_separate_no_event_confirmation',lambda:all(e['event_relation']=='UNDETERMINED'and e['source_relation']and e['mechanism_relation']and e['support_status']for e in data['evidence_relations']))
    check('no_accept_adoption_device_or_root_promotion',lambda:all(not any(r[k]for k in ['weekly_event_confirmed','manual_accept_created','hardware_validated','formal_adoption'])and not r['root_cause']['independently_confirmed']for r in rs))
    check('full_patch_capture_not_full_function_review',lambda:all(not r.get('full_source_semantics_reviewed',False)and not r.get('aggregate_diff_reviewed_as_complete',False)for r in rr))
    check('github_selected_patch_files_validated_hunks_complete',lambda:all(p['filename']in r['changed_filenames']and core.check_patch_hunks((folder/p['file']).read_text(encoding='utf-8'))for r in rr for p in r.get('reviewed_patches',[])))
    check('raw_gitcode_hunks_and_deletions_accounted_for',lambda:all(all(f['hunks_complete']is not False for f in split_raw_diff((folder/r['raw_diff']).read_text(encoding='utf-8')))for r in rr if r.get('raw_diff')))
    check('all_source_excerpt_ranges_exact_and_hash_match',lambda:all(core.sha(folder/e['file'])==e['sha256']and (folder/e['file']).read_bytes().decode('utf-8')[e['char_start']:e['char_end']]==e['quote']for e in es))
    refs={e['evidence_id']for e in es}
    check('public_code_findings_have_exact_excerpts_and_no_weekly_transfer',lambda:all(f['evidence_ids']and set(f['evidence_ids'])<=refs and not f['weekly_root_confirmed']and f['event_relation']=='UNDETERMINED'for f in data['public_findings']))
    byresource={r['resource_id']:r for r in rr}
    check('shared_public_finding_case_links_preserved',lambda:all(set(f['task_ids'])<=set(byresource[f['resource_id']]['task_ids'])for f in data['public_findings']))
    check('six_driving_reviews_retained_without_new_card_decision',lambda:r2.validate_quantities(data['driving_quantities'])and all(c['action']=='PENDING'for c in data['comparisons']if c.get('task_id')in SIX))
    check('rc026_description_diff_conflict_explicit',lambda:data['field_audits'][25]['processing_status']=='SOURCE_DESCRIPTION_DIFF_CONFLICT')
    check('rc062_no_register_contamination_rc029_no_stage_inference',lambda:all(not any(w in f['expected_relation']for w in ['寄存器','构造步骤'])for f in data['failures']if f.get('task_id')=='RC-062')and
        all(not any(w in json.dumps(f,ensure_ascii=False)for w in ['前块','当前块','前一块'])for f in data['failures']if f.get('task_id')=='RC-029'))
    check('counterevidence_not_ignored',lambda:'清零' in next(r for r in rr if r['resource_id']=='GC-ISSUE-cann-ops-nn-90')['notes'][0]and
        all('90'in data['field_audits'][n-1]['assessment']for n in [71,82,100,110,128]))
    check('128_initialized_transcription_conflict_retained',lambda:'初始化的空间'in rs[127]['original_input']['fault']['reported_root_cause']and '冲突'in rs[109]['field_audit']['remaining_gaps'][0])
    check('old30_42_v4_and_sparse_conditions_unchanged',lambda:all(core.sha(folder/p)==core.read(folder/'source_revision.json')['all_file_sha256'][p]for p in
        ['baseline_30_index.json','condition_definitions.json','sources/original/api42_trigger_library_original.md','sources/original/precision_trigger_knowledge_v4.md'])and all(not c['counts_as_verified_coverage']for c in data['conditions']))
    for name,key in [('results','results'),('failure_relations','failures'),('condition_relations','conditions'),('mode_comparison','comparisons'),('field_audits','field_audits'),('search_audit','search_audit'),('resource_audit','resource_audit'),('public_findings','public_findings'),('evidence_relations','evidence_relations')]:
        check('html_json_equal_'+name,lambda n=name,k=key:core.rows(folder/(n+'.jsonl'))==data[k])
    check('summary_recomputed_not_label_or_case_lists',lambda:data['summary']==core.read(folder/'summary.json')==summary(data,folder))
    budgets=core.read(folder/'input_budget_receipts.json')
    check('whole_request_budget_reproduces_with_instructions_and_scope',lambda:budgets==core.input_budget_receipts(inputs,data['baseline'],data['definitions'],folder,core.read(folder/'review_context.json')))
    check('160000_chars_oversize_blocked_no_silent_truncation',lambda:not budgets['automatic_truncation']and all(r['budget_chars']==160000 and r['status']==('BLOCKED'if r['serialized_input_chars']>160000 else'WITHIN_BUDGET')for r in budgets['receipts']))
    check('all_evidence_input_receipts_sha_match',lambda:all(core.sha(folder/p)==h for p,h in core.read(folder/'evidence_sha256_manifest.json')['files'].items()))
    check('historical_bundles_readonly_match_collection_baseline',lambda:historical_unchanged(folder))
    check('complete_manifest_payload_no_unlisted_files',lambda:set(r2.file_hashes(folder))-EXCLUDED==set(m['payload_sha256'])and all(core.sha(folder/p)==h for p,h in m['payload_sha256'].items()))
    historical=folder.resolve().is_relative_to((core.REPO/'reports/archive').resolve())
    if historical:
        code=core.historical_code_hashes(m['analysis_code_sha256'])
        fp=hashlib.sha256(json.dumps(dict(code=code,policy=core.read(folder/'review_policy.json')),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        check('historical_code_policy_budget_fingerprint',lambda:code==m['analysis_code_sha256']and fp==m['policy_fingerprint'])
    else:
        code,fp=fingerprint(folder)
        check('current_code_policy_budget_fingerprint',lambda:code==m['analysis_code_sha256']and fp==m['policy_fingerprint'])
    if git_index:
        check('git_index_exact_payload_bytes',lambda:all(index_sha(folder/p)==h for p,h in m['payload_sha256'].items()))
    import importlib.metadata
    deps={}
    for n in ['pydantic','openpyxl','PyYAML']:
        try:deps[n]=importlib.metadata.version(n)
        except importlib.metadata.PackageNotFoundError:deps[n]='NOT_INSTALLED'
    result=dict(status='FAIL'if any(c['status']=='FAIL'for c in checks)else'PASS',checks=checks,check_count=len(checks),
        policy_version=VERSION,policy_fingerprint=fp,read_only=True,python=sys.version,executable=sys.executable,dependencies=deps,
        records=128,device_runs=0,policy_status='HISTORICAL_POLICY_NOT_CURRENT_REVIEW'if historical else'CURRENT_POLICY',
        scope='SOURCE_SEARCH_AND_SELECTED_BODY_DIFF_AUDIT_NOT_HARDWARE_REPRODUCTION')
    if result['status']=='FAIL':raise ValueError(json.dumps(result,ensure_ascii=False))
    return result


def query_limits(qs):
    counts=Counter((cid,cycle)for q in qs for cid,cycle in q['evidence_cycle_by_task'].items())
    return all(1<=cycle<=3 and count<=4 for (cid,cycle),count in counts.items())


def historical_unchanged(folder):
    baseline=core.read(folder/'collection/source_archive_hashes.json')
    for name,hashes in baseline.items():
        # Collection uses directory names, with platform-native separators.
        p=core.resolve_historical_path(name)
        if p.exists()and {str(Path(k)).replace('\\','/'):v for k,v in hashes.items()}!=r2.file_hashes(p):return False
    return True


def index_sha(path):
    rec=subprocess.run(['git','show',':'+path.relative_to(core.REPO).as_posix()],cwd=core.REPO,capture_output=True)
    return hashlib.sha256(rec.stdout).hexdigest()if rec.returncode==0 else None


def package(folder):
    folder=independent_output(folder,SOURCE);verify(folder);target=folder.with_suffix('.zip')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9)as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():z.write(p,folder.name+'/'+p.relative_to(folder).as_posix())
    with zipfile.ZipFile(target)as z:
        if z.testzip():raise ValueError('ZIP CRC failed')
        for p in folder.rglob('*'):
            if p.is_file()and hashlib.sha256(z.read(folder.name+'/'+p.relative_to(folder).as_posix())).hexdigest()!=core.sha(p):raise ValueError('ZIP member mismatch')
    return dict(file=str(target),sha256=core.sha(target),bytes=target.stat().st_size)
