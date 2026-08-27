#!/usr/bin/env python3
"""Allow one real crawl per morning/evening schedule window."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from zoneinfo import ZoneInfo


PACIFIC = ZoneInfo("America/Los_Angeles")
MORNING_HOURS = {7, 9}
EVENING_HOURS = {19, 21}


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


def schedule_hour(schedule: str) -> Optional[int]:
    fields = schedule.split()
    if len(fields) != 5 or not fields[1].isdigit():
        return None
    return int(fields[1])


def window_start(schedule: str, now: datetime) -> Optional[datetime]:
    hour = schedule_hour(schedule)
    if hour not in MORNING_HOURS | EVENING_HOURS:
        return None
    local_now = now.astimezone(PACIFIC)
    window_date = local_now.date()
    if hour in EVENING_HOURS and local_now.hour < 4:
        window_date -= timedelta(days=1)
    start_hour = 4 if hour in MORNING_HOURS else 16
    return datetime.combine(window_date, time(start_hour), tzinfo=PACIFIC).astimezone(
        timezone.utc
    )


def should_run(
    event_name: str,
    schedule: str,
    current_run_id: str,
    successful_runs: Iterable[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> bool:
    if event_name != "schedule":
        return True
    start = window_start(schedule, now or datetime.now(timezone.utc))
    if start is None:
        return True
    for run in successful_runs:
        if str(run.get("id") or "") == str(current_run_id):
            continue
        created_at = parse_timestamp(str(run.get("created_at") or ""))
        if created_at is not None and created_at >= start:
            return False
    return True


def fetch_successful_runs(repository: str, token: str) -> Iterable[Dict[str, Any]]:
    url = (
        f"https://api.github.com/repos/{repository}/actions/workflows/"
        "job-monitor.yml/runs?status=success&per_page=30"
    )
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
        payload = json.load(response)
    return payload.get("workflow_runs") or []


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
        write_output(args.output, True)
        print("Manual run: cadence guard allows the crawl.")
        return 0

    try:
        runs = fetch_successful_runs(args.repository, os.environ["GH_TOKEN"])
        execute = should_run(
            args.event_name,
            args.schedule,
            args.run_id,
            runs,
        )
    except Exception as exc:
        # Missing a crawl is worse than a harmless deduplicated extra run.
        print(f"Cadence lookup failed open: {type(exc).__name__}: {exc}")
        execute = True
    write_output(args.output, execute)
    print("Cadence guard allows the crawl." if execute else "This window already has a successful run; skipping the duplicate trigger.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
