# Forge MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a working Forge MVP that can wake up on a schedule, discover actionable software-development tasks, assemble execution context, run an Attractor pipeline, log progress and failures, notify the operator, and preserve enough state to recover from failures and accelerate repeated work.

**MVP Definition:** A single-machine Forge runtime in `/home/matt/dev/ray` that supports:
- one real scheduler path (`Axon`)
- one real task source (`Pipeline` GitHub adapter)
- one real execution engine (`Kinetic` via Attractor)
- one real observability layer (`Lens`)
- one real operator channel (`Uplink` via Slack)
- one new persistent state layer (`Memory`) for job/run state and reusable recipes

**Architecture:** Keep the system flat-file first and process-oriented. Axon triggers Cortex. Cortex queries Pipeline, reads Lens + Memory, assembles a Brief, dispatches Kinetic through Attractor, writes state transitions to Lens and Memory, and sends alerts/heartbeats through Uplink. Memory is a small local file-backed layer, not a database server.

**Tech Stack:** Python 3 stdlib for Axon/Cortex/Pipeline/Uplink/Memory glue, TypeScript Attractor runtime for Kinetic, JSON/JSONL/Markdown flat files, `gh` CLI for GitHub, Slack MCP for operator messaging, `unittest` + Attractor integration tests.

---

## MVP Scope

### In scope

- Axon-managed scheduled runs
- Cortex boot + task loop
- GitHub-backed Pipeline adapter
- Brief assembly from task + Lens + Memory + operator/tool state
- Kinetic dispatch into one real Attractor pipeline
- Lens logging for each meaningful state transition
- Uplink Slack heartbeat/failure notifications
- Memory for run tracking, failure recovery, and task recipes

### Out of scope

- Multiple task backends beyond GitHub
- Multi-host execution
- Autonomous PR merge
- Advanced memory retrieval or embeddings
- General-purpose daemonization beyond cron + local files

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `forge/cortex/__init__.py` | Cortex package marker |
| Create | `forge/cortex/cli.py` | Entry point for heartbeat/manual runs |
| Create | `forge/cortex/runtime.py` | Boot sequence, task loop, dispatch orchestration |
| Create | `forge/cortex/brief.py` | Brief assembly helpers |
| Create | `forge/memory/.gitkeep` | Track memory directory |
| Create | `forge/memory/runs.json` | Run-state store |
| Create | `forge/memory/recipes.json` | Recipe store |
| Create | `forge/memory/tasks/.gitkeep` | Track task memory dir |
| Create | `forge/memory/failures.jsonl` | Failure event log |
| Create | `forge/pipeline/__init__.py` | Pipeline package marker |
| Create | `forge/pipeline/github_adapter.py` | GitHub Issues adapter via `gh` |
| Create | `forge/pipeline/service.py` | Normalized task list/update surface |
| Create | `forge/uplink/slack.py` | Slack heartbeat/failure message helpers |
| Create | `forge/pipelines/github-task.dot` | First real Kinetic pipeline |
| Create | `forge/pipelines/github-task-qa.dot` | Self-verifying QA pipeline |
| Create | `tests/cortex/test_memory.py` | Memory tests |
| Create | `tests/cortex/test_brief.py` | Brief assembly tests |
| Create | `tests/pipeline/test_github_adapter.py` | Pipeline adapter tests |
| Create | `tests/cortex/test_runtime.py` | Cortex task loop tests |
| Create | `tests/integration/test_mvp_flow.py` | End-to-end MVP integration |
| Create | `MVP-HANDOFF.md` | Running-state and merge handoff |

---

## Task 1: Stabilize the Runtime Baseline

- [ ] Start from merged `main` with Axon and Lens root-repo changes included
- [ ] Confirm the baseline runtime directories exist:
  - `logs/`
  - `forge/uplink/inbox.json`
  - `forge/axon/registry.json`
  - `forge/memory/`
- [ ] Confirm Axon CLI and tests pass from the main repo working tree
- [ ] Write `MVP-HANDOFF.md` at session start

**Exit criteria:** Axon baseline is verified and ready to extend.

---

## Task 2: Implement Memory

- [ ] Write failing tests for run records, task-local state, failure logging, and recipe loading
- [ ] Implement writable Memory helpers and seed `recipes.json`
- [ ] Keep Memory file-backed and human-readable
- [ ] Commit Memory as the mutable state surface for Cortex

**Exit criteria:** Memory can track active runs, failures, and recipe hints without external services.

---

## Task 3: Implement Pipeline v1

- [ ] Write failing tests for normalized GitHub task listing and updates
- [ ] Implement GitHub adapter using `gh`
- [ ] Implement Pipeline service with canonical task objects
- [ ] Add a health-check path for Brief assembly

**Exit criteria:** Cortex can list actionable GitHub tasks in normalized form.

---

## Task 4: Implement Brief Assembly

- [ ] Write failing tests for Brief assembly
- [ ] Build Brief from:
  - normalized task
  - Lens history
  - Memory
  - operator context
  - tool health
  - Uplink overrides
- [ ] Log the Brief to Lens before dispatch

**Exit criteria:** Cortex can produce a complete Brief for one real task.

---

## Task 5: Implement Cortex Runtime Loop

- [ ] Write failing tests for:
  - boot with no tasks
  - boot with one ready task
  - stale active run detection
  - failure path that writes Lens + Memory + Uplink signals
- [ ] Implement runtime + CLI heartbeat entrypoint
- [ ] Start sequentially: one task at a time

**Exit criteria:** `python3 -m forge.cortex.cli heartbeat` works against a stub task source.

---

## Task 6: Wire Kinetic to a Real Forge Pipeline

- [ ] Create `forge/pipelines/github-task.dot`
- [ ] Create `forge/pipelines/github-task-qa.dot`
- [ ] Ensure pipeline progress lands in `logs/history.jsonl`
- [ ] Use Attractor as-is rather than replacing it

**Exit criteria:** Cortex can dispatch one real Attractor pipeline using a generated Brief.

---

## Task 7: Uplink and Scheduling

- [ ] Implement Slack heartbeat/failure payloads
- [ ] Add `cortex-heartbeat` to Axon registry
- [ ] Keep crontab apply operator-gated
- [ ] Ensure every scheduled run leaves a Lens trace

**Exit criteria:** A local machine can run the MVP unattended on a schedule with operator visibility.

---

## Task 8: End-to-End Verification

- [ ] Add integration coverage for Axon -> Cortex -> Pipeline -> Brief -> Kinetic -> Lens -> Memory -> Uplink
- [ ] Run the QA pipeline end to end
- [ ] Update `MVP-HANDOFF.md` with start/stop/inspect guidance
- [ ] Produce merge-readiness notes

**Exit criteria:** One complete local flow works and is documented.

---

## Success Criteria

- a cron-triggerable command exists that starts Cortex
- Cortex can pull one actionable GitHub task
- Cortex assembles a Brief using Lens + Memory + operator/tool state
- Cortex dispatches a real Attractor pipeline
- pipeline progress is visible in `logs/history.jsonl`
- run state is visible in `forge/memory/`
- failures are recorded and surfaced
- the operator receives a useful Slack heartbeat or failure summary
