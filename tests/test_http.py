import unittest

from h1b_job_monitor.http import _RobotsRules, _ascii_request_url


class RobotsRulesTests(unittest.TestCase):
    def test_unicode_job_url_is_percent_encoded(self):
        value = _ascii_request_url("https://example.com/jobs/software–engineer?q=cloud platform")
        self.assertEqual(
            value,
            "https://example.com/jobs/software%E2%80%93engineer?q=cloud%20platform",
        )

    def test_longest_allow_overrides_root_disallow(self):
        rules = _RobotsRules(
            "User-agent: *\nDisallow: /\nAllow: /careers\n"
        )
        agent = "H1BJobMonitor/1.0 (+personal-use)"
        self.assertTrue(rules.can_fetch(agent, "https://example.com/careers/sitemap.xml"))
        self.assertTrue(rules.can_fetch(agent, "https://example.com/careers/job/1"))
        self.assertFalse(rules.can_fetch(agent, "https://example.com/api/private"))

    def test_specific_agent_group_overrides_wildcard(self):
        rules = _RobotsRules(
            "User-agent: *\nAllow: /\n\n"
            "User-agent: H1BJobMonitor\nDisallow: /private\n"
        )
        agent = "H1BJobMonitor/1.0"
        self.assertFalse(rules.can_fetch(agent, "https://example.com/private/job"))
        self.assertTrue(rules.can_fetch(agent, "https://example.com/public/job"))


if __name__ == "__main__":
    unittest.main()
