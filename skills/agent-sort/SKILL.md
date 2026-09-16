---
name: agent-sort
description: Choose the smallest suitable workflow tier, agent roles, and skills for a coding task when routing or context cost is unclear.
---

# Agent Sort

Use this skill when deciding how to route work, not while carrying out an already clear assignment. Optimize for first-pass correctness before token minimization.

1. Take a documented deterministic fast path before exploration when one exactly matches the request.
2. Use Tier 0 without delegates for inspection, configuration checks, and deterministic sync.
3. Use Tier 1 directly only for a known-location change of at most one implementation file plus one related test or configuration file, with no architectural, concurrency, lifecycle, security, or public-contract risk and with focused verification available. Otherwise use one quick implementer.
4. Use Tier 2 with one primary specialist and only the validation or review gates justified by changed risk. Avoid duplicate review of the same risk, but retain separate gates for distinct risks.
5. Keep Tier 3 discovery, planning, cohesive implementation slices, and independent integration validation.
6. Dispatch compact verified facts rather than conversation history. Preserve one transient delegation retry and at most two evidence-backed repair cycles.

At 8 direct tool calls, reassess the approach; at 12, replan or explain why more work is required. These checkpoints govern work performed, not provider billing, and never justify skipping required verification or reporting false success. Skills guide the active agent and do not themselves authorize subagents.
