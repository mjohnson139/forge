from __future__ import annotations

import json
from pathlib import Path


def append_history_entry(repo_root: str | Path, entry: dict[str, object]) -> None:
    logs_dir = Path(repo_root) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    history_path = logs_dir / "history.jsonl"
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
