from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from forge.axon.lens import append_history_entry


MONITOR_SOURCE = "axon-cron"
MONITOR_JOB = "silence-check"


@dataclass(frozen=True)
class SilenceCheckResult:
    outcome: str
    alert_needed: bool
    summary: str


def run_silence_check(
    *,
    repo_root: str | Path,
    now_iso: str | None = None,
    max_silence_minutes: int = 60,
) -> SilenceCheckResult:
    root = Path(repo_root)
    history_path = root / "logs" / "history.jsonl"
    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
    entries = history_path.read_text(encoding="utf-8").splitlines() if history_path.exists() else []
    last_entry = _find_last_non_monitor_entry(entries)
    last_timestamp = (
        datetime.fromisoformat(last_entry["timestamp"]) if last_entry is not None else None
    )

    if last_timestamp and now - last_timestamp <= timedelta(minutes=max_silence_minutes):
        append_history_entry(
            root,
            {
                "timestamp": now.isoformat(),
                "source": MONITOR_SOURCE,
                "job": MONITOR_JOB,
                "summary": "Silence check passed.",
                "outcome": "success",
                "next_action": "none",
                "task_id": None,
            },
        )
        return SilenceCheckResult(
            outcome="success",
            alert_needed=False,
            summary="Silence check passed.",
        )

    summary = f"No Forge activity in >{max_silence_minutes} minutes."
    append_history_entry(
        root,
        {
            "timestamp": now.isoformat(),
            "source": MONITOR_SOURCE,
            "job": MONITOR_JOB,
            "summary": summary,
            "outcome": "failure",
            "next_action": "dispatch uplink alert",
            "task_id": None,
        },
    )
    return SilenceCheckResult(
        outcome="failure",
        alert_needed=True,
        summary=summary,
    )


def _find_last_non_monitor_entry(entries: list[str]) -> dict[str, object] | None:
    for line in reversed(entries):
        entry = json.loads(line)
        if entry.get("source") == MONITOR_SOURCE and entry.get("job") == MONITOR_JOB:
            continue
        return entry
    return None
