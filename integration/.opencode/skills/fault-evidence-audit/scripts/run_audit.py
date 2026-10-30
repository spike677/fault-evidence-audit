"""Invoke the separately installed core without duplicating business logic."""
import os
import subprocess
import sys
from pathlib import Path


def main():
    configured = os.getenv("FAULTAUDIT_HOME")
    candidates = [Path(configured).resolve()] if configured else list(Path(__file__).resolve().parents)
    core = next((directory / "run_faultaudit.py" for directory in candidates
                 if (directory / "run_faultaudit.py").is_file()), None)
    if core is None:
        print("Set FAULTAUDIT_HOME to the extracted core directory containing run_faultaudit.py", file=sys.stderr)
        return 1
    return subprocess.call([sys.executable, str(core), *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
