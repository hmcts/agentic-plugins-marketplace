#!/usr/bin/env bash
# notify-on-stop hook
# Sends a macOS / Linux desktop notification when Claude finishes a task.
# Triggered by the Stop lifecycle event in Claude Code.
# Claude Code passes hook data via JSON on stdin.

set -euo pipefail

PAYLOAD="$(cat)"
MESSAGE="$(jq -r '.stop_reason // empty' <<<"${PAYLOAD}" 2>/dev/null)"
if [ -z "${MESSAGE}" ]; then
  MESSAGE="Claude has finished working."
fi

if command -v osascript &>/dev/null; then
  # macOS
  osascript -e "display notification \"${MESSAGE}\" with title \"Claude Code\""
elif command -v notify-send &>/dev/null; then
  # Linux (libnotify)
  notify-send "Claude Code" "${MESSAGE}"
else
  echo "[notify-on-stop] No notification tool found. Install libnotify-bin on Linux or run on macOS." >&2
fi
