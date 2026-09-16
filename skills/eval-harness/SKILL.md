---
name: eval-harness
description: Design focused evaluations for agent prompts, routing, protocol, or harness changes using repeatable scenarios and measurable pass criteria.
---

# Evaluation Harness

Use this skill for changes to agents, skills, routing, protocol, or orchestration where examples alone cannot establish quality.

1. Define representative scenarios, expected decisions, forbidden outcomes, and measurable pass criteria before comparing results.
2. Include normal, boundary, and failure cases that exercise the changed contract.
3. Prefer deterministic checks for structure and behavior; reserve model judgment for genuinely semantic criteria.
4. Compare candidate and baseline on correctness, latency, token use, and unnecessary delegation when data is available.
5. Report regressions and uncertainty rather than averaging away critical failures.

Keep the evaluation bounded and reproducible. Do not make it a mandatory gate for unrelated code changes or tune against hidden test details.
