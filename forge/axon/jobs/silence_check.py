from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from forge.axon.lens import append_history_entry


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
    last_entry = json.loads(entries[-1]) if entries else None
    last_timestamp = (
        datetime.fromisoformat(last_entry["timestamp"]) if last_entry is not None else None
    )

    if last_timestamp and now - last_timestamp <= timedelta(minutes=max_silence_minutes):
        append_history_entry(
            root,
            {
                "timestamp": now.isoformat(),
                "source": "axon-cron",
                "job": "silence-check",
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

    summary = "No Forge activity in >60 minutes."
    append_history_entry(
        root,
        {
            "timestamp": now.isoformat(),
            "source": "axon-cron",
            "job": "silence-check",
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
