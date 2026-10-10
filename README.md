# Autonomous Dev Team

Autonomous Dev Team adds a practical multi-agent workflow to Codex, Claude Code, and Google Antigravity.

## Dev Team Roster

Autonomous Dev Team organizes specialized agents into a cohesive engineering team coordinated by the orchestrator:

| Role | Agent | Responsibilities |
|---|---|---|
| **Orchestrator** | `/root` | Interprets intent, selects workflow tiers, routes tasks, and synthesizes final completion. |
| **Architect** | `architect` | Read-only discovery and 1–3 slice contract planning; traces symbols and failure paths. |
| **Implementer** | `implementer` | Surgical changes, multi-file features, and refactors; owns correctness, root-cause diagnosis, and focused unit tests. |
| **Verifier** | `verifier` | Independently verifies full test suites, packaging, builds, regression risks, semantic contracts, and safety checks. |

> **Roster Inspection:** Run `python3 .autonomous-dev-team/sync.py --team` (or type `/team` during an active chat session) to view the active provider's roster and assigned model reasoning tiers. `/team` is a direct `sync.py` argument, never a flag for `npm`, Gradle, Make, package scripts, or build commands. The agent runs exactly one roster command without probing, building, searching, or delegating first.

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
> - Fresh installations place the runner (`.autonomous-dev-team/sync.py`) and project configuration (`.autonomous-dev-team/config.toml`) into `.autonomous-dev-team/`, while isolating managed internal sources inside `.autonomous-dev-team/_internal/` (`_internal/agents/*`, `_internal/skills/*`).
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
   Installation generates `.autonomous-dev-team/config.toml` in your repository. This is the **only file you should configure or edit**. All other files in `.autonomous-dev-team/` (such as `sync.py` and the `_internal/` directory) are engine-managed plumbing. Use `config.toml` to define test commands, build commands, provider models, and guardrails.

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
| **Codex** | `.codex/config.toml`, `.codex/agents/*.toml`, `.agents/skills/*`, `.codex/prompts/*.md` |
| **Claude Code** | `AGENTS.md`, `.claude/agents/*.md`, `.claude/skills/*` |
| **Google Antigravity** | `AGENTS.md`, `.agents/skills/*` |

The compiler also tracks managed files in `.autonomous-dev-team/manifest.json` for clean pruning and synchronization. `.autonomous-dev-team/config.toml` is the sole source of truth. Internal role instructions in `.autonomous-dev-team/_internal/agents/` and generated provider files should never be edited by hand.

## How the Workflow Works

The root agent selects the smallest safe workflow tier for each task:

- **Tier 0 (Direct)**: Direct `/root` inspection and deterministic sync.
- **Tier 1 (Surgical)**: Direct `/root` surgical edits (≤3 files, ≤150 lines, focused verification passes).
- **Tier 2 (Feature / Bugfix)**: `implementer` -> `verifier` (cohesive feature or bugfix; root cause diagnosis folded into `implementer`).
- **Tier 3 (Architecture / Overhaul)**: `architect` -> `implementer` -> `verifier` (multi-subsystem or architectural overhaul).

Specialized evaluation and safety guidance is preserved in `skills/` (such as `skills/security-review`, `skills/verification-loop`, and `skills/eval-harness`) and standalone tools in `scripts/`. They guide the active agent without requiring separate prompt roles.

### Coding Skills

The canonical skills are `team`, `agent-introspection-debugging`, `documentation-lookup`, `verification-loop`, `agent-sort`, `eval-harness`, `tdd-workflow`, `security-review`, and `coding-standards`. Providers may select a skill implicitly when its description matches the task; selection is contextual, so skills do not run on every request. Explicit invocation remains available, including Codex prompt aliases. Skills guide the active agent and never authorize delegation or broader access on their own.

Correctness comes before raw token minimization. The governor prefers the cheapest workflow that still provides adequate implementation and verification evidence, avoids duplicate reviewers covering the same risk, and permits multiple gates for distinct high-risk concerns. It preserves one retry for a plausibly transient delegation failure and allows the original implementer at most two evidence-backed repair cycles; every repair across agents and reasoning steps also counts toward the configured total repair limit. At 8 direct tool calls the agent reassesses its approach; at 12 it replans or explains why more work is needed. These checkpoints govern work performed, not provider billing, and they never override required correctness gates or permit success claims while verification is failing or incomplete.

Context duplication is strictly minimized, polling loops are avoided, and verification remains proportional to risk.

## Configuration Example

Map capability tiers to provider models, then assign roles to tiers in `.autonomous-dev-team/config.toml`:

```toml
active_provider = "codex"

[models]
balanced = { codex = "gpt-5.6-terra", claude = "claude-haiku-5-5", antigravity = "gemini-3.8-flash" }
deep     = { codex = "gpt-6.1-sol",   claude = "claude-sonnet-5-5", antigravity = "gemini-3.8-flash" }
ultra    = { codex = "gpt-6-astra",   claude = "claude-opus-5-5",   antigravity = "gemini-3.8-flash" }

[agents.implementer]
tier = "balanced"                 # every dispatch starts here
escalation = ["deep", "ultra"]    # adaptive escalation ladder
```

**Adaptive reasoning:** `adaptive_steps` configures the implementer’s balanced/medium → balanced/high → deep/medium → exceptional ultra/medium ladder; legacy `escalation` lists remain supported. Advance one effective step only on evidence of a reasoning blocker, reset unrelated slices, and bound all repairs with `reasoning_policy.max_repairs`. Missing context calls for exploration; environment and permission failures do not justify escalation. Routing considers behavioral risk first and preserves required public-interface, dependency, migration, and security gates.

Provider delivery is declared in TOML: Codex supports native effort configuration, but runtime model and effort overrides still depend on the available dispatch tool and client/model support. Unsupported overrides must be reported. Claude effort descriptions are advisory; Antigravity has no native effort override. Ineffective steps collapse, so the current identical Antigravity models produce one effective step. No native provider flags are invented.

Verification handoffs may reuse results only when the exact command, cwd, exit/result, and all relevant state are unchanged. Independent broader gates remain required. Persistent machine caching is deferred because arbitrary shell commands do not expose complete environment dependencies.

The optional benchmark runner validates a JSON manifest without executing commands:

```sh
python3 scripts/benchmark.py benchmark.json
python3 scripts/benchmark.py benchmark.json --execute > results.json
```

A manifest contains `tasks` (`id`, `snapshot`, `verify` argv), `variants` (`id`, candidate `command` argv, optional `usage_file`), `repetitions`, and `timeout_seconds`. Each run gets a fresh snapshot; the verifier runs independently. Use an external trusted verifier or hidden tests for credible outcomes because candidates can edit copied tests. Temporary directories are not security sandboxes: commands retain host, environment, and network access. Run only trusted commands.

An optional candidate usage file contains `{"credits":1.2,"provenance":"actual meter source"}`. Missing or invalid costs remain unknown. Aggregates include failed-run costs, report coverage, and calculate credits per success only with complete cost coverage and at least one success. Compare the same credit units across variants; the runner makes no pricing assumptions or paid API calls. Exit status is 1 for unsuccessful runs and 2 for invalid manifests.

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
