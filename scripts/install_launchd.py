#!/usr/bin/env python3
"""Install (but do not run during project setup) a twice-daily macOS launchd job."""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from pathlib import Path


LABEL = "com.prudhvi.h1b-job-monitor"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    project = Path(__file__).resolve().parents[1]
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    if args.uninstall:
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
        if plist_path.exists():
            plist_path.unlink()
        print(f"Removed {plist_path}")
        return

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [
            str(Path(args.python).resolve()),
            "-m",
            "h1b_job_monitor",
            "crawl",
            "--companies",
            str(project / "config" / "companies.json"),
            "--profile",
            str(project / "config" / "profile.json"),
            "--state",
            str(project / "data" / "jobs.sqlite"),
            "--output-dir",
            str(project / "reports"),
            "--mode",
            "auto",
        ],
        "EnvironmentVariables": {"PYTHONPATH": str(project / "src")},
        "WorkingDirectory": str(project),
        "StartCalendarInterval": [
            {"Hour": 7, "Minute": 17},
            {"Hour": 19, "Minute": 17},
        ],
        "RunAtLoad": False,
        "StandardOutPath": str(project / "logs" / "launchd.stdout.log"),
        "StandardErrorPath": str(project / "logs" / "launchd.stderr.log"),
        "ProcessType": "Background",
    }
    (project / "logs").mkdir(parents=True, exist_ok=True)
    with plist_path.open("wb") as stream:
        plistlib.dump(payload, stream, sort_keys=False)
    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    print(f"Installed {plist_path}; scheduled for 07:17 and 19:17 local time.")


if __name__ == "__main__":
    main()

