import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from h1b_job_monitor.models import Company, FetchResult, Job, SponsorshipEvidence
from h1b_job_monitor.monitor import JobMonitor
from h1b_job_monitor.state import StateStore


ROOT = Path(__file__).resolve().parents[1]
PROFILE = json.loads((ROOT / "config/profile.json").read_text())


def make_company(company_id="example"):
    return Company(
        id=company_id,
        name=company_id.title(),
        domain=f"{company_id}.com",
        careers_url=f"https://{company_id}.com/jobs",
        enabled=True,
        connector={"type": "greenhouse", "default_country": "US"},
        sponsorship=SponsorshipEvidence("high", 0.82, "Recent transfer LCAs", ["https://dol.gov"]),
        fit_tags=["backend", "distributed-systems", "platform", "security"],
    )


def make_job(posted, company_id="example", source_job_id="job-1"):
    return Job(
        company_id=company_id,
        company=company_id.title(),
        source="greenhouse",
        source_job_id=source_job_id,
        title="Software Engineer II, Backend Security Platform",
        location="Seattle, WA",
        description=(
            "Build Java Spring Boot distributed systems on AWS with Kafka, DynamoDB, Kubernetes, "
            "security and on-call ownership. Requires 3+ years of software engineering experience."
        ),
        source_url=f"https://{company_id}.com/jobs/{source_job_id}",
        apply_url=f"https://{company_id}.com/jobs/{source_job_id}/apply",
        posted_at=posted,
        posting_date_kind="first_published",
        posting_date_confidence="high",
    )


class MonitorTests(unittest.TestCase):
    def test_initial_then_no_duplicate_then_verified_repost(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            store = StateStore(path / "state.sqlite")
            company = make_company()
            monitor = JobMonitor([company], PROFILE, store, path / "reports")

            current_job = make_job(datetime(2026, 8, 24, tzinfo=timezone.utc))
            monitor._fetch_one = lambda _company, _since, _mode: FetchResult(
                company_id="example", source="greenhouse", jobs=[current_job, current_job], requests=1
            )
            first = monitor.run("auto", now=datetime(2026, 8, 25, tzinfo=timezone.utc))
            self.assertEqual(first["mode"], "initial")
            self.assertEqual(first["emitted_jobs"], 1)

            current_job = make_job(datetime(2026, 8, 24, tzinfo=timezone.utc))
            second = monitor.run("auto", now=datetime(2026, 8, 25, 12, tzinfo=timezone.utc))
            self.assertEqual(second["mode"], "incremental")
            self.assertEqual(second["emitted_jobs"], 0)

            current_job = make_job(datetime(2026, 8, 23, tzinfo=timezone.utc))
            current_job.source_job_id = "job-2"
            current_job.source_url = "https://example.com/jobs/job-2"
            stale_unseen = monitor.run("auto", now=datetime(2026, 8, 25, 13, tzinfo=timezone.utc))
            self.assertEqual(stale_unseen["emitted_jobs"], 0)

            current_job = make_job(datetime(2026, 8, 26, tzinfo=timezone.utc))
            third = monitor.run("auto", now=datetime(2026, 8, 26, 12, tzinfo=timezone.utc))
            self.assertEqual(third["emitted_jobs"], 1)
            store.close()

    def test_failed_company_retries_from_its_own_cursor_without_reemitting_healthy_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            store = StateStore(path / "state.sqlite")
            companies = [make_company("alpha"), make_company("beta")]
            monitor = JobMonitor(companies, PROFILE, store, path / "reports")
            phase = 1
            calls = []

            def fetch(company, since, source_mode):
                calls.append((phase, company.id, since, source_mode))
                if phase == 1 and company.id == "beta":
                    return FetchResult(
                        company_id="beta",
                        source="greenhouse",
                        error="temporary upstream failure",
                        requests=1,
                    )
                if company.id == "alpha":
                    jobs = [
                        make_job(
                            datetime(2026, 8, 24, tzinfo=timezone.utc),
                            "alpha",
                            "alpha-job",
                        )
                    ]
                else:
                    jobs = [
                        make_job(
                            datetime(2026, 8, 25, tzinfo=timezone.utc),
                            "beta",
                            "beta-job",
                        )
                    ]
                return FetchResult(
                    company_id=company.id,
                    source="greenhouse",
                    jobs=jobs,
                    requests=1,
                )

            monitor._fetch_one = fetch
            first = monitor.run("auto", now=datetime(2026, 8, 25, tzinfo=timezone.utc))
            self.assertEqual(first["status"], "partial")
            self.assertEqual(first["emitted_jobs"], 1)
            first_report = json.loads(
                (path / "reports" / "runs" / first["run_id"] / "matches.json").read_text()
            )
            self.assertEqual(first_report["metadata"]["status"], "partial")

            phase = 2
            second_now = datetime(2026, 8, 26, tzinfo=timezone.utc)
            second = monitor.run("auto", now=second_now)
            self.assertEqual(second["mode"], "incremental")
            self.assertEqual(second["status"], "success")
            self.assertEqual(second["emitted_jobs"], 1)
            second_report = json.loads((path / "reports" / "latest.json").read_text())
            self.assertEqual(second_report["jobs"][0]["company_id"], "beta")

            phase_two_calls = {company_id: (since, source_mode) for call_phase, company_id, since, source_mode in calls if call_phase == 2}
            self.assertEqual(phase_two_calls["alpha"][1], "incremental")
            self.assertEqual(
                phase_two_calls["alpha"][0],
                datetime(2026, 8, 24, 18, tzinfo=timezone.utc),
            )
            self.assertEqual(phase_two_calls["beta"][1], "initial")
            self.assertEqual(
                phase_two_calls["beta"][0],
                datetime(2026, 8, 19, tzinfo=timezone.utc),
            )
            store.close()

    def test_degraded_source_is_partial_and_does_not_advance_its_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            store = StateStore(path / "state.sqlite")
            monitor = JobMonitor([make_company()], PROFILE, store, path / "reports")
            calls = []

            def fetch(_company, since, source_mode):
                calls.append((since, source_mode))
                return FetchResult(
                    company_id="example",
                    source="greenhouse",
                    jobs=[make_job(datetime(2026, 8, 24, tzinfo=timezone.utc))],
                    warning="one recent detail request failed",
                    cursor_complete=False,
                )

            monitor._fetch_one = fetch
            first = monitor.run("auto", now=datetime(2026, 8, 25, tzinfo=timezone.utc))
            second = monitor.run("auto", now=datetime(2026, 8, 26, tzinfo=timezone.utc))
            self.assertEqual(first["status"], "partial")
            self.assertEqual(second["status"], "partial")
            self.assertEqual(calls[0][1], "initial")
            self.assertEqual(calls[1][1], "initial")
            self.assertEqual(calls[1][0], datetime(2026, 8, 19, tzinfo=timezone.utc))
            store.close()

    def test_export_failure_does_not_suppress_job_on_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            store = StateStore(path / "state.sqlite")
            monitor = JobMonitor([make_company()], PROFILE, store, path / "reports")
            jobs = []
            monitor._fetch_one = lambda _company, _since, _mode: FetchResult(
                company_id="example", source="greenhouse", jobs=list(jobs)
            )

            baseline = monitor.run("auto", now=datetime(2026, 8, 24, tzinfo=timezone.utc))
            self.assertEqual(baseline["status"], "success")
            jobs.append(make_job(datetime(2026, 8, 25, tzinfo=timezone.utc)))
            with patch("h1b_job_monitor.monitor.export_run", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    monitor.run("auto", now=datetime(2026, 8, 25, 1, tzinfo=timezone.utc))

            recovered = monitor.run("auto", now=datetime(2026, 8, 25, 2, tzinfo=timezone.utc))
            self.assertEqual(recovered["status"], "success")
            self.assertEqual(recovered["emitted_jobs"], 1)
            store.close()


if __name__ == "__main__":
    unittest.main()
