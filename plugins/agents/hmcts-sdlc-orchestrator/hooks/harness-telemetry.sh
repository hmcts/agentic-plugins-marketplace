#!/usr/bin/env bash
# Record harness usage events to a local JSONL log, and maintain the session
# state the git hooks read when recording which commits the harness helped
# produce. Attribution is held in that local index only — nothing is ever
# written into a commit message. See docs/telemetry/attribution-index.md.
#
# Wired to SessionStart, PostToolUse (Skill|Task|Agent|Write|Edit), Stop, SessionEnd.
#
# Records NO prompt text, NO file contents, NO file paths, NO developer identity.
# Only: event kind, timestamp, session id, repo basename, branch, tool name,
# skill/agent name, and whether a write landed in docs/pipeline/.
#
# Never blocks. Always exits 0 — telemetry must not be able to break a session.

set -uo pipefail

# --- opt-out ---------------------------------------------------------------
[[ "${CPP_HARNESS_TELEMETRY:-on}" == "off" ]] && exit 0
[[ "${CPP_HOOKS_DISABLE:-0}" == "1" ]] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

STATE_DIR="${CPP_HARNESS_STATE_DIR:-$HOME/.cpp-harness}"
LOG_DIR="$STATE_DIR/events"
SESSION_DIR="$STATE_DIR/by-repo"
mkdir -p "$LOG_DIR" "$SESSION_DIR" 2>/dev/null || exit 0

# --- pseudonymous installation id ------------------------------------------
# Random, generated once, stored locally, never derived from name/email/host.
# Without it "weekly active developers" — the headline adoption metric — cannot
# be computed, because every other field is deliberately non-identifying.
# It cannot be mapped back to a person without access to that person's machine.
ID_FILE="$STATE_DIR/installation-id"
if [[ ! -s "$ID_FILE" ]]; then
  { uuidgen 2>/dev/null || od -An -tx1 -N16 /dev/urandom | tr -d ' \n'; } >"$ID_FILE" 2>/dev/null || true
fi
# Lower-cased: uuidgen returns uppercase on macOS and lowercase elsewhere, and
# the same installation must not appear as two ids in an aggregated report.
install_id="$(tr -cd 'a-fA-F0-9' <"$ID_FILE" 2>/dev/null | tr 'A-F' 'a-f' | cut -c1-12)"

input="$(cat)"
event="$(jq -r '.hook_event_name // empty' <<<"$input")"
session="$(jq -r '.session_id // empty' <<<"$input" | tr -cd 'a-f0-9' | cut -c1-12)"
cwd="$(jq -r '.cwd // empty' <<<"$input")"
[[ -z "$event" ]] && exit 0

now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# --- repo identity ---------------------------------------------------------
# Basename only. The absolute path can contain a person's name (/Users/<name>/…)
# and is never written to the log.
repo=""
branch=""
repo_root=""
if [[ -n "$cwd" && -d "$cwd" ]]; then
  repo_root="$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null || true)"
  if [[ -n "$repo_root" ]]; then
    repo="$(basename "$repo_root")"
    branch="$(git -C "$repo_root" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
  fi
fi

emit() {  # emit <kind> [extra-jq-object]
  local kind="$1" extra="${2:-{\}}"
  jq -c -n \
    --arg ts "$now" --arg ev "$kind" --arg sid "$session" --arg inst "$install_id" \
    --arg repo "$repo" --arg branch "$branch" \
    --argjson extra "$extra" \
    '{ts:$ts, event:$ev, session:$sid, install:$inst, repo:$repo, branch:$branch} + $extra' \
    >>"$LOG_DIR/events-$(date -u +%Y-%m).jsonl" 2>/dev/null || true
}

# Path to the per-repo session pointer the git post-commit hook consults.
pointer=""
if [[ -n "$repo_root" ]]; then
  key="$(printf '%s' "$repo_root" | shasum | cut -c1-16)"
  pointer="$SESSION_DIR/$key.json"
fi

# Record a stage as having run in this session (idempotent, order-preserving).
add_stage() {
  local stage="$1"
  [[ -z "$pointer" || -z "$stage" ]] && return 0
  local tmp="$pointer.tmp.$$"
  jq -c --arg s "$stage" --arg sid "$session" --arg ts "$now" \
     '. as $d
      | ($d.stages // []) as $st
      | $d + {session:$sid, updated:$ts,
              stages: (if ($st | index($s)) then $st else $st + [$s] end)}' \
     "$pointer" >"$tmp" 2>/dev/null && mv -f "$tmp" "$pointer" 2>/dev/null
  rm -f "$tmp" 2>/dev/null
  return 0
}

# Map an agent/subagent name onto its pipeline stage slug. Anything not in this
# table is an ad-hoc skill, not a pipeline stage.
stage_for_agent() {
  case "${1##*:}" in
    requirements-analyst)   echo requirements ;;
    architecture-designer)  echo architecture ;;
    story-writer)           echo user-story ;;
    test-engineer)          echo test-specs ;;
    implementation)         echo code ;;
    code-reviewer)          echo code-review ;;
    ci-orchestrator)        echo build-test ;;
    deployer)               echo deploy-sandbox ;;
    *)                      echo "" ;;
  esac
}

case "$event" in

  SessionStart)
    # Resolve the harness identity recorded against each commit. When running as
    # an installed plugin CLAUDE_PLUGIN_ROOT points at the plugin; when running
    # from a working copy of this repo it does not, so fall back to the draft.
    harness="hmcts-sdlc-orchestrator@unknown"
    for manifest in \
      "${CLAUDE_PLUGIN_ROOT:-}/.claude-plugin/plugin.json" \
      "$(dirname "${BASH_SOURCE[0]}")/../../plugin-draft/hmcts-sdlc-orchestrator/.claude-plugin/plugin.json"
    do
      if [[ -n "$manifest" && -f "$manifest" ]]; then
        harness="$(jq -r '"\(.name)@\(.version)"' "$manifest" 2>/dev/null || echo "$harness")"
        break
      fi
    done

    if [[ -n "$pointer" ]]; then
      jq -c -n --arg sid "$session" --arg ts "$now" --arg h "$harness" \
        '{session:$sid, harness:$h, started:$ts, updated:$ts, stages:[]}' \
        >"$pointer" 2>/dev/null || true
    fi
    emit session_start "$(jq -c -n --arg src "$(jq -r '.source // "startup"' <<<"$input")" '{source:$src}')"
    ;;

  PostToolUse)
    tool="$(jq -r '.tool_name // empty' <<<"$input")"
    case "$tool" in
      Skill)
        name="$(jq -r '.tool_input.skill // empty' <<<"$input")"
        [[ -z "$name" ]] && exit 0
        emit skill_used "$(jq -c -n --arg n "$name" '{skill:$n}')"
        ;;
      Task|Agent)
        name="$(jq -r '.tool_input.subagent_type // .tool_input.description // empty' <<<"$input")"
        [[ -z "$name" ]] && exit 0
        stage="$(stage_for_agent "$name")"
        emit agent_used "$(jq -c -n --arg n "$name" --arg s "$stage" '{agent:$n, stage:$s}')"
        [[ -n "$stage" ]] && add_stage "$stage"
        ;;
      Write|Edit)
        # Only artefact writes are interesting, and only the fact of them.
        path="$(jq -r '.tool_input.file_path // empty' <<<"$input")"
        case "$path" in
          */docs/pipeline/*)
            kind="$(basename "$(dirname "$path")")"
            emit artefact_written "$(jq -c -n --arg k "$kind" --arg t "$tool" '{artefact:$k, tool:$t}')"
            ;;
        esac
        ;;
    esac
    ;;

  Stop)
    emit turn_end
    ;;

  SessionEnd)
    stages="[]"
    [[ -n "$pointer" && -f "$pointer" ]] && stages="$(jq -c '.stages // []' "$pointer" 2>/dev/null || echo '[]')"
    emit session_end "$(jq -c -n --argjson st "$stages" \
      --arg r "$(jq -r '.reason // empty' <<<"$input")" '{stages:$st, reason:$r}')"
    # Close the attribution window so later manual commits are not mis-tagged.
    [[ -n "$pointer" ]] && rm -f "$pointer" 2>/dev/null
    ;;

esac

exit 0
