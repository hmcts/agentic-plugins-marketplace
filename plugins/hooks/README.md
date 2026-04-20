# Hook Plugins

Hooks are shell scripts that Claude Code executes automatically in response to lifecycle events — before or after tool calls, when a session ends, and more.

## Available hooks

| Plugin | Event | Description |
|--------|-------|-------------|
| [notify-on-stop](./notify-on-stop/) | `Stop` | Desktop notification when Claude finishes |
| [audit-log](./audit-log/) | `PostToolUse` | JSON audit trail of every tool call |

## Installation

```bash
/plugin install <name>@agentic-plugins-marketplace
```

## Lifecycle events

| Event | Fires when | Can block? |
|-------|-----------|-----------|
| `PreToolUse` | Before any tool call | Yes (non-zero exit blocks) |
| `PostToolUse` | After a tool returns | No |
| `Notification` | Claude surfaces a notification | No |
| `Stop` | Claude finishes its turn | No |
| `SubagentStop` | A subagent finishes | No |

## Adding a new hook

See [CONTRIBUTING.md](../../CONTRIBUTING.md#adding-a-hook).
