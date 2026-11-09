"""Read local PrecisionTesting assets. No clone, source changes or device actions."""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
import re
import subprocess

from .store import AuditError, digest
from .trigger_taxonomy import load_taxonomy

AUDITED_COMMIT = "72c62d2deab7cac9cce2061034167e22ef45a140"
REPOSITORY = "https://gitcode.com/yunqixuan/PrecisionTesting.git"
CHECKERS = ("scripts/verify_schema.py", "scripts/verify_trigger_coverage.py", "scripts/prepare_atk_submission.py")


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _git(repo, *args):
    try:
        return subprocess.check_output(["git", "-c", "core.longpaths=true", "-C", str(repo), *args],
            text=True, encoding="utf-8", stderr=subprocess.PIPE, timeout=30).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuditError("PrecisionTesting checkout cannot be inspected by local Git") from exc


def inside(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise AuditError("Evidence/asset path escapes the selected task")
    return path


def _manifest(task):
    files = []
    for directory in ("01_generate/src", "01_generate/interfaces", "02_atk_run/atk_runnable"):
        path = task / directory
        if not path.is_dir():
            raise AuditError("PrecisionTesting task asset directory is missing: " + directory)
        files.extend(p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    files.extend(task / name for name in ("01_generate/submission/test_suite.template.json", "02_atk_run/atk_run_config.json"))
    return {p.relative_to(task).as_posix(): file_hash(p) for p in sorted(files)}


def describe(repo, slug, *, expected_commit=AUDITED_COMMIT):
    repo = Path(repo).resolve()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", slug):
        raise AuditError("Select an explicit single PrecisionTesting task slug")
    remote = _git(repo, "remote", "get-url", "origin")
    if remote.removesuffix(".git") != REPOSITORY.removesuffix(".git"):
        raise AuditError("Wrong PrecisionTesting repository owner/name; no same-name substitution")
    head = _git(repo, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit) or head != expected_commit:
        raise AuditError("TARGET_REAUDIT_REQUIRED: checkout does not match the explicitly reviewed commit")
    if head != AUDITED_COMMIT:
        raise AuditError("TARGET_REAUDIT_REQUIRED: update this Bridge release after reviewing the new target commit")
    protected = [*CHECKERS, "docs/trigger_library.md", "tasks/" + slug, "prompts/" + slug + ".md"]
    if _git(repo, "status", "--porcelain=v1", "--untracked-files=no", "--", *protected):
        raise AuditError("PrecisionTesting selected source assets have uncommitted changes")
    for relative in CHECKERS:
        committed = subprocess.check_output(["git", "-C", str(repo), "show", "HEAD:" + relative], timeout=30)
        if (repo / relative).read_bytes().replace(b"\r\n", b"\n") != committed.replace(b"\r\n", b"\n"):
            raise AuditError("Native checker differs from the reviewed Git source: " + relative)
    task = inside(repo / "tasks", slug)
    config = read_json(task / "02_atk_run/atk_run_config.json")
    if config.get("slug") != slug or not config.get("atk_config", {}).get("target_aclnn_name"):
        raise AuditError("Task config must preserve its slug and explicit target ACLNN API")
    library = repo / "docs/trigger_library.md"
    taxonomy = load_taxonomy(library)
    return {"repository": REPOSITORY, "repo_path": str(repo), "commit": head, "task_slug": slug,
        "api_name": config["atk_config"]["target_aclnn_name"], "task_assets": _manifest(task),
        "prompt_sha256": file_hash(repo / "prompts" / (slug + ".md")),
        "checker_sha256": {p: file_hash(repo / p) for p in CHECKERS},
        "library_file_sha256": file_hash(library),
        "library_text_sha256": hashlib.sha256(library.read_text(encoding="utf-8").encode("utf-8")).hexdigest(),
        "api42_items": taxonomy["items"], "api42_families": taxonomy["families"], "api42_context": taxonomy["context"],
        "task_config": config, "runtime_identity": {"expected_image": config.get("container", {}).get("image"),
            "actual_binary_verified": False, "source_snapshot_equals_runtime": "NOT_ESTABLISHED"}}


def presentation(text):
    lines = []
    for line in html.unescape(text).splitlines():
        line = re.sub(r"^\\(?=[#>\-`])", "", line).strip()
        if not line:
            continue
        if line.startswith("|"):
            if re.fullmatch(r"[|:\-\s]+", line):
                continue
            line = "|".join(cell.strip() for cell in line.split("|"))
        lines.append(line)
    return lines


def compare_api42(original, target):
    def normalized(value):
        if isinstance(value, str): return html.unescape(value)
        if isinstance(value, list): return [normalized(v) for v in value]
        return value
    local = {i["id"]: i for i in original["items"]}
    remote = {i["id"]: i for i in target["api42_items"]}
    differences, representation = [], []
    if set(local) != set(remote) or len(local) != 42:
        raise AuditError("API42_LIBRARY_MISMATCH: expected the complete original 42 IDs")
    for key in local:
        for field in ("name", "definition", "requires", "skip_if"):
            a, b = local[key].get(field, []), remote[key].get(field, [])
            if normalized(a) != normalized(b): differences.append(key + ":" + field)
            elif a != b: representation.append(key + ":" + field)
    families = {f["family_id"]: f for f in target["api42_families"]}
    for f in original.get("families", []):
        for field in ("requires", "skip_if"):
            if normalized(f.get(field, [])) != normalized(families.get(f["family_id"], {}).get(field, [])):
                differences.append(f["family_id"] + ":" + field)
    for key, value in original.get("context", {}).items():
        if presentation(value["source_quote"]) != presentation(target["api42_context"].get(key, {}).get("source_quote", "")):
            differences.append("context:" + key)
    if differences:
        raise AuditError("API42_LIBRARY_MISMATCH: " + ", ".join(differences))
    return {"comparison": "MATCH_WITH_EXPLICIT_PRESENTATION_NORMALIZATION", "representation_differences": sorted(set(representation)),
        "original_file_sha256": original["source_sha256"], "target_file_sha256": target["library_file_sha256"],
        "target_coverage_text_sha256": target["library_text_sha256"], "libraries_modified": False,
        "automatic_label_conversion": False}


def verify_workspace(context, workspace):
    workspace = Path(workspace).resolve()
    repo = Path(context.target["repo_path"])
    if workspace == repo or workspace.is_relative_to(repo / "tasks"):
        raise AuditError("An isolated writable workspace is required; never use original tasks")
    for relative, expected in context.target["task_assets"].items():
        path = inside(workspace, relative)
        if not path.is_file() or file_hash(path) != expected:
            raise AuditError("Workspace copied asset differs: " + relative)
    for directory in ("01_generate/src", "02_atk_run/atk_runnable"):
        actual = {p.relative_to(workspace).as_posix() for p in (workspace / directory).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
        expected = {p for p in context.target["task_assets"] if p.startswith(directory + "/")}
        if actual != expected:
            raise AuditError("Unexpected file in immutable copied assets: " + directory)


def verify_citation(target, citation):
    if not citation.path.startswith(("01_generate/src/", "01_generate/interfaces/")):
        raise AuditError("Operator evidence must cite selected source/API assets")
    task = Path(target["repo_path"]) / "tasks" / target["task_slug"]
    path = inside(task, citation.path)
    if citation.path not in target["task_assets"] or file_hash(path) != target["task_assets"][citation.path]:
        raise AuditError("Operator evidence asset is not the frozen task input")
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    quote = "".join(lines[citation.line-1:])
    if not citation.quote.strip() or not quote.startswith(citation.quote):
        raise AuditError("Operator source quote does not start at its cited line")


def protect_output(path, *, store=None, repo=None):
    path = Path(path).resolve()
    if store and path.is_relative_to(store.root):
        raise AuditError("Bridge artifacts must be outside the state directory")
    if repo:
        repo = Path(repo).resolve()
        if path.is_relative_to(repo):
            relative = path.relative_to(repo).parts
            if not relative or relative[0] != ".runs" or len(relative) < 4:
                raise AuditError("Bridge cannot write PrecisionTesting original repository assets")
            suffix = "/".join(relative[2:])
            if not suffix.startswith(("01_generate/report/", "03_report/", "bridge/")):
                raise AuditError("Bridge outputs belong in workspace reports, not copied inputs/runnables")
    return path


def immutable_json(path, value):
    path = Path(path)
    if path.exists():
        if read_json(path) != value:
            raise AuditError("Existing Bridge artifact differs; choose a new path and retain history")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    return str(path.resolve())
