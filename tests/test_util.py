import unittest
from datetime import datetime, timezone

from h1b_job_monitor.util import canonical_url, extract_jsonld, jsonld_location, parse_datetime, strip_html


class UtilTests(unittest.TestCase):
    def test_parse_iso_and_epoch_ms(self):
        self.assertEqual(parse_datetime("2026-08-25T10:00:00Z").year, 2026)
        self.assertEqual(
            parse_datetime("2026-08-25T07:26:36.7620792Z").microsecond,
            762079,
        )
        self.assertEqual(parse_datetime("2026-8-22").date().isoformat(), "2026-08-22")
        self.assertEqual(parse_datetime(1787587200000).date().isoformat(), "2026-08-24")

    def test_relative_date(self):
        now = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)
        self.assertEqual(parse_datetime("Posted 2 Days Ago", now=now).date().isoformat(), "2026-08-23")

    def test_html_and_jsonld(self):
        page = '<script type="application/ld+json">{"@type":"JobPosting","title":"SWE"}</script>'
        self.assertEqual(extract_jsonld(page)[0]["title"], "SWE")
        self.assertEqual(strip_html("<p>A &amp; B</p>"), "A & B")

    def test_jsonld_location_renders_nested_country_name(self):
        value = {
            "jobLocation": {
                "address": {
                    "addressLocality": "Redmond",
                    "addressRegion": "WA",
                    "addressCountry": {"@type": "Country", "name": "US"},
                }
            }
        }
        self.assertEqual(jsonld_location(value), "Redmond, WA, US")

    def test_canonical_url_removes_tracking(self):
        self.assertEqual(canonical_url("https://EXAMPLE.com/job/1/?utm_source=x&ref=abc"), "https://example.com/job/1?ref=abc")


if __name__ == "__main__":
    unittest.main()
