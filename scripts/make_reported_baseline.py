#!/usr/bin/env python3
"""Create public, minimal delivery receipts from a completed local report."""
import argparse
import hashlib
import json
from pathlib import Path


def build_baseline(report_bytes):
    report = json.loads(report_bytes)
    meta = report['metadata']
    if meta['status'] not in {'success', 'partial'}:
        raise ValueError('Cannot acknowledge a failed or incomplete report')
    jobs = report['jobs']
    if any(j.get('apply_priority') not in {'P0', 'P1', 'P2'} or not j.get('posted_at')
           or not j.get('job_key') for j in jobs):
        raise ValueError('Report contains invalid delivery candidates')
    return {'schema_version': 1, 'report_id': meta['run_id'], 'reported_at': meta['started_at'],
            'source_report_sha256': hashlib.sha256(report_bytes).hexdigest(),
            'jobs': [{'job_key': j['job_key'], 'posted_at': j['posted_at']} for j in jobs]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    baseline = build_baseline(args.report.read_bytes())
    args.output.write_text(json.dumps(baseline, indent=2) + '\n', encoding='utf-8')
    print(f"Recorded {len(baseline['jobs'])} local report receipts; no SQLite state was replaced.")
