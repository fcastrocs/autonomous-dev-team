# Autonomous Multi-Agent Protocol — {PROJECT_NAME}

**Charter:** `/root` owns intent interpretation, tier selection, routing, cohesive slicing, synthesis, and completion for {PROJECT_DESCRIPTION}.

## Repository guardrails

{PROJECT_GUARDRAILS}

- Keep disjoint subsystems in separate implementation slices.
- Use deterministic build synchronization: `{BUILD_SYNC_CMD}`.
- **Configuration Invariant**: `.autonomous-dev-team.toml` is the sole source of truth for all provider models, reasoning tiers, token limits, and agent settings. Never modify `sync.py` to hardcode, patch, or inject model configurations or provider-specific settings.
- Never use interactive Git commands.
- Limit file reads to 60 lines, diffs to `git diff -U3`, and broad output to the last 25 lines.
- Dispatch compact context only; wait reactively rather than busy-polling.

## Adaptive routing

- **Tier 0:** Direct inspection, configuration checks, or deterministic sync is handled by `/root`.
- **Tier 1:** A surgical, low-risk edit goes to `quick-implementer`, followed by `{FOCUSED_TEST_CMD}`.
- **Tier 2:** A cohesive feature or known-cause bug goes to `implementer`; an unknown-cause failure goes first to `diagnostician`. After focused tests pass, `code-validator` validates only broader new risk with `{FULL_TEST_CMD}` or `{BUILD_CMD}`. Use `code-reviewer` only for semantic risk.
- **Tier 3:** `code-explorer` produces targeted facts, `planner` defines one to three cohesive slices, implementers own those slices, and `code-validator` performs broad integration/build checks. Add review only for semantic risk.

Detailed role rules live in `agents/<role>.md`; model routing lives only in `.autonomous-dev-team.toml`.

## Contracts

Every dispatch states goal, why, scope, symbols, verified facts, constraints, required behavior, exact verification, and explicit non-goals. Discovery reports root cause, relevant files, execution flow, verified facts, uncertainties, ownership boundary, and verification. Completion reports status, changed files, behavior, verification, remaining risk, and follow-up.

When validation or review fails, send the original implementer a repair packet containing the exact command, exit code/error excerpt, changed files, and known-good facts. Reuse that implementer for at most two repair cycles. If the same issue still fails, stop and report the blocker or replan; never loop indefinitely.


