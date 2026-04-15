#!/usr/bin/env bash
# audit-log hook
# Appends a JSON line to ~/.claude/audit.log for every tool Claude calls.
# Triggered by PostToolUse so it runs after every tool invocation.

set -euo pipefail

LOG_FILE="${CLAUDE_AUDIT_LOG:-${HOME}/.claude/audit.log}"

# Claude Code passes tool details as environment variables:
#   CLAUDE_TOOL_NAME      — name of the tool that was called
#   CLAUDE_TOOL_INPUT     — JSON string of the tool's input arguments
#   CLAUDE_TOOL_RESULT    — JSON string of the tool's result (may be large)
#   CLAUDE_SESSION_ID     — unique ID for the current Claude Code session

TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
TOOL="${CLAUDE_TOOL_NAME:-unknown}"
SESSION="${CLAUDE_SESSION_ID:-unknown}"

# Write a compact JSON log line (omit TOOL_RESULT to keep log size manageable)
printf '{"timestamp":"%s","session":"%s","tool":"%s","input":%s}\n' \
  "${TIMESTAMP}" \
  "${SESSION}" \
  "${TOOL}" \
  "${CLAUDE_TOOL_INPUT:-null}" \
  >> "${LOG_FILE}"
