#!/usr/bin/env python3
"""Safely restore an optional, short-lived first-run SQLite snapshot."""

from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def restore(seed: Path, destination: Path, max_age_hours: float) -> bool:
    if destination.exists():
        print(f"State already exists at {destination}; bootstrap was not needed.")
        return True
    if not seed.exists():
        print("No bootstrap snapshot is present; the monitor will initialize a fresh 7-day state.")
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="jobs-bootstrap-", suffix=".sqlite", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with gzip.open(seed, "rb") as source, temporary.open("wb") as target:
            shutil.copyfileobj(source, target)
        connection = sqlite3.connect(str(temporary))
        try:
            integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError(f"SQLite quick_check failed: {integrity}")
            row = connection.execute(
                """
                SELECT started_at FROM runs
                WHERE status IN ('success', 'partial')
                ORDER BY started_at DESC LIMIT 1
                """
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise ValueError("bootstrap snapshot has no completed usable run")
        newest_run = parse_timestamp(str(row[0]))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        if newest_run < cutoff:
            print(
                f"Bootstrap snapshot is stale ({newest_run.isoformat()}); "
                "the monitor will initialize a fresh 7-day state."
            )
            return False
        os.replace(temporary, destination)
        print(f"Restored validated bootstrap state from {seed}.")
        return True
    except (OSError, sqlite3.Error, ValueError) as exc:
        print(f"Bootstrap snapshot was ignored safely: {type(exc).__name__}: {exc}")
        return False
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, default=Path("seed/jobs.sqlite.gz"))
    parser.add_argument("--destination", type=Path, default=Path("data/jobs.sqlite"))
    parser.add_argument("--max-age-hours", type=float, default=72.0)
    args = parser.parse_args()
    restore(args.seed, args.destination, args.max_age_hours)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
