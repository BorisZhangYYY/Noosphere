import { ArrowRight, BookOpenText, CloudArrowUp, MagnifyingGlass, Path } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { InlineSelect } from "../components/InlineSelect";
import { ErrorPanel, LoadingPanel } from "../components/StatePanel";
import { StatusBadge } from "../components/StatusBadge";
import { localizedPlatformLabel } from "../localization";
import type { ArticleSummary } from "../types";

function relativeTime(value: string | null, locale: string, unknown: string, justNow: string) {
  if (!value) return unknown;
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return value;
  const hours = Math.max(0, Math.round((Date.now() - timestamp) / 3_600_000));
  if (hours < 1) return justNow;
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (hours < 24) return formatter.format(-hours, "hour");
  const days = Math.round(hours / 24);
  return formatter.format(-days, "day");
}

function ArticleRow({ article }: { article: ArticleSummary }) {
  const { t, i18n } = useTranslation();
  const platformLabel = localizedPlatformLabel(article.platform, article.platformLabel, t);
  return (
    <Link className="article-row" to={`/articles/${encodeURIComponent(article.id)}`}>
      <span className="source-monogram" aria-hidden="true">{platformLabel.slice(0, 1).toUpperCase()}</span>
      <span className="article-primary">
        <strong>{article.title}</strong>
        <span>{article.classification ? [article.classification.tag_name, article.classification.subtag_name].filter(Boolean).join(" / ") : article.author || platformLabel}</span>
      </span>
      <span className="article-source">{platformLabel}</span>
      <span className="article-captured">{relativeTime(article.capturedAt, i18n.resolvedLanguage ?? i18n.language, t("common.unknown"), t("library.justNow"))}</span>
      <StatusBadge status={article.status} />
      <ArrowRight size={18} className="row-arrow" />
    </Link>
  );
}

export function DashboardPage() {
  const { t, i18n } = useTranslation();
  const query = useQuery({ queryKey: ["articles", i18n.resolvedLanguage], queryFn: api.listArticles });
  const taxonomyQuery = useQuery({ queryKey: ["taxonomy", i18n.resolvedLanguage], queryFn: api.getTaxonomy });
  const [categoryFilter, setCategoryFilter] = useState("");
  const [search, setSearch] = useState("");
  const articles = query.data?.articles ?? [];
  const taxonomyCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const article of articles) {
      const classification = article.classification;
      if (!classification) continue;
      counts.set(classification.tag_id, (counts.get(classification.tag_id) ?? 0) + 1);
      if (classification.subtag_id) counts.set(classification.subtag_id, (counts.get(classification.subtag_id) ?? 0) + 1);
    }
    return counts;
  }, [articles]);
  const normalizedSearch = search.trim().toLocaleLowerCase();
  const visibleArticles = articles.filter((article) => {
    const categoryMatches = !categoryFilter || article.classification?.tag_id === categoryFilter || article.classification?.subtag_id === categoryFilter;
    const searchMatches = !normalizedSearch || [article.title, article.author ?? "", article.platformLabel, ...(article.searchTerms ?? [])].join(" ").toLocaleLowerCase().includes(normalizedSearch);
    return categoryMatches && searchMatches;
  });
  const reviewed = articles.filter((article) => article.status === "reviewed" || article.status === "uploaded").length;
  const uploaded = articles.filter((article) => article.status === "uploaded").length;
  const needsAttention = articles.filter((article) => article.status === "failed").length;

  return (
    <div className="page dashboard-page">
      <header className="page-header dashboard-header">
        <div>
          <p className="context-label">{t("library.eyebrow")}</p>
          <h1>{t("library.title")}</h1>
          <p>{t("library.description")}</p>
        </div>
        <label className="search-field">
          <MagnifyingGlass size={19} />
          <input type="search" placeholder={t("library.search")} aria-label={t("library.search")} value={search} onChange={(event) => setSearch(event.target.value)} />
          <kbd>⌘K</kbd>
        </label>
      </header>

      <section className="metrics-strip" aria-label={t("library.summary")}>
        <div><BookOpenText size={22} /><span><strong>{articles.length}</strong>{t("library.captured")}</span></div>
        <div><Path size={22} /><span><strong>{reviewed}</strong>{t("library.reviewed")}</span></div>
        <div><CloudArrowUp size={22} /><span><strong>{uploaded}</strong>{t("library.uploaded")}</span></div>
        <div className={needsAttention ? "metric-attention" : ""}><span><strong>{needsAttention}</strong>{t("library.attention")}</span></div>
      </section>

      <section className="workspace-surface recent-section">
        <div className="section-heading">
          <div><h2>{t("library.recentTitle")}</h2><p>{t("library.recentDescription")}</p></div>
          <span>{t("library.total", { count: visibleArticles.length })}</span>
        </div>
        {taxonomyQuery.data?.tags.length ? <div className="taxonomy-shelf" aria-label={t("library.taxonomy")}>
          <button type="button" className={!categoryFilter ? "active taxonomy-all" : "taxonomy-all"} onClick={() => setCategoryFilter("")}><span>{t("library.allTags")}</span><small>{articles.length}</small></button>
          {taxonomyQuery.data.tags.map((tag) => {
            const familyValues = new Set([tag.id, ...tag.children.map((child) => child.id)]);
            const selected = familyValues.has(categoryFilter) ? categoryFilter : tag.id;
            return <div className={`taxonomy-family${familyValues.has(categoryFilter) ? " active" : ""}`} key={tag.id} title={tag.description}>
              <InlineSelect
                value={selected}
                ariaLabel={tag.name}
                onChange={setCategoryFilter}
                options={[
                  { value: tag.id, label: <span className="taxonomy-option-label"><span>{tag.name}</span><small>{taxonomyCounts.get(tag.id) ?? 0}</small></span>, description: tag.description },
                  ...tag.children.map((child) => ({ value: child.id, label: <span className="taxonomy-option-label"><span>{child.name}</span><small>{taxonomyCounts.get(child.id) ?? 0}</small></span>, description: child.description }))
                ]}
              />
            </div>;
          })}
        </div> : null}
        <div className="article-list-header" aria-hidden="true">
          <span>{t("library.columnArticle")}</span><span>{t("library.columnSource")}</span><span>{t("library.columnCaptured")}</span><span>{t("library.columnStatus")}</span>
        </div>
        {query.isLoading && <LoadingPanel />}
        {query.isError && <ErrorPanel message={(query.error as Error).message} />}
        {!query.isLoading && !query.isError && articles.length === 0 && (
          <div className="empty-state">
            <div className="empty-illustration"><BookOpenText size={34} /></div>
            <h3>{t("library.emptyTitle")}</h3>
            <p>{t("library.emptyDescription")}</p>
          </div>
        )}
        {visibleArticles.slice(0, 8).map((article) => <ArticleRow article={article} key={article.id} />)}
      </section>

      <section className="pipeline-callout">
        <div className="pipeline-symbol"><Path size={28} /></div>
        <div><h2>{t("library.activityTitle")}</h2><p>{needsAttention ? t("library.activityIssues", { count: needsAttention }) : t("library.activityClear")}</p></div>
        <Link to="/pipeline" className="button-secondary">{t("library.viewPipeline")} <ArrowRight size={17} /></Link>
      </section>
    </div>
  );
}
