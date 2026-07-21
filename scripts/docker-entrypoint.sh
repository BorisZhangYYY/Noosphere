#!/usr/bin/env bash
set -euo pipefail

# Default to starting the MCP server if no command is provided.
CMD="${1:-mcp}"

DATA_DIR="${NOOSPHERE_HOME:-/data}"
CONFIG_PATH="${NOOSPHERE_CONFIG:-$DATA_DIR/config.json}"
mkdir -p "$DATA_DIR/articles" "$DATA_DIR/archive" "$DATA_DIR/cache/crawl4ai" "$DATA_DIR/backups" "$DATA_DIR/logs"

if [ ! -f "$CONFIG_PATH" ]; then
    cp /app/config.json.example "$CONFIG_PATH"
    chmod 600 "$CONFIG_PATH"
    echo "Created default configuration at $CONFIG_PATH"
fi

if [ "$CMD" = "mcp" ]; then
    echo "Starting Noosphere MCP and web service on port ${MCP_PORT:-8080}..."
    exec python3 -m src.mcp.server
fi

# Fall back to the provided command (useful for debugging).
exec "$@"
