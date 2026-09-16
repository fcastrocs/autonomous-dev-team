---
name: team
description: Inspect provider and roster status by running sync.py --team directly; never forward --team to a build or package command.
---

# Dev Team Status

Inspect the active provider configuration, setup sync status, and dev team roster.

`--team` is an argument to this project's `sync.py`, not a generic build flag. Run exactly one of these literal commands based on the already-known repository layout:

1. Installed project: `python3 .autonomous-dev-team/sync.py --team`
2. This source repository: `python3 sync.py --team`

Do not probe for files first. Never append or forward `--team` to `npm`, `npx`, Gradle, Make, a package script, the configured build command, or any other wrapper; `npm run build --team` is invalid. Do not build, search, inspect agent files, delegate, or schedule a wait before executing the inspection command.

The inspection command is synchronous. Report its output when it exits. If it fails, report that exact command, exit status, and error output without running a fallback or diagnostic command.

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
