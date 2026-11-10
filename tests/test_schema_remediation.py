"""Synthetic protocol remediation, not a replay of onsite OpenCode responses."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from openpyxl import Workbook

from faultaudit import cann_baseline as builder, trigger_workflow as workflow, xlsx_workflow as files
from faultaudit.source_manifest import SELECTION_CONTRACT, FieldBinding, build, materialize_fields, resolve
from faultaudit.store import AuditError, digest
from faultaudit.trigger_assessment import validate_assessment
from faultaudit.trigger_sparse import CONTRACT, ClassificationFeedback, citation_example, frame_version
from faultaudit import baseline_recovery as recovery
from tests.test_baseline_recovery import RecoveryFixture
from tests.test_trigger_assessment import HASH
from tests.test_trigger_sparse import sparse_attempt
from tests import test_trigger_v4 as v4_fixtures


class A1BindingTests(RecoveryFixture):
    def task(self):
        self.start(1)
        task = files.next_tasks(self.store, self.run)['tasks'][0]
        return task, self.request(task), self.response(self.request(task))

    def test_original_headers_and_all_program_owned_binding_fields(self):
        book = Workbook(); sheet = book.active
        sheet.append(['故障模式编号', '模式名称', '一级\n(架构层次)', '故障原因'] + [None] * 11)
        sheet.append(['SYN', '合成机理', '芯片使能', '原文：内部地址计算溢出'] + [''] * 10 + ['原始案例链接'])
        book.save(self.modes)
        self.run = workflow.start_init(self.store, self.modes, self.taxonomy, self.root/'work', executor='codex',
            v4_source=self.v4, baseline_builder=True, expected_mode_count=1, input_budget_chars=160000)['run_id']
        task = files.next_tasks(self.store, self.run)['tasks'][0]; request = self.request(task)
        manifest = request['payload']['source_manifest']
        ids = [e['source_id'] for e in manifest['entries'] if e['column_key'] in {'一级\n(架构层次)', '__column_15'}]
        response = self.response(request)
        response['field_bindings']['fault_object']['source_ids'] = ids
        original = copy.deepcopy(response)
        self.submit(task, response)
        result = builder.current_definitions(self.store, self.run)[0]['result']
        receipt = result['source_binding']
        self.assertEqual(response, original)
        self.assertEqual(receipt['contract'], SELECTION_CONTRACT)
        fields = {e['column_key']: e for e in receipt['selected_entries']}
        self.assertEqual(fields['一级\n(架构层次)']['cell_address'], 'C2')
        self.assertEqual(fields['__column_15']['cell_address'], 'O2')
        for e in receipt['selected_entries']:
            fact = next(f for f in result['condition_facts'] if f['fact_id'] == e['source_id'])
            self.assertEqual(fact['statement'], e['original_value'])
            self.assertEqual(fact['source_cells'], [{'field': e['column_key'], 'cell': e['cell_address'], 'quote': e['original_value']}])
            self.assertEqual(e['workbook_hash'], request['payload']['subject']['source_case']['source_sha256'])
            self.assertEqual(e['row_number'], 2)
            self.assertEqual(e['sheet_name'], request['payload']['subject']['source_case']['sheet'])
        self.assertFalse(result['validation_status']['SOURCE_VERIFIED'])

    def test_model_cannot_supply_or_override_original_facts_and_quotes(self):
        task, _, good = self.task()
        for key in ('condition_facts', 'source_cells', 'source_refs', 'quote', 'workbook_hash'):
            bad = copy.deepcopy(good); bad[key] = [] if key != 'quote' else '伪造原文'
            with self.subTest(key=key), self.assertRaises(AuditError): self.submit(task, bad)
        bad = copy.deepcopy(good); bad['field_bindings']['failure_mechanism']['derived_text'] = '伪造原始声明'
        with self.assertRaisesRegex(AuditError, 'program owns'): self.submit(task, bad)
        self.assertEqual(builder.current_definitions(self.store, self.run), [])

    def test_unknown_or_duplicate_source_ids_rejected(self):
        task, _, good = self.task()
        for ids in (['no-such-source'], good['field_bindings']['fault_object']['source_ids'] * 2):
            bad = copy.deepcopy(good); bad['field_bindings']['fault_object']['source_ids'] = ids
            with self.assertRaisesRegex(AuditError, 'source_id'): self.submit(task, bad)

    def test_legacy_quote_and_alias_gates_still_reject_invalid_text(self):
        _, request, _ = self.task(); manifest = request['payload']['source_manifest']
        ref = {'source_id': manifest['entries'][0]['source_id'], 'quote': 'not in original'}
        with self.assertRaisesRegex(AuditError, 'exact quote'): resolve(manifest, [ref])
        changed = copy.deepcopy(manifest); changed['entries'][0]['column_key'] = 'renamed'
        with self.assertRaisesRegex(AuditError, 'frozen source'):
            materialize_fields(request['payload']['subject']['source_case'], changed, {})

    def test_webpage_assertions_and_gaps_cannot_become_source_declarations(self):
        task, _, good = self.task()
        for origin in ('HISTORICAL_EVIDENCE', 'GAP', 'SELF_CHECK'):
            bad = copy.deepcopy(good); bad['field_bindings']['failure_mechanism']['origin'] = origin
            with self.assertRaises(AuditError): self.submit(task, bad)
        bad = copy.deepcopy(good); bad['field_bindings']['failure_mechanism'].update(source_ids=['snapshot-fact'])
        with self.assertRaises(AuditError): self.submit(task, bad)

    def test_derivation_uses_real_ids_and_does_not_require_same_named_column(self):
        task, request, response = self.task()
        self.assertNotIn('failure_mechanism', request['payload']['subject']['source_case']['raw'])
        response['field_bindings']['failure_mechanism'].update(origin='MODEL_DERIVED',
            derived_text='合成推导：写回/同步存在竞争', reason='从原表同步竞争及残留描述提炼，未核实网页')
        response['field_bindings']['input_trigger_conditions'] = {'origin': 'UNKNOWN', 'reason': '未提供API前提'}
        self.submit(task, response)
        result = builder.current_definitions(self.store, self.run)[0]['result']
        self.assertEqual(result['failure_mechanism']['status'], 'INFERRED')
        self.assertTrue(result['failure_mechanism']['derivation_reason'])
        self.assertEqual(result['input_trigger_conditions']['status'], 'UNKNOWN')
        self.assertFalse(result['validation_status']['HARDWARE_VALIDATED'])

    def test_compatibility_unknown_cannot_be_promoted_independently_of_known_fields(self):
        self.start(1); subject = self.store.records(self.run, 'trigger_subjects')[0]
        old = self.seed_history(subject)
        # Build a genuine archived UNKNOWN, with a matching immutable response hash.
        old['raw_response']['definition']['input_trigger_conditions'] = {
            'text': '未知API输入', 'status': 'UNKNOWN', 'condition_fact_ids': []}
        old['result']['input_trigger_conditions'] = {**old['raw_response']['definition']['input_trigger_conditions'], 'derivation_reason': ''}
        self.store.put(self.run, 'mode_definitions', old['definition_id'], old, mutable=True)
        accepted = self.store.get(self.run, 'workflow_results', old['definition_id'])
        accepted.update(response=old['raw_response'], response_hash=digest(old['raw_response']))
        self.store.put(self.run, 'workflow_results', old['definition_id'], accepted, mutable=True)
        task = files.next_tasks(self.store, self.run)['tasks'][0]; request = self.request(task)
        good = self.compatibility_response(request)
        bad = copy.deepcopy(good)
        next(c for c in bad['field_checks'] if c['field']=='input_trigger_conditions')['verdict'] = 'SUPPORTED'
        with self.assertRaisesRegex(AuditError, 'unknown historical claim'): self.submit(task, bad)
        self.submit(task, good)
        result = builder.current_definitions(self.store, self.run)[0]['result']
        self.assertEqual(result['input_trigger_conditions']['status'], 'UNKNOWN')
        self.assertEqual(result['failure_mechanism']['status'], 'STATED')
        self.assertEqual(self.store.get(self.run, 'mode_definitions', old['definition_id']), old)
        self.assertEqual(self.store.records(self.run, 'reviews'), [])

    def test_new_contract_also_passes_historical_structural_review_without_raw_rewrite(self):
        from faultaudit.baseline_recovery import precheck
        task, _, response = self.task(); self.submit(task, response)
        record = builder.current_definitions(self.store, self.run)[0]
        subject = self.store.records(self.run, 'trigger_subjects')[0]
        self.assertEqual(precheck(self.store, self.run, subject, record)['structural_status'], 'PASS')
        self.assertEqual(record['raw_response'], response)


class A2CitationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = v4_fixtures.V4Tests(); self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def attempt(self, multiple_classes=False):
        p, r, cell = self.fixture.attempt('合法普通输入shape，有不同边界构造线索', 'INPUT_SHAPE')
        p.update(phase='INIT', assessment_basis='SOURCE_DEFINITIONS', baseline_axis='V4', classification_contract=CONTRACT)
        p['subject']['mode_id'] = 'M1'
        r['condition_facts'] = [{**copy.deepcopy(r['condition_facts'][0]), 'fact_id': f'F{i}'} for i in (1, 2)]
        keys = ['S1', 'S2'] if multiple_classes else ['S1']
        rows, links, scenarios = [], [], []
        for n, key in enumerate(keys):
            row = self.fixture.label(r, key, cell, facts=['F1', 'F2'])
            children = row['construction_checks'][:2 if not multiple_classes else 1]
            row['construction_checks'] = children
            for i, child in enumerate(children):
                fid = f'F{i+1}' if not multiple_classes else f'F{n+1}'
                child.update(applicability='PARTIAL', condition_fact_ids=[fid], source_cells=[cell],
                    construction_recipe='合成设计：边界两侧合法输入；实际API粒度未知')
                sid = f'{key}-local-{i}'
                links.append({'scheme':'V4', 'definition_version':frame_version(p,'V4'), 'trigger_id':key,
                    'detail_ids':['D'], 'scenario_ids':[sid], 'condition_fact_ids':[fid],
                    'construction_ids':[child['construction_id']]})
                scenarios.append({'scenario_id':sid, 'title':'独立子问题范围', 'condition_fact_ids':[fid], 'reason':'合成原文范围'})
            row['condition_fact_ids'] = sorted({fid for l in links if l['trigger_id']==key for fid in l['condition_fact_ids']})
            rows.append(row)
        r.update(rows=[], v4_rows=rows, external_branches=[], execution_method_links=[], classification_contract=CONTRACT,
            classification_summary={'status':'CLASSIFIED','reason':'原文条件线索，未证实事件','unknowns':['接口粒度']},
            scenarios=scenarios, label_links=links,
            details=[{'detail_id':'D','mode_id':'M1','name':'合成机制','mechanism':cell['quote'],
                      'evidence_basis':'SOURCE_DEFINITION','source_cells':[cell]}],
            decision={'action':'INIT_ONLY','reason':'仅初始化'})
        return p, r

    def test_one_class_and_two_constructions_can_use_distinct_facts(self):
        p, r = self.attempt(); out = validate_assessment(p, r, HASH)
        self.assertEqual(len(out['label_links']), 2)
        self.assertNotEqual(out['label_links'][0]['condition_fact_ids'], out['label_links'][1]['condition_fact_ids'])
        self.assertFalse(out['execution_verified'])

    def test_multiple_classes_do_not_inherit_each_others_facts(self):
        p, r = self.attempt(True); out = validate_assessment(p, r, HASH)
        self.assertEqual(len(out['v4_rows']), 2)
        self.assertEqual([l['condition_fact_ids'] for l in out['label_links']], [['F1'], ['F2']])

    def test_single_construction_stays_sparse(self):
        p, r = self.attempt(); r['label_links'] = r['label_links'][:1]; r['scenarios'] = r['scenarios'][:1]
        r['v4_rows'][0].update(condition_fact_ids=['F1'], construction_checks=r['v4_rows'][0]['construction_checks'][:1])
        self.assertEqual(len(validate_assessment(p, r, HASH)['v4_rows'][0]['construction_checks']), 1)

    def test_construction_fact_missing_from_link_has_located_diagnostic(self):
        p, r = self.attempt(); r['label_links'][0]['condition_fact_ids'] = ['F2']; r['scenarios'][0]['condition_fact_ids'] = ['F2']
        with self.assertRaises(ClassificationFeedback) as error: validate_assessment(p, r, HASH)
        d = error.exception.diagnostic
        self.assertEqual(d['row_id'], 'S1'); self.assertEqual(d['link_id'], 'label_links[0]')
        self.assertEqual(d['construction_id'], r['label_links'][0]['construction_ids'][0])
        self.assertEqual(d['missing_fact_ids'], ['F1'])
        self.assertEqual(d['violated_rule'], 'POSITIVE_CONSTRUCTION_FACTS_SUBSET_LINK')

    def test_link_fact_missing_from_scenario_returns_scenario_and_missing_id(self):
        p, r = self.attempt(); r['scenarios'][0]['condition_fact_ids'] = ['F2']
        with self.assertRaises(ClassificationFeedback) as error: validate_assessment(p, r, HASH)
        self.assertEqual(error.exception.diagnostic['scenario_id'], 'S1-local-0')
        self.assertEqual(error.exception.diagnostic['missing_fact_ids'], ['F1'])

    def test_positive_row_fact_cannot_be_hidden_by_links(self):
        p, r = self.attempt(); r['condition_facts'].append({**r['condition_facts'][0], 'fact_id':'F3'})
        r['v4_rows'][0]['condition_fact_ids'].append('F3')
        with self.assertRaises(ClassificationFeedback) as error: validate_assessment(p, r, HASH)
        self.assertEqual(error.exception.diagnostic['missing_fact_ids'], ['F3'])
        self.assertEqual(error.exception.diagnostic['violated_rule'], 'POSITIVE_ROW_FACTS_COVERED')

    def test_unexpected_link_facts_are_reported_without_weakening_rule(self):
        p, r = self.attempt(); r['label_links'][0]['condition_fact_ids'].append('F-other')
        with self.assertRaises(ClassificationFeedback) as error: validate_assessment(p, r, HASH)
        self.assertEqual(error.exception.diagnostic['unexpected_fact_ids'], ['F-other'])

    def test_full_applicable_row_still_cannot_stitch_different_scenarios(self):
        p, r = self.attempt(); r['v4_rows'][0]['applicability'] = 'APPLICABLE'
        with self.assertRaisesRegex(ClassificationFeedback, 'split required facts'): validate_assessment(p, r, HASH)

    def test_prompt_examples_use_actual_frozen_codes_and_leave_source_unchanged(self):
        p, _ = self.attempt(); before = copy.deepcopy(p)
        text = builder.axis_instructions('V4', p)
        self.assertIn('CORRECT:', text); self.assertIn('INCORRECT:', text)
        self.assertIn(p['v4_taxonomy']['items'][0]['construction_ids'][0], citation_example(p))
        self.assertEqual(p, before)


class A3ThreeStateTests(unittest.TestCase):
    def attempt(self, text='API shape 未提供', role='UNKNOWN'):
        p, r = sparse_attempt(text, role)
        p.update(baseline_axis='API42', input_condition_scheme='ORIGINAL42')
        r.update(rows=[], scenarios=[], label_links=[], source_relation='UNKNOWN',
            classification_summary={'status':'INSUFFICIENT_INFORMATION', 'reason':'原定义未提供合法API前提', 'unknowns':['shape/dtype/参数未知']})
        return p, r

    def test_unknown_is_a_valid_complete_attempt_with_specific_gaps(self):
        p, r = self.attempt(); out = validate_assessment(p, r, HASH)
        self.assertEqual(out['classification_summary']['status'], 'INSUFFICIENT_INFORMATION')
        self.assertEqual(out['rows'], [])
        self.assertEqual(out['classification_scope']['omitted_rules'], 'NOT_ASSESSED')
        self.assertEqual(out['source_relation'], 'UNKNOWN')

    def test_positive_non_api_dependency_allows_axis_exclusion(self):
        p, r = self.attempt('仅Host线程交错产生竞争，同实参同二进制', 'SYNC_RACE')
        r['classification_summary'] = {'status':'NOT_APPLICABLE','reason':'明确非API执行依赖', 'exclusion_fact_ids':['F']}
        self.assertEqual(validate_assessment(p, r, HASH)['classification_summary']['status'], 'NOT_APPLICABLE')

    def test_missing_inputs_cannot_become_whole_axis_non_applicability(self):
        for role in ('UNKNOWN', 'INPUT_SHAPE'):
            p, r = self.attempt(role=role)
            r['classification_summary'] = {'status':'NOT_APPLICABLE','reason':'错误地将缺失视为排除','exclusion_fact_ids':['F']}
            with self.assertRaisesRegex(AuditError, 'positive non-API'): validate_assessment(p, r, HASH)

    def test_definition_without_webpage_can_classify_partial_and_keep_source_unknown(self):
        p, r = sparse_attempt(); p.update(baseline_axis='API42', input_condition_scheme='ORIGINAL42')
        r['label_links'][0].update(scheme='ORIGINAL42', definition_version=frame_version(p,'ORIGINAL42'))
        out = validate_assessment(p, r, HASH)
        self.assertEqual(out['rows'][0]['applicability'], 'PARTIAL')
        self.assertEqual(out['source_relation'], 'UNKNOWN')
        # Complete grounded Requires/Skip can establish applicability without a webpage MATCH.
        r['rows'][0]['applicability'] = 'APPLICABLE'
        for check in r['rows'][0]['predicate_checks']:
            check.update(result='MET' if check['clause_role']=='INCLUSION' else 'NOT_MET',
                condition_fact_ids=['F'], source_cells=r['condition_facts'][0]['source_cells'])
        out = validate_assessment(p, r, HASH)
        self.assertEqual(out['rows'][0]['applicability'], 'APPLICABLE')
        self.assertEqual(out['source_relation'], 'UNKNOWN')

    def test_no_auto_upgrade_to_source_match_or_full_applicability(self):
        p, r = self.attempt(); r['source_relation'] = 'MATCH'
        with self.assertRaises(AuditError): validate_assessment(p, r, HASH)
        p, r = sparse_attempt(); p.update(baseline_axis='API42', input_condition_scheme='ORIGINAL42')
        r['label_links'][0].update(scheme='ORIGINAL42', definition_version=frame_version(p,'ORIGINAL42'))
        r['rows'][0]['applicability'] = 'APPLICABLE'
        with self.assertRaises(AuditError): validate_assessment(p, r, HASH)

    def test_unknown_does_not_mean_dense_padding_or_forty_two_negative_rows(self):
        p, r = self.attempt(); row = sparse_attempt()[1]['rows'][0]; row['applicability'] = 'UNKNOWN'
        r['rows'] = [row]
        with self.assertRaisesRegex(AuditError, 'Omit UNKNOWN'): validate_assessment(p, r, HASH)
        self.assertIn('UNKNOWN is valid', builder.axis_instructions('API42'))
        self.assertIn('failed Requires', builder.axis_instructions('API42'))


class StageCompatibilityTests(RecoveryFixture):
    def upgrade(self):
        self.start(1); self.advance(); self.advance()
        before = {kind: self.store.records(self.run, kind) for kind in
                  ('mode_definitions', 'trigger_assessments', 'baseline_execution', 'workflow_attempts')}
        self.policy = patch('faultaudit.xlsx_workflow._policy', return_value='e' * 64)
        self.policy.start(); self.addCleanup(self.policy.stop)
        self.assertEqual(builder.current_definitions(self.store, self.run), [])
        self.assertEqual(workflow.current_assessments(self.store, self.run), [])
        task = files.next_tasks(self.store, self.run)['tasks'][0]
        self.assertEqual(task['kind'], 'baseline_compatibility')
        self.submit(task, self.compatibility_response(self.request(task)))
        return before

    def test_unchanged_completed_axes_and_execution_are_revalidated_without_new_accepts(self):
        before = self.upgrade()
        after_review = {kind: self.store.records(self.run, kind) for kind in before}
        values = workflow.current_assessments(self.store, self.run) + builder.current_execution(self.store, self.run)
        self.assertEqual(len(values), 3)
        for r in values:
            self.assertEqual(r['current_validation']['status'], 'READ_ONLY_REVALIDATED')
            self.assertNotEqual(r['policy_hash'], 'e' * 64)
        for kind in before:
            self.assertEqual(self.store.records(self.run, kind), after_review[kind])
        self.assertEqual(recovery.recovery_plan(self.store, self.run)['current_downstream_units'], 3)
        self.assertEqual(len(recovery.recovery_plan(self.store, self.run)['read_only_revalidated_stage_ids']), 3)
        self.assertEqual([t['kind'] for t in files.next_tasks(self.store, self.run)['tasks']], ['baseline_review'])
        for kind, records in before.items():
            key = {'mode_definitions':'definition_id','trigger_assessments':'assessment_id',
                   'baseline_execution':'execution_id'}.get(kind)
            if key:
                for record in records:
                    self.assertEqual(self.store.get(self.run, kind, record[key]), record)
        self.assertEqual(self.store.records(self.run, 'reviews'), [])

    def test_old_requests_stay_unsubmittable_even_if_completed_result_revalidates(self):
        before = self.upgrade()
        old = before['trigger_assessments'][0]
        with self.assertRaisesRegex(AuditError, 'policy'):
            files.submit(self.store, self.run, old['assessment_id'], old['raw_response'])
        self.assertEqual(len(workflow.current_assessments(self.store, self.run)), 2)

    def test_input_change_invalidates_read_only_results_and_retains_history(self):
        before = self.upgrade(); subject = self.store.records(self.run, 'trigger_subjects')[0]
        case = self.store.get(self.run, 'cases', subject['case_id']); case['raw']['故障原因'] += '，变更触发前提'
        self.store.put(self.run, 'cases', case['case_id'], case, mutable=True)
        self.assertEqual(workflow.current_assessments(self.store, self.run), [])
        self.assertEqual(builder.current_execution(self.store, self.run), [])
        self.assertEqual(self.store.records(self.run, 'trigger_assessments'), before['trigger_assessments'])

    def test_current_validator_rejection_or_tampered_response_prevents_compatibility(self):
        before = self.upgrade()
        with patch('faultaudit.trigger_workflow.validate_assessment', side_effect=AuditError('new semantic gate')):
            self.assertEqual(workflow.current_assessments(self.store, self.run), [])
        old = copy.deepcopy(before['trigger_assessments'][0]); old['raw_response']['source_relation'] = 'MATCH'
        self.store.put(self.run, 'trigger_assessments', old['assessment_id'], old, mutable=True)
        self.assertEqual(len(workflow.current_assessments(self.store, self.run)), 1)
        self.assertEqual(len(builder.current_execution(self.store, self.run)), 1)

    def test_located_feedback_is_archived_with_rejected_attempt(self):
        from tests.v4_fixtures import v4_unknown
        self.start(1); self.advance()
        task = next(t for t in files.next_tasks(self.store, self.run)['tasks'] if t['kind']=='baseline_v4')
        request = self.request(task); response = self.response(request)
        row = next(v for v in v4_unknown(request['payload'], response)['v4_rows'] if v['trigger_id']=='S5')
        row.update(applicability='PARTIAL', condition_fact_ids=['F'], evidence_basis='SOURCE_DEFINITION',
                   source_cells=response['condition_facts'][0]['source_cells'], reason='合成输入线索')
        row['construction_checks'] = []
        response['v4_rows'] = [row]
        with self.assertRaises(ClassificationFeedback): self.submit(task, response)
        attempt = next(a for a in self.store.records(self.run, 'workflow_attempts') if a['task_id']==task['task_id'])
        self.assertEqual(attempt['status'], 'REJECTED')
        self.assertEqual(attempt['diagnostic']['row_id'], 'S5')
        self.assertEqual(attempt['diagnostic']['missing_fact_ids'], ['F'])
        self.assertEqual(json.loads(Path(attempt['response']).read_text(encoding='utf-8')), response)
