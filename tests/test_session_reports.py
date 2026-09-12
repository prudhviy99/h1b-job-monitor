import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from h1b_job_monitor.eligibility import open_for_application
from h1b_job_monitor.models import FetchResult
from h1b_job_monitor.monitor import JobMonitor
from h1b_job_monitor.state import StateStore
from h1b_job_monitor.util import stable_job_key
from scripts.github_session import publish_session
from scripts.make_reported_baseline import build_baseline
from test_monitor import make_job, make_company, PROFILE

NOW = datetime(2026, 9, 6, 17, tzinfo=timezone.utc)


class SessionReportTests(unittest.TestCase):
    def test_local_receipts_preserve_history_and_allow_later_reposts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = StateStore(root/'db.sqlite')
            monitor = JobMonitor([make_company()], PROFILE, store, root/'reports')
            local_job = make_job(NOW - timedelta(days=1))
            key = stable_job_key(local_job.company_id, local_job.source_job_id, local_job.source_url, local_job.title, local_job.location)
            baseline = {'schema_version':1, 'report_id':'local-week', 'reported_at':NOW.isoformat(),
                        'jobs':[{'job_key':key, 'posted_at':local_job.posted_at.isoformat()}]}
            # Receipts must not fabricate a successful full-company crawl.
            store.import_reported_baseline(baseline)
            store.import_reported_baseline(baseline)
            self.assertIsNone(store.last_usable_run_started_at())
            self.assertEqual(store.conn.execute('select count(*) from external_report_receipts').fetchone()[0], 1)
            monitor._fetch_one = lambda *a: FetchResult(company_id='example', source='greenhouse', jobs=[local_job])
            self.assertEqual(monitor.run(now=NOW)['emitted_jobs'], 0)
            self.assertFalse((root/'reports/application-queue.json').exists())
            self.assertEqual(json.loads((root/'reports/latest.json').read_text())['jobs'], [])
            history = store.last_usable_run_started_at()
            store.import_reported_baseline(baseline)
            self.assertEqual(store.last_usable_run_started_at(), history)
            repost = make_job(NOW + timedelta(hours=13))
            monitor._fetch_one = lambda *a: FetchResult(company_id='example', source='greenhouse', jobs=[repost])
            self.assertEqual(monitor.run(now=NOW+timedelta(hours=14))['emitted_jobs'], 1)
            self.assertEqual(json.loads((root/'reports/latest.json').read_text())['jobs'][0]['event_type'], 'reposted')
            self.assertEqual(monitor.run(now=NOW+timedelta(hours=15))['emitted_jobs'], 0)
            store.close()

    def test_baseline_validation_is_atomic_and_never_moves_watermark_backward(self):
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory)/'db.sqlite')
            baseline = {'schema_version':1, 'report_id':'local', 'reported_at':NOW.isoformat(),
                        'jobs':[{'job_key':'a'*64, 'posted_at':NOW.isoformat()}]}
            store.import_reported_baseline(baseline)
            baseline['jobs'][0]['posted_at'] = (NOW-timedelta(days=1)).isoformat()
            store.import_reported_baseline(baseline)
            self.assertEqual(store.conn.execute('select posted_at from external_report_receipts').fetchone()[0], NOW.isoformat())
            baseline['jobs'].append({'job_key':'invalid','posted_at':NOW.isoformat()})
            with self.assertRaises(ValueError): store.import_reported_baseline(baseline)
            self.assertEqual(store.conn.execute('select count(*) from external_report_receipts').fetchone()[0], 1)
            store.close()

    def test_report_only_excludes_expired_postings(self):
        job = make_job(NOW)
        for raw in ({'validThrough':'2026-09-05'}, {'canApply':False}, {'isListed':False}):
            job.raw = raw
            self.assertFalse(open_for_application(job, NOW))
        job.raw = {'PostingEndDate':'2026-09-06'}
        self.assertTrue(open_for_application(job, NOW))

    def test_zero_match_session_creates_issue_and_same_workflow_updates_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'summary.md'; path.write_text('No new verified matches.')
            calls=[]
            def fake(*args):
                calls.append(args)
                return '[[]]' if args[0]=='api' else 'https://github.com/o/r/issues/1'
            publish_session('o/r', 'o', '123', 'Zero matches', path, 0, fake)
            create = next(c for c in calls if c[:2]==('issue','create'))
            self.assertIn('h1b-session-report', create)
            self.assertIn('--assignee', create)
            self.assertIn('h1b-session:123', path.with_name('session-issue.md').read_text())
            calls.clear()
            def existing(*args):
                calls.append(args)
                return json.dumps([[{'number':1,'body':'<!-- h1b-session:123 -->'}]]) if args[0]=='api' else ''
            publish_session('o/r', 'o', '123', 'Retry result', path, 1, existing)
            self.assertTrue(any(c[:2]==('issue','edit') for c in calls))
            self.assertFalse(any(c[:2] in [('issue','create'),('issue','close')] for c in calls))

    def test_baseline_contains_no_resume_or_application_history(self):
        report = {'metadata':{'status':'success','run_id':'local','started_at':NOW.isoformat()},
                  'jobs':[{'job_key':'a'*64,'posted_at':NOW.isoformat(),'apply_priority':'P1',
                           'description':'company text','resume':'must not be copied'}]}
        result = build_baseline(json.dumps(report).encode())
        self.assertEqual(set(result['jobs'][0]), {'job_key','posted_at'})
        self.assertNotIn('resume', json.dumps(result))

    def test_zero_match_retry_updates_window_report_without_losing_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'summary.md'
            path.write_text('Original job: Backend Engineer')
            calls = []
            reports = []
            def fake(*args):
                calls.append(args)
                return json.dumps([reports]) if args[0] == 'api' else 'https://github.com/o/r/issues/9'
            publish_session('o/r', 'o', '123', 'First report', path, 1, fake, '2026-09-12-morning')
            reports.append({'number':9, 'title':'First report', 'body':path.with_name('session-issue.md').read_text()})
            calls.clear()
            path.write_text('Expedia access denied; 64/65 healthy; no new matches')
            publish_session('o/r', 'o', '124', 'Retry', path, 0, fake, '2026-09-12-morning')
            body = path.with_name('session-issue.md').read_text()
            self.assertIn('Original job: Backend Engineer', body)
            self.assertIn('Expedia access denied', body)
            self.assertFalse(any(c[:2] == ('issue','create') for c in calls))
            self.assertFalse(any(c[:2] == ('issue','comment') for c in calls))
            reports[0]['body'] = body
            path.write_text('Recovered; 65/65 healthy')
            publish_session('o/r', 'o', '124', 'Retry rerun', path, 0, fake, '2026-09-12-morning')
            updated = path.with_name('session-issue.md').read_text()
            self.assertIn('Original job: Backend Engineer', updated)
            self.assertNotIn('Expedia access denied', updated)
            self.assertEqual(updated.count('<!-- h1b-session:124 -->'), 1)
            calls.clear()
            publish_session('o/r', 'o', '125', 'Evening', path, 0, fake, '2026-09-12-evening')
            self.assertTrue(any(c[:2] == ('issue','create') for c in calls))
            calls.clear()
            publish_session('o/r', 'o', '126', 'New jobs in retry', path, 1, fake, '2026-09-12-morning')
            self.assertTrue(any(c[:2] == ('issue','create') for c in calls))


if __name__ == '__main__':
    unittest.main()
