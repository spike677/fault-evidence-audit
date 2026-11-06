"""Structured-XLSX workflow: existing core + external Agent + one workbook.

The program owns routing and continuation. Websites and semantic decisions stay
with the configured Agent, through files or an argv-based process adapter.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .bridge import CodexJudge, OpenCodeJudge, export_model_tasks, policy_fingerprint, submit_model_results
from .catalog_drafts import prepare_draft, validate_draft
from .evidence_plan import register_search_policy, resource_kind
from .importers import import_cases, import_catalog
from .input_budget import InputTooLarge, finalize_model_task
from .pipeline import evidence_plan, execute, fetch_tasks, import_into, report_data
from .store import AuditError, Store, canonical_url, digest
from .wiki_checks import record_wiki_check, wiki_plan

RULE_VERSION = "structured-xlsx-1"
WORKBOOK_NAME = "故障整理及模式库建议.xlsx"


def config(store: Store, run_id: str) -> dict:
    value = store.get(run_id, "xlsx_workflow", "config")
    if not value:
        raise AuditError("Start a structured XLSX workflow first")
    return value


def start(store: Store, source: Path, catalog: Path, work_root: Path, *, executor="opencode",
          source_kind="LEGACY_TABLE", catalog_sheets=None, expected_catalog_count=None,
          catalog_scope="UNSPECIFIED", run_id=None) -> dict:
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
    import_into(store, run_id, cases)
    import_into(store, run_id, items, catalog=True)
    directory = (work_root / run_id).resolve()
    if directory.is_relative_to(store.root):
        raise AuditError("Workflow files must be outside state")
    value = old or {"run_id": run_id, "directory": str(directory), "executor": executor,
                    "source_hash": cases["documents"][0]["source_sha256"], "rule_version": RULE_VERSION}
    if not old:
        store.put(run_id, "xlsx_workflow", "config", value)
        register_search_policy(store, run_id, {"required_sources": ["WIKI"]})
    return {**value, "case_count": len(cases["cases"]), "catalog_count": len(items["items"])}


def _policy() -> str:
    from . import wiki_checks
    return digest({"core": policy_fingerprint(), "workflow": digest(Path(__file__).read_bytes()),
                   "wiki": digest(Path(wiki_checks.__file__).read_bytes())})


def _json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _request(store, run_id, cfg, kind, payload, instructions, priority) -> dict | None:
    try:
        request = finalize_model_task({"kind": kind, "run_id": run_id, "policy_hash": _policy(),
            "instructions": instructions, "payload": payload})
    except InputTooLarge as exc:
        block = {"kind": kind, "case_ids": payload.get("case_ids", []), "reason": "INPUT_TOO_LARGE",
                 "input_budget": exc.details, "policy_hash": _policy()}
        store.put(run_id, "workflow_blocks", digest(block), block)
        return {"blocked": True, "block_id": digest(block), **block}
    task_id = request["task_id"]
    store.put(run_id, "workflow_requests", task_id, request)
    path = Path(cfg["directory"]) / "tasks" / task_id / "request.json"
    _json(path, request)
    done = store.get(run_id, "workflow_results", task_id)
    if done and not done.get("retry"):
        return None
    return {"task_id": task_id, "kind": kind, "priority": priority, "request": str(path)}


def next_tasks(store: Store, run_id: str) -> dict:
    cfg = config(store, run_id)
    cases = store.records(run_id, "cases")
    checks = {case["case_id"]: wiki_plan(store, run_id, case) for case in cases}
    # A bounded NO_MATCH fulfills checking, not finding. Release only this
    # workflow's temporary Wiki selection condition for the individual case.
    for cid, check in checks.items():
        register_search_policy(store, run_id,
            {} if check["status"] == "NO_MATCH" else {"required_sources": ["WIKI"]}, case_id=cid)
    tasks, blocks = [], []
    def add(kind, payload, text, priority):
        value = _request(store, run_id, cfg, kind, payload, text, priority)
        if value and value.get("blocked"):
            blocks.append(value["block_id"])
        elif value:
            tasks.append(value)
    for done in store.records(run_id, "workflow_results"):
        if not done.get("retry"):
            continue
        old = store.get(run_id, "workflow_requests", done["task_id"])
        if old and old["policy_hash"] == _policy():
            case = old["payload"].get("case")
            if old["kind"] == "wiki_check" and old["payload"]["wiki_input_hash"] != checks[case["case_id"]]["input_hash"]:
                continue
            path = Path(cfg["directory"]) / "tasks" / old["task_id"] / "request.json"
            tasks.append({"task_id": old["task_id"], "kind": old["kind"], "priority": 0, "request": str(path)})
    for case in cases:
        check = checks[case["case_id"]]
        if check["status"] == "SEARCH_REQUIRED":
            add("wiki_check", {"case": case, "case_ids": [case["case_id"]], "wiki_input_hash": check["input_hash"],
                               "wiki_task_id": check["task_id"]},
                "Search Wiki first within a stated scope. Return {request_hash, outcome: FOUND|NO_MATCH|BLOCKED, "
                "executed:true, query, scope, checked_at (ISO timezone), executed_by, reason, packages:[]}. "
                "FOUND requires actual captured Wiki EvidencePackage(s); they remain candidates until comparison. "
                "NO_MATCH describes only this bounded search; auth failure is BLOCKED. Never invent a login or search.", 0)
    for item in fetch_tasks(store, run_id)["fetch_tasks"]:
        relevant = [case for case in cases if case["case_id"] in item["case_ids"]]
        add("fetch", {"url": item["url"], "case_ids": item["case_ids"], "references": item["references"], "cases": relevant},
            "Read this supplied URL using the site's actual tools. Return {request_hash, outcome: CAPTURED|BLOCKED, "
            "packages:[EvidencePackage]}. Preserve body, comments, applicable issue and needed Diff, exact capture "
            "scope and access failures. Use the requested URL; no expansion to fill evidence types.",
            0 if resource_kind({"url": item["url"]}) == "WIKI" else 2)
    plan = evidence_plan(store, run_id)
    for row in plan["cases"]:
        check = checks[row["case_id"]]
        if row["search_control"]["search_allowed"] and check["status"] in {"FOUND", "NO_MATCH"}:
            case = next(c for c in cases if c["case_id"] == row["case_id"])
            prior_ids = set(row["excluded_candidate_judgment_ids"] + row["insufficient_candidate_judgment_ids"])
            prior = [{"judgment_id": j["judgment_id"],
                      "url": store.get(run_id, "snapshots", j["snapshot_id"])["url"], "reason": j["short_reason"]}
                     for j in store.records(run_id, "judgments") if j["judgment_id"] in prior_ids]
            add("search", {"case": case, "case_ids": [case["case_id"]], "search_policy": row["search_control"]["policy"],
                "excluded_candidate_judgment_ids": row["excluded_candidate_judgment_ids"],
                "insufficient_candidate_judgment_ids": row["insufficient_candidate_judgment_ids"], "previous_candidates": prior},
                "Search for evidence of this specific fault, GitHub then GitCode/Gitee/CodeHub/DTS as applicable. "
                "Stop after one adequate candidate; do not fill all source types. Return {request_hash, "
                "outcome: FOUND|NO_MATCH|BLOCKED, executed:true, query, scope, checked_at, executed_by, reason, "
                "packages:[captured EvidencePackage]}. Keyword matches are not confirmed incidents.", 2)
    judge = CodexJudge(store, run_id) if cfg["executor"] == "codex" else OpenCodeJudge(store, run_id)
    execute(store, run_id, judge, mode=cfg["executor"], model_id=cfg["executor"] + "-managed")
    for task in export_model_tasks(store, run_id, executor=cfg["executor"])["tasks"]:
        add("model", {"task": task},
            "Execute the complete enclosed model task using its instructions and expected_contract. Return its "
            "standard result envelope with original run/task/request hash and actual producer metadata. "
            "The inner task, not this dispatch wrapper, supplies the response identity. Do not invent ACCEPT.", 3)
    if not tasks:
        for case in cases:
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
    cfg = config(store, run_id)
    request = store.get(run_id, "workflow_requests", task_id)
    if not request or request["policy_hash"] != _policy():
        raise AuditError("Workflow request is missing or its policy changed")
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
            if outcome in {"FOUND", "CAPTURED"} and not packages:
                raise AuditError("A captured result requires evidence packages")
            if kind == "fetch" and (len(packages) != 1 or canonical_url(packages[0]["url"]) != canonical_url(payload["url"])):
                raise AuditError("Fetch must return one package for the requested URL, including access failures")
            snapshots = []
            for package in packages:
                if kind == "wiki_check" and resource_kind(snapshot=package) != "WIKI":
                    raise AuditError("Wiki check returned a non-Wiki resource")
                package = {**package, "case_ids": payload["case_ids"]}
                if kind != "fetch":
                    package.update(origin="SEARCH_DISCOVERED", record_discovery=True, discovery_query=response["query"])
                snapshots.append(store.ingest_evidence(run_id, package, path.parent if path else None))
            if kind == "wiki_check":
                record_wiki_check(store, run_id, payload["case"]["case_id"], outcome=outcome,
                    query=response["query"], scope=response["scope"], checked_at=response["checked_at"],
                    executed_by=response["executed_by"], executed=True, reason=response["reason"],
                    snapshot_id=snapshots[0]["snapshot_id"] if snapshots else None)
    except Exception as exc:
        store.put(run_id, "workflow_attempts", attempt_id, {**attempt, "status": "REJECTED", "error": str(exc)})
        raise
    store.put(run_id, "workflow_attempts", attempt_id, {**attempt, "status": "ACCEPTED"})
    store.put(run_id, "workflow_results", task_id, {**attempt, "response": response}, mutable=bool(previous))
    return {"task_id": task_id, "accepted": True}


def export(store: Store, run_id: str) -> dict:
    from .exporters import export_workbook_xlsx
    from .ranking_report import build_ranked_workbook
    cfg = config(store, run_id)
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
        values = {"类型": block["reason"], "说明": json.dumps(block["input_budget"], ensure_ascii=False),
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


def drive(store: Store, run_id: str, command: list[str], *, max_rounds=32) -> dict:
    from .agent_adapter import run_agent
    for _ in range(max_rounds):
        step = next_tasks(store, run_id)
        if not step["tasks"]:
            return export(store, run_id)
        for task in step["tasks"]:
            destination = Path(task["response"])
            try:
                body = json.loads(destination.read_text(encoding="utf-8-sig")) if destination.exists() else run_agent(
                    command, Path(task["request"]), destination)
            except AuditError as exc:
                store.put(run_id, "workflow_attempts", digest(str(destination)), {"task_id": task["task_id"],
                    "response": str(destination), "status": "AGENT_FAILED", "error": str(exc)})
                raise
            submit(store, run_id, task["task_id"], body, path=destination)
    raise AuditError("Workflow round limit reached; state and task files retained for resume")


def retry(store: Store, run_id: str, task_id: str) -> dict:
    task = store.get(run_id, "workflow_requests", task_id)
    if not task or task["kind"] not in {"fetch", "wiki_check", "search"}:
        raise AuditError("Retry applies to collection tasks; changed model decisions need fresh inputs")
    store.put(run_id, "workflow_results", task_id, {"task_id": task_id, "retry": True}, mutable=True)
    return {"task_id": task_id, "retry": True}
