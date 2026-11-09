"""Continuous local dispatch; workers never share a model conversation or Store.

Only the coordinator reads/writes SQLite. Each worker executes one immutable
request through the configured Agent process; browser tasks share a serial lane.
"""
from __future__ import annotations

import json
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from .store import AuditError, Store, digest, now

BROWSER_KINDS = {"fetch", "search", "wiki_check"}
AUTH_REASONS = {"AUTH_REQUIRED", "LOGIN_REQUIRED", "AUTHENTICATION_REQUIRED", "AUTH_BLOCKED"}


@contextmanager
def run_lock(directory: Path):
    """A process crash releases the OS lock; no stale PID-file deletion needed."""
    directory.mkdir(parents=True, exist_ok=True)
    handle = (directory / ".driver.lock").open("a+b")
    handle.seek(0, 2)
    if not handle.tell():
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        try:
            import msvcrt
        except ImportError:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        handle.close()
        raise AuditError("A workflow driver already owns this run") from exc
    try:
        yield
    finally:
        handle.close()


def _site(task: dict, request: dict) -> str:
    if task["kind"] == "wiki_check":
        return "wiki.huawei.com"
    return urlsplit(request.get("payload", {}).get("url", "")).hostname or ""


def _auth_required(response: dict) -> bool:
    codes = {response.get("reason_code"), response.get("blocked_reason")} if response.get("outcome") == "BLOCKED" else set()
    for package in response.get("packages", []):
        codes.add(package.get("status"))
        observation = package.get("page_observation") or package.get("capture_observation") or {}
        codes.add(observation.get("page_kind") or observation.get("page_type"))
    return bool(codes.intersection(AUTH_REASONS | {"LOGIN", "LOGIN_PAGE"}))


def auth_site(request: dict, response: dict) -> str:
    for package in response.get("packages", []):
        if package.get("status") in AUTH_REASONS or (package.get("capture_observation") or {}).get("page_kind") == "LOGIN":
            return urlsplit(package.get("url", "")).hostname or ""
    return urlsplit(response.get("blocked_url", "")).hostname or _site({"kind": request.get("kind")}, request)


def executor_blocked(request: dict, response: dict) -> bool:
    """Transport-level inability to read input is never a model result."""
    from .knowledge_common import SEMANTIC_KINDS
    if request.get("kind") not in {"model", "catalog_draft", "trigger_classify", "trigger_design"} | SEMANTIC_KINDS or response.get("outcome") != "BLOCKED":
        return False
    if (response.get("request_hash") != request.get("request_hash")
            or not request.get("request_hash") or response.get("reason_code") != "EXECUTOR_CONTEXT_LIMIT"
            or not isinstance(response.get("reason"), str) or not response["reason"].strip()):
        raise AuditError("Executor blocking requires outer request_hash, EXECUTOR_CONTEXT_LIMIT and a reason")
    return True


def _body(command, task, timeout):
    """No Store, other task payload, or parent model transcript enters a worker."""
    destination = Path(task["response"])
    if destination.exists():
        try:
            value = json.loads(destination.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AuditError("Saved response could not be read: " + str(exc)) from exc
        if not isinstance(value, dict):
            raise AuditError("Saved response must be a JSON object")
        return value
    from .agent_adapter import run_agent
    return run_agent(command, Path(task["request"]), destination, timeout=timeout,
                     feedback=task.get("previous_error", ""))


def reset_execution(store: Store, run_id: str, task_id: str) -> None:
    """Explicit retry resets a bounded execution, retaining archived attempts."""
    record = store.get(run_id, "workflow_execution", task_id)
    if record:
        store.event(run_id, "workflow_execution_reset", record)
        store.put(run_id, "workflow_execution", task_id,
                  {**record, "status": "RETRY", "attempts": 0, "updated_at": now()}, mutable=True)
        if record.get("site"):
            auth = store.get(run_id, "workflow_auth", record["site"])
            if auth:
                store.put(run_id, "workflow_auth", record["site"],
                          {**auth, "status": "RETRY", "updated_at": now()}, mutable=True)


def _execution(store, run_id, task, **changes):
    old = store.get(run_id, "workflow_execution", task["task_id"]) or {}
    value = {"task_id": task["task_id"], "kind": task["kind"], "attempts": 0,
             **old, **changes, "updated_at": now()}
    store.put(run_id, "workflow_execution", task["task_id"], value, mutable=bool(old))
    return value


def _failed_attempt(store, run_id, task, error, *, status="AGENT_FAILED"):
    identity = digest([task["task_id"], task["response"]])
    # submit() may already have archived a REJECTED attempt. Do not replace it.
    if not store.get(run_id, "workflow_attempts", identity):
        store.put(run_id, "workflow_attempts", identity,
                  {"task_id": task["task_id"], "response": task["response"], "status": status,
                   "error": str(error), "recorded_at": now()})


def _finish(store, run_id, step, *, rounds, reason):
    from . import xlsx_workflow as workflow
    active_ids = {task["task_id"] for task in step["tasks"]}
    executions = [record for record in store.records(run_id, "workflow_execution")
                  if record["task_id"] in active_ids and record["status"] != "SUCCEEDED"]
    blocked_ids = list((store.get(run_id, "workflow_state", "current") or {}).get("block_ids", []))
    for record in executions:
        request = store.get(run_id, "workflow_requests", record["task_id"]) or {}
        payload = request.get("payload", {})
        cases = payload.get("case_ids", [])
        if not cases and payload.get("subject", {}).get("case_id"):
            cases = [payload["subject"]["case_id"]]
        if not cases and payload.get("task", {}).get("payload", {}).get("case"):
            cases = [payload["task"]["payload"]["case"]["case_id"]]
        block = {"kind": record["kind"], "case_ids": cases,
                 "reason": record.get("blocked_code") or ("WAITING_AUTH" if record["status"] == "WAITING_AUTH" else "AGENT_EXECUTION_FAILED"),
                 "input_budget": {"task_id": record["task_id"], "attempts": record["attempts"],
                                  "status": record["status"], "error": record.get("error", "")}}
        block_id = digest(block)
        store.put(run_id, "workflow_blocks", block_id, block)
        blocked_ids.append(block_id)
    handoffs = [r for r in store.records(run_id, "workflow_auth") if r.get("status") == "WAITING_AUTH"]
    for auth in handoffs:
        request = store.get(run_id, "workflow_requests", auth["task_id"]) or {}
        block = {"kind": "authentication", "case_ids": request.get("payload", {}).get("case_ids", []),
                 "reason": "WAITING_AUTH", "input_budget": {"site": auth["site"], "task_id": auth["task_id"],
                 "reason": auth["reason"]}}
        block_id = digest(block)
        store.put(run_id, "workflow_blocks", block_id, block)
        blocked_ids.append(block_id)
    driver = {"status": "WAITING_AUTH" if handoffs else reason, "rounds": rounds,
              "unresolved_task_ids": sorted(active_ids), "auth_handoffs": handoffs}
    state = store.get(run_id, "workflow_state", "current") or {}
    store.put(run_id, "workflow_state", "current", {**state, "driver": driver,
              "block_ids": sorted(set(blocked_ids)), "task_ids": sorted(active_ids)}, mutable=True)
    result = workflow.export(store, run_id)
    return {**result, "driver": driver}


def drive(store: Store, run_id: str, command: list[str], *, max_rounds=32, workers=2,
          max_attempts=2, timeout=300, browser_timeout=None) -> dict:
    """Drain ready work without item-count approvals; isolate bounded failures.

    workers limits semantic commands; browser commands have a separate single
    lane. Run-level serialization and all commits stay in this calling thread.
    """
    from . import xlsx_workflow as workflow
    if not isinstance(workers, int) or isinstance(workers, bool) or not 1 <= workers <= 4:
        raise AuditError("Semantic workers must be between 1 and 4")
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 1 for v in (max_attempts, max_rounds)):
        raise AuditError("Attempt and round limits must be positive integers")
    if timeout <= 0 or browser_timeout is not None and browser_timeout <= 0:
        raise AuditError("Agent timeouts must be positive")
    directory = Path(workflow.config(store, run_id)["directory"])
    with run_lock(directory), ThreadPoolExecutor(max_workers=workers) as semantic, \
            ThreadPoolExecutor(max_workers=1) as browser:
        for round_number in range(1, max_rounds + 1):
            step = workflow.next_tasks(store, run_id)
            if not step["tasks"]:
                return _finish(store, run_id, step, rounds=round_number, reason="DRAINED")
            pending_browser, pending_semantic, futures = [], [], {}
            for original in step["tasks"]:
                task = dict(original)
                saved = store.get(run_id, "workflow_execution", task["task_id"]) or {}
                task["previous_error"] = saved.get("error", "")[:2000]
                if saved.get("status") == "RUNNING":
                    # Only this coordinator can hold the run lock. RUNNING here
                    # therefore belongs to an interrupted previous process.
                    prior_path = saved.get("response")
                    if prior_path and Path(prior_path).is_file():
                        task["response"] = prior_path
                        task["resume_attempt"] = True
                    else:
                        if prior_path:
                            _failed_attempt(store, run_id, {**task, "response": prior_path},
                                            "Previous coordinator stopped before response", status="INTERRUPTED")
                        saved = _execution(store, run_id, task, status="INTERRUPTED",
                                           error="Previous coordinator stopped before response")
                        task["response"] = str(workflow.response_path(store, run_id, task["task_id"]))
                if saved.get("attempts", 0) >= max_attempts and not task.get("resume_attempt"):
                    continue
                if saved.get("status") == "EXTERNAL_BLOCKED" and saved.get("blocked_code") == "EXECUTOR_CONTEXT_LIMIT":
                    continue
                if saved.get("status") == "WAITING_AUTH":
                    auth = store.get(run_id, "workflow_auth", saved.get("site", "")) or {}
                    if auth.get("status") == "WAITING_AUTH":
                        continue
                request = store.get(run_id, "workflow_requests", task["task_id"]) or {}
                site = _site(task, request)
                auth = store.get(run_id, "workflow_auth", site) if site else None
                if task["kind"] in BROWSER_KINDS and auth and auth.get("status") == "WAITING_AUTH":
                    _execution(store, run_id, task, site=site, status="WAITING_AUTH",
                               error="Complete the existing site login handoff before retry")
                    continue
                if task["kind"] in BROWSER_KINDS:
                    pending_browser.append((task, site))
                else:
                    pending_semantic.append((task, site))

            def launch_semantic():
                active = sum(task["kind"] not in BROWSER_KINDS for task, _ in futures.values())
                while pending_semantic and active < workers:
                    task, site = pending_semantic.pop(0)
                    saved = store.get(run_id, "workflow_execution", task["task_id"]) or {}
                    record = _execution(store, run_id, task, status="RUNNING", site=site,
                        response=task["response"], attempts=saved.get("attempts", 0) + (not task.get("resume_attempt", False)))
                    futures[semantic.submit(_body, command, task, timeout)] = (task, record)
                    active += 1

            def launch_browser():
                while pending_browser:
                    task, site = pending_browser.pop(0)
                    auth = store.get(run_id, "workflow_auth", site) if site else None
                    if auth and auth.get("status") == "WAITING_AUTH":
                        _execution(store, run_id, task, site=site, status="WAITING_AUTH",
                                   error="Complete the existing site login handoff before retry")
                        continue
                    saved = store.get(run_id, "workflow_execution", task["task_id"]) or {}
                    record = _execution(store, run_id, task, status="RUNNING", site=site,
                        response=task["response"], attempts=saved.get("attempts", 0) + (not task.get("resume_attempt", False)))
                    futures[browser.submit(_body, command, task, browser_timeout or timeout)] = (task, record)
                    break

            launch_semantic()
            launch_browser()
            if not futures:
                return _finish(store, run_id, step, rounds=round_number, reason="BLOCKED")
            while futures:
                completed, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in completed:
                    task, record = futures.pop(future)
                    try:
                        response = future.result()
                        request = store.get(run_id, "workflow_requests", task["task_id"]) or {}
                        context_blocked = executor_blocked(request, response)
                        if context_blocked:
                            _failed_attempt(store, run_id, task, response["reason"], status="EXTERNAL_BLOCKED")
                        else:
                            workflow.submit(store, run_id, task["task_id"], response, path=Path(task["response"]))
                    except Exception as exc:
                        _failed_attempt(store, run_id, task, exc)
                        _execution(store, run_id, task, status="FAILED", error=str(exc))
                    else:
                        status = "SUCCEEDED"
                        if context_blocked:
                            status = "EXTERNAL_BLOCKED"
                        elif _auth_required(response):
                            status = "WAITING_AUTH"
                            site = auth_site(request, response) or record.get("site") or "unknown-site"
                            previous = store.get(run_id, "workflow_auth", site)
                            if not previous or previous.get("status") != "WAITING_AUTH":
                                auth = {"site": site, "status": "WAITING_AUTH", "task_id": task["task_id"],
                                        "reason": response.get("reason", "User login required in existing Edge session"),
                                        "updated_at": now()}
                                store.put(run_id, "workflow_auth", site, auth, mutable=bool(previous))
                                store.event(run_id, "workflow_auth_handoff", auth)
                        elif response.get("outcome") == "BLOCKED":
                            status = "EXTERNAL_BLOCKED"
                        _execution(store, run_id, task, status=status, error=response.get("reason", ""),
                                   blocked_code="EXECUTOR_CONTEXT_LIMIT" if context_blocked else "")
                    if task["kind"] in BROWSER_KINDS:
                        launch_browser()
                    else:
                        launch_semantic()
        step = workflow.next_tasks(store, run_id)
        return _finish(store, run_id, step, rounds=max_rounds, reason="LIMIT_REACHED")
