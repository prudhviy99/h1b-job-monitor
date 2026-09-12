#!/usr/bin/env python3
"""Treat a validated, usable partial report as delivered, not a crashed workflow.

The report and database keep their partial status and failed-source cursors.
Unknown exits, missing reports, and wholly failed crawls remain fatal.
"""
import json
import sys
from pathlib import Path


def workflow_exit(exit_code, report):
    if exit_code == 0:
        return 0
    metadata = report.get('metadata', {}) if isinstance(report, dict) else {}
    if not isinstance(metadata, dict):
        return exit_code
    try:
        enabled = int(metadata.get('companies_enabled', 0))
        healthy = int(metadata.get('companies_ok', 0))
        failed = int(metadata.get('companies_failed', 0))
    except (TypeError, ValueError):
        return exit_code
    if (exit_code == 2 and metadata.get('status') == 'partial'
            and 0 < healthy < enabled and failed > 0
            and healthy + failed == enabled and isinstance(report.get('jobs'), list)):
        return 0
    return exit_code


if __name__ == '__main__':
    code = int(sys.argv[1])
    try:
        report = json.loads(Path(sys.argv[2]).read_text())
    except (OSError, ValueError):
        report = {}
    result = workflow_exit(code, report)
    if code and not result:
        print('::warning::Partial coverage: exact source failures are in the session report; failed-source cursors are preserved.')
    raise SystemExit(result)
