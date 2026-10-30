import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("install_opencode", ROOT / "scripts" / "install_opencode.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class PackagingTests(unittest.TestCase):
    def test_project_install_is_idempotent_and_never_overwrites_conflicts(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            project = Path(directory)
            first = installer.install(project)
            self.assertTrue(first)
            self.assertEqual(first, installer.install(project))
            target = project / ".opencode" / "commands" / "evidence-audit.md"
            target.write_text("user-owned instructions", encoding="utf-8")
            with self.assertRaises(ValueError):
                installer.install(project)
            self.assertEqual(target.read_text(encoding="utf-8"), "user-owned instructions")

    def test_skill_launcher_finds_source_core_without_installing_globally(self):
        runner = ROOT / "integration" / ".opencode" / "skills" / "fault-evidence-audit" / "scripts" / "run_audit.py"
        process = subprocess.run([sys.executable, str(runner), "doctor"], capture_output=True,
                                 encoding="utf-8", cwd=ROOT)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(json.loads(process.stdout)["version"], "0.1.1")


if __name__ == "__main__":
    unittest.main()
