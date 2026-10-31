"""Read-only, ID-based statistics over exported reports and explicit round inputs.

This module never opens SQLite or fills missing round history by inference.
Classification axes overlap: their case counts must not be added together.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

AXES = ("case_attribution", "event_relation", "pattern_relation", "support_level", "review_status")
COLLECTION_IDS = {"cases": "case_id", "snapshots": "snapshot_id", "judgments": "judgment_id",
                  "mappings": "task_id", "tasks": "task_id", "model_tasks": "task_id", "model_results": "task_id"}


def _issue(code: str, message: str, **details) -> dict:
    return {"code": code, "message": message, **details}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _run_id(data: dict) -> str | None:
    run = data.get("run")
    value = run.get("run_id") if isinstance(run, dict) else data.get("run_id")
    return value if isinstance(value, str) and value.strip() else None


def _index(data: dict, collection: str, errors: list, warnings: list, *, context: str) -> tuple[dict, bool]:
    if collection not in data:
        warnings.append(_issue("MISSING_COLLECTION", "Report collection is absent; completeness cannot be assumed",
                               context=context, collection=collection))
        return {}, False
    records = data[collection]
    if not isinstance(records, list):
        errors.append(_issue("INVALID_COLLECTION", "Report collection must be a list", context=context, collection=collection))
        return {}, False
    indexed = {}
    duplicate_count = 0
    for position, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(_issue("INVALID_RECORD", "Report record must be an object", context=context,
                                 collection=collection, position=position))
            continue
        field = COLLECTION_IDS[collection]
        identifier = record.get(field)
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append(_issue("MISSING_RECORD_ID", "A record has no stable identity", context=context,
                                 collection=collection, position=position, id_field=field))
            continue
        try:
            encoded = _canonical(record)
        except (ValueError, TypeError):
            errors.append(_issue("INVALID_RECORD_VALUE", "Record cannot be serialized deterministically", context=context,
                                 collection=collection, record_id=identifier))
            continue
        if identifier in indexed:
            if _canonical(indexed[identifier]) != encoded:
                errors.append(_issue("CONFLICTING_DUPLICATE_ID", "Same ID has different records; neither copy is selected",
                                     context=context, collection=collection, record_id=identifier))
            else:
                duplicate_count += 1
        else:
            indexed[identifier] = record
    if duplicate_count:
        warnings.append(_issue("IDENTICAL_DUPLICATES_DEDUPLICATED", "Identical repeated records count once",
                               context=context, collection=collection, duplicate_count=duplicate_count))
    return indexed, True


def _counts(judgments: list[dict]) -> dict:
    return {"judgment_count": len(judgments), "case_count": len({j["case_id"] for j in judgments})}


def _axes(judgments: list[dict]) -> dict:
    result = {}
    for axis in AXES:
        buckets = defaultdict(list)
        for judgment in judgments:
            buckets[judgment[axis]].append(judgment)
        result[axis] = {value: _counts(records) for value, records in sorted(buckets.items())}
    return result


def _empty_current(status: str) -> dict:
    return {"status": status, "including_rejected": {"judgment_count": None, "case_count": None},
            "excluding_rejected": {"judgment_count": None, "case_count": None},
            "rejected": {"judgment_count": None, "case_count": None},
            "confirmed_accepted": {"judgment_count": None, "case_count": None},
            "snapshot_count": None, "mapping_count": None, "mapping_count_excluding_rejected": None,
            "classifications": None, "classifications_excluding_rejected": None}


def _current(indexes: dict, present: dict, errors: list, warnings: list) -> dict:
    initial_errors = len(errors)
    required = ("cases", "snapshots", "judgments", "mappings", "tasks")
    unknown = not all(present[name] for name in required)
    current = {name: [] for name in ("snapshots", "judgments", "mappings")}
    for name, output in current.items():
        for identity, record in indexes[name].items():
            if not isinstance(record.get("is_stale"), bool):
                unknown = True
                warnings.append(_issue("CURRENT_SCOPE_UNKNOWN", "is_stale metadata is missing or invalid; current totals are unknown",
                                       collection=name, record_id=identity))
                continue
            if record["is_stale"]:
                continue
            if name in {"judgments", "mappings"}:
                case_id = record.get("case_id")
                task = indexes["tasks"].get(record.get("task_id"))
                if not isinstance(case_id, str) or not case_id.strip() or not task:
                    unknown = True
                    warnings.append(_issue("CURRENT_DEPENDENCY_UNKNOWN", "Current result lacks case/task identity",
                                           collection=name, record_id=identity))
                    continue
                if present["cases"] and case_id not in indexes["cases"]:
                    errors.append(_issue("MISSING_CASE", "A current result references an absent case",
                                         collection=name, record_id=identity, case_id=case_id))
                if task.get("status") != "SUCCEEDED":
                    errors.append(_issue("CURRENT_TASK_STATE_CONFLICT", "Non-stale result does not have a succeeded pipeline task",
                                         collection=name, record_id=identity, task_status=task.get("status")))
                if name == "judgments":
                    if any(not isinstance(record.get(axis), str) or not record[axis].strip() for axis in AXES):
                        unknown = True
                        warnings.append(_issue("CURRENT_CLASSIFICATION_UNKNOWN", "Judgment classification or review metadata is incomplete",
                                               record_id=identity))
                    snapshot = indexes["snapshots"].get(record.get("snapshot_id"))
                    if not snapshot:
                        errors.append(_issue("MISSING_SNAPSHOT", "A current judgment references an absent snapshot", record_id=identity))
                    elif snapshot.get("is_stale") is True:
                        errors.append(_issue("CURRENT_SNAPSHOT_STATE_CONFLICT", "Current judgment references a stale snapshot", record_id=identity))
                elif not isinstance(record.get("review_status"), str):
                    unknown = True
                    warnings.append(_issue("CURRENT_REVIEW_UNKNOWN", "Mapping review metadata is incomplete", record_id=identity))
            output.append(record)
    if len(errors) > initial_errors:
        return _empty_current("RECONCILIATION_FAILED")
    if unknown:
        return _empty_current("UNKNOWN")
    js = current["judgments"]
    non_rejected = [j for j in js if j["review_status"] != "REJECT"]
    confirmed = [j for j in js if j["case_attribution"] == "CONFIRMED" and j["event_relation"] == "SAME_EVENT"
                 and j["support_level"] == "DIRECT" and j["review_status"] == "ACCEPT"
                 and indexes["snapshots"][j["snapshot_id"]].get("status") == "COMPLETE"
                 and not j.get("conflicting_dimensions")
                 and "CONTRADICTED" not in (j.get("claim_support") or {}).values()]
    return {"status": "OK", "including_rejected": _counts(js), "excluding_rejected": _counts(non_rejected),
            "rejected": _counts([j for j in js if j["review_status"] == "REJECT"]),
            "confirmed_accepted": _counts(confirmed), "snapshot_count": len(current["snapshots"]),
            "mapping_count": len(current["mappings"]),
            "mapping_count_excluding_rejected": sum(m["review_status"] != "REJECT" for m in current["mappings"]),
            "classifications": _axes(js), "classifications_excluding_rejected": _axes(non_rejected)}


def _manifest_ids(manifest: dict, key: str, errors: list, warnings: list, *, required: bool) -> set[str] | None:
    value = manifest.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(_issue("INCOMPLETE_ROUND_MANIFEST", "Manifest must explicitly list valid IDs, including an empty list when none",
                             field=key))
        return None
    if len(value) != len(set(value)):
        warnings.append(_issue("MANIFEST_IDS_DEDUPLICATED", "Repeated manifest IDs count once", field=key))
    return set(value)


def _result_proof(record: dict, kind: str, indexes: dict, run_id: str, errors: list) -> None:
    task_id = record.get("task_id")
    task = indexes["tasks"].get(task_id)
    valid_state = task and (task.get("status") == "SUCCEEDED" or
                           (record.get("is_stale") is True and task.get("status") == "STALE"))
    if not valid_state or task.get("kind") != kind:
        errors.append(_issue("ROUND_PIPELINE_RESULT_MISSING", "New result needs a matching succeeded task or documented stale history",
                             result_id=record.get("judgment_id", task_id), pipeline_task_id=task_id))
        return
    candidates = [model_task for model_task in indexes["model_tasks"].values()
                  if model_task.get("pipeline_task_id") == task_id and model_task.get("kind") == kind]
    matched = False
    for model_task in candidates:
        response = indexes["model_results"].get(model_task["task_id"])
        if not response:
            continue
        if (model_task.get("run_id") != run_id or response.get("run_id") != run_id
                or not model_task.get("request_hash") or response.get("request_hash") != model_task["request_hash"]):
            errors.append(_issue("ROUND_MODEL_BINDING_CONFLICT", "Model request/result run or hash differs", task_id=model_task["task_id"]))
            continue
        payload, result = model_task.get("payload", {}), response.get("result", {})
        if not isinstance(payload, dict) or not isinstance(result, dict):
            continue
        case = payload.get("case", {})
        identifiers_match = case.get("case_id") == record.get("case_id") == result.get("case_id")
        if kind == "compare":
            identifiers_match = identifiers_match and (payload.get("snapshot", {}).get("snapshot_id")
                == record.get("snapshot_id") == result.get("snapshot_id"))
        if not identifiers_match:
            errors.append(_issue("ROUND_RESULT_ID_CONFLICT", "Returned result does not match its recorded case/snapshot", pipeline_task_id=task_id))
            continue
        # Every field returned by the accepted model must survive in the pipeline result.
        if any(key not in record or record[key] != value for key, value in result.items()):
            errors.append(_issue("ROUND_RESULT_CONTENT_CONFLICT", "Pipeline result differs from its accepted model response", pipeline_task_id=task_id))
            continue
        matched = True
    if not matched:
        errors.append(_issue("ROUND_MODEL_RESULT_MISSING", "No matching accepted model request/result proves this new result",
                             result_id=record.get("judgment_id", task_id), pipeline_task_id=task_id))


def _empty_round(status: str, reason: str) -> dict:
    return {"status": status, "new_judgment_count": None, "new_case_count": None, "new_snapshot_count": None,
            "new_mapping_count": None, "current_new_judgment_count": None, "current_new_case_count": None,
            "current_new_snapshot_count": None, "current_new_mapping_count": None,
            "new_judgment_count_excluding_rejected": None, "current_new_judgment_count_excluding_rejected": None,
            "reason": reason, "errors": []}


def _round(data: dict, indexes: dict, baseline: dict | None, manifest: dict | None,
           run_id: str | None, current_ok: bool, warnings: list) -> dict:
    if baseline is None or manifest is None:
        missing = "baseline report and round manifest" if baseline is None and manifest is None else "baseline report" if baseline is None else "round manifest"
        return _empty_round("UNKNOWN", "Missing " + missing + "; round additions are not inferred")
    errors = []
    if not isinstance(baseline, dict) or not isinstance(manifest, dict):
        output = _empty_round("RECONCILIATION_FAILED", "Baseline and manifest must be objects")
        output["errors"] = [_issue("INVALID_ROUND_INPUT", output["reason"])]
        return output
    if not run_id or _run_id(baseline) != run_id or manifest.get("run_id") != run_id:
        errors.append(_issue("ROUND_RUN_MISMATCH", "Report, baseline and round manifest must identify the same run"))
    before = {}
    for name in ("judgments", "mappings", "snapshots"):
        before[name], available = _index(baseline, name, errors, warnings, context="baseline")
        if not available or name not in data:
            errors.append(_issue("INCOMPLETE_ROUND_HISTORY", "Full before/after history is required", collection=name))
        removed = set(before[name]) - set(indexes[name])
        if removed:
            errors.append(_issue("BASELINE_HISTORY_MISSING", "After-report dropped baseline IDs", collection=name, ids=sorted(removed)))
        for identity in set(before[name]) & set(indexes[name]):
            mutable = {"is_stale", "review_status"}
            old = {key: value for key, value in before[name][identity].items() if key not in mutable}
            new = {key: value for key, value in indexes[name][identity].items() if key not in mutable}
            if old != new:
                errors.append(_issue("BASELINE_RECORD_CONTENT_CONFLICT", "An existing immutable ID changed content between reports",
                                     collection=name, record_id=identity))
    task_ids = _manifest_ids(manifest, "pipeline_task_ids", errors, warnings, required=False)
    jids = _manifest_ids(manifest, "judgment_ids", errors, warnings, required=task_ids is None)
    mids = _manifest_ids(manifest, "mapping_ids", errors, warnings, required=task_ids is None)
    sids = _manifest_ids(manifest, "snapshot_ids", errors, warnings, required=True)
    if task_ids is not None:
        missing_tasks = task_ids - set(indexes["tasks"])
        if missing_tasks:
            errors.append(_issue("ROUND_TASK_MISSING", "Manifest names pipeline tasks absent from report", ids=sorted(missing_tasks)))
        inferred_j = {identity for identity, record in indexes["judgments"].items()
                      if record.get("task_id") in task_ids and identity not in before["judgments"]}
        inferred_m = {identity for identity, record in indexes["mappings"].items()
                      if record.get("task_id") in task_ids and identity not in before["mappings"]}
        for explicit, inferred, field in ((jids, inferred_j, "judgment_ids"), (mids, inferred_m, "mapping_ids")):
            if explicit is not None and explicit != inferred:
                errors.append(_issue("MANIFEST_TASK_ID_CONFLICT", "Explicit IDs disagree with pipeline task selection", field=field))
        jids = inferred_j if jids is None else jids
        mids = inferred_m if mids is None else mids
    selected = {"judgments": jids, "mappings": mids, "snapshots": sids}
    for name, ids in selected.items():
        if ids is None:
            continue
        actual = set(indexes[name]) - set(before[name])
        if ids != actual:
            errors.append(_issue("ROUND_ID_SET_MISMATCH", "Manifest must match all and only IDs added since baseline",
                                 collection=name, missing_from_manifest=sorted(actual - ids), not_new_or_absent=sorted(ids - actual)))
    for name, kind in (("judgments", "compare"), ("mappings", "catalog")):
        for identity in selected[name] or set():
            if identity in indexes[name] and identity not in before[name]:
                _result_proof(indexes[name][identity], kind, indexes, run_id or "", errors)
    if errors:
        output = _empty_round("RECONCILIATION_FAILED", "Round inputs failed reconciliation; additions are not reported")
        output["errors"] = errors
        return output
    new_js = [indexes["judgments"][identity] for identity in jids or set()]
    output = _empty_round("KNOWN", "Manifest reconciled against retained before/after ID history and accepted results")
    output.update(new_judgment_count=len(new_js), new_case_count=len({j["case_id"] for j in new_js}),
                  new_snapshot_count=len(sids or set()), new_mapping_count=len(mids or set()))
    if all(isinstance(j.get("review_status"), str) for j in new_js):
        output["new_judgment_count_excluding_rejected"] = sum(j["review_status"] != "REJECT" for j in new_js)
    if current_ok:
        current_js = [j for j in new_js if j["is_stale"] is False]
        output.update(current_new_judgment_count=len(current_js), current_new_case_count=len({j["case_id"] for j in current_js}),
                      current_new_snapshot_count=sum(indexes["snapshots"][identity]["is_stale"] is False for identity in sids or set()),
                      current_new_mapping_count=sum(indexes["mappings"][identity]["is_stale"] is False for identity in mids or set()),
                      current_new_judgment_count_excluding_rejected=sum(j["review_status"] != "REJECT" for j in current_js))
    return output


def report_statistics(data: dict, baseline: dict | None = None, round_manifest: dict | None = None) -> dict:
    """Return explicit unknown/failed states without changing any input report.

    Mapping identity is its pipeline ``task_id`` in the report schema. A manifest
    supplies snapshot_ids plus judgment_ids/mapping_ids, or pipeline_task_ids.
    Round history includes results that became stale during that round; separate
    current_new_* counts exclude them. No source files or database are opened.
    """
    definitions = {"judgment_identity": "unique judgment_id", "case_identity": "unique case_id",
        "association_identity": "validate planned_associations/judged_associations count unique (case_id, snapshot_id) pairs, not judgment IDs",
        "snapshot_identity": "unique snapshot_id; an ingested snapshot does not require a completed model task",
        "mapping_identity": "mapping.task_id", "current_scope": "Current as of this input report's exported is_stale flags and task states, not a fresh database/policy query; is_stale=false and SUCCEEDED, with REJECT counted separately",
        "classifications_scope": "Current non-stale judgments including REJECT; excluding-REJECT axes are separately provided",
        "classifications_overlap": True,
        "classification_warning": "Axes overlap. Case counts and counts across different axes must not be summed or substituted for judgment counts.",
        "confirmed_accepted": "COMPLETE snapshot + CONFIRMED + SAME_EVENT + DIRECT + human review ACCEPT, without conflicting dimensions or CONTRADICTED claims",
        "new_case_count": "Unique cases involved in new judgments; not newly imported cases",
        "round_new_scope": "All IDs added after baseline, including results made stale later in the round"}
    errors, warnings = [], []
    if not isinstance(data, dict):
        return {"schema_version": "1.0", "run_id": None, "status": "RECONCILIATION_FAILED",
            "current": _empty_current("RECONCILIATION_FAILED"), "round": _empty_round("UNKNOWN", "No valid report"),
            "errors": [_issue("INVALID_REPORT", "Report must be an object")], "warnings": [], "definitions": definitions}
    run_id = _run_id(data)
    indexes, present = {}, {}
    for name in COLLECTION_IDS:
        indexes[name], present[name] = _index(data, name, errors, warnings, context="report")
    if not run_id:
        warnings.append(_issue("REPORT_RUN_UNKNOWN", "Report does not identify its run"))
    current = _current(indexes, present, errors, warnings)
    if errors:
        current = _empty_current("RECONCILIATION_FAILED")
    elif not run_id:
        current = _empty_current("UNKNOWN")
    round_value = _round(data, indexes, baseline, round_manifest, run_id, current["status"] == "OK", warnings)
    errors.extend(round_value["errors"])
    if errors:
        status = "RECONCILIATION_FAILED"
        if any(error.get("context") == "report" for error in errors):
            round_value = _empty_round("RECONCILIATION_FAILED", "After-report has conflicting or invalid records")
    else:
        status = "OK" if current["status"] == "OK" else "UNKNOWN"
    return {"schema_version": "1.0", "run_id": run_id, "status": status, "current": current,
            "round": round_value, "errors": errors, "warnings": warnings, "definitions": definitions}
