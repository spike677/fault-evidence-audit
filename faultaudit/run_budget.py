"""Freeze a workflow's input capacity without rewriting requests or policies."""
from __future__ import annotations

import inspect
from functools import wraps

from .input_budget import BUDGET_VERSION, BUDGET_SCOPE, using_budget
from .store import AuditError, digest

KIND = "workflow_runtime"
KEY = "input_budget"


def status(store, run_id):
    pinned = store.get(run_id, KIND, KEY)
    requests = store.records(run_id, "workflow_requests")
    budgets = sorted({r.get("input_budget", {}).get("budget") for r in requests
                      if type(r.get("input_budget", {}).get("budget")) is int})
    return {"status": "PINNED" if pinned else "UNPINNED", "pinned": pinned,
            "historical_request_count": len(requests), "historical_budgets": budgets}


def pin(store, run_id, chars, *, reason="EXPLICIT_OPERATOR_CONFIGURATION"):
    store.run_info(run_id)
    if type(chars) is not int or chars <= 0:
        raise AuditError("Run input budget must be a positive integer")
    old = store.get(run_id, KIND, KEY)
    if old:
        if old["budget"] != chars:
            raise AuditError("Run input budget is frozen; do not change it while resuming this run")
        return {"run_id": run_id, "idempotent": True, **old}
    requests = store.records(run_id, "workflow_requests")
    if any(r.get("input_budget", {}).get("budget") != chars for r in requests):
        raise AuditError("Requested run budget differs from historical requests or their budget is missing")
    record = {"budget": chars, "version": BUDGET_VERSION, "scope": BUDGET_SCOPE,
              "reason": reason, "historical_request_count": len(requests),
              "historical_requests_hash": digest(sorted(r["request_hash"] for r in requests))}
    store.put(run_id, KIND, KEY, record)
    store.event(run_id, "run_input_budget_pinned", record)
    return {"run_id": run_id, **record}


def require_pinned(store, run_id):
    if not store.get(run_id, KIND, KEY):
        raise AuditError("RUN_BUDGET_UNPINNED: use xlsx-workflow pin-budget --run RUN --chars HISTORICAL_BUDGET before planning or submitting")


def scoped(function):
    """Queries and generators use the same budget as planning/submission."""
    @wraps(function)
    def call(store, run_id, *args, **kwargs):
        record = store.get(run_id, KIND, KEY)
        with using_budget(record["budget"] if record else None):
            return function(store, run_id, *args, **kwargs)

    @wraps(function)
    def generate(store, run_id, *args, **kwargs):
        record = store.get(run_id, KIND, KEY)
        iterator = function(store, run_id, *args, **kwargs)
        while True:
            with using_budget(record["budget"] if record else None):
                try:
                    value = next(iterator)
                except StopIteration:
                    return
            yield value

    return generate if inspect.isgeneratorfunction(function) else call
