import unittest
from scripts.github_status import render_status
from tests.test_schedule_guard import crawl, stamp


class GithubStatusTests(unittest.TestCase):
    def test_success_with_no_matches_is_explicit(self):
        title, body = render_status(stamp("2026-08-31T03:00:00Z"),
                                    [crawl("2026-08-31T02:20:00Z")], 63, "owner/repo", "10", [], [])
        self.assertIn("healthy", title)
        self.assertIn("no new verified matches", body)
        self.assertIn("2026-08-30 07:20 PM PDT", body)
        self.assertIn("Failure alerts close only after recovery", body)

    def test_old_success_does_not_hide_missed_evening(self):
        title, body = render_status(stamp("2026-08-31T04:00:00Z"),
                                    [crawl("2026-08-30T18:04:00Z")], 63, "owner/repo", "10", [], [])
        self.assertIn("overdue", title)
        self.assertIn("full crawl: **no**", body)

    def test_infrastructure_failure_overrides_success(self):
        title, body = render_status(stamp("2026-08-31T03:00:00Z"),
                                    [crawl("2026-08-31T02:20:00Z")], 63, "owner/repo", "10", ["Backup=failure"], [])
        self.assertIn("needs attention", title)
        self.assertIn("Backup=failure", body)

    def test_missing_state_is_visible(self):
        title, body = render_status(stamp("2026-08-31T03:00:00Z"), [], 63,
                                    "owner/repo", "10", ["State missing"], [])
        self.assertIn("needs attention", title)
        self.assertIn("Never", body)

    def test_cooldown_displays_eligibility_not_a_promised_start(self):
        row = crawl("2026-08-31T05:42:00Z")
        row.update(status="partial", companies_ok=62, companies_failed=1,
                   finished_at="2026-08-31T05:45:00Z")
        title, body = render_status(stamp("2026-08-31T06:00:00Z"), [row], 63,
                                    "owner/repo", "10", [], [])
        self.assertIn("needs attention", title)
        self.assertIn("2026-08-30 11:45 PM PDT", body)
        self.assertIn("not a guaranteed start time", body)


if __name__ == "__main__":
    unittest.main()
