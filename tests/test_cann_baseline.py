"""Synthetic Builder integration only; no actual model, website or production state."""
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook

from faultaudit import cann_baseline as builder, trigger_workflow as workflow
from faultaudit import xlsx_workflow as files
from faultaudit.store import AuditError, Store
from faultaudit.trigger_sparse import CONTRACT, frame_version
from faultaudit.trigger_assessment import validate_assessment
from faultaudit.trigger_taxonomy import EXPECTED_IDS
from tests.test_trigger_taxonomy import taxonomy_text
from tests.v4_fixtures import markdown
from tests.test_trigger_assessment import fixture, HASH
from tests.test_trigger_sparse import sparse_attempt


DIMENSIONS = list(builder.CrossDimensionReview.model_fields['dimension'].annotation.__args__)


class BaselineBuilderTests(unittest.TestCase):
    def setUp(self):
        self.budget = patch.dict(os.environ, {'FAULTAUDIT_MAX_INPUT_CHARS': '240000'})
        self.budget.start()
        self.addCleanup(self.budget.stop)
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-baseline-', dir=Path(__file__).parent)
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'state')
        self.taxonomy = self.root / 'trigger_library.md'
        self.taxonomy.write_text(taxonomy_text(), encoding='utf-8')
        self.v4 = self.root / 'v4.md'
        self.v4.write_text(markdown(), encoding='utf-8')
        self.modes = self.root / 'modes.xlsx'

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def start(self, count=2, cause='同一调用发生同步竞争，输出有残留', **options):
        book = Workbook(); sheet = book.active
        sheet.append(['故障模式编号', '模式名称', '故障原因', '算子', '案例链接'])
        for i in range(count):
            sheet.append([f'SYN-{i}', '合成模式' + str(i), cause, 'SyntheticFoo', ''])
        book.save(self.modes)
        cfg = workflow.start_init(self.store, self.modes, self.taxonomy, self.root / 'work',
            executor='codex', v4_source=self.v4, baseline_builder=True, expected_mode_count=count, **options)
        self.run = cfg['run_id']
        return cfg

    def request(self, task):
        return self.store.get(self.run, 'workflow_requests', task['task_id'])

    def response(self, request):
        p = request['payload']
        _, template = fixture()
        if request['kind'] == 'baseline_review':
            return {'request_hash': request['request_hash'], 'executor': 'codex', 'producer': template['producer'],
                'self_check': template['self_check'], 'reviewed_mode_ids': [m['mode_id'] for m in p['mode_records']],
                'findings': [], 'comparison_checks': [{'dimension': d, 'status': 'NEEDS_CLARIFICATION',
                    'reason': '合成协议样例，缺输入细节，不声称真实归类'} for d in DIMENSIONS],
                'recommendation': 'READY_WITH_GAPS', 'reason': '合成单元测试，保留明确未知'}
        case = p['subject']['source_case']
        cell = {'field': '故障原因', 'cell': case['cell_locations']['故障原因'], 'quote': case['raw']['故障原因']}
        fact = {'fact_id': 'F', 'statement': cell['quote'], 'subject': 'SOURCE_RECORD', 'role': 'SYNC_RACE',
            'evidence_basis': 'SOURCE_DEFINITION', 'source_cells': [cell]}
        if request['kind'] == 'baseline_define':
            from faultaudit.source_manifest import references_for_cells
            fact['source_refs'] = references_for_cells(p['source_manifest'], [cell])
        common = {'request_hash': request['request_hash'], 'case_id': case['case_id'], 'executor': 'codex',
            'producer': template['producer'], 'condition_facts': [fact], 'self_check': template['self_check']}
        claim = {'text': cell['quote'], 'status': 'STATED', 'condition_fact_ids': ['F']}
        if request['kind'] == 'baseline_define':
            if p.get('source_contract'):
                source_id = next(e['source_id'] for e in p['source_manifest']['entries'] if e['column_key']=='故障原因')
                return {k: v for k, v in {**common, 'condition_facts': None,
                    'field_bindings': {field: {'origin': 'SOURCE_DECLARATION', 'source_ids': [source_id]}
                                       for field in builder.FIELDS}}.items() if k != 'condition_facts'}
            return {**common, 'definition': {'mode_id': p['subject']['mode_id'], 'mode_name': p['original_mode']['description'],
                **{field: copy.deepcopy(claim) for field in builder.FIELDS}}}
        if request['kind'] == 'baseline_execution':
            return {**common, 'execution_conditions': claim, 'execution_method_links': [{
                'method_id': 'E3', 'reason': '合成输出预填检查建议，不是同步根因确认', 'condition_fact_ids': ['F']}],
                'evidence_gaps': ['没有历史正文或实机执行；不阻止定义归类']}
        return {**template, **common, 'rows': [], 'v4_rows': [], 'external_branches': [],
            'classification_contract': CONTRACT,
            'classification_summary': {'status': 'INSUFFICIENT_INFORMATION', 'reason': '定义缺少合法API和具体构造前提',
                'unknowns': ['API签名和条件公式']}, 'label_links': [], 'scenarios': [],
            'details': [{'detail_id': 'D', 'mode_id': p['subject']['mode_id'], 'name': '合成同步机理',
                'mechanism': cell['quote'], 'evidence_basis': 'SOURCE_DEFINITION', 'source_cells': [cell]}]}

    def submit(self, task, response=None):
        request = self.request(task)
        return files.submit(self.store, self.run, task['task_id'], self.response(request) if response is None else response)

    def advance(self):
        batch = files.next_tasks(self.store, self.run)
        for task in batch['tasks']:
            self.submit(task)
        return batch

    def finish_stages(self):
        self.advance()  # A1
        self.advance()  # A2/A3/A4
        return files.next_tasks(self.store, self.run)

    def test_original42_receipt_freezes_full_definitions_and_source_unchanged(self):
        before = self.taxonomy.read_bytes(); v4_before = self.v4.read_bytes()
        cfg = self.start()
        receipt = self.store.get(self.run, 'api42_registry_receipts', cfg['api42_registry_id'])
        self.assertEqual(receipt['actual_ids'], list(EXPECTED_IDS))
        self.assertEqual(receipt['source_sha256'], hashlib.sha256(before).hexdigest())
        self.assertEqual(receipt['source_file'], str(self.taxonomy.resolve()))
        self.assertEqual([receipt[k] for k in ('duplicate_ids', 'missing_ids', 'unexpected_ids')], [[], [], []])
        self.assertTrue(all(i['name'] and i['definition'] for i in receipt['items']))
        self.assertEqual(workflow._taxonomy(self.store, self.run)['items'],
            self.store.get(self.run, 'trigger_taxonomies', workflow._taxonomy(self.store, self.run)['original_taxonomy_id'])['items'])
        self.assertEqual(workflow._taxonomy(self.store, self.run)['definition_version'], receipt['definition_version'])
        self.assertEqual(self.taxonomy.read_bytes(), before)
        self.assertEqual(self.v4.read_bytes(), v4_before)
        self.assertTrue(builder.configure(self.store, self.run)['idempotent'])

    def test_changed_file_duplicate_missing_ids_and_mode_count_are_not_silently_accepted(self):
        self.start()
        with self.assertRaises(AuditError): builder.configure(self.store, self.run, expected_mode_count=30)
        before = self.taxonomy.read_text(encoding='utf-8')
        for changed in (before.replace('Synthetic trigger 1.1.1', 'Changed definition'),
                        before.replace('**1.1.1 Synthetic', '**1.1.2 Synthetic'),
                        before.replace('**1.1.1 Synthetic', '**9.1.1 Synthetic')):
            self.taxonomy.write_text(changed, encoding='utf-8')
            with self.assertRaises(AuditError): builder.configure(self.store, self.run)
        self.taxonomy.write_text(before, encoding='utf-8')
        self.assertTrue(builder.configure(self.store, self.run)['idempotent'])

    def test_independent_stages_without_wiki_repeated_dispatch_is_stable(self):
        self.start()
        first = files.next_tasks(self.store, self.run)
        self.assertEqual([t['kind'] for t in first['tasks']], ['baseline_define'] * 2)
        self.assertEqual(first, files.next_tasks(self.store, self.run))
        for task in first['tasks']: self.submit(task)
        second = files.next_tasks(self.store, self.run)
        self.assertEqual(sorted(t['kind'] for t in second['tasks']),
            sorted(['baseline_v4', 'baseline_api42', 'baseline_execution'] * 2))
        for task in second['tasks']:
            p = self.request(task)['payload']
            if task['kind'] == 'baseline_api42':
                self.assertNotIn('v4_taxonomy', p)
                self.assertEqual(p['input_condition_scheme'], 'ORIGINAL42')
            self.submit(task)
        self.assertEqual([t['kind'] for t in files.next_tasks(self.store, self.run)['tasks']], ['baseline_review'])
        self.assertEqual(self.store.records(self.run, 'snapshots'), [])
        self.assertEqual(self.store.records(self.run, 'judgments'), [])

    def test_definitions_are_grounded_and_do_not_generate_human_accept(self):
        self.start(1)
        task = files.next_tasks(self.store, self.run)['tasks'][0]
        valid = self.response(self.request(task))
        for mutate in (lambda r: r['field_bindings']['failure_mechanism'].update(source_ids=[]),
                       lambda r: r['field_bindings']['failure_mechanism'].update(quote='invented'),
                       lambda r: r.update(definition={'mode_id':'OTHER'}),
                       lambda r: r.update(review_status='ACCEPT')):
            invalid = copy.deepcopy(valid); mutate(invalid)
            with self.assertRaises(AuditError): self.submit(task, invalid)
        self.submit(task, valid)
        mode = builder.current_definitions(self.store, self.run)[0]['result']
        self.assertFalse(mode['validation_status']['SOURCE_VERIFIED'])
        self.assertFalse(mode['validation_status']['HARDWARE_VALIDATED'])
        self.assertEqual(self.store.records(self.run, 'reviews'), [])

    def test_one_axis_does_not_mark_the_other_axis_assessed(self):
        from faultaudit.trigger_combinations import analyze
        self.start(1); self.advance()
        task = next(t for t in files.next_tasks(self.store, self.run)['tasks'] if t['kind'] == 'baseline_v4')
        self.submit(task)
        frames = analyze(workflow._projection(self.store, self.run))['frames']
        counts = {(f['scheme'], f['axis']): f['assessed_unit_count'] for f in frames}
        self.assertEqual(counts[('V4', 'DESCRIPTION')], 1)
        self.assertEqual(counts[('ORIGINAL42', 'DESCRIPTION')], 0)

    def test_positive_independent_labels_reach_baseline_without_verification_inheritance(self):
        from tests.v4_fixtures import v4_unknown
        from faultaudit.trigger_v4 import canonical_conditions
        self.start(2, cause='合法输入维长65，尾块分块地址步长错误'); self.advance()
        for task in files.next_tasks(self.store, self.run)['tasks']:
            request = self.request(task); p = request['payload']; r = self.response(request)
            if task['kind'] in {'baseline_v4', 'baseline_api42'}:
                r['condition_facts'][0]['role'] = 'INPUT_SHAPE'
                cell = r['condition_facts'][0]['source_cells'][0]
                scheme = 'V4' if task['kind'] == 'baseline_v4' else 'ORIGINAL42'
                key = 'S5' if scheme == 'V4' else '1.2.4'
                if scheme == 'V4':
                    row = next(v for v in v4_unknown(p, r)['v4_rows'] if v['trigger_id'] == key)
                    child = row['construction_checks'][0]
                    child.update(applicability='PARTIAL', condition_fact_ids=['F'], source_cells=[cell],
                        reason='原输入维长与分块线索', construction_recipe='构造粒度边界两侧合法输入；接口粒度仍待补充')
                    row['construction_checks'] = [child]; r['v4_rows'] = [row]
                else:
                    item = next(i for i in p['taxonomy']['items'] if i['id'] == key)
                    family = next(f for f in p['taxonomy']['families'] if f['family_id'] == item['family_id'])
                    row = {'trigger_id': key, 'predicate_checks': [{'clause_role': role, 'clause': text, 'result': 'UNKNOWN'}
                        for role, text in sorted(canonical_conditions(item, family))]}
                    r['rows'] = [row]
                row.update(applicability='PARTIAL', relation='UNKNOWN', evidence_basis='SOURCE_DEFINITION',
                    condition_fact_ids=['F'], source_cells=[cell], reason='按原文条件归类，未确认全部前提')
                r['classification_summary'] = {'status': 'CLASSIFIED', 'reason': '合成明确输入线索', 'unknowns': ['接口粒度']}
                r['scenarios'] = [{'scenario_id': 's', 'title': '同一尾块输入', 'condition_fact_ids': ['F'], 'reason': '同一单元格'}]
                r['label_links'] = [{'scheme': scheme, 'trigger_id': key, 'definition_version': frame_version(p, scheme),
                    'detail_ids': ['D'], 'scenario_ids': ['s'], 'condition_fact_ids': ['F'],
                    'construction_ids': [child['construction_id']] if scheme == 'V4' else []}]
            self.submit(task, r)
        task = files.next_tasks(self.store, self.run)['tasks'][0]
        review = self.response(self.request(task)); ids = review['reviewed_mode_ids']
        records = self.request(task)['payload']['mode_records']
        review['findings'] = [{'relation': 'SHARED_CONSTRUCTION', 'mode_ids': ids,
            'reason': '共用合成构造线索，不证明相同失效机理', 'source_fact_ids': {m['mode_id']: ['A1:' + m['condition_facts'][0]['fact_id']] for m in records}}]
        next(c for c in review['comparison_checks'] if c['dimension'] == 'SHARED_CONSTRUCTION')['finding_indexes'] = [0]
        self.submit(task, review)
        frozen = workflow.finalize(self.store, self.run, allow_pending=True)
        for mode in frozen['mode_records']:
            self.assertEqual(mode['v4_theme_ids'], ['S'])
            self.assertEqual(mode['v4_class_ids'], ['S5'])
            self.assertEqual(len(mode['v4_scenario_ids']), 1)
            self.assertNotIn('S5', mode['v4_scenario_ids'])
            self.assertEqual(mode['api_trigger_ids'], ['1.2.4'])
            self.assertEqual(mode['execution_method_ids'], ['E3'])
            self.assertFalse(mode['validation_status']['SOURCE_VERIFIED'])
            self.assertFalse(mode['validation_status']['HARDWARE_VALIDATED'])
        self.assertEqual(len(frozen['mode_ids']), 2)
        self.assertEqual(self.store.records(self.run, 'reviews'), [])

    def test_cross_review_is_required_even_with_allow_pending_and_checks_every_dimension(self):
        self.start(2)
        with self.assertRaisesRegex(AuditError, 'A1-A4'): workflow.finalize(self.store, self.run, allow_pending=True)
        task = self.finish_stages()['tasks'][0]
        with self.assertRaisesRegex(AuditError, 'horizontal review'): workflow.finalize(self.store, self.run, allow_pending=True)
        good = self.response(self.request(task))
        bad = copy.deepcopy(good); bad['comparison_checks'].pop()
        with self.assertRaisesRegex(AuditError, 'six'): self.submit(task, bad)
        bad = copy.deepcopy(good); bad['reviewed_mode_ids'].pop()
        with self.assertRaisesRegex(AuditError, 'every original'): self.submit(task, bad)
        bad = copy.deepcopy(good); bad['recommendation'] = 'READY'
        with self.assertRaisesRegex(AuditError, 'Unclear'): self.submit(task, bad)
        bad = copy.deepcopy(good); bad['automatic_merge'] = True
        with self.assertRaises(AuditError): self.submit(task, bad)
        self.submit(task, good)
        with self.assertRaisesRegex(AuditError, 'gaps'): workflow.finalize(self.store, self.run)
        frozen = workflow.finalize(self.store, self.run, allow_pending=True)
        self.assertEqual(len(frozen['mode_records']), 2)
        self.assertTrue(frozen['baseline_version'].startswith('CANN-BASELINE-v1-'))
        self.assertNotIn('revised_definition_version', frozen)
        self.assertEqual(frozen['status'], 'READY_WITH_GAPS')
        self.assertEqual(files.next_tasks(self.store, self.run)['tasks'], [])
        self.assertEqual(workflow.status(self.store, self.run)['subject_count'], 2)  # no recursion with frozen head
        self.assertEqual(workflow.finalize(self.store, self.run, allow_pending=True)['baseline_id'], frozen['baseline_id'])

    def test_rework_cannot_be_frozen_and_findings_need_scoped_support(self):
        self.start(2); task = self.finish_stages()['tasks'][0]
        response = self.response(self.request(task)); ids = response['reviewed_mode_ids']
        response['findings'] = [{'relation': 'SAME_MECHANISM_CANDIDATE', 'mode_ids': ids,
            'reason': '相同原文机理待复核', 'source_fact_ids': {m: ['F'] for m in ids}}]
        response['comparison_checks'][0]['finding_indexes'] = [0]
        with self.assertRaisesRegex(AuditError, 'unknown definition facts'): self.submit(task, response)
        response['findings'][0]['source_fact_ids'] = {m['mode_id']: ['A1:' + m['condition_facts'][0]['fact_id']]
            for m in self.request(task)['payload']['mode_records']}
        response['recommendation'] = 'REWORK_REQUIRED'
        self.submit(task, response)
        with self.assertRaisesRegex(AuditError, 'rework'): workflow.finalize(self.store, self.run, allow_pending=True)

    def test_four_artifacts_keep_axes_mechanism_methods_and_gaps_separate(self):
        self.start(2); self.finish_stages()
        result = workflow.export(self.store, self.run)
        output = Path(result['report_html']).parent
        self.assertEqual({p.name for p in output.iterdir()}, {'baseline_30_modes.html', 'baseline_30_modes.json',
            'baseline_42_api_mapping.tsv', 'baseline_v4_mapping.tsv'})
        data = json.loads(Path(result['report_json']).read_text(encoding='utf-8'))
        self.assertEqual(data['baseline_freeze']['status'], 'NOT_FROZEN')
        self.assertEqual(data['mapping_document_status'], 'NOT_PROVIDED')
        for mode in data['mode_records']:
            self.assertTrue(mode['failure_mechanism']['text'])
            self.assertEqual(mode['v4_scenario_ids'], [])
            self.assertEqual(mode['api_trigger_ids'], [])
            self.assertEqual(mode['execution_method_ids'], ['E3'])
            self.assertIn('A1:' + mode['condition_facts'][0]['fact_id'], mode['evidence_index'])
        for filename in ('baseline_42_api_mapping.tsv', 'baseline_v4_mapping.tsv'):
            with (output / filename).open(encoding='utf-8-sig', newline='') as stream:
                self.assertEqual(len(list(csv.DictReader(stream, delimiter='\t'))), 2)
        html = Path(result['report_html']).read_text(encoding='utf-8')
        for term in ('failure_mechanism', 'A1', 'A2', 'A3', 'A4', 'SHA-256', '横向'):
            self.assertTrue(term in html, term)

    def test_original_input_change_invalidates_all_stages_and_keeps_history(self):
        self.start(1); self.advance(); old = builder.current_definitions(self.store, self.run)[0]
        task = files.next_tasks(self.store, self.run)['tasks'][0]
        case = self.store.records(self.run, 'cases')[0]
        case = copy.deepcopy(case); case['raw']['故障原因'] += '，输入改变'
        self.store.put(self.run, 'cases', case['case_id'], case, mutable=True)
        self.assertEqual(builder.current_definitions(self.store, self.run), [])
        self.assertEqual(workflow.current_assessments(self.store, self.run), [])
        with self.assertRaises(AuditError): self.submit(task)
        self.assertEqual(len(self.store.records(self.run, 'mode_definitions')), 1)
        self.assertEqual(self.store.get(self.run, 'mode_definitions', old['definition_id']), old)
        self.assertEqual([t['kind'] for t in files.next_tasks(self.store, self.run)['tasks']], ['baseline_define'])

    def test_catalog_definition_change_invalidates_a1_without_rewriting_history(self):
        self.start(1); self.advance()
        old = builder.current_definitions(self.store, self.run)[0]
        item = self.store.records(self.run, 'catalog')[0]
        changed = {**item, 'mechanism': '更新的原模式说明'}
        self.store.put(self.run, 'catalog', item['item_id'], changed, mutable=True)
        self.assertEqual(builder.current_definitions(self.store, self.run), [])
        self.assertEqual(self.store.get(self.run, 'mode_definitions', old['definition_id']), old)
        extra = {**changed, 'item_id': 'SYN-EXTRA'}
        self.store.put(self.run, 'catalog', extra['item_id'], extra)
        with self.assertRaisesRegex(AuditError, 'catalog and Baseline subjects differ'):
            workflow.finalize(self.store, self.run, allow_pending=True)

    def test_execution_dependency_and_policy_change_make_baseline_stale_without_deleting_history(self):
        self.start(1); self.finish_stages(); self.advance()
        frozen = workflow.finalize(self.store, self.run, allow_pending=True)
        self.assertTrue(builder.current_review(self.store, self.run))
        with patch('faultaudit.cann_baseline._available_evidence', return_value={'changed': 'new capture'}):
            self.assertEqual(builder.current_execution(self.store, self.run), [])
            self.assertIsNone(builder.current_review(self.store, self.run))
            with self.assertRaisesRegex(AuditError, 'stale'): workflow._baseline(self.store, self.run, allow_pending=True)
        with patch('faultaudit.xlsx_workflow._policy', return_value='new-policy'):
            self.assertEqual(builder.current_definitions(self.store, self.run), [])
            self.assertIsNone(builder.current_review(self.store, self.run))
        self.assertEqual(self.store.get(self.run, 'trigger_baselines', frozen['baseline_id']), frozen)


class IndependentAxisGateTests(unittest.TestCase):
    def test_all_builder_tasks_report_context_limits_as_transport_blocks(self):
        from faultaudit.knowledge_common import SEMANTIC_KINDS
        from faultaudit.workflow_driver import executor_blocked
        for kind in SEMANTIC_KINDS:
            request = {'kind': kind, 'request_hash': HASH}
            response = {'request_hash': HASH, 'outcome': 'BLOCKED', 'reason_code': 'EXECUTOR_CONTEXT_LIMIT',
                'reason': 'Complete frozen input cannot fit this execution session'}
            self.assertTrue(executor_blocked(request, response))
            response['request_hash'] = 'forged'
            with self.assertRaises(AuditError): executor_blocked(request, response)

    def test_original42_link_cannot_use_revised42_or_v4_crosswalk(self):
        p, r = sparse_attempt(); p.update(baseline_axis='API42', input_condition_scheme='ORIGINAL42')
        r['label_links'][0]['scheme'] = 'REVISED42'
        with self.assertRaises(AuditError): validate_assessment(p, r, HASH)
        r['label_links'][0]['scheme'] = 'ORIGINAL42'
        out = validate_assessment(p, r, HASH)
        self.assertEqual(out['input_condition_scheme'], 'ORIGINAL42')
        self.assertEqual(out['details'][0]['trigger_ids'], ['1.3.2'])

    def test_no_api_details_is_unknown_not_whole_axis_not_applicable(self):
        p, r = sparse_attempt(); p.update(baseline_axis='API42', input_condition_scheme='ORIGINAL42')
        r.update(rows=[], scenarios=[], label_links=[])
        r['classification_summary'] = {'status': 'NOT_APPLICABLE', 'reason': '未给API', 'exclusion_fact_ids': ['F']}
        with self.assertRaisesRegex(AuditError, 'non-API'): validate_assessment(p, r, HASH)
        r['classification_summary'].update(status='INSUFFICIENT_INFORMATION', unknowns=['缺API签名'])
        self.assertEqual(validate_assessment(p, r, HASH)['classification_summary']['status'], 'INSUFFICIENT_INFORMATION')
        r['condition_facts'][0]['role'] = 'SYNC_RACE'
        r['classification_summary']['status'] = 'NOT_APPLICABLE'
        self.assertEqual(validate_assessment(p, r, HASH)['classification_summary']['status'], 'NOT_APPLICABLE')

    def test_s5_is_a_class_not_a_construction_and_construction_needs_own_recipe(self):
        from tests.test_trigger_v4 import V4Tests
        from tests.v4_fixtures import v4_unknown
        f = V4Tests(); f.setUp()
        try:
            p, r, cell = f.attempt('输入分块对齐条件', 'INPUT_SHAPE')
            f.label(r, 'S5', cell)
            row = next(v for v in r['v4_rows'] if v['trigger_id'] == 'S5')
            child = row['construction_checks'][0]
            child.update(applicability='PARTIAL', condition_fact_ids=['F'], source_cells=[cell],
                reason='合成分块条件', construction_recipe='合法边界输入设计，API粒度未知')
            row['construction_checks'] = [child]
            p.update(classification_contract=CONTRACT, baseline_axis='V4')
            r.update(classification_contract=CONTRACT, rows=[], external_branches=[], v4_rows=[row],
                classification_summary={'status': 'CLASSIFIED', 'reason': '合成条件', 'unknowns': ['粒度']},
                scenarios=[{'scenario_id': 's', 'title': '分块条件', 'condition_fact_ids': ['F'], 'reason': '同情景'}],
                label_links=[{'scheme': 'V4', 'trigger_id': 'S5', 'definition_version': frame_version(p, 'V4'),
                    'detail_ids': ['D'], 'scenario_ids': ['s'], 'condition_fact_ids': ['F'], 'construction_ids': [child['construction_id']]}],
                details=[{'detail_id': 'D', 'name': '合成机理', 'mechanism': cell['quote'],
                    'evidence_basis': 'SOURCE_DEFINITION', 'source_cells': [cell]}])
            out = validate_assessment(p, r, HASH)
            self.assertEqual(out['rows'], [])
            self.assertNotEqual(out['label_links'][0]['construction_ids'], ['S5'])
            bad = copy.deepcopy(r); bad['label_links'][0]['construction_ids'] = ['S5']
            with self.assertRaises(AuditError): validate_assessment(p, bad, HASH)
            bad = copy.deepcopy(r); bad['v4_rows'][0]['construction_checks'][0]['construction_recipe'] = ''
            with self.assertRaisesRegex(AuditError, 'recipe'): validate_assessment(p, bad, HASH)
        finally:
            f.tearDown()
