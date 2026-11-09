"""Read-only Baseline export and immutable rule attribution. Never run devices."""
from __future__ import annotations

import copy
from pathlib import Path
import re
from pydantic import ValidationError

from .store import AuditError, digest
from .precision_contracts import PrecisionContext, BindingDraft, BoundRules
from . import precision_target as target

BRIDGE_VERSION = "precision-bridge-0.1.18"
TRIGGER_REF = re.compile(r"^TRIGGER-(1\.(?:\d+|C)\.\d+):\s*\S.*$", re.S)
CODE_REF = re.compile(r"^CODE-([A-Za-z0-9][A-Za-z0-9_-]*):\s*\S.*$", re.S)


def policy_hash():
    from . import precision_contracts, precision_gate, precision_native
    from .input_budget import budget_policy
    return digest({"version": BRIDGE_VERSION, "sources": [target.file_hash(m.__file__) for m in
        (precision_contracts, target, precision_gate, precision_native)], "bridge": target.file_hash(__file__), "input_budget": budget_policy()})


def _parse(model, value):
    try:
        return model.model_validate(value)
    except ValidationError as exc:
        raise AuditError("Invalid Precision Bridge contract: " + str(exc)) from exc


def _context(store, run_id, description, *, baseline_id=None, mode_ids=None, blind=False):
    baseline = None; modes = []; v4 = None; links = {}
    if blind:
        api42 = {"scheme": "ORIGINAL42_TARGET", "file_sha256": description["library_file_sha256"],
            "coverage_text_sha256": description["library_text_sha256"], "items": description["api42_items"],
            "families": description["api42_families"], "context": description["api42_context"]}
    else:
        if store is None:
            raise AuditError("Known-pattern export/check requires its live read-only Baseline state")
        from .trigger_workflow import _baseline
        from .knowledge_common import PROFILE
        from .trigger_v4 import LEGACY_VERSION
        frozen = _baseline(store, run_id, baseline_id)
        if frozen.get("knowledge_profile") != PROFILE or frozen.get("input_condition_scheme") != "ORIGINAL42":
            raise AuditError("Bridge requires a frozen Builder Baseline with original42; no revised42 substitution")
        original = store.get(run_id, "trigger_taxonomies", frozen["taxonomy_id"])
        if original.get("definition_version") != LEGACY_VERSION:
            raise AuditError("Bridge API42 definition version is not the original version")
        comparison = target.compare_api42(original, description)
        available = {m["mode_id"]: m for m in frozen["mode_records"]}
        selected = sorted(mode_ids if mode_ids is not None else available)
        if not selected or len(selected) != len(set(selected)) or not set(selected) <= set(available):
            raise AuditError("Selected mode IDs must be unique and present in the frozen Baseline")
        modes = [copy.deepcopy(available[k]) for k in selected]
        baseline = {k: frozen[k] for k in ("run_id", "baseline_id", "baseline_version", "index_hash", "status", "mode_ids", "coverage_kind")}
        baseline["selected_mode_ids"] = selected
        api42 = {"scheme": "ORIGINAL42", "registry": frozen["api42_registry"], "taxonomy": original,
            "comparison": comparison, "automatic_label_conversion": False}
        v4_source = store.get(run_id, "trigger_v4_taxonomies", frozen["v4_taxonomy_id"])
        v4 = {k: v4_source[k] for k in ("taxonomy_id", "definition_version", "source_sha256", "items", "constructions", "guides", "mounts")}
        v4["methods"] = [m for m in v4_source["methods"] if m["method_id"] in {"E1", "E2", "E3", "E4", "E5"}]
        for assessment in frozen["condition_index"]:
            if assessment["mode_id"] not in selected:
                continue
            for index, link in enumerate(assessment.get("label_links", [])):
                if link["scheme"] in {"ORIGINAL42", "V4"}:
                    links[assessment["assessment_id"] + ":link-" + str(index)] = {
                        "mode_id": assessment["mode_id"], "assessment_id": assessment["assessment_id"],
                        "issue_index": assessment.get("issue_index"), "link": copy.deepcopy(link)}
    body = {"schema_version": "cann_precision_context.v1", "purpose": "BLIND_DISCOVERY" if blind else "KNOWN_PATTERN_VALIDATION",
        "blind_evaluation": blind, "bridge_policy_hash": policy_hash(), "baseline": baseline, "modes": modes,
        "api42": api42, "v4": v4, "condition_links": links, "target": description,
        "input_scope": {"selected_modes_complete": True, "selected_mode_count": len(modes),
            "full_baseline_mode_count": len(baseline["mode_ids"]) if baseline else 0,
            "omitted_modes": sorted(set(baseline["mode_ids"]) - {m["mode_id"] for m in modes}) if baseline else [],
            "v4_layers_separate": True, "source_and_runtime_versions_distinct": True,
            "new_agent_session_required": True, "actual_agent_context_isolation_attested": False,
            "device_execution": "NOT_RUN", "automatic_adoption": False}}
    return _parse(PrecisionContext, {**body, "context_hash": digest(body)})


def export_context(store, run_id, repo, slug, output, *, baseline_id=None, mode_ids=None, expected_commit=target.AUDITED_COMMIT):
    description = target.describe(repo, slug, expected_commit=expected_commit)
    value = _context(store, run_id, description, baseline_id=baseline_id, mode_ids=mode_ids)
    path = target.protect_output(output, store=store, repo=repo)
    target.immutable_json(path, value.model_dump())
    return {"context": str(path), "context_hash": value.context_hash, "mode_count": len(value.modes),
        "purpose": value.purpose, "baseline_version": value.baseline["baseline_version"], "state_written": False}


def export_blind(repo, slug, output, *, expected_commit=target.AUDITED_COMMIT):
    value = _context(None, None, target.describe(repo, slug, expected_commit=expected_commit), blind=True)
    path = target.protect_output(output, repo=repo)
    target.immutable_json(path, value.model_dump())
    return {"context": str(path), "context_hash": value.context_hash, "purpose": value.purpose,
        "known_mode_knowledge_exported": False, "actual_agent_context_isolation_attested": False, "state_written": False}


def current_context(value, store=None):
    value = value if isinstance(value, PrecisionContext) else _parse(PrecisionContext, value)
    if value.bridge_policy_hash != policy_hash():
        raise AuditError("BRIDGE_POLICY_CHANGED: re-export context; retain old artifacts")
    if value.target["commit"] != target.AUDITED_COMMIT:
        raise AuditError("TARGET_REAUDIT_REQUIRED: this Bridge release has not reviewed that commit")
    description = target.describe(value.target["repo_path"], value.target["task_slug"])
    baseline = value.baseline or {}
    fresh = _context(store, baseline.get("run_id"), description, baseline_id=baseline.get("baseline_id"),
        mode_ids=baseline.get("selected_mode_ids"), blind=value.blind_evaluation)
    if fresh.context_hash != value.context_hash:
        raise AuditError("CONTEXT_STALE: Baseline or target assets changed; no old binding may be reused")
    return value


def native_rules(path):
    suite = target.read_json(path)
    if not isinstance(suite, list) or not suite:
        raise AuditError("Native test_suite must be a nonempty array, not a normalized internal_suite")
    result = {}
    for rule in suite:
        if (not isinstance(rule, dict) or type(rule.get("id")) is not int or rule["id"] < 0
                or rule["id"] in result or not isinstance(rule.get("inputs"), list) or not rule["inputs"]
                or not isinstance(rule.get("generate_intent"), str) or not rule["generate_intent"].strip()
                or not isinstance(rule.get("trigger_library_ref"), list) or not rule["trigger_library_ref"]):
            raise AuditError("Native rule identity, intent, inputs and trigger references must be explicit and unique")
        for group in rule["inputs"]:
            for entry in (group if isinstance(group, list) else [group]):
                if isinstance(entry, dict) and entry.get("type") in {"tensor", "tensors", "tensor_tuple"}:
                    shape = entry.get("shape")
                    if not isinstance(shape, list) or any(type(d) is not int or d < 0 for d in shape):
                        raise AuditError("Native tensor shape needs concrete nonnegative integer dimensions")
        result[rule["id"]] = rule
    return result


def references(rule, ids):
    api, codes = set(), set()
    for ref in rule["trigger_library_ref"]:
        if not isinstance(ref, str):
            raise AuditError("Native trigger references must be strings")
        a, c = TRIGGER_REF.fullmatch(ref.strip()), CODE_REF.fullmatch(ref.strip())
        if a and a[1] in ids: api.add(a[1])
        elif c: codes.add(c[1])
        else: raise AuditError("Unknown/malformed API trigger or V4-as-API reference: " + ref)
    return api, codes


def _unique(values, name):
    if len(values) != len(set(values)):
        raise AuditError(name + " must be unique")
    return set(values)


def _protocol(protocol, binding, rules):
    if protocol.target_case_id != binding.case_id:
        raise AuditError("E protocol must preserve this binding's target call")
    ids = _unique([p.call_id for p in protocol.participants], "Participant calls")
    if protocol.target_call_id not in ids or any(p.case_id not in rules for p in protocol.participants):
        raise AuditError("E protocol participants must reference actual suite cases")
    target_call = next(p for p in protocol.participants if p.call_id == protocol.target_call_id)
    if target_call.role != "TARGET" or target_call.case_id != binding.case_id:
        raise AuditError("The named comparison target must be the target participant")
    expected_inputs = rules[binding.case_id]["inputs"]
    if any(p.role == "TARGET" and digest(rules[p.case_id]["inputs"]) != digest(expected_inputs) for p in protocol.participants):
        raise AuditError("All compared target invocations must preserve target arguments")
    if protocol.method_id in {"E2", "E4"}:
        compared = [p for p in protocol.participants if p.role == "TARGET" or protocol.method_id == "E4" and p.role == "INTERFERER"]
        for participant in compared:
            if not any(p.role == "CONTROL" and p.output_owner == participant.output_owner
                    and digest(rules[p.case_id]["inputs"]) == digest(rules[participant.case_id]["inputs"]) for p in protocol.participants):
                raise AuditError("Each compared target/interferer needs its own serial control and output ownership")
    roles = [p.role for p in protocol.participants]
    if (protocol.method_id == "E1" and (protocol.repeats < 2 or not protocol.reset_policy.strip())
        or protocol.method_id == "E2" and (roles.count("PREDECESSOR") < 2 or "CONTROL" not in roles)
        or protocol.method_id == "E3" and not protocol.output_prefill.strip()
        or protocol.method_id == "E4" and ("INTERFERER" not in roles or "CONTROL" not in roles)
        or protocol.method_id == "E5" and (roles.count("RANK") < 2 or not protocol.participation_config.strip())):
        raise AuditError("Incomplete " + protocol.method_id + " execution-design protocol")


def validate_draft(context, draft, suite_path):
    draft = draft if isinstance(draft, BindingDraft) else _parse(BindingDraft, draft)
    if draft.context_hash != context.context_hash or draft.purpose != context.purpose or draft.suite_sha256 != target.file_hash(suite_path):
        raise AuditError("Binding draft context, purpose or complete suite hash differs")
    if draft.request_hash != draft_request(context.model_dump(), suite_path)["request_hash"]:
        raise AuditError("Binding draft belongs to an old/other whole model request")
    check = draft.self_check
    if not check.passed or not all((check.numeric_meaning_checked, check.citations_checked,
        check.counterevidence_checked, check.issue_scope_checked, check.event_vs_technical_checked)):
        raise AuditError("Binding needs the bounded Agent self-check; never a human ACCEPT")
    rules = native_rules(suite_path)
    if _unique([b.case_id for b in draft.rules], "Bound case IDs") != set(rules):
        raise AuditError("Bind every actual native case exactly once; no omitted/prefix-only suite")
    modes = {m["mode_id"]: m for m in context.modes}
    api_ids = {i["id"] for i in context.target["api42_items"]}
    works = {}; non_api = set()
    for b in draft.rules:
        rule = rules[b.case_id]
        if b.inputs_sha256 != digest(rule["inputs"]):
            raise AuditError("Case inputs differ from the Agent-reviewed binding")
        api, codes = references(rule, api_ids)
        if _unique(b.api_trigger_ids, "Bound API IDs") != api or _unique(b.code_ids, "Bound CODE IDs") != codes:
            raise AuditError("Binding API/CODE refs must exactly match the native rule")
        if context.blind_evaluation and (b.mode_links or b.protocols):
            raise AuditError("Blind tasks cannot inherit known-mode links or E-method knowledge")
        if not context.blind_evaluation and not b.mode_links:
            raise AuditError("Known-pattern rules require explicit grounded mode links")
        _unique([l.mode_id for l in b.mode_links], "Mode links")
        linked_api, methods = set(), set()
        excluded = bool(b.mode_links)
        for link in b.mode_links:
            if link.mode_id not in modes:
                raise AuditError("Binding mode is outside the selected frozen scope")
            mode = modes[link.mode_id]
            if not _unique(link.evidence_keys, "Mode evidence keys") <= set(mode["evidence_index"]):
                raise AuditError("Unknown or cross-mode evidence key")
            for key, field in (("api_trigger_ids", "api_trigger_ids"), ("v4_class_ids", "v4_class_ids"),
                ("v4_scenario_ids", "v4_scenario_ids"), ("execution_method_ids", "execution_method_ids")):
                if not _unique(getattr(link, key), key) <= set(mode[field]):
                    raise AuditError("Independent-axis label is absent from this mode's frozen classification: " + key)
            proofs = []
            for key in _unique(link.condition_link_keys, "Condition proof keys"):
                proof = context.condition_links.get(key)
                if not proof or proof["mode_id"] != link.mode_id:
                    raise AuditError("Condition proof belongs to another mode/issue")
                proofs.append(proof["link"])
            for scheme, selected in (("ORIGINAL42", link.api_trigger_ids), ("V4", link.v4_class_ids)):
                if set(selected) != {p["trigger_id"] for p in proofs if p["scheme"] == scheme}:
                    raise AuditError("Every selected condition needs its exact independent classification proof")
            constructors = {k for p in proofs if p["scheme"] == "V4" for k in p.get("construction_ids", [])}
            if not set(link.v4_scenario_ids) <= constructors:
                raise AuditError("V4 scenario needs its own explicit construction proof; class IDs are not constructions")
            linked_api.update(link.api_trigger_ids); methods.update(link.execution_method_ids)
            exclusion_roles = set()
            for rationale in mode["classification_rationales"]:
                if rationale["axis"] == "API42" and rationale["summary"]["status"] == "NOT_APPLICABLE":
                    exclusion_roles.update(mode["evidence_index"].get(rationale["assessment_id"] + ":" + fid, {}).get("role")
                        for fid in rationale["summary"].get("exclusion_fact_ids", []))
            excluded &= exclusion_roles == {"INTERNAL_COMPUTATION"}
        if not context.blind_evaluation and linked_api != api:
            raise AuditError("Native API refs cannot be inherited from a different mode or inferred from V4")
        if _unique([p.method_id for p in b.protocols], "E protocols") != methods:
            raise AuditError("Every selected E method needs its own protocol, and no unlinked protocol is accepted")
        for p in b.protocols: _protocol(p, b, rules)
        if _unique([j.code_id for j in b.code_justifications], "CODE justifications") != codes:
            raise AuditError("Every CODE reference needs a separate source-grounded justification")
        for j in b.code_justifications:
            for citation in j.source_evidence: target.verify_citation(context.target, citation)
            if j.kind == "EXECUTION_METHOD" and not b.protocols:
                raise AuditError("Execution-only CODE justification requires a complete E protocol")
        independent_non_api = False
        if b.non_api_basis:
            if not codes or not all(j.kind == "CODE_PATH" for j in b.code_justifications):
                raise AuditError("Independent non-API code basis must belong to actual CODE_PATH references")
            for citation in b.non_api_basis.source_evidence: target.verify_citation(context.target, citation)
            if not any(b.non_api_basis.positive_fact in c.quote for c in b.non_api_basis.source_evidence):
                raise AuditError("A positive non-API fact must occur in its exact code quotation; missing fields are insufficient")
            if b.non_api_basis.role != "INTERNAL_COMPUTATION" and not b.protocols:
                raise AuditError("Execution-context evidence needs a complete E protocol, not a single-call CODE_PATH label")
            independent_non_api = b.semantic_review.status == "CHECKED"
        if codes and not api and (independent_non_api or not context.blind_evaluation and (b.protocols or excluded)):
            non_api.add(b.case_id)
        if b.semantic_review.status == "CHECKED" and not b.semantic_review.source_evidence:
            raise AuditError("A checked legal-domain claim needs exact operator source/API quotations")
        for citation in b.semantic_review.source_evidence: target.verify_citation(context.target, citation)
        protocol_key = []
        for p in b.protocols:
            v = p.model_dump(exclude={"target_case_id", "target_call_id", "participants"})
            v["participants"] = [{**a.model_dump(exclude={"case_id", "call_id"}),
                "inputs_sha256": digest(rules[a.case_id]["inputs"])} for a in p.participants]
            protocol_key.append(v)
        works[str(b.case_id)] = digest({"target_commit": context.target["commit"], "task": context.target["task_slug"],
            "assets": context.target["task_assets"], "inputs": rule["inputs"], "seed": b.experiment_seed, "protocols": protocol_key})
    return draft, works, non_api


def bind(store, context_value, suite, assignment, output):
    context = current_context(context_value, store)
    if isinstance(assignment, dict) and assignment.get("outcome") == "BLOCKED":
        request = draft_request(context.model_dump(), suite)
        if (assignment.get("request_hash") != request["request_hash"]
                or assignment.get("reason_code") != "EXECUTOR_CONTEXT_LIMIT"
                or not isinstance(assignment.get("reason"), str) or not assignment["reason"].strip()):
            raise AuditError("Executor blocking requires the current OUTER hash, context-limit code and reason")
        block = {"schema_version": "cann_precision_binding_block.v1", "status": "BLOCKED",
            "reason": "EXECUTOR_CONTEXT_LIMIT", "context_hash": context.context_hash,
            "suite_sha256": target.file_hash(suite), "raw_response": assignment,
            "binding_created": False, "hardware_validated": False, "state_written": False}
        path = target.protect_output(output, store=store, repo=context.target["repo_path"])
        target.immutable_json(path, block)
        return {"block": str(path), "status": "BLOCKED", "reason": block["reason"],
            "binding_created": False, "state_written": False}
    draft, works, _ = validate_draft(context, assignment, suite)
    body = {"schema_version": "cann_precision_bindings.v1", "bridge_policy_hash": policy_hash(),
        "draft": draft.model_dump(), "execution_work_ids": works}
    value = _parse(BoundRules, {**body, "binding_hash": digest(body)})
    # Check again after file reads; a changed source cannot receive a current binding.
    current_context(context, store)
    path = target.protect_output(output, store=store, repo=context.target["repo_path"])
    target.immutable_json(path, value.model_dump())
    return {"bindings": str(path), "binding_hash": value.binding_hash, "case_count": len(draft.rules),
        "unique_input_spec_work_count": len(set(works.values())), "status": "BOUND_PENDING_GATE",
        "hardware_validated": False, "state_written": False}


def draft_request(context_value, suite):
    from .input_budget import finalize_model_task
    context = _parse(PrecisionContext, context_value)
    rules = native_rules(suite)
    return finalize_model_task({"kind": "precision_bind", "payload": {"context": context.model_dump(),
        "suite": list(rules.values()), "suite_sha256": target.file_hash(suite),
        "input_scope": {"context_and_suite_complete": True, "external_source_reading_not_attested": True},
        "response_schema": BindingDraft.model_json_schema(),
        "case_inputs_sha256": {str(k): digest(v["inputs"]) for k, v in rules.items()}},
        "instructions": "Read the complete context and suite in an independent worker. Return BindingDraft with the OUTER request_hash. "
            "Bind every case exactly once; cite frozen mode evidence and independent condition proof keys. "
            "Cite exact selected operator source/API lines for legality. Missing facts stay NEEDS_FACTS; "
            "E1-E5 require complete design protocols, not a device result. CODE-only is not a fake API trigger. "
            "Do not modify original tasks/prompts/libraries or generate human ACCEPT. No NPU/GPU/queue execution. "
            "If the complete task does not fit, report BLOCKED rather than returning a shortened successful binding."})
