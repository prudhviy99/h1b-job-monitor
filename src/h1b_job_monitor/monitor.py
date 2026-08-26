from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .connectors import make_connector
from .exporters import export_run
from .http import HttpClient
from .models import Company, FetchResult, Job
from .ranking import Ranker
from .state import StateStore


LOGGER = logging.getLogger(__name__)


class JobMonitor:
    def __init__(
        self,
        companies: List[Company],
        profile: Dict[str, Any],
        state: StateStore,
        output_dir: Path,
    ) -> None:
        self.companies = companies
        self.profile = profile
        self.state = state
        self.output_dir = Path(output_dir)
        network = profile.get("network", {})
        self.client = HttpClient(
            state=state,
            user_agent=str(network.get("user_agent", "H1BJobMonitor/1.0")),
            timeout_seconds=float(network.get("timeout_seconds", 25)),
            min_interval_seconds=float(network.get("min_interval_seconds_per_host", 0.8)),
            max_retries=int(network.get("max_retries", 3)),
            max_response_bytes=int(network.get("max_response_bytes", 15_000_000)),
        )
        self.workers = max(1, min(12, int(network.get("company_workers", 4))))
        self.ranker = Ranker(profile)
        candidate = profile.get("candidate", {})
        self.profile_revision = str(candidate.get("profile_revision", "unversioned"))
        fingerprint_payload = {
            "profile_revision": self.profile_revision,
            "candidate_years": candidate.get("years_of_relevant_us_experience"),
            "highest_degree": candidate.get("highest_degree"),
            "filters": profile.get("filters", {}),
            "matching": profile.get("matching", {}),
        }
        serialized_profile = json.dumps(
            fingerprint_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.profile_fingerprint = hashlib.sha256(serialized_profile.encode("utf-8")).hexdigest()[:16]

    def _fetch_one(self, company: Company, since: datetime, mode: str) -> FetchResult:
        connector_type = str(company.connector.get("type", ""))
        try:
            connector = make_connector(connector_type)
            return connector.fetch(company, self.client, since, mode=mode)
        except Exception as exc:
            LOGGER.exception("Source failed for %s", company.name)
            return FetchResult(
                company_id=company.id,
                source=connector_type,
                requests=self.client.request_count,
                error=f"{type(exc).__name__}: {exc}",
            )

    def run(
        self,
        mode: str = "auto",
        now: Optional[datetime] = None,
        selected_company_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        previous_usable = self.state.last_usable_run_started_at()
        if mode == "auto":
            mode = "incremental" if previous_usable else "initial"
        if mode not in {"initial", "incremental"}:
            raise ValueError("mode must be auto, initial, or incremental")
        filters = self.profile.get("filters", {})
        lookback = int(filters.get("lookback_days", 7))
        initial_since = now - timedelta(days=lookback)
        if mode == "incremental" and previous_usable is None:
            mode = "initial"

        enabled = [company for company in self.companies if company.enabled]
        if selected_company_ids:
            wanted = set(selected_company_ids)
            enabled = [company for company in enabled if company.id in wanted]
            missing = wanted - {company.id for company in enabled}
            if missing:
                raise ValueError(f"Unknown or disabled company id(s): {sorted(missing)}")
        if selected_company_ids:
            company_map = {company.id: company for company in enabled}
            disabled_health: List[FetchResult] = []
        else:
            company_map = {company.id: company for company in self.companies}
            disabled_health = []
            for company in self.companies:
                if company.enabled:
                    continue
                connector_type = str(company.connector.get("type", "manual"))
                if connector_type == "workday":
                    warning = "Disabled pending per-tenant robots/terms review or explicit access approval."
                else:
                    warning = "Research universe only: no supported safe read-only connector is enabled."
                disabled_health.append(
                    FetchResult(
                        company_id=company.id,
                        source=connector_type,
                        skipped=True,
                        warning=warning,
                    )
                )
        overlap = timedelta(hours=float(filters.get("incremental_overlap_hours", 6)))
        company_since: Dict[str, datetime] = {}
        company_modes: Dict[str, str] = {}
        profile_backfill_company_ids = set()
        for company in enabled:
            connector_type = str(company.connector.get("type", ""))
            previous_company_success = self.state.last_successful_company_run_started_at(
                company.id, connector_type
            )
            previous_profile_fingerprint = self.state.company_profile_fingerprint(
                company.id, connector_type
            )
            profile_changed = previous_profile_fingerprint != self.profile_fingerprint
            if mode == "initial" or previous_company_success is None or profile_changed:
                company_since[company.id] = initial_since
                company_modes[company.id] = "initial"
                if profile_changed:
                    profile_backfill_company_ids.add(company.id)
            else:
                company_since[company.id] = previous_company_success - overlap
                company_modes[company.id] = "incremental"
        since = min(company_since.values(), default=initial_since)

        run_id = self.state.start_run(mode, len(enabled), now)
        results: List[FetchResult] = list(disabled_health)
        stats = {
            "companies_ok": 0,
            "companies_failed": 0,
            "companies_degraded": 0,
            "fetched_jobs": 0,
            "accepted_jobs": 0,
            "emitted_jobs": 0,
        }
        emitted: List[Job] = []
        emitted_keys = set()
        rejected: List[Job] = []
        fatal_error = ""
        try:
            with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="company") as pool:
                futures = {
                    pool.submit(
                        self._fetch_one,
                        company,
                        company_since[company.id],
                        company_modes[company.id],
                    ): company
                    for company in enabled
                }
                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
                    status = (
                        "skipped" if result.skipped
                        else ("error" if result.error else ("degraded" if not result.cursor_complete else "ok"))
                    )
                    if result.error or result.skipped:
                        stats["companies_failed"] += 1
                    elif not result.cursor_complete:
                        stats["companies_failed"] += 1
                        stats["companies_degraded"] += 1
                    else:
                        stats["companies_ok"] += 1
                    self.state.record_company_run(
                        run_id,
                        result.company_id,
                        result.source,
                        status,
                        len(result.jobs),
                        result.requests,
                        result.error,
                        result.warning,
                    )
                    stats["fetched_jobs"] += len(result.jobs)

            allowed_date_confidence = set(filters.get("date_confidence_allowed", ["high", "medium_high", "medium"]))
            for result in results:
                if result.error or result.skipped:
                    continue
                company = company_map[result.company_id]
                result_since = company_since[result.company_id]
                result_mode = company_modes[result.company_id]
                for job in result.jobs:
                    job.discovered_at = now
                    job.sponsorship_confidence = company.sponsorship.confidence
                    job.sponsorship_evidence = company.sponsorship.summary
                    decision = self.ranker.evaluate(job, company, now=now)
                    job.match_score = decision.score
                    job.apply_priority = decision.priority
                    job.why_matches = decision.why
                    job.rejection_reasons = decision.rejection_reasons
                    job.extracted_min_years = decision.min_years
                    job.extracted_max_years = decision.max_years
                    job.sponsorship_score = decision.sponsorship_score
                    job.role_sponsorship_signal = decision.sponsorship_signal

                    previous = self.state.get_previous(job)
                    previously_delivered = self.state.was_emitted_in_usable_run(job)
                    previous_posted = None
                    if previous is not None and previous["posted_at"]:
                        previous_posted = datetime.fromisoformat(previous["posted_at"])
                    date_verified = (
                        job.posted_at is not None and job.posting_date_confidence in allowed_date_confidence
                    )
                    fresh = False
                    provisional_event = "new" if previous is None or not previously_delivered else "seen"
                    if result_mode == "initial":
                        fresh = bool(
                            date_verified
                            and result_since <= job.posted_at <= now + timedelta(hours=24)
                        )
                        if not fresh:
                            job.rejection_reasons.append("not a verified posting from the initial 7-day window")
                    elif previous is None or not previously_delivered:
                        provisional_event = "new"
                        allow_undated = bool(filters.get("subsequent_run_allows_new_undated_jobs", False))
                        fresh = bool(
                            (date_verified and result_since <= job.posted_at <= now + timedelta(hours=24))
                            or (allow_undated and job.posted_at is None)
                        )
                        if not fresh:
                            job.rejection_reasons.append("newly discovered, but posting date is stale or unverified")
                    elif (
                        date_verified
                        and previous_posted is not None
                        and job.posted_at > previous_posted + timedelta(hours=12)
                        and job.posted_at >= result_since
                    ):
                        provisional_event = "reposted"
                        fresh = True

                    accepted = decision.accepted and fresh
                    if decision.accepted:
                        stats["accepted_jobs"] += 1
                    job_key, actual_event = self.state.upsert_job(
                        run_id, job, accepted=decision.accepted, emitted=False, seen_at=now
                    )
                    job.event_type = (
                        provisional_event
                        if provisional_event in {"new", "reposted"}
                        else actual_event
                    )
                    should_emit = (
                        accepted
                        and job_key not in emitted_keys
                        and provisional_event in {"new", "reposted"}
                    )
                    if should_emit:
                        emitted_keys.add(job_key)
                        emitted.append(job)
                    elif job.rejection_reasons:
                        rejected.append(job)

            stats["emitted_jobs"] = len(emitted)
            if stats["companies_ok"] + stats["companies_degraded"] == 0:
                status = "failed"
            elif stats["companies_failed"]:
                status = "partial"
            else:
                status = "success"
            metadata = {
                "run_id": run_id,
                "mode": mode,
                "status": status,
                "started_at": now.isoformat(),
                "since": since.isoformat(),
                "cursor_strategy": "per_company",
                "profile_revision": self.profile_revision,
                "profile_fingerprint": self.profile_fingerprint,
                "profile_backfill_companies": len(profile_backfill_company_ids),
                "companies_configured": len(self.companies),
                "companies_enabled": len(enabled),
                **stats,
            }
            report_title = str(
                self.profile.get("reporting", {}).get(
                    "html_title", "Verified H-1B job matches"
                )
            )
            reporting = self.profile.get("reporting", {})
            run_dir = export_run(
                self.output_dir,
                metadata,
                emitted,
                rejected,
                results,
                company_map,
                report_title,
                now,
                include_rejections=bool(reporting.get("include_rejections_in_audit", True)),
                max_rejections_per_company=int(reporting.get("max_rejections_per_company", 50)),
            )
            metadata["run_dir"] = str(run_dir)
            completed_profile_sources = [
                (result.company_id, result.source)
                for result in results
                if (
                    result.company_id in company_since
                    and not result.error
                    and not result.skipped
                    and result.cursor_complete
                )
            ]
            self.state.finalize_usable_run(
                run_id,
                status,
                stats,
                [job.job_key for job in emitted],
                now,
                completed_profile_sources,
                self.profile_fingerprint,
            )
            return metadata
        except Exception as exc:
            fatal_error = f"{type(exc).__name__}: {exc}"
            self.state.finish_run(run_id, "failed", stats, fatal_error)
            raise
