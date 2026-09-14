#!/usr/bin/env python3
"""
Unit tests for Autonomous Multi-Agent Protocol synchronizer (sync.py).
Verifies stack auto-detection, multi-provider compilation, placeholder integrity,
and --check consistency.
"""

import json
import hashlib
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

import sync

BASE_DIR = Path(__file__).resolve().parent.parent

class TestSyncCompiler(unittest.TestCase):

    def test_load_config(self):
        config_path = BASE_DIR / sync.CONFIG_NAME
        cfg = sync.load_config(config_path)
        self.assertIn("project", cfg)
        self.assertEqual(cfg["project"]["name"], "autonomous-dev-team")
        self.assertIn("codex", cfg)
        self.assertIn("claude", cfg)
        self.assertIn("gemini", cfg)

    def test_generate_all_outputs_integrity(self):
        outputs = sync.generate_all_outputs(BASE_DIR, "all")
        
        # Verify key provider files exist in output map
        output_names = [p.name for p in outputs.keys()]
        self.assertIn("config.toml", output_names)  # .codex/config.toml
        self.assertIn("CLAUDE.md", output_names)
        self.assertIn("AGENTS.md", output_names)
        self.assertIn("GEMINI.md", output_names)
        
        # Verify all 7 agents generated for codex
        agent_names = ["code-explorer.toml", "planner.toml", "implementer.toml", 
                       "quick-implementer.toml", "code-validator.toml", 
                       "code-reviewer.toml", "commit-pusher.toml"]
        for aname in agent_names:
            self.assertIn(aname, output_names, f"Missing Codex agent: {aname}")
            
        # Verify no unreplaced placeholders remain in any output
        placeholder_pattern = re.compile(r'\{[A-Z0-9_]+\}')
        for fpath, content in outputs.items():
            matches = placeholder_pattern.findall(content)
            self.assertEqual(matches, [], f"Unreplaced placeholders in {fpath.name}: {matches}")

    def test_provider_filter(self):
        codex_only = sync.generate_all_outputs(BASE_DIR, "codex")
        for fpath in codex_only.keys():
            self.assertTrue(".codex" in str(fpath))

        claude_only = sync.generate_all_outputs(BASE_DIR, "claude")
        self.assertEqual(list(claude_only.keys())[0].name, "CLAUDE.md")

        gemini_only = sync.generate_all_outputs(BASE_DIR, "gemini")
        gemini_names = {p.name for p in gemini_only.keys()}
        self.assertEqual(gemini_names, {"GEMINI.md", "settings.json"})

        antigravity_only = sync.generate_all_outputs(BASE_DIR, "agy")
        self.assertEqual({p.name for p in antigravity_only}, {"AGENTS.md"})

    def test_check_passes_on_current_repo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            shutil.copytree(BASE_DIR / "agents", tmppath / "agents")
            shutil.copy(BASE_DIR / sync.CONFIG_NAME, tmppath / sync.CONFIG_NAME)
            sync.run_sync(tmppath)
            self.assertEqual(sync.run_check(tmppath), 0)

    def test_detect_project_stack_node(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            pkg_json = {
                "name": "my-express-app",
                "description": "Backend API",
                "scripts": {
                    "build": "tsc",
                    "test": "jest",
                    "test:integration": "jest --config jest.integration.js"
                }
            }
            with open(tmppath / "package.json", "w", encoding="utf-8") as f:
                json.dump(pkg_json, f)

            stack = sync.detect_project_stack(tmppath)
            self.assertEqual(stack["stack"], "Node.js")
            self.assertEqual(stack["name"], tmppath.name)
            self.assertEqual(stack["build_sync_cmd"], "npm run build")
            self.assertEqual(stack["focused_test_cmd"], "npm test -- {file}")
            self.assertEqual(stack["full_test_cmd"], "npm run test:integration")

    def test_detect_project_stack_python(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "pyproject.toml").touch()
            (tmppath / "pytest.ini").touch()

            stack = sync.detect_project_stack(tmppath)
            self.assertEqual(stack["stack"], "Python")
            self.assertIn("pytest", stack["focused_test_cmd"])
            self.assertIn("__pycache__/**", stack["forbidden_paths"])

    def test_detect_project_stack_rust(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "Cargo.toml").touch()

            stack = sync.detect_project_stack(tmppath)
            self.assertEqual(stack["stack"], "Rust")
            self.assertEqual(stack["build_cmd"], "cargo build")
            self.assertIn("target/**", stack["forbidden_paths"])

    def test_detect_project_stack_go(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "go.mod").touch()

            stack = sync.detect_project_stack(tmppath)
            self.assertEqual(stack["stack"], "Go")
            self.assertIn("go test", stack["full_test_cmd"])

    def test_init_in_scratch_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Copy agents folder to target so compilation succeeds
            shutil.copytree(BASE_DIR / "agents", tmppath / "agents")
            
            # Setup a python project
            (tmppath / "requirements.txt").touch()
            
            sync.run_init(tmppath)
            
            self.assertTrue((tmppath / sync.CONFIG_NAME).exists())
            self.assertTrue((tmppath / ".codex" / "config.toml").exists())
            self.assertTrue((tmppath / "CLAUDE.md").exists())
            self.assertTrue((tmppath / "AGENTS.md").exists())
            self.assertTrue((tmppath / "GEMINI.md").exists())
            
            # Check content of generated config
            with open(tmppath / sync.CONFIG_NAME, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn('Python', content)

    def test_local_installer_creates_spaced_target_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "new project"
            unrelated = target / "config.toml"
            command = ["bash", str(BASE_DIR / "install.sh"), "--provider", "codex", str(target)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            first_config = (target / sync.CONFIG_NAME).read_text(encoding="utf-8")
            unrelated.write_text('[tool.example]\nvalue = true\n', encoding="utf-8")
            subprocess.run(command, check=True, capture_output=True, text=True)
            self.assertEqual((target / sync.CONFIG_NAME).read_text(encoding="utf-8"), first_config)
            self.assertEqual(unrelated.read_text(encoding="utf-8"), '[tool.example]\nvalue = true\n')
            self.assertTrue((target / ".codex" / "config.toml").exists())
            self.assertFalse((target / "CLAUDE.md").exists())

    def test_remote_installer_requires_pinned_verified_archive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = Path(tmpdir) / "install.sh"
            shutil.copy(BASE_DIR / "install.sh", runner)
            result = subprocess.run(["bash", str(runner), str(Path(tmpdir) / "target")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("remote installation requires --version", result.stderr)

            result = subprocess.run(
                ["bash", str(runner), "--version", "v1", "--archive-url",
                 "https://example.invalid/v1.tar.gz", "--sha256", "bad", str(Path(tmpdir) / "target")],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("64 hexadecimal", result.stderr)

    def test_remote_installer_rejects_special_archive_members(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            runner = tmppath / "install.sh"
            shutil.copy(BASE_DIR / "install.sh", runner)
            archive = tmppath / "release-v1.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                directory = tarfile.TarInfo("release-v1/")
                directory.type = tarfile.DIRTYPE
                bundle.addfile(directory)
                fifo = tarfile.TarInfo("release-v1/unsafe-fifo")
                fifo.type = tarfile.FIFOTYPE
                bundle.addfile(fifo)
            checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
            bin_dir = tmppath / "bin"
            bin_dir.mkdir()
            fake_curl = bin_dir / "curl"
            fake_curl.write_text(
                "#!/bin/sh\n"
                "while [ \"$#\" -gt 0 ]; do\n"
                "  if [ \"$1\" = --output ]; then cp \"$MALICIOUS_ARCHIVE\" \"$2\"; exit; fi\n"
                "  shift\n"
                "done\nexit 2\n",
                encoding="utf-8")
            fake_curl.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
            environment["MALICIOUS_ARCHIVE"] = str(archive)
            result = subprocess.run(
                ["bash", str(runner), "--version", "v1", "--archive-url",
                 "https://example.invalid/release-v1.tar.gz", "--sha256", checksum,
                 str(tmppath / "target")],
                capture_output=True, text=True, env=environment)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe path or non-file entry", result.stderr)

    def test_installer_avoids_gnu_only_utility_options(self):
        installer = (BASE_DIR / "install.sh").read_text(encoding="utf-8")
        self.assertIn("shasum -a 256", installer)
        self.assertNotIn("--no-same-owner", installer)
        self.assertNotIn("--no-same-permissions", installer)
        self.assertNotRegex(installer, r"\b(?:cp|mv)\s+[^\n]*--")

    def test_native_provider_outputs_and_codex_hierarchy(self):
        outputs = sync.generate_all_outputs(BASE_DIR, "all")
        codex = outputs[BASE_DIR / ".codex" / "config.toml"]
        self.assertIn("[agents.code-explorer]", codex)
        self.assertNotIn("[agents]\n", codex)
        claude_agent = outputs[BASE_DIR / ".claude" / "agents" / "implementer.md"]
        self.assertTrue(claude_agent.startswith("---\nname: implementer\n"))
        settings = json.loads(outputs[BASE_DIR / ".gemini" / "settings.json"])
        self.assertEqual(settings["context"]["fileName"], "GEMINI.md")

    def test_manifest_stale_cleanup_is_guarded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            shutil.copytree(BASE_DIR / "agents", tmppath / "agents")
            shutil.copy(BASE_DIR / sync.CONFIG_NAME, tmppath / sync.CONFIG_NAME)
            stale = tmppath / "stale.md"
            stale.write_text("user content", encoding="utf-8")
            (tmppath / sync.MANIFEST_NAME).write_text(
                json.dumps({"files": ["stale.md"]}), encoding="utf-8")
            sync.run_sync(tmppath, "all")
            self.assertTrue(stale.exists())
            manifest = json.loads((tmppath / sync.MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertNotIn("stale.md", manifest["files"])

    def test_init_migrates_only_identified_legacy_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            shutil.copytree(BASE_DIR / "agents", tmppath / "agents")
            source = (BASE_DIR / sync.CONFIG_NAME).read_text(encoding="utf-8")
            legacy = source.replace(
                f'[schema]\nname = "{sync.SCHEMA_NAME}"\nversion = {sync.SCHEMA_VERSION}\n\n', "")
            (tmppath / "config.toml").write_text(legacy, encoding="utf-8")
            sync.run_init(tmppath)
            self.assertTrue((tmppath / sync.CONFIG_NAME).exists())
            self.assertTrue((tmppath / "config.toml").exists())
            migrated = sync.load_config(tmppath / sync.CONFIG_NAME)
            self.assertEqual(migrated["schema"]["name"], sync.SCHEMA_NAME)
            self.assertEqual(migrated["schema"]["version"], sync.SCHEMA_VERSION)

    def test_unrelated_legacy_config_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "config.toml").write_text(
                '[project]\nname = "other"\n[claude]\nenabled = true\n', encoding="utf-8")
            self.assertFalse(sync.is_legacy_config(sync.load_config(tmppath / "config.toml")))

    def test_scoped_sync_preserves_other_provider_ownership(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            shutil.copytree(BASE_DIR / "agents", tmppath / "agents")
            shutil.copy(BASE_DIR / sync.CONFIG_NAME, tmppath / sync.CONFIG_NAME)
            sync.run_sync(tmppath, "all")
            all_owned = set(json.loads((tmppath / sync.MANIFEST_NAME).read_text())["files"])
            sync.run_sync(tmppath, "codex")
            scoped_owned = set(json.loads((tmppath / sync.MANIFEST_NAME).read_text())["files"])
            self.assertEqual(scoped_owned, all_owned)
            self.assertTrue((tmppath / "CLAUDE.md").exists())
            self.assertEqual(sync.run_check(tmppath, "codex"), 0)
            sync.run_sync(tmppath, "all")
            self.assertEqual(set(json.loads((tmppath / sync.MANIFEST_NAME).read_text())["files"]), all_owned)

    def test_stale_symlink_is_never_followed_or_deleted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            shutil.copytree(BASE_DIR / "agents", tmppath / "agents")
            shutil.copy(BASE_DIR / sync.CONFIG_NAME, tmppath / sync.CONFIG_NAME)
            target = tmppath / "target.md"
            target.write_text("AUTO-GENERATED BY sync.py\nkeep", encoding="utf-8")
            link = tmppath / "stale.md"
            link.symlink_to(target)
            (tmppath / sync.MANIFEST_NAME).write_text(
                json.dumps({"files": ["stale.md"]}), encoding="utf-8")
            sync.run_sync(tmppath, "all")
            self.assertTrue(link.is_symlink())
            self.assertEqual(target.read_text(encoding="utf-8"), "AUTO-GENERATED BY sync.py\nkeep")


if __name__ == "__main__":
    unittest.main()
