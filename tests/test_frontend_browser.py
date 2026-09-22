"""Opt-in browser regression against the built app and an isolated real server.

Run: NOOSPHERE_BROWSER_TESTS=1 python -m pytest tests/test_frontend_browser.py -q
"""
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

pytestmark = pytest.mark.skipif(os.getenv("NOOSPHERE_BROWSER_TESTS") != "1", reason="Opt-in browser test requires built frontend and Playwright Chromium")


@pytest.fixture
def browser_server(tmp_path, monkeypatch):
    directory = tmp_path / "articles" / "browser_article"
    directory.mkdir(parents=True)
    for name in ("raw.md", "reviewed.md"):
        (directory / name).write_text("# Browser article\n\nOriginal paragraph.\n")
    manifest = {"article_id": directory.name, "article": {"title": "Browser article", "url": "https://example.test/article", "author": "Author", "platform": "wechat_mp", "captured_at": "2026-09-18T00:00:00Z"}, "paths": {"raw": "raw.md", "reviewed": "reviewed.md", "assets": "assets"}}
    (directory / "manifest.json").write_text(json.dumps(manifest))
    config = tmp_path / "browser-config.json"
    config.write_text(json.dumps({"output_dir": str(directory.parent), "checkpoint": {"backend": "sqlite"}}))
    monkeypatch.setenv("NOOSPHERE_CONFIG", str(config))
    monkeypatch.setenv("NOOSPHERE_ACCESS_TOKEN", "browser-test-token")
    with socket.socket() as socket_:
        socket_.bind(("127.0.0.1", 0))
        port = socket_.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    with (tmp_path / "server.log").open("w") as log:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "src.mcp.server:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port), "--no-proxy-headers"], stdout=log, stderr=log)
        try:
            for _ in range(100):
                try:
                    urllib.request.urlopen(base + "/health", timeout=1).close()
                    break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError((tmp_path / "server.log").read_text())
                    time.sleep(0.05)
            else:
                raise RuntimeError("Browser test server did not start")
            yield base, directory
        finally:
            process.terminate()
            process.wait(timeout=10)


@pytest.mark.asyncio
async def test_drafts_survive_dialog_refresh_and_save_then_conflict(browser_server):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(http_credentials={"username": "noosphere", "password": "browser-test-token"}, viewport={"width": 1440, "height": 1000})
        await context.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(base + "/app/#/articles/browser_article")
        await page.get_by_role("button", name="Edit", exact=True).click()
        editor = page.locator('.vditor-wysiwyg [contenteditable="true"]')
        await expect(editor).to_be_visible()
        await editor.click()
        await page.keyboard.press("ControlOrMeta+End")
        await page.keyboard.insert_text(" UNSAVED_MARKER")
        await page.get_by_role("button", name="Write reflection", exact=True).first.click()
        await page.get_by_role("button", name="Close reflection dialog", exact=True).click()
        await expect(editor).to_contain_text("UNSAVED_MARKER")
        await page.get_by_role("button", name="Sync content mirror").click()
        await expect(editor).to_contain_text("UNSAVED_MARKER")

        pending = asyncio.Event()
        release = asyncio.Event()
        async def delay_save(route):
            if route.request.method != "PATCH":
                await route.continue_()
                return
            response = await route.fetch()
            pending.set()
            await release.wait()
            await route.fulfill(response=response)
        await page.route("**/api/v1/articles/browser_article", delay_save)
        await page.get_by_role("button", name="Save reviewed Markdown", exact=True).click()
        await asyncio.wait_for(pending.wait(), timeout=10)
        await editor.click()
        await page.keyboard.press("ControlOrMeta+End")
        await page.keyboard.insert_text(" TYPED_DURING_SAVE")
        release.set()
        await expect(page.get_by_role("button", name="Save reviewed Markdown", exact=True)).to_be_enabled()
        await expect(editor).to_contain_text("TYPED_DURING_SAVE")
        await page.unroute("**/api/v1/articles/browser_article", delay_save)
        assert "UNSAVED_MARKER" in (directory / "reviewed.md").read_text()
        assert "TYPED_DURING_SAVE" not in (directory / "reviewed.md").read_text()

        detail = await (await context.request.get(base + "/api/v1/articles/browser_article")).json()
        other = await context.request.patch(base + "/api/v1/articles/browser_article", data={"reviewedMarkdown": "# Other window\n", "expectedRevision": detail["revision"]})
        assert other.status == 200
        await page.get_by_role("button", name="Save reviewed Markdown", exact=True).click()
        await expect(page.get_by_role("alert").filter(has_text="Article changed")).to_be_visible()
        await expect(editor).to_contain_text("TYPED_DURING_SAVE")
        assert "Other window" in (directory / "reviewed.md").read_text()
        assert not errors, errors
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("language,theme,width", [("en", "light", 1440), ("zh", "dark", 1024), ("en", "dark", 390)])
async def test_reading_layout_and_theme_remain_usable(browser_server, tmp_path, language, theme, width):
    from playwright.async_api import async_playwright, expect
    base, _ = browser_server
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(http_credentials={"username": "noosphere", "password": "browser-test-token"}, viewport={"width": width, "height": 900})
        await context.add_init_script(f"localStorage.setItem('noosphere-language', '{language}'); localStorage.setItem('noosphere-theme', '{theme}')")
        page = await context.new_page()
        await page.goto(base + "/app/#/articles/browser_article")
        await expect(page.locator('.reader-surface')).to_contain_text("Original paragraph.")
        await expect(page.locator('html')).to_have_attribute("lang", "zh-CN" if language == "zh" else "en")
        await expect(page.locator('.radix-themes')).to_have_class(__import__('re').compile(theme))
        assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        await page.screenshot(path=str(tmp_path / f"reader-{language}-{theme}-{width}.png"), full_page=True)
        await browser.close()


def test_authenticated_remote_mcp_stream_uses_shared_access_control(browser_server):
    import httpx
    base, _ = browser_server
    with httpx.stream("GET", base + "/sse", headers={"Authorization": "Bearer browser-test-token", "Host": "noosphere.example"}, timeout=5, trust_env=False) as response:
        assert response.status_code == 200
        assert next(response.iter_lines()) == "event: endpoint"


@pytest.mark.asyncio
async def test_search_and_batch_workspace(browser_server, tmp_path):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(http_credentials={"username": "noosphere", "password": "browser-test-token"}, viewport={"width": 1280, "height": 900})
        await context.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        page = await context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(base + '/app/#/search?q=Original')
        await expect(page.get_by_role('heading', name='Full-text search')).to_be_visible()
        await expect(page.locator('.search-result')).to_have_count(1)
        await expect(page.locator('.search-passage mark').first).to_be_visible()
        await page.get_by_role('link', name='Open passage').first.click()
        await expect(page.get_by_role('region', name='Search passage context')).to_contain_text('Original paragraph')
        await page.goto(base + '/app/#/batches')
        await page.locator('textarea').fill('https://example.test/article\nhttps://example.test/article#duplicate\ninvalid-url')
        await page.get_by_role('button', name='Check URLs', exact=True).click()
        await expect(page.locator('.batch-preview')).to_contain_text('Already captured')
        await expect(page.locator('.batch-preview')).to_contain_text('Invalid URL')
        await page.get_by_role('button', name='Start batch', exact=True).click()
        await expect(page.locator('.batch-table tbody tr')).to_have_count(3)
        await expect(page.locator('.batch-table')).to_contain_text('Skipped')
        await page.screenshot(path=str(tmp_path / 'batch-desktop.png'), full_page=True)
        await page.set_viewport_size({'width': 390, 'height': 844})
        await page.goto(base + '/app/#/search?q=Original')
        await expect(page.locator('.search-result')).to_have_count(1)
        assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        await page.screenshot(path=str(tmp_path / 'search-mobile.png'), full_page=True)
        assert not errors
        await browser.close()
