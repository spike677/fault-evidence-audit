"""Parse the original V4 source verbatim; no revisions or crosswalk generation."""
from __future__ import annotations

import re
from pathlib import Path

from .store import AuditError, digest

V4_VERSION = "V4-ORIGINAL-v1"
LEGACY_VERSION = "TRIGGER42-ORIGINAL-v1"
PROFILE = "V4_AND_ORIGINAL42_v1"
CLASS_IDS = tuple(f"{prefix}{i}" for prefix, n in (("D", 4), ("N", 6), ("S", 9), ("I", 4), ("T", 3), ("C", 5)) for i in range(1, n + 1))
INPUT_ROLES = {"INPUT_VALUE", "INPUT_SHAPE", "INPUT_DTYPE", "INPUT_LAYOUT", "INDEX_OR_OFFSET", "API_CONTROL"}


def require_original_profile(payload: dict):
    """Archived interpretations cannot silently become original-rule judgments."""
    taxonomy = payload.get("taxonomy") or {}
    profile = payload.get("classification_profile", "")
    v4 = payload.get("v4_taxonomy") or {}
    if (payload.get("input_condition_scheme") == "REVISED42"
            or str(taxonomy.get("definition_version") or "").startswith("TRIGGER42-BOUNDARIES-")
            or profile == "V4_AND_REVISED42_v1" or payload.get("mapping")
            or v4 and v4.get("definition_version") != V4_VERSION):
        raise AuditError("Archived revised profile is not supported; create a new run from original sources")
    for item in taxonomy.get("items", []):
        if "family_requires_override" in item or "family_skip_override" in item:
            raise AuditError("Original API42 cannot carry family-clause overrides")
    for item in v4.get("items", []):
        if (item.get("requires") != item.get("original_requires", item.get("requires"))
                or item.get("skip_if") != item.get("original_skip_if", item.get("skip_if"))):
            raise AuditError("Original V4 prerequisites cannot be overridden")


def _anchor(path, lines, start, end):
    return {"source_file": str(path), "line_start": start + 1, "line_end": end,
            "source_quote": "".join(lines[start:end]).rstrip()}

def load_v4(path: Path) -> dict:
    path = Path(path).resolve()
    raw = path.read_bytes()
    lines = raw.decode("utf-8-sig").splitlines(keepends=True)
    text = "".join(lines)
    starts = [(n, m[1], m[2]) for n, line in enumerate(lines)
              if (m := re.match(r"^### ([DNSITC]\d+) (.+?)\s*$", line))]
    if [key for _, key, _ in starts] != list(CLASS_IDS):
        raise AuditError("V4 needs the complete ordered 31 condition classes")
    items, mounts, guides, constructors = [], [], [], {}
    for position, (start, key, name) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else next(
            (n for n in range(start + 1, len(lines)) if lines[n].startswith("## ")), len(lines))
        body = lines[start:end]
        fields = {}
        for label, field in (("条件定义", "definition"), ("检验目的", "purpose"),
                             ("适用前提（Requires）", "requires"), ("跳过/能力限制（Skip if）", "skip_if")):
            prefix = "- **" + label + "**："
            matches = [v.strip()[len(prefix):] for v in body if v.strip().startswith(prefix)]
            if len(matches) != 1:
                raise AuditError(f"V4 {key} needs exactly one complete {label}")
            fields[field] = matches[0]
        construction_ids = []
        for offset, line in enumerate(body):
            match = re.match(r"^  - `([^`]+)` — \*\*(.+?)\*\*：(.*)$", line.rstrip())
            if match:
                cid, cname, definition = match.groups()
                value = {"id": cid, "name": cname, "definition": definition.strip()}
                if cid in constructors and any(constructors[cid][f] != value[f] for f in value):
                    raise AuditError("Shared V4 construction code has inconsistent definitions: " + cid)
                constructors.setdefault(cid, {**value, "source_occurrences": []})["source_occurrences"].append(
                    _anchor(path, lines, start + offset, start + offset + 1))
                construction_ids.append(cid)
                mounts.append({"category_id": key, "construction_id": cid})
            example = re.match(r"^\d+\. \*\*(" + key + r"-\d+)\*\*：\*\*(.+?)\*\*(.*)$", line.rstrip())
            if example:
                guides.append({"guide_id": example[1], "category_id": key,
                    "title": example[2], "text": example[3].strip(),
                    "source_status": "CONSTRUCTION_LEAD_NOT_DEVICE_VERIFIED",
                    **_anchor(path, lines, start + offset, start + offset + 1)})
        if not construction_ids or len(construction_ids) != len(set(construction_ids)):
            raise AuditError("V4 category needs unique mounted construction codes: " + key)
        items.append({"id": key, "family_id": key[0], "name": name,
            "definition": fields["definition"], "purpose": fields["purpose"],
            "original_requires": [fields["requires"]], "original_skip_if": [fields["skip_if"]],
            "requires": [fields["requires"]],
            "skip_if": [fields["skip_if"]],
            "construction_requires": [],
            "path_requires": [],
            "analysis_requires": [],
            "source_status": "ORIGINAL_VERBATIM", "construction_ids": construction_ids,
            **_anchor(path, lines, start, end)})
    if len(constructors) != 55 or len(mounts) != 64 or len(guides) != 195 or len({v["guide_id"] for v in guides}) != 195:
        raise AuditError("V4 counts must be 55 unique constructions, 64 mounts and 195 unique guidance IDs")
    methods = []
    for key in ("E1", "E2", "E3", "E4", "E5"):
        start = next((i for i, line in enumerate(lines) if line.startswith("### " + key + " ")), None)
        if start is None:
            raise AuditError("V4 execution protocol missing: " + key)
        end = next((i for i in range(start + 1, len(lines)) if re.match(r"^#{1,3} ", lines[i])), len(lines))
        methods.append({"method_id": key, "name": lines[start].strip()[4:],
            "definition": "".join(lines[start + 1:end]).strip(), "execution_implemented": False,
            **_anchor(path, lines, start, end)})
    identity = {"definition_version": V4_VERSION, "source_sha256": digest(raw)}
    hashed = digest(identity)
    return {"schema_version": "1.0", "definition_version": V4_VERSION,
        "taxonomy_id": "trigger-v4-" + hashed[:24], "taxonomy_hash": hashed,
        "source_file": str(path), "source_sha256": digest(raw), "original_document": text,
        "item_count": 31, "construction_count": 55, "mount_count": 64, "guide_count": 195,
        "items": items, "constructions": list(constructors.values()), "mounts": mounts, "guides": guides,
        "methods": methods, "global_rules": text[:text.index("## D 退化输入")],
        "source_audit_status": "COMPANION_AUDIT_NOT_PROVIDED", "execution_implemented": False}


def canonical_conditions(item: dict, family: dict | None = None) -> set[tuple[str, str]]:
    family = family or {}
    includes = [item["definition"], *item.get("requires", []),
                *family.get("requires", [])]
    excludes = [*item.get("skip_if", []), *family.get("skip_if", [])]
    return {("INCLUSION", v.strip()) for v in includes if v.strip()} | {("EXCLUSION", v.strip()) for v in excludes if v.strip()}


def model_v4(frozen: dict) -> dict:
    """Complete classification rules; all 195 guides stay frozen for design tasks."""
    keys = ("id", "family_id", "name", "definition", "purpose", "original_requires", "original_skip_if",
            "requires", "skip_if", "construction_requires", "path_requires", "analysis_requires",
            "source_status", "construction_ids", "line_start", "line_end")
    return {k: frozen[k] for k in ("taxonomy_id", "taxonomy_hash", "definition_version", "source_sha256", "item_count",
        "construction_count", "mount_count", "guide_count", "source_audit_status")} | {
        "items": [{k: v[k] for k in keys if k in v} for v in frozen["items"]],
        "constructions": [{k: c[k] for k in ("id", "name", "definition")} for c in frozen["constructions"]],
        "methods": [{k: m[k] for k in ("method_id", "name", "definition")} for m in frozen["methods"] if m["method_id"] in {"E1", "E2", "E3", "E4", "E5"}],
        "global_rules": frozen["global_rules"],
        "input_scope": {"all_31_definitions_complete": True, "all_55_constructions_complete": True,
            "all_64_mounts_included": True, "guidance_examples_included": False,
            "exclusion_reason": "195 guidance examples are a separate frozen design index, not classification prerequisites"}}
