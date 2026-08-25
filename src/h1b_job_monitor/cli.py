from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import logging
import logging.handlers
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from . import __version__
from .config import load_companies, load_json
from .monitor import JobMonitor
from .ranking import Ranker
from .state import StateStore
from .util import parse_datetime


@contextlib.contextmanager
def exclusive_run_lock(state_path: Path):
    lock_path = state_path.with_suffix(state_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"Another crawl is already using {state_path}") from exc
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def configure_logging(log_file: Path, verbose: bool) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)
    rotating = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    rotating.setFormatter(formatter)
    root.addHandler(rotating)


def validate(companies_path: Path, profile_path: Path) -> int:
    companies = load_companies(companies_path)
    profile = load_json(profile_path)
    errors: List[str] = []
    enabled = 0
    known = {"amazon", "greenhouse", "lever", "ashby", "smartrecruiters", "workday", "sitemap", "jsonld_pages"}
    for company in companies:
        if company.enabled:
            enabled += 1
            kind = company.connector.get("type")
            if kind not in known:
                errors.append(f"{company.id}: enabled unknown connector {kind!r}")
        if not company.sponsorship.sources:
            errors.append(f"{company.id}: sponsorship evidence has no source URL")
        for url in company.sponsorship.sources:
            if not url.startswith("https://"):
                errors.append(f"{company.id}: non-HTTPS evidence URL {url!r}")
    if not profile.get("candidate") or not profile.get("filters"):
        errors.append("profile must contain candidate and filters")
    try:
        Ranker(profile)
    except (KeyError, TypeError, ValueError, re.error) as exc:
        errors.append(f"invalid matching/ranking configuration: {exc}")
    result = {
        "companies": len(companies),
        "enabled": enabled,
        "disabled_research_only": len(companies) - enabled,
        "errors": errors,
    }
    print(json.dumps(result, indent=2))
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="h1b-job-monitor")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    crawl = sub.add_parser("crawl", help="Fetch official sources, filter, rank, persist, and export")
    crawl.add_argument("--companies", type=Path, default=Path("config/companies.json"))
    crawl.add_argument("--profile", type=Path, default=Path("config/profile.json"))
    crawl.add_argument("--state", type=Path, default=Path("data/jobs.sqlite"))
    crawl.add_argument("--output-dir", type=Path, default=Path("reports"))
    crawl.add_argument("--mode", choices=("auto", "initial", "incremental"), default="auto")
    crawl.add_argument("--company", action="append", dest="company_ids")
    crawl.add_argument("--now", help="UTC/ISO timestamp override for reproducible tests")
    crawl.add_argument("--verbose", action="store_true")

    check = sub.add_parser("validate-config", help="Validate company and profile configuration")
    check.add_argument("--companies", type=Path, default=Path("config/companies.json"))
    check.add_argument("--profile", type=Path, default=Path("config/profile.json"))
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-config":
        return validate(args.companies, args.profile)

    configure_logging(Path("logs/monitor.log"), args.verbose)
    companies = load_companies(args.companies)
    profile = load_json(args.profile)
    now = parse_datetime(args.now) if args.now else None
    if args.now and now is None:
        raise SystemExit(f"Could not parse --now={args.now!r}")
    with exclusive_run_lock(args.state):
        state = StateStore(args.state)
        try:
            monitor = JobMonitor(companies, profile, state, args.output_dir)
            result = monitor.run(args.mode, now=now, selected_company_ids=args.company_ids)
        finally:
            state.close()
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
