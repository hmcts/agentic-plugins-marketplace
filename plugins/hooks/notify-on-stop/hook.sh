#!/usr/bin/env bash
# notify-on-stop hook
# Sends a macOS / Linux desktop notification when Claude finishes a task.
# Triggered by the Stop lifecycle event in Claude Code.

set -euo pipefail

# Consume stdin — Stop event payload contains stop_reason and session_id
PAYLOAD="$(cat)"
STOP_REASON="$(echo "$PAYLOAD" | jq -r '.stop_reason // "end_turn"')"

MESSAGE="Claude has finished (${STOP_REASON})."

if command -v osascript &>/dev/null; then
  # macOS
  osascript -e "display notification \"${MESSAGE}\" with title \"Claude Code\""
elif command -v notify-send &>/dev/null; then
  # Linux (libnotify)
  notify-send "Claude Code" "${MESSAGE}"
else
  echo "[notify-on-stop] No notification tool found. Install libnotify-bin on Linux or run on macOS." >&2
fi
