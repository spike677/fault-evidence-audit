"""Install only project-local templates; conflicts are detected before writes."""
import argparse
import json
import os
import sys
from pathlib import Path


def install(project: Path) -> list[str]:
    root = Path(__file__).resolve().parents[1]
    source = root / "integration" / ".opencode"
    project = project.resolve()
    if not project.is_dir():
        raise ValueError("Project directory must already exist")
    files = [(project / ".opencode" / p.relative_to(source), p.read_bytes())
             for p in sorted(source.rglob("*")) if p.is_file()]
    location = project / ".opencode" / "skills" / "fault-evidence-audit" / "core-location.json"
    try:
        core_path = os.path.relpath(root, location.parent)
    except ValueError:
        # Windows cannot express a relative path across drives. This generated
        # local file is never copied back into the distributable templates.
        core_path = str(root)
    config = {"schema_version": "1.0", "core_path": core_path}
    files.append((location, (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode("utf-8")))
    conflicts = []
    for destination, content in files:
        if destination.exists() and (not destination.is_file() or destination.read_bytes() != content):
            conflicts.append(str(destination))
        for parent in destination.parents:
            if parent == project:
                break
            if parent.exists() and not parent.is_dir():
                conflicts.append(str(parent))
    if conflicts:
        raise ValueError("Existing different files or blocked directories; no changes were made: "
                         + ", ".join(dict.fromkeys(conflicts)))
    for destination, content in files:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(content)
    return [str(destination) for destination, _ in files]


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    for installed in install(args.project):
        print(installed)
