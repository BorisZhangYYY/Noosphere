#!/usr/bin/env bash

# Local helper for the Noosphere skill.
#
# This script is a convenience wrapper for local development and updates.
# It is NOT required for standard Claude Code usage.
#
# Standard installation:
#   npx skills add BorisZhangYYY/Noosphere --skill noosphere --agent claude-code
#
# You can also manually copy or symlink this skill into ~/.claude/skills/ or
# your workspace .claude/skills/ directory.

set -euo pipefail

# All work is done inside functions so that `source ./skill.sh noosphere`
# does not leak helper variables into the caller's shell.

_noosphere_skill_dir() {
  local script_path
  script_path="$(readlink -f "${BASH_SOURCE[0]}")"
  dirname "${script_path}"
}

_noosphere_skill_path() {
  local script_dir
  script_dir="$(_noosphere_skill_dir)"
  printf '%s\n' "${script_dir}/skills/noosphere/SKILL.md"
}

_noosphere_skill_source() {
  local script_dir
  script_dir="$(_noosphere_skill_dir)"
  printf '%s\n' "${script_dir}/skills/noosphere"
}

_noosphere_claude_target() {
  printf '%s\n' "${HOME}/.claude/skills/noosphere"
}

_noosphere_validate() {
  local script_dir
  script_dir="$(_noosphere_skill_dir)"
  bash "${script_dir}/skills/noosphere/scripts/validate_setup.sh"
}

_noosphere_update() {
  local script_dir skill_source claude_target tmp_target
  script_dir="$(_noosphere_skill_dir)"
  skill_source="$(_noosphere_skill_source)"
  claude_target="$(_noosphere_claude_target)"

  if [[ ! -d "${claude_target}" ]]; then
    printf 'Skill not installed at %s.\n' "${claude_target}"
    printf 'Install it with:\n'
    printf '  npx skills add BorisZhangYYY/Noosphere --skill noosphere --agent claude-code\n'
    printf 'Or symlink/copy manually from %s\n' "${skill_source}"
    return 0
  fi

  if [[ -L "${claude_target}" ]]; then
    local link_target
    link_target="$(readlink -f "${claude_target}")"
    if [[ "${link_target}" == "${skill_source}" ]]; then
      printf 'Symlinked skill already points to %s; no copy needed.\n' "${skill_source}"
      printf 'Run "git pull" in the project directory if you want the latest code.\n'
    else
      printf 'Symlink at %s points to %s, not %s.\n' "${claude_target}" "${link_target}" "${skill_source}"
      printf 'Leaving it untouched.\n'
    fi
    return 0
  fi

  if [[ ! -d "${claude_target}" ]]; then
    printf 'Warning: %s exists but is neither a symlink nor directory; leaving it untouched.\n' "${claude_target}" >&2
    return 1
  fi

  # Atomic replacement: copy to a temp directory next to the target, then swap.
  tmp_target="${claude_target}.tmp.$$"
  printf 'Re-copying skill from %s to %s\n' "${skill_source}" "${claude_target}"
  rm -rf "${tmp_target}"
  cp -R "${skill_source}" "${tmp_target}"
  rm -rf "${claude_target}.old"
  mv "${claude_target}" "${claude_target}.old"
  mv "${tmp_target}" "${claude_target}"
  rm -rf "${claude_target}.old"
  printf 'Skill updated at %s\n' "${claude_target}"
}

_noosphere_help() {
  local script_dir skill_source
  script_dir="$(_noosphere_skill_dir)"
  skill_source="$(_noosphere_skill_source)"

  cat <<EOF
Usage: ./skill.sh <command>

Commands:
  noosphere   Print the local skill path (backward compatibility).
  validate    Run local setup validation.
  update      Re-sync the copied skill at ~/.claude/skills/noosphere from this repo.
  help        Show this message.

Standard install:
  npx skills add BorisZhangYYY/Noosphere --skill noosphere --agent claude-code

Local install alternatives:
  # Symlink (always reflects project changes after git pull)
  ln -s "${skill_source}" ~/.claude/skills/noosphere

  # Copy (requires re-copy or ./skill.sh update to refresh)
  cp -R "${skill_source}" ~/.claude/skills/noosphere
EOF
}

_noosphere_main() {
  local command
  command="${1:-help}"

  case "${command}" in
    noosphere)
      # Backward-compatible path echo used by some local workflows.
      _noosphere_skill_path
      ;;
    validate)
      _noosphere_validate
      ;;
    update)
      _noosphere_update
      ;;
    help|--help|-h)
      _noosphere_help
      ;;
    *)
      printf 'Unknown command: %s\n' "${command}" >&2
      printf "Run './skill.sh help' for usage.\n" >&2
      exit 1
      ;;
  esac
}

# Run main only when executed, not when sourced.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  _noosphere_main "$@"
fi
