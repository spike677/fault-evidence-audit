"""Trusted root preservation, exact evidence scopes and publication integration."""
import copy
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import rc128_trusted_report as report
from rc128_report_layout import verify as verify_migration
from rc128_review import writable_output
from rc128_component_reader import hunk_signatures


class TrustedReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=report.read_jsonl(report.CURRENT/'results.jsonl')
        cls.components=report.read_jsonl(report.EVIDENCE/'component_reviews.jsonl')
        cls.notes=report.read_jsonl(report.EVIDENCE/'case_review_notes.jsonl')
        cls.by={r['task_id']:r for r in cls.rows}

    def test_all_original_bytes_roots_and_identities_survive(self):
        self.assertEqual(report.INPUT_SHA,sha256((report.INPUTS/'handoff128.jsonl').read_bytes()).hexdigest())
        self.assertEqual(128,len(self.by))
        self.assertEqual(report.read_jsonl(report.INPUTS/'handoff128.jsonl'),[r['original_input'] for r in self.rows])
        self.assertTrue(report.validate(self.rows,self.components)['passed'])
        self.assertEqual(110,sum(bool(r['trusted_root']['original_text'].strip()) for r in self.rows))

    def test_lack_of_code_does_not_downgrade_the_original_cause(self):
        original=self.by['RC-001']['original_input']
        for status in report.CODE_LABELS:
            note=copy.deepcopy(self.notes[0]);note['code_assessment']['status']=status
            root=report.adopt_root(original,note)
            self.assertEqual(original['fault']['reported_root_cause'],root['adopted_text'])
            self.assertEqual('ADOPTED_WEEKLY',root['status'])

    def test_public_pr_cannot_fill_an_empty_cause(self):
        original=copy.deepcopy(self.by['RC-003']['original_input'])
        note=copy.deepcopy(self.notes[2]);note['code_assessment'].update(status='SUPPORTED',explanation='similar PR')
        self.assertEqual('',report.adopt_root(original,note)['adopted_text'])
        original['dts_facts']=[{'root_cause':'unrelated source','read_status':'READABLE'}]
        note['adopt_from_source_id']='RC-003:dts_facts:0'
        note['source_consistency']['status']='SCOPE_DIFFERENCE'
        with self.assertRaises(ValueError):report.adopt_root(original,note)

    def test_explicit_consistent_summary_can_fill_only_empty_original(self):
        raw=copy.deepcopy(self.by['RC-003']['original_input'])
        raw['dts_facts']=[{'root_cause':'explicit consistent summary'}]
        note=copy.deepcopy(self.notes[2]);note['source_consistency']['status']='CONSISTENT'
        note['adopt_from_source_id']='RC-003:dts_facts:0'
        self.assertEqual('explicit consistent summary',report.adopt_root(raw,note)['adopted_text'])
        raw['fault']['reported_root_cause']='keep original'
        self.assertEqual('keep original',report.adopt_root(raw,note)['adopted_text'])

    def test_source_conflicts_are_exposed_without_replacing_the_weekly_cause(self):
        r=self.by['RC-030']
        self.assertEqual('SCOPE_DIFFERENCE',r['source_consistency']['status'])
        self.assertTrue(r['trusted_sources'])
        self.assertEqual(r['original_input']['fault']['reported_root_cause'],r['trusted_root']['adopted_text'])
        self.assertEqual('SOURCE_PAYLOAD_CONFLICT',self.by['RC-069']['source_consistency']['status'])
        self.assertTrue(all(not s['internal_original_read_in_this_stage'] for r in self.rows for s in r['trusted_sources']))

    def test_bad_root_replacement_and_acceptance_are_rejected(self):
        changed=copy.deepcopy(self.rows);changed[0]['trusted_root']['adopted_text']='made up public root'
        self.assertFalse(report.validate(changed,self.components)['passed'])
        changed=copy.deepcopy(self.rows);changed[0]['human_decision']='ACCEPT'
        self.assertFalse(report.validate(changed,self.components)['passed'])

    def test_unbacked_code_link_is_rejected(self):
        changed=copy.deepcopy(self.rows)
        changed[0]['code_assessment'].update(status='SUPPORTED',accepted_urls=['https://github.com/not-captured/pull/1'])
        self.assertFalse(report.validate(changed,self.components)['passed'])

    def test_153_components_have_explicit_scopes_not_whole_file_claims(self):
        self.assertEqual(153,len(self.components))
        self.assertEqual({'DIFF':39,'PATCH':57,'SOURCE':57},dict(__import__('collections').Counter(c['kind'] for c in self.components)))
        self.assertTrue(all(c['reason'] and c['case_scope_review'] and not c['full_file_semantic_review'] for c in self.components))
        self.assertTrue(all(c['exact_read_ranges'] or c['shared_review_resources'] for c in self.components))
        self.assertTrue(all(c['exact_read_ranges'] for c in self.components if c['kind']=='SOURCE'))
        bad=copy.deepcopy(self.components);bad[0]['disposition']='PENDING'
        self.assertFalse(report.validate(self.rows,bad)['passed'])

    def test_patch_proof_does_not_hide_unique_commits_or_truncation(self):
        patch='diff --git a/a b/a\n@@ -1 +1 @@\n-before\n+after\n'
        self.assertEqual(hunk_signatures(patch),hunk_signatures('From envelope\n'+patch+'-- \nmail trailer\n'))
        self.assertNotEqual(hunk_signatures(patch),hunk_signatures(patch+patch.replace('after','different')))
        with self.assertRaises(ValueError):hunk_signatures(patch.removesuffix('+after\n'))
        # Five early sharing assumptions failed stronger proof and stay corrected.
        fixes=json.loads((report.EVIDENCE/'review_corrections.json').read_bytes())['corrections']
        self.assertEqual(5,len(fixes))
        shared={c['resource_id'] for c in self.components if c['disposition']=='PATCH_HUNKS_SHARED'}
        self.assertFalse(shared & {f['resource_id'] for f in fixes})

    def test_new_corroboration_has_precise_scope_and_event_limit(self):
        deq=self.by['RC-030']['code_assessment']
        self.assertEqual('PARTIAL',deq['status']);self.assertIn('9119',str(deq['accepted_urls']))
        self.assertIn('安全Brcb',deq['explanation'])
        self.assertEqual('UNDETERMINED',self.by['RC-062']['public_code_event_relation'])
        self.assertEqual('SUPPORTED',self.by['RC-094']['code_assessment']['status'])
        self.assertTrue(any('85aa6c88' in str(f) for f in self.by['RC-094']['followup_evidence']))

    def test_mode_advice_comes_from_current_review_not_prior_pending_count(self):
        self.assertEqual('COVERED',self.by['RC-017']['mode_assessment']['decision'])
        self.assertEqual('M025',self.by['RC-017']['original_mode_comparisons'][0]['mode_id'])
        self.assertEqual('UNFROZEN_STAGING',json.loads((report.INPUTS/'baseline_30_modes.json').read_bytes())['baseline_status'])
        self.assertTrue(all(not r['mode_assessment']['formal_adoption'] for r in self.rows))

    def test_current_html_json_and_statistics_are_identical(self):
        html=(report.CURRENT/'report.html').read_text(encoding='utf8')
        payload=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',html,re.S)[1])
        self.assertEqual(set(self.by),set(payload))
        for r in self.rows:self.assertEqual(r['code_assessment']['status'],payload[r['task_id']]['code'])
        self.assertEqual(report.summarize(self.rows,self.components),json.loads((report.EVIDENCE/'summary.json').read_bytes()))
        self.assertEqual(['README.md','report.html','results.jsonl'],sorted(p.name for p in report.CURRENT.iterdir() if p.is_file()))

    def test_every_archived_byte_matches_before_migration(self):
        result=verify_migration()
        self.assertTrue(result['passed']);self.assertEqual(4486,result['tracked_files'])
        self.assertFalse(result['historical_manifests_rewritten'])
        with self.assertRaises(ValueError):writable_output(report.SOURCE/'validation.json')

    def test_budget_is_preserved_without_emitting_model_or_device_work(self):
        policy=json.loads((report.EVIDENCE/'policy.json').read_bytes())
        self.assertEqual(160000,policy['model_input_budget_chars'])
        self.assertEqual(0,policy['model_tasks_emitted'])
        self.assertTrue(all(r['human_decision'] is None and not r['formal_adoption'] and not r['hardware_validated'] for r in self.rows))

    def test_policy_change_does_not_let_an_old_report_pass_as_current(self):
        with patch.object(report,'VERSION','different-policy'):
            with self.assertRaisesRegex(ValueError,'stale'):report.verify()


if __name__=='__main__':unittest.main()
