# Audit Log Hook

Appends a JSON line to `~/.claude/audit.log` for every tool Claude invokes. Useful for compliance, debugging, or just understanding what Claude did during a session.

## Log format

Each line is a newline-delimited JSON object:

```json
{"timestamp":"2026-04-15T10:30:00Z","session":"sess_abc123","tool":"Bash","input":{"command":"git status"}}
```

## Events

| Event | When it fires |
|-------|--------------|
| `PostToolUse` | After every tool call Claude makes |

## Installation

```bash
./scripts/install.sh hooks/audit-log
```

## Manual installation

```bash
mkdir -p ~/.claude/hooks
cp hook.sh ~/.claude/hooks/audit-log.sh
chmod +x ~/.claude/hooks/audit-log.sh
```

Then add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "hooks": [{ "type": "command", "command": "~/.claude/hooks/audit-log.sh" }]
      }
    ]
  }
}
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_AUDIT_LOG` | `~/.claude/audit.log` | Path to the log file |

## Querying the log

```bash
# Show all Bash commands Claude ran today
jq 'select(.tool == "Bash") | .input.command' ~/.claude/audit.log

# Count tool calls per session
jq -r .session ~/.claude/audit.log | sort | uniq -c | sort -rn
```
