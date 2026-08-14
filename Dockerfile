FROM node:22-slim AS web-builder

WORKDIR /web

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

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
COPY --from=web-builder /web/dist /app/frontend/dist

# Create a non-root user with a writable browser-cache directory.
RUN useradd -m -u 1000 noosphere && \
    mkdir -p /data /app/prompts && \
    chown -R noosphere:noosphere /data /app/prompts /home/noosphere

# Playwright installs OS packages through apt, which requires root. Retry each
# archive download before retrying the full idempotent install so one transient
# mirror 5xx does not force apt to fetch the whole dependency set again.
# Install the browser itself after switching users so its cache remains writable.
RUN printf '%s\n' \
        'Acquire::Retries "5";' \
        'Acquire::http::Pipeline-Depth "0";' \
        'Acquire::http::Timeout "30";' \
        > /etc/apt/apt.conf.d/80-noosphere-retries && \
    set -e; \
    for dependency_attempt in 1 2 3; do \
        if playwright install-deps chromium; then \
            break; \
        fi; \
        if [ "$dependency_attempt" = "3" ]; then \
            exit 1; \
        fi; \
    done

USER noosphere
RUN playwright install chromium

# Keep every direct-image entry point on the writable runtime volume, not the
# read-only application directory. Docker Compose already supplies these
# values, while standalone `docker run` calls need safe defaults as well.
ENV NOOSPHERE_HOME=/data \
    NOOSPHERE_CONFIG=/data/config.json

WORKDIR /app

# The entrypoint starts the MCP server by default.
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["mcp"]
