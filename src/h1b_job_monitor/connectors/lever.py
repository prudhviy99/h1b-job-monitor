from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base import Connector, likely_detail_candidate, register
from ..http import HttpClient, HttpError, RobotsDenied
from ..models import Company, FetchResult, Job
from ..util import extract_jsonld, jsonld_location, parse_datetime, strip_html


@register
class LeverConnector(Connector):
    type_name = "lever"

    def fetch(self, company: Company, client: HttpClient, since: datetime, mode: str = "initial") -> FetchResult:
        config = company.connector
        site = config["site"]
        region = config.get("region", "global")
        host = "api.eu.lever.co" if region == "eu" else "api.lever.co"
        base = config.get("api_base", f"https://{host}/v0/postings")
        access = config.get("access_policy", "documented_public_api")
        page_size = min(100, int(config.get("page_size", 100)))
        max_pages = int(config.get("max_pages", 30))
        client.reset_request_count()
        records: List[Dict[str, Any]] = []
        seen = set()
        for page in range(max_pages):
            batch = client.get(
                f"{base.rstrip('/')}/{site}",
                params={"mode": "json", "skip": page * page_size, "limit": page_size},
                headers={"Accept": "application/json"},
                access_policy=access,
            ).json()
            if not isinstance(batch, list):
                raise HttpError(f"Lever returned a non-list payload for {company.name}")
            for item in batch:
                key = str(item.get("id", ""))
                if key and key not in seen:
                    seen.add(key)
                    records.append(item)
            if len(batch) < page_size:
                break
        warning = ""
        pagination_incomplete = bool(len(batch) == page_size and page + 1 >= max_pages)
        if pagination_incomplete:
            warning = f"Lever pagination stopped at configured max_pages={max_pages}."

        jobs: List[Job] = []
        detail_budget = int(config.get("max_date_validation_requests", 60))
        # Hosted-page validation is required because Lever's createdAt is not a
        # documented posting-date contract. Rechecking every historical job on
        # every run is both impolite and expensive, so known old records use a
        # separate rotating budget. Records least recently seen are ordered first
        # below, which gives eventual repost coverage without a full-board crawl.
        repost_detail_budget = int(config.get("max_repost_validation_requests", 6))
        detail_errors = 0
        detail_budget_skips = 0
        repost_budget_skips = 0
        validation_failures = 0
        now = datetime.now(timezone.utc)

        def validation_priority(item: Dict[str, Any]) -> tuple:
            hosted_url = str(item.get("hostedUrl", ""))
            previous = (
                client.state.get_by_canonical_url(company.id, hosted_url)
                if mode == "incremental" and hosted_url
                else None
            )
            created = parse_datetime(item.get("createdAt"), now=now)
            recent_or_unknown = created is None or created >= since - timedelta(days=2)
            if recent_or_unknown or previous is None:
                return (0, -(created.timestamp() if created else now.timestamp()))
            last_seen = parse_datetime(previous["last_seen_at"], now=now) if previous["last_seen_at"] else None
            return (1, last_seen or datetime.min.replace(tzinfo=timezone.utc))

        records.sort(key=validation_priority)
        for item in records:
            categories = item.get("categories") or {}
            locations = categories.get("allLocations") or [categories.get("location", "")]
            location = " | ".join(str(x) for x in locations if x)
            created = parse_datetime(item.get("createdAt"), now=now)
            posted = created
            date_kind = "lever_createdAt_unverified" if created else "unknown"
            date_confidence = "low" if created else "unknown"
            hosted_url = str(item.get("hostedUrl", ""))
            previous = (
                client.state.get_by_canonical_url(company.id, hosted_url)
                if mode == "incremental" and hosted_url
                else None
            )
            previous_posted = (
                parse_datetime(previous["posted_at"], now=now)
                if previous is not None and previous["posted_at"]
                else None
            )
            requires_validation = (
                likely_detail_candidate(str(item.get("text", "")))
                and (
                    created is None
                    or created >= since - timedelta(days=2)
                    or previous is not None
                )
            )
            if requires_validation:
                if not hosted_url:
                    validation_failures += 1
                    continue
                historical_repost_check = bool(
                    previous is not None
                    and created is not None
                    and created < since - timedelta(days=2)
                )
                if historical_repost_check:
                    if repost_detail_budget <= 0:
                        repost_budget_skips += 1
                        continue
                    repost_detail_budget -= 1
                else:
                    if detail_budget <= 0:
                        detail_budget_skips += 1
                        continue
                    detail_budget -= 1
                try:
                    page = client.get(hosted_url, access_policy="strict", use_cache=True).text
                    postings = extract_jsonld(page)
                    if postings:
                        jsonld_date = parse_datetime(postings[0].get("datePosted"), now=now)
                        if jsonld_date and (
                            created is None or abs((jsonld_date.date() - created.date()).days) <= 1
                        ):
                            posted = jsonld_date
                            date_kind = "jsonld_datePosted"
                            date_confidence = "medium_high"
                        elif jsonld_date and previous_posted and jsonld_date > previous_posted:
                            posted = jsonld_date
                            date_kind = "jsonld_datePosted_verified_repost"
                            date_confidence = "medium_high"
                        elif jsonld_date:
                            posted = jsonld_date
                            date_kind = "jsonld_conflicts_with_createdAt"
                            date_confidence = "low"
                except (HttpError, RobotsDenied):
                    detail_errors += 1
                    continue
                if date_confidence != "medium_high":
                    validation_failures += 1
                    continue
            description_parts = [item.get("descriptionPlain") or strip_html(item.get("description", ""))]
            for section in item.get("lists") or []:
                description_parts.append(str(section.get("text", "")))
                description_parts.append(strip_html(section.get("content", "")))
            description_parts.append(item.get("additionalPlain") or strip_html(item.get("additional", "")))
            jobs.append(
                Job(
                    company_id=company.id,
                    company=company.name,
                    source=self.type_name,
                    source_job_id=str(item.get("id", "")),
                    title=str(item.get("text", "")),
                    location=location,
                    description=" ".join(str(x) for x in description_parts if x),
                    source_url=hosted_url,
                    apply_url=str(item.get("applyUrl", "")),
                    posted_at=posted,
                    posting_date_kind=date_kind,
                    posting_date_confidence=date_confidence,
                    employment_type=str(categories.get("commitment", "")),
                    department=" | ".join(
                        str(categories.get(key, "")) for key in ("department", "team") if categories.get(key)
                    ),
                    workplace_type=str(item.get("workplaceType", "")),
                    raw=item,
                )
            )
        warning_parts = [warning] if warning else []
        if detail_errors:
            warning_parts.append(f"Left {detail_errors} failed date-validation candidate(s) unseen for retry.")
        if validation_failures:
            warning_parts.append(f"Left {validation_failures} unverified date candidate(s) unseen.")
        if detail_budget_skips:
            warning_parts.append(
                f"Left {detail_budget_skips} candidate(s) unseen after the date-validation budget was exhausted."
            )
        if repost_budget_skips:
            warning_parts.append(
                f"Deferred {repost_budget_skips} known historical candidate(s) to later rotating repost checks."
            )
        return FetchResult(
            company_id=company.id,
            source=self.type_name,
            jobs=jobs,
            requests=client.request_count,
            warning=" ".join(warning_parts),
            cursor_complete=not (
                pagination_incomplete
                or detail_errors
                or validation_failures
                or detail_budget_skips
            ),
        )
