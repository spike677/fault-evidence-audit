"""File task bridge: an external executor owns model execution and credentials.

The core only emits immutable requests and validates imported results. Producer
metadata is an executor's audit declaration, not proof of provider routing.
"""
from __future__ import annotations

from . import contracts, gates, model, prompts, input_budget
from . import store as store_module
from .contracts import EvidenceSummary
from .model import PendingModelResult, validate_task_result
from .store import AuditError, Store, digest
from pathlib import Path

SCHEMA_VERSION = "1.0"
EXECUTORS = {"opencode", "codex"}


def _executor(value: str) -> str:
    if value not in EXECUTORS:
        raise AuditError("Executor must be opencode or codex")
    return value


def policy_fingerprint() -> str:
    from .pipeline import RULE_VERSION
    source_hash = digest(b"".join(Path(module.__file__).read_bytes() for module in
                                  (contracts, gates, model, prompts, store_module, input_budget))
                         + Path(__file__).read_bytes() + Path(__file__).with_name("pipeline.py").read_bytes())
    return digest({"source_hash": source_hash, "input_budget_policy": input_budget.budget_policy(),
                   "prompt_version": prompts.PROMPT_VERSION, "rule_version": RULE_VERSION})


def _snapshot_input_scope(snapshot: dict) -> dict:
    declared = snapshot.get("input_scope")
    if isinstance(declared, dict):
        return dict(declared)
    return {"scope": "UNSPECIFIED", "provided_segment_ids": [s["segment_id"] for s in snapshot.get("segments", [])],
            "provided_chars": len(snapshot.get("text", "")), "retrieval_status": snapshot.get("status")}


def _snapshot_payload(snapshot: dict) -> dict:
    return {**prompts.snapshot_data(snapshot), "input_scope": _snapshot_input_scope(snapshot)}


def _check_current(store: Store, run_id: str, task: dict) -> None:
    executor = _executor(task.get("executor", "opencode"))
    if task["run_id"] != run_id or task["policy_hash"] != policy_fingerprint():
        raise AuditError("Model task belongs to another run or an obsolete core policy")
    unsigned = {key: value for key, value in task.items() if key != "request_hash"}
    if digest(unsigned) != task["request_hash"] or digest(task["payload"]) != task["input_hash"]:
        raise AuditError("Stored model request integrity mismatch")
    parent = next((t for t in store.tasks(run_id) if t["task_id"] == task["pipeline_task_id"]), None)
    if not parent or parent["status"] in {"STALE", "BLOCKED"}:
        raise AuditError("Model task is stale, blocked, or its pipeline dependency is missing")
    try:
        measurement = input_budget.check_input_budget(task)
    except model.ModelError as exc:
        raise AuditError(str(exc)) from exc
    recorded = task.get("input_budget", {})
    if any(recorded.get(key) != measurement[key] for key in ("chars", "budget", "scope", "serialization")):
        raise AuditError("Model task input budget metadata does not match its complete serialized request")
    payload = task["payload"]
    snapshot = payload.get("snapshot")
    if snapshot:
        active = {s["snapshot_id"]: s for s in store.active_snapshots(run_id)}
        saved = active.get(snapshot["snapshot_id"])
        if not saved:
            raise AuditError("Model task refers to an obsolete snapshot")
        problems = store.verify_snapshot(saved)
        if problems:
            raise AuditError("; ".join(problems))
        original_segments = {s["segment_id"]: s["text"] for s in saved["segments"]}
        if any(original_segments.get(s["segment_id"]) != s["text"] for s in snapshot["segments"]):
            raise AuditError("Task segment does not match its saved snapshot")
    case = payload.get("case")
    if case and store.get(run_id, "cases", case["case_id"]) != case:
        raise AuditError("Model task source case no longer matches the immutable input")
    if task["kind"] == "compare":
        from .pipeline import current_summaries
        current = [summary for summary in current_summaries(store, run_id)
                   if summary["snapshot_id"] == snapshot["snapshot_id"] and summary["model_mode"] == executor
                   and summary.get("requested_model_id", summary["model_id"]) == executor + "-managed"]
        summary_hash = digest(payload["summary"])
        if len(current) != 1 or digest({key: current[0][key] for key in EvidenceSummary.model_fields}) != summary_hash:
            raise AuditError("Model task independent summary dependency is stale")
    if task["kind"] == "catalog":
        if digest(payload["items"]) != digest(store.records(run_id, "catalog")):
            raise AuditError("Model task catalog version is stale")
        from .pipeline import current_judgments
        current = [j for j in current_judgments(store, run_id, mode=executor, model_id=executor + "-managed")
                   if j["case_id"] == case["case_id"] and j.get("review_status") != "REJECT"]
        if digest(current) != digest(payload["judgments"]):
            raise AuditError("Model task judgment/review dependencies are stale")


class OpenCodeJudge:
    """Create a request or consume a verified response from this executor."""
    executor = "opencode"
    model_id = "opencode-managed"

    def __init__(self, store: Store, run_id: str):
        self.store, self.run_id = store, run_id
        self.calls: list[dict] = []
        self.pipeline_task_id = ""
        self.execution_signature = digest({"policy": policy_fingerprint(), "executor": self.executor})

    def _request(self, kind: str, payload: dict, instructions: str, expected_contract: str) -> dict:
        if not self.pipeline_task_id:
            raise AuditError(self.executor + " bridge needs a pipeline task context")
        task = {"schema_version": SCHEMA_VERSION, "run_id": self.run_id, "kind": kind,
                "pipeline_task_id": self.pipeline_task_id, "policy_hash": policy_fingerprint(),
                "input_hash": digest(payload), "payload": payload, "instructions": instructions,
                "expected_contract": expected_contract,
                "executor": self.executor, "model_service": self.executor,
                "model_role": "Evidence judge; actual provider/model is reported by the executing " + self.executor + " session"}
        task = input_budget.finalize_model_task(task)
        self.store.put(self.run_id, "model_tasks", task["task_id"], task)
        response = self.store.get(self.run_id, "model_results", task["task_id"])
        if not response:
            raise PendingModelResult(task_id=task["task_id"], operation=kind)
        _check_current(self.store, self.run_id, task)
        self.calls.append({"executor": self.executor, "operation": kind, "task_id": task["task_id"],
                           "request_hash": task["request_hash"], "producer_reported": response["producer"],
                           "status": "IMPORTED_RESULT", "network_requested_by_core": False})
        return response["result"]

    def summarize(self, snapshot: dict) -> dict:
        messages = prompts.summary_messages(snapshot)
        return self._request("summarize", {"snapshot": _snapshot_payload(snapshot),
                                          "input_scope": _snapshot_input_scope(snapshot)},
                             messages[0]["content"], "EvidenceSummary")

    def compare(self, case: dict, snapshot: dict, summary: dict) -> dict:
        summary = {key: summary[key] for key in EvidenceSummary.model_fields}
        messages = prompts.comparison_messages(case, snapshot, summary)
        return self._request("compare", {"case": case, "snapshot": _snapshot_payload(snapshot), "summary": summary,
                                        "input_scope": _snapshot_input_scope(snapshot)},
                             messages[0]["content"], "Judgment")

    def map_catalog(self, case: dict, judgments: list[dict], items: list[dict]) -> dict:
        messages = prompts.catalog_messages(case, judgments, items)
        return self._request("catalog", {"case": case, "judgments": judgments, "items": items,
                                        "input_scope": {"scope": "FULL_CATALOG", "catalog_item_count": len(items),
                                                        "provided_item_ids": [item["item_id"] for item in items],
                                                        "catalog_hash": digest(items)}},
                             messages[0]["content"], "CatalogResponse")


class CodexJudge(OpenCodeJudge):
    """The same file protocol, with Codex producer identity kept explicit."""
    executor = "codex"
    model_id = "codex-managed"


def export_model_tasks(store: Store, run_id: str, *, executor: str = "opencode") -> dict:
    executor = _executor(executor)
    tasks, stale = [], []
    for task in store.records(run_id, "model_tasks"):
        if task.get("executor", "opencode") != executor:
            continue
        if store.get(run_id, "model_results", task["task_id"]):
            continue
        try:
            _check_current(store, run_id, task)
        except AuditError:
            stale.append(task["task_id"])
            continue
        tasks.append(task)
    return {"schema_version": SCHEMA_VERSION, "run_id": run_id, "tasks": tasks,
            "stale_tasks_excluded": stale,
            "executor": executor,
            "execution_owner": executor + "; no model endpoints or credentials are configured in this core"}


def submit_model_results(store: Store, run_id: str, envelopes: list[dict], *, executor: str = "opencode") -> dict:
    executor = _executor(executor)
    prepared, idempotent = [], 0
    for envelope in envelopes:
        if envelope.get("schema_version") != SCHEMA_VERSION or envelope.get("run_id") != run_id:
            raise AuditError("Model result schema_version or run_id mismatch")
        task_id = envelope.get("task_id", "")
        task = store.get(run_id, "model_tasks", task_id)
        if not task or envelope.get("request_hash") != task["request_hash"]:
            raise AuditError("Unknown task or request_hash mismatch; use the core's exported request")
        if task.get("executor", "opencode") != executor:
            raise AuditError("Model task belongs to another executor")
        _check_current(store, run_id, task)
        producer = envelope.get("producer", {})
        version_field = executor + "_version"
        if not isinstance(producer, dict) or producer.get("executor") != executor or any(
            not isinstance(producer.get(k), str) or not producer[k].strip()
            for k in (version_field, "provider", "model", "session_id")
        ):
            raise AuditError("Producer must identify " + executor + " version, reported provider/model and session")
        result = envelope.get("result")
        if not isinstance(result, dict):
            raise AuditError("Model result must be a structured object")
        if result.get("model_mode") not in {None, executor} or result.get("model_id") not in {None, producer["model"]}:
            raise AuditError("Result model metadata disagrees with its " + executor + " producer")
        value = {**result, "model_mode": executor, "model_id": producer["model"]}
        payload = task["payload"]
        snapshot_view = payload.get("snapshot")
        if snapshot_view is not None:
            snapshot_view = {**snapshot_view, "input_scope": payload.get("input_scope", snapshot_view.get("input_scope", {}))}
        checked = validate_task_result(task["kind"], value, snapshot=snapshot_view,
                                       case=payload.get("case"), judgments=payload.get("judgments"),
                                       items=payload.get("items"))
        if task["kind"] == "compare":
            from .pipeline import gate_judgment
            saved_snapshot = store.get(run_id, "snapshots", payload["snapshot"]["snapshot_id"])
            actual_view = {**saved_snapshot, "text": snapshot_view["text"], "segments": snapshot_view["segments"],
                           "input_scope": snapshot_view["input_scope"]}
            gate_judgment(payload["case"], actual_view, checked)
        saved = {"schema_version": SCHEMA_VERSION, "run_id": run_id, "task_id": task_id,
                 "request_hash": task["request_hash"], "producer": producer, "result": checked}
        existing = store.get(run_id, "model_results", task_id)
        if existing:
            if existing != saved:
                raise AuditError("A different result already exists; preserve the first response and use a new run for rejudgment")
            idempotent += 1
        else:
            if any(p["task_id"] == task_id and p != saved for p in prepared):
                raise AuditError("Batch contains conflicting results for the same task")
            if not any(p["task_id"] == task_id for p in prepared):
                prepared.append(saved)
    # Validate the complete batch before committing any response.
    for value in prepared:
        store.put(run_id, "model_results", value["task_id"], value)
        store.event(run_id, executor + "_result_received", {"task_id": value["task_id"],
                                                        "request_hash": value["request_hash"],
                                                        "producer_reported": value["producer"]})
    return {"run_id": run_id, "accepted": len(prepared), "idempotent": idempotent}
