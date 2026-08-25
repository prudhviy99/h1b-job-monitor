# Company universe — batch B research sources

**Research cut:** 2026-08-25. **Universe size:** 100 employers. **Scope:** enterprise SaaS/security, banking/payments, insurance, healthcare technology, telecom, semiconductor/hardware software organizations, autonomy/transportation, and retail/marketplace/logistics engineering.

## Primary evidence and method

- Sponsorship evidence comes from the [U.S. Department of Labor OFLC FY2025 Q4 LCA disclosure workbook](https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2025_Q4.xlsx), linked from the [official OFLC Performance Data page](https://www.dol.gov/agencies/eta/foreign-labor/performance). The quarter covers determinations issued July–September 2025. Each row was matched to exact or tightly anchored legal-employer names; common-substring false positives (for example, Box/Dropbox, Arm/Farm, Cisco/San Francisco, Ford/Stanford, and Charter schools) were excluded.
- DOL explains the LCA process on the [official FLAG LCA page](https://flag.dol.gov/programs/LCA). A certified LCA permits an employer to proceed to a USCIS petition; it is not itself a petition approval, proof of a filled job, or a guarantee that every open role sponsors.
- `certified_records` counts both `Certified` and `Certified - Withdrawn` determinations. `softwareish_records` is a conservative reported job-title or SOC-title heuristic covering software/developer/engineer/platform/infrastructure/security/SRE/cloud/systems/application terms. `change_employer_positions` sums DOL's `CHANGE_EMPLOYER` field and can exceed record count because one LCA can cover multiple positions.
- Every careers link points either to the employer's official domain or its linked first-party ATS tenant. ATS identifiers are crawler seeds, not claims that an undocumented endpoint is stable; custom/Phenom/Eightfold sites may require adapters or sitemap discovery.
- Career/ATS URLs were HTTP-smoke-checked on 2026-08-25. Eighty-three of 100 returned 2xx to a simple client; the remainder returned bot controls, certificate-chain errors, or ATS 5xx responses and were retained only where the official careers page or search indexing corroborated the route. Direct API checks returned 200 for the listed Greenhouse boards, the ServiceNow/Zscaler/Intuitive/Western Digital SmartRecruiters tenants, and the Palantir/Zoox Lever tenants.
- Staffing firms, outsourcing consultancies/body shops, job aggregators, and companies without a current official careers presence were excluded.

## Confidence rubric

- **High:** at least 20 certified quarter records, at least 8 software-like records, and at least 3 `CHANGE_EMPLOYER` positions.
- **Medium-high:** at least 20 certified quarter records and at least 8 software-like records, but fewer than 3 observed change-employer positions.
- **Medium:** smaller but still current, directly observed employer-level LCA activity with relevant software-like titles. Confirm transfer support before investing in a lengthy application.

Distribution: high=85, medium-high=5, medium=10.

## Employer-by-employer audit index

### Enterprise SaaS

| Employer | Confidence | FY25-Q4 certified / software-like / change-employer positions | Official careers / ATS |
|---|---:|---:|---|
| Salesforce | high | 445 / 410 / 140 | [custom](https://www.salesforce.com/company/careers/jobs/) |
| ServiceNow | high | 116 / 99 / 81 | [smartrecruiters](https://careers.servicenow.com/jobs/) |
| Adobe | high | 136 / 111 / 44 | [phenom](https://careers.adobe.com/us/en/search-results) |
| Workday | high | 53 / 49 / 11 | [workday](https://workday.wd5.myworkdayjobs.com/Workday) |
| Atlassian | high | 92 / 80 / 38 | [custom](https://www.atlassian.com/company/careers/all-jobs) |
| Snowflake | high | 110 / 100 / 64 | [phenom](https://careers.snowflake.com/us/en/search-results) |
| Datadog | high | 25 / 20 / 9 | [greenhouse](https://careers.datadoghq.com/) |
| Cloudflare | high | 27 / 24 / 10 | [greenhouse](https://www.cloudflare.com/careers/jobs/) |
| MongoDB | high | 45 / 39 / 91 | [greenhouse](https://www.mongodb.com/company/careers/teams/engineering) |
| Confluent | high | 34 / 31 / 7 | [custom](https://careers.confluent.io/open-positions/united_states) |
| Okta | high | 35 / 29 / 8 | [greenhouse](https://www.okta.com/company/careers/) |
| Twilio | high | 35 / 32 / 7 | [greenhouse](https://jobs.twilio.com/careers) |
| HubSpot | high | 31 / 27 / 7 | [greenhouse](https://www.hubspot.com/careers/jobs) |
| Zoom | high | 20 / 17 / 11 | [workday](https://careers.zoom.us/jobs/search) |
| DocuSign | high | 71 / 66 / 30 | [phenom](https://careers.docusign.com/careers-home/jobs/) |
| Dropbox | medium | 14 / 10 / 5 | [custom](https://www.dropbox.jobs/en/jobs/) |
| Box | high | 30 / 30 / 10 | [greenhouse](https://www.box.com/careers/jobs) |
| Nutanix | high | 32 / 29 / 6 | [workday](https://nutanix.wd1.myworkdayjobs.com/Nutanix) |
| Palantir | medium | 16 / 12 / 8 | [lever](https://www.palantir.com/careers/) |
| CrowdStrike | high | 40 / 34 / 8 | [workday](https://crowdstrike.wd5.myworkdayjobs.com/crowdstrikecareers) |
| Zscaler | high | 24 / 22 / 9 | [smartrecruiters](https://www.zscaler.com/careers/search) |
| Palo Alto Networks | high | 97 / 88 / 189 | [phenom](https://jobs.paloaltonetworks.com/en/search-jobs) |
| Rubrik | high | 22 / 18 / 5 | [greenhouse](https://www.rubrik.com/company/careers) |
| Samsara | medium | 13 / 9 / 5 | [greenhouse](https://www.samsara.com/company/careers/roles) |
| Figma | medium | 9 / 5 / 4 | [greenhouse](https://www.figma.com/careers/) |

### Banking & Payments

| Employer | Confidence | FY25-Q4 certified / software-like / change-employer positions | Official careers / ATS |
|---|---:|---:|---|
| JPMorgan Chase | high | 629 / 475 / 39 | [oracle](https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/jobs) |
| Capital One | high | 220 / 113 / 58 | [phenom](https://www.capitalonecareers.com/search-jobs) |
| Goldman Sachs | high | 287 / 156 / 93 | [custom](https://higher.gs.com/results) |
| Morgan Stanley | high | 216 / 156 / 57 | [eightfold](https://morganstanley.eightfold.ai/careers) |
| Bank of America | high | 139 / 103 / 12 | [custom](https://careers.bankofamerica.com/en-us/job-search) |
| Citi | high | 425 / 271 / 64 | [phenom](https://jobs.citi.com/search-jobs) |
| Wells Fargo | high | 116 / 86 / 39 | [custom](https://www.wellsfargojobs.com/en/jobs/) |
| American Express | high | 165 / 140 / 62 | [oracle](https://careers.americanexpress.com/en/sites/CX_1/jobs) |
| Visa | high | 170 / 144 / 24 | [workday](https://visa.wd5.myworkdayjobs.com/Visa) |
| Mastercard | high | 172 / 159 / 23 | [phenom](https://careers.mastercard.com/us/en/search-results) |
| PayPal | high | 225 / 178 / 86 | [eightfold](https://paypal.eightfold.ai/careers) |
| Block | high | 35 / 23 / 8 | [greenhouse](https://block.xyz/careers/jobs) |
| Stripe | high | 58 / 38 / 17 | [custom](https://stripe.com/careers/search) |
| Fiserv | high | 94 / 91 / 33 | [phenom](https://careers.fiserv.com/us/en) |
| Fidelity Investments | high | 516 / 474 / 108 | [custom](https://jobs.fidelity.com/en/jobs/) |
| Charles Schwab | high | 124 / 118 / 22 | [phenom](https://www.schwabjobs.com/search-jobs) |
| State Street | high | 98 / 67 / 11 | [workday](https://statestreet.wd1.myworkdayjobs.com/Global) |
| Coinbase | high | 29 / 23 / 17 | [greenhouse](https://www.coinbase.com/careers/positions) |

### Insurance

| Employer | Confidence | FY25-Q4 certified / software-like / change-employer positions | Official careers / ATS |
|---|---:|---:|---|
| Progressive | medium | 18 / 14 / 1 | [custom](https://careers.progressive.com/search/jobs) |
| Liberty Mutual | high | 34 / 21 / 5 | [eightfold](https://searchjobs.libertymutualgroup.com/careers) |
| Travelers | medium | 17 / 15 / 3 | [workday](https://careers.travelers.com/job-search-results/) |
| Nationwide | medium | 16 / 13 / 0 | [workday](https://nationwide.wd1.myworkdayjobs.com/Nationwide_Career) |
| Northwestern Mutual | medium-high | 34 / 32 / 2 | [custom](https://careers.northwesternmutual.com/) |
| State Farm | medium | 16 / 16 / 0 | [custom](https://jobs.statefarm.com/main/jobs) |

### Healthcare Technology

| Employer | Confidence | FY25-Q4 certified / software-like / change-employer positions | Official careers / ATS |
|---|---:|---:|---|
| UnitedHealth Group / Optum | high | 150 / 136 / 12 | [phenom](https://careers.unitedhealthgroup.com/job-search-results/) |
| CVS Health / Aetna | high | 266 / 230 / 68 | [phenom](https://jobs.cvshealth.com/us/en/search-results) |
| The Cigna Group / Evernorth | high | 108 / 93 / 5 | [phenom](https://jobs.thecignagroup.com/us/en/search-results) |
| Humana | high | 78 / 68 / 17 | [workday](https://humana.wd5.myworkdayjobs.com/Humana_External_Career_Site) |
| Elevance Health | medium-high | 113 / 94 / 0 | [workday](https://careers.elevancehealth.com/) |
| Centene | high | 38 / 35 / 4 | [custom](https://jobs.centene.com/us/en/jobs/) |
| Medtronic | high | 57 / 46 / 10 | [workday](https://medtronic.wd1.myworkdayjobs.com/MedtronicCareers) |
| Intuitive Surgical | high | 62 / 47 / 14 | [smartrecruiters](https://careers.intuitive.com/en/jobs/) |
| Illumina | high | 26 / 20 / 4 | [workday](https://illumina.wd1.myworkdayjobs.com/illumina-careers) |
| Veeva Systems | medium-high | 33 / 29 / 0 | [custom](https://careers.veeva.com/job-search-results/) |

### Telecom

| Employer | Confidence | FY25-Q4 certified / software-like / change-employer positions | Official careers / ATS |
|---|---:|---:|---|
| Verizon | high | 82 / 76 / 4 | [custom](https://mycareer.verizon.com/jobs/) |
| AT&T | high | 125 / 109 / 46 | [phenom](https://www.att.jobs/search-jobs) |
| T-Mobile | high | 128 / 108 / 39 | [custom](https://careers.t-mobile.com/jobs) |
| Comcast | high | 159 / 151 / 8 | [phenom](https://jobs.comcast.com/search-jobs) |
| Charter Communications / Spectrum | high | 189 / 169 / 4 | [phenom](https://jobs.spectrum.com/search-jobs) |
| Nokia | high | 37 / 37 / 10 | [oracle](https://jobs.nokia.com/en/sites/CX_1) |

### Semiconductors & Hardware

| Employer | Confidence | FY25-Q4 certified / software-like / change-employer positions | Official careers / ATS |
|---|---:|---:|---|
| NVIDIA | high | 470 / 436 / 2058 | [workday](https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite) |
| Intel | high | 282 / 276 / 6 | [phenom](https://jobs.intel.com/en/search-jobs) |
| AMD | high | 125 / 123 / 51 | [custom](https://careers.amd.com/careers-home/jobs) |
| Cisco | high | 196 / 178 / 380 | [custom](https://careers.cisco.com/global/en) |
| Broadcom | high | 22 / 22 / 13 | [workday](https://broadcom.wd1.myworkdayjobs.com/External_Career) |
| Marvell | high | 49 / 47 / 16 | [workday](https://marvell.wd1.myworkdayjobs.com/MarvellCareers) |
| Micron Technology | high | 91 / 81 / 20 | [eightfold](https://careers.micron.com/careers) |
| Applied Materials | high | 53 / 45 / 15 | [workday](https://amat.wd1.myworkdayjobs.com/External) |
| Lam Research | high | 22 / 20 / 10 | [workday](https://lamresearch.wd1.myworkdayjobs.com/Lam_External) |
| KLA | high | 42 / 39 / 21 | [workday](https://kla.wd1.myworkdayjobs.com/Search) |
| Synopsys | medium | 14 / 14 / 166 | [phenom](https://careers.synopsys.com/search-jobs) |
| Cadence Design Systems | high | 54 / 52 / 14 | [workday](https://cadence.wd1.myworkdayjobs.com/External_Careers) |
| Arm | high | 44 / 42 / 21 | [phenom](https://careers.arm.com/search-jobs) |
| Western Digital | high | 77 / 74 / 177 | [smartrecruiters](https://jobs.smartrecruiters.com/WesternDigital) |
| Hewlett Packard Enterprise | high | 85 / 79 / 6 | [phenom](https://careers.hpe.com/us/en/search-results) |
| Dell Technologies | high | 135 / 88 / 6 | [oracle](https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/careers/jobs) |

### Autonomy & Transportation

| Employer | Confidence | FY25-Q4 certified / software-like / change-employer positions | Official careers / ATS |
|---|---:|---:|---|
| Uber | high | 182 / 124 / 64 | [custom](https://www.uber.com/us/en/careers/list/) |
| Lyft | high | 26 / 18 / 14 | [greenhouse](https://www.lyft.com/careers) |
| Waymo | high | 41 / 38 / 14 | [eightfold](https://careers.withwaymo.com/jobs/search) |
| Zoox | high | 53 / 49 / 10 | [lever](https://jobs.lever.co/zoox) |
| Rivian | high | 152 / 138 / 56 | [custom](https://careers.rivian.com/careers-home/jobs) |
| Tesla | high | 357 / 325 / 60 | [custom](https://www.tesla.com/careers/search/) |
| Aurora Innovation | medium | 6 / 6 / 4 | [custom](https://aurora.tech/careers/) |
| General Motors | high | 188 / 184 / 61 | [phenom](https://search-careers.gm.com/en/jobs/) |
| Ford | high | 184 / 169 / 27 | [oracle](https://efds.fa.em5.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs) |

### Retail, Marketplaces & Logistics

| Employer | Confidence | FY25-Q4 certified / software-like / change-employer positions | Official careers / ATS |
|---|---:|---:|---|
| Airbnb | high | 50 / 41 / 17 | [greenhouse](https://careers.airbnb.com/positions/) |
| DoorDash | high | 108 / 73 / 53 | [greenhouse](https://careersatdoordash.com/jobs/) |
| Target | medium-high | 58 / 44 / 2 | [custom](https://corporate.target.com/careers/job-search) |
| The Home Depot | high | 75 / 45 / 13 | [custom](https://careers.homedepot.com/job-search-results/) |
| Lowe's | medium-high | 85 / 84 / 1 | [phenom](https://talent.lowes.com/us/en/search-results) |
| Costco Wholesale | high | 37 / 37 / 9 | [taleo](https://phf.tbe.taleo.net/phf02/ats/careers/v2/searchResults?org=COSTCO&cws=41) |
| Nike | high | 66 / 53 / 5 | [custom](https://careers.nike.com/jobs) |
| Starbucks | high | 69 / 63 / 11 | [eightfold](https://apply.starbucks.com/careers) |
| Chewy | high | 40 / 25 / 8 | [phenom](https://careers.chewy.com/us/en/search-results) |
| eBay | high | 119 / 88 / 25 | [phenom](https://jobs.ebayinc.com/us/en/search-results) |

## Operational cautions

1. Re-check sponsorship at the posting level. Wording such as “no current or future sponsorship” overrides employer-level evidence.
2. For an H-1B transfer search, prioritize employers with observed `CHANGE_EMPLOYER` positions, then confirm with the recruiter before interviews.
3. Hardware, autonomous-vehicle, telecom, retail, and healthcare employers have large nonmatching catalogs. Apply the role-fit and seniority filters before surfacing jobs.
4. A missing posting date is not evidence that a job is new. Use first-seen time separately and label it clearly.
5. ATS migrations happen. The official careers URL is canonical; an ATS identifier should be re-discovered if it stops resolving.

The machine-readable CSV retains matched legal-employer names and raw audit counts so future refreshes can be diffed and independently checked.
