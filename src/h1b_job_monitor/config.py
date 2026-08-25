from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .models import Company, SponsorshipEvidence


def load_json(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path}")
    return value


def load_companies(path: Path) -> List[Company]:
    payload = load_json(path)
    results: List[Company] = []
    seen = set()
    for raw in payload.get("companies", []):
        company_id = str(raw["id"])
        if company_id in seen:
            raise ValueError(f"Duplicate company id: {company_id}")
        seen.add(company_id)
        sponsorship_raw = raw.get("sponsorship") or {}
        sponsorship = SponsorshipEvidence(
            confidence=str(sponsorship_raw.get("confidence", "historical")),
            score=float(sponsorship_raw.get("score", 0.3)),
            summary=str(sponsorship_raw.get("summary", "No recent evidence recorded.")),
            sources=list(sponsorship_raw.get("sources") or []),
            evidence_year=sponsorship_raw.get("evidence_year"),
            certified_lcas=sponsorship_raw.get("certified_lcas"),
            certified_positions=sponsorship_raw.get("certified_positions"),
            software_related_positions=sponsorship_raw.get("software_related_positions"),
            change_employer_positions=sponsorship_raw.get("change_employer_positions"),
            caveat=str(sponsorship_raw.get("caveat") or SponsorshipEvidence.__dataclass_fields__["caveat"].default),
        )
        connector = dict(raw.get("connector") or {})
        if raw.get("enabled", False) and not connector.get("type"):
            raise ValueError(f"Enabled company {company_id} has no connector type")
        results.append(
            Company(
                id=company_id,
                name=str(raw["name"]),
                domain=str(raw.get("domain", "")),
                careers_url=str(raw.get("careers_url", "")),
                enabled=bool(raw.get("enabled", False)),
                connector=connector,
                sponsorship=sponsorship,
                fit_tags=list(raw.get("fit_tags") or []),
                notes=str(raw.get("notes", "")),
            )
        )
    return results

