"""Frozen target selection, body-repair dispatch and independent task inputs."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from faultaudit import xlsx_workflow as workflow
from faultaudit.pipeline import report_data, validate, fetch_tasks
from faultaudit.store import AuditError
from faultaudit.workflow_scope import scoped_store
from tests import test_xlsx_workflow as fixtures


class WorkflowScopeTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.XlsxWorkflowTests()
        self.fx.setUp()

    def tearDown(self):
        self.fx.tearDown()

    def test_232_target_records_do_not_schedule_430_historical_records(self):
        rows = [[f'SYN-{i}', f'Synthetic output differs {i}', 'Unknown',
                 'https://example.invalid/wiki/shared', '', 'P1'] for i in range(662)]
        self.fx.write_source(rows)
        from faultaudit.importers import import_cases
        cases = import_cases(self.fx.source)['cases']
        selected = [case['case_id'] for case in cases[:232]]
        result = workflow.start(self.fx.store, self.fx.source, self.fx.catalog, self.fx.work,
                                executor='codex', case_ids=selected)
        run = result['run_id']
        self.assertEqual(len(self.fx.store.records(run, 'cases')), 662)
        view = scoped_store(self.fx.store, run)
        self.assertEqual(len(view.records(run, 'cases')), 232)
        step = workflow.next_tasks(self.fx.store, run)
        self.assertEqual(len(step['wiki_checks']), 232)
        tasks = step['tasks']
        self.assertEqual(len(tasks), 1)
        request = json.loads(Path(tasks[0]['request']).read_text('utf-8'))
        self.assertEqual(set(request['payload']['case_ids']), set(selected))
        self.assertEqual(len(request['payload']['reference_ids']), 232)
        self.assertNotIn('cases', request['payload'])
        self.assertTrue(request['execution_context']['new_session_required'])
        self.assertEqual(request['execution_context']['history'], 'THIS_TASK_ONLY')
        self.assertFalse(validate(view, run)['errors'])
        data = report_data(view, run)
        self.assertEqual({case['case_id'] for case in data['cases']}, set(selected))
        self.assertEqual(len(self.fx.store.records(run, 'cases')), 662)
        with self.assertRaisesRegex(AuditError, 'scope is frozen'):
            workflow.start(self.fx.store, self.fx.source, self.fx.catalog, self.fx.work,
                           executor='codex', run_id=run, case_ids=[cases[-1]['case_id']])

    def test_title_only_capture_is_retained_and_repaired_not_summarized(self):
        self.fx.start()
        run = self.fx.run
        first = workflow.next_tasks(self.fx.store, run)['tasks'][0]
        request = self.fx.load_request(first)
        package = self.fx.package(request['payload']['url'])
        package.update(title='Only a title', text='Only a title', components={'body': 'PARTIAL'})
        package['capture_observation'].update(page_kind='TITLE_ONLY', title='Only a title', body_quotes=[], body_locator='')
        workflow.submit(self.fx.store, run, first['task_id'],
                        {'request_hash': request['request_hash'], 'outcome': 'CAPTURED', 'packages': [package]})
        step = workflow.next_tasks(self.fx.store, run)
        self.assertTrue(any(task['kind'] == 'fetch' for task in step['tasks']))
        self.assertFalse(any(task['kind'] == 'model' for task in step['tasks']))
        self.assertNotEqual(step['wiki_checks'][next(iter(step['wiki_checks']))]['status'], 'FOUND')
        repair = next(task for task in step['tasks'] if task['kind'] == 'fetch')
        self.assertIn('repair_capture', self.fx.load_request(repair)['payload'])
        self.assertEqual(len(self.fx.store.records(run, 'snapshots')), 1)
        body = self.fx.response(repair)
        workflow.submit(self.fx.store, run, repair['task_id'], body)
        ready = workflow.next_tasks(self.fx.store, run)
        self.assertTrue(any(task['kind'] == 'model' for task in ready['tasks']))
        self.assertEqual(len(self.fx.store.records(run, 'snapshots')), 2)

    def test_repeated_empty_page_repairs_stop_with_explicit_gap(self):
        self.fx.start()
        run = self.fx.run
        for _ in range(3):
            task = next(t for t in workflow.next_tasks(self.fx.store, run)['tasks'] if t['kind'] == 'fetch')
            req = self.fx.load_request(task)
            package = self.fx.package(req['payload']['url'])
            package.update(title='Index', text='Child A', components={'body': 'PARTIAL'})
            package['capture_observation'].update(page_kind='INDEX', body_quotes=[], body_locator='', title='Index')
            workflow.submit(self.fx.store, run, task['task_id'],
                            {'request_hash': req['request_hash'], 'outcome': 'CAPTURED', 'packages': [package]})
        step = workflow.next_tasks(self.fx.store, run)
        self.assertFalse(any(t['kind'] == 'fetch' for t in step['tasks']))
        state = self.fx.store.get(run, 'workflow_state', 'current')
        self.assertTrue(any(self.fx.store.get(run, 'workflow_blocks', key)['reason'] == 'PAGE_BODY_UNAVAILABLE'
                            for key in state['block_ids']))

    def test_same_pr_comment_alias_has_one_fetch_and_all_source_occurrences(self):
        self.fx.start([['SYN-A', 'Synthetic A', 'Unknown', '', 'https://github.com/Example/Repo/pull/1', 'P1'],
                       ['SYN-B', 'Synthetic B', 'Unknown', '', 'https://github.com/example/repo/pull/1?utm_source=x#discussion_r1', 'P1']])
        run = self.fx.run
        tasks = workflow.next_tasks(self.fx.store, run)['tasks']
        fetches = [t for t in tasks if t['kind'] == 'fetch']
        self.assertEqual(len(fetches), 1)
        req = self.fx.load_request(fetches[0])
        self.assertEqual(len(req['payload']['reference_ids']), 2)
        workflow.submit(self.fx.store, run, fetches[0]['task_id'], self.fx.response(fetches[0]))
        self.assertEqual(len(fetch_tasks(scoped_store(self.fx.store, run), run)['fetch_tasks']), 0)
        self.assertEqual(len(self.fx.store.records(run, 'references')), 2)
        self.assertEqual(self.fx.store.records(run, 'event_groups'), [])

    def test_index_navigation_supplies_independent_child_without_repeated_parent_fetch(self):
        self.fx.start()
        run = self.fx.run
        initial = workflow.next_tasks(self.fx.store, run)['tasks'][0]
        request = self.fx.load_request(initial)
        parent = self.fx.package(request['payload']['url'])
        child_url = 'https://wiki.example.invalid/WIKI123'
        parent.update(title='Index', text='Fault details: '+child_url, components={'body': 'PARTIAL'})
        parent['capture_observation'].update(page_kind='INDEX', title='Index', body_quotes=[], body_locator='')
        workflow.submit(self.fx.store, run, initial['task_id'],
                        {'request_hash':request['request_hash'], 'outcome':'CAPTURED', 'packages':[parent]})
        repair = next(t for t in workflow.next_tasks(self.fx.store, run)['tasks'] if t['kind']=='fetch')
        req = self.fx.load_request(repair)
        self.assertEqual(req['payload']['navigation_targets'][0]['description'], 'Synthetic output differs')
        child = self.fx.package(child_url)
        workflow.submit(self.fx.store, run, repair['task_id'], {'request_hash':req['request_hash'],
            'outcome':'CAPTURED', 'packages':[parent], 'linked_packages':[
                {'package':child, 'case_ids':req['payload']['case_ids'], 'navigation_quote':'Fault details: '+child_url}]})
        step=workflow.next_tasks(self.fx.store, run)
        self.assertFalse(any(t['kind']=='fetch' for t in step['tasks']))
        self.assertTrue(any(t['kind']=='model' for t in step['tasks']))
        refs=self.fx.store.records(run,'references')
        self.assertTrue(any(r['origin']=='LINK_DISCOVERED' and r['parent_url']==parent['url'] for r in refs))
        self.assertEqual(len(self.fx.store.records(run,'snapshots')),2)

    def test_empty_selection_is_rejected_instead_of_running_all_cases(self):
        self.fx.write_source()
        with self.assertRaisesRegex(AuditError,'nonempty JSON array'):
            workflow.start(self.fx.store,self.fx.source,self.fx.catalog,self.fx.work,executor='codex',case_ids=[])

    def test_manual_capacity_block_can_be_retried_without_a_fake_success(self):
        self.fx.start()
        run=self.fx.run
        fetch=workflow.next_tasks(self.fx.store,run)['tasks'][0]
        workflow.submit(self.fx.store,run,fetch['task_id'],self.fx.response(fetch))
        task=next(t for t in workflow.next_tasks(self.fx.store,run)['tasks'] if t['kind']=='model')
        req=self.fx.load_request(task)
        blocked=workflow.submit(self.fx.store,run,task['task_id'],{'request_hash':req['request_hash'],
            'outcome':'BLOCKED','reason_code':'EXECUTOR_CONTEXT_LIMIT','reason':'Synthetic worker cannot read full input'})
        self.assertTrue(blocked['blocked'])
        self.assertEqual(self.fx.store.records(run,'model_results'),[])
        self.assertIsNone(self.fx.store.get(run,'workflow_results',task['task_id']))
        self.assertFalse(any(t['task_id']==task['task_id'] for t in workflow.next_tasks(self.fx.store,run)['tasks']))
        workflow.retry(self.fx.store,run,task['task_id'])
        self.assertTrue(any(t['task_id']==task['task_id'] for t in workflow.next_tasks(self.fx.store,run)['tasks']))

    def test_manual_login_wait_and_retry_do_not_duplicate_fetch(self):
        self.fx.start()
        run=self.fx.run
        task=workflow.next_tasks(self.fx.store,run)['tasks'][0]
        req=self.fx.load_request(task)
        blocked={'request_hash':req['request_hash'],'outcome':'BLOCKED','reason':'Synthetic login required',
            'packages':[{'url':req['payload']['url'],'text':'','status':'AUTH_REQUIRED',
                         'components':{'body':'AUTH_REQUIRED'},'is_synthetic':True}]}
        workflow.submit(self.fx.store,run,task['task_id'],blocked)
        step=workflow.next_tasks(self.fx.store,run)
        self.assertFalse(any(t['kind']=='fetch' for t in step['tasks']))
        self.assertEqual(len(self.fx.store.events(run,'workflow_auth_handoff')),1)
        workflow.retry(self.fx.store,run,task['task_id'])
        step=workflow.next_tasks(self.fx.store,run)
        fetches=[t for t in step['tasks'] if t['kind']=='fetch']
        self.assertEqual(len(fetches),1)
        self.assertEqual(fetches[0]['task_id'],task['task_id'])

    def test_explicit_network_block_is_not_turned_into_automatic_capture_repair(self):
        self.fx.start()
        run=self.fx.run
        task=workflow.next_tasks(self.fx.store,run)['tasks'][0]
        req=self.fx.load_request(task)
        workflow.submit(self.fx.store,run,task['task_id'],{'request_hash':req['request_hash'],'outcome':'BLOCKED',
            'reason':'Synthetic network unavailable','packages':[{'url':req['payload']['url'],'text':'',
                'status':'NETWORK_BLOCKED','components':{'body':'NETWORK_BLOCKED'},'is_synthetic':True}]})
        self.assertFalse(any(t['kind']=='fetch' for t in workflow.next_tasks(self.fx.store,run)['tasks']))


if __name__ == '__main__':
    unittest.main()
