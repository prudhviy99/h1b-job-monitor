# Research and verification methodology

Research cut: **2026-08-25**

## Candidate definition

The ranking profile is anchored to the updated one-page master resume dated August 25, 2026, and the exact profile confirmed in the referenced job-search conversation. The PDF itself is not committed because it contains personal contact information.

- Capital One Software Engineer contract beginning June 2026, with Java/Spring Boot APIs and Python/FastAPI services;
- AWS Software Development Engineer, AWS Shield / DDoS Protection, October 2022-April 2026;
- professionally evidenced Java/Spring backend services, Kinesis telemetry, DynamoDB/RDS, multi-region AWS delivery, DDoS/security, and production on-call ownership;
- project-backed Spring WebFlux, Redis/Lua, NGINX, rate limiting, circuit breakers, observability, Spring AI, RAG, MCP, and pgvector;
- target SWE II/SDE II/mid-level and only selective Senior roles whose requirements remain in the 3-5 year band.

The month-only employment dates support approximately 3.75 years of relevant US experience as of August 26, 2026. The crawler does not infer six-plus years, formal Staff/leadership level, production AI/ML experience, or employment depth for skills-only entries such as Kafka/MSK. AI project terms receive lower weight and can strengthen only a software/backend/platform title; pure AI/ML/scientist titles remain excluded. The profile file is `config/profile.json`.

## Independent employer passes

Two independent passes produced 200 researched rows that merge to 149 unique direct employers.

Pass A focused on technology, cloud, infrastructure, security, fintech, data, and developer tools. It matched exact legal petitioners against the official DOL FY2026 Q1 LCA disclosure file, retained only Certified H-1B cases, counted candidate-relevant titles, and separately summed new-employment, change-employer, and continued-employment positions. It verified 100 official career routes and structured ATS identities.

Pass B broadened enterprise SaaS, banks/payments, insurance, healthcare technology, telecom, semiconductors/hardware software organizations, autonomy/transportation, and retail/logistics. It independently matched legal employers against official FY2025 Q4 disclosure data and rechecked official careers/ATS routes. Its recent-record counts combine `Certified` and `Certified - Withdrawn` cases; the audit calls these `recent_lca_records` rather than implying they are all currently Certified.

Duplicates prefer Pass A's newer FY2026 evidence while retaining combined tags and source URLs. The exact merge output is `company_universe.csv`; the machine configuration is `../config/companies.json`.

## Primary sources

- DOL OFLC Performance Data: https://www.dol.gov/agencies/eta/foreign-labor/performance
- FY2026 Q1 LCA disclosure workbook: https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2026_Q1.xlsx
- FY2026 Q1 record layout: https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Record_Layout_FY2026_Q1.pdf
- FY2025 Q4 LCA disclosure workbook: https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q4.xlsx
- DOL FLAG LCA program explanation: https://flag.dol.gov/programs/LCA

The DOL performance page advertises a newer cumulative FY2026 Q2 release, but the research pass used FY2026 Q1 for its primary reproducible calculations because both the direct workbook and its record layout were successfully retrieved and verified. The secondary pass uses the complete FY2025 Q4 file. The evidence period is explicit per row; it is never mislabeled as live requisition-level sponsorship.

## Legal-employer controls

- No fuzzy joins were used for the primary pass; every matched petitioner name is retained in the audit CSV.
- Parent-company entities were combined only when the ownership/branding link was clear.
- Common-substring traps such as Box/Dropbox, Arm/Farm, Cisco/San Francisco, Ford/Stanford, and Charter schools were excluded.
- Staffing, recruiting, outsourcing, body-shop, and aggregator employers were excluded even when filing volume was large.

## Confidence and caveats

Pass A's high-confidence threshold requires at least 10 Certified H-1B cases, at least five candidate-relevant title matches, and at least five change-employer positions in FY2026 Q1. Medium requires recent Certified evidence plus a new/change-employer signal. Low means current Certified evidence exists but no recent new/change-employer signal was observed.

Pass B uses a similar sector-broadening rubric from FY2025 Q4. Its exact counts, case-status basis, and legal names remain in the source pass notes and the merged audit CSV.

`CHANGE_EMPLOYER` is the most relevant DOL transfer-oriented signal, but it is an employer-entered worker-position count on an LCA. It is not proof of an approved or completed H-1B transfer. Certified LCAs also do not establish that a current role sponsors. Posting-level restrictions override every company score.

## Career-source verification

Official company career pages were followed to their ATS or first-party routes. Greenhouse board tokens, Ashby board names, Lever site names, SmartRecruiters identifiers, and Workday tenant/site components were checked against returned employer/job URLs. ATS identifiers were not admitted solely because a guessed endpoint returned HTTP 200.

The implementation favors vendor-documented public read APIs. Workday and undocumented/custom sources stay disabled when a safe access basis is not established. This produces lower coverage than indiscriminate scraping and substantially higher confidence in provenance.

A third access-focused pass audited 39 difficult official career routes against live robots rules, linked terms, sitemap completeness, stable URL structure, and `JobPosting.datePosted`. Sixteen sitemap/JSON-LD routes were enabled, Amazon retained its dedicated first-party JSON connector, and 22 ambiguous, prohibited, incomplete, or unsupported routes remained disabled. The row-level audit is `coverage_expansion_audit.csv`.

## Job-level controls

The source-specific posting date must have acceptable confidence. Greenhouse uses `first_published`, never `updated_at`. Lever's undocumented millisecond value is validated against hosted JSON-LD for recent candidates. Ashby uses `publishedAt` and labels it last-published. SmartRecruiters uses `releasedDate`. Workday, when explicitly enabled, uses detail `jobPostingInfo.startDate`. Generic pages require schema.org `JobPosting.datePosted` by default.

After date verification, the pipeline applies role shape, title/seniority, ATS department scope, experience, US location, resume-aligned skills, employer sponsorship confidence, and posting-level work-authorization language. An eligible title must be an actual software/development/SDE/SWE/MTS/SRE or explicitly software-aligned backend/platform/infrastructure/security/systems role; a loose domain word cannot rescue customer, sales, advocacy, product, administration, field, or generic systems work. Operations titles require software-development evidence. Pure frontend/mobile/QA/data-science/ML-research/robotics departments are rejected, with a narrow secondary exception for ML/AI platform or infrastructure work.

Java/Spring, Python/FastAPI, AWS, backend/distributed systems, API, and Shield/DDoS/security work form the professional core-evidence gate. Skills present only as a project or skills-list entry are lower-weight secondary evidence; explicit multi-year requirements beyond the resume's established depth reject the role. AI platform, ML infrastructure, and the narrow streaming/telemetry Data Engineer exception can never receive P0.

Experience extraction recognizes common numeric/word/range forms, degree-versus-experience alternatives, and both normal and HTML-flattened Minimum/Preferred Qualifications sections. The candidate's Master's degree selects the applicable degree branch without silently discarding unrelated higher experience requirements. Explicit Senior roles require a verifiable floor of three to five years; common staff-level title codes and level-IV/VI+ forms are rejected.

The technical score is capped at 90: title evidence contributes at most 30, skill groups 42, breadth 6, and experience fit 12. Sponsorship, location, and broad company tags do not add technical points; sponsorship remains a separate gate and priority condition. This prevents keyword inventories or employer reputation from rescuing a weak role. Every rejected job retains reasons in the run audit.

The matching configuration is fingerprinted per company and connector. A profile change causes a one-time seven-day re-evaluation for every complete source without resetting the SQLite database. Previously delivered roles remain suppressed; failed or incomplete sources retain the old fingerprint and retry on a later run.
