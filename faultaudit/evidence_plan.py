"""Evidence-first routing and explicitly confirmed event/evidence registrations.

Building a plan only reads the supplied Store. It neither searches a website nor
infers event groups. Task progress is excluded from stable routing identities.
"""
from __future__ import annotations

from .store import AuditError, Store, canonical_url, digest, now

POLICY_VERSION = "evidence-first-0.1.6"
ORIGINAL_KINDS = {"ORIGINAL_WEEKLY", "ORIGINAL_OBP", "SOURCE_WEEKLY_REPORT", "SOURCE_OBP"}
DISCOVERY_KINDS = {"SEARCH_DISCOVERED", "LINK_DISCOVERED", "OPEN_CODE_SEARCH", "AGENT_DISCOVERY", "HUMAN_ADDED"}
UNREADABLE = {"AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "TIMEOUT", "PARSE_FAILED", "UNSUPPORTED", "NETWORK_BLOCKED"}
IDENTITY_COLUMNS = {"序号", "统一id", "case_id", "external_id", "source_id", "来源", "source", "source_file",
                    "source_sheet", "source_row", "优先级组", "优先级", "priority", "source_priority", "wiki", "dts",
                    "pr", "github", "gitcode", "codehub", "url", "证据来源", "证据判断", "证据强度", "库覆盖（98条）"}


def _url(value: str | None) -> str | None:
    try:
        return canonical_url(value) if value else None
    except (ValueError, TypeError):
        return None


def source_relation(case: dict, ref: dict) -> dict:
    """Prove only that a reference came from an original source, not its cause."""
    trace = {"case_id": case.get("case_id"), "ref_id": ref.get("ref_id"),
             "source_file": case.get("source_file"), "source_sha256": case.get("source_sha256"),
             "sheet": case.get("sheet"), "row": case.get("row"), "reference_location": ref.get("location"),
             "origin": ref.get("origin"), "discovered_by": ref.get("discovered_by")}
    locations = case.get("cell_locations") or {}
    expected_locations = {f"{case.get('sheet')}!{location} (row {case.get('row')})" for location in locations.values()}
    complete_trace = (bool(case.get("source_file")) and bool(case.get("source_sha256"))
                      and bool(case.get("sheet")) and isinstance(case.get("row"), int) and case["row"] >= 1
                      and ref.get("location") in expected_locations)
    linked = (case.get("source_kind") in ORIGINAL_KINDS and ref.get("origin") == case.get("source_kind")
              and ref.get("case_id") == case.get("case_id") and ref.get("discovered_by") == "importer" and complete_trace)
    return {"relation": "SOURCE_LINKED" if linked else "PROVENANCE_PENDING", "trace": trace,
            "reason": "Original-source reference with file/row/cell trace" if linked else "Original-source provenance has not been restored"}


def semantic_input(case: dict) -> dict:
    """Exclude source identities while retaining all technical raw fields.

    Event/incident identifiers intentionally remain. A confirmed event group does
    not authorize reuse across different root causes, descriptions or settings.
    """
    raw = {key: value for key, value in (case.get("raw") or {}).items()
           if key.strip().casefold() not in IDENTITY_COLUMNS}
    return {"raw": raw, **{key: case.get(key, "") for key in
            ("description", "customer_model", "operator_raw", "root_cause_raw", "root_cause_origin")}}


def semantic_input_hash(case: dict) -> str:
    return digest(semantic_input(case))


def _confirmation(user_confirmed: bool, confirmed_by: str, reason: str) -> None:
    if user_confirmed is not True or not isinstance(confirmed_by, str) or not confirmed_by.strip() or not isinstance(reason, str) or not reason.strip():
        raise AuditError("Explicit user confirmation, confirmed_by and reason are required")


def register_event_group(store: Store, run_id: str, *, case_ids: list[str], user_confirmed: bool,
                         confirmed_by: str, reason: str, group_id: str | None = None) -> dict:
    _confirmation(user_confirmed, confirmed_by, reason)
    if not isinstance(case_ids, list) or any(not isinstance(value, str) or not value.strip() for value in case_ids):
        raise AuditError("Event group case_ids must be nonempty case identities")
    members = sorted(set(case_ids))
    if len(members) < 2:
        raise AuditError("An event group requires at least two distinct original case IDs")
    known = {case["case_id"] for case in store.records(run_id, "cases")}
    if set(members) - known:
        raise AuditError("Event group includes a case outside this run")
    group_id = group_id or "group-" + digest(members)[:24]
    if not isinstance(group_id, str) or not group_id.strip():
        raise AuditError("group_id must be nonempty")
    for existing in store.records(run_id, "event_groups"):
        if existing["group_id"] == group_id:
            if existing["case_ids"] != members:
                raise AuditError("Group identity already has different immutable members")
            return existing
        if set(existing["case_ids"]) & set(members):
            raise AuditError("Overlapping event groups require an explicit reconciliation; groups are not transitively merged")
    record = {"group_id": group_id, "case_ids": members, "user_confirmed": True,
              "confirmed_by": confirmed_by.strip(), "reason": reason.strip(), "registered_at": now()}
    store.put(run_id, "event_groups", group_id, record)
    store.event(run_id, "event_group_registered", record)
    return record


def register_evidence_association(store: Store, run_id: str, *, case_id: str, user_confirmed: bool,
                                  confirmed_by: str, reason: str, ref_id: str | None = None,
                                  snapshot_id: str | None = None, scope: str = "FULL_SNAPSHOT",
                                  applicable_issue_ids: list[str] | None = None) -> dict:
    _confirmation(user_confirmed, confirmed_by, reason)
    if not store.get(run_id, "cases", case_id):
        raise AuditError("Evidence association case is outside this run")
    if not ref_id and not snapshot_id:
        raise AuditError("Evidence association must identify a reference or a captured snapshot")
    ref = store.get(run_id, "references", ref_id) if ref_id else None
    snapshot = store.get(run_id, "snapshots", snapshot_id) if snapshot_id else None
    if ref_id and (not ref or ref["case_id"] != case_id):
        raise AuditError("Evidence association reference must belong to this original case")
    if snapshot_id and not snapshot:
        raise AuditError("Evidence association snapshot is outside this run")
    if ref and snapshot and _url(ref.get("url")) != _url(snapshot.get("url")):
        raise AuditError("Reference and snapshot identify different resources; register the actual evidence reference")
    if applicable_issue_ids is not None and (not isinstance(applicable_issue_ids, list) or any(
            not isinstance(value, str) or not value.strip() for value in applicable_issue_ids)):
        raise AuditError("Applicable issue IDs must be nonempty strings")
    issue_ids = sorted(set(applicable_issue_ids or []))
    if scope not in {"FULL_SNAPSHOT", "ISSUES"} or (scope == "ISSUES" and not issue_ids):
        raise AuditError("Association scope must be FULL_SNAPSHOT or ISSUES with explicit issue IDs")
    scope = "ISSUES" if issue_ids else scope
    identity = {"case_id": case_id, "ref_id": ref_id, "snapshot_id": snapshot_id,
                "scope": scope, "applicable_issue_ids": issue_ids, "user_confirmed": True,
                "confirmed_by": confirmed_by.strip(), "reason": reason.strip()}
    association_id = "association-" + digest(identity)[:24]
    existing = store.get(run_id, "evidence_associations", association_id)
    if existing:
        return existing
    record = {"association_id": association_id, **identity, "registered_at": now()}
    store.put(run_id, "evidence_associations", association_id, record)
    store.event(run_id, "evidence_association_registered", record)
    return record


def _source_record(case: dict) -> dict:
    return {key: case.get(key) for key in ("case_id", "external_id", "source_file", "source_sha256", "sheet", "row", "cell_locations")}


def _conflicting(judgment: dict) -> bool:
    return (judgment.get("review_status") != "REJECT" and
            (judgment.get("processing_status") == "EXCEPTION" or judgment.get("support_level") == "CONFLICT" or bool(judgment.get("conflicting_dimensions"))
             or "CONTRADICTED" in (judgment.get("claim_support") or {}).values()
             or any(fact.get("relation") == "CONFLICT" for fact in judgment.get("fact_comparisons", []))))


def _applies(judgment: dict, case_id: str) -> bool:
    return judgment.get("case_id") == case_id or case_id in judgment.get("member_case_ids", [])


def _search_decision(case: dict, snapshot: dict, judgment: dict, cases: dict) -> str:
    from .gates import judgment_semantic_errors, processing_decision
    original = cases.get(judgment.get("case_id"), case)
    if semantic_input_hash(original) != semantic_input_hash(case):
        return "PENDING"
    if judgment_semantic_errors(original, snapshot, judgment):
        return "EXCEPTION"
    return processing_decision(original, snapshot, judgment, "SEARCH_CANDIDATE")["processing_status"]


def _search_usable(case: dict, snapshot: dict, judgments: list[dict], cases: dict) -> bool:
    return any(_applies(judgment, case["case_id"]) and judgment.get("snapshot_id") == snapshot["snapshot_id"]
               and judgment.get("review_status") != "REJECT"
               and judgment.get("case_attribution") != "MISMATCH" and judgment.get("event_relation") != "DIFFERENT_EVENT"
               and _search_decision(case, snapshot, judgment, cases) == "AUTO_PROCESSED" for judgment in judgments)


def _readable(option: dict, active: dict) -> bool:
    snapshot = option["snapshot"]
    return bool(snapshot and snapshot["snapshot_id"] in active and snapshot.get("text", "").strip()
                and snapshot.get("status") in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"})


def _rank(option: dict, active: dict):
    priority = {"SOURCE_LINKED": 0, "USER_CONFIRMED": 1, "SEARCH_CANDIDATE": 2, "PROVENANCE_PENDING": 3}
    return (not _readable(option, active), priority[option["relation"]], (option["ref"] or {}).get("location", ""),
            (option["ref"] or {}).get("ref_id", ""), (option["snapshot"] or {}).get("snapshot_id", ""))


def _candidate(ref: dict | None, snapshot: dict | None, relation: str, provenance: dict,
               association: dict | None = None) -> dict:
    return {"ref": ref, "snapshot": snapshot, "relation": relation, "provenance": provenance,
            "association_id": association.get("association_id") if association else None,
            "issue_scope": {"scope": association.get("scope", "FULL_SNAPSHOT") if association else "FULL_SNAPSHOT",
                            "applicable_issue_ids": association.get("applicable_issue_ids", []) if association else []}}


def build_evidence_plan(store: Store, run_id: str, *, judgments: list[dict] | None = None) -> dict:
    """Plan one sufficient evidence path per case, preserving known conflicts.

    The caller may provide current judgments. This function deliberately never
    calls pipeline.current_judgments, avoiding planning/currentness recursion.
    """
    cases = {case["case_id"]: case for case in store.records(run_id, "cases")}
    refs = {ref["ref_id"]: ref for ref in store.records(run_id, "references")}
    snapshots = {snapshot["snapshot_id"]: snapshot for snapshot in store.records(run_id, "snapshots")}
    active = {snapshot["snapshot_id"]: snapshot for snapshot in store.active_snapshots(run_id)}
    by_url = {_url(snapshot["url"]): snapshot for snapshot in active.values()}
    associations = [record for record in store.records(run_id, "evidence_associations") if record.get("user_confirmed") is True]
    groups = [group for group in store.records(run_id, "event_groups") if group.get("user_confirmed") is True]
    group_by_case = {case_id: group for group in groups for case_id in group["case_ids"]}
    judgments = [j for j in judgments or [] if not j.get("is_stale", False)]
    candidates = {}
    for case_id, case in cases.items():
        options = []
        case_associations = [association for association in associations if association["case_id"] == case_id]
        associated_refs = {association.get("ref_id") for association in case_associations}
        for ref in refs.values():
            if ref["case_id"] != case_id or ref["ref_id"] in associated_refs:
                continue
            relation = source_relation(case, ref)
            if relation["relation"] != "SOURCE_LINKED" and ref.get("origin") in DISCOVERY_KINDS:
                relation = {"relation": "SEARCH_CANDIDATE", "trace": {"case_id": case_id, "ref_id": ref["ref_id"],
                    "origin": ref.get("origin"), "location": ref.get("location"), "discovery_query": ref.get("discovery_query", "")}}
            options.append(_candidate(ref, by_url.get(_url(ref.get("url"))), relation["relation"], relation))
        for association in case_associations:
            ref = refs.get(association.get("ref_id"))
            snapshot = snapshots.get(association.get("snapshot_id")) if association.get("snapshot_id") else by_url.get(_url((ref or {}).get("url")))
            options.append(_candidate(ref, snapshot, "USER_CONFIRMED", {"association": association}, association))
        candidates[case_id] = options
    # A user-confirmed event group can borrow an original/confirmed member source.
    # The provenance continues to identify the member who actually supplied it.
    for case_id, options in candidates.items():
        group = group_by_case.get(case_id)
        own_trusted = any(option["relation"] in {"SOURCE_LINKED", "USER_CONFIRMED"} for option in options)
        if group and not own_trusted:
            for member in group["case_ids"]:
                if member == case_id:
                    continue
                for option in candidates.get(member, []):
                    if option["relation"] not in {"SOURCE_LINKED", "USER_CONFIRMED"} or option["provenance"].get("inherited_from_case_id"):
                        continue
                    options.append({**option, "relation": "USER_CONFIRMED", "provenance": {
                        "group_id": group["group_id"], "inherited_from_case_id": member, "source": option["provenance"]}})
    plans, work = [], {}
    for case_id, case in sorted(cases.items()):
        group = group_by_case.get(case_id)
        all_options = candidates[case_id]
        excluded = [j for j in judgments if _applies(j, case_id) and (j.get("case_attribution") == "MISMATCH" or j.get("event_relation") == "DIFFERENT_EVENT")
                    and j.get("review_status") != "REJECT" and j.get("snapshot_id") in active
                    and _search_decision(case, active[j["snapshot_id"]], j, cases) == "AUTO_PROCESSED"]
        excluded_ids = {j["snapshot_id"] for j in excluded}
        options = [option for option in all_options if not (option["relation"] == "SEARCH_CANDIDATE" and option["snapshot"]
                   and option["snapshot"]["snapshot_id"] in excluded_ids)]
        trusted_snapshot_ids = {option["snapshot"]["snapshot_id"] for option in options if option["snapshot"]
                                and option["relation"] in {"SOURCE_LINKED", "USER_CONFIRMED"}}
        conflicts = [j for j in judgments if _applies(j, case_id) and (_conflicting(j) or
                     (j.get("review_status") != "REJECT" and j.get("snapshot_id") in trusted_snapshot_ids and
                      (j.get("case_attribution") == "MISMATCH" or j.get("event_relation") == "DIFFERENT_EVENT")))]
        trusted = [option for option in options if option["relation"] in {"SOURCE_LINKED", "USER_CONFIRMED"}]
        search = [option for option in options if option["relation"] == "SEARCH_CANDIDATE"]
        usable = [option for option in search if option["snapshot"] and _search_usable(case, option["snapshot"], judgments, cases)]
        selected = []
        issues, required, optional = [], [], []
        path, relation, stop_reason = "SEARCH_REQUIRED", "PROVENANCE_PENDING", "NO_EVIDENCE_SEARCH_REQUIRED"
        if conflicts:
            conflict_ids = {j.get("snapshot_id") for j in conflicts}
            selected = [option for option in options if option["snapshot"] and option["snapshot"]["snapshot_id"] in conflict_ids]
            read_trusted = sorted((option for option in trusted if _readable(option, active)), key=lambda option: _rank(option, active))
            if read_trusted and read_trusted[0] not in selected:
                selected.append(read_trusted[0])
            path, stop_reason = "EXCEPTION", "KNOWN_CONFLICT_REQUIRES_RECONCILIATION"
            relation = "SOURCE_LINKED" if any(option["relation"] == "SOURCE_LINKED" for option in options) else "PROVENANCE_PENDING"
            required.append({"action": "RECONCILE_CONFLICT", "judgment_ids": sorted(j.get("judgment_id", "") for j in conflicts)})
            issues.append({"code": "KNOWN_CONFLICT", "judgment_ids": sorted(j.get("judgment_id", "") for j in conflicts)})
        elif trusted or usable or search:
            pool = trusted or usable or search
            chosen = sorted(pool, key=lambda option: _rank(option, active))[0]
            selected = [chosen]
            relation = chosen["relation"]
            snapshot, ref = chosen["snapshot"], chosen["ref"]
            if snapshot and snapshot["snapshot_id"] not in active:
                path, stop_reason = "EXCEPTION", "CONFIRMED_SNAPSHOT_VERSION_IS_STALE"
                required.append({"action": "RECONFIRM_SNAPSHOT", "snapshot_id": snapshot["snapshot_id"]})
            elif snapshot and snapshot.get("status") in UNREADABLE:
                path, stop_reason = "EXCEPTION", "FETCH_FAILURE_NOT_NO_EVIDENCE"
                required.append({"action": "RESOLVE_CAPTURE_FAILURE", "snapshot_id": snapshot["snapshot_id"], "status": snapshot["status"]})
            elif snapshot and snapshot.get("text", "").strip() and snapshot.get("status") in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"}:
                if snapshot.get("status") != "COMPLETE":
                    optional.append({"action": "COMPLETE_CAPTURE", "snapshot_id": snapshot["snapshot_id"], "blocking": False})
                path = relation if relation != "SEARCH_CANDIDATE" else "VERIFIED_SEARCH" if chosen in usable else "SEARCH_CANDIDATE"
                stop_reason = "USABLE_SEARCH_EVIDENCE_FOUND" if path == "VERIFIED_SEARCH" else "PARTIAL_CONTENT_USABLE_NO_SEARCH" if optional else "EVIDENCE_AVAILABLE_NO_SEARCH"
                required.append({"action": "EXTRACT_FACTS", "snapshot_id": snapshot["snapshot_id"], "issue_scope": chosen["issue_scope"]})
            elif ref and ref.get("status") == "PARSED" and _url(ref.get("url")):
                path = "FETCH_ORIGINAL" if relation == "SOURCE_LINKED" else "FETCH_EXISTING"
                stop_reason = "EXISTING_REFERENCE_NEEDS_FETCH_NO_SEARCH"
                required.append({"action": "FETCH", "ref_id": ref["ref_id"], "url": ref["url"]})
            else:
                path, stop_reason = "EXCEPTION", "REFERENCE_REQUIRES_RESTORATION"
                required.append({"action": "RESTORE_REFERENCE", "ref_id": (ref or {}).get("ref_id")})
        elif options:
            selected = list(options)
            path, stop_reason = "EXCEPTION", "REFERENCE_PROVENANCE_PENDING"
            required.append({"action": "RESTORE_PROVENANCE", "ref_ids": sorted((option["ref"] or {}).get("ref_id", "") for option in options)})
        else:
            if excluded:
                stop_reason = "EXISTING_CANDIDATES_EXCLUDED_NO_APPLICABLE_EVIDENCE"
            required.append({"action": "SEARCH", "case_id": case_id, "description": case.get("description", "")})
        selected_ref_ids = sorted({option["ref"]["ref_id"] for option in selected if option["ref"]})
        selected_snapshot_ids = sorted({option["snapshot"]["snapshot_id"] for option in selected if option["snapshot"]})
        scopes = sorted((option["issue_scope"] for option in selected), key=digest)
        routing = {"case_id": case_id, "group_id": group["group_id"] if group else None, "relation": relation,
                   "selected_ref_ids": selected_ref_ids, "selected_snapshot_ids": selected_snapshot_ids, "issue_scopes": scopes}
        plan = {**routing, "external_id": case.get("external_id", ""), "source_file": case.get("source_file"),
                "sheet": case.get("sheet"), "row": case.get("row"),
                "path": path, "routing_hash": digest(routing), "required_actions": required, "optional_actions": optional,
                "stop_reason": stop_reason, "issues": issues, "association_ids": sorted({option["association_id"] for option in selected if option["association_id"]}),
                "excluded_candidate_judgment_ids": sorted(j.get("judgment_id", "") for j in excluded),
                "provenance": [option["provenance"] for option in selected], "work_ids": []}
        for option in selected:
            snapshot = option["snapshot"]
            if not snapshot or snapshot["snapshot_id"] not in active or snapshot.get("status") not in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"} or not snapshot.get("text", "").strip():
                continue
            work_relation = "USER_CONFIRMED" if group and option["relation"] in {"SOURCE_LINKED", "USER_CONFIRMED"} else option["relation"]
            work_key = {"group_or_case_id": group["group_id"] if group else case_id, "snapshot_id": snapshot["snapshot_id"],
                        "issue_scope": option["issue_scope"], "input_hash": semantic_input_hash(case), "relation": work_relation}
            work_id = "work-" + digest(work_key)[:24]
            item = work.setdefault(work_id, {"work_id": work_id, **work_key, "group_id": group["group_id"] if group else None,
                "representative_case_id": case_id, "case_ids": [], "ref_ids": [], "snapshot_id": snapshot["snapshot_id"],
                "source_records": [], "member_relations": {}, "actions": ["EXTRACT_FACTS", "MATCH_CATALOG"]})
            if case_id not in item["case_ids"]:
                item["case_ids"].append(case_id)
                item["source_records"].append(_source_record(case))
            item["member_relations"][case_id] = option["relation"]
            item["ref_ids"] = sorted(set(item["ref_ids"]) | ({option["ref"]["ref_id"]} if option["ref"] else set()))
            if work_id not in plan["work_ids"]:
                plan["work_ids"].append(work_id)
        plans.append(plan)
    group_plans = [{**group, "input_variants": {case_id: semantic_input_hash(cases[case_id]) for case_id in group["case_ids"]},
                    "technical_input_divergence": len({semantic_input_hash(cases[case_id]) for case_id in group["case_ids"]}) > 1}
                   for group in groups]
    return {"schema_version": "1.0", "run_id": run_id, "policy_version": POLICY_VERSION,
            "plan_hash": digest({"policy_version": POLICY_VERSION, "routing": [plan["routing_hash"] for plan in plans]}),
            "cases": plans, "groups": group_plans, "work_items": sorted(work.values(), key=lambda item: item["work_id"])}
