"""Read a frozen input-trigger taxonomy without inferring fault mechanisms.

The 42 input categories and optional outside branches are separate registries.
All definitions retain their source ranges; this loader never edits the source.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .store import AuditError, digest

LOADER_VERSION = "trigger-taxonomy-2"
FAMILY_COUNTS = {"1.1": 5, "1.2": 8, "1.3": 4, "1.4": 3,
                 "1.5": 4, "1.6": 2, "1.7": 6, "1.8": 3, "1.C": 7}
EXPECTED_IDS = tuple(f"{family}.{index}" for family, count in FAMILY_COUNTS.items()
                     for index in range(1, count + 1))
BRANCH_ROLES = {"2.1": "PLATFORM", "2.2": "COMPILER_OPTION", "2.3": "BUILD_VARIANT",
                "3.1": "DEVICE_SCHEDULING", "3.2": "STREAM_ASYNC", "3.3": "SYNC_RACE"}


def condition_role_requirements(trigger_id: str) -> set[str]:
    """Source-role boundaries, not extra taxonomy items or keyword matching."""
    if trigger_id.startswith("1.C."):
        return {"API_CONTROL"}
    if trigger_id.startswith("1.7."):
        return {"INPUT_VALUE"}
    if trigger_id.startswith("1.3."):
        return {"INDEX_OR_OFFSET"}
    return {"INPUT_VALUE", "INPUT_SHAPE", "INPUT_DTYPE", "INPUT_LAYOUT", "INDEX_OR_OFFSET", "API_CONTROL"}

_HEADING = re.compile(r"^\s*\\?(#{1,6})\s+(.+?)\s*$")
_FAMILY = re.compile(r"^(1\.(?:\d+|C))\s+(.+)$")
_ITEM = re.compile(r"^\s*(?:[-*]\s+)?`?\[[^\]]*\]`?\s+\*\*"
                   r"(1\.(?:\d+|C)\.\d+)\s+([^*]+)\*\*(.*)$")
_CONTROL = re.compile(r"^\s*\|\s*\*\*(1\.C\.\d+)\*\*\s*\|\s*([^|]+)"
                      r"\|\s*([^|]*)\|(?:.*)$")


def builtin_user_branches() -> dict:
    """Return only the outside-branch definitions supplied by the user.

    This is an opt-in supplement, not content inferred from trigger_library.md.
    """
    provenance = "user instruction 2026-11-06"
    declarations = (
        ("2", "实现实例", "平台/SoC、编译选项/宏、构建变体；固定单实例可为0。",
         "Branch2: 2.1 平台/SoC，2.2 编译选项/宏，2.3 构建变体；固定单实例可为0。",
         (("2.1", "平台/SoC"), ("2.2", "编译选项/宏"), ("2.3", "构建变体"))),
        ("3", "执行情境", "设备调度、流与异步、同步/竞态；同实参、同二进制。",
         "Branch3: 3.1 设备调度，3.2 流与异步，3.3 同步/竞态；同实参、同二进制。",
         (("3.1", "设备调度"), ("3.2", "流与异步"), ("3.3", "同步/竞态"))),
    )
    return {"provenance": provenance, "branches": [
        {"branch_id": branch_id, "name": name, "definition": definition,
         "source_quote": quote, "categories": [
             {"id": category_id, "name": category_name, "definition": category_name,
              "source_quote": category_id + " " + category_name}
             for category_id, category_name in categories]}
        for branch_id, name, definition, quote, categories in declarations]}


def _read(path: Path) -> tuple[Path, bytes, list[str]]:
    path = Path(path).resolve()
    raw = path.read_bytes()
    try:
        lines = raw.decode("utf-8-sig").splitlines(keepends=True)
    except UnicodeError as exc:
        raise AuditError("Taxonomy source must be UTF-8 text") from exc
    return path, raw, lines


def _heading(line: str) -> tuple[int, str] | None:
    match = _HEADING.match(line.rstrip("\r\n"))
    return (len(match[1]), match[2]) if match else None


def _end_section(lines: list[str], start: int) -> int:
    level, _ = _heading(lines[start])
    return next((index for index in range(start + 1, len(lines))
                 if (heading := _heading(lines[index])) and heading[0] <= level), len(lines))


def _source(path: Path, lines: list[str], start: int, end: int) -> dict:
    while end > start and (not lines[end - 1].strip()
                          or lines[end - 1].strip() in {"---", "\\---"}):
        end -= 1
    return {"source_file": str(path), "line_start": start + 1, "line_end": end,
            "source_quote": "".join(lines[start:end])}


def _clauses(lines: list[str], label: str) -> list[str]:
    """Keep explicit clauses and their continuation, including OR bullet lists."""
    clauses, active = [], None
    labels = re.compile(r"^(Requires(?:[（(].*?[）)])?|Skip if|Generator|Values|Note|代码信号)\s*[:：]\s*(.*)$", re.I)
    for raw in lines:
        line = raw.strip().replace("**", "")
        line = re.sub(r"^\\(?=[>\-*])", "", line)
        line = re.sub(r"^>\s*", "", line)
        match = labels.match(line)
        if match:
            key = re.sub(r"[（(].*", "", match[1]).strip().casefold()
            if key == label.casefold():
                clauses.append(match[2].strip())
                active = len(clauses) - 1
            else:
                active = None
        elif active is not None and line and line not in {"---", "\\---"}:
            clauses[active] = (clauses[active] + "\n" + line).strip()
    return [clause for clause in clauses if clause]


def _undefined(branch_id: str, source: dict | None = None) -> dict:
    return {"branch_id": branch_id, "status": "UNDEFINED", "included_in_42": False,
            "name": "", "definition": "", "source_quote": "", "categories": [],
            "reason": "Authoritative branch definition was not supplied in a supported structured form",
            "source_file": (source or {}).get("source_file", ""),
            "source_sha256": (source or {}).get("source_sha256", "")}


def _branches(path: Path | None, user_definitions: dict | None = None) -> tuple[list[dict], dict | None]:
    if path is not None and user_definitions is not None:
        raise AuditError("Provide branch_source or user_branch_definitions, not both")
    if path is None and user_definitions is None:
        return [_undefined("2"), _undefined("3")], None
    if user_definitions is not None:
        if not isinstance(user_definitions, dict) or not isinstance(user_definitions.get("branches"), list):
            raise AuditError("User branch definitions require a branches list")
        value = user_definitions
        source = {"source_file": "", "source_sha256": digest(value),
                  "source_quote": json.dumps(value, ensure_ascii=False, sort_keys=True),
                  "format": "USER_DEFINITIONS", "provenance": value.get("provenance", "USER_SUPPLIED_DEFINITIONS")}
    else:
        path, raw, lines = _read(path)
        text = "".join(lines)
        source = {"source_file": str(path), "source_sha256": digest(raw),
                  "source_quote": text, "format": "UNPARSED", "provenance": "BRANCH_SOURCE_FILE"}
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return [_undefined(key, source) for key in ("2", "3")], source
    result = {key: _undefined(key, source) for key in ("2", "3")}
    if not isinstance(value, dict) or not isinstance(value.get("branches"), list):
        return list(result.values()), source
    if user_definitions is None:
        source["format"] = "BRANCH_JSON"
    seen = set()
    for entry in value["branches"]:
        if not isinstance(entry, dict) or entry.get("branch_id") not in result:
            raise AuditError("Outside branch IDs must be explicit strings '2' or '3'")
        branch_id = entry["branch_id"]
        if branch_id in seen:
            raise AuditError("Duplicate outside branch ID: " + branch_id)
        seen.add(branch_id)
        if any(not isinstance(entry.get(key), str) or not entry[key].strip()
               for key in ("name", "definition", "source_quote")):
            raise AuditError("Outside branches require name, definition and an explicit source_quote")
        categories = entry.get("categories", [])
        if not isinstance(categories, list):
            raise AuditError("Outside branch categories must be a list")
        category_ids, normalized = set(), []
        for category in categories:
            if not isinstance(category, dict) or not isinstance(category.get("id"), str) or not re.fullmatch(
                    re.escape(branch_id) + r"\.[1-9]\d*", category["id"]):
                raise AuditError("Outside category ID must belong to its explicit branch")
            if category["id"] in category_ids:
                raise AuditError("Duplicate outside category ID: " + category["id"])
            category_ids.add(category["id"])
            if any(not isinstance(category.get(key), str) or not category[key].strip()
                   for key in ("name", "definition", "source_quote")):
                raise AuditError("Outside categories require name, definition and an explicit source_quote")
            normalized.append({key: category[key] for key in ("id", "name", "definition", "source_quote")})
        provenance = {"source_file": source["source_file"], "source_sha256": source["source_sha256"],
                      "provenance": source["provenance"]}
        result[branch_id] = {"branch_id": branch_id, "status": "DEFINED", "included_in_42": False,
                             **{key: entry[key] for key in ("name", "definition", "source_quote")},
                             "categories": [{**category, **provenance} for category in normalized], **provenance}
    return list(result.values()), source


def load_taxonomy(path: Path, branch_source: Path | None = None, *, user_branch_definitions: dict | None = None) -> dict:
    """Load exactly 35 data triggers plus 7 API-control triggers, read-only.

    Requires/skip_if on each item are item-local. Family conditions and global
    applicability/coverage rules are retained separately and must also be used.
    Missing Branch 2/3 leaves stay undefined and do not change the 42-item count.
    Explicit user_branch_definitions are separately identified as user supplied.
    """
    path, raw, lines = _read(path)
    marker = next((i for i, line in enumerate(lines) if "# Trigger Library" in line), None)
    if marker is None:
        raise AuditError("Taxonomy source needs a Trigger Library heading")
    checklist = next((i for i in range(marker, len(lines))
                      if (heading := _heading(lines[i])) and heading[1].strip().casefold() == "trigger checklist"), None)
    if checklist is None:
        raise AuditError("Taxonomy source needs its Trigger Checklist section")
    starts = {}
    for index in range(checklist + 1, len(lines)):
        heading = _heading(lines[index])
        match = _FAMILY.match(heading[1]) if heading else None
        if match:
            if match[1] not in FAMILY_COUNTS or match[1] in starts:
                raise AuditError("Unknown or duplicate trigger family: " + match[1])
            starts[match[1]] = (index, _end_section(lines, index), match[2])
    if set(starts) != set(FAMILY_COUNTS):
        raise AuditError("Taxonomy must define all nine trigger families")
    entries = []
    for index in range(checklist + 1, len(lines)):
        item, control = _ITEM.match(lines[index].rstrip("\r\n")), _CONTROL.match(lines[index].rstrip("\r\n"))
        if not item and not control:
            continue
        match = item or control
        item_id = match[1]
        family = item_id.rsplit(".", 1)[0]
        if item_id not in EXPECTED_IDS or family not in starts:
            raise AuditError("Unknown trigger ID: " + item_id)
        if not starts[family][0] < index < starts[family][1]:
            raise AuditError("Trigger definition is outside its family: " + item_id)
        entries.append((index, item_id, family, match[2].strip(), item, control))
    ids = [entry[1] for entry in entries]
    if len(ids) != len(set(ids)):
        raise AuditError("Duplicate trigger IDs are not allowed")
    if set(ids) != set(EXPECTED_IDS):
        raise AuditError("Taxonomy must contain exactly the expected 42 unique trigger IDs; missing: "
                         + ", ".join(key for key in EXPECTED_IDS if key not in ids))
    items, families = [], []
    for family in FAMILY_COUNTS:
        start, end, name = starts[family]
        members = [entry for entry in entries if entry[2] == family]
        intro_end = members[0][0]
        families.append({"family_id": family, "name": name, "item_count": len(members),
                         "requires": _clauses(lines[start + 1:intro_end], "Requires"),
                         "skip_if": _clauses(lines[start + 1:intro_end], "Skip if"),
                         **_source(path, lines, start, intro_end)})
        for position, (index, item_id, _, item_name, item, control) in enumerate(members):
            item_end = members[position + 1][0] if position + 1 < len(members) else end
            if control:
                item_end = index + 1
            source = _source(path, lines, index, item_end)
            if control:
                definition, requires, skip_if = item_name, [control[3].strip()] if control[3].strip() else [], []
            else:
                tail = item[3].strip().lstrip("—–- ")
                body = lines[index + 1:source["line_end"]]
                definition = (tail + "\n" + "".join(body)).strip()
                requires = _clauses(body, "Requires")
                skip_if = _clauses(body, "Skip if")
            items.append({"id": item_id, "family_id": family, "name": item_name,
                          "definition": definition, "requires": requires, "skip_if": skip_if,
                          **source})
    context = {}
    selectors = {"scope": "0. scope:", "applicability": "0.1 ", "coverage": "how to use"}
    for key, prefix in selectors.items():
        index = next((i for i in range(marker, checklist)
                      if (heading := _heading(lines[i])) and heading[1].casefold().startswith(prefix)), None)
        if index is not None:
            context[key] = _source(path, lines, index, _end_section(lines, index))
    branches, branch_metadata = _branches(branch_source, user_branch_definitions)
    identity = {"loader_version": LOADER_VERSION, "source_sha256": digest(raw),
                "branch_source_sha256": branch_metadata["source_sha256"] if branch_metadata else None}
    taxonomy_hash = digest(identity)
    return {"schema_version": "1.0", "loader_version": LOADER_VERSION,
            "taxonomy_id": "trigger-taxonomy-" + taxonomy_hash[:24], "taxonomy_hash": taxonomy_hash,
            "source_file": str(path), "source_sha256": identity["source_sha256"],
            "item_count": len(items), "items": items, "families": families,
            "context": context, "branches": branches, "branch_source": branch_metadata}
