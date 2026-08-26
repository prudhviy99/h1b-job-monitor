#!/usr/bin/env python3
"""Render a safe GitHub Actions summary and expose alert metadata."""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote, urlsplit


def markdown_text(value: Any, limit: int = 600) -> str:
    if isinstance(value, (list, tuple)):
        value = "; ".join(str(item) for item in value)
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit:
        text = text[: max(0, limit - 1)].rstrip() + "…"
    text = html.escape(text, quote=False)
    for character in "\\`*_{}[]()#+-.!|":
        text = text.replace(character, "\\" + character)
    return text.replace("@", "&#64;")


def safe_url(value: Any) -> str:
    raw = re.sub(r"[\x00-\x20\x7f]+", "", str(value or ""))[:2048]
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return ""
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    return quote(raw, safe=":/?#[]@!$&'()*+,;=%")


def load_report(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def load_last_error(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-120:]
    except OSError:
        return ""
    error_pattern = re.compile(r"error|exception|traceback|failed|denied|timed?\s*out", re.I)
    for line in reversed(lines):
        if error_pattern.search(line):
            return line.strip()
    return ""


def load_failures(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    failures = []
    for row in rows:
        status = row.get("status")
        enabled = str(row.get("enabled") or "").casefold() in {"1", "true", "yes"}
        if status == "ok" or (status == "skipped" and not enabled):
            continue
        failures.append(row)
    return failures


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as stream:
        stream.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--health", type=Path, required=True)
    parser.add_argument("--log", type=Path, default=Path("logs/monitor.log"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--monitor-outcome", default="success")
    parser.add_argument("--monitor-exit-code", default="")
    parser.add_argument("--step-outcome", action="append", default=[])
    args = parser.parse_args()

    report = load_report(args.report)
    metadata = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
    raw_jobs = report.get("jobs") if isinstance(report.get("jobs"), list) else []
    eligible_jobs = [
        job for job in raw_jobs
        if isinstance(job, dict) and job.get("apply_priority") in {"P0", "P1", "P2"}
    ]
    failures = load_failures(args.health)
    reported_status = str(metadata.get("status") or "")
    usable_partial = reported_status == "partial" and args.monitor_exit_code.strip() == "2"
    monitor_failed = not report or (
        args.monitor_outcome != "success" and not usable_partial
    )
    infrastructure_failures = []
    for outcome in args.step_outcome:
        name, separator, status = outcome.partition("=")
        if separator and status.strip().lower() in {"failure", "cancelled"}:
            infrastructure_failures.append(f"{name.strip()}: {status.strip().lower()}")
    jobs = [] if monitor_failed or infrastructure_failures else eligible_jobs
    reported_failures = int(metadata.get("companies_failed") or 0)
    should_alert = bool(jobs or failures or reported_failures or monitor_failed or infrastructure_failures)
    date = datetime.now(timezone.utc).date().isoformat()
    run_marker = re.sub(r"[^A-Za-z0-9_.:-]", "_", str(metadata.get("run_id") or ""))[:120]

    if monitor_failed or infrastructure_failures:
        title = f"H-1B monitor failed — {date}"
    elif failures or reported_failures:
        title = f"H-1B monitor source failure — {date}"
    else:
        count = len(jobs)
        title = f"H-1B monitor: {count} new match{'es' if count != 1 else ''} — {date}"

    lines = ["# H-1B job monitor", ""]
    if run_marker:
        lines.extend([f"<!-- h1b-monitor-run:{run_marker} -->", ""])
    if metadata:
        lines.extend([
            f"Run `{markdown_text(metadata.get('run_id'))}` · `{markdown_text(metadata.get('mode'))}`",
            "",
        ])
    if monitor_failed:
        lines.extend([
            "## Monitor failure",
            "",
            "The crawler process failed or did not produce a valid report. Open the workflow logs and uploaded artifact for details.",
            "",
        ])
        if args.monitor_exit_code == "124":
            lines.extend(["- Exact cause: crawler exceeded its 90-minute safety limit.", ""])
        else:
            fatal_detail = load_last_error(args.log)
            if fatal_detail:
                lines.extend([f"- Last logged error: {markdown_text(fatal_detail, limit=1000)}", ""])
    if infrastructure_failures:
        lines.extend(["## Workflow failures", ""])
        for failure in infrastructure_failures:
            lines.append(f"- {markdown_text(failure)}")
        lines.append("")
    if failures or reported_failures:
        lines.extend(["## Source failures", ""])
        if failures:
            for row in failures:
                detail = markdown_text(row.get("error") or row.get("warning") or "Unknown failure")
                lines.append(f"- **{markdown_text(row.get('company'))}** (`{markdown_text(row.get('source'))}`): {detail}")
        else:
            lines.append(f"- The run metadata reports {reported_failures} failed source(s); inspect the artifact for details.")
        lines.append("")
    if jobs:
        lines.extend([f"## {len(jobs)} new verified match{'es' if len(jobs) != 1 else ''}", ""])
        for job in jobs:
            priority = markdown_text(job.get("apply_priority"))
            company = markdown_text(job.get("company"))
            title_text = markdown_text(job.get("title"))
            apply_url = safe_url(job.get("apply_url") or job.get("source_url"))
            title_link = f"[{title_text}](<{apply_url}>)" if apply_url else title_text
            lines.extend([
                f"### {priority} — {company}: {title_link}",
                "",
                f"- **Location:** {markdown_text(job.get('location'))}",
                f"- **Why it matches:** {markdown_text(job.get('why_matches'))}",
                f"- **Sponsorship confidence:** {markdown_text(job.get('sponsorship_confidence'))}",
                f"- **Event:** {markdown_text(job.get('event_type'))}",
                "",
            ])
    elif not monitor_failed and not infrastructure_failures and not failures and not reported_failures:
        lines.extend(["No new verified matches and no enabled-source failures.", ""])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    write_output("should_alert", "true" if should_alert else "false")
    write_output("alert_title", title)
    count = len(jobs)
    write_output(
        "match_title",
        f"H-1B monitor: {count} new match{'es' if count != 1 else ''} — {date}",
    )
    if monitor_failed or infrastructure_failures or failures or reported_failures:
        alert_kind = "failure"
    elif jobs:
        alert_kind = "matches"
    else:
        alert_kind = "none"
    write_output("alert_kind", alert_kind)
    write_output("monitor_run_id", run_marker)
    write_output("new_matches", str(len(jobs)))
    write_output("source_failures", str(max(len(failures), reported_failures)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
