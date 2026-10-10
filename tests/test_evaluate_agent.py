import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import evaluate_agent  # noqa: E402


class TestCompletionContractMatchesRoleTemplates(unittest.TestCase):
    """Drift guard: the fields the audit requires must appear in each role's own Completion Format."""

    def test_every_required_field_appears_in_its_role_template(self):
        agents_dir = Path(__file__).resolve().parents[1] / "agents"
        for role, keys in evaluate_agent.REQUIRED_FIELDS.items():
            template = (agents_dir / f"{role}.md").read_text(encoding="utf-8")
            with self.subTest(role=role):
                self.assertEqual(evaluate_agent.audit_contract_adherence(template, keys), [])


class TestContractAuditCaseInsensitivity(unittest.TestCase):
    def test_lowercase_field_satisfies_required_key_and_missing_field_is_reported(self):
        self.assertEqual(evaluate_agent.audit_contract_adherence("status: PASS\nRisk: None", ["Status:"]), [])
        self.assertEqual(evaluate_agent.audit_contract_adherence("Risk: None", ["Status:"]), ["Status:"])

    def test_field_must_start_a_line_so_prose_cannot_satisfy_it(self):
        self.assertEqual(evaluate_agent.audit_contract_adherence("The build status: unknown in prose.", ["Status:"]), ["Status:"])
        self.assertEqual(evaluate_agent.audit_contract_adherence("- **Remaining risk:** edge case", ["Risk:"]), ["Risk:"])

    def test_completion_template_bold_format_is_accepted(self):
        report = "### Completion: x\n- **Status:** PASS\n- **Verification:** exit 0\n- **Risk:** None\n"
        self.assertEqual(evaluate_agent.audit_contract_adherence(report, ["Status:", "Verification:", "Risk:"]), [])


class TestSecretLeakageAuditCoverage(unittest.TestCase):
    def test_token_families_are_flagged_with_their_label(self):
        cases = [
            ("ghp_" + "a" * 36, "GitHub Personal Access Token"),
            ("ghs_" + "a" * 36, "GitHub token"),
            ("gho_" + "a" * 36, "GitHub token"),
            ("ghu_" + "a" * 36, "GitHub token"),
            ("ghr_" + "a" * 36, "GitHub token"),
            ("github_pat_" + "a" * 82, "GitHub fine-grained token"),
        ]
        for token, label in cases:
            with self.subTest(token=token[:12]):
                self.assertEqual(evaluate_agent.audit_secret_leakage(f"x {token} y"), [label])

    def test_length_boundaries(self):
        self.assertEqual(evaluate_agent.audit_secret_leakage("ghp_" + "a" * 35), [])
        self.assertEqual(evaluate_agent.audit_secret_leakage("ghp_" + "a" * 36), ["GitHub Personal Access Token"])
        self.assertEqual(evaluate_agent.audit_secret_leakage("github_pat_" + "a" * 81), [])
        self.assertEqual(evaluate_agent.audit_secret_leakage("github_pat_" + "a" * 82), ["GitHub fine-grained token"])

    def test_clean_report_is_not_flagged(self):
        self.assertEqual(evaluate_agent.audit_secret_leakage("Status: PASS\nRisk: None"), [])


class TestInputLoading(unittest.TestCase):
    def test_reads_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dispatch.md"
            path.write_text("Goal: fix the regression.", encoding="utf-8")
            self.assertEqual(evaluate_agent.read_input(str(path), "dispatch"), "Goal: fix the regression.")

    def test_reads_stdin_when_dash(self):
        with mock.patch("sys.stdin", io.StringIO("Goal: fix the regression.")):
            self.assertEqual(evaluate_agent.read_input("-", "dispatch"), "Goal: fix the regression.")

    def test_reads_special_files_such_as_dev_null(self):
        self.assertEqual(evaluate_agent.read_input("/dev/null", "report"), "")


class TestSkillInjectionAudit(unittest.TestCase):
    def test_flags_bug_fix_dispatch_missing_tdd_workflow(self):
        dispatch = "Goal: fix the regression in the parser. Required behavior: reproduce and fix."
        self.assertEqual(evaluate_agent.audit_skill_injection(dispatch, "implementer"), ["tdd-workflow"])

    def test_cited_skill_is_not_flagged(self):
        dispatch = "Constraints: tdd-workflow (skills/tdd-workflow/SKILL.md): write the failing test first. Fix the regression."
        self.assertEqual(evaluate_agent.audit_skill_injection(dispatch, "implementer"), [])

    def test_only_checks_skills_for_the_receiving_role(self):
        dispatch = "Verify the trust boundary and secret handling."
        self.assertEqual(evaluate_agent.audit_skill_injection(dispatch, "verifier"), ["security-review"])
        self.assertEqual(evaluate_agent.audit_skill_injection(dispatch, "implementer"), [])

    def test_unrelated_dispatch_is_not_flagged(self):
        dispatch = "Goal: rename a local variable for clarity."
        self.assertEqual(evaluate_agent.audit_skill_injection(dispatch, "implementer"), [])


if __name__ == "__main__":
    unittest.main()
