import gzip
import importlib.util
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_cloud_state", ROOT / "scripts" / "bootstrap_cloud_state.py"
)
bootstrap = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(bootstrap)


class BootstrapCloudStateTests(unittest.TestCase):
    def make_seed(self, root: Path, started_at: datetime) -> Path:
        database = root / "source.sqlite"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE runs(started_at TEXT, status TEXT)")
        connection.execute(
            "INSERT INTO runs(started_at, status) VALUES(?, 'success')",
            (started_at.isoformat(),),
        )
        connection.commit()
        connection.close()
        seed = root / "jobs.sqlite.gz"
        with database.open("rb") as source, gzip.open(seed, "wb") as target:
            shutil.copyfileobj(source, target)
        return seed

    def test_restores_recent_valid_snapshot_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = self.make_seed(root, datetime.now(timezone.utc))
            destination = root / "data" / "jobs.sqlite"
            self.assertTrue(bootstrap.restore(seed, destination, max_age_hours=72))
            self.assertTrue(destination.exists())
            connection = sqlite3.connect(destination)
            self.assertEqual(connection.execute("PRAGMA quick_check").fetchone()[0], "ok")
            connection.close()

    def test_ignores_stale_snapshot_and_leaves_fresh_initialization_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = self.make_seed(root, datetime.now(timezone.utc) - timedelta(days=10))
            destination = root / "data" / "jobs.sqlite"
            self.assertFalse(bootstrap.restore(seed, destination, max_age_hours=72))
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
