#!/usr/bin/env bash
# Block dangerous shell invocations: hook bypass, force-push to main, prod cluster/DB access.
# Wired to PreToolUse:Bash.

set -euo pipefail

[[ "${CPP_HOOKS_DISABLE:-0}" == "1" ]] && exit 0

input="$(cat)"
[[ "$(jq -r '.hook_event_name // empty' <<<"$input")" == "PreToolUse" ]] || exit 0
[[ "$(jq -r '.tool_name // empty'       <<<"$input")" == "Bash" ]]       || exit 0

cmd="$(jq -r '.tool_input.command // empty' <<<"$input")"
[[ -z "$cmd" ]] && exit 0

block() {
  local label="$1" reason="$2"
  cat >&2 <<EOF
[guard-bash] Blocked: $label

$reason

CPP rule: see https://tools.hmcts.net/confluence/pages/viewpage.action?pageId=1969095323
Override (single session) with CPP_HOOKS_DISABLE=1 only if you understand the consequences.
EOF
  exit 2
}

# Hook / signing bypass
grep -E -q -- '(^|[[:space:]])--no-verify($|[[:space:]])'                 <<<"$cmd" && block "git --no-verify"               "Pre-commit/pre-push hooks must run."
grep -E -q -- '(^|[[:space:]])--no-gpg-sign($|[[:space:]])'               <<<"$cmd" && block "git --no-gpg-sign"             "Commit signing must not be bypassed."
grep -E -q -- '(^|[[:space:]])--dangerously-skip-permissions($|[[:space:]])' <<<"$cmd" && block "--dangerously-skip-permissions" "Per-action approval is required on machines with CPP access."

# Force-push to protected branches
if grep -E -q 'git[[:space:]]+push' <<<"$cmd" \
   && grep -E -q -- '(--force\b|(^|[[:space:]])-f($|[[:space:]])|--force-with-lease)' <<<"$cmd" \
   && grep -E -q '(\b|:)(main|master|develop|release/[A-Za-z0-9._/-]+)\b' <<<"$cmd"; then
  block "git force-push to protected branch" "Force-pushing main/master/develop/release branches is not allowed."
fi

# Prod / live AKS or kubectl
grep -E -iq 'kubectl[[:space:]].*--context[= ][^[:space:]]*\b(prod|production|live)\b' <<<"$cmd" && block "kubectl against prod context" "Claude must not run kubectl against prod/live clusters."
grep -E -iq 'az[[:space:]]+aks[[:space:]].*\b(prod|live|production)\b'                  <<<"$cmd" && block "az aks targeting prod" "Production AKS operations require human-driven workflows, not Claude."

# Prod DB connections (heuristic: hostname contains prod/live)
grep -E -iq '(psql|mysql|jdbc:(postgresql|mysql))[^[:space:]]*\b(prod|live)\b'           <<<"$cmd" && block "DB connection to prod/live" "Do not connect Claude to production databases."

# rm -rf on workspace roots
grep -E -q 'rm[[:space:]]+(-[rRfF]+[[:space:]]+)+(/|/Users/[^/]+(/cpp)?/?[[:space:]]*$|\$HOME/?[[:space:]]*$)' <<<"$cmd" && block "rm -rf on workspace root" "Refusing destructive recursive delete on a top-level path."

exit 0
