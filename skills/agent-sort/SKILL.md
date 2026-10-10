---
name: agent-sort
description: Choose the smallest suitable workflow tier, agent roles, and skills for a coding task when routing or context cost is unclear.
---

# Agent Sort

Use this skill when deciding how to route work, not while carrying out an already clear assignment. Optimize for first-pass correctness before token minimization.

1. Take a documented deterministic fast path before exploration when one exactly matches the request.
2. Use Tier 0 without delegates for direct inspection, configuration checks, and deterministic sync.
3. Use Tier 1 directly only for localized surgical edits (touching ≤3 files, modifying ≤150 lines, introducing no public-interface, dependency, migration, or security path changes, and with focused verification passing).
4. Use Tier 2 (`implementer` -> `verifier`) for cohesive features or bugfixes, with root-cause diagnosis handled by `implementer`. Retain separate gates for distinct risks.
5. Use Tier 3 (`architect` -> `implementer` -> `verifier`) for multi-subsystem, architectural overhaul, or complex planning.
6. Dispatch compact verified facts rather than conversation history. Preserve one transient delegation retry, reuse the original implementer for at most two evidence-backed repair cycles, and count every repair across agents and reasoning steps toward the configured total repair limit.
7. Follow configured `adaptive_steps` one effective step at a time, including same-model effort changes, only on evidence of a reasoning blocker; use exceptional steps only with prior-step evidence, and reset unrelated slices.

At 8 direct tool calls, reassess the approach; at 12, replan or explain why more work is required. These checkpoints govern work performed, not provider billing, and never justify skipping required verification or reporting false success. Skills guide the active agent and do not themselves authorize subagents.
