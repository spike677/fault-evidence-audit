"""Release invariants independent of historical labels and runtime evidence."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class OriginalDeliveryTests(unittest.TestCase):
    def test_original_documents_remain_exact_and_complete(self):
        manifest = json.loads((ROOT / "knowledge/originals.json").read_text("utf8"))
        for entry in manifest["files"]:
            with self.subTest(path=entry["path"]):
                data = (ROOT / entry["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry["sha256"])

    def test_only_project_links_are_published_in_research(self):
        files = {p.relative_to(ROOT / "research").as_posix()
                 for p in (ROOT / "research").rglob("*") if p.is_file()}
        self.assertEqual(files, {"README.md"})

    def test_public_examples_are_only_synthetic_inputs(self):
        files = list((ROOT / "examples").glob("*.json"))
        self.assertTrue(files)
        self.assertTrue(all(p.name.startswith("synthetic_") for p in files))

    def test_required_inputs_are_in_delivery_without_archived_results(self):
        import importlib.util
        import tempfile
        import zipfile
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location("delivery", ROOT / "scripts/build_delivery.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            # Build at the actual source root, then inspect the declared archive.
            archive = module.build()
            with zipfile.ZipFile(archive) as package:
                names = {name.removeprefix("fault_evidence_audit/") for name in package.namelist()}
            required = {"knowledge/originals.json", "knowledge/trigger_library.md",
                        "knowledge/precision_trigger_knowledge_v4.md", "inputs/manifest.json",
                        "inputs/rc128_original.jsonl", "inputs/cann30_original.txt",
                        "inputs/cases555/cases.jsonl", "inputs/verify.py", "research/README.md"}
            self.assertTrue(required <= names, required - names)
            self.assertFalse(any(name.split('/')[0] in {"archive", "reports", "work", "catalog"}
                                 for name in names))


if __name__ == "__main__":
    unittest.main()
