"""Structured-XLSX workflow: existing core + external Agent + one workbook.

The program owns routing and continuation. Websites and semantic decisions stay
with the configured Agent, through files or an argv-based process adapter.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from .bridge import CodexJudge, OpenCodeJudge, export_model_tasks, policy_fingerprint, submit_model_results
from .catalog_drafts import prepare_draft, validate_draft
from .evidence_plan import register_search_policy, resource_kind, collection_source_policy
from .importers import import_cases, import_catalog
from .input_budget import InputTooLarge, finalize_model_task
from .pipeline import evidence_plan, execute, fetch_tasks, import_into, report_data, require_catalog_mapping
from .store import AuditError, Store, canonical_url, digest
from .wiki_checks import record_wiki_check, wiki_plan
from .capture_quality import capture_quality, collection_observation_instructions
from .resource_identity import resource_key, same_resource
from .search_guidance import search_guidance, validate_search_trace
from .workflow_scope import scoped_store
from .contracts import EvidencePackage

RULE_VERSION = "structured-xlsx-2"
WORKBOOK_NAME = "故障整理及模式库建议.xlsx"


def config(store: Store, run_id: str) -> dict:
    value = store.get(run_id, "xlsx_workflow", "config")
    if not value:
        raise AuditError("Start a structured XLSX workflow first")
    return value


def start(store: Store, source: Path, catalog: Path, work_root: Path, *, executor="opencode",
          source_kind="LEGACY_TABLE", catalog_sheets=None, expected_catalog_count=None,
          catalog_scope="UNSPECIFIED", run_id=None, case_ids=None) -> dict:
    if source.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise AuditError("This workflow supports structured XLSX only; Word/PPT/arbitrary layouts are TODO")
    if executor not in {"opencode", "codex"}:
        raise AuditError("Executor must be opencode or codex")
    cases = import_cases(source, source_kind)
    if not cases["cases"] or not any(case["description"] for case in cases["cases"]):
        raise AuditError("Structured XLSX needs a recognized problem-description header")
    items = import_catalog(catalog, sheets=catalog_sheets, scope=catalog_scope, expected_count=expected_catalog_count)
    run_id = store.run_info(run_id)["run_id"] if run_id else store.create_run({"workflow": RULE_VERSION})
    old = store.get(run_id, "xlsx_workflow", "config")
    if old:
        if old["source_hash"] != cases["documents"][0]["source_sha256"] or old["executor"] != executor:
            raise AuditError("Resume with the original source and executor or start a new run")
    if case_ids is not None and (not isinstance(case_ids, list) or not case_ids or not all(isinstance(key, str) for key in case_ids)):
        raise AuditError("case_ids must be a nonempty JSON array of case IDs")
    selected = sorted(case_ids if case_ids is not None else (old or {}).get("selected_case_ids") or [case["case_id"] for case in cases["cases"]])
    known = {case["case_id"] for case in store.records(run_id, "cases")} | {case["case_id"] for case in cases["cases"]}
    if not selected or len(selected) != len(set(selected)) or set(selected) - known:
        raise AuditError("Workflow scope must contain unique case IDs from this run")
    if old and old.get("selected_case_ids") and selected != old["selected_case_ids"]:
        raise AuditError("Workflow case scope is frozen; retain this run and use a linked follow-up run for another scope")
    directory = (work_root / run_id).resolve()
    if directory.is_relative_to(store.root):
        raise AuditError("Workflow files must be outside state")
    from .pipeline import check_catalog_import
    check_catalog_import(store, run_id, items)
    import_into(store, run_id, cases)
    import_into(store, run_id, items, catalog=True)
    value = old or {"run_id": run_id, "directory": str(directory), "executor": executor,
                    "source_hash": cases["documents"][0]["source_sha256"], "rule_version": RULE_VERSION}
    value = {**value, "selected_case_ids": selected, "scope_hash": digest(selected),
             "capture_quality_required": True, "max_search_rounds": 3,
             "capture_attempts_per_resource": 3, "rule_version": RULE_VERSION}
    if old != value:
        store.put(run_id, "xlsx_workflow", "config", value, mutable=bool(old))
        if old:
            store.event(run_id, "workflow_config_upgraded", {"previous": old, "current": value})
    if not old:
        register_search_policy(store, run_id, {"required_sources": ["WIKI"]})
    return {**value, "case_count": len(selected), "catalog_count": len(items["items"])}


def _policy() -> str:
    from . import wiki_checks, capture_quality, search_guidance, resource_identity, workflow_scope
    from . import trigger_taxonomy, trigger_assessment, trigger_workflow
    return digest({"core": policy_fingerprint(), "workflow": digest(Path(__file__).read_bytes()),
                   "helpers": digest(b"".join(Path(module.__file__).read_bytes() for module in
                       (wiki_checks, capture_quality, search_guidance, resource_identity, workflow_scope,
                        trigger_taxonomy, trigger_assessment, trigger_workflow)))})


def _json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _request(store, run_id, cfg, kind, payload, instructions, priority) -> dict | None:
    try:
        request = finalize_model_task({"kind": kind, "run_id": run_id, "policy_hash": _policy(),
            "collection_policy_hash": collection_source_policy(store, run_id)["policy_hash"],
            "instructions": instructions, "payload": payload,
            "execution_context": {"new_session_required": True, "history": "THIS_TASK_ONLY",
                "role": "browser" if kind in {"fetch", "wiki_check", "search"} else "semantic",
                "scope_hash": cfg.get("scope_hash", "")}})
    except InputTooLarge as exc:
        block = {"kind": kind, "case_ids": payload.get("case_ids", []), "reason": "INPUT_TOO_LARGE",
                 "input_budget": exc.details, "policy_hash": _policy()}
        store.put(run_id, "workflow_blocks", digest(block), block)
        return {"blocked": True, "block_id": digest(block), **block}
    task_id = request["task_id"]
    store.put(run_id, "workflow_requests", task_id, request)
    path = Path(cfg["directory"]) / "tasks" / task_id / "request.json"
    _json(path, request)
    execution = store.get(run_id, "workflow_execution", task_id) or {}
    site = urlsplit(payload.get("url", "https://wiki.huawei.com/" if kind == "wiki_check" else "")).netloc.lower()
    auth = store.get(run_id, "workflow_auth", site) if site and kind in {"fetch", "wiki_check", "search"} else None
    if execution.get("blocked_code") == "EXECUTOR_CONTEXT_LIMIT" or auth and auth.get("status") == "WAITING_AUTH":
        code = "EXECUTOR_CONTEXT_LIMIT" if execution.get("blocked_code") == "EXECUTOR_CONTEXT_LIMIT" else "WAITING_AUTH"
        block = {"kind": kind, "case_ids": payload.get("case_ids", []), "reason": code,
                 "details": {"task_id": task_id, "site": site, "error": execution.get("error", (auth or {}).get("reason", ""))},
                 "policy_hash": _policy()}
        store.put(run_id, "workflow_blocks", digest(block), block)
        return {"blocked": True, "block_id": digest(block), **block}
    done = store.get(run_id, "workflow_results", task_id)
    if done and not done.get("retry"):
        return None
    return {"task_id": task_id, "kind": kind, "priority": priority, "request": str(path)}


def next_tasks(store: Store, run_id: str) -> dict:
    store = scoped_store(store, run_id)
    cfg = config(store, run_id)
    trigger_mode = cfg.get("purpose", "").startswith("TRIGGER_")
    cases = store.records(run_id, "cases")
    if cfg.get("purpose") == "TRIGGER_INIT" and cfg.get("init_basis") == "SOURCE_DEFINITIONS":
        from .trigger_workflow import classification_payloads
        from .trigger_assessment import instructions as trigger_instructions
        tasks, blocks = [], []
        for payload in classification_payloads(store, run_id):
            value = _request(store, run_id, cfg, "trigger_classify", payload, trigger_instructions(), 4)
            if value and value.get("blocked"):
                blocks.append(value["block_id"])
            elif value:
                tasks.append(value)
        checks = {case["case_id"]: {"status": "NOT_REQUESTED",
            "reason": "Explicit source-definition initialization; webpage evidence was not requested"} for case in cases}
        return _finish_tasks(store, run_id, cfg, tasks, blocks, checks)
    checks = {case["case_id"]: wiki_plan(store, run_id, case) for case in cases}
    source_policy = collection_source_policy(store, run_id)
    # A bounded NO_MATCH fulfills checking, not finding. Release only this
    # workflow's temporary Wiki selection condition for the individual case.
    for cid, check in checks.items():
        stopping = ({"required_any_sources": source_policy["collection_sources"]}
                    if check["status"] == "NOT_SUPPORTED" else
                    {} if check["status"] == "NO_MATCH" else {"required_sources": ["WIKI"]})
        register_search_policy(store, run_id, stopping, case_id=cid)
    tasks, blocks = [], []
    def add(kind, payload, text, priority):
        value = _request(store, run_id, cfg, kind, payload, text, priority)
        if value and value.get("blocked"):
            blocks.append(value["block_id"])
        elif value:
            tasks.append(value)
    retry_resources = set()
    for done in store.records(run_id, "workflow_results"):
        if not done.get("retry"):
            continue
        old = store.get(run_id, "workflow_requests", done["task_id"])
        if old and old["policy_hash"] == _policy() and old.get("collection_policy_hash") == source_policy["policy_hash"]:
            if set(old["payload"].get("case_ids", [])) - {c["case_id"] for c in cases}:
                continue
            case = old["payload"].get("case")
            if old["kind"] == "wiki_check" and old["payload"]["wiki_input_hash"] != checks[case["case_id"]]["input_hash"]:
                continue
            path = Path(cfg["directory"]) / "tasks" / old["task_id"] / "request.json"
            tasks.append({"task_id": old["task_id"], "kind": old["kind"], "priority": 0, "request": str(path)})
            if old["kind"] == "fetch":
                retry_resources.add(resource_key(old["payload"]["url"]))
    for case in cases:
        check = checks[case["case_id"]]
        if check["status"] == "SEARCH_REQUIRED":
            guidance = search_guidance(case, max_rounds=cfg.get("max_search_rounds", 3), collection_policy=source_policy)
            add("wiki_check", {"case": case, "case_ids": [case["case_id"]], "wiki_input_hash": check["input_hash"],
                               "wiki_task_id": check["task_id"], "search_guidance": guidance,
                               **({"previous_domain_assessments": check.get("domain_source_assessments", [])} if trigger_mode else {})},
                "Search Wiki first within a stated scope. Return {request_hash, outcome: FOUND|NO_MATCH|BLOCKED, "
                "executed:true, query, scope, checked_at (ISO timezone), executed_by, reason, packages:[]}. "
                "FOUND requires actual captured Wiki EvidencePackage(s); they remain candidates until comparison. "
                "NO_MATCH describes only this bounded search; auth failure is BLOCKED. Never invent a login or search. "
                + guidance["instructions"] + " " + collection_observation_instructions(), 0)
    for item in fetch_tasks(store, run_id)["fetch_tasks"]:
        if resource_key(item["url"]) in retry_resources:
            continue
        relevant = [case for case in cases if case["case_id"] in item["case_ids"]]
        from .pipeline import current_judgments
        from .resource_identity import snapshot_index
        active = snapshot_index(store.active_snapshots(run_id))
        children = [ref for ref in store.records(run_id, "references") if ref.get("parent_url")
                    and same_resource(ref["parent_url"], item["url"])]
        child_coverage = set()
        current = current_judgments(store, run_id)
        for child in children:
            snapshot = active.get(resource_key(child["url"]))
            if not snapshot or not capture_quality(snapshot, require_observation=True)["usable_body"]:
                continue
            js = [j for j in current if j["snapshot_id"] == snapshot["snapshot_id"] and j["case_id"] == child["case_id"]]
            if not js or any(j.get("processing_status") == "AUTO_PROCESSED" and j["case_attribution"] != "MISMATCH"
                             and j["event_relation"] != "DIFFERENT_EVENT" for j in js):
                child_coverage.add(child["case_id"])
        if set(item["case_ids"]) <= child_coverage:
            continue  # Existing navigation candidates are processed before rereading the index.
        previous = [value for value in store.records(run_id, "workflow_results")
                    if not value.get("retry") and (request := store.get(run_id, "workflow_requests", value["task_id"]))
                    and request["kind"] == "fetch" and same_resource(request["payload"]["url"], item["url"])]
        if len(previous) >= cfg.get("capture_attempts_per_resource", 3):
            block = {"kind": "fetch", "case_ids": item["case_ids"], "reason": "PAGE_BODY_UNAVAILABLE",
                     "details": {"url": item["url"], "attempts": len(previous)}, "policy_hash": _policy()}
            store.put(run_id, "workflow_blocks", digest(block), block)
            blocks.append(digest(block))
            continue
        # Capture is independent of the hoped-for case conclusion. Keep all
        # occurrence identities, without repeating hundreds of source rows.
        payload = {"url": item["url"], "case_ids": item["case_ids"],
                   "reference_ids": [ref["ref_id"] for ref in item["references"]]}
        if item.get("snapshot_id") and capture_quality(store.get(run_id, "snapshots", item["snapshot_id"]),
                                                       require_observation=True)["needs_repair"]:
            snapshot = store.get(run_id, "snapshots", item["snapshot_id"])
            payload["repair_capture"] = {"snapshot_id": item["snapshot_id"],
                                         "quality": capture_quality(snapshot, require_observation=True),
                                         "previous_attempts": len(previous)}
            payload["navigation_targets"] = [{"case_id": c["case_id"], "description": c["description"],
                "operator": c["operator_raw"], "customer_model": c["customer_model"],
                "sheet": c["sheet"], "row": c["row"], "cell_locations": c["cell_locations"]} for c in relevant]
            payload["previous_children"] = [{"url": ref["url"], "case_id": ref["case_id"]} for ref in children]
        add("fetch", payload,
            "Read this supplied URL using the site's actual tools. Return {request_hash, outcome: CAPTURED|BLOCKED, "
            "packages:[EvidencePackage]}. Preserve body, comments, applicable issue and needed Diff, exact capture "
            "scope and access failures. Use the requested URL; no expansion to fill evidence types. "
            "For an index, retain its package and return related child captures in linked_packages "
            "[{package:EvidencePackage,case_ids:[applicable target IDs],navigation_quote:exact parent passage containing child URL}]. "
            "Use navigation_targets to select subpages; child linkage remains a candidate, not confirmed. "
            + collection_observation_instructions(),
            0 if resource_kind({"url": item["url"]}) == "WIKI" else 2)
    plan = evidence_plan(store, run_id)
    if cfg.get("purpose") == "TRIGGER_INIT":
        from .trigger_workflow import source_lookups
        for lookup in source_lookups(store, run_id):
            guidance = search_guidance(lookup["case"], max_rounds=cfg.get("max_search_rounds", 3), collection_policy=source_policy)
            add("search", {**lookup, "search_guidance": guidance},
                "Resolve this ORIGINAL supplied identifier using the actual Wiki/DTS search tools. "
                "Do not construct or guess an internal URL. Capture the page for this exact identifier, "
                "not a PR mentioning it. Keep the original reference and SEARCH_DISCOVERED URL origins separate. "
                "Return the standard executed search response with packages, query, scope, checked_at, executed_by, "
                "reason and search trace. " + guidance["instructions"] + " " + collection_observation_instructions(), 1)
    for row in plan["cases"]:
        check = checks[row["case_id"]]
        if row["search_control"]["search_allowed"] and check["status"] in {"FOUND", "NO_MATCH", "NOT_SUPPORTED"}:
            case = next(c for c in cases if c["case_id"] == row["case_id"])
            prior_ids = set(row["excluded_candidate_judgment_ids"] + row["insufficient_candidate_judgment_ids"])
            prior = [{"judgment_id": j["judgment_id"],
                      "url": store.get(run_id, "snapshots", j["snapshot_id"])["url"], "reason": j["short_reason"]}
                     for j in store.records(run_id, "judgments") if j["judgment_id"] in prior_ids]
            guidance = search_guidance(case, max_rounds=cfg.get("max_search_rounds", 3), collection_policy=source_policy)
            add("search", {"case": case, "case_ids": [case["case_id"]], "search_policy": row["search_control"]["policy"],
                "search_guidance": guidance,
                "collection_source_policy": source_policy,
                **({"previous_domain_assessments": row.get("domain_source_assessments", [])} if trigger_mode else {}),
                "excluded_candidate_judgment_ids": row["excluded_candidate_judgment_ids"],
                "insufficient_candidate_judgment_ids": row["insufficient_candidate_judgment_ids"], "previous_candidates": prior},
                "Search for evidence of this specific fault within collection_source_policy.collection_sources. "
                "When GitCode is explicitly selected, search GitCode first; any enabled GitHub fallback remains separately attributed. "
                "Wiki NOT_SUPPORTED is an explicit user override, not a completed Wiki search or NO_MATCH. "
                "Stop after one adequate candidate; do not fill all source types. Return {request_hash, "
                "outcome: FOUND|NO_MATCH|BLOCKED, executed:true, query, scope, checked_at, executed_by, reason, "
                "packages:[captured EvidencePackage]}. Keyword matches are not confirmed incidents. "
                + guidance["instructions"] + " " + collection_observation_instructions(), 2)
    judge = CodexJudge(store, run_id) if cfg["executor"] == "codex" else OpenCodeJudge(store, run_id)
    execute(store, run_id, judge, mode=cfg["executor"], model_id=cfg["executor"] + "-managed",
            summarize_only=cfg.get("purpose") == "TRIGGER_INIT", map_catalog=require_catalog_mapping(store, run_id))
    for task in export_model_tasks(store, run_id, executor=cfg["executor"])["tasks"]:
        add("model", {"task": task},
            "Execute the complete enclosed model task using its instructions and expected_contract. Return its "
            "standard result envelope {schema_version:'1.0',run_id:inner.run_id,task_id:inner.task_id,"
            "request_hash:inner.request_hash,producer:{executor:'" + cfg["executor"] + "'," + cfg["executor"] + "_version:"
            "actual version or 'unreported',provider:actual provider,model:actual model or 'unreported',"
            "session_id:actual task session},result:expected_contract body}. "
            "The inner task, not this dispatch wrapper, supplies the response identity. Do not invent ACCEPT.", 3)
    # A ready case does not wait for unrelated cases' fetch/summary tasks.
    pending_cases = set()
    for task in tasks:
        payload = store.get(run_id, "workflow_requests", task["task_id"])["payload"]
        pending_cases.update(payload.get("case_ids", []))
        inner = payload.get("task", {})
        pending_cases.update(inner.get("payload", {}).get("processing_context", {}).get("member_case_ids", []))
        if inner.get("payload", {}).get("case"):
            pending_cases.add(inner["payload"]["case"]["case_id"])
        if inner.get("kind") == "summarize":
            sid = inner["payload"]["snapshot"]["snapshot_id"]
            pending_cases.update(row["case_id"] for row in plan["cases"] if sid in row["selected_snapshot_ids"])
    if trigger_mode:
        from .trigger_workflow import classification_payloads
        from .trigger_assessment import instructions as trigger_instructions
        for payload in classification_payloads(store, run_id):
            if not set(payload["case_ids"]) & pending_cases:
                add("trigger_classify", payload, trigger_instructions(), 4)
    for case in ([] if trigger_mode else cases):
        if case["case_id"] not in pending_cases:
            prepared = prepare_draft(store, run_id, [case["case_id"]])
            if prepared["status"] == "BLOCKED":
                block = {"kind": "catalog_draft", "case_ids": [case["case_id"]],
                         "reason": "INPUT_TOO_LARGE", "input_budget": prepared["input_budget"], "policy_hash": _policy()}
                store.put(run_id, "workflow_blocks", digest(block), block)
                blocks.append(digest(block))
                continue
            add("catalog_draft", {"request": prepared["request"], "case_ids": [case["case_id"]]},
                "Execute the enclosed catalog draft request. Decide ADD/REFINE/APPEND_CASE/NO_CHANGE and quantity "
                "from facts and the complete original library. Return CATALOG_DRAFT with the INNER request_hash "
                "and actual producer; keep source attribution/unknowns distinct from verified root causes.", 4)
    return _finish_tasks(store, run_id, cfg, tasks, blocks, checks)


def _finish_tasks(store, run_id, cfg, tasks, blocks, checks):
    tasks = list({task["task_id"]: task for task in tasks}.values())
    tasks.sort(key=lambda task: (task["priority"], task["task_id"]))
    for task in tasks:
        task["response"] = str(response_path(store, run_id, task["task_id"]))
    store.put(run_id, "workflow_state", "current", {"block_ids": blocks,
              "task_ids": [task["task_id"] for task in tasks]}, mutable=True)
    return {"run_id": run_id, "status": "WAITING_AGENT" if tasks else "READY_TO_EXPORT",
            "tasks": tasks, "wiki_checks": checks, "directory": cfg["directory"]}


def response_path(store, run_id, task_id) -> Path:
    cfg = config(store, run_id)
    attempts = [r for r in store.records(run_id, "workflow_attempts") if r["task_id"] == task_id]
    folder = Path(cfg["directory"]) / "tasks" / task_id / f"attempt-{len(attempts)+1:04d}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "response.json"


def submit(store: Store, run_id: str, task_id: str, response: dict, *, path: Path | None = None) -> dict:
    store = scoped_store(store, run_id)
    cfg = config(store, run_id)
    request = store.get(run_id, "workflow_requests", task_id)
    if not request or request["policy_hash"] != _policy():
        raise AuditError("Workflow request is missing or its policy changed")
    if request.get("collection_policy_hash") != collection_source_policy(store, run_id)["policy_hash"]:
        raise AuditError("Collection source availability changed; request a fresh task and preserve the old response")
    previous = store.get(run_id, "workflow_results", task_id)
    if previous and not previous.get("retry"):
        if previous["response_hash"] == digest(response):
            return {"task_id": task_id, "idempotent": True}
        raise AuditError("Response already accepted; retain it and use a new task for changed input")
    destination = response_path(store, run_id, task_id)
    _json(destination, response)
    attempt = {"task_id": task_id, "response": str(destination), "response_hash": digest(response)}
    attempt_id = digest([task_id, str(destination)])
    kind, payload = request["kind"], request["payload"]
    try:
        from .workflow_driver import executor_blocked
        if executor_blocked(request, response):
            store.put(run_id, "workflow_attempts", attempt_id, {**attempt, "status": "EXTERNAL_BLOCKED", "error": response["reason"]})
            old = store.get(run_id, "workflow_execution", task_id) or {}
            store.put(run_id, "workflow_execution", task_id, {**old, "task_id": task_id, "kind": kind,
                "attempts": old.get("attempts", 0), "status": "EXTERNAL_BLOCKED",
                "blocked_code": "EXECUTOR_CONTEXT_LIMIT", "error": response["reason"]}, mutable=bool(old))
            return {"task_id": task_id, "blocked": True, "reason": "EXECUTOR_CONTEXT_LIMIT"}
        if kind == "model":
            envelopes = response.get("results", [response])
            submit_model_results(store, run_id, envelopes, executor=cfg["executor"])
        elif kind == "catalog_draft":
            if response.get("executor") != cfg["executor"]:
                raise AuditError("Catalog draft executor differs from the configured Agent")
            validation = validate_draft(store, run_id, payload["request"], response)
            if validation["errors"]:
                raise AuditError("; ".join(validation["errors"]))
            store.put(run_id, "workflow_drafts", payload["request"]["request_hash"],
                      {"request": payload["request"], "response": response, "validation": validation})
        elif kind == "trigger_classify":
            from .trigger_workflow import accept_assessment
            accept_assessment(store, run_id, request, response)
        else:
            if response.get("request_hash") != request["request_hash"]:
                raise AuditError("Collection response request_hash mismatch")
            source_cases = payload.get("cases", [payload["case"]] if "case" in payload else [])
            if any(store.get(run_id, "cases", c["case_id"]) != c for c in source_cases):
                raise AuditError("Source input changed; request a new collection task")
            if kind == "wiki_check" and payload["wiki_input_hash"] != wiki_plan(store, run_id, payload["case"])["input_hash"]:
                raise AuditError("Wiki source relationships changed; request a new check task")
            outcome = response.get("outcome")
            if outcome not in {"CAPTURED", "FOUND", "NO_MATCH", "BLOCKED"}:
                raise AuditError("Collection outcome must be CAPTURED/FOUND/NO_MATCH/BLOCKED")
            if kind != "fetch" and (response.get("executed") is not True or not all(
                    response.get(k) for k in ("query", "scope", "checked_at", "executed_by", "reason"))):
                raise AuditError("Search needs actual execution, query, scope, time, actor and reason")
            packages = response.get("packages", [])
            if kind in {"wiki_check", "search"}:
                issues = validate_search_trace(payload["case"], response,
                    max_rounds=payload.get("search_guidance", {}).get("max_rounds", 3),
                    required="search_guidance" in payload)
                if issues:
                    raise AuditError("; ".join(issues))
            if outcome in {"FOUND", "CAPTURED"} and not packages:
                raise AuditError("A captured result requires evidence packages")
            if kind == "fetch" and (len(packages) != 1 or not same_resource(packages[0]["url"], payload["url"])):
                raise AuditError("Fetch must return one package for the requested URL, including access failures")
            for package in packages:
                EvidencePackage.model_validate(package)
                if (source_policy := collection_source_policy(store, run_id))["explicit_override"] and resource_kind(snapshot=package) not in source_policy["collection_sources"]:
                    raise AuditError("Collected resource is outside the explicitly enabled sources")
                errors = capture_quality(package, require_observation=True)["errors"]
                if errors:
                    raise AuditError("; ".join(errors))
            if payload.get("source_lookup"):
                from .trigger_workflow import validate_source_lookup
                validate_source_lookup(payload, response)
            for child in response.get("linked_packages", []):
                package = child.get("package", {})
                EvidencePackage.model_validate(package)
                navigation = child.get("navigation_quote", "")
                child_cases = child.get("case_ids", [])
                if (kind != "fetch" or not navigation or navigation not in packages[0].get("text", "")
                        or not package.get("url") or package["url"] not in navigation
                        or not child_cases or set(child_cases) - set(payload["case_ids"])):
                    raise AuditError("Linked capture requires an exact parent navigation quote and applicable selected case IDs")
                errors = capture_quality(package, require_observation=True)["errors"]
                if errors:
                    raise AuditError("; ".join(errors))
            snapshots = []
            for package in packages:
                quality = capture_quality(package, require_observation=True)
                if quality["errors"]:
                    raise AuditError("; ".join(quality["errors"]))
                if kind == "wiki_check" and resource_kind(snapshot=package) != "WIKI":
                    raise AuditError("Wiki check returned a non-Wiki resource")
                package = {**package, "case_ids": payload["case_ids"]}
                if kind != "fetch":
                    package.update(origin="SEARCH_DISCOVERED", record_discovery=True, discovery_query=response["query"])
                snapshots.append(store.ingest_evidence(run_id, package, path.parent if path else None))
            for child in response.get("linked_packages", []):
                package = child.get("package", {})
                child_cases = child.get("case_ids", [])
                package = {**package, "case_ids": child_cases, "origin": "LINK_DISCOVERED", "record_discovery": True,
                           "discovered_from_url": payload["url"], "discovery_query": "INDEX_NAVIGATION"}
                store.ingest_evidence(run_id, package, path.parent if path else None)
            if kind == "wiki_check":
                record_wiki_check(store, run_id, payload["case"]["case_id"], outcome=outcome,
                    query=response["query"], scope=response["scope"], checked_at=response["checked_at"],
                    executed_by=response["executed_by"], executed=True, reason=response["reason"],
                    snapshot_id=snapshots[0]["snapshot_id"] if snapshots else None)
            if payload.get("source_lookup"):
                from .trigger_workflow import record_source_lookup
                record_source_lookup(store, run_id, payload, response, snapshots)
    except Exception as exc:
        store.put(run_id, "workflow_attempts", attempt_id, {**attempt, "status": "REJECTED", "error": str(exc)})
        raise
    store.put(run_id, "workflow_attempts", attempt_id, {**attempt, "status": "ACCEPTED"})
    store.put(run_id, "workflow_results", task_id, {**attempt, "response": response}, mutable=bool(previous))
    from .workflow_driver import _auth_required, auth_site
    if _auth_required(response):
        site = auth_site(request, response)
        old = store.get(run_id, "workflow_auth", site)
        if not old or old.get("status") != "WAITING_AUTH":
            record = {"site": site, "status": "WAITING_AUTH", "task_id": task_id,
                      "reason": response.get("reason", "Complete login in the existing Edge session")}
            store.put(run_id, "workflow_auth", site, record, mutable=bool(old))
            store.event(run_id, "workflow_auth_handoff", record)
    return {"task_id": task_id, "accepted": True}


def export(store: Store, run_id: str) -> dict:
    store = scoped_store(store, run_id)
    from .exporters import export_workbook_xlsx
    from .ranking_report import build_ranked_workbook
    cfg = config(store, run_id)
    if cfg.get("purpose", "").startswith("TRIGGER_"):
        from .trigger_workflow import export as trigger_export
        return trigger_export(store, run_id)
    cases = store.records(run_id, "cases")
    checks = {c["case_id"]: wiki_plan(store, run_id, c) for c in cases}
    proposals = []
    for value in store.records(run_id, "workflow_drafts"):
        try:
            validation = validate_draft(store, run_id, value["request"], value["response"])
        except (ValueError, KeyError):
            continue
        if not validation["errors"]:
            # Per-case Agent responses may each use P1. Give the projection a
            # stable global identity without rewriting the original response.
            proposals.extend({**p, "proposal_id": value["request"]["task_id"] + ":" + p["proposal_id"]}
                             for p in value["response"]["proposals"])
    data = report_data(store, run_id)
    state = store.get(run_id, "workflow_state", "current") or {}
    pending_wiki = sum(check["status"] not in {"FOUND", "NO_MATCH"} for check in checks.values())
    status = "COMPLETE" if data["validation"].get("complete") and not pending_wiki \
        and not state.get("block_ids") and not state.get("task_ids") else "COMPLETE_WITH_PENDING"
    data["validation"]["status"] = status
    workbook = build_ranked_workbook(data, wiki_checks=checks, proposals=proposals)
    for block_id in state.get("block_ids", []):
        block = store.get(run_id, "workflow_blocks", block_id)
        table = next(s for s in workbook["sheets"] if s["name"] == "异常与待处理")
        values = {"类型": block["reason"], "说明": json.dumps(block.get("details", block.get("input_budget", {})), ensure_ascii=False),
                  "case_id": ";".join(block["case_ids"]), "需人工裁决": "否"}
        table["rows"].append([values.get(column, "") for column in table["columns"]])
    output = Path(cfg["directory"]) / "output"
    output.mkdir(parents=True, exist_ok=True)
    # Only the final workbook is delivered; adapter JSON/previews are temporary.
    with tempfile.TemporaryDirectory(prefix="faultaudit-xlsx-", dir=Path(cfg["directory"])) as scratch:
        source = Path(scratch) / "workbook_data.json"
        source.write_text(json.dumps(workbook, ensure_ascii=False), encoding="utf-8")
        result = export_workbook_xlsx(source, Path(scratch) / WORKBOOK_NAME)
        Path(result["xlsx"]).replace(output / WORKBOOK_NAME)
    result.update(xlsx=str(output / WORKBOOK_NAME), case_count=len(cases), wiki_pending=pending_wiki,
                  xlsx_sha256=digest((output / WORKBOOK_NAME).read_bytes()),
                  status=status)
    store.event(run_id, "workflow_export", result)
    return result


def drive(store: Store, run_id: str, command: list[str], *, max_rounds=32, workers=2,
          max_attempts=2, timeout=300, browser_timeout=None) -> dict:
    from .workflow_driver import drive as run
    return run(store, run_id, command, max_rounds=max_rounds, workers=workers,
               max_attempts=max_attempts, timeout=timeout, browser_timeout=browser_timeout)


def retry(store: Store, run_id: str, task_id: str) -> dict:
    from .workflow_driver import reset_execution
    task = store.get(run_id, "workflow_requests", task_id)
    execution = store.get(run_id, "workflow_execution", task_id) or {}
    if task and task["kind"] in {"model", "catalog_draft", "trigger_classify"} and execution.get("blocked_code") == "EXECUTOR_CONTEXT_LIMIT":
        reset_execution(store, run_id, task_id)
        old = store.get(run_id, "workflow_execution", task_id)
        store.put(run_id, "workflow_execution", task_id, {**old, "blocked_code": None}, mutable=True)
        return {"task_id": task_id, "retry": True}
    if not task or task["kind"] not in {"fetch", "wiki_check", "search"}:
        raise AuditError("Retry applies to collection tasks; changed model decisions need fresh inputs")
    store.put(run_id, "workflow_results", task_id, {"task_id": task_id, "retry": True}, mutable=True)
    reset_execution(store, run_id, task_id)
    from .workflow_driver import _site
    site = _site({"kind": task["kind"]}, task)
    for auth in store.records(run_id, "workflow_auth"):
        if auth.get("task_id") == task_id or site and auth.get("site") == site:
            store.event(run_id, "workflow_auth_retry", auth)
            store.put(run_id, "workflow_auth", auth["site"], {**auth, "status": "RETRY"}, mutable=True)
    return {"task_id": task_id, "retry": True}


def configure_collection(store: Store, run_id: str, sources: list[str], *, wiki_policy="NOT_SUPPORTED", reason: str) -> dict:
    """Record an explicit user-selected availability scope without faking reads."""
    from .evidence_plan import SEARCH_SOURCES
    old = config(store, run_id)
    if (not sources or len(sources) != len(set(sources)) or set(sources) - set(SEARCH_SOURCES)
            or not reason.strip() or wiki_policy not in {"REQUIRED", "NOT_SUPPORTED"}
            or wiki_policy == "NOT_SUPPORTED" and "WIKI" in sources
            or wiki_policy == "REQUIRED" and "WIKI" not in sources):
        raise AuditError("Select unique supported sources and an explicit consistent Wiki policy with a reason")
    value = {**old, "collection_sources": sorted(sources), "wiki_policy": wiki_policy,
             "collection_policy_reason": reason}
    if old != value:
        store.put(run_id, "xlsx_workflow", "config", value, mutable=True)
        store.event(run_id, "collection_source_policy_changed", {"previous": old, "current": value})
    policy = {"required_any_sources": sources}
    register_search_policy(store, run_id, policy)
    for case in store.records(run_id, "cases"):
        register_search_policy(store, run_id, policy, case_id=case["case_id"])
    return {"run_id": run_id, **collection_source_policy(store, run_id)}
