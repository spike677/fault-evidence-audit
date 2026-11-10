"""Offline review-publication reader, renderer and invariant checks.

This module verifies supplied review data. It does not collect websites, execute
models or devices, alter state, or approve library entries.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
import re
import struct
import sys
from collections import Counter
from pathlib import Path


DATA_FILES={
    'cases':'technical_cases.json','relations':'condition_relations.json',
    'definitions':'condition_definitions.json','baseline':'baseline_api42_index.json',
    'coverage':'api42_coverage.json','tests':'api42_test_catalog.json',
    'designs':'test_designs.json','increments':'mode_increments.json',
    'candidates':'new_mode_adjudication.json','gaps':'api42_gap_plan.json',
    'evidence':'evidence/observations.json','source_receipt':'validation/source_review_receipt.json',
    'strongest':'evidence/strongest_evidence.json','contexts':'evidence/pinned_support_contexts.json',
}
FORBIDDEN=re.compile(r'(?i)(?:(?<![a-z0-9])[a-z]:[\\/]|file://|wiki\.huawei\.com|DTSPortal|clouddragon|codehub\.|\.sqlite(?:3)?\b|run-20\d{6}T\d{6})')


def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def read_bundle(folder):return {key:load(Path(folder)/name)for key,name in DATA_FILES.items()}


def build_strongest_evidence(folder):
    """Select claim-specific evidence, never an event identity/acceptance grade."""
    folder=Path(folder);cases=load(folder/DATA_FILES['cases'])['cases']
    observations=load(folder/DATA_FILES['evidence'])['observations']
    contexts=load(folder/DATA_FILES['contexts'])['contexts']
    order=['TC-GEMM-PRECISION-FLAG','TC-MEGAMOE-REUSE-SPAN','TC-GRADPROBS-DTYPE','TC-GATHER-SCALAR-COUNT',
        'TC-DEQUANT-REDUCE-STRIDE','TC-DEQUANT-SCALE-BUFFER','TC-BOOL-REDUCE','TC-RADIX-SYNC','TC-FIA-M-PIPE',
        'TC-GMM-K0','TC-LI-DUPLICATE-SPACE','TC-NSA-TOPK-TMPUB','TC-RADIX-API-WORKSPACE','TC-SFAG-EVENT-ID',
        'TC-FP8-VSCALE','TC-REPEAT-INT32-ROUTE','TC-MATMUL-DISPATCH-DTYPE','TC-FAG-MTE2-DIM','TC-PLUGIN-ASYNC']
    byid={c['technical_case_id']:c for c in cases};entries=[]
    for cid in order:
        c=byid[cid];available=[o for o in observations if o['technical_case_id']==cid]
        primary=next((o for o in available if o['representation']=='EXACT_OBSERVED_DIFF_LINES'),available[0])
        selected=([primary]+[o for o in available if o is not primary])
        context_ids=[x['source_id']for x in contexts if cid in x['technical_case_ids']]
        pinned=primary['source_url']
        if '/pull/'in pinned and primary.get('blob')and primary.get('file'):
            pinned=pinned.split('/pull/')[0]+'/blob/'+primary['blob']+'/'+primary['file']
        elif '/pull/'in pinned:
            pinned=next((o['source_url']for o in available if '/blob/'in o['source_url']and o.get('file')==primary.get('file')),pinned)
        excerpts={k:primary[k]for k in ['before','after','selected_patch_lines']if primary.get(k)is not None}
        missing=list(c['unresolved_gaps'])
        missing+=['没有本轮设备执行或WB客户事件确认；不据主证据自动批准正式模式。']
        entries.append(dict(technical_case_id=cid,title=c['title'],primary_observation_id=primary['observation_id'],
            supporting_observation_ids=[o['observation_id']for o in selected[1:]],supporting_context_ids=context_ids,
            source_url=primary['source_url'],pinned_source_url=pinned,
            file=primary.get('file'),location=primary.get('line')or primary.get('new_line')or primary.get('json_pointer')or'选定变更段',
            representation=primary['representation'],primary_excerpt=excerpts,
            supports_claim=c['failure_mechanism'],why_selected='当前资料中最贴近该实现缺陷的变更或精确纠错行；并列观察与API/测试上下文保留，不按条数累加独立证据。',
            does_not_prove=missing,mechanism_relation=c['mechanism_relation'],impact_status=c['impact_status'],
            evidence_scope='SELECTED_SOURCE_OR_PATCH_NOT_FULL_PR_VERIFICATION',hardware_execution=False,weekly_event_confirmed=False,
            formal_mode_adoption=False))
    result=dict(entries=entries,case_count=19,
        selection_scope='最强指对当前代码级主张的贴近程度，不代表同客户事件或DIRECT/正式入库。',
        observation_count=len(observations),support_context_count=len(contexts),new_historical_event_count=0,
        shared_fix_groups=[dict(id='GH12123_COMBINED_FIX',technical_case_ids=['TC-DEQUANT-REDUCE-STRIDE','TC-DEQUANT-SCALE-BUFFER'],
            independent_component_cause_confirmed=False,historical_event_count_claimed=0)])
    dump(folder/DATA_FILES['strongest'],result);return result


def write_manifest(folder):
    folder=Path(folder);path=folder/'manifest.json';m=load(path)if path.exists()else{}
    m['bundle_version']='Expansion-v1-full-results-20261110'
    m['report_files']={'canonical':'CANN_EXPANSION_FULL_RESULTS.html','legacy_alias':'CANN_EXPANSION_CANDIDATE_CATALOG.html'}
    m['payload_sha256']={p.relative_to(folder).as_posix():sha(p)for p in sorted(folder.rglob('*'))
        if p.is_file()and p.name not in ['manifest.json','publication_validation.json']}
    dump(path,m)


def recompute_api42(data):
    baseline=data['baseline']['relations'];rows=[r for r in data['relations']['relations']if r['condition_system']=='API42']
    original={r['condition_id']for r in baseline if'L1'in r['coverage_levels']}
    history={r['condition_id']for r in baseline if'L2'in r['coverage_levels']}
    branch={r['condition_id']for r in rows if r['evidence_kind']=='EXPLICIT_BRANCH_RELATION'}
    extra={r['condition_id']for r in rows}
    return dict(original_mode_count=30,related_original_modes=len({r['mode_id']for r in baseline}),
        original_relation_count=len(baseline),original_L1=len(original),original_L2=len(history),
        baseline_plus_new_branch=len(original|branch),baseline_plus_context=len(original|extra),
        technical_cases=len(data['cases']['cases']),api42_technical_cases=len({r['technical_case_id']for r in rows}),
        api42_relation_rows=len(rows),api42_unique_conditions=len(extra),
        new_branch_ids=sorted(branch-original),new_context_only_ids=sorted((extra-original)-branch),
        broad_gap_count=42-len(original|extra),narrow_gap_count=42-len(original|branch))


def validate(folder):
    folder=Path(folder);data=read_bundle(folder);checks=[]
    def check(name,test):
        try:
            if not test():raise AssertionError(name)
            checks.append({'name':name,'status':'PASS'})
        except Exception as exc:checks.append({'name':name,'status':'FAIL','error':str(exc)})
    cs=data['cases']['cases'];cases={c['technical_case_id']:c for c in cs};rs=data['relations']['relations']
    defs={(d['condition_system'],d['condition_id']):d for d in data['definitions']['conditions']}
    evidence={e['observation_id']:e for e in data['evidence']['observations']}
    designs={d['design_id']:d for d in data['designs']['designs']}
    stats=recompute_api42(data)
    check('19_unique_technical_cases',lambda:len(cs)==len(cases)==19)
    check('23_unique_sparse_relations',lambda:len(rs)==len({r['relation_id']for r in rs})==23)
    check('42_and_55_independent_original_definitions',lambda:Counter(s for s,_ in defs)=={'API42':42,'V4':55})
    check('every_case_has_root_sources_and_limits',lambda:all(c['failure_mechanism']and c['evidence_observation_ids']and c['unresolved_gaps']for c in cs))
    check('source_observation_ids_resolve',lambda:all(set(c['evidence_observation_ids'])<=set(evidence)for c in cs))
    check('public_source_urls_are_pinned_or_pr',lambda:all(e['source_url'].startswith(('https://github.com/','https://gitcode.com/'))for e in evidence.values()))
    check('relation_keys_and_mounts_valid',lambda:all(r['technical_case_id']in cases and(r['condition_system'],r['condition_id'])in defs and
        (r['condition_system']!='V4'or set(r['class_scope'])<=set(defs['V4',r['condition_id']]['class_ids']))for r in rs))
    check('all_42_design_index_entries_not_execution_claims',lambda:len(data['tests']['conditions'])==42 and all(not t['hardware_execution_validated']and not t['template_is_executable_coverage']for t in data['tests']['conditions']))
    check('nineteen_design_cards_five_ready_recipes',lambda:len(designs)==19 and sum(d['design_complete']for d in designs.values())==5)
    check('design_references_resolve',lambda:all(set(c['test_design_ids'])<=set(designs)for c in cs))
    check('no_auto_accept_no_device_claims',lambda:all(not c['MODE_ACCEPTED']and not c['hardware_validated']and not c['weekly_event_confirmed']for c in cs))
    check('57_python_33_offline_source_checks_reported_separately',lambda:data['source_receipt']['python_tests']==57 and data['source_receipt']['offline_js_checks']==33 and data['source_receipt']['device_runs']==0)
    check('18_19_20_sets_recomputed',lambda:(stats['original_L1'],stats['baseline_plus_new_branch'],stats['baseline_plus_context'])==(18,19,20))
    check('25_original_relations_18_modes_3_history_conditions',lambda:(stats['original_relation_count'],stats['related_original_modes'],stats['original_L2'])==(25,18,3))
    check('8_api_rows_6_cases_6_conditions',lambda:(stats['api42_relation_rows'],stats['api42_technical_cases'],stats['api42_unique_conditions'])==(8,6,6))
    check('new_branch_C3_context_C1',lambda:stats['new_branch_ids']==['1.C.3']and stats['new_context_only_ids']==['1.C.1'])
    check('recorded_statistics_equal_recalculation',lambda:stats==data['coverage']['recomputed'])
    check('22_broad_23_narrow_gaps',lambda:(stats['broad_gap_count'],stats['narrow_gap_count'])==(22,23))
    check('four_ten_three_two_scope_actions',lambda:Counter(c['action']for c in cs)=={'ADD_CASE_TO_EXISTING':4,'EXTEND_EXISTING_MODE':10,'NEW_CANDIDATE':3,'RELATED_OUT_OF_SCOPE':2})
    check('functional_matmul_not_precision_case',lambda:cases['TC-MATMUL-DISPATCH-DTYPE']['mechanism_relation']=='FUNCTIONAL_OUT_OF_SCOPE'and cases['TC-MATMUL-DISPATCH-DTYPE']['proposed_mode_id']is None)
    check('fia_separate_matrix_pipe_mechanism',lambda:cases['TC-FIA-M-PIPE']['action']=='EXTEND_EXISTING_MODE')
    check('gather_real_old_cpp_not_enum_sizeof',lambda:'ge::GetSizeByDataType(index->GetDataType())'in load(folder/'evidence/gather_1562_diff.json')['old_exact_line'])
    deq=load(folder/'evidence/dequant_constants.json')
    check('pinned_dequant_constants',lambda:deq['constants']=={'BLOCK_SIZE':32,'BLOCK_ELEM':8,'MASK_NUM_T32':64,'MASK_BLK_STRIDE':8})
    check('stride_integer_truncation_host_identity',lambda:all(q//8-(q//64)*8==(q%64)//8 for q in range(1,1025)))
    check('actual_dequant_tiling_remains_unknown',lambda:not cases['TC-DEQUANT-REDUCE-STRIDE']['integer_truncation_analysis']['actual_q_observed'])
    def bool_probe():
        product=1.0
        for _ in range(4096):product=struct.unpack('>f',struct.pack('>f',product*.5))[0]
        return product==0 and all(x!=0 for x in [.5]*4096)
    check('BOOL_logic_vs_FP32_product_host_only',bool_probe)
    def source_units():
        a=designs['DESIGN-DEQUANT-UPSTREAM']['alignment_semantics']
        return a['input_row_bytes']==768 and a['fp32_intermediate_row_bytes']==384 and a['int8_output_row_bytes']==96 and not a['actual_ub_factor_dimy_captured']
    check('dequant_elements_and_bytes_separated',source_units)
    def code_syntax():
        for d in designs.values():
            if d.get('code'):compile(d['code'],d['design_id'],'exec')
        return True
    check('device_recipe_syntax_only_no_execution',code_syntax)
    def check_manifest():
        m=load(folder/'manifest.json')
        for name,h in m['payload_sha256'].items():
            p=(folder/name).resolve()
            if not p.is_relative_to(folder.resolve())or sha(p)!=h:return False
        return True
    check('payload_manifest_hashes',check_manifest)
    check('canonical_LF_bytes_for_git_replay',lambda:all(b'\r\n'not in(folder/name).read_bytes()for name in load(folder/'manifest.json')['payload_sha256']))
    check('no_private_paths_internal_hosts_or_runtime_state',lambda:all(not FORBIDDEN.search(p.read_text(encoding='utf-8'))for p in folder.rglob('*')if p.is_file()and p.suffix in['.json','.jsonl','.html','.md']))
    check('no_init_or_original_30_definition_body',lambda:data['baseline']['publication_scope']=='OPAQUE_MODE_IDS_RELATION_INDEX_NO_INIT_BODY'and all('original_definition'not in m and'original_15_values'not in m for m in data['baseline']['modes']))
    strongest=data['strongest']['entries'];context_ids={c['source_id']for c in data['contexts']['contexts']}
    check('19_claim_scoped_primary_evidence_entries',lambda:len(strongest)==19 and{e['technical_case_id']for e in strongest}==set(cases))
    check('primary_and_supporting_evidence_resolve',lambda:all(e['primary_observation_id']in evidence and set(e['supporting_observation_ids'])<=set(evidence)and set(e['supporting_context_ids'])<=context_ids for e in strongest))
    check('primary_evidence_has_fixed_commit_file_url',lambda:all(re.search(r'/blob/[0-9a-f]{40}/',e['pinned_source_url'])for e in strongest))
    check('strongest_evidence_retains_scope_and_unknowns',lambda:all(e['supports_claim']and e['does_not_prove']and not e['hardware_execution']and not e['weekly_event_confirmed']and not e['formal_mode_adoption']for e in strongest))
    check('four_prior_pinned_public_contexts',lambda:len(context_ids)==4 and all('/blob/'in c['url']and c['capture_origin']=='PRIOR_TARGETED_OBSERVATION'for c in data['contexts']['contexts']))
    check('full_html_and_legacy_alias_are_identical',lambda:(folder/'CANN_EXPANSION_FULL_RESULTS.html').read_bytes()==(folder/'CANN_EXPANSION_CANDIDATE_CATALOG.html').read_bytes())
    return dict(status='PASS'if all(c['status']=='PASS'for c in checks)else'FAIL',python_version=sys.version,
        platform=platform.platform(),dependencies='Python standard library only',check_count=len(checks),
        passed=sum(c['status']=='PASS'for c in checks),checks=checks,recomputed=stats,
        scope='PUBLICATION_DATA_HOST_ARITHMETIC_AND_SYNTAX_ONLY',device_runs=0,formal_mode_adoptions=0)


def render(folder):
    folder=Path(folder);data=read_bundle(folder)
    payload=json.dumps(data,ensure_ascii=False).replace('<','\\u003c').replace('&','\\u0026')
    for name in ['CANN_EXPANSION_FULL_RESULTS.html','CANN_EXPANSION_CANDIDATE_CATALOG.html']:
        (folder/name).write_text(HTML.replace('__DATA__',payload),encoding='utf-8',newline='\n')
    s=recompute_api42(data);text=['# CANN Expansion：公开技术证据与审查结果','',
        '2026-11-10。本包发布19条公开代码技术案例、23条API42/V4稀疏关系及可复核源码定位。正式入库、WB客户事件确认、NPU/GPU执行均为0。',
        '应用版本仍为0.1.20；本次提交增加独立审查数据及离线校验/报告工具。','',
        '## 先看结论','',
        '- 原30条完成审查；18/30模式有API42关系，25条原关系按条件去重为18/42。',
        '- 原18＋新增明确分支关系为19/42（新增1.C.3）。再含quant_mode=1公开测试配置为20/42（另含1.C.1）。19不表示19项全部经过源码证实；20不表示配置单独致因。',
        '- 原历史摘要代表3/42，原测试设计3/42，设备验证0/42；三种统计不混用。',
        '- 当前草案动作为4条案例追加、10条机制详情、3条新候选、2条范围外。动作不是根因相同或精度影响已证实。',
        '- 42项都有设计索引，其中5项有既有配方引用；不是42项可执行覆盖。宽口径22项、窄口径23项缺口仍保留，缺口历史检索未执行。','',
        '## 阅读与复现','',
        '[下载完整HTML结果](CANN_EXPANSION_FULL_RESULTS.html)（单文件，下载后在本地或远端机器打开） · [每案最强证据索引](evidence/STRONGEST_EVIDENCE.md) · [19案例完整数据](technical_cases.json) · [证据观察及定位](evidence/observations.json) · [42条件统计](api42_coverage.json) · [42设计索引](api42_test_catalog.json) · [验证记录](validation/publication_validation.json)','',
        '完整HTML包括案例、模式增量/候选、API42、V4、测试、缺口和所有公开证据；完整表示发布内容齐备，不表示42项已覆盖或设备已验收。旧HTML文件名保留为相同内容的兼容入口。GitHub文件页显示HTML源码，下载后打开才能使用交互视图。','',
        '```sh','python -m faultaudit.review_bundle evidence reports/expansion-v1-20261110',
        'python -m faultaudit.review_bundle render reports/expansion-v1-20261110',
        'python -m faultaudit.review_bundle manifest reports/expansion-v1-20261110',
        'python -m faultaudit.review_bundle verify reports/expansion-v1-20261110',
        'python -m unittest discover -s tests -p test_review_bundle.py -v',
        'node scripts/verify_expansion_publication_ui.cjs reports/expansion-v1-20261110','```','',
        '这些命令只读取公开包、检查数据/Host算术/代码语法并生成静态报告，不执行所展示的设备配方。manifest仅在显式重建后更新哈希，verify不会自动修复或删改数据。','',
        '## 发布边界','',
        '原始Init、30条原定义正文/15列、内部Wiki/DTS、原周报、客户原文、现场state和模型请求响应未提交。原模式只保留不含定义正文的ID—条件关系索引，用于重算统计；公开读者不能据这些摘要计数声称重新验证了历史原文。',
        '与原模式的比较是技术评审建议。源码证据只支持正文中的实际修改，不证明对应客户事件。GitCode多为选段观察，不冒充完整页面或完整PR核验。',
        'API42采用本包冻结定义及其原SHA；仓库knowledge同名Markdown字节SHA不同，不自动互换。V4保持6主题、31条件类、55种构造情形、64挂载、195指导案例及E1–E5，42与V4不自动转换标签。','',
        '## 19条案例总览','',
        '|案例|算子/对象|机理关系|影响状态|草案动作|','|---|---|---|---|---|']
    for c in data['cases']['cases']:text.append('|['+c['technical_case_id']+'](#'+c['technical_case_id'].lower()+')|'+c['operator']+'|'+c['mechanism_relation']+'|'+c['impact_status']+'|'+c['action']+'|')
    observations={o['observation_id']:o for o in data['evidence']['observations']}
    for c in data['cases']['cases']:
        text += ['', '### '+c['technical_case_id'],'','**'+c['title']+'**','',
            '- 根因/实现缺陷：'+c['failure_mechanism'],'- 错误行为：'+c['faulty_behavior'],
            '- 修复机制：'+c['repair_mechanism'],'- 原模式关系：'+str(c['proposed_mode_id']or c['similar_original_mode_ids'])+'；'+c['relation_reason'],
            '- 触发前提：'+c['trigger_predicate'],'- 待证：'+'；'.join(c['unresolved_gaps']),
            '- 测试设计：'+', '.join(c['test_design_ids'])+'（未执行）。','']
        for oid in c['evidence_observation_ids']:
            o=observations[oid];text += ['- ['+o['source_url']+']('+o['source_url']+')；文件 `'+str(o.get('file')or'见链接')+'`；定位 `'+str(o.get('line')or o.get('json_pointer')or'选定变更')+'`；'+o['representation']+'。']
            if o.get('before')or o.get('after'):text += ['```text','before: '+str(o.get('before')or'未摘录'),'after:  '+str(o.get('after')or'未摘录'),'```']
    text += ['', '## 两处精确源码纠错','',
        'Gather原diff旧语句为`ge::GetSizeByDataType(index->GetDataType())`，不是C++枚举变量sizeof。按Tensor元素字节数建立旧谓词模型有据；INT64合法性和真实mode日志仍待现场。见[evidence/gather_1562_diff.json](evidence/gather_1562_diff.json)。',
        'dequant固定版本常量为BLOCK_SIZE=32、BLOCK_ELEM=8、MASK_NUM_T32=64、MASK_BLK_STRIDE=8；旧(q//64)*8与新q//8差为(q%64)//8。实际UbFactorDimy未取得，不能把派生输出96直接代入；错误间距不必越界。见[常量](evidence/dequant_constants.json)和[三文件patch](evidence/github_12123_patch.json)。','',
        '## 验证边界','',
        '私有来源工作区已运行57项Python检查及33项离线JavaScript检查，摘要和来源产物哈希保留在[source_review_receipt.json](validation/source_review_receipt.json)。该回执不是公开包可重跑的私有Init测试。',
        '本包另有可独立重跑的发布检查、单元测试和离线交互检查，结果见[publication_validation.json](validation/publication_validation.json)。浏览器布局、设备内核、现场OpenCode和生产续跑均未在本次发布中验收。','']
    (folder/'README.md').write_text('\n'.join(text),encoding='utf-8',newline='\n')
    best=['# 每条技术案例的最强相关证据','',data['strongest']['selection_scope'],
        '19个主证据入口、32条变更观察及4份先前定向API/测试上下文。它们不是相互独立的19/32/4起故障；GH12123两个子问题共享修复和测试，独立贡献未隔离。','',
        '[完整HTML](../CANN_EXPANSION_FULL_RESULTS.html) · [结构化索引](strongest_evidence.json) · [32条观察](observations.json) · [4份补充上下文](pinned_support_contexts.json)','']
    contexts={x['source_id']:x for x in data['contexts']['contexts']}
    for e in data['strongest']['entries']:
        best+=['## '+e['technical_case_id'],'','**'+e['title']+'**','',
            '- 主证据：['+e['source_url']+']('+e['source_url']+')',
            '- 固定版本：['+e['pinned_source_url']+']('+e['pinned_source_url']+')',
            '- 定位：`'+str(e['file'])+'` · `'+str(e['location'])+'` · '+e['representation'],
            '- 支持的主张：'+e['supports_claim'],'- 不证明：'+'；'.join(e['does_not_prove']),
            '```json',json.dumps(e['primary_excerpt'],ensure_ascii=False,indent=2),'```']
        for ctx_id in e['supporting_context_ids']:
            ctx=contexts[ctx_id];best+=['- 补充上下文：['+ctx_id+']('+ctx['url']+')；'+ctx['scope']+'；'+ctx['lines']+'。']
            best+=['  - '+fact for fact in ctx['facts']]
        best+=['']
    (folder/'evidence/STRONGEST_EVIDENCE.md').write_text('\n'.join(best),encoding='utf-8',newline='\n')


HTML=r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CANN完整公开审查结果 · Expansion v1</title><style>
body{font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif;color:#172a40;background:#f3f6fb;margin:0}header{background:#183c61;color:white;padding:25px}main{max-width:1320px;margin:auto;padding:20px}nav{display:flex;gap:8px;flex-wrap:wrap}button,input{font:inherit;padding:8px 12px;border:1px solid #bdcad9;border-radius:5px;background:white}button{cursor:pointer;color:#145389}.active{background:#17558e;color:white}input{margin:15px 0;width:min(650px,95%)}.card{background:white;border:1px solid #d4deea;border-radius:9px;padding:18px;margin:14px 0}.note{background:#fff2d6;padding:12px;border-left:4px solid #c68b18}h1,h2,h3{margin:0 0 10px}h1{font-size:27px}h2{font-size:22px}h3{font-size:18px}p{margin:8px 0}.pill{display:inline-block;background:#e8f1fb;color:#17558e;border-radius:12px;padding:2px 8px;margin:2px;font-size:12px}table{border-collapse:collapse;width:100%}td,th{padding:8px;text-align:left;border-bottom:1px solid #d7e0eb;vertical-align:top}.scroll{overflow:auto}a{color:#145e9c;overflow-wrap:anywhere}pre{background:#f1f5fa;padding:12px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:550px;overflow:auto}summary{cursor:pointer}details{margin:9px 0}.link{border:0;background:transparent;text-decoration:underline;padding:0}.stats{display:flex;gap:12px;flex-wrap:wrap}.stats strong{font-size:28px;display:block}.stats .card{flex:1;min-width:160px}.muted{color:#5c6f83}code{font-size:13px}</style></head><body><header><h1>CANN完整公开审查结果 · Expansion v1</h1><p>19条案例、模式增量/候选、API42/V4、测试设计、缺口和最强相关证据；完整报告不代表测试全覆盖。正式入库、客户事件确认和设备执行均为0。</p></header><main><nav id="nav"></nav><input id="query" aria-label="搜索" placeholder="搜索案例、算子、模式ID或条件"><div id="result"></div><p class="muted">本HTML自包含所有公开审查数据，无外部JSON/脚本依赖；源码外链需联网。原Init、内部原文和现场state未包含。最新发布检查另见同目录validation/publication_validation.json。</p></main><script type="application/json" id="payload">__DATA__</script><script>
"use strict";const D=JSON.parse(document.getElementById('payload').textContent),CASES=D.cases.cases,REL=D.relations.relations;let view='overview';
const VIEWS=[['overview','总览与18/19/20'],['best','最强相关证据'],['modes','模式增量 / 候选'],['cases','19技术案例'],['api','API42'],['v4','V4条件'],['designs','测试设计'],['gaps','缺口与阶段状态'],['evidence','全部源码证据']];
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const pre=x=>'<pre>'+esc(typeof x==='string'?x:JSON.stringify(x,null,2))+'</pre>';const detail=(name,x)=>'<details><summary>'+esc(name)+'</summary>'+pre(x)+'</details>';const pill=x=>'<span class="pill">'+esc(x)+'</span>';const matches=(x,q)=>!q||JSON.stringify(x).toLowerCase().includes(q.toLowerCase());const selectCases=q=>CASES.filter(c=>matches(c,q));const button=id=>'<button class="link" onclick="focusCase('+esc(JSON.stringify(id))+')">'+esc(id)+'</button>';
function url(u){try{let p=new URL(u);return ['https:','http:'].includes(p.protocol)?p.href:null}catch{return null}}function source(u){const p=url(u);return p?'<a target="_blank" rel="noopener noreferrer" href="'+esc(p)+'">'+esc(u)+'</a>':esc(u)}
function overview(){const s=D.coverage.recomputed;return '<div class="stats">'+[['原L1',18],['原18＋新分支',19],['再含测试配置',20]].map(([n,c])=>'<div class="card"><strong>'+c+'/42</strong>'+n+'</div>').join('')+'</div><section class="card"><h2>统计口径</h2><p>原30条全部完成审查，18/30模式有API42关系。25条原关系去重为18/42；其中历史摘要代表3/42。</p><p>19包含原18项技术推导及新增1.C.3，不表示19项全部已经代码证实。20另含1.C.1测试配置，不证明配置单独致因。</p><p>新增案例有8条API42关系、6案例、6条件ID；其中既有repeat关系复用。42设计索引不等于42测试覆盖；设备验证0/42。</p><div class="note">19条案例保留。4条案例追加、10条机制详情、3条候选、2条范围外。SAME_MECHANISM / FAMILY_RELATED与功能失败、卡死、精度影响分别记录。全部仍为草案。</div>'+detail('重新计算结果',s)+detail('发布范围和来源回执',D.source_receipt)+'</section>'}
function caseCard(c){const obs=D.evidence.observations.filter(o=>c.evidence_observation_ids.includes(o.observation_id));return '<article class="card" id="case-'+esc(c.technical_case_id)+'"><h2>'+esc(c.title)+'</h2>'+pill(c.technical_case_id)+pill(c.action)+pill(c.mechanism_relation)+pill(c.impact_status)+'<p><strong>实现缺陷：</strong>'+esc(c.failure_mechanism)+'</p><p>错误行为：'+esc(c.faulty_behavior)+'</p><p>修复：'+esc(c.repair_mechanism)+'</p><p>原模式：'+esc(c.proposed_mode_id||c.similar_original_mode_ids.join(', '))+'；'+esc(c.relation_reason)+'</p><p>触发：'+esc(c.trigger_predicate)+'</p><p>待证：'+esc(c.unresolved_gaps.join('；'))+'</p>'+obs.map(o=>'<p>'+source(o.source_url)+'</p>'+detail('文件/行号、变更前后及观察范围',o)).join('')+detail('完整公开案例记录（含PR/commit/issue及作者测试说明）',c)+detail('条件关联',REL.filter(r=>r.technical_case_id===c.technical_case_id))+detail('测试配方（未执行）',D.designs.designs.filter(d=>d.technical_case_ids.includes(c.technical_case_id)))+'</article>'}
function conditions(system,q){let defs=D.definitions.conditions.filter(d=>d.condition_system===system&&matches(d,q));return '<section class="card"><h2>'+system+' · 原始定义</h2><p>规则独立；只有稀疏关系，没有补满标签。V4同一构造的挂载范围不自动转移覆盖。</p></section>'+defs.map(d=>{let rs=REL.filter(r=>r.condition_system===system&&r.condition_id===d.condition_id),base=system==='API42'?D.baseline.relations.filter(r=>r.condition_id===d.condition_id):[],t=system==='API42'?D.tests.conditions.find(t=>t.condition_id===d.condition_id):null;return '<article class="card"><h3>'+esc(d.condition_id+' · '+d.name)+'</h3><p>'+esc(d.definition)+'</p>'+detail('Requires / Skip及冻结规则来源',d)+'<p>原模式ID：'+esc([...new Set(base.map(r=>r.mode_id))].join(', ')||'暂无；不等于全局不适用')+'</p>'+rs.map(r=>'<p>'+button(r.technical_case_id)+' '+pill(r.evidence_kind)+' '+esc(r.supporting_fact)+'</p>'+detail('关系证据与限制',r)).join('')+(t?'<p>输入设计：'+esc(t.design_template.input_construction)+'</p><p>Oracle：'+esc(t.design_template.oracle_design)+'</p><p>待绑定：'+esc(t.design_template.remaining_contract_or_capability_gates)+'</p>'+detail('完整设计索引，非执行覆盖',t):'')+'</article>'}).join('')}
function bestEvidenceView(q){const rows=D.strongest.entries.filter(e=>matches(e,q));return '<section class="card"><h2>每案最强相关证据 '+rows.length+' / 19</h2><p>'+esc(D.strongest.selection_scope)+'</p><p>32条变更观察＋4份先前定向API/测试上下文。选段、精确纠错与规范化摘要分别标注，不按条数累加独立事件。</p></section>'+rows.map(e=>{const support=D.contexts.contexts.filter(c=>e.supporting_context_ids.includes(c.source_id));return '<article class="card" id="best-'+esc(e.technical_case_id)+'"><h3>'+button(e.technical_case_id)+' · '+esc(e.title)+'</h3>'+pill(e.representation)+pill(e.mechanism_relation)+'<p>主证据：'+source(e.source_url)+'</p><p>固定版本：'+source(e.pinned_source_url)+'</p><p>文件/位置：<code>'+esc(e.file)+' · '+esc(e.location)+'</code></p><p><strong>支持：</strong>'+esc(e.supports_claim)+'</p>'+pre(e.primary_excerpt)+'<p class="note"><strong>不能据此确认：</strong>'+esc(e.does_not_prove.join('；'))+'</p>'+support.map(c=>'<h3>'+esc(c.source_id)+'</h3>'+source(c.url)+'<p>'+esc(c.scope)+' · '+esc(c.lines)+'</p>'+pre(c.facts)).join('')+detail('主证据选择、其他观察和适用范围',e)+'</article>'}).join('')}
function modeResultsView(q){const entries=D.increments.entries.filter(e=>matches(e,q));let h='<section class="card"><h2>模式增量与候选裁决</h2><p>4条案例追加、10条机制详情、3条候选、2条范围外。FAMILY_RELATED不等于同一机理，动作不等于正式接受。原30正文不在公开包中，仅保留ID—条件索引。</p></section>';for(const [action,name]of [['ADD_CASE_TO_EXISTING','案例追加'],['EXTEND_EXISTING_MODE','机制详情'],['RELATED_OUT_OF_SCOPE','范围外技术关系']]){const rs=entries.filter(e=>e.action===action);h+='<h2>'+name+' · '+rs.length+'</h2>'+rs.map(e=>'<article class="card"><h3>'+button(e.technical_case_id)+' · '+esc(e.mechanism_subtype_name)+'</h3>'+pill(e.mechanism_relation)+pill(e.impact_status)+'<p>原模式：'+esc(e.proposed_mode_id||'无主归属')+'</p><p>'+esc(e.reason)+'</p>'+detail('机制子类型与当前去向',e)+'</article>').join('')}const candidates=D.candidates.candidates.filter(c=>matches(c,q));h+='<h2>新模式候选 · '+candidates.length+'</h2>'+candidates.map(c=>'<article class="card" id="candidate-'+esc(c.draft_id)+'"><h3>'+esc(c.suggested_abstract_name)+'</h3>'+pill(c.independence)+'<p>'+c.technical_case_ids.map(button).join(' / ')+'</p><p>相似原模式：'+esc(c.similar_modes.join(', '))+'</p><p>'+esc(c.why_distinct)+'</p><p class="note">待证：'+esc(c.required_next_evidence.join('；'))+'</p>'+detail('裁决、竞争假设及未正式入库状态',c)+'</article>').join('');return h+detail('保留的历史候选状态',D.candidates.retained_historical_candidates)+detail('30条原模式的分类索引（无Init正文）',D.baseline.modes)}
function gapResultsView(q){const rows=D.gaps.entries.filter(g=>matches(g,q));return '<section class="card"><h2>22项宽口径缺口／23项窄口径缺口</h2><p>quant_mode=1只计入测试配置上下文，所以窄口径还多1.C.1。历史故障代表与测试设计覆盖分开；缺少历史事件不阻断设计。</p><div class="note">42项设计索引已整理；目标API、Oracle、路径或执行能力未齐备的条目仍待绑定。本轮没有执行22项缺口的历史检索，没有NPU/GPU执行。</div>'+detail('原始缺口计划与统计口径',D.gaps)+'</section>'+rows.map(g=>'<article class="card" id="gap-'+esc(g.condition_id)+'"><h3>'+esc(g.condition_id+' · '+g.name)+'</h3>'+pill(g.design_readiness_category)+pill(g.source_collection_status)+'<p>候选接口族：'+esc(g.proposed_operator_family)+'</p><p>下一步：'+esc(g.next_binding_or_evidence)+'</p>'+detail('缺口维度、设计前置条件和状态',g)+'</article>').join('')}
function renderView(v,q=''){if(v==='overview')return overview();if(v==='best')return bestEvidenceView(q);if(v==='modes')return modeResultsView(q);if(v==='gaps')return gapResultsView(q);if(v==='cases')return selectCases(q).map(caseCard).join('')||'<p>无匹配案例</p>';if(v==='api')return conditions('API42',q);if(v==='v4')return conditions('V4',q);if(v==='designs')return '<div class="note">设计配方与真实执行分开。五份完整配方仍依赖现场API/设备，其他十四份缺API或路径。</div>'+D.designs.designs.filter(d=>matches(d,q)).map(d=>'<article class="card"><h3>'+esc(d.design_id)+'</h3>'+pill('NOT_EXECUTED')+'<p>'+d.technical_case_ids.map(button).join(' / ')+'</p><p>'+esc(d.inputs)+'</p><p>路径：'+esc(d.target_path)+'</p><p>参考：'+esc(d.reference)+'</p>'+detail('完整配方、代码及能力缺口',d)+'</article>').join('');if(v==='evidence')return D.evidence.observations.filter(o=>matches(o,q)).map(o=>'<article class="card"><h3>'+esc(o.observation_id)+'</h3>'+source(o.source_url)+detail('原文摘录/规范化观察及定位',o)+'</article>').join('')+D.contexts.contexts.filter(c=>matches(c,q)).map(c=>'<article class="card"><h3>'+esc(c.source_id)+'</h3>'+source(c.url)+'<p>'+esc(c.capture_origin)+' · '+esc(c.scope)+' · '+esc(c.lines)+'</p>'+pre(c.facts)+'</article>').join('');return ''}
function update(){document.getElementById('nav').innerHTML=VIEWS.map(([id,name])=>'<button class="'+(view===id?'active':'')+'" onclick="setView('+esc(JSON.stringify(id))+')">'+esc(name)+'</button>').join('');document.getElementById('result').innerHTML=renderView(view,document.getElementById('query').value)}function setView(v){if(VIEWS.some(([id])=>id===v)){view=v;update()}}function focusCase(id){view='cases';document.getElementById('query').value='';update();document.getElementById('case-'+id)?.scrollIntoView({behavior:'smooth',block:'start'})}document.getElementById('query').addEventListener('input',update);update();
</script></body></html>'''


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['verify','render','evidence','manifest']);parser.add_argument('folder',type=Path);parser.add_argument('--receipt',type=Path)
    args=parser.parse_args(argv)
    if args.action=='render':render(args.folder);return 0
    if args.action=='evidence':build_strongest_evidence(args.folder);return 0
    if args.action=='manifest':write_manifest(args.folder);return 0
    result=validate(args.folder)
    if args.receipt:dump(args.receipt,result)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['status']=='PASS'else 1


if __name__=='__main__':raise SystemExit(main())
