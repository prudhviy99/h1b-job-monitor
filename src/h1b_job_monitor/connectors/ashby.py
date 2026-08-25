from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import urlsplit

from .base import Connector, register
from ..http import HttpClient
from ..models import Company, FetchResult, Job
from ..util import parse_datetime, strip_html


def _address_text(address: Any) -> str:
    if not isinstance(address, dict):
        return ""
    value = address.get("postalAddress", address)
    if not isinstance(value, dict):
        return ""
    bits = [value.get("addressLocality"), value.get("addressRegion"), value.get("addressCountry")]
    return ", ".join(str(x) for x in bits if x)


@register
class AshbyConnector(Connector):
    type_name = "ashby"

    def fetch(self, company: Company, client: HttpClient, since, mode: str = "initial") -> FetchResult:
        config = company.connector
        board = config["board_name"]
        base = config.get("api_base", "https://api.ashbyhq.com/posting-api/job-board")
        access = config.get("access_policy", "documented_public_api")
        client.reset_request_count()
        payload = client.get(
            f"{base.rstrip('/')}/{board}",
            params={"includeCompensation": str(config.get("include_compensation", False)).lower()},
            access_policy=access,
        ).json()
        jobs: List[Job] = []
        for item in payload.get("jobs", []):
            if item.get("isListed") is False:
                continue
            locations: List[str] = []
            if item.get("location"):
                locations.append(str(item["location"]))
            structured = _address_text(item.get("address"))
            if structured:
                locations.append(structured)
            for secondary in item.get("secondaryLocations") or []:
                if secondary.get("location"):
                    locations.append(str(secondary["location"]))
                secondary_address = _address_text(secondary.get("address"))
                if secondary_address:
                    locations.append(secondary_address)
            job_url = str(item.get("jobUrl", ""))
            source_id = urlsplit(job_url).path.rstrip("/").split("/")[-1] if job_url else ""
            posted = parse_datetime(item.get("publishedAt"))
            jobs.append(
                Job(
                    company_id=company.id,
                    company=company.name,
                    source=self.type_name,
                    source_job_id=source_id or job_url,
                    title=str(item.get("title", "")),
                    location=" | ".join(dict.fromkeys(x for x in locations if x)),
                    description=str(item.get("descriptionPlain") or strip_html(item.get("descriptionHtml", ""))),
                    source_url=job_url,
                    apply_url=str(item.get("applyUrl", "")),
                    posted_at=posted,
                    posting_date_kind="last_published" if posted else "unknown",
                    posting_date_confidence="high" if posted else "unknown",
                    employment_type=str(item.get("employmentType", "")),
                    department=" | ".join(str(item.get(key, "")) for key in ("department", "team") if item.get(key)),
                    workplace_type=str(item.get("workplaceType", "Remote" if item.get("isRemote") else "")),
                    raw=item,
                )
            )
        warning = "" if payload.get("apiVersion") in (None, "1", 1) else f"Unexpected Ashby apiVersion={payload.get('apiVersion')}"
        return FetchResult(
            company_id=company.id,
            source=self.type_name,
            jobs=jobs,
            requests=client.request_count,
            warning=warning,
        )
