#!/usr/bin/env bash
# Validate local Noosphere setup before running commands.
# This script can be run from any directory.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Derive the project root from this script's location:
# skills/noosphere/scripts/validate_setup.sh -> project root.
script_path="$(readlink -f "${BASH_SOURCE[0]}")"
script_dir="$(dirname "${script_path}")"
project_root="$(cd "${script_dir}/../../.." && pwd)"
config_file="${project_root}/config.json"

errors=0

_print() {
    printf '%b\n' "$1"
}

_print "Noosphere setup validation"
_print "=========================="
_print ""

# 1. Python
if command -v python3 >/dev/null 2>&1; then
    py_version="$(python3 --version)"
    _print "${GREEN}✓${NC} python3 found: ${py_version}"
else
    _print "${RED}✗${NC} python3 not found in PATH"
    errors=$((errors + 1))
fi

# 2. nsphr command
if command -v nsphr >/dev/null 2>&1; then
    _print "${GREEN}✓${NC} nsphr command found"
else
    _print "${YELLOW}!${NC} nsphr command not found. Run: pip install -e ."
    errors=$((errors + 1))
fi

# 3. config.json
if [[ -f "${config_file}" ]]; then
    _print "${GREEN}✓${NC} config.json exists"
    if python3 -m json.tool "${config_file}" > /dev/null 2>&1; then
        _print "${GREEN}✓${NC} config.json is valid JSON"
    else
        _print "${RED}✗${NC} config.json is not valid JSON"
        errors=$((errors + 1))
    fi
else
    _print "${YELLOW}!${NC} config.json not found at ${config_file}. Copy from config.json.example and customize."
    errors=$((errors + 1))
fi

# 4. Required config fields (best-effort, non-blocking warnings)
if [[ -f "${config_file}" ]] && python3 -m json.tool "${config_file}" > /dev/null 2>&1; then
    config_check=$(python3 - <<PYEOF "${config_file}"
import json
import sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    c = json.load(f)

ai = c.get("ai", {})
provider = ai.get("provider", "")
ai_providers = c.get("ai_providers", {})

print("ai_provider_present:", bool(provider))
print("provider_in_ai_providers:", provider in ai_providers)
print("has_upload_target:", "siyuan" in c or "local_archive" in c)
PYEOF
    )

    if [[ "${config_check}" == *"ai_provider_present: True"* ]]; then
        _print "${GREEN}✓${NC} ai.provider configured"
    else
        _print "${YELLOW}!${NC} ai.provider not configured"
    fi

    if [[ "${config_check}" == *"provider_in_ai_providers: True"* ]]; then
        _print "${GREEN}✓${NC} ai_providers includes the configured provider"
    else
        _print "${YELLOW}!${NC} ai_providers missing entry for configured provider"
    fi

    if [[ "${config_check}" == *"has_upload_target: True"* ]]; then
        _print "${GREEN}✓${NC} At least one upload target configured (siyuan or local_archive)"
    else
        _print "${YELLOW}!${NC} No upload target configured (add siyuan or local_archive)"
    fi
fi

_print ""
if [[ "${errors}" -eq 0 ]]; then
    _print "${GREEN}Validation passed.${NC}"
    exit 0
else
    _print "${RED}Validation failed with ${errors} error(s).${NC}"
    exit 1
fi
