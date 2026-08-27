import unittest
from datetime import datetime, timezone

from scripts.schedule_guard import should_run, window_start


class ScheduleGuardTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 26, 22, 0, tzinfo=timezone.utc)  # 15:00 Pacific

    def test_manual_runs_are_never_suppressed(self):
        self.assertTrue(
            should_run(
                "workflow_dispatch",
                "17 7 * * *",
                "2",
                [{"id": 1, "created_at": "2026-08-26T12:00:00Z"}],
                self.now,
            )
        )

    def test_morning_backup_skips_after_a_success_in_the_same_window(self):
        runs = [{"id": 1, "created_at": "2026-08-26T14:17:00Z"}]
        self.assertFalse(should_run("schedule", "47 9 * * *", "2", runs, self.now))

    def test_morning_primary_runs_when_only_an_older_success_exists(self):
        runs = [{"id": 1, "created_at": "2026-08-26T10:30:00Z"}]
        self.assertTrue(should_run("schedule", "17 7 * * *", "2", runs, self.now))

    def test_evening_backup_uses_the_evening_window(self):
        evening = datetime(2026, 8, 27, 5, 0, tzinfo=timezone.utc)  # 22:00 Pacific
        runs = [{"id": 1, "created_at": "2026-08-27T02:17:00Z"}]
        self.assertFalse(should_run("schedule", "47 21 * * *", "2", runs, evening))

    def test_current_run_and_unknown_schedules_fail_open(self):
        runs = [{"id": 2, "created_at": "2026-08-26T14:17:00Z"}]
        self.assertTrue(should_run("schedule", "47 9 * * *", "2", runs, self.now))
        self.assertTrue(should_run("schedule", "* * * * *", "3", runs, self.now))

    def test_late_evening_event_before_four_am_uses_previous_date(self):
        late = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)  # 02:00 Pacific
        self.assertEqual(
            window_start("17 19 * * *", late),
            datetime(2026, 8, 26, 23, 0, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
