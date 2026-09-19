#!/usr/bin/env python3
"""Autonomous Multi-Agent Protocol — Cross-Platform Installer.

Zero external dependencies beyond Python 3.11+.
Works on Linux, macOS, and Windows.
"""

import sys

# Explicit Python version check at top of install.py: Python 3.11+
if sys.version_info < (3, 11):
    import shutil
    import os
    candidates = [
        shutil.which("python3.11"),
        shutil.which("python3.12"),
        shutil.which("python3.13"),
        os.path.expanduser("~/.local/bin/python3.11"),
        "/opt/homebrew/bin/python3.11",
        "/usr/local/bin/python3.11",
    ]
    target_py = None
    for cand in candidates:
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            target_py = cand
            break
    if target_py and os.path.realpath(target_py) != os.path.realpath(sys.executable) and sys.argv and sys.argv[0] != "-c":
        args = [target_py]
        if " -m " in sys.argv[0]:
            parts = sys.argv[0].split(" -m ", 1)
            args.extend(["-m", parts[1]])
            args.extend(sys.argv[1:])
        else:
            args.extend(sys.argv)
        os.execv(target_py, args)
    sys.stderr.write(
        f"Error: Python 3.11 or higher is required (found Python {sys.version_info[0]}.{sys.version_info[1]}).\n"
    )
    sys.exit(1)


sys.dont_write_bytecode = True

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request

# These defaults are injected into the release copy of this installer. Keep
# them empty in the checkout so local development never silently downloads a
# remote payload.
DEFAULT_VERSION = ""
DEFAULT_ARCHIVE_URL = ""
DEFAULT_SHA256 = ""

CONFIG_NAME = ".autonomous-dev-team.toml"
ENCAPSULATED_DIR = ".autonomous-dev-team"
INTERNAL_DIR = "_internal"
MANAGED_DIRS = ("agents", "skills")
VALID_PROVIDERS = ("all", "codex", "claude", "antigravity", "agy")


def die(message: str) -> None:
    sys.stderr.write(f"Error: {message}\n")
    sys.exit(1)


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description=(
            "A checkout containing .autonomous-dev-team.toml, sync.py, and agents/ "
            "supplies a local development payload.\n"
            "Otherwise all three remote options are required. Authentication is provider-owned."
        ),
    )
    parser.add_argument(
        "--provider",
        default="all",
        choices=VALID_PROVIDERS,
        help="all, codex, claude, antigravity, or agy (default: all)",
    )
    parser.add_argument(
        "--version",
        default=os.environ.get("AUTONOMOUS_DEV_TEAM_VERSION") or DEFAULT_VERSION,
        help="Pinned release version (required remotely)",
    )
    parser.add_argument(
        "--archive-url",
        default=os.environ.get("AUTONOMOUS_DEV_TEAM_ARCHIVE_URL") or DEFAULT_ARCHIVE_URL,
        help="Release archive URL (required remotely)",
    )
    parser.add_argument(
        "--sha256",
        default=os.environ.get("AUTONOMOUS_DEV_TEAM_SHA256") or DEFAULT_SHA256,
        help="Expected archive SHA-256 (required remotely)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing installer-managed source files",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Target directory (default: .)",
    )
    return parser.parse_args(argv)


def compute_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def download_and_extract_remote(
    version: str,
    archive_url: str,
    expected_sha256: str,
    temp_dir: Path,
) -> Path:
    if not version:
        die("remote installation requires --version")
    if not archive_url:
        die("remote installation requires --archive-url")
    if not expected_sha256:
        die("remote installation requires --sha256")

    if not re.fullmatch(r"[A-Za-z0-9._-]+", version):
        die("invalid release version")

    if not re.fullmatch(r"[A-Fa-f0-9]+", expected_sha256):
        die("--sha256 must be hexadecimal")
    if len(expected_sha256) != 64:
        die("--sha256 must contain 64 hexadecimal characters")

    if version not in archive_url:
        die("archive URL must contain the pinned version")

    parsed = urllib.parse.urlparse(archive_url)
    if parsed.scheme not in ("https", "http", "file"):
        die("archive URL must use HTTPS, HTTP, or file scheme")

    archive_path = temp_dir / "release.tar.gz"
    try:
        req = (
            urllib.request.Request(
                archive_url,
                headers={"User-Agent": "autonomous-dev-team-installer"},
            )
            if parsed.scheme in ("https", "http")
            else archive_url
        )
        with urllib.request.urlopen(req) as resp, open(archive_path, "wb") as out:
            shutil.copyfileobj(resp, out)
    except Exception as exc:
        die(f"failed to download release archive: {exc}")

    actual_sha256 = compute_sha256(archive_path)
    if actual_sha256.lower() != expected_sha256.lower():
        die("release archive checksum verification failed")

    unpacked = temp_dir / "unpacked"
    unpacked.mkdir(parents=True, exist_ok=True)

    try:
        with tarfile.open(archive_path, "r:gz") as bundle:
            members = bundle.getmembers()
            for member in members:
                member_path = PurePosixPath(member.name)
                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                    or not (member.isfile() or member.isdir())
                ):
                    die("release archive contains an unsafe path or non-file entry")
            if hasattr(tarfile, "data_filter"):
                bundle.extractall(unpacked, members=members, filter="data")
            else:
                bundle.extractall(unpacked, members=members)
    except SystemExit:
        raise
    except Exception:
        die("release archive contains an unsafe path or non-file entry")

    payload_dir = None
    for candidate in unpacked.rglob("sync.py"):
        if candidate.is_file():
            cand_dir = candidate.parent
            if (cand_dir / CONFIG_NAME).is_file() and (cand_dir / "agents").is_dir():
                payload_dir = cand_dir
                break

    if payload_dir is None:
        die(f"release {version} does not contain canonical sources")

    return payload_dir


def main() -> None:
    args = parse_arguments(sys.argv[1:])

    if args.provider not in VALID_PROVIDERS:
        die(f"unsupported provider: {args.provider}")

    script_dir = None
    if "__file__" in globals() and __file__ and __file__ != "<stdin>":
        try:
            script_dir = Path(__file__).resolve().parent
        except Exception:
            script_dir = None

    is_local = (
        script_dir is not None
        and (script_dir / CONFIG_NAME).is_file()
        and (script_dir / "sync.py").is_file()
        and (script_dir / "agents").is_dir()
    )

    remote_temp_ctx = None
    try:
        if is_local:
            payload_dir = script_dir
        else:
            remote_temp_ctx = tempfile.TemporaryDirectory(prefix="autonomous-dev-team-")
            payload_dir = download_and_extract_remote(
                version=args.version,
                archive_url=args.archive_url,
                expected_sha256=args.sha256,
                temp_dir=Path(remote_temp_ctx.name),
            )

        target_dir = Path(args.target).resolve()
        client_dir = target_dir / ENCAPSULATED_DIR
        client_internal_dir = client_dir / INTERNAL_DIR

        if client_dir.is_symlink():
            die(f"managed source path must not be a symlink: {client_dir}")
        if client_internal_dir.is_symlink():
            die(f"managed source path must not be a symlink: {client_internal_dir}")

        for managed_dir_name in MANAGED_DIRS:
            for candidate in (
                client_internal_dir / managed_dir_name,
                client_dir / managed_dir_name,
                target_dir / managed_dir_name,
            ):
                if candidate.is_symlink():
                    die(f"managed source path must not be a symlink: {candidate}")

        if not args.force:
            target_sync = client_dir / "sync.py"
            if target_sync.exists() or target_sync.is_symlink():
                die(f"managed source already exists: {target_sync} (use --force to replace it)")

            for managed_dir_name in MANAGED_DIRS:
                payload_managed = payload_dir / managed_dir_name
                if not payload_managed.is_dir():
                    continue
                for source in sorted(payload_managed.iterdir()):
                    for parent_dir in (client_internal_dir, client_dir):
                        target_source = parent_dir / managed_dir_name / source.name
                        if target_source.exists() or target_source.is_symlink():
                            die(f"managed source already exists: {target_source} (use --force to replace it)")

        target_dir.mkdir(parents=True, exist_ok=True)
        client_dir.mkdir(parents=True, exist_ok=True)
        client_internal_dir.mkdir(parents=True, exist_ok=True)
        # Clean up any leftover temporary staging folders from previous aborted runs
        for candidate_root in (client_dir, target_dir):
            for pattern in (".install_stage.*", ".autonomous-dev-team.install.*"):
                for leftover in candidate_root.glob(pattern):
                    if leftover.is_dir() and not leftover.is_symlink():
                        try:
                            shutil.rmtree(leftover)
                        except OSError:
                            pass

        with tempfile.TemporaryDirectory(
            dir=client_dir, prefix=".install_stage."
        ) as stage_dir_name:
            stage_dir = Path(stage_dir_name)
            stage_sync = stage_dir / "sync.py"
            shutil.copy2(payload_dir / "sync.py", stage_sync)
            try:
                stage_sync.chmod(stage_sync.stat().st_mode | 0o755)
            except OSError:
                pass

            shutil.copytree(payload_dir / "agents", stage_dir / "agents")
            if (payload_dir / "skills").is_dir():
                shutil.copytree(payload_dir / "skills", stage_dir / "skills")

            for managed_dir_name in MANAGED_DIRS:
                stage_managed = stage_dir / managed_dir_name
                if stage_managed.is_dir():
                    dest_managed = client_internal_dir / managed_dir_name
                    dest_managed.mkdir(parents=True, exist_ok=True)
                    for source in list(stage_managed.iterdir()):
                        dest_source = dest_managed / source.name
                        if dest_source.is_dir() and not dest_source.is_symlink():
                            shutil.rmtree(dest_source)
                        elif dest_source.exists() or dest_source.is_symlink():
                            dest_source.unlink()
                        shutil.move(str(source), str(dest_source))
                    try:
                        stage_managed.rmdir()
                    except OSError:
                        pass
                    # If legacy un-prefixed directory exists in client_dir, clean it up
                    legacy_managed = client_dir / managed_dir_name
                    if legacy_managed.is_dir() and not legacy_managed.is_symlink():
                        shutil.rmtree(legacy_managed)

            dest_sync = client_dir / "sync.py"
            if dest_sync.exists() or dest_sync.is_symlink():
                dest_sync.unlink()
            shutil.move(str(stage_sync), str(dest_sync))

        init_cmd = [
            sys.executable,
            "-B",
            str(client_dir / "sync.py"),
            "--dir",
            str(payload_dir),
            "--init",
            str(target_dir),
            "--provider",
            args.provider,
        ]
        res = subprocess.run(init_cmd)
        if res.returncode != 0:
            sys.exit(res.returncode)

        check_cmd = [
            sys.executable,
            "-B",
            str(client_dir / "sync.py"),
            "--check",
            "--provider",
            args.provider,
        ]
        res = subprocess.run(check_cmd, cwd=str(target_dir))
        if res.returncode != 0:
            sys.exit(res.returncode)

        # Ensure no bytecode cache was created
        for pycache in (client_dir / "__pycache__", client_internal_dir / "__pycache__", target_dir / "__pycache__"):
            if pycache.is_dir() and not pycache.is_symlink():
                try:
                    shutil.rmtree(pycache)
                except OSError:
                    pass

        print(f"\nInstallation complete for {target_dir} (provider: {args.provider}).")
        print("Authenticate with the selected provider CLI before use.")

    finally:
        if remote_temp_ctx is not None:
            remote_temp_ctx.cleanup()


if __name__ == "__main__":
    main()
