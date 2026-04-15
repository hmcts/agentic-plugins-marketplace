#!/usr/bin/env bash
# Agentic Plugins Marketplace — installer
#
# Usage:
#   ./scripts/install.sh                          # interactive list + pick
#   ./scripts/install.sh mcp-servers/github       # install by path
#   ./scripts/install.sh skills/code-review
#   ./scripts/install.sh hooks/notify-on-stop
#   ./scripts/install.sh templates/python-project --target /path/to/project
#
# Options:
#   --target <dir>   For template plugins: directory where CLAUDE.md is written
#                    (defaults to current working directory)
#   --dry-run        Print what would be done without making any changes
#   --help           Show this message

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGINS_DIR="${REPO_ROOT}/plugins"
CLAUDE_DIR="${HOME}/.claude"
SETTINGS_FILE="${CLAUDE_DIR}/settings.json"
SKILLS_DIR="${CLAUDE_DIR}/skills"
HOOKS_DIR="${CLAUDE_DIR}/hooks"

DRY_RUN=false
TARGET_DIR="${PWD}"
PLUGIN_PATH=""

# ── helpers ──────────────────────────────────────────────────────────────────

log()  { echo "[install] $*"; }
err()  { echo "[install] ERROR: $*" >&2; exit 1; }
dry()  { if $DRY_RUN; then echo "[dry-run] $*"; else eval "$*"; fi; }

require_cmd() {
  command -v "$1" &>/dev/null || err "Required command not found: $1. Please install it and retry."
}

require_jq() { require_cmd jq; }

read_manifest() {
  local plugin_dir="$1"
  local manifest="${plugin_dir}/plugin.json"
  [[ -f "${manifest}" ]] || err "No plugin.json found in ${plugin_dir}"
  cat "${manifest}"
}

# ── argument parsing ──────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)   DRY_RUN=true; shift ;;
    --target)    TARGET_DIR="$2"; shift 2 ;;
    --help|-h)
      grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' | tail -n +2
      exit 0
      ;;
    *)
      [[ -z "${PLUGIN_PATH}" ]] || err "Unexpected argument: $1"
      PLUGIN_PATH="$1"
      shift
      ;;
  esac
done

# ── interactive mode ──────────────────────────────────────────────────────────

if [[ -z "${PLUGIN_PATH}" ]]; then
  echo ""
  echo "Available plugins:"
  echo ""
  find "${PLUGINS_DIR}" -name "plugin.json" | sort | while read -r manifest; do
    dir="$(dirname "${manifest}")"
    rel="${dir#"${PLUGINS_DIR}/"}"
    desc="$(jq -r '.description' "${manifest}" 2>/dev/null || echo '(no description)')"
    printf "  %-40s %s\n" "${rel}" "${desc}"
  done
  echo ""
  read -rp "Plugin to install (e.g. mcp-servers/github): " PLUGIN_PATH
  [[ -n "${PLUGIN_PATH}" ]] || err "No plugin selected."
fi

# ── resolve plugin directory ──────────────────────────────────────────────────

PLUGIN_DIR="${PLUGINS_DIR}/${PLUGIN_PATH}"
[[ -d "${PLUGIN_DIR}" ]] || err "Plugin not found: ${PLUGIN_PATH}"

require_jq
MANIFEST="$(read_manifest "${PLUGIN_DIR}")"

NAME="$(echo "${MANIFEST}" | jq -r '.name')"
TYPE="$(echo "${MANIFEST}" | jq -r '.type')"
DESC="$(echo "${MANIFEST}" | jq -r '.description')"

log "Installing plugin: ${NAME} (${TYPE})"
log "${DESC}"
echo ""

# ── install by type ───────────────────────────────────────────────────────────

install_mcp_server() {
  require_cmd claude

  local transport command args env_block
  transport="$(echo "${MANIFEST}" | jq -r '.mcp.transport')"
  command="$(echo "${MANIFEST}" | jq -r '.mcp.command // empty')"
  args="$(echo "${MANIFEST}" | jq -r '(.mcp.args // []) | join(" ")')"

  # Build env flags
  local env_flags=""
  while IFS="=" read -r key value; do
    if [[ "${value}" == \$\{*\} ]]; then
      # Value is a placeholder — resolve from environment
      var_name="${value:2:-1}"
      actual="${!var_name:-}"
      if [[ -z "${actual}" ]]; then
        echo "[install] WARNING: Environment variable ${var_name} is not set."
        echo "[install]          Set it before installing, or add it manually afterwards."
      fi
      env_flags+=" -e ${key}=${actual}"
    else
      env_flags+=" -e ${key}=${value}"
    fi
  done < <(echo "${MANIFEST}" | jq -r '(.mcp.env // {}) | to_entries[] | "\(.key)=\(.value)"')

  local claude_cmd="claude mcp add ${NAME}${env_flags} -- ${command} ${args}"
  log "Running: ${claude_cmd}"
  dry "${claude_cmd}"
  log "MCP server '${NAME}' installed. Restart Claude Code to activate it."
}

install_skill() {
  local skill_file trigger
  skill_file="$(echo "${MANIFEST}" | jq -r '.skill.file')"
  trigger="$(echo "${MANIFEST}" | jq -r '.skill.trigger // .name')"

  mkdir -p "${SKILLS_DIR}"
  local dest="${SKILLS_DIR}/${trigger}.md"
  log "Copying skill to ${dest}"
  dry "cp '${PLUGIN_DIR}/${skill_file}' '${dest}'"
  log "Skill '/${trigger}' installed. It will be available in your next Claude Code session."
}

install_hook() {
  local event hook_command hook_script_src hook_script_name
  event="$(echo "${MANIFEST}" | jq -r '.hook.event')"
  hook_command="$(echo "${MANIFEST}" | jq -r '.hook.command')"
  hook_script_name="$(basename "${hook_command}")"

  # Copy the hook script if one exists in the plugin dir
  local script_src
  script_src="$(find "${PLUGIN_DIR}" -name "*.sh" | head -1)"
  if [[ -n "${script_src}" ]]; then
    mkdir -p "${HOOKS_DIR}"
    local dest="${HOOKS_DIR}/${hook_script_name}"
    log "Copying hook script to ${dest}"
    dry "cp '${script_src}' '${dest}'"
    dry "chmod +x '${dest}'"
  fi

  # Merge into settings.json
  log "Updating ${SETTINGS_FILE}"
  if $DRY_RUN; then
    echo "[dry-run] Would add ${event} hook to ${SETTINGS_FILE}"
    return
  fi

  mkdir -p "${CLAUDE_DIR}"
  if [[ ! -f "${SETTINGS_FILE}" ]]; then
    echo '{}' > "${SETTINGS_FILE}"
  fi

  local expanded_command="${hook_command/\~/${HOME}}"
  local new_hook_entry
  new_hook_entry="$(jq -n \
    --arg event "${event}" \
    --arg cmd "${expanded_command}" \
    '{"type":"command","command":$cmd}')"

  # Use jq to safely merge the new hook into the existing settings
  local updated
  updated="$(jq \
    --arg event "${event}" \
    --argjson entry "${new_hook_entry}" \
    '
      .hooks //= {}
      | .hooks[$event] //= [{"hooks":[]}]
      | .hooks[$event][0].hooks += [$entry]
    ' "${SETTINGS_FILE}")"
  echo "${updated}" > "${SETTINGS_FILE}"
  log "Hook '${NAME}' registered for event: ${event}"
}

install_template() {
  local template_file target_path
  template_file="$(echo "${MANIFEST}" | jq -r '.template.file')"
  target_path="$(echo "${MANIFEST}" | jq -r '.template.targetPath // "CLAUDE.md"')"

  local dest="${TARGET_DIR}/${target_path}"
  if [[ -f "${dest}" ]]; then
    log "WARNING: ${dest} already exists. A backup will be created."
    dry "cp '${dest}' '${dest}.bak'"
  fi
  log "Copying template to ${dest}"
  dry "cp '${PLUGIN_DIR}/${template_file}' '${dest}'"
  log "Template installed at ${dest}. Open it and fill in your project-specific details."
}

case "${TYPE}" in
  mcp-server) install_mcp_server ;;
  skill)      install_skill ;;
  hook)       install_hook ;;
  template)   install_template ;;
  *)          err "Unknown plugin type: ${TYPE}" ;;
esac

echo ""
log "Done."
