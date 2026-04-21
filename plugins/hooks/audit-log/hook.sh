#!/usr/bin/env bash
# audit-log hook
# Appends a JSON line to ~/.claude/audit.log for every tool Claude calls.
# Triggered by PostToolUse so it runs after every tool invocation.

set -euo pipefail

LOG_FILE="${CLAUDE_AUDIT_LOG:-${HOME}/.claude/audit.log}"

PAYLOAD="$(cat)"

TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
TOOL="$(echo "$PAYLOAD" | jq -r '.tool_name // "unknown"')"
SESSION="$(echo "$PAYLOAD" | jq -r '.session_id // "unknown"')"
INPUT="$(echo "$PAYLOAD" | jq -c '.tool_input // null')"

printf '{"timestamp":"%s","session":"%s","tool":"%s","input":%s}\n' \
  "${TIMESTAMP}" \
  "${SESSION}" \
  "${TOOL}" \
  "${INPUT}" \
  >> "${LOG_FILE}"
