#!/usr/bin/env python3
"""Maintain one always-open, human-readable monitor status issue."""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

try:
    from .schedule_guard import PACIFIC, decide, expected_companies, parse_timestamp, read_history
    from .github_summary import markdown_text
except ImportError:
    from schedule_guard import PACIFIC, decide, expected_companies, parse_timestamp, read_history
    from github_summary import markdown_text


def local_time(value):
    timestamp = parse_timestamp(value)
    return timestamp.astimezone(PACIFIC).strftime("%Y-%m-%d %I:%M %p %Z") if timestamp else "Never"


def render_status(now, history, expected, repository, run_id, issues, failures, cache_key=""):
    decision = decide(now, history, expected)
    latest = history[0] if history else {}
    if issues or (latest and latest.get("status") != "success"):
        health = "needs attention"
    elif decision["window_complete"]:
        health = "healthy"
    elif decision["late_minutes"] > 90:
        health = "overdue"
    else:
        health = "crawl due"
    title = f"Job monitor status — {health} (Pacific time)"
    run_url = f"https://github.com/{repository}/actions/runs/{run_id}"
    previous = re.fullmatch(r"h1b-state-v2-(\d+)-\d+", cache_key)
    prior_url = f"https://github.com/{repository}/actions/runs/{previous.group(1)}" if previous else f"https://github.com/{repository}/actions"
    body = [
        "# Job monitor status", "",
        f"**{health.upper()}** · Last wake-up check: **{local_time(now.isoformat())}**", "",
        "This issue stays open. A wake-up check is not necessarily a job crawl.", "",
        f"- Current due window: **{decision['window_key']}**",
        f"- Window covered by a successful full crawl: **{'yes' if decision['window_complete'] else 'no'}**",
        f"- Latest actual crawl: **{local_time(latest.get('started_at'))}**",
        f"- Latest crawl outcome: **{markdown_text(latest.get('status') or 'none')}**",
        f"- Sources healthy in latest crawl: **{latest.get('companies_ok', 0)}/{latest.get('companies_total', expected)}**",
        f"- New matches in latest crawl: **{latest.get('emitted_jobs', 0)}**",
        f"- Next regular target: **{local_time(decision['next_target_at'])}**",
        f"- Cadence: {decision['reason']}",
        f"- [This wake-up/run]({run_url}) · [Restored state's workflow]({prior_url})",
        f"- [Job-match issues](https://github.com/{repository}/issues?q=is%3Aissue+label%3Ah1b-monitor-match)",
        "", "Targets are 7:17 AM and 7:17 PM Pacific. Half-hourly GitHub wake-ups are best-effort, not a timing guarantee.",
        "If this timestamp stops advancing, GitHub may not be delivering events; this same scheduler cannot alert while it is completely stopped.",
        "",
    ]
    if latest.get("status") == "success" and not latest.get("emitted_jobs"):
        body += ["The latest real crawl completed with **no new verified matches**. That is different from not running.", ""]
    if issues:
        body += ["## Workflow problems", ""] + [f"- {markdown_text(issue, 1200)}" for issue in issues] + [""]
    if failures:
        body += ["## Latest source problems", ""]
        for row in failures:
            body.append(f"- **{markdown_text(row['company_id'])}**: {markdown_text(row.get('error') or row.get('warning') or row['status'], 1200)}")
        body += ["", "Access-denied pages are not bypassed. Failed sources retain their cursor and are retried after a cooldown.", ""]
    body += ["## Recent actual crawls", "", "| Pacific start | Outcome | Healthy sources | New matches |", "|---|---|---|---|"]
    for row in history[:6]:
        body.append(f"| {local_time(row['started_at'])} | {markdown_text(row['status'])} | {row['companies_ok']}/{row['companies_total']} | {row['emitted_jobs']} |")
    body += ["", "Failure alerts close only after recovery. Job-match issues are never automatically closed.",
             "State cache and checked backups preserve seen-job deduplication; missing state blocks a crawl rather than resetting it.", ""]
    return title, "\n".join(body)


def publish(repository, title, body_path):
    def gh(*arguments):
        return subprocess.check_output(["gh", *arguments], text=True).strip()
    gh("label", "create", "h1b-monitor-status", "--repo", repository, "--color", "0E8A16",
       "--description", "Always-open monitor liveness, cadence, and source health", "--force")
    existing = json.loads(gh("issue", "list", "--repo", repository, "--state", "all",
                             "--label", "h1b-monitor-status", "--limit", "1", "--json", "number,state"))
    if existing:
        number = str(existing[0]["number"])
        gh("issue", "edit", number, "--repo", repository, "--title", title, "--body-file", str(body_path))
        if existing[0]["state"] == "CLOSED":
            gh("issue", "reopen", number, "--repo", repository)
        print(f"https://github.com/{repository}/issues/{number}")
    else:
        print(gh("issue", "create", "--repo", repository, "--title", title, "--body-file",
                 str(body_path), "--label", "h1b-monitor-status"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=Path("data/jobs.sqlite"))
    parser.add_argument("--companies", type=Path, default=Path("config/companies.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/monitor-status.md"))
    parser.add_argument("--step-outcome", action="append", default=[])
    parser.add_argument("--cache-key", default="")
    args = parser.parse_args()
    problems = [value for value in args.step_outcome if value.rsplit("=", 1)[-1] in {"failure", "cancelled"}]
    history, failures = [], []
    expected = expected_companies(args.companies)
    try:
        history = read_history(args.state)
        if history:
            with sqlite3.connect(args.state.resolve().as_uri() + "?mode=ro", uri=True) as connection:
                connection.row_factory = sqlite3.Row
                failures = [dict(row) for row in connection.execute(
                    "SELECT * FROM company_runs WHERE run_id=? AND status NOT IN ('ok','skipped')",
                    (history[0]["run_id"],),
                )]
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        problems.append(f"Persistent state unavailable: {exc}")
    title, body = render_status(
        datetime.now(timezone.utc), history, expected, os.environ["GITHUB_REPOSITORY"],
        os.environ["GITHUB_RUN_ID"], problems, failures, args.cache_key,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(body, encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
            stream.write(body)
    publish(os.environ["GITHUB_REPOSITORY"], title, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

