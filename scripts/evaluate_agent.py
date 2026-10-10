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


def audit_contract_adherence(content: str, required_keys: list[str]) -> list[str]:
    """Check that required contract sections or keys appear in the agent output."""
    missing = []
    for key in required_keys:
        if not re.search(re.escape(key), content, re.IGNORECASE):
            missing.append(key)
    return missing


def audit_secret_leakage(content: str) -> list[str]:
    """Check for suspicious secret tokens or credentials in the report."""
    leak_patterns = [
        (r"(?i)api[_-]?key\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{16,}['\"]?", "API key"),
        (r"(?i)secret[_-]?key\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{16,}['\"]?", "Secret key"),
        (r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}", "Bearer token"),
        (r"(?i)ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token"),
    ]
    findings = []
    for pattern, desc in leak_patterns:
        if re.search(pattern, content):
            findings.append(desc)
    return findings


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
    args = parser.parse_args()

    content = ""
    if args.report_file:
        report_path = Path(args.report_file)
        if not report_path.is_file():
            sys.exit(f"Error: Report file '{report_path}' not found.")
        content = report_path.read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        content = sys.stdin.read()
    else:
        parser.print_help()
        sys.exit(1)

    print("=== Agent Evaluation Report ===")
    
    # 1. Contract coverage
    required_sections = ["Status:", "Verification:", "Remaining risk:"]
    missing = audit_contract_adherence(content, required_sections)
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

    # 3. Verification audit
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
