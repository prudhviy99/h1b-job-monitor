from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

from .base import Connector, likely_detail_candidate, register
from ..http import HttpClient, HttpError
from ..models import Company, FetchResult, Job
from ..util import parse_datetime, strip_html


def _location(item: Dict[str, Any]) -> str:
    location = item.get("location") or {}
    if location.get("fullLocation"):
        return str(location["fullLocation"])
    bits = [location.get("city"), location.get("region"), location.get("country")]
    text = ", ".join(str(x) for x in bits if x)
    if location.get("remote"):
        text = f"Remote | {text}" if text else "Remote"
    return text


@register
class SmartRecruitersConnector(Connector):
    type_name = "smartrecruiters"

    def fetch(self, company: Company, client: HttpClient, since, mode: str = "initial") -> FetchResult:
        config = company.connector
        identifier = config["company_identifier"]
        base = config.get("api_base", "https://api.smartrecruiters.com/v1/companies")
        access = config.get("access_policy", "disabled")
        if access != "documented_public_api":
            return FetchResult(
                company_id=company.id,
                source=self.type_name,
                skipped=True,
                warning=(
                    "SmartRecruiters is disabled unless access_policy=documented_public_api is explicitly set; "
                    "its robots file conflicts with its public Posting API documentation."
                ),
            )
        list_url = f"{base.rstrip('/')}/{identifier}/postings"
        client.reset_request_count()
        page_size = 100
        max_pages = int(config.get("max_pages", 30))
        records: List[Dict[str, Any]] = []
        seen = set()
        offset = 0
        total = None
        for _ in range(max_pages):
            payload = client.get(
                list_url,
                params={"limit": page_size, "offset": offset},
                access_policy=access,
            ).json()
            batch = payload.get("content", [])
            if total is None:
                total = int(payload.get("totalFound", len(batch)))
            for item in batch:
                key = str(item.get("id", ""))
                if key and key not in seen:
                    seen.add(key)
                    records.append(item)
            if not batch or offset + len(batch) >= int(payload.get("totalFound", total or 0)):
                break
            offset += len(batch)
        warning = ""
        pagination_incomplete = bool(batch and offset + len(batch) < (total or 0))
        if pagination_incomplete:
            warning = f"SmartRecruiters pagination stopped before totalFound={total}."

        jobs: List[Job] = []
        detail_budget = int(config.get("max_detail_requests", 80))
        detail_errors = 0
        detail_budget_skips = 0
        for item in records:
            posted = parse_datetime(item.get("releasedDate"))
            relevant_recent = likely_detail_candidate(str(item.get("name", ""))) and (
                posted is None or posted >= since - timedelta(days=1)
            )
            detail: Dict[str, Any] = {}
            if relevant_recent:
                if detail_budget <= 0:
                    detail_budget_skips += 1
                    continue
                detail_budget -= 1
                try:
                    detail = client.get(
                        f"{list_url}/{item['id']}", access_policy=access
                    ).json()
                except (HttpError, ValueError, TypeError):
                    detail_errors += 1
                    continue
            merged = {**item, **detail}
            sections = ((merged.get("jobAd") or {}).get("sections") or {})
            description_parts: List[str] = []
            for key in (
                "companyDescription",
                "jobDescription",
                "qualifications",
                "additionalInformation",
            ):
                section = sections.get(key) or {}
                description_parts.append(strip_html(section.get("text", "")))
            location = _location(merged)
            loc = merged.get("location") or {}
            workplace = "Remote" if loc.get("remote") else ("Hybrid" if loc.get("hybrid") else "")
            jobs.append(
                Job(
                    company_id=company.id,
                    company=company.name,
                    source=self.type_name,
                    source_job_id=str(merged.get("id", "")),
                    title=str(merged.get("name", "")),
                    location=location,
                    description=" ".join(x for x in description_parts if x),
                    source_url=str(merged.get("postingUrl") or merged.get("ref", "")),
                    apply_url=str(merged.get("applyUrl", "")),
                    posted_at=posted,
                    posting_date_kind="releasedDate" if posted else "unknown",
                    posting_date_confidence="high" if posted else "unknown",
                    employment_type=str((merged.get("typeOfEmployment") or {}).get("label", "")),
                    department=" | ".join(
                        str((merged.get(key) or {}).get("label", ""))
                        for key in ("department", "function")
                        if (merged.get(key) or {}).get("label")
                    ),
                    workplace_type=workplace,
                    raw=merged,
                )
            )
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
            cursor_complete=not (pagination_incomplete or detail_errors or detail_budget_skips),
        )
