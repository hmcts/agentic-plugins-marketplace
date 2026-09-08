---
name: hol-guard
description: Use when the user wants to protect Claude Code or another local AI harness with HOL Guard, inspect Guard approvals or receipts, or verify runtime security setup before tools execute.
license: Apache-2.0
---

# HOL Guard

HOL Guard is a local security layer for AI agents, tools, MCP servers, plugins, skills, and package installs. Use this skill to put the `hol-guard` runtime on the execution path and verify that Guard owns the protection setup.

## Safety rules

- Never read `.env` files.
- Never bypass Guard approvals.
- Do not mark a workspace protected until a Guard command proves status.
- Prefer Guard-owned commands over direct edits to user-level harness configuration.
- Preserve existing workspace changes.

## Install check

Probe the actual CLI instead of relying on shell-specific executable lookup commands:

```bash
hol-guard --version
```

If the CLI is unavailable and the user asked for runtime setup, prefer an isolated CLI install:

```bash
pipx install hol-guard
```

Then verify the runtime and detect the exact supported local harness identifier:

```bash
hol-guard status
hol-guard detect --json
```

## Protect a local harness

Use the exact harness identifier returned by `hol-guard detect --json`. Do not maintain or guess a separate supported-harness list in this skill.

For a detected supported harness, use Guard's own install and run flow:

```bash
hol-guard bootstrap
hol-guard install <harness>
hol-guard run <harness> --dry-run
hol-guard doctor <harness> --json
hol-guard run <harness>
hol-guard status
```

A missing detection result, Guard error, failed dry-run, or failed doctor check is not permission to launch an unprotected fallback agent.

### Claude Code

When `hol-guard detect --json` identifies Claude Code, use its exact Guard harness identifier:

```bash
hol-guard install claude-code
hol-guard run claude-code --dry-run
hol-guard doctor claude-code --json
hol-guard run claude-code
```

Prefer these Guard-owned Claude hooks and checks over manual configuration changes.

## Review blocked or queued requests

```bash
hol-guard approvals
hol-guard approvals open <request-id>
hol-guard receipts
hol-guard diff <harness>
```

For a terminal-only decision:

```bash
hol-guard approvals approve <request-id>
hol-guard approvals deny <request-id>
```

Only approve after reading the risk reason and understanding the requested scope.

## Evidence

Use Guard evidence commands when the user needs an audit trail or handoff artifact:

```bash
hol-guard receipts
hol-guard inventory
hol-guard abom --format json
hol-guard events
```

Cloud sync is optional and should only be enabled when the user asks for it.

## Upstream references

- HOL Guard: https://github.com/hashgraph-online/hol-guard
- Canonical Agent Skill: https://github.com/hashgraph-online/hol-guard-plugin/tree/main/skills/hol-guard
