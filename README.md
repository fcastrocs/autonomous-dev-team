# Autonomous Dev Team

Autonomous Dev Team adds a practical multi-agent workflow to Codex, Claude Code, Gemini, and Antigravity. It generates each provider's native instruction files from one project configuration.

## Install

Once a release has been published, from the root of the repository you want to set up, run:

```bash
curl -fsSL https://github.com/fcastrocs/autonomous-dev-team/releases/latest/download/install.sh | bash
```

That installs support for every provider into the current directory. To install only one provider, add `--provider`:

```bash
curl -fsSL https://github.com/fcastrocs/autonomous-dev-team/releases/latest/download/install.sh | bash -s -- --provider codex
```

Supported values are `codex`, `claude`, `gemini`, `antigravity` (or `agy`), and `all`.

The installer preserves your existing project files and configuration. You still need to authenticate the relevant provider CLI yourself.

If you are developing this repository before publishing a release, use the local installer instead:

```bash
./install.sh
```

## Set up your project

Installation creates `.autonomous-dev-team.toml` in your repository. This is the only file you should configure or edit. Do not modify any other installed or generated file. Use it to adjust the commands and guardrails for your project—for example, its test command, build command, and paths agents must not edit.

Then regenerate provider files:

```bash
./sync.py
```

Confirm that generated files match the configuration:

```bash
./sync.py --check
```

Run `./sync.py` again whenever you change `.autonomous-dev-team.toml`.

## What it creates

Depending on the selected provider, the installer generates:

- Codex: `.codex/config.toml` and `.codex/agents/`
- Claude Code: `CLAUDE.md` and `.claude/agents/`
- Gemini: `GEMINI.md` and `.gemini/settings.json`
- Antigravity: `AGENTS.md`

`.autonomous-dev-team.toml` is the only supported customization file. The protocol and generated provider files should not be edited by hand; refresh generated files with `./sync.py`.

## How the workflow works

The root agent chooses the smallest safe workflow for a task:

- Direct checks and deterministic commands run directly.
- Small, local changes get one focused implementer.
- Larger changes are explored, planned in cohesive slices, implemented, and independently validated.

The protocol also limits context duplication, avoids polling loops, and keeps verification proportional to risk.

## Configuration

Use `.autonomous-dev-team.toml` to select active providers and models. A typical change looks like:

```toml
active_provider = "codex"

[codex.orchestrator]
model = "gpt-5.6-terra"
reasoning_effort = "low"
```

After editing it, run `./sync.py`.

## Developing this repository

Run the focused test suite:

```bash
python3 -m unittest tests/test_sync.py
```

To publish a release (GitHub CLI authentication required):

```bash
./release.sh
```

The command requires a clean checkout, finds the latest `vMAJOR.MINOR.PATCH` tag (local or on `origin`), and bumps its patch version. With no existing release it starts at `v0.0.1`. It then tags and pushes that version and publishes a checksum-pinned installer plus its matching payload. After it succeeds, the installation commands above are available.

## License

MIT
