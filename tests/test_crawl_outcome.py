import unittest
from scripts.crawl_outcome import workflow_exit


class CrawlOutcomeTests(unittest.TestCase):
    def test_partial_delivery_is_not_a_workflow_crash(self):
        report = {'metadata': {'status': 'partial', 'companies_enabled': 65,
                              'companies_ok': 64, 'companies_failed': 1}, 'jobs': []}
        self.assertEqual(workflow_exit(2, report), 0)
        self.assertEqual(report['metadata']['status'], 'partial')
        for code in (1, 124, 137):
            self.assertEqual(workflow_exit(code, report), code)

    def test_missing_malformed_and_all_failed_reports_remain_fatal(self):
        for report in ({}, [], {'metadata': None}, {'metadata': {'status': 'success'}},
                       {'metadata': {'status': 'partial', 'companies_enabled': 65,
                                     'companies_ok': 0, 'companies_failed': 65}, 'jobs': []},
                       {'metadata': {'status': 'partial', 'companies_enabled': 65,
                                     'companies_ok': 64, 'companies_failed': 2}, 'jobs': []}):
            with self.subTest(report=report):
                self.assertEqual(workflow_exit(2, report), 2)

    def test_workflow_keeps_fatal_propagation_and_raw_exit_for_summary(self):
        from pathlib import Path
        workflow = (Path(__file__).resolve().parents[1]/'.github/workflows/job-monitor.yml').read_text()
        self.assertIn('echo "exit_code=$status"', workflow)
        self.assertIn('python scripts/crawl_outcome.py "$status" reports/latest.json', workflow)
        self.assertIn("steps.crawl.outcome == 'failure'", workflow)
        self.assertIn("steps.state-save.outcome == 'failure'", workflow)
        self.assertNotIn('gh issue comment', workflow)
