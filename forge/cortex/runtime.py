from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any, Callable
import uuid

from forge.axon.lens import append_history_entry
from forge.cortex.brief import assemble_brief, brief_to_context_flags
from forge.uplink.slack import build_failure_message, build_heartbeat_message


Dispatcher = Callable[[Path, str, dict[str, Any]], subprocess.CompletedProcess[str]]
Notifier = Callable[[str], None]


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
    ) -> None:
        self.repo_root = Path(repo_root)
        self.pipeline_service = pipeline_service
        self.memory_store = memory_store
        self.dispatcher = dispatcher or dispatch_attractor
        self.notifier = notifier or (lambda _message: None)

    def heartbeat(self) -> HeartbeatResult:
        tool_statuses = [self.pipeline_service.healthcheck()]
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


def dispatch_attractor(
    repo_root: Path,
    pipeline_name: str,
    brief: dict[str, Any],
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
    return subprocess.run(command, text=True, capture_output=True, check=False)


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
