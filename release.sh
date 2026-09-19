#!/usr/bin/env bash

set -euo pipefail

REPOSITORY="fcastrocs/autonomous-dev-team"

fail() {
  echo "release: $*" >&2
  exit 1
}

if [[ $# -gt 1 ]]; then
  fail "usage: ./release.sh [version]"
fi

if [[ -n $(git status --porcelain) ]]; then
  fail "working tree must be clean"
fi
if [[ ! -f install.py || ! -f sync.py || ! -d agents || ! -d skills ]]; then
  fail "run this command from the autonomous-dev-team repository root"
fi
command -v gh >/dev/null || fail "GitHub CLI (gh) is required"
gh auth status >/dev/null 2>&1 || fail "GitHub CLI (gh) must be authenticated"

PYTHON=""
for cand in python3.11 python3.12 python3.13 "$HOME/.local/bin/python3.11" /opt/homebrew/bin/python3.11 /usr/local/bin/python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1 || [[ -x "$cand" ]]; then
    if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      PYTHON="$cand"
      break
    fi
  fi
done

[[ -n "$PYTHON" ]] || fail "Python 3.11 or higher is required"

"$PYTHON" sync.py --check || fail "provider files are out of sync; run 'python3 sync.py' first"
"$PYTHON" -m unittest discover tests || fail "test suite failed; fix tests before releasing"

if [[ $# -eq 1 ]]; then
  VERSION="$1"
  [[ $VERSION == v* ]] || VERSION="v$VERSION"
  if ! [[ $VERSION =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    fail "version must follow semantic versioning (e.g. v0.1.0 or 0.1.0)"
  fi
else
  CURRENT_VERSION=$( {
    git tag -l
    git ls-remote --tags --refs origin 'v*' | awk '{sub("refs/tags/", "", $2); print $2}'
  } | awk '
    /^v[0-9]+\.[0-9]+\.[0-9]+$/ {
      version = substr($0, 2)
      split(version, parts, ".")
      major = parts[1] + 0
      minor = parts[2] + 0
      patch = parts[3] + 0
      if (!found || major > best_major || (major == best_major && minor > best_minor) || (major == best_major && minor == best_minor && patch > best_patch)) {
        best_major = major
        best_minor = minor
        best_patch = patch
        found = 1
      }
    }
    END { if (found) printf "%d.%d.%d", best_major, best_minor, best_patch }
  ')

  if [[ -z $CURRENT_VERSION ]]; then
    VERSION=v0.0.1
  else
    IFS=. read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"
    VERSION="v$MAJOR.$MINOR.$((PATCH + 1))"
  fi
fi

if git rev-parse -q --verify "refs/tags/$VERSION" >/dev/null; then
  fail "tag $VERSION already exists locally"
fi
if git ls-remote --tags --refs origin "refs/tags/$VERSION" 2>/dev/null | grep -q "$VERSION"; then
  fail "tag $VERSION already exists on origin"
fi

RELEASE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/autonomous-dev-team-release.XXXXXX")
ARCHIVE_NAME="autonomous-dev-team-$VERSION.tar.gz"
ARCHIVE_PATH="$RELEASE_DIR/$ARCHIVE_NAME"
INSTALLER_PATH="$RELEASE_DIR/install.py"

cleanup() {
  rm -rf "$RELEASE_DIR"
}
trap cleanup EXIT

git tag -a "$VERSION" -m "Release $VERSION"
git archive --format=tar.gz --prefix="autonomous-dev-team-$VERSION/" -o "$ARCHIVE_PATH" "$VERSION"

if command -v sha256sum >/dev/null; then
  CHECKSUM=$(sha256sum "$ARCHIVE_PATH" | awk '{print $1}')
elif command -v shasum >/dev/null; then
  CHECKSUM=$(shasum -a 256 "$ARCHIVE_PATH" | awk '{print $1}')
else
  fail "sha256sum or shasum is required"
fi

ARCHIVE_URL="https://github.com/$REPOSITORY/releases/download/$VERSION/$ARCHIVE_NAME"
sed \
  -e "s|^DEFAULT_VERSION = .*$|DEFAULT_VERSION = \"$VERSION\"|" \
  -e "s|^DEFAULT_ARCHIVE_URL = .*$|DEFAULT_ARCHIVE_URL = \"$ARCHIVE_URL\"|" \
  -e "s|^DEFAULT_SHA256 = .*$|DEFAULT_SHA256 = \"$CHECKSUM\"|" \
  install.py > "$INSTALLER_PATH"
chmod +x "$INSTALLER_PATH"

git push origin HEAD "refs/tags/$VERSION"
gh release create "$VERSION" "$ARCHIVE_PATH" "$INSTALLER_PATH" --title "$VERSION" --generate-notes

echo "Published $VERSION. Install with:"
echo "curl -fsSL https://github.com/$REPOSITORY/releases/latest/download/install.py | python3 -"
