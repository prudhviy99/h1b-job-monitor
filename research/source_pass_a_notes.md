# Company universe batch A — research notes and sources

Research completed: **2026-08-25**  
Scope: **100 product employers** in large technology, cloud/infrastructure, cybersecurity, fintech/payments, data platforms, developer tools, and a limited set of engineering-heavy financial institutions.

## Result

- 100/100 employers have a directly verified official career presence.
- 100/100 have at least one **Certified** H-1B LCA in the official DOL FY2026 Q1 disclosure file.
- 72 are marked `high`, 24 `medium`, and 4 `low` under the conservative transfer-signal rubric below.
- Staffing firms, body shops, and job aggregators were deliberately excluded even when they appeared near the top of the filing data.

The structured output is `company_batch_a.csv`. It includes exact DOL petitioner names, recent filing counts, H-1B filing-basis signals, official career URLs, ATS types/endpoints, candidate-fit tags, and company-specific caveats.

## Primary sponsorship source

The quantitative evidence comes from these official U.S. Department of Labor sources:

- [DOL OFLC Performance Data landing page](https://www.dol.gov/agencies/eta/foreign-labor/performance)
- [FY2026 Q1 LCA disclosure workbook](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2026_Q1.xlsx)
- [FY2026 Q1 LCA record layout](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Record_Layout_FY2026_Q1.pdf)

The directly reproducible Q1 workbook contains determinations from **2025-10-01 through 2025-12-31**. It has 83,120 nonblank rows across all visa classes, including 79,852 H-1B rows. Of the H-1B rows, 71,782 have status exactly `Certified`.

The DOL landing page now advertises an FY2026 Q2 cumulative file covering 2025-10-01 through 2026-03-31, but its listed filename was not directly retrievable at the documented DOL file path during this research pass. To preserve reproducibility, the CSV uses the latest official workbook whose direct download and record layout were both successfully verified: FY2026 Q1. This is still recent federal evidence, not historical-only evidence.

## Extraction and matching method

1. Retained only rows where `VISA_CLASS == H-1B`.
2. Retained only rows where `CASE_STATUS == Certified`. `Certified - Withdrawn`, `Withdrawn`, and `Denied` were excluded from every company count.
3. Matched manually reviewed legal petitioner patterns case-insensitively. The exact matched names are preserved in `matched_dol_employer_names`; there is no fuzzy company-name joining.
4. Aggregated parent-company legal entities only when ownership/branding was clear, such as Amazon/AWS entities, Visa entities, Mastercard entities, and Dell entities.
5. Counted a filing as candidate-relevant when its title matched: `software`, `engineer`, `developer`, `platform`, `infrastructure`, `security`, `site reliability`, `sre`, `cloud`, `systems`, `devops`, `backend`, `distributed`, `data`, or `member of technical staff`.
6. Summed the DOL filing-basis fields `CHANGE_EMPLOYER`, `NEW_EMPLOYMENT`, and `CONTINUED_EMPLOYMENT` only across Certified H-1B cases. These are employer-reported **worker positions**, not petition approvals or confirmed hires, and may exceed the number of cases or overlap within a case.
7. Cross-checked every retained employer against an official company career page or a company-owned/linked ATS board. No company was admitted solely because it had historical sponsorship data.

## Confidence rubric

`high`

- At least 10 Certified H-1B cases in FY2026 Q1;
- at least 5 candidate-relevant title matches; and
- at least 5 employer-reported `CHANGE_EMPLOYER` positions.

`medium`

- At least one Certified FY2026 Q1 H-1B case; and
- at least one `CHANGE_EMPLOYER` or `NEW_EMPLOYMENT` position;
- but it does not meet all high-confidence volume thresholds.

`low`

- Recent Certified FY2026 Q1 H-1B evidence exists, usually in directly relevant engineering titles, but the quarter shows no `CHANGE_EMPLOYER` or `NEW_EMPLOYMENT` positions for the matched legal entity.

The four `low` entries are **Nutanix, Confluent, Fortinet, and Proofpoint**. They remain in the universe because their recent continued-employment sponsorship, active official career presence, and technical fit are real, but a transfer-seeking candidate should normally require `medium` or `high` confidence unless an individual posting or recruiter explicitly confirms transfer support.

## Career-site and ATS verification

The ATS mix in the CSV is:

| ATS/source type | Employers | Verification result on 2026-08-25 |
|---|---:|---|
| Greenhouse | 33 | 33/33 public board APIs returned HTTP 200 and nonempty job arrays |
| Workday | 17 | 17/17 tenant career roots returned HTTP 200 |
| Ashby | 7 | 7/7 public posting APIs returned HTTP 200 and nonempty job arrays |
| Oracle Recruiting | 5 | 5/5 candidate-experience roots returned HTTP 200 |
| SmartRecruiters | 1 | ServiceNow API returned HTTP 200 with active postings |
| Lever | 1 | Palantir API returned HTTP 200 with active postings |
| SAP SuccessFactors | 1 | NetApp official career root returned HTTP 200 |
| Avature | 1 | Bloomberg search endpoint returned HTTP 200 |
| Custom/company frontend | 34 | Official pages were checked individually; most returned HTTP 200 |

For Greenhouse, Ashby, and Lever rows, `ats_identifier_or_base_url` is the board token. For Workday, Oracle, SmartRecruiters, Avature, and custom API rows, it is a full base URL when a stable endpoint was found.

Several official custom career sites returned bot-defense responses to a plain command-line client even though the official pages and current listings were independently visible: Nutanix and Akamai (`403`), Arista and Uber (`406`), and Expedia, PayPal, and Fidelity (`403`). They are marked `custom`; a monitor should use a documented public API/sitemap if found later, obey robots/terms, rate-limit heavily, and fail gracefully rather than bypass access controls.

Representative structured endpoints verified during this pass include:

- Greenhouse: Cloudflare, Datadog, MongoDB, Databricks, DoorDash, Airbnb, Lyft, Pinterest, Reddit, Roblox, Discord, Affirm, Brex, Okta, Zscaler, Rubrik, Netskope, Anthropic, Figma, and others.
- Ashby: Snowflake, Confluent, Ramp, Vanta, Gen Digital, OpenAI, and Notion.
- Workday: NVIDIA, Adobe, Cisco, Intel, HPE, Workday, Autodesk, Red Hat, F5, Visa, Mastercard, Wells Fargo, Remitly, CrowdStrike, Palo Alto Networks, Qualys, and Proofpoint.
- Oracle: Oracle, Dell, JPMorgan Chase, American Express, and Fortinet.

## Candidate-fit review

This batch was selected for a candidate with Amazon/AWS Shield experience in backend services, distributed systems, security, multi-region infrastructure, Java/Spring, Kinesis/Kafka, DynamoDB/RDS, and approximately 3.5 years of experience.

- Cloud/data/security employers received tags for backend, platform, infrastructure, SRE, distributed systems, or security.
- Banks and payments companies received Java/Spring/AWS/Kafka/backend/security tags because those are recurring role families in their engineering organizations and align with the candidate profile.
- Hardware-heavy employers were retained only because they also operate substantial cloud, systems software, platform, infrastructure, or security teams; their caveats explicitly tell the crawler to reject silicon, firmware, embedded, and unrelated hardware roles.
- Very selective or senior-skewing employers are retained as targeted opportunities, with caveats to require explicit 3–5 YOE fit rather than trusting titles such as `Senior` or `Member of Technical Staff`.

Examples of deliberately excluded high-volume filers include Cognizant, TCS, Infosys, Wipro, LTIMindtree, Mphasis, Compunnel, Randstad Digital, Kforce, and similar staffing/outsourcing firms. Their exclusion is intentional, not an omission caused by lack of sponsorship data.

## Legal-name and rebrand notes

- **Everpure:** Pure Storage, Inc. changed its corporate name to Everpure, Inc. on 2026-02-23. The DOL Q1 evidence and active Greenhouse board token still use `PURE STORAGE, INC.` / `purestorage`. See the [company FAQ](https://blog.everpuredata.com/news-events/faq-pure-storage-to-become-everpure/) and [SEC Form 8-K](https://www.sec.gov/Archives/edgar/data/1474432/000147443226000011/pstg-20260223.htm).
- **Instacart:** matched to DOL petitioner `Maplebear Inc.`.
- **Rippling:** matched to `People Center, Inc. d/b/a Rippling`.
- **Amazon:** aggregates clearly branded Amazon.com Services, AWS, Development Center U.S., and Data Services petitioners; exact names remain in the CSV.

## Important limitations

- An LCA is a required labor-attestation step, not proof that USCIS approved a petition, that the worker started, or that an employer will sponsor a particular open job.
- Company-level sponsorship history must never override a posting that says sponsorship is unavailable.
- `CHANGE_EMPLOYER` is the strongest transfer-oriented signal available in this DOL file, but its value is the number of worker positions the employer entered, not a count of completed transfers.
- Title matching is a screening heuristic. The job monitor still needs full-description YOE, seniority, location, and skill filtering.
- Employer legal names and ATS platforms can change. Revalidate the company configuration periodically, especially after acquisitions or rebrands.
- The list is deliberately product-company-heavy and quality-filtered; it is broad but not a claim that every legitimate U.S. sponsor is included.
