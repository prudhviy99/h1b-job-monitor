from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Type

from ..http import HttpClient
from ..models import Company, FetchResult


LIKELY_TITLE = re.compile(
    r"\b(software|backend|back-end|platform|infrastructure|site reliability|sre|"
    r"security|cloud|distributed|systems?|production|devops|reliability|java|service)\b",
    re.I,
)
OBVIOUS_NON_TARGET = re.compile(
    r"\b(intern(ship)?|new grad(uate)?|campus|apprentice|engineering manager|director|"
    r"vice president|principal|distinguished|staff software|front[ -]?end|mobile|ios|android|"
    r"data scientist|product manager|sales|marketing|recruiter)\b",
    re.I,
)


def likely_detail_candidate(title: str) -> bool:
    return bool(LIKELY_TITLE.search(title or "")) and not bool(OBVIOUS_NON_TARGET.search(title or ""))


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
