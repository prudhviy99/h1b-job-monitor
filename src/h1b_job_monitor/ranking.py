from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .models import Company, Decision, Job


INTERNSHIP = re.compile(r"\b(intern(ship)?|co-?op|apprentice)\b", re.I)
NEW_GRAD = re.compile(
    r"\b(new grad(uate)?|university grad|campus|early career|entry[ -]level|junior|jr\.?|associate)\b",
    re.I,
)
MANAGEMENT = re.compile(r"\b(manager|director|head of|vice president|vp|people leader|team leader)\b", re.I)
TOO_SENIOR = re.compile(r"\b(staff|principal|distinguished|fellow|chief|architect|lead)\b", re.I)
JUNIOR_LEVEL = re.compile(
    r"\b(software (development )?engineer|sde|swe|site reliability engineer|security engineer)"
    r"\s*[,/\-]?\s*(?:level\s*)?(i|1)\b",
    re.I,
)
TOO_HIGH_LEVEL = re.compile(
    r"\b(software (development )?engineer|sde|swe|site reliability engineer|security engineer|systems engineer)"
    r"\s*[,/\-]?\s*(?:level\s*)?(iv|4)\b",
    re.I,
)
SENIOR = re.compile(r"\b(senior|sr\.?|software engineer iii|sde iii)\b", re.I)
TARGET_TITLE = re.compile(
    r"\b(software|backend|back-end|platform|infrastructure|site reliability|sre|"
    r"production engineer|security engineer|cloud engineer|distributed systems?|systems engineer|devops)\b",
    re.I,
)
IRRELEVANT_TITLE = re.compile(
    r"\b(front[ -]?end|ui engineer|ux|mobile|ios|android|embedded|firmware|hardware|"
    r"machine learning|ML engineer|AI engineer|data science|data scientist|data analyst|business analyst|"
    r"qa|quality assurance|test engineer|testing|validation|technical escalations?|"
    r"product manager|program manager|project manager|sales engineer|solutions architect|"
    r"customer support|technical support|designer|research scientist)\b",
    re.I,
)
GOVERNMENT_RESTRICTION = re.compile(
    r"\b(federal role|must be (?:a )?U\.?S\.? citizen|U\.?S\.? citizenship (?:is )?required|"
    r"active (?:security )?clearance|requires? (?:a )?(?:security )?clearance|"
    r"eligible for (?:a )?(?:U\.?S\.? )?security clearance|"
    r"(?:U\.?S\.?\s+persons?\s+(?:is\s+)?required|must\s+be\s+(?:a\s+)?U\.?S\.?\s+persons?)|"
    r"(?:U\.?S\.?\s+citizen|green\s+card\s+holder).{0,30}\bonly|"
    r"(?:must|required\s+to)\s+(?:possess|maintain|obtain)\s+(?:an?\s+)?(?:secret|top\s+secret|TS(?:/SCI)?|security)\s+clearance|"
    r"requires?\s+(?:ITAR|export[- ]control)\s+eligibility|"
    r"export[- ]control\s+laws?.{0,140}(?:may|must|need).{0,100}legal\s+status\s+requirements?|"
    r"(?:ITAR|export[- ]controls?).{0,70}(?:must|require).{0,35}U\.?S\.?\s+persons?|"
    r"(?:top\s+secret|TS/SCI)(?:\s+clearance)?|"
    r"requires?.{0,100}(?:candidate.{0,35})?be\s+(?:a\s+)?U\.?S\.?\s+citizen)\b",
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
    )
]
POSITIVE_SPONSORSHIP = [
    re.compile(pattern, re.I)
    for pattern in (
        r"\bvisa\s+sponsorship\s+(?:is\s+)?available\b",
        r"\b(?:we|the company)\s+(?:will\s+)?sponsor.{0,40}(?:h-?1b|work visa|employment visa)",
        r"\bh-?1b\s+(?:transfer\s+)?sponsorship\s+(?:is\s+)?(?:available|supported)\b",
        r"\bwe\s+do\s+sponsor\s+visas?\b",
    )
]

NON_US = re.compile(
    r"\b(Canada|India|United Kingdom|UK|Ireland|Germany|France|Spain|Poland|Romania|"
    r"Israel|Singapore|Australia|Mexico|Brazil|Japan|China|Taiwan|Netherlands|Sweden|Panama|Panam[aá]|"
    r"Vancouver|Toronto|Montreal|London|Dublin|Bengaluru|Bangalore|Hyderabad|Pune|Gurugram|"
    r"Karnataka|Karnātaka|Telangana|Maharashtra|Tamil Nadu|Haryana|Uttar Pradesh|Delhi|Noida|Chennai|Mumbai)\b",
    re.I,
)
US_MARKER = re.compile(
    r"\b(United States|U\.S\.?|USA|US Remote|Remote[- /]US|Remote.*United States|"
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

YEAR_RANGE = re.compile(
    r"(?<!\d)(\d{1,2})(?:\s*\+)?\s*(?:-|–|—|to)\s*(\d{1,2})\s*(?:\+\s*)?years?(?:\s+of)?",
    re.I,
)
YEAR_SINGLE = re.compile(r"(?<!\d)(\d{1,2})\s*\+?\s*years?(?:\s+of)?", re.I)


SKILL_GROUPS: Sequence[Tuple[str, int, Sequence[str]]] = (
    ("backend services", 12, (r"\bbackend\b", r"microservices?", r"REST API", r"service[- ]to[- ]service")),
    ("distributed systems", 14, (r"distributed systems?", r"high[- ]throughput", r"large[- ]scale", r"scalab")),
    ("Java/Spring", 12, (r"\bJava\b", r"Spring Boot", r"Spring WebFlux", r"\bJVM\b")),
    ("AWS/cloud", 11, (r"\bAWS\b", r"Amazon Web Services", r"cloud infrastructure", r"cloud platform")),
    ("streaming/messaging", 9, (r"\bKafka\b", r"\bKinesis\b", r"event[- ]driven", r"stream processing", r"\bSQS\b")),
    ("datastores", 7, (r"DynamoDB", r"\bRDS\b", r"PostgreSQL", r"NoSQL", r"Redis", r"data model")),
    ("security/DDoS", 12, (r"security", r"DDoS", r"threat", r"abuse", r"bot", r"WAF", r"network security")),
    ("platform/infrastructure", 10, (r"platform engineering", r"infrastructure", r"Kubernetes", r"Terraform", r"CDK", r"ECS")),
    ("SRE/operations", 9, (r"site reliability", r"\bSRE\b", r"on[- ]call", r"incident", r"reliability", r"SLO")),
    ("observability", 5, (r"observability", r"CloudWatch", r"Prometheus", r"Grafana", r"OpenTelemetry")),
    ("multi-region", 5, (r"multi[- ]region", r"regional", r"global infrastructure", r"disaster recovery")),
)

TITLE_SCORE_RULES: Sequence[Tuple[str, int, str]] = (
    ("software engineering", 18, r"\bsoftware (development )?engineer\b|\bSDE\b"),
    ("backend", 12, r"backend|back-end"),
    ("platform/infrastructure/systems", 12, r"platform|infrastructure|distributed|systems"),
    ("security/SRE/production", 14, r"security|site reliability|\bSRE\b|production engineer"),
)


def _preferred_requirement(text: str, start: int, end: int) -> bool:
    prefix = text[max(0, start - 100) : start].lower()
    suffix = text[end : min(len(text), end + 60)].lower()
    local_prefix = re.split(r"[\n.!;]", prefix)[-1]
    return bool(
        re.search(r"\b(preferred|nice to have|bonus|ideally|a plus)\b[^\n.!;]{0,45}$", local_prefix)
        or re.match(
            r"\s*(?:is\s+|are\s+)?(?:preferred|nice to have|a plus|ideal|bonus)\b",
            suffix,
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
    if re.search(r"(?:for\s+over|over|more\s+than)\s*$", prefix) and re.match(
        r"\s*[,;]?\s*(?:we|our|the\s+company|the\s+team)\b", suffix
    ):
        return False
    if "+" in phrase:
        return True
    if re.search(r"\b(?:require[sd]?|minimum|at\s+least|must\s+have|you\s+have|qualification)\b[^\n.!;]{0,45}$", prefix):
        return True
    return bool(
        re.match(
            r"\s*(?:of\s+)?(?:relevant\s+|professional\s+|industry\s+|hands[- ]on\s+)?"
            r"(?:experience|software|engineering|development|developing|programming|coding|backend|platform|"
            r"infrastructure|security|Java|AWS|with\b|in\b)",
            suffix,
            re.I,
        )
    )


def extract_years(text: str) -> Tuple[Optional[float], Optional[float]]:
    candidates: List[Tuple[int, int, bool]] = []
    range_spans: List[Tuple[int, int]] = []
    for match in YEAR_RANGE.finditer(text):
        range_spans.append(match.span())
        low, high = int(match.group(1)), int(match.group(2))
        if low <= 15 and high <= 20 and low <= high and _looks_like_experience_requirement(
            text, match.start(), match.end()
        ):
            preferred = _preferred_requirement(text, match.start(), match.end())
            candidates.append((low, high, preferred))
    for match in YEAR_SINGLE.finditer(text):
        if any(match.start() < end and match.end() > start for start, end in range_spans):
            continue
        value = int(match.group(1))
        if value <= 20 and _looks_like_experience_requirement(text, match.start(), match.end()):
            preferred = _preferred_requirement(text, match.start(), match.end())
            candidates.append((value, value, preferred))
    required = [value for value in candidates if not value[2]]
    pool = required or candidates
    if not pool:
        return None, None
    # Multiple skill-specific minima usually appear beside the overall minimum; the largest
    # required value is the conservative estimate.
    return float(max(x[0] for x in pool)), float(max(x[1] for x in pool))


def sponsorship_signal(text: str) -> str:
    if any(pattern.search(text) for pattern in NEGATIVE_SPONSORSHIP):
        return "explicit_no_sponsorship"
    if any(pattern.search(text) for pattern in POSITIVE_SPONSORSHIP):
        return "explicit_sponsorship_available"
    return "not_stated"


def _explicit_raw_countries(raw: Any) -> List[str]:
    """Extract only structured location-country values, not incidental prose."""
    values: List[str] = []
    country_keys = {
        "addresscountry",
        "country",
        "countrycode",
        "normalizedcountrycode",
    }

    def visit(value: Any, parent_key: str = "") -> None:
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
                    visit(child, normalized_key)
        elif isinstance(value, list):
            for child in value:
                visit(child, parent_key)

    visit(raw)
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

    text = f"{job.location} {job.workplace_type}".strip()
    segments = [segment for segment in re.split(r"\s*[|;]\s*", text) if segment]
    has_non_us = False
    for segment in segments:
        non_us = bool(NON_US.search(segment))
        us = bool(US_MARKER.search(segment) or US_STATE_ABBREVIATION.search(segment))
        has_non_us = has_non_us or non_us
        if us and not non_us:
            return "us"
        if us and non_us and re.search(r"\b(United States|USA|U\.S\.|US)\b", segment, re.I):
            return "us"
    if has_non_us:
        return "non_us"
    if US_MARKER.search(text) or US_STATE_ABBREVIATION.search(text):
        return "us"
    if re.search(r"\bremote\b", text, re.I) and company.connector.get("default_country", "").upper() in {"US", "USA"}:
        return "us_inferred_remote"
    if not text and company.connector.get("default_country", "").upper() in {"US", "USA"}:
        return "us_inferred_missing"
    return "unknown"


class Ranker:
    def __init__(self, profile: Dict[str, Any]) -> None:
        self.profile = profile
        filters = profile.get("filters", {})
        matching = profile.get("matching", {})
        self.min_score = float(filters.get("min_match_score", 62))
        self.min_sponsorship = float(filters.get("min_sponsorship_score", 0.55))
        self.max_required_years = float(filters.get("max_required_years", 5))
        self.senior_max_required_years = float(filters.get("senior_max_required_years", 5))
        self.exclude_explicit_no = bool(filters.get("exclude_explicit_no_sponsorship", True))
        self.require_us_location = bool(filters.get("require_us_location", True))

        def configured_pattern(key: str, default: re.Pattern) -> re.Pattern:
            value = matching.get(key)
            return re.compile(str(value), re.I) if value else default

        self.internship = configured_pattern("internship_title_regex", INTERNSHIP)
        self.new_grad = configured_pattern("junior_title_regex", NEW_GRAD)
        self.management = configured_pattern("management_title_regex", MANAGEMENT)
        self.too_senior = configured_pattern("too_senior_title_regex", TOO_SENIOR)
        self.junior_level = configured_pattern("level_i_title_regex", JUNIOR_LEVEL)
        self.too_high_level = configured_pattern("level_iv_title_regex", TOO_HIGH_LEVEL)
        self.senior = configured_pattern("selective_senior_title_regex", SENIOR)
        self.target_title = configured_pattern("target_title_regex", TARGET_TITLE)
        self.irrelevant_title = configured_pattern("irrelevant_title_regex", IRRELEVANT_TITLE)
        self.government_restriction = configured_pattern(
            "work_authorization_restriction_regex", GOVERNMENT_RESTRICTION
        )
        self.p0_title_specialty = configured_pattern(
            "p0_specialty_title_regex",
            re.compile(
                r"backend|platform|infrastructure|distributed|security|site reliability|\bSRE\b|"
                r"cloud|AWS|Kinesis|Kafka|DynamoDB|database|storage|resilien|network",
                re.I,
            ),
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

    def evaluate(self, job: Job, company: Company, now: Optional[datetime] = None) -> Decision:
        now = now or datetime.now(timezone.utc)
        title = job.title.strip()
        text = f"{title}\n{job.department}\n{job.description}"
        rejection: List[str] = []
        why: List[str] = []

        if not title or not job.source_url:
            rejection.append("missing title or official source URL")
        if self.internship.search(title):
            rejection.append("internship/co-op")
        if self.new_grad.search(title):
            rejection.append("new-grad/entry-level")
        if self.management.search(title):
            rejection.append("people-management role")
        if self.too_senior.search(title):
            rejection.append("staff/principal/architect/lead level")
        if self.junior_level.search(title):
            rejection.append("level-I/junior role")
        if self.too_high_level.search(title):
            rejection.append("level-IV role exceeds target seniority")
        if self.irrelevant_title.search(title):
            rejection.append("title is outside backend/platform/security/SRE scope")
        if re.search(r"\bfederal\b", title, re.I) or self.government_restriction.search(text):
            rejection.append("citizenship/clearance-restricted or federal role")
        if not self.target_title.search(title):
            rejection.append("title lacks a target engineering discipline")

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

        min_years, max_years = extract_years(job.description)
        explicit_mid_title = bool(re.search(r"\b(?:ii|2|mid[ -]level)\b", title, re.I))
        junior_ranges = [
            match
            for match in YEAR_RANGE.finditer(job.description)
            if int(match.group(2)) <= 2
            and not _preferred_requirement(job.description, match.start(), match.end())
        ]
        if junior_ranges and not explicit_mid_title:
            rejection.append("experience range is explicitly junior (at most two years)")
        elif (
            min_years is not None
            and max_years is not None
            and min_years <= 1
            and max_years <= 1
            and not explicit_mid_title
        ):
            rejection.append("experience floor is explicitly junior (one year or less)")
        if min_years is not None:
            if min_years > self.max_required_years:
                rejection.append(f"requires about {min_years:g}+ years")
            else:
                why.append(f"experience floor appears to be {min_years:g} years")
        if self.senior.search(title):
            if min_years is None:
                rejection.append("Senior title with no verifiable 3-5 year experience floor")
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
        elif role_signal == "explicit_sponsorship_available":
            sponsor_score = max(0.92, sponsor_score)
            why.append("posting explicitly indicates sponsorship availability")
        elif sponsor_score >= self.min_sponsorship:
            why.append(f"{company.sponsorship.confidence} employer-level sponsorship evidence")
        if sponsor_score < self.min_sponsorship:
            rejection.append("employer/role sponsorship confidence below threshold")

        score = 0.0
        for _label, weight, pattern in self.title_score_rules:
            if re.search(pattern, title, re.I):
                score += weight

        matched_groups = []
        for label, weight, patterns in self.skill_groups:
            if any(re.search(pattern, text, re.I) for pattern in patterns):
                score += weight
                matched_groups.append(label)
        if matched_groups:
            why.append("matches " + ", ".join(matched_groups[:6]))
        if len(matched_groups) >= 4:
            score += 5
        if min_years is None:
            score -= 4
        elif min_years <= 4:
            score += 7
        elif min_years <= 5:
            score += 3

        score += min(12.0, sponsor_score * 12.0)
        fit_overlap = set(tag.lower() for tag in company.fit_tags) & {
            "backend",
            "distributed-systems",
            "platform",
            "infrastructure",
            "security",
            "sre",
            "cloud",
            "java",
        }
        score += min(4, len(fit_overlap))
        score = max(0.0, min(100.0, round(score, 1)))

        if score < self.min_score:
            rejection.append(f"match score {score:g} is below {self.min_score:g}")
        accepted = not rejection
        age_days = (now - job.posted_at).total_seconds() / 86400 if job.posted_at else None
        title_specialty = bool(self.p0_title_specialty.search(title))
        if accepted and title_specialty and score >= 86 and sponsor_score >= 0.75 and (age_days is None or age_days <= 2.25):
            priority = "P0"
        elif accepted and score >= 74 and sponsor_score >= 0.60:
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
