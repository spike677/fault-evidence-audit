import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from faultaudit import __version__

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("install_opencode", ROOT / "scripts" / "install_opencode.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class PackagingTests(unittest.TestCase):
    def install_fixture(self, project):
        """Place a tiny core below its workspace without host dependencies."""
        project.mkdir()
        core = project / "工具 核心"
        (core / "scripts").mkdir(parents=True)
        shutil.copyfile(ROOT / "scripts" / "install_opencode.py", core / "scripts" / "install_opencode.py")
        shutil.copytree(ROOT / "integration", core / "integration")
        (core / "run_faultaudit.py").write_text(
            "import json, os, sys\nfrom pathlib import Path\n"
            "print(json.dumps({'core': str(Path(__file__).resolve().parent), "
            "'cwd': os.getcwd(), 'args': sys.argv[1:]}))\n", encoding="utf-8")
        with patch.object(installer, "__file__", str(core / "scripts" / "install_opencode.py")):
            installer.install(project)
        skill = project / ".opencode" / "skills" / "fault-evidence-audit"
        return core, skill / "scripts" / "run_audit.py", skill / "core-location.json"

    def run_launcher(self, runner, *args, cwd=None, home=None):
        environment = os.environ.copy()
        environment.pop("FAULTAUDIT_HOME", None)
        environment["PYTHONIOENCODING"] = "utf-8"
        if home is not None:
            environment["FAULTAUDIT_HOME"] = str(home)
        return subprocess.run([sys.executable, str(runner), *args], capture_output=True,
                              encoding="utf-8", cwd=cwd or ROOT, env=environment, timeout=30)

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
        process = self.run_launcher(runner, "doctor")
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(json.loads(process.stdout)["version"], __version__)

    def test_parent_workspace_finds_core_and_preserves_cwd_and_arguments(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            project = Path(directory) / "父 工作区"
            core, runner, location = self.install_fixture(project)
            config = json.loads(location.read_text(encoding="utf-8"))
            self.assertFalse(Path(config["core_path"]).is_absolute())
            self.assertEqual((location.parent / config["core_path"]).resolve(), core.resolve())
            process = self.run_launcher(runner, "--state", "本地 状态", "doctor", cwd=project)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            result = json.loads(process.stdout)
            self.assertEqual(result["core"], str(core.resolve()))
            self.assertEqual(result["cwd"], str(project.resolve()))
            self.assertEqual(result["args"], ["--state", "本地 状态", "doctor"])

    def test_relative_core_configuration_survives_workspace_move(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            base = Path(directory).resolve()
            project = base / "原 工作区"
            core, runner, _ = self.install_fixture(project)
            runner_relative = runner.relative_to(project)
            core_relative = core.relative_to(project)
            moved = base / "迁移 后的工作区"
            self.assertTrue(project.resolve().is_relative_to(base))
            self.assertTrue(moved.resolve().is_relative_to(base))
            project.rename(moved)
            process = self.run_launcher(moved / runner_relative, "doctor", cwd=moved)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertEqual(json.loads(process.stdout)["core"], str((moved / core_relative).resolve()))

    def test_invalid_explicit_home_never_falls_back_to_installed_core(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            project = Path(directory) / "workspace"
            _, runner, _ = self.install_fixture(project)
            for home in (project / "missing-core", ""):
                with self.subTest(home=home):
                    process = self.run_launcher(runner, "doctor", home=home)
                    self.assertEqual(process.returncode, 1)
                    self.assertFalse(process.stdout)
                    self.assertIn("FAULTAUDIT_HOME", process.stderr)

    def test_explicit_home_overrides_installed_location(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            project = Path(directory) / "workspace"
            _, runner, _ = self.install_fixture(project)
            override = Path(directory) / "explicit-core"
            override.mkdir()
            (override / "run_faultaudit.py").write_text("print('explicit-core')\n", encoding="utf-8")
            process = self.run_launcher(runner, "doctor", home=override)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertEqual(process.stdout.strip(), "explicit-core")

    def test_invalid_installed_location_never_falls_back_to_ancestor_core(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            project = Path(directory) / "workspace"
            _, runner, location = self.install_fixture(project)
            (project / "run_faultaudit.py").write_text("print('wrong ancestor core')\n", encoding="utf-8")
            for value in ("not json", '{"schema_version":"1.0","core_path":"missing"}', '[]'):
                with self.subTest(value=value):
                    location.write_text(value, encoding="utf-8")
                    process = self.run_launcher(runner, "doctor", cwd=project)
                    self.assertEqual(process.returncode, 1)
                    self.assertFalse(process.stdout)
                    self.assertIn("Installed core configuration is invalid", process.stderr)

    def test_configuration_conflict_is_detected_before_any_template_is_written(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            project = Path(directory)
            location = project / ".opencode" / "skills" / "fault-evidence-audit" / "core-location.json"
            location.parent.mkdir(parents=True)
            location.write_text('{"user_owned":true}\n', encoding="utf-8")
            before = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
            with self.assertRaises(ValueError):
                installer.install(project)
            after = {p.relative_to(project): p.read_bytes() for p in project.rglob("*") if p.is_file()}
            self.assertEqual(after, before)

    def test_blocked_parent_directory_is_detected_before_any_writes(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            project = Path(directory)
            (project / ".opencode").mkdir()
            blocked = project / ".opencode" / "skills"
            blocked.write_text("user-owned file", encoding="utf-8")
            with self.assertRaises(ValueError):
                installer.install(project)
            self.assertEqual(blocked.read_text(encoding="utf-8"), "user-owned file")
            self.assertFalse((project / ".opencode" / "commands").exists())


if __name__ == "__main__":
    unittest.main()
