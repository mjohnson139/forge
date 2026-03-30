from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


ACTIVE_RUN_STATES = {"pending", "running", "blocked", "failed", "stale"}
TERMINAL_RUN_STATES = {"completed", "skipped"}


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    task_id: str | None
    job_name: str
    pipeline: str | None
    state: str
    attempt: int
    started_at: str
    updated_at: str
    last_heartbeat_at: str
    last_error: str | None
    next_action: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RunRecord":
        return cls(
            run_id=str(payload["run_id"]),
            task_id=_optional_str(payload.get("task_id")),
            job_name=str(payload["job_name"]),
            pipeline=_optional_str(payload.get("pipeline")),
            state=str(payload["state"]),
            attempt=int(payload.get("attempt", 1)),
            started_at=str(payload["started_at"]),
            updated_at=str(payload["updated_at"]),
            last_heartbeat_at=str(payload["last_heartbeat_at"]),
            last_error=_optional_str(payload.get("last_error")),
            next_action=str(payload.get("next_action", "none")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskMemory:
    task_id: str
    last_summary: str | None = None
    last_outcome: str | None = None
    last_pipeline: str | None = None
    open_blockers: list[str] = field(default_factory=list)
    recent_decisions: list[str] = field(default_factory=list)
    recipe_hint: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "TaskMemory":
        return cls(
            task_id=str(payload["task_id"]),
            last_summary=_optional_str(payload.get("last_summary")),
            last_outcome=_optional_str(payload.get("last_outcome")),
            last_pipeline=_optional_str(payload.get("last_pipeline")),
            open_blockers=list(payload.get("open_blockers", [])),
            recent_decisions=list(payload.get("recent_decisions", [])),
            recipe_hint=_optional_str(payload.get("recipe_hint")),
            updated_at=_optional_str(payload.get("updated_at")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Recipe:
    name: str
    match_rules: Mapping[str, Any]
    pipeline: str
    brief_context: Mapping[str, Any] = field(default_factory=dict)
    success_patterns: list[str] = field(default_factory=list)
    watchouts: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "Recipe":
        return cls(
            name=str(payload["name"]),
            match_rules=dict(payload.get("match_rules", {})),
            pipeline=str(payload["pipeline"]),
            brief_context=dict(payload.get("brief_context", {})),
            success_patterns=list(payload.get("success_patterns", [])),
            watchouts=list(payload.get("watchouts", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def matches(
        self,
        *,
        source: str | None = None,
        labels: Sequence[str] = (),
        title: str = "",
        body: str = "",
    ) -> bool:
        rule_source = _optional_str(self.match_rules.get("source"))
        if rule_source is not None and source != rule_source:
            return False

        rule_labels = list(self.match_rules.get("labels", []))
        if rule_labels and not set(rule_labels).issubset(set(labels)):
            return False

        keywords = [str(keyword).lower() for keyword in self.match_rules.get("keywords", [])]
        haystack = f"{title}\n{body}".lower()
        return all(keyword in haystack for keyword in keywords)


class MemoryStore:
    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)
        self.memory_dir = self.repo_root / "forge" / "memory"
        self.tasks_dir = self.memory_dir / "tasks"
        self.runs_path = self.memory_dir / "runs.json"
        self.recipes_path = self.memory_dir / "recipes.json"
        self.failures_path = self.memory_dir / "failures.jsonl"

    def ensure_layout(self) -> None:
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        _ensure_json_file(self.runs_path, [])
        _ensure_json_file(self.recipes_path, [])
        self.failures_path.parent.mkdir(parents=True, exist_ok=True)
        self.failures_path.touch(exist_ok=True)

    def load_runs(self) -> list[RunRecord]:
        payload = _load_json(self.runs_path, default=[])
        if not isinstance(payload, list):
            raise ValueError("runs.json must contain a JSON array")
        return [RunRecord.from_mapping(item) for item in payload]

    def write_runs(self, runs: Sequence[RunRecord]) -> None:
        self.runs_path.write_text(
            json.dumps([run.to_dict() for run in runs], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def upsert_run(self, run: RunRecord) -> None:
        runs = self.load_runs()
        updated = False
        new_runs: list[RunRecord] = []
        for existing in runs:
            if existing.run_id == run.run_id:
                new_runs.append(run)
                updated = True
            else:
                new_runs.append(existing)
        if not updated:
            new_runs.append(run)
        self.write_runs(new_runs)

    def get_run(self, run_id: str) -> RunRecord | None:
        for run in self.load_runs():
            if run.run_id == run_id:
                return run
        return None

    def latest_run_for_task(self, task_id: str) -> RunRecord | None:
        matches = [run for run in self.load_runs() if run.task_id == task_id]
        if not matches:
            return None
        return sorted(matches, key=lambda run: run.updated_at)[-1]

    def load_task_memory(self, task_id: str) -> dict[str, Any] | None:
        path = self._task_memory_path(task_id)
        if not path.exists():
            return None
        payload = _load_json(path, default={})
        if not isinstance(payload, dict):
            raise ValueError(f"task memory file for {task_id} must contain an object")
        return payload

    def upsert_task_memory(self, memory: TaskMemory) -> None:
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self._task_memory_path(memory.task_id).write_text(
            json.dumps(memory.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def append_failure(self, event: Mapping[str, Any] | dict[str, Any]) -> None:
        self.failures_path.parent.mkdir(parents=True, exist_ok=True)
        with self.failures_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(event), sort_keys=True) + "\n")

    def append_failure_event(self, **kwargs: Any) -> None:
        self.append_failure(kwargs)

    def load_recipes(self) -> list[Recipe]:
        payload = _load_json(self.recipes_path, default=[])
        if not isinstance(payload, list):
            raise ValueError("recipes.json must contain a JSON array")
        return [Recipe.from_mapping(item) for item in payload]

    def write_recipes(self, recipes: Sequence[Recipe]) -> None:
        self.recipes_path.write_text(
            json.dumps([recipe.to_dict() for recipe in recipes], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def find_recipe(
        self,
        task: Mapping[str, Any] | None = None,
        *,
        source: str | None = None,
        labels: Sequence[str] = (),
        title: str = "",
        body: str = "",
    ) -> dict[str, Any] | None:
        if task is not None:
            source = _optional_str(task.get("source")) if source is None else source
            labels = list(task.get("labels", labels))
            title = str(task.get("title", title))
            body = str(task.get("body", body))
        for recipe in self.load_recipes():
            if recipe.matches(source=source, labels=labels, title=title, body=body):
                return recipe.to_dict()
        return None

    def brief_context_for_task(
        self,
        *,
        task_id: str,
        source: str | None = None,
        title: str = "",
        body: str = "",
        labels: Sequence[str] = (),
    ) -> dict[str, Any]:
        task_memory = self.load_task_memory(task_id)
        active_run = self.find_active_run(task_id)
        recipe = self.find_recipe(source=source, labels=labels, title=title, body=body)
        return {
            "task_memory": task_memory,
            "active_run": active_run,
            "recipe": recipe,
        }

    def find_active_run(self, task_id: str) -> dict[str, Any] | None:
        run = self.latest_run_for_task(task_id)
        return run.to_dict() if run else None

    def start_run(self, **kwargs: Any) -> None:
        now = kwargs.get("now") or kwargs.get("started_at") or kwargs.get("updated_at")
        timestamp = str(now) if now is not None else _utc_now()
        self.upsert_run(
            RunRecord(
                run_id=str(kwargs["run_id"]),
                task_id=_optional_str(kwargs.get("task_id")),
                job_name=str(kwargs.get("job_name", "cortex-heartbeat")),
                pipeline=_optional_str(kwargs.get("pipeline")),
                state="running",
                attempt=int(kwargs.get("attempt", 1)),
                started_at=str(kwargs.get("started_at", timestamp)),
                updated_at=str(kwargs.get("updated_at", timestamp)),
                last_heartbeat_at=str(kwargs.get("last_heartbeat_at", timestamp)),
                last_error=_optional_str(kwargs.get("last_error")),
                next_action=str(kwargs.get("next_action", "dispatch kinetic")),
            )
        )

    def complete_run(self, run_id: str, *, next_action: str) -> None:
        run = self.get_run(run_id)
        if run is None:
            return
        self.upsert_run(
            RunRecord(
                run_id=run.run_id,
                task_id=run.task_id,
                job_name=run.job_name,
                pipeline=run.pipeline,
                state="completed",
                attempt=run.attempt,
                started_at=run.started_at,
                updated_at=_utc_now(),
                last_heartbeat_at=_utc_now(),
                last_error=run.last_error,
                next_action=next_action,
            )
        )

    def fail_run(self, run_id: str, error: str, *, next_action: str) -> None:
        run = self.get_run(run_id)
        if run is None:
            return
        self.upsert_run(
            RunRecord(
                run_id=run.run_id,
                task_id=run.task_id,
                job_name=run.job_name,
                pipeline=run.pipeline,
                state="failed",
                attempt=run.attempt,
                started_at=run.started_at,
                updated_at=_utc_now(),
                last_heartbeat_at=_utc_now(),
                last_error=error,
                next_action=next_action,
            )
        )

    def save_task_summary(self, task_id: str, *, summary: str, outcome: str, pipeline: str) -> None:
        existing = self.load_task_memory(task_id) or {"task_id": task_id}
        merged = TaskMemory(
            task_id=task_id,
            last_summary=summary,
            last_outcome=outcome,
            last_pipeline=pipeline,
            open_blockers=list(existing.get("open_blockers", [])),
            recent_decisions=list(existing.get("recent_decisions", [])),
            recipe_hint=existing.get("recipe_hint"),
            updated_at=_utc_now(),
        )
        self.upsert_task_memory(merged)

    def _task_memory_path(self, task_id: str) -> Path:
        return self.tasks_dir / f"{_slugify(task_id)}.json"


def _ensure_json_file(path: Path, default: Any) -> None:
    if path.exists():
        return
    path.write_text(json.dumps(default, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _slugify(value: str) -> str:
    chars = [ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value]
    slug = "".join(chars).strip("_")
    return slug or "task"


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
