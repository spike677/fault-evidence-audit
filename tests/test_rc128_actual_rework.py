import copy
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from rc128_actual_report import (DEFAULT_OUT, EXPECTED_INPUT_SHA, check_diff_hunks,
                                 component_text, make_summary, read_jsonl, validate_data)
from rc128_actual_findings import CASE_NOTES


class ActualReworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=DEFAULT_OUT
        cls.rows=read_jsonl(cls.out/'results.jsonl')
        cls.resources=read_jsonl(cls.out/'resource_audit.jsonl')
        cls.queries=read_jsonl(cls.out/'search_audit.jsonl')
        cls.summary=json.loads((cls.out/'summary.json').read_bytes())

    def test_all_128_have_new_receipts_and_authored_review(self):
        ids={f'RC-{n:03d}' for n in range(1,129)}
        self.assertEqual(ids,{r['task_id'] for r in self.rows})
        self.assertEqual(128,len(self.rows))
        self.assertEqual({s[-3:] for s in ids},set(CASE_NOTES))
        self.assertTrue(all(r['query_ids'] and r['current_review_note'] for r in self.rows))
        self.assertEqual({1:72,2:56},dict(__import__('collections').Counter(r['phase'] for r in self.rows)))

    def test_original_bytes_and_original_pr_links_are_preserved(self):
        self.assertEqual(EXPECTED_INPUT_SHA,sha256((self.out/'inputs/handoff128.jsonl').read_bytes()).hexdigest())
        original=read_jsonl(self.out/'inputs/handoff128.jsonl')
        self.assertEqual(original,[r['original_input'] for r in self.rows])
        v=validate_data(self.out,self.rows,self.resources,self.queries)
        self.assertTrue(v['passed'],v)
        self.assertEqual(21,v['original_pr_clues_re_fetched'])

    def test_unread_capture_never_becomes_semantic_review(self):
        unread=[c for c in self.resources if c['outcome']=='READABLE' and not c['review_selections']]
        self.assertTrue(unread)
        self.assertTrue(all(c['semantic_read_scope']=='CAPTURED_NOT_SEMANTICALLY_REVIEWED' for c in unread))

    def test_quotes_match_exact_saved_representation_including_crlf(self):
        for c in self.resources:
            text=component_text(self.out,c)
            for q in c['review_selections']:
                self.assertEqual(q['selection_sha256'],sha256(text[q['start']:q['end']].encode()).hexdigest(),c['url'])

    def test_truncated_patch_is_not_complete(self):
        complete='diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1,2 +1,2 @@\n keep\n-old\n+new\n'
        self.assertTrue(check_diff_hunks(complete)['returned_hunks_structurally_complete'])
        self.assertFalse(check_diff_hunks(complete.removesuffix('+new\n'))['returned_hunks_structurally_complete'])
        self.assertFalse(check_diff_hunks('<html>login</html>')['returned_hunks_structurally_complete'])
        self.assertFalse(check_diff_hunks(complete)['full_pr_file_set_verified'])

    def test_event_relation_is_not_inherited_from_upstream_negative_labels(self):
        self.assertTrue(any(r['original_input'].get('relation',{}).get('event')=='DIFFERENT_EVENT' for r in self.rows))
        self.assertTrue(all(r['event_relation']=='UNDETERMINED' and not r['weekly_event_confirmed'] for r in self.rows))
        self.assertTrue(all(r['human_decision'] is None and not r['formal_adoption'] and not r['hardware_validated'] for r in self.rows))

    def test_precise_new_negative_index_evidence_is_separate_from_old_dtype_pr(self):
        r=next(r for r in self.rows if r['task_id']=='RC-023')
        self.assertIn('#10579',r['current_review_note'])
        self.assertIn('#4833',r['current_review_note'])
        self.assertIn('默认填充/掩码',r['current_review_note'])
        self.assertEqual('PENDING',r['mode_advice']['decision'])
        self.assertEqual('PUBLIC_CODE_CORROBORATES_PART_OF_RELATION',r['root_evidence_level'])

    def test_new_proposals_are_not_declared_merged(self):
        for url in ['https://github.com/vllm-project/vllm-ascend/pull/9896',
                    'https://github.com/vllm-project/vllm-ascend/pull/16699']:
            body=next(c for c in self.resources if c['url']==url and c['kind']=='BODY')
            self.assertFalse(body['merged'])

    def test_body_resource_budget_and_rounds(self):
        v=validate_data(self.out,self.rows,self.resources,self.queries)
        self.assertLessEqual(v['max_body_resources_per_case_round'],4)
        self.assertLessEqual(max(v['query_rounds']),3)

    def test_missing_case_and_acceptance_are_rejected(self):
        self.assertFalse(validate_data(self.out,self.rows[:-1],self.resources,self.queries)['passed'])
        changed=copy.deepcopy(self.rows)
        changed[0]['human_decision']='ACCEPT'
        self.assertFalse(validate_data(self.out,changed,self.resources,self.queries)['passed'])

    def test_html_json_counts_and_summary_are_identical(self):
        html=(self.out/'report.html').read_text(encoding='utf-8')
        self.assertEqual(128,len(re.findall(r'<article class="case" id="RC-\d{3}">',html)))
        self.assertEqual(make_summary(self.rows,self.resources,self.queries),self.summary)
        self.assertIn('未读正文',html)
        self.assertIn('UNDETERMINED',html)


if __name__=='__main__':unittest.main()
