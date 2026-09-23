import { useEffect, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import type { CollectionNode } from "../types";
import { cleanPassage } from "../markdownClean";
import { ErrorPanel, LoadingPanel } from "../components/StatePanel";

function collectionOptions(nodes: CollectionNode[], prefix = ""): { id: string; label: string }[] { return nodes.flatMap(node => [{ id: node.id, label: prefix + node.name }, ...collectionOptions(node.children, prefix + node.name + " / ")]); }

export function SearchPage() {
  const { i18n } = useTranslation();
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
    <header><h1>{zh ? "全文搜索" : "Full-text search"}</h1><p>{zh ? "找回正文、感想和批注中的片段。用双引号搜索完整短语。" : "Find passages in articles, reflections and annotations. Use quotes for phrases."}</p></header>
    <form className="discovery-filters" onSubmit={e => { e.preventDefault(); update("q", draft); }}>
      <input aria-label={zh ? "搜索内容" : "Search text"} type="search" value={draft} onChange={e => setDraft(e.target.value)} placeholder={zh ? "关键词或短语…" : "Words or phrases…"} />
      <button type="submit">{zh ? "搜索" : "Search"}</button>
      <select aria-label={zh ? "搜索范围" : "Search scope"} value={params.get("scope") ?? "all"} onChange={e => update("scope", e.target.value)}>{Object.entries(scopes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
      <select aria-label={zh ? "分类及子分类" : "Collection and descendants"} value={params.get("collection") ?? ""} onChange={e => update("collection", e.target.value)}><option value="">{zh ? "所有分类" : "All collections"}</option>{collectionOptions(collections.data?.collections ?? []).map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select>
      <select aria-label={zh ? "来源平台" : "Source platform"} value={params.get("platform") ?? ""} onChange={e => update("platform", e.target.value)}><option value="">{zh ? "所有来源" : "All sources"}</option><option value="wechat_mp">{zh ? "微信公众号" : "WeChat"}</option><option value="zhihu_zhuanlan">{zh ? "知乎" : "Zhihu"}</option><option value="xiaoheihe">{zh ? "小黑盒" : "Xiaoheihe"}</option><option value="x">X</option></select>
      <label>{zh ? "开始日期" : "From"}<input type="date" value={params.get("after") ?? ""} onChange={e => update("after", e.target.value)} /></label>
      <label>{zh ? "结束日期" : "Until"}<input type="date" value={params.get("before") ?? ""} onChange={e => update("before", e.target.value)} /></label>
    </form>
    <div className="discovery-toolbar"><span aria-live="polite">{query.data ? `${query.data.total} ${zh ? "篇文章" : "articles"}` : ""}</span><button type="button" disabled={rebuild.isPending} onClick={() => rebuild.mutate()}>{zh ? "重建搜索索引" : "Rebuild index"}</button></div>
    {query.isFetching && <LoadingPanel />}
    {(query.error || rebuild.error) && <ErrorPanel message={String(query.error || rebuild.error)} />}
    {query.data?.total === 0 && <p>{zh ? "没有找到匹配内容，试试更短的关键词或其他搜索范围。" : "No matches. Try fewer words or another scope."}</p>}
    <div className="search-results">{query.data?.results.map(result => <article key={result.article.id} className="search-result">
      <h2><Link to={`/articles/${encodeURIComponent(result.article.id)}`}>{result.article.title}</Link></h2>
      <p className="search-result-meta">{result.article.author} · {result.article.platformLabel}</p>
      {result.matches.map(match => {
        const cleaned = cleanPassage(match.text, match.highlights, zh ? "[图片]" : "[image]");
        return <div key={match.field} className="search-passage"><span>{scopes[match.field]}</span><p>{Array.from(cleaned.text).map((char, index) => cleaned.highlights.some(([start, end]) => index >= start && index < end) ? <mark key={index}>{char}</mark> : char)}</p><Link to={`/articles/${encodeURIComponent(result.article.id)}?${new URLSearchParams({ search: params.get("q") ?? "", field: match.field, digest: match.digest, start: String(match.start) })}`}>{zh ? "打开片段" : "Open passage"}</Link></div>;
      })}
    </article>)}</div>
    {query.data && query.data.total > 30 && <nav className="discovery-toolbar" aria-label={zh ? "搜索分页" : "Search pages"}>{[ -30, 30 ].map(delta => <button type="button" key={delta} disabled={delta < 0 ? Number(params.get("offset") ?? 0) === 0 : Number(params.get("offset") ?? 0) + 30 >= query.data!.total} onClick={() => { const next = new URLSearchParams(params); next.set("offset", String(Math.max(0, Number(params.get("offset") ?? 0) + delta))); setParams(next); }}>{delta < 0 ? (zh ? "上一页" : "Previous") : (zh ? "下一页" : "Next")}</button>)}</nav>}
  </main>;
}
