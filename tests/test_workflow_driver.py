"""Synthetic scheduling tests; these do not claim real Agent/site execution."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from faultaudit import xlsx_workflow as workflow
from faultaudit.store import AuditError, Store, digest
from faultaudit.workflow_driver import drive, reset_execution, run_lock


class CoordinatorStore(Store):
    """An actual SQLite connection which rejects all worker-thread access."""
    def __init__(self, root):
        self.owner = threading.get_ident()
        super().__init__(root)

    def put(self, *args, **kwargs):
        assert threading.get_ident() == self.owner, "Worker attempted a SQLite write"
        return super().put(*args, **kwargs)

    def get(self, *args, **kwargs):
        assert threading.get_ident() == self.owner, "Worker attempted a SQLite read"
        return super().get(*args, **kwargs)


class WorkflowDriverTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).parent / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="continuous-driver-", dir=scratch)
        self.root = Path(self.temp.name)
        self.store = CoordinatorStore(self.root / "state")
        self.run = self.store.create_run()
        self.directory = self.root / "runs" / self.run
        self.store.put(self.run, "xlsx_workflow", "config", {"directory": str(self.directory), "executor": "codex"})
        self.tasks = []
        self.command = ["synthetic-agent", "{request}", "{response}"]

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def task(self, task_id, kind="model", url=""):
        request = {"task_id": task_id, "kind": kind, "payload": {"case_ids": ["SYN-CASE-" + task_id], "url": url}}
        request["request_hash"] = digest(request)
        path = self.directory / "tasks" / task_id / "request.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(request), encoding="utf-8")
        self.store.put(self.run, "workflow_requests", task_id, request)
        self.tasks.append({"task_id": task_id, "kind": kind, "request": str(path)})
        return self.tasks[-1]

    def next(self, store, run):
        tasks = []
        for task in self.tasks:
            result = store.get(run, "workflow_results", task["task_id"])
            if not result or result.get("retry"):
                tasks.append({**task, "response": str(workflow.response_path(store, run, task["task_id"]))})
        store.put(run, "workflow_state", "current", {"task_ids": [t["task_id"] for t in tasks], "block_ids": []}, mutable=True)
        return {"tasks": tasks}

    def submit(self, store, run, task_id, response, *, path=None):
        if response.get("task_id") != task_id:
            raise AuditError("Synthetic response has wrong task identity")
        old = store.get(run, "workflow_results", task_id)
        if old and not old.get("retry"):
            return {"idempotent": True}
        store.put(run, "workflow_results", task_id, response, mutable=bool(old))
        store.put(run, "workflow_attempts", digest([task_id, str(path)]),
                  {"task_id": task_id, "status": "ACCEPTED", "response": str(path)})
        return {"accepted": True}

    def export(self, store, run):
        state = store.get(run, "workflow_state", "current")
        return {"status": "COMPLETE_WITH_PENDING" if state["task_ids"] or state["block_ids"] else "COMPLETE"}

    def run_driver(self, producer, **options):
        with patch.object(workflow, "next_tasks", side_effect=self.next), \
             patch.object(workflow, "submit", side_effect=self.submit), \
             patch.object(workflow, "export", side_effect=self.export), \
             patch("faultaudit.agent_adapter.run_agent", side_effect=producer):
            return drive(self.store, self.run, self.command, **options)

    @staticmethod
    def success(command, request, response, **kwargs):
        result = {"task_id": json.loads(request.read_text("utf-8"))["task_id"]}
        response.write_text(json.dumps(result), encoding="utf-8")
        return result

    def test_twenty_five_tasks_drain_without_ten_item_approval_and_parent_only_writes(self):
        for i in range(25):
            self.task("SYN-" + str(i))
        calls = []
        def produce(*args, **kwargs):
            calls.append((str(args[1]), threading.get_ident()))
            return self.success(*args, **kwargs)
        result = self.run_driver(produce)
        self.assertEqual(result["driver"]["status"], "DRAINED")
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(len(calls), 25)
        self.assertEqual(len(self.store.records(self.run, "workflow_results")), 25)
        self.assertTrue(all(identity != self.store.owner for _, identity in calls))
        self.assertEqual(self.store.events(self.run, "review"), [])
        again = self.run_driver(lambda *a, **k: self.fail("Already completed task was dispatched"))
        self.assertEqual(again["driver"]["status"], "DRAINED")

    def test_one_task_timeout_retries_twice_and_does_not_stop_other_work(self):
        self.task("SYN-fails")
        for i in range(12):
            self.task("SYN-good-" + str(i))
        failures = []
        def produce(*args, **kwargs):
            if "SYN-fails" in str(args[1]):
                failures.append(str(args[2]))
                args[2].write_text("partial timeout output", encoding="utf-8")
                raise AuditError("Synthetic timeout")
            return self.success(*args, **kwargs)
        result = self.run_driver(produce)
        self.assertEqual(result["driver"]["status"], "BLOCKED")
        self.assertEqual(result["status"], "COMPLETE_WITH_PENDING")
        self.assertEqual(len(self.store.records(self.run, "workflow_results")), 12)
        self.assertEqual(len(failures), 2)
        self.assertEqual(len(set(failures)), 2)
        self.assertTrue(all(Path(p).read_text("utf-8") == "partial timeout output" for p in failures))
        self.assertIsNone(self.store.get(self.run, "workflow_results", "SYN-fails"))
        self.assertEqual(self.store.get(self.run, "workflow_execution", "SYN-fails")["attempts"], 2)
        self.run_driver(lambda *a, **k: self.fail("Exhausted work automatically retried"))

    def test_invalid_submission_is_isolated_and_rejected_output_is_retained(self):
        self.task("SYN-invalid")
        self.task("SYN-good")
        paths = []
        def produce(*args, **kwargs):
            if "SYN-invalid" in str(args[1]):
                paths.append(args[2])
                args[2].write_text('{"task_id":"wrong"}', encoding="utf-8")
                return {"task_id": "wrong"}
            return self.success(*args, **kwargs)
        result = self.run_driver(produce)
        self.assertEqual(result["status"], "COMPLETE_WITH_PENDING")
        self.assertEqual(len(paths), 2)
        self.assertEqual(len(self.store.records(self.run, "workflow_results")), 1)
        self.assertTrue(all(p.is_file() for p in paths))

    def test_transient_failure_finishes_in_next_attempt_and_preserves_history(self):
        self.task("SYN-retry")
        attempts = []
        def produce(*args, **kwargs):
            attempts.append(args[2])
            if len(attempts) == 1:
                raise RuntimeError("Synthetic transient executor bug")
            return self.success(*args, **kwargs)
        result = self.run_driver(produce)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(self.store.get(self.run, "workflow_execution", "SYN-retry")["attempts"], 2)
        self.assertEqual({r["status"] for r in self.store.records(self.run, "workflow_attempts")}, {"AGENT_FAILED", "ACCEPTED"})

    def test_retry_feedback_is_bounded_and_sent_only_to_the_same_failed_task(self):
        self.task("SYN-needs-correction")
        self.task("SYN-unrelated")
        observations = []
        def produce(*args, **kwargs):
            task_id = json.loads(args[1].read_text("utf-8"))["task_id"]
            observations.append((task_id, kwargs.get("feedback")))
            if task_id == "SYN-needs-correction" and not kwargs.get("feedback"):
                raise AuditError("Synthetic validator: citation not in selected segment; " + "R" * 3000)
            return self.success(*args, **kwargs)
        result = self.run_driver(produce)
        self.assertEqual(result["status"], "COMPLETE")
        failed_task = [feedback for tid, feedback in observations if tid == "SYN-needs-correction"]
        self.assertEqual(failed_task[0], "")
        self.assertEqual(len(failed_task[1]), 2000)
        self.assertTrue(failed_task[1].startswith("Synthetic validator: citation not in selected segment;"))
        self.assertEqual([feedback for tid, feedback in observations if tid == "SYN-unrelated"], [""])

    def test_oversize_retry_is_blocked_once_and_retains_measured_budget(self):
        from faultaudit.input_budget import InputTooLarge
        self.task('SYN-too-large')
        calls = []
        def produce(*args, **kwargs):
            calls.append(args[2])
            raise InputTooLarge({'chars':6000,'budget':5000,'scope':'WHOLE_MODEL_TASK','kind':'SAME_TASK_RETRY'})
        result = self.run_driver(produce)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['status'], 'COMPLETE_WITH_PENDING')
        record = self.store.get(self.run, 'workflow_execution', 'SYN-too-large')
        self.assertEqual(record['blocked_code'], 'INPUT_TOO_LARGE')
        self.assertEqual(record['input_budget']['chars'], 6000)

    def test_rejected_response_and_located_feedback_follow_same_task_into_fresh_attempt(self):
        from faultaudit.trigger_sparse import ClassificationFeedback
        self.task('SYN-located'); observed = []; original_submit = self.submit
        def submit(store, run, task_id, response, *, path=None):
            if not response.get('corrected'):
                error = ClassificationFeedback('bad link', rule='LINK_FACTS_SUBSET_SCENARIO', row_id='S5',
                    link_id='label_links[0]', missing=['F1'])
                store.put(run, 'workflow_attempts', digest([task_id,str(path)]), {'task_id':task_id,
                    'response':str(path), 'response_hash':digest(response), 'status':'REJECTED', 'diagnostic':error.diagnostic})
                raise error
            return original_submit(store, run, task_id, response, path=path)
        self.submit = submit
        def produce(command, request, destination, **kwargs):
            observed.append((destination, kwargs))
            req = json.loads(request.read_text(encoding='utf-8'))
            body = {'task_id':req['task_id'], 'request_hash':req['request_hash'], 'corrected':bool(kwargs.get('feedback'))}
            destination.write_text(json.dumps(body), encoding='utf-8')
            return body
        self.assertEqual(self.run_driver(produce)['status'], 'COMPLETE')
        self.assertEqual(len(observed), 2)
        self.assertNotEqual(observed[0][0], observed[1][0])
        self.assertEqual(observed[1][1]['previous_response'], str(observed[0][0]))
        self.assertEqual(observed[1][1]['diagnostic']['missing_fact_ids'], ['F1'])
        self.assertTrue(observed[0][0].is_file())

    def test_interrupted_response_resumes_submission_without_a_new_agent_context(self):
        task = self.task("SYN-resume")
        path = workflow.response_path(self.store, self.run, task["task_id"])
        path.write_text('{"task_id":"SYN-resume"}', encoding="utf-8")
        self.store.put(self.run, "workflow_execution", task["task_id"],
                       {"task_id": task["task_id"], "kind": "model", "status": "RUNNING", "attempts": 1, "response": str(path)})
        result = self.run_driver(lambda *a, **k: self.fail("Persisted output should be submitted, not regenerated"), max_attempts=1)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(self.store.get(self.run, "workflow_execution", task["task_id"])["attempts"], 1)

    def test_interrupted_command_without_output_retains_attempt_and_resumes(self):
        task = self.task("SYN-interrupted")
        path = workflow.response_path(self.store, self.run, task["task_id"])
        self.store.put(self.run, "workflow_execution", task["task_id"],
                       {"task_id": task["task_id"], "kind": "model", "status": "RUNNING", "attempts": 1, "response": str(path)})
        result = self.run_driver(self.success)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual({r["status"] for r in self.store.records(self.run, "workflow_attempts")}, {"INTERRUPTED", "ACCEPTED"})
        self.assertEqual(self.store.get(self.run, "workflow_execution", task["task_id"])["attempts"], 2)

    def test_interrupted_final_attempt_does_not_exceed_execution_budget(self):
        task = self.task("SYN-interrupted-final")
        path = workflow.response_path(self.store, self.run, task["task_id"])
        self.store.put(self.run, "workflow_execution", task["task_id"],
                       {"task_id": task["task_id"], "kind": "model", "status": "RUNNING", "attempts": 2, "response": str(path)})
        result = self.run_driver(lambda *a, **k: self.fail("Already exhausted work re-executed"))
        self.assertEqual(result["status"], "COMPLETE_WITH_PENDING")
        self.assertEqual(self.store.get(self.run, "workflow_execution", task["task_id"])["attempts"], 2)

    def test_same_site_auth_handoff_occurs_once_and_other_work_continues(self):
        self.task("SYN-login", "fetch", "https://wiki.huawei.com/page/1")
        self.task("SYN-waits", "fetch", "https://wiki.huawei.com/page/2")
        self.task("SYN-independent")
        calls = []
        def produce(*args, **kwargs):
            tid = json.loads(args[1].read_text("utf-8"))["task_id"]
            calls.append(tid)
            if tid == "SYN-login":
                result = {"task_id": tid, "outcome": "BLOCKED", "reason_code": "AUTH_REQUIRED", "reason": "Synthetic Edge login"}
                args[2].write_text(json.dumps(result), encoding="utf-8")
                return result
            return self.success(*args, **kwargs)
        result = self.run_driver(produce)
        self.assertEqual(result["driver"]["status"], "WAITING_AUTH")
        self.assertEqual(set(calls), {"SYN-login", "SYN-independent"})
        self.assertEqual(len(self.store.events(self.run, "workflow_auth_handoff")), 1)
        self.assertEqual(self.store.get(self.run, "workflow_execution", "SYN-waits")["attempts"], 0)
        self.run_driver(lambda *a, **k: self.fail("Login-waiting task re-dispatched"))
        self.assertEqual(len(self.store.events(self.run, "workflow_auth_handoff")), 1)
        self.store.put(self.run, "workflow_results", "SYN-login", {"retry": True}, mutable=True)
        reset_execution(self.store, self.run, "SYN-login")
        recovered = self.run_driver(self.success)
        self.assertEqual(recovered["status"], "COMPLETE")
        self.assertEqual(len(self.store.events(self.run, "workflow_execution_reset")), 1)

    def test_browser_lane_is_serial_and_semantic_contexts_can_run_in_parallel(self):
        for i in range(4):
            self.task("SYN-browser-" + str(i), "fetch", "https://example.invalid/page/" + str(i))
            self.task("SYN-model-" + str(i))
        active, peak = {"fetch": 0, "model": 0}, {"fetch": 0, "model": 0}
        gate = threading.Lock()
        def produce(*args, **kwargs):
            kind = json.loads(args[1].read_text("utf-8"))["kind"]
            with gate:
                active[kind] += 1
                peak[kind] = max(peak[kind], active[kind])
            time.sleep(0.03)
            result = self.success(*args, **kwargs)
            with gate:
                active[kind] -= 1
            return result
        result = self.run_driver(produce, workers=2)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(peak, {"fetch": 1, "model": 2})

    def test_only_auth_blocked_result_remains_partial_after_no_ready_tasks(self):
        self.task("SYN-only-login", "wiki_check")
        def blocked(command, request, response, **kwargs):
            body = {"task_id": "SYN-only-login", "outcome": "BLOCKED", "reason_code": "AUTH_REQUIRED", "reason": "Synthetic login"}
            response.write_text(json.dumps(body), encoding="utf-8")
            return body
        result = self.run_driver(blocked)
        self.assertEqual(result["driver"]["status"], "WAITING_AUTH")
        self.assertEqual(result["status"], "COMPLETE_WITH_PENDING")
        self.assertEqual(result["driver"]["unresolved_task_ids"], [])
        self.assertTrue(self.store.get(self.run, "workflow_state", "current")["block_ids"])

    def test_executor_context_blocking_is_outer_bound_and_never_a_business_result(self):
        self.task("SYN-context")
        self.task("SYN-independent")
        calls = []
        def produce(*args, **kwargs):
            request = json.loads(args[1].read_text("utf-8"))
            calls.append(request["task_id"])
            if request["task_id"] == "SYN-context":
                result = {"request_hash": request["request_hash"], "outcome": "BLOCKED",
                          "reason_code": "EXECUTOR_CONTEXT_LIMIT", "reason": "Synthetic executor cannot read all input"}
                args[2].write_text(json.dumps(result), encoding="utf-8")
                return result
            return self.success(*args, **kwargs)
        result = self.run_driver(produce)
        self.assertEqual(result["status"], "COMPLETE_WITH_PENDING")
        self.assertEqual(calls.count("SYN-context"), 1)
        self.assertIsNone(self.store.get(self.run, "workflow_results", "SYN-context"))
        record = self.store.get(self.run, "workflow_execution", "SYN-context")
        self.assertEqual((record["status"], record["blocked_code"]), ("EXTERNAL_BLOCKED", "EXECUTOR_CONTEXT_LIMIT"))
        self.assertEqual(len(self.store.records(self.run, "workflow_results")), 1)
        blocks = self.store.records(self.run, "workflow_blocks")
        self.assertEqual({b["reason"] for b in blocks}, {"EXECUTOR_CONTEXT_LIMIT"})
        self.run_driver(lambda *a, **k: self.fail("Context-limited task should await explicit retry"))

    def test_wrong_outer_hash_cannot_create_context_block_declaration(self):
        self.task("SYN-context-forged", "catalog_draft")
        def produce(*args, **kwargs):
            result = {"request_hash": "wrong", "outcome": "BLOCKED", "reason_code": "EXECUTOR_CONTEXT_LIMIT", "reason": "Synthetic inability"}
            args[2].write_text(json.dumps(result), encoding="utf-8")
            return result
        self.run_driver(produce)
        record = self.store.get(self.run, "workflow_execution", "SYN-context-forged")
        self.assertEqual(record["status"], "FAILED")
        self.assertEqual(record["attempts"], 2)
        self.assertIsNone(self.store.get(self.run, "workflow_results", "SYN-context-forged"))

    def test_capture_observation_login_pauses_queued_site_work_even_if_capture_outcome(self):
        self.task("SYN-auth-capture", "fetch", "https://wiki.huawei.com/page/1")
        self.task("SYN-auth-queued", "fetch", "https://wiki.huawei.com/page/2")
        calls = []
        def produce(*args, **kwargs):
            request = json.loads(args[1].read_text("utf-8"))
            calls.append(request["task_id"])
            result = {"task_id": request["task_id"], "outcome": "CAPTURED", "packages": [
                {"status": "AUTH_REQUIRED", "capture_observation": {"page_kind": "LOGIN"}}]}
            args[2].write_text(json.dumps(result), encoding="utf-8")
            return result
        result = self.run_driver(produce)
        self.assertEqual(calls, ["SYN-auth-capture"])
        self.assertEqual(result["driver"]["status"], "WAITING_AUTH")
        self.assertEqual(self.store.get(self.run, "workflow_execution", "SYN-auth-queued")["status"], "WAITING_AUTH")
        self.assertEqual(len(self.store.events(self.run, "workflow_auth_handoff")), 1)

    def test_task_kind_timeout_configuration_is_forwarded(self):
        self.task("SYN-browser", "wiki_check")
        self.task("SYN-model")
        observed = {}
        def produce(*args, **kwargs):
            observed[json.loads(args[1].read_text("utf-8"))["kind"]] = kwargs["timeout"]
            return self.success(*args, **kwargs)
        self.run_driver(produce, timeout=31, browser_timeout=17)
        self.assertEqual(observed, {"wiki_check": 17, "model": 31})

    def test_round_limit_exports_partial_and_next_invocation_can_continue(self):
        self.task("SYN-eventual")
        first = self.run_driver(lambda *a, **k: (_ for _ in ()).throw(AuditError("Synthetic failure")), max_rounds=1)
        self.assertEqual(first["driver"]["status"], "LIMIT_REACHED")
        self.assertEqual(first["status"], "COMPLETE_WITH_PENDING")
        second = self.run_driver(self.success)
        self.assertEqual(second["status"], "COMPLETE")

    def test_os_run_lock_rejects_second_coordinator_and_releases_on_close(self):
        with run_lock(self.directory):
            with self.assertRaisesRegex(AuditError, "already owns"):
                with run_lock(self.directory):
                    self.fail("Second coordinator entered")
        with run_lock(self.directory):
            pass

    def test_actual_processes_receive_distinct_request_files_and_fresh_context_contract(self):
        for i in range(3):
            self.task("SYN-process-" + str(i))
        script = self.root / "synthetic_agent.py"
        script.write_text("import json,os,pathlib,sys\n"
            "request,response=map(pathlib.Path,sys.argv[1:])\n"
            "value=json.loads(request.read_text('utf-8'))\n"
            "response.write_text(json.dumps({'task_id':value['task_id'],'pid':os.getpid(),"
            "'context':os.environ['FAULTAUDIT_CONTEXT_MODE']}),encoding='utf-8')\n", encoding="utf-8")
        self.command = [sys.executable, str(script), "{request}", "{response}"]
        with patch.object(workflow, "next_tasks", side_effect=self.next), \
             patch.object(workflow, "submit", side_effect=self.submit), \
             patch.object(workflow, "export", side_effect=self.export):
            result = drive(self.store, self.run, self.command)
        self.assertEqual(result["status"], "COMPLETE")
        responses = self.store.records(self.run, "workflow_results")
        self.assertEqual(len({r["pid"] for r in responses}), 3)
        self.assertEqual({r["context"] for r in responses}, {"fresh-task"})


if __name__ == "__main__":
    unittest.main()
