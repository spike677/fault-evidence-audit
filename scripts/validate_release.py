"""Run pure offline tests and persist the actual release validation result."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "examples" / "validation_result.json")
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    from faultaudit import __version__
    payload = {"version": __version__, "tested_at_utc": datetime.now(timezone.utc).isoformat(),
               "python": platform.python_version(), "platform": platform.system(),
               "pydantic": importlib.metadata.version("pydantic"),
               "openpyxl": importlib.metadata.version("openpyxl"),
               "tests_run": result.testsRun, "successful": result.wasSuccessful(),
               "failures": [str(t) for t, _ in result.failures], "errors": [str(t) for t, _ in result.errors],
               "skipped": [str(t) for t, _ in result.skipped],
               "network_scope": "No network and no model services; OpenCode task/result protocol only",
               "model_execution_owner": "opencode",
               "live_deepseek_tested": False, "internal_collectors_tested": False,
               "actual_98_item_catalog_tested": False}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
