from __future__ import annotations

import csv
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .models import Company, FetchResult, Job


REPORT_FIELDS = [
    "company",
    "title",
    "location",
    "posted_at",
    "posting_date_kind",
    "posting_date_confidence",
    "source_url",
    "apply_url",
    "discovered_at",
    "event_type",
    "sponsorship_confidence",
    "sponsorship_score",
    "sponsorship_evidence",
    "role_sponsorship_signal",
    "match_score",
    "why_matches",
    "apply_priority",
    "extracted_min_years",
    "source",
    "source_job_id",
]


def _rows(jobs: Iterable[Job]) -> List[Dict[str, Any]]:
    rows = []
    for job in jobs:
        value = job.to_dict()
        rows.append({key: value.get(key, "") for key in REPORT_FIELDS})
    return rows


def write_csv(path: Path, jobs: Iterable[Job]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        writer.writerows(_rows(jobs))


def write_rejections(path: Path, jobs: Iterable[Job]) -> None:
    fields = [
        "company", "title", "location", "posted_at", "source_url", "match_score",
        "sponsorship_score", "rejection_reasons", "source", "source_job_id"
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for job in jobs:
            value = job.to_dict()
            writer.writerow({key: value.get(key, "") for key in fields})


def write_json(path: Path, metadata: Dict[str, Any], jobs: Iterable[Job]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"metadata": metadata, "jobs": [job.to_dict() for job in jobs]}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _age(posted: Any, now: datetime) -> str:
    if posted is None:
        return "date unavailable"
    delta = max(0.0, (now - posted).total_seconds() / 86400)
    if delta < 1:
        return f"{max(1, round(delta * 24))}h old"
    return f"{delta:.1f}d old"


def write_markdown(path: Path, metadata: Dict[str, Any], jobs: List[Job], now: datetime) -> None:
    lines = [
        "# Verified H-1B job matches",
        "",
        f"Run: `{metadata['run_id']}` | Mode: **{metadata['mode']}** | Generated: {now.isoformat()}",
        "",
        (
            f"Found **{len(jobs)}** new/reposted roles after official-source, date, US-location, "
            "seniority, experience, relevance, and sponsorship-confidence gates."
        ),
        "",
        "> Employer LCA history is evidence, not a guarantee that a particular team will transfer an H-1B. Confirm before investing in a long application.",
        "",
    ]
    if not jobs:
        lines.extend([
            "No roles cleared every conservative gate in this run.",
            "",
            "Check `company_health.csv` for sources that failed or were intentionally disabled.",
        ])
    for priority in ("P0", "P1", "P2"):
        selected = [job for job in jobs if job.apply_priority == priority]
        if not selected:
            continue
        label = {"P0": "Apply immediately", "P1": "Strong match", "P2": "Worth reviewing"}[priority]
        lines.extend([f"## {priority} - {label}", ""])
        for job in selected:
            why = "; ".join(job.why_matches)
            lines.extend([
                f"### [{job.company} - {job.title}]({job.source_url})",
                "",
                f"- **Location:** {job.location}",
                f"- **Freshness:** {_age(job.posted_at, now)} ({job.posting_date_kind}, {job.posting_date_confidence})",
                f"- **Match:** {job.match_score:.1f}/100 - {why}",
                f"- **Sponsorship:** {job.sponsorship_confidence} ({job.sponsorship_score:.2f}); {job.role_sponsorship_signal}",
                f"- **Evidence:** {job.sponsorship_evidence}",
                f"- **Event:** {job.event_type}",
                f"- **Apply:** {job.apply_url or job.source_url}",
                "",
            ])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_html(path: Path, title: str, metadata: Dict[str, Any], jobs: List[Job], now: datetime) -> None:
    cards = []
    for job in jobs:
        why = "; ".join(job.why_matches)
        cards.append(f"""
        <article class="card {html.escape(job.apply_priority.lower())}">
          <div class="top"><span class="priority">{html.escape(job.apply_priority)}</span><span>{html.escape(_age(job.posted_at, now))}</span></div>
          <h2><a href="{html.escape(job.source_url, quote=True)}">{html.escape(job.title)}</a></h2>
          <div class="company">{html.escape(job.company)} · {html.escape(job.location)}</div>
          <div class="scores"><span>Match {job.match_score:.1f}</span><span>Sponsorship {job.sponsorship_score:.2f}</span><span>{html.escape(job.event_type)}</span></div>
          <p>{html.escape(why)}</p>
          <p class="evidence">{html.escape(job.sponsorship_evidence)}</p>
          <a class="apply" href="{html.escape(job.apply_url or job.source_url, quote=True)}">Open official application</a>
        </article>""")
    empty = "<div class='empty'>No roles cleared every conservative gate in this run.</div>" if not cards else ""
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{--ink:#17202a;--muted:#5b6673;--bg:#f5f7fa;--card:#fff;--line:#dfe5eb;--p0:#b42318;--p1:#175cd3;--p2:#337f49}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
main{{max-width:1000px;margin:0 auto;padding:36px 20px 60px}}h1{{margin:0 0 6px;font-size:30px}}.meta{{color:var(--muted);margin-bottom:20px}}
.notice{{background:#fff7e6;border:1px solid #f3d39b;border-radius:10px;padding:12px 15px;margin:18px 0 24px}}
.grid{{display:grid;gap:14px}}.card{{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--p2);border-radius:12px;padding:18px;box-shadow:0 2px 8px #1018280d}}
.card.p0{{border-left-color:var(--p0)}}.card.p1{{border-left-color:var(--p1)}}.top,.scores{{display:flex;gap:10px;justify-content:space-between;color:var(--muted);font-size:13px}}
.priority{{font-weight:800;color:var(--ink)}}h2{{font-size:20px;margin:8px 0 2px}}a{{color:#175cd3}}.company{{color:var(--muted)}}.scores{{justify-content:flex-start;margin:12px 0}}.scores span{{background:#eef2f6;border-radius:999px;padding:3px 8px}}
.evidence{{font-size:13px;color:var(--muted)}}.apply{{display:inline-block;margin-top:5px;font-weight:700}}.empty{{padding:30px;background:#fff;border:1px solid var(--line);border-radius:12px}}
</style></head><body><main><h1>{html.escape(title)}</h1>
<div class="meta">{html.escape(metadata['mode'])} run · {html.escape(now.isoformat())} · {len(jobs)} emitted role(s)</div>
<div class="notice">Recent employer filings increase confidence, but do not guarantee that this requisition or team will transfer an H-1B. A posting-level “no sponsorship” statement always wins.</div>
<section class="grid">{''.join(cards)}{empty}</section></main></body></html>"""
    path.write_text(document, encoding="utf-8")


def write_company_health(path: Path, results: List[FetchResult], company_map: Dict[str, Company]) -> None:
    fields = [
        "company", "company_id", "enabled", "source", "status", "jobs_fetched", "requests",
        "warning", "error", "careers_url", "sponsorship_confidence"
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for result in sorted(results, key=lambda x: company_map[x.company_id].name):
            company = company_map[result.company_id]
            status = (
                "skipped" if result.skipped
                else ("error" if result.error else ("degraded" if not result.cursor_complete else "ok"))
            )
            writer.writerow({
                "company": company.name,
                "company_id": company.id,
                "enabled": company.enabled,
                "source": result.source,
                "status": status,
                "jobs_fetched": len(result.jobs),
                "requests": result.requests,
                "warning": result.warning,
                "error": result.error,
                "careers_url": company.careers_url,
                "sponsorship_confidence": company.sponsorship.confidence,
            })


def export_run(
    output_dir: Path,
    metadata: Dict[str, Any],
    emitted: List[Job],
    rejected: List[Job],
    results: List[FetchResult],
    company_map: Dict[str, Company],
    title: str,
    now: datetime,
    include_rejections: bool = True,
    max_rejections_per_company: int = 50,
) -> Path:
    run_dir = output_dir / "runs" / metadata["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    emitted.sort(key=lambda job: ({"P0": 0, "P1": 1, "P2": 2}.get(job.apply_priority, 9), -job.match_score, job.company))
    write_csv(run_dir / "matches.csv", emitted)
    write_json(run_dir / "matches.json", metadata, emitted)
    write_markdown(run_dir / "daily_report.md", metadata, emitted, now)
    write_html(run_dir / "daily_report.html", title, metadata, emitted, now)
    rejection_rows: List[Job] = []
    if include_rejections:
        per_company: Dict[str, int] = {}
        for job in rejected:
            count = per_company.get(job.company_id, 0)
            if count >= max(0, max_rejections_per_company):
                continue
            rejection_rows.append(job)
            per_company[job.company_id] = count + 1
    write_rejections(run_dir / "rejections_audit.csv", rejection_rows)
    write_company_health(run_dir / "company_health.csv", results, company_map)

    # Stable latest files are intentionally rewritten after a successful report export.
    write_csv(output_dir / "latest.csv", emitted)
    write_json(output_dir / "latest.json", metadata, emitted)
    write_markdown(output_dir / "latest.md", metadata, emitted, now)
    write_html(output_dir / "latest.html", title, metadata, emitted, now)
    write_company_health(output_dir / "company_health.csv", results, company_map)
    return run_dir
