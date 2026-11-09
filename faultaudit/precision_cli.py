"""Small independent Bridge CLI; keep doctor usable without third-party imports."""
from pathlib import Path


def add_parser(sub):
    command = sub.add_parser("precision-bridge", help="Read-only frozen Baseline export and native ATK rule attribution")
    actions = command.add_subparsers(dest="precision_command", required=True)
    export = actions.add_parser("export", help="Export a current READY Builder Baseline; never export known-mode data as blind")
    export.add_argument("--baseline-run", required=True)
    export.add_argument("--baseline-id")
    export.add_argument("--mode-id", action="append")
    blind = actions.add_parser("blind", help="Create a knowledge-free native blind context in a separate session")
    for item in (export, blind):
        item.add_argument("--repo", type=Path, required=True)
        item.add_argument("--task-slug", required=True)
        item.add_argument("--out", type=Path, required=True)
    request = actions.add_parser("draft", help="Write a whole-input-budgeted assignment task for an existing independent Agent")
    bind = actions.add_parser("bind", help="Validate and preserve immutable case-to-mode/source bindings")
    check = actions.add_parser("check", help="Run only upstream format/JSON checks; no ATK queue or device actions")
    for item in (request, bind, check):
        item.add_argument("--context", type=Path, required=True)
        item.add_argument("--suite", type=Path, required=True)
        item.add_argument("--out", type=Path, required=True)
    bind.add_argument("--assignments", type=Path, required=True)
    check.add_argument("--bindings", type=Path, required=True)
    check.add_argument("--workspace", type=Path, required=True)
    check.add_argument("--atk-suite", type=Path)
    check.add_argument("--python", type=Path, help="Interpreter containing the native checkers' PyYAML dependency")
    check.add_argument("--timeout", type=int, default=30)
    check.add_argument("--diagnostic-smoke", action="store_true", help="Permit only recognized case-budget warnings; never formal completion")


def run(args):
    from contextlib import closing, nullcontext
    from types import SimpleNamespace
    from .store import Store, AuditError
    from . import precision_bridge as bridge, precision_target as target, precision_gate as gate
    from .input_budget import InputTooLarge
    action = args.precision_command
    value = target.read_json(args.context) if action in {"draft", "bind", "check"} else None
    need_state = action == "export" or value is not None and value.get("purpose") == "KNOWN_PATTERN_VALIDATION"
    session = closing(Store(args.state, read_only=True)) if need_state else nullcontext(None)
    with session as store:
        context = bridge.current_context(value, store) if value else None
        # Even blind/draft commands must not write into the configured state root.
        target.protect_output(args.out, store=SimpleNamespace(root=Path(args.state).resolve()),
            repo=context.target["repo_path"] if context else args.repo)
        if action == "export":
            return bridge.export_context(store, args.baseline_run, args.repo, args.task_slug, args.out,
                baseline_id=args.baseline_id, mode_ids=args.mode_id), 0
        if action == "blind":
            return bridge.export_blind(args.repo, args.task_slug, args.out), 0
        if action == "draft":
            try:
                request = bridge.draft_request(context.model_dump(), args.suite)
            except InputTooLarge as exc:
                block = {"kind": "precision_bind", "status": "BLOCKED", "reason": "INPUT_TOO_LARGE",
                    "input_budget": exc.details, "input_truncated": False}
                target.immutable_json(args.out, block)
                return {"request": str(args.out.resolve()), **block}, 2
            target.immutable_json(args.out, request)
            return {"request": str(args.out.resolve()), "task_id": request["task_id"], "request_hash": request["request_hash"],
                "input_budget": request["input_budget"], "status": "WAITING_AGENT", "state_written": False}, 0
        if action == "bind":
            result = bridge.bind(store, context.model_dump(), args.suite, target.read_json(args.assignments), args.out)
            return result, 2 if result.get("status") == "BLOCKED" else 0
        if args.timeout < 1:
            raise AuditError("Native checker timeout must be positive")
        report = gate.check(store, context.model_dump(), target.read_json(args.bindings), args.workspace,
            suite=args.suite, atk_suite=args.atk_suite, python=args.python, diagnostic=args.diagnostic_smoke, timeout=args.timeout)
        result = gate.write_report(report, args.out, store=store, repo=context.target["repo_path"])
        accepted = report["formal_suite_ready"] or report["rule_design_ready"] and report["native_suite_status"] in {"PROTOCOL_DESIGN_ONLY", "DIAGNOSTIC_ONLY"}
        return result, 0 if accepted else 2
