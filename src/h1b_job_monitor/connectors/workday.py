from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .base import Connector, likely_detail_candidate, register
from ..http import HttpClient, HttpError
from ..models import Company, FetchResult, Job
from ..util import parse_datetime, strip_html


def _page_fingerprint(batch: List[Dict[str, Any]]) -> str:
    values = [str(x.get("externalPath", "")) for x in batch]
    return hashlib.sha256(json.dumps(values).encode("utf-8")).hexdigest()


def _parse_posted_age(value: Any, now: datetime) -> Optional[datetime]:
    return parse_datetime(value, now=now)


@register
class WorkdayConnector(Connector):
    type_name = "workday"

    def fetch(self, company: Company, client: HttpClient, since: datetime, mode: str = "initial") -> FetchResult:
        config = company.connector
        if not config.get("access_approved", False):
            return FetchResult(
                company_id=company.id,
                source=self.type_name,
                skipped=True,
                warning="Workday source disabled: per-tenant access_approved is not true.",
            )
        host = config["host"].rstrip("/")
        if not host.startswith("http"):
            host = f"https://{host}"
        tenant = config["tenant"]
        site = config["site"]
        access = config.get("access_policy", "strict")
        list_url = f"{host}/wday/cxs/{tenant}/{site}/jobs"
        if config.get("crawl_delay_seconds"):
            client.limiter.set_host_interval(list_url, float(config["crawl_delay_seconds"]))
        applied_facets = config.get("applied_facets", {})
        max_pages = min(100, int(config.get("max_pages", 100)))
        client.reset_request_count()
        now = datetime.now(timezone.utc)
        records: List[Dict[str, Any]] = []
        page_fingerprints = set()
        first_total: Optional[int] = None
        monotonic = True
        previous_oldest: Optional[datetime] = None
        consecutive_old_pages = 0
        unparseable_age = False
        warning_parts: List[str] = []
        cursor_complete = True

        page_number = -1
        for page_number in range(max_pages):
            offset = page_number * 20
            if first_total is not None and offset >= first_total:
                break
            payload = client.post_json(
                list_url,
                {
                    "appliedFacets": applied_facets,
                    "limit": 20,
                    "offset": offset,
                    "searchText": "",
                },
                access_policy=access,
            ).json()
            batch = payload.get("jobPostings", [])
            if page_number == 0:
                first_total = int(payload.get("total", len(batch)))
                if first_total == 2000:
                    cursor_complete = False
                    warning_parts.append(
                        "Workday reported its 2,000-record cap; configure mutually exclusive US/engineering facets for completeness."
                    )
            if not batch:
                break
            fingerprint = _page_fingerprint(batch)
            if fingerprint in page_fingerprints:
                cursor_complete = False
                warning_parts.append(f"Workday repeated a page at offset={offset}; pagination stopped.")
                break
            page_fingerprints.add(fingerprint)
            records.extend(batch)

            parsed = [_parse_posted_age(item.get("postedOn"), now) for item in batch]
            if any(value is None for value in parsed):
                unparseable_age = True
            valid = [value for value in parsed if value is not None]
            if valid:
                newest, oldest = max(valid), min(valid)
                if previous_oldest is not None and newest > previous_oldest + timedelta(hours=24):
                    monotonic = False
                previous_oldest = oldest
                if max(valid) < since - timedelta(days=1):
                    consecutive_old_pages += 1
                else:
                    consecutive_old_pages = 0
            if monotonic and not unparseable_age and consecutive_old_pages >= 2:
                break
        if (
            first_total is not None
            and len(records) < first_total
            and page_number + 1 >= max_pages
            and not (monotonic and not unparseable_age and consecutive_old_pages >= 2)
        ):
            cursor_complete = False
            warning_parts.append(f"Workday pagination reached max_pages={max_pages}.")

        jobs: List[Job] = []
        detail_budget = int(config.get("max_detail_requests", 120))
        detail_errors = 0
        detail_budget_skips = 0
        for summary in records:
            estimated = _parse_posted_age(summary.get("postedOn"), now)
            should_detail = likely_detail_candidate(str(summary.get("title", ""))) and (
                estimated is None or estimated >= since - timedelta(days=2)
            )
            if not should_detail:
                continue
            if detail_budget <= 0:
                detail_budget_skips += 1
                continue
            external_path = str(summary.get("externalPath", ""))
            detail_url = f"{host}/wday/cxs/{tenant}/{site}{external_path}"
            detail_budget -= 1
            try:
                payload = client.get(detail_url, access_policy=access, use_cache=True).json()
                info = payload.get("jobPostingInfo", payload)
            except (HttpError, ValueError, TypeError):
                detail_errors += 1
                continue
            if info.get("posted") is False or info.get("canApply") is False:
                continue
            locations: List[str] = []
            for value in (info.get("location"), summary.get("locationsText")):
                if value:
                    locations.append(str(value))
            for value in info.get("additionalLocations") or []:
                if isinstance(value, dict):
                    locations.append(str(value.get("descriptor") or value.get("name") or ""))
                else:
                    locations.append(str(value))
            posted = parse_datetime(info.get("startDate"), now=now) or estimated
            source_url = str(info.get("externalUrl") or f"{host}/{site}{external_path}")
            source_id = str(
                info.get("id") or info.get("jobPostingId") or info.get("jobReqId") or external_path
            )
            jobs.append(
                Job(
                    company_id=company.id,
                    company=company.name,
                    source=self.type_name,
                    source_job_id=source_id,
                    title=str(info.get("title") or summary.get("title", "")),
                    location=" | ".join(dict.fromkeys(x for x in locations if x)),
                    description=strip_html(info.get("jobDescription", "")),
                    source_url=source_url,
                    apply_url=source_url,
                    posted_at=posted,
                    posting_date_kind="posting_start_date" if info.get("startDate") else "relative_postedOn",
                    posting_date_confidence="high" if info.get("startDate") else "medium",
                    employment_type=str(info.get("timeType", "")),
                    raw={"summary": summary, "detail": info},
                )
            )
        if detail_budget_skips:
            cursor_complete = False
            warning_parts.append(
                f"Workday detail request budget was exhausted; {detail_budget_skips} candidate(s) were not evaluated."
            )
        if detail_errors:
            cursor_complete = False
            warning_parts.append(f"Skipped {detail_errors} failed Workday detail request(s).")
        return FetchResult(
            company_id=company.id,
            source=self.type_name,
            jobs=jobs,
            requests=client.request_count,
            warning=" ".join(warning_parts),
            cursor_complete=cursor_complete,
        )
