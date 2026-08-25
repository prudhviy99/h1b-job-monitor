from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

from .base import Connector, register
from ..http import HttpClient
from ..models import Company, FetchResult, Job
from ..util import parse_datetime, strip_html


@register
class AmazonConnector(Connector):
    type_name = "amazon"

    @staticmethod
    def _location(value: Any) -> str:
        if isinstance(value, str) and value.lstrip().startswith("{"):
            try:
                import json

                value = json.loads(value)
            except (TypeError, ValueError):
                pass
        if isinstance(value, dict):
            return str(
                value.get("normalizedLocation")
                or value.get("location")
                or value.get("locationNonStemming")
                or ""
            )
        return str(value or "")

    def fetch(self, company: Company, client: HttpClient, since, mode: str = "initial") -> FetchResult:
        config = company.connector
        endpoint = config.get("endpoint", "https://www.amazon.jobs/en/search.json")
        access = config.get("access_policy", "strict")
        keywords = config.get(
            "keywords",
            ["software engineer", "systems engineer", "security engineer", "site reliability"],
        )
        page_size = min(100, int(config.get("page_size", 100)))
        max_pages = int(config.get("max_pages_per_query", 3))
        client.reset_request_count()
        records: Dict[str, Dict[str, Any]] = {}
        warning_parts: List[str] = []
        pagination_incomplete = False
        for keyword in keywords:
            for page in range(max_pages):
                payload = client.get(
                    endpoint,
                    params={
                        "offset": page * page_size,
                        "result_limit": page_size,
                        "sort": "recent",
                        "category[]": "software-development",
                        "base_query": keyword,
                    },
                    access_policy=access,
                    use_cache=True,
                ).json()
                batch = payload.get("jobs", [])
                for item in batch:
                    key = str(item.get("id") or item.get("id_icims") or item.get("job_path", ""))
                    if key:
                        records[key] = item
                if len(batch) < page_size:
                    break
                last_posted = parse_datetime(batch[-1].get("posted_date")) if batch else None
                if last_posted and last_posted < since - timedelta(days=1):
                    break
            if batch and len(batch) == page_size and page + 1 >= max_pages:
                pagination_incomplete = True
                warning_parts.append(f"Query '{keyword}' reached max_pages_per_query={max_pages}.")

        jobs: List[Job] = []
        for key, item in records.items():
            if item.get("is_intern") or item.get("university_job") or item.get("is_manager"):
                continue
            country = str(item.get("country_code", ""))
            if country and country.upper() not in {"US", "USA"}:
                continue
            posted = parse_datetime(item.get("posted_date"))
            path = str(item.get("job_path", ""))
            source_url = path if path.startswith("http") else f"https://www.amazon.jobs{path}"
            description = " ".join(
                strip_html(item.get(field, ""))
                for field in ("description", "basic_qualifications", "preferred_qualifications")
            )
            locations = item.get("locations") or [item.get("location", "")]
            jobs.append(
                Job(
                    company_id=company.id,
                    company=company.name,
                    source=self.type_name,
                    source_job_id=key,
                    title=str(item.get("title", "")),
                    location=" | ".join(
                        dict.fromkeys(self._location(x) for x in locations if self._location(x))
                    ),
                    description=description,
                    source_url=source_url,
                    apply_url=str(item.get("url_next_step") or source_url),
                    posted_at=posted,
                    posting_date_kind="posted_date" if posted else "unknown",
                    posting_date_confidence="high" if posted else "unknown",
                    employment_type=str(item.get("job_schedule_type", "")),
                    department=str(item.get("job_category", "")),
                    raw=item,
                )
            )
        return FetchResult(
            company_id=company.id,
            source=self.type_name,
            jobs=jobs,
            requests=client.request_count,
            warning=" ".join(warning_parts),
            cursor_complete=not pagination_incomplete,
        )
