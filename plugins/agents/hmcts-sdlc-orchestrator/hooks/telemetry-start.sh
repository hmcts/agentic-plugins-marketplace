#!/usr/bin/env bash
# SessionStart hook: find or start the local telemetry forwarder, then record the session start.
# Telemetry never blocks a session: this script always exits 0.
# CPP_HARNESS_TELEMETRY=off turns it off for the session.
# Every Python call runs isolated (-I -B) from the data directory, never the session's cwd,
# so nothing in a checked-out repository can be imported.

set -u

[ "${CPP_HARNESS_TELEMETRY:-on}" = "off" ] && exit 0
root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
data="${CLAUDE_PLUGIN_DATA:-${HOME:-}/.claude/plugins/data/hmcts-sdlc-orchestrator}"
cd "$data" 2>/dev/null || cd / || exit 0

py=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
    "$candidate" -I -B -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    py="$candidate"
    break
  fi
done
if [ -z "$py" ]; then
  echo "cpp telemetry: python3 3.9+ not found; telemetry off for this session"
  exit 0
fi

# The hook JSON on stdin passes straight through to the CLI.
"$py" -I -B "$root/bin/cpp_telemetry" start || true
exit 0
