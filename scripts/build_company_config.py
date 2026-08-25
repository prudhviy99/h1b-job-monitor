#!/usr/bin/env python3
"""Merge independently researched employer batches into monitor config and an audit CSV."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit


CONFIDENCE_SCORE = {
    "high": 0.82,
    "medium-high": 0.72,
    "medium_high": 0.72,
    "medium": 0.62,
    "low": 0.45,
    "historical": 0.30,
}

TARGET_SLUG_REGEX = (
    r"software|backend|back-end|platform|infrastructure|security|site-reliability|"
    r"reliability|cloud|systems|devops|java|distributed|production-engineer"
)
SENIORITY_SLUG_EXCLUDE_REGEX = (
    r"(?:^|[-/])(?:intern(?:ship)?|new-grad|graduate|student|manager|director|staff|"
    r"principal|distinguished|fellow|chief|architect|lead)(?:[-/]|$)"
)
HPE_SLUG_EXCLUDE_REGEX = (
    rf"(?:{SENIORITY_SLUG_EXCLUDE_REGEX})|"
    r"(?:^|[-/])(?:pre-sales|presales|sales|account-executive|officer|strategist|consultant|"
    r"consulting|advisor|leader|test|testing|quality|qa|embedded|firmware|hardware|mechanical|"
    r"electrical|ml|mlops|genai|data-science|data-engineer|support|federal|clearance|early-career)"
    r"(?:[-/]|$)"
)
TARGET_REFINED_SLUG_REGEX = (
    r"software|backend|back-end|site-reliability|devops|distributed|java|cybersecurity|"
    r"application-security|cloud-security|(?:platform|infrastructure|cloud|systems?|security)-"
    r"(?:software-)?(?:engineer|developer)|(?:engineer|developer)-"
    r"(?:platform|infrastructure|cloud|systems?|security)"
)

SAFE_SITEMAPS: Dict[str, Dict[str, Any]] = {
    "Microsoft": {
        "sitemap_url": "https://apply.careers.microsoft.com/careers/sitemap_index.xml",
        "job_url_regex": r"^https://apply\.careers\.microsoft\.com/careers/job/\d+-[^?#]+\?domain=microsoft\.com(?:&.*)?$",
        "max_detail_requests": 240,
        "terms_url": "",
        "access_review": "Robots explicitly allows career pages and the official sitemap; candidate, login, apply, and undocumented APIs are excluded.",
    },
    "Netflix": {
        "sitemap_url": "https://explore.jobs.netflix.net/careers/sitemap_index.xml?domain=netflix.com&microsite=netflix.com",
        "job_url_regex": r"^https://explore\.jobs\.netflix\.net/careers/job/\d+-[^?#]+\?domain=netflix\.com&microsite=netflix\.com(?:&.*)?$",
        "max_detail_requests": 160,
        "terms_url": "",
        "access_review": "Robots explicitly allows career pages and declares the official sitemap; application and undocumented API paths are excluded.",
    },
    "Expedia Group": {
        "sitemap_url": "https://careers.expediagroup.com/jobs-sitemap.xml",
        "job_url_regex": r"^https?://careers\.expediagroup\.com/job/[^/]+/[^/]+/[A-Za-z0-9-]+/?$",
        "max_detail_requests": 80,
        "crawl_delay_seconds": 10,
        "terms_url": "",
        "access_review": "Robots advertises the job sitemap and permits job pages; the declared ten-second crawl delay is enforced.",
    },
    "Stripe": {
        "sitemap_url": "https://stripe.com/sitemap/sitemap.xml",
        "job_url_regex": r"^https://stripe\.com/careers/listing/[^/]+/\d+/?$",
        "max_detail_requests": 160,
        "max_sitemaps": 20,
        "terms_url": "",
        "access_review": "Robots permits career pages and declares the site sitemap; only public listing pages are considered.",
    },
    "PayPal": {
        "sitemap_url": "https://paypal.eightfold.ai/careers/sitemap_index.xml?domain=paypal.com",
        "job_url_regex": r"^https://paypal\.eightfold\.ai/careers/job/\d+-[^?#]+\?domain=paypal\.com(?:&.*)?$",
        "max_detail_requests": 100,
        "terms_url": "",
        "access_review": "Robots explicitly allows career pages and declares the official sitemap; application and undocumented API paths are excluded.",
    },
    "Morgan Stanley": {
        "sitemap_url": "https://morganstanley.eightfold.ai/careers/sitemap_index.xml",
        "job_url_regex": r"^https://morganstanley\.eightfold\.ai/careers/job/\d+-[^?#]+\?domain=morganstanley\.com(?:&.*)?$",
        "max_detail_requests": 180,
        "terms_url": "",
        "access_review": "Robots explicitly allows career pages; only sitemap and public job pages are used.",
    },
    "Micron Technology": {
        "sitemap_url": "https://careers.micron.com/careers/sitemap_index.xml?domain=micron.com",
        "job_url_regex": r"^https://careers\.micron\.com/careers/job/\d+-[^?#]+\?domain=micron\.com(?:&.*)?$",
        "max_detail_requests": 160,
        "terms_url": "",
        "access_review": "Robots explicitly allows career pages and declares the official sitemap; only title-prefiltered public pages are used.",
    },
    "Waymo": {
        "sitemap_url": "https://careers.withwaymo.com/sitemap.xml",
        "job_url_regex": r"^https://careers\.withwaymo\.com/jobs/[^?#]+$",
        "max_detail_requests": 120,
        "crawl_delay_seconds": 5,
        "terms_url": "",
        "access_review": "Robots permits job pages and the sitemap, disallows APIs, and its five-second crawl delay is enforced.",
    },
    "Starbucks": {
        "sitemap_url": "https://apply.starbucks.com/careers/sitemap_index.xml?domain=starbucks.com",
        "job_url_regex": r"^https://apply\.starbucks\.com/careers/job/\d+-[^?#]+\?domain=starbucks\.com(?:&.*)?$",
        "max_detail_requests": 100,
        "terms_url": "",
        "access_review": "Robots explicitly allows career pages and declares the official sitemap; the large catalog is title-prefiltered before detail reads.",
    },
    "Target": {
        "sitemap_url": "https://corporate.target.com/sitemapjob.xml",
        "job_url_regex": r"^https://corporate\.target\.com/jobs/[A-Za-z0-9-]+/[A-Za-z0-9-]+/[^?#]+$",
        "max_detail_requests": 140,
        "url_include_regex": TARGET_REFINED_SLUG_REGEX,
        "terms_url": "",
        "access_review": "Robots advertises the job sitemap and permits job pages; the catalog is title-prefiltered before detail reads.",
    },
    "Nike": {
        "sitemap_url": "https://careers.nike.com/sitemap.xml",
        "job_url_regex": r"^https://careers\.nike\.com/[^/]+/job/[A-Za-z0-9-]+$",
        "max_detail_requests": 140,
        "max_sitemaps": 20,
        "terms_url": "",
        "access_review": "Robots declares the sitemap and permits public job pages; only title-prefiltered listing pages are fetched.",
    },
    "Capital One": {
        "sitemap_url": "https://www.capitalonecareers.com/jobs_sitemap.xml",
        "job_url_regex": r"^https://www\.capitalonecareers\.com/job/[^/]+/[^/]+/1732/\d+$",
        "max_detail_requests": 600,
        "terms_url": "https://www.capitalone.com/digital/terms-conditions/",
        "access_review": "Robots advertises the job sitemap and disallows search, not job pages; reviewed terms had no crawler ban.",
    },
    "Charles Schwab": {
        "sitemap_url": "https://www.schwabjobs.com/sitemap-jobs.xml",
        "job_url_regex": r"^https://www\.schwabjobs\.com/job/[^/]+/[^/]+/\d+/\d+$",
        "max_detail_requests": 180,
        "terms_url": "",
        "access_review": "Robots advertises the job sitemap and permits job pages; no career-site automated-access restriction found.",
    },
    "Synopsys": {
        "sitemap_url": "https://careers.synopsys.com/sitemap.xml",
        "job_url_regex": r"^https://careers\.synopsys\.com/job/[^/]+/[^/]+/44408/\d+$",
        "max_detail_requests": 120,
        "terms_url": "",
        "access_review": "Robots disallows search but permits the sitemap and job pages; no crawler prohibition found in reviewed career legal pages.",
    },
    "Arm": {
        "sitemap_url": "https://careers.arm.com/sitemap.xml",
        "job_url_regex": r"^https://careers\.arm\.com/job/[^/]+/[^/]+/33099/\d+$",
        "max_detail_requests": 180,
        "terms_url": "https://www.arm.com/company/policies/terms-and-conditions",
        "access_review": "Robots permits the sitemap and job pages; reviewed terms had no robot, scraping, crawling, or data-mining prohibition.",
    },
    "Hewlett Packard Enterprise": {
        "sitemap_url": "https://careers.hpe.com/us/en/sitemap_index.xml",
        "job_url_regex": r"^https://careers\.hpe\.com/us/en/job/\d+/[^/?#]+$",
        "max_detail_requests": 180,
        "url_exclude_regex": HPE_SLUG_EXCLUDE_REGEX,
        "crawl_delay_seconds": 2,
        "terms_url": "https://www.hpe.com/us/en/legal/acceptable-use-policy.html",
        "access_review": "Robots permits and advertises career sitemaps; reviewed acceptable-use policy is respected with low-volume, title-prefiltered reads.",
    },
}


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


def split_values(value: str) -> List[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def integer_from(pattern: str, value: str) -> Optional[int]:
    match = re.search(pattern, value, re.I)
    return int(match.group(1)) if match else None


def workday_parts(identifier: str) -> Optional[Tuple[str, str, str]]:
    if identifier.startswith("http"):
        parsed = urlsplit(identifier)
        host = parsed.netloc
        pieces = [item for item in parsed.path.split("/") if item]
        if host.endswith("myworkdayjobs.com") and pieces:
            tenant = host.split(".", 1)[0]
            return host, tenant, pieces[-1]
        return None
    pieces = identifier.split(":")
    if len(pieces) == 3:
        tenant, cluster, site = pieces
        return f"{tenant}.{cluster}.myworkdayjobs.com", tenant, site
    return None


def connector_for(row: Dict[str, str]) -> Tuple[bool, Dict[str, Any], str]:
    ats = row.get("ats_type", "").strip().lower()
    identifier = (
        row.get("ats_identifier_or_base_url")
        or row.get("ats_identifier/base_url")
        or ""
    ).strip()
    name = row["canonical_name"]
    common = {"default_country": "US"}
    if name == "Amazon":
        return True, {
            "type": "amazon",
            "endpoint": identifier or "https://www.amazon.jobs/en/search.json",
            "access_policy": "strict",
            "keywords": [
                "software engineer",
                "software development engineer",
                "security engineer",
                "systems engineer"
            ],
            "page_size": 100,
            "max_pages_per_query": 4,
            **common,
        }, "enabled-official-company-api"
    if ats == "greenhouse" and identifier:
        return True, {
            "type": "greenhouse",
            "board_token": identifier.rstrip("/").split("/")[-1],
            "access_policy": "documented_public_api",
            "max_detail_requests": 80,
            **common,
        }, "enabled-documented-public-api"
    if ats == "lever" and identifier:
        return True, {
            "type": "lever",
            "site": identifier.rstrip("/").split("/")[-1],
            "region": "eu" if "api.eu.lever" in identifier or "jobs.eu.lever" in identifier else "global",
            "access_policy": "documented_public_api",
            "page_size": 100,
            "max_pages": 30,
            "max_date_validation_requests": 60,
            **common,
        }, "enabled-documented-public-api"
    if ats == "ashby" and identifier:
        return True, {
            "type": "ashby",
            "board_name": identifier.rstrip("/").split("/")[-1],
            "access_policy": "documented_public_api",
            "include_compensation": False,
            **common,
        }, "enabled-documented-public-api"
    if ats == "smartrecruiters" and identifier:
        match = re.search(r"/companies/([^/]+)", identifier)
        company_identifier = match.group(1) if match else identifier.rstrip("/").split("/")[-1]
        return True, {
            "type": "smartrecruiters",
            "company_identifier": company_identifier,
            "access_policy": "documented_public_api",
            "public_api_policy_basis": [
                "https://developers.smartrecruiters.com/docs/posting-api",
                "https://developers.smartrecruiters.com/docs/authentication"
            ],
            "max_pages": 30,
            "max_detail_requests": 80,
            **common,
        }, "enabled-explicit-public-api-policy-exception"
    if ats == "workday" and identifier:
        parsed = workday_parts(identifier)
        if parsed:
            host, tenant, site = parsed
            return False, {
                "type": "workday",
                "host": host,
                "tenant": tenant,
                "site": site,
                "access_policy": "strict",
                "access_approved": False,
                "terms_url": "https://www.workday.com/en-us/legal/site-terms.html",
                "applied_facets": {},
                "max_pages": 100,
                "max_detail_requests": 120,
                **common,
            }, "disabled-pending-per-tenant-access-review"
    return False, {
        "type": "manual",
        "ats_observed": ats or "unknown",
        "identifier": identifier,
        **common,
    }, "research-only-no-safe-connector-yet"


def normalize(row: Dict[str, str], batch: str) -> Dict[str, Any]:
    summary = row.get("evidence_summary", "")
    evidence_urls = row.get("evidence_urls") or row.get("evidence_url(s)") or ""
    confidence = row.get("sponsorship_confidence", "historical").lower().replace(" ", "-")
    if batch == "A":
        certified_lcas = integer_from(r"(\d+)\s+Certified H-1B LCA", summary)
        software_positions = integer_from(r"(\d+)\s+had software", summary)
        change_positions = integer_from(r"(\d+)\s+change-employer position", summary)
        legal_names = row.get("matched_dol_employer_names", "")
        case_status_basis = "Certified only"
    else:
        certified_lcas = int(row.get("fy2025_q4_certified_records") or 0)
        software_positions = int(row.get("fy2025_q4_softwareish_records") or 0)
        change_positions = int(row.get("fy2025_q4_change_employer_positions") or 0)
        legal_names = row.get("matched_legal_employers", "")
        case_status_basis = "Certified or Certified-Withdrawn"
    enabled, connector, monitor_status = connector_for(row)
    return {
        "id": slug(row["canonical_name"]),
        "name": row["canonical_name"].strip(),
        "domain": row.get("domain", "").strip(),
        "careers_url": row.get("careers_url", "").strip(),
        "enabled": enabled,
        "connector": connector,
        "monitor_status": monitor_status,
        "sponsorship": {
            "confidence": confidence,
            "score": CONFIDENCE_SCORE.get(confidence, 0.30),
            "summary": summary,
            "sources": split_values(evidence_urls),
            "evidence_year": row.get("sponsorship_recent_year", ""),
            "certified_lcas": certified_lcas,
            "certified_positions": certified_lcas,
            "recent_lca_records": certified_lcas,
            "case_status_basis": case_status_basis,
            "software_related_positions": software_positions,
            "change_employer_positions": change_positions,
            "legal_employer_names": legal_names,
            "caveat": row.get("caveats", ""),
        },
        "fit_tags": split_values(row.get("role_fit_tags", "")),
        "notes": row.get("caveats", ""),
        "research_batch": batch,
        "sector": row.get("sector", ""),
    }


def merge(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    # FY2026 batch A is preferred for evidence recency and connector verification.
    if secondary["research_batch"] == "A":
        primary, secondary = secondary, primary
    primary["fit_tags"] = sorted(set(primary["fit_tags"]) | set(secondary["fit_tags"]))
    primary["sponsorship"]["sources"] = list(
        dict.fromkeys(primary["sponsorship"]["sources"] + secondary["sponsorship"]["sources"])
    )
    primary["notes"] = " ".join(dict.fromkeys(x for x in (primary["notes"], secondary["notes"]) if x))
    if not primary["enabled"] and secondary["enabled"]:
        primary["enabled"] = secondary["enabled"]
        primary["connector"] = secondary["connector"]
        primary["monitor_status"] = secondary["monitor_status"]
    primary["research_batch"] = "A+B"
    primary["sector"] = primary.get("sector") or secondary.get("sector", "")
    return primary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-a", type=Path, required=True)
    parser.add_argument("--batch-b", type=Path, required=True)
    parser.add_argument("--config-out", type=Path, required=True)
    parser.add_argument("--audit-out", type=Path, required=True)
    args = parser.parse_args()

    companies: Dict[str, Dict[str, Any]] = {}
    for batch, path in (("A", args.batch_a), ("B", args.batch_b)):
        for row in read_csv(path):
            normalized = normalize(row, batch)
            key = normalized["name"].casefold()
            companies[key] = merge(companies[key], normalized) if key in companies else normalized
    for item in companies.values():
        if item["name"] not in SAFE_SITEMAPS:
            continue
        source = SAFE_SITEMAPS[item["name"]]
        item["enabled"] = True
        item["monitor_status"] = "enabled-robots-and-terms-reviewed-sitemap-jsonld"
        item["connector"] = {
            "type": "sitemap",
            "sitemap_url": source["sitemap_url"],
            "job_url_regex": source["job_url_regex"],
            "url_include_regex": source.get("url_include_regex", TARGET_SLUG_REGEX),
            "url_exclude_regex": source.get("url_exclude_regex", SENIORITY_SLUG_EXCLUDE_REGEX),
            "access_policy": "strict",
            "allow_lastmod_as_posted_date": False,
            "max_sitemaps": source.get("max_sitemaps", 10),
            "max_detail_requests": source["max_detail_requests"],
            "crawl_delay_seconds": source.get("crawl_delay_seconds", 0),
            "terms_url": source["terms_url"],
            "access_reviewed_at": "2026-08-25",
            "access_review": source["access_review"],
            "default_country": "US",
        }

    ordered = sorted(companies.values(), key=lambda x: (-x["sponsorship"]["score"], x["name"]))

    payload = {
        "schema_version": 1,
        "generated_from": [
            "research/source_pass_a.csv",
            "research/source_pass_b.csv",
            "research/coverage_expansion_audit.csv",
        ],
        "evidence_warning": (
            "DOL-certified LCAs are employer-level evidence and do not prove USCIS petition approval, "
            "current hiring, or sponsorship availability for an individual requisition."
        ),
        "companies": ordered,
    }
    args.config_out.parent.mkdir(parents=True, exist_ok=True)
    args.config_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    fields = [
        "name", "domain", "careers_url", "sector", "sponsorship_confidence",
        "evidence_period", "recent_lca_records", "case_status_basis", "software_related_positions",
        "change_employer_positions", "legal_employer_names", "fit_tags",
        "monitor_status", "connector_type", "evidence_summary", "evidence_sources", "caveats"
    ]
    args.audit_out.parent.mkdir(parents=True, exist_ok=True)
    with args.audit_out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in ordered:
            evidence = item["sponsorship"]
            writer.writerow({
                "name": item["name"],
                "domain": item["domain"],
                "careers_url": item["careers_url"],
                "sector": item.get("sector", ""),
                "sponsorship_confidence": evidence["confidence"],
                "evidence_period": evidence["evidence_year"],
                "recent_lca_records": evidence["recent_lca_records"],
                "case_status_basis": evidence["case_status_basis"],
                "software_related_positions": evidence["software_related_positions"],
                "change_employer_positions": evidence["change_employer_positions"],
                "legal_employer_names": evidence.get("legal_employer_names", ""),
                "fit_tags": ";".join(item["fit_tags"]),
                "monitor_status": item["monitor_status"],
                "connector_type": item["connector"]["type"],
                "evidence_summary": evidence["summary"],
                "evidence_sources": ";".join(evidence["sources"]),
                "caveats": item["notes"],
            })


if __name__ == "__main__":
    main()
