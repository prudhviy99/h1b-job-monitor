import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

from h1b_job_monitor.connectors.ashby import AshbyConnector
from h1b_job_monitor.connectors.amazon import AmazonConnector
from h1b_job_monitor.connectors.base import likely_detail_candidate
from h1b_job_monitor.connectors.greenhouse import GreenhouseConnector
from h1b_job_monitor.connectors.lever import LeverConnector
from h1b_job_monitor.connectors.sitemap import SitemapConnector
from h1b_job_monitor.connectors.smartrecruiters import SmartRecruitersConnector
from h1b_job_monitor.connectors.workday import WorkdayConnector
from h1b_job_monitor.http import HttpError
from h1b_job_monitor.models import Company, SponsorshipEvidence


FIXTURES = Path(__file__).parent / "fixtures"
SINCE = datetime(2026, 8, 18, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, value, url="https://example.test"):
        self.value = value
        self.url = url
        self.status = 200
        self.headers = {}
        if isinstance(value, (dict, list)):
            self.body = json.dumps(value).encode()
            self._text = json.dumps(value)
        elif isinstance(value, bytes):
            self.body = value
            self._text = value.decode()
        else:
            self.body = str(value).encode()
            self._text = str(value)

    @property
    def text(self):
        return self._text

    def json(self):
        return self.value if isinstance(self.value, (dict, list)) else json.loads(self._text)


class FakeClient:
    def __init__(self, get_handler=None, post_values=None):
        self.get_handler = get_handler
        self.post_values = list(post_values or [])
        self._count = 0
        self.state = FakeState()

    @property
    def request_count(self):
        return self._count

    def reset_request_count(self):
        self._count = 0

    def get(self, url, **kwargs):
        self._count += 1
        value = self.get_handler(url, kwargs) if callable(self.get_handler) else self.get_handler
        return FakeResponse(value, url)

    def post_json(self, url, payload, **kwargs):
        self._count += 1
        return FakeResponse(self.post_values.pop(0), url)


class FakeState:
    def __init__(self, seen_urls=None, rows=None):
        self.seen_urls = set(seen_urls or [])
        self.rows = dict(rows or {})

    def has_canonical_url(self, company_id, url):
        return url in self.seen_urls

    def get_by_canonical_url(self, company_id, url):
        return self.rows.get(url)


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def company(connector, name="Example"):
    return Company(
        id="example",
        name=name,
        domain="example.com",
        careers_url="https://example.com/jobs",
        enabled=True,
        connector=connector,
        sponsorship=SponsorshipEvidence("high", 0.82, "recent", ["https://dol.gov"]),
    )


class ConnectorTests(unittest.TestCase):
    def test_amazon_labels_basic_and_preferred_qualification_fields(self):
        payload = {
            "jobs": [
                {
                    "id": "amazon-1",
                    "title": "Software Development Engineer II",
                    "country_code": "US",
                    "posted_date": "2026-08-24",
                    "job_path": "/en/jobs/amazon-1/software-development-engineer-ii",
                    "locations": ["Seattle, WA, USA"],
                    "description": "Build Java services on AWS.",
                    "basic_qualifications": "3+ years of software engineering experience.",
                    "preferred_qualifications": "8+ years of distributed systems experience.",
                }
            ]
        }
        result = AmazonConnector().fetch(
            company({"type": "amazon", "keywords": ["software engineer"]}),
            FakeClient(payload),
            SINCE,
        )
        self.assertEqual(len(result.jobs), 1)
        self.assertIn("Basic Qualifications: 3+ years", result.jobs[0].description)
        self.assertIn("Preferred Qualifications: 8+ years", result.jobs[0].description)

    def test_resume_aligned_api_python_and_observability_titles_reach_detail_fetch(self):
        for title in (
            "API Engineer",
            "Python Engineer, Backend Services",
            "Observability Engineer",
            "Telemetry Engineer",
            "SWE II, Backend Platform",
            "SDE II, AWS Shield",
            "Member of Technical Staff",
            "Senior Member of Technical Staff, Backend Platform",
            "Data Engineer, Real-Time Streaming",
        ):
            with self.subTest(title=title):
                self.assertTrue(likely_detail_candidate(title))

        for title in (
            "Full Stack Software Engineer",
            "Software Development Engineer in Test",
            "Robotics Software Engineer",
            "AI DevOps Engineer",
            "Platform Security Engineer, DRTM / Secure Launch",
            "Data Engineer, Monetization Data Platform",
            "Staff Backend Engineer",
            "Staff Platform Engineer",
            "Staff Site Reliability Engineer",
            "Lead Backend Engineer",
            "Technical Lead, Platform",
            "Manager, Software Engineering",
        ):
            with self.subTest(title=title):
                self.assertFalse(likely_detail_candidate(title))

    def test_greenhouse_uses_first_published_not_updated(self):
        payload = fixture("greenhouse.json")

        def handler(url, kwargs):
            if url.endswith("/101"):
                return payload["jobs"][0]
            return payload

        result = GreenhouseConnector().fetch(
            company({"type": "greenhouse", "board_token": "example"}), FakeClient(handler), SINCE
        )
        self.assertEqual(len(result.jobs), 2)
        self.assertEqual(result.jobs[1].posted_at.year, 2025)
        self.assertEqual(result.jobs[0].posting_date_kind, "first_published")

    def test_lever_validates_date_with_jsonld(self):
        payload = fixture("lever.json")
        page = '<script type="application/ld+json">{"@type":"JobPosting","datePosted":"2026-08-24"}</script>'
        client = FakeClient(lambda url, kwargs: page if "jobs.lever.co" in url else payload)
        result = LeverConnector().fetch(
            company({"type": "lever", "site": "example", "page_size": 100}), client, SINCE
        )
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.jobs[0].posting_date_confidence, "medium_high")

    def test_lever_revalidates_known_old_id_and_detects_repost(self):
        payload = fixture("lever.json")
        payload[0]["createdAt"] = 1767225600000  # 2026-01-01 UTC
        hosted = payload[0]["hostedUrl"]
        page = '<script type="application/ld+json">{"@type":"JobPosting","datePosted":"2026-08-24"}</script>'
        client = FakeClient(lambda url, kwargs: page if "jobs.lever.co" in url else payload)
        client.state = FakeState(rows={hosted: {
            "posted_at": "2026-01-01T00:00:00+00:00",
            "last_seen_at": "2026-08-20T00:00:00+00:00",
        }})
        result = LeverConnector().fetch(
            company({"type": "lever", "site": "example", "page_size": 100}),
            client,
            SINCE,
            mode="incremental",
        )
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.jobs[0].posting_date_kind, "jsonld_datePosted_verified_repost")

    def test_lever_prioritizes_recent_jobs_over_historical_repost_budget(self):
        payload = fixture("lever.json")
        recent = dict(payload[0])
        recent["id"] = "recent"
        recent["hostedUrl"] = "https://jobs.lever.co/example/recent"
        recent["createdAt"] = 1787529600000  # 2026-08-24 UTC
        old = dict(payload[0])
        old["id"] = "old"
        old["hostedUrl"] = "https://jobs.lever.co/example/old"
        old["createdAt"] = 1767225600000  # 2026-01-01 UTC
        page = '<script type="application/ld+json">{"@type":"JobPosting","datePosted":"2026-08-24"}</script>'
        client = FakeClient(lambda url, kwargs: page if "jobs.lever.co" in url else [old, recent])
        client.state = FakeState(rows={old["hostedUrl"]: {
            "posted_at": "2026-01-01T00:00:00+00:00",
            "last_seen_at": "2026-08-20T00:00:00+00:00",
        }})
        result = LeverConnector().fetch(
            company({
                "type": "lever",
                "site": "example",
                "page_size": 100,
                "max_date_validation_requests": 1,
                "max_repost_validation_requests": 0,
            }),
            client,
            SINCE,
            mode="incremental",
        )
        self.assertEqual([job.source_job_id for job in result.jobs], ["recent"])
        self.assertIn("Deferred 1 known historical", result.warning)
        self.assertTrue(result.cursor_complete)

    def test_greenhouse_detail_budget_gap_marks_cursor_incomplete(self):
        payload = fixture("greenhouse.json")
        payload["jobs"][0].pop("content", None)
        payload["jobs"][0].pop("first_published", None)
        result = GreenhouseConnector().fetch(
            company({
                "type": "greenhouse",
                "board_token": "example",
                "max_detail_requests": 0,
            }),
            FakeClient(payload),
            SINCE,
        )
        self.assertFalse(result.cursor_complete)
        self.assertIn("budget was exhausted", result.warning)

    def test_greenhouse_bulk_keeps_old_live_descriptions_without_detail_calls(self):
        payload = fixture("greenhouse.json")
        for item in payload["jobs"]:
            item["content"] = "Build Java backend services. Requires 3+ years."
        calls = []
        def handler(url, kwargs):
            calls.append((url, kwargs))
            return payload
        result = GreenhouseConnector().fetch(
            company({"type": "greenhouse", "board_token": "example", "max_detail_requests": 0}),
            FakeClient(handler), SINCE,
        )
        self.assertTrue(result.cursor_complete)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["params"], {"content": "true"})
        self.assertIn("Java backend", result.jobs[1].description)

    def test_ashby_excludes_unlisted_and_keeps_secondary_location(self):
        result = AshbyConnector().fetch(
            company({"type": "ashby", "board_name": "example"}),
            FakeClient(fixture("ashby.json")),
            SINCE,
        )
        self.assertEqual(len(result.jobs), 1)
        self.assertIn("Remote (US)", result.jobs[0].location)

    def test_smartrecruiters_joins_detail_sections(self):
        listing = fixture("smartrecruiters_list.json")
        detail = fixture("smartrecruiters_detail.json")
        client = FakeClient(lambda url, kwargs: detail if url.endswith("sr-101") else listing)
        result = SmartRecruitersConnector().fetch(
            company({
                "type": "smartrecruiters",
                "company_identifier": "Example",
                "access_policy": "documented_public_api",
            }),
            client,
            SINCE,
        )
        self.assertEqual(len(result.jobs), 1)
        self.assertIn("3+ years", result.jobs[0].description)
        self.assertEqual(result.jobs[0].posting_date_confidence, "high")

    def test_smartrecruiters_requires_explicit_policy(self):
        result = SmartRecruitersConnector().fetch(
            company({"type": "smartrecruiters", "company_identifier": "Example"}),
            FakeClient(fixture("smartrecruiters_list.json")),
            SINCE,
        )
        self.assertTrue(result.skipped)

    def test_workday_uses_detail_start_date(self):
        listing = fixture("workday_list.json")
        detail = fixture("workday_detail.json")
        client = FakeClient(lambda url, kwargs: detail, post_values=[listing])
        result = WorkdayConnector().fetch(
            company({
                "type": "workday",
                "host": "example.wd1.myworkdayjobs.com",
                "tenant": "example",
                "site": "Site",
                "access_approved": True,
            }),
            client,
            SINCE,
        )
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.jobs[0].posted_at.date().isoformat(), "2026-08-24")
        self.assertIn("Remote - US", result.jobs[0].location)

    def test_sitemap_jsonld(self):
        sitemap = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/jobs/1</loc><lastmod>2026-08-24</lastmod></url></urlset>"""
        page = """<script type="application/ld+json">{"@type":"JobPosting","identifier":{"value":"1"},"title":"Backend Software Engineer","datePosted":"2026-08-24","description":"Java AWS distributed systems. 3+ years.","jobLocation":{"address":{"addressLocality":"Seattle","addressRegion":"WA","addressCountry":"US"}},"hiringOrganization":{"name":"Example"},"url":"https://example.com/jobs/1"}</script>"""
        client = FakeClient(lambda url, kwargs: page if url.endswith("/1") else sitemap)
        result = SitemapConnector().fetch(
            company({"type": "sitemap", "sitemap_url": "https://example.com/sitemap.xml"}),
            client,
            SINCE,
        )
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.jobs[0].posting_date_confidence, "high")

    def test_sitemap_upgrades_reviewed_http_locations_to_https(self):
        sitemap = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>http://example.com/jobs/1</loc></url></urlset>"""
        page = """<script type="application/ld+json">{"@type":"JobPosting","identifier":"1","title":"Backend Engineer","datePosted":"2026-08-24","hiringOrganization":{"name":"Example"}}</script>"""
        requested = []

        def handler(url, _kwargs):
            requested.append(url)
            return page if url == "https://example.com/jobs/1" else sitemap

        result = SitemapConnector().fetch(
            company(
                {
                    "type": "sitemap",
                    "sitemap_url": "https://example.com/sitemap.xml",
                    "upgrade_http_to_https": True,
                }
            ),
            FakeClient(handler),
            SINCE,
        )
        self.assertEqual(len(result.jobs), 1)
        self.assertIn("https://example.com/jobs/1", requested)
        self.assertNotIn("http://example.com/jobs/1", requested)

    def test_sitemap_accepts_configured_hiring_organization_alias(self):
        sitemap = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/jobs/1</loc></url></urlset>"""
        page = """<script type="application/ld+json">{"@type":"JobPosting","identifier":"1","title":"Backend Software Engineer","datePosted":"2026-08-24","hiringOrganization":{"name":"HPE"}}</script>"""
        client = FakeClient(lambda url, kwargs: page if url.endswith("/1") else sitemap)
        result = SitemapConnector().fetch(
            company(
                {
                    "type": "sitemap",
                    "sitemap_url": "https://example.com/sitemap.xml",
                    "hiring_organization_aliases": ["HPE"],
                },
                name="Hewlett Packard Enterprise",
            ),
            client,
            SINCE,
        )
        self.assertEqual(len(result.jobs), 1)
        self.assertNotIn("mismatched hiringOrganization", result.warning)

    def test_sitemap_rejects_unrelated_hiring_organization_despite_aliases(self):
        sitemap = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/jobs/1</loc></url></urlset>"""
        page = """<script type="application/ld+json">{"@type":"JobPosting","identifier":"1","title":"Backend Software Engineer","datePosted":"2026-08-24","hiringOrganization":{"name":"HP Inc."}}</script>"""
        client = FakeClient(lambda url, kwargs: page if url.endswith("/1") else sitemap)
        result = SitemapConnector().fetch(
            company(
                {
                    "type": "sitemap",
                    "sitemap_url": "https://example.com/sitemap.xml",
                    "hiring_organization_aliases": ["HPE"],
                },
                name="Hewlett Packard Enterprise",
            ),
            client,
            SINCE,
        )
        self.assertEqual(result.jobs, [])
        self.assertIn("mismatched hiringOrganization='HP Inc.'", result.warning)

    def test_sitemap_accepts_strict_full_url_allowlist(self):
        sitemap = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/jobs/backend-engineer/1</loc></url></urlset>"""
        page = """<script type="application/ld+json">{"@type":"JobPosting","identifier":"1","title":"Backend Engineer","datePosted":"2026-8-22","hiringOrganization":{"name":"Example"},"url":"http://example.com/jobs/backend-engineer/1"}</script>"""
        client = FakeClient(lambda url, kwargs: page if "/jobs/" in url else sitemap)
        result = SitemapConnector().fetch(
            company({
                "type": "sitemap",
                "sitemap_url": "https://example.com/sitemap.xml",
                "job_url_regex": r"^https://example\.com/jobs/[^/]+/\d+$",
            }),
            client,
            SINCE,
        )
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.jobs[0].posted_at.date().isoformat(), "2026-08-22")
        self.assertEqual(result.jobs[0].source_url, "https://example.com/jobs/backend-engineer/1")

    def test_sitemap_deduplicates_and_rechecks_known_url_for_repost(self):
        sitemap = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/jobs/1</loc></url><url><loc>https://example.com/jobs/1</loc></url></urlset>"""
        page = """<script type="application/ld+json">{"@type":"JobPosting","identifier":"1","title":"Backend Engineer","datePosted":"2026-08-24","hiringOrganization":{"name":"Example"}}</script>"""
        client = FakeClient(lambda url, kwargs: page if url.endswith("/1") else sitemap)
        client.state = FakeState({"https://example.com/jobs/1"})
        result = SitemapConnector().fetch(
            company({"type": "sitemap", "sitemap_url": "https://example.com/sitemap.xml"}),
            client,
            SINCE,
            mode="incremental",
        )
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(client.request_count, 2)

    def test_sitemap_excludes_rejected_seniority_slugs_before_detail(self):
        sitemap = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/jobs/staff-software-engineer/1</loc></url><url><loc>https://example.com/jobs/backend-software-engineer/2</loc></url></urlset>"""
        page = """<script type="application/ld+json">{"@type":"JobPosting","identifier":"2","title":"Backend Software Engineer","datePosted":"2026-08-24","hiringOrganization":{"name":"Example"}}</script>"""
        client = FakeClient(lambda url, kwargs: page if url.endswith("/2") else sitemap)
        result = SitemapConnector().fetch(
            company({
                "type": "sitemap",
                "sitemap_url": "https://example.com/sitemap.xml",
                "url_exclude_regex": r"(?:^|[-/])(?:staff|principal)(?:[-/]|$)",
            }),
            client,
            SINCE,
        )
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(client.request_count, 2)

    def test_sitemap_seniority_exemptions_preserve_mts_and_bank_ladder_roles(self):
        sitemap = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/jobs/member-of-technical-staff/1</loc></url><url><loc>https://example.com/jobs/principal-associate-software-engineer/2</loc></url><url><loc>https://example.com/jobs/staff-software-engineer/3</loc></url></urlset>"""

        def handler(url, kwargs):
            if url.endswith("/1"):
                return """<script type="application/ld+json">{"@type":"JobPosting","identifier":"1","title":"Member of Technical Staff","datePosted":"2026-08-24","hiringOrganization":{"name":"Example"}}</script>"""
            if url.endswith("/2"):
                return """<script type="application/ld+json">{"@type":"JobPosting","identifier":"2","title":"Principal Associate, Software Engineer","datePosted":"2026-08-24","hiringOrganization":{"name":"Example"}}</script>"""
            return sitemap

        result = SitemapConnector().fetch(
            company({
                "type": "sitemap",
                "sitemap_url": "https://example.com/sitemap.xml",
                "url_exclude_regex": r"(?:^|[-/])(?:staff|principal)(?:[-/]|$)",
                "url_exclude_exempt_regex": r"member-of-technical-staff|principal-associate",
            }),
            FakeClient(handler),
            SINCE,
        )
        self.assertEqual({job.source_job_id for job in result.jobs}, {"1", "2"})
        self.assertEqual(result.requests, 3)

    def test_sitemap_terminal_gone_detail_does_not_degrade_cursor(self):
        sitemap = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/jobs/1</loc></url></urlset>"""
        for status in (404, 410):
            with self.subTest(status=status):
                def handler(url, kwargs):
                    if url.endswith("/1"):
                        cause = HTTPError(url, status, "gone", None, None)
                        raise HttpError(f"HTTP {status} for {url}: gone") from cause
                    return sitemap

                result = SitemapConnector().fetch(
                    company({"type": "sitemap", "sitemap_url": "https://example.com/sitemap.xml"}),
                    FakeClient(handler),
                    SINCE,
                )
                self.assertEqual(result.jobs, [])
                self.assertTrue(result.cursor_complete)
                self.assertIn("gone detail page(s)", result.warning)

    def test_sitemap_nonterminal_detail_failures_still_degrade_cursor(self):
        sitemap = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/jobs/1</loc></url></urlset>"""
        failures = (
            ("network", HttpError("Request failed after retries: timed out")),
            ("rate_limit", HttpError("HTTP 429 for https://example.com/jobs/1: slow down")),
            ("server", HttpError("HTTP 503 for https://example.com/jobs/1: unavailable")),
            ("parse", ValueError("invalid detail response")),
        )
        for label, failure in failures:
            with self.subTest(failure=label):
                def handler(url, kwargs):
                    if url.endswith("/1"):
                        raise failure
                    return sitemap

                result = SitemapConnector().fetch(
                    company({"type": "sitemap", "sitemap_url": "https://example.com/sitemap.xml"}),
                    FakeClient(handler),
                    SINCE,
                )
                self.assertEqual(result.jobs, [])
                self.assertFalse(result.cursor_complete)
                self.assertIn("Skipped failed detail page", result.warning)

    def test_sitemap_access_denied_stops_remaining_requests(self):
        sitemap = '<urlset><url><loc>https://example.com/jobs/1</loc></url><url><loc>https://example.com/jobs/2</loc></url></urlset>'
        requested = []
        def handler(url, kwargs):
            requested.append(url)
            if "/jobs/" in url:
                raise HttpError(f"HTTP 403 for {url}: Access denied")
            return sitemap
        result = SitemapConnector().fetch(
            company({"type": "sitemap", "sitemap_url": "https://example.com/sitemap.xml"}),
            FakeClient(handler), SINCE,
        )
        self.assertEqual(len(requested), 2)
        self.assertFalse(result.cursor_complete)
        self.assertIn("stopped remaining detail requests", result.warning)


if __name__ == "__main__":
    unittest.main()
