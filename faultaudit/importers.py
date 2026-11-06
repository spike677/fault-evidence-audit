"""Read source workbooks and text tables without overwriting source material."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .contracts import CatalogItem, ReferenceOccurrence, SourceCase


_ALIASES = {
    "id": ("统一ID", "统一id", "external_id", "问题ID", "故障ID", "ID", "id", "编号", "序号"),
    "description": ("问题描述", "故障描述", "故障现象", "问题现象", "description", "symptom", "问题", "描述", "故障模式描述", "故障名称", "故障模式名称", "模式名称", "故障模式"),
    "customer_model": ("客户/模型", "客户／模型", "客户模型", "customer_model", "模型", "客户"),
    "operator": ("算子", "operator", "operator_raw", "涉及算子", "故障算子", "作用点"),
    "root_cause": ("根因", "根因/进展", "根因／进展", "root_cause_raw", "root_cause", "根因原文", "原因", "故障根因"),
    "item_id": ("item_id", "故障模式ID", "故障模式编号", "故障编号", "ID", "id", "编号", "序号", "统一ID"),
    "mechanism": ("mechanism", "失效机理", "故障机理", "机理", "根因", "故障模式", "故障原因"),
    "trigger": ("trigger", "触发条件", "触发", "适用条件", "条件"),
}
_REFERENCE_HEADERS = ("wiki", "dts", "pr", "github", "gitcode", "codehub", "链接", "url", "commit")
_EMPTY_LINKS = {"", "无", "暂无", "无链接", "未提供", "-", "—", "/", "n/a", "none", "null", "无（待补）", "无(待补)"}
_URL_RE = re.compile(r"https?://[^\s<>\[\]\"'()\\，；。]*", re.IGNORECASE)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def is_empty_link_value(value: Any) -> bool:
    """Recognize only a whole-field empty-link placeholder, never a substring."""
    return _text(value).strip().casefold() in _EMPTY_LINKS


def _pick(raw: dict[str, str], field: str) -> str:
    keys = {key.strip().casefold(): value for key, value in raw.items()}
    for alias in _ALIASES[field]:
        value = keys.get(alias.casefold(), "")
        if value.strip():
            return value
    return ""


def _stable(prefix: str, *values: Any) -> str:
    body = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return prefix + "-" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]


def _headers(values: list[Any], warnings: list[str], where: str) -> list[str]:
    seen: dict[str, int] = {}
    result = []
    for i, value in enumerate(values, start=1):
        name = _text(value).strip() or f"__column_{i}"
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            warnings.append(f"{where}: duplicate header {name!r}; retained as {name}#{seen[name]}")
            name = f"{name}#{seen[name]}"
        result.append(name)
    return result


def _normalise_json_rows(data: Any) -> list[tuple[str, list[Any]]]:
    if isinstance(data, list):
        return [("JSON", data)]
    if not isinstance(data, dict):
        raise ValueError("JSON input must be a list or object containing cases/rows/items/sheets")
    if isinstance(data.get("sheets"), dict):
        return [(str(name), rows) for name, rows in data["sheets"].items()]
    for key in ("cases", "rows", "items", "records", "data"):
        if isinstance(data.get(key), list):
            return [("JSON", data[key])]
    raise ValueError("JSON object must contain cases, rows, items, records, data or sheets")


def _select_sheets(available: list[str], sheets: list[str] | None) -> list[str]:
    if sheets is None:
        return available
    if not sheets:
        raise ValueError("Sheet selection must contain at least one sheet name")
    missing = sorted(set(sheets) - set(available))
    if missing:
        raise ValueError(f"Unknown sheet(s): {', '.join(missing)}; available: {', '.join(available)}")
    selected = set(sheets)
    return [name for name in available if name in selected]


def _read_source(path: Path, warnings: list[str], *, sheets: list[str] | None = None
                 ) -> tuple[list[tuple[str, int, dict[str, str], dict[str, str], dict[str, str]]], list[str]]:
    """Return source rows and selected sheet names, including empty sheets."""
    suffix = path.suffix.casefold()
    records = []
    if suffix in {".csv", ".tsv"}:
        selected_sheets = _select_sheets([path.name], sheets)
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter="\t" if suffix == ".tsv" else ",")
            try:
                head = _headers(next(reader), warnings, path.name)
            except StopIteration:
                return [], selected_sheets
            for rownum, values in enumerate(reader, start=2):
                if len(values) > len(head):
                    warnings.append(f"{path.name}:{rownum}: values exceed header width; extra values retained")
                names = head + [f"__column_{i + 1}" for i in range(len(head), len(values))]
                raw = {name: _text(values[i]) if i < len(values) else "" for i, name in enumerate(names)}
                coordinates = {name: f"column:{i + 1}" for i, name in enumerate(names)}
                records.append((path.name, rownum, raw, coordinates, {}))
        return records, selected_sheets
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        tables = _normalise_json_rows(data)
        selected_sheets = _select_sheets([name for name, _ in tables], sheets)
        for sheet, rows in tables:
            if sheet not in selected_sheets:
                continue
            if not isinstance(rows, list):
                raise ValueError(f"JSON sheet {sheet!r} must contain a list")
            for index, entry in enumerate(rows, start=1):
                if not isinstance(entry, dict):
                    raise ValueError(f"JSON {sheet}[{index}] must be an object")
                source = entry.get("raw") if isinstance(entry.get("raw"), dict) else entry
                raw = {str(key): _text(value) for key, value in source.items()}
                coordinates = {name: f"/{sheet}/{index - 1}/{name}" for name in raw}
                records.append((sheet, index, raw, coordinates, {}))
        return records, selected_sheets
    if suffix in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook

        # Normal read mode retains hyperlink targets. This module never saves workbooks.
        workbook = load_workbook(path, read_only=False, data_only=False, keep_links=False)
        try:
            selected_sheets = _select_sheets(workbook.sheetnames, sheets)
            known = {name.casefold() for aliases in _ALIASES.values() for name in aliases}
            for sheet in workbook.worksheets:
                if sheet.title not in selected_sheets:
                    continue
                rows = sheet.iter_rows()
                nonempty = []
                for cells in rows:
                    if any(cell.value is not None and _text(cell.value).strip() for cell in cells):
                        nonempty.append(cells)
                if not nonempty:
                    continue
                header_index = next((i for i, cells in enumerate(nonempty[:20])
                                     if sum(_text(cell.value).strip().casefold() in known for cell in cells) >= 2), 0)
                for cells in nonempty[:header_index]:
                    warnings.append(f"{sheet.title}:{cells[0].row}: preamble before detected header was not imported")
                header_cells = nonempty[header_index]
                head = _headers([cell.value for cell in header_cells], warnings, sheet.title)
                if sheet.sheet_state != "visible":
                    warnings.append(f"{sheet.title}: hidden worksheet included")
                for cells in nonempty[header_index + 1:]:
                    raw = {name: _text(cells[i].value) if i < len(cells) else "" for i, name in enumerate(head)}
                    locations = {name: cells[i].coordinate for i, name in enumerate(head) if i < len(cells)}
                    targets = {name: cells[i].hyperlink.target for i, name in enumerate(head)
                               if i < len(cells) and cells[i].hyperlink and cells[i].hyperlink.target}
                    records.append((sheet.title, cells[0].row, raw, locations, targets))
                if sheet.merged_cells.ranges:
                    warnings.append(f"{sheet.title}: merged cells retained without filling empty cells: "
                                    + ", ".join(str(value) for value in sheet.merged_cells.ranges))
                hidden = [str(num) for num, dimension in sheet.row_dimensions.items() if dimension.hidden]
                if hidden:
                    warnings.append(f"{sheet.title}: hidden rows included: {','.join(hidden)}")
        finally:
            workbook.close()
        return records, selected_sheets
    raise ValueError(f"Unsupported input extension {suffix!r}; use xlsx, csv, tsv or json")


def _read(path: Path, warnings: list[str], *, sheets: list[str] | None = None
          ) -> list[tuple[str, int, dict[str, str], dict[str, str], dict[str, str]]]:
    """Return (sheet,row,raw,header->cell coordinate,header->hyperlink target)."""
    return _read_source(path, warnings, sheets=sheets)[0]


def extract_urls(raw: str) -> list[str]:
    """Recover conservative HTTP(S) candidates, preserving raw text elsewhere.

    Markdown wrappers frequently repeat the same URL as both label and target;
    only those same-cell candidates are coalesced. References in different cells
    or source rows remain independent, even when their target is identical.
    """
    unescaped = html.unescape(re.sub(r"\\([\\\[\]()_*])", r"\1", raw))
    result = []
    for match in _URL_RE.finditer(unescaped):
        url = match.group(0).rstrip(".,;:!?，；。")
        if url not in result:
            result.append(url)
    return result


def _valid_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        _ = parts.port
        return parts.scheme.lower() in {"http", "https"} and bool(parts.hostname) and not parts.username
    except ValueError:
        return False


def _references(case: dict[str, Any], locations: dict[str, str], targets: dict[str, str],
                warnings: list[str]) -> list[dict[str, Any]]:
    references = []
    for key, raw in case["raw"].items():
        target = targets.get(key)
        urls = extract_urls(raw)
        if target and target not in urls:
            urls.append(target)
        reference_key = key.casefold()
        looks_like_ref = (any(token in reference_key for token in _REFERENCE_HEADERS if token != "pr")
                          or bool(re.search(r"(^|[\s_/#（(])prs?($|[\s_/#）)])", reference_key))
                          or (reference_key.startswith("pr") and any("\u4e00" <= char <= "\u9fff" for char in reference_key))
                          or raw.lstrip().upper().startswith("=HYPERLINK("))
        if not urls and (not looks_like_ref or is_empty_link_value(raw)):
            continue
        location = f"{case['sheet']}!{locations.get(key, key)} (row {case['row']})"
        for index, candidate in enumerate(urls or [None], start=1):
            valid = bool(candidate) and _valid_url(candidate)
            status = "PARSED" if valid else "MALFORMED" if candidate else "UNRESOLVED"
            if status != "PARSED":
                warnings.append(f"{location}: {status.lower()} reference retained")
            reference = ReferenceOccurrence(
                ref_id=_stable("ref", case["case_id"], key, index, candidate),
                case_id=case["case_id"], raw_text=raw if raw else target or "",
                url=candidate, origin=case["source_kind"], location=location, status=status,
            )
            references.append(reference.model_dump())
    return references


def _document(path: Path, sha256: str, source_kind: str) -> dict[str, Any]:
    return {"source_file": str(path), "source_sha256": sha256,
            "source_kind": source_kind, "size_bytes": path.stat().st_size}


def import_cases(path: str | Path, source_kind: str = "LEGACY_TABLE") -> dict[str, Any]:
    path = Path(path).resolve()
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    warnings: list[str] = []
    cases, references, exclusions = [], [], []
    for sheet, row, raw, locations, targets in _read(path, warnings):
        if not any(value.strip() for value in raw.values()):
            exclusions.append({"exclusion_id": _stable("excluded", sha256, sheet, row), "source_file": str(path),
                               "source_sha256": sha256, "sheet": sheet, "row": row, "reason": "EMPTY_ROW"})
            continue
        origin = "SOURCE_RAW" if source_kind in {"ORIGINAL_WEEKLY", "ORIGINAL_OBP", "SOURCE_WEEKLY_REPORT", "SOURCE_OBP"} else "LEGACY_DERIVED_UNKNOWN"
        case = SourceCase(
            case_id=_stable("case", sha256, sheet, row), external_id=_pick(raw, "id"),
            source_file=str(path), source_sha256=sha256, sheet=sheet, row=row,
            source_kind=source_kind, raw=raw, cell_locations=locations, description=_pick(raw, "description"),
            customer_model=_pick(raw, "customer_model"), operator_raw=_pick(raw, "operator"),
            root_cause_raw=_pick(raw, "root_cause"), root_cause_origin=origin,
        ).model_dump()
        if not case["description"]:
            warnings.append(f"{sheet}:{row}: description not found; source row retained")
        cases.append(case)
        references.extend(_references(case, locations, targets, warnings))
    document = {**_document(path, sha256, source_kind), "case_count": len(cases),
                "reference_count": len(references), "excluded_count": len(exclusions),
                "input_record_count": len(cases) + len(exclusions)}
    return {"cases": cases, "references": references, "exclusions": exclusions,
            "warnings": warnings, "documents": [document]}


def import_catalog(path: str | Path, *, sheets: list[str] | None = None,
                   scope: str = "UNSPECIFIED", expected_count: int | None = None) -> dict[str, Any]:
    path = Path(path).resolve()
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    warnings: list[str] = []
    items = []
    seen_ids: set[str] = set()
    records, selected_sheets = _read_source(path, warnings, sheets=sheets)
    for sheet, row, raw, locations, _ in records:
        if not any(value.strip() for value in raw.values()):
            continue
        item_id = _pick(raw, "item_id") or _stable("catalog", sha256, sheet, row)
        if item_id in seen_ids:
            warnings.append(f"{sheet}:{row}: duplicate catalog item_id {item_id!r}; retained for gate review")
        seen_ids.add(item_id)
        items.append(CatalogItem(
            item_id=item_id, description=_pick(raw, "description"), operator=_pick(raw, "operator"),
            mechanism=_pick(raw, "mechanism"), trigger=_pick(raw, "trigger"), raw=raw,
            source_file=str(path), source_sha256=sha256,
            source_location=f"{sheet}!row:{row}; cells={','.join(locations.values())}",
            catalog_scope=scope, catalog_version=sha256, sheet=sheet, row=row,
        ).model_dump())
    if sheets is not None and not items:
        raise ValueError("Selected catalog sheets contain no items")
    if expected_count is not None and len(items) != expected_count:
        raise ValueError(f"Catalog item count mismatch: expected {expected_count}, got {len(items)}")
    identity = {"source_sha256": sha256, "sheets": sorted(selected_sheets), "scope": scope}
    document = {**_document(path, sha256, "CATALOG"), "catalog_identity": identity}
    return {"items": items, "warnings": warnings, "catalog_identity": identity,
            "documents": [document]}
