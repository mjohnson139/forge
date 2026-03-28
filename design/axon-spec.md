# Axon — Cron Manager NLSpec

## Overview

Axon is the heartbeat of Forge. It is not a custom daemon — it IS the Linux crontab. Every scheduled action in Forge is a crontab entry that invokes Claude Code with a prompt. Axon defines what runs, when, and ensures Forge never goes silent.

---

## Responsibilities

- Maintain the cron registry: the authoritative list of all scheduled jobs
- Run each job by invoking `claude --print "<prompt>"` in the Forge directory
- Ensure each job appends a structured entry to `logs/history.jsonl`
- Detect silence: if no `history.jsonl` entry for >60 minutes, that anomaly is surfaced via Uplink
- Support ad-hoc job creation by operator or Cortex (via registry edit + crontab install)
- Log each job's raw output to `logs/<job>.log`

---

## Interface

**Inputs:**
- `forge/axon/registry.json` — the job registry (read by Cortex to install/update crontab)
- Linux crontab — the actual execution mechanism
- `logs/history.jsonl` — read to check for silence

**Outputs:**
- Claude Code invocations (each job's scheduled command)
- Raw job logs at `logs/<job>.log`
- Structured Lens entries in `logs/history.jsonl`
- Uplink alert if silence is detected (written by the silence-check job)

---

## Behavior

### Registry

The cron registry is `forge/axon/registry.json`. It is an array of job objects:

```
{
  "name": "board-check",
  "schedule": "*/30 * * * *",
  "command": "cd /home/matt/dev/ray && claude --print 'Check the GitHub task board. Log results.' >> logs/board-check.log 2>&1",
  "last_run": "<ISO timestamp or null>",
  "last_outcome": "success | failure | partial | skipped | pending | null"
}
```

Cortex reads `registry.json` and installs the entries into crontab via `crontab -e` or by writing a crontab file. The registry is the source of truth — the crontab reflects it.

### Job Execution

Each job runs as:
```
cd /home/matt/dev/ray && claude --print "<prompt>" >> logs/<job>.log 2>&1
```

After each run, the job (or the Claude Code session it invokes) appends one JSON line to `logs/history.jsonl`. See Lens spec for the entry schema.

### Silence Detection

A dedicated Axon job (e.g., on a 65-minute schedule) reads `logs/history.jsonl` and checks the timestamp of the most recent entry. If the last entry is more than 60 minutes old, it:
1. Writes an alert entry to `logs/history.jsonl` with `outcome: failure`
2. Dispatches a WARN-level Uplink alert: "No Forge activity in >60 minutes."

Silence detection itself being silent is the edge case — the silence-check job must be robust and minimal.

### Failure Handling

If a job produces no output or exits with a non-zero code:
1. The failure is logged to `logs/<job>.log`
2. A Lens entry is appended with `outcome: failure` and the error summary
3. Uplink is notified with an ERROR alert including the job name and last output

### Ad-hoc Job Creation

Operator or Cortex can add a new entry to `registry.json`. Cortex then runs:
```
crontab -l > /tmp/crontab_current && echo "<schedule> <command>" >> /tmp/crontab_current && crontab /tmp/crontab_current
```
Never self-modify crontab without operator approval or explicit instruction from Cortex.

### Current Jobs

| Job | Schedule | Purpose |
|-----|----------|---------|
| `board-check` | Every 30 min | Check GitHub task board, log summary |
| `silence-check` | Every 65 min | Detect if Forge has gone quiet |

---

## Constraints

- **Axon does not manage its own process.** It IS the crontab. There is no Axon daemon.
- **Never self-modify crontab without operator approval.** All crontab changes go through Cortex and require explicit instruction.
- **Each job must produce a Lens entry.** A job that runs and leaves no trace in `history.jsonl` is a silent failure.
- **Silence detection must be independent.** The silence-check job must not depend on other jobs being healthy to run.
- **No overlapping runs.** If a job is still running when its next trigger fires, the second invocation should be skipped (use `flock` or equivalent if needed).

---

## Integration Points

| Component | How Axon uses it |
|-----------|-----------------|
| **Cortex** | Cortex installs/updates crontab from registry; each cron job invokes Cortex |
| **Lens** | Each job appends a structured entry to `logs/history.jsonl`; silence-check reads it |
| **Uplink** | Failure and silence alerts dispatched via Uplink |

---

## Open Questions

- Axon cron registry format decision: `forge/axon/registry.json` (flat JSON) vs structured YAML — flat JSON chosen for now per Pike Rule 3.
- How should `last_run` and `last_outcome` in registry.json be updated — by Cortex after each run, or by the job itself?
- Should silence detection threshold be configurable in `registry.json` or hardcoded?
