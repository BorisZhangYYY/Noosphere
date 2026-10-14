"""Opt-in browser regression against the built app and an isolated real server.

Run: NOOSPHERE_BROWSER_TESTS=1 python -m pytest tests/test_frontend_browser.py -q
"""
import asyncio
import base64
import json
import os
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
        assert outer_bounds['x'] + outer_bounds['width'] < inner_bounds['x']
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
        await expect(page.locator('.search-focus-rect').first).to_be_visible()
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
        assert outer_bounds['x'] + outer_bounds['width'] < inner_bounds['x']
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
