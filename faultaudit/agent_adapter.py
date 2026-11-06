"""Execute an external Agent command using request/response files, never a client."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .store import AuditError


def run_agent(command: list[str], request_path: Path, response_path: Path, *, timeout: float = 300) -> dict:
    """Run a configured argv; output files from failed attempts remain available."""
    if not any("{request}" in arg for arg in command) or not any("{response}" in arg for arg in command):
        raise AuditError("Agent command must contain both {request} and {response} placeholders")
    request_path, response_path = request_path.resolve(), response_path.resolve()
    if response_path.exists():
        raise AuditError(f"Agent response already exists; allocate a new attempt: {response_path}")
    argv = [arg.replace("{request}", str(request_path)).replace("{response}", str(response_path)) for arg in command]
    response_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        process = subprocess.run(argv, cwd=request_path.parent, shell=False, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise AuditError(f"Agent command timed out after {timeout} seconds") from exc
    except OSError as exc:
        raise AuditError(f"Agent command could not start: {exc}") from exc
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
