---
name: verification-loop
description: Verify an implementation before completion with the smallest relevant checks, escalating to broader validation only when the changed risk requires it.
---

# Verification Loop

Use this skill after an implementation or repair when completion depends on demonstrated behavior.

1. Map each requested behavior to one observable check.
2. Run the repository's focused verification first.
3. Inspect the failure before changing code; do not rerun an unchanged failing command.
4. Escalate to the configured full suite or build check only when cross-module or generated-output risk warrants it.
5. Report commands, outcomes, and any unverified risk in the completion contract.

Respect validator ownership of broad validation. Do not invent unrelated checks, update snapshots without review, or claim success from partial output.
