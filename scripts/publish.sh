#!/usr/bin/env bash
# ==============================================================================
# scripts/publish.sh — Deterministic Git Publishing
# Publishes verified changes to git with explicit user approval.
# ==============================================================================

set -euo pipefail

fail() {
  echo "publish error: $*" >&2
  exit 1
}

# 1. Verification of environment
command -v git >/dev/null || fail "git command not found"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "not inside a git repository"

# 2. Parse arguments
COMMIT_MSG=""
AUTO_APPROVE=0
PATHS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--message)
      [[ $# -ge 2 ]] || fail "missing argument for $1"
      COMMIT_MSG="$2"
      shift 2
      ;;
    -y|--yes)
      AUTO_APPROVE=1
      shift
      ;;
    -h|--help)
      echo "Usage: scripts/publish.sh [-m \"commit message\"] [-y|--yes] [paths...]"
      echo ""
      echo "Options:"
      echo "  -m, --message   Commit message to use"
      echo "  -y, --yes       Bypass interactive approval (pre-approved)"
      echo "  -h, --help      Show this help message"
      exit 0
      ;;
    --)
      shift
      PATHS+=("$@")
      break
      ;;
    *)
      PATHS+=("$1")
      shift
      ;;
  esac
done

# 3. Check working tree status
CHANGES=$(git status --porcelain)
if [[ -z "$CHANGES" ]]; then
  echo "Nothing to publish (working tree clean)."
  exit 0
fi

echo "=== Current Repository Status ==="
git status -sb
echo ""

# 4. Check for forbidden files in diff / untracked
FORBIDDEN_MATCHES=$(git status --porcelain | grep -E '\.env$|\.env\..*|\.git/|__pycache__/|\.pytest_cache/' || true)
if [[ -n "$FORBIDDEN_MATCHES" ]]; then
  fail "forbidden files detected in status (redact secrets/artifacts before publishing):"$'\n'"$FORBIDDEN_MATCHES"
fi

# 5. User approval gate
if [[ "$AUTO_APPROVE" -ne 1 ]]; then
  if [[ ! -t 0 ]]; then
    fail "interactive approval required in non-interactive environment (pass --yes to confirm user approval)"
  fi
  read -r -p "Approve staging, commit, and push? [y/N]: " CONFIRM
  if [[ "$CONFIRM" != [yY] && "$CONFIRM" != [yY][eE][sS] ]]; then
    echo "Publish cancelled by user."
    exit 1
  fi
fi

# 6. Stage explicit paths or all changes
if [[ ${#PATHS[@]} -gt 0 ]]; then
  git add -- "${PATHS[@]}"
else
  git add -A
fi

echo "=== Staged Changes ==="
git diff --cached --stat
echo ""

# Check that something was staged
STAGED_DIFF=$(git diff --cached --name-only)
if [[ -z "$STAGED_DIFF" ]]; then
  echo "No changes staged for commit."
  exit 0
fi

# 7. Commit
if [[ -z "$COMMIT_MSG" ]]; then
  if [[ -t 0 ]]; then
    read -r -p "Enter commit message: " COMMIT_MSG
  fi
  [[ -n "$COMMIT_MSG" ]] || fail "commit message cannot be empty"
fi

git commit -m "$COMMIT_MSG"

# 8. Push upstream safely (never force push)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" == "HEAD" ]]; then
  fail "detached HEAD state; checkout a branch before pushing"
fi

UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name "@{u}" 2>/dev/null || true)
if [[ -n "$UPSTREAM" ]]; then
  echo "Pushing to upstream: $UPSTREAM"
  git push
else
  echo "Setting upstream origin/$BRANCH and pushing"
  git push -u origin "$BRANCH"
fi

echo "✓ Successfully published changes to branch '$BRANCH'."
