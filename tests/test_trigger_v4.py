"""Synthetic boundaries for versioned V4 classification and design-only tasks."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from faultaudit.store import AuditError, Store, digest
from faultaudit.trigger_v4 import (load_v4, model_v4, require_original_profile,
    CLASS_IDS, V4_VERSION, LEGACY_VERSION, PROFILE, canonical_conditions)
from faultaudit.trigger_assessment import validate_assessment
from faultaudit.trigger_design import validate_design
from tests.test_condition_classification import attempt, leaf
from tests.test_trigger_assessment import HASH
from tests.test_trigger_workflow import synthetic_taxonomy
from tests import test_trigger_workflow as workflow_helpers
from faultaudit import trigger_workflow as workflow
from tests.v4_fixtures import markdown, v4_unknown


class V4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-v4-', dir=Path(__file__).parent)
        self.root = Path(self.temp.name)
        self.path = self.root / 'synthetic-v4.md'
        self.path.write_text(markdown(), encoding='utf-8')
        self.v4 = load_v4(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def attempt(self, text='普通张量shape驱动内部地址偏移', role='INPUT_SHAPE'):
        p, r, cell = attempt(text, role)
        original = synthetic_taxonomy()
        # Retain the existing fixture's clauses so its own 42 checks remain valid.
        original.update(items=p['taxonomy']['items'], families=p['taxonomy'].get('families', []))
        revised = {**original, "definition_version": LEGACY_VERSION}
        p.update(taxonomy=revised, v4_taxonomy=model_v4(self.v4), classification_profile=PROFILE,
            input_condition_scheme='ORIGINAL42',
            execution_capabilities={'classes':{},'methods':{},'provenance':'synthetic-only'})
        for row in r['rows']:
            item = next(i for i in revised['items'] if i['id']==row['trigger_id'])
            family = next((f for f in revised['families'] if f['family_id']==item['family_id']), {})
            row['predicate_checks']=[{'clause_role':k,'clause':t,'result':'UNKNOWN'} for k,t in sorted(canonical_conditions(item,family))]
        return p, v4_unknown(p,r), cell

    def label(self, response, key, cell, state='PARTIAL', facts=None, full=False):
        row=next(v for v in response['v4_rows'] if v['trigger_id']==key)
        row.update(applicability=state, condition_fact_ids=facts or ['F'], source_cells=[cell], evidence_basis='SOURCE_DEFINITION')
        if full:
            for c in row['predicate_checks']:
                c.update(result='MET' if c['clause_role']=='INCLUSION' else 'NOT_MET',
                    condition_fact_ids=facts or ['F'],source_cells=[cell])
        return row

    def test_no_matched_class_implies_no_synchronization_or_new_mechanism(self):
        p,r,_=self.attempt('只有故障症状，没有可决定条件','UNKNOWN')
        output=validate_assessment(p,r,HASH)
        self.assertTrue(all(v['applicability']=='UNKNOWN' for v in output['v4_rows']))
        self.assertTrue(all(b['relation']=='UNKNOWN' for b in output['external_branches']))
        self.assertEqual(output['decision']['action'],'UNDETERMINED')

    def test_complete_registry_and_unique_mount_counts(self):
        self.assertEqual((len(self.v4['items']),len(self.v4['constructions']),len(self.v4['mounts']),len(self.v4['guides'])),(31,55,64,195))
        self.assertEqual([i['id'] for i in self.v4['items']],list(CLASS_IDS))
        model=model_v4(self.v4)
        self.assertTrue(model['input_scope']['all_31_definitions_complete'])
        self.assertFalse(model['input_scope']['guidance_examples_included'])
        self.assertEqual(len(model['constructions']),55)

    def test_original_source_prerequisites_and_methods_are_preserved(self):
        before=self.path.read_bytes()
        c2=next(i for i in self.v4['items'] if i['id']=='C2')
        self.assertEqual(c2['requires'],c2['original_requires'])
        self.assertEqual(c2['skip_if'],c2['original_skip_if'])
        self.assertEqual({m['method_id'] for m in self.v4['methods']}, {'E1','E2','E3','E4','E5'})
        self.assertTrue(all(not item.get('construction_requires') and not item.get('path_requires') and not item.get('analysis_requires') for item in self.v4['items']))
        self.assertIn('合成语义前提',c2['original_requires'][0])
        self.assertEqual(self.path.read_bytes(),before)

    def test_archived_profile_and_predicate_overrides_are_rejected(self):
        p,r,_=self.attempt()
        p['input_condition_scheme']='REVISED42'
        with self.assertRaisesRegex(AuditError,'Archived revised profile'):
            validate_assessment(p,r,HASH)
        p['input_condition_scheme']='ORIGINAL42'
        p['v4_taxonomy']['items'][0]['requires']=['a widened replacement']
        with self.assertRaisesRegex(AuditError,'cannot be overridden'):
            validate_assessment(p,r,HASH)

    def test_added_execution_method_is_not_accepted_as_original(self):
        p,r=self.design()
        p['methods'].append({'method_id':'B3.2-PRODUCER-CONSUMER-v1'})
        with self.assertRaisesRegex(AuditError,'Archived execution method'):
            validate_design(p,r,HASH)

    def test_shared_constructor_definition_cannot_change_silently(self):
        text=markdown().replace('合成构造定义synthetic_code_0','另一种定义',1)
        self.path.write_text(text,encoding='utf-8')
        with self.assertRaisesRegex(AuditError,'inconsistent'):load_v4(self.path)

    def test_missing_class_or_guidance_is_not_truncated_success(self):
        self.path.write_text(markdown().replace('### N4 ','### X4 '),encoding='utf-8')
        with self.assertRaisesRegex(AuditError,'31'):load_v4(self.path)
        self.path.write_text(markdown().replace('1. **D1-01**','1. **bad-id**'),encoding='utf-8')
        with self.assertRaisesRegex(AuditError,'195'):load_v4(self.path)








    def test_unsupported_capability_claim_and_fake_path_coverage_rejected(self):
        p,r,_=self.attempt()
        r['v4_rows'][0]['coverage']['construction']='DECLARED_SUPPORTED'
        with self.assertRaisesRegex(AuditError,'capability profile'):validate_assessment(p,r,HASH)
        r['v4_rows'][0]['coverage'].update(construction='UNKNOWN',path='COVERED')
        with self.assertRaises(AuditError):validate_assessment(p,r,HASH)

    def test_missing_mount_or_canonical_clause_is_rejected(self):
        p,r,_=self.attempt()
        r['v4_rows'][0]['construction_checks'].pop()
        with self.assertRaisesRegex(AuditError,'mounted'):validate_assessment(p,r,HASH)
        r=v4_unknown(p,r);r['v4_rows'][0]['predicate_checks'].pop()
        with self.assertRaisesRegex(AuditError,'every whole'):validate_assessment(p,r,HASH)

    def test_mapping_cannot_supply_a_positive_label_without_local_facts(self):
        p,r,_=self.attempt()
        r['v4_rows'][0]['applicability']='PARTIAL'
        with self.assertRaisesRegex(AuditError,'local condition'):validate_assessment(p,r,HASH)


    def design(self):
        p,r,cell=self.attempt()
        self.label(r,'I3',cell)
        result=validate_assessment(p,r,HASH)
        payload={'case':{'case_id':'C'},'assessment_views':[{'assessment_id':'A','condition_facts':result['condition_facts'],
            'selected_rows':[{'trigger_id':'I3'}]}],
            'selected_categories':[{'id':'I3','construction_ids':['idx']}],
            'guidance':[{'guide_id':'I3-01','category_id':'I3'}],
            'methods':[{'method_id':v} for v in ('E1','E2','E3','E4','E5')]}
        response={k:copy.deepcopy(r[k]) for k in ('executor','producer','self_check')}
        response.update(request_hash=HASH,case_id='C',cards=[{'card_id':'card','assessment_id':'A','status':'NEEDS_FACTS',
            'category_ids':['I3'],'construction_ids':['idx'],'guide_ids':['I3-01'],'condition_fact_ids':['F'],
            'variables':[{'name':'shape','kind':'INPUT','proposed_values':['N'],'condition_fact_ids':['F'],'reason':'合成驱动'}],
            'boundaries':['宽整数先算公式'],'reference':'宽整数地址参考','target_path':'目标内部算址待定位','checks':['地址与数值'],
            'unknowns':['位宽待确认'],'execution_status':'NOT_RUN'}])
        return payload,response

    def participant(self,key,role,target='T',values='fixed'):
        return {'participant_id':key,'role':role,'target_call_id':target,'input_assignment':values,
            'output_owner':key+'-out','context':key+'-context','stream':key+'-stream',
            'executor':key+'-executor','lifecycle':'independent planned lifecycle; NOT_RUN'}

    def test_design_only_never_accepts_device_pass(self):
        p,r=self.design();validate_design(p,r,HASH)
        r['cards'][0]['execution_status']='PASSED'
        with self.assertRaises(AuditError):validate_design(p,r,HASH)

    def test_design_cannot_borrow_issue_facts_or_convert_derived_to_input(self):
        p,r=self.design();r['cards'][0]['condition_fact_ids']=['OTHER-ISSUE']
        with self.assertRaisesRegex(AuditError,'one selected'):validate_design(p,r,HASH)
        r['cards'][0]['condition_fact_ids']=['F'];p['assessment_views'][0]['condition_facts'][0]['role']='DERIVED_CONTROL'
        with self.assertRaisesRegex(AuditError,'API input'):validate_design(p,r,HASH)

    def test_e2_fixes_target_and_allows_different_predecessor(self):
        p,r=self.design();card=r['cards'][0]
        card.update(execution_method_ids=['E2'],participants=[self.participant('target','TARGET'),self.participant('pre','PREDECESSOR','P','different shape')],
            target_invariant={'target_call_id':'T','variable_participant_ids':['pre']},serial_baseline='fresh T',protocol_steps=['fresh T','P then identical T'])
        validate_design(p,r,HASH)
        card.pop('serial_baseline')
        with self.assertRaisesRegex(AuditError,'serial baseline'):validate_design(p,r,HASH)

    def test_e4_isolates_outputs_and_target_reference(self):
        p,r=self.design();card=r['cards'][0]
        card.update(execution_method_ids=['E4'],participants=[self.participant('target','TARGET'),self.participant('interferer','INTERFERER','U','threshold=0.5')],
            target_invariant={'target_call_id':'T','variable_participant_ids':['interferer']},serial_baseline='each threshold separate reference',protocol_steps=['serial','interleaved'])
        validate_design(p,r,HASH)
        card['participants'][1]['output_owner']=card['participants'][0]['output_owner']
        with self.assertRaisesRegex(AuditError,'distinct output'):validate_design(p,r,HASH)



class V4WorkflowTests(unittest.TestCase):
    setUp=workflow_helpers.TriggerWorkflowTests.setUp
    tearDown=workflow_helpers.TriggerWorkflowTests.tearDown
    write_modes=workflow_helpers.TriggerWorkflowTests.write_modes
    start=workflow_helpers.TriggerWorkflowTests.start
    response=workflow_helpers.TriggerWorkflowTests.response
    def test_v4_workflow_dispatches_design_and_keeps_versioned_history(self):
        from faultaudit import xlsx_workflow as xw
        with patch.dict('os.environ', {'FAULTAUDIT_MAX_INPUT_CHARS': '160000'}):
            self.start()
        path=self.root/'synthetic-v4.md';path.write_text(markdown(),encoding='utf-8')
        self.store.put(self.run,'trigger_config','config',{**workflow._settings(self.store,self.run),'basis':'SOURCE_DEFINITIONS'},mutable=True)
        cfg=self.store.get(self.run,'xlsx_workflow','config')
        self.store.put(self.run,'xlsx_workflow','config',{**cfg,'init_basis':'SOURCE_DEFINITIONS'},mutable=True)
        old_taxonomy=workflow._taxonomy(self.store,self.run)
        workflow.configure_v4(self.store,self.run,path)
        self.assertEqual(self.store.get(self.run,'trigger_taxonomies',old_taxonomy['taxonomy_id']),old_taxonomy)
        with patch.dict('os.environ',{'FAULTAUDIT_MAX_INPUT_CHARS':'160000'}):
            queue=xw.next_tasks(self.store,self.run)
            task=queue['tasks'][0];req=self.store.get(self.run,'workflow_requests',task['task_id'])
            self.assertEqual(req['payload']['evaluation_order'][1:3],['v4_rows','rows'])
            response=self.response(req,definition_only=True)
            # Rebuild original canonical checks; fixture is explicitly synthetic.
            for row in response['rows']:
                item=next(i for i in req['payload']['taxonomy']['items'] if i['id']==row['trigger_id'])
                row['predicate_checks']=[{'clause_role':k,'clause':v,'result':'UNKNOWN'} for k,v in sorted(canonical_conditions(item))]
            response=v4_unknown(req['payload'],response)
            xw.submit(self.store,self.run,task['task_id'],response)
            next_queue=xw.next_tasks(self.store,self.run)
            self.assertEqual([t['kind'] for t in next_queue['tasks']],['trigger_design'])
            design=next_queue['tasks'][0];dreq=self.store.get(self.run,'workflow_requests',design['task_id'])
            self.assertEqual(dreq['payload']['input_scope']['selected_guide_ids'],[])
            answer={k:copy.deepcopy(response[k]) for k in ('executor','producer','self_check')}
            answer.update(request_hash=dreq['request_hash'],case_id=dreq['payload']['case']['case_id'],cards=[{
                'card_id':'synthetic-missing','assessment_id':task['task_id'],'status':'NEEDS_FACTS',
                'reference':'reference unknown','target_path':'unknown','checks':['obtain legal input roles'],
                'unknowns':['no positive category facts']}])
            xw.submit(self.store,self.run,design['task_id'],answer)
            self.assertEqual(xw.next_tasks(self.store,self.run)['tasks'],[])
            from faultaudit.trigger_report import build_workbook
            projection=workflow._projection(self.store,self.run)
            book=build_workbook(projection)
            names=[v['name'] for v in book['sheets']]
            self.assertLess(names.index('V4条件分类'),names.index('42项条件分类'))
            self.assertEqual(len(next(v['rows'] for v in book['sheets'] if v['name']=='V4构造情形')),64)
            card_table=next(v for v in book['sheets'] if v['name']=='用例设计卡')
            self.assertEqual(card_table['rows'][0][card_table['columns'].index('执行结果')],'NOT_RUN')
            base=workflow.finalize(self.store,self.run)
            self.assertEqual(base['v4_definition_version'],V4_VERSION)
            self.assertNotIn('mapping_id',base)
            self.assertNotIn('revised_definition_version',base)
            from openpyxl import Workbook
            source=self.root/'synthetic-incremental.xlsx'
            workbook=Workbook()
            workbook.active.append(['统一ID','问题描述'])
            workbook.active.append(['SYN-NEW','Synthetic new case with unknown mechanism'])
            workbook.save(source)
            incremental=workflow.start_incremental(self.store,source,self.run,self.work,executor='codex')
            inc_run=incremental['run_id']
            self.assertEqual(workflow._settings(self.store,inc_run)['input_condition_scheme'],'ORIGINAL42')
            self.assertEqual(self.store.records(inc_run,'trigger_mappings'),[])
            self.assertEqual(workflow._projection(self.store,inc_run)['v4_taxonomy']['definition_version'],V4_VERSION)

            self.assertEqual(len(base['condition_index'][0]['v4_rows']),31)
            combined=copy.deepcopy(projection)
            combined.update(phase='INCREMENTAL',baseline=copy.deepcopy(base))
            previous_index=copy.deepcopy(base['condition_index'])
            previous_index[0]['rows'][0]['applicability']='APPLICABLE'
            wrong_issue=copy.deepcopy(projection['assessments'][0])
            wrong_issue['issue_index']=999
            combined['previous_classification']={'taxonomy':{'definition_version':'SYNTHETIC-PRIOR'},
                'assessments':[wrong_issue],'baseline':{'condition_index':previous_index}}
            changes=next(t for t in build_workbook(combined)['sheets'] if t['name']=='逐项分类变化')
            init_changes=[dict(zip(changes['columns'],r)) for r in changes['rows'] if r[0]=='INIT']
            self.assertEqual(len(init_changes),1)
            self.assertEqual(init_changes[0]['旧适用性'],'APPLICABLE')
            self.assertEqual(init_changes[0]['新适用性'],'UNKNOWN')
            self.assertEqual(init_changes[0]['旧定义版本'],'SYNTHETIC-PRIOR')
            increment_changes=[dict(zip(changes['columns'],r)) for r in changes['rows'] if r[0]=='INCREMENTAL']
            self.assertEqual(len(increment_changes),42)
            self.assertTrue(all(r['旧适用性']=='无同范围旧评估' for r in increment_changes))
            combined['baseline']['status']='STALE'
            stale_changes=next(t for t in build_workbook(combined)['sheets'] if t['name']=='逐项分类变化')
            self.assertFalse(any(r[0]=='INIT' for r in stale_changes['rows']))
            history=len(self.store.records(self.run,'trigger_assessments'))
            path.write_text(markdown()+'\nnew source annotation\n',encoding='utf-8')
            workflow.configure_v4(self.store,self.run,path)
            self.assertEqual(workflow.current_assessments(self.store,self.run),[])
            self.assertEqual(len(self.store.records(self.run,'trigger_assessments')),history)
            from faultaudit.trigger_design import current_designs
            self.assertEqual(current_designs(self.store,self.run),[])

    def test_v4_requests_block_on_actual_serialized_budget_and_keep_full_definitions(self):
        from faultaudit import xlsx_workflow as xw
        with patch.dict('os.environ', {'FAULTAUDIT_MAX_INPUT_CHARS': '1000'}):
            self.start()
        path=self.root/'v4.md';path.write_text(markdown(),encoding='utf-8')
        cfg=self.store.get(self.run,'xlsx_workflow','config')
        self.store.put(self.run,'xlsx_workflow','config',{**cfg,'init_basis':'SOURCE_DEFINITIONS'},mutable=True)
        settings=workflow._settings(self.store,self.run)
        self.store.put(self.run,'trigger_config','config',{**settings,'basis':'SOURCE_DEFINITIONS'},mutable=True)
        workflow.configure_v4(self.store,self.run,path)
        with patch.dict('os.environ',{'FAULTAUDIT_MAX_INPUT_CHARS':'1000'}):
            result=xw.next_tasks(self.store,self.run)
            self.assertFalse(result['tasks'])
            state=self.store.get(self.run,'workflow_state','current')
            blocks=[self.store.get(self.run,'workflow_blocks',key) for key in state['block_ids']]
            self.assertTrue(blocks)
            self.assertTrue(all(b['reason']=='INPUT_TOO_LARGE' for b in blocks))
            self.assertTrue(all(b['input_budget']['budget']==1000 for b in blocks))
        payload=next(workflow.classification_payloads(self.store,self.run))
        self.assertEqual((len(payload['taxonomy']['items']),len(payload['v4_taxonomy']['items']),len(payload['v4_taxonomy']['constructions'])),(42,31,55))
        self.assertEqual(len(self.store.records(self.run,'trigger_assessments')),0)
        from faultaudit.trigger_report import build_workbook
        book=build_workbook(workflow._projection(self.store,self.run))
        self.assertTrue(all(s['columns'] for s in book['sheets']))
        self.assertEqual(next(s['rows'] for s in book['sheets'] if s['name']=='V4条件分类'),[])
