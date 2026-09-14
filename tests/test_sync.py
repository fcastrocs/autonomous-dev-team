#!/usr/bin/env python3
"""
Unit tests for Autonomous Multi-Agent Protocol synchronizer (sync.py).
Verifies stack auto-detection, multi-provider compilation, placeholder integrity,
and --check consistency.
"""

import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sync

BASE_DIR = Path(__file__).resolve().parent.parent

class TestSyncCompiler(unittest.TestCase):

    def test_load_config(self):
        config_path = BASE_DIR / "config.toml"
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
        self.assertEqual(gemini_names, {"AGENTS.md", "GEMINI.md"})

    def test_check_passes_on_current_repo(self):
        code = sync.run_check(BASE_DIR)
        self.assertEqual(code, 0, "run_check should return 0 for clean repository")

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
            
            self.assertTrue((tmppath / "config.toml").exists())
            self.assertTrue((tmppath / ".codex" / "config.toml").exists())
            self.assertTrue((tmppath / "CLAUDE.md").exists())
            self.assertTrue((tmppath / "AGENTS.md").exists())
            self.assertTrue((tmppath / "GEMINI.md").exists())
            
            # Check content of generated config
            with open(tmppath / "config.toml", "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn('Python', content)


if __name__ == "__main__":
    unittest.main()
