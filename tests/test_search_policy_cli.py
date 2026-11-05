"""Search policy CLI acceptance with synthetic records and no live services."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SearchPolicyCLITests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "tests" / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="search-policy-cli-", dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.state = self.directory / "state"
        source = self.directory / "cases.json"
        source.write_text(json.dumps([{"统一ID": "SYN-POLICY-01", "问题描述": "synthetic restore failure",
                                      "DTS": "https://dts.example.invalid/ticket/one"},
                                     {"统一ID": "SYN-POLICY-02", "问题描述": "synthetic numeric failure"}]), encoding="utf-8")
        self.run_id = self.cli("import", "--input", source, "--source-kind", "ORIGINAL_WEEKLY")["run_id"]
        self.case_id = next(row["case_id"] for row in self.plan()["cases"] if row["external_id"] == "SYN-POLICY-01")

    def cli(self, *args, expected=0):
        process = subprocess.run([sys.executable, str(ROOT / "run_faultaudit.py"), "--state", str(self.state),
                                  *map(str, args)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                                 env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=30)
        self.assertEqual(process.returncode, expected, process.stdout + process.stderr)
        self.assertFalse(process.stderr, process.stderr)
        return json.loads(process.stdout)

    def plan(self):
        return self.cli("evidence-plan", "--run", self.run_id)

    def control(self):
        return next(row["search_control"] for row in self.plan()["cases"] if row["case_id"] == self.case_id)

    def test_run_policy_case_override_and_reset_to_one_evidence(self):
        self.cli("set-search-policy", "--run", self.run_id, "--require-source", "GITCODE")
        self.assertEqual(self.control()["policy"]["required_sources"], ["GITCODE"])
        self.cli("set-search-policy", "--run", self.run_id, "--case-id", self.case_id,
                 "--require-any-source", "GITCODE", "GITHUB")
        self.assertEqual(set(self.control()["policy"]["required_any_sources"]), {"GITCODE", "GITHUB"})
        self.assertEqual(self.control()["policy"]["required_sources"], [], "Case policy replaces the run default")
        self.cli("set-search-policy", "--run", self.run_id, "--case-id", self.case_id)
        self.assertEqual(self.control()["policy"], {"min_usable_evidence": 1, "required_sources": [], "required_any_sources": []})

    def test_programmatic_json_policy_and_explicit_and_or_semantics(self):
        path = self.directory / "policy.json"
        value = {"min_usable_evidence": 2, "required_sources": ["DTS"], "required_any_sources": ["GITCODE", "GITHUB"]}
        path.write_text(json.dumps(value), encoding="utf-8")
        self.cli("set-search-policy", "--run", self.run_id, "--file", path)
        self.assertEqual(self.control()["policy"], value)
        self.cli("set-search-policy", "--run", self.run_id, "--require-source", "GITCODE", "--require-source", "DTS")
        self.assertEqual(set(self.control()["policy"]["required_sources"]), {"DTS", "GITCODE"})

    def test_invalid_or_ambiguous_policy_does_not_replace_current_policy(self):
        before = self.control()["policy_hash"]
        path = self.directory / "invalid.json"
        for value in ({"min_usable_evidence": 0}, {"min_usable_evidence": True}, {"required_sources": ["UNKNOWN"]},
                      {"invented_field": "ignored"}):
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.subTest(value=value):
                self.cli("set-search-policy", "--run", self.run_id, "--file", path, expected=1)
                self.assertEqual(self.control()["policy_hash"], before)
        path.write_text("{}", encoding="utf-8")
        self.cli("set-search-policy", "--run", self.run_id, "--file", path, "--min-evidence", 1, expected=1)
        self.assertEqual(self.control()["policy_hash"], before)

    def test_existing_unread_dts_is_fetched_without_default_new_search(self):
        row = next(row for row in self.plan()["cases"] if row["case_id"] == self.case_id)
        self.assertFalse(row["search_control"]["search_allowed"])
        self.assertIn("FETCH", [action["action"] for action in row["required_actions"]])
        self.assertFalse(any(action["action"] in {"SEARCH", "SEARCH_SUPPORT"} for action in row["required_actions"]))


if __name__ == "__main__":
    unittest.main()
