import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from h1b_job_monitor.exporters import export_run
from h1b_job_monitor.models import Company, FetchResult, Job, SponsorshipEvidence


class ExporterTests(unittest.TestCase):
    def test_csv_date_basis_and_rejection_limit(self):
        now = datetime(2026, 8, 25, tzinfo=timezone.utc)
        company = Company(
            id="example",
            name="Example",
            domain="example.com",
            careers_url="https://example.com/jobs",
            enabled=True,
            connector={"type": "greenhouse"},
            sponsorship=SponsorshipEvidence("high", 0.82, "recent", ["https://dol.gov"]),
        )

        def make_job(source_id):
            return Job(
                company_id="example",
                company="Example",
                source="greenhouse",
                source_job_id=source_id,
                title="Backend Software Engineer",
                location="Seattle, WA",
                description="Java AWS",
                source_url=f"https://example.com/jobs/{source_id}",
                posted_at=now,
                posting_date_kind="first_published",
                posting_date_confidence="high",
                rejection_reasons=["test rejection"],
            )

        emitted = make_job("accepted")
        emitted.apply_priority = "P1"
        emitted.match_score = 80
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            export_run(
                root,
                {"run_id": "run-1", "mode": "initial"},
                [emitted],
                [make_job("r1"), make_job("r2")],
                [FetchResult(company_id="example", source="greenhouse")],
                {"example": company},
                "Report",
                now,
                include_rejections=True,
                max_rejections_per_company=1,
            )
            with (root / "latest.csv").open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["posting_date_kind"], "first_published")
            with (root / "runs/run-1/rejections_audit.csv").open(
                newline="", encoding="utf-8"
            ) as stream:
                rejected = list(csv.DictReader(stream))
            self.assertEqual(len(rejected), 1)


if __name__ == "__main__":
    unittest.main()
