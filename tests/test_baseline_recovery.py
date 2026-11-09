"""Synthetic recovery only: no onsite database, website, model or device."""
import copy
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest
from unittest.mock import patch

from faultaudit import baseline_recovery as recovery, cann_baseline as builder
from faultaudit import xlsx_workflow as files, trigger_workflow as workflow
from faultaudit import run_budget
from faultaudit.input_budget import BUDGET_ENV, get_budget_chars, using_budget
from faultaudit.source_manifest import build, resolve, references_for_cells
from faultaudit.store import AuditError, Store, digest
from tests import test_cann_baseline as fixtures


class RecoveryFixture(unittest.TestCase):
    setUp = fixtures.BaselineBuilderTests.setUp
    tearDown = fixtures.BaselineBuilderTests.tearDown
    start = fixtures.BaselineBuilderTests.start
    request = fixtures.BaselineBuilderTests.request
    response = fixtures.BaselineBuilderTests.response
    submit = fixtures.BaselineBuilderTests.submit
    advance = fixtures.BaselineBuilderTests.advance

    def seed_history(self, subject, policy='1' * 64, quote=None):
        """Construct an old signed request and accepted legacy record, not a migration."""
        case = self.store.get(self.run, 'cases', subject['case_id'])
        payload = {'subject': {**subject, 'source_case': case},
            'original_mode': self.store.get(self.run, 'catalog', subject['mode_id']),
            'case_ids': [subject['case_id']], 'basis_hash': builder.definition_basis(self.store, self.run, subject),
            'response_schema': {'title': 'Synthetic legacy 0.1.18 definition contract'}}
        with patch('faultaudit.xlsx_workflow._policy', return_value=policy):
            task = files._request(self.store, self.run, files.config(self.store, self.run),
                                  'baseline_define', payload, 'Synthetic historical A1 instructions', 3)
        request = self.request(task)
        view = copy.deepcopy(request)
        view['payload']['source_manifest'] = build(case)
        response = self.response(view)
        for fact in response['condition_facts']:
            fact.pop('source_refs', None)
            if quote is not None:
                fact['statement'] = quote
                fact['source_cells'][0]['quote'] = quote
        if quote is not None:
            for field in builder.FIELDS:
                response['definition'][field]['text'] = quote
        value, facts = builder.validate_common(payload, response, builder.DefinitionResponse, request['request_hash'])
        result = {**value.definition.model_dump(), 'condition_facts': [f.model_dump(exclude={'source_refs'}) for f in facts.values()],
            'basis': 'MODE_DEFINITION', 'source_case_id': case['case_id'], 'evidence_refs': [],
            'validation_status': {'MODE_DEFINITION': 'REVIEWED_BY_AGENT', 'HISTORICAL_EVIDENCE': 'NOT_VERIFIED',
                                  'SOURCE_VERIFIED': False, 'HARDWARE_VALIDATED': False}}
        record = {'definition_id': task['task_id'], 'subject_id': subject['subject_id'], 'case_id': case['case_id'],
                  'basis_hash': payload['basis_hash'], 'policy_hash': policy, 'raw_response': response, 'result': result}
        self.store.put(self.run, 'mode_definitions', task['task_id'], record)
        self.store.put(self.run, 'workflow_results', task['task_id'],
                       {'task_id': task['task_id'], 'response': response, 'response_hash': digest(response)})
        self.store.put(self.run, 'workflow_attempts', digest([task['task_id'], 'synthetic-old-attempt']),
                       {'task_id': task['task_id'], 'status': 'ACCEPTED', 'response_hash': digest(response)})
        return record

    def compatibility_response(self, request, *, decision='REUSE', selected=None):
        payload = request['payload']
        values = payload['historical_definitions']
        chosen = next(c for c in values if c['definition_id'] == selected) if selected else values[0]
        checks = []
        facts = {f['fact_id']: f for f in chosen['result']['condition_facts']}
        for field in builder.FIELDS:
            claim = chosen['result'][field]
            cells = [cell for key in claim['condition_fact_ids'] for cell in facts[key]['source_cells']]
            checks.append({'field': field, 'verdict': 'UNKNOWN' if claim['status'] == 'UNKNOWN' else 'SUPPORTED',
                           'reason': '合成语义协议样例，引用对应原始声明；不声称真实故障被核验',
                           'source_refs': references_for_cells(payload['source_manifest'], cells)})
        _, template = fixtures.fixture()
        return {'request_hash': request['request_hash'], 'case_id': payload['subject']['case_id'],
            'executor': 'codex', 'producer': template['producer'], 'self_check': template['self_check'],
            'decision': decision, 'selected_definition_id': chosen['definition_id'] if decision == 'REUSE' else None,
            'field_checks': checks, 'version_checks': [{'definition_id': c['definition_id'],
                'verdict': 'SELECTED' if c == chosen and decision == 'REUSE' else 'EQUIVALENT',
                'reason': '合成两版完整对照，未将记录数量变化当成技术变化'} for c in values],
            'reason': '明确的合成复核声明；不是自动迁移或人工ACCEPT'}


class RunBudgetTests(RecoveryFixture):
    def test_pinned_160000_survives_default_env_and_direct_queries(self):
        self.start(1, input_budget_chars=160000)
        with patch.dict(os.environ, {BUDGET_ENV: '48000'}):
            task = files.next_tasks(self.store, self.run)['tasks'][0]
            request = self.request(task)
            self.assertEqual(request['input_budget']['budget'], 160000)
            self.submit(task)
            self.assertEqual(len(builder.current_definitions(self.store, self.run)), 1)
            self.assertEqual(recovery.recovery_plan(self.store, self.run)['budget']['pinned']['budget'], 160000)
            self.assertEqual(get_budget_chars(), 48000)
        self.assertEqual(os.environ[BUDGET_ENV], '240000')

    def test_old_unpinned_run_is_readable_but_cannot_plan_or_submit(self):
        self.start(1, input_budget_chars=160000)
        task = files.next_tasks(self.store, self.run)['tasks'][0]
        with self.store.conn:
            self.store.conn.execute('DELETE FROM records WHERE run_id=? AND kind=?', (self.run, run_budget.KIND))
        self.assertEqual(recovery.recovery_plan(self.store, self.run)['budget']['status'], 'UNPINNED')
        with self.assertRaisesRegex(AuditError, 'RUN_BUDGET_UNPINNED'):
            files.next_tasks(self.store, self.run)
        with self.assertRaisesRegex(AuditError, 'RUN_BUDGET_UNPINNED'):
            self.submit(task)
        with self.assertRaisesRegex(AuditError, 'historical'):
            run_budget.pin(self.store, self.run, 48000)
        run_budget.pin(self.store, self.run, 160000)
        self.assertTrue(run_budget.pin(self.store, self.run, 160000)['idempotent'])
        with self.assertRaisesRegex(AuditError, 'frozen'):
            run_budget.pin(self.store, self.run, 170000)
        self.submit(task)

    def test_context_isolation_and_generator_does_not_leak_budget(self):
        self.start(1, input_budget_chars=160000)
        generator = builder.payloads(self.store, self.run)
        next(generator)
        self.assertEqual(get_budget_chars(), 240000)
        generator.close()
        def read(chars):
            with using_budget(chars):
                return [get_budget_chars() for _ in range(25)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(read, [160000, 80000]))
        self.assertEqual(values, [[160000] * 25, [80000] * 25])
        self.assertEqual(get_budget_chars(), 240000)

    def test_readonly_recovery_preview_does_not_touch_database_or_create_tasks(self):
        self.start(1, input_budget_chars=160000)
        self.seed_history(self.store.records(self.run, 'trigger_subjects')[0])
        before = (self.root / 'state/audit.sqlite3').read_bytes()
        requests = self.store.records(self.run, 'workflow_requests')
        ro = Store(self.root / 'state', read_only=True)
        try:
            result = recovery.recovery_plan(ro, self.run)
        finally:
            ro.close()
        self.assertEqual(result['compatibility_pending_modes'], 1)
        self.assertEqual(result['state_writes'], 0)
        self.assertEqual((self.root / 'state/audit.sqlite3').read_bytes(), before)
        self.assertEqual(self.store.records(self.run, 'workflow_requests'), requests)


class ManifestTests(RecoveryFixture):
    def test_manifest_must_match_store_source_not_only_the_request_copy(self):
        self.start(1)
        payload = next(builder.payloads(self.store, self.run))
        payload['subject']['source_case']['raw']['故障原因'] = '伪造请求副本中的原始事实'
        payload['source_manifest'] = build(payload['subject']['source_case'])
        task = files._request(self.store, self.run, files.config(self.store, self.run),
                              'baseline_define', payload, builder.INSTRUCTIONS, 3)
        with self.assertRaisesRegex(AuditError, 'frozen original'):
            self.submit(task, self.response(self.request(task)))
        self.assertEqual(builder.current_definitions(self.store, self.run), [])

    def test_blank_and_multiline_headers_bind_by_id_without_guessing(self):
        from openpyxl import Workbook
        book = Workbook(); sheet = book.active
        sheet.append(['故障模式编号', '模式名称', '一级\n(架构层次)', '故障原因', None])
        sheet.append(['SYN-0', '合成模式', '芯片使能', '内部算址溢出', 'https://example.org/issue'])
        book.save(self.modes)
        cfg = workflow.start_init(self.store, self.modes, self.taxonomy, self.root / 'work', executor='codex',
            v4_source=self.v4, baseline_builder=True, expected_mode_count=1, input_budget_chars=160000)
        self.run = cfg['run_id']
        task = files.next_tasks(self.store, self.run)['tasks'][0]; request = self.request(task)
        manifest = request['payload']['source_manifest']
        last = next(e for e in manifest['entries'] if e['column_key'] == '__column_5')
        self.assertEqual(resolve(manifest, [{'source_id': last['source_id'], 'quote': last['original_value']}]),
                         [{'field': '__column_5', 'cell': 'E2', 'quote': last['original_value']}])
        self.assertIn('一级\n(架构层次)', [e['column_key'] for e in manifest['entries']])
        response = self.response(request)
        response['condition_facts'][0]['source_cells'] = []
        self.submit(task, response)
        fact = builder.current_definitions(self.store, self.run)[0]['result']['condition_facts'][0]
        self.assertEqual(fact['source_cells'][0]['cell'], 'D2')
        self.assertNotIn('source_refs', fact)

    def test_invalid_id_quote_or_alias_and_missing_manifest_refs_are_rejected(self):
        self.start(1)
        task = files.next_tasks(self.store, self.run)['tasks'][0]
        response = self.response(self.request(task))
        mutations = [lambda r:r['condition_facts'][0]['source_refs'][0].update(source_id='source-not-real'),
            lambda r:r['condition_facts'][0]['source_refs'][0].update(quote='invented'),
            lambda r:r['condition_facts'][0]['source_cells'][0].update(field='human readable alias'),
            lambda r:r['condition_facts'][0].update(source_refs=[])]
        for mutate in mutations:
            invalid = copy.deepcopy(response); mutate(invalid)
            with self.assertRaises(AuditError): self.submit(task, invalid)
        self.assertEqual(builder.current_definitions(self.store, self.run), [])
        self.submit(task, response)

    def test_inference_and_gaps_do_not_masquerade_as_original_facts(self):
        self.start(1)
        task = files.next_tasks(self.store, self.run)['tasks'][0]
        response = self.response(self.request(task))
        response['definition']['failure_mechanism'].update(status='INFERRED')
        with self.assertRaisesRegex(AuditError, 'derivation_reason'): self.submit(task, response)
        response['definition']['failure_mechanism']['derivation_reason'] = '按源故障原因推导；不是逐字原文'
        response['definition']['input_trigger_conditions'] = {'text': '未提供API前提', 'status': 'UNKNOWN', 'condition_fact_ids': []}
        response['evidence_gaps'] = ['历史网页正文未核验']
        self.submit(task, response)
        result = builder.current_definitions(self.store, self.run)[0]['result']
        self.assertEqual(result['input_trigger_conditions']['status'], 'UNKNOWN')
        self.assertEqual(result['evidence_gaps'], ['历史网页正文未核验'])
        self.assertFalse(result['validation_status']['SOURCE_VERIFIED'])


class CompatibilityTests(RecoveryFixture):
    def set_up_history(self, versions=1):
        self.start(1, input_budget_chars=160000)
        subject = self.store.records(self.run, 'trigger_subjects')[0]
        records = [self.seed_history(subject, str(i+1) * 64) for i in range(versions)]
        task = files.next_tasks(self.store, self.run)['tasks'][0]
        self.assertEqual(task['kind'], 'baseline_compatibility')
        return subject, records, task, self.request(task)

    def test_structural_pass_does_not_automatically_accept_history(self):
        _, records, _, _ = self.set_up_history()
        self.assertEqual(builder.current_definitions(self.store, self.run), [])
        preview = recovery.recovery_plan(self.store, self.run)
        self.assertEqual(preview['compatibility_pending_modes'], 1)
        self.assertEqual(preview['matrix'][0]['historical_candidates'][0]['precheck']['structural_status'], 'PASS')
        self.assertEqual(self.store.get(self.run, 'mode_definitions', records[0]['definition_id']), records[0])
        self.assertEqual(self.store.records(self.run, 'reviews'), [])

    def test_explicit_semantic_reuse_preserves_two_versions_and_produces_one_current_definition(self):
        _, records, task, request = self.set_up_history(2)
        response = self.compatibility_response(request, selected=records[1]['definition_id'])
        self.submit(task, response)
        current = builder.current_definitions(self.store, self.run)
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]['historical_definition_id'], records[1]['definition_id'])
        for old in records:
            self.assertEqual(self.store.get(self.run, 'mode_definitions', old['definition_id']), old)
        self.assertEqual(len(self.store.records(self.run, 'mode_definitions')), 3)
        self.assertEqual(self.store.records(self.run, 'reviews'), [])
        self.assertFalse(current[0]['result']['validation_status']['SOURCE_VERIFIED'])
        next_batch = files.next_tasks(self.store, self.run)
        self.assertEqual(sorted(t['kind'] for t in next_batch['tasks']), ['baseline_api42','baseline_execution','baseline_v4'])
        self.assertEqual(next_batch, files.next_tasks(self.store, self.run))

    def test_missing_field_version_or_citation_cannot_be_reused(self):
        _, _, task, request = self.set_up_history(2)
        response = self.compatibility_response(request)
        for mutate in (lambda r:r['field_checks'].pop(), lambda r:r['version_checks'].pop(),
            lambda r:r['field_checks'][0].update(source_refs=[]),
            lambda r:r['field_checks'][0].update(verdict='CONFLICT'),
            lambda r:r.update(review_status='ACCEPT'),
            lambda r:r['self_check'].update(counterevidence_checked=False)):
            invalid = copy.deepcopy(response); mutate(invalid)
            with self.assertRaises(AuditError): self.submit(task, invalid)
        self.assertEqual(builder.current_definitions(self.store, self.run), [])

    def test_conflict_is_blocked_instead_of_repeat_review_or_define(self):
        _, _, task, request = self.set_up_history()
        self.submit(task, self.compatibility_response(request, decision='CONFLICT'))
        next_batch = files.next_tasks(self.store, self.run)
        self.assertEqual(next_batch['status'], 'BLOCKED')
        self.assertEqual(next_batch['tasks'], [])
        preview = recovery.recovery_plan(self.store, self.run)
        self.assertEqual(preview['conflict_modes'], 1)
        self.assertEqual(builder.current_definitions(self.store, self.run), [])

    def test_regenerate_is_explicit_and_not_an_automatic_history_rewrite(self):
        _, records, task, request = self.set_up_history()
        self.submit(task, self.compatibility_response(request, decision='REGENERATE'))
        new_task = files.next_tasks(self.store, self.run)['tasks'][0]
        self.assertEqual(new_task['kind'], 'baseline_define')
        context = self.request(new_task)['payload']['compatibility_regeneration']
        self.assertEqual(context['review']['decision'], 'REGENERATE')
        self.assertEqual(context['review_id'], task['task_id'])
        self.submit(new_task)
        self.assertEqual(len(builder.current_definitions(self.store, self.run)), 1)
        self.assertEqual(self.store.get(self.run, 'mode_definitions', records[0]['definition_id']), records[0])

    def test_review_quote_may_narrow_original_fact_but_not_escape_its_span(self):
        self.start(1)
        subject = self.store.records(self.run, 'trigger_subjects')[0]
        old = self.seed_history(subject, quote='同一调用发生同步竞争')
        task = files.next_tasks(self.store, self.run)['tasks'][0]
        request = self.request(task)
        response = self.compatibility_response(request)
        response['field_checks'][0]['source_refs'][0]['quote'] = '输出有残留'
        with self.assertRaisesRegex(AuditError, 'original supporting facts'):
            self.submit(task, response)
        for check in response['field_checks']:
            check['source_refs'][0]['quote'] = '同步竞争'
        self.submit(task, response)
        current = builder.current_definitions(self.store, self.run)[0]
        self.assertEqual(current['result']['failure_mechanism']['text'], '同一调用发生同步竞争')
        self.assertEqual(self.store.get(self.run, 'mode_definitions', old['definition_id']), old)

    def test_changed_source_stales_review_without_changing_accepted_history(self):
        subject, records, task, request = self.set_up_history()
        case = self.store.get(self.run, 'cases', subject['case_id'])
        case['raw']['故障原因'] += '，定义改变'
        self.store.put(self.run, 'cases', case['case_id'], case, mutable=True)
        with self.assertRaisesRegex(AuditError, 'changed'):
            self.submit(task, self.compatibility_response(request))
        self.assertEqual(files.next_tasks(self.store, self.run)['tasks'][0]['kind'], 'baseline_define')
        self.assertEqual(self.store.get(self.run, 'mode_definitions', records[0]['definition_id']), records[0])

    def test_tampered_archived_response_cannot_be_structurally_promoted(self):
        self.start(1)
        subject = self.store.records(self.run, 'trigger_subjects')[0]
        old = self.seed_history(subject)
        changed = copy.deepcopy(old); changed['raw_response']['definition']['failure_mechanism']['text'] = 'tampered'
        self.store.put(self.run, 'mode_definitions', old['definition_id'], changed, mutable=True)
        plan = recovery.recovery_plan(self.store, self.run)
        self.assertEqual(plan['definition_required_modes'], 1)
        self.assertEqual(plan['matrix'][0]['historical_candidates'][0]['precheck']['structural_status'], 'FAIL')

    def test_old_request_is_not_accepted_even_after_a_successful_compatibility_review(self):
        _, records, task, request = self.set_up_history()
        self.submit(task, self.compatibility_response(request))
        with self.assertRaisesRegex(AuditError, 'policy'):
            files.submit(self.store, self.run, records[0]['definition_id'], records[0]['raw_response'])

    def test_compatibility_context_limit_remains_blocked_and_never_current(self):
        _, _, task, request = self.set_up_history()
        result = self.submit(task, {'request_hash': request['request_hash'], 'outcome': 'BLOCKED',
            'reason_code': 'EXECUTOR_CONTEXT_LIMIT', 'reason': 'synthetic complete input cannot be processed'})
        self.assertTrue(result['blocked'])
        self.assertEqual(builder.current_definitions(self.store, self.run), [])
        batch = files.next_tasks(self.store, self.run)
        self.assertEqual(batch['status'], 'BLOCKED')
        self.assertEqual(batch['tasks'], [])

    def test_rejected_original_and_unsubmitted_variant_are_reviewed_without_retry_feedback_loop(self):
        self.start(1)
        with patch('faultaudit.xlsx_workflow._policy', return_value='1' * 64):
            old_task = files.next_tasks(self.store, self.run)['tasks'][0]
            original = self.response(self.request(old_task))
            original['condition_facts'][0]['source_refs'][0]['quote'] = 'invented'
            with self.assertRaises(AuditError): self.submit(old_task, original)
        attempt = self.store.records(self.run, 'workflow_attempts')[0]
        path = Path(attempt['response'])
        original_bytes = path.read_bytes()
        current = files.next_tasks(self.store, self.run)['tasks'][0]
        context = self.request(current)['payload']['historical_rejected_inputs'][0]
        self.assertEqual(context['files'][0]['role'], 'ORIGINAL_REJECTED')
        self.assertEqual(context['files'][0]['response_hash'], attempt['response_hash'])
        # Missing response.rejected.json alone did not make the original disappear.
        path.with_name('response.rejected.json').write_bytes(original_bytes)
        repaired = self.response(self.request(old_task))
        path.write_text(json.dumps(repaired, ensure_ascii=False), encoding='utf-8')
        current = files.next_tasks(self.store, self.run)['tasks'][0]
        roles = {f['role'] for f in self.request(current)['payload']['historical_rejected_inputs'][0]['files']}
        self.assertEqual(roles, {'ORIGINAL_REJECTED', 'UNSUBMITTED_VARIANT'})
        response = self.response(self.request(current))
        response['condition_facts'][0]['source_refs'][0]['quote'] = 'still invalid'
        with self.assertRaises(AuditError): self.submit(current, response)
        # Current-policy failures must retry this task, not grow a new task per attempt.
        self.assertEqual(files.next_tasks(self.store, self.run)['tasks'][0]['task_id'], current['task_id'])
        self.assertEqual(path.with_name('response.rejected.json').read_bytes(), original_bytes)
        self.assertEqual(builder.current_definitions(self.store, self.run), [])


class DownstreamRecoveryTests(RecoveryFixture):
    def test_builder_axis_direct_entry_requires_current_signed_request(self):
        self.start(1); self.advance()
        task = next(t for t in files.next_tasks(self.store, self.run)['tasks'] if t['kind']=='baseline_v4')
        request = self.request(task)
        bare = {k: request[k] for k in ('task_id', 'request_hash', 'payload')}
        with self.assertRaisesRegex(AuditError, 'policy'):
            workflow.accept_assessment(self.store, self.run, bare, self.response(request))
        self.assertEqual(workflow.current_assessments(self.store, self.run), [])

    def test_thirty_mode_historical_split_then_ninety_current_stage_tasks(self):
        self.start(30, input_budget_chars=160000)
        subjects = sorted(self.store.records(self.run, 'trigger_subjects'), key=lambda s:int(s['mode_id'].split('-')[1]))
        histories = [self.seed_history(s) for s in subjects[:18]]
        histories += [self.seed_history(s, '2' * 64) for s in subjects[:2]]
        old_hashes = {r['definition_id']: digest(r) for r in histories}
        batch = files.next_tasks(self.store, self.run)
        self.assertEqual(sum(t['kind']=='baseline_compatibility' for t in batch['tasks']), 18)
        self.assertEqual(sum(t['kind']=='baseline_define' for t in batch['tasks']), 12)
        for task in batch['tasks']:
            request = self.request(task)
            response = self.compatibility_response(request) if task['kind']=='baseline_compatibility' else self.response(request)
            self.submit(task, response)
        self.assertEqual(len(builder.current_definitions(self.store, self.run)), 30)
        stages = files.next_tasks(self.store, self.run)
        self.assertEqual(len(stages['tasks']), 90)
        self.assertEqual(len({t['task_id'] for t in stages['tasks']}), 90)
        self.assertEqual(stages, files.next_tasks(self.store, self.run))
        for task in stages['tasks']:
            self.assertEqual(self.request(task)['input_budget']['budget'], 160000)
        for key, old_hash in old_hashes.items():
            self.assertEqual(digest(self.store.get(self.run, 'mode_definitions', key)), old_hash)
        self.assertEqual(recovery.recovery_plan(self.store, self.run)['expected_downstream_units'], 90)
        self.assertEqual(self.store.records(self.run, 'reviews'), [])

    def test_reference_update_affects_execution_but_preserves_classification(self):
        self.start(1, input_budget_chars=160000); self.advance(); self.advance()
        before = workflow.current_assessments(self.store, self.run)
        self.assertEqual(len(before), 2)
        self.assertEqual(len(builder.current_execution(self.store, self.run)), 1)
        case_id = self.store.records(self.run, 'cases')[0]['case_id']
        self.store.put(self.run, 'references', 'synthetic-new-link',
            {'ref_id':'synthetic-new-link','case_id':case_id,'url':'https://example.org/new-proof'})
        self.assertEqual(workflow.current_assessments(self.store, self.run), before)
        self.assertEqual(builder.current_execution(self.store, self.run), [])
        kinds = [t['kind'] for t in files.next_tasks(self.store, self.run)['tasks']]
        self.assertEqual(kinds, ['baseline_execution'])

    def test_provenance_only_record_refresh_does_not_change_technical_dependency(self):
        self.start(1, input_budget_chars=160000); self.advance(); self.advance()
        subject = self.store.records(self.run, 'trigger_subjects')[0]
        before = recovery.axis_basis(self.store, self.run, subject, 'V4')
        record = copy.deepcopy(builder.current_definitions(self.store, self.run)[0])
        record['definition_id'] = 'synthetic-provenance-refresh'
        record['result']['evidence_refs'] = [{'note':'synthetic additional provenance, no technical change'}]
        manifest = build(self.store.get(self.run, 'cases', subject['case_id']))
        recovery.save_definition(self.store, self.run, record, manifest)
        self.assertEqual(recovery.axis_basis(self.store, self.run, subject, 'V4'), before)
        self.assertEqual(len(workflow.current_assessments(self.store, self.run)), 2)
        self.assertEqual(len(builder.current_definitions(self.store, self.run)), 1)

    def test_unrelated_mode_does_not_invalidate_this_modes_classification(self):
        self.start(2); self.advance(); self.advance()
        subjects = self.store.records(self.run, 'trigger_subjects')
        original = [a for a in workflow.current_assessments(self.store, self.run) if a['subject_id']==subjects[0]['subject_id']]
        other = self.store.get(self.run, 'catalog', subjects[1]['mode_id'])
        other['mechanism'] += '，另一模式定义更新'
        self.store.put(self.run, 'catalog', other['item_id'], other, mutable=True)
        current = [a for a in workflow.current_assessments(self.store, self.run) if a['subject_id']==subjects[0]['subject_id']]
        self.assertEqual(current, original)
        self.assertEqual(len(current), 2)
