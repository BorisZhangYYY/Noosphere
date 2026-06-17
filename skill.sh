#!/usr/bin/env bash

# Local skill registry for Noosphere
set -euo pipefail

skill_name="${1:-}"

case "$skill_name" in
  noosphere)
    echo "skills/noosphere/SKILL.md"
    ;;
  "")
    echo "Usage: source ./skill.sh <skill-name>"
    echo "Available skills: noosphere"
    ;;
  *)
    echo "Unknown skill: $skill_name" >&2
    echo "Available skills: noosphere" >&2
    exit 1
    ;;
esac
