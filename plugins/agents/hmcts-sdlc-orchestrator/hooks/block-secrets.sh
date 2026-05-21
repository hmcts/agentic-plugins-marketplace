#!/usr/bin/env bash
# Block prompts / file edits that contain likely secrets.
# Wired to UserPromptSubmit and PreToolUse:Write|Edit.
# Exit 2 + stderr -> Claude Code blocks the action and shows the reason.

set -euo pipefail

input="$(cat)"
event="$(jq -r '.hook_event_name // empty' <<<"$input")"

case "$event" in
  UserPromptSubmit)
    text="$(jq -r '.prompt // empty' <<<"$input")"
    where="prompt"
    ;;
  PreToolUse)
    tool="$(jq -r '.tool_name // empty' <<<"$input")"
    case "$tool" in
      Write)  text="$(jq -r '.tool_input.content // empty'    <<<"$input")"; where="Write content" ;;
      Edit)   text="$(jq -r '.tool_input.new_string // empty' <<<"$input")"; where="Edit new_string" ;;
      *)      exit 0 ;;
    esac
    ;;
  *) exit 0 ;;
esac

[[ -z "$text" ]] && exit 0

# Patterns: secret-shaped strings we never want pasted.
# Each entry: "label::regex"
patterns=(
  "Azure Key Vault URI::[a-z0-9-]+\\.vault\\.azure\\.net"
  "Azure Storage key::AccountKey=[A-Za-z0-9+/=]{40,}"
  "Azure SAS token::[?&]sig=[A-Za-z0-9%]{20,}"
  "Azure connection string::DefaultEndpointsProtocol=https;AccountName="
  "Azure SP secret env::AZURE_CLIENT_SECRET\\s*=\\s*\\S+"
  "Service principal password::--password[= ][A-Za-z0-9~._-]{16,}"
  "JWT::eyJ[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}"
  "Private key block::-----BEGIN (RSA |EC |OPENSSH |PGP |DSA )?PRIVATE KEY-----"
  "PEM certificate body::-----BEGIN CERTIFICATE-----"
  "Kubeconfig marker::client-certificate-data:|client-key-data:"
  "AWS access key::AKIA[0-9A-Z]{16}"
  "GitHub PAT::gh[pousr]_[A-Za-z0-9]{30,}"
  "Slack token::xox[baprs]-[A-Za-z0-9-]{10,}"
  "Generic password assignment::(password|passwd|pwd)\\s*[:=]\\s*['\"][^'\"]{8,}['\"]"
  "DB connection w/ creds::(postgres|jdbc:postgresql|mysql|jdbc:mysql)://[^/\\s:]+:[^@\\s]+@"
)

for p in "${patterns[@]}"; do
  label="${p%%::*}"
  regex="${p##*::}"
  if grep -E -q -- "$regex" <<<"$text"; then
    cat >&2 <<EOF
[block-secrets] Blocked $where: matched pattern "$label".

CPP rule: never paste secrets into Claude. See:
  https://tools.hmcts.net/confluence/pages/viewpage.action?pageId=1969095323

If this is a false positive, redact the value or set CPP_HOOKS_DISABLE=1 for this session.
EOF
    exit 2
  fi
done

exit 0
