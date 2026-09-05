from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

from .base import Connector, likely_detail_candidate, register
from ..http import HttpClient, HttpError
from ..models import Company, FetchResult, Job
from ..util import parse_datetime, strip_html


@register
class GreenhouseConnector(Connector):
    type_name = "greenhouse"

    def fetch(self, company: Company, client: HttpClient, since, mode: str = "initial") -> FetchResult:
        config = company.connector
        token = config["board_token"]
        base = config.get("api_base", "https://boards-api.greenhouse.io/v1/boards")
        access = config.get("access_policy", "documented_public_api")
        list_url = f"{base.rstrip('/')}/{token}/jobs"
        client.reset_request_count()
        # The documented bulk endpoint includes descriptions and departments.
        # Without content=true, older live roles became empty-description
        # rejections and disappeared from the application backlog on later runs.
        response = client.get(list_url, params={"content": "true"}, access_policy=access)
        payload = response.json()
        items = payload.get("jobs", [])
        jobs: List[Job] = []
        detail_budget = int(config.get("max_detail_requests", 80))
        detail_errors = 0
        detail_budget_skips = 0
        for item in items:
            if item.get("internal_job_id") is None and config.get("exclude_prospect_posts", True):
                continue
            posted = parse_datetime(item.get("first_published"))
            detail: Dict[str, Any] = {}
            needs_detail = likely_detail_candidate(str(item.get("title", ""))) and (
                posted is None or not item.get("content")
            )
            if needs_detail:
                if detail_budget <= 0:
                    detail_budget_skips += 1
                    continue
                detail_url = f"{list_url}/{item['id']}"
                detail_budget -= 1
                try:
                    detail = client.get(detail_url, access_policy=access).json()
                    posted = parse_datetime(detail.get("first_published")) or posted
                except (HttpError, ValueError, TypeError):
                    detail_errors += 1
                    # Leave the role unseen so a later successful run can still
                    # emit it as a newly verified posting.
                    continue
            merged = {**item, **detail}
            location = (merged.get("location") or {}).get("name", "")
            departments = merged.get("departments") or []
            department = " | ".join(str(x.get("name", "")) for x in departments if x.get("name"))
            jobs.append(
                Job(
                    company_id=company.id,
                    company=company.name,
                    source=self.type_name,
                    source_job_id=str(merged.get("id", "")),
                    title=str(merged.get("title", "")),
                    location=location,
                    description=strip_html(merged.get("content", "")),
                    source_url=str(merged.get("absolute_url", "")),
                    apply_url=str(merged.get("absolute_url", "")),
                    posted_at=posted,
                    posting_date_kind="first_published" if posted else "unknown",
                    posting_date_confidence="high" if posted else "unknown",
                    department=department,
                    raw=merged,
                )
            )
        warning = ""
        count_mismatch = payload.get("meta", {}).get("total") not in (None, len(items))
        if count_mismatch:
            warning = "Greenhouse meta.total differed from returned job count."
        if detail_errors:
            warning = " ".join(
                x for x in (warning, f"Left {detail_errors} failed detail candidate(s) unseen for retry.") if x
            )
        if detail_budget_skips:
            warning = " ".join(
                x for x in (warning, f"Left {detail_budget_skips} candidate(s) unseen after the detail budget was exhausted.") if x
            )
        return FetchResult(
            company_id=company.id,
            source=self.type_name,
            jobs=jobs,
            requests=client.request_count,
            warning=warning,
            cursor_complete=not (count_mismatch or detail_errors or detail_budget_skips),
        )
