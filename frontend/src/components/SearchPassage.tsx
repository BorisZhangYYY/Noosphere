import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api";

export function SearchPassage({ articleId }: { articleId: string }) {
  const [params] = useSearchParams();
  const { i18n } = useTranslation();
  const zh = i18n.resolvedLanguage?.startsWith("zh");
  const args = new URLSearchParams(params); args.set("article", articleId);
  const query = useQuery({ queryKey: ["search-passage", args.toString()], queryFn: () => api.searchPassage(args.toString()), enabled: Boolean(params.get("digest")) });
  if (!params.get("digest")) return null;
  const labels: Record<string, string> = zh ? { reviewed: "正文", raw: "原文", reflection: "感想", annotations: "批注", title: "标题", author: "作者" } : { reviewed: "Article", raw: "Original", reflection: "Reflections", annotations: "Annotations", title: "Title", author: "Author" };
  return <section className="search-context" aria-label={zh ? "搜索片段上下文" : "Search passage context"}>
    <strong>{labels[params.get("field") ?? "reviewed"]}</strong>
    <Link to={`/search?q=${encodeURIComponent(params.get("search") ?? "")}`}>{zh ? "返回搜索" : "Back to search"}</Link>
    {query.isPending && <p>{zh ? "正在定位…" : "Locating passage…"}</p>}
    {query.error && <p role="alert">{String(query.error)}</p>}
    {query.data?.changed ? <p>{zh ? "此内容已修改，请重新搜索以定位最新片段。" : "This content has changed. Search again to locate the current passage."}</p> : <pre>{query.data?.text}</pre>}
  </section>;
}
