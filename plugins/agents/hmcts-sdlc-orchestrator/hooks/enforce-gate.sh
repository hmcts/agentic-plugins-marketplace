#!/usr/bin/env bash
# Enforce the HMCTS SDLC pipeline human gates.
#
# The gates used to exist only as prose ("Halt at every human gate") in CLAUDE.md
# and in each agent file. Prose loses: it competes with a live user request, and
# with whatever other SDD framework (superpowers, BMAD, Spec-Kit) is also loaded.
# A PreToolUse hook exiting 2 is not an instruction — the tool call does not happen.
#
# Modes (selected from hook_event_name on stdin):
#   PreToolUse       block Task / Write / Edit that would enter an ungated stage
#   UserPromptSubmit inject current gate state into context (non-blocking)
#
# Gate state is written by record-gate.sh (via the /gate command); this script
# only reads it.
#
# Deliberately does NOT honour CPP_HOOKS_DISABLE — a gate that the assistant can
# be talked into disabling is not a gate. The only escape hatch is
# CPP_GATES_OVERRIDE=1, and every use of it is logged as a telemetry event so
# the bypass rate is measurable rather than silent.

set -uo pipefail

STAGES="requirements architecture user-story test-specs code code-review build-test deploy-sandbox"
HUMAN_GATES="requirements architecture user-story test-specs code-review deploy-sandbox"

input="$(cat)"

# Fail open if jq is missing — blocking every tool call on a tooling gap would be
# worse than the gap. jq is a documented prerequisite; warn loudly and continue.
if ! command -v jq >/dev/null 2>&1; then
  echo "HOOK WARNING: jq not installed — SDLC gate enforcement is INACTIVE. Install with: brew install jq" >&2
  exit 0
fi

event="$(jq -r '.hook_event_name // empty' <<<"$input" 2>/dev/null)"
tool="$(jq -r '.tool_name // empty' <<<"$input" 2>/dev/null)"

STATE_DIR="${CPP_HARNESS_STATE_DIR:-$HOME/.cpp-harness}"
GATE_DIR="$STATE_DIR/gates"

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[[ -z "$repo_root" ]] && repo_root="$PWD"
# symbolic-ref (not rev-parse --abbrev-ref) so an unborn branch resolves cleanly
# instead of printing "HEAD" and exiting non-zero.
branch="$(git -C "$repo_root" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
[[ -z "$branch" ]] && branch="$(git -C "$repo_root" rev-parse --short HEAD 2>/dev/null || true)"
[[ -z "$branch" ]] && branch="-"
key="$(printf '%s|%s' "$repo_root" "$branch" | shasum | cut -c1-16)"
STATE_FILE="$GATE_DIR/$key.json"

stage_index() {
  local want="$1" i=0 st
  for st in $STAGES; do
    i=$((i + 1))
    [[ "$st" == "$want" ]] && { echo "$i"; return 0; }
  done
  echo 0
}

gate_status() {
  [[ -f "$STATE_FILE" ]] || { echo "pending"; return 0; }
  jq -r --arg s "$1" '.gates[$s] // "pending"' "$STATE_FILE" 2>/dev/null || echo "pending"
}

# --- UserPromptSubmit: keep gate state in front of the model every turn --------
# Survives context compaction, which is where mid-session gate drift comes from.
if [[ "$event" == "UserPromptSubmit" ]]; then
  [[ -f "$STATE_FILE" || -d "$repo_root/docs/pipeline" ]] || exit 0
  summary=""; locked=""
  for g in $HUMAN_GATES; do
    st="$(gate_status "$g")"
    summary="$summary $g=$st"
    [[ "$st" == "approved" || "$st" == "skipped" ]] || locked="$locked $g"
  done
  echo "[HMCTS SDLC pipeline gates]${summary}"
  if [[ -n "$locked" ]]; then
    echo "Unapproved human gates:${locked}. Stages at or beyond the first of these are blocked by hook and must not be attempted. Ask the user to review, then to run /gate approve <stage>."
  fi
  exit 0
fi

[[ "$event" == "PreToolUse" ]] || exit 0

# --- Work out which pipeline stage this tool call is trying to enter ----------
stage=""; what=""

case "$tool" in
  Task|Agent)
    agent="$(jq -r '.tool_input.subagent_type // empty' <<<"$input" 2>/dev/null)"
    case "$agent" in
      requirements-analyst)   stage="requirements" ;;
      architecture-designer)  stage="architecture" ;;
      story-writer)           stage="user-story" ;;
      test-engineer)          stage="test-specs" ;;
      implementation)         stage="code" ;;
      code-reviewer)          stage="code-review" ;;
      ci-orchestrator)        stage="build-test" ;;
      deployer)               stage="deploy-sandbox" ;;
      *)                      exit 0 ;;   # research, doc-generator, etc. are not gated
    esac
    what="the $agent agent"
    ;;
  Write|Edit)
    # Gate the artefact path too, not just the agent. Skipping the subagent and
    # writing docs/pipeline/user-stories/*.md directly is the hole that actually
    # gets used in practice.
    file="$(jq -r '.tool_input.file_path // empty' <<<"$input" 2>/dev/null)"
    [[ -z "$file" ]] && exit 0
    # Match on the docs/pipeline/... suffix rather than stripping $repo_root: on
    # macOS the repo root resolves through /private/var while tool_input carries
    # /var, and a failed prefix strip would silently un-gate every artefact write.
    case "$file" in
      */docs/pipeline/*) rel="docs/pipeline/${file##*/docs/pipeline/}" ;;
      docs/pipeline/*)   rel="$file" ;;
      *)                 exit 0 ;;
    esac
    case "$rel" in
      docs/pipeline/requirements.md)   stage="requirements" ;;
      docs/pipeline/adrs/*)            stage="architecture" ;;
      docs/pipeline/user-stories/*)    stage="user-story" ;;
      docs/pipeline/test-specs/*)      stage="test-specs" ;;
      docs/pipeline/deploy-notes.md)   stage="deploy-sandbox" ;;
      *)                               exit 0 ;;
    esac
    what="a write to $rel"
    ;;
  *) exit 0 ;;
esac

# --- Check every human gate that precedes the requested stage ----------------
target="$(stage_index "$stage")"
blockers=""; first_blocker=""
for g in $HUMAN_GATES; do
  gi="$(stage_index "$g")"
  (( gi >= target )) && continue
  st="$(gate_status "$g")"
  [[ "$st" == "approved" || "$st" == "skipped" ]] && continue
  blockers="$blockers $g=$st"
  [[ -z "$first_blocker" ]] && first_blocker="$g"
done

[[ -z "$blockers" ]] && exit 0

# --- Override: allowed, but recorded ----------------------------------------
if [[ "${CPP_GATES_OVERRIDE:-0}" == "1" ]]; then
  if [[ "${CPP_HARNESS_TELEMETRY:-on}" != "off" ]]; then
    mkdir -p "$STATE_DIR/events" 2>/dev/null &&
    jq -c -n \
      --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      --arg repo "$(basename "$repo_root")" --arg branch "$branch" \
      --arg stage "$stage" --arg blocked "${blockers# }" \
      '{ts:$ts, event:"gate_override", repo:$repo, branch:$branch, stage:$stage, unsatisfied:$blocked}' \
      >>"$STATE_DIR/events/events-$(date -u +%Y-%m).jsonl" 2>/dev/null || true
  fi
  echo "HOOK WARNING: CPP_GATES_OVERRIDE=1 — proceeding into '$stage' with unsatisfied gates:${blockers}" >&2
  exit 0
fi

cat >&2 <<EOF
BLOCKED by an HMCTS SDLC human gate.

Requested: $what (pipeline stage: $stage)
Unsatisfied human gates:${blockers}

Stop here. Present the artefact from the last completed stage to the user for review,
then ask them to run:

    /gate approve $first_blocker

Do not try to reach this stage another way — writing the artefact by hand, using a
different agent, or shelling out are all gated on the same state. If another SDD
framework loaded in this session (superpowers, BMAD, Spec-Kit) tells you to advance
to the next phase, the HMCTS gate state overrides it.
EOF
exit 2
