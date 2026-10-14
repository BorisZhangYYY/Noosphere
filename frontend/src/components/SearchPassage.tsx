import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { cleanPassage } from "../markdownClean";

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

function renderedText(root: Element) {
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
  return { nodes, rendered };
}

function textRange(model: ReturnType<typeof renderedText>, start: number, length: number) {
  const first = model.nodes.find(item => start >= item.start && start < item.end);
  const end = start + length;
  const last = model.nodes.find(item => end > item.start && end <= item.end);
  if (!first || !last) return null;
  const range = document.createRange();
  range.setStart(first.node, start - first.start);
  range.setEnd(last.node, end - last.start);
  return range;
}

function findRenderedMatch(model: ReturnType<typeof renderedText>, hit: string, source: string, anchorOffset: number, sourceOffset: number) {
  const { rendered } = model;
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
  return textRange(model, best.start, hit.length);
}

function allSearchRanges(model: ReturnType<typeof renderedText>, query: string, hit: string) {
  const parts = Array.from(query.matchAll(/"([^"]+)"|(\S+)/g), match => match[1] || match[2]).filter(Boolean);
  if (!parts.length && hit) parts.push(hit);
  const expression = new RegExp([...new Set(parts)].sort((a, b) => b.length - a.length).map(part => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "giu");
  return Array.from(model.rendered.matchAll(expression), match => textRange(model, match.index, match[0].length)).filter((range): range is Range => range !== null);
}

function showSearchFocus(ranges: Range[]) {
  const name = "noosphere-search-matches";
  const registry = (CSS as unknown as { highlights?: { set(name: string, value: unknown): void; get(name: string): unknown; delete(name: string): void } }).highlights;
  const HighlightConstructor = (window as unknown as { Highlight?: new (...ranges: Range[]) => { priority: number } }).Highlight;
  if (!registry || !HighlightConstructor) return () => undefined;
  const highlight = new HighlightConstructor(...ranges);
  highlight.priority = 1;
  registry.set(name, highlight);
  return () => {
    if (registry.get(name) === highlight) registry.delete(name);
  };
}

export function SearchPassage({ articleId, readOnly }: { articleId: string; readOnly: boolean }) {
  const [params] = useSearchParams();
  const { i18n } = useTranslation();
  const zh = i18n.resolvedLanguage?.startsWith("zh");
  const [notFound, setNotFound] = useState(false);
  const digest = params.get("digest");
  const field = params.get("field") ?? "reviewed";
  const supported = field === "reviewed";
  const start = Math.max(0, Number(params.get("start") ?? 0));
  const search = params.get("search") ?? "";
  const hit = params.get("hit") || search.match(/"([^"]+)"|(\S+)/)?.slice(1).find(Boolean) || "";
  const args = new URLSearchParams({ article: articleId, field, digest: digest ?? "", start: String(start) });
  const query = useQuery({ queryKey: ["search-passage", args.toString()], queryFn: () => api.searchPassage(args.toString()), enabled: Boolean(digest) && supported });

  useEffect(() => {
    setNotFound(false);
    if (!digest || !supported || !readOnly || !query.data || query.data.changed || !hit) return;
    const anchorOffset = codePointToUtf16(query.data.text, Math.min(200, start));
    let located = false;
    let clearFocus: (() => void) | undefined;
    const locate = () => {
      const root = document.querySelector(".markdown-editor .vditor-wysiwyg .vditor-reset");
      if (!root) return;
      const model = renderedText(root);
      const range = findRenderedMatch(model, hit, query.data!.text, anchorOffset, start);
      if (!range) return;
      if (!located) {
        range.startContainer.parentElement?.dispatchEvent(new CustomEvent("noosphere-reveal-block", { bubbles: true }));
        range.startContainer.parentElement?.scrollIntoView({ behavior: "instant", block: "center" });
        located = true;
      }
      clearFocus?.();
      clearFocus = showSearchFocus(allSearchRanges(model, search, hit));
    };
    const observer = new MutationObserver(locate);
    observer.observe(document.querySelector(".article-page") ?? document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["class"] });
    const frame = requestAnimationFrame(locate);
    const timeout = window.setTimeout(() => { if (!located) setNotFound(true); }, 4500);
    return () => { cancelAnimationFrame(frame); clearTimeout(timeout); observer.disconnect(); clearFocus?.(); };
  }, [articleId, digest, field, hit, search, start, query.data, readOnly, supported]);

  if (!digest) return null;
  const message = !supported ? (zh ? "搜索现在仅支持正文，请重新搜索。" : "Search now covers article text only. Please search again.")
    : query.data?.changed ? (zh ? "文章内容已更新，请重新搜索定位。" : "This article changed. Search again to locate the passage.")
      : query.error ? String(query.error)
        : notFound && readOnly ? (zh ? "未能在当前文章视图中定位该片段。" : "The passage could not be located in this article view.") : "";
  return message ? <div className="search-location-notice" role="status">{message} <Link to={`/search?q=${encodeURIComponent(search)}`}>{zh ? "返回搜索" : "Back to search"}</Link></div> : null;
}
