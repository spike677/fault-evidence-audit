"""Actual-receipt consistency plus synthetic source-gate regressions; no device."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import rc128_field_audit as audit
import rc128_review as core
import official_repo_pilot as pilot
from rc128_field_decisions import notes


class OfficialFieldAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=audit.OUTPUT;cls.data=audit.payload(cls.folder)
        cls.resources={r['resource_id']:r for r in cls.data['resource_audit']}
        cls.audits={a['task_id']:a for a in cls.data['field_audits']}

    def test128_actual_processing_not128_confirmed_roots(self):
        self.assertEqual(len(notes()),128)
        self.assertTrue(all(a['actual_search_ids']or a['resource_ids']for a in self.audits.values()))
        self.assertTrue(all(not a['root_independently_confirmed']and a['remaining_gaps']for a in self.audits.values()))

    def test_no_event_accept_or_adoption_inference(self):
        for r in self.data['evidence_relations']:
            self.assertEqual(r['event_relation'],'UNDETERMINED')
            self.assertFalse(r['manual_accept_created'])
        for f in self.data['public_findings']:
            self.assertFalse(f['weekly_root_confirmed']);self.assertFalse(f['hardware_validated'])

    def test_canonical_repo_not_keyword_or_personal_fork(self):
        reg=self.data['repository_registry']
        self.assertTrue(pilot.primary_source('https://gitcode.com/cann/ops-nn/pull/6170',reg))
        for url in ['https://github.com/unrelated/cann/issues/1','https://gitcode.com/somebody/ops-nn/pull/6170',
                    'https://gitcode.com.evil.test/cann/ops-nn/pull/6170','http://gitcode.com/cann/ops-nn']:
            self.assertFalse(pilot.primary_source(url,reg))

    def test_all21_original_pr_urls_acquired_after_web_block(self):
        original=core.read(self.folder/'evidence/resource_index.json')['resources']
        by={r['url']:r for r in self.resources.values()}
        self.assertEqual(len(original),21)
        for r in original:
            self.assertIn(r['url'],by);self.assertTrue(by[r['url']].get('raw_diff'))
        prior=by['https://gitcode.com/cann/ops-transformer/pull/8752']
        self.assertTrue(any('BLOCKED'in a['status']for a in prior['capture_attempts']))
        self.assertTrue(any(a['status']=='SUCCESS'for a in prior['capture_attempts']))

    def test_one_snapshot_shared_by_cases_without_dropping_sources(self):
        r=self.resources['GC-cann-ops-transformer-8005']
        self.assertEqual(r['task_ids'],['RC-029','RC-060'])
        rels=[e for e in self.data['evidence_relations']if e['resource_id']==r['resource_id']]
        self.assertEqual({e['task_id']for e in rels},{'RC-029','RC-060'})
        self.assertEqual(len(self.resources),len({r['url']for r in self.resources.values()}))

    def test_raw_same_diff_not_independent_corroboration(self):
        a=self.resources['GC-cann-ops-transformer-12509'];b=self.resources['GC-cann-ops-transformer-12716']
        self.assertNotEqual(a['url'],b['url'])
        self.assertEqual(core.sha(self.folder/a['raw_diff']),core.sha(self.folder/b['raw_diff']))
        self.assertIn('同Diff',self.audits['RC-008']['assessment'])

    def test_deleted_file_diff_counts_and_partial_hunks(self):
        text='diff --git a/a.py b/a.py\n--- a/a.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-a\n-b\n'
        r=audit.split_raw_diff(text)[0]
        self.assertEqual(r['filename'],'a.py');self.assertTrue(r['deleted']);self.assertTrue(r['hunks_complete'])
        self.assertFalse(audit.split_raw_diff(text.replace('-b\n',''))[0]['hunks_complete'])

    def test_query_round_limit_and_page_dedup(self):
        self.assertTrue(audit.query_limits(self.data['search_audit']))
        bad=[dict(evidence_cycle_by_task={'RC-001':1})for _ in range(5)]
        self.assertFalse(audit.query_limits(bad))
        self.assertFalse(audit.query_limits([dict(evidence_cycle_by_task={'RC-001':4})]))
        pages=[q for q in self.data['search_audit']if q['query_id']=='SIDE-SEARCH-24']
        self.assertEqual(len(pages),1);self.assertEqual(pages[0]['pages_observed'],[1,2,3])

    def test_unobserved_total_not_claimed_zero(self):
        q=next(q for q in self.data['search_audit']if q['query_id']=='SIDE-SEARCH-16')
        self.assertIsNone(q['candidate_count']);self.assertEqual(q['outcome'],'NO_CANDIDATES_VISIBLE_UI_TOTAL_UNCONFIRMED')
        self.assertFalse(q['exhaustive_repository_review'])

    def test_native_empty_query_not_gitcode_absence(self):
        q=next(q for q in self.data['search_audit']if q['query_id']=='SEARCH-R1-RC-105')
        self.assertEqual(q['outcome'],'NO_MATCH_IN_THIS_QUERY')
        self.assertIn('not absence',q['result_scope'])

    def test_comparison_reuse_retains_fetch_target_and_case_link(self):
        r=self.resources['GH-PR-vllm-project-vllm-ascend-10507']
        self.assertEqual(r['collection_task_ids'],['RC-045'])
        self.assertEqual(r['additional_comparison_task_ids'],['RC-021'])
        self.assertEqual(set(r['task_ids']),{'RC-021','RC-045'})
        self.assertIn(r['resource_id'],self.audits['RC-021']['resource_ids'])

    def test_6827_description_diff_conflict_not_invented_prefill_kernel(self):
        a=self.audits['RC-026'];self.assertEqual(a['processing_status'],'SOURCE_DESCRIPTION_DIFF_CONFLICT')
        r=self.resources['GH-PR-vllm-project-vllm-ascend-6827']
        self.assertEqual((r['reviewed_file_count'],r['changed_file_count']),(1,4))
        patch=(self.folder/r['reviewed_patches'][0]['file']).read_text(encoding='utf8')
        self.assertIn('split_qkv_rmsnorm_rope_kernel[grid]',patch)
        self.assertNotIn('split_qkv_rmsnorm_rope_prefill_kernel',patch)

    def test_8005_parameter_change_not_stage_or_scale_axes_proof(self):
        r=self.resources['GC-cann-ops-transformer-8005'];t=(self.folder/r['raw_diff']).read_text(encoding='utf8')
        self.assertEqual(t.count('+                        deScaleVValue, deScaleVValue);'),4)
        cond=next(c for c in self.data['conditions']if c.get('task_id')=='RC-029'and c['condition_id']=='scale_structure')
        self.assertEqual(cond['semantic_applicability']['status'],'UNKNOWN')
        self.assertIn('完整对象',self.audits['RC-029']['remaining_gaps'][0])

    def test_ctrl_init_specific_code_not_a05_or_memory_init(self):
        r=self.resources['GC-cann-opbase-279'];t=(self.folder/r['raw_diff']).read_text(encoding='utf8')
        self.assertEqual(t.count('+    set_ctrl(newCtrl);'),2)
        self.assertIn('ISA',self.audits['RC-010']['remaining_gaps'][0])
        self.assertIn('不等同同步或内存初始化',self.audits['RC-010']['remaining_gaps'][0])

    def test_inactive_mlp_and_issue_title_not_initialization_proof(self):
        self.assertIn('未执行MLP不证明未初始化',self.audits['RC-023']['remaining_gaps'][0])
        r=self.resources['GC-ISSUE-cann-ops-nn-90']
        self.assertIn('清零操作在算子执行前已完成',r['body_transcript'])
        self.assertIn('维护者',r['notes'][0])

    def test_deterministic_log_failure_not_configuration_propagation_bug(self):
        r=self.resources['GC-ISSUE-Ascend-pytorch-5929']
        self.assertIn('与配置是否透传无关',r['body_transcript'])
        self.assertIn('没有取得原buffer',self.audits['RC-105']['assessment'])

    def test_cpu_replay_not_npu_validation(self):
        r=self.resources['GC-ISSUE-Ascend-pytorch-5951'];self.assertIn('CPU',r['notes'][0])
        self.assertIn('未执行',r['notes'][0]);self.assertFalse(r['hardware_validated'])

    def test_two_deepspeed_fixes_not_one_cause(self):
        fs=[f for f in self.data['public_findings']if 'RC-122'in f['task_ids']]
        self.assertEqual(len(fs),2)
        self.assertIn('rank',fs[0]['finding']);self.assertIn('wait_stream',fs[1]['finding'])
        self.assertFalse(any(f['weekly_root_confirmed']for f in fs))

    def test_exact_excerpt_scope_rejects_missing_locator(self):
        with tempfile.TemporaryDirectory()as tmp:
            p=Path(tmp);(p/'x').write_text('line 1\nexact\nline 3\n',encoding='utf8',newline='')
            e=audit.exact_excerpt(p,'X','x','exact',context=0)
            self.assertEqual(e['quote'],'exact');self.assertEqual(e['line_start'],2)
            with self.assertRaisesRegex(ValueError,'Locator missing'):audit.exact_excerpt(p,'X','x','absent')

    def test_oversize_full_envelope_blocks_instead_of_truncates(self):
        f=self.folder;d=self.data;inputs=core.rows(f/'sources/original/handoff.jsonl')[:1]
        b=core.input_budget_receipts(inputs,d['baseline'],d['definitions'],f,{'RC-001':{'proof':'末尾'+('X'*160001)}})
        r=b['receipts'][0];self.assertEqual(r['status'],'BLOCKED');self.assertEqual(r['reason'],'INPUT_TOO_LARGE')
        self.assertGreater(r['serialized_input_chars'],160000);self.assertFalse(b['automatic_truncation'])

    def test_default_and_nested_output_cannot_overwrite_history(self):
        for old in [audit.SOURCE,audit.PILOT,core.LEGACY_BUNDLE]:
            for p in [old,old/'new']:
                with self.assertRaisesRegex(ValueError,'read-only'):audit.independent_output(p,audit.SOURCE)

    def test_manifest_current_and_history_readonly(self):
        before=core.sha(audit.SOURCE/'validation.json');r=core.verify(audit.SOURCE)
        self.assertEqual(r['policy_status'],'HISTORICAL_POLICY_NOT_CURRENT_REVIEW')
        self.assertEqual(before,core.sha(audit.SOURCE/'validation.json'))
        self.assertTrue(audit.historical_unchanged(self.folder));self.assertEqual(audit.verify(self.folder)['status'],'PASS')


if __name__=='__main__':unittest.main()
