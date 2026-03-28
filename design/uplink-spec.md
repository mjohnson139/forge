# Uplink — Remote Admin NLSpec

## Overview

Uplink is the operator's window into Forge from anywhere. It pushes heartbeats and alerts outbound, and receives operator commands inbound — all via Slack, using Claude.ai's MCP integration. No open ports. No stored tokens. Forge only reaches out; it never listens.

---

## Responsibilities

- Push heartbeat summaries to the operator on a regular cadence
- Push alerts for errors, stale state, and credential failures
- Dispatch human gate approval requests from Kinetic
- Poll for inbound operator commands and queue them for Cortex
- Never take actions directly — only pass commands to Cortex

---

## Interface

**Transport:** Slack via Claude.ai MCP
- MCP tool: `mcp__claude_ai_Slack__slack_send_message` (outbound)
- MCP tool: `mcp__claude_ai_Slack__slack_read_channel` (inbound poll)
- Channel: `#ray-groove-manager` in `mattjohnsontalk.slack.com` (channel ID: `C0AN6F2MUAH`)
- Auth: managed entirely by Claude.ai — no token stored in Forge, no credential rotation needed

**Inbound queue:** `forge/uplink/inbox.json` — array of parsed operator commands, written by Uplink's poll job, consumed and cleared by Cortex

---

## Behavior

### Outbound: Heartbeat

Sent every N Axon runs (configurable, default: every 2 board-check runs = every 60 minutes).

**Heartbeat message format:**
```
[Forge Heartbeat] <timestamp>
Last job: <job_name> at <time> — <outcome>
Active tasks: <count>
Anomalies: <none | list of issues>
```

Cortex reads recent Lens history and the current Pipeline task count to populate this message.

### Outbound: Alert

Sent on any of: job failure, silence detection, credential failure, anomaly.

**Alert message format:**
```
[<SEVERITY>] <component>: <message>
Suggested action: <what the operator should do>
```

Severity levels: `INFO`, `WARN`, `ERROR`

Examples:
- `[ERROR] Axon: board-check job failed — no output in last run. Check logs/board-check.log.`
- `[WARN] Lens: No Forge activity in >60 minutes.`
- `[ERROR] Anvil: GitHub credential expired. Run: gh auth login`

### Outbound: Human gate request

Sent when Kinetic reaches a `human` node in a pipeline.

**Human gate message format:**
```
[Gate] <task_title>
Decision required: <question>
Options: <option1> / <option2> / <option3>
Reply with: approve <task_id> | reject <task_id> | skip <task_id>
```

### Inbound: Operator command polling

An Axon cron runs every 60 seconds. It:
1. Calls `mcp__claude_ai_Slack__slack_read_channel` to read recent messages in `#ray-groove-manager`
2. Filters for messages from the operator (not from Forge itself)
3. Parses messages for recognized commands (see command vocabulary below)
4. Writes parsed commands to `forge/uplink/inbox.json` as an array of objects:

```
[
  {
    "received_at": "<ISO 8601>",
    "raw":         "<original message text>",
    "command":     "<status | run | approve | reject>",
    "args":        {"job": "<job_name>", "task_id": "<id>"}
  }
]
```

5. Cortex reads and clears `inbox.json` at startup and after each run

### Operator command vocabulary (MVP)

| Command | Example | Action |
|---------|---------|--------|
| `status` | `status` | Cortex sends current Lens summary + active task list |
| `run <job>` | `run board-check` | Cortex triggers the named Axon job immediately |
| `approve <task_id>` | `approve gh-42` | Cortex resumes a human gate in Kinetic with approval |
| `reject <task_id>` | `reject gh-42` | Cortex resumes a human gate in Kinetic with rejection |

Unrecognized commands are logged to Lens with `outcome: skipped` and the operator is notified that the command was not understood.

---

## Constraints

- **Uplink never takes actions directly.** It only queues commands in `inbox.json`. Cortex decides what to do.
- **Uplink only sends to the operator's private channel.** `#ray-groove-manager` is the sole outbound destination. Never send to public channels or DMs without operator instruction.
- **No open ports.** Forge never runs an HTTP server or listener. Inbound commands are received by polling.
- **No token stored in Forge.** Slack auth is managed by Claude.ai MCP. If MCP is unavailable, Uplink is unavailable — this is surfaced in Anvil health status.
- **Heartbeat cadence must be configurable** — stored in `forge/axon/registry.json` as part of the heartbeat job definition, not hardcoded.
- **Uplink poll job must write to Lens** on every run (even if no new commands) to avoid triggering silence detection.

---

## Integration Points

| Component | How Uplink interacts |
|-----------|---------------------|
| **Axon** | Uplink poll is an Axon cron job (every 60s); heartbeat is an Axon cron job |
| **Cortex** | Cortex reads `inbox.json`; Cortex triggers outbound Uplink messages |
| **Kinetic** | Human gate nodes dispatch approval requests through Uplink |
| **Lens** | Uplink poll job writes to Lens; Cortex reads Lens to build heartbeat content |
| **Anvil** | Claude.ai MCP health is tracked in Anvil; Uplink availability depends on it |

---

## Open Questions

- What is the right heartbeat cadence? Every 2 board-checks (60 min) or configurable per `registry.json`?
- How should Uplink handle rate limiting from Slack MCP — backoff strategy?
- If `inbox.json` has unprocessed commands when Cortex starts a new run, should it process all of them or only the most recent?
- Future transport: Telegram is the preferred long-term transport (mobile-native, lower friction). Migration path from Slack → Telegram?
