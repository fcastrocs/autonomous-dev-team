#!/usr/bin/env python3
"""Local coding-task benchmark; no provider APIs or price estimates.

JSON manifest: {"tasks": [{"id": "fix", "snapshot": "fixtures/fix",
"verify": ["python3", "-m", "unittest"]}], "variants": [{"id": "agent-a",
"command": ["my-agent", "fix the task"], "usage_file": "usage.json"}],
"repetitions": 1, "timeout_seconds": 300}.
Snapshot paths resolve relative to the manifest. Commands run in fresh copies.
usage_file is optional, relative to that copy, and may contain {"credits": 1.2,
"provenance": "meter name"}. Credits are reported observations, not verified
billing; compare only equivalent units. Missing/invalid credits remain unknown.
Use an external trusted verifier for strong evidence: candidates can alter tests
inside their task copy. Manifests and commands are trusted executable inputs. Temporary directories
isolate task files, NOT processes, credentials, network, or the host filesystem.
Use --execute to run; the default only validates and describes the plan.
"""

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import tempfile
import time


EXCLUDED = {".git", ".codex", ".claude", ".agents", "__pycache__", ".pytest_cache", "dist", "build", ".venv"}


def command_result(argv, cwd, timeout):
    start = time.monotonic()
    result = {"argv": argv, "exit_status": None, "timed_out": False, "error": None}
    try:
        # Discard command output: it may contain credentials or unbounded logs.
        process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=(os.name == "posix"))
        try:
            result["exit_status"] = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            result["timed_out"] = True
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            result["exit_status"] = process.wait()
    except OSError as error:
        result["error"] = str(error)
    result["elapsed_seconds"] = time.monotonic() - start
    return result


def aggregate(runs):
    summaries = []
    for variant in sorted({run["variant"] for run in runs}):
        group = [run for run in runs if run["variant"] == variant]
        known = [run["reported_credits"] for run in group
                 if run["reported_credits"] is not None]
        successes = sum(run["success"] for run in group)
        complete = len(known) == len(group)
        try:
            total = sum(float(credits) for credits in known) if known else None
        except (OverflowError, ValueError):
            total = None
        if total is not None and not math.isfinite(total):
            total = None
        summaries.append({"variant": variant, "runs": len(group),
                          "verified_successes": successes,
                          "success_rate": successes / len(group),
                          "known_credit_runs": len(known),
                          "credit_coverage": len(known) / len(group),
                          "known_reported_credits": total,
                          "credits_per_verified_success":
                          total / successes if complete and successes and total is not None else None})
    return summaries


def validate(manifest, base):
    for key in ("tasks", "variants"):
        entries = manifest.get(key)
        if not isinstance(entries, list) or not entries:
            raise ValueError(key + " must be a nonempty list")
        if any(not isinstance(entry, dict) for entry in entries):
            raise ValueError(key + " entries must be objects")
        ids = [entry.get("id") for entry in entries]
        if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
            raise ValueError(key + " require unique nonempty string ids")
    repetitions = manifest.get("repetitions", 1)
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("repetitions must be a positive integer")
    timeout = manifest.get("timeout_seconds", 300)
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout_seconds must be finite and positive")
    for entries, field in ((manifest["tasks"], "verify"), (manifest["variants"], "command")):
        for entry in entries:
            argv = entry.get(field)
            if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or not a for a in argv):
                raise ValueError("commands must be nonempty argv lists")
    for task in manifest["tasks"]:
        snapshot = task.get("snapshot")
        if not isinstance(snapshot, str) or not (base / snapshot).is_dir():
            raise ValueError("task snapshot must name an existing directory")
        if any(part in EXCLUDED for part in Path(snapshot).parts):
            raise ValueError("snapshot cannot be a forbidden generated path")
        if (base / snapshot).is_symlink():
            raise ValueError("snapshot symlinks are unsupported")
    for variant in manifest["variants"]:
        usage = variant.get("usage_file")
        if usage is not None and (not isinstance(usage, str) or not usage
                                  or Path(usage).is_absolute() or ".." in Path(usage).parts):
            raise ValueError("usage_file must be a relative path within the task copy")
    return repetitions, timeout


def copy_snapshot(source, destination):
    def ignore(directory, names):
        ignored = [name for name in names if name in EXCLUDED]
        for name in names:
            if name not in ignored and (Path(directory) / name).is_symlink():
                raise ValueError("snapshot symlinks are unsupported: " + name)
        return ignored
    shutil.copytree(source, destination, ignore=ignore)


def reported_usage(workspace, variant):
    if "usage_file" not in variant:
        return None, "unknown", None
    report = workspace / variant["usage_file"]
    try:
        if not report.resolve().is_relative_to(workspace.resolve()):
            raise ValueError("usage report escapes task copy")
        metadata = report.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("usage report must be a regular file, not a symlink or special file")
        if metadata.st_size > 65536:
            raise ValueError("usage report exceeds 64 KiB")
        # Nonblocking open and descriptor validation also guard replacement races.
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(report, flags)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("usage report must be a regular file")
            payload = stream.read(65537)
        if len(payload) > 65536:
            raise ValueError("usage report exceeds 64 KiB")
        usage = json.loads(payload)
        credits = usage.get("credits")
        if type(credits) not in (int, float) or credits < 0:
            raise ValueError("credits must be a finite nonnegative number")
        try:
            finite_credits = math.isfinite(float(credits))
        except OverflowError as error:
            raise ValueError("credits must be a finite nonnegative number") from error
        if not finite_credits:
            raise ValueError("credits must be a finite nonnegative number")
        provenance = usage.get("provenance", "unknown")
        if not isinstance(provenance, str):
            raise ValueError("provenance must be a string")
        return credits, provenance, None
    except (OSError, OverflowError, ValueError, AttributeError) as error:
        return None, "unknown", str(error)


def run_manifest(manifest, base, execute=False):
    base = Path(base)
    repetitions, timeout = validate(manifest, base)
    result = {"schema_version": 1, "dry_run": not execute,
              "cost_basis": "self-reported credits; no price estimates or billing verification",
              "planned_runs": len(manifest["tasks"]) * len(manifest["variants"]) * repetitions,
              "runs": [], "summary": []}
    if not execute:
        return result
    for task in manifest["tasks"]:
        for variant in manifest["variants"]:
            for repetition in range(1, repetitions + 1):
                with tempfile.TemporaryDirectory(prefix="coding-benchmark-") as temporary:
                    workspace = Path(temporary) / "task"
                    copy_snapshot(base / task["snapshot"], workspace)
                    # Never mistake a fixture's old usage report for this run's usage.
                    if "usage_file" in variant:
                        usage_path = workspace / variant["usage_file"]
                        if usage_path.is_file():
                            usage_path.unlink()
                    candidate = command_result(variant["command"], workspace, timeout)
                    credits, provenance, usage_error = reported_usage(workspace, variant)
                    verifier = command_result(task["verify"], workspace, timeout)
                    success = all(step["exit_status"] == 0 and not step["timed_out"]
                                  and step["error"] is None for step in (candidate, verifier))
                    result["runs"].append({"task": task["id"], "variant": variant["id"],
                                           "repetition": repetition, "candidate": candidate,
                                           "verifier": verifier, "success": success,
                                           "reported_credits": credits,
                                           "usage_provenance": provenance,
                                           "usage_error": usage_error})
    result["summary"] = aggregate(result["runs"])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--execute", action="store_true", help="run trusted manifest commands")
    args = parser.parse_args()
    try:
        result = run_manifest(json.loads(args.manifest.read_text()),
                              args.manifest.resolve().parent, args.execute)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(2, "benchmark: " + str(error) + "\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    return 1 if args.execute and any(not run["success"] for run in result["runs"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
