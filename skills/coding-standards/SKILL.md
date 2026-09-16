---
name: coding-standards
description: Apply repository-local coding conventions when implementing or reviewing code and no narrower language or framework standard already governs the change.
---

# Coding Standards

Use this skill as a lightweight fallback for implementation quality, after inspecting nearby code and repository instructions.

1. Follow local naming, layout, typing, error-handling, and testing patterns.
2. Keep the diff minimal and preserve public behavior unless the assignment changes it.
3. Prefer clear control flow and explicit failure handling over clever abstractions or silent fallbacks.
4. Remove only duplication introduced or directly exposed by the change.
5. Document non-obvious constraints, not code that is already self-explanatory.

Repository instructions and established conventions take precedence. Do not perform speculative cleanup, mass formatting, dependency changes, or unrelated refactors.
