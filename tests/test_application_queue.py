import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from h1b_job_monitor.application_queue import select_queue, export_queue
from h1b_job_monitor.models import FetchResult
from h1b_job_monitor.monitor import JobMonitor
from h1b_job_monitor.state import StateStore
from test_monitor import make_job, make_company, PROFILE
from scripts.github_queue import render_queue

NOW = datetime(2026, 9, 4, tzinfo=timezone.utc)


class ApplicationQueueTests(unittest.TestCase):
    def test_live_backlog_remains_in_queue_without_being_realerted(self):
        with tempfile.TemporaryDirectory() as temp:
            store = StateStore(Path(temp) / "db.sqlite")
            monitor = JobMonitor([make_company()], PROFILE, store, Path(temp) / "reports")
            def fetch(*args):
                return FetchResult(company_id="example", source="greenhouse", jobs=[
                    make_job(NOW - timedelta(days=12), source_job_id="backlog"),
                    make_job(NOW - timedelta(days=1), source_job_id="fresh")])
            monitor._fetch_one = fetch
            first = monitor.run(now=NOW)
            self.assertEqual(first["emitted_jobs"], 1)
            self.assertEqual(first["queue_jobs"], 2)
            second = monitor.run(now=NOW + timedelta(hours=12))
            self.assertEqual(second["emitted_jobs"], 0)
            data = json.loads((Path(temp) / "reports/application-queue.json").read_text())
            self.assertEqual(len(data["jobs"]), 2)
            self.assertEqual(data["jobs"][0]["discovered_at"], NOW.isoformat())
            monitor._fetch_one = lambda *args: FetchResult(company_id="example", source="greenhouse", jobs=[])
            self.assertEqual(monitor.run(now=NOW + timedelta(days=1))["queue_jobs"], 0)
            store.close()

    def test_expired_and_old_roles_excluded_unknown_age_honest_and_req_deduped(self):
        jobs = []
        for i in range(5):
            j = make_job(NOW - timedelta(days=2), source_job_id=str(i))
            j.apply_priority = "P1"
            jobs.append(j)
        jobs[0].raw = {"validThrough": "2026-09-01"}
        jobs[1].posted_at = NOW - timedelta(days=31)
        jobs[2].posted_at = None
        jobs[2].posting_date_confidence = "unknown"
        jobs[3].raw = {"internal_job_id": 123}
        jobs[4].raw = {"internal_job_id": 123}
        jobs[4].location = "New York, NY"
        selected = select_queue(jobs, NOW)
        self.assertEqual(len(selected), 2)
        self.assertIn("New York", selected[0].location)
        self.assertIsNone(selected[1].posted_at)

    def test_public_output_escapes_injection_and_does_not_claim_unknown_dates(self):
        j = make_job(None)
        j.title = '<script>alert(1)</script> @someone'
        j.apply_priority = 'P1'
        j.posting_date_confidence = 'unknown'
        j.apply_url = 'javascript:alert(1)'
        meta = {"run_id": "test", "status": "success", "companies_enabled": 1, "companies_ok": 1, "started_at": NOW.isoformat()}
        with tempfile.TemporaryDirectory() as temp:
            export_queue(Path(temp), meta, [j], NOW, {})
            text = (Path(temp) / 'application-queue.html').read_text()
            self.assertNotIn('<script>alert(1)', text)
            self.assertNotIn('href="javascript:', text)
            self.assertIn('Posting age unverified', text)
            payload = json.loads((Path(temp) / 'application-queue.json').read_text())
            text = render_queue(payload, 'owner/repo', '123')
            self.assertNotIn('@someone', text)
            self.assertNotIn('javascript:', text)


if __name__ == '__main__':
    unittest.main()
