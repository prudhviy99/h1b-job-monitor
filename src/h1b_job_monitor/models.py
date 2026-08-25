from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SponsorshipEvidence:
    confidence: str
    score: float
    summary: str
    sources: List[str] = field(default_factory=list)
    evidence_year: Optional[str] = None
    certified_lcas: Optional[int] = None
    certified_positions: Optional[int] = None
    software_related_positions: Optional[int] = None
    change_employer_positions: Optional[int] = None
    caveat: str = (
        "Employer-level filing history is not a promise that this role or team will transfer an H-1B."
    )


@dataclass
class Company:
    id: str
    name: str
    domain: str
    careers_url: str
    enabled: bool
    connector: Dict[str, Any]
    sponsorship: SponsorshipEvidence
    fit_tags: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class Job:
    company_id: str
    company: str
    source: str
    source_job_id: str
    title: str
    location: str
    description: str
    source_url: str
    apply_url: str = ""
    posted_at: Optional[datetime] = None
    posting_date_kind: str = "unknown"
    posting_date_confidence: str = "unknown"
    employment_type: str = ""
    department: str = ""
    workplace_type: str = ""
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    discovered_at: Optional[datetime] = None
    sponsorship_confidence: str = ""
    sponsorship_score: float = 0.0
    sponsorship_evidence: str = ""
    role_sponsorship_signal: str = "not_stated"
    match_score: float = 0.0
    apply_priority: str = "REJECT"
    why_matches: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)
    extracted_min_years: Optional[float] = None
    extracted_max_years: Optional[float] = None
    event_type: str = ""
    job_key: str = ""

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value.pop("raw", None)
        for key in ("posted_at", "discovered_at"):
            if value[key] is not None:
                value[key] = value[key].astimezone(timezone.utc).isoformat()
        value["why_matches"] = "; ".join(self.why_matches)
        value["rejection_reasons"] = "; ".join(self.rejection_reasons)
        return value


@dataclass
class FetchResult:
    company_id: str
    source: str
    jobs: List[Job] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=utc_now)
    requests: int = 0
    error: str = ""
    warning: str = ""
    skipped: bool = False
    cursor_complete: bool = True


@dataclass
class Decision:
    accepted: bool
    score: float
    priority: str
    why: List[str]
    rejection_reasons: List[str]
    min_years: Optional[float]
    max_years: Optional[float]
    sponsorship_score: float
    sponsorship_signal: str
