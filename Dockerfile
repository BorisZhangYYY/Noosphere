FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies for packages that need compilation.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy source and install the package in editable mode.
COPY --chown=root:root . /app
RUN pip install --no-cache-dir -e /app

# --- Runtime image ---
FROM python:3.11-slim

WORKDIR /app

# Keep runtime lean; copy installed site-packages and binaries from builder.
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Create a non-root user and writable directories.
RUN useradd -m -u 1000 noosphere && \
    mkdir -p /app/data /app/outputs /app/prompts /app/.noosphere && \
    chown -R noosphere:noosphere /app/data /app/outputs /app/prompts /app/.noosphere

# Install Playwright Chromium browser and system dependencies as runtime user.
# Doing this in the runtime stage ensures the browser cache is writable and the
# required shared libraries are present in the final image.
USER noosphere
RUN playwright install chromium && playwright install-deps chromium

WORKDIR /app

# The entrypoint starts the MCP server by default.
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["mcp"]
