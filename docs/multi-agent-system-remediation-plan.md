# Autonomous Dev Team — Multi-Agent System Remediation Plan

**Target Providers:** Google Antigravity (`agy`), OpenAI Codex, Anthropic Claude Code  
**Repositories Involved:** `autonomous-dev-team`, target projects (e.g. `IPTV`)  
**Date:** 2026-09-18  

---

## 1. Context & Forensic Findings Summary

During recent real-world sessions in [IPTV](file:///Users/machiagod/repos/IPTV):
1. **Google Antigravity Session (`59dd4fd2`):**
   - The user requested `/plan` with strict instructions: `YOU ARE NOT ALLOWED TO MODIFY ANY SOURCE FILE OR IMPLEMENT THE PLAN WITHOUT EXPLICIT APPROVAL FROM ME.`
   - Antigravity never used `autonomous-dev-team` roles (`code-explorer`, `planner`, `implementer`, `code-validator`).
   - The agent performed 378 tool calls directly as `/root`.
   - At Step 247, the model attempted to halt and wait for user approval, but because the CLI was run with `--dangerously-skip-permissions`, the Stop Hook auto-approved the artifact and injected: `Stop hook blocked termination: The user has automatically approved the artifact through their review policy. Proceed to execution.`, causing a runaway single-agent execution.
2. **OpenAI Codex Session (`01a0b56f`):**
   - The user requested `$team`, interactive planning for rewriting `playlist-builder` to Python, and implementation (`approved, implement.`).
   - Codex never spawned subagents (0 calls to `spawn_agent`, empty `thread_spawn_edges`).
   - Codex platform injected: `<multi_agent_mode>Any earlier instruction enabling proactive multi-agent delegation no longer applies. Do not spawn sub-agents unless the user or applicable AGENTS.md/skill instructions explicitly ask for sub-agents, delegation, or parallel agent work.</multi_agent_mode>`.
   - The fast-path roster check `python3 .autonomous-dev-team/sync.py --team` crashed with `ModuleNotFoundError: No module named 'tomllib'` because macOS default `python3` is Python 3.9.6.

---

## 2. Root Cause Analysis Matrix

| Provider | Root Cause | Impact |
| :--- | :--- | :--- |
| **Antigravity (`agy`)** | Missing native subagent compilation in `sync.py` | `sync.py` generated `AGENTS.md` and `.agents/skills/*`, but **no custom agents in `.agents/agents/<role>/agent.md`**. Antigravity only exposed built-in `self` and `research`. |
| **Antigravity (`agy`)** | Broken persona paths in installed target | `AGENTS.md` told `/root` to dispatch `self` with `agents/<role>.md`, but installed targets store internal sources in `.autonomous-dev-team/_internal/agents/`. |
| **Antigravity (`agy`)** | Stop Hook auto-approval with `--dangerously-skip-permissions` | Runtime auto-approved planning artifact and commanded immediate execution (`Proceed to execution`), overriding the user's explicit instruction not to edit files. |
| **Codex** | Platform `<multi_agent_mode>` directive suppression | Codex requires explicit trigger phrasing (*"explicitly ask for sub-agents, delegation, or parallel agent work"*). The general tier descriptions in `.codex/config.toml` did not trigger spawning. |
| **Codex / macOS** | System Python 3.9 crash on `tomllib` | macOS `/usr/bin/python3` is 3.9.6. `sync.py` imported `tomllib` unconditionally at line 36 without a version guard or Python 3.11 detection, breaking `$team`. |
| **Both** | Lack of strict negative constraints on `/root` | Orchestrator protocol stated tool limits were "checkpoints, not forced completion limits." Once planning ended, single-agent bias led `/root` to perform all code edits directly. |

---

## 3. Comprehensive Remediation Plan

### Workstream 1: Native Antigravity Subagent Generation in `sync.py`
Antigravity discovers custom Markdown subagents located at `.agents/agents/<agent_name>/agent.md` with YAML frontmatter.

**Changes in [sync.py](file:///Users/machiagod/repos/autonomous-dev-team/sync.py):**
1. Add `compile_antigravity_agents(config, project, guardrails_block, base_dir)`:
   For every configured agent in `.autonomous-dev-team.toml`:
   - Generate `.agents/agents/<role>/agent.md`:
     ```markdown
     ---
     name: {role_name}
     description: {role_description}
     subagent: true
     mainAgent: false
     ---

     # {role_name} Persona
     {role_system_prompt_interpolated}
     ```
2. Track `.agents/agents/**` in `manifest.json` for proper sync, pruning, and `--check`.
3. In `AGENTS.md` dispatch syntax, direct Antigravity to invoke subagents by their registered names:
   ```markdown
   ## Antigravity Dispatch Syntax
   Invoke the designated subagent directly via `invoke_subagent` using its registered name:
   - `code-explorer` (Model: `flash`)
   - `planner` (Model: `flash`)
   - `quick-implementer` (Model: `flash`)
   - `implementer` (Model: `flash`)
   - `diagnostician` (Model: `flash`)
   - `code-validator` (Model: `flash`)
   - `code-reviewer` (Model: `flash`)
   ```

---

### Workstream 2: Codex Platform Directive Trigger in `config.toml`
Codex's platform actively blocks subagent spawning unless instructions explicitly demand it.

**Changes in [sync.py](file:///Users/machiagod/repos/autonomous-dev-team/sync.py) (`compile_codex`):**
In `.codex/config.toml`'s `developer_instructions`:
Insert an explicit, non-negotiable instruction containing the exact phrasing required by Codex's `<multi_agent_mode>` filter:
```markdown
# Codex delegation adapter
MANDATORY MULTI-AGENT INSTRUCTION:
The user and repository protocol explicitly ask for sub-agents, delegation, and parallel agent work for all non-trivial tasks.
- For Tier 2 (features/fixes) and Tier 3 (architecture/refactors/plans), /root MUST call `spawn_agent` to delegate work to the designated specialist (`code-explorer`, `planner`, `implementer`, `code-validator`).
- /root is strictly an orchestrator and MUST NOT directly write multi-file implementation code or author tests.
- Use `spawn_agent` with `fork_turns = "none"` and pass only the Compact Dispatch Contract.
```

---

### Workstream 3: Python 3.11+ Interpreter Guard & Fallback in `sync.py`
Prevent `ModuleNotFoundError: No module named 'tomllib'` on systems where `python3` defaults to Python 3.9 (e.g. macOS).

**Changes in [sync.py](file:///Users/machiagod/repos/autonomous-dev-team/sync.py):**
1. At the very top of `sync.py` (before `import tomllib`):
   ```python
   import sys
   if sys.version_info < (3, 11):
       # Attempt auto-reexec with python3.11 if present on PATH or common macOS locations
       import shutil, subprocess
       py311 = shutil.which("python3.11") or "/Users/machiagod/.local/bin/python3.11"
       if py311 and py311 != sys.executable:
           sys.exit(subprocess.call([py311] + sys.argv))
       sys.stderr.write(
           f"Error: Python 3.11+ is required (found Python {sys.version_info.major}.{sys.version_info.minor}).\n"
           f"Please run using 'python3.11' or activate a Python 3.11 virtual environment.\n"
       )
       sys.exit(1)
   ```
2. Update [skills/team/SKILL.md](file:///Users/machiagod/repos/autonomous-dev-team/skills/team/SKILL.md) and [agents/orchestrator.md](file:///Users/machiagod/repos/autonomous-dev-team/agents/orchestrator.md):
   Allow invoking with `python3.11 .autonomous-dev-team/sync.py --team` or `python3` with interpreter resolution.

---

### Workstream 4: Correct Persona Paths for Installed Targets
Eliminate references to non-existent `agents/<role>.md` in installed client repositories.

**Changes in [sync.py](file:///Users/machiagod/repos/autonomous-dev-team/sync.py):**
- In installed projects (where `ENCAPSULATED_DIR_NAME` is used):
  - In `AGENTS.md`: Reference `.agents/agents/<role>/agent.md` or `.autonomous-dev-team/_internal/agents/<role>.md`.
  - In `.codex/config.toml`: Reference `.codex/agents/<role>.toml` or `.autonomous-dev-team/_internal/agents/<role>.md`.
  - In source repository checkout: Fall back to `agents/<role>.md`.

---

### Workstream 5: Hard Negative Invariants in `agents/orchestrator.md`
Prevent single-agent bias across all providers by converting soft advisory routing into strict behavioral invariants.

**Changes in [agents/orchestrator.md](file:///Users/machiagod/repos/autonomous-dev-team/agents/orchestrator.md):**
Add a dedicated **Strict Orchestration Invariants** section:
```markdown
## Strict Orchestration Invariants

1. `/root` is strictly an orchestrator and synthesizer.
2. `/root` is FORBIDDEN from directly modifying source code, editing implementation files, or writing tests for any Tier 2 or Tier 3 task.
3. `/root` is FORBIDDEN from executing implementation directly when a task touches more than one file or introduces behavioral risk.
4. When `/plan` or an architectural task is received:
   - `/root` MUST delegate fact-gathering and codebase exploration to `code-explorer`.
   - `/root` MUST delegate plan formulation and slice breakdown to `planner`.
5. When execution is approved:
   - `/root` MUST dispatch implementation slices to `implementer` (or `quick-implementer` for single-file surgical changes).
   - `/root` MUST dispatch verification to `code-validator`.
6. Slash commands (`/plan`, `/goal`), plan modes, and auto-approval messages NEVER waive these invariants.
```

---

### Workstream 6: Runtime Review Policy Guidance
1. When planning non-trivial migrations in Antigravity, avoid `--dangerously-skip-permissions` if human-in-the-loop plan review is desired.
2. If running non-interactively or with permissions skipped, the agent's prompt must explicitly recognize that auto-approval is authorization for the *multi-agent pipeline to begin execution*, **not** for `/root` to bypass subagents and execute everything itself.

---

## 4. Implementation Steps & Verification Strategy

### Step 1: Update `sync.py` & `agents/orchestrator.md` in `autonomous-dev-team`
- Implement Python 3.11 guard and re-exec logic at top of [sync.py](file:///Users/machiagod/repos/autonomous-dev-team/sync.py).
- Add `compile_antigravity_agents()` to generate `.agents/agents/<role>/agent.md`.
- Update `compile_codex()` to include the mandatory subagent directive.
- Update [agents/orchestrator.md](file:///Users/machiagod/repos/autonomous-dev-team/agents/orchestrator.md) with hard orchestration invariants and correct persona paths.

### Step 2: Unit Testing in `autonomous-dev-team`
- Run `pytest tests/test_sync.py` to ensure compiler correctness, schema validation, and manifest tracking.
- Add test assertions verifying:
  - Antigravity generates `.agents/agents/<role>/agent.md` for all configured agents.
  - Codex developer instructions include the mandatory trigger statement.
  - Python version guard rejects or handles Python < 3.11.

### Step 3: Deploy & Sync in `IPTV`
- Run `python3.11 sync.py` to compile the changes in `autonomous-dev-team`.
- Run `python3.11 install.py --force /Users/machiagod/repos/IPTV` to update the installed files in IPTV.
- Verify in IPTV:
  - `ls /Users/machiagod/repos/IPTV/.agents/agents/` shows all 14 roles with valid `agent.md` files.
  - `python3 .autonomous-dev-team/sync.py --team` completes successfully with exit code 0.
  - `python3.11 .autonomous-dev-team/sync.py --check` passes cleanly.
