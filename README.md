# Autonomous Dev Team

A lightweight, multi-service multi-agent protocol and configuration engine for AI coding assistants (**Codex**, **Claude Code**, and **Gemini / Antigravity**).

Designed to eliminate interactive tool runaways, redundant verification loops, and context bloat through strict operational guardrails, tiered routing, and contract-oriented slicing.

---

## Key Features

1. **Zero-Friction Bootstrap & Stack Auto-Detection**:
   - Automatically detects your project's ecosystem (**Node.js**, **Python**, **Rust**, **Go**) and creates a tailored `.autonomous-dev-team.toml` with real build commands, test selectors, and forbidden paths.
   - Install into any project in 5 seconds with a single command.
2. **Single Source of Truth (`.autonomous-dev-team.toml`)**:
   - Define project invariants (subsystems, forbidden paths, build/test commands) in one place.
   - Configure model names and reasoning/thinking effort for each agent across providers without editing 8 different `.toml` or `.md` files.
3. **Deterministic Compiler (`sync.py`)**:
   - Zero-dependency Python script that compiles `.autonomous-dev-team.toml` and `agents/*.md` into native configurations:
     - `.codex/config.toml` + `.codex/agents/*.toml` for OpenAI Codex.
     - `CLAUDE.md` for Anthropic Claude Code.
     - `AGENTS.md` and `GEMINI.md` for Google Gemini / Antigravity.
   - Injects project safety invariants and 4-tier routing instructions directly into orchestrator and agent instructions.
   - Built-in `--check` flag for CI and pre-commit validation.
4. **Core Operational Invariants**:
   - **Zero Full-History Forks (`fork_turns = "none"`)**: Dispatches subagents with compact contracts (≤ 1,500 tokens) instead of duplicating parent history.
   - **Anti-Polling**: Eliminates busy-polling loops in favor of reactive wakeups.
   - **Cohesive Slicing**: Bounded 1–3 contract seams; strictly forbids file-by-file micro-slicing.
   - **Circuit Breakers**: Hard tool call ceilings per role and an immediate 2-attempt failure breaker.
   - **Validate New Risk, Not Re-Run Proof**: Never re-runs passing unit tests in validator; validator runs only broad integration/build checks.

---

## Repository Structure

```text
.
├── .autonomous-dev-team.toml # Central config: project invariants + provider models
├── sync.py                    # Compiles config.toml + agents/*.md into native provider files
├── install.sh                 # Bootstrap script to install this protocol into any repository
├── AGENTS.md                  # Antigravity protocol with compiled project guardrails
├── GEMINI.md                  # Gemini assistant rules mirror
├── CLAUDE.md                  # Claude Code protocol with compiled project guardrails
├── .codex/                    # Generated Codex configurations
│   ├── config.toml            # Root orchestrator developer instructions & agent registry
│   └── agents/*.toml          # Specialist agent configurations with compiled instructions
├── agents/                    # Specialist persona prompt templates
│   ├── code-explorer.md       # Read-only scout; produces structured Discovery Manifests
│   ├── planner.md             # Tier 3 contract-oriented slicer; enforces anti-micro-slicing
│   ├── implementer.md         # Cohesive seam owner; verifies focused unit tests to green
│   ├── quick-implementer.md   # Low-cost surgical implementer for small single-file edits
│   ├── code-validator.md      # Independent runner for broad builds and integration tests
│   ├── code-reviewer.md       # Senior reviewer for semantic risks (lifecycle, concurrency, security)
│   └── commit-pusher.md       # Safe deterministic non-interactive Git publisher
└── tests/
    └── test_sync.py           # Unit tests verifying compiler and stack detection
```

---

## Quickstart: Installing into Any Project

The canonical remote command is shown as a release template until this project publishes an installer URL and checksum; replace all three release values with those from the same published release:

```bash
curl -fsSL https://github.com/OWNER/autonomous-dev-team/releases/download/VERSION/install.sh | bash -s -- --version VERSION --archive-url https://github.com/OWNER/autonomous-dev-team/archive/refs/tags/VERSION.tar.gz --sha256 RELEASE_SHA256 /path/to/my-app
```

The version must appear in the HTTPS archive URL, and its SHA-256 is verified before extraction. The installer creates a missing target (including paths with spaces), stages one coherent `sync.py` + `agents/` payload, initializes zero-required-config defaults, compiles the requested providers, and runs `--check`. Reruns preserve `.autonomous-dev-team.toml` and unrelated files. It never interprets a project's ordinary `config.toml` as protocol configuration unless it carries the legacy protocol schema.

For development from a local checkout (no network):

```bash
./install.sh --provider all "/path/to/my app"
```

Provider authentication is a prerequisite and remains owned by each provider CLI. Use `--provider codex`, `claude`, `gemini`, `antigravity` (alias `agy`), or `all`. After installation, edit `.autonomous-dev-team.toml`, run `./sync.py`, and use `./sync.py --check` in CI.

---

## Provider Compatibility Details

### 1. OpenAI Codex
- **Root Orchestrator**: Configured in `.codex/config.toml` with `developer_instructions` covering token limits, project guardrails, Tier 0–3 routing, and dispatch contracts.
- **Subagents**: Generated in `.codex/agents/*.toml` with individual models, reasoning levels, and compiled instructions.

### 2. Anthropic Claude Code
- **Artifacts**: `CLAUDE.md` plus `.claude/agents/*.md` specialist definitions.
- **Limitation**: The protocol supplies instructions and personas; tool availability and subagent execution are controlled by the installed Claude Code version.
- **Communication Contracts**: Discovery Manifest, Compact Dispatch Contract, and Completion Contract formats are embedded for structured output.

### 3. Google Gemini
- **Artifacts**: `GEMINI.md` and `.gemini/settings.json`.
- **Limitation**: The settings select the context filename; supported tools and delegation remain Gemini CLI capabilities.

### 4. Antigravity (`agy` alias)
- **Artifact**: `AGENTS.md` with a conservative provider-native dispatch contract.
- **Limitation**: Agent invocation is guidance, not an authentication or tool installer.
- **Antigravity Subagent Dispatch Protocol**:
  ```python
  invoke_subagent(
      TypeName="self",         # or "research" for read-only exploration
      Role="code-explorer",    # specialist role name
      Model="flash",           # "flash" for scouts/validators, "pro" for implementer/planner
      Prompt="<Compact Dispatch Contract + agents/<role>.md>"
  )
  ```

---

## Configuring Models & Reasoning

Change model versions, reasoning effort, or active providers in `.autonomous-dev-team.toml`:

```toml
active_provider = "all"  # also: "codex", "claude", "gemini", "antigravity" / "agy"

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

After modifying `.autonomous-dev-team.toml`, execute:
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
