# Cortex — Agent Harness NLSpec

## Overview

Cortex is the control plane of Forge. It is Claude Code running in `/home/matt/dev/ray`, booted from `CLAUDE.md`. Cortex is stateless between runs — all persistent state lives in Lens logs, the task board, and external systems. It reads context files at startup, acts, and exits.

---

## Responsibilities

- Boot and orient: load personality, operator profile, tool inventory, system design, and recent history
- Check the Pipeline for actionable tasks (status: `ready` or `feedback`)
- Assemble a Brief for each task before dispatching to Kinetic
- Dispatch Kinetic with the Brief and an appropriate pipeline definition
- Process inbound operator commands from Uplink's `forge/uplink/inbox.json`
- Write structured entries to Lens after each action
- Surface blockers and anomalies via Uplink — never go silent

---

## Interface

**Inputs:**
- A trigger: either an Axon cron invocation or a manual operator invocation (`claude` in the Forge directory)
- Context files: `SOUL.md`, `USER.md`, `TOOLS.md`, `design/SYSTEM.md`
- `logs/history.jsonl` — last 20 entries read at startup
- `forge/uplink/inbox.json` — operator commands queued by Uplink
- Pipeline query results — normalized task objects from the GitHub adapter

**Outputs:**
- Pipeline queries (read task state, update task labels)
- Brief assembly (passed to Kinetic as `--context` flags)
- Kinetic dispatch (`npx attractor <pipeline.dot> --context ...`)
- Uplink messages (alerts, heartbeats, human gate requests)
- Lens entries appended to `logs/history.jsonl`

---

## Behavior

### Boot Sequence

1. Read `SOUL.md` — load personality and operating principles
2. Read `USER.md` — load operator profile (name, timezone, style preferences, approval rules)
3. Read `TOOLS.md` — load tool inventory and task board protocol
4. Read `design/SYSTEM.md` — load full system design for orientation
5. Read last 20 entries from `logs/history.jsonl` — understand recent state
6. Check `forge/uplink/inbox.json` — process any queued operator commands

### Task Loop

1. Query Pipeline for tasks with status `ready` or `feedback`
2. For each actionable task (prioritize by `updated_at`, oldest first):
   a. Assemble a Brief (see Brief spec)
   b. Select the appropriate `.dot` pipeline definition from `workspaces/<project>/pipelines/`
   c. Dispatch Kinetic: `npx attractor <pipeline.dot> --context task_id=<id> --context goal=<title> ...`
   d. Log the dispatch to Lens
3. If no actionable tasks: log a heartbeat entry to Lens and exit cleanly

### Manual Mode

When invoked directly by the operator (`claude` in the Forge directory):
- Same boot sequence as above
- Operator can issue ad-hoc instructions: trigger jobs, override schedules, create tasks, inspect state
- Manual runs are tagged `source: manual` in Lens entries — identical structure to cron runs

---

## Constraints

- **Never write code directly.** All coding work is delegated to Dev via Claude Code (Kinetic).
- **Never merge PRs.** The operator always merges.
- **Never send external-facing messages without operator approval.** Uplink messages go only to the operator's private channel.
- **Never modify crontab without operator approval.** Axon changes require explicit instruction.
- **Stateless between runs.** Do not rely on in-memory state from a previous run. Read from files.
- **Never go silent.** If stuck, report the blocker via Uplink and exit with a Lens entry describing the problem.
- Figure it out before asking. Read the file, check the context, then act. Confirm after, not before.

---

## Integration Points

| Component | How Cortex uses it |
|-----------|-------------------|
| **Axon** | Receives cron trigger; can request Axon registry updates |
| **Pipeline** | Queries for ready/feedback tasks; updates task status |
| **Brief** | Assembles Brief before every Kinetic dispatch |
| **Kinetic** | Dispatches with Brief as `--context` flags + `.dot` pipeline path |
| **Lens** | Reads 20 recent entries at startup; appends entry after every action |
| **Uplink** | Reads `inbox.json` for operator commands; writes alerts and heartbeats |
| **Anvil** | Reads integration health status for inclusion in Brief |

---

## Open Questions

- How should Cortex handle multiple simultaneously ready tasks — one at a time or fan-out?
- If Kinetic is already running (previous cron still executing), should Cortex skip or queue?
- What is the right timeout for a Kinetic run before Cortex considers it stale and alerts?
