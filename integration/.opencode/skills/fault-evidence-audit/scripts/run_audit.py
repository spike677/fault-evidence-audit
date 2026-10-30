"""Invoke the separately installed core without duplicating business logic."""
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    configured = os.getenv("FAULTAUDIT_HOME")
    launcher = Path(__file__).resolve()
    location = launcher.parents[1] / "core-location.json"
    if configured is not None:
        if not configured.strip():
            print("FAULTAUDIT_HOME is empty; set it to the core directory containing run_faultaudit.py", file=sys.stderr)
            return 1
        core = Path(configured).resolve() / "run_faultaudit.py"
        if not core.is_file():
            print("FAULTAUDIT_HOME does not contain run_faultaudit.py: " + str(core.parent), file=sys.stderr)
            return 1
    elif location.exists():
        try:
            config = json.loads(location.read_text(encoding="utf-8"))
            if (not isinstance(config, dict) or config.get("schema_version") != "1.0"
                    or not isinstance(config.get("core_path"), str) or not config["core_path"].strip()):
                raise ValueError("expected schema_version=1.0 and a nonempty core_path")
            core = (location.parent / config["core_path"]).resolve() / "run_faultaudit.py"
            if not core.is_file():
                raise ValueError("configured core does not contain run_faultaudit.py: " + str(core.parent))
        except (OSError, ValueError) as exc:
            print("Installed core configuration is invalid: " + str(exc), file=sys.stderr)
            return 1
    else:
        core = next((directory / "run_faultaudit.py" for directory in launcher.parents
                     if (directory / "run_faultaudit.py").is_file()), None)
    if core is None:
        print("Run scripts/install_opencode.py --project <workspace> from the core, or set FAULTAUDIT_HOME "
              "to the extracted core directory containing run_faultaudit.py", file=sys.stderr)
        return 1
    return subprocess.call([sys.executable, str(core), *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
