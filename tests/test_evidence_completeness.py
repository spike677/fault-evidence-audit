import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from faultaudit.contracts import EvidencePackage
from faultaudit.store import AuditError, Store, canonical_url, digest


class EvidenceCompletenessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "state")
        self.run_id = self.store.create_run()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def package(self, **overrides):
        return {"url": "https://example.invalid/wiki/one", "text": "Synthetic technical source.",
                "status": "COMPLETE", "components": {"body": "COMPLETE"}, **overrides}

    def ingest(self, **overrides):
        return self.store.ingest_evidence(self.run_id, self.package(**overrides))

    def test_generic_legacy_snapshot_identity_is_preserved(self):
        package = EvidencePackage.model_validate(self.package()).model_dump()
        content = {key: package[key] for key in
                   ("title", "text", "status", "components", "derived_from", "is_synthetic")}
        content.update(requested_url=package["url"], final_url=package["url"])
        expected = "snapshot-" + digest([canonical_url(package["url"]), None, content])[:24]
        snapshot = self.ingest()
        self.assertEqual(snapshot["snapshot_id"], expected)
        self.assertEqual(snapshot["snapshot_id"], self.ingest()["snapshot_id"])

    def test_complete_rejects_declared_incomplete_components_without_writing(self):
        for status in ("PARTIAL", "UNKNOWN", "NOT_FETCHED", "AUTH_REQUIRED", "NETWORK_BLOCKED"):
            with self.subTest(status=status), self.assertRaises(AuditError):
                self.ingest(components={"body": "COMPLETE", "comments": status})
        self.assertEqual(self.store.records(self.run_id, "snapshots"), [])

    def test_required_component_must_be_accounted_for(self):
        with self.assertRaises(AuditError):
            self.ingest(required_components=["attachment_index"])
        snapshot = self.ingest(required_components=["attachment_index"],
                               components={"body": "COMPLETE", "attachment_index": "NOT_APPLICABLE"})
        self.assertEqual(snapshot["required_components"], ["attachment_index"])
        with self.assertRaises(AuditError):
            self.ingest(components={"body": "NOT_APPLICABLE"})

    def test_complete_pr_description_without_diff_is_rejected(self):
        for overrides in ({"artifact_type": "PR"},
                          {"url": "https://example.invalid/project/pulls/2094"},
                          {"final_url": "https://example.invalid/project/pull/2094/files"}):
            with self.subTest(overrides=overrides), self.assertRaises(AuditError):
                self.ingest(**overrides)

    def test_complete_pr_requires_matching_file_counts_and_complete_diff(self):
        package = {"artifact_type": "PR", "expected_file_count": 2, "captured_file_count": 1,
                   "components": {"body": "COMPLETE", "file_list": "COMPLETE", "diff": "COMPLETE"}}
        with self.assertRaises(AuditError):
            self.ingest(**package)
        with self.assertRaises(AuditError):
            self.ingest(artifact_type="PR", components=package["components"])
        snapshot = self.ingest(**{**package, "captured_file_count": 2})
        self.assertEqual(snapshot["expected_file_count"], snapshot["captured_file_count"])
        with self.assertRaises(AuditError):
            self.ingest(**{**package, "captured_file_count": 2,
                           "components": {"body": "COMPLETE", "file_list": "COMPLETE", "diff": "PARTIAL"}})
        empty = self.ingest(**{**package, "expected_file_count": 0, "captured_file_count": 0})
        self.assertEqual(empty["captured_file_count"], 0)

    def test_partial_pr_preserves_counts_and_actual_gaps(self):
        snapshot = self.ingest(artifact_type="PR", status="PARTIAL", expected_file_count=3,
                               captured_file_count=1, components={"body": "COMPLETE", "diff": "PARTIAL"})
        self.assertEqual(snapshot["status"], "PARTIAL")
        self.assertEqual(snapshot["captured_file_count"], 1)
        self.assertEqual(snapshot["components"]["diff"], "PARTIAL")

    def test_new_retrieval_states_are_preserved_without_claiming_complete(self):
        for status in ("NOT_FETCHED", "NETWORK_BLOCKED", "CONTENT_CAPTURED"):
            with self.subTest(status=status):
                snapshot = self.ingest(status=status, components={"body": "UNKNOWN"})
                self.assertEqual(snapshot["status"], status)

    def test_pr_counts_are_nonnegative_actual_integers(self):
        for value in (-1, True, 1.5, "1"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                EvidencePackage(url="https://example.invalid/pr/2094", captured_file_count=value)

    def test_authentication_redirect_is_rejected_even_for_long_page(self):
        with self.assertRaises(AuditError):
            self.ingest(final_url="https://login.example.invalid/sso/authorize", text="SSO screen. " * 1000)
        with self.assertRaises(AuditError):
            self.ingest(final_url="https://example.invalid/login", text="Login screen. " * 1000)
        retained = self.ingest(status="AUTH_REQUIRED", final_url="https://login.example.invalid/sso/authorize")
        self.assertEqual(retained["status"], "AUTH_REQUIRED")

    def test_login_form_is_rejected_but_technical_mentions_are_not(self):
        with self.assertRaises(AuditError):
            self.ingest(text='<html><body>Please sign in<form><input type="password"></form></body></html>')
        with self.assertRaises(AuditError):
            self.ingest(text="Please sign in to continue")
        technical = 'Troubleshooting: if a page says "please sign in", authenticate first. '
        snapshot = self.ingest(text=technical + '<form><input type="password"></form> is a login form example.')
        self.assertEqual(snapshot["status"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
