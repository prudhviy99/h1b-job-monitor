#!/usr/bin/env python3
"""Allow one completed crawl per Pacific morning/evening window."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple
from zoneinfo import ZoneInfo


PACIFIC = ZoneInfo("America/Los_Angeles")

# GitHub schedules these expressions in UTC. Each group includes both the PDT
# and PST primary/backup possibilities. The window check suppresses the
# seasonally early candidate and every candidate after a completed crawl.
MORNING_SCHEDULES = {
    "17 14 * * *",
    "17 15 * * *",
    "47 16 * * *",
    "47 17 * * *",
}
EVENING_SCHEDULES = {
    "17 2 * * *",
    "17 3 * * *",
    "47 4 * * *",
    "47 5 * * *",
}
RETIRED_TIMEZONE_SCHEDULES = {
    "17 7 * * *",
    "47 9 * * *",
    "17 19 * * *",
    "47 21 * * *",
}
REPORT_ARTIFACT_PREFIX = "h1b-job-report-"


def parse_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_schedule(schedule: str) -> str:
    return " ".join(schedule.split())


def schedule_kind(schedule: str) -> Optional[str]:
    normalized = normalize_schedule(schedule)
    if normalized in MORNING_SCHEDULES:
        return "morning"
    if normalized in EVENING_SCHEDULES:
        return "evening"
    return None


def nominal_scheduled_time(schedule: str, now: datetime) -> Optional[datetime]:
    """Return the most recent nominal daily UTC occurrence for a trigger."""
    fields = normalize_schedule(schedule).split()
    if len(fields) != 5 or not fields[0].isdigit() or not fields[1].isdigit():
        return None
    minute = int(fields[0])
    hour = int(fields[1])
    if not (0 <= minute <= 59 and 0 <= hour <= 23):
        return None
    utc_now = now.astimezone(timezone.utc)
    candidate = utc_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate > utc_now:
        candidate -= timedelta(days=1)
    return candidate


def local_datetime(day: date, value: time) -> datetime:
    return datetime.combine(day, value, tzinfo=PACIFIC).astimezone(timezone.utc)


def window_bounds(schedule: str, now: datetime) -> Optional[Tuple[datetime, datetime]]:
    """Resolve the logical Pacific window belonging to this UTC trigger."""
    kind = schedule_kind(schedule)
    nominal = nominal_scheduled_time(schedule, now)
    if kind is None or nominal is None:
        return None
    local_day = nominal.astimezone(PACIFIC).date()
    if kind == "morning":
        return (
            local_datetime(local_day, time(7, 0)),
            local_datetime(local_day, time(19, 0)),
        )
    return (
        local_datetime(local_day, time(19, 0)),
        local_datetime(local_day + timedelta(days=1), time(4, 0)),
    )


def cadence_decision(
    event_name: str,
    schedule: str,
    current_run_id: str,
    completed_crawls: Iterable[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> Tuple[bool, str]:
    if event_name != "schedule":
        return True, "Manual run: cadence guard allows the crawl."
    if normalize_schedule(schedule) in RETIRED_TIMEZONE_SCHEDULES:
        return False, "Retired timezone trigger arrived from GitHub's queue; skipping."
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    bounds = window_bounds(schedule, current_time)
    if bounds is None:
        return True, "Unknown schedule: cadence guard fails open and allows the crawl."
    start, end = bounds
    if current_time < start:
        return False, "Seasonal alternate trigger arrived before its Pacific window; skipping."
    if current_time >= end:
        return False, "Delayed trigger arrived after its Pacific window; skipping."
    for run in completed_crawls:
        if str(run.get("id") or "") == str(current_run_id):
            continue
        created_at = parse_timestamp(str(run.get("created_at") or ""))
        if created_at is not None and start <= created_at < end:
            return False, "This window already has a completed crawl; skipping the duplicate trigger."
    return True, "No completed crawl exists in this window; cadence guard allows the crawl."


def should_run(
    event_name: str,
    schedule: str,
    current_run_id: str,
    completed_crawls: Iterable[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> bool:
    return cadence_decision(
        event_name,
        schedule,
        current_run_id,
        completed_crawls,
        now,
    )[0]


def fetch_json(url: str, token: str) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "h1b-job-monitor-schedule-guard",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def has_report_artifact(payload: Dict[str, Any]) -> bool:
    return any(
        str(artifact.get("name") or "").startswith(REPORT_ARTIFACT_PREFIX)
        and not artifact.get("expired", False)
        for artifact in payload.get("artifacts") or []
    )


def fetch_completed_crawls(
    repository: str,
    token: str,
    since: datetime,
    current_run_id: str,
) -> Iterable[Dict[str, Any]]:
    """Return successful runs that actually uploaded a crawl report."""
    runs_url = (
        f"https://api.github.com/repos/{repository}/actions/workflows/"
        "job-monitor.yml/runs?status=success&per_page=50"
    )
    runs = fetch_json(runs_url, token).get("workflow_runs") or []
    completed = []
    for run in runs:
        run_id = str(run.get("id") or "")
        if not run_id or run_id == str(current_run_id):
            continue
        created_at = parse_timestamp(str(run.get("created_at") or ""))
        if created_at is None or created_at < since:
            continue
        artifacts_url = (
            f"https://api.github.com/repos/{repository}/actions/runs/"
            f"{run_id}/artifacts?per_page=100"
        )
        if has_report_artifact(fetch_json(artifacts_url, token)):
            completed.append(run)
    return completed


def write_output(path: str, should_execute: bool) -> None:
    with Path(path).open("a", encoding="utf-8") as stream:
        stream.write(f"should_run={'true' if should_execute else 'false'}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--schedule", default="")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.event_name != "schedule":
        execute, reason = cadence_decision(
            args.event_name,
            args.schedule,
            args.run_id,
            [],
        )
    elif normalize_schedule(args.schedule) in RETIRED_TIMEZONE_SCHEDULES:
        execute, reason = cadence_decision(
            args.event_name,
            args.schedule,
            args.run_id,
            [],
        )
    else:
        try:
            now = datetime.now(timezone.utc)
            bounds = window_bounds(args.schedule, now)
            since = bounds[0] if bounds else now - timedelta(days=2)
            crawls = fetch_completed_crawls(
                args.repository,
                os.environ["GH_TOKEN"],
                since,
                args.run_id,
            )
            execute, reason = cadence_decision(
                args.event_name,
                args.schedule,
                args.run_id,
                crawls,
                now,
            )
        except Exception as exc:
            # Missing a crawl is worse than a harmless state-deduplicated extra run.
            execute = True
            reason = f"Cadence lookup failed open: {type(exc).__name__}: {exc}"
    write_output(args.output, execute)
    print(reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
