#!/usr/bin/env python3
"""Publish one permanent session-report issue, including successful zero-match runs."""
import json
import os
import subprocess
from pathlib import Path


def publish_session(repository, owner, run_id, title, summary_path, new_matches, call=None):
    def invoke(*args):
        command = ['gh', *args]
        if args[0] != 'api':
            command += ['--repo', repository]
        return subprocess.check_output(command, text=True).strip()
    gh = call or invoke
    label = 'h1b-session-report'
    gh('label', 'create', label, '--color', '0052cc', '--description',
       'Permanent report for each actual crawl, including zero matches', '--force')
    marker = f'<!-- h1b-session:{run_id} -->'
    body = summary_path.read_text(encoding='utf-8')
    body += f'\n\n{marker}\n\n[Download this session’s HTML, CSV and JSON report](https://github.com/{repository}/actions/runs/{run_id}).\n'
    body += '\nThis is a session snapshot, not a rolling queue. Earlier reports remain available; later reports exclude unchanged previously reported jobs.\n'
    issue_path = summary_path.with_name('session-issue.md')
    issue_path.write_text(body, encoding='utf-8')
    # Paginate all labeled reports: rerunning even an old workflow must not
    # create a second issue merely because the first left a recent-results cap.
    pages = json.loads(gh('api', f'repos/{repository}/issues?state=all&labels={label}&per_page=100',
                         '--paginate', '--slurp'))
    existing = next((r for page in pages for r in page if marker in (r.get('body') or '')), None)
    labels = [label]
    if new_matches:
        gh('label', 'create', 'h1b-monitor-match', '--color', '1D76DB',
           '--description', 'New verified H-1B-friendly role matches', '--force')
        labels.append('h1b-monitor-match')
    if existing:
        gh('issue', 'edit', str(existing['number']), '--title', title, '--body-file', str(issue_path),
           '--add-label', ','.join(labels))
        return f"https://github.com/{repository}/issues/{existing['number']}"
    return gh('issue', 'create', '--title', title, '--body-file', str(issue_path),
              '--label', ','.join(labels), '--assignee', owner)


if __name__ == '__main__':
    print(publish_session(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_REPOSITORY_OWNER'],
                          os.environ['GITHUB_RUN_ID'], os.environ['SESSION_TITLE'],
                          Path('reports/github-summary.md'), int(os.environ['NEW_MATCHES'])))
