"""Opt-in browser regression against the built app and an isolated real server.

Run: NOOSPHERE_BROWSER_TESTS=1 python -m pytest tests/test_frontend_browser.py -q
"""
import asyncio
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

pytestmark = pytest.mark.skipif(os.getenv("NOOSPHERE_BROWSER_TESTS") != "1", reason="Opt-in browser test requires built frontend and Playwright Chromium")


async def sign_in(page, token="browser-test-token"):
    """Authenticate through the same in-app flow used by a real browser."""
    field = page.locator('.login-page input[type="password"]')
    await field.wait_for()
    await field.fill(token)
    await page.locator('.login-page button[type="submit"]').click()
    await page.locator(".app-root").wait_for()


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
        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        await context.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(base + "/app/#/articles/browser_article")
        await sign_in(page)
        await page.get_by_role("button", name="Edit", exact=True).click()
        editor = page.locator('.vditor-wysiwyg [contenteditable="true"]')
        await expect(editor).to_be_visible()
        await editor.click()
        await page.keyboard.press("ControlOrMeta+End")
        await page.keyboard.insert_text(" UNSAVED_MARKER")
        await page.get_by_role("button", name="Write reflection", exact=True).first.click()
        await page.get_by_role("button", name="Close reflection dialog", exact=True).click()
        await expect(editor).to_contain_text("UNSAVED_MARKER")
        await page.get_by_role("button", name="Article text backup", exact=True).click()
        await page.get_by_role("button", name="Refresh text copy", exact=True).click()
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
async def test_structural_blocks_drag_history_selection_and_save(browser_server, tmp_path):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    quote = '> 写作时专注内容，需要时再调整顺序。'
    table = '| 操作 | 使用方式 |\n| :--- | ---: |\n| 拖动 | 抓住块左侧手柄 |\n| 键盘 | Alt + 上下方向键 |'
    code = '~~~js\n// Keep this blank line.\n\nconsole.log("body")\n~~~'
    markdown = '\n\n'.join(['# Browser article', 'Lead.', quote, table, code, 'Tail.']) + '\n'
    (directory / 'reviewed.md').write_text(markdown)
    original_raw = (directory / 'raw.md').read_bytes()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 1100})
        await page.add_init_script("localStorage.setItem('noosphere-language', 'zh')")
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(base + '/app/#/articles/browser_article')
        await sign_in(page)
        await page.locator('.editor-mode-toggle button').nth(1).click()
        root = page.locator('.vditor-wysiwyg > .vditor-reset')
        cell = root.locator(':scope > table td').first
        await cell.evaluate("element => { element.closest('.vditor-reset').focus(); const range = document.createRange(); range.selectNodeContents(element); const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); }")
        await cell.hover()
        handle = page.locator('.noosphere-block-handle')
        await expect(handle).to_be_visible()
        bounds = await handle.bounding_box()
        target = await root.locator(':scope > p').filter(has_text='Tail.').bounding_box()
        await page.mouse.move(bounds['x'] + 10, bounds['y'] + 14)
        await page.mouse.down()
        await page.mouse.move(target['x'] + 70, target['y'] + target['height'] - 2, steps=12)
        await expect(page.locator('.noosphere-image-drop-line')).to_be_visible()
        await page.mouse.up()
        order = "() => { const nodes = [...document.querySelector('.vditor-wysiwyg > .vditor-reset').children]; return nodes.findIndex(n => n.tagName === 'TABLE') > nodes.findIndex(n => n.textContent === 'Tail.'); }"
        await page.wait_for_function(order)
        assert await page.evaluate('window.getSelection().toString()') == '拖动'
        await root.focus()
        await page.keyboard.press('ControlOrMeta+z')
        await page.wait_for_function("() => document.querySelector('.vditor-wysiwyg > .vditor-reset').children[3].tagName === 'TABLE'")
        await page.keyboard.press('ControlOrMeta+y')
        await page.wait_for_function(order)
        for selector in [':scope > blockquote', ':scope > div[data-type="code-block"]']:
            await root.locator(selector).hover()
            await expect(handle).to_be_visible()
            await handle.focus()
            await page.keyboard.press('Alt+ArrowUp')
        await page.locator('.article-save-button').click()
        await expect(page.locator('.article-save-state')).to_have_text('已保存')
        saved = (directory / 'reviewed.md').read_text()
        for block in [quote, table, code]:
            assert block in saved
        assert saved.index(quote) < saved.index(code) < saved.index('Lead.') < saved.index('Tail.') < saved.index(table)
        assert (directory / 'raw.md').read_bytes() == original_raw
        await page.screenshot(path=str(tmp_path / 'structural-blocks.png'), full_page=True)
        await page.reload()
        await expect(root.locator(':scope > table td')).to_have_count(4)
        await page.wait_for_function(order)
        await expect(page.locator('.noosphere-block-controls')).to_be_hidden()
        assert not errors, errors
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('touch', [False, True])
async def test_list_item_and_whole_list_scopes(browser_server, tmp_path, touch):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    listing = '- [x] 第一项 **重点**\n  - 子项甲\n  - 子项乙\n- [ ] 第二项\n- [ ] 第三项'
    (directory / 'reviewed.md').write_text('# Browser article\n\nLead.\n\n' + listing + '\n\nTail.\n')
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={'width': 390 if touch else 1440, 'height': 1000}, has_touch=touch)
        await page.add_init_script("localStorage.setItem('noosphere-language', 'zh')")
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(base + '/app/#/articles/browser_article')
        await sign_in(page)
        await page.locator('.editor-mode-toggle button').nth(1).click()
        root = page.locator('.vditor-wysiwyg > .vditor-reset')
        items = root.locator(':scope > ul > li')
        first = items.filter(has_text='第一项')
        await first.evaluate("element => { element.closest('.vditor-reset').focus(); const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT); let node; while ((node = walker.nextNode()) && !node.textContent.includes('第一项')) {} const start = node.textContent.indexOf('第一项'); const range = document.createRange(); range.setStart(node, start); range.setEnd(node, start + 3); const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); }")
        if not touch:
            await first.hover(position={'x': 70, 'y': 10})
        handle = page.locator('.noosphere-block-handle')
        await expect(handle).to_be_visible()
        outline = await page.locator('.noosphere-block-boundary').bounding_box()
        list_bounds = await root.locator(':scope > ul').bounding_box()
        handle_bounds = await handle.bounding_box()
        assert outline['x'] <= list_bounds['x']
        assert handle_bounds['x'] + handle_bounds['width'] <= outline['x'] + 1
        if touch:
            await handle.tap()
            await page.get_by_role('button', name='下移块', exact=True).tap()
        else:
            bounds = await handle.bounding_box()
            target = await items.filter(has_text='第二项').bounding_box()
            await page.mouse.move(bounds['x'] + 10, bounds['y'] + 14, steps=15)
            await page.mouse.down()
            await page.mouse.move(target['x'] + 70, target['y'] + target['height'] - 2, steps=8)
            await expect(page.locator('.noosphere-image-drop-line')).to_be_visible()
            await page.mouse.up()
        await expect(items.nth(1)).to_contain_text('第一项')
        await expect(items.nth(1).locator(':scope > ul > li')).to_have_count(2)
        assert await page.evaluate('window.getSelection().toString()') == '第一项'
        await root.focus()
        await page.keyboard.press('ControlOrMeta+z')
        await expect(items.first).to_contain_text('第一项')
        await page.keyboard.press('ControlOrMeta+y')
        await expect(items.nth(1)).to_contain_text('第一项')
        child = items.nth(1).locator(':scope > ul > li').first
        if touch:
            await child.tap()
            await handle.tap()
            await page.get_by_role('button', name='下移块', exact=True).tap()
        else:
            await child.hover()
            outline = await page.locator('.noosphere-block-boundary').bounding_box()
            list_bounds = await items.nth(1).locator(':scope > ul').bounding_box()
            handle_bounds = await handle.bounding_box()
            assert outline['x'] <= list_bounds['x']
            assert handle_bounds['x'] + handle_bounds['width'] <= outline['x'] + 1
            await handle.focus()
            await page.keyboard.press('Alt+ArrowDown')
        await expect(items.nth(1).locator(':scope > ul > li').first).to_contain_text('子项乙')
        outer = page.locator('.noosphere-container-handle')
        await expect(outer).to_be_visible()
        await expect(handle).to_be_visible()
        outer_bounds = await outer.bounding_box()
        inner_bounds = await handle.bounding_box()
        list_bounds = await root.locator(':scope > ul').bounding_box()
        assert abs(outer_bounds['x'] + outer_bounds['width'] - inner_bounds['x']) < 1
        assert outer_bounds['height'] == inner_bounds['height'] == 28
        assert abs(outer_bounds['y'] - inner_bounds['y']) < 2
        if touch:
            await outer.tap()
            await page.get_by_role('button', name='下移块', exact=True).tap()
        else:
            await outer.focus()
            await page.keyboard.press('Alt+ArrowDown')
        order = "() => { const nodes = [...document.querySelector('.vditor-wysiwyg > .vditor-reset').children]; return nodes.findIndex(n => n.tagName === 'UL') > nodes.findIndex(n => n.textContent === 'Tail.'); }"
        await page.wait_for_function(order)
        await expect(page.get_by_role('button', name='列表项', exact=True)).to_be_visible()
        await page.locator('.article-save-button').click()
        await expect(page.locator('.article-save-state')).to_have_text('已保存')
        saved = (directory / 'reviewed.md').read_text()
        assert '- [ ] 第二项\n- [x] 第一项 **重点**\n  - 子项乙\n  - 子项甲\n- [ ] 第三项' in saved
        assert saved.index('Tail.') < saved.index('- [ ] 第二项')
        assert 'noosphere-block' not in saved
        assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
        await page.screenshot(path=str(tmp_path / f'list-scopes-{touch}.png'), full_page=True)
        await page.reload()
        await expect(root.locator(':scope > ul > li')).to_have_count(3)
        await page.wait_for_function(order)
        assert not errors, errors
        await browser.close()


@pytest.mark.asyncio
async def test_touch_selects_complete_table_and_single_line_quote(browser_server):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    table = '| A | B |\n| --- | --- |\n| one | two |'
    quote = '> 单行引用。'
    (directory / 'reviewed.md').write_text('# Browser article\n\nSingle line.\n\n' + table + '\n\n' + quote + '\n\nTail.\n')
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={'width': 390, 'height': 1000}, has_touch=True)
        await page.add_init_script("localStorage.setItem('noosphere-language', 'zh')")
        await page.goto(base + '/app/#/articles/browser_article')
        await sign_in(page)
        await page.locator('.editor-mode-toggle button').nth(1).click()
        root = page.locator('.vditor-wysiwyg > .vditor-reset')
        await root.locator(':scope > p').first.tap()
        for selector in [':scope > table', ':scope > blockquote']:
            block = root.locator(selector)
            await block.tap(position={'x': 40, 'y': 12})
            handle = page.locator('.noosphere-block-handle')
            await expect(handle).to_be_visible()
            await handle.tap()
            await expect(page.get_by_role('button', name='整个列表', exact=True)).to_be_hidden()
            await page.get_by_role('button', name='上移块', exact=True).tap()
        await expect(root.locator(':scope > table td')).to_have_count(2)
        await expect(root.locator(':scope > blockquote')).to_have_text('单行引用。')
        await page.locator('.article-save-button').tap()
        await expect(page.locator('.article-save-state')).to_have_text('已保存')
        saved = (directory / 'reviewed.md').read_text()
        assert saved.index(table) < saved.index(quote) < saved.index('Single line.')
        assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("language,theme,width", [("en", "light", 1440), ("zh", "dark", 1024), ("en", "dark", 390)])
async def test_reading_layout_and_theme_remain_usable(browser_server, tmp_path, language, theme, width):
    from playwright.async_api import async_playwright, expect
    base, _ = browser_server
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={"width": width, "height": 900})
        await context.add_init_script(f"localStorage.setItem('noosphere-language', '{language}'); localStorage.setItem('noosphere-theme', '{theme}')")
        page = await context.new_page()
        await page.goto(base + "/app/#/articles/browser_article")
        await sign_in(page)
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
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        await context.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        page = await context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(base + '/app/#/search?q=Original')
        await sign_in(page)
        await expect(page.get_by_role('heading', name='Full-text search')).to_be_visible()
        await expect(page.locator('.search-result')).to_have_count(1)
        await expect(page.locator('.search-passage mark').first).to_be_visible()
        await page.get_by_role('link', name='View in article ↗', exact=True).first.click()
        await expect(page.locator('.reader-surface')).to_contain_text('Original paragraph.')
        await page.wait_for_function("CSS.highlights?.get('noosphere-search-matches')?.size > 0")
        await expect(page.locator('.search-location-notice')).to_have_count(0)
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


@pytest.mark.asyncio
async def test_in_app_login_logout_and_global_route_layout(browser_server, tmp_path):
    from playwright.async_api import async_playwright, expect
    base, _ = browser_server
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={"width": 390, "height": 844})
        await context.add_init_script("localStorage.setItem('noosphere-language', 'en'); localStorage.setItem('noosphere-theme', 'dark')")
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        await page.goto(base + "/app/#/")
        await expect(page.get_by_role("heading", name="Noosphere")).to_be_visible()
        await page.screenshot(path=str(tmp_path / "login-mobile-dark.png"), full_page=True)
        await page.get_by_role("textbox", name="Access token").fill("wrong-token")
        await page.get_by_role("button", name="Sign in", exact=True).click()
        await expect(page.get_by_role("alert")).to_contain_text("Incorrect token")
        await sign_in(page)

        await page.get_by_role("button", name="Open navigation").click()
        await page.get_by_role("button", name="Capture URL").click()
        await page.get_by_role("menuitem", name="Multiple articles").click()
        await expect(page.get_by_role("dialog", name="Capture multiple articles")).to_be_visible()
        await page.screenshot(path=str(tmp_path / "batch-dialog-mobile-dark.png"), full_page=True)
        await page.keyboard.press("Escape")
        await expect(page.get_by_role("dialog", name="Capture multiple articles")).to_be_hidden()

        for route in ("/", "/search?q=Original", "/batches", "/settings", "/library", "/articles/browser_article"):
            await page.goto(base + "/app/#" + route)
            await expect(page.locator(".app-root")).to_be_visible()
            assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), route
            await page.wait_for_timeout(350)
            slug = route.split("?", 1)[0].strip("/").replace("/", "-") or "dashboard"
            await page.screenshot(path=str(tmp_path / f"{slug}-mobile-dark.png"), full_page=True)

        await page.set_viewport_size({"width": 1280, "height": 900})
        for route in ("/", "/search?q=Original", "/batches", "/settings", "/library", "/articles/browser_article"):
            await page.goto(base + "/app/#" + route)
            await expect(page.locator(".app-root")).to_be_visible()
            assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), route
            slug = route.split("?", 1)[0].strip("/").replace("/", "-") or "dashboard"
            await page.screenshot(path=str(tmp_path / f"{slug}-desktop-dark.png"), full_page=True)

        await page.set_viewport_size({"width": 390, "height": 844})
        await page.wait_for_timeout(350)
        await page.get_by_role("button", name="Open navigation").click()
        await page.get_by_role("button", name="Sign out").click()
        await expect(page.get_by_role("button", name="Sign in", exact=True)).to_be_visible()
        assert not errors
        await browser.close()


@pytest.mark.asyncio
async def test_paragraph_drag_keeps_markdown_images_history_and_save(browser_server, tmp_path):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    assets = directory / "assets"
    assets.mkdir()
    (assets / "pixel.png").write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="))
    structures = ["- Point\n  - Nested point\n- Other point", "| Left | Right |\n| :--- | ---: |\n| one | two |", '```python\n## Code heading\n\nprint("body")\n```', "$$\nx + y = z\n$$", "<div>HTML content</div>"]
    markdown = "\n\n".join(["# Browser article", 'First paragraph **bold** [link](https://example.test) ![first](assets/pixel.png "caption").', *structures, "Last paragraph ![second](assets/pixel.png).", "Reference paragraph with note[^one].", "Second note paragraph[^two].", "[^one]: Footnote text.", "[^two]: Second footnote text."]) + "\n"
    (directory / "reviewed.md").write_text(markdown)
    original_raw = (directory / "raw.md").read_bytes()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 1100})
        await page.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(base + "/app/#/articles/browser_article")
        await sign_in(page)
        await page.get_by_role("button", name="Edit", exact=True).click()
        root = page.locator(".vditor-wysiwyg > .vditor-reset")
        first = root.locator(":scope > p").filter(has_text="First paragraph")
        await expect(first).to_be_visible()
        await first.evaluate("element => { const range = document.createRange(); range.selectNodeContents(element); range.collapse(false); const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); element.parentElement.focus(); }")
        await page.keyboard.insert_text(" NEW_TYPED")
        await first.hover()
        handle = page.locator(".noosphere-block-handle")
        await expect(handle).to_be_visible()
        bounds = await handle.bounding_box()
        target = await root.locator(":scope > table").bounding_box()
        await page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
        await page.mouse.down()
        await page.mouse.move(target["x"] + 80, target["y"] + target["height"] - 3, steps=12)
        await expect(page.locator(".noosphere-image-drop-line")).to_be_visible()
        await page.mouse.up()
        order = "() => { const nodes = [...document.querySelector('.vditor-wysiwyg > .vditor-reset').children]; return nodes.findIndex(n => n.textContent.includes('First paragraph')) > nodes.findIndex(n => n.tagName === 'TABLE'); }"
        await page.wait_for_function(order)
        await expect(first).to_contain_text("NEW_TYPED")
        await expect(root.locator("img")).to_have_count(2)
        await root.focus()
        await page.keyboard.press("ControlOrMeta+z")
        await page.wait_for_function("() => { const nodes = [...document.querySelector('.vditor-wysiwyg > .vditor-reset').children]; return nodes[1].textContent.includes('First paragraph'); }")
        await expect(first).to_contain_text("NEW_TYPED")
        await page.keyboard.press("ControlOrMeta+y")
        await page.wait_for_function(order)
        await expect(page.get_by_role("button", name="Save reviewed Markdown", exact=True)).to_be_enabled()
        await page.get_by_role("button", name="Save reviewed Markdown", exact=True).click()
        await expect(page.get_by_role("button", name="Save reviewed Markdown", exact=True)).to_be_disabled()
        await expect(page.locator(".article-save-state")).to_have_text("Saved")
        saved = (directory / "reviewed.md").read_text()
        for block in structures:
            assert block in saved
        assert "NEW_TYPED" in saved
        assert saved.count("assets/pixel.png") == 2
        assert saved.index("| Left | Right |") < saved.index("First paragraph")
        assert "noosphere-block" not in saved
        assert (directory / "raw.md").read_bytes() == original_raw
        await page.screenshot(path=str(tmp_path / "paragraph-drag-desktop.png"), full_page=True)
        await page.reload()
        await expect(root).to_be_visible()
        await page.wait_for_function(order)
        await expect(root.locator("img")).to_have_count(2)
        await expect(page.locator(".noosphere-block-controls")).to_be_hidden()
        await page.get_by_role("button", name="Edit", exact=True).click()
        second_note = root.locator(":scope > p").filter(has_text="Second note paragraph")
        await second_note.hover()
        await handle.focus()
        await page.keyboard.press("Alt+ArrowUp")
        await page.wait_for_function("() => { const text = document.querySelector('.vditor-wysiwyg > .vditor-reset').textContent; return text.indexOf('Second note paragraph') < text.indexOf('Reference paragraph'); }")
        await page.get_by_role("button", name="Save reviewed Markdown", exact=True).click()
        await expect(page.locator(".article-save-state")).to_have_text("Saved")
        saved = (directory / "reviewed.md").read_text()
        assert "Reference paragraph with note[^one]." in saved
        assert "Second note paragraph[^two]." in saved
        assert "[^two]: Second footnote text." in saved
        await root.focus()
        await page.keyboard.press("ControlOrMeta+a")
        await page.keyboard.press("Backspace")
        await expect(root.locator("img")).to_have_count(2)
        await expect(first).to_contain_text("NEW_TYPED")
        await root.locator("img").first.focus()
        await page.keyboard.press("Alt+ArrowDown")
        await page.wait_for_function("() => !document.querySelector('.vditor-wysiwyg img').closest('p').textContent.includes('First paragraph')")
        await expect(root.locator("img")).to_have_count(2)
        await page.wait_for_timeout(1200)
        await root.focus()
        await page.keyboard.press("ControlOrMeta+z")
        await page.wait_for_function("() => document.querySelector('.vditor-wysiwyg img').closest('p').textContent.includes('First paragraph')")
        assert not errors, errors
        await browser.close()


@pytest.mark.asyncio
async def test_paragraph_drag_noop_cancel_and_edge_scroll(browser_server):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    (directory / "reviewed.md").write_text("# Browser article\n\n" + "\n\n".join(f"Paragraph {index:02d}. " + "Content. " * 10 for index in range(24)) + "\n")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 850})
        await page.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        await page.goto(base + "/app/#/articles/browser_article")
        await sign_in(page)
        await page.get_by_role("button", name="Edit", exact=True).click()
        root = page.locator(".vditor-wysiwyg > .vditor-reset")
        first = root.locator(":scope > p").first
        await first.hover()
        handle = page.locator(".noosphere-block-handle")
        await expect(handle).to_be_visible()
        bounds = await handle.bounding_box()
        target = await first.bounding_box()
        await page.mouse.move(bounds["x"] + 10, bounds["y"] + 14)
        await page.mouse.down()
        await page.mouse.move(target["x"] + 50, target["y"] + 4, steps=4)
        await expect(page.locator(".noosphere-image-drop-line")).to_be_hidden()
        await page.mouse.up()
        await expect(page.get_by_role("button", name="Save reviewed Markdown", exact=True)).to_be_disabled()
        await first.hover()
        bounds = await handle.bounding_box()
        reader = page.locator(".reader-surface")
        viewport = await reader.bounding_box()
        await page.mouse.move(bounds["x"] + 10, bounds["y"] + 14)
        await page.mouse.down()
        await page.mouse.move(viewport["x"] + 80, viewport["y"] + viewport["height"] - 8, steps=5)
        await page.wait_for_function("document.querySelector('.reader-surface').scrollTop > 20")
        await page.keyboard.press("Escape")
        await page.mouse.up()
        await expect(page.locator(".noosphere-image-drop-line")).to_be_hidden()
        await expect(page.get_by_role("button", name="Save reviewed Markdown", exact=True)).to_be_disabled()
        scroll = await reader.evaluate("element => element.scrollTop")
        await page.wait_for_timeout(150)
        assert abs(await reader.evaluate("element => element.scrollTop") - scroll) < 2
        await expect(root.locator(":scope > p").first).to_contain_text("Paragraph 00.")
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("language,theme,width,touch", [("en", "light", 1440, False), ("zh", "dark", 1024, False), ("zh", "light", 390, True)])
async def test_paragraph_controls_selection_keyboard_and_touch(browser_server, tmp_path, language, theme, width, touch):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    (directory / "reviewed.md").write_text("# Browser article\n\nFirst paragraph. 中文输入。\n\nSecond paragraph.\n\nThird paragraph.\n")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={"width": width, "height": 900}, has_touch=touch)
        await context.add_init_script(f"localStorage.setItem('noosphere-language', '{language}'); localStorage.setItem('noosphere-theme', '{theme}')")
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(base + "/app/#/articles/browser_article")
        await sign_in(page)
        await page.locator(".editor-mode-toggle button").nth(1).click()
        root = page.locator(".vditor-wysiwyg > .vditor-reset")
        first = root.locator(":scope > p").filter(has_text="First paragraph")
        await first.evaluate("element => { element.parentElement.focus(); const range = document.createRange(); range.setStart(element.firstChild, 0); range.setEnd(element.firstChild, 5); const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range); }")
        if not touch:
            await first.hover()
        handle = page.locator(".noosphere-block-handle")
        await expect(handle).to_be_visible()
        await handle.dispatch_event("keydown", {"key": "ArrowDown", "altKey": True, "isComposing": True})
        await expect(root.locator(":scope > p").first).to_contain_text("First paragraph")
        if touch:
            await handle.tap()
            await page.get_by_role("button", name="下移块", exact=True).tap()
        else:
            await handle.focus()
            await page.keyboard.press("Alt+ArrowDown")
        await expect(root.locator(":scope > p").nth(1)).to_contain_text("First paragraph")
        assert await page.evaluate("window.getSelection().toString()") == "First"
        await expect(handle).to_be_visible()
        await page.screenshot(path=str(tmp_path / f"paragraph-controls-{language}-{theme}-{width}.png"), full_page=True)
        if touch:
            await page.get_by_role("button", name="上移块", exact=True).tap()
        else:
            await page.keyboard.press("Alt+ArrowUp")
        await expect(root.locator(":scope > p").first).to_contain_text("First paragraph")
        await page.locator(".editor-mode-toggle button").first.click()
        await expect(page.locator(".noosphere-block-controls")).to_be_hidden()
        assert await page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        assert not errors, errors
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('touch', [False, True])
async def test_heading_fold_scope_history_navigation_and_save(browser_server, tmp_path, touch):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    section = '## Alpha\n\nAlpha **body** [link][ref].\n\n### Nested\n\nNested body.\n\n![one](assets/fold.png)\n\n- Item\n  - Child\n\n|a|b|\n|---|---|\n|x|y|\n\n~~~js\n## Code text\n\ncode()\n~~~'
    markdown = '# Browser article\n\nIntro.\n\n' + section + '\n\n## Beta\n\nBeta body.\n\n## End\n\nEnd body.\n\n[ref]: https://example.test\n'
    (directory / 'reviewed.md').write_text(markdown)
    original_raw = (directory / 'raw.md').read_bytes()
    (directory / 'assets').mkdir()
    (directory / 'assets' / 'fold.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='))
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={'width': 390 if touch else 1440, 'height': 1100}, has_touch=touch)
        await page.add_init_script("localStorage.setItem('noosphere-language', 'en'); localStorage.setItem('noosphere-theme', 'dark')")
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(base + '/app/#/articles/browser_article')
        await sign_in(page)
        await page.get_by_role('button', name='Edit', exact=True).click()
        root = page.locator('.vditor-wysiwyg > .vditor-reset')
        alpha = root.locator(':scope > h2').filter(has_text='Alpha')
        nested = root.locator(':scope > h3').filter(has_text='Nested')
        body = root.locator(':scope > p').filter(has_text='Alpha body')
        nested_body = root.locator(':scope > p').filter(has_text='Nested body.')
        handle = page.locator('.noosphere-block-handle')
        fold = page.locator('.noosphere-heading-toggle')
        save = page.get_by_role('button', name='Save reviewed Markdown', exact=True)
        toggle_fold = fold.tap if touch else fold.click
        async def select_heading(node):
            if touch:
                await node.tap()
            else:
                await node.hover(position={'x': 60, 'y': 12})
            await expect(handle).to_be_visible()
        await expect(save).to_be_disabled()
        await select_heading(alpha)
        await expect(handle).to_have_attribute('aria-label', 'Move heading')
        if touch:
            await handle.tap()
            await page.get_by_role('button', name='Move block down', exact=True).tap()
        else:
            await handle.focus()
            await page.keyboard.press('Alt+ArrowDown')
        await page.wait_for_function("() => { const root = document.querySelector('.vditor-wysiwyg > .vditor-reset'); const alpha = [...root.children].find(n => n.tagName === 'H2' && n.textContent === 'Alpha'); return alpha.previousElementSibling.textContent.includes('Alpha body'); }", timeout=5000)
        await expect(nested_body).to_be_visible()
        await root.focus()
        await page.keyboard.press('ControlOrMeta+z')
        await page.wait_for_function("() => { const root = document.querySelector('.vditor-wysiwyg > .vditor-reset'); const alpha = [...root.children].find(n => n.tagName === 'H2' && n.textContent === 'Alpha'); return alpha.nextElementSibling.textContent.includes('Alpha body'); }")
        await expect(save).to_be_disabled()
        await select_heading(nested)
        await toggle_fold()
        await expect(nested_body).to_be_hidden()
        await expect(body).to_be_visible()
        await select_heading(alpha)
        await toggle_fold()
        await expect(body).to_be_hidden()
        await expect(nested).to_be_hidden()
        await expect(root.locator('img')).to_be_hidden()
        await expect(page.locator('.noosphere-image-actions')).to_be_hidden()
        await expect(save).to_be_disabled()
        await page.get_by_role('button', name='Read only', exact=True).click()
        await expect(body).to_be_visible()
        await expect(nested_body).to_be_visible()
        await expect(page.locator('.noosphere-block-controls')).to_be_hidden()
        await page.get_by_role('button', name='Edit', exact=True).click()
        await expect(body).to_be_hidden()
        await select_heading(alpha)
        await expect(handle).to_have_attribute('aria-label', 'Move folded section')
        if touch:
            await handle.tap()
            await page.get_by_role('button', name='Move block down', exact=True).tap()
        else:
            bounds = await handle.bounding_box()
            target = await root.locator(':scope > h2').filter(has_text='Beta').bounding_box()
            await page.mouse.move(bounds['x'] + 10, bounds['y'] + 14)
            await page.mouse.down()
            await page.mouse.move(target['x'] + 60, target['y'] + target['height'] - 2, steps=8)
            await expect(page.locator('.noosphere-image-drop-line')).to_be_visible()
            await page.mouse.up()
        order = "() => [...document.querySelectorAll('.vditor-wysiwyg > .vditor-reset > h2')].map(n => n.textContent).join(',') === 'Beta,Alpha,End'"
        await page.wait_for_function(order)
        await expect(body).to_be_hidden()
        await root.focus()
        await page.keyboard.press('ControlOrMeta+z')
        await expect(root.locator(':scope > h2').first).to_have_text('Alpha')
        await expect(body).to_be_hidden()
        await page.keyboard.press('ControlOrMeta+y')
        await page.wait_for_function(order)
        await expect(body).to_be_hidden()
        await select_heading(alpha)
        await toggle_fold()
        await expect(body).to_be_visible()
        await expect(nested).to_be_visible()
        await expect(nested_body).to_be_hidden()
        await select_heading(alpha)
        await toggle_fold()
        if touch:
            await select_heading(alpha)
            await toggle_fold()
        else:
            await page.locator('.article-outline button[aria-label="Nested"]').click(force=True)
        await expect(nested).to_be_visible()
        await expect(body).to_be_visible()
        await expect(nested_body).to_be_hidden()
        await select_heading(nested)
        await toggle_fold()
        await expect(nested_body).to_be_visible()
        await save.click()
        await expect(page.locator('.article-save-state')).to_have_text('Saved')
        saved = (directory / 'reviewed.md').read_text()
        assert section in saved
        assert saved.index('Beta body.') < saved.index('## Alpha') < saved.index('## End')
        assert '[ref]: https://example.test' in saved
        assert saved.count('assets/fold.png') == 1
        assert 'noosphere-' not in saved
        assert (directory / 'raw.md').read_bytes() == original_raw
        assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
        await select_heading(alpha)
        await toggle_fold()
        await page.screenshot(path=str(tmp_path / f'heading-fold-{touch}.png'), full_page=True)
        await page.reload()
        await page.wait_for_function(order)
        await expect(nested_body).to_be_visible()
        assert not errors, errors
        await browser.close()


@pytest.mark.asyncio
async def test_duplicate_heading_folds_follow_selected_section_and_typing(browser_server):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    (directory / 'reviewed.md').write_text('# Browser article\n\n## Same\n\nFirst body.\n\n## Same\n\nSecond body.\n\n## End\n\nEnd body.\n')
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={'width': 1024, 'height': 1000})
        await page.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        await page.goto(base + '/app/#/articles/browser_article')
        await sign_in(page)
        await page.get_by_role('button', name='Edit', exact=True).click()
        root = page.locator('.vditor-wysiwyg > .vditor-reset')
        same = root.locator(':scope > h2').filter(has_text='Same')
        first = root.locator(':scope > p').filter(has_text='First body.')
        second = root.locator(':scope > p').filter(has_text='Second body.')
        await same.nth(1).hover(position={'x': 50, 'y': 10})
        await page.locator('.noosphere-heading-toggle').click()
        await expect(first).to_be_visible()
        await expect(second).to_be_hidden()
        await page.locator('.noosphere-block-handle').focus()
        await page.keyboard.press('Alt+ArrowUp')
        await page.wait_for_function("() => document.querySelector('.vditor-wysiwyg > .vditor-reset > h2').nextElementSibling.textContent === 'Second body.'")
        await expect(second).to_be_hidden()
        await expect(first).to_be_visible()
        await root.focus()
        await page.keyboard.press('ControlOrMeta+z')
        await page.wait_for_function("() => document.querySelector('.vditor-wysiwyg > .vditor-reset > h2').nextElementSibling.textContent === 'First body.'")
        await expect(second).to_be_hidden()
        await expect(first).to_be_visible()
        await page.keyboard.press('ControlOrMeta+y')
        await page.wait_for_function("() => document.querySelector('.vditor-wysiwyg > .vditor-reset > h2').nextElementSibling.textContent === 'Second body.'")
        await expect(second).to_be_hidden()
        end = root.locator(':scope > p').filter(has_text='End body.')
        await end.click()
        await page.keyboard.press('End')
        await page.keyboard.insert_text(' Typed text.')
        await page.wait_for_timeout(900)
        await expect(end).to_contain_text('Typed text.')
        await expect(second).to_be_hidden()
        await page.get_by_role('button', name='Save reviewed Markdown', exact=True).click()
        await expect(page.locator('.article-save-state')).to_have_text('Saved')
        saved = (directory / 'reviewed.md').read_text()
        assert saved.index('Second body.') < saved.index('First body.')
        assert 'End body. Typed text.' in saved
        assert saved.count('## Same') == 2
        assert 'noosphere-' not in saved
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('width,theme', [(1440, 'light'), (1024, 'dark')])
async def test_continuous_left_gutter_and_compact_group_drag(browser_server, tmp_path, width, theme):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    listing = '- First\n  - Child one\n  - Child two\n- Second\n- Third'
    table = '| A | B |\n| --- | --- |\n| one | two |'
    (directory / 'reviewed.md').write_text('# Browser article\n\nLead paragraph.\n\n## Body\n\n> A single-line quote.\n\n' + listing + '\n\n' + table + '\n\nTail paragraph.\n')
    original_raw = (directory / 'raw.md').read_bytes()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={'width': width, 'height': 1200})
        await page.add_init_script(f"localStorage.setItem('noosphere-language', 'en'); localStorage.setItem('noosphere-theme', '{theme}')")
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(base + '/app/#/articles/browser_article')
        await sign_in(page)
        await page.get_by_role('button', name='Edit', exact=True).click()
        root = page.locator('.vditor-wysiwyg > .vditor-reset')
        lead = root.locator(':scope > p').filter(has_text='Lead paragraph.')
        lead_bounds = await lead.bounding_box()
        reader_bounds = await page.locator('.reader-surface').bounding_box()
        x = max(lead_bounds['x'] - 64, reader_bounds['x'] + 4)
        handle = page.locator('.noosphere-block-handle')
        outer = page.locator('.noosphere-container-handle')
        boundary = page.locator('.noosphere-block-boundary')
        await page.mouse.move(20, 20)
        await expect(page.locator('.noosphere-block-controls')).to_be_hidden()
        items = root.locator(':scope > ul > li')
        second = items.nth(1)
        second_bounds = await second.bounding_box()
        await page.mouse.move(x, second_bounds['y'] + 14)
        await expect(handle).to_be_visible()
        await expect(outer).to_be_visible()
        async def follows(node):
            bounds = await node.bounding_box()
            await page.mouse.move(x, bounds['y'] + 14, steps=8)
            await expect(handle).to_be_visible()
            await page.wait_for_function("top => Math.abs(document.querySelector('.noosphere-block-boundary').getBoundingClientRect().top - top) < 2", arg=bounds['y'])
        await follows(items.first)
        await follows(items.first.locator(':scope > ul > li').first)
        await follows(items.first.locator(':scope > ul > li').nth(1))
        await follows(second)
        await follows(items.nth(2))
        third_bounds = await items.nth(2).bounding_box()
        table_bounds = await root.locator(':scope > table').bounding_box()
        for y in range(int(third_bounds['y'] + third_bounds['height']), int(table_bounds['y']) + 2, 3):
            await page.mouse.move(x, y)
            await expect(handle).to_be_visible()
        outline = await boundary.bounding_box()
        assert abs(outline['y'] - table_bounds['y']) < 2
        lead_bounds = await lead.bounding_box()
        for y in range(int(lead_bounds['y'] + 2), int(second_bounds['y']) + 14, 8):
            await page.mouse.move(x, y)
            await expect(handle).to_be_visible()
        await follows(second)
        inner_bounds = await handle.bounding_box()
        outer_bounds = await outer.bounding_box()
        assert outer_bounds['height'] == inner_bounds['height'] == 28
        assert abs(outer_bounds['x'] + outer_bounds['width'] - inner_bounds['x']) < 1
        assert abs(outer_bounds['y'] - inner_bounds['y']) < 2
        await page.mouse.move(outer_bounds['x'] + outer_bounds['width'] / 2, outer_bounds['y'] + 14, steps=12)
        list_bounds = await root.locator(':scope > ul').bounding_box()
        await page.wait_for_function("height => Math.abs(document.querySelector('.noosphere-block-boundary').getBoundingClientRect().height - height) < 2", arg=list_bounds['height'])
        await page.screenshot(path=str(tmp_path / f'compact-gutter-{width}.png'), full_page=True)
        target = await root.locator(':scope > p').filter(has_text='Tail paragraph.').bounding_box()
        await page.mouse.down()
        await page.mouse.move(target['x'] + 60, target['y'] + target['height'] - 2, steps=12)
        await expect(page.locator('.noosphere-image-drop-line')).to_be_visible()
        await page.mouse.up()
        await page.wait_for_function("() => {const nodes = [...document.querySelector('.vditor-wysiwyg > .vditor-reset').children]; return nodes.findIndex(n => n.tagName === 'UL') > nodes.findIndex(n => n.textContent === 'Tail paragraph.');}")
        await root.focus()
        await page.keyboard.press('ControlOrMeta+z')
        await page.wait_for_function("() => document.querySelector('.vditor-wysiwyg > .vditor-reset > ul').nextElementSibling.tagName === 'TABLE'")
        await page.keyboard.press('ControlOrMeta+y')
        await page.get_by_role('button', name='Save reviewed Markdown', exact=True).click()
        await expect(page.locator('.article-save-state')).to_have_text('Saved')
        saved = (directory / 'reviewed.md').read_text()
        assert listing in saved
        assert saved.index('Tail paragraph.') < saved.index('- First')
        assert 'noosphere-' not in saved
        assert (directory / 'raw.md').read_bytes() == original_raw
        await page.get_by_role('button', name='Read only', exact=True).click()
        current = await root.locator(':scope > ul > li').nth(1).bounding_box()
        await page.mouse.move(x, current['y'] + 14)
        await expect(page.locator('.noosphere-block-controls')).to_be_hidden()
        assert not errors, errors
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('width,theme', [(1440, 'light'), (1024, 'dark'), (390, 'light')])
async def test_fixed_two_column_grips_and_full_left_hover_corridor(browser_server, tmp_path, width, theme):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    lead = '  \n'.join(['Lead line one.', 'Lead line two.', 'Lead line three.', 'Lead line four.'])
    listing = '- Parent\n  - Nested one\n  - Nested two\n- Sibling'
    numbers = '9998. First numbered\n9999. Second numbered\n10000. Third numbered'
    markdown = '\n\n'.join(['# Browser article', lead, '## Body', listing, numbers, '- [x] Checked\n- [ ] Unchecked', 'Tail.']) + '\n'
    (directory / 'reviewed.md').write_text(markdown)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={'width': width, 'height': 1200})
        await page.add_init_script(f"localStorage.setItem('noosphere-language', 'en'); localStorage.setItem('noosphere-theme', '{theme}')")
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(base + '/app/#/articles/browser_article')
        await sign_in(page)
        await page.get_by_role('button', name='Edit', exact=True).click()
        root = page.locator('.vditor-wysiwyg > .vditor-reset')
        handle = page.locator('.noosphere-block-handle')
        outer = page.locator('.noosphere-container-handle')
        boundary = page.locator('.noosphere-block-boundary')
        controls = page.locator('.noosphere-block-controls')
        reader = page.locator('.reader-surface')

        paragraph = root.locator(':scope > p').first
        await paragraph.scroll_into_view_if_needed()
        bounds = await paragraph.bounding_box()
        reader_bounds = await reader.bounding_box()
        y = bounds['y'] + bounds['height'] - 10
        assert y > bounds['y'] + 28
        await page.mouse.move(20, 20)
        await expect(controls).to_be_hidden()
        await page.mouse.move(reader_bounds['x'] + 1, y)
        await expect(handle).to_be_visible()
        paragraph_grip = await handle.bounding_box()
        rail_left = paragraph_grip['x']
        for x in range(int(bounds['x'] + 20), int(reader_bounds['x']), -4):
            await page.mouse.move(x, y)
            await expect(handle).to_be_visible()
        outline = await boundary.bounding_box()
        assert abs(outline['y'] - bounds['y']) < 1

        for item in [root.locator(':scope > ul').first.locator('li').nth(1),
                     root.locator(':scope > ol > li').first,
                     root.locator(':scope > ul').last.locator(':scope > li').first]:
            await item.scroll_into_view_if_needed()
            await page.mouse.move(20, 20)
            await expect(controls).to_be_hidden()
            bounds = await item.bounding_box()
            reader_bounds = await reader.bounding_box()
            y = bounds['y'] + 14
            await page.mouse.move(reader_bounds['x'] + 1, y)
            await expect(handle).to_be_visible()
            await expect(outer).to_be_visible()
            inner_bounds = await handle.bounding_box()
            outer_bounds = await outer.bounding_box()
            assert abs(outer_bounds['x'] - rail_left) < 1
            assert abs(outer_bounds['x'] + outer_bounds['width'] - inner_bounds['x']) < 1
            assert inner_bounds['width'] == outer_bounds['width'] == 22
            assert inner_bounds['height'] == outer_bounds['height'] == 28
            assert abs(inner_bounds['y'] - outer_bounds['y']) < 1
            for grip in [handle, outer]:
                dots = await grip.locator('svg circle').evaluate_all('nodes => nodes.map(node => [node.cx.baseVal.value, node.cy.baseVal.value])')
                assert len(dots) == 6
                assert len({dot[0] for dot in dots}) == 2
                assert len({dot[1] for dot in dots}) == 3
            assert await outer.locator('svg path').count() == 1
            assert await handle.locator('svg path').count() == 0
            outline = await boundary.bounding_box()
            assert inner_bounds['x'] + inner_bounds['width'] <= outline['x'] + 1

            await item.hover(position={'x': 20, 'y': 14})
            for x in range(int(bounds['x'] + 20), int(inner_bounds['x'] + 10), -3):
                await page.mouse.move(x, y)
                await expect(handle).to_be_visible()
                await expect(outer).to_be_visible()
                outline = await boundary.bounding_box()
                assert abs(outline['y'] - bounds['y']) < 1
                assert abs(outline['height'] - bounds['height']) < 1
            await page.mouse.move(inner_bounds['x'] + 10, y)
            await page.wait_for_timeout(180)
            await expect(handle).to_be_visible()
            await page.mouse.move(outer_bounds['x'] + 10, y, steps=12)
            await page.wait_for_timeout(180)
            await expect(outer).to_be_visible()
            list_bounds = await item.evaluate("element => { let list = element.closest('ul,ol'); while (list.parentElement.closest('ul,ol')) list = list.parentElement.closest('ul,ol'); const bounds = list.getBoundingClientRect(); return {y: bounds.top, height: bounds.height}; }")
            outline = await boundary.bounding_box()
            assert abs(outline['y'] - list_bounds['y']) < 1
            assert abs(outline['height'] - list_bounds['height']) < 1
            await page.mouse.move(inner_bounds['x'] + 10, y, steps=12)
            outline = await boundary.bounding_box()
            assert abs(outline['y'] - bounds['y']) < 1
            assert abs(outline['height'] - bounds['height']) < 1
            await page.mouse.move(reader_bounds['x'] + 1, y, steps=12)
            await page.wait_for_timeout(180)
            await expect(handle).to_be_visible()
            await expect(outer).to_be_visible()

        await page.screenshot(path=str(tmp_path / f'fixed-grips-{width}-{theme}.png'), full_page=True)
        assert (directory / 'reviewed.md').read_text() == markdown
        await page.get_by_role('button', name='Read only', exact=True).click()
        await page.mouse.move(reader_bounds['x'] + 1, y)
        await expect(controls).to_be_hidden()
        assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
        assert not errors, errors
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('width,theme', [(1440, 'light'), (1024, 'dark')])
async def test_workspace_drag_order_stays_inside_category_and_survives_reload(browser_server, tmp_path, width, theme):
    import re
    import shutil
    from playwright.async_api import async_playwright, expect
    from src.core.config.config import clear_config_cache
    from src.core.collections import CollectionStore
    base, directory = browser_server
    clear_config_cache()
    store = CollectionStore()
    alpha = store.create_collection(name='Alpha')
    beta = store.create_collection(name='Beta')
    child_a = store.create_collection(name='Child A', parent_id=alpha['id'])
    child_b = store.create_collection(name='Child B', parent_id=alpha['id'])
    for index, (article_id, title) in enumerate([('second', 'Second article'), ('third', 'Third article'), ('foreign', 'Foreign article'), ('root_one', 'Root one'), ('root_two', 'Root two')], start=1):
        clone = directory.parent / article_id
        shutil.copytree(directory, clone)
        manifest = json.loads((clone / 'manifest.json').read_text())
        manifest['article_id'] = article_id
        manifest['article']['title'] = title
        manifest['article']['captured_at'] = f'2026-10-0{index}T00:00:00Z'
        (clone / 'manifest.json').write_text(json.dumps(manifest))
        (clone / 'reviewed.md').write_text(f'# {title}\n\nOriginal paragraph.\n')
    for article_id in ['browser_article', 'second', 'third']:
        store.assign_article(article_id, collection_id=alpha['id'], source='ai', reason='Topic match', confidence=.91)
    store.assign_article('foreign', collection_id=beta['id'], source='ai', reason='Other topic', confidence=.88)
    assignments = {item: store.get_assignment(item) for item in ['browser_article', 'second', 'third', 'foreign']}
    files = {str(path): path.read_bytes() for path in directory.parent.rglob('*') if path.is_file()}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={'width': width, 'height': 1100})
        await page.add_init_script(f"localStorage.setItem('noosphere-language','en'); localStorage.setItem('noosphere-theme','{theme}')")
        errors = []
        requests = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url) if request.method == 'POST' and request.url.endswith('/order?locale=en-US') else None)
        await page.goto(base + '/app/')
        await sign_in(page)
        sidebar = page.locator('.library-sidebar-workspace')
        alpha_scope = sidebar.locator(f'[data-order-scope="{alpha["id"]}"]')
        article = lambda article_id: sidebar.locator(f'.knowledge-article-row[data-order-id="{article_id}"]')
        branch = lambda collection_id: sidebar.locator(f'.collection-branch[data-order-id="{collection_id}"]')
        async def open_branch(collection_id):
            toggle = branch(collection_id).locator(':scope > .collection-row .collection-toggle')
            await toggle.wait_for()
            if await toggle.get_attribute('aria-expanded') == 'false':
                await toggle.click()
        async def ids(scope):
            return await scope.locator(':scope > [data-order-id]').evaluate_all('nodes => nodes.map(node => node.dataset.orderId)')
        drag_data = None
        current_source = None
        current_target = None
        current_y = 0
        async def begin(source, target, side='after'):
            nonlocal current_source, current_target, current_y, drag_data
            current_source, current_target = source, target
            drag_data = await page.evaluate_handle('new DataTransfer()')
            await source.dispatch_event('dragstart', {'dataTransfer': drag_data})
            bounds = await target.bounding_box()
            current_y = bounds['y'] + (3 if side == 'before' else bounds['height'] - 3)
            await target.dispatch_event('dragover', {'dataTransfer': drag_data, 'clientY': current_y, 'clientX': bounds['x'] + 30})
        async def release():
            await current_target.dispatch_event('drop', {'dataTransfer': drag_data, 'clientY': current_y})
            await current_source.dispatch_event('dragend', {'dataTransfer': drag_data})
        await open_branch(alpha['id'])
        await open_branch(beta['id'])
        await expect(article('third')).to_be_visible()
        assert await ids(alpha_scope) == ['third', 'second', 'browser_article']
        await begin(article('third').locator('button').first, article('browser_article'))
        await expect(alpha_scope).to_have_class(re.compile('workspace-order-allowed-scope'))
        await expect(article('browser_article')).to_have_class(re.compile('workspace-order-after'))
        await page.screenshot(path=str(tmp_path / f'workspace-allowed-{width}.png'))
        await release()
        await page.wait_for_function("id => [...document.querySelector(`[data-order-scope='${id}']`).children].map(node => node.dataset.orderId).join(',') === 'second,browser_article,third'", arg=alpha['id'])
        count = len(requests)
        await begin(article('second').locator('button').first, article('foreign'))
        await expect(article('foreign')).to_have_class(re.compile('workspace-order-blocked'))
        await expect(sidebar.locator('.workspace-order-hint')).to_have_class(re.compile('blocked'))
        await page.screenshot(path=str(tmp_path / f'workspace-forbidden-{width}.png'))
        await release()
        assert len(requests) == count
        assert store.get_assignment('second') == assignments['second']
        await begin(article('second').locator('button').first, article('root_one'))
        await expect(article('root_one')).to_have_class(re.compile('workspace-order-blocked'))
        await release()
        assert len(requests) == count
        await begin(branch(beta['id']).locator(':scope > .collection-row .collection-name'), branch(alpha['id']).locator(':scope > .collection-row'), 'before')
        await expect(branch(alpha['id'])).to_have_class(re.compile('workspace-order-before'))
        await release()
        await page.wait_for_function("id => document.querySelector('.library-sidebar-tree > .workspace-collection-scope > .collection-branch').dataset.orderId === id", arg=beta['id'])
        child = branch(child_b['id']).locator(':scope > .collection-row .collection-name')
        await expect(child).to_have_attribute('draggable', 'true')
        await child.focus()
        await page.keyboard.press('Alt+ArrowUp')
        await page.wait_for_function("ids => document.querySelector(`[data-order-id='${ids[0]}'] > .collection-children > .workspace-collection-scope > .collection-branch`).dataset.orderId === ids[1]", arg=[alpha['id'], child_b['id']])
        await page.reload()
        await open_branch(alpha['id'])
        await expect(article('third')).to_be_visible()
        assert await ids(alpha_scope) == ['second', 'browser_article', 'third']
        assert await sidebar.locator('.library-sidebar-tree > .workspace-collection-scope > .collection-branch').first.get_attribute('data-order-id') == beta['id']
        await branch(alpha['id']).locator(':scope > .collection-row .collection-name').click()
        main_scope = page.locator(f'.collection-index-list [data-order-scope="{alpha["id"]}"]')
        await expect(main_scope.locator('a')).to_have_count(3)
        assert await ids(main_scope) == ['second', 'browser_article', 'third']
        await main_scope.locator('a').first.focus()
        await page.keyboard.press('Alt+ArrowDown')
        await page.wait_for_function("id => document.querySelector(`.collection-index-list [data-order-scope='${id}']`).firstElementChild.dataset.orderId === 'browser_article'", arg=alpha['id'])
        assert await ids(alpha_scope) == ['browser_article', 'second', 'third']
        await article('browser_article').locator('button').first.click()
        await page.locator('.editor-mode-toggle button').nth(1).click()
        root = page.locator('.vditor-wysiwyg > .vditor-reset')
        await expect(root).to_be_visible()
        text_before = await root.inner_text()
        await begin(article('second').locator('button').first, root)
        await expect(sidebar.locator('.workspace-order-hint')).to_have_class(re.compile('blocked'))
        await release()
        assert await root.inner_text() == text_before
        assert assignments == {item: store.get_assignment(item) for item in assignments}
        assert files == {name: Path(name).read_bytes() for name in files}
        assert not errors, errors
        await browser.close()
    clear_config_cache()


@pytest.mark.asyncio
async def test_native_workspace_article_drag_retains_geometry_and_order(browser_server):
    import shutil
    from playwright.async_api import async_playwright, expect
    from src.core.config.config import clear_config_cache
    from src.core.collections import CollectionStore
    base, directory = browser_server
    clear_config_cache()
    store = CollectionStore()
    category = store.create_collection(name='Native drag')
    clone = directory.parent / 'native_second'
    shutil.copytree(directory, clone)
    manifest = json.loads((clone / 'manifest.json').read_text())
    manifest['article_id'] = 'native_second'
    manifest['article']['captured_at'] = '2026-10-14T00:00:00Z'
    (clone / 'manifest.json').write_text(json.dumps(manifest))
    (clone / 'reviewed.md').write_text('# Second article\n\nText.\n')
    for item in ['browser_article', 'native_second']:
        store.assign_article(item, collection_id=category['id'], source='ai')
    before = store.get_assignment('native_second')
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
        await page.add_init_script("localStorage.setItem('noosphere-language','en')")
        await page.goto(base + '/app/')
        await sign_in(page)
        branch = page.locator(f'.collection-branch[data-order-id="{category["id"]}"]')
        toggle = branch.locator('.collection-toggle').first
        await toggle.wait_for()
        if await toggle.get_attribute('aria-expanded') == 'false':
            await toggle.click()
        source = page.locator('.knowledge-article-row[data-order-id="native_second"] button').first
        target = page.locator('.knowledge-article-row[data-order-id="browser_article"]')
        await expect(source).to_be_visible()
        bounds = await source.bounding_box()
        await page.mouse.move(bounds['x'] + 30, bounds['y'] + 16)
        await page.mouse.down()
        await asyncio.wait_for(page.mouse.move(bounds['x'] + 50, bounds['y'] + 20), timeout=8)
        during = await source.bounding_box()
        assert abs(during['y'] - bounds['y']) < 1
        destination = await target.bounding_box()
        await page.mouse.move(destination['x'] + 30, destination['y'] + destination['height'] - 3, steps=10)
        await expect(target).to_have_class(__import__('re').compile('workspace-order-after'))
        await page.mouse.up()
        await page.wait_for_function("id => document.querySelector(`[data-order-scope='${id}']`).firstElementChild.dataset.orderId === 'browser_article'", arg=category['id'])
        assert store.get_assignment('native_second') == before
        await browser.close()
    clear_config_cache()


@pytest.mark.asyncio
@pytest.mark.parametrize('width,theme,language', [(1440, 'light', 'en'), (1024, 'dark', 'en'), (390, 'dark', 'zh')])
async def test_annotation_click_bubble_is_persistent_and_editable(browser_server, tmp_path, width, theme, language):
    from playwright.async_api import async_playwright, expect
    from src.application import service
    base, directory = browser_server
    article = '# Browser article\n\n同一句。\n\n间隔文字。\n\n同一句。\n\n其他正文。\n'
    (directory / 'reviewed.md').write_text(article)
    (directory / 'reflection.md').write_text('Independent reflection')
    original_note = '**原有理解**\n\n独立的注释内容。'
    updated_note = '**修改后的理解**\n\n' + '\n\n'.join(f'只修改注释，段落 {index}。' for index in range(20))
    annotation = service.create_article_annotation(directory.name, quote='同一句。', occurrence=1, note=original_note)
    snapshots = {name: (directory / name).read_bytes() for name in ['reviewed.md', 'raw.md', 'reflection.md']}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': width, 'height': 1000}, has_touch=True)
        await context.add_init_script(f"localStorage.setItem('noosphere-language', '{language}'); localStorage.setItem('noosphere-theme', '{theme}')")
        page = await context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(base + '/app/#/articles/browser_article')
        await sign_in(page)
        paragraphs = page.locator('.vditor-wysiwyg .vditor-reset p').filter(has_text='同一句。')
        await expect(paragraphs).to_have_count(2)
        async def quote_point(index):
            await paragraphs.nth(index).scroll_into_view_if_needed()
            return await paragraphs.nth(index).evaluate('''element => {
                const range = document.createRange(); range.selectNodeContents(element);
                const rect = range.getClientRects()[0]; return {x: rect.left + 8, y: rect.top + rect.height / 2, top: rect.top, right: rect.right};
            }''')
        preview = page.locator('.annotation-preview-bubble')
        first = await quote_point(0)
        await page.mouse.click(first['x'], first['y'])
        await expect(preview).to_have_count(0)
        second = await quote_point(1)
        await page.mouse.move(second['x'], second['y'])
        await expect(preview).to_have_count(0)
        await page.mouse.click(second['x'], second['y'])
        await expect(preview).to_contain_text('原有理解')
        await expect(preview.locator('strong')).to_have_text('原有理解')
        bounds = await preview.bounding_box()
        assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width
        assert bounds['y'] + bounds['height'] < second['top']
        if second['right'] - 24 + bounds['width'] <= width - 12:
            assert abs(bounds['x'] - (second['right'] - 24)) < 2
        assert await preview.evaluate("element => getComputedStyle(element, '::after').width") == '10px'
        await page.mouse.move(15, 800)
        await page.wait_for_timeout(1300)
        await expect(preview).to_be_visible()
        await page.screenshot(path=str(tmp_path / f'annotation-bubble-{width}.png'))
        await page.keyboard.press('Escape')
        await expect(preview).to_have_count(0)
        await page.mouse.click(second['x'], second['y'])
        await expect(preview).to_be_visible()
        await page.mouse.click(second['x'], second['y'])
        await expect(preview).to_have_count(0)
        await page.mouse.click(second['x'], second['y'])
        await expect(preview).to_be_visible()
        await preview.get_by_role('button', name='Close' if language == 'en' else '关闭', exact=True).click()
        await expect(preview).to_have_count(0)
        await page.mouse.click(second['x'], second['y'])
        await expect(preview).to_be_visible()
        await page.mouse.click(15, 800)
        await expect(preview).to_have_count(0)
        await page.mouse.click(second['x'], second['y'])
        await expect(preview).to_be_visible()
        await preview.get_by_role('button', name='Edit' if language == 'en' else '编辑', exact=True).click()
        dialog = page.locator('.annotation-dialog')
        await expect(dialog.locator('textarea')).to_have_value(original_note)
        await dialog.locator('textarea').fill(updated_note)
        await dialog.get_by_role('button', name='Save interpretation' if language == 'en' else '保存理解', exact=True).click()
        await expect(dialog.locator('.annotation-note-view')).to_contain_text('修改后的理解')
        await dialog.get_by_role('button', name='Close' if language == 'en' else '关闭', exact=True).last.click()
        second = await quote_point(1)
        await page.mouse.click(second['x'], second['y'])
        await expect(preview).to_contain_text('修改后的理解')
        await preview.locator('.annotation-preview-content').evaluate('element => element.scrollTop = element.scrollHeight')
        await page.mouse.move(15, 800)
        await page.wait_for_timeout(300)
        await expect(preview).to_be_visible()
        assert (await preview.bounding_box())['height'] <= 281
        await preview.get_by_role('button', name='Edit' if language == 'en' else '编辑', exact=True).click()
        await expect(dialog.locator('textarea')).to_have_value(updated_note)
        await dialog.get_by_role('button', name='Cancel' if language == 'en' else '取消', exact=True).click()
        await page.reload()
        second = await quote_point(1)
        await page.touchscreen.tap(second['x'], second['y'])
        await expect(preview).to_contain_text('修改后的理解')
        await preview.get_by_role('button', name='Edit' if language == 'en' else '编辑', exact=True).click()
        await expect(dialog.locator('textarea')).to_have_value(updated_note)
        assert service.get_article_annotations(directory.name)['items'][0]['id'] == annotation['id']
        assert {name: (directory / name).read_bytes() for name in snapshots} == snapshots
        assert not errors
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('width,theme', [(1440, 'light'), (390, 'dark')])
async def test_body_search_highlights_every_occurrence_and_cleans_up(browser_server, tmp_path, width, theme):
    from playwright.async_api import async_playwright, expect
    from src.application import service
    base, directory = browser_server
    article = '# Browser article\n\n## 标题折叠\n\n这个章节可以折叠。展开时移动标题本身，折叠后移动整个章节。\n\n## 下一段\n\n正文可以继续编辑。\n' + '\n\n'.join(f'长正文 {index}，用于验证快速滚动。' for index in range(45))
    (directory / 'reviewed.md').write_text(article)
    (directory / 'reflection.md').write_text('折叠 reflectiononlyneedle')
    service.create_article_annotation(directory.name, quote='折叠后移动整个章节。', note='折叠 annotationonlyneedle')
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={'width': width, 'height': 1000})
        await context.add_init_script(f"localStorage.setItem('noosphere-language', 'en'); localStorage.setItem('noosphere-theme', '{theme}')")
        page = await context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(base + '/app/#/search?q=折叠&scope=annotations')
        await sign_in(page)
        await expect(page.locator('.search-passage')).to_have_count(1)
        await expect(page.locator('.search-passage mark')).to_have_count(3)
        await expect(page.get_by_role('button', name='Search scope')).to_have_count(0)
        await expect(page.locator('.search-results')).not_to_contain_text('annotationonlyneedle')
        await expect(page.locator('.search-results')).not_to_contain_text('reflectiononlyneedle')
        await page.locator('.search-passage').click()
        await page.wait_for_function("CSS.highlights?.get('noosphere-search-matches')?.size === 3")
        await expect(page.locator('.search-location-notice')).to_have_count(0)
        await page.wait_for_timeout(3300)
        await page.wait_for_function("CSS.highlights?.get('noosphere-search-matches')?.size === 3")
        await page.set_viewport_size({'width': max(390, width - 150), 'height': 850})
        await page.mouse.wheel(0, 180)
        await page.wait_for_timeout(150)
        geometry = await page.evaluate('''() => {
            const root = document.querySelector('.vditor-wysiwyg .vditor-reset');
            const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
            const expected = []; let node;
            while ((node = walker.nextNode())) {
                for (const match of node.data.matchAll(/折叠/g)) {
                    const range = document.createRange(); range.setStart(node, match.index); range.setEnd(node, match.index + 2);
                    for (const rect of range.getClientRects()) expected.push([rect.left, rect.top, rect.width]);
                }
            }
            const actual = [...CSS.highlights.get('noosphere-search-matches')].flatMap(range => [...range.getClientRects()].map(rect => [rect.left, rect.top, rect.width]));
            return {expected, actual};
        }''')
        assert len(geometry['expected']) == len(geometry['actual']) == 3
        assert all(abs(a - b) < 2 for expected, actual in zip(geometry['expected'], geometry['actual']) for a, b in zip(expected, actual))
        await page.screenshot(path=str(tmp_path / f'search-all-hits-{width}.png'), full_page=True)
        await page.add_style_tag(content='.birds, .wind-lines, .wind-particles, .stars, .sky-object { display: none !important; } *, *::before, *::after { animation: none !important; transition: none !important; }')
        for position in [0, 450, 1200, 180, 1600, 30, 900, 240]:
            await page.evaluate('''position => {
                const reader = document.querySelector('.reader-surface');
                if (getComputedStyle(reader).overflowY === 'auto') reader.scrollTop = position;
                else window.scrollTo(0, position);
            }''', position)
            assert await page.evaluate("[...CSS.highlights.get('noosphere-search-matches')].every(range => range.toString() === '折叠' && range.startContainer.parentElement.closest('.vditor-reset'))")
        reader = page.locator('.reader-surface')
        await reader.hover()
        for amount in [600, -500, 1000, -800]:
            await page.mouse.wheel(0, amount)
        await page.screenshot(path=str(tmp_path / f'search-fast-scroll-{width}.png'))
        await expect(page.locator('.search-focus-layer, .search-focus-rect')).to_have_count(0)
        if width == 1440:
            await page.evaluate('''() => {
                const reader = document.querySelector('.reader-surface');
                const heading = reader.querySelector('h2');
                const toolbar = document.querySelector('.article-toolbar').getBoundingClientRect();
                reader.scrollTop += heading.getBoundingClientRect().top - toolbar.top - 25;
            }''')
            assert await page.evaluate("[...CSS.highlights.get('noosphere-search-matches')][0].getBoundingClientRect().top < document.querySelector('.reader-surface').getBoundingClientRect().top")
            toolbar = page.locator('.article-toolbar')
            highlighted_toolbar = await toolbar.screenshot()
            await page.evaluate("window.savedSearchHighlight = CSS.highlights.get('noosphere-search-matches'); CSS.highlights.delete('noosphere-search-matches')")
            plain_toolbar = await toolbar.screenshot()
            assert highlighted_toolbar == plain_toolbar, 'Search paint escaped the clipped reader into the toolbar'
            await page.evaluate("CSS.highlights.set('noosphere-search-matches', window.savedSearchHighlight); delete window.savedSearchHighlight")
        await page.get_by_role('button', name='Edit', exact=True).click()
        await page.wait_for_function("!CSS.highlights?.has('noosphere-search-matches')")
        await page.get_by_role('button', name='Read only', exact=True).click()
        await page.wait_for_function("CSS.highlights?.get('noosphere-search-matches')?.size === 3")
        await page.goto(base + '/app/#/articles/browser_article')
        await page.wait_for_function("!CSS.highlights?.has('noosphere-search-matches')")
        for term in ['annotationonlyneedle', 'reflectiononlyneedle']:
            await page.goto(base + '/app/#/search?q=' + term)
            await expect(page.locator('.search-result')).to_have_count(0)
            await expect(page.get_by_text('No matches found', exact=True)).to_be_visible()
        assert (directory / 'reviewed.md').read_text() == article
        assert not errors
        await browser.close()
