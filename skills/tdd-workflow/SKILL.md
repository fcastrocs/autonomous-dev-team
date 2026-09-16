---
name: tdd-workflow
description: Apply a focused red-green-refactor cycle for reproducible bugs or behavior changes when an automated test can express the requirement.
---

# TDD Workflow

Use this skill when a requested behavior or reproduced defect has a stable automated test boundary.

1. Locate the closest existing test convention and choose the smallest test level that proves the behavior.
2. Add or adjust one focused test and confirm it fails for the intended reason.
3. Implement the minimum cohesive change that makes the test pass.
4. Refactor only after green, preserving the same behavioral assertion.
5. Run the configured focused verification and hand broader risk to the validator when required.

Do not force TDD onto documentation-only, mechanical configuration, generated output, or behavior that cannot be tested reliably. Never weaken an assertion merely to obtain green.
