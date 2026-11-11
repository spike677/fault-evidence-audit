"""Offline data-contract and regression checks; no model, browser or device."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import rc128_review as review
import rc128_decisions as decisions

BUNDLE=ROOT/'reports/rc128-evidence-review-20261111'


class ReviewContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results=review.rows(BUNDLE/'results.jsonl')
        cls.failures=review.rows(BUNDLE/'failure_relations.jsonl')
        cls.conditions=review.rows(BUNDLE/'condition_relations.jsonl')
        cls.technical=review.read(BUNDLE/'technical_cases.json')['cases']

    def test_original_128_and_source_group_denominators(self):
        self.assertEqual([r['task_id']for r in self.results],[f'RC-{i:03}'for i in range(1,129)])
        self.assertEqual(sum(review.read(BUNDLE/'summary.json')['source_groups'].values()),128)
        self.assertEqual([r['original_input']for r in self.results],review.rows(BUNDLE/'sources/original/handoff.jsonl'))

    def test_code_clue_resource_dedup_keeps_all_links(self):
        resources=review.read(BUNDLE/'evidence/resource_index.json')['resources']
        self.assertEqual(len(resources),21)
        for r in self.results:
            for clue in r['original_input']['public_code_clues']:
                item=next(x for x in resources if x['url']==clue['link'])
                self.assertIn(r['task_id'],item['task_ids'])

    def test_missing_dts_body_not_faked_by_readable_status(self):
        r=self.results[0]
        self.assertEqual(r['original_input']['dts_facts'][0]['read_status'],'READABLE')
        self.assertTrue(any(q['code']=='UPSTREAM_READABLE_BODY_NOT_TRANSFERRED'for q in r['source_quality_issues']))
        self.assertFalse(r['root_cause']['independently_confirmed'])

    def test_operators_or_mechanisms_not_event_identity(self):
        for r in self.results:
            for a in r['source_associations']:
                self.assertEqual(a['event_relation'],'UNDETERMINED')
        self.assertGreater(sum(a['mechanism_relation']=='DIFFERENT_MECHANISM'for r in self.results for a in r['source_associations']),0)

    def test_no_auto_accept_no_device_or_adoption(self):
        for r in self.results:
            for key in ['manual_accept_created','formal_adoption','weekly_event_confirmed','hardware_validated']:
                self.assertFalse(r[key])

    def test_forward_negative_index_not_backward_dtype(self):
        r=self.results[22]
        self.assertIn('abs',r['root_cause']['conclusion'])
        t=next(t for t in self.technical if t['technical_case_id']=='TC-GRADPROBS-DTYPE')
        self.assertEqual(t['contract'],'METADATA_OWNER')
        self.assertFalse(t['weekly_event_confirmed'])
        self.assertEqual(r['source_associations'][-1]['mechanism_relation'],'DIFFERENT_MECHANISM')

    def test_reduction_stride_not_input_alignment_or_address_overflow(self):
        f=next(f for f in self.failures if f.get('technical_case_id')=='TC-DEQUANT-REDUCE-STRIDE')
        self.assertEqual(192%64,0)
        self.assertEqual(96//8-(96//64)*8,4)
        self.assertIn('UbFactorDimy',f['semantic_detail']['q_role'])
        self.assertFalse(f['semantic_detail']['independent_component_causality_isolated'])
        self.assertFalse(any(c.get('task_id')=='RC-030'and c['condition_id']=='1.3.2'for c in self.conditions))

    def test_gather_element_count_not_itemsize_or_enum_size(self):
        f=next(f for f in self.failures if f.get('technical_case_id')=='TC-GATHER-SCALAR-COUNT')
        self.assertIn('itemsize',f['semantic_detail']['actual'])
        self.assertIn('1536',f['semantic_detail']['consumer'])
        self.assertNotIn('sizeof(enum)',f['semantic_detail']['actual'])

    def test_multisubproblem_masks_and_dtypes_do_not_leak(self):
        fs=[f for f in self.failures if f.get('task_id')=='RC-104']
        self.assertEqual(len(fs),4)
        for c in [c for c in self.conditions if c.get('task_id')=='RC-104']:
            self.assertEqual(len(c['issue_scope_map']),1)
            if c['condition_id']=='enum_dtype':self.assertEqual(c['issue_scope_map'],['RC-104:REL-01'])
            if c['condition_id']=='enum_mask':self.assertEqual(c['issue_scope_map'],['RC-104:REL-02'])

    def test_output_inf_is_not_input_nan_and_internal_random_not_api_switch(self):
        self.assertFalse(any(c.get('task_id')in ['RC-004','RC-075','RC-084']and c['condition_id']=='1.7.2'for c in self.conditions))
        self.assertFalse(any(c.get('task_id')=='RC-043'and c['condition_id']=='1.C.5'for c in self.conditions))

    def test_initialized_word_conflict_preserved(self):
        text=self.results[127]['original_input']['fault']['reported_root_cause']
        self.assertIn('为初始化',text)
        self.assertNotIn('为未初始化',text)
        self.assertIn('转录冲突',self.results[127]['root_cause']['conclusion'])

    def test_original42_uses_actual_typora_source_not_repo_copy(self):
        d=review.read(BUNDLE/'condition_definitions.json')['definitions']
        api=[x for x in d if x['system']=='API42'];v4=[x for x in d if x['system']=='V4']
        self.assertEqual(len(api),42);self.assertEqual(len(v4),55)
        self.assertEqual(api[0]['source_sha256'],review.sha(BUNDLE/'sources/original/api42_trigger_library_original.md'))
        self.assertNotEqual(api[0]['source_sha256'],review.sha(BUNDLE/'sources/original/trigger_library.md'))

    def test_wiki_embedded_commit_was_resolved_not_ignored(self):
        r=self.results[93]
        self.assertIn('scaling_factor',r['root_cause']['conclusion'])
        t=next(t for t in self.technical if t['technical_case_id']=='TC-ROPE-CACHE-EXTENT')
        self.assertIn('RC-094',t['related_task_ids'])
        self.assertTrue(any(x.startswith('GH-ROPE-a3a3d38')for x in t['evidence_ids']))
        self.assertFalse(t['weekly_event_confirmed'])

    def test_hidden_code_hint_preserves_source_and_deduplicates(self):
        record={'confirmed_internal_facts':[{'fix':'bugfix PR a3a3d38'},{'fix':'bugfix PR a3a3d38'}],
                'description':'员工30045269，日期20261111',
                'public_code_clues':[{'link':'https://gitcode.com/cann/ops-nn/pull/1'}]}
        leads=review.discover_code_leads(record)
        commits=[x for x in leads if x['kind']=='COMMIT_HINT']
        self.assertEqual(len(commits),1)
        self.assertEqual(commits[0]['value'],'a3a3d38')
        self.assertEqual(len(commits[0]['source_pointers']),2)
        self.assertEqual(commits[0]['attribution'],'UNVERIFIED')
        self.assertEqual(len([x for x in leads if x['kind']=='URL']),1)

    def test_draft_fix_not_reported_as_merged(self):
        d=review.unpack_tool(review.read(BUNDLE/'evidence/github/GH-GRAPH-16482.json'))
        self.assertTrue(d['pull_request']['draft']);self.assertFalse(d['pull_request']['merged'])
        t=next(t for t in self.technical if t['technical_case_id']=='TC-GRAPH-LIVE-REDUCTION')
        self.assertTrue(any('未合并' in g for g in t['unresolved_gaps']))

    def test_patch_mid_hunk_cut_is_detected(self):
        whole='@@ -1,2 +1,2 @@\n a\n-b\n+c'
        self.assertTrue(review.check_patch_hunks(whole))
        self.assertFalse(review.check_patch_hunks(whole.rsplit('\n',1)[0]))

    def test_oversize_serialized_input_blocks_without_cutting_tail(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);p=root/'sources/original';p.mkdir(parents=True)
            for name in ['api42_trigger_library_original.md','precision_trigger_knowledge_v4.md']:(p/name).write_text('合成定义\n',encoding='utf-8')
            record={'task_id':'RC-SYNTHETIC','fault':{'reported_root_cause':'a'*170000+'末尾关键结论'}}
            before=copy.deepcopy(record)
            result=review.input_budget_receipts([record],[],[],root)
            self.assertEqual(result['receipts'][0]['status'],'BLOCKED')
            self.assertEqual(result['receipts'][0]['reason'],'INPUT_TOO_LARGE')
            self.assertEqual(record,before)
            self.assertFalse(result['automatic_truncation'])

    def test_input_budget_includes_instructions_and_full_knowledge(self):
        receipt=review.read(BUNDLE/'input_budget_receipts.json')
        self.assertTrue(receipt['instructions_included'])
        self.assertTrue(receipt['serialized_data_included'])
        self.assertEqual(len(receipt['receipts']),128)
        self.assertGreater(max(r['serialized_input_chars']for r in receipt['receipts']),100000)
        self.assertTrue(all(r['status']=='WITHIN_BUDGET'for r in receipt['receipts']))

    def test_same_ids_changed_input_cannot_reuse_curated_results(self):
        with tempfile.TemporaryDirectory()as tmp:
            b=Path(tmp);p=b/'sources/original';p.mkdir(parents=True)
            shutil.copyfile(BUNDLE/'input_manifest.json',b/'input_manifest.json')
            (p/'handoff.jsonl').write_text('{"task_id":"RC-001","changed":true}\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'different input SHA'):review.build(b)

    def test_unique_record_count_not_label_or_subproblem_sum(self):
        s=review.read(BUNDLE/'summary.json')
        self.assertEqual(s['unique_task_count'],128)
        self.assertGreater(s['weekly_subproblem_assessments'],128)
        self.assertGreater(s['failure_relation_rows'],s['weekly_subproblem_assessments'])
        self.assertEqual(sum(s['weekly_draft_actions'].values()),128)

    def test_exact_quote_changes_are_rejected(self):
        with tempfile.TemporaryDirectory()as tmp:
            target=Path(tmp)/'bundle';shutil.copytree(BUNDLE,target)
            doc=review.read(target/'evidence/quote_index.json');doc['anchors'][0]['quote']='合成篡改文本'
            review.write(target/'evidence/quote_index.json',doc)
            with self.assertRaisesRegex(ValueError,'all_exact_quotes_resolve'):review.verify(target)


if __name__=='__main__':unittest.main()
