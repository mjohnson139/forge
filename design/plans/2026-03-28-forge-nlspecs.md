# Forge NLSpecs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write one NLSpec file per Forge component in `design/`, following the NLSpec pattern from `mjohnson139/attractor` — human-readable, agent-implementable, no code.

**Architecture:** Each spec is a standalone markdown file that fully describes one component's behavior, interface, inputs, outputs, and constraints. Together they form the complete design of Forge. The source of truth for all content is `design/SYSTEM.md`. No implementation code is written — these are specs only.

**Tech Stack:** Markdown, NLSpec pattern (see `mjohnson139/attractor` for reference style)

---

## NLSpec Pattern Reference

Each spec file follows this structure:
1. **Overview** — what this component is and why it exists (2-3 sentences)
2. **Responsibilities** — bulleted list of what it does
3. **Interface** — inputs it accepts, outputs it produces
4. **Behavior** — how it works, step by step, in plain English
5. **Constraints** — what it must never do, edge cases, failure modes
6. **Integration points** — which other Forge components it talks to and how
7. **Open questions** — unresolved design decisions for this component

---

## Files to Create

- `design/cortex-spec.md` — agent harness, boot sequence, personality loading
- `design/axon-spec.md` — cron manager, registry, job definitions
- `design/pipeline-spec.md` — task aggregator, adapters, normalization
- `design/brief-spec.md` — context packet data structure, assembly process
- `design/kinetic-spec.md` — Attractor integration, DOT pipelines, Brief intake
- `design/lens-spec.md` — logging, history.jsonl, structured entries, self-reading
- `design/uplink-spec.md` — Slack via Claude.ai MCP, heartbeat push, command receive
- `design/anvil-spec.md` — MCP tools inventory, credential health checks, auth flows

---

## Task 1: cortex-spec.md — Agent Harness

**Files:**
- Create: `design/cortex-spec.md`

- [ ] **Step 1: Write the spec**

Content must cover:
- Cortex is Claude Code running in `/home/matt/dev/ray` with `CLAUDE.md` as entrypoint
- Boot sequence: reads SOUL.md → USER.md → TOOLS.md → design/SYSTEM.md → recent Lens history
- Personality is loaded from SOUL.md — swappable without changing system behavior
- Core behaviors that are NOT persona (bias for action, never go silent, figure it out before asking) live in CLAUDE.md
- Stateless between runs — all state lives in Lens, Pipeline, and external systems
- On startup in manual mode: reads last 20 entries from `logs/history.jsonl` to orient itself
- Interface: receives a trigger (cron or manual), produces actions (Pipeline queries, Brief assembly, Kinetic dispatch, Uplink messages)
- Constraints: never writes code directly, never merges PRs, never sends external messages without operator approval

- [ ] **Step 2: Review against SYSTEM.md section 1 and 5**

Check that every point in SYSTEM.md §1 (Cortex) and §5 (Personality) is covered. Add anything missing.

- [ ] **Step 3: Commit**

```bash
git add design/cortex-spec.md
git commit -m "spec: add Cortex NLSpec"
```

---

## Task 2: axon-spec.md — Cron Manager

**Files:**
- Create: `design/axon-spec.md`

- [ ] **Step 1: Write the spec**

Content must cover:
- Axon is the Linux crontab — no custom cron daemon, just crontab entries
- Cron registry: `forge/axon/registry.json` — array of job objects: `{name, schedule, command, last_run, last_outcome}`
- Each job runs a claude invocation: `cd /home/matt/dev/ray && claude --print "<prompt>" >> logs/<job>.log 2>&1`
- On each run, job appends a structured entry to `logs/history.jsonl`
- Silence detection: if no entry in `logs/history.jsonl` for >60 minutes, that is itself an anomaly to surface via Uplink
- Ad-hoc job creation: operator can add entries to registry.json and Cortex installs them via `crontab`
- Current jobs: board-check every 30 minutes
- Failure handling: if a job produces no output or errors, Uplink is notified
- Constraints: Axon does not manage its own process — it IS the crontab. Never self-modify without operator approval.

- [ ] **Step 2: Review against SYSTEM.md section 2**

Check all points covered. Confirm silence detection is specified.

- [ ] **Step 3: Commit**

```bash
git add design/axon-spec.md
git commit -m "spec: add Axon NLSpec"
```

---

## Task 3: pipeline-spec.md — Task Aggregator

**Files:**
- Create: `design/pipeline-spec.md`

- [ ] **Step 1: Write the spec**

Content must cover:
- Pipeline is a pluggable fan-in — multiple task sources collapse into one normalized work stream
- Normalized task format (the canonical task object): `{id, source, title, body, labels, status, updated_at, url}`
- Status vocabulary: `ready | in-progress | in-review | feedback | accepted | idea`
- Adapter interface: any adapter must implement `list() → Task[]` and `update(id, changes) → void`
- Adapter v1: GitHub Issues via `gh` CLI — `mjohnson139/ray-groove-issues`, label-based workflow (see TOOLS.md)
- Adapter stubs (future): Linear, Notion, Slack threads, direct operator input
- Pipeline does not store state — it queries on demand
- Cortex calls Pipeline to check for actionable tasks (status: ready or feedback)
- Constraints: Pipeline never modifies tasks without explicit instruction from Cortex. Read-mostly.

- [ ] **Step 2: Review against SYSTEM.md Pipeline entry and TOOLS.md**

Confirm normalized task format covers everything TOOLS.md needs.

- [ ] **Step 3: Commit**

```bash
git add design/pipeline-spec.md
git commit -m "spec: add Pipeline NLSpec"
```

---

## Task 4: brief-spec.md — Context Packet

**Files:**
- Create: `design/brief-spec.md`

- [ ] **Step 1: Write the spec**

Content must cover:
- A Brief is the full intelligence packet assembled by Cortex before handing off to Kinetic
- Brief is the "smart object" per Pike Rule 5 — everything else stays stupid
- Brief schema:
  - `task` — the normalized task from Pipeline (id, title, body, labels, url)
  - `history` — last N relevant Lens entries for this task or project
  - `operator` — from USER.md: name, timezone, style preferences, approval rules
  - `tools` — available Anvil integrations and their current health status
  - `context` — any runtime overrides from Uplink or operator (e.g. "focus on X", "skip Y")
  - `assembled_at` — timestamp
- Assembly process: Cortex reads task from Pipeline → fetches relevant Lens history → loads USER.md → checks Anvil health → merges any active overrides → produces Brief
- Brief is passed to Kinetic as `--context` flags (key=value pairs matching Attractor's CLI interface)
- Brief is also logged to Lens for observability
- Constraints: Brief is immutable once assembled. If context changes mid-run, a new Brief is assembled for the next run.

- [ ] **Step 2: Review — does every Kinetic input come from the Brief?**

Kinetic should need nothing outside the Brief to do its job. Verify this is true.

- [ ] **Step 3: Commit**

```bash
git add design/brief-spec.md
git commit -m "spec: add Brief NLSpec"
```

---

## Task 5: kinetic-spec.md — Task Engine

**Files:**
- Create: `design/kinetic-spec.md`

- [ ] **Step 1: Write the spec**

Content must cover:
- Kinetic IS Attractor (`mjohnson139/attractor`) — not reimplemented, wired in
- Kinetic receives a Brief and a pipeline definition (`.dot` file) and executes the graph
- Invocation: `npx attractor <pipeline.dot> --context task_id=<id> --context goal=<title> ...` (Brief fields become `--context` flags)
- Pipeline definitions live in `workspaces/<project>/pipelines/*.dot`
- Standard pipeline types: `coding-task.dot`, `research-task.dot`, `review-task.dot`
- Node handler types available: `codergen` (Claude Code), `tool` (shell/CLI), `human` (Uplink gate), `llm` (direct LLM call)
- Human gate behavior: Kinetic pauses, sends approval request via Uplink (Slack), waits for operator reply before proceeding
- Outcomes feed back into Lens: each completed node appends to `logs/history.jsonl`
- Checkpoint/resume: if run is interrupted, Attractor resumes from last checkpoint on next invocation
- Constraints: Kinetic never picks tasks directly — it only receives Briefs from Cortex. Kinetic never writes to Pipeline.

- [ ] **Step 2: Review against SYSTEM.md section 3b**

Confirm all Attractor capabilities are represented and how they map to Forge concepts.

- [ ] **Step 3: Commit**

```bash
git add design/kinetic-spec.md
git commit -m "spec: add Kinetic NLSpec"
```

---

## Task 6: lens-spec.md — Logging and Observability

**Files:**
- Create: `design/lens-spec.md`

- [ ] **Step 1: Write the spec**

Content must cover:
- Three log horizons: current run (`logs/<job>.log`), history (`logs/history.jsonl`), plan (`logs/plan.md`)
- `history.jsonl` entry schema: `{timestamp, source, job, summary, outcome, next_action, task_id?}`
- `source` values: `axon-cron | manual | kinetic | uplink`
- `outcome` values: `success | failure | partial | skipped | pending`
- Cortex reads last 20 entries from `history.jsonl` on every startup to orient itself
- Lens write interface: any component appends to `history.jsonl` by writing a JSON line — no central writer, no locking (append-only is safe)
- Log rotation: `logs/<job>.log` rotated when >1MB, keep last 3 rotations. `history.jsonl` never rotated — it is the record.
- Silence detection input: Axon reads `history.jsonl` to confirm recent activity; if last entry is >60 min old, triggers Uplink alert
- `logs/plan.md` is human-readable: current task in progress, next 3 tasks queued, last 5 completed
- Constraints: Lens is append-only for history. Never delete entries. Never modify past entries.

- [ ] **Step 2: Review against SYSTEM.md section 3**

Confirm all three horizons are fully specified with file paths and schemas.

- [ ] **Step 3: Commit**

```bash
git add design/lens-spec.md
git commit -m "spec: add Lens NLSpec"
```

---

## Task 7: uplink-spec.md — Remote Admin

**Files:**
- Create: `design/uplink-spec.md`

- [ ] **Step 1: Write the spec**

Content must cover:
- Transport: Slack via Claude.ai MCP — confirmed working, no token stored in Forge, auth managed by Claude.ai
- Channel: `#ray-groove-manager` in `mattjohnsontalk.slack.com` (channel ID: `C0AN6F2MUAH`)
- Outbound (Forge → Slack): heartbeat summary every N Axon runs, alerts on error/stale/credential failure, human gate approval requests from Kinetic
- Inbound (Slack → Forge): operator replies polled by an Axon cron; commands parsed and dispatched to Cortex
- Heartbeat message format: timestamp, last job run, active tasks count, any anomalies
- Alert message format: severity (INFO/WARN/ERROR), component, message, suggested action
- Human gate format: task title, decision required, options (e.g. "approve / reject / skip")
- Operator command vocabulary (MVP): `status`, `run <job>`, `approve <task_id>`, `reject <task_id>`
- Inbound poll: Axon cron every 60 seconds reads `#ray-groove-manager` for new messages from operator, parses commands, writes to a command queue file `forge/uplink/inbox.json`
- Cortex processes `inbox.json` at startup and after each run
- Constraints: Uplink never takes actions directly — it only passes commands to Cortex. Uplink never sends external-facing messages (only to operator channel).

- [ ] **Step 2: Review against SYSTEM.md section 7**

Confirm Slack transport details are accurate and inbound polling is fully specified.

- [ ] **Step 3: Commit**

```bash
git add design/uplink-spec.md
git commit -m "spec: add Uplink NLSpec"
```

---

## Task 8: anvil-spec.md — MCP Tools and Credential Management

**Files:**
- Create: `design/anvil-spec.md`

- [ ] **Step 1: Write the spec**

Content must cover:
- Anvil is the inventory of external system integrations and the credential health layer
- Integration registry: `forge/anvil/integrations.json` — array of `{name, type, health_check_cmd, last_checked, status}`
- Active integrations: GitHub (`gh auth status`), Slack (Claude.ai MCP — always healthy if Claude is running)
- Health check: each integration has a CLI command that returns exit code 0 if healthy
- Health checks run at Cortex startup and results go into the Brief and Lens
- Credential failure flow: Anvil detects failure → writes alert to Uplink → for services supporting device auth (e.g. `gh auth login`), Anvil generates the auth URL/code and sends it via Uplink → polls for success → updates integration status
- For Claude.ai MCP integrations (Slack, Linear, Gmail, Notion): auth is managed by Claude.ai, health check is a simple API call
- Tool invocation: components call external tools directly (gh CLI, MCP tools) — Anvil does not proxy calls, it only manages health and credentials
- Constraints: Anvil never stores credentials in plaintext files. Use system credential store or environment variables. Never log credential values.

- [ ] **Step 2: Review against SYSTEM.md section 6**

Confirm all active and target integrations are covered with health check strategy.

- [ ] **Step 3: Commit**

```bash
git add design/anvil-spec.md
git commit -m "spec: add Anvil NLSpec"
```

---

## Final Step: Update SYSTEM.md

- [ ] **Add links from SYSTEM.md component table to each spec file**

```bash
git add design/SYSTEM.md
git commit -m "spec: link component specs from SYSTEM.md"
```
