"""Measure the complete serialized executor request without truncating inputs.

The configured limit counts Unicode characters in canonical JSON, rather than
tokens or bytes. It includes instructions, data, scope, hashes and budget metadata.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from . import model
from .model import ModelError
from .store import canonical_json, digest

BUDGET_ENV = "FAULTAUDIT_MAX_INPUT_CHARS"
BUDGET_VERSION = "whole-model-task-1"
BUDGET_SCOPE = "WHOLE_MODEL_TASK"
_RUN_BUDGET: ContextVar[int | None] = ContextVar("faultaudit_run_budget", default=None)


@contextmanager
def using_budget(budget: int | None):
    """A run-local override, isolated across nested runs and threads."""
    if budget is not None and (type(budget) is not int or budget <= 0):
        raise ModelError("Run input budget must be a positive integer", "INVALID_INPUT_BUDGET")
    token = _RUN_BUDGET.set(budget)
    try:
        yield
    finally:
        _RUN_BUDGET.reset(token)


def get_budget_chars() -> int:
    """Read a positive character limit, defaulting to the shared model constant."""
    pinned = _RUN_BUDGET.get()
    if pinned is not None:
        return pinned
    configured = os.environ.get(BUDGET_ENV)
    try:
        budget = int(configured.strip()) if configured is not None else model.MAX_INPUT_CHARS
    except (TypeError, ValueError) as exc:
        raise ModelError(f"{BUDGET_ENV} must be a positive integer", "INVALID_INPUT_BUDGET") from exc
    if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
        raise ModelError(f"{BUDGET_ENV} must be a positive integer", "INVALID_INPUT_BUDGET")
    return budget


def budget_policy() -> dict:
    """Configuration is part of request policy identity, including runtime changes."""
    return {"version": BUDGET_VERSION, "budget": get_budget_chars(), "scope": BUDGET_SCOPE,
            "serialization": "canonical-json-unicode-characters", "environment_key": BUDGET_ENV}


def serialized_chars(value: Any) -> int:
    return len(canonical_json(value))


class InputTooLarge(ModelError):
    def __init__(self, details: dict):
        self.details = details
        self.chars = details["chars"]
        self.budget = details["budget"]
        self.scope = details["scope"]
        super().__init__(f"Model task input is {self.chars} serialized characters; budget is {self.budget} "
                         f"(scope={self.scope}, kind={details.get('kind', 'unknown')}). Input was not truncated.",
                         "INPUT_TOO_LARGE")


def check_input_budget(request: dict, *, budget: int | None = None) -> dict:
    """Validate the final request, returning content-free audit measurements."""
    budget = get_budget_chars() if budget is None else budget
    if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
        raise ModelError("Input budget must be a positive integer", "INVALID_INPUT_BUDGET")
    details = {"chars": serialized_chars(request), "budget": budget, "scope": BUDGET_SCOPE,
               "kind": request.get("kind"), "pipeline_task_id": request.get("pipeline_task_id"),
               "input_scope": request.get("payload", {}).get("input_scope", {}),
               "serialization": "canonical-json-unicode-characters", "budget_version": BUDGET_VERSION}
    if details["chars"] > budget:
        raise InputTooLarge(details)
    return details


def finalize_model_task(unsigned: dict) -> dict:
    """Attach auditable measurements and sign a whole request of that exact size.

    Fixed-length ID placeholders allow the measurement to include both hashes.
    The only size dependency is the decimal digit count of the measurement itself,
    which converges before the actual identity values are calculated.
    """
    task = dict(unsigned)
    budget = get_budget_chars()
    task["input_budget"] = {"chars": 0, "budget": budget, "scope": BUDGET_SCOPE,
                            "serialization": "canonical-json-unicode-characters", "version": BUDGET_VERSION}
    candidate = {**task, "task_id": "llm-" + "0" * 24, "request_hash": "0" * 64}
    for _ in range(12):
        measured = serialized_chars(candidate)
        if measured == task["input_budget"]["chars"]:
            break
        task["input_budget"]["chars"] = measured
    else:
        raise ModelError("Unable to measure complete model task input", "INVALID_INPUT_BUDGET")
    # Refuse oversized requests before storing or presenting any task to an executor.
    check_input_budget(candidate, budget=budget)
    task["task_id"] = "llm-" + digest(task)[:24]
    task["request_hash"] = digest(task)
    measured = check_input_budget(task, budget=budget)
    if measured["chars"] != task["input_budget"]["chars"]:
        raise ModelError("Final model task size differs from its measurement", "INVALID_INPUT_BUDGET")
    return task
