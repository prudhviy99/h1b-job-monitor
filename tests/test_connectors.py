import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from h1b_job_monitor.connectors.ashby import AshbyConnector
from h1b_job_monitor.connectors.greenhouse import GreenhouseConnector
from h1b_job_monitor.connectors.lever import LeverConnector
from h1b_job_monitor.connectors.sitemap import SitemapConnector
from h1b_job_monitor.connectors.smartrecruiters import SmartRecruitersConnector
from h1b_job_monitor.connectors.workday import WorkdayConnector
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


def company(connector):
    return Company(
        id="example",
        name="Example",
        domain="example.com",
        careers_url="https://example.com/jobs",
        enabled=True,
        connector=connector,
        sponsorship=SponsorshipEvidence("high", 0.82, "recent", ["https://dol.gov"]),
    )


class ConnectorTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
