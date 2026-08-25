# ATS connector research and implementation notes

Research snapshot: **2026-08-25 (America/Los_Angeles)**

Scope: official/public job-source retrieval for Greenhouse, Lever, Ashby,
SmartRecruiters, Workday, and a conservative sitemap + `JobPosting` JSON-LD
fallback. This document describes discovery, response normalization, freshness,
pagination, canonical URLs, deduplication, and access-safety behavior. It does
not cover sponsorship research or job ranking.

## Bottom line

Use the four documented public posting APIs first. Treat Workday CXS as an
undocumented, first-party frontend endpoint and gate it with per-tenant robots
and terms review. Use sitemap/JSON-LD only when a company has no usable ATS
feed.

| Source | Recommended status | Official public contract? | Page size | Best posting date | Date confidence |
|---|---|---:|---:|---|---|
| Greenhouse | Enable | Yes | All jobs in one list response | `first_published` from job detail; observed on list too | High |
| Lever | Enable with date validation | Yes | `skip`/`limit`; no total | hosted-page JSON-LD `datePosted`; v0 `createdAt` is useful but undocumented | Medium-high after JSON-LD validation |
| Ashby | Enable | Yes | All jobs in one response | `publishedAt` (last published) | High |
| SmartRecruiters | Enable only under a recorded public-API policy exception | Yes; no auth by design | 100 max observed; `offset` paging | `releasedDate` | High |
| Workday CXS | Conditional / per tenant | No public CXS documentation found | 20 max observed; `offset` paging | detail `jobPostingInfo.startDate` | High for value, lower for contract stability |
| Sitemap + JSON-LD | Fallback | Open standards, but site-specific | Sitemap: 50,000 URL protocol limit | JSON-LD `datePosted`; never sitemap `lastmod` | High if first-party JSON-LD validates |

The most important freshness rule is to preserve both the date and its basis:

```text
posted_at
posted_at_basis        # first_published | jsonld_datePosted | last_published |
                       # releasedDate | posting_start_date | first_seen
posted_at_confidence   # high | medium | low | unknown
source_updated_at      # separate from posted_at
first_seen_at
```

Do not silently turn `updated_at`, sitemap `lastmod`, or crawler discovery time
into a posting date. That would create false “posted in the last 7 days” hits.

## Recommended normalized source contract

Every connector should produce the same raw-normalized shape before ranking:

```text
source_type
source_account                   # board token / site slug / tenant+site
source_job_key                   # stable provider-specific ID
company
title
locations[]                      # retain all locations
country_codes[]
workplace_type                   # on_site | hybrid | remote | unknown
employment_type
department
team
description_html
description_text
posted_at
posted_at_basis
posted_at_confidence
source_updated_at
source_url                       # canonical human-readable posting URL
apply_url
is_active
discovered_at
raw_payload_hash
```

Recommended keys:

| Source | `source_job_key` |
|---|---|
| Greenhouse | `greenhouse:{board_token}:{jobs[].id}` |
| Lever | `lever:{region}:{site}:{id}` |
| Ashby | `ashby:{board_name}:{UUID-like final jobUrl segment}`; fall back to normalized full `jobUrl` |
| SmartRecruiters | `smartrecruiters:{companyIdentifier}:{id}` |
| Workday | `workday:{host}:{site}:{jobPostingInfo.id}`; fall back to `externalPath` |
| JSON-LD | `jsonld:{canonical_url}`; use `identifier.value` as a secondary alias, not the only key |

Provider IDs should drive within-source deduplication. A title/location hash is
only a secondary cross-source alias because the same requisition can have
legitimate location-specific posts.

## 1. Greenhouse Job Board API

### Access and discovery

Official documentation: [Greenhouse Job Board API](https://developer.greenhouse.io/job-board.html).
Greenhouse states that job-board GET data is public and does not require
authentication. Only application submission requires credentials; this monitor
must never submit applications.

The board token normally comes from one of these official-career links:

```text
https://boards.greenhouse.io/{board_token}
https://job-boards.greenhouse.io/{board_token}
https://boards.greenhouse.io/embed/job_board?for={board_token}
```

Do not guess a token and trust a 200 response alone. Verify it by:

1. following the employer's official careers page to the Greenhouse board;
2. calling `GET /v1/boards/{board_token}` and checking the board name;
3. checking that returned `absolute_url` values resolve to that employer or its
   Greenhouse board.

### Endpoints

```http
GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs
GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}
GET https://boards-api.greenhouse.io/v1/boards/{board_token}
```

Prefer the lighter list without `content` for discovery, then fetch detail for
recent/title-location candidates. `content=true` is convenient for small boards
or a one-request snapshot but transfers every full description.

The list response is:

```json
{
  "jobs": [
    {
      "id": 7194969,
      "internal_job_id": 123,
      "title": "Software Engineer",
      "updated_at": "2026-08-24T10:26:32-04:00",
      "first_published": "2026-08-22T09:00:00-04:00",
      "application_deadline": null,
      "location": {"name": "New York, NY"},
      "absolute_url": "https://company.example/jobs/7194969?gh_jid=7194969",
      "content": "&lt;p&gt;...&lt;/p&gt;",
      "departments": [],
      "offices": [],
      "metadata": []
    }
  ],
  "meta": {"total": 1}
}
```

The documented list fields include `id`, `internal_job_id`, `title`,
`updated_at`, `requisition_id`, location, `absolute_url`, language, and
metadata. `content=true` adds description, departments, and offices. The
documented **job-detail** response includes `first_published` and
`application_deadline`.

In the 2026-08-25 live test, Datadog's list response also contained
`first_published` and `application_deadline` on every inspected record. Because
the list documentation does not currently promise those two fields, implement
this defensively:

1. Use non-null list `first_published` when present.
2. If missing, apply cheap title/location filters using the list response.
3. Fetch job detail for the surviving candidates and use the documented detail
   `first_published`.
4. Use that detail response for the description needed by ranking.
5. Never substitute `updated_at` for `first_published` in the seven-day filter.

### Pagination and caching

The jobs list has no documented `limit`, `page`, or cursor. It returns all
published jobs with `meta.total`. Datadog's live feed returned 453 records and
`meta.total == 453`; adding `limit=1&page=2` did not paginate it.

The tested endpoint returned an `ETag`, and `If-None-Match` returned `304`.
Store the ETag per board and use conditional requests on later runs.

### Field and parsing notes

- Stable key: `jobs[].id`, not `internal_job_id`. Greenhouse distinguishes the
  job post from the internal job. Multiple posts may represent one internal
  job.
- Exclude prospect/general-interest posts where `internal_job_id` is null.
- `content` contains entity-escaped HTML. The live response began with
  `&lt;p&gt;...`; HTML-unescape once, sanitize, then derive plain text.
- `metadata` is employer-configured and schema-less. It can contain useful
  employment type, engineering area, IC/manager, location, and pay fields, but
  must not be required for parsing.
- `location.name` can be a free-form multi-location label. Prefer `offices[]`
  when it supplies structured city/country, but retain the displayed location.
- `absolute_url` is the source URL. It may be a custom employer domain. When
  removing analytics query parameters, preserve identity parameters such as
  `gh_jid` if the path itself does not identify the job.
- `updated_at` belongs in `source_updated_at`; it is useful for change hashes,
  not first-run freshness.
- `first_published` is the original publication timestamp for that job post.
  A brand-new post ID for a repost should be treated as a new posting.

### Live proof

```text
GET https://boards-api.greenhouse.io/v1/boards/datadog/jobs?content=true
HTTP 200; 453 jobs; meta.total 453
content=false payload about 625 KB; content=true about 5.7 MB
sample id: 7194969
sample first_published: 2025-08-27T10:34:20-04:00
sample updated_at: 2026-08-24T10:26:32-04:00
```

This sample is a good demonstration of why `updated_at` must not be called a
new-post date.

## 2. Lever Postings API

### Access and discovery

Official documentation: [Lever Postings API](https://github.com/lever/postings-api/blob/master/README.md).
The repository belongs to Lever's verified GitHub organization. It says the API
is designed to power job sites, returns published public postings, and supports
global and EU instances.

Find `site` and region from the employer's official-career link:

```text
https://jobs.lever.co/{site}
https://jobs.eu.lever.co/{site}
```

Then use the corresponding API host:

```http
GET https://api.lever.co/v0/postings/{site}?mode=json&skip={n}&limit={n}
GET https://api.eu.lever.co/v0/postings/{site}?mode=json&skip={n}&limit={n}
GET https://api.lever.co/v0/postings/{site}/{posting_id}
```

Send both `Accept: application/json` and `mode=json` to avoid accidental HTML
responses.

### Response shape

The list response is a bare array:

```json
[
  {
    "id": "ac978161-6f46-4f6b-ad9e-a258e642751c",
    "text": "Software Engineer",
    "createdAt": 1787046089466,
    "categories": {
      "location": "New York, NY",
      "allLocations": ["New York, NY", "Washington, DC"],
      "commitment": "Full-time",
      "team": "Engineering",
      "department": "Product"
    },
    "country": "US",
    "workplaceType": "hybrid",
    "description": "<div>...</div>",
    "descriptionPlain": "...",
    "lists": [{"text": "What We Require", "content": "<li>...</li>"}],
    "additional": "<div>...</div>",
    "additionalPlain": "...",
    "hostedUrl": "https://jobs.lever.co/site/id",
    "applyUrl": "https://jobs.lever.co/site/id/apply",
    "salaryRange": null
  }
]
```

Official v0 documentation covers the ID/title, category and location fields,
country, HTML/plain description fragments, lists, hosted/apply URLs,
workplace type, and optional salary. It does **not** document `createdAt`, even
though that field was present in every live Palantir response inspected. A
long-standing [Lever issue records that `createdAt` is undocumented](https://github.com/lever/postings-api/issues/35).

### Posting date strategy

The hosted Lever page contains `JobPosting` JSON-LD with `datePosted`. In the
live Palantir sample:

```text
v0 createdAt: 1711403416463 -> 2024-03-25 UTC date
hosted JSON-LD datePosted: 2024-03-25
```

Use this conservative flow for first-run seven-day results:

1. Treat numeric `createdAt` as Unix milliseconds and use it only to shortlist.
2. For a potentially recent, relevant job, fetch `hostedUrl` if robots permits.
3. Parse first-party `JobPosting.datePosted` and require it to agree with the
   UTC date derived from `createdAt` (allowing timezone date-boundary tolerance).
4. Mark a matching value `posted_at_basis=jsonld_datePosted` and confidence
   `medium-high`. If JSON-LD is absent or conflicts, mark the date uncertain and
   do not claim it is a verified past-week posting.

The cross-check validates what Lever publicly declares as the posting date. It
does not prove that a republished posting retained the correct original date.
Lever v0 exposes no documented update timestamp, so persistent ID snapshots and
`first_seen_at` are essential. A repost that keeps the same ID and date cannot
be reliably identified as new from this API alone.

### Pagination and caching

Lever documents `skip` and `limit`, but no total count. Loop until a response
contains fewer than `limit` records, and deduplicate every page by `id` because
the live set can change while offsets are being read.

The Palantir live board returned 308 jobs. It honored limits of 100, 101, 200,
and 500; 500 returned all 308. A page size of 100 is a conservative default.

The API returned an `ETag`, and a matching `If-None-Match` returned `304`.

### Field and parsing notes

- Use `text` as the title; there is no `title` field.
- Use every entry in `categories.allLocations`, not only primary `location`.
- `country` is ISO 3166-1 alpha-2 when known, but may be null.
- Prefer `descriptionPlain`, supplemented by plain text extracted from
  `lists[].content` and `additionalPlain`. The `lists[].content` fragment may
  contain bare `<li>` nodes without a wrapping list.
- Normalize non-breaking spaces and Unicode punctuation in plain fields.
- `workplaceType` is useful but not sufficient for geographic eligibility.
- Use `hostedUrl` as source/canonical and `applyUrl` as the apply target.
- Strip only analytics parameters. Do not reconstruct a URL if Lever supplies
  one.
- Global and EU are separate namespaces; region is part of the source key.

### Live proof

```text
GET https://api.lever.co/v0/postings/palantir?mode=json
HTTP 200; 308 jobs
pagination with skip=1&limit=1 returned the next posting
hosted page supplied schema.org JobPosting JSON-LD
```

## 3. Ashby public Job Postings API

### Access and discovery

Official documentation: [Ashby Job Postings API](https://developers.ashbyhq.com/docs/public-job-posting-api).
Ashby documents this lightweight API specifically for currently published job
postings and describes how to find the board name from the hosted job-board
URL:

```text
https://jobs.ashbyhq.com/{JOB_BOARD_NAME}
```

Endpoint:

```http
GET https://api.ashbyhq.com/posting-api/job-board/{JOB_BOARD_NAME}?includeCompensation=true
```

The board name should be copied exactly from the official URL; do not assume
case folding.

### Response shape

```json
{
  "apiVersion": "1",
  "jobs": [
    {
      "title": "Security Engineer, Cloud",
      "location": "New York, NY (HQ)",
      "secondaryLocations": [
        {
          "location": "Remote (US)",
          "address": {
            "postalAddress": {"addressCountry": "United States"}
          }
        }
      ],
      "department": "Engineering",
      "team": "Backend",
      "isRemote": true,
      "workplaceType": "Hybrid",
      "descriptionHtml": "<p>...</p>",
      "descriptionPlain": "...",
      "publishedAt": "2026-04-07T17:12:35.753+00:00",
      "employmentType": "FullTime",
      "address": {
        "postalAddress": {
          "addressLocality": "New York City",
          "addressRegion": "NY",
          "addressCountry": "USA"
        }
      },
      "jobUrl": "https://jobs.ashbyhq.com/ramp/34413f8d-...",
      "applyUrl": "https://jobs.ashbyhq.com/ramp/34413f8d-.../application",
      "isListed": true,
      "compensation": {}
    }
  ]
}
```

### Pagination, freshness, and caching

No pagination parameters are documented. The live Ramp response returned all
139 jobs. Adding `limit=1&offset=1` still returned 139, confirming those query
parameters are ignored on the tested board.

`publishedAt` is documented as the ISO timestamp when the job was **last
published**. Use `posted_at_basis=last_published`. This is an exact provider
timestamp, but it may intentionally move when a role is republished.

The endpoint returned `Cache-Control: public, max-age=60,
stale-while-revalidate=60` and an `ETag`; `If-None-Match` returned `304`.

### Field and parsing notes

- Exclude `isListed=false` from normal discovery. Ashby says these posts should
  be available only by direct link, not listed on the job board.
- The feed has no explicit posting ID. Use the stable final path component of
  `jobUrl` plus the board name. Retain the full normalized `jobUrl` as a backup.
- `jobUrl` is the source/canonical URL; `applyUrl` is the application URL.
- The official field table describes secondary address components directly
  under `address`, but the live Ramp payload nested them under
  `address.postalAddress`, like the primary address. Accept both shapes.
- `isRemote` and `workplaceType` can appear contradictory for multi-location
  roles. In the live sample, a hybrid primary role had remote secondary
  locations and `isRemote=true`. Preserve per-location facts and do not reduce
  this to a single boolean too early.
- `employmentType` enum values documented by Ashby are `FullTime`, `PartTime`,
  `Intern`, `Contract`, and `Temporary`.
- `includeCompensation=true` can substantially increase response size. Ramp's
  response was about 2.3 MB with compensation. Make it configurable or use
  `false` when compensation is not part of ranking.
- Parse `descriptionPlain` for matching and retain sanitized
  `descriptionHtml` for reports.

### Live proof

```text
GET https://api.ashbyhq.com/posting-api/job-board/ramp?includeCompensation=true
HTTP 200; apiVersion 1; 139 jobs
sample had primary New York, three secondary locations, publishedAt,
jobUrl/applyUrl, description HTML/plain, and structured compensation
```

## 4. SmartRecruiters Posting API

### Access and discovery

Official documentation:

- [Posting API overview](https://developers.smartrecruiters.com/docs/posting-api)
- [Posting API endpoints](https://developers.smartrecruiters.com/docs/endpoints)
- [Authentication](https://developers.smartrecruiters.com/docs/authentication)
- [Paging model](https://developers.smartrecruiters.com/docs/customer-overview)

SmartRecruiters says this API exposes public postings for custom career sites.
Its authentication guide explicitly lists the Posting API under APIs whose
public data requires no authentication by design.

The `companyIdentifier` is the final segment of the employer's default page:

```text
https://careers.smartrecruiters.com/{companyIdentifier}
```

Endpoints:

```http
GET https://api.smartrecruiters.com/v1/companies/{companyIdentifier}/postings?limit=100&offset=0
GET https://api.smartrecruiters.com/v1/companies/{companyIdentifier}/postings/{postingId}
```

The list supports documented filters such as `q`, country, region, city,
department, language, and custom fields. For accuracy, prefer an unfiltered
company crawl and filter locally; remote and multi-location metadata are not
consistent enough to trust a single country query as the only discovery path.

### List and detail shapes

The list wraps summary records:

```json
{
  "limit": 100,
  "offset": 0,
  "totalFound": 550,
  "content": [
    {
      "id": "744000145459619",
      "uuid": "bad3db37-...",
      "name": "Software Engineer",
      "company": {"identifier": "ServiceNow", "name": "ServiceNow"},
      "releasedDate": "2026-08-25T09:06:24.270Z",
      "location": {
        "city": "San Diego",
        "region": "CA",
        "country": "us",
        "remote": false,
        "hybrid": true,
        "fullLocation": "San Diego, CA, United States"
      },
      "department": {"id": "...", "label": "Engineering"},
      "function": {"id": "engineering", "label": "Engineering"},
      "typeOfEmployment": {"id": "permanent", "label": "Full-time"},
      "experienceLevel": {"id": "mid_senior_level", "label": "Mid-Senior"},
      "customField": [],
      "ref": "https://api.smartrecruiters.com/..."
    }
  ]
}
```

Fetch detail only for locally shortlisted records. Detail adds:

```text
active
postingUrl
applyUrl
referralUrl
jobId / jobAdId
jobAd.sections.companyDescription.text
jobAd.sections.jobDescription.text
jobAd.sections.qualifications.text
jobAd.sections.additionalInformation.text
```

Section text is HTML. Join known sections in that order and sanitize/derive
plain text.

### Pagination, freshness, and caching

Loop using `offset += count(content)` until `offset + count >= totalFound`.
The live ServiceNow API clamped requested limits 101 and 200 to 100, so use 100
as the page size. Deduplicate by `id` and tolerate `totalFound` changing during
a crawl.

`releasedDate` is an exact provider timestamp for the public posting. Use
`posted_at_basis=releasedDate`. The endpoint documentation notes that content
updates require re-posting the job; snapshot the date and payload hash so a
changed release can be audited.

The list endpoint returned an `ETag`; `If-None-Match` returned `304`.

### Canonical URL and field notes

- `id` is the best public-post key. Retain `uuid`, `jobId`, and `jobAdId` as
  aliases for diagnostics.
- Use detail `postingUrl` as canonical source URL. It has no tracking query.
- Use detail `applyUrl` as apply URL; it may include `?oga=true`.
- Country code casing varies; normalize to uppercase.
- `experienceLevel` is often `Not Applicable`, even for clearly senior jobs.
  Never use it as the only seniority filter; parse title and qualifications.
- Location `remote` and `hybrid` booleans can coexist with free-form/custom
  fields. Preserve all evidence.
- Some summary fields are optional. The official docs direct clients to the
  summary `ref`/detail endpoint for the full object.

### Robots-policy conflict

On 2026-08-25, `https://api.smartrecruiters.com/robots.txt` returned:

```text
User-agent: LinkedInBot
Allow: /v1/companies/
User-agent: *
Disallow: /
```

This conflicts with the official developer documentation describing the
Posting API as public, no-auth, and intended for programmatic career sites.
Make the policy explicit rather than accidentally ignoring it:

- Strict REP mode: disable SmartRecruiters unless the operator has permission.
- Documented-public-API mode: allow only the two documented read-only Posting
  API GET endpoints, record the official documentation as the access basis,
  use low rates/conditional requests, and continue to obey robots for any HTML
  career-page fetches.

Do not generalize the exception to other SmartRecruiters endpoints. Never call
candidate, internal-posting, referral, or application-write APIs.

### Live proof

```text
GET https://api.smartrecruiters.com/v1/companies/ServiceNow/postings?limit=2&offset=0
HTTP 200; totalFound 550; two summaries
GET .../postings/744000145459619
HTTP 200; full section HTML, releasedDate, postingUrl, and applyUrl
```

## 5. Workday CXS

### Status and caution

Workday does not publish a public job-board API comparable to the four above.
The `/wday/cxs/...` JSON endpoints are first-party endpoints used by the public
Workday careers frontend, but they are undocumented and can change without
notice. Do not describe this connector as an official supported API.

Workday's [Online Terms of Service](https://www.workday.com/en-us/legal/site-terms.html)
cover Workday sites/APIs that fall within their definition and prohibit data
mining/robots, applications interacting without consent, and ignoring
`robots.txt`. Whether those terms or an employer's terms govern a particular
`myworkdayjobs.com` tenant must be checked per tenant. Safest policy:

1. Store `terms_url`, `terms_checked_at`, `robots_checked_at`, and an explicit
   `access_approved` flag per Workday source.
2. Disable a source when its linked terms prohibit automation or its robots
   disallow the required paths.
3. Do not bypass WAFs, CAPTCHAs, session gates, or authentication.
4. Prefer an employer-provided XML/JSON feed or job sitemap when available.

### Endpoint discovery

From a public board such as:

```text
https://{tenant}.wd{cluster}.myworkdayjobs.com/{locale}/{site}
```

derive and verify:

```text
host   = {tenant}.wd{cluster}.myworkdayjobs.com
tenant = Workday tenant path component (often the hostname prefix)
site   = public job-posting site ID from the URL/config
```

Do not assume the hostname prefix always equals the tenant path. Probe the
candidate endpoint and verify returned employer/URLs against the official
career link. Store host, tenant, and site independently.

### Listing endpoint

```http
POST https://{host}/wday/cxs/{tenant}/{site}/jobs
Content-Type: application/json
Accept: application/json

{
  "appliedFacets": {},
  "limit": 20,
  "offset": 0,
  "searchText": ""
}
```

Response:

```json
{
  "total": 2000,
  "jobPostings": [
    {
      "title": "Software Engineer, SPE",
      "externalPath": "/job/Israel-Yokneam/Software-Engineer--SPE_JR2015623",
      "locationsText": "Israel, Yokneam",
      "postedOn": "Posted 23 Days Ago",
      "bulletFields": ["JR2015623"]
    }
  ],
  "facets": [],
  "userAuthenticated": false
}
```

The live NVIDIA tenant rejected limits 50 and 100 with HTTP 400; 20 worked.
Use `limit=20`. Offset paging had two non-obvious boundaries:

- `total` was 2000 at offset 0 and **0 at offset 20 despite returning 20
  jobs**. Only the first-page total is meaningful.
- Offset 1980 returned the expected last 20-record page, but offset 2000 and
  higher silently wrapped to the first page. A naïve “continue until an empty
  page” loop would never terminate.

Stop when the next offset reaches the first-page total, and also stop/error on
a repeated page fingerprint. Treat an exact first-page total of 2000 as a
possible platform cap. If the in-scope result set can reach that cap, partition
it with mutually exclusive tenant facets (for example country or job family),
ensure each partition is below the cap, and deduplicate the union. The tested
NVIDIA `United States + Engineering` partition with empty search text was 931
records. (`searchText="software"` reduced it to 680, but search results were
relevance ordered and are not suitable for the posting-age early-stop
optimization.)

With empty search text, NVIDIA's results were empirically sorted newest first:

```text
offset   0: Posted Today .. Posted Yesterday
offset  40: Posted Yesterday .. Posted Yesterday
offset 100: Posted 2 Days Ago .. Posted 3 Days Ago
offset 200: Posted 5 Days Ago .. Posted 5 Days Ago
offset 400: Posted 8 Days Ago .. Posted 8 Days Ago
```

Sorting is undocumented. A safe optimization may stop only after:

1. all observed pages so far are monotonic by parsed age;
2. at least two complete consecutive pages are older than the lookback cutoff;
3. no page contains an unparseable/localized `postedOn` value.

Otherwise crawl to the first-page total/cap boundary with repeat-page
detection. On later runs, use a cutoff based on the last successful scan plus a
safety overlap and deduplicate by stable ID.

Facet IDs are tenant-specific. Discover them from `facets[]` by descriptor,
then send arrays under their `facetParameter`, for example:

```json
{
  "appliedFacets": {
    "locationHierarchy1": ["tenant-specific-US-id"],
    "jobFamilyGroup": ["tenant-specific-Engineering-id"]
  },
  "limit": 20,
  "offset": 0,
  "searchText": ""
}
```

Do not copy facet IDs between companies. A geographic facet can reduce traffic,
but validate that it retains remote and multi-location US roles.

### Detail endpoint and exact date

Append the listing `externalPath` to the CXS site base:

```http
GET https://{host}/wday/cxs/{tenant}/{site}{externalPath}
```

Relevant `jobPostingInfo` fields observed live:

```json
{
  "id": "74121c85898c1032795e582be5f20000",
  "jobPostingId": "Software-Engineer--SPE_JR2015623",
  "jobPostingSiteId": "NVIDIAExternalCareerSite",
  "jobReqId": "JR2015623",
  "title": "Software Engineer, SPE",
  "jobDescription": "<p>...</p>",
  "startDate": "2026-08-02",
  "postedOn": "Posted 23 Days Ago",
  "posted": true,
  "canApply": true,
  "location": "Israel, Yokneam",
  "additionalLocations": [],
  "jobRequisitionLocation": {},
  "country": {"descriptor": "Israel", "id": "..."},
  "timeType": "Full time",
  "externalUrl": "https://.../{site}/job/..."
}
```

`startDate` matched `postedOn` in two live checks, including a posting with
`startDate=2026-08-25` and `postedOn="Posted Today"`. In this payload it is the
job-posting availability start date, not a candidate's employment start date.
Normalize it as `posted_at_basis=posting_start_date`.

Fetch detail for relevant candidates and any recent records needed for exact
dating. Use `posted`/`canApply` when present to suppress closed posts. Use
`externalUrl` as canonical source URL. For multi-location jobs, detail may add
`additionalLocations`; one live NVIDIA record expanded `"4 Locations"` into
Santa Clara plus Austin, Hillsboro, and Seattle.

### Sitemap

Tenant robots may advertise a site-specific sitemap:

```text
Sitemap: https://{host}/{site}/siteMap.xml
```

NVIDIA's sitemap returned 100 job URLs, while CXS reported 2000 jobs. It had no
`lastmod` values. Therefore a Workday sitemap can be a useful low-cost discovery
signal, but must not be assumed complete or sufficient for a seven-day
backfill.

### Live proof

```text
POST https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs
HTTP 200; first-page total 2000; maximum accepted limit 20; offsets >=2000
wrapped to page 1 in the tested tenant

GET https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/job/...
HTTP 200; exact startDate, HTML description, stable IDs, full locations,
canonical externalUrl
```

NVIDIA's robots file allowed its public career-site path and disallowed its
talent-community path at test time. Robots rules are per host/tenant and must be
rechecked rather than copied.

## 6. Generic sitemap + JSON-LD fallback

Use this only on an employer's official careers host (or its linked official ATS
host), never on aggregators.

### Sitemap discovery and parsing

1. Fetch and parse `https://host/robots.txt` for `Sitemap:` lines.
2. If none are declared, probe a small allowlist such as `/sitemap.xml` and
   `/sitemap_index.xml`; do not brute-force paths.
3. Parse `urlset` and recursively parse `sitemapindex`, including `.xml.gz`.
4. Enforce byte, nesting, URL-count, scheme, and host allowlists to prevent
   decompression bombs and SSRF.
5. Filter candidate URLs using employer-specific career path rules, then fetch
   only likely job-detail pages.

The [Sitemaps protocol](https://www.sitemaps.org/protocol.html) allows 50,000
URLs and 50 MB uncompressed per sitemap. Its `lastmod` means **the page was last
modified**, not when the job was posted and not when the sitemap was generated.
Store it as `source_updated_at`/crawl priority only.

### JSON-LD extraction

On each allowed, first-party detail page, parse every
`<script type="application/ld+json">` block. Support:

- a single object;
- an array of objects;
- an object with `@graph`;
- `@type` as either a string or an array.

Select only `@type: JobPosting`. The canonical schema is
[schema.org/JobPosting](https://schema.org/JobPosting), and Google's
[Job posting structured-data guide](https://developers.google.com/search/docs/appearance/structured-data/job-posting)
states that `datePosted` is the employer's original posting date in ISO 8601.

Useful fields:

```text
identifier.value
title
description
datePosted
validThrough
employmentType
hiringOrganization.name / sameAs
jobLocation[].address.addressLocality/addressRegion/addressCountry
jobLocationType
applicantLocationRequirements
baseSalary
directApply
eligibilityToWorkRequirement
url
```

Validation rules:

- Require title, description, `datePosted`, and `hiringOrganization.name` for a
  first-run past-week result.
- Verify hiring organization against configured company names/aliases.
- Require the page/canonical URL to be on an approved official or ATS host.
- Reject expired records when `validThrough < now`.
- For remote jobs, retain both `jobLocationType=TELECOMMUTE` and
  `applicantLocationRequirements`; “remote” does not mean remote anywhere.
- Prefer `<link rel="canonical">`, then JSON-LD `url`, then the fetched URL,
  but reject a canonical that leaves approved hosts.
- Decode HTML entities and sanitize `description`; never execute embedded
  scripts.
- If JSON parsing fails, log a bounded redacted diagnostic and skip rather than
  guessing dates from visible prose.
- Treat sitemap `lastmod`, HTTP `Last-Modified`, and OpenGraph article dates as
  low-confidence update signals, not `datePosted` substitutes.

### Other fallback formats

RSS/Atom feeds can be used when the official careers site advertises them.
Their `pubDate`/`updated` values are still feed/page update dates unless the
feed contract explicitly defines them as job publication dates. Custom
Next.js state, internal GraphQL calls, and undocumented JavaScript bundles are
fragile last resorts and should be company-specific, opt-in connectors rather
than generic extraction heuristics.

## Robots, terms, and polite network behavior

The baseline standard is [RFC 9309, Robots Exclusion Protocol](https://www.rfc-editor.org/rfc/rfc9309.html).
Robots policy is host-specific: check the API host separately from a hosted job
page and separately from the employer's custom careers domain.

Implement its failure semantics, not just `Allow`/`Disallow`: follow up to five
redirects; a 4xx makes robots “unavailable” and RFC 9309 permits access, while a
5xx/network-unreachable robots file requires temporary complete disallow. Use a
previously cached valid file for no more than 24 hours in normal conditions.
Treat robots content as untrusted input and cap parsing size.

Live robots observations on 2026-08-25:

| Host | Observation |
|---|---|
| `boards-api.greenhouse.io` | `Disallow: /embed/`; API job path was not disallowed |
| `api.lever.co` | `Allow: /` and `Crawl-delay: 1` |
| `jobs.lever.co` | `Allow: /` for generic agents plus Cloudflare content signals; several named AI-training bots disallowed |
| `api.ashbyhq.com` | `/robots.txt` returned 401; rely on the documented public API contract and avoid unrelated paths |
| `jobs.ashbyhq.com` | disallowed `/meeting/`, `/b/`, and `/api/`; ordinary job paths were not disallowed |
| `api.smartrecruiters.com` | generic agents disallowed; see the narrowly scoped public-API policy conflict above |
| NVIDIA Workday tenant | advertised site sitemap; allowed public site path; disallowed `/talentcommunity/` |

`Crawl-delay` is not part of RFC 9309, but honor it when present as a courtesy.
Recommended defaults:

```text
User-Agent: H1BJobMonitor/{version} (+operator contact or project URL)
per-host concurrency: 1
per-host steady rate: 1 request/second
timeout: 10 seconds connect, 30 seconds total
max retries: 4
retry: 408, 425, 429, and transient 5xx only
backoff: full jitter, 1s base, 60s cap
Retry-After: always honor
robots cache: <=24 hours
```

Additional requirements:

- Conditional GET using ETag/`If-None-Match` worked live on Greenhouse, Lever,
  Ashby, and SmartRecruiters. Use it.
- Avoid retries on normal 400/401/403/404 responses. Repeated 404/410 should
  mark the source stale and trigger a logged configuration review.
- A 401/403, CAPTCHA, WAF challenge, or login gate is a stop signal, not
  something to bypass.
- Store only public job data. Never collect candidate data or invoke application
  submission endpoints.
- Add a random small scheduler offset so hundreds of sources do not all fire at
  exactly 00:00/12:00.
- Record `last_attempt_at`, `last_success_at`, status, response count, duration,
  ETag, and bounded error text per source.
- Do not erase previously seen jobs on one failed or partial crawl. Mark a job
  inactive only after a successful complete source snapshot (or a configured
  number of consecutive complete absences).

## First run and subsequent-run semantics

### First run

For a newly initialized source:

1. Retrieve all potentially recent records using the provider's supported
   paging and date strategy.
2. Normalize, deduplicate, and score.
3. Return a job as “posted in the past 7 days” only when an accepted posting
   date is at or after `now - 7 days` and has high or validated medium-high
   confidence.
4. Store every observed source ID, including irrelevant/old jobs, so run two
   does not emit the old board as new.
5. Quarantine unknown-date jobs from the first-run report rather than calling
   them recent.

### Subsequent runs

- A never-before-seen provider ID discovered after a successful initialized
  snapshot is `newly_discovered=true`.
- Preserve its provider posting date separately. A newly discovered ID can have
  an old/unknown posting date because of source expansion or a prior partial
  failure; report that distinction.
- If an existing ID's posting date advances (Ashby republish, SmartRecruiters
  release) or its payload changes materially, record an update event. Do not
  emit it as a brand-new job unless product policy explicitly treats reposts as
  new.
- Track source completeness. A failed page means the whole snapshot is partial;
  it must not close missing jobs or advance a “fully scanned” watermark.
- Keep a two-run overlap around time cutoffs to absorb clock skew and eventual
  consistency; deduplication makes overlap cheap.

## Representative connector test matrix

These tests should become deterministic fixture tests plus a small optional
live smoke suite:

| Test | Expected assertion |
|---|---|
| Greenhouse Datadog list | JSON object, jobs length equals meta total; nonempty IDs/titles; content decodes; exact detail date |
| Greenhouse old-but-updated record | `updated_at` does not pass recent-post filter when `first_published` is old |
| Lever Palantir pages | skip/limit produce distinct IDs; all pages dedup; JSON-LD date agrees with `createdAt` date |
| Lever null/missing fields fixture | missing country/team/department/salary does not fail normalization |
| Ashby Ramp list | `apiVersion == "1"`; unlisted fixture excluded; primary and secondary locations parsed from both address shapes |
| SmartRecruiters ServiceNow list/detail | 100-record max handled; detail sections joined; postingUrl/applyUrl separated |
| Workday NVIDIA list/detail | max page 20; later-page `total=0` ignored; >=2000 wrap detected; detail startDate and additional locations parsed |
| Workday localized/unknown `postedOn` fixture | optimizer refuses early stop and falls back to full scan |
| Sitemap index fixture | nested/gzipped maps, namespaces, limits, and host validation work |
| JSON-LD fixture | object, list, and `@graph` shapes; multiple locations; remote restrictions; expired post rejected |
| HTTP behavior | 304 is success/no change; 429 honors Retry-After; partial page failure does not close jobs |

Live smoke tests should assert only contract invariants, not volatile job counts,
titles, or dates. Store compact sanitized fixtures for normal unit tests so CI
does not repeatedly hit production ATS services.

## Suggested connector priority

1. Greenhouse
2. Ashby
3. Lever (with JSON-LD date validation)
4. SmartRecruiters (only under explicit documented-public-API policy)
5. Employer-provided sitemap + JSON-LD
6. Workday CXS after per-tenant access review

This ordering optimizes date accuracy, API stability, and request cost. It does
not imply company quality or sponsorship confidence.
