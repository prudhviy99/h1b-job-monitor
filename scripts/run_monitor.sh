#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PYTHON_BIN=${H1B_MONITOR_PYTHON:-python3}

cd "$PROJECT_DIR"
PYTHONPATH="$PROJECT_DIR/src" "$PYTHON_BIN" -m h1b_job_monitor crawl \
  --companies "$PROJECT_DIR/config/companies.json" \
  --profile "$PROJECT_DIR/config/profile.json" \
  --state "$PROJECT_DIR/data/jobs.sqlite" \
  --output-dir "$PROJECT_DIR/reports" \
  --mode auto

