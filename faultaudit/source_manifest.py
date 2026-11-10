"""Program-owned anchors for a frozen source row; no header guessing."""
from __future__ import annotations

import copy
from typing import Literal
from pydantic import Field

from .contracts import Contract
from .store import AuditError, digest
from .trigger_assessment import ConditionFact

VERSION = "source-row-manifest-1"
SELECTION_CONTRACT = "A1_SOURCE_SELECTION_V2"


class FieldBinding(Contract):
    origin: Literal["SOURCE_DECLARATION", "MODEL_DERIVED", "UNKNOWN"]
    source_ids: list[str] = Field(default_factory=list)
    derived_text: str = ""
    reason: str = ""


def materialize_fields(case, manifest, bindings):
    """The model selects immutable IDs; it never authors original facts or anchors."""
    if manifest != build(case):
        raise AuditError("Source manifest differs from the frozen source row")
    entries = {e["source_id"]: e for e in manifest["entries"]}
    claims, facts, selected = {}, {}, {}
    for field, binding in bindings.items():
        ids = binding.source_ids
        if len(ids) != len(set(ids)) or not set(ids) <= set(entries):
            raise AuditError(f"{field}: unknown or duplicate source_id")
        if binding.origin == "UNKNOWN":
            if ids or binding.derived_text or not binding.reason.strip():
                raise AuditError(f"{field}: UNKNOWN needs a gap reason, no asserted facts")
            claims[field] = {"text": binding.reason, "status": "UNKNOWN", "condition_fact_ids": []}
            continue
        if not ids:
            raise AuditError(f"{field}: declarations and deductions need supporting source_ids")
        if binding.origin == "SOURCE_DECLARATION" and binding.derived_text:
            raise AuditError(f"{field}: the program owns declaration text and exact quotes")
        if binding.origin == "MODEL_DERIVED" and (not binding.derived_text.strip() or not binding.reason.strip()):
            raise AuditError(f"{field}: MODEL_DERIVED needs derived_text and a derivation_reason")
        for source_id in ids:
            entry = entries[source_id]
            # resolve() checks the actual coordinate and nonblank original text.
            ref = {"source_id": source_id, "quote": entry["original_value"]}
            cells = resolve(manifest, [ref])
            facts[source_id] = {"fact_id": source_id, "statement": entry["original_value"],
                "subject": "SOURCE_RECORD", "role": "UNKNOWN", "evidence_basis": "SOURCE_DEFINITION",
                "source_cells": cells, "source_refs": [ref]}
            selected[source_id] = copy.deepcopy(entry)
        claims[field] = {"text": ("\n".join(entries[k]["original_value"] for k in ids)
                                      if binding.origin == "SOURCE_DECLARATION" else binding.derived_text),
                         "status": "STATED" if binding.origin == "SOURCE_DECLARATION" else "INFERRED",
                         "condition_fact_ids": ids,
                         "derivation_reason": binding.reason if binding.origin == "MODEL_DERIVED" else ""}
    return claims, list(facts.values()), {"contract": SELECTION_CONTRACT,
        "manifest_hash": manifest["manifest_hash"], "selected_entries": list(selected.values()),
        "field_bindings": {field: binding.model_dump() for field, binding in bindings.items()}}


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
