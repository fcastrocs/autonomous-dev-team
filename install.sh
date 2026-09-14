#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Autonomous Multi-Agent Protocol — Project Installer
# Bootstraps this multi-service protocol into any target repository.
# Usage: ./install.sh /path/to/target-repo
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <target-repository-path>"
  echo "Example: $0 /home/user/Documents/repos/my-app"
  exit 1
fi

TARGET_DIR="$(cd "$1" && pwd)"

if [ ! -d "$TARGET_DIR" ]; then
  echo "Error: Target directory '$1' does not exist."
  exit 1
fi

echo "Installing Autonomous Multi-Agent Protocol into: $TARGET_DIR"

# 1. Copy agents/ directory
mkdir -p "$TARGET_DIR/agents"
cp -r "$SCRIPT_DIR/agents/"* "$TARGET_DIR/agents/"
echo "  ✓ Copied specialist agent templates to agents/"

# 2. Copy sync.py
cp "$SCRIPT_DIR/sync.py" "$TARGET_DIR/sync.py"
chmod +x "$TARGET_DIR/sync.py"
echo "  ✓ Copied sync.py compiler"

# 3. Copy config.toml only if it does not already exist
if [ -f "$TARGET_DIR/config.toml" ]; then
  echo "  ℹ Existing config.toml found in target; preserving existing settings."
else
  cp "$SCRIPT_DIR/config.toml" "$TARGET_DIR/config.toml"
  echo "  ✓ Installed default config.toml"
fi

# 4. Run sync.py in the target directory
echo "  ⚡ Compiling provider configs in target repository..."
(cd "$TARGET_DIR" && python3 sync.py)

echo ""
echo "=============================================================================="
echo "✓ Installation complete!"
echo "Next steps in $TARGET_DIR:"
echo "  1. Edit 'config.toml' with your project invariants (subsystems, test commands, forbidden paths)."
echo "  2. Run './sync.py' whenever you modify config.toml or model settings."
echo "=============================================================================="
