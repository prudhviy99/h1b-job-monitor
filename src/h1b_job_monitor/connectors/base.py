from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Type

from ..http import HttpClient
from ..models import Company, FetchResult


LIKELY_TITLE = re.compile(
    r"\b(software|backend|back-end|platform|infrastructure|site reliability|sre|"
    r"security|cloud|distributed|streaming|systems?|production|devops|devsecops|reliability|"
    r"java|python|api|service|observability|telemetry|sde|swe|mts|technical staff)\b",
    re.I,
)
OBVIOUS_NON_TARGET = re.compile(
    r"\b(intern(ship)?|new grad(uate)?|campus|apprentice|engineering (?:manager|mgr\.?|supervisor|leader)|"
    r"manager|mgr\.?|staff|lead|(?:group|technical) leader|director|"
    r"vice president|principal|distinguished|LMTS|PMTS|DMTS|AMTS|staff software|front[ -]?end|mobile|ios|android|"
    r"full[ -]?stack|SDET|software (?:development )?engineer (?:in|for) test|"
    r"(?:software )?quality engineer|robotics|machine learning engineer|AI engineer|data engineer|data scientist|"
    r"AI devops|DRTM|secure launch|solutions? engineer|consultant|"
    r"(?:platform|cloud|infrastructure|security|systems?) specialist|"
    r"(?:test|testing|qa|quality) (?:platform|infrastructure|systems?)|build (?:&|and) test|"
    r"product manager|sales|marketing|recruiter)\b",
    re.I,
)
ALIGNED_DATA_ENGINEER = re.compile(
    r"\bdata engineer\b.{0,45}\b(?:streaming|real[- ]time|telemetry|distributed)\b|"
    r"\b(?:streaming|real[- ]time|telemetry|distributed)\b.{0,45}\bdata engineer\b",
    re.I,
)


def likely_detail_candidate(title: str) -> bool:
    value = title or ""
    aligned_data_engineer = bool(ALIGNED_DATA_ENGINEER.search(value))
    exclusion_value = re.sub(
        r"\b(?:principal associate|(?:senior )?member of technical staff|MTS)\b",
        "",
        value,
        flags=re.I,
    )
    return bool(LIKELY_TITLE.search(value)) and (
        aligned_data_engineer or not bool(OBVIOUS_NON_TARGET.search(exclusion_value))
    )


class Connector(ABC):
    type_name = "base"

    @abstractmethod
    def fetch(self, company: Company, client: HttpClient, since: datetime, mode: str = "initial") -> FetchResult:
        raise NotImplementedError


REGISTRY: Dict[str, Type[Connector]] = {}


def register(cls: Type[Connector]) -> Type[Connector]:
    REGISTRY[cls.type_name] = cls
    return cls


def make_connector(name: str) -> Connector:
    if name not in REGISTRY:
        raise ValueError(f"Unknown connector type: {name}")
    return REGISTRY[name]()
