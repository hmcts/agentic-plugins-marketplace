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

```
/plugin install notify-on-stop@agentic-plugins-marketplace
```

## Customisation

Set `CLAUDE_STOP_MESSAGE` in your environment to override the notification text:

```bash
export CLAUDE_STOP_MESSAGE="Your coding assistant is ready."
```
