# Hosted reliability audit — August 30, 2026

## Verified incidents

| Event | Pacific timestamp | Evidence |
|---|---|---|
| August 29 morning target | 07:17 AM; actual crawl 10:43 AM | [run 33266383259](https://github.com/prudhviy99/h1b-job-monitor/actions/runs/33266383259) |
| August 29 evening target | 07:17 PM; actual crawl Aug 30 01:22 AM, Expedia 403 | [run 33301398743](https://github.com/prudhviy99/h1b-job-monitor/actions/runs/33301398743) |
| Source recovery | Aug 30 02:19 AM; 63/63 healthy, zero new matches | [run 33303762466](https://github.com/prudhviy99/h1b-job-monitor/actions/runs/33303762466) |
| August 30 morning target | 07:17 AM; actual crawl 11:04 AM, 63/63 healthy, zero new matches | [run 33326995883](https://github.com/prudhviy99/h1b-job-monitor/actions/runs/33326995883) |
| Failure issue closure | Aug 30 02:22 AM, correctly resolved after full recovery | [issue 13](https://github.com/prudhviy99/h1b-job-monitor/issues/13) |

As of 20:51 Pacific on August 30, that day's evening native event had not arrived. Failed/source-alert issues were closed after recovery, not job-match issues. The state cache was restored from the preceding real run each time; no database reset was observed.

## Corrections to prior conclusions

- UTC scheduling did not eliminate the delay. Workflow event creation itself was hours late, while runner startup after event creation was only seconds. The evidence does not establish a timezone-parser bug.
- HTTPS normalization did not permanently eliminate Expedia access denial. HTTPS pages also intermittently returned 403 on hosted runners; a later ordinary retry recovered. This is not grounds to rotate identities or bypass access controls.
- A manual successful run proves crawling/persistence at that instant, not future native schedule delivery.

## Changes

1. Half-hourly wake-ups use actual Pacific time and the persisted SQLite crawl ledger. Delayed or retired cron expressions cannot assign the wrong window. A completed full scan satisfies a window; normal manual dispatches obey the same guard.
2. Incomplete attempts have a one-hour cooldown and three-attempt limit per window. Access-denied sitemap sources stop further detail requests and retain their cursor.
3. One always-open status issue distinguishes heartbeat checks, real crawls, zero matches, source failures, and overdue windows. Match issues stay open; recovery comments explain failure-alert closure. Visible issue dates use Pacific time.
4. Separate checked recovery artifacts back up durable seen-job state. Cache absence no longer silently falls through to seven-day reinitialization. Recovery rejects corruption, stale rollback, and overwriting an existing state database.

## Residual limitations

[GitHub documents that scheduled events can be delayed or dropped](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). Its status page listed no incident for August 29–30, but that does not override the repository's observed delays.

Frequent native wake-ups reduce dependence on any single cron event; they do not create an independent scheduler or guarantee bounded lateness. An independently hosted, authenticated workflow dispatcher plus a separate freshness alert is needed for a stronger timing promise. No such service has been provisioned. See README for the narrow dispatch contract.
