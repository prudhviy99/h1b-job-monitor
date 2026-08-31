# H-1B-friendly software job monitor

This project discovers newly posted US software-engineering roles from official employer career sources, then applies conservative gates for the candidate's current background: Capital One Java/Spring Boot and Python/FastAPI services; AWS Shield, backend and distributed systems, Kinesis telemetry, DynamoDB/RDS, multi-region infrastructure, security, and SRE/operations; plus project-backed WebFlux/Redis/NGINX and AI incident-triage experience. The profile represents roughly 3.75 years of relevant US experience as of August 2026.

It is deliberately not a LinkedIn scraper, job aggregator, auto-apply tool, or claim that a company will sponsor every role.

## What is included

- A quality-screened universe of **149 direct employers**, with official career URLs, legal-employer matching, recent DOL LCA evidence, confidence, filing counts, role-fit tags, and caveats.
- **63 enabled official sources** (34 Greenhouse, 16 reviewed sitemap/JSON-LD feeds, 7 Ashby, 3 SmartRecruiters, 2 Lever, and Amazon Jobs); 86 additional employers remain visible as conservative research-only coverage.
- Read-only connectors for Greenhouse, Lever, Ashby, SmartRecruiters, Amazon Jobs, Workday (disabled until explicit per-tenant access approval), sitemap + `JobPosting` JSON-LD, and fixed JSON-LD page sets.
- Exact first-run semantics: only matches with a supported posting date from the previous seven days.
- Incremental semantics: only unseen stable IDs or verified reposts whose posting date advanced; content-only edits are not emitted as new jobs.
- SQLite persistence, cross-run deduplication, HTTP ETag/Last-Modified caching, rate limiting, retries with backoff, robots checks, response-size limits, source health, and graceful per-company failure handling.
- Configurable title, seniority, years-of-experience, role-family, skill, location, sponsorship, and freshness ranking.
- CSV, JSON, Markdown, and a readable HTML report.
- macOS `launchd`, cron, and GitHub Actions scheduler options. None is silently activated by the files alone.

## Quick start

Python 3.9 or newer is enough; the monitor has no third-party runtime dependencies.

```bash
cd /absolute/path/to/h1b-job-monitor
PYTHONPATH=src python3 -m h1b_job_monitor validate-config
PYTHONPATH=src python3 -m h1b_job_monitor crawl --mode auto
```

Open `reports/latest.html`, or use `reports/latest.csv` / `reports/latest.json` in another workflow.

`--mode auto` uses `initial` when no usable run exists and `incremental` afterward. Each employer advances from its own last complete source run, so an outage cannot move that employer's cursor past unseen jobs. To rerun a seven-day backfill deliberately, pass `--mode initial`. To test a few sources:

```bash
PYTHONPATH=src python3 -m h1b_job_monitor crawl \
  --state data/smoke.sqlite \
  --output-dir reports/smoke \
  --mode initial \
  --company amazon --company datadog --company ramp --company palantir --company servicenow
```

## Output contract

Each emitted role includes:

- company, title, location, official source and application URLs;
- provider posting timestamp, date basis, and date confidence;
- `discovered_at`, stable source ID, and event type (`new` or verified `reposted`);
- employer sponsorship confidence, source-backed evidence summary, role-level sponsorship language, and score;
- match score, extracted experience floor, concise match reasons, and `P0`/`P1`/`P2` application priority.

Every run creates `reports/runs/<run-id>/` with:

- `daily_report.html` and `daily_report.md`;
- `matches.csv` and `matches.json`;
- `rejections_audit.csv`, which makes false-positive tuning inspectable;
- `company_health.csv`, including zero-result sources, policy skips, warnings, requests, and failures.

Stable `reports/latest.*` files are rewritten only after the report export completes.

## Conservative gates

The defaults live in `config/profile.json`. The `filters` section controls technical-score thresholds, sponsorship, years-of-experience, date-confidence, freshness, and US-location gates. The `matching` section exposes role-shape and department inclusion/exclusion, seniority, P0 specialty, capped title/skill scoring, and every resume-aligned skill group/weight as configurable regular expressions. Invalid matching configuration is caught by `validate-config` before a crawl.

The match score is deliberately technical-only: title evidence is capped at 30, skill evidence at 42, breadth at 6, and experience fit at 12, for a maximum of 90. Employer sponsorship, geography, and broad company tags cannot rescue a technically weak role; sponsorship remains a separate hard gate and priority condition.

The AI/RAG/MCP material is project evidence, not production ML experience. It can strengthen an otherwise relevant backend or platform posting, but pure AI-engineer, ML-engineer, scientist, and research titles remain excluded. AI/ML platform work is capped below P0. Kafka/MSK, Redis, Docker/ECS, GraphQL, observability tools, and AI application tooling are treated as secondary evidence: a posting that explicitly requires more experience in one of these than the resume establishes is rejected even if Java/AWS terms also appear. Kubernetes and Terraform are not scored because they do not appear in the current canonical resume.

The monitor fingerprints the relevance-affecting profile. When matching rules change, each healthy company automatically receives a one-time seven-day re-evaluation. Roles already delivered remain deduplicated; a previously rejected role that newly qualifies is labeled `new` because it is new to the user. A failed or incomplete source keeps its prior fingerprint and retries the backfill later.

The monitor requires an actual software-engineering role shape plus professionally evidenced Java, Python, AWS, backend/distributed-systems, security, or API work. Bare words such as “platform” or “backend” cannot rescue customer, product, advocacy, administration, or generic systems roles. Operations-oriented SRE/platform/infrastructure/security titles also require software-development evidence. Explicit ATS department scope is used to reject frontend/mobile/QA/data-science/robotics work; software work on ML platform or infrastructure may survive but remains capped below P0. A narrowly aligned streaming/real-time/telemetry Data Engineer role can survive, but ordinary data-engineering roles do not.

The monitor also rejects internships, new-grad/entry-level and level-I roles, managers/directors, staff/principal/architect/lead and common L6/IC6/E6+ roles, clearly unrelated frontend/mobile/data-science/pure-ML/test/support roles, federal/citizenship/clearance-restricted roles, non-US or unverifiable locations, and roles requiring more than five years.

`Senior` is not automatically rejected. A Senior role survives only when the description supplies a verifiable experience floor of five years or less. A Senior role with no parseable experience floor is rejected.

Posting-level language such as “without current or future sponsorship” overrides company filing history and causes rejection. Explicit sponsorship availability boosts confidence. Silence in the posting is not treated as proof either way.

## Sponsorship evidence: what it means

The strongest research pass uses official DOL FY2026 Q1 disclosure records and retains only `VISA_CLASS == H-1B` and `CASE_STATUS == Certified`. Employer-reported `CHANGE_EMPLOYER` positions are used as a transfer-oriented signal. A second independent pass cross-checks FY2025 Q4 activity and broadens sector coverage; its counts combine `Certified` and `Certified - Withdrawn`, and this different case-status basis is labeled explicitly in every audit row.

An LCA is a labor-condition filing, not a USCIS petition approval, completed transfer, current vacancy, or promise that a specific team will sponsor. That limitation is carried into every report. Exact petitioner names and source URLs remain in `research/company_universe.csv` so the mapping is auditable.

Confidence defaults:

- `high`: recent, meaningful filing volume plus relevant engineering titles and transfer-oriented activity;
- `medium-high` / `medium`: current evidence but weaker volume or transfer signal;
- `low`: recent sponsorship evidence without a recent new/change-employer signal; excluded by the default sponsorship threshold;
- `historical`: retained only for research unless newer evidence is added.

Staffing firms, outsourcing consultancies, body shops, aggregators, and obvious low-quality intermediaries are intentionally absent.

## Source access policy

The monitor never submits an application, bypasses authentication, solves CAPTCHAs, rotates identities, or evades access controls.

- Greenhouse, Lever, and Ashby are marked `documented_public_api` because their vendors document unauthenticated public job-posting APIs.
- SmartRecruiters documents its Posting API as public/no-auth, but its generic API robots policy conflicts with that documentation. Each enabled SmartRecruiters source therefore carries an explicit, narrow, read-only public-API exception and the documentation URLs. Strict users can change its `access_policy` to `disabled`.
- Workday CXS is first-party but undocumented, and Workday's general terms create a material automation concern. Workday employers are researched and configured but disabled by default (`access_approved: false`). Enable a tenant only after reviewing that employer's current robots/terms or obtaining permission. The connector still includes the important 20-record page limit, repeated-page detection, 2,000-record cap warning, exact detail `startDate`, and facet support.
- HTML/sitemap connectors use strict robots behavior. A missing robots file that cannot be distinguished from a network failure causes a conservative skip rather than an assumed permission.
- Sixteen official sitemap/`JobPosting` routes passed a separate live robots/terms audit. Per-host crawl delays recorded by that audit (including Expedia's ten seconds and Waymo's five seconds) are enforced. The exact enabled/disabled decisions and caveats are in `research/coverage_expansion_audit.csv`.

This policy costs coverage, intentionally. `company_health.csv` makes that cost visible instead of pretending every employer was crawled.

## Scheduling twice daily

### Hosted GitHub Actions schedule

The workflow targets **07:17 and 19:17 America/Los_Angeles**, including daylight-saving changes. GitHub sends lightweight wake-ups every half hour. A wake-up restores the shared SQLite state and checks the window due at the actual current Pacific time—not the potentially hours-old cron expression. Only a completed, successful crawl of the entire enabled company universe satisfies a window. Extra wake-ups do not crawl or emit jobs. An incomplete crawl may retry after 60 minutes, up to three attempts per window; failures remain visible after that. A missed interval is covered by the next actual crawl using preserved per-company cursors.

**GitHub schedules are best-effort, not guaranteed appointment times.** Recent native events arrived 3–6 hours late even with UTC schedules. More frequent wake-ups improve recovery but cannot provide an independent guarantee against GitHub's scheduler stopping entirely. Hosted execution does not depend on the laptop. Normal manual runs and external dispatches obey the same cadence; use the explicit `force_crawl` option only for an intentional additional scan.

This repository is intentionally public. Its workflow definition, run logs, job summaries, match/failure issues, repository owner, and legacy local launcher/package identifiers are therefore public. The checked-in matching profile contains only generalized experience and skill evidence; the resume file, contact details, and local SQLite database are excluded. Each run retains the report artifact for 30 days and creates an owner-assigned public issue for new P0/P1/P2 matches.

Open the issue labeled **h1b-monitor-status** first. It stays open and shows the last wake-up separately from the last actual crawl, source counts, latest outcome, new-match count (including zero), due window, and recent history. Its timestamp is a snapshot: if it stops advancing, do not mistake the old “healthy” label for a live guarantee. This scheduler cannot send an alert while all of its own triggers have stopped.

Issues labeled **h1b-monitor-match** contain jobs and are never auto-closed. Issues labeled **h1b-monitor-failure** describe operational problems; recovery closes them with a link to the successful run. Closure does not delete or retract any jobs. All new issue dates and visible crawl timestamps use Pacific time. Expedia and other sites can intermittently deny hosted requests; the crawler stops that source's detail requests on 401/403, preserves its cursor, and reports the failure without bypassing access controls.

State is saved in the existing cache and in a checksum-checked recovery artifact retained for 90 days. The recovery copy includes job identities, emission markers, sightings, cursors, and run history; disposable HTTP-response cache entries are omitted from the copy only. Backups are accessible to people who can download this public repository's artifacts. If the cache disappears, the latest backup is verified before restoration. Missing/corrupt state or a backup older than a newer unbacked report blocks execution: it never silently resets seen jobs or reinitializes the past week.

### Optional independent scheduler (not deployed)

For stronger timing, an independently hosted scheduler can invoke the GitHub workflow API at the same local targets, or every half hour as a redundant wake-up. It must run off the laptop and use a **new fine-grained token restricted to this repository with Actions: write**, stored as a secret—not the laptop's existing broad Git credential. Do not put a token in a URL, source file, issue, or log.

Send an authenticated HTTPS POST to `https://api.github.com/repos/prudhviy99/h1b-job-monitor/actions/workflows/job-monitor.yml/dispatches` with body `{"ref":"main","inputs":{"force_crawl":false}}`. The ordinary native scheduler remains a fallback; both triggers share the same concurrency group, cadence, and SQLite deduplication. Dispatch acceptance is not run success: the external scheduler should also verify a completed full crawl after each target and alert through its own channel if none arrives. No external account, credential, paid service, or independent alerting has been configured by this repository.

The earlier laptop-bound Codex task is paused after the hosted workflow's first successful run, preventing independent databases and duplicate alerts.

### macOS alternative

The installer writes a user LaunchAgent and schedules 07:17 and 19:17 in the Mac's local timezone:

```bash
python3 scripts/install_launchd.py --python "$(command -v python3)"
```

Check it with:

```bash
launchctl list | grep com.prudhvi.h1b-job-monitor
```

Remove it with:

```bash
python3 scripts/install_launchd.py --uninstall
```

The installer is included but is not run automatically. Do not enable it alongside the hosted workflow unless duplicate crawls and separate state are intentional.

### cron

Copy and edit `scheduler/crontab.example`. Cron uses the machine's local timezone.

### GitHub Actions

`.github/workflows/job-monitor.yml` is the hosted workflow definition. It uses half-hourly wake-ups with a Pacific-time/SQLite cadence guard, prevents overlapping runs, validates tests before crawling, checkpoints SQLite, saves cache plus checked recovery backups, publishes reports and status, and pins third-party actions to reviewed commit SHAs. Scheduled starts can still be delayed or dropped; the listed target times are not hard real-time guarantees.

## Reliability and state

The SQLite database is `data/jobs.sqlite`. The main identity is a hash of employer plus the provider's stable posting ID. URL and title/location are fallbacks only. A second run does not emit an already-seen role. If the same stable ID gets a later provider posting date, it can be emitted as `reposted`; a changed description alone becomes `updated` in the audit but is not a new alert.

The CLI takes a nonblocking file lock next to the database, so an overlapping scheduler invocation exits instead of racing the state. SQLite uses WAL mode. Every source failure is isolated. A partial run processes healthy employers but does not advance a failed or incomplete employer's cursor. Recent detail failures, relevant request-budget exhaustion, and unsafe pagination truncation are marked `degraded` in source health rather than being called complete.

The evolving database is carried between hosted runs through the GitHub Actions cache, with a separate checksum-checked recovery artifact after each delivered crawl. Cache eviction triggers validated backup recovery, never a fresh seven-day initialization. If neither current state nor a safe backup is available, the workflow fails visibly and requires repair before crawling. The former one-time deployment bootstrap is no longer used by the hosted workflow.

GET responses with ETag or Last-Modified are conditionally retrieved and cached in SQLite. `429` and transient 5xx responses are retried with exponential backoff and jitter. Requests are rate-limited per host, and response size is capped.

## Tests

Run the deterministic suite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Fixtures cover Greenhouse's `first_published` versus `updated_at`, Lever JSON-LD date and same-ID repost validation, Ashby unlisted posts and nested secondary locations, SmartRecruiters list/detail behavior and its explicit policy gate, Workday exact dates, sitemap JSON-LD/repost/deduplication, standards-correct robots Allow precedence, selective Senior and junior gates, flattened ATS qualification sections, role/department scope, sponsorship/work-authorization overrides, configurable US location/title rules, atomic delivery finalization, and SQLite new/seen/reposted state.

The initial build also performed live smoke crawls against Amazon Jobs, Datadog/Greenhouse, Ramp/Ashby, Palantir/Lever, and ServiceNow/SmartRecruiters. Live job counts are intentionally not asserted in unit tests because they are volatile.

## Updating the employer universe

`config/companies.json` is the runtime configuration; `research/company_universe.csv` is the human audit view.

For an employer to become enabled, require all of the following:

1. current, source-backed sponsorship evidence;
2. a direct employer, not an intermediary;
3. an official careers route and verified employer/board identity;
4. a supported, read-only source with an acceptable access policy;
5. a meaningful fit to backend/platform/infrastructure/security/SRE/distributed-systems hiring.

Do not guess ATS identifiers. Follow the official career page to the board and verify returned company name and posting URLs.

## Known limitations

- Employer-level sponsorship evidence is never requisition-level confirmation.
- Lever's v0 `createdAt` is undocumented; recent candidates require matching hosted-page `JobPosting.datePosted`.
- Ashby's `publishedAt` is a last-published timestamp and can advance on republish.
- Greenhouse `updated_at` is never used as a new-post date.
- Some career systems have no safe, stable read-only source. Those employers remain in the research universe but are not silently scraped.
- Job descriptions express years of experience inconsistently. The rejection audit exists so edge cases can be tuned without hiding decisions.
- Reports link to official applications but do not apply automatically.
