from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import time
from typing import Any, Callable
import uuid

from forge.axon.lens import append_history_entry
from forge.cortex.brief import assemble_brief, brief_to_context_flags
from forge.uplink.slack import SlackNotifier, build_failure_message, build_heartbeat_message


Dispatcher = Callable[[Path, str, dict[str, Any]], subprocess.CompletedProcess[str]]
Notifier = Callable[[str], None]

_RATE_LIMIT_MARKERS = ("429", "rate limit", "rate_limit", "ratelimit")


class PipelineTimeoutError(Exception):
    """Raised when an Attractor pipeline exceeds its time budget."""


@dataclass(frozen=True)
class HeartbeatResult:
    outcome: str
    summary: str
    next_action: str
    task_id: str | None


class CortexRuntime:
    def __init__(
        self,
        *,
        repo_root: str | Path,
        pipeline_service: Any,
        memory_store: Any,
        dispatcher: Dispatcher | None = None,
        notifier: Notifier | None = None,
        stale_threshold_minutes: int = 60,
        pipeline_timeout_seconds: int = 600,
        retry_delay_seconds: float = 5.0,
        _sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.pipeline_service = pipeline_service
        self.memory_store = memory_store
        self.stale_threshold_minutes = stale_threshold_minutes
        self.pipeline_timeout_seconds = pipeline_timeout_seconds
        self.retry_delay_seconds = retry_delay_seconds
        self._sleep = _sleep if _sleep is not None else time.sleep

        if dispatcher is None:
            _timeout = pipeline_timeout_seconds

            def _dispatch(root: Path, name: str, brief: dict[str, Any]) -> subprocess.CompletedProcess[str]:
                return dispatch_attractor(root, name, brief, timeout=_timeout)

            self.dispatcher: Dispatcher = _dispatch
        else:
            self.dispatcher = dispatcher
        self.notifier = notifier or SlackNotifier(repo_root=self.repo_root).notify

    def heartbeat(self) -> HeartbeatResult:
        self._check_stale_runs()

        health = self.pipeline_service.healthcheck()
        health_status = health.get("status", "healthy") if isinstance(health, dict) else "healthy"
        health_detail = str(health.get("detail", "")) if isinstance(health, dict) else ""

        if health_status not in ("healthy", "ok"):
            if any(m in health_detail.lower() for m in _RATE_LIMIT_MARKERS):
                return self._record_health_failure(
                    error=f"GitHub rate limited: {health_detail}",
                    failure_source="rate_limit",
                    next_action="wait and retry",
                )
            self._sleep(self.retry_delay_seconds)
            health = self.pipeline_service.healthcheck()
            health_status = health.get("status", "healthy") if isinstance(health, dict) else "healthy"
            health_detail = str(health.get("detail", "")) if isinstance(health, dict) else ""
            if health_status not in ("healthy", "ok"):
                return self._record_health_failure(
                    error=f"GitHub health check failed: {health_detail or health_status}",
                    failure_source="github_auth",
                    next_action="check gh auth status",
                )

        tool_statuses = [health]
        tasks = self.pipeline_service.list({"status": ["ready", "feedback"]})

        if not tasks:
            summary = "No actionable tasks found."
            append_history_entry(
                self.repo_root,
                {
                    "timestamp": _now_iso(),
                    "source": "cortex",
                    "job": "heartbeat",
                    "summary": summary,
                    "outcome": "skipped",
                    "next_action": "none",
                    "task_id": None,
                },
            )
            self.notifier(build_heartbeat_message(summary=summary, task=None, run_state="idle", next_action="none"))
            return HeartbeatResult(
                outcome="skipped",
                summary=summary,
                next_action="none",
                task_id=None,
            )

        task = tasks[0]
        run_id = str(uuid.uuid4())
        pipeline_name = self._select_pipeline(task)
        brief = assemble_brief(
            task,
            repo_root=self.repo_root,
            tool_statuses=tool_statuses,
            memory_store=self.memory_store,
            runtime_context={"pipeline": pipeline_name},
        )
        self.memory_store.start_run(
            run_id=run_id,
            task_id=task["id"],
            job_name="cortex-heartbeat",
            pipeline=pipeline_name,
            next_action="dispatch kinetic",
        )
        append_history_entry(
            self.repo_root,
            {
                "timestamp": _now_iso(),
                "source": "cortex",
                "job": "brief-assembly",
                "summary": f"Assembled Brief for {task['id']}.",
                "outcome": "pending",
                "next_action": f"dispatch {pipeline_name}",
                "task_id": task["id"],
            },
        )

        try:
            completed = self.dispatcher(self.repo_root, pipeline_name, brief)
        except (subprocess.TimeoutExpired, PipelineTimeoutError):
            error = f"Pipeline {pipeline_name} timed out after {self.pipeline_timeout_seconds}s"
            self.memory_store.fail_run(run_id, error, next_action="operator review")
            self.memory_store.append_failure_event(
                task_id=task["id"],
                run_id=run_id,
                source="timeout",
                summary=error,
            )
            append_history_entry(
                self.repo_root,
                {
                    "timestamp": _now_iso(),
                    "source": "cortex",
                    "job": "heartbeat",
                    "summary": f"Pipeline timeout for {task['id']}: {error}",
                    "outcome": "timeout",
                    "next_action": "operator review",
                    "task_id": task["id"],
                },
            )
            self.notifier(
                build_failure_message(
                    task=task,
                    run_state="timeout",
                    blocker=error,
                    next_action="operator review",
                )
            )
            self._maybe_add_watchout(task, source="timeout", error=error)
            return HeartbeatResult(
                outcome="timeout",
                summary=error,
                next_action="operator review",
                task_id=task["id"],
            )
        except Exception as exc:
            self.memory_store.fail_run(run_id, str(exc), next_action="operator review")
            self.memory_store.append_failure_event(
                task_id=task["id"],
                run_id=run_id,
                source="cortex",
                summary=str(exc),
            )
            append_history_entry(
                self.repo_root,
                {
                    "timestamp": _now_iso(),
                    "source": "cortex",
                    "job": "heartbeat",
                    "summary": f"Dispatch failed for {task['id']}: {exc}",
                    "outcome": "failure",
                    "next_action": "operator review",
                    "task_id": task["id"],
                },
            )
            self.notifier(
                build_failure_message(
                    task=task,
                    run_state="failed",
                    blocker=str(exc),
                    next_action="operator review",
                )
            )
            self._maybe_add_watchout(task, source="cortex", error=str(exc))
            return HeartbeatResult(
                outcome="failure",
                summary=str(exc),
                next_action="operator review",
                task_id=task["id"],
            )

        outcome = "success" if completed.returncode == 0 else "failure"
        summary = f"Pipeline {pipeline_name} exited with code {completed.returncode}."
        next_action = "review results" if outcome == "success" else "inspect failure"
        if completed.returncode == 0:
            self.memory_store.complete_run(run_id, next_action=next_action)
        else:
            self.memory_store.fail_run(run_id, summary, next_action=next_action)
            self.memory_store.append_failure_event(
                task_id=task["id"],
                run_id=run_id,
                source="kinetic",
                summary=summary,
            )
        self.memory_store.save_task_summary(
            task["id"],
            summary=summary,
            outcome=outcome,
            pipeline=pipeline_name,
        )
        append_history_entry(
            self.repo_root,
            {
                "timestamp": _now_iso(),
                "source": "cortex",
                "job": "heartbeat",
                "summary": summary,
                "outcome": outcome,
                "next_action": next_action,
                "task_id": task["id"],
            },
        )
        self.notifier(
            build_heartbeat_message(
                summary=summary,
                task=task,
                run_state=outcome,
                next_action=next_action,
            )
        )
        return HeartbeatResult(
            outcome=outcome,
            summary=summary,
            next_action=next_action,
            task_id=task["id"],
        )

    def _select_pipeline(self, task: dict[str, Any]) -> str:
        recipe = self.memory_store.find_recipe(task)
        if recipe and recipe.get("pipeline"):
            return str(recipe["pipeline"])
        return "github-task.dot"

    def _check_stale_runs(self) -> None:
        stale_runs = self.memory_store.find_stale_runs(
            threshold_minutes=self.stale_threshold_minutes
        )
        for run in stale_runs:
            if self.memory_store.has_recent_alert(run.run_id, "stale", within_minutes=30):
                continue
            self.memory_store.mark_run_stale(run.run_id)
            self.memory_store.record_alert(run.run_id, "stale")
            task_ref = {"id": run.task_id or run.run_id, "title": f"stale run {run.run_id}"}
            append_history_entry(
                self.repo_root,
                {
                    "timestamp": _now_iso(),
                    "source": "cortex",
                    "job": "stale-check",
                    "summary": f"Run {run.run_id} marked stale (no heartbeat within {self.stale_threshold_minutes}m)",
                    "outcome": "stale",
                    "next_action": "operator review",
                    "task_id": run.task_id,
                },
            )
            self.notifier(
                build_failure_message(
                    task=task_ref,
                    run_state="stale",
                    blocker=f"No heartbeat update within {self.stale_threshold_minutes} minutes",
                    next_action="operator review",
                )
            )

    def _record_health_failure(
        self, *, error: str, failure_source: str, next_action: str
    ) -> "HeartbeatResult":
        self.memory_store.append_failure_event(
            task_id=None,
            run_id=None,
            source=failure_source,
            summary=error,
        )
        append_history_entry(
            self.repo_root,
            {
                "timestamp": _now_iso(),
                "source": "cortex",
                "job": "heartbeat",
                "summary": error,
                "outcome": "failure",
                "next_action": next_action,
                "task_id": None,
            },
        )
        self.notifier(
            build_failure_message(
                task=None,
                run_state="failed",
                blocker=error,
                next_action=next_action,
            )
        )
        self._maybe_add_watchout(None, source=failure_source, error=error)
        return HeartbeatResult(
            outcome="failure",
            summary=error,
            next_action=next_action,
            task_id=None,
        )

    def _maybe_add_watchout(
        self, task: dict[str, Any] | None, *, source: str, error: str
    ) -> None:
        count = self.memory_store.failure_event_count(source)
        if count < 2:
            return
        recipe = self.memory_store.find_recipe(task) if task is not None else None
        if recipe:
            self.memory_store.add_recipe_watchout(
                recipe["name"], f"Repeated {source} failures: {error}"
            )


def dispatch_attractor(
    repo_root: Path,
    pipeline_name: str,
    brief: dict[str, Any],
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    attractor = _find_attractor_executable(repo_root)
    pipeline_path = repo_root / "forge" / "pipelines" / pipeline_name
    command = [
        str(attractor),
        str(pipeline_path),
        "--dir",
        str(repo_root),
        "--logs-dir",
        str(repo_root / "logs"),
    ]
    for pair in brief_to_context_flags(brief):
        command.extend(["--context", pair])
    return subprocess.run(command, text=True, capture_output=True, check=False, timeout=timeout)


def _find_attractor_executable(repo_root: Path) -> Path:
    candidates = [
        repo_root / "tools" / "attractor" / "attractor",
        repo_root.parent / "tools" / "attractor" / "attractor",
        repo_root.parent.parent / "tools" / "attractor" / "attractor",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
