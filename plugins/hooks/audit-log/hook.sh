#!/usr/bin/env bash
# audit-log hook
# Appends a JSON line to ~/.claude/audit.log for every tool Claude calls.
# Triggered by PostToolUse so it runs after every tool invocation.
# Claude Code passes hook data via JSON on stdin.

set -euo pipefail

LOG_FILE="${CLAUDE_AUDIT_LOG:-${HOME}/.claude/audit.log}"

PAYLOAD="$(cat)"
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
TOOL="$(jq -r '.tool_name // "unknown"' <<<"${PAYLOAD}")"
SESSION="$(jq -r '.session_id // "unknown"' <<<"${PAYLOAD}")"
INPUT="$(jq -c '.tool_input // null' <<<"${PAYLOAD}")"

# Write a compact JSON log line (omit tool_response to keep log size manageable)
printf '{"timestamp":"%s","session":"%s","tool":"%s","input":%s}\n' \
  "${TIMESTAMP}" \
  "${SESSION}" \
  "${TOOL}" \
  "${INPUT}" \
  >> "${LOG_FILE}"
