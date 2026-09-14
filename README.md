# Autonomous Dev Team

A lightweight, multi-service multi-agent protocol and configuration engine for AI coding assistants (**Codex**, **Claude Code**, and **Gemini / Antigravity**).

Designed to eliminate interactive tool runaways, redundant verification loops, and context bloat through strict operational guardrails, tiered routing, and contract-oriented slicing.

---

## Key Features

1. **Single Source of Truth (`config.toml`)**:
   - Define project invariants (subsystems, forbidden paths, build/test commands) in one place.
   - Configure model names and reasoning/thinking effort for each agent across providers without editing 8 different `.toml` or `.md` files.
2. **Deterministic Compiler (`sync.py`)**:
   - Zero-dependency Python script that compiles `config.toml` and `agents/*.md` into native configurations:
     - `.codex/config.toml` + `.codex/agents/*.toml` for OpenAI Codex.
     - `CLAUDE.md` for Anthropic Claude Code.
     - `AGENTS.md` for Google Gemini / Antigravity.
   - Injects project safety invariants directly into agent system instructions to prevent hallucinations and build breaks.
3. **Core Operational Invariants**:
   - **Zero Full-History Forks (`fork_turns = "none"`)**: Dispatches subagents with compact contracts (≤ 1,500 tokens) instead of duplicating parent history.
   - **Anti-Polling**: Eliminates busy-polling loops in favor of reactive wakeups.
   - **Cohesive Slicing**: Bounded 1–3 contract seams; strictly forbids file-by-file micro-slicing.
   - **Circuit Breakers**: Hard tool call ceilings per role and an immediate 2-attempt failure breaker.
   - **Validate New Risk, Not Re-Run Proof**: Never re-runs passing unit tests in validator; validator runs only broad integration/build checks.

---

## Repository Structure

```text
.
├── config.toml                # Central config: [project] invariants + models/reasoning per provider
├── sync.py                    # Compiles config.toml + agents/*.md into native provider files
├── install.sh                 # Bootstrap script to install this protocol into any repository
├── AGENTS.md                  # Canonical protocol with compiled project guardrails
├── CLAUDE.md                  # Claude Code protocol with compiled project guardrails
├── .codex/                    # Generated Codex configurations
│   ├── config.toml
│   └── agents/*.toml
└── agents/                    # Specialist persona prompt templates
    ├── code-explorer.md       # Read-only scout; produces structured Discovery Manifests
    ├── planner.md             # Tier 3 contract-oriented slicer; enforces anti-micro-slicing
    ├── implementer.md         # Cohesive seam owner; verifies focused unit tests to green
    ├── quick-implementer.md   # Low-cost surgical implementer for small single-file edits
    ├── code-validator.md      # Independent runner for broad builds and integration tests
    ├── code-reviewer.md       # Senior reviewer for semantic risks (lifecycle, concurrency, security)
    └── commit-pusher.md       # Safe deterministic non-interactive Git publisher
```

---

## Quickstart: Installing into Another Project

To equip any project (e.g. `../my-app`) with this multi-agent setup:

```bash
./install.sh /path/to/my-app
```

Then inside your project:
1. Open `config.toml` and define your project's invariants:
   ```toml
   [project]
   name = "my-app"
   description = "Backend REST API in Node/Express"
   forbidden_paths = ["dist/**", "coverage/**"]
   build_sync_cmd = "npm run build"
   focused_test_cmd = "npm test -- {file}"
   full_test_cmd = "npm run test:integration"
   ```
2. Run `./sync.py` to compile the configurations into `.codex/`, `CLAUDE.md`, and `AGENTS.md`.

---

## Configuring Models & Reasoning

Change model versions, reasoning effort, or active providers in `config.toml`:

```toml
active_provider = "all"  # "all" | "codex" | "claude" | "gemini"

[codex.orchestrator]
model = "gpt-5.6-terra"
reasoning_effort = "low"

[codex.agents.implementer]
model = "gpt-5.6-sol"
reasoning_effort = "low"

[claude.orchestrator]
model = "claude-3-7-sonnet"
thinking = "low"

[claude.agents.implementer]
model = "claude-3-7-sonnet"
thinking = "medium"

[gemini.orchestrator]
model = "pro"

[gemini.agents.implementer]
model = "pro"
```

After modifying `config.toml`, execute:
```bash
./sync.py
```
All provider files are immediately updated in under a second.

---

## Adaptive Task Routing (Tiers 0–3)

Before executing any task, the `/root` Orchestrator classifies the request:

- **Tier 0 (Direct Operation)**: Deterministic tasks, inspecting Git status, running asset sync, checking small configs. Handled directly by `/root` without spawning subagents.
- **Tier 1 (Surgical Change)**: 1 file or localized edits, typos, simple helpers, isolated bug fixes. Assigned to `quick-implementer` with narrow verification.
- **Tier 2 (Cohesive Feature / Localized Bug)**: 1–3 tightly coupled files in a single subsystem. Assigned to `implementer` (owns cohesive seam + unit tests) and optional `code-reviewer`.
- **Tier 3 (Cross-Subsystem / Architectural Change)**: Multi-subsystem changes, state machine redesign, public API or boundary changes. Routed through `code-explorer` → `planner` (1–3 cohesive slices) → `implementer(s)` → `code-validator` → optional `code-reviewer`.

---

## License
MIT
