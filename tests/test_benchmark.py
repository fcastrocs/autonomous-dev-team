import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "benchmark", Path(__file__).resolve().parents[1] / "scripts" / "benchmark.py")
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "snapshot").mkdir()
        (self.root / "snapshot" / "seed").write_text("original")

    def manifest(self, candidate, verifier="assert True", **extra):
        return {"tasks": [{"id": "task", "snapshot": "snapshot",
                           "verify": [sys.executable, "-c", verifier]}],
                "variants": [{"id": "variant", "command":
                              [sys.executable, "-c", candidate]}], **extra}

    def run_manifest(self, manifest):
        return benchmark.run_manifest(manifest, self.root, execute=True)

    def test_dry_run_does_not_execute(self):
        result = benchmark.run_manifest(self.manifest("raise Exception()"), self.root)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["runs"], [])

    def test_isolation_and_independent_verification(self):
        code = "from pathlib import Path; p=Path('seed'); assert p.read_text()=='original'; p.write_text('changed')"
        result = self.run_manifest(self.manifest(
            code, "from pathlib import Path; assert Path('seed').read_text()=='changed'",
            repetitions=2))
        self.assertEqual([r["success"] for r in result["runs"]], [True, True])
        self.assertEqual((self.root / "snapshot" / "seed").read_text(), "original")
        self.assertIsNone(result["runs"][0]["reported_credits"])
        self.assertIsNone(result["summary"][0]["credits_per_verified_success"])

    def test_candidate_and_verifier_failures(self):
        for candidate, verifier in [("raise SystemExit(2)", "assert True"),
                                    ("pass", "raise SystemExit(3)")]:
            result = self.run_manifest(self.manifest(candidate, verifier))
            self.assertFalse(result["runs"][0]["success"])
            self.assertEqual(result["summary"][0]["verified_successes"], 0)

    def test_timeout_and_missing_executable(self):
        manifest = self.manifest("import time; time.sleep(10)", timeout_seconds=0.05)
        run = self.run_manifest(manifest)["runs"][0]
        self.assertTrue(run["candidate"]["timed_out"])
        self.assertFalse(run["success"])
        manifest["variants"][0]["command"] = [str(self.root / "missing")]
        run = self.run_manifest(manifest)["runs"][0]
        self.assertIsNotNone(run["candidate"]["error"])

    def test_cost_coverage_and_aggregation(self):
        runs = [{"variant": "a", "success": True, "reported_credits": 2},
                {"variant": "a", "success": False, "reported_credits": 4},
                {"variant": "b", "success": True, "reported_credits": None}]
        a, b = benchmark.aggregate(runs)
        self.assertEqual(a["credits_per_verified_success"], 6)
        self.assertEqual(a["known_credit_runs"], 2)
        self.assertEqual(b["known_credit_runs"], 0)
        self.assertIsNone(b["credits_per_verified_success"])
        self.assertIsNone(b["known_reported_credits"])
        runs.append({"variant": "a", "success": True, "reported_credits": None})
        self.assertIsNone(benchmark.aggregate(runs)[0]["credits_per_verified_success"])

    def test_unrepresentable_usage_and_overflowing_totals_are_unavailable(self):
        manifest = self.manifest(
            "from pathlib import Path; Path('usage.json').write_text('{\"credits\": 1' + '0' * 400 + '}')")
        manifest["variants"][0]["usage_file"] = "usage.json"
        run = self.run_manifest(manifest)["runs"][0]
        self.assertIsNone(run["reported_credits"])
        self.assertIn("finite nonnegative", run["usage_error"])

        summary = benchmark.aggregate([
            {"variant": "a", "success": True, "reported_credits": 1e308},
            {"variant": "a", "success": True, "reported_credits": 1e308},
        ])[0]
        self.assertEqual(summary["known_credit_runs"], 2)
        self.assertEqual(summary["credit_coverage"], 1)
        self.assertIsNone(summary["known_reported_credits"])
        self.assertIsNone(summary["credits_per_verified_success"])
        json.dumps(summary, allow_nan=False)

    def test_reported_usage_and_invalid_usage(self):
        for credits, expected in [(3.5, 3.5), (-1, None), (True, None), ("4", None)]:
            payload = json.dumps({"credits": credits, "provenance": "local meter"})
            code = "from pathlib import Path; Path('usage.json').write_text(" + repr(payload) + ")"
            manifest = self.manifest(code)
            manifest["variants"][0]["usage_file"] = "usage.json"
            run = self.run_manifest(manifest)["runs"][0]
            self.assertEqual(run["reported_credits"], expected)
            if expected is not None:
                self.assertEqual(run["usage_provenance"], "local meter")

    def test_rejects_invalid_manifest(self):
        for field, value in [("repetitions", 0), ("timeout_seconds", -1)]:
            with self.assertRaises(ValueError):
                self.run_manifest(self.manifest("pass", **{field: value}))
        manifest = self.manifest("pass")
        manifest["variants"][0]["usage_file"] = "../usage.json"
        with self.assertRaises(ValueError):
            self.run_manifest(manifest)

    def test_snapshot_excludes_generated_paths_and_rejects_symlinks(self):
        # Only create disposable fixture names, never read repository artifacts.
        for name in benchmark.EXCLUDED:
            (self.root / "snapshot" / name).mkdir()
        verifier = "from pathlib import Path; assert {p.name for p in Path('.').iterdir()}=={'seed'}"
        result = self.run_manifest(self.manifest("pass", verifier))
        self.assertTrue(result["runs"][0]["success"])
        (self.root / "snapshot" / "link").symlink_to(self.root / "snapshot" / "seed")
        with self.assertRaises(ValueError):
            self.run_manifest(self.manifest("pass"))

    def test_stale_usage_not_counted_and_failure_cost_retained(self):
        (self.root / "snapshot" / "usage.json").write_text('{"credits": 9}')
        manifest = self.manifest("pass")
        manifest["variants"][0]["usage_file"] = "usage.json"
        self.assertIsNone(self.run_manifest(manifest)["runs"][0]["reported_credits"])
        manifest["variants"][0]["command"] = [sys.executable, "-c",
            "from pathlib import Path; Path('usage.json').write_text('{\"credits\": 7}'); raise SystemExit(2)"]
        result = self.run_manifest(manifest)
        self.assertFalse(result["runs"][0]["success"])
        self.assertEqual(result["summary"][0]["known_reported_credits"], 7)
        self.assertEqual(result["runs"][0]["usage_provenance"], "unknown")

    def test_usage_symlink_rejected(self):
        report = self.root / "report.json"
        report.write_text('{"credits": 3}')
        (self.root / "usage.json").symlink_to(report)
        credits, provenance, error = benchmark.reported_usage(
            self.root, {"usage_file": "usage.json"})
        self.assertIsNone(credits)
        self.assertEqual(provenance, "unknown")
        self.assertIn("regular file", error)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires FIFO support")
    def test_usage_fifo_rejected_without_blocking(self):
        os.mkfifo(self.root / "usage.json")
        # A subprocess deadline makes regression failure bounded if FIFO is read.
        script = ("import importlib.util; from pathlib import Path; "
                  "s=importlib.util.spec_from_file_location('benchmark', "
                  + repr(str(Path(benchmark.__file__))) + "); "
                  "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                  "r=m.reported_usage(Path(" + repr(str(self.root))
                  + "), {'usage_file':'usage.json'}); "
                  "assert r[0] is None and 'regular file' in r[2]")
        result = benchmark.command_result([sys.executable, "-c", script], self.root, 2)
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["exit_status"], 0)


if __name__ == "__main__":
    unittest.main()
