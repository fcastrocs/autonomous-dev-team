#!/usr/bin/env python3
"""
scripts/audit_harness.py — Agent Harness and Context Efficiency Audit

Audits prompt files, token budgets, routing invariants, and active tree size.
Read-only inspection; does not modify repository files.
"""

import argparse
import sys
from pathlib import Path

# Add project root to path to import sync helpers if available
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    import sync
except ImportError:
    sync = None


def audit_prompts(agents_dir: Path) -> list[dict]:
    findings = []
    if not agents_dir.is_dir():
        return [{"severity": "ERROR", "msg": f"Agents directory not found: {agents_dir}"}]

    for prompt_file in sorted(agents_dir.glob("*.md")):
        text = prompt_file.read_text(encoding="utf-8")
        chars = len(text)
        tokens = round(chars / 4)
        is_orch = prompt_file.name == "orchestrator.md"
        limit_chars = 7000 if is_orch else 1800
        limit_tokens = 1750 if is_orch else 450

        status = "OK"
        if chars > limit_chars:
            status = "EXCEEDED"
            findings.append({
                "severity": "WARN",
                "file": prompt_file.name,
                "msg": f"Prompt length {chars} chars exceeds budget ({limit_chars} chars)",
            })

        findings.append({
            "severity": "INFO",
            "file": prompt_file.name,
            "chars": chars,
            "tokens": tokens,
            "status": status,
        })
    return findings


def main():
    parser = argparse.ArgumentParser(description="Audit agent harness, prompt budgets, and efficiency.")
    parser.add_argument("--dir", default=str(BASE_DIR), help="Repository base directory.")
    args = parser.parse_args()

    base_path = Path(args.dir).resolve()
    agents_dir = base_path / "agents"

    print("=== Agent Harness Efficiency Audit ===")
    print(f"Inspecting directory: {base_path}\n")

    results = audit_prompts(agents_dir)
    has_warnings = False
    for r in results:
        if r["severity"] == "INFO":
            print(f"  • {r['file']:<20}: {r['chars']:>5} chars (~{r['tokens']:>4} tokens) [{r['status']}]")
        else:
            print(f"  [{r['severity']}] {r['file']}: {r['msg']}")
            has_warnings = True

    if sync:
        print("\n--- Provider Active Tree Token Summary ---")
        try:
            stats = sync.run_stats(base_path, quiet=True)
            for prov, pdata in stats.items():
                tree = pdata["total_active_tree"]
                print(f"  [{pdata['display_name']}]: {tree['files_count']} files, {tree['chars']:,} chars (~{tree['tokens']:,} tokens)")
        except Exception as e:
            print(f"  Could not compute stats: {e}")

    print("\nAudit complete.")
    sys.exit(1 if has_warnings else 0)


if __name__ == "__main__":
    main()
