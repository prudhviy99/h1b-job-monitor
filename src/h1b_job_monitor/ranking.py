from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .models import Company, Decision, Job


INTERNSHIP = re.compile(r"\b(intern(ship)?|co-?op|apprentice)\b", re.I)
NEW_GRAD = re.compile(
    r"\b(new (?:college )?grad(?:uate)?|recent grad(?:uate)?|university grad|graduate|campus|early career|"
    r"(?:early|emerging|entry) talent|entry[ -]level|junior|jr\.?|associate|trainee|AMTS)\b",
    re.I,
)
EARLY_CAREER_METADATA = re.compile(
    r"\b(university recruiting|campus programs?|early careers?|student programs?|"
    r"new grad(?:uate)?|university grad(?:uate)?|entry[ -]level)\b",
    re.I,
)
IRRELEVANT_DEPARTMENT = re.compile(
    r"\b(iOS|Android|mobile|front[ -]?end|UI|UX|user interface|quality (?:assurance|engineering)|"
    r"QA|test(?:ing)? engineering|software test|validation|verification|V&V|customer engineering|"
    r"professional services|sales engineering|solutions engineering|technical support|customer support|"
    r"developer relations|data science|machine learning|artificial intelligence|ML|AI|robotics|"
    r"hardware|firmware|embedded)\b",
    re.I,
)
SECONDARY_PLATFORM_DEPARTMENT = re.compile(
    r"^(?=.*\b(?:machine learning|artificial intelligence|ML|AI)\b)"
    r"(?=.*\b(?:platform|infrastructure|systems?|serving|runtime|reliability|security)\b).*$",
    re.I,
)
MANAGEMENT = re.compile(
    r"\b(manager|mgr\.?|supervisor|director|head of|vice president|vp|people leader|team leader|"
    r"engineering leader|group leader|technical leader)\b",
    re.I,
)
TOO_SENIOR = re.compile(
    r"\b(staff|principal|distinguished|fellow|chief|architect|lead|LMTS|PMTS|DMTS)\b|"
    r"\b(?:master|advisory|expert)\s+(?:software\s+)?(?:engineer|developer)\b|"
    r"\b(?:engineer|developer)\s*[,/-]?\s*(?:master|advisory|expert)\b",
    re.I,
)
LEVEL_ROLE_STEM = (
    r"(?:software (?:(?:development|dev|developer) )?engineer|software developer|"
    r"systems development engineer|(?:security|cloud|platform|infrastructure) development engineer|"
    r"sde|swe|sre|mts|member of technical staff|site reliability engineer|"
    r"(?:backend|back-end|platform|infrastructure|security|systems?|production|cloud|reliability|"
    r"devops|devsecops|observability|telemetry|data|api|java|python) "
    r"(?:software )?(?:engineer|developer))"
)
JUNIOR_LEVEL = re.compile(
    rf"\b{LEVEL_ROLE_STEM}\s*[,/\-]?\s*(?:level\s*)?(?:i(?!\s*[/\-]\s*o\b)|1)\b",
    re.I,
)
TOO_HIGH_LEVEL = re.compile(
    rf"\b{LEVEL_ROLE_STEM}\s*[,/\-]?\s*(?:level\s*)?(?:iv|v|vi|vii|viii|ix|x|[4-9]|10)\b|"
    r"\bengineer\s*[,/\-]?\s*(?:vi|vii|viii|ix|x|[6-9]|10)\b|"
    r"\b(?:L|IC|E)\s*[- ]?(?:6|7|8|9|10)\b",
    re.I,
)
SENIOR = re.compile(
    rf"\b(?:senior|sr\.?|senior associate|principal associate|senior member of technical staff|SMTS|member of technical staff|MTS|"
    rf"{LEVEL_ROLE_STEM}\s*[,/\-]?\s*(?:level\s*)?(?:iii|3))\b",
    re.I,
)
TARGET_TITLE = re.compile(
    r"\b(?:SDE|SWE|SRE|MTS)\b|"
    r"\bmember of technical staff\b|"
    r"\bsoftware (?:(?:development|dev) )?(?:engineer|developer)\b|"
    r"\bsystems development engineer\b|"
    r"\b(?:security|cloud|platform|infrastructure) development engineer\b|"
    r"\b(?:backend|back-end|backend platform|cloud platform|cloud infrastructure|data platform|"
    r"developer platform|security platform|platform reliability|application security|network security|"
    r"platform|infrastructure|site reliability|reliability|production|security|cloud|"
    r"distributed systems?|systems software|software systems|devops|devsecops|api|java|python|"
    r"observability|telemetry) "
    r"(?:software )?(?:engineer|developer)\b",
    re.I,
)
IRRELEVANT_TITLE = re.compile(
    r"\b(front[ -]?end|ui engineer|ux|mobile|ios|android|robotics|embedded|firmware|hardware|"
    r"machine learning(?![ /-]*(?:platform|infrastructure|systems|serving|runtime|reliability|security))|"
    r"ML engineer|AI engineer|AI systems engineer|applied AI(?![ /-]*(?:platform|infrastructure|systems))|"
    r"deep learning|edge AI|physical.{0,20}AI|data engineer|data science|data scientist|data analyst|"
    r"business analyst|full[ -]?stack|product engineer|SDET|software (?:development )?engineer (?:in|for) test|"
    r"(?:software )?quality engineer|qa|quality assurance|test engineer|test automation|testing|"
    r"validation engineer|(?:GRC|compliance|risk) (?:analyst|engineer|specialist|manager)|"
    r"(?:analyst|engineer|specialist|manager)[, /-]+(?:GRC|compliance|risk)|SOC|penetration test|pentest|red team|"
    r"offensive security|security analyst|client platform security|endpoint security|corporate security|"
    r"security engineer.{0,30}privacy|security engineer.{0,40}(?:incident response|detection and response)|"
    r"console frameworks?|AI devops|DRTM|secure launch|customer reliability|support reliability|customer success|"
    r"technical escalations?|"
    r"(?:solutions?|sales) engineer|consultant|(?:platform|cloud|infrastructure|security|systems?) specialist|recruiter|"
    r"(?:test|testing|QA|quality|verification|validation|V&V) (?:platform|infrastructure|systems?)|"
    r"build (?:&|and) test|"
    r"product manager|program manager|project manager|solutions architect|"
    r"customer support|technical support|designer|applied scientist|research engineer|research scientist)\b",
    re.I,
)
GOVERNMENT_RESTRICTION = re.compile(
    r"\b(federal role|must be (?:a )?U\.?S\.? citizen|U\.?S\.? citizenship (?:is )?required|"
    r"active (?:U\.?S\.?\s+)?(?:government\s+)?(?:security )?clearance|"
    r"requires? (?:a )?(?:U\.?S\.?\s+)?(?:government\s+)?(?:security )?clearance|"
    r"eligible for (?:a )?(?:U\.?S\.? )?security clearance|"
    r"(?:eligib(?:le|ility)|ability|willingness)(?:\s+and\s+willingness)?\s+to\s+"
    r"(?:obtain|maintain|hold).{0,50}(?:U\.?S\.?|government|secret|top\s+secret|TS(?:/SCI)?).{0,35}clearance|"
    r"(?:U\.?S\.?\s+persons?\s+(?:is\s+)?required|must\s+be\s+(?:a\s+)?U\.?S\.?\s+persons?)|"
    r"(?:U\.?S\.?\s+citizen|green\s+card\s+holder).{0,30}\bonly|"
    r"(?:must|required\s+to)\s+(?:possess|maintain|obtain)\s+(?:an?\s+)?(?:secret|top\s+secret|TS(?:/SCI)?|security)\s+clearance|"
    r"requires?\s+(?:ITAR|export[- ]control)\s+eligibility|"
    r"export[- ]control\s+laws?.{0,140}(?:may|must|need).{0,100}legal\s+status\s+requirements?|"
    r"(?:ITAR|export[- ]controls?).{0,70}(?:must|require).{0,35}U\.?S\.?\s+persons?|"
    r"(?:top\s+secret|TS/SCI)(?:\s+clearance)?|"
    r"requires?.{0,100}(?:candidate.{0,35})?be\s+(?:a\s+)?U\.?S\.?\s+citizens?|"
    r"(?:must|required\s+to)\s+be\s+(?:eligible|able)\s+to\s+(?:obtain|maintain|hold)"
    r"(?:\s+and\s+maintain)?\s+(?:an?\s+)?(?:security|secret|top\s+secret|TS(?:/SCI)?)\s+clearance|"
    r"(?:ability|eligibility)\s+to\s+(?:obtain|maintain|hold).{0,30}"
    r"(?:security|secret|top\s+secret|TS(?:/SCI)?)\s+clearance\s+(?:is\s+)?required|"
    r"must\s+(?:have\s+or\s+)?be\s+able\s+to\s+(?:obtain|maintain|hold).{0,25}"
    r"(?:security|secret|top\s+secret|TS(?:/SCI)?)\s+clearance|"
    r"must\s+be\s+eligible\s+for\s+(?:an?\s+)?(?:security|secret|top\s+secret|TS(?:/SCI)?)\s+clearance|"
    r"clearance\s+eligibility\s+(?:is\s+)?required|"
    r"must\s+be\s+(?:a\s+)?citizen\s+of\s+the\s+United\s+States|"
    r"(?:only\s+U\.?S\.?\s+citizens?\s+may\s+apply|open\s+only\s+to\s+U\.?S\.?\s+citizens?)|"
    r"limited\s+to\s+(?:U\.?S\.?|United\s+States)\s+persons?|"
    r"must\s+be\s+(?:a\s+)?(?:permanent\s+resident|green\s+card\s+holder)\s+or\s+(?:a\s+)?U\.?S\.?\s+citizen|"
    r"United\s+States\s+citizenship\s+(?:is\s+)?required|"
    r"(?:applicants?|candidates?)\s+must\s+be\s+(?:U\.?S\.?|United\s+States)\s+nationals?|"
    r"(?:current\s+)?(?:security|secret|top\s+secret|TS(?:/SCI)?)\s+clearance\s+"
    r"(?:is\s+)?required|"
    r"must\s+(?:hold|possess|have)\s+(?:an?\s+)?(?:current\s+)?"
    r"(?:security|secret|top\s+secret|TS(?:/SCI)?)\s+clearance|"
    r"must\s+obtain\s+(?:an?\s+)?(?:DoD\s+)?(?:secret|top\s+secret|TS(?:/SCI)?)(?:\s+clearance)?|"
    r"only\s+(?:U\.?S\.?|United\s+States)\s+persons?\s+may\s+apply|"
    r"(?:U\.?S\.?|United\s+States)\s+national\s+status\s+(?:is\s+)?required|"
    r"(?:permanent\s+residents?|green\s+card\s+holders?)\s+only|"
    r"no\s+foreign\s+nationals?|"
    r"must\s+qualify\s+as\s+(?:an?\s+)?(?:U\.?S\.?|United\s+States)\s+person\s+under\s+ITAR)\b",
    re.I,
)

NEGATIVE_SPONSORSHIP = [
    re.compile(pattern, re.I)
    for pattern in (
        r"(?:will|does|do|can)\s+not\s+(?:provide|offer|support|sponsor).{0,45}(?:visa|immigration|sponsorship|h-?1b)",
        r"\bcannot\s+(?:provide|offer|support|sponsor).{0,45}(?:visa|immigration|sponsorship|h-?1b|(?:employment|work)\s+authorization)",
        r"(?:unable|not able)\s+to\s+(?:provide|offer|support|sponsor).{0,45}(?:visa|immigration|sponsorship|h-?1b)",
        r"\bno\s+(?:visa|immigration)\s+sponsorship\b",
        r"without\s+(?:the\s+)?(?:current\s+or\s+future\s+)?(?:need\s+for\s+)?(?:visa|employment|immigration)?\s*sponsorship",
        r"must\s+be\s+(?:legally\s+)?authorized\s+to\s+work.{0,100}without.{0,40}sponsorship",
        r"not\s+(?:eligible|available)\s+for.{0,40}(?:visa|immigration|h-?1b)\s+sponsorship",
        r"(?:visa|immigration|h-?1b)\s+sponsorship\s+(?:is|will be)\s+not\s+available",
        r"(?:will|does|do)\s+not\s+sponsor.{0,80}(?:employment|work)\s+authorization",
        r"not\s+eligible\s+for.{0,50}(?:employment[- ]based\s+)?sponsorship",
        r"(?:requiring|need(?:ing)?).{0,35}(?:visa|immigration)\s+sponsorship.{0,55}(?:will\s+not|won't|cannot)\s+be\s+considered",
        r"(?:visa|immigration|h-?1b)\s+sponsorship\s+(?:is|will\s+be)\s+(?:unavailable|not\s+(?:available|provided|offered|supported))",
        r"\bsponsorship\s+(?:is|will\s+be)\s+(?:unavailable|not\s+(?:available|provided|offered|supported))\b",
        r"\bno\s+(?:visa\s+|immigration\s+)?sponsorship\s+(?:is\s+)?available\b",
        r"\bineligible\s+for.{0,45}(?:visa|immigration|employment[- ]based)?\s*sponsorship\b",
        r"\bmay\s+not\s+be\s+able.{0,240}(?:support|provide|offer|sponsor).{0,90}(?:h-?1b|visa|sponsorship)",
        r"\bh-?1b\s+transfers?\s+(?:(?:is|are)\s+)?not\s+(?:supported|accepted|available)\b",
        r"\b(?:we|the\s+company)\s+do(?:es)?\s+not\s+accept.{0,25}\bh-?1b\s+transfers?\b",
        r"\bnot\s+eligible\s+for.{0,35}(?:visa|immigration)\s+support\b",
        r"\bno\s+immigration\s+assistance\s+(?:is\s+)?available\b",
        r"\bmust\s+have\s+unrestricted\s+(?:employment|work)\s+authorization\b",
        r"\bunable\s+to\s+provide.{0,30}(?:employment|work)\s+authorization\s+assistance\b",
        r"\bnot\s+open\s+to.{0,25}(?:visa|immigration|h-?1b)\s+sponsorship\b",
        r"\bnot\s+(?:considering|accepting).{0,45}(?:candidates?|applicants?).{0,35}"
        r"(?:require|need)(?:s|ing)?.{0,20}(?:visa|immigration)?\s*sponsorship\b",
        r"\b(?:candidates?|applicants?).{0,25}requir(?:e|es|ing).{0,20}sponsorship.{0,35}"
        r"(?:not|ineligible).{0,20}(?:eligible\s+)?for\s+(?:hire|employment|consideration)\b",
        r"\bsponsorship\s+for.{0,35}(?:employment|work)\s+authorization\s+"
        r"(?:is|will\s+be)\s+not\s+available\b",
        r"\bunable\s+to\s+sponsor.{0,50}(?:employment|work)\s+authorization\b",
        r"\b(?:visa|immigration)\s+sponsorship\s+cannot\s+be\s+accommodated\b",
        r"\bno\s+(?:work|employment)\s+visa\s+sponsorship.{0,25}(?:provided|available|offered|supported)\b",
        r"\b(?:visa|immigration|employment)\s+sponsorship\s*:?\s*not\s+(?:available|offered|provided|supported)\b",
        r"\bsponsorship\s*:?\s*not\s+(?:available|offered|provided|supported)\b",
        r"\bno\s+(?:visa\s+|immigration\s+|employment\s+)?sponsorship\s+(?:is\s+)?"
        r"(?:provided|offered|supported)\b",
        r"\b(?:we|the\s+company)\s+(?:cannot|do(?:es)?\s+not)\s+accommodate.{0,25}"
        r"(?:visa|immigration)?\s*sponsorship\b",
        r"\b(?:we|the\s+company)\s+(?:are|is)\s+not\s+offering.{0,25}sponsorship\b",
        r"\bwe\s+(?:don['’]t|won['’]t)\s+sponsor.{0,25}(?:visas?|h-?1b|immigration)\b",
        r"\bh-?1b\s+(?:is\s+)?not\s+(?:supported|accepted|available)\b",
        r"\bh-?1b\s+candidates?.{0,20}cannot\s+be\s+considered\b",
        r"\bno\s+h-?1b\s+transfers?\b",
        r"\bno\s+h-?1b\s+sponsorship\b",
        r"\bh-?1b\s+sponsorship\s+(?:is\s+)?unavailable\b",
        r"\bh-?1b\s+transfers?\s+(?:cannot|can['’]?t)\s+be\s+"
        r"(?:supported|accepted|processed|accommodated)\b",
        r"\b(?:we|the\s+company)\s+(?:cannot|can['’]?t|do(?:es)?\s+not|don['’]?t|won['’]?t)\s+"
        r"(?:process|support|accept|transfer)\s+(?:h-?1b(?:s|\s+transfers?)?)\b",
        r"\b(?:candidates?|applicants?)\s+must\s+not(?:\s+now\s+or\s+in\s+the\s+future)?\s+"
        r"require.{0,30}(?:visa|immigration)?\s*sponsorship\b",
        r"\b(?:visa|immigration|h-?1b)?\s*sponsorship\s*:\s*(?:no|none)\b",
        r"\bimmigration\s+support\s+(?:is\s+)?not\s+(?:provided|available|offered|supported)\b",
        r"\bno\s+(?:current\s+or\s+)?future\s+(?:visa\s+|immigration\s+)?sponsorship\s+"
        r"(?:is\s+)?(?:available|provided|offered|supported)\b",
        r"\bno\s+sponsorship\s*(?:[.!;]|$)",
    )
]
H1B_POSITIVE_SPONSORSHIP = [
    re.compile(pattern, re.I)
    for pattern in (
        r"\b(?:we|the company)\s+(?:will\s+)?sponsor.{0,40}h-?1b\b",
        r"\bh-?1b\s+(?:transfer\s+)?sponsorship\s+(?:is\s+)?(?:available|supported)\b",
    )
]
POSITIVE_SPONSORSHIP = [
    re.compile(pattern, re.I)
    for pattern in (
        r"\bvisa\s+sponsorship\s+(?:is\s+)?available\b",
        r"\b(?:we|the company)\s+(?:will\s+)?sponsor.{0,40}(?:work visa|employment visa)",
        r"\bwe\s+do\s+sponsor\s+visas?\b",
    )
]

NON_US = re.compile(
    r"\b(Canada|India|United Kingdom|UK|Ireland|Germany|France|Spain|Poland|Romania|"
    r"Israel|Singapore|Australia|(?<!New )Mexico|Brazil|Japan|China|Taiwan|Netherlands|Sweden|Panama|Panam[aá]|"
    r"Argentina|Colombia|Portugal|Switzerland|Costa Rica|Europe|EMEA|APAC|"
    r"Vancouver|Toronto|Montreal|London|Dublin|Tbilisi|Batumi|Kutaisi|Bengaluru|Bangalore|Hyderabad|Pune|Gurugram|"
    r"Karnataka|Karnātaka|Telangana|Maharashtra|Tamil Nadu|Haryana|Uttar Pradesh|Delhi|Noida|Chennai|Mumbai)\b",
    re.I,
)
US_MARKER = re.compile(
    r"\b(United States|U\.?S\.?|USA|US Remote|Remote[- /]US|Remote.*United States|"
    r"Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|"
    r"Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|"
    r"Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|"
    r"New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|"
    r"Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|"
    r"West Virginia|Wisconsin|Wyoming|District of Columbia)\b",
    re.I,
)
US_STATE_ABBREVIATION = re.compile(
    r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|"
    r"MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|"
    r"WV|WI|WY|DC)\b"
)
US_CITY_NAME_COLLISION = re.compile(
    r"^\s*(?:Dublin|London|New London|Mexico|Sweden|Brazil|Panama City|Vancouver)\s*,\s*"
    r"(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|"
    r"MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|"
    r"WV|WI|WY|DC|Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|"
    r"Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|"
    r"Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|"
    r"Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|"
    r"North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|"
    r"South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|"
    r"West Virginia|Wisconsin|Wyoming|District of Columbia)"
    r"(?:\s*,\s*(?:United States|U\.?S\.?A?))?\s*$",
    re.I,
)

YEAR_WORD_VALUES = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
YEAR_TOKEN = r"(?:\d{1,2}|zero|one|two|three|four|five|six|seven|eight|nine|ten)"
YEAR_RANGE = re.compile(
    rf"(?<!\w)({YEAR_TOKEN})(?:\s*\+)?\s*(?:-|–|—|to)\s*({YEAR_TOKEN})\s*(?:\+\s*)?"
    rf"(?:years?|yrs?\.?)(?:['’])?(?:\s+of)?",
    re.I,
)
YEAR_SINGLE = re.compile(
    rf"(?<!\w)({YEAR_TOKEN})(?:\s*\+|\s*[- ]plus|\s+or\s+more)?\s*[-–—]?\s*"
    rf"(?:years?|yrs?\.?)(?:['’])?(?:\s+of)?",
    re.I,
)

CORE_PROFESSIONAL_EVIDENCE = re.compile(
    r"\b(?:Java|JVM|Spring(?: Boot)?|Python|FastAPI|AWS|Amazon Web Services|Kinesis|DynamoDB|RDS|"
    r"DDoS|Shield|multi[- ]region|distributed systems?|high[- ]throughput|security telemetry|"
    r"threat intelligence|network security|application security|traffic mitigation|rate limit|"
    r"abuse prevention|backend|microservices?|REST(?:ful)? APIs?)\b",
    re.I,
)
OPERATIONS_TITLE = re.compile(
    r"\b(?:systems?|cloud|security|infrastructure|platform|site reliability|reliability|production|"
    r"observability|telemetry) (?:software )?(?:engineer|developer)\b|\b(?:SRE|DevOps|DevSecOps)\b",
    re.I,
)
SOFTWARE_DEVELOPMENT_EVIDENCE = re.compile(
    r"\b(?:software|backend|Java|JVM|Python|Spring|FastAPI|microservices?|REST(?:ful)? APIs?|"
    r"API development|distributed systems?|programming|coding|write code|develop(?:ing|ment)? services?|"
    r"systems development|developer platform|infrastructure[- ]as[- ]code|IaC|CDK|software automation)\b",
    re.I,
)
ALIGNED_DATA_ENGINEER_TITLE = re.compile(
    r"\bdata engineer\b.{0,45}\b(?:streaming|real[- ]time|telemetry|distributed)\b|"
    r"\b(?:streaming|real[- ]time|telemetry|distributed)\b.{0,45}\bdata engineer\b",
    re.I,
)
SECONDARY_PLATFORM_TITLE = re.compile(
    r"^(?=.*\b(?:AI|artificial intelligence|machine learning|ML|GenAI|MLOps|model serving|"
    r"model runtime|LLMs?)\b)(?=.*\b(?:backend|platform|infrastructure|serving|runtime|"
    r"reliability|security)\b)(?=.*\b(?:software|backend|platform|infrastructure|reliability|"
    r"security) (?:software )?(?:engineer|developer)\b).*$",
    re.I,
)
UNSUPPORTED_SPECIALIZATION_EVIDENCE = re.compile(
    r"\A(?:(?=[\s\S]*\b(?:GPU|TPU|Trainium|specialized\s+(?:AI\s+)?accelerators?)\b)"
    r"(?=[\s\S]*\b(?:compilers?|kernels?|CUDA|LLVM|MLIR|XLA|Triton)\b)|"
    r"(?=[\s\S]*\b(?:machine learning|ML)\s+models?\b)"
    r"(?=[\s\S]*\b(?:training|retraining|inference|model serving)\b)"
    r"(?=[\s\S]*\b(?:computer vision|model lifecycle|model deployment|applied scientists?)\b)|"
    r"(?=[\s\S]*\bSAP\b)(?=[\s\S]*\b(?:ABAP|S/4HANA|SAP HANA|BTP|CDS views?)\b)|"
    r"(?=[\s\S]*\b(?:multimodal|VLM|pre[- ]training|post[- ]training|synthetic data)\b)"
    r"(?=[\s\S]*\b(?:training data|LLMs?|foundation models?)\b)|"
    r"(?=[\s\S]*\b(?:KVM|libvirt|QEMU)\b)(?=[\s\S]*\b(?:Ceph|LVM|NFS|iSCSI|FC|NVMeoF|GFS2)\b)|"
    r"(?=[\s\S]*\b(?:AppDynamics|Control-M|InfluxDB)\b)"
    r"(?=[\s\S]*\b(?:Oracle|RHEL|Red Hat Enterprise Linux)\b)|"
    r"[\s\S]*\b(?:looking\s+for|seeking)\s+(?:an?\s+)?full[- ]stack\s+(?:software\s+)?engineer\b|"
    r"[\s\S]*\b(?:develop|build)\w*\s+(?:products?|applications?)\s+primarily\s+using\b"
    r"[\s\S]{0,100}\b(?:Java|Python)\b[\s\S]{0,30}\bback[- ]?end\b"
    r"[\s\S]{0,80}\b(?:React(?:\.js)?|JavaScript|TypeScript)\b[\s\S]{0,40}\bfront[- ]?end\b|"
    r"(?=[\s\S]*\bprivacy[- ]preserving\s+analytics?\b)"
    r"(?=[\s\S]*\bdeploying\s+AI/ML\s+solutions?\b)|"
    r"(?=[\s\S]*\bRequired Skills and Experience\b)"
    r"(?=[\s\S]*\b(?:OAuth\s*2\.0|OpenID Connect|JWTs?|PKCE)\b)"
    r"(?=[\s\S]*\b(?:gRPC|Protocol Buffers)\b)|"
    r"(?=[\s\S]*\b(?:data-driven systems|ML-powered features|A/B experimentation platforms)\b)"
    r"(?=[\s\S]*\bbackend APIs?\s*\(e\.g\.,?\s*gRPC\))"
    r"(?=[\s\S]*\b(?:Flink|Spark)\b)|"
    r"(?=[\s\S]*\bRequired skills\b)(?=[\s\S]*\b(?:MFA|SSO|OAuth\s*2\.0)\b)"
    r"(?=[\s\S]*\bworking knowledge of PHP\b)|"
    r"(?=[\s\S]*\b(?:HLS|HTTP Live Streaming|MPEG-DASH|MP4)\b)"
    r"(?=[\s\S]*\b(?:H\.264|H\.265|HEVC|VP9|AV1)\b)|"
    r"[\s\S]*\b3\+\s+years?\s+of\s+relevant\s+industry\s+experience\s*"
    r"\([^)]*(?:Payments|Fintech)[^)]*\)\s+as\s+(?:a\s+)?backend software engineer\b|"
    r"[\s\S]*\bExperience\s+leading\s+design,\s+implementation,\s+and\s+deployment\s+of\s+"
    r"one\s+or\s+more\s+high\s+scale,\s+cross-functional\s+payment\s+systems\b|"
    r"(?=[\s\S]*\bdeep expertise in systems-level performance analysis, profiling\b)"
    r"(?=[\s\S]*\btrack record of reducing infrastructure costs\b)|"
    r"[\s\S]*\b(?:experience|proficiency)\s+(?:(?:in|with)\s+)?C\+\+\s+(?:is\s+)?required\b|"
    r"[\s\S]*\b\d+\+?\s+years?['’]?\s+experience\s+building\s+backend\s+APIs?\s+for\s+mobile\s+apps?\b|"
    r"[\s\S]*\bexperience\s+(?:in|with)\s+(?:the\s+)?games?\s+industry\b|"
    r"[\s\S]*\b(?:advanced|expert)\s+(?:Python\s+and\s+)?\.NET\s+skills\b)",
    re.I,
)
SECONDARY_TECHNOLOGY_GROUPS: Sequence[Tuple[str, str, str, float]] = (
    (
        "Python/FastAPI",
        r"\b(?:Python|FastAPI)\b",
        r"\b(?:Java|Spring)\b.{0,35}\b(?:or|/)\b.{0,20}\b(?:Python|FastAPI)\b|"
        r"\b(?:Python|FastAPI)\b.{0,35}\b(?:or|/)\b.{0,20}\b(?:Java|Spring)\b",
        1,
    ),
    (
        "Kafka/MSK",
        r"\b(?:Kafka|MSK)\b",
        r"\bKinesis\b.{0,35}\b(?:or|/)\b.{0,20}\b(?:Kafka|MSK)\b|"
        r"\b(?:Kafka|MSK)\b.{0,35}\b(?:or|/)\b.{0,20}\bKinesis\b",
        0,
    ),
    (
        "GraphQL",
        r"\bGraphQL\b",
        r"\b(?:REST(?:ful)?|HTTP)\s*APIs?\b.{0,35}\b(?:or|/)\b.{0,20}\bGraphQL\b|"
        r"\bGraphQL\b.{0,35}\b(?:or|/)\b.{0,20}\b(?:REST(?:ful)?|HTTP)\s*APIs?\b",
        0,
    ),
    (
        "Redis/ElastiCache",
        r"\b(?:Redis|ElastiCache)\b",
        r"\b(?:DynamoDB|RDS)\b.{0,35}\b(?:or|/)\b.{0,20}\b(?:Redis|ElastiCache)\b|"
        r"\b(?:Redis|ElastiCache)\b.{0,35}\b(?:or|/)\b.{0,20}\b(?:DynamoDB|RDS)\b",
        0,
    ),
    ("Docker/ECS", r"\b(?:Docker|ECS)\b", r"(?!x)x", 0),
    (
        "specialized observability stack",
        r"\b(?:Prometheus|Grafana|OpenTelemetry|Jaeger)\b",
        r"\bCloudWatch\b.{0,35}\b(?:or|/)\b.{0,20}\b(?:Prometheus|Grafana|OpenTelemetry|Jaeger)\b|"
        r"\b(?:Prometheus|Grafana|OpenTelemetry|Jaeger)\b.{0,35}\b(?:or|/)\b.{0,20}\bCloudWatch\b",
        0,
    ),
    ("NGINX", r"\bNGINX\b", r"(?!x)x", 0),
    (
        "AI/ML application infrastructure",
        r"\b(?:AI|ML|RAG|LLMs?|MCP|Model Context Protocol|machine learning|artificial intelligence|generative AI|GenAI|MLOps)\b",
        r"(?!x)x",
        0,
    ),
    (
        "frontend/mobile application stack",
        r"\b(?:Angular|React(?:\.js)?|Vue(?:\.js)?|JavaScript|TypeScript|Node\.js|"
        r"iOS|Android|Swift|Kotlin)\b",
        r"\b(?:Java|Spring|Python|FastAPI)\b.{0,45}\b(?:or|/)\b.{0,30}"
        r"\b(?:Angular|React(?:\.js)?|Vue(?:\.js)?|JavaScript|TypeScript|Node\.js|iOS|Android|Swift|Kotlin)\b|"
        r"\b(?:Angular|React(?:\.js)?|Vue(?:\.js)?|JavaScript|TypeScript|Node\.js|iOS|Android|Swift|Kotlin)\b"
        r".{0,45}\b(?:or|/)\b.{0,30}\b(?:Java|Spring|Python|FastAPI)\b",
        0,
    ),
    (
        ".NET/C#",
        r"(?:\bC#(?!\w)|(?<!\w)\.NET\b|\bASP\.NET\b)",
        r"\b(?:Java|Spring|Python|FastAPI)\b.{0,45}\b(?:or|/)\b.{0,30}"
        r"(?:\bC#(?!\w)|(?<!\w)\.NET\b|\bASP\.NET\b)|"
        r"(?:\bC#(?!\w)|(?<!\w)\.NET\b|\bASP\.NET\b).{0,45}\b(?:or|/)\b.{0,30}"
        r"\b(?:Java|Spring|Python|FastAPI)\b",
        0,
    ),
)


SKILL_GROUPS: Sequence[Tuple[str, int, Sequence[str]]] = (
    (
        "backend/API services",
        8,
        (
            r"\bbackend\b",
            r"microservices?",
            r"REST(?:ful)? API",
            r"service[- ]to[- ]service",
            r"server[- ]side",
            r"GraphQL",
            r"JPA",
            r"Hibernate",
        ),
    ),
    (
        "distributed systems/performance",
        10,
        (
            r"distributed systems?",
            r"high[- ]throughput",
            r"large[- ]scale",
            r"high[- ]scale",
            r"fault[- ]tolerant",
            r"backpressure",
            r"low[- ]latency",
            r"high[- ]performance",
            r"performance engineering",
            r"load test",
            r"latency benchmark",
            r"capacity planning",
            r"concurren",
            r"bounded queues?",
        ),
    ),
    (
        "Java/Spring",
        10,
        (r"\bJava\b", r"Spring Boot", r"Spring WebFlux", r"Spring Security", r"\bJVM\b"),
    ),
    ("Python/FastAPI", 5, (r"\bPython\b", r"FastAPI")),
    (
        "AWS/cloud",
        8,
        (r"\bAWS\b", r"Amazon Web Services", r"AWS CDK", r"cloud infrastructure", r"cloud platform", r"cloud[- ]native", r"\bIAM\b"),
    ),
    (
        "streaming/messaging",
        7,
        (r"\bKafka\b", r"\bMSK\b", r"\bKinesis\b", r"event[- ]driven", r"stream processing", r"message queues?", r"pub[- /]?sub", r"\bSQS\b", r"\bSNS\b", r"EventBridge"),
    ),
    (
        "datastores",
        6,
        (r"DynamoDB", r"\bRDS\b", r"PostgreSQL", r"pgvector", r"vector database", r"NoSQL", r"Redis", r"ElastiCache", r"data model", r"key[- ]value"),
    ),
    (
        "security/DDoS",
        10,
        (r"security engineering", r"security telemetry", r"DDoS", r"threat", r"abuse", r"\bbots?\b", r"network security", r"application security", r"threat intelligence", r"rate limit", r"traffic mitigation"),
    ),
    (
        "platform/infrastructure",
        7,
        (r"platform engineering", r"developer platform", r"infrastructure", r"infrastructure[- ]as[- ]code", r"\bIaC\b", r"\bCDK\b", r"\bECS\b", r"Docker", r"containers?", r"\bLinux\b", r"NGINX", r"reverse proxy"),
    ),
    (
        "SRE/operations",
        7,
        (r"site reliability", r"\bSRE\b", r"on[- ]call", r"incident (?:response|management)", r"production incidents?", r"reliability engineering", r"\bSLOs?\b", r"runbooks?", r"circuit breakers?", r"safe degradation", r"operational excellence"),
    ),
    (
        "observability",
        4,
        (r"observability", r"CloudWatch", r"Prometheus", r"Grafana", r"OpenTelemetry", r"Jaeger", r"distributed tracing", r"telemetry"),
    ),
    ("multi-region", 4, (r"multi[- ]region", r"cross[- ]region", r"geo[- ]distributed", r"global infrastructure")),
    ("AI application infrastructure", 3, (r"Spring AI", r"retrieval[- ]augmented", r"\bRAG\b", r"Model Context Protocol", r"\bMCP\b", r"\bLLMs?\b", r"generative AI", r"AI platform", r"agentic")),
)

TITLE_SCORE_RULES: Sequence[Tuple[str, int, str]] = (
    (
        "target engineering role",
        18,
        r"\bsoftware (?:(?:development|dev|developer) )?engineer\b|\bsoftware developer\b|"
        r"\b(?:SDE|SWE)\b|"
        r"\bsystems development engineer\b|\b(?:security|cloud|platform|infrastructure) development engineer\b|"
        r"\b(?:member of technical staff|MTS)\b|"
        r"\bdata engineer\b.{0,45}\b(?:streaming|real[- ]time|telemetry|distributed)\b|"
        r"\b(?:streaming|real[- ]time|telemetry|distributed)\b.{0,45}\bdata engineer\b|"
        r"\b(?:backend|back-end|platform|infrastructure|systems?|security|reliability|production|"
        r"cloud|API|Java|Python|observability|"
        r"telemetry) (?:software )?(?:engineer|developer)\b|\b(?:SRE|DevOps|DevSecOps)\b",
    ),
    (
        "target role family",
        10,
        r"backend|back-end|platform|infrastructure|distributed|systems|security|site reliability|"
        r"\bSRE\b|production engineer|cloud|reliability|observability|telemetry|\bAPI\b",
    ),
    (
        "exact resume domain",
        12,
        r"DDoS|Shield|Kinesis|DynamoDB|telemetry|control plane|data plane|resilien|\bbots?\b|"
        r"abuse|rate limit",
    ),
)


def _preferred_requirement(text: str, start: int, end: int) -> bool:
    prefix = text[max(0, start - 100) : start].lower()
    suffix = text[end : min(len(text), end + 60)].lower()
    local_prefix = re.split(r"[\n.!;]", prefix.rstrip())[-1]
    section_prefix = text[max(0, start - 500) : start]
    section_headings = list(
        re.finditer(
            r"(?im)^\s*(preferred|minimum|required|basic|must[- ]have|nice to have)"
            r"(?:\s+(?:qualifications?|experience|skills?|requirements?))?\s*:?\s*$",
            section_prefix,
        )
    )
    if section_headings and section_headings[-1].group(1).lower() in {
        "preferred",
        "nice to have",
    }:
        return True
    # ATS HTML is commonly flattened to a single line. Treat the nearest
    # inline qualifications heading as authoritative even when its content is
    # long, while bounding the lookup to avoid leaking across the whole post.
    inline_section_prefix = text[max(0, start - 4000) : start]
    inline_headings = list(
        re.finditer(
            r"\b(preferred|minimum|required|basic|must[- ]have)\s+"
            r"(?:qualifications?|experience|skills?|requirements?)\b\s*:|"
            r"\b(nice to have)\b\s*:",
            inline_section_prefix,
            re.I,
        )
    )
    if inline_headings:
        latest_heading = inline_headings[-1]
        intervening = inline_section_prefix[latest_heading.end() :]
        other_section = re.search(
            r"\b(?:responsibilities|what you(?:'|’)?ll do|about (?:the )?(?:role|team|company)|"
            r"benefits|compensation|location|job duties|the opportunity)\b\s*:",
            intervening,
            re.I,
        )
        if not other_section:
            heading_label = next(
                group for group in latest_heading.groups() if group is not None
            ).lower()
            return heading_label in {"preferred", "nice to have"}
    return bool(
        re.search(r"\b(preferred|nice to have|bonus|ideally|a plus)\b[^\n.!;]{0,45}$", local_prefix)
        or re.match(
            r"\s*(?:is\s+|are\s+)?(?:preferred|nice to have|a plus|ideal|bonus)\b",
            suffix,
        )
    )


def _optional_government_restriction(text: str, start: int, end: int) -> bool:
    """Accept optionality only when its grammar is tied to the restriction itself."""
    prefix = re.split(r"[.!;\n]", text[max(0, start - 120) : start])[-1]
    suffix = re.split(r"[.!;\n]", text[end : min(len(text), end + 240)])[0]
    optional_marker = r"(?:preferred|optional|beneficial|nice to have|a plus)"
    if re.search(
        rf"\b{optional_marker}\b(?:\s+qualification)?\s*[:,-]?\s*$",
        prefix,
        re.I,
    ):
        return True
    if re.match(
        rf"\s*,?\s*(?:is|are)?\s*(?:{optional_marker}|not\s+(?:necessary|required))\b",
        suffix,
        re.I,
    ):
        return True
    # Example: "Active UK or US clearance, or eligibility and willingness to
    # obtain one, is beneficial, but not necessary." The optional predicate is
    # attached to the clearance alternative, not merely elsewhere in the sentence.
    return bool(
        re.match(
            rf"\s*,?\s*or\s+(?:eligibility|ability)(?:\s+and\s+willingness)?\s+to\s+"
            rf"(?:obtain|maintain|hold)\s+(?:one|it|the\s+clearance)\s*,?\s*"
            rf"(?:is|are)\s+(?:{optional_marker}|not\s+(?:necessary|required))\b",
            suffix,
            re.I,
        )
    )


def _looks_like_experience_requirement(text: str, start: int, end: int) -> bool:
    phrase = text[start:end].lower()
    prefix = text[max(0, start - 90) : start].lower()
    suffix = text[end : min(len(text), end + 100)].lower()
    local = (
        re.split(r"[\n.!;]", prefix)[-1]
        + phrase
        + re.split(r"[\n.!;]", suffix)[0]
    ).lower()
    if re.match(r"\s*(?:ago|of\s+service|with\s+(?:the\s+)?company)\b", suffix):
        return False
    if re.search(r"\b(?:founded|established|incorporated|vest|vesting|benefit)\b", local):
        return False
    if re.search(
        r"\b(?:we|our\s+team|the\s+team|our\s+company|the\s+company|our\s+product|the\s+product)\s+"
        r"(?:has|have|brings?|offers?|possesses?)\s*$",
        prefix,
        re.I,
    ):
        return False
    if re.search(r"(?:for\s+over|over|more\s+than)\s*$", prefix) and re.match(
        r"\s*[,;]?\s*(?:we|our|the\s+company|the\s+team)\b", suffix
    ):
        return False
    if re.search(r"\b(?:require[sd]?|minimum|at\s+least|must\s+have|you\s+have|qualification)\b[^\n.!;]{0,45}$", prefix):
        return True
    if re.search(r"\b(?:professional\s+)?experience\s*:\s*$", prefix, re.I):
        return True
    if re.match(r"\s*(?:is\s+)?(?:required|minimum)\b", suffix, re.I):
        return True
    if re.search(
        r"\b(?:bachelor|master)'?s?\s+degree\s+(?:and|with)\s*$", prefix, re.I
    ) and re.match(r"\s*[,;]?\s*(?:or\b|$)", suffix, re.I):
        return True
    return bool(
        re.match(
            r"\s*(?:of\s+)?(?:(?:relevant|professional|industry|hands[- ]on|equivalent|"
            r"demonstrated|proven)\s*,?\s*)*"
            r"(?:experience|software|engineering|development|developing|programming|coding|backend|platform|"
            r"infrastructure|security|Java|Python|AWS|Kafka|Kinesis|GraphQL|Redis|Docker|ECS|"
            r"Prometheus|Grafana|OpenTelemetry|NGINX|working\s+with\b|with\b|in\b)",
            suffix,
            re.I,
        )
        or re.match(
            r"\s*(?:of\s+)?(?:(?:relevant|professional|industry|hands[- ]on)\s*,?\s*)*"
            r"(?:[A-Za-z0-9+#./-]+\s+){1,5}(?:development|engineering|programming)\s+experience\b",
            suffix,
            re.I,
        )
    )


def _year_value(value: str) -> int:
    normalized = value.strip().lower()
    return int(normalized) if normalized.isdigit() else YEAR_WORD_VALUES[normalized]


def _strictly_greater_year_floor(text: str, start: int) -> bool:
    prefix = text[max(0, start - 35) : start]
    return bool(re.search(r"\b(?:more\s+than|greater\s+than|over)\s*$", prefix, re.I))


@dataclass(frozen=True)
class ExperienceRequirement:
    low: int
    high: int
    preferred: bool
    start: int
    end: int
    is_range: bool


def _experience_requirements(text: str) -> List[ExperienceRequirement]:
    requirements: List[ExperienceRequirement] = []
    range_spans: List[Tuple[int, int]] = []
    for match in YEAR_RANGE.finditer(text):
        range_spans.append(match.span())
        low, high = _year_value(match.group(1)), _year_value(match.group(2))
        if low <= 15 and high <= 20 and low <= high and _looks_like_experience_requirement(
            text, match.start(), match.end()
        ):
            requirements.append(
                ExperienceRequirement(
                    low,
                    high,
                    _preferred_requirement(text, match.start(), match.end()),
                    match.start(),
                    match.end(),
                    True,
                )
            )
    for match in YEAR_SINGLE.finditer(text):
        if any(match.start() < end and match.end() > start for start, end in range_spans):
            continue
        value = _year_value(match.group(1))
        if _strictly_greater_year_floor(text, match.start()):
            value += 1
        if value <= 20 and _looks_like_experience_requirement(text, match.start(), match.end()):
            requirements.append(
                ExperienceRequirement(
                    value,
                    value,
                    _preferred_requirement(text, match.start(), match.end()),
                    match.start(),
                    match.end(),
                    False,
                )
            )
    return requirements


def _degree_alternative_adjusted(
    text: str,
    requirements: List[ExperienceRequirement],
    highest_degree: str,
) -> List[ExperienceRequirement]:
    if not requirements or "master" not in highest_degree.lower():
        return requirements
    retained = list(requirements)
    for alternative in re.finditer(r"\bor\b", text, re.I):
        left_boundary = max(
            text.rfind(".", 0, alternative.start()),
            text.rfind("!", 0, alternative.start()),
            text.rfind("?", 0, alternative.start()),
            text.rfind("\n", 0, alternative.start()),
        ) + 1
        right_positions = [
            position
            for marker in (".", "!", "?", "\n")
            if (position := text.find(marker, alternative.end())) >= 0
        ]
        right_boundary = min(right_positions) if right_positions else len(text)
        left = text[left_boundary : alternative.start()]
        right = text[alternative.end() : right_boundary]
        left_bachelor = list(re.finditer(r"\bbachelor'?s?\b", left, re.I))
        left_master = list(re.finditer(r"\bmaster'?s?\b", left, re.I))
        right_bachelor = list(re.finditer(r"\bbachelor'?s?\b", right, re.I))
        right_master = list(re.finditer(r"\bmaster'?s?\b", right, re.I))
        if not (
            bool(left_bachelor) != bool(left_master)
            and bool(right_bachelor) != bool(right_master)
            and bool(left_bachelor) != bool(right_bachelor)
        ):
            continue
        left_requirements = [
            requirement
            for requirement in retained
            if left_boundary <= requirement.start < alternative.start()
        ]
        right_requirements = [
            requirement
            for requirement in retained
            if alternative.end() <= requirement.start < right_boundary
        ]
        if not left_requirements or not right_requirements:
            continue

        def absolute_degree_position(matches: Sequence[re.Match], offset: int) -> int:
            match = matches[-1] if offset == left_boundary else matches[0]
            return offset + ((match.start() + match.end()) // 2)

        if left_bachelor:
            bachelor_requirements, bachelor_degree = left_requirements, absolute_degree_position(
                left_bachelor, left_boundary
            )
            master_requirements, master_degree = right_requirements, absolute_degree_position(
                right_master, alternative.end()
            )
        else:
            master_requirements, master_degree = left_requirements, absolute_degree_position(
                left_master, left_boundary
            )
            bachelor_requirements, bachelor_degree = right_requirements, absolute_degree_position(
                right_bachelor, alternative.end()
            )
        bachelor_requirement = min(
            bachelor_requirements,
            key=lambda requirement: abs(((requirement.start + requirement.end) // 2) - bachelor_degree),
        )
        master_requirement = min(
            master_requirements,
            key=lambda requirement: abs(((requirement.start + requirement.end) // 2) - master_degree),
        )
        bachelor_distance = abs(
            ((bachelor_requirement.start + bachelor_requirement.end) // 2) - bachelor_degree
        )
        master_distance = abs(
            ((master_requirement.start + master_requirement.end) // 2) - master_degree
        )
        if bachelor_distance <= 160 and master_distance <= 160:
            retained.remove(bachelor_requirement)

    # A completed Bachelor's/Master's also satisfies explicit degree-versus-extra-
    # experience alternatives such as "Master's + 5 years, or 8 years without a degree."
    for alternative in re.finditer(r"\bor\b", text, re.I):
        left_boundary = max(
            text.rfind(".", 0, alternative.start()),
            text.rfind("!", 0, alternative.start()),
            text.rfind("?", 0, alternative.start()),
            text.rfind("\n", 0, alternative.start()),
        ) + 1
        right_positions = [
            position
            for marker in (".", "!", "?", "\n")
            if (position := text.find(marker, alternative.end())) >= 0
        ]
        right_boundary = min(right_positions) if right_positions else len(text)
        left = text[left_boundary : alternative.start()]
        right = text[alternative.end() : right_boundary]
        degree_pattern = re.compile(r"\b(?:bachelor|master)'?s?\b", re.I)
        no_degree_pattern = re.compile(
            r"\b(?:without\s+(?:a\s+)?degree|in\s+lieu\s+of\s+(?:a\s+)?degree|equivalent\s+experience)\b",
            re.I,
        )
        left_degree, right_degree = degree_pattern.search(left), degree_pattern.search(right)
        left_no_degree, right_no_degree = no_degree_pattern.search(left), no_degree_pattern.search(right)
        if not ((left_degree and right_no_degree) or (right_degree and left_no_degree)):
            continue
        left_requirements = [
            requirement
            for requirement in retained
            if left_boundary <= requirement.start < alternative.start()
        ]
        right_requirements = [
            requirement
            for requirement in retained
            if alternative.end() <= requirement.start < right_boundary
        ]
        if not left_requirements or not right_requirements:
            continue
        if left_degree and right_no_degree:
            degree_requirement = min(
                left_requirements,
                key=lambda requirement: abs(
                    ((requirement.start + requirement.end) // 2)
                    - (left_boundary + ((left_degree.start() + left_degree.end()) // 2))
                ),
            )
            extra_requirement = min(
                right_requirements,
                key=lambda requirement: abs(
                    ((requirement.start + requirement.end) // 2)
                    - (alternative.end() + ((right_no_degree.start() + right_no_degree.end()) // 2))
                ),
            )
        else:
            degree_requirement = min(
                right_requirements,
                key=lambda requirement: abs(
                    ((requirement.start + requirement.end) // 2)
                    - (alternative.end() + ((right_degree.start() + right_degree.end()) // 2))
                ),
            )
            extra_requirement = min(
                left_requirements,
                key=lambda requirement: abs(
                    ((requirement.start + requirement.end) // 2)
                    - (left_boundary + ((left_no_degree.start() + left_no_degree.end()) // 2))
                ),
            )
        if (
            abs(extra_requirement.low - degree_requirement.low) >= 1
            and extra_requirement.low >= degree_requirement.low
        ):
            retained.remove(extra_requirement)
    return retained


def extract_years(
    text: str,
    highest_degree: str = "masters",
) -> Tuple[Optional[float], Optional[float]]:
    candidates = _degree_alternative_adjusted(
        text,
        _experience_requirements(text),
        highest_degree,
    )
    required = [value for value in candidates if not value.preferred]
    pool = required or candidates
    if not pool:
        return None, None
    # Multiple skill-specific minima usually appear beside the overall minimum; the largest
    # required value is the conservative estimate.
    return float(max(x.low for x in pool)), float(max(x.high for x in pool))


def _sentence_window(text: str, start: int, end: int) -> Tuple[str, int]:
    left = max(text.rfind(".", 0, start), text.rfind(";", 0, start), text.rfind("\n", 0, start)) + 1
    right_candidates = [position for marker in (".", ";", "\n") if (position := text.find(marker, end)) >= 0]
    right = min(right_candidates) if right_candidates else len(text)
    # Some ATS text flattens a required language list as
    # "3+ years ... programming languages; Go, Python, Rust".  The semicolon is
    # part of that requirement, not a new qualification.
    if (
        right < len(text)
        and text[right] == ";"
        and re.search(r"\bprogramming\s+languages?\s*$", text[end:right], re.I)
    ):
        trailing_candidates = [
            position
            for marker in (".", ";", "\n")
            if (position := text.find(marker, right + 1)) >= 0
        ]
        right = min(trailing_candidates) if trailing_candidates else len(text)
    return text[left:right], left


def _secondary_technology_overages(
    text: str,
    requirements: Sequence[ExperienceRequirement],
    groups: Sequence[Tuple[str, str, str, float]],
) -> List[Tuple[str, int]]:
    def bound_to_requirement(
        sentence: str,
        requirement: ExperienceRequirement,
        offset: int,
        technology_match: re.Match,
    ) -> bool:
        requirement_start = requirement.start - offset
        requirement_end = requirement.end - offset
        if technology_match.start() >= requirement_end:
            between = sentence[requirement_end : technology_match.start()]
            return bool(
                re.fullmatch(
                    r"\s*(?:"
                    r"(?:(?:relevant|professional|hands[- ]on|industry)\s+)?"
                    r"(?:(?:software|backend|application)\s+)?"
                    r"(?:(?:development|engineering|programming)\s+)?"
                    r"(?:experience\s*)?"
                    r"(?:\(\s*(?:or\s+)?(?:relevant\s+)?(?:internship(?:\s*/\s*academic)?|academic)\s+"
                    r"projects?\s*\)\s*)?"
                    r"(?:(?:with|in|using|of)\s*)?"
                    r"|"
                    r"(?:of\s+)?software\s+development\s+experience\s+in\s+"
                    r"(?:one|1)\s+or\s+more\s+general[- ]purpose\s+programming\s+languages?\s*;\s*"
                    r"(?:[A-Za-z][A-Za-z0-9+#./-]*(?:\s+[A-Za-z][A-Za-z0-9+#./-]*){0,2}\s*,\s*)*"
                    r"|"
                    r"(?:(?:relevant|professional|hands[- ]on|industry)\s+)?"
                    r"(?:(?:(?:software|backend|application)\s+)?(?:development\s+)?experience\s+)?"
                    r"(?:developing|building|designing|operating|implementing|maintaining|working\s+with)\s+"
                    r"(?:[A-Za-z0-9+#./-]+\s+){0,7}(?:(?:with|in|using|of)\s*)?"
                    r")[:,-]?\s*",
                    between,
                    re.I,
                )
            )
        if technology_match.end() <= requirement_start:
            between = sentence[technology_match.end() : requirement_start]
            return bool(
                re.fullmatch(
                    r"\s*(?:hands[- ]on\s+)?(?:experience|development|engineering|programming)?"
                    r"\s*(?:of|for|:|,|-)?\s*",
                    between,
                    re.I,
                )
            )
        return False

    core_alternative = re.compile(
        r"\b(?:Java|Spring|Kinesis|DynamoDB|RDS|CloudWatch|AWS|Amazon Web Services)\b|"
        r"\b(?:REST(?:ful)?|HTTP)\s*APIs?\b",
        re.I,
    )
    list_separator = re.compile(r"\s*(?:(?:,|/)|\b(?:and|or)\b)\s*", re.I)
    overages: List[Tuple[str, int]] = []
    for requirement in requirements:
        if requirement.preferred:
            continue
        sentence, offset = _sentence_window(text, requirement.start, requirement.end)
        group_tokens: List[Tuple[int, int, str, str, re.Match]] = []
        for label, technology_regex, alternative_regex, max_years in groups:
            if requirement.low > max_years:
                for match in re.finditer(technology_regex, sentence, re.I):
                    prefix = sentence[max(0, match.start() - 55) : match.start()]
                    suffix = sentence[match.end() : min(len(sentence), match.end() + 55)]
                    technology_is_optional = bool(
                        re.search(
                            r"\b(?:preferred|optional|nice to have|bonus|a plus)\b[^,;]{0,30}$",
                            prefix,
                            re.I,
                        )
                        or re.match(
                            r"\s*(?:is\s+|are\s+)?(?:preferred|optional|nice to have|bonus|a plus)\b",
                            suffix,
                            re.I,
                        )
                    )
                    if not technology_is_optional:
                        group_tokens.append(
                            (match.start(), match.end(), label, alternative_regex, match)
                        )
        if not group_tokens:
            continue
        core_tokens = [
            (match.start(), match.end(), "", "", match)
            for match in core_alternative.finditer(sentence)
        ]
        tokens = sorted(group_tokens + core_tokens, key=lambda token: (token[0], token[1]))
        requirement_start = requirement.start - offset
        requirement_end = requirement.end - offset
        bound_indexes = [
            index
            for index, token in enumerate(tokens)
            if bound_to_requirement(sentence, requirement, offset, token[4])
        ]
        if not bound_indexes:
            continue
        # Use the nearest directly bound token, then expand only across actual list
        # separators. This distinguishes "Java and Python" from an unrelated later
        # phrase such as "AWS experience and Python familiarity".
        anchor = min(
            bound_indexes,
            key=lambda index: min(
                abs(tokens[index][0] - requirement_end),
                abs(requirement_start - tokens[index][1]),
            ),
        )
        first = last = anchor
        while first > 0 and list_separator.fullmatch(
            sentence[tokens[first - 1][1] : tokens[first][0]]
        ):
            first -= 1
        while last + 1 < len(tokens) and list_separator.fullmatch(
            sentence[tokens[last][1] : tokens[last + 1][0]]
        ):
            last += 1
        connected = tokens[first : last + 1]
        list_tail_end = min(len(sentence), connected[-1][1] + 55)
        connected_text = sentence[connected[0][0] : list_tail_end]
        has_core_option = any(not token[2] for token in connected)
        choice_prefix = sentence[
            max(requirement_end, connected[0][0] - 140) : connected[0][0]
        ]
        explicit_or_list = bool(
            re.search(r"\bor\b", connected_text, re.I)
            or re.search(
                r"\b(?:one|1)\s+or\s+more\s+general[- ]purpose\s+programming\s+languages?\s*;"
                r"[^;.!\n]{0,120}$",
                choice_prefix,
                re.I,
            )
        )
        for _start, _end, label, alternative_regex, _match in connected:
            if not label:
                continue
            if explicit_or_list and has_core_option:
                continue
            if alternative_regex and re.search(alternative_regex, connected_text, re.I):
                continue
            overages.append((label, requirement.low))
    return list(dict.fromkeys(overages))


def sponsorship_signal(text: str) -> str:
    if any(pattern.search(text) for pattern in NEGATIVE_SPONSORSHIP):
        return "explicit_no_sponsorship"
    if any(pattern.search(text) for pattern in H1B_POSITIVE_SPONSORSHIP):
        return "explicit_h1b_sponsorship_available"
    if any(pattern.search(text) for pattern in POSITIVE_SPONSORSHIP):
        return "explicit_sponsorship_available"
    return "not_stated"


def _explicit_raw_countries(raw: Any) -> List[str]:
    """Extract countries only from job/applicant location structures."""
    values: List[str] = []
    country_keys = {
        "addresscountry",
        "country",
        "countrycode",
        "normalizedcountrycode",
    }

    location_root_keys = {
        "address",
        "additionallocations",
        "applicantlocationrequirements",
        "joblocation",
        "location",
        "locations",
        "secondarylocations",
        "worklocation",
    }

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized_key = re.sub(r"[^a-z]", "", str(key).lower())
                if normalized_key in country_keys:
                    if isinstance(child, dict):
                        for name_key in ("name", "value", "code"):
                            if name_key in child and isinstance(child[name_key], str):
                                values.append(child[name_key].strip())
                    elif isinstance(child, str):
                        values.append(child.strip())
                else:
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    if isinstance(raw, dict):
        for key, child in raw.items():
            normalized_key = re.sub(r"[^a-z]", "", str(key).lower())
            if normalized_key in country_keys:
                if isinstance(child, str):
                    values.append(child.strip())
                elif isinstance(child, dict):
                    collect(child)
            elif normalized_key in location_root_keys:
                collect(child)
    return [value for value in values if value]


def location_status(job: Job, company: Company) -> str:
    structured_countries = {
        re.sub(r"[^A-Z]", "", value.upper()) for value in _explicit_raw_countries(job.raw)
    }
    us_country_values = {"US", "USA", "UNITEDSTATES", "UNITEDSTATESOFAMERICA"}
    if structured_countries:
        if structured_countries & us_country_values:
            return "us"
        return "non_us"

    location_text = job.location.strip()
    for location_segment in re.split(r"\s*[|;]\s*", location_text):
        normalized_location_segment = re.sub(
            r"\s*(?:\((?:hybrid|remote|on[- ]?site)\)|(?:[-,/]\s*)?"
            r"(?:hybrid|remote|on[- ]?site))\s*$",
            "",
            location_segment,
            flags=re.I,
        )
        if US_CITY_NAME_COLLISION.fullmatch(normalized_location_segment):
            return "us"
    text = f"{location_text} {job.workplace_type}".strip()
    segments = [segment for segment in re.split(r"\s*[|;]\s*", text) if segment]
    has_non_us = False
    for segment in segments:
        non_us = bool(NON_US.search(segment))
        explicit_us_collision_address = bool(US_CITY_NAME_COLLISION.fullmatch(segment))
        ambiguous_remote_code = bool(
            re.fullmatch(r"\s*remote\s*[-,/]?\s*[A-Z]{2}\s*", segment, re.I)
        )
        us = bool(
            US_MARKER.search(segment)
            or (not ambiguous_remote_code and US_STATE_ABBREVIATION.search(segment))
        )
        has_non_us = has_non_us or non_us
        if us and (not non_us or explicit_us_collision_address):
            return "us"
        if us and non_us and re.search(r"\b(United States|USA|U\.S\.|US)\b", segment, re.I):
            return "us"
    if has_non_us:
        return "non_us"
    ambiguous_remote_code = bool(
        re.fullmatch(r"\s*remote\s*[-,/]?\s*[A-Z]{2}\s*", location_text, re.I)
    )
    if US_MARKER.search(text) or (
        not ambiguous_remote_code and US_STATE_ABBREVIATION.search(text)
    ):
        return "us"
    if (
        re.fullmatch(r"remote", location_text, re.I)
        and company.connector.get("default_country", "").upper() in {"US", "USA"}
    ):
        return "us_inferred_remote"
    return "unknown"


class Ranker:
    def __init__(self, profile: Dict[str, Any]) -> None:
        self.profile = profile
        filters = profile.get("filters", {})
        matching = profile.get("matching", {})
        self.min_score = float(filters.get("min_match_score", 55))
        self.min_sponsorship = float(filters.get("min_sponsorship_score", 0.55))
        self.p1_score = float(filters.get("p1_match_score", 70))
        self.p1_min_sponsorship = float(filters.get("p1_min_sponsorship_score", 0.60))
        self.p0_score = float(filters.get("p0_match_score", 82))
        self.p0_min_sponsorship = float(filters.get("p0_min_sponsorship_score", 0.75))
        self.max_required_years = float(filters.get("max_required_years", 4))
        self.senior_max_required_years = float(filters.get("senior_max_required_years", 4))
        self.exclude_explicit_no = bool(filters.get("exclude_explicit_no_sponsorship", True))
        self.require_us_location = bool(filters.get("require_us_location", True))
        self.max_title_score = float(matching.get("max_title_score", 30))
        self.max_skill_score = float(matching.get("max_skill_score", 42))
        candidate = profile.get("candidate", {})
        self.candidate_years = float(candidate.get("years_of_relevant_us_experience", 3.5))
        self.highest_degree = str(candidate.get("highest_degree", "masters"))
        self.ideal_required_years = min(
            self.max_required_years,
            max(3.0, float(math.ceil(self.candidate_years))),
        )
        if not 0 <= self.min_sponsorship <= self.p1_min_sponsorship <= self.p0_min_sponsorship <= 1:
            raise ValueError("sponsorship thresholds must satisfy min <= P1 <= P0 within 0..1")
        if not 0 <= self.min_score <= self.p1_score <= self.p0_score <= 100:
            raise ValueError("match thresholds must satisfy min <= P1 <= P0 within 0..100")
        if self.max_title_score < 0 or self.max_skill_score < 0:
            raise ValueError("title and skill score caps must be non-negative")
        if self.candidate_years <= 0 or self.max_required_years <= 0:
            raise ValueError("candidate and required years must be positive")

        def configured_pattern(key: str, default: re.Pattern) -> re.Pattern:
            value = matching.get(key)
            return re.compile(str(value), re.I) if value else default

        self.internship = configured_pattern("internship_title_regex", INTERNSHIP)
        self.new_grad = configured_pattern("junior_title_regex", NEW_GRAD)
        self.early_career_metadata = configured_pattern(
            "early_career_metadata_regex", EARLY_CAREER_METADATA
        )
        self.irrelevant_department = configured_pattern(
            "irrelevant_department_regex", IRRELEVANT_DEPARTMENT
        )
        self.secondary_platform_department = configured_pattern(
            "secondary_platform_department_regex", SECONDARY_PLATFORM_DEPARTMENT
        )
        self.management = configured_pattern("management_title_regex", MANAGEMENT)
        self.too_senior = configured_pattern("too_senior_title_regex", TOO_SENIOR)
        self.junior_level = configured_pattern("level_i_title_regex", JUNIOR_LEVEL)
        self.too_high_level = configured_pattern("level_iv_title_regex", TOO_HIGH_LEVEL)
        self.senior = configured_pattern("selective_senior_title_regex", SENIOR)
        self.target_title = configured_pattern("target_title_regex", TARGET_TITLE)
        self.irrelevant_title = configured_pattern("irrelevant_title_regex", IRRELEVANT_TITLE)
        self.core_professional_evidence = configured_pattern(
            "core_professional_evidence_regex", CORE_PROFESSIONAL_EVIDENCE
        )
        self.operations_title = configured_pattern("operations_title_regex", OPERATIONS_TITLE)
        self.software_development_evidence = configured_pattern(
            "software_development_evidence_regex", SOFTWARE_DEVELOPMENT_EVIDENCE
        )
        self.aligned_data_engineer_title = configured_pattern(
            "aligned_data_engineer_title_regex", ALIGNED_DATA_ENGINEER_TITLE
        )
        self.secondary_platform_title = configured_pattern(
            "secondary_platform_title_regex", SECONDARY_PLATFORM_TITLE
        )
        self.unsupported_specialization_evidence = configured_pattern(
            "unsupported_specialization_evidence_regex",
            UNSUPPORTED_SPECIALIZATION_EVIDENCE,
        )
        additional_specialization_patterns = matching.get(
            "additional_unsupported_specialization_evidence_regexes"
        ) or []
        if not isinstance(additional_specialization_patterns, list):
            raise ValueError(
                "additional_unsupported_specialization_evidence_regexes must be a list"
            )
        if additional_specialization_patterns:
            additional = "|".join(
                f"(?:{str(pattern)})" for pattern in additional_specialization_patterns
            )
            self.unsupported_specialization_evidence = re.compile(
                rf"(?:{self.unsupported_specialization_evidence.pattern}|\A(?:{additional}))",
                re.I,
            )
        self.government_restriction = configured_pattern(
            "work_authorization_restriction_regex", GOVERNMENT_RESTRICTION
        )
        self.p0_title_specialty = configured_pattern(
            "p0_specialty_title_regex",
            re.compile(
                r"distributed|DDoS|Shield|Kinesis|Kafka|DynamoDB|telemetry|observability|resilien|"
                r"streaming|multi[- ]region|data plane|control plane|abuse|\bbots?\b|rate limit|"
                r"security platform|backend platform|cloud platform",
                re.I,
            ),
        )
        self.secondary_title_specialty = configured_pattern(
            "secondary_specialty_title_regex",
            re.compile(r"\b(AI|machine learning|ML|deep learning|generative AI|LLM)\b", re.I),
        )
        configured_skills = matching.get("skill_groups") or []
        if configured_skills:
            self.skill_groups: Sequence[Tuple[str, int, Sequence[str]]] = tuple(
                (
                    str(group["label"]),
                    int(group["weight"]),
                    tuple(str(pattern) for pattern in group["patterns"]),
                )
                for group in configured_skills
            )
        else:
            self.skill_groups = SKILL_GROUPS
        configured_title_scores = matching.get("title_score_rules") or []
        if configured_title_scores:
            self.title_score_rules: Sequence[Tuple[str, int, str]] = tuple(
                (str(rule["label"]), int(rule["weight"]), str(rule["regex"]))
                for rule in configured_title_scores
            )
        else:
            self.title_score_rules = TITLE_SCORE_RULES
        secondary_default_max_years = float(
            matching.get("secondary_technology_max_required_years", 2)
        )
        configured_secondary_technologies = matching.get("secondary_technology_experience_groups") or []
        if configured_secondary_technologies:
            self.secondary_technology_groups: Sequence[Tuple[str, str, str, float]] = tuple(
                (
                    str(group["label"]),
                    str(group["regex"]),
                    str(group.get("core_alternative_regex", r"(?!x)x")),
                    float(group.get("max_required_years", secondary_default_max_years)),
                )
                for group in configured_secondary_technologies
            )
        else:
            self.secondary_technology_groups = SECONDARY_TECHNOLOGY_GROUPS
        for _label, _weight, patterns in self.skill_groups:
            for pattern in patterns:
                re.compile(pattern, re.I)
        for _label, _weight, pattern in self.title_score_rules:
            re.compile(pattern, re.I)
        for _label, pattern, alternative_pattern, max_years in self.secondary_technology_groups:
            re.compile(pattern, re.I)
            re.compile(alternative_pattern, re.I)
            if max_years < 0:
                raise ValueError("secondary technology experience ceilings must be non-negative")

    def evaluate(self, job: Job, company: Company, now: Optional[datetime] = None) -> Decision:
        now = now or datetime.now(timezone.utc)
        title = job.title.strip()
        text = f"{title}\n{job.department}\n{job.description}"
        role_metadata = f"{job.employment_type}\n{job.department}"
        rejection: List[str] = []
        why: List[str] = []
        title_without_selective_mts = re.sub(
            r"\b(?:member of technical staff|MTS)\b", "", title, flags=re.I
        )
        title_without_bank_ladder = re.sub(
            r"\b(?:senior|principal) associate\b", "", title, flags=re.I
        )
        title_without_selective_mts = re.sub(
            r"\bprincipal associate\b", "", title_without_selective_mts, flags=re.I
        )
        aligned_data_engineer = bool(self.aligned_data_engineer_title.search(title))
        secondary_platform_title = bool(self.secondary_platform_title.search(title))
        secondary_platform_department = bool(
            self.secondary_platform_department.search(job.department)
        )

        if not title or not job.source_url:
            rejection.append("missing title or official source URL")
        if self.internship.search(title) or self.internship.search(role_metadata):
            rejection.append("internship/co-op")
        if (
            self.new_grad.search(title_without_bank_ladder)
            or self.early_career_metadata.search(role_metadata)
        ):
            rejection.append("new-grad/entry-level")
        if self.management.search(title):
            rejection.append("people-management role")
        if self.irrelevant_department.search(job.department) and not secondary_platform_department:
            rejection.append("department is outside backend/platform/security/SRE scope")
        if self.too_senior.search(title_without_selective_mts):
            rejection.append("staff/principal/architect/lead level")
        if self.junior_level.search(title):
            rejection.append("level-I/junior role")
        if self.too_high_level.search(title):
            rejection.append("level-IV/V role exceeds target seniority")
        if self.irrelevant_title.search(title) and not (
            aligned_data_engineer or secondary_platform_title
        ):
            rejection.append("title is outside backend/platform/security/SRE scope")
        mandatory_government_restriction = any(
            not _optional_government_restriction(text, match.start(), match.end())
            for match in self.government_restriction.finditer(text)
        )
        if re.search(r"\bfederal\b", title, re.I) or mandatory_government_restriction:
            rejection.append("citizenship/clearance-restricted or federal role")
        if not self.target_title.search(title) and not aligned_data_engineer:
            rejection.append("title lacks a target engineering discipline")
        if not self.core_professional_evidence.search(text):
            rejection.append("posting lacks a professionally evidenced core technology or domain")
        if self.operations_title.search(title) and not self.software_development_evidence.search(text):
            rejection.append("operations-oriented title lacks software-development evidence")
        if aligned_data_engineer and not self.software_development_evidence.search(text):
            rejection.append("streaming data-engineer title lacks software-development evidence")
        if self.unsupported_specialization_evidence.search(job.description):
            rejection.append("posting requires a specialist domain not established by the resume")

        loc_status = location_status(job, company)
        if self.require_us_location:
            if loc_status == "non_us":
                rejection.append("non-US location")
            elif loc_status == "unknown":
                rejection.append("US eligibility could not be verified from location")
            elif loc_status.startswith("us_inferred"):
                why.append("US location inferred from the employer feed configuration")
            else:
                why.append("US/US-remote location")
        elif loc_status in {"us", "us_inferred_remote", "us_inferred_missing"}:
            why.append("US/US-remote location")

        experience_requirements = _degree_alternative_adjusted(
            job.description,
            _experience_requirements(job.description),
            self.highest_degree,
        )
        min_years, max_years = extract_years(job.description, self.highest_degree)
        required_year_ranges = [
            requirement
            for requirement in experience_requirements
            if requirement.is_range and not requirement.preferred
        ]
        junior_ranges = [
            requirement
            for requirement in required_year_ranges
            if requirement.high <= 2
        ]
        early_career_band = any(
            requirement.low <= 1 and requirement.high <= 3
            for requirement in required_year_ranges
        )
        if junior_ranges:
            rejection.append("experience range is explicitly junior (at most two years)")
        elif early_career_band:
            rejection.append("experience range is an early-career band (1-3 years)")
        elif (
            min_years is not None
            and max_years is not None
            and min_years <= 1
            and max_years <= 1
        ):
            rejection.append("experience floor is explicitly junior (one year or less)")
        secondary_technology_overages = _secondary_technology_overages(
            job.description,
            experience_requirements,
            self.secondary_technology_groups,
        )
        for technology, years in secondary_technology_overages:
            rejection.append(
                f"requires {years:g}+ years of {technology}, beyond verified resume depth"
            )
        if min_years is not None:
            if min_years > self.max_required_years:
                rejection.append(f"requires about {min_years:g}+ years")
            else:
                why.append(f"experience floor appears to be {min_years:g} years")
        if self.senior.search(title):
            if min_years is None:
                rejection.append(
                    f"Senior title with no verifiable 3-{self.senior_max_required_years:g} year experience floor"
                )
            elif min_years > self.senior_max_required_years:
                rejection.append("Senior role exceeds configured experience ceiling")
            else:
                why.append("Senior title retained because stated experience is within range")

        role_signal = sponsorship_signal(text)
        sponsor_score = company.sponsorship.score
        if role_signal == "explicit_no_sponsorship":
            sponsor_score = 0.0
            if self.exclude_explicit_no:
                rejection.append("posting explicitly rules out sponsorship")
        elif role_signal == "explicit_h1b_sponsorship_available":
            sponsor_score = max(0.92, sponsor_score)
            why.append("posting explicitly indicates H-1B sponsorship availability")
        elif role_signal == "explicit_sponsorship_available":
            sponsor_score = max(0.58, sponsor_score)
            why.append("posting explicitly indicates generic visa sponsorship availability")
        elif sponsor_score >= self.min_sponsorship:
            why.append(f"{company.sponsorship.confidence} employer-level sponsorship evidence")
        if sponsor_score < self.min_sponsorship:
            rejection.append("employer/role sponsorship confidence below threshold")

        title_score = 0.0
        for _label, weight, pattern in self.title_score_rules:
            if re.search(pattern, title, re.I):
                title_score += weight
        score = min(self.max_title_score, title_score)

        matched_groups = []
        skill_score = 0.0
        for label, weight, patterns in self.skill_groups:
            if any(re.search(pattern, text, re.I) for pattern in patterns):
                skill_score += weight
                matched_groups.append(label)
        score += min(self.max_skill_score, skill_score)
        if matched_groups:
            why.append("matches " + ", ".join(matched_groups[:6]))
        if len(matched_groups) >= 4:
            score += 6
        elif len(matched_groups) == 3:
            score += 4
        elif len(matched_groups) == 2:
            score += 2
        if min_years is not None and min_years <= 2:
            score += 3
        elif min_years is not None and min_years <= self.ideal_required_years:
            score += 12
        elif min_years is not None and min_years <= self.max_required_years:
            score += 8
        if early_career_band:
            score -= 6
        score = max(0.0, min(100.0, round(score, 1)))

        if score < self.min_score:
            rejection.append(f"match score {score:g} is below {self.min_score:g}")
        accepted = not rejection
        age_days = (now - job.posted_at).total_seconds() / 86400 if job.posted_at else None
        title_specialty = bool(self.p0_title_specialty.search(title))
        secondary_specialty = bool(
            self.secondary_title_specialty.search(title)
            or aligned_data_engineer
            or secondary_platform_title
            or secondary_platform_department
        )
        stretch_experience = (
            min_years is not None and min_years > self.ideal_required_years
        )
        incomplete_experience_fit = min_years is None or min_years <= 2
        if accepted and stretch_experience:
            why.append("experience floor is above the ideal target; priority capped at P2")
        if accepted and min_years is None:
            why.append("experience floor is not verifiable; priority capped at P2")
        elif accepted and min_years <= 2:
            why.append("experience floor is below the target band; priority capped at P2")
        if (
            accepted
            and title_specialty
            and not secondary_specialty
            and not early_career_band
            and not stretch_experience
            and not incomplete_experience_fit
            and score >= self.p0_score
            and sponsor_score >= self.p0_min_sponsorship
            and (age_days is None or age_days <= 2.25)
        ):
            priority = "P0"
        elif (
            accepted
            and not early_career_band
            and not stretch_experience
            and not incomplete_experience_fit
            and score >= self.p1_score
            and sponsor_score >= self.p1_min_sponsorship
        ):
            priority = "P1"
        elif accepted:
            priority = "P2"
        else:
            priority = "REJECT"
        return Decision(
            accepted=accepted,
            score=score,
            priority=priority,
            why=why,
            rejection_reasons=list(dict.fromkeys(rejection)),
            min_years=min_years,
            max_years=max_years,
            sponsorship_score=round(sponsor_score, 2),
            sponsorship_signal=role_signal,
        )
