---
name: verification-loop
description: Verify an implementation before completion with the smallest relevant checks, escalating to broader validation only when the changed risk requires it.
---

# Verification Loop

Use this skill after an implementation or repair when completion depends on demonstrated behavior.

1. Map each changed behavior to observable checks covering success, error, and boundary handling.
2. Verify assertion quality: ensure checks assert on meaningful invariants, fail cleanly on regressions, and reject false-success or swallowed-error paths.
3. Run the repository's focused verification first.
4. Inspect the failure before changing code; do not rerun an unchanged failing command.
5. Escalate to the configured full suite or build check only when cross-module or generated-output risk warrants it.
6. Report commands, outcomes, and any unverified risk in the completion contract.

Respect verifier ownership of broad validation. Do not invent unrelated checks, update snapshots without review, or claim success from partial output.
