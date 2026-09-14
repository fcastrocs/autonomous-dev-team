#!/usr/bin/env bash

set -euo pipefail

VERSION=${1:-}
REPOSITORY="fcastrocs/autonomous-dev-team"

fail() {
  echo "release: $*" >&2
  exit 1
}

if [[ ! $VERSION =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
  fail "usage: ./release.sh vMAJOR.MINOR.PATCH"
fi

if [[ -n $(git status --porcelain) ]]; then
  fail "working tree must be clean"
fi
if [[ ! -f install.sh || ! -f sync.py || ! -d agents ]]; then
  fail "run this command from the autonomous-dev-team repository root"
fi
command -v gh >/dev/null || fail "GitHub CLI (gh) is required"
gh auth status >/dev/null 2>&1 || fail "GitHub CLI (gh) must be authenticated"
if git show-ref --verify --quiet "refs/tags/$VERSION"; then
  fail "tag $VERSION already exists"
fi

RELEASE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/autonomous-dev-team-release.XXXXXX")
ARCHIVE_NAME="autonomous-dev-team-$VERSION.tar.gz"
ARCHIVE_PATH="$RELEASE_DIR/$ARCHIVE_NAME"
INSTALLER_PATH="$RELEASE_DIR/install.sh"

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
  -e "s|^DEFAULT_VERSION=$|DEFAULT_VERSION=$VERSION|" \
  -e "s|^DEFAULT_ARCHIVE_URL=$|DEFAULT_ARCHIVE_URL=$ARCHIVE_URL|" \
  -e "s|^DEFAULT_SHA256=$|DEFAULT_SHA256=$CHECKSUM|" \
  install.sh > "$INSTALLER_PATH"
chmod +x "$INSTALLER_PATH"

git push origin "refs/tags/$VERSION"
gh release create "$VERSION" "$ARCHIVE_PATH" "$INSTALLER_PATH" --title "$VERSION" --generate-notes

echo "Published $VERSION. Install with:"
echo "curl -fsSL https://github.com/$REPOSITORY/releases/latest/download/install.sh | bash"
