#!/usr/bin/env bash
# Stop / SubagentStop / SessionEnd hook: hand the hook JSON to the local telemetry forwarder.
# Prints nothing and always exits 0 within 3 s: a watchdog ends the work after 2.5 s.
# The control token goes only to the port that `ensure-running` proof-checked in this run,
# and never on a command line (curl reads the header from a file descriptor).

set -u

[ "${CPP_HARNESS_TELEMETRY:-on}" = "off" ] && exit 0
data="${CLAUDE_PLUGIN_DATA:-${HOME:-}/.claude/plugins/data/hmcts-sdlc-orchestrator}"
[ -e "$data/opt-out" ] && exit 0
root="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

input=""
IFS= read -r -d '' input || true
[ -n "$input" ] || exit 0
exec >/dev/null 2>&1

nudge() {
  local py port token
  py=python3
  command -v "$py" >/dev/null 2>&1 || py=python
  command -v "$py" >/dev/null 2>&1 || return 0
  # Finds or starts the forwarder and prints its port once the healthz proof passes.
  port="$("$py" -B "$root/bin/cpp_telemetry" ensure-running </dev/null)" || return 0
  case "$port" in '' | *[!0-9]*) return 0 ;; esac
  token=""
  [ -r "$data/token" ] && IFS= read -r token <"$data/token"
  case "$token" in '' | *[!0-9a-f]*) return 0 ;; esac
  if command -v curl >/dev/null 2>&1 &&
    printf '%s' "$input" | curl -s -o /dev/null -m 2 --noproxy '*' -X POST \
      -H 'Content-Type: application/json' -H @<(printf 'X-Cpp-Telemetry-Token: %s\n' "$token") \
      --data-binary @- "http://127.0.0.1:$port/hook"; then
    return 0
  fi
  "$py" -B - "$port" "$data/token" <(printf '%s' "$input") <<'PY'
import sys
import urllib.request

port, token_path, body_path = int(sys.argv[1]), sys.argv[2], sys.argv[3]
with open(token_path, encoding="utf-8") as fh:
    token = fh.read().strip()
with open(body_path, "rb") as fh:
    body = fh.read()
request = urllib.request.Request(
    "http://127.0.0.1:%d/hook" % port, data=body, method="POST",
    headers={"Content-Type": "application/json", "X-Cpp-Telemetry-Token": token})
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never through a proxy
try:
    opener.open(request, timeout=2).close()
except Exception:
    pass
PY
}

nudge &
worker=$!
(sleep 2.5 && kill "$worker") &
watchdog=$!
wait "$worker"
kill "$watchdog"
exit 0
