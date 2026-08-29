import unittest
from datetime import datetime, timezone

from scripts.schedule_guard import (
    cadence_decision,
    has_report_artifact,
    should_run,
    window_bounds,
)


class ScheduleGuardTests(unittest.TestCase):
    def test_manual_runs_are_never_suppressed(self):
        self.assertTrue(
            should_run(
                "workflow_dispatch",
                "",
                "2",
                [{"id": 1, "created_at": "2026-08-26T14:20:00Z"}],
                datetime(2026, 8, 26, 15, 0, tzinfo=timezone.utc),
            )
        )

    def test_summer_morning_primary_runs(self):
        now = datetime(2026, 8, 26, 14, 22, tzinfo=timezone.utc)
        self.assertTrue(should_run("schedule", "17 14 * * *", "2", [], now))

    def test_summer_morning_alternate_skips_after_completed_crawl(self):
        now = datetime(2026, 8, 26, 15, 22, tzinfo=timezone.utc)
        crawls = [{"id": 1, "created_at": "2026-08-26T14:22:00Z"}]
        self.assertFalse(should_run("schedule", "17 15 * * *", "2", crawls, now))

    def test_winter_early_morning_candidate_is_skipped(self):
        now = datetime(2026, 1, 15, 14, 22, tzinfo=timezone.utc)  # 06:22 PST
        decision, reason = cadence_decision("schedule", "17 14 * * *", "2", [], now)
        self.assertFalse(decision)
        self.assertIn("before", reason)

    def test_winter_morning_primary_runs(self):
        now = datetime(2026, 1, 15, 15, 22, tzinfo=timezone.utc)  # 07:22 PST
        self.assertTrue(should_run("schedule", "17 15 * * *", "2", [], now))

    def test_summer_evening_primary_uses_previous_pacific_date(self):
        now = datetime(2026, 8, 27, 2, 22, tzinfo=timezone.utc)  # Aug 26 19:22 PDT
        self.assertEqual(
            window_bounds("17 2 * * *", now),
            (
                datetime(2026, 8, 27, 2, 0, tzinfo=timezone.utc),
                datetime(2026, 8, 27, 11, 0, tzinfo=timezone.utc),
            ),
        )
        self.assertTrue(should_run("schedule", "17 2 * * *", "2", [], now))

    def test_evening_backup_skips_after_completed_crawl(self):
        now = datetime(2026, 8, 27, 4, 52, tzinfo=timezone.utc)
        crawls = [{"id": 1, "created_at": "2026-08-27T02:22:00Z"}]
        self.assertFalse(should_run("schedule", "47 4 * * *", "2", crawls, now))

    def test_successful_noop_without_report_is_not_a_completed_crawl(self):
        self.assertFalse(has_report_artifact({"artifacts": []}))
        self.assertFalse(
            has_report_artifact(
                {"artifacts": [{"name": "unrelated", "expired": False}]}
            )
        )

    def test_uploaded_report_identifies_completed_crawl(self):
        self.assertTrue(
            has_report_artifact(
                {
                    "artifacts": [
                        {"name": "h1b-job-report-123-1", "expired": False}
                    ]
                }
            )
        )
        self.assertFalse(
            has_report_artifact(
                {
                    "artifacts": [
                        {"name": "h1b-job-report-123-1", "expired": True}
                    ]
                }
            )
        )

    def test_delayed_trigger_after_its_window_is_skipped(self):
        now = datetime(2026, 8, 27, 13, 0, tzinfo=timezone.utc)  # 06:00 PDT
        decision, reason = cadence_decision("schedule", "17 2 * * *", "2", [], now)
        self.assertFalse(decision)
        self.assertIn("after", reason)

    def test_current_run_and_unknown_schedules_fail_open(self):
        now = datetime(2026, 8, 26, 14, 22, tzinfo=timezone.utc)
        crawls = [{"id": 2, "created_at": "2026-08-26T14:20:00Z"}]
        self.assertTrue(should_run("schedule", "17 14 * * *", "2", crawls, now))
        self.assertTrue(should_run("schedule", "* * * * *", "3", crawls, now))

    def test_retired_timezone_schedule_is_always_skipped(self):
        now = datetime(2026, 8, 29, 5, 0, tzinfo=timezone.utc)
        decision, reason = cadence_decision("schedule", "47 21 * * *", "2", [], now)
        self.assertFalse(decision)
        self.assertIn("Retired", reason)


if __name__ == "__main__":
    unittest.main()
