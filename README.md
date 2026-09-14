# Autonomous Dev Team

Autonomous Dev Team adds a practical multi-agent workflow to Codex, Claude Code, Gemini, and Antigravity. It generates each provider's native instruction files from one project configuration.

## Install

From the root of the repository you want to set up, run:

```bash
git clone --depth 1 https://github.com/fcastrocs/autonomous-dev-team.git /tmp/autonomous-dev-team
/tmp/autonomous-dev-team/install.sh
```

That installs support for every provider and uses the current directory as the target. To install only one provider, add `--provider`:

```bash
/tmp/autonomous-dev-team/install.sh --provider codex
```

Supported values are `codex`, `claude`, `gemini`, `antigravity` (or `agy`), and `all`.

The installer preserves your existing project files and configuration. You still need to authenticate the relevant provider CLI yourself.

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
./release.sh v1.0.0
```

The command requires a clean checkout, tags and pushes the version, and publishes a checksum-pinned installer plus its matching payload. Users can then install from inside their project with the one-line command printed by the release script.

## License

MIT
