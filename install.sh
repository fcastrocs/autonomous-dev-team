#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: install.sh [options] [target-directory]
  --provider NAME     all, codex, claude, gemini, antigravity, or agy (default: all)
  --version VERSION   Pinned release version (required remotely)
  --archive-url URL   Release archive URL (required remotely)
  --sha256 HEX        Expected archive SHA-256 (required remotely)
  -h, --help          Show this help

A checkout containing sync.py and agents/ supplies a local development payload.
Otherwise all three remote options are required. Authentication is provider-owned.
EOF
}
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

# These defaults are injected into the release copy of this installer.  Keep
# them empty in the checkout so local development never silently downloads a
# remote payload.
DEFAULT_VERSION=
DEFAULT_ARCHIVE_URL=
DEFAULT_SHA256=
PROVIDER=all; VERSION=${AUTONOMOUS_DEV_TEAM_VERSION:-$DEFAULT_VERSION}; ARCHIVE_URL=${AUTONOMOUS_DEV_TEAM_ARCHIVE_URL:-$DEFAULT_ARCHIVE_URL}; EXPECTED_SHA256=${AUTONOMOUS_DEV_TEAM_SHA256:-$DEFAULT_SHA256}; TARGET_INPUT=.
while [ "$#" -gt 0 ]; do
  case "$1" in
    --provider) [ "$#" -ge 2 ] || die "--provider requires a value"; PROVIDER=$2; shift 2 ;;
    --version) [ "$#" -ge 2 ] || die "--version requires a value"; VERSION=$2; shift 2 ;;
    --archive-url) [ "$#" -ge 2 ] || die "--archive-url requires a value"; ARCHIVE_URL=$2; shift 2 ;;
    --sha256) [ "$#" -ge 2 ] || die "--sha256 requires a value"; EXPECTED_SHA256=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --*) die "unknown option: $1" ;;
    *) [ "$TARGET_INPUT" = . ] || die "only one target directory may be specified"; TARGET_INPUT=$1; shift ;;
  esac
done
case "$PROVIDER" in all|codex|claude|gemini|antigravity|agy) ;; *) die "unsupported provider: $PROVIDER" ;; esac

SCRIPT_DIR=$(CDPATH= cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)
PAYLOAD_DIR=$SCRIPT_DIR; TEMP_DIR=
cleanup() { [ -z "$TEMP_DIR" ] || rm -rf "$TEMP_DIR"; }
trap cleanup EXIT HUP INT TERM

if [ ! -f "$PAYLOAD_DIR/sync.py" ] || [ ! -d "$PAYLOAD_DIR/agents" ]; then
  [ -n "$VERSION" ] || die "remote installation requires --version"
  [ -n "$ARCHIVE_URL" ] || die "remote installation requires --archive-url"
  [ -n "$EXPECTED_SHA256" ] || die "remote installation requires --sha256"
  case "$VERSION" in *[!A-Za-z0-9._-]*|'') die "invalid release version" ;; esac
  case "$EXPECTED_SHA256" in *[!A-Fa-f0-9]*|'') die "--sha256 must be hexadecimal" ;; esac
  [ "${#EXPECTED_SHA256}" -eq 64 ] || die "--sha256 must contain 64 hexadecimal characters"
  case "$ARCHIVE_URL" in *"$VERSION"*) ;; *) die "archive URL must contain the pinned version" ;; esac
  command -v curl >/dev/null 2>&1 || die "curl is required for remote installation"
  if command -v sha256sum >/dev/null 2>&1; then
    SHA256_TOOL=sha256sum
  elif command -v shasum >/dev/null 2>&1; then
    SHA256_TOOL=shasum
  else
    die "sha256sum or shasum is required for remote installation"
  fi
  command -v python3 >/dev/null 2>&1 || die "python3 is required for remote installation"
  TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/autonomous-dev-team.XXXXXXXX")
  curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 "$ARCHIVE_URL" --output "$TEMP_DIR/release.tar.gz"
  if [ "$SHA256_TOOL" = sha256sum ]; then
    ACTUAL_SHA256=$(sha256sum "$TEMP_DIR/release.tar.gz" | awk '{print $1}')
  else
    ACTUAL_SHA256=$(shasum -a 256 "$TEMP_DIR/release.tar.gz" | awk '{print $1}')
  fi
  [ "$ACTUAL_SHA256" = "$EXPECTED_SHA256" ] || die "release archive checksum verification failed"
  mkdir "$TEMP_DIR/unpacked"
  python3 - "$TEMP_DIR/release.tar.gz" "$TEMP_DIR/unpacked" <<'PY' || die "release archive contains an unsafe path or non-file entry"
import pathlib
import sys
import tarfile

archive, destination = sys.argv[1:]
with tarfile.open(archive, "r:gz") as bundle:
    members = bundle.getmembers()
    for member in members:
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
            raise SystemExit(1)
    bundle.extractall(destination, members=members)
PY
  chmod -R u+rwX,go-rwx "$TEMP_DIR/unpacked"
  PAYLOAD_DIR=$(find "$TEMP_DIR/unpacked" -type f -name sync.py -print -quit | sed 's|/sync.py$||')
  [ -n "$PAYLOAD_DIR" ] && [ -d "$PAYLOAD_DIR/agents" ] || die "release $VERSION does not contain sync.py and agents/"
fi

mkdir -p "$TARGET_INPUT"
TARGET_DIR=$(CDPATH= cd "$TARGET_INPUT" && pwd)
STAGE_DIR=$(mktemp -d "$TARGET_DIR/.autonomous-dev-team.install.XXXXXXXX")
cp "$PAYLOAD_DIR/sync.py" "$STAGE_DIR/sync.py"
cp -R "$PAYLOAD_DIR/agents" "$STAGE_DIR/agents"
chmod +x "$STAGE_DIR/sync.py"
mkdir -p "$TARGET_DIR/agents"
for source in "$STAGE_DIR"/agents/*; do mv -f "$source" "$TARGET_DIR/agents/$(basename "$source")"; done
mv -f "$STAGE_DIR/sync.py" "$TARGET_DIR/sync.py"
rmdir "$STAGE_DIR/agents" "$STAGE_DIR"
(cd "$TARGET_DIR" && python3 ./sync.py --init . --provider "$PROVIDER")
(cd "$TARGET_DIR" && python3 ./sync.py --check --provider "$PROVIDER")
printf '\nInstallation complete for %s (provider: %s).\n' "$TARGET_DIR" "$PROVIDER"
printf 'Authenticate with the selected provider CLI before use.\n'
