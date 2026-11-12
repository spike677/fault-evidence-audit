"""Targeted R2 regressions. Synthetic mutations only; historical bundles read-only."""
import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import rc128_review as core
import rc128_revision as revision
import rc128_six_reviews as six


class QuantityRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legacy=core.LEGACY_BUNDLE;cls.folder=core.DEFAULT
        text=(cls.legacy/'report.html').read_text(encoding='utf-8')
        cls.old=json.loads(re.search(r'<script type="application/json" id="payload">(.*?)</script>',text,re.S).group(1))
        cls.modes={m['mode_id']:m for m in cls.old['baseline']}
        cls.defs={(d['system'],d['condition_id']):d for d in cls.old['definitions']}
        cls.data=revision.reconcile(cls.old,cls.modes,cls.defs)

    def test_six_and_22_quantities_not128_deep_reviews(self):
        self.assertEqual(len(self.data['case_reviews']),6)
        self.assertEqual(len(self.data['driving_quantities']),22)
        self.assertTrue(revision.validate_quantities(self.data['driving_quantities']))
        self.assertEqual(sum(r['review_scope']=='HISTORICAL_ANALYSIS_REUSED'for r in self.data['results']),119)

    def test_unknown_reason_required_for_each_question_and_q3_role(self):
        for q in self.data['driving_quantities']:
            for part in [q['Q1'],q['Q2'],q['Q4'],*q['Q3'].values()]:
                self.assertTrue(part['answer']);self.assertTrue(part['unknown_reason'])
                self.assertFalse(part['confirmed'])
        bad=copy.deepcopy(self.data['driving_quantities']);bad[0]['Q3']['initializer']['unknown_reason']=''
        self.assertFalse(revision.validate_quantities(bad))

    def test_missing_or_duplicate_driver_rejected(self):
        self.assertFalse(revision.validate_quantities(self.data['driving_quantities'][:-1]))
        bad=copy.deepcopy(self.data['driving_quantities']);bad[0]['quantity_id']=bad[1]['quantity_id']
        self.assertFalse(revision.validate_quantities(bad))

    def test_four_questions_cannot_create_accept_or_confirmation(self):
        bad=copy.deepcopy(self.data['driving_quantities']);bad[0]['relation_confirmed']=True
        self.assertFalse(revision.validate_quantities(bad))
        bad[0]['relation_confirmed']=False;bad[0]['manual_accept_created']=True
        self.assertFalse(revision.validate_quantities(bad))
        self.assertTrue(all(m['action']=='PENDING'for m in self.data['comparisons']if m.get('task_id')in six.SIX))

    def test_noncount_encoding_and_unknown_consumer_not_unit_error(self):
        qs=[q for q in self.data['driving_quantities']if q['task_id']in ['RC-010','RC-105']]
        self.assertTrue(all('非计数量'in q['Q2']['answer']for q in qs))
        self.assertTrue(all(not q['unit_error_confirmed']for q in qs))

    def test_cache_mismatch_does_not_assert_key_omission(self):
        r=next(r for r in self.data['case_reviews']if r['task_id']=='RC-009')
        self.assertIn('不预断key遗漏',r['candidate_mechanism']['unknown'])
        self.assertFalse(r['original30_relation']['priority_inferred_from_four_questions'])

    def test_initialization_does_not_become_sync_or_a05(self):
        r=next(r for r in self.data['case_reviews']if r['task_id']=='RC-010')
        self.assertIn('不等于同步或内存初始化',r['candidate_mechanism']['unknown'])
        self.assertEqual([m['mode_id']for m in r['original30_relation']['similar_modes']],['M013','M007'])

    def test_no_mlp_does_not_prove_uninitialized(self):
        q=next(q for q in self.data['driving_quantities']if q['label']=='专家槽位结果可用性')
        self.assertIn('未执行MLP不等于未初始化',q['Q2']['answer'])
        self.assertIn('默认填充',q['Q3']['initializer']['answer'])

    def test_negative_index_transform_not_automatically_defect(self):
        q=next(q for q in self.data['driving_quantities']if q['label']=='abs后索引')
        self.assertIn('不能仅凭转换判缺陷',q['Q2']['answer'])
        self.assertFalse(q['relation_confirmed'])

    def test_rc062_register_constructor_contamination_removed(self):
        f=next(f for f in self.data['failures']if f.get('task_id')=='RC-062')
        self.assertNotIn('寄存器',f['expected_relation']);self.assertNotIn('构造步骤',f['expected_relation'])
        self.assertIn('目标调用',f['expected_relation'])
        r=next(r for r in self.data['case_reviews']if r['task_id']=='RC-062')
        self.assertNotIn('恢复遗漏',r['candidate_mechanism']['name'])
        self.assertEqual(len(r['candidate_mechanism']['alternatives']),6)

    def test_rc029_parameter_replacement_not_stage_semantics(self):
        targets=[f for f in self.data['failures']if (f.get('task_id')or f.get('technical_case_id'))in ['RC-029','TC-FP8-VSCALE']]
        for f in targets:
            for forbidden in ['前块','当前块','前一块','前位置','前/当前']:
                self.assertNotIn(forbidden,json.dumps(f,ensure_ascii=False))
        qs=[q for q in self.data['driving_quantities']if q['task_id']=='RC-029']
        self.assertIn('OBS:TC-FP8-VSCALE:1:before',qs[0]['Q1']['evidence_ids'])

    def test_shared_only_corrections_do_not_claim_quantity_review(self):
        for cid in six.SHARED:
            r=next(r for r in self.data['results']if r['task_id']==cid)
            self.assertEqual(r['review_scope'],'SHARED_TEMPLATE_CORRECTION_ONLY')
            self.assertNotIn('quantity_ids',r)
        for cid in ['TC-FP8-VSCALE','TC-SFAG-EVENT-ID']:
            t=next(t for t in self.data['technical_cases']if t['technical_case_id']==cid)
            self.assertIn('NOT_QUANTITY_REVIEW',t['review_scope'])

    def test_semantic_applicability_can_coexist_with_construction_block(self):
        c=next(c for c in self.data['conditions']if c.get('task_id')=='RC-009'and c['system']=='V4')
        synthetic=copy.deepcopy(c)
        synthetic['semantic_applicability']['status']='APPLICABLE'
        synthetic['construction_feasibility']['status']='BLOCKED_AUTOCONTIGUOUS'
        self.assertEqual(synthetic['semantic_applicability']['status'],'APPLICABLE')
        # The real report does not invent an executor observation.
        self.assertEqual(c['construction_feasibility']['status'],'EXECUTOR_CAPABILITY_UNKNOWN')
        api=next(c for c in self.data['conditions']if c.get('task_id')=='RC-009'and c['system']=='API42')
        self.assertEqual(api['semantic_applicability']['status'],'SCHEMA_CONDITIONAL')

    def test_zeros_classification_without_kernel_confirmation(self):
        c=next(c for c in self.data['conditions']if c.get('task_id')=='RC-062'and c['condition_id']=='zeros')
        self.assertEqual(c['semantic_applicability']['status'],'CONDITIONAL_SOURCE_CLASSIFICATION')
        self.assertFalse(c['defect_confirmed']);self.assertFalse(c['counts_as_verified_coverage'])

    def test_scale_structure_not_inferred_from_scale_word(self):
        c=next(c for c in self.data['conditions']if c.get('task_id')=='RC-029'and c['condition_id']=='scale_structure')
        self.assertEqual(c['semantic_applicability']['status'],'UNKNOWN')
        self.assertIn('形状／轴',c['semantic_applicability']['reason'])

    def test_shared_mounts_independently_assessed(self):
        for cid,scenario,unknown in [('RC-023','index_mask','C4'),('RC-029','enum_quant','C2')]:
            c=next(c for c in self.data['conditions']if c.get('task_id')==cid and c['condition_id']==scenario)
            m=next(m for m in c['class_assessments']if m['class_id']==unknown)
            self.assertEqual(m['status'],'UNKNOWN')

    def test_carrier_change_does_not_change_mechanism_or_relationship(self):
        original=copy.deepcopy(six.REVIEWS['RC-009'])
        try:
            a=six.review('RC-009',[],self.modes)
            six.REVIEWS['RC-009']['carrier']='different carrier'
            b=six.review('RC-009',[],self.modes)
            self.assertNotEqual(a['implementation_carrier'],b['implementation_carrier'])
            self.assertEqual(a['candidate_mechanism'],b['candidate_mechanism'])
            self.assertEqual(a['original30_relation'],b['original30_relation'])
        finally:six.REVIEWS['RC-009']=original

    def test_six_four_column_claims_have_scope_and_reference(self):
        for r in self.data['case_reviews']:
            for k in ['candidate_mechanism','implementation_carrier','evidence_level','original30_relation']:self.assertTrue(r[k])
            for claim in r['evidence_level']['claims']:
                self.assertTrue(claim['evidence_ids']);self.assertTrue(claim['limitation'])

    def test_summary_does_not_inherit_seven_current_candidate_groups(self):
        s=revision.summary(self.data,self.folder)
        self.assertEqual(s['candidate_review_families'],0)
        self.assertEqual(s['schema_version'],'RC128-RELATION-REVIEW-2')
        self.assertIn('R2新增搜索0轮',s['search_count_scope'])
        self.assertEqual(s['revision']['new_or_extension_decisions'],0)

    def test_original_input_and122_core_analyses_preserved(self):
        self.assertEqual([r['original_input']for r in self.data['results']],[r['original_input']for r in self.old['results']])
        for old,new in zip(self.old['results'],self.data['results']):
            if old['task_id']not in six.SIX:self.assertEqual(old['root_cause'],new['root_cause'])
        for old,new in zip(self.old['failures'],self.data['failures']):
            if (old.get('task_id')or old.get('technical_case_id'))not in six.EXPECTED:self.assertEqual(old,new)

    def test_new_context_is_included_in_entire_serialized_budget(self):
        args=([self.old['results'][0]['original_input']],self.old['baseline'],self.old['definitions'],self.legacy)
        small=core.input_budget_receipts(*args,review_context={'RC-001':{'source':''}})['receipts'][0]
        context={'RC-001':{'source':'x'*160001+'TAIL_CONCLUSION'}}
        big=core.input_budget_receipts(*args,review_context=context)['receipts'][0]
        self.assertGreater(big['serialized_input_chars'],small['serialized_input_chars']+160000)
        self.assertEqual(big['status'],'BLOCKED');self.assertEqual(big['reason'],'INPUT_TOO_LARGE')
        self.assertEqual(context['RC-001']['source'][-15:],'TAIL_CONCLUSION')
        changed=core.input_budget_receipts(*args,review_context=context,input_budget=300000)['receipts'][0]
        self.assertEqual(changed['status'],'WITHIN_BUDGET')

    def test_published_source_write_rejected_including_nested_paths(self):
        for path in [self.legacy,self.legacy/'new.json',self.legacy/'evidence/new.json']:
            with self.assertRaisesRegex(ValueError,'read-only'):core.writable_output(path)

    def test_historical_verify_does_not_rewrite_old_validation(self):
        before=revision.file_hashes(self.legacy)
        result=core.verify(self.legacy)
        self.assertEqual(before,revision.file_hashes(self.legacy))
        self.assertEqual(result['policy_status'],'HISTORICAL_POLICY_NOT_CURRENT_REVIEW')

    def test_current_build_verify_policy_and_readonly_validation(self):
        before=core.sha(self.folder/'validation.json')
        r=core.verify(self.folder)
        self.assertEqual(r['status'],'PASS');self.assertEqual(r['policy_version'],revision.VERSION)
        self.assertEqual(before,core.sha(self.folder/'validation.json'))
        self.assertNotEqual(r['policy_fingerprint'],core.read(self.legacy/'manifest.json')['policy_fingerprint'])


if __name__=='__main__':unittest.main()
