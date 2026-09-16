---
name: agent-sort
description: Choose the smallest suitable workflow tier, agent roles, and skills for a coding task when routing or context cost is unclear.
---

# Agent Sort

Use this skill when deciding how to route work, not while carrying out an already clear assignment.

1. Classify the task using the repository's Tier 0–3 routing rules.
2. Select only roles with distinct ownership and only skills directly relevant to the task.
3. Keep direct inspection and deterministic sync with the root agent.
4. Use one cohesive implementer for related changes; add validation or review only for new risk.
5. Dispatch compact verified facts rather than conversation history.

Skills guide the active agent and do not themselves authorize subagents. Never spawn roles merely to fill a roster or duplicate another role's work.
