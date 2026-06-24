#!/usr/bin/env bash
# Block prompts / file edits that look like they contain CPP case data or PII.
# Wired to UserPromptSubmit and PreToolUse:Write|Edit.
# Pattern set is intentionally conservative; tune via CPP_PII_ALLOW env if needed.

set -euo pipefail

[[ "${CPP_HOOKS_DISABLE:-0}" == "1" ]] && exit 0

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

# CPP / criminal-justice PII shapes.
# Refs:
#  - URN (Unique Reference Number, CJS): 2 digits + 2 letters + 7 digits, e.g. 01AA1234567
#  - NINO (UK National Insurance Number)
#  - Loose DOB (yyyy-mm-dd or dd/mm/yyyy) is too noisy on its own; we require an adjacent label
patterns=(
  "URN (CJS)::\\b[0-9]{2}[A-Z]{2}[0-9]{7}\\b"
  "NINO::\\b[A-CEGHJ-PR-TW-Z]{2}[0-9]{6}[A-D]\\b"
  "DOB w/ label::\\b(DOB|date.of.birth)\\b[^A-Za-z0-9]{0,5}([0-9]{2}[/.-][0-9]{2}[/.-][0-9]{2,4}|[0-9]{4}-[0-9]{2}-[0-9]{2})"
  "UK passport hint::\\bpassport\\b[^A-Za-z0-9]{0,5}[0-9]{9}\\b"
  "Defendant block::\\b(defendant|witness|victim)\\s*(name|surname)\\s*[:=]"
  "Court reference label::\\b(case|court).?(ref(erence)?|number)\\s*[:=]"
)

for p in "${patterns[@]}"; do
  label="${p%%::*}"
  regex="${p##*::}"
  if grep -E -q -- "$regex" <<<"$text"; then
    cat >&2 <<EOF
[block-pii] Blocked $where: matched pattern "$label".

CPP rule: no real case data, PII, or court references in Claude prompts/files.
Use synthetic / anonymised data. See:
  https://tools.hmcts.net/confluence/pages/viewpage.action?pageId=1969095323

Set CPP_HOOKS_DISABLE=1 to override for one session if you are certain this is synthetic.
EOF
    exit 2
  fi
done

exit 0
