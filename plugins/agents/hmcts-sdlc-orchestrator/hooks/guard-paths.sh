#!/usr/bin/env bash
# Block reads/writes to sensitive files (secrets, kubeconfigs, prod helm values).
# Wired to PreToolUse:Read|Write|Edit.

set -euo pipefail

[[ "${CPP_HOOKS_DISABLE:-0}" == "1" ]] && exit 0

input="$(cat)"
[[ "$(jq -r '.hook_event_name // empty' <<<"$input")" == "PreToolUse" ]] || exit 0

tool="$(jq -r '.tool_name // empty' <<<"$input")"
case "$tool" in
  Read)        path="$(jq -r '.tool_input.file_path // empty' <<<"$input")" ;;
  Write|Edit)  path="$(jq -r '.tool_input.file_path // empty' <<<"$input")" ;;
  *)           exit 0 ;;
esac
[[ -z "$path" ]] && exit 0

block() {
  local label="$1"
  cat >&2 <<EOF
[guard-paths] Blocked $tool on: $path
Reason: $label

CPP rule: see https://tools.hmcts.net/confluence/pages/viewpage.action?pageId=1969095323
EOF
  exit 2
}

base="$(basename "$path")"

# Allow obvious templates / examples
case "$base" in
  .env.example|.env.sample|.env.template|.env.dist) exit 0 ;;
esac

# Secrets-shaped files
case "$base" in
  .env|.env.*|*.env)                      block "dotenv file" ;;
  kubeconfig|kubeconfig.*|*.kubeconfig)   block "kubeconfig" ;;
  id_rsa|id_ed25519|id_ecdsa|id_dsa)      block "SSH private key" ;;
  credentials.json|credentials|service-account*.json) block "credentials file" ;;
esac

# Path-segment based
case "$path" in
  */secrets/*|*/.secrets/*|*/private-keys/*) block "secrets directory" ;;
  *.pem|*.key|*.pfx|*.p12)                   block "certificate / key file" ;;
esac

# Prod Helm values — read is fine, writes/edits are blocked
if [[ "$tool" != "Read" ]]; then
  case "$path" in
    *cpp-helm-chart/*values-live*.yaml|*cpp-helm-chart/*values-prod*.yaml|*cpp-helm-chart/*values-production*.yaml)
      block "edit to prod Helm values (use a PR via human-driven flow)"
      ;;
    *cpp-flux-config/clusters/*prod*/*|*cpp-flux-config/clusters/*live*/*)
      block "edit to prod Flux cluster config"
      ;;
  esac
fi

exit 0
