# Anvil — MCP Tools and Credential Management NLSpec

## Overview

Anvil is Forge's connection to the outside world. It maintains an inventory of external system integrations, tracks their health, and manages credential failure detection and recovery. Anvil never proxies calls — components invoke tools directly. Anvil only manages health and credentials.

---

## Responsibilities

- Maintain the integration registry: what is connected, how to check it, when it was last checked
- Run health checks at Cortex startup and include results in the Brief
- Detect credential failures and surface them to Cortex/Uplink immediately
- Initiate credential recovery flows for services that support device/browser auth
- Write health check results to Lens
- Never store credentials in plaintext files

---

## Interface

**Integration registry:** `forge/anvil/integrations.json`

Array of integration objects:

```
{
  "name":             "<integration name>",
  "type":             "<gh-cli | claude-ai-mcp | mcp-server | local-tool>",
  "health_check_cmd": "<shell command that exits 0 if healthy>",
  "last_checked":     "<ISO 8601 or null>",
  "status":           "<healthy | degraded | failed | unknown>"
}
```

**Type vocabulary:**

| Type | Description |
|------|-------------|
| `gh-cli` | GitHub CLI — local binary, manages its own credentials |
| `claude-ai-mcp` | MCP server via Claude.ai — auth managed by Claude.ai, not Forge |
| `mcp-server` | Self-hosted or third-party MCP server with local credentials |
| `local-tool` | Local binary or script with no external auth — health check is invocation test |

**Outputs:**
- Updated `last_checked` and `status` in `integrations.json` after each health check
- Lens entries recording health check results
- Uplink alerts on credential failure
- Auth recovery codes/URLs dispatched via Uplink

---

## Behavior

### Health check cycle

At Cortex startup:
1. Cortex reads `forge/anvil/integrations.json`
2. For each integration, Cortex runs `health_check_cmd` and checks the exit code
3. Exit 0 → `status: healthy`; non-zero → `status: failed`
4. `last_checked` is updated to the current timestamp
5. Results are written back to `integrations.json`
6. Results are appended to `logs/history.jsonl` (source: `cortex`, one entry per failed integration; a single summary entry if all healthy)
7. Results are included in the Brief's `tools` field

### Active integrations

| Integration | Type | Health check command |
|-------------|------|---------------------|
| GitHub | `gh-cli` | `gh auth status` |
| Slack | `claude-ai-mcp` | `mcp__claude_ai_Slack__slack_read_channel` (test call) — healthy if Claude.ai MCP is running |

For Claude.ai MCP integrations, "healthy" means Claude.ai is running and the MCP connection is active. Auth is managed by Claude.ai — Forge has no credentials to rotate.

### Target integrations (future, not yet active)

| Integration | Type | Notes |
|-------------|------|-------|
| Telegram | `mcp-server` | Preferred long-term Uplink transport |
| Linear | `claude-ai-mcp` | Task source for Pipeline |
| Gmail | `claude-ai-mcp` | Email monitoring |
| Notion | `claude-ai-mcp` | Second-brain integration |

### Credential failure flow

When a health check fails for a `gh-cli` type integration:
1. Anvil writes a failure entry to Lens
2. Uplink dispatches an ERROR alert: e.g., `[ERROR] Anvil: GitHub credential expired. Run: gh auth login`
3. If the service supports device auth (e.g., GitHub), Anvil generates the auth initiation:
   - Runs `gh auth login --web` (or equivalent) to start the device flow
   - Captures the one-time code and device verification URL
   - Sends these to the operator via Uplink: `[ACTION REQUIRED] GitHub auth: go to <url> and enter code <code>`
4. Anvil polls `gh auth status` every 30 seconds until healthy or timeout (15 minutes)
5. On success: updates `integrations.json`, writes a success Lens entry, sends confirmation via Uplink
6. On timeout: sends WARN alert, marks status `failed`, stops polling

For Claude.ai MCP integrations: auth is managed by Claude.ai. If an MCP tool call fails, Anvil marks it `degraded` and alerts the operator to check the Claude.ai MCP connection. No auth flow to initiate from Forge.

### Forge never silently fails on auth

If any active integration is `failed` or `degraded`:
- The Brief reflects this in the `tools` field (status: `failed`)
- Cortex may choose to skip tasks that depend on the failed integration
- The operator is always notified via Uplink — never a silent skip

---

## Constraints

- **Never store credentials in plaintext files.** Use system credential stores (e.g., `gh` manages its own token in the system keychain or `~/.config/gh/hosts.yml` — Forge does not read or write this file).
- **Never log credential values.** Lens entries and Uplink messages must never contain tokens, passwords, or secrets — only status and auth URLs/codes.
- **Anvil does not proxy tool calls.** Components call `gh`, MCP tools, etc. directly. Anvil only manages the health layer.
- **Health checks must be fast and non-destructive.** A health check command must complete in <5 seconds and must not modify state.
- **Anvil reads, never writes, to external credential stores.** It calls `gh auth login` to initiate a flow, but it does not write tokens itself.

---

## Integration Points

| Component | How Anvil interacts |
|-----------|-------------------|
| **Cortex** | Cortex runs health checks via Anvil at startup; receives health results for Brief assembly |
| **Brief** | Anvil health status populates the `tools` field |
| **Lens** | Health check results written to `logs/history.jsonl` |
| **Uplink** | Credential failures and auth recovery steps dispatched via Uplink alerts |

---

## Open Questions

- Should `integrations.json` include a `required: true/false` field to distinguish critical vs. optional integrations?
- Device auth flow UX: how does Forge present a `gh auth login` code cleanly in a Slack message? Format and timeout need to be specified precisely.
- Should Anvil run health checks on a background Axon cron (not just at Cortex startup) to catch mid-run degradation?
- What is the fallback if both Slack MCP and GitHub are simultaneously `failed` — how does Forge signal the operator?
