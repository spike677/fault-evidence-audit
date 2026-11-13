"""Cross-platform CLI. Collectors return packages; this process owns audit state."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
from pathlib import Path

from . import __version__


def write_json(value, path: Path | None = None):
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def doctor() -> dict:
    versions = {}
    for package in ("pydantic", "openpyxl"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    core_ready = bool(versions["pydantic"] and versions["pydantic"].split(".")[0] == "2")
    return {"version": __version__, "python": sys.version.split()[0], "executable": sys.executable,
            "platform": platform.platform(), "dependencies": versions,
            "core_ready": core_ready, "xlsx_import_ready": bool(versions["openpyxl"]),
            "dependency_help": "Install requirements.txt with this Python executable" if not core_ready else None,
            "model_service": {"owner": "opencode", "transport": "file-task-bridge",
                              "supported_executors": ["opencode", "codex"],
                              "credentials_in_core": False, "network_execution_in_core": False},
            "collection": "EvidencePackage import; live internal connectors must be supplied on site",
            "opencode": "Inspect the actual OpenChamber server; PATH version alone is insufficient",
            "xlsx": "Optional @oai/artifact-tool Node adapter; HTML/JSON/TSV require no Node"}


def demo(store: Store, output: Path) -> dict:
    """Use synthetic documents, never purport to have fetched private resources."""
    from .importers import import_cases, import_catalog
    from .pipeline import execute, import_into, report_data
    from .model import MockJudge
    output.mkdir(parents=True, exist_ok=True)
    rows = [
        {"统一ID": "DEMO-CASE-DELTA", "来源": "合成周报 batch-alpha", "客户/模型": "合成 Model-X",
         "问题描述": "[合成] 输出 乱码，排查 AllReduce", "算子": "all_reduce",
         "根因": "[合成] ExampleRuntime AllReduce 精度问题", "wiki": "https://example.invalid/wiki/dequant"},
        {"统一ID": "DEMO-CASE-ETA", "来源": "合成周报 batch-gamma", "客户/模型": "合成 Model-X",
         "问题描述": "[合成] Example Attention 输出 乱码", "算子": "Example Attention",
         "根因": "[合成] scale metadata 读取问题", "wiki": "https://example.invalid/wiki/shared"},
        {"统一ID": "DEMO-CASE-THETA", "来源": "合成周报 batch-delta", "客户/模型": "合成 Model-X",
         "问题描述": "[合成] 确定性固定不住", "算子": "example_cache", "根因": "[合成] cache update ordering",
         "wiki": "https://example.invalid/wiki/shared", "DTS": "https://example.invalid/dts/scan"},
        {"统一ID": "DEMO-CASE-ZETA", "来源": "合成周报 batch-epsilon", "客户/模型": "合成 ExampleRunner",
         "问题描述": "[合成] 批处理异常，单条处理正常", "算子": "example_embedding / example_cache",
         "根因": "[合成] save/restore cached indices", "DTS": "https://example.invalid/dts/scan"},
        {"统一ID": "DEMO-NO-LINK", "问题描述": "[合成] 无链接问题必须保留", "根因": "待定位"},
    ]
    source_path = output / "synthetic_cases.json"
    write_json(rows, source_path)
    catalog_path = output / "synthetic_catalog.json"
    write_json([{"item_id": "DEMO-CAT-1", "description": "[合成] AllReduce precision", "operator": "all_reduce", "mechanism": "rounding"},
                {"item_id": "DEMO-CAT-2", "description": "[合成] quant alignment", "operator": "example_quantize", "mechanism": "alignment"}], catalog_path)
    run_id = store.create_run({"is_synthetic": True, "purpose": "Offline workflow regression only; no semantic verification"})
    import_into(store, run_id, import_cases(source_path, source_kind="ORIGINAL_WEEKLY"))
    import_into(store, run_id, import_catalog(catalog_path), catalog=True)
    evidence = [
        {"url": "https://example.invalid/wiki/dequant", "title": "合成量化算子问题",
         "text": "合成资料，非真实Wiki。\n算子：example_quantize\n根因：示例量化参数不匹配。\n替换小算子后正常。"},
        {"url": "https://example.invalid/wiki/shared", "title": "合成多问题复盘",
         "text": "合成资料，非真实Wiki。\n# 问题一\n算子：Example Attention\n根因：scale metadata读取。\n# 问题二\n算子：example_cache\n根因：cache update ordering影响确定性。"},
        {"url": "https://example.invalid/dts/scan", "title": "合成扫描工单",
         "text": "合成资料，非真实DTS。\n此条为自动扫描发现，目前可见内容没有客户复现、模型、save/restore或修复结论。"},
    ]
    for i, package in enumerate(evidence):
        package.update({"status": "COMPLETE", "components": {"body": "COMPLETE"}, "is_synthetic": True,
                        "retrieved_by": "synthetic-fixture"})
        write_json(package, output / f"synthetic_evidence_{i+1}.json")
        store.ingest_evidence(run_id, package)
    result = execute(store, run_id, MockJudge(), mode="mock", model_id="mock-conservative-v1")
    from .exporters import export_report
    outputs = export_report(report_data(store, run_id), output / "report")
    return {"run_id": run_id, "validation": result, "outputs": outputs,
            "notice": "SYNTHETIC MOCK DEMO: no private pages were fetched and no DeepSeek API was called"}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="faultaudit", description="Fault evidence audit: preserve sources, cite text, expose uncertainty")
    p.add_argument("--state", default=".faultaudit", help="Directory containing SQLite and immutable content snapshots")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    from .precision_cli import add_parser as precision_parser
    precision_parser(sub)
    sub.add_parser("doctor")
    imp = sub.add_parser("import")
    imp.add_argument("--input", type=Path, required=True)
    imp.add_argument("--source-kind", choices=["LEGACY_TABLE", "ORIGINAL_WEEKLY", "ORIGINAL_OBP"], default="LEGACY_TABLE")
    imp.add_argument("--catalog", type=Path)
    imp.add_argument("--catalog-sheet", action="append", help="Exact catalog sheet name; repeat to select multiple sheets")
    imp.add_argument("--catalog-scope", default="UNSPECIFIED", help="Frozen catalog scope, for example INFERENCE or TRAINING")
    imp.add_argument("--expected-catalog-count", type=int, help="Reject the import if the selected catalog size differs")
    imp.add_argument("--run", help="Append inputs to an existing run; same file rows are idempotent")
    evidence = sub.add_parser("ingest-evidence")
    evidence.add_argument("--run", default="latest")
    evidence.add_argument("--package", type=Path, required=True)
    fetch = sub.add_parser("fetch-tasks")
    fetch.add_argument("--run", default="latest")
    fetch.add_argument("--out", type=Path)
    index = sub.add_parser("evidence-index", help="Show every case citing each URL and its individual judgment")
    index.add_argument("--run", default="latest")
    index.add_argument("--url", help="Optionally select one exact evidence URL")
    index.add_argument("--out", type=Path)
    run = sub.add_parser("run")
    run.add_argument("--run", default="latest")
    run.add_argument("--mode", choices=["mock", "opencode", "codex"], required=True)
    run.add_argument("--retry-failed", action="store_true")
    run.add_argument("--resume", action="store_true", help="All runs already resume idempotently; retained for explicit operator intent")
    for name in ("status", "validate", "export", "review"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--run", default="latest")
        if name == "validate":
            cmd.add_argument("--strict", action="store_true", help="Exit 2 when any unresolved item remains")
        elif name == "export":
            cmd.add_argument("--out", type=Path, required=True)
            cmd.add_argument("--xlsx", action="store_true", help="Also run the optional artifact-tool Node exporter")
            cmd.add_argument("--baseline", type=Path, help="Complete pre-round report.json from the same run")
            cmd.add_argument("--round-manifest", type=Path, help="Explicit result/snapshot ID manifest for this round")
        elif name == "review":
            target = cmd.add_mutually_exclusive_group(required=True)
            target.add_argument("--judgment")
            target.add_argument("--mapping", help="Review a catalog mapping by its task_id")
            cmd.add_argument("--verdict", choices=["ACCEPT", "REJECT", "NEEDS_INFO"], required=True)
            cmd.add_argument("--reason", required=True)
            cmd.add_argument("--reviewer", required=True)
    sample = sub.add_parser("demo")
    sample.add_argument("--out", type=Path, required=True)
    schema = sub.add_parser("schemas")
    schema.add_argument("--out", type=Path, required=True)
    requests = sub.add_parser("model-tasks", help="Emit dependency-ready model tasks for OpenCode execution")
    requests.add_argument("--run", default="latest")
    requests.add_argument("--executor", choices=["opencode", "codex"], default="opencode")
    requests.add_argument("--out", type=Path, required=True)
    results = sub.add_parser("submit-model-results", help="Verify returned OpenCode result envelopes")
    results.add_argument("--run", default="latest")
    results.add_argument("--executor", choices=["opencode", "codex"], default="opencode")
    results.add_argument("--file", type=Path, required=True)
    reconciliation = sub.add_parser("reconcile-report", help="Reconcile exported JSON only; never opens SQLite")
    reconciliation.add_argument("--input", type=Path, required=True)
    reconciliation.add_argument("--baseline", type=Path)
    reconciliation.add_argument("--round-manifest", type=Path)
    reconciliation.add_argument("--out", type=Path, required=True)
    plan = sub.add_parser("evidence-plan", help="Read-only preview of selected evidence, search stops and necessary work")
    plan.add_argument("--run", default="latest")
    plan.add_argument("--out", type=Path)
    investigation = sub.add_parser("investigation-plan", help="Read-only issue/PR investigation plan and cited current technical facts")
    investigation.add_argument("--run", default="latest")
    investigation.add_argument("--out", type=Path, required=True)
    catalog_draft = sub.add_parser("catalog-draft", help="Read-only pattern proposals, validation and merge preview")
    draft_commands = catalog_draft.add_subparsers(dest="draft_command", required=True)
    for operation in ("prepare", "validate", "export"):
        draft_cmd = draft_commands.add_parser(operation)
        draft_cmd.add_argument("--run", default="latest")
        draft_cmd.add_argument("--out", type=Path, required=operation != "validate")
        if operation == "prepare":
            draft_cmd.add_argument("--case-id", action="append", required=True, help="Exact internal case ID; repeat to select")
            draft_cmd.add_argument("--expected-additions", type=int, help="Optional exact ADD count; omitted lets Agent decide")
        else:
            draft_cmd.add_argument("--request", type=Path, required=True)
            draft_cmd.add_argument("--draft", type=Path, required=True)
        if operation == "export":
            draft_cmd.add_argument("--xlsx", action="store_true")
    workflow = sub.add_parser("xlsx-workflow", help="Structured XLSX, Wiki-first Agent workflow and one ranked workbook")
    flow = workflow.add_subparsers(dest="flow_command", required=True)
    start = flow.add_parser("start")
    start.add_argument("--input", type=Path, required=True)
    start.add_argument("--catalog", type=Path, required=True)
    start.add_argument("--work-root", type=Path, default=Path("work/runs"))
    start.add_argument("--run")
    start.add_argument("--executor", choices=["opencode", "codex"], default="opencode")
    start.add_argument("--source-kind", choices=["ORIGINAL_WEEKLY", "ORIGINAL_OBP", "LEGACY_TABLE"], default="LEGACY_TABLE")
    start.add_argument("--catalog-sheet", action="append")
    start.add_argument("--catalog-scope", default="UNSPECIFIED")
    start.add_argument("--expected-catalog-count", type=int)
    start.add_argument("--case-ids-file", type=Path, help="Optional JSON array of target case IDs; frozen for this workflow")
    start.add_argument("--input-budget", type=int, help="Freeze the new run's complete-request character budget")
    trigger = sub.add_parser("trigger-workflow", help="Initialize trigger coverage, then classify incremental faults")
    trigger_flow = trigger.add_subparsers(dest="trigger_command", required=True)
    init = trigger_flow.add_parser("init")
    init.add_argument("--modes", type=Path, required=True)
    init.add_argument("--taxonomy", type=Path, required=True)
    init.add_argument("--v4", type=Path, help="Original V4 required by default Baseline Builder; API42 remains original")
    init.add_argument("--legacy-dense", action="store_true", help="Explicit legacy response contract; default is V5 sparse")
    init.add_argument("--simple-v5", action="store_true", help="Use the prior single-task sparse Init, without Baseline Builder")
    init.add_argument("--expected-mode-count", type=int, default=30, help="Baseline Builder original mode count")
    init.add_argument("--with-designs", action="store_true", help="Also schedule separate scenario-bound design tasks")
    init.add_argument("--capabilities-file", type=Path, help="Declared design capabilities; not an execution receipt")
    init.add_argument("--catalog-scope", default="ORIGINAL_MECHANISM_LIBRARY")
    init.add_argument("--basis", choices=["HISTORICAL_EVIDENCE", "SOURCE_DEFINITIONS"],
                      default="SOURCE_DEFINITIONS", help="Existing mode definitions do not require customer-event confirmation")
    init.add_argument("--branch-source", type=Path)
    init.add_argument("--user-branches", action="store_true", default=True,
                      help="Use the user's explicit Branch 2/3 definitions (default)")
    init.add_argument("--no-user-branches", action="store_false", dest="user_branches")
    classify = trigger_flow.add_parser("classify")
    classify.add_argument("--baseline-run", required=True)
    classify.add_argument("--baseline-id")
    classify.add_argument("--input", type=Path, required=True)
    classify.add_argument("--allow-pending-baseline", action="store_true")
    configure_v4 = trigger_flow.add_parser("configure-v4", help="Maintain an Init with separately frozen original V4 and original42 rules")
    configure_v4.add_argument("--run", default="latest")
    configure_v4.add_argument("--source", type=Path, required=True)
    configure_v4.add_argument("--capabilities-file", type=Path)
    configure_v5 = trigger_flow.add_parser("configure-v5", help="Maintain an existing Init using sparse scenario classification")
    configure_v5.add_argument("--run", default="latest")
    configure_v5.add_argument("--with-designs", action="store_true")
    builder = trigger_flow.add_parser("configure-baseline", help="Verify original API42 and enable A1-A4 plus horizontal review")
    builder.add_argument("--run", default="latest")
    builder.add_argument("--expected-mode-count", type=int, default=30)
    reassess = trigger_flow.add_parser("reassess", help="Request a fresh subject assessment; preserve sources and history")
    reassess.add_argument("--run", default="latest")
    reassess.add_argument("--subject-id", required=True)
    reassess.add_argument("--reason", required=True)
    reassess.add_argument("--requested-by", required=True, help="Actual Agent/operator requesting reassessment; not a human verdict")
    for entry in (init, classify):
        entry.add_argument("--work-root", type=Path, default=Path("work/runs"))
        entry.add_argument("--executor", choices=["opencode", "codex"], default="opencode")
        entry.add_argument("--input-budget", type=int, help="Freeze the new run's complete-request character budget")
    for commands in (flow, trigger_flow):
        pin_budget = commands.add_parser("pin-budget", help="Freeze the original run budget; preserve requests and history")
        pin_budget.add_argument("--run", default="latest")
        pin_budget.add_argument("--chars", type=int, required=True)
    recovery = trigger_flow.add_parser("recovery-plan", help="Read-only mode/stage recovery preview; no tasks or model execution")
    recovery.add_argument("--run", default="latest")
    for commands, operations in ((flow, ("next", "submit", "drive", "export", "retry", "set-sources")),
                                 (trigger_flow, ("next", "submit", "drive", "export", "retry", "status", "finalize", "set-sources"))):
        for operation in operations:
            cmd = commands.add_parser(operation)
            cmd.add_argument("--run", default="latest")
            if operation == "export" and commands is trigger_flow:
                cmd.add_argument("--xlsx", action="store_true", help="Also export a compact optional XLSX index")
            if operation in {"submit", "retry"}:
                cmd.add_argument("--task-id", required=True)
            if operation == "submit":
                cmd.add_argument("--response", type=Path, required=True)
            if operation == "finalize":
                cmd.add_argument("--allow-pending", action="store_true")
            if operation == "set-sources":
                cmd.add_argument("--source", action="append", required=True,
                    choices=["WIKI", "DTS", "GITCODE", "GITHUB", "GITEE", "CODEHUB"])
                cmd.add_argument("--wiki-policy", choices=["REQUIRED", "NOT_SUPPORTED"], required=True)
                cmd.add_argument("--reason", required=True)
            if operation == "drive":
                cmd.add_argument("--agent-command-file", type=Path, required=True, help="JSON argv with {request}/{response}")
                cmd.add_argument("--max-rounds", type=int, default=32)
                cmd.add_argument("--workers", type=int, default=2)
                cmd.add_argument("--max-attempts", type=int, default=2)
                cmd.add_argument("--timeout", type=float, default=300)
                cmd.add_argument("--browser-timeout", type=float)
    search_policy = sub.add_parser("set-search-policy", help="Set a run default or case search stopping requirement")
    search_policy.add_argument("--run", default="latest")
    search_policy.add_argument("--case-id")
    search_policy.add_argument("--file", type=Path, help="Complete policy JSON; cannot be combined with policy flags")
    search_policy.add_argument("--min-evidence", type=int)
    search_policy.add_argument("--require-source", action="append", default=None,
                               choices=["WIKI", "DTS", "GITCODE", "GITHUB", "GITEE", "CODEHUB"])
    search_policy.add_argument("--require-any-source", nargs="+", default=None,
                               choices=["WIKI", "DTS", "GITCODE", "GITHUB", "GITEE", "CODEHUB"])
    group = sub.add_parser("register-event-group", help="Register only a user-confirmed event relationship")
    group.add_argument("--run", default="latest")
    group.add_argument("--case-ids", nargs="+", required=True)
    group.add_argument("--group-id")
    association = sub.add_parser("confirm-evidence", help="Record an explicit user-confirmed evidence relationship")
    association.add_argument("--run", default="latest")
    association.add_argument("--case-id", required=True)
    association.add_argument("--ref-id")
    association.add_argument("--snapshot-id")
    association.add_argument("--issue", action="append", default=[])
    for registration in (group, association):
        registration.add_argument("--user-confirmed", action="store_true", required=True)
        registration.add_argument("--confirmed-by", required=True)
        registration.add_argument("--reason", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    # JSON files and stdout use the same UTF-8 protocol, including Windows pipes
    # whose inherited ANSI encoding may not represent a Chinese workspace path.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    store = None
    try:
        if args.command == "doctor":
            write_json(doctor())
            return 0
        if args.command == "precision-bridge":
            from .precision_cli import run as run_precision
            result, code = run_precision(args)
            write_json(result)
            return code
        if args.command == "reconcile-report":
            from .statistics import report_statistics
            load = lambda path: json.loads(path.read_text(encoding="utf-8-sig")) if path else None
            result = report_statistics(load(args.input), baseline=load(args.baseline),
                                       round_manifest=load(args.round_manifest))
            write_json(result, args.out)
            write_json({"statistics": str(args.out.resolve()), "status": result["status"],
                        "round_status": result["round"]["status"], "sqlite_opened": False})
            return 2 if result["status"] == "RECONCILIATION_FAILED" else 0
        # Keep doctor and --version available even when third-party dependencies
        # are absent, so a new environment can diagnose itself without a traceback.
        from .contracts import CatalogDraft, EvidencePackage, EvidenceSummary, Judgment
        from .importers import import_cases, import_catalog
        from .pipeline import (check_catalog_import, evidence_index, execute, fetch_tasks,
                               import_into, report_data, validate)
        from .store import AuditError, Store
        if args.command == "schemas":
            for cls in (EvidencePackage, EvidenceSummary, Judgment, CatalogDraft):
                write_json(cls.model_json_schema(), args.out / f"{cls.__name__}.schema.json")
            write_json({"schemas": str(args.out.resolve())})
            return 0
        read_only = args.command in {"evidence-plan", "investigation-plan", "catalog-draft"} or (
            args.command == "trigger-workflow" and args.trigger_command in {"recovery-plan", "status"})
        store = Store(args.state, read_only=read_only)
        if args.command in {"xlsx-workflow", "trigger-workflow"}:
            from . import xlsx_workflow as workflow
            operation = args.flow_command if args.command == "xlsx-workflow" else args.trigger_command
            if args.command == "trigger-workflow":
                from . import trigger_workflow as trigger_workflow
            if operation == "init":
                result = trigger_workflow.start_init(store, args.modes, args.taxonomy, args.work_root,
                    executor=args.executor, branch_source=args.branch_source, user_branches=args.user_branches,
                    catalog_scope=args.catalog_scope, basis=args.basis, v4_source=args.v4,
                    capabilities=json.loads(args.capabilities_file.read_text(encoding="utf-8-sig")) if args.capabilities_file else None,
                    sparse=not args.legacy_dense, with_designs=args.with_designs,
                    baseline_builder=not args.legacy_dense and not args.simple_v5, expected_mode_count=args.expected_mode_count,
                    input_budget_chars=args.input_budget)
            elif operation == "classify":
                result = trigger_workflow.start_incremental(store, args.input, args.baseline_run, args.work_root,
                    executor=args.executor, baseline_id=args.baseline_id, allow_pending_baseline=args.allow_pending_baseline,
                    input_budget_chars=args.input_budget)
            elif operation == "start":
                result = workflow.start(store, args.input, args.catalog, args.work_root, executor=args.executor,
                    source_kind=args.source_kind, catalog_sheets=args.catalog_sheet,
                    expected_catalog_count=args.expected_catalog_count, catalog_scope=args.catalog_scope, run_id=args.run,
                    case_ids=json.loads(args.case_ids_file.read_text(encoding="utf-8-sig")) if args.case_ids_file else None,
                    input_budget_chars=args.input_budget)
            else:
                selected_run = store.run_info(args.run)["run_id"]
                if operation == "pin-budget":
                    from .run_budget import pin
                    result = pin(store, selected_run, args.chars)
                elif operation == "recovery-plan":
                    from .baseline_recovery import recovery_plan
                    result = recovery_plan(store, selected_run)
                elif operation == "next":
                    result = workflow.next_tasks(store, selected_run)
                elif operation == "submit":
                    result = workflow.submit(store, selected_run, args.task_id,
                        json.loads(args.response.read_text(encoding="utf-8-sig")), path=args.response)
                elif operation == "retry":
                    result = workflow.retry(store, selected_run, args.task_id)
                elif operation == "set-sources":
                    result = workflow.configure_collection(store, selected_run, args.source,
                        wiki_policy=args.wiki_policy, reason=args.reason)
                elif operation == "configure-v4":
                    result = trigger_workflow.configure_v4(store, selected_run, args.source,
                        capabilities=json.loads(args.capabilities_file.read_text(encoding="utf-8-sig")) if args.capabilities_file else None)
                elif operation == "configure-v5":
                    result = trigger_workflow.configure_v5(store, selected_run, with_designs=args.with_designs)
                elif operation == "configure-baseline":
                    from .cann_baseline import configure
                    result = configure(store, selected_run, expected_mode_count=args.expected_mode_count)
                elif operation == "reassess":
                    from .trigger_maintenance import request_reassessment
                    result = request_reassessment(store, selected_run, args.subject_id,
                        reason=args.reason, requested_by=args.requested_by)
                elif operation == "drive":
                    result = workflow.drive(store, selected_run,
                        json.loads(args.agent_command_file.read_text(encoding="utf-8-sig")), max_rounds=args.max_rounds,
                        workers=args.workers, max_attempts=args.max_attempts, timeout=args.timeout,
                        browser_timeout=args.browser_timeout)
                elif operation == "status":
                    result = trigger_workflow.status(store, selected_run)
                elif operation == "finalize":
                    result = trigger_workflow.finalize(store, selected_run, allow_pending=args.allow_pending)
                else:
                    result = (trigger_workflow.export(store, selected_run, xlsx=args.xlsx)
                        if args.command == "trigger-workflow" else workflow.export(store, selected_run))
            write_json(result)
            return 2 if result.get("status") in {"COMPLETE_WITH_PENDING", "BLOCKED"} else 0
        if args.command == "demo":
            write_json(demo(store, args.out.resolve()))
            return 0
        if args.command == "import":
            if not args.catalog and (args.catalog_sheet is not None or args.catalog_scope != "UNSPECIFIED"
                                     or args.expected_catalog_count is not None):
                raise AuditError("Catalog selection options require --catalog")
            if args.expected_catalog_count is not None and args.expected_catalog_count < 1:
                raise AuditError("--expected-catalog-count must be positive")
            imported = import_cases(args.input, source_kind=args.source_kind)
            catalog = import_catalog(args.catalog, sheets=args.catalog_sheet, scope=args.catalog_scope,
                                     expected_count=args.expected_catalog_count) if args.catalog else None
            run_id = store.run_info(args.run)["run_id"] if args.run else None
            if catalog:
                check_catalog_import(store, run_id, catalog)
            run_id = run_id or store.create_run()
            counts = import_into(store, run_id, imported)
            if catalog:
                import_into(store, run_id, catalog, catalog=True)
            write_json({"run_id": run_id, "imported": counts,
                        "catalog_identity": catalog.get("catalog_identity") if catalog else None,
                        "validation": validate(store, run_id)})
            return 0
        run_id = store.run_info(args.run)["run_id"]
        from .workflow_scope import scoped_store
        store = scoped_store(store, run_id)
        if args.command == "catalog-draft":
            from .catalog_drafts import prepare_draft, validate_draft, export_draft, write_new_json
            if args.out and args.out.resolve().is_relative_to(store.root):
                raise AuditError("Read-only catalog draft output must be outside the state directory")
            if args.draft_command == "prepare":
                result = prepare_draft(store, run_id, args.case_id, args.expected_additions)
                args.out.mkdir(parents=True, exist_ok=False)
                if result["status"] == "BLOCKED":
                    write_new_json(args.out / "blocked.json", result)
                    write_json({"status": "BLOCKED", "reason": result["reason"], "input_budget": result["input_budget"],
                                "output": str(args.out.resolve()), "sqlite_read_only": True})
                    return 2
                write_new_json(args.out / "request.json", result["request"])
                write_new_json(args.out / "response_template.json", result["response_template"])
                write_json({"status": result["status"], "output": str(args.out.resolve()),
                            "input_budget": result["request"]["input_budget"], "sqlite_read_only": True})
                return 0
            load = lambda path: json.loads(path.read_text(encoding="utf-8-sig"))
            request, response = load(args.request), load(args.draft)
            if args.draft_command == "validate":
                result = validate_draft(store, run_id, request, response)
                if args.out:
                    write_new_json(args.out, result)
                write_json(result)
                return 2 if result["errors"] else 0
            result = export_draft(store, run_id, request, response, args.out.resolve())
            if args.xlsx and result["outputs"]:
                from .exporters import export_workbook_xlsx
                result["outputs"].update(export_workbook_xlsx(Path(result["outputs"]["workbook_data"]),
                                                           args.out.resolve() / "catalog_draft.xlsx"))
            write_json(result)
            return 2 if result["validation"]["errors"] else 0
        if args.command == "investigation-plan":
            from .investigation import investigation_plan
            if args.out.resolve().is_relative_to(store.root):
                raise AuditError("Read-only investigation output must be outside the state directory")
            write_json(investigation_plan(store, run_id), args.out)
            return 0
        if args.command == "evidence-plan":
            from .pipeline import evidence_plan
            write_json(evidence_plan(store, run_id), args.out)
            return 0
        if args.command == "set-search-policy":
            from .evidence_plan import register_search_policy
            if args.file and any(value is not None for value in (args.min_evidence, args.require_source, args.require_any_source)):
                raise AuditError("--file cannot be combined with search policy flags")
            policy = json.loads(args.file.read_text(encoding="utf-8-sig")) if args.file else {
                "min_usable_evidence": args.min_evidence if args.min_evidence is not None else 1,
                "required_sources": args.require_source or [],
                "required_any_sources": args.require_any_source or [],
            }
            write_json(register_search_policy(store, run_id, policy, case_id=args.case_id))
            return 0
        if args.command in {"register-event-group", "confirm-evidence"}:
            from .evidence_plan import register_event_group, register_evidence_association
            common = {"user_confirmed": args.user_confirmed, "confirmed_by": args.confirmed_by, "reason": args.reason}
            if args.command == "register-event-group":
                result = register_event_group(store, run_id, case_ids=args.case_ids, group_id=args.group_id, **common)
            else:
                result = register_evidence_association(store, run_id, case_id=args.case_id, ref_id=args.ref_id,
                    snapshot_id=args.snapshot_id, applicable_issue_ids=args.issue, **common)
            write_json(result)
            return 0
        if args.command == "ingest-evidence":
            body = json.loads(args.package.read_text(encoding="utf-8-sig"))
            packages = body if isinstance(body, list) else [body]
            snapshots = [store.ingest_evidence(run_id, pkg, args.package.parent) for pkg in packages]
            write_json({"run_id": run_id, "snapshots": [{"snapshot_id": s["snapshot_id"], "status": s["status"]} for s in snapshots]})
        elif args.command == "fetch-tasks":
            value = fetch_tasks(store, run_id)
            write_json(value, args.out)
            if args.out:
                write_json({"run_id": run_id, "task_file": str(args.out.resolve()), "count": len(value["fetch_tasks"])})
        elif args.command == "evidence-index":
            value = evidence_index(store, run_id, args.url)
            write_json(value, args.out)
            if args.out:
                write_json({"run_id": run_id, "index_file": str(args.out.resolve()),
                            "count": len(value["evidence_index"]), "shared_evidence_count": value["shared_evidence_count"]})
        elif args.command == "run":
            from .model import MockJudge
            from .bridge import OpenCodeJudge, CodexJudge
            if args.mode == "mock":
                judge, model_id = MockJudge(), "mock-conservative-v1"
            elif args.mode == "opencode":
                judge, model_id = OpenCodeJudge(store, run_id), "opencode-managed"
            else:
                judge, model_id = CodexJudge(store, run_id), "codex-managed"
            result = execute(store, run_id, judge, mode=args.mode, model_id=model_id, retry_failed=args.retry_failed)
            write_json(result)
            return 0 if result["valid"] else 2
        elif args.command in {"model-tasks", "submit-model-results"}:
            from .bridge import OpenCodeJudge, CodexJudge, export_model_tasks, submit_model_results
            accepted = None
            if args.command == "submit-model-results":
                body = json.loads(args.file.read_text(encoding="utf-8-sig"))
                envelopes = body if isinstance(body, list) else body.get("results", [body]) if isinstance(body, dict) else None
                if not isinstance(envelopes, list):
                    raise AuditError("Results must be an envelope, a list, or an object with results")
                accepted = submit_model_results(store, run_id, envelopes, executor=args.executor)
            judge = CodexJudge(store, run_id) if args.executor == "codex" else OpenCodeJudge(store, run_id)
            status = execute(store, run_id, judge, mode=args.executor, model_id=args.executor + "-managed")
            ready = export_model_tasks(store, run_id, executor=args.executor)
            if args.command == "model-tasks":
                write_json(ready, args.out)
                write_json({"run_id": run_id, "task_file": str(args.out.resolve()),
                            "ready_model_tasks": len(ready["tasks"]), "validation": status})
            else:
                write_json({**accepted, "ready_model_tasks": len(ready["tasks"]), "validation": status})
        elif args.command in {"status", "validate"}:
            result = validate(store, run_id)
            write_json(result)
            return 2 if not result["valid"] or (getattr(args, "strict", False) and not result["complete"]) else 0
        elif args.command == "export":
            from .exporters import export_report
            load = lambda path: json.loads(path.read_text(encoding="utf-8-sig")) if path else None
            data = report_data(store, run_id, baseline=load(args.baseline), round_manifest=load(args.round_manifest))
            output = export_report(data, args.out.resolve())
            if args.xlsx:
                from .exporters import export_workbook_xlsx
                output.update(export_workbook_xlsx(Path(output["workbook_data"]), args.out.resolve() / "audit.xlsx"))
            write_json({"run_id": run_id, "outputs": output, "validation": validate(store, run_id),
                        "statistics_status": data["statistics"]["status"],
                        "round_statistics_status": data["statistics"]["round"]["status"]})
            if data["statistics"]["status"] == "RECONCILIATION_FAILED":
                return 2
        elif args.command == "review":
            record_id = args.mapping or args.judgment
            kind = "mappings" if args.mapping else "judgments"
            if not store.get(run_id, kind, record_id):
                raise AuditError("Review target not found in this run")
            key = "mapping_id" if args.mapping else "judgment_id"
            store.event(run_id, "review", {key: record_id, "record_kind": kind, "verdict": args.verdict,
                                           "reason": args.reason, "reviewer": args.reviewer})
            if kind == "judgments":
                case_id = store.get(run_id, kind, record_id)["case_id"]
                for task in store.tasks(run_id):
                    if task["kind"] == "catalog" and task["target_id"] == case_id and task["status"] != "STALE":
                        store.task_status(run_id, task["task_id"], "STALE", "Judgment review changed; catalog requires revalidation")
            write_json({"run_id": run_id, "review_saved": record_id, "record_kind": kind, "verdict": args.verdict})
        return 0
    except Exception as exc:
        # The core never initializes a live model client or reads model secrets.
        write_json({"error": type(exc).__name__, "message": str(exc)}, None)
        return 1
    finally:
        if store:
            store.close()
