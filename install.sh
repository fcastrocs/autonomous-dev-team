#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Autonomous Multi-Agent Protocol — Project Installer
# Bootstraps this multi-service protocol into any target repository.
# Usage: ./install.sh [target-repository-path]
# If no path is provided, installs into the current working directory.
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_INPUT="${1:-.}"

TARGET_DIR="$(cd "$TARGET_INPUT" && pwd)"

if [ ! -d "$TARGET_DIR" ]; then
  echo "Error: Target directory '$TARGET_INPUT' does not exist."
  exit 1
fi

echo "=============================================================================="
echo "⚡ Installing Autonomous Multi-Agent Protocol into: $TARGET_DIR"
echo "=============================================================================="

# 1. Copy agents/ directory
mkdir -p "$TARGET_DIR/agents"
cp -r "$SCRIPT_DIR/agents/"* "$TARGET_DIR/agents/"
echo "  ✓ Copied specialist agent templates to agents/"

# 2. Copy sync.py
cp "$SCRIPT_DIR/sync.py" "$TARGET_DIR/sync.py"
chmod +x "$TARGET_DIR/sync.py"
echo "  ✓ Copied sync.py compiler"

# 3. Initialize or compile
if [ -f "$TARGET_DIR/config.toml" ]; then
  echo "  ℹ Existing config.toml found in target; preserving existing settings."
  echo "  ⚡ Compiling provider configs in target repository..."
  (cd "$TARGET_DIR" && python3 sync.py)
else
  echo "  🔍 Initializing configuration with project stack auto-detection..."
  (cd "$TARGET_DIR" && python3 sync.py --init .)
fi

echo ""
echo "=============================================================================="
echo "✓ Installation complete for: $(basename "$TARGET_DIR")"
echo ""
echo "Supported AI Assistants ready in this repository:"
echo "  • OpenAI Codex:          .codex/config.toml & .codex/agents/*.toml"
echo "  • Anthropic Claude Code: CLAUDE.md"
echo "  • Google Gemini / AGY:   AGENTS.md & GEMINI.md"
echo ""
echo "Next steps:"
echo "  1. Review 'config.toml' (auto-detected settings already applied)."
echo "  2. Run './sync.py --check' to verify configs anytime."
echo "=============================================================================="
