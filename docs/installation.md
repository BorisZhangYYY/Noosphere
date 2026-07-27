# Installation and Deployment

Noosphere exposes one business system through three interfaces. A Docker deployment serves both the web workspace and MCP endpoint; the local Python installation provides the CLI and can also start the MCP service.

## Requirements

- Python 3.11 or newer for local CLI development.
- Docker with the Compose plugin for the complete service stack.
- Network access to the selected crawler and AI provider.
- A SiYuan instance only when SiYuan upload is enabled.

## Local CLI

```bash
git clone https://github.com/BorisZhangYYY/Noosphere.git
cd Noosphere
python -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
cp config.json.example config.json
nsphr --help
```

Edit `config.json` before running AI review, Firecrawl, or SiYuan upload. Local development defaults to SQLite and writes article workspaces beneath `outputs/` unless configured otherwise.

## Docker: Web and MCP

```bash
git clone https://github.com/BorisZhangYYY/Noosphere.git
cd Noosphere
docker compose up -d --build
docker compose ps
curl http://localhost:8080/health
```

Available endpoints:

- Web workspace: `http://localhost:8080/app/`
- MCP SSE endpoint: `http://localhost:8080/sse`
- Health check: `http://localhost:8080/health`
- PostgreSQL host port: `5432`

The Compose stack builds `noosphere:latest` locally. To use the published image instead, remove the `build:` block in `docker-compose.yml` and configure:

```yaml
image: ghcr.io/boriszhangyyy/noosphere:latest
```

### PostgreSQL in Docker

PostgreSQL is required by the Docker Compose deployment. It stores workflow checkpoints, taxonomy assignments, operation history, and recycle-bin records; article Markdown and images remain portable files in the mounted data directory.

If PostgreSQL is stopped after Noosphere has already started, the web service process can remain visible because Compose only enforces dependency order during startup. Article files remain readable, while database-backed metadata temporarily degrades or becomes unavailable. Restart the complete stack with:

```bash
docker compose up -d postgres noosphere
docker compose ps
```

Both `noosphere-postgres` and `noosphere-mcp` should report `healthy`.

## Persistent Data Directory

The default host directory is `.noosphere/`. To bind a different directory:

```bash
NOOSPHERE_DATA_DIR=/absolute/path/to/noosphere-data docker compose up -d --build
```

The directory holds PostgreSQL data, application configuration, article workspaces and assets, logs, archives, caches, and backups. Back up this directory as one unit.

## Local MCP Development

With the Python package installed:

```bash
nsphr mcp --host 127.0.0.1 --port 8080
```

This is useful for development, but the Docker stack is the recommended way to run PostgreSQL and all crawler dependencies together.

## Stop or Update

Stop services without deleting the bound data directory:

```bash
docker compose down
```

Rebuild after updating the source checkout:

```bash
git pull
docker compose up -d --build
```

Do not delete `.noosphere/` or a custom `NOOSPHERE_DATA_DIR` unless the stored configuration, articles, and database are no longer needed.
