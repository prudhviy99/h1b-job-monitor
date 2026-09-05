from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


UTC = timezone.utc


def parse_datetime(value: Any, now: Optional[datetime] = None) -> Optional[datetime]:
    if value is None or value == "":
        return None
    now = now or datetime.now(UTC)
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 10_000_000_000:
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (ValueError, OverflowError, OSError):
            return None

    text = str(value).strip()
    lowered = text.lower()
    if lowered in {"today", "posted today", "just posted"}:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if lowered in {"yesterday", "posted yesterday"}:
        return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    match = re.search(r"(?:posted\s+)?(\d+)\s+(hour|day|week|month)s?\s+ago", lowered)
    if match:
        count = int(match.group(1))
        unit = match.group(2)
        delta = {
            "hour": timedelta(hours=count),
            "day": timedelta(days=count),
            "week": timedelta(weeks=count),
            "month": timedelta(days=30 * count),
        }[unit]
        return now - delta

    normalized = text.replace("Z", "+00:00")
    # Some sitemaps emit more than ISO 8601's six microsecond digits. Preserve
    # timestamp ordering by truncating (not rounding) to Python's precision.
    normalized = re.sub(
        r"(\.\d{6})\d+(?=(?:[+-]\d{2}:\d{2})?$)",
        r"\1",
        normalized,
    )
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)
    except ValueError:
        pass
    # Some JobPosting feeds emit authoritative but non-zero-padded dates.
    calendar_match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if calendar_match:
        try:
            return datetime(*(int(part) for part in calendar_match.groups()), tzinfo=UTC)
        except ValueError:
            return None
    for fmt in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%a, %d %b %Y %H:%M:%S %z",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)
        except ValueError:
            continue
    return None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def strip_html(value: Any) -> str:
    if value is None:
        return ""
    # Greenhouse content is sometimes HTML-escaped twice. Decode before
    # parsing so tags do not survive as text and interrupt qualification rules.
    value = str(value)
    for _ in range(3):
        decoded = html.unescape(value)
        if decoded == value:
            break
        value = decoded
    parser = _TextExtractor()
    try:
        parser.feed(str(value))
        parser.close()
        return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    except Exception:
        return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(value)))).strip()


class _JsonLdExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_jsonld = False
        self.parts: List[str] = []
        self.blocks: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        if tag.lower() != "script":
            return
        attributes = {str(k).lower(): str(v).lower() for k, v in attrs if k and v}
        if "ld+json" in attributes.get("type", ""):
            self.in_jsonld = True
            self.parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self.in_jsonld:
            self.blocks.append("".join(self.parts).strip())
            self.in_jsonld = False
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.in_jsonld:
            self.parts.append(data)


def extract_jsonld(html_text: str) -> List[Dict[str, Any]]:
    parser = _JsonLdExtractor()
    parser.feed(html_text)
    parser.close()
    results: List[Dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            graph = value.get("@graph")
            if graph:
                visit(graph)
            kind = value.get("@type", "")
            kinds = kind if isinstance(kind, list) else [kind]
            if any(str(item).lower() == "jobposting" for item in kinds):
                results.append(value)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for block in parser.blocks:
        if not block:
            continue
        try:
            visit(json.loads(block))
        except json.JSONDecodeError:
            continue
    return results


def jsonld_location(value: Dict[str, Any]) -> str:
    locations = value.get("jobLocation") or value.get("applicantLocationRequirements") or []
    if not isinstance(locations, list):
        locations = [locations]
    rendered: List[str] = []
    for item in locations:
        if not isinstance(item, dict):
            continue
        address = item.get("address", item)
        if isinstance(address, str):
            rendered.append(address)
            continue
        if not isinstance(address, dict):
            continue
        bits = []
        for key in ("addressLocality", "addressRegion", "addressCountry"):
            bit = address.get(key)
            if isinstance(bit, dict):
                bit = bit.get("name") or bit.get("value") or bit.get("@id")
            bits.append(bit)
        text = ", ".join(str(bit) for bit in bits if bit)
        if text:
            rendered.append(text)
    remote = str(value.get("jobLocationType", "")).upper() == "TELECOMMUTE"
    if remote:
        rendered.insert(0, "Remote")
    return " | ".join(dict.fromkeys(rendered))


TRACKING_QUERY_KEYS = {
    "gh_jid",
    "gh_src",
    "lever-source",
    "source",
    "src",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def canonical_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    path = re.sub(r"/+", "/", parts.path).rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(sorted(query)), ""))


def stable_job_key(company_id: str, source_job_id: str, url: str, title: str, location: str) -> str:
    identity = source_job_id.strip() or canonical_url(url) or f"{title.lower()}|{location.lower()}"
    return hashlib.sha256(f"{company_id}|{identity}".encode("utf-8")).hexdigest()


def content_hash(parts: Iterable[str]) -> str:
    normalized = "|".join(re.sub(r"\s+", " ", str(item)).strip().lower() for item in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def coalesce(*values: Any, default: Any = "") -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return default
