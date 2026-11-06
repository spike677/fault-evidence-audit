"""Evidence-first routing and explicitly confirmed event/evidence registrations.

Building a plan only reads the supplied Store. It neither searches a website nor
infers event groups. Task progress is excluded from stable routing identities.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from .importers import is_empty_link_value
from .resource_identity import resource_key, same_resource, snapshot_index
from .store import AuditError, Store, canonical_url, digest, now

POLICY_VERSION = "evidence-first-0.1.8"
SEARCH_SOURCES = {"WIKI", "DTS", "GITCODE", "GITHUB", "GITEE", "CODEHUB"}
DEFAULT_SEARCH_POLICY = {"min_usable_evidence": 1, "required_sources": [], "required_any_sources": []}
ORIGINAL_KINDS = {"ORIGINAL_WEEKLY", "ORIGINAL_OBP", "SOURCE_WEEKLY_REPORT", "SOURCE_OBP"}
TABLE_GRADES = {"SOURCE_CELL_LINKED", "LEGACY_TABLE_LINKED"}
GRADE_PRIORITY = {"SOURCE_CELL_LINKED": 0, "LEGACY_TABLE_LINKED": 1, "SEARCH_DISCOVERED": 2, "PROVENANCE_PENDING": 3}
DISCOVERY_KINDS = {"SEARCH_DISCOVERED", "LINK_DISCOVERED", "OPEN_CODE_SEARCH", "AGENT_DISCOVERY", "HUMAN_ADDED"}
UNREADABLE = {"AUTH_REQUIRED", "FORBIDDEN", "NOT_FOUND", "TIMEOUT", "PARSE_FAILED", "UNSUPPORTED", "NETWORK_BLOCKED"}
IDENTITY_COLUMNS = {"序号", "统一id", "case_id", "external_id", "source_id", "来源", "source", "source_file",
                    "source_sheet", "source_row", "优先级组", "优先级", "priority", "source_priority", "wiki", "dts",
                    "pr", "github", "gitcode", "gitee", "codehub", "url", "证据来源", "证据判断", "证据强度", "库覆盖（98条）"}


def _url(value: str | None) -> str | None:
    try:
        return canonical_url(value) if value else None
    except (ValueError, TypeError):
        return None


def _resource(value: str | None) -> str | None:
    url = _url(value)
    return resource_key(url) if url else None


def _trigger_source_relations(store: Store, run_id: str) -> dict:
    """Use mode-entry source checks only in taxonomy initialization runs.

    A mode definition is not an incident. These checks route source material
    without manufacturing an event judgment or a human confirmation.
    """
    config = store.get(run_id, "xlsx_workflow", "config") or {}
    if config.get("purpose") != "TRIGGER_INIT":
        return {}
    from .trigger_workflow import source_relations

    return source_relations(store, run_id)


def normalize_search_policy(policy: dict) -> dict:
    """Validate a complete, small search stopping policy, without coercion."""
    if not isinstance(policy, dict) or set(policy) - set(DEFAULT_SEARCH_POLICY):
        raise AuditError("Search policy has unsupported fields")
    minimum = policy.get("min_usable_evidence", 1)
    if type(minimum) is not int or minimum < 1:
        raise AuditError("min_usable_evidence must be a positive integer")
    result = {"min_usable_evidence": minimum}
    for field in ("required_sources", "required_any_sources"):
        values = policy.get(field, [])
        if not isinstance(values, list) or any(not isinstance(value, str) or value not in SEARCH_SOURCES for value in values):
            raise AuditError(f"{field} must contain only {', '.join(sorted(SEARCH_SOURCES))}")
        result[field] = sorted(set(values))
    return result


def register_search_policy(store: Store, run_id: str, policy: dict, case_id: str | None = None) -> dict:
    """Append a run policy or full case override; previous revisions remain."""
    store.run_info(run_id)
    if case_id is not None and not store.get(run_id, "cases", case_id):
        raise AuditError("Search policy case is outside this run")
    normalized = normalize_search_policy(policy)
    previous = [record for record in store.records(run_id, "search_policies") if record.get("case_id") == case_id]
    latest = max(previous, key=lambda record: record["revision"], default=None)
    if latest and latest["policy"] == normalized:
        return latest
    revision = max((record["revision"] for record in previous), default=0) + 1
    identity = {"case_id": case_id, "revision": revision, "policy": normalized}
    record = {"policy_record_id": "search-policy-" + digest(identity)[:24], **identity,
              "policy_hash": digest(normalized), "registered_at": now()}
    store.put(run_id, "search_policies", record["policy_record_id"], record)
    store.event(run_id, "search_policy_registered", record)
    return record


def get_search_policy(store: Store, run_id: str, case_id: str | None = None) -> dict:
    records = store.records(run_id, "search_policies")
    own = [record for record in records if case_id is not None and record.get("case_id") == case_id]
    run = [record for record in records if record.get("case_id") is None]
    record = max(own or run, key=lambda item: item["revision"], default=None)
    if record:
        policy = normalize_search_policy(record["policy"])
        return {"policy": policy, "policy_hash": digest(policy), "policy_record_id": record["policy_record_id"],
                "scope": "CASE" if own else "RUN"}
    policy = normalize_search_policy({})
    return {"policy": policy, "policy_hash": digest(policy), "policy_record_id": None, "scope": "DEFAULT"}


def resource_kind(ref: dict | None = None, snapshot: dict | None = None, case: dict | None = None) -> str:
    """Classify navigation resources, never fault identity or root-cause truth."""
    ref, snapshot = ref or {}, snapshot or {}
    for value in (ref.get("url"), snapshot.get("url")):
        if not _url(value):
            continue
        parsed = urlsplit(value)
        host, path = (parsed.hostname or "").casefold(), parsed.path.casefold()
        if host == "github.com" or host.endswith(".github.com"):
            return "GITHUB"
        if host == "gitcode.com" or host.endswith(".gitcode.com"):
            return "GITCODE"
        if host == "gitee.com" or host.endswith(".gitee.com"):
            return "GITEE"
        if host.startswith(("codehub.", "codehub-")) or "codehub" in host.split("."):
            return "CODEHUB"
        if host.startswith("wiki.") or re.search(r"/(?:wiki|wikis)(?:/|$)", path):
            return "WIKI"
        if host.startswith(("dts.", "dts-")) or re.search(r"/(?:dts|dtsportal)(?:/|$)", path):
            return "DTS"
    # Only an exact imported source cell supplies a header hint. The word wiki
    # in an arbitrary discovery location is not evidence of the resource type.
    if case:
        for header, location in (case.get("cell_locations") or {}).items():
            if ref.get("location") != f"{case.get('sheet')}!{location} (row {case.get('row')})":
                continue
            key = header.strip().casefold()
            for word, kind in (("wiki", "WIKI"), ("dts", "DTS"), ("gitcode", "GITCODE"),
                               ("github", "GITHUB"), ("gitee", "GITEE"), ("codehub", "CODEHUB")):
                if word in key:
                    if kind in {"GITCODE", "GITHUB", "GITEE"} and (ref.get("url") or snapshot.get("url")):
                        continue
                    return kind
    return {"WIKI": "WIKI", "DTS": "DTS"}.get(snapshot.get("artifact_type"), "UNKNOWN")


def source_relation(case: dict, ref: dict) -> dict:
    """Keep original-cell, legacy-table and search provenance distinct.

    A link supplied by a legacy table is usable material, while its historical
    root-cause attribution remains unverified. Confirmation never changes origin.
    """
    trace = {"case_id": case.get("case_id"), "ref_id": ref.get("ref_id"),
             "source_file": case.get("source_file"), "source_sha256": case.get("source_sha256"),
             "sheet": case.get("sheet"), "row": case.get("row"), "reference_location": ref.get("location"),
             "origin": ref.get("origin"), "discovered_by": ref.get("discovered_by")}
    locations = case.get("cell_locations") or {}
    expected_locations = {f"{case.get('sheet')}!{location} (row {case.get('row')})" for location in locations.values()}
    complete_trace = (bool(case.get("source_file")) and bool(case.get("source_sha256"))
                      and bool(case.get("sheet")) and isinstance(case.get("row"), int) and case["row"] >= 1
                      and ref.get("location") in expected_locations)
    same_case = ref.get("case_id") == case.get("case_id")
    imported = same_case and ref.get("discovered_by") == "importer" and complete_trace
    origin = ref.get("origin", "UNKNOWN")
    if origin in DISCOVERY_KINDS or origin in {"SEARCH_CANDIDATE", "SEARCH_DISCOVERED"}:
        grade = "SEARCH_DISCOVERED"
        reason = "Discovered evidence; applicability must be established from its content"
    elif imported and case.get("source_kind") in ORIGINAL_KINDS and origin in ORIGINAL_KINDS:
        grade = "SOURCE_CELL_LINKED"
        reason = "Original-source reference with file/row/cell trace"
    elif imported and (origin == case.get("source_kind") or origin in {"LEGACY_TABLE", "SOURCE_EXCEL", "SOURCE_LINKED"}):
        grade = "LEGACY_TABLE_LINKED"
        reason = "Reference was supplied by the legacy table; original weekly provenance and root cause remain distinct"
    else:
        grade = "PROVENANCE_PENDING"
        reason = "An agent must recover the reference origin or report the remaining provenance gap"
    legacy = "SOURCE_LINKED" if grade == "SOURCE_CELL_LINKED" else "SEARCH_CANDIDATE" if grade == "SEARCH_DISCOVERED" else "PROVENANCE_PENDING"
    return {"relation": grade, "source_grade": grade, "legacy_relation": legacy, "trace": trace,
            "trace_complete": bool(complete_trace and same_case),
            "source_recovery_required": grade == "PROVENANCE_PENDING", "reason": reason}


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
    if ref and snapshot and not same_resource(ref.get("url"), snapshot.get("url")):
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
    return processing_decision(original, snapshot, judgment, "SEARCH_DISCOVERED")["processing_status"]


def _search_usable(case: dict, snapshot: dict, judgments: list[dict], cases: dict) -> bool:
    return any(_applies(judgment, case["case_id"]) and judgment.get("snapshot_id") == snapshot["snapshot_id"]
               and judgment.get("review_status") != "REJECT"
               and judgment.get("case_attribution") != "MISMATCH" and judgment.get("event_relation") != "DIFFERENT_EVENT"
               and _search_decision(case, snapshot, judgment, cases) == "AUTO_PROCESSED" for judgment in judgments)


def _search_insufficient(case: dict, snapshot: dict, judgment: dict, cases: dict) -> bool:
    """A completed, weak comparison is not an unfinished model task forever."""
    from .gates import FACT_CATEGORIES, SELF_CHECK_FIELDS
    check, facts = judgment.get("self_check") or {}, judgment.get("fact_comparisons") or []
    return (judgment.get("model_mode") != "mock" and judgment.get("review_status") != "REJECT"
            and snapshot.get("status") in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"} and bool(snapshot.get("text", "").strip())
            and {fact.get("category") for fact in facts} == FACT_CATEGORIES
            and check.get("attempt") == 1 and check.get("passed") is True and not check.get("issues")
            and all(check.get(field) is True for field in SELF_CHECK_FIELDS)
            and bool((judgment.get("applicable_issue") or {}).get("evidence"))
            and any(fact.get("source_field") and fact.get("source_quote") and fact.get("source_cell") and fact.get("evidence") for fact in facts)
            and _search_decision(case, snapshot, judgment, cases) == "PENDING")


def _readable(option: dict, active: dict) -> bool:
    from .capture_quality import capture_quality
    snapshot = option["snapshot"]
    return bool(snapshot and snapshot["snapshot_id"] in active and snapshot.get("text", "").strip()
                and snapshot.get("status") in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"}
                and capture_quality(snapshot)["usable_body"])


def _rank(option: dict, active: dict):
    return (not _readable(option, active), GRADE_PRIORITY[option["relation"]], (option["ref"] or {}).get("location", ""),
            (option["ref"] or {}).get("ref_id", ""), (option["snapshot"] or {}).get("snapshot_id", ""))


def _search_rank(option: dict):
    # Keep the first candidate pending until resolved or positively excluded;
    # a later readable result must not hide an earlier authentication failure.
    ref = option["ref"] or {}
    return (ref.get("discovered_at") or "", ref.get("location", ""), ref.get("ref_id", ""),
            (option["snapshot"] or {}).get("snapshot_id", ""))


def _goal(policy: dict, usable: list[dict], kind) -> dict:
    unique = {option["snapshot"]["snapshot_id"]: option for option in usable}
    sources = sorted({kind(option) for option in unique.values()} - {"UNKNOWN"})
    missing = sorted(set(policy["required_sources"]) - set(sources))
    missing_any = policy["required_any_sources"] if policy["required_any_sources"] and not set(policy["required_any_sources"]) & set(sources) else []
    return {"usable_evidence_count": len(unique), "usable_sources": sources,
            "missing_sources": missing, "missing_any_sources": missing_any,
            "satisfied": len(unique) >= policy["min_usable_evidence"] and not missing and not missing_any}


def _candidate(ref: dict | None, snapshot: dict | None, relation: str, provenance: dict,
               association: dict | None = None) -> dict:
    return {"ref": ref, "snapshot": snapshot, "relation": relation, "provenance": provenance,
            "user_confirmed": association is not None, "group_confirmation": None,
            "association_id": association.get("association_id") if association else None,
            "issue_scope": {"scope": association.get("scope", "FULL_SNAPSHOT") if association else "FULL_SNAPSHOT",
                            "applicable_issue_ids": association.get("applicable_issue_ids", []) if association else []}}


def build_evidence_plan(store: Store, run_id: str, *, judgments: list[dict] | None = None) -> dict:
    """Select all supplied table references and only necessary search candidates.

    Scope-specific confirmations replace a resource's default FULL_SNAPSHOT view.
    The planner is read-only; origin recovery and all collection run externally.
    """
    cases = {case["case_id"]: case for case in store.records(run_id, "cases")}
    all_refs = store.records(run_id, "references")
    ignored_empty_refs = {ref["ref_id"] for ref in all_refs
                          if not ref.get("url") and is_empty_link_value(ref.get("raw_text", ""))}
    refs = {ref["ref_id"]: ref for ref in all_refs if ref["ref_id"] not in ignored_empty_refs}
    snapshots = {snapshot["snapshot_id"]: snapshot for snapshot in store.records(run_id, "snapshots")}
    active = {snapshot["snapshot_id"]: snapshot for snapshot in store.active_snapshots(run_id)}
    by_resource = snapshot_index(list(active.values()))
    associations = [record for record in store.records(run_id, "evidence_associations") if record.get("user_confirmed") is True
                    and (record.get("ref_id") not in ignored_empty_refs or record.get("snapshot_id"))]
    groups = [group for group in store.records(run_id, "event_groups") if group.get("user_confirmed") is True]
    group_by_case = {case_id: group for group in groups for case_id in group["case_ids"]}
    judgments = [judgment for judgment in judgments or [] if not judgment.get("is_stale", False)]
    domain_relations = _trigger_source_relations(store, run_id)
    candidates = {}

    def resource_url(association):
        snapshot = snapshots.get(association.get("snapshot_id"))
        ref = refs.get(association.get("ref_id"))
        return _resource((snapshot or ref or {}).get("url"))

    for case_id, case in cases.items():
        options = []
        registered = [association for association in associations if association["case_id"] == case_id]
        scoped_urls = {resource_url(association) for association in registered
                       if association.get("scope") == "ISSUES" or association.get("applicable_issue_ids")}
        associated_refs = {association.get("ref_id") for association in registered}
        for ref in refs.values():
            if ref["case_id"] != case_id or ref["ref_id"] in associated_refs or _resource(ref.get("url")) in scoped_urls:
                continue
            provenance = source_relation(case, ref)
            snapshot = by_resource.get(_resource(ref.get("url")))
            options.append(_candidate(ref, snapshot, provenance["relation"], provenance))
        for association in registered:
            snapshot = snapshots.get(association.get("snapshot_id")) if association.get("snapshot_id") else None
            ref = refs.get(association.get("ref_id"))
            url = resource_url(association)
            matching = [value for value in refs.values() if value["case_id"] == case_id and _resource(value.get("url")) == url]
            if ref is not None:
                matching = [ref]
            # An explicit scope also retains the original same-URL occurrence trace.
            matching = matching or [None]
            for actual_ref in matching:
                actual_snapshot = snapshot or by_resource.get(_resource((actual_ref or {}).get("url")))
                provenance = source_relation(case, actual_ref) if actual_ref else {
                    "relation": "PROVENANCE_PENDING", "source_grade": "PROVENANCE_PENDING",
                    "reason": "Snapshot origin is not upgraded by user confirmation", "trace": {"case_id": case_id}}
                options.append(_candidate(actual_ref, actual_snapshot, provenance["relation"],
                    {"source": provenance, "association": association}, association))
        candidates[case_id] = options

    # Only an explicitly confirmed group can borrow another member's supplied source.
    for case_id, options in candidates.items():
        group = group_by_case.get(case_id)
        supplied = any(option["relation"] in TABLE_GRADES or option["user_confirmed"] for option in options)
        if group and not supplied:
            for member in group["case_ids"]:
                if member == case_id:
                    continue
                for option in candidates.get(member, []):
                    if ((option["relation"] not in TABLE_GRADES and not option["user_confirmed"])
                            or option["provenance"].get("inherited_from_case_id")):
                        continue
                    options.append({**option, "user_confirmed": True, "group_confirmation": group["group_id"],
                        "provenance": {"group_id": group["group_id"], "inherited_from_case_id": member,
                                       "source": option["provenance"]}})

    # Bind prior decisions to all current candidates, including rejected search
    # candidates that must not be tried again. A replaced issue scope is not current.
    candidate_work_ids = set()
    candidate_work_ids_by_case = {}
    for case_id, options in candidates.items():
        candidate_work_ids_by_case[case_id] = set()
        group = group_by_case.get(case_id)
        for option in options:
            if _readable(option, active):
                key = {"group_or_case_id": group["group_id"] if group else case_id,
                       "snapshot_id": option["snapshot"]["snapshot_id"], "issue_scope": option["issue_scope"],
                       "input_hash": semantic_input_hash(cases[case_id])}
                work_id = "work-" + digest(key)[:24]
                candidate_work_ids.add(work_id)
                candidate_work_ids_by_case[case_id].add(work_id)
    judgments = [judgment for judgment in judgments if not judgment.get("work_id") or judgment["work_id"] in candidate_work_ids]

    def actions_for(option):
        snapshot, ref = option["snapshot"], option["ref"]
        required, optional = [], []
        if option["relation"] == "PROVENANCE_PENDING":
            required.append({"action": "RECOVER_PROVENANCE", "actor": "AGENT", "ref_id": (ref or {}).get("ref_id"),
                             "snapshot_id": (snapshot or {}).get("snapshot_id"), "on_failure": "REPORT_PROVENANCE_GAP"})
        if snapshot and snapshot["snapshot_id"] not in active:
            required.append({"action": "RECONFIRM_SNAPSHOT", "actor": "AGENT", "snapshot_id": snapshot["snapshot_id"]})
            return required, optional, "CAPTURE_GAPS"
        if snapshot and snapshot.get("status") in UNREADABLE:
            required.append({"action": "RESOLVE_CAPTURE_FAILURE", "actor": "AGENT", "snapshot_id": snapshot["snapshot_id"],
                             "status": snapshot["status"]})
            return required, optional, "CAPTURE_GAPS"
        if _readable(option, active):
            required.append({"action": "EXTRACT_FACTS", "snapshot_id": snapshot["snapshot_id"], "issue_scope": option["issue_scope"]})
            if snapshot.get("status") != "COMPLETE":
                optional.append({"action": "COMPLETE_CAPTURE", "snapshot_id": snapshot["snapshot_id"], "blocking": False})
            return required, optional, "PROVENANCE_RECOVERY" if option["relation"] == "PROVENANCE_PENDING" else None
        if ref and ref.get("status") == "PARSED" and _url(ref.get("url")):
            required.append({"action": "FETCH", "actor": "AGENT", "ref_id": ref["ref_id"], "url": ref["url"]})
            return required, optional, "FETCH_REQUIRED"
        required.append({"action": "RESTORE_REFERENCE", "actor": "AGENT", "ref_id": (ref or {}).get("ref_id"),
                         "on_failure": "REPORT_REFERENCE_GAP"})
        return required, optional, "PROVENANCE_RECOVERY"

    plans, work = [], {}
    for case_id, case in sorted(cases.items()):
        group = group_by_case.get(case_id)
        case_judgments = [judgment for judgment in judgments if not judgment.get("work_id")
                          or judgment["work_id"] in candidate_work_ids_by_case[case_id]]
        all_options = candidates[case_id]
        domain_assessments = [{"snapshot_id": snapshot_id, "source_relation": relation}
            for (candidate_case_id, snapshot_id), relation in sorted(domain_relations.items())
            if candidate_case_id == case_id and snapshot_id in active]
        domain_excluded = {item["snapshot_id"] for item in domain_assessments if item["source_relation"] == "NOT_RELATED"}
        domain_weak = {item["snapshot_id"] for item in domain_assessments if item["source_relation"] in {"PARTIAL", "UNKNOWN"}}
        domain_usable = {item["snapshot_id"] for item in domain_assessments if item["source_relation"] in {"MATCH", "SUPPLIED_IDENTIFIER"}}
        excluded = [judgment for judgment in case_judgments if _applies(judgment, case_id)
            and (judgment.get("case_attribution") == "MISMATCH" or judgment.get("event_relation") == "DIFFERENT_EVENT")
            and judgment.get("review_status") != "REJECT" and judgment.get("snapshot_id") in active
            and _search_decision(case, active[judgment["snapshot_id"]], judgment, cases) == "AUTO_PROCESSED"]
        insufficient = [judgment for judgment in case_judgments if _applies(judgment, case_id)
            and judgment.get("snapshot_id") in active and _search_insufficient(case, active[judgment["snapshot_id"]], judgment, cases)]

        def option_judged(option, judgment):
            if not option["snapshot"] or option["snapshot"]["snapshot_id"] != judgment.get("snapshot_id"):
                return False
            if not judgment.get("work_id"):
                return True
            key = {"group_or_case_id": group["group_id"] if group else case_id,
                   "snapshot_id": option["snapshot"]["snapshot_id"], "issue_scope": option["issue_scope"],
                   "input_hash": semantic_input_hash(case)}
            return judgment["work_id"] == "work-" + digest(key)[:24]

        options = [option for option in all_options if not (option["relation"] == "SEARCH_DISCOVERED"
            and not option["user_confirmed"] and (
                (option["snapshot"] or {}).get("snapshot_id") in domain_excluded | domain_weak
                or any(option_judged(option, judgment) for judgment in excluded + insufficient)))]
        supplied = [option for option in options if option["relation"] in TABLE_GRADES or option["user_confirmed"]]
        supplied_snapshot_ids = {option["snapshot"]["snapshot_id"] for option in supplied if option["snapshot"]}
        conflicts = [judgment for judgment in case_judgments if _applies(judgment, case_id) and (_conflicting(judgment) or
            (judgment.get("review_status") != "REJECT" and judgment.get("snapshot_id") in supplied_snapshot_ids
             and (judgment.get("case_attribution") == "MISMATCH" or judgment.get("event_relation") == "DIFFERENT_EVENT")))]
        search = [option for option in options if option["relation"] == "SEARCH_DISCOVERED" and not option["user_confirmed"]]
        usable = [option for option in search if option["snapshot"] and (
            option["snapshot"]["snapshot_id"] in domain_usable and _readable(option, active)
            or _search_usable(case, option["snapshot"], case_judgments, cases))]
        unresolved = [option for option in options if option["relation"] == "PROVENANCE_PENDING" and not option["user_confirmed"]]
        selected, required, optional, issues = [], [], [], []
        policy_info = get_search_policy(store, run_id, case_id)
        policy = policy_info["policy"]
        kind = lambda option: resource_kind(option["ref"], option["snapshot"],
            cases.get((option["ref"] or {}).get("case_id"), case))
        selected = sorted(supplied, key=lambda option: _rank(option, active))
        conflict_ids = {judgment.get("snapshot_id") for judgment in conflicts}
        counted = [option for option in supplied if _readable(option, active)
                   and option["snapshot"]["snapshot_id"] not in conflict_ids | domain_excluded]

        def helps(option, goal):
            if goal["missing_sources"] or goal["missing_any_sources"]:
                return kind(option) in goal["missing_sources"] or kind(option) in goal["missing_any_sources"]
            return goal["usable_evidence_count"] < policy["min_usable_evidence"]

        # Validated discoveries supplement supplied material only while a declared
        # condition is unmet. Stop as soon as the complete AND/OR goal is satisfied.
        remaining_usable = list(usable)
        while remaining_usable:
            goal = _goal(policy, counted, kind)
            if goal["satisfied"]:
                break
            helpful = [option for option in remaining_usable if helps(option, goal)]
            if not helpful:
                break
            option = sorted(helpful, key=_search_rank)[0]
            remaining_usable.remove(option)
            selected.append(option)
            counted.append(option)
        goal = _goal(policy, counted, kind)
        policy_reasons = []
        if goal["usable_evidence_count"] < policy["min_usable_evidence"]:
            policy_reasons.append("MIN_USABLE_EVIDENCE_NOT_MET")
        if goal["missing_sources"]:
            policy_reasons.append("REQUIRED_SOURCES_NOT_MET")
        if goal["missing_any_sources"]:
            policy_reasons.append("REQUIRED_ANY_SOURCE_NOT_MET")
        control_status = "SATISFIED" if goal["satisfied"] else "SEARCH_REQUIRED"
        path, stop_reason = ("TABLE_REFERENCES", "ALL_SUPPLIED_REFERENCES_SELECTED_NO_SEARCH") if supplied else (
            ("VERIFIED_SEARCH", "USABLE_SEARCH_EVIDENCE_FOUND") if goal["satisfied"] else
            ("SEARCH_REQUIRED", "EXISTING_CANDIDATES_EXCLUDED_NO_APPLICABLE_EVIDENCE" if excluded or domain_excluded else "NO_EVIDENCE_SEARCH_REQUIRED"))
        if not goal["satisfied"] and not conflicts:
            pending_supplied = [option for option in supplied if not _readable(option, active)]
            unknown_sources = [option for option in supplied if kind(option) == "UNKNOWN"] if (
                goal["missing_sources"] or goal["missing_any_sources"]) else []
            remaining = [option for option in search if option not in selected and option not in usable and helps(option, goal)]
            if pending_supplied:
                control_status = "CAPTURE_GAP" if any(option["snapshot"] and option["snapshot"].get("status") in UNREADABLE
                    or (option["ref"] and not option["ref"].get("url")) for option in pending_supplied) else "PROCESS_EXISTING"
            elif unresolved:
                control_status = "PROVENANCE_PENDING"
                if not supplied:
                    selected.extend(sorted(unresolved, key=lambda option: _rank(option, active)))
                    path, stop_reason = "PROVENANCE_RECOVERY", "AGENT_RECOVERS_SOURCE_BEFORE_REPORTING_GAP"
                else:
                    required.extend({"action": "RECOVER_PROVENANCE", "actor": "AGENT", "ref_id": (option["ref"] or {}).get("ref_id"),
                                     "on_failure": "REPORT_PROVENANCE_GAP"} for option in unresolved)
            elif unknown_sources:
                control_status = "SOURCE_UNKNOWN"
                required.extend({"action": "RECOVER_RESOURCE_KIND", "actor": "AGENT", "ref_id": (option["ref"] or {}).get("ref_id"),
                                 "snapshot_id": (option["snapshot"] or {}).get("snapshot_id")} for option in unknown_sources)
            elif remaining:
                candidate = sorted(remaining, key=_search_rank)[0]
                selected.append(candidate)
                control_status = "CAPTURE_GAP" if candidate["snapshot"] and candidate["snapshot"].get("status") in UNREADABLE else "CANDIDATE_PENDING"
                path, stop_reason = "SEARCH_CANDIDATE", "EXISTING_CANDIDATE_NEEDS_FACT_COMPARISON"
            else:
                required.append({"action": "SEARCH_SUPPORT" if policy != DEFAULT_SEARCH_POLICY else "SEARCH", "actor": "AGENT",
                    "case_id": case_id, "description": case.get("description", ""), "policy_hash": policy_info["policy_hash"],
                    "target_sources": sorted(set(goal["missing_sources"]) | set(goal["missing_any_sources"])),
                    "min_additional_evidence": max(0, policy["min_usable_evidence"] - goal["usable_evidence_count"])})
        chosen_discoveries = [option for option in selected if option in search]
        search_control = {**policy_info, **goal, "search_allowed": control_status == "SEARCH_REQUIRED" and not conflicts,
            "status": "CONFLICT" if conflicts else control_status, "reasons": policy_reasons,
            "selected_candidate_ref_ids": sorted({option["ref"]["ref_id"] for option in chosen_discoveries if option["ref"]}),
            "selected_candidate_snapshot_ids": sorted({option["snapshot"]["snapshot_id"] for option in chosen_discoveries if option["snapshot"]}),
            "counting_basis": "UNIQUE_READABLE_SUPPLIED_SNAPSHOT_OR_FACT_VALIDATED_DISCOVERY;_NOT_FAULT_CONFIRMATION"}
        if domain_assessments:
            search_control["counting_basis"] += ";_TRIGGER_INIT_CURRENT_SOURCE_ASSESSMENT"
        if conflicts:
            search_control["satisfied"] = False
            search_control["reasons"].append("KNOWN_CONFLICT")
        # In the XLSX workflow, a blocked supplied PR or a wrong original Wiki
        # must not hide an already captured replacement Wiki from verification.
        if "WIKI" in goal["missing_sources"] and store.get(run_id, "xlsx_workflow", "config"):
            pending = [option for option in search if kind(option) == "WIKI"
                       and option not in selected and option not in usable]
            if pending:
                selected.append(sorted(pending, key=_search_rank)[0])
        if conflicts:
            conflict_ids = {judgment.get("snapshot_id") for judgment in conflicts}
            for option in options:
                if option["snapshot"] and option["snapshot"]["snapshot_id"] in conflict_ids and option not in selected:
                    selected.append(option)
            path, stop_reason = "EXCEPTION", "KNOWN_CONFLICT_REQUIRES_RECONCILIATION"
            required.append({"action": "RECONCILE_CONFLICT", "judgment_ids": sorted(j.get("judgment_id", "") for j in conflicts)})
            issues.append({"code": "KNOWN_CONFLICT", "judgment_ids": sorted(j.get("judgment_id", "") for j in conflicts)})
        states = []
        for option in selected:
            more, suggestions, state = actions_for(option)
            required.extend(more)
            optional.extend(suggestions)
            states.append(state)
        unselected_unknown = [option for option in unresolved if option not in selected]
        if unselected_unknown:
            unknown_ids = sorted({option["ref"]["ref_id"] for option in unselected_unknown if option["ref"]})
            issues.append({"code": "UNRESOLVED_REFERENCE_PROVENANCE", "ref_ids": unknown_ids,
                           "handling": "Agent recovers origin or reports the remaining gap; not an automatic human exception"})
            optional.extend({"action": "RECOVER_PROVENANCE", "actor": "AGENT", "blocking": False,
                             "ref_id": option["ref"]["ref_id"] if option["ref"] else None,
                             "on_failure": "REPORT_PROVENANCE_GAP"} for option in unselected_unknown)
        if not conflicts and selected:
            if "CAPTURE_GAPS" in states:
                path, stop_reason = "CAPTURE_GAPS", "COLLECTION_FAILURE_IS_A_REPORTED_GAP_NOT_AN_AUTOMATIC_HUMAN_DECISION"
            elif "PROVENANCE_RECOVERY" in states:
                path, stop_reason = "PROVENANCE_RECOVERY", "AGENT_RECOVERS_SOURCE_BEFORE_REPORTING_GAP"
            elif "FETCH_REQUIRED" in states:
                path = "FETCH_ORIGINAL" if any(option["relation"] == "SOURCE_CELL_LINKED" for option in selected) else "FETCH_PROVIDED"
                stop_reason = "FETCH_ALL_SUPPLIED_REFERENCES_NO_NEW_SEARCH" if supplied else "FETCH_EXISTING_SEARCH_CANDIDATE"
            elif supplied:
                grades = {option["relation"] for option in selected}
                path = next(iter(grades)) if len(grades) == 1 else "TABLE_REFERENCES"
                stop_reason = "ALL_SUPPLIED_REFERENCES_AVAILABLE_NO_SEARCH"
        if not conflicts and search_control["search_allowed"]:
            path = "SEARCH_REQUIRED"
            if policy != DEFAULT_SEARCH_POLICY:
                stop_reason = "EXPLICIT_SEARCH_POLICY_UNMET"
        elif not conflicts and chosen_discoveries and not goal["satisfied"] and not any(states):
            path, stop_reason = "SEARCH_CANDIDATE", "EXISTING_CANDIDATE_NEEDS_FACT_COMPARISON"
        selected_ref_ids = sorted({option["ref"]["ref_id"] for option in selected if option["ref"]})
        selected_snapshot_ids = sorted({option["snapshot"]["snapshot_id"] for option in selected if option["snapshot"]})
        grades = sorted({option["relation"] for option in selected}, key=lambda grade: GRADE_PRIORITY[grade])
        relation = grades[0] if grades else "PROVENANCE_PENDING"
        confirmed = any(option["user_confirmed"] for option in selected)
        scopes = sorted((option["issue_scope"] for option in selected), key=digest)
        routing = {"case_id": case_id, "group_id": group["group_id"] if group else None, "relation": relation,
            "source_grades": grades, "user_confirmed": confirmed, "selected_ref_ids": selected_ref_ids,
            "selected_snapshot_ids": selected_snapshot_ids, "issue_scopes": scopes, "search_policy_hash": policy_info["policy_hash"]}
        if domain_assessments:
            routing["domain_source_assessments"] = domain_assessments
        plan = {**routing, "external_id": case.get("external_id", ""), "source_file": case.get("source_file"),
            "sheet": case.get("sheet"), "row": case.get("row"),
            "source_grade": relation, "path": path, "routing_hash": digest(routing),
            "search_control": search_control,
            "required_actions": required, "optional_actions": optional, "stop_reason": stop_reason, "issues": issues,
            "association_ids": sorted({option["association_id"] for option in selected if option["association_id"]}),
            "group_confirmation": group["group_id"] if group else None,
            "excluded_candidate_judgment_ids": sorted(j.get("judgment_id", "") for j in excluded),
            "insufficient_candidate_judgment_ids": sorted(j.get("judgment_id", "") for j in insufficient
                if any(option["relation"] == "SEARCH_DISCOVERED" and not option["user_confirmed"] and option_judged(option, j) for option in all_options)),
            "domain_source_assessments": domain_assessments,
            "excluded_source_snapshot_ids": sorted(domain_excluded),
            "insufficient_source_snapshot_ids": sorted(domain_weak),
            "provenance": [option["provenance"] for option in selected], "work_ids": []}
        for option in selected:
            if not _readable(option, active):
                continue
            snapshot = option["snapshot"]
            work_key = {"group_or_case_id": group["group_id"] if group else case_id, "snapshot_id": snapshot["snapshot_id"],
                        "issue_scope": option["issue_scope"], "input_hash": semantic_input_hash(case)}
            work_id = "work-" + digest(work_key)[:24]
            item = work.setdefault(work_id, {"work_id": work_id, **work_key, "group_id": group["group_id"] if group else None,
                "representative_case_id": case_id, "case_ids": [], "ref_ids": [], "source_records": [], "member_relations": {},
                "source_grades": [], "member_source_grades": {}, "member_user_confirmed": {}, "user_confirmed": False,
                "association_ids": [], "group_confirmation": group["group_id"] if group else None,
                "provenance": [], "actions": ["EXTRACT_FACTS", "MATCH_CATALOG"]})
            if case_id not in item["case_ids"]:
                item["case_ids"].append(case_id)
                item["source_records"].append(_source_record(case))
            member_grades = set(item["member_source_grades"].get(case_id, [])) | {option["relation"]}
            item["member_source_grades"][case_id] = sorted(member_grades, key=lambda grade: GRADE_PRIORITY[grade])
            item["member_relations"][case_id] = item["member_source_grades"][case_id][0]
            item["source_grades"] = sorted(set(item["source_grades"]) | {option["relation"]}, key=lambda grade: GRADE_PRIORITY[grade])
            item["relation"] = item["source_grade"] = item["source_grades"][0]
            item["member_user_confirmed"][case_id] = item["member_user_confirmed"].get(case_id, False) or option["user_confirmed"] or bool(group)
            item["user_confirmed"] = any(item["member_user_confirmed"].values())
            item["ref_ids"] = sorted(set(item["ref_ids"]) | ({option["ref"]["ref_id"]} if option["ref"] else set()))
            item["association_ids"] = sorted(set(item["association_ids"]) | ({option["association_id"]} if option["association_id"] else set()))
            if option["provenance"] not in item["provenance"]:
                item["provenance"].append(option["provenance"])
            if work_id not in plan["work_ids"]:
                plan["work_ids"].append(work_id)
        plans.append(plan)
    group_plans = [{**group, "input_variants": {case_id: semantic_input_hash(cases[case_id]) for case_id in group["case_ids"]},
                    "technical_input_divergence": len({semantic_input_hash(cases[case_id]) for case_id in group["case_ids"]}) > 1}
                   for group in groups]
    collection = {}
    selected_refs = {ref_id for plan in plans for ref_id in plan["selected_ref_ids"]}
    for ref_id in sorted(selected_refs):
        ref = refs[ref_id]
        url = _url(ref.get("url"))
        if ref.get("status") != "PARSED" or not url:
            continue
        key = resource_key(url)
        snapshot = by_resource.get(key)
        readable = bool(snapshot and snapshot.get("status") in {"COMPLETE", "PARTIAL", "CONTENT_CAPTURED"} and snapshot.get("text", "").strip())
        item = collection.setdefault(key, {"fetch_id": "resource-" + digest(key)[:24], "url": key,
            "resource_key": key, "original_urls": [], "ref_ids": [],
            "case_ids": [], "required": not readable, "retrieval_status": snapshot["status"] if snapshot else "NOT_FETCHED",
            "snapshot_id": snapshot["snapshot_id"] if snapshot else None, "action": "FETCH", "actor": "AGENT"})
        item["ref_ids"].append(ref_id)
        item["original_urls"] = sorted(set(item["original_urls"]) | {url})
        citing = {plan["case_id"] for plan in plans if ref_id in plan["selected_ref_ids"]}
        item["case_ids"] = sorted(set(item["case_ids"]) | citing)
    return {"schema_version": "1.0", "run_id": run_id, "policy_version": POLICY_VERSION,
        "plan_hash": digest({"policy_version": POLICY_VERSION, "routing": [plan["routing_hash"] for plan in plans]}),
        "cases": plans, "groups": group_plans, "ignored_empty_reference_ids": sorted(ignored_empty_refs),
        "work_items": sorted(work.values(), key=lambda item: item["work_id"]),
        "fetch_work_items": sorted(collection.values(), key=lambda item: item["url"])}
