"""Application availability checks shared by initial and incremental reports."""
from datetime import datetime
from .models import Job
from .util import parse_datetime


def open_for_application(job: Job, now: datetime) -> bool:
    for field in ("validThrough", "application_deadline", "PostingEndDate"):
        deadline = parse_datetime(job.raw.get(field))
        if deadline and deadline.date() < now.date():
            return False
    return job.raw.get("canApply") is not False and job.raw.get("isListed") is not False
