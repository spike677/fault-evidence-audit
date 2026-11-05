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


def _record_case_ids(record: dict) -> set[str]:
    """A shared event result is one judgment involving every explicit member."""
    members = record.get("member_case_ids", [])
    result = {record["case_id"]}
    if isinstance(members, list):
        result.update(value for value in members if isinstance(value, str))
    return result


def _counts(judgments: list[dict]) -> dict:
    return {"judgment_count": len(judgments), "case_count": len(set().union(*(_record_case_ids(j) for j in judgments)))}


def _axes(judgments: list[dict]) -> dict:
    result = {}
    for axis in AXES:
        buckets = defaultdict(list)
        for judgment in judgments:
            buckets[judgment[axis]].append(judgment)
        result[axis] = {value: _counts(records) for value, records in sorted(buckets.items())}
    return result


def _required_result(record: dict, indexes: dict) -> bool:
    """Explicitly unused work is history; older reports default to required."""
    task = indexes["tasks"].get(record.get("task_id"), {})
    return record.get("required") is not False and task.get("required") is not False


def _processing(records: list[dict], *, mapping: bool = False) -> dict:
    buckets = {status: [] for status in ("AUTO_PROCESSED", "PENDING", "EXCEPTION", "LEGACY_REVIEW")}
    for record in records:
        status = record.get("processing_status")
        if status == "AUTO_PROCESSED" and record.get("review_required") is False and record.get("review_status") == "NOT_REQUIRED":
            buckets[status].append(record)
        elif status in {"PENDING", "EXCEPTION"}:
            buckets[status].append(record)
        elif status is None and record.get("review_status") not in {"ACCEPT", "REJECT"}:
            buckets["LEGACY_REVIEW"].append(record)
    if mapping:
        return {status: {"mapping_count": len(values), "case_count": len(set().union(*(_record_case_ids(v) for v in values)))}
                for status, values in buckets.items()}
    return {status: _counts(values) for status, values in buckets.items()}


def _selection_statistics(data: dict, current_snapshots: list[dict]) -> dict:
    result = {"selected_snapshot_count": None, "unused_reference_count": None, "required_reference_count": None,
              "event_group_count": None, "planned_work_count": None}
    plans = data.get("evidence_plans")
    if isinstance(plans, dict) and isinstance(plans.get("cases"), list):
        entries = plans["cases"]
        if any(not isinstance(value, dict) or any(not isinstance(value.get(key), list)
                or any(not isinstance(identity, str) or not identity.strip() for identity in value[key])
                for key in ("selected_ref_ids", "selected_snapshot_ids")) for value in entries):
            return result
        selected_sids = {identity for value in entries for identity in value.get("selected_snapshot_ids", [])}
        result["selected_snapshot_count"] = len(selected_sids & {s["snapshot_id"] for s in current_snapshots})
        references = data.get("references")
        if isinstance(references, list) and all(isinstance(ref, dict) and isinstance(ref.get("ref_id"), str) for ref in references):
            reference_ids = {ref["ref_id"] for ref in references}
            selected_refs = {identity for value in entries for identity in value.get("selected_ref_ids", [])}
            result["unused_reference_count"] = len(reference_ids - selected_refs)
            result["required_reference_count"] = len(reference_ids & selected_refs)
        work = plans.get("work_items")
        if isinstance(work, list) and all(isinstance(item, dict) and isinstance(item.get("work_id"), str) and item["work_id"].strip() for item in work):
            result["planned_work_count"] = len({item["work_id"] for item in work})
    groups = data.get("event_groups")
    if isinstance(groups, list) and all(isinstance(group, dict) and isinstance(group.get("group_id"), str) for group in groups):
        result["event_group_count"] = len({group["group_id"] for group in groups})
    return result


def _empty_current(status: str) -> dict:
    return {"status": status, "including_rejected": {"judgment_count": None, "case_count": None},
            "excluding_rejected": {"judgment_count": None, "case_count": None},
            "rejected": {"judgment_count": None, "case_count": None},
            "confirmed_accepted": {"judgment_count": None, "case_count": None},
            "snapshot_count": None, "mapping_count": None, "mapping_count_excluding_rejected": None,
            "classifications": None, "classifications_excluding_rejected": None,
            "processing": None, "mapping_processing": None, "auto_processed_count": None,
            "human_exception_count": None, "pending_human_exception_count": None, "agent_pending_count": None,
            "mapping_auto_processed_count": None, "mapping_human_exception_count": None,
            "mapping_agent_pending_count": None, "selected_snapshot_count": None,
            "unused_reference_count": None, "required_reference_count": None, "event_group_count": None,
            "planned_work_count": None, "current_work_count": None, "current_case_snapshot_pair_count": None}


def _current(indexes: dict, present: dict, errors: list, warnings: list, data: dict | None = None) -> dict:
    initial_errors = len(errors)
    required = ("cases", "snapshots", "judgments", "mappings", "tasks")
    unknown = not all(present[name] for name in required)
    current = {name: [] for name in ("snapshots", "judgments", "mappings")}
    for name, output in current.items():
        for identity, record in indexes[name].items():
            if name in {"judgments", "mappings"} and not _required_result(record, indexes):
                continue
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
                members = record.get("member_case_ids", [])
                if not isinstance(members, list) or any(not isinstance(value, str) or not value.strip() for value in members):
                    errors.append(_issue("INVALID_GROUP_MEMBERS", "Shared result member_case_ids must contain valid case IDs",
                                         collection=name, record_id=identity))
                elif present["cases"] and set(members) - set(indexes["cases"]):
                    errors.append(_issue("MISSING_GROUP_CASE", "Shared result references absent member cases",
                                         collection=name, record_id=identity, case_ids=sorted(set(members) - set(indexes["cases"]))))
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
                if record.get("processing_status") is not None and (record["processing_status"] not in {"AUTO_PROCESSED", "PENDING", "EXCEPTION"}
                        or not isinstance(record.get("review_required"), bool)):
                    unknown = True
                    warnings.append(_issue("CURRENT_PROCESSING_UNKNOWN", "Processing metadata is incomplete or invalid",
                                           collection=name, record_id=identity))
            output.append(record)
    work_results = defaultdict(list)
    for judgment in current["judgments"]:
        work_id = judgment.get("work_id")
        if isinstance(work_id, str) and work_id.strip():
            work_results[work_id].append(judgment["judgment_id"])
    for work_id, judgment_ids in work_results.items():
        if len(judgment_ids) > 1:
            errors.append(_issue("CURRENT_WORK_ID_CONFLICT", "One evidence work has multiple current judgment IDs; no result is silently selected",
                                 work_id=work_id, judgment_ids=sorted(judgment_ids)))
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
    processing = _processing(js)
    mapping_processing = _processing(current["mappings"], mapping=True)
    return {"status": "OK", "including_rejected": _counts(js), "excluding_rejected": _counts(non_rejected),
            "rejected": _counts([j for j in js if j["review_status"] == "REJECT"]),
            "confirmed_accepted": _counts(confirmed), "snapshot_count": len(current["snapshots"]),
            "mapping_count": len(current["mappings"]),
            "mapping_count_excluding_rejected": sum(m["review_status"] != "REJECT" for m in current["mappings"]),
            "classifications": _axes(js), "classifications_excluding_rejected": _axes(non_rejected),
            "processing": processing, "mapping_processing": mapping_processing,
            "auto_processed_count": processing["AUTO_PROCESSED"]["judgment_count"],
            "human_exception_count": processing["EXCEPTION"]["judgment_count"],
            "pending_human_exception_count": sum(j.get("processing_status") == "EXCEPTION" and j.get("review_required") is True
                                                 and j["review_status"] not in {"ACCEPT", "REJECT"} for j in js),
            "agent_pending_count": processing["PENDING"]["judgment_count"],
            "mapping_auto_processed_count": mapping_processing["AUTO_PROCESSED"]["mapping_count"],
            "mapping_human_exception_count": mapping_processing["EXCEPTION"]["mapping_count"],
            "mapping_agent_pending_count": mapping_processing["PENDING"]["mapping_count"],
            "current_work_count": len(work_results) if len(work_results) == len(js) else None,
            "current_case_snapshot_pair_count": len({(cid, j["snapshot_id"]) for j in js for cid in _record_case_ids(j)}),
            **_selection_statistics(data or {}, current["snapshots"])}


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
            if record.get("work_id"):
                context = payload.get("processing_context", {})
                if (not isinstance(context, dict) or context.get("work_id") != record["work_id"]
                        or any(value.get("work_id", record["work_id"]) != record["work_id"] for value in (model_task, response))):
                    errors.append(_issue("ROUND_WORK_SCOPE_CONFLICT", "Accepted model request does not identify this exact work/issue scope",
                                         pipeline_task_id=task_id, work_id=record["work_id"]))
                    continue
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
            mutable = {"is_stale", "review_status", "required"}
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
    output.update(new_judgment_count=len(new_js), new_case_count=_counts(new_js)["case_count"],
                  new_snapshot_count=len(sids or set()), new_mapping_count=len(mids or set()))
    if all(isinstance(j.get("review_status"), str) for j in new_js):
        output["new_judgment_count_excluding_rejected"] = sum(j["review_status"] != "REJECT" for j in new_js)
    if current_ok:
        current_js = [j for j in new_js if j.get("is_stale") is False and _required_result(j, indexes)]
        output.update(current_new_judgment_count=len(current_js), current_new_case_count=_counts(current_js)["case_count"],
                      current_new_snapshot_count=sum(indexes["snapshots"][identity]["is_stale"] is False for identity in sids or set()),
                      current_new_mapping_count=sum(indexes["mappings"][identity].get("is_stale") is False
                                                    and _required_result(indexes["mappings"][identity], indexes) for identity in mids or set()),
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
        "association_identity": "Current validate planned_associations/judged_associations aliases count unique work_id including issue scope; older reports may declare legacy case/snapshot pairs. The report validation association_identity and ID lists define its scope",
        "snapshot_identity": "unique snapshot_id; an ingested snapshot does not require a completed model task",
        "event_group_identity": "Shared explicit event work counts once by judgment_id; involved case counts include unique case_id and member_case_ids, without merging original case records",
        "mapping_identity": "mapping.task_id", "current_scope": "Current as of this input report's exported is_stale flags and task states, not a fresh database/policy query; required is not false, is_stale=false and SUCCEEDED, with REJECT counted separately; legacy reports default to required",
        "classifications_scope": "Current non-stale judgments including REJECT; excluding-REJECT axes are separately provided",
        "classifications_overlap": True,
        "classification_warning": "Axes overlap. Case counts and counts across different axes must not be summed or substituted for judgment counts.",
        "confirmed_accepted": "COMPLETE snapshot + CONFIRMED + SAME_EVENT + DIRECT + human review ACCEPT, without conflicting dimensions or CONTRADICTED claims",
        "new_case_count": "Unique cases involved in new judgments; not newly imported cases",
        "round_new_scope": "All IDs added after baseline, including results made stale or unused later in the round",
        "snapshot_count": "All active ingested snapshots, including unused evidence; selected_snapshot_count is separate",
        "selection_counts": "Derived from evidence_plans selected IDs; missing plan metadata is unknown rather than zero",
        "work_counts": "planned_work_count deduplicates evidence_plans.work_items by work_id; current_work_count counts necessary current judgment work IDs, unknown when legacy records lack work_id. Different issue scopes of one case/snapshot remain separate work; multiple current judgments for the same work fail reconciliation",
        "current_case_snapshot_pair_count": "Unique (member case_id, snapshot_id) pairs; multiple issue works can share one pair, so pair counts must not replace work/judgment counts",
        "auto_processed_count": "Required current judgments with AUTO_PROCESSED, review_required=false and review_status=NOT_REQUIRED; no human ACCEPT is synthesized",
        "human_exception_count": "Required current EXCEPTION judgment records, including already reviewed exceptions; pending_human_exception_count excludes human ACCEPT/REJECT",
        "agent_pending_count": "Required current PENDING judgment records for agent completion; not human exceptions",
        "mapping_processing_counts": "Mapping records counted separately from judgment records; case counts are not merged across explicit event groups"}
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
    current = _current(indexes, present, errors, warnings, data)
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
