import json
import sqlite3
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from h1b_job_monitor.state import StateStore
from scripts.cloud_state import make_backup, restore_archive, recover, inspect_state
from tests.test_state import make_job


class CloudStateTests(unittest.TestCase):
    def make_state(self, root):
        state = root / "source.sqlite"
        store = StateStore(state)
        now = datetime.now(timezone.utc)
        run = store.start_run("initial", 1, now)
        store.upsert_job(run, make_job(), True, True, now)
        store.finish_run(run, "success", {"companies_ok": 1, "emitted_jobs": 1})
        store.put_http_cache("https://example.com", b"temporary-response", 200, None, None)
        store.close()
        return state

    def archive(self, folder, path):
        with zipfile.ZipFile(path, "w") as target:
            for name in ("jobs.sqlite.gz", "manifest.json"):
                target.write(folder / name, name)

    def test_backup_recovery_preserves_seen_jobs_and_leaves_source_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.make_state(root)
            info = inspect_state(state)
            make_backup(state, root / "snapshot")
            self.assertEqual(inspect_state(state), info)
            with sqlite3.connect(state) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM http_cache").fetchone()[0], 1)
            self.archive(root / "snapshot", root / "backup.zip")
            restored = root / "restored.sqlite"
            self.assertTrue(restore_archive(root / "backup.zip", restored))
            self.assertEqual(inspect_state(restored), info)
            with sqlite3.connect(restored) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM http_cache").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM sightings WHERE emitted=1").fetchone()[0], 1)

    def test_corrupt_backup_fails_without_creating_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.make_state(root)
            make_backup(state, root / "snapshot")
            (root / "snapshot" / "jobs.sqlite.gz").write_bytes(b"corrupt")
            self.archive(root / "snapshot", root / "bad.zip")
            destination = root / "new.sqlite"
            with self.assertRaises(ValueError):
                restore_archive(root / "bad.zip", destination)
            self.assertFalse(destination.exists())

    def test_existing_database_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.make_state(root)
            before = inspect_state(state)
            self.assertFalse(restore_archive(root / "not-needed.zip", state))
            self.assertEqual(inspect_state(state), before)

    def test_missing_cache_and_backups_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory, patch("scripts.cloud_state.gh_json", return_value={"artifacts": []}):
            destination = Path(directory) / "jobs.sqlite"
            with self.assertRaisesRegex(RuntimeError, "Refusing to reset"):
                recover(destination, "owner/repo")
            self.assertFalse(destination.exists())

    def test_newer_unbacked_report_prevents_stale_rollback(self):
        artifacts = [
            dict(name="h1b-state-backup-1-1", expired=False, created_at="2026-08-29", workflow_run={"id": 1}),
            dict(name="h1b-job-report-2-1", expired=False, created_at="2026-08-30", workflow_run={"id": 2}),
        ]
        with tempfile.TemporaryDirectory() as directory, patch("scripts.cloud_state.gh_json", return_value={"artifacts": artifacts}):
            with self.assertRaisesRegex(RuntimeError, "stale rollback"):
                recover(Path(directory) / "jobs.sqlite", "owner/repo")


if __name__ == "__main__":
    unittest.main()

