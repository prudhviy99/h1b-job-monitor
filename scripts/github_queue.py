#!/usr/bin/env python3
"""Publish the rolling queue without modifying new-job alerts or private tracking."""
import json
import os
import subprocess
from pathlib import Path

try:
    from .github_summary import markdown_text, safe_url, local_run_time
except ImportError:
    from github_summary import markdown_text, safe_url, local_run_time


def render_queue(payload, repository, run_id):
    meta, jobs = payload["metadata"], payload["jobs"]
    timestamp = local_run_time(meta).strftime("%Y-%m-%d %I:%M %p %Z")
    lines = ["# Application queue", "", f"Updated **{timestamp}** · **{len(jobs)} current matches**", "",
             f"Crawl: **{meta['status']}**, **{meta.get('companies_ok', 0)}/{meta['companies_enabled']}** sources healthy.", "",
             "This is a rolling backlog, including earlier alerts. Check your private application tracker before applying. "
             "A role appears here only when its official source was observed in this crawl; it can still close afterward. "
             "Employer sponsorship history is not a guarantee for the role. No application history is published here.", "",
             "Start with the first 35, using autofill and reviewing required answers before submitting. "
             "The ordering favors fresh jobs and employer variety. There is no guarantee of 35 suitable vacancies every day.", "",
             f"[Full searchable HTML, CSV and JSON: download this run's report artifact](https://github.com/{repository}/actions/runs/{run_id})", ""]
    for i, job in enumerate(jobs[:60], 1):
        url = safe_url(job.get("apply_url") or job.get("source_url"))
        if not url:
            continue
        date = str(job.get("posted_at") or "")[:10] if job.get("posting_date_confidence") in {"high", "medium_high", "medium"} else "age unverified"
        years = job.get("extracted_min_years")
        years = f"{years:g}+ years minimum" if years is not None else "years not stated"
        lines.extend([
            f"### {i}. {markdown_text(job['apply_priority'])} · {markdown_text(job['company'])}: [{markdown_text(job['title'])}](<{url}>)",
            f"{markdown_text(job['location'])} · {markdown_text(date)} · {markdown_text(years)} · employer sponsorship: {markdown_text(job['sponsorship_confidence'])}", "",
            markdown_text(job.get("why_matches"), 360), "",
        ])
    if len(jobs) > 60:
        lines.append(f"{len(jobs) - 60} additional matches are in the full report artifact.")
    if not jobs:
        lines.append("No current roles cleared the profile and queue-age gates in this crawl.")
    return "\n".join(lines)


def main():
    repository = os.environ["GITHUB_REPOSITORY"]
    run_id = os.environ["GITHUB_RUN_ID"]
    payload = json.loads(Path("reports/application-queue.json").read_text())
    path = Path("reports/application-queue.md")
    path.write_text(render_queue(payload, repository, run_id), encoding="utf-8")
    def gh(*args):
        return subprocess.check_output(["gh", *args, "--repo", repository], text=True).strip()
    label = "h1b-application-queue"
    gh("label", "create", label, "--color", "5319e7", "--description", "Rolling current job matches; not application history", "--force")
    found = json.loads(gh("issue", "list", "--state", "all", "--label", label, "--limit", "1", "--json", "number,state"))
    title = f"Application queue — {len(payload['jobs'])} current matches"
    if found:
        number = str(found[0]["number"])
        gh("issue", "edit", number, "--title", title, "--body-file", str(path))
        if found[0]["state"] == "CLOSED":
            gh("issue", "reopen", number)
    else:
        print(gh("issue", "create", "--title", title, "--body-file", str(path), "--label", label))


if __name__ == "__main__":
    main()
