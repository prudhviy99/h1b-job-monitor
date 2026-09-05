# Job discovery audit — September 4, 2026

## Observed failure modes

- The September 4 morning cloud crawl succeeded: 62/62 sources, 12,111 fetched records, 49 technical matches, zero new alerts. Its state contained 13 matched records with dates in the past 30 days. A zero-alert report was therefore not a usable daily application queue.
- Greenhouse list requests omitted the documented `content=true` option. Outside the recent-detail window, live records were rebuilt with empty descriptions and failed relevance checks. This lost useful backlog and spent extra calls obtaining individual descriptions for fresh roles.
- Discovery covered 62 of 149 researched employers. A research row did not mean a working connector. Three existing employer records now have reviewed connectors: Adyen (Greenhouse), Arista Networks (SmartRecruiters), and General Motors (public Workday tenant).
- The persistent state deduplicates notifications, not a person's applications. Earlier issues must not be mistaken for unapplied jobs.
- Native GitHub triggers have arrived hours late. The existing half-hour wake-ups, Pacific window guard, state recovery, and retries work when GitHub delivers a trigger, but cannot guarantee two punctual runs or alert independently during a total scheduler outage.

## Changes

The documented full-description Greenhouse feed now supplies live job descriptions without individual requests when content and first-published date are present. Fallback detail calls remain bounded. First-published dates are still used; updated timestamps are not substituted.

A separate 30-day application queue is regenerated from the current crawl, with JSON, CSV, searchable HTML, and one always-open GitHub issue. It does not change seen-job delivery markers. It includes earlier alerts and suitable unalerted backlog, and labels uncertain posting ages. Removed or failed-source jobs are not silently carried into the current queue. Coverage is limited to records actually retrieved in the crawl; date-prefiltered sitemap/Workday connectors do not promise a complete 30-day backlog. Multiple Greenhouse location posts sharing an internal requisition are grouped. The first batch favors recent dates, fit, and up to three roles per employer before overflow.

Explicit expired application deadlines and closed/unlisted flags are checked. A live official listing still cannot prove that a vacancy is funded, actively interviewing, or sponsor-approved; the application page is the final check.

The new resume is identified by its filename and SHA-256 in the profile. The experience ceiling stays four years; Amazon remains disabled. Public artifacts contain no resume file, contact details, conversation excerpts, or application history.

## Source checks and boundaries

| Employer/source | September 4 check | Outcome |
|---|---|---|
| Adyen | [Official branded board](https://job-boards.greenhouse.io/adyen), [company vacancies](https://careers.adyen.com/vacancies), public API returned matching employer jobs | Enable existing Greenhouse connector |
| Arista Networks | [Official branded board](https://careers.smartrecruiters.com/AristaNetworks), API employer identity and 240 published jobs verified | Enable existing SmartRecruiters connector |
| General Motors | Public `Careers_GM` tenant, current robots rules, [GM user guidelines](https://www.gm.com/user-guidelines) | Enable rate-limited Workday connector; three seconds between calls; no private sites |
| Visa | Both observed SmartRecruiters identifier variants returned zero jobs | Do not present an empty obsolete feed as coverage |
| IBM | Advertised English sitemap returned HTTP 202 with an empty body | Keep manual |
| Oracle | Career HTML identifies its Candidate Experience backend; [Oracle terms](https://www.oracle.com/legal/terms.html) restrict automated access; the [API documentation](https://docs.oracle.com/en/cloud/saas/human-resources/farws/op-recruitingcejobrequisitions-get.html) marks relevant resource endpoints internal-use | Use official alerts/manual discovery; do not reverse engineer around this restriction |
| eBay | Current Workday robots reviewed; current corporate terms page returned 403 | Keep previous disabled status pending a complete access review |
| Aurora | Career platform has changed; tested Ashby identifier returned 404 | No guessed connector enabled |
| Veeva | Public sitemap exposes jobs, but lastmod is regenerated daily | No use of sitemap lastmod as a posting date; pending detail/date verification |
| DOL FY2026 Q3 | Indexed [DOL performance page](https://www.dol.gov/agencies/eta/foreign-labor/performance) advertises newer disclosures; direct retrieval returned 403 | Do not claim refreshed evidence or fabricate counts; retain explicitly dated FY2026 Q1 / FY2025 Q4 employer evidence |

The three new connectors reuse existing matched legal-employer LCA records; no new sponsorship claim is inferred merely from having an ATS page. Recorded confidence describes employer filing history, not current per-role H-1B transfer approval.

## Authoritative API references

- [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html): GET endpoints are public; `content=true` includes descriptions, departments and offices.
- [SmartRecruiters Posting API](https://developers.smartrecruiters.com/docs/posting-api): public published-job discovery.
- [Ashby public postings API](https://developers.ashbyhq.com/docs/public-job-posting-api): listed jobs, published dates and official application URLs.

## Practical limits

This system cannot truthfully guarantee 30 new sponsor-compatible mid-level vacancies every day, or 30 submissions in an hour on arbitrary employer forms. It can remove repeated discovery work, retain a useful backlog, and rank the next application batch. Application speed must be measured separately using autofill. Rejection causes require application-level outcomes; they cannot be inferred from crawler health or a match score.
