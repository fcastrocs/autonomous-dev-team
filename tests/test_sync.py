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
        self.assertEqual(cfg["schema_version"], 2)
        self.assertIn("project", cfg)
        self.assertEqual(cfg["project"]["name"], "autonomous-dev-team")
        self.assertIn("models", cfg)
        self.assertIn("agents", cfg)

    def test_generate_all_outputs_integrity(self):
        outputs = sync.generate_all_outputs(BASE_DIR, "all")
        
        # Verify key provider files exist in output map
        output_names = [p.name for p in outputs.keys()]
        self.assertIn("config.toml", output_names)  # .codex/config.toml
        self.assertNotIn("CLAUDE.md", output_names)
        self.assertIn("AGENTS.md", output_names)
        self.assertNotIn("GEMINI.md", output_names)
        self.assertNotIn("orchestrator.toml", output_names)
        
        # Verify all three agents generated for codex
        agent_names = ["architect.toml", "implementer.toml", "verifier.toml"]
        for aname in agent_names:
            self.assertIn(aname, output_names, f"Missing Codex agent: {aname}")

        self.assertEqual(len([k for k in outputs if ".codex/agents" in str(k)]), 3)
        self.assertEqual(len([k for k in outputs if ".agents/agents" in str(k) and k.name == "agent.md"]), 3)
            
        # Verify no unreplaced placeholders remain in any output
        placeholder_pattern = re.compile(r'\{[A-Z0-9_]+\}')
        for fpath, content in outputs.items():
            matches = placeholder_pattern.findall(content)
            self.assertEqual(matches, [], f"Unreplaced placeholders in {fpath.name}: {matches}")

        agy_md = outputs.get(BASE_DIR / "AGENTS.md", "")
        self.assertIn("# autonomous-dev-team", agy_md)
        self.assertIn("## Repository Guardrails & Commands", agy_md)
        self.assertNotIn("## Antigravity Dispatch Syntax", agy_md)
        self.assertNotIn("## Claude Model Routing", agy_md)
        self.assertLessEqual(len(agy_md), 1600)
        self.assertLessEqual(sync.estimate_tokens(len(agy_md)), 400)

        claude_orch = outputs.get(BASE_DIR / ".claude" / "agents" / "orchestrator.md", "")
        self.assertIn("## Claude Model Routing", claude_orch)

    def test_effective_forbidden_paths_includes_provider_outputs(self):
        project = {"forbidden_paths": [".git/**", "__pycache__/**"]}
        effective = sync.get_effective_forbidden_paths(project)
        self.assertIn(".codex/**", effective)
        self.assertIn(".claude/**", effective)
        self.assertIn(".agents/**", effective)
        self.assertIn(".git/**", effective)
        self.assertIn("__pycache__/**", effective)

        guardrails = sync.build_project_guardrails(project)
        self.assertIn("`.codex/**`", guardrails)
        self.assertIn("`.claude/**`", guardrails)
        self.assertIn("`.agents/**`", guardrails)

    def test_provider_filter(self):
        codex_only = sync.generate_all_outputs(BASE_DIR, "codex")
        for fpath in codex_only.keys():
            self.assertTrue(".codex" in str(fpath) or ".agents" in str(fpath))

        claude_only = sync.generate_all_outputs(BASE_DIR, "claude")
        self.assertTrue(any(p.name == "AGENTS.md" for p in claude_only))
        self.assertFalse(any(p.name == "CLAUDE.md" for p in claude_only))
        self.assertTrue(any(p.name == "SKILL.md" for p in claude_only))

        antigravity_only = sync.generate_all_outputs(BASE_DIR, "antigravity")
        self.assertEqual({p.name for p in antigravity_only}, {"AGENTS.md", "SKILL.md", "agent.md", "hooks.json"})

        agy_only = sync.generate_all_outputs(BASE_DIR, "agy")
        self.assertEqual({p.name for p in agy_only}, {"AGENTS.md", "SKILL.md", "agent.md", "hooks.json"})

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
            self.assertFalse((tmppath / "CLAUDE.md").exists())
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
        self.assertEqual(parsed["schema_version"], 2)
        self.assertEqual(parsed["project"]["name"], stack["name"])
        self.assertEqual(parsed["project"]["description"], stack["description"])
        self.assertEqual(len(parsed["agents"]), 3)
        self.assertIn("architect", parsed["agents"])
        self.assertEqual(parsed["agents"]["architect"]["tier"], "balanced")
        self.assertEqual(parsed["agents"]["architect"]["reasoning_effort"], "medium")
        self.assertIn("implementer", parsed["agents"])
        self.assertEqual(parsed["agents"]["implementer"]["tier"], "balanced")
        self.assertEqual(parsed["agents"]["implementer"]["reasoning_effort"], "medium")
        self.assertIn("verifier", parsed["agents"])
        self.assertEqual(parsed["agents"]["verifier"]["tier"], "balanced")
        self.assertEqual(parsed["agents"]["verifier"]["reasoning_effort"], "medium")
        self.assertEqual(parsed["orchestrator"]["tier"], "balanced")
        self.assertEqual(parsed["orchestrator"]["reasoning_effort"], "low")

        codex_agents = sync.provider_agents(parsed, "codex")
        claude_agents = sync.provider_agents(parsed, "claude")
        antigravity_agents = sync.provider_agents(parsed, "antigravity")

        self.assertEqual(len(codex_agents), 3)
        self.assertEqual(len(claude_agents), 3)
        self.assertEqual(len(antigravity_agents), 3)

        balanced = parsed["models"]["balanced"]
        for role in ("architect", "implementer", "verifier"):
            self.assertEqual(codex_agents[role]["model"], balanced["codex"])
            self.assertEqual(codex_agents[role]["reasoning_effort"], "medium")
            self.assertEqual(claude_agents[role]["model"], balanced["claude"])
            self.assertEqual(claude_agents[role]["thinking"], "medium")
            self.assertEqual(antigravity_agents[role]["model"], balanced["antigravity"])
            self.assertEqual(antigravity_agents[role]["reasoning"], "medium")

        codex_orch = sync.resolve_orchestrator(parsed, "codex")
        self.assertEqual(codex_orch["model"], balanced["codex"])
        self.assertEqual(codex_orch["reasoning_effort"], "low")

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
            BASE_DIR / ".claude" / "agents" / "orchestrator.md",
        ):
            self.assertEqual(outputs[path].count(marker), 1, str(path))
        self.assertEqual(outputs[BASE_DIR / "AGENTS.md"].count(marker), 0)



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

    def test_sync_enforces_python_311_requirement(self):
        sync_code = (BASE_DIR / "sync.py").read_text(encoding="utf-8")
        self.assertIn("sys.version_info < (3, 11)", sync_code)
        code = "import sys, os, shutil; sys.version_info = (3, 10, 0); " + sync_code.split("import sys\n", 1)[1]
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
            self.assertFalse((target / "CLAUDE.md").exists())
            self.assertFalse((target / "__pycache__").exists())
            self.assertFalse((target / ".autonomous-dev-team" / "__pycache__").exists())
            self.assertEqual(list(target.glob(".autonomous-dev-team.install.*")), [])
            self.assertEqual(list((target / ".autonomous-dev-team").glob(".install_stage.*")), [])

    def test_native_provider_outputs_and_codex_hierarchy(self):
        outputs = sync.generate_all_outputs(BASE_DIR, "all")
        codex = outputs[BASE_DIR / ".codex" / "config.toml"]
        self.assertIn("[agents.architect]", codex)
        self.assertNotIn("[agents.code-explorer]", codex)
        self.assertNotIn("[agents.planner]", codex)
        self.assertNotIn("[agents.quick-implementer]", codex)
        self.assertNotIn("[agents]\n", codex)
        self.assertNotIn("[agents.orchestrator]", codex)
        cfg = sync.load_config(BASE_DIR / sync.CONFIG_NAME)
        codex_orch = sync.resolve_orchestrator(cfg, "codex")
        codex_roster = sync.provider_agents(cfg, "codex")
        claude_roster = sync.provider_agents(cfg, "claude")
        self.assertIn(f'model = "{codex_orch["model"]}"', codex)
        self.assertIn('model_reasoning_effort = "low"', codex)
        self.assertIn("tool_output_token_limit = 6000", codex)
        self.assertIn("model_auto_compact_token_limit = 45000", codex)
        self.assertIn('model_auto_compact_token_limit_scope = "body_after_prefix"', codex)
        self.assertIn("MANDATORY MULTI-AGENT INSTRUCTION:", codex)
        self.assertIn("explicitly ask for sub-agents, delegation, and parallel agent work", codex)
        for agent_name in ("architect", "implementer", "verifier"):
            agent = outputs[BASE_DIR / ".codex" / "agents" / f"{agent_name}.toml"]
            self.assertIn('model_reasoning_effort = "medium"', agent)
            self.assertIn(f'model = "{codex_roster[agent_name]["model"]}"', agent)
            self.assertNotIn("## Model escalation ladder", agent)
        self.assertNotIn(BASE_DIR / "CLAUDE.md", outputs)
        claude_agent = outputs[BASE_DIR / ".claude" / "agents" / "implementer.md"]
        self.assertTrue(claude_agent.startswith("---\nname: implementer\n"))
        self.assertIn("implementer agent for autonomous-dev-team", claude_agent)
        self.assertIn("provider-configured reasoning effort", claude_agent)
        self.assertNotIn("Default:** `low` reasoning effort", claude_agent)
        for agent_name in ("architect", "implementer", "verifier"):
            claude_agent = outputs[BASE_DIR / ".claude" / "agents" / f"{agent_name}.md"]
            self.assertIn(f"model: {claude_roster[agent_name]['model']}", claude_agent)
            self.assertIn(f"reasoning effort: {claude_roster[agent_name]['thinking']}", claude_agent)
            self.assertNotIn("## Model escalation ladder", claude_agent)
        orch_claude = outputs[BASE_DIR / ".claude" / "agents" / "orchestrator.md"]
        self.assertIn("Use Claude Code's native agent configuration", orch_claude)
        self.assertIn("## Claude Model Routing", orch_claude)
        for agent_name in ("architect", "implementer", "verifier"):
            a = claude_roster[agent_name]
            self.assertIn(f"- `{agent_name}`: `{a['model']}` (thinking: `{a['thinking']}`; advisory)", orch_claude)
        models = cfg["models"]
        self.assertIn("## Model escalation ladder", codex)
        self.assertIn(
            f"- `implementer`: `balanced` (`{models['balanced']['codex']}`, effort `medium`) -> "
            f"`balanced` (`{models['balanced']['codex']}`, effort `high`) -> "
            f"`deep` (`{models['deep']['codex']}`, effort `medium`) -> "
            f"`ultra` (`{models['ultra']['codex']}`, effort `medium`, exceptional)",
            codex,
        )
        self.assertIn(
            f"- `implementer`: `balanced` (`{models['balanced']['claude']}`, effort `medium`) -> "
            f"`deep` (`{models['deep']['claude']}`, effort `medium`) -> "
            f"`ultra` (`{models['ultra']['claude']}`, effort `medium`, exceptional)",
            orch_claude,
        )
        agents_md = outputs[BASE_DIR / "AGENTS.md"]
        self.assertNotIn("## Claude Model Routing", agents_md)
        self.assertNotIn("## Antigravity Dispatch Syntax", agents_md)
        self.assertLessEqual(len(agents_md), 1600)
        self.assertLessEqual(sync.estimate_tokens(len(agents_md)), 400)
        self.assertNotIn("specialist", agents_md.lower())
        self.assertNotIn("GEMINI.md", [p.name for p in outputs])

    def test_correctness_first_routing_contract_is_generated(self):
        outputs = sync.generate_all_outputs(BASE_DIR, "all")
        self.assertNotIn(BASE_DIR / "CLAUDE.md", outputs)
        adapters = (
            outputs[BASE_DIR / ".codex" / "config.toml"],
            outputs[BASE_DIR / ".claude" / "agents" / "orchestrator.md"],
        )
        for content in adapters:
            self.assertIn("Highest-priority `/team` fast path", content)
            self.assertIn("treat `--team` exclusively as a direct `sync.py` argument", content)
            self.assertIn("`npm run build --team` is invalid", content)
            self.assertIn("without a fallback command", content)
            self.assertIn("touches ≤3 files, modifies ≤150 lines", content)
            self.assertIn("never remove a required correctness gate", content)
            self.assertIn("permit multiple gates for genuinely distinct risks", content)
            self.assertIn("After 8 direct tool calls", content)
            self.assertIn("after 12, replan or explain", content)
            self.assertIn("Never report success while required verification is failing or incomplete", content)
        self.assertNotIn("Highest-priority `/team` fast path", outputs[BASE_DIR / "AGENTS.md"])
        self.assertNotIn("Adaptive routing", outputs[BASE_DIR / "AGENTS.md"])

        implementer_prompt = (BASE_DIR / "agents" / "implementer.md").read_text(encoding="utf-8")
        self.assertIn("provider-configured reasoning effort", implementer_prompt)
        self.assertNotIn("Escalate to `medium` or `high`", implementer_prompt)

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
            self.assertFalse((tmppath / "CLAUDE.md").exists())
            self.assertTrue((tmppath / "AGENTS.md").exists())
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
        self.assertIn("architect", output)
        cfg = sync.load_config(BASE_DIR / sync.CONFIG_NAME)
        self.assertIn(cfg["models"]["balanced"]["antigravity"], output)
        self.assertIn("adaptive: balanced `", output)
        self.assertIn("effort unsupported; ineffective steps collapsed", output)
        self.assertNotIn("-> ultra `", output)

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

    def test_skill_generation(self):
        outputs = sync.generate_all_outputs(BASE_DIR, "all")
        skill_names = {
            "team", "agent-introspection-debugging", "documentation-lookup",
            "verification-loop", "agent-sort", "eval-harness", "tdd-workflow",
            "security-review", "coding-standards",
        }

        for skill_name in skill_names:
            paths = (
                BASE_DIR / ".agents" / "skills" / skill_name / "SKILL.md",
                BASE_DIR / ".claude" / "skills" / skill_name / "SKILL.md",
                BASE_DIR / ".codex" / "prompts" / f"{skill_name}.md",
            )
            for skill_path in paths:
                self.assertIn(skill_path, outputs)
                self.assertTrue(outputs[skill_path].startswith(f"---\nname: {skill_name}\n"))

        team_paths = (
            BASE_DIR / ".agents" / "skills" / "team" / "SKILL.md",
            BASE_DIR / ".claude" / "skills" / "team" / "SKILL.md",
            BASE_DIR / ".codex" / "prompts" / "team.md",
        )
        for spath in team_paths:
            content = outputs[spath]
            self.assertIn("Run exactly one of these literal commands", content)
            self.assertIn("python3 .autonomous-dev-team/sync.py --team", content)
            self.assertIn("python3 sync.py --team", content)
            self.assertIn("`npm run build --team` is invalid", content)
            self.assertIn("Do not probe for files first", content)
            self.assertIn("without running a fallback or diagnostic command", content)
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

        agent_sort_paths = (
            BASE_DIR / ".agents" / "skills" / "agent-sort" / "SKILL.md",
            BASE_DIR / ".claude" / "skills" / "agent-sort" / "SKILL.md",
            BASE_DIR / ".codex" / "prompts" / "agent-sort.md",
        )
        for spath in agent_sort_paths:
            content = outputs[spath]
            self.assertIn("first-pass correctness before token minimization", content)
            self.assertIn("checkpoints govern work performed, not provider billing", content)
            self.assertIn("separate gates for distinct risks", content)

        self.assertFalse(any(path.name == "openai.yaml" for path in outputs))
        self.assertFalse(any(path.name == "openai.yaml" for path in (BASE_DIR / "skills").rglob("*")))

    def test_codex_scope_generates_implicit_and_explicit_skills(self):
        outputs = sync.generate_all_outputs(BASE_DIR, "codex")
        for skill_name in ("team", "verification-loop", "security-review"):
            self.assertIn(BASE_DIR / ".agents" / "skills" / skill_name / "SKILL.md", outputs)
            self.assertIn(BASE_DIR / ".codex" / "prompts" / f"{skill_name}.md", outputs)
        self.assertFalse(any(path.parts[-3:-1] == (".claude", "skills") for path in outputs))

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
            tmppath = Path(tmpdir).resolve()
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
            self.assertFalse((tmppath / "CLAUDE.md").exists())
            self.assertTrue((tmppath / "AGENTS.md").exists())
            self.assertTrue((tmppath / ".codex" / "config.toml").exists())
            self.assertEqual(sync.run_check(tmppath, "all"), 0)

    def test_client_encapsulated_layout_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir).resolve()
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
            self.assertFalse((tmppath / "CLAUDE.md").exists())
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
            tmppath = Path(tmpdir).resolve()
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
            self.assertFalse((tmppath / "CLAUDE.md").exists())
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

    def test_trampoline_build_args_module_mode(self):
        target_py = "/mock/bin/python3.11"
        argv = ["python3 -m unittest", "discover", "tests"]
        expected = [target_py, "-m", "unittest", "discover", "tests"]
        self.assertEqual(sync.build_trampoline_args(target_py, argv), expected)

    def test_trampoline_build_args_script_mode(self):
        target_py = "/mock/bin/python3.11"
        argv = ["sync.py", "--check"]
        expected = [target_py, "sync.py", "--check"]
        self.assertEqual(sync.build_trampoline_args(target_py, argv), expected)

    def test_trampoline_build_args_bypasses(self):
        target_py = "/mock/bin/python3.11"
        self.assertIsNone(sync.build_trampoline_args(target_py, ["-c"]))
        self.assertIsNone(sync.build_trampoline_args(target_py, ["-c", "import sys"]))
        self.assertIsNone(sync.build_trampoline_args(target_py, []))

    def test_trampoline_reexec_behavior(self):
        target_py = "/mock/bin/python3.11"
        with mock.patch("os.execv") as mock_execv:
            argv = ["python3 -m unittest", "discover", "tests"]
            args = sync.build_trampoline_args(target_py, argv)
            if args is not None:
                mock_execv(target_py, args)
            mock_execv.assert_called_once_with(
                target_py,
                [target_py, "-m", "unittest", "discover", "tests"],
            )

        with mock.patch("os.execv") as mock_execv:
            argv = ["-c"]
            args = sync.build_trampoline_args(target_py, argv)
            if args is not None:
                mock_execv(target_py, args)
            mock_execv.assert_not_called()

    def test_legacy_claude_md_is_unlinked_when_tracked_in_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            self.copy_canonical_sources(tmppath)
            shutil.copy(BASE_DIR / sync.CONFIG_NAME, tmppath / sync.CONFIG_NAME)
            legacy_claude = tmppath / "CLAUDE.md"
            legacy_claude.write_text(f"{sync.AUTO_GEN_HEADER_MD}\n# Legacy Claude", encoding="utf-8")
            (tmppath / sync.MANIFEST_NAME).write_text(
                json.dumps({"schema": sync.SCHEMA_NAME, "version": sync.SCHEMA_VERSION, "files": ["CLAUDE.md"]}),
                encoding="utf-8"
            )
            self.assertTrue(legacy_claude.exists())
            sync.run_sync(tmppath, "all")
            self.assertFalse(legacy_claude.exists())
            manifest = json.loads((tmppath / sync.MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertNotIn("CLAUDE.md", manifest["files"])
            self.assertIn("AGENTS.md", manifest["files"])

    def test_legacy_claude_md_is_unlinked_in_scoped_claude_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            self.copy_canonical_sources(tmppath)
            shutil.copy(BASE_DIR / sync.CONFIG_NAME, tmppath / sync.CONFIG_NAME)
            legacy_claude = tmppath / "CLAUDE.md"
            legacy_claude.write_text(f"{sync.AUTO_GEN_HEADER_MD}\n# Legacy Claude", encoding="utf-8")
            (tmppath / sync.MANIFEST_NAME).write_text(
                json.dumps({"schema": sync.SCHEMA_NAME, "version": sync.SCHEMA_VERSION, "files": ["CLAUDE.md"]}),
                encoding="utf-8"
            )
            self.assertTrue(legacy_claude.exists())
            sync.run_sync(tmppath, "claude")
            self.assertFalse(legacy_claude.exists())
            manifest = json.loads((tmppath / sync.MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertNotIn("CLAUDE.md", manifest["files"])
            self.assertIn("AGENTS.md", manifest["files"])

    def test_stale_claude_agents_are_unlinked_when_tracked_in_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            self.copy_canonical_sources(tmppath)
            shutil.copy(BASE_DIR / sync.CONFIG_NAME, tmppath / sync.CONFIG_NAME)
            stale_agent = tmppath / ".claude" / "agents" / "code-explorer.md"
            stale_agent.parent.mkdir(parents=True, exist_ok=True)
            stale_agent.write_text("---\nname: code-explorer\n---\n# Stale Agent", encoding="utf-8")
            (tmppath / sync.MANIFEST_NAME).write_text(
                json.dumps({
                    "schema": sync.SCHEMA_NAME,
                    "version": sync.SCHEMA_VERSION,
                    "files": [".claude/agents/code-explorer.md"]
                }),
                encoding="utf-8"
            )
            self.assertTrue(stale_agent.exists())
            sync.run_sync(tmppath, "claude")
            self.assertFalse(stale_agent.exists())
            manifest = json.loads((tmppath / sync.MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertNotIn(".claude/agents/code-explorer.md", manifest["files"])
            self.assertIn(".claude/agents/architect.md", manifest["files"])

    def test_compile_agents_md_and_output_provider(self):
        self.assertEqual(sync.output_provider("AGENTS.md"), "shared")
        self.assertEqual(sync.output_provider("CLAUDE.md"), "claude")
        self.assertEqual(sync.output_provider(".claude/agents/implementer.md"), "claude")
        self.assertEqual(sync.output_provider(".agents/agents/implementer/agent.md"), "antigravity")
        self.assertEqual(sync.output_provider(".agents/skills/security-review/SKILL.md"), "antigravity")
        self.assertEqual(sync.output_provider(".agents/skills/tdd-workflow/SKILL.md"), "antigravity")
        self.assertEqual(sync.output_provider(".codex/config.toml"), "codex")

        config = sync.load_config(sync.resolve_config_path(BASE_DIR))
        project = config.get("project", {})
        guardrails = sync.build_project_guardrails(project)

        slim_md = sync.compile_agents_md(config, project, guardrails, BASE_DIR)
        self.assertIn("# autonomous-dev-team", slim_md)
        self.assertIn("## Repository Guardrails & Commands", slim_md)
        self.assertNotIn("## Claude Subagent Guidance", slim_md)
        self.assertNotIn("## Claude Model Routing", slim_md)
        self.assertNotIn("## Antigravity Dispatch Syntax", slim_md)
        self.assertNotIn("Adaptive routing", slim_md)
        self.assertNotIn("Highest-priority `/team` fast path", slim_md)
        self.assertLessEqual(len(slim_md), 1600)
        self.assertLessEqual(sync.estimate_tokens(len(slim_md)), 400)

    def test_orchestrator_uses_provider_native_role_path(self):
        """Ensure orchestrator protocol text references the correct provider-native agent path."""
        config = sync.load_config(sync.resolve_config_path(BASE_DIR))
        project = dict(config.get("project", {}))
        project["forbidden_paths"] = sync.get_effective_forbidden_paths(project)
        guardrails = sync.build_project_guardrails(project)

        claude_proto = sync.compile_orchestrator_protocol(BASE_DIR, project, guardrails, provider="claude")
        self.assertIn(".claude/agents/", claude_proto)
        self.assertNotIn(".agents/agents/", claude_proto)
        self.assertNotIn(".codex/agents/", claude_proto)

        codex_proto = sync.compile_orchestrator_protocol(BASE_DIR, project, guardrails, provider="codex")
        self.assertIn(".codex/agents/", codex_proto)
        self.assertNotIn(".agents/agents/", codex_proto)
        self.assertNotIn(".claude/agents/", codex_proto)

        agy_proto = sync.compile_orchestrator_protocol(BASE_DIR, project, guardrails, provider="antigravity")
        self.assertIn(".agents/agents/", agy_proto)
        self.assertNotIn(".claude/agents/", agy_proto)
        self.assertNotIn(".codex/agents/", agy_proto)

    def test_estimate_tokens(self):
        self.assertEqual(sync.estimate_tokens(0), 0)
        self.assertEqual(sync.estimate_tokens(4), 1)
        self.assertEqual(sync.estimate_tokens(10), 2)
        self.assertEqual(sync.estimate_tokens(100), 25)
        self.assertEqual(sync.estimate_tokens(9758), 2440)

    def test_run_stats_data(self):
        stats = sync.run_stats(BASE_DIR, "all", quiet=True)
        self.assertIn("antigravity", stats)
        self.assertIn("claude", stats)
        self.assertIn("codex", stats)

        for prov in ("antigravity", "claude", "codex"):
            p_data = stats[prov]
            self.assertEqual(p_data["provider"], prov)
            self.assertIn("display_name", p_data)
            self.assertIn("ambient", p_data)
            self.assertIn("orchestrator", p_data)
            self.assertIn("subagents", p_data)
            self.assertIn("total_active_tree", p_data)

            ambient = p_data["ambient"]
            self.assertIsInstance(ambient["characters"], int)
            self.assertEqual(ambient["tokens"], sync.estimate_tokens(ambient["characters"]))
            if prov in ("antigravity", "claude"):
                self.assertLessEqual(ambient["characters"], 1600)
                self.assertLessEqual(ambient["tokens"], 400)

            orch = p_data["orchestrator"]
            self.assertIsInstance(orch["characters"], int)
            self.assertGreater(orch["characters"], 0)
            self.assertEqual(orch["tokens"], sync.estimate_tokens(orch["characters"]))

            tree = p_data["total_active_tree"]
            self.assertIsInstance(tree["characters"], int)
            self.assertGreater(tree["characters"], 0)
            self.assertEqual(tree["tokens"], sync.estimate_tokens(tree["characters"]))
            expected_files = 13 if prov == "codex" else 14
            self.assertEqual(tree["files_count"], expected_files)

            subagents = p_data["subagents"]
            self.assertIn("implementer", subagents)
            self.assertIn("architect", subagents)
            self.assertIn("verifier", subagents)
            self.assertEqual(len(subagents), 3)

            for role_name, s_info in subagents.items():
                self.assertGreater(s_info["role_characters"], 0)
                self.assertEqual(
                    s_info["start_cost_characters"],
                    s_info["role_characters"] + ambient["characters"]
                )
                self.assertEqual(
                    s_info["start_cost_tokens"],
                    sync.estimate_tokens(s_info["start_cost_characters"])
                )

    def test_stats_cli(self):
        # 1. Test full stats CLI output
        res = subprocess.run(
            [sys.executable, str(BASE_DIR / "sync.py"), "--stats"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"sync.py --stats failed: {res.stderr}")
        self.assertIn("Autonomous Dev Team — Context & Token Statistics", res.stdout)
        self.assertIn("[Google Antigravity]", res.stdout)
        self.assertIn("[Claude Code]", res.stdout)
        self.assertIn("[Codex]", res.stdout)
        self.assertIn("Ambient Files:", res.stdout)
        self.assertIn("Root Orchestrator:", res.stdout)
        self.assertIn("Subagent Start Costs (ambient + role):", res.stdout)
        self.assertIn("Total Active Tree:", res.stdout)
        self.assertIn("implementer", res.stdout)
        self.assertIn("architect", res.stdout)
        self.assertIn("verifier", res.stdout)

        # 2. Test scoped stats CLI output (--provider claude)
        res_claude = subprocess.run(
            [sys.executable, str(BASE_DIR / "sync.py"), "--stats", "--provider", "claude"],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
        )
        self.assertEqual(res_claude.returncode, 0, f"sync.py --stats --provider claude failed: {res_claude.stderr}")
        self.assertIn("[Claude Code]", res_claude.stdout)
        self.assertNotIn("[Google Antigravity]", res_claude.stdout)
        self.assertNotIn("[Codex]", res_claude.stdout)

    def test_golden_set_tasks(self):
        tasks_file = BASE_DIR / "tests" / "golden_set" / "tasks.json"
        self.assertTrue(tasks_file.is_file())
        tasks = json.loads(tasks_file.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(tasks), 8)
        self.assertLessEqual(len(tasks), 12)

        tiers = {t["tier"] for t in tasks}
        self.assertIn("T1", tiers)
        self.assertIn("T2", tiers)
        self.assertIn("T3", tiers)

        required_keys = {"id", "tier", "description", "files_touched", "expected_verification", "risk_category"}
        for task in tasks:
            for k in required_keys:
                self.assertIn(k, task)
            self.assertIsInstance(task["files_touched"], list)
            self.assertGreater(len(task["files_touched"]), 0)

    def test_v1_snapshot_fixtures(self):
        snapshot_dir = BASE_DIR / "tests" / "fixtures" / "v1_snapshot"
        self.assertTrue(snapshot_dir.is_dir())
        self.assertTrue((snapshot_dir / "AGENTS.md").is_file())
        self.assertTrue((snapshot_dir / ".codex" / "config.toml").is_file())
        self.assertTrue((snapshot_dir / ".claude" / "agents" / "implementer.md").is_file())
        self.assertTrue((snapshot_dir / ".agents" / "agents" / "implementer" / "agent.md").is_file())

    def test_schema_v1_hard_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            v1_config = tmppath / sync.CONFIG_NAME
            v1_config.write_text(
                '[schema]\nname = "autonomous-dev-team"\nversion = 1\n[project]\nname = "v1-app"\n',
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit) as cm:
                sync.load_config(v1_config)
            self.assertEqual(str(cm.exception), "Error: Config schema v1 is unsupported. Update to schema_version = 2.")

            # Also verify when schema_version is missing entirely
            missing_version_cfg = tmppath / "no_version.toml"
            missing_version_cfg.write_text('[project]\nname = "no-version"\n', encoding="utf-8")
            with self.assertRaises(SystemExit) as cm:
                sync.load_config(missing_version_cfg)
            self.assertEqual(str(cm.exception), "Error: Config schema v1 is unsupported. Update to schema_version = 2.")

    def test_adaptive_reasoning_policy(self):
        cfg = sync.load_config(Path(__file__).resolve().parents[1] / ".autonomous-dev-team.toml")
        steps = sync.resolve_adaptive_steps(cfg, "codex")["implementer"]
        self.assertEqual([(s["tier"], s["effort"]) for s in steps],
                         [("balanced", "medium"), ("balanced", "high"),
                          ("deep", "medium"), ("ultra", "medium")])
        native = sync.render_escalation_ladder(cfg, "codex")
        self.assertIn("model AND reasoning_effort", native)
        self.assertIn("max 3 total repair attempts", native)
        self.assertIn("advisory", sync.render_escalation_ladder(cfg, "claude"))
        self.assertIn("unsupported", sync.render_escalation_ladder(cfg, "antigravity"))
        self.assertEqual(len(sync.resolve_adaptive_steps(cfg, "antigravity")["implementer"]), 1)
        self.assertEqual(len(sync.resolve_adaptive_steps(cfg, "claude")["implementer"]), 3)
        self.assertIn("reset for unrelated slices", (BASE_DIR / "agents/orchestrator.md").read_text())
        self.assertIn("never reset the counter by escalating", (BASE_DIR / "agents/orchestrator.md").read_text())
        cfg["agents"]["implementer"]["adaptive_steps"][0]["effort"] = "typo"
        self.assertTrue(any("effort" in e for e in sync.validate_model_tiers(cfg)))
        cfg["reasoning_policy"]["max_repairs"] = 0
        self.assertTrue(any("max_repairs" in e for e in sync.validate_model_tiers(cfg)))

    def test_escalation_ladder_resolution_and_tier_validation(self):
        cfg = {
            "schema_version": 2,
            "models": {
                "balanced": {"codex": "c-bal", "claude": "cl-bal", "antigravity": "a-bal"},
                "deep": {"codex": "c-deep", "claude": "cl-deep", "antigravity": "a-deep"},
                "ultra": {"codex": "c-ultra", "claude": "cl-ultra", "antigravity": "a-ultra"},
            },
            "orchestrator": {"tier": "balanced"},
            "agents": {
                "implementer": {"tier": "balanced", "escalation": ["deep", "ultra"]},
                "verifier": {"tier": "balanced"},
            },
        }
        self.assertEqual(sync.validate_model_tiers(cfg), [])
        ladders = sync.resolve_escalation_ladders(cfg, "claude")
        self.assertEqual(ladders, {"implementer": [("balanced", "cl-bal"), ("deep", "cl-deep"), ("ultra", "cl-ultra")]})
        self.assertNotIn("verifier", ladders)
        self.assertIn("`balanced` (`c-bal`) -> `deep` (`c-deep`) -> `ultra` (`c-ultra`)",
                      sync.render_escalation_ladder(cfg, "codex"))

        cfg["agents"]["implementer"]["escalation"] = ["deep", "hyper"]
        cfg["agents"]["verifier"]["tier"] = "ultar"
        errors = sync.validate_model_tiers(cfg)
        self.assertTrue(any("'hyper'" in e for e in errors))
        self.assertTrue(any("agents.verifier references unknown model tier 'ultar'" in e for e in errors))

        with tempfile.TemporaryDirectory() as tmpdir:
            bad = Path(tmpdir) / "bad.toml"
            bad.write_text(
                'schema_version = 2\n[models]\nbalanced = { codex = "x" }\n'
                '[agents.implementer]\ntier = "balanced"\nescalation = ["ultra"]\n',
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit) as cm:
                sync.load_config(bad)
            self.assertIn("unknown model tier 'ultra'", str(cm.exception))

    def test_schema_v2_model_aliases(self):
        sample_config = {
            "schema_version": 2,
            "project": {"name": "test-project"},
            "models": {
                "fast": {"codex": "gpt-6-luna", "claude": "claude-3-5-haiku", "antigravity": "flash"},
                "balanced": {"codex": "gpt-6.1-sol", "claude": "claude-3-7-sonnet", "antigravity": "flash"},
                "deep": {"codex": "gpt-6.1-sol", "claude": "claude-3-7-sonnet", "antigravity": "flash"},
            },
            "orchestrator": {
                "tier": "balanced",
                "reasoning_effort": "low",
            },
            "agents": {
                "fast-agent": {
                    "description": "Fast scout",
                    "tier": "fast",
                    "reasoning_effort": "low",
                },
                "balanced-agent": {
                    "description": "Balanced builder",
                    "tier": "balanced",
                    "reasoning_effort": "medium",
                },
                "deep-agent": {
                    "description": "Deep planner",
                    "tier": "deep",
                    "reasoning_effort": "high",
                },
            },
        }

        # 1. Test Codex resolution
        codex_agents = sync.provider_agents(sample_config, "codex")
        self.assertEqual(codex_agents["fast-agent"]["model"], "gpt-6-luna")
        self.assertEqual(codex_agents["fast-agent"]["reasoning_effort"], "low")
        self.assertEqual(codex_agents["balanced-agent"]["model"], "gpt-6.1-sol")
        self.assertEqual(codex_agents["balanced-agent"]["reasoning_effort"], "medium")
        self.assertEqual(codex_agents["deep-agent"]["model"], "gpt-6.1-sol")
        self.assertEqual(codex_agents["deep-agent"]["reasoning_effort"], "high")

        # 2. Test Claude resolution (thinking follows reasoning_effort for every model)
        claude_agents = sync.provider_agents(sample_config, "claude")
        self.assertEqual(claude_agents["fast-agent"]["model"], "claude-3-5-haiku")
        self.assertEqual(claude_agents["fast-agent"]["thinking"], "low")
        self.assertEqual(claude_agents["balanced-agent"]["model"], "claude-3-7-sonnet")
        self.assertEqual(claude_agents["balanced-agent"]["thinking"], "medium")
        self.assertEqual(claude_agents["deep-agent"]["model"], "claude-3-7-sonnet")
        self.assertEqual(claude_agents["deep-agent"]["thinking"], "high")

        # 3. Test Antigravity resolution
        agy_agents = sync.provider_agents(sample_config, "antigravity")
        self.assertEqual(agy_agents["fast-agent"]["model"], "flash")
        self.assertEqual(agy_agents["fast-agent"]["reasoning"], "low")
        self.assertEqual(agy_agents["balanced-agent"]["model"], "flash")
        self.assertEqual(agy_agents["balanced-agent"]["reasoning"], "medium")
        self.assertEqual(agy_agents["deep-agent"]["model"], "flash")
        self.assertEqual(agy_agents["deep-agent"]["reasoning"], "high")

        # 4. Test Orchestrator resolution across all providers
        codex_orch = sync.resolve_orchestrator(sample_config, "codex")
        self.assertEqual(codex_orch["model"], "gpt-6.1-sol")
        self.assertEqual(codex_orch["reasoning_effort"], "low")

        claude_orch = sync.resolve_orchestrator(sample_config, "claude")
        self.assertEqual(claude_orch["model"], "claude-3-7-sonnet")
        self.assertEqual(claude_orch["thinking"], "low")

        agy_orch = sync.resolve_orchestrator(sample_config, "antigravity")
        self.assertEqual(agy_orch["model"], "flash")
        self.assertEqual(agy_orch["reasoning"], "low")

    def test_check_fails_on_budget_exceeded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            self.copy_canonical_sources(tmppath)
            shutil.copy(BASE_DIR / sync.CONFIG_NAME, tmppath / sync.CONFIG_NAME)
            sync.run_sync(tmppath)
            self.assertEqual(sync.run_check(tmppath, quiet=True), 0)

            # 1. Bloat AGENTS.md directly beyond MAX_AMBIENT_CHARS (1600 chars)
            agents_file = tmppath / "AGENTS.md"
            original_agents_content = agents_file.read_text(encoding="utf-8")
            agents_file.write_text(original_agents_content + "\n" + ("X" * 2000), encoding="utf-8")
            self.assertEqual(sync.run_check(tmppath, quiet=True), 1)

            # Reset AGENTS.md
            agents_file.write_text(original_agents_content, encoding="utf-8")
            self.assertEqual(sync.run_check(tmppath, quiet=True), 0)

            # 2. Bloat canonical source agents/implementer.md and sync
            impl_src = tmppath / "agents" / "implementer.md"
            original_impl_content = impl_src.read_text(encoding="utf-8")
            impl_src.write_text(original_impl_content + "\n" + ("Y" * 2000), encoding="utf-8")
            sync.run_sync(tmppath)
            self.assertEqual(sync.run_check(tmppath, quiet=True), 1)

            # Reset implementer.md
            impl_src.write_text(original_impl_content, encoding="utf-8")
            sync.run_sync(tmppath)
            self.assertEqual(sync.run_check(tmppath, quiet=True), 0)

    def test_check_fails_on_orchestrator_leakage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            self.copy_canonical_sources(tmppath)
            shutil.copy(BASE_DIR / sync.CONFIG_NAME, tmppath / sync.CONFIG_NAME)
            sync.run_sync(tmppath)
            self.assertEqual(sync.run_check(tmppath, quiet=True), 0)

            impl_src = tmppath / "agents" / "implementer.md"
            original_impl_content = impl_src.read_text(encoding="utf-8")

            for marker in sync.LEAKAGE_MARKERS:
                impl_src.write_text(original_impl_content + f"\nForbidden marker: {marker}\n", encoding="utf-8")
                sync.run_sync(tmppath)
                self.assertEqual(
                    sync.run_check(tmppath, quiet=True),
                    1,
                    f"run_check should fail when leakage marker '{marker}' is present",
                )

            # Reset and verify clean check passes
            impl_src.write_text(original_impl_content, encoding="utf-8")
            sync.run_sync(tmppath)
            self.assertEqual(sync.run_check(tmppath, quiet=True), 0)

    def test_run_verify_cli(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            self.copy_canonical_sources(tmppath)

            # 1. Verify success path with passing verify commands
            pass_cfg = """
schema_version = 2
active_provider = "all"
[project]
name = "test-proj"
[verify]
commands = ["python3 -c \\"import sys; sys.exit(0)\\""]
"""
            (tmppath / sync.CONFIG_NAME).write_text(pass_cfg.strip() + "\n", encoding="utf-8")

            # Standard mode
            self.assertEqual(sync.run_verify(tmppath, hook_mode=False), 0)

            # Hook mode
            with io.StringIO() as buf, redirect_stdout(buf):
                ret = sync.run_verify(tmppath, hook_mode=True)
                self.assertEqual(ret, 0)
                payload = json.loads(buf.getvalue().strip())
                self.assertEqual(payload, {"decision": "allow"})

            # CLI subprocess with --run-verify
            res = subprocess.run(
                [sys.executable, str(BASE_DIR / "sync.py"), "--run-verify", "--dir", str(tmppath)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0)

            # CLI subprocess with --run-verify --hook
            res_hook = subprocess.run(
                [sys.executable, str(BASE_DIR / "sync.py"), "--run-verify", "--hook", "--dir", str(tmppath)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res_hook.returncode, 0)
            payload = json.loads(res_hook.stdout.strip())
            self.assertEqual(payload, {"decision": "allow"})

            # 2. Verify failure path with failing verify commands
            fail_cfg = """
schema_version = 2
active_provider = "all"
[project]
name = "test-proj"
[verify]
commands = ["python3 -c \\"import sys; sys.exit(1)\\""]
"""
            (tmppath / sync.CONFIG_NAME).write_text(fail_cfg.strip() + "\n", encoding="utf-8")

            # Standard mode (exits 1)
            self.assertEqual(sync.run_verify(tmppath, hook_mode=False), 1)

            # Hook mode (exits 0 with continue decision)
            with io.StringIO() as buf, redirect_stdout(buf):
                ret = sync.run_verify(tmppath, hook_mode=True)
                self.assertEqual(ret, 0)
                payload = json.loads(buf.getvalue().strip())
                self.assertEqual(payload["decision"], "continue")
                self.assertIn("reason", payload)

            # CLI subprocess failure
            res_fail = subprocess.run(
                [sys.executable, str(BASE_DIR / "sync.py"), "--run-verify", "--dir", str(tmppath)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res_fail.returncode, 1)

            # CLI subprocess failure in hook mode
            res_fail_hook = subprocess.run(
                [sys.executable, str(BASE_DIR / "sync.py"), "--run-verify", "--hook", "--dir", str(tmppath)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res_fail_hook.returncode, 0)
            payload_fail = json.loads(res_fail_hook.stdout.strip())
            self.assertEqual(payload_fail["decision"], "continue")

    def test_antigravity_hooks_generation(self):
        hooks_content = sync.compile_antigravity_hooks(BASE_DIR)
        hooks_data = json.loads(hooks_content)
        self.assertIn("verify-gate", hooks_data)
        self.assertIn("Stop", hooks_data["verify-gate"])
        stop_actions = hooks_data["verify-gate"]["Stop"]
        self.assertEqual(len(stop_actions), 1)
        self.assertEqual(stop_actions[0]["type"], "command")
        self.assertIn("sync.py --run-verify --hook", stop_actions[0]["command"])

        # Encapsulated base_dir
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            nested = tmppath / sync.ENCAPSULATED_DIR_NAME
            nested.mkdir()
            (nested / "sync.py").touch()
            encap_hooks = json.loads(sync.compile_antigravity_hooks(tmppath))
            self.assertIn(f"{sync.ENCAPSULATED_DIR_NAME}/sync.py", encap_hooks["verify-gate"]["Stop"][0]["command"])

    def test_canonical_roster_consolidation(self):
        """Verifies exactly 3 subagents (architect, implementer, verifier) are compiled and deprecated roles are pruned."""
        config_path = BASE_DIR / sync.CONFIG_NAME
        cfg = sync.load_config(config_path)
        self.assertEqual(set(cfg.get("agents", {}).keys()), {"architect", "implementer", "verifier"})

        # Verifier strength at least as strong as implementer
        impl_tier = cfg["agents"]["implementer"]["tier"]
        verif_tier = cfg["agents"]["verifier"]["tier"]
        tier_ranks = {"fast": 1, "balanced": 2, "deep": 3, "ultra": 4}
        self.assertGreaterEqual(tier_ranks[verif_tier], tier_ranks[impl_tier])

        # Implementer escalation ladder climbs strictly: balanced -> deep -> ultra
        ladder = [impl_tier] + cfg["agents"]["implementer"].get("escalation", [])
        self.assertEqual(ladder, ["balanced", "deep", "ultra"])
        self.assertEqual([tier_ranks[t] for t in ladder], sorted({tier_ranks[t] for t in ladder}))
        for prov in ("codex", "claude", "antigravity"):
            self.assertIn(prov, cfg["models"]["ultra"])

        outputs = sync.generate_all_outputs(BASE_DIR, "all")
        codex_subagents = [p.name for p in outputs.keys() if ".codex/agents" in str(p)]
        claude_subagents = [p.name for p in outputs.keys() if ".claude/agents" in str(p) and p.name != "orchestrator.md"]
        agy_subagents = [p.parent.name for p in outputs.keys() if ".agents/agents" in str(p) and p.name == "agent.md"]

        expected_roles = {"architect", "implementer", "verifier"}
        self.assertEqual(set(s.replace(".toml", "") for s in codex_subagents), expected_roles)
        self.assertEqual(set(s.replace(".md", "") for s in claude_subagents), expected_roles)
        self.assertEqual(set(agy_subagents), expected_roles)

        # Manifest synchronization cleanly unlinks deprecated role files
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            self.copy_canonical_sources(tmppath)
            shutil.copy(BASE_DIR / sync.CONFIG_NAME, tmppath / sync.CONFIG_NAME)

            # Simulate preexisting deprecated roles tracked in manifest
            deprecated_files = [
                ".claude/agents/code-validator.md",
                ".claude/agents/code-reviewer.md",
                ".claude/agents/diagnostician.md",
                ".codex/agents/code-validator.toml",
                ".codex/agents/code-reviewer.toml",
                ".codex/agents/diagnostician.toml",
                ".agents/agents/code-validator/agent.md",
                ".agents/agents/code-reviewer/agent.md",
                ".agents/agents/diagnostician/agent.md",
            ]
            for dep in deprecated_files:
                fpath = tmppath / dep
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text("AUTO-GENERATED BY sync.py\nlegacy content", encoding="utf-8")

            (tmppath / sync.MANIFEST_NAME).write_text(
                json.dumps({"schema": sync.SCHEMA_NAME, "version": sync.SCHEMA_VERSION, "files": deprecated_files}),
                encoding="utf-8"
            )

            sync.run_sync(tmppath, "all")

            for dep in deprecated_files:
                self.assertFalse((tmppath / dep).exists(), f"Deprecated file {dep} was not unlinked")

            # Check that empty parent directories in .agents/agents/ were pruned
            for dep_role in ("code-validator", "code-reviewer", "diagnostician"):
                self.assertFalse((tmppath / ".agents" / "agents" / dep_role).exists())

            # Check active subagents exist
            self.assertTrue((tmppath / ".claude" / "agents" / "verifier.md").exists())
            self.assertTrue((tmppath / ".codex" / "agents" / "verifier.toml").exists())
            self.assertTrue((tmppath / ".agents" / "agents" / "verifier" / "agent.md").exists())


if __name__ == "__main__":
    unittest.main()
