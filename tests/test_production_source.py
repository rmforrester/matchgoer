"""Offline source-provenance guardrails; no deployment or production transport."""
import importlib.util
import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from production_source_guard import require_canonical
from stage_production_source import verify_files, stage
from backend.production_source_continuity import assess, check_from_environment, extend_alert


class AncestryGuard(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="matchgoer-source-guard-")
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.run_git(self.repo, "init", "-b", "master")
        self.run_git(self.repo, "config", "user.name", "Local source test")
        self.run_git(self.repo, "config", "user.email", "local-source-test@invalid.example")
        (self.repo / "source.txt").write_text("canonical\n")
        (self.repo / "ops").mkdir()
        (self.repo / "ops/production_sources.json").write_text(json.dumps({"services": {
            "writer": {"files": {"source.txt": {"source": "source.txt",
                "sha256": hashlib.sha256(b"canonical\n").hexdigest()}}}}}))
        self.run_git(self.repo, "add", ".")
        self.run_git(self.repo, "commit", "-m", "base")
        self.base = self.run_git(self.repo, "rev-parse", "HEAD")
        self.run_git(self.repo, "remote", "add", "origin", str(self.repo))
        self.run_git(self.repo, "update-ref", "refs/remotes/origin/master", self.base)
        self.run_git(self.repo, "checkout", "--detach")
        (self.repo / "source.txt").write_text("prepared production\n")
        self.run_git(self.repo, "commit", "-am", "prepared")
        self.candidate = self.run_git(self.repo, "rev-parse", "HEAD")

    def run_git(self, repo, *args, use_cwd=True):
        command = ["git"] + (["-C", str(repo)] if use_cwd else []) + list(args)
        return subprocess.check_output(command, stderr=subprocess.DEVNULL).decode().strip()

    def tearDown(self):
        # Only this test-created temporary directory is eligible for removal.
        assert self.repo.resolve().is_relative_to(self.root)
        self.temp.cleanup()

    def test_detached_unpromoted_commit_rejected(self):
        with self.assertRaisesRegex(ValueError, "REFUSE_NONCANONICAL"):
            require_canonical(self.repo, self.candidate)

    def test_local_promotion_simulation_accepts(self):
        # This is a test-only repository, never Matchgoer's master or origin.
        self.run_git(self.repo, "update-ref", "refs/heads/master", self.candidate)
        self.run_git(self.repo, "update-ref", "refs/remotes/origin/master", self.candidate)
        self.assertEqual(require_canonical(self.repo, self.candidate), self.candidate)

    def test_stale_tracking_ref_refused(self):
        self.run_git(self.repo, "update-ref", "refs/remotes/origin/master", self.candidate)
        with self.assertRaisesRegex(ValueError, "CANONICAL_REF_STALE"):
            require_canonical(self.repo, self.base)

    def test_staging_uses_committed_source_not_dirty_worktree(self):
        (self.repo / "source.txt").write_text("unapproved dirty source\n")
        destination = self.root / "staged"
        self.assertEqual(stage(self.repo, self.base, "writer", destination), 1)
        self.assertEqual((destination / "source.txt").read_bytes(), b"canonical\n")


class SourceProfiles(unittest.TestCase):
    def test_all_profiles_reproduce_recorded_source(self):
        services = json.loads((ROOT / "ops/production_sources.json").read_text())["services"]
        for service in services:
            with self.subTest(service=service):
                self.assertGreater(verify_files(ROOT, service), 0)

    def test_live_and_approved_acknowledgements_are_separate(self):
        profiles = json.loads((ROOT / "ops/production_sources.json").read_text())["services"]
        def baseline(service):
            path = profiles[service]["files"]["identity-continuity-baseline.json"]["source"]
            return json.loads((ROOT / path).read_text())
        live, approved = baseline("backup"), baseline("backup-approved-test-orphan")
        self.assertEqual(len(live["relationships"]), 17)
        self.assertEqual(len(live["acknowledged_orphans"]), 3)
        self.assertEqual(approved["relationships"][:-1], live["relationships"])
        self.assertEqual(approved["acknowledged_orphans"][:-1], live["acknowledged_orphans"])
        self.assertEqual(len(approved["acknowledged_orphans"]), 4)

    def test_attestations_exactly_43(self):
        config = json.loads((ROOT / "config/global_fixture_discovery.json").read_text(encoding="utf-8"))
        self.assertEqual(len(config["home_ground_reviews"]), 43)


class DriftMonitor(unittest.TestCase):
    def test_detached_source_warns_without_hiding_existing_alert(self):
        sha, master = "a" * 40, "b" * 40
        result = assess({"writer": {"id": "example", "revision": sha}}, master,
                        lambda *_: {"merge_base_commit": {"sha": "c" * 40}})
        self.assertEqual(result["status"], "FAIL")
        payload = extend_alert({"subject": "existing", "text": "Existing integrity warning"}, result)
        self.assertIn("Existing integrity warning", payload["text"])
        self.assertIn("PRODUCTION SOURCE CONTINUITY: FAIL", payload["text"])

    def test_canonical_ancestor_passes(self):
        sha = "a" * 40
        result = assess({"writer": {"id": "example", "revision": sha}}, "b" * 40,
                        lambda *_: {"merge_base_commit": {"sha": sha}})
        self.assertEqual(result["status"], "PASS")
        self.assertIsNone(extend_alert(None, result))

    def test_cli_source_without_commit_is_not_assumed_canonical(self):
        result = assess({"backup": {"id": "example", "revision": None}}, "b" * 40,
                        lambda *_: self.fail("Missing provenance must not be compared"))
        self.assertEqual(result["status"], "FAIL")

    def test_missing_monitor_access_fails_closed_without_network(self):
        result = check_from_environment({}, lambda *_: self.fail("No network expected"))
        self.assertEqual(result["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
