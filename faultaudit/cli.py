"""Cross-platform CLI. Collectors return packages; this process owns audit state."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import uuid
import zipfile
import xml.etree.ElementTree as ET
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
        from .contracts import EvidencePackage, EvidenceSummary, Judgment
        from .importers import import_cases, import_catalog
        from .pipeline import (check_catalog_import, evidence_index, execute, fetch_tasks,
                               import_into, report_data, validate)
        from .store import AuditError, Store
        if args.command == "schemas":
            for cls in (EvidencePackage, EvidenceSummary, Judgment):
                write_json(cls.model_json_schema(), args.out / f"{cls.__name__}.schema.json")
            write_json({"schemas": str(args.out.resolve())})
            return 0
        store = Store(args.state, read_only=args.command == "evidence-plan")
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
        if args.command == "evidence-plan":
            from .pipeline import evidence_plan
            write_json(evidence_plan(store, run_id), args.out)
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
                node = os.getenv("FAULTAUDIT_NODE", "node")
                script = Path(__file__).resolve().parents[1] / "scripts" / "export_xlsx.mjs"
                target = args.out.resolve() / "audit.xlsx"
                temporary = args.out.resolve() / f"audit-build-{uuid.uuid4().hex[:8]}.xlsx"
                command = [node, str(script), "--input", str(output["workbook_data"]), "--output", str(temporary),
                           "--preview-dir", str(args.out.resolve() / "xlsx_previews")]
                if os.getenv("FAULTAUDIT_NODE_MODULES"):
                    command.extend(["--modules", os.environ["FAULTAUDIT_NODE_MODULES"]])
                process = subprocess.run(command,
                                         capture_output=True, text=True, encoding="utf-8", errors="replace")
                if not temporary.is_file():
                    raise AuditError("Basic reports were saved; optional XLSX exporter failed: " + process.stderr[-2000:])
                # Some bundled runtimes report 1 after a completed save. Check a
                # fresh output's ZIP and workbook structure instead of trusting an
                # old file or ignoring the runtime status.
                with zipfile.ZipFile(temporary) as package:
                    if package.testzip():
                        raise AuditError("XLSX ZIP integrity check failed")
                    workbook = ET.fromstring(package.read("xl/workbook.xml"))
                    expected = len(json.loads(Path(output["workbook_data"]).read_text(encoding="utf-8"))["sheets"])
                    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                    if len(workbook.findall("s:sheets/s:sheet", ns)) != expected:
                        raise AuditError("XLSX sheet count does not match report data")
                temporary.replace(target)
                output["xlsx"] = str(target)
                if process.returncode:
                    output["xlsx_runtime_warning"] = f"Runtime exited {process.returncode}; fresh saved ZIP and sheet count verified. Check previews before use."
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
