from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

from .base import Connector, register
from ..http import HttpClient, HttpError
from ..models import Company, FetchResult, Job
from ..util import extract_jsonld, jsonld_location, parse_datetime, strip_html


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _children_text(node: ET.Element) -> Dict[str, str]:
    return {_local_name(child.tag): (child.text or "").strip() for child in list(node)}


def _identifier(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("value") or value.get("name") or value.get("@id") or "")
    return str(value or "")


def _reviewed_sitemap_url(url: str, upgrade_http_to_https: bool) -> str:
    """Upgrade sitemap-provided HTTP links only for an explicitly reviewed source."""
    if not upgrade_http_to_https:
        return url
    parts = urlsplit(url)
    if parts.scheme.casefold() != "http":
        return url
    return urlunsplit(("https", parts.netloc, parts.path, parts.query, parts.fragment))


def _terminal_gone_status(exc: HttpError) -> Optional[int]:
    """Return a terminal HTTP status for a definitively removed detail page."""
    cause_status = getattr(exc.__cause__, "code", None)
    try:
        status = int(cause_status)
    except (TypeError, ValueError):
        status = None
    if status in {404, 410}:
        return status

    # HttpError's public shape is currently text-only. Keep the fallback
    # anchored to its exact status prefix so a URL or response body containing
    # "404" cannot make a transient failure look terminal.
    match = re.match(r"^HTTP (404|410) for ", str(exc))
    return int(match.group(1)) if match else None


@register
class SitemapConnector(Connector):
    type_name = "sitemap"

    def fetch(self, company: Company, client: HttpClient, since: datetime, mode: str = "initial") -> FetchResult:
        config = company.connector
        sitemap_urls = config.get("sitemap_urls") or [config["sitemap_url"]]
        access = config.get("access_policy", "strict")
        max_sitemaps = int(config.get("max_sitemaps", 30))
        max_detail = int(config.get("max_detail_requests", 80))
        upgrade_http_to_https = bool(config.get("upgrade_http_to_https", False))
        url_pattern = re.compile(config.get("job_url_regex", r"/jobs?/|/careers?/"), re.I)
        include_pattern = re.compile(config["url_include_regex"], re.I) if config.get("url_include_regex") else None
        exclude_pattern = re.compile(config["url_exclude_regex"], re.I) if config.get("url_exclude_regex") else None
        exclude_exempt_pattern = (
            re.compile(config["url_exclude_exempt_regex"], re.I)
            if config.get("url_exclude_exempt_regex")
            else None
        )
        hiring_organization_aliases = {
            str(alias).strip().casefold()
            for alias in config.get("hiring_organization_aliases", [])
            if str(alias).strip()
        }
        client.reset_request_count()

        crawl_delay = float(config.get("crawl_delay_seconds", 0))
        if crawl_delay:
            for source_url in sitemap_urls:
                client.limiter.set_host_interval(source_url, crawl_delay)

        queue = list(sitemap_urls)
        visited = set()
        candidate_urls = set()
        candidates: List[Tuple[str, Optional[datetime], bool]] = []
        warning_parts: List[str] = []
        cursor_complete = True
        while queue and len(visited) < max_sitemaps:
            sitemap_url = queue.pop(0)
            if sitemap_url in visited:
                continue
            visited.add(sitemap_url)
            response = client.get(sitemap_url, access_policy=access, use_cache=True)
            try:
                root = ET.fromstring(response.body)
            except ET.ParseError as exc:
                warning_parts.append(f"Invalid XML sitemap {sitemap_url}: {exc}")
                cursor_complete = False
                continue
            root_kind = _local_name(root.tag)
            if root_kind == "sitemapindex":
                for node in list(root):
                    values = _children_text(node)
                    location = _reviewed_sitemap_url(
                        values.get("loc", ""), upgrade_http_to_https
                    )
                    modified = parse_datetime(values.get("lastmod"))
                    if location and (modified is None or modified >= since - timedelta(days=2)):
                        queue.append(location)
                continue
            for node in list(root):
                values = _children_text(node)
                location = _reviewed_sitemap_url(
                    values.get("loc", ""), upgrade_http_to_https
                )
                # Match against the complete canonical URL. This supports strict
                # host-and-path allowlists as well as the default path expression.
                if not location or not url_pattern.search(location):
                    continue
                if include_pattern and not include_pattern.search(urlsplit(location).path):
                    continue
                path = urlsplit(location).path
                exclusion_path = (
                    exclude_exempt_pattern.sub("", path) if exclude_exempt_pattern else path
                )
                if exclude_pattern and exclude_pattern.search(exclusion_path):
                    continue
                modified = parse_datetime(values.get("lastmod"))
                if modified is not None and modified < since - timedelta(days=2):
                    continue
                if location in candidate_urls:
                    continue
                candidate_urls.add(location)
                previously_seen = bool(
                    mode == "incremental" and client.state.has_canonical_url(company.id, location)
                )
                candidates.append((location, modified, previously_seen))
        if queue:
            warning_parts.append(f"Sitemap traversal reached max_sitemaps={max_sitemaps}.")
            cursor_complete = False

        # New URLs come first during incremental runs. Known URLs are still
        # conditionally requested so a same-URL, newer datePosted can be detected
        # as a verified repost.
        if mode == "incremental":
            candidates.sort(key=lambda item: (item[2], -(item[1].timestamp() if item[1] else 0)))
        else:
            candidates.sort(key=lambda item: item[1] or datetime.min.replace(tzinfo=since.tzinfo), reverse=True)

        jobs: List[Job] = []
        detail_errors = 0
        gone_details = 0
        for page_url, lastmod, _previously_seen in candidates[:max_detail]:
            if crawl_delay:
                client.limiter.set_host_interval(page_url, crawl_delay)
            try:
                page = client.get(page_url, access_policy=access, use_cache=True).text
            except HttpError as exc:
                if _terminal_gone_status(exc) is not None:
                    gone_details += 1
                    continue
                detail_errors += 1
                cursor_complete = False
                if detail_errors <= 5:
                    warning_parts.append(f"Skipped failed detail page {page_url}: {exc}")
                if getattr(exc.__cause__, "code", None) in {401, 403} or re.match(r"^HTTP (401|403) for ", str(exc)):
                    warning_parts.append(
                        "Access denied: stopped remaining detail requests for this source; "
                        "cursor preserved for a later scheduled recovery attempt."
                    )
                    break
                continue
            except (UnicodeError, ValueError) as exc:
                detail_errors += 1
                cursor_complete = False
                if detail_errors <= 5:
                    warning_parts.append(f"Skipped failed detail page {page_url}: {exc}")
                continue
            postings = extract_jsonld(page)
            for item in postings:
                posted = parse_datetime(item.get("datePosted"))
                if posted is None and config.get("allow_lastmod_as_posted_date", False):
                    posted = lastmod
                source_url = str(item.get("url") or page_url)
                if (
                    source_url.startswith("http://")
                    and page_url.startswith("https://")
                    and urlsplit(source_url).netloc.casefold() == urlsplit(page_url).netloc.casefold()
                ):
                    source_url = "https://" + source_url[len("http://") :]
                title = str(item.get("title") or item.get("name") or "")
                description = strip_html(item.get("description", ""))
                source_id = _identifier(item.get("identifier")) or source_url
                organization = item.get("hiringOrganization") or {}
                if isinstance(organization, dict):
                    org_name = str(organization.get("name", ""))
                    normalized_org_name = org_name.strip().casefold()
                    company_name = company.name.strip().casefold()
                    company_name_matches = bool(
                        normalized_org_name
                        and (
                            company_name in normalized_org_name
                            or normalized_org_name in company_name
                        )
                    )
                    alias_matches = normalized_org_name in hiring_organization_aliases
                    if org_name and not company_name_matches and not alias_matches:
                        warning_parts.append(f"Skipped JSON-LD with mismatched hiringOrganization={org_name!r}.")
                        continue
                jobs.append(
                    Job(
                        company_id=company.id,
                        company=company.name,
                        source=self.type_name,
                        source_job_id=source_id,
                        title=title,
                        location=jsonld_location(item),
                        description=description,
                        source_url=source_url,
                        apply_url=source_url,
                        posted_at=posted,
                        posting_date_kind=(
                            "jsonld_datePosted" if item.get("datePosted") else "sitemap_lastmod"
                        ),
                        posting_date_confidence=(
                            "high" if item.get("datePosted") else ("low" if posted else "unknown")
                        ),
                        employment_type=str(item.get("employmentType", "")),
                        workplace_type=str(item.get("jobLocationType", "")),
                        raw=item,
                    )
                )
        if len(candidates) > max_detail:
            cursor_complete = False
            warning_parts.append(
                f"Sitemap had {len(candidates)} candidate URLs; only max_detail_requests={max_detail} were fetched."
            )
        if detail_errors > 5:
            warning_parts.append(f"Skipped {detail_errors - 5} additional failed detail pages.")
        if gone_details:
            warning_parts.append(
                f"Skipped {gone_details} gone detail page(s) returning terminal HTTP 404/410."
            )
        return FetchResult(
            company_id=company.id,
            source=self.type_name,
            jobs=jobs,
            requests=client.request_count,
            warning=" ".join(dict.fromkeys(warning_parts)),
            cursor_complete=cursor_complete,
        )


@register
class JsonLdPagesConnector(Connector):
    type_name = "jsonld_pages"

    def fetch(self, company: Company, client: HttpClient, since: datetime, mode: str = "initial") -> FetchResult:
        config = company.connector
        access = config.get("access_policy", "strict")
        client.reset_request_count()
        jobs: List[Job] = []
        for page_url in config.get("urls", []):
            page = client.get(page_url, access_policy=access, use_cache=True).text
            for item in extract_jsonld(page):
                source_url = str(item.get("url") or page_url)
                jobs.append(
                    Job(
                        company_id=company.id,
                        company=company.name,
                        source=self.type_name,
                        source_job_id=_identifier(item.get("identifier")) or source_url,
                        title=str(item.get("title") or item.get("name") or ""),
                        location=jsonld_location(item),
                        description=strip_html(item.get("description", "")),
                        source_url=source_url,
                        apply_url=source_url,
                        posted_at=parse_datetime(item.get("datePosted")),
                        posting_date_kind="jsonld_datePosted" if item.get("datePosted") else "unknown",
                        posting_date_confidence="high" if item.get("datePosted") else "unknown",
                        employment_type=str(item.get("employmentType", "")),
                        workplace_type=str(item.get("jobLocationType", "")),
                        raw=item,
                    )
                )
        return FetchResult(
            company_id=company.id,
            source=self.type_name,
            jobs=jobs,
            requests=client.request_count,
        )
