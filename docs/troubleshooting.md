# Troubleshooting

Start with the exact error recorded in **Processing Pipeline**. Noosphere preserves failed jobs and article workspaces so a retry does not erase the evidence needed to diagnose the failure.

For a Docker deployment, collect the current service state and recent logs:

```bash
docker compose ps
docker compose logs --tail=100 noosphere postgres
curl http://localhost:8080/health
```

Do not paste API keys, SiYuan tokens, or an unmasked `config.json` into an issue or support message.

## Extraction Stops or Times Out

Symptoms include `couldn't get a connection after 30.00 sec`, an upstream HTTP status, or a pipeline row that remains **Needs attention**.

1. Expand the failed pipeline row and keep its upstream status and message.
2. In **Settings → Crawler**, test the configured primary crawler and verify the fallback is a different crawler or disabled.
3. Confirm the source URL is still reachable from the machine running Docker. Some platforms may reject a datacenter address while opening normally in a desktop browser.
4. Use **Retry** on the failed task after connectivity or crawler configuration is corrected. The failed run remains in history.

An extracted WeChat article may initially use a generic fallback title such as `微信公众号文章`. After a successful AI review, article lists prefer the reviewed document heading recovered from the content.

## AI Provider Returns 403 or Cannot Connect

A message such as `403 Forbidden` means the request reached the provider but was rejected; a connection timeout means it did not complete within the configured network window.

1. Open **Settings → AI provider** and test the exact provider profile used by the failed task.
2. Check the protocol and base URL together. An Anthropic Messages endpoint cannot be used as an OpenAI Chat Completions endpoint, and a complete request URL must not receive a second protocol path.
3. Re-enter the API key when it may have expired or lacks model access. Stored secrets remain masked and cannot be recovered through MCP.
4. Confirm the configured model is available to that account, then retry the task.

The text-review and image-review roles are independent. A provider working for text does not prove that its selected model accepts image input.

## Images Are Not Reviewed

If the pipeline reports images as unreviewed, Noosphere keeps them instead of guessing.

1. Mark image capability only on a model that actually supports image input.
2. Select that profile for the separate image-review role.
3. Test the provider profile before retrying the article.
4. Inspect the article workbench after review. Active and removed images remain reversible without changing `raw.md`.

A text-only profile can remain selected for article review while a different vision-capable profile handles images.

## SiYuan Upload Fails

1. Test the SiYuan connection in **Settings** using the same URL and token stored for the running deployment.
2. From Docker, `localhost` refers to the Noosphere container, not the host machine. Use a host address that the container can reach.
3. Verify that the target notebook still exists and that the token can create documents in it.
4. Retry upload after correcting connectivity or authorization. The reviewed article and its local assets remain available even when upload fails.

Noosphere does not import or inspect a separate note workspace. It sends the selected reviewed article only through the explicitly configured upload adapter.

## PostgreSQL Does Not Restart with Docker

Both Compose services use `restart: unless-stopped`. Starting the whole Compose project should bring PostgreSQL to a healthy state before Noosphere starts:

```bash
docker compose up -d postgres noosphere
docker compose ps
```

Both `noosphere-postgres` and `noosphere-mcp` should report `healthy`. If PostgreSQL was manually stopped, Docker honors that explicit stop until the project is started again. Start the Compose project rather than only the MCP container.

Taxonomy, operation history, recycle-bin records, and workflow checkpoints live in PostgreSQL. Article Markdown and images remain in the configured data directory, but database-backed features may temporarily degrade while PostgreSQL is unavailable.

## Docker Build Fails During Dependency Download

Package mirrors and browser dependency downloads can fail transiently. Preserve the full error, confirm normal network access, and retry the build:

```bash
docker compose build --no-cache noosphere
docker compose up -d
```

Use `--no-cache` only for recovery or release verification because it makes the next build substantially slower.
