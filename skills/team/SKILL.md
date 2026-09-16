---
name: team
description: Inspect the active provider configuration, setup sync status, and dev team roster.
---

# Dev Team Status

Inspect the active provider configuration, setup sync status, and dev team roster.

Run exactly one inspection command, choosing the first path that exists:

1. Installed project: `python3 .autonomous-dev-team/sync.py --team`
2. This source repository: `python3 sync.py --team`

Do not run the project's build command, search the repository, inspect agent files, or schedule a wait before executing the inspection command. The command is synchronous; report its output when it exits.

## Presentation Instructions

When reporting the results:
1. Always display the full status section from the command output:
   - **Configuration File**
   - **Active Provider**
   - **Setup Sync Status**
2. Present the dev team roster as a markdown table with columns:
   - `Role`
   - `Agent`
   - `Model`
   - `Reasoning Effort`
3. Designate `/root` as `Orchestrator` and all other team members as `Agent`. Never use "Specialist".
4. Do NOT summarize, abbreviate, or omit roles from the roster. Always include every configured team role in the table.
