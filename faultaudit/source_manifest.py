"""Program-owned anchors for a frozen source row; no header guessing."""
from __future__ import annotations

import copy
from pydantic import Field

from .contracts import Contract
from .store import AuditError, digest
from .trigger_assessment import ConditionFact

VERSION = "source-row-manifest-1"


class SourceReference(Contract):
    source_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class ManifestFact(ConditionFact):
    source_refs: list[SourceReference] = Field(default_factory=list)


def build(case):
    entries = []
    for field, value in sorted(case.get("raw", {}).items()):
        entry = {"workbook_hash": case["source_sha256"], "sheet_name": case["sheet"],
                 "row_number": case["row"], "cell_address": case.get("cell_locations", {}).get(field, ""),
                 "column_key": field, "original_value": value}
        entries.append({"source_id": "source-" + digest(entry)[:32], **entry})
    data = {"version": VERSION, "case_id": case["case_id"], "entries": entries}
    return {**data, "manifest_hash": digest(data)}


def resolve(manifest, references):
    entries = {e["source_id"]: e for e in manifest["entries"]}
    cells = []
    for reference in references:
        ref = reference.model_dump() if hasattr(reference, "model_dump") else reference
        entry = entries.get(ref["source_id"])
        if (not entry or not entry["cell_address"] or not ref["quote"].strip()
                or ref["quote"] not in entry["original_value"]):
            raise AuditError("Source manifest ID, coordinate or exact quote is invalid")
        cell = {"field": entry["column_key"], "cell": entry["cell_address"], "quote": ref["quote"]}
        if cell in cells:
            raise AuditError("Duplicate source manifest reference")
        cells.append(cell)
    return cells


def references_for_cells(manifest, cells):
    """Only exact old anchors can be normalized for an explicit review."""
    result = []
    for cell in cells:
        matches = [e for e in manifest["entries"]
                   if e["column_key"] == cell["field"] and e["cell_address"] == cell["cell"]
                   and cell["quote"].strip() and cell["quote"] in e["original_value"]]
        if len(matches) != 1:
            raise AuditError("Historical source cell cannot be bound exactly; do not infer a header alias")
        result.append({"source_id": matches[0]["source_id"], "quote": cell["quote"]})
    return result


def prepare(payload, response):
    manifest = payload.get("source_manifest")
    if not manifest:
        return response
    if manifest != build(payload["subject"]["source_case"]):
        raise AuditError("Source manifest differs from the frozen source row")
    value = copy.deepcopy(response)
    for fact in value.get("condition_facts", []):
        refs = fact.get("source_refs", [])
        if fact.get("subject") == "SOURCE_RECORD" and payload.get("source_manifest_required") and not refs:
            raise AuditError("A1 original facts must select source_refs from the supplied manifest")
        if refs:
            cells = resolve(manifest, refs)
            if fact.get("source_cells") and fact["source_cells"] != cells:
                raise AuditError("Submitted source cells disagree with their manifest IDs")
            fact["source_cells"] = cells
    return value


def canonical_fact(fact):
    return {key: value for key, value in fact.items() if key != "source_refs"}
