#!/usr/bin/env python3
"""Back up durable job identity state; never silently reinitialize a hosted monitor."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

BACKUP_PREFIX = "h1b-state-backup-"
MAX_STATE_BYTES = 1024 * 1024 * 1024


def inspect_state(path):
    path = Path(path).resolve()
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed.")
        counts = {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                  for name in ("jobs", "runs", "sightings", "company_runs")}
        row = connection.execute(
            "SELECT run_id FROM runs WHERE status IN ('success','partial') ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            raise ValueError("Database has no completed usable crawl.")
    return {"counts": counts, "latest_run_id": row[0]}


def make_backup(state, output):
    state, output = Path(state), Path(output)
    original = inspect_state(state)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="h1b-snapshot-") as temporary:
        copy = Path(temporary) / "jobs.sqlite"
        with closing(sqlite3.connect(state.resolve().as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(copy)) as target:
                source.backup(target)
                # Only the disposable response cache is omitted from the COPY.
                # All jobs, sightings, delivery markers, cursors, and history stay.
                if target.execute("SELECT 1 FROM sqlite_master WHERE name='http_cache'").fetchone():
                    target.execute("DELETE FROM http_cache")
                    target.commit()
                target.execute("VACUUM")
                target.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                target.execute("PRAGMA journal_mode=DELETE")
        if inspect_state(copy) != original:
            raise ValueError("Backup changed durable job-state counts.")
        compressed = output / "jobs.sqlite.gz"
        with copy.open("rb") as source, gzip.open(compressed, "wb") as target:
            shutil.copyfileobj(source, target)
    manifest = dict(original, version=1, created_at=datetime.now(timezone.utc).isoformat(),
                    sha256=hashlib.sha256(compressed.read_bytes()).hexdigest())
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def restore_archive(archive, destination):
    destination = Path(destination)
    if destination.exists():
        inspect_state(destination)
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="h1b-recover-", dir=destination.parent) as temporary:
        restored = Path(temporary) / "jobs.sqlite"
        with zipfile.ZipFile(archive) as zipped:
            # Read specific entries only; never extract untrusted archive paths.
            if zipped.getinfo("jobs.sqlite.gz").file_size > MAX_STATE_BYTES:
                raise ValueError("Backup archive is too large.")
            manifest = json.loads(zipped.read("manifest.json"))
            compressed = zipped.read("jobs.sqlite.gz")
        if manifest.get("version") != 1 or hashlib.sha256(compressed).hexdigest() != manifest.get("sha256"):
            raise ValueError("Backup manifest/checksum mismatch.")
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as source, restored.open("wb") as target:
            written = 0
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_STATE_BYTES:
                    raise ValueError("Expanded backup is too large.")
                target.write(chunk)
        restored_info = inspect_state(restored)
        if any(restored_info[key] != manifest.get(key) for key in ("counts", "latest_run_id")):
            raise ValueError("Restored state does not match its manifest.")
        # Same-filesystem link is atomic and refuses to replace an existing DB.
        os.link(restored, destination)
    return True


def gh_json(endpoint):
    return json.loads(subprocess.check_output(["gh", "api", endpoint], text=True))


def recover(state, repository):
    state = Path(state)
    if state.exists():
        inspect_state(state)
        print("Validated existing persistent state; no recovery needed.")
        return
    artifacts = gh_json(f"repos/{repository}/actions/artifacts?per_page=100")["artifacts"]
    backups = sorted(
        (a for a in artifacts if a["name"].startswith(BACKUP_PREFIX) and not a["expired"]),
        key=lambda a: a["created_at"], reverse=True,
    )
    if not backups:
        raise RuntimeError("State cache is missing and no recoverable backup exists. Refusing to reset seen jobs.")
    backup = backups[0]
    newer_reports = [
        a for a in artifacts if a["name"].startswith("h1b-job-report-")
        and a["created_at"] > backup["created_at"]
        and a.get("workflow_run", {}).get("id") != backup.get("workflow_run", {}).get("id")
    ]
    if newer_reports:
        raise RuntimeError("A newer crawl report exists without its state backup. Refusing a stale rollback.")
    if backup["size_in_bytes"] > MAX_STATE_BYTES:
        raise ValueError("Remote backup is too large.")
    with tempfile.TemporaryDirectory(prefix="h1b-download-") as temporary:
        archive = Path(temporary) / "backup.zip"
        with archive.open("wb") as target:
            subprocess.run(["gh", "api", f"repos/{repository}/actions/artifacts/{backup['id']}/zip"],
                           check=True, stdout=target)
        restore_archive(archive, state)
    print(f"Recovered validated state from {backup['name']}; seen jobs were preserved.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("backup", "recover"))
    parser.add_argument("--state", type=Path, default=Path("data/jobs.sqlite"))
    parser.add_argument("--output", type=Path, default=Path("state-backup"))
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    args = parser.parse_args()
    if args.operation == "backup":
        print(json.dumps(make_backup(args.state, args.output), indent=2))
    else:
        recover(args.state, args.repository)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
