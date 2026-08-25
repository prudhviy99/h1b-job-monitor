import csv
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "github_summary", ROOT / "scripts" / "github_summary.py"
)
github_summary = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(github_summary)


class GitHubSummaryTests(unittest.TestCase):
    def test_sanitizes_markdown_and_rejects_unsafe_urls(self):
        rendered = github_summary.markdown_text("@person [click](javascript:alert(1))\n# heading")
        self.assertNotIn("@person", rendered)
        self.assertIn("&#64;person", rendered)
        self.assertIn("\\[click\\]", rendered)
        self.assertEqual(github_summary.safe_url("javascript:alert(1)"), "")
        self.assertEqual(github_summary.safe_url("https://user:pass@example.com/job"), "")
        self.assertTrue(github_summary.safe_url("https://example.com/a_(b)?x=1"))

    def test_partial_report_is_source_failure_not_total_failure_and_filters_priorities(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            report = path / "latest.json"
            health = path / "health.csv"
            output = path / "summary.md"
            github_output = path / "outputs.txt"
            report.write_text(json.dumps({
                "metadata": {
                    "run_id": "run-1",
                    "mode": "incremental",
                    "status": "partial",
                    "companies_failed": 1,
                },
                "jobs": [
                    {
                        "apply_priority": "P1",
                        "company": "Example",
                        "title": "Backend Engineer",
                        "apply_url": "https://example.com/job",
                    },
                    {
                        "apply_priority": "REJECT",
                        "company": "Noise",
                        "title": "Unrelated",
                        "apply_url": "https://example.com/noise",
                    },
                ],
            }), encoding="utf-8")
            with health.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=["company", "source", "status", "warning", "error"]
                )
                writer.writeheader()
                writer.writerow({
                    "company": "Flaky",
                    "source": "greenhouse",
                    "status": "degraded",
                    "warning": "one detail failed",
                    "error": "",
                })

            argv = [
                "github_summary.py",
                "--report", str(report),
                "--health", str(health),
                "--output", str(output),
                "--monitor-outcome", "failure",
            ]
            with patch.object(sys, "argv", argv), patch.dict(
                os.environ, {"GITHUB_OUTPUT": str(github_output)}, clear=False
            ):
                self.assertEqual(github_summary.main(), 0)

            summary = output.read_text(encoding="utf-8")
            outputs = github_output.read_text(encoding="utf-8")
            self.assertIn("## Source failures", summary)
            self.assertNotIn("## Monitor failure", summary)
            self.assertIn("Backend Engineer", summary)
            self.assertNotIn("Unrelated", summary)
            self.assertIn("alert_kind=failure", outputs)
            self.assertIn("new_matches=1", outputs)
            self.assertIn("match_title=H-1B monitor: 1 new match", outputs)


if __name__ == "__main__":
    unittest.main()
