from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re


ALLOWED_OUTCOMES = {"success", "failure", "partial", "skipped", "pending"}
CRON_FIELD_PATTERN = re.compile(r"^[\d*/,\-]+$")


@dataclass(frozen=True)
class Job:
    name: str
    schedule: str
    command: str
    last_run: str | None
    last_outcome: str | None


def load_registry(path: str | Path) -> list[Job]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("registry must be a JSON array")

    jobs: list[Job] = []
    seen_names: set[str] = set()
    required_keys = {"name", "schedule", "command", "last_run", "last_outcome"}

    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"job {index} must be an object")

        missing_keys = required_keys - set(item)
        if missing_keys:
            missing = ", ".join(sorted(missing_keys))
            raise ValueError(f"job {index} missing required keys: {missing}")

        extra_keys = set(item) - required_keys
        if extra_keys:
            extra = ", ".join(sorted(extra_keys))
            raise ValueError(f"job {index} has unexpected keys: {extra}")

        job = Job(**item)
        _validate_job(job, seen_names)
        seen_names.add(job.name)
        jobs.append(job)

    return jobs


def _validate_job(job: Job, seen_names: set[str]) -> None:
    if not job.name:
        raise ValueError("job name must be non-empty")
    if job.name in seen_names:
        raise ValueError(f"duplicate job name: {job.name}")

    if not job.command:
        raise ValueError(f"job {job.name} command must be non-empty")

    schedule_fields = job.schedule.split()
    if len(schedule_fields) != 5:
        raise ValueError(f"job {job.name} schedule must have 5 cron fields")
    if any(CRON_FIELD_PATTERN.fullmatch(field) is None for field in schedule_fields):
        raise ValueError(f"job {job.name} schedule contains invalid characters")

    if job.last_outcome is not None and job.last_outcome not in ALLOWED_OUTCOMES:
        raise ValueError(
            f"job {job.name} last_outcome must be one of "
            f"{', '.join(sorted(ALLOWED_OUTCOMES))} or null"
        )
