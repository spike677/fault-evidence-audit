import unittest

from faultaudit.trigger_report import build_workbook
from tests.test_trigger_report import fixture


class DeclaredReportStatusTests(unittest.TestCase):
    def test_incremental_mode_count_uses_frozen_baseline_not_fault_subjects(self):
        data = fixture()
        data['phase'] = 'INCREMENTAL'
        data['baseline'] = {'mode_ids': ['CAT-A', 'CAT-B']}
        for subject in data['subjects']:
            subject.pop('mode_id')
            subject['subject_kind'] = 'FAULT_CASE'
        table = next(s for s in build_workbook(data)['sheets'] if s['name'] == '运行统计')
        rows = {r[0]: dict(zip(table['columns'], r)) for r in table['rows']}
        self.assertEqual(rows['原模式数量']['值'], 2)
        self.assertEqual(rows['来源记录数量']['值'], 3)
        self.assertIn('冻结基线', rows['原模式数量']['口径'])

    def test_declared_processing_and_target_are_separate_from_web_pending(self):
        data = fixture()
        for assessment in data['assessments']:
            assessment['result'].update(processing_status='PENDING', declared_processing_status='AUTO_PROCESSED')
            assessment['result']['declared_comparison'] = {
                'rows': [], 'scope_relation': 'IN_SCOPE', 'scope_reason': 'Synthetic test scope',
                'decision': {'action': 'CLASSIFY_DECLARED', 'target_mode_ids': ['M1'],
                             'target_detail_ids': [], 'reason': 'Synthetic declared result'},
            }
        sheet = build_workbook(data)['sheets'][0]
        row = dict(zip(sheet['columns'], sheet['rows'][0]))
        self.assertEqual(row['处理状态'], 'PENDING')
        self.assertEqual(row['声明整理状态'], 'AUTO_PROCESSED')
        self.assertEqual(row['声明目标模式'], 'M1')


if __name__ == '__main__':
    unittest.main()
