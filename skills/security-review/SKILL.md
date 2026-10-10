---
name: security-review
description: Perform focused security reasoning for changes involving trust boundaries, authorization, secrets, untrusted input, command execution, paths, or network access.
---

# Security Review

Use this skill when a task introduces or changes a security-sensitive boundary.

1. Identify assets, entry points, trust boundaries, and attacker-controlled data in the changed scope.
2. Trace authentication, authorization, validation, escaping, secret handling, filesystem access, subprocesses, and outbound requests as applicable.
3. Report only evidence-backed findings as priority (P0–P3), location, impact, exploit conditions, and a concrete mitigation, in the verifier's Findings format. Never quote a secret's value; cite its type and location.
4. Distinguish confirmed vulnerabilities from hardening suggestions and unknowns.
5. Verify a requested fix with a focused regression check when permitted.

Keep review read-only unless implementation was requested. This skill guides security work; it does not expand access.
