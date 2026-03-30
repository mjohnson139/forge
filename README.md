# Forge

> Autonomous operations agent. Smart, biased for action, does the work of hundreds.

Forge is a personal operations system built on Claude Code. It runs on a heartbeat, picks up work, delegates to specialists, manages credentials, and reports to its operator.

Not a workflow builder. Not a notes app. An agent with a bias for action.

## Components

| Component | Role |
|-----------|------|
| **Cortex** | Agent harness — instructions, personality, boot sequence |
| **Axon** | Cron manager — heartbeat, scheduled jobs, pulse |
| **Pipeline** | Task aggregator — fan-in from GitHub, Linear, Notion, or any source |
| **Memory** | Persistent run state and reusable recipes for Cortex |
| **Brief** | Context packet — assembled before execution, the smart object |
| **Kinetic** | Task engine — powered by [Attractor](https://github.com/mjohnson139/attractor) |
| **Lens** | Logging and observability — what it's doing, done, and planning |
| **Uplink** | Remote admin — operator comms and alerts via Slack |
| **Anvil** | MCP tools and credential management |

## Design

Full system design and NLSpecs are in [`design/`](design/).

Start with [`design/SYSTEM.md`](design/SYSTEM.md).

## Guiding Principles

Rob Pike's 5 Rules. Start simple. Measure before optimizing. The Brief is the smart object — keep everything else stupid.

## Status

Early design phase. Components are being specified before implementation.
