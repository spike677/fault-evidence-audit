"""Offline mechanism -> sparse conditions -> path -> oracle report adapter.

Uses the captured R3 evidence and native sparse/design contracts. No collection,
model client, production state writes, admission, or device executor is added.
Semantic decisions live in the two explicitly Agent-curated review modules.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rc128_review as core
import rc128_revision as r2
import rc128_field_audit as r3
from rc128_mechanism_contracts import validate_analysis
from faultaudit.trigger_v4 import canonical_conditions

VERSION = 'RC128-MECHANISM-DESIGN-4'
OUTPUT = core.REPO / 'reports/archive/rc128-mechanism-design-20261112-r4'
SOURCE = r3.OUTPUT
PILOT_IDS = ['RC-002', 'RC-024', 'RC-029', 'RC-030', 'RC-031', 'RC-099', 'RC-122']
BUDGET = 160000
CODE = ['scripts/rc128_mechanism_review.py', 'scripts/rc128_mechanism_contracts.py',
        'scripts/rc128_mechanism_cases.py', 'scripts/rc128_mechanism_remaining.py',
        'scripts/rc128_mechanism_html.py', 'faultaudit/trigger_sparse.py',
        'faultaudit/trigger_design.py', 'faultaudit/trigger_assessment.py',
        'faultaudit/trigger_v4.py']
EXCLUDED = {'manifest.json', 'validation.json', 'ui_validation.json',
            'test_results.txt', 'git_publication.json', 'browser_validation.json'}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def code_hashes():
    return {p: core.sha(core.REPO / p) for p in CODE}


def policy():
    return dict(version=VERSION, budget_chars=BUDGET, definitions='FROZEN_ORIGINAL42_AND_V4_INDEPENDENT',
        classification='SPARSE_SELECTED_RULES_NO_CROSSWALK', source='R3_CAPTURED_EVIDENCE_REUSED_NO_NEW_SEARCH',
        semantics='APPLICABILITY_NOT_CAUSALITY; CONSTRUCTION_AND_EXECUTION_SEPARATE',
        execution='OFFLINE_DESIGN_ONLY', mode_decision='PENDING', pilot_ids=PILOT_IDS)


def fingerprint():
    return digest(dict(code=code_hashes(), policy=policy()))


def definitions(data):
    """Keep original definitions/predicates; V4 class and construction separate."""
    result = {}
    for d in data['definitions']:
        scheme = 'ORIGINAL42' if d['system'] == 'API42' else 'V4'
        version = scheme + ':' + d['source_sha256']
        if scheme == 'ORIGINAL42':
            rule = dict(scheme=scheme, definition_version=version, id=d['condition_id'],
                name=d['name'], definition=d['definition'], requires=deepcopy(d['requires']),
                skip_if=deepcopy(d['skip_if']), construction_ids=[], constructions=[],
                source_file=d['source_file'], source_sha256=d['source_sha256'],
                source_quote=d['source_quote'])
            # Retain the frozen original API-control family boundary, including
            # the prose restriction outside its Requires list. No revised42.
            if d['condition_id'].startswith('1.C.'):
                boundary = next(line.strip().lstrip('\\> ').strip()
                    for line in d['family_source']['source_quote'].splitlines() if '仅当 schema/' in line)
                rule['requires'].append(boundary)
            result[scheme, rule['id']] = rule
        else:
            for c in d['original_class_predicates']:
                key = scheme, c['id']
                if key not in result:
                    result[key] = dict(scheme=scheme, definition_version=version, id=c['id'],
                        name=c['name'], definition=c['definition'],
                        requires=deepcopy(c['original_requires']), skip_if=deepcopy(c['original_skip_if']),
                        construction_ids=deepcopy(c['construction_ids']), constructions=[],
                        source_file=d['source_file'], source_sha256=d['source_sha256'],
                        source_quote=c['source_quote'])
                result[key]['constructions'].append(dict(id=d['condition_id'], name=d['name'],
                    definition=d['definition'], source_quote=d['original_source_occurrences']))
    return list(result.values())


def rule_for(candidate, rules):
    scheme = 'ORIGINAL42' if candidate['system'] in ('API42', 'ORIGINAL42') else 'V4'
    cid = candidate['condition_id']
    if scheme == 'V4':
        # A construction can be mounted in several classes. Never infer that
        # every mount applies; an explicit class is required from the reviewer.
        explicit = candidate.get('class_id')
        if explicit:
            cid = explicit
        elif not any(r['scheme'] == 'V4' and r['id'] == cid for r in rules):
            return None
    return next((r for r in rules if (r['scheme'], r['id']) == (scheme, cid)), None)


def select_conditions(candidates, rules, fact_id, analysis_id):
    labels, links, notes = [], [], []
    selected = set()
    for c in candidates:
        rule = rule_for(c, rules)
        if not rule:
            notes.append(dict(candidate=c, status='UNKNOWN',
                reason='未给出唯一适用类别；构造代码不能自动继承所有挂载类别。'))
            continue
        key = rule['scheme'], rule['id']
        clue = c.get('semantic_applicability', c.get('status', 'UNKNOWN'))
        positive = clue in ('APPLICABLE', 'PARTIAL', 'candidate') and c.get('association_basis') not in ('PROPOSED_TEST_ONLY', 'UNKNOWN')
        # Agent selected a concrete clue, but the complete original contract is
        # not independently verified here. Preserve a PARTIAL, never upgrade to
        # full applicability or historical-trigger coverage.
        status = 'PARTIAL' if positive else 'UNKNOWN'
        notes.append(dict(scheme=key[0], trigger_id=key[1],
            proposed_construction_id=c['condition_id'] if key[0] == 'V4' else None,
            reviewed_claim=c, interpretation='条件线索不等于已证致因；完整谓词仍待核，构造代码未自动建立正向关联。'))
        if key in selected:
            continue
        selected.add(key)
        checks = [dict(clause_role=role, clause=clause, result='UNKNOWN',
                       condition_fact_ids=[], evidence=[], source_cells=[])
                  for role, clause in sorted(canonical_conditions(rule))]
        labels.append(dict(scheme=key[0], definition_version=rule['definition_version'], trigger_id=key[1],
            semantic_applicability=status,
            construction_feasibility=dict(status='NOT_ASSESSED',
                reason='本轮仅完成构造设计；实际输入合同、执行器保留条件和目标路径均未设备验证。'),
            condition_fact_ids=[fact_id] if positive else [], predicate_checks=checks,
            construction_checks=[]))
        if positive:
            links.append(dict(scheme=key[0], definition_version=rule['definition_version'], trigger_id=key[1],
                detail_ids=[analysis_id], scenario_ids=[analysis_id + ':SCENARIO'],
                condition_fact_ids=[fact_id], construction_ids=[]))
    scenarios = [dict(scenario_id=analysis_id + ':SCENARIO', title='本子问题的已声明或已观察条件',
        condition_fact_ids=[fact_id], reason='仅限本子问题共同出现的事实；不从另一子问题、映射文件或测试假设继承条件。')] if links else []
    return labels, links, scenarios, notes


def raw_claims(row, aid, issue_key, evidence_ids):
    refs = [e for e in row['evidence_ids'] if e in evidence_ids and ':fault:' in e]
    if not refs:
        refs = [e for e in row['evidence_ids'] if e in evidence_ids]
    text = json.dumps(row['original_input']['fault'], ensure_ascii=False, separators=(',', ':'))
    return [dict(claim_id=aid + ':SOURCE', task_id=row['task_id'], subproblem_id=issue_key,
        statement=text, basis='SOURCE_DECLARED', evidence_ids=refs)]


def make_analysis(row, issue, rules, evidence_ids, *, public=False, code_refs=None):
    tid, key = row['task_id'], issue['issue_key']
    aid = tid + (':PUBLIC:' if public else ':WEEKLY:') + key
    if public:
        mechanism = issue['mechanism_claim']
        claims = [dict(claim_id=aid + ':SOURCE', task_id=tid, subproblem_id=key,
            statement=issue['observed_change'], basis='CAPTURED_FACT', evidence_ids=code_refs)]
        basis = 'CODE_INFERENCE'
        ds = issue['proposed_design']
        candidates = issue.get('candidate_conditions', [])
        target = ds['target_path']
        reference = ds['baseline']
        checks = ds['oracle'] if isinstance(ds['oracle'], list) else [ds['oracle']]
        gaps = ds.get('unknowns', [])
        required = ds.get('capability', [])
        required = required if isinstance(required, list) else [required]
        original = issue['original30']
        mids = original.get('similar_mode_ids', [])
        boundary = original['boundary']
        expected, actual = issue['expected_relation'], issue['observed_change']
    else:
        mechanism = issue['mechanism_summary']
        claims = raw_claims(row, aid, key, evidence_ids)
        basis = {'source_declared': 'SOURCE_DECLARED', 'logic_hypothesis': 'HYPOTHESIS',
                 'unknown': 'UNKNOWN'}.get(issue['evidence_level'], 'UNKNOWN')
        ds = issue['design']
        candidates = issue.get('suggested_conditions', [])
        target = issue['path_to_verify']
        reference = ds['reference']
        checks = ds['checks']
        gaps = ds.get('unknowns', [])
        required = ds.get('required_capability', [])
        original = issue['original30_comparison']
        mids = original.get('mode_ids', [])
        boundary = original['explanation']
        expected = issue['expected_relation']
        actual = ('来源声明：' if basis == 'SOURCE_DECLARED' else '待验证的关系解释：') + mechanism
    fid = aid + ':FACT'
    facts = [dict(fact_id=fid, statement=claims[0]['statement'], role='UNKNOWN',
                  basis='CAPTURED_FACT' if public else 'SOURCE_DECLARED',
                  source_claim_ids=[claims[0]['claim_id']])]
    labels, links, scenarios, notes = select_conditions(candidates, rules, fid, aid)
    cats = [l['trigger_id'] for l in links if l['scheme'] == 'V4']
    # Native cards can be fully scoped yet NEEDS_FACTS. A design status is not
    # a verdict on the mechanism, applicability, or device execution.
    status = ds.get('design_status', ds.get('status', 'NEEDS_FACTS'))
    if status not in ('DESIGN_READY', 'NEEDS_FACTS', 'CAPABILITY_BLOCKED'):
        status = 'NEEDS_FACTS'
    if not cats:
        status = 'NEEDS_FACTS'
        gaps = [*gaps, '没有已确认的 V4 构造类别；现为定向设计草案，不据此计入条件覆盖。']
    if not gaps and status != 'DESIGN_READY':
        gaps = ['具体合法输入、合同及路径探针尚待核验。']
    variables = []
    if public:
        for v in ds.get('variables', []):
            variables.append(dict(name=v['name'], kind='CONTEXT',
                proposed_values=[str(x) for x in v.get('proposed_values', [])], condition_fact_ids=[fid], guide_ids=[],
                reason=v['meaning'] + '；候选取值为测试提案，未当作历史触发事实。'))
    card = dict(card_id=aid + ':DESIGN', assessment_id=aid,
        scenario_id=scenarios[0]['scenario_id'] if scenarios else '', status=status,
        category_ids=cats, construction_ids=[], guide_ids=[], execution_method_ids=[],
        condition_fact_ids=[fid], variables=variables, boundaries=[], reference=reference,
        target_path=target, checks=checks or ['先恢复可比调用和参考结果，再确定数值/状态断言。'],
        required_capabilities=required,
        capability_gaps=['本工具没有设备执行器；输入实际保留、目标路径和执行结果未验收。'],
        unknowns=gaps, execution_status='NOT_RUN', path_coverage='DESIGN_ONLY', execution_implemented=False)
    return dict(analysis_id=aid, task_id=tid, subproblem_id=key,
        entity_type='INDEPENDENT_PUBLIC_TECHNICAL_CASE' if public else 'WEEKLY_SOURCE_DECLARATION',
        evidence_level=issue['evidence_level'], source_claims=claims,
        mechanism=dict(statement=mechanism, source_claim_ids=[claims[0]['claim_id']]),
        mechanism_chain=dict(expected_relation=expected, observed_change=actual,
            consumer=issue.get('consumer', target), target_path=target, oracle=checks, basis=basis),
        source_scope='捕获Diff中的具体修改；未读函数、硬件因果和周报事件身份不继承。' if public else '原始转交字段与既有摘要；不是本轮读取内部正文或复现。',
        source_read_limitations=issue.get('source_read_limitations', []),
        condition_facts=facts, selected_labels=labels, label_links=links, scenarios=scenarios,
        condition_notes=notes, design_cards=[card],
        mode_comparisons=[dict(mode_id=m, relation='UNKNOWN', reason=boundary, evidence_ids=claims[0]['evidence_ids']) for m in dict.fromkeys(mids)],
        original30_boundary=boundary,
        implementation_carrier=row.get('implementation_scope', 'UNDETERMINED'),
        mode_decision=dict(action='PENDING', reason='仅作可追溯的边界比较与归卡讨论；不自动决定新增或扩展。'),
        weekly_event_confirmed=False, formal_adoption=False, manual_accept_created=False,
        hardware_validated=False, adoption_status='SUGGESTION_ONLY')


def public_analyses(data, folder, rules):
    from rc128_mechanism_cases import mechanism_cases
    rows = {r['task_id']: r for r in data['results']}
    resources = {r['resource_id']: r for r in data['resource_audit']}
    known = {e['evidence_id'] for e in data['quotes'] + data['field_excerpts']}
    extras, analyses = [], []
    for issue in mechanism_cases():
        refs = []
        for loc in issue['locator_markers']:
            ex = r3.exact_excerpt(folder, loc['resource_id'], loc['file'], loc['marker'],
                                 index=loc.get('index', 0), context=loc.get('context', 350))
            ex['claim_scope'] = loc['claim_scope']
            if ex['evidence_id'] not in known:
                extras.append(ex)
                known.add(ex['evidence_id'])
            refs.append(ex['evidence_id'])
        a = make_analysis(rows[issue['task_id']], issue, rules, known, public=True, code_refs=list(dict.fromkeys(refs)))
        a['resource_ids'] = issue['resource_ids']
        a['code_read_scopes'] = [dict(resource_id=rid, url=resources[rid]['url'],
            diff_read_scope=resources[rid].get('diff_read_scope'),
            source_status=resources[rid].get('source_status'), merged=resources[rid].get('merged'),
            head_sha=resources[rid].get('head_sha')) for rid in issue['resource_ids']]
        analyses.append(a)
    return analyses, extras


def weekly_pilot(row, data):
    """Pilot public code cases retain their distinct original incident analysis."""
    # Read only the original fault fields here. In particular the R3 synthesized
    # cause_chain for RC-030 already mentions three unrelated public fixes; it
    # must not be recycled as three historical weekly claims.
    specifics = {
        'RC-002': ('baddbmm计算结果应满足可比输入的精度/范围约定；FP32规避不能定位内部错误。',
            'baddbmm输入、乘法中间量、beta加法及输出', ['M001', 'M009'],
            '同原30低精范围/溢出模式相似，但原事件的dtype、alpha/beta、cubeMathType和中间量未知。',
            ['同一输入分别保存乘积和最终输出，比较FP16/FP32与高精参考', '先排除latent/randn输入不一致，不能用公开精度标志补丁代替现场路径']),
        'RC-024': ('compressor各读写跨度应落在相应KV及临时区容量内；NaN现象不能单独定位哪段越界。',
            'compressor的KV生产、临时区分配与读写消费者', ['M004', 'M015', 'M026'],
            '与偏移、踩踏、切分三类均有边界相似；缺容量公式、地址及模板，不能直接归入某一类。',
            ['恢复shape、KV容量、UB需求和真实越界地址', '对照写入前后哨兵及KV有限性，排除原输入NaN']),
        'RC-029': ('静态量化V载荷应使用合同对应的scale；两个代码变量的对象/阶段不得由名字推断。',
            'FP8 Attention中V载荷、scale生产及读取', ['M010', 'M024'],
            '与反量化位置及排列对应关系相似，但本记录未说明两个scale的轴、形状与调用边。',
            ['固定同一合法V载荷，逐组赋不同scale并保存读取值', '对照BF16路线需先统一量化误差参考与实际配置']),
        'RC-030': ('合法输出维度下，dequant+swiglu+quant应满足声明的数学参考与写回跨度。',
            'npu_dequant_swiglu_quant的输入、输出维度及量化消费者', ['M004', 'M015', 'M026'],
            '原文只声明未对齐64和小算子规避，不足以在偏移、内存踩踏和切分逻辑中裁决；不能继承公开12123的两处修改为本事件根因。',
            ['恢复输出维度由哪些合法输入决定，检查64边界两侧及TP8/16实际shape', '逐阶段对照小算子结果，不把输入192当成未对齐64的直接证据']),
        'RC-031': ('固定目标调用与二进制后，多次中间结果应满足所声明的确定性要求；回答长度不等于算子确定性测量。',
            'split_qkv_rmsnorm_rope中间结果及后续生成', ['M012', 'M007'],
            '与内部确定性和同步都有可检验方向；没有依赖或调度证据，不能由非确定性直接归入缺同步。原文另称GPU评分也波动、非问题，不能合并为同一故障。',
            ['固定输入、seed、解码参数、二进制，重复比较目标算子中间量', '独立保存单请求与并发结果；明确GPU评分波动是另一条非问题观察']),
        'RC-099': ('topk_weight的数值类型应满足MoE消费者约定，不能无声破坏权重数值。',
            'topk_weight生成、类型转换与MoE加权消费', ['M030', 'M001'],
            '与类型转换丢失及混精路径相似；原记录没有源/目标dtype和真实转换路径，不能直接等同2026年公开DSV4修改。',
            ['恢复topk_weight转换前后dtype、值、归一化约定和最终加权结果', '分开类型断言、数值保持和最终MoE输出参考，不以无报错判通过']),
        'RC-122': ('优化器读取某轮梯度前，该轮最终聚合结果须已可用；bucket/rank状态须保持相应归属。',
            'Deepspeed梯度生产、最后聚合、buffer复用及优化器读取', ['M007', 'M028'],
            '原摘要有等待和multi_rank桶排查，M007是相似方向；rank重置和双流换槽两个公开补丁仍是独立技术观察，不能直接认作2025年本次修复。',
            ['记录最终聚合完成与优化器读取的事件先后，保存每轮梯度归属', '用串行归约/显式等待参考，分开False规避和实际同步因果；0.14.3不能预先标修复']),
    }
    expected, consumer, mids, boundary, checks = specifics[row['task_id']]
    return [dict(issue_key='original-claim', evidence_level='source_declared',
        mechanism_summary=row['original_input']['fault']['reported_root_cause'],
        expected_relation=expected, consumer=consumer,
        path_to_verify=consumer + '；原版本及实际调用未恢复，以下为待验证路径。', suggested_conditions=[],
        design=dict(status='NEEDS_FACTS', reference='原故障同实参的数学/串行参考，容差、配置与版本需恢复。',
            checks=checks, required_capability=['原调用和版本追溯', '对应中间量/调度与路径探针'],
            unknowns=['缺原事件合法实参、参考容差和目标实现；摘要声明尚未独立确认。', '公开PR的同事件关系未确定，测试提案不作历史触发事实。']),
        original30_comparison=dict(mode_ids=mids, decision='PENDING', explanation=boundary))]


def analyses_for(data, folder, *, pilot_only=False):
    from rc128_mechanism_remaining import review
    rules = definitions(data)
    public, extra = public_analyses(data, folder, rules)
    evidence_ids = {e['evidence_id'] for e in data['quotes'] + data['field_excerpts'] + extra}
    result = []
    corrections = []
    for row in data['results']:
        if row['task_id'] in PILOT_IDS:
            issues = weekly_pilot(row, data)
        elif pilot_only:
            continue
        else:
            entry = review(row['task_id'])
            issues = entry['issues']
            if entry.get('source_corrections'):
                corrections.append(dict(task_id=row['task_id'], corrections=entry['source_corrections']))
        for issue in issues:
            result.append(make_analysis(row, issue, rules, evidence_ids))
    return result + public, extra, rules, corrections


def analysis_errors(analyses, rules, evidence_ids):
    errors = []
    for a in analyses:
        for e in validate_analysis(a, rules, evidence_ids):
            errors.append(dict(analysis_id=a['analysis_id'], **e))
    return errors


def pilot(folder, source=SOURCE):
    folder = r3.independent_output(folder, source)
    r3.archive_verify(Path(source))
    data = r3.payload(Path(source))
    # Locators read captured files in the source; no new website requests.
    analyses, extra, rules, _ = analyses_for(data, Path(source), pilot_only=True)
    known = {e['evidence_id'] for e in data['quotes'] + data['field_excerpts'] + extra}
    errors = analysis_errors(analyses, rules, known)
    budgets = budget_receipts(Path(source), data, analyses, extra)
    selected_budgets = [r for r in budgets['receipts'] if r['case_id'] in PILOT_IDS]
    errors.extend(dict(analysis_id=r['task_id'], code='INPUT_TOO_LARGE', path='serialized_input',
                       message=str(r['serialized_input_chars'])) for r in selected_budgets if r['status'] == 'BLOCKED')
    record = dict(status='FAIL' if errors else 'PASS', case_ids=PILOT_IDS, analyses=len(analyses),
        code_analyses=sum(a['entity_type'] == 'INDEPENDENT_PUBLIC_TECHNICAL_CASE' for a in analyses),
        policy_fingerprint=fingerprint(), source_manifest_sha256=core.sha(Path(source) / 'manifest.json'),
        errors=errors, admission=False, hardware_execution=False,
        whole_request_budget_receipts=selected_budgets,
        note='代表案例合同、精确选段、输入/代码/事件分离验收；不是设备或根因因果复现。')
    folder.mkdir(parents=True, exist_ok=True)
    core.jsonl(folder / 'pilot_analyses.jsonl', analyses)
    core.write(folder / 'pilot_validation.json', record)
    return record


def budget_receipts(folder, data, analyses, extra):
    original = {r['task_id']: r['original_input'] for r in data['results']}
    excerpts = {e['evidence_id']: e for e in data['field_excerpts'] + extra + data['quotes']}
    contexts, inputs = {}, []
    for a in analyses:
        aid = a['analysis_id']
        ids = {eid for c in a['source_claims'] for eid in c['evidence_ids']}
        inputs.append(dict(task_id=aid, case_id=a['task_id'], original_record=original[a['task_id']]))
        contexts[aid] = dict(analysis_scope=a['source_scope'], entity_type=a['entity_type'],
            subproblem_id=a['subproblem_id'], source_claims=a['source_claims'],
            instruction='仅分析本子问题：定位应有与实际关系；原42/V4独立稀疏判断并逐项核对Requires/Skip。设计输入、目标路径探针、独立参考、判据和能力缺口。测试提案不作为已观察条件。',
            selected_exact_evidence=[excerpts[eid] for eid in sorted(ids)],
            evidence_scope='本任务原始转交字段完整；公开代码仅含注明范围的精确选段，不声称完整PR/内网正文核验。')
    result = core.input_budget_receipts(inputs, data['baseline'], data['definitions'], folder,
                                      review_context=contexts, input_budget=BUDGET)
    cases = {a['analysis_id']: a['task_id'] for a in analyses}
    for receipt in result['receipts']:
        receipt['case_id'] = cases[receipt['task_id']]
    result['work_unit'] = 'ONE_EXPLICIT_SUBPROBLEM; NO_CROSS_ISSUE_AGGREGATION_OR_TRUNCATION'
    return result


def build(folder, source=SOURCE):
    folder = r3.independent_output(folder, source)
    source = Path(source).resolve()
    r3.archive_verify(source)
    receipt = core.read(folder / 'pilot_validation.json')
    if receipt['status'] != 'PASS' or receipt['policy_fingerprint'] != fingerprint() or receipt['source_manifest_sha256'] != core.sha(source / 'manifest.json'):
        raise ValueError('Pilot must pass under the same source, definitions, input budget and implementation before batch build.')
    if (folder / 'manifest.json').exists():
        raise ValueError('A published output archive is immutable. Use a new independent output directory.')
    source_hashes = r2.file_hashes(source)
    # Only the immutable evidence/input trees are reused. Old conclusions remain
    # in an explicitly named history directory, never current result files.
    for name in ['sources', 'evidence', 'receipts', 'collection']:
        if (source / name).exists():
            shutil.copytree(source / name, folder / name, dirs_exist_ok=True)
    history = folder / 'history/r3'
    for rel in ['manifest.json', 'validation.json', 'summary.json', 'review_policy.json', 'results.jsonl',
                'failure_relations.jsonl', 'condition_relations.jsonl', 'mode_comparison.jsonl', 'field_audits.jsonl',
                'driving_quantities.jsonl']:
        target = history / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / rel, target)
    for name in ['input_manifest.json', 'condition_definitions.json', 'baseline_30_index.json']:
        shutil.copyfile(source / name, folder / name)
    data = r3.payload(source)
    analyses, extras, rules, corrections = analyses_for(data, folder)
    known = {e['evidence_id'] for e in data['quotes'] + data['field_excerpts'] + extras}
    errors = analysis_errors(analyses, rules, known)
    if errors:
        core.write(folder / 'build_errors.json', errors)
        raise ValueError(f'{len(errors)} mechanism/design contract failures; see build_errors.json')
    budgets = budget_receipts(folder, data, analyses, extras)
    blocked = {r['case_id'] for r in budgets['receipts'] if r['status'] == 'BLOCKED'}
    results = deepcopy(data['results'])
    for row in results:
        aa = [a for a in analyses if a['task_id'] == row['task_id']]
        row['analysis_ids'] = [a['analysis_id'] for a in aa]
        row['review_policy'] = VERSION
        row['mechanism_processing'] = dict(status='BLOCKED' if row['task_id'] in blocked else 'ANALYSIS_ATTEMPT_COMPLETED',
            reason='INPUT_TOO_LARGE' if row['task_id'] in blocked else None,
            review_scope='PILOT_CODE_CASE_PLUS_DISTINCT_WEEKLY_DECLARATION' if row['task_id'] in PILOT_IDS else 'AGENT_REVIEW_OF_CAPTURED_INPUT_AND_SCOPED_EVIDENCE',
            native_design_statuses=[c['status'] for a in aa for c in a['design_cards']],
            full_semantic_root_confirmation=False)
        row['historical_unresolved_gaps'] = row.pop('unresolved_gaps', [])
        row['historical_mode_comparisons'] = [m for m in data['comparisons'] if m.get('task_id') == row['task_id']]
        row['current_design_gaps'] = list(dict.fromkeys(g for a in aa for c in a['design_cards'] for g in c['unknowns']))
        row['historical_analysis_notice'] = 'root_cause/failure_relation_ids及旧分类字段为R3历史；本轮当前分析以analysis_ids为准，不能混作新版证实结果。'
    cards = [dict(task_id=a['task_id'], entity_type=a['entity_type'], **c) for a in analyses for c in a['design_cards']]
    conditions = [dict(task_id=a['task_id'], analysis_id=a['analysis_id'], entity_type=a['entity_type'],
        **s, counts_as_confirmed_historical_trigger=False) for a in analyses for s in a['selected_labels']]
    comparisons = [dict(task_id=a['task_id'], analysis_id=a['analysis_id'], entity_type=a['entity_type'],
        mode_decision=a['mode_decision'], **m) for a in analyses for m in a['mode_comparisons']]
    summary = dict(policy_version=VERSION, records=len(results), unique_case_ids=len({r['task_id'] for r in results}),
        mechanism_analyses=len(analyses), weekly_subproblems=sum(a['entity_type'] == 'WEEKLY_SOURCE_DECLARATION' for a in analyses),
        independent_public_subproblems=sum(a['entity_type'] == 'INDEPENDENT_PUBLIC_TECHNICAL_CASE' for a in analyses),
        design_cards=len(cards), design_statuses=dict(Counter(c['status'] for c in cards)),
        selected_rule_assessments=len(conditions), partial_rule_assessments=sum(c['semantic_applicability'] == 'PARTIAL' for c in conditions),
        fully_applicable_rules=sum(c['semantic_applicability'] == 'APPLICABLE' for c in conditions),
        confirmed_55_construction_links=0, confirmed_historical_trigger_coverage=0,
        input_blocked_case_ids=sorted(blocked), pilot_case_ids=PILOT_IDS,
        searches_reused=len(data['search_audit']), resources_reused=len(data['resource_audit']), new_searches=0,
        manual_accept_created=0, formal_adoption=0, device_runs=0,
        note='案例数、子问题数、标签数分别统计。PARTIAL为具体条件线索，不是完整适用、因果触发或55构造覆盖。')
    outdata = dict(summary=summary, results=results, analyses=analyses, definitions=rules,
        quotes=data['quotes'], excerpts=data['field_excerpts'] + extras, resources=data['resource_audit'],
        searches=data['search_audit'], baseline30=data['baseline'], evidence_relations=data['evidence_relations'],
        public_findings=data['public_findings'],
        corrections=corrections)
    for name, values in [('results', results), ('mechanism_analyses', analyses), ('design_cards', cards),
                         ('condition_relations', conditions), ('mode_comparison', comparisons),
                         ('public_findings', data['public_findings']), ('resource_audit', data['resource_audit']),
                         ('search_audit', data['search_audit']), ('evidence_relations', data['evidence_relations'])]:
        core.jsonl(folder / (name + '.jsonl'), values)
    for name, value in [('summary', summary), ('classification_rules', rules), ('evidence_index', outdata['quotes'] + outdata['excerpts']),
                        ('source_corrections', corrections), ('input_budget', budgets), ('review_policy', policy())]:
        core.write(folder / (name + '.json'), value)
    core.write(folder / 'source_revision.json', dict(source_bundle=source.relative_to(core.REPO).as_posix(),
        source_manifest_sha256=core.sha(source / 'manifest.json'), source_policy=r3.VERSION,
        original_input_sha256=core.sha(source / 'sources/original/handoff.jsonl'),
        source_file_sha256=source_hashes, original42_and_v4_unchanged=True))
    core.write(folder / 'evidence_sha256_manifest.json', dict(files={p: h for p, h in r2.file_hashes(folder).items()
        if p.startswith(('sources/', 'evidence/', 'receipts/', 'collection/'))},
        scope='本包复用R3已取得原始材料；快照完整性和选段语义审读范围分开。'))
    core.write(folder / 'historical_gap_review.json', dict(policy=VERSION,
        rule='旧缺口保持历史身份；新版current_design_gaps按原事件/公开技术观察分别填写。',
        corrections=[
            dict(task_id='RC-010', issue='279已取得Diff，但ISA位定义、设备上下文和复位范围仍未知。旧未读声明不作为当前采集状态。'),
            dict(task_id='RC-029', issue='新PR快照不替代旧归档commit；参数替换可查，不继承前块/当前块推断。'),
            dict(task_id='RC-099', issue='公开PR可见.to类型转换；原周报事件是否采用该路径仍未知，两个替代PR不能当成均已合入。')]))
    from rc128_mechanism_html import render
    render(folder, outdata)
    (folder / '.gitattributes').write_text('* -text\n', encoding='ascii')
    (folder / 'README.md').write_text(readme(folder, summary), encoding='utf-8')
    make_manifest(folder)
    return verify(folder)


def make_manifest(folder):
    core.write(folder / 'manifest.json', dict(schema_version='RC128-BUNDLE-4', policy_fingerprint=fingerprint(),
        policy_version=VERSION, analysis_code_sha256=code_hashes(),
        payload_sha256={p: h for p, h in r2.file_hashes(folder).items() if p not in EXCLUDED}))


def verify(folder, git_index=False):
    folder = Path(folder)
    m = core.read(folder / 'manifest.json')
    data = r3.payload(folder)
    known = {e['evidence_id'] for e in data['quotes'] + data['excerpts']}
    checks = []
    def check(name, ok):
        checks.append(dict(name=name, passed=bool(ok)))
    check('128_unique_original_records', len(data['results']) == 128 and len({r['task_id'] for r in data['results']}) == 128)
    raw = core.rows(folder / 'sources/original/handoff.jsonl')
    check('each_original_input_identical', {r['task_id']: r['original_input'] for r in data['results']} == {r['task_id']: r for r in raw})
    check('every_case_has_current_analysis', {a['task_id'] for a in data['analyses']} == {r['task_id'] for r in raw})
    check('all_native_sparse_and_design_contracts', not analysis_errors(data['analyses'], data['definitions'], known))
    check('all_claims_exact_evidence_exists', r2.anchors_valid(folder, data['quotes']))
    check('all_code_excerpts_exact', all(core.sha(folder / e['file']) == e['sha256'] and
        (folder / e['file']).read_bytes().decode('utf-8')[e['char_start']:e['char_end']] == e['quote'] for e in data['excerpts']))
    check('all_mode_decisions_pending', all(a['mode_decision']['action'] == 'PENDING' for a in data['analyses']))
    check('no_admission_accept_or_device_execution', all(not a[k] for a in data['analyses'] for k in ['formal_adoption', 'manual_accept_created', 'hardware_validated', 'weekly_event_confirmed']))
    check('all_cards_not_executed', all(c['execution_status'] == 'NOT_RUN' and not c['execution_implemented'] for a in data['analyses'] for c in a['design_cards']))
    check('frozen42_and_v4_separate', sum(d['scheme'] == 'ORIGINAL42' for d in data['definitions']) == 42 and sum(d['scheme'] == 'V4' for d in data['definitions']) == 31)
    check('55_unique_constructions_retained', len({c['id'] for d in data['definitions'] if d['scheme'] == 'V4' for c in d['constructions']}) == 55)
    for name, key in [('results', 'results'), ('mechanism_analyses', 'analyses')]:
        check(name + '_html_json_identical', core.rows(folder / (name + '.jsonl')) == data[key])
    check('summary_html_json_identical', core.read(folder / 'summary.json') == data['summary'])
    check('all_immutable_evidence_sha', all(core.sha(folder / p) == h for p, h in core.read(folder / 'evidence_sha256_manifest.json')['files'].items()))
    check('manifest_complete_and_hashes_match', set(r2.file_hashes(folder)) - EXCLUDED == set(m['payload_sha256']) and all(core.sha(folder / p) == h for p, h in m['payload_sha256'].items()))
    historical=folder.resolve().is_relative_to((core.REPO/'reports/archive').resolve())
    if historical:
        old_code=core.historical_code_hashes(m['analysis_code_sha256'])
        old_fp=digest(dict(code=old_code,policy=core.read(folder/'review_policy.json')))
        check('historical_code_policy_budget_fingerprint',m['policy_fingerprint']==old_fp and m['analysis_code_sha256']==old_code)
    else:
        check('current_code_policy_budget_fingerprint', m['policy_fingerprint'] == fingerprint() and m['analysis_code_sha256'] == code_hashes())
    p = core.read(folder / 'pilot_validation.json')
    check('pilot_passed_before_batch_same_policy', p['status'] == 'PASS' and p['policy_fingerprint'] == m['policy_fingerprint'])
    budget = core.read(folder / 'input_budget.json')
    check('whole_input_budget_160000_no_truncation', len(budget['receipts']) == len(data['analyses']) and not budget['automatic_truncation'] and all(r['budget_chars'] == BUDGET for r in budget['receipts']))
    blocked_cases = {r['case_id'] for r in budget['receipts'] if r['status'] == 'BLOCKED'}
    check('blocked_input_never_success', all(x['mechanism_processing']['status'] == ('BLOCKED' if x['task_id'] in blocked_cases else 'ANALYSIS_ATTEMPT_COMPLETED') for x in data['results']))
    src = core.read(folder / 'source_revision.json')
    source = core.resolve_historical_path(src['source_bundle'])
    check('entire_source_archive_unchanged', r2.file_hashes(source) == src['source_file_sha256'])
    check('source_historical_validation_not_rewritten', core.sha(folder / 'history/r3/validation.json') == src['source_file_sha256']['validation.json'])
    if git_index:
        check('all_staged_payload_bytes_match', all(r3.index_sha(folder / p) == h for p, h in m['payload_sha256'].items()))
    errors = [c['name'] for c in checks if not c['passed']]
    return dict(status='FAIL' if errors else 'PASS', checks=checks, errors=errors, check_count=len(checks),
        policy_fingerprint=m['policy_fingerprint'], records=128, read_only=True,
        device_validation=False, root_cause_confirmation=False,
        policy_status='HISTORICAL_POLICY_NOT_CURRENT_REVIEW'if historical else'CURRENT_POLICY')


def readme(folder, s):
    rel = (folder.relative_to(core.REPO) if folder.is_relative_to(core.REPO) else folder).as_posix()
    return f'''# 128条失效机理、稀疏条件及测试设计

主要入口：[完整离线HTML](report.html)。本包复用R3检索、正文、Diff和SHA，不声称重新搜索或设备复现。

{s['records']}条记录，{s['weekly_subproblems']}个原记录子问题，{s['independent_public_subproblems']}个独立公开代码子问题。
代表案例为 {', '.join(PILOT_IDS)}，先经过同策略pilot，再展开128条。原始输入与旧归档未改写。

当前分析：`mechanism_analyses.jsonl`；原记录：`results.jsonl`；原生卡：`design_cards.jsonl`；稀疏类别：`condition_relations.jsonl`；原30比较：`mode_comparison.jsonl`。
`history/r3/`为旧策略材料，不作为本轮重新确认；`source_corrections.json`保留本轮原文字段纠偏。

原42、V4类及55构造分别保留。具体构造提案见condition_notes；完整Requires/Skip未核清时类别保持PARTIAL或UNKNOWN，不把测试提案当成历史触发事实。
DESIGN_READY只指可继续实现的离线设计，不代表执行器已实现、路径已命中或设备通过。NEEDS_FACTS同样保留具体路径、判据及缺口。
所有归卡仍PENDING，无自动ACCEPT、正式入库、Baseline冻结或设备执行。内部Wiki/DTS仍为转交摘要。

复现（仓库根目录，Python3.12+及requirements）：
```
python scripts/rc128_mechanism_review.py pilot NEW_DIR --source-bundle reports/archive/rc128-evidence-review-20261112-r3
python scripts/rc128_mechanism_review.py build NEW_DIR --source-bundle reports/archive/rc128-evidence-review-20261112-r3
python scripts/rc128_mechanism_review.py verify {rel}
python scripts/rc128_mechanism_review.py verify {rel} --git-index
python scripts/rc128_mechanism_review.py package {rel}
```
build拒绝已有manifest的输出目录；不操作现场run/state。预算160000检查包含指令、序列化输入、原30、两库全文及选段，超限标记BLOCKED，不截断。预算检查不证明Agent会话未发生上下文截断。
历史材料按旧manifest保留；代码升级只能新建归档，旧validation不重写。
'''


def package(folder):
    folder = Path(folder)
    validation = verify(folder)
    if validation['status'] != 'PASS':
        raise ValueError('Cannot package an invalid or stale archive: ' + ', '.join(validation['errors']))
    path = folder.with_suffix('.zip')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():
                z.write(p, p.relative_to(folder).as_posix())
    return dict(file=str(path), sha256=core.sha(path), files=len(r2.file_hashes(folder)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('command', choices=['pilot', 'build', 'verify', 'package'])
    ap.add_argument('output', type=Path)
    ap.add_argument('--source-bundle', type=Path, default=SOURCE)
    ap.add_argument('--git-index', action='store_true')
    args = ap.parse_args()
    if args.command == 'pilot':
        result = pilot(args.output, args.source_bundle)
    elif args.command == 'build':
        result = build(args.output, args.source_bundle)
        core.write(args.output / 'validation.json', result)
    elif args.command == 'verify':
        result = verify(args.output, args.git_index)
    else:
        result = package(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get('status') == 'FAIL':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
