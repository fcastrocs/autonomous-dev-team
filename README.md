# Autonomous Dev Team

Autonomous Dev Team adds a practical multi-agent workflow to Codex, Claude Code, and Google Antigravity.

## Dev Team Roster

Autonomous Dev Team organizes specialized agents into a cohesive engineering team coordinated by the orchestrator:

| Role | Agent | Responsibilities |
|---|---|---|
| **Orchestrator** | `/root` | Interprets intent, selects workflow tiers, routes tasks, and synthesizes final completion. |
| **Code Explorer** | `code-explorer` | Gathers targeted facts, traces symbols, and maps call flows without making edits. |
| **Planner** | `planner` | Deconstructs complex work into 1–3 cohesive implementation slices with clear invariants. |
| **Quick Implementer** | `quick-implementer` | Fast, surgical, single-file edits and low-risk fixes verified by focused unit tests. |
| **Implementer** | `implementer` | End-to-end features and multi-file fixes; owns code correctness and focused unit tests. |
| **Diagnostician** | `diagnostician` | Investigates unknown bugs, identifies root causes, and proves reproduction paths. |
| **Code Validator** | `code-validator` | Independently verifies full test suites, packaging, builds, and regression risks. |
| **Code Reviewer** | `code-reviewer` | Inspects semantic risks, architecture alignment, safety, and guardrail enforcement. |
| **Commit Pusher** | `commit-pusher` | Manages Git operations, atomic commits, staging, and branch pushing safely. |

> **Roster Inspection:** Run `python3 .autonomous-dev-team/sync.py --team` (or type `/team` during an active chat session) to view the active provider's roster and assigned model reasoning tiers.

## Requirements

- **Python 3.11+** (standard library only; no external package dependencies required)
- At least one supported AI coding assistant CLI:
  - [OpenAI Codex](https://github.com/openai/codex)
  - [Anthropic Claude Code](https://github.com/anthropics/claude-code)
  - [Google Antigravity](https://github.com/google-deepmind) (`agy`)

## Installation

### Remote Installation (Published Release)

Run the installer from the root of the repository you want to set up:

**Linux / macOS:**
```bash
curl -fsSL https://github.com/fcastrocs/autonomous-dev-team/releases/latest/download/install.py | python3 -
```

**Windows (PowerShell):**
```powershell
curl.exe -fsSL https://github.com/fcastrocs/autonomous-dev-team/releases/latest/download/install.py | python -
```

### Installation Options

Pass options directly after the command:

```bash
# Install for a specific provider
curl -fsSL https://github.com/fcastrocs/autonomous-dev-team/releases/latest/download/install.py | python3 - --provider codex

# Overwrite existing managed source files
curl -fsSL https://github.com/fcastrocs/autonomous-dev-team/releases/latest/download/install.py | python3 - --force
```

| Option | Values | Default | Description |
|---|---|---|---|
| `--provider` | `all`, `codex`, `claude`, `antigravity`, `agy` | `all` | Target AI provider configuration |
| `--force` | _flag_ | `false` | Replace existing managed source files |
| `-h`, `--help` | _flag_ | | Show usage instructions and options |

> **Installation Behavior:**
> - Fresh installations copy managed sources (`.autonomous-dev-team/sync.py`, `.autonomous-dev-team/agents/*`, `.autonomous-dev-team/skills/*`) into `.autonomous-dev-team/` while preserving existing project files.
> - If any managed source already exists, installation stops without replacing it. Use `--force` to explicitly update them.
> - Authentication is provider-owned; authenticate with your provider CLI before use.

### Local Installation (Development Checkout)

To install from a local checkout into a target repository:

```bash
# Run from within the target repository:
python3 /path/to/autonomous-dev-team/install.py

# Or specify the target path directly:
python3 install.py /path/to/target-project

# To update an existing installation explicitly:
python3 install.py --force /path/to/target-project
```

## Set Up Your Project

1. **Configure Your Project**:
   Installation generates `.autonomous-dev-team/config.toml` in your repository. This is the **only file you should configure or edit**. Use it to define test commands, build commands, provider models, and guardrails.

2. **Regenerate Provider Files**:
   ```bash
   python3 .autonomous-dev-team/sync.py
   ```

3. **Verify Configuration Sync**:
   ```bash
   python3 .autonomous-dev-team/sync.py --check
   ```

4. **Inspect Roster & Sync Status**:
   ```bash
   python3 .autonomous-dev-team/sync.py --team
   ```
   You can also type `/team` during an active agent session (Codex, Claude Code, or Antigravity) to inspect loaded team roles and reasoning tiers.

> Re-run `python3 .autonomous-dev-team/sync.py` whenever you modify `.autonomous-dev-team/config.toml`.

## Generated Files

Depending on the selected provider, the compiler generates:

| Provider | Generated Artifacts |
|---|---|
| **Codex** | `.codex/config.toml`, `.codex/agents/*.toml`, `.codex/prompts/team.md` |
| **Claude Code** | `CLAUDE.md`, `.claude/agents/*.md`, `.claude/skills/team/*` |
| **Google Antigravity** | `AGENTS.md`, `.agents/skills/team/*` |

The compiler also tracks managed files in `.autonomous-dev-team/manifest.json` for clean pruning and synchronization. `.autonomous-dev-team/config.toml` is the sole source of truth. Role instructions in `.autonomous-dev-team/agents/` and generated provider files should never be edited by hand.

## How the Workflow Works

The root agent selects the smallest safe workflow tier for each task:

- **Tier 0 (Direct)**: Inspection, configuration checks, and deterministic sync run directly.
- **Tier 1 (Surgical)**: Local, low-risk changes route to `quick-implementer`.
- **Tier 2 (Feature / Fix)**: Cohesive features go to `implementer`; unknown-cause failures route first to `diagnostician`. Independent verification is owned by `code-validator`.
- **Tier 3 (Architecture)**: `code-explorer` inspects, `planner` defines cohesive slices, implementers execute, and `code-validator` validates.

Context duplication is strictly minimized, polling loops are avoided, and verification remains proportional to risk.

## Configuration Example

Select active providers and models in `.autonomous-dev-team/config.toml`:

```toml
active_provider = "codex"

[codex.orchestrator]
model = "gpt-5.6-terra"
reasoning_effort = "low"
```

After modifying `.autonomous-dev-team/config.toml`, run `python3 .autonomous-dev-team/sync.py`.

## Developing this Repository

Using `make` (run `make help` for all targets) or standard Python commands:

- **Run focused unit tests**:
  ```bash
  make test
  # or: python3 -m unittest tests/test_sync.py
  ```
- **Run the full test discovery suite**:
  ```bash
  make test-all
  # or: python3 -m unittest discover tests
  ```
- **Check configuration sync**:
  ```bash
  make check
  # or: python3 sync.py --check
  ```
- **Inspect active roster & sync status**:
  ```bash
  make team
  # or: python3 sync.py --team
  ```
- **Synchronize provider configurations**:
  ```bash
  make sync
  # or: python3 sync.py
  ```
- **Publish a release** (GitHub CLI authentication required):
  ```bash
  ./release.sh
  # or with an explicit version:
  ./release.sh v0.0.1
  # or via make:
  make release [VERSION=v0.0.1]
  ```
  Requires a clean checkout, runs test and sync verification, starts at `v0.0.1` (or increments the latest patch version `v0.0.2`, `v0.0.3`, etc.), archives repository sources, injects pinned defaults into `install.py`, and publishes a GitHub release.

## License

MIT
