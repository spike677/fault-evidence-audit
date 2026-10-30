import unittest

from pydantic import ValidationError

from faultaudit.contracts import EvidencePackage, EvidenceRef, EvidenceSummary, Judgment, SourceCase


class ContractTests(unittest.TestCase):
    def test_legacy_root_cause_is_unknown_by_default(self):
        case = SourceCase(case_id="c", source_file="source.csv", source_sha256="h", sheet="s", row=2)
        self.assertEqual(case.root_cause_origin, "LEGACY_DERIVED_UNKNOWN")
        self.assertEqual(case.model_dump()["raw"], {})

    def test_independent_mutable_defaults(self):
        first, second = EvidencePackage(url="https://example.invalid/1"), EvidencePackage(url="https://example.invalid/2")
        first.case_ids.append("c")
        self.assertEqual(second.case_ids, [])

    def test_invalid_fetch_status_rejected(self):
        with self.assertRaises(ValidationError):
            EvidencePackage(url="https://example.invalid/1", status="SUCCESS")

    def test_nonempty_fact_needs_citation(self):
        payload = dict(snapshot_id="s", model_mode="mock", model_id="mock-v1")
        with self.assertRaises(ValidationError):
            EvidenceSummary(**payload, issues=[{"label": "x", "facts": [{"field": "operator", "value": "all_reduce"}]}])
        summary = EvidenceSummary(**payload, issues=[{"label": "x", "facts": [{
            "field": "operator", "value": "all_reduce", "evidence": [{"segment_id": "s:1", "quote": "all_reduce"}]
        }]}])
        self.assertEqual(summary.issues[0]["facts"][0]["value"], "all_reduce")

    def test_blank_reference_rejected(self):
        with self.assertRaises(ValidationError):
            EvidenceRef(segment_id=" ", quote="q")

    def test_positive_judgments_require_evidence_and_anchor(self):
        payload = dict(case_id="c", snapshot_id="s", case_attribution="UNKNOWN", event_relation="UNDETERMINED",
                       pattern_relation="POSSIBLY_RELATED", support_level="PENDING", short_reason="unknown",
                       model_mode="mock", model_id="mock-v1")
        self.assertEqual(Judgment(**payload).evidence, [])
        with self.assertRaises(ValidationError):
            Judgment(**{**payload, "support_level": "DIRECT"})
        with self.assertRaises(ValidationError):
            Judgment(**{**payload, "event_relation": "SAME_EVENT"})
        accepted = Judgment(**{**payload, "support_level": "DIRECT", "case_attribution": "CONFIRMED",
                              "event_relation": "SAME_EVENT", "event_anchor": "explicit customer ticket",
                              "evidence": [{"segment_id": "s:1", "quote": "customer ticket"}]})
        self.assertEqual(accepted.model_dump()["event_relation"], "SAME_EVENT")

    def test_claim_support_keys_are_limited(self):
        payload = dict(case_id="c", snapshot_id="s", case_attribution="UNKNOWN", event_relation="UNDETERMINED",
                       pattern_relation="UNDETERMINED", support_level="PENDING", short_reason="unknown",
                       model_mode="mock", model_id="mock-v1")
        with self.assertRaises(ValidationError):
            Judgment(**payload, claim_support={"made_up": "SUPPORTED"})
        self.assertEqual(Judgment(**payload, claim_support={"root_cause": "UNKNOWN"}).claim_support["root_cause"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
