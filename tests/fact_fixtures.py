"""Protocol fixtures add explicit unknowns; they do not infer business truth."""
def with_fact_audit(result, task):
    if task["kind"] != "compare":
        return result
    case, snapshot = task["payload"]["case"], task["payload"]["snapshot"]
    segment = snapshot["segments"][0]
    ref = {"segment_id": segment["segment_id"], "quote": segment["text"]}
    field = next((key for key, value in case["raw"].items() if value.strip() and case["cell_locations"].get(key)), None)
    facts = [{"category": category, "source_field": "", "source_quote": "", "source_cell": "",
              "source_meaning": "", "evidence_meaning": "", "evidence": [], "relation": "UNKNOWN",
              "reason": "Synthetic protocol fixture does not infer this fact"}
             for category in ("NUMBER", "TERM", "SCENARIO", "TECHNICAL_CONCLUSION")]
    if field:
        facts[2].update(source_field=field, source_quote=case["raw"][field], source_cell=case["cell_locations"][field], evidence=[ref])
    refs = list(result.get("evidence") or [])
    if ref not in refs:
        refs.append(ref)
    return {**result, "evidence": refs, "fact_comparisons": facts,
            "applicable_issue": {"label": task["payload"]["summary"]["issues"][0]["label"], "evidence": [ref],
                                 "selection_reason": "Scope of synthetic fixture"},
            "self_check": {"attempt": 1, "numeric_meaning_checked": True, "citations_checked": True,
                           "counterevidence_checked": True, "issue_scope_checked": True, "event_vs_technical_checked": True,
                           "passed": True, "issues": []}}
