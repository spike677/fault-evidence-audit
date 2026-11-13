"""Offline adapter integration; captured fixtures, no production state or device."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import rc128_mechanism_review as r4
import rc128_field_audit as r3


class MechanismReviewIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = r3.payload(r3.OUTPUT)
        cls.analyses, cls.extra, cls.rules, cls.corrections = r4.analyses_for(cls.data, r3.OUTPUT)
        cls.evidence_ids = {e['evidence_id'] for e in cls.data['quotes'] + cls.data['field_excerpts'] + cls.extra}

    def test_every_original_case_attempted_with_native_cards(self):
        self.assertEqual({a['task_id'] for a in self.analyses}, {r['task_id'] for r in self.data['results']})
        self.assertEqual(r4.analysis_errors(self.analyses, self.rules, self.evidence_ids), [])

    def test_original42_and_v4_independent_frozen_definitions(self):
        api = [r for r in self.rules if r['scheme'] == 'ORIGINAL42']
        v4 = [r for r in self.rules if r['scheme'] == 'V4']
        self.assertEqual((len(api), len(v4)), (42, 31))
        self.assertEqual(len({c['id'] for r in v4 for c in r['constructions']}), 55)
        self.assertEqual({r['source_sha256'] for r in api}, {'69f6cae46a021b5f242cd6bdf6600618bf63e2de7c87122c2187c90d08837a82'})
        self.assertEqual({r['source_sha256'] for r in v4}, {'e4aafbd2aaa6054e2f721b3d23f8808670ea97ca65bdf6082188a280c67f3193'})

    def test_weekly_and_public_do_not_inherit_event_or_root(self):
        for tid in r4.PILOT_IDS:
            aa = [a for a in self.analyses if a['task_id'] == tid]
            self.assertEqual({a['entity_type'] for a in aa}, {'WEEKLY_SOURCE_DECLARATION', 'INDEPENDENT_PUBLIC_TECHNICAL_CASE'})
            self.assertTrue(all(not a['weekly_event_confirmed'] for a in aa))
            public_ids = {c['claim_id'] for a in aa if a['entity_type'].startswith('INDEPENDENT') for c in a['source_claims']}
            self.assertTrue(all(not public_ids.intersection(a['mechanism']['source_claim_ids']) for a in aa if a['entity_type'].startswith('WEEKLY')))

    def test_weekly_pilot_uses_original_claim_not_old_public_inference(self):
        weekly = [a for a in self.analyses if a['task_id'] == 'RC-030' and a['entity_type'].startswith('WEEKLY')]
        self.assertEqual(len(weekly), 1)
        original = next(r for r in self.data['results'] if r['task_id'] == 'RC-030')['original_input']['fault']['reported_root_cause']
        self.assertEqual(weekly[0]['mechanism']['statement'], original)
        self.assertNotIn('12123', weekly[0]['mechanism']['statement'])

    def test_proposed_test_does_not_supply_positive_label(self):
        d = self.rules[0]
        candidate = dict(system='API42', condition_id=d['id'], semantic_applicability='APPLICABLE', association_basis='PROPOSED_TEST_ONLY')
        labels, links, scenarios, _ = r4.select_conditions([candidate], self.rules, 'fact', 'analysis')
        self.assertEqual(labels[0]['semantic_applicability'], 'UNKNOWN')
        self.assertFalse(links or scenarios)

    def test_logic_hypothesis_remains_distinct_from_source_declaration(self):
        aa = [a for a in self.analyses if a['evidence_level'] == 'logic_hypothesis']
        self.assertTrue(aa)
        self.assertTrue(all(a['mechanism_chain']['basis'] == 'HYPOTHESIS' for a in aa))
        self.assertTrue(all(not a['mechanism_chain']['observed_change'].startswith('来源声明：') for a in aa))
        self.assertTrue(all(c['basis'] == 'SOURCE_DECLARED' for a in aa for c in a['source_claims']))

    def test_multimounted_construction_needs_explicit_class(self):
        labels, links, _, notes = r4.select_conditions([dict(system='V4', condition_id='enum_dtype', status='candidate')], self.rules, 'f', 'a')
        self.assertFalse(labels or links)
        self.assertEqual(notes[0]['status'], 'UNKNOWN')

    def test_mode_and_device_statuses_cannot_be_laundered_by_card_readiness(self):
        self.assertTrue(any(c['status'] == 'DESIGN_READY' for a in self.analyses for c in a['design_cards']))
        for a in self.analyses:
            self.assertEqual(a['mode_decision']['action'], 'PENDING')
            self.assertFalse(a['formal_adoption'] or a['manual_accept_created'] or a['hardware_validated'])
            for c in a['design_cards']:
                self.assertEqual(c['execution_status'], 'NOT_RUN')
                self.assertFalse(c['execution_implemented'])

    def test_budget_contains_instruction_full_rules_and_selected_evidence(self):
        pp = [a for a in self.analyses if a['task_id'] in r4.PILOT_IDS]
        b = r4.budget_receipts(r3.OUTPUT, self.data, pp, self.extra)
        self.assertEqual(len(b['receipts']), len(pp))
        self.assertTrue(all(r['status'] == 'WITHIN_BUDGET' for r in b['receipts']))
        self.assertTrue(b['instructions_included'] and b['serialized_data_included'])
        self.assertFalse(b['automatic_truncation'])

    def test_oversize_original_text_blocks_without_prefix_truncation(self):
        data = deepcopy(self.data)
        a = self.analyses[0]
        row = next(r for r in data['results'] if r['task_id'] == a['task_id'])
        row['original_input']['fault']['tail_sentinel'] = 'X' * 170000 + '重要结论在末尾'
        b = r4.budget_receipts(r3.OUTPUT, data, [a], self.extra)
        self.assertEqual(b['receipts'][0]['status'], 'BLOCKED')
        self.assertEqual(b['receipts'][0]['reason'], 'INPUT_TOO_LARGE')
        self.assertGreater(b['receipts'][0]['serialized_input_chars'], 170000)
        self.assertFalse(b['automatic_truncation'])

    def test_different_subproblems_keep_different_paths_and_oracles(self):
        aa = [a for a in self.analyses if a['task_id'] == 'RC-030' and a['entity_type'].startswith('INDEPENDENT')]
        self.assertEqual(len(aa), 3)
        self.assertEqual(len({a['analysis_id'] for a in aa}), 3)
        self.assertEqual(len({a['design_cards'][0]['target_path'] for a in aa}), 3)
        self.assertEqual(len({json.dumps(a['design_cards'][0]['checks']) for a in aa}), 3)

    def test_history_source_cannot_be_output(self):
        with self.assertRaises(ValueError):
            r4.pilot(r3.OUTPUT, r3.OUTPUT)

    def test_invalid_or_stale_archive_cannot_be_packaged(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'invalid'
            with patch.object(r4, 'verify', return_value=dict(status='FAIL', errors=['stale_policy'])):
                with self.assertRaisesRegex(ValueError, 'stale_policy'):
                    r4.package(out)
            self.assertFalse(out.with_suffix('.zip').exists())

    def test_budget_or_code_change_invalidates_pilot_before_any_batch_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'pilot_validation.json').write_text(json.dumps(dict(status='PASS', policy_fingerprint='old', source_manifest_sha256='old')), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'Pilot must pass'):
                r4.build(out, r3.OUTPUT)
            self.assertFalse((out / 'sources').exists())

    def test_direct_cli_pilot_then_complete_offline_build_preserves_source(self):
        source_hashes = r4.r2.file_hashes(r3.OUTPUT)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'new-output'
            run = subprocess.run([sys.executable, 'scripts/rc128_mechanism_review.py', 'pilot', str(out),
                '--source-bundle', 'reports/archive/rc128-evidence-review-20261112-r3'],
                cwd=r4.core.REPO, capture_output=True, encoding='utf-8')
            self.assertEqual(run.returncode, 0, run.stderr)
            # Build needs an archive path within the repo for provenance, but
            # the destination is an independent temporary directory.
            result = r4.build(out, Path('reports/archive/rc128-evidence-review-20261112-r3'))
            self.assertEqual(result['status'], 'PASS', result['errors'])
            self.assertEqual(r4.r2.file_hashes(r3.OUTPUT), source_hashes)
            with self.assertRaisesRegex(ValueError, 'immutable'):
                r4.build(out, r3.OUTPUT)


if __name__ == '__main__':
    unittest.main()
