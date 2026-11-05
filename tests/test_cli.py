"""Source-checkout CLI acceptance tests using synthetic local files only."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parent
RUNNER = PROJECT / "run_faultaudit.py"


class CLITests(unittest.TestCase):
    def setUp(self):
        scratch = PROJECT / "tests" / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="faultaudit-cli-", dir=scratch)
        self.root = Path(self.temp.name)
        self.state = self.root / "state"

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args, expected=0):
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        # Tests never acquire a real model endpoint or API key from the host.
        for key in ("FAULTAUDIT_BASE_URL", "FAULTAUDIT_MODEL", "FAULTAUDIT_API_KEY"):
            environment.pop(key, None)
        process = subprocess.run(
            [sys.executable, str(RUNNER), "--state", str(self.state), *map(str, args)],
            cwd=self.root, env=environment, capture_output=True, text=True,
            encoding="utf-8", errors="strict", timeout=30,
        )
        self.assertEqual(process.returncode, expected, f"stdout={process.stdout}\nstderr={process.stderr}")
        self.assertFalse(process.stderr, process.stderr)
        return json.loads(process.stdout)

    def write_json(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def input_files(self):
        source = self.write_json("cases.json", [
            {"序号": "ROW-C", "统一ID": "CASE-ALPHA", "来源": "合成周报 r1", "客户/模型": "合成模型",
             "问题描述": "[合成] token乱码", "算子": "all_reduce", "根因": "原始周报归因一，须原样保留",
             "wiki": "https://example.invalid/wiki/shared", "DTS": "", "PR": ""},
            {"序号": "ROW-D", "统一ID": "CASE-BETA", "来源": "合成周报 r2", "客户/模型": "合成模型",
             "问题描述": "[合成] 确定性问题", "算子": "rope", "根因": "原始周报归因二",
             "wiki": "https://example.invalid/wiki/shared"},
            {"序号": "ROW-E", "统一ID": "CASE-GAMMA", "问题描述": "[合成] 无链接也不能遗漏", "根因": "待定位"},
        ])
        catalog = self.write_json("catalog.json", [
            {"item_id": "C-001", "description": "[合成] 通信精度", "operator": "all_reduce", "mechanism": "rounding", "trigger": "PCIe"},
            {"item_id": "C-002", "description": "[合成] 缓存未加载", "operator": "rope", "mechanism": "cache", "trigger": "wakeup"},
        ])
        return source, catalog

    def test_doctor_reports_configuration_without_creating_state(self):
        value = self.run_cli("doctor")
        self.assertTrue(value["version"])
        self.assertTrue(value["dependencies"]["pydantic"])
        self.assertTrue(value["dependencies"]["openpyxl"])
        self.assertEqual(value["model_service"]["owner"], "opencode")
        self.assertEqual(value["model_service"]["transport"], "file-task-bridge")
        self.assertFalse(value["model_service"]["credentials_in_core"])
        self.assertFalse(value["model_service"]["network_execution_in_core"])
        self.assertNotIn("deepseek", value)
        self.assertFalse(self.state.exists())

    def test_import_fetch_ingest_run_export_and_strict_validation(self):
        source, catalog = self.input_files()
        imported = self.run_cli("import", "--input", source, "--source-kind", "ORIGINAL_WEEKLY", "--catalog", catalog)
        run_id = imported["run_id"]
        self.assertEqual(imported["validation"]["counts"]["cases"], 3)
        self.assertEqual(imported["validation"]["counts"]["reference_occurrences"], 2)
        self.assertEqual(imported["validation"]["counts"]["catalog_items"], 2)

        tasks_path = self.root / "fetch_tasks.json"
        fetched = self.run_cli("fetch-tasks", "--run", run_id, "--out", tasks_path)
        self.assertEqual(fetched["count"], 1)
        tasks = json.loads(tasks_path.read_text(encoding="utf-8"))["fetch_tasks"]
        self.assertEqual(len(tasks[0]["case_ids"]), 2)
        self.assertEqual(len(tasks[0]["references"]), 2)
        self.assertEqual(tasks[0]["retrieval_status"], "NOT_FETCHED")

        evidence = self.write_json("evidence.json", {
            "url": tasks[0]["url"], "title": "合成资料，非真实Wiki", "status": "COMPLETE",
            "text": "合成证据正文：本页包含 all_reduce 与 rope 两类讨论，不能仅凭共享链接合并事件。",
            "components": {"body": "COMPLETE"}, "retrieved_by": "cli-test-fixture", "is_synthetic": True,
        })
        ingested = self.run_cli("ingest-evidence", "--run", run_id, "--package", evidence)
        self.assertEqual(len(ingested["snapshots"]), 1)
        self.assertEqual(ingested["snapshots"][0]["status"], "COMPLETE")
        current_tasks = self.run_cli("fetch-tasks", "--run", run_id)["fetch_tasks"]
        self.assertEqual(current_tasks, [], "Captured evidence needs no repeated collection task")

        result = self.run_cli("run", "--run", run_id, "--mode", "mock", "--resume")
        self.assertTrue(result["valid"], result)
        self.assertFalse(result["complete"])
        self.assertEqual(result["batch_status"], "COMPLETE_WITH_PENDING")
        self.assertEqual(result["counts"]["cases"], 3)
        self.assertEqual(result["counts"]["planned_associations"], 2)
        self.assertEqual(result["counts"]["judged_associations"], 2)
        self.assertEqual(result["counts"]["task_states"].get("FAILED", 0), 0)
        self.assertTrue(any("no references" in pending for pending in result["pending"]))

        exported = self.run_cli("export", "--run", run_id, "--out", self.root / "report")
        for name in ("report_json", "report_html", "summary_tsv", "workbook_data"):
            self.assertTrue(Path(exported["outputs"][name]).is_file(), name)
        report = json.loads(Path(exported["outputs"]["report_json"]).read_text(encoding="utf-8"))
        self.assertEqual(len(report["cases"]), 3)
        first_case = next(case for case in report["cases"] if case["external_id"] == "CASE-ALPHA")
        self.assertEqual(first_case["raw"]["根因"], "原始周报归因一，须原样保留")
        self.assertEqual(len(report["judgments"]), 2)
        self.assertTrue(all(j["model_mode"] == "mock" for j in report["judgments"]))
        self.assertTrue(all(j["event_relation"] == "UNDETERMINED" for j in report["judgments"]))
        self.assertTrue(all(m["overall"] == "UNDETERMINED" for m in report["mappings"]))
        self.assertTrue(all(len(m["catalog_results"]) == 2 for m in report["mappings"]))

        normal = self.run_cli("validate", "--run", run_id)
        strict = self.run_cli("validate", "--run", run_id, "--strict", expected=2)
        self.assertTrue(normal["valid"])
        self.assertFalse(strict["complete"])

        # Resume reuses work and importing the same original file does not drop
        # or duplicate rows, occurrences, summaries, or judgments.
        resumed = self.run_cli("run", "--run", run_id, "--mode", "mock", "--resume")
        self.assertEqual(result["counts"], resumed["counts"])
        repeated = self.run_cli("import", "--run", run_id, "--input", source, "--source-kind", "ORIGINAL_WEEKLY")
        self.assertEqual(repeated["validation"]["counts"]["cases"], 3)
        self.assertEqual(repeated["validation"]["counts"]["reference_occurrences"], 2)

    def test_opencode_handoff_works_without_core_model_configuration(self):
        source, _ = self.input_files()
        imported = self.run_cli("import", "--input", source)
        run_id = imported["run_id"]
        evidence = self.write_json("evidence.json", {
            "url": "https://example.invalid/wiki/shared", "title": "Synthetic only",
            "text": "Synthetic all_reduce precision discussion; event attribution remains unconfirmed.",
            "status": "COMPLETE", "components": {"body": "COMPLETE"}, "is_synthetic": True,
        })
        self.run_cli("ingest-evidence", "--run", run_id, "--package", evidence)
        waiting = self.run_cli("run", "--run", run_id, "--mode", "opencode")
        self.assertTrue(waiting["valid"])
        self.assertFalse(waiting["complete"])
        self.assertEqual(waiting["counts"]["task_states"].get("FAILED", 0), 0)
        requests_path = self.root / "model_tasks.json"
        exported = self.run_cli("model-tasks", "--run", run_id, "--out", requests_path)
        self.assertEqual(exported["ready_model_tasks"], 1)
        task = json.loads(requests_path.read_text(encoding="utf-8"))["tasks"][0]
        self.assertEqual(task["kind"], "summarize")
        snapshot = task["payload"]["snapshot"]
        segment = snapshot["segments"][0]
        envelope = {"schema_version": "1.0", "run_id": run_id, "task_id": task["task_id"],
            "request_hash": task["request_hash"], "producer": {"executor": "opencode", "opencode_version": "2.2.0",
                "provider": "synthetic-only", "model": "synthetic-model", "session_id": "offline-cli-test"},
            "result": {"snapshot_id": snapshot["snapshot_id"], "issues": [{"label": "Synthetic only", "facts": [
                {"field": "observation", "value": segment["text"], "evidence": [{"segment_id": segment["segment_id"], "quote": segment["text"]}]}]}],
                "unknown_fields": ["event attribution"]}}
        response_path = self.write_json("model_results.json", {"results": [envelope]})
        submitted = self.run_cli("submit-model-results", "--run", run_id, "--file", response_path)
        self.assertEqual(submitted["accepted"], 1)
        self.assertEqual(submitted["ready_model_tasks"], 2)
        repeated = self.run_cli("submit-model-results", "--run", run_id, "--file", response_path)
        self.assertEqual(repeated["idempotent"], 1)
        self.run_cli("model-tasks", "--run", run_id, "--out", requests_path)
        compare_tasks = json.loads(requests_path.read_text(encoding="utf-8"))["tasks"]
        self.assertEqual([task["kind"] for task in compare_tasks], ["compare", "compare"])
        report = self.run_cli("export", "--run", run_id, "--out", self.root / "opencode-report")
        self.assertTrue(Path(report["outputs"]["report_html"]).is_file())


if __name__ == "__main__":
    unittest.main()
