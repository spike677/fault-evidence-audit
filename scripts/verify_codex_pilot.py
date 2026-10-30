"""Check an independently executed synthetic pilot against withheld expectations.

This script never generates model responses. Semantic attack probes are checked
without saving them, and accepted model proposals remain pending human review.
"""
from __future__ import annotations

import argparse
import copy
import html
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from faultaudit.bridge import submit_model_results
from faultaudit import __version__
from faultaudit.exporters import export_report
from faultaudit.model import validate_task_result
from faultaudit.pipeline import evidence_index, report_data
from faultaudit.store import Store, digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT / "work" / "codex_pilot")
    parser.add_argument("--run", default="latest")
    args = parser.parse_args()
    directory = args.root.resolve()
    expected = json.loads((directory / "expectations.json").read_text(encoding="utf-8"))
    store = Store(directory / "state")
    try:
        run_id = store.run_info(args.run)["run_id"]
        data = report_data(store, run_id)
        cases = {case["case_id"]: case for case in data["cases"]}
        snapshots = {snapshot["snapshot_id"]: snapshot for snapshot in data["snapshots"]}
        judgments = [j for j in data["judgments"] if not j["is_stale"]]
        mappings = [m for m in data["mappings"] if not m["is_stale"]]
        checks = []

        def check(name, passed, detail=None):
            checks.append({"name": name, "passed": bool(passed), "detail": detail})

        check("five_source_cases_retained", len(cases) == expected["cases"])
        check("seven_individual_judgments", len(judgments) == expected["associations"])
        check("five_independent_summaries", len([s for s in data["summaries"] if not s["is_stale"]]) == 5)
        shared_snapshot = next((s for s in snapshots.values() if s["url"].endswith("sim-attention-rope")), {})
        shared_summary = next((s for s in data["summaries"] if not s["is_stale"]
                               and s["snapshot_id"] == shared_snapshot.get("snapshot_id")), {})
        issue_values = ["\n".join(json.dumps(fact.get("value"), ensure_ascii=False) for fact in issue.get("facts", []))
                        for issue in shared_summary.get("issues", [])]
        check("shared_wiki_two_separate_issues", any("SIM-ATTN-202" in value and "SIM-ROPE-303" not in value
              and "V scale" in value for value in issue_values) and any("SIM-ROPE-303" in value
              and "SIM-ATTN-202" not in value and "H2D" in value for value in issue_values))
        check("frozen_synthetic_98_catalog", len(data["catalog"]) == 98 and
              data["catalog_selections"][0]["scope"] == "INFERENCE")
        source_rows = json.loads((directory / "inputs" / "cases.json").read_text(encoding="utf-8"))
        check("original_fields_unchanged", sorted(source_rows, key=lambda row: row["统一ID"]) ==
              sorted((case["raw"] for case in cases.values()), key=lambda row: row["统一ID"]))
        by_pair = {(cases[j["case_id"]]["external_id"], snapshots[j["snapshot_id"]]["url"]): j for j in judgments}
        association_results = []
        for criterion in expected["associations_expected"]:
            key = (criterion["external_id"], criterion["url"])
            judgment = by_pair.get(key, {})
            failures = []
            for field in ("event_relation", "pattern_relation", "case_attribution", "support_level"):
                if field in criterion and judgment.get(field) != criterion[field]:
                    failures.append(field)
            if criterion.get("must_not_be_direct") and judgment.get("support_level") == "DIRECT":
                failures.append("unexpected_direct_support")
            if criterion.get("must_not_confirm_root_cause") and judgment.get("claim_support", {}).get("root_cause") == "SUPPORTED":
                failures.append("unexpected_supported_root_cause")
            if "root_cause_support" in criterion and judgment.get("claim_support", {}).get("root_cause") != criterion["root_cause_support"]:
                failures.append("root_cause_support")
            if "allowed_pattern_relations" in criterion and judgment.get("pattern_relation") not in criterion["allowed_pattern_relations"]:
                failures.append("pattern_relation")
            quotes = "\n".join(ref["quote"] for ref in judgment.get("evidence", []))
            if criterion.get("required_issue_anchor") and criterion["required_issue_anchor"] not in quotes:
                failures.append("wrong_shared_wiki_issue")
            if criterion.get("required_issue_anchor"):
                expected_terms = ("V scale", "head") if criterion["external_id"] == "SIM-002" else ("H2D", "pin_memory")
                if not all(term in quotes for term in expected_terms):
                    failures.append("missing_matching_mechanism_quote")
            check("association:" + criterion["external_id"] + ":" + criterion["url"], bool(judgment) and not failures, failures)
            association_results.append({"external_id": key[0], "url": key[1], "passed": bool(judgment) and not failures,
                "actual": {field: judgment.get(field) for field in ("event_relation", "pattern_relation", "case_attribution", "support_level")},
                "reason": judgment.get("short_reason"), "criterion": criterion["criterion"]})
        mapping_results = []
        for external_id, criterion in expected["catalog_expected"].items():
            mapping = next((m for m in mappings if cases[m["case_id"]]["external_id"] == external_id), {})
            rows = mapping.get("catalog_results", [])
            by_id = {row["item_id"]: row for row in rows}
            passed = len(rows) == len(by_id) == 98 and set(by_id) == {item["item_id"] for item in data["catalog"]}
            positives = {row["item_id"] for row in rows if row["result"] in {"COVERED", "PARTIALLY_COVERED"}}
            if "must_cover" in criterion:
                passed = passed and all(by_id.get(item_id, {}).get("result") == "COVERED" for item_id in criterion["must_cover"])
                passed = passed and positives == set(criterion["must_cover"])
            if "all_items_must_be" in criterion:
                passed = passed and all(row["result"] == criterion["all_items_must_be"] for row in rows)
            check("catalog:" + external_id, passed)
            mapping_results.append({"external_id": external_id, "rows": len(rows), "positive_patterns": sorted(positives),
                                    "overall": mapping.get("overall"), "passed": bool(passed)})
        check("model_proposals_never_auto_accepted", all(j.get("review_status") == "NEEDS_REVIEW" for j in judgments)
              and all(m.get("review_status") == "NEEDS_REVIEW" for m in mappings))
        index = evidence_index(store, run_id)
        check("both_shared_artifacts_reverse_indexed", index["shared_evidence_count"] == 2)
        check("valid_but_not_business_complete", data["validation"]["valid"] and not data["validation"]["complete"])
        pr = next((s for s in snapshots.values() if s.get("artifact_type") == "PR"), {})
        check("pr_diff_gap_explicitly_preserved", pr.get("status") == "PARTIAL"
              and pr.get("components", {}).get("diff") == "NOT_FETCHED"
              and pr.get("expected_file_count") == 1 and pr.get("captured_file_count") == 0)
        check("seventeen_actual_codex_results", len(data["model_results"]) == 17 and all(
            result["producer"]["executor"] == "codex" and result["result"]["model_mode"] == "codex"
            for result in data["model_results"]))
        failed_tasks = [task for task in data["tasks"] if task["status"] == "FAILED"]
        check("no_failed_pipeline_tasks", not failed_tasks, failed_tasks)

        rejection_probes = []
        summary_envelope = json.loads((directory / "01_results.json").read_text(encoding="utf-8"))["results"][0]
        for name in ("wrong_executor", "wrong_request_hash", "fabricated_quote"):
            bad = copy.deepcopy(summary_envelope)
            if name == "wrong_executor":
                bad["producer"]["executor"] = "opencode"
            elif name == "wrong_request_hash":
                bad["request_hash"] = "not-the-request-hash"
            else:
                bad["result"]["issues"][0]["facts"][0]["evidence"][0]["quote"] = "FABRICATED QUOTE: absent from every supplied segment"
            try:
                submit_model_results(store, run_id, [bad], executor="codex")
                rejected, reason = False, "Unexpectedly accepted"
            except (ValueError, RuntimeError) as exc:
                rejected, reason = True, str(exc)
            rejection_probes.append({"name": name, "rejected": rejected, "reason": reason})
            check("reject:" + name, rejected)
        with tempfile.TemporaryDirectory(prefix="pilot-probes-", dir=directory) as scratch:
            probe_store = Store(Path(scratch) / "state")
            try:
                probe_run = probe_store.create_run({"is_synthetic": True})
                packages = json.loads((directory / "inputs" / "evidence.json").read_text(encoding="utf-8"))
                probes = [("incomplete_pr_declared_complete", {**packages[-1], "status": "COMPLETE"}),
                    ("authentication_redirect", {**packages[0], "final_url": "https://login.example.invalid/sso"})]
                for name, package in probes:
                    try:
                        probe_store.ingest_evidence(probe_run, package)
                        rejected, reason = False, "Unexpectedly accepted"
                    except ValueError as exc:
                        rejected, reason = True, str(exc)
                    rejection_probes.append({"name": name, "rejected": rejected, "reason": reason})
                    check("reject:" + name, rejected)
                blocked = probe_store.ingest_evidence(probe_run, {"url": "https://example.invalid/codehub/blocked",
                    "status": "NETWORK_BLOCKED", "is_synthetic": True, "text": ""})
                check("network_blocked_preserved", blocked["status"] == "NETWORK_BLOCKED")
            finally:
                probe_store.close()

        # An exact real quote attached to a wrong pattern can pass structural
        # checks. Record this limit without committing the adversarial proposal.
        semantic_probe = {"name": "real_quote_wrong_catalog_pattern", "saved": False}
        before_semantic_probe = digest([store.records(run_id, kind) for kind in ("mappings", "judgments", "model_results")])
        if mappings:
            base = next((m for m in mappings if cases[m["case_id"]]["external_id"] == "SIM-001"), None)
            if base:
                keys = ("case_id", "catalog_results", "overall", "scope", "model_mode", "model_id")
                candidate = copy.deepcopy({key: base[key] for key in keys})
                correct_refs = next(row["evidence"] for row in candidate["catalog_results"] if row["item_id"] == "F-001")
                wrong = next(row for row in candidate["catalog_results"] if row["item_id"] == "F-006")
                wrong.update(result="COVERED", evidence=correct_refs, reason="Adversarial semantic mismatch using a genuine quote")
                try:
                    validate_task_result("catalog", candidate, case=cases[base["case_id"]],
                        judgments=[j for j in judgments if j["case_id"] == base["case_id"]], items=data["catalog"])
                    semantic_probe["structurally_accepted"] = True
                except (ValueError, RuntimeError) as exc:
                    semantic_probe.update(structurally_accepted=False, reason=str(exc))
                semantic_probe["semantic_match"] = False
        semantic_probe["state_unchanged"] = before_semantic_probe == digest([
            store.records(run_id, kind) for kind in ("mappings", "judgments", "model_results")])
        check("semantic_attack_not_saved", semantic_probe["state_unchanged"])
        outputs = export_report(data, directory / "report")
        result = {"run_id": run_id, "core_version": __version__, "synthetic_only": True, "mock_used": False,
            "model_execution": "Current Codex session subagent; no separate model HTTP/CLI invocation by the core",
            "precise_model_id_exposed": False, "precise_codex_backend_version_exposed": False,
            "checks_passed": sum(check["passed"] for check in checks), "checks_total": len(checks),
            "catalog_comparisons": sum(len(m["catalog_results"]) for m in mappings),
            "execution_notes": ["One generic contract clarification distinguished model coverage proposals from human ACCEPT; no withheld scenario answers were supplied."],
            "successful": all(check["passed"] for check in checks), "checks": checks,
            "associations": association_results, "mappings": mapping_results, "rejection_probes": rejection_probes,
            "known_semantic_limit": semantic_probe, "validation": data["validation"], "outputs": outputs,
            "scope_limit": "One run on synthetic data; not real internal collection, DeepSeek validation, or actual 98-pattern accuracy"}
        summary_target = directory / "verification_report.html"
        result["outputs"]["verification_html"] = str(summary_target)
        esc = lambda value: html.escape(str(value))
        association_rows = "".join(
            f'<tr><td>{esc(row["external_id"])}</td><td>{esc(row["criterion"])}</td>'
            f'<td>{esc(row["actual"]["event_relation"])}</td><td>{esc(row["actual"]["support_level"])}</td>'
            f'<td>{"通过" if row["passed"] else "未通过"}</td></tr>' for row in association_results)
        mapping_rows = "".join(
            f'<tr><td>{esc(row["external_id"])}</td><td>{row["rows"]}</td><td>{esc(", ".join(row["positive_patterns"]) or "无")}</td>'
            f'<td>{esc(row["overall"])}</td><td>待人工复核</td></tr>' for row in mapping_results)
        rejection_rows = "".join(f'<tr><td>{esc(row["name"])}</td><td>{"已拒收" if row["rejected"] else "未拒收"}</td>'
                                 f'<td>{esc(row["reason"])}</td></tr>' for row in rejection_probes)
        summary_target.write_text(f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Codex 合成模拟验收</title>
<style>body{{font-family:system-ui,"Microsoft YaHei",sans-serif;max-width:1180px;margin:36px auto;padding:0 20px;color:#193047;line-height:1.6}}h1{{font-size:28px}}h2{{font-size:20px;margin-top:30px}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{border:1px solid #d8e2ec;padding:10px;text-align:left;vertical-align:top;overflow-wrap:anywhere}}th{{background:#edf3f8}}.notice{{background:#fff4df;border-left:4px solid #d89526;padding:16px}}.metrics{{background:#e9f4ef;padding:18px;font-size:20px}}code{{overflow-wrap:anywhere}}</style></head>
<body><h1>Codex 合成模拟验收 · v{esc(__version__)}</h1><p>运行：<code>{esc(run_id)}</code></p>
<p class="metrics">{result["checks_passed"]}/{result["checks_total"]} 项检查通过 · 17 个模型任务 · 7 个关联 · 490 项模式比较</p>
<p>当前 Codex 会话独立读取导出请求，按文件协议完成摘要、关联和模式比较，未使用 mock。输入全部为合成材料，独立验收预期未提供给执行模型。执行中澄清过一次“模型覆盖建议与人工 ACCEPT 不同”的通用合同口径。</p>
<p class="notice"><strong>业务状态：待人工复核。</strong>PR Diff 缺口与两个事件的证据不足均保留。对抗测试确认：真实引文挂到错误模式上仍可通过结构校验，因此不能用结构通过替代语义复核。错误候选没有保存。</p>
<h2>逐关联检查</h2><table><tr><th>记录</th><th>验收目标</th><th>事件关系</th><th>支持强度</th><th>结果</th></tr>{association_rows}</table>
<h2>全库比较</h2><table><tr><th>记录</th><th>比较条目</th><th>正向模式建议</th><th>模型总体建议</th><th>人工状态</th></tr>{mapping_rows}</table>
<h2>错误输入测试</h2><table><tr><th>场景</th><th>结果</th><th>程序理由</th></tr>{rejection_rows}</table>
<h2>适用范围</h2><p>本次仅验证五条合成故障上的协议、引用及目标场景预期，不证明真实内网采集、DeepSeek能力或真实98条故障库准确率。当前会话精确模型ID与后台版本未暴露，生产者如实标注unreported。</p>
<p><a href="verification_result.json">机器可读验收结果</a> · <a href="report/report.html">完整审计报告</a> · <a href="report/report.json">完整原始与模型记录</a></p></body></html>''', encoding="utf-8")
        target = directory / "verification_result.json"
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: result[key] for key in ("run_id", "checks_passed", "checks_total", "successful", "known_semantic_limit")}, ensure_ascii=False))
        return 0 if result["successful"] else 1
    finally:
        store.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
