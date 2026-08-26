import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from h1b_job_monitor.models import Job
from h1b_job_monitor.state import StateStore


def make_job(posted="2026-08-24T00:00:00+00:00"):
    return Job(
        company_id="example",
        company="Example",
        source="test",
        source_job_id="101",
        title="Backend Software Engineer",
        location="Seattle, WA",
        description="Java AWS",
        source_url="https://example.com/jobs/101?utm_source=test",
        posted_at=datetime.fromisoformat(posted),
        posting_date_confidence="high",
        match_score=80,
        apply_priority="P1",
    )


class StateTests(unittest.TestCase):
    def test_existing_sightings_schema_is_migrated_for_observed_posted_at(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite"
            connection = sqlite3.connect(path)
            connection.execute(
                """
                CREATE TABLE sightings (
                    run_id TEXT NOT NULL,
                    job_key TEXT NOT NULL,
                    seen_at TEXT NOT NULL,
                    accepted INTEGER NOT NULL,
                    emitted INTEGER NOT NULL,
                    match_score REAL NOT NULL,
                    priority TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    PRIMARY KEY(run_id, job_key)
                )
                """
            )
            connection.commit()
            connection.close()

            store = StateStore(path)
            columns = {
                row["name"]
                for row in store.conn.execute("PRAGMA table_info(sightings)").fetchall()
            }
            self.assertIn("posted_at", columns)
            store.close()

    def test_new_seen_reposted_and_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.sqlite")
            now = datetime(2026, 8, 25, tzinfo=timezone.utc)
            run1 = store.start_run("initial", 1, now)
            job1 = make_job()
            key, event = store.upsert_job(run1, job1, True, True, now)
            self.assertEqual(event, "new")
            self.assertTrue(store.has_seen(job1))
            store.finish_run(run1, "success", {})

            run2 = store.start_run("incremental", 1, now)
            _, event = store.upsert_job(run2, make_job(), True, False, now)
            self.assertEqual(event, "seen")
            _, event = store.upsert_job(run2, make_job("2026-08-25T00:00:00+00:00"), True, True, now)
            self.assertEqual(event, "reposted")

            store.put_http_cache("https://example.com/feed", b"hello", 200, '"abc"', None)
            self.assertEqual(store.get_http_cache("https://example.com/feed")["body"], b"hello")

            self.assertIsNone(store.company_profile_fingerprint("example", "test"))
            store.set_company_profile_fingerprint("example", "test", "abc123", now)
            self.assertEqual(store.company_profile_fingerprint("example", "test"), "abc123")
            store.close()

    def test_failed_repost_sighting_does_not_advance_canonical_posted_at(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.sqlite")
            baseline_time = datetime(2026, 8, 25, tzinfo=timezone.utc)
            baseline_job = make_job("2026-08-24T00:00:00+00:00")
            baseline_run = store.start_run("initial", 1, baseline_time)
            key, event = store.upsert_job(
                baseline_run, baseline_job, True, False, baseline_time
            )
            self.assertEqual(event, "new")
            store.finalize_usable_run(
                baseline_run,
                "success",
                {"emitted_jobs": 1},
                [key],
                baseline_time,
                [],
                "profile-v1",
            )

            repost_job = make_job("2026-08-26T00:00:00+00:00")
            failed_time = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)
            failed_run = store.start_run("incremental", 1, failed_time)
            _, event = store.upsert_job(
                failed_run, repost_job, True, False, failed_time
            )
            self.assertEqual(event, "reposted")
            store.finish_run(failed_run, "failed", {"emitted_jobs": 1}, "export failed")

            persisted = store.get_previous(repost_job)
            self.assertEqual(persisted["posted_at"], baseline_job.posted_at.isoformat())
            failed_sighting = store.conn.execute(
                "SELECT posted_at, emitted FROM sightings WHERE run_id=? AND job_key=?",
                (failed_run, key),
            ).fetchone()
            self.assertEqual(failed_sighting["posted_at"], repost_job.posted_at.isoformat())
            self.assertEqual(failed_sighting["emitted"], 0)

            recovery_time = datetime(2026, 8, 26, 13, tzinfo=timezone.utc)
            recovery_run = store.start_run("incremental", 1, recovery_time)
            _, event = store.upsert_job(
                recovery_run, repost_job, True, False, recovery_time
            )
            self.assertEqual(event, "reposted")
            store.finalize_usable_run(
                recovery_run,
                "success",
                {"emitted_jobs": 1},
                [key],
                recovery_time,
                [],
                "profile-v1",
            )
            self.assertEqual(
                store.get_previous(repost_job)["posted_at"], repost_job.posted_at.isoformat()
            )

            steady_time = datetime(2026, 8, 26, 14, tzinfo=timezone.utc)
            steady_run = store.start_run("incremental", 1, steady_time)
            _, event = store.upsert_job(
                steady_run, repost_job, True, False, steady_time
            )
            self.assertEqual(event, "seen")
            store.close()

    def test_older_usable_sighting_cannot_roll_back_repost_watermark(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.sqlite")
            newer_job = make_job("2026-08-26T00:00:00+00:00")

            baseline_time = datetime(2026, 8, 27, tzinfo=timezone.utc)
            baseline_run = store.start_run("initial", 1, baseline_time)
            key, event = store.upsert_job(
                baseline_run, newer_job, True, False, baseline_time
            )
            self.assertEqual(event, "new")
            store.finalize_usable_run(
                baseline_run,
                "success",
                {"emitted_jobs": 1},
                [key],
                baseline_time,
                [],
                "profile-v1",
            )

            older_job = make_job("2026-08-24T00:00:00+00:00")
            older_time = datetime(2026, 8, 27, 1, tzinfo=timezone.utc)
            older_run = store.start_run("incremental", 1, older_time)
            _, event = store.upsert_job(
                older_run, older_job, True, False, older_time
            )
            self.assertEqual(event, "seen")
            store.finalize_usable_run(
                older_run,
                "success",
                {"emitted_jobs": 0},
                [],
                older_time,
                [],
                "profile-v1",
            )
            self.assertEqual(
                store.get_previous(newer_job)["posted_at"], newer_job.posted_at.isoformat()
            )

            newer_again_time = datetime(2026, 8, 27, 2, tzinfo=timezone.utc)
            newer_again_run = store.start_run("incremental", 1, newer_again_time)
            _, event = store.upsert_job(
                newer_again_run, newer_job, True, False, newer_again_time
            )
            self.assertEqual(event, "seen")
            store.close()


if __name__ == "__main__":
    unittest.main()
