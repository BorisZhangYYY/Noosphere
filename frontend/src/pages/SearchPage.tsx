import { cloneElement, isValidElement, useEffect, useState, type ReactNode } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api";
import type { CollectionNode } from "../types";
import { cleanPassage } from "../markdownClean";
import { ErrorPanel, LoadingPanel } from "../components/StatePanel";
import { InlineSelect } from "../components/InlineSelect";

function collectionOptions(nodes: CollectionNode[], prefix = ""): { id: string; label: string }[] { return nodes.flatMap(node => [{ id: node.id, label: prefix + node.name }, ...collectionOptions(node.children, prefix + node.name + " / ")]); }

function codePointToUtf16(text: string, offset: number) {
  return Array.from(text).slice(0, offset).join("").length;
}

function markdownResourceUrl(src: string | undefined, articleId: string) {
  if (!src) return undefined;
  if (!src.startsWith("assets/")) return src;
  return `/api/v1/articles/${encodeURIComponent(articleId)}/${src.split("/").map(encodeURIComponent).join("/")}`;
}

function SearchImage({ src, alt, fallback }: { src?: string; alt: string; fallback: string }) {
  const [failed, setFailed] = useState(false);
  return failed || !src ? <span className="search-image-fallback">{alt || fallback}</span>
    : <img className="search-passage-image" src={src} alt={alt} loading="lazy" onError={() => setFailed(true)} />;
}

function highlightMarkdownChildren(children: ReactNode, terms: string[]): ReactNode {
  if (typeof children === "string") {
    if (!terms.length) return children;
    const expression = new RegExp(terms.map(term => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).sort((a, b) => b.length - a.length).join("|"), "giu");
    const parts: ReactNode[] = [];
    let cursor = 0;
    for (const match of children.matchAll(expression)) {
      if (match.index > cursor) parts.push(children.slice(cursor, match.index));
      parts.push(<mark key={`${match.index}-${match[0]}`}>{match[0]}</mark>);
      cursor = match.index + match[0].length;
    }
    if (cursor < children.length) parts.push(children.slice(cursor));
    return parts.length ? parts : children;
  }
  if (Array.isArray(children)) return children.map(child => highlightMarkdownChildren(child, terms));
  if (isValidElement<{ children?: ReactNode }>(children) && children.type !== "mark" && children.props.children !== undefined) {
    return cloneElement(children, { children: highlightMarkdownChildren(children.props.children, terms) });
  }
  return children;
}

function SearchMarkdown({ text, highlights, articleId, fallback }: { text: string; highlights: [number, number][]; articleId: string; fallback: string }) {
  const terms = [...new Set(highlights.map(([start, end]) => text.slice(start, end)).filter(Boolean))];
  const highlighted = (children: ReactNode) => highlightMarkdownChildren(children, terms);
  return <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
    p: ({ children }) => <p>{highlighted(children)}</p>,
    li: ({ children }) => <li>{highlighted(children)}</li>,
    h1: ({ children }) => <h3>{highlighted(children)}</h3>,
    h2: ({ children }) => <h3>{highlighted(children)}</h3>,
    h3: ({ children }) => <h3>{highlighted(children)}</h3>,
    h4: ({ children }) => <h4>{highlighted(children)}</h4>,
    h5: ({ children }) => <h4>{highlighted(children)}</h4>,
    h6: ({ children }) => <h4>{highlighted(children)}</h4>,
    td: ({ children }) => <td>{highlighted(children)}</td>,
    th: ({ children }) => <th>{highlighted(children)}</th>,
    code: ({ children, className }) => <code className={className}>{highlighted(children)}</code>,
    a: ({ href, children }) => <a href={markdownResourceUrl(href, articleId)} target="_blank" rel="noopener noreferrer" onClick={event => event.stopPropagation()}>{highlighted(children)}</a>,
    img: ({ src, alt }) => <SearchImage src={markdownResourceUrl(src, articleId)} alt={alt ?? ""} fallback={fallback} />
  }}>{text}</ReactMarkdown>;
}

export function SearchPage() {
  const { i18n } = useTranslation();
  const navigate = useNavigate();
  const zh = i18n.resolvedLanguage?.startsWith("zh");
  const [params, setParams] = useSearchParams();
  const [draft, setDraft] = useState(params.get("q") ?? "");
  useEffect(() => setDraft(params.get("q") ?? ""), [params]);
  const collections = useQuery({ queryKey: ["collections", i18n.resolvedLanguage], queryFn: api.getCollections });
  const query = useQuery({ queryKey: ["full-search", params.toString(), zh], queryFn: () => api.search(params.toString()), enabled: Boolean(params.get("q")) });
  const rebuild = useMutation({ mutationFn: api.rebuildSearch, onSuccess: () => query.refetch() });
  const scopes: Record<string, string> = zh ? { all: "全部内容", title: "标题", author: "作者", reviewed: "正文", reflection: "感想", annotations: "批注", raw: "原文" } : { all: "All content", title: "Title", author: "Author", reviewed: "Article", reflection: "Reflections", annotations: "Annotations", raw: "Original" };
  function update(name: string, value: string) { const next = new URLSearchParams(params); next.set(name, value); next.delete("offset"); setParams(next); }
  return <main className="page discovery-page">
    <header className="discovery-header"><p className="context-label">{zh ? "知识检索" : "Knowledge retrieval"}</p><h1>{zh ? "全文搜索" : "Full-text search"}</h1><p>{zh ? "找回正文、感想和批注中的片段。用双引号搜索完整短语。" : "Find passages in articles, reflections and annotations. Use quotes for phrases."}</p></header>
    <form className="search-controls" onSubmit={e => { e.preventDefault(); update("q", draft); }}>
      <div className="search-query-row">
        <input aria-label={zh ? "搜索内容" : "Search text"} type="search" value={draft} onChange={e => setDraft(e.target.value)} placeholder={zh ? "关键词或短语…" : "Words or phrases…"} />
        <button className="button-primary" type="submit">{zh ? "搜索" : "Search"}</button>
      </div>
      <div className="search-filter-grid">
        <div className="discovery-select-field"><span>{zh ? "搜索范围" : "Search scope"}</span><InlineSelect ariaLabel={zh ? "搜索范围" : "Search scope"} value={params.get("scope") ?? "all"} onChange={value => update("scope", value)} options={Object.entries(scopes).map(([value, label]) => ({ value, label }))} /></div>
        <div className="discovery-select-field"><span>{zh ? "分类及子分类" : "Collection"}</span><InlineSelect ariaLabel={zh ? "分类及子分类" : "Collection"} value={params.get("collection") ?? ""} onChange={value => update("collection", value)} options={[{ value: "", label: zh ? "所有分类" : "All collections" }, ...collectionOptions(collections.data?.collections ?? []).map(c => ({ value: c.id, label: c.label }))]} /></div>
        <div className="discovery-select-field"><span>{zh ? "来源平台" : "Source platform"}</span><InlineSelect ariaLabel={zh ? "来源平台" : "Source platform"} value={params.get("platform") ?? ""} onChange={value => update("platform", value)} options={[{ value: "", label: zh ? "所有来源" : "All sources" }, { value: "wechat_mp", label: zh ? "微信公众号" : "WeChat" }, { value: "zhihu_zhuanlan", label: zh ? "知乎" : "Zhihu" }, { value: "xiaoheihe", label: zh ? "小黑盒" : "Xiaoheihe" }, { value: "x", label: "X" }]} /></div>
        <label><span>{zh ? "开始日期" : "From"}</span><input type="date" value={params.get("after") ?? ""} onChange={e => update("after", e.target.value)} /></label>
        <label><span>{zh ? "结束日期" : "Until"}</span><input type="date" value={params.get("before") ?? ""} onChange={e => update("before", e.target.value)} /></label>
      </div>
    </form>
    <div className="search-toolbar"><span aria-live="polite">{query.data ? `${query.data.total} ${zh ? "篇文章" : "articles"}` : (zh ? "输入关键词开始搜索" : "Enter a query to search")}</span><button className="button-secondary" type="button" disabled={rebuild.isPending} onClick={() => rebuild.mutate()}>{rebuild.isPending ? (zh ? "正在重建…" : "Rebuilding…") : (zh ? "重建搜索索引" : "Rebuild index")}</button></div>
    {query.isFetching && <LoadingPanel />}
    {(query.error || rebuild.error) && <ErrorPanel message={String(query.error || rebuild.error)} />}
    {query.data?.total === 0 && <div className="discovery-empty"><h2>{zh ? "没有找到匹配内容" : "No matches found"}</h2><p>{zh ? "试试更短的关键词、完整短语或其他搜索范围。" : "Try fewer words, an exact phrase or another search scope."}</p></div>}
    <div className="search-results">{query.data?.results.map(result => <article key={result.article.id} className="search-result">
      <h2><Link to={`/articles/${encodeURIComponent(result.article.id)}`}>{result.article.title}</Link></h2>
      <p className="search-result-meta">{result.article.author} · {result.article.platformLabel}</p>
      {result.matches.map(match => {
        const displayHighlights = match.highlights.map(([start, end]) => [codePointToUtf16(match.text, start), codePointToUtf16(match.text, end)] as [number, number]);
        const firstHit = match.highlights[0];
        const hit = firstHit ? match.text.slice(codePointToUtf16(match.text, firstHit[0]), codePointToUtf16(match.text, firstHit[1])) : "";
        const location = new URLSearchParams({ search: params.get("q") ?? "", field: match.field, digest: match.digest, start: String(match.start + (firstHit?.[0] ?? 0)), hit });
        const destination = `/articles/${encodeURIComponent(result.article.id)}?${location}`;
        return <div key={match.field} className="search-passage" role="link" tabIndex={0} onClick={event => {
          if (!(event.target instanceof Element) || !event.target.closest("a, button")) navigate(destination);
        }} onKeyDown={event => { if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); navigate(destination); } }} aria-label={`${scopes[match.field]}：${cleanPassage(match.text, [], "").text.slice(0, 90)}`}>
          <span>{scopes[match.field]}</span>
          <div className="search-snippet">
            <SearchMarkdown text={match.text} highlights={displayHighlights} articleId={result.article.id} fallback={zh ? "文章图片无法显示" : "Article image unavailable"} />
          </div>
          <Link className="search-passage-location" to={destination}>{zh ? "在文章中查看 ↗" : "View in article ↗"}</Link>
        </div>;
      })}
    </article>)}</div>
    {query.data && query.data.total > 30 && <nav className="search-pagination" aria-label={zh ? "搜索分页" : "Search pages"}>{[ -30, 30 ].map(delta => <button className="button-secondary" type="button" key={delta} disabled={delta < 0 ? Number(params.get("offset") ?? 0) === 0 : Number(params.get("offset") ?? 0) + 30 >= query.data!.total} onClick={() => { const next = new URLSearchParams(params); next.set("offset", String(Math.max(0, Number(params.get("offset") ?? 0) + delta))); setParams(next); }}>{delta < 0 ? (zh ? "上一页" : "Previous") : (zh ? "下一页" : "Next")}</button>)}</nav>}
  </main>;
}
