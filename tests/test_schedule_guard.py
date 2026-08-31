import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from scripts.schedule_guard import current_window, decide, read_history


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def crawl(start, status="success", expected=63, finished=None):
    started = stamp(start)
    return dict(run_id=start, started_at=start,
                finished_at=finished or (started + timedelta(minutes=4)).isoformat(),
                status=status, companies_total=expected,
                companies_ok=expected if status == "success" else expected - 1,
                companies_failed=0 if status == "success" else 1, emitted_jobs=0)


class ScheduleGuardTests(unittest.TestCase):
    def test_delayed_wakeup_serves_current_evening_not_original_cron(self):
        morning = crawl("2026-08-30T18:04:00Z")
        result = decide(stamp("2026-08-31T03:00:00Z"), [morning], 63)
        self.assertTrue(result["should_run"])
        self.assertEqual(result["window_key"], "2026-08-30-evening")

    def test_evening_catchup_does_not_expire_at_four_am(self):
        result = decide(stamp("2026-08-31T13:30:00Z"), [], 63)
        self.assertTrue(result["should_run"])
        self.assertEqual(result["window_key"], "2026-08-30-evening")

    def test_success_suppresses_extra_scheduled_and_normal_manual_wakeups(self):
        rows = [crawl("2026-08-31T02:20:00Z")]
        self.assertFalse(decide(stamp("2026-08-31T03:00:00Z"), rows, 63)["should_run"])
        self.assertTrue(decide(stamp("2026-08-31T03:00:00Z"), rows, 63, force=True)["should_run"])

    def test_next_morning_is_not_suppressed_by_previous_evening(self):
        rows = [crawl("2026-08-31T02:20:00Z")]
        self.assertTrue(decide(stamp("2026-08-31T14:17:00Z"), rows, 63)["should_run"])

    def test_before_target_keeps_previous_window(self):
        rows = [crawl("2026-08-31T02:20:00Z")]
        result = decide(stamp("2026-08-31T14:16:59Z"), rows, 63)
        self.assertFalse(result["should_run"])
        self.assertEqual(result["window_key"], "2026-08-30-evening")

    def test_partial_run_does_not_count_as_success_and_respects_cooldown(self):
        rows = [crawl("2026-08-31T02:20:00Z", "partial")]
        result = decide(stamp("2026-08-31T02:55:00Z"), rows, 63)
        self.assertFalse(result["should_run"])
        self.assertFalse(result["window_complete"])
        self.assertIn("cooldown", result["reason"])
        self.assertTrue(decide(stamp("2026-08-31T03:25:00Z"), rows, 63)["should_run"])

    def test_repeated_failures_are_bounded_per_window(self):
        rows = [crawl(f"2026-08-31T{hour:02d}:20:00Z", "partial") for hour in (2, 4, 6)]
        result = decide(stamp("2026-08-31T08:00:00Z"), rows, 63)
        self.assertFalse(result["should_run"])
        self.assertIn("limit", result["reason"])
        self.assertTrue(decide(stamp("2026-08-31T14:17:00Z"), rows, 63)["should_run"])

    def test_subset_and_unfinished_runs_do_not_satisfy_full_crawl(self):
        subset = crawl("2026-08-31T02:20:00Z", expected=1)
        self.assertTrue(decide(stamp("2026-08-31T03:30:00Z"), [subset], 63)["should_run"])
        unfinished = crawl("2026-08-31T02:20:00Z")
        unfinished["finished_at"] = None
        self.assertFalse(decide(stamp("2026-08-31T02:30:00Z"), [unfinished], 63)["window_complete"])

    def test_dst_changes_targets_without_cron_reconfiguration(self):
        for instant, target in (
            ("2026-03-07T16:00:00Z", "2026-03-07T15:17:00+00:00"),
            ("2026-03-08T16:00:00Z", "2026-03-08T14:17:00+00:00"),
            ("2026-11-01T16:00:00Z", "2026-11-01T15:17:00+00:00"),
        ):
            with self.subTest(instant=instant):
                self.assertEqual(current_window(stamp(instant))["target_at"], target)

    def test_missing_state_fails_closed_without_creating_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.sqlite"
            with self.assertRaises(RuntimeError):
                read_history(path)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
