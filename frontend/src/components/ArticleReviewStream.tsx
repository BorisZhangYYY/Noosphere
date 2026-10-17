import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from "react";
import type { Components } from "react-markdown";
import { useTranslation } from "react-i18next";
import { ReviewMarkdown } from "./ReviewMarkdown";

export function ArticleReviewStream({ articleId, text, source, following, onFollowingChange }: { articleId: string; text: string; source: string; following: boolean; onFollowingChange: (value: boolean) => void }) {
  const { t } = useTranslation();
  const host = useRef<HTMLDivElement>(null);
  const follow = useRef(following);
  follow.current = following;
  const scrollFrame = useRef(0);
  const onFollowingChangeRef = useRef(onFollowingChange);
  onFollowingChangeRef.current = onFollowingChange;
  const readingNodes = useRef<HTMLElement[]>([]);
  const readingAnchor = useRef<{ node: HTMLElement; top: number; label: string; tag: string; occurrence: number } | null>(null);
  const renderedText = useRef("");
  const rememberReadingPosition = useCallback(() => {
    const root = host.current?.closest<HTMLElement>(".reader-surface");
    const nodes = readingNodes.current;
    if (!root || !nodes.length) return;
    const edge = root.getBoundingClientRect().top + 70;
    let left = 0, right = nodes.length;
    while (left < right) {
      const middle = (left + right) >>> 1;
      if (nodes[middle].getBoundingClientRect().top <= edge) left = middle + 1;
      else right = middle;
    }
    let index = Math.max(0, left - 1);
    if (nodes[index].getBoundingClientRect().bottom <= edge && index + 1 < nodes.length) index++;
    const node = nodes[index], label = node.textContent?.replace(/\u200b/g, "").trim() ?? "", tag = node.tagName.toLowerCase();
    const previous = readingAnchor.current;
    const occurrence = previous?.node === node && previous.label === label ? previous.occurrence
      : nodes.slice(0, index).filter(item => item.tagName.toLowerCase() === tag && item.textContent?.replace(/\u200b/g, "").trim() === label).length;
    readingAnchor.current = { node, top: node.getBoundingClientRect().top, label, tag, occurrence };
  }, []);
  const cancelScroll = useCallback(() => {
    cancelAnimationFrame(scrollFrame.current);
    scrollFrame.current = 0;
  }, []);
  const scheduleScroll = useCallback(() => {
    if (!follow.current || scrollFrame.current) return;
    let last = performance.now();
    const step = (now: number) => {
      scrollFrame.current = 0;
      const root = host.current?.closest<HTMLElement>(".reader-surface");
      if (!root || !follow.current) return;
      const distance = Math.max(0, root.scrollHeight - root.clientHeight) - root.scrollTop;
      if (Math.abs(distance) > 0.5) {
        root.scrollTop += distance * (1 - Math.exp(-Math.min(48, Math.max(1, now - last)) / 80));
        rememberReadingPosition();
        last = now;
        scrollFrame.current = requestAnimationFrame(step);
      }
    };
    scrollFrame.current = requestAnimationFrame(step);
  }, [rememberReadingPosition]);
  const components = useMemo<Components>(() => ({
    img: ({ src, alt, node: _node, ...props }) => {
      const local = src?.match(/^(?:\.\/)?(assets|removed)\/(.+)$/);
      const url = local ? `/api/v1/articles/${encodeURIComponent(articleId)}/${local[1]}/${encodeURIComponent(local[2])}` : src;
      return <img {...props} src={url} alt={alt ?? ""} />;
    }
  }), [articleId]);
  useLayoutEffect(() => () => {
    const root = host.current?.closest<HTMLElement>(".reader-surface");
    if (!root || !host.current) return;
    // The parent can already have removed the status bar by this cleanup.
    const { top, label, tag, occurrence = 0 } = readingAnchor.current ?? {};
    const restore = (framesLeft: number) => {
      if (!root.isConnected || !label || top === undefined || !tag) return;
      const saved = root.querySelector<HTMLElement>(".article-saved-content:not([hidden])");
      if (saved?.dataset.articleId !== articleId) return;
      const match = [...saved?.querySelectorAll<HTMLElement>(tag) ?? []]
        .filter(node => node.textContent?.replace(/\u200b/g, "").trim() === label)[occurrence];
      if (match) {
        const distance = match.getBoundingClientRect().top - top;
        if (getComputedStyle(root).overflowY === "visible") window.scrollBy({ top: distance, behavior: "auto" });
        else root.scrollTop += distance;
      }
      // Native mobile anchoring can settle one frame after switching back to page scrolling.
      if (framesLeft > 0) requestAnimationFrame(() => restore(framesLeft - 1));
    };
    requestAnimationFrame(() => restore(2));
  }, []);
  useEffect(() => {
    const root = host.current?.closest<HTMLElement>(".reader-surface");
    if (!root || !host.current) return;
    root.scrollTop = 0;
    const pause = () => {
      if (!follow.current) return;
      follow.current = false;
      cancelScroll();
      onFollowingChangeRef.current(false);
    };
    let touchY = 0;
    const wheel = (event: WheelEvent) => { if (event.deltaY < 0) pause(); };
    const key = (event: KeyboardEvent) => { if (["ArrowUp", "PageUp", "Home"].includes(event.key) || (event.key === " " && event.shiftKey)) pause(); };
    const touchStart = (event: TouchEvent) => { touchY = event.touches[0]?.clientY ?? 0; };
    const touchMove = (event: TouchEvent) => {
      const nextY = event.touches[0]?.clientY ?? touchY;
      if (nextY > touchY) pause();
      touchY = nextY;
    };
    const pointer = (event: PointerEvent) => {
      if (event.clientX >= root.getBoundingClientRect().right - 18) pause();
    };
    // Scroll events also come from layout and our own animation; only user intent pauses following.
    root.addEventListener("wheel", wheel, { passive: true });
    root.addEventListener("keydown", key);
    root.addEventListener("touchstart", touchStart, { passive: true });
    root.addEventListener("touchmove", touchMove, { passive: true });
    root.addEventListener("pointerdown", pointer);
    root.addEventListener("noosphere-reveal-block", pause);
    root.addEventListener("scroll", rememberReadingPosition, { passive: true });
    window.addEventListener("scroll", rememberReadingPosition, { passive: true });
    const observer = new ResizeObserver(() => { rememberReadingPosition(); scheduleScroll(); });
    observer.observe(root);
    observer.observe(host.current);
    scheduleScroll();
    return () => {
      cancelScroll();
      observer.disconnect();
      root.removeEventListener("scroll", rememberReadingPosition);
      window.removeEventListener("scroll", rememberReadingPosition);
      root.removeEventListener("wheel", wheel);
      root.removeEventListener("keydown", key);
      root.removeEventListener("touchstart", touchStart);
      root.removeEventListener("touchmove", touchMove);
      root.removeEventListener("pointerdown", pointer);
      root.removeEventListener("noosphere-reveal-block", pause);
    };
  }, [cancelScroll, scheduleScroll, rememberReadingPosition]);
  useLayoutEffect(() => {
    readingNodes.current = [...host.current?.querySelectorAll<HTMLElement>("h1,h2,h3,p,li,pre") ?? []];
    const anchor = readingAnchor.current;
    if (anchor && !following && !text.startsWith(renderedText.current)) {
      const root = host.current?.closest<HTMLElement>(".reader-surface");
      const match = readingNodes.current.filter(node => node.tagName.toLowerCase() === anchor.tag && node.textContent?.replace(/\u200b/g, "").trim() === anchor.label)[anchor.occurrence];
      if (root && match) root.scrollTop += match.getBoundingClientRect().top - anchor.top;
      readingAnchor.current = null;
    }
    renderedText.current = text;
    rememberReadingPosition();
    if (following) scheduleScroll();
    else cancelScroll();
  }, [text, following, cancelScroll, scheduleScroll, rememberReadingPosition]);
  return <div ref={host} className="article-review-stream markdown-editor markdown-editor-readonly" tabIndex={0} aria-busy="true" aria-label={t("pipeline.reviewOutput")}>
    <div className="vditor-wysiwyg"><div className="vditor-reset article-review-prose">
    {text && <><ReviewMarkdown text={text} source={source} components={components} /><span className="article-review-cursor" aria-hidden="true" /></>}
    </div></div>
  </div>;
}
