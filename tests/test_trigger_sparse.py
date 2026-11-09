"""Targeted V5 checks only. No production state, web or model execution."""
import copy
from pathlib import Path
import unittest

from faultaudit.store import AuditError
from faultaudit.trigger_assessment import validate_assessment
from faultaudit.trigger_sparse import CONTRACT, frame_version
from tests.test_condition_classification import attempt, label
from tests.test_trigger_assessment import HASH


def sparse_attempt(text="INT32地址偏移溢出", role="INDEX_OR_OFFSET"):
    p, r, cell = attempt(text, role)
    p.update(phase="INIT", assessment_basis="SOURCE_DEFINITIONS", classification_contract=CONTRACT)
    p["subject"]["mode_id"] = "M1"
    label(r, "1.3.2", cell, role_result="MET")
    r.update(classification_contract=CONTRACT,
        rows=[row for row in r["rows"] if row["trigger_id"] == "1.3.2"], external_branches=[],
        details=[{"detail_id": "D1", "mode_id": "M1", "name": "偏移溢出", "mechanism": cell["quote"],
            "evidence_basis": "SOURCE_DEFINITION", "source_cells": [cell]}],
        classification_summary={"status": "CLASSIFIED", "reason": "原文有明确偏移条件", "unknowns": ["公式未知"]},
        scenarios=[{"scenario_id": "s1", "title": "偏移边界", "condition_fact_ids": ["F"], "reason": "同一原文条件"}],
        label_links=[{"scheme": "REVISED42", "definition_version": frame_version(p, "REVISED42"),
            "trigger_id": "1.3.2", "detail_ids": ["D1"], "scenario_ids": ["s1"], "condition_fact_ids": ["F"]}],
        decision={"action": "INIT_ONLY", "reason": "只整理原定义"})
    return p, r


class SparseAssessmentTests(unittest.TestCase):
    def test_one_selected_rule_and_derived_links_without_web_confirmation(self):
        p, r = sparse_attempt(); before = copy.deepcopy(r)
        out = validate_assessment(p, r, HASH)
        self.assertEqual(r, before)
        self.assertEqual(len(out["rows"]), 1)
        self.assertEqual(out["details"][0]["trigger_ids"], ["1.3.2"])
        self.assertEqual(out["details"][0]["condition_links"], r["label_links"])
        self.assertEqual(out["classification_scope"]["omitted_rules"], "NOT_ASSESSED")
        self.assertEqual(out["processing_status"], "AUTO_PROCESSED")
        self.assertFalse(out["review_required"])
        self.assertFalse(out["execution_verified"])

    def test_missing_link_or_unknown_scenario_is_rejected(self):
        for mutate in (lambda r: r.update(label_links=[]),
                       lambda r: r["label_links"][0].update(scenario_ids=["other"]),
                       lambda r: r["label_links"][0].update(detail_ids=["unknown"]),
                       lambda r: r["label_links"][0].update(definition_version="old")):
            p, r = sparse_attempt(); mutate(r)
            with self.assertRaises(AuditError): validate_assessment(p, r, HASH)

    def test_no_dense_unknown_padding_is_accepted_or_saved(self):
        p, r = sparse_attempt(); r["rows"][0]["applicability"] = "UNKNOWN"
        with self.assertRaisesRegex(AuditError, "Omit UNKNOWN"):
            validate_assessment(p, r, HASH)

    def test_empty_classification_needs_specific_gap_and_preserves_definition(self):
        p, r = sparse_attempt(); r.update(rows=[], scenarios=[], label_links=[],
            classification_summary={"status": "INSUFFICIENT_INFORMATION", "reason": "缺合法输入和地址公式", "unknowns": ["API和公式"]})
        out = validate_assessment(p, r, HASH)
        self.assertEqual(out["rows"], [])
        self.assertEqual(len(out["details"]), 1)
        self.assertEqual(out["processing_status"], "PENDING")
        r["classification_summary"]["unknowns"] = []
        with self.assertRaisesRegex(AuditError, "specific missing"):
            validate_assessment(p, r, HASH)

    def test_strong_match_and_accept_gates_remain(self):
        p, r = sparse_attempt(); r["rows"][0]["relation"] = "MATCH"
        with self.assertRaises(AuditError): validate_assessment(p, r, HASH)
        p, r = sparse_attempt(); r["decision"]["action"] = "ACCEPT"
        with self.assertRaises(AuditError): validate_assessment(p, r, HASH)

    def test_links_cannot_silently_disagree_with_legacy_detail_ids(self):
        p, r = sparse_attempt(); r["details"][0]["trigger_ids"] = ["1.1.1"]
        with self.assertRaisesRegex(AuditError, "conflict"):
            validate_assessment(p, r, HASH)

    def test_candidate_proposal_does_not_require_or_generate_formal_adoption(self):
        p,r=sparse_attempt();p.update(phase='INCREMENTAL',assessment_basis='HISTORICAL_EVIDENCE')
        r['decision']={'action':'UNDETERMINED','reason':'事件与正式入库尚未确认'}
        r['candidate_proposal']={'action':'PROPOSE_NEW_MODE_CANDIDATE','closest_mode_ids':['M1'],
            'detail_ids':['D1'],'difference':'合成具体机理边界差异，仍待复核','reason':'仅原文候选，不是正式新增'}
        out=validate_assessment(p,r,HASH)
        self.assertEqual(out['decision']['action'],'UNDETERMINED')
        self.assertEqual(out['candidate_proposal']['adoption_status'],'SUGGESTION_ONLY')
        self.assertFalse(out['review_required'])
        r['candidate_proposal']['detail_ids']=[]
        with self.assertRaisesRegex(AuditError,'current quoted mechanism'):
            validate_assessment(p,r,HASH)

    def test_scenario_facts_are_local_and_complete(self):
        p, r = sparse_attempt(); r["scenarios"][0]["condition_fact_ids"] = ["OTHER"]
        with self.assertRaisesRegex(AuditError, "unknown local facts"):
            validate_assessment(p, r, HASH)
        p, r = sparse_attempt(); r["scenarios"].append({**r["scenarios"][0], "scenario_id": "s2"})
        with self.assertRaisesRegex(AuditError, "Unlinked scenarios"):
            validate_assessment(p, r, HASH)

    def test_v4_labels_and_selected_mounts_are_sparse_and_independent(self):
        from tests.test_trigger_v4 import V4Tests
        fixture = V4Tests(); fixture.setUp()
        try:
            p, r, cell = fixture.attempt('输入为一个合法的普通张量shape', 'INPUT_SHAPE')
            fixture.label(r, 'S1', cell)
            r.update(rows=[], v4_rows=[v for v in r['v4_rows'] if v['trigger_id']=='S1'], external_branches=[],
                classification_contract=CONTRACT,
                classification_summary={'status':'CLASSIFIED','reason':'原输入shape线索','unknowns':['粒度未知']},
                scenarios=[{'scenario_id':'s1','title':'输入shape','condition_fact_ids':['F'],'reason':'同一句输入声明'}],
                label_links=[{'scheme':'V4','definition_version':frame_version(p,'V4'),'trigger_id':'S1',
                    'detail_ids':['D'],'scenario_ids':['s1'],'condition_fact_ids':['F']}],
                details=[{'detail_id':'D','name':'输入shape机理候选','mechanism':cell['quote'],
                    'evidence_basis':'SOURCE_DEFINITION','source_cells':[cell]}])
            r['v4_rows'][0]['construction_checks']=[]
            p['classification_contract']=CONTRACT
            out=validate_assessment(p,r,HASH)
            self.assertEqual(out['rows'],[])
            self.assertEqual(len(out['v4_rows']),1)
            self.assertEqual(out['v4_rows'][0]['construction_checks'],[])
            self.assertEqual(out['details'][0]['trigger_ids'],[])
            r.update(v4_rows=[],scenarios=[],label_links=[],classification_summary={
                'status':'INSUFFICIENT_INFORMATION','reason':'该源定义没有可归类的输入条件','unknowns':['合法输入条件']})
            self.assertEqual(validate_assessment(p,r,HASH)['v4_processing_status'],'NOT_ASSESSED')
        finally: fixture.tearDown()

    def test_branch_only_means_identified_context_not_all_inputs_excluded(self):
        from tests.test_condition_classification import leaf
        text='同一调用存在多核同步竞争'
        p,r=sparse_attempt(text,'SYNC_RACE')
        from tests.test_condition_classification import attempt as base_attempt
        _,template,cell=base_attempt(text,'SYNC_RACE')
        leaf(template,'3.3',cell,'PARTIAL')
        r.update(rows=[],external_branches=[b for b in template['external_branches'] if b['branch_id']=='3'])
        r['external_branches'][0]['category_checks']=[c for c in r['external_branches'][0]['category_checks'] if c['category_id']=='3.3']
        r['classification_summary']['status']='BRANCH_ONLY'
        r['details'][0].update(name='同步竞争',mechanism=text)
        r['label_links'][0].update(scheme='BRANCH',definition_version=frame_version(p,'BRANCH'),trigger_id='3.3')
        out=validate_assessment(p,r,HASH)
        self.assertEqual(out['rows'],[])
        self.assertEqual(out['classification_summary']['status'],'BRANCH_ONLY')
        self.assertEqual(out['external_branches'][0]['category_checks'][0]['applicability'],'PARTIAL')


class CombinationTests(unittest.TestCase):
    def data(self):
        from faultaudit.trigger_combinations import analyze
        p, r = sparse_attempt(); result = validate_assessment(p, r, HASH)
        result['rows'].append({**copy.deepcopy(result['rows'][0]),'trigger_id':'1.1.1'})
        result['scenarios'].append({'scenario_id':'s2','title':'另一情景','condition_fact_ids':['F'],'reason':'合成独立情景'})
        result['label_links'].append({**copy.deepcopy(result['label_links'][0]),'trigger_id':'1.1.1','scenario_ids':['s2']})
        data={'phase':'INCREMENTAL','run_id':'synthetic','taxonomy':p['taxonomy'],
            'subjects':[{'case_id':'C1','source_case':{'description':'test','raw':{}}},
                        {'case_id':'C2','source_case':{'description':'unassessed','raw':{}}}],
            'assessments':[{'assessment_id':'A1','case_id':'C1','result':result}], 'gaps':[]}
        return data, analyze

    def test_same_case_is_not_same_scenario(self):
        data, analyze = self.data(); frame=analyze(data)['frames'][0]
        pair=frame['pairs'][0]
        self.assertEqual((pair['count'],pair['same_scenario_count']),(1,0))
        self.assertEqual(sum(g['count'] for g in frame['exact_combinations']),2)
        self.assertEqual(frame['unassessed_unit_ids'],['C2'])
        self.assertEqual(len(frame['categories']),42)

    def test_duplicate_and_stale_results_do_not_duplicate_case_count(self):
        data, analyze = self.data()
        data['assessments'] += [copy.deepcopy(data['assessments'][0]),
            {**copy.deepcopy(data['assessments'][0]),'assessment_id':'OLD','is_stale':True}]
        self.assertEqual(analyze(data)['assessments_counted'],1)
        self.assertEqual(analyze(data)['frames'][0]['pairs'][0]['count'],1)

    def test_local_scenario_names_do_not_merge_across_assessments(self):
        data, analyze=self.data(); a=data['assessments'][0]
        a['result']['label_links'][1]['scenario_ids']=['s1']
        other=copy.deepcopy(a);other['assessment_id']='A2'
        other['result']['rows']=other['result']['rows'][1:]
        other['result']['label_links']=other['result']['label_links'][1:]
        a['result']['rows']=a['result']['rows'][:1]
        a['result']['label_links']=a['result']['label_links'][:1]
        data['assessments'].append(other)
        self.assertEqual(analyze(data)['frames'][0]['pairs'][0]['same_scenario_count'],0)

    def test_confirmed_axis_does_not_inherit_description_tags(self):
        data, analyze=self.data(); confirmed=analyze(data)['frames'][1]
        self.assertEqual(confirmed['pairs'],[])
        self.assertEqual(confirmed['exact_combinations'][0]['categories'],[])

    def test_same_scenario_pair_is_deduplicated_by_case(self):
        data,analyze=self.data()
        a=data['assessments'][0]
        a['result']['label_links'][1]['scenario_ids']=['s1']
        data['assessments'].append({**copy.deepcopy(a),'assessment_id':'A2'})
        pair=analyze(data)['frames'][0]['pairs'][0]
        self.assertEqual((pair['count'],pair['same_scenario_count']),(1,1))

    def test_old_frame_does_not_enter_current_combinations(self):
        data,analyze=self.data()
        data['assessments'][0]['result']['definition_versions']={'revised42':'STALE'}
        frame=analyze(data)['frames'][0]
        self.assertEqual(frame['assessed_unit_count'],0)
        self.assertEqual(frame['pairs'],[])

    def test_mode_and_case_counting_units_are_distinct(self):
        data,analyze=self.data();data['phase']='INIT'
        for subject in data['subjects']:subject['mode_id']='M1'
        frame=analyze(data)['frames'][0]
        self.assertEqual((frame['counting_unit'],frame['unit_count']),('mode_id',1))

    def test_html_primary_is_escaped_and_contains_no_dense_unknown_table(self):
        from faultaudit.trigger_html import render,index_workbook
        data,_=self.data();data['subjects'][0]['source_case']['raw']={'描述':'</script><img src=x onerror=alert(1)>'}
        report=render(data)
        self.assertNotIn('<img src=x',report)
        self.assertIn('同情景',report)
        self.assertIn('NOT_ASSESSED',report)
        self.assertIn('原始定义',report)
        self.assertEqual(len(index_workbook(data)['sheets']),4)


class SparseWorkflowTests(unittest.TestCase):
    def test_opt_in_changes_identity_preserves_sources_and_rejects_old_request(self):
        from tests.test_trigger_declared import DeclaredWorkflowTests
        from faultaudit import trigger_workflow as workflow, xlsx_workflow as xw
        helper=DeclaredWorkflowTests();helper.setUp()
        try:
            helper.start()
            run=helper.source.run; store=helper.store
            old_payload=next(workflow.classification_payloads(store,run))
            request=helper.source.request(old_payload)
            source=copy.deepcopy(store.records(run,'cases'))
            workflow.configure_v5(store,run)
            self.assertEqual(store.records(run,'cases'),source)
            self.assertTrue(workflow.configure_v5(store,run)['idempotent'])
            payload=next(workflow.classification_payloads(store,run))
            self.assertEqual(payload['classification_contract'],CONTRACT)
            self.assertNotEqual(payload['basis_hash'],old_payload['basis_hash'])
            with self.assertRaisesRegex(AuditError,'input/baseline changed'):
                workflow.accept_assessment(store,run,request,{})
            dispatched=xw.next_tasks(store,run)
            self.assertEqual([v['kind'] for v in dispatched['tasks']],['trigger_classify'])
            result=workflow.export(store,run)
            self.assertEqual(result['primary_report'],'HTML')
            self.assertTrue(Path(result['report_html']).is_file())
            self.assertNotIn('xlsx',result)
            self.assertEqual(store.events(run,'review'),[])
        finally: helper.tearDown()
