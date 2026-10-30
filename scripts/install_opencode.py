"""Install only project-local templates; conflicts are detected before writes."""
import argparse
import shutil
from pathlib import Path


def install(project: Path) -> list[str]:
    root = Path(__file__).resolve().parents[1]
    source = root / "integration" / ".opencode"
    project = project.resolve()
    if not project.is_dir():
        raise ValueError("Project directory must already exist")
    pairs = [(p, project / ".opencode" / p.relative_to(source)) for p in source.rglob("*") if p.is_file()]
    conflicts = [str(dst) for src, dst in pairs if dst.exists() and (not dst.is_file() or src.read_bytes() != dst.read_bytes())]
    if conflicts:
        raise ValueError("Existing different files; no changes were made: " + ", ".join(conflicts))
    for src, dst in pairs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copyfile(src, dst)
    return [str(dst) for _, dst in pairs]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    for installed in install(args.project):
        print(installed)
