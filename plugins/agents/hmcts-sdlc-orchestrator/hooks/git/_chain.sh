#!/usr/bin/env bash
# Shared helpers for the harness git hooks. Sourced, never executed directly.
#
# The harness records which commits it helped produce in a LOCAL index
# (~/.cpp-harness/events/*.jsonl), keyed by commit SHA. Nothing is written into
# the commit message, so nothing about AI assistance appears in public git
# history. See docs/telemetry/attribution-index.md.

# ---------------------------------------------------------------------------
# chain_repo_hook <hook-name> [args...]
#
# Runs the repository's own hook of that name and propagates its exit status.
#
# core.hooksPath is a GLOBAL setting that overrides per-repo hooks, so without
# this the harness would silently disable husky and commitlint in every
# cpp-ui-* repo. Set CPP_HOOK_STDIN to a file path to feed the chained hook the
# stdin it expects (post-rewrite and pre-push both receive data there).
# ---------------------------------------------------------------------------
chain_repo_hook() {
  local name="$1"; shift
  local root candidate self_dir
  root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  [[ -n "$root" ]] || return 0
  # BASH_SOURCE[1] is the hook that sourced us, not this file.
  self_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" 2>/dev/null && pwd)" || return 0

  for candidate in "$root/.husky/$name" "$root/.git/hooks/$name"; do
    [[ -x "$candidate" ]] || continue
    # Never re-invoke ourselves if core.hooksPath resolves back to this dir.
    [[ "$(cd "$(dirname "$candidate")" && pwd)" == "$self_dir" ]] && continue
    if [[ -n "${CPP_HOOK_STDIN:-}" && -f "${CPP_HOOK_STDIN}" ]]; then
      "$candidate" "$@" <"$CPP_HOOK_STDIN" || return $?
    else
      "$candidate" "$@" </dev/null || return $?
    fi
    return 0
  done
  return 0
}

# ---------------------------------------------------------------------------
# harness_enabled
#
# True when telemetry is on and we are inside a git repo the harness knows
# about. Sets REPO_ROOT, INSTALL_ID, LOG_DIR, STATE_DIR.
#
# Deliberately does NOT require a live Claude session: rebases and pushes
# routinely happen hours after the session ended, and dropping those events
# would break the rewrite chain that keeps attribution attached to a commit.
# ---------------------------------------------------------------------------
harness_enabled() {
  [[ "${CPP_HARNESS_TELEMETRY:-on}" == "off" ]] && return 1
  [[ "${CPP_HOOKS_DISABLE:-0}" == "1" ]] && return 1
  command -v jq >/dev/null 2>&1 || return 1

  REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  [[ -n "$REPO_ROOT" ]] || return 1
  REPO_KEY="$(printf '%s' "$REPO_ROOT" | shasum | cut -c1-16)"

  STATE_DIR="${CPP_HARNESS_STATE_DIR:-$HOME/.cpp-harness}"
  [[ -d "$STATE_DIR" ]] || return 1          # harness never ran here
  LOG_DIR="$STATE_DIR/events"
  mkdir -p "$LOG_DIR" 2>/dev/null || return 1

  # Lower-cased: uuidgen is uppercase on macOS, lowercase elsewhere, and one
  # installation must not appear as two ids in an aggregated report.
  INSTALL_ID="$(tr -cd 'a-fA-F0-9' <"$STATE_DIR/installation-id" 2>/dev/null \
                | tr 'A-F' 'a-f' | cut -c1-12)"
  HARNESS_SESSION=""
  HARNESS_NAME=""
  HARNESS_STAGES="[]"
  return 0
}

# ---------------------------------------------------------------------------
# harness_session
#
# harness_enabled, plus a live session pointer for this repo. Only commits made
# while a session is open are attributed, so this is the stricter gate that
# post-commit uses. Additionally sets HARNESS_SESSION, HARNESS_NAME,
# HARNESS_STAGES.
# ---------------------------------------------------------------------------
harness_session() {
  harness_enabled || return 1
  local pointer ttl
  pointer="$STATE_DIR/by-repo/$REPO_KEY.json"
  [[ -f "$pointer" ]] || return 1

  # SessionEnd deletes the pointer, but a crashed session leaves it behind.
  # Anything older than the TTL is not trusted to still represent live work.
  ttl="${CPP_HARNESS_SESSION_TTL_HOURS:-8}"
  [[ -n "$(find "$pointer" -mmin +$((ttl * 60)) 2>/dev/null)" ]] && return 1

  HARNESS_SESSION="$(jq -r '.session // empty' "$pointer" 2>/dev/null)"
  HARNESS_NAME="$(jq -r '.harness // empty' "$pointer" 2>/dev/null)"
  HARNESS_STAGES="$(jq -c '.stages // []' "$pointer" 2>/dev/null || echo '[]')"
  [[ -n "$HARNESS_SESSION" && -n "$HARNESS_NAME" ]] || return 1
  return 0
}

# ---------------------------------------------------------------------------
# emit_event <json-object>
#
# Appends one record to the monthly event log. Repo BASENAME only — an absolute
# path contains /Users/<name>/ and would identify a person.
# ---------------------------------------------------------------------------
emit_event() {
  local branch
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
  jq -c -n \
    --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg sid "${HARNESS_SESSION:-}" \
    --arg inst "${INSTALL_ID:-}" \
    --arg repo "$(basename "$REPO_ROOT")" \
    --arg branch "$branch" \
    --argjson extra "$1" \
    '{ts:$ts, session:$sid, install:$inst, repo:$repo, branch:$branch} + $extra' \
    >>"$LOG_DIR/events-$(date -u +%Y-%m).jsonl" 2>/dev/null || true
}
