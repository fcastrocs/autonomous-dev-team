#!/usr/bin/env python3
"""
scripts/evaluate_agent.py — Agent Contract and Output Quality Audit

Evaluates an agent's output against its dispatch contract, cited evidence,
and completion criteria. Read-only inspection; does not modify repository files.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


# Completion fields each role must return. Must match the Completion Format in agents/<role>.md (checked by tests).
REQUIRED_FIELDS = {
    "implementer": ["Status:", "Verification:", "Risk:"],
    "verifier": ["Status:", "Evidence:", "Classification:", "Risk:"],
}


def audit_contract_adherence(content: str, required_keys: list[str]) -> list[str]:
    """Check that required contract sections or keys appear in the agent output."""
    missing = []
    for key in required_keys:
        # Anchor to a line start, optionally after a list marker and bold markers, so prose cannot satisfy a field.
        pattern = rf"^\s*(?:[-*]\s*)?(?:\*\*)?{re.escape(key)}"
        if not re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
            missing.append(key)
    return missing


def audit_secret_leakage(content: str) -> list[str]:
    """Check for suspicious secret tokens or credentials in the report."""
    leak_patterns = [
        (r"(?i)api[_-]?key\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{16,}['\"]?", "API key"),
        (r"(?i)secret[_-]?key\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{16,}['\"]?", "Secret key"),
        (r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}", "Bearer token"),
        (r"(?i)ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token"),
        (r"(?i)gh[osur]_[a-zA-Z0-9]{36}", "GitHub token"),
        (r"github_pat_[a-zA-Z0-9_]{82}", "GitHub fine-grained token"),
    ]
    findings = []
    for pattern, desc in leak_patterns:
        if re.search(pattern, content):
            findings.append(desc)
    return findings


# Keyword triggers mirror the "Skill injection" table in agents/orchestrator.md.
# Heuristic and advisory: it flags likely omissions, it does not judge the slice.
SKILL_TRIGGERS = {
    "tdd-workflow": ("implementer", [r"\bbug\b", r"regression", r"reproduc"]),
    "security-review": ("verifier", [r"trust boundary", r"secret", r"credential", r"command execution", r"network"]),
    "documentation-lookup": ("architect", [r"external", r"third-party", r"provider behavior", r"\bAPI\b"]),
}


def read_input(arg: str, label: str) -> str:
    """Read a report or dispatch from a file path, or from stdin when arg is '-'. Accepts pipes and /dev/fd paths."""
    if arg == "-":
        return sys.stdin.read()
    try:
        return Path(arg).read_text(encoding="utf-8")
    except OSError as exc:
        sys.exit(f"Error: cannot read {label} '{arg}': {exc}")


def audit_skill_injection(dispatch: str, role: str) -> list[str]:
    """Return skills whose trigger matches a dispatch for this role but that the dispatch does not cite."""
    missing = []
    for skill, (skill_role, triggers) in SKILL_TRIGGERS.items():
        if role != skill_role:
            continue
        triggered = any(re.search(t, dispatch, re.IGNORECASE) for t in triggers)
        if triggered and skill not in dispatch:
            missing.append(skill)
    return missing


def audit_verification_claims(commands: list[str], cwd: Path) -> list[dict]:
    """Run claimed verification commands to confirm they actually pass."""
    results = []
    for cmd in commands:
        try:
            res = subprocess.run(
                cmd,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=120,
            )
            results.append({
                "command": cmd,
                "passed": res.returncode == 0,
                "exit_code": res.returncode,
                "stderr_snippet": res.stderr[:300].strip() if res.returncode != 0 else "",
            })
        except subprocess.TimeoutExpired:
            results.append({
                "command": cmd,
                "passed": False,
                "exit_code": -1,
                "stderr_snippet": "Command timed out after 120s",
            })
    return results


def main():
    parser = argparse.ArgumentParser(description="Audit agent output against dispatch contracts and evidence.")
    parser.add_argument("report_file", nargs="?", help="Path to markdown/text file containing agent completion report.")
    parser.add_argument("--verify-command", action="append", default=[], help="Verification command claimed by agent to run and validate.")
    parser.add_argument("--check-secrets", action="store_true", default=True, help="Scan report for accidental secret leakage.")
    parser.add_argument("--dispatch", help="Dispatch packet sent to the role, as a file path or '-' for stdin; checked for skill injection (advisory).")
    parser.add_argument("--role", default="implementer", help="Role that produced the report or received the dispatch: implementer or verifier.")
    args = parser.parse_args()

    content = ""
    if args.report_file:
        content = read_input(args.report_file, "report")
    elif not sys.stdin.isatty():
        content = sys.stdin.read()
    else:
        parser.print_help()
        sys.exit(1)

    print("=== Agent Evaluation Report ===")
    
    # 1. Contract coverage
    if args.role not in REQUIRED_FIELDS:
        sys.exit(f"Error: no completion contract for role '{args.role}'. Use one of: {', '.join(REQUIRED_FIELDS)}.")
    missing = audit_contract_adherence(content, REQUIRED_FIELDS[args.role])
    if missing:
        print(f"[-] Contract coverage: Missing required fields: {', '.join(missing)}")
    else:
        print("[+] Contract coverage: All required completion fields present.")

    # 2. Secret leakage
    leaks = audit_secret_leakage(content)
    if leaks:
        print(f"[-] Security finding: Potential secrets detected: {', '.join(leaks)}")
    else:
        print("[+] Security audit: No secrets or credentials leaked in report.")

    # 3. Skill injection (advisory: warns, never changes the verdict)
    if args.dispatch:
        if not args.role:
            sys.exit("Error: --dispatch requires --role.")
        skipped = audit_skill_injection(read_input(args.dispatch, "dispatch"), args.role)
        if skipped:
            print(f"[!] Skill injection: trigger matched but not cited for {args.role}: {', '.join(skipped)}")
        else:
            print(f"[+] Skill injection: no missing skill for {args.role}.")

    # 4. Verification audit
    verdict = "PASS"
    if args.verify_command:
        print("\n--- Verification Claim Audit ---")
        results = audit_verification_claims(args.verify_command, Path.cwd())
        for r in results:
            if r["passed"]:
                print(f"  [+] Claimed command passed: `{r['command']}`")
            else:
                print(f"  [-] Claimed command failed (exit {r['exit_code']}): `{r['command']}`")
                if r["stderr_snippet"]:
                    print(f"      {r['stderr_snippet']}")
                verdict = "FAIL"

    if missing or leaks or verdict == "FAIL":
        print(f"\nOverall Verdict: FAIL")
        sys.exit(1)
    else:
        print(f"\nOverall Verdict: PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
