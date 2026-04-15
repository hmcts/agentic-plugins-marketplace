# Notify on Stop Hook

Sends a desktop notification when Claude finishes a long-running task so you can context-switch away and come back when it's done. Works on macOS (native notifications) and Linux (libnotify).

## Events

| Event | When it fires |
|-------|--------------|
| `Stop` | Claude has finished its current turn and is waiting for input |

## Prerequisites

- **macOS** — no extra dependencies (uses `osascript`)
- **Linux** — install `libnotify-bin`: `sudo apt install libnotify-bin`

## Installation

```bash
./scripts/install.sh hooks/notify-on-stop
```

The installer:
1. Copies `hook.sh` to `~/.claude/hooks/notify-on-stop.sh` and makes it executable
2. Appends the hook entry to `~/.claude/settings.json`

## Manual installation

```bash
# 1. Copy the script
mkdir -p ~/.claude/hooks
cp hook.sh ~/.claude/hooks/notify-on-stop.sh
chmod +x ~/.claude/hooks/notify-on-stop.sh

# 2. Add to settings.json (merge into existing hooks array if present)
cat >> ~/.claude/settings.json <<'EOF'
{
  "hooks": {
    "Stop": [
      { "hooks": [{ "type": "command", "command": "~/.claude/hooks/notify-on-stop.sh" }] }
    ]
  }
}
EOF
```

## Customisation

Set `CLAUDE_STOP_MESSAGE` in your environment to override the notification text:

```bash
export CLAUDE_STOP_MESSAGE="Your coding assistant is ready."
```
