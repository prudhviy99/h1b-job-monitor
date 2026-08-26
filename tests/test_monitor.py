import copy
import json
import sqlite3
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
    def test_profile_change_backfills_recent_rejections_without_reemitting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            store = StateStore(path / "state.sqlite")
            company = make_company()
            old_profile = copy.deepcopy(PROFILE)
            old_profile["matching"]["target_title_regex"] = r"\bwidget engineer\b"
            current_job = make_job(
                datetime(2026, 8, 20, tzinfo=timezone.utc),
                source_job_id="profile-job",
            )
            calls = []

            def fetch(_company, since, source_mode):
                calls.append((since, source_mode))
                return FetchResult(
                    company_id="example",
                    source="greenhouse",
                    jobs=[current_job],
                    requests=1,
                )

            old_monitor = JobMonitor([company], old_profile, store, path / "reports")
            old_monitor._fetch_one = fetch
            old_run = old_monitor.run(
                "auto", now=datetime(2026, 8, 25, tzinfo=timezone.utc)
            )
            self.assertEqual(old_run["emitted_jobs"], 0)

            new_monitor = JobMonitor([company], PROFILE, store, path / "reports")
            new_monitor._fetch_one = fetch
            backfill = new_monitor.run(
                "auto", now=datetime(2026, 8, 26, tzinfo=timezone.utc)
            )
            self.assertEqual(calls[1][1], "initial")
            self.assertEqual(calls[1][0], datetime(2026, 8, 19, tzinfo=timezone.utc))
            self.assertEqual(backfill["profile_backfill_companies"], 1)
            self.assertEqual(backfill["emitted_jobs"], 1)
            report = json.loads((path / "reports" / "latest.json").read_text())
            self.assertEqual(report["jobs"][0]["event_type"], "new")

            steady_state = new_monitor.run(
                "auto", now=datetime(2026, 8, 26, 12, tzinfo=timezone.utc)
            )
            self.assertEqual(calls[2][1], "incremental")
            self.assertEqual(steady_state["profile_backfill_companies"], 0)
            self.assertEqual(steady_state["emitted_jobs"], 0)
            store.close()

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

    def test_export_failure_does_not_suppress_verified_repost_on_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            store = StateStore(path / "state.sqlite")
            monitor = JobMonitor([make_company()], PROFILE, store, path / "reports")
            current_job = make_job(datetime(2026, 8, 24, tzinfo=timezone.utc))
            monitor._fetch_one = lambda _company, _since, _mode: FetchResult(
                company_id="example", source="greenhouse", jobs=[current_job]
            )

            baseline = monitor.run("auto", now=datetime(2026, 8, 25, tzinfo=timezone.utc))
            self.assertEqual(baseline["status"], "success")
            self.assertEqual(baseline["emitted_jobs"], 1)

            current_job = make_job(datetime(2026, 8, 26, tzinfo=timezone.utc))
            with patch("h1b_job_monitor.monitor.export_run", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    monitor.run("auto", now=datetime(2026, 8, 26, 12, tzinfo=timezone.utc))

            persisted_job = store.get_previous(current_job)
            self.assertEqual(
                persisted_job["posted_at"],
                datetime(2026, 8, 24, tzinfo=timezone.utc).isoformat(),
            )

            recovered = monitor.run("auto", now=datetime(2026, 8, 26, 13, tzinfo=timezone.utc))
            self.assertEqual(recovered["status"], "success")
            self.assertEqual(recovered["emitted_jobs"], 1)
            recovered_report = json.loads((path / "reports" / "latest.json").read_text())
            self.assertEqual(recovered_report["jobs"][0]["event_type"], "reposted")

            steady_state = monitor.run(
                "auto", now=datetime(2026, 8, 26, 14, tzinfo=timezone.utc)
            )
            self.assertEqual(steady_state["emitted_jobs"], 0)
            store.close()

    def test_finalize_failure_atomically_preserves_verified_repost_for_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            store = StateStore(path / "state.sqlite")
            monitor = JobMonitor([make_company()], PROFILE, store, path / "reports")
            current_job = make_job(datetime(2026, 8, 24, tzinfo=timezone.utc))
            monitor._fetch_one = lambda _company, _since, _mode: FetchResult(
                company_id="example",
                source="greenhouse",
                jobs=[current_job],
            )
            baseline = monitor.run(
                "auto", now=datetime(2026, 8, 25, tzinfo=timezone.utc)
            )
            self.assertEqual(baseline["emitted_jobs"], 1)

            store.conn.executescript(
                """
                CREATE TRIGGER abort_profile_fingerprint_finalize
                BEFORE INSERT ON company_profile_fingerprints
                BEGIN
                    SELECT RAISE(ABORT, 'injected finalization failure');
                END;
                """
            )
            store.conn.commit()

            current_job = make_job(datetime(2026, 8, 26, tzinfo=timezone.utc))
            with self.assertRaisesRegex(sqlite3.IntegrityError, "injected finalization failure"):
                monitor.run("auto", now=datetime(2026, 8, 26, 12, tzinfo=timezone.utc))

            failed_run = store.conn.execute(
                "SELECT run_id, status FROM runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            self.assertEqual(failed_run["status"], "failed")
            sighting = store.conn.execute(
                "SELECT emitted, posted_at FROM sightings WHERE run_id=?",
                (failed_run["run_id"],),
            ).fetchone()
            self.assertEqual(sighting["emitted"], 0)
            self.assertEqual(
                sighting["posted_at"],
                datetime(2026, 8, 26, tzinfo=timezone.utc).isoformat(),
            )
            persisted_job = store.conn.execute(
                "SELECT posted_at, last_emitted_at FROM jobs "
                "WHERE company_id='example' AND source_job_id='job-1'"
            ).fetchone()
            self.assertEqual(
                persisted_job["posted_at"],
                datetime(2026, 8, 24, tzinfo=timezone.utc).isoformat(),
            )
            self.assertIsNotNone(persisted_job["last_emitted_at"])
            self.assertTrue(store.was_emitted_in_usable_run(current_job))

            store.conn.execute("DROP TRIGGER abort_profile_fingerprint_finalize")
            store.conn.commit()
            recovered = monitor.run(
                "auto", now=datetime(2026, 8, 26, 13, tzinfo=timezone.utc)
            )
            self.assertEqual(recovered["status"], "success")
            self.assertEqual(recovered["emitted_jobs"], 1)
            recovered_report = json.loads((path / "reports" / "latest.json").read_text())
            self.assertEqual(recovered_report["jobs"][0]["event_type"], "reposted")

            steady_state = monitor.run(
                "auto", now=datetime(2026, 8, 26, 14, tzinfo=timezone.utc)
            )
            self.assertEqual(steady_state["emitted_jobs"], 0)
            store.close()


if __name__ == "__main__":
    unittest.main()
