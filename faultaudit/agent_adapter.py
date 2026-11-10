"""Execute an external Agent command using request/response files, never a client."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .store import AuditError


def _logs(directory, stdout, stderr):
    for name, value in (("agent.stdout.log", stdout), ("agent.stderr.log", stderr)):
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        with (directory / name).open("x", encoding="utf-8") as output:
            output.write(value or "")


def run_agent(command: list[str], request_path: Path, response_path: Path, *, timeout: float = 300,
              feedback: str = "", previous_response: str = "", diagnostic: dict | None = None) -> dict:
    """Run one task process; the adapter must start a fresh Agent context.

    The environment is an explicit handoff contract, not proof that an external
    model service obeyed it. Returned producer/session metadata remains auditable.
    """
    if not any("{request}" in arg for arg in command) or not any("{response}" in arg for arg in command):
        raise AuditError("Agent command must contain both {request} and {response} placeholders")
    request_path, response_path = request_path.resolve(), response_path.resolve()
    if response_path.exists():
        raise AuditError(f"Agent response already exists; allocate a new attempt: {response_path}")
    if any((response_path.parent / name).exists() for name in ("agent.stdout.log", "agent.stderr.log", "retry_context.json")):
        raise AuditError("Agent attempt artifacts already exist; allocate a new attempt")
    argv = [arg.replace("{request}", str(request_path)).replace("{response}", str(response_path)) for arg in command]
    response_path.parent.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "FAULTAUDIT_CONTEXT_MODE": "fresh-task",
                   "FAULTAUDIT_REQUEST_PATH": str(request_path),
                   "FAULTAUDIT_RESPONSE_PATH": str(response_path),
                   # Override even when empty: a parent's environment must not
                   # accidentally attach another task's diagnostic to this one.
                   "FAULTAUDIT_ATTEMPT_FEEDBACK": feedback[:2000],
                   "FAULTAUDIT_RETRY_CONTEXT": ""}
    try:
        request = json.loads(request_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise AuditError("Agent request could not be read: " + str(exc)) from exc
    budget = request.get("input_budget", {}).get("budget")
    if budget is not None:
        from .input_budget import BUDGET_ENV
        if type(budget) is not int or budget <= 0:
            raise AuditError("Agent request has an invalid input budget")
        environment[BUDGET_ENV] = str(budget)
    if previous_response:
        from .input_budget import check_input_budget
        prior = Path(previous_response).resolve()
        if not prior.is_relative_to(request_path.parent) or prior == response_path:
            raise AuditError("Retry context must belong to this task and an earlier response destination")
        try:
            previous = json.loads(prior.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise AuditError("Previous task response could not be read: " + str(exc)) from exc
        if not isinstance(previous, dict) or previous.get("request_hash") != request.get("request_hash"):
            raise AuditError("Retry context response does not bind this unchanged task")
        context = {"request_hash": request["request_hash"], "previous_response_path": str(prior),
            "previous_response": previous, "diagnostic": diagnostic or {}, "error": feedback[:2000],
            "instructions": "Repair only this same task's contract errors against the complete original request. "
                "The rejected response and diagnostics are not evidence. Preserve unknowns and actual producer identity."}
        measurement = check_input_budget({"kind": "SAME_TASK_RETRY", "request": request,
            "retry_context": context}, budget=budget)
        retry_path = response_path.parent / "retry_context.json"
        with retry_path.open("x", encoding="utf-8") as output:
            json.dump(context, output, ensure_ascii=False, indent=2)
        (response_path.parent / "retry_input_budget.json").write_text(
            json.dumps(measurement, ensure_ascii=False, indent=2), encoding="utf-8")
        environment["FAULTAUDIT_RETRY_CONTEXT"] = str(retry_path)
    try:
        process = subprocess.run(argv, cwd=request_path.parent, shell=False, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=timeout, env=environment)
    except subprocess.TimeoutExpired as exc:
        _logs(response_path.parent, exc.stdout, exc.stderr)
        raise AuditError(f"Agent command timed out after {timeout} seconds") from exc
    except OSError as exc:
        raise AuditError(f"Agent command could not start: {exc}") from exc
    _logs(response_path.parent, process.stdout, process.stderr)
    if process.returncode:
        detail = process.stderr.strip()[-1000:] or "(no stderr)"
        raise AuditError(f"Agent command failed (returncode={process.returncode}): {detail}")
    if not response_path.is_file():
        raise AuditError("Agent command exited 0 but did not write its response JSON")
    try:
        response = json.loads(response_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"Agent command exited 0 but response JSON could not be read: {exc}") from exc
    if not isinstance(response, dict):
        raise AuditError("Agent response JSON must be an object")
    return response
