---
name: agent-introspection-debugging
description: Diagnose repeated agent failures, tool loops, contradictory state, or stalled multi-agent execution by inspecting evidence before retrying.
---

# Agent Introspection Debugging

Use this skill when an agent repeats a failed action, reports state that conflicts with the workspace, or stops making measurable progress.

1. Capture the exact failing command, exit status, relevant output, and current repository state.
2. Separate verified facts from assumptions and list at most three plausible causes.
3. Run the smallest read-only check that distinguishes those causes.
4. Repair through the existing routing contract. Send failures back to the original implementer with the command, error excerpt, changed files, and known-good facts.
5. Stop after the repository's bounded repair cycles. Report the blocker instead of retrying blindly.

Do not broaden permissions, inspect secrets, mutate unrelated files, or replace the diagnostician for an unknown-cause code failure.
