"""Read-only catalog proposals: bind current evidence, validate, preview, export.

No model/network client, state writes, event merging or formal catalog adoption.
Exact citations establish traceability; semantic conclusions remain Agent proposals.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from .contracts import CatalogDraft, CatalogDraftRow
from .input_budget import InputTooLarge, check_input_budget, finalize_model_task
from .investigation import ROOT_FIELDS, investigation_plan
from .pipeline import current_mappings
from .store import AuditError, Store, canonical_url, digest

RULE_VERSION = "catalog-draft-1.0"
COLUMNS = dict(zip(CatalogDraftRow.model_fields, [
    "一级（架构层次）", "二级（物理实体）", "三级（部件、功能模块）", "四级（部件、功能模块）",
    "模式名称", "故障原因", "故障影响", "参考业务场景", "精度故障类型", "检查机制", "模块处理建议",
    "故障可构造", "注入工具", "构造方法", "案例链接",
]))
SUGGESTIONS = {"detection", "mitigation", "constructibility", "injection_tool", "injection_method"}
INSTRUCTIONS = """Produce a CATALOG_DRAFT JSON response using the supplied schema and request_hash.
Use all selected cases and compare every frozen catalog item per proposal. The expected
number of ADD proposals is fixed by this request. Do not create human ACCEPT or modify state.
Abstract the pattern name; describe the specific mechanism separately. Fill all fifteen columns
and a field basis for each. Cite current fact_ids or exact source cells; imported attributions
are not verified root causes. Keep absent details unknown, units and implementation ownership
unchanged. Do not mix subproblems, or confirm a customer event from another event's facts.
CASE_ROOT_CAUSE requires a current root-cause candidate for the exact work and fact.
INDEPENDENT_TECHNICAL_PATTERN never confirms the associated customer case. Checks, mitigation
and injection are proposals, NOT_EXECUTED; do not claim local reproduction. Self-check numeric
meaning, citations, counterevidence, issue scope and event-vs-technical identity once. Keep
unresolved conflicts explicit. Use current search_control; do not expand searches to fill fields.
If unable to read the complete request, report blocking instead of submitting a complete draft.
"""


def draft_policy_fingerprint() -> str:
    from .bridge import policy_fingerprint
    from . import investigation
    return digest({"core": policy_fingerprint(), "rule": RULE_VERSION,
                   "sources": digest(Path(__file__).read_bytes() + Path(investigation.__file__).read_bytes())})


def draft_context(store: Store, run_id: str, case_ids: list[str], expected_additions: int) -> dict:
    if not case_ids or len(set(case_ids)) != len(case_ids):
        raise AuditError("Select a nonempty, unique case ID set")
    if isinstance(expected_additions, bool) or not isinstance(expected_additions, int) or expected_additions < 0:
        raise AuditError("Expected additions must be a nonnegative integer")
    plan = investigation_plan(store, run_id)
    selected = set(case_ids)
    cases = [case for case in plan["cases"] if case["case_id"] in selected]
    if {case["case_id"] for case in cases} != selected:
        raise AuditError("Selected case ID is absent from this run")
    works = [work for work in plan["work_items"] if selected.intersection(work["case_ids"])]
    sids = {work["snapshot_id"] for work in works}
    catalog = store.records(run_id, "catalog")
    ids = [item["item_id"] for item in catalog]
    identity = store.get(run_id, "catalog_selections", "frozen")
    if not catalog or len(ids) != len(set(ids)) or not identity:
        raise AuditError("A nonempty frozen catalog with unique IDs is required")
    if any(item["source_sha256"] != identity["source_sha256"] for item in catalog):
        raise AuditError("Catalog rows do not match the frozen source identity")
    catalog = sorted(catalog, key=lambda item: (item.get("sheet", ""), item.get("row") or 0, item["item_id"]))
    # Retain the complete frozen library and selected inputs; never truncate.
    return {"run_id": run_id, "selected_case_ids": sorted(selected), "expected_additions": expected_additions,
            "baseline_identity": identity, "baseline_hash": digest(catalog), "catalog": catalog,
            "cases": cases, "work_items": works,
            "resources": [r for r in plan["resources"] if selected.intersection(r["case_ids"])],
            "independent_technical_facts": [f for f in plan["independent_technical_facts"] if f["snapshot_id"] in sids],
            "current_mappings": [m for m in current_mappings(store, run_id) if m["case_id"] in selected],
            "input_scope": "COMPLETE_FROZEN_CATALOG_AND_SELECTED_CASES; CAPTURED_EVIDENCE_ONLY"}


def prepare_draft(store: Store, run_id: str, case_ids: list[str], expected_additions: int) -> dict:
    context = draft_context(store, run_id, case_ids, expected_additions)
    unsigned = {"kind": "catalog_draft", "schema_version": "1.0", "run_id": run_id,
                "policy_hash": draft_policy_fingerprint(), "instructions": INSTRUCTIONS,
                "response_schema": CatalogDraft.model_json_schema(), "payload": context}
    try:
        request = finalize_model_task(unsigned)
    except InputTooLarge as exc:
        return {"status": "BLOCKED", "reason": "INPUT_TOO_LARGE", "input_budget": exc.details,
                "context": context, "request": None}
    return {"status": "READY_FOR_AGENT", "request": request,
            "response_template": {"schema_version": "1.0", "kind": "CATALOG_DRAFT",
                "request_hash": request["request_hash"], "executor": "opencode",
                "created_by": "REPLACE_WITH_ACTUAL_EXECUTOR", "producer": {
                    "executor_version": "UNREPORTED", "provider": "UNREPORTED",
                    "model": "UNREPORTED", "session_id": "UNREPORTED"}, "proposals": []}}


def _check_request(store: Store, run_id: str, request: dict) -> dict:
    if request.get("kind") != "catalog_draft" or request.get("run_id") != run_id:
        raise AuditError("Catalog draft request belongs to a different kind or run")
    if digest({key: value for key, value in request.items() if key != "request_hash"}) != request.get("request_hash"):
        raise AuditError("Catalog draft request integrity mismatch")
    if request.get("policy_hash") != draft_policy_fingerprint():
        raise AuditError("Catalog draft request policy is stale")
    measurement = check_input_budget(request)
    if any(request.get("input_budget", {}).get(key) != measurement[key]
           for key in ("chars", "budget", "scope", "serialization")):
        raise AuditError("Catalog draft request input budget metadata mismatch")
    saved = request["payload"]
    current = draft_context(store, run_id, saved["selected_case_ids"], saved["expected_additions"])
    if digest(current) != digest(saved):
        raise AuditError("Catalog draft inputs are stale: baseline, evidence, input or review changed")
    return current


def _unknown(value: str) -> bool:
    return value.strip().casefold().startswith(("未知", "无法确定", "待定位", "待确认", "待核验", "暂无", "unknown"))


def validate_draft(store: Store, run_id: str, request: dict, response: dict) -> dict:
    """Rebuild current dependencies, then enforce shared field/scope gates."""
    context = _check_request(store, run_id, request)
    draft = CatalogDraft.model_validate(response)
    errors, warnings, statuses = [], [], []
    if draft.request_hash != request["request_hash"]:
        errors.append("Response does not belong to this request")
    if not draft.created_by.strip() or draft.created_by == "REPLACE_WITH_ACTUAL_EXECUTOR":
        errors.append("Report the actual creator, not the unfilled response template")
    catalog_ids = {item["item_id"] for item in context["catalog"]}
    selected = set(context["selected_case_ids"])
    cases = {case["case_id"]: case["source_case"] for case in context["cases"]}
    works = {work["work_id"]: work for work in context["work_items"]}
    facts = {fact["fact_id"]: fact for fact in context["independent_technical_facts"]}
    seen, covered, pattern_names = set(), set(), set()
    additions = 0
    for p in draft.proposals:
        prefix = p.proposal_id + ": "
        fail = lambda message: errors.append(prefix + message)
        if p.proposal_id in seen:
            fail("duplicate proposal_id")
        seen.add(p.proposal_id)
        covered.update(p.case_ids)
        if len(set(p.case_ids)) != len(p.case_ids) or not set(p.case_ids) <= selected:
            fail("case_ids must be unique selected cases")
        if len(set(p.work_ids)) != len(p.work_ids) or any(wid not in works for wid in p.work_ids):
            fail("work_ids must be unique current selected work IDs")
        pworks = [works[wid] for wid in p.work_ids if wid in works]
        if any(not set(work["case_ids"]).intersection(p.case_ids) for work in pworks):
            fail("work does not belong to a proposal case")
        if not p.self_check.passed or p.self_check.issues or not all(
                getattr(p.self_check, key) for key in ("numeric_meaning_checked", "citations_checked",
                "counterevidence_checked", "issue_scope_checked", "event_vs_technical_checked")):
            fail("bounded self-check must pass; unresolved facts must remain unknown or explicit conflicts")
        compared = [item.item_id for item in p.coverage_comparisons]
        if len(compared) != len(set(compared)) or set(compared) != catalog_ids:
            fail("coverage comparison must include every frozen item exactly once")
        if p.action == "ADD":
            additions += 1
            if p.target_item_id is not None:
                fail("ADD cannot overwrite an existing item")
            if any(item.relation == "SAME_PATTERN" for item in p.coverage_comparisons):
                fail("existing SAME_PATTERN requires append/refine/no-change, not ADD")
            name = p.row.pattern_name.strip().casefold()
            if name in pattern_names:
                fail("duplicate ADD pattern name; combine supporting cases in one proposal")
            pattern_names.add(name)
            if name in {item["description"].strip().casefold() for item in context["catalog"]}:
                fail("ADD pattern name already exists in the frozen catalog")
        elif p.action in {"REFINE", "APPEND_CASE"} and p.target_item_id not in catalog_ids:
            fail("refine/append requires an existing target item")
        elif p.target_item_id is not None and p.target_item_id not in catalog_ids:
            fail("unknown target item")
        if p.action == "APPEND_CASE" and not any(item.item_id == p.target_item_id and item.relation == "SAME_PATTERN"
                                                for item in p.coverage_comparisons):
            fail("APPEND_CASE requires a SAME_PATTERN comparison for its target")
        if set(p.field_bases) != set(COLUMNS):
            fail("field_bases must cover all fifteen columns exactly")
        valid_fact_ids = set()
        for key, basis in p.field_bases.items():
            if key not in COLUMNS:
                continue
            value = getattr(p.row, key)
            if not basis.note.strip():
                fail(key + " has a blank basis note")
            if len(set(basis.fact_ids)) != len(basis.fact_ids):
                fail(key + " repeats fact IDs")
            if basis.kind == "UNKNOWN" and not _unknown(value):
                fail(key + " must display an explicit unknown")
            if basis.kind in {"CITED_FACT", "CODE_INFERENCE"} and not basis.fact_ids:
                fail(key + " requires current cited facts")
            if basis.kind == "SOURCE_CELL" and not basis.source_cells:
                fail(key + " requires exact original cells")
            if key in SUGGESTIONS and basis.kind not in {"PROPOSED", "UNKNOWN"}:
                fail(key + " must remain a suggestion or unknown, not an executed result")
            for cell in basis.source_cells:
                source = cases.get(cell.case_id)
                if (cell.case_id not in p.case_ids or not source or not cell.quote.strip()
                        or source["cell_locations"].get(cell.field) != cell.cell
                        or cell.quote not in source["raw"].get(cell.field, "")):
                    fail(key + " source cell/quotation does not match a selected immutable case")
            for fid in basis.fact_ids:
                fact = facts.get(fid)
                matching = [work for work in pworks if fact and work["snapshot_id"] == fact["snapshot_id"]
                    and (not work["issue_scope"].get("applicable_issue_ids")
                         or fact["issue_label"] in work["issue_scope"]["applicable_issue_ids"])]
                if not fact or not matching:
                    fail(key + " uses a stale, missing or out-of-scope fact")
                    continue
                valid_fact_ids.add(fid)
                if p.evidence_scope == "CASE_ROOT_CAUSE" and not any(
                        fid in work["independent_fact_ids"] for work in matching):
                    fail(key + " fact is not resolved for this case/subproblem")
                if key == "root_cause":
                    if fact["field"].strip().casefold() not in ROOT_FIELDS:
                        fail("root_cause must cite a mechanism fact, not just a symptom/operator")
                    if p.evidence_scope == "CASE_ROOT_CAUSE" and not any(
                            any(candidate["fact_id"] == fid for candidate in work["root_cause_candidates"])
                            for work in matching):
                        fail("root_cause is not a current root-cause candidate for this work")
        by_snapshot = {}
        for fid in valid_fact_ids:
            fact = facts[fid]
            by_snapshot.setdefault(fact["snapshot_id"], set()).add((fact["summary_task_id"], fact["issue_index"]))
        if any(len(issues) > 1 for issues in by_snapshot.values()):
            fail("one proposal cannot mix different issues/summary executions from the same snapshot")
        root = p.field_bases.get("root_cause")
        if root is not None and root.kind not in {"CITED_FACT", "CODE_INFERENCE", "SOURCE_CELL", "UNKNOWN"}:
            fail("root_cause cannot be invented from an abstraction or a proposed check")
        if p.evidence_scope == "CASE_ROOT_CAUSE" and (not root or root.kind not in {"CITED_FACT", "CODE_INFERENCE"}):
            fail("CASE_ROOT_CAUSE requires a current cited root-cause candidate")
        if p.evidence_scope == "CASE_ROOT_CAUSE" and root and any(not any(
                cid in work["case_ids"] and any(candidate["fact_id"] in root.fact_ids
                    for candidate in work["root_cause_candidates"]) for work in pworks) for cid in p.case_ids):
            fail("every case requires its own resolved work or explicit shared event work")
        for key in ("effect", "scenario", "precision_type"):
            basis = p.field_bases.get(key)
            if basis and basis.kind != "UNKNOWN" and not (basis.fact_ids or basis.source_cells):
                fail(key + " requires grounding or an explicit unknown")
        allowed_urls = {facts[fid]["url"] for fid in valid_fact_ids}
        allowed_urls.update(r["url"] for r in context["resources"] if set(r["case_ids"]).intersection(p.case_ids))
        if not _unknown(p.row.case_links):
            for link in p.row.case_links.splitlines():
                try:
                    if canonical_url(link) not in allowed_urls:
                        fail("case_links URL was not supplied or cited")
                except ValueError:
                    fail("case_links must contain one known HTTP(S) URL per line or an explicit unknown")
        root_status = ("UNKNOWN" if root is None or root.kind == "UNKNOWN" else
                       "IMPORTED_ATTRIBUTION_NOT_VERIFIED" if root.kind == "SOURCE_CELL" else "CITED_MODEL_PROPOSAL")
        statuses.append({"proposal_id": p.proposal_id, "revision": p.revision, "action": p.action,
            "root_cause_status": root_status, "evidence_scope": p.evidence_scope,
            "case_root_cause_confirmed": False, "human_accept_created": False,
            "processing_status": "EXCEPTION" if p.conflicts else "DRAFT",
            "implementation_owner": p.implementation_owner, "injection_execution": p.injection_execution,
            "unknowns": p.unknowns, "conflicts": p.conflicts})
        if root_status in {"UNKNOWN", "IMPORTED_ATTRIBUTION_NOT_VERIFIED"}:
            warnings.append(prefix + root_status)
    if covered != selected:
        errors.append("Every selected case must appear in a proposal; cases cannot be silently dropped")
    if additions != context["expected_additions"]:
        errors.append(f"Expected {context['expected_additions']} ADD proposals, received {additions}")
    return {"status": "BLOCKED" if errors else "VALID_DRAFT", "errors": errors, "warnings": warnings,
            "rule_version": RULE_VERSION, "policy_hash": request["policy_hash"],
            "input_budget": request["input_budget"], "request_hash": request["request_hash"], "response_hash": digest(response),
            "baseline_hash": context["baseline_hash"], "baseline_count": len(catalog_ids),
            "proposal_count": len(seen), "case_count": len(covered), "addition_count": additions,
            "merged_preview_count": len(catalog_ids) + additions, "proposals": statuses,
            "executor": draft.executor, "created_by": draft.created_by,
            "producer_reported": draft.producer.model_dump(), "external_agent_execution_verified": False,
            "semantic_truth_verified": False, "formal_catalog_updated": False, "human_accept_created": False}


def _display(p, field: str) -> str:
    value = getattr(p.row, field)
    kind = p.field_bases[field].kind
    if kind == "PROPOSED":
        return "建议（未验证、未执行）：" + value
    if kind == "SOURCE_CELL":
        return "原表陈述（未核验）：" + value
    if field == "root_cause" and kind in {"CITED_FACT", "CODE_INFERENCE"} and p.evidence_scope == "INDEPENDENT_TECHNICAL_PATTERN":
        return "资料机制（客户关联未确认）：" + ("代码推断：" if kind == "CODE_INFERENCE" else "") + value
    if kind == "CODE_INFERENCE":
        return "代码推断：" + value
    return value


def _core(item: dict) -> list:
    raw = item.get("raw", {})
    pick = lambda *keys: next((raw[key] for key in keys if raw.get(key)), "")
    return [item["item_id"], "原库", pick("模式名称", "故障模式名称", "description") or item["description"],
            pick("故障原因", "mechanism") or item["mechanism"], pick("故障影响", "effect"),
            pick("案例链接", "links", "link", "url")]


def draft_workbook(request: dict, draft: CatalogDraft, validation: dict) -> dict:
    context = request["payload"]
    additions = [p for p in draft.proposals if p.action == "ADD"]
    merged = [_core(item) for item in context["catalog"]]
    merged.extend([p.proposal_id, "新增草案", *[_display(p, key) for key in
                  ("pattern_name", "root_cause", "effect", "case_links")]] for p in additions)
    evidence = []
    facts = {f["fact_id"]: f for f in context["independent_technical_facts"]}
    for p in draft.proposals:
        for field, basis in p.field_bases.items():
            head = [p.proposal_id, COLUMNS[field], basis.kind, basis.note]
            for fid in basis.fact_ids:
                fact = facts[fid]
                for ref in fact["evidence"]:
                    evidence.append([*head, fid, fact["url"], fact["issue_label"], ref["segment_id"],
                                     ref["quote"], fact["value"], fact["capture_status"]])
            for cell in basis.source_cells:
                source = next(case["source_case"] for case in context["cases"] if case["case_id"] == cell.case_id)
                evidence.append([*head, cell.case_id, f"{source['sheet']}!{cell.cell}", cell.field,
                                 "", cell.quote, source["raw"][cell.field], "原始表格陈述"])
            if not basis.fact_ids and not basis.source_cells:
                evidence.append([*head, "", "", "", "", "", "", ""])
    sheets = [
        {"name": "新增草案（15列）", "columns": list(COLUMNS.values()),
         "rows": [[_display(p, key) for key in COLUMNS] for p in additions]},
        {"name": "合并核对（共有字段）", "columns": ["ID", "来源", "模式名称", "故障原因", "故障影响", "案例链接"], "rows": merged},
        {"name": "草案状态", "columns": ["提案ID", "动作", "实现归属", "证据范围", "根因状态", "处理状态", "缺口", "冲突", "注入执行", "正式入库"],
         "rows": [[s["proposal_id"], s["action"], s["implementation_owner"], s["evidence_scope"], s["root_cause_status"],
                   s["processing_status"], "\n".join(s["unknowns"]), "\n".join(s["conflicts"]), "未执行", "否"] for s in validation["proposals"]]}]
    changes = [p for p in draft.proposals if p.action != "ADD"]
    if changes:
        sheets.append({"name": "既有模式调整建议", "columns": ["提案ID", "目标模式ID", "动作", *COLUMNS.values()],
            "rows": [[p.proposal_id, p.target_item_id, p.action, *[_display(p, key) for key in COLUMNS]] for p in changes]})
    sheets.append({"name": "字段与来源依据", "columns": ["提案ID", "字段", "依据类型", "说明", "事实或来源ID",
        "地址或单元格", "子问题或字段", "片段ID", "精确引文", "原始事实值", "采集范围"], "rows": evidence})
    return {"schema_version": "1.0", "source_report": "catalog_draft.json", "sheets": sheets}


def write_new_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def export_draft(store: Store, run_id: str, request: dict, response: dict, output: Path) -> dict:
    output = output.resolve()
    if output.is_relative_to(store.root):
        raise AuditError("Read-only catalog draft output must be outside the state directory")
    validation = validate_draft(store, run_id, request, response)
    if validation["errors"]:
        return {"validation": validation, "outputs": {}}
    draft = CatalogDraft.model_validate(response)
    workbook = draft_workbook(request, draft, validation)
    # Fresh outputs preserve revisions; an existing directory is never appended to.
    output.mkdir(parents=True, exist_ok=False)
    files = {name: str(output / filename) for name, filename in (
        ("request", "request.json"), ("draft", "catalog_draft.json"), ("validation", "validation.json"),
        ("baseline", "baseline_original.json"), ("workbook_data", "workbook_data.json"),
        ("preview_tsv", "merged_preview.tsv"))}
    for key, value in (("request", request), ("draft", response), ("validation", validation),
                       ("baseline", {"identity": request["payload"]["baseline_identity"],
                                     "items": request["payload"]["catalog"]}), ("workbook_data", workbook)):
        write_new_json(Path(files[key]), value)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    table = workbook["sheets"][1]
    # Excel formula injection escaping is presentation-only; JSON stays lossless.
    safe = lambda value: "'" + str(value) if str(value).lstrip("\ufeff \t\r\n").startswith(("=", "+", "-", "@")) else value
    writer.writerow(table["columns"])
    writer.writerows([[safe(value) for value in row] for row in table["rows"]])
    Path(files["preview_tsv"]).write_text(buffer.getvalue(), encoding="utf-8-sig")
    return {"validation": validation, "outputs": files}
