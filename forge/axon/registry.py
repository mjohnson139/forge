from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Job:
    name: str
    schedule: str
    command: str
    last_run: str | None
    last_outcome: str | None


def load_registry(path: str | Path) -> list[Job]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Job(**item) for item in data]
