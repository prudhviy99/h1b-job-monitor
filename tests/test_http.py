import unittest
from io import BytesIO
from unittest.mock import patch, Mock
from urllib.error import HTTPError, URLError

from h1b_job_monitor.http import _RobotsRules, _ascii_request_url, RobotsGate


class RobotsRulesTests(unittest.TestCase):
    @patch('h1b_job_monitor.http.time.sleep')
    @patch('h1b_job_monitor.http.urllib.request.urlopen')
    def test_robots_retries_transient_failure_but_never_bypasses_denial(self, fetch, sleep):
        url = 'https://example.com/jobs'
        fetch.side_effect = [HTTPError(url, 503, 'Unavailable', {}, None), BytesIO(b'User-agent: *\nAllow: /')]
        self.assertTrue(RobotsGate('Test', Mock()).allowed(url)[0])
        self.assertEqual(fetch.call_count, 2)
        fetch.reset_mock()
        fetch.side_effect = HTTPError(url, 403, 'Forbidden', {}, None)
        self.assertFalse(RobotsGate('Test', Mock()).allowed(url)[0])
        self.assertEqual(fetch.call_count, 1)
        fetch.reset_mock()
        fetch.side_effect = URLError('timed out')
        allowed, reason = RobotsGate('Test', Mock()).allowed(url)
        self.assertFalse(allowed)
        self.assertIn('timed out', reason)
        self.assertEqual(fetch.call_count, 3)

    @patch('h1b_job_monitor.http.urllib.request.urlopen')
    def test_robots_does_not_retry_before_long_server_cooldown(self, fetch):
        fetch.side_effect = HTTPError('https://example.com/robots.txt', 429, 'Busy', {'Retry-After': '3600'}, None)
        self.assertFalse(RobotsGate('Test', Mock()).allowed('https://example.com/jobs')[0])
        self.assertEqual(fetch.call_count, 1)

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
