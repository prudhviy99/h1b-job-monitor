#!/usr/bin/env python3
"""Publish one permanent session-report issue, including successful zero-match runs."""
import json
import os
import re
import subprocess
from pathlib import Path


def publish_session(repository, owner, run_id, title, summary_path, new_matches, call=None, window_key=''):
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
    end_marker = f'<!-- /h1b-session:{run_id} -->'
    window_marker = f'<!-- h1b-window:{window_key} -->' if window_key else ''
    body = marker + '\n\n' + summary_path.read_text(encoding='utf-8')
    body += f'\n\n[Download this session’s HTML, CSV and JSON report](https://github.com/{repository}/actions/runs/{run_id}).\n'
    body += '\nThis is a session snapshot, not a rolling queue. Earlier reports remain available; later reports exclude unchanged previously reported jobs.\n'
    body += '\n' + end_marker + '\n'
    issue_path = summary_path.with_name('session-issue.md')
    # Paginate all labeled reports: rerunning even an old workflow must not
    # create a second issue merely because the first left a recent-results cap.
    pages = json.loads(gh('api', f'repos/{repository}/issues?state=all&labels={label}&per_page=100',
                         '--paginate', '--slurp'))
    reports = [r for page in pages for r in page]
    existing = next((r for r in reports if marker in (r.get('body') or '')), None)
    if existing and end_marker in (existing.get('body') or ''):
        # Rerun replaces only its own section, never other checks or earlier jobs.
        body = re.sub(re.escape(marker) + r'.*?' + re.escape(end_marker),
                      lambda _: body.strip(), existing['body'], flags=re.S)
        title = existing.get('title') or title
    elif not existing and not new_matches and window_marker:
        candidates = [r for r in reports if window_marker in (r.get('body') or '')]
        if candidates:
            existing = max(candidates, key=lambda r: r['number'])
            body = existing['body'] + '\n\n---\n\n## Follow-up check (no new jobs)\n\n' + body
            title = existing.get('title') or title
    if window_marker and window_marker not in body:
        body = window_marker + '\n\n' + body
    issue_path.write_text(body, encoding='utf-8')
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
                          Path('reports/github-summary.md'), int(os.environ['NEW_MATCHES']),
                          window_key=os.environ.get('SESSION_WINDOW', '')))
