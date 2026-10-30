"""Create a source handoff and SHA256 manifest; exclude local running data."""
import hashlib
import json
import zipfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from faultaudit import __version__


def build() -> Path:
    root = Path(__file__).resolve().parents[1]
    destination = root / "dist"
    destination.mkdir(exist_ok=True)
    paths = []
    allowed = {"faultaudit": {".py"}, "scripts": {".py", ".mjs"}, "integration": {".py", ".md", ".yaml"},
               "tests": {".py"}, "schemas": {".json"}, "examples": {".json", ".tsv", ".txt"}}
    for name, extensions in allowed.items():
        directory = root / name
        if directory.exists():
            paths.extend(p for p in directory.rglob("*") if p.is_file()
                         and "__pycache__" not in p.parts and p.suffix in extensions
                         and ".scratch" not in p.relative_to(directory).parts
                         and not any(part.startswith("tmp") for part in p.relative_to(directory).parts[:-1]))
    paths.extend(root / name for name in ("README.md", "THIRD_PARTY_REFERENCES.md", "pyproject.toml",
                                          "requirements.txt", "run_faultaudit.py", "VALIDATION.md", ".gitignore") if (root / name).is_file())
    unique = sorted(set(paths), key=lambda p: p.relative_to(root).as_posix())
    manifest = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in unique}
    text = json.dumps({"version": __version__, "files": manifest}, ensure_ascii=False, indent=2) + "\n"
    (destination / "MANIFEST.sha256.json").write_text(text, encoding="utf-8")
    target = destination / f"fault_evidence_audit_v{__version__}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as package:
        for path in unique:
            package.write(path, "fault_evidence_audit/" + path.relative_to(root).as_posix())
        package.writestr("fault_evidence_audit/MANIFEST.sha256.json", text)
    return target


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(build())
