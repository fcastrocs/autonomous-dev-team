#!/usr/bin/env python3
"""
Unit tests for Autonomous Multi-Agent Protocol synchronizer (sync.py).
Verifies stack auto-detection, multi-provider compilation, placeholder integrity,
and --check consistency.
"""

import io
import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import sync

BASE_DIR = Path(__file__).resolve().parent.parent

class TestSyncCompiler(unittest.TestCase):

    def copy_canonical_sources(self, target):
        shutil.copytree(BASE_DIR / "agents", target / "agents")
        if (BASE_DIR / "skills").exists():
            shutil.copytree(BASE_DIR / "skills", target / "skills")

    def test_load_config(self):
        config_path = BASE_DIR / sync.CONFIG_NAME
        cfg = sync.load_config(config_path)
        self.assertIn("project", cfg)
        self.assertEqual(cfg["project"]["name"], "autonomous-dev-team")
        self.assertIn("codex", cfg)
        self.assertIn("claude", cfg)
        self.assertIn("antigravity", cfg)

    def test_generate_all_outputs_integrity(self):
        outputs = sync.generate_all_outputs(BASE_DIR, "all")
        
        # Verify key provider files exist in output map
        output_names = [p.name for p in outputs.keys()]
        self.assertIn("config.toml", output_names)  # .codex/config.toml
        self.assertIn("CLAUDE.md", output_names)
        self.assertIn("AGENTS.md", output_names)
        self.assertNotIn("GEMINI.md", output_names)
        self.assertNotIn("orchestrator.toml", output_names)
        
        # Verify all thirteen agents generated for codex
        agent_names = ["code-explorer.toml", "planner.toml", "implementer.toml", 
                       "quick-implementer.toml", "diagnostician.toml", "code-validator.toml", 
                       "code-reviewer.toml", "commit-pusher.toml", "harness-optimizer.toml",
                       "agent-evaluator.toml", "security-reviewer.toml", "pr-test-analyzer.toml",
                       "silent-failure-hunter.toml"]
        for aname in agent_names:
            self.assertIn(aname, output_names, f"Missing Codex agent: {aname}")
            
        self.assertEqual(len([k for k in outputs if ".codex/agents" in str(k)]), 13)
            
        # Verify no unreplaced placeholders remain in any output
        placeholder_pattern = re.compile(r'\{[A-Z0-9_]+\}')
        for fpath, content in outputs.items():
            matches = placeholder_pattern.findall(content)
            self.assertEqual(matches, [], f"Unreplaced placeholders in {fpath.name}: {matches}")

        agy_md = outputs.get(BASE_DIR / "AGENTS.md", "")
        self.assertIn("# Antigravity Delegation Adapter", agy_md)
        self.assertIn("## Antigravity Dispatch Syntax", agy_md)

    def test_provider_filter(self):
        codex_only = sync.generate_all_outputs(BASE_DIR, "codex")
        for fpath in codex_only.keys():
            self.assertTrue(".codex" in str(fpath) or ".agents" in str(fpath))

        claude_only = sync.generate_all_outputs(BASE_DIR, "claude")
        self.assertTrue(any(p.name == "CLAUDE.md" for p in claude_only))
        self.assertTrue(any(p.name == "SKILL.md" for p in claude_only))

        antigravity_only = sync.generate_all_outputs(BASE_DIR, "antigravity")
        self.assertEqual({p.name for p in antigravity_only}, {"AGENTS.md", "SKILL.md"})

        agy_only = sync.generate_all_outputs(BASE_DIR, "agy")
        self.assertEqual({p.name for p in agy_only}, {"AGENTS.md", "SKILL.md"})

    def test_check_passes_on_current_repo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            self.copy_canonical_sources(tmppath)
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

    def test_detect_project_stack_python_unittest_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            (tmppath / "pyproject.toml").touch()
            (tmppath / "tests").mkdir()
            (tmppath / "tests" / "test_something.py").touch()

            stack = sync.detect_project_stack(tmppath)
            self.assertEqual(stack["stack"], "Python")
            self.assertEqual(stack["focused_test_cmd"], "python3 -m unittest {file}")
            self.assertEqual(stack["full_test_cmd"], "python3 -m unittest discover tests")

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
            self.copy_canonical_sources(tmppath)
            
            # Setup a python project
            (tmppath / "requirements.txt").touch()
            
            sync.run_init(tmppath)
            
            self.assertTrue((tmppath / ".autonomous-dev-team" / "config.toml").exists())
            self.assertTrue((tmppath / ".autonomous-dev-team" / "manifest.json").exists())
            self.assertTrue((tmppath / ".codex" / "config.toml").exists())
            self.assertTrue((tmppath / "CLAUDE.md").exists())
            self.assertTrue((tmppath / "AGENTS.md").exists())
            self.assertTrue((tmppath / ".agents" / "skills" / "team" / "SKILL.md").exists())
            self.assertTrue((tmppath / ".claude" / "skills" / "team" / "SKILL.md").exists())
            self.assertTrue((tmppath / ".codex" / "prompts" / "team.md").exists())
            self.assertFalse((tmppath / "GEMINI.md").exists())
            
            # Check content of generated config
            with open(tmppath / ".autonomous-dev-team" / "config.toml", "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn('Python', content)

    def test_canonical_config_tailoring_is_toml_safe_and_complete(self):
        stack = {
            "name": 'quoted "project"',
            "description": "line one\nline two\\end",
            "forbidden_paths": ['build/"quoted"', "tmp\\cache"],
            "build_sync_cmd": "python3 sync.py",
            "focused_test_cmd": "test {file}",
            "full_test_cmd": "test all",
            "build_cmd": "build",
        }
        rendered = sync.generate_project_config_toml(stack, BASE_DIR)
        parsed = sync.tomllib.loads(rendered)
        self.assertEqual(parsed["project"]["name"], stack["name"])
        self.assertEqual(parsed["project"]["description"], stack["description"])
        for provider in ("codex", "claude", "antigravity"):
            self.assertEqual(len(parsed[provider]["agents"]), 13)
            self.assertIn("diagnostician", parsed[provider]["agents"])
            for role in ("harness-optimizer", "agent-evaluator", "security-reviewer",
                         "pr-test-analyzer", "silent-failure-hunter"):
                self.assertIn(role, parsed[provider]["agents"])
        self.assertEqual(parsed["codex"]["orchestrator"]["model"], "gpt-5.6-sol")
        self.assertEqual(parsed["codex"]["orchestrator"]["reasoning_effort"], "low")
        expected_reasoning = {
            "harness-optimizer": "high",
            "agent-evaluator": "medium",
            "security-reviewer": "high",
            "pr-test-analyzer": "medium",
            "silent-failure-hunter": "medium",
        }
        for role, reasoning in expected_reasoning.items():
            expected_codex_model = "gpt-5.6-sol" if role == "harness-optimizer" else "gpt-5.6-terra"
            self.assertEqual(parsed["codex"]["agents"][role]["model"], expected_codex_model)
            expected_codex_reasoning = "high" if role == "security-reviewer" else "medium"
            self.assertEqual(parsed["codex"]["agents"][role]["reasoning_effort"], expected_codex_reasoning)
            self.assertEqual(parsed["claude"]["agents"][role]["model"], "claude-3-7-sonnet")
            self.assertEqual(parsed["claude"]["agents"][role]["thinking"], reasoning)
            self.assertEqual(parsed["antigravity"]["agents"][role]["model"], "flash")
            self.assertEqual(parsed["antigravity"]["agents"][role]["reasoning"], reasoning)

    def test_missing_canonical_config_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(FileNotFoundError, sync.CONFIG_NAME):
                sync.generate_project_config_toml({"name": "project"}, Path(tmpdir))

    def test_no_secondary_config_template_exists_or_is_required(self):
        self.assertFalse((BASE_DIR / "templates").exists())
        installer = (BASE_DIR / "install.py").read_text(encoding="utf-8")
        self.assertNotIn("templates", installer)
        self.assertIn(sync.CONFIG_NAME, installer)

    def test_shared_orchestrator_role_is_canonical_and_present_once(self):
        self.assertEqual(sync.ORCHESTRATOR_PROTOCOL, Path("agents/orchestrator.md"))
        self.assertTrue((BASE_DIR / sync.ORCHESTRATOR_PROTOCOL).is_file())
        self.assertFalse((BASE_DIR / "protocol").exists())
        marker = "Reuse that implementer for at most two repair cycles."
        outputs = sync.generate_all_outputs(BASE_DIR, "all")
        for path in (
            BASE_DIR / ".codex" / "config.toml",
            BASE_DIR / "CLAUDE.md",
            BASE_DIR / "AGENTS.md",
        ):
            self.assertEqual(outputs[path].count(marker), 1, str(path))



    def test_local_installer_requires_force_to_replace_managed_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "new project"
            client_dir = target / ".autonomous-dev-team"
            unrelated = target / "config.toml"
            command = [sys.executable, str(BASE_DIR / "install.py"), "--provider", "codex", str(target)]
            subprocess.run(command, check=True, capture_output=True, text=True)
            first_config = (client_dir / "config.toml").read_text(encoding="utf-8")
            self.assertIn('active_provider = "codex"', first_config)
            unrelated.write_text('[tool.example]\nvalue = true\n', encoding="utf-8")
            installed_sync = client_dir / "sync.py"
            installed_sync.write_text("user-managed content\n", encoding="utf-8")
            refused = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("use --force to replace it", refused.stderr)
            self.assertEqual(installed_sync.read_text(encoding="utf-8"), "user-managed content\n")
            forced_command = command[:-1] + ["--force", command[-1]]
            subprocess.run(forced_command, check=True, capture_output=True, text=True)
            self.assertEqual(installed_sync.read_text(encoding="utf-8"), (BASE_DIR / "sync.py").read_text(encoding="utf-8"))
            installed_sync.unlink()
            shutil.rmtree(client_dir / "_internal" / "agents")
            (client_dir / "_internal" / "agents").mkdir(parents=True, exist_ok=True)
            installed_agent = client_dir / "_internal" / "agents" / "implementer.md"
            installed_agent.write_text("local agent changes\n", encoding="utf-8")
            refused = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn(str(installed_agent), refused.stderr)
            self.assertEqual(installed_agent.read_text(encoding="utf-8"), "local agent changes\n")
            subprocess.run(forced_command, check=True, capture_output=True, text=True)
            self.assertEqual((client_dir / "config.toml").read_text(encoding="utf-8"), first_config)
            self.assertEqual(unrelated.read_text(encoding="utf-8"), '[tool.example]\nvalue = true\n')
            self.assertTrue((client_dir / "_internal" / "agents" / "orchestrator.md").is_file())
            self.assertFalse((client_dir / "agents").exists())
            self.assertFalse((target / "agents").exists())
            self.assertFalse((target / "sync.py").exists())
            self.assertFalse((target / "protocol").exists())
            self.assertTrue((target / ".codex" / "config.toml").exists())
            self.assertFalse((target / "CLAUDE.md").exists())
            self.assertTrue((client_dir / "manifest.json").exists())
            self.assertFalse((target / "__pycache__").exists())
            self.assertFalse((client_dir / "__pycache__").exists())
            self.assertEqual(list(target.glob(".autonomous-dev-team.install.*")), [])
            self.assertEqual(list(client_dir.glob(".install_stage.*")), [])

    def test_remote_installer_requires_pinned_verified_archive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = Path(tmpdir) / "install.py"
            shutil.copy(BASE_DIR / "install.py", runner)
            result = subprocess.run([sys.executable, str(runner), str(Path(tmpdir) / "target")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("remote installation requires --version", result.stderr)

            result = subprocess.run(
                [sys.executable, str(runner), "--version", "v1", "--archive-url",
                 "https://example.invalid/v1.tar.gz", "--sha256", "bad", str(Path(tmpdir) / "target")],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("64 hexadecimal", result.stderr)

    def test_installer_rejects_symlinked_managed_directories_even_with_force(self):
        for managed_dir in ("agents",):
            with self.subTest(managed_dir=managed_dir), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                target = root / "target"
                outside = root / "outside"
                target.mkdir()
                outside.mkdir()
                (target / managed_dir).symlink_to(outside, target_is_directory=True)
                command = [
                    sys.executable, str(BASE_DIR / "install.py"), "--provider", "codex",
                    "--force", str(target),
                ]

                result = subprocess.run(command, capture_output=True, text=True)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("must not be a symlink", result.stderr)
                self.assertEqual(list(outside.iterdir()), [])
                self.assertFalse((target / "sync.py").exists())

    def test_remote_installer_rejects_special_archive_members(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            runner = tmppath / "install.py"
            shutil.copy(BASE_DIR / "install.py", runner)
            archive = tmppath / "release-v1.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                directory = tarfile.TarInfo("release-v1/")
                directory.type = tarfile.DIRTYPE
                bundle.addfile(directory)
                fifo = tarfile.TarInfo("release-v1/unsafe-fifo")
                fifo.type = tarfile.FIFOTYPE
                bundle.addfile(fifo)
            checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
            result = subprocess.run(
                [sys.executable, str(runner), "--version", "v1", "--archive-url",
                 archive.as_uri(), "--sha256", checksum,
                 str(tmppath / "target")],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe path or non-file entry", result.stderr)

    def test_installer_is_cross_platform_pure_python(self):
        installer = (BASE_DIR / "install.py").read_text(encoding="utf-8")
        self.assertIn("sys.version_info < (3, 11)", installer)
        self.assertIn("sys.executable", installer)
        self.assertNotIn("shasum", installer)
        self.assertNotIn("curl", installer)

    def test_remote_installer_rejects_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            runner = tmppath / "install.py"
            shutil.copy(BASE_DIR / "install.py", runner)
            archive = tmppath / "release-v1.tar.gz"
            archive.write_bytes(b"invalid-archive-content")
            result = subprocess.run(
                [sys.executable, str(runner), "--version", "v1", "--archive-url",
                 archive.as_uri(), "--sha256", "0" * 64,
                 str(tmppath / "target")],
                capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("checksum verification failed", result.stderr)

    def test_installer_enforces_python_311_requirement(self):
        installer = (BASE_DIR / "install.py").read_text(encoding="utf-8")
        self.assertIn("sys.version_info < (3, 11)", installer)
        code = "import sys; sys.version_info = (3, 10, 0); " + installer.split("import sys\n", 1)[1]
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Python 3.11 or higher is required", result.stderr)

    def test_remote_installer_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            runner = tmppath / "install.py"
            shutil.copy(BASE_DIR / "install.py", runner)
            archive = tmppath / "release-v1.0.0.tar.gz"
            prefix = "autonomous-dev-team-v1.0.0"
            with tarfile.open(archive, "w:gz") as bundle:
                bundle.add(BASE_DIR / sync.CONFIG_NAME, arcname=f"{prefix}/{sync.CONFIG_NAME}")
                bundle.add(BASE_DIR / "sync.py", arcname=f"{prefix}/sync.py")
                bundle.add(BASE_DIR / "agents", arcname=f"{prefix}/agents")
                if (BASE_DIR / "skills").exists():
                    bundle.add(BASE_DIR / "skills", arcname=f"{prefix}/skills")
            checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
            target = tmppath / "target"
            result = subprocess.run(
                [sys.executable, str(runner), "--version", "v1.0.0", "--archive-url",
                 archive.as_uri(), "--sha256", checksum, "--provider", "all",
                 str(target)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"Installer failed: {result.stderr}")
            self.assertTrue((target / ".autonomous-dev-team" / "config.toml").exists())
            self.assertTrue((target / ".autonomous-dev-team" / "sync.py").exists())
            self.assertTrue((target / ".autonomous-dev-team" / "_internal" / "agents").exists())
            self.assertFalse((target / ".autonomous-dev-team" / "agents").exists())
            self.assertTrue((target / ".autonomous-dev-team" / "manifest.json").exists())
            self.assertFalse((target / "sync.py").exists())
            self.assertFalse((target / "agents").exists())
            self.assertFalse((target / sync.CONFIG_NAME).exists())
            self.assertTrue((target / "AGENTS.md").exists())
            self.assertTrue((target / "CLAUDE.md").exists())
            self.assertFalse((target / "__pycache__").exists())
            self.assertFalse((target / ".autonomous-dev-team" / "__pycache__").exists())
            self.assertEqual(list(target.glob(".autonomous-dev-team.install.*")), [])
            self.assertEqual(list((target / ".autonomous-dev-team").glob(".install_stage.*")), [])

    def test_native_provider_outputs_and_codex_hierarchy(self):
        outputs = sync.generate_all_outputs(BASE_DIR, "all")
        codex = outputs[BASE_DIR / ".codex" / "config.toml"]
        self.assertIn("[agents.code-explorer]", codex)
        self.assertNotIn("[agents]\n", codex)
        self.assertNotIn("[agents.orchestrator]", codex)
        self.assertIn('model = "gpt-5.6-sol"', codex)
        self.assertIn('model_reasoning_effort = "low"', codex)
        self.assertIn("tool_output_token_limit = 6000", codex)
        self.assertIn("model_auto_compact_token_limit = 45000", codex)
        self.assertIn('model_auto_compact_token_limit_scope = "body_after_prefix"', codex)
        for agent_name in ("planner", "implementer", "diagnostician", "code-reviewer"):
            agent = outputs[BASE_DIR / ".codex" / "agents" / f"{agent_name}.toml"]
            self.assertIn('model_reasoning_effort = "medium"', agent)
        for agent_name in ("code-explorer", "quick-implementer", "code-validator", "commit-pusher"):
            agent = outputs[BASE_DIR / ".codex" / "agents" / f"{agent_name}.toml"]
            self.assertIn('model_reasoning_effort = "low"', agent)
        validator = outputs[BASE_DIR / ".codex" / "agents" / "code-validator.toml"]
        self.assertIn('model = "gpt-5.6-terra"', validator)
        expected_codex = {
            "harness-optimizer": ("gpt-5.6-sol", "medium"),
            "agent-evaluator": ("gpt-5.6-terra", "medium"),
            "security-reviewer": ("gpt-5.6-terra", "high"),
            "pr-test-analyzer": ("gpt-5.6-terra", "medium"),
            "silent-failure-hunter": ("gpt-5.6-terra", "medium"),
        }
        for agent_name, (model, reasoning) in expected_codex.items():
            agent = outputs[BASE_DIR / ".codex" / "agents" / f"{agent_name}.toml"]
            self.assertIn(f'model = "{model}"', agent)
            self.assertIn(f'model_reasoning_effort = "{reasoning}"', agent)
        claude_md = outputs[BASE_DIR / "CLAUDE.md"]
        self.assertIn("Use Claude Code's native agent configuration", claude_md)
        self.assertNotIn("specialist", claude_md.lower())
        claude_agent = outputs[BASE_DIR / ".claude" / "agents" / "implementer.md"]
        self.assertTrue(claude_agent.startswith("---\nname: implementer\n"))
        self.assertIn("implementer agent for autonomous-dev-team", claude_agent)
        expected_claude_reasoning = {
            "harness-optimizer": "high",
            "agent-evaluator": "medium",
            "security-reviewer": "high",
            "pr-test-analyzer": "medium",
            "silent-failure-hunter": "medium",
        }
        for agent_name, reasoning in expected_claude_reasoning.items():
            claude_agent = outputs[BASE_DIR / ".claude" / "agents" / f"{agent_name}.md"]
            self.assertIn("model: claude-3-7-sonnet", claude_agent)
            self.assertIn(f"reasoning effort: {reasoning}", claude_agent)
        agy_adapter = outputs[BASE_DIR / "AGENTS.md"]
        self.assertIn("# Antigravity Delegation Adapter", agy_adapter)
        self.assertIn("Role` to the\nagent name", agy_adapter)
        for agent_name in ("harness-optimizer", "agent-evaluator", "security-reviewer",
                           "pr-test-analyzer", "silent-failure-hunter"):
            self.assertIn(f"- `{agent_name}`: model `flash`", agy_adapter)
        self.assertNotIn("specialist", agy_adapter.lower())
        self.assertNotIn("GEMINI.md", [p.name for p in outputs])

    def test_manifest_stale_cleanup_is_guarded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            self.copy_canonical_sources(tmppath)
            shutil.copy(BASE_DIR / sync.CONFIG_NAME, tmppath / sync.CONFIG_NAME)
            stale = tmppath / "stale.md"
            stale.write_text("user content", encoding="utf-8")
            (tmppath / sync.MANIFEST_NAME).write_text(
                json.dumps({"files": ["stale.md"]}), encoding="utf-8")
            sync.run_sync(tmppath, "all")
            self.assertTrue(stale.exists())
            manifest = json.loads((tmppath / sync.MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertNotIn("stale.md", manifest["files"])

    def test_legacy_config_is_not_resolved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            legacy = tmppath / "config.toml"
            legacy.write_text('[project]\nname = "test"\n', encoding="utf-8")
            with self.assertRaises(SystemExit) as cm:
                sync.resolve_config_path(tmppath)
            self.assertIn(sync.CONFIG_NAME, str(cm.exception))

    def test_scoped_sync_preserves_other_provider_ownership(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            self.copy_canonical_sources(tmppath)
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
            self.copy_canonical_sources(tmppath)
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

    def test_inspect_team_in_sync(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = sync.inspect_team(BASE_DIR, "antigravity")
        self.assertEqual(ret, 0)
        output = buf.getvalue()
        self.assertIn("Google Antigravity", output)
        self.assertIn("✓ In sync", output)
        self.assertIn("orchestrator (/root)", output)
        self.assertIn("code-explorer", output)
        self.assertIn("flash", output)

    def test_inspect_team_all_providers(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = sync.inspect_team(BASE_DIR, "all")
        self.assertEqual(ret, 0)
        output = buf.getvalue()
        self.assertIn("Google Antigravity Team Roster", output)
        self.assertIn("Claude Code Team Roster", output)
        self.assertIn("Codex Team Roster", output)

    def test_inspect_team_out_of_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            self.copy_canonical_sources(tmppath)
            shutil.copy(BASE_DIR / sync.CONFIG_NAME, tmppath / sync.CONFIG_NAME)
            buf = io.StringIO()
            with redirect_stdout(buf):
                ret = sync.inspect_team(tmppath, "antigravity")
            self.assertEqual(ret, 1)
            self.assertIn("⚠ Out of sync", buf.getvalue())

    def test_team_skill_generation(self):
        outputs = sync.generate_all_outputs(BASE_DIR, "all")
        
        agy_skill = BASE_DIR / ".agents" / "skills" / "team" / "SKILL.md"
        claude_skill = BASE_DIR / ".claude" / "skills" / "team" / "SKILL.md"
        codex_skill = BASE_DIR / ".codex" / "prompts" / "team.md"
        
        self.assertIn(agy_skill, outputs)
        self.assertIn(claude_skill, outputs)
        self.assertIn(codex_skill, outputs)
        
        for spath in (agy_skill, claude_skill, codex_skill):
            content = outputs[spath]
            self.assertTrue(content.startswith("---\nname: team\n"))
            self.assertIn("Execute the build sync inspection command:", content)
            self.assertIn("--team`", content)
            self.assertIn("Presentation Instructions", content)
            self.assertIn("Configuration File", content)
            self.assertIn("Active Provider", content)
            self.assertIn("Setup Sync Status", content)
            self.assertIn("`Role`", content)
            self.assertIn("`Agent`", content)
            self.assertIn("`Model`", content)
            self.assertIn("`Reasoning Effort`", content)
            self.assertIn("Orchestrator", content)
            self.assertIn('Never use "Specialist"', content)
            self.assertIn("Do NOT summarize, abbreviate, or omit roles from the roster", content)

    def test_detect_runtime_provider(self):
        for var in ("ANTIGRAVITY_AGENT", "ANTIGRAVITY_CONVERSATION_ID", "ANTIGRAVITY_LS_ADDRESS"):
            with mock.patch.dict(os.environ, {var: "1"}, clear=True):
                self.assertEqual(sync.detect_runtime_provider(), "antigravity")

        for var in ("CLAUDE_CODE", "CLAUDECODE", "CLAUDE_SESSION_ID", "CLAUDE_PROJECT_DIR", "CLAUDE_CONVERSATION_ID"):
            with mock.patch.dict(os.environ, {var: "1"}, clear=True):
                self.assertEqual(sync.detect_runtime_provider(), "claude")

        for var in ("CODEX_CLI", "CODEX_THREAD_ID", "CODEX_SANDBOX"):
            with mock.patch.dict(os.environ, {var: "1"}, clear=True):
                self.assertEqual(sync.detect_runtime_provider(), "codex")

        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(sync.detect_runtime_provider())

    def test_inspect_team_runtime_detection(self):
        with mock.patch.dict(os.environ, {"ANTIGRAVITY_AGENT": "1"}, clear=True):
            buf = io.StringIO()
            with redirect_stdout(buf):
                ret = sync.inspect_team(BASE_DIR)
            self.assertEqual(ret, 0)
            output = buf.getvalue()
            self.assertIn("Active Provider    : Google Antigravity (setting: antigravity)", output)
            self.assertIn("Google Antigravity Team Roster", output)
            self.assertNotIn("Claude Code Team Roster", output)
            self.assertNotIn("Codex Team Roster", output)

        with mock.patch.dict(os.environ, {"CLAUDE_CODE": "1"}, clear=True):
            buf = io.StringIO()
            with redirect_stdout(buf):
                ret = sync.inspect_team(BASE_DIR)
            self.assertEqual(ret, 0)
            output = buf.getvalue()
            self.assertIn("Active Provider    : Claude Code (setting: claude)", output)
            self.assertIn("Claude Code Team Roster", output)
            self.assertNotIn("Google Antigravity Team Roster", output)
            self.assertNotIn("Codex Team Roster", output)

        with mock.patch.dict(os.environ, {"ANTIGRAVITY_AGENT": "1"}, clear=True):
            buf = io.StringIO()
            with redirect_stdout(buf):
                ret = sync.inspect_team(BASE_DIR, "all")
            self.assertEqual(ret, 0)
            output = buf.getvalue()
            self.assertIn("Google Antigravity Team Roster", output)
            self.assertIn("Claude Code Team Roster", output)
            self.assertIn("Codex Team Roster", output)

    def test_inspect_team_column_alignment(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            sync.inspect_team(BASE_DIR, "antigravity")
        lines = [l for l in buf.getvalue().splitlines() if l.startswith("  • ")]
        self.assertTrue(len(lines) >= 2)
        colon_indices = {l.index(":") for l in lines}
        self.assertEqual(len(colon_indices), 1, f"Colons not aligned: {colon_indices}")
        reasoning_indices = {l.index("(reasoning:") for l in lines}
        self.assertEqual(len(reasoning_indices), 1, f"Reasoning not aligned: {reasoning_indices}")

    def test_makefile_targets_consistency(self):
        makefile_path = BASE_DIR / "Makefile"
        self.assertTrue(makefile_path.exists())
        content = makefile_path.read_text(encoding="utf-8")
        
        # Extract .PHONY targets
        phony_match = re.search(r'^\.PHONY:\s*(.+)$', content, re.MULTILINE)
        self.assertIsNotNone(phony_match)
        phony_targets = phony_match.group(1).split()
        
        # Ensure each phony target has a defined rule
        for target in phony_targets:
            res = subprocess.run(
                ["make", "-n", target],
                cwd=str(BASE_DIR),
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"make -n {target} failed: {res.stderr}")
            self.assertNotIn("Nothing to be done for", res.stdout, f"Target '{target}' has no recipe in Makefile")

    def test_root_level_self_hosted_layout_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            self.copy_canonical_sources(tmppath)
            shutil.copy(BASE_DIR / sync.CONFIG_NAME, tmppath / sync.CONFIG_NAME)
            shutil.copy(BASE_DIR / "sync.py", tmppath / "sync.py")

            self.assertEqual(sync.resolve_config_path(tmppath), tmppath / sync.CONFIG_NAME)
            self.assertEqual(sync.resolve_agents_dir(tmppath), tmppath / "agents")
            self.assertEqual(sync.resolve_skills_dir(tmppath), tmppath / "skills")
            self.assertEqual(sync.resolve_manifest_path(tmppath), tmppath / sync.MANIFEST_NAME)
            self.assertEqual(sync.resolve_base_dir(tmppath), tmppath)

            sync.run_sync(tmppath, "all")

            self.assertTrue((tmppath / sync.MANIFEST_NAME).exists())
            self.assertFalse((tmppath / ".autonomous-dev-team").exists())
            self.assertTrue((tmppath / "CLAUDE.md").exists())
            self.assertTrue((tmppath / "AGENTS.md").exists())
            self.assertTrue((tmppath / ".codex" / "config.toml").exists())
            self.assertEqual(sync.run_check(tmppath, "all"), 0)

    def test_client_encapsulated_layout_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            client_dir = tmppath / ".autonomous-dev-team"
            client_dir.mkdir(parents=True)
            self.copy_canonical_sources(client_dir)
            shutil.copy(BASE_DIR / sync.CONFIG_NAME, client_dir / "config.toml")
            shutil.copy(BASE_DIR / "sync.py", client_dir / "sync.py")

            self.assertFalse((tmppath / "agents").exists())
            self.assertFalse((tmppath / "skills").exists())
            self.assertFalse((tmppath / "sync.py").exists())
            self.assertFalse((tmppath / sync.CONFIG_NAME).exists())

            self.assertEqual(sync.resolve_config_path(tmppath), client_dir / "config.toml")
            self.assertEqual(sync.resolve_agents_dir(tmppath), client_dir / "agents")
            self.assertEqual(sync.resolve_skills_dir(tmppath), client_dir / "skills")
            self.assertEqual(sync.resolve_manifest_path(tmppath), client_dir / "manifest.json")
            self.assertEqual(sync.resolve_base_dir(client_dir), tmppath)

            sync.run_sync(tmppath, "all")

            self.assertTrue((client_dir / "manifest.json").exists())
            self.assertFalse((tmppath / sync.MANIFEST_NAME).exists())
            self.assertTrue((tmppath / "CLAUDE.md").exists())
            self.assertTrue((tmppath / "AGENTS.md").exists())
            self.assertTrue((tmppath / ".codex" / "config.toml").exists())
            self.assertEqual(sync.run_check(tmppath, "all"), 0)

            # Test invocation of sync.py from inside .autonomous-dev-team
            res = subprocess.run(
                [sys.executable, str(client_dir / "sync.py"), "--check", "--provider", "all"],
                cwd=str(tmppath),
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"Check failed: {res.stderr}")

    def test_client_encapsulated_internal_layout_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            client_dir = tmppath / ".autonomous-dev-team"
            internal_dir = client_dir / "_internal"
            internal_dir.mkdir(parents=True)
            self.copy_canonical_sources(internal_dir)
            shutil.copy(BASE_DIR / sync.CONFIG_NAME, client_dir / "config.toml")
            shutil.copy(BASE_DIR / "sync.py", client_dir / "sync.py")

            self.assertFalse((tmppath / "agents").exists())
            self.assertFalse((tmppath / "skills").exists())
            self.assertFalse((client_dir / "agents").exists())
            self.assertFalse((client_dir / "skills").exists())

            self.assertEqual(sync.resolve_config_path(tmppath), client_dir / "config.toml")
            self.assertEqual(sync.resolve_agents_dir(tmppath), internal_dir / "agents")
            self.assertEqual(sync.resolve_skills_dir(tmppath), internal_dir / "skills")
            self.assertEqual(sync.resolve_manifest_path(tmppath), client_dir / "manifest.json")
            self.assertEqual(sync.resolve_base_dir(internal_dir), tmppath)

            sync.run_sync(tmppath, "all")

            self.assertTrue((client_dir / "manifest.json").exists())
            self.assertTrue((tmppath / "CLAUDE.md").exists())
            self.assertTrue((tmppath / "AGENTS.md").exists())
            self.assertTrue((tmppath / ".codex" / "config.toml").exists())
            self.assertEqual(sync.run_check(tmppath, "all"), 0)

            res = subprocess.run(
                [sys.executable, str(client_dir / "sync.py"), "--check", "--provider", "all"],
                cwd=str(tmppath),
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"Check failed: {res.stderr}")

    def test_config_resolution_fallbacks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            client_dir = tmppath / ".autonomous-dev-team"
            client_dir.mkdir(parents=True)

            # Fallback 1: .autonomous-dev-team/.autonomous-dev-team.toml
            legacy_namespaced = client_dir / sync.CONFIG_NAME
            legacy_namespaced.write_text('[project]\nname = "test"\n', encoding="utf-8")
            self.assertEqual(sync.resolve_config_path(tmppath), legacy_namespaced)
            legacy_namespaced.unlink()

            # Fallback 2: root .autonomous-dev-team.toml
            root_config = tmppath / sync.CONFIG_NAME
            root_config.write_text('[project]\nname = "test"\n', encoding="utf-8")
            self.assertEqual(sync.resolve_config_path(tmppath), root_config)


if __name__ == "__main__":
    unittest.main()
