"""Reproducible RC-001..128 review bundle; no production state/model/device writes."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import platform
import re
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
LEGACY_BUNDLE = REPO / 'reports/rc128-evidence-review-20261111'
DEFAULT = REPO / 'reports/rc128-evidence-review-20261112-r2'


def writable_output(folder):
    """The published R1 snapshot is immutable, including through symlinks."""
    p = Path(folder).resolve()
    if p == LEGACY_BUNDLE.resolve() or LEGACY_BUNDLE.resolve() in p.parents:
        raise ValueError('Historical bundle is read-only; choose an independent output directory.')
    return p


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    p = writable_output(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    return [json.loads(s) for s in Path(path).read_text(encoding='utf-8-sig').splitlines() if s.strip()]


def jsonl(path, values):
    writable_output(path)
    Path(path).write_text(''.join(json.dumps(v, ensure_ascii=False, separators=(',', ':'))+'\n' for v in values), encoding='utf-8', newline='\n')


def init(folder=DEFAULT):
    folder = writable_output(folder)
    workspace = REPO.parent
    inputs = {
        'sources/original/handoff.jsonl': workspace / '数据/CANN_WEEKLY_EXTERNEL_SEARCH_HANDOFF_FOR_CODEX_20261111.jsonl',
        'sources/original/handoff.md': workspace / '数据/CANN_WEEKLY_EXTERNEL_SEARCH_HANDOFF_FOR_CODEX_20261111.md',
        'sources/original/CANN_30_MODES_WIKI_DTS_BASELINE_20261110.md': workspace / '数据/CANN_30_MODES_WIKI_DTS_BASELINE_20261110.md',
        'sources/baseline_30.json': REPO / 'reports/baseline-30-api42-v4-20261111/review_data.json',
        'sources/original/trigger_library.md': REPO / 'knowledge/trigger_library.md',
        'sources/original/api42_trigger_library_original.md': Path(r'D:\project\typora\trigger_library.md'),
        'sources/original/precision_trigger_knowledge_v4.md': REPO / 'knowledge/precision_trigger_knowledge_v4.md',
        'sources/semantic30_prior.json': workspace / 'work/semantic30_relationship_review_20261111/semantic30_data.json',
        'sources/prior_technical_cases.json': REPO / 'reports/expansion-v1-20261110/technical_cases.json',
        'sources/prior_observations.json': REPO / 'reports/expansion-v1-20261110/evidence/observations.json',
        'sources/prior_condition_relations.json': REPO / 'reports/expansion-v1-20261110/condition_relations.json',
        'sources/prior_definitions.json': REPO / 'reports/expansion-v1-20261110/condition_definitions.json',
        'sources/prior_contexts.json': REPO / 'reports/expansion-v1-20261110/evidence/pinned_support_contexts.json',
        'sources/prior_dequant_constants.json': REPO / 'reports/expansion-v1-20261110/evidence/dequant_constants.json',
        'sources/prior_gather_exact_diff.json': REPO / 'reports/expansion-v1-20261110/evidence/gather_1562_diff.json',
    }
    receipts = []
    for name, source in inputs.items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and sha(target) != sha(source):
            raise ValueError(f'Frozen input changed: {name}')
        if not target.exists():
            shutil.copyfile(source, target)
        receipts.append(dict(file=name, original_path=str(source), sha256=sha(target), bytes=target.stat().st_size))
    input_rows = rows(folder / 'sources/original/handoff.jsonl')
    assert len(input_rows) == 128 and len({r['task_id'] for r in input_rows}) == 128
    groups = defaultdict(list)
    for r in input_rows:
        group = ('PUBLIC_CODE_CLUE' if r['public_code_clues'] else 'WIKI_SUMMARY' if r['confirmed_internal_facts'] or r['related_internal_facts'] else 'DTS_SUMMARY' if r['dts_facts'] else 'DESCRIPTION_ONLY')
        groups[group].append(r['task_id'])
    queries = []
    for line in (REPO / 'scripts/rc128_search_queries.txt').read_text(encoding='utf-8').splitlines():
        n, q = line.split('|', 1)
        queries.append(dict(task_id='RC-'+n, round=1, query=q, max_reviewed_new_sources=4))
    assert len(queries) == 128 and {q['task_id'] for q in queries} == {r['task_id'] for r in input_rows}
    write(folder/'search_plan.json', queries)
    write(folder/'input_manifest.json', dict(schema_version='RC128-REVIEW-1', files=receipts, groups=dict(groups),
        input_count=128, state_modified=False, baseline_frozen=False, formal_adoption=False,
        note='文件冻结仅指本报告输入字节快照；不代表工作流Baseline冻结。'))
    return dict(records=len(input_rows), groups={k:len(v) for k,v in groups.items()}, frozen_files=len(receipts))


def pointer(value, path):
    for part in path.strip('/').split('/') if path else []:
        part=part.replace('~1','/').replace('~0','~')
        value=value[int(part)] if isinstance(value,list) else value[part]
    return value


def unpack_tool(value):
    value=value.get('result',value)
    value=value.get('structuredContent',value)
    if isinstance(value.get('content'),str):
        try:
            parsed=json.loads(value['content'])
            if isinstance(parsed,dict):return parsed
        except ValueError:pass
    return value


def source_group(row):
    return ('PUBLIC_CODE_CLUE' if row['public_code_clues'] else 'WIKI_SUMMARY' if row['confirmed_internal_facts'] or row['related_internal_facts'] else 'DTS_SUMMARY' if row['dts_facts'] else 'DESCRIPTION_ONLY')


def parse_search_results(output):
    """Index candidate snippets only. A search hit is never an audited fix."""
    text=output if isinstance(output,str) else json.dumps(output,ensure_ascii=False)
    candidates=[]
    for block in re.split(r'-{12,}',text):
        m=re.search(r'^([^\n]*?)\s*\((https?://[^\s]+)\)\s*\n',block.strip())
        if not m:continue
        title,url=m.groups()
        primary=bool(re.match(r'https://github\.com/(Ascend|vllm-project|pytorch|microsoft|deepspeedai|mindspore-ai|verl-project|NVIDIA|NVIDIA-NeMo|QwenLM|deepseek-ai|triton-lang)/|https://gitcode\.com/(cann|Ascend)/|https://(www\.)?(onnxruntime\.ai|pytorch\.org)/',url,re.I))
        candidates.append(dict(title=title.strip(),url=url,primary_source=primary,
            status='SEARCH_INDEX_ONLY_NOT_FULL_SOURCE',snippet=block.strip()))
    return candidates


def discover_code_leads(record):
    """Surface links/commit hints in summaries; never infer their attribution."""
    found={}
    def walk(value,path=''):
        if isinstance(value,dict):
            for k,v in value.items():walk(v,path+'/'+k.replace('~','~0').replace('/','~1'))
        elif isinstance(value,list):
            for i,v in enumerate(value):walk(v,path+'/'+str(i))
        elif isinstance(value,str):
            for url in re.findall(r'https?://[^\s<>"）)]+',value):
                if not re.match(r'https?://(?:www\.)?(github\.com|gitcode\.com|gitee\.com)/',url,re.I):continue
                item=found.setdefault(('URL',url),dict(kind='URL',value=url,source_pointers=[],attribution='UNVERIFIED'))
                item['source_pointers'].append(path)
            if re.search(r'(?i)commit|bugfix|\bPR\b|提交',value):
                for m in re.finditer(r'(?<![a-zA-Z0-9])[0-9a-f]{7,40}(?![a-zA-Z0-9])',value):
                    hint=m.group()
                    if not re.search('[a-f]',hint):continue
                    item=found.setdefault(('COMMIT_HINT',hint),dict(kind='COMMIT_HINT',value=hint,source_pointers=[],attribution='UNVERIFIED'))
                    item['source_pointers'].append(path)
    walk(record)
    return list(found.values())


def quote_anchor(catalog, source_id, file, json_pointer, quote, *, task_id=None, line=None, kind='SOURCE_DECLARATION', url=None):
    if quote is None or quote=='':return
    json_value=not isinstance(quote,str)
    if json_value:quote=json.dumps(quote,ensure_ascii=False,separators=(',',':'))
    catalog.append(dict(evidence_id=source_id,file=file,json_pointer=json_pointer,
        quote=quote,quote_is_serialized_json_value=json_value,task_id=task_id,jsonl_line=line,kind=kind,url=url,
        source_text_scope='EXACT_FIELD_IN_FROZEN_HANDOFF' if line else 'EXACT_FIELD_IN_ARCHIVED_DOCUMENT',
        independently_fetched_source=kind in ['CURRENT_GITHUB_PATCH','CURRENT_GITHUB_SOURCE','CURRENT_GITHUB_ISSUE']))


def check_patch_hunks(patch):
    """Validate the API did not cut a textual hunk mid-body."""
    lines=patch.splitlines();hunks=[];current=None
    for line in lines:
        m=re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',line)
        if m:
            if current:hunks.append(current)
            current=[int(m.group(2) or 1),int(m.group(4) or 1),0,0]
        elif current and not line.startswith('\\'):
            if line.startswith(' '):current[2]+=1;current[3]+=1
            elif line.startswith('-'):current[2]+=1
            elif line.startswith('+'):current[3]+=1
    if current:hunks.append(current)
    return bool(hunks) and all(a==c and b==d for a,b,c,d in hunks)


def github_documents(folder):
    docs=[]
    for path in sorted((folder/'evidence/github').glob('*.json')):
        raw=read(path);d=unpack_tool(raw);sid=raw['source_id']
        if d.get('error') or raw.get('result',{}).get('isError'):continue
        is_commit=bool(d.get('commit')and d.get('sha')and sid=='GH-ROPE-a3a3d38')
        patches=d.get('patches')or(d.get('files')if is_commit else None)
        if patches:
            for i,item in enumerate(patches):
                text=item.get('patch')
                if not text:continue
                out=folder/'evidence/decoded'/f'{sid}-{i+1}.patch'
                out.parent.mkdir(parents=True,exist_ok=True);out.write_text(text,encoding='utf-8',newline='\n')
                docs.append(dict(evidence_id=f'{sid}:{i+1}',source_id=sid,file=out.relative_to(folder).as_posix(),
                    archive_file=path.relative_to(folder).as_posix(),archive_pointer=f'/files/{i}/patch'if is_commit else f'/patches/{i}/patch',
                    filename=item['filename'],url=d.get('html_url')or d.get('url'),kind='CURRENT_GITHUB_PATCH',
                    text=text,sha256=sha(out),hunks_complete=check_patch_hunks(text),captured_at=raw['captured_at']))
        elif isinstance(d.get('content'),str):
            text=d['content'];out=folder/'evidence/decoded'/f'{sid}.source.txt'
            out.parent.mkdir(parents=True,exist_ok=True);out.write_text(text,encoding='utf-8',newline='\n')
            docs.append(dict(evidence_id=sid,source_id=sid,file=out.relative_to(folder).as_posix(),
                archive_file=path.relative_to(folder).as_posix(),archive_pointer='/content',
                url=d.get('url') or d.get('display_url'),kind='CURRENT_GITHUB_SOURCE',text=text,sha256=sha(out),captured_at=raw['captured_at']))
        elif d.get('pull_request'):
            p=d['pull_request']
            for key in ['body','diff']:
                text=p.get(key) if key=='body' else d.get('diff')
                if not isinstance(text,str) or not text:continue
                out=folder/'evidence/decoded'/f'{sid}-{key}.txt'
                out.parent.mkdir(parents=True,exist_ok=True);out.write_text(text,encoding='utf-8',newline='\n')
                docs.append(dict(evidence_id=f'{sid}:{key}',source_id=sid,file=out.relative_to(folder).as_posix(),
                    archive_file=path.relative_to(folder).as_posix(),archive_pointer='/pull_request/body' if key=='body' else '/diff',
                    url=p.get('url'),kind='CURRENT_GITHUB_PATCH' if key=='diff' else 'CURRENT_GITHUB_ISSUE',
                    text=text,sha256=sha(out),head_sha=p.get('head_sha'),merged=p.get('merged'),draft=p.get('draft'),
                    completeness='PER_FILE_COVERAGE_NOT_PROVEN_BY_THIS_AGGREGATED_DIFF',captured_at=raw['captured_at']))
        elif d.get('body'):
            text=d['body'];out=folder/'evidence/decoded'/f'{sid}.issue.txt'
            out.parent.mkdir(parents=True,exist_ok=True);out.write_text(text,encoding='utf-8',newline='\n')
            docs.append(dict(evidence_id=sid,source_id=sid,file=out.relative_to(folder).as_posix(),
                archive_file=path.relative_to(folder).as_posix(),archive_pointer='/body',url=d.get('html_url'),
                kind='CURRENT_GITHUB_ISSUE',text=text,sha256=sha(out),captured_at=raw['captured_at']))
    return docs


def excerpt(doc, marker, before=2, after=12):
    """Explicit selection range from a complete archived source, no full-source claim."""
    pos=doc['text'].find(marker)
    if pos<0:raise ValueError(f'{doc["evidence_id"]}: absent quote marker {marker}')
    ls=doc['text'].splitlines(keepends=True);n=doc['text'][:pos].count('\n')
    start=max(0,n-before);end=min(len(ls),n+after)
    q=''.join(ls[start:end]);offset=sum(len(s)for s in ls[:start])
    return dict(evidence_id=doc['evidence_id'],file=doc['file'],source_url=doc.get('url'),
        quote=q,char_start=offset,char_end=offset+len(q),line_start=start+1,line_end=end,
        kind=doc['kind'],selection_scope='ONLY_THIS_EXPLICIT_RANGE_REVIEWED',sha256=doc['sha256'])


def original30_index(baseline, semantic):
    old={r['mode_id']:r for r in semantic['rows']};out=[]
    for i,m in enumerate(baseline['modes']):
        s=old[m['mode_id']]
        out.append(dict(mode_id=m['mode_id'],original_order=m['original_order'],name=m['mode_name'],
            original_definition=m['original_definition'],failure_mechanism=m['failure_mechanism'],
            semantic_dimensions=s['semantic_dimensions'],relationships=s['relationships'],
            lifecycle_obligations=s['lifecycle_obligations'],
            current_review_note={'M026':'原表32b的单位未核验，旧MODEL_DERIVED写32B不能作为单位确认；对齐与越界关系仍待证。',
                'M004':'旧window偏移声明与useBufferType漏传讨论分开，尚无修复原文把两者连接。',
                'M006':'V4 minus_one为用户暂记；具体-1语义及6.3 RC1 B060修复证据仍待确认。'}.get(m['mode_id'],'原整理机理及来源声明，不等于原文独立核验。'),
            basis=dict(file='sources/baseline_30.json',json_pointer=f'/modes/{i}',semantic_file='sources/semantic30_prior.json'),
            caveat='原定义与既有审读，不是本轮重新取得历史Wiki/DTS原文或验证根因。',
            historical_source_verified=False,hardware_validated=False))
    return sorted(out,key=lambda r:r['original_order'])


def taxonomy_definitions(baseline):
    definitions=[]
    for c in baseline['api42']['conditions']:
        definitions.append(dict(system='API42',condition_id=c['condition_id'],name=c['name'],definition=c['definition'],
            requires=c.get('family_requires',[])+c.get('requires',[]),skip_if=c.get('family_skip_if',[])+c.get('skip_if',[]),
            class_ids=[c['family_id']],theme_ids=[],source_sha256=baseline['api42']['source_sha256'],
            source_file='sources/original/api42_trigger_library_original.md',line_start=c['line_start'],line_end=c['line_end'],
            source_quote=c['source_quote'],family_source=c.get('family_source')))
    for c in baseline['v4']['conditions']:
        definitions.append(dict(system='V4',condition_id=c['condition_id'],name=c['name'],definition=c['definition'],
            requires=[dict(class_id=p['id'],conditions=p['original_requires'])for p in c['original_class_predicates']],
            skip_if=[dict(class_id=p['id'],conditions=p['original_skip_if'])for p in c['original_class_predicates']],
            class_ids=c['original_class_ids'],theme_ids=c['original_theme_ids'],
            source_sha256=baseline['v4']['source_sha256'],source_file='sources/original/precision_trigger_knowledge_v4.md',
            original_class_predicates=c['original_class_predicates'],original_source_occurrences=c['original_source_occurrences']))
    return definitions


def _build_v1(folder):
    from rc128_decisions import (CONTRACTS,DECISIONS,DECISIONS_INPUT_SHA256,EXTRA_SUBISSUES,PRIOR_CASE_LINKS,
        TEXT_DUPLICATE_CANDIDATES,TC_CONTRACTS,NEW_TECHNICAL_CASES,DIMENSIONS,CANDIDATE_FAMILIES)
    folder=writable_output(folder);manifest=read(folder/'input_manifest.json')
    if sha(folder/'sources/original/handoff.jsonl')!=DECISIONS_INPUT_SHA256:
        raise ValueError('Curated review belongs to a different input SHA; new inputs require a new review, not ID-only reuse.')
    for f in manifest['files']:
        if sha(folder/f['file'])!=f['sha256']:raise ValueError('Frozen source changed: '+f['file'])
    input_rows=rows(folder/'sources/original/handoff.jsonl')
    decisions={d['task_id']:d for d in DECISIONS}
    assert len(decisions)==len(input_rows)==128 and set(decisions)=={r['task_id']for r in input_rows}
    baseline=read(folder/'sources/baseline_30.json');semantic=read(folder/'sources/semantic30_prior.json')
    index=original30_index(baseline,semantic);mode_by_id={m['mode_id']:m for m in index}
    definitions=taxonomy_definitions(baseline);definition_map={(d['system'],d['condition_id']):d for d in definitions}
    assert sha(folder/'sources/original/api42_trigger_library_original.md')==baseline['api42']['source_sha256']
    assert sha(folder/'sources/original/precision_trigger_knowledge_v4.md')==baseline['v4']['source_sha256']
    write(folder/'baseline_30_index.json',dict(modes=index,baseline_library_size=30,
        baseline_replaced=False,comparison_uses_53_catalog=False,
        discussion_updates=baseline['discussions'],source_verified=False,hardware_validated=False))
    write(folder/'condition_definitions.json',dict(definitions=definitions,API42=42,V4=dict(themes=6,classes=31,scenarios=55,guidance=195,execution_methods='E1–E5'),
        mapping_performs_automatic_conversion=False,original_definitions_modified=False))
    catalog=[];results=[];failures=[];conditions=[];comparisons=[];search_index=[];resources={};gaps=[]
    for i,row in enumerate(input_rows,1):
        cid=row['task_id'];d=decisions[cid];n=int(cid[-3:]);refs=[];associations=[];quality=[]
        def add(field,quote,kind='SOURCE_DECLARATION',sid=None,url=None):
            eid=sid or f'{cid}:{field.strip("/").replace("/",":")}'
            quote_anchor(catalog,eid,'sources/original/handoff.jsonl',field,quote,task_id=cid,line=i,kind=kind,url=url)
            if isinstance(quote,str)and quote:refs.append(eid)
            return eid
        for key in ['description','reported_root_cause','weekly_progress']:
            add('/fault/'+key,row['fault'][key])
        if not row['fault']['reported_root_cause']:
            quality.append(dict(code='ROOT_NOT_REPORTED',detail='无根因文本，不从标题/相邻记录/工单自动回填。'))
        for kind in ['confirmed_internal_facts','related_internal_facts','dts_facts']:
            for j,fact in enumerate(row[kind]):
                frefs=[]
                for key,value in fact.items():
                    if isinstance(value,str)and value:
                        frefs.append(add(f'/{kind}/{j}/{key}',value,'HANDOFF_DTS_SUMMARY'if kind=='dts_facts'else'HANDOFF_WIKI_SUMMARY'))
                matching_summary=kind!='dts_facts'and n in [2,8,10,24,29,30,94,121]
                associations.append(dict(resource_id=f'{cid}:{kind}:{j}',source_relation='HANDOFF_SUMMARY_ONLY',
                    upstream_source_label=kind,event_relation='UNDETERMINED',mechanism_relation='RELATED_MECHANISM'if matching_summary else'UNDETERMINED',
                    support_status='PARTIAL_SUPPORT'if matching_summary else'INSUFFICIENT_INFORMATION',evidence_ids=frefs,
                    observed_facts=fact,review=('摘要与本条定位方向有具体吻合，可整理其原文所述事实；尚缺独立原文及事件身份。'if matching_summary else'保留这份摘要描述的技术事实；没有原文URL/快照、明确事件身份和精确子问题，不能继承上游事件判定。'),
                    missing=['当前包未提供原始页面正文/附件和可核验来源ID。'],weekly_event_confirmed=False))
                if kind=='dts_facts'and fact.get('read_status')=='READABLE':
                    quality.append(dict(code='UPSTREAM_READABLE_BODY_NOT_TRANSFERRED',detail='READABLE是上游读取状态，本包仅有摘要。若questions又写无可读正文，两种口径并列，不伪造完整工单。'))
                if re.search(r'(?:\d{8}|\d{7,8}\s*$)',str(fact.get('operator',''))):
                    quality.append(dict(code='OPERATOR_FIELD_CONTAINS_PERSON',detail='operator字段混入人员信息，不作为算子匹配输入。'))
        for j,clue in enumerate(row['public_code_clues']):
            url=clue['link'];rid='PR-'+hashlib.sha256(url.encode()).hexdigest()[:16]
            resource=resources.setdefault(rid,dict(resource_id=rid,url=url,task_ids=[],capture_status='FETCH_BLOCKED',
                capture_attempts=[],original_diff_capture=clue.get('diff_capture'),full_pr_reviewed=False))
            resource['task_ids'].append(cid)
            p_refs=[]
            for key,value in clue.items():
                if isinstance(value,str)and value:p_refs.append(add(f'/public_code_clues/{j}/{key}',value,'UPSTREAM_PR_CLUE',url=url))
            mech=('DIFFERENT_MECHANISM'if n in [22,23,30,49,65,69]else'RELATED_MECHANISM'if n in [2,8,24,32]else'UNDETERMINED')
            associations.append(dict(resource_id=rid,url=url,source_relation='HANDOFF_REFERENCE',event_relation='UNDETERMINED',
                mechanism_relation=mech,support_status='NO_SUPPORT'if n in [23,30,49,65,69]else'INSUFFICIENT_INFORMATION',
                evidence_ids=p_refs,review=d['actual_relation'],missing=[d['missing'],'公开线索原标RAW_DIFF_PARTIAL，本轮GitCode网页仍受阻；旧代码观察另列。'],
                weekly_event_confirmed=False))
        if n==2:quality.append(dict(code='BEAT_BATCH_BETA_AMBIGUITY',detail='上游DTS/标题转录混有beat、batch和公开beta=0；保留原值，不静默归一化。'))
        if n==30:quality.append(dict(code='INPUT_OUTPUT_ALIGNMENT_SCOPE_CONFLICT',detail='周报输出维度与Wiki输入形状说法不同；公开x[2,192]的半宽96不等于输入192非64对齐。'))
        if n==128:quality.append(dict(code='INITIALIZED_UNINITIALIZED_TRANSCRIPTION_CONFLICT',detail='RC128“初始化”与RC110“未初始化”相反，本条只作条件化分类。'))
        if n==121:quality.append(dict(code='AG_COLLECTIVE_NAME_CONFLICT',detail='摘要将AG写成All-Reduce；与原讨论AllGatherMatmul含义不一致，保留原词并补核通信对象。'))
        if n==94:quality.append(dict(code='REPEATED_INTERNAL_SUMMARY_NOT_INDEPENDENT',detail='四份同主题/近重复摘要不计为四个独立事件或独立验证。短提交号被解析为公开代码线索。'))
        logs=[]
        for p in sorted((folder/'evidence/search').glob(cid+'-r*.json')):
            log=read(p);candidates=parse_search_results(log['tool_output'])
            selected=[x for x in candidates if x['primary_source']][:4]
            entry=dict(task_id=cid,round=log['round'],query=log['query'],file=p.relative_to(folder).as_posix(),
                sha256=sha(p),candidates_indexed=len(candidates),selected_candidates=selected,
                selection_scope='候选索引选段；未取全文的命中不算完成代码审查。',
                outcome='PRIMARY_CANDIDATES_NOT_EVENT_VERIFIED'if selected else'NO_USABLE_PRIMARY_MATCH_IN_RETURNED_RESULTS')
            if not candidates and ('error'in str(log['tool_output']).lower()):entry['outcome']='TOOL_BLOCKED'
            search_index.append(entry);logs.append(entry)
        if not logs:raise ValueError('Search not attempted: '+cid)
        primary_refs=[x for x in refs if ':fault:'in x]
        if n==94:primary_refs+=[x for x in refs if ':confirmed_internal_facts:'in x]
        profile=CONTRACTS[d['contract']]
        parts=EXTRA_SUBISSUES.get(n,[(d['contract'],d['object_roles'],d['actual_relation'])])
        fids=[]
        for k,(contract,subject,actual)in enumerate(parts,1):
            prof=CONTRACTS[contract];fid=f'{cid}:REL-{k:02}'
            dimensions=case_dimensions(n,k,prof,subject,DIMENSIONS)
            failures.append(dict(relation_id=fid,task_id=cid,entity_type='WEEKLY_RECORD',issue_scope=subject,
                mechanism_title=prof[0],object_roles=d['object_roles'] if len(parts)==1 else subject,
                measurement_and_representation=dimensions[0],lifecycle=dimensions[1],consumers=dimensions[2],
                dimension_status='SOURCE_DESCRIBED_WITH_UNKNOWNS'if n in DIMENSIONS else'DESIGN_QUESTIONS_NOT_ESTABLISHED_FACTS',
                expected_relation=expected_for_subproblem(n, contract, prof[1]),actual_relation=actual,trigger_predicate='见原记录及适用条件；未给出的实参/谓词保持未知。',
                cause_chain=d['actual_relation'],basis=d['certainty'],evidence_ids=primary_refs,
                evidence_scope='原记录声明/排查进展；不是本轮复现或独立根因确认。',
                alternative_explanations=d['missing'],unresolved=[d['missing']],
                source_verified=False,hardware_validated=False,formal_adoption=False))
            fids.append(fid)
        reason=d['comparison_reason']or(f'与{", ".join(d["similar_mode_ids"]) or "原30条"}的关系仍需具体失效边核对；'+d['missing'])
        cmp_id=cid+':MODE'
        comparisons.append(dict(comparison_id=cmp_id,task_id=cid,entity_type='WEEKLY_RECORD',action=d['action'],
            similar_original_mode_ids=d['similar_mode_ids'],closest_mode_differences=[dict(mode_id=mid,
                original_mechanism=mode_by_id[mid]['failure_mechanism'],difference_or_boundary=reason,
                reference_file='baseline_30_index.json')for mid in d['similar_mode_ids']],
            reason=reason,mechanism_candidate=d['actual_relation'],basis=d['certainty'],evidence_ids=primary_refs,
            implementation_scope=d['implementation_scope'],decision_scope='REVIEW_DRAFT_NOT_FORMAL_ADOPTION',
            proposed_pattern_name=next((x['name']for x in CANDIDATE_FAMILIES if cid in x['members']),None),
            source_verified=False,hardware_validated=False,formal_adoption=False))
        for system,key in [('API42','api42_ids'),('V4','v4_scenario_ids')]:
            for cond in d[key]:
                definition=definition_map[system,cond]
                status='SOURCE_CONTEXT_NOT_CAUSAL_PROOF'
                if d['certainty']in ['HYPOTHESIS','UNKNOWN']or(system=='API42'and cond.startswith('1.C.')):status='LOGICAL_TEST_DIRECTION'
                if n==30:status='PARTIAL_ALIGNMENT_SCOPE_UNRESOLVED'
                crid=f'{cid}:{system}:{cond}'
                conditions.append(dict(relation_id=crid,task_id=cid,entity_type='WEEKLY_RECORD',system=system,condition_id=cond,
                    class_ids=definition['class_ids'],theme_ids=definition['theme_ids'],status=status,
                    applicability='PARTIAL_OR_UNKNOWN',reason=d['actual_relation'],missing=d['missing'],
                    issue_scope='逐子问题采用下列范围，禁止其它子问题继承。',issue_scope_map=condition_subissues(n,system,cond,fids),
                    source_evidence_ids=primary_refs,definition_ref=dict(file='condition_definitions.json',system=system,condition_id=cond),
                    predicate_checks=dict(observed_condition='描述/讨论给出相关构造方向，详见精确原文；未视为唯一致因。',
                        requires=[dict(condition=x,status='UNKNOWN_OR_PARTIAL',reason=d['missing'])for x in definition['requires']],
                        skip_if=[dict(condition=x,status='NOT_FULLY_CHECKED',reason='接口合同/执行器能力不足时保留缺口，不把能力不足写成不适用。')for x in definition['skip_if']]),
                    source_verified=False,hardware_validated=False,historical_event_confirmed=False,counts_as_verified_coverage=False))
        results.append(dict(task_id=cid,input_line=i,original_input=row,source_group=source_group(row),
            discovered_code_leads=discover_code_leads(row),
            search_status='SEARCH_ATTEMPTED_REVIEW_WITH_GAPS',search_rounds=len(logs),search_receipts=[x['file']for x in logs],
            root_cause=dict(conclusion=d['actual_relation'],basis=d['certainty'],independently_confirmed=False),
            implementation_scope=d['implementation_scope'],source_quality_issues=quality,
            source_associations=associations,failure_relation_ids=fids,mode_comparison_id=cmp_id,
            proposed_api42_ids=d['api42_ids'],proposed_v4_scenario_ids=d['v4_scenario_ids'],
            condition_classification_status='SPARSE_ATTEMPT_WITH_REQUIRES_GAPS'if d['api42_ids']or d['v4_scenario_ids']else'NO_SUPPORTED_LABEL_YET_NOT_ALL_NOT_APPLICABLE',
            branch_contexts=[dict(branch_id=x,status='CONTEXT_OR_HYPOTHESIS_NOT_VERIFIED',missing='Branch3同实参同二进制及具体参与者/依赖仍需核对。'if x.startswith('3.')else'限定目标平台与路径，普通版本号不作为构建因果。')for x in d['branch_ids']],
            execution_methods=[dict(method_id=x,status='DESIGN_ONLY_NOT_EXECUTED')for x in d['execution_method_ids']],
            related_technical_case_ids=PRIOR_CASE_LINKS.get(n,[]),evidence_ids=refs,
            unresolved_gaps=[d['missing']],weekly_event_confirmed=False,review_status='AGENT_REVIEW_WITH_GAPS',
            manual_accept_created=False,hardware_validated=False,formal_adoption=False))
        gaps.extend(dict(task_id=cid,kind=q['code'],detail=q['detail'])for q in quality)
        gaps.append(dict(task_id=cid,kind='CLAIM_SPECIFIC_EVIDENCE_GAP',detail=d['missing']))
    for p in (folder/'evidence/fetches').glob('pr-batch-*.json'):
        receipt=read(p)
        for url in receipt['urls']:
            rid='PR-'+hashlib.sha256(url.encode()).hexdigest()[:16]
            if rid in resources:resources[rid]['capture_attempts'].append(p.relative_to(folder).as_posix())
    prior_cases=read(folder/'sources/prior_technical_cases.json')['cases'];observations=read(folder/'sources/prior_observations.json')['observations']
    for i,o in enumerate(observations):
        quote_anchor(catalog,o['observation_id'],'sources/prior_observations.json',f'/observations/{i}',o,
            kind='PRIOR_SELECTED_CODE_OBSERVATION',url=o['source_url'])
        for key in ['before','after','selected_patch_lines']:
            val=o.get(key)
            if isinstance(val,str)and val:
                quote_anchor(catalog,o['observation_id']+':'+key,'sources/prior_observations.json',f'/observations/{i}/{key}',val,
                    kind='PRIOR_SELECTED_CODE_OBSERVATION',url=o['source_url'])
    docs=github_documents(folder)
    selected=primary_excerpts(docs)
    write(folder/'evidence/current_source_index.json',dict(documents=[{k:v for k,v in doc.items()if k!='text'}for doc in docs],selected_excerpts=selected,
        note='取得完整文件与语义审读选段分别记录；非所有下载文件都已全文语义核验。'))
    technical_cases,tf,tc,tm=technical_review(folder,prior_cases,observations,selected,definition_map)
    failures+=tf;conditions+=tc;comparisons+=tm
    for r in results:
        r['related_technical_case_ids']+= [t['technical_case_id']for t in technical_cases if r['task_id']in t.get('related_task_ids',[])and t['technical_case_id']not in r['related_technical_case_ids']]
        context_ids={'RC-111':['GH-FUSION-SCHEMA-PINNED','GH-TORCH-SDPA'],
            'RC-074':['GH-ORT-CANN','GH-ORT-CANN-OPTIONS'],'RC-075':['GH-ORT-CANN','GH-ORT-CANN-OPTIONS'],
            'RC-031':['GH-VLLM-ROPE'],'RC-055':['GH-VLLM-ROPE']}.get(r['task_id'],[])
        r['public_context_excerpt_ids']=[x['excerpt_id']for x in selected if x['evidence_id']in context_ids]
        r['public_context_scope']='API合同/当前实现上下文，不等于历史客户事件或具体修复已证。'
    jsonl(folder/'results.jsonl',results);jsonl(folder/'failure_relations.jsonl',failures)
    jsonl(folder/'condition_relations.jsonl',conditions);jsonl(folder/'mode_comparison.jsonl',comparisons)
    write(folder/'technical_cases.json',dict(cases=technical_cases,prior_case_count=19,new_independent_case_count=len(NEW_TECHNICAL_CASES),weekly_event_confirmed_count=0))
    write(folder/'evidence/quote_index.json',dict(anchors=catalog))
    write(folder/'evidence/resource_index.json',dict(resources=list(resources.values()),unique_original_pr_count=len(resources)))
    write(folder/'search_index.json',dict(searches=search_index,round_limit=3,new_sources_review_limit_per_round=4,
        input_information_does_not_prove_negative=True,search_status_not_equal_evidence_status=True))
    write(folder/'unresolved_gaps.json',dict(gaps=gaps,internal_full_pages_available=False,
        missing_original_weekly_identity='RC号不能凭描述自动回填WB号、Sheet和原行号。'))
    write(folder/'cross_review.json',dict(text_duplicate_candidates=TEXT_DUPLICATE_CANDIDATES,
        candidate_families=CANDIDATE_FAMILIES,candidate_family_count_is_not_proven_new_modes=True,
        grouping_policy='共享资源/标签/症状不合并事件。下面是分析透镜，不宣称同机理。',
        contract_lenses=[dict(contract=k,title=v[0],task_ids=[d['task_id']for d in DECISIONS if d['contract']==k])for k,v in CONTRACTS.items()],
        shared_fix_groups=[dict(id='DEQUANT-12123',technical_case_ids=['TC-DEQUANT-REDUCE-STRIDE','TC-DEQUANT-SCALE-BUFFER'],
            independent_component_causality_isolated=False,weekly_event_confirmed=False)],formal_adoption=False))
    prior_relations=read(folder/'sources/prior_condition_relations.json')['relations']
    summary=summarize(results,failures,conditions,comparisons,technical_cases,baseline,search_index,prior_relations)
    write(folder/'summary.json',summary)
    write(folder/'review_policy.json',dict(version='RC128-RELATION-REVIEW-1',input_budget_chars=160000,
        source_claim_is_not_confirmation=True,logical_classification_allowed=True,sparse_labels_only=True,
        full_taxonomy_predicates_required=True,no_automatic_mapping=True,no_auto_accept=True,
        original_state_modified=False,device_runs=0,scope='报告/离线分析工具；未启动生产模型桥接或drive。'))
    budgets=input_budget_receipts(input_rows,index,definitions,folder)
    write(folder/'input_budget_receipts.json',budgets)
    payload=dict(summary=summary,results=results,failures=failures,conditions=conditions,comparisons=comparisons,
        technical_cases=technical_cases,baseline=index,definitions=definitions,quotes=catalog,
        current_excerpts=selected,cross_review=read(folder/'cross_review.json'))
    render(folder,payload)
    write_readme(folder,summary)
    make_manifest(folder)
    return verify(folder)


def condition_subissues(n,system,condition,ids):
    if n==104:
        return [ids[0]]if condition=='enum_dtype'else[ids[1]]if condition=='enum_mask'else[ids[2]]
    if n==65:return ids[1:]
    if n==22:return [ids[0]]
    if n==1:return [ids[0]]
    if n==30:return [ids[0]]if condition in ['1.2.2','tile_shape']else[ids[1]]
    if n==74:return [ids[1]]if condition in ['1.7.6','intermediate_overflow']else ids
    return ids


def case_dimensions(n,k,profile,subject,overrides):
    scoped={
      1:[('rms_norm计算、乘权重及回转dtype各自分开，实际dtype未给。','单次调用提升/计算/乘权重先后，尚无跨调用证据。','ATB rms_norm计算和后续消费；升精位置待核。'),
         ('RoPE位置/旋转排列语义，不能用norm的dtype事实补齐。','位置嵌入准备→旋转应用；缺具体公式。','MindIE和transformers apply_rotary_pos_emb各自实现。')],
      22:[('专家分数、相等分数及TopK索引不同；输入余弦1不等于逐bit一致。','打分→排序→专家选择；需要tie-breaking合同。','TopK排序逻辑及专家索引消费者。'),
          ('MM浮点累加的类型/次序；未给具体tile和舍入。','门控MM先计算分数，再被后继消费；非同步根因已证。','MM输出和router消费者；允许误差合同待定。')],
      30:[('q=UbFactorDimy；旧(q//64)*8、新q//8；输入192不是直接的q。','多个repeat行被WholeReduceMax读取；实际tiling尚未知。','WholeReduceMax的srcRepStride；可能读错行而不越界。'),
          ('scale广播临时区容量：元素/字节/对齐空间；实际分配取自Host与InitBuffer。','原outLocal兼作临时→Brcb/Copy；新scaleBuf分配/释放与Host预算联动。','Brcb/Copy及随后Div的scale消费者；独立因果未隔离。')],
      65:[('82%是EMA中的原始权重比例，不是dtype误差或INT32阈值。','训练更新EMA→评估读取EMA；两侧生效条件不同。','图像编辑推理的权重消费者。'),
          ('repeat_interleave反向FP32与BF16计算路径，不同于shape>INT32_MAX选路。','同一次反向计算中的表示/累加，缺具体实现修复。','反向梯度消费者及gnorm，不继承EMA效果原因。'),
          ('rmsnorm小算子提升FP32再回转BF16，与未提升路径区分。','运算内转换先后；没有复用/释放证据。','rmsnorm及其后续反向消费者。')],
      74:[('ReduceMean输出偏差，原输入/参考数值未知。','provider精度路径选择→均值计算；保持dtype后仍有差异。','Sub先消费均值；不能以Mul溢出证明均值实现根因。'),
          ('Sub放大输入→Mul中间FP16溢出；输出Inf不等于输入Inf。','先有均值误差，再放大到乘法；尚缺实际范围。','Mul及后续输出消费者。')],
      80:[('timestamp/step_embedder语义未给，不由rmsnorm dtype填充。','时间/步嵌入产生与使用，具体阶段缺证据。','step_embedder消费者待定位。'),
          ('rmsnorm转CPU对照，未分离dtype、公式和时序。','规避后仍有长期gnorm差异，不称完整修复。','norm输出后续训练消费。')],
      81:[('mhc权重BF16→FP32，Pearson0.93→0.97；不是SwiGLU范数。','替换推理侧权重后对照，长期效果未知。','mhc投影/后续logits消费者。'),
          ('5.90625/5.875是两种SwiGLU输出范数；容差未给。','单模块实现对比，尚无确定生命周期故障。','SwiGLU后继消费者；不能与mhc权重实验合并归因。')],
      104:[('linear先升FP32→计算→回BF16的路径；另一侧matmul+bias需等价对照。','单次linear运算的转换先后，不继承数据集处理原因。','linear数值消费者。'),
           ('历史/当前对话片段及mask有效集合，不是dtype。','对话拼接→mask→前向消费；错误mask当前数据。','模型attention/loss mask消费者。'),
           ('packed token与label两侧身份不等价；不是合法相同实参下结果差异。','packing→模型前向/损失计算。','token与label的模型/损失消费者。'),
           ('数据集样本数与GBS整除关系；实际GBS未给，不伪造API batch数。','epoch尾样本处理→下一epoch loss对齐。','dataloader及epoch样本消费。')],
    }
    if n in scoped:return scoped[n][k-1]
    if n in overrides:return overrides[n]
    return ('未取得本子问题完整计量/表示事实；设计核对方向：'+profile[2],
        '创建/初始化/读写/复位/释放责任未完整取证；设计核对方向：'+profile[3],
        '具体失效消费者尚待定位；设计核对方向：'+profile[4])


def primary_excerpts(docs):
    by_id={d['evidence_id']:d for d in docs};out=[]
    selections=[
        ('GH-DEQUANT-PATCH:1','UB_RESERVE',2,12),
        ('GH-DEQUANT-PATCH:2','WholeReduceMax(',3,32),
        ('GH-DEQUANT-PATCH:2','InitBuffer(scaleBuf_',3,9),
        ('GH-DEQUANT-PATCH:3','_REPRO_CASES',2,15),
        ('GH-DEQUANT-12123:body','Fix the precision',0,10),
        ('GH-DS-7371:diff','reduction_stream.wait_stream',3,9),
        ('GH-DS-7371:body','synchronization problem',0,8),
        ('GH-GRAPH-16484','2. Compiled MoE',0,20),
        ('GH-GRAPH-16482:diff','def _ascend_moe_forward_complete(',2,24),
        ('GH-GRAPH-16482:diff','test_complete_moe',2,42),
        ('GH-OPPLUGIN-META','def npu_moe_token_unpermute_grad_meta(',1,11),
        ('GH-FUSION-SCHEMA-PINNED','func: npu_fusion_attention(',0,5),
        ('GH-TORCH-SDPA','scale_factor = 1 / math.sqrt(query.size(-1))',3,7),
        ('GH-ORT-CANN-OPTIONS','AddAssignmentToReference(cann::provider_option_names::kPrecisionMode',2,5),
        ('GH-ORT-CANN','std::string precision_mode',3,6),
        ('GH-VLLM-ROPE','def split_qkv_rmsnorm_rope_kernel',0,22),
        ('GH-ROPE-a3a3d38:1','self.rotary_emb.scaling_factor',4,20),
        ('GH-ROPE-1332:body','cached cosine',0,13),
    ]
    for sid,marker,b,a in selections:
        if sid not in by_id:continue
        x=excerpt(by_id[sid],marker,b,a);x['excerpt_id']=sid+':Q'+str(sum(q['evidence_id']==sid for q in out)+1)
        out.append(x)
    return out


def technical_review(folder,prior,observations,selected,defs):
    from rc128_decisions import CONTRACTS,TC_CONTRACTS,NEW_TECHNICAL_CASES,PRIOR_CASE_LINKS
    failures=[];conditions=[];comparisons=[];cases=[]
    old_rel=read(folder/'sources/prior_condition_relations.json')['relations']
    for c0 in prior:
        c=dict(c0);cid=c['technical_case_id'];kind,action,reason=TC_CONTRACTS[cid];prof=CONTRACTS[kind]
        obs=[o for o in observations if o['technical_case_id']==cid]
        ef=[o['observation_id']+':'+key for o in obs for key in ['before','after','selected_patch_lines']if isinstance(o.get(key),str)and o[key]]
        # selected_patch_lines can be a list: retain full original observation record too.
        if not ef:ef=[o['observation_id']for o in obs]
        current_prefixes={'TC-GRADPROBS-DTYPE':['GH-OPPLUGIN-META'],
            'TC-DEQUANT-REDUCE-STRIDE':['GH-DEQUANT-PATCH:2','GH-DEQUANT-PATCH:3'],
            'TC-DEQUANT-SCALE-BUFFER':['GH-DEQUANT-PATCH:1','GH-DEQUANT-PATCH:2']}.get(cid,[])
        fresh=[x['excerpt_id']for x in selected if any(x['evidence_id']==p for p in current_prefixes)]
        c.update(entity_type='INDEPENDENT_TECHNICAL_CASE',action=action,comparison_reason=reason,
            related_task_ids=[f'RC-{n:03}'for n,ids in PRIOR_CASE_LINKS.items()if cid in ids],
            evidence_ids=ef+fresh,evidence_basis='CURRENT_GITHUB_PATCH'if cid.startswith('TC-DEQUANT-')and fresh else'PRIOR_SELECTED_CODE_WITH_CURRENT_IMPLEMENTATION_CONTEXT'if fresh else'PRIOR_SELECTED_CODE_OBSERVATION',
            original_action=c0['action'],weekly_event_confirmed=False,MODE_ACCEPTED=False,hardware_validated=False,
            source_completeness='选段支持具体主张；旧GitCode PR全文本轮未取到。')
        c['failure_relation_id']=cid+':REL';c['contract']=kind
        dims=technical_dimensions(cid,prof)
        failures.append(dict(relation_id=c['failure_relation_id'],technical_case_id=cid,entity_type='INDEPENDENT_TECHNICAL_CASE',
            issue_scope=c['title'],mechanism_title=prof[0],object_roles=c['operator']+'；'+', '.join(c.get('functions',[])),
            measurement_and_representation=dims[0],lifecycle=dims[1],consumers=dims[2],
            expected_relation=c['expected_behavior'],actual_relation=c['faulty_behavior'],cause_chain=c['failure_mechanism'],
            trigger_predicate=c['trigger_predicate'],basis=c['evidence_basis'],evidence_ids=c['evidence_ids'],
            semantic_detail=technical_detail(cid),unresolved=c['unresolved_gaps'],
            weekly_event_confirmed=False,hardware_validated=False,formal_adoption=False))
        comparisons.append(dict(comparison_id=cid+':MODE',technical_case_id=cid,entity_type='INDEPENDENT_TECHNICAL_CASE',
            action=action,similar_original_mode_ids=c['similar_original_mode_ids'],reason=reason,evidence_ids=c['evidence_ids'],
            basis=c['evidence_basis'],implementation_scope=c['implementation_scope'],formal_adoption=False,
            caveat='代码技术案例的机理比较，不转移为所关联RC/WB客户事件。'))
        for r in old_rel:
            if r['technical_case_id']!=cid:continue
            system=r['condition_system'];cond=r['condition_id'];definition=defs[system,cond]
            conditions.append(dict(relation_id=cid+':'+system+':'+cond,technical_case_id=cid,entity_type='INDEPENDENT_TECHNICAL_CASE',
                system=system,condition_id=cond,class_ids=definition['class_ids'],theme_ids=definition['theme_ids'],
                status='EXPLICIT_CODE_PREDICATE'if r['evidence_kind']=='EXPLICIT_BRANCH_RELATION'else'TEST_CONFIGURATION_CONTEXT'if r['evidence_kind']=='TEST_CONFIGURATION_CONTEXT'else'PRIOR_CODE_RELATED_PROPOSAL',
                reason=r.get('reason',r.get('predicate','见原关系记录及当前技术案例。')),source_relation_record=r,
                source_evidence_ids=c['evidence_ids'],definition_ref=dict(file='condition_definitions.json',system=system,condition_id=cond),
                applicability='PARTIAL_OR_UNKNOWN',predicate_checks=dict(requires=definition['requires'],skip_if=definition['skip_if'],
                    missing='技术谓词/测试配置与完整接口Requires分开；未给出的合同保持未知。'),
                source_verified=False,hardware_validated=False,historical_event_confirmed=False,counts_as_verified_coverage=False))
        cases.append(c)
    for c0 in NEW_TECHNICAL_CASES:
        c=dict(c0);cid=c['technical_case_id'];prof=CONTRACTS[c['contract']]
        refs=[x['excerpt_id']for x in selected if any(x['evidence_id']==p or x['evidence_id'].startswith(p+':')for p in c['evidence_ids'])]
        c.update(entity_type='INDEPENDENT_TECHNICAL_CASE',comparison_reason='与原有同步/编译模式比较的实现详情，未转成周报事件。',
            evidence_ids=refs,evidence_basis='CURRENT_GITHUB_PATCH_AND_AUTHOR_REPORT',weekly_event_confirmed=False,
            MODE_ACCEPTED=False,hardware_validated=False,source_completeness='完整API响应归档，结论只使用注明的代码/说明选段。')
        dims=technical_dimensions(cid,prof)
        failures.append(dict(relation_id=cid+':REL',technical_case_id=cid,entity_type='INDEPENDENT_TECHNICAL_CASE',issue_scope=c['title'],
            mechanism_title=prof[0],object_roles=c['operator'],measurement_and_representation=dims[0],lifecycle=dims[1],consumers=dims[2],
            expected_relation=c['expected_behavior'],actual_relation=c['failure_mechanism'],cause_chain=c['failure_mechanism'],
            trigger_predicate=c['trigger_predicate'],basis=c['evidence_basis'],evidence_ids=refs,unresolved=c['unresolved_gaps'],
            weekly_event_confirmed=False,hardware_validated=False,formal_adoption=False))
        comparisons.append(dict(comparison_id=cid+':MODE',technical_case_id=cid,entity_type='INDEPENDENT_TECHNICAL_CASE',action=c['action'],
            similar_original_mode_ids=c['similar_original_mode_ids'],reason=c['comparison_reason'],basis=c['evidence_basis'],
            evidence_ids=refs,implementation_scope=c['implementation_scope'],formal_adoption=False))
        c['failure_relation_id']=cid+':REL';cases.append(c)
    return cases,failures,conditions,comparisons


def technical_dimensions(cid,profile):
    dims={
      'TC-PLUGIN-ASYNC':('workspace字节容量、executor及ACL tensor句柄；具体大小与释放点未知。','手工分配→异步算子提交→完成→释放；改由EXEC_NPU_CMD封装管理。','frequency_regulator异步执行器；用户已返回不代表设备已经完成。'),
      'TC-GRADPROBS-DTYPE':('grad_probs输出dtype属于probs；grad_unpermuted_tokens是另一输入对象。','Meta推导与真实输出分配应一致；当前固定源码Meta继承probs.dtype。','Meta输出和后继梯度消费，不是scale读取或普通低精升精时机。'),
      'TC-RADIX-SYNC':('UB/WS数据和跨核/流水事件；SToV与SyncAll作用层次分开。','批处理生产/搬运→同步→计算消费；具体失效复现输入尚缺。','RadixTopK的目标UB/WS分支，非所有TopK同症状。'),
      'TC-RADIX-API-WORKSPACE':('W_alloc需覆盖W_kernel+W_api；库API需要的空间不能从预算遗漏。','Host总workspace规划→分配→设备API消费；运行时真实W_api尚未知。','RadixTopK中AscendC库API所需工作区。'),
      'TC-BOOL-REDUCE':('BOOL输出、输入cast、dimList归约轴与910B/910_93条件。','API根据输出dtype/SoC选择ReduceAll分支，再归约目标轴。','ExecuteProd/ReduceAll；尚无完整失败输入，不能单独证明新数学错误机理。'),
      'TC-GEMM-PRECISION-FLAG':('beta=0、cubeMathType=4与enableGemm16In32Out布尔精度请求不同。','计算NeedEnableFp32Output→沿beta=0分支传递→GEMM消费；旧分支漏传。','ExecGemmV3WithAlphaBetaOp最终执行路径，非所有FP16溢出。'),
      'TC-GATHER-SCALAR-COUNT':('index_numel元素计数对1536元素阈值；旧额外乘itemsize，不是sizeof枚举本身。','Host累计index各维→模式选择→Gather实现执行。','non-Regbase、dim0、batchDims0且self_bytes阈值路径的模式判定。'),
      'TC-MATMUL-DISPATCH-DTYPE':('原ori_info dtype与转换后support_info dtype；支持检查须消费实际类型。','输入转换→支持性判定→二进制选择；旧检查仍读转换前对象。','MatMulV3 kernel binary支持选择器，当前证据是功能失败。'),
      'TC-REPEAT-INT32-ROUTE':('xViewShape某轴的元素长度>INT32_MAX；不自动证明某offset已溢出。','API判大shape+合法dtype→选V2执行；不是BF16反向精度转换。','RepeatInterleave分派器；数值损坏的具体输入尚缺。'),
      'TC-FIA-M-PIPE':('矩阵M流水的完成依赖；不是MTE2/核间barrier的同一个层级。','ComputeMm1中相邻Mmad计算段→PipeBarrier<PIPE_M>→下一段。','IfaMatmulFullQuant的矩阵流水消费者；目标模板必须实际命中。'),
      'TC-GMM-K0':('groupType=SPLIT_K且maxK=0；M/N输出仍可能非空。','空归约输入→跳过不适用高阶Matmul tiling→kernel清零输出。','GroupedMatmul空K分支及后续非空输出读取。'),
      'TC-FAG-MTE2-DIM':('dimD是实际数据维度，mm1BaseK是tiling基块K；两者并不总相等。','四处MTE2参数配置→按该长度搬运→计算消费。','FAG bn2 MM12的MTE2指令尺寸参数；不由OOM标题推出每次都越界。'),
      'TC-NSA-TOPK-TMPUB':('旧20*S2align经验容量与GetTopKMaxMinTmpSize返回需求；具体字节阈值未知。','Host查询/预算tmpUbSize→tiling传递→kernel分配和TopK消费。','TopK库API临时UB；Host与kernel必须使用同一实际需求。'),
      'TC-SFAG-EVENT-ID':('scatterTmpK/V及Pong的Mte2WaitV事件身份，不是等待时长或地址。','分配/保存事件ID→UpdateGmOffset赋给runInfo→等待消费者读取；旧漏四项。','SparseFAG runInfo的WaitV/Pong等待逻辑；作者报告卡死。'),
      'TC-MEGAMOE-REUSE-SPAN':('输入行宽K，SwiGLU输出行宽N/2；slotWidth应max(K,N/2)，再乘行/专家数。','仍活跃输入共用槽→输出更宽写入→覆盖后续未读输入；不必出整个allocation。','GMM1后续输入读取与SwiGLU输出写入的复用消费者。'),
      'TC-LI-DUPLICATE-SPACE':('Duplicate额外DUPSIZE=256字节，mask条目和尾偏移64/128须分别解释。','临时区分配→向量Duplicate实际足迹→其它逻辑消费；多项修改尚未隔离。','LightningIndexer的Duplicate/尾mask路径。'),
      'TC-FP8-VSCALE':('当前deScaleVValue与前值deScalePreVValue；per-head/batch/循环块归属尚未知。','准备scale→FlashUpdateNew/LastNew当前更新；前值不能替代当前所需对象。','FP8 GQA update参数的消费者；图中反量化节点位置是另一机制。'),
      'TC-DEQUANT-REDUCE-STRIDE':('q=UbFactorDimy；BLOCK_ELEM8、MASK_NUM_T32 64和块步长8；公式差(q%64)//8。','WholeReduceMax按repeat读取行；实际q与路径未取得，错误读取不必越界。','WholeReduceMax的srcRepStride；输入192、半宽96与实际tiling q分开。'),
      'TC-DEQUANT-SCALE-BUFFER':('scaleBuf容量按行向上取BLOCK_ELEM并乘广播单元和sizeof(float)。','InitBuffer→Brcb临时scale→Copy→FreeTensor；Host同时扣除容量。','Brcb/Copy及Div读取的缩放数据；与归约步长共同修复，单独致因未证。'),
      'TC-DS-IPG-SWAP':('bucket.index两个缓冲索引与当前/归约流依赖，不是梯度dtype转换。','生产数据/上一轮归约→双向wait_stream→交换index→下一轮复用。','当前流与reduction_stream的梯度桶消费；现场是否同版本分支未知。'),
      'TC-GRAPH-LIVE-REDUCTION':('ALLGATHER/MC2/ALLTOALL不同最终TP归约需要，不能把Python布尔决定冻结。','首次trace→图重放时通信方法变化→重复或缺失归约；草案把整runner放不透明边界。','MoERunner.forward及其输出的后续消费；只验证到作者代码/CPU测试说明。'),
      'TC-ROPE-CACHE-EXTENT':('seq_len=max_position_embeddings*scaling_factor是元素/位置长度，不是字节或INT32 overflow。','已有扩展缓存→图模式截取cos/sin→位置索引消费；旧切片只含基准长度。','mla_v1.forward的decode/prefill两处cos/sin消费者；两处同一提交不算两事件。'),
    }
    return dims.get(cid,(profile[2],profile[3],profile[4]))


def technical_detail(cid):
    details={
      'TC-GRADPROBS-DTYPE':dict(required='grad_probs.dtype = probs.dtype',actual='旧Meta使用grad_unpermuted_tokens.dtype；当前固定源码6417–6425行使用probs.dtype。',
          failed_edge='输出语义对象probs → 输出dtype来源',not_equivalent_to='不是先低精计算再升精，也不是FP32输入被强转FP16。'),
      'TC-GATHER-SCALAR-COUNT':dict(required='index_numel = product(index.shape)',actual='旧indexSize = itemsize(index.dtype) * product(index.shape)',
          consumer='1536元素阈值；还要求non-Regbase、dim=0、batchDims=0、self_bytes>=102400等条件。',
          failed_edge='计数生成的字节倍数 → 消费者所需元素数',impact='选路缺陷可说明，数值损坏尚未证明。'),
      'TC-MEGAMOE-REUSE-SPAN':dict(required='slotWidth = max(K, N/2)',actual='旧槽宽K而SwiGLU输出宽N/2',
          predicate='N/2 > K且仍有后续未读输入',failed_edge='输出写入足迹 → 同时存活输入的保留区',
          impact='可能在同一分配区内覆盖未读数据，不必越出整个allocation。'),
      'TC-SFAG-EVENT-ID':dict(required='分配的scatterTmpK/V及Pong事件ID完整赋给runInfo',actual='旧UpdateGmOffset漏四项赋值',
          failed_edge='事件身份初始化/传播 → Mte2WaitV消费者',impact='作者报告偶现卡死，不自动改写为精度故障。'),
      'TC-FP8-VSCALE':dict(required='FlashUpdateNew/LastNew的目标参数接收当前deScaleVValue',actual='旧传deScalePreVValue',
          failed_edge='当前载荷/更新阶段 → 正确scale对象',unknown='变量属于head、batch还是循环块仍需完整上下文。'),
      'TC-DEQUANT-REDUCE-STRIDE':dict(required='q//8',actual='(q//64)*8',difference='(q%64)//8',
          q_role='tl_->UbFactorDimy，不能直接代入输入192；若实际q=96，则旧8、新12，差4。',
          failed_edge='内部行跨度换算/整数截断次序 → WholeReduceMax重复步长',
          public_test='x=[2,192]；门/值半宽96。192本身能被64整除。',independent_component_causality_isolated=False),
      'TC-DEQUANT-SCALE-BUFFER':dict(required='Brcb/Copy临时scale空间容量和生命周期独立满足访问需求',actual='旧outLocal兼作临时区；新scaleBuf_和Host UB预算联动',
          failed_edge='广播指令实际临时足迹 → 缓冲容量/复用合同',independent_component_causality_isolated=False),
      'TC-GEMM-PRECISION-FLAG':dict(required='beta=0路径也把NeedEnableFp32Output结果传到ExecGemmV3WithAlphaBetaOp',
          actual='旧分支未传enableGemm16In32Out',failed_edge='精度请求 → 实际GEMM执行控制项',
          unknown='原周报没有beta和cubeMathType，不能确认其命中这个分支。'),
      'TC-FAG-MTE2-DIM':dict(required='MTE2配置消费实际dimD',actual='旧四处使用mm1BaseK',failed_edge='搬运对象的维度角色 → 指令尺寸参数'),
      'TC-LI-DUPLICATE-SPACE':dict(required='考虑Duplicate额外DUPSIZE=256字节及尾mask访问',actual='旧逻辑缓冲区未充分预留',
          failed_edge='指令物理访问足迹 → 分配容量',unknown='mask[1]→[2]和尾偏移64→128同PR修改，不能各算独立验证。'),
    }
    return details.get(cid,dict(failed_edge='见实际/应有关系、触发谓词和归档观察；缺失公式不补写。'))


def summarize(results,failures,conditions,comparisons,technical,baseline,searches,prior_relations=None):
    from rc128_decisions import CANDIDATE_FAMILIES
    prior_relations=prior_relations or []
    old_api={r['condition_id']for r in baseline['relations']if r['condition_system']=='API42'and'L1'in r['coverage_levels']}
    old_v4={r['condition_id']for r in baseline['relations']if r['condition_system']=='V4'and'L1'in r['coverage_levels']}
    def sets(system,statuses):return sorted({r['condition_id']for r in conditions if r['system']==system and r['status']in statuses})
    return dict(schema_version='RC128-RELATION-REVIEW-1',unique_task_count=len({r['task_id']for r in results}),
        source_groups=dict(Counter(r['source_group']for r in results)),search_attempted_tasks=len({s['task_id']for s in searches}),
        search_round_count=len(searches),original_unique_pr_count=21,
        weekly_subproblem_assessments=sum(r['entity_type']=='WEEKLY_RECORD'for r in failures),
        independent_technical_cases=len(technical),prior_technical_cases=19,new_independent_technical_cases=len(technical)-19,
        failure_relation_rows=len(failures),sparse_condition_rows=len(conditions),condition_rows_by_status=dict(Counter(r['status']for r in conditions)),
        proposed_api42_unique=len({r['condition_id']for r in conditions if r['system']=='API42'}),
        proposed_v4_scenarios_unique=len({r['condition_id']for r in conditions if r['system']=='V4'}),
        weekly_draft_actions=dict(Counter(r['action']for r in comparisons if r['entity_type']=='WEEKLY_RECORD')),
        technical_draft_actions=dict(Counter(r['action']for r in comparisons if r['entity_type']=='INDEPENDENT_TECHNICAL_CASE')),
        new_mode_candidate_rows=sum(c['action']=='NEW_CANDIDATE'for c in comparisons),candidate_review_families=len(CANDIDATE_FAMILIES),
        candidate_count_scope='8条建议归7组待审方向；不是7条已证独立新模式，也未合并RC与TC事件。',
        comparison_to_prior19={system:dict(previous_condition_ids=sorted({r['condition_id']for r in prior_relations if r['condition_system']==system}),
            additional_proposal_ids=sorted({r['condition_id']for r in conditions if r['system']==system}-{r['condition_id']for r in prior_relations if r['condition_system']==system}),
            additional_verified_coverage=0)for system in ['API42','V4']},
        baseline=dict(modes=30,api42_L1_ids=sorted(old_api),v4_L1_scenario_ids=sorted(old_v4)),
        condition_increment=dict(
            API42=dict(explicit_code_predicate_ids=sets('API42',{'EXPLICIT_CODE_PREDICATE'}),
                new_explicit_code_predicate_ids=sorted(set(sets('API42',{'EXPLICIT_CODE_PREDICATE'}))-old_api),
                source_context_ids=sets('API42',{'SOURCE_CONTEXT_NOT_CAUSAL_PROOF'}),
                new_source_context_ids=sorted(set(sets('API42',{'SOURCE_CONTEXT_NOT_CAUSAL_PROOF'}))-old_api),
                logical_test_direction_ids=sets('API42',{'LOGICAL_TEST_DIRECTION'})),
            V4=dict(explicit_code_predicate_ids=sets('V4',{'EXPLICIT_CODE_PREDICATE'}),
                new_explicit_code_predicate_ids=sorted(set(sets('V4',{'EXPLICIT_CODE_PREDICATE'}))-old_v4),
                source_context_ids=sets('V4',{'SOURCE_CONTEXT_NOT_CAUSAL_PROOF'}),
                logical_test_direction_ids=sets('V4',{'LOGICAL_TEST_DIRECTION'}))),
        evidence_verified_weekly_events=0,formal_adoptions=0,hardware_executions=0,manual_accepts_created=0,
        caveat='标签提案、子问题评估和技术案例不能相加当故障数；源码选段/配置不增加历史事件或实机覆盖。',
        runtime=dict(python=sys.version,executable=sys.executable,platform=platform.platform()))


def input_budget_receipts(inputs,index,definitions,folder,review_context=None,input_budget=160000):
    compact_defs=[{k:d[k]for k in ['system','condition_id','name','definition','requires','skip_if','class_ids','theme_ids']}for d in definitions]
    compact_modes=[dict(mode_id=m['mode_id'],name=m['name'],mechanism=m['failure_mechanism'],definition=m['original_definition'])for m in index]
    original_knowledge={name:(folder/'sources/original'/name).read_bytes().decode('utf-8-sig')for name in ['api42_trigger_library_original.md','precision_trigger_knowledge_v4.md']}
    instruction='对本条按子问题独立审读。先事实与证据范围，再原42与V4独立稀疏分类，核对完整Requires/Skip；定位对象、计量/表示、生命周期和消费者之间的失效关系。不得从缺失推出否定，不得继承人工ACCEPT；机理相似不等于同事件。'
    receipts=[]
    for r in inputs:
        task=dict(instruction=instruction,record=r,original30=compact_modes,classification_definitions=compact_defs,
            original_knowledge=original_knowledge,
            input_scope='完整本条转交字段、30定义、原42/V4原文及完整适用谓词；不含完整内网原文，不能声称内网全文核验。')
        if review_context is not None:
            task['revision_instruction']='逐驱动量回答对象、单位、生命周期四项责任及消费者；未知说明原因。语义适用与构造能力分开；四问不能替代复现或产生新增／扩展决定。'
            task['revision_context']=review_context.get(r['task_id'],{'scope':'历史沿用或共享模板纠正，非逐驱动量复审'})
        wire=json.dumps(task,ensure_ascii=False,separators=(',',':'))
        size=len(wire);receipts.append(dict(task_id=r['task_id'],serialized_input_chars=size,budget_chars=input_budget,
            status='BLOCKED'if size>input_budget else'WITHIN_BUDGET',reason='INPUT_TOO_LARGE'if size>input_budget else None,
            serialized_sha256=hashlib.sha256(wire.encode()).hexdigest(),input_scope=task['input_scope']))
    return dict(receipts=receipts,instructions_included=True,serialized_data_included=True,automatic_truncation=False,
        execution_mode='CODEX_AGENT_CURATED_REVIEW_NOT_PRODUCTION_BRIDGE_SUBMISSION',
        budget_check_does_not_prove_session_untruncated=True,definition_count=97,
        note='检查可复建分析输入包规模；不声称128个生产模型请求已提交或执行。下载的大文件仅使用注明范围的原文选段。')


HTML = r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>128条核验 · 条件与失效关系</title><style>
:root{--bg:#f3f5f8;--ink:#182333;--muted:#586777;--line:#d8e0e8;--brand:#155e83;--soft:#e9f3f8}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1480px;margin:auto;padding:28px 24px 80px}h1{font-size:30px;line-height:1.3;margin:0 0 15px}h2{font-size:23px}h3{font-size:19px;margin:0 0 10px}h4{margin:14px 0 6px}p{margin:8px 0}a{color:var(--brand);overflow-wrap:anywhere}button,input,select{font:inherit}button{border:1px solid var(--line);border-radius:7px;background:white;padding:7px 12px;cursor:pointer}button.active{background:var(--brand);color:white}nav{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0}.toolbar{position:sticky;top:0;z-index:3;display:flex;gap:8px;flex-wrap:wrap;padding:12px;background:#f3f5f8f5;border-bottom:1px solid var(--line)}input,select{padding:7px 10px;border:1px solid var(--line);border-radius:6px;background:white}#query{flex:1;min-width:240px}.card,.panel{background:white;border:1px solid var(--line);border-radius:10px;padding:20px;margin:16px 0}.panel{background:var(--soft)}.muted{color:var(--muted)}.tag{display:inline-block;padding:2px 8px;border-radius:5px;background:#edf2f6;margin:2px;font-size:13px;overflow-wrap:anywhere}.warn{background:#fff3d8}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}.metric{padding:15px;background:white;border:1px solid var(--line);border-radius:8px}.metric strong{display:block;font-size:26px;color:var(--brand)}table{width:100%;border-collapse:collapse;margin:10px 0;font-size:14px}th,td{border:1px solid var(--line);text-align:left;vertical-align:top;padding:8px;overflow-wrap:anywhere}th{background:#f0f4f7}details{margin:10px 0}summary{cursor:pointer;color:var(--brand)}pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:6px 0;padding:12px;background:#f5f7fa;border-radius:5px;font:13px/1.6 ui-monospace,Consolas,monospace}blockquote{margin:8px 0;padding:8px 12px;border-left:3px solid #78acc6;background:#f5f9fc;white-space:pre-wrap;overflow-wrap:anywhere}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.scroll{overflow:auto}.small{font-size:13px}.danger{color:#8b3e00}.counter{padding:8px 0;font-weight:600}.line{border-top:1px solid var(--line);padding-top:10px}@media(max-width:760px){main{padding:18px 12px}.grid{grid-template-columns:1fr}th,td{min-width:110px}h1{font-size:24px}}@media print{.toolbar,nav{display:none}details{display:block}.card{break-inside:avoid}}
</style></head><body><main><h1>128条：证据核验、42/55与失效关系</h1><p>逐条保留来源、根因声明与未知项；原30条用于机理比较，原42和V4独立用于条件分类。<b>检索处理完成不等于128条根因已经证实。</b></p><div id="metrics" class="metrics"></div><div class="panel"><b>证据边界</b><p>128条均执行定向检索；原21个GitCode PR本轮网页读取受阻。内部资料目前是转交摘要，历史代码选段与本轮GitHub原文分别标注。所有事件关系、正式入库、人工ACCEPT和设备执行保持独立；本包不启动drive或冻结Baseline。</p><p>API42标签、V4构造、Branch 2/3、E方法与真实失效机理是不同维度。多标签和子问题数不等于故障数。<a href="README.md">复现与交付说明</a> · <a href="manifest.json">SHA清单</a> · <a href="sources/original/handoff.jsonl">原128条</a></p></div><nav id="nav"></nav><div class="toolbar"><input id="query" aria-label="检索报告" placeholder="RC编号、算子、原模式、条件、失效关系"><select id="action" aria-label="模式建议"><option value="">全部建议</option><option value="ADD_CASE">补充案例</option><option value="EXTEND">扩展详情</option><option value="NEW_CANDIDATE">新增候选</option><option value="PENDING">待确认</option></select><select id="group" aria-label="来源组"><option value="">全部来源</option><option>PUBLIC_CODE_CLUE</option><option>WIKI_SUMMARY</option><option>DTS_SUMMARY</option><option>DESCRIPTION_ONLY</option></select><input id="mode" aria-label="原模式编号" placeholder="原模式，如M007" size="12"><button id="reset">清除筛选</button></div><div id="count" class="counter"></div><div id="content"></div><p class="muted small">报告输入与历史记录保留；全量结果在JSONL中。无自动ACCEPT、无Baseline冻结、无正式入库、无NPU/GPU执行。下载完整目录后可离线打开本HTML；本页不发网络请求。</p></main><script type="application/json" id="payload">__PAYLOAD__</script><script>
const D=JSON.parse(document.getElementById('payload').textContent),$=id=>document.getElementById(id);
const ACTION={ADD_CASE:'补充案例',EXTEND:'扩展详情',NEW_CANDIDATE:'新增模式候选',PENDING:'待确认'};
const BASIS={SOURCE_DECLARED:'来源声明，未独立证实',INTERNAL_SUMMARY_DECLARED:'内部摘要声明，代码依据另列',HYPOTHESIS:'逻辑假设/排查方向',UNKNOWN:'根因未知',CURRENT_GITHUB_PATCH:'本轮GitHub代码选段',PRIOR_SELECTED_CODE_OBSERVATION:'历史代码选段',CURRENT_GITHUB_PATCH_AND_AUTHOR_REPORT:'本轮代码及作者说明'};
const QUOTES=new Map(D.quotes.map(x=>[x.evidence_id,x])),FRESH=new Map(D.current_excerpts.map(x=>[x.excerpt_id,x])),CMPS=new Map(D.comparisons.map(x=>[x.comparison_id,x]));let view='cases';
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=x=>typeof x==='string'?x:JSON.stringify(x,null,2),tags=xs=>(xs||[]).map(x=>'<span class="tag">'+esc(x)+'</span>').join('');
function link(url,label){if(!url)return'';try{const u=new URL(url);if(!['http:','https:'].includes(u.protocol))return esc(label||url)}catch{if(!/^(sources|evidence)\/[a-zA-Z0-9_./-]+$/.test(url))return esc(label||url)}return'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">'+esc(label||url)+'</a>'}
function quote(id){const q=QUOTES.get(id)||FRESH.get(id);if(!q)return'<p class="muted">'+esc(id)+'：见完整来源观察。</p>';return'<details><summary>'+esc(id)+' · '+esc(q.kind||'')+'</summary><p class="small">'+link(q.file,q.file)+' '+esc(q.json_pointer||'')+(q.line_start?' L'+q.line_start+'–'+q.line_end:'')+(q.jsonl_line?' 第'+q.jsonl_line+'行':'')+'</p>'+link(q.source_url||q.url,'原来源')+'<blockquote>'+esc(q.quote)+'</blockquote></details>'}
function relationCard(f){return'<section class="line"><h4>'+esc(f.relation_id)+' · '+esc(f.issue_scope)+'</h4><div class="grid"><div><b>对象角色</b><p>'+esc(f.object_roles)+'</p><b>计量与表示域</b><p>'+esc(f.measurement_and_representation)+'</p></div><div><b>生命周期</b><p>'+esc(f.lifecycle)+'</p><b>消费者</b><p>'+esc(f.consumers)+'</p></div></div><p><b>应有关系：</b>'+esc(f.expected_relation)+'</p><p><b>实际失效／待核关系：</b>'+esc(f.actual_relation)+'</p><p><b>因果链及前提：</b>'+esc(f.cause_chain)+' '+esc(f.trigger_predicate)+'</p>'+tags([BASIS[f.basis]||f.basis])+(f.semantic_detail?'<pre>'+esc(fmt(f.semantic_detail))+'</pre>':'')+'<p class="danger"><b>待补：</b>'+esc((f.unresolved||[]).join('；'))+'</p></section>'}
function conditionCard(c){const def=D.definitions.find(d=>d.system===c.system&&d.condition_id===c.condition_id);return'<details><summary>'+esc(c.system+' '+c.condition_id+' · '+(def?.name||''))+' '+tags([c.status])+'</summary><p>'+esc(c.reason)+'</p><p><b>采用子问题：</b>'+esc((c.issue_scope_map||[c.technical_case_id]).join('；'))+'</p><p><b>定义：</b>'+esc(def?.definition)+'</p><p><b>Requires：</b></p><pre>'+esc(fmt(def?.requires))+'</pre><p><b>Skip／能力限制：</b></p><pre>'+esc(fmt(def?.skip_if))+'</pre><p><b>核对状态：</b>'+esc(c.missing||c.predicate_checks?.missing||'完整接口合同未核验；有标签不等于条件已覆盖。')+'</p><p class="muted">此项不增加已证历史故障或实机覆盖。</p></details>'}
function selectRows(q='',a='',g='',m=''){q=q.toLowerCase().trim();m=m.toLowerCase().trim();return D.results.filter(r=>{const c=CMPS.get(r.mode_comparison_id);return(!q||JSON.stringify([r,D.failures.filter(f=>f.task_id===r.task_id)]).toLowerCase().includes(q))&&(!a||c.action===a)&&(!g||r.source_group===g)&&(!m||c.similar_original_mode_ids.some(x=>x.toLowerCase()===m))})}
function caseCard(r){const c=CMPS.get(r.mode_comparison_id),f=D.failures.filter(x=>x.task_id===r.task_id),cs=D.conditions.filter(x=>x.task_id===r.task_id);return'<article class="card" id="'+esc(r.task_id)+'"><h3>'+esc(r.task_id)+' · '+esc(r.original_input.fault.description)+'</h3>'+tags([ACTION[c.action],r.source_group,BASIS[r.root_cause.basis]||r.root_cause.basis,...c.similar_original_mode_ids])+'<p><b>当前判断：</b>'+esc(r.root_cause.conclusion)+'</p><p><b>与原30条的区别：</b>'+esc(c.reason)+'</p><p><b>实现范围：</b>'+esc(r.implementation_scope)+'</p>'+f.map(relationCard).join('')+'<h4>42 / V4：独立、稀疏的分类尝试</h4>'+(cs.map(conditionCard).join('')||'<p class="muted">暂未建立可成立关联；没有判其余97项全部不适用。</p>')+'<p><b>Branch情境：</b>'+tags(r.branch_contexts.map(x=>x.branch_id))+' <b>E方法：</b>'+tags(r.execution_methods.map(x=>x.method_id))+' <span class="muted">仅设计/情境，未执行</span></p><h4>逐资料归属与支持范围</h4><div class="scroll"><table><thead><tr><th>资料</th><th>事件／机理／支持</th><th>事实与缺口</th></tr></thead><tbody>'+r.source_associations.map(s=>'<tr><td>'+esc(s.resource_id)+'<br>'+link(s.url,'原引用')+'<br>'+esc(s.source_relation)+'</td><td>'+esc(s.event_relation)+'<br>'+esc(s.mechanism_relation)+'<br>'+esc(s.support_status)+'</td><td>'+esc(s.review)+'<details><summary>实际转交事实</summary><pre>'+esc(fmt(s.observed_facts||{}))+'</pre></details></td></tr>').join('')+'</tbody></table></div><p class="muted">未从上游全局relation复制确定性结论；不同算子/机制不单独证明不同事件。</p><h4>最贴近本条的来源与独立技术证据</h4>'+r.evidence_ids.filter(x=>x.includes(':fault:')).map(quote).join('')+(r.public_context_excerpt_ids||[]).map(quote).join('')+r.related_technical_case_ids.map(id=>{const t=D.technical_cases.find(x=>x.technical_case_id===id);return t?'<details><summary>'+esc(id)+' · 独立技术案例，不确认本事件</summary>'+technicalCard(t,r.task_id)+'</details>':''}).join('')+'<h4>检索与数据质量</h4><p>实际检索 '+r.search_rounds+' 轮；'+r.search_receipts.map(p=>'<a href="'+esc(p)+'">检索原始返回</a>').join(' · ')+'</p>'+r.source_quality_issues.map(x=>'<p class="danger">'+esc(x.code)+'：'+esc(x.detail)+'</p>').join('')+'<p class="danger"><b>仍缺：</b>'+esc(r.unresolved_gaps.join('；'))+'</p><details><summary>原始记录全文（包括上游判断，均保留）</summary><pre>'+esc(fmt(r.original_input))+'</pre></details></article>'}
function technicalCard(t,embeddedScope=""){const f=D.failures.find(x=>x.technical_case_id===t.technical_case_id);return'<article class="card" id="'+esc((embeddedScope?embeddedScope+"--":"")+t.technical_case_id)+'"><h3>'+esc(t.technical_case_id)+' · '+esc(t.title)+'</h3>'+tags([ACTION[t.action],t.evidence_basis,...t.similar_original_mode_ids])+'<p><b>机理：</b>'+esc(t.failure_mechanism)+'</p><p><b>与原30条比较：</b>'+esc(t.comparison_reason)+'</p><p><b>关联入口：</b>'+esc((t.related_task_ids||[]).join('、'))+'；事件关系仍未确认。</p>'+(f?relationCard(f):'')+D.conditions.filter(c=>c.technical_case_id===t.technical_case_id).map(conditionCard).join('')+'<h4>可追溯代码证据（选段范围）</h4>'+t.evidence_ids.map(quote).join('')+'<p class="danger">'+esc(t.unresolved_gaps.join('；'))+'</p></article>'}
function summaryView(){const s=D.summary;return'<div class="card"><h2>统计口径与增量</h2><pre>'+esc(fmt(s))+'</pre><p>原30条的L1只是技术关联。新增源码谓词、来源上下文和逻辑设计方向分别统计，均不自动增加历史代表或设备覆盖。</p></div><div class="card"><h2>横向审查</h2><p>'+esc(D.cross_review.grouping_policy)+'</p>'+D.cross_review.text_duplicate_candidates.map(x=>'<p><b>'+esc(x.task_ids.join(' / '))+'</b>：'+esc(x.reason)+'</p>').join('')+'<p>未合并任何事件，未把共享PR的两处修改计为两份独立验证。</p></div>'}
function candidateGroups(){return '<div class="panel"><h2>8条候选建议 / 7组待审方向</h2><p>不等于7条已证新模式。RC与公开技术案例仅按待核机理方向归组，不合并事件。</p>'+D.cross_review.candidate_families.map(f=>'<details><summary>'+esc(f.candidate_id+' · '+f.name)+'</summary>'+tags([f.scope,f.basis,...f.members])+'<p>'+esc(f.discriminant)+'</p></details>').join('')+'</div>'}
function renderView(v,q=''){if(v==='cases')return selectRows(q,$('action').value,$('group').value,$('mode').value).map(caseCard).join('');if(v==='summary')return summaryView();if(v==='technical')return D.technical_cases.filter(t=>!q||JSON.stringify(t).toLowerCase().includes(q.toLowerCase())).map(t=>technicalCard(t)).join('');if(v==='candidates')return candidateGroups()+D.comparisons.filter(c=>c.action==='NEW_CANDIDATE'&&(!q||JSON.stringify(c).toLowerCase().includes(q.toLowerCase()))).map(c=>'<article class="card"><h3>'+esc(c.task_id||c.technical_case_id)+'</h3>'+tags([c.basis,c.implementation_scope,...c.similar_original_mode_ids])+'<p>'+esc(c.reason)+'</p><p>'+esc(c.mechanism_candidate||'见独立技术案例及证据选段。')+'</p><p class="danger">候选，未入库；是否为CANN、框架或模型脚本分别列明。</p></article>').join('');if(v==='baseline')return D.baseline.filter(m=>!q||JSON.stringify(m).toLowerCase().includes(q.toLowerCase())).map(m=>'<article class="card"><h3>'+m.original_order+' / '+esc(m.mode_id)+' '+esc(m.name)+'</h3><p>'+'<b>原整理机理（非独立证实）：</b>'+esc(m.failure_mechanism.text||fmt(m.failure_mechanism))+'</p><p class="danger">'+esc(m.current_review_note)+'</p><pre>'+esc(fmt(m.semantic_dimensions))+'</pre><h4>声明及未知的具体关系</h4><pre>'+esc(fmt(m.relationships))+'</pre><details><summary>原定义</summary><pre>'+esc(fmt(m.original_definition))+'</pre></details><p>'+esc(m.caveat)+'</p><h4>本轮对照入口</h4>'+D.comparisons.filter(c=>c.similar_original_mode_ids.includes(m.mode_id)).map(c=>'<p>'+esc(c.task_id||c.technical_case_id)+' · '+esc(ACTION[c.action])+' · '+esc(c.reason)+'</p>').join('')+'</article>').join('');if(v==='conditions')return D.definitions.filter(d=>!q||JSON.stringify(d).toLowerCase().includes(q.toLowerCase())).map(d=>'<article class="card"><h3>'+esc(d.system+' '+d.condition_id+' '+d.name)+'</h3>'+tags(d.class_ids)+'<p>'+esc(d.definition)+'</p><details><summary>完整Requires与Skip</summary><pre>'+esc(fmt({Requires:d.requires,Skip:d.skip_if}))+'</pre></details>'+D.conditions.filter(c=>c.system===d.system&&c.condition_id===d.condition_id).map(c=>'<p>'+esc(c.task_id||c.technical_case_id)+' · '+esc(c.status)+'</p>').join('')+'<p class="muted">未列关联不等于不适用；类别、构造情形与失效机理不互换。</p></article>').join('');if(v==='evidence')return D.current_excerpts.map(x=>'<article class="card"><h3>'+esc(x.excerpt_id)+'</h3>'+quote(x.excerpt_id)+'</article>').join('');return''}
const VIEWS=[['cases','128条逐条结果'],['technical','独立技术案例'],['candidates','新增机理候选'],['baseline','原30条关系索引'],['conditions','原42 / V4定义与关联'],['evidence','本轮最强公开原文'],['summary','统计 / 横向审查']];
function draw(){const q=$('query').value; $('content').innerHTML=renderView(view,q)||'<p>没有匹配项。</p>';$('count').textContent=view==='cases'?selectRows(q,$('action').value,$('group').value,$('mode').value).length+' / 128 条记录；筛选不会改变全量结果':'独立视图；子问题、标签与案例数量分别统计';$('nav').innerHTML=VIEWS.map(([id,label])=>'<button class="'+(view===id?'active':'')+'" onclick="setView(\''+id+'\')">'+esc(label)+'</button>').join('')}
function setView(v){view=v;draw()}
$('metrics').innerHTML=[['128','逐条检索 / 分类尝试'],[D.summary.weekly_subproblem_assessments,'原记录子问题评估'],[D.summary.independent_technical_cases,'独立技术案例'],['0','正式入库 / 设备执行']].map(([v,n])=>'<div class="metric"><strong>'+v+'</strong>'+esc(n)+'</div>').join('');
for(const id of ['query','action','group','mode'])$(id).addEventListener(id==='query'||id==='mode'?'input':'change',draw);
$('reset').addEventListener('click',()=>{for(const id of ['query','action','group','mode'])$(id).value='';draw()});draw();
</script></body></html>'''


def render(folder,payload):
    encoded=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    (folder/'report.html').write_text(HTML.replace('__PAYLOAD__',encoded),encoding='utf-8',newline='\n')


def write_readme(folder,summary):
    actions=summary['weekly_draft_actions'];technical=summary['technical_draft_actions']
    text=f'''# 128条证据核验与失效关系审读

[下载完整离线HTML](report.html)是主要阅读入口，也可[下载完整资料包ZIP](../rc128-evidence-review-20261111.zip)。GitHub文件页显示源码，请下载后用浏览器打开；无需服务器或网络。全部128条原文、逐资料判断、四维关系、分类理由和最强选段都在HTML中，完整来源另行归档。

## 实际完成与边界

- 128/128条完成真实定向检索，{summary['search_round_count']}轮检索原始返回已保存；原始组为16公开线索、12 Wiki摘要、23 DTS摘要、77描述记录。
- 原21个唯一GitCode PR均实际尝试打开，网页工具不可访问，API预检418。没有将其写为“PR不存在”或“无修复”。历史选段与本轮GitHub原文分开。
- 原记录按子问题形成{summary['weekly_subproblem_assessments']}个失效关系评估；每条都有对象、计量/表示域、生命周期、消费者及缺口。不是这些关系都已证实。
- 原记录草案：补充案例{actions.get('ADD_CASE',0)}、扩展详情{actions.get('EXTEND',0)}、新增候选{actions.get('NEW_CANDIDATE',0)}、待确认{actions.get('PENDING',0)}；候选中框架/模型侧项目独立标范围。
- 原记录及独立TC共有8条新增建议，归7组待审方向。RC029和公开V-scale案例保留各自身份，不当作两个独立新模式，也未确认同一具体事件/根因。
- 独立技术案例{summary['independent_technical_cases']}条：保留原19条，新增{summary['new_independent_technical_cases']}条公开来源审读。技术建议：{json.dumps(technical,ensure_ascii=False)}。不计为128条之外新增的客户事件。
- 原42采用`D:\\project\\typora\\trigger_library.md`的原字节版本，SHA见清单。仓库同名文件保留作未选用参考；不使用V5修订版替换。
- V4保持6主题、31条件类、55种构造情形、195参考案例及E1–E5。原42和V4独立，未做自动标签转换。
- 0条新确认WB事件、0条正式入库、0次设备执行、0条人工ACCEPT；没有修改现场state、历史或原知识库，没有冻结Baseline。

## 重要纠偏

- RC002：原周报中间FP16溢出与beta=0精度标志PR不直接等同；保留beat/batch/beta冲突。
- RC023：负索引/未激活专家被消费，不是反向grad_probs.dtype修复；后者独立技术价值保留。
- RC030：dequant与MegaMoE槽复用分开。新取#12123含3个变更文件，x=[2,192]本身对齐64，半宽96和内部UbFactorDimy分开；归约步长与scale临时区共同修复，不计为两次独立因果验证。
- RC049/064：kernel二进制缺失或拼写修改不证明当前权重差异/decode读错根因。
- RC065：EMA、repeat反向dtype、rmsnorm三子问题分开；INT32选路案例不能替代这些根因。
- RC069：图像输入丢失与BOOL归约PR无已证对应。
- RC110/128：“未初始化/初始化”转录冲突保留；不静默修正文句。
- RC094：从Wiki摘要中发现a3a3d38，实际取得2025-06-21公开提交/PR1332；两处图模式seq_len补乘scaling_factor，补到RoPE缓存切片范围机理，不冒充原事件确认。
- M006的V4 minus_one暂记、M026对齐单位待查、M004 useBufferType讨论及其与旧偏移归因的边界继续保留。

## 文件

|文件|用途|
|---|---|
|[results.jsonl](results.jsonl)|128条原输入、检索回执、逐资料关系和结论|
|[failure_relations.jsonl](failure_relations.jsonl)|逐子问题的四维关系、应有/实际关系与证据层级|
|[condition_relations.jsonl](condition_relations.jsonl)|API42/V4稀疏关联；Requires/Skip与支持范围|
|[mode_comparison.jsonl](mode_comparison.jsonl)|原30条比较及新增候选，包含独立TC|
|[baseline_30_index.json](baseline_30_index.json)|原30条定义与关系审读索引，不替换原库|
|[technical_cases.json](technical_cases.json)|独立技术案例，全部不冒充周报事件|
|[summary.json](summary.json)|去重统计、条件增量及范围|
|[cross_review.json](cross_review.json)|横向比较与重复文本线索，未合事件|
|[evidence/current_source_index.json](evidence/current_source_index.json)|本轮GitHub完整响应/文件及精确审读选段|
|[evidence/quote_index.json](evidence/quote_index.json)|原文JSON指针、行号与精确引文|
|[search_index.json](search_index.json)|逐条实际检索范围、候选与原始返回|
|[unresolved_gaps.json](unresolved_gaps.json)|缺口和转录问题|
|[input_manifest.json](input_manifest.json)|输入路径、SHA、来源分组|
|[manifest.json](manifest.json)|完整交付字节清单与分析代码指纹|
|[validation.json](validation.json)|数据、原文引文、预算及Git暂存字节校验|
|[ui_validation.json](ui_validation.json)|离线交互检查，不冒充真实浏览器或设备执行|
|[test_results.txt](test_results.txt)|实际解释器、完整命令输出和针对性回归日志|

`sources/original/`保留用户授权提交的原始MD/JSONL、原库基线MD和原42/V4。`sources/`含既有30条及19条技术案例数据。`evidence/github/`为本轮工具响应，`evidence/decoded/`为完整响应中解出的文件/补丁，`evidence/search/`保留全部检索返回，`evidence/fetches/`保存失败及访问范围。

`summary.json`分别对照原30条和之前19条公开技术案例。`1.C.3`代码分支关系和`1.C.1`测试配置在之前19案例中已经存在，不再算作本轮新发现。新增来源上下文、逻辑构造方向和确切代码谓词不混算为覆盖率。

## 复现和验证

```text
python scripts/rc128_review.py build reports/rc128-evidence-review-20261111
python scripts/rc128_review.py verify reports/rc128-evidence-review-20261111
python -m unittest discover -s tests -p test_rc128_review.py -v
node scripts/verify_rc128_ui.cjs reports/rc128-evidence-review-20261111
```

发布包可离线复建，不需要内网原文、模型服务或设备。`init`仅用于开发机第一次从本机原路径冻结输入，不是Baseline初始化。
本工具复现本轮已审读数据及报告，不自动重跑联网检索或生成模型判断。审读决定绑定本批输入SHA；不能更换128条内容后仅按RC编号继承旧判断。

`input_budget_receipts.json`检查可复建的整条分析资料包，含指令和序列化数据，预算160000字符；不证明会话无截断，也不声称提交了128个生产模型请求。下载的大文件只采用注明范围的选段进行本轮判断。

后续优先补真正缺失的原始身份、关键修复函数和故障实参，复用已有资料；不为补齐Wiki/DTS/PR类型重新全库采集。明确新源码/合同和证据变化后再重算受影响项，不继承历史ACCEPT。
'''
    (folder/'README.md').write_text(text,encoding='utf-8',newline='\n')


def make_manifest(folder):
    excluded={'manifest.json','validation.json','ui_validation.json','test_results.txt','git_publication.json'}
    code_paths=['scripts/rc128_review.py','scripts/rc128_decisions.py','scripts/rc128_search_queries.txt']
    code_hashes={p:sha(REPO/p)for p in code_paths}
    fingerprint=hashlib.sha256(json.dumps(code_hashes,sort_keys=True).encode()).hexdigest()
    write(folder/'manifest.json',dict(schema_version='RC128-BUNDLE-1',policy_fingerprint=fingerprint,analysis_code_sha256=code_hashes,
        payload_sha256={p.relative_to(folder).as_posix():sha(p)for p in sorted(folder.rglob('*'))if p.is_file()and p.name not in excluded},
        original_state_modified=False,baseline_workflow_frozen=False,formal_adoption=False))


def _verify_v1(folder,git_index=False):
    import importlib.metadata
    from rc128_decisions import DECISIONS_INPUT_SHA256
    folder=Path(folder);checks=[]
    def check(name,test):
        try:
            answer=test()
            if answer is False:raise AssertionError(name)
            checks.append(dict(name=name,status='PASS'))
        except Exception as exc:checks.append(dict(name=name,status='FAIL',error=str(exc)))
    rs=rows(folder/'results.jsonl');fs=rows(folder/'failure_relations.jsonl');cs=rows(folder/'condition_relations.jsonl');ms=rows(folder/'mode_comparison.jsonl')
    original=rows(folder/'sources/original/handoff.jsonl');s=read(folder/'summary.json');manifest=read(folder/'manifest.json')
    quote_catalog=read(folder/'evidence/quote_index.json')['anchors'];primary=read(folder/'evidence/current_source_index.json')
    refs={q['evidence_id']for q in quote_catalog}|{q['excerpt_id']for q in primary['selected_excerpts']}
    defs={(d['system'],d['condition_id']):d for d in read(folder/'condition_definitions.json')['definitions']}
    search=read(folder/'search_index.json')['searches'];baseline=read(folder/'baseline_30_index.json')['modes'];tech=read(folder/'technical_cases.json')['cases']
    check('128_contiguous_unique_ids',lambda:[r['task_id']for r in rs]==[f'RC-{i:03}'for i in range(1,129)])
    check('curated_input_hash_locked_not_id_only_reuse',lambda:sha(folder/'sources/original/handoff.jsonl')==DECISIONS_INPUT_SHA256)
    check('original_input_exactly_preserved',lambda:[r['original_input']for r in rs]==original)
    def md_roundtrip():
        text=(folder/'sources/original/handoff.md').read_text(encoding='utf-8-sig');decoder=json.JSONDecoder();pos=0;values=[]
        while pos<len(text):
            while pos<len(text)and text[pos].isspace():pos+=1
            if pos==len(text):break
            v,end=decoder.raw_decode(text,pos);values.append(v);pos=end
        return values==original
    check('source_md_128_objects_equal_jsonl',md_roundtrip)
    check('16_12_23_77_disjoint_source_groups',lambda:Counter(r['source_group']for r in rs)=={'PUBLIC_CODE_CLUE':16,'WIKI_SUMMARY':12,'DTS_SUMMARY':23,'DESCRIPTION_ONLY':77})
    check('all_128_real_search_receipts_present',lambda:{x['task_id']for x in search}=={r['task_id']for r in rs}and all((folder/x['file']).is_file()and sha(folder/x['file'])==x['sha256']for x in search))
    check('max_three_rounds_four_selected_sources',lambda:all(1<=r['search_rounds']<=3 for r in rs)and all(len(x['selected_candidates'])<=4 for x in search))
    resources=read(folder/'evidence/resource_index.json')['resources']
    check('21_pr_resources_unique_all_references_retained',lambda:len(resources)==len({r['url']for r in resources})==21 and sum(len(r['task_ids'])for r in resources)==sum(len(r['public_code_clues'])for r in original))
    check('all_21_fetch_attempts_recorded_no_fake_complete',lambda:all(r['capture_attempts']and not r['full_pr_reviewed']for r in resources))
    check('30_original_modes_preserved_in_original_order',lambda:len(baseline)==30 and [m['original_order']for m in baseline]==list(range(1,31)))
    check('original42_and55_independent_definitions',lambda:Counter(a for a,b in defs)=={'API42':42,'V4':55})
    check('all_sparse_labels_resolve',lambda:all((c['system'],c['condition_id'])in defs for c in cs))
    check('all_128_have_classification_attempt_without_dense_matrix',lambda:all(r['condition_classification_status']for r in rs)and len(cs)<128*(42+55))
    check('all_128_have_specific_relation_and_missing',lambda:all(r['failure_relation_ids']and r['unresolved_gaps']for r in rs)and all(all(f.get(k)for k in ['object_roles','measurement_and_representation','lifecycle','consumers','expected_relation','actual_relation','unresolved'])for f in fs))
    check('unique_subproblem_and_comparison_ids',lambda:len(fs)==len({f['relation_id']for f in fs})and len(ms)==len({m['comparison_id']for m in ms}))
    check('original_mode_comparison_ids_valid',lambda:all(set(m['similar_original_mode_ids'])<={b['mode_id']for b in baseline}for m in ms))
    check('no_event_identity_inherited_from_global_input',lambda:all(s['event_relation']=='UNDETERMINED'for r in rs for s in r['source_associations']))
    check('operator_difference_does_not_become_different_event',lambda:all(a['event_relation']!='DIFFERENT_EVENT'for r in rs for a in r['source_associations']if a['mechanism_relation']=='DIFFERENT_MECHANISM'))
    check('source_claim_not_confirmation_no_accept_freeze_adoption_device',lambda:all(not any(r[k]for k in ['weekly_event_confirmed','manual_accept_created','hardware_validated','formal_adoption'])for r in rs)and all(not t['MODE_ACCEPTED']and not t['weekly_event_confirmed']and not t['hardware_validated']for t in tech))
    check('requires_skip_checks_present_not_omitted',lambda:all('predicate_checks'in c and c['predicate_checks'].get('requires')is not None and c['predicate_checks'].get('skip_if')is not None for c in cs))
    check('labels_never_transfer_to_verified_coverage',lambda:all(not c['counts_as_verified_coverage']and not c['historical_event_confirmed']and not c['hardware_validated']for c in cs))
    check('each_candidate_has_nearest_mode_and_boundary',lambda:all(c['similar_original_mode_ids']and c['reason']for c in ms if c['action']=='NEW_CANDIDATE'))
    cross=read(folder/'cross_review.json')
    check('candidate_families_keep_rc_tc_identity_and_no_adoption',lambda:len(cross['candidate_families'])==7 and
        {member for f in cross['candidate_families']for member in f['members']}==
        {c.get('task_id')or c.get('technical_case_id')for c in ms if c['action']=='NEW_CANDIDATE'}and cross['candidate_family_count_is_not_proven_new_modes'])
    check('embedded_wiki_commit_hint_discovered_with_provenance',lambda:any(x['kind']=='COMMIT_HINT'and x['value']=='a3a3d38'and len(x['source_pointers'])==4 for x in rs[93]['discovered_code_leads']))
    def anchors_valid():
        doc_cache={};rowmap={r['task_id']:r for r in original}
        for q in quote_catalog:
            if q['jsonl_line']:
                obj=original[q['jsonl_line']-1]
                if obj['task_id']!=q['task_id']:return False
            else:
                if q['file']not in doc_cache:doc_cache[q['file']]=read(folder/q['file'])
                obj=doc_cache[q['file']]
            value=pointer(obj,q['json_pointer'])
            actual=json.dumps(value,ensure_ascii=False,separators=(',',':'))if q['quote_is_serialized_json_value']else value
            if actual!=q['quote']:return False
        return True
    check('all_exact_quotes_resolve_to_json_pointer_and_original_line',anchors_valid)
    check('all_conclusion_evidence_ids_resolve',lambda:all(set(f['evidence_ids'])<=refs for f in fs)and all(set(c['source_evidence_ids'])<=refs for c in cs))
    def primary_exact():
        for q in primary['selected_excerpts']:
            text=(folder/q['file']).read_bytes().decode('utf-8')
            if text[q['char_start']:q['char_end']]!=q['quote']or sha(folder/q['file'])!=q['sha256']:return False
        return True
    check('fresh_code_quotes_exact_range_sha',primary_exact)
    dequant=[x for x in primary['documents']if x['source_id']=='GH-DEQUANT-PATCH']
    check('dequant_three_changed_files_complete_patch_hunks',lambda:len(dequant)==3 and all(x['hunks_complete']for x in dequant))
    check('dequant_patch_files_equal_api_filename_list_and_pr_metadata',lambda:
        {x['filename']for x in dequant}==set(unpack_tool(read(folder/'evidence/github/GH-DEQUANT-FILES.json'))['filenames'])and
        len(dequant)==unpack_tool(read(folder/'evidence/github/GH-DEQUANT-12123.json'))['pull_request']['changed_files'])
    check('dequant_early_truncation_formula_correct',lambda:all(q//8-(q//64)*8==(q%64)//8 for q in range(1,2049))and 192%64==0 and 96%64!=0)
    check('dequant_cocomponent_not_independent_cause',lambda:all(not x.get('semantic_detail',{}).get('independent_component_causality_isolated',False)for x in fs if x.get('technical_case_id')in ['TC-DEQUANT-REDUCE-STRIDE','TC-DEQUANT-SCALE-BUFFER']))
    check('critical_002_023_030_049_065_069_not_upgraded_by_wrong_pr',lambda:all(not r['root_cause']['independently_confirmed']and all(not a['weekly_event_confirmed']for a in r['source_associations'])for r in rs if r['task_id']in ['RC-002','RC-023','RC-030','RC-049','RC-065','RC-069']))
    check('128_initialized_uninitialized_conflict_retained',lambda:any(x['code']=='INITIALIZED_UNINITIALIZED_TRANSCRIPTION_CONFLICT'for x in rs[127]['source_quality_issues'])and '未初始化'not in rs[127]['original_input']['fault']['reported_root_cause'])
    check('104_subissues_no_cross_classification',lambda:len(rs[103]['failure_relation_ids'])==4 and all(len(c['issue_scope_map'])==1 for c in cs if c.get('task_id')=='RC-104'))
    check('no_input_inf_label_from_output_nan',lambda:not any(c.get('task_id')in ['RC-004','RC-075','RC-084','RC-110']and c['system']=='API42'and c['condition_id']=='1.7.2'for c in cs))
    budgets=read(folder/'input_budget_receipts.json')
    check('whole_serialized_request_instruction_and_definitions_budgeted',lambda:len(budgets['receipts'])==128 and budgets['definition_count']==97 and budgets['instructions_included']and budgets['serialized_data_included']and not budgets['automatic_truncation']and all(r['serialized_input_chars']<=r['budget_chars']for r in budgets['receipts']))
    check('budget_receipt_is_not_a_model_execution_claim',lambda:budgets['execution_mode']=='CODEX_AGENT_CURATED_REVIEW_NOT_PRODUCTION_BRIDGE_SUBMISSION'and budgets['budget_check_does_not_prove_session_untruncated'])
    check('all_frozen_input_file_bytes_preserved',lambda:all(sha(folder/x['file'])==x['sha256']for x in read(folder/'input_manifest.json')['files']))
    check('all_published_payload_sha256_match',lambda:all((folder/p).is_file()and sha(folder/p)==h for p,h in manifest['payload_sha256'].items()))
    check('historical_policy_fingerprint_self_consistent',lambda:hashlib.sha256(json.dumps(manifest['analysis_code_sha256'],sort_keys=True).encode()).hexdigest()==manifest['policy_fingerprint'])
    payload=re.search(r'<script type="application/json" id="payload">(.*?)</script>',(folder/'report.html').read_text(encoding='utf-8'),re.S)
    html_data=json.loads(payload.group(1))
    check('html_contains_all_128_unmodified_results',lambda:html_data['results']==rs)
    check('html_contains_all_subproblems_labels_comparisons',lambda:html_data['failures']==fs and html_data['conditions']==cs and html_data['comparisons']==ms)
    check('stats_recomputed_not_case_id_or_label_sum',lambda:s==summarize(rs,fs,cs,ms,tech,read(folder/'sources/baseline_30.json'),search,read(folder/'sources/prior_condition_relations.json')['relations']))
    if git_index:
        import subprocess
        def index_matches():
            for rel,h in manifest['payload_sha256'].items():
                path=(folder/rel).relative_to(REPO).as_posix()
                p=subprocess.run(['git','show',':'+path],cwd=REPO,capture_output=True)
                if p.returncode or hashlib.sha256(p.stdout).hexdigest()!=h:return False
            return True
        check('git_index_exact_frozen_bytes_no_line_ending_drift',index_matches)
    dependencies={}
    for name in ['pydantic','openpyxl','PyYAML']:
        try:dependencies[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:dependencies[name]='NOT_INSTALLED'
    failed=sum(x['status']=='FAIL'for x in checks)
    result=dict(status='FAIL'if failed else'PASS',checks=checks,check_count=len(checks),failed=failed,
        python=sys.version,executable=sys.executable,dependencies=dependencies,device_runs=0,
        verification_scope='OFFLINE_DATA_SOURCE_RANGE_AND_REPORT_CONSISTENCY_NOT_HARDWARE_OR_FULL_PR_SEMANTICS')
    if failed:raise ValueError(json.dumps(result,ensure_ascii=False))
    return dict(status='PASS',policy_status='HISTORICAL_POLICY_NOT_CURRENT_REVIEW',policy_fingerprint=manifest['policy_fingerprint'],read_only=True,checks=checks,check_count=len(checks),records=128,subproblems=s['weekly_subproblem_assessments'],
        independent_technical_cases=len(tech),whole_input_chars_max=max(x['serialized_input_chars']for x in budgets['receipts']),python=sys.version,dependencies=dependencies)


def expected_for_subproblem(n, contract, fallback):
    from rc128_six_reviews import EXPECTED
    return EXPECTED.get(f'RC-{n:03}', fallback)


def build(folder=DEFAULT, source_bundle=LEGACY_BUNDLE, field_audit=False):
    from rc128_decisions import DECISIONS_INPUT_SHA256
    folder=writable_output(folder)
    if (folder/'sources/original/handoff.jsonl').exists() and sha(folder/'sources/original/handoff.jsonl') != DECISIONS_INPUT_SHA256:
        raise ValueError('Curated review belongs to a different input SHA; not ID-only reuse.')
    if field_audit:
        from rc128_field_audit import build as build_field_audit
        return build_field_audit(folder, Path(source_bundle))
    from rc128_revision import build_revision
    return build_revision(folder, Path(source_bundle))


def verify(folder=DEFAULT,git_index=False):
    folder=Path(folder)
    version=read(folder/'manifest.json')['schema_version']
    if version=='RC128-BUNDLE-3':
        from rc128_field_audit import verify as verify_field_audit
        return verify_field_audit(folder,git_index)
    if version=='RC128-BUNDLE-2':
        from rc128_revision import verify_revision
        # Old reports retain their original policy, rather than pretending a
        # byte-valid R2 report was reviewed under the new R3 source policy.
        return verify_revision(folder,git_index,historical_policy=True)
    return _verify_v1(folder,git_index)


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('command', choices=['init', 'build', 'verify'])
    p.add_argument('folder', nargs='?', type=Path, default=DEFAULT)
    p.add_argument('--git-index',action='store_true')
    p.add_argument('--source-bundle',type=Path,default=LEGACY_BUNDLE)
    p.add_argument('--field-audit',action='store_true',help='Build the explicit R3 source-audit overlay from an R2 archive.')
    args=p.parse_args()
    if args.command == 'init': result=init(args.folder)
    elif args.command == 'build': result=build(args.folder,args.source_bundle,args.field_audit)
    else: result=verify(args.folder,args.git_index)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
