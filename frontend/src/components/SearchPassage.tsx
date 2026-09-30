import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { cleanPassage } from "../markdownClean";
import type { ArticleAnnotation } from "../types";

function normalize(value: string) {
  return value.replace(/\s+/g, "").toLocaleLowerCase();
}

function codePointToUtf16(text: string, offset: number) {
  return Array.from(text).slice(0, offset).join("").length;
}

function matchingSuffix(left: string, right: string) {
  let length = 0;
  while (length < left.length && length < right.length && left[left.length - 1 - length] === right[right.length - 1 - length]) length += 1;
  return length;
}

function matchingPrefix(left: string, right: string) {
  let length = 0;
  while (length < left.length && length < right.length && left[length] === right[length]) length += 1;
  return length;
}

function findRenderedMatch(root: Element, hit: string, source: string, anchorOffset: number, sourceOffset: number) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      return parent && !parent.closest("script, style, textarea, [hidden], [aria-hidden='true'], .vditor-copy")
        ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    }
  });
  const nodes: { node: Text; start: number; end: number }[] = [];
  let rendered = "";
  let current: Node | null;
  while ((current = walker.nextNode())) {
    const node = current as Text;
    nodes.push({ node, start: rendered.length, end: rendered.length + node.data.length });
    rendered += node.data;
  }
  if (!rendered || !hit) return null;
  const before = normalize(cleanPassage(source.slice(Math.max(0, anchorOffset - 100), anchorOffset), [], "").text).slice(-50);
  const after = normalize(cleanPassage(source.slice(anchorOffset + hit.length, anchorOffset + hit.length + 100), [], "").text).slice(0, 50);
  const folded = rendered.toLocaleLowerCase();
  const term = hit.toLocaleLowerCase();
  let best: { start: number; score: number } | null = null;
  for (let from = 0; from <= folded.length - term.length;) {
    const start = folded.indexOf(term, from);
    if (start < 0) break;
    const preceding = normalize(rendered.slice(Math.max(0, start - 120), start));
    const following = normalize(rendered.slice(start + hit.length, start + hit.length + 120));
    const score = matchingSuffix(preceding, before) + matchingPrefix(following, after);
    if (!best || score > best.score || (score === best.score && Math.abs(start - sourceOffset) < Math.abs(best.start - sourceOffset))) best = { start, score };
    from = start + Math.max(1, term.length);
  }
  if (!best) return null;
  const first = nodes.find((item) => best.start >= item.start && best.start < item.end);
  const end = best.start + hit.length;
  const last = nodes.find((item) => end > item.start && end <= item.end);
  if (!first || !last) return null;
  const range = document.createRange();
  range.setStart(first.node, best.start - first.start);
  range.setEnd(last.node, end - last.start);
  return range;
}

function showSearchFocus(range: Range) {
  const layer = document.createElement("div");
  layer.className = "search-focus-layer";
  layer.setAttribute("aria-hidden", "true");
  document.body.appendChild(layer);
  const marks: HTMLSpanElement[] = [];
  let frame = 0;
  let disposed = false;
  const paint = () => {
    if (disposed || !range.startContainer.isConnected) return;
    const rects = Array.from(range.getClientRects()).filter(rect => rect.width > 0 && rect.height > 0);
    while (marks.length < rects.length) {
      const mark = document.createElement("span");
      mark.className = "search-focus-rect";
      layer.appendChild(mark);
      marks.push(mark);
    }
    while (marks.length > rects.length) marks.pop()?.remove();
    rects.forEach((rect, index) => {
      const mark = marks[index];
      mark.style.left = `${rect.left - 1}px`;
      mark.style.top = `${rect.bottom + 3}px`;
      mark.style.width = `${rect.width + 2}px`;
      mark.style.height = "1.5px";
    });
    frame = requestAnimationFrame(paint);
  };
  frame = requestAnimationFrame(paint);
  const timeout = window.setTimeout(dispose, 3000);
  function dispose() {
    if (disposed) return;
    disposed = true;
    window.clearTimeout(timeout);
    cancelAnimationFrame(frame);
    layer.remove();
  }
  return dispose;
}

export function SearchPassage({ articleId, annotations = [], onOpenAnnotation }: {
  articleId: string;
  annotations?: ArticleAnnotation[];
  onOpenAnnotation?: (annotationId: string, focus: boolean) => void;
}) {
  const [params] = useSearchParams();
  const { i18n } = useTranslation();
  const zh = i18n.resolvedLanguage?.startsWith("zh");
  const [notFound, setNotFound] = useState(false);
  const openAnnotationRef = useRef(onOpenAnnotation);
  openAnnotationRef.current = onOpenAnnotation;
  const digest = params.get("digest");
  const field = params.get("field") ?? "reviewed";
  const start = Math.max(0, Number(params.get("start") ?? 0));
  const hit = params.get("hit") || (params.get("search") ?? "").match(/"([^"]+)"|(\S+)/)?.slice(1).find(Boolean) || "";
  const args = new URLSearchParams({ article: articleId, field, digest: digest ?? "", start: String(start) });
  const query = useQuery({ queryKey: ["search-passage", args.toString()], queryFn: () => api.searchPassage(args.toString()), enabled: Boolean(digest) });

  useEffect(() => {
    setNotFound(false);
    if (!digest || !query.data || query.data.changed || !hit) return;
    let annotationSelector = "";
    if (field === "annotations") {
      let offset = 0;
      for (const annotation of annotations) {
        const noteLength = Array.from(annotation.note).length;
        const length = noteLength + 1 + Array.from(annotation.quote).length;
        if (start >= offset && start < offset + length) {
          openAnnotationRef.current?.(annotation.id, true);
          annotationSelector = start - offset <= noteLength ? ".annotation-note-view" : ".annotation-quoted-passage";
          break;
        }
        offset += length + 2;
      }
    }
    const selector = annotationSelector || (field === "reflection" ? ".reflection-section-body"
      : field === "raw" ? ".article-source-search"
        : field === "author" ? ".inspection-source-section"
          : ".markdown-editor .vditor-wysiwyg .vditor-reset");
    const anchorOffset = codePointToUtf16(query.data.text, Math.min(200, start));
    let finished = false;
    let clearFocus: (() => void) | undefined;
    const locate = () => {
      if (finished) return;
      const root = document.querySelector(selector);
      const range = root && findRenderedMatch(root, hit, query.data!.text, anchorOffset, start);
      if (!range) return;
      range.startContainer.parentElement?.scrollIntoView({ behavior: "instant", block: "center" });
      clearFocus = showSearchFocus(range);
      finished = true;
    };
    const observer = new MutationObserver(locate);
    observer.observe(field === "annotations" ? document.body : document.querySelector(".article-page") ?? document.body, { childList: true, subtree: true, characterData: true });
    const frame = requestAnimationFrame(locate);
    const timeout = window.setTimeout(() => { observer.disconnect(); if (!finished) setNotFound(true); }, 4500);
    return () => { cancelAnimationFrame(frame); clearTimeout(timeout); observer.disconnect(); clearFocus?.(); };
  }, [articleId, digest, field, hit, start, query.data, annotations]);

  if (!digest) return null;
  const message = query.data?.changed ? (zh ? "文章内容已更新，请重新搜索定位。" : "This article changed. Search again to locate the passage.")
    : query.error ? String(query.error)
      : notFound ? (zh ? "未能在当前文章视图中定位该片段。" : "The passage could not be located in this article view.") : "";
  return message ? <div className="search-location-notice" role="status">{message} <Link to={`/search?q=${encodeURIComponent(params.get("search") ?? "")}`}>{zh ? "返回搜索" : "Back to search"}</Link></div> : null;
}
