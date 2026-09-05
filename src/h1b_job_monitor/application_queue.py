"""A current application backlog, separate from deduplicated new-job alerts."""
from __future__ import annotations

import copy
import html
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlsplit

from .exporters import write_csv
from .models import Job
from .util import parse_datetime


def application_identity(job: Job) -> str:
    # Greenhouse can publish several location-specific posts for one vacancy.
    # Do not merge unrelated roles just because their titles happen to match.
    req = job.raw.get("internal_job_id") if job.source == "greenhouse" else None
    return f"{job.company_id}:requisition:{req}" if req else job.job_key or f"{job.company_id}:{job.source_job_id}"


def eligible_for_queue(job: Job, now: datetime, days: int) -> bool:
    if job.apply_priority not in {"P0", "P1", "P2"}:
        return False
    if job.posted_at and not now - timedelta(days=days) <= job.posted_at <= now + timedelta(hours=24):
        return False
    for field in ("validThrough", "application_deadline", "PostingEndDate"):
        deadline = parse_datetime(job.raw.get(field))
        # A date-only closing date remains open through that day.
        if deadline and deadline.date() < now.date():
            return False
    if job.raw.get("canApply") is False or job.raw.get("isListed") is False:
        return False
    return True


def select_queue(jobs: List[Job], now: datetime, days=30, daily_target=35, per_company=3):
    unique: Dict[str, Job] = {}
    for job in jobs:
        if not eligible_for_queue(job, now, days):
            continue
        key = application_identity(job)
        if key in unique:
            old = unique[key]
            if job.location not in old.location:
                old.location += " | " + job.location
            continue
        unique[key] = copy.deepcopy(job)
    ranked = sorted(unique.values(), key=lambda j: (
        j.posting_date_confidence not in {"high", "medium_high", "medium"},
        bool(j.posted_at and j.posted_at < now - timedelta(days=7)),
        {"P0": 0, "P1": 1, "P2": 2}[j.apply_priority],
        -j.match_score, -(j.posted_at.timestamp() if j.posted_at else 0), j.company,
    ))
    first, overflow, counts = [], [], Counter()
    for job in ranked:
        if len(first) < daily_target and counts[job.company_id] < per_company:
            first.append(job)
            counts[job.company_id] += 1
        else:
            overflow.append(job)
    return first + overflow


def _text(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _url(value: str) -> str:
    try:
        p = urlsplit(value)
        return value if p.scheme in {"https", "http"} and p.hostname and not p.username else ""
    except ValueError:
        return ""


def export_queue(output: Path, metadata: dict, jobs: List[Job], now: datetime, config: dict):
    days = int(config.get("lookback_days", 30))
    target = int(config.get("daily_target", 35))
    selected = select_queue(jobs, now, days, target, int(config.get("first_batch_per_company", 3)))
    queue_meta = {**metadata, "queue_jobs": len(selected), "queue_lookback_days": days,
                  "daily_target": target, "unverified_dates": sum(j.posting_date_confidence not in
                  {"high", "medium_high", "medium"} for j in selected)}
    output.mkdir(parents=True, exist_ok=True)
    (output / "application-queue.json").write_text(json.dumps({
        "metadata": queue_meta, "jobs": [j.to_dict() for j in selected]
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(output / "application-queue.csv", selected)
    cards = []
    for index, job in enumerate(selected, 1):
        verified_date = job.posting_date_confidence in {"high", "medium_high", "medium"}
        date = job.posted_at.strftime("%b %d, %Y") if job.posted_at and verified_date else "Posting age unverified"
        years = f"{job.extracted_min_years:g}+ years minimum" if job.extracted_min_years is not None else "Years not stated; review scope"
        cards.append(f'''<article data-priority="{_text(job.apply_priority)}" data-company="{_text(job.company)}">
<div class="tag">{index} · {_text(job.apply_priority)} · {_text(date)}</div>
<h2><a target="_blank" rel="noopener noreferrer" href="{_text(_url(job.apply_url or job.source_url))}">{_text(job.title)}</a></h2>
<p class="company">{_text(job.company)} · {_text(job.location)}</p>
<p>{_text(years)} · Match {job.match_score:g}/100 · Employer sponsorship evidence: {_text(job.sponsorship_confidence)}</p>
<p>{_text('; '.join(job.why_matches))}</p>
<details><summary>Sponsorship evidence and limits</summary><p>{_text(job.sponsorship_evidence)}</p>
<p>Employer filings do not confirm this individual role's transfer policy.</p></details>
</article>''')
    notice = ("Seen on an official feed or job page in this crawl. Roles can close afterward. "
              "This queue includes earlier alerts and unalerted backlog; check your application tracker before submitting. "
              "Missing or conflicting posting dates are labeled, never presented as newly posted. "
              "Application history is not stored in this public report.")
    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Application queue</title>
<style>body{{font:16px/1.55 system-ui;background:#f4f6f8;color:#17202a;margin:0}}main{{max-width:1050px;margin:auto;padding:28px 20px}}
h1{{margin-bottom:8px}}h2{{font-size:20px;margin:6px 0}}a{{color:#135db5}}article{{background:white;border:1px solid #dae0e8;border-radius:12px;padding:20px;margin:14px 0}}
.tag,.company{{color:#546378}}.notice{{background:#fff3cf;border-radius:10px;padding:16px}}input,select{{font:inherit;padding:10px;border:1px solid #bcc7d3;border-radius:6px;margin:8px}}details{{font-size:14px}}</style></head><body><main>
<h1>Application queue · {len(selected)} roles</h1><p>Checked {_text(now.isoformat())} · {_text(metadata['status'])} crawl · {metadata.get('companies_ok', 0)}/{metadata.get('companies_enabled', 0)} sources healthy</p>
<p class="notice">{_text(notice)}</p><p>Start with up to {target} roles. The first batch favors recent postings and limits repeated employers to {config.get('first_batch_per_company', 3)} each when supply allows. Extra roles follow.</p>
<input id="search" aria-label="Search companies and jobs" placeholder="Search company, title, technology…"><select id="priority" aria-label="Priority"><option value="">All priorities</option><option>P0</option><option>P1</option><option>P2</option></select>
<p id="count"></p>{''.join(cards) or '<p>No current roles cleared the profile gates.</p>'}
<script>function filter(){{const q=document.getElementById('search').value.toLowerCase();const p=document.getElementById('priority').value;let n=0;document.querySelectorAll('article').forEach(a=>{{a.hidden=!(a.textContent.toLowerCase().includes(q)&&(!p||a.dataset.priority===p));if(!a.hidden)n++;}});document.getElementById('count').textContent=n+' roles shown';}}document.getElementById('search').addEventListener('input',filter);document.getElementById('priority').addEventListener('change',filter);filter();</script>
</main></body></html>'''
    (output / "application-queue.html").write_text(document, encoding="utf-8")
    return queue_meta
