# Lens — Logging and Observability NLSpec

## Overview

Lens is how Forge sees itself. It is the logging and observability layer — three log horizons that together tell any component (or operator) what Forge is doing, what it has done, and what it plans to do next. Lens is append-only. History is never deleted, never modified.

---

## Responsibilities

- Receive structured log entries from all Forge components (append-only, no central writer)
- Provide Cortex with recent history at startup for orientation
- Provide Axon's silence-detection job with a recency check
- Maintain a human-readable planning view (`logs/plan.md`)
- Manage raw log file rotation for `logs/<job>.log` files

---

## Interface

**Write interface:** Any component appends a JSON line to `logs/history.jsonl` by writing directly to the file. No central writer, no locking — append-only writes to a single file are safe on Linux.

**Read interface:**
- Cortex reads last 20 entries at startup: `tail -n 20 logs/history.jsonl | jq`
- Axon silence-check reads the last entry's timestamp: `tail -n 1 logs/history.jsonl | jq .timestamp`
- Operator reads `logs/plan.md` for a human-friendly planning view

---

## Behavior

### Three log horizons

| Horizon | File | What it contains |
|---------|------|-----------------|
| Current run | `logs/<job>.log` | Raw stdout/stderr from the Claude Code session for that job |
| Run history | `logs/history.jsonl` | One JSON line per completed run or significant event |
| Planning view | `logs/plan.md` | Human-readable: current task, next 3 queued, last 5 completed |

### `history.jsonl` entry schema

Each entry is a single JSON line (no pretty-printing):

```
{
  "timestamp":   "<ISO 8601, UTC>",
  "source":      "<axon-cron | manual | kinetic | uplink | cortex>",
  "job":         "<job name or task_id-node_name>",
  "summary":     "<1-2 sentence plain English summary of what happened>",
  "outcome":     "<success | failure | partial | skipped | pending>",
  "next_action": "<what happens next, or 'none'>",
  "task_id":     "<source-prefixed task ID, or null if not task-specific>"
}
```

**`source` values:**

| Value | Written by |
|-------|-----------|
| `axon-cron` | A scheduled Axon cron job |
| `manual` | An operator-invoked manual session |
| `kinetic` | A Kinetic pipeline node |
| `uplink` | An inbound operator command processed by Cortex |
| `cortex` | Cortex itself (Brief assembly, startup orientation, anomaly detection) |

**`outcome` values:**

| Value | Meaning |
|-------|---------|
| `success` | Completed without errors |
| `failure` | Errored or produced no useful output |
| `partial` | Completed with warnings or incomplete results |
| `skipped` | Intentionally bypassed (e.g., no ready tasks) |
| `pending` | Started but not yet complete (e.g., Brief assembled, Kinetic running) |

### Cortex startup read

On every startup, Cortex runs:
```
tail -n 20 logs/history.jsonl
```
It reads these 20 entries to orient itself: understand what was last worked on, detect any in-progress or failed tasks, and avoid duplicating recent work.

### Silence detection

The silence-check Axon job reads:
```
tail -n 1 logs/history.jsonl | jq .timestamp
```
If the timestamp is more than 60 minutes ago, the job writes a failure entry to `history.jsonl` and dispatches a WARN alert via Uplink. The silence-check job itself must write to `history.jsonl` on every run (even if no silence is detected), so its own absence can be detected.

### `logs/plan.md` — human-readable planning view

Updated by Cortex after each task loop. Format:

```markdown
# Forge Plan — <ISO date>

## In Progress
- [task_id] <title> (started <timestamp>)

## Next Up
- [task_id] <title>
- [task_id] <title>
- [task_id] <title>

## Recently Completed
- [task_id] <title> — <outcome> (<timestamp>)
- [task_id] <title> — <outcome> (<timestamp>)
- [task_id] <title> — <outcome> (<timestamp>)
- [task_id] <title> — <outcome> (<timestamp>)
- [task_id] <title> — <outcome> (<timestamp>)
```

### Log rotation

- `logs/<job>.log` — rotated when size exceeds 1MB. Keep last 3 rotations (`<job>.log.1`, `<job>.log.2`, `<job>.log.3`). Managed by Cortex or a dedicated Axon job.
- `logs/history.jsonl` — **never rotated**. It is the permanent record of Forge's activity. No deletion, no archiving.
- `logs/plan.md` — overwritten on each Cortex task loop. Not versioned.

---

## Constraints

- **Lens is append-only for `history.jsonl`.** Never delete entries. Never modify past entries. The record is immutable.
- **Every component that takes a significant action must write to Lens.** Cortex, Kinetic, and Axon all write entries. Silence is a bug.
- **No central Lens writer process.** All components write directly via file append. This keeps Lens simple and failure-independent.
- **Entries must be valid JSON lines.** Invalid JSON in `history.jsonl` will break Cortex's startup read. Validate before appending.
- **`summary` must be human-readable.** An operator skimming `history.jsonl` should understand what happened without decoding keys.

---

## Integration Points

| Component | How it uses Lens |
|-----------|-----------------|
| **Cortex** | Reads last 20 entries at startup; writes entries after every significant action |
| **Axon** | Each cron job writes an entry; silence-check reads last entry timestamp |
| **Kinetic** | Appends entry after each completed pipeline node |
| **Uplink** | Reads recent history for heartbeat summary content |
| **Brief** | Brief assembly reads Lens history to populate the `history` field |

---

## Open Questions

- Lens log retention policy: `history.jsonl` grows indefinitely — when does it become a problem, and what is the plan then? (CXDB ingest via Attractor may help here.)
- Should `logs/plan.md` be generated from `history.jsonl` + Pipeline query, or maintained as a separate writable file?
- Consider a `lens query` CLI helper for Cortex to do structured lookups (e.g., "last 5 entries for task_id gh-42") without raw `jq` pipelines.
