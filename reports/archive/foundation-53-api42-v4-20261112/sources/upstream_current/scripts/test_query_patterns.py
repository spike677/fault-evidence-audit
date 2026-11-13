#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import query_patterns

ROOT = os.path.dirname(SCRIPT_DIR)


class QueryPatternsTest(unittest.TestCase):
    def test_compositions_are_valid_and_json_serializable(self):
        compositions = query_patterns.load_compositions(ROOT)
        self.assertEqual(3, len(compositions))
        json.dumps(compositions, ensure_ascii=False, allow_nan=False)

    def test_experiments_cover_action_state_lifecycle(self):
        state_actions = {
            "GetWorkspaceSize", "PoisonWorkspace", "ReuseWorkspace", "ReuseExecutor",
            "SwitchStream", "RecordEvent", "WaitEvent", "GraphCapture",
        }
        for composition in query_patterns.load_compositions(ROOT):
            experiment = composition["next_experiment"]
            actions = experiment["actions"]
            types = [action["type"] for action in actions]
            self.assertEqual("deep-experiment/v1", experiment["schema_version"])
            self.assertIn("Execute", types)
            self.assertTrue(state_actions.intersection(types), composition["id"])
            self.assertEqual("Free", types[-1])
            self.assertTrue(experiment["initial_state"])
            self.assertEqual("designed", experiment["provenance"]["coverage_state"])

    def test_query_returns_only_complete_member_closure(self):
        result = query_patterns.query_patterns(["FP-A05", "FP-A21"], root=ROOT)
        self.assertEqual(["COMP-A05-A21"], [c["id"] for c in result["compositions"]])
        self.assertIsNone(result["unknown_pattern_candidate"])
        partial = query_patterns.query_patterns(["FP-A05"], root=ROOT)
        self.assertEqual([], partial["compositions"])
        unrelated = query_patterns.query_patterns(["FP-A05", "FP-A22"], root=ROOT)
        self.assertEqual([], unrelated["compositions"])

    def test_query_rejects_text_or_unknown_ids_instead_of_guessing(self):
        with self.assertRaises(ValueError):
            query_patterns.query_patterns(["workspace dirty data"], root=ROOT)
        with self.assertRaises(ValueError):
            query_patterns.query_patterns(["FP-A99"], root=ROOT)

    def test_unknown_candidate_has_stable_fingerprint_and_pending_state(self):
        failure_a = {
            "operation": "aclnnExample", "oracle": "golden-canary", "code": "mismatch",
            "shape": [1, 3], "address": "0x1000", "timestamp": "2026-11-01T00:00:00Z",
        }
        failure_b = dict(failure_a, shape=[7, 9], address="0xdeadbeef", timestamp="later")
        first = query_patterns.build_unknown_pattern_candidate(
            failure_a, trace_ref="trace/run-a.json")
        second = query_patterns.build_unknown_pattern_candidate(
            failure_b, trace_ref="trace/run-b.json")
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(first["id"], second["id"])
        self.assertEqual("trace/run-a.json", first["trace_ref"])
        self.assertEqual("trace/run-b.json", second["trace_ref"])
        self.assertEqual("golden-canary", first["observed_oracle"])
        self.assertEqual("designed", first["coverage_state"])
        self.assertEqual("pending_verification", first["status"])
        self.assertFalse(first["is_pattern_fact"])
        json.dumps(first, ensure_ascii=False, allow_nan=False)

    def test_unknown_candidate_is_only_generated_without_pattern_hits(self):
        failure = {"operation": "aclnnExample", "code": "E999", "oracle": "error-code"}
        result = query_patterns.query_patterns(
            ["FP-A05"], root=ROOT, failure=failure, trace_ref="trace/known.json")
        self.assertIsNone(result["unknown_pattern_candidate"])
        unmatched = query_patterns.query_patterns(
            [], root=ROOT, failure=failure, trace_ref="trace/unknown.json")
        self.assertEqual("unknown-pattern", unmatched["unknown_pattern_candidate"]["candidate_type"])

    def test_cli_emits_composition_json(self):
        completed = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "query_patterns.py"),
             "--root", ROOT, "--hits", "FP-B07,FP-A05"],
            check=True, capture_output=True, text=True, encoding="utf-8")
        result = json.loads(completed.stdout)
        self.assertEqual(["COMP-B07-A05"], [c["id"] for c in result["compositions"]])

    def test_cli_emits_unknown_candidate_json(self):
        failure = {
            "operation": "aclnnExample", "signature": "output-canary-changed",
            "observed_oracle": "golden-canary", "trace_ref": "trace/cli-unknown.json",
        }
        with tempfile.TemporaryDirectory(prefix="query_patterns_") as tmp:
            path = os.path.join(tmp, "failure.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(failure, handle)
            completed = subprocess.run(
                [sys.executable, os.path.join(SCRIPT_DIR, "query_patterns.py"),
                 "--root", ROOT, "--failure", path],
                check=True, capture_output=True, text=True, encoding="utf-8")
        candidate = json.loads(completed.stdout)["unknown_pattern_candidate"]
        self.assertEqual("trace/cli-unknown.json", candidate["trace_ref"])
        self.assertEqual("pending_verification", candidate["status"])


if __name__ == "__main__":
    unittest.main()
