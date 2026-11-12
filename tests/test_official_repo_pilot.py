"""Source identity and evidence-scope regressions; no network or device calls."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import official_repo_pilot as p


class OfficialSourcePilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=p.registry();cls.results=p.rows(p.PILOT/'pilot_results.jsonl')
        cls.resources=p.rows(p.PILOT/'resource_audit.jsonl');cls.searches=p.rows(p.PILOT/'search_audit.jsonl')

    def test_exact_official_owners_and_repositories(self):
        for url in ['https://github.com/vllm-project/vllm','https://github.com/deepseek-ai/DeepSeek-R1','https://gitcode.com/cann/ops-nn/pull/10622']:
            self.assertTrue(p.primary_source(url,self.registry))

    def test_brand_words_in_personal_repo_not_primary(self):
        for url in ['https://github.com/somebody/vllm-ascend','https://github.com/somebody/cann','https://gitcode.com/somebody/ops-nn']:
            self.assertFalse(p.primary_source(url,self.registry))

    def test_canonical_pr_allowed_with_personal_contributor_fork(self):
        self.assertTrue(p.primary_source('https://github.com/vllm-project/vllm-ascend/pull/12123',self.registry))
        self.assertFalse(p.primary_source('https://github.com/ZT-AIA/vllm-ascend',self.registry))

    def test_blogs_and_similar_hostnames_not_primary(self):
        self.assertFalse(p.primary_source('https://blog.gitcode.com/cann/ops-nn',self.registry))
        self.assertFalse(p.primary_source('https://github.com.example.org/vllm-project/vllm',self.registry))

    def test_raw_and_api_links_keep_same_verified_owner(self):
        a=p.repository_key('https://api.github.com/repos/Ascend/op-plugin/contents/a?ref=abc')
        b=p.repository_key('https://raw.githubusercontent.com/Ascend/op-plugin/abc/a')
        self.assertEqual(a,b);self.assertTrue(p.primary_source('https://raw.githubusercontent.com/Ascend/op-plugin/abc/a',self.registry))

    def test_github_cann_404_not_equivalent_to_gitcode_missing(self):
        self.assertFalse(p.primary_source('https://github.com/cann/ops-nn',self.registry))
        self.assertTrue(p.primary_source('https://gitcode.com/cann/ops-nn',self.registry))
        self.assertTrue(p.receipt('REPO-CANN-GITHUB')['result']['isError'])

    def test_multifile_diff_validated_per_file_not_as_one_hunk_stream(self):
        text=(p.PILOT/'evidence/side/CANN-10622.diff').read_text(encoding='utf-8')
        parts=p.split_diff(text)
        self.assertEqual(len(parts),2);self.assertTrue(all(x['hunks_complete']for x in parts))
        self.assertEqual(sum(l.startswith('+')and not l.startswith('+++')for l in text.splitlines()),7)

    def test_cut_hunk_rejected(self):
        text=(p.PILOT/'evidence/side/CANN-10622.diff').read_text(encoding='utf-8')
        parts=p.split_diff('\n'.join(text.splitlines()[:-1]))
        self.assertFalse(parts[-1]['hunks_complete'])

    def test_query_empty_is_bounded_not_root_negative(self):
        empty=[x for x in self.searches if x['outcome']=='NO_MATCH_IN_THIS_QUERY']
        self.assertTrue(empty)
        self.assertTrue(all(x['receipt']and not x['exhaustive_repository_review']for x in empty))
        self.assertEqual(next(r for r in self.results if r['task_id']=='RC-009')['event_relation'],'UNDETERMINED')

    def test_web_block_and_side_success_both_retained(self):
        cann=next(r for r in self.resources if r['resource_id']=='CANN10622')
        self.assertEqual([a['status']for a in cann['capture_attempts']],['FETCH_BLOCKED','BODY_AND_RAW_DIFF_READ'])
        self.assertTrue(all(not r['primary_source']for r in self.resources if r['capture_status']=='FETCH_BLOCKED_IN_WEB_TOOL'))

    def test_100_concurrency_does_not_identify_event(self):
        c=next(r for r in self.results if r['task_id']=='RC-003')
        self.assertIn('DeepSeek-V4',c['finding']);self.assertEqual(c['event_relation'],'UNDETERMINED')
        self.assertFalse(c['confirmed_root_cause'])

    def test_contract_difference_not_math_equivalent_order_mode(self):
        c=next(r for r in self.results if r['task_id']=='RC-111')
        self.assertIn('M019',c['mode_boundary']);self.assertIn('改变数学含义',c['mode_boundary'])
        self.assertFalse(c['formal_adoption'])

    def test_final_patch_not_outdated_bot_comment_used_for_tests(self):
        t=p.structured('SIDE-PR12123-FILE-3')['patch']['patch']
        self.assertIn('atol=1e-4, rtol=5e-3',t)
        c=next(r for r in self.results if r['task_id']=='RC-030')
        self.assertIn('独立致因未隔离',c['failed_relation']);self.assertIn('q未采到',c['failed_relation'])

    def test_verifier_read_only_and_data_hashes(self):
        before=p.sha(p.PILOT/'validation.json')
        self.assertEqual(p.verify()['status'],'PASS')
        self.assertEqual(p.sha(p.PILOT/'validation.json'),before)


if __name__=='__main__':unittest.main()
