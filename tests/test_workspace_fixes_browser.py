"""Opt-in regressions for removed-image placement and live workspace review."""
import base64
import asyncio
import os
import struct
import zlib

import pytest

from test_frontend_browser import browser_server, sign_in

pytestmark = pytest.mark.skipif(os.getenv("NOOSPHERE_BROWSER_TESTS") != "1", reason="Requires built frontend and Playwright Chromium")


@pytest.mark.asyncio
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("browser_server", ["streaming_wait_review"], indirect=True)
async def test_waiting_review_has_no_fake_percentage_and_finishes_into_history(browser_server, tmp_path, theme):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    starting = (directory / "reviewed.md").read_text()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        await context.add_init_script(f"localStorage.setItem('noosphere-language', 'en'); localStorage.setItem('noosphere-theme', '{theme}')")
        await context.request.post(base + "/api/v1/auth/login", data={"password": "browser-test-token"})
        response = await context.request.post(base + "/api/v1/articles/browser_article/review", data={})
        assert response.status == 202
        page = await context.new_page()
        await page.goto(base + "/app/#/articles/browser_article")
        status = page.locator(".article-review-status")
        await expect(status.get_by_role("button", name="Stop following", exact=True)).to_be_visible()
        await expect(status.get_by_role("button", name="Cancel review", exact=True)).to_be_visible()
        assert await status.evaluate("node => getComputedStyle(node).backgroundColor") == "rgba(0, 0, 0, 0)"
        progress = page.locator(".article-review-section .upload-progress")
        await expect(progress).to_contain_text("Reviewing text")
        await expect(page.locator(".article-review-stream")).to_have_text("")
        await expect(page.locator(".article-review-stream .article-review-cursor")).to_have_count(0)
        assert "Waiting for" not in await progress.text_content()
        await expect(progress.locator("progress:not([value])")).to_have_count(1)
        assert "%" not in await progress.text_content()
        job = (await (await context.request.get(base + "/api/v1/jobs")).json())["jobs"][0]
        assert job["status"] == "running" and job["progress"] is None and job["reviewPreview"] == ""
        assert (directory / "reviewed.md").read_text() == starting
        await page.screenshot(path=str(tmp_path / f"waiting-review-{theme}.png"))
        await page.locator(".article-breadcrumb-root").click()
        await expect(page.locator(".dashboard-job progress:not([value])")).to_have_count(1)
        assert "%" not in await page.locator(".dashboard-job").text_content()
        (tmp_path / "allow-first").touch()
        await page.locator(".dashboard-job-row").click()
        await expect(page.locator(".article-review-stream")).to_contain_text("First streamed paragraph.")
        (tmp_path / "allow-second").touch()
        await expect(page.locator(".article-review-stream")).to_contain_text("Second streamed paragraph.")
        (tmp_path / "finish-review").touch()
        await expect(page.locator(".article-review-stream")).to_have_count(0)
        await expect(page.locator(".article-saved-content")).to_contain_text("Final reviewed ending.")
        await page.locator(".article-breadcrumb-root").click()
        await expect(page.locator(".dashboard-job")).to_have_count(0)
        history = page.get_by_role("tab", name="Task history")
        await expect(history.locator("small")).to_have_text("1")
        await history.click()
        await expect(page.locator(".dashboard-job-succeeded")).to_have_count(1)
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True], ids=["complete", "cancel"])
@pytest.mark.parametrize("browser_server", ["streaming_wait_review"], indirect=True)
async def test_rereview_never_flashes_starting_article_when_job_snapshots_lag(browser_server, tmp_path, cancel):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    starting = (directory / "reviewed.md").read_bytes()
    stale_job = {"id": "earlier-review", "articleId": "browser_article", "status": "running", "stage": "ai_review",
                 "createdAt": "2000-01-01T00:00:00Z", "reviewPreview": "Original paragraph.", "events": [], "progress": None}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        await context.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        await context.request.post(base + "/api/v1/auth/login", data={"password": "browser-test-token"})
        page = await context.new_page()
        await page.route("**/api/v1/jobs/stream", lambda route: route.abort())
        started = False
        async def lagging_jobs(route):
            await asyncio.sleep(0.35)
            await route.fulfill(json={"jobs": []})
        async def article_snapshot(route):
            response = await route.fetch()
            data = await response.json()
            if started:
                data["activeReview"] = stale_job
            await route.fulfill(response=response, json=data)
        async def start_review(route):
            nonlocal started
            response = await route.fetch()
            started = True
            await route.fulfill(response=response)
        await page.route("**/api/v1/jobs", lagging_jobs)
        await page.route("**/api/v1/articles/browser_article?*", article_snapshot)
        await page.route("**/api/v1/articles/browser_article/review?*", start_review)
        await page.goto(base + "/app/#/articles/browser_article")
        await expect(page.locator(".article-saved-content")).to_contain_text("Original paragraph.")
        await page.get_by_role("button", name="Edit", exact=True).click()
        await page.evaluate('''() => {
          window.reviewTransitions = {entered: false, flashes: [], frames: 0};
          const sample = () => {
            const state = window.reviewTransitions, live = document.querySelector('.article-review-stream');
            const saved = document.querySelector('.article-saved-content');
            if (live) state.entered = true;
            if (state.entered && ((!saved?.hidden && saved?.textContent.includes('Original paragraph.')) || live?.textContent.includes('Original paragraph.'))) state.flashes.push(performance.now());
            state.frames++;
            window.reviewTransitionFrame = requestAnimationFrame(sample);
          }; sample();
        }''')
        await page.get_by_role("button", name="Review with AI", exact=True).click()
        output = page.locator(".article-review-stream")
        await expect(output).to_have_text("")
        await page.wait_for_timeout(1300)
        await expect(output).to_have_text("")
        await expect(page.locator(".article-saved-content")).to_be_hidden()
        (tmp_path / "allow-first").touch()
        await expect(output).to_contain_text("First streamed paragraph.")
        (tmp_path / "allow-second").touch()
        await expect(output).to_contain_text("Second streamed paragraph.")
        samples = await page.evaluate("() => { cancelAnimationFrame(window.reviewTransitionFrame); return window.reviewTransitions; }")
        assert samples["frames"] > 10 and samples["flashes"] == [], samples
        await page.unroute("**/api/v1/articles/browser_article?*", article_snapshot)
        if cancel:
            await page.get_by_role("button", name="Cancel review", exact=True).click()
            await expect(output).to_have_count(0)
            await expect(page.locator(".article-saved-content")).to_contain_text("Original paragraph.")
            assert (directory / "reviewed.md").read_bytes() == starting
        else:
            (tmp_path / "finish-review").touch()
            await expect(output).to_have_count(0)
            await expect(page.locator(".article-saved-content")).to_contain_text("Final reviewed ending.")
        await browser.close()


@pytest.mark.asyncio
async def test_completed_manual_capture_does_not_ask_for_nonexistent_approval(browser_server):
    from playwright.async_api import async_playwright, expect
    base, _ = browser_server
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await page.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        await page.route("**/api/v1/jobs/stream", lambda route: route.abort())
        await page.route("**/api/v1/jobs", lambda route: route.fulfill(json={"jobs": [{
            "id": "completed-manual-capture", "kind": "capture", "articleId": "browser_article",
            "createdAt": "2026-10-16T00:00:00Z", "status": "awaiting_review", "events": [],
            "reviewPreview": "Reviewed article body.",
        }]}))
        await page.goto(base + "/app/")
        await sign_in(page)
        await expect(page.locator(".dashboard-job")).to_have_count(0)
        await page.get_by_role("tab", name="Task history").click()
        job = page.locator(".dashboard-job").first
        await expect(job.locator("em")).to_have_text("AI review complete")
        assert "approval" not in (await job.text_content()).lower()
        await expect(job.get_by_role("link", name="Open article", exact=False)).to_be_visible()
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("size,removed,adjacent", [(100, False, False), (640, False, False), (100, True, False), (640, True, False), (100, False, True)])
async def test_each_image_exposes_its_own_pointer_grip_and_saves(browser_server, size, removed, adjacent):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    (directory / "assets").mkdir()
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress((b"\x00" + b"\x80\x90\xa0" * size) * size)) + chunk(b"IEND", b"")
    (directory / "assets/diagram.png").write_bytes(png)
    image_markdown = "![diagram](assets/diagram.png)"
    if adjacent:
        (directory / "assets/other.png").write_bytes(png)
        image_markdown += " ![other](assets/other.png)"
    markdown = f"# Browser article\n\nFirst paragraph.\n\n{image_markdown}\n\nLast paragraph.\n"
    for name in ("raw.md", "reviewed.md"):
        (directory / name).write_text(markdown)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={"width": 1440, "height": 1200})
        await context.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        await context.request.post(base + "/api/v1/auth/login", data={"password": "browser-test-token"})
        if removed:
            url = base + "/api/v1/articles/browser_article"
            detail = await (await context.request.get(url)).json()
            response = await context.request.patch(url + "/images/diagram.png", data={
                "state": "removed", "reviewedMarkdown": detail["editableMarkdown"], "expectedRevision": detail["revision"],
            })
            assert response.status == 200
        page = await context.new_page()
        await page.goto(base + "/app/#/articles/browser_article")
        await page.get_by_role("button", name="Edit", exact=True).click()
        image = page.locator('.vditor-wysiwyg img[data-asset-name="diagram.png"]')
        if removed:
            await expect(image).to_be_hidden()
            await page.get_by_role("button", name="Show removed images", exact=True).click()
        await image.hover()
        handle = page.locator('.noosphere-image-handle[data-asset-name="diagram.png"]')
        await expect(handle).to_be_visible()
        await expect(page.locator(".noosphere-image-handle")).to_have_count(2 if adjacent else 1)
        source = await handle.bounding_box()
        target = await page.locator('.vditor-wysiwyg > .vditor-reset > p').filter(has_text="Last paragraph.").bounding_box()
        await page.mouse.move(source["x"] + source["width"] / 2, source["y"] + source["height"] / 2)
        await page.mouse.down()
        await page.mouse.move(target["x"] + 70, target["y"] + target["height"] - 1, steps=12)
        await expect(page.locator(".noosphere-image-drop-line")).to_be_visible()
        await page.mouse.up()
        order = "() => { const nodes = [...document.querySelector('.vditor-wysiwyg > .vditor-reset').children]; return nodes.findIndex(n => n.querySelector('img[data-asset-name=\"diagram.png\"]')) > nodes.findIndex(n => n.textContent === 'Last paragraph.'); }"
        await page.wait_for_function(order)
        if adjacent:
            await expect(page.locator('.vditor-wysiwyg img[data-asset-name="other.png"]')).to_be_visible()
        await page.locator(".article-save-button").click()
        await expect(page.locator(".article-save-state")).to_have_text("Saved")
        await page.reload()
        if removed:
            await expect(image).to_be_hidden()
            await page.get_by_role("button", name="Show removed images", exact=True).click()
        await expect(image).to_be_visible()
        await page.wait_for_function(order)
        assert (directory / "raw.md").read_text() == markdown
        assert (directory / ("removed" if removed else "assets") / "diagram.png").is_file()
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("browser_server", ["streaming_long_review"], indirect=True)
async def test_long_review_keeps_playing_after_completion_and_respects_reading_position(browser_server, tmp_path):
    from playwright.async_api import async_playwright, expect
    base, _ = browser_server
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await page.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        await page.goto(base + "/app/#/articles/browser_article")
        await sign_in(page)
        await page.get_by_role("button", name="Edit", exact=True).click()
        await page.get_by_role("button", name="Review with AI", exact=True).click()
        output = page.locator(".article-review-stream")
        reader = page.locator(".reader-surface")
        await expect(output).to_contain_text("First streamed paragraph.")
        (tmp_path / "allow-second").touch()
        await expect(output).to_contain_text("Continuous long article")
        (tmp_path / "finish-review").touch()
        await page.wait_for_function("async () => (await (await fetch('/api/v1/jobs')).json()).jobs[0].status === 'succeeded'")
        await expect(output).to_be_visible()
        await expect(output).to_have_attribute("aria-busy", "true")
        samples = await output.evaluate('''node => new Promise(resolve => {
          const samples = [], start = performance.now(); let last = 0;
          function step(now) {
            if (now - last > 30) { samples.push(node.textContent.length); last = now; }
            if (now - start < 300) requestAnimationFrame(step); else resolve(samples);
          } requestAnimationFrame(step);
        })''')
        assert len(set(samples)) >= 4, samples
        assert samples == sorted(samples), samples
        bounds = await reader.bounding_box()
        await page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + 100)
        await page.mouse.wheel(0, -10000)
        await page.wait_for_timeout(100)
        before = await reader.evaluate("node => node.scrollTop")
        await page.wait_for_timeout(180)
        assert abs(await reader.evaluate("node => node.scrollTop") - before) < 3
        await reader.evaluate("node => { node.scrollTop = 350; }")
        await page.wait_for_timeout(80)
        anchor = await output.evaluate('''node => {
          const edge = node.closest('.reader-surface').getBoundingClientRect().top + 70;
          const nodes = [...node.querySelectorAll('p')];
          const block = nodes.find(item => item.getBoundingClientRect().bottom > edge);
          return {label: block.textContent.trim(), occurrence: nodes.filter(item => item.textContent.trim() === block.textContent.trim()).indexOf(block), top: block.getBoundingClientRect().top};
        }''')
        await expect(output).to_have_count(0, timeout=12000)
        saved = page.locator(".article-saved-content")
        await expect(saved).to_be_visible()
        await expect(saved).to_contain_text("Final reviewed ending.")
        assert len(await saved.text_content()) > 50000
        after_top = await saved.evaluate('''(node, anchor) => [...node.querySelectorAll('p')].filter(item => item.textContent.trim() === anchor.label)[anchor.occurrence].getBoundingClientRect().top''', anchor)
        assert abs(after_top - anchor["top"]) < 4, (anchor, after_top)
        assert '"markdown":' not in await saved.text_content()
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("live_connection", [True, False], ids=["live-stream", "polling-fallback"])
@pytest.mark.parametrize("browser_server", ["streaming_review"], indirect=True)
async def test_article_review_streams_in_article_and_shares_dashboard_progress(browser_server, tmp_path, live_connection):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    original = (directory / "reviewed.md").read_text()
    raw = (directory / "raw.md").read_bytes()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        if not live_connection:
            await page.route("**/api/v1/jobs/stream", lambda route: route.abort())
        await page.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(base + "/app/#/articles/browser_article")
        await sign_in(page)
        await page.get_by_role("button", name="Edit", exact=True).click()
        await page.get_by_role("button", name="Review with AI", exact=True).click()
        output = page.locator(".article-review-stream")
        await expect(output).to_contain_text("First streamed paragraph.")
        await expect(page.locator(".article-saved-content")).to_be_hidden()
        assert (directory / "reviewed.md").read_text() == original
        await page.get_by_role("link", name="Workspace", exact=True).click()
        job = page.locator(".dashboard-job").first
        await expect(job.locator("progress")).to_be_visible()
        await expect(page.locator(".review-output")).to_have_count(0)
        await expect(page.locator(".atmosphere")).to_have_count(1)
        await job.get_by_role("link", name="Open article", exact=False).click()
        await expect(output).to_contain_text("First streamed paragraph.")
        (tmp_path / "allow-second").touch()
        await expect(output).to_contain_text("Second streamed paragraph.")
        assert (directory / "reviewed.md").read_text() == original
        await page.reload()
        await expect(output).to_contain_text("Second streamed paragraph.")
        (tmp_path / "finish-review").touch()
        await expect(output).to_have_count(0, timeout=12000)
        await expect(page.locator(".article-saved-content")).to_contain_text("Final reviewed ending.")
        await page.get_by_role("link", name="Workspace", exact=True).click()
        await expect(page.locator(".dashboard-job")).to_have_count(0)
        await page.get_by_role("tab", name="Task history").click()
        await expect(job).to_contain_text("Completed")
        await expect(page.locator(".metrics-strip > div").nth(1).locator("strong")).to_have_text("1")
        await expect(page.locator(".article-row .status-badge")).to_contain_text("Reviewed")
        assert (directory / "raw.md").read_bytes() == raw
        assert not errors, errors
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("browser_server", ["streaming_review"], indirect=True)
async def test_cancel_half_written_review_restores_original_after_navigation(browser_server):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    original = (directory / "reviewed.md").read_bytes()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await page.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        await page.goto(base + "/app/#/articles/browser_article")
        await sign_in(page)
        await page.get_by_role("button", name="Edit", exact=True).click()
        await page.get_by_role("button", name="Review with AI", exact=True).click()
        await expect(page.locator(".article-review-stream")).to_contain_text("First streamed paragraph.")
        await page.get_by_role("link", name="Workspace", exact=True).click()
        await page.locator(".dashboard-job").first.get_by_role("link").click()
        await expect(page.locator(".article-review-stream")).to_contain_text("First streamed paragraph.")
        await page.get_by_role("button", name="Cancel review", exact=True).click()
        await expect(page.locator(".article-review-stream")).to_have_count(0)
        await expect(page.locator(".article-saved-content")).to_be_visible()
        await expect(page.locator(".article-saved-content")).to_contain_text("Original paragraph.")
        await expect(page.locator(".article-review-restored")).to_be_visible()
        assert (directory / "reviewed.md").read_bytes() == original
        await page.reload()
        await expect(page.locator(".article-saved-content")).to_contain_text("Original paragraph.")
        await expect(page.locator(".article-review-stream")).to_have_count(0)
        await browser.close()


@pytest.mark.asyncio
async def test_removed_image_can_drag_and_save_without_becoming_active(browser_server):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    (directory / "assets").mkdir()
    (directory / "assets/pixel.png").write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="))
    markdown = "# Browser article\n\nFirst paragraph.\n\n![diagram](assets/pixel.png)\n\nLast paragraph.\n"
    (directory / "raw.md").write_text(markdown)
    (directory / "reviewed.md").write_text(markdown)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        await context.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        await context.request.post(base + "/api/v1/auth/login", data={"password": "browser-test-token"})
        article_url = base + "/api/v1/articles/browser_article"
        detail = await (await context.request.get(article_url)).json()
        removed = await context.request.patch(article_url + "/images/pixel.png", data={
            "state": "removed", "reviewedMarkdown": detail["editableMarkdown"], "expectedRevision": detail["revision"],
        })
        assert removed.status == 200
        page = await context.new_page()
        await page.goto(base + "/app/#/articles/browser_article")
        image = page.locator('.vditor-wysiwyg img[data-asset-name="pixel.png"]')
        await expect(page.get_by_role("button", name="Show removed images", exact=True)).to_have_attribute("aria-pressed", "true")
        await expect(image).to_be_hidden()
        await page.get_by_role("button", name="Edit", exact=True).click()
        await expect(image).to_be_hidden()
        await page.get_by_role("button", name="Show removed images", exact=True).click()
        await expect(image).to_be_visible()
        await expect(image).to_have_attribute("draggable", "true")
        root = page.locator(".vditor-wysiwyg > .vditor-reset")
        target = root.locator(":scope > p").filter(has_text="Last paragraph.")
        transfer = await page.evaluate_handle("new DataTransfer()")
        await image.dispatch_event("dragstart", {"dataTransfer": transfer})
        bounds = await target.bounding_box()
        point = {"dataTransfer": transfer, "clientX": bounds["x"] + 30, "clientY": bounds["y"] + bounds["height"] - 1}
        await target.dispatch_event("dragover", point)
        await expect(page.locator(".noosphere-image-drop-line")).to_be_visible()
        await target.dispatch_event("drop", point)
        order = "() => { const nodes = [...document.querySelector('.vditor-wysiwyg > .vditor-reset').children]; return nodes.findIndex(n => n.querySelector('img')) > nodes.findIndex(n => n.textContent === 'Last paragraph.'); }"
        await page.wait_for_function(order)
        await image.focus()
        await page.keyboard.press("Alt+ArrowUp")
        await image.focus()
        await page.keyboard.press("Alt+ArrowDown")
        await page.wait_for_function(order)
        await page.locator(".article-save-button").click()
        await expect(page.locator(".article-save-state")).to_have_text("Saved")
        await page.reload()
        await expect(root).to_be_visible()
        await expect(image).to_be_hidden()
        await page.get_by_role("button", name="Show removed images", exact=True).click()
        await expect(image).to_be_visible()
        await page.wait_for_function(order)
        await expect(image).to_have_class(__import__("re").compile("noosphere-image-removed"))
        assert (directory / "removed/pixel.png").is_file()
        assert not (directory / "assets/pixel.png").exists()
        assert "pixel.png" not in (directory / "reviewed.md").read_text()
        assert (directory / "raw.md").read_text() == markdown
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("browser_server", ["streaming_wait_review"], indirect=True)
async def test_capture_opens_unfiled_article_before_review_finishes(browser_server, tmp_path):
    from playwright.async_api import async_playwright, expect
    base, directory = browser_server
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        await context.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        await context.request.post(base + "/api/v1/auth/login", data={"password": "browser-test-token"})
        response = await context.request.post(base + "/api/v1/captures", data={"url": "https://example.com/new-capture", "reviewMode": "ai_then_manual"})
        assert response.status == 202
        page = await context.new_page()
        await page.goto(base + "/app/")
        job = page.locator(".dashboard-job").first
        await expect(job.locator("progress")).to_be_visible()
        await job.get_by_role("link").click()
        await expect(page.locator(".article-review-stream")).to_have_text("")
        (tmp_path / "allow-first").touch()
        await expect(page.locator(".article-review-stream")).to_contain_text("First streamed paragraph.")
        detail = await (await context.request.get(base + "/api/v1/articles/browser_article")).json()
        assert not (detail.get("collection") or {}).get("collection_id")
        assert detail["activeReview"]["kind"] == "capture"
        assert (directory / "reviewed.md").read_text().startswith("# Browser article\n\nOriginal paragraph.")
        (tmp_path / "allow-second").touch()
        (tmp_path / "finish-review").touch()
        await expect(page.locator(".article-review-stream")).to_have_count(0, timeout=12000)
        await expect(page.locator(".article-saved-content")).to_contain_text("Final reviewed ending.")
        await page.get_by_role("link", name="Workspace", exact=True).click()
        await expect(page.locator(".dashboard-job")).to_have_count(0)
        await page.get_by_role("tab", name="Task history").click()
        await expect(job.locator("em")).to_have_text("AI review complete")
        await browser.close()


@pytest.mark.asyncio
async def test_current_tasks_archive_terminal_states_and_retain_capture_retry(browser_server):
    from playwright.async_api import async_playwright, expect
    base, _ = browser_server
    statuses = ["queued", "running", "succeeded", "awaiting_review", "recovered", "failed", "cancelled", "paused"]
    jobs = [{"id": status, "kind": "capture", "url": f"https://example.test/{status}",
             "articleId": "browser_article", "status": status, "progress": 78, "createdAt": "2026-10-17T00:00:00Z", "events": []}
            for status in statuses]
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await page.add_init_script("localStorage.setItem('noosphere-language', 'en')")
        await page.route("**/api/v1/jobs/stream", lambda route: route.abort())
        await page.route("**/api/v1/jobs", lambda route: route.fulfill(json={"jobs": jobs}))
        async def retry(route):
            job = {**jobs[5], "id": "retried", "status": "queued"}
            jobs.insert(0, job)
            await route.fulfill(status=202, json=job)
        await page.route("**/api/v1/captures/failed/retry", retry)
        await page.goto(base + "/app/")
        await sign_in(page)
        current = page.get_by_role("tab", name="Current runs")
        history = page.get_by_role("tab", name="Task history")
        await expect(current.locator("small")).to_have_text("2")
        await expect(history.locator("small")).to_have_text("6")
        await expect(page.locator(".dashboard-job")).to_have_count(2)
        await expect(page.locator(".dashboard-job progress:not([value])")).to_have_count(2)
        assert "78%" not in await page.locator(".dashboard-jobs").text_content()
        jobs[1]["status"] = "succeeded"
        await expect(current.locator("small")).to_have_text("1")
        await expect(history.locator("small")).to_have_text("7")
        await expect(page.locator(".dashboard-job")).to_have_count(1)
        await history.click()
        await expect(page.locator(".dashboard-job")).to_have_count(7)
        await expect(page.locator(".dashboard-job").filter(has=page.locator(".dashboard-job-awaiting_review"))).to_contain_text("AI review complete")
        await page.get_by_role("button", name="Retry", exact=True).click()
        await expect(current.locator("small")).to_have_text("2")
        await current.click()
        await expect(page.locator(".dashboard-job")).to_have_count(2)
        await expect(page.locator(".dashboard-job-failed")).to_have_count(0)
        await browser.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("width,theme", [(1440, "light"), (390, "light"), (1440, "dark"), (390, "dark")])
@pytest.mark.parametrize("browser_server", ["streaming_long_review"], indirect=True)
async def test_follow_control_keeps_scrolling_pauses_and_resumes_on_desktop_and_mobile(browser_server, tmp_path, width, theme):
    from playwright.async_api import async_playwright, expect
    base, _ = browser_server
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(viewport={"width": width, "height": 1000 if width > 500 else 844})
        await context.add_init_script(f"localStorage.setItem('noosphere-language', 'en'); localStorage.setItem('noosphere-theme', '{theme}')")
        await context.request.post(base + "/api/v1/auth/login", data={"password": "browser-test-token"})
        response = await context.request.post(base + "/api/v1/articles/browser_article/review", data={})
        assert response.status == 202
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(base + "/app/#/articles/browser_article")
        output, reader = page.locator(".article-review-stream"), page.locator(".reader-surface")
        status = page.locator(".article-review-status")
        follow = status.get_by_role("button", name="Stop following", exact=True)
        await expect(output).to_contain_text("First streamed paragraph.")
        await expect(follow).to_have_attribute("aria-pressed", "true")
        assert await status.evaluate("node => getComputedStyle(node).backgroundColor") == "rgba(0, 0, 0, 0)"
        assert not await status.evaluate("node => !!node.closest('.reader-surface')")
        assert await page.locator(".article-review-section .article-review-controls").evaluate("node => getComputedStyle(node).display") == "grid"
        assert await page.locator("html").get_attribute("data-theme") == theme
        await page.screenshot(path=str(tmp_path / f"review-follow-{width}-{theme}.png"))
        status_top = (await status.bounding_box())["y"]
        (tmp_path / "allow-second").touch()
        await page.wait_for_function("() => document.querySelector('.reader-surface').scrollTop > 160")
        await expect(follow).to_have_attribute("aria-pressed", "true")
        assert abs((await status.bounding_box())["y"] - status_top) < 2
        await follow.click()
        resume = status.get_by_role("button", name="Follow output", exact=True)
        await expect(resume).to_have_attribute("aria-pressed", "false")
        before = await reader.evaluate("node => node.scrollTop")
        await page.wait_for_timeout(250)
        assert abs(await reader.evaluate("node => node.scrollTop") - before) < 3
        await resume.click()
        await expect(follow).to_have_attribute("aria-pressed", "true")
        await page.wait_for_function("() => { const node = document.querySelector('.reader-surface'); return node.scrollTop > 500; }")
        await output.focus()
        await page.keyboard.press("PageUp")
        await expect(resume).to_have_attribute("aria-pressed", "false")
        await resume.click()
        await expect(follow).to_have_attribute("aria-pressed", "true")
        await page.wait_for_function("() => { const node = document.querySelector('.reader-surface'); return node.scrollHeight - node.clientHeight - node.scrollTop < 3; }", timeout=15000)
        await expect(follow).to_have_attribute("aria-pressed", "true")
        bounds = await reader.bounding_box()
        await page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + 120)
        await page.mouse.wheel(0, -450)
        await expect(resume).to_have_attribute("aria-pressed", "false")
        await page.wait_for_timeout(200)
        before = await reader.evaluate("node => node.scrollTop")
        await page.wait_for_timeout(200)
        assert abs(await reader.evaluate("node => node.scrollTop") - before) < 3
        await resume.click()
        await page.wait_for_function("() => { const node = document.querySelector('.reader-surface'); return node.scrollHeight - node.clientHeight - node.scrollTop < 3; }")
        await follow.click()
        await expect(resume).to_have_attribute("aria-pressed", "false")
        anchor = await output.evaluate('''node => {
          const edge = node.closest('.reader-surface').getBoundingClientRect().top + 70;
          const nodes = [...node.querySelectorAll('p')];
          const block = nodes.find(item => item.getBoundingClientRect().bottom > edge);
          const label = block.textContent.trim();
          return {label, occurrence: nodes.filter(item => item.textContent.trim() === label).indexOf(block), top: block.getBoundingClientRect().top};
        }''')
        (tmp_path / "finish-review").touch()
        await expect(output).to_have_count(0, timeout=12000)
        await expect(page.locator(".article-saved-content")).to_contain_text("Final reviewed ending.")
        await page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(resolve))))")
        after = await page.evaluate('''anchor => {
          const block = [...document.querySelectorAll('.article-saved-content p')].filter(item => item.textContent.trim() === anchor.label)[anchor.occurrence];
          return {top: block?.getBoundingClientRect().top, scroll: document.querySelector('.reader-surface').scrollTop, windowScroll: window.scrollY};
        }''', anchor)
        assert abs(after["top"] - anchor["top"]) < 4, (anchor, after)
        assert not errors, errors
        await browser.close()
