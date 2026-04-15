# Hook Plugins

Hooks are shell scripts that Claude Code executes automatically in response to lifecycle events — before or after tool calls, when a session ends, and more. They let you add automation, logging, or guardrails without modifying Claude's behaviour directly.

## Available hooks

| Plugin | Event | Description |
|--------|-------|-------------|
| [notify-on-stop](./notify-on-stop/) | `Stop` | Desktop notification when Claude finishes |
| [audit-log](./audit-log/) | `PostToolUse` | JSON audit trail of every tool call |

## Lifecycle events

| Event | Fires when |
|-------|-----------|
| `PreToolUse` | Before Claude calls any tool (can block the call) |
| `PostToolUse` | After a tool returns |
| `Notification` | Claude wants to surface a message |
| `Stop` | Claude has finished its turn |
| `SubagentStop` | A subagent has finished |

## How hooks work

1. Claude Code detects a lifecycle event.
2. It finds all matching hook entries in `~/.claude/settings.json`.
3. It executes the configured shell command, passing event context as environment variables.
4. For `PreToolUse`, a non-zero exit code blocks the tool call.

## Adding a new hook

See [CONTRIBUTING.md](../../../CONTRIBUTING.md#adding-a-hook).
