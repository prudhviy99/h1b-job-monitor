from __future__ import annotations

import email.utils
import http.client as http_client
import json
import logging
import random
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .state import StateStore


LOGGER = logging.getLogger(__name__)


def _ascii_request_url(url: str) -> str:
    """Percent-encode Unicode path/query characters for urllib's HTTP layer."""
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname.encode("idna").decode("ascii") if parts.hostname else ""
    if parts.port:
        host = f"{host}:{parts.port}"
    if parts.username:
        credentials = urllib.parse.quote(parts.username, safe="")
        if parts.password:
            credentials += ":" + urllib.parse.quote(parts.password, safe="")
        host = f"{credentials}@{host}"
    path = urllib.parse.quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
    query = urllib.parse.quote(parts.query, safe="=&?/%:@!$'()*+,;[]-._~")
    return urllib.parse.urlunsplit((parts.scheme, host, path, query, ""))


class HttpError(RuntimeError):
    pass


class RobotsDenied(HttpError):
    pass


class _RobotsRules:
    """Small RFC-9309-style Allow/Disallow evaluator.

    Python 3.9's ``urllib.robotparser`` uses first-match behavior and therefore
    incorrectly denies common rules such as ``Disallow: /`` followed by the
    more-specific ``Allow: /careers``.  The REP requires the longest matching
    rule, with Allow winning ties.
    """

    def __init__(self, text: str) -> None:
        self.groups: List[Tuple[List[str], List[Tuple[bool, str]]]] = []
        agents: List[str] = []
        rules: List[Tuple[bool, str]] = []
        saw_rule = False
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            field, value = (part.strip() for part in line.split(":", 1))
            field = field.casefold()
            if field == "user-agent":
                if saw_rule and agents:
                    self.groups.append((agents, rules))
                    agents, rules, saw_rule = [], [], False
                if value:
                    agents.append(value.casefold())
            elif field in {"allow", "disallow"} and agents:
                saw_rule = True
                # An empty Disallow is the REP's way of declaring no restriction.
                if value:
                    rules.append((field == "allow", value))
        if agents:
            self.groups.append((agents, rules))

    @staticmethod
    def _matches(pattern: str, target: str) -> bool:
        anchored = pattern.endswith("$")
        if anchored:
            pattern = pattern[:-1]
        expression = re.escape(pattern).replace(r"\*", ".*")
        return re.match("^" + expression + ("$" if anchored else ""), target) is not None

    def can_fetch(self, user_agent: str, url: str) -> bool:
        product = user_agent.split()[0].split("/", 1)[0].casefold()
        matches: List[Tuple[int, List[Tuple[bool, str]]]] = []
        for agents, rules in self.groups:
            specificities = [len(agent) for agent in agents if agent != "*" and agent in product]
            if specificities:
                matches.append((max(specificities), rules))
            elif "*" in agents:
                matches.append((0, rules))
        if not matches:
            return True
        best_group = max(specificity for specificity, _ in matches)
        selected_rules = [rule for specificity, rules in matches if specificity == best_group for rule in rules]
        parsed = urllib.parse.urlsplit(url)
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        matching = [
            (len(pattern.rstrip("$")), allowed)
            for allowed, pattern in selected_rules
            if self._matches(pattern, target)
        ]
        if not matching:
            return True
        longest = max(length for length, _ in matching)
        return any(allowed for length, allowed in matching if length == longest)


@dataclass
class HttpResponse:
    url: str
    status: int
    headers: Dict[str, str]
    body: bytes
    from_cache: bool = False

    @property
    def text(self) -> str:
        content_type = self.headers.get("content-type", "")
        encoding = "utf-8"
        if "charset=" in content_type:
            encoding = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
        return self.body.decode(encoding, errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)


class HostRateLimiter:
    def __init__(self, min_interval_seconds: float) -> None:
        self.min_interval = max(0.0, min_interval_seconds)
        self._last: Dict[str, float] = {}
        self._host_intervals: Dict[str, float] = {}
        self._lock = threading.Lock()

    def set_host_interval(self, url: str, seconds: float) -> None:
        """Raise (never lower) the request interval for one reviewed host."""
        host = urllib.parse.urlsplit(url).netloc.lower()
        with self._lock:
            self._host_intervals[host] = max(
                self._host_intervals.get(host, self.min_interval),
                max(0.0, seconds),
            )

    def wait(self, url: str) -> None:
        host = urllib.parse.urlsplit(url).netloc.lower()
        while True:
            with self._lock:
                now = time.monotonic()
                interval = self._host_intervals.get(host, self.min_interval)
                wait_for = interval - (now - self._last.get(host, 0.0))
                if wait_for <= 0:
                    self._last[host] = now
                    return
            time.sleep(min(wait_for, 0.25))


class RobotsGate:
    """Caches robots rules. A fetch failure is recorded as unknown, not as permission."""

    def __init__(self, user_agent: str, limiter: HostRateLimiter, timeout: float = 15.0) -> None:
        self.user_agent = user_agent
        self.limiter = limiter
        self.timeout = timeout
        self._cache: Dict[str, Optional[_RobotsRules]] = {}
        self._lock = threading.Lock()

    def _origin(self, url: str) -> str:
        parts = urllib.parse.urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"

    def allowed(self, url: str, policy: str = "strict") -> Tuple[bool, str]:
        if policy == "documented_public_api":
            return True, "documented public ATS API; explicit narrow API exception"
        if policy == "disabled":
            return False, "source disabled by access policy"

        origin = self._origin(url)
        with self._lock:
            known = origin in self._cache
            parser = self._cache.get(origin)
        if not known:
            robots_url = f"{origin}/robots.txt"
            try:
                self.limiter.wait(robots_url)
                request = urllib.request.Request(
                    robots_url,
                    headers={"User-Agent": self.user_agent, "Accept": "text/plain,*/*;q=0.1"},
                )
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    text = response.read(1_000_000).decode("utf-8", errors="replace")
                parser = _RobotsRules(text)
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    parser = _RobotsRules("User-agent: *\nDisallow: /")
                elif exc.code == 404:
                    parser = _RobotsRules("User-agent: *\nDisallow:")
                else:
                    parser = None
            except Exception as exc:
                LOGGER.warning("Could not retrieve robots.txt for %s: %s", origin, exc)
                parser = None
            with self._lock:
                self._cache[origin] = parser

        if parser is None:
            return False, "robots.txt unavailable; strict policy skipped source"
        allowed = parser.can_fetch(self.user_agent, url)
        return allowed, "allowed by robots.txt" if allowed else "disallowed by robots.txt"


class HttpClient:
    RETRYABLE = {408, 425, 429, 500, 502, 503, 504}

    def __init__(
        self,
        state: StateStore,
        user_agent: str,
        timeout_seconds: float = 25.0,
        min_interval_seconds: float = 0.8,
        max_retries: int = 3,
        max_response_bytes: int = 15_000_000,
    ) -> None:
        self.state = state
        self.user_agent = user_agent
        self.timeout = timeout_seconds
        self.max_retries = max_retries
        self.max_response_bytes = max_response_bytes
        self.limiter = HostRateLimiter(min_interval_seconds)
        self.robots = RobotsGate(user_agent, self.limiter, timeout_seconds)
        self._local = threading.local()

    @property
    def request_count(self) -> int:
        return getattr(self._local, "request_count", 0)

    def reset_request_count(self) -> None:
        self._local.request_count = 0

    def _increment(self) -> None:
        self._local.request_count = self.request_count + 1

    def get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        access_policy: str = "strict",
        use_cache: bool = True,
    ) -> HttpResponse:
        if params:
            pairs = [(key, item) for key, value in params.items() for item in (value if isinstance(value, list) else [value])]
            separator = "&" if urllib.parse.urlsplit(url).query else "?"
            url = f"{url}{separator}{urllib.parse.urlencode(pairs)}"
        return self._request(
            "GET", url, None, headers or {}, access_policy=access_policy, use_cache=use_cache
        )

    def post_json(
        self,
        url: str,
        payload: Dict[str, Any],
        *,
        headers: Optional[Dict[str, str]] = None,
        access_policy: str = "strict",
    ) -> HttpResponse:
        merged = {"Content-Type": "application/json", **(headers or {})}
        return self._request(
            "POST",
            url,
            json.dumps(payload).encode("utf-8"),
            merged,
            access_policy=access_policy,
            use_cache=False,
        )

    def _request(
        self,
        method: str,
        url: str,
        data: Optional[bytes],
        headers: Dict[str, str],
        *,
        access_policy: str,
        use_cache: bool,
    ) -> HttpResponse:
        url = _ascii_request_url(url)
        allowed, reason = self.robots.allowed(url, access_policy)
        if not allowed:
            raise RobotsDenied(f"{reason}: {url}")

        cached = self.state.get_http_cache(url) if method == "GET" and use_cache else None
        request_headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
            **headers,
        }
        if cached:
            if cached.get("etag"):
                request_headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                request_headers["If-Modified-Since"] = cached["last_modified"]

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                self.limiter.wait(url)
                request = urllib.request.Request(url, data=data, method=method, headers=request_headers)
                self._increment()
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read(self.max_response_bytes + 1)
                    if len(body) > self.max_response_bytes:
                        raise HttpError(f"Response exceeded {self.max_response_bytes} bytes: {url}")
                    response_headers = {key.lower(): value for key, value in response.headers.items()}
                    result = HttpResponse(
                        url=response.geturl(),
                        status=response.status,
                        headers=response_headers,
                        body=body,
                    )
                    if method == "GET" and use_cache and response.status == 200:
                        self.state.put_http_cache(
                            url,
                            body,
                            response.status,
                            response_headers.get("etag"),
                            response_headers.get("last-modified"),
                        )
                    return result
            except urllib.error.HTTPError as exc:
                if exc.code == 304 and cached:
                    return HttpResponse(
                        url=url,
                        status=200,
                        headers={},
                        body=cached["body"],
                        from_cache=True,
                    )
                last_error = exc
                if exc.code not in self.RETRYABLE or attempt >= self.max_retries:
                    detail = exc.read(2_000).decode("utf-8", errors="replace") if exc.fp else ""
                    raise HttpError(f"HTTP {exc.code} for {url}: {detail[:300]}") from exc
                delay = self._retry_delay(attempt, exc.headers.get("Retry-After"))
                LOGGER.warning("HTTP %s for %s; retrying in %.1fs", exc.code, url, delay)
                time.sleep(delay)
            except (urllib.error.URLError, TimeoutError, OSError, http_client.HTTPException) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                delay = self._retry_delay(attempt, None)
                LOGGER.warning("Request failed for %s: %s; retrying in %.1fs", url, exc, delay)
                time.sleep(delay)
        raise HttpError(f"Request failed after retries for {url}: {last_error}")

    @staticmethod
    def _retry_delay(attempt: int, retry_after: Optional[str]) -> float:
        if retry_after:
            try:
                return min(120.0, max(0.0, float(retry_after)))
            except ValueError:
                try:
                    target = email.utils.parsedate_to_datetime(retry_after)
                    return min(120.0, max(0.0, (target - datetime.now(timezone.utc)).total_seconds()))
                except Exception:
                    pass
        return min(30.0, (2 ** attempt) + random.uniform(0.1, 0.8))
