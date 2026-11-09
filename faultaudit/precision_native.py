"""Run only the audited upstream format checks/JSON preparation, never ATK jobs."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile

from . import precision_target as target
from .store import digest


def validate_native(context, workspace, *, python=None, timeout=30):
    repo = Path(context.target["repo_path"])
    workspace = Path(workspace).resolve()
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    results = []; materialized = None
    with tempfile.TemporaryDirectory(prefix="precision-bridge-") as temporary:
        witness = Path(temporary) / "expected_atk.json"
        commands = [
            ("schema", [str(repo / "scripts/verify_schema.py"), "--task-dir", str(workspace)], "PASS:"),
            ("coverage", [str(repo / "scripts/verify_trigger_coverage.py"), "verify", "--task-dir", str(workspace)], "PASS:"),
            ("prepare", [str(repo / "scripts/prepare_atk_submission.py"), "prepare", "--task-dir", str(workspace),
                "--output", str(witness)], "ATK-ready JSON saved to:")]
        for name, arguments, success_marker in commands:
            try:
                process = subprocess.run([str(python or sys.executable), *arguments], cwd=repo, env=env,
                    text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=timeout)
                stdout, stderr, code = process.stdout, process.stderr, process.returncode
                passed = code == 0 and success_marker in stdout and not any(t.startswith("FAIL:") for t in stdout.splitlines())
            except (OSError, subprocess.TimeoutExpired) as exc:
                stdout, stderr, code, passed = "", str(exc), None, False
            results.append({"checker": name, "exit_code": code, "core_passed": passed,
                "stdout": stdout, "stderr": stderr, "stdout_sha256": digest(stdout.encode("utf-8")),
                "stderr_sha256": digest(stderr.encode("utf-8")),
                "warnings": [s.removeprefix("WARNING:").strip() for s in stdout.splitlines() if s.startswith("WARNING:")],
                "execution_scope": "FORMAT_AND_JSON_ONLY; NO_ATK_QUEUE_OR_DEVICE_EXECUTION"})
        if results[-1]["core_passed"] and witness.is_file():
            materialized = target.read_json(witness)
        else:
            results[-1]["core_passed"] = False
    return results, materialized
