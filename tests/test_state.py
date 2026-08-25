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
            store.close()


if __name__ == "__main__":
    unittest.main()

