"""Snapshot replacement invalidates only its actual downstream work."""
import json
import unittest
from faultaudit.bridge import submit_model_results
from faultaudit.importers import import_cases
from faultaudit.pipeline import import_into, current_mappings, current_judgments
from tests import test_evidence_workflow as fixtures


class DependencyInvalidationTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.EvidenceWorkflowTests()
        self.fx.setUp()
        self.store, self.run = self.fx.store, self.fx.run_id
        self.a = self.fx.load()[0]
        row = {**self.a['raw'], '统一ID': 'SYN-B', 'wiki': 'https://example.invalid/secondary'}
        path = self.fx.directory/'other.json'
        path.write_text(json.dumps([row], ensure_ascii=False), encoding='utf-8')
        self.b = import_cases(path, 'ORIGINAL_WEEKLY')['cases'][0]
        import_into(self.store, self.run, import_cases(path, 'ORIGINAL_WEEKLY'))
        self.old = self.fx.capture()
        self.store.ingest_evidence(self.run, {'url': row['wiki'], 'text': fixtures.TEXT,
            'status': 'PARTIAL', 'components': {'body': 'COMPLETE'}, 'is_synthetic': True})

    def tearDown(self):
        self.fx.doCleanups()

    def replace_a(self):
        return self.store.ingest_evidence(self.run, {'url': 'https://example.invalid/main',
            'text': 'Changed synthetic observation.', 'status': 'PARTIAL',
            'components': {'body': 'COMPLETE'}, 'is_synthetic': True})

    def test_updating_a_keeps_b_current_mapping_without_another_execute(self):
        self.fx.finish()
        before = current_mappings(self.store, self.run)
        self.assertEqual(len(before), 2)
        b = next(m for m in before if m['case_id'] == self.b['case_id'])
        self.replace_a()
        self.assertEqual([m['task_id'] for m in current_mappings(self.store, self.run)], [b['task_id']])
        self.assertEqual({j['case_id'] for j in current_judgments(self.store, self.run)}, {self.b['case_id']})
        self.assertEqual(len(self.store.records(self.run, 'mappings')), 2)
        self.assertEqual(len(self.store.records(self.run, 'snapshots')), 3)

    def test_pending_compare_is_invalidated_by_exact_snapshot_not_old_pair_target(self):
        _, summaries = self.fx.drive()
        submit_model_results(self.store, self.run, [self.fx.envelope(task) for task in summaries])
        _, compares = self.fx.drive()
        self.assertEqual(len(compares), 2)
        a = next(t for t in compares if t['payload']['case']['case_id'] == self.a['case_id'])
        b = next(t for t in compares if t['payload']['case']['case_id'] == self.b['case_id'])
        self.replace_a()
        states = {t['task_id']: t['status'] for t in self.store.tasks(self.run)}
        self.assertEqual(states[a['pipeline_task_id']], 'STALE')
        self.assertEqual(states[b['pipeline_task_id']], 'PENDING')


if __name__ == '__main__':
    unittest.main()
