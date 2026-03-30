# Memory — Persistent State and Recipes NLSpec

## Overview

Memory is the writable state layer for Forge. It complements Lens: Lens is the append-only history of what happened, while Memory holds the current operational picture of what is running, what failed, what was learned, and which recipe is likely to work next.

For the MVP, Memory is file-backed and local. Text files are the right tradeoff for now. If Forge later proves it needs stronger querying, concurrency, or retention guarantees, Memory can be upgraded behind the same logical interface.

---

## Responsibilities

- Track active and recent runs across Axon, Cortex, and Kinetic
- Store task-local summaries, blockers, and recent decisions
- Record failure and retry metadata for recovery logic
- Store reusable recipes for common knowledge-work patterns
- Provide Cortex with mutable context that should not live in append-only Lens history

---

## Interface

**Storage layout:**

- `forge/memory/runs.json` — active and recent run records
- `forge/memory/tasks/<task_id>.json` — task-local state and summaries
- `forge/memory/recipes.json` — reusable task recipes
- `forge/memory/failures.jsonl` — append-only failure events

**Run record schema:**

```
{
  "run_id": "<unique id>",
  "task_id": "<source-prefixed task id or null>",
  "job_name": "<axon job or manual trigger>",
  "pipeline": "<pipeline name or null>",
  "state": "<pending | running | blocked | failed | completed | stale>",
  "attempt": 1,
  "started_at": "<ISO 8601>",
  "updated_at": "<ISO 8601>",
  "last_heartbeat_at": "<ISO 8601>",
  "last_error": "<summary or null>",
  "next_action": "<summary or none>"
}
```

**Task memory schema:**

```
{
  "task_id": "<source-prefixed task id>",
  "last_summary": "<summary or null>",
  "last_outcome": "<success | failure | partial | skipped | pending | null>",
  "last_pipeline": "<pipeline name or null>",
  "open_blockers": ["<blocker>"],
  "recent_decisions": ["<decision>"],
  "recipe_hint": "<recipe name or null>",
  "updated_at": "<ISO 8601>"
}
```

**Recipe schema:**

```
{
  "name": "<recipe name>",
  "match_rules": {
    "source": "<github | linear | ... | null>",
    "labels": ["<label>"],
    "keywords": ["<keyword>"]
  },
  "pipeline": "<pipeline name>",
  "brief_context": {
    "<key>": "<value>"
  },
  "success_patterns": ["<signal>"],
  "watchouts": ["<risk>"]
}
```

---

## Behavior

### Run tracking

1. Cortex creates or updates a run record before dispatching Kinetic
2. The run moves through states: `pending -> running -> completed|failed|blocked|stale`
3. Axon and Cortex use run state to detect overlapping work and stale execution
4. Uplink summaries can include current run state without reconstructing it from Lens

### Task-local memory

1. After each significant task outcome, Cortex updates the task memory file
2. The file stores the most useful summary, blockers, pipeline used, and recent decisions
3. On the next run for the same task, Cortex uses this as part of Brief assembly

### Recipes

1. Recipes are explicit, operator-readable artifacts
2. Cortex matches recipes during Brief assembly using task source, labels, or keywords
3. A recipe may suggest a preferred pipeline, added brief context, success patterns, and watchouts
4. Recipes are hints, not hard requirements; Cortex can override them if the current task differs

### Failure handling

1. Every meaningful failure is appended to `failures.jsonl`
2. The active run record is updated with state, last error, and next action
3. Cortex can suppress duplicate alerts by checking whether the same run is already marked `blocked` or `stale`

---

## Constraints

- **Memory is writable; Lens is immutable.** Do not rewrite `history.jsonl` to represent current state.
- **Memory is local-first.** Start with files; do not introduce a service or database until proven necessary.
- **Memory stores summaries, not transcripts.** Keep it inspectable and compact.
- **Recipes are explicit.** Do not hide critical behavior in opaque heuristics.
- **Memory must degrade safely.** If a memory file is missing or corrupt, Forge should rebuild or continue with reduced context rather than crash silently.

---

## Integration Points

| Component | How it uses Memory |
|-----------|--------------------|
| **Cortex** | Primary reader/writer; run state, task memory, recipes |
| **Brief** | Consumes task memory, active run state, and recipe hints |
| **Axon** | Reads run state for stale detection and heartbeat summaries |
| **Lens** | Complements Memory with append-only history |
| **Uplink** | Uses current run state and failures in alerts and heartbeats |

---

## Open Questions

- When should old run records be compacted or archived?
- Should recipes be entirely manual, or can Cortex propose recipe updates for operator approval?
- What is the threshold for replacing flat files with a heavier backend?
