"""Gitee is a source type, not an operator/mechanism input."""
import unittest
from faultaudit.evidence_plan import normalize_search_policy, resource_kind, semantic_input_hash


class GiteeSourceTests(unittest.TestCase):
    def test_gitee_is_supported_in_source_requirements(self):
        self.assertEqual(resource_kind({"url": "https://gitee.com/example/synthetic/issues/I1"}), "GITEE")
        self.assertEqual(normalize_search_policy({"required_sources": ["GITEE"]})["required_sources"], ["GITEE"])

    def test_gitee_reference_changes_do_not_split_shared_technical_work(self):
        a = {"description": "same synthetic symptom", "raw": {"问题描述": "same synthetic symptom", "gitee": "https://gitee.com/a/b/issues/I1"}}
        b = {**a, "raw": {**a["raw"], "gitee": "https://gitee.com/a/b/pulls/2"}}
        self.assertEqual(semantic_input_hash(a), semantic_input_hash(b))
