# Forge — System Specification

> Next-generation autonomous operations agent. Smart, biased for action, does the work of hundreds.

---

## Guiding Principles

**Rob Pike's 5 Rules of Programming** — the law of the land for how Forge gets built.

1. **Don't guess bottlenecks.** You can't tell where a program will spend its time. Don't optimize until you've proven where the problem is.
2. **Measure first.** Don't tune for speed until you've measured. Don't optimize unless one part overwhelms the rest.
3. **Simple beats fancy.** Fancy algorithms are slow when n is small — and n is usually small. Don't get fancy until you've proven you need to.
4. **Simple is less buggy.** Fancy algorithms are harder to implement and harder to debug. Use simple algorithms and simple data structures.
5. **Data dominates.** Choose the right data structures and the algorithms become obvious. *"Write stupid code that uses smart objects."*

> Premature optimization is the root of all evil. — Tony Hoare / Hoare's Razor, restated by Pike rules 1 & 2
> When in doubt, use brute force. — Ken Thompson, on rules 3 & 4

**Applied to Forge:** Start with flat files. Start with a single cron. Start with one Pipeline adapter. Measure before adding complexity. The Brief is the smart object — keep everything else stupid.

---

## The System: Forge

Forge is an autonomous operations agent. It runs on a heartbeat, picks up work, delegates to specialists, manages credentials, and reports to its operator. It is not a workflow builder. It is not a notes app. It is an agent with a bias for action.

Not OpenClaw. OpenClaw was dumb and inert.

---

## Components

| Component | Name | Role | Spec |
|-----------|------|------|------|
| System | **Forge** | The whole thing | — |
| Agent harness / brain | **Cortex** | Instructions, personality, boot sequence | [cortex-spec.md](cortex-spec.md) |
| Cron manager | **Axon** | Heartbeat, scheduled jobs, pulse | [axon-spec.md](axon-spec.md) |
| Task surface | **Pipeline** | Pluggable task aggregator — fan-in from GitHub, Linear, Notion, Slack, or any source into a single normalized work stream | [pipeline-spec.md](pipeline-spec.md) |
| Context packet | **Brief** | Assembled by Cortex before execution — task, history, operator profile, available tools, overrides | [brief-spec.md](brief-spec.md) |
| Task engine | **Kinetic** | Receives a Brief, executes via Attractor DOT pipelines | [kinetic-spec.md](kinetic-spec.md) |
| Logging / observability | **Lens** | What it's doing, done, and planning | [lens-spec.md](lens-spec.md) |
| Remote admin / notifications | **Uplink** | Operator comms, alerts, remote control | [uplink-spec.md](uplink-spec.md) |
| MCP / integrations | **Anvil** | External systems, credential management | [anvil-spec.md](anvil-spec.md) |

---

## 1. Cortex — Agent Harness

The control plane. Claude Code is the runtime.

- `CLAUDE.md` — entrypoint, boot sequence, mission
- `SOUL.md` — personality and operating principles
- `USER.md` — operator profile (timezone, style, preferences)
- `TOOLS.md` — tool inventory and task board protocol
- `SYSTEM.md` — this file; living design document

All behavior flows from these files. Cortex is stateless between runs — state lives in Lens logs, the task board, and external systems.

---

## 2. Axon — Cron Manager

The pulse of Forge. Crons are the primary trigger mechanism.

**Current:**
- Every 30 min — check GitHub task board, log summary

**Planned:**
- Configurable schedule per job
- Cron registry: what's running, last run, last result
- Ad-hoc cron creation from manual mode or agent decision
- Each run produces a structured Lens log entry

**Design principle:** Forge should never go silent. If no Axon cron has fired in N minutes, that itself is a Uplink alert.

---

## 3. Lens — Logging and Observability

Forge must be legible — to the operator and to itself on the next run.

**Three log horizons:**

| Horizon | What | Where |
|---------|------|-------|
| What it's doing | Current run output | `logs/<job>.log` |
| What it's done | Structured run history | `logs/history.jsonl` |
| What it's planning | Pending tasks / next actions | Task board + `logs/plan.md` |

**Requirements:**
- Each run appends a structured entry: timestamp, job, summary, outcome, next action
- Errors and anomalies flagged distinctly
- Log rotation / size management
- Self-readable: Cortex reads its own Lens history at startup to orient itself

---

## 3b. Kinetic — Task Engine (powered by Attractor)

**Kinetic is Attractor.** `mjohnson139/attractor` is the execution engine — not rebuilt, wired in.

**What Attractor brings:**
- DOT-based pipeline definitions — workflows as directed graphs, version-controlled, diffable, visualizable
- Pluggable handler system: LLM calls, tool execution, human approval gates, parallel fan-out
- Full execution engine with context state, edge routing, and condition evaluation
- Checkpoint/resume — if a run crashes, it picks back up from the last completed node
- CXDB history ingest — ingests Claude/Gemini conversation history with fork detection (feeds Lens)
- `--context key=value` CLI flag for seeding pipeline context at invocation

**How it fits in Forge:**
- Axon triggers a Kinetic pipeline via `attractor <workflow.dot>`
- Cortex picks up a task from the board, selects or generates the appropriate `.dot` pipeline
- Kinetic traverses the graph — calling Claude Code, tools, or human gates as needed
- Human gates route to Uplink for operator approval before proceeding
- Outcomes and context updates feed into Lens logs

**Workflow definitions** live in `workspaces/<project>/pipelines/*.dot`

**Repo:** `mjohnson139/attractor` — TypeScript, actively maintained, last commit March 2026

---

## 4. Manual Mode

Operator can jump in at any time to debug, tweak, or redirect.

- Invoke directly via CLI: `claude` in the Forge directory
- Cortex reads recent Lens history and task board state on entry
- Can pause/cancel in-progress work
- Can create ad-hoc tasks, override schedules, adjust Axon timing
- Can trigger any Axon job immediately without waiting for schedule
- Manual runs logged identically to scheduled runs (tagged `source: manual`)

---

## 5. Personality

Forge operates with a bias for action.

- **Detective Joe Friday energy** — just the facts, short answers, no filler
- **Does before asking** — reads the file, checks the context, figures it out
- **Biased for action** — picks up ready work without waiting to be told twice
- **Opinionated** — disagrees when right, doesn't just comply
- **Private** — operator's systems and data stay private
- **Not the operator's public voice** — careful with anything external

Encoded in `SOUL.md`. Applies equally in scheduled and manual mode.

---

## 6. Anvil — MCP Tools and Credential Management

Forge's connection to the outside world.

**Active integrations:**
- GitHub (`gh` CLI — task board, repos, PRs)
- Slack (MCP — notifications, operator comms)

**Target integrations:**
- Telegram (preferred — readily available as MCP, lower friction, mobile-native)
- Notion / second-brain CLI
- Linear (MCP available)
- Gmail (MCP available)

**Credential management:**
- Anvil detects when a credential is expired or missing
- For services that support device/browser auth flows (e.g. `gh auth login`), Forge initiates the sequence and sends the operator a code via Uplink
- Operator authenticates in their own browser; Forge detects success and resumes
- Credential health checked at startup and included in Lens heartbeat logs

**Design principle:** Forge never silently fails on an auth issue. It surfaces the problem and hands the operator exactly what they need to fix it.

---

## 7. Uplink — Remote Admin

Operator observability and control from anywhere.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FORGE                                │
│                                                             │
│  ┌─────────┐    ┌─────────┐    ┌──────────┐                │
│  │  AXON   │───▶│ CORTEX  │───▶│ KINETIC  │                │
│  │ (crons) │    │(claude) │    │(attractor)│                │
│  └─────────┘    └────┬────┘    └────┬─────┘                │
│       │              │              │                       │
│       │         ┌────▼────┐         │                       │
│       └────────▶│  LENS   │◀────────┘                       │
│                 │ (logs)  │                                 │
│                 └────┬────┘                                 │
│                      │                                      │
│                 ┌────▼────┐                                 │
│                 │  ANVIL  │                                 │
│                 │(creds / │                                 │
│                 │  MCP)   │                                 │
│                 └────┬────┘                                 │
│                      │                                      │
└──────────────────────┼──────────────────────────────────────┘
                       │ outbound only — no open ports
                       ▼
              ┌─────────────────┐
              │     UPLINK      │
              │  (Telegram bot) │
              │  polls commands │
              │  pushes alerts  │
              └────────┬────────┘
                       │
                  [internet]
                       │
              ┌────────▼────────┐
              │    TELEGRAM     │
              └────────┬────────┘
                       │
                  ┌────▼────┐
                  │  MATT   │
                  └─────────┘
```

**No open ports.** Uplink polls Telegram for inbound commands on an Axon cron. Forge never listens — only reaches out. No tunnel, no exposed server.

### Requirements
- Push alerts: anomalies, errors, stale state, credential failures
- Push heartbeat summary every N Axon runs
- Receive operator commands: trigger runs, override tasks, check status
- Approve/reject pending actions (external messages, PRs) via bot reply

### Transport
- **Slack via Claude.ai MCP** — confirmed working. Auth managed by Claude.ai, not Forge. No token stored locally, no credential rotation needed. Messages sent to `#ray-groove-manager`.

### Minimum Viable Uplink
1. Heartbeat summary pushed to Telegram every N Axon runs
2. Alerts pushed on error or stale state
3. Operator replies to bot to trigger manual check or override

---

## Open Questions

- [x] Uplink: Slack via Claude.ai MCP — confirmed working, no token management needed, auth handled by Claude.ai
- [ ] Lens log retention policy: how long, how much
- [ ] Axon cron registry format: flat file vs structured JSON
- [ ] Anvil auth flow UX: how does Forge present a `gh auth login` code cleanly via Uplink
- [ ] CXDB vs flat files for Lens — queryable history or keep it simple for now

---

## What Forge Is Not

- Not OpenClaw. OpenClaw was dumb and inert.
- Not a notes app or a workflow builder.
- Not multi-tenant. Built for one operator.
- Not passive. Forge has a heartbeat and a bias for action.
