#!/usr/bin/env bash
set -euo pipefail

# Default to starting the MCP server if no command is provided.
CMD="${1:-mcp}"

if [ "$CMD" = "mcp" ]; then
    echo "Starting Noosphere MCP server on port ${MCP_PORT:-8080}..."
    exec python3 -m src.mcp.server
fi

# Fall back to the provided command (useful for debugging).
exec "$@"
