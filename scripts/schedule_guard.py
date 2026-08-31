#!/usr/bin/env python3
"""Decide whether a real crawl is due from Pacific wall time and durable state."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")
RETRY_MINUTES = 60
MAX_ATTEMPTS_PER_WINDOW = 3


def parse_timestamp(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def expected_companies(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    companies = value["companies"] if isinstance(value, dict) else value
    count = sum(bool(company.get("enabled")) for company in companies)
    if not count:
        raise ValueError("No enabled companies; refusing to declare the monitor healthy.")
    return count


def read_history(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise RuntimeError("Persistent state is missing; recover it before crawling.")
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT 500"
        )]


def current_window(now):
    """A delayed wake-up serves the window due NOW, regardless of its cron text."""
    local = now.astimezone(PACIFIC)
    day = local.date()
    morning = datetime.combine(day, time(7, 17), PACIFIC)
    evening = datetime.combine(day, time(19, 17), PACIFIC)
    if local >= evening:
        start, end, kind = evening, datetime.combine(day + timedelta(days=1), time(7, 17), PACIFIC), "evening"
    elif local >= morning:
        start, end, kind = morning, evening, "morning"
    else:
        start, end, kind = datetime.combine(day - timedelta(days=1), time(19, 17), PACIFIC), morning, "evening"
    return {
        "window_key": f"{start.date().isoformat()}-{kind}",
        "target_at": start.astimezone(timezone.utc).isoformat(),
        "next_target_at": end.astimezone(timezone.utc).isoformat(),
    }


def is_full_success(row, expected):
    return (
        row.get("status") == "success" and bool(row.get("finished_at"))
        and int(row.get("companies_total") or 0) == expected
        and int(row.get("companies_ok") or 0) == expected
        and int(row.get("companies_failed") or 0) == 0
    )


def decide(now, history, expected, force=False):
    now = now.astimezone(timezone.utc)
    result = current_window(now)
    start = parse_timestamp(result["target_at"])
    end = parse_timestamp(result["next_target_at"])
    # A subset-only diagnostic crawl cannot satisfy the whole company universe.
    attempts = [
        row for row in history
        if start <= parse_timestamp(row["started_at"]) < end
        and int(row.get("companies_total") or 0) == expected
    ]
    attempts.sort(key=lambda row: parse_timestamp(row["started_at"]), reverse=True)
    covered = any(is_full_success(row, expected) for row in attempts)
    result.update(
        checked_at=now.isoformat(), window_complete=covered,
        attempts=len(attempts), late_minutes=max(0, int((now - start).total_seconds() / 60)),
        should_run=False,
    )
    if force:
        result.update(should_run=True, reason="Explicit forced crawl requested; job deduplication remains enabled.")
    elif covered:
        result["reason"] = "Current window already has a successful full crawl; no additional crawl needed."
    elif len(attempts) >= MAX_ATTEMPTS_PER_WINDOW:
        result["reason"] = "Retry limit reached for this window; source failures remain visible. Next window will retry."
    elif attempts and now < parse_timestamp(attempts[0].get("finished_at") or attempts[0]["started_at"]) + timedelta(minutes=RETRY_MINUTES):
        retry_at = parse_timestamp(attempts[0].get("finished_at") or attempts[0]["started_at"]) + timedelta(minutes=RETRY_MINUTES)
        result.update(retry_at=retry_at.isoformat(), reason="Previous crawl was incomplete; waiting for the one-hour recovery cooldown.")
    else:
        result.update(should_run=True, reason="No successful full crawl in the current window; running catch-up now.")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=Path("data/jobs.sqlite"))
    parser.add_argument("--companies", type=Path, default=Path("config/companies.json"))
    parser.add_argument("--event-name", default="schedule")
    parser.add_argument("--schedule", default="")
    parser.add_argument("--force", choices=("true", "false"), default="false")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, default=Path("reports/cadence.json"))
    args = parser.parse_args()
    history = read_history(args.state)
    decision = decide(datetime.now(timezone.utc), history, expected_companies(args.companies), args.force == "true")
    decision.update(event_name=args.event_name, trigger_expression=args.schedule)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
    with args.output.open("a", encoding="utf-8") as stream:
        stream.write(f"should_run={str(decision['should_run']).lower()}\n")
        stream.write(f"window_key={decision['window_key']}\n")
    print(json.dumps(decision, indent=2))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write(f"## Cadence check: {decision['window_key']}\n\n{decision['reason']}\n\n")
            stream.write("This is a wake-up check, not evidence that a crawl ran. See the always-open monitor status issue.\n\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
