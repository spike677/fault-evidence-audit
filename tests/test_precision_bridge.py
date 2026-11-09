"""Synthetic Bridge acceptance; no real customer input, site, model or device."""
import copy
import io
import json
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path
import unittest
from unittest.mock import patch

from faultaudit import precision_bridge as bridge, precision_target as target, precision_gate as gate
from faultaudit import trigger_workflow as workflow, xlsx_workflow as files
from faultaudit.precision_contracts import BindingDraft
from faultaudit.store import AuditError, Store, digest
from faultaudit.trigger_sparse import CONTRACT, frame_version
from faultaudit.trigger_v4 import canonical_conditions
from tests import test_cann_baseline as baseline_helpers
from tests.v4_fixtures import v4_unknown


# These fixture executables model native checker transport/exit semantics only.
# They do not implement an operator, emulate ATK, or establish real coverage.
CHECKER = r'''import argparse,copy,json,sys
from pathlib import Path
kind = KIND
p=argparse.ArgumentParser()
if kind!='schema': p.add_argument('command')
p.add_argument('--task-dir',type=Path,required=True)
if kind=='prepare': p.add_argument('--output',type=Path,required=True)
a=p.parse_args();w=a.task_dir
suite=json.loads((w/'01_generate/submission/test_suite.json').read_text(encoding='utf-8'))
cfg=json.loads((w/'02_atk_run/atk_run_config.json').read_text(encoding='utf-8'))
flags=json.loads((w/'synthetic_checker_flags.json').read_text()) if (w/'synthetic_checker_flags.json').exists() else {}
if flags.get('fail'): print('FAIL: synthetic checker failure');sys.exit(7)
if len(suite)!=cfg['max_cases']:
    print('WARNING: '+(f"rule count {len(suite)} is not a complete count [{cfg['max_cases']}]" if kind=='schema' else f"submission count {len(suite)} is not an allowed complete count: [{cfg['max_cases']}]") )
missing=[r['id'] for r in suite if not any(s.startswith('TRIGGER-') for s in r['trigger_library_ref'])]
if missing: print('WARNING: suite cases missing a primary trigger budget entry: '+', '.join(map(str,missing)))
for warning in flags.get('warnings',[]): print('WARNING: '+warning)
if kind=='prepare':
    out=copy.deepcopy(suite)
    for r in out:r.update(cfg['atk_config']['case_template'])
    a.output.write_text(json.dumps(out),encoding='utf-8')
    print('ATK-ready JSON saved to: '+str(a.output))
else:print('PASS: synthetic core format only')
'''


class PrecisionBridgeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = baseline_helpers.BaselineBuilderTests()
        self.fixture.setUp()
        self.addCleanup(self.cleanup_fixture)
        self.bridge_budget = patch.dict('os.environ', {'FAULTAUDIT_MAX_INPUT_CHARS':'1000000'})
        self.bridge_budget.start(); self.addCleanup(self.bridge_budget.stop)
        self.root, self.store = self.fixture.root, self.fixture.store
        self._baseline()
        self.repo = self.root / 'pt'
        self.slug = 'ops-synthetic'
        self.task = self.repo / 'tasks' / self.slug
        for p in ('01_generate/src', '01_generate/interfaces', '01_generate/submission', '02_atk_run/atk_runnable', '03_report'):
            (self.task / p).mkdir(parents=True, exist_ok=True)
        (self.repo / 'docs').mkdir(); (self.repo / 'scripts').mkdir(); (self.repo / 'prompts').mkdir()
        shutil.copy2(self.fixture.taxonomy, self.repo / 'docs/trigger_library.md')
        (self.repo / 'prompts' / (self.slug + '.md')).write_text('Synthetic blind task; no real operator.', encoding='utf-8')
        self.source_text = '// Synthetic only.\n// Legal API domain: self fp32 dimensions are nonnegative.\n// E1 repeat; E2 predecessors; E3 prefill; E4 interference; E5 ranks.\n'
        (self.task / '01_generate/src/kernel.cpp').write_text(self.source_text, encoding='utf-8')
        (self.task / '01_generate/interfaces/operator_doc.md').write_text(self.source_text, encoding='utf-8')
        (self.task / '02_atk_run/atk_runnable/executor.py').write_text('# synthetic, not executed\n', encoding='utf-8')
        (self.task / '01_generate/submission/test_suite.template.json').write_text('[]', encoding='utf-8')
        config = {'slug': self.slug, 'max_cases': 2, 'container': {'image': 'synthetic:not-a-device'},
            'atk_config': {'target_aclnn_name': 'aclnnSynthetic', 'case_template': {
                'name': 'Synthetic', 'api_type': 'execute_synthetic', 'aclnn_api_type': 'execute_aclnnSynthetic', 'standard': {'acc': 'single_bm'}}}}
        self.write(self.task / '02_atk_run/atk_run_config.json', config)
        self.committed = {}
        for name, kind in zip(target.CHECKERS, ('schema', 'coverage', 'prepare')):
            (self.repo / name).write_text(CHECKER.replace('KIND', repr(kind)), encoding='utf-8')
            self.committed[name] = (self.repo / name).read_bytes()
        self.remote = target.REPOSITORY; self.head = target.AUDITED_COMMIT
        self.git_patch = patch('faultaudit.precision_target._git', side_effect=self.fake_git)
        self.git_patch.start(); self.addCleanup(self.git_patch.stop)
        self.real_output = subprocess.check_output
        self.output_patch = patch('faultaudit.precision_target.subprocess.check_output', side_effect=self.fake_output)
        self.output_patch.start(); self.addCleanup(self.output_patch.stop)
        self.workspace = self.root / 'ws'
        shutil.copytree(self.task, self.workspace)
        report = self.workspace / '01_generate/report'; report.mkdir()
        shutil.copy2(self.repo / 'docs/trigger_library.md', report / 'trigger_library.md')
        self.write(report / 'trigger_coverage.json', {'synthetic_only': True})
        self.suite = self.workspace / '01_generate/submission/test_suite.json'
        self.rules = [{'id': i, 'generate_intent': 'Synthetic shape input design, not a real fault',
            'trigger_library_ref': ['TRIGGER-1.2.4: synthetic shape condition'],
            'inputs': [{'name': 'self', 'type': 'tensor', 'dtype': 'fp32', 'shape': [65+i], 'range_values': [0,1]}]}
            for i in range(2)]
        self.write(self.suite, self.rules)
        self.context_path = self.root / 'context.json'
        bridge.export_context(self.store, self.run, self.repo, self.slug, self.context_path)
        self.context = target.read_json(self.context_path)
        self.mode = self.context['modes'][0]

    def cleanup_fixture(self):
        self.fixture.tearDown()
        self.fixture.doCleanups()

    def fake_git(self, repo, *args):
        if args == ('remote','get-url','origin'): return self.remote
        if args == ('rev-parse','HEAD'): return self.head
        if args[0] == 'status': return ''
        raise AssertionError(args)

    def fake_output(self, command, **kwargs):
        if command[:1] == ['git'] and 'show' in command:
            return self.committed[command[-1].removeprefix('HEAD:')]
        return self.real_output(command, **kwargs)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def _baseline(self, *, non_api=False):
        f = self.fixture
        f.start(2, cause='合成维长65尾块步长错误；重复/前序状态/输出预填/线程干扰/多rank执行条件')
        f.advance()
        for task in files.next_tasks(self.store, f.run)['tasks']:
            request=f.request(task);p=request['payload'];r=f.response(request)
            if task['kind']=='baseline_execution':
                r['execution_method_links']=[{'method_id': 'E'+str(i),'reason':'合成执行方法建议','condition_fact_ids':['F']} for i in range(1,6)]
            else:
                cell=r['condition_facts'][0]['source_cells'][0]
                if task['kind']=='baseline_api42' and non_api:
                    r['classification_summary']={'status':'NOT_APPLICABLE','reason':'明确执行条件独立于API输入轴','exclusion_fact_ids':['F']}
                else:
                    r['condition_facts'][0]['role']='INPUT_SHAPE'
                    scheme='V4' if task['kind']=='baseline_v4' else 'ORIGINAL42'
                    key='S5' if scheme=='V4' else '1.2.4'
                    if scheme=='V4':
                        row=next(v for v in v4_unknown(p,r)['v4_rows'] if v['trigger_id']==key)
                        child=row['construction_checks'][0]
                        child.update(applicability='PARTIAL',condition_fact_ids=['F'],source_cells=[cell],
                            reason='合成边界构造',construction_recipe='维长边界两侧的合法输入；实际粒度待补')
                        row['construction_checks']=[child];r['v4_rows']=[row]
                    else:
                        item=next(i for i in p['taxonomy']['items'] if i['id']==key)
                        family=next(v for v in p['taxonomy']['families'] if v['family_id']==item['family_id'])
                        row={'trigger_id':key,'predicate_checks':[{'clause_role':role,'clause':text,'result':'UNKNOWN'} for role,text in sorted(canonical_conditions(item,family))]}
                        r['rows']=[row]
                    row.update(applicability='PARTIAL',relation='UNKNOWN',evidence_basis='SOURCE_DEFINITION',condition_fact_ids=['F'],source_cells=[cell],reason='按合成原文整理')
                    r['classification_summary']={'status':'CLASSIFIED','reason':'合成条件已有说明','unknowns':['底层粒度']}
                    r['scenarios']=[{'scenario_id':'s','title':'合成输入','condition_fact_ids':['F'],'reason':'同一来源'}]
                    r['label_links']=[{'scheme':scheme,'trigger_id':key,'definition_version':frame_version(p,scheme),
                        'detail_ids':['D'],'scenario_ids':['s'],'condition_fact_ids':['F'],
                        'construction_ids':[child['construction_id']] if scheme=='V4' else []}]
            f.submit(task,r)
        task=files.next_tasks(self.store,f.run)['tasks'][0]
        review=f.response(f.request(task));review['recommendation']='READY'
        for c in review['comparison_checks']:c.update(status='REVIEWED',reason='合成协议验收已检查此维度，不声明真实故障成立')
        f.submit(task,review);files.next_tasks(self.store,f.run)
        self.run=f.run
        self.frozen=workflow.finalize(self.store,self.run)
        self.assertEqual(self.frozen['status'],'READY')

    def citation(self):
        return {'path':'01_generate/src/kernel.cpp','line':2,'quote':self.source_text.splitlines(keepends=True)[1]}

    def draft(self, context=None):
        context=context or self.context
        request=bridge.draft_request(context,self.suite)
        from tests.test_trigger_assessment import fixture
        _,template=fixture()
        rules=bridge.native_rules(self.suite)
        out={'request_hash':request['request_hash'],'context_hash':context['context_hash'], 'suite_sha256':target.file_hash(self.suite),
            'purpose':context['purpose'],'producer':template['producer'],'self_check':template['self_check'],'rules':[]}
        for case_id,rule in rules.items():
            known=context['purpose']=='KNOWN_PATTERN_VALIDATION'
            mode=context['modes'][0] if known else None
            proof_keys=[k for k,v in context['condition_links'].items() if known and v['mode_id']==mode['mode_id']]
            link={'mode_id':mode['mode_id'],'evidence_keys':['A1:F'],'condition_link_keys':proof_keys,
                'api_trigger_ids':['1.2.4'],'v4_class_ids':['S5'],'v4_scenario_ids':mode['v4_scenario_ids'],
                'execution_method_ids':[],'reason':'合成逐规则溯源'} if known else None
            out['rules'].append({'case_id':case_id,'inputs_sha256':digest(rule['inputs']), 'mode_links':[link] if known else [],
                'api_trigger_ids':['1.2.4'],'code_ids':[],'code_justifications':[],'protocols':[],
                'semantic_review':{'status':'CHECKED','reason':'合成合法域检查，不是机理证明','source_evidence':[self.citation()]}})
        return out

    def participant(self, name, case_id, role, owner='target'):
        return {'call_id':name,'case_id':case_id,'role':role,'context':'synthetic-context-'+name,
            'stream':'stream-'+name,'executor':'execute_aclnnSynthetic','output_owner':owner}

    def protocol(self, method):
        participants=[self.participant('target',0,'TARGET'),self.participant('serial',0,'CONTROL')]
        if method=='E2': participants += [self.participant('P',1,'PREDECESSOR'),self.participant('Q',1,'PREDECESSOR')]
        if method=='E4': participants += [self.participant('interferer',1,'INTERFERER','other'),self.participant('other-serial',1,'CONTROL','other')]
        if method=='E5': participants += [self.participant('rank0',0,'RANK','rank0'),self.participant('rank1',1,'RANK','rank1')]
        return {'method_id':method,'target_case_id':0,'target_call_id':'target','same_target_arguments_required':True,
            'same_target_binary_required':True,'participants':participants,'steps':['Compare each owned output to its serial reference'],
            'oracle':'Exact target/control comparison; no actual device execution','repeats':2,
            'reset_policy':'Reset before each independent control trial','output_prefill':'Prefill the declared output buffer before target T',
            'participation_config':'Two ranks, fixed participation and roles'}

    def code_case(self, draft, *, method='E3', kind='EXECUTION_METHOD'):
        self.rules[0]['trigger_library_ref']=['CODE-state-only: synthetic non-API test condition']
        self.write(self.suite,self.rules)
        draft=self.draft()
        b=draft['rules'][0]
        b['api_trigger_ids']=[];b['code_ids']=['state-only']
        b['code_justifications']=[{'code_id':'state-only','kind':kind,'reason':'明确非API条件','source_evidence':[self.citation()]}]
        b['mode_links'][0].update(api_trigger_ids=[],v4_class_ids=[],v4_scenario_ids=[],condition_link_keys=[],execution_method_ids=[method] if method else [])
        b['protocols']=[self.protocol(method)] if method else []
        return draft

    def bind_and_check(self, draft=None, *, context=None, diagnostic=False, materialized=True):
        context=context or self.context;draft=draft or self.draft(context)
        bound_path=self.root/('bindings-'+digest(draft)[:12]+'.json')
        bridge.bind(self.store if context['baseline'] else None,context,self.suite,draft,bound_path)
        atk=self.root/'atk.json'
        config=target.read_json(self.task/'02_atk_run/atk_run_config.json')
        data=copy.deepcopy(target.read_json(self.suite))
        for row in data:row.update(config['atk_config']['case_template'])
        self.write(atk,data)
        return gate.check(self.store if context['baseline'] else None,context,target.read_json(bound_path),self.workspace,
            suite=self.suite,atk_suite=atk if materialized else None,diagnostic=diagnostic)

    def test_export_current_baseline_is_read_only_and_keeps_axes_and_versions(self):
        before=self.store.conn.total_changes
        second=self.root/'second.json'
        bridge.export_context(self.store,self.run,self.repo,self.slug,second)
        self.assertEqual(target.read_json(second),self.context)
        self.assertEqual(self.store.conn.total_changes,before)
        self.assertEqual(len(self.context['modes']),2)
        self.assertEqual(self.context['api42']['scheme'],'ORIGINAL42')
        self.assertEqual((len(self.context['v4']['items']),len(self.context['v4']['constructions']),len(self.context['v4']['guides'])),(31,55,195))
        self.assertEqual(self.context['modes'][0]['v4_class_ids'],['S5'])
        self.assertNotIn('S5',self.context['modes'][0]['v4_scenario_ids'])
        self.assertFalse(self.context['modes'][0]['validation_status']['HARDWARE_VALIDATED'])

    def test_selected_export_declares_omissions_instead_of_silent_library_reduction(self):
        path=self.root/'one.json'
        bridge.export_context(self.store,self.run,self.repo,self.slug,path,mode_ids=[self.mode['mode_id']])
        value=target.read_json(path)
        self.assertEqual(len(value['modes']),1)
        self.assertEqual(value['input_scope']['full_baseline_mode_count'],2)
        self.assertEqual(len(value['input_scope']['omitted_modes']),1)
        with self.assertRaises(AuditError):bridge.export_context(self.store,self.run,self.repo,self.slug,path,mode_ids=['absent'])

    def test_unfrozen_provisional_and_stale_baselines_are_rejected_without_history_deletion(self):
        old=copy.deepcopy(self.frozen)
        self.store.put(self.run,'trigger_baseline_heads','current',{'baseline_id':'missing'},mutable=True)
        with self.assertRaises(AuditError):bridge.export_context(self.store,self.run,self.repo,self.slug,self.root/'fail.json')
        self.store.put(self.run,'trigger_baseline_heads','current',{'baseline_id':old['baseline_id']},mutable=True)
        self.store.put(self.run,'trigger_baselines',old['baseline_id'],{**old,'status':'READY_WITH_GAPS'},mutable=True)
        with self.assertRaisesRegex(AuditError,'gaps'):bridge.export_context(self.store,self.run,self.repo,self.slug,self.root/'fail.json')
        self.store.put(self.run,'trigger_baselines',old['baseline_id'],old,mutable=True)
        case=self.store.records(self.run,'cases')[0];case={**case,'raw':{**case['raw'],'new':'changed'}}
        self.store.put(self.run,'cases',case['case_id'],case,mutable=True)
        with self.assertRaisesRegex(AuditError,'stale'):bridge.current_context(self.context,self.store)
        self.assertEqual(self.store.get(self.run,'trigger_baselines',old['baseline_id']),old)

    def test_normal_binding_and_formal_json_gate_create_no_device_or_review_result(self):
        before=self.store.conn.total_changes
        report=self.bind_and_check()
        self.assertEqual(report['status'],'DESIGN_READY')
        self.assertTrue(report['formal_suite_ready'])
        self.assertEqual(report['native_suite_status'],'FORMAL_READY')
        self.assertFalse(report['hardware_validated'])
        self.assertFalse(report['human_accept_created'])
        self.assertEqual(self.store.conn.total_changes,before)
        self.assertEqual(self.store.records(self.run,'reviews'),[])

    def test_identity_case_coverage_input_and_source_forgery_are_rejected(self):
        good=self.draft()
        mutations=[lambda r:r.update(request_hash='a'*64),lambda r:r.update(context_hash='b'*64),
            lambda r:r['rules'].pop(),lambda r:r['rules'].append(copy.deepcopy(r['rules'][0])),
            lambda r:r['rules'][0].update(inputs_sha256='c'*64),
            lambda r:r['rules'][0]['mode_links'][0].update(evidence_keys=['another-mode:F']),
            lambda r:r['rules'][0]['semantic_review']['source_evidence'][0].update(quote='invented'),
            lambda r:r.update(review_status='ACCEPT')]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                bad=copy.deepcopy(good);mutate(bad)
                with self.assertRaises(AuditError):bridge.bind(self.store,self.context,self.suite,bad,self.root/'bad.json')

    def test_v4_construct_cannot_be_a_class_id_or_auto_api_mapping(self):
        for mutate in (lambda l:l.update(v4_scenario_ids=['S5']),lambda l:l.update(api_trigger_ids=['1.2.2']),
                       lambda l:l.update(condition_link_keys=[])):
            draft=self.draft();mutate(draft['rules'][0]['mode_links'][0])
            with self.assertRaises(AuditError):bridge.bind(self.store,self.context,self.suite,draft,self.root/'bad.json')

    def test_known_mode_exposure_cannot_be_reported_as_blind(self):
        draft=self.draft();draft['purpose']='BLIND_DISCOVERY'
        with self.assertRaises(AuditError):bridge.bind(self.store,self.context,self.suite,draft,self.root/'bad.json')
        changed=copy.deepcopy(self.context);changed.update(purpose='BLIND_DISCOVERY',blind_evaluation=True)
        changed['context_hash']=digest({k:v for k,v in changed.items() if k!='context_hash'})
        with self.assertRaises(AuditError):bridge.current_context(changed,None)

    def test_blind_lane_exports_no_baseline_knowledge_and_needs_no_state(self):
        path=self.root/'blind.json'
        bridge.export_blind(self.repo,self.slug,path)
        context=target.read_json(path)
        self.assertIsNone(context['baseline']);self.assertEqual(context['modes'],[]);self.assertIsNone(context['v4'])
        report=self.bind_and_check(self.draft(context),context=context)
        self.assertTrue(report['formal_suite_ready'])
        self.assertFalse(report['actual_agent_context_isolation_attested'])
        draft=self.draft(context);draft['rules'][0]['mode_links']=self.draft()['rules'][0]['mode_links']
        with self.assertRaises(AuditError):bridge.bind(None,context,self.suite,draft,self.root/'bad.json')

    def test_unknown_warning_blocks_even_when_native_checkers_exit_zero(self):
        self.write(self.workspace/'synthetic_checker_flags.json',{'warnings':['Unknown new native coverage gap']})
        report=self.bind_and_check()
        self.assertEqual(report['status'],'BLOCKED')
        self.assertFalse(report['formal_suite_ready'])
        self.assertTrue(all(r['exit_code']==0 for r in report['native_results']))
        self.assertTrue(any(w['resolution']=='UNRESOLVED_BLOCKING' for w in report['warning_outcomes']))

    def test_formal_short_suite_blocks_but_explicit_diagnostic_does_not_claim_completion(self):
        self.rules=self.rules[:1];self.write(self.suite,self.rules)
        report=self.bind_and_check()
        self.assertEqual(report['status'],'BLOCKED')
        report=self.bind_and_check(diagnostic=True)
        self.assertEqual(report['native_suite_status'],'DIAGNOSTIC_ONLY')
        self.assertFalse(report['formal_suite_ready'])

    def test_all_e_methods_have_independent_design_acceptance_without_fake_api_tags(self):
        for method in ('E1','E2','E3','E4','E5'):
            with self.subTest(method=method):
                draft=self.code_case(None,method=method)
                report=self.bind_and_check(draft)
                self.assertEqual(report['status'],'DESIGN_READY')
                self.assertEqual(report['native_suite_status'],'PROTOCOL_DESIGN_ONLY')
                self.assertEqual(report['code_only_accepted_design_case_ids'],[0])
                self.assertEqual(report['execution_method_ids'],[method])
                self.assertFalse(report['formal_suite_ready'])
                self.assertFalse(report['hardware_validated'])
                self.assertTrue(all(w['resolution'].startswith('NON_API_DESIGN_PATH') for w in report['warning_outcomes']))

    def test_code_only_without_positive_exclusion_or_e_protocol_is_not_whitelisted(self):
        draft=self.code_case(None,method=None,kind='CODE_PATH')
        report=self.bind_and_check(draft)
        self.assertEqual(report['status'],'BLOCKED')
        self.assertEqual(report['code_only_accepted_design_case_ids'],[])

    def test_code_path_with_frozen_non_api_basis_can_finish_json_acceptance(self):
        self._baseline(non_api=True)
        path=self.root/'non-api-context.json'
        bridge.export_context(self.store,self.run,self.repo,self.slug,path)
        self.context=target.read_json(path)
        self.rules[0]['trigger_library_ref']=['CODE-state-only: independent internal path']
        self.rules[1]['trigger_library_ref']=['CODE-state-only: same internal path with another shape']
        self.write(self.suite,self.rules)
        draft=self.draft()
        for b in draft['rules']:
            b.update(api_trigger_ids=[],code_ids=['state-only'],code_justifications=[{
                'code_id':'state-only','kind':'CODE_PATH','reason':'frozen explicit non-API applicability','source_evidence':[self.citation()]}])
            b['mode_links'][0].update(api_trigger_ids=[])
        report=self.bind_and_check(draft)
        self.assertEqual(report['native_suite_status'],'FORMAL_READY_WITH_NON_API_BINDING')
        self.assertTrue(report['formal_suite_ready'])
        self.assertFalse(report['root_cause_or_event_confirmed'])

    def test_e4_allows_other_arguments_but_requires_each_own_serial_reference(self):
        draft=self.code_case(None,method='E4')
        self.assertEqual(self.bind_and_check(draft)['status'],'DESIGN_READY')
        draft['rules'][0]['protocols'][0]['participants'][-1]['case_id']=0
        with self.assertRaisesRegex(AuditError,'own serial control'):
            bridge.bind(self.store,self.context,self.suite,draft,self.root/'bad.json')

    def test_incomplete_e_design_and_fabricated_execution_success_are_rejected(self):
        for mutate in (lambda p:p.update(repeats=1),lambda p:p.update(reset_policy=''),
                       lambda p:p.update(execution_status='PASS'),lambda p:p.update(same_target_binary_required=False)):
            draft=self.code_case(None,method='E1');mutate(draft['rules'][0]['protocols'][0])
            with self.assertRaises(AuditError):bridge.bind(self.store,self.context,self.suite,draft,self.root/'bad.json')

    def test_identical_input_specs_share_work_but_deliberate_repetition_remains_distinct(self):
        self.rules[1]['inputs']=copy.deepcopy(self.rules[0]['inputs']);self.write(self.suite,self.rules)
        draft=self.draft()
        report=self.bind_and_check(draft)
        self.assertEqual(report['statistics']['unique_input_spec_work_ids'],1)
        self.assertEqual(report['statistics']['duplicate_input_spec_groups'],[[0,1]])
        draft['rules'][0]['experiment_seed']=42
        self.assertEqual(self.bind_and_check(draft)['statistics']['unique_input_spec_work_ids'],2)

    def test_binding_is_idempotent_but_changed_inputs_and_old_policy_cannot_be_reused(self):
        draft=self.draft();path=self.root/'bound.json'
        first=bridge.bind(self.store,self.context,self.suite,draft,path)
        self.assertEqual(bridge.bind(self.store,self.context,self.suite,draft,path),first)
        before=path.read_bytes()
        self.rules[0]['inputs'][0]['shape']=[99];self.write(self.suite,self.rules)
        with self.assertRaises(AuditError):gate.check(self.store,self.context,target.read_json(path),self.workspace,suite=self.suite)
        self.assertEqual(path.read_bytes(),before)
        with patch('faultaudit.precision_bridge.policy_hash',return_value='changed'):
            with self.assertRaisesRegex(AuditError,'BRIDGE_POLICY_CHANGED'):bridge.current_context(self.context,self.store)

    def test_original_target_workspace_and_state_outputs_are_protected(self):
        with self.assertRaises(AuditError):bridge.export_context(self.store,self.run,self.repo,self.slug,self.repo/'docs/overwrite.json')
        with self.assertRaises(AuditError):bridge.export_context(self.store,self.run,self.repo,self.slug,self.store.root/'overwrite.json')
        before=target.file_hash(self.workspace/'01_generate/src/kernel.cpp')
        (self.workspace/'01_generate/src/kernel.cpp').write_text('changed',encoding='utf-8')
        with self.assertRaisesRegex(AuditError,'copied asset'):self.bind_and_check()
        self.assertNotEqual(target.file_hash(self.workspace/'01_generate/src/kernel.cpp'),before)
        self.assertEqual((self.task/'01_generate/src/kernel.cpp').read_text(encoding='utf-8'),self.source_text)

    def test_same_name_wrong_owner_and_unreviewed_or_tampered_checkers_are_rejected(self):
        self.remote='https://gitcode.com/someone-else/PrecisionTesting.git'
        with self.assertRaisesRegex(AuditError,'owner/name'):bridge.current_context(self.context,self.store)
        self.remote=target.REPOSITORY;self.head='a'*40
        with self.assertRaisesRegex(AuditError,'REAUDIT'):bridge.current_context(self.context,self.store)
        self.head=target.AUDITED_COMMIT
        (self.repo/target.CHECKERS[0]).write_text('print("PASS:")',encoding='utf-8')
        with self.assertRaisesRegex(AuditError,'differs from the reviewed'):bridge.current_context(self.context,self.store)

    def test_native_json_tampering_is_not_hidden_by_valid_simplified_rules(self):
        draft=self.draft();bound=self.root/'bound.json'
        bridge.bind(self.store,self.context,self.suite,draft,bound)
        native=copy.deepcopy(self.rules)
        for r in native:r.update({'name':'WRONG','api_type':'execute_wrong','standard':{}})
        atk=self.root/'wrong-atk.json';self.write(atk,native)
        report=gate.check(self.store,self.context,target.read_json(bound),self.workspace,suite=self.suite,atk_suite=atk)
        self.assertIn('ATK_JSON_DIFFERS_FROM_UPSTREAM_MATERIALIZATION',report['errors'])
        self.assertFalse(report['formal_suite_ready'])

    def test_missing_semantic_facts_and_missing_final_atk_artifact_remain_visible(self):
        draft=self.draft();draft['rules'][0]['semantic_review']['status']='NEEDS_FACTS'
        report=self.bind_and_check(draft)
        self.assertEqual(report['status'],'NEEDS_FACTS');self.assertFalse(report['formal_suite_ready'])
        report=self.bind_and_check(materialized=False)
        self.assertEqual(report['native_suite_status'],'MATERIALIZATION_CHECKED_FINAL_ARTIFACT_MISSING')
        self.assertFalse(report['formal_suite_ready'])

    def test_checker_failure_is_blocked_not_a_successful_device_result(self):
        self.write(self.workspace/'synthetic_checker_flags.json',{'fail':True})
        report=self.bind_and_check()
        self.assertEqual(report['status'],'BLOCKED')
        self.assertTrue(all(r['exit_code']==7 for r in report['native_results']))
        self.assertEqual(report['device_execution'],'NOT_RUN')

    def test_whole_model_request_budget_counts_context_suite_schema_and_instruction(self):
        from faultaudit.input_budget import InputTooLarge,serialized_chars
        task=bridge.draft_request(self.context,self.suite)
        self.assertEqual(task['input_budget']['chars'],serialized_chars(task))
        with patch.dict('os.environ',{'FAULTAUDIT_MAX_INPUT_CHARS':'10'}):
            with self.assertRaises(InputTooLarge):bridge.draft_request(self.context,self.suite)

    def test_cli_uses_read_only_state_and_returns_pending_for_no_materialized_output(self):
        from faultaudit.cli import main
        before=target.file_hash(self.store.root/'audit.sqlite3')
        out=self.root/'cli-context.json'
        stream=io.StringIO()
        with redirect_stdout(stream):
            code=main(['--state',str(self.store.root),'precision-bridge','export','--baseline-run',self.run,
                '--repo',str(self.repo),'--task-slug',self.slug,'--out',str(out)])
        self.assertEqual(code,0)
        self.assertEqual(before,target.file_hash(self.store.root/'audit.sqlite3'))
        self.assertFalse(json.loads(stream.getvalue())['state_written'])

    def test_report_files_append_history_and_keep_raw_warnings_and_claim_boundaries(self):
        report=self.bind_and_check()
        out=self.root/'checks'
        result=gate.write_report(report,out,store=self.store,repo=self.repo)
        first=Path(result['report_json']).read_bytes()
        second=self.bind_and_check()
        next_result=gate.write_report(second,out,store=self.store,repo=self.repo)
        self.assertNotEqual(result['report_json'],next_result['report_json'])
        self.assertEqual(Path(result['report_json']).read_bytes(),first)
        self.assertIn('未执行',Path(result['report_html']).read_text(encoding='utf-8'))
        self.assertEqual(len(list(out.glob('*.json'))),2)
